"""使用自有 TLS 写入器和独立接收端校验复用连接的写出摘要。"""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from socket import socketpair
from ssl import PROTOCOL_TLS_CLIENT, PROTOCOL_TLS_SERVER, SSLContext
from subprocess import DEVNULL, run
from tempfile import TemporaryDirectory
import unittest

from http_capture import CliWriteReceipts, HttpCapture


def message(body: bytes, extra: bytes = b'') -> bytes:
    """构造固定合成 POST。@param body 实体。@param extra 可选头行。@return 完整 HTTP 字节。"""
    return (b'POST /v1/messages HTTP/1.1\r\n' + extra + b'Content-Length: '
            + str(len(body)).encode() + b'\r\n\r\n' + body)


class CliReceiptTests(unittest.TestCase):
    """对照单请求、复用、同正文重发和尾部中断。"""

    def test_split_headers_and_shared_write(self):
        """对每个分段位置核对相同实体和不同请求头的写出。@return None。"""
        raw = [message(b'{}'), message(b'{}', b'X-Case: two\r\n'), message(b'')]
        stream = b''.join(raw)
        for split in range(len(stream) + 1):
            parser = CliWriteReceipts()
            samples = list(parser.feed(stream[:split])) + list(parser.feed(stream[split:]))
            parser.finish()
            self.assertEqual([s['http_sha256'] for s in samples], [sha256(m).hexdigest() for m in raw])
            self.assertEqual([s['sequence'] for s in samples], [1, 2, 3])
            self.assertEqual(samples[0]['body_sha256'], samples[1]['body_sha256'])
            self.assertNotIn('request_id', samples[0])
        single = HttpCapture()
        single.feed(stream)
        self.assertEqual(single.error, 'HTTP_EXTRA_BYTES')

    def test_partial_and_malformed(self):
        """确认部分写入不产生完整摘要，出错连接保留缺口。@return None。"""
        parser = CliWriteReceipts()
        raw = message(b'private-fixture', b'Authorization: private-fixture\r\n')
        self.assertEqual(len(list(parser.feed(message(b'{}') + raw[:-1]))), 1)
        self.assertFalse(parser.current.body)
        self.assertNotIn('private-fixture', str(parser.current.headers))
        with self.assertRaisesRegex(ValueError, 'HTTP_PARTIAL'):
            parser.finish()
        broken = CliWriteReceipts()
        with self.assertRaisesRegex(ValueError, 'HTTP_LENGTH_UNKNOWN'):
            list(broken.feed(b'POST /v1/messages HTTP/1.1\r\n\r\n'))
        with self.assertRaisesRegex(ValueError, 'HTTP_LENGTH_UNKNOWN'):
            list(broken.feed(message(b'{}')))

    def test_real_tls_writer(self):
        """核对同一握手上真实 TLS 接受量与独立接收端的原始 HTTP 摘要。@return None。"""
        with TemporaryDirectory() as directory:
            cert, key = Path(directory) / 'cert', Path(directory) / 'key'
            run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                 '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
                 '-out', str(cert), '-keyout', str(key)], check=True, stdout=DEVNULL, stderr=DEVNULL)
            server, client = SSLContext(PROTOCOL_TLS_SERVER), SSLContext(PROTOCOL_TLS_CLIENT)
            server.load_cert_chain(cert, key)
            client.load_verify_locations(cafile=str(cert))
            left, right = socketpair()
            left.settimeout(5)
            right.settimeout(5)
            messages = [message(b'first'), message(b'same'), message(b'same')]

            def receive():
                """从 TLS 接收端独立读取三份有边界的请求。@return 依次接收的原始摘要。"""
                digests = []
                with server.wrap_socket(left, server_side=True) as tls, tls.makefile('rb') as source:
                    for _ in messages:
                        head = source.readline()
                        length = None
                        while True:
                            line = source.readline()
                            if not line:
                                raise EOFError('接收端的请求头被截断')
                            head += line
                            if line == b'\r\n':
                                break
                            if line.startswith(b'Content-Length:'):
                                length = int(line.split(b':', 1)[1])
                        self.assertIsNotNone(length)
                        body = source.read(length)
                        self.assertEqual(len(body), length)
                        digests.append(sha256(head + body).hexdigest())
                return digests

            with left, right, ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(receive)
                with client.wrap_socket(right, server_hostname='localhost') as tls:
                    parser = CliWriteReceipts()
                    data = b''.join(messages)
                    receipts = []
                    for part in (data[:7], data[7:]):
                        while part:
                            accepted = tls.send(part)
                            self.assertGreater(accepted, 0)
                            receipts.extend(parser.feed(part[:accepted]))
                            part = part[accepted:]
                    parser.finish()
                self.assertEqual([row['http_sha256'] for row in receipts], result.result())
            self.assertEqual([row['sequence'] for row in receipts], [1, 2, 3])


if __name__ == '__main__':
    unittest.main()
