"""具体续聊的原Scope、一次性PTY、输入收据及真实私有WS回归。"""
from __future__ import annotations

import base64
import hashlib
import json
import select
import socket
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import FastAPI, WebSocket
from uvicorn import Config, Server

import main
from cluster_continue import NodeContinues, PtyInput
from cluster_continue_contract import ContinueStart, ContinueTask, ContinueWork
from cluster_continue_runner import ClusterContinues, RemoteContinuePty
from cluster_execution_grants import ExecutionGrant, ExecutionGrants, ExecutionLeaseProof
from cluster_quota import quota_scope_path
from cluster_runtime_host import NodeRuntimeHost
from cluster_terminal import TerminalInputQuery
from cluster_terminal_sessions import TerminalSessions
from run_artifacts import ordinary_run_alias
from runtime_files import atomic_json
from test_cluster_runtime_host import _HostedRuntime
from test_cluster_terminal_sessions import _Gateway, _Peer
import test_cluster_execution as execution_fixture
import test_cluster_execution_store as store_fixture


def continued_work() -> ContinueWork:
    """冻结原Run、会话及续聊代次。:return: 原具体工作。"""
    return ContinueWork(id='abcdef123456', account_id=1, task=ContinueTask(id=9), sid='987654abcdef', generation=0,
        session_id='original-session', version='2.1.303', permission_mode='bypassPermissions', model='offline-model')


class NodeContinueTests(unittest.TestCase):
    """实际SQLite、root文件、证明与socketpair，原CLI准备使用可观察替身。"""

    def setUp(self) -> None:
        """建立原账号与仍有效的有限许可。:return: None。"""
        fixture = execution_fixture.NodeExecutionTests(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.executor, self.now = fixture, fixture.executor, int(time.time())
        self.host = NodeRuntimeHost(self.executor, runtime_factory=_HostedRuntime)
        self.addCleanup(self.host.close)
        self.grants = ExecutionGrants(fixture.root, fixture.node_key, 'synthetic', self.executor.database, lambda: self.now)
        self.host.attach_grants(self.grants)
        self.executor.prepare(fixture.request)
        self.work = continued_work()
        grant = ExecutionGrant(operation_id='d' * 32, node_key=fixture.node_key, account_id=1, gateway_account_id=7,
            environment_id='e' * 32, assignment_revision=1, generation=1, source=self.work.source, role='cli',
            not_after=self.now + 30, lease=ExecutionLeaseProof(owner=self.work.source, generation='original-lease',
                expires_at=self.now + 30, exclusive=False, shared_cli=False))
        self.scope = grant.scope(); self.grants.create(grant)
        atomic_json(quota_scope_path(fixture.root, self.scope), {'scope': self.scope.model_dump(),
            'state': {'identity': 'synthetic-quota', 'remote_cli': {'source': self.scope.source, 'sample_required': False}}})
        session = fixture.root / 'environments' / self.scope.environment_id / 'home/.claude/projects' / (
            '/home/node/projects/' + ordinary_run_alias(self.scope.environment_id, self.work.id)).replace('/', '-') / (self.work.session_id + '.jsonl')
        session.parent.mkdir(parents=True); session.write_text('{"type":"user"}\n')
        runtime = self.host.runtime
        runtime.project_iterations = None
        runtime.begin_continue = Mock(return_value=('original-token', 'original-token'))
        runtime.environment_lock = Mock(return_value=threading.RLock())
        self.job = {'token': 'original-token', 'source': self.scope.source,
            'row': {'environment_id': self.scope.environment_id, 'generation': 1}, 'account': {'id': 1, 'cc2api_account_id': 7}}
        runtime.job_for_container = Mock(return_value=self.job)
        runtime.authorize_input = Mock(side_effect=lambda job: self.grants.authorize(self.scope))
        self.actor = NodeContinues(self.executor, self.host, self.grants)
        self.addCleanup(self.actor.close)
        self.request = ContinueStart(scope=self.scope, work=self.work)

    def _open(self):
        self.assertEqual('ready', self.actor.start(self.request)['phase'])
        raw, peer = socket.socketpair(); raw.setblocking(False); peer.settimeout(1)
        self.addCleanup(peer.close)
        with patch('cluster_continue.open_continue_pty', return_value=('actual-exec', raw)):
            self.actor.open_pty(self.scope)
        return raw, peer

    def test_prepare_and_pty_start_are_once_and_bind_original_run_and_session(self):
        """重复准备只查原收据，重复PTY连接拒绝创建第二个原生会话。:return: None。"""
        raw, peer = self._open()
        self.assertEqual('ready', self.actor.start(self.request)['phase'])
        self.host.runtime.begin_continue.assert_called_once()
        arguments = self.host.runtime.begin_continue.call_args.args
        self.assertEqual(self.work.run(), arguments[1]); self.assertEqual(self.work.sid, arguments[2])
        with patch('cluster_continue.open_continue_pty', side_effect=AssertionError('重复启动')):
            with self.assertRaisesRegex(ValueError, '已经登记'):
                self.actor.open_pty(self.scope)
        self.assertEqual('ready', self.actor.get(self.scope)['phase'])

    def test_input_is_exactly_once_expired_is_not_sent_and_partial_remains_unknown(self):
        """真实字节只进入原socket一次，过期拒绝，部分发送跨actor保持未知。:return: None。"""
        raw, peer = self._open()
        data = '原继续内容\r'.encode()
        request = PtyInput(operation_id='1' * 32, data=base64.b64encode(data).decode())
        receipt = self.actor.send_input(self.scope, request)
        self.assertEqual('sent', receipt['status']); self.assertEqual(data, peer.recv(4096))
        self.assertEqual(receipt, self.actor.send_input(self.scope, request))
        self.assertFalse(select.select([peer], [], [], 0.05)[0])
        with self.assertRaisesRegex(ValueError, '已变化'):
            self.actor.send_input(self.scope, request.model_copy(update={'data': base64.b64encode(b'changed').decode()}))
        raw.close()
        self.actor.ptys[self.scope.operation_id]['raw'] = Mock(send=Mock(return_value=1))
        partial = request.model_copy(update={'operation_id': '2' * 32})
        self.assertEqual('unknown', self.actor.send_input(self.scope, partial)['status'])
        recovered = NodeContinues(self.executor, self.host, self.grants)
        self.assertEqual('unknown', recovered.input_receipt(TerminalInputQuery(scope=self.scope, operation_id='2' * 32))['status'])
        with self.assertRaisesRegex(ValueError, '等待核对'):
            self.actor.send_input(self.scope, request.model_copy(update={'operation_id': '3' * 32}))

    def test_expired_proof_preserves_output_and_rejects_input(self):
        """原证明截止后输出仍可观察，后续实际输入明确not_sent。:return: None。"""
        raw, peer = self._open()
        self.now += 31
        peer.sendall(b'original-output')
        self.assertEqual(b'original-output', raw.recv(4096))
        receipt = self.actor.send_input(self.scope, PtyInput(operation_id='1' * 32, data=base64.b64encode(b'input').decode()))
        self.assertEqual('not_sent', receipt['status'])
        self.assertFalse(select.select([peer], [], [], 0.05)[0])

    def test_real_private_websocket_preserves_bytes_and_lost_ack_queries_original_receipt(self):
        """真实UDS/WS与本地输出socket桥保持原字节，丢ACK只查原收据。:return: None。"""
        self.assertEqual('ready', self.actor.start(self.request)['phase'])
        raw, peer = socket.socketpair(); raw.setblocking(False); peer.settimeout(2)
        self.addCleanup(peer.close)
        app = FastAPI()
        drop = threading.Event(); drop.set()

        @app.websocket('/continue-pty')
        async def endpoint(websocket: WebSocket):
            """连接本次冻结actor，首个输入ACK故意丢弃。:param websocket: 私有连接。:return: None。"""
            await websocket.accept()
            scope = json.loads(await websocket.receive_text())
            self.assertEqual(self.scope.model_dump(), scope)
            original = websocket.send_json

            async def send_json(value):
                if value.get('type') == 'input_ack' and drop.is_set():
                    drop.clear(); return
                await original(value)

            websocket.send_json = send_json
            await self.actor.serve(websocket, self.scope)

        path = self.fixture.root / 'private-pty.sock'
        server = Server(Config(app, uds=str(path), log_level='critical', access_log=False, loop='asyncio'))
        thread = threading.Thread(target=server.run, daemon=True); thread.start()
        deadline = time.monotonic() + 5
        while not server.started:
            self.assertLess(time.monotonic(), deadline); time.sleep(0.01)
        private = self.fixture.root / 'client-private'; private.mkdir(mode=0o700)
        (private / 'execution-token').write_text('a' * 64); (private / 'execution-token').chmod(0o600)
        owner = Mock()
        owner.sessions.service.connection.return_value = SimpleNamespace(private=private, pty_socket=lambda: path)
        owner.sessions._call.side_effect = lambda row, operation, payload: self.actor.input_receipt(TerminalInputQuery.model_validate(payload))
        row = {'node_id': 1, 'operation_id': self.scope.operation_id, 'record': {'scope': self.scope.model_dump()}}
        bridge = None
        try:
            with patch('cluster_continue.open_continue_pty', return_value=('actual-exec', raw)):
                bridge = RemoteContinuePty(owner, row)
            peer.sendall('原PTY输出'.encode())
            self.assertTrue(select.select([bridge], [], [], 2)[0])
            self.assertEqual('原PTY输出'.encode(), bridge.recv(4096))
            data = '唯一输入\r'.encode()
            with patch('cluster_continue_runner.PTY_ACK_TIMEOUT', 0.1):
                self.assertEqual(len(data), bridge.send(data))
            self.assertEqual(data, peer.recv(4096))
            owner.sessions._call.assert_called_once()
            self.assertEqual('continue-input', owner.sessions._call.call_args.args[1])
            owner.sessions._isolate.assert_not_called()
        finally:
            if bridge is not None: bridge.close()
            server.should_exit = True; thread.join(5)
            self.assertFalse(thread.is_alive())


class _ContinuePeer(_Peer):
    """复用真实中央租约回执替身，保留具体续聊操作名称。"""

    def execution_environment(self, container, payload, operation):
        """将原续聊动作交给原固定接口。:param container: 原节点。:param payload: 原输入。:param operation: 原动作。:return: 原回执。"""
        if operation.startswith('continue-'):
            try:
                value = super().execution_environment(container, payload, 'terminal-' + operation.removeprefix('continue-'))
            finally:
                self.calls[-1] = operation
            value['continue'] = value.pop('terminal')
            return value
        return super().execution_environment(container, payload, operation)


class CentralContinueTests(unittest.TestCase):
    """原中央许可、Scope分类和停止释放顺序保持可核对。"""

    def test_original_nonshared_lease_and_main_owner_callback_keep_continue_source(self):
        """真实SQLite登记具体续聊，额度回调使用原owner锁及普通交互模式。:return: None。"""
        fixture = store_fixture.NodeExecutionStoreTests(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        work, peer = continued_work(), _ContinuePeer()
        scope = fixture.scope.model_copy(update={'role': 'cli', 'source': work.source})
        connection = fixture.fixture.database()
        try:
            with connection:
                connection.execute("INSERT INTO runs(id,account_id,task_id,status) VALUES(?,1,9,'success')", (work.id,))
        finally: connection.close()
        manager = main.ContinueManager(Mock()); manager._run_locks[work.id] = work.sid
        guard = Mock(); guard.admit.return_value = True
        service = SimpleNamespace(store=fixture.fixture.store, connection=lambda node: peer)
        sessions = TerminalSessions(fixture.ledger, service, SimpleNamespace(deployment='synthetic'), _Gateway(),
            Mock(), Mock(), run_quota_admit=main._remote_execution_quota_admit_locked)
        self.addCleanup(sessions.close)
        with patch.multiple(main, get_db=fixture.fixture.database, quota_guard=guard, continue_manager=manager,
                credential_ownership=None, _quota_identity=lambda _: 'quota-synthetic'):
            with main._oauth_owner_lock('synthetic'):
                row = sessions.start(ContinueStart(scope=scope, work=work))
        self.assertEqual('running', row['phase'])
        self.assertFalse(row['record']['lease']['shared_cli'])
        self.assertIsNone(guard.admit.call_args.kwargs['workload'])
        self.assertIn('continue-start', peer.calls)
        self.assertEqual('closed', sessions.stop(scope.operation_id)['phase'])
        self.assertIn('continue-control', peer.calls)

    def test_failed_stop_keeps_original_manager_session_until_actual_release(self):
        """停止未知时保留原sid/定位和重试入口，确认后才解除运行占用。:return: None。"""
        runner = Mock(); runner.cleanup.side_effect = ValueError('合成原节点未确认停止')
        manager = main.ContinueManager(runner)
        session = main.ContinueSession('abcdef123456', '123456abcdef', 1, 'remote-continue:' + '1' * 32,
            'remote-continue:' + '1' * 32, 'original-session', 'bypassPermissions')
        manager.sessions[session.sid] = session; manager._run_locks[session.run_id] = session.sid
        remote = Mock(); remote.handles.return_value = True
        with patch.multiple(main, cluster_continues=remote, account_runtime=object()):
            with self.assertRaises(ValueError): manager.cleanup(session.sid)
            self.assertIs(session, manager.get(session.sid)); self.assertEqual('reconcile', session.status)
            self.assertEqual(session.sid, manager._run_locks[session.run_id])
            runner.cleanup.side_effect = None
            manager.cleanup(session.sid)
        self.assertIsNone(manager.get(session.sid)); self.assertNotIn(session.run_id, manager._run_locks)

    def test_public_continue_errors_redact_private_validation_and_remote_sdk_details(self):
        """实际HTTP准备入口隐藏Pydantic投影与远程SDK私有异常内容。:return: None。"""
        with self.assertRaises(ValueError) as failure:
            ContinueWork.model_validate({'private_token': 'synthetic-private-token'})
        run = {'id': 'abcdef123456', 'account_id': 1, 'run_kind': 'normal', 'status': 'success'}
        account = {'id': 1, 'name': 'synthetic', 'enabled': True}
        for error, code in ((failure.exception, 409), (RuntimeError('synthetic-private-token'), 503)):
            connection, manager, remote = Mock(), Mock(), Mock()
            connection.execute.return_value.fetchone.side_effect = [run, account, account]
            manager.start.side_effect = error; remote.routes.return_value = True
            with patch.multiple(main, get_db=Mock(return_value=connection), continue_manager=manager, cluster_continues=remote,
                    _ensure_run_claude_code_version=Mock(), _ensure_run_claude_effort_level=Mock(),
                    _account_run_window=Mock(return_value={'allowed': True})):
                with self.assertRaises(main.HTTPException) as public:
                    main.continue_run_start(run['id'])
            self.assertEqual(code, public.exception.status_code)
            self.assertNotIn('synthetic-private-token', public.exception.detail)
