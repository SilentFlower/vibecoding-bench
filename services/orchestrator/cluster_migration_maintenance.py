"""识别已暂停的原迁移，允许组件维护保留原租约和未完成资料。"""
from __future__ import annotations

import json
import re
import hashlib


def paused_migration_record(migration: dict) -> dict | None:
    """读取可保留的提交前暂停操作。:param migration: 持久迁移行。:return: 原记录或None。"""
    record = json.loads(migration['record_json'])
    if (migration['phase'] != 'reconcile'
            or record.get('last_confirmed_phase') not in ('source_fenced', 'exporting', 'importing', 'verified')
            or 'cancellation' in record.get('checkpoints', {})
            or not re.fullmatch('[a-f0-9]{32}', migration['operation_id'])):
        return None
    return record


def paused_migration_lease(database, environment: dict, snapshot: dict) -> dict | None:
    """核对停止环境的原迁移占用，维护期间保持原账号关闭。

    :param database: 中央数据库连接工厂。
    :param environment: 当前中央环境。
    :param snapshot: 实际网关租约；独立账号传递空占用。
    :return: 带原记录的迁移行；实际活动或身份不符返回None。
    """
    if (environment.get('state') not in ('ready', 'stopped')
            or any(snapshot.get(key) != 0 for key in ('active', 'waiting', 'importing'))):
        return None
    connection = database()
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='node_migrations'").fetchone():
            return None
        stored = connection.execute("SELECT m.*,n.kind AS source_kind FROM node_migrations m JOIN account_node_assignments a ON a.account_id=m.account_id "
            'JOIN cluster_nodes n ON n.id=m.source_node_id '
            "WHERE m.account_id=? AND m.phase='reconcile' AND a.phase='reconcile' AND a.node_id=m.source_node_id",
            (environment['account_id'],)).fetchone()
        if stored is None:
            return None
        migration = dict(stored)
        if environment['state'] != 'stopped' and migration['source_kind'] != 'ssh':
            return None
        record = paused_migration_record(migration)
        assignment = connection.execute('SELECT revision FROM account_node_assignments WHERE account_id=?',
            (environment['account_id'],)).fetchone()
    finally:
        connection.close()
    if (record is None or record.get('environment_id') != environment['environment_id']
            or record.get('source_generation') != environment['generation']
            or record.get('source_fingerprint_sha256') != hashlib.sha256(environment['fingerprint_json'].encode()).hexdigest()
            or assignment['revision'] != record.get('source_revision')):
        return None
    expected = record.get('checkpoints', {}).get('gateway_lease')
    holders = snapshot.get('holders')
    if expected is None:
        if holders != [] or snapshot.get('lease') is not None:
            return None
    elif (not isinstance(holders, list) or len(holders) != 1
            or not isinstance(holders[0], dict)
            or expected.get('owner') != 'node-migration:' + migration['operation_id']
            or not isinstance(expected.get('generation'), str) or not expected['generation']
            or any(holders[0].get(key) != expected.get(key) for key in ('owner', 'generation'))
            or holders[0].get('exclusive') is not True):
        return None
    return {**migration, 'record': record}
