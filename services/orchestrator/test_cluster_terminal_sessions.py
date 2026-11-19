"""中央真实租约协调接口、持久会话及提交未知恢复的离线合同验证。"""
from __future__ import annotations

import copy
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_runtime import RuntimeBusy
from cluster_terminal import TerminalStart
from cluster_terminal_sessions import TerminalSessions
from runtime_files import atomic_json
from system_update_gate import DeploymentGate
import test_cluster_execution_store as store_fixture


class _Gateway:
    """提供原网关共享CLI模式、同代认领与释放语义的执行替身。"""

    def __init__(self) -> None:
        """建立空闲租约与独立调用记录。:return: None。"""
        self.lease, self.calls = None, []
        self.unknown_release = False

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == 'POST':
            operation = payload['operation']
            if operation in ('prepare-cli', 'prepare-cli-shared'):
                if self.lease is not None:
                    raise RuntimeBusy('合成CLI已占用')
                self.lease = {'owner': payload['owner'], 'generation': 'original-real-lease',
                    'expires_at': int(time.time()) + 30, 'exclusive': False,
                    'shared_cli': operation == 'prepare-cli-shared', 'phase': 'prepared'}
            else:
                if self.lease is None or any(payload[key] != self.lease[key] for key in ('owner', 'generation')):
                    raise ValueError('合成原租约代次不匹配')
                if operation == 'release':
                    self.lease = None
                    if self.unknown_release:
                        raise ConnectionError('合成释放已应用但响应丢失')
                else:
                    if operation == 'claim':
                        self.lease['phase'] = 'claimed'
                    self.lease['expires_at'] = int(time.time()) + 30
        return {'holders': [copy.deepcopy(self.lease)] if self.lease else [], 'lease': copy.deepcopy(self.lease),
            'active': 0, 'importing': 0}


class _Peer:
    """记录固定节点操作，未知提交仍保留原节点收据。"""

    def __init__(self) -> None:
        """建立节点私有收据与可控故障开关。:return: None。"""
        self.grant, self.receipt, self.calls = None, None, []
        self.unknown_start = self.unknown_stop = self.fail_renew = False

    def execution_environment(self, container, payload, operation):
        """按原私有协议返回可核对结果。:param container: 原容器。:param payload: 冻结输入。:param operation: 固定动作。:return: 私有回执。"""
        self.calls.append(operation)
        if operation == 'grant-create':
            self.grant = copy.deepcopy(payload)
            value, key = {'grant': self.grant, 'phase': 'prepared'}, 'record'
        elif operation == 'grant-renew':
            if self.fail_renew:
                raise ConnectionError('合成证明续接未知')
            self.grant = copy.deepcopy(payload)
            value, key = {'grant': self.grant, 'phase': 'active'}, 'record'
        elif operation == 'terminal-start':
            self.receipt = {'protocol': 1, 'scope': payload['scope'], 'phase': 'ready',
                'result': {'token': 'synthetic-original-token', 'source': payload['scope']['source']}, 'pending_input': None}
            if self.unknown_start:
                raise ConnectionError('合成节点已启动但响应丢失')
            value, key = self.receipt, 'terminal'
        elif operation == 'terminal-get':
            value, key = self.receipt, 'terminal'
        elif operation == 'terminal-control':
            if payload['operation'] == 'stop':
                self.receipt['phase'] = 'closed'
                if self.unknown_stop:
                    raise ConnectionError('合成节点已停止但响应丢失')
                value = {'stopped': True}
            else:
                value = {'source': payload['scope']['source'], 'operation': payload['operation']}
            key = 'terminal'
        elif operation == 'terminal-send':
            value, key = {'status': 'sent', 'operation_id': payload['operation_id']}, 'terminal'
        elif operation == 'terminal-input':
            value, key = {'status': 'sent', 'operation_id': payload['operation_id'], 'scope': payload['scope']}, 'terminal'
        elif operation == 'terminal-reconcile':
            self.receipt['pending_input'] = None
            value, key = {'status': 'sent' if payload['sent'] else 'not_sent',
                'operation_id': payload['operation_id']}, 'terminal'
        else:
            value, key = {}, 'terminal'
        return {'protocol': 1, 'node_key': 'b' * 32, key: copy.deepcopy(value)}


class TerminalSessionTests(unittest.TestCase):
    """实际中央账本与原Gateway/节点合同替身联合验证恢复边界。"""

    def setUp(self) -> None:
        """准备独立中央SQLite、账号及同批节点。:return: None。"""
        fixture = store_fixture.NodeExecutionStoreTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.gateway, self.peer = fixture, _Gateway(), _Peer()
        service = SimpleNamespace(store=fixture.fixture.store, connection=lambda node: self.peer)
        self.admit, self.release = Mock(return_value='synthetic-quota'), Mock()
        self.sessions = TerminalSessions(fixture.ledger, service, SimpleNamespace(deployment='synthetic'),
            self.gateway, self.admit, self.release)
        self.addCleanup(self.sessions.close)
        self.request = TerminalStart(scope=fixture.scope, work=fixture.work)

    def test_start_and_stop_keep_actual_original_lease_and_both_receipts(self) -> None:
        """重复启动查询原账本，中央同代续约，节点停止后才释放原许可。:return: None。"""
        row = self.sessions.start(self.request)
        self.assertEqual('running', row['phase'])
        self.assertEqual(row, self.sessions.start(self.request))
        self.assertEqual(1, self.peer.calls.count('terminal-start'))
        renewed = self.sessions.renew(self.fixture.scope.operation_id)
        self.assertEqual(2, renewed['record']['grant']['sequence'])
        self.assertEqual('original-real-lease', renewed['record']['lease']['generation'])
        self.release.assert_not_called()
        result = self.sessions.stop(self.fixture.scope.operation_id)
        self.assertEqual('closed', result['phase'])
        self.assertEqual('closed', result['record']['node_receipt']['phase'])
        self.assertTrue(result['record']['lease_released']['released'])
        self.assertIsNone(self.gateway.lease)
        self.release.assert_called_once()
        self.assertFalse(self.release.call_args.args[2])

    def test_independent_account_uses_finite_admission_without_gateway_calls(self) -> None:
        """独立账号实际停止与额度释放后才关闭，网关调用数保持零。:return: None。"""
        connection = self.fixture.fixture.database()
        try:
            with connection:
                connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
        finally:
            connection.close()
        self.sessions.runtime.environment_jobs = Mock(return_value=[])
        request = self.request.model_copy(update={'scope': self.request.scope.model_copy(update={'gateway_account_id': None})})
        row = self.sessions.start(request)
        self.assertEqual('running', row['phase'])
        self.assertTrue(row['record']['local_admission_intent'])
        self.assertIsNone(row['record']['grant']['lease'])
        self.assertIsNone(row['record']['lease'])
        renewed = self.sessions.renew(request.scope.operation_id)
        self.assertEqual(2, renewed['record']['grant']['sequence'])
        with patch('cluster_terminal_sessions.time.time', return_value=renewed['record']['grant']['not_after'] + 1):
            with self.assertRaisesRegex(RuntimeBusy, '已过期'):
                self.sessions.renew(request.scope.operation_id)
        self.release.side_effect = ValueError('合成额度释放待核对')
        with self.assertRaisesRegex(ValueError, '额度释放'):
            self.sessions.stop(request.scope.operation_id)
        self.assertFalse(self.fixture.ledger.get(request.scope.operation_id)['record']['local_admission_released'])
        self.release.side_effect = None
        closed = self.sessions.stop(request.scope.operation_id)
        self.assertEqual('closed', closed['phase'])
        self.assertTrue(closed['record']['local_admission_released'])
        self.assertIsNone(closed['record']['lease_released'])
        self.assertEqual([], self.gateway.calls)

    def test_unknown_gateway_prepare_before_node_grant_can_cancel_original_admission(self) -> None:
        """网关prepare已完成但响应丢失时，节点提交前仍能核对并撤销原许可。:return: None。"""
        original = self.gateway._request

        def request(method, path, payload=None):
            result = original(method, path, payload)
            if payload and payload.get('operation') in ('prepare-cli', 'prepare-cli-shared'):
                raise ConnectionError('合成prepare响应丢失')
            return result

        self.gateway._request = Mock(side_effect=request)
        with self.assertRaises(ConnectionError):
            self.sessions.start(self.request)
        row = self.fixture.ledger.get(self.request.scope.operation_id)
        self.assertIsNone(row['record']['grant'])
        self.assertEqual([], self.peer.calls)
        self.release.side_effect = ValueError('合成额度释放失败')
        with self.assertRaisesRegex(ValueError, '额度释放失败'):
            self.sessions.stop(self.request.scope.operation_id)
        self.assertIsNone(self.gateway.lease)
        self.assertEqual('reconcile', self.fixture.ledger.get(self.request.scope.operation_id)['phase'])
        self.release.side_effect = None
        closed = self.sessions.stop(self.request.scope.operation_id)
        self.assertTrue(closed['record']['node_start_cancelled'])
        self.assertTrue(closed['record']['lease_released']['released'])
        self.assertIsNone(closed['record']['node_receipt'])
        self.assertEqual('closed', closed['phase'])
        self.assertTrue(self.release.call_args.args[2])
        self.assertEqual([], self.peer.calls)

    def test_restart_restores_old_maintenance_activity_and_stops_before_any_new_input(self) -> None:
        """维护中重启先恢复原占用，只允许按原节点停止和真实租约释放收口。:return: None。"""
        self.sessions.start(self.request)
        self.sessions.close()
        root = self.fixture.fixture.path.parent / 'maintenance-gate'
        atomic_json(root / 'admission.json', {'schema_version': 1, 'deployment': 'synthetic',
            'operation_id': str(uuid.uuid4()), 'epoch': str(uuid.uuid4()), 'phase': 'blocked',
            'target_release': 'system-ci-1-1', 'revision': str(uuid.uuid4()), 'created_at': '2026-11-17T00:00:00Z'})
        gate = DeploymentGate(root, 'synthetic')
        restored = TerminalSessions(self.fixture.ledger, self.sessions.service, self.sessions.runtime,
            self.gateway, self.admit, self.release, activity_gate=gate)
        self.addCleanup(restored.close)
        before = list(self.peer.calls)
        self.assertEqual({'recovered': 1, 'invalid': []}, restored.recover())
        self.assertEqual(before, self.peer.calls)
        self.assertEqual(1, gate.state()['active'])
        self.assertEqual('reconcile', self.fixture.ledger.get(self.fixture.scope.operation_id)['phase'])
        with self.assertRaises(ValueError):
            restored.send(self.fixture.scope.operation_id, '1' * 32, '过期后新输入', [], True)
        self.assertEqual('closed', restored.stop(self.fixture.scope.operation_id)['phase'])
        self.assertEqual(0, gate.state()['active'])

    def test_unknown_start_keeps_real_holder_and_never_replays_start(self) -> None:
        """启动回执丢失保留真实占用，重试只查询原reconcile，停止沿原节点收据收口。:return: None。"""
        self.peer.unknown_start = True
        with self.assertRaises(ConnectionError):
            self.sessions.start(self.request)
        row = self.sessions.start(self.request)
        self.assertEqual('reconcile', row['phase'])
        self.assertEqual(1, self.peer.calls.count('terminal-start'))
        self.assertIsNotNone(self.gateway.lease)
        self.release.assert_not_called()
        self.assertEqual('ready', self.sessions.node_state(self.fixture.scope.operation_id)['phase'])
        self.assertEqual('closed', self.sessions.stop(self.fixture.scope.operation_id)['phase'])

    def test_quota_rejection_before_gateway_intent_is_known_not_started(self) -> None:
        """中央额度拒绝时关闭本处理者的未提交登记，原节点启动入口保持关闭。:return: None。"""
        self.admit.side_effect = RuntimeBusy('合成额度未放行')
        with self.assertRaises(RuntimeBusy):
            self.sessions.start(self.request)
        row = self.fixture.ledger.get(self.fixture.scope.operation_id)
        self.assertEqual(('closed', 'central_not_started'), (row['phase'], row['record']['failure']))
        self.assertEqual([], self.peer.calls)
        self.assertEqual(['GET'], [method for method, _, _ in self.gateway.calls])
        self.release.assert_called_once()
        self.assertTrue(self.release.call_args.args[2])

    def test_lost_stop_and_release_responses_are_resolved_by_reading_original_receipts(self) -> None:
        """停止和释放响应丢失后只读确认原结果，保持单次节点启动与原租约代次。:return: None。"""
        self.sessions.start(self.request)
        self.peer.unknown_stop, self.gateway.unknown_release = True, True
        result = self.sessions.stop(self.fixture.scope.operation_id)
        self.assertEqual('closed', result['phase'])
        self.assertEqual(1, self.peer.calls.count('terminal-start'))
        self.assertIn('terminal-get', self.peer.calls)
        self.assertEqual('GET', self.gateway.calls[-1][0])

    def test_unknown_proof_renewal_closes_new_central_input_and_preserves_actual_holder(self) -> None:
        """节点续接未知立即隔离下一输入，原真实租约和节点收据保留。:return: None。"""
        self.sessions.start(self.request)
        self.peer.fail_renew = True
        with self.assertRaises(ConnectionError):
            self.sessions.renew(self.fixture.scope.operation_id)
        self.assertEqual('reconcile', self.fixture.ledger.get(self.fixture.scope.operation_id)['phase'])
        self.assertIsNotNone(self.gateway.lease)
        with self.assertRaises(ValueError):
            self.sessions.send(self.fixture.scope.operation_id, '1' * 32, '合成后续输入', [], True)
        self.assertNotIn('terminal-send', self.peer.calls)
        self.release.assert_not_called()
        self.assertEqual('closed', self.sessions.stop(self.fixture.scope.operation_id)['phase'])

    def test_quota_release_failure_reuses_confirmed_node_and_gateway_receipts(self) -> None:
        """额度收尾失败保留已确认双端收据，恢复只重试原额度释放。:return: None。"""
        self.sessions.start(self.request)
        self.release.side_effect = RuntimeError('合成额度收尾未确认')
        with self.assertRaises(RuntimeError):
            self.sessions.stop(self.fixture.scope.operation_id)
        record = self.fixture.ledger.get(self.fixture.scope.operation_id)['record']
        self.assertEqual('closed', record['node_receipt']['phase'])
        self.assertTrue(record['lease_released']['released'])
        self.release.side_effect = None
        self.assertEqual('closed', self.sessions.stop(self.fixture.scope.operation_id)['phase'])
        self.assertEqual(1, self.peer.calls.count('terminal-control'))
        self.assertEqual(1, len([payload for method, _, payload in self.gateway.calls
            if method == 'POST' and payload['operation'] == 'release']))

    def test_disabled_account_can_stop_original_job_and_read_scope_cannot_be_overridden(self) -> None:
        """停用后关闭新操作，原停止仍可收口；只读参数保持原scope。:return: None。"""
        self.sessions.start(self.request)
        with self.assertRaisesRegex(ValueError, '参数'):
            self.sessions.read(self.fixture.scope.operation_id, 'observe', scope={'account_id': 2})
        connection = self.fixture.fixture.database()
        try:
            with connection:
                connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
        finally:
            connection.close()
        self.assertEqual('closed', self.sessions.stop(self.fixture.scope.operation_id)['phase'])

    def test_input_receipt_query_keeps_execution_and_input_identifiers_distinct(self) -> None:
        """原会话与输入操作使用独立参数，最终节点scope仍取原账本。:return: None。"""
        self.sessions.start(self.request)
        receipt = self.sessions.read(self.fixture.scope.operation_id, 'input', input_id='1' * 32)
        self.assertEqual('1' * 32, receipt['operation_id'])
        self.assertEqual(self.fixture.scope.model_dump(), receipt['scope'])
        with self.assertRaisesRegex(ValueError, '缺少'):
            self.sessions.read(self.fixture.scope.operation_id, 'input')

    def test_control_and_manual_input_resolution_preserve_original_permit_deadline(self) -> None:
        """暂停及人工输入结论不派生新租约，恢复仍引用原scope和截止。:return: None。"""
        started = self.sessions.start(self.request)
        lease = started['record']['lease']
        frozen = self.sessions.control(self.fixture.scope.operation_id, 'freeze')
        self.assertEqual(self.fixture.scope.source, frozen['source'])
        self.peer.receipt['pending_input'] = '1' * 32
        receipt = self.sessions.resolve_input(self.fixture.scope.operation_id, '1' * 32, '2' * 32, False)
        self.assertEqual('not_sent', receipt['status'])
        self.assertEqual(lease, self.fixture.ledger.get(self.fixture.scope.operation_id)['record']['lease'])
        self.assertEqual('resume', self.sessions.control(self.fixture.scope.operation_id, 'resume')['operation'])

    def test_unknown_start_remains_counted_until_both_ends_confirm_stop(self) -> None:
        """中央维护计数包含未知远程执行，双端收口后定向释放。:return: None。"""
        directory = self.fixture.fixture.path.parent / 'gate'
        atomic_json(directory / 'admission.json', {'schema_version': 1, 'deployment': 'synthetic', 'operation_id': None,
            'epoch': str(uuid.uuid4()), 'revision': str(uuid.uuid4()), 'phase': 'idle', 'target_release': None,
            'created_at': '2026-11-17T00:00:00Z'})
        gate = DeploymentGate(directory, 'synthetic')
        self.sessions.activity_gate = gate
        self.peer.unknown_start = True
        with self.assertRaises(ConnectionError):
            self.sessions.start(self.request)
        self.assertEqual(1, gate.state()['active'])
        self.sessions.stop(self.fixture.scope.operation_id)
        self.assertEqual(0, gate.state()['active'])

    def test_unsubmitted_quota_cleanup_failure_can_be_recovered_without_node_operations(self) -> None:
        """认领意图前的额度收尾故障可沿原登记恢复，实际节点与网关写入保持关闭。:return: None。"""
        self.admit.side_effect = RuntimeBusy('合成额度暂未放行')
        self.release.side_effect = RuntimeError('合成额度收尾失败')
        with self.assertRaises(RuntimeError):
            self.sessions.start(self.request)
        row = self.fixture.ledger.get(self.fixture.scope.operation_id)
        self.assertFalse(row['record']['gateway_prepare_intent'])
        self.release.side_effect = None
        result = self.sessions.stop(self.fixture.scope.operation_id)
        self.assertEqual(('closed', 'central_not_started'), (result['phase'], result['record']['failure']))
        self.assertEqual([], self.peer.calls)
        self.assertEqual(['GET'], [method for method, _, _ in self.gateway.calls])


if __name__ == '__main__':
    unittest.main()
