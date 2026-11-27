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


def main():
    """在仅回环容器运行固定账号事件源。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=("live", "restart"), required=True)
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

    fixture.install_source()
    with patch.multiple(fixture, QuietHandler=ModelHeaders,
                        verify_structured_tool_round=partial(verify, model_betas=model_betas)), TemporaryDirectory(
                            prefix="tui-context-keep-all-") as temporary:
        proof = fixture.verify(
            args.gateway, args.sender, Path(temporary), installed_runtime=True, structured_output=args.case,
            signed_tool_history=True, trace_startup=True,
        )
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
