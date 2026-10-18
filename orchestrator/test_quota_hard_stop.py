"""验证 v3 运行中阈值终止、持久终态与下一题调度；不访问真实上游。"""

import threading
import time
import unittest
from unittest.mock import Mock, patch

import main
import test_quota
from account_runtime import AccountRuntime
from test_quota import quota_headers


class QuotaHardStopTests(unittest.TestCase):
    """使用真实 SQLite 和额度合并验证当前执行的强制中断。"""

    _run = test_quota.QuotaGuardTests._run
    _state = test_quota.QuotaGuardTests._state
    _expire = test_quota.QuotaGuardTests._expire

    def setUp(self) -> None:
        """建立独立账号和 v3 执行替身，禁止自动额度网络查询。@return None。"""
        test_quota.QuotaGuardTests.setUp(self)
        with patch.dict("os.environ", {"V3_DEPLOYMENT_ID": "hard-stop", "V3_ACCOUNT_IMAGE": "synthetic",
                "V3_NETWORK": "synthetic"}):
            schema = AccountRuntime(Mock(), self.base, self.base, main.get_db, Mock(), Mock())
            schema.heartbeat_pool.shutdown()
        self.runtime = Mock()
        self.runtime.job_for_container.return_value = {
            "token": "worker:current", "run_id": "original", "source": "run:original:0",
            "row": {"account_id": 1, "environment_id": "environment", "generation": 7},
        }
        self.runtime.run_artifact_path.side_effect = lambda rid, name: self.base / rid / name
        patcher = patch.object(main, "account_runtime", self.runtime)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runner.read_worker_status.return_value = {}
        self.runner.start_run.return_value = ("sidecar", "worker:current")
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=60,"
                               "warmup_quota_7d_limit_percent=80 WHERE id=1")
        connection.close()

    def _running(self, kind="normal", batch=True) -> dict:
        """固化当前执行归属；参数为种类及批次标记，返回原任务。"""
        task = self._run(kind=kind, batch=batch, status="running")
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE runs SET worker_container='worker:current',"
                "sidecar_container='sidecar',environment_id='environment',environment_generation=7,"
                "execution_source='run:original:0',quota_identity=? WHERE id='original'",
                (main._quota_identity(self.account),))
        connection.close()
        return task

    def _observe(self, five=60, seven=40, delay=600) -> None:
        """合并真实协议形状的额度；参数为已用百分比和重置延迟。@return None。"""
        headers = quota_headers(time.time(), five=delay, seven=3600)
        headers["anthropic-ratelimit-unified-5h-utilization"] = str(five / 100)
        headers["anthropic-ratelimit-unified-7d-utilization"] = str(seven / 100)
        self._state(headers, status=200)

    def _enforce(self) -> None:
        """调用正在等待原进程的阈值检查。@return None。"""
        self.scheduler._enforce_running_quota("original", self.account, 0, "worker:current")

    def test_equal_threshold_stops_original_without_quota_resume(self) -> None:
        """等值命中永久结束本轮，重置只恢复下一题且保留原间隔。@return None。"""
        self._running()
        self._observe()
        deadline = time.time() + 1200
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE task_batches SET next_launch_at=? WHERE id=1", (deadline,))
            connection.execute("INSERT INTO task_batch_items(batch_id,topic_id,prompt,status) "
                               "VALUES(1,1,'下一题','pending')")
        connection.close()
        marker = self.base / "project.txt"
        marker.write_text("保留未完成产物")
        self._enforce()
        run = main.get_run("original")
        self.assertEqual("stopped", run["status"])
        self.assertIsNotNone(run["stop_requested_at"])
        self.assertIn("5h", run["error"])
        self.assertIn("60%", run["error"])
        self.assertIn("观测", run["error"])
        self.runner.cleanup.assert_called_once_with(None, "worker:current")
        self.assertEqual("保留未完成产物", marker.read_text())
        connection = main.get_db()
        self.assertEqual("stopped", connection.execute("SELECT status FROM task_batch_items "
                         "WHERE run_id='original'").fetchone()[0])
        batch = connection.execute("SELECT status,next_launch_at FROM task_batches WHERE id=1").fetchone()
        self.assertEqual(("quota_wait", deadline), tuple(batch))
        connection.close()
        self._expire()
        self.scheduler.submit = Mock()
        self.scheduler.submit_batch = Mock()
        self.guard._resume_account(self.account)
        self.scheduler.submit.assert_not_called()
        self.scheduler.submit_batch.assert_called_once_with(1)
        self.assertEqual("stopped", main.get_run("original")["status"])
        connection = main.get_db()
        self.assertEqual(deadline, connection.execute("SELECT next_launch_at FROM task_batches "
                         "WHERE id=1").fetchone()[0])
        connection.close()

    def test_crossed_5h_or_7d_threshold_stops_normal_and_warmup(self) -> None:
        """任一窗口跨阈值都终止，养号仍由原调度器创建新轮。@return None。"""
        self._running(kind="warmup", batch=False)
        self._observe(five=55, seven=81)
        self._enforce()
        self.assertEqual("stopped", main.get_run("original")["status"])
        self.assertIn("7d", main.get_run("original")["error"])
        scheduler = main.WarmupScheduler(self.scheduler)
        scheduler.handle_run_terminal("original", 7)
        connection = main.get_db()
        account = connection.execute("SELECT warmup_last_status,warmup_next_run_at,"
                                     "warmup_auth_failures FROM accounts WHERE id=1").fetchone()
        connection.close()
        self.assertEqual("stopped", account[0])
        self.assertGreater(account[1], time.time())
        self.assertEqual(0, account[2])

    def test_unknown_low_disabled_expired_and_capture_keep_running(self) -> None:
        """未知、低位、过期、关闭及抓包不触发百分比停止。@return None。"""
        self._running()
        self._enforce()
        self._observe(five=59, seven=79)
        self._enforce()
        self._observe(five=68)
        self._expire()
        self._enforce()
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=NULL,"
                               "warmup_quota_7d_limit_percent=NULL WHERE id=1")
        connection.close()
        self._observe(five=90, seven=90)
        self._enforce()
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=60 WHERE id=1")
            connection.execute("UPDATE runs SET run_kind='capture' WHERE id='original'")
        connection.close()
        self._enforce()
        self.assertEqual("running", main.get_run("original")["status"])
        self.runner.cleanup.assert_not_called()

    def test_stale_execution_cannot_stop_replacement(self) -> None:
        """来源和执行代次不同不能用旧回调停止新 CLI。@return None。"""
        self._running()
        self._observe(five=68)
        self.runtime.job_for_container.return_value["source"] = "run:replacement:0"
        self._enforce()
        self.assertEqual("running", main.get_run("original")["status"])
        self.runner.cleanup.assert_not_called()

    def test_authentication_failure_and_user_stop_win(self) -> None:
        """明确认证错误与用户已提交的停止不被百分比原因覆盖。@return None。"""
        self._running()
        self._observe(five=68)
        self.runner.read_worker_status.return_value = {"status": "auth_failed", "error": "invalid_grant"}
        self._enforce()
        self.assertEqual("running", main.get_run("original")["status"])
        self.runner.read_worker_status.return_value = {}
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE runs SET status='stopping',stop_requested_at=?,error='用户停止' "
                               "WHERE id='original'", (time.time(),))
        connection.close()
        self._enforce()
        self.assertEqual("用户停止", main.get_run("original")["error"])
        self.runner.cleanup.assert_not_called()

    def test_cleanup_failure_does_not_claim_stopped_or_resume_batch(self) -> None:
        """进程清理失败保留失败原因并暂停批次，不伪造已经停止。@return None。"""
        self._running()
        self._observe(five=68)
        self.runner.cleanup.side_effect = ValueError("合成清理失败")
        with self.assertRaisesRegex(ValueError, "合成清理失败"):
            self._enforce()
        run = main.get_run("original")
        self.assertEqual("failed", run["status"])
        self.assertIn("清理失败", run["error"])
        self.assertIn("68%", run["error"])
        connection = main.get_db()
        self.assertEqual("paused", connection.execute("SELECT status FROM task_batches WHERE id=1").fetchone()[0])
        connection.close()

    def test_scheduler_keeps_threshold_reason_and_actual_exit_code(self) -> None:
        """真实调度入口经过活跃回调后保留终态、命中原因和退出码。@return None。"""
        task = self._run()
        self._observe(five=55)

        def start(*args):
            """记录与实际 v3 start_run 相同的归属列；返回执行句柄。"""
            connection = main.get_db()
            with connection:
                connection.execute("UPDATE runs SET environment_id='environment',environment_generation=7,"
                                   "execution_source='run:original:0' WHERE id='original'")
            connection.close()
            return "sidecar", "worker:current"

        def wait(worker_id, *, on_running):
            """模拟正在工作的进程首次报告跨阈值，执行真正的停止回调。"""
            self._observe(five=68)
            on_running()
            return 143

        self.runner.start_run.side_effect = start
        self.runner.wait_worker.side_effect = wait
        self.scheduler._execute("original", self.account, task)
        run = main.get_run("original")
        self.assertEqual("stopped", run["status"])
        self.assertEqual(143, run["exit_code"])
        self.assertIn("68%", run["error"])
        self.assertIn("60%", run["error"])
        self.assertIsNotNone(run["ended_at"])

    def test_configuration_change_and_repeated_callback(self) -> None:
        """运行中降低阈值立即生效，重复检查不再次清理。@return None。"""
        self._running()
        self._observe(five=55)
        self._enforce()
        self.runner.cleanup.assert_not_called()
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=50 WHERE id=1")
        connection.close()
        self._enforce()
        first = main.get_run("original")
        self._enforce()
        self.assertEqual(first["ended_at"], main.get_run("original")["ended_at"])
        self.assertIn("50%", first["error"])
        self.runner.cleanup.assert_called_once_with(None, "worker:current")

    def test_completed_run_is_not_reclassified_when_last_observation_is_high(self) -> None:
        """已有正常完成证据优先，不把晚到的额度变成事后停止。@return None。"""
        self._running()
        self._observe(five=68)
        self.runner.read_worker_status.return_value = {"status": "success"}
        self._enforce()
        self.runner.cleanup.assert_not_called()

    def test_config_raised_before_stop_claim_cancels_stale_decision(self) -> None:
        """停止认领前用户提高阈值时，不按刚失效的旧配置终止任务。@return None。"""
        self._running()
        self._observe(five=68)
        original = self.guard.policy_snapshot

        def changed(*args, **kwargs):
            """返回旧判定前模拟另一个配置事务提交，返回原判定。"""
            policy = original(*args, **kwargs)
            connection = main.get_db()
            with connection:
                connection.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=90 WHERE id=1")
            connection.close()
            return policy

        with patch.object(self.guard, "policy_snapshot", side_effect=changed):
            self._enforce()
        self.assertEqual("running", main.get_run("original")["status"])
        self.runner.cleanup.assert_not_called()

    def test_auth_failure_published_during_cleanup_keeps_permanent_gate(self) -> None:
        """清理竞争中收到明确认证失败时，最终仍显示认证失败。@return None。"""
        self._running()
        self._observe(five=68)

        def cleanup(*args):
            """模拟 CLI 在终止前写入已经收到的上游认证错误。"""
            self.runner.read_worker_status.return_value = {"status": "auth_failed", "error": "invalid_grant"}

        self.runner.cleanup.side_effect = cleanup
        self._enforce()
        self.assertEqual("auth_failed", main.get_run("original")["status"])
        self.assertEqual("invalid_grant", self.guard.snapshot(self.account)["account_error"])

    def test_restart_finishes_stopping_intent_without_resuming_original(self) -> None:
        """停止意图先落盘，重启只能完成旧轮收口，不能恢复原题。@return None。"""
        self._running()
        self._observe(five=68)
        connection = main.get_db()
        with connection:
            connection.execute("UPDATE runs SET status='stopping',stop_requested_at=?,error=? WHERE id='original'",
                               (time.time(), "额度阈值强制中断：5h 已用 68% ≥ 60%"))
        connection.close()
        self.scheduler.submit = Mock()
        self.guard.recover()
        self.assertEqual("stopped", main.get_run("original")["status"])
        self.scheduler.submit.assert_not_called()


class RuntimeQuotaCallbackTests(unittest.TestCase):
    """验证实际 exec 等待器只在当前活跃执行中调用检查。"""

    def test_callback_runs_while_busy_and_finished_exec_keeps_exit_code(self) -> None:
        """真实等待循环保留实际退出码，完成后不再检查阈值。@return None。"""
        runtime = AccountRuntime.__new__(AccountRuntime)
        runtime.client = Mock()
        runtime.lock = threading.RLock()
        job = {"token": "worker:current", "exec": "exec", "row": {
            "environment_id": "environment", "container_id": "worker"}}
        runtime.jobs = {"environment": job}
        runtime.client.api.exec_inspect.side_effect = [{"Running": True}, {"Running": False, "ExitCode": 143}]
        callback = Mock()
        with patch("account_runtime.time.sleep"):
            code = runtime.wait_worker("worker:current", on_running=callback)
        self.assertEqual(143, code)
        callback.assert_called_once_with()

    def test_finished_or_replaced_exec_does_not_run_old_callback(self) -> None:
        """已退出或被替换的执行不再运行旧保护回调。@return None。"""
        runtime = AccountRuntime.__new__(AccountRuntime)
        runtime.client = Mock()
        runtime.lock = threading.RLock()
        job = {"token": "worker:current", "exec": "exec", "row": {
            "environment_id": "environment", "container_id": "worker"}}
        runtime.jobs = {"environment": job}
        callback = Mock()
        runtime.client.api.exec_inspect.return_value = {"Running": False, "ExitCode": 0}
        self.assertEqual(0, runtime.wait_worker("worker:current", on_running=callback))

        def inspect(exec_id):
            """替换执行登记，旧进程只被观察，不获得停止新代的机会。"""
            runtime.jobs["environment"] = {**job, "token": "worker:new"}
            runtime.client.api.exec_inspect.side_effect = None
            runtime.client.api.exec_inspect.return_value = {"Running": False, "ExitCode": 143}
            return {"Running": True}

        runtime.client.api.exec_inspect.side_effect = inspect
        with patch("account_runtime.time.sleep"):
            self.assertEqual(143, runtime.wait_worker("worker:current", on_running=callback))
        callback.assert_not_called()


if __name__ == "__main__":
    unittest.main()
