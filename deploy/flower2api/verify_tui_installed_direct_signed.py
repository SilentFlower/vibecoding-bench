"""经内置直发候选验证公开签名块、同进程工具续轮和恢复来源边界。"""

from argparse import ArgumentParser
from contextlib import closing
from functools import partial
from io import BytesIO
import json
from os import kill
from pathlib import Path
from re import fullmatch
from signal import SIGKILL
from socket import if_nameindex
from sqlite3 import connect
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import verify_tui_cold_history as fixture
import verify_tui_core_http_hook as core
from fixtures.native_model_send.direct_egress_identity import model_body_identity
from tui_message_json import MessageJSON
from tui_messages import BODY_LIMIT, wire_events
from verify_tui_installed_direct_stock import observe_delivery


REPORTED_MODEL = "claude-opus-4-6"


def _model_reply(body, _homes, final, *, signed, missing_model):
    if fixture.find_blocks(body, "tool_use_id", fixture.NEW_ID):
        return fixture.message_sse({"type": "text", "text": final}, "end_turn", "msg_direct_signed_done")
    return fixture.fixture_tool_sse(
        {"type": "tool_use", "id": fixture.NEW_ID, "name": fixture.NATIVE_TOOL_NAME, "input": fixture.ARGS},
        with_signature=True, model=None if missing_model else REPORTED_MODEL,
        thinking_text=signed.get("thinking", ""),
        redacted=signed if signed["type"] == "redacted_thinking" else None,
    )


def _decode(raw, stream):
    if not stream:
        return json.loads(raw)
    assembled = MessageJSON(BODY_LIMIT)
    for _, event in wire_events(BytesIO(raw)):
        if event is not None:
            if event["type"] == "content_block_start" and event["content_block"]["type"] == "thinking":
                assert event["content_block"]["signature"] == ""
            assembled.add(event)
    return json.loads(assembled.finish())


def _check(manage, token, account, received, _homes, final, deliveries, *, signed, stream, restart, missing_model):
    body = {"model": "claude-sonnet-4-6", "max_tokens": 4096, "stream": stream,
            "thinking": {"type": "adaptive", "display": "summarized"},
            "messages": [{"role": "user", "content": "请读取隔离便签，再根据便签回复。"}], "tools": [fixture.TOOL]}
    headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-direct-signed/1"}

    def post(label, request, expected, *, other_session=False):
        actual_headers = {**headers, "x-session-id": str(uuid4())} if other_session else headers
        _, raw, request_id = fixture.checked_messages(
            manage, token, request, actual_headers, received, label, expected_status=expected, trace_startup=True,
        )
        if expected != 200:
            assert manage("GET", "request-diagnostics/" + request_id)["attempts"] == []
        return raw, request_id

    raw, offer_id = post("direct_signed_offer", body, 200)
    offer = _decode(raw, stream)
    tool = {"type": "tool_use", "id": fixture.NEW_ID, "name": fixture.TOOL["name"], "input": fixture.ARGS}
    assert offer["stop_reason"] == "tool_use" and len(received) == 1
    assert fixture.same_json_value(offer["content"], [signed, tool]), offer
    executed = []
    (result,) = fixture.fixture_parallel_results([tool], executed)
    follow = {**body, "messages": [*body["messages"], {"role": "assistant", "content": offer["content"]},
                                  {"role": "user", "content": [result]}]}
    field = "signature" if signed["type"] == "thinking" else "data"
    changed = {**follow, "messages": [body["messages"][0], {"role": "assistant", "content": [
        {**signed, field: "Y2hhbmdlZA=="}, tool,
    ]}, follow["messages"][-1]]}
    post("direct_signed_other_session", follow, 400, other_session=True)
    post("direct_signed_changed", changed, 422)
    assert len(received) == 1
    statuses = [200, 400, 422]
    ids = [offer_id]
    # 请求与模型自报身份不同。整个签名组只沿工具 ID 登记真正收到的响应模型。
    with closing(connect("file:/native/tui-reconnect/receipts.db?mode=ro", uri=True)) as database:
        (context,), = database.execute("SELECT n.context FROM receipts r JOIN native_receipt_inputs n"
                                      " ON r.actor=n.actor AND r.revision=n.revision").fetchall()
    signed_models = json.loads(context).get("signed_tool_models", {})
    assert signed_models == ({} if missing_model else {tool["id"]: REPORTED_MODEL}), signed_models
    if restart:
        # 观察原档实际完整写入后结束进程，验证原回执只能沿可信签名来源恢复。
        binding, = Path("/native/tui-workspaces").glob("*.json")
        archive_id = json.loads(binding.read_bytes())["native_session_id"]
        project = Path("/native/tui-sessions") / archive_id / "home/.claude/projects"

        def recorded_archive():
            for archive in project.glob(f"*/{archive_id}.jsonl"):
                snapshot = archive.read_bytes()
                if not snapshot.endswith(b"\n"):
                    continue
                matching = [row["message"] for row in map(json.loads, snapshot.splitlines())
                            if row.get("type") == "assistant" and signed in row["message"].get("content", ())]
                if matching:
                    assert all(row.get("model") == (None if missing_model else REPORTED_MODEL)
                               for row in matching), matching
                    return archive, snapshot
            return None

        archive, original = fixture.wait_for(recorded_archive)
        cli_pid = next(iter(deliveries.values()))["tunnel"]["cli_pid"]
        kill(cli_pid, SIGKILL)
        fixture.wait_for(lambda: not Path(f"/proc/{cli_pid}").exists())
    if missing_model:
        post("direct_signed_without_response_model", follow, 422)
        statuses.append(422)
        assert len(received) == 1
    else:
        raw, receipt_id = post("direct_signed_receipt", follow, 200)
        complete = _decode(raw, stream)
        assert complete["stop_reason"] == "end_turn"
        assert complete["content"] == [{"type": "text", "text": final}], complete
        post("direct_signed_duplicate", follow, 400)
        ids.append(receipt_id)
        statuses.extend([200, 400])
        assert len(received) == 2
        sent = received[1][1]
        actual_signed = fixture.find_blocks(sent, "type", signed["type"])
        assert actual_signed == [("assistant", signed)], actual_signed
        assert fixture.find_blocks(sent, "id", tool["id"]) == [
            ("assistant", {**tool, "name": fixture.NATIVE_TOOL_NAME}),
        ]
        (role, observed), = fixture.find_blocks(sent, "tool_use_id", tool["id"])
        assert role == "user" and observed["type"] == "tool_result" and not observed.get("is_error", False)
        assert observed["content"].startswith(result["content"]), observed
        tail = observed["content"].removeprefix(result["content"])
        assert tail == "" or fullmatch(r"\n\n<system-reminder>\n<total_tokens>\d+ tokens left</total_tokens>\n"
                                       r"</system-reminder>", tail), observed
    assert executed == [tool["id"]]
    attempts = []
    for public_id, (digest, model, _tls) in zip(ids, received, strict=True):
        detail = manage("GET", "request-diagnostics/" + public_id)
        attempt, = detail["attempts"]
        delivery = deliveries[digest]
        reservation = detail["request"]["context"]["tui_reservation_id"]
        assert detail["request"]["context"]["tui_confirmed_model_responses"] == 1
        assert attempt["attempt_id"] == reservation and attempt["account_id"] == account
        assert attempt["context"]["tui_body_source"] == delivery["connection_owner"] == "interactive_cli"
        assert delivery["permit"]["reservation_id"] == reservation
        assert delivery["permit"]["body_identity"] == {**model_body_identity(model), "billing_cch": "00000"}
        assert model["thinking"] == body["thinking"]
        attempts.append({"request_id": public_id, "reservation_id": reservation, "delivery": delivery,
                         "session_origin": attempt["context"]["tui_session_origin"]})
    assert len({a["reservation_id"] for a in attempts}) == len(ids)
    assert len({a["delivery"]["tunnel"]["cli_pid"] for a in attempts}) == 1 + int(restart and not missing_model)
    assert [a["session_origin"] for a in attempts] == ["new_session"] + (
        [] if missing_model else ["disk_resume" if restart else "live_process"]
    )
    if restart:
        assert archive.read_bytes() == original
    return {"http_statuses": statuses, "model_posts": len(received), "client_tools": executed, "attempts": attempts,
            "signed_block": signed["type"], "stream": stream, "restart": restart, "signed_models": signed_models,
            "wire_final": "unavailable"}


def main():
    """使用固定内置运行件走公开 Messages 和隔离模型。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--representation", choices=("sse", "json"), required=True)
    parser.add_argument("--case", choices=("thinking", "signature-only", "redacted"), required=True)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--missing-model", action="store_true")
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    signed = fixture.EXTERNAL_REDACTED_THINKING if args.case == "redacted" else fixture.SIGNED_THINKING
    if args.case == "signature-only":
        signed = {**signed, "thinking": ""}
    with (
        patch.multiple(
            fixture, STOCK_POLICIES=("append",), observe_stock_delivery=observe_delivery,
            QuietHandler=core.ObservedModel,
            stock_model_reply=partial(_model_reply, signed=signed, missing_model=args.missing_model),
            verify_stock_client=partial(_check, signed=signed, stream=args.representation == "sse",
                                        restart=args.restart or args.missing_model,
                                        missing_model=args.missing_model),
        ),
        TemporaryDirectory() as folder,
    ):
        report = fixture.verify(Path("/verification/claude-code-gateway"), Path("/usr/local/bin/account-sender"),
                                Path(folder), installed_runtime=True, stock_client=True, trace_startup=True)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
