"""独立 OpenSSL 上游与公开 ClientHello 观测，仅允许回环隔离测试。"""

import base64
import hashlib
import json
import os
import select
import socket
import socketserver
import ssl
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(sys.argv[1])
assert os.readlink('/proc/self/ns/net') != os.readlink('/proc/1/ns/net')
assert [line.split(':')[0].strip() for line in Path('/proc/net/dev').read_text().splitlines()[2:] if ':' in line] == ['lo']
ROOT.mkdir(parents=True, exist_ok=True)
ROOT.joinpath('leaf.ext').write_text('basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:api.anthropic.com,DNS:fixture.local\n')
for args in [
    ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'ca.key', '-out', 'ca.pem', '-days', '1', '-subj', '/CN=CCRB synthetic upstream', '-addext', 'basicConstraints=critical,CA:TRUE'],
    ['req', '-newkey', 'rsa:2048', '-nodes', '-keyout', 'leaf.key', '-out', 'leaf.csr', '-subj', '/CN=api.anthropic.com'],
    ['x509', '-req', '-in', 'leaf.csr', '-CA', 'ca.pem', '-CAkey', 'ca.key', '-CAcreateserial', '-out', 'leaf.pem', '-days', '1', '-extfile', 'leaf.ext'],
]:
    subprocess.run(['openssl', *args], cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

LOCK = threading.Lock()
CALLS = []
HELLOS = []
CONNECTIONS = {}
SERVERS = []
TARGETS = []
CONNECT_HEADS = []


def connection_id(connection):
    """为实际 TLS 对象分配稳定编号。:param connection: SSL 对象。:return: 单调编号。"""
    with LOCK:
        if connection not in CONNECTIONS:
            CONNECTIONS[connection] = len(CONNECTIONS) + 1
        return CONNECTIONS[connection]


def numbers(data):
    """读取 16 位公开字段数组。:param data: 字节。:return: 有序整数。"""
    assert len(data) % 2 == 0
    return [int.from_bytes(data[index:index + 2], 'big') for index in range(0, len(data), 2)]


def client_hello(data):
    """逐字段解析 ClientHello，仅排除随机数、会话随机 ID 和实际公钥。:param data: 握手字节。:return: 公开字段。"""
    position = 4
    version = int.from_bytes(data[position:position + 2], 'big')
    position += 34
    session_length = data[position]
    position += 1 + session_length
    length = int.from_bytes(data[position:position + 2], 'big')
    ciphers = numbers(data[position + 2:position + 2 + length])
    position += 2 + length
    compression_length = data[position]
    compression = list(data[position + 1:position + 1 + compression_length])
    position += 1 + compression_length
    extension_length = int.from_bytes(data[position:position + 2], 'big')
    position += 2
    assert position + extension_length == len(data)
    extensions = []
    while position < len(data):
        kind = int.from_bytes(data[position:position + 2], 'big')
        size = int.from_bytes(data[position + 2:position + 4], 'big')
        payload = data[position + 4:position + 4 + size]
        assert len(payload) == size
        if kind == 51:
            shares, cursor = [], 2
            assert int.from_bytes(payload[:2], 'big') == len(payload) - 2
            while cursor < len(payload):
                group, key_length = numbers(payload[cursor:cursor + 4])
                shares.append([group, key_length])
                cursor += 4 + key_length
            assert cursor == len(payload)
            value = shares
        else:
            value = payload.hex()
        extensions.append([kind, value])
        position += 4 + size
    return {'legacyVersion': version, 'sessionIdLength': session_length, 'ciphers': ciphers, 'compression': compression, 'extensions': extensions}


class Reader:
    """在 HTTP 解析器实际读取时保留原字节。"""
    def __init__(self, source):
        """绑定读取器。:param source: 原流。:return: None。"""
        self.source, self.raw = source, bytearray()

    def readline(self, size=-1):
        """记录请求行和头。:param size: 上限。:return: 原字节。"""
        value = self.source.readline(size)
        self.raw.extend(value)
        return value

    def read(self, size=-1):
        """记录实体。:param size: 长度。:return: 原字节。"""
        value = self.source.read(size)
        self.raw.extend(value)
        return value

    def __getattr__(self, name):
        """委托文件属性。:param name: 属性名。:return: 原属性。"""
        return getattr(self.source, name)


class Handler(BaseHTTPRequestHandler):
    """返回合成 Messages 响应并保存实收字节。"""
    protocol_version = 'HTTP/1.1'

    def setup(self):
        """安装实际读取观测。:return: None。"""
        super().setup()
        self.rfile = Reader(self.rfile)

    def do_POST(self):
        """单次合成业务请求，不访问外部。:return: None。"""
        with LOCK:
            chosen = self.server.response_mode
        raw_body = self.rfile.read(min(65536, int(self.headers['content-length'])) if chosen == 'partial' else int(self.headers['content-length']))
        body = {} if chosen == 'partial' else json.loads(raw_body)
        raw = bytes(self.rfile.raw)
        self.rfile.raw.clear()
        with LOCK:
            index = len(CALLS)
            path = ROOT / ('request-' + str(index) + '.json')
            path.write_text(json.dumps({'body': raw_body.decode(), 'head': base64.b64encode(raw[:-len(raw_body)]).decode(), 'headers': list(self.headers.raw_items())}, ensure_ascii=False))
            CALLS.append({'index': index, 'file': str(path), 'connection': connection_id_unlocked(self.connection), 'rawBytes': len(raw), 'rawSha256': hashlib.sha256(raw).hexdigest(), 'bodyBytes': len(raw_body), 'bodySha256': hashlib.sha256(raw_body).hexdigest(), 'tls': self.connection.version(), 'alpn': self.connection.selected_alpn_protocol(), 'resumed': self.connection.session_reused})
        if chosen == 'partial':
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        tools = body.get('tools', [])
        tool_names = [tool.get('name') for tool in tools]
        results = any(block.get('type') == 'tool_result' for message in body.get('messages', []) if isinstance(message.get('content'), list) for block in message['content'])
        blocks = [{'type': 'text', 'text': '离线真实 CC 回环完成'}]
        if body.get('max_tokens') == 8192 or '</block>' in body.get('stop_sequences', []):
            blocks = [{'type': 'text', 'text': '<block>no</block>'}]
        elif 'SubagentHandback' in tool_names:
            blocks = [{'type': 'tool_use', 'id': 'toolu_fixture_handback', 'name': 'SubagentHandback', 'input': {'message': '离线子代理完成'}}]
        elif 'Agent' in tool_names and not results:
            blocks = [{'type': 'tool_use', 'id': 'toolu_fixture_agent_' + str(index) + '_' + str(child), 'name': 'Agent', 'input': {'description': '隔离子代理 ' + str(child), 'prompt': '只回复离线测试完成，然后交回报告。', 'subagent_type': 'Explore'}} for child in range(3)]
        message = {'id': 'msg_fixture_' + str(index), 'type': 'message', 'role': 'assistant', 'model': body['model'], 'content': blocks, 'stop_reason': 'tool_use' if blocks[0]['type'] == 'tool_use' else 'end_turn', 'stop_sequence': None, 'usage': {'input_tokens': 1, 'output_tokens': 1}}
        if chosen in ['401', '429', '500', 'redirect']:
            content = json.dumps({'type': 'error', 'error': {'type': 'synthetic_error', 'message': '离线错误'}}).encode()
            self.send_response(302 if chosen == 'redirect' else int(chosen))
            self.send_header('content-type', 'application/json')
            self.send_header('location', '/must-not-retry')
            self.send_header('content-length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        if not body.get('stream'):
            content = json.dumps(message, ensure_ascii=False).encode()
            with LOCK:
                CALLS[index]['responseBytes'] = len(content)
                CALLS[index]['responseSha256'] = hashlib.sha256(content).hexdigest()
            self.send_response(200)
            self.send_header('content-type', 'application/json; note="text/event-stream"' if chosen == 'json-mime-parameter' else 'application/json')
            self.send_header('content-length', str(len(content)))
            if chosen == 'close':
                self.send_header('connection', 'close')
                self.close_connection = True
            self.end_headers()
            self.wfile.write(content)
            self.wfile.flush()
            return
        self.send_response(200)
        self.send_header('content-type', 'Text/Event-Stream' if chosen == 'mimecase' else 'text/event-stream')
        self.send_header('transfer-encoding', 'chunked')
        self.end_headers()

        response_entity = bytearray()

        def chunk(value):
            """写出真实分块响应。:param value: 原片段。:return: None。"""
            response_entity.extend(value)
            self.wfile.write(('%x\r\n' % len(value)).encode() + value + b'\r\n')
            self.wfile.flush()

        def event(value):
            """序列化合成 SSE。:param value: 事件。:return: None。"""
            newline = '\r' if chosen == 'crline' else '\n'
            chunk(('event: ' + value['type'] + '\ndata: ' + json.dumps(value, ensure_ascii=False) + '\n\n').replace('\n', newline).encode())

        event({'type': 'message_start', 'message': {**message, 'content': [], 'stop_reason': None}})
        if chosen in ['long', 'cancel']:
            for _ in range(36 if chosen == 'long' else 120):
                time.sleep(1)
                chunk(b': keepalive\n\n')
        for block_index, block in enumerate(blocks):
            start = {**block, 'input': {}} if block['type'] == 'tool_use' else {'type': 'text', 'text': ''}
            event({'type': 'content_block_start', 'index': block_index, 'content_block': start})
            delta = {'type': 'input_json_delta', 'partial_json': json.dumps(block['input'], ensure_ascii=False)} if block['type'] == 'tool_use' else {'type': 'text_delta', 'text': block['text']}
            event({'type': 'content_block_delta', 'index': block_index, 'delta': delta})
            event({'type': 'content_block_stop', 'index': block_index})
        if chosen == 'sse-error':
            event({'type': 'error', 'error': {'message': '离线 SSE 错误'}})
        elif chosen != 'incomplete':
            event({'type': 'message_delta', 'delta': {'stop_reason': message['stop_reason']}, 'usage': {'output_tokens': 1}})
            event({'type': 'message_stop'})
        with LOCK:
            CALLS[index]['responseBytes'] = len(response_entity)
            CALLS[index]['responseSha256'] = hashlib.sha256(response_entity).hexdigest()
        self.wfile.write(b'0\r\n\r\n')
        self.wfile.flush()

    def log_message(self, format, *args):
        """关闭访问日志。:param format: 格式。:param args: 参数。:return: None。"""


def connection_id_unlocked(connection):
    """调用方已持锁时取得实际连接编号。:param connection: TLS 对象。:return: 编号。"""
    if connection not in CONNECTIONS:
        CONNECTIONS[connection] = len(CONNECTIONS) + 1
    return CONNECTIONS[connection]


class Server(ThreadingHTTPServer):
    """使用独立 OpenSSL TLS 的多连接 HTTP 上游。"""
    daemon_threads = True

    def handle_error(self, request, client_address):
        """取消和断连由测试断言处理。:param request: socket。:param client_address: 地址。:return: None。"""


def start_server(mode):
    """启动指定 TLS 版本，独立记录 ClientHello。:param mode: 模式。:return: 上游端口。"""
    server = Server(('127.0.0.1', 0), Handler)
    server.response_mode = 'json'
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ROOT / 'leaf.pem', ROOT / 'leaf.key')
    context.set_alpn_protocols(['http/1.1'])
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2 if mode == 'tls12' else ssl.TLSVersion.TLSv1_3
    if mode == 'hrr':
        context.set_ecdh_curve('prime256v1')

    def observe(connection, direction, version, content_type, message_type, data):
        """记录公开握手，排除随机密钥。:param connection: 连接。:param direction: 方向。:param version: 版本。:param content_type: 记录类型。:param message_type: 握手类型。:param data: 字节。:return: None。"""
        if direction == 'read' and int(content_type) == 22 and int(message_type) == 1:
            parsed = client_hello(data)
            identifier = connection_id(connection)
            with LOCK:
                HELLOS.append({'connection': identifier, 'fields': parsed})

    context._msg_callback = observe
    server.socket = context.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    SERVERS.append(server)
    return server.server_port


class Proxy(socketserver.ThreadingTCPServer):
    """固定目标的合成 CONNECT 入口。"""
    daemon_threads = True
    allow_reuse_address = True


class Tunnel(socketserver.BaseRequestHandler):
    """只转发密文，不改写最终 HTTP。"""
    def handle(self):
        """处理 CONNECT 并双向传输。:return: None。"""
        header = bytearray()
        while not header.endswith(b'\r\n\r\n') and len(header) < 128 * 1024:
            value = self.request.recv(1)
            if not value:
                return
            header.extend(value)
        target = bytes(header).split(b'\r\n')[0].decode()
        authorization = [line.split(b':', 1)[1].strip() for line in bytes(header).split(b'\r\n')[1:] if line.lower().startswith(b'proxy-authorization:')]
        with LOCK:
            TARGETS.append(target)
            CONNECT_HEADS.append({'target': target, 'authorizationSha256': hashlib.sha256(authorization[0]).hexdigest() if authorization else None, 'headers': [line.decode('latin1') if not line.lower().startswith(b'proxy-authorization:') else 'Proxy-Authorization: [SYNTHETIC]' for line in bytes(header).split(b'\r\n')[1:] if line]})
        if target not in ['CONNECT api.anthropic.com:443 HTTP/1.1', 'CONNECT fixture.local:443 HTTP/1.1']:
            self.request.sendall(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n')
            return
        with socket.create_connection(('127.0.0.1', self.server.upstream_port)) as upstream:
            self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            while True:
                readable, _, _ = select.select([self.request, upstream], [], [], 60)
                if not readable:
                    continue
                for source in readable:
                    value = source.recv(65536)
                    if not value:
                        return
                    (upstream if source is self.request else self.request).sendall(value)


for line in sys.stdin:
    command = json.loads(line)
    if command['type'] == 'start':
        port = start_server(command.get('mode', 'tls13'))
        proxy = Proxy(('127.0.0.1', 0), Tunnel)
        proxy.upstream_port = port
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        SERVERS.append(proxy)
        result = {'port': port, 'proxyPort': proxy.server_address[1], 'caFile': str(ROOT / 'ca.pem')}
    elif command['type'] == 'response_mode':
        servers = [server for server in SERVERS if isinstance(server, Server) and server.server_port == command['port']]
        if len(servers) != 1 or not isinstance(command['mode'], str):
            raise ValueError('响应模式指令未绑定已启动的上游')
        # 测试控制保持在私有管道，生产请求头白名单无需承载夹具开关。
        with LOCK:
            servers[0].response_mode = command['mode']
        result = {'type': 'response_mode', 'port': command['port'], 'mode': command['mode']}
    elif command['type'] == 'report':
        with LOCK:
            result = {'calls': list(CALLS), 'hellos': list(HELLOS), 'targets': list(TARGETS), 'connectHeads': list(CONNECT_HEADS)}
    elif command['type'] == 'shutdown':
        break
    else:
        raise ValueError('非法夹具命令')
    print(json.dumps(result, ensure_ascii=False), flush=True)
for server in SERVERS:
    server.shutdown()
    server.server_close()
