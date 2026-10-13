"""验证原生 TLS 下的无人值守额度采样、恢复和本地账号养号。"""
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import main
import test_quota


class AutoUsageTests(unittest.TestCase):
    """复用真实 SQLite 与调度器，模拟额度服务而不发送模型请求。"""

    _run = test_quota.QuotaGuardTests._run
    _state = test_quota.QuotaGuardTests._state

    def setUp(self) -> None:
        """建立隔离数据库、原生账号运行时和可控 usage 结果。@return None。"""
        test_quota.QuotaGuardTests.setUp(self)
        environment = patch.dict(main.os.environ, {"V3_DEPLOYMENT_ID": "test-auto", "V3_ACCOUNT_IMAGE": "synthetic",
            "V3_NETWORK": "vibebench-v3-test-auto", "V3_ACCOUNT_MEMORY": "1536m"})
        environment.start()
        self.addCleanup(environment.stop)
        runtime = main.AccountRuntime(Mock(), self.base, self.base, main.get_db,
            main.derive_v3_fingerprint, main.cc2api_client)
        self.addCleanup(runtime.heartbeat_pool.shutdown)
        patcher = patch.object(main, "account_runtime", runtime)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.runtime = runtime
        self.runner.query_quota.side_effect = None
        self.runner.query_quota.return_value = self._usage(10)
        with main.get_db() as conn:
            conn.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=70,warmup_quota_7d_limit_percent=85 WHERE id=1")
            self.account = dict(conn.execute("SELECT * FROM accounts WHERE id=1").fetchone())

    def _usage(self, five=10, seven=20) -> dict:
        """生成未来窗口的标准化真实接口结果；参数为已用百分比。@return 额度对象。"""
        now = time.time()
        return {"ok": True,
            "five_hour": {"utilization": five, "resets_at": datetime.fromtimestamp(now + 3600, timezone.utc).isoformat()},
            "seven_day": {"utilization": seven, "resets_at": datetime.fromtimestamp(now + 86400, timezone.utc).isoformat()}}

    def test_unknown_task_queries_before_execution_and_updates_after_consumption(self) -> None:
        """未知额度自动查询；当前任务收尾后高用量阻止下一条。@return None。"""
        task = self._run()
        self.runner.query_quota.side_effect = [self._usage(10), self._usage(75)]
        self.scheduler._execute("original", self.account, task)
        self.assertEqual("success", main.get_run("original")["status"])
        self.assertEqual(2, self.runner.query_quota.call_count)
        next_task = self._run("next")
        self.scheduler._execute("next", self.account, next_task)
        self.assertEqual("quota_wait", main.get_run("next")["status"])
        self.assertEqual(1, self.runner.start_run.call_count)
        self.assertEqual("automatic", self.guard.snapshot(self.account)["source"])

    def test_expired_window_refreshes_without_manual_query(self) -> None:
        """5h 重置自动采样，不让旧高位额度永久阻断。@return None。"""
        now = time.time()
        self._state(test_quota.quota_headers(now, five=1), status=429)
        with patch.object(main.time, "time", return_value=now + 2):
            self.assertTrue(self.guard.refresh_usage(self.account))
            self.assertFalse(self.guard.policy_snapshot(self.account, "normal")["blocked"])
        self.runner.query_quota.assert_called_once()

    def test_failure_retries_later_and_does_not_send_model_requests(self) -> None:
        """查询失败有间隔重试；等待期间不启动 CLI。@return None。"""
        task = self._run()
        self.runner.query_quota.return_value = {"ok": False, "raw": {"status": 429, "retry_after_sec": 120}}
        self.scheduler._execute("original", self.account, task)
        for _ in range(3):
            self.guard.tick()
        self.runner.query_quota.assert_called_once()
        self.runner.start_run.assert_not_called()
        policy = self.guard.policy_snapshot(self.account, "normal")
        self.assertIn("自动额度查询失败", policy["message"])
        retry = policy["refresh_retry_at"]
        self.assertGreater(retry, time.time() + 110)
        self.runner.query_quota.return_value = self._usage(10)
        with patch.object(main.time, "time", return_value=retry + 1), patch.object(self.scheduler, "submit") as submit:
            self.guard.tick()
        submit.assert_called_once()
        self.assertEqual("queued", main.get_run("original")["status"])

    def test_zero_run_batch_is_resumed_by_automatic_usage(self) -> None:
        """尚未创建第一条 run 的批次也能由自动采样恢复。@return None。"""
        with main.get_db() as conn:
            conn.execute("INSERT INTO task_batches(id,account_id,name,status) VALUES(1,1,'fixture','quota_wait')")
            conn.execute("INSERT INTO task_batch_items(batch_id,topic_id,prompt,status) VALUES(1,1,'English task','pending')")
        with patch.object(self.scheduler, "submit_batch") as submit:
            self.guard.tick()
        submit.assert_called_once_with(1)
        with main.get_db() as conn:
            self.assertEqual("active", conn.execute("SELECT status FROM task_batches WHERE id=1").fetchone()[0])
            self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])

    def test_concurrent_admission_reuses_recent_usage(self) -> None:
        """同时启动复用同账号采样，避免重复查询。@return None。"""
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(lambda _: self.guard.refresh_usage(self.account), range(4))))
        self.runner.query_quota.assert_called_once()

    def test_missing_enabled_window_and_auth_error_are_visible(self) -> None:
        """不完整额度和认证错误不会伪装成功，也不会高速重查。@return None。"""
        self.runner.query_quota.return_value = {"ok": True, "five_hour": self._usage()["five_hour"]}
        self.assertFalse(self.guard.refresh_usage(self.account))
        self.assertTrue(self.guard.policy_snapshot(self.account, "normal")["blocked"])
        self.guard._usage_refresh.clear()
        self.runner.query_quota.return_value = {"ok": False, "raw": {"status": 401}}
        self.assertFalse(self.guard.refresh_usage(self.account))
        self.assertIn("认证失败", self.guard.policy_snapshot(self.account, "normal")["message"])

    def test_partial_result_cannot_reuse_consumption_before_cache(self) -> None:
        """消费后缺失的窗口不能用旧低位数据代替新采样。@return None。"""
        self.assertTrue(self.guard.refresh_usage(self.account))
        self.guard.invalidate_usage(self.account)
        self.runner.query_quota.return_value = {"ok": True, "five_hour": self._usage()["five_hour"]}
        self.assertFalse(self.guard.refresh_usage(self.account, force=True))
        self.assertTrue(self.guard.policy_snapshot(self.account, "normal")["blocked"])

    def test_native_quota_probe_does_not_inject_mitm_certificates(self) -> None:
        """查询实际 exec 使用原生 TLS，错误也保持结构化返回。@return None。"""
        runner = object.__new__(main.Runner)
        runner.client = Mock()
        runner.client.api.exec_create.return_value = {"Id": "probe"}
        runner.client.api.exec_start.return_value = json.dumps(self._usage()).encode()
        runner.client.api.exec_inspect.return_value = {"ExitCode": 0}
        with patch.object(self.runtime, "job_for_container", return_value={"row": {"container_id": "container"}}):
            result = runner._exec_quota_probe("container")
        self.assertTrue(result["ok"])
        environment = runner.client.api.exec_create.call_args.kwargs["environment"]
        self.assertEqual("1", environment["V3_NATIVE_USAGE"])
        self.assertFalse(any(key in environment for key in (
            "NODE_EXTRA_CA_CERTS", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "GIT_SSL_CAINFO")))

    def test_bound_query_uses_existing_owner_lock_without_reentry(self) -> None:
        """绑定查询沿唯一刷新者同步 AT，不重入 owner 锁导致死锁。@return None。"""
        runner = object.__new__(main.Runner)
        account = dict(self.account, cc2api_account_id=7, upstream_socks5_host="proxy.invalid")
        row = {"environment_id": "synthetic"}
        container = Mock(id="container")
        job = {"token": "probe"}
        with main._oauth_owner_lock(account["name"]), \
                patch.object(self.runtime, "ensure", return_value=(row, container)), \
                patch.object(self.runtime, "claim", return_value=job), \
                patch.object(self.runtime, "sync_credentials"), \
                patch.object(self.runtime, "release") as release, \
                patch.object(main, "_sync_bound_account_credentials", side_effect=AssertionError("不可重入 owner 锁")), \
                patch.object(main, "_sync_bound_account_credentials_locked") as synchronize, \
                patch.object(runner, "_exec_quota_probe", return_value=self._usage()):
            result = runner.query_quota(account)
        self.assertTrue(result["ok"])
        synchronize.assert_called_once_with(account, 600)
        release.assert_called_once_with(job)

    def test_unbound_warmup_config_and_terminal_schedule_work(self) -> None:
        """本地 OAuth 能启用、创建、执行养号并安排下一次。@return None。"""
        profile = main.PROFILES_DIR / "fixture"
        (profile / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": "local", "emailAddress": "fixture@example.invalid"}}))
        (profile / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {
            "accessToken": "synthetic", "refreshToken": "synthetic-refresh", "expiresAt": int((time.time() + 86400) * 1000)}}))
        main.update_account_warmup(1, main.WarmupConfigIn(enabled=True))
        with main.get_db() as conn:
            self.account = dict(conn.execute("SELECT * FROM accounts WHERE id=1").fetchone())
        warmup = main.WarmupScheduler(self.scheduler)
        with patch.object(main, "warmup_scheduler", warmup), patch.object(self.scheduler, "submit") as submit:
            result = warmup.trigger_account(1)
            self.assertTrue(result["started"])
            args = submit.call_args.args
            self.scheduler._execute(*args)
        with main.get_db() as conn:
            account = dict(conn.execute("SELECT * FROM accounts WHERE id=1").fetchone())
        self.assertIsNone(account["cc2api_account_id"])
        self.assertEqual("success", account["warmup_last_status"])
        self.assertGreater(account["warmup_next_run_at"], time.time())
        main.cc2api_client.resolve_credentials.assert_not_called()

    def test_new_run_uses_global_settings_and_resume_keeps_snapshot(self) -> None:
        """固定账号的新 run 使用新全局参数，恢复仍保留原快照。@return None。"""
        old = self._run()
        main.save_runtime_model_setting("sonnet")
        main.save_runtime_effort_setting("low")
        main.save_runtime_claude_code_version_setting("2.1.293")
        with patch.object(self.scheduler, "submit") as submit:
            rid = main.run_task(old["id"])["run_ids"][0]
        created = main.get_run(rid)
        self.assertEqual(("low", "2.1.293"), (created["claude_effort_level"], created["claude_code_version"]))
        self.scheduler._execute(*submit.call_args.args)
        self.assertEqual("sonnet", main.get_run(rid)["execution_model"])
        with main.get_db() as conn:
            conn.execute("UPDATE runs SET status='quota_wait' WHERE id=?", (rid,))
        main.save_runtime_model_setting("opus")
        main.save_runtime_claude_code_version_setting("2.1.280")
        with patch.object(self.scheduler, "submit") as resume:
            self.guard._resume_account(self.account)
        restored = resume.call_args.args[2]
        self.assertEqual(("sonnet", "low", "2.1.293"), (
            restored["model_override"], restored["claude_effort_level"], restored["claude_code_version"]))


if __name__ == "__main__":
    unittest.main()
