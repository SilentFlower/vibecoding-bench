"""维护窗口内的双库一致快照、可恢复替换与精确轮换。"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import sys
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path
from source_layout import source_path
from stat import S_ISREG

# 独立维护模块和测试入口沿安装后的相同目录布局定位纯运行模块。
sys.path.insert(0, str(source_path(Path(__file__).resolve().parents[2], 'orchestrator')))
from runtime_files import atomic_json, directory_fd
from system_update_contract import safe_read, strict_json, utc_now


DATABASES = {'bench': 'bench/db.sqlite', 'gateway': 'gateway/gateway.sqlite'}


def assert_quiescent(data: Path) -> None:
    """在停止控制服务后拒绝仍持有本部署数据库的本机进程。

    :param data: 固定部署数据根。
    :return: None；相关归属无法读取时保持维护阻断。
    """
    targets = {str(data / relative) + suffix for relative in DATABASES.values() for suffix in ('', '-wal', '-shm')}
    identities = set()
    for target in targets:
        path = Path(target)
        if path.exists():
            info = _file(path)
            identities.add((info.st_dev, info.st_ino))
    owners = {_file(data / relative).st_uid for relative in DATABASES.values()} | {os.geteuid()}
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if os.geteuid() != 0 and process.stat().st_uid not in owners:
                continue
            for descriptor in (process / 'fd').iterdir():
                try:
                    target = os.readlink(descriptor).removesuffix(' (deleted)')
                    info = descriptor.stat()
                except FileNotFoundError:
                    continue
                # 容器中的同一挂载会显示 /data 路径，使用 inode 同时识别跨命名空间持有者。
                if target in targets or (info.st_dev, info.st_ino) in identities:
                    raise ValueError('数据库仍有本机进程持有，保持维护等待')
        except (FileNotFoundError, ProcessLookupError):
            continue
        except PermissionError as error:
            raise ValueError('数据库写入者归属暂时无法核验') from error


def _file(path: Path):
    descriptor = directory_fd(path.parent)
    try:
        info = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        if not S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('数据库快照路径必须为独立普通文件')
        return info
    finally:
        os.close(descriptor)


def _digest(path: Path) -> str:
    _file(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _logical(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for statement in connection.iterdump():
        digest.update(statement.encode())
        digest.update(b'\n')
    return digest.hexdigest()


def _sync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _binding(deployment: str, operation: dict) -> dict:
    for field in ('operation_id', 'epoch'):
        value = operation[field]
        if str(uuid.UUID(value)) != value:
            raise ValueError('数据库快照操作身份无效')
    return {'schema_version': 1, 'deployment': deployment, 'operation_id': operation['operation_id'],
        'epoch': operation['epoch'], 'source_release': operation['original']['release']['release']}


def verify_snapshot(folder: Path, deployment: str, operation: dict) -> dict:
    """校验同一次操作的完整双库快照，任一缺失或损坏均拒绝。

    :param folder: 本次操作的精确快照目录。
    :param deployment: 固定部署标识。
    :param operation: 持久更新操作。
    :return: 校验过的完整私有清单。
    """
    descriptor = directory_fd(folder)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('数据库快照目录必须为当前用户私有')
    finally:
        os.close(descriptor)
    value = strict_json(safe_read(folder / 'manifest.json', private=True))
    if (set(value) != {'schema_version', 'deployment', 'operation_id', 'epoch', 'source_release', 'databases', 'completed_at'} or type(value['schema_version']) is not int
            or any(value.get(key) != item for key, item in _binding(deployment, operation).items()) or set(value.get('databases', {})) != set(DATABASES)):
        raise ValueError('数据库快照归属或完整性无效')
    completed = value['completed_at']
    if not isinstance(completed, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', completed):
        raise ValueError('数据库快照完成时间无效')
    datetime.fromisoformat(completed.replace('Z', '+00:00'))
    if strict_json(safe_read(folder / 'intent.json', private=True)) != _binding(deployment, operation):
        raise ValueError('数据库快照意图与完成归属不符')
    for name, relative in DATABASES.items():
        entry = value['databases'][name]
        fields = {'relative_path', 'size', 'sha256', 'logical_sha256', 'uid', 'gid', 'mode', 'schema_version'}
        if (not isinstance(entry, dict) or set(entry) != fields
                or any(type(entry[key]) is not int or entry[key] < 0 for key in ('size', 'uid', 'gid', 'mode', 'schema_version'))
                or not 0 < entry['size'] <= 1024 ** 4 or entry['mode'] > 0o777 or entry['uid'] >= 2 ** 32 or entry['gid'] >= 2 ** 32
                or any(not isinstance(entry[key], str) or not re.fullmatch('[a-f0-9]{64}', entry[key]) for key in ('sha256', 'logical_sha256'))):
            raise ValueError('数据库快照清单字段无效')
        path = folder / (name + '.sqlite')
        info = _file(path)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('数据库快照文件权限或归属无效')
        if entry.get('relative_path') != relative or info.st_size != entry.get('size') or _digest(path) != entry.get('sha256'):
            raise ValueError('数据库快照字节校验失败')
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as database:
            if database.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or _logical(database) != entry.get('logical_sha256'):
                raise ValueError('数据库快照逻辑校验失败')
    return value


def create_snapshot(data: Path, folder: Path, deployment: str, operation: dict) -> dict:
    """在写入者停止后保存两个数据库及 WAL 已提交事务。

    :param data: 固定部署数据根。
    :param folder: 本次操作的私有快照目录。
    :param deployment: 固定部署标识。
    :param operation: 持久操作；调用方持有维护门禁和存储锁。
    :return: 完整快照清单；空间或任一校验失败明确抛错。
    """
    binding = _binding(deployment, operation)
    if (folder / 'manifest.json').exists():
        return verify_snapshot(folder, deployment, operation)
    size = 0
    for relative in DATABASES.values():
        source = data / relative
        physical = _file(source).st_size
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as database:
            logical = database.execute('PRAGMA page_count').fetchone()[0] * database.execute('PRAGMA page_size').fetchone()[0]
        size += max(physical, logical)
    wal_size = sum(_file(path).st_size for relative in DATABASES.values() if (path := Path(str(data / relative) + '-wal')).exists())
    same_filesystem = data.stat().st_dev == folder.parent.stat().st_dev
    required = size * (2 if same_filesystem else 1) + wal_size + 64 * 1024 ** 2
    if shutil.disk_usage(data).free < required:
        raise ValueError(f'数据库快照及恢复空间不足，至少需要 {required} 字节可用空间')
    snapshot_required = size + wal_size + 64 * 1024 ** 2
    if shutil.disk_usage(folder.parent).free < snapshot_required:
        raise ValueError(f'数据库快照所在文件系统空间不足，至少需要 {snapshot_required} 字节')
    folder.mkdir(mode=0o700, exist_ok=True)
    descriptor = directory_fd(folder)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError('数据库快照目录必须为当前用户私有')
    finally:
        os.close(descriptor)
    intent = folder / 'intent.json'
    if intent.exists():
        if strict_json(safe_read(intent, private=True)) != binding:
            raise ValueError('数据库快照目录已有其他操作')
    else:
        atomic_json(intent, binding)
    databases = {}
    for name, relative in DATABASES.items():
        source, target = data / relative, folder / (name + '.sqlite')
        original = _file(source)
        if target.exists():
            _file(target)
            target.unlink()
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as current:
            current.execute('BEGIN')
            logical = _logical(current)
            exists = current.execute("SELECT 1 FROM sqlite_master WHERE name='system_schema_migrations'").fetchone()
            version = current.execute('SELECT COALESCE(MAX(version),0) FROM system_schema_migrations').fetchone()[0] if exists else 0
            with closing(sqlite3.connect(target)) as snapshot:
                current.backup(snapshot)
                # 完成快照只保留一个独立文件，校验和轮换不依赖短命 WAL/SHM。
                snapshot.execute('PRAGMA journal_mode=DELETE')
                if snapshot.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or _logical(snapshot) != logical:
                    raise ValueError('数据库快照未通过完整性验证')
        after = _file(source)
        if (original.st_dev, original.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError('快照期间数据库文件归属发生变化')
        _sync(target)
        databases[name] = {'relative_path': relative, 'size': _file(target).st_size,
            'sha256': _digest(target), 'logical_sha256': logical, 'uid': original.st_uid,
            'gid': original.st_gid, 'mode': original.st_mode & 0o777, 'schema_version': version}
    value = {**binding, 'databases': databases, 'completed_at': utc_now()}
    atomic_json(folder / 'manifest.json', value)
    return verify_snapshot(folder, deployment, operation)


def restore_snapshot(data: Path, folder: Path, deployment: str, operation: dict, save) -> None:
    """在同代次关闭门禁内逐库恢复，持久意图支持替换中断续接。

    :param data: 本部署数据根。
    :param folder: 本次完整快照目录。
    :param deployment: 固定部署标识。
    :param operation: 持久操作，重新接单后拒绝恢复旧快照。
    :param save: 每次副作用前后的原子持久回调。
    :return: None；任何未知内容变化保持维护阻断。
    """
    if operation.get('release_started'):
        raise ValueError('本次升级已进入开放准入边界，禁止旧快照覆盖后来数据')
    snapshot = verify_snapshot(folder, deployment, operation)
    restored = operation.setdefault('database_restore', {})
    for name, relative in DATABASES.items():
        entry = snapshot['databases'][name]
        target = data / relative
        actual = _digest(target)
        state = restored.get(name)
        if state:
            if actual == entry['sha256'] and not any(Path(str(target) + suffix).exists() for suffix in ('-wal', '-shm')):
                state['state'] = 'completed'
                save()
                continue
            if state['state'] == 'completed' or actual != state['before_sha256']:
                raise ValueError('数据库恢复发现后来或外来的数据变化')
        else:
            state = {'state': 'intent', 'before_sha256': actual, 'auxiliary': {}}
            for suffix in ('-wal', '-shm'):
                auxiliary = Path(str(target) + suffix)
                if auxiliary.exists():
                    state['auxiliary'][suffix] = _digest(auxiliary)
            restored[name] = state
            save()
        temporary = target.with_name('.' + target.name + '.restore-' + operation['operation_id'])
        if temporary.exists():
            if _digest(temporary) != entry['sha256']:
                info = _file(temporary)
                if not state.get('temporary_intent') or info.st_uid != os.geteuid() or info.st_mode & 0o077:
                    raise ValueError('数据库恢复暂存文件身份不符')
                # 复制中断留下的本操作私有暂存可重建，原库仍由恢复意图保护。
                temporary.unlink()
        if not temporary.exists():
            state['temporary_intent'] = True
            save()
            descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, 'wb') as output, (folder / (name + '.sqlite')).open('rb') as source:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            if _digest(temporary) != entry['sha256']:
                raise ValueError('数据库恢复暂存校验失败')
        os.chown(temporary, entry['uid'], entry['gid'], follow_symlinks=False)
        os.chmod(temporary, entry['mode'], follow_symlinks=False)
        # 控制服务始终停止；只移除本次已登记的 sidecar，防止旧 WAL 污染恢复文件。
        for suffix in ('-wal', '-shm'):
            auxiliary = Path(str(target) + suffix)
            if auxiliary.exists():
                if _digest(auxiliary) != state['auxiliary'].get(suffix):
                    raise ValueError('数据库恢复发现未登记的日志文件')
                auxiliary.unlink()
        os.replace(temporary, target)
        descriptor = directory_fd(target.parent)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        state['state'] = 'completed'
        save()


def rotate_snapshots(operations: Path, deployment: str, protected: set[str], keep: int = 2) -> dict:
    """仅回收本部署已完成且无活动引用的精确快照文件。

    :param operations: 本部署操作目录。
    :param deployment: 固定部署标识。
    :param protected: 所有活动或待恢复操作 ID。
    :param keep: 保留的最近完成组数。
    :return: 脱敏清理结果。
    """
    candidates = []
    preserved = 0
    for parent in operations.iterdir():
        folder = parent / 'database-snapshot'
        if parent.is_symlink() or folder.is_symlink() or not (folder / 'manifest.json').is_file():
            if folder.exists() or folder.is_symlink():
                preserved += 1
            continue
        try:
            operation = strict_json(safe_read(parent / 'operation.json', private=True))
            if operation['phase'] not in ('succeeded', 'succeeded_cleanup_pending', 'restored', 'failed', 'cancelled'):
                protected.add(parent.name)
            manifest = verify_snapshot(folder, deployment, operation)
            if manifest['operation_id'] != parent.name:
                preserved += 1
                continue
            candidates.append((manifest['completed_at'], parent.name, folder))
        except (ValueError, OSError, KeyError, sqlite3.Error):
            preserved += 1
            continue
    candidates.sort(reverse=True)
    retained = {identifier for _, identifier, _ in candidates[:keep]} | protected
    removed = []
    for _, identifier, folder in candidates:
        if identifier in retained:
            continue
        names = {'manifest.json', 'intent.json', 'bench.sqlite', 'gateway.sqlite'}
        if {path.name for path in folder.iterdir()} != names:
            preserved += 1
            continue
        for name in names:
            _file(folder / name)
        for name in names:
            (folder / name).unlink()
        folder.rmdir()
        removed.append(identifier)
    return {'removed_operations': removed, 'retained_groups': len(candidates) - len(removed), 'preserved_unverified_groups': preserved}
