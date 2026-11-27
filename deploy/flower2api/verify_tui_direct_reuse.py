"""核对同一隔离 TLS 隧道上两个真实 CLI 模型 POST 的许可和预留。"""

from argparse import ArgumentParser
from functools import partial
from hashlib import file_digest
import json
from os import chown
from pathlib import Path
from shutil import copy2
from socket import if_nameindex
from tempfile import TemporaryDirectory
from time import monotonic_ns
from unittest.mock import patch
from uuid import UUID

import verify_tui_cold_history as fixture
import verify_tui_core_http_hook as core
import verify_tui_guarded_egress as guarded
from fixtures.native_model_send.direct_egress_identity import model_body_identity


MOD_BINDING = "import { endpoint, bearer } from './runtime/binding.js'\n"
CANDIDATE_MODE = "candidate-response"
PERMIT_HOOK = """
    let replyTicket
    if (model) {
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
      if (replyTicket && value.status === 400) {
        await $.http.fetch(endpoint + '/direct-http-reply', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + bearer},
          body: JSON.stringify({ticket: replyTicket, status: value.status}),
        })
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
    runtime = module.parent / "runtime"
    runtime.mkdir(mode=0o700)
    chown(runtime, 1001, 1001)
    source = module.read_text()
    target = "    const reply = await next(e)"
    assert source.count(target) == 1 and source.endswith("  })\n\n}\n")
    source = source.replace(target, PERMIT_HOOK + target)
    if mode == CANDIDATE_MODE:
        response = "        hasErrorBody: value.text?.includes('隔离模型明确拒绝合成请求') ?? false})"
        assert source.count(response) == 1
        source = source.replace(response, response + "\n" + REPLY_HOOK)
    module.write_text(MOD_BINDING + source.removesuffix("  })\n\n}\n") + MOD_RECOVERY + "\n}\n")


class ObservedModel(core.ObservedModel):
    """记录模型接收端的 SDK 请求 ID。"""

    def parse_request(self):
        """关联模型请求头与连接。@return 原解析结果。"""
        parsed = super().parse_request()
        if parsed and self.command == "POST" and self.path == "/v1/messages":
            fixture.startup_event("direct_model_http_identity", peer_port=self.client_address[1],
                                  sdk_request_id=self.headers.get("x-client-request-id"))
        return parsed


def collect(manage, token, identifier, received, sender_status, restart, *, source_observer, mode, stages,
            public_stream=False):
    """关联公开请求、核心钩子、账号隧道和接收端。
    @param manage 管理入口。@param token 合成入口凭据。@param identifier 隔离账号。
    @param received 实际模型收件。@param sender_status 失败时的发送器诊断。
    @param restart 可用的发送器重启入口。@param source_observer 是否使用额外账号观测器。
    @param mode 试接模式。@param stages 实测代理和接收端事件。@return 隔离证据。
    @param public_stream 是否通过真实公开 SSE 执行工具。
    """
    expected = 200 if mode == "allow" else 502
    public = guarded.check(manage, token, identifier, received, sender_status, restart,
                           source_observer=source_observer, mode="tool", receipt_status=expected, public_stream=public_stream)
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
    (tunnel,) = map(json.loads, Path("/tmp/flower-direct-tunnels.jsonl").read_text().splitlines())
    (proxy,) = stages["proxy_connect_accepted"]
    (hello,) = stages["model_client_hello"]
    (hop,) = stages["proxy_model_tcp_connected"]
    assert tunnel["account_proxy_peer_port"] == proxy["peer_port"]
    assert hop["peer_port"] == hello["peer_port"] and hello["server_name"] == "api.anthropic.com"
    posts = stages["model_received"]
    count = 1 if mode == "deny-receipt" else 2
    assert len(posts) == len(received) == count and all(post["peer_port"] == hop["peer_port"] for post in posts), stages
    digests = [digest for digest, _, _ in received]
    assert digests == [post["model_body_sha256"] for post in posts] and len(set(digests)) == count
    model_headers = stages["direct_model_http_identity"]
    assert len(model_headers) == count and all(row["peer_port"] == hop["peer_port"] for row in model_headers)
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
        assert all(row["cli_pid"] == tunnel["cli_pid"] and row["sdk_request_id"] == "[redacted]"
                   for row in permits), permits
        granted = [row for row in permits if row["allowed"]]
        assert all(row["monotonic_ns"] < post["monotonic_ns"] for row, post in zip(granted, posts, strict=True))
        for row, (_, actual, _) in zip(granted, received, strict=True):
            row["observed_body_identity"] = model_body_identity(actual)
        assert all(row["body_identity"]["sha256"] == row["observed_body_identity"]["sha256"] for row in granted), granted
        assert all(row["body_identity"]["billing_cch"] == "00000"
                   and row["observed_body_identity"]["billing_cch"] not in (None, "00000") for row in granted), granted
        assert permits[0]["step"][0] == permits[1]["step"][0] and permits[0]["step"][1] != permits[1]["step"][1], permits
    if mode != "allow":
        assert public["public_error"]["type"] == "api_error"
    return {"mode": mode, "public": public, "cli_tunnel": tunnel, "permits": permits,
            "model_attempts": model_events, "transport": stages, "diagnostics": diagnostics,
            "wire_final": "unavailable"}


def main():
    """使用固定 CLI 与实验 guard，在断网容器运行单个复用对照。@return 无。"""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("connect-only", "allow", "deny-receipt"), required=True)
    parser.add_argument("--gateway", type=Path, required=True)
    parser.add_argument("--sender", type=Path, default=Path("/usr/local/bin/account-sender"))
    parser.add_argument("--direct-candidate", action="store_true", help="使用允许延后首帧的直发候选")
    parser.add_argument("--stream", action="store_true", help="经公开 SSE 交付工具和完整答复")
    args = parser.parse_args()
    assert Path("/.dockerenv").is_file() and {name for _, name in if_nameindex()} == {"lo"}
    if args.direct_candidate and args.mode != "allow":
        parser.error("直发候选需要 --mode allow")
    if args.stream and not args.direct_candidate:
        parser.error("公开 SSE 需要允许工具回执的直发候选")
    version = "2.1.321"
    digest = core.PROGRAMS[version]
    with Path(f"/cli/{version}/node_modules/.bin/claude").open("rb") as stream:
        assert file_digest(stream, "sha256").hexdigest() == digest
    core.install(version, digest, "tool", "managed")
    if args.mode != "connect-only":
        install_permit(CANDIDATE_MODE if args.direct_candidate and args.mode == "allow" else args.mode)
    stages = {key: [] for key in ("proxy_connect_accepted", "proxy_model_tcp_connected",
                                 "model_client_hello", "model_received", "direct_model_http_identity")}
    observe = fixture.startup_event

    def capture(stage, **data):
        if stage in stages:
            stages[stage].append({**data, "monotonic_ns": monotonic_ns()})
        observe(stage, **data)

    with patch.multiple(
        fixture, QuietHandler=ObservedModel, startup_event=capture,
        verify_structured_tool_round=partial(collect, mode=args.mode, stages=stages, public_stream=args.stream),
    ), TemporaryDirectory(prefix="tui-direct-reuse-") as folder:
        result = fixture.verify(
            args.gateway, args.sender, Path(folder), installed_runtime=True,
            structured_output="live", trace_startup=True, model_connection_contract="live",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
