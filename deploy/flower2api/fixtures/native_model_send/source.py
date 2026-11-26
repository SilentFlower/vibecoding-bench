"""仅回环验收用的账号事件源。合成 HTTPS 模型与 Mod 共用原会话获准的监听端口。"""

from contextlib import suppress
import gzip
from hashlib import sha256
import hmac
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
from os import readlink
from secrets import token_hex
from shutil import copyfile
from socket import MSG_PEEK, SHUT_WR, if_nameindex, socketpair
from ssl import PROTOCOL_TLS_SERVER, SSLContext, SSLSocket
import sys
from threading import Event, Thread
from time import monotonic, monotonic_ns, sleep, time_ns
from urllib.parse import urlsplit

sys.path.insert(0, "/opt/flower/tui")
import tui_sender_launch
import tui_session
from tui_messages import BODY_LIMIT
from tui_source_impl import IO_TIMEOUT, main

FIXTURE = Path("/verify-native")
_OUTPUT = Path("/native/native-observations.jsonl")


def record(**facts):
    """落盘合成观测，不包含帐号凭据或对话正文。@param facts 本次计数或摘要。@return 无。"""
    with _OUTPUT.open("a") as output:
        print(
            json.dumps({"ns": monotonic_ns(), **facts}, ensure_ascii=False), file=output
        )


def cli_owns_peer(connection, pid):
    """核对服务器看到的 TLS 对端套接字属于本轮 CLI。
    @param connection 实际 TLS 连接。@param pid 受管进程。@return 文件描述符是否匹配。
    """
    peer = f"0100007F:{connection.getpeername()[1]:04X}"
    local = f"0100007F:{connection.getsockname()[1]:04X}"
    sockets = {
        "socket:[" + row[9] + "]"
        for line in Path("/proc/net/tcp").read_text().splitlines()[1:]
        if (row := line.split())[1:4] == [peer, local, "01"]
    }
    for fd in Path(f"/proc/{pid}/fd").iterdir():
        try:
            if readlink(fd) in sockets:
                return True
        except FileNotFoundError:
            continue
    return False


def chunks(body, label, *, title=None):
    """生成便签或标题回复。@param body 实收正文。@param label 本轮编号。@param title 可选测试标题。@return 原始 SSE 帧。"""
    prior = body["messages"][-1].get("content")
    results = (
        [b for b in prior if b.get("type") == "tool_result"]
        if isinstance(prior, list)
        else []
    )
    if results:
        assert len(results) == 1 and results[0]["tool_use_id"] == "toolu_candidate"
        assert "NOTE_OK" in str(results[0]["content"])
    first = not results and title is None
    message = {
        "id": "msg_" + label,
        "type": "message",
        "role": "assistant",
        "model": body["model"],
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 7 if title is None else 3, "output_tokens": 0},
    }
    block = (
        {"type": "tool_use", "id": "toolu_candidate", "name": "ReadNote", "input": {}}
        if first
        else {"type": "text", "text": ""}
    )
    delta = (
        [
            {"type": "input_json_delta", "partial_json": '{"key":'},
            {"type": "input_json_delta", "partial_json": '"note"}'},
        ]
        if first
        else [{"type": "text_delta", "text": title or "收到测试便签。"}]
    )
    events = [
        {"type": "message_start", "message": message},
        {"type": "content_block_start", "index": 0, "content_block": block},
        *[{"type": "content_block_delta", "index": 0, "delta": d} for d in delta],
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {
                "stop_reason": "tool_use" if first else "end_turn",
                "stop_sequence": None,
            },
            "usage": {"output_tokens": 5 if title is None else 2},
        },
        {"type": "message_stop"},
    ]
    return [
        b"event: "
        + e["type"].encode()
        + b"\ndata: "
        + json.dumps(e, ensure_ascii=False).encode()
        + b"\n\n"
        for e in events
    ]


class Trial:
    """仅存在于本轮合成模型请求的观测状态。"""

    def __init__(self, actor, submission):
        """绑定已认领的正文与 actor。@param actor 受管会话。@param submission 已认领输入。@return 无。"""
        self.id = token_hex(16)
        self.actor, self.submission = actor, submission
        self.used = False
        self.done = Event()
        self.writer, self.reader = socketpair()
        self.writer.settimeout(IO_TIMEOUT)
        self.failure = None
        self.expected_digest = None
        self.independent_model = False

    def consume(self):
        """复用正式事件处理与背压，核对经过 CLI 的事件与 TLS 模型写出的字节。@return 无。"""
        digest = sha256()
        try:
            with self.reader, self.reader.makefile("rb") as source:
                for wire in self.actor._model_events(self.submission.step, source):
                    digest.update(wire)
            observed = digest.hexdigest()
            if not self.independent_model and observed != self.expected_digest:
                raise ValueError("同一回复的字节摘要不同")
            record(completed=self.id, sse_sha256=observed)
        except (OSError, ValueError, RuntimeError) as error:
            self.failure = type(error).__name__
            self.actor.abort()
        finally:
            self.done.set()
            with suppress(OSError):
                self.writer.shutdown(SHUT_WR)
            self.writer.close()


def offer(actor, http, submission):
    """向内层交付一次获准的模型消息。@param actor 本轮会话。@param http 回环请求。
    @param submission 正式账号入口已认领的输入。@return 无。
    """
    if not actor.oauth_file or not submission.account_token:
        raise ValueError("此验收要求正式完整凭据模式")
    # 本机合成服务只认验收器刚生成的账号，即使被误装到其他回环账号也拒绝其真实凭据。
    if not hmac.compare_digest(
        sha256(submission.account_token.encode()).hexdigest(),
        (FIXTURE / "synthetic-at.sha256").read_text(),
    ):
        raise ValueError("该账号不属于这次合成模型验收")
    trial = Trial(actor, submission)
    with actor.changed:
        if (
            getattr(actor, "native_trial", None)
            and not actor.native_trial.done.is_set()
        ):
            raise RuntimeError("上次实验流仍在消费")
        actor.native_trial = trial
    grant = {
        "id": trial.id,
        "body": submission.body.decode(),
        "headers": submission.headers,
    }
    route = getattr(actor.driver, "model_proxy_fixture", None)
    if route is not None:
        route.prepare_main(trial, grant)
    if (FIXTURE / "probe-account-proxy").is_file():
        proxy = json.loads(Path("/run/v3/sender.json").read_bytes())["proxy_url"]
        address = urlsplit(proxy)
        if (
            address.scheme != "http"
            or address.hostname != "127.0.0.1"
            or not address.port
            or address.username
        ):
            raise ValueError("此探测仅接受无凭据的隔离回环代理")
        grant["probeProxy"] = proxy
    payload = json.dumps(grant, ensure_ascii=False).encode()
    http.send_response(200)
    http.send_header("Content-Type", "application/vnd.flower.native-lab+json")
    http.send_header("Content-Length", str(len(payload)))
    http.end_headers()
    http.wfile.write(payload)
    submission.record_cli_handoff()


class DualProtocol(ThreadingHTTPServer):
    """在原会话私有监听器内处理本地合成模型 TLS，外部地址不参加实验。"""

    def finish_request(self, request, client_address):
        """依据接收的协议派往本机模型或已有回调。@param request 本机连接。@param client_address 对端。@return 无。"""
        request.settimeout(IO_TIMEOUT)
        if request.recv(1, MSG_PEEK) != b"\x16":
            return super().finish_request(request, client_address)
        context = SSLContext(PROTOCOL_TLS_SERVER)
        context.load_cert_chain(FIXTURE / "localhost.crt", FIXTURE / "localhost.key")
        with context.wrap_socket(request, server_side=True) as tls:
            super().finish_request(tls, client_address)


class Callback(tui_session._Callback):
    """验收用 HTTPS 模型及单次响应观察，两者分别核对凭据与实体。"""

    def send_error(self, code, message=None, explain=None):
        """独立见证重复请求的服务端状态。@param code 状态。@param message 原因。@param explain 明细。@return 无。"""
        if code == 409 and self.headers.get("x-native-lab-repeat") == "1":
            record(repeated_seed_rejected=True)
        if self.command == "CONNECT" and self.path == "model-probe.invalid:443":
            actor = self.server.actor
            record(
                session_proxy_status=code,
                cli_pid=actor.process.pid,
                cli_peer=cli_owns_peer(self.connection, actor.process.pid),
            )
        return super().send_error(code, message, explain)

    def do_POST(self):
        """在原会话许可下记录模型收包与返回流。@return 无。"""
        path = urlsplit(self.path).path
        if not path.startswith("/native-lab/"):
            if isinstance(self.connection, SSLSocket):
                return self.send_error(404)
            return super().do_POST()
        actor = self.server.actor
        trial = getattr(actor, "native_trial", None)
        fields = path.split("/", 3)
        if (
            not trial
            or len(fields) != 4
            or not hmac.compare_digest(fields[2], trial.id)
            or actor.dead.is_set()
            or actor.claim is not trial.submission.handle
        ):
            return self.send_error(403)
        action = fields[3]
        model = action == "v1/messages"
        token = trial.submission.account_token if model else actor.bearer
        if (
            isinstance(self.connection, SSLSocket) != model
            or self.headers.get("Authorization") != "Bearer " + token
        ):
            return self.send_error(403)
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 <= size <= BODY_LIMIT:
            return self.send_error(413)
        content = self.rfile.read(size)
        if len(content) != size:
            return self.send_error(400)
        if model:
            with actor.changed:
                if trial.used:
                    return self.send_error(409)
                trial.used = True
            if self.headers.get("Content-Encoding") == "gzip":
                with gzip.GzipFile(fileobj=BytesIO(content)) as gz:
                    content = gz.read(BODY_LIMIT + 1)
            if content != trial.submission.body:
                return self.send_error(422)
            handle = trial.submission.handle
            now = time_ns() // 1_000_000
            if (
                not handle.expires_at
                or handle.expires_at <= now
                or handle.reservation["deadline_unix_ms"] <= now
            ):
                return self.send_error(403)
            body = json.loads(content)
            cancel_trial = body["messages"][0].get("content") == "在半截参数处取消本轮"
            frames = chunks(body, trial.id)
            trial.expected_digest = sha256(b"".join(frames)).hexdigest()
            owner = cli_owns_peer(self.connection, actor.process.pid)
            if not owner:
                raise RuntimeError("HTTPS 对端不属于当前 CLI 进程")
            record(
                received=trial.id,
                cli_peer=owner,
                cli_pid=actor.process.pid,
                private_port=self.server.server_port,
                tls=self.connection.version(),
                names=[k for k, v in self.headers.raw_items()],
                model_bytes=len(content),
                cancel_trial=cancel_trial,
                sha256=sha256(content).hexdigest(),
                body_equal=True,
                language=self.headers.get("Accept-Language"),
                cache=self.headers.get("Cache-Control"),
            )
            Thread(target=trial.consume, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            if not cancel_trial:
                self.send_header("Content-Length", str(sum(map(len, frames))))
            self.end_headers()
            for index, frame in enumerate(frames):
                self.wfile.write(frame)
                self.wfile.flush()
                if index == 2 and cancel_trial:
                    until = monotonic() + 30
                    reason = "actor_cancelled"
                    try:
                        # 周期性发送 SSE 注释，让传输层观察客户端关闭后的实际写结果。
                        while not actor.dead.wait(0.1):
                            if monotonic() >= until:
                                raise TimeoutError("候选内部模型流在断开后仍未回收")
                            self.wfile.write(b": waiting\n\n")
                            self.wfile.flush()
                    except OSError:
                        reason = "peer_disconnected"
                    record(canceled_model=trial.id, stop_reason=reason)
                    return
                if index == 2 and len(frames) == 7:
                    until = monotonic() + 30
                    while not Path("/native/client-saw-partial").exists():
                        if monotonic() >= until:
                            raise TimeoutError("客户端未收到半截工具参数")
                        sleep(0.02)
            return
        if action == "proxy-check" and (FIXTURE / "probe-account-proxy").is_file():
            errors = json.loads(content)
            if set(errors) != {"session", "account"} or not all(
                isinstance(v, str)
                and v.isascii()
                and v.replace("_", "").isalnum()
                and len(v) <= 64
                for v in errors.values()
            ):
                return self.send_error(400)
            record(
                proxy_attempt=errors,
                cli_pid=actor.process.pid,
                cli_peer=cli_owns_peer(self.connection, actor.process.pid),
            )
        elif action == "bytes" and trial.used and not trial.done.is_set():
            trial.writer.sendall(content)
        elif action == "end" and trial.used:
            with suppress(OSError):
                trial.writer.shutdown(SHUT_WR)
            if not trial.done.wait(IO_TIMEOUT) or trial.failure:
                return self.send_error(409)
        elif action == "abort":
            with suppress(OSError):
                trial.writer.shutdown(SHUT_WR)
            trial.writer.close()
            actor.abort()
        else:
            return self.send_error(409)
        self.send_response(204)
        self.end_headers()


def start():
    """启动只含回环接口的真实账号事件源。@return 事件源的退出状态。"""
    if [name for _, name in if_nameindex()] != ["lo"]:
        raise RuntimeError("合成模型验收必须使用独立的仅回环网络空间")
    original = tui_sender_launch.launch_workspace_cli
    original_abort = tui_session._Actor.abort
    route = None
    if (FIXTURE / "managed-proxy.json").is_file():
        sys.path.insert(0, str(FIXTURE))
        from managed_route import ManagedRoute

        route = ManagedRoute(FIXTURE, cli_owns_peer, record)
        route.install(tui_session, Callback)

    def abort(actor, failure=None):
        original_abort(actor, failure)
        trial = getattr(actor, "native_trial", None)
        if trial is not None and not trial.done.is_set():
            with suppress(OSError):
                trial.writer.shutdown(SHUT_WR)
            trial.writer.close()
            if not trial.used:
                trial.reader.close()
                trial.done.set()

    tui_session._Actor.abort = abort

    def launch(reservation, command, **kwargs):
        # 只为本候选镜像的受信实验预加载模块授予原 Mod 的同等可读范围。
        mod = Path(kwargs["arguments"][kwargs["arguments"].index("--plugin-dir") + 1])
        copyfile(FIXTURE / "preload.mjs", mod / "hooks/native.mjs")
        copyfile(
            FIXTURE / ("model.crt" if route else "localhost.crt"), mod / "hooks/ca.crt"
        )
        if route:
            route.prepare_cli(kwargs, mod, reservation["session_id"])
        kwargs["environment"].update(
            BUN_OPTIONS="--preload " + str(mod / "hooks/native.mjs"),
            NODE_EXTRA_CA_CERTS=str(mod / "hooks/ca.crt"),
        )
        return original(reservation, command, **kwargs)

    tui_sender_launch.launch_workspace_cli = launch
    if route is None:
        tui_session.ThreadingHTTPServer = DualProtocol
        tui_session._Callback = Callback

    def create_driver(config):
        driver = tui_session.SessionDriver(config, native_dispatch=offer)
        driver.cli_handoff_capture = True
        driver.model_proxy_fixture = route
        return driver

    return main(create_driver)


if __name__ == "__main__":
    sys.exit(start())
