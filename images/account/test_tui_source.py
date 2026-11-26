"""用实际 Unix socket 检查 sender 所有的事件源协议。"""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
from subprocess import run
import sys
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
import unittest
from uuid import uuid4

from tui_source import AccountSource, CHUNK_LIMIT, CONTROL_LIMIT, listen
from tui_messages import ModelResponseError


class InstalledSourceTests(unittest.TestCase):
    """复现正式 sender 的隔离解释器环境，校验构建后事件源的导入顺序。"""

    def test_source_imports_installed_modules_with_isolated_python(self):
        """从空目录启动，与正式入口相同的 -I 必须只按安装目录解析事件源依赖。@return 无。"""
        program = Path(__file__).resolve().with_name("tui_source.py")
        with TemporaryDirectory() as folder:
            result = run([sys.executable, "-I", "-c",
                          "import runpy, sys; runpy.run_path(sys.argv[1])", str(program)],
                         cwd=folder, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


class Driver:
    """记录准备、发送与释放。@param config 测试账号容量。"""

    def __init__(self, config):
        self.released = Event()
        self.submitted = 0
        self.available = True
        self.stream = True
        self.frames = None
        self.reservation = None
        self.quota_headers = None

    def ready(self):
        """返回驱动是否就绪。@return 就绪状态。"""
        return self.available

    def idle(self):
        """返回是否空闲。@return 空闲状态。"""
        return True

    def prepare(self, reservation, body, *, cancel_event):
        """预留一轮。@param reservation 预留。@param body 正文。@param cancel_event 断连。@return 自身句柄。"""
        if body == b"unsupported":
            raise ValueError("输入不支持")
        if body == b"full":
            raise TimeoutError
        if body == b"provider-wait":
            raise ModelResponseError(429, b"", source="local_provider_backoff", retry_after=31)
        if body == b"queue":
            while not cancel_event.is_set():
                time.sleep(0.01)
            self.released.set()
            raise TimeoutError
        self.kind = "new"
        self.body = body
        self.reservation = reservation
        return self

    def send(self, command):
        """提供两个模拟原始分片。@param command 已提交预留。@return 字节迭代器。"""
        self.submitted += 1
        if self.frames is not None:
            yield from self.frames
            return
        yield self.body
        yield b"x" * (CHUNK_LIMIT + 5)

    def close(self):
        """标记句柄归还。@return 无。"""
        self.released.set()


class SourceTests(unittest.TestCase):
    """通过真实发送器协议检查源的绑定、流和取消。"""

    def setUp(self):
        """创建私有运行目录和测试发布者。@return 无。"""
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "events.sock"
        self.config = self.path.with_suffix(".json")
        self.binding = {"account_id": 1, "environment_id": "env", "generation": 2, "release_id": "release"}
        self.document = {"binding": {**self.binding, "secret": "test-only"}, "tui_v2": {"max_reservations": 1}}
        self.config.write_text(json.dumps(self.document))
        self.driver = Driver({})
        self.source = AccountSource(self.config, lambda config: self.driver)
        self.server = self.enterContext(listen(self.path, self.source, os.getpid()))
        thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(self.server.shutdown)

    @contextmanager
    def _connect(self, action="bind", **overrides):
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(2)
            client.connect(str(self.path))
            with client.makefile("rwb") as stream:
                proof = {**self.binding, "protocol": 1, "nonce": str(uuid4()), **overrides}
                self._write(stream, {**proof, "action": action})
                yield proof, stream

    @staticmethod
    def _write(stream, fields):
        stream.write(json.dumps(fields).encode() + b"\n")
        stream.flush()

    def _prepare(self, proof, stream, body, *, headers=None, input_format=None, body_policy=None,
                 send_body=True, oauth_file=False, model_header_policy=False):
        self.assertTrue(json.loads(stream.readline())["ready"])
        identity = {**self.binding, "reservation_id": str(uuid4()), "continuation_only": False,
                    "deadline_unix_ms": int(time.time() * 1000) + 5000}
        self._write(stream, {**proof, "action": "prepare", "reservation": identity,
                             "body_sha256": hashlib.sha256(body).hexdigest(), "body_len": len(body),
                             **({"model_headers_len": len(headers)} if headers is not None else {}),
                             **({"model_header_policy": 1} if model_header_policy else {}),
                             **({"input_format": input_format} if input_format is not None else {}),
                             **({"oauth_file_protocol": 1} if oauth_file else {}),
                             **({"body_policy": body_policy} if body_policy is not None else {})})
        if send_body:
            stream.write(body)
            if headers is not None:
                stream.write(headers)
            stream.flush()
        return {"action": "send", "workspace": {}, "reservation_id": identity["reservation_id"]}

    def test_status_returns_original_receipt_idle_with_busy_peer(self):
        """源只验证同代原轮。旧驱动仅有全局空闲时保持原返回。@return 无。"""
        with self._connect("status", receipt={"principal_id": 9, "session_id": "A"}) as (_, stream):
            self.assertNotIn("receipt_idle", json.loads(stream.readline()))
        self.driver.idle = lambda: False
        self.driver.receipt_idle = lambda identity: identity == (1, "env", 2, 9, "A")
        for session, expected in (("A", True), ("B", False)):
            with self._connect("status", receipt={"principal_id": 9, "session_id": session}) as (_, stream):
                reply = json.loads(stream.readline())
                self.assertFalse(reply["idle"])
                self.assertIs(reply["receipt_idle"], expected)

    def test_native_dispatch_only_advertises_implemented_protocols(self):
        """原生候选只声明当前可用能力，旧投递继续原协商。@return 无。"""
        self.driver.managed_oauth = True
        self.driver.oauth_file_available = True
        for dispatch in (None, object()):
            self.driver.native_dispatch = dispatch
            self.driver.cli_handoff_capture = True
            with self.subTest(native=dispatch is not None), self._connect("status") as (_, stream):
                state = json.loads(stream.readline())
                self.assertEqual(state["oauth_file_protocol"], 1)
                self.assertEqual(state.get("capture_cli_submission_protocol"), 1 if dispatch is not None else None)
                for name in ("capture_http_protocol", "signature_repair_protocol"):
                    self.assertEqual(state.get(name), 1 if dispatch is None else None)
        for fields in ({"capture_http": True}, {"signature_repair": False},
                       {"capture_cli_submission": True, "capture_assembly": True}):
            with self.subTest(fields=fields), self._connect() as (proof, stream):
                command = self._prepare(proof, stream, b"{}")
                self.assertEqual(json.loads(stream.readline())["kind"], "new")
                self._write(stream, {**command, **fields, "account_token": "test-at"})
                self.assertEqual(stream.readline(), b"")
                self.assertEqual(self.driver.submitted, 0)

    def test_binding_before_body_and_real_readiness(self):
        """绑定或父进程不符时关闭，真实驱动未就绪时返回相应状态。@return 无。"""
        with self._connect(account_id=2) as (_, stream):
            self.assertEqual(stream.readline(), b"")
        self.driver.available = False
        with self._connect("status") as (_, stream):
            self.assertIs(json.loads(stream.readline())["ready"], False)
        self.server.sender_pid = -1
        # 拒绝发生在对端身份检查；内核可能在客户端写握手或读响应时通知断连。
        with self.assertRaises((BrokenPipeError, ConnectionResetError, EOFError)):
            with self._connect("status") as (_, stream):
                if not stream.readline():
                    raise EOFError

    def test_file_mode_is_selected_before_private_credential_delivery(self):
        """旧组合只交付 AT，新组合另收完整快照。@return 无。"""
        self.driver.managed_oauth = True
        self.driver.oauth_file_available = True
        send = self.driver.send
        observed = []

        def record(command):
            observed.append(command)
            return send(command)

        self.driver.send = record
        file = {"access_token": "synthetic-at", "refresh_token": "synthetic-rt",
                "expires_at": time.time_ns() // 1_000_000 + 30_000}
        for offer in (False, True):
            with self._connect() as (proof, stream):
                command = self._prepare(proof, stream, b"{}", oauth_file=offer)
                ready = json.loads(stream.readline())
                self.assertEqual(ready.get("oauth_file_protocol"), 1 if offer else None)
                if offer:
                    snapshot = json.dumps(file).encode()
                    self._write(stream, {**command, "oauth_file_len": len(snapshot)})
                    stream.write(snapshot)
                    stream.flush()
                else:
                    self._write(stream, {**command, "account_token": "legacy-at"})
                self.assertEqual(json.loads(stream.readline())["status"], 200)
                while True:
                    size, = struct.unpack("!I", stream.read(4))
                    if not size:
                        break
                    stream.read(size)
        self.assertEqual(observed[0]["account_token"], "legacy-at")
        self.assertNotIn("oauth_file", observed[0])
        self.assertEqual(observed[1]["oauth_file"], file)
        self.assertNotIn("account_token", observed[1])

    def test_send_chunking_and_single_reservation(self):
        """准备后按原记录提交，大分片按线上协议分块并保留内容。@return 无。"""
        body = "正文🌸".encode()
        quota = {"anthropic-ratelimit-unified-5h-utilization": "0.25",
                 "anthropic-ratelimit-unified-5h-reset": "2030-01-01T12:00:00Z"}
        self.driver.quota_headers = {**quota, "anthropic-ratelimit-unified-7d-reset": "x" * CONTROL_LIMIT}
        with self._connect() as (proof, stream):
            command = self._prepare(proof, stream, body)
            ready = json.loads(stream.readline())
            self.assertEqual((ready["kind"], ready["workspace_protocol"]), ("new", 1))
            self.assertEqual(self.driver.submitted, 0)
            self._write(stream, command)
            head = stream.readline()
            self.assertLessEqual(len(head), CONTROL_LIMIT)
            self.assertEqual(json.loads(head)["content_type"], "text/event-stream")
            self.assertEqual(json.loads(head)["quota_headers"], quota)
            collected = []
            while True:
                size, = struct.unpack("!I", stream.read(4))
                if not size:
                    break
                self.assertLessEqual(size, CHUNK_LIMIT)
                collected.append(stream.read(size))
            self.assertEqual(b"".join(collected), body + b"x" * (CHUNK_LIMIT + 5))
        self.assertEqual(self.driver.submitted, 1)

    def test_negotiated_model_headers_after_the_unchanged_body(self):
        """带长 beta 的后缀与冻结正文分别读取，非法头值在准备前拒绝。@return 无。"""
        headers = {"anthropic-version": "2023-06-01", "anthropic-beta": "feature-" + "a" * 5000}
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"original", headers=json.dumps(headers).encode(), input_format="claude_code")
            self.assertEqual(json.loads(stream.readline())["model_headers_protocol"], 1)
            self.assertEqual(self.driver.body, b"original")
            self.assertEqual(self.driver.reservation["model_headers"], headers)
            self.assertEqual(self.driver.reservation["input_format"], "claude_code")
        for invalid in ({"authorization": "test"}, {"anthropic-beta": "first\r\nsecond"},
                        {"anthropic-version": 1}, {"anthropic-version": "测试"}, []):
            with self.subTest(invalid=invalid), self._connect() as (proof, stream):
                self._prepare(proof, stream, b"unused", headers=json.dumps(invalid).encode())
                self.assertEqual(stream.readline(), b"")
                self.assertEqual(self.driver.body, b"original")
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"unused", input_format="unexpected", send_body=False)
            self.assertEqual(stream.readline(), b"")
            self.assertEqual(self.driver.body, b"original")
        extended = {**headers, "accept-language": "café", "anthropic-dangerous-direct-browser-access": "false"}
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"unused", headers=json.dumps(extended).encode())
            self.assertEqual(stream.readline(), b"")
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"extended", headers=json.dumps(extended).encode(),
                          model_header_policy=True)
            self.assertEqual(json.loads(stream.readline())["model_header_policy_protocol"], 1)
            self.assertEqual(self.driver.reservation["model_headers"], extended)
            self.assertEqual(self.driver.body, b"extended")

    def test_policy_arrives_only_in_verified_prepare(self):
        """源端仅接收完整合法的本轮设置，仍向驱动交付原字节。@return 无。"""
        policy = {"sub2api": True, "ttl": "5m", "adaptive": False}
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"original", body_policy=policy)
            self.assertEqual(json.loads(stream.readline())["body_policy_protocol"], 1)
            self.assertEqual(self.driver.reservation["body_policy"], policy)
            self.assertEqual(self.driver.body, b"original")
        for invalid in ([], {"ttl": "off"}, {**policy, "adaptive": 1},
                        {**policy, "ttl": "auto"}, {**policy, "extra": True}):
            with self.subTest(invalid=invalid), self._connect() as (proof, stream):
                # 声明非空正文但仅写控制帧，明确要求在对端等待正文前返回 EOF。
                self._prepare(proof, stream, b"unused", body_policy=invalid, send_body=False)
                self.assertEqual(stream.readline(), b"")
                self.assertEqual(self.driver.body, b"original")

    def _nonstream(self, frames, *, expected_headers=None):
        self.driver.stream = False
        self.driver.frames = frames
        with self._connect() as (proof, stream):
            command = self._prepare(proof, stream, b"{}")
            self.assertEqual(json.loads(stream.readline())["kind"], "new")
            self._write(stream, command)
            head = json.loads(stream.readline())
            self.assertEqual(head["content_type"], "application/json")
            self.assertEqual(head["message_id_mode"], "gateway")
            for key, value in (expected_headers or {}).items():
                self.assertEqual(head[key], value)
            body = bytearray()
            while size := int.from_bytes(stream.read(4), "big"):
                self.assertLessEqual(size, CHUNK_LIMIT)
                body.extend(stream.read(size))
            return head["status"], json.loads(body)

    def test_json_uses_same_single_submission_and_terminal_errors(self):
        """检查非流式 JSON 完整返回、源错误及缺终态时的标准错误信封。@return 无。"""
        opening = b'data: {"type":"message_start","message":{"type":"message","id":"msg_source","content":[],"role":"assistant","usage":{"input_tokens":5}}}\n\n'
        ending = b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":7}}\n\n'
        stop = b'data: {"type":"message_stop"}\n\n'
        error = b'event: error\ndata: {"type":"error","error":{"type":"overloaded_error","message":"busy"}}\n\n'
        self.driver.quota_headers = {"anthropic-ratelimit-unified-7d-utilization": "0.43",
                                     "anthropic-ratelimit-unified-7d-reset": "2030-01-08T12:00:00Z"}
        status, msg = self._nonstream(
            [opening, ending, stop], expected_headers={"quota_headers": self.driver.quota_headers})
        self.driver.quota_headers = None
        self.assertEqual((status, msg["id"], msg["usage"]), (200, "msg_source", {"input_tokens": 5, "output_tokens": 7}))
        self.assertEqual(self._nonstream([b": ping\n\n", error]), (529, {"type": "error", "error": {
            "type": "overloaded_error", "message": "busy"}}))
        for frames in ([opening], [opening, error]):
            _, rejected = self._nonstream(frames)
            self.assertEqual(rejected["type"], "error")
        self.assertEqual(self.driver.submitted, 4)

    def test_http_failure_before_first_event_preserves_status_in_both_modes(self):
        """同一上游首帧前的失败在两种响应模式均保留 HTTP 状态和标准错误。@return 无。"""
        upstream_error = {"type": "error", "error": {"type": "rate_limit_error", "message": "fixture busy"}}

        quota = {"anthropic-ratelimit-unified-5h-status": "rejected"}

        def failed():
            yield from ()
            raise ModelResponseError(429, json.dumps(upstream_error).encode(),
                                     source="managed_oauth_http", retry_after=42, quota_headers=quota)

        expected = {"status": 429, "error_source": "managed_oauth_http", "retry_after": 42, "quota_headers": quota}
        self.assertEqual(self._nonstream(failed(), expected_headers=expected), (429, upstream_error))
        self.driver.stream = True
        self.driver.frames = failed()
        with self._connect() as (proof, stream):
            command = self._prepare(proof, stream, b"{}")
            self.assertEqual(json.loads(stream.readline())["kind"], "new")
            self._write(stream, command)
            head = json.loads(stream.readline())
            self.assertEqual({key: head[key] for key in expected}, expected)
            size = int.from_bytes(stream.read(4), "big")
            self.assertEqual(json.loads(stream.read(size)), upstream_error)
            self.assertEqual(int.from_bytes(stream.read(4), "big"), 0)
        self.assertEqual(self.driver.submitted, 2)

    def test_private_error_keeps_policy_fields_and_upstream_origin(self):
        """真实模型事件发生于非流式聚合时，只有分类字段穿过私有链路。@return 无。"""
        upstream = {"upstream_code": "cyber_policy", "internal": "private"}
        frame = b"event: error\ndata: " + json.dumps({"type": "error", "error": upstream}).encode() + b"\n\n"
        status, payload = self._nonstream([frame], expected_headers={"error_source": "local_provider_event"})
        self.assertEqual(status, 502)
        self.assertEqual(payload["_tui_policy_evidence"]["error"], {"upstream_code": "cyber_policy"})
        self.assertEqual(payload["error"]["type"], "api_error")
        self.assertEqual(self.driver.submitted, 1)

    def test_cancel_unsupported_and_changed_binding_submit_zero(self):
        """覆盖显式拒绝、等待提交时断开以及提交前绑定被替换。@return 无。"""
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"unsupported")
            self.assertEqual(json.loads(stream.readline())["error"], "unsupported_input")
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"provider-wait")
            head = json.loads(stream.readline())
            self.assertEqual((head["error"], head["retry_after"]), ("local_provider_backoff", 31))
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"cancel")
            self.assertEqual(json.loads(stream.readline())["kind"], "new")
        self.assertTrue(self.driver.released.wait(2))
        with self._connect() as (proof, stream):
            command = self._prepare(proof, stream, b"changed")
            self.assertEqual(json.loads(stream.readline())["kind"], "new")
            self.document["binding"]["secret"] += "-changed"
            self.config.write_text(json.dumps(self.document))
            self._write(stream, command)
            self.assertEqual(stream.readline(), b"")
        self.assertEqual(self.driver.submitted, 0)

    def test_disconnecting_during_prepare_releases_queue_without_send(self):
        """满额提示与队列中的取消均在模型调用前处理。@return 无。"""
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"full")
            self.assertEqual(json.loads(stream.readline())["error"], "capacity")
        with self._connect() as (proof, stream):
            self._prepare(proof, stream, b"queue")
        self.assertTrue(self.driver.released.wait(2))
        self.assertEqual(self.driver.submitted, 0)

    def test_capacity_update_keeps_prepared_session(self):
        """容量热调整时，已冻结的同一绑定仍能完成 send。@return 无。"""
        with self._connect() as (proof, stream):
            command = self._prepare(proof, stream, b"held")
            self.assertEqual(json.loads(stream.readline())["kind"], "new")
            self.document["tui_v2"]["max_reservations"] = 2
            self.config.write_text(json.dumps(self.document))
            with self._connect("status") as (_, status):
                self.assertIs(json.loads(status.readline())["ready"], True)
            self.assertFalse(self.driver.released.is_set())
            self._write(stream, command)
            self.assertEqual(json.loads(stream.readline())["status"], 200)
        self.assertEqual(self.driver.submitted, 1)


if __name__ == "__main__":
    unittest.main()
