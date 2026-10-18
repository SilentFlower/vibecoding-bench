"""验证 v3 被动额度、手动查询、原任务恢复和本地账号养号。"""
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from cli_quota import statusline_quota_observation
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
        self.runner.query_quota.side_effect = AssertionError("v3 自动路径禁止主动查询")
        with main.get_db() as conn:
            conn.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=70,warmup_quota_7d_limit_percent=85 WHERE id=1")
            self.account = dict(conn.execute("SELECT * FROM accounts WHERE id=1").fetchone())

    def _usage(self, five=10, seven=20) -> dict:
        """生成未来窗口的标准化真实接口结果；参数为已用百分比。@return 额度对象。"""
        now = time.time()
        return {"ok": True,
            "five_hour": {"utilization": five, "resets_at": datetime.fromtimestamp(now + 3600, timezone.utc).isoformat()},
            "seven_day": {"utilization": seven, "resets_at": datetime.fromtimestamp(now + 86400, timezone.utc).isoformat()}}

    def _passive(self, five=10, seven=20, observed=None, reset=None) -> None:
        """注入正常响应的数据；参数为百分比与时间，返回 None。"""
        now = time.time() if observed is None else observed
        observation = statusline_quota_observation({
            "five_hour": {"used_percentage": five, "resets_at": reset or now + 3600},
            "seven_day": {"used_percentage": seven, "resets_at": now + 86400},
        }, now)
        self.guard._observe(self.account, main._quota_identity(self.account), observation)

    def test_unknown_task_runs_without_usage_and_passive_high_value_stops_next(self) -> None:
        """首次未知可运行，正式响应达到阈值后下一条等待；无 usage 请求。@return None。"""
        task = self._run()
        def completed(worker, *, on_running=None):
            """模拟进程已退出后取得最后额度，不再调用活跃回调；返回退出码。"""
            self._passive(75)
            return 0
        self.runner.wait_worker.side_effect = completed
        self.scheduler._execute("original", self.account, task)
        self.assertEqual("success", main.get_run("original")["status"])
        self.scheduler._execute("next", self.account, self._run("next"))
        self.assertEqual("quota_wait", main.get_run("next")["status"])
        self.assertEqual(1, self.runner.start_run.call_count)
        self.runner.query_quota.assert_not_called()
        self.assertEqual("cli", self.guard.snapshot(self.account)["source"])

    def test_old_observation_does_not_trigger_time_based_usage_query(self) -> None:
        """超过原五分钟缓存也只使用有效窗口，后台不主动补查。@return None。"""
        now = time.time()
        self._passive(10, observed=now)
        with patch.object(main.time, "time", return_value=now + 301):
            self.assertFalse(self.guard.policy_snapshot(self.account, "normal")["blocked"])
            for _ in range(3):
                self.guard.tick()
        self.runner.query_quota.assert_not_called()
        main.cc2api_client.refresh_usage.assert_not_called()

    def test_expired_threshold_admits_only_one_existing_execution(self) -> None:
        """已命中窗口重置后，普通任务与养号共享一个持久更新机会。@return None。"""
        now = time.time()
        self._passive(75, observed=now, reset=now + 1)
        self.assertTrue(self.guard.policy_snapshot(self.account, "normal")["blocked"])
        with patch.object(main.time, "time", return_value=now + 2):
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda n: self.guard.admit(self.account, f"run:restore:{n}",
                    workload="normal" if n % 2 else "warmup"), range(4)))
            self.assertEqual(1, sum(results))
            self.assertTrue(self.guard.policy_snapshot(self.account, "normal")["blocked"])
            self._passive(10, observed=now + 2)
            self.assertFalse(self.guard.policy_snapshot(self.account, "normal")["blocked"])
        self.runner.query_quota.assert_not_called()

    def test_incomplete_recovery_does_not_issue_another_update_opportunity(self) -> None:
        """一次正常恢复仍缺原阻断窗口时，重启不重新发机会。@return None。"""
        now = time.time()
        self._passive(75, observed=now, reset=now + 1)
        with patch.object(main.time, "time", return_value=now + 2):
            self.assertTrue(self.guard.admit(self.account, "run:restore:1", workload="normal"))
            self.guard._observe(self.account, main._quota_identity(self.account),
                statusline_quota_observation({"seven_day": {"used_percentage": 20, "resets_at": now + 86400}}, now + 2))
            self.guard.release(self.account, "run:restore:1")
            restarted = main.QuotaGuard(self.runner)
            self.assertFalse(restarted.admit(self.account, "run:restore:2", workload="normal"))
        self.runner.query_quota.assert_not_called()

    def test_zero_run_batch_resumes_without_usage_query(self) -> None:
        """尚未创建第一条 run 的批次能正常启动，不靠 usage 解锁。@return None。"""
        with main.get_db() as conn:
            conn.execute("INSERT INTO task_batches(id,account_id,name,status) VALUES(1,1,'fixture','quota_wait')")
            conn.execute("INSERT INTO task_batch_items(batch_id,topic_id,prompt,status) VALUES(1,1,'English task','pending')")
        with patch.object(self.scheduler, "submit_batch") as submit:
            self.guard.tick()
        submit.assert_called_once_with(1)
        self.runner.query_quota.assert_not_called()

    def test_common_exhaustion_without_thresholds_has_one_persistent_recovery(self) -> None:
        """阈值关闭也不能对已耗尽窗口反复投放无新观察的恢复。@return None。"""
        with main.get_db() as connection:
            connection.execute("UPDATE accounts SET warmup_quota_5h_limit_percent=NULL,warmup_quota_7d_limit_percent=NULL WHERE id=1")
        now = time.time()
        self._passive(100, observed=now, reset=now + 1)
        with patch.object(main.time, "time", return_value=now + 2):
            self.assertTrue(self.guard.admit(self.account, "run:restore:1", workload="normal"))
            self.guard.release(self.account, "run:restore:1")
            restarted = main.QuotaGuard(self.runner)
            self.assertFalse(restarted.admit(self.account, "run:restore:2", workload="warmup"))
            self._passive(10, observed=now + 2)
            self.assertTrue(restarted.admit(self.account, "run:restore:3", workload="normal"))
        self.runner.query_quota.assert_not_called()

    def test_continue_ignores_threshold_but_shares_common_recovery(self) -> None:
        """续聊不受百分比阈值限制，却与普通任务共享共同耗尽的单次恢复。@return None。"""
        now = time.time()
        self._passive(75, observed=now)
        self.assertTrue(self.guard.admit(self.account, "continue:synthetic:1"))
        self.assertFalse(self.guard.admit(self.account, "run:normal:1", workload="normal"))
        self._passive(100, observed=now + 0.1, reset=now + 1)
        with patch.object(main.time, "time", return_value=now + 2):
            self.assertTrue(self.guard.admit(self.account, "continue:synthetic:2"))
            self.guard.release(self.account, "continue:synthetic:2")
            self.assertFalse(self.guard.admit(self.account, "run:normal:2", workload="normal"))
            self.assertFalse(self.guard.admit(self.account, "continue:synthetic:3"))
        self.runner.query_quota.assert_not_called()

    def test_manual_query_is_once_and_permanent_error_stops_background_recovery(self) -> None:
        """用户查询明确返回暂停时停止恢复，后续 tick 不重查。@return None。"""
        self._run(status="quota_wait")
        self.runner.query_quota.side_effect = None
        self.runner.query_quota.return_value = {"ok": False, "raw": {"status": 403,
            "error": 'HTTP 403: {"error":{"type":"account_on_hold"}}'}}
        main.query_account_quota(1)
        for _ in range(3):
            self.guard.tick()
        self.runner.query_quota.assert_called_once()
        self.assertEqual("account_on_hold", self.guard.snapshot(self.account)["account_error"])
        self.assertEqual("auth_failed", main.get_run("original")["status"])

    def test_manual_network_failure_is_not_permanent_and_does_not_retry(self) -> None:
        """网络／普通认证失败不猜测封禁，也不安排后台查询。@return None。"""
        self.runner.query_quota.side_effect = None
        self.runner.query_quota.return_value = {"ok": False, "raw": {"status": 401, "error": "Invalid token"}}
        main.query_account_quota(1)
        self.guard.tick()
        self.runner.query_quota.assert_called_once()
        self.assertFalse(self.guard.snapshot(self.account).get("account_error"))
        self.assertIsNone(self.guard.policy_snapshot(self.account, "normal")["refresh_retry_at"])

    def test_cli_observation_file_reaches_shared_quota_state(self) -> None:
        """正式执行的 CLI 文件进入现有游标；本地字段不能伪造永久账号错误。@return None。"""
        source = "run:synthetic:0"
        flows = self.base / "flows/fixture/1/synthetic"
        context = self.guard.prepare(self.account, source, flows, self.base / "controls")
        directory = flows / "cli"
        directory.mkdir()
        now = time.time()
        event = {"source": "cli:" + source, "identity": context["QUOTA_IDENTITY"], "ts": now,
            "origin": "cli", "session_id": "synthetic", "response_id": "response-1",
            "rate_limits": {"five_hour": {"used_percentage": 75, "resets_at": now + 3600}},
            "account_error": "account_on_hold"}
        (directory / "cli-quota.jsonl").write_text(json.dumps(event) + "\n")
        self.guard.consume(self.account)
        self.assertEqual(75, self.guard.snapshot(self.account)["windows"]["five_hour"]["utilization"])
        self.assertTrue(self.guard.policy_snapshot(self.account, "normal")["blocked"])
        self.assertFalse(self.guard.snapshot(self.account).get("account_error"))
        self.runner.query_quota.assert_not_called()

    def test_restart_recovers_only_active_batches_and_keeps_saved_delay(self) -> None:
        """重启重新注册活动批次并保留延迟，不投放暂停、删除或停用账号的批次。@return None。"""
        deadline = time.time() + 600
        with main.get_db() as connection:
            connection.execute("INSERT INTO accounts(id,name,profile_path,enabled) VALUES(2,'disabled','disabled',0)")
            for batch_id, account_id, status, deleted in ((1, 1, 'active', None),
                    (2, 1, 'paused', None), (3, 2, 'active', None), (4, 1, 'active', time.time())):
                connection.execute("INSERT INTO task_batches(id,account_id,name,status,deleted_at,next_launch_at) VALUES(?,?,?, ?,?,?)",
                    (batch_id, account_id, 'fixture', status, deleted, deadline))
            connection.execute("INSERT INTO task_batch_items(batch_id,topic_id,prompt,status) VALUES(1,1,'English task','pending')")
        with patch.object(self.scheduler, "submit_batch") as submit:
            self.scheduler.recover_active_batches()
        submit.assert_called_once_with(1)
        with patch.object(main, "V3_ENABLED", True), patch.object(self.scheduler, "_sleep_batch_delay", return_value=False) as delay:
            self.scheduler._execute_batch(1)
        delay.assert_called_once()
        self.assertGreater(delay.call_args.args[1], 590)
        with main.get_db() as connection:
            self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
            self.assertEqual(deadline, connection.execute("SELECT next_launch_at FROM task_batches WHERE id=1").fetchone()[0])

    def test_native_quota_probe_does_not_inject_mitm_certificates(self) -> None:
        """查询实际 exec 使用原生 TLS，错误也保持结构化返回。@return None。"""
        runner = object.__new__(main.Runner)
        runner.client = Mock()
        runner.client.api.exec_create.return_value = {"Id": "probe"}
        runner.client.api.exec_start.return_value = json.dumps(self._usage()).encode()
        runner.client.api.exec_inspect.return_value = {"ExitCode": 0}
        row = self.runtime._row(self.account["name"], self.account["id"])
        with patch.object(self.runtime, "job_for_container", return_value={"row": {**row, "container_id": "container"}}):
            result = runner._exec_quota_probe("container")
        self.assertTrue(result["ok"])
        environment = runner.client.api.exec_create.call_args.kwargs["environment"]
        self.assertEqual("1", environment["V3_NATIVE_USAGE"])
        self.assertEqual("America/Los_Angeles", environment["TZ"])
        self.assertEqual("en_US.UTF-8", environment["LANG"])
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
