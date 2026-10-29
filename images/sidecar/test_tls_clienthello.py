"""离线验证握手结构、标准 JA3、执行归属和私有证据文件边界。"""

import base64
import hashlib
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from tls_clienthello import MAX_CLIENTHELLO_BYTES, append_private_jsonl, capture_context_snapshot, ja3_fingerprint, parse_clienthello


def _vector(values: list[int], prefix: int = 2, width: int = 2) -> bytes:
    payload = b"".join(value.to_bytes(width, "big") for value in values)
    return len(payload).to_bytes(prefix, "big") + payload


def _body(extensions: list[tuple[int, bytes]] | None = None, *, version: int = 771,
          ciphers: list[int] | None = None) -> bytes:
    result = version.to_bytes(2, "big") + b"R" * 32 + b"\x00" + _vector(ciphers or [4865, 4866]) + b"\x01\x00"
    if extensions is not None:
        payload = b"".join(kind.to_bytes(2, "big") + len(data).to_bytes(2, "big") + data for kind, data in extensions)
        result += len(payload).to_bytes(2, "big") + payload
    return result


def _server_name(host: str) -> bytes:
    name = host.encode("ascii")
    payload = b"\x00" + len(name).to_bytes(2, "big") + name
    return len(payload).to_bytes(2, "big") + payload


class ClientHelloParserTests(unittest.TestCase):
    """解析真实字节形状，验证原序事实和不可伪造的失败状态。"""

    def test_official_ja3_vectors(self) -> None:
        """两条 Salesforce 官方向量独立约束五字段及 MD5。:return: None。"""
        cases = [
            (769, [47, 53, 5, 10, 49161, 49162, 49171, 49172, 50, 56, 19, 4], [0, 10, 11], [23, 24, 25], [0],
             "769,47-53-5-10-49161-49162-49171-49172-50-56-19-4,0-10-11,23-24-25,0", "ada70206e40642a3e4461f35503241d5"),
            (769, [4, 5, 10, 9, 100, 98, 3, 6, 19, 18, 99], [], [], [],
             "769,4-5-10-9-100-98-3-6-19-18-99,,,", "de350869b8c85de67a350c8d186f11e6"),
        ]
        for version, ciphers, extensions, groups, formats, text, digest in cases:
            with self.subTest(digest=digest):
                self.assertEqual({"string": text, "md5": digest}, ja3_fingerprint(version, ciphers, extensions, groups, formats))

    def test_order_unknown_ids_grease_and_opaque_alpn_are_preserved(self) -> None:
        """GREASE 仅从 JA3 投影移除，未知组和 ALPN 原始字节可复核。:return: None。"""
        shares = b"\x0a\x0a\x00\x01X" + b"\xfe\x30\x00\x05abcde"
        extensions = [(0x2A2A, b""), (43, _vector([772, 771], prefix=1)), (65000, b"opaque"),
                      (13, _vector([0x3A3A, 2052, 1027])), (10, _vector([0x1A1A, 29, 4588])),
                      (51, len(shares).to_bytes(2, "big") + shares),
                      (16, b"\x00\x05\x02h2\x01\xff"), (11, _vector([0], prefix=1, width=1)),
                      (0, _server_name("api.anthropic.com"))]
        raw = _body(extensions, ciphers=[0x0A0A, 4865, 4866])
        result = parse_clienthello(raw)
        self.assertEqual("ok", result["parse_status"])
        self.assertEqual(771, result["legacy_version"])
        self.assertEqual([0x0A0A, 4865, 4866], result["cipher_suites"])
        self.assertEqual([kind for kind, _ in extensions], [item["type"] for item in result["extensions"]])
        self.assertEqual([payload for _, payload in extensions],
                         [base64.b64decode(item["data_base64"]) for item in result["extensions"]])
        self.assertEqual([0x3A3A, 2052, 1027], result["signature_algorithms"])
        self.assertEqual([0x1A1A, 29, 4588], result["supported_groups"])
        self.assertEqual([772, 771], result["supported_versions"])
        self.assertEqual([{"group": 0x0A0A, "key_exchange_length": 1},
                          {"group": 0xFE30, "key_exchange_length": 5}], result["key_share"])
        self.assertEqual([{"text": "h2", "base64": "aDI="}, {"text": None, "base64": "/w=="}], result["alpn_protocols"])
        self.assertEqual("api.anthropic.com", result["sni"])
        self.assertEqual("771,4865-4866,43-65000-13-10-51-16-11-0,29-4588,0", result["ja3"]["string"])
        self.assertEqual("clienthello_body", result["raw_format"])
        self.assertFalse(result["tls_record_preserved"])
        self.assertFalse(result["raw_truncated"])
        self.assertEqual(raw, base64.b64decode(result["raw_base64"]))
        self.assertEqual(len(raw), result["raw_bytes"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), result["raw_sha256"])

    def test_missing_extensions_and_empty_key_share_are_distinct(self) -> None:
        """旧 TLS 缺扩展正常，合法空 client_shares 也不是解析失败。:return: None。"""
        missing = parse_clienthello(_body())
        self.assertEqual("ok", missing["parse_status"])
        self.assertEqual("771,4865-4866,,,", missing["ja3"]["string"])
        self.assertIsNone(missing["key_share"])
        empty = parse_clienthello(_body([(51, b"\x00\x00")]))
        self.assertEqual("ok", empty["parse_status"])
        self.assertEqual([], empty["key_share"])

    def test_every_truncated_mandatory_prefix_keeps_raw_and_has_no_ja3(self) -> None:
        """逐字节截断强制字段均失败，不能从不完整前缀补造指纹。:return: None。"""
        raw = _body()
        for length in range(len(raw)):
            with self.subTest(length=length):
                result = parse_clienthello(raw[:length])
                self.assertEqual("error", result["parse_status"])
                self.assertIsNone(result["ja3"])
                self.assertEqual(raw[:length], base64.b64decode(result["raw_base64"]))

    def test_malformed_vectors_duplicate_extensions_and_tail_keep_evidence(self) -> None:
        """已知向量、重复扩展及尾部长度不合法时保留原字节而拒绝完整解析。:return: None。"""
        cases = [
            _body([(13, b"\x00\x03\x04\x03\x08")]),
            _body([(10, b"\x00\x04\x00\x1d")]),
            _body([(43, b"\x03\x03\x04\x03")]),
            _body([(11, b"\x00")]),
            _body([(51, b"\x00\x05\x00\x1d\x00\x02X")]),
            _body([(51, b"\x00\x04\x00\x1d\x00\x00")]),
            _body([(16, b"\x00\x01\x00")]),
            _body([(0, b"\x00\x04\x00\x00\x02X")]),
            _body([(65000, b"one"), (65000, b"two")]),
            _body([]) + b"unclaimed",
        ]
        for raw in cases:
            with self.subTest(raw_sha256=hashlib.sha256(raw).hexdigest()):
                result = parse_clienthello(raw)
                self.assertEqual("error", result["parse_status"])
                self.assertIsNone(result["ja3"])
                self.assertEqual(raw, base64.b64decode(result["raw_base64"]))
                self.assertTrue(result["parse_error"])
        duplicate = parse_clienthello(cases[-2])
        self.assertEqual(2, len(duplicate["extensions"]))

    def test_oversize_is_explicit_and_preserves_full_length_and_hash(self) -> None:
        """异常超限输入仅保存明确标记的前缀，不冒充完整握手。:return: None。"""
        raw = b"X" * (MAX_CLIENTHELLO_BYTES + 1)
        result = parse_clienthello(raw)
        self.assertEqual("oversize", result["parse_status"])
        self.assertTrue(result["raw_truncated"])
        self.assertEqual(len(raw), result["raw_bytes"])
        self.assertEqual(MAX_CLIENTHELLO_BYTES, result["raw_saved_bytes"])
        self.assertEqual(raw[:MAX_CLIENTHELLO_BYTES], base64.b64decode(result["raw_base64"]))
        self.assertEqual(hashlib.sha256(raw).hexdigest(), result["raw_sha256"])
        self.assertIsNone(result["ja3"])


class CaptureContextTests(unittest.TestCase):
    """执行版本只来自固定快照，归属冲突不能传播错误标签。"""

    def test_supported_run_continue_and_work_contexts_are_whitelisted(self) -> None:
        """保留真实 run 或 work 身份，配置中的未知材料不进入快照。:return: None。"""
        for source, identity in [("run:rid:1", {"run_id": "rid"}), ("continue:sid:2", {"run_id": "rid"}),
                                 ("projects:work:3", {"namespace": "projects", "work_id": "work"}),
                                 ("warmup:work:4", {"namespace": "warmup", "work_id": "work"})]:
            with self.subTest(source=source):
                payload = {"schema": 1, "source": source, "claude_code_version": "2.1.303", **identity,
                           "claude_code_version_source": "account", "token": {"raw": "canary"}}
                context, status, error = capture_context_snapshot(json.dumps(payload), source)
                self.assertEqual("ok", status)
                self.assertIsNone(error)
                self.assertEqual({key: value for key, value in payload.items() if key != "token"}, context)

    def test_missing_corrupt_and_wrong_source_do_not_guess_version(self) -> None:
        """旧入口或坏快照明确未知；另一执行的标签不被静默接受。:return: None。"""
        valid = {"schema": 1, "source": "run:other:0", "claude_code_version": "2.1.303", "run_id": "other"}
        for raw, expected in [("", "missing"), ("[]", "invalid"), ("broken", "invalid"),
                              ("X" * 4097, "invalid"), (json.dumps(valid), "source_mismatch")]:
            with self.subTest(status=expected):
                context, status, error = capture_context_snapshot(raw, "run:current:1")
                self.assertEqual(expected, status)
                self.assertEqual("run:current:1", context["source"])
                self.assertIsNone(context["claude_code_version"])
                self.assertTrue(error)
        invalid = {**valid, "source": "projects:work:1", "namespace": "projects", "work_id": "work"}
        self.assertEqual("invalid", capture_context_snapshot(json.dumps(invalid), invalid["source"])[1])


class PrivateTLSFileTests(unittest.TestCase):
    """含恢复材料的文件不能经权限或链接边界泄漏。"""

    def setUp(self) -> None:
        """创建隔离临时目录。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.path = self.base / "tls_clienthello.jsonl"

    def test_private_create_and_existing_file_append_preserve_old_bytes(self) -> None:
        """创建权限固定 0600，既有证据仅追加且可收紧旧权限。:return: None。"""
        previous_umask = os.umask(0o022)
        try:
            append_private_jsonl(self.path, {"attempt": 1})
        finally:
            os.umask(previous_umask)
        old = self.path.read_bytes()
        self.assertEqual(0o600, stat.S_IMODE(self.path.stat().st_mode))
        self.path.chmod(0o644)
        append_private_jsonl(self.path, {"attempt": 2})
        self.assertTrue(self.path.read_bytes().startswith(old))
        self.assertEqual([{"attempt": 1}, {"attempt": 2}], [json.loads(line) for line in self.path.read_text().splitlines()])
        self.assertEqual(0o600, stat.S_IMODE(self.path.stat().st_mode))

    def test_file_parent_ancestor_symlinks_and_hardlinks_are_refused(self) -> None:
        """链接目标及原证据字节均保持，不只检查最末级文件名。:return: None。"""
        target = self.base / "target"
        target.write_bytes(b"preserved")
        self.path.symlink_to(target)
        with self.assertRaises(OSError):
            append_private_jsonl(self.path, {"raw": "private"})
        self.path.unlink()
        os.link(target, self.path)
        with self.assertRaises(OSError):
            append_private_jsonl(self.path, {"raw": "private"})
        self.path.unlink()
        directory = self.base / "real"
        (directory / "child").mkdir(parents=True)
        (self.base / "alias").symlink_to(directory, target_is_directory=True)
        for path in (self.base / "alias" / "new.jsonl", self.base / "alias" / "child" / "new.jsonl"):
            with self.assertRaises(OSError):
                append_private_jsonl(path, {"raw": "private"})
        self.assertEqual(b"preserved", target.read_bytes())
        self.assertFalse((directory / "new.jsonl").exists())

    def test_fifo_does_not_block_observer(self) -> None:
        """非普通文件立即失败，不能把观察 hook 卡在 FIFO 打开上。:return: None。"""
        os.mkfifo(self.path)
        with self.assertRaises(OSError):
            append_private_jsonl(self.path, {"raw": "private"})


if __name__ == "__main__":
    unittest.main()
