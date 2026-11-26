"""把同一 sender 内的官方交互会话绑定到一次次受权的客户端工具往返。"""

from base64 import b64decode
from collections import Counter, deque
from contextlib import ExitStack, closing, suppress
from dataclasses import dataclass, field
import fcntl
from functools import partial
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
from tempfile import TemporaryDirectory
import termios
import time
from threading import Condition, Event, Thread
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from runtime_files import atomic_text
from tui_capacity import TuiCapacity, TuiCapacityError
from tui_cold_history import ColdHistory, MCP_SERVER, SIGNED_THINKING_TYPES
from tui_reconnect import ReceiptCheckpoints, digest
from tui_input_policy import CONTEXT_BETA, InputRejection, native_input
from tui_messages import (
    BODY_LIMIT,
    MessageInputObservation,
    MODEL_PROTOCOL_HEADERS,
    ModelResponseError,
    SubagentAmbiguousError,
    SubagentBindingError,
    SubagentCapacityError,
    WireStep,
    history_digest,
    input_message,
    passive_quota_headers,
    prompt_text,
    receipt_snapshot,
    provider_session,
    split_reply,
    tool_receipts,
    valid_model_header_value,
    wire_events,
)
from tui_workspace_launch import WorkspaceLaunchObservation

# 与网关的 BINDING_TTL_MS 一致，客户端确认工具时原进程和资源名额仍随会话保留。
_RECEIPT_SECONDS = 60 * 60
# CC 2.1.293 的单次 Mod HTTP 调用在 30 秒中止，留出响应和调度余量。
_RECEIPT_POLL_SECONDS = 20
# 同步父链占满物理进程时，给在途回执留出短暂释放机会。后台配对使用原请求期限。
_AGENT_HANDOFF_SECONDS = 2.0
# 只在原工具有效期内留历史配对，耗尽时不再发放后台认领权限。
_BACKGROUND_AGENT_LIMIT = 1024
# 与网关保留的服务端会话命名空间一致，对外自报不能打开子代理私有工作区。
AGENT_SESSION_PREFIX = "gateway-tools-"
TITLE_SESSION_PREFIX = AGENT_SESSION_PREFIX + "title-"
SUGGESTION_SESSION_PREFIX = AGENT_SESSION_PREFIX + "suggestion-"


@dataclass
class _AgentOffer:
    """记录父工具允许启动的一个子代理。原进程退出后保留有期限的身份和摘要。"""

    parent: "_Actor | None"
    group: object
    tool_digest: bytes
    prompt: bytes
    until: float
    claimed: str | None = None
    submitted: bool = False
    receipt_received: bool = False
    background_id: str | None = None
    conflicted: bool = False
    asynchronous: bool = False
    messages: Counter = field(default_factory=Counter)

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
    agent_summary: bool = False
    recovering: bool = False
    exact_receipt_only: bool = False
    groups: frozenset | None = None


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
            return content, Counter()
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
            if texts and texts[0]:
                extras = Counter()
                prefix = "The coordinator sent a message while you were working:\n"
                suffix = "\n\nAddress this before completing your current task."
                for text in texts[1:]:
                    if not text.startswith(prefix) or not text.endswith(suffix):
                        raise SubagentBindingError("追加消息缺少原生定向投递标记")
                    extras[sha256(text[len(prefix):-len(suffix)].encode()).digest()] += 1
                return texts[0], extras
        break
    raise SubagentBindingError("子代理首轮缺少可核对的输入")


def _json(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _install_mod(source, private_dir):
    # copytree(source, private_dir) 会把发行目录的 0755 覆到已核验的会话根目录。
    # 各子目录只来自镜像固定清单，外层 0700 权限始终由账号工作区持有。
    for component in (".claude-plugin", "hooks"):
        shutil.copytree(source / component, private_dir / component, dirs_exist_ok=True)


@dataclass(frozen=True)
class _ModelSubmission:
    """一次已认领的模型步骤。正文、账号凭据和头仅在账号服务内持有。"""

    step: WireStep
    handle: "_Reserved"
    body: bytes = field(repr=False)
    headers: dict = field(repr=False)
    account_token: str | None = field(repr=False)

    def record_cli_handoff(self):
        """原生适配器确认交付后，向本次调试采集交回实际正文与协议选项。@return 无。"""
        capture = getattr(self.handle, "capture", None)
        if capture is not None:
            capture.append((list(self.headers.items()), self.body))


class _StaleReceipt(ValueError):
    """迟到或重复的私有查询，只结束本次查询。"""


class _Callback(BaseHTTPRequestHandler):
    """只在当前会话的回环端口接收原版 Mod 回执。"""

    def log_message(self, *_):
        """省略可能包含客户数据的访问日志。@return 无。"""

    def do_CONNECT(self):
        """终止官方子进程发起的外部代理连接。@return 无。"""
        self.send_error(403)

    def do_GET(self):
        """声明 MCP 使用单次 JSON 应答。@return 无。"""
        self.send_error(405)

    def do_POST(self):
        """按会话令牌校验并分发结构化事件。@return 无。"""
        target = urlsplit(self.path)
        if target.scheme or target.netloc:
            self.send_error(403)
            return
        actor = self.server.actor
        mcp = target.path == "/mcp" and actor.cold_history is not None
        model = target.path == actor.model_path + "/v1/messages"
        bearer = actor.model_authorization() if model else actor.bearer
        authorization = self.headers.get("Authorization", "")
        if bearer is None or not authorization.isascii() or not hmac.compare_digest(
            authorization, "Bearer " + bearer
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
                actor.serve_model(self, data, native_raw=raw)
                return
            reply = actor.cold_history.mcp(data) if mcp else actor.callback(self.path, data)
            if reply is None:
                self.send_response(202)
                self.end_headers()
                return
            payload = _json(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            if mcp and data.get("method") == "tools/list":
                actor.mcp_ready.set()
        except _StaleReceipt:
            with suppress(OSError):
                self.send_error(409)
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
        self.agent_messages = Counter()
        self.agent_offers = {}
        self.completed_normally = False
        self.settings = settings
        self.prompt = prompt
        self.prompt_hash = sha256(prompt.encode()).digest()
        self.marker = "Flower session " + uuid4().hex
        self.media_paths: tuple[str, ...] = ()
        self.bearer = secrets.token_urlsafe(32)
        self.model_bearer = secrets.token_urlsafe(32)
        self.model_path = "/model/" + self.model_bearer if driver.managed_oauth else ""
        self.launch_token = None
        self.oauth_file = False
        self.credential_dir = None
        self.guard_text = "Flower2API 会话 " + uuid4().hex
        self.changed = Condition()
        self.ready = Event()
        self.mcp_ready = Event()
        self.dead = Event()
        self.retired = Event()
        self.failure = None
        self.master = None
        self.process = None
        self.launch_observation = WorkspaceLaunchObservation()
        self.step = None
        self.frame_batch = []
        self.finished = False
        self.history = None
        self.expected = None
        self.receipt_revision = None
        self.wait_until = None
        self.answers = {}
        self.delivered = set()
        self.receipt_key = secrets.token_bytes(32)
        self.claim = None
        self.port = None
        self.worker = None
        self.cold_history = None
        self.recovery_history = None
        self.signed_tool_models = {}

    def model_authorization(self):
        """读取当前模型回环的账号授权。@return 当前回合 AT 或原会话口令。"""
        with self.changed:
            if self.oauth_file:
                return self.claim.account_token if self.claim is not None else None
            return self.launch_token if self.model_path else self.model_bearer

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

    def _stage_current_images(self, home, resources):
        sources = [block["source"] for block in self.cold_history.current_blocks if block["type"] == "image"]
        if not sources:
            return None
        # 原生文件粘贴会附带来源。使用本进程内的目录别名，模型不会收到账号私有目录路径。
        folder = Path(resources.enter_context(TemporaryDirectory(prefix="images-", dir=home / "tmp")))
        descriptor = os.open(folder, os.O_PATH | os.O_DIRECTORY)
        resources.callback(os.close, descriptor)
        aliases = []
        for index, source in enumerate(sources, 1):
            name = f"attachment-{index}.{source['media_type'].split('/')[1]}"
            with os.fdopen(os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
                stream.write(b64decode(source["data"], validate=True))
            aliases.append(f"/proc/self/fd/{descriptor}/{name}")
        self.media_paths = tuple(aliases)
        return descriptor

    def _terminal_marker(self):
        return "".join(f"[Image #{index}] " for index in range(1, len(self.media_paths) + 1)) + self.marker

    def _monitor(self, command):
        master, slave = None, None
        try:
            home, mod = self.driver.launcher.session_paths(command)
            server = ThreadingHTTPServer(("127.0.0.1", 0), _Callback)
            with closing(server), ExitStack() as history_resources:
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
                    plan = self.cold_history
                    if plan is not None and (plan.thinking or {}).get("display") == "summarized":
                        classic["showThinkingSummaries"] = True
                    opts = [
                        # 同一预留会话的显示名稳定。传成单个参数，兼容以连字符开头的合法会话 ID。
                        f"--name={self.reservation['session_id']}",
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
                    launch_options = {}
                    resume = None
                    wait_for_mcp = False
                    if plan is not None:
                        # 本轮设置来自当前账号，恢复时也应按当前轮构造系统正文。
                        opts.extend(["--system-prompt-snapshot", "off"])
                        if system_prompt := plan.system_argument():
                            flag, text = system_prompt
                            instructions = plugin / "instructions.md"
                            atomic_text(instructions, text)
                            opts.extend([flag, str(instructions)])
                        if plan.effort:
                            opts.extend(["--effort", plan.effort])
                        if plan.tools:
                            wait_for_mcp = True
                            mcp = plugin / "mcp.json"
                            atomic_text(mcp, _json({"mcpServers": {MCP_SERVER: {
                                "type": "http", "url": endpoint + "/mcp", "headers": {
                                    "Authorization": "Bearer " + self.bearer,
                                },
                            }}}))
                            opts.extend(["--mcp-config", str(mcp)])
                        launch_plan = self.recovery_history or plan
                        launch_options["prepare_history"] = launch_plan.import_session
                        if self.recovery_history is None:
                            launch_options["prepare_history"] = partial(
                                launch_plan.import_session, replay_resources=history_resources,
                                observation=self.launch_observation,
                            )
                            if (media := self._stage_current_images(home, history_resources)) is not None:
                                launch_options["media_fd"] = media
                        resume = bool(launch_plan.history)
                    elif self.receipt_revision is not None:
                        launch_options["recover_incomplete_history"] = True
                    master, slave = os.openpty()
                    self.master = master
                    # 纯图文提交先显示附件标记。让当前编号留在固定 CLI 的提示行可视范围内。
                    columns = min(0xffff, max(100, len(self._terminal_marker()) + 4))
                    fcntl.ioctl(
                        slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, columns, 0, 0)
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
                    if self.cold_history is not None and self.cold_history.has_history_cache_markers():
                        # CLI 的自动断点会与客户前缀同时出现，还可能改变 TTL 顺序。
                        env["DISABLE_PROMPT_CACHING"] = "1"
                    self.process = self.driver.launcher.launch_session(
                        self.reservation,
                        command,
                        arguments=opts,
                        config_dir=home / ".claude",
                        environment=env,
                        resume=resume,
                        terminal_fd=slave,
                        mod_dir=plugin,
                        model_endpoint=(endpoint + self.model_path, self.launch_token or self.model_bearer),
                        observation=self.launch_observation,
                        **({"oauth_file": True} if self.oauth_file else {}),
                        **launch_options,
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
                        media_index, waiting_for_image = 0, b""
                        while not self.dead.is_set() and self.process.poll() is None:
                            with self.changed:
                                if self.claim and self.claim.disconnected and self.claim.disconnected.is_set():
                                    # 网关已释放这次私有发送。空闲模型也随监护循环退出。
                                    break
                                if (
                                    self.wait_until is not None
                                    and time.monotonic() >= self.wait_until
                                ):
                                    break
                            if select.select([master], [], [], 0.1)[0]:
                                data = os.read(master, 65536)
                                if not data:
                                    break
                                screen = tail + data
                                seen |= "❯".encode() in screen
                                if waiting_for_image and waiting_for_image in screen:
                                    waiting_for_image = b""
                                tail = screen[-max(4, len(waiting_for_image)):]
                            if (
                                seen
                                and self.ready.is_set()
                                and (not wait_for_mcp or self.mcp_ready.is_set())
                                and not submitted
                                and not self.dead.is_set()
                                and not waiting_for_image
                            ):
                                if media_index:
                                    os.write(master, b" ")
                                if media_index < len(self.media_paths):
                                    path = self.media_paths[media_index].encode()
                                    os.write(master, b"\x1b[200~" + path + b"\x1b[201~")
                                    media_index += 1
                                    # CLI 用光标定位显示标记中的空格。等实际渲染出编号再贴下一张。
                                    waiting_for_image = f"#{media_index}]".encode()
                                    tail = b""
                                    continue
                                # 客户正文交给 Mod。PTY 只接收服务端生成的标记和附件别名。
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
                    if self.cold_history is not None:
                        (plugin / "mcp.json").unlink(missing_ok=True)
                        (plugin / "instructions.md").unlink(missing_ok=True)
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
                and data.get("marker") == self._terminal_marker()
            ):
                prompt, self.prompt = self.prompt, None
                if self.cold_history is not None and self.cold_history.current_blocks and self.recovery_history is None:
                    blocks = self.cold_history.submitted_blocks()
                    if self.media_paths:
                        # 内容块中的图像由实际 PTY 粘贴提供。回调只描述它们在图文中的位置。
                        blocks = [{"type": "image"} if block["type"] == "image" else block for block in blocks]
                    return {"prompt": data["marker"], "guard": self.guard_text, "blocks": blocks,
                            "media": bool(self.media_paths)}
                return {"prompt": prompt, "guard": self.guard_text}
            elif path == "/results":
                return self._tool_results(data)
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

    def _tool_results(self, data):
        """在持有 actor 条件锁时等待本步工具。@param data 私有查询。@return 原始回执或下次查询编号。"""
        ids = data.get("ids")
        if (not isinstance(ids, list) or not ids or self.step is None
                or not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids)):
            raise _StaleReceipt("原生工具归属无效")
        requested = set(ids)
        declared = {b["id"] for b in (self.expected or self.step.blocks) if b["type"] == "tool_use"}
        delivered = self.delivered
        if not requested <= declared or requested & delivered:
            raise _StaleReceipt("原生工具未在该轮登记或已经交付")
        # 编号绑定此 actor 的模型步骤及工具子集；轮询次数不会增加驻留记录。
        ticket = hmac.new(self.receipt_key, _json(sorted(ids)).encode(), sha256).hexdigest()
        if "ticket" in data and data["ticket"] != ticket:
            raise _StaleReceipt("工具等待编号已失效")
        timeout = _RECEIPT_POLL_SECONDS
        if self.wait_until is not None:
            remaining = self.wait_until - time.monotonic()
            if remaining <= 0:
                raise _StaleReceipt("已超过会话工具绑定有效期")
            timeout = min(timeout, remaining)
        if not self.changed.wait_for(
            lambda: self.dead.is_set() or delivered is not self.delivered or requested <= self.answers.keys(),
            timeout,
        ):
            if self.wait_until is not None and time.monotonic() >= self.wait_until:
                raise _StaleReceipt("已超过会话工具绑定有效期")
            return {"pending": ticket}
        if self.dead.is_set() or delivered is not self.delivered or requested & delivered:
            raise _StaleReceipt("原生工具回执已取消、已交付或已换轮")
        delivered.update(requested)
        return {"results": [self.answers[i] for i in ids]}

    def _observe(self, step, event):
        with self.changed:
            if self.dead.is_set():
                raise RuntimeError("原工具步骤已退出")
            if (event and event.get("type") == "content_block_start"
                    and event.get("content_block", {}).get("type") in ("tool_use", "server_tool_use")):
                # 新指令可能随下一帧到达客户端，从此不能再派发产生它的旧步骤。
                self.driver.checkpoints.new_tool(self.identity, self.receipt_revision)
            block = step.observe(event)
        if self.reservation.get("agent_summary"):
            # 进度回复只交给辅助请求，模型输出不能创建业务工具派工。
            return
        if block is None or block["type"] != "tool_use" or block["name"] not in ("Agent", "Task", "SendMessage"):
            if step.stopped:
                with self.driver.lock:
                    self.driver.lock.notify_all()
            return
        # 在公开关闭帧之前发布完整工具；等待方和提交方都按 driver → actor 顺序获取锁。
        with self.driver.lock, self.changed:
            arguments = block.get("input")
            if not isinstance(arguments, dict):
                return
            if block["name"] in ("Agent", "Task"):
                prompt = arguments.get("prompt")
                if isinstance(prompt, str) and prompt:
                    self.agent_offers[block["id"]] = _AgentOffer(
                        self, step.offer_group, sha256(block["id"].encode()).digest(), sha256(prompt.encode()).digest(),
                        time.monotonic() + _RECEIPT_SECONDS,
                        asynchronous=arguments.get("run_in_background") is True,
                    )
            elif block["name"] == "SendMessage":
                self.driver._record_message(self, arguments)
            self.driver.lock.notify_all()

    def _finish_step(self):
        self.expected = self.step.blocks if self.step.reason == "tool_use" else None
        if self.expected:
            native = self.cold_history.receipt_boundary() if self.cold_history is not None else None
            if native is not None:
                if self.step.response_model and any(b["type"] in SIGNED_THINKING_TYPES for b in self.expected):
                    self.signed_tool_models.update(dict.fromkeys(self.step.tool_ids, self.step.response_model))
                if self.signed_tool_models:
                    native["signed_tool_models"] = self.signed_tool_models
            self.receipt_revision = self.driver.checkpoints.offer(
                self.identity, self.reservation["session_id"], self.history,
                [receipt_snapshot(b) for b in self.expected], _RECEIPT_SECONDS,
                native=native,
            )
            self.wait_until = time.monotonic() + _RECEIPT_SECONDS
            for offer in self.agent_offers.values():
                offer.until = self.wait_until
        self._publish(self.step.final)
        self.finished = True
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

    def _matches_current_blocks(self, content):
        if not isinstance(content, list):
            return False
        expected = self.cold_history.submitted_blocks()
        if not self.media_paths:
            actual = [block.get("text") if isinstance(block, dict) and block.get("type") == "text" else None
                      for block in content[-len(expected):]]
            return actual == [block["text"] for block in expected]
        sources = [{"type": "text", "text": f"[Image: source: {path}]"} for path in self.media_paths]
        tail = content[-(len(expected) + len(sources)):]
        if any(not isinstance(block, dict) for block in tail):
            return False
        normalized = [{key: value for key, value in block.items() if key != "cache_control"} for block in tail]
        actual = normalized[:len(expected)]
        if normalized[len(expected):] != sources:
            return False
        # 固定 CLI 会在追加来源说明前为最后一个文本块补一个换行。
        if expected[-1]["type"] == "text" and actual[-1] == {**expected[-1], "text": expected[-1]["text"] + "\n"}:
            actual[-1] = expected[-1]
        return actual == expected

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
        if self.recovery_history is not None:
            # 恢复会话可能在已闭合的结果后生成额外助理边界。核对完整历史中的原调用 ID 后再查本轮标记。
            expected_ids = set(handle.answers)
            ids = [block.get("tool_use_id") for row in rows if isinstance(row.get("content"), list)
                   for block in row["content"] if block.get("type") == "tool_result"
                   and block.get("tool_use_id") in expected_ids]
            if set(ids) != expected_ids or len(ids) != len(expected_ids):
                return False
        # 2.1.293 在新轮或恢复后都只用最近用户输入及紧随的系统行认领本次许可。
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
        multiple = self.cold_history is not None and self.cold_history.current_blocks and self.recovery_history is None
        # Mod 失效时 CLI 可能保留标记。只有按顺序保留原图文和已知附件来源才能认领本轮。
        if multiple and not self._matches_current_blocks(content):
            return False
        if isinstance(content, list):
            marker = "<system-reminder>\n" + line + "\n</system-reminder>"
            guard_count = sum(
                1
                for block in content
                if isinstance(block, dict)
                and block.get("type") == "text"
                and block.get("text") in (marker, marker + "\n")
            )
            if guard_count:
                return guard_count == 1
            # 恢复失败轮时 CLI 会合并相邻用户行。本轮提示是合并后的最后一个文本块。
            latest = content[-1] if content else None
            if not isinstance(latest, dict) or latest.get("type") != "text":
                return False
            content = latest.get("text")
        # 合并用户行和原生字符串用户行都要求精确提示和单独的当前系统标记行。
        if not multiple and (
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

    @staticmethod
    def _protocol_headers(sdk_headers, handle):
        # 能力由本轮 SDK 实际声明，普通 API 只能选择已具备的 beta。
        options = handle.model_headers
        version = options.get("anthropic-version")
        beta = options.get("anthropic-beta")
        sdk_beta = sdk_headers.get("anthropic-beta", "")
        supported = {token.strip() for token in sdk_beta.split(",")}
        if (version is not None and version != sdk_headers.get("anthropic-version", "2023-06-01")
                or beta is not None and not handle.preserve_model_beta
                and any(token.strip() not in supported for token in beta.split(","))):
            raise ModelResponseError(422, _json({"type": "error", "error": {
                "type": "invalid_request_error", "code": "unsupported_parameter",
                "message": "请求的协议版本或 beta 超出本轮原生 SDK 能力",
            }}).encode())
        actual = {}
        for name, value in sdk_headers.items():
            name = name.lower()
            if (name in MODEL_PROTOCOL_HEADERS - {"anthropic-version", "anthropic-beta"}
                    or name.startswith("x-stainless-")) and valid_model_header_value(value):
                actual[name] = value
        for name, value in options.items():
            # 公开 JSON 转成上游 SSE 时，沿用同轮原生请求的接收声明。
            if name != "accept" or handle.stream:
                actual[name] = value
        if not (handle.preserve_model_beta and beta):
            if sdk_beta:
                actual["anthropic-beta"] = sdk_beta
            else:
                actual.pop("anthropic-beta", None)
        return actual

    def _claim_model(self, sdk_headers, native, native_raw=None):
        """在当前预留中认领一次模型提交。@param sdk_headers 该 CLI 的本轮头。
        @param native 内层 CLI 用于配对的请求。@param native_raw CLI 已提交的原始正文。
        @return 本次模型提交的输入，未匹配时为空。
        """
        with self.driver.lock, self.changed:
            step, handle = self.step, self.claim
            pending = not (
                self.dead.is_set()
                or step is None
                or handle is None
                or step.native is None
                or step.claimed
                or (self.oauth_file and (
                    not handle.account_token or not hmac.compare_digest(
                        sdk_headers.get("Authorization", ""), "Bearer " + handle.account_token
                    )
                ))
                or not self._main_request(native, handle)
            )
            if pending:
                if self.oauth_file and handle.expires_at <= time.time_ns() // 1_000_000:
                    raise ModelResponseError(503, _json({"type": "error", "error": {
                        "type": "api_error", "message": "V2 账号凭据已过期",
                    }}).encode())
                if (
                    handle.kind == "new"
                    and self.agent_offer is not None
                    and not self.driver._valid_agent(
                        self.agent_offer, self.identity[-1], self.agent_messages
                    )
                ):
                    # sender 已允许启动终端时，父工具仍可能拒绝。提交模型前再核对一次。
                    raise SubagentBindingError("子代理的原工具已拒绝或取消")
                headers = handle.model_headers
                if handle.model_header_policy:
                    headers = self._protocol_headers(sdk_headers, handle)
                if handle.kind == "new" and self.agent_offer is not None:
                    self.agent_offer.messages.clear()
                    self.agent_messages.clear()
                if self.cold_history is not None:
                    thinking = self.cold_history.thinking
                    if thinking is not None and thinking["type"] == "adaptive" and native.get("thinking") != thinking:
                        raise ModelResponseError(422, _json({"error": {"type": "invalid_request_error",
                            "code": "unsupported_parameter", "message": "CLI 未保留请求的自适应思考显示模式"}}))
                    if self.cold_history.effort is not None:
                        output = native.get("output_config")
                        if not isinstance(output, dict) or output.get("effort") != self.cold_history.effort:
                            raise ModelResponseError(422, _json({"error": {"type": "invalid_request_error",
                                "code": "unsupported_parameter", "message": "CLI 当前模型未生成请求的推理强度"}}))
                    if not self.cold_history.matches_tool_choice(native):
                        raise ModelResponseError(422, _json({"error": {"type": "invalid_request_error",
                            "code": "unsupported_parameter", "message": "CLI 未保留请求的工具选择"}}))
                    if not self.cold_history.matches_history_cache_markers(native):
                        raise ModelResponseError(422, _json({"error": {"type": "invalid_request_error",
                            "code": "unsupported_parameter", "message": "CLI 未保留历史缓存标记"}}))
                    if handle.kind == "recovered" and not self.recovery_history.matches_recovered_signatures(native):
                        raise ModelResponseError(422, _json({"error": {"type": "invalid_request_error",
                            "code": "unsupported_parameter", "message": "CLI 未保留已核对的签名工具历史"}}))
                if handle.kind == "recovered" and not self.driver.checkpoints.submit(
                    self.identity, self.receipt_revision, handle.request_digest, True
                ):
                    raise InputRejection("recovery_used")
                step.claimed = True
                raw, handle.raw = handle.raw, None
                account_token = handle.account_token
                # 原回执已用于核对此次模型提交。此后出现的工具属于这次响应；
                # 在原版终端看到它们之前换一份交付记录，避免它读到上一轮同名 ID 的旧结果。
                self.answers = {}
                self.delivered = set()
                self.receipt_key = secrets.token_bytes(32)
                self.changed.notify_all()
        if not pending:
            return None
        if self.cold_history is not None:
            if native_raw is None:
                raise RuntimeError("冷导入缺少实际 CLI 正文")
            handle.body_source = "interactive_cli"
            plan = self.recovery_history or self.cold_history
            handle.instruction_location = plan.observed_instruction_location(native)
            return _ModelSubmission(step, handle, native_raw, headers, account_token)
        # 旧进程仍校验启动 AT。文件模式的令牌已经与原生步骤绑定。
        if handle.api_context is not None:
            offered = {v.strip() for v in sdk_headers.get("anthropic-beta", "").split(",")}
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
            raw, headers, self.identity[4].removeprefix(TITLE_SESSION_PREFIX).removeprefix(SUGGESTION_SESSION_PREFIX),
            handle.upstream_session_id,
        )
        handle.body_source = "account_sender"
        handle.instruction_location = handle.input_observation.instruction_location
        return _ModelSubmission(step, handle, raw, headers, account_token)

    def serve_model(self, http, native, *, native_raw=None):
        """交付同一次已认领的模型响应。@param http 当前 TUI 连接。
        @param native 内层 CLI 请求。@param native_raw CLI 原始正文。@return 无。
        """
        submission = self._claim_model(http.headers, native, native_raw)
        if submission is None:
            http.send_error(409, "No pending model step")
            return
        if self.driver.managed_oauth and submission.account_token is None:
            raise ModelResponseError(503, b"")
        if self.cold_history is None and self.driver.native_dispatch is not None and self.driver.managed_oauth:
            # 只有镜像的受信入口能安装原生投递器；两条路径使用同一份一次认领结果。
            self.driver.native_dispatch(self, http, submission)
            return
        step, handle = submission.step, submission.handle
        raw, headers = submission.body, submission.headers
        account_token = submission.account_token
        options = {"headers": headers}
        if self.cold_history is not None:
            submission.record_cli_handoff()
        elif getattr(handle, "capture", None) is not None:
            options["capture"] = handle.capture
        if self.driver.managed_oauth:
            # CLI 原生请求的授权头只认证回环连接，实际模型发送取当前认领的账号 AT。
            options["headers"] = {
                **headers,
                **{name: http.headers[name] for name in ("user-agent", "x-app", "anthropic-beta")
                   if name not in headers and http.headers.get(name)},
            }
            if handle.capture_assembly:
                options["capture_assembly"] = True
            if handle.expires_at is not None:
                options["expires_at"] = handle.expires_at
            send_model = self.driver.launcher.managed_model_response
            options.update(account_token=account_token, reservation=handle.reservation)
        else:
            send_model = self.driver.launcher.local_model_response
        repair = handle.signature_exchange
        if repair is not None and handle.signature_known:
            prepared = repair(raw)
            if prepared is not None:
                raw, _ = prepared
        with ExitStack() as active:
            try:
                upstream = active.enter_context(send_model(raw, **options))
            except ModelResponseError as error:
                if repair is None or error.signature_evidence is None:
                    raise
                # 只在首帧前等待同轮许可，CLI 与工具账本仍归原步骤。
                restored = repair(raw, error)
                if (
                    restored is None or self.dead.is_set()
                    or (handle.expires_at is not None and handle.expires_at <= time.time_ns() // 1_000_000)
                ):
                    raise
                raw, attempt_id = restored
                if self.driver.managed_oauth:
                    options["attempt_id"] = attempt_id
                try:
                    upstream = active.enter_context(send_model(raw, **options))
                except ModelResponseError as final_error:
                    # 本机发送器明确确认尚未出站时，仍交付已经取得的签名拒绝。
                    if final_error.before_send:
                        raise error from None
                    if final_error.source in ("managed_oauth_http", "local_provider_http"):
                        handle.repair_attempt_id = attempt_id
                    raise
                handle.repair_attempt_id = attempt_id
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
            if self.driver.managed_oauth:
                # 发布首个模型事件前把同轮额度交给预留，避免事件源先发送私有响应头。
                handle.quota_headers = passive_quota_headers(upstream.headers)
            http.model_stream_started = True
            http.send_response(200)
            http.send_header("Content-Type", "text/event-stream")
            http.send_header("Connection", "close")
            http.end_headers()
            http.close_connection = True
            for wire in self._model_events(step, upstream):
                http.wfile.write(wire)
                http.wfile.flush()

    def _model_events(self, step, upstream):
        """按外层读取进度观察同一模型流，确认终态后唤醒会话。
        @param step 已认领的模型步骤。@param upstream 原始 SSE 字节流。@return 供内层 CLI 消费的原帧。
        """
        tail = bytearray()
        for wire, event in wire_events(upstream):
            if (self.reservation["session_id"].startswith(SUGGESTION_SESSION_PREFIX)
                    and event is not None and event.get("type") == "content_block_start"
                    and event.get("content_block", {}).get("type") in ("tool_use", "server_tool_use")):
                # 声明保留用于前缀缓存。建议是文本回复，工具输出不能进入客户端或终端执行。
                event = {"type": "error", "error": {"type": "api_error", "message": "建议回复包含工具调用"}}
                wire = b"event: error\ndata: " + _json(event).encode() + b"\n\n"
            terminal_error = event is not None and event.get("type") == "error"
            with self.changed:
                if self.dead.is_set():
                    raise RuntimeError("模型轮已取消")
                if terminal_error:
                    # 上游已建立 SSE 时保留其原始 error 记录，不能伪造正常 message_stop。
                    self._publish([wire])
                    self.finished = True
                    self.expected = None
                    self.changed.notify_all()
            if terminal_error:
                yield wire
                return
            public = wire
            if (self.cold_history is not None and event is not None
                    and event.get("type") == "content_block_start"
                    and event.get("content_block", {}).get("type") == "tool_use"):
                block = event["content_block"]
                tool = self.cold_history.tools.get(block.get("name"))
                if tool is None:
                    raise ValueError("模型工具不属于当前会话的 MCP 声明")
                # 内层使用原生 MCP 名称，外层仍用客户工具名称和同一模型调用 ID。
                event = {**event, "content_block": {**block, "name": tool["name"]}}
                public = b"event: content_block_start\ndata: " + _json(event).encode() + b"\n\n"
            self._observe(step, event)
            with self.changed:
                if step.stopped:
                    if len(tail) + len(wire) > BODY_LIMIT:
                        raise ValueError("模型终态后的数据超限")
                    tail.extend(wire)
                else:
                    self._publish([public])
            yield wire
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
            self.agent_offers = {}
            self.step = WireStep(handle.tools)
            self.history = handle.history
            self.answers = {} if handle.kind == "recovered" else handle.answers
            self.wait_until = None
            self.changed.notify_all()
            if handle.kind != "continuation":
                self.launch_token = None if self.oauth_file else handle.account_token
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


def _receipt_request(body, reservation, *, cache_ttl=None):
    # 只绑定实际支持的生成参数和返回表示，连接 ID 与预留期限可随重试变化。
    policy = reservation.get("body_policy")
    if cache_ttl is not None and cache_ttl != (policy["ttl"] if policy else "off"):
        # 原生续轮沿根轮的 TTL。网关省略默认策略，摘要也要沿用这种旧表示。
        policy = {**(policy or {"sub2api": False, "adaptive": False}), "ttl": cache_ttl}
        if cache_ttl == "off" and not policy["sub2api"] and not policy["adaptive"]:
            policy = None
    return digest([body, dict(reservation.get("model_headers") or {}), policy, reservation.get("input_format")])


class _Reserved:
    """账号内只准单次提交的交互预留。"""

    def __init__(
        self, actor, kind, history, answers, body, stream, raw, reservation, request_digest=None,
        *, input_observation,
    ):
        self.actor = actor
        self.kind = kind
        self.history = history
        self.answers = answers
        self.tools = body.get("tools", [])
        self.stream = stream
        self.raw = raw
        self.model_headers = dict(reservation.get("model_headers") or {})
        self.model_header_policy = reservation.get("model_header_policy") == 1
        self.preserve_model_beta = self.model_header_policy and (
            native_input(body, reservation.get("input_format"))
            or any(row["role"] == "system" for row in body["messages"])
        )
        self.upstream_session_id = None
        self.reservation = reservation
        self.account_token = None
        self.disconnected = None
        self.quota_headers = None
        self.expires_at = None
        # 原生请求已声明完整的协议上下文。普通 API 的历史管理需要本次实际 CLI 提供能力。
        self.api_context = body.get("context_management") if "metadata" not in body else None
        self.thinking = body.get("thinking")
        self.capture_assembly = False
        self.signature_exchange = None
        self.signature_known = False
        self.repair_attempt_id = None
        self.body_source = None
        self.input_observation = input_observation
        self.instruction_location = None
        self.sent = self.completed = False
        self.request_digest = request_digest

    @property
    def session_origin(self) -> str | None:
        """返回本次尝试对应的实际会话来源。@return 复用或启动来源。"""
        if self.kind == "continuation":
            return "live_process"
        return self.actor.launch_observation.origin

    def send(self, command):
        """实际启动或恢复一个模型步骤。@param command 已核验工作区。@return 逐帧输出。"""
        actor = self.actor
        token = command.pop("account_token", None)
        file = command.pop("oauth_file", None)
        with actor.changed:
            if self.sent or actor.claim is not self or actor.dead.is_set():
                raise ValueError("原预留已提交或已取消")
            if self.kind == "continuation" and actor.oauth_file != (file is not None):
                raise ValueError("原工具回执的凭据模式已变化")
            if file is not None:
                home, _ = actor.driver.launcher.session_paths(command)
                directory = home / ".claude"
                if actor.credential_dir is not None and actor.credential_dir != directory:
                    raise ValueError("本轮凭据文件与原会话目录不符")
                actor.credential_dir = directory
                try:
                    actor.driver.launcher.publish_oauth_file(directory, file)
                except (OSError, ValueError):
                    # 此时本轮工具凭据尚未交给 CLI，网关可归还原工具回执。
                    raise ModelResponseError(503, _json({"type": "error", "error": {
                        "type": "api_error", "message": "V2 完整账号凭据不可用",
                    }}).encode(), source="oauth_file_before_model") from None
                token = file["access_token"]
                self.expires_at = file["expires_at"]
        with actor.driver.lock, actor.changed:
            if self.sent or actor.claim is not self or actor.dead.is_set():
                raise ValueError("原预留已提交或已取消")
            if self.kind == "new" and actor.agent_offer is not None:
                if not actor.driver._valid_agent(actor.agent_offer, actor.identity[-1], actor.agent_messages):
                    raise SubagentBindingError("子代理所属原轮已结束或取消")
                actor.agent_offer.submitted = True
            self.capture_assembly = command.get("capture_assembly") is True
            self.upstream_session_id = command.get("upstream_session_id")
            if self.answers:
                recorded = actor.driver.checkpoints.submit(
                    actor.identity, actor.receipt_revision, self.request_digest, False
                )
                if self.kind == "recovered" and not recorded:
                    raise ValueError("此恢复许可已消费或过期")
            else:
                actor.driver.checkpoints.discard(actor.identity)
            if self.kind != "continuation":
                actor.oauth_file = file is not None
            self.account_token = token
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
            if self.sent and (not self.completed or not actor.expected or self.reservation.get("agent_summary")):
                step = actor.step
                actor.completed_normally = (
                    self.completed
                    and step is not None
                    and step.stopped
                    and bool(step.final)
                )
                actor.abort()
            if not self.sent and self.kind != "continuation":
                actor.abort()
            actor.changed.notify_all()
        if actor.dead.is_set() and actor.worker is None:
            actor.driver._retire(actor)


class SessionDriver:
    """绑定当前账号的真实 TUI 会话。@param config 受信预留配置。@param launcher 原版账号启动器。"""

    def __init__(self, config, launcher=None, capacity=None, *, native_dispatch=None):
        """创建该账号的进程表。@param config 源配置。@param launcher 受信启动器。
        @param capacity 账号容量。@param native_dispatch 镜像提供的原生模型投递回调。@return 无。
        """
        if launcher is None:
            import tui_sender_launch as launcher
        self.launcher = launcher
        self.checkpoints = ReceiptCheckpoints(getattr(launcher, "STORAGE", None))
        self.managed_oauth = getattr(launcher, "managed_oauth_enabled", lambda: False)()
        self.oauth_file_available = getattr(launcher, "file_oauth_enabled", lambda: False)()
        self.native_dispatch = native_dispatch
        # 编排每个 HTTP 并发配置两个预留。等待新 TUI 的队列必须留下至少一个传输名额还工具。
        limit = max(1, config["max_reservations"] // 2)
        self.summary_only_headroom = False
        if capacity is None:
            memory = Path("/sys/fs/cgroup/memory.max").read_text().strip()
            # 1GiB 账号实测同时持有三个 TUI。预留 256MiB 基础开销及每进程 256MiB。
            reserve = 256 * 1024**2
            self.summary_only_headroom = memory == "max"
            budget = (
                (limit + 2) * reserve
                if memory == "max"
                else int(memory)
                if memory.isdecimal()
                else 0
            )
            # 暂停等 Agent 的父进程继续记入 RAM；只多规划一个经验证的子进程。
            # 无硬预算时把最后一位仅用于等工具的子代理查询进度；其它入口沿用之前的上限。
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
        with actor.changed:
            directory, actor.credential_dir = actor.credential_dir, None
            if directory is not None:
                try:
                    self.launcher.clear_oauth_file(directory)
                except OSError:
                    # 下次事件源取得独占监听锁后定向回收；处理错误仍归还当前进程名额。
                    pass
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
                            self.checkpoints.discard(child.identity)
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

    def _record_message(self, actor, arguments, *, failed=False):
        recipient, message = arguments.get("to"), arguments.get("message")
        if not isinstance(recipient, str) or not isinstance(message, str):
            return
        offer = self.background_agents.get((*actor.identity[:5], recipient))
        if offer is None or offer.parent is not actor or time.monotonic() >= offer.until:
            return
        digest = sha256(message.encode()).digest()
        if failed:
            if offer.messages[digest] > 1:
                offer.messages[digest] -= 1
            else:
                offer.messages.pop(digest, None)
        elif not offer.submitted:
            offer.messages[digest] += 1

    def _acknowledge_agents(self, actor, answers):
        self._prune_background()
        newly_bound = set()
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
                newly_bound.add(hint)
        # 同一父轮可以同时发出启动与追加消息。收到启动回执才有可核对的收件人。
        for block in actor.expected or ():
            if block["type"] != "tool_use" or block["name"] != "SendMessage" or block["id"] not in answers:
                continue
            arguments = block.get("input")
            if not isinstance(arguments, dict) or not isinstance(arguments.get("to"), str):
                continue
            failed = answers[block["id"]].get("is_error") is True
            if arguments["to"] in newly_bound:
                if not failed:
                    self._record_message(actor, arguments)
            elif failed:
                self._record_message(actor, arguments, failed=True)
        self.lock.notify_all()

    def _claim_agent(self, identity, hint, prompts, extras, ticket):
        self._prune_background()
        matched = self.background_agents.get((*identity, hint))
        if matched is not None:
            if (
                matched.prompt not in prompts
                or (ticket.groups is not None and matched.group not in ticket.groups)
                or matched.claimed is not None
                or matched.conflicted
                or not extras <= matched.messages
            ):
                raise SubagentBindingError("子代理与已登记的后台启动回执不符")
            matched.claimed = hint
            return matched
        matching = []
        for actor in self.sessions.values():
            if actor.identity[:5] != identity or actor.dead.is_set():
                continue
            with actor.changed:
                matching.extend(
                    offer
                    for offer in actor.agent_offers.values()
                    if not offer.receipt_received and offer.prompt in prompts
                )
        # CLI 有时在后台首轮多附一个 LF。这种匹配必须等原工具的启动回执核对子 ID。
        if not matching:
            raise SubagentBindingError("子代理缺少原父轮的派工")
        groups = frozenset(offer.group for offer in matching)
        if ticket.groups is None:
            ticket.groups = groups
        elif ticket.groups.isdisjoint(groups):
            raise SubagentBindingError("等待的原父轮已结束或取消")
        # 其它父轮的同提示工具也会造成歧义，但不能成为本次等待的归属。
        if len(matching) > 1 or matching[0].prompt != prompts[0] or extras:
            ticket.exact_receipt_only = True
        if ticket.exact_receipt_only:
            return None
        if matching[0].claimed is not None:
            raise SubagentBindingError("子代理需要同一会话中唯一待交接的 Agent 工具")
        (offer,) = matching
        # 流还可能给出同提示兄弟。只在原模型已封闭该组时按唯一完整提示认领。
        with offer.parent.changed:
            if not offer.parent.step.stopped:
                return None
            if offer.parent.step.reason != "tool_use":
                raise SubagentBindingError("父轮没有完成该工具组")
        offer.claimed = hint
        return offer

    @staticmethod
    def _valid_agent(offer, hint, messages):
        if offer.conflicted or time.monotonic() >= offer.until or not messages <= offer.messages:
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
        if key in self.sessions:
            return False
        if ticket.agent_summary:
            # 只有原子代理正在等工具时才借一个空闲物理位；父子派工已经排队时先满足派工。
            owner = self.sessions.get(key[:-1])
            return ordinary_room or (
                owner is not None and owner.expected is not None and not owner.dead.is_set()
                and not any(w.offer and any(w.offer.waiting_ancestors()) for w in self.waiters)
            )
        if ticket.recovering:
            return ordinary_room or len(key) > 5
        return (len(key) == 5 or offer is not None) and (
            ordinary_room or offer is not None and any(offer.waiting_ancestors())
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
        input_observation = MessageInputObservation()
        body, stream, frozen = input_message(
            raw, native=reservation.get("input_format"), session_id=reservation["session_id"],
            body_policy=reservation.get("body_policy"),
            observation=input_observation,
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
        summary = reservation.get("agent_summary") is True
        if summary:
            if agent_hint is None or reservation["continuation_only"]:
                raise ValueError("原生进度查询缺少独立预留")
            # 只有认证的网关在核对原工具组后设置此位。用独立 actor 和工作区运行原始正文。
            # 同一个子代理的重复查询串行使用自己的进度工作区，避免每次心跳创建一份持久 HOME。
            actor_key = (*actor_key, "agent-summary")
        offered, returned = split_reply(messages)
        policy = reservation.get("body_policy")
        # disabled 经平台改写后也会呈现 adaptive/updates，仍须与客户端显式指定区分。
        native_body_policy = not policy or not (policy["sub2api"] or policy["adaptive"])
        native_cache_ttl = policy["ttl"] if policy else "off"
        deadline = reservation["deadline_unix_ms"] / 1000

        def remaining():
            result = deadline - time.time()
            if result <= 0 or cancel_event is not None and cancel_event.is_set():
                raise TimeoutError("原版会话预留已取消或到期")
            return result

        checkpoint = None
        native_checkpoint = None
        if not summary and (returned or reservation["continuation_only"]):
            if not returned:
                raise ValueError("缺少原轮工具结果")
            tool_results_only = all(
                row["role"] == "user" and isinstance(row["content"], list) and row["content"]
                and all(block["type"] == "tool_result" for block in row["content"])
                for row in messages[offered + 1:]
            )
            request = _receipt_request(body, reservation)
            active_request, active_ttl = request, native_cache_ttl
            with self.lock:
                while (actor := self.sessions.get(actor_key)) is not None:
                    with actor.changed:
                        root = actor.cold_history
                        frozen_ttl = root.cache_ttl if root is not None else native_cache_ttl
                        if frozen_ttl != active_ttl:
                            active_ttl = frozen_ttl
                            active_request = (request if active_ttl == native_cache_ttl
                                              else _receipt_request(body, reservation, cache_ttl=active_ttl))
                        prior = actor.claim
                        retiring = actor.dead.is_set() or (prior is not None and prior.sent
                                                           and prior.request_digest == active_request)
                    if not retiring:
                        break
                    # 原网关退出时，发送器可能正在释放同一请求。只等待该步骤的监护线程。
                    self.lock.wait(min(remaining(), 0.05))
                # 监护线程已经完成进程回收才会从此表删除；同一会话的其他子代理独立运行。
                if actor is None:
                    checkpoint = self.checkpoints.find(actor_key)
                    if checkpoint is None:
                        raise InputRejection("unrecoverable_tool")
                    branch, previous, expected, prior_request, revision, native_checkpoint = checkpoint
                    answers = tool_receipts(messages, previous, expected,
                                            input_format=reservation.get("input_format"), checkpoint=True)
                    if native_checkpoint is None and prior_request is not None and prior_request != request:
                        raise ValueError("已提交的工具结果或模型参数与重试不符")
            if actor is not None:
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
                    answers = tool_receipts(messages, actor.history, actor.expected,
                                            input_format=reservation.get("input_format"))
                    handle = _Reserved(
                        actor,
                        "continuation",
                        history,
                        answers,
                        body,
                        stream,
                        frozen,
                        reservation,
                        active_request,
                        input_observation=input_observation,
                    )
                    if actor.cold_history is not None:
                        prompt_index = len(actor.cold_history.history) + 1
                        # 继续使用原进程的生效设置，校验通过后才把回执交给等待工具。
                        plan = ColdHistory.from_request(
                            {**body, "messages": messages[:prompt_index]}, actor.cold_history.system_policy,
                            cache_ttl=actor.cold_history.cache_ttl,
                        )
                        if not native_body_policy or plan != actor.cold_history or not tool_results_only:
                            raise InputRejection("unsupported_parameter")
                    actor.claim = handle
                    return handle

        cold = recovery_history = None
        signed_tool_models = {}
        system_policy = reservation.get("client_system_prompt_policy", "append")
        is_native = native_input(body, reservation.get("input_format"))
        native_history_allowed = (self.managed_oauth and reservation.get("native_cold_history") is True
                                  and native_body_policy and agent_hint is None and not is_native)
        if native_checkpoint is not None:
            if not native_history_allowed or not tool_results_only:
                raise InputRejection("unsupported_parameter")
            boundary = dict(native_checkpoint)
            signed_tool_models = boundary.pop("signed_tool_models", {})
            cold = ColdHistory.from_receipt_boundary(body, boundary)
            if cold is None:
                raise InputRejection("unsupported_parameter")
            request = _receipt_request(body, reservation, cache_ttl=cold.cache_ttl)
            if prior_request is not None and prior_request != request:
                raise ValueError("已提交的工具结果或模型参数与重试不符")
            recovery_history = cold.resume_receipts(messages, signed_tool_models=signed_tool_models)
            if recovery_history is None:
                raise InputRejection("unsupported_parameter")
        elif native_history_allowed and checkpoint is None:
            cold = ColdHistory.from_request(body, system_policy, cache_ttl=native_cache_ttl)
        if cold is None and system_policy != "append" and not is_native and checkpoint is None:
            raise InputRejection("unsupported_parameter")
        launch_plan = recovery_history or cold
        prompt = launch_plan.submitted_prompt() if launch_plan is not None else prompt_text(messages)
        with self.lock:
            if agent_hint is not None and not summary and (
                actor_key in self.sessions
                or any(item.actor_key == actor_key for item in self.waiters)
            ):
                raise SubagentBindingError("此子代理已持有独立进程，工具回执须返回原轮")
            if agent_hint is not None and not summary and checkpoint is None:
                child_text, extras = _agent_prompt(messages)
                prompts = [sha256(child_text.encode()).digest()]
                if child_text.endswith("\n"):
                    prompts.append(sha256(child_text[:-1].encode()).digest())
            offer = None
            ticket = _Waiting(actor_key, agent_summary=summary, recovering=checkpoint is not None)
            handoff_limit = time.monotonic() + _AGENT_HANDOFF_SECONDS
            try:
                while True:
                    if self.closed:
                        raise RuntimeError("当前账号事件源已关闭")
                    try:
                        timeout = remaining()
                    except TimeoutError:
                        if ticket.exact_receipt_only and not (cancel_event and cancel_event.is_set()):
                            raise SubagentAmbiguousError("本次预留结束前未收到对应启动回执") from None
                        raise
                    capacity = self.capacity.snapshot()
                    physical_limit = self.ordinary_limit if self.summary_only_headroom and not summary else capacity.limit
                    if (summary and capacity.in_use >= physical_limit and self.sessions
                            and all(actor.expected and actor.claim is None for actor in self.sessions.values())):
                        # 全部物理位都在等外部工具。让进度请求退避，把下一次准入留给真回执。
                        raise TimeoutError("原工具等待已占满账号物理进程额度")
                    if agent_hint is not None and not summary and offer is None and checkpoint is None:
                        # 两个相同提示在收到启动回执前无法区分，挂起握手而不占进程。
                        offer = ticket.offer = self._claim_agent(
                            identity,
                            agent_hint,
                            prompts,
                            extras,
                            ticket,
                        )
                    if offer is not None:
                        if not self._valid_agent(offer, agent_hint, extras):
                            raise SubagentBindingError("子代理所属原轮已结束或取消")
                        if (
                            capacity.in_use >= physical_limit
                            and not offer.asynchronous
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
                        capacity.in_use < physical_limit
                        and self._eligible(ticket, ordinary_room)
                        and first in (None, ticket)
                    ):
                        slot = self.capacity.acquire(
                            timeout=0, cancel_event=cancel_event
                        )
                        actor_reservation = reservation
                        if summary:
                            branch_id = UUID(bytes=sha256(_json(actor_key).encode()).digest()[:16], version=4)
                            actor_reservation = {**reservation, "session_id": AGENT_SESSION_PREFIX + str(branch_id)}
                        elif checkpoint is not None:
                            actor_reservation = {**reservation, "session_id": branch}
                        elif offer is not None:
                            actor_reservation = {**reservation, "session_id": AGENT_SESSION_PREFIX + str(uuid4())}
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
                        actor.cold_history = cold
                        actor.recovery_history = recovery_history
                        actor.signed_tool_models = signed_tool_models
                        if checkpoint is not None:
                            actor.receipt_revision = revision
                        if offer is not None:
                            actor.agent_messages = extras
                        self.sessions[actor_key] = actor
                        handle = _Reserved(
                            actor,
                            "recovered" if checkpoint is not None else "new",
                            history,
                            answers if checkpoint is not None else {},
                            body,
                            stream,
                            frozen,
                            reservation,
                            request if checkpoint is not None else None,
                            input_observation=input_observation,
                        )
                        actor.claim = handle
                        return handle
                    if ticket not in self.waiters:
                        # 源端与 sender 都给一个可信子依赖留下有界位置。
                        # 已占满普通队列时，合法子轮仍可等下一次物理释放。
                        reserved = any(len(item.actor_key) > 5 and not item.agent_summary for item in self.waiters)
                        if len(self.waiters) - int(reserved) >= self.max_waiters and (
                            reserved or agent_hint is None or summary
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
        self.checkpoints.close()
