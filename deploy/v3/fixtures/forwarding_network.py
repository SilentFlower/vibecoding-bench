"""隔离转发上游：仅在本进程终止 TLS，不向任何公网地址建立连接。"""
import hashlib
import json
import socket
import socketserver
import ssl
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mock_network import forward_http, read_exact, serve_dns


ROOT = Path('/fixtures-data')
LOCK = threading.Lock()


def record(kind, **values):
    """保存不含认证信息的关联证据。

    :param kind: 证据类型。
    :param values: 合成请求的有限摘要。
    :return: None。
    """
    with LOCK, (ROOT / 'evidence.jsonl').open('a') as output:
        output.write(json.dumps({'kind': kind, 'at': time.time(), **values}) + '\n')


class Upstream(BaseHTTPRequestHandler):
    """返回可精确核对的 JSON 或有限/慢速 SSE。"""

    protocol_version = 'HTTP/1.1'

    def do_POST(self):
        """处理合成请求，不保存凭据或完整请求体。

        :return: None。
        """
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        payload = json.loads(body)
        marker = payload.get('marker') or payload.get('messages', [{}])[-1].get('content', '')
        record('upstream', marker=marker, path=self.path, body_sha256=hashlib.sha256(body).hexdigest(),
               billing_rewritten=any('x-anthropic-billing-header:' in str(item) and 'cc_version=0.0.1' not in str(item)
                   for item in payload.get('system', [])),
               metadata=payload.get('metadata'), tls=isinstance(self.connection, ssl.SSLSocket))
        self.send_response(200)
        self.send_header('request-id', 'synthetic-' + str(marker))
        self.send_header('anthropic-ratelimit-unified-verify-marker', str(marker))
        self.send_header('anthropic-ratelimit-unified-status', 'allowed')
        self.send_header('anthropic-ratelimit-unified-5h-utilization', '0.12')
        if not payload.get('stream'):
            value = {'marker': marker, 'ok': True}
            if self.path.startswith('/v1/messages'):
                value = {'id': 'msg_synthetic', 'type': 'message', 'role': 'assistant',
                    'content': [{'type': 'text', 'text': marker}], 'model': payload['model'],
                    'stop_reason': 'end_turn', 'stop_sequence': None,
                    'usage': {'input_tokens': 10, 'output_tokens': 1, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0}}
            response = json.dumps(value, separators=(',', ':')).encode()
            record('json-response', marker=marker, response_sha256=hashlib.sha256(response).hexdigest())
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)
            return
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Transfer-Encoding', 'chunked')
        self.end_headers()
        sequence = [('message_start', {'type': 'message_start', 'message': {'id': 'msg_synthetic', 'type': 'message',
            'role': 'assistant', 'content': [], 'model': payload.get('model', 'synthetic'), 'stop_reason': None,
            'stop_sequence': None, 'usage': {'input_tokens': 10, 'output_tokens': 0}}}),
            ('content_block_start', {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'text', 'text': ''}}),
            ('content_block_delta', {'type': 'content_block_delta', 'index': 0,
                'delta': {'type': 'text_delta', 'text': marker}}),
            ('content_block_stop', {'type': 'content_block_stop', 'index': 0}),
            ('message_delta', {'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 1}}),
            ('message_stop', {'type': 'message_stop'})]
        slow = str(marker).startswith('slow-')
        chunks = [*sequence[:2], *[sequence[2]] * 600, *sequence[3:]] if str(marker).startswith('slow-cancel') else sequence
        digest = hashlib.sha256()
        completed = False
        try:
            for name, value in chunks:
                event = ('event: ' + name + '\ndata: ' + json.dumps(value, separators=(',', ':')) + '\n\n').encode()
                digest.update(event)
                self.wfile.write(f'{len(event):x}\r\n'.encode() + event + b'\r\n')
                self.wfile.flush()
                time.sleep(0.1 if slow else 0.02)
            self.wfile.write(b'0\r\n\r\n')
            completed = True
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
            pass
        finally:
            record('stream-end', marker=marker, completed=completed, response_sha256=digest.hexdigest())

    def log_message(self, *args):
        """关闭默认日志，避免请求正文或认证信息泄露。

        :param args: 默认日志参数。
        :return: None。
        """


def tunnel(connection, peer, target, port, protocol):
    """将所有允许连接约束到本地服务，并记录真实发起 IP。

    :param connection: 已协商的代理连接。
    :param peer: 发起端 IP。
    :param target: 客户端请求的主机。
    :param port: 客户端请求的端口。
    :param protocol: 代理协议。
    :return: None。
    """
    record('proxy', peer=peer, target=target, port=port, protocol=protocol)
    if port == 53:
        serve_dns(connection)
    elif port == 443:
        mode = (ROOT / 'tls-mode').read_text().strip() if (ROOT / 'tls-mode').exists() else 'valid'
        forward_http(connection, {'valid': 8443, 'untrusted': 8444, 'hostname': 8445}[mode])


class Socks(socketserver.BaseRequestHandler):
    """隔离 SOCKS5，支持 DNS 隧道及固定 TLS 服务。"""

    def handle(self):
        """处理一次 SOCKS 请求。

        :return: None。
        """
        connection = self.request
        _, count = read_exact(connection, 2)
        read_exact(connection, count)
        connection.sendall(b'\x05\x00')
        _, command, _, kind = read_exact(connection, 4)
        if kind == 1:
            target = socket.inet_ntoa(read_exact(connection, 4))
        elif kind == 3:
            target = read_exact(connection, read_exact(connection, 1)[0]).decode('ascii')
        else:
            return
        port = struct.unpack('!H', read_exact(connection, 2))[0]
        if command != 1 or port not in (53, 443) or (ROOT / 'proxy-fail').exists():
            connection.sendall(b'\x05\x02\x00\x01' + b'\x00' * 6)
            return
        connection.sendall(b'\x05\x00\x00\x01' + b'\x00' * 6)
        tunnel(connection, self.client_address[0], target, port, 'socks5')


class Connect(socketserver.BaseRequestHandler):
    """隔离 HTTP CONNECT，可显式模拟认证拒绝。"""

    def handle(self):
        """处理一次 CONNECT 请求。

        :return: None。
        """
        request = b''
        while b'\r\n\r\n' not in request:
            part = self.request.recv(4096)
            if not part or len(request) + len(part) > 65536:
                return
            request += part
        method, target, _ = request.split(b'\r\n', 1)[0].decode('ascii').split(' ', 2)
        host, port = target.rsplit(':', 1)
        port = int(port)
        if method != 'CONNECT' or port not in (53, 443) or (ROOT / 'proxy-fail').exists():
            self.request.sendall(b'HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n')
            return
        self.request.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        tunnel(self.request, self.client_address[0], host, port, 'http')


class Server(socketserver.ThreadingTCPServer):
    """代理连接独立处理，清理时不等待长连接。"""
    allow_reuse_address = True
    daemon_threads = True


def main():
    """启动三个证书场景和两个代理入口。

    :return: None。
    """
    for mode, port in (('valid', 8443), ('untrusted', 8444), ('hostname', 8445)):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(ROOT / (mode + '.crt')), str(ROOT / (mode + '.key')))
        server = ThreadingHTTPServer(('0.0.0.0', port), Upstream)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=Server(('0.0.0.0', 1081), Connect).serve_forever, daemon=True).start()
    (ROOT / 'ready').touch()
    Server(('0.0.0.0', 1080), Socks).serve_forever()


if __name__ == '__main__':
    main()
