"""用合成接口验证真实环境页面；阻断所有实际网络和模型请求。"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import mimetypes
import re
import time
from pathlib import Path
from source_layout import source_path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
BASE = 'http://environment-ui.test'
OLD_SHA = 'a' * 64
NEW_SHA = 'b' * 64
ENVIRONMENT = '1' * 32


def sample_rows() -> list[dict]:
    """生成按现有公开字段组织的环境样例。@return 四种环境及单账号内核试点。"""
    row = {'environment_id': ENVIRONMENT, 'name': '演示环境 A', 'account_id': 1, 'generation': 10,
        'state': 'ready', 'busy': False, 'fingerprint': {'tz': 'America/Los_Angeles', 'mem': 'unlimited',
            'hostname': 'demo-machine', 'lang': 'en_US.UTF-8', 'profile_version': 1},
        'identity_status': '已确认 CLI 本地设备身份', 'cli_versions': ['2.1.293'],
        'role_status': {'cli': 'running', 'network': 'running', 'sender': 'running'},
        'can_reprofile': False, 'reprofile_message': '已有运行历史，保留原画像。',
        'run_window': {'timezone': 'America/Los_Angeles', 'server_now': time.time(),
            'message': '全天可运行', 'next_open_at': None, 'next_close_at': None,
            'config': {'enabled': False, 'days': [0, 1, 2, 3, 4], 'intervals': [{'start': '09:00', 'end': '18:00'}]}},
        'physical_features': {'message': '上次采集快照', 'observed_at': time.time(), 'fields': [
            {'key': 'ram_bytes', 'label': '容器 RAM 上限', 'configured': 0, 'observed': 0, 'status': 'match'},
            {'key': 'cpu', 'label': 'CPU 型号', 'configured': None, 'observed': None, 'status': 'unobserved'}]},
        'native_preparation': {'state': 'ready', 'idle_workers': 1, 'live_workers': 1,
            'pid': 27, 'checked_at_ms': int(time.time() * 1000)},
        'content_capture': {'enabled': True, 'applied': True, 'supported': True,
            'generation': 10, 'revision': 'a'*64,
            'tls_observer': {'state': 'ready', 'reason': None, 'protocol_version': 1}},
        'criu': {'schema_version': 1, 'enabled': True, 'platform_enabled': True, 'applied': True,
            'supported': True, 'installed': True, 'state': 'ready', 'reason': None, 'template_ready': True,
            'generation': 10, 'revision': 'c'*64, 'memory_mib': 0, 'required_memory_mib': 2056,
            'last_start_source': 'criu_restore'},
        'native_kernel': {'state': 'active', 'revision': '10:initial',
            'current': {'release': 'v0.1.0-beta.3', 'launcher_sha256': OLD_SHA},
            'prepared': {'release': 'v0.1.0-beta.4', 'launcher_sha256': NEW_SHA},
            'previous': {'release': 'v0.1.0-beta.4', 'launcher_sha256': NEW_SHA},
            'pid': 27, 'image_sha256': OLD_SHA, 'error': None}}
    rows = [row]
    for number, status in [(2, 'ready'), (3, 'stopped'), (4, 'future-state')]:
        other = copy.deepcopy(row)
        other.update(environment_id=str(number) * 32, name=f'演示环境 {number}', account_id=number,
            state=status, native_kernel=None, native_preparation=None)
        if status != 'ready':
            other['role_status'] = {'cli': 'exited', 'network': 'missing', 'sender': 'exited'}
        rows.append(other)
    return rows


class Fixture:
    """托管合成 API 与真实静态资源。所有浏览器请求都在本进程内完成。"""

    def __init__(self, gateway: Path) -> None:
        """初始化夹具。@param gateway 网关静态产物。@return None。"""
        self.gateway = gateway
        self.rows = sample_rows()
        self.writes: list[dict] = []
        self.sessions = 0
        self.reads = 0
        self.revision = 0
        self.criu_revision = 0
        self.fail_read = False
        self.fail_operation = False
        self.fail_releases = False
        self.release_reads = 0
        self.operation_gate: asyncio.Event | None = None
        self.operation_started = asyncio.Event()
        self.hold_next_read = False
        self.read_gate = asyncio.Event()
        self.read_started = asyncio.Event()
        self.unexpected: list[str] = []
        self.external: list[str] = []

    async def route(self, route) -> None:
        """在网络前拦截全部资源及接口。@param route 浏览器路由。@return None。"""
        request = route.request
        parsed = urlsplit(request.url)
        if parsed.netloc != 'environment-ui.test':
            # 字体及终端 CDN 在合成场景中不加载，页面按钮不会连接 OAuth 或模型。
            self.external.append(parsed.netloc)
            await route.fulfill(status=200, body='')
            return
        path = parsed.path
        payload: dict | list = {}
        status = 200
        if path == '/admin/dashboard':
            payload = {'accounts': {'total': 0, 'active': 0, 'error': 0, 'disabled': 0}, 'tokens': {'total': 0}}
        elif path == '/runtime/api/summary':
            payload = {'active_runs':0}
        elif path == '/runtime/api/system-updates/status':
            payload = {'installed':False}
        elif path == '/admin/runtime/session':
            assert request.method == 'POST'
            self.sessions += 1
            payload = {'ok': True}
        elif path == '/admin/settings':
            payload = {'request_diagnostics_log_mode': 'info'}
        elif path.startswith('/admin/request-diagnostics'):
            root = {'request_id': '11111111-1111-4111-8111-111111111111', 'started_at': '2026-11-12T00:00:00Z',
                'status_code': 200, 'account_id': 1, 'outcome': 'success', 'attempt_count': 2, 'log_mode': 'info'}
            if path == '/admin/request-diagnostics':
                payload = {'items': [root], 'total': 1, 'health': {}}
            else:
                attempt = {'attempt_id': '22222222-2222-4222-8222-222222222222', 'account_id': 1,
                    'ordinal': 1, 'profile_selection': 'native293_cc_prepared', 'status_code': 200,
                    'outcome': 'success', 'log_mode': 'info', 'capture_status': 'disabled'}
                legacy = dict(attempt, ordinal=2, attempt_id='33333333-3333-4333-8333-333333333333')
                attempt['runtime'] = {'worker_id': '44444444-4444-4444-8444-444444444444', 'worker_pid': 27,
                    'kernel_generation': None, 'warm_hit': True, 'preparation_wait_ms': 0, 'checkout_ms': 1,
                    'worker_start_ms': None, 'prepared_ms': 185}
                payload = {'request': root, 'attempts': [attempt, legacy]}
        elif '/api/' in path:
            api = path.split('/api/', 1)[1]
            if request.method != 'GET':
                body = json.loads(request.post_data or '{}')
                self.writes.append({'path': path, 'body': body})
                if api.endswith('/criu'):
                    current = self.rows[0]['criu']
                    assert type(body['enabled']) is bool
                    assert body['expected_generation'] == current['generation'] and body['expected_revision'] == current['revision']
                    self.criu_revision += 1
                    current.update(enabled=body['enabled'], revision=str(self.criu_revision)*64,
                        state='preparing' if body['enabled'] else 'disabled', reason=None, template_ready=False)
                    payload = copy.deepcopy(current)
                elif api.endswith('/content-capture'):
                    current = self.rows[0]['content_capture']
                    if body['expected_generation'] != current['generation'] or body['expected_revision'] != current['revision']:
                        status, payload = 409, {'detail': '采集配置已变化，请重新读取'}
                    else:
                        self.revision += 1
                        current.update(enabled=body['enabled'], revision=str(self.revision)*64,
                            tls_observer={'state': 'preparing' if body['enabled'] else 'disabled', 'reason': None})
                        payload = copy.deepcopy(current)
                elif api.endswith('/native-kernel'):
                    kernel = self.rows[0]['native_kernel']
                    self.operation_started.set()
                    if self.operation_gate:
                        await self.operation_gate.wait()
                    if self.fail_operation or body['expected_revision'] != kernel['revision']:
                        status, payload = 409, {'detail': '内核状态已变更，请刷新后重新操作'}
                    else:
                        self.revision += 1
                        kernel['revision'] = f'10:revision-{self.revision}'
                        if body['operation'] in ('activate', 'rollback'):
                            target = kernel['prepared'] if body['operation'] == 'activate' else kernel['previous']
                            kernel['previous'], kernel['current'] = kernel['current'], target
                        kernel['state'] = 'active'
                        payload = copy.deepcopy(kernel)
                elif api.endswith('/native-preparation'):
                    self.rows[0]['native_preparation'] = {'state': 'preparing', 'checking': True, 'reason': 'backend_pending'}
                    payload = {'queued': True}
                elif api.endswith('/physical-features/refresh') or api.endswith('/maintenance'):
                    payload = {'ok': True}
                elif api.endswith('/run-window') and request.method == 'PUT':
                    self.rows[0]['run_window']['config'] = body
                    payload = self.rows[0]['run_window']
                else:
                    self.unexpected.append(request.method + ' ' + path)
                    status, payload = 400, {'detail': '夹具拒绝额外写入'}
            elif api == 'environments':
                self.reads += 1
                payload = copy.deepcopy(self.rows)
                if self.hold_next_read:
                    self.hold_next_read = False
                    self.read_started.set()
                    await self.read_gate.wait()
                if self.fail_read:
                    status, payload = 503, {'detail': '合成读取故障'}
            elif api.endswith('/native-kernel/releases'):
                self.release_reads += 1
                payload = {'state': 'stale' if self.fail_releases else 'ready',
                    'reason': 'release_rate_limited' if self.fail_releases else None, 'latest': 'v0.1.0-beta.4',
                    'versions': [{'release': 'v0.1.0-beta.4'}, {'release': 'v0.1.0-beta.3'}]}
            elif api.endswith('/criu'):
                payload = copy.deepcopy(self.rows[0]['criu'])
            elif api.endswith('/content-capture'):
                payload = copy.deepcopy(self.rows[0]['content_capture'])
            elif api.endswith('/run-window'):
                payload = self.rows[0]['run_window']
            elif api in ('accounts', 'accounts/login-drafts', 'topics', 'task-batches'):
                payload = []
            elif api == 'auth/me':
                payload = {'user': '合成验证', 'authenticated': True}
            else:
                self.unexpected.append(request.method + ' ' + path)
                status, payload = 404, {'detail': '未定义的合成接口'}
        else:
            if path.startswith('/runtime/'):
                filename = path.removeprefix('/runtime/') or 'index.html'
                directory = source_path(ROOT, 'webui')
            elif path in ('/', '/environments', '/tasks', '/requests', '/updates'):
                directory, filename = self.gateway, 'index.html'
            else:
                directory, filename = self.gateway, path.lstrip('/')
            resource = (directory / filename).resolve()
            assert resource.is_relative_to(directory.resolve()) and resource.is_file(), str(resource)
            await route.fulfill(path=str(resource), content_type=mimetypes.guess_type(resource)[0] or 'application/octet-stream')
            return
        await route.fulfill(status=status, content_type='application/json', body=json.dumps(payload))


async def run(output: Path, gateway: Path) -> dict:
    """通过原生路由执行资源事务与完整状态矩阵。@param output 证据目录。@param gateway 网关构建。@return 合并报告。"""
    from verify_native_environments import run as verify_core
    from verify_native_environment_edges import run as verify_edges
    core = await verify_core(output, gateway)
    edges = await verify_edges(output, gateway)
    return {'passed': core['passed'] and edges['passed'], 'scenes': core['checks'] + edges['checks'],
        'errors': core['errors'] + edges['errors'], 'real_model_requests': 0}


def main() -> None:
    """解析本地证据路径并执行验收。@return None。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.deploy/environment-ui-verification')
    parser.add_argument('--gateway-dist', type=Path, default=source_path(ROOT, 'cc2api/web/dist'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    assert (args.gateway_dist / 'index.html').is_file(), '先在 cc2api/web 执行 npm run build 准备主后台静态产物'
    result = asyncio.run(run(args.output.resolve(), args.gateway_dist.resolve()))
    (args.output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
