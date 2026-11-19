"""在已核对的 SSH 宿主或独立辅助容器中检查及清空节点数据。"""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import sys
from pathlib import PurePosixPath


MARKER = 'cluster-node.json'
FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _open_root(root: str) -> int:
    path = PurePosixPath(root)
    if not path.is_absolute() or len(path.parts) < 2 or str(path) != root or '..' in path.parts:
        raise ValueError('节点数据目录需要核对')
    directory = os.open('/', FLAGS)
    try:
        for part in path.parts[1:]:
            following = os.open(part, FLAGS, dir_fd=directory)
            os.close(directory)
            directory = following
        return os.dup(directory)
    finally:
        os.close(directory)


def _mounts() -> dict[str, tuple[str, PurePosixPath, PurePosixPath]]:
    result = {}
    with open('/proc/self/mountinfo', encoding='utf-8', errors='surrogateescape') as source:
        for line in source:
            mount_id, _, device, root, target = line.split()[:5]
            location = tuple(PurePosixPath(re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), value))
                for value in (root, target))
            result[mount_id] = (device, *location)
    return result


def _overlaps(left: PurePosixPath, right: PurePosixPath) -> bool:
    return left == right or left in right.parents or right in left.parents


def _source_location(descriptor: int, mounts: dict) -> tuple[str, PurePosixPath]:
    device, root, target = mounts[_mount_id(descriptor)]
    actual = PurePosixPath(os.readlink(f'/proc/self/fd/{descriptor}'))
    return device, root / actual.relative_to(target)


def verify_removal_mounts(root: str, sources: list[str]) -> dict:
    """核对其他容器的实际绑定源。:param root: 原节点数据根。:param sources: Docker 报告的其他绑定源。:return: 明确核对结果。"""
    target = PurePosixPath(root)
    mounts = _mounts()
    try:
        directory = _open_root(root)
    except FileNotFoundError:
        directory = None
    root_location = None
    if directory is not None:
        try:
            root_location = _source_location(directory, mounts)
        finally:
            os.close(directory)
    for source in sources:
        if _overlaps(target, PurePosixPath(os.path.realpath(source))):
            break
        if root_location is None:
            continue
        try:
            descriptor = os.open(source, os.O_PATH)
        except FileNotFoundError:
            continue
        except OSError:
            raise ValueError('无法确认其他容器的绑定挂载，请核对 SSH 用户的目录访问权限') from None
        try:
            device, actual = _source_location(descriptor, mounts)
        finally:
            os.close(descriptor)
        if device == root_location[0] and _overlaps(actual, root_location[1]):
            break
    else:
        return {'ok': True}
    raise ValueError('其他容器仍在使用节点数据目录，请先核对挂载')


def _data_state(directory: int, owner: dict) -> str:
    try:
        descriptor = os.open(MARKER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    except FileNotFoundError:
        if os.listdir(directory):
            raise ValueError('数据目录有内容且缺少本节点安装标记') from None
        return 'empty'
    with os.fdopen(descriptor, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o077
                or metadata.st_uid not in (0, os.fstat(directory).st_uid)
                or json.loads(source.read(8193)) != owner):
            raise ValueError('数据目录安装标记与原节点身份不一致')
    return 'owned'


def _mount_id(directory: int) -> str:
    with open(f'/proc/self/fdinfo/{directory}', encoding='ascii') as source:
        return next(line.split()[1] for line in source if line.startswith('mnt_id:'))


def _erase_entry(directory: int, name: str, mount_id: str) -> None:
    entry = os.stat(name, dir_fd=directory, follow_symlinks=False)
    if not stat.S_ISDIR(entry.st_mode):
        os.unlink(name, dir_fd=directory)
        return
    child = os.open(name, FLAGS, dir_fd=directory)
    try:
        if _mount_id(child) != mount_id:
            raise ValueError('节点数据目录存在其他挂载，请核对后重试')
        for item in os.listdir(child):
            _erase_entry(child, item, mount_id)
        os.rmdir(name, dir_fd=directory)
    finally:
        os.close(child)


def removal_files(action: str, root: str, owner: dict, proof: dict | None) -> dict:
    """核对同一数据目录并按原归属清理。:param action: 探测或擦除。:param root: 目录。:param owner: 安装身份。:param proof: 原目录设备及 inode。:return: 公开目录状态及身份。"""
    if action not in ('probe', 'erase') or (action == 'erase' and proof is None):
        raise ValueError('节点数据清理操作无效')
    # 数据根可以是独占挂载，清理保留根目录并拒绝进入任何下级挂载。
    if any(PurePosixPath(root) in target.parents for _, _, target in _mounts().values()):
        raise ValueError('节点数据目录存在其他挂载，请核对后重试')
    try:
        directory = _open_root(root)
    except FileNotFoundError:
        return {'state': 'absent', 'identity': None}
    try:
        if action == 'erase':
            # SSH 断开或控制端重启时，同一数据目录只能有一个擦除进程。
            fcntl.flock(directory, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(directory)
        identity = {'device': info.st_dev, 'inode': info.st_ino}
        if proof is not None and identity != proof:
            raise ValueError('节点数据目录已经换址，请核对原目录')
        state = _data_state(directory, owner)
        if action == 'erase' and state == 'owned':
            # 最后移除标记，避免重试把仅擦除了一部分的目录识别为其他资料。
            mount_id = _mount_id(directory)
            for name in os.listdir(directory):
                if name != MARKER:
                    _erase_entry(directory, name, mount_id)
            if set(os.listdir(directory)) != {MARKER}:
                raise ValueError('节点数据目录在清理期间发生变化')
            os.unlink(MARKER, dir_fd=directory)
            os.fsync(directory)
            state = _data_state(directory, owner)
        return {'state': state, 'identity': identity}
    finally:
        os.close(directory)


def main() -> None:
    """执行原节点宿主或辅助容器中的固定文件操作。:return: 通过标准输出返回可校验回执。"""
    try:
        value = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.load(sys.stdin)
        if value['action'] == 'verify_mounts':
            result = verify_removal_mounts(value['root'], value['sources'])
        else:
            result = removal_files(value['action'], value['root'], value['owner'], value.get('proof'))
    except ValueError as error:
        print(json.dumps({'error': str(error) if type(error) is ValueError else '节点数据归属标记无效'}))
        raise SystemExit(1 if len(sys.argv) > 1 else 0) from None
    except OSError:
        print(json.dumps({'error': '无法访问节点数据目录，请核对目录与权限后重试'}))
        raise SystemExit(1 if len(sys.argv) > 1 else 0) from None
    else:
        print(json.dumps(result))


if __name__ == '__main__':
    main()
