"""核对冷导入边界、记录归属和工具声明。"""

from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from tui_cold_history import ColdHistory


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

    def test_private_session_contains_only_completed_history(self):
        """检查导入只含已完成的原历史，并使用独立会话 ID。@return 无。"""
        plan = ColdHistory.from_request(self.body)
        self.assertEqual(plan.prompt, "本轮输入")
        self.assertEqual(plan.system, "业务指令一\n业务指令二")
        with TemporaryDirectory() as directory:
            config = Path(directory)
            history = plan.import_session(config, Path("/native/workspace"))
            other = plan.import_session(config, Path("/native/workspace"))
            self.assertNotEqual(history, other)
            self.assertEqual(history.stat().st_mode & 0o777, 0o600)
            rows = [json.loads(line) for line in history.read_text().splitlines()]
            self.assertEqual([row["type"] for row in rows], ["user", "assistant", "user", "assistant"])
            self.assertEqual([row["parentUuid"] for row in rows], [None, *[row["uuid"] for row in rows[:-1]]])
            self.assertEqual({row["sessionId"] for row in rows}, {history.stem})
            self.assertEqual(rows[1]["message"]["content"], self.body["messages"][1]["content"])
            self.assertEqual(rows[2]["message"]["content"], self.body["messages"][2]["content"])

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
