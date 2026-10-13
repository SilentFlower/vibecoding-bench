"""隔离网络内的 SOCKS/DNS/HTTP 替身；全部连接仅映射到本进程。"""
import ipaddress
import json
import socket
import socketserver
import ssl
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    """记录发送来源并返回合成额度头，不访问公网。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self):
        """通过真实本地 TLS 返回合成 usage，不记录凭据。@return None。"""
        now = time.time()
        body = json.dumps({
            "five_hour": {"utilization": 12, "resets_at": datetime.fromtimestamp(now + 3600, timezone.utc).isoformat()},
            "seven_day": {"utilization": 23, "resets_at": datetime.fromtimestamp(now + 86400, timezone.utc).isoformat()},
        }).encode()
        with Path("/fixtures-data/usage-calls.jsonl").open("a") as output:
            output.write(json.dumps({"path": self.path, "tls": isinstance(self.connection, ssl.SSLSocket)}) + "\n")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        """原样返回请求正文及来源地址，返回 None。"""
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/v1/v3-stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            try:
                for index in range(1200):
                    event = ("data: " + json.dumps({"index": index, "time": time.time()}) + "\n\n").encode()
                    self.wfile.write(f"{len(event):x}\r\n".encode() + event + b"\r\n")
                    self.wfile.flush()
                    time.sleep(0.1)
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        self.send_response(429)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("anthropic-ratelimit-unified-5h-utilization", "0.12")
        self.send_header("X-Mock-Peer", self.client_address[0])
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """关闭含请求路径的默认日志，返回 None。"""
        pass


def read_exact(connection, size):
    """读取 SOCKS/DNS 定长字段；返回字节串。"""
    result = b""
    while len(result) < size:
        part = connection.recv(size - len(result))
        if not part:
            raise EOFError()
        result += part
    return result


def serve_dns(connection):
    """在当前代理隧道内返回合成 A 记录。@param connection 已建立的代理连接；@return None。"""
    while True:
        try:
            size = struct.unpack("!H", read_exact(connection, 2))[0]
            query = read_exact(connection, size)
        except EOFError:
            return
        end = 12
        while query[end]:
            end += 1 + query[end]
        end += 5
        answer = query[:2] + b"\x81\x80" + query[4:6] + b"\x00\x01\x00\x00\x00\x00" + query[12:end]
        answer += b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + ipaddress.ip_address("198.18.0.10").packed
        connection.sendall(struct.pack("!H", len(answer)) + answer)


def record_tls(connection, peer):
    """记录隔离 TLS 探针的来源、长度和有限前缀。@param connection 代理连接；@param peer 来源 IP；@return None。"""
    native_usage = Path("/fixtures-data/usage-tls.enabled").exists()
    hello = connection.recv(16384, socket.MSG_PEEK if native_usage else 0)
    with open("/fixtures-data/tls.jsonl", "a") as output:
        output.write(json.dumps({"peer": peer, "record_type": hello[0] if hello else None,
            "length": len(hello), "payload_prefix": hello[:32].hex()}) + "\n")
    if native_usage:
        forward_http(connection, port=8443)


def forward_http(connection, port=8081):
    """把隔离代理的 8081 隧道转到本地合成 HTTP。@param connection 代理连接；@return None。"""
    with socket.create_connection(("127.0.0.1", port)) as upstream:
        def forward(source, destination):
            """转发有限本地字节并在结束时关闭写侧。"""
            try:
                while part := source.recv(65536):
                    destination.sendall(part)
            finally:
                try:
                    destination.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
        thread = threading.Thread(target=forward, args=(connection, upstream), daemon=True)
        thread.start()
        forward(upstream, connection)
        thread.join(timeout=2)


class Socks(socketserver.BaseRequestHandler):
    """只转发到本地 HTTP，DNS 返回合成 IPv4，公网地址不建立连接。"""

    def handle(self):
        """解析连接目标并在隔离测试服务内处理，返回 None。"""
        connection = self.request
        _, count = read_exact(connection, 2)
        read_exact(connection, count)
        connection.sendall(b"\x05\x00")
        _, command, _, kind = read_exact(connection, 4)
        if kind == 1:
            read_exact(connection, 4)
        elif kind == 3:
            read_exact(connection, read_exact(connection, 1)[0])
        else:
            return
        port = struct.unpack("!H", read_exact(connection, 2))[0]
        if command != 1 or port not in (53, 8081, 443):
            connection.sendall(b"\x05\x02\x00\x01" + b"\x00" * 6)
            return
        connection.sendall(b"\x05\x00\x00\x01" + b"\x00" * 6)
        if port == 53:
            serve_dns(connection)
        elif port == 443:
            record_tls(connection, self.client_address[0])
        else:
            forward_http(connection)


class HttpConnect(socketserver.BaseRequestHandler):
    """提供隔离 HTTP CONNECT 上游，覆盖 DNS、TLS 和本地 HTTP。"""

    def handle(self):
        """解析 CONNECT 后复用合成隧道处理器，返回 None。"""
        connection = self.request
        request = b""
        while b"\r\n\r\n" not in request:
            part = connection.recv(4096)
            if not part or len(request) + len(part) > 65536:
                return
            request += part
        try:
            method, target, _ = request.split(b"\r\n", 1)[0].decode("ascii").split(" ", 2)
            _, port_text = target.rsplit(":", 1)
            port = int(port_text)
        except (ValueError, UnicodeDecodeError):
            return
        if method != "CONNECT" or port not in (53, 8081, 443):
            connection.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            return
        connection.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        if port == 53:
            serve_dns(connection)
        elif port == 443:
            record_tls(connection, self.client_address[0])
        else:
            forward_http(connection)


class Server(socketserver.ThreadingTCPServer):
    """允许立即重启测试服务，每个 SOCKS 连接独立处理。"""
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    certificate = Path("/fixtures-data/native-usage.crt")
    if certificate.exists():
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(certificate), "/fixtures-data/native-usage.key")
        tls_server = ThreadingHTTPServer(("0.0.0.0", 8443), Handler)
        tls_server.socket = context.wrap_socket(tls_server.socket, server_side=True)
        threading.Thread(target=tls_server.serve_forever, daemon=True).start()
    threading.Thread(target=ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever, daemon=True).start()
    threading.Thread(target=Server(("0.0.0.0", 1081), HttpConnect).serve_forever, daemon=True).start()
    Server(("0.0.0.0", 1080), Socks).serve_forever()
