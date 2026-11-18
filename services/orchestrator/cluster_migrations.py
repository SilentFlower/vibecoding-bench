"""人工迁移的持久阶段、归属CAS与失败隔离记录。"""
from __future__ import annotations

import json
import hashlib
import re
import time

from cluster_store import ClusterStore
from cluster_migration_errors import public_failure


_NEXT = {'requested': 'draining', 'draining': 'source_fenced', 'source_fenced': 'exporting',
    'exporting': 'importing', 'importing': 'verified'}
_TERMINAL = {'completed', 'cancelled'}


class NodeMigrations:
    """所有跨节点IO位于短事务外，迁移记录持续关闭账号准入。

    :param store: 与中央账号共用写锁和连接工厂的节点存储。
    """

    def __init__(self, store: ClusterStore) -> None:
        """保存中央权威依赖。:param store: 节点存储。:return: None。"""
        self.store = store

    def get(self, operation_id: str) -> dict:
        """读取内部完整迁移记录。:param operation_id: 原操作。:return: 内部回执和冻结范围。"""
        connection = self.store.database()
        try:
            row = connection.execute('SELECT * FROM node_migrations WHERE operation_id=?', (operation_id,)).fetchone()
            if row is None:
                raise ValueError('迁移操作不存在')
            return {**dict(row), 'record': json.loads(row['record_json'])}
        finally:
            connection.close()

    def begin(self, operation_id: str, account_id: int, target_id: int, revision: int, *, execution: dict | None = None) -> dict:
        """持久登记迁移并关闭账号新准入，相同操作只返回原冻结范围。

        :param operation_id: 调用方分配的唯一操作身份。
        :param account_id: 原账号。
        :param target_id: 管理员选择的节点。
        :param revision: 原分配版本。
        :param execution: 协调器冻结的执行范围，与关闭准入同事务登记。
        :return: 持久迁移记录。
        """
        if not re.fullmatch('[a-f0-9]{32}', operation_id):
            raise ValueError('迁移操作身份无效')
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    existing = connection.execute('SELECT * FROM node_migrations WHERE operation_id=?', (operation_id,)).fetchone()
                    if existing is not None:
                        record = json.loads(existing['record_json'])
                        if (existing['account_id'], existing['target_node_id'], record['source_revision']) != (account_id, target_id, revision):
                            raise ValueError('原迁移操作的冻结范围不一致')
                        if execution is not None and record.get('checkpoints', {}).get('execution', {}).get('version') != execution.get('version'):
                            raise ValueError('原迁移冻结CLI版本已变化')
                    else:
                        assignment = connection.execute('SELECT b.* FROM account_node_assignments b JOIN accounts a ON a.id=b.account_id '
                            'WHERE b.account_id=? AND a.deleted_at IS NULL', (account_id,)).fetchone()
                        if assignment is None or assignment['revision'] != revision or assignment['phase'] != 'ready':
                            raise ValueError('账号归属已变化或已有维护操作')
                        if assignment['node_id'] == target_id:
                            raise ValueError('迁移目标与当前节点相同')
                        target = connection.execute('SELECT * FROM cluster_nodes WHERE id=? AND enabled=1 AND deleted_at IS NULL', (target_id,)).fetchone()
                        if target is None:
                            raise ValueError('目标节点不存在或已暂停接单')
                        source = connection.execute('SELECT * FROM cluster_nodes WHERE id=? AND deleted_at IS NULL',
                            (assignment['node_id'],)).fetchone()
                        for side, node in (('原', source), ('目标', target)):
                            if node is None:
                                raise ValueError(side + '节点归属需要核对')
                            if node['kind'] == 'ssh' and json.loads(node['preparation_json'] or '{}').get('state') != 'prepared':
                                raise ValueError(side + '节点正在同步组件，请完成后再开始迁移')
                        environment = connection.execute('SELECT * FROM account_environments WHERE account_id=?', (account_id,)).fetchone()
                        if environment is None:
                            raise ValueError('账号尚无环境，请选择首次执行节点')
                        if connection.execute("SELECT 1 FROM node_migrations WHERE account_id=? AND phase NOT IN ('completed','cancelled')", (account_id,)).fetchone():
                            raise ValueError('账号已有未收口迁移，请继续原操作')
                        record = {'protocol': 1, 'operation_id': operation_id, 'account_id': account_id,
                            'environment_id': environment['environment_id'], 'source_revision': revision,
                            'source_generation': environment['generation'], 'source_state': environment['state'],
                            'source_fingerprint_sha256': hashlib.sha256(environment['fingerprint_json'].encode()).hexdigest(),
                            'receipts': {}, 'last_confirmed_phase': 'requested'}
                        if execution is not None:
                            record['checkpoints'] = {'execution': execution}
                        now = time.time()
                        connection.execute('INSERT INTO node_migrations(operation_id,account_id,source_node_id,target_node_id,phase,record_json,created_at,updated_at) '
                            "VALUES(?,?,?,?,'requested',?,?,?)", (operation_id, account_id, assignment['node_id'], target_id,
                                json.dumps(record, ensure_ascii=False, allow_nan=False), now, now))
                        result = connection.execute("UPDATE account_node_assignments SET phase='maintenance' "
                            "WHERE account_id=? AND node_id=? AND revision=? AND phase='ready'",
                            (account_id, assignment['node_id'], revision))
                        if result.rowcount != 1:
                            raise ValueError('登记期间账号归属已变化')
            finally:
                connection.close()
        return self.get(operation_id)

    def advance(self, operation_id: str, phase: str, receipt: dict) -> dict:
        """按顺序保存已核对回执，拒绝跳过源隔离与数据核验。

        :param operation_id: 原操作。
        :param phase: 已完成本阶段所需IO后的新阶段。
        :param receipt: 执行协调方已验证的无凭据回执。
        :return: 新持久记录。
        """
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    row = connection.execute('SELECT * FROM node_migrations WHERE operation_id=?', (operation_id,)).fetchone()
                    if row is None or _NEXT.get(row['phase']) != phase:
                        raise ValueError('迁移阶段已变化或不能跳过核验')
                    record = json.loads(row['record_json'])
                    record['receipts'][phase] = receipt
                    record['last_confirmed_phase'] = phase
                    self._save(connection, operation_id, phase, record)
            finally:
                connection.close()
        return self.get(operation_id)

    def progress(self, operation_id: str, stage: str) -> None:
        """保存实际执行步骤，确认游标仍只由回执推进。:param operation_id: 原操作。:param stage: 固定步骤。:return: None。"""
        from cluster_migration_errors import MigrationFailure
        MigrationFailure('unconfirmed', stage)
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    row = connection.execute('SELECT phase,record_json FROM node_migrations WHERE operation_id=?', (operation_id,)).fetchone()
                    if row is None or row['phase'] in _TERMINAL:
                        return
                    record = json.loads(row['record_json'])
                    record['progress'] = {'stage': stage, 'updated_at': time.time()}
                    self._save(connection, operation_id, row['phase'], record)
            finally:
                connection.close()

    def isolate(self, operation_id: str, reason: str, *, failure: dict | None = None) -> dict:
        """将未知结果保留在原归属的维护状态。

        :param operation_id: 原操作。
        :param reason: 固定脱敏原因代码。
        :param failure: 可选受控失败原因。
        :return: 待核对记录，账号保持关闭新准入。
        """
        if not re.fullmatch('[a-z][a-z0-9_]{0,79}', reason):
            raise ValueError('迁移原因代码无效')
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    row = connection.execute('SELECT * FROM node_migrations WHERE operation_id=?', (operation_id,)).fetchone()
                    if row is None or row['phase'] in _TERMINAL:
                        raise ValueError('迁移操作已结束或不存在')
                    record = json.loads(row['record_json'])
                    record['reason'] = reason
                    if failure is not None:
                        record['failure'] = public_failure(failure)
                    self._save(connection, operation_id, 'reconcile', record)
                    connection.execute("UPDATE account_node_assignments SET phase='reconcile' WHERE account_id=?", (row['account_id'],))
            finally:
                connection.close()
        return self.get(operation_id)

    def checkpoint(self, operation_id: str, key: str, value: dict, *, previous: dict | None = None) -> dict:
        """在跨节点IO前持久冻结尝试或收据，重试沿用相同范围。

        :param operation_id: 原迁移操作。
        :param key: 执行计划、网关租约或上传尝试的固定槽位。
        :param value: 受信协调器保存的无凭据元数据。
        :param previous: 仅网关租约在原证明CAS匹配时可记录恢复后的新代次。
        :return: 当前记录；已冻结槽位拒绝不同值覆盖。
        """
        if key not in ('execution', 'gateway_lease', 'archive', 'transfer', 'target', 'cancellation', 'target_revoked', 'source_restored'):
            raise ValueError('迁移检查点类型无效')
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    row = connection.execute('SELECT * FROM node_migrations WHERE operation_id=?', (operation_id,)).fetchone()
                    if row is None or row['phase'] in _TERMINAL:
                        raise ValueError('迁移操作已结束或不存在')
                    record = json.loads(row['record_json'])
                    checkpoints = record.setdefault('checkpoints', {})
                    replace_lease = key == 'gateway_lease' and previous is not None and checkpoints.get(key) == previous
                    if key in checkpoints and checkpoints[key] != value and not replace_lease:
                        raise ValueError('原迁移检查点的冻结范围已变化')
                    checkpoints[key] = value
                    self._save(connection, operation_id, row['phase'], record)
            finally:
                connection.close()
        return self.get(operation_id)

    def resume(self, operation_id: str) -> dict:
        """按原已确认阶段恢复协调游标，账号继续维护。

        :param operation_id: 原待核对操作。
        :return: 原已确认阶段，节点IO仍须按同操作复核。
        """
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    row = connection.execute('SELECT * FROM node_migrations WHERE operation_id=?', (operation_id,)).fetchone()
                    if row is None or row['phase'] != 'reconcile':
                        raise ValueError('迁移当前阶段不属于待核对恢复')
                    record = json.loads(row['record_json'])
                    phase = record['last_confirmed_phase']
                    if phase not in {*_NEXT, 'verified', 'committed'}:
                        raise ValueError('迁移原已确认阶段无效')
                    committed = phase == 'committed'
                    node_id = row['target_node_id'] if committed else row['source_node_id']
                    revision = record['target_revision'] if committed else record['source_revision']
                    result = connection.execute("UPDATE account_node_assignments SET phase='maintenance' "
                        "WHERE account_id=? AND node_id=? AND revision=? AND phase='reconcile'",
                        (row['account_id'], node_id, revision))
                    if result.rowcount != 1:
                        raise ValueError('迁移恢复时归属或分配版本已变化')
                    record.pop('reason', None)
                    self._save(connection, operation_id, phase, record)
            finally:
                connection.close()
        return self.get(operation_id)

    def cancel(self, operation_id: str, source_receipt: dict, target_receipt: dict) -> dict:
        """在提交前核对目标撤销和源恢复后，原子开放原归属。

        :param operation_id: 原未提交迁移。
        :param source_receipt: 原固定源已恢复且保持停止的收据。
        :param target_receipt: 目标已停止且拒绝迟到命令的撤销收据。
        :return: cancelled记录，原分配版本保持。
        """
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    row = connection.execute('SELECT * FROM node_migrations WHERE operation_id=?', (operation_id,)).fetchone()
                    if row is None or row['phase'] in _TERMINAL:
                        raise ValueError('迁移操作已结束或不存在')
                    record = json.loads(row['record_json'])
                    if record['last_confirmed_phase'] == 'committed':
                        raise ValueError('迁移归属已提交，请核对并继续目标激活')
                    base = {'operation_id': operation_id, 'account_id': row['account_id'], 'environment_id': record['environment_id']}
                    source = {**base, 'node_id': row['source_node_id'], 'revision': record['source_revision'],
                        'generation': record['source_generation'], 'phase': 'restored'}
                    target = {**base, 'node_id': row['target_node_id'], 'revision': record['source_revision'] + 1, 'phase': 'revoked'}
                    if source_receipt != source or target_receipt != target:
                        raise ValueError('取消迁移的双端收据与原冻结范围不一致')
                    result = connection.execute("UPDATE account_node_assignments SET phase='ready' WHERE account_id=? "
                        "AND node_id=? AND revision=? AND phase IN ('maintenance','reconcile')",
                        (row['account_id'], row['source_node_id'], record['source_revision']))
                    if result.rowcount != 1:
                        raise ValueError('取消迁移期间原归属已变化')
                    environment = connection.execute("UPDATE account_environments SET state='stopped' "
                        'WHERE environment_id=? AND account_id=? AND generation=?',
                        (record['environment_id'], row['account_id'], record['source_generation']))
                    if environment.rowcount != 1:
                        raise ValueError('取消迁移期间源实际代次已变化')
                    record['receipts']['source_restored'], record['receipts']['target_revoked'] = source_receipt, target_receipt
                    record['last_confirmed_phase'] = 'cancelled'
                    self._save(connection, operation_id, 'cancelled', record)
            finally:
                connection.close()
        return self.get(operation_id)

    def commit(self, operation_id: str, environment: dict) -> dict:
        """原子切换已核验目标及实际环境，继续关闭准入直到激活回执完成。

        :param operation_id: 已达到verified的原操作。
        :param environment: 目标组件核对并返回的实际环境。
        :return: committed阶段及新分配版本。
        """
        fields = ('fingerprint_json', 'generation', 'container_id', 'network_container_id', 'sender_container_id', 'isolation_version', 'state')
        if any(key not in environment for key in fields):
            raise ValueError('目标环境回执缺少必要字段')
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    row = connection.execute('SELECT * FROM node_migrations WHERE operation_id=?', (operation_id,)).fetchone()
                    if row is None or row['phase'] != 'verified':
                        raise ValueError('迁移尚未完成目标核验')
                    record = json.loads(row['record_json'])
                    old = connection.execute('SELECT * FROM account_environments WHERE environment_id=? AND account_id=?',
                        (record['environment_id'], row['account_id'])).fetchone()
                    if (old is None or old['generation'] != record['source_generation']
                            or environment.get('environment_id') != record['environment_id']
                            or environment.get('account_id') != row['account_id'] or environment.get('name') != old['name']
                            or type(environment['generation']) is not int or environment['generation'] <= old['generation']
                            or environment['isolation_version'] != 2 or environment['state'] not in ('ready', 'stopped')):
                        raise ValueError('目标环境身份或代次与源冻结范围不一致')
                    before, after = json.loads(old['fingerprint_json']), json.loads(environment['fingerprint_json'])
                    if hashlib.sha256(old['fingerprint_json'].encode()).hexdigest() != record['source_fingerprint_sha256']:
                        raise ValueError('源环境冻结配置已变化，拒绝提交迁移')
                    if any(before.get(key) != after.get(key) for key in ('hostname', 'machine_id', 'mac', 'tz', 'lang')):
                        raise ValueError('目标环境的逻辑身份发生变化')
                    target = connection.execute('SELECT 1 FROM cluster_nodes WHERE id=? AND enabled=1 AND deleted_at IS NULL', (row['target_node_id'],)).fetchone()
                    if target is None:
                        raise ValueError('目标节点已暂停或移除')
                    result = connection.execute("UPDATE account_node_assignments SET node_id=?,revision=revision+1 "
                        "WHERE account_id=? AND node_id=? AND revision=? AND phase='maintenance'",
                        (row['target_node_id'], row['account_id'], row['source_node_id'], record['source_revision']))
                    if result.rowcount != 1:
                        raise ValueError('账号原归属已变化，拒绝切换')
                    connection.execute('UPDATE account_environments SET ' + ','.join(field + '=?' for field in fields)
                        + ' WHERE environment_id=?', (*(environment[field] for field in fields), record['environment_id']))
                    record['target_revision'] = record['source_revision'] + 1
                    record['target_generation'] = environment['generation']
                    record['last_confirmed_phase'] = 'committed'
                    self._save(connection, operation_id, 'committed', record)
            finally:
                connection.close()
        return self.get(operation_id)

    def finish(self, operation_id: str, receipt: dict) -> dict:
        """持久核对目标激活收据后开放新归属。

        :param operation_id: 原已提交操作。
        :param receipt: 协调方通过受信节点操作核对的激活回执。
        :return: completed记录。
        """
        with self.store.lock:
            connection = self.store.database()
            try:
                with connection:
                    row = connection.execute("SELECT * FROM node_migrations WHERE operation_id=? AND phase='committed'", (operation_id,)).fetchone()
                    if row is None:
                        raise ValueError('迁移提交或激活状态需要核对')
                    record = json.loads(row['record_json'])
                    expected = {'operation_id': operation_id, 'node_id': row['target_node_id'], 'account_id': row['account_id'],
                        'environment_id': record['environment_id'], 'revision': record['target_revision'],
                        'generation': record['target_generation'], 'phase': 'activated'}
                    if receipt != expected:
                        raise ValueError('目标激活回执与提交身份不一致')
                    state = 'stopped' if record['source_state'] == 'stopped' else 'ready'
                    environment = connection.execute('UPDATE account_environments SET state=? WHERE environment_id=? AND account_id=? AND generation=?',
                        (state, record['environment_id'], row['account_id'], record['target_generation']))
                    if environment.rowcount != 1:
                        raise ValueError('目标激活后的环境代次已变化')
                    result = connection.execute("UPDATE account_node_assignments SET phase='ready' WHERE account_id=? "
                        "AND node_id=? AND revision=? AND phase='maintenance'", (row['account_id'], row['target_node_id'], record['target_revision']))
                    if result.rowcount != 1:
                        raise ValueError('提交后的账号节点归属已变化')
                    record['receipts']['activated'] = receipt
                    record['last_confirmed_phase'] = 'completed'
                    self._save(connection, operation_id, 'completed', record)
            finally:
                connection.close()
        return self.get(operation_id)

    def _save(self, connection, operation_id: str, phase: str, record: dict) -> None:
        connection.execute('UPDATE node_migrations SET phase=?,record_json=?,updated_at=? WHERE operation_id=?',
            (phase, json.dumps(record, ensure_ascii=False, allow_nan=False), time.time(), operation_id))


def pristine_target_migration(migration: dict, node_id: int) -> bool:
    """识别尚未建立目标副本的原迁移，允许先更新空目标组件。

    :param migration: 原持久迁移行。
    :param node_id: 正在同步的目标节点。
    :return: 原源已隔离且目标尚无传输检查点时为True。
    """
    record = json.loads(migration['record_json'])
    return (migration['target_node_id'] == node_id and migration['source_node_id'] != node_id
        and migration['phase'] in ('source_fenced', 'reconcile')
        and record.get('last_confirmed_phase') == 'source_fenced'
        and set(record.get('receipts', {})) <= {'draining', 'source_fenced'}
        and 'archive' not in record.get('checkpoints', {})
        and 'cancellation' not in record.get('checkpoints', {}))
