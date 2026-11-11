"""两库共享的迁移登记校验与稳定合同，不导入运行服务。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def registry_contract(value: dict) -> str:
    """计算规范登记的稳定摘要。:param value: 已校验登记。:return: SHA256。"""
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_registry(value: dict, database: str) -> dict:
    """校验有序且只声明兼容迁移的登记。

    :param value: 完整登记对象。
    :param database: 固定数据库名称。
    :return: 原登记；未知字段、摘要或链不完整时拒绝。
    """
    if (set(value) != {'schema_version', 'database', 'steps'} or type(value['schema_version']) is not int
            or value['schema_version'] != 1 or value['database'] != database
            or not isinstance(value['steps'], list) or not 1 <= len(value['steps']) <= 10000):
        raise ValueError('数据库迁移登记格式无效')
    seen = set()
    for version, step in enumerate(value['steps'], 1):
        if (not isinstance(step, dict) or set(step) != {'id', 'version', 'predecessor', 'checksum', 'engine', 'kind', 'rollback_mode'}
                or not isinstance(step['id'], str) or not re.fullmatch(database + r'\.[a-z][a-z0-9_.-]{0,80}', step['id'])
                or step['id'] in seen or type(step['version']) is not int or step['version'] != version
                or type(step['predecessor']) is not int or step['predecessor'] != version - 1
                or not isinstance(step['checksum'], str) or not re.fullmatch('[a-f0-9]{64}', step['checksum'])
                or step['engine'] != 'sqlite' or step['kind'] not in ('schema', 'data') or step['rollback_mode'] != 'compatible'):
            raise ValueError('数据库迁移登记的步骤或前驱无效')
        seen.add(step['id'])
    return value


def load_registry(path: Path, database: str) -> dict:
    """从固定源码读取有界迁移登记。

    :param path: 固定登记文件。
    :param database: 固定库名。
    :return: 校验后的对象。
    """
    if path.is_symlink() or path.stat().st_size > 128 * 1024:
        raise ValueError('数据库迁移登记来源无效')
    return validate_registry(json.loads(path.read_text()), database)
