#!/usr/bin/env python3
"""在 Docker 回环中核验默认发行网关的 V2 公开请求、账号发送器动作与就绪诊断。"""
from __future__ import annotations

import argparse
import json
import os
from contextlib import ExitStack, closing
from hashlib import file_digest, sha256
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import BaseRequestHandler, ThreadingTCPServer
from sqlite3 import connect
from subprocess import Popen, run
from tempfile import mkdtemp
from threading import Thread
from time import monotonic, sleep
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4


from verify_tui_public_gateway import check_public_gateway
from verify_tui_prompt_cache import check_prompt_cache
from verify_tui_sender_actions import check_actions, check_restarted, wait_for, write_source_binding


DOCKER = ['docker', '--host', 'unix:///var/run/docker.sock']


def http(port: int, method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    """调用本地接口。@param port 回环端口。@param method 请求方法。@param path 路径。
    @param token 合成鉴权。@param body 可选对象。@return 状态码与 JSON 对象。
    """
    client = HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json',
                   'User-Agent': 'flower-tui-sender-status/1'}
        client.request(method, path, None if body is None else json.dumps(body), headers)
        response = client.getresponse()
        payload = response.read()
        return response.status, json.loads(payload) if payload.startswith(b'{') else {}
    finally:
        client.close()


def start_server(stack: ExitStack, server):
    """启动回环服务。@param stack 退出时停止服务。@param server 监听器。@return 原监听器。"""
    stack.enter_context(server)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stack.callback(thread.join)
    stack.callback(server.shutdown)
    return server


def probe(folder: Path, gateway: Path) -> None:
    """核验私有接口和实际 Gateway。@param folder 隔离状态与证据。@param gateway 默认发行二进制。@return 无。"""
    deployment = 'sender-status-fixture'
    environment = uuid4().hex
    host = 'flower2api-' + sha256(deployment.encode()).hexdigest()[:12] + '-' + environment
    internal, secret, admin = (uuid4().hex + uuid4().hex for _ in range(3))
    binding = {'account_id': 1, 'environment_id': environment, 'generation': 5,
               'endpoint': f'http://{host}:8091', 'secret': secret, 'release_id': 'local-test'}
    registered = None
    sleeping = False
    registry_queries = []
    upstream_connections = []
    rollback_predecessors = []
    native_requests = []
    native_route = f'/cluster-transports/v2/{sha256(deployment.encode()).hexdigest()[:12]}/{"b" * 32}/{environment}/1'

    class Registry(BaseHTTPRequestHandler):
        """按既有协议返回合成编排登记；发送器由实际账号二进制运行。"""

        def do_GET(self):
            """按实际编排协议区分读取现有绑定与唤醒。@return 无。"""
            nonlocal sleeping
            if self.path == native_route + '/internal/native/status':
                if self._native_authorized():
                    self._reply_json({'raw_input_protocol': 1, 'version': '2.1.293',
                        'environment_id': environment, 'generation': 174})
                return
            if self.headers.get('Authorization') != 'Bearer ' + internal:
                self.send_error(401)
                return
            registry_queries.append(self.path)
            target = urlsplit(self.path)
            query = parse_qs(target.query, keep_blank_values=True)
            rollback = query.get('tui_rollback_generation')
            if (target.path != '/internal/v3/transport/1'
                    or query.keys() - {'wake', 'tui_oauth_profile', 'tui_previous_release', 'tui_rollback_generation'}
                    or query.get('wake') not in (None, ['false'], ['true'])
                    or query.get('tui_oauth_profile') not in (None, ['false'])
                    or ('tui_previous_release' in query and (
                        query['tui_previous_release'] != ['true'] or query.get('wake') != ['false']))
                    or (rollback is not None and (len(rollback) != 1 or not rollback[0].isdigit()
                        or query.keys() != {'wake', 'tui_rollback_generation'} or query.get('wake') != ['false']))):
                self.send_error(404)
                return
            if rollback is not None:
                scope = {key: value for key, value in registered.items() if key != 'secret'} if registered else None
                payload = {'scope': scope, 'predecessors': rollback_predecessors, 'stopped': sleeping} if scope else None
            elif query.get('wake') == ['false']:
                payload = None if sleeping else registered
            else:
                sleeping = False
                payload = registered
            self._reply_json(payload)

        def do_POST(self):
            """核对配置切换的维护租约，仅在真实发送器空闲时放行。@return 无。"""
            nonlocal sleeping
            if self.path == native_route + '/internal/native/messages':
                if self._native_authorized():
                    submission = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                    native_requests.append((submission['request']['account_id'], submission['request']['generation']))
                    self._reply_json({'id': 'msg_fixture_v1', 'type': 'message', 'role': 'assistant',
                        'model': 'claude-sonnet-4-6', 'content': [{'type': 'text', 'text': '隔离回切后首轮 V1'}],
                        'stop_reason': 'end_turn', 'usage': {'input_tokens': 1, 'output_tokens': 1}})
                return
            if self.headers.get('Authorization') != 'Bearer ' + internal:
                self.send_error(401)
                return
            if self.path != '/internal/v3/quiesce/1':
                self.send_error(404)
                return
            lease = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert lease['owner'].startswith('gateway-config:') and lease['generation']
            code, state = control()
            idle = code == 200 and state['active'] == 0 and state['tui_v2']['idle'] is True
            if idle:
                # 正式编排在配置门禁下停止账号环境，后续只读发现应为空。
                sleeping = True
            self.send_response(200 if idle else 409)
            self.send_header('Content-Length', '0')
            self.end_headers()

        def _native_authorized(self):
            if (self.headers.get('x-v3-relay-token') == internal
                    and self.headers.get('Authorization') == 'Bearer ' + secret):
                return True
            self.send_error(401)
            return False

        def _reply_json(self, payload):
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    class Upstream(BaseRequestHandler):
        """统计任何意外访问合成代理或模型地址的 TCP 连接。"""

        def handle(self):
            """只计数并关闭连接。"""
            upstream_connections.append(1)

    def control(method='GET', path='/internal/status', token=secret):
        return http(8091, method, path, token, {} if method == 'POST' else None)

    def write_config(sender_binding, proxy, **extra):
        path = folder / 'sender/sender.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'binding': sender_binding, 'proxy_url': proxy,
                                         'allowed_origin': proxy, **extra}))
        temporary.chmod(0o640)
        temporary.replace(path)

    with ExitStack() as stack:
        registry = start_server(stack, ThreadingHTTPServer(('127.0.0.1', 0), Registry))
        upstream = start_server(stack, ThreadingTCPServer(('127.0.0.1', 0), Upstream))
        proxy = f'http://127.0.0.1:{upstream.server_address[1]}'
        limit = monotonic() + 10
        while True:
            try:
                assert control()[0] == 503
                break
            except ConnectionRefusedError:
                if monotonic() >= limit:
                    raise
                sleep(0.1)
        write_config({**binding, 'account_id': 0}, proxy)
        assert control()[1]['tui_v2']['reason'] == 'binding_unverified'
        write_config(binding, proxy)
        assert control(token='') == (401, {'error': 'unauthorized'})
        assert control(token=internal)[0] == 401
        code, sender = control()
        assert code == 200 and sender['active'] == 0
        assert sender['environment_id'] == environment and sender['generation'] == binding['generation']
        assert sender['tui_v2'] == {'protocol': 1, 'ready': False, 'idle': None,
                                    'account_id': 1, 'release_id': 'local-test',
                                    'reason': 'messages_tool_and_usage_events_unavailable'}
        assert secret not in json.dumps(sender)
        actions = check_actions(binding, secret, write_config, control, proxy)

        with Path('/etc/hosts').open('a') as hosts:
            hosts.write(f'\n127.0.0.1 {host}\n')
        # 正向切换走管理 API，随后在独立 SQLite 中重现已有 V2 选择而事件源缺失的历史状态。
        options = {'PATH': '/usr/bin:/bin:/usr/local/bin', 'HOME': '/tmp', 'SERVER_HOST': '127.0.0.1',
                   'SERVER_PORT': '18090', 'DATABASE_DRIVER': 'sqlite', 'DATABASE_DSN': str(folder / 'gateway.db'),
                   'ADMIN_PASSWORD': admin, 'LOG_LEVEL': 'warn', 'V3_DEPLOYMENT_ID': deployment,
                   'V3_RELEASE': 'local-test', 'V3_INTERNAL_TOKEN': internal,
                   'V3_RUNTIME_URL': f'http://127.0.0.1:{registry.server_port}'}

        def launch_gateway(resources, port=18090, database=None):
            log = resources.enter_context((folder / 'gateway.log').open('ab'))
            env = {**options, 'SERVER_PORT': str(port), 'DATABASE_DSN': str(database or folder / 'gateway.db')}
            process = Popen([str(gateway)], env=env, cwd=folder, stdout=log, stderr=log)

            def stop():
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)

            resources.callback(stop)
            limit = monotonic() + 20
            while monotonic() < limit and process.poll() is None:
                try:
                    if http(port, 'GET', '/admin/accounts', admin)[0] == 200:
                        return stop
                except OSError:
                    sleep(0.1)
            raise RuntimeError('默认 Gateway 启动失败，见 gateway.log')

        def admin_call(method, path, body):
            code, value = http(18090, method, '/admin/' + path, admin, body)
            assert code in (200, 201), (code, value)
            return value

        def set_runtime(generation, value):
            nonlocal registered, sleeping
            sleeping = value
            registered = {**binding, 'generation': generation}
            write_source_binding(registered)
            write_config(registered, proxy, tui_v2={'max_reservations': 3})

        def rollback_after_upgrades(account):
            """验证已有陈旧绑定和管理回切意向随后台自动应用。@param account 当前管理视图。@return 新视图。"""
            nonlocal registered, stop_gateway
            set_runtime(174, False)
            scope = {key: value for key, value in binding.items() if key != 'secret'}
            def encode(value):
                return json.dumps(value, separators=(',', ':')).encode()
            location = (scope['account_id'], environment, 'local-old', scope['endpoint'])
            location_digest = sha256(encode(location)).hexdigest()
            digest = sha256(encode((*location[:2], 168, *location[2:]))).hexdigest()
            # 隔离数据库载入旧发行已保存的绑定，实际网关与发送器使用当前发行。
            with closing(connect(folder / 'gateway.db')) as db, db:
                changed = db.execute("UPDATE tui_backend_intents SET binding=? WHERE account_id=1 AND revision=? AND target=''",
                    (f'v3:{environment}:168:{location_digest}:{digest}', account['request_backend_revision']))
                assert changed.rowcount == 1
            rollback_predecessors.append({**scope, 'generation': 172, 'release_id': 'local-previous'})
            try:
                pending = admin_call('PUT', 'accounts/1', {'request_backend': 'native293',
                    'request_backend_revision': account['request_backend_revision']})
                assert pending['request_backend'] == 'tui_v2' and pending['request_backend_pending'] == 'native293'
                assert pending['request_backend_wait_reason'] == 'runtime_unconfirmed'
                repeated = admin_call('PUT', 'accounts/1', {'request_backend': 'native293',
                    'request_backend_revision': pending['request_backend_revision']})
                assert repeated['request_backend_revision'] == pending['request_backend_revision']
                stop_gateway()
                stop_gateway = launch_gateway(initial)
                restarted = admin_call('GET', 'accounts/1', None)
                assert restarted['request_backend_pending'] == 'native293'
                assert restarted['request_backend_revision'] == pending['request_backend_revision']
                rollback_predecessors.append({**scope, 'generation': 171, 'release_id': 'local-old'})

                def applied():
                    state = admin_call('GET', 'accounts/1', None)
                    return state['request_backend'] == 'native293' and state['request_backend_pending'] is None

                wait_for(applied, '后台未应用跨代回切')
                observed = admin_call('GET', 'accounts/1', None)
                assert observed['request_backend_revision'] == pending['request_backend_revision'] + 1
                # 使用私有 V1 合成发送器确认普通客户端首轮走新路由，并只提交一次。
                registered = {**registered, 'endpoint': options['V3_RUNTIME_URL'] + native_route}
                status, message = http(18090, 'POST', '/v1/messages', token, {'model': 'claude-sonnet-4-6',
                    'stream': False, 'max_tokens': 8, 'messages': [{'role': 'user', 'content': '验证回切'}]})
                assert status == 200 and message['id'] == 'msg_fixture_v1', status
                assert native_requests == [(1, 174)]
                return observed
            finally:
                rollback_predecessors.clear()

        def compare_cache(token):
            primary, snapshot = folder/'gateway.db', folder/'cache-compare.db'
            with ExitStack() as peer:
                previous = admin_call('GET', 'settings', None)['v3_admission_wait_seconds']
                admin_call('PUT', 'settings', {'v3_admission_wait_seconds': '2'})
                peer.callback(admin_call, 'PUT', 'settings', {'v3_admission_wait_seconds': previous})
                # 两套相同账号状态分别运行同一段工具历史，避免跨实验触发已完成工具的防重放。
                with closing(connect(primary)) as source, closing(connect(snapshot)) as target:
                    source.backup(target)
                launch_gateway(peer, 18091, snapshot)
                return check_prompt_cache(token, [('raw', 18090, primary), ('gateway', 18091, snapshot)])

        with ExitStack() as initial:
            stop_gateway = launch_gateway(initial)
            admin_call('PUT', 'settings', {'allowed_user_agents': 'flower-tui-sender-status*'})
            account = admin_call('POST', 'accounts', {'email': 'sender@fixture.test',
                'request_backend': 'legacy', 'setup_token': 'synthetic-' + uuid4().hex, 'proxy_url': proxy,
                'auto_telemetry': False, 'auto_poll_usage': False, 'concurrency': 1, 'rpm_limit': 0})
            assert account['id'] == 1
            token = admin_call('POST', 'tokens', {'name': 'fixture', 'allowed_accounts': '1'})['token']
            missing_revision = http(18090, 'PUT', '/admin/accounts/1', admin, {'request_backend': 'tui_v2'})[0]
            assert missing_revision == 400
            original = admin_call('GET', 'accounts/1', None)
            assert original['tui_v2_available'] is False
            activation = http(18090, 'PUT', '/admin/accounts/1', admin, {'request_backend': 'tui_v2',
                              'request_backend_revision': original['request_backend_revision']})[0]
            assert activation == 503
            unchanged = admin_call('GET', 'accounts/1', None)
            assert unchanged['request_backend'] == 'legacy' and unchanged['request_backend_pending'] is None
            assert unchanged['request_backend_revision'] == original['request_backend_revision']
            registered = binding
            positive = check_public_gateway(binding, write_config, proxy, control, admin_call, http, token,
                                            folder / 'native/tui-v2-submissions.json', set_runtime, compare_cache,
                                            rollback_after_upgrades)
            write_source_binding(binding)
            registered = None
            sleeping = False
        with closing(connect(folder / 'gateway.db')) as db, db:
            assert db.execute("UPDATE accounts SET request_backend='tui_v2' WHERE id=1").rowcount == 1
        launch_gateway(stack)
        request = {'model': 'claude-sonnet-4-6', 'stream': True, 'max_tokens': 8,
                   'messages': [{'role': 'user', 'content': '仅回环不可用验证'}]}
        before_invalid = len(registry_queries)
        assert http(18090, 'POST', '/v1/messages', 'fixture-invalid', request)[0] == 401
        assert len(registry_queries) == before_invalid

        public = {}
        for label, registered, expected in (
            ('no_running_binding', None, 'NotRunning'),
            ('cross_account', {**binding, 'account_id': 2}, 'BindingUnverified'),
            ('wrong_bearer', {**binding, 'secret': internal}, 'BindingUnverified'),
            ('stale_generation', {**binding, 'generation': 4}, 'BindingUnverified'),
            ('no_tool_and_usage_events', binding, 'MessagesToolAndUsageEventsUnavailable'),
        ):
            log_path = folder / 'gateway.log'
            previous = log_path.stat().st_size
            code, error = http(18090, 'POST', '/v1/messages', token, request)
            assert code == 503 and error == {'type': 'error', 'error': {'type': 'api_error',
                'message': 'Service temporarily unavailable'}}, (label, code, error)
            diagnostic = log_path.read_bytes()[previous:].decode()
            assert '发送前拒绝 V2 请求' in diagnostic and expected in diagnostic, (label, diagnostic)
            public[label] = {'status': code, 'diagnostic': expected}
        assert registry_queries[before_invalid:] == [
            '/internal/v3/transport/1?wake=false&tui_oauth_profile=false'
        ] * len(public)
        assert control()[1]['active'] == 0 and not upstream_connections
        result = {'status': 'passed', 'sender': sender, 'private_missing_config': 503,
                  'private_invalid_bearer': 401, 'sender_actions': actions,
                  'public': public, 'public_ready': positive, 'public_invalid_bearer': 401,
                  'enable_without_revision': missing_revision, 'enable_without_source': activation,
                  'registry_queries': registry_queries, 'upstream_connections': len(upstream_connections)}
        (folder / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


def run_probe_container(sender: Path, gateway: Path, root: Path, config: Path, native: Path,
                        events: Path, image: str, flags: list[str]) -> None:
    """启动新发行进程，在同账号命名空间核验私有接口。
    @param sender 默认发送器。@param gateway 默认网关。@param root 证据目录。@param config 发送器配置。
    @param native 私有持久卷。@param events Unix socket 目录。@param image 本机账号镜像。
    @param flags 首次或重建阶段。@return 无。
    """
    with ExitStack() as stack:
        container = run([*DOCKER, 'run', '-d', '--rm', '--pull', 'never', '--network', 'none',
                         '--user', '1001:1001', '--read-only', '--cap-drop', 'ALL',
                         '--security-opt', 'no-new-privileges', '--entrypoint', '/usr/local/bin/account-sender',
                         '--mount', f'type=bind,src={sender},dst=/usr/local/bin/account-sender,readonly',
                         '--mount', f'type=bind,src={config},dst=/run/v3,readonly',
                         '--mount', f'type=bind,src={events},dst=/run/v3/tui-v2',
                         '--mount', f'type=bind,src={native},dst=/native', image],
                        check=True, capture_output=True, text=True).stdout.strip()
        stack.callback(run, [*DOCKER, 'rm', '-f', container], capture_output=True)
        network = run([*DOCKER, 'inspect', '--format', '{{.HostConfig.NetworkMode}}', container],
                      check=True, capture_output=True, text=True).stdout.strip()
        assert network == 'none'
        # 从实际 sender 容器验证：事件源 UID 能绑定私有 socket，配置父目录仍是只读。
        socket_check = (
            "import os,socket,stat\n"
            "from pathlib import Path\n"
            "parent=Path('/run/v3'); child=parent/'tui-v2'; path=child/'mount-check.sock'\n"
            "assert os.geteuid()==child.stat().st_uid==1001 and stat.S_IMODE(child.stat().st_mode)==0o700\n"
            "assert os.statvfs(parent).f_flag & os.ST_RDONLY and not os.statvfs(child).f_flag & os.ST_RDONLY\n"
            "with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:\n"
            "    sock.bind(str(path)); path.unlink()\n")
        run([*DOCKER, 'exec', container, 'python3', '-c', socket_check], check=True)
        run([*DOCKER, 'run', '--rm', '--pull', 'never', '--network', 'container:' + container,
             '--pid', 'container:' + container,
             '--user', '0:1001', '--entrypoint', 'python3',
             '--mount', f'type=bind,src={gateway},dst=/gateway,readonly',
             '--mount', f'type=bind,src={root},dst=/lab',
             '--mount', f'type=bind,src={Path(__file__).resolve()},dst=/verify.py,readonly',
             '--mount', f'type=bind,src={events},dst=/fixture',
             '--mount', f'type=bind,src={Path(__file__).with_name("verify_tui_sender_actions.py").resolve()},dst=/verify_tui_sender_actions.py,readonly',
             '--mount', f'type=bind,src={Path(__file__).with_name("verify_tui_public_gateway.py").resolve()},dst=/verify_tui_public_gateway.py,readonly',
             '--mount', f'type=bind,src={Path(__file__).with_name("verify_tui_prompt_cache.py").resolve()},dst=/verify_tui_prompt_cache.py,readonly',
             image, '/verify.py', '--probe', '/lab', '--gateway', '/gateway', *flags], check=True)


def main() -> int:
    """在现有账号镜像的隔离容器中运行发行制品。@return 验收退出状态。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sender', type=Path)
    parser.add_argument('--gateway', type=Path, required=True)
    parser.add_argument('--account-image')
    parser.add_argument('--probe', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--after-restart', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.probe:
        if args.after_restart:
            check_restarted(args.probe)
        else:
            probe(args.probe, args.gateway)
        return 0
    if not args.sender or not args.account_image:
        parser.error('需要默认发行 sender 和本机账号镜像')
    sender, gateway = (path.resolve(strict=True) for path in (args.sender, args.gateway))
    root = Path(mkdtemp(prefix='flower-tui-sender-status-'))
    print('证据目录', root, flush=True)
    config = root / 'sender'
    config.mkdir(mode=0o750)
    os.chown(config, 0, 1001)
    events = config / 'tui-v2'
    events.mkdir(mode=0o700)
    os.chown(events, 1001, 1001)
    native = root / 'native'
    native.mkdir(mode=0o700)
    os.chown(native, 1001, 1001)
    for flags in ([], ['--after-restart']):
        run_probe_container(sender, gateway, root, config, native, events, args.account_image, flags)

    result = json.loads((root / 'results.json').read_text())
    image = run([*DOCKER, 'image', 'inspect', '--format', '{{.Id}}', args.account_image],
                check=True, capture_output=True, text=True).stdout.strip()
    result.update({'account_image_id': image, 'network_mode': 'none'})
    for artifact in (sender, gateway):
        with artifact.open('rb') as file:
            result[artifact.name + '_sha256'] = file_digest(file, 'sha256').hexdigest()
    (root / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
