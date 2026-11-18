"""从GitHub受信构建运行读取同源码候选，保留原手动发布批次校验。"""
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import manage
from candidate_images import BUNDLE_NAME, MANIFEST_NAME, METADATA_NAME, adopt_candidate, export_candidate
from release_ci import validate_publish_source
from system_update_contract import MANIFEST_LIMIT, MAX_BUNDLE_BYTES, REPOSITORY, strict_json

WORKFLOW = '.github/workflows/v3-build.yml'
REQUIRED_STEPS = ('验证系统更新合同与恢复状态机', '构建两个镜像并生成版本清单',
    '导出可信候选镜像', '上传可信候选产物')
MAX_ARCHIVE = MAX_BUNDLE_BYTES + 8 * 1024 * 1024


def check_checkout(revision: str) -> None:
    """确认发布工作区仍是冻结的干净源码。

    :param revision: 本次Action冻结的源码SHA。
    :return: None；源码或工作区发生变化时拒绝复用。
    """
    if (manage.command('git', 'rev-parse', 'HEAD', capture=True).strip() != revision
            or manage.command('git', 'status', '--porcelain', capture=True).strip()):
        raise ValueError('发布工作区与冻结源码不一致，拒绝复用候选')


def github_json(endpoint: str) -> dict:
    """通过当前job令牌读取固定仓库API，隐藏鉴权及原始错误正文。

    :param endpoint: 本模块拼装的仓库内API路径。
    :return: 有界GitHub对象。
    """
    result = subprocess.run(['gh', 'api', 'repos/' + REPOSITORY + '/' + endpoint],
        capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError('读取候选构建来源失败，请核对Actions读取权限与网络')
    return strict_json(result.stdout, 4 * 1024 * 1024)


def trusted_run(run: dict, revision: str, ref: str) -> bool:
    """只接受本仓受信分支上同一源码的构建工作流。

    :param run: GitHub返回的实际运行对象。
    :param revision: 本次冻结的发布源码。
    :param ref: 本次受信分支。
    :return: 来源全部匹配时为真。
    """
    repository, head = run.get('repository') or {}, run.get('head_repository') or {}
    return (type(run.get('id')) is int and run['id'] > 0
        and type(run.get('run_attempt')) is int and run['run_attempt'] > 0
        and run.get('head_sha') == revision and run.get('head_branch') == ref.removeprefix('refs/heads/')
        and run.get('event') in ('push', 'workflow_dispatch')
        and str(run.get('path', '')).split('@', 1)[0] == WORKFLOW
        and repository.get('full_name', '').lower() == REPOSITORY.lower()
        and head.get('full_name', '').lower() == REPOSITORY.lower()
        and type(repository.get('id')) is int and repository['id'] > 0
        and head.get('id') == repository['id'])


def candidate_artifact(run: dict, jobs: dict, artifacts: dict) -> dict | None:
    """核对必要步骤和当前attempt的不可变归档，允许缓存post仍在进行。

    :param run: 已核对来源的实际运行。
    :param jobs: 原attempt的作业和步骤。
    :param artifacts: 原运行的实际产物列表。
    :return: 受信且就绪的唯一产物，尚未就绪时为None。
    """
    build_jobs = [job for job in jobs.get('jobs', []) if job.get('name') == 'build']
    if len(build_jobs) != 1:
        return None
    steps = build_jobs[0].get('steps', [])
    for name in REQUIRED_STEPS:
        matching = [step for step in steps if step.get('name') == name]
        if len(matching) != 1 or matching[0].get('status') != 'completed' or matching[0].get('conclusion') != 'success':
            return None
    expected = f"v3-candidate-{run['id']}-{run['run_attempt']}"
    matches = [item for item in artifacts.get('artifacts', []) if item.get('name') == expected]
    if len(matches) > 1:
        raise ValueError('同批候选产物不唯一')
    if not matches or matches[0].get('expired') is True:
        return None
    artifact = matches[0]
    origin = artifact.get('workflow_run') or {}
    repository_id = run['repository']['id']
    if (type(artifact.get('id')) is not int or artifact['id'] <= 0
            or artifact.get('expired') is not False
            or type(artifact.get('size_in_bytes')) is not int or not 0 < artifact['size_in_bytes'] <= MAX_ARCHIVE
            or not re.fullmatch(r'sha256:[a-f0-9]{64}', str(artifact.get('digest', '')))
            or origin.get('id') != run['id'] or origin.get('head_sha') != run['head_sha']
            or origin.get('head_branch') != run['head_branch']
            or origin.get('repository_id') != repository_id or origin.get('head_repository_id') != repository_id):
        raise ValueError('候选归档的来源或摘要无效')
    return artifact


def download_archive(artifact: dict, target: Path) -> None:
    """下载固定归档ID并验证GitHub记录的原始ZIP摘要。

    :param artifact: 已冻结并核对来源的归档对象。
    :param target: 全新私有ZIP路径。
    :return: None；下载失败或摘要不符时拒绝继续。
    """
    with target.open('xb') as stream:
        os.chmod(target, 0o600)
        result = subprocess.run(['gh', 'api', f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip"],
            stdout=stream, stderr=subprocess.DEVNULL, timeout=900)
    if result.returncode:
        raise RuntimeError('候选归档下载失败')
    if target.stat().st_size > MAX_ARCHIVE:
        raise ValueError('候选归档超过下载预算')
    with target.open('rb') as stream:
        if 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest() != artifact['digest']:
            raise ValueError('候选归档的GitHub摘要不匹配')


def unpack_archive(path: Path, folder: Path) -> None:
    """只提取固定三份普通文件，拒绝路径穿越、重复成员与膨胀归档。

    :param path: 已完成GitHub摘要核验的ZIP。
    :param folder: 当前进程的私有候选目录。
    :return: None。
    """
    limits = {METADATA_NAME: MANIFEST_LIMIT, MANIFEST_NAME: MANIFEST_LIMIT, BUNDLE_NAME: MAX_BUNDLE_BYTES}
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) != 3 or {item.filename for item in members} != set(limits):
            raise ValueError('候选归档包含未知或重复路径')
        for item in members:
            mode = item.external_attr >> 16
            if (item.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                    or not 0 < item.file_size <= limits[item.filename] or item.flag_bits & 1):
                raise ValueError('候选归档成员类型或大小无效')
            target = folder / item.filename
            with archive.open(item) as source, target.open('xb') as output:
                os.chmod(target, 0o600)
                remaining = item.file_size
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError('候选归档成员不完整')
                    output.write(block)
                    remaining -= len(block)
                if source.read(1):
                    raise ValueError('候选归档成员超过声明大小')


def resolve_candidate(manifest_path: Path, wait_seconds: int = 1200) -> bool:
    """查找或等待同源码候选，缺失时返回原完整构建路径。

    :param manifest_path: 本次正式本地清单的全新路径。
    :param wait_seconds: 在途候选的最长等待时间。
    :return: 已验证并换批复用时为真；无可用候选时为假。
    """
    validate_publish_source()
    revision, ref = os.environ['GITHUB_SHA'], os.environ['GITHUB_REF']
    check_checkout(revision)
    rows = github_json(f'actions/workflows/v3-build.yml/runs?head_sha={revision}&per_page=30')['workflow_runs']
    candidates = [run for run in rows if trusted_run(run, revision, ref)]
    if not candidates:
        return False
    selected = max(candidates, key=lambda run: run['id'])
    run_id, attempt = selected['id'], selected['run_attempt']
    deadline = time.monotonic() + wait_seconds
    while True:
        run = github_json(f'actions/runs/{run_id}')
        if not trusted_run(run, revision, ref) or run['run_attempt'] != attempt:
            raise ValueError('候选构建来源或attempt已变化')
        if run['status'] == 'completed' and run.get('conclusion') != 'success':
            return False
        jobs = github_json(f'actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100')
        artifacts = github_json(f'actions/runs/{run_id}/artifacts?per_page=100')
        artifact = candidate_artifact(run, jobs, artifacts)
        if artifact is not None:
            break
        if run['status'] == 'completed':
            return False
        if time.monotonic() >= deadline:
            raise RuntimeError('同源码候选尚未完成，请稍后重试发布')
        print(json.dumps({'event': 'flower2api-candidate-wait', 'run_id': run_id, 'attempt': attempt}), flush=True)
        time.sleep(10)
    identity = {'repository': REPOSITORY, 'ref': ref, 'revision': revision, 'run_id': run_id, 'run_attempt': attempt}
    with tempfile.TemporaryDirectory(prefix='flower2api-candidate-') as temporary:
        root = Path(temporary)
        archive = root / 'artifact.zip'
        download_archive(artifact, archive)
        folder = root / 'candidate'
        folder.mkdir(mode=0o700)
        unpack_archive(archive, folder)
        current = github_json(f'actions/runs/{run_id}')
        if (not trusted_run(current, revision, ref) or current['run_attempt'] != attempt
                or (current['status'] == 'completed' and current.get('conclusion') != 'success')):
            raise ValueError('候选下载期间来源已变化')
        adopt_candidate(folder, identity, manifest_path)
    print(json.dumps({'event': 'flower2api-candidate-reused', 'run_id': run_id, 'attempt': attempt,
        'revision': revision}), flush=True)
    return True


def main() -> None:
    """执行受信候选导出或发布侧复用。:return: None；异常保持非零退出。"""
    parser = argparse.ArgumentParser(description='同源码候选镜像交付')
    parser.add_argument('action', choices=('export', 'resolve'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--wait-seconds', type=int, default=1200)
    args = parser.parse_args()
    if args.wait_seconds < 0 or args.wait_seconds > 3600:
        parser.error('候选等待时间须在0到3600秒之间')
    if args.action == 'export':
        if args.output is None:
            parser.error('候选导出需要--output')
        export_candidate(args.manifest, args.output)
        return
    reused = resolve_candidate(args.manifest, args.wait_seconds)
    print(json.dumps({'event': 'flower2api-candidate-result', 'reused': reused}), flush=True)
    if os.environ.get('GITHUB_OUTPUT'):
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
            stream.write('reused=' + str(reused).lower() + '\n')


if __name__ == '__main__':
    main()
