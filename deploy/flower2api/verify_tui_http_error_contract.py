"""用两种同状态、同消息的拒绝对照现行公开错误与受管 CLI 直发试接。"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from functools import partial
from hashlib import file_digest, sha256
import json
from pathlib import Path
from socket import if_nameindex
from tempfile import TemporaryDirectory
from time import monotonic_ns
from unittest.mock import patch
from uuid import uuid4

import verify_tui_cold_history as fixture
import verify_tui_core_http_hook as core
from verify_tui_direct_reuse import install_permit
from verify_tui_public_sse_observer import read_events


ERROR_TYPES = ("invalid_request_error", "api_error")
ERROR_MESSAGE = "隔离模型明确拒绝合成请求"
PROJECTED_ERROR = {"type": "api_error", "message": "V2 模型响应无效或提前终止"}
VERSION = "2.1.321"
TURN_HOOKS = """
  const fields = value => value != null && typeof value === 'object' ? Object.keys(value).sort() : []
  const inspect = (phase, value) => {
    const encoded = JSON.stringify(value) ?? ''
    return {phase, kind: value?.kind ?? null, fields: fields(value),
      hasProviderData: encoded.includes('isolated-provider-detail'),
      structuredErrorType: /"(type|error_type|code)":"(invalid_request_error|api_error)"/.exec(encoded)?.[2] ?? null,
      renderedError: value?.answer === 'API Error: 400 隔离模型明确拒绝合成请求'}
  }
  on('turn.step', async function* ($, e, next) {
    const stream = next(e)
    for (;;) {
      const part = await stream.next()
      const record = inspect(part.done ? 'step_result' : 'step_chunk', part.value)
      $.ui.log('FLOWER-CORE-HTTP|' + JSON.stringify(record) + '|END', {to: 'debug'})
      if (part.done) return part.value
      yield part.value
    }
  })
  on('turn.complete', async ($, e, next) => {
    const record = inspect('turn_complete', e)
    $.ui.log('FLOWER-CORE-HTTP|' + JSON.stringify(record) + '|END', {to: 'debug'})
    const transcript = await $.session.messages()
    const api = await $.session.messages({as: 'api'})
    for (const [phase, rows] of [['session_transcript', transcript], ['session_api', api]]) {
      const encoded = JSON.stringify(rows)
      const summary = {phase,
        roles: Array.isArray(rows) ? rows.map(row => row.role) : [],
        fields: Array.isArray(rows) ? rows.map(row => fields(row)) : [],
        hasProviderData: /invalid_request_error|api_error|isolated-provider-detail/.test(encoded),
        hasRenderedError: encoded.includes('隔离模型明确拒绝合成请求')}
      $.ui.log('FLOWER-CORE-HTTP|' + JSON.stringify(summary) + '|END', {to: 'debug'})
    }
    return next(e)
  })
"""


class FixedDateModel(core.ObservedModel):
    """给两个合成错误返回同一日期，保留其它普通 HTTP 响应行为。"""

    def date_time_string(self, timestamp=None):
        """读取固定的隔离日期。@param timestamp HTTP 服务传入的时刻。@return HTTP 日期。"""
        return "Thu, 26 Nov 2026 00:00:00 GMT"


def install_turn_hooks(*, public_stream):
    """在同一个官方受管 Mod 内开启阶段观测。@param public_stream 是否验收公开 SSE。@return 无。"""
    digest = core.PROGRAMS[VERSION]
    program = Path(f"/cli/{VERSION}/node_modules/.bin/claude")
    with program.open("rb") as executable:
        assert file_digest(executable, "sha256").hexdigest() == digest
    core.install(VERSION, digest, "tool" if public_stream else "error", "managed")
    if public_stream:
        install_permit("observe-sse")
    module = Path(f"/opt/{core.POLICY_MARKET}/{core.POLICY_PLUGIN}/hooks/observe.js")
    source = module.read_text()
    assert source.endswith("\n}\n")
    marker = "record({phase: 'reply', keys: Object.keys(value), status: value.status, header,"
    assert source.count(marker) == 1
    source = source.replace(marker, marker + "\n        responseHeaders: headers,")
    module.write_text(source if public_stream else source[:-3] + TURN_HOOKS + "\n}\n")


def verify_hooks():
    """读核心 HTTP、轮次和失败记录。@return 可公开的隔离钩子观测。"""
    (log,) = Path("/native/tui-sessions").glob("*/home/.claude/core-http.log")
    lines = log.read_text(errors="replace").splitlines()
    assert any(f"{core.POLICY_PLUGIN}@{core.POLICY_MARKET}" in line and "tier prepend" in line for line in lines)
    assert any("sec-default" in line and " loaded (" in line for line in lines)
    events = [json.loads(line.split(core.MARKER, 1)[1].split("|END", 1)[0])
              for line in lines if core.MARKER in line and "|END" in line]
    model = [event for event in events if event.get("model")]
    offer, reply = model
    assert (offer["phase"], offer["origin"], offer["method"]) == ("offer", "engine", "POST"), offer
    assert (reply["phase"], reply["status"], reply["header"], reply["isStreaming"], reply["textLength"]) == (
        "reply", 400, "model-http-400", True, 0,
    ), reply
    (stop,) = (event for event in events if event["phase"] == "stop_failure")
    assert (stop["category"], stop["detailsType"], stop["hasRenderedError"]) == ("unknown", "undefined", True), stop
    turn = [event for event in events if event["phase"] in ("step_chunk", "step_result", "turn_complete")]
    assert {event["phase"] for event in turn} == {"step_chunk", "step_result", "turn_complete"}, turn
    assert all(not event["hasProviderData"] and event["structuredErrorType"] is None for event in turn), turn
    session_rows = [event for event in events if event["phase"] in ("session_transcript", "session_api")]
    assert {row["phase"] for row in session_rows} == {"session_transcript", "session_api"}, session_rows
    assert all(row["roles"] and not row["hasProviderData"] for row in session_rows), session_rows
    return {"http_reply": reply, "turn": turn, "stop_failure": stop, "session_rows": session_rows}


def verify_model_connection(reservation_id, stages, model_digest):
    """按账号代理连接关联同一预留和模型实收。
    @param reservation_id 原公开预留。@param stages 两段代理及模型事件。
    @param model_digest 模型实收正文摘要。@return 专属隧道及实收事件。
    """
    (tunnel,) = map(json.loads, Path("/tmp/flower-direct-tunnels.jsonl").read_text().splitlines())
    assert tunnel["reservation_id"] == reservation_id, tunnel
    (connect,) = stages["proxy_connect_accepted"]
    (connection,) = stages["proxy_model_tcp_connected"]
    (post,) = stages["model_received"]
    assert tunnel["account_proxy_peer_port"] == connect["peer_port"]
    assert connection["peer_port"] == post["peer_port"] and post["model_body_sha256"] == model_digest
    return {"tunnel": tunnel, "model_received": post}


def verify_stream_hooks(reservation_id, stages, model_digest):
    """验证公开首帧前的真实 CLI 请求。@param reservation_id 原公开预留。
    @param stages 代理连接和模型收件。@param model_digest 模型实收正文摘要。
    @return 模型状态与物理归属。
    """
    offer, reply = [event for event in read_events() if event.get("model")]
    assert (offer["phase"], offer["origin"], offer["method"]) == ("offer", "engine", "POST"), offer
    assert (reply["phase"], reply["status"], reply["header"], reply["isStreaming"], reply["textLength"]) == (
        "reply", 400, "model-http-400", True, 0,
    ), reply
    connection = verify_model_connection(reservation_id, stages, model_digest)
    (permit,) = map(json.loads, Path("/tmp/flower-direct-permits.jsonl").read_text().splitlines())
    assert permit["allowed"] and permit["reservation_id"] == reservation_id
    assert permit["cli_pid"] == connection["tunnel"]["cli_pid"]
    return {"http_reply": reply, "permit": permit, **connection}


def check(manage, token, identifier, received, sender_status, restart, *, source_observer, path, error, emitted,
          public_stream, stages, upstream_status, expected_metadata=None):
    """关联公开回包与原模型拒绝。@param manage 管理入口。@param token 合成凭据。
    @param identifier 当前账号。@param received 模型收件。@param sender_status 诊断读取。
    @param restart 重启选项。@param source_observer 额外事件源观测。
    @param path 验证路线。@param error 期望的旧公开错误。@param emitted 模型实发的错误。
    @param public_stream 是否提交公开 stream:true。@param stages 代理及模型接收时点。
    @param upstream_status 模型确实返回的 HTTP 状态。
    @param expected_metadata 当前路径应公开交付的标准错误元数据。
    @return 请求、尝试、实收与钩子记录。
    """
    assert not source_observer and not restart
    session = str(uuid4())
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": public_stream, "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": fixture.REJECT_MODEL_REQUEST}]}
    headers = {"x-session-id": session, "User-Agent": "flower2api-http-error-proof/1"}
    phase = f"http_error_{path}_{error['type']}"
    started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    start = monotonic_ns()
    response_headers = {}

    def observe_response(response):
        response_headers["content_type"] = response.getheader("content-type")
        response_headers["monotonic_ns"] = monotonic_ns()
        response_headers["latency_ms"] = (response_headers["monotonic_ns"] - start) // 1_000_000

    status, raw, request_id = fixture.checked_messages(
        manage, token, body, headers, received, phase, expected_status=upstream_status if path == "account" else 502,
        trace_startup=True, sender_status=sender_status, observe_response=observe_response,
    )
    diagnostics = fixture.report_request_diagnostics(manage, phase, request_id, session, started_at)
    (row,) = diagnostics["requests"]
    assert row["request_id"] == request_id and row["status_code"] == status, row
    reservation_id = row["diagnostic_context"]["tui_reservation_id"]
    assert reservation_id and response_headers["content_type"].startswith("application/json"), response_headers
    (model_digest, _, tls), = received
    (model_error,) = emitted
    assert model_error["status"] == upstream_status, model_error
    public = json.loads(raw)
    if path == "account":
        expected = expected_metadata or {"type": "error", "error": error}
        assert public == expected, public
        assert row["diagnostic_context"]["tui_confirmed_model_responses"] == 1, row
    elif public_stream:
        assert isinstance(public.get("error"), str) and public["error"], public
    else:
        assert public == {"type": "error", "error": PROJECTED_ERROR}, public
    hooks = None
    if path == "cli":
        hooks = (verify_stream_hooks(reservation_id, stages, model_digest) if public_stream else
                 {**verify_hooks(), **verify_model_connection(reservation_id, stages, model_digest)})
        assert hooks["model_received"]["monotonic_ns"] < response_headers["monotonic_ns"], hooks
        # 实收与试接钩子是独立证据，Gateway 没有得到同一响应的结构化投影。
        assert (row["outcome"], row["error_stage"]) == ("transport_error", "tui_send_http"), (row, hooks)
        assert row["native_rejection"] is None, row
        assert row["diagnostic_context"].get("tui_confirmed_model_responses") is None, row
    else:
        assert (row["outcome"], row["error_stage"]) == ("upstream_rejected", "upstream_headers"), row
    if path == "cli" and public_stream:
        assert row["attempt_count"] == 0 and row["attempts"] == [], row
    else:
        (attempt,) = row["attempts"]
        assert attempt["request_id"] == request_id and attempt["status_code"] == (None if path == "cli" else status)
        assert attempt["attempt_id"] == reservation_id and row["attempt_count"] == 1, row
        assert (attempt["outcome"], attempt["error_stage"]) == (row["outcome"], row["error_stage"]), row
    return {"path": path, "stream": public_stream, "http_status": status, "public_body": public,
            "request_id": request_id, "reservation_id": reservation_id, "public_headers": response_headers,
            "model_posts": len(received), "model_request_sha256": model_digest, "model_tls": tls,
            "model_response": model_error, "diagnostics": diagnostics,
            "hooks": hooks, "wire_final": "unavailable"}


def main():
    """运行单个错误样本。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--path", choices=("account", "cli"), required=True)
    parser.add_argument("--error-type", choices=ERROR_TYPES, required=True)
    parser.add_argument("--stream", action="store_true", help="公开请求使用 stream:true，核对首帧前的 JSON 错误")
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, default=Path("/usr/local/bin/account-sender"))
    parser.add_argument("--source-account", action="store_true", help="用当前源码安装账号事件源")
    parser.add_argument("--error-metadata", choices=("valid", "invalid"), help="核对标准错误关联与结构化错误码")
    parser.add_argument("--upstream-status", choices=(400, 502), type=int, default=400,
                        help="账号路径可用同文真实 502 对照直发试接合成 502")
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    if args.path == "cli" and (args.source_account or args.error_metadata or args.upstream_status != 400):
        parser.error("可选错误元数据、候选账号源码及真实 502 需要 --path account")
    if args.upstream_status == 502 and args.error_type != PROJECTED_ERROR["type"]:
        parser.error("真实 502 对照需要 --error-type api_error")
    if args.path == "cli":
        install_turn_hooks(public_stream=args.stream)
    elif args.source_account:
        fixture.install_source()
    error = PROJECTED_ERROR if args.upstream_status == 502 else {"type": args.error_type, "message": ERROR_MESSAGE}
    # 让原状态、消息、长度与响应头保持相同。公开错误类型的差异来自正文。
    padding = "x" * (len(max(ERROR_TYPES, key=len)) - len(args.error_type))
    payload = {"type": "error", "error": {**error, "details": {"tag": "isolated-provider-detail", "padding": padding}}}
    expected_metadata = None
    if args.error_metadata == "valid":
        request_id = "req_01SyntheticMessagesError"
        details = {"error_code": "synthetic_invalid_parameter"}
        payload["request_id"] = request_id
        payload["error"]["details"].update(details)
        expected_metadata = {"type": "error", "error": {**error, "details": details}, "request_id": request_id}
    elif args.error_metadata == "invalid":
        payload["request_id"] = "req_非法"
        payload["error"]["details"]["error_code"] = {"private": "isolated-provider-detail"}
    emit = fixture.response_json
    emitted = []
    observe = fixture.startup_event
    stages = {name: [] for name in ("proxy_connect_accepted", "proxy_model_tcp_connected", "model_received")}

    def trace(stage, **data):
        if stage in stages:
            stages[stage].append({"monotonic_ns": monotonic_ns(), **data})
        observe(stage, **data)

    def model_reply(handler, value, *, status=200, headers=None):
        if status == 400 and handler.path == "/v1/messages" and value == {"type": "error", "error": {
            "type": "invalid_request_error", "message": ERROR_MESSAGE,
        }}:
            value = payload
            raw = json.dumps(value).encode()
            emit(handler, value, status=args.upstream_status, headers=headers)
            emitted.append({"status": args.upstream_status, "body": value, "body_octets": len(raw),
                            "body_sha256": sha256(raw).hexdigest()})
            return
        emit(handler, value, status=status, headers=headers)

    with patch.multiple(
        fixture, QuietHandler=FixedDateModel, response_json=model_reply, startup_event=trace,
        verify_structured_tool_round=partial(
            check, path=args.path, error=error, emitted=emitted, public_stream=args.stream, stages=stages,
            upstream_status=args.upstream_status, expected_metadata=expected_metadata,
        ),
    ), TemporaryDirectory(prefix="http-error-contract-") as folder:
        result = fixture.verify(
            args.gateway, args.sender, Path(folder), installed_runtime=True,
            structured_output="live", trace_startup=True, failure_boundaries=True, model_connection_contract="server-close",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
