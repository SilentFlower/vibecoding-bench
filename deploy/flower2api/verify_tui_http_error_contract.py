"""用两种同状态、同消息的拒绝对照现行公开错误与受管 CLI 直发试接。"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from functools import partial
from hashlib import file_digest, sha256
import json
from pathlib import Path
from socket import if_nameindex
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import verify_tui_cold_history as fixture
import verify_tui_core_http_hook as core


ERROR_TYPES = ("invalid_request_error", "api_error")
ERROR_MESSAGE = "隔离模型明确拒绝合成请求"
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


def install_turn_hooks():
    """在同一个官方受管 Mod 内开启只读阶段观测。@return 无。"""
    digest = core.PROGRAMS[VERSION]
    program = Path(f"/cli/{VERSION}/node_modules/.bin/claude")
    with program.open("rb") as executable:
        assert file_digest(executable, "sha256").hexdigest() == digest
    core.install(VERSION, digest, "error", "managed")
    module = Path(f"/opt/{core.POLICY_MARKET}/{core.POLICY_PLUGIN}/hooks/observe.js")
    source = module.read_text()
    assert source.endswith("\n}\n")
    marker = "record({phase: 'reply', keys: Object.keys(value), status: value.status, header,"
    assert source.count(marker) == 1
    source = source.replace(marker, marker + "\n        responseHeaders: headers,")
    module.write_text(source[:-3] + TURN_HOOKS + "\n}\n")


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


def check(manage, token, identifier, received, sender_status, restart, *, source_observer, path, error, emitted):
    """关联公开回包与原模型拒绝。@param manage 管理入口。@param token 合成凭据。
    @param identifier 当前账号。@param received 模型收件。@param sender_status 诊断读取。
    @param restart 重启选项。@param source_observer 额外事件源观测。
    @param path 验证路线。@param error 期望的旧公开错误。@param emitted 模型实发的错误。
    @return 请求、尝试、实收与钩子记录。
    """
    assert not source_observer and not restart
    session = str(uuid4())
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": False, "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": fixture.REJECT_MODEL_REQUEST}]}
    headers = {"x-session-id": session, "User-Agent": "flower2api-http-error-proof/1"}
    phase = f"http_error_{path}_{error['type']}"
    started_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    status, raw, request_id = fixture.checked_messages(
        manage, token, body, headers, received, phase, expected_status=400 if path == "account" else 502,
        trace_startup=True, sender_status=sender_status,
    )
    diagnostics = fixture.report_request_diagnostics(manage, phase, request_id, session, started_at)
    (row,) = diagnostics["requests"]
    (attempt,) = row["attempts"]
    assert row["request_id"] == attempt["request_id"] == request_id and row["attempt_count"] == 1, row
    assert row["status_code"] == attempt["status_code"] == status, row
    assert attempt["attempt_id"] == row["diagnostic_context"]["tui_reservation_id"], row
    (model_digest, _, tls), = received
    (model_error,) = emitted
    public = json.loads(raw)
    if path == "account":
        assert public == {"type": "error", "error": error}, public
    else:
        assert public["error"]["type"] == "api_error", public
    return {"path": path, "http_status": status, "public_body": public, "request_id": request_id,
            "model_posts": len(received), "model_request_sha256": model_digest, "model_tls": tls,
            "model_response": model_error, "diagnostics": diagnostics,
            "hooks": verify_hooks() if path == "cli" else None, "wire_final": "unavailable"}


def main():
    """运行单个错误样本。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--path", choices=("account", "cli"), required=True)
    parser.add_argument("--error-type", choices=ERROR_TYPES, required=True)
    parser.add_argument("--gateway", type=Path, required=True)
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    if args.path == "cli":
        install_turn_hooks()
    error = {"type": args.error_type, "message": ERROR_MESSAGE}
    # 让原状态、消息、长度与响应头保持相同。公开错误类型的差异来自正文。
    padding = "x" * (len(max(ERROR_TYPES, key=len)) - len(args.error_type))
    payload = {"type": "error", "error": {**error, "details": {"tag": "isolated-provider-detail", "padding": padding}}}
    emit = fixture.response_json
    emitted = []

    def model_reply(handler, value, *, status=200, headers=None):
        if status == 400 and handler.path == "/v1/messages" and value == {"type": "error", "error": {
            "type": "invalid_request_error", "message": ERROR_MESSAGE,
        }}:
            value = payload
            raw = json.dumps(value).encode()
            emit(handler, value, status=status, headers=headers)
            emitted.append({"status": status, "body": value, "body_octets": len(raw), "body_sha256": sha256(raw).hexdigest()})
            return
        emit(handler, value, status=status, headers=headers)

    with patch.multiple(
        fixture, QuietHandler=FixedDateModel, response_json=model_reply,
        verify_structured_tool_round=partial(check, path=args.path, error=error, emitted=emitted),
    ), TemporaryDirectory(prefix="http-error-contract-") as folder:
        result = fixture.verify(
            args.gateway, Path("/usr/local/bin/account-sender"), Path(folder), installed_runtime=True,
            structured_output="live", trace_startup=True, failure_boundaries=True, model_connection_contract="server-close",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
