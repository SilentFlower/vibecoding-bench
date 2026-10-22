"""冻结制品的受限盘点与原子物理去重，不处理账号可写业务文件。"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
from stat import S_IMODE, S_ISDIR, S_ISLNK, S_ISREG, S_ISSOCK
import uuid


def _relative(value: str) -> tuple[str, ...]:
    parts = value.split('/')
    if not value or PurePosixPath(value).is_absolute() or any(part in ('', '.', '..') for part in parts):
        raise ValueError('存储路径必须是根目录内的规范相对路径')
    return tuple(parts)


def _parent(root_fd: int, relative: str) -> tuple[int, str]:
    parts = _relative(relative)
    descriptor = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def _hash(descriptor: int) -> str:
    checksum = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while content := os.read(descriptor, 1024 * 1024):
        checksum.update(content)
    return checksum.hexdigest()


def _identity(metadata) -> tuple:
    return (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns,
        S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid)


def acquire_storage_lock(root: Path) -> int:
    """为备份、维护与启动取得同一部署的非阻塞磁盘操作锁。

    :param root: 已验证且非链接的部署数据根。
    :return: 调用方必须在 finally 中关闭的已加锁文件描述符。
    """
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open('.v3-storage-maintenance.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
            0o600, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        metadata = os.fstat(descriptor)
        if (not S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != os.geteuid()
                or S_IMODE(metadata.st_mode) & 0o077 or metadata.st_size != 0):
            raise ValueError('部署磁盘操作锁的类型、归属或权限无效')
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('本部署已有备份、维护或启动操作') from error
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_storage_json(path: Path, *, maximum_bytes: int = 64 * 1024**2, private: bool = True) -> object:
    """有界读取维护元数据，拒绝链接、FIFO 及不符合私有权限的清单。

    :param path: 已由业务入口限定用途的元数据路径。
    :param maximum_bytes: 允许的最大文件字节数。
    :param private: 是否要求当前维护用户所有且其他用户不可访问。
    :return: 解码后的 JSON；异常不读取链接目标或等待管道。
    """
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if (not S_ISREG(metadata.st_mode) or metadata.st_size > maximum_bytes
                or (private and (metadata.st_uid != os.geteuid() or S_IMODE(metadata.st_mode) & 0o077))):
            raise ValueError('存储清单的文件类型、大小、归属或权限无效')
        content = source.read(maximum_bytes + 1)
        if len(content) > maximum_bytes or _identity(os.fstat(source.fileno())) != _identity(metadata):
            raise ValueError('读取期间存储清单发生变化或超出上限')
    return json.loads(content)


def tree_inventory(root: Path, excluded: set[str] | None = None, *, durable: bool = False) -> dict[str, dict]:
    """盘点普通文件、目录与链接，不跟随链接或复制运行 socket。

    :param root: 可信父目录下的非链接目录。
    :param excluded: 精确排除的相对路径，目录同时排除其子树。
    :param durable: 备份完成前将已读取文件及目录同步到持久存储。
    :return: 包含字节摘要、权限与归属的逻辑文件清单。
    """
    ignored = excluded or set()
    for value in ignored:
        _relative(value)
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    entries = {}
    try:
        for directory, folders, names, parent in os.fwalk('.', dir_fd=descriptor, follow_symlinks=False):
            relative_directory = str(PurePosixPath(directory))
            metadata = os.fstat(parent)
            entries[relative_directory] = {'kind': 'directory', 'mode': S_IMODE(metadata.st_mode),
                'uid': metadata.st_uid, 'gid': metadata.st_gid}
            for name in sorted(folders + names):
                relative = str(PurePosixPath(directory) / name)
                if relative in ignored:
                    if name in folders:
                        folders.remove(name)
                    continue
                metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
                item = {'mode': S_IMODE(metadata.st_mode), 'uid': metadata.st_uid, 'gid': metadata.st_gid}
                if S_ISLNK(metadata.st_mode):
                    item.update(kind='symlink', target=os.readlink(name, dir_fd=parent))
                    if name in folders:
                        folders.remove(name)
                elif S_ISDIR(metadata.st_mode):
                    continue
                elif S_ISSOCK(metadata.st_mode):
                    continue
                elif S_ISREG(metadata.st_mode):
                    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                    try:
                        before = os.fstat(file_fd)
                        if _identity(before) != _identity(metadata):
                            raise ValueError('盘点期间文件被替换')
                        item.update(kind='file', size=before.st_size, sha256=_hash(file_fd))
                        if _identity(os.fstat(file_fd)) != _identity(before):
                            raise ValueError('盘点期间文件内容发生变化')
                        if durable:
                            os.fsync(file_fd)
                    finally:
                        os.close(file_fd)
                else:
                    raise ValueError('持久目录包含无法备份的特殊文件')
                entries[relative] = item
            if durable:
                os.fsync(parent)
    finally:
        os.close(descriptor)
    return entries


def preserve_metadata(root: Path, inventory: dict[str, dict]) -> None:
    """为已复制的私有树恢复归属和权限，不跟随符号链接。

    :param root: 新建且仅维护进程可访问的恢复目录。
    :param inventory: 原始逻辑文件清单。
    :return: None。
    """
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for relative, item in sorted(inventory.items(), key=lambda value: value[0].count('/'), reverse=True):
            if relative == '.':
                os.fchown(descriptor, item['uid'], item['gid'])
                os.fchmod(descriptor, item['mode'])
                continue
            parent, name = _parent(descriptor, relative)
            try:
                os.chown(name, item['uid'], item['gid'], dir_fd=parent, follow_symlinks=False)
                if item['kind'] != 'symlink':
                    file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                    try:
                        os.fchmod(file_fd, item['mode'])
                    finally:
                        os.close(file_fd)
            finally:
                os.close(parent)
    finally:
        os.close(descriptor)


def _protected_parent(root_fd: int, relative: str, uid: int) -> bool:
    parts = _relative(relative)
    descriptor = os.dup(root_fd)
    try:
        for part in ('', *parts[:-1]):
            if part:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            metadata = os.fstat(descriptor)
            if metadata.st_uid != uid or S_IMODE(metadata.st_mode) & 0o022:
                return False
        return True
    finally:
        os.close(descriptor)


def deduplicate_immutable_tree(root: Path, *, minimum_bytes: int = 4096,
                               owner_uid: int | None = None, apply: bool = True,
                               canonical_root: Path | None = None) -> dict:
    """在受保护的冻结树中原子复用同字节、同权限的普通文件。

    :param root: 调用方已证明不会原地写入的私有冻结目录。
    :param minimum_bytes: 小于此值的文件不参与去重。
    :param owner_uid: 唯一允许的文件与父目录所有者，默认当前维护用户。
    :param apply: False 时只计算清单，不写入文件。
    :param canonical_root: 可选的管理端私有制品缓存，只保存相同字节的只读程序。
    :return: 复用文件数与估算释放块数；实际收益仍须测量文件系统。
    """
    if minimum_bytes < 0:
        raise ValueError('去重文件大小下限不能为负数')
    uid = os.geteuid() if owner_uid is None else owner_uid
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    canonical_fd = None
    groups, records = {}, []
    result = {'files': 0, 'relinked_files': 0, 'estimated_released_bytes': 0, 'applied': apply}
    try:
        root_device = os.fstat(descriptor).st_dev
        if canonical_root is not None:
            resolved_root, resolved_cache = root.resolve(), canonical_root.resolve()
            if (resolved_root == resolved_cache or resolved_root in resolved_cache.parents
                    or resolved_cache in resolved_root.parents):
                raise ValueError('共享制品缓存必须与账号版本目录分离')
            if not apply:
                raise ValueError('共享制品缓存不支持只读盘点模式')
            canonical_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            canonical_fd = os.open(canonical_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            metadata = os.fstat(canonical_fd)
            if metadata.st_uid != uid or S_IMODE(metadata.st_mode) & 0o077 or metadata.st_dev != root_device:
                raise ValueError('共享制品缓存的归属、权限或文件系统不一致')
            try:
                fcntl.flock(canonical_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return dict(result, busy=True)
        for directory, folders, names, parent in os.fwalk('.', dir_fd=descriptor, follow_symlinks=False):
            folders[:] = sorted(name for name in folders
                if S_ISDIR(os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode))
            for name in sorted(names):
                metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
                relative = str(PurePosixPath(directory) / name)
                if (not S_ISREG(metadata.st_mode) or metadata.st_size < minimum_bytes
                        or metadata.st_uid != uid or S_IMODE(metadata.st_mode) & 0o022
                        or metadata.st_dev != root_device or not _protected_parent(descriptor, relative, uid)):
                    continue
                file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                try:
                    if _identity(os.fstat(file_fd)) != _identity(metadata):
                        raise ValueError('去重盘点期间文件被替换')
                    digest = _hash(file_fd)
                    if _identity(os.fstat(file_fd)) != _identity(metadata):
                        raise ValueError('去重盘点期间文件被改写')
                finally:
                    os.close(file_fd)
                key = (digest, metadata.st_size, S_IMODE(metadata.st_mode), metadata.st_uid, metadata.st_gid)
                result['files'] += 1
                if canonical_fd is not None:
                    canonical_name = digest + '.' + format(S_IMODE(metadata.st_mode), 'o') + '.' + str(metadata.st_uid) + '.' + str(metadata.st_gid)
                    try:
                        os.link(name, canonical_name, src_dir_fd=parent, dst_dir_fd=canonical_fd,
                            follow_symlinks=False)
                        os.fsync(canonical_fd)
                    except FileExistsError:
                        pass
                    cached_fd = os.open(canonical_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=canonical_fd)
                    try:
                        cached = os.fstat(cached_fd)
                        if (not S_ISREG(cached.st_mode) or (cached.st_size, S_IMODE(cached.st_mode),
                                cached.st_uid, cached.st_gid) != key[1:] or _hash(cached_fd) != digest):
                            raise ValueError('共享制品缓存与已验证程序不一致')
                    finally:
                        os.close(cached_fd)
                    previous = (canonical_name, cached)
                else:
                    previous = groups.setdefault(key, (relative, metadata))
                if (previous[1].st_dev, previous[1].st_ino) != (metadata.st_dev, metadata.st_ino):
                    records.append((previous, (relative, metadata), digest))
        for (source, source_metadata), (target, target_metadata), digest in records:
            source_parent, source_name = _parent(canonical_fd if canonical_fd is not None else descriptor, source)
            try:
                target_parent, target_name = _parent(descriptor, target)
                try:
                    source_fd = os.open(source_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=source_parent)
                    try:
                        target_fd = os.open(target_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=target_parent)
                    except BaseException:
                        os.close(source_fd)
                        raise
                    try:
                        current_target = os.fstat(target_fd)
                        if (_identity(os.fstat(source_fd)) != _identity(source_metadata)
                                or _identity(current_target) != _identity(target_metadata)
                                or _hash(source_fd) != digest or _hash(target_fd) != digest):
                            raise ValueError('去重清单已过期，文件保持原样')
                        if apply:
                            temporary = '.dedup-' + uuid.uuid4().hex
                            try:
                                os.link(source_name, temporary, src_dir_fd=source_parent,
                                    dst_dir_fd=target_parent, follow_symlinks=False)
                                linked = os.stat(temporary, dir_fd=target_parent, follow_symlinks=False)
                                if _identity(linked) != _identity(source_metadata):
                                    raise ValueError('共享源在链接时发生变化')
                                if _identity(os.stat(target_name, dir_fd=target_parent,
                                        follow_symlinks=False)) != _identity(target_metadata):
                                    raise ValueError('去重目标在替换前发生变化')
                                os.replace(temporary, target_name, src_dir_fd=target_parent, dst_dir_fd=target_parent)
                                os.fsync(target_parent)
                            finally:
                                try:
                                    os.unlink(temporary, dir_fd=target_parent)
                                except FileNotFoundError:
                                    pass
                        result['relinked_files'] += 1
                        if current_target.st_nlink == 1:
                            result['estimated_released_bytes'] += current_target.st_blocks * 512
                    finally:
                        os.close(source_fd)
                        os.close(target_fd)
                finally:
                    os.close(target_parent)
            finally:
                os.close(source_parent)
    finally:
        if canonical_fd is not None:
            os.close(canonical_fd)
        os.close(descriptor)
    return result
