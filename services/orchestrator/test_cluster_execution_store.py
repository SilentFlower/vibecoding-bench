"""中央节点会话冻结范围、source唯一、原租约及停止回执CAS验证。"""
from __future__ import annotations

import json
import unittest

from cluster_execution_grants import ExecutionGrant, ExecutionLeaseProof, ExecutionScope
from cluster_execution_store import NodeExecutions
from cluster_terminal import TerminalWork
import test_cluster_migrations as migration_fixture


class NodeExecutionStoreTests(unittest.TestCase):
    """真实中央SQLite事务与节点迁移夹具验证会话恢复账本。"""

    def setUp(self) -> None:
        """建立已准备同批SSH节点及其实际账号归属。:return: None。"""
        fixture = migration_fixture.NodeMigrationTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        connection = fixture.database()
        try:
            with connection:
                connection.execute('UPDATE account_node_assignments SET node_id=? WHERE account_id=1', (fixture.target,))
                connection.execute('UPDATE accounts SET cc2api_account_id=7 WHERE id=1')
                connection.execute('UPDATE cluster_nodes SET preparation_json=? WHERE id=?',
                    (json.dumps({'state': 'prepared', 'release': 'synthetic-release'}), fixture.target))
        finally:
            connection.close()
        self.work = TerminalWork(id='c' * 32, account_id=1, generation=2,
            session_id='11111111-2222-4333-8444-555555555555', project_key='synthetic-project', objective_id='FIRST',
            library_digest='f' * 64, settings_json=json.dumps({'claude_code_version': '2.1.303', 'claude_effort_level': 'high'}),
            remaining_sec=60, created_at=1000.0)
        source = 'projects:' + self.work.id + ':2'
        self.scope = ExecutionScope(operation_id='d' * 32, node_key='b' * 32, account_id=1, gateway_account_id=7,
            environment_id='e' * 32, assignment_revision=1, generation=4, source=source, role='projects')
        self.ledger = NodeExecutions(fixture.store, 'synthetic-release')
        self.lease = ExecutionLeaseProof(owner=source, generation='original-central-lease', expires_at=1020,
            exclusive=False, shared_cli=True)
        self.grant = ExecutionGrant(**self.scope.model_dump(), not_after=1020, sequence=1, lease=self.lease)

    def checkpoint(self, phase: str, **changes) -> dict:
        """以当前CAS版本保存单个确定阶段。:param phase: 新阶段。:param changes: 本次证据。:return: 新记录。"""
        row = self.ledger.get(self.scope.operation_id)
        return self.ledger.checkpoint(self.scope.operation_id, row['revision'], phase, **changes)

    def running(self) -> dict:
        """顺序登记中央意图、真实租约、节点证明及启动确认。:return: running记录。"""
        self.ledger.begin(self.scope, self.work)
        self.checkpoint('preparing', gateway_prepare_intent=True)
        self.checkpoint('claimed', lease=self.lease)
        self.checkpoint('starting', grant=self.grant)
        return self.checkpoint('running', node_receipt={'protocol': 1, 'scope': self.scope.model_dump(),
            'phase': 'ready', 'result': {'token': 'synthetic-original-token', 'source': self.scope.source}})

    def test_begin_is_durable_idempotent_and_original_source_cannot_be_reassigned(self) -> None:
        """重启读取同一scope，换操作重发同source与冻结工作变更均被拒绝。:return: None。"""
        row = self.ledger.begin(self.scope, self.work)
        self.assertEqual(row, NodeExecutions(self.fixture.store, 'synthetic-release').get(self.scope.operation_id))
        self.assertEqual(row, self.ledger.begin(self.scope, self.work))
        self.assertEqual(row, self.ledger.by_source(self.scope.account_id, self.scope.source))
        self.assertEqual([row], self.ledger.active(self.scope.account_id))
        with self.assertRaisesRegex(ValueError, '原source'):
            self.ledger.begin(self.scope.model_copy(update={'operation_id': 'a' * 32}), self.work)
        with self.assertRaisesRegex(ValueError, '冻结范围'):
            self.ledger.begin(self.scope, self.work.model_copy(update={'remaining_sec': 59}))
        self.assertEqual('preparing', row['phase'])

    def test_wrong_assignment_generation_release_or_scope_is_rejected_before_insert(self) -> None:
        """真实中央归属、环境代次与发布匹配后才建立执行登记。:return: None。"""
        for change in ({'generation': 3}, {'node_key': 'a' * 32}, {'assignment_revision': 2}, {'gateway_account_id': 8}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.ledger.begin(self.scope.model_copy(update=change), self.work)
        with self.assertRaisesRegex(ValueError, '同批'):
            NodeExecutions(self.fixture.store, 'other-release').begin(self.scope, self.work)

    def test_cas_and_renewal_keep_original_owner_generation_and_monotonic_sequence(self) -> None:
        """旧CAS和换租约被拒绝；同代续接保持中央与节点原截止一致。:return: None。"""
        row = self.running()
        newer_lease = self.lease.model_copy(update={'expires_at': 1030})
        newer_grant = self.grant.model_copy(update={'sequence': 2, 'not_after': 1030, 'lease': newer_lease})
        updated = self.checkpoint('running', lease=newer_lease, grant=newer_grant)
        self.assertEqual(2, updated['record']['grant']['sequence'])
        with self.assertRaisesRegex(ValueError, '版本已变化'):
            self.ledger.checkpoint(self.scope.operation_id, row['revision'], 'running')
        with self.assertRaisesRegex(ValueError, '原租约'):
            self.checkpoint('running', lease=newer_lease.model_copy(update={'generation': 'other'}), grant=None)
        with self.assertRaises(ValueError):
            self.checkpoint('running', grant=self.grant)
        self.assertEqual(updated, self.ledger.get(self.scope.operation_id))

    def test_close_requires_original_node_stop_and_exact_central_release(self) -> None:
        """TTL和单端回执均不构成关闭，节点与中央两端确认后保存closed。:return: None。"""
        self.running()
        self.checkpoint('stopping')
        with self.assertRaisesRegex(ValueError, '节点停止'):
            self.checkpoint('closed')
        closed = {'protocol': 1, 'scope': self.scope.model_dump(), 'phase': 'closed',
            'result': {'token': 'synthetic-original-token', 'source': self.scope.source}}
        self.checkpoint('stopping', node_receipt=closed)
        with self.assertRaises(ValueError):
            self.checkpoint('closed', lease_released={'owner': self.scope.source, 'generation': 'wrong', 'released': True})
        result = self.checkpoint('closed', lease_released={'owner': self.scope.source,
            'generation': self.lease.generation, 'released': True})
        self.assertEqual('closed', result['phase'])
        with self.assertRaises(ValueError):
            self.checkpoint('running')

    def test_changed_configuration_closes_new_admission_and_keeps_history(self) -> None:
        """节点停用、配置或分配变化拒绝新操作，原会话仍可只读。:return: None。"""
        row = self.running()
        self.assertEqual(row, self.ledger.admit(self.scope.operation_id))
        node = self.fixture.store.get(row['node_id'])
        changed = self.fixture.store.set_enabled(node['id'], node['revision'], False)
        with self.assertRaises(ValueError):
            self.ledger.admit(self.scope.operation_id)
        self.assertEqual(row, self.ledger.get(self.scope.operation_id))
        self.fixture.store.set_enabled(node['id'], changed['revision'], True)
        self.assertEqual(row, self.ledger.admit(self.scope.operation_id))
        connection = self.fixture.database()
        try:
            with connection:
                connection.execute("UPDATE cluster_nodes SET config_json='{} ' WHERE id=?", (node['id'],))
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, '配置'):
            self.ledger.admit(self.scope.operation_id)

    def test_confirmed_closed_source_can_resume_same_work_with_new_operation(self) -> None:
        """同代原会话确认收口后允许新握手，原未知操作仍受活动唯一索引保护。:return: None。"""
        self.running()
        self.checkpoint('stopping')
        closed = {'protocol': 1, 'scope': self.scope.model_dump(), 'phase': 'closed',
            'result': {'token': 'synthetic-original-token', 'source': self.scope.source}}
        self.checkpoint('closed', node_receipt=closed, lease_released={'owner': self.scope.source,
            'generation': self.lease.generation, 'released': True})
        next_scope = self.scope.model_copy(update={'operation_id': 'a' * 32})
        with self.assertRaisesRegex(ValueError, '剩余预算'):
            self.ledger.begin(next_scope, self.work.model_copy(update={'remaining_sec': 61}))
        resumed = self.ledger.begin(next_scope, self.work.model_copy(update={'remaining_sec': 59, 'resume_required': True}))
        self.assertEqual('preparing', resumed['phase'])
        self.assertEqual('closed', self.ledger.get(self.scope.operation_id)['phase'])
        self.assertEqual(resumed, self.ledger.by_source(self.scope.account_id, self.scope.source))
        self.assertEqual([resumed], self.ledger.active(self.scope.account_id))
        with self.assertRaisesRegex(ValueError, '原source'):
            self.ledger.begin(next_scope.model_copy(update={'operation_id': '9' * 32}), self.work)


if __name__ == '__main__':
    unittest.main()
