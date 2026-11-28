"""在公开 Messages 核对历史管理守卫的来源及原工具回执重提。"""

from argparse import ArgumentParser
from contextlib import contextmanager
import json
from pathlib import Path
from socket import if_nameindex
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from fixtures.native_model_send.tui_startup_trace import DISABLE_THINKING_SETTING
import verify_tui_cold_history as fixture
from verify_tui_context_management import KEEP_ONE


QUESTION = "请核对合成历史管理策略。"
ERROR = {"type": "error", "error": {"type": "invalid_request_error", "code": "unsupported_parameter",
                                   "message": "本轮 CLI 不支持请求的历史管理策略"}}
SWITCH = Path("/opt/flower/tui") / DISABLE_THINKING_SETTING


@contextmanager
def disabled_thinking():
    """通过隔离启动观察器关闭真实 CLI 的思考。@return 此期间新启动 CLI 的测试作用域。"""
    SWITCH.touch()
    try:
        yield
    finally:
        SWITCH.unlink()


def verify(manage, token, identifier, received, sender_status, restart, *, source_observer):
    """从公开入口对照两种错误来源及原回执重提。
    @param manage 管理入口。@param token 隔离公开凭据。@param identifier 账号。
    @param received 模型实收。@param sender_status 诊断读取。@param restart 结束旧 CLI 并重启 sender。
    @param source_observer 是否启用正文替身。@return 请求、尝试和实收证据。
    """
    assert not source_observer and restart is not None
    manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": "append"})
    cases = {}
    callbacks = []

    def post(name, body, headers, status, count, stage=None):
        before = len(received)
        actual, raw, request_id = fixture.checked_messages(
            manage, token, body, headers, received, name, expected_status=status, trace_startup=True,
            sender_status=sender_status,
        )
        (row,) = fixture.report_request_diagnostics(manage, name, request_id, headers["x-session-id"], None)["requests"]
        assert row["request_id"] == request_id and row["status_code"] == actual == status
        assert len(received) - before == count, (name, row)
        reply = json.loads(raw)
        if stage is not None:
            (attempt,) = row["attempts"]
            context = row["diagnostic_context"]
            outcome = "local_rejected" if count == 0 else "upstream_rejected"
            assert row["attempt_count"] == 1 and attempt["attempt_id"] == context["tui_reservation_id"]
            assert row["outcome"] == attempt["outcome"] == outcome, (name, row)
            assert row["error_stage"] == attempt["error_stage"] == stage, (name, row)
            assert context["tui_confirmed_model_responses"] == count, (name, row)
            assert reply["error"]["message"] == ERROR["error"]["message"], reply
        if status == 400:
            assert row["attempt_count"] == 0 and not row["attempts"], (name, row)
        if status == 200:
            (attempt,) = row["attempts"]
            assert attempt["diagnostic_context"]["tui_body_source"] == "account_sender", (name, row)
        cases[name] = {"status": status, "new_model_posts": count, "response": reply, "diagnostics": row}
        return reply

    def request(text=QUESTION, stream=False):
        return {"model": fixture.MODEL, "max_tokens": 4096, "stream": stream, "system": fixture.SYSTEM[0],
                "messages": [{"role": "user", "content": text}], "context_management": KEEP_ONE}

    def session():
        return {"x-session-id": str(uuid4()), "User-Agent": "flower2api-context-guard/1"}

    for stream in (False, True):
        label = "sse" if stream else "json"
        with disabled_thinking():
            local = post(label + "_guard", request(stream=stream), session(), 422, 0, "tui_cli_input_guard")
        model = post(label + "_model", request(fixture.REJECT_MODEL_REQUEST, stream), session(), 422, 1, "upstream_headers")
        assert local == model, (local, model)

    for origin in ("guard", "model"):
        body = {**request(), "tools": [fixture.TOOL]}
        headers = session()
        initial = post(origin + "_initial", body, headers, 200, 1)
        tool, = [block for block in initial["content"] if block["type"] == "tool_use"]
        assert (tool["id"], tool["name"], tool["input"]) == (fixture.NEW_ID, fixture.TOOL["name"], fixture.ARGS)
        callbacks.append({"session": headers["x-session-id"], "tool_use_id": tool["id"]})
        result = {"type": "tool_result", "tool_use_id": tool["id"], "content": fixture.REPLY}
        follow = {**body, "messages": [*body["messages"], {"role": "assistant", "content": initial["content"]},
                                     {"role": "user", "content": [result]}]}
        restart(headers)
        if origin == "guard":
            with disabled_thinking():
                post("guard_receipt", follow, headers, 422, 0, "tui_cli_input_guard")
            post("guard_wrong_session", follow, session(), 400, 0)
            final = post("guard_retry", follow, headers, 200, 1)
            assert final["stop_reason"] == "end_turn" and final["content"] == [{"type": "text", "text": fixture.FINAL}]
        else:
            with patch.object(fixture, "REJECT_MODEL_REQUEST", QUESTION):
                post("model_receipt", follow, headers, 422, 1, "upstream_headers")
        native = received[-1][1]
        assert native["context_management"] == KEEP_ONE
        assert fixture.find_blocks(native, "tool_use_id", tool["id"]) == [("user", result)]
        post(origin + "_duplicate", follow, headers, 400, 0)
    assert len(received) == 6 and len(callbacks) == 2
    return {"cases": cases, "model_posts": len(received), "client_tool_calls": callbacks, "wire_final": "unavailable"}


def main():
    """在仅回环的容器运行固定账号和隔离模型。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, default=Path("/usr/local/bin/account-sender"))
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    fixture.install_source(trace_startup=True)
    respond = fixture.response_json

    def model_response(handler, payload, *, status=200, headers=None):
        if status == 400 and payload.get("error", {}).get("message") == "隔离模型明确拒绝合成请求":
            return respond(handler, ERROR, status=422,
                           headers={**(headers or {}), "x-v3-tui-error-source": "tui_cli_input_guard"})
        return respond(handler, payload, status=status, headers=headers)

    with patch.multiple(fixture, verify_structured_tool_round=verify, response_json=model_response), TemporaryDirectory(
        prefix="tui-context-guard-",
    ) as temporary:
        proof = fixture.verify(
            args.gateway, args.sender, Path(temporary), trace_startup=True, installed_runtime=True,
            structured_output="restart", failure_boundaries=True,
        )
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
