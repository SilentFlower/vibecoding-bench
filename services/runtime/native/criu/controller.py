"""每账号受信恢复控制器；控制面只接受本sender与已登记零业务模板。"""
import asyncio
from dataclasses import dataclass, field
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
from uuid import uuid4

from entropy import PROFILE
from protocol import command, freeze_tree, receive, send

ROOT = Path('/var/lib/ccrb-criu')
TOOLS = Path('/opt/ccrb-criu')


def process_identity(pid: int) -> tuple[int, str, dict]:
    """读取实际身份。@param pid 当前账号命名空间PID。@return 父PID、启动时刻、状态字段。"""
    root = Path('/proc', str(pid))
    fields = dict(line.split(':', 1) for line in (root / 'status').read_text().splitlines() if ':' in line)
    return int(fields['PPid']), (root / 'stat').read_text().rsplit(')', 1)[1].split()[19], fields


def restricted(fields: dict) -> bool:
    """校验业务身份。@param fields proc状态。@return 是否满足固定受限合同。"""
    return ([int(value) for value in fields['Uid'].split()] == [1001] * 4
            and all(int(fields[name], 16) == 0 for name in ('CapEff', 'CapPrm', 'CapInh', 'CapAmb'))
            and fields['NoNewPrivs'].strip() == '1' and fields['Seccomp'].strip() == '2')


def verify_image(pid: int, profile: dict) -> None:
    """校验实际封存执行体。@param pid 已持有进程。@param profile 构建冻结画像。@return 无。"""
    with open(f'/proc/{pid}/exe', 'rb') as source:
        if (os.fstat(source.fileno()).st_size != profile['image_bytes']
                or fcntl.fcntl(source, fcntl.F_GET_SEALS) & 15 != 15
                or hashlib.file_digest(source, 'sha256').hexdigest() != profile['image_sha256']):
            raise ValueError('RESTORE_IMAGE_IDENTITY')


@dataclass
class Template:
    """已冻结模板及在途引用。@param value 精确登记命令。@param root 私有目录。@param configuration 内部恢复参数。@param files 冻结文件身份及摘要。@param filesystem 原生目录权限与时间。"""
    value: dict
    root: Path
    configuration: dict
    files: dict
    filesystem: dict
    valid: bool = True
    users: int = 0
    drained: asyncio.Event = field(default_factory=asyncio.Event)


class Controller:
    """持有单账号模板与物理恢复实例，所有清理由同一事件循环负责。"""

    def __init__(self, sender: int, maximum: int, work_root: str, profile: dict):
        """绑定受信角色配置。@param sender 实际sender子PID。@param maximum 物理worker上限。@param work_root 固定种子根。@param profile 构建冻结画像。@return 无。"""
        self.sender = sender
        self.maximum = maximum
        self.work_root = Path(work_root)
        self.profile = profile
        self.templates = {}
        self.owners = {}
        self.active = 0
        self.clients = set()
        self.building = set()
        self.operations = {}
        self.cleaning = set()

    def authenticate(self, connection: socket.socket) -> None:
        """只受理直属sender自身。@param connection 系统鉴权连接。@return 无。"""
        pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if pid != self.sender or uid != 1001:
            raise ValueError('RESTORE_PEER_INVALID')

    async def run(self, arguments: list[str], timeout: float) -> None:
        """有界执行固定CRIU命令并等待真实退出。@param arguments 内部参数。@param timeout 秒预算。@return 无。"""
        process = await asyncio.create_subprocess_exec(str(TOOLS / 'criu'), '--no-default-config', *arguments,
            stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            if await asyncio.wait_for(process.wait(), timeout):
                raise ValueError('RESTORE_CRIU_FAILED')
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def template(self, value: dict, connection: socket.socket) -> None:
        """冻结本sender的零业务种子并维持模板租约。@param value 白名单登记。@param connection 存活租约。@return 无。"""
        identifier = value['template']
        if identifier in self.templates or identifier in self.building or self.templates or self.building:
            raise ValueError('RESTORE_TEMPLATE_BUSY')
        self.building.add(identifier)
        root = ROOT / 'templates' / identifier
        template = None
        pidfd = None
        created = False
        try:
            root.mkdir(mode=0o700)
            created = True
            pid = value['pid']
            pidfd = os.pidfd_open(pid)
            parent, started, status = process_identity(pid)
            if parent != self.sender or not restricted(status):
                raise ValueError('RESTORE_SEED_OWNERSHIP')
            environment = dict(entry.split(b'=', 1) for entry in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in entry)
            source = self.work_root / value['worker']
            if (environment.get(b'CCRB_TEMPLATE_ID') != identifier.encode()
                    or environment.get(b'CCRB_WORKER_ID') != value['worker'].encode()
                    or environment.get(b'HOME') != str(source / 'home').encode()
                    or environment.get(b'CLAUDE_CONFIG_DIR') != str(source / 'config').encode()
                    or Path(f'/proc/{pid}/cwd').resolve() != source / 'cwd'):
                raise ValueError('RESTORE_SEED_BINDING')
            verify_image(pid, self.profile)
            pipes = {str(fd): os.readlink(f'/proc/{pid}/fd/{fd}') for fd in (0, 1, 2)}
            if any(not name.startswith('pipe:[') or not name.endswith(']') for name in pipes.values()):
                raise ValueError('RESTORE_SEED_PIPES')
            (root / 'images').mkdir(mode=0o700)
            await self.run(['dump', '-t', str(pid), '-D', str(root / 'images'), '--shell-job', '--leave-running',
                            '-v2', '-o', str(root / 'dump.log')], 30)
            if process_identity(pid)[:2] != (parent, started):
                raise ValueError('RESTORE_SEED_EXITED')
            filesystem = freeze_tree(source, root / 'fs', 1001)
            for path in (root / 'images').iterdir():
                path.chmod(0o600)
            configuration = {'images': str(root / 'images'), 'work_root': str(self.work_root),
                'source_root': str(source), 'source_pid': pid,
                'source_max_pid': max(int(path.name) for path in Path(f'/proc/{pid}/task').iterdir()), 'pipes': pipes,
                'image_sha256': self.profile['image_sha256']}
            files = {}
            paths = [path for name in ('images', 'fs') for path in [root / name, *(root / name).rglob('*')]]
            for path in paths:
                info = path.stat()
                digest = None
                if path.is_file():
                    with path.open('rb') as content:
                        digest = hashlib.file_digest(content, 'sha256').hexdigest()
                files[str(path.relative_to(root))] = {'identity': (info.st_dev, info.st_ino, info.st_size, info.st_ctime_ns,
                    info.st_mtime_ns, info.st_mode, info.st_uid, info.st_nlink), 'sha256': digest}
            # 摘要在零业务冻结时生成；私有目录不可由sender改写，后续用含ctime的身份拒绝变化。
            (root / 'images-manifest.json').write_text(json.dumps(files, sort_keys=True))
            (root / 'images-manifest.json').chmod(0o600)
            template = Template(value, root, configuration, files, filesystem)
            template.drained.set()
            self.templates[identifier] = template
            await send(connection, {'protocol': 1, 'type': 'template_ready', 'template': identifier,
                                    'image': self.profile['image_sha256']})
            await asyncio.get_running_loop().sock_recv(connection, 1)
        finally:
            self.cleaning.add(asyncio.current_task())
            self.building.discard(identifier)
            if pidfd is not None:
                os.close(pidfd)
            if template:
                template.valid = False
                self.templates.pop(identifier, None)
                await template.drained.wait()
            if created:
                shutil.rmtree(root, ignore_errors=True)

    async def restore(self, value: dict, connection: socket.socket) -> None:
        """先移交存活句柄，再恢复单个物理实例。@param value 绑定元数据。@param connection 生命周期连接。@return 无。"""
        template = self.templates.get(value['template'])
        if (not template or not template.valid or value['key'] != template.value['key']
                or value['worker'] == template.value['worker'] or self.active >= self.maximum):
            raise ValueError('RESTORE_TEMPLATE_UNAVAILABLE')
        paths = [path for name in ('images', 'fs') for path in [template.root / name, *(template.root / name).rglob('*')]]
        if {str(path.relative_to(template.root)) for path in paths} != set(template.files):
            raise ValueError('RESTORE_TEMPLATE_CHANGED')
        for name, frozen in template.files.items():
            info = (template.root / name).lstat()
            actual = (info.st_dev, info.st_ino, info.st_size, info.st_ctime_ns,
                      info.st_mtime_ns, info.st_mode, info.st_uid, info.st_nlink)
            if actual != frozen['identity']:
                raise ValueError('RESTORE_TEMPLATE_CHANGED')
        template.users += 1
        template.drained.clear()
        self.active += 1
        root = ROOT / 'instances' / str(uuid4())
        process = None
        namespace_fd = None
        namespace = None
        pid = None
        descriptors = []
        tasks = []
        created = False
        try:
            root.mkdir(mode=0o700)
            created = True
            freeze_tree(template.root / 'fs', root / 'fs', 0)
            for relative, metadata in template.filesystem.items():
                path = root / 'fs' / relative
                os.chmod(path, metadata['mode'])
                os.utime(path, ns=(metadata['atime_ns'], metadata['mtime_ns']))
                os.chown(path, 1001, metadata['gid'])
            (root / 'config.json').write_text(json.dumps(template.configuration))
            os.chmod(root / 'config.json', 0o600)
            gate_r, gate_w = os.pipe2(os.O_CLOEXEC)
            report_r, report_w = os.pipe2(os.O_CLOEXEC)
            incoming_r, incoming_w = os.pipe2(os.O_CLOEXEC)
            outgoing_r, outgoing_w = os.pipe2(os.O_CLOEXEC)
            errors_r, errors_w = os.pipe2(os.O_CLOEXEC)
            descriptors.extend((gate_r, gate_w, report_r, report_w, incoming_r, incoming_w, outgoing_r, outgoing_w, errors_r, errors_w))
            inherited = (gate_r, report_w, incoming_r, outgoing_w, errors_w)
            with (root / 'namespace.log').open('xb') as private_log:
                os.chmod(root / 'namespace.log', 0o600)
                process = await asyncio.create_subprocess_exec(str(TOOLS / 'launch'), 'namespace', root.name,
                    *[str(fd) for fd in inherited], pass_fds=inherited, stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.PIPE, stderr=private_log)
            for descriptor in inherited:
                os.close(descriptor)
                descriptors.remove(descriptor)
            namespace = int(await asyncio.wait_for(process.stdout.readline(), 2))
            parent, started, status = process_identity(namespace)
            if parent != process.pid or status['NSpid'].split()[-1] != '1':
                raise ValueError('RESTORE_NAMESPACE_OWNERSHIP')
            namespace_fd = os.pidfd_open(namespace)
            await send(connection, {'protocol': 1, 'type': 'namespace_ready', 'pid': namespace, 'started': started}, (namespace_fd,))
            if await asyncio.wait_for(receive(connection), 2) != {'type': 'start'}:
                raise ValueError('RESTORE_START_ACK')
            if not template.valid:
                raise ValueError('RESTORE_TEMPLATE_EXPIRED')
            os.write(gate_w, b'S')
            disconnected = asyncio.create_task(asyncio.get_running_loop().sock_recv(connection, 1))
            tasks.append(disconnected)
            # 非阻塞读取管道，让取消和控制连接断开都能及时收口。
            async def read_pipe(descriptor: int, limit: int) -> bytes:
                """通过事件循环读取管道。@param descriptor 内部只读FD。@param limit 字节上限。@return 完整内容。"""
                reader = asyncio.StreamReader(limit=limit)
                protocol = asyncio.StreamReaderProtocol(reader)
                transport, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, os.fdopen(os.dup(descriptor), 'rb', buffering=0))
                try:
                    return await reader.read(limit)
                finally:
                    transport.close()

            async def drain_errors() -> None:
                """持续丢弃原生stderr，避免克隆管道阻塞。@return 无。"""
                while await read_pipe(errors_r, 65536):
                    pass

            tasks.append(asyncio.create_task(drain_errors()))
            reporting = asyncio.create_task(asyncio.wait_for(read_pipe(report_r, 4096), 35))
            tasks.append(reporting)
            completed, _ = await asyncio.wait((reporting, disconnected), return_when=asyncio.FIRST_COMPLETED)
            if disconnected in completed:
                raise ValueError('RESTORE_CONNECTION_CLOSED')
            report = json.loads(reporting.result())
            inner = report['inner_pid']
            children = Path(f'/proc/{namespace}/task/{namespace}/children').read_text().split()
            candidates = [int(child) for child in children if process_identity(int(child))[2]['NSpid'].split()[-1] == str(inner)]
            if len(candidates) != 1 or report['entropy'].get('profile') != PROFILE:
                raise ValueError('RESTORE_WORKER_OWNERSHIP')
            pid = candidates[0]
            parent, started, status = process_identity(pid)
            if parent != namespace or not restricted(status):
                raise ValueError('RESTORE_WORKER_OWNERSHIP')
            worker_fd = os.pidfd_open(pid)
            descriptors.append(worker_fd)
            self.owners[pid] = {'owner': namespace, 'started': started, 'worker': value['worker'],
                                'image': self.profile['image_sha256']}
            await send(connection, {'protocol': 1, 'type': 'restore_ready', 'pid': pid, 'parent': namespace,
                'inner_pid': inner, 'started': started, 'template': value['template'],
                'seed_worker': template.value['worker'], 'worker': value['worker'], 'nonce': value['nonce'],
                'image': self.profile['image_sha256'], 'entropy_profile': PROFILE}, (incoming_w, outgoing_r, worker_fd))
            exited = asyncio.create_task(process.wait())
            tasks.append(exited)
            await asyncio.wait((exited, disconnected), return_when=asyncio.FIRST_COMPLETED)
        finally:
            self.cleaning.add(asyncio.current_task())
            if namespace_fd is not None:
                try:
                    signal.pidfd_send_signal(namespace_fd, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process:
                if namespace_fd is None and process.returncode is None:
                    process.kill()
                await process.wait()
                await process.communicate()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if pid is not None:
                self.owners.pop(pid, None)
            for descriptor in descriptors:
                os.close(descriptor)
            if namespace_fd is not None:
                os.close(namespace_fd)
            if created:
                shutil.rmtree(root, ignore_errors=True)
            self.active -= 1
            template.users -= 1
            if not template.users:
                template.drained.set()

    async def handle(self, connection: socket.socket) -> None:
        """执行一次受控操作并持有租约。@param connection 已接受的私有连接。@return 无。"""
        self.clients.add(asyncio.current_task())
        pending = None
        try:
            self.authenticate(connection)
            value = command(await asyncio.wait_for(receive(connection), 2))
            operation = self.template if value['type'] == 'template' else self.restore
            pending = asyncio.create_task(operation(value, connection))
            self.operations[asyncio.current_task()] = pending
            # 初始阶段失败或客户端主动关闭时，operation自己的finally负责真实退出。
            try:
                await pending
            finally:
                if not pending.done():
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
        except (OSError, ValueError, KeyError, TypeError, asyncio.TimeoutError) as error:
            reasons = {'RESTORE_TEMPLATE_BUSY', 'RESTORE_SEED_OWNERSHIP', 'RESTORE_SEED_BINDING',
                'RESTORE_IMAGE_IDENTITY', 'RESTORE_SEED_PIPES', 'RESTORE_CRIU_FAILED', 'RESTORE_SEED_EXITED',
                'RESTORE_TEMPLATE_UNAVAILABLE', 'RESTORE_NAMESPACE_OWNERSHIP', 'RESTORE_START_ACK',
                'RESTORE_TEMPLATE_EXPIRED', 'RESTORE_CONNECTION_CLOSED', 'RESTORE_WORKER_OWNERSHIP',
                'RESTORE_TEMPLATE_CHANGED',
                'RESTORE_PEER_INVALID', 'RESTORE_COMMAND_INVALID', 'RESTORE_COMMAND_LIMIT'}
            reason = str(error) if type(error) is ValueError and str(error) in reasons else 'RESTORE_OPERATION_FAILED'
            print(json.dumps({'layer': 'criu_controller', 'reason': reason}), flush=True)
        finally:
            connection.close()
            self.clients.discard(asyncio.current_task())
            self.operations.pop(asyncio.current_task(), None)
            self.cleaning.discard(pending)

    async def serve(self, listener: socket.socket) -> None:
        """接受有界账号连接。@param listener 私有监听器。@return 无。"""
        loop = asyncio.get_running_loop()
        while True:
            connection, _ = await loop.sock_accept(listener)
            if len(self.clients) >= self.maximum + 4:
                connection.close()
                continue
            asyncio.create_task(self.handle(connection))

    async def close(self) -> None:
        """撤销全部模板和恢复实例，并等待清理。@return 无。"""
        tasks = list(self.clients)
        for task in tasks:
            # 正在等待真实退出的finally必须完成；只有尚未收口的操作需要首次撤销。
            if self.operations.get(task) not in self.cleaning:
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
