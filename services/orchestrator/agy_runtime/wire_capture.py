"""读取同一次模型请求的实际 HTTP 传输或原生 TLS 写入。"""
import base64
from io import BytesIO
import re


TRACE_LIMIT = 32 * 1024 * 1024
HEADER_LIMIT = 128 * 1024
_EVENT = re.compile(rb'=> Send (header|data), ([0-9]+) bytes ')
_LINE = re.compile(rb'[0-9a-f]+: ')
_HEADER = re.compile(rb"[!#$%&'*+.^_\x60|~0-9A-Za-z-]+")


def read_chunks(reader, limit):
    """读取有界 HTTP 分块实体。@param reader 二进制流。@param limit 逻辑实体上限。@return 原实体字节。"""
    raw = bytearray()
    while True:
        line = reader.readline(128)
        if not line.endswith(b'\r\n'):
            raise ValueError('分块首行无效')
        size = int(line[:-2].split(b';', 1)[0], 16)
        if size == 0:
            if reader.readline(128) != b'\r\n':
                raise ValueError('分块结束无效')
            return raw
        if not 0 < size <= limit - len(raw):
            raise ValueError('分块长度越界')
        chunk = reader.read(size)
        if len(chunk) != size or reader.read(2) != b'\r\n':
            raise ValueError('分块正文未收口')
        raw.extend(chunk)


class WireTrace:
    """只观察模型 POST 的出站头和正文，跳过 CONNECT、TLS 握手和响应。"""

    def __init__(self, path):
        """冻结本次允许的出站路径。@param path 实际预期 HTTP 路径。@return 无。"""
        self.request = ('POST ' + path + ' HTTP/1.1').encode()
        self.headers = None
        self.data = bytearray()
        self.failed = False
        self.status = None

    def read(self, stream):
        """消费实际传输日志并立即丢弃非模型流量。@param stream 私有匿名管道。@return 无。"""
        event = None
        remaining = 0
        value = bytearray()
        try:
            with stream:
                for line in stream:
                    if self.failed:
                        continue
                    match = _EVENT.match(line)
                    if match:
                        if remaining:
                            self.failed = True
                            continue
                        event = match[1]
                        remaining = int(match[2])
                        limit = HEADER_LIMIT if event == b'header' else TRACE_LIMIT - len(self.data)
                        if not 0 < remaining <= limit:
                            self.failed = True
                        value.clear()
                        continue
                    if not remaining:
                        continue
                    prefix = _LINE.match(line)
                    if not prefix:
                        self.failed = True
                        continue
                    count = min(remaining, 16)
                    try:
                        part = bytes.fromhex(line[prefix.end():prefix.end() + count * 3 - 1].decode('ascii'))
                    except (UnicodeError, ValueError):
                        self.failed = True
                        continue
                    if len(part) != count:
                        self.failed = True
                        continue
                    value.extend(part)
                    remaining -= count
                    if not remaining and event == b'header':
                        if value.split(b'\r\n', 1)[0] == self.request:
                            if self.headers is not None:
                                self.failed = True
                            try:
                                self.headers = self._headers(value)
                            except ValueError:
                                self.failed = True
                    elif not remaining and event == b'data' and self.headers is not None:
                        self.data.extend(value)
            self.failed |= bool(remaining)
        except (OSError, ValueError):
            self.failed = True

    @staticmethod
    def _headers(raw):
        if not raw.endswith(b'\r\n\r\n'):
            raise ValueError('出站头未收口')
        pairs = []
        for line in raw.split(b'\r\n')[1:-2]:
            name, separator, value = line.partition(b':')
            if not separator or not _HEADER.fullmatch(name):
                raise ValueError('出站头无效')
            pairs.append([name.decode('ascii').lower(), value.strip().decode('latin1')])
        return pairs

    def body(self, expected):
        """仅在观察的实体与当次实际提交相符时返回正文。@param expected 本次受控发送实体。@return 完整实体或空。"""
        if self.failed or self.headers is None:
            return None
        if ['transfer-encoding', 'chunked'] in self.headers:
            stream = BytesIO(self.data)
            try:
                observed = read_chunks(stream, TRACE_LIMIT)
            except ValueError:
                return None
            if stream.read(1):
                return None
        else:
            observed = self.data
        return expected if observed == expected else None


class NativeTlsTrace:
    """只接收当前模型作业的 TLS 接受字节，按实际 HTTP 边界判定完整性。"""

    def __init__(self):
        """初始化有界作业副本。@return 无。"""
        self.data = bytearray()
        self.headers = None
        self.status = None
        self.failed = False
        self.call_id = None

    def append(self, event):
        """累积观察器同一调用的本地 TLS 接受字节。@param event 已绑定的观察事件。@return 无。"""
        if self.failed:
            return
        if self.call_id is None:
            self.call_id = event['call_id']
        try:
            raw = base64.b64decode(event['data_base64'], validate=True)
            if self.call_id != event['call_id'] or not raw or len(raw) != event['bytes'] or len(self.data) + len(raw) > TRACE_LIMIT:
                raise ValueError('原生写入观察归属或长度无效')
            self.data.extend(raw)
        except (KeyError, TypeError, ValueError):
            self.failed = True
            self.data.clear()

    def body(self, _expected):
        """依据捕获的头验证完整实体。@param _expected 兼容实际传输观察的接口。@return 已核对的实体或空。"""
        if self.failed:
            return None
        end = self.data.find(b'\r\n\r\n', 0, HEADER_LIMIT)
        if end < 0:
            return None
        try:
            raw_headers = bytes(self.data[:end + 4])
            request_line = raw_headers.split(b'\r\n', 1)[0]
            if not re.fullmatch(rb'POST /v1internal:streamGenerateContent(?:\?[^ ]*)? HTTP/1\.1', request_line):
                return None
            headers = WireTrace._headers(raw_headers)
            lengths = [value for name, value in headers if name == 'content-length']
            transfers = [value.lower() for name, value in headers if name == 'transfer-encoding']
            body = bytes(self.data[end + 4:])
            if not lengths and transfers == ['chunked']:
                stream = BytesIO(body)
                body = bytes(read_chunks(stream, TRACE_LIMIT))
                if stream.read(1):
                    return None
            elif not transfers and len(lengths) == 1 and lengths[0].isascii() and lengths[0].isdigit() and int(lengths[0]) == len(body):
                pass
            else:
                return None
            self.headers = headers
            return body
        except (ValueError, OverflowError):
            return None
