"""读取账号私有目录中的 CC 组装后快照。"""
import json
import os
import stat
import uuid
from pathlib import Path

MAX_CAPTURE_BYTES = 6 * 1024 * 1024


def read_capture(root: Path, account_id: int, attempt_id: str) -> dict:
    """只读打开归属匹配的快照，拒绝链接、路径穿越及超限文件。

    :param root: 从已绑定环境解析的账号根目录。
    :param account_id: 网关账号 ID。
    :param attempt_id: 诊断尝试的标准 UUID。
    :return: 组装快照；缺失抛出 FileNotFoundError，损坏抛出 ValueError。
    """
    if str(uuid.UUID(attempt_id)) != attempt_id:
        raise ValueError('尝试标识格式无效')
    directory = root / 'flows/api/cc-prepared'
    for path in (root, root / 'flows', root / 'flows/api', directory):
        if path.is_symlink():
            raise ValueError('采集目录归属无效')
    descriptor = os.open(directory / (attempt_id + '.json'), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CAPTURE_BYTES:
            raise ValueError('采集文件类型或大小无效')
        data = source.read(MAX_CAPTURE_BYTES + 1)
    if len(data) > MAX_CAPTURE_BYTES:
        raise ValueError('采集文件超出读取上限')
    value = json.loads(data)
    if (not isinstance(value, dict) or value.get('schema_version') != 1
            or value.get('account_id') != account_id or value.get('attempt_id') != attempt_id
            or value.get('stage') != 'cc_prepared'):
        raise ValueError('采集文件归属或阶段无效')
    return value
