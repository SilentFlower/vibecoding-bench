"""验证公开双工具夹具按声明的 JSON 类型执行合成回调。"""

from copy import deepcopy
from unittest import TestCase

import verify_tui_cold_history as fixture


class ParallelToolFixtureTests(TestCase):
    """核对 Set-Tag 的合法布尔参数及数字反例。"""

    def test_boolean_false_produces_the_original_error_receipt(self):
        """布尔 false 通过校验并按原 ID 交回预期错误。@return 无。"""
        callbacks = []
        result = fixture.fixture_parallel_results([{
            "id": fixture.SECOND_ID,
            "name": fixture.PARALLEL_SECOND_TOOL["name"],
            "input": {"tag_id": 74, "active": False},
        }], callbacks)

        self.assertEqual(callbacks, [fixture.SECOND_ID])
        self.assertEqual(result, [{"type": "tool_result", "tool_use_id": fixture.SECOND_ID,
                                   "content": fixture.SECOND_REPLY, "is_error": True}])

    def test_numeric_zero_fails_before_recording_the_callback(self):
        """数字零触发参数校验失败。@return 无。"""
        callbacks = []
        with self.assertRaises(AssertionError):
            fixture.fixture_parallel_results([{
                "id": fixture.SECOND_ID,
                "name": fixture.PARALLEL_SECOND_TOOL["name"],
                "input": {"tag_id": 74, "active": 0},
            }], callbacks)

        self.assertEqual(callbacks, [])

    def test_serial_model_contract_preserves_json_booleans(self):
        """核对布尔禁并行和嵌套声明，数字替代分别触发断言。@return 无。"""
        tools = [fixture.TOOL, fixture.PARALLEL_SECOND_TOOL]
        choice = fixture.SERIAL_AUTO
        model = {"tools": deepcopy(tools), "tool_choice": dict(reversed(list(choice.items())))}
        fixture._verify_serial_model_tools(model, tools, choice, "append_disabled")

        numeric_choice = {**model, "tool_choice": {**choice, "disable_parallel_tool_use": 1}}
        with self.assertRaisesRegex(AssertionError, "disable_parallel_tool_use.*1"):
            fixture._verify_serial_model_tools(numeric_choice, tools, choice, "append_disabled")

        model["tools"][0]["input_schema"]["properties"]["options"]["additionalProperties"] = 0
        with self.assertRaisesRegex(AssertionError, "additionalProperties.*0"):
            fixture._verify_serial_model_tools(model, tools, choice, "append_disabled")
