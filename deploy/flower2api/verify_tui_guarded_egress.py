"""用隔离事件源验收原版 CLI 的公开文本和单组工具直发。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from functools import partial
from hashlib import sha256
from http.client import HTTPConnection
from io import BytesIO
import json
from pathlib import Path
from re import fullmatch
from select import select
from shutil import copy2
from socket import SHUT_RDWR, if_nameindex
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic_ns
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import verify_tui_cold_history as fixture
from tui_message_json import MessageJSON
from tui_messages import BODY_LIMIT, wire_events


def install(*, observe_failure=False, debug_file=None):
    """在一次性容器安装直发试接。
    @param observe_failure 是否读取官方失败事件。
    @param debug_file 测试工作区的官方调试日志名。@return 无。
    """
    if not Path("/.dockerenv").is_file() or {name for _, name in if_nameindex()} != {"lo"}:
        raise RuntimeError("直发试接只允许在仅回环的验收容器运行")
    root = Path("/opt/flower/tui")
    source = root / "tui_source.py"
    frozen = root / "frozen_tui_source.py"
    if frozen.exists() or (root / "fixture_tui_source.py").exists():
        raise RuntimeError("直发试接需要全新的内置账号事件源")
    source.rename(frozen)
    copy2(Path(__file__).with_name("fixtures") / "native_model_send/guarded_egress_source.py", source)
    mod = root / "tui-mod/hooks/session.js"
    body = mod.read_text()
    start = body.index("        await post($, 'end',")
    end = body.index("        if (pending)", start)
    adjusted = body[:start] + """
        await post($, 'direct-result', { turn: e.turnId, step: e.index, reason: response.stopReason,
          answer: response.answer, usage: response.usage,
          frames: (pending ?? []).filter(item => ['tool', 'input'].includes(item.kind)) })
""" + body[end:]
    if observe_failure:
        register = "export function register(on) {"
        assert adjusted.count(register) == 1
        adjusted = adjusted.replace(register, register + """
  on('classic.StopFailure', async ($, e, next) => {
    const fields = Object.keys(e).filter(key => e[key] !== undefined).sort()
    const summary = { fields, error: e.error, text: e.last_assistant_message }
    $.ui.log('R1-STOP-FAILURE|' + JSON.stringify(summary) + '|R1-END', {to: 'debug'})
    return next(e)
  })
""")
        debug_file = "stop-failure.log"
    if debug_file is not None:
        runtime = source.read_text()
        launch = '\n    settings = {**environment,'
        assert runtime.count(launch) == 1
        debug = f'\n    options["arguments"] = [*options["arguments"], "--debug-file", str(config_dir / {debug_file!r})]'
        source.write_text(runtime.replace(launch, debug + launch))
    mod.write_text(adjusted)


class ModelPath(fixture.QuietHandler):
    """让同一隔离模型接受原版直发的 beta 查询。"""

    def parse_request(self):
        """保留语义等价的标准 Messages 查询。@return 原解析结果。"""
        parsed = super().parse_request()
        if parsed and self.command == "POST" and self.path == "/v1/messages?beta=true":
            fixture.startup_event("isolated_direct_beta_query", path=urlsplit(self.path).path)
            self.path = "/v1/messages"
        return parsed


class RejectedModel(ModelPath):
    """在合成拒绝的 HTTP 回包里增加可定位的响应头。"""

    def send_response(self, code, message=None):
        """交付隔离回包状态和标记。@param code HTTP 状态。@param message 状态文本。@return 无。"""
        super().send_response(code, message)
        if code == 400:
            self.send_header("x-fixture-provider-status", "isolated-provider-http-header")


def check_provider_error(manage, token, identifier, received, sender_status, restart, *, source_observer):
    """核对真实直发错误与官方失败事件。@return 本次公开请求、实收与失败事件。"""
    assert not source_observer and not restart
    headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-direct-guarded-lab/1"}
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": False, "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": fixture.REJECT_MODEL_REQUEST}]}
    started = fixture.datetime.now(fixture.timezone.utc).isoformat(timespec="milliseconds")
    status, raw, request_id = fixture.checked_messages(
        manage, token, body, headers, received, "guarded_provider_error", expected_status=502,
        trace_startup=True, sender_status=sender_status,
    )
    assert len(received) == 1

    def read_failure():
        for log in Path("/native/tui-sessions").glob("*/home/.claude/stop-failure.log"):
            for line in log.read_text(errors="replace").splitlines():
                if "R1-STOP-FAILURE|" in line and "|R1-END" in line:
                    return json.loads(line.split("R1-STOP-FAILURE|", 1)[1].split("|R1-END", 1)[0])
        return None

    event = fixture.wait_for(read_failure)
    assert event["error"] == "unknown" and event["text"] == "API Error: 400 隔离模型明确拒绝合成请求", event
    assert {"status", "headers", "body", "error_details"}.isdisjoint(event["fields"]), event
    evidence = fixture.report_request_diagnostics(manage, "guarded_provider_error", request_id,
                                                  headers["x-session-id"], started)
    return {"public_status": status, "public_error": json.loads(raw)["error"], "request_id": request_id,
            "model_status": 400, "model_posts": len(received), "model_body_sha256": received[0][0],
            "stop_failure": event, "diagnostics": evidence, "wire_final": "unavailable"}


def _reconnect_receipt(manage, token, headers, follow, first, received, post, tail):
    sent = Event()
    try:
        with closing(HTTPConnection("127.0.0.1", 18090, timeout=30)) as connection:
            connection.request("POST", "/v1/messages", fixture.encoded(follow), headers={
                **headers, "authorization": "Bearer " + token, "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            })
            fixture.wait_for(lambda: tail.first_frame_ns)
            assert len(received) == 2 and not tail.writing_tail.is_set()
            assert not select([connection.sock], [], [], 0)[0]
            connection.sock.shutdown(SHUT_RDWR)
            disconnected = monotonic_ns()
        # 重交写入后才释放模型尾段，确保断开和新读者都发生在公开首响之前。
        with ThreadPoolExecutor(max_workers=1) as pool:
            retried = pool.submit(post, "direct_receipt_reattach", follow, 200, sent=sent)
            try:
                assert sent.wait(5) and not retried.done() and len(received) == 2
                sent_before_tail = monotonic_ns()
            finally:
                tail.release.set()
            answer, reader = retried.result()
    finally:
        tail.release.set()
    assert len(received) == 2 and tail.completed.is_set()
    assert tail.first_frame_ns <= disconnected <= sent_before_tail <= tail.ended_ns

    def ended():
        rows = manage("GET", "request-diagnostics")["items"]
        own = [row for row in rows if row["request_id"] not in (first["request_id"], reader["request_id"])]
        return own[0] if len(own) == 1 and own[0]["finished_at"] else None

    original = fixture.wait_for(ended)
    detail = manage("GET", "request-diagnostics/" + reader["request_id"])
    assert detail["request"]["outcome"] in ("tui_reconnect_stream", "tui_reconnect_cached")
    assert detail["request"]["attempt_count"] == 0 and not detail["attempts"]
    assert original["attempt_count"] == 1
    return answer, {"request_id": original["request_id"], "status": original["status_code"],
                    "reservation_id": original["context"]["tui_reservation_id"],
                    "reconnect": {**reader, "original_response_headers": None, "reader_attempts": 0,
                                  "new_model_posts": 0, "outcome": detail["request"]["outcome"],
                                  "model_first_frame_ns": tail.first_frame_ns, "model_end_ns": tail.ended_ns,
                                  "disconnect_ns": disconnected, "retry_written_ns": sent_before_tail}}


def check(manage, token, identifier, received, sender_status, restart, *, source_observer, mode, receipt_status=200,
          public_stream=False, receipt_tail=None, before_receipt=None):
    """通过公开网关核对真实工具。@param public_stream 是否读取公开 SSE。@return 公开回执和模型实收。"""
    assert not source_observer and not restart
    headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-direct-guarded-lab/1"}
    question = "从真实原版进程直接提交的合成问题。"
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": public_stream, "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": question}]}
    tool_executions = []

    def post(label, request, expected, *, sent=None):
        if sent is None:
            status, raw, request_id = fixture.checked_messages(
                manage, token, request, headers, received, label, expected_status=expected,
                trace_startup=True, sender_status=sender_status,
            )
        else:
            ids = []
            status, raw = fixture.call(
                18090, "POST", "/v1/messages", token, request, headers,
                observe_request_sent=sent.set,
                observe_headers=lambda response: ids.append(response.getheader("x-cc2api-request-id")),
            )
            request_id, = ids
            assert status == expected and request_id, (status, raw)
        context = manage("GET", "request-diagnostics/" + request_id)["request"].get("context") or {}
        proof = {"status": status, "request_id": request_id, "reservation_id": context.get("tui_reservation_id")}
        if public_stream and status == 200:
            output = MessageJSON(BODY_LIMIT)
            sequence = []
            for _, item in wire_events(BytesIO(raw)):
                if item is not None and item["type"] != "ping":
                    output.add(item)
                    sequence.append(item["type"])
            assert sequence[:2] == ["message_start", "content_block_start"], sequence
            assert sequence[-3:] == ["content_block_stop", "message_delta", "message_stop"], sequence
            assert sequence[2:-3] and all(kind == "content_block_delta" for kind in sequence[2:-3]), sequence
            proof["sse_events"] = sequence
            raw = output.finish()
        return json.loads(raw), proof

    first = None
    result = None
    if mode == "tool":
        body["tools"] = [fixture.TOOL]
        tool_reply, first = post("guarded_direct_tool_offer", body, 200)
        assert len(received) == 1 and tool_reply["stop_reason"] == "tool_use"
        assert tool_reply["content"] == [{"type": "tool_use", "id": fixture.NEW_ID,
                                          "name": fixture.TOOL["name"], "input": fixture.ARGS}]
        call, = tool_reply["content"]
        # 执行端只接收公开回复中的工具 ID 和参数，读取夹具提供的一条合成便签。
        notes = {fixture.encoded(fixture.ARGS): fixture.REPLY}
        result = {"type": "tool_result", "tool_use_id": call["id"], "content": notes[fixture.encoded(call["input"])]}
        tool_executions.append(call["id"])
        follow = {**body, "messages": [*body["messages"], {"role": "assistant", "content": tool_reply["content"]},
                                      {"role": "user", "content": [result]}]}
        if before_receipt is not None:
            before_receipt()
        if receipt_tail is not None:
            answer, request = _reconnect_receipt(manage, token, headers, follow, first, received, post, receipt_tail)
        else:
            answer, request = post("guarded_direct_tool_receipt", follow, receipt_status)
        if receipt_status != 200:
            return {**request, "initial": first, "tool_result": result, "model_posts": len(received),
                    "public_error": answer["error"], "client_tool_executions": len(tool_executions),
                    "session_id": headers["x-session-id"], "wire_final": "unavailable"}
        if receipt_tail is None:
            _, duplicate = post("guarded_direct_tool_duplicate", follow, 400)
            request["duplicate"] = duplicate
        assert len(received) == 2
        (role, block), = fixture.find_blocks(received[-1][1], "tool_use_id", result["tool_use_id"])
        assert role == "user" and block["content"].count(fixture.REPLY) == 1
    else:
        answer, request = post("guarded_direct_public", body, 200)
        assert len(received) == 1
    model_hash, model, tls = received[-1]
    # 正式公开网关会替换响应 ID。随后以原 CLI 归档的独立事件核对提供方 ID。
    assert fullmatch(r"msg_[0-9a-f]{32}", answer["id"]) and answer["stop_reason"] == "end_turn", answer
    assert answer["content"] == [{"type": "text", "text": fixture.FINAL}]
    assert (answer["usage"]["input_tokens"], answer["usage"]["output_tokens"]) == (10, 8)
    assert sum(block.get("text") == question for row in model["messages"] if row["role"] == "user"
               for block in fixture.blocks(row)) == 1
    return {**request, "initial": first, "tool_result": result,
            "client_tool_executions": len(tool_executions),
            "session_id": headers["x-session-id"], "model_posts": len(received), "model_body_sha256": model_hash,
            "model_tls": tls, "answer_id": answer["id"], "answer_sha256": sha256(fixture.FINAL.encode()).hexdigest(),
            "model_usage": answer["usage"], "wire_final": "unavailable"}


def main():
    """在仅回环容器替换本次试接用事件源。@return 无。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", required=True, type=Path)
    parser.add_argument("--sender", default=Path("/usr/local/bin/account-sender"), type=Path)
    parser.add_argument("--case", choices=("text", "tool", "provider-error"), required=True)
    args = parser.parse_args()
    failure = args.case == "provider-error"
    install(observe_failure=failure)
    with patch.multiple(
        fixture, QuietHandler=RejectedModel if failure else ModelPath,
        verify_structured_tool_round=check_provider_error if failure else partial(check, mode=args.case),
    ), TemporaryDirectory(prefix="guarded-direct-first-") as folder:
        result = fixture.verify(
            args.gateway, args.sender, Path(folder), installed_runtime=True, structured_output="live",
            trace_startup=True, model_connection_contract="server-close", failure_boundaries=failure,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
