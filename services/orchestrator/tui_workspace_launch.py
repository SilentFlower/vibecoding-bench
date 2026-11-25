"""账号 TUI 事件源依照本次发送器提交的绑定启动或恢复官方进程。"""

from contextlib import ExitStack
from collections.abc import Callable
from hashlib import sha256
import json
import os
from pathlib import Path
from stat import S_IMODE, S_ISREG
from subprocess import Popen
from uuid import UUID

from runtime_files import directory_fd


def _key(fields) -> str:
    # 与发送器相同的有序 JSON 元组，显式编码避免不同身份字段拼接成相同字符串。
    data = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode()
    return sha256(data).hexdigest()


def _owned_dir(stack: ExitStack, path: Path) -> int:
    fd = directory_fd(path)
    stack.callback(os.close, fd)
    info = os.fstat(fd)
    if info.st_uid != os.geteuid() or S_IMODE(info.st_mode) != 0o700:
        raise ValueError("V2 工作区目录的归属或权限不符")
    return fd


def _owned_file(directory: int, name: str):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    stream = os.fdopen(fd, "rb")
    info = os.fstat(fd)
    if (
        not S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or info.st_mode & 0o077
    ):
        stream.close()
        raise ValueError("V2 会话文件的归属或权限不符")
    return stream


def _resume_path(stack: ExitStack, config: Path, work: Path, native_id: str, required: bool):
    # 只对确实不存在的记录允许初次启动。链接、损坏记录和错误归属必须由原检查明确拒绝。
    project = config / "projects" / str(work).replace("/", "-")
    name = native_id + ".jsonl"
    try:
        directory = directory_fd(project)
        stack.callback(os.close, directory)
        stream = _owned_file(directory, name)
    except FileNotFoundError:
        if required:
            raise
        return None
    with stream:
        main = False
        for line in stream:
            row = json.loads(line)
            if row.get("type") in ("user", "assistant") and not row.get("isSidechain"):
                if row.get("sessionId") != native_id or row.get("cwd") != str(work):
                    raise ValueError("V2 恢复历史与当前会话工作区不匹配")
                main = True
        if not main:
            raise ValueError("V2 恢复历史缺少原生主轮")
    return project / name


def launch_workspace_cli(
    reservation: dict,
    command: dict,
    *,
    program: Path,
    arguments: list[str],
    config_dir: Path,
    environment: dict[str, str],
    resume: bool | None,
    terminal_fd: int,
    storage: Path = Path("/native"),
    program_fd: int | None = None,
    inherited_fds: tuple[int, ...] = (),
    initialize_profile: Callable[[Path], None] | None = None,
) -> Popen:
    """在该账号发送器绑定的目录启动交互 CLI，继承事件源已分配的 PTY。

    @param reservation 同一受信 socket 的 prepare 身份。
    @param command 同一预留的 send 指令，由事件源单次认领。
    @param program 账号角色已核对的官方 CLI 可执行文件。
    @param arguments 受信事件源提供的交互参数，启动和恢复选项由本函数追加。
    @param config_dir 账号在本角色中使用的官方配置目录。
    @param environment 账号角色已准备的环境。
    @param resume True 要求已登记历史，False 首次启动，None 在同一绑定已有历史时恢复。
    @param terminal_fd 事件源持有的 PTY 从端。
    @param storage sender 与事件源共用的受控账号卷。
    @param program_fd 可选的已核验程序描述符，由同容器隔离入口在执行时关闭。
    @param inherited_fds 受信启动器额外传入的同会话描述符。
    @param initialize_profile 可选，新会话由受信控制端为已核验目录初始化独立配置。
    @return 由事件源负责监督与回收的官方进程。
    """
    if (
        command.get("action") != "send"
        or command.get("reservation_id") != reservation["reservation_id"]
    ):
        raise ValueError("V2 提交与已准备预留不匹配")
    launch = command["workspace"]
    scope = (
        reservation["account_id"],
        reservation["environment_id"],
        reservation["principal_id"],
    )
    session = reservation["session_id"]
    key = _key((scope, session))
    base = storage / "tui-workspaces"
    path = base / (key + ".json")
    if launch["version"] != 1 or str(path) != launch["binding_file"]:
        raise ValueError("V2 提交绑定属于其他会话")
    with ExitStack() as stack:
        parent = _owned_dir(stack, base)
        with _owned_file(parent, path.name) as stream:
            record = json.load(stream)
        native_id = record["native_session_id"]
        if (
            record["session_key"] != key
            or native_id != launch["native_session_id"]
            or str(UUID(native_id)) != native_id
            or UUID(native_id).version != 4
        ):
            raise ValueError("V2 原生会话身份不匹配")
        client = record["client_path"]
        project = _key(
            (scope, "project", client)
            if client is not None
            else (scope, "session", session)
        )
        work = base / project
        if str(work) != launch["work_dir"]:
            raise ValueError("V2 提交工作目录不属于当前绑定")
        cwd = _owned_dir(stack, work)
        session_args = ["--session-id", native_id]
        history = None if resume is False else _resume_path(stack, config_dir, work, native_id, required=resume is True)
        if history is not None:
            session_args = ["--resume", str(history)]
        if initialize_profile is not None:
            # 节点迁移只复制对话；首次在目标恢复时按同一私有 cwd 重建本机信任配置。
            initialize_profile(work)
        # 真实 cwd 由已核验的目录描述符确定，Windows 和远程路径始终留在原始 Messages 正文中。
        descriptors = (cwd,) if program_fd is None else (cwd, program_fd)
        return Popen(
            ["/usr/bin/setsid", "--ctty", program, *arguments, *session_args],
            cwd=f"/proc/self/fd/{cwd}",
            pass_fds=(*descriptors, *inherited_fds),
            stdin=terminal_fd,
            stdout=terminal_fd,
            stderr=terminal_fd,
            env={**environment, "CLAUDE_CONFIG_DIR": str(config_dir)},
        )
