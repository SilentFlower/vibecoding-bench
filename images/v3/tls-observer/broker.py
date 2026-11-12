#!/usr/local/bin/python3
"""每账号固定加载器；私有socket只受理直属sender的真实worker。"""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
from uuid import UUID

from observer import IMAGE_SHA256, ADMITTED_IMAGES

ROOT = Path('/opt/ccrb-tls-observer')
SOCKET = Path('/run/ccrb-observer/control.sock')


def identity(pid: int) -> tuple[int, int, str]:
    """读取实际父进程、UID及启动时刻。@param pid 本命名空间PID。@return 归属三元组。"""
    status = dict(line.split(':', 1) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)
    started = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    return int(status['PPid']), int(status['Uid'].split()[0]), started


def validate(value: dict, peer: int, sender: int, owners: dict | None = None) -> str:
    """核对固定协议和本sender直属进程。@param value 请求。@param peer 真实客户端。@param sender 权威父PID。@return 目标启动时刻。"""
    if (not isinstance(value, dict) or set(value) != {'pid', 'worker', 'capture', 'image'}
            or type(value['pid']) is not int or value['pid'] < 2 or value['image'] not in ADMITTED_IMAGES):
        raise ValueError('OBSERVER_COMMAND_INVALID')
    for key in ('worker', 'capture'):
        if not isinstance(value[key], str) or str(UUID(value[key])) != value[key]:
            raise ValueError('OBSERVER_COMMAND_INVALID')
    if identity(peer)[:2] != (sender, 1001):
        raise ValueError('WORKER_OWNERSHIP')
    registered = owners.get(value['pid']) if owners is not None else None
    target = identity(value['pid'])
    if registered:
        if (target != (registered['owner'], 1001, registered['started'])
                or registered['worker'] != value['worker'] or registered['image'] != value['image']):
            raise ValueError('WORKER_OWNERSHIP')
    elif target[:2] != (sender, 1001):
        raise ValueError('WORKER_OWNERSHIP')
    return identity(value['pid'])[2]


class Broker:
    """持有本账号sender和有界的单worker采集代次。"""

    def __init__(self, sender: int, maximum: int, owners: dict | None = None):
        """绑定权威sender。@param sender 实际子进程。@param maximum 配置worker上限。@return None。"""
        self.sender = sender
        self.owners = owners
        self.maximum = maximum
        self.active = set()
        self.clients = 0
        self.tasks = set()
        self.cleaning = set()

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """受理单次私有采集，断开时释放。@param reader 客户端。@param writer 私有结果。@return None。"""
        process = None
        target_fd = None
        target = None
        admitted = False
        tasks = []
        self.clients += 1
        self.tasks.add(asyncio.current_task())
        try:
            peer, uid, _ = struct.unpack('3i', writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != 1001 or self.clients > self.maximum:
                return
            raw = await asyncio.wait_for(reader.readline(), 2)
            if len(raw) > 4096 or not raw.endswith(b'\n'):
                return
            value = json.loads(raw)
            started = validate(value, peer, self.sender, self.owners)
            target = value['pid']
            if target in self.active or len(self.active) >= self.maximum:
                return
            target_fd = os.pidfd_open(target)
            if identity(target)[2] != started:
                return
            self.active.add(target)
            admitted = True
            registered = self.owners.get(target) if self.owners is not None else None
            owner = registered['owner'] if registered else self.sender
            process = await asyncio.create_subprocess_exec(str(ROOT / 'launch'), 'observer',
                '--pid', str(target), '--worker', value['worker'], '--capture', value['capture'],
                '--image', value['image'], '--owner', str(owner), '--started', started,
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                env={'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8'})

            async def command():
                line = await reader.readline()
                if len(line) > 4096 or not line.endswith(b'\n'):
                    return
                # 收口只转发一条命令；observer继续核对capture_id和实际请求头归属。
                process.stdin.write(line)
                await process.stdin.drain()
                await reader.read(1)

            async def result():
                total = 0
                while True:
                    data = await process.stdout.read(65536)
                    if not data:
                        return
                    total += len(data)
                    if total > 6 * 1024 * 1024:
                        return
                    writer.write(data)
                    await asyncio.wait_for(writer.drain(), 2)

            async def alive():
                while not select.select([target_fd], [], [], 0)[0]:
                    await asyncio.sleep(0.1)

            tasks = [asyncio.create_task(action()) for action in (command, result, alive)]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except (OSError, ValueError, KeyError, TypeError, asyncio.TimeoutError):
            pass
        finally:
            self.cleaning.add(asyncio.current_task())
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if process:
                # 固定C监督进程在EOF时以同UID回收观察器，清理不再依赖帮助进程pidfd分配。
                process.stdin.close()
                try:
                    await asyncio.wait_for(process.communicate(), 2)
                except asyncio.TimeoutError:
                    pass
            if target_fd is not None:
                os.close(target_fd)
            if admitted:
                self.active.discard(target)
            self.clients -= 1
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), .25)
            except (OSError, asyncio.TimeoutError):
                # 放弃读取的客户端不能让尾部缓冲拖住连接资源回收。
                writer.transport.abort()
            self.tasks.discard(asyncio.current_task())
            self.cleaning.discard(asyncio.current_task())

    async def close(self) -> None:
        """撤销全部在途采集并等待其监督进程收口。@return 无。"""
        tasks = list(self.tasks)
        for task in tasks:
            # EOF可能已进入清理；再次取消会截断communicate，留下尚未关闭的子进程管道。
            if task not in self.cleaning:
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> None:
    """启动固定业务子进程及受限加载服务，退出时整体收口。@return None。"""
    if os.getuid() != 0:
        raise SystemExit('受限加载器需要可信容器入口')
    # 预先选择业务组，socket归属无需额外授予CHOWN能力。
    os.setgid(1001)
    libc = ctypes.CDLL(None)
    if libc.prctl(4, 0, 0, 0, 0) or libc.prctl(38, 1, 0, 0, 0):
        raise SystemExit('加载器权限初始化失败')
    config = json.loads(Path('/run/v3/sender.json').read_text())
    maximum = config.get('native', {}).get('max_workers', 1)
    if type(maximum) is not int or maximum < 1:
        raise SystemExit('原生进程预算无效')
    # 只限制诊断资源，业务原生池继续采用原配置并发。
    maximum = min(maximum, 64)
    SOCKET.parent.mkdir(mode=0o750, exist_ok=True)
    os.chown(SOCKET.parent, 0, 1001)
    SOCKET.unlink(missing_ok=True)
    sender = await asyncio.create_subprocess_exec(str(ROOT / 'launch'), 'sender')
    sender_fd = os.pidfd_open(sender.pid)
    broker = Broker(sender.pid, maximum)
    server = await asyncio.start_unix_server(broker.handle, str(SOCKET), limit=4096)
    os.chown(SOCKET, 0, 1001)
    SOCKET.chmod(0o660)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    stopped = asyncio.create_task(stop.wait())
    exited = asyncio.create_task(sender.wait())
    try:
        await asyncio.wait([stopped, exited], return_when=asyncio.FIRST_COMPLETED)
    finally:
        server.close()
        await server.wait_closed()
        await broker.close()
        if sender.returncode is None:
            stopper = await asyncio.create_subprocess_exec(str(ROOT / 'launch'), 'stop', str(sender_fd), pass_fds=(sender_fd,))
            await stopper.wait()
            try:
                await asyncio.wait_for(sender.wait(), 3)
            except asyncio.TimeoutError:
                raise RuntimeError('业务进程收口失败') from None
        stopped.cancel()
        SOCKET.unlink(missing_ok=True)
        os.close(sender_fd)
    if exited.done() and sender.returncode:
        raise SystemExit(sender.returncode)


if __name__ == '__main__':
    asyncio.run(main())
