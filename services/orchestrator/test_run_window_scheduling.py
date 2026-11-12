"""通过真实调度入口和 SQLite 验证当地运行时段，不调用真实上游。"""
import json
import time
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

import main
import test_quota
from account_runtime import AccountRuntime
from run_windows import normalize_run_window


class RunWindowSchedulingTests(unittest.TestCase):
    """验证窗口等待、准入竞争、恢复和交互输入的共同边界。"""

    _run = test_quota.QuotaGuardTests._run
    _state = test_quota.QuotaGuardTests._state

    def setUp(self) -> None:
        """准备合成账号、真实调度器和固定 UTC 时区。@return None。"""
        test_quota.QuotaGuardTests.setUp(self)
        with patch.dict("os.environ", {"V3_DEPLOYMENT_ID": "window-tests", "V3_ACCOUNT_IMAGE": "synthetic", "V3_NETWORK": "synthetic"}):
            schema = AccountRuntime(Mock(), self.base, self.base, main.get_db, Mock(), Mock())
            schema.heartbeat_pool.shutdown()
        self.runtime = Mock()
        self.runtime.run_artifact_path.side_effect = lambda rid, name: self.base / rid / name
        for name, value in (("account_runtime", self.runtime), ("_effective_account_timezone", Mock(return_value="UTC"))):
            patcher = patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _configure(self, state="closed") -> dict:
        """相对当前 UTC 分钟构造确定开放或关闭的窗口，返回最新账号。"""
        minute = int(time.time() // 60) % 1440
        start = (minute + (60 if state == "closed" else -60)) % 1440
        end = (minute + (120 if state == "closed" else 60)) % 1440
        configuration = normalize_run_window({"schema": 1, "enabled": state != "disabled", "days": list(range(7)),
            "intervals": [{"start": f"{start // 60:02}:{start % 60:02}", "end": f"{end // 60:02}:{end % 60:02}"}]})
        with main.get_db() as connection:
            connection.execute("UPDATE accounts SET run_window_json=? WHERE id=1", (json.dumps(configuration),))
            self.account = dict(connection.execute("SELECT * FROM accounts WHERE id=1").fetchone())
        return self.account

    def test_outside_window_waits_without_cli_resources_then_runs_same_payload(self) -> None:
        """等待时不占信号量或写锁，开放后复用同一 run 和正文。@return None。"""
        task = self._run()
        self._configure()

        def open_window(delay):
            """窗口等待期间核对持久标记和资源释放，再由用户关闭限制。"""
            run = main.get_run("original")
            self.assertEqual("queued", run["status"])
            self.assertIsNone(run["started_at"])
            self.assertGreater(run["window_wait_until"], time.time())
            self.runner.start_run.assert_not_called()
            semaphore = self.scheduler._sem(1)
            self.assertTrue(semaphore.acquire(blocking=False))
            semaphore.release()
            self.assertTrue(main._db_lock.acquire(blocking=False))
            main._db_lock.release()
            self._configure("disabled")
            return False

        with patch.object(self.scheduler._window_stop, "wait", side_effect=open_window):
            self.scheduler._execute("original", self.account, task)
        result = main.get_run("original")
        self.assertEqual("success", result["status"])
        self.assertIsNone(result["window_wait_until"])
        self.assertEqual("保持原 prompt", self.runner.start_run.call_args.args[2]["prompt"])
        self.runner.query_quota.assert_not_called()

    def test_closing_window_during_running_task_keeps_actual_success(self) -> None:
        """已启动的整轮不会因时段关闭被提前停止。@return None。"""
        task = self._run()
        self._configure("open")

        def finish(worker):
            """模拟整轮执行期间跨过关闭时刻。"""
            self._configure()
            self.assertEqual("running", main.get_run("original")["status"])
            self.runner.cleanup.assert_not_called()
            return 0

        self.runner.wait_worker.side_effect = finish
        self.scheduler._execute("original", self.account, task)
        result = main.get_run("original")
        self.assertEqual("success", result["status"])
        self.assertIsNone(result["stop_requested_at"])
        self.assertFalse(result["run_window"]["allowed"])

    def test_semaphore_wait_rechecks_window_and_releases_before_resubmit(self) -> None:
        """入队时开放也不能绕过信号量等待后关闭的窗口。@return None。"""
        task = self._run()
        self._configure("open")
        semaphore = Mock()
        semaphore.acquire.side_effect = lambda: self._configure()
        with patch.object(self.scheduler, "_sem", return_value=semaphore), patch.object(self.scheduler, "submit") as submit:
            self.scheduler._execute("original", self.account, task)
        semaphore.release.assert_called_once()
        submit.assert_called_once()
        self.assertFalse(self.scheduler.is_executing("original", 0))
        self.assertEqual("queued", main.get_run("original")["status"])
        self.runner.start_run.assert_not_called()

    def test_stopped_waiter_never_starts_when_window_opens(self) -> None:
        """用户停止优先，随后开放窗口也不能复活该排队。@return None。"""
        task = self._run()
        self._configure()

        def stop_waiter(delay):
            """模拟等待期间已完成的用户停止操作。"""
            with main.get_db() as connection:
                connection.execute("UPDATE runs SET status='stopped',stop_requested_at=? WHERE id='original'", (time.time(),))
            self._configure("open")
            return False

        with patch.object(self.scheduler._window_stop, "wait", side_effect=stop_waiter):
            self.scheduler._execute("original", self.account, task)
        self.assertEqual("stopped", main.get_run("original")["status"])
        self.runner.start_run.assert_not_called()

    def _prepare_recovery_window(self) -> None:
        """建立开放时段及已到期的真实耗尽事实，启用持久单次恢复。"""
        with main.get_db() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=77 WHERE id=1")
        self._configure("open")
        self._state(test_quota.quota_headers(time.time(), 600, rejected=True))
        test_quota.QuotaGuardTests._expire(self)
        self.assertTrue(self.guard.snapshot(self.account)["retry_ready"])

    def _assert_credentials_cross_window(self, kind: str) -> None:
        """真实时间算法跨关窗后保持原轮次排队，并能重新使用未发出的恢复机会。"""
        task = self._run(kind=kind)
        self._prepare_recovery_window()
        snapshot = main.run_window_snapshot
        clock = {"offset": 0}

        def prepare(*args):
            """只推进窗口业务时钟，确认准备前确实认领过恢复机会。"""
            with main.get_db() as connection:
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM warmup_quota_admissions").fetchone()[0])
            clock["offset"] = 7200

        with patch.object(main, "run_window_snapshot", side_effect=lambda configuration, zone, now:
                snapshot(configuration, zone, now + clock["offset"])), \
                patch.object(main, "_sync_bound_account_credentials_locked", side_effect=prepare), \
                patch.object(self.scheduler, "submit") as submit:
            self.scheduler._execute("original", self.account, task)
            result = main.get_run("original")
            self.assertFalse(result["run_window"]["allowed"])
            self.assertEqual("queued", result["status"])
            self.assertIsNone(result["started_at"])
            self.assertIsNotNone(result["window_wait_until"])
            self.assertIsNone(self.guard.snapshot(self.account)["recovery_source"])
            self.assertFalse(self.scheduler.is_executing("original", 0))
            semaphore = self.scheduler._sem(1)
            self.assertTrue(semaphore.acquire(blocking=False))
            semaphore.release()
            submit.assert_called_once()
            self.runner.start_run.assert_not_called()
            with main.get_db() as connection:
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM warmup_quota_admissions").fetchone()[0])
        with patch.object(main, "_sync_bound_account_credentials_locked"):
            self.scheduler._execute("original", self.account, task)
        self.assertEqual("success", main.get_run("original")["status"])
        self.runner.start_run.assert_called_once()
        self.assertEqual("保持原 prompt", self.runner.start_run.call_args.args[2]["prompt"])

    def test_normal_credentials_cross_window_preserves_queue_and_recovery(self) -> None:
        """普通任务凭据准备跨关窗时不能启动，开放后执行原轮次。@return None。"""
        self._assert_credentials_cross_window("normal")

    def test_warmup_credentials_cross_window_preserves_queue_and_recovery(self) -> None:
        """养号准备跨关窗时不发新轮次或耗掉恢复机会。@return None。"""
        self._assert_credentials_cross_window("warmup")

    def test_capture_credentials_cross_window_preserves_queue_and_recovery(self) -> None:
        """抓包准备跨关窗时同样等待，不能借不同额度策略绕过。@return None。"""
        self._assert_credentials_cross_window("capture")

    def test_new_continue_credentials_cross_window_returns_recovery(self) -> None:
        """新续聊准备跨关窗时拒绝且不留下会话锁或已消费许可。@return None。"""
        self._run(status="success")
        self._prepare_recovery_window()
        manager = main.ContinueManager(self.runner)
        snapshot = main.run_window_snapshot
        clock = {"offset": 0}

        def prepare(*args):
            """模拟凭据准备期间当地时段结束。"""
            clock["offset"] = 7200

        with patch.object(main, "_find_latest_claude_session_id", return_value="original-session"), \
                patch.object(main, "run_window_snapshot", side_effect=lambda configuration, zone, now:
                    snapshot(configuration, zone, now + clock["offset"])), \
                patch.object(main, "_sync_bound_account_credentials_locked", side_effect=prepare), \
                self.assertRaisesRegex(ValueError, "休息中"):
            manager.start(main.get_run("original"), self.account)
        self.runner.start_continue.assert_not_called()
        self.assertFalse(manager.sessions)
        self.assertFalse(manager._run_locks)
        self.assertIsNone(self.guard.snapshot(self.account)["recovery_source"])
        with main.get_db() as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM warmup_quota_admissions").fetchone()[0])
        self.runner.start_continue.return_value = ("sidecar", "worker")
        with patch.object(main, "_find_latest_claude_session_id", return_value="original-session"), \
                patch.object(main, "_sync_bound_account_credentials_locked"):
            session = manager.start(main.get_run("original"), self.account)
        self.assertEqual("running", session.status)
        self.runner.start_continue.assert_called_once()
        manager.cleanup(session.sid)

    def test_resumed_attempt_defers_after_preparation_and_survives_restart(self) -> None:
        """已运行过的任务在新代准备跨关窗后仍可按同一代次恢复排队。@return None。"""
        self._run(status="quota_wait")
        self._prepare_recovery_window()
        with main.get_db() as connection:
            connection.execute("UPDATE runs SET started_at=?,quota_identity=? WHERE id='original'",
                (time.time() - 600, main._quota_identity(self.account)))
        with patch.object(self.scheduler, "submit") as submit:
            self.guard._resume_account(self.account)
        rid, account, task = submit.call_args.args
        self.assertEqual(1, task["quota_attempt"])
        snapshot = main.run_window_snapshot
        clock = {"offset": 0}

        def prepare(*args):
            """恢复的新代次在凭据准备期间跨过关窗边界。"""
            clock["offset"] = 7200

        with patch.object(main, "run_window_snapshot", side_effect=lambda configuration, zone, now:
                snapshot(configuration, zone, now + clock["offset"])), \
                patch.object(main, "_sync_bound_account_credentials_locked", side_effect=prepare), \
                patch.object(main, "_find_latest_claude_session_id", return_value="original-session"), \
                patch.object(self.scheduler, "submit"):
            self.scheduler._execute(rid, account, task)
        result = main.get_run(rid)
        self.assertEqual("queued", result["status"])
        self.assertIsNone(result["started_at"])
        self.assertIsNone(result["worker_container"])
        self.runner.start_run.assert_not_called()
        self.guard.recover()
        restored = main.Scheduler(self.runner)
        with patch.object(restored, "submit") as submit:
            restored.recover_window_waits()
        self.assertEqual((rid, 1), (submit.call_args.args[0], submit.call_args.args[2]["quota_attempt"]))

    def test_continue_resume_credentials_cross_window_keeps_original_session(self) -> None:
        """续聊恢复准备跨关窗时保留等待，开放后同会话仍可恢复。@return None。"""
        self._run(status="success")
        with main.get_db() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=77 WHERE id=1")
        self._configure("open")
        self._state(test_quota.quota_headers(time.time(), 600, rejected=True))
        manager = main.ContinueManager(self.runner)
        with patch.object(main, "_find_latest_claude_session_id", return_value="original-session"):
            session = manager.start(main.get_run("original"), self.account)
        session.connected = True
        test_quota.QuotaGuardTests._expire(self)
        snapshot = main.run_window_snapshot
        clock = {"offset": 0}

        def prepare(*args):
            """模拟恢复凭据准备期间跨过结束边界。"""
            clock["offset"] = 7200

        with patch.object(main, "run_window_snapshot", side_effect=lambda configuration, zone, now:
                snapshot(configuration, zone, now + clock["offset"])), \
                patch.object(main, "_sync_bound_account_credentials_locked", side_effect=prepare), \
                patch.object(manager, "cleanup") as cleanup:
            manager.quota_tick(self.account)
        self.runner.start_continue.assert_not_called()
        cleanup.assert_not_called()
        self.assertIs(manager.get(session.sid), session)
        self.assertEqual("quota_wait", session.status)
        self.assertFalse(session.run_window["allowed"])
        self.assertIsNone(self.guard.snapshot(self.account)["recovery_source"])
        with main.get_db() as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM warmup_quota_admissions").fetchone()[0])
        self.runner.start_continue.return_value = ("sidecar", "worker")
        with patch.object(main, "_sync_bound_account_credentials_locked"):
            manager.quota_tick(self.account)
        self.assertEqual("running", session.status)
        self.assertEqual("original-session", self.runner.start_continue.call_args.args[3])
        self.runner.start_continue.assert_called_once()
        manager.cleanup(session.sid)

    def test_unstarted_release_preserves_other_source_identity_and_used_recovery(self) -> None:
        """未启动退还不影响其它来源/身份，正常退出仍保留已使用机会。@return None。"""
        self._prepare_recovery_window()
        source = "run:original:1"
        self.assertTrue(self.guard.admit(self.account, source))
        self.guard.release(self.account, "run:original:0", unstarted=True)
        self.guard.release({**self.account, "cc2api_account_id": 88}, source, unstarted=True)
        self.assertEqual(source, self.guard.snapshot(self.account)["recovery_source"])
        with main.get_db() as connection:
            self.assertEqual(source, connection.execute("SELECT source FROM warmup_quota_admissions").fetchone()[0])
        self.guard.release(self.account, source, unstarted=True)
        self.assertIsNone(self.guard.snapshot(self.account)["recovery_source"])
        self.assertTrue(self.guard.admit(self.account, "run:replacement:0"))
        self.guard.release(self.account, "run:replacement:0")
        self.assertFalse(self.guard.admit(self.account, "run:another:0"))

    def test_disabled_account_cancels_window_wait(self) -> None:
        """等待期间停用账号不再占用排队工作。@return None。"""
        task = self._run()
        self._configure()

        def disable_account(delay):
            """模拟管理员停用账号。"""
            with main.get_db() as connection:
                connection.execute("UPDATE accounts SET enabled=0 WHERE id=1")
            return False

        with patch.object(self.scheduler._window_stop, "wait", side_effect=disable_account):
            self.scheduler._execute("original", self.account, task)
        self.assertEqual("failed", main.get_run("original")["status"])
        self.runner.start_run.assert_not_called()

    def test_quota_resume_outside_window_does_not_claim_recovery(self) -> None:
        """休息期不提前消耗唯一额度恢复许可。@return None。"""
        self._run(status="quota_wait")
        self._configure()
        with patch.object(self.guard, "admit", wraps=self.guard.admit) as admit:
            self.guard._resume_account(self.account)
        admit.assert_not_called()
        with main.get_db() as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM warmup_quota_admissions").fetchone()[0])
        self.assertEqual(0, main.get_run("original")["quota_attempt"])

    def test_warmup_tick_and_manual_entry_do_not_prepare_outside_window(self) -> None:
        """自动养号跳过，立即养号明确拒绝，均不先同步凭据。@return None。"""
        self._configure()
        warmup = main.WarmupScheduler(self.scheduler)
        self.assertFalse(warmup.trigger_account(1, require_due=True)["started"])
        with patch.object(main, "warmup_scheduler", warmup), self.assertRaises(HTTPException) as raised:
            main.run_account_warmup_now(1)
        self.assertEqual(409, raised.exception.status_code)
        self.runner.start_run.assert_not_called()
        main.cc2api_client._request.assert_not_called()

    def test_continue_input_is_rejected_without_stopping_output_or_replay(self) -> None:
        """窗口外输入不发往 PTY；已有回合保持运行，开放后不重放旧输入。@return None。"""
        self._configure()
        manager = main.ContinueManager(self.runner)
        session = main.ContinueSession("sid", "original", 1, "sidecar", "worker", "session", "bypassPermissions")
        manager.sessions[session.sid] = session
        raw = Mock()
        with patch.object(manager, "cleanup") as cleanup:
            self.assertFalse(manager.send_input(session, 0, raw, b"blocked"))
        raw.send.assert_not_called()
        cleanup.assert_not_called()
        self.assertEqual("running", session.status)
        self._configure("open")
        self.assertTrue(manager.send_input(session, 0, raw, b"new input"))
        raw.send.assert_called_once_with(b"new input")

    def test_new_continue_is_refused_before_creating_session(self) -> None:
        """休息时不能通过新续聊绕过时间窗口。@return None。"""
        self._configure()
        manager = main.ContinueManager(self.runner)
        with self.assertRaisesRegex(ValueError, "休息中"):
            manager.start({"id": "original"}, self.account)
        self.runner.start_continue.assert_not_called()

    def test_restart_preserves_queued_waiter_and_frozen_execution(self) -> None:
        """窗口排队不会被额度恢复当成崩溃执行，重投复用原快照。@return None。"""
        self._run()
        self._configure()
        with main.get_db() as connection:
            connection.execute("UPDATE runs SET window_wait_until=?,followup_plan_json='[\"Original followup\"]' "
                               "WHERE id='original'", (time.time() + 600,))
        self.guard.recover()
        self.runner.cleanup_quota_run.assert_not_called()
        with patch.object(self.scheduler, "submit") as submit:
            self.scheduler.recover_window_waits()
        rid, account, task = submit.call_args.args
        self.assertEqual("original", rid)
        self.assertEqual("保持原 prompt", task["prompt"])
        self.assertEqual('["Original followup"]', task["followup_plan_json"])
        self.assertEqual("2.1.62", task["claude_code_version"])
        self.assertEqual("high", task["claude_effort_level"])
        self.assertEqual(0, task["quota_attempt"])

    def test_restart_finishes_waiter_stop_intent_without_revival(self) -> None:
        """排队取消时崩溃只完成旧停止意图，不新建执行。@return None。"""
        self._run(status="stopping")
        with main.get_db() as connection:
            connection.execute("UPDATE runs SET window_wait_until=?,stop_requested_at=? WHERE id='original'",
                (time.time() + 600, time.time()))
        with patch.object(self.scheduler, "submit") as submit:
            self.scheduler.recover_window_waits()
        submit.assert_not_called()
        self.assertEqual("stopped", main.get_run("original")["status"])

    def test_batch_pause_during_rest_preserves_random_interval_and_pending_item(self) -> None:
        """休息中的人工暂停保留原投放间隔，不生成下一轮。@return None。"""
        self._run(batch=True, status="success")
        self._configure()
        deadline = time.time() - 1
        with main.get_db() as connection:
            connection.execute("UPDATE task_batches SET next_launch_at=? WHERE id=1", (deadline,))
            connection.execute("INSERT INTO task_batch_items(batch_id,topic_id,prompt,status) VALUES(1,1,'Next','pending')")

        def pause_batch(delay):
            """窗口等待中模拟人工暂停。"""
            with main.get_db() as connection:
                connection.execute("UPDATE task_batches SET status='paused' WHERE id=1")
            return False

        with patch.object(self.scheduler._window_stop, "wait", side_effect=pause_batch):
            self.scheduler._execute_batch(1)
        with main.get_db() as connection:
            self.assertEqual(("paused", deadline), tuple(connection.execute("SELECT status,next_launch_at "
                             "FROM task_batches WHERE id=1").fetchone()))
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM task_batch_items WHERE status='pending'").fetchone()[0])
        self.runner.start_run.assert_not_called()

    def test_save_and_repeated_schema_upgrade_keep_configuration_and_credentials(self) -> None:
        """保存重读和幂等升级保留时段及原凭据，不分配环境。@return None。"""
        credentials = (main.PROFILES_DIR / "fixture/.credentials.json").read_bytes()
        body = main.RunWindowConfigIn(enabled=True, days=[0, 2, 4], intervals=[{"start": "22:00", "end": "02:00"}])
        result = main.update_account_run_window(1, body)
        main.init_db()
        main.init_db()
        policy = main.get_account_run_window(1)
        self.assertEqual(result["run_window"]["config"], policy["config"])
        self.assertEqual("UTC", policy["timezone"])
        self.assertEqual(credentials, (main.PROFILES_DIR / "fixture/.credentials.json").read_bytes())
        self.runtime.ensure.assert_not_called()
        with self.assertRaises(ValidationError):
            main.RunWindowConfigIn(enabled="true", days=[0], intervals=[])


if __name__ == "__main__":
    unittest.main()
