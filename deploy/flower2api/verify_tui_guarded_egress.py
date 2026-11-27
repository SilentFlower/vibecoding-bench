"""用隔离事件源验收原版 CLI 的公开文本和单组工具直发。"""

import argparse
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
from re import fullmatch
from shutil import copy2
from socket import if_nameindex
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import verify_tui_cold_history as fixture


def install():
    """只在一次性容器中安装有明确模式边界的试接。@return 无。"""
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
    mod.write_text(body[:start] + """
        await post($, 'direct-result', { turn: e.turnId, step: e.index, reason: response.stopReason,
          answer: response.answer, usage: response.usage,
          frames: (pending ?? []).filter(item => ['tool', 'input'].includes(item.kind)) })
""" + body[end:])


class ModelPath(fixture.QuietHandler):
    """让同一隔离模型接受原版直发的 beta 查询。"""

    def parse_request(self):
        """保留语义等价的标准 Messages 查询。@return 原解析结果。"""
        parsed = super().parse_request()
        if parsed and self.command == "POST" and self.path == "/v1/messages?beta=true":
            fixture.startup_event("isolated_direct_beta_query", path=urlsplit(self.path).path)
            self.path = "/v1/messages"
        return parsed


def check(manage, token, identifier, received, sender_status, restart, *, source_observer, mode):
    """通过正式网关提交简单非流式请求。@return 公开回执和模型实收。"""
    assert not source_observer and not restart
    headers = {"x-session-id": str(uuid4()), "User-Agent": "flower2api-direct-guarded-lab/1"}
    question = "从真实原版进程直接提交的合成问题。"
    body = {"model": fixture.MODEL, "max_tokens": 128, "stream": False, "thinking": {"type": "disabled"},
            "messages": [{"role": "user", "content": question}]}
    def post(label, request, expected):
        status, raw, request_id = fixture.checked_messages(
            manage, token, request, headers, received, label, expected_status=expected,
            trace_startup=True, sender_status=sender_status,
        )
        context = manage("GET", "request-diagnostics/" + request_id)["request"].get("context") or {}
        return json.loads(raw), {"status": status, "request_id": request_id,
                                 "reservation_id": context.get("tui_reservation_id")}

    first = None
    result = None
    if mode == "tool":
        body["tools"] = [fixture.TOOL]
        tool_reply, first = post("guarded_direct_tool_offer", body, 200)
        assert len(received) == 1 and tool_reply["stop_reason"] == "tool_use"
        assert tool_reply["content"] == [{"type": "tool_use", "id": fixture.NEW_ID,
                                          "name": fixture.TOOL["name"], "input": fixture.ARGS}]
        result = {"type": "tool_result", "tool_use_id": tool_reply["content"][0]["id"], "content": fixture.REPLY}
        follow = {**body, "messages": [*body["messages"], {"role": "assistant", "content": tool_reply["content"]},
                                      {"role": "user", "content": [result]}]}
        answer, request = post("guarded_direct_tool_receipt", follow, 200)
        _, duplicate = post("guarded_direct_tool_duplicate", follow, 400)
        assert len(received) == 2
        (role, block), = fixture.find_blocks(received[-1][1], "tool_use_id", result["tool_use_id"])
        assert role == "user" and block["content"].count(fixture.REPLY) == 1
        request["duplicate"] = duplicate
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
            "session_id": headers["x-session-id"], "model_posts": len(received), "model_body_sha256": model_hash,
            "model_tls": tls, "answer_id": answer["id"], "answer_sha256": sha256(fixture.FINAL.encode()).hexdigest(),
            "model_usage": answer["usage"], "wire_final": "unavailable"}


def main():
    """在仅回环容器替换本次试接用事件源。@return 无。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", required=True, type=Path)
    parser.add_argument("--sender", default=Path("/usr/local/bin/account-sender"), type=Path)
    parser.add_argument("--case", choices=("text", "tool"), required=True)
    args = parser.parse_args()
    install()
    with patch.multiple(
        fixture, QuietHandler=ModelPath, verify_structured_tool_round=partial(check, mode=args.case)
    ), TemporaryDirectory(prefix="guarded-direct-first-") as folder:
        result = fixture.verify(
            args.gateway, args.sender, Path(folder), installed_runtime=True, structured_output="live",
            trace_startup=True, model_connection_contract="server-close",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
