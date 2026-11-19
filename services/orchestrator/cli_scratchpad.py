"""账号 CLI 临时文件的私有磁盘挂载与旧内存盘保全。"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import shutil
import tarfile
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from stat import S_ISREG
from threading import Lock

from docker.errors import DockerException, NotFound
from docker.types import Mount

from runtime_files import atomic_json, directory_fd
from storage_maintenance import preserve_metadata, read_storage_json, tree_inventory


SCRATCHPAD_TARGET = '/tmp/claude-1000'
SCRATCHPAD_STORE = 'cli-scratchpad'
SCRATCHPAD_RUNTIME = 'runtime/scratchpad-mount'
_PROTOCOL = 1
_ARCHIVE_LIMIT = 512 * 1024 * 1024
_ENTRY_LIMIT = 100000
_SUPPORTED_FILESYSTEMS = set()
_CAPABILITY_LOCK = Lock()
_EXPORT = r'''
import signal
import sys
import tarfile

signal.alarm(45)
root = Path('/tmp/claude-1000')
try:
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
except FileNotFoundError:
    with tarfile.open(fileobj=sys.stdout.buffer, mode='w|') as output:
        header = tarfile.TarInfo('claude-1000')
        header.type, header.mode, header.uid, header.gid = tarfile.DIRTYPE, 0o700, 1000, 1000
        output.addfile(header)
    if root.exists() or root.is_symlink():
        raise ValueError('临时目录在导出期间出现')
else:
    try:
        before = tree_inventory(root, entry_limit=100000)
        links = {}
        with tarfile.open(fileobj=sys.stdout.buffer, mode='w|', format=tarfile.PAX_FORMAT) as output:
            for name, item in sorted(before.items()):
                parent, leaf = (os.dup(root_fd), '.') if name == '.' else _parent(root_fd, name)
                try:
                    metadata = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
                    header = tarfile.TarInfo('claude-1000' + ('' if name == '.' else '/' + name))
                    header.mode, header.uid, header.gid, header.mtime = item['mode'], item['uid'], item['gid'], metadata.st_mtime
                    if item['kind'] == 'directory':
                        if not S_ISDIR(metadata.st_mode):
                            raise ValueError('临时目录类型变化')
                        header.type = tarfile.DIRTYPE
                        output.addfile(header)
                    elif item['kind'] == 'symlink':
                        if not S_ISLNK(metadata.st_mode):
                            raise ValueError('临时链接类型变化')
                        header.type, header.linkname = tarfile.SYMTYPE, item['target']
                        output.addfile(header)
                    else:
                        descriptor = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                        with os.fdopen(descriptor, 'rb') as source:
                            actual = os.fstat(source.fileno())
                            if not S_ISREG(actual.st_mode) or _identity(actual) != _identity(metadata):
                                raise ValueError('临时文件类型或身份变化')
                            key = (actual.st_dev, actual.st_ino)
                            if key in links:
                                header.type, header.linkname = tarfile.LNKTYPE, links[key]
                                output.addfile(header)
                            else:
                                header.size = item['size']
                                class CheckedReader:
                                    """对实际导出的文件块计算摘要。"""
                                    def __init__(self):
                                        """初始化摘要。:return: None。"""
                                        self.digest = hashlib.sha256()
                                    def read(self, size):
                                        """读取并累计摘要。:param size: 块大小。:return: 文件字节。"""
                                        content = source.read(size)
                                        self.digest.update(content)
                                        return content
                                reader = CheckedReader()
                                output.addfile(header, reader)
                                if reader.digest.hexdigest() != item['sha256'] or _identity(os.fstat(source.fileno())) != _identity(actual):
                                    raise ValueError('临时文件在导出期间变化')
                                links[key] = header.name
                finally:
                    os.close(parent)
        if before != tree_inventory(root, entry_limit=100000):
            raise ValueError('临时文件树在导出期间变化')
    finally:
        os.close(root_fd)
'''
_MOUNT_PROBE = """import json,os,pathlib
rows=[line.split() for line in pathlib.Path('/proc/self/mountinfo').read_text().splitlines()]
matches=[row for row in rows if row[4]=='/tmp/claude-1000']
safe=len(matches)==1 and {'noexec','nosuid','nodev'}<=set(matches[0][5].split(','))
print(json.dumps({'safe':safe,'uid':os.geteuid()}))
"""


def private_directory(path: Path) -> None:
    """创建当前服务私有目录，已有目录只核对权限和归属。

    :param path: 受控的精确目录，父级逐层拒绝链接。
    :return: None；未知权限或归属保持原状并拒绝使用。
    """
    parent = directory_fd(path.parent, create=True)
    try:
        try:
            os.mkdir(path.name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
        descriptor = os.open(path.name, os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        try:
            metadata = os.fstat(descriptor)
            if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
                raise ValueError('私有目录权限或归属无效')
        finally:
            os.close(descriptor)
    finally:
        os.close(parent)



def _store(runtime, row: dict) -> Path:
    path = runtime._root(row) / SCRATCHPAD_STORE
    private_directory(path)
    return path


def _document(path: Path, row: dict) -> dict | None:
    if not path.exists() and not path.is_symlink():
        return None
    value = read_storage_json(path, maximum_bytes=65536)
    if (not isinstance(value, dict) or value.get('protocol') != _PROTOCOL
            or value.get('environment_id') != row['environment_id']):
        raise ValueError('CLI临时文件记录归属或协议不符')
    return value


def _identity(row: dict) -> dict:
    return {'protocol': _PROTOCOL, 'environment_id': row['environment_id']}


def scratchpad_runtime_registered(root: Path, environment_id: str) -> bool:
    """核验可在目标节点重建的挂载目录，未知历史目录保持迁移保全。

    :param root: 原生命周期已核验归属的环境根。
    :param environment_id: 当前环境的不可变身份。
    :return: 双份协议和私有目录均核验通过时返回True，未登记目录返回False。
    """
    transient = root / SCRATCHPAD_RUNTIME
    if not transient.exists() and not transient.is_symlink():
        return False
    descriptor = directory_fd(transient)
    try:
        row = {'environment_id': environment_id}
        marker = _document(transient / 'mount.json', row)
        if marker is None:
            return False
        if _document(root / SCRATCHPAD_STORE / 'layout.json', row) is None:
            raise ValueError('CLI临时文件挂载目录缺少持久布局证明')
        metadata = os.fstat(descriptor)
        if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
            raise ValueError('CLI临时文件挂载目录权限或归属不符')
        if set(os.listdir(descriptor)) != {'mount.json', 'lower', 'work'}:
            raise ValueError('CLI临时文件挂载目录含有未知资料')
        for name in ('lower', 'work'):
            child = directory_fd(transient / name)
            try:
                metadata = os.fstat(child)
                if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
                    raise ValueError('CLI临时文件挂载子目录权限或归属不符')
                if name == 'lower' and os.listdir(child):
                    raise ValueError('CLI临时文件只读下层必须为空')
            finally:
                os.close(child)
        return True
    finally:
        os.close(descriptor)


def _volume_spec(runtime, row: dict) -> tuple[str, dict, dict]:
    root = runtime._root(row)
    host = runtime.host_data / root.relative_to(runtime.data)
    if any(character in str(host) for character in ',:\\\n\r'):
        raise ValueError('CLI临时文件宿主路径不支持挂载分隔符')
    scope = [runtime.deployment, getattr(runtime, 'node_key', None), row['environment_id'], str(host)]
    digest = hashlib.sha256(json.dumps(scope, separators=(',', ':')).encode()).hexdigest()[:32]
    options = {'type': 'overlay', 'device': 'overlay', 'o': ','.join((
        'lowerdir=' + str(host / SCRATCHPAD_RUNTIME / 'lower'),
        'upperdir=' + str(host / SCRATCHPAD_STORE / 'data'),
        'workdir=' + str(host / SCRATCHPAD_RUNTIME / 'work'), 'noexec', 'nosuid', 'nodev'))}
    labels = {'vibebench.product': 'v3', 'vibebench.deployment': runtime.deployment,
        'vibebench.environment': row['environment_id'], 'vibebench.role': 'cli-scratchpad',
        'vibebench.scratchpad-protocol': str(_PROTOCOL),
        'vibebench.cluster-node': getattr(runtime, 'node_key', None) or 'local'}
    return 'bench-cli-scratchpad-' + digest, options, labels


def _disk_supported(runtime, row: dict) -> bool:
    store = _store(runtime, row)
    image = runtime.client.images.get(runtime.image)
    key = (runtime.client.api.base_url, getattr(runtime, 'node_key', None), str(runtime.host_data),
        image.id, store.stat().st_dev)
    with _CAPABILITY_LOCK:
        known = key in _SUPPORTED_FILESYSTEMS
    if known:
        atomic_json(store / 'capability.json', {**_identity(row), 'supported': True,
            'node_key': getattr(runtime, 'node_key', None) or 'local', 'reason': 'verified_cached'})
        return True
    probe = Path(tempfile.mkdtemp(prefix='.probe-', dir=store))
    volume = container = None
    supported, cleaned = False, True
    reason = 'overlay_mount_unavailable'
    try:
        _volume_spec(runtime, row)
        for name in ('lower', 'upper', 'work'):
            (probe / name).mkdir(mode=0o700)
        os.chown(probe / 'upper', 1000, 1000)
        host = runtime.host_data / probe.relative_to(runtime.data)
        options = {'type': 'overlay', 'device': 'overlay', 'o': ','.join((
            'lowerdir=' + str(host / 'lower'), 'upperdir=' + str(host / 'upper'),
            'workdir=' + str(host / 'work'), 'noexec', 'nosuid', 'nodev'))}
        labels = {'vibebench.product': 'v3', 'vibebench.deployment': runtime.deployment,
            'vibebench.role': 'cli-scratchpad-probe'}
        volume = runtime.client.volumes.create(name='bench-cli-scratchpad-probe-' + uuid.uuid4().hex,
            driver='local', driver_opts=options, labels=labels)
        container = runtime.client.containers.create(runtime.image,
            name='bench-cli-scratchpad-probe-' + uuid.uuid4().hex,
            entrypoint=['python3', '-I', '-c', _MOUNT_PROBE], user='1000:1000',
            network_mode='none', read_only=True, cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
            mem_limit='64m', memswap_limit='64m', pids_limit=32, labels=labels,
            tmpfs={'/tmp': 'rw,noexec,nosuid,nodev,size=16m,mode=1777'},
            mounts=[Mount(SCRATCHPAD_TARGET, volume.name, no_copy=True)])
        container.start()
        result = container.wait(timeout=15)
        supported = result.get('StatusCode') == 0 and json.loads(container.logs(stdout=True, stderr=False)) == {'safe': True, 'uid': 1000}
        reason = 'verified' if supported else 'unsafe_mount'
    except (DockerException, OSError, ValueError) as error:
        reason = type(error).__name__
    finally:
        for resource in (container, volume):
            if resource is not None:
                try:
                    resource.remove(force=True) if resource is container else resource.remove()
                except Exception:
                    cleaned = False
        if cleaned:
            shutil.rmtree(probe)
    supported = supported and cleaned
    if not cleaned:
        reason = 'probe_cleanup_pending'
        atomic_json(probe / 'cleanup.json', {**_identity(row),
            'container_id': container.id if container is not None else None,
            'volume_name': volume.name if volume is not None else None})
    atomic_json(store / 'capability.json', {**_identity(row), 'supported': supported,
        'node_key': getattr(runtime, 'node_key', None) or 'local', 'reason': reason})
    if supported:
        with _CAPABILITY_LOCK:
            _SUPPORTED_FILESYSTEMS.add(key)
    return supported


def _disk_mount(runtime, row: dict, container) -> bool:
    matches = [item for item in container.attrs.get('Mounts', []) if item.get('Destination') == SCRATCHPAD_TARGET]
    if not matches:
        return False
    name, options, labels = _volume_spec(runtime, row)
    if (len(matches) != 1 or matches[0].get('Type') != 'volume'
            or matches[0].get('Name') != name or matches[0].get('RW') is not True):
        raise ValueError('CLI临时文件挂载归属不符')
    volume = runtime.client.volumes.get(name)
    volume.reload()
    if (volume.attrs.get('Driver') != 'local' or volume.attrs.get('Options') != options
            or volume.attrs.get('Labels') != labels):
        raise ValueError('CLI临时文件卷配置或归属不符')
    return True


def _archive_path(store: Path, receipt: dict) -> Path:
    name = receipt.get('archive')
    if (not isinstance(name, str) or re.fullmatch(r'legacy-[a-f0-9]{32}\.tar', name) is None
            or re.fullmatch(r'[a-f0-9]{64}', str(receipt.get('sha256'))) is None):
        raise ValueError('CLI临时文件转存回执无效')
    path = store / name
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if (not S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077 or metadata.st_size > _ARCHIVE_LIMIT):
            raise ValueError('CLI临时文件转存包类型、权限或大小无效')
        checksum = hashlib.sha256()
        while chunk := source.read(1024 * 1024):
            checksum.update(chunk)
    if checksum.hexdigest() != receipt['sha256']:
        raise ValueError('CLI临时文件转存包摘要不一致')
    return path


def _discard_snapshot(store: Path, receipt: dict) -> None:
    name = receipt.get('archive')
    if name is None and receipt.get('empty') is True:
        return
    if not isinstance(name, str) or re.fullmatch(r'legacy-[a-f0-9]{32}\.tar', name) is None:
        raise ValueError('CLI临时文件清理记录无效')
    parent = directory_fd(store)
    try:
        try:
            metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_nlink != 1:
            raise ValueError('CLI临时文件转存包清理归属不符')
        os.unlink(name, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)


def _archive_relative(name: str) -> str:
    parts = name.rstrip('/').split('/')
    if (not parts or parts[0] != 'claude-1000' or any(part in ('', '.', '..') for part in parts)):
        raise ValueError('CLI临时文件转存包路径越界')
    return '/'.join(parts[1:]) or '.'


def _unpack(path: Path, target: Path) -> dict:
    entries, hardlinks, timestamps, total = {}, {}, {}, 0
    # 所有链接最后创建，普通文件落盘期间的父目录完全由控制端建立。
    with tarfile.open(path, mode='r|') as archive:
        for member in archive:
            name = _archive_relative(member.name)
            if name in entries or len(entries) >= _ENTRY_LIMIT:
                raise ValueError('CLI临时文件转存包含重复路径或条目过多')
            if name == '.' and not member.isdir():
                raise ValueError('CLI临时文件根必须为目录')
            item = {'mode': member.mode & 0o7777, 'uid': member.uid, 'gid': member.gid}
            if not (0 <= member.uid < 2**32 and 0 <= member.gid < 2**32):
                raise ValueError('CLI临时文件归属无效')
            if member.isdir():
                item['kind'] = 'directory'
            elif member.issym():
                item.update(kind='symlink', target=member.linkname)
            elif member.islnk():
                item['kind'] = 'file'
                hardlinks[name] = _archive_relative(member.linkname)
            elif member.isfile():
                total += member.size
                if member.size < 0 or total > _ARCHIVE_LIMIT:
                    raise ValueError('CLI临时文件转存内容过大')
                item.update(kind='file', size=member.size)
            else:
                raise ValueError('CLI临时文件转存包含特殊文件')
            entries[name] = item
            timestamps[name] = member.mtime
            destination = target / name
            if member.isdir():
                destination.mkdir(mode=0o700, parents=True, exist_ok=True)
            elif member.isfile():
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                checksum = hashlib.sha256()
                with os.fdopen(descriptor, 'wb') as output, archive.extractfile(member) as content:
                    while chunk := content.read(1024 * 1024):
                        checksum.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                item['sha256'] = checksum.hexdigest()
    if '.' not in entries:
        raise ValueError('CLI临时文件转存包缺少根目录')
    for name in entries:
        parent = PurePosixPath(name).parent
        while str(parent) != '.':
            if entries.get(str(parent), {}).get('kind') != 'directory':
                raise ValueError('CLI临时文件父目录类型不一致')
            parent = parent.parent
    for name, source in hardlinks.items():
        original = entries.get(source)
        if original is None or original.get('kind') != 'file' or source in hardlinks:
            raise ValueError('CLI临时文件硬链接目标无效')
        if any(entries[name][key] != original[key] for key in ('mode', 'uid', 'gid')):
            raise ValueError('CLI临时文件硬链接元数据不一致')
        os.link(target / source, target / name, follow_symlinks=False)
        entries[name] = dict(original)
    for name, item in entries.items():
        if item['kind'] == 'symlink':
            (target / name).symlink_to(item['target'])
    preserve_metadata(target, entries)
    for name in sorted(entries, key=lambda item: item.count('/'), reverse=True):
        os.utime(target / name, (timestamps[name], timestamps[name]), follow_symlinks=False)
    if tree_inventory(target, durable=True, entry_limit=_ENTRY_LIMIT) != entries:
        raise ValueError('CLI临时文件转存内容核验失败')
    return entries


def preserve_cli_scratchpad(runtime, row: dict, container) -> None:
    """在原生命周期门禁内保全旧CLI内存盘，导出失败保留源实例。

    :param runtime: 持有环境锁和原维护／停止许可的运行时。
    :param row: 已核验的环境行。
    :param container: 归属已核验的固定CLI。
    :return: None；磁盘布局直接沿用持久数据。
    """
    existing = runtime._root(row) / SCRATCHPAD_STORE
    if not existing.exists() and not existing.is_symlink():
        image = runtime.client.images.get(runtime.image)
        labels = image.attrs['Config'].get('Labels') or {}
        if labels.get('vibebench.cli-scratchpad-protocol') != str(_PROTOCOL):
            return
    container.reload()
    if _disk_mount(runtime, row, container) or container.status in ('exited', 'dead', 'created'):
        return
    if container.status != 'running':
        raise ValueError('CLI临时文件源状态不明，保留原实例')
    store = _store(runtime, row)
    if _document(store / 'restore.json', row) is not None:
        raise ValueError('CLI临时文件恢复尚未确认，保留原转存包')
    if _document(store / 'layout.json', row) is not None:
        raise ValueError('原CLI与磁盘临时文件布局冲突，请先对账')
    started = container.attrs.get('State', {}).get('StartedAt')
    if not isinstance(started, str) or not started:
        raise ValueError('CLI临时文件转存缺少源实例启动身份')
    source = {'container_id': container.id, 'generation': row['generation'], 'started_at': started,
        'node_key': getattr(runtime, 'node_key', None) or 'local'}
    previous = _document(store / 'legacy.json', row)
    if previous is not None and previous.get('container_id') != container.id:
        raise ValueError('CLI临时文件已有其他源实例，请先对账')
    if previous is not None and previous.get('started_at') != started:
        restored = {**_identity(row), 'container_id': container.id,
            'started_at': started, 'archive_sha256': previous.get('sha256')}
        if _document(store / 'restored.json', row) != restored:
            raise ValueError('CLI临时文件原快照尚未恢复到本次启动，保留转存包')
    archive_path = store / ('legacy-' + uuid.uuid4().hex + '.tar')
    published = False
    try:
        # Docker归档看不到本机隔离挂载中的tmpfs。可信程序在旧CLI内导出，
        # 复用只依赖标准库的盘点实现，兼容仍在运行且尚未安装新模块的旧镜像。
        program = Path(__file__).with_name('storage_maintenance.py').read_text() + '\n' + _EXPORT
        execution = runtime.client.api.exec_create(container.id, ['python3', '-I', '-c', program],
            stdout=True, stderr=False, user='1000:1000')['Id']
        chunks = runtime.client.api.exec_start(execution, stream=True)
        checksum, size = hashlib.sha256(), 0
        try:
            with archive_path.open('xb') as output:
                os.fchmod(output.fileno(), 0o600)
                for chunk in chunks:
                    size += len(chunk)
                    if size > _ARCHIVE_LIMIT:
                        raise ValueError('CLI临时文件转存包超过上限')
                    checksum.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        finally:
            close = getattr(chunks, 'close', None)
            if close is not None:
                close()
        result = runtime.client.api.exec_inspect(execution)
        if result.get('Running') is not False or result.get('ExitCode') != 0:
            raise ValueError('CLI临时文件导出或源文件一致性尚未确认')
        with tempfile.TemporaryDirectory(prefix='.verify-', dir=store) as temporary:
            _unpack(archive_path, Path(temporary))
        container.reload()
        if (container.id != source['container_id'] or container.status != 'running'
                or container.attrs.get('State', {}).get('StartedAt') != started):
            raise ValueError('CLI临时文件转存期间源启动身份变化，保留原实例')
        atomic_json(store / 'legacy.json', {**_identity(row), **source,
            'archive': archive_path.name, 'sha256': checksum.hexdigest()})
        published = True
        if previous is not None:
            _discard_snapshot(store, previous)
    finally:
        if not published:
            archive_path.unlink(missing_ok=True)


def prepare_scratchpad_mount(runtime, row: dict) -> Mount | None:
    """为新CLI准备账号私有数据与受保护文件系统卷。

    :param runtime: 原账号运行时，已持有环境创建锁。
    :param row: 已核验的当前环境行。
    :return: 原路径Docker卷挂载；全新环境能力不足时沿用tmpfs并返回None。
    """
    store = _store(runtime, row)
    layout = _document(store / 'layout.json', row)
    if not _disk_supported(runtime, row):
        if layout is None:
            if (store / 'data').exists() or (store / 'data').is_symlink():
                raise ValueError('CLI临时文件目录尚未完成发布，请先对账')
            return None
        raise ValueError('当前节点无法安全挂载已保留的CLI临时文件，请使用兼容节点继续恢复')
    data = store / 'data'
    if layout is None:
        receipt = _document(store / 'legacy.json', row)
        prepared = _document(store / 'prepared.json', row)
        if data.exists() or data.is_symlink():
            inventory = tree_inventory(data, durable=True, entry_limit=_ENTRY_LIMIT)
            checksum = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
            if prepared is None or prepared.get('tree_sha256') != checksum:
                raise ValueError('CLI临时文件目录尚未完成发布，请先对账')
        else:
            with tempfile.TemporaryDirectory(prefix='.prepare-', dir=store) as temporary:
                stage = Path(temporary) / 'data'
                stage.mkdir(mode=0o700)
                if receipt is not None and receipt.get('empty') is not True:
                    _unpack(_archive_path(store, receipt), stage)
                else:
                    os.chown(stage, 1000, 1000)
                inventory = tree_inventory(stage, durable=True, entry_limit=_ENTRY_LIMIT)
                checksum = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
                atomic_json(store / 'prepared.json', {**_identity(row), 'tree_sha256': checksum})
                os.rename(stage, data)
        atomic_json(store / 'layout.json', _identity(row))
    descriptor = directory_fd(data)
    try:
        if os.fstat(descriptor).st_uid != 1000:
            raise ValueError('CLI临时文件根目录所有者不符')
    finally:
        os.close(descriptor)
    transient = runtime._root(row) / SCRATCHPAD_RUNTIME
    private_directory(transient)
    if _document(transient / 'mount.json', row) is None:
        if any(transient.iterdir()):
            raise ValueError('CLI临时文件挂载目录含有未登记资料，请先对账')
        # 先发布归属，再创建可重建子目录，使中途失败可按原协议继续。
        atomic_json(transient / 'mount.json', _identity(row))
    for name in ('lower', 'work'):
        private_directory(transient / name)
    scratchpad_runtime_registered(runtime._root(row), row['environment_id'])
    name, options, labels = _volume_spec(runtime, row)
    try:
        volume = runtime.client.volumes.get(name)
    except NotFound:
        volume = runtime.client.volumes.create(name=name, driver='local', driver_opts=options, labels=labels)
    volume.reload()
    if (volume.attrs.get('Driver') != 'local' or volume.attrs.get('Options') != options
            or volume.attrs.get('Labels') != labels):
        raise ValueError('CLI临时文件卷配置或归属不符')
    return Mount(SCRATCHPAD_TARGET, volume.name, no_copy=True)


def restore_cli_scratchpad(runtime, row: dict, container, *, fresh: bool = False) -> None:
    """唤醒旧CLI时恢复原临时路径，并核验新布局的安全挂载。

    :param runtime: 持有原环境启动锁的运行时。
    :param row: 已核验环境行。
    :param container: 已启动且归属正确的固定CLI。
    :param fresh: 仅原角色创建入口可声明新建的空CLI，允许接续同环境旧快照。
    :return: None；文件或挂载核验失败阻挡后续业务准入。
    """
    root = runtime._root(row) / SCRATCHPAD_STORE
    if not root.exists() and not root.is_symlink():
        return
    container.reload()
    if _disk_mount(runtime, row, container):
        result = container.exec_run(['python3', '-I', '-c', _MOUNT_PROBE])
        if result.exit_code or json.loads(result.output) != {'safe': True, 'uid': 1000}:
            raise ValueError('CLI临时文件安全挂载核验失败')
        store = _store(runtime, row)
        receipt = _document(store / 'legacy.json', row)
        if receipt is not None:
            # 磁盘数据已发布且实际挂载通过，收口仅用于转存的内部副本。
            _discard_snapshot(store, receipt)
            (store / 'legacy.json').unlink(missing_ok=True)
        (store / 'restore.json').unlink(missing_ok=True)
        return
    store = _store(runtime, row)
    if _document(store / 'layout.json', row) is not None:
        raise ValueError('原CLI尚未挂载已发布的磁盘临时文件')
    receipt = _document(store / 'legacy.json', row)
    if receipt is not None:
        foreign = receipt.get('container_id') != container.id
        if receipt.get('empty') is not True:
            started = container.attrs.get('State', {}).get('StartedAt')
            if not isinstance(started, str) or not started:
                raise ValueError('CLI临时文件恢复缺少原实例启动身份')
            identity = {**_identity(row), 'container_id': container.id,
                'started_at': started, 'archive_sha256': receipt['sha256']}
            pending = _document(store / 'restore.json', row)
            # 停止可能在转存之后失败，原启动中的最新文件仍是权威状态。
            if not foreign and receipt.get('started_at') == started and pending is None:
                return
            if foreign and not fresh and pending != identity:
                raise ValueError('CLI临时文件恢复目标与原实例不符')
            if _document(store / 'restored.json', row) == identity:
                (store / 'restore.json').unlink(missing_ok=True)
                return
            atomic_json(store / 'restore.json', identity)
            parent = directory_fd(runtime._root(row) / 'runtime/cli')
            name = 'scratchpad-restore-' + uuid.uuid4().hex + '.tar'
            try:
                metadata = os.fstat(parent)
                if metadata.st_uid != 0 or metadata.st_gid != 1000 or metadata.st_mode & 0o022:
                    raise ValueError('CLI临时文件恢复控制目录权限不符')
                descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o640, dir_fd=parent)
                with os.fdopen(descriptor, 'wb') as output, _archive_path(store, receipt).open('rb') as source:
                    os.fchown(output.fileno(), 0, 1000)
                    os.fchmod(output.fileno(), 0o640)
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                # 同样绕过Docker归档视图，在原挂载命名空间里复用严格解包实现。
                program = Path(__file__).with_name('storage_maintenance.py').read_text()
                program += '\nimport tarfile\nimport sys\nimport tempfile\n'
                program += f'\n_ARCHIVE_LIMIT={_ARCHIVE_LIMIT}\n_ENTRY_LIMIT={_ENTRY_LIMIT}\n'
                program += inspect.getsource(_archive_relative) + '\n' + inspect.getsource(_unpack)
                program += "\nwith tempfile.TemporaryDirectory(prefix='.v3-scratchpad-',dir='/tmp') as temporary:\n"
                program += "    target=Path(temporary)/'data'\n    target.mkdir(mode=0o700)\n"
                program += "    _unpack(Path(sys.argv[1]),target)\n    destination=Path('/tmp/claude-1000')\n"
                program += "    if destination.is_symlink():\n        raise ValueError('临时目录根不能为链接')\n"
                program += "    if destination.exists() and any(destination.iterdir()):\n"
                program += "        if tree_inventory(destination)!=tree_inventory(target):\n            raise ValueError('临时文件恢复目标已有未知内容')\n"
                program += "    else:\n        os.rename(target,destination)\n"
                result = container.exec_run(['python3', '-I', '-c', program, '/run/v3/' + name], user='1000:1000')
                if result.exit_code:
                    raise ValueError('CLI临时文件恢复未确认')
                if foreign:
                    atomic_json(store / 'legacy.json', {**receipt, 'container_id': container.id,
                        'generation': row['generation'], 'node_key': getattr(runtime, 'node_key', None) or 'local',
                        'started_at': started, 'restored_from': receipt['container_id']})
                atomic_json(store / 'restored.json', identity)
                (store / 'restore.json').unlink(missing_ok=True)
            finally:
                try:
                    os.unlink(name, dir_fd=parent)
                except FileNotFoundError:
                    pass
                finally:
                    os.close(parent)
        elif foreign:
            if not fresh:
                raise ValueError('CLI临时文件恢复目标与原实例不符')
            (store / 'legacy.json').unlink()


def remove_scratchpad_volume(runtime, row: dict) -> None:
    """角色已移除后收口本环境的卷元数据，保留磁盘文件。

    :param runtime: 持有原环境移除锁的运行时。
    :param row: 已核验环境行。
    :return: None；未知归属或仍被引用的卷保留并报错。
    """
    store = runtime._root(row) / SCRATCHPAD_STORE
    if not store.exists() and not store.is_symlink():
        return
    _store(runtime, row)
    name, options, labels = _volume_spec(runtime, row)
    try:
        volume = runtime.client.volumes.get(name)
    except NotFound:
        return
    volume.reload()
    if (volume.attrs.get('Driver') != 'local' or volume.attrs.get('Options') != options
            or volume.attrs.get('Labels') != labels):
        raise ValueError('CLI临时文件卷清理归属不符')
    volume.remove()
