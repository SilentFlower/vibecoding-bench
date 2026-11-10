"""读取账号私有目录中的 CC 组装后快照。"""
import json
import os
import stat
import time
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

from runtime_files import directory_fd

MAX_CAPTURE_BYTES = 6 * 1024 * 1024
RETENTION_MS = 7 * 24 * 60 * 60 * 1000


class CaptureExpired(ValueError):
    """已确认归属的快照超过保留期。"""


def _read(directory: int, account_id: int, attempt_id: str, now_ms: int) -> tuple[dict, os.stat_result]:
    descriptor = os.open(attempt_id + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CAPTURE_BYTES:
            raise ValueError('采集文件类型或大小无效')
        data = source.read(MAX_CAPTURE_BYTES + 1)
    if len(data) > MAX_CAPTURE_BYTES:
        raise ValueError('采集文件超出读取上限')
    value = json.loads(data)
    if (not isinstance(value, dict) or type(value.get('schema_version')) is not int or value.get('schema_version') != 1
            or type(value.get('account_id')) is not int or value.get('account_id') != account_id or value.get('attempt_id') != attempt_id
            or value.get('stage') != 'cc_prepared'):
        raise ValueError('采集文件归属或阶段无效')
    captured = value.get('captured_at_ms')
    if type(captured) is not int or captured <= 0 or captured > now_ms + 300_000:
        raise ValueError('采集文件时间无效')
    return value, metadata


def read_capture(root: Path, account_id: int, attempt_id: str, *, now_ms: int | None = None) -> dict:
    """只读打开归属匹配的快照，拒绝链接、路径穿越及超限文件。

    :param root: 从已绑定环境解析的账号根目录。
    :param account_id: 网关账号 ID。
    :param attempt_id: 诊断尝试的标准 UUID。
    :param now_ms: 可注入的 UTC 毫秒，省略时取当前时间。
    :return: 组装快照；缺失抛出 FileNotFoundError，损坏抛出 ValueError。
    """
    if str(uuid.UUID(attempt_id)) != attempt_id:
        raise ValueError('尝试标识格式无效')
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    directory = directory_fd(root / 'flows/api/cc-prepared')
    try:
        value, _ = _read(directory, account_id, attempt_id, now_ms)
    finally:
        os.close(directory)
    if value['captured_at_ms'] < now_ms - RETENTION_MS:
        raise CaptureExpired('采集文件已超过七天保留期')
    return value


def cleanup_captures(root: Path, account_id: int, *, now_ms: int | None = None,
        stopping: Callable[[], bool] = lambda: False) -> Iterator[dict[str, int]]:
    """逐文件返回清理计数，调用者按预算暂停并继续迭代。

    :param root: 持久环境根目录。
    :param account_id: 当前唯一网关账号归属。
    :param now_ms: 可注入的 UTC 毫秒，默认逐文件读取当前时间。
    :param stopping: 服务停止标记，删除前再次核对。
    :return: 每个目录项的扫描、删除和失败计数；生成器关闭时释放目录。
    """
    directory = directory_fd(root / 'flows/api/cc-prepared')
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                result = {'scanned': 1, 'deleted': 0, 'failed': 0}
                try:
                    attempt_id = entry.name.removesuffix('.json')
                    if not entry.name.endswith('.json') or str(uuid.UUID(attempt_id)) != attempt_id:
                        yield result
                        continue
                    current_ms = int(time.time() * 1000) if now_ms is None else now_ms
                    value, original = _read(directory, account_id, attempt_id, current_ms)
                    if value['captured_at_ms'] < current_ms - RETENTION_MS and not stopping():
                        current = os.stat(entry.name, dir_fd=directory, follow_symlinks=False)
                        # 原子重命名可能在读取后发布另一文件，旧身份不能授权删除新文件。
                        identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
                        if stat.S_ISREG(current.st_mode) and identity(current) == identity(original):
                            os.unlink(entry.name, dir_fd=directory)
                            result['deleted'] = 1
                except FileNotFoundError:
                    pass
                except (ValueError, OSError):
                    result['failed'] = 1
                yield result
    finally:
        os.close(directory)
