"""从 sender 的受管安装和原生工作区启动同容器交互式 Claude Code。"""

from collections.abc import Iterator
from contextlib import closing, contextmanager, suppress
from ctypes import CDLL, c_int, c_ushort
from datetime import datetime, timezone
import fcntl
from functools import lru_cache
from hashlib import file_digest, sha256
from http.client import HTTPConnection, HTTPException, HTTPResponse
from ipaddress import ip_address
import json
import os
from pathlib import Path
from socket import AF_UNIX, SOCK_SEQPACKET, create_connection, socketpair
from stat import S_IMODE, S_ISREG
from subprocess import DEVNULL, Popen, run
from threading import Lock, Thread
import time
from urllib.parse import urlsplit
from uuid import UUID

from runtime_files import atomic_json, atomic_text, directory_fd, private_directory
from tui_direct_version import DIRECT_CLI_SHA256, DIRECT_CLI_VERSION
from tui_messages import (
    BODY_LIMIT, MODEL_PROTOCOL_HEADERS, OAUTH_FILE_LIMIT,
    ModelResponseError, encode, valid_model_header_value,
)
from tui_workspace_launch import WorkspaceLaunchObservation, launch_workspace_cli


VERSION = "2.1.293"
# 上一版已签 Mod 继续用于已有管理员明确发布的策略。发行自动策略核对本批钩子。
_PREVIOUS_MANAGED_DIRECT_HOOK = "ec3ed74088d5a767696c1d0106588f1ee24ebf39ae789cc04cc918f17b8bc8f8"
PROGRAM_SHA256 = "8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978"
INSTALL = Path("/cli") / VERSION
STORAGE = Path("/native")
GUARD = Path("/opt/flower/tui/tui-guard")
CONNECT_SHIM = GUARD.with_name("tui-connect.so")
LOCAL_PROVIDER = Path("/run/v3/tui-local-provider.json")
_OAUTH_FILE_NAME = ".credentials.json"
ACCOUNT_ORIGIN = "https://api.anthropic.com"
_program_lock = Lock()
_verified_program = None
_SECOND_NS = 1_000_000_000
_MAX_RETRY_SECONDS = (1 << 64) - 1


def _verify_inode(identity: tuple, descriptor: int, expected: str) -> None:
    global _verified_program
    # 多个准备线程的 FD 编号各异。同一已核验的只读 inode 只读一次固定版本程序。
    with _program_lock:
        if identity == _verified_program:
            return
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            if file_digest(stream, "sha256").hexdigest() != expected:
                raise ValueError("账号受管 CLI 摘要与 V2 的固定版本不符")
        _verified_program = identity


@contextmanager
def _open_program():
    install, expected = ((INSTALL.with_name(DIRECT_CLI_VERSION), DIRECT_CLI_SHA256)
                         if direct_model_enabled() else (INSTALL, PROGRAM_SHA256))
    if install.resolve(strict=True) != install or not (install / ".ready").is_file():
        raise ValueError("账号尚未安装 V2 的官方 CLI")
    path = (install / "node_modules/.bin/claude").resolve(strict=True)
    if not path.is_relative_to(install):
        raise ValueError("官方 CLI 程序越过账号固定版本目录")
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("官方 CLI 文件归属或权限不符")
        _verify_inode((info.st_dev, info.st_ino, info.st_ctime_ns, info.st_size, expected), stream.fileno(), expected)
        yield path, stream.fileno()


def official_program() -> Path:
    """核对当前账号已安装的原版 CLI。@return 只读安装卷中的实际可执行文件路径。"""
    with _open_program() as (path, _):
        return path


def _loopback_provider() -> tuple[str, str, str, int]:
    # 本机开发单独启用。运行时目录由控制端只读挂载，消息正文与 HTTP 头均无配置入口。
    if os.environ.get("V3_TUI_LOCAL_PROVIDER_CONFIG") != str(LOCAL_PROVIDER):
        raise ValueError("该 sender 未配置本机交互提供方")
    with os.fdopen(os.open(LOCAL_PROVIDER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or S_IMODE(info.st_mode) not in (0o400, 0o440, 0o600, 0o640)
                or info.st_mode & 0o040 and info.st_gid != os.getegid()):
            raise ValueError("本机交互提供方配置的归属或权限无效")
        values = json.load(stream)
    if not isinstance(values, dict) or set(values) != {"base_url", "local_bearer"}:
        raise ValueError("本机交互提供方配置无效")
    return _loopback_endpoint(values["base_url"], values["local_bearer"])


def _loopback_endpoint(url: str, secret: str) -> tuple[str, str, str, int]:
    target = urlsplit(url)
    if (target.scheme != "http" or not target.hostname or not ip_address(target.hostname).is_loopback
            or target.username is not None or target.password is not None or target.path not in ("", "/")
            or target.query or target.fragment or not target.port
            or not isinstance(secret, str) or not secret or any(ord(c) < 33 or ord(c) > 126 for c in secret)):
        raise ValueError("本机交互提供方需要显式回环地址和本地网关口令")
    return target.geturl().rstrip("/"), secret, target.hostname, target.port


def _retry_seconds(values):
    if len(values) != 1:
        return None
    value = values[0].strip(" \t")
    if value.isascii() and value.isdecimal():
        digits = value.lstrip("0")
        return _MAX_RETRY_SECONDS if len(digits) > 20 else min(int(digits or "0"), _MAX_RETRY_SECONDS)
    # HTTP-date 允许三种历史格式。只按 GMT 解析，避免不相关头部或正文被解释为退避指令。
    for fmt in ("%a, %d %b %Y %H:%M:%S GMT", "%A, %d-%b-%y %H:%M:%S GMT", "%a %b %d %H:%M:%S %Y"):
        try:
            date = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if "%y" in fmt:
            # RFC 850 双位年份以当前时间向未来最多 50 年解释。
            limit = datetime.fromtimestamp(time.time_ns() // _SECOND_NS, timezone.utc).year + 50
            year = limit - (limit - date.year) % 100
            try:
                date = date.replace(year=year)
            except ValueError:
                return None
        until = int(date.timestamp()) * _SECOND_NS
        return max(0, (until - time.time_ns() + _SECOND_NS - 1) // _SECOND_NS)
    return None


def _provider_wait(provider, *, seconds=None):
    _, bearer, host, port = provider
    # 凭据和地址共同标识实际接收该模型 POST 的提供方，只向本账号持久卷写入摘要与到期时间。
    owner = sha256(f"{ip_address(host)}\0{port}\0{bearer}".encode()).hexdigest()
    directory = STORAGE / "tui-provider-backoff"
    private_directory(directory)
    path = directory / owner
    lock = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        now = time.time_ns()
        try:
            fd = os.open(owner, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=lock)
        except FileNotFoundError:
            previous = 0
        else:
            with os.fdopen(fd, "rb") as stream:
                value = stream.read(32)
                if not value.isdigit() or len(value) > 30 or not S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("本机模型退避记录无效")
                previous = int(value)
        deadline = max(previous, now + (seconds or 0) * _SECOND_NS)
        if deadline > previous and seconds:
            atomic_text(path, str(deadline))
        elif previous and previous <= now:
            path.unlink()
        # 并发的短退避不能提前开放原提供方；休眠和 sender 重启后仍使用同一到期时间。
        return min(_MAX_RETRY_SECONDS, (deadline - now + _SECOND_NS - 1) // _SECOND_NS)
    finally:
        os.close(lock)


def _check_wait(provider):
    seconds = _provider_wait(provider)
    if seconds:
        raise ModelResponseError(429, encode({"error": {
            "type": "rate_limit_error", "message": "本机模型提供方仍在限流等待期",
        }}), source="local_provider_backoff", retry_after=seconds)


def check_provider_backoff():
    """在预留工具轮或交互进程之前核对当前提供方的退避期。@return 无。"""
    if not managed_oauth_enabled():
        _check_wait(_loopback_provider())


def managed_oauth_enabled() -> bool:
    """读取编排为此容器选择的凭据模式。@return 是否使用受管账号凭据。"""
    return os.environ.get("V3_TUI_MANAGED_OAUTH") == "1"


def _managed_policy_enabled() -> bool:
    return os.environ.get("V3_TUI_MANAGED_POLICY") == "1"


def direct_model_enabled() -> bool:
    """报告编排为本角色核定的直发能力。@return 当前绑定是否具备直发能力。"""
    return os.environ.get("V3_TUI_DIRECT") == "1"


def _sender_config():
    return json.loads(Path(os.environ.get("V3_SENDER_CONFIG", "/run/v3/sender.json")).read_bytes())


def _check_direct_policy(config):
    policy = config.get("tui_managed_policy") or {}
    binding = config["binding"]
    engine = Path(__file__).with_name("tui-direct-mod") / "hooks/engine.js"
    allowed_hooks = {sha256(engine.read_bytes()).hexdigest()}
    if not policy.get('release_bundle'):
        allowed_hooks.add(_PREVIOUS_MANAGED_DIRECT_HOOK)
    if (config.get("tui_direct") is not True or not _managed_policy_enabled()
            or any(policy.get(key) != binding[key] for key in ('account_id', 'environment_id'))
            or not policy.get("managed_order") or policy.get("direct_hook_sha256") not in allowed_hooks):
        raise ValueError("账号直发缺少同发行的管理员 Mod")


def _bound_sender(reservation: dict) -> tuple[dict, dict]:
    config = _sender_config()
    binding = config["binding"]
    identity = {name: reservation[name] for name in ("account_id", "environment_id", "generation")}
    if any(binding[name] != value for name, value in identity.items()) or config.get("allowed_origin") != ACCOUNT_ORIGIN:
        raise ValueError("V2 模型投递的账号绑定已变化")
    return config, identity


def direct_proxy(reservation: dict) -> str:
    """取本轮已校验账号的冻结代理配置。@param reservation 同轮预留。@return 账号代理 URL。"""
    config, _ = _bound_sender(reservation)
    if not direct_model_enabled():
        raise ValueError("当前账号环境缺少直发能力")
    _check_direct_policy(config)
    return config["proxy_url"]


class _ObservedHTTPConnection(HTTPConnection):
    """保留由 HTTPConnection 编码的请求头顺序，包括其自动生成的字段。"""

    def putheader(self, header, *values):
        """记录已被标准库接纳的请求头。@param header 字段名。@param values 字段值。@return 无。"""
        super().putheader(header, *values)
        def decoded(value):
            return value.decode("latin-1") if isinstance(value, bytes) else str(value)
        self.observed_headers.append((decoded(header), "\r\n\t".join(map(decoded, values))))


def _read_model_error(response):
    try:
        raw = response.read(BODY_LIMIT + 1)
    except (OSError, HTTPException):
        # 已知 HTTP 状态仍可交付，截断正文不能取得修复许可。
        return b"", False
    if len(raw) > BODY_LIMIT:
        return b"", False
    if response.chunked:
        return raw, response.isclosed()
    if response.length is None:
        # 阻塞读取上限加一字节后的短读已到 EOF。解析失败的长度声明也会得到 None。
        return raw, response.getheader("Content-Length") is None
    return raw, response.length == 0


@contextmanager
def local_model_response(raw: bytes, *, headers: dict[str, str] | None = None, capture=None) -> Iterator[HTTPResponse]:
    """将已认领的一轮业务正文投递给本账号显式配置的独立回环模型。

    @param raw 输入校验后的 Messages 正文；调用者负责本轮的单次认领。
    @param headers 已准入协议选项和受信 SDK 字段。@param capture 当前私有采集的结果容器。
    @return 可逐段读取的原 HTTP 响应，退出时关闭连接。
    """
    provider = _loopback_provider()
    _, bearer, host, port = provider
    headers = headers or {}
    if any((name not in MODEL_PROTOCOL_HEADERS and name != "x-claude-code-session-id"
            and not name.startswith("x-stainless-")) or not valid_model_header_value(value)
           for name, value in headers.items()):
        raise ValueError("本机模型的版本或功能声明无效")
    # 与 sender 的源数据空闲预算一致。HTTPConnection 不跟随重定向、不重试模型 POST。
    _check_wait(provider)
    connection_type = HTTPConnection if capture is None else _ObservedHTTPConnection
    with closing(connection_type(host, port, timeout=120)) as connection:
        if capture is not None:
            connection.observed_headers = []
        connection.request("POST", "/v1/messages", body=raw, headers={
            "Authorization": "Bearer " + bearer,
            "Content-Type": "application/json",
            "accept": "text/event-stream",
            "anthropic-version": "2023-06-01",
            **headers,
        })
        if capture is not None:
            # request 已将全部实体交给回环连接；响应、TLS 或远端已收不能由本事件推断。
            capture.append((connection.observed_headers, raw))
        with closing(connection.getresponse()) as response:
            if response.status != 200:
                seconds = None
                if response.status == 429:
                    seconds = _retry_seconds(response.headers.get_all("Retry-After", []))
                    if seconds is not None:
                        seconds = _provider_wait(provider, seconds=seconds)
                raw_error, complete = _read_model_error(response)
                raise ModelResponseError(response.status, raw_error,
                                         source="local_provider_http" if 400 <= response.status < 600 else None,
                                         retry_after=seconds, complete=complete)
            yield response


@lru_cache(maxsize=3)
def _guard_usable(identity: tuple, check: str) -> bool:
    # 不同镜像的程序有不同 inode；缺失内核权限或制品时保持未就绪。
    return run([GUARD, check], stdin=DEVNULL,
               stdout=DEVNULL, stderr=DEVNULL, check=False).returncode == 0


@lru_cache(maxsize=1)
def _loopback_broker():
    serve = CDLL(str(CONNECT_SHIM)).tui_run_loopback_broker
    serve.argtypes = [c_int, c_ushort]
    serve.restype = c_int
    return serve


@contextmanager
def _loopback_channel(port: int | None):
    if port is None:
        yield [], ()
        return
    serve = _loopback_broker()
    client, server = socketpair(AF_UNIX, SOCK_SEQPACKET)

    def serve_current_session():
        # CLI 退出后内核关闭其一端。受信线程随 Unix 通道结束，无需回收额外进程。
        with server:
            serve(server.fileno(), port)

    with client:
        try:
            Thread(target=serve_current_session, daemon=True).start()
        except BaseException:
            server.close()
            raise
        yield ["--oauth-loopback", str(port), str(client.fileno())], (client.fileno(),)


def account_ready() -> bool:
    """核验当前角色的本机开发后端、官方程序和隔离能力。@return 是否可接受本机预留。"""
    try:
        oauth = managed_oauth_enabled()
        if oauth:
            if not file_oauth_enabled() or not direct_model_enabled():
                return False
            _check_direct_policy(_sender_config())
        elif _managed_policy_enabled() or direct_model_enabled():
            return False
        official_program()
        info = GUARD.stat()
        check = "--check-managed-policy" if oauth else "--check"
        if not _guard_usable((info.st_dev, info.st_ino, info.st_ctime_ns), check):
            return False
        if oauth:
            _loopback_broker()
            return True
        _, _, host, port = _loopback_provider()
        # Rust 的整个状态握手为一秒；探测本机监听器不投递推理请求。
        with create_connection((host, port), timeout=0.3):
            return True
    except (AttributeError, KeyError, OSError, TypeError, ValueError):
        return False


def session_paths(command: dict) -> tuple[Path, Path]:
    """取得原生会话的独立 HOME 和只读 Mod 目录。@param command sender 的已认领提交。@return 两个目录。"""
    native_id = command["workspace"]["native_session_id"]
    identifier = UUID(native_id)
    if identifier.version != 4 or str(identifier) != native_id:
        raise ValueError("账号交互进程需要已登记的原生会话 UUID")
    base = STORAGE / "tui-sessions"
    session = base / native_id
    home, mod = session / "home", session / "mod"
    for path in (base, session, home, mod, home / ".claude", home / "tmp"):
        private_directory(path)
    return home, mod


def file_oauth_enabled() -> bool:
    """报告受管事件源支持完整凭据文件。@return 是否启用账号模式。"""
    return managed_oauth_enabled()


def publish_oauth_file(config_dir: Path, snapshot: dict) -> bool:
    """按发放的同一账号快照原子更新官方文件。@param config_dir 会话配置目录。
    @param snapshot 已认证的本轮完整快照。@return 是否进行了实际写入。
    """
    if snapshot["expires_at"] <= time.time_ns() // 1_000_000:
        raise ValueError("V2 账号凭据已过期")
    oauth = dict(snapshot.get("profile", {"scopes": ["user:inference"]}))
    oauth.update({
        "accessToken": snapshot["access_token"], "refreshToken": snapshot["refresh_token"],
        "expiresAt": snapshot["expires_at"],
    })
    for source, target in (("subscription_type", "subscriptionType"), ("rate_limit_tier", "rateLimitTier")):
        if source in snapshot:
            oauth.setdefault(target, snapshot[source])
    document = {"claudeAiOauth": oauth}
    directory = directory_fd(config_dir)
    try:
        try:
            fd = os.open(_OAUTH_FILE_NAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            pass
        else:
            with os.fdopen(fd, "rb") as saved:
                info = os.fstat(saved.fileno())
                if not S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
                    raise ValueError("V2 凭据文件归属无效")
                if S_IMODE(info.st_mode) == 0o600 and info.st_size <= OAUTH_FILE_LIMIT:
                    try:
                        if json.load(saved) == document:
                            return False
                    except (ValueError, UnicodeError):
                        pass
    finally:
        os.close(directory)
    atomic_json(config_dir / _OAUTH_FILE_NAME, document)
    return True


def clear_oauth_file(config_dir: Path) -> None:
    """只清理当前会话的凭据文件及其原子写入残留。@param config_dir 私有会话目录。@return 无。"""
    try:
        directory = directory_fd(config_dir)
    except (FileNotFoundError, NotADirectoryError):
        return
    try:
        for name in os.listdir(directory):
            suffix = name.removeprefix(_OAUTH_FILE_NAME + ".")
            if name == _OAUTH_FILE_NAME or (name != suffix and len(suffix) == 32
                                           and all(c in "0123456789abcdef" for c in suffix)):
                with suppress(FileNotFoundError):
                    os.unlink(name, dir_fd=directory)
    finally:
        os.close(directory)


def purge_oauth_files() -> None:
    """持账号事件源独占锁回收异常退出的凭据。@return 无。"""
    root = STORAGE / "tui-sessions"
    try:
        directory = directory_fd(root)
    except FileNotFoundError:
        return
    try:
        for name in os.listdir(directory):
            try:
                identifier = UUID(name)
            except ValueError:
                continue
            if identifier.version == 4 and str(identifier) == name:
                clear_oauth_file(root / name / "home" / ".claude")
    finally:
        os.close(directory)


def _initialize_local_profile(config_dir: Path, work: Path) -> None:
    # 仅标记本次 sender 核验过的私有目录，登录材料由本轮凭据模式提供。
    path = config_dir / ".claude.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, "w") as stream:
        json.dump({"hasCompletedOnboarding": True, "lastOnboardingVersion": VERSION,
                   "projects": {str(work): {"hasTrustDialogAccepted": True}}}, stream)


def launch_session(
    reservation: dict, command: dict, *, arguments: list[str], config_dir: Path,
    environment: dict[str, str], resume: bool | None, terminal_fd: int, mod_dir: Path,
    model_endpoint: tuple[str, str] | None = None,
    oauth_file: bool = False,
    prepare_history=None,
    media_fd: int | None = None,
    recover_incomplete_history: bool = False,
    observation: WorkspaceLaunchObservation | None = None,
) -> Popen:
    """用账号内核限定工作区后，在真实 PTY 上运行固定版本。

    @param reservation sender 核验过的账号与会话预留。
    @param command 单次提交和已冻结的工作区。
    @param arguments 会话驱动选取的固定交互选项。
    @param config_dir 原生会话的私有配置目录。
    @param environment 驱动为子进程显式选择的环境。
    @param resume 是否读取同一绑定的原生历史；None 时按已验证记录决定。
    @param terminal_fd 驱动持有的 PTY 从端。
    @param mod_dir 只属于本原生会话的受信任 Mod 目录。
    @param model_endpoint 会话本机代理入口或隔离开发端点与口令。
    @param oauth_file 是否启用独占账号刷新与完整文件。
    @param prepare_history 可选，同一会话的外部历史导入函数。
    @param media_fd 可选，本会话私有图像暂存目录的 O_PATH 描述符。
    @param recover_incomplete_history 仅旧工具账本已核对原回执时，允许为缺少主轮的原档另开 CLI。
    @param observation 可选，本轮实际启动的会话来源。
    @return 直属交互进程，退出由账号执行器回收。
    """
    home, mod = session_paths(command)
    if config_dir != home / ".claude" or mod_dir != mod:
        raise ValueError("交互进程的配置或 Mod 不属于当前会话")
    managed_guard = []
    if managed_oauth_enabled():
        if not oauth_file:
            raise ValueError("Claude 托管策略需要本轮的完整账号凭据")
        config, _ = _bound_sender(reservation)
        if not direct_model_enabled():
            raise ValueError("受管账号需要已授权的 CLI 直发")
        _check_direct_policy(config)
        managed_guard = ["--managed-policy"]
        target = urlsplit(model_endpoint[0] if model_endpoint is not None else "")
        if (target.scheme != "http" or target.hostname != "127.0.0.1" or target.port is None
                or target.username is not None or target.password is not None):
            raise ValueError("完整凭据需要受信的本机代理入口")
        # 本机入口只承接 OAuth 控制和受管 CONNECT。模型 HTTPS 由 CLI 自身发起。
        proxy = f"http://127.0.0.1:{target.port}"
        url = ACCOUNT_ORIGIN
        auth = {
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "HTTP_PROXY": proxy, "HTTPS_PROXY": proxy, "NO_PROXY": "127.0.0.1,localhost",
            "FLOWER_TUI_DIRECT_BINDING": str(config_dir / "flower-direct.json"),
            "FLOWER_TUI_DIRECT_REQUIRED": "1",
        }
    else:
        if oauth_file or _managed_policy_enabled() or direct_model_enabled():
            raise ValueError("本机开发提供方不接受受管账号授权")
        url, bearer, _, _ = _loopback_provider()
        if model_endpoint is not None:
            url, bearer, _, _ = _loopback_endpoint(*model_endpoint)
        auth = {"ANTHROPIC_AUTH_TOKEN": bearer}
    with (_open_program() as (_, fd),
          _loopback_channel(target.port if oauth_file else None) as (network_guard, network_fds)):
        media_guard = [f"--media-fd={media_fd}"] if media_fd is not None else []
        media_fds = (media_fd,) if media_fd is not None else ()
        return launch_workspace_cli(
            reservation, command, program=GUARD,
            arguments=[*network_guard, *managed_guard, *media_guard, str(home), str(mod), f"/proc/self/fd/{fd}", *arguments],
            config_dir=config_dir, environment={
                **{k: environment[k] for k in ("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "MAX_THINKING_TOKENS",
                                               "CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING", "DISABLE_PROMPT_CACHING")
                   if k in environment},
                "HOME": str(home), "TMPDIR": str(home / "tmp"), "PATH": "/usr/bin:/bin",
                "SHELL": "/bin/bash", "LANG": "C.UTF-8", "TERM": "xterm-256color",
                "ANTHROPIC_BASE_URL": url, **auth,
            }, resume=resume, terminal_fd=terminal_fd, storage=STORAGE, program_fd=fd,
            inherited_fds=(*network_fds, *media_fds),
            initialize_profile=lambda work: _initialize_local_profile(config_dir, work),
            prepare_history=prepare_history, recover_incomplete_history=recover_incomplete_history,
            observation=observation,
        )
