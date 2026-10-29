"""以独立游标解析既有握手，并与固定 SDK 比较；输入与输出均为 JSON。

输入通过 stdin 提供含 records 的研究证据；只输出字段摘要，不输出原始握手。
"""
import base64
import hashlib
import json
import sys

from mitmproxy import tls, version


class Cursor:
    """按网络字节序严格读取给定字节串。

    :param data: 待解析的字节串。
    """

    def __init__(self, data):
        """保存解析输入。

        :param data: 待解析的字节串。
        """
        self.data = data
        self.position = 0

    def take(self, length):
        """读取并推进游标，截断时报错。

        :param length: 要读取的字节数。
        :return: 本段字节。
        """
        if length < 0 or self.position + length > len(self.data):
            raise ValueError("向量截断")
        result = self.data[self.position:self.position + length]
        self.position += length
        return result

    def integer(self, width):
        """读取一个无符号网络序整数。

        :param width: 整数宽度，单位字节。
        :return: 整数值。
        """
        return int.from_bytes(self.take(width), "big")

    def vector(self, width):
        """读取带字节长度前缀的向量。

        :param width: 长度前缀宽度。
        :return: 向量字节。
        """
        return self.take(self.integer(width))

    def finish(self):
        """断言没有多余字节。

        :return: 无。
        """
        assert self.position == len(self.data), "存在尾随字节"


def numbers(raw, prefix, element):
    """解码带长度前缀的定宽整数列表。

    :param raw: 向量正文。
    :param prefix: 长度前缀宽度。
    :param element: 元素宽度。
    :return: 有序整数列表。
    """
    cursor = Cursor(raw)
    data = cursor.vector(prefix)
    cursor.finish()
    assert len(data) % element == 0, "向量长度不能整除元素宽度"
    return [int.from_bytes(data[i:i + element], "big") for i in range(0, len(data), element)]


def analyze(record):
    """独立解析一个 TLS 初始握手并核对 SDK 与旧证据。

    :param record: 包含原始 record 和原有解析结果的样本。
    :return: 不含原始握手的验证摘要。
    """
    records = Cursor(base64.b64decode(record["raw_base64"], validate=True))
    handshake = b""
    while records.position < len(records.data):
        assert records.integer(1) == 22, "仅接受本探针的 handshake record"
        records.take(2)
        handshake += records.vector(2)
    records.finish()
    handshake_cursor = Cursor(handshake)
    assert handshake_cursor.integer(1) == 1
    body = handshake_cursor.vector(3)
    handshake_cursor.finish()
    cursor = Cursor(body)
    legacy_version = cursor.integer(2)
    cursor.take(32)
    cursor.vector(1)
    ciphers_raw = cursor.vector(2)
    assert len(ciphers_raw) % 2 == 0
    ciphers = [int.from_bytes(ciphers_raw[i:i + 2], "big") for i in range(0, len(ciphers_raw), 2)]
    cursor.vector(1)
    extensions = []
    if cursor.position < len(body):
        extension_cursor = Cursor(cursor.vector(2))
        while extension_cursor.position < len(extension_cursor.data):
            extensions.append((extension_cursor.integer(2), extension_cursor.vector(2)))
        extension_cursor.finish()
    cursor.finish()
    fields = {"legacy_version": legacy_version, "cipher_suites": ciphers, "extensions": [kind for kind, _ in extensions]}
    formats = []
    for kind, value in extensions:
        if kind in (10, 13, 43):
            name = {10: "supported_groups", 13: "signature_algorithms", 43: "supported_versions"}[kind]
            fields[name] = numbers(value, 1 if kind == 43 else 2, 2)
        elif kind == 11:
            formats = numbers(value, 1, 1)
        elif kind == 16:
            outer = Cursor(value)
            inner = Cursor(outer.vector(2))
            outer.finish()
            fields["alpn"] = []
            while inner.position < len(inner.data):
                fields["alpn"].append(inner.vector(1).decode("ascii"))
            inner.finish()
        elif kind == 51:
            outer = Cursor(value)
            inner = Cursor(outer.vector(2))
            outer.finish()
            fields["key_share"] = []
            while inner.position < len(inner.data):
                group = inner.integer(2)
                key = inner.vector(2)
                fields["key_share"].append({"group": group, "key_length": len(key)})
            inner.finish()
    for key, expected in record["parsed"].items():
        assert fields[key] == expected, key
    hello = tls.ClientHello(body)
    assert hello.raw_bytes(wrap_in_record=False) == body
    expected_wrapper = b"\x16\x03\x03" + (len(body) + 4).to_bytes(2, "big") + b"\x01" + len(body).to_bytes(3, "big") + body
    assert hello.raw_bytes() == expected_wrapper
    assert hello.cipher_suites == ciphers
    assert hello.extensions == extensions
    assert hello.alpn_protocols == [x.encode("ascii") for x in fields.get("alpn", [])]
    grease = {0x0A0A + i * 0x1010 for i in range(16)}
    # JA3 仅在投影中排除 GREASE，保持上方解析结果中的原始顺序与值。
    segments = [[legacy_version], [x for x in ciphers if x not in grease], [kind for kind, _ in extensions if kind not in grease], [x for x in fields.get("supported_groups", []) if x not in grease], formats]
    ja3 = ",".join("-".join(str(x) for x in part) for part in segments)
    return {"source": record["source"], "body_length": len(body), "assertions": "passed", "fields": fields, "ja3": ja3, "ja3_md5": hashlib.md5(ja3.encode("ascii")).hexdigest()}


def main():
    """执行固定版本对照。

    :return: 无；验证失败时以异常结束。
    """
    assert version.VERSION == "11.1.3", version.VERSION
    evidence = json.load(sys.stdin)
    results = [analyze(record) for record in evidence["records"]]
    print(json.dumps({"status": "passed", "mitmproxy_version": version.VERSION, "evidence_kind": "prior_synthetic_handshake", "sample_count": len(results), "records": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
