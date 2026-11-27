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


def _model_reply(body, _homes, final, *, reason):
    if fixture.find_blocks(body, "text", NEXT_QUESTION):
        return fixture.message_sse({"type": "text", "text": final}, "end_turn", "msg_direct_terminal_next")
    return fixture.message_sse({"type": "text", "text": TEXT}, reason, "msg_direct_terminal")


def _check(manage, token, account, received, _homes, final, deliveries, *, reason, stream):
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": stream, "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": QUESTION}]}
    headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-direct-terminal/1"}
    if reason == "refusal":
        # 现有策略封禁使用公开正文中的会话标识，与传输会话头一致。
        body["metadata"] = {"user_id": json.dumps({"session_id": headers["x-session-id"]})}
    attempts = []

    def post(label, request, expected_reason, text, session_headers=headers):
        before = len(received)
        status, raw, request_id = fixture.checked_messages(manage, token, request, session_headers, received, label,
                                                           trace_startup=True)
        if stream:
            reply = MessageJSON(BODY_LIMIT)
            for _, event in wire_events(BytesIO(raw)):
                if event is not None:
                    reply.add(event)
            result = json.loads(reply.finish())
        else:
            result = json.loads(raw)
        assert result["stop_reason"] == expected_reason and result["stop_sequence"] is None, result
        assert result["content"] == [{"type": "text", "text": text}], result
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
                         "status": status, "stop_reason": result["stop_reason"], "delivery": delivery})
        return result

    offer = post("direct_text_stop", body, reason, TEXT)
    follow = {**body, "messages": [*body["messages"], {"role": "assistant", "content": offer["content"]},
                                  {"role": "user", "content": NEXT_QUESTION}]}
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
        # 回环受管策略只允许一个活动 CLI 绑定。先观察上一进程的正常退场。
        original_pid = attempts[0]["delivery"]["tunnel"]["cli_pid"]
        fixture.wait_for(lambda: not Path(f"/proc/{original_pid}").exists())
        fresh_id = str(uuid4())
        fresh = {**body, "messages": [{"role": "user", "content": NEXT_QUESTION}],
                 "metadata": {"user_id": json.dumps({"session_id": fresh_id})}}
        post("direct_text_stop_next", fresh, "end_turn", final, {**headers, "x-session-id": fresh_id})
    else:
        post("direct_text_stop_next", follow, "end_turn", final)
        assert [role for role, _ in fixture.find_blocks(received[1][1], "text", TEXT)] == ["assistant"]
    assert len(received) == len({a["reservation_id"] for a in attempts}) == 2
    return {**proof, "reason": reason, "stream": stream, "attempts": attempts,
            "model_posts": len(received), "wire_final": "unavailable"}


def main():
    """以已安装的交互 CLI 在回环隔离环境读回真正的公开终态。@return 脱敏证据。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--reason", choices=("end_turn", "refusal", "max_tokens"), required=True)
    parser.add_argument("--representation", choices=("sse", "json"), required=True)
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    assert Path("/opt/flower/tui/fixture-installed-direct").is_file()
    with (
        patch.multiple(
            fixture, STOCK_POLICIES=("append",), QuietHandler=ObservedModel, observe_stock_delivery=observe_delivery,
            stock_model_reply=partial(_model_reply, reason=args.reason),
            verify_stock_client=partial(_check, reason=args.reason, stream=args.representation == "sse"),
        ),
        TemporaryDirectory() as folder,
    ):
        report = fixture.verify(Path("/verification/claude-code-gateway"), Path("/usr/local/bin/account-sender"),
                                Path(folder), installed_runtime=True, stock_client=True, trace_startup=True)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
