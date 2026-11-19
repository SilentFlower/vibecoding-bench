"""具体节点Run的冻结输入、一次性启动和中央原租约协调回归。"""
from __future__ import annotations

import base64
import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import main

from cluster_execution_grants import ExecutionGrant, ExecutionGrants, ExecutionLeaseProof
from cluster_runs import NodeRuns, RunArtifact, RunFile, RunFiles, RunRefresh, RunStart, RunTask, RunWork
from cluster_runner import ClusterRunner
from cluster_quota import quota_scope_path
from cluster_runtime_host import NodeRuntimeHost
from cluster_terminal_sessions import TerminalSessions
from runtime_files import atomic_json
from test_cluster_runtime_host import _HostedRuntime
from test_cluster_terminal_sessions import _Gateway, _Peer
import test_cluster_execution as execution_fixture
import test_cluster_execution_store as store_fixture


def frozen_run(account_id: int = 1, *, capture: bool = False) -> RunWork:
    """构造真实Run长度和原worker实际消费字段。:param account_id: 原账号。:param capture: 原捕获模式。:return: 冻结工作。"""
    return RunWork(id='abcdef123456', account_id=account_id, task=RunTask(id=9, capture_full_http=capture), worker_env={
        'RUN_ID': 'abcdef123456', 'TASK_PROMPT': '原题\n原补充', 'CLAUDE_CODE_VERSION': '2.1.303',
        'CLAUDE_CODE_EFFORT_LEVEL': 'high', 'CLAUDE_PERMISSION_MODE': 'bypassPermissions',
        'QUOTA_SOURCE': 'run:abcdef123456:0', 'ACC_NAME': 'synthetic', 'TIMEOUT_SEC': '60'})


class NodeRunTests(unittest.TestCase):
    """使用真实SQLite投影与证明，driver启动使用可观察替身。"""

    def setUp(self) -> None:
        """建立原安装、账号、有限许可和中央门禁。:return: None。"""
        fixture = execution_fixture.NodeExecutionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.executor = fixture, fixture.executor
        self.host = NodeRuntimeHost(self.executor, runtime_factory=_HostedRuntime)
        self.addCleanup(self.host.close)
        self.grants = ExecutionGrants(fixture.root, fixture.node_key, 'synthetic', self.executor.database, lambda: 1000)
        self.host.attach_grants(self.grants)
        self.executor.prepare(fixture.request)
        self.work = frozen_run()
        self.work.worker_env['ACC_NAME'] = fixture.request.account['name']
        grant = ExecutionGrant(operation_id='d' * 32, node_key=fixture.node_key, account_id=1, gateway_account_id=7,
            environment_id='e' * 32, assignment_revision=1, generation=1, source=self.work.source, role='cli',
            not_after=1020, lease=ExecutionLeaseProof(owner=self.work.source, generation='original-lease', expires_at=1020,
                exclusive=False, shared_cli=True))
        self.scope = grant.scope()
        self.grants.create(grant)
        atomic_json(quota_scope_path(fixture.root, self.scope), {'scope': self.scope.model_dump(),
            'state': {'identity': 'synthetic-quota', 'remote_cli': {'source': self.work.source, 'sample_required': False}}})
        self.host.runtime.project_iterations = None
        self.host.runtime.start_run = Mock(return_value=('original-token', 'original-token'))
        self.runs = NodeRuns(self.executor, self.host, self.grants)
        self.request = RunStart(scope=self.scope, work=self.work)

    def test_original_driver_starts_once_and_only_this_run_is_projected(self) -> None:
        """重复提交和重建actor只查原回执，启动保持原任务与原worker字节。:return: None。"""
        result = self.runs.start(self.request)
        self.assertEqual('ready', result['phase'])
        self.assertEqual(result, NodeRuns(self.executor, self.host, self.grants).start(self.request))
        self.host.runtime.start_run.assert_called_once()
        account, task, run_id, environment, quota = self.host.runtime.start_run.call_args.args
        self.assertEqual(self.work.id, run_id)
        self.assertEqual(self.work.worker_env, environment)
        self.assertEqual(self.work.task.model_dump(), task)
        self.assertEqual(self.work.source, quota['QUOTA_SOURCE'])
        self.assertEqual('synthetic-quota', quota['QUOTA_IDENTITY'])
        connection = self.executor.database()
        try:
            self.assertEqual([(self.work.id, 1, 9)], [tuple(row) for row in connection.execute('SELECT id,account_id,task_id FROM runs')])
            self.assertEqual(0, connection.execute('SELECT count(*) FROM tasks').fetchone()[0])
        finally:
            connection.close()

    def test_unknown_start_remains_original_operation_after_actor_restart(self) -> None:
        """启动结果未知保存脱敏类型，新的actor继续读取原工作。:return: None。"""
        self.host.runtime.start_run.side_effect = RuntimeError('合成私有异常')
        result = self.runs.start(self.request)
        self.assertEqual('reconcile', result['phase'])
        self.assertNotIn('合成私有异常', str(result))
        self.assertEqual(result, NodeRuns(self.executor, self.host, self.grants).start(self.request))
        self.host.runtime.start_run.assert_called_once()

    def test_environment_and_scope_cannot_override_service_owned_targets(self) -> None:
        """拒绝任意环境变量、变更source和错误账号。:return: None。"""
        for extra in ({'V3_NODE_INPUT_SOCKET': '/tmp/other'}, {'LD_PRELOAD': '/tmp/library'}, {'QUOTA_SOURCE': 'other'}):
            raw = self.work.model_dump()
            raw['worker_env'].update(extra)
            with self.assertRaises(ValueError):
                RunWork.model_validate(raw)
        with self.assertRaises(ValueError):
            RunStart(scope=self.scope.model_copy(update={'account_id': 2}), work=self.work)

    def test_input_lock_contention_is_a_readonly_busy_receipt(self) -> None:
        """输入持锁时状态读取明确返回busy，原Run和有限许可保持原阶段。:return: None。"""
        self.runs.start(self.request)
        with self.executor._locked(environment_id=self.scope.environment_id):
            result = self.runs.poll(self.scope)
        self.assertEqual({'scope': self.scope.model_dump(), 'busy': True}, result)
        self.assertEqual('ready', self.runs.get(self.scope)['phase'])

    def test_artifact_read_uses_original_path_and_rejects_links_and_public_phase_file(self) -> None:
        """实际固定文件有界读取，链接与不私有阶段文件在读取前拒绝。:return: None。"""
        self.runs.start(self.request)
        path = self.fixture.root / 'original-artifact.json'
        self.host.runtime.run_artifact_path = Mock(return_value=path)
        path.write_bytes(b'a' * (200 * 1024))
        request = RunArtifact(scope=self.scope, name='transcript.log')
        first = self.runs.artifact(request)
        second = self.runs.artifact(request.model_copy(update={'offset': 128 * 1024}))
        self.assertEqual(128 * 1024, len(base64.b64decode(first['content'])))
        self.assertEqual(72 * 1024, len(base64.b64decode(second['content'])))
        self.assertEqual(first['file_identity'], second['file_identity'])
        path.unlink()
        path.symlink_to(self.fixture.root / 'cluster-node.json')
        with self.assertRaises(OSError):
            self.runs.artifact(request)
        path.unlink()
        path.write_text('{}')
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            self.runs.artifact(RunArtifact(scope=self.scope, name='followups.json'))
        path.chmod(0o600)
        self.assertEqual(b'{}', base64.b64decode(self.runs.artifact(RunArtifact(scope=self.scope, name='followups.json'))['content']))

    def test_closed_run_archives_original_artifact_before_next_attempt_rewrites_live_file(self) -> None:
        """实际停止回执须包含本次原产物冻结，后续尝试改写原路径仍可读旧记录。:return: None。"""
        self.runs.start(self.request)
        runtime = self.host.runtime
        job = {'token': 'original-token', 'source': self.scope.source}
        runtime.restore_execution = Mock(return_value=job)
        runtime.cleanup = Mock()
        runtime._execution_path = Mock(return_value=self.fixture.root / 'missing-execution.json')
        runtime.environment_jobs = Mock(return_value=[])
        directory = self.fixture.root / 'artifacts'
        directory.mkdir()
        runtime.run_artifact_path = Mock(side_effect=lambda _run, name: directory / name)
        (directory / 'transcript.log').write_text('原尝试转录')
        (directory / 'followups.json').write_text('{}')
        (directory / 'followups.json').chmod(0o600)
        self.runs.recover_stop(self.scope)
        self.assertEqual('closed', self.runs.get(self.scope)['phase'])
        (directory / 'transcript.log').write_text('后续尝试改写')
        result = self.runs.artifact(RunArtifact(scope=self.scope, name='transcript.log'))
        self.assertEqual('原尝试转录', base64.b64decode(result['content']).decode())
        index = self.runs._archive_index(self.scope)
        self.assertEqual(hashlib.sha256('原尝试转录'.encode()).hexdigest(), index['files']['transcript.log']['sha256'])

    def test_node_refresh_only_publishes_original_owner_result_and_same_decision_is_idempotent(self) -> None:
        """Node只同步已投影AT并回执原请求，重复或变更结论有明确边界。:return: None。"""
        self.runs.start(self.request)
        runtime = self.host.runtime
        runtime.environment_lock = Mock(return_value=threading.RLock())
        runtime.job_for_container = Mock(return_value={'row': {}, 'account': {}})
        runtime.sync_credentials = Mock()
        directory = self.fixture.root / 'refresh-artifacts'
        directory.mkdir()
        runtime.run_artifact_path = Mock(side_effect=lambda _run, name: directory / name)
        raw = b'{"reason":"auth_error"}'
        (directory / 'oauth-refresh-request.json').write_bytes(raw)
        request = RunRefresh(scope=self.scope, request_sha256=hashlib.sha256(raw).hexdigest(), ok=True)
        result = self.runs.refresh(request)
        self.assertEqual('ready', result['phase'])
        self.assertEqual(result, self.runs.refresh(request, query=True))
        self.assertEqual(result, self.runs.refresh(request))
        runtime.sync_credentials.assert_called_once()
        self.assertEqual({'ok': True}, json.loads((directory / 'oauth-refresh-result.json').read_text()))
        with self.assertRaisesRegex(ValueError, '结论已变化'):
            self.runs.refresh(request.model_copy(update={'ok': False}))

    def test_node_files_and_stats_use_frozen_scope_paths_and_readonly_pages(self) -> None:
        """原scope固定物理根，文件分页、预览和缓存用量均由实际文件产生。:return: None。"""
        self.runs.start(self.request)
        workspace = self.runs._workspace(self.scope)
        workspace.mkdir(parents=True)
        for number in range(130):
            (workspace / f'{number:03}.txt').write_text('中文产物')
        (workspace / '.claude-home').mkdir()
        (workspace / '.claude-home/secret').write_text('私有凭据')
        first = self.runs.dispatch('run-files', RunFiles(scope=self.scope).model_dump_json().encode())
        self.assertEqual(128, len(first['files']))
        second = self.runs.dispatch('run-files', RunFiles(scope=self.scope, after=first['next']).model_dump_json().encode())
        self.assertEqual(['128.txt', '129.txt'], [item['path'] for item in second['files']])
        self.assertIsNone(second['next'])
        result = self.runs.dispatch('run-file', RunFile(scope=self.scope, path='001.txt').model_dump_json().encode())
        self.assertEqual('中文产物', base64.b64decode(result['text_base64']).decode())
        with self.assertRaises(ValueError):
            RunFile(scope=self.scope, path='.claude-home/secret')
        group = self.runs._flow_group(self.scope)
        attempt = group / 'executions' / ('1' * 20)
        attempt.mkdir(parents=True)
        (attempt / 'stats.jsonl').write_text(json.dumps({'phase': 'response', 'flow_id': 'original',
            'usage': {'input_tokens': 2, 'cache_read_input_tokens': 5, 'output_tokens': 7}}))
        value = self.runs.dispatch('run-stats', self.scope.model_dump_json().encode())
        self.assertEqual((7, 7, 1, 'sidecar'), tuple(value['stats'][name] for name in ('tokens_in', 'tokens_out', 'requests', 'source')))
        with self.assertRaises((ValueError, OSError)):
            self.runs.dispatch('run-files', RunFiles(scope=self.scope.model_copy(update={'environment_id': '9' * 32})).model_dump_json().encode())


class _RunPeer(_Peer):
    """将具体Run协议映射到原租约替身，记录真实线上动作名称。"""

    def execution_environment(self, container, payload, operation):
        """沿原回执合同返回具体Run结果。:param container: 原控制容器。:param payload: 原输入。:param operation: 具体动作。:return: 原结果。"""
        if operation == 'run-poll':
            self.calls.append(operation)
            if getattr(self, 'busy_reads', 0):
                self.busy_reads -= 1
                value = {'scope': payload, 'busy': True}
            else:
                value = {'scope': payload, 'running': True, 'exit_code': None, 'worker_status': {}, 'pending_input': None}
            return {'protocol': 1, 'node_key': 'b' * 32, 'run': value}
        if operation == 'run-artifact':
            self.calls.append(operation)
            content = self.artifacts.get(payload['name'])
            offset = payload['offset']
            value = {'scope': payload['scope'], 'name': payload['name'], 'file_identity': '1:2' if content is not None else None,
                'size': len(content) if content is not None else 0, 'offset': offset,
                'content': base64.b64encode(content[offset:offset+128*1024] if content is not None else b'').decode()}
            return {'protocol': 1, 'node_key': 'b' * 32, 'run': value}
        if operation == 'run-session':
            return {'protocol': 1, 'node_key': 'b' * 32, 'run': {'scope': payload, 'session_id': 'original-session'}}
        if operation in ('run-refresh', 'run-refresh-get'):
            self.calls.append(operation)
            if operation == 'run-refresh':
                self.refresh_receipt = {'request': payload, 'phase': 'ready'}
                if getattr(self, 'refresh_unknown', False):
                    raise ConnectionError('合成发布已经完成但响应丢失')
            return {'protocol': 1, 'node_key': 'b' * 32, 'run': self.refresh_receipt}
        if operation.startswith('run-'):
            try:
                result = super().execution_environment(container, payload, 'terminal-' + operation.removeprefix('run-'))
            finally:
                self.calls[-1] = operation
            result['run'] = result.pop('terminal')
            return result
        return super().execution_environment(container, payload, operation)


class CentralRunSessionTests(unittest.TestCase):
    """具体Run与工程共用原中央执行账本及真实租约生命周期。"""

    def setUp(self) -> None:
        """准备原中央实际SQLite及固定节点替身。:return: None。"""
        fixture = store_fixture.NodeExecutionStoreTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.peer, self.gateway = fixture, _RunPeer(), _Gateway()
        service = SimpleNamespace(store=fixture.fixture.store, connection=lambda node: self.peer)
        self.sessions = TerminalSessions(fixture.ledger, service, SimpleNamespace(deployment='synthetic'),
            self.gateway, Mock(return_value='quota-synthetic'), Mock())
        self.addCleanup(self.sessions.close)
        self.work = frozen_run()
        self.scope = fixture.scope.model_copy(update={'role': 'cli', 'source': self.work.source})
        self.request = RunStart(scope=self.scope, work=self.work)

    def _register_run(self) -> ClusterRunner:
        connection = self.fixture.fixture.database()
        try:
            with connection:
                connection.execute("INSERT INTO runs(id,account_id,task_id,status,execution_source) VALUES(?,1,9,'running',?)",
                    (self.work.id, self.work.source))
        finally:
            connection.close()
        return ClusterRunner(self.sessions, Mock(return_value='quota-synthetic'))

    def test_run_uses_original_shared_lease_and_node_stop_before_central_release(self) -> None:
        """具体Run正常认领、续约与真实停止收口复用原账本。:return: None。"""
        result = self.sessions.start(self.request)
        self.assertEqual('running', result['phase'])
        self.assertEqual(self.work.model_dump(), result['record']['work'])
        self.assertIn('run-start', self.peer.calls)
        self.sessions.renew(self.scope.operation_id)
        self.assertEqual('closed', self.sessions.stop(self.scope.operation_id)['phase'])
        self.assertIn('run-control', self.peer.calls)
        self.assertIsNone(self.gateway.lease)
        # 已经停止的同一尝试不能通过新操作自动重放。
        with self.assertRaisesRegex(ValueError, '已实际收口'):
            self.fixture.ledger.begin(self.scope.model_copy(update={'operation_id': '9' * 32}), self.work)

    def test_actual_run_admission_reuses_scheduler_owner_lock_without_reacquiring_it(self) -> None:
        """普通Runner沿原已持有owner锁的回调，工程回调继续自行取锁。:return: None。"""
        self._register_run()
        self.sessions.run_quota_admit = main._remote_execution_quota_admit_locked
        self.sessions.quota_admit = Mock(side_effect=AssertionError('误用工程owner锁回调'))
        account = self.sessions._account(self.scope)
        guard = Mock()
        guard.admit.return_value = True
        owner = main._oauth_owner_lock(account['name'])
        with owner:
            with patch.multiple(main, get_db=self.fixture.fixture.database, quota_guard=guard,
                    credential_ownership=None, _quota_identity=lambda _: 'quota-synthetic',
                    _oauth_owner_lock=Mock(side_effect=AssertionError('重复领取不可重入owner锁'))):
                row = self.sessions.start(self.request)
        self.assertEqual('running', row['phase'])
        self.assertEqual('normal', guard.admit.call_args.kwargs['workload'])
        self.sessions.quota_admit.assert_not_called()

    def test_unknown_run_start_retains_central_lease_and_original_operation(self) -> None:
        """响应丢失保持reconcile，后续启动只查原账本。:return: None。"""
        self.peer.unknown_start = True
        with self.assertRaises(ConnectionError):
            self.sessions.start(self.request)
        row = self.sessions.start(self.request)
        self.assertEqual('reconcile', row['phase'])
        self.assertIsNotNone(self.gateway.lease)
        self.assertEqual(1, self.peer.calls.count('run-start'))

    def test_busy_poll_retries_only_read_and_keeps_original_start(self) -> None:
        """状态忙仅重读同scope，原启动和输入均保持一次性。:return: None。"""
        self.sessions.start(self.request)
        self.peer.busy_reads = 2
        remote = ClusterRunner(self.sessions, Mock())
        result = remote.poll('remote-run:' + self.scope.operation_id)
        self.assertTrue(result['running'])
        self.assertEqual(3, self.peer.calls.count('run-poll'))
        self.assertEqual(1, self.peer.calls.count('run-start'))
        self.assertEqual('running', self.fixture.ledger.get(self.scope.operation_id)['phase'])

    def test_original_attempt_session_and_bounded_artifacts_survive_central_attempt_increment(self) -> None:
        """额度恢复在新尝试启动前读取原source，完整产物按片段还原。:return: None。"""
        self.sessions.start(self.request)
        remote = self._register_run()
        self.peer.artifacts = {'transcript.log': b'original\n' * 40000}
        self.assertEqual(self.peer.artifacts['transcript.log'], remote.artifact(self.work.id, 'transcript.log', limit=400000))
        with self.assertRaisesRegex(ValueError, '读取上限'):
            remote.artifact(self.work.id, 'transcript.log')
        self.assertIsNone(remote.artifact(self.work.id, 'status.json'))
        connection = self.fixture.fixture.database()
        try:
            with connection:
                connection.execute('UPDATE runs SET quota_attempt=1 WHERE id=?', (self.work.id,))
        finally:
            connection.close()
        self.assertEqual(self.scope.operation_id, remote.for_run(self.work.id)['operation_id'])
        self.assertEqual('original-session', remote.latest_session(self.work.id))

    def test_public_phase_summary_and_tail_read_from_original_node(self) -> None:
        """公开入口沿原冻结计划核对远程摘要，尾部读取保留原截断语义。:return: None。"""
        self.sessions.start(self.request)
        remote = self._register_run()
        messages = ['Follow up one.', 'Follow up two.']
        digest = hashlib.sha256(json.dumps({'run_id': self.work.id, 'followups': messages}, ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.peer.artifacts = {'followups.json': json.dumps({'schema': 1, 'run_id': self.work.id,
            'plan_digest': digest, 'completed_stages': 3, 'phase': 'complete'}).encode(),
            'transcript.log': b'line\n' * 1000}
        with patch.multiple(main, cluster_runner=remote, _require_visible_run=Mock()):
            summary = main._public_followup_progress({'id': self.work.id, 'status': 'running', 'followup_plan_json': json.dumps(messages)})
            self.assertEqual(('complete', 2), (summary['phase'], summary['completed']))
            response = main.get_transcript(self.work.id, tail_bytes=1024)
            self.assertEqual('true', response.headers['x-log-truncated'])
            self.assertEqual(self.peer.artifacts['transcript.log'][-1024:].split(b'\n', 1)[1], response.body)

    def test_central_file_pages_scope_cursor_and_preview_are_validated_before_public_output(self) -> None:
        """跨scope、重复游标和越界预览拒绝，公开端点先检查运行可见性。:return: None。"""
        self.sessions.start(self.request)
        remote = self._register_run()
        scope = self.scope.model_dump()
        pages = [{'scope': scope, 'available': True, 'files': [{'path': 'a.txt', 'type': 'file', 'size': 12}], 'next': 'a.txt'},
            {'scope': scope, 'available': True, 'files': [{'path': 'b', 'type': 'dir'}], 'next': None}]
        with patch.object(self.sessions, '_call', side_effect=pages):
            self.assertEqual(['a.txt', 'b'], [item['path'] for item in remote.files(self.work.id)])
        with patch.object(self.sessions, '_call', return_value=pages[0]):
            with self.assertRaisesRegex(ValueError, '游标'):
                remote.files(self.work.id)
        bad_scope = {**scope, 'environment_id': '9' * 32}
        with patch.object(self.sessions, '_call', return_value={**pages[1], 'scope': bad_scope}):
            with self.assertRaisesRegex(ValueError, '回执'):
                remote.files(self.work.id)
        preview = {'scope': scope, 'available': True, 'path': 'a.txt', 'size': 12, 'truncated': False,
            'binary': False, 'text_base64': base64.b64encode('中文产物'.encode()).decode()}
        with patch.object(self.sessions, '_call', return_value=preview):
            self.assertEqual('中文产物', remote.file(self.work.id, 'a.txt')['text'])
        preview['text_base64'] = base64.b64encode(b'x' * 65537).decode()
        with patch.object(self.sessions, '_call', return_value=preview), self.assertRaisesRegex(ValueError, '上限'):
            remote.file(self.work.id, 'a.txt')
        with patch.multiple(main, cluster_runner=remote, _require_visible_run=Mock(side_effect=main.HTTPException(404, '隐藏运行'))):
            with patch.object(remote, 'for_run', side_effect=AssertionError('隐藏运行触发节点读取')):
                for reader in (main.list_workspace, main.get_stats, main.get_capture):
                    with self.assertRaises(main.HTTPException):
                        reader(self.work.id)

    def test_managed_refresh_keeps_original_owner_lock_and_lost_ack_only_queries_receipt(self) -> None:
        """刷新回调仅调用一次，发布响应丢失只查原scope和原请求。:return: None。"""
        self.sessions.start(self.request)
        remote = self._register_run()
        self.peer.artifacts = {'oauth-refresh-request.json': b'{"reason":"auth_error"}'}
        self.peer.refresh_unknown = True
        self.sessions.service.prepare_remote_cli = Mock()
        owner = threading.Lock()
        refresh = Mock(side_effect=lambda: self.assertTrue(owner.locked()))
        stop = Mock()
        stop.wait.return_value = stop.is_set.return_value = False
        remote.watch_managed_oauth_refresh('remote-run:' + self.scope.operation_id,
            {'id': 1, 'cc2api_account_id': 7}, stop, refresh, owner)
        refresh.assert_called_once()
        self.sessions.service.prepare_remote_cli.assert_called_once()
        self.assertEqual(1, self.peer.calls.count('run-refresh'))
        self.assertEqual(1, self.peer.calls.count('run-refresh-get'))
        self.assertEqual('running', self.fixture.ledger.get(self.scope.operation_id)['phase'])

    def test_restart_recovery_waits_for_actual_node_close_and_leaves_current_process_sources_owned(self) -> None:
        """旧节点失联保留占用，恢复后只通知旧操作，新作业的续约异常由原执行者收口。:return: None。"""
        self.sessions.start(self.request)
        remote = self._register_run()
        self.sessions.recover()
        completed = Mock()
        with patch.object(self.sessions, '_call', side_effect=ConnectionError('合成节点离线')):
            remote.recover_once(completed)
        completed.assert_not_called()
        self.assertEqual('reconcile', self.fixture.ledger.get(self.scope.operation_id)['phase'])
        self.assertIsNotNone(self.gateway.lease)

        connection = self.fixture.fixture.database()
        try:
            current = connection.execute('SELECT status,error FROM runs WHERE id=?', (self.work.id,)).fetchone()
            self.assertEqual(('running', '服务重启后原节点执行正在对账'), tuple(current))
        finally:
            connection.close()
        remote.recover_once(completed)
        self.assertEqual('closed', self.fixture.ledger.get(self.scope.operation_id)['phase'])
        completed.assert_called_once()
        self.assertIsNone(self.gateway.lease)
        raw = self.work.model_dump()
        raw['id'] = 'fedcba654321'
        raw['worker_env'].update(RUN_ID=raw['id'], QUOTA_SOURCE='run:' + raw['id'] + ':0')
        work = RunWork.model_validate(raw)
        scope = self.scope.model_copy(update={'operation_id': '9' * 32, 'source': work.source})
        connection = self.fixture.fixture.database()
        try:
            with connection:
                connection.execute("INSERT INTO runs(id,account_id,task_id,status,execution_source) VALUES(?,1,9,'running',?)",
                    (work.id, work.source))
        finally:
            connection.close()
        self.sessions.start(RunStart(scope=scope, work=work))
        self.sessions._isolate(scope.operation_id, 'remote_renew_unconfirmed')
        controls = self.peer.calls.count('run-control')
        remote.recover_once(completed)
        self.assertEqual(controls, self.peer.calls.count('run-control'))
        self.assertEqual('reconcile', self.fixture.ledger.get(scope.operation_id)['phase'])
        self.assertIsNotNone(self.gateway.lease)

    def test_failed_start_owner_explicitly_queues_original_scope_even_after_run_becomes_failed(self) -> None:
        """启动所有者失败后单独登记旧scope，失败Run仍可在原节点回连后收口。:return: None。"""
        self.sessions.start(self.request)
        remote = self._register_run()
        with patch.object(remote, '_start', side_effect=ConnectionError('合成启动回执丢失')):
            with self.assertRaises(ConnectionError):
                remote.start(self.work.id, {'id': 1}, self.work.task.model_dump(), self.work.worker_env)
        connection = self.fixture.fixture.database()
        try:
            with connection:
                connection.execute("UPDATE runs SET status='failed' WHERE id=?", (self.work.id,))
        finally:
            connection.close()
        remote.recovery_sources = None
        completed = Mock()
        remote.recover_once(completed)
        completed.assert_called_once()
        self.assertEqual('closed', self.fixture.ledger.get(self.scope.operation_id)['phase'])
        self.assertEqual(1, self.peer.calls.count('run-start'))
        self.assertIsNone(self.gateway.lease)


    def test_failed_heartbeat_join_still_queues_owned_running_scope_for_actual_stop(self) -> None:
        """续约线程等待和隔离落盘均失败时，原所有者登记仍能驱动原作业收口。:return: None。"""
        self.sessions.start(self.request)
        remote = self._register_run()
        with patch.object(self.sessions, '_stop_heartbeat', side_effect=ValueError('合成续约尚未退出')):
            with patch.object(self.sessions, '_isolate', side_effect=ConnectionError('合成隔离落盘暂不可用')):
                with self.assertRaisesRegex(ValueError, '续约'):
                    remote.cleanup('remote-run:' + self.scope.operation_id)
        self.assertEqual('running', self.fixture.ledger.get(self.scope.operation_id)['phase'])
        completed = Mock()
        remote.recover_once(completed)
        completed.assert_called_once()
        self.assertEqual('closed', self.fixture.ledger.get(self.scope.operation_id)['phase'])
        self.assertEqual(1, self.peer.calls.count('run-start'))


class RunnerEntryRoutingTests(unittest.TestCase):
    """原Runner在创建本地目录及挂载之前完成节点路由。"""

    def test_actual_entry_routes_before_central_filesystem_and_preserves_frozen_environment(self) -> None:
        """远程入口只交付原解析环境，原本机准备调用留给本机分支。:return: None。"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = Mock()
            remote.routes.return_value = True
            remote.start.return_value = ('remote-run:' + '1' * 32,) * 2
            runner = main.Runner.__new__(main.Runner)
            runner._quota_mounts = Mock(side_effect=AssertionError('误用本机挂载'))
            task = {'id': 9, 'prompt': '原题\n原补充', 'claude_code_version': '2.1.303',
                'claude_effort_level': 'high', 'timeout_sec': 60, 'capture_permission_mode': 'bypassPermissions',
                'model_override': 'offline-model'}
            account = {'id': 1, 'name': 'synthetic', 'cc2api_account_id': 7}
            with patch.multiple(main, cluster_runner=remote, project_iterations=None, BENCH_DATA=root,
                    HOST_BENCH_DATA=root, _persist_default_claude_settings=Mock(side_effect=AssertionError('误用本机profile'))):
                result = runner.start_run('abcdef123456', account, task)
            self.assertEqual(remote.start.return_value, result)
            environment = remote.start.call_args.args[3]
            work = RunWork(id='abcdef123456', account_id=1, task=RunTask(id=9), worker_env=environment)
            self.assertEqual(task['prompt'], work.worker_env['TASK_PROMPT'])
            self.assertEqual('1', work.worker_env['CC2API_MANAGED_OAUTH'])
            self.assertEqual([], list(root.iterdir()))

    def test_remote_preparation_validation_error_does_not_publish_private_configuration(self) -> None:
        """节点私有投影验证失败只公开固定原因。:return: None。"""
        with self.assertRaises(ValueError) as failure:
            RunWork.model_validate({'private_token': 'synthetic-private-token'})
        remote = Mock(); remote.routes.return_value = True; remote.start.side_effect = failure.exception
        runner = main.Runner.__new__(main.Runner)
        task = {'id': 9, 'prompt': '合成原题', 'claude_code_version': '2.1.303', 'claude_effort_level': 'high',
            'capture_permission_mode': 'bypassPermissions', 'model_override': 'offline-model'}
        with patch.multiple(main, cluster_runner=remote, project_iterations=None):
            with self.assertRaises(main.RuntimeBusy) as public:
                runner.start_run('abcdef123456', {'id': 1, 'name': 'synthetic'}, task)
        self.assertNotIn('synthetic-private-token', str(public.exception))
