"""把同一 sender 内的官方交互会话绑定到一次次受权的客户端工具往返。"""

from collections import deque
from contextlib import closing, suppress
from dataclasses import dataclass
import fcntl
import gzip
from hashlib import sha256
from io import BytesIO
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import select
import shutil
import struct
from subprocess import TimeoutExpired
import termios
import time
from threading import Condition, Event, Thread
from urllib.parse import urlsplit
from uuid import uuid4

from tui_capacity import TuiCapacity, TuiCapacityError
from tui_input_policy import CONTEXT_BETA
from tui_messages import (
    BODY_LIMIT,
    ModelResponseError,
    SubagentAmbiguousError,
    SubagentBindingError,
    SubagentCapacityError,
    WireStep,
    history_digest,
    input_message,
    prompt_text,
    provider_session,
    split_reply,
    tool_receipts,
    wire_events,
)

# 与网关的 BINDING_TTL_MS 一致，客户端确认工具时原进程和资源名额仍随会话保留。
_RECEIPT_SECONDS = 60 * 60
# 2.1.293 的后台启动回执与子请求近同时到达，给它一个短的交接窗口。同步父轮本身无法释放名额。
_AGENT_HANDOFF_SECONDS = 2.0
# 只在原工具有效期内留历史配对，耗尽时不再发放后台认领权限。
_BACKGROUND_AGENT_LIMIT = 1024
# 与网关保留的服务端会话命名空间一致，对外自报不能打开子代理私有工作区。
AGENT_SESSION_PREFIX = "gateway-tools-"


@dataclass
class _AgentOffer:
    """记录父工具允许启动的一个子代理。原进程退出后保留有期限的身份和摘要。"""

    parent: "_Actor | None"
    tool_digest: bytes
    prompt: bytes
    until: float
    claimed: str | None = None
    submitted: bool = False
    receipt_received: bool = False
    background_id: str | None = None
    conflicted: bool = False

    def waiting_ancestors(self):
        """枚举因本次同步依赖驻留的进程。@return 尚未收到回执的父链。"""
        offer = self
        while (
            offer
            and offer.parent
            and not offer.receipt_received
            and not offer.parent.retired.is_set()
        ):
            yield offer.parent
            offer = offer.parent.agent_offer


@dataclass(eq=False)
class _Waiting:
    """将等待中的进程身份与它已认领的父工具绑定，供准入与取消共用。"""

    actor_key: tuple
    offer: _AgentOffer | None = None
    exact_receipt_only: bool = False


def _background_agent_id(receipt):
    # 只识别固定 CLI 的成功启动回执；普通 Agent 输出也可能提到 agentId。
    if receipt.get("is_error", False) is not False:
        return None
    content = receipt.get("content")
    prefix = "Async agent launched successfully."
    if isinstance(content, list):
        if not content or any(
            not isinstance(block, dict)
            or block.get("type") != "text"
            or not isinstance(block.get("text"), str)
            for block in content
        ):
            return None
        # 原版 CLI 可以在启动回执后附其他文本；第二份启动声明使同一个工具的身份有歧义。
        if any(block["text"].startswith(prefix) for block in content[1:]):
            return None
        content = content[0]["text"]
    if not isinstance(content, str):
        return None
    heading, _, rest = content.partition("\n")
    if heading.split(" (", 1)[0] != prefix:
        return None
    line = rest.partition("\n")[0]
    agent_id, marker, _ = line.removeprefix("agentId: ").partition(" (internal ID")
    # 容器入口按网关相同的 256 字节边界接收 agent hint。
    if (
        line.startswith("agentId: ")
        and marker
        and len(agent_id) <= 256
        and agent_id.isascii()
        and agent_id.isalnum()
    ):
        return agent_id
    return None


def _agent_prompt(messages):
    # 子代理的首条用户消息原样承载 Agent.prompt。只允许明确文本块与 CLI 提醒块。
    for row in messages:
        if row["role"] == "system":
            continue
        if row["role"] != "user":
            break
        content = row["content"]
        if isinstance(content, str) and content:
            return sha256(content.encode()).digest()
        if isinstance(content, list) and all(
            block["type"] == "text" and isinstance(block.get("text"), str)
            for block in content
        ):
            texts = [block["text"] for block in content]
            # 优先保留完整字符串。仅有一个业务文本时才忽略独立的原生上下文提醒。
            if len(texts) > 1:
                texts = [
                    text
                    for text in texts
                    if not (
                        text.startswith("<system-reminder>\n")
                        and text.rstrip().endswith("</system-reminder>")
                    )
                ]
            if len(texts) == 1 and texts[0]:
                return sha256(texts[0].encode()).digest()
        break
    raise SubagentBindingError("子代理首轮缺少可核对的输入")


def _json(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _install_mod(source, private_dir):
    # copytree(source, private_dir) 会把发行目录的 0755 覆到已核验的会话根目录。
    # 各子目录只来自镜像固定清单，外层 0700 权限始终由账号工作区持有。
    for component in (".claude-plugin", "hooks"):
        shutil.copytree(source / component, private_dir / component, dirs_exist_ok=True)


class _Callback(BaseHTTPRequestHandler):
    """只在当前会话的回环端口接收原版 Mod 回执。"""

    def log_message(self, *_):
        """省略可能包含客户数据的访问日志。@return 无。"""

    def do_POST(self):
        """按会话令牌校验并分发结构化事件。@return 无。"""
        actor = self.server.actor
        model = urlsplit(self.path).path == actor.model_path + "/v1/messages"
        bearer = actor.bearer
        if model:
            bearer = actor.launch_token if actor.model_path else actor.model_bearer
        if not hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + bearer
        ):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= BODY_LIMIT:
                raise ValueError("回调正文长度无效")
            raw = self.rfile.read(length)
            encoding = self.headers.get("Content-Encoding", "identity").lower()
            if encoding == "gzip":
                with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
                    raw = stream.read(BODY_LIMIT + 1)
            if encoding not in ("identity", "gzip") or len(raw) > BODY_LIMIT:
                raise ValueError("回调正文编码无效")
            data = json.loads(raw)
            if model:
                actor.serve_model(self, data)
                return
            payload = _json(actor.callback(self.path, data)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except ModelResponseError as error:
            actor.abort(error)
            with suppress(OSError):
                self.send_response(error.status)
                self.send_header("Content-Type", "application/json")
                if error.retry_after is not None:
                    self.send_header("Retry-After", str(error.retry_after))
                self.send_header("Content-Length", str(len(error.body)))
                self.end_headers()
                self.wfile.write(error.body)
        except (ValueError, KeyError, OSError, RuntimeError):
            actor.abort()
            self.close_connection = True
            if not getattr(self, "model_stream_started", False):
                with suppress(OSError):
                    self.send_error(409)


class _Actor:
    """维护一个真实交互子进程与它的已登记会话。"""

    def __init__(
        self, driver, identity, reservation, settings, prompt, slot, agent_offer=None
    ):
        self.driver = driver
        self.slot = slot
        self.identity = identity
        self.reservation = reservation
        self.agent_offer = agent_offer
        self.agent_offers = {}
        self.completed_normally = False
        self.settings = settings
        self.prompt = prompt
        self.prompt_hash = sha256(prompt.encode()).digest()
        self.marker = "Flower session " + uuid4().hex
        self.bearer = secrets.token_urlsafe(32)
        self.model_bearer = secrets.token_urlsafe(32)
        self.model_path = "/model/" + self.model_bearer if driver.managed_oauth else ""
        self.launch_token = None
        self.guard_text = "Flower2API 会话 " + uuid4().hex
        self.changed = Condition()
        self.ready = Event()
        self.dead = Event()
        self.retired = Event()
        self.failure = None
        self.master = None
        self.process = None
        self.step = None
        self.frame_batch = []
        self.finished = False
        self.history = None
        self.expected = None
        self.wait_until = None
        self.answers = {}
        self.delivered = set()
        self.claim = None
        self.port = None
        self.worker = None

    def abort(self, failure=None):
        """立即唤醒全部等待者；监护线程负责回收进程。@return 无。"""
        with self.changed:
            if self.failure is None and failure is not None:
                self.failure = failure
            self.dead.set()
            self.changed.notify_all()

    def start(self, command):
        """由专属监护线程创建 PTY、Mod 与原版子进程。@param command 已认领的启动指令。@return 无。"""
        self.worker = Thread(target=self._monitor, args=(command,), daemon=True)
        try:
            self.worker.start()
        except BaseException:
            # 未启动的线程没有 finally 来归还名额，交由预留的 close 同步收回。
            self.worker = None
            self.abort()
            raise

    def _monitor(self, command):
        master, slave = None, None
        try:
            home, mod = self.driver.launcher.session_paths(command)
            server = ThreadingHTTPServer(("127.0.0.1", 0), _Callback)
            with closing(server):
                server.actor = self
                self.port = server.server_address[1]
                endpoint = "http://127.0.0.1:" + str(self.port)
                version = Path(__file__).resolve().with_name("tui-mod")
                # 原版进程只能读取自己的 mod 根目录。启动前只复制镜像内的固定程序。
                plugin = mod
                _install_mod(version, plugin)
                try:
                    (plugin / "hooks/binding.js").write_text(
                        f"export const endpoint = {_json(endpoint)}\nexport const bearer = {_json(self.bearer)}\n"
                    )
                    # 第二层拒绝用于 Mod 未能截获工具的情况，客户端从不触达服务器工具。
                    classic = {
                        "hooks": {
                            "PreToolUse": [
                                {
                                    "hooks": [
                                        {
                                            "type": "command",
                                            "command": 'printf \'%s\\n\' \'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
                                            '"permissionDecision":"deny","permissionDecisionReason":"工具由客户端执行"}}\'',
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                    opts = [
                        "--name",
                        "Flower2API V2",
                        "--model",
                        self.settings["model"],
                        "--strict-mcp-config",
                        "--permission-mode",
                        "dontAsk",
                        "--setting-sources",
                        "",
                        "--disable-slash-commands",
                        "--settings",
                        _json(classic),
                        "--tools",
                        "",
                        "--plugin-dir",
                        str(plugin),
                    ]
                    master, slave = os.openpty()
                    self.master = master
                    fcntl.ioctl(
                        slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 100, 0, 0)
                    )
                    if self.dead.is_set():
                        raise RuntimeError("原预留已经取消")
                    budget = self.settings.get("max_tokens")
                    env = (
                        {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(budget)}
                        if type(budget) is int and budget > 0
                        else {}
                    )
                    if self.settings.get("thinking", {}).get("type") == "disabled":
                        env["MAX_THINKING_TOKENS"] = "0"
                    self.process = self.driver.launcher.launch_session(
                        self.reservation,
                        command,
                        arguments=opts,
                        config_dir=home / ".claude",
                        environment=env,
                        resume=None,
                        terminal_fd=slave,
                        mod_dir=plugin,
                        model_endpoint=(endpoint + self.model_path, self.launch_token or self.model_bearer),
                    )
                    os.close(slave)
                    slave = None
                    callback = Thread(
                        target=server.serve_forever,
                        kwargs={"poll_interval": 0.05},
                        daemon=True,
                    )
                    callback.start()
                    try:
                        seen, tail, submitted = False, b"", False
                        while not self.dead.is_set() and self.process.poll() is None:
                            with self.changed:
                                if (
                                    self.wait_until is not None
                                    and time.monotonic() >= self.wait_until
                                ):
                                    break
                            if select.select([master], [], [], 0.1)[0]:
                                data = os.read(master, 65536)
                                if not data:
                                    break
                                seen |= "❯".encode() in tail + data
                                tail = data[-4:]
                            if (
                                seen
                                and self.ready.is_set()
                                and not submitted
                                and not self.dead.is_set()
                            ):
                                # 成员内容经 prompt.submit 传送；控制字符和斜杠始终不会写进 PTY。
                                os.write(master, self.marker.encode())
                                if not self.dead.wait(0.18):
                                    os.write(master, b"\r")
                                submitted = True
                    finally:
                        self.abort()
                        server.shutdown()
                        callback.join()
                finally:
                    if self.process is not None:
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=1)
                        except TimeoutExpired:
                            self.process.kill()
                            self.process.wait()
                    (plugin / "hooks/binding.js").unlink(missing_ok=True)
        except Exception:
            # 任何启动、归属或终端错误都会由等待中的发送者以中断报告；不记录客户正文。
            self.abort()
        finally:
            for fd in (master, slave):
                if fd is not None:
                    os.close(fd)
            self.abort()
            self.driver._retire(self)

    def callback(self, path, data):
        """按回合次序接受 Mod 事件并施加背压。@param path 回调类型。@param data 官方事件。@return 回执。"""
        with self.changed:
            if self.dead.is_set():
                raise ValueError("进程已取消")
            if path == "/ready":
                self.ready.set()
            elif (
                path == "/prompt"
                and self.prompt is not None
                and data.get("marker") == self.marker
            ):
                prompt, self.prompt = self.prompt, None
                return {"prompt": prompt, "guard": self.guard_text}
            elif path == "/results":
                ids = data["ids"]
                if (
                    not ids
                    or self.step is None
                    or not all(isinstance(i, str) for i in ids)
                    or len(set(ids)) != len(ids)
                ):
                    raise ValueError("原生工具归属无效")
                declared = {
                    b["id"]
                    for b in (self.expected or self.step.blocks)
                    if b["type"] == "tool_use"
                }
                requested = set(ids)
                delivered = self.delivered
                if not requested <= declared or requested & delivered:
                    raise ValueError("原生工具未在该轮登记")
                if not self.changed.wait_for(
                    lambda: (
                        self.dead.is_set()
                        or delivered is not self.delivered
                        or requested <= self.answers.keys()
                    ),
                    _RECEIPT_SECONDS,
                ):
                    raise ValueError("已超过会话工具绑定有效期")
                if self.dead.is_set():
                    raise ValueError("原生工具已取消")
                # 等待释放过锁；另一回调可能已领取回执，或原轮已经结束。
                if delivered is not self.delivered or requested & delivered:
                    raise ValueError("原生工具回执已交付或已换轮")
                delivered.update(requested)
                return {"results": [self.answers[i] for i in ids]}
            elif path == "/begin":
                if self.step is None or self.claim is None or self.dead.is_set():
                    raise ValueError("缺少已提交的有效预留")
                if set(self.answers) != self.delivered:
                    raise ValueError("原工具尚未接到全部回执")
                if (
                    self.step.native is not None
                    or not isinstance(data.get("turn"), str)
                    or type(data.get("step")) is not int
                ):
                    raise ValueError("原生步骤已认领或缺少原始步骤标识")
                self.step.native = (data["turn"], data["step"])
                self.step.native_model = data.get("model")
                self.expected = None
                self.wait_until = None
            elif path == "/end":
                if (
                    self.step is None
                    or self.step.native != (data.get("turn"), data.get("step"))
                    or self.finished
                    or not self.step.stopped
                    or self.step.reason != data.get("reason")
                ):
                    raise ValueError("原版 CLI 未确认相同模型响应的终态")
                if (
                    not self.changed.wait_for(
                        lambda: self.dead.is_set() or self.step.final is not None, 120
                    )
                    or self.dead.is_set()
                ):
                    raise ValueError("模型响应未完整结束")
                self.step.terminal_seen = True
                # 2.1.293 确认模型拒答后会尝试开启下一步。原响应已完整结束，此时即可交付。
                if self.step.reason in ("tool_use", "refusal"):
                    self._finish_step()
            elif path == "/complete" and self.step is not None:
                if (
                    not self.step.terminal_seen
                    or self.step.native[0] != data.get("turn")
                    or data.get("aborted") is not False
                    or self.step.reason == "tool_use"
                ):
                    raise ValueError("原版 TUI 未正常结束本个会话轮次")
                if self.step.reason != "refusal":
                    self._finish_step()
            else:
                raise ValueError("非法原生步骤状态")
        return {}

    def _finish_step(self):
        self._publish(self.step.final)
        self.finished = True
        self.expected = self.step.blocks if self.step.reason == "tool_use" else None
        if self.expected:
            self.wait_until = time.monotonic() + _RECEIPT_SECONDS
            self.agent_offers = {}
            for block in self.expected:
                if block["type"] != "tool_use" or block["name"] not in (
                    "Agent",
                    "Task",
                ):
                    continue
                arguments = block.get("input")
                prompt = (
                    arguments.get("prompt") if isinstance(arguments, dict) else None
                )
                if isinstance(prompt, str) and prompt:
                    self.agent_offers[block["id"]] = _AgentOffer(
                        self,
                        sha256(block["id"].encode()).digest(),
                        sha256(prompt.encode()).digest(),
                        self.wait_until,
                    )
        self.changed.notify_all()

    def _publish(self, batch):
        # 调用方持有同一 Condition；最多缓存一个尚未被公开连接消费的 SSE 事件。
        if (
            not self.changed.wait_for(
                lambda: self.dead.is_set() or not self.frame_batch, 120
            )
            or self.dead.is_set()
        ):
            raise RuntimeError("公开输出已中断")
        self.frame_batch = batch
        self.changed.notify_all()

    def _main_request(self, body, handle):
        if (
            not isinstance(body, dict)
            or body.get("stream") is not True
            or self.step is None
            or body.get("model") != self.step.native_model
        ):
            return False
        rows = body.get("messages")
        if not isinstance(rows, list) or not rows or not isinstance(rows[-1], dict):
            return False
        content = rows[-1].get("content")
        if not isinstance(content, list):
            return False
        if handle.kind == "continuation":
            _, results = split_reply(rows)
            ids = [b.get("tool_use_id") for b in results]
            return (
                bool(ids)
                and set(ids) == self.delivered == set(handle.answers)
                and len(ids) == len(self.delivered)
            )
        # 2.1.293 按模型生成两种原生布局。只检查最近用户输入及紧随的系统行；
        # 旧会话历史、引述标记的标题和调用方提供的文本都不能单独消费本次许可。
        last_user = next(
            (
                i
                for i in range(len(rows) - 1, -1, -1)
                if isinstance(rows[i], dict) and rows[i].get("role") == "user"
            ),
            None,
        )
        if last_user is None:
            return False
        content = rows[last_user].get("content")
        line = "prompt.submit hook additional context: " + self.guard_text
        if isinstance(content, list):
            marker = "<system-reminder>\n" + line + "\n</system-reminder>"
            return (
                sum(
                    1
                    for block in content
                    if isinstance(block, dict)
                    and block.get("type") == "text"
                    and block.get("text") in (marker, marker + "\n")
                )
                == 1
            )
        # DeepSeek 的真实主轮保留纯字符串用户行，把 hook context 收入其后的原生系统块。
        # 校验完整用户文本和独立随机标记行，避免在系统摘要中搜到历史提示就认领。
        if (
            not isinstance(content, str)
            or sha256(content.encode()).digest() != self.prompt_hash
        ):
            return False
        tail = rows[last_user + 1 :]
        if not tail or any(
            not isinstance(r, dict)
            or r.get("role") != "system"
            or not isinstance(r.get("content"), list)
            for r in tail
        ):
            return False
        return (
            sum(
                block["text"].split("\n").count(line)
                for row in tail
                for block in row["content"]
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
            )
            == 1
        )

    def serve_model(self, http, native):
        """一轮原生模型 POST 开启一次冻结的本机请求。@param http 当前 TUI 的模型连接。
        @param native 原生 CLI 请求，仅用于核对已开放的主步骤。@return 无。
        """
        with self.driver.lock, self.changed:
            step, handle = self.step, self.claim
            pending = not (
                self.dead.is_set()
                or step is None
                or handle is None
                or step.native is None
                or step.claimed
                or not self._main_request(native, handle)
            )
            if pending:
                if (
                    handle.kind == "new"
                    and self.agent_offer is not None
                    and not self.driver._valid_agent(
                        self.agent_offer, self.identity[-1]
                    )
                ):
                    # sender 已允许启动终端时，父工具仍可能拒绝。提交模型前再核对一次。
                    raise SubagentBindingError("子代理的原工具已拒绝或取消")
                step.claimed = True
                raw, handle.raw = handle.raw, None
                account_token = handle.account_token
                # 原回执已用于核对此次模型提交。此后出现的工具属于这次响应；
                # 在原版终端看到它们之前换一份交付记录，避免它读到上一轮同名 ID 的旧结果。
                self.answers = {}
                self.delivered = set()
                self.changed.notify_all()
        if not pending:
            http.send_error(409, "No pending model step")
            return
        # 原进程的回环鉴权与本次上游 AT 独立，换代后仍可把工具交给原进程。
        headers = handle.model_headers
        if handle.api_context is not None:
            offered = {v.strip() for v in http.headers.get("anthropic-beta", "").split(",")}
            thinking = handle.thinking if handle.thinking is not None else native.get("thinking", {})
            clears = any(edit["type"] == "clear_thinking_20251015" for edit in handle.api_context.get("edits", []))
            if CONTEXT_BETA not in offered or (clears and thinking.get("type") not in ("enabled", "adaptive")):
                raise ModelResponseError(422, _json({"error": {"type": "invalid_request_error",
                    "code": "unsupported_parameter", "message": "本轮 CLI 不支持请求的历史管理策略"}}))
            if clears and handle.thinking is None:
                # 只有清理思考且客户端省略 thinking 时，复用同一原版步骤实际启用的配置。
                raw = _json({**json.loads(raw), "thinking": thinking}).encode()
            beta = headers.get("anthropic-beta", "")
            if CONTEXT_BETA not in {v.strip() for v in beta.split(",")}:
                headers = {**headers, "anthropic-beta": ",".join(filter(None, (beta, CONTEXT_BETA)))}
        raw, headers = provider_session(
            raw, headers, self.identity[4], handle.upstream_session_id,
        )
        options = {"headers": headers}
        if getattr(handle, "capture", None) is not None:
            options["capture"] = handle.capture
        if self.driver.managed_oauth:
            if account_token is None:
                raise ModelResponseError(503, b"")
            # CLI 原生请求的授权头只认证回环连接，实际模型发送取当前认领的账号 AT。
            options["headers"] = {
                **headers,
                **{name: http.headers[name] for name in ("user-agent", "x-app", "anthropic-beta")
                   if name not in headers and http.headers.get(name)},
            }
            model_response = self.driver.launcher.managed_model_response(
                raw, account_token=account_token, reservation=handle.reservation, **options
            )
        else:
            model_response = self.driver.launcher.local_model_response(raw, **options)
        with model_response as upstream:
            if upstream.status != 200:
                raw_error = upstream.read(BODY_LIMIT + 1)
                raise ModelResponseError(
                    upstream.status, raw_error if len(raw_error) <= BODY_LIMIT else b""
                )
            if (
                upstream.getheader("Content-Type", "").split(";")[0].strip()
                != "text/event-stream"
            ):
                raise RuntimeError("受管本机提供方没有交付成功的 Messages 事件流")
            http.model_stream_started = True
            http.send_response(200)
            http.send_header("Content-Type", "text/event-stream")
            http.send_header("Connection", "close")
            http.end_headers()
            http.close_connection = True
            tail = bytearray()
            for wire, event in wire_events(upstream):
                with self.changed:
                    if self.dead.is_set():
                        raise RuntimeError("模型轮已取消")
                    if event and event.get("type") == "error":
                        # 上游已建立 SSE 时保留其原始 error 记录，不能伪造正常 message_stop。
                        self._publish([wire])
                        self.finished = True
                        self.expected = None
                        self.changed.notify_all()
                        http.wfile.write(wire)
                        http.wfile.flush()
                        return
                    step.observe(event)
                    if step.stopped:
                        if len(tail) + len(wire) > BODY_LIMIT:
                            raise ValueError("模型终态后的数据超限")
                        tail.extend(wire)
                    else:
                        self._publish([wire])
                http.wfile.write(wire)
                http.wfile.flush()
            with self.changed:
                if not step.stopped or not tail:
                    raise ValueError("模型事件在终态之前结束")
                step.final = [bytes(tail)]
                self.changed.notify_all()

    def events(self, handle, command):
        """本轮原生事件的迭代器。@param handle 认领。@param command 发送指令。@return SSE 分帧。"""
        with self.changed:
            if self.claim is not handle or self.dead.is_set():
                raise RuntimeError("交互会话已失效")
            self.finished = False
            self.step = WireStep(handle.tools)
            self.history = handle.history
            self.answers = handle.answers
            self.wait_until = None
            self.changed.notify_all()
            if handle.kind == "new":
                self.launch_token = handle.account_token
                self.start(command)
        while True:
            with self.changed:
                if not self.changed.wait_for(
                    lambda: self.frame_batch or self.dead.is_set() or self.finished, 120
                ):
                    raise RuntimeError("原生事件流长时间无响应")
                if self.dead.is_set() and not self.frame_batch:
                    raise self.failure or RuntimeError("原生事件流已中断")
                batch, self.frame_batch = self.frame_batch, []
                finished = self.finished
                self.changed.notify_all()
            yield from batch
            if finished:
                handle.completed = True
                return


class _Reserved:
    """账号内只准单次提交的交互预留。"""

    def __init__(self, actor, kind, history, answers, body, stream, raw, reservation):
        self.actor = actor
        self.kind = kind
        self.history = history
        self.answers = answers
        self.tools = body.get("tools", [])
        self.stream = stream
        self.raw = raw
        self.model_headers = dict(reservation.get("model_headers") or {})
        self.upstream_session_id = None
        self.reservation = reservation
        self.account_token = None
        # 原生请求已声明完整的协议上下文。普通 API 的历史管理需要本次实际 CLI 提供能力。
        self.api_context = body.get("context_management") if "metadata" not in body else None
        self.thinking = body.get("thinking")
        self.sent = self.completed = False

    def send(self, command):
        """实际启动或恢复一个模型步骤。@param command 已核验工作区。@return 逐帧输出。"""
        actor = self.actor
        with actor.driver.lock, actor.changed:
            if self.sent or actor.dead.is_set():
                raise ValueError("原预留已提交或已取消")
            if self.kind == "new" and actor.agent_offer is not None:
                if not actor.driver._valid_agent(actor.agent_offer, actor.identity[-1]):
                    raise SubagentBindingError("子代理所属原轮已结束或取消")
                actor.agent_offer.submitted = True
            self.upstream_session_id = command.get("upstream_session_id")
            self.account_token = command.pop("account_token", None)
            self.sent = True
            actor.driver._acknowledge_agents(actor, self.answers)
        return self.actor.events(self, command)

    def close(self):
        """取消未提交预留，或在终态归还原进程。@return 无。"""
        actor = self.actor
        with actor.changed:
            self.account_token = None
            if actor.claim is not self:
                return
            actor.claim = None
            if self.sent and (not self.completed or not actor.expected):
                step = actor.step
                actor.completed_normally = (
                    self.completed
                    and step is not None
                    and step.stopped
                    and bool(step.final)
                )
                actor.abort()
            if not self.sent and self.kind == "new":
                actor.abort()
            actor.changed.notify_all()
        if actor.dead.is_set() and actor.worker is None:
            actor.driver._retire(actor)


class SessionDriver:
    """绑定当前账号的真实 TUI 会话。@param config 受信预留配置。@param launcher 原版账号启动器。"""

    def __init__(self, config, launcher=None, capacity=None):
        """创建该账号的进程表。@param config 源配置。@param launcher 注入的受信启动器。@return 无。"""
        if launcher is None:
            import tui_sender_launch as launcher
        self.launcher = launcher
        self.managed_oauth = getattr(launcher, "managed_oauth_enabled", lambda: False)()
        # 编排每个 HTTP 并发配置两个预留。等待新 TUI 的队列必须留下至少一个传输名额还工具。
        limit = max(1, config["max_reservations"] // 2)
        if capacity is None:
            memory = Path("/sys/fs/cgroup/memory.max").read_text().strip()
            # 1GiB 账号实测同时持有三个 TUI。预留 256MiB 基础开销及每进程 256MiB。
            reserve = 256 * 1024**2
            budget = (
                (limit + 1) * reserve
                if memory == "max"
                else int(memory)
                if memory.isdecimal()
                else 0
            )
            # 暂停等 Agent 的父进程继续记入 RAM；只多规划一个经验证的子进程。
            # 无 cgroup 硬预算时沿用旧的保守预算，由物理容量本身裁掉余量。
            capacity = TuiCapacity(
                limit + 1,
                budget_bytes=budget,
                fixed_reserve_bytes=reserve,
                per_process_reserve_bytes=reserve,
                max_waiters=config["max_reservations"] - 1,
            )
        self.capacity = capacity
        self.ordinary_limit = limit
        self.lock = Condition()
        self.waiters = deque()
        self.max_waiters = config["max_reservations"] - 1
        self.sessions = {}
        self.background_agents = {}
        self.closed = False

    def ready(self):
        """检查账号受权启动能力。@return 已装配、获准且可以分配原版进程。"""
        try:
            return (
                not self.closed
                and self.capacity.snapshot().limit > 0
                and self.launcher.account_ready()
            )
        except (ValueError, OSError):
            return False

    def idle(self):
        """查看账号有无仍等候客户端的原生进程。@return 是否完全空闲。"""
        with self.lock:
            return not self.sessions

    def receipt_idle(self, identity):
        """检查原轮和它的子进程。@param identity 已认证的原账号、代次、主体与会话。@return 原轮是否已退出。"""
        with self.lock:
            # 同一客户端会话的 Agent 可比父进程活得更久，须等待原会话的全部相关进程。
            return not (any(key[:5] == identity for key in self.sessions)
                        or any(waiter.actor_key[:5] == identity for waiter in self.waiters))

    def _retire(self, actor):
        with self.lock:
            if self.sessions.get(actor.identity) is actor:
                del self.sessions[actor.identity]
                actor.slot.release_after_close()
                if actor.agent_offer is not None and not actor.agent_offer.submitted:
                    actor.agent_offer.claimed = None
                if not actor.completed_normally:
                    for child in self.sessions.values():
                        if (
                            child.agent_offer is not None
                            and child.agent_offer.parent is actor
                        ):
                            child.abort()
                for offer in self.background_agents.values():
                    if offer.parent is actor:
                        if not actor.completed_normally:
                            offer.conflicted = True
                        offer.parent = None
                # 已退场祖先只需留下寿命标记，活动子进程无需持有更早的完整依赖链。
                actor.agent_offers.clear()
                actor.agent_offer = None
            actor.retired.set()
            self.lock.notify_all()

    def _prune_background(self):
        now = time.monotonic()
        for key in [
            key for key, offer in self.background_agents.items() if now >= offer.until
        ]:
            del self.background_agents[key]

    def _acknowledge_agents(self, actor, answers):
        self._prune_background()
        for tool_id in answers.keys() & actor.agent_offers.keys():
            offer = actor.agent_offers[tool_id]
            if offer.receipt_received:
                continue
            offer.receipt_received = True
            hint = _background_agent_id(answers[tool_id])
            if hint is None:
                # 工具回执本身只结束父等待；失败或普通前台结果不能授予后台启动。
                continue
            offer.background_id = hint
            key = (*actor.identity[:5], hint)
            prior = self.background_agents.get(key)
            if prior is not None and prior is not offer:
                # 重复标识不能覆盖原工具，且要保留冲突记录直至双方都过期。
                prior.until = max(prior.until, offer.until)
                prior.conflicted = offer.conflicted = True
            elif (
                prior is not None
                or len(self.background_agents) < _BACKGROUND_AGENT_LIMIT
            ):
                self.background_agents[key] = offer
        self.lock.notify_all()

    def _claim_agent(self, identity, hint, prompt, *, exact_receipt_only):
        self._prune_background()
        matched = self.background_agents.get((*identity, hint))
        if matched is not None:
            if (
                matched.prompt != prompt
                or matched.claimed is not None
                or matched.conflicted
            ):
                raise SubagentBindingError("子代理与已登记的后台启动回执不符")
            matched.claimed = hint
            return matched
        if exact_receipt_only:
            return None
        matching = []
        for actor in self.sessions.values():
            if actor.identity[:5] != identity or actor.dead.is_set():
                continue
            with actor.changed:
                matching.extend(
                    offer
                    for offer in actor.agent_offers.values()
                    if not offer.receipt_received and offer.prompt == prompt
                )
        if len(matching) > 1:
            return None
        if not matching or matching[0].claimed is not None:
            raise SubagentBindingError("子代理需要同一会话中唯一待交接的 Agent 工具")
        (offer,) = matching
        offer.claimed = hint
        return offer

    @staticmethod
    def _valid_agent(offer, hint):
        if offer.conflicted or time.monotonic() >= offer.until:
            return False
        parent = offer.parent
        if offer.receipt_received:
            return (
                offer.background_id is not None
                and offer.background_id == hint
                and (
                    parent is None
                    or not parent.dead.is_set()
                    or parent.completed_normally
                )
            )
        return parent is not None and not parent.dead.is_set()

    def _eligible(self, ticket, ordinary_room):
        key, offer = ticket.actor_key, ticket.offer
        # 子身份本身没有额外容量。只有仍在原父进程上等待的依赖可以借驻留位。
        return (
            key not in self.sessions
            and (len(key) == 5 or offer is not None)
            and (ordinary_room or offer is not None and any(offer.waiting_ancestors()))
        )

    def _blocked_dependency(self, ticket):
        # 多棵树也可能合占所有物理位；每个等待子轮单独计算自身深度会漏掉这种互等。
        candidates = list(self.waiters)
        if ticket not in candidates:
            candidates.append(ticket)
        parents = set()
        for candidate in candidates:
            offer = candidate.offer
            if offer is not None:
                parents.update(offer.waiting_ancestors())
        return all(actor in parents for actor in self.sessions.values())

    def prepare(self, reservation, raw, *, cancel_event=None):
        """只预留身份和物理容量，收到 send 才启动。@param reservation 身份。@param raw 正文。
        @param cancel_event 准备连接断开信号。@return 可单次提交的预留。
        """
        body, stream, frozen = input_message(
            raw, native=reservation.get("input_format"), session_id=reservation["session_id"],
            body_policy=reservation.get("body_policy"),
        )
        # 在认领工具回执之前检查退避期，等待结束后客户端仍能将回执交还原进程。
        check_wait = getattr(self.launcher, "check_provider_backoff", None)
        if check_wait is not None:
            check_wait()
        messages = body["messages"]
        history = history_digest(messages)
        identity = tuple(
            reservation[key]
            for key in (
                "account_id",
                "environment_id",
                "generation",
                "principal_id",
                "session_id",
            )
        )
        agent_hint = reservation.get("agent_hint")
        actor_key = identity if agent_hint is None else (*identity, agent_hint)
        returned = split_reply(messages)[1]
        deadline = reservation["deadline_unix_ms"] / 1000

        def remaining():
            result = deadline - time.time()
            if result <= 0 or cancel_event is not None and cancel_event.is_set():
                raise TimeoutError("原版会话预留已取消或到期")
            return result

        if returned or reservation["continuation_only"]:
            with self.lock:
                actor = self.sessions.get(actor_key)
            if actor is None or not returned:
                raise ValueError("缺少工具结果所属的原会话")
            with actor.changed:
                # 对外终帧可稍早于上一传输线程归还句柄。只等本次已经确认完成的交接。
                prior = actor.claim
                while (
                    actor.claim is not None
                    and actor.claim is prior
                    and actor.finished
                    and not actor.dead.is_set()
                ):
                    actor.changed.wait(min(remaining(), 0.05))
                if (
                    actor.dead.is_set()
                    or actor.expected is None
                    or actor.claim is not None
                ):
                    raise ValueError("原会话未准备接收该工具结果")
                answers = tool_receipts(messages, actor.history, actor.expected)
                handle = _Reserved(
                    actor,
                    "continuation",
                    history,
                    answers,
                    body,
                    stream,
                    frozen,
                    reservation,
                )
                actor.claim = handle
                return handle

        prompt = prompt_text(messages)
        with self.lock:
            if agent_hint is not None and (
                actor_key in self.sessions
                or any(item.actor_key == actor_key for item in self.waiters)
            ):
                raise SubagentBindingError("此子代理已持有独立进程，工具回执须返回原轮")
            child_prompt = _agent_prompt(messages) if agent_hint is not None else None
            offer = None
            ticket = _Waiting(actor_key)
            handoff_limit = time.monotonic() + _AGENT_HANDOFF_SECONDS
            try:
                while True:
                    if self.closed:
                        raise RuntimeError("当前账号事件源已关闭")
                    timeout = remaining()
                    capacity = self.capacity.snapshot()
                    if agent_hint is not None and offer is None:
                        # 两个相同提示在收到启动回执前无法区分，挂起握手而不占进程。
                        offer = ticket.offer = self._claim_agent(
                            identity,
                            agent_hint,
                            child_prompt,
                            exact_receipt_only=ticket.exact_receipt_only,
                        )
                        if offer is None:
                            # 先前已观察到歧义；另一个工具退场也不能证明本请求属于幸存工具。
                            ticket.exact_receipt_only = True
                            left = handoff_limit - time.monotonic()
                            if left <= 0:
                                raise SubagentAmbiguousError(
                                    "同提示子代理在交接期内缺少唯一启动回执"
                                )
                            timeout = min(timeout, left)
                    if offer is not None:
                        if not self._valid_agent(offer, agent_hint):
                            raise SubagentBindingError("子代理所属原轮已结束或取消")
                        if (
                            capacity.in_use >= capacity.limit
                            and self._blocked_dependency(ticket)
                        ):
                            left = handoff_limit - time.monotonic()
                            if left <= 0:
                                raise SubagentCapacityError(
                                    "同步子代理所在父链已占满物理容量"
                                )
                            timeout = min(timeout, left)
                        # 回执状态在原 actor 锁下推进，短轮询避免反向持有两个锁。
                        timeout = min(timeout, 0.05)
                    if capacity.limit == 0:
                        raise TimeoutError("当前账号没有可用的交互进程额度")
                    ordinary_room = capacity.in_use < self.ordinary_limit
                    first = next(
                        (
                            item
                            for item in self.waiters
                            if self._eligible(item, ordinary_room)
                        ),
                        None,
                    )
                    if (
                        capacity.in_use < capacity.limit
                        and self._eligible(ticket, ordinary_room)
                        and first in (None, ticket)
                    ):
                        slot = self.capacity.acquire(
                            timeout=0, cancel_event=cancel_event
                        )
                        actor_reservation = (
                            reservation
                            if offer is None
                            else {
                                **reservation,
                                "session_id": AGENT_SESSION_PREFIX + str(uuid4()),
                            }
                        )
                        actor = _Actor(
                            self,
                            actor_key,
                            actor_reservation,
                            {
                                k: body[k]
                                for k in ("model", "max_tokens", "thinking")
                                if k in body
                            },
                            prompt,
                            slot,
                            offer,
                        )
                        self.sessions[actor_key] = actor
                        handle = _Reserved(
                            actor,
                            "new",
                            history,
                            {},
                            body,
                            stream,
                            frozen,
                            reservation,
                        )
                        actor.claim = handle
                        return handle
                    if ticket not in self.waiters:
                        # 源端与 sender 都给一个可信子依赖留下有界位置。
                        # 已占满普通队列时，合法子轮仍可等下一次物理释放。
                        reserved = any(len(item.actor_key) > 5 for item in self.waiters)
                        if len(self.waiters) - int(reserved) >= self.max_waiters and (
                            reserved or agent_hint is None
                        ):
                            raise TimeoutError("交互等待队列已满")
                        self.waiters.append(ticket)
                    self.lock.wait(
                        min(timeout, 0.05) if cancel_event is not None else timeout
                    )
            except TuiCapacityError as error:
                raise TimeoutError("交互进程名额或等待期限已耗尽") from error
            finally:
                if (
                    offer is not None
                    and actor_key not in self.sessions
                    and not offer.submitted
                ):
                    offer.claimed = None
                if ticket in self.waiters:
                    self.waiters.remove(ticket)
                    self.lock.notify_all()

    def close(self):
        """取消本账号所有会话，等到子进程确实退出。@return 无。"""
        with self.lock:
            self.closed = True
            self.background_agents.clear()
            actors = list(self.sessions.values())
            self.lock.notify_all()
        for actor in actors:
            actor.abort()
        for actor in actors:
            if actor.worker:
                actor.worker.join()
            else:
                self._retire(actor)
