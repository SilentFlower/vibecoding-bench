"""迁移阶段与原子归属切换的真实SQLite故障边界测试。"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from cluster_migrations import NodeMigrations
from cluster_store import ClusterStore
from database_migrations import apply_migrations


class NodeMigrationTests(unittest.TestCase):
    """节点IO由执行层验证，本层核对持久顺序、CAS及未知状态保护。"""

    def setUp(self) -> None:
        """建立固定源环境与可用目标节点。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'bench.sqlite'
        connection = self.database()
        try:
            apply_migrations(connection)
            fingerprint = json.dumps({'hostname': 'fixed', 'machine_id': 'a' * 32,
                'mac': '02:00:00:00:00:01', 'tz': 'UTC', 'lang': 'en_US.UTF-8'})
            with connection:
                connection.execute("INSERT INTO accounts(id,name,profile_path) VALUES(1,'synthetic','profiles/synthetic')")
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json,generation,state,isolation_version) "
                    "VALUES(?,'synthetic',1,?,4,'ready',2)", ('e' * 32, fingerprint))
                self.target = connection.execute("INSERT INTO cluster_nodes(node_key,name,kind,config_json,created_at) VALUES(?,'目标','ssh','{}',0)",
                    ('b' * 32,)).lastrowid
                connection.execute('UPDATE cluster_nodes SET preparation_json=? WHERE id=?',
                    (json.dumps({'state': 'prepared', 'release': 'synthetic-release'}), self.target))
                self.environment = dict(connection.execute('SELECT * FROM account_environments').fetchone())
        finally:
            connection.close()
        self.store = ClusterStore(self.database, threading.Lock())
        self.migrations = NodeMigrations(self.store)
        self.operation = 'c' * 32
        self.target_environment = {**self.environment, 'generation': 5, 'container_id': 'target-cli',
            'network_container_id': 'target-network', 'sender_container_id': 'target-sender'}

    def database(self):
        """打开临时库。:return: 待关闭SQLite连接。"""
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def verified(self) -> None:
        """顺序保存合成隔离与数据核验收据。:return: None。"""
        self.migrations.begin(self.operation, 1, self.target, 1)
        for phase in ('draining', 'source_fenced', 'exporting', 'importing', 'verified'):
            self.migrations.advance(self.operation, phase, {'verified_stage': phase})

    def test_source_fence_receipt_updates_central_stopped_state(self) -> None:
        """真实源停止的已确认收据同步中央状态，原运行意图保留在迁移记录。:return: None。"""
        self.migrations.begin(self.operation, 1, self.target, 1)
        self.migrations.advance(self.operation, 'draining', {'active': 0})
        migration = self.migrations.advance(self.operation, 'source_fenced', {'phase': 'fenced'})
        with self.database() as connection:
            self.assertEqual('stopped', connection.execute('SELECT state FROM account_environments').fetchone()[0])
        self.assertEqual('ready', migration['record']['source_state'])

    def test_begin_is_idempotent_and_durable_admission_stays_closed(self) -> None:
        """原操作重试返回同一记录，另一个迁移无法穿过维护边界。:return: None。"""
        first = self.migrations.begin(self.operation, 1, self.target, 1)
        self.assertEqual(first, self.migrations.begin(self.operation, 1, self.target, 1))
        self.assertEqual('maintenance', self.store.assignment(1)['phase'])
        self.assertEqual('requested', NodeMigrations(self.store).get(self.operation)['phase'])
        with self.assertRaisesRegex(ValueError, '维护|迁移'):
            self.migrations.begin('d' * 32, 1, self.target, 1)
        with self.assertRaisesRegex(ValueError, '冻结范围'):
            self.migrations.begin(self.operation, 1, self.target, 2)

    def test_state_machine_requires_source_fence_and_verified_import(self) -> None:
        """跳过排空或数据核验被拒绝，目标归属保持原值。:return: None。"""
        self.migrations.begin(self.operation, 1, self.target, 1)
        with self.assertRaisesRegex(ValueError, '阶段'):
            self.migrations.advance(self.operation, 'verified', {})
        with self.assertRaisesRegex(ValueError, '核验'):
            self.migrations.commit(self.operation, self.target_environment)
        self.assertEqual('local', self.store.assignment(1)['kind'])

    def test_commit_and_activation_publish_new_revision_in_order(self) -> None:
        """目标资料与归属在同事务切换，激活证明之前持续维护。:return: None。"""
        self.verified()
        record = self.migrations.commit(self.operation, self.target_environment)
        assignment = self.store.assignment(1)
        self.assertEqual((self.target, 2, 'maintenance'), (assignment['node_id'], assignment['revision'], assignment['phase']))
        connection = self.database()
        try:
            actual = dict(connection.execute('SELECT * FROM account_environments').fetchone())
        finally:
            connection.close()
        self.assertEqual(self.target_environment, actual)
        with self.assertRaisesRegex(ValueError, '激活回执'):
            self.migrations.finish(self.operation, {'phase': 'activated'})
        receipt = {'operation_id': self.operation, 'node_id': self.target, 'account_id': 1,
            'environment_id': 'e' * 32, 'revision': 2, 'generation': 5, 'phase': 'activated'}
        self.assertEqual('completed', self.migrations.finish(self.operation, receipt)['phase'])
        self.assertEqual('ready', self.store.assignment(1)['phase'])
        self.assertEqual(2, record['record']['target_revision'])

    def test_identity_conflict_rolls_back_database_switch(self) -> None:
        """目标逻辑身份冲突时，源环境和分配版本完整保留。:return: None。"""
        self.verified()
        target = {**self.target_environment, 'fingerprint_json': json.dumps({'hostname': 'foreign'})}
        with self.assertRaisesRegex(ValueError, '逻辑身份'):
            self.migrations.commit(self.operation, target)
        self.assertEqual((1, 'local', 'maintenance'),
            (self.store.assignment(1)['revision'], self.store.assignment(1)['kind'], self.store.assignment(1)['phase']))
        self.assertEqual('verified', self.migrations.get(self.operation)['phase'])

    def test_source_revision_conflict_preserves_both_original_records(self) -> None:
        """源分配被改变后CAS拒绝切换，并回滚目标环境写入。:return: None。"""
        self.verified()
        connection = self.database()
        try:
            with connection:
                connection.execute('UPDATE account_node_assignments SET revision=9 WHERE account_id=1')
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, '原归属'):
            self.migrations.commit(self.operation, self.target_environment)
        connection = self.database()
        try:
            self.assertEqual(4, connection.execute('SELECT generation FROM account_environments').fetchone()[0])
        finally:
            connection.close()

    def test_post_commit_unknown_state_keeps_target_and_requires_reconciliation(self) -> None:
        """切换后断连保留新归属及待对账，不自动回退源副本。:return: None。"""
        self.verified()
        self.migrations.commit(self.operation, self.target_environment)
        record = self.migrations.isolate(self.operation, 'target_activation_unknown')
        assignment = self.store.assignment(1)
        self.assertEqual((self.target, 2, 'reconcile'), (assignment['node_id'], assignment['revision'], assignment['phase']))
        self.assertEqual('committed', record['record']['last_confirmed_phase'])
        self.assertEqual('target_activation_unknown', record['record']['reason'])

    def test_source_configuration_change_blocks_commit_with_unchanged_generation(self) -> None:
        """同代次配置改变也触发冻结摘要校验，保持原归属维护。:return: None。"""
        self.verified()
        connection = self.database()
        try:
            with connection:
                value = json.loads(self.environment['fingerprint_json'])
                value['mem'] = '8g'
                connection.execute('UPDATE account_environments SET fingerprint_json=?', (json.dumps(value),))
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, '冻结配置'):
            self.migrations.commit(self.operation, self.target_environment)
        self.assertEqual('local', self.store.assignment(1)['kind'])
        self.assertEqual('maintenance', self.store.assignment(1)['phase'])

    def test_stopped_source_remains_stopped_after_activation(self) -> None:
        """迁移冻结原停止状态，目标准备产生新代次后仍按停止状态完成。:return: None。"""
        connection = self.database()
        try:
            with connection:
                connection.execute("UPDATE account_environments SET state='stopped'")
        finally:
            connection.close()
        self.verified()
        self.migrations.commit(self.operation, self.target_environment)
        self.migrations.finish(self.operation, {'operation_id': self.operation, 'node_id': self.target, 'account_id': 1,
            'environment_id': 'e' * 32, 'revision': 2, 'generation': 5, 'phase': 'activated'})
        connection = self.database()
        try:
            self.assertEqual('stopped', connection.execute('SELECT state FROM account_environments').fetchone()[0])
        finally:
            connection.close()

    def test_resume_restores_original_cursor_and_keeps_target_after_commit(self) -> None:
        """重启继续原阶段，提交后的恢复保持新归属维护。:return: None。"""
        self.verified()
        self.migrations.isolate(self.operation, 'transfer_unknown')
        self.assertEqual('verified', self.migrations.resume(self.operation)['phase'])
        self.assertEqual('maintenance', self.store.assignment(1)['phase'])
        self.migrations.commit(self.operation, self.target_environment)
        self.migrations.isolate(self.operation, 'target_activation_unknown')
        self.assertEqual('committed', self.migrations.resume(self.operation)['phase'])
        self.assertEqual((self.target, 'maintenance'), (self.store.assignment(1)['node_id'], self.store.assignment(1)['phase']))

    def test_cancel_requires_both_receipts_and_refuses_post_commit_rollback(self) -> None:
        """提交前使用完整双端收据恢复源，提交后保持新目标。:return: None。"""
        self.verified()
        base = {'operation_id': self.operation, 'account_id': 1, 'environment_id': 'e' * 32}
        source = {**base, 'node_id': 1, 'revision': 1, 'generation': 4, 'phase': 'restored'}
        target = {**base, 'node_id': self.target, 'revision': 2, 'phase': 'revoked'}
        with self.assertRaisesRegex(ValueError, '双端收据'):
            self.migrations.cancel(self.operation, source, {**target, 'revision': 9})
        self.assertEqual('maintenance', self.store.assignment(1)['phase'])
        self.migrations.commit(self.operation, self.target_environment)
        with self.assertRaisesRegex(ValueError, '归属已提交'):
            self.migrations.cancel(self.operation, source, target)

    def test_checkpoint_is_frozen_and_survives_recovery(self) -> None:
        """上传尝试先落盘，同操作恢复继续原尝试。:return: None。"""
        self.migrations.begin(self.operation, 1, self.target, 1)
        value = {'transfer_id': 'd' * 32}
        self.migrations.checkpoint(self.operation, 'transfer', value)
        self.migrations.checkpoint(self.operation, 'transfer', value)
        with self.assertRaisesRegex(ValueError, '冻结范围'):
            self.migrations.checkpoint(self.operation, 'transfer', {'transfer_id': 'e' * 32})
        self.assertEqual(value, NodeMigrations(self.store).get(self.operation)['record']['checkpoints']['transfer'])

    def test_verified_cancel_restores_only_original_source_revision(self) -> None:
        """双端核对成功后原归属恢复，停止状态随事务保存。:return: None。"""
        self.verified()
        base = {'operation_id': self.operation, 'account_id': 1, 'environment_id': 'e' * 32}
        source = {**base, 'node_id': 1, 'revision': 1, 'generation': 4, 'phase': 'restored'}
        target = {**base, 'node_id': self.target, 'revision': 2, 'phase': 'revoked'}
        self.assertEqual('cancelled', self.migrations.cancel(self.operation, source, target)['phase'])
        self.assertEqual((1, 1, 'ready'), (self.store.assignment(1)['node_id'], self.store.assignment(1)['revision'], self.store.assignment(1)['phase']))
        connection = self.database()
        try:
            self.assertEqual('stopped', connection.execute('SELECT state FROM account_environments').fetchone()[0])
        finally:
            connection.close()
