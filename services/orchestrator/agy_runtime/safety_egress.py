"""在原生模型请求发出前补齐同一作业的 Gemini 安全阈值。"""
import gzip
import hmac
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
import secrets
import subprocess
import threading
import time
from urllib.parse import urlsplit
import zlib

from .wire_capture import WireTrace, read_chunks


# 发送器固定使用 consumer 凭据。目录查询与模型请求共享原生选用的 daily 端点。
CLOUD_CODE = 'https://daily-cloudcode-pa.googleapis.com'
MODEL_PATH = '/v1internal:streamGenerateContent?alt=sse'
CONTROL_PATHS = frozenset('/v1internal:' + method for method in (
    'loadCodeAssist', 'fetchAdminControls', 'fetchAvailableModels', 'fetchUserInfo',
    'retrieveUserQuotaSummary', 'listExperiments', 'writeTrajectoryAcls'))
BODY_LIMIT = 64 * 1024 * 1024
HEADER_NAMES = ('Content-Type', 'Content-Encoding', 'Transfer-Encoding', 'User-Agent', 'Accept',
                'Accept-Encoding', 'Expect', 'X-Goog-Api-Client', 'X-Goog-Request-Params')
CURL_DEFAULT_HEADERS = ('Accept', 'Content-Type', 'Expect', 'User-Agent')


class _Pipe:
    def __init__(self, file):
        self.file = file

    def makefile(self, mode):
        return self.file


class _Request(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def setup(self):
        self.request.settimeout(10)
        super().setup()

    def log_message(self, *_args):
        # 路径含当前作业的随机标识，正文和认证头也不进入访问日志。
        return

    def _body(self):
        lengths = self.headers.get_all('Content-Length', [])
        transfer = self.headers.get_all('Transfer-Encoding', [])
        if not lengths and [value.lower() for value in transfer] == ['chunked']:
            raw = read_chunks(self.rfile, BODY_LIMIT)
        elif len(lengths) == 1 and not transfer:
            size = int(lengths[0])
            if not 0 <= size <= BODY_LIMIT:
                raise ValueError('native_post_size')
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError('native_post_incomplete')
        else:
            raise ValueError('native_post_framing')
        return raw

    def do_POST(self):
        """校验作业绑定，再发送一次模型请求或原生控制请求。@return 无。"""
        self.close_connection = True
        scope = self.server.scope
        auth = self.headers.get_all('Authorization', [])
        if not self.path.startswith(scope.prefix + '/') or len(auth) != 1 or not hmac.compare_digest(
                auth[0].encode('latin1'), scope.authorization):
            self.send_error(403)
            return
        path = self.path[len(scope.prefix):]
        if path != MODEL_PATH and path not in CONTROL_PATHS:
            self.send_error(404)
            return
        try:
            raw = self._body()
            if path == MODEL_PATH:
                codec = self.headers.get('Content-Encoding', 'identity').lower()
                if codec == 'gzip':
                    with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
                        raw = stream.read(BODY_LIMIT + 1)
                if codec not in ('identity', 'gzip') or len(raw) > BODY_LIMIT:
                    raise ValueError('native_post_encoding')
                body = json.loads(raw)
                if not isinstance(body, dict) or not isinstance(body.get('request'), dict):
                    raise ValueError('native_gemini_envelope')
                body['request']['safetySettings'] = scope.rules
                raw = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()
                if len(raw) > BODY_LIMIT:
                    raise ValueError('native_gemini_size')
                if codec == 'gzip':
                    raw = gzip.compress(raw, mtime=0)
            headers = [f'Authorization: {auth[0]}']
            for name in HEADER_NAMES:
                value = self.headers.get(name)
                if value and all(32 <= ord(char) <= 126 for char in value):
                    headers.append(f'{name}: {value}')
        except (OSError, EOFError, ValueError, zlib.error):
            self.send_error(400)
            return
        with scope.lock:
            allowed = not scope.closed and not (path == MODEL_PATH and scope.model_started)
            if allowed and path == MODEL_PATH:
                # 在发送前取得唯一许可，上游结果不明确时也保持已领取状态。
                scope.model_started = True
        if not allowed:
            self.send_error(409)
            return
        self._forward(scope, path, headers, raw)

    def _forward(self, scope, path, headers, raw):
        sent = False
        process = None
        trace = WireTrace(path) if path == MODEL_PATH and scope.capture else None
        try:
            process = scope.open_request(path, headers, raw, trace)
            response = http.client.HTTPResponse(_Pipe(process.stdout), method='POST')
            with response:
                response.begin()
                # 原生收到响应后可能立即结束作业，先关联实际模型状态。
                if path == MODEL_PATH:
                    scope.model_status = response.status
                if trace is not None:
                    trace.status = response.status
                self.send_response_only(response.status)
                for name in ('Content-Type', 'Content-Encoding', 'Retry-After', 'X-Request-Id'):
                    if value := response.getheader(name):
                        self.send_header(name, value)
                self.send_header('Connection', 'close')
                chunked = response.status not in (204, 304)
                if chunked:
                    self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                sent = True
                if chunked:
                    while chunk := response.read1(64 * 1024):
                        self.wfile.write(f'{len(chunk):x}\r\n'.encode())
                        self.wfile.write(chunk)
                        self.wfile.write(b'\r\n')
                    # 上游截断时保留未收口的帧，让原生读取器观察到传输失败。
                    if process.wait() == 0 and response.length in (None, 0):
                        self.wfile.write(b'0\r\n\r\n')
        except (OSError, ValueError, http.client.HTTPException):
            if not sent:
                self.send_error(502)
        finally:
            if process is not None:
                scope.finish_request(process)
            if trace is not None:
                if getattr(trace, 'thread', None) is not None:
                    trace.thread.join(1)
                    if trace.thread.is_alive():
                        trace = None
                if trace is not None:
                    scope.capture(trace, raw, list(self.headers.items()), headers)


class SafetyEgress:
    """持有一次原生作业的回环入口和活动上游连接。"""

    def __init__(self, rules, token, proxy, ca_file=None, capture=None, *, execution_deadline=None):
        """冻结阈值及租约。@param rules 客户端安全规则。@param token 当前代次访问令牌。@param proxy 账号代理。@param ca_file 受信证书路径。@param capture 采集回调。@param execution_deadline 原单调截止。@return 无。"""
        parsed = urlsplit(proxy)
        if parsed.scheme not in ('http', 'socks5', 'socks5h') or not parsed.hostname or not parsed.port:
            raise ValueError('native_safety_proxy_missing')
        self.rules = rules
        self.capture = capture
        self.deadline = time.monotonic() + 120 if execution_deadline is None else execution_deadline
        self.authorization = ('Bearer ' + token).encode('ascii')
        self.proxy = proxy
        self.ca_file = ca_file
        self.prefix = '/' + secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.closed = False
        self.model_started = False
        self.model_status = None
        self.processes = set()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), _Request)
        self.server.scope = self
        self.url = f'http://127.0.0.1:{self.server.server_port}{self.prefix}'
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
        self.thread.start()

    def open_request(self, path, headers, raw, trace=None):
        """通过原账号代理发起固定目标请求。@param path 受信动作。@param headers 筛过的原生头。@param raw 调整后的正文。@param trace 可选出站采集。@return 持有响应字节的进程。"""
        # 匿名文件让凭据、代理口令和消息都不进入参数、环境变量或磁盘。
        with os.fdopen(os.memfd_create('agy-gemini-input', os.MFD_CLOEXEC), 'wb') as body:
            body.write(raw)
            body.flush()
            body.seek(0)
            fd = body.fileno()
            supplied = {header.split(':', 1)[0].lower() for header in headers}
            # 只保留原生提供的头。空值让 curl 关闭自己的默认头和大正文 Expect 握手。
            suppressed = [name + ':' for name in CURL_DEFAULT_HEADERS if name.lower() not in supplied]
            lines = [f'proxy = {json.dumps(self.proxy, ensure_ascii=False)}',
                     *(f'header = {json.dumps(header, ensure_ascii=False)}' for header in (*headers, *suppressed))]
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise OSError('request_deadline_exceeded')
            command = ['curl', '-q', '--config', '-', '--silent', '--http1.1', '--raw', '--include',
                       '--no-buffer', '--suppress-connect-headers', '--noproxy', '', '--max-time', f'{max(.001, remaining):.3f}',
                       '--proxy-header', 'Proxy-Connection:', '--proxy-header', 'User-Agent: Go-http-client/1.1',
                       '--data-binary', f'@/proc/self/fd/{fd}', '--url', CLOUD_CODE + path]
            if self.ca_file:
                command.extend(('--cacert', self.ca_file))
            if trace is not None:
                command.extend(('--trace', '/dev/stderr'))
            with self.lock:
                if self.closed:
                    raise OSError('native_safety_scope_closed')
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE if trace is not None else subprocess.DEVNULL, pass_fds=(fd,),
                                           env={'PATH': '/usr/local/bin:/usr/bin:/bin'})
                self.processes.add(process)
            if trace is not None:
                trace.thread = threading.Thread(target=trace.read, args=(process.stderr,), daemon=True)
                trace.thread.start()
            try:
                with process.stdin:
                    process.stdin.write(('\n'.join(lines) + '\n').encode())
            except OSError:
                self.finish_request(process)
                raise
            return process

    def finish_request(self, process):
        """释放已完成或断开的连接。@param process 当前出站进程。@return 无。"""
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        with self.lock:
            self.processes.discard(process)

    def close(self):
        """撤销当前作业监听和未收口的连接。@return 无。"""
        with self.lock:
            if self.closed:
                return
            self.closed = True
            for process in self.processes:
                if process.poll() is None:
                    process.kill()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
