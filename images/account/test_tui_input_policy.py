"""检查普通 API、原生扩展和模型业务副本之间的兼容边界。"""

import json
import unittest

from tui_input_policy import InputRejection, direct_model_options
from tui_messages import MessageInputObservation, input_message


class InputPolicyTests(unittest.TestCase):
    """固定 native293 公开错误分类，以及发送给模型的正文范围。"""

    def setUp(self):
        """初始化本组的独立会话标识和无扩展请求。@return 无。"""
        self.session = "00000000-0000-0000-0000-000000000001"
        self.body = {
            "model": "model",
            "messages": [{"role": "user", "content": "合成"}],
            "stream": True,
        }
        self.native = {
            **self.body,
            "system": [
                {
                    "type": "text",
                    "text": "You are Claude Code, Anthropic's official CLI for Claude.",
                }
            ],
            "metadata": {
                "user_id": json.dumps(
                    {
                        "session_id": self.session,
                        "device_id": "0" * 64,
                        "account_uuid": "",
                    }
                )
            },
        }

    def test_metadata_is_private_but_nested_tool_data_is_business(self):
        """剥除普通 API 的顶层 metadata 并核对原会话；同名工具参数原样保留。@return 无。"""
        schema = {"type": "object", "properties": {"metadata": {"type": "string"}}}
        fields = {
            "audit": "synthetic",
            "user_id": json.dumps({"session_id": self.session}),
        }
        body = {
            **self.body,
            "tools": [{"name": "Echo", "input_schema": schema}],
            "metadata": fields,
        }
        for cli in (False, True):
            parsed, _, wire = input_message(
                json.dumps(body), native=cli, session_id=self.session
            )
            self.assertNotIn("metadata", json.loads(wire))
            self.assertEqual(parsed["tools"][0]["input_schema"], schema)
        for invalid, code in [
            ({"user_id": 7}, "invalid_metadata"),
            ({"user_id": '{"session_id":123}'}, "invalid_metadata"),
            ({"user_id": '{"session_id":"different"}'}, "context_conflict"),
        ]:
            with self.subTest(code=code), self.assertRaisesRegex(InputRejection, code):
                input_message(
                    json.dumps({**self.body, "metadata": invalid}),
                    session_id=self.session,
                )

    def test_direct_options_are_typed_and_must_match_declarations(self):
        """只交付已校验的逐步参数。选择名称必须属于当前调用方声明。@return 无。"""
        body = {**self.body, "tools": [{"name": "Echo", "input_schema": {}}]}
        for parameters, reason in (
            ({"output_config": {"format": {"type": "json_schema"}}}, "invalid_parameter"),
            ({"tool_choice": {"type": "tool", "name": "Unknown"}}, "invalid_parameter"),
            ({"tool_choice": {"type": "any"}, "tools": []}, "invalid_parameter"),
            ({"tool_choice": {"type": "auto", "disable_parallel_tool_use": 1}}, "invalid_parameter"),
            ({"temperature": 1.2}, "invalid_temperature"),
        ):
            with self.subTest(parameters=parameters), self.assertRaisesRegex(InputRejection, reason):
                direct_model_options({**body, **parameters})
        for choice in ({"type": "tool", "name": "Echo"}, {"type": "auto", "disable_parallel_tool_use": True},
                       {"type": "any"}, {"type": "none"}):
            with self.subTest(choice=choice):
                self.assertEqual(direct_model_options({**body, "tool_choice": choice}), {"tool_choice": choice})
        schema = {"type": "json_schema", "schema": {"type": "object", "additionalProperties": False}}
        self.assertEqual(direct_model_options({**body, "output_config": {"effort": "medium", "format": schema},
                                               "temperature": 0.4}),
                         {"output_config": {"format": schema}, "temperature": 0.4})
        for choice in ({"type": "auto"}, {"type": "auto", "disable_parallel_tool_use": False}):
            self.assertEqual(direct_model_options({**body, "tool_choice": choice}), {})

    def test_native_and_api_have_different_allowlists(self):
        """API 根字段与 V1 逐项一致，原生保留扩展和空 MCP，非空服务器声明拒绝。@return 无。"""
        for key in (
            "top_p",
            "top_k",
            "stop_sequences",
            "service_tier",
            "inference_geo",
            "cache_control",
            "safeguards",
            "speed",
            "future_model_option",
            "mcp_servers",
        ):
            with (
                self.subTest(key=key),
                self.assertRaisesRegex(InputRejection, "unsupported_parameter"),
            ):
                input_message(json.dumps({**self.body, key: []}), native=True)
        raw = json.dumps(
            {
                **self.native,
                "mcp_servers": [],
                "nested_option": {"metadata": "模型参数"},
            }
        ).encode()
        self.assertIs(input_message(raw, native=True)[2], raw)
        for config in ([{"type": "url"}], {}, None):
            with (
                self.subTest(config=config),
                self.assertRaisesRegex(InputRejection, "unsupported_parameter"),
            ):
                input_message(
                    json.dumps({**self.native, "mcp_servers": config}), native=True
                )
        with self.assertRaisesRegex(InputRejection, "invalid_native_request"):
            input_message(
                json.dumps({**self.native, "metadata": {"user_id": "invalid"}}),
                native=True,
            )
        with self.assertRaisesRegex(InputRejection, "invalid_native_request"):
            input_message(json.dumps(self.native), native="claude_code_280")

    def test_sender_instruction_location_uses_ordinary_top_level_system(self):
        """代发观测只使用实际普通顶层文本。@return 无。"""
        for body, expected in (
            (self.body, None),
            ({**self.body, "system": "  "}, None),
            ({**self.body, "system": [{"type": "text", "text": "业务指令"}]}, "system"),
            (self.native, None),
        ):
            with self.subTest(expected=expected, native=body is self.native):
                observed = MessageInputObservation()
                input_message(json.dumps(body), native="claude_code_293" if body is self.native else False,
                              observation=observed)
                self.assertEqual(observed.instruction_location, expected)

    def test_api_and_context_message_system_blocks(self):
        """业务 system 依 V1 的普通构造与显式消息级 system 区分；不以系统提示冒充原生。@return 无。"""
        block = {
            "type": "text",
            "text": "business",
            "cache_control": {"type": "ephemeral"},
        }
        with self.assertRaisesRegex(InputRejection, "unsupported_parameter"):
            input_message(json.dumps({**self.body, "system": [block]}))
        timed = {
            "role": "system",
            "content": "scope",
            "clear_at": "next_user_message",
            "output_config": {},
        }
        raw = json.dumps(
            {
                **self.body,
                "system": [block],
                "messages": [timed, *self.body["messages"]],
            }
        ).encode()
        self.assertIs(input_message(raw, native=True)[2], raw)
        for extra, expected in [
            ({"clear_at": "past"}, "invalid_parameter"),
            ({"unknown": False}, "unsupported_parameter"),
        ]:
            with self.assertRaisesRegex(InputRejection, expected):
                input_message(
                    json.dumps({**self.body, "messages": [{**timed, **extra}]})
                )

    def test_basic_api_types_follow_native293_errors(self):
        """同一组通用结构错误返回对应的 V1 错误码。@return 无。"""
        for fields, code in [
            ({"model": ""}, "invalid_model"),
            ({"messages": []}, "invalid_messages"),
            ({"messages": [{"role": "other", "content": ""}]}, "invalid_message"),
            ({"messages": [{"role": "user", "content": [1]}]}, "invalid_content"),
            ({"system": [1]}, "invalid_system"),
            ({"tools": {}}, "invalid_tools"),
            ({"output_config": False}, "invalid_parameter"),
            ({"thinking": 0}, "invalid_parameter"),
            ({"tool_choice": []}, "invalid_parameter"),
            ({"stream": "true"}, "invalid_stream"),
            ({"max_tokens": True}, "invalid_max_tokens"),
            ({"temperature": "x"}, "invalid_temperature"),
        ]:
            with (
                self.subTest(fields=fields),
                self.assertRaisesRegex(InputRejection, code),
            ):
                input_message(json.dumps({**self.body, **fields}))

    def test_context_management_preserves_rules_and_rejects_wrong_shapes(self):
        """明确区分未实现字段或类型 422 与已知指令的结构错误 400。@return 无。"""
        thinking = {
            "type": "clear_thinking_20251015",
            "keep": {"type": "thinking_turns", "value": 1},
        }
        tool = {
            "type": "clear_tool_uses_20250919",
            "trigger": {"type": "input_tokens", "value": 0},
            "keep": {"type": "tool_uses", "value": 40},
            "clear_at_least": {"type": "input_tokens", "value": 0},
            "exclude_tools": ["echo"],
            "clear_tool_inputs": False,
        }
        for config in ({}, {"edits": []}, {"edits": [thinking, tool]}):
            raw = json.dumps({**self.body, "context_management": config}).encode()
            self.assertIs(input_message(raw)[2], raw)
        rejected = [
            ({"unknown": True}, "unsupported_parameter"),
            ({"edits": [{"type": "new"}]}, "unsupported_parameter"),
            ({"edits": [{**tool, "future": 1}]}, "unsupported_parameter"),
        ]
        for v in (
            None,
            [],
            {"edits": None},
            {"edits": "wrong"},
            {"edits": [2]},
            {"edits": [tool, thinking]},
            {"edits": [thinking, thinking]},
            {"edits": [{**thinking, "keep": None}]},
            {"edits": [{**tool, "exclude_tools": [""]}]},
            {"edits": [{**tool, "clear_tool_inputs": 1}]},
        ):
            rejected.append((v, "invalid_context_management"))
        for count in (True, -1, 2**53, 1.5):
            rejected.append(
                (
                    {
                        "edits": [
                            {**tool, "keep": {"type": "tool_uses", "value": count}}
                        ]
                    },
                    "invalid_context_management",
                )
            )
        for config, code in rejected:
            with (
                self.subTest(config=config),
                self.assertRaisesRegex(InputRejection, code),
            ):
                input_message(json.dumps({**self.body, "context_management": config}))
