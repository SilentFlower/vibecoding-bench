"""仅在隔离容器运行的正式入口直发实验事件源。"""

from contextlib import closing, suppress
from hashlib import sha256
from http.client import HTTPConnection
from ipaddress import ip_address
from os import getuid, getgid
from io import BytesIO
import json
from pathlib import Path
from select import select
from socket import if_nameindex
import ssl
import sys
from time import monotonic, monotonic_ns, sleep, time_ns
from urllib.parse import urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import frozen_tui_source as source
import tui_sender_launch as launcher
import tui_session as session

if not Path("/.dockerenv").is_file() or {name for _, name in if_nameindex()} != {"lo"}:
    raise RuntimeError("直发试接只允许在仅回环的验收容器运行")
TARGET = "api.anthropic.com"
CONFIG = json.loads(Path("/run/v3/sender.json").read_bytes())
PROXY = urlsplit(CONFIG["proxy_url"])
if (CONFIG.get("allowed_origin") != f"https://{TARGET}" or PROXY.scheme != "http"
        or not ip_address(PROXY.hostname).is_loopback or not PROXY.port or PROXY.username or PROXY.password):
    raise RuntimeError("直发试接只允许使用已配置的回环账号代理")
ORIGINAL_LAUNCH = launcher.launch_workspace_cli
ORIGINAL_CALLBACK = session._Actor.callback
POLICY_MODE = Path("/opt/flower/tui/fixture-direct-permit")
PERMITS = Path("/tmp/flower-direct-permits.jsonl")
TUNNELS = Path("/tmp/flower-direct-tunnels.jsonl")
CANDIDATE_MODE = "candidate-response"


def report(stage, **data):
    """输出一次隔离试接的非敏感证据。@return 无。"""
    print(json.dumps({"event": stage, **data}), file=sys.stderr, flush=True)


def launch(*args, environment, **options):
    """保留原工作区启动器与网络守卫，只替换测试实例的官方代理与端点设置。@return 子进程。"""
    config_dir = options["config_dir"]
    ca = config_dir / "lab-ca.pem"
    ca.write_text(ssl.DER_cert_to_PEM_cert(Path("/run/v3/verification-ca.der").read_bytes()))
    context = urlsplit(environment["ANTHROPIC_BASE_URL"])
    assert context.hostname == "127.0.0.1" and context.port
    settings = {**environment, "ANTHROPIC_BASE_URL": "https://" + TARGET,
                "HTTPS_PROXY": f"http://127.0.0.1:{context.port}", "NODE_EXTRA_CA_CERTS": str(ca),
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1",
                "CLAUDE_CODE_ENABLE_PROMPT_SUGGESTION": "0"}
    if POLICY_MODE.is_file():
        arguments = options["arguments"]
        mod = Path(arguments[arguments.index("--plugin-dir") + 1])
        # 一次性容器仅接入一个原生 actor。受管 Mod 使用此 actor 自己的回环回调授权。
        managed = Path("/opt/flower-http-test/flower-http-policy/hooks/runtime/binding.js")
        try:
            with managed.open("x") as listener:
                listener.write((mod / "hooks/binding.js").read_text())
        except OSError as error:
            report("direct_permit_launch_failed", error=type(error).__name__, errno=error.errno,
                   uid=getuid(), gid=getgid())
            raise
    return ORIGINAL_LAUNCH(*args, environment=settings, **options)


def _valid_attempt(actor, step, handle):
    mode = POLICY_MODE.read_text() if POLICY_MODE.is_file() else None
    probe_sse = handle and (mode == CANDIDATE_MODE or (not handle.tools and mode == "observe-sse"))
    return (step and step.native and handle and actor.process and not actor.dead.is_set()
            and len(handle.tools) <= 1 and (not handle.stream or probe_sse) and actor.oauth_file
            and handle.expires_at and handle.expires_at > time_ns() // 1_000_000
            and all(CONFIG["binding"][key] == handle.reservation[key]
                    for key in ("account_id", "environment_id", "generation")))


def _record_event(file, event, **data):
    with file.open("a") as stream:
        stream.write(json.dumps(data) + "\n")
    report(event, **data)


class Callback(session._Callback):
    """隔离实例的会话专属账号代理首跳。"""

    def do_CONNECT(self):
        """只允许已认领的主步骤建立一次固定目标隧道。@return 无。"""
        actor = self.server.actor
        with actor.changed:
            step, handle = actor.step, actor.claim
            gated = POLICY_MODE.is_file()
            if (self.path != TARGET + ":443" or not _valid_attempt(actor, step, handle)
                    or step.claimed != gated or getattr(actor, "direct_tunnel_step", None) is step):
                return self.send_error(403)
            peer = f"0100007F:{self.client_address[1]:04X}"
            here = f"0100007F:{self.server.server_port:04X}"
            (inode,) = [row[9] for line in Path("/proc/net/tcp").read_text().splitlines()[1:]
                        if (row := line.split())[1:4] == [peer, here, "01"]]
            for fd in Path(f"/proc/{actor.process.pid}/fd").iterdir():
                with suppress(FileNotFoundError):
                    if fd.readlink() == Path(f"socket:[{inode}]"):
                        break
            else:
                return self.send_error(403)
            actor.direct_tunnel_step = step
            if not gated:
                step.claimed = True
                handle.body_source = "interactive_cli"
            reservation = handle.reservation["reservation_id"]
        with closing(HTTPConnection(PROXY.hostname, PROXY.port, timeout=10)) as relay:
            relay.set_tunnel(TARGET, 443)
            relay.connect()
            _record_event(TUNNELS, "direct_tunnel", cli_pid=actor.process.pid,
                          source_port=self.client_address[1], inode=inode, session_proxy_port=self.server.server_port,
                          account_proxy_port=PROXY.port, account_proxy_peer_port=relay.sock.getsockname()[1],
                          reservation_id=reservation)
            self.send_response_only(200)
            self.end_headers()
            streams = {self.connection: relay.sock, relay.sock: self.connection}
            while ready := select(list(streams), [], [], 5)[0]:
                for stream in ready:
                    data = stream.recv(65536)
                    if not data:
                        return
                    streams[stream].sendall(data)


def _observe_after_archive(actor, data):
    config = actor.credential_dir
    assert config is not None
    until = monotonic() + 3
    while monotonic() < until:
        for archive in config.glob("projects/*/*.jsonl"):
            for line in archive.read_bytes().splitlines():
                row = json.loads(line)
                raw = row.get("message", {}) if row.get("type") == "assistant" else {}
                if (raw.get("stop_reason") == data["reason"] and raw.get("model") == actor.step.native_model
                        and raw.get("content") == [{"type": "text", "text": data["answer"]}]):
                    return raw
        sleep(0.03)
    raise ValueError("实际原生响应未出现在本会话归档")


def _deliver(actor, result, message, parts):
    events = [{"type": "message_start", "message": {**message, "stop_reason": None, "content": []}}]
    events.extend(parts)
    events.extend([
        {"type": "message_delta", "delta": {"stop_reason": result["reason"], "stop_sequence": None},
         "usage": result["usage"]},
        {"type": "message_stop"},
    ])
    wire = b"".join(("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n").encode()
                    for event in events)
    for _ in actor._model_events(actor.step, BytesIO(wire)):
        pass
    ORIGINAL_CALLBACK(actor, "/end", result)


def _authorize_http(actor, data):
    from direct_egress_identity import model_body_identity

    with actor.changed:
        step, handle = actor.step, actor.claim
        raw = data.get("body")
        allowed_path = data.get("url") in (
            f"https://{TARGET}/v1/messages", f"https://{TARGET}/v1/messages?beta=true",
        )
        if (not _valid_attempt(actor, step, handle) or step.claimed or not allowed_path
                or data.get("method") != "POST" or not isinstance(raw, str)):
            raise ValueError("缺少同一会话的当前模型预留")
        body = json.loads(raw)
        if not actor._main_request(body, handle):
            raise ValueError("模型输入不属于当前预留")
        mode = POLICY_MODE.read_text()
        allowed = not (mode == "deny-receipt" and handle.kind == "continuation")
        _record_event(PERMITS, "direct_http_permit", allowed=allowed, cli_pid=actor.process.pid,
                      monotonic_ns=monotonic_ns(),
                      reservation_id=handle.reservation["reservation_id"], step=list(step.native),
                      core_body_sha256=sha256(raw.encode()).hexdigest(),
                      sdk_request_id=data.get("requestId"),
                      body_identity=model_body_identity(body))
        if allowed:
            step.claimed = True
            handle.body_source = "interactive_cli"
            if mode == CANDIDATE_MODE:
                ticket = uuid4().hex
                actor.direct_http_reply = (step, handle, ticket)
                return {"allowed": True, "reply_ticket": ticket}
        return {"allowed": allowed}


def _project_http_rejection(actor, data):
    with actor.changed:
        step, handle = actor.step, actor.claim
        if (
            type(data.get("status")) is not int or data["status"] != 400
            or not isinstance(data.get("ticket"), str)
            or not _valid_attempt(actor, step, handle)
            or getattr(actor, "direct_http_reply", None) != (step, handle, data["ticket"])
            or not step.claimed or step.started
        ):
            raise session._StaleReceipt("直发响应不属于当前模型步骤")
        actor.direct_http_reply = None
        # 状态来自同次受管 HTTP 回包。正文继续沿公共通用错误格式生成。
        report("direct_http_rejection", reservation_id=handle.reservation["reservation_id"], status=400)
        actor.abort(session.ModelResponseError(400, b"", source="managed_oauth_http"))
    return {}


def callback(actor, path, data):
    """使用受信 Mod 的完成态投影单文本或单工具的 JSON 答复。@return 原协议回执。"""
    if path == "/direct-http-permit" and POLICY_MODE.is_file():
        return _authorize_http(actor, data)
    if path == "/direct-http-reply" and POLICY_MODE.is_file() and POLICY_MODE.read_text() == CANDIDATE_MODE:
        return _project_http_rejection(actor, data)
    if path == "/begin":
        actor.direct_result = None
        actor.direct_http_reply = None
    elif path == "/direct-result":
        with actor.changed:
            if (not actor.step or not actor.step.claimed or actor.claim.stream
                    or actor.step.native != (data["turn"], data["step"])):
                raise ValueError("缺少同一文本模型步骤")
            actor.direct_result = data
        if data["reason"] == "tool_use":
            frames = data["frames"]
            tool, *arguments = frames
            assert tool["kind"] == "tool" and all(part["kind"] == "input" and part["index"] == tool["index"]
                                                  for part in arguments)
            assert actor.cold_history is not None and tool["name"] in actor.cold_history.tools
            assert isinstance(json.loads("".join(part["json"] for part in arguments)), dict)
            report("native_mod_tool_result", tool_id=tool["id"], fragments=len(arguments), usage=data["usage"])
            # 网关按原合同为对外消息生成新 ID。官方 Mod 在此处已有实际工具 ID 和参数分片。
            init = {"type": "message", "role": "assistant", "model": actor.step.native_model, "usage": data["usage"]}
            parts = [
                {"type": "content_block_start", "index": 0,
                 "content_block": {"type": "tool_use", "id": tool["id"], "name": tool["name"], "input": {}}},
                *({"type": "content_block_delta", "index": 0,
                   "delta": {"type": "input_json_delta", "partial_json": part["json"]}} for part in arguments),
                {"type": "content_block_stop", "index": 0},
            ]
            _deliver(actor, data, init, parts)
            actor.direct_result = None
        return {}
    if path == "/complete" and getattr(actor, "direct_result", None) is not None:
        result = actor.direct_result
        raw = _observe_after_archive(actor, result)
        assert raw["id"] and result["reason"] == "end_turn"
        parts = [
            {"type": "content_block_start", "index": 0, "content_block": raw["content"][0]},
            {"type": "content_block_stop", "index": 0},
        ]
        report("native_archive_response", message_id=raw["id"], usage=result["usage"],
               answer_sha256=sha256(result["answer"].encode()).hexdigest())
        _deliver(actor, result, raw, parts)
    return ORIGINAL_CALLBACK(actor, path, data)


launcher.launch_workspace_cli = launch
session._Callback = Callback
session._Actor.callback = callback

if __name__ == "__main__":
    source.main()
