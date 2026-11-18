"""平台原维护操作串联Node备份、同步和取消的合同回归。"""
from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from system_update_host import HostDeployment
import test_system_updater


class ClusterHostUpdateTests(unittest.TestCase):
    """同一冻结Node集合沿原操作推进，保持短请求与后台长作业。"""

    def setUp(self) -> None:
        """建立只替换远程HTTP的原宿主执行器。:return: None。"""
        self.host = HostDeployment.__new__(HostDeployment)
        self.operation = {'operation_id': 'original', 'epoch': 'epoch', 'before': {'nodes': [{'id': 2}]}}
        self.selected = {'release': {'release': 'system-new'}, 'selection': {
            'control': {'release': 'new-control', 'reference': 'trusted-control'},
            'account': {'release': 'original-account', 'reference': 'trusted-account'}}}
        self.save = Mock()

    def test_preparation_collects_complete_same_epoch_backup_before_central_switch(self) -> None:
        """原目标组件与冻结Node一致，完整备份回执落盘后才返回。:return: None。"""
        row = {'node_id': 2, 'phase': 'backed_up', 'running': False, 'preparation': {'state': 'preparing'}}
        self.host.request = Mock(side_effect=[{'nodes': []}, {'nodes': [row]}])
        self.host.prepare_nodes(self.operation, self.selected, self.save, lambda: False)
        body = self.host.request.call_args_list[0].args[2]
        self.assertEqual('original', body['operation_id'])
        self.assertEqual('new-control', body['control_release'])
        self.assertEqual('original-account', body['account_release'])
        self.assertEqual([row], self.operation['cluster_backups'])
        self.assertEqual('backed_up', self.operation['cluster_nodes']['phase'])

    def test_cancel_waits_for_original_node_worker_before_returning(self) -> None:
        """取消先通知原节点作业，再等待实际后台收口。:return: None。"""
        running = {'node_id': 2, 'phase': 'fenced', 'running': True, 'preparation': {'state': 'preparing'}}
        done = {**running, 'phase': 'backed_up', 'running': False}
        self.host.request = Mock(side_effect=[{'nodes': []}, {'nodes': []}, {'nodes': [running]}, {'nodes': [done]}])
        with patch('system_update_host.time.sleep'):
            self.host.prepare_nodes(self.operation, self.selected, self.save, lambda: True)
        actions = [call.args[2]['action'] for call in self.host.request.call_args_list]
        self.assertEqual(['prepare', 'cancel-preparation', 'status', 'status'], actions)
        self.assertNotIn('cluster_backups', self.operation)

    def test_resume_and_restore_preserve_original_scope(self) -> None:
        """中央换批后核对Node完成，恢复原资料保持相同维护身份。:return: None。"""
        completed = {'node_id': 2, 'phase': 'completed', 'running': False,
            'preparation': {'state': 'prepared', 'release': 'new-control'}}
        self.host.request = Mock(return_value={'nodes': [completed]})
        self.host.resume_nodes(self.operation, self.selected, self.save)
        self.assertEqual('completed', self.operation['cluster_nodes']['phase'])
        restored = {**completed, 'phase': 'platform_restored'}
        self.host.request = Mock(side_effect=[{'nodes': []}, {'nodes': [restored]}])
        self.host.restore_nodes(self.operation, self.save)
        body = self.host.request.call_args_list[0].args[2]
        self.assertEqual({'operation_id': 'original', 'epoch': 'epoch', 'action': 'restore', 'preserve_data': False}, body)
        self.assertEqual('restored', self.operation['cluster_nodes']['phase'])


class ClusterUpdateOrderingTests(unittest.TestCase):
    """真实签名与持久状态机覆盖集群可选宿主钩子顺序。"""

    def test_nodes_backup_precedes_switch_and_resume_precedes_health(self) -> None:
        """备份、中央切换、节点恢复和最终验收沿同一原操作依次执行。:return: None。"""
        fixture = test_system_updater.SystemUpdaterTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        original_capture = fixture.backend.capture
        fixture.backend.capture = lambda *args: {**original_capture(*args), 'nodes': [{'id': 2}]}
        fixture.backend.prepare_nodes = lambda *args: fixture.backend.calls.append('nodes-backup')
        fixture.backend.resume_nodes = lambda *args: fixture.backend.calls.append('nodes-resume')
        fixture.engine.submit('install', fixture.request())
        self.assertEqual('succeeded', fixture.join()['operation']['phase'])
        calls = fixture.backend.calls
        self.assertLess(calls.index('nodes-backup'), calls.index('switch'))
        self.assertLess(calls.index('switch'), calls.index('nodes-resume'))
        self.assertLess(calls.index('nodes-resume'), calls.index('health'))
