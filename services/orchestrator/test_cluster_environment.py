"""源环境隔离记录、真实角色停止判定及旧源拒绝的测试。"""
from __future__ import annotations

import json
import unittest
from unittest.mock import Mock, patch

from docker.errors import DockerException

from account_runtime import RuntimeBusy
from account_update_identity import role_release
from cluster_environment import EnvironmentFence, fence_environment, restore_fenced_source
from runtime_files import atomic_json
import test_account_runtime as runtime_fixture


class EnvironmentFenceTests(unittest.TestCase):
    """复用真实运行时和SQLite，Docker角色由可核对状态替身承接。"""

    def setUp(self) -> None:
        """建立原代次与三角色可观察状态。:return: None。"""
        fixture = runtime_fixture.AccountRuntimeTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.runtime = fixture.runtime
        self.row = self.runtime._row('synthetic', 1)
        self.runtime._update(self.row, state='ready', generation=3, isolation_version=2,
            container_id='source-cli', sender_container_id='source-sender', network_container_id='source-network')
        self.root = self.runtime._root(self.row)
        self.root.mkdir(parents=True, exist_ok=True)
        self.request = EnvironmentFence(operation_id='f' * 32, node_key='local', account_id=1,
            environment_id=self.row['environment_id'], assignment_revision=1, generation=3)
        self.containers = []
        for role, label in (('cli', 'account'), ('sender', 'account-sender'), ('network', 'account-network')):
            container = Mock(id='source-' + role, status='running', labels={**self.runtime._labels(self.row),
                'vibebench.role': label, 'vibebench.isolation-version': '2',
                'vibebench.release': role_release(self.runtime, self.row)}, attrs={'State': {'Running': True, 'Pid': 33}})
            def stop(timeout=None, current=container):
                current.status = 'exited'
                current.attrs['State'] = {'Running': False, 'Pid': 0}
            container.stop.side_effect = stop
            container.exec_run.return_value = Mock(exit_code=0, output=b'{"orphans":[]}')
            self.containers.append(container)
        by_id = {item.id: item for item in self.containers}
        fixture.client.containers.get.side_effect = by_id.__getitem__
        fixture.client.containers.list.return_value = self.containers
        self.runtime.reviews.serial_state = Mock(return_value=None)
        self.runtime.reviews.check_orphans = Mock()
        self.sender = patch.object(self.runtime, '_running_sender_active', return_value=0)
        self.sender.start()
        self.addCleanup(self.sender.stop)

    def test_fence_stops_three_roles_and_durably_blocks_old_source(self) -> None:
        """停止按原运行时执行，隔离记录和代次跨恢复保留。:return: None。"""
        receipt = fence_environment(self.runtime, self.row, self.request)
        self.assertEqual(['source-cli', 'source-network', 'source-sender'], receipt['stopped_containers'])
        self.assertEqual('fenced', receipt['phase'])
        self.assertEqual('stopped', self.runtime._row('synthetic', 1)['state'])
        for container in self.containers:
            container.stop.assert_called_once_with(timeout=5)
        with self.assertRaises(RuntimeBusy):
            self.runtime._check_node_fence(self.row)
        self.runtime.reconcile()
        self.assertEqual(3, self.runtime._row('synthetic', 1)['generation'])
        self.assertEqual('fenced', json.loads((self.root / 'runtime/node-fence.json').read_text())['phase'])
        self.assertEqual('fenced', fence_environment(self.runtime, self.row, self.request)['phase'])

    def test_pending_owner_handoff_blocks_migration_until_original_publication(self) -> None:
        """迁移等待原凭据交接完成，已发布回执允许正常源隔离。:return: None。"""
        marker=self.root/'runtime/owner-transition.json'
        atomic_json(marker,{'phase':'preparing'})
        with self.assertRaises(RuntimeBusy):
            fence_environment(self.runtime,self.row,self.request)
        for container in self.containers:
            container.stop.assert_not_called()
        atomic_json(marker,{'phase':'published'})
        self.assertEqual('fenced',fence_environment(self.runtime,self.row,self.request)['phase'])

    def test_execution_record_and_active_sender_refuse_stopping(self) -> None:
        """活动CLI证据和发送器计数分别阻止源停止。:return: None。"""
        record = self.root / 'runtime/executions/synthetic.json'
        atomic_json(record, {'source': 'run:synthetic'})
        with self.assertRaisesRegex(RuntimeBusy, '执行'):
            fence_environment(self.runtime, self.row, self.request)
        record.unlink()
        with patch.object(self.runtime, '_running_sender_active', return_value=1):
            with self.assertRaisesRegex(RuntimeBusy, '活动请求'):
                fence_environment(self.runtime, self.row, self.request)
        for container in self.containers:
            container.stop.assert_not_called()
        self.assertFalse((self.root / 'runtime/node-fence.json').exists())

    def test_partial_stop_keeps_fencing_intent_and_retries_same_operation(self) -> None:
        """Docker停止中断后保留隔离意图，同操作核对后可继续停止。:return: None。"""
        sender = self.containers[1]
        original = sender.stop.side_effect
        sender.stop.side_effect = DockerException('synthetic stop failure')
        with self.assertRaises(DockerException):
            fence_environment(self.runtime, self.row, self.request)
        self.assertEqual('fencing', json.loads((self.root / 'runtime/node-fence.json').read_text())['phase'])
        with self.assertRaises(RuntimeBusy):
            self.runtime._check_node_fence(self.row)
        sender.stop.side_effect = original
        self.assertEqual('fenced', fence_environment(self.runtime, self.row, self.request)['phase'])

    def test_wrong_generation_or_other_operation_cannot_reuse_fence(self) -> None:
        """源代次与操作边界分别校验，错误请求保持原环境。:return: None。"""
        with self.assertRaisesRegex(ValueError, '代次'):
            fence_environment(self.runtime, self.row, self.request.model_copy(update={'generation': 2}))
        fence_environment(self.runtime, self.row, self.request)
        with self.assertRaisesRegex(ValueError, '其他隔离'):
            fence_environment(self.runtime, self.row, self.request.model_copy(update={'operation_id': 'a' * 32}))

    def test_remote_assignment_is_fenced_with_the_same_operation(self) -> None:
        """SSH节点的本地归属记录随真实停止进入fenced并拒绝其他版本。:return: None。"""
        request = self.request.model_copy(update={'node_key': 'b' * 32})
        self.runtime.node_key = request.node_key
        for container in self.containers:
            container.labels['vibebench.cluster-node'] = request.node_key
        owner = {'protocol': 1, 'node_key': request.node_key, 'account_id': 1,
            'environment_id': request.environment_id, 'revision': 1, 'phase': 'ready'}
        path = self.root / 'runtime/node-assignment.json'
        atomic_json(path, owner)
        with self.assertRaisesRegex(ValueError, '版本'):
            fence_environment(self.runtime, self.row, request.model_copy(update={'assignment_revision': 2}))
        self.assertEqual(owner, json.loads(path.read_text()))
        fence_environment(self.runtime, self.row, request)
        actual = json.loads(path.read_text())
        self.assertEqual(('fenced', request.operation_id), (actual['phase'], actual['operation_id']))

    def test_actual_unregistered_cli_process_blocks_fencing(self) -> None:
        """真实进程探针返回孤儿时保持原角色，不能只依据空jobs认定空闲。:return: None。"""
        self.containers[0].exec_run.return_value = Mock(exit_code=0, output=b'{"orphans":[123]}')
        with self.assertRaisesRegex(RuntimeBusy, '未登记'):
            fence_environment(self.runtime, self.row, self.request)
        for container in self.containers:
            container.stop.assert_not_called()
        self.assertFalse((self.root / 'runtime/node-fence.json').exists())

    def test_missing_source_root_cannot_create_a_false_fence_receipt(self) -> None:
        """源目录缺失时保持未知，拒绝创建替代空树和停止回执。:return: None。"""
        self.root.rmdir()
        with self.assertRaises(FileNotFoundError):
            fence_environment(self.runtime, self.row, self.request)
        self.assertFalse(self.root.exists())
        for container in self.containers:
            container.stop.assert_not_called()

    def test_source_restore_keeps_cancellation_tombstone_and_refuses_old_fence(self) -> None:
        """源恢复保持停止并撤销旧操作，下一次明确迁移可使用新操作。:return: None。"""
        fence_environment(self.runtime, self.row, self.request)
        self.assertEqual('restored', restore_fenced_source(self.runtime, self.row, self.request)['phase'])
        self.assertEqual('restored', restore_fenced_source(self.runtime, self.row, self.request)['phase'])
        self.runtime._check_node_fence(self.row)
        with self.assertRaisesRegex(ValueError, '已取消'):
            fence_environment(self.runtime, self.row, self.request)
        next_request = self.request.model_copy(update={'operation_id': 'e' * 32})
        self.assertEqual('fenced', fence_environment(self.runtime, self.row, next_request)['phase'])
