"""在隔离容器中验证正式账号创建、后台补热和实际模型热命中。"""
import argparse
import hashlib
import json
import os
import signal
import sqlite3
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from verify_agy_native_loopback import Binding, ENVIRONMENT, MODEL, Proxy, SECRET, SOURCE_SHA, Upstream, require


class PreparationBinding(Binding):
    """使用合成编排准入，业务仍由真实发送器和原版 AGY 执行。"""

    capacity_limited = True
    registrations = []
    preparations = []

    def do_POST(self):
        """提供合成 OAuth 确认、环境登记及当前运行绑定。@return 无。"""
        route = urlsplit(self.path)
        if route.path not in ('/internal/v3/agy-auth/verify', '/internal/v3/agy-environments/1'):
            return super().do_POST()
        require(self.headers.get('authorization') == 'Bearer ' + SECRET, '后台登记服务证明错误')
        if route.path.endswith('/verify'):
            body = json.loads(self.rfile.read(int(self.headers['content-length'])))
            require(body['document']['token']['access_token'] == 'synthetic-at-1', '合成凭据不匹配')
            value = {'email_address': 'synthetic@example.test', 'capabilities': {'model_mappings': Upstream.model_mappings}}
        else:
            account, _ = _request('/admin/runtime/accounts/1/config')
            require(account['platform'] == 'antigravity' and account['credential_state']['phase'] == 'ready', '登记发生在账号提交之前')
            value = {'environment_id': ENVIRONMENT, 'generation': 1}
            if route.query == 'prepare=false':
                self.registrations.append(account['account_id'])
                value['state'] = 'registered'
            elif self.capacity_limited:
                self.preparations.append(route.query)
                value.update(state='unprepared', reason='waiting_capacity')
            else:
                self.preparations.append(route.query)
                value.update(state='bound', binding={'account_id': 1, 'environment_id': ENVIRONMENT, 'generation': 1,
                    'endpoint': f'http://{_sender_host()}:8091', 'secret': SECRET, 'release_id': 'synthetic-release'})
        raw = json.dumps(value).encode()
        self.send_response(200)
        self.send_header('content-length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _sender_host():
    return f"flower2api-{hashlib.sha256(b'synthetic').hexdigest()[:12]}-{ENVIRONMENT}"


def _request(path, body=None, *, method=None, token='synthetic-admin', sender=False, status=200):
    port, headers = (8091, {'authorization': f'Bearer {SECRET}'}) if sender else (5674, {'x-api-key': token})
    headers['content-type'] = 'application/json'
    request = Request(f'http://127.0.0.1:{port}{path}',
        data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        response = urlopen(request, timeout=30)
    except HTTPError as error:
        response = error
    with response:
        require(response.status == status, f'{path} 返回 {response.status}，预期 {status}')
        return json.load(response), response.headers


def _wait(check, message, seconds=45):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        try:
            value = check()
            if value:
                return value
        except OSError:
            pass
        time.sleep(.15)
    raise ValueError(message)


def _sender_state():
    return _request('/internal/status', sender=True)[0]


def _wait_hot(previous=None):
    def current_pid():
        sender = _sender_state()
        runtime = sender['agy']
        pid = runtime.get('idle_pid')
        if sender['active'] != 0 or pid is None or pid == previous:
            return None
        require(runtime['idle_workers'] == runtime['allocated_workers'] == runtime['workers'] == 1, '单名额实际池不符')
        os.kill(pid, 0)
        return pid
    return _wait(current_pid, '未观测到空闲的真实 AGY PID', seconds=90)


def _spawn(name):
    executable = f'/opt/{name}'
    loader = '/opt/verify-lib/ld-linux-x86-64.so.2'
    command = [loader, '--library-path', '/opt/verify-lib', executable] if Path(loader).is_file() else [executable]
    with Path(f'/state/{name}.log').open('ab') as output:
        return subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)


def inside():
    """启动隔离服务并核对连续补位。@return 脱敏验证结果。"""
    os.umask(0o077)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('/state/server.crt', '/state/server.key')
    proxy = ThreadingHTTPServer(('127.0.0.1', 19090), Proxy)
    proxy.context = context
    binding = ThreadingHTTPServer(('127.0.0.1', 8765), PreparationBinding)
    for server in (proxy, binding):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    Path('/state/sender.json').write_text(json.dumps({
        'binding': {'account_id': 1, 'environment_id': ENVIRONMENT, 'generation': 1,
            'endpoint': 'http://localhost:8091', 'secret': SECRET, 'release_id': 'synthetic-release'},
        'proxy_url': 'http://127.0.0.1:19090', 'allowed_origin': 'https://cloudcode-pa.googleapis.com',
        'native_capture_dir': '/state/capture',
        'agy': {'protocol_version': 1, 'source_sha256': SOURCE_SHA, 'module_root': '/opt/orchestrator',
            'binary_path': '/usr/local/bin/agy-1.5.9', 'work_root': '/state/native', 'max_workers': 1, 'memory_mib': 768}}))
    sender, gateway = _spawn('sender'), _spawn('gateway')
    try:
        _wait(lambda: _request('/api/hello')[0], '网关未就绪')
        _request('/admin/settings', {'request_diagnostics_log_mode': 'debug'}, method='PUT')
        account, _ = _request('/admin/accounts', {'name': '合成新账号', 'email': 'synthetic@example.test',
            'platform': 'antigravity', 'auth_type': 'oauth', 'access_token': 'synthetic-at-1',
            'refresh_token': 'synthetic-rt', 'expires_at': 4070908800000, 'concurrency': 1,
            'proxy_url': 'http://127.0.0.1:19090', 'auto_poll_usage': False}, status=201)
        require(account['id'] == 1 and PreparationBinding.registrations == [1], '正式保存尚未确认唯一环境登记')
        try:
            _wait(lambda: any(row.get('reason') == 'waiting_capacity' for row in _request('/admin/native-preparations')[0]),
                '后台容量等待未显示')
        except ValueError:
            print(json.dumps({'preparations': PreparationBinding.preparations,
                'snapshots': _request('/admin/native-preparations')[0]}, ensure_ascii=False))
            raise
        require(_sender_state()['agy']['workers'] == 0, '容量不足时出现实际进程')
        PreparationBinding.capacity_limited = False
        initial = _wait_hot()
        require(not Upstream.calls, '首次预热提交了模型')
        token, _ = _request('/admin/tokens', {'name': '合成调用方', 'allowed_accounts': '1'}, status=201)
        result, headers = _request(f'/v1beta/models/{MODEL}:generateContent',
            {'contents': [{'role': 'user', 'parts': [{'text': '合成热命中验证'}]}]}, token=token['token'])
        require(result['usageMetadata']['totalTokenCount'] == 7 and len(Upstream.calls) == 1, '首次模型提交次数或响应不符')
        diagnostic = '/admin/request-diagnostics/' + headers['x-cc2api-request-id']
        detail = _wait(lambda: (_request(diagnostic)[0]['attempts'] or None), '缺少业务请求进程证据')
        observed = detail[0]['runtime']
        require(observed['warm_hit'] is True and observed['worker_pid'] == initial, '首次业务未使用后台预热进程')

        require(_wait_hot() == initial, '首轮正常收口后热进程发生变化')
        os.kill(initial, signal.SIGKILL)
        refilled = _wait_hot(initial)
        with sqlite3.connect('/state/gateway.sqlite') as database:
            database.execute("UPDATE accounts SET access_token='synthetic-at-2' WHERE id=1")
            database.execute('UPDATE account_credential_states SET generation=2 WHERE account_id=1')
        rotated = _wait_hot(refilled)
        require(_sender_state()['agy']['idle_identity'][0]['credential_generation'] == 2, '换代后未使用当前凭据代次')
        sender.terminate()
        require(sender.wait(20) == 0 and any(Path('/state/native').glob('*/state/stopped.json')), '空闲发送器未完成真实关停')
        sender = _spawn('sender')
        restarted = _wait_hot(rotated)
        require(len(Upstream.calls) == 1, '退出补位、凭据换代或发送器重启提交了模型')
        gateway.terminate()
        gateway.wait(10)
        PreparationBinding.preparations.clear()
        gateway = _spawn('gateway')
        # 启动扫描应早于 20 秒定时巡检，已有账号重新走幂等登记。
        _wait(lambda: 'prepare=true' in PreparationBinding.preparations, '启动扫描未处理已有 AGY 账号', seconds=15)
        require(_wait_hot() == restarted, '网关重启导致当前发送器重复建进程')
        return {'registered_before_response': True, 'capacity_waited': True, 'warm_hit': True,
            'startup_scan': True, 'native_pids': [initial, refilled, rotated, restarted], 'upstream_model_submissions': 1}
    finally:
        for process in (sender, gateway):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    """在无网络容器中执行固定原版验证。@return 无。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--image')
    parser.add_argument('--loader-root', type=Path)
    parser.add_argument('--inside', action='store_true')
    args = parser.parse_args()
    if args.inside:
        print(json.dumps(inside(), ensure_ascii=False))
        return
    require(args.image, '需要明确的隔离验证镜像')
    import docker

    root = Path(__file__).resolve().parents[2]
    source = root / 'services/orchestrator'
    with tempfile.TemporaryDirectory(prefix='agy-prewarm-') as temporary:
        state = Path(temporary)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
            '-subj', '/CN=AGY prewarm fixture', '-addext', 'subjectAltName=DNS:*.googleapis.com',
            '-keyout', str(state / 'server.key'), '-out', str(state / 'server.crt')],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (state / 'trust.pem').write_bytes(Path('/etc/ssl/certs/ca-certificates.crt').read_bytes() + (state / 'server.crt').read_bytes())
        (state / 'capture').mkdir(mode=0o700)
        for path in (state, *state.iterdir()):
            os.chown(path, 1001, 1001)
        binaries = root / 'services/gateway/target/debug'
        volumes = {
            str(binaries / 'claude-code-gateway'): {'bind': '/opt/gateway', 'mode': 'ro'},
            str(binaries / 'account-sender'): {'bind': '/opt/sender', 'mode': 'ro'},
            str(Path(__file__).resolve().parent): {'bind': '/opt/probes', 'mode': 'ro'},
            str(source / 'agy_runtime'): {'bind': '/opt/orchestrator/agy_runtime', 'mode': 'ro'},
            str(source / 'runtime_files.py'): {'bind': '/usr/local/bin/runtime_files.py', 'mode': 'ro'},
            str(state): {'bind': '/state', 'mode': 'rw'},
            str(state / 'capture'): {'bind': '/flows', 'mode': 'rw'},
            str(state / 'trust.pem'): {'bind': '/etc/ssl/certs/ca-certificates.crt', 'mode': 'ro'},
        }
        if args.loader_root:
            for name in ('ld-linux-x86-64.so.2', 'libc.so.6', 'libm.so.6', 'libgcc_s.so.1'):
                volumes[str((args.loader_root / name).resolve(strict=True))] = {'bind': '/opt/verify-lib/' + name, 'mode': 'ro'}
        environment = {'PYTHONPATH': '/opt/orchestrator:/usr/local/bin', 'DATABASE_DRIVER': 'sqlite',
            'DATABASE_DSN': '/state/gateway.sqlite', 'ADMIN_PASSWORD': 'synthetic-admin', 'V3_SENDER_CONFIG': '/state/sender.json',
            'V3_RUNTIME_URL': 'http://127.0.0.1:8765', 'V3_INTERNAL_TOKEN': SECRET, 'V3_DEPLOYMENT_ID': 'synthetic',
            'V3_RELEASE': 'synthetic-release', 'LOG_LEVEL': 'warn', 'TOKIO_WORKER_THREADS': '2'}
        client = docker.from_env(timeout=60)
        container = client.containers.run(args.image, ['/opt/probes/verify_agy_prewarm.py', '--inside'],
            entrypoint=['python3'], detach=True, user='1001:1001', network_mode='none', read_only=True,
            cap_drop=['ALL'], security_opt=['no-new-privileges:true'], mem_limit='768m', pids_limit=512,
            tmpfs={'/tmp': 'rw,nosuid,nodev,size=128m'}, extra_hosts={_sender_host(): '127.0.0.1'},
            volumes=volumes, environment=environment, labels={'vibebench.test-task': 'agy-default-environment-prewarm'})
        try:
            result = container.wait(timeout=480)
            logs = container.logs().decode(errors='replace')
            if result['StatusCode'] != 0:
                for name in ('gateway', 'sender'):
                    path = state / f'{name}.log'
                    if path.is_file():
                        print(path.read_text()[-2500:])
                raise ValueError(logs)
            print(logs.strip())
        finally:
            container.remove(force=True)
            client.close()


if __name__ == '__main__':
    main()
