"""隔离观察官方受管钩子在公开 SSE 首帧之前能读到的模型事件。"""

from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from functools import partial
from hashlib import file_digest
from http.client import HTTPConnection
import json
from pathlib import Path
from socket import if_nameindex
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic_ns, sleep
from unittest.mock import patch
from uuid import uuid4

import verify_tui_cold_history as fixture
import verify_tui_core_http_hook as core
from verify_tui_direct_reuse import CANDIDATE_MODE, install_permit
from verify_tui_public_sse import ModelStream, PROBE_QUESTION, SENDER


EARLY_STREAM_HOOK = """
  on('turn.step', async function* ($, e, next) {
    const stream = next(e)
    let sampled = false
    for (;;) {
      const item = await stream.next()
      const value = item.value
      const record = {phase: item.done ? 'public_sse_step_result' : 'public_sse_chunk',
        kind: value?.kind ?? null, fields: Object.keys(value ?? {}).sort(),
        modelMessageIdVisible: JSON.stringify(value)?.includes('msg_cold_reply') ?? false,
        inputCount: value?.usage?.input_tokens ?? null, text: value?.kind === 'text' ? value.text : null}
      $.ui.log('FLOWER-CORE-HTTP|' + JSON.stringify(record) + '|END', {to: 'debug'})
      if (item.done) return value
      yield value
      if (value?.kind === 'text' && !sampled) {
        sampled = true
        const rows = await $.session.messages({as: 'api'})
        const usage = await $.session.usage()
        const snapshot = {phase: 'public_sse_session_prefix',
          apiRoles: rows.map(row => row.role),
          modelMessageIdVisible: JSON.stringify(rows).includes('msg_cold_reply'),
          sessionUsageFields: Object.keys(usage).sort()}
        $.ui.log('FLOWER-CORE-HTTP|' + JSON.stringify(snapshot) + '|END', {to: 'debug'})
      }
    }
  })
"""


def read_events():
    """读取当前唯一 CLI 的测试事件。@return 已观察到的事件。"""
    logs = list(Path("/native/tui-sessions").glob("*/home/.claude/core-http.log"))
    if not logs:
        return []
    (log,) = logs
    records = []
    for line in log.read_text(errors="replace").splitlines():
        _, marker, payload = line.partition(": " + core.MARKER)
        if marker and payload.startswith("{") and payload.endswith("|END"):
            try:
                record = json.loads(payload.removesuffix("|END"))
            except json.JSONDecodeError as error:
                raise AssertionError(("隔离钩子日志格式", payload)) from error
            records.append(record)
    return records


def compare(manage, token, identifier, received, sender_status, restart, *, source_observer, stream, candidate=False,
            hold_model_tail=False):
    """模型保留终帧时核对官方流事件和公开边界。@param manage 管理接口。@param token 合成凭据。
    @param identifier 隔离账号。@param received 模型实收。@param sender_status 发送器诊断。
    @param restart 重启处理器。@param source_observer 是否使用额外账号观测。
    @param stream 模型流屏障。@param candidate 是否启用完成态交付。@return 实测隔离对照。
    @param hold_model_tail 是否核对暂时无模型数据时原连接仍可交付。
    """
    assert not restart and not source_observer
    session = str(uuid4())
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": True,
            "messages": [{"role": "user", "content": PROBE_QUESTION}]}
    headers = {"x-session-id": session, "User-Agent": "flower2api-public-sse-observer/1"}
    public_headers = Event()
    public_times = {}

    def observe_response(response):
        public_times["response_headers_ns"] = monotonic_ns()
        fixture.startup_event("direct_sse_public_headers", status=response.status,
                              request_id=response.getheader("x-cc2api-request-id"))
        public_headers.set()

    def public_candidate():
        with closing(HTTPConnection("127.0.0.1", 18090, timeout=30)) as connection:
            connection.request("POST", "/v1/messages", fixture.encoded(body), headers={
                **headers, "authorization": "Bearer " + token, "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            })
            with closing(connection.getresponse()) as response:
                observe_response(response)
                request_id = response.getheader("x-cc2api-request-id")
                if response.status != 200:
                    return response.status, response.read(), request_id
                assert response.getheader("content-type").startswith("text/event-stream")
                prefix = bytearray()
                data_seen = False
                for line in iter(response.readline, b""):
                    prefix.extend(line)
                    if line.startswith(b"data:"):
                        data_seen = True
                    elif data_seen and line in (b"\n", b"\r\n"):
                        public_times["first_data_frame_ns"] = monotonic_ns()
                        break
                return response.status, bytes(prefix) + response.read(), request_id

    def before_tail():
        rows = read_events()
        snapshot = next((row for row in rows if row["phase"] == "public_sse_session_prefix"), None)
        if snapshot is not None:
            return [row for row in rows if row["phase"] == "public_sse_chunk"], snapshot

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(public_candidate) if candidate else pool.submit(
            fixture.checked_messages, manage, token, body, headers, received, "isolated_public_sse",
            expected_status=502, trace_startup=True, sender_status=sender_status, observe_response=observe_response,
        )
        try:
            early, session_prefix = fixture.wait_for(before_tail)
            assert len(received) == 1 and stream.written > 0 and not stream.writing_tail.is_set()
            assert not stream.completed.is_set() and not public_headers.is_set() and not pending.done()
            assert [row["kind"] for row in early] == ["engine", "engine", "text"], early
            assert all(row["inputCount"] is None and not row["modelMessageIdVisible"] for row in early), early
            assert all(row["fields"] == ["kind", "ref"] for row in early[:2]), early
            assert session_prefix["apiRoles"] == ["user"] and not session_prefix["modelMessageIdVisible"], session_prefix
            start = stream.events[0]["message"]
            assert start["id"] == "msg_cold_reply" and start["usage"]["input_tokens"] > 0, start
            assert early[2]["text"] == stream.events[2]["delta"]["text"], early
            if hold_model_tail:
                sleep(6)
                assert not stream.writing_tail.is_set() and not public_headers.is_set()
        finally:
            stream.release.set()
        status, raw, request_id = pending.result()
    assert stream.completed.wait(5) and len(received) == 1
    (permit,) = map(json.loads, Path("/tmp/flower-direct-permits.jsonl").read_text().splitlines())
    (tunnel,) = map(json.loads, Path("/tmp/flower-direct-tunnels.jsonl").read_text().splitlines())
    diagnostics = fixture.report_request_diagnostics(manage, "isolated_public_sse", request_id, session, None)
    (request,) = diagnostics["requests"]
    assert request["status_code"] == status
    reservation_id = request["diagnostic_context"]["tui_reservation_id"]
    assert permit["allowed"] and permit["reservation_id"] == tunnel["reservation_id"] == reservation_id
    assert permit["cli_pid"] == tunnel["cli_pid"]
    events = read_events()
    model_reply = [row for row in events if row.get("origin") == "engine"
                   and row.get("model") and row["phase"] == "reply"]
    (reply,) = model_reply
    assert (reply["status"], reply["isStreaming"], reply["textLength"]) == (200, True, 0), reply
    result = {"authorization": "isolated_managed_policy", "stream": body["stream"], "request_id": request_id,
            "permit": permit, "tunnel": tunnel, "model_posts": len(received), "early_hook_events": early,
            "model_first_frame": start, "early_session_snapshot": session_prefix,
            "step_results_after_tail": [row for row in events if row["phase"] == "public_sse_step_result"],
            "public_diagnostics": diagnostics,
            "public_headers_before_model_tail": False, "http_status": status,
            "core_reply": reply, "wire_final": "unavailable"}
    if not candidate:
        return {**result, "public_error": json.loads(raw)["error"]}
    assert status == 200, (status, raw, request_id)
    events = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
    assert [event["type"] for event in events] == [event["type"] for event in stream.events]
    assert events[2]["delta"] == stream.events[2]["delta"]
    assert events[0]["message"]["usage"]["input_tokens"] == start["usage"]["input_tokens"]
    assert events[-2]["usage"]["output_tokens"] == stream.events[-2]["usage"]["output_tokens"]
    assert events[-2]["delta"]["stop_reason"] == "end_turn"
    assert stream.first_frame_ns < stream.ended_ns <= public_times["response_headers_ns"] <= public_times["first_data_frame_ns"]
    (attempt,) = request["attempts"]
    assert attempt["attempt_id"] == reservation_id and attempt["request_id"] == request_id
    return {**result, "data_frames": len(events), "answer": events[2]["delta"]["text"],
            "timing_ns": {"model_first_frame_ns": stream.first_frame_ns, "model_end_ns": stream.ended_ns, **public_times}}


def main():
    """运行仅回环的受管钩子对照。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, default=SENDER)
    parser.add_argument("--direct-candidate", action="store_true", help="验收模型结束后的候选公开事件流")
    parser.add_argument("--hold-model-tail", action="store_true", help="隔离模型发送前缀后空闲六秒")
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    version = "2.1.321"
    digest = core.PROGRAMS[version]
    with Path(f"/cli/{version}/node_modules/.bin/claude").open("rb") as executable:
        assert file_digest(executable, "sha256").hexdigest() == digest
    core.install(version, digest, "tool", "managed")
    install_permit(CANDIDATE_MODE if args.direct_candidate else "observe-sse")
    module = Path(f"/opt/{core.POLICY_MARKET}/{core.POLICY_PLUGIN}/hooks/observe.js")
    source = module.read_text()
    assert source.endswith("\n}\n")
    module.write_text(source[:-3] + EARLY_STREAM_HOOK + "\n}\n")
    stream = ModelStream(pressure=False)
    with patch.multiple(
        fixture, QuietHandler=core.ObservedModel,
        verify_structured_tool_round=partial(compare, stream=stream, candidate=args.direct_candidate,
                                              hold_model_tail=args.hold_model_tail),
    ), TemporaryDirectory(prefix="tui-sse-observer-") as folder:
        proof = fixture.verify(args.gateway, args.sender, Path(folder), installed_runtime=True, structured_output="live",
                               model_stream_probe=stream, trace_startup=True)
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
