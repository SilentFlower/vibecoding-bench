"""节点有限执行证明的持久范围、单调续接、过期和撤销测试。"""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from cluster_execution_grants import ExecutionGrant, ExecutionGrants, ExecutionLeaseProof
from database_migrations import apply_migrations
from runtime_files import atomic_json


class ExecutionGrantTests(unittest.TestCase):
    """使用真实节点元数据、受保护文件与SQLite核对执行准入。"""

    def setUp(self) -> None:
        """建立固定安装、分配和实际环境代次。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        self.node_key, self.environment_id = 'a' * 32, 'e' * 32
        self.path = self.data / 'node.sqlite'
        atomic_json(self.data / 'cluster-node.json', {'protocol': 1, 'node_key': self.node_key, 'deployment_id': 'synthetic'})
        self.root = self.data / 'environments' / self.environment_id
        self.assignment = {'protocol': 1, 'node_key': self.node_key, 'account_id': 1,
            'environment_id': self.environment_id, 'revision': 5, 'phase': 'ready'}
        atomic_json(self.root / 'runtime/node-assignment.json', self.assignment)
        connection = self.database()
        try:
            apply_migrations(connection)
            with connection:
                connection.execute("INSERT INTO accounts(id,name,profile_path,cc2api_account_id) VALUES(1,'synthetic','profiles/synthetic',7)")
                connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json,generation,state,isolation_version) "
                    "VALUES(?,'synthetic',1,'{}',3,'ready',2)", (self.environment_id,))
        finally:
            connection.close()
        self.now = 1000.0
        self.store = ExecutionGrants(self.data, self.node_key, 'synthetic', self.database, lambda: self.now)
        self.grant = ExecutionGrant(operation_id='b' * 32, node_key=self.node_key, account_id=1, gateway_account_id=7,
            environment_id=self.environment_id, assignment_revision=5, generation=3, source='projects:synthetic:1',
            role='projects', not_after=1020, lease=ExecutionLeaseProof(owner='projects:synthetic:1',
                generation='synthetic-original-lease', expires_at=1020, exclusive=False, shared_cli=True))
        self.scope = self.grant.scope()

    def database(self):
        """打开节点投影库。:return: 待关闭连接。"""
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def test_disabled_account_only_admits_original_bound_login_source(self) -> None:
        """人工停用例外仅限绑定login SID，普通作业、刷新与独立许可仍拒绝。:return: None。"""
        with self.database() as connection:
            connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
        for role,source in (('projects','projects:synthetic:1'),('projects','login:'+'a'*12),
                ('login','oauth-refresh:'+'a'*32),('login','login:invalid')):
            grant=self.grant.model_copy(update={'role':role,'source':source,
                'lease':self.grant.lease.model_copy(update={'owner':source})})
            with self.subTest(role=role,source=source),self.assertRaises(ValueError):
                self.store.create(grant)
        source='login:'+'a'*12
        grant=self.grant.model_copy(update={'role':'login','source':source,
            'lease':self.grant.lease.model_copy(update={'owner':source,'exclusive':True,'shared_cli':False})})
        self.store.create(grant)
        self.store.activate(grant.scope())
        self.assertEqual(grant,self.store.authorize(grant.scope()))
        with self.database() as connection:
            connection.execute('UPDATE accounts SET deleted_at=1 WHERE id=1')
        with self.assertRaises(ValueError):
            self.store.authorize(grant.scope())

    def test_disabled_independent_account_only_admits_exact_login_without_gateway_lease(self) -> None:
        """独立停用账号仅原明确登录来源可认领有限许可，普通刷新继续关闭。:return: None。"""
        with self.database() as connection:
            connection.execute('UPDATE accounts SET enabled=0,cc2api_account_id=NULL WHERE id=1')
        grant=self.grant.model_copy(update={'gateway_account_id':None,'lease':None,'role':'login','source':'oauth-refresh:'+'b'*32})
        with self.assertRaises(ValueError):
            self.store.create(grant)
        grant=grant.model_copy(update={'source':'login:'+'a'*12})
        self.store.create(grant)
        self.store.activate(grant.scope())
        self.assertEqual(grant,self.store.authorize(grant.scope()))
        self.assertIsNone(grant.lease)

    def test_start_claim_is_durable_and_repeated_claim_does_not_authorize_replay(self) -> None:
        """证明和启动意图持久保存，同操作再认领需查询原结果。:return: None。"""
        prepared = self.store.create(self.grant)
        self.assertEqual(prepared, self.store.create(self.grant))
        self.assertEqual('active', self.store.activate(self.scope)['phase'])
        with self.assertRaisesRegex(ValueError, '原启动收据'):
            self.store.activate(self.scope)
        restarted = ExecutionGrants(self.data, self.node_key, 'synthetic', self.database, lambda: self.now)
        self.assertEqual('active', restarted.get(self.scope)['phase'])
        self.assertEqual(self.grant, restarted.authorize(self.scope))
        self.now = 1005
        self.assertEqual(1020, restarted.authorize(self.scope).not_after)

    def test_only_monotonic_central_renewal_changes_original_deadline(self) -> None:
        """续接只接受相同owner/租约代次，重试保持幂等并拒绝跳号。:return: None。"""
        self.store.create(self.grant)
        self.store.activate(self.scope)
        renewed = self.grant.model_copy(update={'sequence': 2, 'not_after': 1030,
            'lease': self.grant.lease.model_copy(update={'expires_at': 1030})})
        self.store.renew(renewed)
        self.assertEqual(2, self.store.renew(renewed)['grant']['sequence'])
        for value in (self.grant, renewed.model_copy(update={'sequence': 4}), renewed.model_copy(update={
                'sequence': 3, 'lease': renewed.lease.model_copy(update={'generation': 'another-lease'})})):
            with self.subTest(value=value.sequence), self.assertRaises(ValueError):
                self.store.renew(value)
        self.assertEqual(renewed, self.store.authorize(self.scope))

    def test_expiry_refuses_new_input_and_requires_actual_job_reconciliation(self) -> None:
        """截止关闭新输入，磁盘记录保留，旧active证明不得直接跨期续接。:return: None。"""
        self.store.create(self.grant)
        self.store.activate(self.scope)
        self.now = 1021
        with self.assertRaisesRegex(ValueError, '过期'):
            self.store.authorize(self.scope)
        renewed = self.grant.model_copy(update={'sequence': 2, 'not_after': 1040,
            'lease': self.grant.lease.model_copy(update={'expires_at': 1040})})
        with self.assertRaisesRegex(ValueError, '实际作业'):
            self.store.renew(renewed)
        self.assertEqual(('active', 1020), (self.store.get(self.scope)['phase'], self.store.get(self.scope)['grant']['not_after']))

    def test_wrong_scope_assignment_generation_and_fence_refuse_input(self) -> None:
        """每次新输入核对节点、账号、分配、实际代次和源隔离。:return: None。"""
        self.store.create(self.grant)
        self.store.activate(self.scope)
        for change in ({'node_key': 'c' * 32}, {'account_id': 2}, {'assignment_revision': 4}, {'generation': 2}, {'source': 'projects:other:1'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.authorize(self.scope.model_copy(update=change))
        atomic_json(self.root / 'runtime/node-assignment.json', {**self.assignment, 'phase': 'fenced'})
        with self.assertRaisesRegex(ValueError, '分配版本'):
            self.store.authorize(self.scope)
        atomic_json(self.root / 'runtime/node-assignment.json', self.assignment)
        atomic_json(self.root / 'runtime/node-fence.json', {'phase': 'fenced'})
        with self.assertRaisesRegex(ValueError, '隔离'):
            self.store.authorize(self.scope)
        self.assertEqual('active', self.store.get(self.scope)['phase'])

    def test_gateway_binding_change_revokes_same_generation_input(self) -> None:
        """同一环境代次的网关归属变化也关闭旧证明输入。:return: None。"""
        self.store.create(self.grant)
        self.store.activate(self.scope)
        connection = self.database()
        try:
            with connection:
                connection.execute('UPDATE accounts SET cc2api_account_id=8 WHERE id=1')
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, '网关绑定'):
            self.store.authorize(self.scope)
        self.assertEqual(7, self.store.get(self.scope)['grant']['gateway_account_id'])

    def test_closed_proof_retains_first_reason_and_cannot_reopen(self) -> None:
        """关闭只撤销输入，不生成停止事实，原记录永久拒绝重新认领。:return: None。"""
        self.store.create(self.grant)
        self.store.activate(self.scope)
        closed = self.store.close(self.scope, 'central_input_closed')
        self.assertEqual(closed, self.store.close(self.scope, 'another_reason'))
        self.assertNotIn('stopped', closed)
        for operation in (lambda: self.store.create(self.grant), lambda: self.store.renew(self.grant),
                lambda: self.store.activate(self.scope), lambda: self.store.authorize(self.scope)):
            with self.assertRaises(ValueError):
                operation()

    def test_private_records_refuse_links_and_preserve_unknown_directory_permissions(self) -> None:
        """未知权限和多链接证明保持原资料，后续操作拒绝读取。:return: None。"""
        directory = self.data / 'node-execution-grants'
        directory.mkdir(mode=0o755)
        with self.assertRaisesRegex(ValueError, '权限'):
            self.store.create(self.grant)
        self.assertEqual(0o755, directory.stat().st_mode & 0o777)
        directory.chmod(0o700)
        self.store.create(self.grant)
        path = directory / self.environment_id / ('b' * 32 + '.json')
        os.link(path, directory / 'extra-link')
        with self.assertRaisesRegex(ValueError, '权限或归属'):
            self.store.get(self.scope)
        self.assertTrue(path.exists())

    def test_strict_binding_and_deadline_reject_expanded_authority(self) -> None:
        """证明不能增加刷新权或超出中央租约及有限时间窗口。:return: None。"""
        for change in ({'gateway_account_id': None}, {'not_after': 1021}, {'source': 'run:other'}, {'sequence': True}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                ExecutionGrant.model_validate({**self.grant.model_dump(), **change})
        future = ExecutionGrant.model_validate({**self.grant.model_dump(), 'not_after': 1100,
            'lease': {**self.grant.lease.model_dump(), 'expires_at': 1100}})
        with self.assertRaisesRegex(ValueError, '时钟'):
            self.store.create(future)
        record = self.data / 'cluster-node.json'
        original = json.loads(record.read_text())
        atomic_json(record, {**original, 'node_key': 'f' * 32})
        with self.assertRaisesRegex(ValueError, '安装归属'):
            self.store.create(self.grant)
