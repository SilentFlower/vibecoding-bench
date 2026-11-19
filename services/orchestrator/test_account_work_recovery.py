"""验证停止失败后的原代次重试、并发单执行和环境对账边界。"""
import threading
import unittest
from unittest.mock import Mock, patch

import main
import test_quota as quota_fixtures
from account_work_control import AccountWorkCoordinator


class AccountRunStopRecoveryTests(unittest.TestCase):
    """使用真实数据库和原停止入口验证整体收口。"""

    setUp = quota_fixtures.QuotaGuardTests.setUp
    _run = quota_fixtures.QuotaGuardTests._run

    def prepare(self, status='running', *, environment=False):
        """保存原运行身份。:param status: 原状态。:param environment: 是否保存环境。:return: None。"""
        self._run('recoverable', status=status)
        connection = main.get_db()
        try:
            with connection:
                connection.execute('UPDATE accounts SET enabled=0 WHERE id=1')
                connection.execute("UPDATE runs SET worker_container='original-worker',sidecar_container='original-sidecar' WHERE id='recoverable'")
                if environment:
                    connection.execute("INSERT INTO account_environments(environment_id,name,account_id,fingerprint_json,generation,state) VALUES('original-env','fixture',1,'{}',7,'cli_reconcile')")
                    connection.execute("UPDATE runs SET environment_id='original-env',environment_generation=7 WHERE id='recoverable'")
        finally:
            connection.close()

    def test_failed_cleanup_retries_original_operation_and_preserves_stop_intent(self):
        """首次清理失败后，整体重试实际清理并释放原占用。:return: None。"""
        self.prepare()
        self.runner.cleanup.side_effect = [RuntimeError('synthetic-unavailable'), None]
        with patch.multiple(main, projects_service=None, warmup_pi_service=None, project_iterations=None,
                cluster_runner=None, cluster_terminal_sessions=None, account_runtime=None):
            control = AccountWorkCoordinator(main.get_db, main._db_lock, main._oauth_owner_lock,
                Mock(), main._stop_account_work, main._account_work_activity)
            with self.assertRaises(main.RuntimeBusy):
                control.change(1, False)
            first = control.snapshot(1)
            stopped_at = main.get_run('recoverable')['stop_requested_at']
            self.assertEqual(first['phase'], 'reconcile')
            self.assertEqual(main.get_run('recoverable')['status'], 'stopping')
            second = control.change(1, False)
            self.assertEqual(second['operation_id'], first['operation_id'])
            self.assertEqual(second['phase'], 'disabled')
            self.assertEqual(main.get_run('recoverable')['status'], 'stopped')
            self.assertEqual(main.get_run('recoverable')['stop_requested_at'], stopped_at)
            self.assertEqual(self.runner.cleanup.call_count, 2)

    def test_concurrent_stops_only_cleanup_one_frozen_run(self):
        """同一运行的重复停止串行核对，实际清理只执行一次。:return: None。"""
        self.prepare()
        entered, release, second_entered = threading.Event(), threading.Event(), threading.Event()
        errors = []

        def cleanup(*_):
            entered.set()
            self.assertTrue(release.wait(2))

        def stop(second=False):
            if second:
                second_entered.set()
            try:
                main._stop_project_run('recoverable', recover_stopping=True)
            except Exception as error:
                errors.append(error)

        self.runner.cleanup.side_effect = cleanup
        with patch.multiple(main, account_runtime=None, cluster_runner=None):
            first = threading.Thread(target=stop)
            second = threading.Thread(target=stop, args=(True,))
            first.start()
            self.assertTrue(entered.wait(1))
            second.start()
            self.assertTrue(second_entered.wait(1))
            self.assertEqual(self.runner.cleanup.call_count, 1)
            release.set()
            first.join(2)
            second.join(2)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.runner.cleanup.call_count, 1)

    def test_stale_quota_attempt_never_cleans_new_execution(self):
        """停止等待期间换代时，原回执不能清理新执行。:return: None。"""
        self.prepare('stopping')

        def change_attempt(*_):
            connection = main.get_db()
            try:
                with connection:
                    connection.execute("UPDATE runs SET quota_attempt=1,status='running',worker_container='new-worker' WHERE id='recoverable'")
            finally:
                connection.close()

        self.runner.persist_worker_profile.side_effect = change_attempt
        with self.assertRaises(main.HTTPException) as error:
            main._stop_project_run('recoverable', recover_stopping=True)
        self.assertEqual(error.exception.status_code, 409)
        self.runner.cleanup.assert_not_called()
        self.assertEqual(main.get_run('recoverable')['worker_container'], 'new-worker')

    def test_isolated_local_execution_requires_original_environment_reconciliation(self):
        """空内存作业不作为停止证明，实际环境对账失败保持原停止阶段。:return: None。"""
        self.prepare('stopping', environment=True)
        runtime = Mock()
        runtime.environment_lock.return_value = threading.RLock()
        runtime.maintenance.side_effect = [ValueError('API still active'), None]
        with patch.multiple(main, account_runtime=runtime, cluster_runner=None):
            with self.assertRaises(ValueError):
                main._stop_project_run('recoverable', recover_stopping=True)
            self.assertEqual(main.get_run('recoverable')['status'], 'stopping')
            main._stop_project_run('recoverable', recover_stopping=True)
            self.assertEqual(main.get_run('recoverable')['status'], 'stopped')
        self.assertEqual(runtime.maintenance.call_count, 2)
        runtime.maintenance.assert_called_with('original-env', 'reconcile')

    def test_changed_environment_generation_keeps_original_stop_unconfirmed(self):
        """环境换代后拒绝对新代次执行原运行的维护收口。:return: None。"""
        self.prepare('stopping', environment=True)
        connection = main.get_db()
        try:
            with connection:
                connection.execute("UPDATE account_environments SET generation=8 WHERE account_id=1")
        finally:
            connection.close()
        runtime = Mock()
        runtime.environment_lock.return_value = threading.RLock()
        with patch.multiple(main, account_runtime=runtime, cluster_runner=None):
            with self.assertRaises(main.RuntimeBusy):
                main._stop_project_run('recoverable', recover_stopping=True)
        runtime.maintenance.assert_not_called()
        self.assertEqual(main.get_run('recoverable')['status'], 'stopping')
