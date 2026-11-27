"""核对同一隔离 TLS 隧道上两个真实 CLI 模型 POST 的许可和预留。"""

from argparse import ArgumentParser
from functools import partial
from hashlib import file_digest
import json
from os import kill
from pathlib import Path
from shutil import copy2
from signal import SIGTERM
from socket import if_nameindex
from tempfile import TemporaryDirectory
from time import monotonic_ns
from unittest.mock import patch
from uuid import UUID

import verify_tui_cold_history as fixture
import verify_tui_core_http_hook as core
import verify_tui_guarded_egress as guarded
from fixtures.native_model_send.direct_egress_identity import model_body_identity
from verify_tui_public_sse import ModelStream


CANDIDATE_MODE = "candidate-response"
PERMIT_HOOK = """
    let replyTicket, endpoint, bearer
    if (model) {
      const bindingPath = await $.env.get('FLOWER_TUI_DIRECT_BINDING')
      if (typeof bindingPath !== 'string') return {deny: '隔离模型缺少本会话授权'}
      const binding = JSON.parse(await $.fs.read(bindingPath))
      endpoint = binding.endpoint
      bearer = binding.bearer
      const permit = await $.http.fetch(endpoint + '/direct-http-permit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + bearer},
        body: JSON.stringify({url: address, method: e.init?.method, body: e.init?.body,
          requestId: e.init?.headers?.['x-client-request-id'] ?? null}),
      })
      const grant = permit.ok ? JSON.parse(permit.text) : null
      if (grant?.allowed !== true) {
        record({phase: 'denied', callbackStatus: permit.status})
        return {deny: '隔离模型未取得当前预留许可'}
      }
      replyTicket = grant.reply_ticket
    }
"""
REPLY_HOOK = """
      if (replyTicket && (value.status === 200 || value.status === 400)) {
        try {
          await $.http.fetch(endpoint + '/direct-http-reply', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + bearer},
            body: JSON.stringify({ticket: replyTicket, status: value.status}),
          })
        } catch (error) {
          // 成功响应的状态观察缺失时，保留 CLI 已取得的模型响应。
          if (value.status === 400) throw error
        }
      }
"""
MOD_RECOVERY = """
  }).catch(() => ({deny: '隔离模型许可回调失败'}))
"""


def install_permit(mode):
    """安装受管的逐请求隔离闸门。@param mode 续轮授权或拒绝对照。@return 无。"""
    root = Path("/opt/flower/tui")
    fixture_path = Path(__file__).with_name("fixtures") / "native_model_send"
    copy2(fixture_path / "direct_egress_identity.py", root)
    (root / "fixture-direct-permit").write_text(mode)
    module = Path(f"/opt/{core.POLICY_MARKET}/{core.POLICY_PLUGIN}/hooks/observe.js")
    source = module.read_text()
    target = "    const reply = await next(e)"
    assert source.count(target) == 1 and source.endswith("  })\n\n}\n")
    source = source.replace(target, PERMIT_HOOK + target)
    if mode == CANDIDATE_MODE:
        response = "        hasErrorBody: value.text?.includes('隔离模型明确拒绝合成请求') ?? false})"
        assert source.count(response) == 1
        source = source.replace(response, response + "\n" + REPLY_HOOK)
    module.write_text(source.removesuffix("  })\n\n}\n") + MOD_RECOVERY + "\n}\n")


class ObservedModel(core.ObservedModel):
    """记录模型接收端的 SDK 请求 ID。"""

    def parse_request(self):
        """关联模型请求头与连接。@return 原解析结果。"""
        parsed = super().parse_request()
        if parsed and self.command == "POST" and self.path == "/v1/messages":
            fixture.startup_event("direct_model_http_identity", peer_port=self.client_address[1],
                                  sdk_request_id=self.headers.get("x-client-request-id"))
        return parsed


class ReceiptTail(ModelStream):
    """只在第二笔模型响应中分段写出合成文本。"""

    def prepare(self, wire):
        """为文本续轮保留闸门。@param wire 模型帧。@return 实际写出的帧。"""
        self.buffered = any(line.startswith(b"data:") and
                            json.loads(line[5:]).get("delta", {}).get("stop_reason") == "end_turn"
                            for line in wire.splitlines())
        return super().prepare(wire) if self.buffered else wire

    def write(self, handler, wire):
        """写出模型帧。@param handler 模型连接。@param wire 响应。@return 无。"""
        if self.buffered:
            super().write(handler, wire)
        else:
            handler.wfile.write(wire)


def collect(manage, token, identifier, received, sender_status, restart, *, source_observer, mode, stages,
            public_stream=False, receipt_tail=None, restart_before_receipt=False, live_projection=False):
    """关联公开请求、核心钩子、账号隧道和接收端。
    @param manage 管理入口。@param token 合成入口凭据。@param identifier 隔离账号。
    @param received 实际模型收件。@param sender_status 失败时的发送器诊断。
    @param restart 可用的发送器重启入口。@param source_observer 是否使用额外账号观测器。
    @param mode 试接模式。@param stages 实测代理和接收端事件。@return 隔离证据。
    @param public_stream 是否通过真实公开 SSE 执行工具。
    @param receipt_tail 断线用例的隔离模型终帧闸门。
    @param restart_before_receipt 是否在同一绑定结束旧 CLI 并验证从磁盘接续。
    @param live_projection 是否在原客户端实际读到增量后断开。
    """
    expected = 200 if mode == "allow" else 502

    def end_original_cli():
        (old,) = map(json.loads, Path("/tmp/flower-direct-tunnels.jsonl").read_text().splitlines())
        pid = old["cli_pid"]
        kill(pid, SIGTERM)
        fixture.wait_for(lambda: not Path(f"/proc/{pid}").exists())

    public = guarded.check(manage, token, identifier, received, sender_status, restart,
                           source_observer=source_observer, mode="tool", receipt_status=expected,
                           public_stream=public_stream, receipt_tail=receipt_tail,
                           before_receipt=end_original_cli if restart_before_receipt else None,
                           live_projection=live_projection)
    assert public["client_tool_executions"] == 1
    (log,) = Path("/native/tui-sessions").glob("*/home/.claude/core-http.log")
    lines = log.read_text(errors="replace").splitlines()
    assert any(f"{core.POLICY_PLUGIN}@{core.POLICY_MARKET}" in line and "tier prepend" in line for line in lines)
    events = [json.loads(line.split(core.MARKER, 1)[1].split("|END", 1)[0])
              for line in lines if core.MARKER in line and "|END" in line]
    model_events = [event for event in events if event["origin"] == "engine" and event["model"]]
    assert [event["phase"] for event in model_events] == (
        ["offer", "reply", "offer", "denied"] if mode == "deny-receipt" else ["offer", "reply"] * 2
    ), model_events
    assert all((event["status"], event["header"]) == (200, "model-http-200")
               for event in model_events if event["phase"] == "reply")
    tunnels = list(map(json.loads, Path("/tmp/flower-direct-tunnels.jsonl").read_text().splitlines()))
    assert len(tunnels) in ((1, 2) if receipt_tail is not None else (1,))
    if restart_before_receipt:
        assert len(tunnels) == 2 and tunnels[0]["cli_pid"] != tunnels[1]["cli_pid"]
    tunnel = tunnels[0]
    model_hops = {}
    for entrance, proxy, hello, hop in zip(tunnels, stages["proxy_connect_accepted"],
                                          stages["model_client_hello"], stages["proxy_model_tcp_connected"], strict=True):
        assert entrance["account_proxy_peer_port"] == proxy["peer_port"]
        assert hop["peer_port"] == hello["peer_port"] and hello["server_name"] == "api.anthropic.com"
        model_hops[hop["peer_port"]] = entrance
    posts = stages["model_received"]
    count = 1 if mode == "deny-receipt" else 2
    assert len(posts) == len(received) == count and set(row["peer_port"] for row in posts) == model_hops.keys(), stages
    digests = [digest for digest, _, _ in received]
    assert digests == [post["model_body_sha256"] for post in posts] and len(set(digests)) == count
    model_headers = stages["direct_model_http_identity"]
    assert [row["peer_port"] for row in model_headers] == [post["peer_port"] for post in posts]
    request_ids = [UUID(row["sdk_request_id"]) for row in model_headers]
    assert len(set(request_ids)) == count
    reservations = [public["initial"]["reservation_id"], public["reservation_id"]]
    assert all(reservations) and len(set(reservations)) == 2 and tunnel["reservation_id"] == reservations[0], public
    diagnostics = []
    for request, reservation in zip((public["initial"], public), reservations, strict=True):
        detail = manage("GET", "request-diagnostics/" + request["request_id"])
        (attempt,) = detail["attempts"]
        assert attempt["attempt_id"] == reservation and detail["request"]["status_code"] == request["status"], detail
        diagnostics.append({"request_id": request["request_id"], "reservation_id": reservation,
                            "account_id": attempt["account_id"], "status": request["status"]})
    assert diagnostics[0]["account_id"] == diagnostics[1]["account_id"]
    permits = []
    if mode != "connect-only":
        permits = list(map(json.loads, Path("/tmp/flower-direct-permits.jsonl").read_text().splitlines()))
        assert [row["reservation_id"] for row in permits] == reservations, permits
        assert [row["allowed"] for row in permits] == [True, mode == "allow"], permits
        granted = [row for row in permits if row["allowed"]]
        assert all(row["sdk_request_id"] == "[redacted]" for row in permits), permits
        assert all(row["cli_pid"] == model_hops[post["peer_port"]]["cli_pid"]
                   for row, post in zip(granted, posts, strict=True)), permits
        assert all(row["monotonic_ns"] < post["monotonic_ns"] for row, post in zip(granted, posts, strict=True))
        for row, (_, actual, _) in zip(granted, received, strict=True):
            row["observed_body_identity"] = model_body_identity(actual)
        assert all(row["body_identity"]["sha256"] == row["observed_body_identity"]["sha256"] for row in granted), granted
        assert all(row["body_identity"]["billing_cch"] == "00000"
                   and row["observed_body_identity"]["billing_cch"] not in (None, "00000") for row in granted), granted
        if len(tunnels) == 1:
            assert all(row["cli_pid"] == tunnel["cli_pid"] for row in permits), permits
            assert permits[0]["step"][0] == permits[1]["step"][0] and permits[0]["step"][1] != permits[1]["step"][1], permits
        else:
            assert permits[1]["reservation_id"] == tunnels[1]["reservation_id"]
    if mode != "allow":
        assert public["public_error"]["type"] == "api_error"
    return {"mode": mode, "restart_before_receipt": restart_before_receipt,
            "public": public, "cli_tunnel": tunnel, "cli_tunnels": tunnels, "permits": permits,
            "model_attempts": model_events, "transport": stages, "diagnostics": diagnostics,
            "wire_final": "unavailable"}


def main():
    """使用固定 CLI 与实验 guard，在断网容器运行单个复用对照。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("connect-only", "allow", "deny-receipt"), required=True)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, default=Path("/usr/local/bin/account-sender"))
    parser.add_argument("--direct-candidate", action="store_true", help="使用允许延后首帧的直发候选")
    parser.add_argument("--installed-direct-candidate", action="store_true", help="从镜像内置直发候选读取实时增量")
    parser.add_argument("--stream", action="store_true", help="经公开 SSE 交付工具和完整答复")
    parser.add_argument("--reconnect", action="store_true", help="在模型已收回执且公开首响前断开并接回")
    parser.add_argument("--restart-before-receipt", action="store_true", help="隔离工具首轮后结束旧 CLI")
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    if args.direct_candidate and args.mode != "allow":
        parser.error("直发候选需要 --mode allow")
    if args.stream and not args.direct_candidate:
        parser.error("公开 SSE 需要允许工具回执的直发候选")
    if args.reconnect and not args.stream:
        parser.error("断线接回需要 --stream")
    if args.restart_before_receipt and not args.reconnect:
        parser.error("冷接续对照需要 --reconnect")
    if args.installed_direct_candidate and not args.direct_candidate:
        parser.error("需要 --direct-candidate")
    version = "2.1.321"
    digest = core.PROGRAMS[version]
    with Path(f"/cli/{version}/node_modules/.bin/claude").open("rb") as stream:
        assert file_digest(stream, "sha256").hexdigest() == digest
    if args.installed_direct_candidate:
        assert Path("/opt/flower/tui/fixture-installed-direct").is_file()
    else:
        core.install(version, digest, "tool", "managed")
        if args.mode != "connect-only":
            install_permit(CANDIDATE_MODE if args.direct_candidate and args.mode == "allow" else args.mode)
    stages = {key: [] for key in ("proxy_connect_accepted", "proxy_model_tcp_connected",
                                 "model_client_hello", "model_received", "direct_model_http_identity")}
    observe = fixture.startup_event
    receipt_tail = ReceiptTail(pressure=False) if args.reconnect else None

    def capture(stage, **data):
        if stage in stages:
            stages[stage].append({**data, "monotonic_ns": monotonic_ns()})
        observe(stage, **data)

    with patch.multiple(
        fixture, QuietHandler=ObservedModel, startup_event=capture,
        verify_structured_tool_round=partial(collect, mode=args.mode, stages=stages, public_stream=args.stream,
                                              receipt_tail=receipt_tail, restart_before_receipt=args.restart_before_receipt,
                                              live_projection=args.installed_direct_candidate),
    ), TemporaryDirectory(prefix="tui-direct-reuse-") as folder:
        result = fixture.verify(
            args.gateway, args.sender, Path(folder), installed_runtime=True,
            structured_output="live", trace_startup=True, model_connection_contract="live", model_stream_probe=receipt_tail,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
