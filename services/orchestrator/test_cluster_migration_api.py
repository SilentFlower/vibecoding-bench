"""人工迁移公开接口、实际后台生命周期与维护准入的测试。"""
from __future__ import annotations

import json
import threading
import time
import unittest
import uuid
from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cluster_migration_api import MigrationOperations, migration_router
from runtime_files import atomic_json
from system_update_gate import DeploymentGate
import test_cluster_migration_runner as runner_fixture
import main


class MigrationApiTests(unittest.TestCase):
    """真实后台线程执行中央事务，公开投影保持有限字段。"""

    def setUp(self) -> None:
        """复用真实SQLite协调夹具，安装独立更新门禁。:return: None。"""
        fixture = runner_fixture.MigrationCoordinatorTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.operations = MigrationOperations(fixture.coordinator)
        self.addCleanup(self.operations.close)
        directory = fixture.root / 'gate'
        self.gate_record = {'schema_version': 1, 'deployment': 'synthetic', 'operation_id': None,
            'epoch': str(uuid.uuid4()), 'phase': 'idle', 'target_release': None,
            'revision': str(uuid.uuid4()), 'created_at': time.time()}
        self.gate_path = directory / 'admission.json'
        atomic_json(self.gate_path, self.gate_record)
        self.gate = DeploymentGate(directory, 'synthetic')
        gate_patch = patch('cluster_migration_api.UPDATE_GATE', self.gate)
        gate_patch.start()
        self.addCleanup(gate_patch.stop)
        app = FastAPI()
        app.include_router(migration_router(lambda: self.operations))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.path = '/api/accounts/1/node-migrations'

    def settled(self) -> dict:
        """等待本次有限后台作业完成。:return: 终止或待核对的公开状态。"""
        deadline = time.monotonic() + 5
        while True:
            response = self.client.get(self.path + '/' + self.fixture.operation)
            self.assertEqual(200, response.status_code)
            value = response.json()
            if not value['running']:
                return value
            self.assertLess(time.monotonic(), deadline, '合成迁移后台作业未及时结束')
            time.sleep(0.01)

    def test_background_operation_tracks_gate_and_deduplicates_resume(self) -> None:
        """长IO期间保留实际准入，同操作继续复用原线程。:return: None。"""
        entered, released = threading.Event(), threading.Event()
        self.addCleanup(released.set)
        original = self.fixture.command
        def command(node_id, operation, payload):
            if operation == 'fence':
                entered.set()
                if not released.wait(5):
                    raise ValueError('合成等待超时')
            return original(node_id, operation, payload)
        self.fixture.coordinator.io.command.side_effect = command
        response = self.client.post(self.path, json=self.fixture.request.model_dump())
        self.assertEqual(202, response.status_code, response.text)
        self.assertTrue(entered.wait(2))
        value = self.client.get(self.path + '/' + self.fixture.operation).json()
        self.assertTrue(value['running'])
        self.assertFalse(value['can_cancel'])
        self.assertGreater(self.gate.state()['active'], 0)
        repeated = self.client.post(self.path + '/' + self.fixture.operation + '/resume')
        self.assertEqual(202, repeated.status_code)
        # 平台开始关闭新工作后，原已登记作业仍保有自己的连续执行证明。
        atomic_json(self.gate_path, {**self.gate_record, 'phase': 'blocked', 'operation_id': str(uuid.uuid4()), 'target_release': 'next'})
        released.set()
        self.assertEqual('completed', self.settled()['phase'])
        self.assertEqual({}, self.gate.active)
        self.assertEqual(1, [item[1] for item in self.fixture.commands].count('fence'))

    def test_failure_exposes_recovery_controls_and_cancel_closes_original_scope(self) -> None:
        """目标未知后通过原操作取消，界面仅获得脱敏阶段。:return: None。"""
        self.fixture.fail_operation = 'prepare-import'
        response = self.client.post(self.path, json=self.fixture.request.model_dump())
        self.assertEqual(202, response.status_code)
        value = self.settled()
        self.assertEqual(('reconcile', 'importing'), (value['phase'], value['last_confirmed_phase']))
        self.assertTrue(value['can_resume'])
        self.assertTrue(value['can_cancel'])
        self.assertNotIn('checkpoints', json.dumps(value))
        self.assertNotIn('s' * 64, json.dumps(value))
        self.assertEqual(202, self.client.post(self.path + '/' + self.fixture.operation + '/cancel').status_code)
        self.assertEqual('cancelled', self.settled()['phase'])
        self.assertEqual('ready', self.fixture.store.assignment(1)['phase'])
        self.assertEqual({}, self.gate.active)

    def test_account_boundary_validation_and_history_omit_private_fields(self) -> None:
        """跨账号、未知字段和非法操作由公开边界拒绝。:return: None。"""
        self.client.post(self.path, json=self.fixture.request.model_dump())
        self.assertEqual('completed', self.settled()['phase'])
        response = self.client.get('/api/accounts/2/node-migrations/' + self.fixture.operation)
        self.assertEqual(404, response.status_code)
        response = self.client.get(self.path)
        self.assertEqual(1, len(response.json()['items']))
        self.assertNotIn('gateway_lease', response.text)
        response = self.client.post(self.path, json={**self.fixture.request.model_dump(), 'private_key': '私有材料不应回显'})
        self.assertEqual(422, response.status_code)
        self.assertNotIn('私有材料不应回显', response.text)
        self.assertEqual(422, self.client.post(self.path + '/' + self.fixture.operation + '/force').status_code)

    def test_main_guard_reads_remote_metadata_under_owner_profile_without_local_home(self) -> None:
        """实际main互斥入口使用中央身份和作业证据，远程环境根由节点核对。:return: None。"""
        connection = self.fixture.fixture.database()
        try:
            with connection:
                connection.execute('UPDATE account_node_assignments SET node_id=? WHERE account_id=1', (self.fixture.fixture.target,))
        finally:
            connection.close()
        runtime = SimpleNamespace(data=self.fixture.root, environment_jobs=Mock(return_value=[]),
            _root=Mock(side_effect=AssertionError('远程HOME应由所属节点读取')))
        with patch.object(main, 'get_db', self.fixture.fixture.database), patch.object(main, 'account_runtime', runtime), \
                patch.object(main, 'credential_ownership', None), patch.object(main, '_require_oauth_owner_transition_idle') as idle:
            with main._node_migration_guard(1) as (account, environment):
                self.assertEqual(1, account['id'])
                self.assertEqual('e' * 32, environment['environment_id'])
                self.assertTrue(main._oauth_owner_lock(account['name']).locked())
                self.assertTrue(main._profile_lock(account['name']).locked())
            idle.assert_called_once()
            runtime._root.assert_not_called()
