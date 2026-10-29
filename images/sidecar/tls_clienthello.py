"""解析客户端握手本体，并把含恢复材料的原始证据追加到私有文件。"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any


# ClientHello 的 cipher、extension 块均受 uint16 长度限制；该上限覆盖合法本体，
# 同时避免异常 SDK 输入让 JSONL 的单行内存和文件占用无限增长。
MAX_CLIENTHELLO_BYTES = 256 * 1024
_GREASE = frozenset(0x0A0A + 0x1010 * index for index in range(16))


class _ParseError(ValueError):
    """仅携带固定错误码的握手结构错误，不包含原始字节。"""


class _Reader:
    """用严格边界游标读取一个独立的 TLS 长度域。"""

    def __init__(self, data: bytes) -> None:
        """创建有界游标。:param data: 本长度域字节。:return: None。"""
        self.data = data
        self.offset = 0

    def take(self, length: int) -> bytes:
        """消费严格字节数。:param length: 非负长度。:return: 对应字节；越界抛固定错误。"""
        if length < 0 or self.offset + length > len(self.data):
            raise _ParseError("truncated_clienthello")
        result = self.data[self.offset:self.offset + length]
        self.offset += length
        return result

    def number(self, width: int) -> int:
        """读取无符号网络序整数。:param width: 字节宽度。:return: 整数值。"""
        return int.from_bytes(self.take(width), "big")

    def vector(self, width: int) -> bytes:
        """读取带前缀长度的向量。:param width: 长度字段宽度。:return: 完整向量字节。"""
        return self.take(self.number(width))

    def finish(self) -> None:
        """确认长度域已读完。:return: None；存在尾部字节时抛固定错误。"""
        if self.offset != len(self.data):
            raise _ParseError("invalid_length")


def _ids(data: bytes, length_width: int, item_width: int) -> list[int]:
    reader = _Reader(data)
    payload = reader.vector(length_width)
    reader.finish()
    if len(payload) % item_width:
        raise _ParseError("invalid_extension_vector")
    return [int.from_bytes(payload[index:index + item_width], "big")
            for index in range(0, len(payload), item_width)]


def ja3_fingerprint(legacy_version: int, cipher_suites: list[int], extensions: list[int],
                    supported_groups: list[int], ec_point_formats: list[int]) -> dict[str, str]:
    """按原序生成标准 JA3，只在指纹投影中移除 GREASE。

    :param legacy_version: ClientHello 本体的 legacy_version，不是协商版本。
    :param cipher_suites: 原序 cipher suite ID。
    :param extensions: 原序扩展类型 ID。
    :param supported_groups: 原序组 ID。
    :param ec_point_formats: 原序 EC 点格式。
    :return: 五字段字符串及其 MD5；该摘要不用于安全身份认证。
    """
    vectors = (cipher_suites, extensions, supported_groups)
    parts = [str(legacy_version)]
    parts.extend("-".join(str(value) for value in values if value not in _GREASE) for values in vectors)
    parts.append("-".join(str(value) for value in ec_point_formats))
    text = ",".join(parts)
    return {"string": text, "md5": hashlib.md5(text.encode("ascii"), usedforsecurity=False).hexdigest()}


def parse_clienthello(raw: bytes) -> dict[str, Any]:
    """解析不含 record／handshake 头的 ClientHello 本体，保留私有原始字节。

    :param raw: mitmproxy ClientHello.raw_bytes(wrap_in_record=False) 的结果。
    :return: 原始封装、解析状态、有序字段及可复算 JA3；异常结构不生成指纹。
    """
    saved = raw[:MAX_CLIENTHELLO_BYTES]
    result: dict[str, Any] = {
        "raw_format": "clienthello_body", "tls_record_preserved": False,
        "raw_base64": base64.b64encode(saved).decode("ascii"),
        "raw_bytes": len(raw), "raw_saved_bytes": len(saved),
        "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_truncated": len(saved) != len(raw),
        "parse_status": "ok", "parse_error": None,
        "legacy_version": None, "cipher_suites": [], "extensions": [],
        "signature_algorithms": None, "supported_groups": None, "supported_versions": None,
        "ec_point_formats": None, "key_share": None, "sni": None, "alpn_protocols": None, "ja3": None,
    }
    if len(raw) > MAX_CLIENTHELLO_BYTES:
        result.update(parse_status="oversize", parse_error="clienthello_too_large")
        return result
    try:
        reader = _Reader(raw)
        result["legacy_version"] = reader.number(2)
        reader.take(32)
        if len(reader.vector(1)) > 32:
            raise _ParseError("invalid_session_id_length")
        ciphers = reader.vector(2)
        if not ciphers or len(ciphers) % 2:
            raise _ParseError("invalid_cipher_suites")
        result["cipher_suites"] = [int.from_bytes(ciphers[index:index + 2], "big")
                                   for index in range(0, len(ciphers), 2)]
        if not reader.vector(1):
            raise _ParseError("invalid_compression_methods")
        # TLS 1.2 及更早版本可以完全没有 extensions 长度域，不能按截断处理。
        extension_reader = _Reader(reader.vector(2) if reader.offset < len(raw) else b"")
        reader.finish()
        extensions: list[tuple[int, bytes]] = []
        while extension_reader.offset < len(extension_reader.data):
            extension_type = extension_reader.number(2)
            payload = extension_reader.vector(2)
            extensions.append((extension_type, payload))
            result["extensions"].append({"type": extension_type, "length": len(payload),
                                         "data_base64": base64.b64encode(payload).decode("ascii")})
        seen: set[int] = set()
        for extension_type, payload in extensions:
            if extension_type in seen:
                raise _ParseError("duplicate_extension")
            seen.add(extension_type)
            if extension_type in (10, 13, 43, 11):
                field = {10: "supported_groups", 13: "signature_algorithms",
                         43: "supported_versions", 11: "ec_point_formats"}[extension_type]
                values = _ids(payload, 1 if extension_type in (11, 43) else 2,
                              1 if extension_type == 11 else 2)
                if not values:
                    raise _ParseError("empty_extension_vector")
                result[field] = values
            elif extension_type == 51:
                outer = _Reader(payload)
                shares = _Reader(outer.vector(2))
                outer.finish()
                result["key_share"] = []
                # 空 client_shares 是合法的 HRR 前置 offer；只验证边界，不硬编码组长度。
                while shares.offset < len(shares.data):
                    group = shares.number(2)
                    exchange = shares.vector(2)
                    if not exchange:
                        raise _ParseError("empty_key_exchange")
                    result["key_share"].append({"group": group, "key_exchange_length": len(exchange)})
            elif extension_type == 0:
                outer = _Reader(payload)
                names = _Reader(outer.vector(2))
                outer.finish()
                if not names.data:
                    raise _ParseError("empty_server_name_list")
                while names.offset < len(names.data):
                    name_type, name = names.number(1), names.vector(2)
                    if not name:
                        raise _ParseError("empty_server_name")
                    if name_type == 0:
                        if result["sni"] is not None or any(value < 33 or value > 126 for value in name):
                            raise _ParseError("invalid_server_name")
                        result["sni"] = name.decode("ascii")
            elif extension_type == 16:
                outer = _Reader(payload)
                protocols = _Reader(outer.vector(2))
                outer.finish()
                if not protocols.data:
                    raise _ParseError("empty_alpn_list")
                result["alpn_protocols"] = []
                while protocols.offset < len(protocols.data):
                    protocol = protocols.vector(1)
                    if not protocol:
                        raise _ParseError("empty_alpn_protocol")
                    text = protocol.decode("ascii") if all(32 <= value <= 126 for value in protocol) else None
                    result["alpn_protocols"].append({"text": text,
                                                     "base64": base64.b64encode(protocol).decode("ascii")})
        result["ja3"] = ja3_fingerprint(result["legacy_version"], result["cipher_suites"],
                                         [item["type"] for item in result["extensions"]],
                                         result["supported_groups"] or [], result["ec_point_formats"] or [])
    except _ParseError as error:
        result.update(parse_status="error", parse_error=str(error))
    return result


def capture_context_snapshot(raw: str, quota_source: str) -> tuple[dict[str, Any], str, str | None]:
    """冻结受支持的执行归属，缺失或冲突时不猜测版本。

    :param raw: CAPTURE_CONTEXT 私有 JSON。
    :param quota_source: 已有 Recorder 的 QUOTA_SOURCE，用于核对本次执行。
    :return: 白名单快照、状态和固定错误码；不返回原始配置或异常文本。
    """
    unknown: dict[str, Any] = {"schema": 1, "source": quota_source or None, "claude_code_version": None}
    if not raw:
        return unknown, "missing", "capture_context_missing"
    try:
        if len(raw) > 4096:
            raise ValueError
        data = json.loads(raw)
        if not isinstance(data, dict) or type(data.get("schema")) is not int or data["schema"] != 1:
            raise ValueError
        for key in ("source", "claude_code_version"):
            value = data.get(key)
            if not isinstance(value, str) or not value or len(value) > 512 or not value.isascii() or not value.isprintable():
                raise ValueError
        if quota_source and data["source"] != quota_source:
            return unknown, "source_mismatch", "capture_context_source_mismatch"
        context = {key: data[key] for key in ("schema", "source", "claude_code_version")}
        for key in ("run_id", "namespace", "work_id", "claude_code_version_source"):
            if key not in data:
                continue
            value = data[key]
            if not isinstance(value, str) or not value or len(value) > 128 or not value.isascii() or not value.isprintable():
                raise ValueError
            context[key] = value
        source_parts = context["source"].split(":")
        if "namespace" in context or "work_id" in context:
            if (context.get("namespace") not in ("projects", "warmup") or not context.get("work_id")
                    or "run_id" in context or source_parts[:2] != [context["namespace"], context["work_id"]]):
                raise ValueError
        elif not context.get("run_id") or source_parts[0] not in ("run", "continue"):
            raise ValueError
        elif source_parts[0] == "run" and source_parts[1:2] != [context["run_id"]]:
            raise ValueError
        return context, "ok", None
    except (ValueError, TypeError):
        return unknown, "invalid", "capture_context_invalid"


def append_private_jsonl(path: Path, record: dict[str, Any]) -> None:
    """在无链接的私有普通文件上追加一条记录，不覆盖既有证据。

    :param path: 已由执行目录派生的目标文件；父目录必须已存在。
    :param record: 含私有原始握手的 JSON 对象。
    :return: None；失败交给观察 hook 记录固定诊断，不能阻断业务转发。
    """
    target = Path(os.path.abspath(path))
    directory = os.open(target.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        # 逐级使用 dir_fd，连父目录链接也拒绝，避免先校验后被替换的路径竞态。
        for part in target.parent.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW
                             | os.O_NONBLOCK | os.O_CLOEXEC, 0o600, dir_fd=directory)
        try:
            status = os.fstat(descriptor)
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise OSError("tls_capture_not_private_file")
            os.fchmod(descriptor, 0o600)
            payload = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("tls_capture_write_incomplete")
                offset += written
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)
