"""验证账号源冻结的模型正文、原始工具历史和 V1 缓存规则。"""

import json
import unittest

from tui_messages import input_message


def _policy(sub2api=True, ttl="off", adaptive=False):
    return {"sub2api": sub2api, "ttl": ttl, "adaptive": adaptive}


def _cache(ttl):
    return {"type": "ephemeral", "ttl": ttl}


def _text(text, **extra):
    return {"type": "text", "text": text, **extra}


def _request(rows, **extra):
    return {
        "model": "chosen",
        "stream": True,
        "messages": [{"role": role, "content": content} for role, content in rows],
        **extra,
    }


def _native_metadata():
    return {
        "user_id": json.dumps(
            {
                "device_id": "0" * 64,
                "account_uuid": "",
                "session_id": "00000000-0000-0000-0000-000000000001",
            }
        )
    }


def _wire(body, policy, *, native=False):
    raw = json.dumps(body, indent=2).encode()
    parsed, _, wire = input_message(raw, body_policy=policy, native=native)
    return parsed, wire, raw


class PolicyTests(unittest.TestCase):
    """按实际模型字节检查布局、继承、批量覆盖及原始历史。"""

    def test_prefix_budget_prioritizes_tail_and_only_normalizes_selected_strings(self):
        """同时覆盖无前缀直到四个前缀断点，尾部优先，原历史形状保留。@return 无。"""
        old = _text("old", cache_control={"future": 1})
        for count in range(5):
            with self.subTest(count=count):
                prefix = [
                    _text(str(i), cache_control=_cache("5m")) for i in range(count)
                ]
                body = _request(
                    [
                        ("user", [old]),
                        ("assistant", "a"),
                        ("user", "b"),
                        ("assistant", "c"),
                        ("user", "d"),
                    ],
                    metadata=_native_metadata(),
                    system=[
                        _text(
                            "You are Claude Code, Anthropic's official CLI for Claude."
                        ),
                        *prefix,
                    ],
                )
                parsed, wire, _ = _wire(body, _policy(), native=True)
                outgoing = json.loads(wire)
                self.assertEqual(parsed, body)
                self.assertEqual(outgoing["system"], body["system"])
                ttl = "5m" if count else "1h"
                self.assertEqual(
                    [m["content"] for m in outgoing["messages"]],
                    [
                        [_text("old")],
                        "a",
                        [_text("b", cache_control=_cache(ttl))] if count < 3 else "b",
                        "c",
                        [_text("d", cache_control=_cache(ttl))] if count < 4 else "d",
                    ],
                )

    def test_unknown_layout_and_combined_noop_preserve_raw_bytes(self):
        """根缓存、嵌套缓存、短时长在前及最终语义未变时保留原 HTTP 正文字节。@return 无。"""
        row = [("user", "x")]
        cases = [
            _request(
                row,
                cache_control=None,
                metadata=_native_metadata(),
                system=[
                    _text("You are Claude Code, Anthropic's official CLI for Claude.")
                ],
            ),
            _request(row, system=[_text("sys", cache_control={"type": "future"})]),
            _request(
                row,
                system=[_text("sys", cache_control=_cache("1h"))],
                tools=[
                    {"name": "t", "input_schema": {}, "cache_control": _cache("5m")}
                ],
            ),
            _request(
                [
                    (
                        "user",
                        [
                            {
                                "type": "tool_result",
                                "content": [_text("nested", cache_control=None)],
                            }
                        ],
                    )
                ]
            ),
            _request(
                [
                    (
                        "assistant",
                        [
                            {
                                "type": "thinking",
                                "thinking": "private",
                                "signature": "sig",
                            },
                            _text(""),
                            {"type": "tool_result"},
                        ],
                    )
                ]
            ),
        ]
        for body in cases:
            with self.subTest(body=body):
                if "system" in body and "metadata" not in body:
                    body = {
                        **body,
                        "metadata": _native_metadata(),
                        "system": [
                            _text(
                                "You are Claude Code, Anthropic's official CLI for Claude."
                            ),
                            *body["system"],
                        ],
                    }
                _, wire, raw = _wire(body, _policy(), native="metadata" in body)
                self.assertIs(wire, raw)
        _, wire, raw = _wire(
            _request([("user", [_text("x", cache_control=_cache("5m"))])]),
            _policy(ttl="5m"),
        )
        self.assertIs(wire, raw)

    def test_ttl_and_thinking_change_only_protocol_fields_and_keep_large_integers(self):
        """顶层兼容和已有 TTL 独立生效，工具参数、schema、签名及嵌套结果原值保留。@return 无。"""
        business = {"cache_control": _cache("5m"), "integer": 10**60 + 1}
        signed = {"type": "thinking", "thinking": "文本", "signature": "opaque"}
        call = {"type": "tool_use", "id": "id", "name": "Read", "input": business}
        nested = [_text("inner", **business)]
        result = {
            "type": "tool_result",
            "tool_use_id": "id",
            "content": nested,
            "cache_control": _cache("5m"),
        }
        body = _request(
            [("assistant", [signed, call]), ("user", [result])],
            cache_control=_cache("5m"),
            system=[
                _text("You are Claude Code, Anthropic's official CLI for Claude."),
                _text("s", cache_control=_cache("5m")),
            ],
            metadata=_native_metadata(),
            tools=[
                {
                    "name": "Read",
                    "input_schema": business,
                    "cache_control": _cache("5m"),
                }
            ],
            thinking={"type": "disabled", "extension": 2},
        )
        parsed, wire, _ = _wire(body, _policy(ttl="1h", adaptive=True), native=True)
        expected = json.loads(json.dumps(body))
        for block in (
            expected,
            expected["system"][1],
            expected["tools"][0],
            expected["messages"][1]["content"][0],
        ):
            block["cache_control"] = _cache("1h")
        expected["thinking"].update(type="adaptive")
        self.assertEqual(json.loads(wire), expected)
        self.assertEqual(parsed["messages"], body["messages"])
        self.assertEqual(parsed["thinking"], expected["thinking"])

    def test_validate_original_json_and_reuse_large_multimodal_body(self):
        """选项开启时也先检查重名字段。大型多模态请求在策略无变化时复用原字节。@return 无。"""
        with self.assertRaisesRegex(ValueError, "重复字段"):
            input_message(
                b'{"model":"m","stream":true,"messages":[{"role":"user","content":"x","content":"y"}]}',
                body_policy=_policy(),
            )
        data = "a" * (8 * 1024 * 1024)
        body = _request(
            [("user", [{"type": "image", "source": {"type": "base64", "data": data}}])],
            thinking={"type": "disabled"},
        )
        raw = json.dumps(body, indent=2).encode()
        for policy in (None, _policy(False), _policy(ttl="5m")):
            self.assertIs(input_message(raw, body_policy=policy)[2], raw)

    def test_adaptive_display_follows_api_and_native_input_formats(self):
        """API 继承 CLI 的 display，原生 CC 保留请求形状。显式选择和关闭开关均保真。@return 无。"""
        identity = {"metadata": _native_metadata()}
        for native, context, default in [
            (False, {}, "updates"),
            (True, {}, "updates"),
            (
                True,
                {
                    **identity,
                    "system": [
                        _text(
                            "You are Claude Code, Anthropic's official CLI for Claude."
                        )
                    ],
                },
                None,
            ),
            (
                False,
                {
                    **identity,
                    "system": [
                        _text(
                            "x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli;"
                        )
                    ],
                },
                None,
            ),
        ]:
            for display in (None, "omitted", "summarized", "updates"):
                with self.subTest(native=native, default=default, display=display):
                    thinking = {
                        "type": "disabled",
                        **({"display": display} if display else {}),
                    }
                    raw = json.dumps(
                        _request([("user", "hello")], thinking=thinking, **context),
                        indent=2,
                    ).encode()
                    self.assertIs(
                        input_message(raw, native=native, body_policy=_policy(False))[
                            2
                        ],
                        raw,
                    )
                    parsed, _, wire = input_message(
                        raw, native=native, body_policy=_policy(False, adaptive=True)
                    )
                    expected = {"type": "adaptive"}
                    if display or default:
                        expected["display"] = display or default
                    self.assertEqual(parsed["thinking"], expected)
                    self.assertEqual(json.loads(wire)["thinking"], expected)
