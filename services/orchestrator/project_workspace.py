"""本机和节点共用的经典项目首次物化合同。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4
from typing import Callable

from project_library import materialize_snapshot, read_document, snapshot_tree, write_document
from runtime_files import directory_fd


def publish_project_workspace(data: Path, target: Path, marker: Path, instance_id: int,
                              seed_digest: str, seed: Callable[[], Path], started: bool, allowed, *,
                              identity_key: str = 'instance_id', staging_root: Path | None = None) -> None:
    """按原实例标记发布seed，已有现场始终按原归属核对。

    :param data: 执行方数据根。
    :param target: 服务端计算的实际工作目录。
    :param marker: root所有的原实例物化标记。
    :param instance_id: 中央原实例。
    :param seed_digest: 原冻结seed摘要。
    :param seed: 只在首次物化时解析的同批只读seed。
    :param started: 中央是否已保存已开始事实。
    :param allowed: 发布前复核原准入的函数。
    :param identity_key: 原实例或场景标记字段，场景始终核对完整标记。
    :param staging_root: 可选执行方随环境保留的暂存目录。
    :return: None；未知目录和丢失现场保持明确失败。
    """
    relative = str(target.relative_to(data))
    if identity_key not in ('instance_id','scenario_id'):
        raise ValueError('项目物化标记身份类型无效')
    expected = {identity_key:instance_id,'seed_digest':seed_digest,'workspace_relative':relative}
    if started:
        if not target.is_dir() or target.is_symlink():
            raise ValueError('已开始项目的工作目录缺失或被替换')
        descriptor = directory_fd(target)
        os.close(descriptor)
        if identity_key=='scenario_id' and (not marker.exists() or read_document(marker)!=expected):
            raise ValueError('场景工作区发布证明缺失或冲突')
        return
    if marker.exists() or marker.is_symlink():
        if marker.is_symlink() or read_document(marker)!=expected:
            raise ValueError('项目发布标记不一致')
        descriptor = directory_fd(target)
        os.close(descriptor)
        return
    if target.exists() or target.is_symlink():
        raise ValueError('项目目录已存在但没有可核对的发布标记')
    objects = data/'project-artifacts/objects'
    baseline = snapshot_tree(seed(),objects)
    if baseline['digest']!=seed_digest:
        raise ValueError('项目seed与原冻结内容不一致')
    write_document(data/'project-artifacts/manifests'/(baseline['digest']+'.json'),baseline)
    staging = (staging_root if staging_root is not None else data/'project-staging')/uuid4().hex
    materialize_snapshot(baseline,objects,staging)
    try:
        for path in [staging,*staging.rglob('*')]:
            os.chown(path,1000,1000,follow_symlinks=False)
            path.chmod(0o755 if path.is_dir() else 0o644)
        descriptor = directory_fd(target.parent,create=True)
        try:
            os.fchown(descriptor,1000,1000)
        finally:
            os.close(descriptor)
        # 标记先于发布落盘；未知目录不能覆盖成另一份seed。
        write_document(marker,expected)
        if not allowed():
            marker.unlink(missing_ok=True)
            raise ValueError('项目发布前批次已暂停或停止')
        os.rename(staging,target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
