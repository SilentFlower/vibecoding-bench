"""养号阈值、持久单次请求与原 run 恢复的行为验证；不访问真实上游。"""

import json
import os
import subprocess
import threading
import time
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from pydantic import ValidationError

import main
from projects import ProjectsService
from quota_protocol import warmup_quota_decision, warmup_sample_used
import test_quota
from test_quota import quota_headers


class WarmupProtocolTests(unittest.TestCase):
    """验证阈值比较和窗口周期，不把养号预算误记为真正耗尽。"""

    def test_each_window_equality_disabled_and_latest_reset(self) -> None:
        """两个窗口任一命中都等待，关闭窗口不参与比较。@return None。"""
        now = time.time()
        state = {"windows": {
            "five_hour": {"utilization": 30, "reset_at": now + 100},
            "seven_day": {"utilization": 20, "reset_at": now + 900},
        }}
        for limits, hit, reset in [
            ({"five_hour": 30}, ["five_hour"], now + 100),
            ({"seven_day": 20}, ["seven_day"], now + 900),
            ({"five_hour": 30, "seven_day": 20}, ["five_hour", "seven_day"], now + 900),
            ({"five_hour": 31, "seven_day": 21}, [], None),
            ({}, [], None),
        ]:
            with self.subTest(limits=limits):
                result = warmup_quota_decision(state, limits, now)
                self.assertEqual(hit, result["hit"])
                self.assertEqual(reset, result["resume_at"])
                self.assertEqual(bool(hit), result["blocked"])
        self.assertNotIn("exhausted", state["windows"]["five_hour"])

    def test_missing_reset_never_bypasses_known_hit(self) -> None:
        """缺 reset 的高位事实持续阻断，不猜恢复时间。@return None。"""
        result = warmup_quota_decision({"windows": {"five_hour": {"utilization": 30}}},
                                       {"five_hour": 30, "seven_day": 20}, time.time())
        self.assertTrue(result["blocked"])
        self.assertFalse(result["sample_required"])
        self.assertIsNone(result["resume_at"])

    def test_partial_update_does_not_rearm_missing_window(self) -> None:
        """一次请求仅补齐 5h 时，仍未知的 7d 不能再次发放机会。@return None。"""
        now = time.time()
        limits = {"five_hour": 30, "seven_day": 20}
        first = warmup_quota_decision({}, limits, now)
        admission = {key: first[key] for key in ("policy_key", "window_key")}
        partial = warmup_quota_decision({"windows": {"five_hour": {"utilization": 10, "reset_at": now + 100}}}, limits, now + 1)
        self.assertEqual(["seven_day"], partial["unknown"])
        self.assertTrue(warmup_sample_used(partial, admission))
        same_unknown = warmup_quota_decision({"observed_at": now + 60}, limits, now + 60)
        self.assertTrue(warmup_sample_used(same_unknown, admission))

    def test_expiry_is_an_opportunity_not_zero_usage(self) -> None:
        """真实窗口到期不归零旧用量，新周期许可与已用旧机会区分。@return None。"""
        now = time.time()
        state = {"windows": {"five_hour": {"utilization": 80, "reset_at": now + 10}}}
        result = warmup_quota_decision(state, {"five_hour": 30}, now + 11)
        self.assertFalse(result["blocked"])
        self.assertTrue(result["sample_required"])
        self.assertEqual(80, state["windows"]["five_hour"]["utilization"])


class WarmupQuotaTests(unittest.TestCase):
    """复用隔离额度夹具，验证真实数据库与调度入口。"""

    _run = test_quota.QuotaGuardTests._run
    _state = test_quota.QuotaGuardTests._state

    def setUp(self) -> None:
        """创建私有数据库、假身份及禁止主动查询的运行器。@return None。"""
        test_quota.QuotaGuardTests.setUp(self)
        patcher = patch.object(main, "account_runtime", None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _configure(self, five=30, seven=None) -> None:
        """写入账号配置并重读；参数为两个已用阈值，返回 None。"""
        conn = main.get_db()
        try:
            with conn:
                conn.execute("UPDATE accounts SET warmup_enabled=1,cc2api_account_id=7,"
                             "warmup_quota_5h_limit_percent=?,warmup_quota_7d_limit_percent=? WHERE id=1", (five, seven))
            self.account = dict(conn.execute("SELECT * FROM accounts WHERE id=1").fetchone())
        finally:
            conn.close()

    def test_single_opportunity_survives_restart_failure_and_regular_requests(self) -> None:
        """未知机会持久化，普通请求不消费或继承养号额度。@return None。"""
        self._configure()
        self.assertTrue(self.guard.admit(self.account, "run:first:0", warmup=True))
        self.guard.release(self.account, "run:first:0")
        restarted = main.QuotaGuard(self.runner)
        self.assertFalse(restarted.admit(self.account, "run:second:0", warmup=True))
        self.assertTrue(restarted.admit(self.account, "run:normal:0"))
        self.assertFalse(restarted.snapshot(self.account)["blocked"])
        self.runner.query_quota.assert_not_called()
        main.cc2api_client.refresh_usage.assert_not_called()

    def test_prepare_marks_only_unknown_warmup_as_quota_sample(self) -> None:
        """养号仅在领取未知额度机会时请求 Recorder，可信低位继续透传。@return None。"""
        self._configure()
        source = "run:sample:0"
        self.assertTrue(self.guard.admit(self.account, source, warmup=True))
        unknown = self.guard.prepare(
            self.account,
            source,
            self.base / "unknown-flows",
            self.base / "unknown-controls",
            warmup=True,
        )
        self.assertEqual("1", unknown["QUOTA_SAMPLE_REQUIRED"])

        now = time.time()
        self._state(quota_headers(now, five=600), status=200)
        known = self.guard.prepare(
            self.account,
            "run:known:0",
            self.base / "known-flows",
            self.base / "known-controls",
            warmup=True,
        )
        self.assertEqual("0", known["QUOTA_SAMPLE_REQUIRED"])

    def test_failed_partial_update_remains_waiting(self) -> None:
        """只取得一个启用窗口时仍等待，重复扫描不再提交养号。@return None。"""
        self._configure(30, 40)
        self.assertTrue(self.guard.admit(self.account, "run:first:0", warmup=True))
        self._state(quota_headers(time.time(), five=600), status=200)
        for _ in range(3):
            self.assertFalse(self.guard.admit(self.account, "run:retry:1", warmup=True))
        self.assertTrue(self.guard.warmup_snapshot(self.account)["sample_used"])

    def test_policy_change_but_not_identical_save_rearms_unknown(self) -> None:
        """只有实质策略变化才重新评估未知机会。@return None。"""
        self._configure(30)
        self.assertTrue(self.guard.admit(self.account, "run:first:0", warmup=True))
        self._configure(30)
        self.assertFalse(self.guard.admit(self.account, "run:again:0", warmup=True))
        self._configure(40)
        self.assertTrue(self.guard.admit(self.account, "run:changed:0", warmup=True))

    def test_config_publish_cannot_overwrite_newer_response(self) -> None:
        """配置保存与响应消费交错后，Recorder 仍读到最新窗口和命中结果。@return None。"""
        self._configure(30)
        now = time.time()
        self._state(quota_headers(now, five=600), status=200)
        flows = self.base / "api-flows"
        self.guard.prepare(self.account, "api:fixture", flows, self.base / "api-controls")
        headers = quota_headers(now + 0.1, five=600)
        headers["anthropic-ratelimit-unified-5h-utilization"] = "0.5"
        (flows / "passive-quota.jsonl").write_text(json.dumps({
            "source": "api:fixture", "identity": main._quota_identity(self.account),
            "ts": now + 0.1, "status": 200, "headers": headers, "origin": "api",
        }) + "\n")
        old_read = threading.Event()
        release_read = threading.Event()
        update_started = threading.Event()
        update_done = threading.Event()
        original = self.guard.snapshot
        errors = []

        def snapshot(account):
            """暂停配置发布的旧窗口读取；参数为账号，返回实际快照。"""
            result = original(account)
            if threading.current_thread() is publisher:
                old_read.set()
                if not release_read.wait(5):
                    raise RuntimeError("配置发布夹具等待超时")
            return result

        def save():
            """调用真实配置接口；返回 None，并收集子线程异常。"""
            try:
                main.update_account_warmup(1, main.WarmupConfigIn(
                    cc2api_account_id=7, enabled=False, warmup_quota_5h_limit_percent=30))
            except Exception as error:
                errors.append(error)

        def consume():
            """消费实际观察文件；返回 None，并收集子线程异常。"""
            update_started.set()
            try:
                self.guard.consume(self.account)
            except Exception as error:
                errors.append(error)
            finally:
                update_done.set()

        publisher = threading.Thread(target=save, daemon=True)
        observer = threading.Thread(target=consume, daemon=True)
        with patch.object(self.guard, "snapshot", side_effect=snapshot):
            try:
                publisher.start()
                self.assertTrue(old_read.wait(5))
                observer.start()
                self.assertTrue(update_started.wait(5))
                # 旧实现让新观察先发布、旧配置后覆盖；串行发布时观察等待读取释放。
                update_done.wait(1)
            finally:
                release_read.set()
                publisher.join(5)
                if observer.ident is not None:
                    observer.join(5)
        self.assertFalse(publisher.is_alive())
        self.assertFalse(observer.is_alive())
        self.assertEqual([], errors)
        published = json.loads((self.base / "quota/1/state.json").read_text())
        self.assertEqual(50, original(self.account)["windows"]["five_hour"]["utilization"])
        self.assertEqual(50, published["windows"]["five_hour"]["utilization"])
        self.assertEqual(["five_hour"], published["warmup_quota"]["hit"])
        self.assertTrue(warmup_quota_decision(published, published["warmup_quota"]["limits"], time.time())["blocked"])

    def test_published_policy_uses_the_same_window_snapshot(self) -> None:
        """共用窗口与养号判定必须一致，不能拼接两次读取的不同事实。@return None。"""
        self._configure(30)
        self._state(quota_headers(time.time(), five=600), status=200)
        low = self.guard.snapshot(self.account)
        high = {**low, "windows": {"five_hour": {**low["windows"]["five_hour"], "utilization": 50}}}
        with patch.object(self.guard, "snapshot", side_effect=[low, high]):
            self.guard._publish(self.account)
            published = json.loads((self.base / "quota/1/state.json").read_text())
            self.assertEqual(20, published["windows"]["five_hour"]["utilization"])
            self.assertEqual([], published["warmup_quota"]["hit"])
            self.guard._publish(self.account)
            published = json.loads((self.base / "quota/1/state.json").read_text())
            self.assertEqual(50, published["windows"]["five_hour"]["utilization"])
            self.assertEqual(["five_hour"], published["warmup_quota"]["hit"])

    def test_public_policies_share_one_quota_and_configuration_snapshot(self) -> None:
        """普通任务和养号公开摘要必须基于同一窗口、阈值与许可读取。@return None。"""
        self._configure(30)
        self._state(quota_headers(time.time(), five=600), status=200)
        low = self.guard.snapshot(self.account)
        high = {
            **low,
            "windows": {
                "five_hour": {
                    **low["windows"]["five_hour"],
                    "utilization": 50,
                },
            },
        }
        with patch.object(self.guard, "snapshot", side_effect=[low, high]) as snapshot:
            policies = self.guard.policy_snapshots(self.account)
        snapshot.assert_called_once_with(self.account)
        self.assertEqual([], policies["normal"]["hit"])
        self.assertEqual([], policies["warmup"]["hit"])
        self.assertFalse(policies["normal"]["blocked"])
        self.assertFalse(policies["warmup"]["blocked"])

    def test_account_api_returns_both_policy_views_from_one_pair(self) -> None:
        """账号 API 同时返回普通任务与养号状态，不丢弃任一视图。@return None。"""
        self._configure(30)
        policies = {
            "normal": {
                "enabled": True,
                "limits": {"five_hour": 30, "seven_day": None},
                "hit": [],
                "unknown": ["five_hour"],
                "blocked": True,
                "resume_at": None,
                "message": "任务额度未知或窗口已到期，请先手动查询额度",
            },
            "warmup": {
                "enabled": True,
                "limits": {"five_hour": 30, "seven_day": None},
                "hit": [],
                "unknown": ["five_hour"],
                "blocked": False,
                "sample_used": False,
                "resume_at": None,
                "message": "养号额度未知或窗口已到期，等待一次正式请求更新",
            },
        }
        with patch.object(self.guard, "policy_snapshots", return_value=policies) as snapshots:
            account = main.list_accounts()[0]
        snapshots.assert_called_once()
        self.assertTrue(account["quota_policy"]["blocked"])
        self.assertFalse(account["warmup_quota"]["blocked"])
        self.assertNotEqual(
            account["quota_policy"]["message"],
            account["warmup_quota"]["message"],
        )

    def test_api_config_strict_validation_omission_and_null(self) -> None:
        """配置严格校验，旧客户端不清阈值，null 只关闭单个窗口。@return None。"""
        self._configure(30, 40)
        for value in (True, 30.5, "30", [], {}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                main.WarmupConfigIn(cc2api_account_id=7, warmup_quota_5h_limit_percent=value)
        for value in (0, 101, -1):
            body = main.WarmupConfigIn(cc2api_account_id=7, warmup_quota_5h_limit_percent=value)
            with self.assertRaises(main.HTTPException) as error:
                main.update_account_warmup(1, body)
            self.assertEqual(400, error.exception.status_code)
        main.update_account_warmup(1, main.WarmupConfigIn(cc2api_account_id=7))
        account = main.list_accounts()[0]
        self.assertEqual(30, account["warmup_quota_5h_limit_percent"])
        self.assertEqual(40, account["warmup_quota_7d_limit_percent"])
        main.update_account_warmup(1, main.WarmupConfigIn(cc2api_account_id=7, warmup_quota_5h_limit_percent=None))
        account = main.list_accounts()[0]
        self.assertIsNone(account["warmup_quota_5h_limit_percent"])
        self.assertEqual(40, account["warmup_quota_7d_limit_percent"])
        self.assertNotIn("admission", account["warmup_quota"])
        main.cc2api_client.resolve_credentials.assert_not_called()

    def test_unbound_account_can_save_thresholds_but_cannot_enable_warmup(self) -> None:
        """未绑定账号可保存普通任务阈值，定时养号仍须绑定。@return None。"""
        conn = main.get_db()
        try:
            with conn:
                conn.execute("UPDATE accounts SET cc2api_account_id=NULL,warmup_enabled=0 WHERE id=1")
        finally:
            conn.close()
        main.update_account_warmup(1, main.WarmupConfigIn(
            enabled=False,
            warmup_quota_5h_limit_percent=70,
            warmup_quota_7d_limit_percent=85,
        ))
        account = main.list_accounts()[0]
        self.assertIsNone(account["cc2api_account_id"])
        self.assertEqual(70, account["warmup_quota_5h_limit_percent"])
        self.assertEqual(85, account["warmup_quota_7d_limit_percent"])
        with self.assertRaises(main.HTTPException) as error:
            main.update_account_warmup(1, main.WarmupConfigIn(enabled=True))
        self.assertEqual(409, error.exception.status_code)
        self.assertIn("同步并绑定", error.exception.detail)

    def test_v3_threshold_save_notifies_both_pi_schedules(self) -> None:
        """阈值落库后通知两个空间重查，省略阈值时不改排期。:return: None。"""
        projects, warmup = Mock(spec=ProjectsService), Mock(spec=ProjectsService)
        with patch.object(main, 'projects_service', projects), patch.object(main, 'warmup_pi_service', warmup):
            main.update_account_warmup(1, main.WarmupConfigIn(warmup_quota_7d_limit_percent=90))
            connection = main.get_db()
            try:
                self.assertEqual(90, connection.execute('SELECT warmup_quota_7d_limit_percent FROM accounts WHERE id=1').fetchone()[0])
            finally:
                connection.close()
            projects.recheck_waiting.assert_called_once_with(1)
            warmup.recheck_waiting.assert_called_once_with(1)
            projects.start.assert_not_called()
            warmup.start.assert_not_called()
            projects.recheck_waiting.reset_mock()
            warmup.recheck_waiting.reset_mock()
            main.update_account_warmup(1, main.WarmupConfigIn())
            projects.recheck_waiting.assert_not_called()
            warmup.recheck_waiting.assert_not_called()

    def test_actual_start_rechecks_threshold_for_warmup_and_normal_task(self) -> None:
        """排队后新额度命中时，养号和普通任务都不创建 worker。@return None。"""
        task = self._run(kind="warmup")
        self._configure(20)
        self._state(quota_headers(time.time(), five=600), status=200)
        self.scheduler._execute("original", self.account, task)
        self.runner.start_run.assert_not_called()
        run = main.get_run("original")
        self.assertEqual("quota_wait", run["status"])
        self.assertIn("阈值", run["error"])
        self.assertFalse(self.guard.snapshot(self.account)["blocked"])
        normal = self._run("normal")
        with patch.object(main, "_sync_bound_account_credentials_locked"):
            self.scheduler._execute("normal", self.account, normal)
        self.assertEqual("quota_wait", main.get_run("normal")["status"])
        self.assertIn("任务阈值", main.get_run("normal")["error"])
        self.runner.start_run.assert_not_called()

    def test_normal_task_unknown_waits_without_using_warmup_sample(self) -> None:
        """普通任务额度未知时直接等待，不领取养号正式请求机会。@return None。"""
        task = self._run()
        self._configure(30)
        self.scheduler._execute("original", self.account, task)
        run = main.get_run("original")
        self.assertEqual("quota_wait", run["status"])
        self.assertIn("手动查询额度", run["error"])
        conn = main.get_db()
        try:
            self.assertEqual(0, conn.execute(
                "SELECT COUNT(*) FROM warmup_quota_admissions"
            ).fetchone()[0])
        finally:
            conn.close()
        self.runner.start_run.assert_not_called()
        main.cc2api_client.refresh_usage.assert_not_called()

    def test_normal_task_known_below_threshold_runs_and_running_task_finishes(self) -> None:
        """可信低用量允许启动；运行中命中阈值时本次仍正常完成。@return None。"""
        task = self._run()
        self._configure(30)
        self._state(quota_headers(time.time(), five=600), status=200)

        def reach_threshold(_worker):
            """模拟 worker 运行期间额度升到阈值；返回正常退出码。"""
            headers = quota_headers(time.time(), five=600)
            headers["anthropic-ratelimit-unified-5h-utilization"] = "0.3"
            self._state(headers, status=200)
            return 0

        self.runner.wait_worker.side_effect = reach_threshold
        with patch.object(main, "_sync_bound_account_credentials_locked"):
            self.scheduler._execute("original", self.account, task)
        self.assertEqual("success", main.get_run("original")["status"])
        self.runner.start_run.assert_called_once()
        self.assertTrue(self.guard.policy_snapshot(self.account, "normal")["blocked"])

    def test_normal_wait_resumes_same_run_after_manual_quota_update(self) -> None:
        """手动额度事实变低后恢复原普通 run、prompt 和执行快照。@return None。"""
        self._run(status="quota_wait")
        self._configure(30)
        with patch.object(self.scheduler, "submit") as submit:
            self.guard._resume_account(self.account)
        submit.assert_not_called()
        self._state(quota_headers(time.time(), five=600), status=200)
        with patch.object(self.scheduler, "submit") as submit:
            self.guard._resume_account(self.account)
        run_id, _, payload = submit.call_args.args
        self.assertEqual("original", run_id)
        self.assertEqual("保持原 prompt", payload["prompt"])
        self.assertEqual("2.1.62", payload["claude_code_version"])
        self.assertEqual("high", payload["claude_effort_level"])
        self.assertEqual(1, main.get_run("original")["quota_attempt"])

    def test_normal_wait_resumes_after_threshold_is_disabled(self) -> None:
        """关闭账号阈值后，未知额度的原普通 run 应恢复。@return None。"""
        self._run(status="quota_wait")
        self._configure(30)
        with patch.object(self.scheduler, "submit") as submit:
            self.guard._resume_account(self.account)
        submit.assert_not_called()
        self._configure(None)
        with patch.object(self.scheduler, "submit") as submit:
            self.guard._resume_account(self.account)
        self.assertEqual("original", submit.call_args.args[0])
        self.assertEqual(1, main.get_run("original")["quota_attempt"])

    def test_batch_waits_before_creating_item_when_policy_blocks(self) -> None:
        """批次在阈值命中时不创建下一条 task/run，并进入额度等待。@return None。"""
        self._configure(20)
        self._state(quota_headers(time.time(), five=600), status=200)
        conn = main.get_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO task_batches(id,account_id,name,status,concurrency,timeout_sec) "
                    "VALUES(1,1,'批次','active',1,1800)"
                )
                conn.execute(
                    "INSERT INTO task_batch_items(batch_id,topic_id,prompt,status) "
                    "VALUES(1,1,'保持原 prompt','pending')"
                )
            before = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        finally:
            conn.close()
        self.scheduler._execute_batch(1)
        conn = main.get_db()
        try:
            self.assertEqual("quota_wait", conn.execute(
                "SELECT status FROM task_batches WHERE id=1"
            ).fetchone()[0])
            self.assertEqual(before, conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
            self.assertEqual("pending", conn.execute(
                "SELECT status FROM task_batch_items WHERE batch_id=1"
            ).fetchone()[0])
        finally:
            conn.close()

    def test_private_control_does_not_poison_shared_quota(self) -> None:
        """Recorder 的阈值暂停保留真实低用量，不制造 unknown 耗尽。@return None。"""
        self._run(kind="warmup")
        self._configure(20)
        source = "run:original:0"
        payload = {"source": source, "status": "quota_wait", "warmup_wait": True,
                   "quota_state": {}, "exhausted": [], "error": "养号阈值等待"}
        control = main._quota_control("original", source)
        control.mkdir(parents=True)
        (control / "pause.json").write_text(json.dumps(payload))
        self.guard.record_control_state(self.account, source, payload)
        self.assertFalse(self.guard.snapshot(self.account)["blocked"])
        self.assertEqual([], self.guard.snapshot(self.account)["exhausted"])

    def test_regular_run_cannot_forge_warmup_control(self) -> None:
        """普通作业伪造养号标记仍走既有额度补证。@return None。"""
        self._run()
        self.guard.record_control_state(self.account, "run:original:0", {
            "source": "run:original:0", "status": "quota_wait", "warmup_wait": True})
        self.assertTrue(self.guard.snapshot(self.account)["blocked"])

    def test_waiting_run_resumes_original_snapshot_after_real_data(self) -> None:
        """单次未知仍等待，真实低额度到来后恢复原 run 及模型快照。@return None。"""
        self._run(kind="warmup", status="quota_wait")
        self._configure(30)
        self.assertTrue(self.guard.admit(self.account, "run:original:0", warmup=True))
        self.guard._resume_account(self.account)
        self.assertEqual(0, main.get_run("original")["quota_attempt"])
        self._state(quota_headers(time.time(), five=600), status=200)
        with patch.object(self.scheduler, "submit") as submit:
            self.guard._resume_account(self.account)
        self.assertEqual("original", submit.call_args.args[0])
        self.assertEqual("2.1.62", submit.call_args.args[2]["claude_code_version"])
        self.assertEqual("high", submit.call_args.args[2]["claude_effort_level"])
        self.assertEqual(1, main.get_run("original")["quota_attempt"])

    def test_restart_keeps_interrupted_warmup_and_used_opportunity(self) -> None:
        """认领后崩溃仍保留原 run，不能重启再发未知请求。@return None。"""
        self._run(kind="warmup")
        self._configure(30)
        self.assertTrue(self.guard.admit(self.account, "run:original:0", warmup=True))
        self.guard.recover()
        self.assertEqual("quota_wait", main.get_run("original")["status"])
        with patch.object(self.scheduler, "submit") as submit:
            self.guard._resume_account(self.account)
        submit.assert_not_called()
        self.assertEqual(0, main.get_run("original")["quota_attempt"])

    def test_timer_immediate_and_expired_wait_do_not_loop(self) -> None:
        """定时与立即运行都拒绝已用未知机会，无原 run 的等待也不反复排入。@return None。"""
        self._configure(30)
        self.assertTrue(self.guard.admit(self.account, "run:first:0", warmup=True))
        warmup = main.WarmupScheduler(Mock())
        self.assertFalse(warmup.trigger_account(1)["started"])
        self.guard._resume_account(self.account)
        conn = main.get_db()
        try:
            account = dict(conn.execute("SELECT * FROM accounts WHERE id=1").fetchone())
            self.assertIsNone(account["warmup_next_run_at"])
            self.assertEqual("quota_wait", account["warmup_last_status"])
            self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
        finally:
            conn.close()

    def test_new_cycle_and_other_account_have_independent_opportunities(self) -> None:
        """窗口真实到期只给一次新机会，其他账号具有独立许可。@return None。"""
        self._configure(30)
        now = time.time()
        self.guard._observe(self.account, main._quota_identity(self.account), {
            "windows": {"five_hour": {"utilization": 20, "reset_at": now + 10}}, "observed_at": now})
        with patch.object(main.time, "time", return_value=now + 11):
            self.assertTrue(self.guard.admit(self.account, "run:cycle:0", warmup=True))
            self.assertFalse(self.guard.admit(self.account, "run:duplicate:0", warmup=True))
        conn = main.get_db()
        try:
            with conn:
                conn.execute("INSERT INTO accounts(id,name,profile_path,enabled,warmup_enabled,cc2api_account_id,"
                             "warmup_quota_5h_limit_percent) VALUES(2,'other','profiles/other',1,1,8,30)")
            other = dict(conn.execute("SELECT * FROM accounts WHERE id=2").fetchone())
        finally:
            conn.close()
        self.assertTrue(self.guard.admit(other, "run:other:0", warmup=True))

    def test_stopped_and_disabled_warmup_cannot_resume(self) -> None:
        """真实额度下降不能复活用户关闭或停止的养号。@return None。"""
        self._run(kind="warmup", status="quota_wait")
        self._configure(30)
        self._state(quota_headers(time.time(), five=600), status=200)
        conn = main.get_db()
        try:
            with conn:
                conn.execute("UPDATE accounts SET warmup_enabled=0 WHERE id=1")
            with patch.object(self.scheduler, "submit") as submit:
                self.guard._resume_account(self.account)
            submit.assert_not_called()
            with conn:
                conn.execute("UPDATE accounts SET warmup_enabled=1 WHERE id=1")
                conn.execute("UPDATE runs SET status='stopped',stop_requested_at=? WHERE id='original'", (time.time(),))
            with patch.object(self.scheduler, "submit") as submit:
                self.guard._resume_account(self.account)
            submit.assert_not_called()
        finally:
            conn.close()

    def test_identity_change_cannot_reuse_old_waiting_run(self) -> None:
        """新身份可有自己的机会，但旧 run 不能在新身份自动执行。@return None。"""
        self._run(kind="warmup", status="quota_wait")
        self._configure(30)
        conn = main.get_db()
        try:
            with conn:
                conn.execute("UPDATE runs SET quota_identity='old-identity' WHERE id='original'")
        finally:
            conn.close()
        with patch.object(self.scheduler, "submit") as submit:
            self.guard._resume_account(self.account)
        submit.assert_not_called()
        self.assertEqual("auth_failed", main.get_run("original")["status"])

    def test_old_database_upgrade_preserves_values_and_is_idempotent(self) -> None:
        """旧库两次升级保留原账号与设置，新增阈值默认关闭。@return None。"""
        with patch.object(main, "DB_PATH", self.base / "legacy.sqlite"):
            conn = main.get_db()
            try:
                with conn:
                    conn.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY,name TEXT UNIQUE,profile_path TEXT,enabled INTEGER)")
                    conn.execute("INSERT INTO accounts VALUES(9,'legacy','profiles/legacy',1)")
                    conn.execute("CREATE TABLE app_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at REAL)")
                    conn.execute("INSERT INTO app_settings VALUES('claude_effort_level','xhigh',1)")
            finally:
                conn.close()
            main.init_db()
            main.init_db()
            conn = main.get_db()
            try:
                row = conn.execute("SELECT * FROM accounts WHERE id=9").fetchone()
                self.assertEqual("legacy", row["name"])
                self.assertIsNone(row["warmup_quota_5h_limit_percent"])
                self.assertIsNone(row["warmup_quota_7d_limit_percent"])
                self.assertEqual("xhigh", conn.execute("SELECT value FROM app_settings").fetchone()[0])
                self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM warmup_quota_admissions").fetchone()[0])
            finally:
                conn.close()

    def test_worker_private_draining_and_pause_sources(self) -> None:
        """实际 shell 只认当前来源的收尾/暂停信号，保留暂停原因。@return None。"""
        script = (Path(__file__).resolve().parents[1] / "images/worker/entrypoint.sh").read_text()
        functions = script[script.index("check_quota_pause() {"):script.index("detect_claude_auth_error() {")]
        status_file = self.base / "worker-status.json"
        functions = functions.replace("/workspace/.bench-status.json", str(status_file))
        control = self.base / "pause.json"
        draining = self.base / "warmup-draining.json"
        env = {**os.environ, "QUOTA_SOURCE": "run:worker:0", "QUOTA_SIGNAL_FILE": str(control), "QUOTA_WARMUP": "1"}
        draining.write_text(json.dumps({"source": "run:older:0", "status": "draining"}))
        self.assertNotEqual(0, subprocess.run(["bash", "-c", functions + "\ncheck_warmup_draining"], env=env).returncode)
        draining.write_text(json.dumps({"source": "run:worker:0", "status": "draining"}))
        self.assertEqual(0, subprocess.run(["bash", "-c", functions + "\ncheck_warmup_draining"], env=env).returncode)
        self.assertNotEqual(0, subprocess.run(["bash", "-c", functions + "\ncheck_warmup_draining"], env={**env, "QUOTA_WARMUP": "0"}).returncode)
        payload = {"source": "run:worker:0", "status": "quota_wait", "warmup_wait": True, "error": "阈值等待"}
        control.write_text(json.dumps(payload))
        self.assertEqual(0, subprocess.run(["bash", "-c", functions + "\ncheck_quota_pause"], env=env).returncode)
        self.assertEqual(payload, json.loads(status_file.read_text()))


if __name__ == "__main__":
    unittest.main()
