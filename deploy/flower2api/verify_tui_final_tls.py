"""用验证构建的真实网关、账号 sender 和私有回环网络验收 V2 TLS 快照。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from hashlib import sha256
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import select
import sqlite3
import socket
from statistics import median
from socketserver import (
    StreamRequestHandler,
    ThreadingTCPServer,
    ThreadingUnixStreamServer,
)
import ssl
import struct
import subprocess
import sys
import tempfile
from threading import Event, Thread
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / name)
    for name in (
        'services/orchestrator',
        'images/account',
        'services/gateway/tests/fixtures',
    )
]
from native_capture import read_capture
from tls_clienthello import parse_body
from tls_http import certificates
from tui_sender_launch import managed_model_response
from tui_source import _oauth_file
from tui_messages import ModelResponseError
from verify_tui_http_handoff import message_sse


def encoded(value):
    """生成验收用 JSON 字节。@param value 合成值。@return UTF-8 字节。"""
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def wait_for(operation):
    """等待异步文件或进程就绪。@param operation 尝试读取的函数。@return 首次成功值。"""
    end = time.monotonic() + 30
    while time.monotonic() < end:
        try:
            result = operation()
            if result:
                return result
        except (OSError, FileNotFoundError):
            pass
        time.sleep(0.05)
    raise AssertionError('等待合成现场就绪超时')


def call(port, method, path, secret, data=None):
    """请求隔离命名空间中的服务。@param port 本机端口。@param method 方法。@param path 路径。
    @param secret 合成凭据。@param data 可选 JSON。@return 状态及响应字节。
    """
    with closing(HTTPConnection('127.0.0.1', port, timeout=30)) as conn:
        conn.request(
            method,
            path,
            None if data is None else encoded(data),
            {
                'Authorization': 'Bearer ' + secret,
                'Content-Type': 'application/json',
                'anthropic-version': '2023-06-01',
            },
        )
        response = conn.getresponse()
        return response.status, response.read()


def serve(stack, server):
    """在后台运行回环服务。@param stack 生命周期。@param server 服务。@return 本机服务。"""
    server.daemon_threads = True
    stack.callback(server.server_close)
    stack.callback(server.shutdown)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def stop(process):
    """回收验收子进程。@param process 子进程。@return 无。"""
    process.terminate()
    process.wait(timeout=15)


def verify(folder, gateway, sender):
    """核对真实 TLS、私有文件与管理接口。@param folder 隔离目录。@param gateway 网关。
    @param sender 验证构建的发送器。@return 仅含合成数值的验收结果。
    """
    binding_secret, admin, internal = (uuid4().hex for _ in range(3))
    deployment, environment = 'tls-test', uuid4().hex
    host = 'flower2api-' + sha256(deployment.encode()).hexdigest()[:12] + '-' + environment
    binding = dict(
        account_id=1,
        environment_id=environment,
        generation=1,
        release_id='tls-test',
        endpoint='http://' + host + ':8091',
        secret=binding_secret,
    )
    records, hellos, source_errors = [], [], []
    submitted_hashes = {}
    file_mode = Event()
    file_mode.set()
    received_modes = []
    cancel_arrived, cancel_release = Event(), Event()
    root = folder / 'account'
    private = root / 'flows/api/cc-prepared'
    private.mkdir(parents=True)
    with (folder / 'hosts').open('a') as hosts:
        hosts.write('127.0.0.1 ' + host + '\n')

    class Upstream(StreamRequestHandler):
        """独立从 TLS 服务端读取 HTTP 实体，持久结果只保留摘要与计数。"""

        def handle(self):
            """处理同连接上的多个请求。@return 无。"""
            connection = uuid4().hex
            while request := self.rfile.readline():
                head = bytearray(request)
                fields = {}
                while line := self.rfile.readline():
                    head += line
                    if line == b'\r\n':
                        break
                    key, value = line.split(b':', 1)
                    fields[key.lower()] = value.strip()
                body = self.rfile.read(int(fields[b'content-length']))
                assert not any(name.startswith(b'x-v3-') for name in fields)
                records.append(
                    (
                        sha256(head + body).hexdigest(),
                        sha256(body).hexdigest(),
                        len(head) + len(body),
                        connection,
                    )
                )
                if b'fixture-cancel' in body:
                    cancel_arrived.set()
                    cancel_release.wait(10)
                reject = b'fixture-error-429' in body
                response = (
                    b'{"error":{"type":"rate_limit_error","message":"fixture"}}'
                    if reject
                    else message_sse(
                        {'type': 'text', 'text': 'fixture-ok'},
                        'end_turn',
                        'msg_fixture',
                    )
                )
                status, mime = (
                    ('429 Too Many Requests', 'application/json')
                    if reject
                    else ('200 OK', 'text/event-stream')
                )
                self.wfile.write(
                    f'HTTP/1.1 {status}\r\nContent-Type: {mime}\r\nContent-Length: {len(response)}\r\n\r\n'.encode()
                    + response
                )

    class Tunnel(StreamRequestHandler):
        """仅把预期目标的 CONNECT 隧道接至合成 HTTPS 服务。"""

        def handle(self):
            """双向传输回环数据。@return 无。"""
            assert self.rfile.readline().split()[:2] == [
                b'CONNECT',
                b'api.anthropic.com:443',
            ]
            while self.rfile.readline().strip():
                pass
            with socket.create_connection(upstream.server_address) as dest:
                self.wfile.write(b'HTTP/1.1 200 Connection established\r\n\r\n')
                peers = {self.connection: dest, dest: self.connection}
                while active := select.select(list(peers), [], [], 30)[0]:
                    for source in active:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        peers[source].sendall(chunk)

    class Registry(BaseHTTPRequestHandler):
        """以实际读取器提供绑定和已保存的尝试。"""

        def log_message(self, *_):
            """忽略访问日志。@return 无。"""

        def do_GET(self):
            """原样调用正式私有文件读取入口。@return 无。"""
            if self.headers.get('authorization') != 'Bearer ' + internal:
                return self.send_error(401)
            if self.path.split('?')[0] == '/internal/v3/transport/1':
                data = binding
            elif self.path.startswith('/internal/v3/native-captures/1/'):
                try:
                    data = read_capture(root, 1, self.path.rsplit('/', 1)[1])
                except FileNotFoundError:
                    return self.send_error(404)
            else:
                return self.send_error(404)
            raw = encoded(data)
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            """确认合成环境的配置租约。@return 无。"""
            if (
                self.path != '/internal/v3/quiesce/1'
                or self.headers.get('authorization') != 'Bearer ' + internal
            ):
                return self.send_error(404)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{}')

    class Source(StreamRequestHandler):
        """模拟 TUI 生命周期，实际模型请求调用正式受管适配器。"""

        def handle(self):
            """处理已绑定的单次预留。@return 无。"""
            try:
                self.turn()
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as error:
                source_errors.append(type(error).__name__)
                raise

        def turn(self):
            """完成私有握手和一次模型调用。@return 无。"""
            proof = json.loads(self.rfile.readline())
            action = proof.pop('action')

            def reply(**extra):
                self.wfile.write(encoded({**proof, 'ready': True, 'idle': True, **extra}) + b'\n')

            reply(
                managed_oauth_protocol=1,
                capture_http_protocol=1,
                input_policy_protocol=1,
                model_headers_protocol=1,
                body_policy_protocol=1,
                upstream_session_protocol=1,
                **({'oauth_file_protocol': 1} if file_mode.is_set() else {}),
            )
            if action != 'bind':
                return
            prepare = json.loads(self.rfile.readline())
            raw = self.rfile.read(prepare['body_len'])
            headers = json.loads(self.rfile.read(prepare.get('model_headers_len', 0)) or b'{}')
            file_selected = prepare.get('oauth_file_protocol') == 1
            reply(kind='new', **({'oauth_file_protocol': 1} if file_selected else {}))
            line = self.rfile.readline()
            if not line:
                return
            command = json.loads(line)
            if command['action'] != 'send':
                return
            if file_selected:
                assert 'account_token' not in command
                credential = _oauth_file(self.rfile, command['oauth_file_len'])
                assert credential['refresh_token'] == account_refresh
                bearer = credential['access_token']
            else:
                assert 'oauth_file_len' not in command
                bearer = command['account_token']
            assert bearer == account_token
            received_modes.append('file' if file_selected else 'legacy')
            submitted_hashes[prepare['reservation']['reservation_id']] = sha256(raw).hexdigest()
            if b'fixture-before-model' in raw:
                assert file_selected
                error_body = encoded({'error': {'type': 'api_error', 'message': 'fixture'}})
                self.wfile.write(
                    encoded(
                        {
                            'status': 503,
                            'content_type': 'application/json',
                            'message_id_mode': 'gateway',
                            'error_source': 'oauth_file_before_model',
                        }
                    )
                    + b'\n'
                )
                self.wfile.write(struct.pack('!I', len(error_body)) + error_body + b'\0\0\0\0')
                return
            try:
                with managed_model_response(
                    raw,
                    account_token=bearer,
                    reservation=prepare['reservation'],
                    headers=headers,
                ) as response:
                    result = response.read()
                status = 200
            except ModelResponseError as error:
                status, result = (
                    error.status,
                    encoded({'error': {'type': 'fixture_error', 'message': 'fixture'}}),
                )
            self.wfile.write(
                encoded(
                    {
                        'status': status,
                        'message_id_mode': 'gateway',
                        'content_type': 'text/event-stream' if status == 200 else 'application/json',
                        'error_source': 'managed_oauth_http',
                    }
                )
                + b'\n'
            )
            self.wfile.write(struct.pack('!I', len(result)) + result + b'\0\0\0\0')

    def setup_process(stack, binary, env, name):
        output = stack.enter_context((folder / (name + '.log')).open('ab'))
        process = subprocess.Popen(
            [str(binary)],
            cwd=folder,
            env={**os.environ, **env},
            stdout=output,
            stderr=output,
        )
        stack.callback(stop, process)
        return process

    def manage(method, path, data=None):
        code, raw = call(18090, method, '/admin/' + path, admin, data)
        assert code in (200, 201), (path, code, raw[:180])
        return json.loads(raw)

    with ExitStack() as stack:
        upstream = ThreadingTCPServer(('127.0.0.1', 0), Upstream)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(folder / 'leaf.pem', folder / 'leaf.key')
        ctx.set_alpn_protocols(['http/1.1'])

        def hello(conn, direction, version, content_type, kind, data):
            if direction == 'read' and int(content_type) == 22 and int(kind) == 1:
                parsed = parse_body(data[4:])
                hellos.append(
                    (
                        parsed['ja3']['string'],
                        parsed['alpn_protocols'],
                        parsed['supported_versions'],
                        parsed['signature_algorithms'],
                        parsed['key_share'],
                        parsed['sni'],
                        parsed['compression_methods'],
                        parsed['session_id_length'],
                        [(e['type'], e['length']) for e in parsed['extensions']],
                    )
                )

        ctx._msg_callback = hello
        upstream.socket = ctx.wrap_socket(upstream.socket, server_side=True)
        serve(stack, upstream)
        tunnel = serve(stack, ThreadingTCPServer(('127.0.0.1', 0), Tunnel))
        registry = serve(stack, ThreadingHTTPServer(('127.0.0.1', 0), Registry))
        proxy = 'http://127.0.0.1:' + str(tunnel.server_address[1])
        os.environ['V3_SENDER_CONFIG'] = '/run/v3/sender.json'
        Path('/run/v3/sender.json').write_bytes(
            encoded(
                dict(
                    binding=binding,
                    proxy_url=proxy,
                    allowed_origin='https://api.anthropic.com',
                    native_capture_dir=str(private),
                    tui_v2={'max_reservations': 12},
                )
            )
        )
        events = Path('/run/v3/tui-v2/events.sock')
        events.parent.mkdir(mode=0o700)
        serve(stack, ThreadingUnixStreamServer(str(events), Source))
        events.chmod(0o600)
        process = setup_process(stack, sender, {}, 'sender')
        gateway_process = setup_process(
            stack,
            gateway,
            dict(
                SERVER_HOST='127.0.0.1',
                SERVER_PORT='18090',
                DATABASE_DRIVER='sqlite',
                DATABASE_DSN=str(folder / 'gateway.db'),
                ADMIN_PASSWORD=admin,
                LOG_LEVEL='warn',
                V3_DEPLOYMENT_ID=deployment,
                V3_RELEASE='tls-test',
                V3_INTERNAL_TOKEN=internal,
                V3_RUNTIME_URL='http://127.0.0.1:' + str(registry.server_port),
            ),
            'gateway',
        )

        def gateway_ready():
            assert gateway_process.poll() is None, (
                '网关启动退出',
                gateway_process.returncode,
            )
            return call(18090, 'GET', '/admin/accounts', admin)[0] == 200

        wait_for(gateway_ready)
        manage(
            'PUT',
            'settings',
            {'allowed_user_agents': '', 'request_diagnostics_log_mode': 'info'},
        )
        account_token = 'fixture-' + uuid4().hex
        account_refresh = 'fixture-refresh-' + uuid4().hex
        manage(
            'POST',
            'accounts',
            dict(
                email='wire@fixture.test',
                request_backend='native293',
                auth_type='oauth',
                access_token=account_token,
                refresh_token=account_refresh,
                expires_at=time.time_ns() // 1_000_000 + 3_600_000,
                proxy_url=proxy,
                auto_telemetry=False,
                auto_poll_usage=False,
                concurrency=4,
                rpm_limit=0,
            ),
        )
        detail = manage('GET', 'accounts/1')
        manage(
            'PUT',
            'accounts/1',
            {
                'request_backend': 'tui_v2',
                'request_backend_revision': detail['request_backend_revision'],
            },
        )
        token = manage('POST', 'tokens', dict(name='wire', allowed_accounts='1'))['token']

        def post(text, stream=True):
            data = {
                'model': 'claude-sonnet-4-6',
                'max_tokens': 64,
                'stream': stream,
                'messages': [{'role': 'user', 'content': text}],
            }
            return call(18090, 'POST', '/v1/messages', token, data)[0]

        assert post('same') == 200
        assert not list(private.glob('*.json'))
        first_hello = hellos[0]
        process.terminate()
        process.wait(10)
        current = setup_process(stack, sender, {}, 'sender')
        wait_for(lambda: call(8091, 'GET', '/internal/status', binding_secret)[0] == 200)
        manage('PUT', 'settings', {'request_diagnostics_log_mode': 'debug'})
        assert post('same') == 200
        assert len(hellos) == 2 and first_hello == hellos[1]
        assert records[0][:3] == records[1][:3]
        assert post('same', False) == 200
        assert records[1][3] == records[2][3]
        assert received_modes == ['file', 'file', 'file']
        file_mode.clear()
        assert post('legacy-token') == 200 and received_modes[-1] == 'legacy'
        file_mode.set()
        before_failure = set(submitted_hashes)
        before_http = len(records)
        assert post('fixture-before-model') == 503 and len(records) == before_http
        (failure_id,) = set(submitted_hashes) - before_failure

        def failure_record():
            with closing(sqlite3.connect(folder / 'gateway.db')) as db:
                row = db.execute(
                    'SELECT request_id FROM request_diagnostic_attempts WHERE attempt_id=?',
                    (failure_id,),
                ).fetchone()
            if row:
                detail = manage('GET', 'request-diagnostics/' + row[0])
                if any(a.get('capture_status') == 'not_submitted' for a in detail['attempts']):
                    return row[0]
            return None

        failure_request = wait_for(failure_record)
        missing = manage('GET', 'request-diagnostics/' + failure_request + '/captures/' + failure_id)
        assert missing['state'] == 'missing' and '模型提交前' in missing['message']
        assert not (private / (failure_id + '.json')).exists()
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(post, ['parallel-one', 'parallel-two'])) == [200, 200]
        assert post(account_token + 'x' * (3 * 1024 * 1024)) == 200
        expected = list(records[1:])
        wait_for(lambda: len(list(private.glob('*.json'))) == len(expected))
        times = {'info': [], 'debug': []}
        for iteration in range(8):
            for mode in ('info', 'debug') if iteration % 2 == 0 else ('debug', 'info'):
                manage('PUT', 'settings', {'request_diagnostics_log_mode': mode})
                begin = time.perf_counter_ns()
                assert post('latency-sample') == 200
                times[mode].append((time.perf_counter_ns() - begin) / 1e6)
                if mode == 'debug':
                    expected.append(records[-1])
                    wait_for(lambda: len(list(private.glob('*.json'))) == len(expected))
        manage('PUT', 'settings', {'request_diagnostics_log_mode': 'debug'})

        # 下游断开时，上游仍未返回响应头；已被接受的完整写入须能独立落盘。
        with closing(HTTPConnection('127.0.0.1', 18090, timeout=10)) as pending:
            pending.request(
                'POST',
                '/v1/messages',
                encoded(
                    {
                        'model': 'claude-sonnet-4-6',
                        'max_tokens': 16,
                        'stream': True,
                        'messages': [{'role': 'user', 'content': 'fixture-cancel'}],
                    }
                ),
                {
                    'Authorization': 'Bearer ' + token,
                    'Content-Type': 'application/json',
                    'anthropic-version': '2023-06-01',
                },
            )
            assert cancel_arrived.wait(10)
        expected.append(records[-1])
        try:
            wait_for(lambda: len(list(private.glob('*.json'))) == len(expected))
        finally:
            cancel_release.set()
        # 只替换验证构建的测试 CA，捕获 TLS 握手失败且零 HTTP 写出的状态。
        current.terminate()
        current.wait(10)
        ca_file = Path('/run/v3/verification-ca.der')
        ca_file.write_bytes((folder / 'wrong/ca.der').read_bytes())
        failed = setup_process(stack, sender, {}, 'sender')
        wait_for(lambda: call(8091, 'GET', '/internal/status', binding_secret)[0] == 200)
        before = len(records)
        assert post('wrong-ca') >= 400 and len(records) == before
        wait_for(lambda: len(list(private.glob('*.json'))) == len(expected) + 1)
        failed.terminate()
        failed.wait(10)
        ca_file.write_bytes((folder / 'ca.der').read_bytes())
        setup_process(stack, sender, {}, 'sender')
        wait_for(lambda: call(8091, 'GET', '/internal/status', binding_secret)[0] == 200)
        assert post('fixture-error-429') == 429
        expected.append(records[-1])
        wait_for(lambda: len(list(private.glob('*.json'))) == len(expected) + 1)
        expected = sorted((http, body, size) for http, body, size, _ in expected)
        actual = []
        for path in private.glob('*.json'):
            snapshot = read_capture(root, 1, path.stem)

            def recorded_attempt():
                with closing(sqlite3.connect(folder / 'gateway.db')) as database:
                    return database.execute(
                        'SELECT request_id FROM request_diagnostic_attempts WHERE attempt_id=?',
                        (path.stem,),
                    ).fetchone()

            try:
                row = wait_for(recorded_attempt)
            except AssertionError as exc:
                raise AssertionError(
                    (
                        '缺少尝试记录',
                        'fixture-cancel' in snapshot['body'],
                        snapshot['wire_final']['reason'],
                    )
                ) from exc
            api = manage('GET', 'request-diagnostics/' + row[0] + '/captures/' + path.stem)
            assert api['snapshot'] == snapshot
            wire = snapshot['wire_final']
            assert wire['request_id'] == path.stem and wire['source'] == 'tui_sender_tls'
            saved = path.read_bytes()
            assert account_token.encode() not in saved and account_refresh.encode() not in saved
            assert snapshot['original_body_sha256'] == submitted_hashes[path.stem]
            if not wire['complete']:
                assert (
                    wire['status'] == 'unavailable'
                    and wire['reason'] == 'REQUEST_NOT_OBSERVED'
                    and wire['body_sha256'] is None
                )
                continue
            if wire['observed_body_bytes'] > 2 * 1024 * 1024:
                assert wire['body_truncated']
            assert wire['body_sha256'] == submitted_hashes[path.stem]
            actual.append((wire['http_sha256'], wire['body_sha256'], wire['observed_http_bytes']))
        assert sorted(actual) == expected and not source_errors
        from playwright.sync_api import sync_playwright, expect

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={'width': 1280, 'height': 960})
            page.add_init_script("localStorage.setItem('claude-code-gateway_auth'," + json.dumps(admin) + ')')
            page.goto('http://127.0.0.1:18090/requests')
            page.get_by_role('button', name='详情', exact=True).first.click()
            panel = page.locator('.request-workspace')
            panel.get_by_role('button', name='阶段证据', exact=True).first.click()
            panel.get_by_role('button', name='最终TLS写出', exact=True).click()
            expect(panel.locator('[data-native-wire-final]')).to_contain_text('账号发送器 TLS 写出证据')
            assert 'Bearer fixture-' not in panel.inner_text()
            browser.close()
        return {
            'requests': len(records),
            'complete': len(actual),
            'handshake_failed': 1,
            'cancelled_after_write': 1,
            'credential_modes': sorted(set(received_modes)),
            'failed_before_model': 1,
            'hello_same': True,
            'http_same': True,
            'reused': True,
            'timing_samples': len(times['debug']),
            'loopback_median_ms': {name: round(median(values), 2) for name, values in times.items()},
        }


def main():
    """创建仅有回环网络的独立测试空间。@return 打印脱敏的验证结果。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--gateway', type=Path, required=True)
    parser.add_argument('--sender', type=Path, required=True)
    parser.add_argument('--case', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.case:
        print(json.dumps(verify(args.case, args.gateway, args.sender), ensure_ascii=False))
        return
    with tempfile.TemporaryDirectory(prefix='flower-tui-tls-') as tmp:
        case = Path(tmp)
        (case / 'hosts').write_text('127.0.0.1 localhost\n')
        for name in ('native', 'v3'):
            (case / name).mkdir(mode=0o700)
        certificates(case)
        (case / 'wrong').mkdir()
        certificates(case / 'wrong')
        (case / 'v3/verification-ca.der').write_bytes((case / 'ca.der').read_bytes())
        env = {
            'PATH': os.environ['PATH'],
            'HOME': '/tmp',
            'PYTHONDONTWRITEBYTECODE': '1',
            'TOKIO_WORKER_THREADS': '2',
            'PLAYWRIGHT_BROWSERS_PATH': os.environ.get(
                'PLAYWRIGHT_BROWSERS_PATH', str(Path.home() / '.cache/ms-playwright')
            ),
        }
        mounts = []
        for directory in (
            '/usr',
            '/bin',
            '/lib',
            '/lib64',
            '/etc',
            str(ROOT),
            str(Path(sys.prefix)),
            str(args.gateway.resolve().parent),
            str(args.sender.resolve().parent),
            env['PLAYWRIGHT_BROWSERS_PATH'],
        ):
            mounts.extend(['--ro-bind', directory, directory])
        subprocess.run(
            [
                'bwrap',
                '--die-with-parent',
                '--unshare-net',
                '--dev',
                '/dev',
                '--proc',
                '/proc',
                '--tmpfs',
                '/tmp',
                *mounts,
                '--bind',
                tmp,
                tmp,
                '--bind',
                str(case / 'v3'),
                '/run/v3',
                '--bind',
                str(case / 'native'),
                '/native',
                '--ro-bind',
                str(case / 'hosts'),
                '/etc/hosts',
                '--chdir',
                tmp,
                sys.executable,
                str(Path(__file__).resolve()),
                '--case',
                tmp,
                '--gateway',
                str(args.gateway.resolve()),
                '--sender',
                str(args.sender.resolve()),
            ],
            env=env,
            check=True,
        )


if __name__ == '__main__':
    main()
