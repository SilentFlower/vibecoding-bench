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
import uuid
import re

from storage_maintenance import preserve_metadata, read_storage_json, tree_inventory
from cluster_backup_index import cluster_backup_scope, verify_cluster_correspondence


DATABASES = ('gateway/gateway.sqlite', 'bench/db.sqlite','node-execution.sqlite','node-execution-local.sqlite',
    'bench/node-execution-local.sqlite')


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
                       mode: str, configuration: dict[str, Path] | None = None, cluster_epoch: str | None = None) -> dict:
    """复制关键状态并生成一致数据库及恢复清单。

    :param root: 已停止且归属已核验的数据根。
    :param target: 调用方新建的私有备份目录。
    :param excluded: 明确排除路径及其固定恢复来源；完整模式为空。
    :param mode: essential 或 full。
    :param configuration: 需要额外保留的部署配置文件。
    :param cluster_epoch: 全部节点停机后共用的备份批次；省略时生成独立批次。
    :return: 不含凭据内容的备份文件与数据库计数。
    """
    if mode not in ('essential', 'full') or (mode == 'full' and excluded):
        raise ValueError('备份模式与排除清单不一致')
    if cluster_epoch is not None and re.fullmatch(r'[a-f0-9]{32}',cluster_epoch) is None:
        raise ValueError('集群备份批次无效')
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
    scope=cluster_backup_scope(destination)
    if scope is not None:
        epoch=cluster_epoch or uuid.uuid4().hex
        if re.fullmatch(r'[a-f0-9]{32}',epoch) is None:
            raise ValueError('集群备份批次无效')
        document['cluster']={**scope,'epoch':epoch}
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
            with closing(sqlite3.connect((restored / relative).as_uri() + '?mode=ro&immutable=1', uri=True)) as database:
                if database.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ValueError('隔离恢复数据库完整性检查未通过')
                if _database_digest(database) != expected:
                    raise ValueError('隔离恢复数据库逻辑状态不一致')
        if 'cluster' in document:
            scope={key:value for key,value in document['cluster'].items() if key!='epoch'}
            if scope!=cluster_backup_scope(restored) or re.fullmatch(r'[a-f0-9]{32}',str(document['cluster'].get('epoch',''))) is None:
                raise ValueError('备份集群安装身份或批次索引不一致')
    return {'status': 'passed', 'files': sum(item['kind'] == 'file' for item in data.values()),
        'databases': len(document['databases']), 'isolated_restore': True}


def verify_cluster_backup(central: Path, node_backups: list[Path]) -> dict:
    """验证同批中央及全部Node备份，并逐项核对冻结归属。

    :param central: 原中央完整性已可离线验证的备份。
    :param node_backups: 同一离线批次的Node备份目录。
    :return: 组合范围、节点/环境及原维护恢复计数。
    """
    verify_backup_data(central)
    document=read_storage_json(central/'backup-files.json')
    scope=document.get('cluster',{})
    if scope.get('kind')!='central':
        raise ValueError('中央备份缺少集群范围索引')
    marker=read_storage_json(central/'.v3-backup.json')
    if (not isinstance(marker,dict) or marker.get('schema')!=2
            or marker.get('files_manifest_sha256')!=hashlib.sha256((central/'backup-files.json').read_bytes()).hexdigest()):
        raise ValueError('中央备份缺少完整完成记录')
    nodes={}
    for target in node_backups:
        verify_backup_data(target)
        item=read_storage_json(target/'backup-files.json').get('cluster',{})
        if (item.get('kind')!='node' or item.get('deployment_id')!=scope['deployment_id']
                or item.get('epoch')!=scope['epoch'] or item.get('node_key') in nodes):
            raise ValueError('Node备份的安装、批次或唯一范围不一致')
        marker=read_storage_json(target/'.v3-node-backup.json')
        if (not isinstance(marker,dict) or marker.get('schema')!=1 or marker.get('node_key')!=item['node_key']
                or marker.get('epoch')!=scope['epoch'] or marker.get('deployment_id')!=scope['deployment_id']
                or marker.get('files_manifest_sha256')!=hashlib.sha256((target/'backup-files.json').read_bytes()).hexdigest()):
            raise ValueError('Node备份缺少同批完整完成记录')
        nodes[item['node_key']]=target/'data'
    if any(item['node_key'] not in nodes for item in scope['nodes']):
        raise ValueError('集群备份仍缺少已登记Node的资料')
    result=verify_cluster_correspondence(central/'data',nodes)
    return {'status':'passed','scope':'cluster','nodes':len(scope['nodes']),
        'isolated_restore':True,**result}
