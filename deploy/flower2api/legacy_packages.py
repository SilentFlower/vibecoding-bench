#!/usr/bin/env python3
"""预览和精确删除已退役的三项旧GHCR包，默认只读取元数据。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = 'SilentFlower/vibecoding-bench'
TARGETS = ('vibebench-orchestrator', 'vibebench-worker', 'vibebench-sidecar')
PROTECTED = ('vibebench-v3-control', 'vibebench-v3-account', 'flower2api-control', 'flower2api-account')
WORKFLOW = '.github/workflows/ghcr-legacy-cleanup.yml'
ROOT = Path(__file__).resolve().parents[2]


class ApiError(RuntimeError):
    """只公开HTTP状态，避免将远端错误正文或认证信息写入收据。"""

    def __init__(self, status: int):
        """保存受控状态。:param status: HTTP状态码，0表示连接失败。:return: None。"""
        self.status = status
        super().__init__(f'GitHub包API失败，HTTP={status}')


class NoRedirect(HTTPRedirectHandler):
    """固定GitHub API来源，拒绝携带认证跳转。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """拒绝重定向。:param req: 原请求。:param fp: 响应。:param code: 状态。:param msg: 消息。:param headers: 响应头。:param newurl: 目标。:return: None。"""
        return None


class GitHubApi:
    """使用当前进程令牌和固定来源执行有界包API调用。"""

    def __init__(self, token: str):
        """核对认证配置。:param token: 私有令牌。:return: None。"""
        if not token or any(character.isspace() for character in token):
            raise ValueError('需要有效GitHub令牌')
        self.token = token
        self.opener = build_opener(NoRedirect())

    def request(self, method: str, path: str):
        """请求精确API路径。:param method: GET或DELETE。:param path: 固定相对路径。:return: JSON或None。"""
        if method not in ('GET', 'DELETE') or not path.startswith('/') or path.startswith('//'):
            raise ValueError('包API参数错误')
        request = Request('https://api.github.com' + path, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'flower2api-legacy-cleanup'})
        try:
            with self.opener.open(request, timeout=30) as response:
                if method == 'DELETE':
                    if response.status != 204:
                        raise ApiError(response.status)
                    return None
                payload = response.read(4 * 1024 * 1024 + 1)
                if len(payload) > 4 * 1024 * 1024:
                    raise ValueError('包API响应超出预算')
                return json.loads(payload)
        except HTTPError as error:
            raise ApiError(error.code) from None
        except OSError:
            raise ApiError(0) from None


def digest(value: dict) -> str:
    """生成冻结材料摘要。:param value: JSON材料。:return: 规范字节SHA256。"""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def package_path(name: str) -> str:
    """限制所有包写入到固定旧三项。:param name: 包名。:return: 受控包API路径。"""
    if name not in TARGETS:
        raise ValueError('包名不在退役白名单')
    return '/users/SilentFlower/packages/container/' + name


def pages(api, path: str) -> list:
    """完整读取有界分页。:param api: API边界。:param path: 读入口。:return: 全部项目。"""
    values = []
    for page in range(1, 101):
        batch = api.request('GET', f'{path}?per_page=100&page={page}')
        if not isinstance(batch, list):
            raise ValueError('包API分页格式错误')
        values.extend(batch)
        if len(batch) < 100:
            return values
    raise ValueError('包API分页超出预算')


def snapshot(api, name: str) -> dict:
    """核对包归属和全部版本。:param api: API边界。:param name: 固定包名。:return: 冻结安全身份。"""
    path = package_path(name)
    value = api.request('GET', path)
    if (not isinstance(value, dict) or value.get('name') != name or value.get('package_type') != 'container'
            or value.get('owner', {}).get('login', '').lower() != 'silentflower'
            or value.get('repository', {}).get('full_name', '').lower() != REPOSITORY.lower()
            or type(value.get('id')) is not int or value['id'] <= 0):
        raise ValueError('旧包归属或身份不符')
    versions = []
    for version in pages(api, path + '/versions'):
        tags = version.get('metadata', {}).get('container', {}).get('tags')
        if (type(version.get('id')) is not int or version['id'] <= 0 or not isinstance(version.get('name'), str)
                or not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags)):
            raise ValueError('包版本格式错误')
        versions.append({'id': version['id'], 'name': version['name'], 'tags': sorted(tags)})
    versions.sort(key=lambda item: item['id'])
    if len({item['id'] for item in versions}) != len(versions) or value.get('version_count') != len(versions):
        raise ValueError('包版本数量发生变化')
    return {'name': name, 'id': value['id'], 'repository': REPOSITORY, 'versions': versions}


def reference_evidence(path: Path, *, now: datetime | None = None) -> dict:
    """核对已记录宿主引用的时效与保护范围。:param path: 只读核验材料。:param now: 测试时钟。:return: 原材料。"""
    value = json.loads(path.read_text())
    age = ((now or datetime.now(timezone.utc)) - datetime.fromisoformat(value['checked_at'])).total_seconds()
    if (value.get('schema_version') != 1 or not 0 <= age <= 86400 or value.get('legacy_references') != []
            or type(value.get('container_count')) is not int or value['container_count'] < 0
            or value.get('protected_packages') != list(PROTECTED)):
        raise ValueError('需要24小时内且无旧镜像引用的完整宿主核验')
    return value


def check_retirement(api, root: Path) -> None:
    """检查旧工作流已退役且没有在途旧发布。:param api: API边界。:param root: 核验源码。:return: None。"""
    workflow = (root / '.github/workflows/docker-publish.yml').read_text()
    if 'LEGACY_IMAGES_RETIRED' not in workflow or any(word in workflow for word in (
            'docker/build-push-action', 'docker push', 'packages: write', 'IMAGE_NAMESPACE')):
        raise ValueError('旧三镜像发布入口尚未退役')
    for status in ('queued', 'in_progress', 'waiting', 'pending', 'requested'):
        runs = api.request('GET', '/repos/' + REPOSITORY
            + '/actions/workflows/docker-publish.yml/runs?per_page=1&status=' + status)
        if not isinstance(runs, dict) or runs.get('workflow_runs') != [] or runs.get('total_count') != 0:
            raise ValueError('存在尚未结束的旧发布任务或运行状态未知')


def preview(api, revision: str, evidence: dict) -> dict:
    """完整预检后生成唯一冻结计划。:param api: API边界。:param revision: 源码SHA。:param evidence: 只读宿主核验。:return: 安全计划。"""
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('预览需要完整源码SHA')
    return {'schema_version': 1, 'repository': REPOSITORY, 'revision': revision,
        'reference_evidence_sha256': digest(evidence), 'packages': [snapshot(api, name) for name in TARGETS]}


def validate_origin(api, plan: dict, run_id: str) -> None:
    """只接受同源码受信手动预览的计划。:param api: API边界。:param plan: 冻结计划。:param run_id: 预览运行。:return: None。"""
    if not re.fullmatch(r'[1-9][0-9]*', run_id):
        raise ValueError('需要精确预览运行ID')
    run = api.request('GET', '/repos/' + REPOSITORY + '/actions/runs/' + run_id)
    if (run.get('head_sha') != plan['revision'] or run.get('event') != 'workflow_dispatch'
            or run.get('conclusion') != 'success' or run.get('path') != WORKFLOW
            or run.get('head_branch') != 'flower2api'
            or run.get('repository', {}).get('full_name') != REPOSITORY):
        raise ValueError('包清理预览来源不符')


def save(path: Path, value: dict) -> None:
    """原子保存同一运行的安全状态。:param path: 已认领输出。:param value: 收据。:return: None。"""
    temporary = path.with_suffix('.tmp')
    with temporary.open('x') as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def apply(api, plan: dict, output: Path, revision: str, evidence: dict) -> dict:
    """完整重验后按三项范围删除，失败保留已完成收据。:param api: API边界。:param plan: 冻结计划。:param output: 新收据。:param revision: 当前SHA。:param evidence: 当前核验。:return: 完整收据。"""
    if output.exists():
        raise ValueError('收据路径必须全新')
    if plan != preview(api, revision, evidence):
        raise ValueError('包清理冻结计划发生变化')
    receipt = {'schema_version': 1, 'plan_sha256': digest(plan), 'status': 'running', 'deleted': [], 'failed': None}
    save(output, receipt)
    for item in plan['packages']:
        name = item['name']
        try:
            if snapshot(api, name) != item:
                raise ValueError('删除前包身份发生变化')
            api.request('DELETE', package_path(name))
            receipt['deleted'].append({'name': name, 'id': item['id'], 'delete_status': 204, 'verified_absent': False})
            save(output, receipt)
            try:
                api.request('GET', package_path(name))
            except ApiError as error:
                if error.status != 404:
                    raise
            else:
                raise ValueError('删除后仍能读取旧包')
            receipt['deleted'][-1]['verified_absent'] = True
            save(output, receipt)
        except (ApiError, ValueError):
            receipt.update(status='partial' if receipt['deleted'] else 'failed', failed=name)
            save(output, receipt)
            raise
    receipt['status'] = 'completed'
    save(output, receipt)
    return receipt


def main() -> None:
    """提供默认预览与明确应用入口。:return: None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference-evidence', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--plan-run')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    revision = os.environ.get('GITHUB_SHA', '')
    if (os.environ.get('GITHUB_REPOSITORY') != REPOSITORY or os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or os.environ.get('GITHUB_REF') != 'refs/heads/flower2api'
            or os.environ.get('GITHUB_WORKFLOW_REF') != REPOSITORY + '/' + WORKFLOW + '@refs/heads/flower2api'):
        raise ValueError('清理仅接受本仓flower2api受信手动入口')
    api = GitHubApi(os.environ.get('GH_TOKEN', ''))
    evidence = reference_evidence(args.reference_evidence)
    check_retirement(api, ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError('输出路径必须全新')
    if not args.apply:
        value = preview(api, revision, evidence)
        save(args.output, value)
        print(json.dumps({'status': 'previewed', 'sha256': digest(value), 'packages': list(TARGETS)}))
        return
    if not args.plan or not args.plan_run or not re.fullmatch(r'[0-9a-f]{64}', args.plan_sha256 or ''):
        raise ValueError('应用需要预览计划、运行及精确摘要')
    plan = json.loads(args.plan.read_text())
    if digest(plan) != args.plan_sha256:
        raise ValueError('预览计划摘要不符')
    validate_origin(api, plan, args.plan_run)
    result = apply(api, plan, args.output, revision, evidence)
    print(json.dumps({'status': result['status'], 'deleted': len(result['deleted'])}))


if __name__ == '__main__':
    main()
