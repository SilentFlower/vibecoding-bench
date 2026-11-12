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


def _validate_stage_details(value: dict) -> None:
    """校验新增的可选阶段合同；历史缺字段继续可读。"""
    statuses = {'complete', 'truncated', 'unavailable', 'failed', 'incomplete'}
    for name, collection, limit, actions in [
            ('header_policy', 'decisions', 1024, {'keep', 'drop', 'runtime', 'context'}),
            ('body_changes', 'items', 128, {'added', 'removed', 'changed'})]:
        if name not in value:
            continue
        detail = value[name]
        if (not isinstance(detail, dict) or detail.get('status') not in statuses
                or detail.get('source') != ('native_header_policy' if name == 'header_policy' else 'observed_diff')
                or not isinstance(detail.get(collection), list) or len(detail[collection]) > limit):
            raise ValueError('采集阶段明细类型或数量无效')
        if 'note' in detail and (not isinstance(detail['note'], str) or len(detail['note']) > 1024):
            raise ValueError('采集阶段说明无效')
        for item in detail[collection]:
            key = 'name' if name == 'header_policy' else 'path'
            if (not isinstance(item, dict) or item.get('action') not in actions
                    or any(not isinstance(item.get(field), str) for field in (key, 'reason'))
                    or len(item['reason'].encode()) > 8192
                    or len(item[key].encode()) > (128*1024 if key == 'name' else 2048)):
                raise ValueError('采集处理项字段无效')
        if name == 'header_policy':
            if sum(len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode()) for item in detail[collection]) > 128*1024:
                raise ValueError('头部处理明细超出预算')
            for key in ('observed_count', 'stored_count'):
                if key in detail and (type(detail[key]) is not int or detail[key] < len(detail[collection])):
                    raise ValueError('头部处理明细计数无效')
            if 'stored_count' in detail and detail['stored_count'] != len(detail[collection]):
                raise ValueError('头部处理实际保存数量不符')
    if 'ingress' in value:
        preview = value['ingress']
        if (not isinstance(preview, dict) or preview.get('status') not in statuses
                or not isinstance(preview.get('body'), str) or len(preview['body'].encode()) > 1024*1024
                or not isinstance(preview.get('headers'), list) or len(preview['headers']) > 4096
                or type(preview.get('body_truncated')) is not bool or type(preview.get('headers_truncated')) is not bool
                or type(preview.get('captured_at_ms')) is not int or preview['captured_at_ms'] <= 0
                or preview['captured_at_ms'] > value['captured_at_ms'] + 300_000
                or type(preview.get('original_body_bytes')) is not int or preview['original_body_bytes'] < 0
                or not isinstance(preview.get('original_body_sha256'), str)
                or len(preview['original_body_sha256']) != 64
                or any(c not in '0123456789abcdefABCDEF' for c in preview['original_body_sha256'])):
            raise ValueError('入口预览字段无效')
        for pair in preview['headers']:
            if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(item, str) for item in pair):
                raise ValueError('入口请求头明细无效')
        if (sum(len(part.encode()) for pair in preview['headers'] for part in pair) > 128*1024
                or not isinstance(value.get('body'), str)
                or len(value['body'].encode()) + len(preview['body'].encode()) > 2*1024*1024):
            raise ValueError('多阶段预览超出共同预算')
    if 'stages' in value:
        stages = value['stages']
        if not isinstance(stages, list) or len(stages) > 4:
            raise ValueError('阶段状态数量无效')
        names = set()
        for stage in stages:
            if (not isinstance(stage, dict) or stage.get('stage') not in {'ingress', 'header_policy', 'cc_prepared', 'wire_final'}
                    or stage['stage'] in names or stage.get('status') not in statuses
                    or any(not isinstance(stage.get(key), str) or len(stage[key]) > 512 for key in ('source', 'representation'))):
                raise ValueError('阶段状态字段无效')
            names.add(stage['stage'])
            if 'note' in stage and (not isinstance(stage['note'], str) or len(stage['note']) > 1024):
                raise ValueError('阶段状态说明无效')


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
    _validate_stage_details(value)
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
