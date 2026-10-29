"""用本地真实 HTTP/SSE 与 mitmdump 验证中断保留，不连接真实账号。"""
import hashlib
import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'orchestrator'))
from capture_artifacts import capture_summary


class Handler(BaseHTTPRequestHandler):
    """仅提供完整响应和可中断 SSE 的本地合成上游。"""

    started = threading.Event()
    finish_stream = threading.Event()

    def log_message(self, *args) -> None:
        """不输出请求内容。:param args: 原日志参数。:return: None。"""

    def do_POST(self) -> None:
        """返回合成响应或等待中断。:return: None。"""
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        if self.path.endswith('/complete'):
            body = b'{"usage":{"input_tokens":2,"output_tokens":3}}'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            self.wfile.write(b'event: message_start\ndata: {"type":"message_start"}\n\n')
            self.wfile.flush()
            self.started.set()
            self.finish_stream.wait(15)


def port() -> int:
    """申请本地临时端口。:return: 空闲端口。"""
    with socket.socket() as stream:
        stream.bind(('127.0.0.1', 0))
        return stream.getsockname()[1]


def wait_for(predicate, timeout: float = 12) -> None:
    """等待本地证据就绪。:param predicate: 条件。:param timeout: 截止秒数。:return: None。"""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError('本地验证条件未在期限内满足')
        time.sleep(0.05)


def verify() -> dict:
    """执行两代真实代理，检查完整流、中断流及旧文件哈希。:return: 可审计结果。"""
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    executable = Path(sys.executable).with_name('mitmdump')
    with tempfile.TemporaryDirectory(prefix='capture-stream-') as temporary:
        base = Path(temporary)
        origin = server.server_address[1]
        processes, clients = [], []
        try:
            for generation in (1, 2):
                directory = base / 'executions' / str(generation)
                directory.mkdir(parents=True)
                listener = port()
                environment = {**os.environ, 'PYTHONPATH': str(ROOT / 'orchestrator'),
                    'STATS_FILE': str(directory / 'stats.jsonl'), 'CAPTURE_FILE': str(directory / 'http_capture.jsonl'),
                    'CAPTURE_INDEX_FILE': str(directory / 'capture_index.json'), 'CAPTURE_FULL_HTTP': '1',
                    'CAPTURE_SCOPE': 'all', 'V3_ACCOUNT': '0', 'QUOTA_SOURCE': f'synthetic:{generation}'}
                with (directory / 'proxy.log').open('wb') as log:
                    process = subprocess.Popen([str(executable), '--listen-host', '127.0.0.1', '--listen-port', str(listener),
                        '-s', str(ROOT / 'images/sidecar/recorder.py'), '--save-stream-file', str(directory / 'capture.flow')],
                        env=environment, stdout=log, stderr=log)
                processes.append(process)

                def ready() -> bool:
                    if process.poll() is not None:
                        raise AssertionError((directory / 'proxy.log').read_text())
                    try:
                        with socket.create_connection(('127.0.0.1', listener), timeout=0.1):
                            return True
                    except OSError:
                        return False

                wait_for(ready)
                client = http.client.HTTPConnection('127.0.0.1', listener, timeout=15)
                clients.append(client)
                client.request('POST', f'http://127.0.0.1:{origin}/v1/complete', b'{}',
                    {'Host': 'api.anthropic.com', 'Content-Type': 'application/json'})
                response = client.getresponse()
                assert response.status == 200 and b'usage' in response.read()
                if generation == 1:
                    streaming = http.client.HTTPConnection('127.0.0.1', listener, timeout=15)
                    clients.append(streaming)
                    streaming.request('POST', f'http://127.0.0.1:{origin}/v1/stream', b'{}',
                        {'Host': 'api.anthropic.com', 'Content-Type': 'application/json'})
                    assert Handler.started.wait(5)
                    wait_for(lambda: (directory / 'capture_index.json').exists()
                        and len(json.loads((directory / 'capture_index.json').read_text())['entries']) == 2)
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=10)
                if generation == 1:
                    summary = capture_summary(base)
                    records = [json.loads(line) for line in (directory / 'http_capture.jsonl').read_text().splitlines()]
                    assert summary['status'] == 'partial', summary
                    assert {item['capture_state'] for item in summary['index']['entries']} == {'complete', 'interrupted'}
                    old = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}
                else:
                    assert old == {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (base / 'executions/1').iterdir()}
            summary = capture_summary(base)
            assert summary['sample_count'] == 3
            return {'result': 'passed', 'transport': '本地真实 HTTP/SSE + mitmdump 子进程',
                'samples': summary['sample_count'], 'interrupted_state': summary['status'],
                'interrupted_callback_states': [item['capture_state'] for item in records if item['request']['path'] == '/v1/stream'],
                'old_artifact_sha256': old, 'new_execution_preserves_old_files': True,
                'real_account_used': False, 'model_requests': 0}
        finally:
            Handler.finish_stream.set()
            for client in clients:
                client.close()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    result = verify()
    output = Path(__file__).with_name('capture-stream-evidence.json')
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))
