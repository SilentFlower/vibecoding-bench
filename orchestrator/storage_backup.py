"""持久状态精简快照与离线恢复校验，不连接账号或修改原始数据。"""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
from stat import S_ISSOCK
import tempfile

from storage_maintenance import preserve_metadata, read_storage_json, tree_inventory


DATABASES = ('gateway/gateway.sqlite', 'bench/db.sqlite')


def _database_digest(database: sqlite3.Connection) -> str:
    checksum = hashlib.sha256()
    for statement in database.iterdump():
        checksum.update(statement.encode('utf-8'))
        checksum.update(b'\n')
    return checksum.hexdigest()


def _write_private(path: Path, value: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        json.dump(value, output, ensure_ascii=False, sort_keys=True)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())


def create_backup_data(root: Path, target: Path, *, excluded: dict[str, dict],
                       mode: str, configuration: dict[str, Path] | None = None) -> dict:
    """复制关键状态并生成一致数据库及恢复清单。

    :param root: 已停止且归属已核验的数据根。
    :param target: 调用方新建的私有备份目录。
    :param excluded: 明确排除路径及其固定恢复来源；完整模式为空。
    :param mode: essential 或 full。
    :param configuration: 需要额外保留的部署配置文件。
    :return: 不含凭据内容的备份文件与数据库计数。
    """
    if mode not in ('essential', 'full') or (mode == 'full' and excluded):
        raise ValueError('备份模式与排除清单不一致')
    ignored = set(excluded)
    database_paths = {relative + suffix for relative in DATABASES for suffix in ('', '-wal', '-shm')}
    before = tree_inventory(root, ignored | database_paths)

    def ignore(directory: str, names: list[str]) -> list[str]:
        """只排除明确路径与运行 socket，不跟随 HOME 中的链接。"""
        result = []
        for name in names:
            path = Path(directory) / name
            relative = str(path.relative_to(root))
            if relative in ignored | database_paths or S_ISSOCK(path.lstat().st_mode):
                result.append(name)
        return result

    destination = target / 'data'
    shutil.copytree(root, destination, symlinks=True, ignore=ignore)
    preserve_metadata(destination, before)
    if tree_inventory(destination, database_paths) != before:
        raise ValueError('备份数据与原状态不一致')
    databases = {}
    for relative in DATABASES:
        source = root / relative
        if source.is_symlink():
            raise ValueError('持久数据库不能为符号链接')
        if not source.exists():
            continue
        metadata = source.stat()
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as current:
            current.execute('BEGIN')
            expected = _database_digest(current)
            with closing(sqlite3.connect(output)) as snapshot:
                current.backup(snapshot)
                if snapshot.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                    raise ValueError('备份数据库完整性检查未通过')
                if _database_digest(snapshot) != expected:
                    raise ValueError('备份数据库逻辑状态不一致')
        output.chmod(0o600)
        os.chown(output, metadata.st_uid, metadata.st_gid, follow_symlinks=False)
        databases[relative] = expected
    if tree_inventory(root, ignored | database_paths) != before:
        raise ValueError('备份期间原始业务状态发生变化')
    config_root = target / 'config'
    if configuration:
        config_root.mkdir(mode=0o700)
        for name, source in configuration.items():
            if Path(name).name != name or not name or source.is_symlink() or not source.is_file():
                raise ValueError('部署备份配置路径无效')
            output = config_root / name
            shutil.copy2(source, output, follow_symlinks=False)
            metadata = source.stat()
            os.chown(output, metadata.st_uid, metadata.st_gid, follow_symlinks=False)
    # sqlite3.Connection 的 with 只结束事务；显式关闭后再盘点，避免 WAL/SHM 随 GC 消失。
    data = tree_inventory(destination, durable=True)
    config = tree_inventory(config_root, durable=True) if configuration else None
    document = {'schema': 2, 'mode': mode, 'data': data, 'configuration': config,
        'databases': databases, 'excluded': excluded}
    _write_private(target / 'backup-files.json', document)
    return {'files': sum(item['kind'] == 'file' for item in data.values()),
        'bytes': sum(item.get('size', 0) for item in data.values()), 'databases': len(databases),
        'excluded_paths': len(excluded), 'mode': mode}


def verify_backup_data(target: Path) -> dict:
    """在独立目录实际复制并核对新格式备份，失败不修改源数据。

    :param target: 包含 backup-files.json 的私有备份根。
    :return: 恢复文件、权限、链接与数据库通过的计数。
    """
    if target.is_symlink() or not target.is_dir():
        raise ValueError('备份目录不能是链接或缺失')
    document = read_storage_json(target / 'backup-files.json')
    if not isinstance(document, dict):
        raise ValueError('备份恢复清单必须是对象')
    if document.get('schema') != 2 or document.get('mode') not in ('essential', 'full'):
        raise ValueError('备份恢复清单版本不支持')
    data = document['data']
    if tree_inventory(target / 'data') != data:
        raise ValueError('备份文件已损坏或被替换')
    configuration = document['configuration']
    if configuration is not None and tree_inventory(target / 'config') != configuration:
        raise ValueError('备份配置已损坏或被替换')
    with tempfile.TemporaryDirectory(prefix='.v3-restore-check-', dir=target.parent) as temporary:
        restored = Path(temporary) / 'data'
        shutil.copytree(target / 'data', restored, symlinks=True)
        preserve_metadata(restored, data)
        if tree_inventory(restored) != data:
            raise ValueError('隔离恢复后的业务文件不一致')
        if configuration is not None:
            config_root = Path(temporary) / 'config'
            shutil.copytree(target / 'config', config_root, symlinks=True)
            preserve_metadata(config_root, configuration)
            if tree_inventory(config_root) != configuration:
                raise ValueError('隔离恢复后的配置不一致')
        for relative, expected in document['databases'].items():
            if relative not in DATABASES:
                raise ValueError('恢复清单含未知数据库路径')
            with closing(sqlite3.connect((restored / relative).as_uri() + '?mode=ro', uri=True)) as database:
                if database.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ValueError('隔离恢复数据库完整性检查未通过')
                if _database_digest(database) != expected:
                    raise ValueError('隔离恢复数据库逻辑状态不一致')
    return {'status': 'passed', 'files': sum(item['kind'] == 'file' for item in data.values()),
        'databases': len(document['databases']), 'isolated_restore': True}
