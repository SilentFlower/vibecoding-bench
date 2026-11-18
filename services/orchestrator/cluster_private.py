"""节点控制进程启动时核对安装与私有维护门禁的归属。"""
from __future__ import annotations

import os
from pathlib import Path
from stat import S_ISDIR, S_ISREG

from runtime_files import directory_fd
from system_update_contract import strict_json
from system_update_gate import validate_gate


def initialize_node_private(data: Path, node_key: str, deployment: str) -> None:
    """将SSH创建的合法私有门禁交给控制容器root，保留原维护状态。

    :param data: 已由SSHbootstrap建立的精确数据根。
    :param node_key: 原安装节点。
    :param deployment: 原部署。
    :return: None；缺失、损坏或未知权限保持原资料并拒绝启动。
    """
    if os.geteuid() != 0:
        raise ValueError('节点控制组件需要原管理容器的root权限')
    root = directory_fd(data)
    try:
        marker = os.open('cluster-node.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
        try:
            metadata = os.fstat(marker)
            if (not S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_mode & 0o077
                    or metadata.st_size > 8192):
                raise ValueError('节点安装标记权限或类型无效')
            owner = strict_json(os.read(marker, 8193), 8192)
            if owner != {'protocol': 1, 'node_key': node_key, 'deployment_id': deployment}:
                raise ValueError('节点控制组件的安装归属不一致')
            installer_uid = metadata.st_uid
        finally:
            os.close(marker)
        root_metadata = os.fstat(root)
        if root_metadata.st_uid not in (0, installer_uid) or root_metadata.st_mode & 0o077:
            raise ValueError('节点数据根权限或归属无效')
        gate = os.open('system-update-gate', os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        try:
            gate_metadata = os.fstat(gate)
            if (not S_ISDIR(gate_metadata.st_mode) or gate_metadata.st_uid not in (0, installer_uid)
                    or gate_metadata.st_mode & 0o077):
                raise ValueError('节点维护目录权限或归属无效')
            record = os.open('admission.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=gate)
            try:
                information = os.fstat(record)
                if (not S_ISREG(information.st_mode) or information.st_nlink != 1 or information.st_mode & 0o077
                        or information.st_uid not in (0, installer_uid) or information.st_size > 8192):
                    raise ValueError('节点维护记录权限或归属无效')
                validate_gate(strict_json(os.read(record, 8193), 8192), deployment)
                # 只改变合法旧记录的服务归属；blocked、epoch和原操作继续保留。
                os.fchown(record, 0, 0)
                os.fsync(record)
            finally:
                os.close(record)
            os.fchown(gate, 0, 0)
            os.fsync(gate)
        finally:
            os.close(gate)
    finally:
        os.close(root)
