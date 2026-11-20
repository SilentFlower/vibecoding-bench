"""在候选停止接单前注册项目内容，启动时读取已校验的冻结目录。"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import sys
from pathlib import Path

from system_update_contract import (PROJECT_LIBRARY_RECEIPT_LIMIT, project_library_receipt_name,
    read_prepared_project_document, safe_read, strict_json, verify_prepared_metadata)


def prepare_library(source: Path, data: Path) -> dict:
    """完整校验并注册候选项目库。:param source: 包内内容根。:param data: 隔离数据挂载。:return: 准备结果。"""
    from project_library import ProjectLibrary

    library = ProjectLibrary(source).install(data)
    root = library.root
    manifest = library.catalog_document.get('project_manifest', 'project.json')

    def checksum(path):
        return hashlib.sha256(read_prepared_project_document(root, path)).hexdigest()

    identity = root.stat()
    return {'source': str(source), 'digest': library.digest, 'inode': identity.st_ino, 'device': identity.st_dev,
        'catalog': checksum('catalog.json'),
        'projects': {key: checksum(Path('projects') / key / manifest) for key in library.projects},
        'environments': {key: checksum(Path('environments') / key / 'profile/profile.json') for key in library.environments}}


def load_prepared_library(source: Path, data: Path):
    """读取宿主已确认的项目库。:param source: 当前镜像内容根。:param data: 调度器数据根。:return: 已注册库。"""
    from project_library import ProjectDefinition, ProjectLibrary

    release = os.environ['V3_RELEASE']
    path = Path(os.environ['V3_UPDATE_SOCKET_DIR']) / project_library_receipt_name(release)
    receipt = strict_json(safe_read(path, PROJECT_LIBRARY_RECEIPT_LIMIT, private=True), PROJECT_LIBRARY_RECEIPT_LIMIT)
    expected = {'deployment': os.environ['V3_DEPLOYMENT_ID'], 'release': release,
        'image_digest': os.environ['V3_PREPARED_PROJECT_LIBRARY_IMAGE'],
        'reference': os.environ['V3_CONTROL_IMAGE'], 'source': str(source)}
    entry = receipt.get('entry')
    if (receipt.get('binding') != expected or not isinstance(entry, dict)
            or entry.get('source') != str(source)):
        raise ValueError('项目库准备记录与当前候选不符')
    catalog, projects, environments = verify_prepared_metadata(data, entry)
    root = data / 'project-library' / 'releases' / entry['digest']
    # 树和离线制品已经完整验证。新工作区及离线制品使用时仍沿原摘要校验。
    library = ProjectLibrary.__new__(ProjectLibrary)
    library.root, library.digest = root, entry['digest']
    library.catalog_document, library.schema, library.version = catalog, catalog['schema'], catalog['version']
    library.projects = {key: ProjectDefinition(root / 'projects' / key, value) for key, value in projects.items()}
    library.environments = environments
    return library


def _stop_preparation(signum, _frame):
    # 让出注册流程的 finally，避免中断时遗留本次项目库暂存目录。
    raise SystemExit(128 + signum)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, _stop_preparation)
    print(json.dumps(prepare_library(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False))
