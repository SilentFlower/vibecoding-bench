#!/usr/bin/env python3
"""在无外网、有限 cgroup 的干净 Python 镜像中验证独立二进制。"""
import argparse
import base64
import concurrent.futures
import hashlib
import http.server
import json
import os
import select
import shutil
import socket
import socketserver
import ssl
import subprocess
import threading
import uuid
from pathlib import Path

IMAGE = 'python@sha256:6dd8b6dab6b3adc7812bab69eca5dbdc1a5cc690ad28306d234ffb4ef8ac9753'
LAUNCHER = '423a6a848c84e09bcc73a8b7be481ed4ead44a6644cef94bbf47d2009d3f6b80'
EXECUTABLE = '22f26d7803f80630968caf21b6170cf9bb94d87bea6f5eef678464f3bb0d3ecd'


def inside(launcher, executable):
    """仅在隔离容器中执行真实请求与满并发测量。@return 可审计的合成验证结果。"""
    assert shutil.which('bun') is None
    assert not Path('/root/project').exists()
    assert hashlib.sha256(Path('/opt/ccrb-runtime').read_bytes()).hexdigest() == launcher
    receipts, workers = [], []
    barriers = {count: threading.Barrier(count, timeout=60) for count in (3, 6)}

    class Upstream(http.server.BaseHTTPRequestHandler):
        """只接收本容器的合成 TLS Messages。"""
        def log_message(self, *_):
            """保持普通日志不包含正文。@return None。"""

        def do_POST(self):
            """记录独立 TLS 实收，所有同组请求就绪后才返回。@return None。"""
            raw = self.rfile.read(int(self.headers['content-length'])).decode()
            body = json.loads(raw)
            label = next(block['text'] for message in body['messages'] for block in
                         ([{'text': message['content']}] if isinstance(message['content'], str) else message['content'])
                         if block.get('text') in ('standalone-3', 'standalone-6'))
            assert self.path.startswith('/v1/messages')
            assert self.headers['authorization'] == 'Bearer synthetic-standalone'
            assert 'cf-ray' not in self.headers
            assert all(name not in body for name in ('settings', 'claude_settings', 'env'))
            receipts.append({'raw': raw, 'headers': dict(self.headers), 'label': label})
            barriers[int(label[-1])].wait()
            response = json.dumps({'id':'msg_offline','type':'message','role':'assistant','model':body['model'],
                'content':[{'type':'text','text':'独立二进制验证'}],'stop_reason':'end_turn','usage':{'input_tokens':1,'output_tokens':1}}).encode()
            self.send_response(200)
            self.send_header('content-type', 'application/json')
            self.send_header('content-length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    upstream = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain('/fixture/ca.pem', '/fixture/key.pem')
    upstream.socket = tls.wrap_socket(upstream.socket, server_side=True)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()

    class Proxy(socketserver.BaseRequestHandler):
        """限定唯一 Anthropic CONNECT 目标的本地代理。"""
        def handle(self):
            """保持 TLS 原始字节，禁止容器内请求其它目标。@return None。"""
            request = b''
            while not request.endswith(b'\r\n\r\n'):
                request += self.request.recv(1)
                assert len(request) < 8192
            assert request.startswith(b'CONNECT api.anthropic.com:443 ')
            with socket.create_connection(('127.0.0.1', upstream.server_port)) as target:
                self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                sockets = [self.request, target]
                while True:
                    ready, _, _ = select.select(sockets, [], [], 120)
                    if not ready:
                        return
                    for source in ready:
                        data = source.recv(65536)
                        if not data:
                            return
                        (target if source is self.request else self.request).sendall(data)

    proxy = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Proxy)
    proxy.daemon_threads = True
    threading.Thread(target=proxy.serve_forever, daemon=True).start()

    def start():
        """以私有 HOME 启动并核对实际执行体。@return 进程及 worker 标识。"""
        worker_id = str(uuid.uuid4())
        root = Path('/native') / worker_id
        for name in ('home', 'config', 'cwd'):
            (root / name).mkdir(parents=True, mode=0o700)
        (root / 'config/.claude.json').write_text(json.dumps({'userID':'a'*64}))
        environment = {'HOME':str(root/'home'),'CLAUDE_CONFIG_DIR':str(root/'config'),'PATH':'/usr/bin:/bin','LANG':'C.UTF-8',
            'CCRB_WORKER_ID':worker_id,'CCRB_CACHE_POLICY':'preserve','CCRB_TELEMETRY':'off',
            'CLAUDE_CODE_OAUTH_TOKEN':'synthetic-standalone','CLAUDE_CODE_ENTRYPOINT':'cli',
            'CLAUDE_CODE_GATEWAY_HINT_HEADERS':'1','CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC':'1',
            'DISABLE_AUTOUPDATER':'1','DISABLE_TELEMETRY':'1','DISABLE_ERROR_REPORTING':'1','DISABLE_AUTO_COMPACT':'1',
            'NODE_EXTRA_CA_CERTS':'/fixture/ca.pem','HTTPS_PROXY':f'http://127.0.0.1:{proxy.server_address[1]}'}
        process = subprocess.Popen(['/opt/ccrb-runtime','--version'], cwd=root/'cwd', env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        workers.append((process, worker_id))
        ready = json.loads(process.stdout.readline())
        assert ready['type'] == 'worker_ready' and ready.get('raw_input_protocol') == 1, ready
        assert ready['pid'] == process.pid and ready['version'] == '2.1.293'
        assert hashlib.sha256(Path(f'/proc/{process.pid}/exe').read_bytes()).hexdigest() == executable
        return process, worker_id

    def run(worker, count):
        """按唯一请求归属收齐响应、终态和 idle。@return 响应字节数。"""
        process, worker_id = worker
        request_id = str(uuid.uuid4())
        command = {'schema_version':2,'type':'request_input','worker_id':worker_id,'request_id':request_id,
            'input':{'schema_version':1,'request_id':request_id,'headers':[['cf-ray','synthetic']],
            'body':{'model':'claude-sonnet-4-6' if count == 3 else 'claude-haiku-4-5','max_tokens':64,'stream':False,
                    'settings':{'env':{'ANTHROPIC_BASE_URL':'https://untrusted.invalid'}},
                    'claude_settings':False,'env':{'PATH':'/untrusted'},
                    'messages':[{'role':'user','content':f'standalone-{count}'}]}}}
        process.stdin.write(json.dumps(command)+'\n')
        process.stdin.flush()
        terminal, body = False, b''
        while True:
            frame = json.loads(process.stdout.readline())
            assert frame['worker_id'] == worker_id and frame['request_id'] == request_id
            if frame['type'] == 'worker_idle':
                assert terminal and json.loads(body)['type'] == 'message'
                return len(body)
            payload = frame['payload']
            assert not terminal and payload.get('attempt') == 1
            assert payload['type'] != 'error'
            if payload['type'] == 'response_headers':
                assert payload['status'] == 200
            elif payload['type'] == 'response_chunk':
                body += base64.b64decode(payload['data_b64'], validate=True)
            elif payload['type'] == 'completed':
                assert payload['state'] == 'success'
                terminal = True

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            active = list(executor.map(lambda _: start(), range(3)))
            list(executor.map(lambda worker: run(worker, 3), active))
            active += list(executor.map(lambda _: start(), range(3)))
            list(executor.map(lambda worker: run(worker, 6), active))
        report = {'launcher_sha256':launcher,'executable_sha256':executable,'messages':receipts,
                  'cgroup':{name:Path('/sys/fs/cgroup',name).read_text().strip() for name in
                            ('memory.max','memory.peak','memory.events')},'source_available':False,'bun_available':False}
        assert len(receipts) == 9
        assert report['cgroup']['memory.max'] == str(2432*1024**2)
        Path('/output/standalone-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        for process, _ in workers:
            process.kill()
            process.wait(timeout=5)
        upstream.shutdown()
        proxy.shutdown()


def main():
    """创建合成证书并在固定镜像中执行受限验收。@return None。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--inside', action='store_true')
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--expected-launcher', default=LAUNCHER)
    parser.add_argument('--expected-executable', default=EXECUTABLE)
    args = parser.parse_args()
    for digest in (args.expected_launcher, args.expected_executable):
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            parser.error('预期 SHA256 必须为 64 位小写十六进制')
    if args.inside:
        inside(args.expected_launcher, args.expected_executable)
        return
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(output/'key.pem'),
                    '-out',str(output/'ca.pem'),'-days','1','-subj','/CN=api.anthropic.com',
                    '-addext','subjectAltName=DNS:api.anthropic.com'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.copyfile(Path(__file__), output/'check.py')
    output.chmod(0o755)
    (output/'key.pem').chmod(0o644)
    subprocess.run(['docker','run','--rm','--network','none','--memory','2432m','--memory-swap','2432m',
        '--pids-limit','128','--read-only','--tmpfs','/tmp:rw,nosuid,nodev,size=16m,mode=1777','--tmpfs','/native:rw,nosuid,nodev,size=128m,mode=700',
        '--mount',f'type=bind,src={args.binary.resolve()},dst=/opt/ccrb-runtime,readonly',
        '--mount',f'type=bind,src={output},dst=/fixture,readonly',
        '--mount',f'type=bind,src={output},dst=/output',IMAGE,'python','/fixture/check.py','--inside', '--expected-launcher', args.expected_launcher,
        '--expected-executable', args.expected_executable], check=True, timeout=240)
    print(json.loads((output/'standalone-report.json').read_text())['cgroup'])


if __name__ == '__main__':
    main()
