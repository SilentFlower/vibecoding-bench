"""恢复同一 AGY 内核持有的零业务快照，根权限仅用于固定进程树。"""
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import tempfile
import time

from controller import process_identity, restricted
from protocol import receive, send

CONTROL = Path('/run/ccrb-criu/agy.sock')
AGY = Path('/usr/local/bin/agy-1.5.9')
OBSERVER = Path('/opt/v3/python/agy_runtime/resources/observer-c')
SOURCE_SHA = '39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43'


def same_executable(pid: int, executable: Path) -> None:
    """核对根所有的执行映像与实际进程 inode。@param pid 已绑定进程。@param executable 固定镜像文件。@return 无。"""
    info = executable.stat()
    actual = Path(f'/proc/{pid}/exe').stat()
    if info.st_uid or info.st_mode & 0o022 or (info.st_dev, info.st_ino) != (actual.st_dev, actual.st_ino):
        raise ValueError('AGY_CRIU_IMAGE')


class AgyController:
    """持有同一账号的单份模板和已恢复进程租约。"""

    def __init__(self, sender: int, root: Path, criu: Path):
        """绑定账号根及固定工具。@param sender 真实发送器。@param root 私有数据根。@param criu 固定工具路径。@return 无。"""
        self.sender = sender
        self.root = root
        self.criu = criu
        self.clients = set()
        self.template = asyncio.Lock()

    def validate(self, connection: socket.socket, value: dict) -> tuple[int, int, int]:
        """核对请求者和两级进程归属。@param connection 业务内核连接。@param value 快照请求。@return 内核、观察器、原生 PID。"""
        peer = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        kernel, uid, _gid = struct.unpack('3i', peer)
        if uid != 1001 or set(value) != {'type', 'observer', 'native'} or value['type'] != 'template':
            raise ValueError('AGY_CRIU_PEER')
        observer, native = value['observer'], value['native']
        if any(type(pid) is not int or not 1 < pid < 2**31 for pid in (observer, native)):
            raise ValueError('AGY_CRIU_PID')
        supervisor, _, kernel_fields = process_identity(kernel)
        parent, _, supervisor_fields = process_identity(supervisor)
        for pid, expected_parent in ((observer, kernel), (native, observer)):
            actual_parent, _, fields = process_identity(pid)
            if actual_parent != expected_parent or not restricted(fields):
                raise ValueError('AGY_CRIU_OWNER')
        if (parent != self.sender or not restricted(kernel_fields) or not restricted(supervisor_fields)
                or b'agy_runtime.kernel' not in Path(f'/proc/{kernel}/cmdline').read_bytes().split(b'\0')
                or b'agy_runtime.supervisor' not in Path(f'/proc/{supervisor}/cmdline').read_bytes().split(b'\0')
                or b'AGY_CRIU_TEMPLATE=1' not in Path(f'/proc/{kernel}/environ').read_bytes().split(b'\0')):
            raise ValueError('AGY_CRIU_OWNER')
        same_executable(observer, OBSERVER)
        same_executable(native, AGY)
        with AGY.open('rb') as executable:
            if hashlib.file_digest(executable, 'sha256').hexdigest() != SOURCE_SHA:
                raise ValueError('AGY_CRIU_IMAGE')
        return kernel, observer, native

    async def run(self, stage: str, root: Path, arguments: list, descriptors: tuple = ()) -> int:
        """只执行固定工具。@param stage dump或restore。@param root 单次模板。@param arguments 内部参数。@param descriptors 保留的输出管道。@return 实测毫秒。"""
        start = time.monotonic()
        # 启动探测可能留下代理连接。模板阶段没有模型业务，恢复后由原生客户端重新连接。
        process = await asyncio.create_subprocess_exec(str(self.criu), '--no-default-config', stage,
            '--images-dir', str(root), '--shell-job', '--file-locks', '--tcp-close', '--log-file', str(root / f'{stage}.log'),
            *arguments, pass_fds=descriptors, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            if await asyncio.wait_for(process.wait(), 25):
                raise ValueError(f'AGY_CRIU_{stage.upper()}')
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        return round((time.monotonic() - start) * 1000)

    async def handle(self, connection: socket.socket) -> None:
        """完成模板登记、单次恢复及真实退出。@param connection 专属内核租约。@return 无。"""
        task = asyncio.current_task()
        self.clients.add(task)
        try:
            if self.template.locked():
                return
            async with self.template:
                value = await asyncio.wait_for(receive(connection), 2)
                kernel, observer, native = await asyncio.to_thread(self.validate, connection, value)
                await self.transaction(connection, kernel, observer, native)
        except (ValueError, OSError, TimeoutError, KeyError, TypeError) as error:
            if str(error) == 'RESTORE_CONNECTION_CLOSED':
                return
            reason = str(error) if type(error) is ValueError and str(error).startswith('AGY_CRIU_') else 'AGY_CRIU_UNAVAILABLE'
            print(json.dumps({'layer': 'agy_criu_controller', 'reason': reason}), flush=True)
            try:
                await send(connection, {'type': 'unavailable', 'reason': reason})
            except OSError:
                # 内核可能已沿请求截止关闭租约。
                pass
        finally:
            connection.close()
            self.clients.discard(task)

    async def transaction(self, connection: socket.socket, kernel: int, observer: int, native: int) -> None:
        """保留事件FD，恢复后继续同一个观察器。@param connection 内核连接。@param kernel 原私有进程。@param observer 观察器。@param native 原生进程。@return 无。"""
        pipes = {}
        source_fd = os.pidfd_open(observer)
        restored = None
        restored_fd = None
        try:
            for path in Path(f'/proc/{observer}/fd').iterdir():
                target = os.readlink(path)
                if target.startswith('pipe:') and target not in pipes:
                    descriptor = os.open(path, os.O_WRONLY | os.O_CLOEXEC)
                    if (fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE) != os.O_WRONLY:
                        os.close(descriptor)
                        raise ValueError('AGY_CRIU_PIPES')
                    pipes[target] = descriptor
            if len(pipes) != 2:
                raise ValueError('AGY_CRIU_PIPES')
            with tempfile.TemporaryDirectory(prefix='agy-', dir=self.root) as temporary:
                root = Path(temporary)
                await send(connection, {'type': 'accepted'})
                if await asyncio.wait_for(receive(connection), 4) != {'type': 'dump'}:
                    raise ValueError('AGY_CRIU_SEQUENCE')
                states = [process_identity(int(task.name))[2] for task in Path(f'/proc/{native}/task').iterdir()]
                if (not states or select.select([source_fd], [], [], 0)[0] or process_identity(observer)[0] != kernel
                        or process_identity(native)[0] != observer
                        or any(fields['State'].split()[0] != 'T' or int(fields['TracerPid']) for fields in states)):
                    raise ValueError('AGY_CRIU_STOP')
                dump_ms = await self.run('dump', root, ['--tree', str(observer)])
                await send(connection, {'type': 'template_ready', 'dump_ms': dump_ms})
                if await receive(connection) != {'type': 'restore'}:
                    raise ValueError('AGY_CRIU_SEQUENCE')
                pidfile = root / 'restored.pid'
                arguments = ['--leave-stopped', '--restore-detached', '--restore-sibling', '--pidfile', str(pidfile)]
                for name, descriptor in pipes.items():
                    arguments.extend(['--inherit-fd', f'fd[{descriptor}]:{name}'])
                try:
                    restore_ms = await self.run('restore', root, arguments, tuple(pipes.values()))
                finally:
                    if pidfile.is_file():
                        restored = int(pidfile.read_text())
                        restored_fd = os.pidfd_open(restored)
                if restored != observer or process_identity(native)[0] != observer:
                    raise ValueError('AGY_CRIU_OWNER')
                same_executable(observer, OBSERVER)
                same_executable(native, AGY)
                if not restricted(process_identity(observer)[2]) or not restricted(process_identity(native)[2]):
                    raise ValueError('AGY_CRIU_OWNER')
            # 原管道保留到恢复成功。后续由恢复进程自身持有写端。
            for descriptor in pipes.values():
                os.close(descriptor)
            pipes.clear()
            await send(connection, {'type': 'restored', 'observer': observer, 'native': native, 'restore_ms': restore_ms})
            await asyncio.get_running_loop().sock_recv(connection, 1)
        finally:
            if restored_fd is not None:
                try:
                    signal.pidfd_send_signal(restored_fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                while not select.select([restored_fd], [], [], 0)[0]:
                    await asyncio.sleep(.01)
                os.close(restored_fd)
                try:
                    os.waitpid(restored, os.WNOHANG)
                except ChildProcessError:
                    pass
            os.close(source_fd)
            for descriptor in pipes.values():
                os.close(descriptor)

    async def serve(self, listener: socket.socket) -> None:
        """监听账号内私有入口。@param listener 已限制权限的端点。@return 无。"""
        while True:
            connection, _ = await asyncio.get_running_loop().sock_accept(listener)
            asyncio.create_task(self.handle(connection))

    async def close(self) -> None:
        """关闭全部租约，等待恢复进程退出。@return 无。"""
        pending = list(self.clients)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
