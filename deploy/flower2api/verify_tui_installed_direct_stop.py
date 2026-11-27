"""在内置直发候选核对模型文本终态和合法下一轮。"""

from argparse import ArgumentParser
from functools import partial
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
REFUSAL_DETAILS = {"type": "refusal", "category": "general_harms", "explanation": "隔离模型实际给出的合成说明。"}


def _model_reply(body, _homes, final, *, reason, text, details, empty_content, second_text=None):
    if fixture.find_blocks(body, "text", NEXT_QUESTION):
        return fixture.message_sse({"type": "text", "text": final}, "end_turn", "msg_direct_terminal_next")
    wire = fixture.message_sse({"type": "text", "text": text}, reason, "msg_direct_terminal")
    if details is None and not empty_content and second_text is None:
        return wire
    events = [event for _, event in wire_events(BytesIO(wire)) if event is not None]
    if empty_content:
        events = [event for event in events if "index" not in event]
    if second_text is not None:
        second = fixture.message_sse({"type": "text", "text": second_text}, reason, "msg_direct_terminal")
        events[-2:-2] = [{**event, "index": 1} for _, event in wire_events(BytesIO(second))
                         if event is not None and "index" in event]
    if details is not None:
        (terminal,) = [event for event in events if event["type"] == "message_delta"]
        terminal["delta"]["stop_details"] = details
    return b"".join(map(fixture.frame, events))


def _check(manage, token, account, received, _homes, final, deliveries, *, reason, stream, content, details):
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": stream, "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": QUESTION}]}
    headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-direct-terminal/1"}
    if reason == "refusal":
        # 现有策略封禁使用公开正文中的会话标识，与传输会话头一致。
        body["metadata"] = {"user_id": json.dumps({"session_id": headers["x-session-id"]})}
    attempts = []

    def post(label, request, expected_reason, expected_content, session_headers=headers, *, expected_details=None):
        before = len(received)
        status, raw, request_id = fixture.checked_messages(manage, token, request, session_headers, received, label,
                                                           trace_startup=True)
        if stream:
            reply = MessageJSON(BODY_LIMIT)
            events = [event for _, event in wire_events(BytesIO(raw)) if event is not None]
            assert [event["type"] for event in events[-2:]] == ["message_delta", "message_stop"], events
            if not expected_content:
                assert not any(event["type"].startswith("content_block_") for event in events), events
            assert fixture.same_json_value(events[-2]["delta"].get("stop_details"), expected_details), events
            for event in events:
                reply.add(event)
            result = json.loads(reply.finish())
        else:
            result = json.loads(raw)
        assert result["stop_reason"] == expected_reason and result["stop_sequence"] is None, result
        assert fixture.same_json_value(result.get("stop_details"), expected_details), result
        assert result["content"] == expected_content, result
        assert (result["usage"]["input_tokens"], result["usage"]["output_tokens"]) == (10, 8), result
        ((digest, model, _tls),) = received[before:]
        def completed_request():
            detail = manage("GET", "request-diagnostics/" + request_id)
            return detail if detail["request"].get("finished_at") else None

        detail = fixture.wait_for(completed_request)
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
                         "stop_details": result.get("stop_details"), "content": result["content"], "delivery": delivery})
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
    parser.add_argument("--stop-details", action="store_true")
    shapes = parser.add_mutually_exclusive_group()
    shapes.add_argument("--empty-text", action="store_true", help="验收单个空字符串文本块的拒答")
    shapes.add_argument("--empty-content", action="store_true", help="验收零内容块拒答的成功交付")
    shapes.add_argument("--two-text-blocks", action="store_true", help="逐块验收含两个原始文本块的拒答")
    shapes.add_argument("--empty-refusal-retry", action="store_true", help="复跑零内容块交付失败后的封禁对照")
    args = parser.parse_args()
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
    stream = args.representation == "sse"
    check = (partial(_check_empty_refusal_retry, stream=stream) if args.empty_refusal_retry else
             partial(_check, reason=args.reason, stream=stream, content=content, details=details))
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    assert Path("/opt/flower/tui/fixture-installed-direct").is_file()
    with (
        patch.multiple(
            fixture, STOCK_POLICIES=("append",), QuietHandler=ObservedModel, observe_stock_delivery=observe_delivery,
            stock_model_reply=partial(_model_reply, reason=args.reason, text=text, details=details,
                                      empty_content=args.empty_content or args.empty_refusal_retry, second_text=second_text),
            verify_stock_client=check,
        ),
        TemporaryDirectory() as folder,
    ):
        report = fixture.verify(Path("/verification/claude-code-gateway"), Path("/usr/local/bin/account-sender"),
                                Path(folder), installed_runtime=True, stock_client=True, trace_startup=True)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
