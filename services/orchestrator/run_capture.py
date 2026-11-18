"""为原节点Run生成有界公开抓包投影，仅暂存脱敏读取器需要的元数据。"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from capture_artifacts import capture_file_preview, capture_summary
from run_artifacts import list_workspace_files
from runtime_files import directory_fd


def run_capture(base: Path, *, running: bool, relative: str | None = None) -> dict:
    """通过固定目录描述符复制有界元数据，再复用原公开抓包规则。

    :param base: 按原Run计算的物理流组。
    :param running: 原中央状态及节点实际回执共同确定的活动事实。
    :param relative: 原公开预览白名单相对路径。
    :return: 原摘要或白名单预览；超限保持明确错误。
    """
    roots, files, total = [(base, '')], [], 0
    try:
        descriptor = directory_fd(base)
    except FileNotFoundError:
        if relative is not None:
            raise FileNotFoundError('原Run抓包文件尚未提供') from None
        return capture_summary(base, running=running)
    try:
        with os.scandir(descriptor) as children:
            for count, child in enumerate(children, 1):
                if count > 10000:
                    raise ValueError('原Run抓包目录超过读取上限')
                # 原续聊兼容入口只允许指向同环境下另一个受管流组。
                if child.name.startswith('continue-') and child.is_symlink():
                    target = (base / child.name).resolve(strict=True)
                    if target.parent != base.parent or not target.name.startswith('group-'):
                        raise ValueError('原Run续聊抓包入口归属错误')
                    roots.append((target, child.name + '/'))
    finally:
        os.close(descriptor)
    with tempfile.TemporaryDirectory(prefix='node-run-public-capture-') as temporary:
        staging = Path(temporary)
        for root, prefix in roots:
            for item in list_workspace_files(root):
                if item['type'] != 'file':
                    continue
                path = Path(item['path'])
                if 'cli' in path.parts or path.name == 'passive-quota.jsonl':
                    continue
                files.append({'path': prefix + item['path'], 'size': item['size']})
                if len(files) > 10000:
                    raise ValueError('原Run抓包文件超过读取上限')
                if path.name not in ('capture_index.json', 'capture-status.json', 'tls_clienthello.jsonl'):
                    continue
                parent = directory_fd((root / path).parent)
                try:
                    source = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                finally:
                    os.close(parent)
                with os.fdopen(source, 'rb') as stream:
                    info = os.fstat(stream.fileno())
                    total += info.st_size
                    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                            or info.st_size > 8 * 1024 * 1024 or total > 64 * 1024 * 1024):
                        raise ValueError('原Run抓包元数据类型或大小超过读取上限')
                    content = stream.read(info.st_size + 1)
                    if len(content) != info.st_size:
                        raise ValueError('原Run抓包元数据在读取期间变化')
                target = staging / prefix / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        if relative is not None:
            value = capture_file_preview(staging, relative)
        else:
            value = capture_summary(staging, running=running, files=sorted(files, key=lambda item: item['path']))
        if len(json.dumps(value, ensure_ascii=False).encode()) > 192 * 1024:
            raise ValueError('原Run公开抓包投影超过读取上限')
        return value
