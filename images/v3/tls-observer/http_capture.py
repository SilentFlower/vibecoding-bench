"""对 TLS 已接受副本流式计算 HTTP 实体证据，所有原文只留在私有管道。"""
import hashlib
import re
import time

BODY_LIMIT = 2 * 1024 * 1024
HEADER_LIMIT = 128 * 1024
TOKEN = re.compile(rb"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


class HttpCapture:
    """一个 SSL 对象在单次作业内的有界 HTTP/1.1 解析状态。"""

    def __init__(self) -> None:
        """初始化长度、摘要与有界预览。@return None。"""
        self.head = bytearray()
        self.headers = []
        self.body = bytearray()
        self.digest = hashlib.sha256()
        self.http_digest = hashlib.sha256()
        self.http_bytes = 0
        self.observed = 0
        self.length = None
        self.error = None

    def feed(self, data: bytes) -> None:
        """消费一次实际接受的字节。@param data 原序副本。@return None。"""
        if self.error:
            return
        if self.length is None:
            self.head.extend(data)
            end = self.head.find(b'\r\n\r\n')
            if end < 0:
                if len(self.head) > HEADER_LIMIT:
                    self.error = 'HTTP_HEADER_LIMIT'
                    self.head.clear()
                return
            if end + 4 > HEADER_LIMIT:
                self.error = 'HTTP_HEADER_LIMIT'
                self.head.clear()
                return
            raw = bytes(self.head[:end])
            data = bytes(self.head[end + 4:])
            self.head.clear()
            lines = raw.split(b'\r\n')
            if not re.fullmatch(rb'POST /v1/messages(?:\?[^ \r\n]*)? HTTP/1\.1', lines[0]):
                self.error = 'HTTP_UNSUPPORTED'
                return
            lengths = []
            for line in lines[1:]:
                name, separator, value = line.partition(b':')
                if not separator or not TOKEN.fullmatch(name) or any(byte < 32 and byte != 9 or byte == 127 for byte in value):
                    self.error = 'HTTP_INVALID'
                    return
                value = value.strip(b' \t')
                self.headers.append([name.decode('ascii'), value.decode('latin-1')])
                if name.lower() == b'content-length':
                    lengths.append(value)
                if name.lower() == b'transfer-encoding':
                    self.error = 'HTTP_UNSUPPORTED'
                    return
            if len(lengths) != 1 or not re.fullmatch(rb'[0-9]{1,16}', lengths[0]):
                self.error = 'HTTP_LENGTH_UNKNOWN'
                return
            self.length = int(lengths[0])
            self.http_digest.update(raw + b'\r\n\r\n')
            self.http_bytes = end + 4
        # 连接复用可能在收口前进入下一请求；先限定实体边界，避免其原文进入本次副本。
        accepted = data[:self.length - self.observed]
        self.observed += len(accepted)
        self.digest.update(accepted)
        self.http_digest.update(accepted)
        self.http_bytes += len(accepted)
        self.body.extend(accepted[:max(0, BODY_LIMIT - len(self.body))])
        if len(accepted) != len(data):
            self.error = 'HTTP_EXTRA_BYTES'

    def client_id(self) -> str | None:
        """读取唯一实际请求头。@return 单个 x-client-request-id；歧义为空。"""
        values = [value for name, value in self.headers if name.lower() == 'x-client-request-id']
        return values[0] if len(values) == 1 else None

    def evidence(self, reason: str | None) -> dict:
        """投影实体完整性。@param reason 外部丢失或失败原因。@return 私有证据对象。"""
        # 外部故障代表连续性或归属待核对；清空预览，防止凭据跨缺口后只剩可见片段。
        unsafe = reason is not None
        reason = reason or self.error
        complete = reason is None and self.length is not None and self.observed == self.length
        raw = b'' if unsafe else bytes(self.body)
        # 截断仅保留完整 UTF-8 字符，合法性由完整实体或正文前缀独立确认。
        try:
            body = raw.decode('utf-8')
        except UnicodeDecodeError as error:
            if len(raw) == BODY_LIMIT and error.start >= len(raw) - 3 and error.reason == 'unexpected end of data':
                body = raw[:error.start].decode('utf-8')
            else:
                body = ''
                complete = False
                reason = reason or 'BODY_ENCODING'
        return {
            'source': 'native_tls_uprobe', 'representation': 'http_entity_from_tls_accepted_write',
            'status': 'complete' if complete else 'incomplete', 'reason': reason or (None if complete else 'HTTP_PARTIAL'),
            'captured_at_ms': int(time.time() * 1000), 'headers': [] if unsafe else self.headers, 'body': body,
            'body_truncated': len(body.encode()) != self.observed,
            'headers_truncated': unsafe and bool(self.headers),
            'observed_body_bytes': self.observed if complete else None,
            'body_sha256': self.digest.hexdigest() if complete else None,
            'observed_http_bytes': self.http_bytes if complete else None,
            'http_sha256': self.http_digest.hexdigest() if complete else None,
            'complete': complete, 'flushed': None,
        }


def unavailable(reason: str) -> dict:
    """生成明确缺证。@param reason 固定原因码。@return 缺证对象。"""
    result = HttpCapture().evidence(reason)
    result['status'] = 'unavailable'
    return result
