"""验证真实 SQLite 上的整体门禁、部分失败、恢复和独立配置。"""
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_work_control import AccountWorkCoordinator


class AccountWorkControlTests(unittest.TestCase):
    """整体停用保持在途 API 收尾，失败后继续原意图。"""

    def setUp(self):
        """创建隔离数据库和合成网关。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'state.sqlite'
        with self.database() as connection:
            connection.executescript('CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT,enabled INTEGER,deleted_at REAL,cc2api_account_id INTEGER);'
                'CREATE TABLE app_settings(key TEXT PRIMARY KEY,value TEXT,updated_at REAL);'
                "INSERT INTO accounts VALUES(1,'synthetic',1,NULL,7),(2,'independent',1,NULL,NULL);")
        self.gateway_state = {'api_accepting': False, 'work_enabled': True, 'admitted_requests': 1}
        self.gateway = Mock()
        self.gateway._request.side_effect = self.request
        self.identity = threading.Lock()
        self.stop = Mock(side_effect=self.check_stop)
        self.controller = self.build()

    def database(self):
        """返回独立连接。:return: SQLite 连接。"""
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def request(self, method, path, body=None):
        """模拟真实字段的网关控制。:param method: 方法。:param path: 路径。:param body: 增量。:return: 原状态。"""
        self.assertEqual(path, '/admin/accounts/7/work-control')
        if method == 'PUT':
            self.gateway_state.update(body)
        return dict(self.gateway_state)

    def build(self):
        """重建控制器复用原落盘意图。:return: 新协调器。"""
        return AccountWorkCoordinator(self.database, threading.Lock(), lambda _: self.identity,
            self.gateway, self.stop, lambda _: 0)

    def check_stop(self, account_id):
        """停止前门禁已关闭且身份锁可取。:param account_id: 账号。:return: None。"""
        account, _ = self.controller._read(account_id)
        self.assertEqual(account['enabled'], 0)
        self.assertTrue(self.identity.acquire(blocking=False))
        self.identity.release()

    def test_disable_drains_api_and_preserves_api_preference_and_other_account(self):
        """关闭整体保留独立 API 偏好，已有流结束后显示已停用。:return: None。"""
        result = self.controller.change(1, False)
        self.assertEqual(result['phase'], 'draining')
        self.assertFalse(self.gateway_state['work_enabled'])
        self.assertFalse(self.gateway_state['api_accepting'])
        self.assertTrue(self.controller.snapshot(2)['enabled'])
        self.gateway_state['admitted_requests'] = 0
        self.assertEqual(self.controller.snapshot(1)['phase'], 'disabled')
        self.controller.change(1, True)
        self.assertTrue(self.gateway_state['work_enabled'])
        self.assertFalse(self.gateway_state['api_accepting'])

    def test_gateway_failure_still_stops_cli_and_retry_keeps_original_operation(self):
        """网关回执失败仍停止 CLI，重试核对同一操作。:return: None。"""
        self.gateway._request.side_effect = ConnectionError('synthetic-unavailable')
        with self.assertRaises(ConnectionError):
            self.controller.change(1, False)
        self.stop.assert_called_once_with(1)
        pending = self.controller.snapshot(1)
        self.assertFalse(pending['enabled'])
        self.assertEqual(pending['phase'], 'reconcile')
        self.gateway._request.side_effect = self.request
        retried = self.controller.change(1, False)
        self.assertEqual(retried['operation_id'], pending['operation_id'])

    def test_restart_recovers_persisted_intent_and_independent_account_works(self):
        """重启后接续已保存的失败操作，独立账号复用原任务停止。:return: None。"""
        self.stop.side_effect = ValueError('synthetic-stop-unconfirmed')
        with self.assertRaises(ValueError):
            self.controller.change(2, False)
        before = self.controller.snapshot(2)
        self.stop.side_effect = self.check_stop
        self.controller = self.build()
        self.controller.recover()
        after = self.controller.snapshot(2)
        self.assertEqual(after['operation_id'], before['operation_id'])
        self.assertEqual(after['phase'], 'disabled')

    def test_read_is_side_effect_free_and_strict_boolean_is_required(self):
        """读取保持原状态，非法布尔值在写入前拒绝。:return: None。"""
        self.controller.snapshot(1)
        self.stop.assert_not_called()
        with self.assertRaises(ValueError):
            self.controller.change(1, 1)
        with self.database() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM app_settings').fetchone()[0], 0)

    def test_repeated_enable_never_closes_task_gate_or_rewrites_completed_operation(self):
        """重复启用在所有网关观察阶段保持账号准入。:return: None。"""
        self.controller.change(1, False)
        enabled = self.controller.change(1, True)
        self.gateway.reset_mock()
        self.stop.reset_mock()

        def observe(method, path, body=None):
            self.assertEqual(self.controller._read(1)[0]['enabled'], 1)
            return self.request(method, path, body)

        self.gateway._request.side_effect = observe
        repeated = self.controller.change(1, True)
        self.assertEqual(repeated['operation_id'], enabled['operation_id'])
        self.assertTrue(repeated['enabled'])
        self.assertTrue(all(call.args[0] == 'GET' for call in self.gateway._request.call_args_list))
        self.stop.assert_not_called()

    def test_repeated_enable_observation_failure_preserves_existing_admission(self):
        """幂等启用的读取失败保留当前运行准入。:return: None。"""
        self.gateway._request.side_effect = ConnectionError('synthetic-unavailable')
        with self.assertRaises(ConnectionError):
            self.controller.change(1, True)
        account, operation = self.controller._read(1)
        self.assertEqual(account['enabled'], 1)
        self.assertIsNone(operation)

    def test_gateway_entry_resolves_original_binding_and_rejects_missing_target(self):
        """网关入口按原关联控制任务账号，缺少目标在写入前拒绝。:return: None。"""
        import main

        request = main.Request({'type': 'http', 'method': 'PUT'})
        with patch.object(main, 'get_db', self.database), patch.object(main, '_account_work_controller', return_value=self.controller):
            with self.assertRaises(main.HTTPException) as error:
                main.gateway_account_work(7, request)
            self.assertEqual(error.exception.status_code, 422)
            self.stop.assert_not_called()
            result = main.gateway_account_work(7, request, main.AccountWorkIn(enabled=False))
            self.assertFalse(result['enabled'])
            self.assertEqual(result['phase'], 'draining')
            self.stop.assert_called_once_with(1)

    def test_unknown_execution_observation_is_visible_and_never_reported_as_stopped(self):
        """执行账本读取失败保留未知占用，公开固定待核对文案。:return: None。"""
        self.controller.change(2, False)
        self.controller.activity = Mock(side_effect=ValueError('synthetic-private-record'))
        snapshot = self.controller.snapshot(2)
        self.assertEqual(snapshot['phase'], 'reconcile')
        self.assertIsNone(snapshot['active_work'])
        self.assertEqual(snapshot['message'], '账号执行占用待核对')

    def test_stop_fanout_keeps_schedules_and_reaches_other_work_after_failure(self):
        """单一执行器失败仍收口其它工作，仅控制指定账号。:return: None。"""
        import main

        with self.database() as connection:
            connection.executescript("CREATE TABLE runs(id TEXT,account_id INTEGER,status TEXT);"
                "INSERT INTO runs VALUES('own-run',1,'running'),('other-run',2,'running');")
        projects, warmup, remote = Mock(), Mock(), Mock()
        projects.pause.side_effect = ValueError('synthetic-stop-unconfirmed')
        remote.ledger.active.return_value = [{'operation_id': 'frozen-operation'}]
        continuation = Mock()
        continuation._lock = threading.Lock()
        continuation.sessions = {'own-session': SimpleNamespace(account_id=1), 'other-session': SimpleNamespace(account_id=2)}
        with patch.multiple(main, get_db=self.database, projects_service=projects, warmup_pi_service=warmup,
                project_iterations=None, continue_manager=continuation, cluster_terminal_sessions=remote, cluster_runner=None), \
                patch.object(main, '_stop_project_run') as stop_run:
            with self.assertRaises(main.RuntimeBusy):
                main._stop_account_work(1)
            projects.pause.assert_called_once_with(1, disable_schedule=False)
            warmup.pause.assert_called_once_with(1, disable_schedule=False)
            stop_run.assert_called_once_with('own-run', recover_stopping=True)
            continuation.cleanup.assert_called_once_with('own-session')
            remote.stop.assert_called_once_with('frozen-operation')
