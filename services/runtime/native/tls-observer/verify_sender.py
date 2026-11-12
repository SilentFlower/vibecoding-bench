"""容器验证专用sender替身；真实原生执行体只访问合成TLS回环。"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from queue import Queue
import select
import socket
from socketserver import BaseRequestHandler, ThreadingTCPServer
import ssl
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

RESULTS = {}
HELLOS = []
LOCK = threading.Lock()
ROOT = Path(tempfile.mkdtemp(prefix='tls-gate-'))


class Upstream(BaseHTTPRequestHandler):
    """独立接收真实HTTP字节，返回固定合成结果。"""

    def log_message(self, *args):
        """禁止将原文写入普通日志。@param args 默认访问日志。@return None。"""

    def parse_request(self):
        """保留接收器原始头。@return HTTP解析结果。"""
        original = self.rfile
        parts = []

        class Reader:
            """只读记录原头行。"""

            def readline(self, *args):
                """记录接收行。@param args 原读取参数。@return 原始字节。"""
                data = original.readline(*args)
                parts.append(data)
                return data

        self.rfile = Reader()
        try:
            result = super().parse_request()
        finally:
            self.rfile = original
        self.raw_head = self.raw_requestline + b''.join(parts)
        return result

    def do_POST(self):
        """记录独立实收摘要。@return None。"""
        body = self.rfile.read(int(self.headers['Content-Length']))
        with LOCK:
            RESULTS[self.headers['x-client-request-id']] = (self.raw_head, body)
        reply = b'{"id":"msg_synthetic","type":"message","role":"assistant","model":"claude-sonnet-4-6","content":[{"type":"text","text":"ok"}],"stop_reason":"end_turn","usage":{"input_tokens":1,"output_tokens":1}}'
        self.send_response(200)
        self.send_header('content-type', 'application/json')
        self.send_header('content-length', str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)


class Proxy(BaseRequestHandler):
    """只允许固定Anthropic目标并转入本地合成TLS。"""

    def handle(self):
        """连接仅在本容器回环。@return None。"""
        data = b''
        while not data.endswith(b'\r\n\r\n'):
            chunk = self.request.recv(1)
            if not chunk or len(data) >= 8192:
                return
            data += chunk
        assert data.startswith(b'CONNECT api.anthropic.com:443 ')
        with socket.create_connection(('127.0.0.1', SERVER.server_port)) as other:
            self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            hello = b''
            captured = False
            while True:
                ready, _, _ = select.select([self.request, other], [], [], 30)
                if not ready:
                    return
                for current in ready:
                    chunk = current.recv(65536)
                    if not chunk:
                        return
                    if current is self.request and not captured:
                        hello += chunk
                        if len(hello) >= 5 and len(hello) >= 5 + int.from_bytes(hello[3:5], 'big'):
                            captured = True
                            with LOCK:
                                HELLOS.append(hello[5:5 + int.from_bytes(hello[3:5], 'big')])
                    (other if current is self.request else self.request).sendall(chunk)


def protocol_projection(hello: bytes) -> tuple:
    """保留握手协议特征，排除随机和临时密钥。@param hello 原始握手。@return 协议投影。"""
    body = hello[4:]
    position = 34
    position += 1 + body[position]
    length = int.from_bytes(body[position:position + 2], 'big')
    ciphers = body[position + 2:position + 2 + length]
    position += 2 + length
    length = body[position]
    compression = body[position + 1:position + 1 + length]
    position += 1 + length
    total = int.from_bytes(body[position:position + 2], 'big')
    position += 2
    end = position + total
    extensions = []
    while position < end:
        kind = int.from_bytes(body[position:position + 2], 'big')
        length = int.from_bytes(body[position + 2:position + 4], 'big')
        data = body[position + 4:position + 4 + length]
        if kind == 51:
            cursor, shares = 2, []
            while cursor < len(data):
                group = int.from_bytes(data[cursor:cursor + 2], 'big')
                size = int.from_bytes(data[cursor + 2:cursor + 4], 'big')
                shares.append((group, size))
                cursor += 4 + size
            data = repr(shares).encode()
        extensions.append((kind, data))
        position += 4 + length
    assert position == end
    return body[:2], ciphers, compression, tuple(extensions)


def execute(size: int, enabled: bool, cancel_first: bool = False) -> dict:
    """执行一次真实原生业务。@param size 合成文本字节。@param enabled 旁路开关。@param cancel_first 首次预备后关闭并复验回收。@return 安全回执。"""
    directory = Path(tempfile.mkdtemp(dir=ROOT))
    (directory / 'home').mkdir()
    (directory / 'config').mkdir()
    (directory / 'config/.claude.json').write_text(json.dumps({'userID': 'a'*64}))
    worker_id, request_id, capture_id = (str(uuid4()) for _ in range(3))
    environment = {'HOME': str(directory / 'home'), 'CLAUDE_CONFIG_DIR': str(directory / 'config'),
        'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'CCRB_WORKER_ID': worker_id,
        'CCRB_CACHE_POLICY': 'preserve', 'CCRB_TELEMETRY': 'off', 'CLAUDE_CODE_OAUTH_TOKEN': 'synthetic-tls-observer',
        'CLAUDE_CODE_ENTRYPOINT': 'cli', 'CLAUDE_CODE_GATEWAY_HINT_HEADERS': '1', 'DISABLE_AUTOUPDATER': '1',
        'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'DISABLE_TELEMETRY': '1', 'DISABLE_ERROR_REPORTING': '1',
        'DISABLE_AUTO_COMPACT': '1', 'NODE_EXTRA_CA_CERTS': str(ROOT / 'cert.pem'),
        'HTTPS_PROXY': f'http://127.0.0.1:{PROXY.server_address[1]}'}
    observer = None
    with subprocess.Popen(['/usr/local/bin/ccrb-runtime', '--version'], cwd=directory, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) as worker:
        try:
            assert select.select([worker.stdout], [], [], 40)[0]
            assert json.loads(worker.stdout.readline())['type'] == 'worker_ready'
            worker_status = Path(f'/proc/{worker.pid}/status').read_text()
            for name in ('CapEff', 'CapPrm', 'CapInh', 'CapAmb'):
                assert name + ':\t0000000000000000' in worker_status
            assert 'NoNewPrivs:\t1' in worker_status
            if enabled:
                arguments = ['/usr/local/bin/python3', '/opt/ccrb-tls-observer/client.py',
                    '--pid', str(worker.pid), '--image', 'af4cea9e21aa959c5e39c389173ba30ebb19b354b67acfe99164946450e9776d',
                    '--worker', worker_id, '--capture', capture_id]
                observer = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                assert select.select([observer.stdout], [], [], 2)[0]
                assert json.loads(observer.stdout.readline()).get('ready') is True
                if cancel_first:
                    retired = []
                    for path in Path('/proc').glob('[0-9]*/cmdline'):
                        try:
                            command = path.read_bytes().split(b'\0')
                            if b'/opt/ccrb-tls-observer/observer.py' in command and capture_id.encode() in command:
                                retired.append(path.parent)
                                status = dict(line.split(':', 1) for line in (path.parent/'status').read_text().splitlines() if ':' in line)
                                retired.append(Path('/proc')/status['PPid'].strip())
                        except FileNotFoundError:
                            pass
                    assert len(retired) == 2
                    observer.kill()
                    observer.wait(timeout=5)
                    deadline = time.monotonic() + 2
                    while any(path.exists() for path in retired) and time.monotonic() < deadline:
                        time.sleep(.01)
                    assert not any(path.exists() for path in retired)
                    capture_id = str(uuid4())
                    arguments[-1] = capture_id
                    observer = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
                    assert select.select([observer.stdout], [], [], 2)[0]
                    assert json.loads(observer.stdout.readline()).get('ready') is True
            body = {'model': 'claude-sonnet-4-6', 'max_tokens': 64, 'stream': False,
                'system': [{'type': 'text', 'text': 'x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=00000;'}],
                'metadata': {'user_id': json.dumps({'device_id': 'c'*64, 'account_uuid': '44444444-4444-4444-8444-444444444444', 'session_id': '22222222-2222-4222-8222-222222222222'})},
                'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'x'*min(size - index, 384*1024)} for index in range(0, size, 384*1024)]}]}
            worker.stdin.write(json.dumps({'type': 'request_input', 'schema_version': 2, 'worker_id': worker_id,
                'request_id': request_id, 'input': {'schema_version': 1, 'request_id': request_id, 'body': body}}) + '\n')
            worker.stdin.flush()
            frames = Queue()

            def read_frames():
                """按完整行入队，避免stdio预读与select产生假超时。@return None。"""
                for line in worker.stdout:
                    frames.put(line)

            threading.Thread(target=read_frames, daemon=True).start()
            client = None
            while True:
                frame = json.loads(frames.get(timeout=40))
                if frame['type'] == 'request_event':
                    payload = frame['payload']
                    assert payload['type'] != 'error', payload.get('code')
                    if payload['type'] == 'cc_prepared':
                        client = next(value for name, value in payload['headers'] if name.lower() == 'x-client-request-id')
                if frame['type'] == 'worker_idle':
                    break
            assert client in RESULTS
            head, actual = RESULTS[client]
            result = {'bytes': len(actual), 'sha256': hashlib.sha256(actual).hexdigest(), 'capture': enabled}
            if observer:
                observer.stdin.write(json.dumps({'capture_id': capture_id, 'client_request_id': client}) + '\n')
                observer.stdin.flush()
                assert select.select([observer.stdout], [], [], 2)[0]
                evidence = json.loads(observer.stdout.readline())
                assert evidence['complete'], evidence.get('reason')
                assert evidence['body_sha256'] == result['sha256']
                assert evidence['observed_body_bytes'] == len(actual)
                assert evidence['http_sha256'] == hashlib.sha256(head + actual).hexdigest()
                assert actual.startswith(evidence['body'].encode())
                result['write_counts'] = evidence['write_counts']
            return result
        finally:
            if observer:
                observer.kill()
                observer.wait(timeout=5)
            worker.kill()
            worker.wait(timeout=5)


def main() -> None:
    """覆盖两种容量、六进程并发和握手对照。@return None。"""
    global SERVER, PROXY
    status = Path('/proc/self/status').read_text()
    assert os.getuid() == 1001 and 'CapEff:\t0000000000000000' in status and 'NoNewPrivs:\t1' in status
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(ROOT/'key.pem'),
        '-out', str(ROOT/'cert.pem'), '-days', '1', '-subj', '/CN=api.anthropic.com',
        '-addext', 'subjectAltName=DNS:api.anthropic.com'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    SERVER = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ROOT/'cert.pem', ROOT/'key.pem')
    SERVER.socket = context.wrap_socket(SERVER.socket, server_side=True)
    PROXY = ThreadingTCPServer(('127.0.0.1', 0), Proxy)
    PROXY.daemon_threads = True
    for server in (SERVER, PROXY):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        small = execute(512*1024, True, cancel_first=True)
        large = execute(4608*1024, True)
        execute(512*1024, False)
        assert protocol_projection(HELLOS[0]) == protocol_projection(HELLOS[2])
        with ThreadPoolExecutor(max_workers=6) as executor:
            parallel = list(executor.map(lambda _: execute(32768, True), range(6)))
        assert len(RESULTS) == 9
        print(json.dumps({'small': small, 'large': large, 'parallel_complete': len(parallel),
            'handshake_projection_equal': True, 'model_requests': 0}), flush=True)
    finally:
        SERVER.shutdown()
        PROXY.shutdown()


if __name__ == '__main__':
    main()
