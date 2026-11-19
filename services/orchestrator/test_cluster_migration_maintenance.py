"""暂停迁移的组件维护保留原操作、租约及实际停止证明。"""
import copy
import json
import shlex
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cluster_migration_maintenance import paused_migration_lease
from cluster_synchronization import NodeSynchronization
from runtime_files import atomic_json
from system_updates import runtime_snapshot
import test_cluster_migration_runner as migration_fixture


class MigrationMaintenanceTests(unittest.TestCase):
    """用真实迁移账本与网关代次核对维护兼容。"""

    def setUp(self) -> None:
        """留下目标准备失败的原迁移。:return: None。"""
        self.flow = migration_fixture.MigrationCoordinatorTests(methodName='runTest')
        self.flow.setUp()
        self.addCleanup(self.flow.doCleanups)
        self.coordinator = self.flow.coordinator
        self.database = self.flow.fixture.database
        self.coordinator.begin(1, self.flow.request)
        self.flow.fail_operation = 'prepare-import'
        with self.assertRaises(ValueError):
            self.coordinator.run(self.flow.operation)
        with self.database() as connection:
            connection.execute("UPDATE account_environments SET state='stopped'")
            self.row = dict(connection.execute('SELECT * FROM account_environments').fetchone())
        self.snapshot = self.flow.gateway._request('GET', '/synthetic/lease')

    def test_original_paused_lease_is_preserved_and_foreign_or_active_work_is_blocked(self) -> None:
        """只有原迁移的空闲排他租约可随维护保留，TTL过期继续核验原代次。:return: None。"""
        self.snapshot['holders'][0]['expires_at'] = 0
        original = copy.deepcopy(self.snapshot)
        result = paused_migration_lease(self.database, self.row, self.snapshot)
        self.assertEqual(self.flow.operation, result['operation_id'])
        self.assertEqual(original, self.snapshot)
        for key in ('active', 'waiting', 'importing'):
            with self.subTest(key=key):
                self.assertIsNone(paused_migration_lease(self.database, self.row, {**self.snapshot, key: 1}))
        foreign = copy.deepcopy(self.snapshot)
        foreign['holders'][0]['generation'] = 'foreign'
        self.assertIsNone(paused_migration_lease(self.database, self.row, foreign))
        self.assertIsNone(paused_migration_lease(self.database, {**self.row, 'generation': 999}, self.snapshot))
        self.assertIsNone(paused_migration_lease(self.database, {**self.row, 'state': 'ready'}, self.snapshot))

    def test_platform_snapshot_accepts_stopped_source_and_keeps_original_lease(self) -> None:
        """平台排空保留已隔离暂停迁移，外来隔离回执继续阻断。:return: None。"""
        runtime = self.coordinator.runtime
        runtime.database = self.database
        runtime.gateway = self.flow.gateway
        runtime.environment_jobs = lambda identifier: []
        runtime._execution_records = lambda row: []
        root = runtime._root(self.row)
        fence = {'phase': 'fenced', 'operation_id': self.flow.operation, 'node_key': 'local',
            'environment_id': self.row['environment_id'], 'account_id': 1, 'generation': 4, 'assignment_revision': 1}
        atomic_json(root / 'runtime/node-fence.json', fence)
        gate = {'phase': 'blocked', 'active': 0}
        with patch('system_updates.UPDATE_GATE.state', return_value=gate):
            self.assertTrue(runtime_snapshot(runtime)['ready'])
            self.assertTrue(self.flow.gateway.holders)
            atomic_json(root / 'runtime/node-fence.json', {**fence, 'operation_id': 'f' * 32})
            self.assertFalse(runtime_snapshot(runtime)['ready'])

    def test_partial_target_files_remain_eligible_for_component_synchronization(self) -> None:
        """目标已发布但准备失败时，维护核对磁盘标记并保留全部资料。:return: None。"""
        target = self.flow.fixture.target
        data = self.flow.root / 'target-data'
        with self.database() as connection:
            connection.execute('UPDATE cluster_nodes SET config_json=? WHERE id=?',
                (json.dumps({'data_root': str(data)}), target))
        marker = data / 'environments' / self.row['environment_id'] / 'runtime/node-migration-target.json'
        atomic_json(marker, {'operation_id': self.flow.operation, 'environment_id': self.row['environment_id'],
            'account_id': 1, 'node_key': 'b' * 32, 'phase': 'published', 'revision': 2, 'source_generation': 4})
        node = Mock()
        node._command.side_effect = lambda command, data, **options: subprocess.check_output(shlex.split(command), input=data)
        service = self.coordinator.service
        service.connection = Mock(return_value=node)
        remote = Mock()
        remote.containers.list.return_value = []
        service.docker = Mock(return_value=remote)
        synchronization = NodeSynchronization(service, self.coordinator.runtime, self.flow.gateway, Mock())
        self.addCleanup(synchronization.close)
        original = marker.read_bytes()
        self.assertEqual([], synchronization._rows(target))
        self.assertEqual(original, marker.read_bytes())
        unknown = SimpleNamespace(id='unknown', labels={'vibebench.role': 'account-network'}, reload=lambda: None,
            attrs={'State': {'Running': True, 'Pid': 99}})
        remote.containers.list.return_value = [unknown]
        with self.assertRaisesRegex(ValueError, '迁移'):
            synchronization._rows(target)

    def test_cancellation_keeps_its_own_recovery_boundary(self) -> None:
        """已经启动取消时继续原取消，不能当作普通暂停维护。:return: None。"""
        self.coordinator.ledger.checkpoint(self.flow.operation, 'cancellation', {'requested': True})
        self.assertIsNone(paused_migration_lease(self.database, self.row, self.snapshot))
