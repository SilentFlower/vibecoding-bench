"""验证 sender 内交互适配的输入保真边界、工具归属、增量和容量。"""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import closing
from email.message import Message
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
import time
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services/orchestrator"))
from tui_capacity import TuiCapacity
from tui_reconnect import ReceiptCheckpoints
from tui_session import SessionDriver, _install_mod
from tui_messages import (
    ModelResponseError,
    SubagentAmbiguousError,
    SubagentBindingError,
    SubagentCapacityError,
    WireStep,
    encode,
    history_digest,
    input_message,
    provider_session,
    tool_receipts,
    wire_events,
)


class SessionTests(unittest.TestCase):
    """固定版结构化事件和账号内原生进程预留的回归。"""

    def test_protocol_headers_use_current_sdk_and_reject_unsupported_beta(self):
        """普通 API 校验同轮原生能力，协议值按准入结果覆盖默认值。@return 无。"""
        identity = {
            **self._identity("header-test"), "model_header_policy": 1,
            "model_headers": {"accept": "text/plain", "anthropic-beta": "sdk-a"},
        }
        sdk = {"Accept": "application/json", "anthropic-beta": "sdk-a,sdk-b",
               "X-Stainless-OS": "sdk-os", "Authorization": "synthetic"}
        with closing(self._driver(1)) as driver, closing(driver.prepare(identity, encode(self._body()))) as handle:
            self.assertEqual(handle.actor._protocol_headers(sdk, handle), {
                "accept": "text/plain", "anthropic-beta": "sdk-a,sdk-b", "x-stainless-os": "sdk-os",
            })
            handle.model_headers["anthropic-beta"] = "extra"
            actor = handle.actor
            actor.step = SimpleNamespace(native=("turn", 1), claimed=False)
            driver.launcher = SimpleNamespace(local_model_response=Mock())
            with patch.object(actor, "_main_request", return_value=True), self.assertRaises(ModelResponseError) as caught:
                actor.serve_model(SimpleNamespace(headers=sdk), {})
            self.assertEqual(caught.exception.status, 422)
            self.assertEqual(json.loads(caught.exception.private_body)["error"]["code"], "unsupported_parameter")
            self.assertFalse(actor.step.claimed)
            driver.launcher.local_model_response.assert_not_called()

    def test_native_dispatch_uses_one_authorized_frozen_submission(self):
        """并发的同轮种子只能认领一次，错误账号授权及过期凭据保留原语义。@return 无。"""
        raw = encode(self._body())
        with closing(self._driver()) as driver, closing(driver.prepare(self._identity("native-send"), raw)) as handle:
            driver.managed_oauth = True
            driver.native_dispatch = Mock()
            actor = handle.actor
            actor.oauth_file = True
            actor.step = SimpleNamespace(native=("turn", 1), native_model="chosen", claimed=False)
            handle.account_token = "synthetic-local-token"
            handle.expires_at = int(time.time() * 1000) + 5000
            request = {**self._body(), "messages": [{"role": "user", "content": [
                {"type": "text", "text": "<system-reminder>\nprompt.submit hook additional context: "
                 + actor.guard_text + "\n</system-reminder>"}]}]}
            wrong = Mock(headers={"Authorization": "Bearer different"})
            actor.serve_model(wrong, request)
            wrong.send_error.assert_called_once_with(409, "No pending model step")
            self.assertFalse(actor.step.claimed)
            failed = Mock(headers={"Authorization": "Bearer " + handle.account_token})
            expires_at, handle.expires_at = handle.expires_at, 1
            with self.assertRaises(ModelResponseError) as expired:
                actor.serve_model(failed, request)
            self.assertEqual(expired.exception.status, 503)
            handle.expires_at = expires_at
            driver.native_dispatch.assert_not_called()
            peers = [Mock(headers=failed.headers) for _ in range(2)]
            with ThreadPoolExecutor(2) as pool:
                list(pool.map(lambda peer: actor.serve_model(peer, request), peers))
            driver.native_dispatch.assert_called_once()
            self.assertEqual(sum(peer.send_error.call_count for peer in peers), 1)
            submission = driver.native_dispatch.call_args.args[2]
            self.assertIs(submission.step, actor.step)
            self.assertEqual(submission.body, raw)
            self.assertNotIn(handle.account_token, repr(submission))
            self.assertIsNone(handle.raw)

    def test_non_stream_accept_uses_sdk_for_upstream_sse(self):
        """公开非流式请求向模型取流时使用同轮 SDK 的 Accept。@return 无。"""
        for explicit in (False, None):
            with self.subTest(stream=explicit), closing(self._driver(1)) as driver:
                body = self._body()
                if explicit is None:
                    del body["stream"]
                else:
                    body["stream"] = explicit
                identity = {**self._identity("accept-json"), "model_header_policy": 1,
                            "model_headers": {"accept": "application/json;q=0.9"}}
                with closing(driver.prepare(identity, encode(body))) as handle:
                    self.assertFalse(handle.stream)
                    self.assertIs(json.loads(handle.raw)["stream"], True)
                    self.assertEqual(handle.actor._protocol_headers({"Accept": "application/json"}, handle),
                                     {"accept": "application/json"})
                    self.assertNotIn("accept", handle.actor._protocol_headers({}, handle))

    def test_provider_session_rewrites_only_user_id_and_session_header(self):
        """发送副本保留缓存前缀、工具 ID、原始字节及其他元数据。@return 无。"""
        original = "a1234567-1234-4123-8123-123456789abc"
        target = "b1234567-1234-4123-8123-123456789abc"
        identity = encode({"session_id": original, "device_id": "合成", "extra": 1})
        body = (
            b' { "metadata" : { "trace": 23, "user\\u005fid" : '
            + encode(identity.decode())
            + b' }, "tools": [ {"name": "Read","cache_control": {"ttl":"1h"}} ],'
            + b' "messages": [{"role":"assistant","content":[{"type":"tool_use",'
            + b'"id":"original-tool-id","name":"Read","input":{"file_path":"local"}}]}] }\n'
        )
        mapped, headers = provider_session(body, {"anthropic-beta": "example"}, original, target)
        self.assertEqual(mapped, body.replace(original.encode(), target.encode()))
        self.assertEqual(headers, {"anthropic-beta": "example", "x-claude-code-session-id": target})
        self.assertEqual(provider_session(body, {}, original, None), (body, {}))
        self.assertEqual(provider_session(body, {}, original, original),
                         (body, {"x-claude-code-session-id": original}))
        header_only = b'{"system":"metadata","messages": []}'
        self.assertEqual(provider_session(header_only, {}, original, target),
                         (header_only, {"x-claude-code-session-id": target}))
        with self.assertRaisesRegex(ValueError, "预留会话"):
            provider_session(body, {}, target, original)
        with self.assertRaises(ValueError):
            provider_session(body, {}, original, "arbitrary")

    @staticmethod
    def _body():
        return {
            "model": "chosen",
            "max_tokens": 128,
            "stream": True,
            "messages": [{"role": "user", "content": "你好"}],
        }

    @staticmethod
    def _identity(session):
        return {
            "account_id": 1,
            "environment_id": "e",
            "generation": 1,
            "principal_id": 9,
            "session_id": session,
            "continuation_only": False,
            "deadline_unix_ms": int(1000 * (time.time() + 5)),
        }

    def test_restore_original_receipt_after_source_restart(self):
        """持久依据绑定原身份、参数和结果，恢复进程沿用原子代理工作区。@return 无。"""
        identity = self._identity("external")
        body = self._body()
        group = [{"type": "tool_use", "id": "tool_a", "name": "Bash", "input": {"command": "true"}}]
        raw = self._returning(body, group, "tool_a")
        child = {**identity, "agent_hint": "child", "continuation_only": True}
        key = (1, "e", 1, 9, "external", "child")
        with TemporaryDirectory() as root, closing(self._driver()) as first:
            first.checkpoints = ReceiptCheckpoints(root)
            # 建立与真实子代理相同的身份、原声明和已接收的工具结果，再模拟进程退出。
            with closing(first.prepare(identity, encode(body))) as initial:
                actor = initial.actor
                first.sessions.pop(actor.identity)
                actor.identity = key
                actor.reservation = {**identity, "session_id": "gateway-tools-private-child"}
                first.sessions[key] = actor
                self._offered(initial, *group)
            with closing(first.prepare(child, raw)) as live:
                self.assertEqual(live.kind, "continuation")
                live.send({"account_token": "fixture"})
            first.close()
            with closing(self._driver()) as restarted:
                restarted.checkpoints = ReceiptCheckpoints(root)
                for other in ({**child, "principal_id": 10}, {**child, "agent_hint": "sibling"},
                              {**child, "generation": 2}):
                    with self.assertRaises(ValueError):
                        restarted.prepare(other, raw)
                changed = json.loads(raw)
                changed["messages"][-1]["content"][0]["content"] = "different"
                with self.assertRaises(ValueError):
                    restarted.prepare(child, encode(changed))
                with self.assertRaises(ValueError):
                    restarted.prepare(child, self._returning({**body, "max_tokens": 256}, group, "tool_a"))
                with closing(restarted.prepare(child, raw)) as restored:
                    self.assertEqual(restored.kind, "recovered")
                    self.assertEqual(restored.actor.reservation["session_id"], "gateway-tools-private-child")
                    self.assertEqual(restored.answers["tool_a"]["content"], "合成回执")
                    with self.assertRaises(ValueError):
                        restarted.prepare(child, raw)
                    self.assertTrue(restarted.checkpoints.submit(
                        key, restored.actor.receipt_revision, restored.request_digest, True
                    ))
                with self.assertRaises(ValueError):
                    restarted.prepare(child, raw)

    def test_restore_native_receipt_reconstructs_original_root_policy_and_tool_names(self):
        """恢复只接受同一根轮配置，保留本轮回执内容及原生工具名。@return 无。"""
        identity = {**self._identity("external-native"), "native_cold_history": True}
        tool = {"name": "LookupNote", "input_schema": {"type": "object"}}
        body = {**self._body(), "system": "原轮指令", "tools": [tool]}
        group = [{"type": "tool_use", "id": "tool_native", "name": tool["name"], "input": {}}]
        returned = json.loads(self._returning(body, group, "tool_native"))
        text_result = [{"type": "text", "text": "合成回执"}]
        returned["messages"][-1]["content"][0]["content"] = text_result
        with TemporaryDirectory() as root, closing(self._driver()) as first:
            first.managed_oauth = True
            first.checkpoints = ReceiptCheckpoints(root)
            with closing(first.prepare(identity, encode(body))) as initial:
                plan = initial.actor.cold_history
                self.assertIsNotNone(plan)
                self._offered(initial, *group)
            first.close()
            continuation = {**identity, "continuation_only": True, "client_system_prompt_policy": "user_reminder"}
            with closing(self._driver()) as restarted:
                restarted.managed_oauth = True
                restarted.checkpoints = ReceiptCheckpoints(root)
                with self.assertRaisesRegex(ValueError, "unsupported_parameter"):
                    restarted.prepare(continuation, encode({**returned, "system": "替换已冻结的指令"}))
                with closing(restarted.prepare(continuation, encode(returned))) as handle:
                    self.assertEqual(handle.kind, "recovered")
                    self.assertEqual(handle.actor.cold_history, plan)
                    recovered = handle.actor.recovery_history
                    self.assertEqual(recovered.history[-2]["content"][0]["name"], "mcp__flower__LookupNote")
                    self.assertEqual(recovered.history[-1]["content"][0]["content"], text_result)
                    self.assertEqual(recovered.system_argument(), ("--append-system-prompt-file", "原轮指令"))

    def test_new_tool_immediately_revokes_old_recovery(self):
        """新指令首帧可能已经到达客户端，拒绝重新生成上一份回执。@return 无。"""
        body, identity = self._body(), self._identity("tool-start")
        group = [{"type": "tool_use", "id": "first", "name": "Bash", "input": {}}]
        with closing(self._driver()) as driver:
            first = driver.prepare(identity, encode(body))
            actor = self._offered(first, *group)
            step = WireStep([{"name": "Bash"}])
            step.observe({"type": "message_start", "message": {}})
            actor._observe(step, {"type": "content_block_start", "index": 0, "content_block":
                                  {"type": "tool_use", "name": "Bash", "id": "second", "input": {}}})
            actor.abort()
            driver._retire(actor)
            with self.assertRaisesRegex(ValueError, "outstanding_tool"):
                driver.prepare(identity, self._returning(body, group, "first"))

    def test_mod_install_preserves_private_directory_mode(self):
        """即使镜像安装目录为 0755，也严格保留每次原生启动所需的私有目录模式。@return 无。"""
        with TemporaryDirectory() as root:
            parent = Path(root)
            source, private = parent / "package", parent / "session"
            source.mkdir()
            source.chmod(0o755)
            private.mkdir(mode=0o700)
            for name in ("hooks", ".claude-plugin"):
                (source / name).mkdir()
                (source / name / "example").write_text("fixture")
            _install_mod(source, private)
            self.assertEqual(private.stat().st_mode & 0o777, 0o700)
            _install_mod(source, private)
            self.assertEqual(private.stat().st_mode & 0o777, 0o700)
            self.assertEqual((private / "hooks/example").read_text(), "fixture")

    def test_frozen_fields_and_format_are_decided_per_public_request(self):
        """完整冻结系统分块、工具、缓存位置与模型选项；非流式仅调整内部取流方式。@return 无。"""
        body = {
            **self._body(),
            "system": [
                {"type":"text","text":"You are Claude Code, Anthropic's official CLI for Claude."},
                {
                    "type": "text",
                    "text": "α",
                    "cache_control": {"type": "ephemeral", "ttl": "1h"},
                }
            ],
            "metadata": {"user_id": json.dumps({"device_id":"0"*64,"account_uuid":"",
                "session_id":"00000000-0000-0000-0000-000000000001"}), "extra": "客户附加信息"},
            "output_config": {
                "effort": "high",
                "format": {"type": "json_schema", "schema": {"type": "object"}},
            },
            "thinking": {"type": "adaptive"},
            "temperature": 0.75,
            "safeguards": [{"type": "dangerous_tool_use"}],
            "tools": [
                {
                    "name": n,
                    "description": "自定义",
                    "input_schema": {
                        "type": "object",
                        "properties": {"proxy_url": {"type": "string"}},
                    },
                }
                for n in ("Read", "Novel")
            ],
        }
        raw = json.dumps(body, indent=2, ensure_ascii=False).encode()
        parsed, stream, wire = input_message(raw, native=True)
        self.assertEqual((parsed, stream, wire), (body, True, raw))
        body.pop("stream")
        parsed, stream, wire = input_message(encode(body), native=True)
        self.assertFalse(stream)
        self.assertEqual(json.loads(wire), {**body, "stream": True})
        body["future_native_extension"] = {"nested": "合法"}
        with self.assertRaises(ValueError):
            input_message(encode(body))
        self.assertEqual(input_message(encode(body), native=True)[0], body)

    def test_missing_and_finite_output_budget_follow_native_input(self):
        """保留缺省及有限数值预算；不把非数字交给 CLI 环境。@return 无。"""
        body = self._body()
        del body["max_tokens"]
        self.assertNotIn("max_tokens", json.loads(input_message(encode(body))[2]))
        for value in (0, 2.5, 12000):
            sample = encode({**body, "max_tokens": value})
            self.assertEqual(input_message(sample)[2], sample)
        for value in (True, "1", None):
            with self.assertRaises(ValueError):
                input_message(encode({**body, "max_tokens": value}))

    def test_control_fields_never_configure_the_account(self):
        """入站原生或通用 JSON 不能指定提供方、账号凭据、程序或分发头。@return 无。"""
        for key in (
            "extra_headers",
            "extra_body",
            "headers",
            "proxy_url",
            "api_key",
            "oauth_token",
            "claude_binary",
            "workdir",
            "local_bearer",
            "base_url",
        ):
            for native in (True, False):
                with (
                    self.subTest(key=key, native=native),
                    self.assertRaises(ValueError),
                ):
                    input_message(
                        encode({**self._body(), key: "不可信"}), native=native
                    )
        body = {**self._body(), "settings": {}, "env": {"TRACE": "disabled"}}
        self.assertEqual(
            json.loads(input_message(encode(body), native=True)[2]), self._body()
        )
        with closing(self._driver()) as driver:
            with self.assertRaises(ValueError):
                driver.prepare(
                    self._identity("x"), encode({**self._body(), "stream": "yes"})
                )
            self.assertTrue(driver.idle())

    @staticmethod
    def _driver(limit=1, *, physical=None):
        return SessionDriver(
            {"max_reservations": 2 * limit},
            object(),
            TuiCapacity(
                limit if physical is None else physical,
                budget_bytes=10,
                fixed_reserve_bytes=0,
                per_process_reserve_bytes=1,
                max_waiters=2 * limit - 1,
            ),
        )

    @staticmethod
    def _offered(handle, *group):
        actor = handle.actor
        stage = WireStep([{"name": b["name"]} for b in group if b["type"] == "tool_use"])
        stage.observe({"type": "message_start", "message": {}})
        for index, block in enumerate(group):
            stage.observe({"type": "content_block_start", "index": index, "content_block": block})
            actor._observe(stage, {"type": "content_block_stop", "index": index})
        with actor.changed:
            actor.history = handle.history
            actor.step = SimpleNamespace(
                final=[b"finished"], stopped=True, reason="tool_use", blocks=list(group)
            )
            actor._finish_step()
            actor.frame_batch = []
            handle.sent = handle.completed = True
        handle.close()
        return actor

    @staticmethod
    def _agent(tool_id, prompt):
        return {
            "type": "tool_use",
            "id": tool_id,
            "name": "Agent",
            "input": {"prompt": prompt},
        }

    def test_exact_receipt_exit_while_other_session_waits(self):
        """同一账号仍为 B 等工具时，已退出的 A 可以获得独立证明。@return 无。"""
        driver = self._driver(limit=2)
        primary, peer = (1, "environment", 2, 3, "first"), (1, "environment", 2, 3, "second")
        driver.sessions[peer] = object()
        self.assertFalse(driver.idle())
        self.assertTrue(driver.receipt_idle(primary))
        self.assertFalse(driver.receipt_idle(peer))
        driver.sessions[(*primary, "active-agent")] = object()
        self.assertFalse(driver.receipt_idle(primary))
        del driver.sessions[(*primary, "active-agent")]
        driver.waiters.append(SimpleNamespace(actor_key=primary))
        self.assertFalse(driver.receipt_idle(primary))

    def test_agent_only_resident_slot_can_bypass_a_waiting_ordinary_request(self):
        """C1 仅给真正在等的父子多留一个过程，普通队列仍可取消。@return 无。"""
        parent = self._body()
        child = {**parent, "messages": [{"role": "user", "content": "child"}]}
        with patch("tui_session.Path.read_text", return_value=str(1024**3)):
            driver = SessionDriver({"max_reservations": 2}, object())
        with closing(driver), ThreadPoolExecutor(max_workers=1) as pool:
            identity = self._identity("parent")
            self._offered(
                driver.prepare(identity, encode(parent)), self._agent("offer", "child")
            )
            cancelled = Event()
            waiting = pool.submit(
                driver.prepare,
                self._identity("ordinary"),
                encode(parent),
                cancel_event=cancelled,
            )
            try:
                end = time.monotonic() + 2
                while (
                    not driver.waiters and not waiting.done() and time.monotonic() < end
                ):
                    time.sleep(0.005)
                self.assertEqual(len(driver.waiters), 1)
                with closing(
                    driver.prepare({**identity, "agent_hint": "child"}, encode(child))
                ):
                    self.assertEqual(driver.capacity.snapshot().limit, 2)
                    self.assertEqual(driver.capacity.snapshot().in_use, 2)
                    self.assertFalse(waiting.done())
            finally:
                cancelled.set()
            with self.assertRaises(TimeoutError):
                waiting.result(2)
            self.assertFalse(driver.waiters)
            self.assertEqual(driver.capacity.snapshot().in_use, 1)

    def test_agent_resident_budget_respects_cgroup_and_reports_disjoint_parent_chains(
        self,
    ):
        """单父和多棵依赖树占满真实 RAM 时，子请求可及时得到容量反馈。@return 无。"""
        for concurrency, memory, sessions in (
            (1, "max", ("a",)),
            (1, str(512 * 1024**2), ("a",)),
            (2, str(768 * 1024**2), ("a", "b")),
        ):
            with (
                self.subTest(memory=memory),
                patch("tui_session.Path.read_text", return_value=memory),
                closing(
                    SessionDriver({"max_reservations": 2 * concurrency}, object())
                ) as driver,
                ThreadPoolExecutor(max_workers=len(sessions)) as pool,
                patch("tui_session._AGENT_HANDOFF_SECONDS", 0),
            ):
                for session in sessions:
                    self._offered(
                        driver.prepare(self._identity(session), encode(self._body())),
                        self._agent("tool-" + session, session),
                    )
                attempts = [
                    pool.submit(
                        driver.prepare,
                        {**self._identity(s), "agent_hint": s},
                        encode(
                            {
                                **self._body(),
                                "messages": [{"role": "user", "content": s}],
                            }
                        ),
                    )
                    for s in sessions
                ]
                done, _ = wait(attempts, timeout=2, return_when=FIRST_COMPLETED)
                self.assertTrue(done)
                self.assertTrue(
                    all(
                        isinstance(item.exception(), SubagentCapacityError)
                        for item in done
                    )
                )
                self.assertEqual(driver.capacity.snapshot().in_use, len(sessions))
                # 先收到容量失败的父轮退场，单独清理剩余的准备线程。
                driver.close()

    @staticmethod
    def _returning(body, group, *ids):
        return encode(
            {
                **body,
                "messages": [
                    *body["messages"],
                    {"role": "assistant", "content": group},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": item,
                                "content": "合成回执",
                            }
                            for item in ids
                        ],
                    },
                ],
            }
        )

    def _background_returning(self, body, group, **agents):
        returned = json.loads(self._returning(body, group, *agents))
        for receipt in returned["messages"][-1]["content"]:
            hint = agents[receipt["tool_use_id"]]
            receipt["content"] = [
                {
                    "type": "text",
                    "text": (
                        "Async agent launched successfully. (This tool result is internal metadata)\n"
                        f"agentId: {hint} (internal ID - do not mention to user.)\n"
                    ),
                }
            ]
            receipt["content"].append({"type": "text", "text": "原版 CLI 的额外上下文"})
        return encode(returned)

    @staticmethod
    def _finish_background(parent, reply):
        reply.send({})
        with parent.changed:
            parent.expected = None
            reply.completed = True
        reply.close()

    def test_agent_branch_keeps_parent_and_nested_tool_receipts_on_original_actors(
        self,
    ):
        """校验真实工具声明会产生独立子租约，子工具回执不会落到父或兄弟。@return 无。"""
        parent = self._body()
        child = {
            **parent,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "子一"}]}
            ],
        }
        sibling = {**parent, "messages": [{"role": "user", "content": "子二"}]}
        ident = self._identity("shared")
        group = [self._agent("offer-a", "子一"), self._agent("offer-b", "子二")]
        with closing(self._driver(3)) as driver:
            ancestor = self._offered(driver.prepare(ident, encode(parent)), *group)
            for bad in (
                {**ident, "agent_hint": "a", "principal_id": 10},
                {**ident, "agent_hint": "a", "session_id": "elsewhere"},
            ):
                with self.assertRaises(SubagentBindingError):
                    driver.prepare(bad, encode(child))
            with self.assertRaises(SubagentBindingError):
                driver.prepare({**ident, "agent_hint": "a"}, encode(parent))
            first = driver.prepare({**ident, "agent_hint": "a"}, encode(child))
            second = driver.prepare({**ident, "agent_hint": "b"}, encode(sibling))
            self.assertEqual(driver.capacity.snapshot().in_use, 3)
            self.assertEqual(
                len(
                    {
                        ancestor.reservation["session_id"],
                        first.actor.reservation["session_id"],
                        second.actor.reservation["session_id"],
                    }
                ),
                3,
            )
            with self.assertRaises(SubagentBindingError):
                driver.prepare({**ident, "agent_hint": "new-alias"}, encode(child))
            read = {"type": "tool_use", "name": "Read", "id": "child-read", "input": {}}
            child_actor = self._offered(first, read)
            # 此测试直接登记合成输出，显式标记子轮已越过一次提交边界。
            child_actor.agent_offer.submitted = True
            returned = self._returning(child, [read], "child-read")
            for hint in ({**ident, "agent_hint": "b"}, ident):
                with self.assertRaises(ValueError):
                    driver.prepare(hint, returned)
            with closing(
                driver.prepare({**ident, "agent_hint": "a"}, returned)
            ) as resume:
                self.assertIs(resume.actor, child_actor)
            with closing(
                driver.prepare(
                    ident, self._returning(parent, group, "offer-a", "offer-b")
                )
            ) as resume:
                self.assertIs(resume.actor, ancestor)
            second.close()
            driver._retire(child_actor)
            with self.assertRaises(SubagentBindingError):
                driver.prepare({**ident, "agent_hint": "replay"}, encode(child))

    def test_agent_dependency_limit_fails_before_model_and_releases_fifo(self):
        """C1 父轮以及 C2 的两级父链占满时拒绝同步子轮，保持原父等候。@return 无。"""
        parent = self._body()
        child = {**parent, "messages": [{"role": "user", "content": "子轮"}]}
        grandchild = {**parent, "messages": [{"role": "user", "content": "孙轮"}]}
        ident = self._identity("same")
        with patch("tui_session._AGENT_HANDOFF_SECONDS", 0.0):
            for limit in (1, 2):
                with self.subTest(limit=limit), closing(self._driver(limit)) as driver:
                    parent_actor = self._offered(
                        driver.prepare(ident, encode(parent)),
                        self._agent("child", "子轮"),
                    )
                    leaf = child
                    if limit == 2:
                        handle = driver.prepare(
                            {**ident, "agent_hint": "a"}, encode(child)
                        )
                        self._offered(handle, self._agent("nested", "孙轮"))
                        leaf = grandchild
                    with self.assertRaises(SubagentCapacityError):
                        driver.prepare({**ident, "agent_hint": "next"}, encode(leaf))
                    self.assertEqual(driver.capacity.snapshot().in_use, limit)
                    self.assertEqual(len(driver.waiters), 0)
                    self.assertFalse(parent_actor.dead.is_set())

    def test_single_ordinary_slot_can_lend_only_to_a_verified_waiting_child(self):
        """并发一时保留普通槽限制，父轮待回执期间仅已登记子轮可借物理余量。@return 无。"""
        body = self._body()
        child = {**body, "messages": [{"role": "user", "content": "子轮"}]}
        identity = self._identity("parent")
        group = [self._agent("offer", "子轮")]
        with (
            closing(self._driver(1, physical=2)) as driver,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            parent = self._offered(driver.prepare(identity, encode(body)), *group)
            ordinary = pool.submit(
                driver.prepare, self._identity("ordinary"), encode(body)
            )
            end = time.monotonic() + 2
            while not driver.waiters and not ordinary.done() and time.monotonic() < end:
                time.sleep(0.005)
            self.assertEqual(len(driver.waiters), 1)
            self.assertEqual(driver.capacity.snapshot().in_use, 1)
            with self.assertRaises(SubagentBindingError):
                driver.prepare({**identity, "agent_hint": "unrelated"}, encode(body))
            with closing(
                driver.prepare({**identity, "agent_hint": "child"}, encode(child))
            ) as admitted:
                self.assertIs(admitted.actor.agent_offer.parent, parent)
                self.assertEqual(driver.capacity.snapshot().in_use, 2)
                self.assertFalse(ordinary.done())
            with closing(
                driver.prepare(identity, self._returning(body, group, "offer"))
            ) as resume:
                self.assertIs(resume.actor, parent)
            self.assertFalse(ordinary.done())
            driver._retire(parent)
            with closing(ordinary.result(2)):
                self.assertEqual(driver.capacity.snapshot().in_use, 1)
            self.assertTrue(driver.idle())

    def test_agent_cancelled_in_queue_returns_its_offer_and_keeps_fifo(self):
        """取消等待不消耗已登记工具，排队的新轮依原到达顺序获得同一硬槽。@return 无。"""
        body = self._body()
        child = {**body, "messages": [{"role": "user", "content": "子轮"}]}
        ident = self._identity("same")
        with (
            closing(self._driver(2)) as driver,
            ThreadPoolExecutor(max_workers=3) as pool,
        ):
            actor = self._offered(
                driver.prepare(ident, encode(body)), self._agent("offer", "子轮")
            )
            busy = driver.prepare(self._identity("busy"), encode(body))
            cancel = Event()
            cancelled = pool.submit(
                driver.prepare,
                {**ident, "agent_hint": "a"},
                encode(child),
                cancel_event=cancel,
            )
            while not driver.waiters and not cancelled.done():
                time.sleep(0.005)
            plain = pool.submit(driver.prepare, self._identity("ahead"), encode(body))
            while len(driver.waiters) < 2 and not plain.done():
                time.sleep(0.005)
            cancel.set()
            with self.assertRaises(TimeoutError):
                cancelled.result(2)
            again = pool.submit(
                driver.prepare, {**ident, "agent_hint": "a"}, encode(child)
            )
            busy.close()
            with closing(plain.result(2)):
                self.assertFalse(again.done())
            with closing(again.result(2)) as child_handle:
                self.assertIs(child_handle.actor.agent_offer.parent, actor)

    def test_verified_background_receipt_allows_child_after_single_slot_parent(self):
        """后台原工具回执能在短窗口内自然释放 C1 的父租约。@return 无。"""
        parent = self._body()
        child = {**parent, "messages": [{"role": "user", "content": "子轮"}]}
        identity = self._identity("shared")
        offer = self._agent("offer", "子轮")
        with (
            closing(self._driver(1)) as driver,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            actor = self._offered(driver.prepare(identity, encode(parent)), offer)
            queued = pool.submit(
                driver.prepare, {**identity, "agent_hint": "agent"}, encode(child)
            )
            while not driver.waiters and not queued.done():
                time.sleep(0.005)
            self.assertFalse(queued.done())
            self._finish_background(
                actor,
                driver.prepare(
                    identity, self._background_returning(parent, [offer], offer="agent")
                ),
            )
            with closing(queued.result(2)) as next_turn:
                self.assertIsNot(next_turn.actor, actor)
                self.assertEqual(driver.capacity.snapshot().in_use, 1)

    def test_denied_parent_receipt_wakes_and_rejects_queued_child_before_retirement(
        self,
    ):
        """失败回执结束父等待，排队子轮在父进程仍驻留时即拒绝。@return 无。"""
        body = self._body()
        child = {**body, "messages": [{"role": "user", "content": "子轮"}]}
        identity = self._identity("shared")
        candidate = {**identity, "agent_hint": "agent"}
        offer = self._agent("offer", "子轮")
        with (
            closing(self._driver(1)) as driver,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            parent = self._offered(driver.prepare(identity, encode(body)), offer)
            queued = pool.submit(driver.prepare, candidate, encode(child))
            end = time.monotonic() + 1
            while not driver.waiters and time.monotonic() < end:
                time.sleep(0.005)
            self.assertEqual(len(driver.waiters), 1)
            raw = json.loads(self._background_returning(body, [offer], offer="agent"))
            raw["messages"][-1]["content"][0]["is_error"] = True
            with closing(driver.prepare(identity, encode(raw))) as denied:
                denied.send({})
                with self.assertRaises(SubagentBindingError):
                    queued.result(1)
                self.assertFalse(parent.retired.is_set())
                self.assertEqual(driver.capacity.snapshot().in_use, 1)
                self.assertFalse(driver.waiters)
                self.assertFalse(driver.background_agents)
                with parent.changed:
                    parent.expected = None
                    denied.completed = True
            self.assertTrue(parent.retired.is_set())
            with self.assertRaises(SubagentBindingError):
                driver.prepare(candidate, encode(child))

    def test_denied_parent_receipt_blocks_model_after_child_send(self):
        """前台子终端已获准启动时，后到失败回执仍阻止尚未认领的模型请求。@return 无。"""
        body = self._body()
        child = {**body, "messages": [{"role": "user", "content": "子轮"}]}
        identity = self._identity("shared")
        offer = self._agent("offer", "子轮")
        with closing(self._driver(1, physical=2)) as driver:
            driver.launcher = SimpleNamespace(local_model_response=Mock())
            parent = self._offered(driver.prepare(identity, encode(body)), offer)
            with closing(
                driver.prepare({**identity, "agent_hint": "agent"}, encode(child))
            ) as prepared:
                prepared.send({})
                actor = prepared.actor
                actor.step = SimpleNamespace(native=("turn", 1), claimed=False)
                raw = json.loads(
                    self._background_returning(body, [offer], offer="agent")
                )
                raw["messages"][-1]["content"][0]["is_error"] = True
                with (
                    closing(driver.prepare(identity, encode(raw))) as denied,
                    patch.object(actor, "_main_request", return_value=True),
                ):
                    denied.send({})
                    with self.assertRaises(SubagentBindingError):
                        actor.serve_model(Mock(), {})
                    self.assertFalse(actor.step.claimed)
                    driver.launcher.local_model_response.assert_not_called()
                    self.assertFalse(driver.background_agents)
                    self.assertFalse(parent.dead.is_set())

    def test_background_child_first_arrives_after_normal_parent_exit(self):
        """正常退出只保留本代的启动配对，迟到子轮用空闲普通名额。@return 无。"""
        body = self._body()
        child = {**body, "messages": [{"role": "user", "content": "后台子轮"}]}
        identity = self._identity("shared")
        offer = self._agent("offer", "后台子轮")
        with closing(self._driver(1)) as driver:
            parent = self._offered(driver.prepare(identity, encode(body)), offer)
            self._finish_background(
                parent,
                driver.prepare(
                    identity, self._background_returning(body, [offer], offer="agent")
                ),
            )
            self.assertTrue(parent.retired.is_set())
            self.assertEqual(driver.capacity.snapshot().in_use, 0)
            candidate = {**identity, "agent_hint": "agent"}
            for override in (
                {"agent_hint": "unknown"},
                {"principal_id": 10},
                {"account_id": 2},
                {"generation": 2},
                {"session_id": "other"},
            ):
                with self.assertRaises(SubagentBindingError):
                    driver.prepare({**candidate, **override}, encode(child))
            with self.assertRaises(SubagentBindingError):
                driver.prepare(candidate, encode(body))
            with closing(driver.prepare(candidate, encode(child))) as reserved:
                proof = reserved.actor.agent_offer
                self.assertIsNone(proof.parent)
                self.assertEqual(proof.tool_digest, sha256(b"offer").digest())
                reserved.send({})
            with self.assertRaises(SubagentBindingError):
                driver.prepare(candidate, encode(child))

    def test_background_child_receipt_accepts_one_cli_line_feed(self):
        """启动回执与子 ID 配对后，仅兼容首轮业务文本多一个换行。@return 无。"""
        body = self._body()
        identity = self._identity("shared")
        candidate = {**identity, "agent_hint": "child"}
        offer = self._agent("offer", "原提示")

        def request(text):
            return encode({**body, "messages": [{"role": "user", "content": [
                {"type": "text", "text": "<system-reminder>\n上下文\n</system-reminder>"},
                {"type": "text", "text": text},
            ]}]})

        with closing(self._driver(1)) as driver, ThreadPoolExecutor(max_workers=1) as pool:
            parent = self._offered(driver.prepare(identity, encode(body)), offer)
            for text in ("原提示 ", "原提示\n\n", "原提示\r\n"):
                with self.assertRaises(SubagentBindingError):
                    driver.prepare(candidate, request(text))
            pending = pool.submit(driver.prepare, candidate, request("原提示\n"))
            end = time.monotonic() + 2
            while not driver.waiters and not pending.done() and time.monotonic() < end:
                time.sleep(0.01)
            self.assertTrue(driver.waiters)
            self._finish_background(parent, driver.prepare(
                identity, self._background_returning(body, [offer], offer="child")))
            with closing(pending.result(3)) as reserved:
                self.assertEqual(reserved.actor.agent_offer.tool_digest, sha256(b"offer").digest())
                reserved.send({})
            with self.assertRaises(SubagentBindingError):
                driver.prepare(candidate, request("原提示\n"))

    def test_cli_groups_agent_text_without_changing_tools_or_signatures(self):
        """原版 CC 按同类原序交还文本及工具，比较后仍保留客户端原文。@return 无。"""
        body = self._body()
        first, second = self._agent("a", "一"), self._agent("b", "二")
        text = {"type": "text", "text": "进度"}
        expected = [first, {"type": "text", "text": sha256("进度".encode()).hexdigest()}, second]
        messages = json.loads(self._returning(body, [text, first, second], "a", "b"))["messages"]
        history = history_digest(body["messages"])
        self.assertEqual(set(tool_receipts(messages, history, expected, input_format="claude_code")), {"a", "b"})
        with self.assertRaises(ValueError):
            tool_receipts(messages, history, expected)
        for blocks in ([text, second, first], [{**text, "text": "变化"}, first, second],
                       [text, first, {**second, "input": first["input"]}]):
            messages[-2]["content"] = blocks
            with self.assertRaises(ValueError):
                tool_receipts(messages, history, expected, input_format="claude_code")
        signed = {"type": "thinking", "thinking": "推理", "signature": "签名"}
        messages[-2]["content"] = [text, signed, first, second]
        with self.assertRaises(ValueError):
            tool_receipts(messages, history, [signed, *expected], input_format="claude_code")

    def test_open_group_waits_until_tool_order_is_known(self):
        """同提示兄弟仍可能到达；组封闭且唯一时早于父终态认领。@return 无。"""
        identity, body = self._identity("streaming"), self._body()
        child = encode({**body, "messages": [{"role": "user", "content": "相同提示"}]})
        for sibling in (False, True):
            with self.subTest(sibling=sibling), closing(self._driver(3)) as driver, ThreadPoolExecutor(1) as pool:
                parent = driver.prepare(identity, encode(body))
                actor = parent.actor
                step = actor.step = WireStep([{"name": "Agent"}])
                step.observe({"type": "message_start", "message": {}})
                def dispatch(index):
                    block = self._agent(str(index), "相同提示")
                    actor._observe(step, {"type": "content_block_start", "index": index, "content_block": block})
                    actor._observe(step, {"type": "content_block_stop", "index": index})
                dispatch(0)
                pending = pool.submit(driver.prepare, {**identity, "agent_hint": "child"}, child)
                limit = time.monotonic() + 1
                while not driver.waiters and not pending.done() and time.monotonic() < limit:
                    time.sleep(.005)
                self.assertTrue(driver.waiters)
                if sibling:
                    dispatch(1)
                step.observe({"type": "message_delta", "delta": {"stop_reason": "tool_use"}})
                actor._observe(step, {"type": "message_stop"})
                self.assertFalse(actor.finished)
                if sibling:
                    parent.close()
                    with self.assertRaises(SubagentBindingError):
                        pending.result(1)
                else:
                    with closing(pending.result(1)) as early:
                        self.assertIs(early.actor.agent_offer, actor.agent_offers["0"])

    def test_cancelled_parent_waiter_cannot_move_to_replacement_step(self):
        """取消父轮后，迟到的唤醒和同文新回执都不能将旧等待转入新派工。@return 无。"""
        body = self._body()
        identity = self._identity("same-session")
        candidate = {**identity, "agent_hint": "child"}
        child = encode({**body, "messages": [{"role": "user", "content": "相同任务"}]})
        for with_receipt in (False, True):
            with self.subTest(receipt=with_receipt), closing(self._driver(3)) as driver, ThreadPoolExecutor(1) as pool:
                original = driver.prepare(identity, encode(body))
                actor = original.actor
                step = actor.step = WireStep([{"name": "Agent"}])
                step.observe({"type": "message_start", "message": {}})
                step.observe({"type": "content_block_start", "index": 0,
                              "content_block": self._agent("old", "相同任务")})
                actor._observe(step, {"type": "content_block_stop", "index": 0})
                waiting = Event()
                claim = driver._claim_agent

                def observe_claim(*args):
                    result = claim(*args)
                    if result is None:
                        waiting.set()
                    return result

                with patch.object(driver, "_claim_agent", side_effect=observe_claim):
                    pending = pool.submit(driver.prepare, candidate, child)
                    self.assertTrue(waiting.wait(1))
                    # 控制原等待再次获取锁的顺序，覆盖替代派工比唤醒先就绪的情况。
                    with driver.lock:
                        original.close()
                        block = self._agent("replacement", "相同任务")
                        parent = self._offered(driver.prepare(identity, encode(body)), block)
                        if with_receipt:
                            self._finish_background(parent, driver.prepare(identity,
                                self._background_returning(body, [block], replacement="child")))
                    with self.assertRaises(SubagentBindingError):
                        pending.result(1)
                with closing(driver.prepare(candidate, child)) as fresh:
                    self.assertEqual(fresh.actor.agent_offer.tool_digest, sha256(b"replacement").digest())

    def test_closed_agent_block_and_late_directed_message(self):
        """父轮仍在输出时接纳等待者，随后用回执确认换行和定向消息。@return 无。"""
        body = self._body()
        identity = self._identity("streaming")
        hint = "child01"
        offer = self._agent("first", "合成任务")
        message = {"type": "tool_use", "name": "SendMessage", "id": "follow",
                   "input": {"to": hint, "message": "追加要求"}}
        text = "The coordinator sent a message while you were working:\n追加要求\n\nAddress this before completing your current task."
        def child(extra):
            return encode({**body, "messages": [{"role": "user", "content": [
                {"type": "text", "text": "合成任务\n"}, {"type": "text", "text": extra}]}]})
        with closing(self._driver(3)) as driver, ThreadPoolExecutor(1) as pool:
            handle = driver.prepare(identity, encode(body))
            actor = handle.actor
            actor.history = handle.history
            step = actor.step = WireStep([{"name": "Agent"}, {"name": "SendMessage"}])
            step.observe({"type": "message_start", "message": {}})
            for index, block in enumerate((offer, message)):
                step.observe({"type": "content_block_start", "index": index, "content_block": block})
                actor._observe(step, {"type": "content_block_stop", "index": index})
            candidate = {**identity, "agent_hint": hint}
            with patch("tui_session._AGENT_HANDOFF_SECONDS", 0.01):
                pending = pool.submit(driver.prepare, candidate, child(text))
                end = time.monotonic() + 1
                while not driver.waiters and not pending.done() and time.monotonic() < end:
                    time.sleep(0.005)
                self.assertTrue(driver.waiters)
                time.sleep(0.04)
                self.assertFalse(pending.done())
                step.observe({"type": "message_delta", "delta": {"stop_reason": "tool_use"}})
                actor._observe(step, {"type": "message_stop"})
                step.final = [b"finished"]
                with actor.changed:
                    actor._finish_step()
                    actor.frame_batch = []
                    handle.sent = handle.completed = True
                handle.close()
                receipt = json.loads(self._background_returning(body, [offer, message], first=hint, follow="unused"))
                receipt["messages"][-1]["content"][1]["content"] = "delivered"
                self._finish_background(actor, driver.prepare(identity, encode(receipt)))
                with closing(pending.result(1)) as reserved:
                    self.assertEqual(reserved.raw, child(text))
                with self.assertRaises(SubagentBindingError):
                    driver.prepare(candidate, child(text.replace("追加要求", "其他要求")))
                with closing(driver.prepare(candidate, child(text))) as retry:
                    retry.send({})
                with self.assertRaises(SubagentBindingError):
                    driver.prepare(candidate, child(text))

    def test_same_prompt_siblings_wait_for_exact_background_ids(self):
        """相同提示不分配原工具，后到的回执精确拨给各 ID 所属分支。@return 无。"""
        body = self._body()
        child = {**body, "messages": [{"role": "user", "content": "同一提示"}]}
        identity = self._identity("shared")
        group = [self._agent(name, "同一提示") for name in ("first", "second")]
        with (
            closing(self._driver(3)) as driver,
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            parent = self._offered(driver.prepare(identity, encode(body)), *group)
            pending = {}
            for agent_id in ("agentB", "agentA"):
                pending[agent_id] = pool.submit(
                    driver.prepare, {**identity, "agent_hint": agent_id}, encode(child)
                )
                end = time.monotonic() + 1
                while len(driver.waiters) < len(pending) and time.monotonic() < end:
                    time.sleep(0.005)
            self.assertEqual(len(driver.waiters), 2)
            self.assertEqual(driver.capacity.snapshot().in_use, 1)
            self._finish_background(
                parent,
                driver.prepare(
                    identity,
                    self._background_returning(
                        body, group, first="agentA", second="agentB"
                    ),
                ),
            )
            first, second = [pending[hint].result(2) for hint in ("agentA", "agentB")]
            with closing(first), closing(second):
                self.assertNotEqual(
                    first.actor.reservation["session_id"],
                    second.actor.reservation["session_id"],
                )
                self.assertEqual(
                    first.actor.agent_offer.tool_digest, sha256(b"first").digest()
                )
                self.assertEqual(
                    second.actor.agent_offer.tool_digest, sha256(b"second").digest()
                )

    def test_unresolved_siblings_release_waiter_and_allow_later_exact_retry(self):
        """同提示兄弟在交接窗内无法区分时释放等待位置，迟到的原回执仍可认领。@return 无。"""
        body = self._body()
        child = encode(
            {**body, "messages": [{"role": "user", "content": "相同子任务"}]}
        )
        identity = self._identity("shared")
        group = [self._agent(name, "相同子任务") for name in ("first", "second")]
        with closing(self._driver(3)) as driver:
            parent = self._offered(driver.prepare(identity, encode(body)), *group)
            candidate = {**identity, "agent_hint": "agentB"}
            with patch("tui_session._AGENT_HANDOFF_SECONDS", 0.02):
                with self.assertRaises(SubagentAmbiguousError):
                    driver.prepare(
                        {
                            **candidate,
                            "deadline_unix_ms": int(time.time() * 1000) + 500,
                        },
                        child,
                    )
            self.assertFalse(driver.waiters)
            self.assertEqual(driver.capacity.snapshot().in_use, 1)
            self.assertTrue(
                all(offer.claimed is None for offer in parent.agent_offers.values())
            )
            self._finish_background(
                parent,
                driver.prepare(
                    identity,
                    self._background_returning(
                        body, group, first="agentA", second="agentB"
                    ),
                ),
            )
            with closing(driver.prepare(candidate, child)) as retry:
                self.assertEqual(
                    retry.actor.agent_offer.tool_digest, sha256(b"second").digest()
                )

    def test_background_proofs_reject_cancelled_expired_or_ambiguous_receipts(self):
        """取消、重复后台 ID、失败和超期回执全部拒绝。@return 无。"""
        body = self._body()
        child = {**body, "messages": [{"role": "user", "content": "后台"}]}
        identity = self._identity("shared")
        candidate = {**identity, "agent_hint": "agent"}
        for scenario in (
            "cancelled",
            "expired",
            "collision",
            "failed",
            "duplicate_reply",
        ):
            with self.subTest(scenario=scenario), closing(self._driver(1)) as driver:
                agents = {"first": "agent"}
                if scenario == "collision":
                    agents["second"] = "agent"
                group = [self._agent(name, "后台") for name in agents]
                parent = self._offered(driver.prepare(identity, encode(body)), *group)
                raw = self._background_returning(body, group, **agents)
                if scenario in ("failed", "duplicate_reply"):
                    error = json.loads(raw)
                    receipt = error["messages"][-1]["content"][0]
                    if scenario == "failed":
                        receipt["is_error"] = True
                    else:
                        receipt["content"].append(receipt["content"][0])
                    raw = encode(error)
                returned = driver.prepare(identity, raw)
                if scenario == "cancelled":
                    returned.send({})
                    returned.close()
                else:
                    self._finish_background(parent, returned)
                if scenario == "expired":
                    driver.background_agents[(*parent.identity, "agent")].until = 0
                with self.assertRaises(SubagentBindingError):
                    driver.prepare(candidate, encode(child))

    def test_nested_agent_requires_its_own_active_offer_and_can_use_capacity_three(
        self,
    ):
        """有第三个硬槽时通过真实依赖链准入孙轮，取消祖先后子分支不能提交。@return 无。"""
        body = self._body()
        child = {**body, "messages": [{"role": "user", "content": "子轮"}]}
        nested = {**body, "messages": [{"role": "user", "content": "孙轮"}]}
        identity = self._identity("same")
        with closing(self._driver(3)) as driver:
            original = self._offered(
                driver.prepare(identity, encode(body)), self._agent("first", "子轮")
            )
            second = self._offered(
                driver.prepare({**identity, "agent_hint": "child"}, encode(child)),
                self._agent("second", "孙轮"),
            )
            with closing(
                driver.prepare({**identity, "agent_hint": "nested"}, encode(nested))
            ) as third:
                self.assertIs(third.actor.agent_offer.parent, second)
                self.assertIs(second.agent_offer.parent, original)
                driver._retire(original)
                self.assertTrue(second.dead.is_set())
                driver._retire(second)
                self.assertTrue(third.actor.dead.is_set())
                with self.assertRaises(ValueError):
                    third.send({})

    def test_thread_start_failure_releases_pending_process_slot(self):
        """系统线程不足使监护线程启动失败时，原进程名额仍可收回。@return 无。"""
        with closing(self._driver()) as driver:
            handle = driver.prepare(self._identity("s"), json.dumps(self._body()))
            with (
                closing(handle),
                patch(
                    "tui_session.Thread.start",
                    side_effect=RuntimeError("thread unavailable"),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    next(handle.send({}))
            self.assertTrue(driver.idle())
            self.assertEqual(driver.capacity.snapshot().in_use, 0)

    def test_cancellation_while_waiting_does_not_reserve_or_launch(self):
        """占用状态下的第二主体可在实际提交前取消。@return 无。"""
        data = json.dumps(self._body())
        with closing(self._driver()) as d, ThreadPoolExecutor(max_workers=1) as pool:
            with closing(d.prepare(self._identity("first"), data)):
                cancel = Event()
                fut = pool.submit(
                    d.prepare, self._identity("second"), data, cancel_event=cancel
                )
                end = time.monotonic() + 2
                while len(d.waiters) == 0 and time.monotonic() < end:
                    time.sleep(0.005)
                self.assertEqual(len(d.waiters), 1)
                cancel.set()
                with self.assertRaises(TimeoutError):
                    fut.result(2)
                self.assertEqual(d.capacity.snapshot().in_use, 1)
            self.assertTrue(d.idle())
            self.assertEqual(d.capacity.snapshot().in_use, 0)

    def test_full_fifo_keeps_transport_slot_for_existing_tools(self):
        """等待新进程的队列满时拒绝额外请求，原工具仍能立即续轮。@return 无。"""
        request = self._body()
        with closing(self._driver()) as d, ThreadPoolExecutor(max_workers=1) as pool:
            first = d.prepare(self._identity("running"), json.dumps(request))
            actor = first.actor
            group = [
                {
                    "type": "tool_use",
                    "id": "read1",
                    "name": "Read",
                    "input": {"file_path": "a"},
                }
            ]
            with actor.changed:
                actor.history = first.history
                actor.expected = group
                first.sent = first.completed = True
            first.close()
            cancel = Event()
            queued = pool.submit(
                d.prepare,
                self._identity("waiting"),
                json.dumps(request),
                cancel_event=cancel,
            )
            try:
                end = time.monotonic() + 2
                while not len(d.waiters) and time.monotonic() < end:
                    time.sleep(0.005)
                self.assertEqual(len(d.waiters), 1)
                with self.assertRaises(TimeoutError):
                    d.prepare(self._identity("overflow"), json.dumps(request))
                returned = {
                    "type": "tool_result",
                    "tool_use_id": "read1",
                    "content": "x",
                }
                request["messages"] += [
                    {"role": "assistant", "content": group},
                    {"role": "user", "content": [returned]},
                ]
                with closing(
                    d.prepare(self._identity("running"), json.dumps(request))
                ) as receipt:
                    self.assertEqual(receipt.kind, "continuation")
                    self.assertIs(receipt.actor, actor)
            finally:
                cancel.set()
                with self.assertRaises(TimeoutError):
                    queued.result(2)

    def test_same_session_new_request_waits_while_the_original_tool_can_continue(self):
        """主轮和标题共用全部归属时，标题只占一个等待位置，工具结果仍接回同一实例。@return 无。"""
        request = self._body()
        ident = self._identity("same")
        with closing(self._driver()) as d, ThreadPoolExecutor(max_workers=1) as pool:
            first = d.prepare(ident, encode(request))
            actor = first.actor
            title = pool.submit(
                d.prepare,
                dict(ident),
                encode(
                    {
                        **request,
                        "output_config": {
                            "format": {"type": "json_schema", "schema": {}}
                        },
                    }
                ),
            )
            try:
                end = time.monotonic() + 2
                while not d.waiters and time.monotonic() < end:
                    time.sleep(0.005)
                self.assertEqual(len(d.waiters), 1)
                self.assertFalse(title.done())
                group = [
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "x"},
                        "id": "t",
                    }
                ]
                with actor.changed:
                    actor.expected, actor.history, actor.finished = (
                        group,
                        first.history,
                        True,
                    )
                    first.sent = first.completed = True
                first.close()
                returned = {
                    "type": "tool_result",
                    "tool_use_id": "t",
                    "content": "正确",
                }
                receipt_body = {
                    **request,
                    "messages": [
                        *request["messages"],
                        {"role": "assistant", "content": group},
                        {"role": "user", "content": [returned]},
                    ],
                }
                wait = ModelResponseError(429, b"", source="local_provider_backoff", retry_after=25)
                with patch.object(d, "launcher", SimpleNamespace(check_provider_backoff=Mock(side_effect=wait))):
                    with self.assertRaises(ModelResponseError) as error:
                        d.prepare(ident, encode(receipt_body))
                    self.assertEqual(error.exception.retry_after, 25)
                    self.assertIsNone(actor.claim)
                    self.assertEqual(actor.expected, group)
                with closing(d.prepare(ident, encode(receipt_body))) as receipt:
                    self.assertIs(receipt.actor, actor)
                    self.assertFalse(title.done())
                actor.abort()
                d._retire(actor)
                with closing(title.result(2)) as second:
                    self.assertEqual(second.kind, "new")
                    self.assertIsNot(second.actor, actor)
            finally:
                first.close()
                if not title.done():
                    actor.abort()
                    d._retire(actor)

    def test_accepts_multiple_tools_and_recovers_each_original_block(self):
        """仅已登记完整工具组可续接，保留每项的原 ID、文本和错误状态。@return 无。"""
        history = self._body()["messages"]
        registered = [
            {"type": "tool_use", "id": i, "name": "Read", "input": {"file_path": i}}
            for i in ("a", "b")
        ]
        results = [
            {
                "type": "tool_result",
                "tool_use_id": "b",
                "content": [{"type": "text", "text": "é"}],
            },
            {
                "type": "tool_result",
                "tool_use_id": "a",
                "is_error": True,
                "content": "拒绝",
            },
        ]

        def received(blocks):
            return [
                *history,
                {"role": "assistant", "content": registered},
                {"role": "user", "content": blocks},
            ]

        self.assertEqual(
            tool_receipts(received(results), history_digest(history), registered),
            {"b": results[0], "a": results[1]},
        )
        for wrong in (
            [results[0]],
            [results[0], results[0]],
            [dict(results[0], tool_use_id="c"), results[1]],
        ):
            with self.assertRaises(ValueError):
                tool_receipts(received(wrong), history_digest(history), registered)

    def test_consecutive_tool_turns_deliver_only_the_current_receipts(self):
        """连续两轮工具结果均能开启原进程的下一步，同轮重复回调仍被拒绝。@return 无。"""
        request = {
            **self._body(),
            "tools": [{"name": "Read", "input_schema": {"type": "object"}}],
        }
        identity = self._identity("multi-turn")
        group = [{"type": "tool_use", "name": "Read", "id": "first", "input": {}}]
        with (
            closing(self._driver()) as driver,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            driver.launcher = Mock()
            with closing(driver.prepare(identity, encode(request))) as first:
                actor = first.actor
                actor.expected, actor.history = group, first.history
                first.sent = first.completed = True
            for index, next_id in enumerate(("second", "third"), 1):
                tool_id = group[0]["id"]
                result = {
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": tool_id,
                }
                request["messages"].extend(
                    [
                        {"role": "assistant", "content": group},
                        {"role": "user", "content": [result]},
                    ]
                )
                identity["body_policy"] = {"sub2api": True, "ttl": "5m" if index == 1 else "1h", "adaptive": False}
                if index == 1:
                    bad = {**request, "thinking": {"type": "disabled"},
                           "context_management": {"edits": [{"type": "clear_thinking_20251015"}]}}
                    with self.assertRaisesRegex(ValueError, "unsupported_parameter"):
                        driver.prepare(identity, encode(bad))
                    driver.launcher.local_model_response.assert_not_called()
                    self.assertEqual(actor.expected, group)
                with closing(driver.prepare(identity, encode(request))) as follow:
                    self.assertEqual(json.loads(follow.raw)["messages"][-1]["content"][0],
                                     {**result, "cache_control": {"type": "ephemeral", "ttl": identity["body_policy"]["ttl"]}})
                    self.assertEqual(follow.history, history_digest(request["messages"]))
                    prior_step = actor.step
                    output = pool.submit(list, follow.send({}))
                    try:
                        with actor.changed:
                            self.assertTrue(
                                actor.changed.wait_for(
                                    lambda: actor.step is not prior_step, 2
                                )
                            )
                        self.assertEqual(
                            actor.callback("/results", {"ids": [tool_id]}),
                            {"results": [result]},
                        )
                        with self.assertRaises(ValueError):
                            actor.callback("/results", {"ids": [tool_id]})
                        event = {
                            "turn": "turn",
                            "step": index,
                            "model": request["model"],
                        }
                        actor.callback("/begin", event)
                        group = [{**group[0], "id": next_id}]
                        events = [
                            {"type": "message_start", "message": {}},
                            {
                                "type": "content_block_start",
                                "index": 0,
                                "content_block": group[0],
                            },
                            {"type": "content_block_stop", "index": 0},
                            {
                                "type": "message_delta",
                                "delta": {"stop_reason": "tool_use"},
                            },
                            {"type": "message_stop"},
                        ]
                        wire = b"".join(b"data: " + encode(e) + b"\n\n" for e in events)
                        response = BytesIO(wire)
                        response.status = 200
                        response.getheader = lambda *_: "text/event-stream"
                        driver.launcher.local_model_response.return_value = response
                        actor.serve_model(Mock(), request)
                        actor.callback("/end", {**event, "reason": "tool_use"})
                        self.assertEqual(b"".join(output.result(2)), wire)
                    finally:
                        if not follow.completed:
                            actor.abort()
            self.assertEqual(driver.launcher.local_model_response.call_count, 2)

    def test_verified_refusal_finishes_before_cli_requests_another_step(self):
        """真实拒答交付完整终帧，普通文本按完整回合收尾，重复回调不增加投递。@return 无。"""
        for reason in ("refusal", "end_turn"):
            with self.subTest(reason=reason), closing(self._driver()) as driver, ThreadPoolExecutor(1) as pool:
                driver.launcher = Mock()
                with closing(driver.prepare(self._identity(reason), encode(self._body()))) as handle:
                    actor = handle.actor
                    with patch.object(actor, "start"):
                        output = pool.submit(list, handle.send({}))
                        try:
                            with actor.changed:
                                self.assertTrue(actor.changed.wait_for(lambda: actor.step is not None, 2))
                            turn = {"turn": "test", "step": 0, "model": "chosen"}
                            actor.callback("/begin", turn)
                            events = [
                                {"type": "message_start", "message": {}},
                                {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": "usage policy [reasoning_extraction]"}},
                                {"type": "content_block_stop", "index": 0},
                                {"type": "message_delta", "delta": {"stop_reason": reason}},
                                {"type": "message_stop"},
                            ]
                            wire = b"".join(b"data: " + encode(e) + b"\n\n" for e in events)
                            source = BytesIO(wire)
                            source.status = 200
                            source.getheader = lambda *_: "text/event-stream"
                            driver.launcher.local_model_response.return_value = source
                            marker = f"<system-reminder>\nprompt.submit hook additional context: {actor.guard_text}\n</system-reminder>"
                            native = {**self._body(), "messages": [{"role": "user", "content": [{"type": "text", "text": marker}]}]}
                            actor.serve_model(Mock(), native)
                            actor.callback("/end", {**turn, "reason": reason})
                            self.assertEqual(actor.finished, reason == "refusal")
                            if reason == "refusal":
                                self.assertEqual(b"".join(output.result(2)), wire)
                                with self.assertRaises(ValueError):
                                    actor.callback("/begin", {**turn, "step": 1})
                                retry = Mock()
                                actor.serve_model(retry, native)
                                retry.send_error.assert_called_once_with(409, "No pending model step")
                            actor.callback("/complete", {"turn": "test", "aborted": False})
                            self.assertEqual(b"".join(output.result(2)), wire)
                            self.assertEqual(actor.frame_batch, [])
                        finally:
                            actor.abort()
                self.assertTrue(driver.idle())
                self.assertTrue(actor.completed_normally)
                self.assertEqual(driver.capacity.snapshot().in_use, 0)
                driver.launcher.local_model_response.assert_called_once()

    def test_native_agent_summary_preserves_receipt_and_reuses_only_its_own_workspace(self):
        """原生进度使用独立进程和原正文，重复查询复用专属工作区。@return 无。"""
        with closing(self._driver(limit=2, physical=2)) as driver:
            parent_id = self._identity("test-session")
            group = [{"type": "tool_use", "id": "r", "name": "Read", "input": {}}]
            with closing(driver.prepare(parent_id, encode(self._body()))) as parent:
                self._offered(parent, *group)
                answers = [{"type": "tool_result", "tool_use_id": "r", "content": "示例"}]
                history = [*self._body()["messages"], {"role": "assistant", "content": group},
                           {"role": "user", "content": [*answers, {"type": "text", "text": "查询进度"}]}]
                raw = encode({**self._body(), "messages": history})
                def read_summary(agent):
                    private = {**parent_id, "agent_hint": agent, "agent_summary": True}
                    with closing(driver.prepare(private, raw)) as handle:
                        self.assertEqual(handle.kind, "new")
                        self.assertEqual(handle.raw, raw)
                        self.assertIsNot(handle.actor, parent.actor)
                        self.assertEqual(parent.actor.expected, group)
                        self.assertFalse(parent.actor.dead.is_set())
                        return handle.actor.reservation["session_id"]
                first = read_summary("agent-one")
                self.assertEqual(first, read_summary("agent-one"))
                self.assertNotEqual(first, read_summary("agent-two"))
                with self.assertRaises(ValueError):
                    driver.prepare({**parent_id, "agent_summary": True}, raw)

    def test_native_progress_yields_to_receipts_when_hard_limit_is_full(self):
        """物理容量只够原进程时，摘要退避且真回执仍能立刻认领。@return 无。"""
        identity = self._identity("one-slot")
        tool = {"type": "tool_use", "id": "original", "name": "Read", "input": {}}
        result = {"type": "tool_result", "tool_use_id": tool["id"], "content": "完成"}
        body = self._body()
        answer = {**body, "messages": [*body["messages"], {"role": "assistant", "content": [tool]},
                                        {"role": "user", "content": [result]}]}
        with closing(self._driver(limit=1, physical=1)) as driver:
            actor = self._offered(driver.prepare(identity, encode(body)), tool)
            with self.assertRaisesRegex(TimeoutError, "物理进程额度"):
                driver.prepare({**identity, "agent_hint": "agent-one", "agent_summary": True}, encode(answer))
            with closing(driver.prepare(identity, encode(answer))) as handle:
                self.assertIs(handle.actor, actor)
                self.assertEqual(handle.answers, {tool["id"]:result})

    def test_slow_receipt_polls_only_its_current_group(self):
        """分段查询等待原结果，过期编号、并行组和重复回执相互隔离。@return 无。"""
        with closing(self._driver()) as driver, closing(
            driver.prepare(self._identity("slow"), encode(self._body()))
        ) as handle:
            actor = handle.actor
            actor.step = WireStep([])
            actor.expected = [{"type": "tool_use", "id": i} for i in ("a", "b")]
            actor.wait_until = time.monotonic() + 3600
            deadline = actor.wait_until
            with patch("tui_session._RECEIPT_POLL_SECONDS", 0):
                ticket = actor.callback("/results", {"ids": ["a"]})["pending"]
                query = {"ids": ["a"], "ticket": ticket}
                self.assertEqual(actor.callback("/results", query), {"pending": ticket})
                self.assertEqual(actor.wait_until, deadline)
                with self.assertRaises(ValueError):
                    actor.callback("/results", {"ids": ["b"], "ticket": ticket})
                actor.answers = {"a": {"content": "A"}, "b": {"content": "B"}}
                self.assertEqual(actor.callback("/results", query), {"results": [{"content": "A"}]})
                with self.assertRaises(ValueError):
                    actor.callback("/results", query)
                self.assertEqual(actor.callback("/results", {"ids": ["b"]}), {"results": [{"content": "B"}]})
                actor.answers.clear()
                actor.delivered = set()
                # 模拟下一步再次出现同样的 ID，上一轮编号也必须失效。
                actor.receipt_key = b"next-step"
                with self.assertRaises(ValueError):
                    actor.callback("/results", query)
                actor.wait_until = time.monotonic() - 1
                with self.assertRaises(ValueError):
                    actor.callback("/results", {"ids": ["a"]})
                actor.abort()
                with self.assertRaises(ValueError):
                    actor.callback("/results", query)

    def test_duplicate_callback_waiting_for_the_same_receipt_is_rejected(self):
        """同一回执到达前后交错的两个回调只有一个能够交付。@return 无。"""
        with (
            closing(self._driver()) as driver,
            closing(
                driver.prepare(self._identity("race"), encode(self._body()))
            ) as handle,
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            actor = handle.actor
            actor.step = WireStep([])
            actor.expected = [{"type": "tool_use", "id": "one"}]
            entered_wait = Event()
            wait = actor.changed.wait

            def observe_wait(timeout):
                entered_wait.set()
                return wait(timeout)

            with patch.object(actor.changed, "wait", side_effect=observe_wait):
                waiting = pool.submit(actor.callback, "/results", {"ids": ["one"]})
                try:
                    self.assertTrue(entered_wait.wait(2))
                    with actor.changed:
                        result = {
                            "type": "tool_result",
                            "tool_use_id": "one",
                            "content": "一次",
                        }
                        actor.answers = {"one": result}
                        self.assertEqual(
                            actor.callback("/results", {"ids": ["one"]}),
                            {"results": [result]},
                        )
                        actor.changed.notify_all()
                    with self.assertRaises(ValueError):
                        waiting.result(2)
                finally:
                    actor.abort()

    def test_real_wire_is_preserved_and_receipts_match_after_cache_moves(self):
        """带真实格式签名、部分工具参数与正文的 SSE 可逐帧交付，续轮仅忽略直接缓存标记迁移。@return 无。"""
        tools = [{"name": "MyTool"}]
        step = WireStep(tools)
        text = "假名🌸" * 4096
        events = [
            {
                "type": "message_start",
                "message": {
                    "id": "msg_original",
                    "model": "chosen",
                    "usage": {"input_tokens": 30},
                },
            },
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "thinking", "thinking": "", "signature": ""},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "想"},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "signature_delta", "signature": "signature"},
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "text", "text": ""},
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "text_delta", "text": text},
            },
            {"type": "content_block_stop", "index": 1},
            {
                "type": "content_block_start",
                "index": 2,
                "content_block": {
                    "type": "tool_use",
                    "id": "t",
                    "name": "MyTool",
                    "input": {},
                },
            },
            {
                "type": "content_block_delta",
                "index": 2,
                "delta": {"type": "input_json_delta", "partial_json": '{"arg":'},
            },
            {
                "type": "content_block_delta",
                "index": 2,
                "delta": {"type": "input_json_delta", "partial_json": '"yes"}'},
            },
            {"type": "content_block_stop", "index": 2},
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {"output_tokens": 5},
            },
            {"type": "message_stop"},
        ]
        source = b":keepalive\r\n\r\n" + b"".join(
            b"data: " + encode(e) + b"\r\n\r\n" for e in events
        )
        pieces = []
        for raw, event in wire_events(BytesIO(source)):
            step.observe(event)
            pieces.append(raw)
        self.assertEqual(b"".join(pieces), source)
        self.assertTrue(step.stopped)
        self.assertEqual(len(step.blocks[1]["text"]), 64)
        cached = {"type": "ephemeral", "ttl": "5m"}
        history = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "a", "cache_control": cached}],
            }
        ]
        assistant = {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "想", "signature": "signature"},
                {"type": "text", "text": text},
                {
                    "type": "tool_use",
                    "name": "MyTool",
                    "id": "t",
                    "input": {"arg": "yes"},
                },
            ],
        }
        returned = {
            "type": "tool_result",
            "tool_use_id": "t",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "AA==",
                    },
                }
            ],
            "cache_control": cached,
        }
        continuation = [
            {"role": "user", "content": "a"},
            assistant,
            {"role": "user", "content": [returned]},
            {"role": "system", "content": "尾部系统消息"},
        ]
        self.assertEqual(
            tool_receipts(continuation, history_digest(history), step.blocks),
            {"t": returned},
        )
        assistant["content"][0]["signature"] = "changed"
        with self.assertRaises(ValueError):
            tool_receipts(continuation, history_digest(history), step.blocks)

    def test_valid_history_after_end_turn_starts_without_stealing_tool_results(self):
        """完整旧历史后接新问题可开始新的 TUI；孤立的末尾回执需要原归属。@return 无。"""
        body = self._body()
        body["messages"] += [
            {"role": "assistant", "content": "一"},
            {"role": "user", "content": "二"},
        ]
        with closing(self._driver()) as driver:
            with closing(driver.prepare(self._identity("s"), encode(body))) as handle:
                self.assertEqual(handle.kind, "new")
                self.assertTrue(handle.stream)
                self.assertEqual(handle.raw, encode(body))
            body["messages"][-1]["content"] = [
                {"type": "tool_result", "tool_use_id": "lost", "content": "x"}
            ]
            with self.assertRaises(ValueError):
                driver.prepare(self._identity("s"), encode(body))

    def test_unrelated_native_call_cannot_claim_the_model(self):
        """同模型的辅助标题请求先到也不能占用已经存在的业务预留。@return 无。"""
        body = self._body()
        with (
            closing(self._driver()) as driver,
            closing(driver.prepare(self._identity("x"), encode(body))) as h,
        ):
            actor = h.actor
            actor.step = WireStep([])
            actor.step.native_model = "chosen"
            native = {
                "model": "chosen",
                "stream": True,
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": "标题请求"}]}
                ],
            }
            self.assertFalse(actor._main_request(native, h))
            native["messages"][0]["content"][0]["text"] = (
                "标题提示引用片段：" + actor.guard_text
            )
            self.assertFalse(actor._main_request(native, h))
            native["messages"][0]["content"][0]["text"] = (
                "<system-reminder>\nprompt.submit hook additional context: "
                + actor.guard_text
                + "\n</system-reminder>"
            )
            self.assertTrue(actor._main_request(native, h))
            native["messages"][0]["content"][0]["text"] += "\n"
            native["messages"].append(
                {
                    "role": "system",
                    "content": [{"type": "text", "text": "尾部原生上下文"}],
                }
            )
            self.assertTrue(actor._main_request(native, h))
            native["messages"].pop()
            h.kind = "continuation"
            h.answers = {"t": {}}
            actor.delivered = {"t"}
            self.assertFalse(actor._main_request(native, h))
            native["messages"][0]["content"] = [
                {"type": "tool_result", "tool_use_id": "t", "content": "x"}
            ]
            self.assertTrue(actor._main_request(native, h))
            h.kind = "new"

    def test_resumed_user_blocks_bind_the_latest_prompt_and_system_guard(self):
        """恢复失败轮后认领最后一个提示文本块及当前标记。@return 无。"""
        body = self._body()
        with (
            closing(self._driver()) as driver,
            closing(driver.prepare(self._identity("x"), encode(body))) as handle,
        ):
            actor = handle.actor
            actor.step = WireStep([])
            actor.step.native_model = "chosen"
            line = "prompt.submit hook additional context: " + actor.guard_text
            historical = {"type": "text", "text": "失败轮的用户输入\n"}
            prompt = {"type": "text", "text": body["messages"][0]["content"]}
            user = {"role": "user", "content": [historical, prompt]}
            system = {
                "role": "system",
                "content": [{"type": "text", "text": "原生环境\n\n" + line}],
            }
            native = {"model": "chosen", "stream": True, "messages": [user, system]}
            self.assertTrue(actor._main_request(native, handle))
            wrong = {
                "旧轮提示在末尾": [{**user, "content": [prompt, historical]}, system],
                "旧轮标记": [user, {**system, "content": [
                    {"type": "text", "text": "prompt.submit hook additional context: 旧轮"},
                ]}],
                "标记重复": [user, system, system],
                "缺少后续系统标记": [system, user],
            }
            for case, messages in wrong.items():
                with self.subTest(case=case):
                    self.assertFalse(actor._main_request({**native, "messages": messages}, handle))

    def test_current_text_blocks_must_reach_model_request_in_original_order(self):
        """原标记出站或 Mod 改写缺块时，保留本轮发送许可。@return 无。"""
        body = self._body()
        blocks = [{"type": "text", "text": part} for part in ("第一段", "第一段", "第二段")]
        body["messages"][-1]["content"] = blocks
        with closing(self._driver()) as driver:
            driver.managed_oauth = True
            identity = {**self._identity("x"), "native_cold_history": True}
            with closing(driver.prepare(identity, encode(body))) as handle:
                actor = handle.actor
                prompt = actor.callback("/prompt", {"marker": actor.marker})
                self.assertEqual(prompt["blocks"], blocks)
                self.assertEqual(prompt["prompt"], actor.marker)
                actor.step = WireStep([])
                actor.step.native_model = "chosen"
                guard = {"type": "text", "text": "<system-reminder>\nprompt.submit hook additional context: "
                                                   + actor.guard_text + "\n</system-reminder>"}
                user = {"role": "user", "content": [guard, *blocks]}
                native = {"model": "chosen", "stream": True, "messages": [user]}
                self.assertTrue(actor._main_request(native, handle))
                user["content"] = [guard, *reversed(blocks)]
                self.assertFalse(actor._main_request(native, handle))
                user["content"] = [guard, blocks[0], {"type": "text", "text": actor.marker}]
                self.assertFalse(actor._main_request(native, handle))

    def test_local_model_string_user_owns_only_its_trailing_system_guard(self):
        """DeepSeek 合并系统梯段时，用户正文、原生模型和独立随机标记行须同时匹配。@return 无。"""
        body = self._body()
        with (
            closing(self._driver()) as driver,
            closing(driver.prepare(self._identity("x"), encode(body))) as h,
        ):
            actor = h.actor
            actor.step = WireStep([])
            actor.step.native_model = "deepseek-flash"
            line = "prompt.submit hook additional context: " + actor.guard_text
            user = {"role": "user", "content": body["messages"][0]["content"]}
            system = {
                "role": "system",
                "content": [
                    {"type": "text", "text": "本轮上下文\n\n" + line + "\n\n日期"}
                ],
            }
            wire = {
                "model": "deepseek-flash",
                "stream": True,
                "messages": [user, system],
            }
            self.assertTrue(actor._main_request(wire, h))
            for wrong in (
                [{**user, "content": "辅助标题"}, system],
                [system, user],
                [user, {"role": "assistant", "content": []}, system],
                [
                    user,
                    {
                        "role": "system",
                        "content": [{"type": "text", "text": "引用：" + line}],
                    },
                ],
                [user, system, system],
            ):
                with self.subTest(rows=len(wrong)):
                    self.assertFalse(
                        actor._main_request({**wire, "messages": wrong}, h)
                    )
            self.assertFalse(actor._main_request({**wire, "model": "其他模型"}, h))

    def test_managed_quota_headers_follow_reserved_response(self):
        """实际事件发布前登记本轮上游额度。@return 无。"""
        events = [
            {"type": "message_start", "message": {}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
            {"type": "message_stop"},
        ]
        wire = b"".join(b"data: " + encode(event) + b"\n\n" for event in events)
        quota = {"anthropic-ratelimit-unified-5h-utilization": "0.25",
                 "anthropic-ratelimit-unified-5h-reset": "2030-01-01T12:00:00Z"}
        response = BytesIO(wire)
        response.status = 200
        response.headers = Message()
        response.headers["Content-Type"] = "text/event-stream"
        for name, value in quota.items():
            response.headers[name] = value
        response.getheader = response.headers.get

        with closing(self._driver()) as driver, ThreadPoolExecutor(1) as pool:
            driver.managed_oauth = True
            driver.launcher = Mock()
            driver.launcher.managed_model_response.return_value = response
            request = self._body()
            with closing(driver.prepare(self._identity("quota"), encode(request))) as handle:
                actor = handle.actor
                with patch.object(actor, "start"):
                    output = pool.submit(list, handle.send({"account_token": "synthetic"}))
                    try:
                        with actor.changed:
                            self.assertTrue(actor.changed.wait_for(lambda: actor.step is not None, 2))
                        turn = {"turn": "quota", "step": 0, "model": "chosen"}
                        actor.callback("/begin", turn)
                        marker = f"<system-reminder>\nprompt.submit hook additional context: {actor.guard_text}\n</system-reminder>"
                        native = {**request, "messages": [{"role": "user", "content": [{"type": "text", "text": marker}]}]}
                        actor.serve_model(Mock(headers={}), native)
                        self.assertEqual(handle.quota_headers, quota)
                        actor.callback("/end", {**turn, "reason": "end_turn"})
                        actor.callback("/complete", {"turn": turn["turn"], "aborted": False})
                        self.assertEqual(b"".join(output.result(2)), wire)
                    finally:
                        actor.abort()

    def test_signature_repair_sends_twice_in_one_claimed_native_step(self):
        """签名拒绝由原步骤恢复，同一请求的原生回调只认领一次。@return 无。"""
        events = [
            {"type": "message_start", "message": {}},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
            {"type": "message_stop"},
        ]
        wire = b"".join(b"data: " + encode(event) + b"\n\n" for event in events)
        response = BytesIO(wire)
        response.status = 200
        response.getheader = lambda _name, _default=None: "text/event-stream"
        first = ModelResponseError(
            400,
            encode({"error": {"type": "invalid_request_error", "message": "Invalid signature in thinking block"}}),
            source="local_provider_http", complete=True,
        )
        self.assertIsNotNone(first.signature_evidence)
        with closing(self._driver()) as driver, ThreadPoolExecutor(1) as pool:
            driver.launcher = Mock()
            driver.launcher.local_model_response.side_effect = [first, response]
            request = {**self._body(), "thinking": {"type": "adaptive"}}
            repaired = encode(self._body())
            with closing(driver.prepare(self._identity("repair"), encode(request))) as handle:
                actor = handle.actor
                admitted = Mock(return_value=(repaired, "714b32be-b08a-464a-bae9-83cce37cd225"))
                handle.signature_exchange = admitted
                with patch.object(actor, "start") as start:
                    output = pool.submit(list, handle.send({}))
                    try:
                        with actor.changed:
                            self.assertTrue(actor.changed.wait_for(lambda: actor.step is not None, 2))
                        step = actor.step
                        turn = {"turn": "repair", "step": 0, "model": "chosen"}
                        actor.callback("/begin", turn)
                        marker = f"<system-reminder>\nprompt.submit hook additional context: {actor.guard_text}\n</system-reminder>"
                        native = {**request, "messages": [{"role": "user", "content": [{"type": "text", "text": marker}]}]}
                        actor.serve_model(Mock(headers={}), native)
                        duplicate = Mock(headers={})
                        actor.serve_model(duplicate, native)
                        duplicate.send_error.assert_called_once_with(409, "No pending model step")
                        self.assertIs(actor.step, step)
                        self.assertTrue(step.claimed)
                        self.assertEqual(handle.repair_attempt_id, "714b32be-b08a-464a-bae9-83cce37cd225")
                        start.assert_called_once()
                        calls = driver.launcher.local_model_response.call_args_list
                        self.assertEqual(len(calls), 2)
                        admitted.assert_called_once_with(calls[0].args[0], first)
                        self.assertEqual(calls[1].args[0], repaired)
                        actor.callback("/end", {**turn, "reason": "end_turn"})
                        actor.callback("/complete", {"turn": turn["turn"], "aborted": False})
                        self.assertEqual(b"".join(output.result(2)), wire)
                    finally:
                        actor.abort()

    def test_http_model_error_keeps_status_and_messages_fields(self):
        """首帧前转交上游错误，保留状态和公开字段。@return 无。"""
        err = ModelResponseError(
            429,
            encode(
                {
                    "error": {
                        "type": "rate_limit_error",
                        "message": "稍后再试",
                        "internal": "meta",
                    }
                }
            ),
        )
        self.assertEqual(err.status, 429)
        self.assertEqual(
            json.loads(err.body),
            {
                "type": "error",
                "error": {"type": "rate_limit_error", "message": "稍后再试"},
            },
        )


if __name__ == "__main__":
    unittest.main()
