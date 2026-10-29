"""在当前镜像实际验证固定原版的额外官方集合，不改变主原生合同。"""
from __future__ import annotations

import json
import hashlib
import sys
import time
import uuid
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from shutil import copytree

from docker import from_env
from docker.errors import NotFound


ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / 'orchestrator'))
from project_verifier import _NATIVE_EXECUTE
from project_scenario_content import validate_environment


WORKSPACE = ROOT / '.deploy/project-catalog-hundred/stage-03'
IMAGE = 'ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1'


def calibrate(slug: str, attempt: int) -> dict:
    """用产品原生引导、离线依赖和固定源码执行额外官方入口。

    :param slug: 本轮已准备的固定项目键。
    :param attempt: 留存原失败现场的独立校准编号。
    :return: 固定原版的额外集合、资源与清理结果，不代表模型完成或修改候选回归。
    """
    project = WORKSPACE / 'drafts/projects' / slug
    environment = WORKSPACE / 'drafts/environments' / (slug + '-py312')
    profile = validate_environment(environment.parent, environment.name)
    resources = profile['regression']
    runner_timeout = max(1, resources['timeout_sec'] - 30)
    directory = WORKSPACE / 'additional-native' / ('attempt-' + str(attempt).zfill(3)) / slug
    directory.mkdir(parents=True, exist_ok=False)
    inputs, output = directory / 'request', directory / 'evidence'
    candidate = directory / 'candidate'
    copytree(project / 'seed', candidate)
    inputs.mkdir(mode=0o755)
    # 父挂载只读时runc不能创建子挂载点，必须在挂载前预置目录。
    copytree(project / 'verification', inputs / 'verification')
    (inputs / 'environment-profile.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    output.mkdir(mode=0o777)
    output.chmod(0o777)
    request = {'script': 'verification/native_additional_original.py', 'args': [],
        'python_paths': ['library/src', 'library'], 'requirements': profile['requirements']}
    (inputs / 'native.json').write_text(json.dumps(request), encoding='utf-8')
    (inputs / 'answer.txt').write_text('', encoding='utf-8')
    client = from_env()
    image = client.images.get(IMAGE)
    container = None
    container_id = None
    started = time.monotonic()
    result = {'project': slug, 'status': 'error', 'real_model_calls': 0}
    try:
        container = client.containers.create(image.id,
            name='bench-project-calibrate-' + uuid.uuid4().hex[:12],
            entrypoint=['python3', '-I', '-B', '-c'], command=[_NATIVE_EXECUTE],
            user='1000:1000', working_dir='/work', network_mode='none', read_only=True,
            cap_drop=['ALL'], security_opt=['no-new-privileges'],
            mem_limit=f"{resources['memory_mb']}m", memswap_limit=f"{resources['memory_mb']}m",
            pids_limit=resources['pids_limit'],
            tmpfs={'/work': 'rw,exec,nosuid,nodev,size=1073741824,mode=1777',
                '/tmp': 'rw,nosuid,nodev,size=67108864,mode=1777'},
            volumes={str(candidate): {'bind': '/source', 'mode': 'ro'},
                str(project / 'seed'): {'bind': '/baseline', 'mode': 'ro'},
                str(inputs): {'bind': '/request-data', 'mode': 'ro'},
                str(environment): {'bind': '/offline', 'mode': 'ro'},
                str(output): {'bind': '/evidence', 'mode': 'rw'}},
            environment={'HOME': '/tmp', 'PYTHONDONTWRITEBYTECODE': '1', 'PIP_CONFIG_FILE': '/dev/null'},
            labels={'vibebench.product': 'v3', 'vibebench.role': 'verification',
                'vibebench.verification': 'project-catalog-hundred-stage-03'})
        container_id = container.id
        container.start()
        # 离线准备额外留出与产品一致的六十秒，回归脚本沿用产品的资源时限。
        completed = container.wait(timeout=resources['timeout_sec'] + 60)
        stdout = container.logs(stdout=True, stderr=False)
        stderr = container.logs(stdout=False, stderr=True)
        (directory / 'stdout.log').write_bytes(stdout)
        (directory / 'stderr.log').write_bytes(stderr)
        container.reload()
        marker = b'VIBEBENCH_NATIVE_READY_V1\n'
        report = json.loads(stdout.removeprefix(marker)) if stdout.startswith(marker) else None
        valid = (completed['StatusCode'] == 0 and report is not None
            and report.get('status') == 'passed')
        result.update(status='passed' if valid else 'error', returncode=completed['StatusCode'],
            bootstrap_ready=stdout.startswith(marker), native=report,
            image_id=image.id, repository_digests=image.attrs.get('RepoDigests', []),
            network='none', user='1000:1000', memory_bytes=resources['memory_mb'] * 1024 * 1024,
            swap_bytes=0, pids_limit=resources['pids_limit'], root_read_only=True,
            regression_timeout_sec=resources['timeout_sec'], runner_timeout_sec=runner_timeout,
            offline_preparation_budget_sec=60,
            control_script_sha256=hashlib.sha256((inputs / 'verification/native_additional_original.py').read_bytes()).hexdigest(),
            account_credentials_mounted=False, oom_killed=container.attrs['State']['OOMKilled'])
    except Exception as error:
        result.update(error_type=type(error).__name__, message=str(error)[:1000])
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception as error:
                result['cleanup_error'] = type(error).__name__ + ':' + str(error)[:1000]
        removed = container_id is None
        if container_id:
            try:
                client.containers.get(container_id)
            except NotFound:
                removed = True
            except Exception as error:
                result['cleanup_observation_error'] = type(error).__name__ + ':' + str(error)[:1000]
        if not removed:
            result['status'] = 'error'
        result.update(container_removed=removed, elapsed_sec=round(time.monotonic() - started, 6))
        (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        client.close()
    return result


def main() -> None:
    """独立校准指定仓，输出实际摘要并以失败退出码保留未通过事实。

    :return: None。
    """
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--projects', nargs='+', required=True)
    options = parser.parse_args()
    if options.attempt < 1:
        parser.error('校准编号必须为正整数')
    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(calibrate, slug, options.attempt)
            for slug in options.projects]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            native = result.get('native') or {}
            print(json.dumps({'project': result['project'], 'status': result['status'],
                'counts': {'passed': native.get('passed'), 'collected': native.get('collected')}, 'doctests': native.get('strict_doctest_count'),
                'subtests': native.get('subtest_count'), 'removed': result['container_removed'],
                'elapsed_sec': result['elapsed_sec']}, ensure_ascii=False), flush=True)
    raise SystemExit(0 if all(item['status'] == 'passed' and item['container_removed'] for item in results) else 1)


if __name__ == '__main__':
    main()
