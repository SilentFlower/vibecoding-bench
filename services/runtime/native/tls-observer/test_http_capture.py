"""合成协议回归；不建立网络或调用模型。"""
import hashlib
import ctypes
import struct
import unittest

from http_capture import BODY_LIMIT, HttpCapture
from observer import Observer


def request(body=b'{"text":"synthetic"}', extra=b''):
    """构造独立HTTP字节。@param body 合成实体。@param extra 额外头。@return 明文。"""
    return (b'POST /v1/messages?beta=true HTTP/1.1\r\nx-client-request-id: fixture\r\n'
            + extra + b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)


class HttpCaptureTest(unittest.TestCase):
    """核对分段、缺口、请求归属及共同上限。"""

    def test_every_header_boundary_and_body_partial(self):
        """任意边界分段保持相同实体。@return None。"""
        body = '{"text":"离线合成"}'.encode()
        raw = request(body)
        for boundary in range(len(raw) + 1):
            state = HttpCapture()
            state.feed(raw[:boundary])
            state.feed(raw[boundary:])
            value = state.evidence(None)
            self.assertTrue(value['complete'], boundary)
            self.assertEqual(value['body'].encode(), body)
            self.assertEqual(value['body_sha256'], hashlib.sha256(body).hexdigest())
            self.assertEqual(state.client_id(), 'fixture')
        state = HttpCapture()
        state.feed(raw[:-1])
        value = state.evidence(None)
        self.assertEqual(value['reason'], 'HTTP_PARTIAL')
        self.assertIsNone(value['body_sha256'])
        self.assertIsNone(value['observed_body_bytes'])

    def test_gap_duplicate_length_and_extra_bytes(self):
        """丢副本及歧义HTTP均保持未知摘要。@return None。"""
        for raw, reason in ((request(), 'EVENT_LOSS'),
                            (request(extra=b'Content-Length: 20\r\n'), None),
                            (request(extra=b'Transfer-Encoding: chunked\r\n'), None),
                            (request() + b'x', None)):
            state = HttpCapture()
            state.feed(raw)
            value = state.evidence(reason)
            self.assertFalse(value['complete'])
            self.assertIsNone(value['body_sha256'])
        state = HttpCapture()
        state.feed(request(extra=b'x-client-request-id: other\r\n'))
        self.assertIsNone(state.client_id())

    def test_full_hash_survives_bounded_multibyte_preview(self):
        """正文只保存前缀，全量哈希覆盖所有已接受字节。@return None。"""
        body = ('中' * (BODY_LIMIT // 3 + 100)).encode()
        state = HttpCapture()
        raw = request(body)
        for offset in range(0, len(raw), 8192):
            state.feed(raw[offset:offset + 8192])
        value = state.evidence(None)
        self.assertTrue(value['complete'])
        self.assertTrue(value['body_truncated'])
        self.assertLessEqual(len(value['body'].encode()), BODY_LIMIT)
        self.assertEqual(value['observed_body_bytes'], len(body))
        self.assertEqual(value['body_sha256'], hashlib.sha256(body).hexdigest())

    def test_reused_connection_excludes_next_request_before_copy_and_hash(self):
        """分段及合并接受均只保留首条实体。@return None。"""
        body = b'{"text":"first-private-body"}'
        first = request(body)
        second = request(b'{"text":"next-info-private-prompt"}',
                         b'Authorization: Bearer next-private-credential\r\n')
        for chunks in ((first, second), (first + second,), (first[:-5], first[-5:] + second)):
            state = HttpCapture()
            for chunk in chunks:
                state.feed(chunk)
            state.feed(second)
            value = state.evidence(None)
            self.assertEqual(value['reason'], 'HTTP_EXTRA_BYTES')
            self.assertEqual(value['body'].encode(), body)
            self.assertNotIn('next-', str(value))
            self.assertEqual(state.observed, len(body))
            self.assertEqual(state.digest.hexdigest(), hashlib.sha256(body).hexdigest())
            self.assertEqual(state.http_digest.hexdigest(), hashlib.sha256(first).hexdigest())
            self.assertIsNone(value['body_sha256'])

    def test_event_gap_stops_parsing_and_withholds_credential_fragments(self):
        """首中尾缺口均保留未知范围，跨事件凭据片段保持私有。@return None。"""
        secret = b'synthetic-credential-prefix-private-suffix'
        raw = request(b'{"text":"' + secret + b'"}')
        boundary = raw.index(secret) + len(b'synthetic-credential-prefix')
        chunks = (raw[:boundary], raw[boundary:-2], raw[-2:])
        for missing in range(3):
            observer = Observer.__new__(Observer)
            observer.pid = 1234
            observer.namespace_pid = 1234
            observer.connections = {}
            observer.writes = observer.accepted = 0
            observer.reason = None
            for sequence, chunk in enumerate(chunks, 1):
                if sequence == missing + 1:
                    continue
                event = struct.pack('<QQQII', 1234 << 32 | 1, 99, sequence, len(chunk), len(chunk))
                record = ctypes.create_string_buffer(event + chunk.ljust(16384, b'\0'))
                observer._sample(None, record, 16416)
            reason = observer.reason or 'EVENT_LOSS'
            if missing < 2:
                self.assertEqual(reason, 'EVENT_SEQUENCE')
            for state in observer.connections.values():
                value = state.evidence(reason)
                self.assertEqual(value['body'], '')
                self.assertEqual(value['headers'], [])
                self.assertNotIn('synthetic-credential-prefix', str(value))
                self.assertIsNone(value['body_sha256'])
                self.assertIsNone(value['http_sha256'])
                self.assertIsNone(value['observed_body_bytes'])
            if missing == 1:
                self.assertEqual(bytes(observer.connections[99].body), b'{"text":"synthetic-credential-prefix')


if __name__ == '__main__':
    unittest.main()
