"""按网关使用的最终消息格式验证真实增量的离线聚合。"""

import json
from io import BytesIO
from unittest import TestCase

from tui_message_json import MessageJSON, ModelError
from tui_messages import WireStep, history_digest, tool_receipts, wire_events


class MessageJSONTests(TestCase):
    """覆盖交错的块、累计用量、原始工具标识和正常化上限。"""

    @staticmethod
    def opened(limit=10 * 1024**2):
        """提供已开始的合成消息。@param limit 最终 JSON 预算。@return 本轮聚合器。"""
        result = MessageJSON(limit)
        result.add(
            {
                "type": "message_start",
                "message": {
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                    "id": "msg_origin",
                    "model": "fixture",
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": 20,
                        "output_tokens": 1,
                        "cache_read_input_tokens": 8,
                        "cache_creation": {"ephemeral_1h_input_tokens": 3},
                    },
                },
            }
        )
        return result

    @staticmethod
    def start(result, index, **block):
        """发布块起点。@param result 聚合器。@param index 块索引。@param block 原块。@return 无。"""
        result.add(
            {"type": "content_block_start", "index": index, "content_block": block}
        )

    @staticmethod
    def delta(result, index, **part):
        """发布片段。@param result 聚合器。@param index 块索引。@param part 原增量。@return 无。"""
        result.add({"type": "content_block_delta", "index": index, "delta": part})

    def test_interleaved_multiple_text_and_same_name_tools(self):
        """两段文本与两个同名工具独立累积，保留原顺序、ID 及累计用量。@return 无。"""
        result = self.opened()
        self.start(result, 0, type="text", text="头")
        self.start(result, 1, type="tool_use", id="tool_a", name="read", input={})
        self.start(result, 2, type="tool_use", id="tool_b", name="read", input={})
        self.start(result, 3, type="text", text="")
        self.delta(result, 1, type="input_json_delta", partial_json='{"x":')
        self.delta(result, 2, type="input_json_delta", partial_json="")
        self.delta(result, 3, type="text_delta", text='尾🌸\n"')
        self.delta(result, 0, type="text_delta", text="中")
        self.delta(result, 1, type="input_json_delta", partial_json='["中",2]}')
        for idx in (2, 1, 3, 0):
            result.add({"type": "content_block_stop", "index": idx})
        result.add(
            {
                "type": "message_delta",
                "delta": {"stop_reason": "tool_use"},
                "usage": {
                    "output_tokens": 19,
                    "cache_creation": {"ephemeral_5m_input_tokens": 6},
                },
            }
        )
        result.add({"type": "message_stop"})
        message = json.loads(result.finish())
        self.assertEqual(message["id"], "msg_origin")
        self.assertEqual(message["stop_reason"], "tool_use")
        self.assertEqual(
            message["usage"],
            {
                "input_tokens": 20,
                "output_tokens": 19,
                "cache_read_input_tokens": 8,
                "cache_creation": {
                    "ephemeral_1h_input_tokens": 3,
                    "ephemeral_5m_input_tokens": 6,
                },
            },
        )
        self.assertEqual(
            message["content"],
            [
                {"type": "text", "text": "头中"},
                {
                    "type": "tool_use",
                    "name": "read",
                    "id": "tool_a",
                    "input": {"x": ["中", 2]},
                },
                {"type": "tool_use", "name": "read", "id": "tool_b", "input": {}},
                {"type": "text", "text": '尾🌸\n"'},
            ],
        )

    def test_large_fragmented_unicode_is_exact_and_limits_are_errors(self):
        """多兆字节的 JSON 输出按最终预算交付，超预算明确报错且不截断。@return 无。"""
        result = self.opened()
        self.start(result, 0, type="text", text="")
        piece = "🌸" * 1024
        for _ in range(2030):
            self.delta(result, 0, type="text_delta", text=piece)
        result.add({"type": "content_block_stop", "index": 0})
        result.add({"type": "message_delta", "delta": {"stop_reason": "end_turn"}})
        result.add({"type": "message_stop"})
        self.assertEqual(
            json.loads(result.finish())["content"][0]["text"], piece * 2030
        )
        limited = self.opened(2048)
        self.start(limited, 0, type="text", text="")
        with self.assertRaises(ModelError):
            self.delta(limited, 0, type="text_delta", text=piece)

    def test_real_sse_fields_and_incomplete_tool(self):
        """校验注释、多行和 CRLF 事件，以及未闭合工具参数的失败结果。@return 无。"""
        records = BytesIO(
            b': heartbeat\r\n\r\nevent: ping\r\ndata: {\r\ndata: "type":"ping"}\r\n\r\n'
        )
        self.assertEqual(
            [value for _, value in wire_events(records)], [None, {"type": "ping"}]
        )
        result = self.opened()
        self.start(result, 0, type="tool_use", id="test", name="tool", input={})
        self.delta(result, 0, type="input_json_delta", partial_json='{"broken":')
        with self.assertRaises(ValueError):
            result.add({"type": "content_block_stop", "index": 0})
        with self.assertRaises(ValueError):
            result.finish()

    def test_thinking_signature_and_nullable_initial_citations(self):
        """分片签名、引用和原生脱敏思考块进入同一份最终响应。@return 无。"""
        result = self.opened()
        self.start(result, 0, type="thinking", thinking="", signature="")
        self.delta(result, 0, type="thinking_delta", thinking="思考")
        self.delta(result, 0, type="signature_delta", signature="one-")
        self.delta(result, 0, type="signature_delta", signature="two")
        result.add({"type": "content_block_stop", "index": 0})
        self.start(result, 1, type="text", text="", citations=None)
        citation = {"type": "char_location", "start_char_index": 0, "end_char_index": 2}
        self.delta(result, 1, type="citations_delta", citation=citation)
        result.add({"type": "content_block_stop", "index": 1})
        self.start(result, 2, type="redacted_thinking", data="opaque")
        result.add({"type": "content_block_stop", "index": 2})
        result.add(
            {
                "type": "message_delta",
                "delta": {"stop_reason": "stop_sequence", "stop_sequence": "结束"},
            }
        )
        result.add({"type": "message_stop"})
        final = json.loads(result.finish())
        self.assertEqual(final["stop_sequence"], "结束")
        self.assertEqual(
            final["content"],
            [
                {"type": "thinking", "thinking": "思考", "signature": "one-two"},
                {"type": "text", "text": "", "citations": [citation]},
                {"type": "redacted_thinking", "data": "opaque"},
            ],
        )
    def test_live_and_json_consumers_share_interleaved_tool_ownership(self):
        """逆序关闭两项工具时，流归属与 JSON 的同名工具输入、标识和顺序一致。@return 无。"""
        result = self.opened()
        step = WireStep([{"name": "read"}])
        step.observe({"type": "message_start", "message": {}})

        def emit(kind, **fields):
            event = {"type": kind, **fields}
            step.observe(event)
            result.add(event)

        for i, name in enumerate(("tool_a", "tool_b")):
            emit("content_block_start", index=i, content_block={"type":"tool_use", "id":name, "name":"read", "input":{}})
        for i, piece in ((0, '{"v":'), (1, '{"v":'), (1, '2}'), (0, '1}')):
            emit("content_block_delta", index=i, delta={"type":"input_json_delta", "partial_json":piece})
        emit("content_block_stop", index=1)
        self.assertEqual([b["id"] for b in step.blocks], ["tool_b"])
        emit("content_block_stop", index=0)
        emit("message_delta", delta={"stop_reason":"tool_use"}, usage={"output_tokens":2})
        emit("message_stop")
        blocks = json.loads(result.finish())["content"]
        self.assertEqual(step.blocks, blocks)
        self.assertEqual([b["input"] for b in blocks], [{"v":1}, {"v":2}])
        previous = [{"role":"user", "content":"请读取两项"}]
        answers = [{"type":"tool_result", "tool_use_id":name, "content":name} for name in ("tool_b","tool_a")]
        follow = [*previous, {"role":"assistant","content":blocks}, {"role":"user","content":answers}]
        self.assertEqual(set(tool_receipts(follow, history_digest(previous), step.blocks)), {"tool_a","tool_b"})
