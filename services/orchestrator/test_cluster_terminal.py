"""具体节点终端的一次性启动、输入未知与原scope定位验证。"""
from __future__ import annotations

import json
import threading
import unittest
from unittest.mock import Mock, patch

from cluster_execution_grants import ExecutionGrant, ExecutionGrants, ExecutionLeaseProof
from cluster_runtime_host import NodeRuntimeHost
from cluster_terminal import (NodeTerminals, TerminalCapture, TerminalControl, TerminalInput, TerminalInputQuery, TerminalMaintenance,
    TerminalObserve, TerminalPassiveAck, TerminalResolution, TerminalStart, TerminalWork)
from runtime_files import atomic_json
from test_cluster_runtime_host import _HostedRuntime
import test_cluster_execution as execution_fixture


class NodeTerminalTests(unittest.TestCase):
    """运行真实投影、证明和持久回执，终端执行使用受控离线替身。"""

    def setUp(self) -> None:
        """建立已准备节点和中央未认领的终端证明。:return: None。"""
        fixture = execution_fixture.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.executor, self.now = fixture, fixture.executor, 1000
        self.host = NodeRuntimeHost(self.executor, runtime_factory=_HostedRuntime)
        self.addCleanup(self.host.close)
        self.grants = ExecutionGrants(fixture.root, fixture.node_key, 'synthetic', self.executor.database, lambda: self.now)
        self.host.attach_grants(self.grants)
        self.executor.prepare(fixture.request)
        self.work = TerminalWork(id='c' * 32, account_id=1, generation=1,
            session_id='11111111-2222-4333-8444-555555555555', project_key='synthetic-project', objective_id='FIRST',
            library_digest='f' * 64, settings_json=json.dumps({'claude_code_version': '2.1.303', 'claude_effort_level': 'high'}),
            remaining_sec=60, created_at=1000.0)
        source = 'projects:' + self.work.id + ':1'
        self.grant = ExecutionGrant(operation_id='d' * 32, node_key=fixture.node_key, account_id=1, gateway_account_id=7,
            environment_id='e' * 32, assignment_revision=1, generation=1, source=source, role='projects',
            not_after=1020, lease=ExecutionLeaseProof(owner=source, generation='original-lease', expires_at=1020,
                exclusive=False, shared_cli=True))
        self.scope = self.grant.scope()
        self.grants.create(self.grant)
        self.terminal = Mock()
        self.terminal.start.return_value = {'token': 'original-token', 'source': source, 'workspace': 'environments/synthetic/projects/owned'}
        self.terminal.observe.return_value = {'screen': '合成画面', 'cursor': 25, 'running': True}
        self.terminals = NodeTerminals(self.executor, self.host, self.grants, Mock(return_value=self.terminal))
        self.terminals.catalogs[self.work.library_digest] = object()
        self.request = TerminalStart(scope=self.scope, work=self.work)

    def input(self, operation_id: str = '1' * 32) -> TerminalInput:
        """构造独立原样输入。:param operation_id: 原操作。:return: 受限输入。"""
        return TerminalInput(scope=self.scope, operation_id=operation_id, text='合成输入', submit=True)

    def test_start_retries_only_return_original_receipt_and_node_owned_paths(self) -> None:
        """同一操作仅启动一次，节点按冻结摘要计算资产根和运行定位。:return: None。"""
        result = self.terminals.start(self.request)
        self.assertEqual('ready', result['phase'])
        self.assertEqual(result, self.terminals.start(self.request))
        self.terminal.start.assert_called_once()
        work = self.terminal.start.call_args.args[1]
        self.assertEqual(str(self.fixture.root / 'project-library/releases' / self.work.library_digest), work['library_root'])
        self.assertNotIn('work', result)
        changed = self.request.model_copy(update={'work': self.work.model_copy(update={'remaining_sec': 59})})
        with self.assertRaisesRegex(ValueError, '冻结工作'):
            self.terminals.start(changed)
        self.assertEqual('active', self.grants.get(self.scope)['phase'])

    def test_prepared_without_node_start_can_close_and_late_start_is_fenced(self) -> None:
        """启动前中央失败可撤销prepared许可，迟到启动继续拒绝。:return: None。"""
        self.assertEqual('NodeReceiptMissing', self.terminals.get(self.scope)['error_type'])
        self.assertEqual({'stopped': True}, self.terminals.recover_stop(self.scope))
        self.assertEqual('closed', self.terminals.get(self.scope)['phase'])
        self.assertEqual('node_not_started', self.grants.get(self.scope)['closed_reason'])
        with self.assertRaises(ValueError):
            self.terminals.start(self.request)
        self.terminal.start.assert_not_called()

    def test_active_without_receipt_keeps_unknown_and_failed_tombstone_retries_original_close(self) -> None:
        """已认领缺回执继续待核对，prepared撤销落盘失败沿原关闭原因恢复。:return: None。"""
        with patch('cluster_terminal.atomic_json', side_effect=OSError('合成标记落盘失败')):
            with self.assertRaises(OSError):
                self.terminals.recover_stop(self.scope)
        self.assertEqual('closed', self.grants.get(self.scope)['phase'])
        self.assertEqual('reconcile', self.terminals.get(self.scope)['phase'])
        self.terminals.recover_stop(self.scope)
        self.assertEqual('closed', self.terminals.get(self.scope)['phase'])
        grant = self.grant.model_copy(update={'operation_id': '9' * 32})
        self.grants.create(grant)
        self.grants.activate(grant.scope())
        with self.assertRaisesRegex(ValueError, '已认领且缺少回执'):
            self.terminals.recover_stop(grant.scope())
        self.assertEqual('active', self.grants.get(grant.scope())['phase'])

    def test_passive_outbox_repeats_original_fact_until_central_persistence_acknowledged(self) -> None:
        """中央响应丢失和重建节点读取器均保留原补证，确认后才读取下一事实。:return: None。"""
        self.terminals.start(self.request)
        facts = {'evidence_key': 'a' * 64, 'quota_limited': True, 'window': 'unknown', 'observed_at': 1001.0}

        def read(_work):
            callback = self.terminals.terminal_factory.call_args.kwargs['quota_observation']
            callback({'id': 1}, self.scope.source, facts)
            return facts

        self.terminal.passive_status.side_effect = read
        self.assertEqual(facts, self.terminals.read(self.scope, 'passive'))
        self.assertEqual(facts, self.terminals.read(self.scope, 'passive'))
        self.terminal.passive_status.assert_called_once()
        with self.assertRaisesRegex(ValueError, '其他'):
            self.terminals.ack_passive(TerminalPassiveAck(scope=self.scope, evidence_key='b' * 64))
        response = self.terminals.ack_passive(TerminalPassiveAck(scope=self.scope, evidence_key='a' * 64))
        self.assertEqual(response, self.terminals.ack_passive(TerminalPassiveAck(scope=self.scope, evidence_key='a' * 64)))
        self.terminal.passive_status.side_effect = None
        self.terminal.passive_status.return_value = {'evidence_key': None}
        self.assertEqual({'evidence_key': None}, self.terminals.read(self.scope, 'passive'))
        self.assertEqual(2, self.terminal.passive_status.call_count)

    def test_capture_and_cleanup_reuse_original_work_and_require_closed_current_scope(self) -> None:
        """抓包只消费原工作，清理须已收口且仍属于当前归属。:return: None。"""
        self.terminals.start(self.request)
        self.terminal.capture.return_value = {'status': 'collecting'}
        self.terminals.capture(TerminalCapture(scope=self.scope, relative='capture_index.json', running=True))
        work, relative = self.terminal.capture.call_args.args
        self.assertEqual('capture_index.json', relative)
        self.assertEqual(self.work.id, work['id'])
        request = TerminalMaintenance(**self.request.model_dump(), operation='cleanup-cycle')
        with self.assertRaisesRegex(ValueError, '收口'):
            self.terminals.maintenance(request)
        self.terminals.control(TerminalControl(scope=self.scope, operation='stop'))
        self.assertEqual({'cleaned': True, 'cycle_no': 1}, self.terminals.maintenance(request))
        self.terminal.cleanup_cycle.assert_called_once()
        with self.assertRaises(ValueError):
            self.terminals.maintenance(request.model_copy(update={'scope': self.scope.model_copy(update={'assignment_revision': 2})}))

    def test_unknown_start_is_durable_and_restart_never_launches_again(self) -> None:
        """启动异常只记录类型，重建节点操作对象后继续查询原未知结果。:return: None。"""
        self.terminal.start.side_effect = RuntimeError('synthetic-sensitive-error')
        result = self.terminals.start(self.request)
        self.assertEqual('reconcile', result['phase'])
        restarted = NodeTerminals(self.executor, self.host, self.grants, Mock(side_effect=AssertionError('不能重启原操作')))
        self.assertEqual(result, restarted.start(self.request))
        self.assertEqual(result, restarted.get(self.scope))
        self.assertNotIn('synthetic-sensitive-error', json.dumps(result))
        self.terminal.start.assert_called_once()

    def test_restart_read_projects_original_ready_receipt_as_reconcile_before_runtime_recovery(self) -> None:
        """新节点进程只有原磁盘回执时明确待核对，原启动事实继续保存。:return: None。"""
        self.terminals.start(self.request)
        original = self.host.runtime
        self.host.runtime = None
        try:
            observed = self.terminals.get(self.scope)
            self.assertEqual('reconcile', observed['phase'])
            self.assertEqual('NodeRestart', observed['error_type'])
            self.assertEqual('ready', self.terminals._record(self.scope)['phase'])
        finally:
            self.host.runtime = original

    def test_unknown_start_recovery_needs_actual_idle_cli_before_closed_receipt(self) -> None:
        """未知启动和空内存jobs仍核对实际CLI，活动进程继续阻止关闭。:return: None。"""
        self.terminal.start.side_effect = ConnectionError('原启动响应未知')
        self.terminals.start(self.request)
        runtime = self.host.runtime
        runtime.restore_execution = Mock(return_value=None)
        child = Mock(status='running')
        child.exec_run.return_value = Mock(exit_code=0)
        runtime._container = Mock(return_value=child)
        self.now = 1030
        with self.assertRaisesRegex(ValueError, '实际CLI'):
            self.terminals.recover_stop(self.scope)
        self.assertEqual('reconcile', self.terminals.get(self.scope)['phase'])
        child.exec_run.return_value = Mock(exit_code=1)
        self.assertEqual({'stopped': True}, self.terminals.recover_stop(self.scope))
        self.assertEqual('closed', self.terminals.get(self.scope)['phase'])
        self.assertEqual('closed', self.grants.get(self.scope)['phase'])
        self.assertEqual([], self.host.gateway.lease_mirror.request('GET', '/admin/runtime/accounts/7/lease')['holders'])

    def test_restart_recovery_reuses_original_job_and_rejects_another_execution_token(self) -> None:
        """原持久执行只按原token收口，其他进程定位继续被拒绝。:return: None。"""
        self.terminals.start(self.request)
        runtime = self.host.runtime
        job = {'token': 'other-token', 'source': self.scope.source}
        runtime.restore_execution = Mock(return_value=job)
        runtime.cleanup = Mock()
        runtime._execution_path = Mock(return_value=self.fixture.root / 'missing-original-execution.json')
        runtime.environment_jobs = Mock(return_value=[])
        with self.assertRaisesRegex(ValueError, 'token'):
            self.terminals.recover_stop(self.scope)
        runtime.cleanup.assert_not_called()
        job['token'] = 'original-token'
        self.assertEqual({'stopped': True}, self.terminals.recover_stop(self.scope))
        runtime.cleanup.assert_called_once_with('original-token')

    def test_independent_terminal_recovers_unknown_stop_and_releases_source_binding(self) -> None:
        """独立证明超期保留现场，原实际CLI空闲后才关闭并解除来源绑定。:return: None。"""
        connection = self.executor.database()
        try:
            with connection:
                connection.execute('UPDATE accounts SET cc2api_account_id=NULL WHERE id=1')
        finally:
            connection.close()
        grant = self.grant.model_copy(update={'operation_id': '9' * 32, 'gateway_account_id': None, 'lease': None})
        scope = grant.scope()
        self.grants.create(grant)
        self.terminal.start.side_effect = ConnectionError('合成独立启动结果未知')
        self.assertEqual('reconcile', self.terminals.start(self.request.model_copy(update={'scope': scope}))['phase'])
        runtime = self.host.runtime
        runtime.restore_execution = Mock(return_value=None)
        child = Mock(status='running')
        child.exec_run.return_value = Mock(exit_code=0)
        runtime._container = Mock(return_value=child)
        self.now = 1030
        with self.assertRaisesRegex(ValueError, '实际CLI'):
            self.terminals.recover_stop(scope)
        child.exec_run.return_value = Mock(exit_code=1)
        self.assertEqual({'stopped': True}, self.terminals.recover_stop(scope))
        self.assertEqual('closed', self.terminals.get(scope)['phase'])
        self.assertNotIn((None, scope.source), self.host.gateway.lease_mirror.scopes)
        self.assertIsNone(runtime.restore_execution.call_args.args[3])
        self.assertEqual({'shared_cli': True}, runtime.restore_execution.call_args.kwargs)

    def test_unknown_input_preserves_intent_and_blocks_following_input(self) -> None:
        """未知投递保持原回执，重复请求与后续不同输入均不会再次投递。:return: None。"""
        self.terminals.start(self.request)
        self.terminal.send.side_effect = RuntimeError('synthetic-private-text')
        receipt = self.terminals.send(self.input())
        self.assertEqual('unknown', receipt['status'])
        self.assertEqual(receipt, self.terminals.send(self.input()))
        self.terminal.send.assert_called_once()
        self.now = 1021
        query = TerminalInputQuery(scope=self.scope, operation_id='1' * 32)
        self.assertEqual(receipt, self.terminals.input_receipt(query))
        with self.assertRaisesRegex(ValueError, '尚未核对'):
            self.terminals.send(self.input('2' * 32))
        with self.assertRaisesRegex(ValueError, '内容已变化'):
            self.terminals.send(self.input().model_copy(update={'text': 'changed'}))
        self.assertEqual('1' * 32, self.terminals.get(self.scope)['pending_input'])
        self.assertNotIn('synthetic-private-text', json.dumps(receipt))

    def test_sent_receipt_allows_next_operation_and_does_not_repeat_old_input(self) -> None:
        """已确认投递后解除原未决指针，重试仍返回原sent回执。:return: None。"""
        self.terminals.start(self.request)
        receipt = self.terminals.send(self.input())
        self.assertEqual('sent', receipt['status'])
        self.assertEqual(receipt, self.terminals.send(self.input()))
        self.assertIsNone(self.terminals.get(self.scope)['pending_input'])
        self.assertEqual('sent', self.terminals.send(self.input('2' * 32))['status'])
        self.assertEqual(2, self.terminal.send.call_count)

    def test_expiry_or_fence_closes_new_input_and_keeps_original_observation(self) -> None:
        """过期关闭新投递，观察仍读取节点保存的原token与路径。:return: None。"""
        self.terminals.start(self.request)
        self.now = 1021
        with self.assertRaisesRegex(ValueError, '过期'):
            self.terminals.send(self.input())
        self.assertEqual('合成画面', self.terminals.observe(TerminalObserve(scope=self.scope))['screen'])
        observed_work = self.terminal.observe.call_args.args[0]
        self.assertEqual('original-token', json.loads(observed_work['runtime_json'])['token'])
        self.now = 1000
        atomic_json(self.fixture.root / 'environments' / self.scope.environment_id / 'runtime/node-fence.json', {'phase': 'fenced'})
        with self.assertRaisesRegex(ValueError, '隔离'):
            self.terminals.send(self.input())
        self.terminal.send.assert_not_called()
        with self.assertRaisesRegex(ValueError, '范围变化'):
            self.terminals.get(self.scope.model_copy(update={'generation': 2}))

    def test_manual_resolution_keeps_original_input_as_receipt_and_allows_next(self) -> None:
        """人工核对结论幂等，原输入仍只查询，下一独立动作重新核对许可。:return: None。"""
        self.terminals.start(self.request)
        self.terminal.send.side_effect = RuntimeError('合成未知')
        self.terminals.send(self.input())
        resolution = TerminalResolution(scope=self.scope, operation_id='1' * 32, resolution_id='9' * 32, sent=False)
        receipt = self.terminals.resolve_input(resolution)
        self.assertEqual('not_sent', receipt['status'])
        self.assertEqual(receipt, self.terminals.resolve_input(resolution))
        self.assertEqual(receipt, self.terminals.send(self.input()))
        self.terminal.send.assert_called_once()
        with self.assertRaisesRegex(ValueError, '另一人工结论'):
            self.terminals.resolve_input(resolution.model_copy(update={'sent': True}))
        self.terminal.send.side_effect = None
        self.assertEqual('sent', self.terminals.send(self.input('2' * 32))['status'])

    def test_confirmed_input_repairs_pending_pointer_without_replaying(self) -> None:
        """确认回执落盘后崩溃的未决指针可按原sent事实收口。:return: None。"""
        self.terminals.start(self.request)
        receipt = self.terminals.send(self.input())
        path = self.terminals._directory(self.scope) / 'execution.json'
        record = json.loads(path.read_text())
        record['pending_input'] = '1' * 32
        atomic_json(path, record)
        self.assertEqual(receipt, self.terminals.send(self.input()))
        self.assertIsNone(self.terminals.get(self.scope)['pending_input'])
        self.terminal.send.assert_called_once()

    def test_starting_receipt_can_be_read_while_original_start_holds_lock(self) -> None:
        """长准备持锁时仍可查询原starting收据，重复查询不启动第二次。:return: None。"""
        entered, finish = threading.Event(), threading.Event()
        answer = self.terminal.start.return_value

        def slow_start(*args):
            entered.set()
            finish.wait(3)
            return answer

        self.terminal.start.side_effect = slow_start
        results = []
        thread = threading.Thread(target=lambda: results.append(self.terminals.start(self.request)), daemon=True)
        thread.start()
        try:
            self.assertTrue(entered.wait(1))
            self.assertEqual('starting', self.terminals.get(self.scope)['phase'])
        finally:
            finish.set()
            thread.join(3)
        self.assertEqual('ready', results[0]['phase'])
        self.terminal.start.assert_called_once()


if __name__ == '__main__':
    unittest.main()
