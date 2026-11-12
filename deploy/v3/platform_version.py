"""正式平台版本的唯一来源与签名说明投影。"""
import re
from pathlib import Path

from system_update_contract import strict_json


VERSION = re.compile(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)')
PREFIX = '平台版本：'


def read_version(path: Path) -> dict:
    """读取受版本控制的正式发行信息。

    :param path: 当前源快照中的元数据。
    :return: 版本与中文变更说明；非法合同抛出 ValueError。
    """
    value = strict_json(path.read_bytes(), 8192)
    if (set(value) != {'schema_version', 'version', 'changes'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or not isinstance(value['version'], str) or not VERSION.fullmatch(value['version'])
            or not isinstance(value['changes'], str) or not value['changes'].strip()
            or len(value['changes']) > 7000):
        raise ValueError('平台版本元数据无效')
    return value


def version_from_changes(changes: str) -> tuple[int, int, int] | None:
    """提取已签名说明中的受控首行，兼容历史纯说明。

    :param changes: 已验签的发行说明。
    :return: 语义版本数字；旧说明返回 None。
    """
    first = changes.split('\n', 1)[0]
    match = VERSION.fullmatch(first.removeprefix(PREFIX)) if first.startswith(PREFIX) else None
    return tuple(map(int, match.groups())) if match else None


def signed_changes(metadata: dict) -> str:
    """生成沿用旧签名合同的可读说明。

    :param metadata: 已校验的唯一版本元数据。
    :return: 版本首行与正式更新说明。
    """
    return f'{PREFIX}{metadata["version"]}\n\n{metadata["changes"].strip()}'


def ensure_forward_version(current: dict, previous: dict) -> None:
    """发布前拒绝版本倒退及不同源码复用版本。

    :param current: 当前待发布的完整发行。
    :param previous: 原受信通道最新完整发行。
    :return: None；同源重跑允许保留版本。
    """
    target, original = version_from_changes(current['changes']), version_from_changes(previous['changes'])
    if target is None:
        raise ValueError('正式发行缺少平台版本')
    if original is None:
        return
    if target < original or (target == original and any(current[role]['revision'] != previous[role]['revision']
            for role in ('control', 'account'))):
        raise ValueError('新的源码发行必须递增平台版本')
