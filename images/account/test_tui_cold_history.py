"""核对冷导入边界、记录归属和工具声明。"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import TestCase
from uuid import uuid4

from tui_cold_history import ColdHistory
from tui_workspace_launch import _resume_path


class ColdHistoryTests(TestCase):
    """使用合成输入测试固定 CLI 的历史合同。"""

    def setUp(self):
        """建立带已完成工具组的对话。@return 无。"""
        self.body = {
            "model": "claude-sonnet-4-6", "max_tokens": 128,
            "system": [{"type": "text", "text": "业务指令一"}, {"type": "text", "text": "业务指令二"}],
            "tools": [{"name": "LookupNote", "input_schema": {"type": "object"}}],
            "messages": [
                {"role": "user", "content": "上一轮输入"},
                {"role": "assistant", "content": [
                    {"type": "tool_use", "id": "toolu_old", "name": "LookupNote", "input": {}}]},
                {"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_old", "content": "上一轮结果"}]},
                {"role": "assistant", "content": "上一轮答复"},
                {"role": "user", "content": "本轮输入"},
            ],
        }

    def test_bound_history_is_idempotent_and_readable_after_restart(self):
        """核对同一绑定只写入已完成的历史，重启后由启动器读回。@return 无。"""
        plan = ColdHistory.from_request(self.body)
        self.assertEqual(plan.prompt, "本轮输入")
        self.assertEqual(plan.system, "业务指令一\n业务指令二")
        session = str(uuid4())
        work = Path("/native/workspace")
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            self.assertEqual(plan.import_session(config, work, session), session)
            history = _resume_path(stack, config, work, session, required=True)
            initial = history.read_bytes()
            restored = ColdHistory.from_request(deepcopy(self.body))
            self.assertEqual(restored.import_session(config, work, session), session)
            self.assertEqual(history.read_bytes(), initial)
            self.assertEqual(list(history.parent.iterdir()), [history])
            self.assertEqual(history.stat().st_mode & 0o777, 0o600)
            rows = [json.loads(line) for line in initial.splitlines()]
            self.assertEqual([row["type"] for row in rows], ["user", "assistant", "user", "assistant"])
            self.assertEqual([row["parentUuid"] for row in rows], [None, *[row["uuid"] for row in rows[:-1]]])
            self.assertEqual({row["sessionId"] for row in rows}, {session})
            self.assertEqual(rows[1]["message"]["content"], self.body["messages"][1]["content"])
            self.assertEqual(rows[2]["message"]["content"], self.body["messages"][2]["content"])

    def test_concurrent_imports_preserve_winning_history(self):
        """相同并发导入复用原文件，分歧历史保留原文件并使用独立会话。@return 无。"""
        first = ColdHistory.from_request(self.body)
        changed = deepcopy(self.body)
        changed["messages"][0]["content"] = "另一条已确认的上一轮输入"
        second = ColdHistory.from_request(changed)
        work = Path("/native/workspace")
        session = str(uuid4())
        with TemporaryDirectory() as directory, ThreadPoolExecutor(max_workers=3) as pool, ExitStack() as stack:
            config = Path(directory)
            barrier = Barrier(3)

            def prepare(plan):
                barrier.wait(timeout=5)
                return plan.import_session(config, work, session)

            futures = [pool.submit(prepare, plan) for plan in (first, first, first)]
            self.assertEqual([future.result() for future in futures], [session] * 3)
            original = _resume_path(stack, config, work, session, required=True)
            original_bytes = original.read_bytes()
            self.assertEqual(list(original.parent.iterdir()), [original])
            barrier = Barrier(2)
            futures = [pool.submit(prepare, plan) for plan in (first, second)]
            same, fork = (future.result() for future in futures)
            self.assertEqual(same, session)
            self.assertNotEqual(fork, session)
            self.assertEqual(original.read_bytes(), original_bytes)
            forked = _resume_path(stack, config, work, fork, required=True)
            self.assertEqual(json.loads(forked.read_bytes().splitlines()[0])["message"]["content"][0]["text"],
                             "另一条已确认的上一轮输入")

    def test_mismatched_disk_owner_is_not_replaced_or_used(self):
        """已有文件的原生会话或目录发生变化时拒绝恢复并保留文件。@return 无。"""
        plan = ColdHistory.from_request(self.body)
        work = Path("/native/workspace")
        session = str(uuid4())
        with TemporaryDirectory() as directory, ExitStack() as stack:
            config = Path(directory)
            plan.import_session(config, work, session)
            path = _resume_path(stack, config, work, session, required=True)
            payload = path.read_text().replace(str(work), "/native/other")
            path.write_text(payload)
            with self.assertRaisesRegex(ValueError, "工作区不匹配"):
                plan.import_session(config, work, session)
            self.assertEqual(path.read_text(), payload)

    def test_unpaired_and_unsupported_inputs_use_existing_contract(self):
        """检查缺配对及扩展字段按原入口合同准入。@return 无。"""
        missing = deepcopy(self.body)
        missing["messages"][2]["content"][0]["tool_use_id"] = "toolu_other"
        self.assertIsNone(ColdHistory.from_request(missing))
        self.assertIsNone(ColdHistory.from_request({**self.body, "tool_choice": {"type": "any"}}))
        cached = deepcopy(self.body)
        cached["system"][0]["cache_control"] = {"type": "ephemeral"}
        self.assertIsNone(ColdHistory.from_request(cached))

    def test_mcp_only_advertises_this_sessions_declarations(self):
        """检查 MCP 只提供本次准入的定义，执行由原回执链处理。@return 无。"""
        plan = ColdHistory.from_request(self.body)
        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        self.assertEqual(plan.mcp(request)["result"]["tools"], [
            {"name": "LookupNote", "description": "", "inputSchema": {"type": "object"}},
        ])
        self.assertIn("error", plan.mcp({**request, "method": "tools/call"}))
