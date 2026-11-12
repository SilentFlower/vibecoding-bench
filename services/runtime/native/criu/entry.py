"""显式启用的账号可信入口，同时持有恢复与TLS观测登记。"""
import asyncio
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import sys

from controller import Controller, ROOT, TOOLS

CONTROL = Path('/run/ccrb-criu/control.sock')


def socket_directory(path: Path) -> None:
    """建立sender可遍历的固定控制目录。@param path 内部固定socket父目录。@return 无。"""
    path.mkdir(mode=0o750, exist_ok=True)
    os.chown(path, 0, 1001)
    # 快照使用umask077；控制目录仍须显式保留业务组的遍历权限。
    path.chmod(0o750)


def dispatcher() -> dict:
    """先核验普通回退也依赖的降权入口与业务过滤器。@return 受信构建画像。"""
    profile_path = TOOLS / 'profile.json'
    info = profile_path.stat()
    if info.st_uid or info.st_mode & 0o022:
        raise ValueError('RESTORE_PROFILE_OWNERSHIP')
    profile = json.loads(profile_path.read_text())
    for name in ('launch', 'business-seccomp.bpf'):
        path = TOOLS / name
        info = path.stat()
        with path.open('rb') as content:
            if (info.st_uid or info.st_mode & 0o022
                    or hashlib.file_digest(content, 'sha256').hexdigest() != profile['files'][name]):
                raise ValueError('RESTORE_DISPATCHER_IDENTITY')
    return profile


def preflight(profile: dict) -> dict:
    """核对实际控制器安全上下文和恢复制品。@param profile 已核验降权入口的画像。@return 可用于恢复的固定画像。"""
    status = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    required = sum(1 << value for value in (0, 1, 3, 5, 6, 7, 8, 12, 18, 19, 21, 24, 25))
    if (os.getuid() or status['Seccomp'].strip() != '0'
            or int(status['CapEff'], 16) & required != required):
        raise ValueError('RESTORE_PRIVILEGE_UNAVAILABLE')
    if (profile['protocol'] != 1 or profile['entropy_profile'] != 'bun143-wipeonfork-v1'
            or profile['criu']['source_version'] != '4.2' or profile['criu']['memfd_executable_restore'] != 1):
        raise ValueError('RESTORE_PROFILE_INVALID')
    for name, digest in profile['files'].items():
        if Path(name).name != name:
            raise ValueError('RESTORE_PROFILE_INVALID')
        path = TOOLS / name
        info = path.stat()
        with path.open('rb') as content:
            if info.st_uid or info.st_mode & 0o022 or hashlib.file_digest(content, 'sha256').hexdigest() != digest:
                raise ValueError('RESTORE_TOOL_IDENTITY')
    return profile


async def main() -> None:
    """启动受限sender，受控退出时等所有实际角色收口。@return 无。"""
    if os.getuid() != 0:
        raise SystemExit('恢复入口身份无效')
    os.umask(0o077)
    os.setgid(1001)
    libc = ctypes.CDLL(None)
    if libc.prctl(4, 0, 0, 0, 0) or libc.prctl(38, 1, 0, 0, 0):
        raise SystemExit('恢复入口权限初始化失败')
    # 恢复工具会读取账号内存；禁用继承链的core文件，保持其与私有快照相同的保密边界。
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    configuration = json.loads(Path('/run/v3/sender.json').read_text())
    native = configuration['native']
    maximum = native['max_workers']
    if type(maximum) is not int or not 1 <= maximum <= 4096:
        raise SystemExit('原生物理预算无效')
    profile = None
    trusted = dispatcher()
    try:
        profile = preflight(trusted)
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({'layer': 'criu_controller', 'state': 'unavailable',
                          'reason': 'RESTORE_PREFLIGHT_FAILED'}), flush=True)
    for name in ('templates', 'instances'):
        directory = ROOT / name
        if directory.exists():
            # 账号sender容器为唯一挂载所有者；崩溃遗留只在新角色启动前清理。
            import shutil
            shutil.rmtree(directory)
        directory.mkdir(mode=0o700, parents=True)
    ROOT.chmod(0o700)
    environment = dict(os.environ)
    environment['CCRB_CRIU'] = '1' if profile else '0'
    sender = await asyncio.create_subprocess_exec(str(TOOLS / 'launch'), 'sender', env=environment)
    sender_fd = os.pidfd_open(sender.pid)
    controller = Controller(sender.pid, maximum, native['work_root'], profile) if profile else None
    listener = None
    serving = None
    observer_server = None
    broker = None
    if controller:
        socket_directory(CONTROL.parent)
        CONTROL.unlink(missing_ok=True)
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(str(CONTROL))
        listener.listen(min(maximum + 4, 128))
        listener.setblocking(False)
        os.chown(CONTROL, 0, 1001)
        CONTROL.chmod(0o660)
        serving = asyncio.create_task(controller.serve(listener))
    if environment.get('CCRB_TLS_OBSERVER'):
        sys.path.insert(0, '/opt/ccrb-tls-observer')
        from broker import Broker, SOCKET
        socket_directory(SOCKET.parent)
        SOCKET.unlink(missing_ok=True)
        broker = Broker(sender.pid, min(maximum, 64), controller.owners if controller else None)
        observer_server = await asyncio.start_unix_server(broker.handle, str(SOCKET), limit=4096)
        os.chown(SOCKET, 0, 1001)
        SOCKET.chmod(0o660)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(number, stopped.set)
    pending = [asyncio.create_task(sender.wait()), asyncio.create_task(stopped.wait())]
    business_exited = False
    try:
        completed, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        business_exited = pending[0] in completed
    finally:
        if serving:
            serving.cancel()
            await asyncio.gather(serving, return_exceptions=True)
        if listener:
            listener.close()
            CONTROL.unlink(missing_ok=True)
        if observer_server:
            observer_server.close()
            await observer_server.wait_closed()
            await broker.close()
        if controller:
            await controller.close()
        if sender.returncode is None:
            stopper = await asyncio.create_subprocess_exec('/opt/ccrb-tls-observer/launch', 'stop', str(sender_fd), pass_fds=(sender_fd,))
            await stopper.wait()
            await sender.wait()
        os.close(sender_fd)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    if business_exited and sender.returncode:
        raise SystemExit(sender.returncode)


if __name__ == '__main__':
    asyncio.run(main())
