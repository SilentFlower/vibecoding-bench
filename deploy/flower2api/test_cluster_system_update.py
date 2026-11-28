"""平台原维护操作串联Node备份、同步和取消的合同回归。"""
from __future__ import annotations

import unittest
from io import BytesIO
from urllib.error import HTTPError
from hashlib import sha256
from pathlib import Path
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
        self.assertTrue(self.operation['node_backup_requested'])

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

    def test_drain_waits_for_active_removal_and_fails_fast_for_retry(self) -> None:
        """安装和回退共用排空，待重试时结束维护并给出可处理原因。:return: 无。"""
        gate = {'phase': 'blocked', 'epoch': 'epoch', 'active': 0}
        runtime = {**gate, 'active': 1, 'ready': False, 'environments': [], 'blockers': ['隔离节点正在移除'],
            'node_removals': [{'name': '隔离节点', 'state': 'removing'}]}
        self.host.request = Mock(side_effect=[runtime, gate])
        self.assertFalse(self.host.drained(self.operation)['ready'])
        runtime['active'] = 0
        self.host.request = Mock(side_effect=[runtime, gate])
        with self.assertRaisesRegex(ValueError, '等待续接'):
            self.host.drained(self.operation)
        runtime['node_removals'][0]['state'] = 'needs_check'
        self.host.request = Mock(side_effect=[runtime, gate])
        with self.assertRaisesRegex(ValueError, '重试移除后再更新平台：隔离节点'):
            self.host.drained(self.operation)

    def test_direct_only_release_uses_natural_drain_on_existing_host(self) -> None:
        """当前候选沿旧宿主已经支持的自然排空入口安装和回退。@return 无。"""
        dockerfile = (Path(__file__).resolve().parents[2] / 'images/v3/Dockerfile').read_text()
        control = dockerfile.split('vibebench.role="control"', 1)[1].split('ENTRYPOINT', 1)[0]
        label = control.split('vibebench.fast-system-update="', 1)[1].split('"', 1)[0]
        original = {'selection': {'fixture': 'original'}}
        selected = {'selection': {'fixture': 'selected'}}

        def images(selection):
            return {
                'control': {'Config': {'Labels': {'vibebench.fast-system-update':
                    label if selection == selected['selection'] else '1'}}},
                'account': {'Config': {'Labels': {'vibebench.fast-system-update': '1'}}},
            }

        self.host.verify_images = images
        self.host.request = Mock()
        self.assertEqual(label, '0')
        self.assertFalse(self.host.fast_transition(original, selected))
        self.assertFalse(self.host.fast_transition(selected, original))
        self.host.request.assert_not_called()

    def test_tui_receipts_allow_rolling_and_preserve_nonrolling_guard(self) -> None:
        """旧网关待回执走自然排空，真实活动与同代约束均保留。@return 无。"""
        gate = {'phase': 'blocked', 'operation_id': 'original', 'epoch': 'epoch', 'active': 0}
        original = {**gate, 'tui_tool_pending': True}
        runtime = {**gate, 'scope': 'control', 'ready': True, 'environments': []}
        self.host.request = Mock(side_effect=[original, runtime, original])
        operation = {**self.operation, 'rolling_accounts': True}
        self.assertFalse(self.host.cancel_inference(operation))
        self.assertTrue(self.host.drained(operation)['ready'])
        self.assertNotIn('/admin/runtime/system-update/cutover', [call.args[1] for call in self.host.request.call_args_list])
        self.host.request = Mock(side_effect=[runtime, {**original, 'active': 1}])
        self.assertFalse(self.host.drained(operation)['ready'])
        self.host.request = Mock(side_effect=[runtime, original])
        with self.assertRaisesRegex(ValueError, '原 V2 工具轮'):
            self.host.drained(self.operation)
        self.host.request = Mock(return_value={**original, 'epoch': 'wrong'})
        with self.assertRaisesRegex(ValueError, '代次'):
            self.host.cancel_inference(operation)

    def test_raced_legacy_receipt_and_scoped_gateway_cutover(self) -> None:
        """旧版只识别确切门禁拒绝，新版受证取消无关推理。@return 无。"""
        operation = {**self.operation, 'rolling_accounts': True}
        gate = {'phase': 'blocked', 'operation_id': 'original', 'epoch': 'epoch', 'active': 0}
        error = HTTPError('http://fixture', 503, '待工具回执', None, BytesIO(
            '{"error":"service unavailable: 请先完成原 V2 工具轮，再切换服务"}'.encode()))
        self.host.request = Mock(side_effect=[{**gate, 'tui_tool_pending': False}, error, {**gate, 'tui_tool_pending': True}])
        self.assertFalse(self.host.cancel_inference(operation))
        self.host.request = Mock(side_effect=[{**gate, 'tui_tool_pending': True, 'tui_receipt_cutover': True},
            {**gate, 'accepted': True, 'preserve_tui': True}])
        self.assertFalse(self.host.cancel_inference(operation))
        self.assertEqual(self.host.request.call_args.args[2], {
            'operation_id': 'original', 'epoch': 'epoch', 'preserve_tui': True})

    def test_abandon_before_node_backup_leaves_other_nodes_untouched(self) -> None:
        """移除阻止排空时，仅释放本次平台门禁。:return: 无。"""
        self.host.env = 'test-only'
        self.host.request = Mock()
        self.host.controls = Mock(return_value={})
        self.host.release = Mock()
        self.operation.update(node_backup_requested=False)
        self.operation['before'].update(env_sha256=sha256(b'test').hexdigest(), controls={})
        with patch('system_update_host.safe_read', return_value=b'test'):
            self.host.abandon(self.operation)
        self.host.request.assert_not_called()
        self.host.release.assert_called_once_with(self.operation)


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

    def test_failed_node_removal_prevents_switching_back_to_older_control(self) -> None:
        """回退使用相同排空保护并释放原平台门禁，待移除节点不交给旧版。:return: 无。"""
        fixture = test_system_updater.SystemUpdaterTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.engine.submit('install', fixture.request())
        self.assertEqual('succeeded', fixture.join()['operation']['phase'])
        prior_calls = len(fixture.backend.calls)

        def blocked(operation):
            """使用待移除的真实宿主排空判断。:param operation: 原平台操作。:return: 排空结果。"""
            host = HostDeployment.__new__(HostDeployment)
            gate = {'phase': 'blocked', 'epoch': operation['epoch'], 'active': 0}
            host.request = Mock(side_effect=[{**gate, 'node_removals': [{'name': '隔离节点', 'state': 'needs_check'}]}, gate])
            return host.drained(operation)

        fixture.backend.drained = blocked
        fixture.engine.submit('rollback', fixture.request(fixture.old))
        state = fixture.join()
        self.assertEqual('failed', state['operation']['phase'])
        self.assertIn('重试移除', state['operation']['error'])
        self.assertEqual(fixture.target['release'], state['current_release'])
        self.assertIn('abandon', fixture.backend.calls[prior_calls:])
        self.assertNotIn('switch', fixture.backend.calls[prior_calls:])
        self.assertFalse(fixture.backend.blocked)
