"""中央工程路由结合真实SQLite和原租约协调器验证执行归属。"""
from __future__ import annotations

import json
import unittest
from unittest.mock import Mock

from cluster_projects_terminal import ClusterProjectsTerminal
from project_runtime_policy import ProjectRuntimeError
import test_cluster_terminal_sessions as session_fixture


class ClusterProjectsTerminalTests(unittest.TestCase):
    """检验远程操作复用原中央账本，本机接口保持原参数。"""

    def setUp(self) -> None:
        """创建原会话协调器和实际中央归属。:return: None。"""
        fixture = session_fixture.TerminalSessionTests(methodName='runTest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.sessions, self.peer = fixture, fixture.sessions, fixture.peer
        self.local = Mock()
        self.local.namespace = 'projects'
        self.local.runtime = self.sessions.runtime
        self.local.runtime._row = Mock(return_value={'environment_id': fixture.fixture.scope.environment_id, 'generation': 4})
        self.sessions.service.prepare_remote_cli = Mock()
        original_call = self.peer.execution_environment

        def call(container, payload, operation):
            if operation == 'terminal-assets':
                return {'protocol': 1, 'node_key': fixture.fixture.scope.node_key,
                    'terminal': {'digest': payload['digest'], 'state': 'registered'}}
            return original_call(container, payload, operation)

        self.peer.execution_environment = Mock(side_effect=call)
        self.terminal = ClusterProjectsTerminal(self.local, self.sessions, lambda _: 'original-identity')
        self.work = {**fixture.fixture.work.model_dump(exclude={'has_baseline'}), 'baseline_json': None, 'status': 'running'}
        connection = fixture.fixture.fixture.database()
        try:
            self.account = dict(connection.execute('SELECT * FROM accounts WHERE id=1').fetchone())
        finally:
            connection.close()

    def started(self) -> dict:
        """实际完成原协调器认领。:return: 保存执行定位后的原工作。"""
        result = self.terminal.start(self.account, self.work)
        return {**self.work, 'runtime_json': json.dumps(result)}

    def test_remote_start_keeps_node_paths_private_and_duplicate_never_submits_again(self) -> None:
        """启动经过真实账本和租约替身，同来源重试只返回原节点定位。:return: None。"""
        work = self.started()
        info = json.loads(work['runtime_json'])
        self.assertEqual(self.fixture.fixture.scope.source, info['source'])
        self.assertEqual('b' * 32, info['node_key'])
        self.assertNotIn('workspace', info)
        self.assertNotIn('native', info)
        self.assertEqual(info, self.terminal.start(self.account, self.work))
        self.assertEqual(1, self.peer.calls.count('terminal-start'))
        self.local.start.assert_not_called()
        self.local.credentials.assert_called_once_with(self.account)
        self.assertEqual('original-identity', self.sessions.service.prepare_remote_cli.call_args.args[3])

    def test_unknown_start_preserves_original_operation_and_does_not_call_local(self) -> None:
        """节点已提交且响应丢失时重复启动留在原未知操作。:return: None。"""
        self.peer.unknown_start = True
        with self.assertRaises(ConnectionError):
            self.terminal.start(self.account, self.work)
        with self.assertRaises(ProjectRuntimeError):
            self.terminal.start(self.account, self.work)
        self.assertEqual(1, self.peer.calls.count('terminal-start'))
        self.assertEqual(1, len(self.sessions.ledger.active(1)))
        self.local.start.assert_not_called()

    def test_reads_follow_frozen_operation_and_input_is_rejected_after_node_disabled(self) -> None:
        """停用节点后只读沿原节点，新输入遵守中央归属门禁。:return: None。"""
        work = self.started()
        row = self.sessions.ledger.by_source(1, self.fixture.fixture.scope.source)
        node = self.sessions.service.store.get(row['node_id'])
        self.sessions.service.store.set_enabled(node['id'], node['revision'], False)
        self.terminal.observe(work, 17)
        self.assertEqual('terminal-observe', self.peer.calls[-1])
        with self.assertRaises(ValueError):
            self.terminal.send(work, '1' * 32, '原样输入', [], True)
        self.local.observe.assert_not_called()
        altered = json.loads(work['runtime_json'])
        altered['token'] = 'other-token'
        with self.assertRaisesRegex(ValueError, '定位'):
            self.terminal.observe({**work, 'runtime_json': json.dumps(altered)})

    def test_stop_and_historical_usage_keep_original_operation_after_runtime_pointer_cleared(self) -> None:
        """双端收口后清除工作定位仍可读取原会话及抓包。:return: None。"""
        work = self.started()
        self.assertEqual({'stopped': True}, self.terminal.control(work, 'stop'))
        self.terminal.usage({**work, 'runtime_json': None})
        self.assertEqual('terminal-usage', self.peer.calls[-1])
        self.terminal.capture({**work, 'runtime_json': None, 'status': 'paused'}, 'capture_index.json')
        arguments = self.peer.execution_environment.call_args.args
        self.assertEqual('terminal-capture', arguments[2])
        self.assertFalse(arguments[1]['running'])

    def test_input_unknown_raises_and_candidate_snapshot_requires_original_submission_id(self) -> None:
        """未知节点输入进入原中央阻塞，候选不创建无归属的快照操作。:return: None。"""
        work = self.started()
        self.sessions.send = Mock(return_value={'status': 'unknown'})
        with self.assertRaisesRegex(ValueError, '未知'):
            self.terminal.send(work, '1' * 32, '输入', [], True)
        self.sessions.snapshot = Mock(return_value={'schema': 1})
        self.terminal.snapshot(work)
        operation = json.loads(work['runtime_json'])['remote_execution']
        self.sessions.snapshot.assert_called_once_with(operation, operation, None)
        with self.assertRaisesRegex(ValueError, '原提交'):
            self.terminal.snapshot(work, self.fixture.fixture.fixture.path.parent / 'objects')

    def test_local_account_uses_original_terminal_without_remote_preparation(self) -> None:
        """默认本地账号沿原终端，参数保持一致。:return: None。"""
        connection = self.fixture.fixture.fixture.database()
        try:
            with connection:
                connection.execute('UPDATE account_node_assignments SET node_id=1 WHERE account_id=1')
        finally:
            connection.close()
        self.terminal.start(self.account, self.work)
        self.local.start.assert_called_once_with(self.account, self.work)
        self.terminal.snapshot(self.work)
        self.local.snapshot.assert_called_once_with(self.work, None, snapshot_id=None)
        self.sessions.service.prepare_remote_cli.assert_not_called()
