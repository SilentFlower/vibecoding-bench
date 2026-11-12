"""验证自设额度阈值允许当前整轮完成，下一轮继续受门禁约束。"""

import threading
import time
import unittest
from unittest.mock import Mock, patch

import main
import test_quota
from account_runtime import AccountRuntime
from test_quota import quota_headers


class QuotaCompletionTests(unittest.TestCase):
    """通过真实调度器、SQLite 和额度协议验证任务轮次边界。"""

    _run = test_quota.QuotaGuardTests._run
    _state = test_quota.QuotaGuardTests._state
    _expire = test_quota.QuotaGuardTests._expire

    def setUp(self) -> None:
        """建立隔离账号及 v3 执行替身，禁止真实上游调用。@return None。"""
        test_quota.QuotaGuardTests.setUp(self)
        with patch.dict("os.environ", {"V3_DEPLOYMENT_ID": "completion", "V3_ACCOUNT_IMAGE": "synthetic",
                "V3_NETWORK": "synthetic"}):
            runtime = AccountRuntime(Mock(), self.base, self.base, main.get_db, Mock(), Mock())
            runtime.heartbeat_pool.shutdown()
        self.runtime = Mock()
        self.runtime.run_artifact_path.side_effect = lambda rid, name: self.base / rid / name
        patcher = patch.object(main, "account_runtime", self.runtime)
        patcher.start()
        self.addCleanup(patcher.stop)
        with main.get_db() as connection:
            connection.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=60,"
                               "warmup_quota_7d_limit_percent=80 WHERE id=1")

    def _observe(self, five=55, seven=40) -> None:
        """合并被动观察；参数为两个窗口的已用百分比。@return None。"""
        headers = quota_headers(time.time(), five=600, seven=3600)
        headers["anthropic-ratelimit-unified-5h-utilization"] = str(five / 100)
        headers["anthropic-ratelimit-unified-7d-utilization"] = str(seven / 100)
        self._state(headers, status=200)

    def _finish(self, kind="normal", five=68, seven=40, batch=False, lower=False, exit_code=0) -> dict:
        """在真实执行中改变用量或配置，返回本轮实际终态。

        :param kind: normal 或 warmup。
        :param five: 执行期间的 5h 百分比。
        :param seven: 执行期间的 7d 百分比。
        :param batch: 是否使用批次 item。
        :param lower: 是否在运行中降低阈值。
        :param exit_code: 模拟实际进程退出码。
        :return: 原 run 的公开状态。
        """
        task = self._run(kind=kind, batch=batch)
        self._observe()

        def wait(worker_id):
            """模拟忙碌期间收到正式观察，确认未发生提前停止。"""
            self._observe(five, seven)
            if lower:
                with main.get_db() as connection:
                    connection.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=50 WHERE id=1")
            run = main.get_run("original")
            self.assertEqual("running", run["status"])
            self.assertIsNone(run["stop_requested_at"])
            self.runner.cleanup.assert_not_called()
            return exit_code

        self.runner.wait_worker.side_effect = wait
        with patch.object(main, "_sync_bound_account_credentials_locked"):
            self.scheduler._execute("original", self.account, task)
        return main.get_run("original")

    def test_equal_5h_threshold_finishes_current_and_blocks_next(self) -> None:
        """等值命中保留成功终态，但下一条普通任务等待。@return None。"""
        result = self._finish(five=60)
        self.assertEqual("success", result["status"])
        self.assertEqual(0, result["exit_code"])
        self.assertIsNone(result["stop_requested_at"])
        task = self._run(rid="next")
        self.scheduler._execute("next", self.account, task)
        self.assertEqual("quota_wait", main.get_run("next")["status"])
        self.runner.start_run.assert_called_once()

    def test_crossed_5h_threshold_finishes_original(self) -> None:
        """一次响应跨过阈值不改 stopped，实际用量仍被保留。@return None。"""
        result = self._finish(five=68)
        self.assertEqual("success", result["status"])
        self.assertIsNone(result["error"])
        self.assertEqual(68, self.guard.snapshot(self.account)["windows"]["five_hour"]["utilization"])
        self.assertTrue(self.guard.policy_snapshot(self.account, "normal")["blocked"])

    def test_7d_warmup_finishes_and_preserves_next_interval(self) -> None:
        """养号命中 7d 后完成本轮，下轮沿原间隔并受阈值约束。@return None。"""
        result = self._finish(kind="warmup", seven=81)
        self.assertEqual("success", result["status"])
        warmup = main.WarmupScheduler(self.scheduler)
        warmup.handle_run_terminal("original", 7)
        with main.get_db() as connection:
            account = connection.execute("SELECT warmup_last_status,warmup_next_run_at,warmup_auth_failures "
                                         "FROM accounts WHERE id=1").fetchone()
        self.assertEqual("success", account[0])
        self.assertGreater(account[1], time.time())
        self.assertEqual(0, account[2])
        self.assertTrue(self.guard.policy_snapshot(self.account, "warmup")["blocked"])

    def test_lowering_threshold_only_blocks_next_round(self) -> None:
        """运行中降低阈值不打断当前整轮。@return None。"""
        self.assertEqual("success", self._finish(five=55, lower=True)["status"])
        self.assertTrue(self.guard.policy_snapshot(self.account, "normal")["blocked"])

    def test_batch_preserves_completed_item_and_original_delay(self) -> None:
        """批次等待不重做成功项，重置后仍保留原投放时间。@return None。"""
        self.assertEqual("success", self._finish(batch=True)["status"])
        deadline = time.time() + 1200
        with main.get_db() as connection:
            connection.execute("UPDATE task_batches SET next_launch_at=? WHERE id=1", (deadline,))
            connection.execute("INSERT INTO task_batch_items(batch_id,topic_id,prompt,status) "
                               "VALUES(1,1,'下一题','pending')")
        with patch.object(self.scheduler, "_sleep_batch_delay", return_value=True):
            self.scheduler._execute_batch(1)
        with main.get_db() as connection:
            self.assertEqual("success", connection.execute("SELECT status FROM task_batch_items "
                             "WHERE run_id='original'").fetchone()[0])
            self.assertEqual(("quota_wait", deadline), tuple(connection.execute("SELECT status,next_launch_at "
                             "FROM task_batches WHERE id=1").fetchone()))
        self._expire()
        with patch.object(self.scheduler, "submit_batch") as submit:
            self.guard._resume_account(self.account)
        submit.assert_called_once_with(1)
        with main.get_db() as connection:
            self.assertEqual(deadline, connection.execute("SELECT next_launch_at FROM task_batches WHERE id=1").fetchone()[0])

    def test_high_observation_does_not_mask_timeout(self) -> None:
        """超时按真实退出码记录，不伪造百分比停止。@return None。"""
        result = self._finish(exit_code=124)
        self.assertEqual("timeout", result["status"])
        self.assertIsNone(result["stop_requested_at"])

    def test_auth_failure_remains_permanent(self) -> None:
        """真实认证失败保留 auth_failed 和永久门禁。@return None。"""
        self.runner.read_worker_status.return_value = {"status": "auth_failed", "error": "invalid_grant"}
        result = self._finish(exit_code=42)
        self.assertEqual("auth_failed", result["status"])
        self.assertEqual("invalid_grant", self.guard.snapshot(self.account)["account_error"])

    def test_user_stop_keeps_reason(self) -> None:
        """用户停止仍可中断当前轮次，不因高用量丢失原因。@return None。"""
        task = self._run()
        self._observe()

        def wait(worker_id):
            """模拟用户在忙碌期间提交停止意图。"""
            self._observe(five=68)
            with main.get_db() as connection:
                connection.execute("UPDATE runs SET status='stopping',stop_requested_at=?,error='用户停止' "
                                   "WHERE id='original'", (time.time(),))
            return 143

        self.runner.wait_worker.side_effect = wait
        self.scheduler._execute("original", self.account, task)
        result = main.get_run("original")
        self.assertEqual("stopped", result["status"])
        self.assertEqual("用户停止", result["error"])

    def test_historical_stopping_intent_finishes_without_revival(self) -> None:
        """升级保留旧停止意图，不能自动复活旧强停任务。@return None。"""
        self._run(status="stopping")
        self._observe(five=68)
        with main.get_db() as connection:
            connection.execute("UPDATE runs SET stop_requested_at=?,error='额度阈值强制中断：历史原因' "
                               "WHERE id='original'", (time.time(),))
        self.guard.recover()
        self.guard._resume_account(self.account)
        self.assertEqual("stopped", main.get_run("original")["status"])
        self.runner.start_run.assert_not_called()


class AccountExecWaitTests(unittest.TestCase):
    """验证等待当前 exec 的实际结果，不因用量或容器常驻而提前结束。"""

    def test_waits_for_original_exec_and_keeps_actual_exit_code(self) -> None:
        """忙碌后退出保留真实退出码，不等待整个常驻容器。@return None。"""
        runtime = AccountRuntime.__new__(AccountRuntime)
        runtime.client = Mock()
        runtime.lock = threading.RLock()
        job = {"token": "worker:current", "exec": "exec", "row": {
            "environment_id": "environment", "container_id": "worker"}}
        runtime.jobs = {"environment": job}
        runtime.client.api.exec_inspect.side_effect = [{"Running": True}, {"Running": False, "ExitCode": 143}]
        with patch("account_runtime.time.sleep"):
            self.assertEqual(143, runtime.wait_worker("worker:current"))
        runtime.client.api.exec_inspect.assert_called_with("exec")


if __name__ == "__main__":
    unittest.main()
