"""在内置直发候选核对模型文本终态和合法下一轮。"""

from argparse import ArgumentParser
from functools import partial
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from socket import if_nameindex
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import verify_tui_cold_history as fixture
from fixtures.native_model_send.direct_egress_identity import model_body_identity
from tui_message_json import MessageJSON
from tui_messages import BODY_LIMIT, wire_events
from verify_tui_core_http_hook import ObservedModel
from verify_tui_installed_direct_stock import observe_delivery

QUESTION = "请给出隔离终态的对照文本。"
NEXT_QUESTION = "请处理一次新的合成便签请求。"
TEXT = "这是隔离模型实际交付的一段话。"
SECOND_TEXT = "这是第二个原始文本块。\n保留块内换行。"
REFUSAL_CATEGORY_ONLY = {"type": "refusal", "category": "general_harms"}
REFUSAL_DETAILS = {**REFUSAL_CATEGORY_ONLY, "explanation": "隔离模型实际给出的合成说明。"}


def _events(wire):
    return [event for _, event in wire_events(BytesIO(wire)) if event is not None]


def _assert_stop_details(value, expected_details, *, exact_presence):
    assert fixture.same_json_value(value.get("stop_details"), expected_details), (
        "拒答详情与模型原对象不符", expected_details, value,
    )
    if exact_presence:
        assert ("stop_details" in value) == (expected_details is not None), (
            "拒答详情的字段存在性与模型原响应不符", value,
        )


class _ModelWire:
    """按模型侧连接保存已实际写出的 SSE。"""

    def __init__(self):
        self.replies = {}

    @staticmethod
    def prepare(wire):
        """沿用组装的回环 SSE。@param wire 待发送响应。@return 原字节。"""
        return wire

    def write(self, handler, wire):
        """写出并记录已发送的响应。@param handler 回环模型连接。@param wire 响应字节。@return 无。"""
        written = handler.wfile.write(wire)
        assert written == len(wire)
        handler.wfile.flush()
        port = handler.client_address[1]
        self.replies[port] = wire
        fixture.startup_event("direct_terminal_model_written", model_peer_port=port,
                              response_sha256=sha256(wire).hexdigest(), response_bytes=len(wire),
                              model_events=[event["type"] for event in _events(wire)])

    def empty_refusal(self, received, deliveries, details, *, omit_message_stop=False):
        """按实收 POST 与预留核对模型实际末帧和详情。@param received 本轮实收。
        @param deliveries POST 与连接的关联。@param details 预期模型详情。
        @param omit_message_stop 模型是否省略末帧。@return 同一预留的模型响应证据。
        """
        ((digest, _, _),) = received
        delivery = deliveries[digest]
        assert delivery["connection_owner"] == "interactive_cli", delivery
        port = delivery["model_peer_port"]
        wire = fixture.wait_for(lambda: self.replies.get(port))
        events = _events(wire)
        kinds = [event["type"] for event in events]
        expected = ["message_start", "message_delta"]
        if not omit_message_stop:
            expected.append("message_stop")
        assert kinds == expected, ("模型实际写出的终帧与用例不符", kinds, expected)
        start, terminal = events[:2]
        assert start["message"]["content"] == [] and terminal["delta"]["stop_reason"] == "refusal", events
        delta = terminal["delta"]
        _assert_stop_details(delta, details, exact_presence=True)
        return {
            "reservation_id": delivery["permit"]["reservation_id"],
            "model_peer_port": port,
            "model_request_sha256": digest,
            "response_sha256": sha256(wire).hexdigest(),
            "model_events": kinds,
            "stop_details_present": "stop_details" in delta,
            "stop_details": delta.get("stop_details"),
            "usage": [start["message"]["usage"]["input_tokens"], terminal["usage"]["output_tokens"]],
        }


def _model_reply(body, _homes, final, *, reason, text, details, empty_content, second_text=None,
                 omit_message_stop=False):
    if fixture.find_blocks(body, "text", NEXT_QUESTION):
        return fixture.message_sse({"type": "text", "text": final}, "end_turn", "msg_direct_terminal_next")
    wire = fixture.message_sse({"type": "text", "text": text}, reason, "msg_direct_terminal")
    if details is None and not empty_content and second_text is None:
        return wire
    events = _events(wire)
    if empty_content:
        events = [event for event in events if "index" not in event]
    if second_text is not None:
        second = fixture.message_sse({"type": "text", "text": second_text}, reason, "msg_direct_terminal")
        events[-2:-2] = [{**event, "index": 1} for event in _events(second) if "index" in event]
    if details is not None:
        (terminal,) = [event for event in events if event["type"] == "message_delta"]
        terminal["delta"]["stop_details"] = details
    if omit_message_stop:
        assert events[-1]["type"] == "message_stop"
        events.pop()
    return b"".join(map(fixture.frame, events))


def _decode_completed_reply(raw, *, stream, content, details):
    if stream:
        reply = MessageJSON(BODY_LIMIT)
        events = _events(raw)
        kinds = [event["type"] for event in events]
        assert kinds[-2:] == ["message_delta", "message_stop"] and kinds.count("message_stop") == 1, events
        if not content:
            assert not any(kind.startswith("content_block_") for kind in kinds), events
        _assert_stop_details(events[-2]["delta"], details, exact_presence=not content)
        for event in events:
            reply.add(event)
        result = json.loads(reply.finish())
    else:
        result = json.loads(raw)
    _assert_stop_details(result, details, exact_presence=not content)
    return result


def _assert_incomplete_reply(status, raw, *, stream):
    if status == 502:
        error = json.loads(raw)
        kinds = ["error"]
    else:
        assert stream and status == 200, ("缺少模型实际末帧", status)
        events = _events(raw)
        kinds = [event["type"] for event in events]
        assert "message_stop" not in kinds and kinds[-1:] == ["error"], ("缺少模型实际末帧", kinds)
        error = events[-1]
    assert error["type"] == "error" and error["error"]["type"] == "api_error", error
    return kinds


def _check(manage, token, account, received, _homes, final, deliveries, *, reason, stream, content, details,
           model_wire=None, omit_message_stop=False):
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": stream, "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": QUESTION}]}
    headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-direct-terminal/1"}
    if reason == "refusal":
        # 现有策略封禁使用公开正文中的会话标识，与传输会话头一致。
        body["metadata"] = {"user_id": json.dumps({"session_id": headers["x-session-id"]})}

    def completed(request_id):
        def completed_request():
            detail = manage("GET", "request-diagnostics/" + request_id)
            return detail if detail["request"].get("finished_at") else None

        return fixture.wait_for(completed_request)

    if omit_message_stop:
        status, raw, request_id = fixture.checked_messages(
            manage, token, body, headers, received, "direct_empty_refusal_missing_stop",
            expected_status=None, trace_startup=True,
        )
        observation = model_wire.empty_refusal(received, deliveries, details, omit_message_stop=True)
        context = completed(request_id)["request"]["context"]
        assert context["tui_reservation_id"] == observation["reservation_id"], context
        public_events = _assert_incomplete_reply(status, raw, stream=stream)
        return {"reason": reason, "stream": stream, "status": status, "request_id": request_id,
                "model_wire": observation, "public_events": public_events, "model_posts": len(received),
                "wire_final": "unavailable"}

    attempts = []

    def post(label, request, expected_reason, expected_content, session_headers=headers, *, expected_details=None):
        before = len(received)
        status, raw, request_id = fixture.checked_messages(manage, token, request, session_headers, received, label,
                                                           trace_startup=True)
        observation = None
        if not expected_content:
            observation = model_wire.empty_refusal(received[before:], deliveries, expected_details)
        result = _decode_completed_reply(raw, stream=stream, content=expected_content, details=expected_details)
        assert result["stop_reason"] == expected_reason and result["stop_sequence"] is None, result
        assert result["content"] == expected_content, result
        expected_usage = observation["usage"] if observation is not None else [10, 8]
        assert [result["usage"]["input_tokens"], result["usage"]["output_tokens"]] == expected_usage, result
        ((digest, model, _tls),) = received[before:]
        detail = completed(request_id)
        expected_outcome = "upstream_rejected" if expected_reason == "refusal" else "success"
        assert detail["request"]["outcome"] == expected_outcome, detail["request"]
        context = detail["request"]["context"]
        (attempt,) = detail["attempts"]
        delivery = deliveries[digest]
        assert context["tui_confirmed_model_responses"] == 1
        assert attempt["account_id"] == account and attempt["request_id"] == request_id
        assert attempt["attempt_id"] == context["tui_reservation_id"] == delivery["permit"]["reservation_id"]
        assert attempt["context"]["tui_body_source"] == delivery["connection_owner"] == "interactive_cli"
        assert delivery["permit"]["body_identity"] == {**model_body_identity(model), "billing_cch": "00000"}
        question = NEXT_QUESTION if before else QUESTION
        assert [role for role, _ in fixture.find_blocks(model, "text", question)] == ["user"]
        attempts.append({"request_id": request_id, "reservation_id": attempt["attempt_id"],
                         "status": status, "stop_reason": result["stop_reason"],
                         "stop_details": result.get("stop_details"), "stop_details_present": "stop_details" in result,
                         "content": result["content"], "delivery": delivery})
        if observation is not None:
            attempts[-1]["model_wire"] = observation
        return result

    offer = post("direct_text_stop", body, reason, content, expected_details=details)
    follow = {**body, "messages": [*body["messages"], {"role": "assistant", "content": offer["content"]},
                                  {"role": "user", "content": NEXT_QUESTION}]}
    final_content = [{"type": "text", "text": final}]
    proof = {}
    if reason == "refusal":
        # 现有策略封禁记录来自模型拒答。另用无关新会话核对账号仍可处理正常请求。
        status, raw, request_id = fixture.checked_messages(
            manage, token, follow, headers, received, "direct_text_stop_blocked", expected_status=400,
            trace_startup=True,
        )
        assert json.loads(raw)["error"]["code"] == "session_policy_blocked"
        assert manage("GET", "request-diagnostics/" + request_id)["attempts"] == [] and len(received) == 1
        proof["same_session_block"] = {"request_id": request_id, "status": status}
        # 新会话在拒答响应交付后立即提交，允许原 CLI 此时仍在退场。
        fresh_id = str(uuid4())
        fresh = {**body, "messages": [{"role": "user", "content": NEXT_QUESTION}],
                 "metadata": {"user_id": json.dumps({"session_id": fresh_id})}}
        post("direct_text_stop_next", fresh, "end_turn", final_content, {**headers, "x-session-id": fresh_id})
    else:
        post("direct_text_stop_next", follow, "end_turn", final_content)
        assert [role for role, _ in fixture.find_blocks(received[1][1], "text", TEXT)] == ["assistant"]
    assert len(received) == len({a["reservation_id"] for a in attempts}) == 2
    return {**proof, "reason": reason, "stream": stream, "attempts": attempts,
            "model_posts": len(received), "wire_final": "unavailable"}


def _check_empty_refusal_retry(manage, token, account, received, _homes, final, deliveries, *, stream):
    session_id = str(uuid4())
    foreign = manage("POST", "tokens", {"name": "independent-empty-refusal-caller",
                                       "allowed_accounts": str(account)})["token"]
    cases = {}

    def post(label, credential, sid, question, expected_status):
        body = {"model": fixture.MODEL, "max_tokens": 128, "stream": stream, "thinking": {"type": "disabled"},
                "metadata": {"user_id": json.dumps({"session_id": sid})},
                "messages": [{"role": "user", "content": question}]}
        headers = {"x-session-id": sid, "User-Agent": "flower2api-direct-terminal/1"}
        before = len(received)
        status, raw, request_id = fixture.checked_messages(
            manage, credential, body, headers, received, label, expected_status=expected_status, trace_startup=True,
        )

        def finished():
            detail = manage("GET", "request-diagnostics/" + request_id)
            return detail if detail["request"].get("finished_at") else None

        detail = fixture.wait_for(finished)
        row = cases[label] = {"status": status, "request_id": request_id, "model_posts": len(received) - before}
        if status == 400:
            assert json.loads(raw)["error"]["code"] == "session_policy_blocked"
            assert detail["attempts"] == [] and row["model_posts"] == 0, detail
            return
        ((digest, sent, _),) = received[before:]
        (attempt,) = detail["attempts"]
        reservation = detail["request"]["context"]["tui_reservation_id"]
        delivery = deliveries[digest]
        assert attempt["account_id"] == account and attempt["request_id"] == request_id
        assert reservation == attempt["attempt_id"] == delivery["permit"]["reservation_id"]
        assert delivery["connection_owner"] == "interactive_cli", delivery
        assert delivery["permit"]["body_identity"] == {**model_body_identity(sent), "billing_cch": "00000"}
        tokens = attempt["tokens"]
        row.update(reservation_id=reservation, tokens=tokens, delivery=delivery)
        if status == 502:
            assert json.loads(raw) == {"type": "error", "error": {
                "type": "api_error", "message": "V2 模型响应无效或提前终止",
            }}
            root = detail["request"]
            assert root["status_code"] == 502 and root["context"]["tui_confirmed_model_responses"] == 1, root
            assert attempt["status_code"] == 200 and attempt["stop_reason"] == "refusal", attempt
            assert root["error_stage"] == attempt["error_stage"] == "tui_response_projection", detail
            assert root["outcome"] == attempt["outcome"] == "transport_error", detail
            assert attempt["ttft_ms"] is None and attempt["upstream_request_id"] is None, attempt
            assert all(value is None for value in tokens.values()), attempt
            row.update(upstream_status=attempt["status_code"], stop_reason=attempt["stop_reason"],
                       error_stage=attempt["error_stage"], confirmed=root["context"]["tui_confirmed_model_responses"])
            return
        if stream:
            reply = MessageJSON(BODY_LIMIT)
            for _, event in wire_events(BytesIO(raw)):
                if event is not None:
                    reply.add(event)
            raw = reply.finish()
        result = json.loads(raw)
        assert result["stop_reason"] == "end_turn" and result["content"] == [{"type": "text", "text": final}], result
        assert (tokens["input_tokens"], tokens["output_tokens"]) == (10, 8), attempt

    post("empty_refusal", token, session_id, QUESTION, 502)
    post("same_session_retry", token, session_id, QUESTION, 400)
    post("other_caller", foreign, session_id, NEXT_QUESTION, 200)
    post("other_session", token, str(uuid4()), NEXT_QUESTION, 200)
    manage("PUT", "settings", {"session_policy_block_enabled": "false"})
    post("policy_disabled", token, session_id, QUESTION, 502)
    assert len(received) == len({row["reservation_id"] for row in cases.values() if "reservation_id" in row}) == 4
    return {"stream": stream, "cases": cases, "model_posts": len(received), "wire_final": "unavailable"}


def main():
    """以已安装的交互 CLI 在回环隔离环境读回真正的公开终态。@return 脱敏证据。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--reason", choices=("end_turn", "refusal", "max_tokens"), required=True)
    parser.add_argument("--representation", choices=("sse", "json"), required=True)
    detail_shapes = parser.add_mutually_exclusive_group()
    detail_shapes.add_argument("--stop-details", action="store_true")
    detail_shapes.add_argument("--category-only-details", action="store_true", help="保留仅含类型和类别的原详情对象")
    shapes = parser.add_mutually_exclusive_group()
    shapes.add_argument("--empty-text", action="store_true", help="验收单个空字符串文本块的拒答")
    shapes.add_argument("--empty-content", action="store_true", help="验收零内容块拒答的成功交付")
    shapes.add_argument("--two-text-blocks", action="store_true", help="逐块验收含两个原始文本块的拒答")
    shapes.add_argument("--empty-refusal-retry", action="store_true", help="复跑零内容块交付失败后的封禁对照")
    parser.add_argument("--omit-message-stop", action="store_true", help="校验缺少模型实际末帧时的公开失败")
    args = parser.parse_args()
    if (args.omit_message_stop or args.category_only_details) and not args.empty_content:
        parser.error("--omit-message-stop 和 --category-only-details 需要 --empty-content")
    if args.reason != "refusal" and (
        args.stop_details or args.empty_text or args.empty_content or args.two_text_blocks or args.empty_refusal_retry
    ):
        parser.error("详情及内容形状选项只用于拒答对照")
    if args.empty_refusal_retry and args.stop_details:
        parser.error("--empty-refusal-retry 使用独立的空内容拒答")
    text = "" if args.empty_text else TEXT
    content = [] if args.empty_content else [{"type": "text", "text": text}]
    second_text = SECOND_TEXT if args.two_text_blocks else None
    if second_text is not None:
        content.append({"type": "text", "text": second_text})
    details = REFUSAL_DETAILS if args.stop_details else None
    if args.category_only_details:
        details = REFUSAL_CATEGORY_ONLY
    stream = args.representation == "sse"
    model_wire = _ModelWire() if args.empty_content else None
    check = (partial(_check_empty_refusal_retry, stream=stream) if args.empty_refusal_retry else
             partial(_check, reason=args.reason, stream=stream, content=content, details=details,
                     model_wire=model_wire, omit_message_stop=args.omit_message_stop))
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    assert Path("/opt/flower/tui/fixture-installed-direct").is_file()
    with (
        patch.multiple(
            fixture, STOCK_POLICIES=("append",), QuietHandler=ObservedModel, observe_stock_delivery=observe_delivery,
            stock_model_reply=partial(_model_reply, reason=args.reason, text=text, details=details,
                                      empty_content=args.empty_content or args.empty_refusal_retry,
                                      second_text=second_text, omit_message_stop=args.omit_message_stop),
            verify_stock_client=check,
        ),
        TemporaryDirectory() as folder,
    ):
        report = fixture.verify(Path("/verification/claude-code-gateway"), Path("/usr/local/bin/account-sender"),
                                Path(folder), installed_runtime=True, stock_client=True, trace_startup=True,
                                model_stream_probe=model_wire)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
