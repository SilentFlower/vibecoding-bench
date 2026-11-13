"""将账号镜像来源与平台发布身份分开，保留精确实例归属证明。"""
from __future__ import annotations

import os
import re

from runtime_files import atomic_json
from runtime_names import matches_image_reference
from system_update_contract import BUILD_RE, strict_json, safe_read


def configured_release(runtime) -> str:
    """读取当前配置的账号镜像发布身份。

    :param runtime: AccountRuntime 或原测试替身。
    :return: 账号来源批次。
    """
    return getattr(runtime, 'account_release_id', runtime.release_id) if os.environ.get('V3_UPDATE_GATE_DIR') else runtime.release_id


def image_origin(runtime, row: dict) -> dict | None:
    """读取私有镜像来源，核对环境身份和协议。

    :param runtime: AccountRuntime。
    :param row: 实际环境记录。
    :return: 已启用更新底座时返回来源，legacy 返回 None。
    """
    if not os.environ.get('V3_UPDATE_GATE_DIR'):
        return None
    path = runtime._root(row) / 'runtime/account-image.json'
    value = strict_json(safe_read(path, private=True))
    if (set(value) != {'schema_version', 'environment_id', 'release', 'reference', 'image_id', 'protocol'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or type(value['protocol']) is not int or value['protocol'] != 1
            or value['environment_id'] != row['environment_id']
            or not isinstance(value['release'], str) or not BUILD_RE.fullmatch(value['release'])
            or not isinstance(value['image_id'], str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', value['image_id'])
            or not matches_image_reference(value['reference'], 'account', value['release'])):
        raise ValueError('账号镜像来源证明无效，需要先对账')
    return value


def save_image_origin(runtime, row: dict) -> None:
    """在受控创建角色前固化经过实际镜像核验的来源。

    :param runtime: AccountRuntime。
    :param row: 本环境持久记录。
    :return: None。
    """
    if not os.environ.get('V3_UPDATE_GATE_DIR'):
        return
    image = runtime.client.images.get(runtime.image)
    labels = image.attrs['Config'].get('Labels') or {}
    release = configured_release(runtime)
    if (labels.get('vibebench.account-runtime-protocol') != '1'
            or labels.get('vibebench.system-update-protocol') != '1'
            or labels.get('vibebench.release') != release
            or labels.get('vibebench.role') != 'account' or labels.get('vibebench.product') != 'v3'):
        raise ValueError('账号镜像缺少受信运行协议')
    atomic_json(runtime._root(row) / 'runtime/account-image.json', {'schema_version': 1,
        'environment_id': row['environment_id'], 'release': release, 'reference': runtime.image,
        'image_id': image.attrs['Id'], 'protocol': 1})


def role_release(runtime, row: dict) -> str:
    """取得环境原始来源，避免平台更新改写旧实例身份。

    :param runtime: AccountRuntime。
    :param row: 环境记录。
    :return: 环境来源发布号。
    """
    origin = image_origin(runtime, row)
    return origin['release'] if origin else configured_release(runtime)
