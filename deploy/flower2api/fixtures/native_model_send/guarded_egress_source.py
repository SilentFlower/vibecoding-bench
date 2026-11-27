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
from threading import Lock, local
from time import monotonic, monotonic_ns, sleep, time_ns
from urllib.parse import urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import frozen_tui_source as source
import tui_sender_launch as launcher
import tui_session as session
from runtime_files import atomic_text
from tui_input_policy import _IDENTITIES
from tui_workspace_launch import publish_workspace_history

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
ORIGINAL_MONITOR = session._Actor._monitor
POLICY_MODE = Path("/opt/flower/tui/fixture-direct-permit")
INSTALLED_PROBE = Path("/opt/flower/tui/fixture-installed-direct")
PERMITS = Path("/tmp/flower-direct-permits.jsonl")
TUNNELS = Path("/tmp/flower-direct-tunnels.jsonl")
CANDIDATE_MODE = "candidate-response"
STOCK_TOOLS = {"Read", "Glob"}
MANAGED_BINDING_LOCK = Lock()
managed_process = None
launch_context = local()


def report(stage, **data):
    """输出一次隔离试接的非敏感证据。@return 无。"""
    print(json.dumps({"event": stage, **data}), file=sys.stderr, flush=True)


def _monitor(actor, command):
    launch_context.actor = actor
    try:
        return ORIGINAL_MONITOR(actor, command)
    finally:
        del launch_context.actor


def _stock_root(config, work, native_id):
    # 原版入站只有当前用户轮时没有已确认历史。保留已占用原 UUID 的档案并按原绑定选新分支。
    return publish_workspace_history(config, work, native_id, lambda _: False, None,
                                     boundary=sha256(b"[]").hexdigest())


def _stock_arguments(arguments, mod, options):
    actor = launch_context.actor
    handle = actor.claim
    if handle.reservation.get("input_format") != "claude_code" or actor.cold_history is not None:
        return arguments
    body = json.loads(handle.raw)
    tools = [tool["name"] for tool in handle.tools]
    if not set(tools) <= STOCK_TOOLS:
        raise ValueError("内置隔离候选只验证外部文本、Read 和 Glob")
    system = body["system"]
    # 账单字段与运行时身份由实际发送的 CLI 自己生成。余下的系统文本经官方文件参数交给同一 CLI。
    if system[0]["text"].startswith("x-anthropic-billing-header:"):
        system = system[1:]
    (identity, *instructions) = system
    if identity["text"] not in _IDENTITIES or any(block.keys() != {"type", "text"} for block in instructions):
        raise ValueError("外部系统提示超出内置隔离候选范围")
    selected = arguments.copy()
    selected[selected.index("--tools") + 1] = ",".join(tools)
    if instructions:
        path = mod / "external-instructions.md"
        atomic_text(path, "\n".join(block["text"] for block in instructions))
        selected.extend(["--system-prompt-snapshot", "off", "--system-prompt-file", str(path)])
    if len(body["messages"]) == 1 and body["messages"][0]["role"] == "user":
        options.update(resume=False, prepare_history=_stock_root)
    report("direct_stock_launch", reservation_id=handle.reservation["reservation_id"], tools=tools,
           instruction_blocks=len(instructions))
    return selected


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
    global managed_process
    if POLICY_MODE.is_file():
        arguments = options["arguments"]
        mod = Path(arguments[arguments.index("--plugin-dir") + 1])
        managed = Path("/opt/flower-http-test/flower-http-policy/hooks/runtime/binding.js")
        with MANAGED_BINDING_LOCK:
            # 隔离受管 Mod 同时只为一个 CLI 授权。进程退出后恢复轮才可发布自己的回环绑定。
            if managed_process is not None and managed_process.poll() is None:
                raise RuntimeError("隔离受管绑定仍归活跃 CLI")
            try:
                atomic_text(managed, (mod / "hooks/binding.js").read_text())
                if INSTALLED_PROBE.is_file():
                    options["arguments"] = _stock_arguments(arguments, mod, options)
            except OSError as error:
                report("direct_permit_launch_failed", error=type(error).__name__, errno=error.errno,
                       uid=getuid(), gid=getgid())
                raise
            managed_process = ORIGINAL_LAUNCH(*args, environment=settings, **options)
            return managed_process
    return ORIGINAL_LAUNCH(*args, environment=settings, **options)


def _valid_attempt(actor, step, handle):
    mode = POLICY_MODE.read_text() if POLICY_MODE.is_file() else None
    probe_sse = handle and (mode == CANDIDATE_MODE or (not handle.tools and mode == "observe-sse"))
    return (step and step.native and handle and actor.process and not actor.dead.is_set()
            and (INSTALLED_PROBE.is_file() or len(handle.tools) <= 1) and (not handle.stream or probe_sse) and actor.oauth_file
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
            # 模型等待期间同一 TLS 隧道可暂时没有数据。以会话生命周期收回连接。
            while not actor.dead.is_set():
                ready, _, _ = select(list(streams), [], [], 1)
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
    wire = b"".join(map(_frame, events))
    for _ in actor._model_events(actor.step, BytesIO(wire)):
        pass
    ORIGINAL_CALLBACK(actor, "/end", result)


def _frame(event):
    return ("event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n").encode()


def _public_tool_name(actor, part):
    name = part["name"]
    if actor.cold_history is not None:
        return actor.cold_history.tools[name]["name"]
    if (not INSTALLED_PROBE.is_file() or name not in STOCK_TOOLS
            or name not in {tool["name"] for tool in actor.claim.tools}):
        raise ValueError("工具不属于本次已声明的隔离调用")
    return name


class _LiveProjection:
    """按官方事件交付文本、签名思考和客户端工具组，沿原步骤发布最终帧。"""

    def __init__(self, actor):
        """构造同一实际步骤的公开开场。@param actor 原会话。@return 无。"""
        self.actor = actor
        self.step = actor.step
        self.next_index = 0
        self.text_indices = {}
        self.text_digest = sha256()
        self.tools = {}
        self.closed = set()
        self._emit({"type": "message_start", "message": {
            "id": "msg_" + uuid4().hex, "role": "assistant", "type": "message", "model": self.step.native_model,
            "content": [], "stop_reason": None, "stop_sequence": None,
            # 受支持的增量未给出供应商开场用量。终态用同一步实际累计值交付。
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }})

    def _emit(self, event):
        self.actor._observe(self.step, event)
        with self.actor.changed:
            self.actor._publish([_frame(event)])

    def _start(self, block):
        index = self.next_index
        self.next_index += 1
        self._emit({"type": "content_block_start", "index": index, "content_block": block})
        return index

    def add(self, chunk):
        """发布实际文本、工具参数分片或已追加的签名块。@param chunk 官方事件。@return 无。"""
        if chunk["kind"] == "signed":
            for block in chunk["blocks"]:
                if block["type"] == "thinking":
                    index = self._start({"type": "thinking", "thinking": "", "signature": ""})
                    if block["thinking"]:
                        self._emit({"type": "content_block_delta", "index": index,
                                    "delta": {"type": "thinking_delta", "thinking": block["thinking"]}})
                    self._emit({"type": "content_block_delta", "index": index,
                                "delta": {"type": "signature_delta", "signature": block["signature"]}})
                else:
                    index = self._start({"type": "redacted_thinking", "data": block["data"]})
                self._emit({"type": "content_block_stop", "index": index})
                self.closed.add(index)
            return
        kind, native_index = chunk["kind"], chunk["index"]
        if kind == "tool":
            if native_index in self.tools:
                raise ValueError("同一原生工具索引重复开始")
            name = _public_tool_name(self.actor, chunk)
            index = self._start({"type": "tool_use", "id": chunk["id"], "name": name, "input": {}})
            self.tools[native_index] = (index, chunk["id"], sha256())
            return
        if kind == "text":
            if native_index not in self.text_indices:
                self.text_indices[native_index] = self._start({"type": "text", "text": ""})
            index, digest = self.text_indices[native_index], self.text_digest
            text = chunk["text"]
            delta = {"type": "text_delta", "text": text}
        else:
            # 官方工具分片带原生索引。多个工具同时打开时仍只更新各自的公开块。
            index, _, digest = self.tools[native_index]
            text = chunk["json"]
            delta = {"type": "input_json_delta", "partial_json": text}
        digest.update(text.encode())
        self._emit({"type": "content_block_delta", "index": index, "delta": delta})

    def finish(self, result):
        """确认交付内容及累计用量，再让原终态回调收口。@param result 官方步骤结果。@return 无。"""
        if result["reason"] != ("tool_use" if self.tools else "end_turn"):
            raise ValueError("流式内容与同一步的结束原因不符")
        # 工具轮的终态 answer 按显示需要在独立文本块之间插入换行。逐块交付使用原生索引和实际分片。
        if not self.tools and self.text_digest.digest() != sha256(result["answer"].encode()).digest():
            raise ValueError("公开增量与官方步骤完整结果不符")
        completed_tools = {}
        for part in result["frames"]:
            if part["kind"] == "tool":
                completed_tools[part["index"]] = (part["id"], sha256())
            else:
                completed_tools[part["index"]][1].update(part["json"].encode())
        if {index: (identifier, digest.digest()) for index, (_, identifier, digest) in self.tools.items()} != {
            index: (identifier, digest.digest()) for index, (identifier, digest) in completed_tools.items()
        }:
            raise ValueError("公开工具组与官方步骤完整结果不符")
        if self.closed:
            # 签名来源使用官方步骤汇报的实际响应模型。开场用于展示的请求模型可能与它不同。
            self.step.response_model = result["usage"].get("model")
        for index in range(self.next_index):
            if index not in self.closed:
                self._emit({"type": "content_block_stop", "index": index})
        self._emit({"type": "message_delta", "delta": {"stop_reason": result["reason"], "stop_sequence": None},
                    "usage": result["usage"]})
        terminal = {"type": "message_stop"}
        self.actor._observe(self.step, terminal)
        with self.actor.changed:
            self.step.final = [_frame(terminal)]
        ORIGINAL_CALLBACK(self.actor, "/end", result)


def _direct_chunk(actor, data):
    with actor.changed:
        step, handle = actor.step, actor.claim
        if (not step or not handle or not step.claimed or step.stopped
                or step.native != (data["turn"], data["step"])):
            raise ValueError("流式增量不属于当前模型步骤")
    chunk = data["chunk"]
    if actor.direct_stream is None:
        actor.direct_stream = _LiveProjection(actor)
    actor.direct_stream.add(chunk)
    return {}


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
    """将同一受信 Mod 步骤交给公开响应及原工具登记。@return 原协议回执。"""
    if path == "/direct-http-permit" and POLICY_MODE.is_file():
        return _authorize_http(actor, data)
    if path == "/direct-http-reply" and POLICY_MODE.is_file() and POLICY_MODE.read_text() == CANDIDATE_MODE:
        return _project_http_rejection(actor, data)
    if path == "/begin":
        actor.direct_result = None
        actor.direct_http_reply = None
        actor.direct_stream = None
    elif path == "/direct-chunk" and INSTALLED_PROBE.is_file():
        return _direct_chunk(actor, data)
    elif path == "/direct-result":
        buffered_stream = POLICY_MODE.is_file() and POLICY_MODE.read_text() == CANDIDATE_MODE
        with actor.changed:
            if (not actor.step or not actor.step.claimed or (actor.claim.stream and not buffered_stream)
                    or actor.step.native != (data["turn"], data["step"])):
                raise ValueError("缺少同一文本模型步骤")
            actor.direct_result = data
        if data["reason"] == "tool_use":
            if actor.direct_stream is not None:
                actor.direct_stream.finish(data)
                actor.direct_result = None
                return {}
            frames = data["frames"]
            tool, *arguments = frames
            assert tool["kind"] == "tool" and all(part["kind"] == "input" and part["index"] == tool["index"]
                                                  for part in arguments)
            _public_tool_name(actor, tool)
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
        text, = raw["content"]
        parts = [
            {"type": "content_block_start", "index": 0, "content_block": {**text, "text": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text["text"]}},
            {"type": "content_block_stop", "index": 0},
        ]
        report("native_archive_response", message_id=raw["id"], usage=result["usage"],
               answer_sha256=sha256(result["answer"].encode()).hexdigest())
        if actor.direct_stream is not None:
            actor.direct_stream.finish(result)
        else:
            _deliver(actor, result, raw, parts)
    return ORIGINAL_CALLBACK(actor, path, data)


launcher.launch_workspace_cli = launch
session._Callback = Callback
session._Actor.callback = callback
if INSTALLED_PROBE.is_file():
    session._Actor._monitor = _monitor

if __name__ == "__main__":
    source.main()
