"""核对固定 CLI 支持的普通 Messages 思考历史管理及回执归属。"""

from argparse import ArgumentParser
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
from socket import if_nameindex
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import verify_tui_cold_history as fixture


MODELS = ("claude-sonnet-4-6", "claude-opus-5-5")
BETA = "context-management-2025-06-27"
THINKING = {"type": "adaptive", "display": "updates"}
EDIT = {"type": "clear_thinking_20251015"}
KEEP_ALL = {"edits": [{**EDIT, "keep": "all"}]}
KEEP_ONE = {"edits": [{**EDIT, "keep": {"type": "thinking_turns", "value": 1}}]}
KEEP_DEFAULT = {"edits": [EDIT]}
CLEAR_TOOLS = {"edits": [{
    "type": "clear_tool_uses_20250919", "trigger": {"type": "tool_uses", "value": 1},
    "keep": {"type": "tool_uses", "value": 1},
}]}


class ContextReport:
    """在隔离模型的最终消息增量发出真实协议形状的上下文编辑报告。"""

    def __init__(self):
        """初始化单次请求要交付的字段。@return 无。"""
        self.fields = {}

    def prepare(self, wire):
        """将报告附在消息增量的顶层。@param wire 隔离模型原流。@return 模型将发出的完整流。"""
        if not self.fields:
            return wire
        frames = [json.loads(line[5:]) for line in wire.splitlines() if line.startswith(b"data:")]
        assert frames[-2]["type"] == "message_delta"
        frames[-2].update(self.fields)
        return b"".join(map(fixture.frame, frames))

    @staticmethod
    def write(handler, wire):
        """写出隔离模型响应。@param handler 接收模型请求的处理器。@param wire 响应字节。@return 无。"""
        handler.wfile.write(wire)


def verify(manage, token, identifier, received, sender_status, restart, *, source_observer, model_betas):
    """从公开接口核对模型实收。
    @param manage 管理 API。@param token 隔离凭据。@param identifier 当前账号。
    @param received 模型实收。@param sender_status sender 就绪接口。@param restart 可选原进程重启。
    @param source_observer 是否注入模型正文观测。@param model_betas 隔离接收器实收 beta。
    @return 输入、回执及诊断对照。
    """
    assert not source_observer
    cases = {}

    def post(label, body, headers, status, source=None, *, receipt=False):
        before = len(received)
        session = headers["x-session-id"]
        started = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        actual, raw, request_id = fixture.checked_messages(
            manage, token, body, headers, received, label, expected_status=status, trace_startup=True,
            sender_status=sender_status, trace_recovery_resend=bool(restart and receipt),
        )
        diagnostics = fixture.report_request_diagnostics(manage, label, request_id, session, started)
        (request,) = diagnostics["requests"]
        context = request["diagnostic_context"]
        party = {"request_id": request_id, "reservation_id": context.get("tui_reservation_id"),
                 "http_status": actual, "model_posts": len(received) - before, "diagnostics": request}
        cases[label] = party
        reply = json.loads(raw)
        if source is None:
            assert request["attempt_count"] == 0 and len(received) == before, party
            if status == 422:
                assert reply["error"]["code"] == "unsupported_parameter", reply
            return reply, None
        assert len(model_betas) == len(received) == before + 1, party
        assert request["attempt_count"] == context["tui_confirmed_model_responses"] == 1, party
        (attempt,) = request["attempts"]
        assert attempt["attempt_id"] == party["reservation_id"] and attempt["request_id"] == request_id
        assert attempt["diagnostic_context"]["tui_body_source"] == source, party
        digest, model_request, _ = received[-1]
        assert model_request["thinking"] == body["thinking"] and model_request["model"] == body["model"], model_request
        assert model_request["context_management"] == body["context_management"] and BETA in model_betas[-1], party
        party.update(model=model_request["model"], thinking=model_request["thinking"],
                     context_management=model_request["context_management"], beta=model_betas[-1],
                     model_body_sha256=digest)
        return reply, model_request

    def question(model, policy, context):
        session = str(uuid4())
        body = {"model": model, "max_tokens": 4096, "stream": False, "system": fixture.SYSTEM[0],
                "messages": [{"role": "user", "content": f"请读回 {policy} {model} 的合成便签。"}],
                "thinking": THINKING, "context_management": context}
        return body, {"x-session-id": session, "User-Agent": "flower2api-context-keep-all/1"}

    for policy in ("append", "replace", "user_reminder"):
        account = manage("PUT", f"accounts/{identifier}", {"client_system_prompt_policy": policy})
        assert account["client_system_prompt_policy"] == policy
        for model in MODELS:
            label = f"{policy}_{model}"
            body, headers = question(model, policy, KEEP_ALL)
            if model == MODELS[0]:
                headers["anthropic-beta"] = BETA
            body["tools"] = [fixture.TOOL]
            first, native = post(label + "_initial", body, headers, 200, "interactive_cli")
            location = "user_reminder" if policy == "user_reminder" else "system"
            first_context = cases[label + "_initial"]["diagnostics"]["attempts"][0]["diagnostic_context"]
            assert first_context["tui_instruction_location"] == location, first_context
            assert first["stop_reason"] == "tool_use", first
            (tool,) = [block for block in first["content"] if block["type"] == "tool_use"]
            assert (tool["name"], tool["input"]) == (fixture.TOOL["name"], fixture.ARGS), tool
            (declaration,) = [tool for tool in native["tools"] if tool.get("description") == fixture.TOOL["description"]]
            result = {"type": "tool_result", "tool_use_id": tool["id"], "content": fixture.REPLY}
            reply = {**body, "messages": [*body["messages"], {"role": "assistant", "content": first["content"]},
                                          {"role": "user", "content": [result]}]}
            if restart is not None:
                restart(headers)
            altered = {key: value for key, value in reply.items() if key != "context_management"}
            post(label + "_removed_context", altered, headers, 422)
            post(label + "_changed_context", {**reply, "context_management": KEEP_ONE}, headers, 422)
            last, native = post(label + "_receipt", reply, headers, 200, "interactive_cli", receipt=True)
            assert last["stop_reason"] == "end_turn", last
            ((role, native_tool),) = fixture.find_blocks(native, "id", tool["id"])
            assert role == "assistant" and native_tool["name"] == declaration["name"], native_tool
            assert native_tool["input"] == tool["input"], native_tool
            ((role, native_result),) = fixture.find_blocks(native, "tool_use_id", tool["id"])
            assert role == "user" and native_result["content"].count(fixture.REPLY) == 1, native_result
            receipt_context = cases[label + "_receipt"]["diagnostics"]["attempts"][0]["diagnostic_context"]
            assert receipt_context["tui_session_origin"] == ("disk_resume" if restart else "live_process"), receipt_context
            cases[label + "_receipt"]["tool_use_id"] = tool["id"]
            post(label + "_duplicate", reply, headers, 400)

        if restart is None:
            for variant, context in (("keep_one", KEEP_ONE), ("keep_default", KEEP_DEFAULT)):
                body, headers = question(MODELS[0], policy, context)
                status, source = (200, "account_sender") if policy == "append" else (422, None)
                post(f"{policy}_{variant}", body, headers, status, source)
    assert len(received) == len(model_betas) == 12 + 2 * (restart is None)
    return {"state": "live" if restart is None else "restart", "cases": cases, "model_posts": len(received),
            "wire_final": "unavailable"}


def verify_response(manage, token, identifier, received, sender_status, restart, *, source_observer, model_betas, probe):
    """核对模型上下文编辑报告在两种公开表示中的字段位置。
    @param manage 管理 API。@param token 合成凭据。@param identifier 当前账号。
    @param received 隔离模型实收。@param sender_status sender 失败观测。@param restart 原进程重启选项。
    @param source_observer 是否替换模型正文观察器。@param model_betas 模型实收功能头。
    @param probe 隔离模型的报告发送器。@return 按公开请求关联的结果。
    """
    assert not source_observer and restart is None
    assert manage("PUT", f"accounts/{identifier}", {
        "client_system_prompt_policy": "append",
    })["client_system_prompt_policy"] == "append"
    report = {"applied_edits": [{"type": CLEAR_TOOLS["edits"][0]["type"],
                                "cleared_tool_uses": 1, "cleared_input_tokens": 17}]}
    variants = (
        ("clear_tools", CLEAR_TOOLS, "account_sender", {"context_management": report}),
        ("keep_all", KEEP_ALL, "interactive_cli", {"context_management": {"applied_edits": []}}),
        ("null", KEEP_ALL, "interactive_cli", {"context_management": None}),
        ("omitted", None, "interactive_cli", {}),
    )
    cases = {}
    for label, context, source, fields in variants:
        for stream in (True, False):
            phase = label + ("_sse" if stream else "_json")
            headers = {"x-session-id": str(uuid4()), "anthropic-beta": BETA,
                       "User-Agent": "flower2api-context-report/1"}
            body = {"model": MODELS[0], "max_tokens": 4096, "stream": stream, "thinking": THINKING,
                    "messages": [{"role": "user", "content": f"合成上下文编辑报告 {phase}"}]}
            if context is not None:
                body["context_management"] = context
            probe.fields = fields
            before = len(received)
            status, raw, request_id = fixture.checked_messages(
                manage, token, body, headers, received, phase, expected_status=200,
                trace_startup=True, sender_status=sender_status,
            )
            ((digest, native, _),) = received[before:]
            if context is not None:
                assert native["context_management"] == context and BETA in model_betas[-1], (phase, native)
            (record,) = fixture.report_request_diagnostics(
                manage, phase, request_id, headers["x-session-id"], None,
            )["requests"]
            (attempt,) = record["attempts"]
            reservation = record["diagnostic_context"]["tui_reservation_id"]
            assert attempt["request_id"] == request_id and attempt["attempt_id"] == reservation
            assert record["attempt_count"] == record["diagnostic_context"]["tui_confirmed_model_responses"] == 1
            assert attempt["diagnostic_context"]["tui_body_source"] == source, (phase, attempt)
            if stream:
                frames = [json.loads(line[5:]) for line in raw.splitlines() if line.startswith(b"data:")]
                (terminal,) = [event for event in frames if event["type"] == "message_delta"]
                text, stop = fixture.structured_sse_text(raw, phase)
                usage = terminal["usage"]
            else:
                terminal = json.loads(raw)
                (block,) = terminal["content"]
                assert block["type"] == "text", (phase, block)
                text, stop, usage = block["text"], terminal["stop_reason"], terminal["usage"]
            observed = {key: terminal[key] for key in ("context_management",) if key in terminal}
            assert fixture.same_json_value(observed, fields), (phase, observed, fields)
            assert (text, stop, usage["output_tokens"]) == (fixture.FINAL, "end_turn", 8), (phase, terminal)
            cases[phase] = {"status": status, "request_id": request_id, "reservation_id": reservation,
                            "provider_path": source, "response_fields": observed, "model_body_sha256": digest}
    assert len(received) == len(model_betas) == len(cases) == 8
    return {"cases": cases, "model_posts": len(received), "wire_final": "unavailable"}


def main():
    """在仅回环容器运行固定账号事件源。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("live", "restart", "response"), required=True)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, default=Path("/usr/local/bin/account-sender"))
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    model_betas = []

    class ModelHeaders(fixture.QuietHandler):
        """只记录模型接收器实际收到的协议 beta。"""

        def parse_request(self):
            """读取已解析模型请求中的 beta。@return 原解析结果。"""
            parsed = super().parse_request()
            if parsed and self.command == "POST" and urlsplit(self.path).path == "/v1/messages":
                model_betas.append([value.strip() for value in self.headers.get("anthropic-beta", "").split(",")
                                    if value.strip()])
            return parsed

    probe = ContextReport() if args.case == "response" else None
    check = partial(verify_response, model_betas=model_betas, probe=probe) if probe else partial(
        verify, model_betas=model_betas,
    )
    fixture.install_source()
    with patch.multiple(fixture, QuietHandler=ModelHeaders,
                        verify_structured_tool_round=check), TemporaryDirectory(
                            prefix="tui-context-keep-all-") as temporary:
        proof = fixture.verify(
            args.gateway, args.sender, Path(temporary), installed_runtime=True,
            structured_output="restart" if args.case == "restart" else "live",
            signed_tool_history=probe is None, trace_startup=True, model_stream_probe=probe,
        )
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
