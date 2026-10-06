"""被动额度门禁、同题恢复和 worker 合成错误的行为回归。"""

import json
import asyncio
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import main
from quota_protocol import merge_quota_observation, quota_decision, quota_observation, quota_timestamp


def quota_headers(now, five=None, seven=None, rejected=False):
    """构造脱敏响应头；参数为观察时间、窗口延迟及拒绝标记，返回头字典。"""
    headers = {}
    for name, delay in (("5h", five), ("7d", seven)):
        if delay is not None:
            headers[f"anthropic-ratelimit-unified-{name}-utilization"] = "1" if rejected else "0.2"
            headers[f"anthropic-ratelimit-unified-{name}-reset"] = str(now + delay)
            headers[f"anthropic-ratelimit-unified-{name}-status"] = "rejected" if rejected else "allowed"
    return headers


class QuotaProtocolTests(unittest.TestCase):
    """验证响应事实的解析与窗口合并。"""

    def test_unknown_and_rpm_429_do_not_invent_quota(self) -> None:
        """无额度头和普通 RPM 429 不猜测通用窗口，返回 None。"""
        for status in (200, 429, 401, 402):
            state = quota_observation({"retry-after": "60"}, status, time.time())
            self.assertFalse(quota_decision(state, time.time())["blocked"])
            self.assertEqual({}, state["windows"])

    def test_both_windows_wait_for_latest_reset(self) -> None:
        """较早窗口到期不能放行，返回 None。"""
        now = time.time()
        state = quota_observation(quota_headers(now, 100, 1000, True), 429, now)
        decision = quota_decision(state, now + 200)
        self.assertTrue(decision["blocked"])
        self.assertEqual(now + 1000, decision["resume_at"])
        self.assertTrue(quota_decision(state, now + 1001)["retry_ready"])

    def test_rejected_without_reset_retains_future_prior_reset(self) -> None:
        """拒绝补证不清空已有可信 reset，返回 None。"""
        now = time.time()
        old = quota_observation(quota_headers(now, 600), 200, now)
        new = quota_observation({"anthropic-ratelimit-unified-5h-status": "rejected"}, 429, now + 1)
        merged = merge_quota_observation(old, new)
        self.assertEqual(now + 600, quota_decision(merged, now + 1)["resume_at"])
        missing = quota_decision(new, now + 1)
        self.assertTrue(missing["blocked"])
        self.assertIsNone(missing["resume_at"])

    def test_partial_allowed_429_and_out_of_order(self) -> None:
        """窗口允许事实优先，高位其它窗口不误停；旧观察不清新拒绝。"""
        now = time.time()
        headers = quota_headers(now, 300, 600, True)
        headers["anthropic-ratelimit-unified-7d-status"] = "allowed"
        state = quota_observation(headers, 429, now)
        self.assertEqual(["five_hour"], quota_decision(state, now)["exhausted"])
        old = quota_observation(quota_headers(now - 1, 300), 200, now - 1)
        self.assertTrue(merge_quota_observation(state, old)["windows"]["five_hour"]["exhausted"])
        partial = quota_observation(quota_headers(now + 1, seven=100), 200, now + 1)
        self.assertTrue(merge_quota_observation(state, partial)["windows"]["five_hour"]["exhausted"])

    def test_invalid_headers_and_time_units(self) -> None:
        """非法数值不形成完整窗口，毫秒及带时区时间正常解析。"""
        now = time.time()
        for value in ("NaN", "inf", "-1", "错误"):
            headers = quota_headers(now, 100)
            headers["anthropic-ratelimit-unified-5h-utilization"] = value
            self.assertEqual({}, quota_observation(headers, 200, now)["windows"])
        self.assertEqual(1700000000, quota_timestamp(1700000000000))
        self.assertEqual(1700000000, quota_timestamp("2023-11-14T22:13:20Z"))
        self.assertIsNone(quota_timestamp("2023-11-14T22:13:20"))
        headers = quota_headers(now, 7 * 3600)
        self.assertEqual({}, quota_observation(headers, 200, now)["windows"])

    def test_rollover_and_model_window(self) -> None:
        """跨周期成功排除高位残留，模型专属窗口不阻断通用额度。"""
        now = time.time()
        old = quota_observation(quota_headers(now, 100, rejected=True), 429, now)
        headers = quota_headers(now + 101, 100)
        headers["anthropic-ratelimit-unified-5h-utilization"] = "1"
        new = quota_observation(headers, 200, now + 101)
        merged = merge_quota_observation(old, new)
        self.assertFalse(quota_decision(merged, now + 101)["blocked"])
        state = quota_observation({"anthropic-ratelimit-unified-7d_oi-status": "rejected"}, 429, now)
        self.assertFalse(quota_decision(state, now)["blocked"])

    def test_build_copy_matches_canonical_protocol(self) -> None:
        """独立 sidecar 构建上下文的协议副本不得漂移。"""
        root = Path(__file__).resolve().parents[1]
        self.assertEqual((root / "orchestrator/quota_protocol.py").read_bytes(),
                         (root / "images/sidecar/quota_protocol.py").read_bytes())

    def test_cached_window_uses_its_own_observation_time(self) -> None:
        """另一个窗口的新样本不能给缓存里的旧允许事实赋新时间。"""
        now = time.time()
        local = quota_observation(quota_headers(now, 300), 200, now)
        local = merge_quota_observation(local, quota_observation(quota_headers(now + 20, seven=300), 200, now + 20))
        shared = quota_observation(quota_headers(now + 10, 300, rejected=True), 429, now + 10)
        merged = merge_quota_observation(shared, local)
        self.assertTrue(merged["windows"]["five_hour"]["exhausted"])
        self.assertEqual(now + 10, merged["windows"]["five_hour"]["observed_at"])


    def test_same_time_allowance_does_not_clear_rejection(self) -> None:
        """并发同时间样本先保留拒绝，后续真实允许才可解除。"""
        now = time.time()
        denied = quota_observation(quota_headers(now, 600, rejected=True), 429, now)
        allowed = quota_observation(quota_headers(now, 600), 200, now)
        for first, second in ((denied, allowed), (allowed, denied)):
            self.assertTrue(merge_quota_observation(first, second)["windows"]["five_hour"]["rejected"])


class QuotaGuardTests(unittest.TestCase):
    """用独立 SQLite 和容器替身验证实际入口与恢复。"""

    def setUp(self) -> None:
        """准备临时数据与禁止主动 usage 的运行器，返回 None。"""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        for name, value in {"BENCH_DATA": self.base, "HOST_BENCH_DATA": self.base,
                            "DB_PATH": self.base / "db.sqlite", "PROFILES_DIR": self.base / "profiles",
                            "WORKSPACES_DIR": self.base / "workspaces", "FLOWS_DIR": self.base / "flows",
                            "CA_DIR": self.base / "ca", "TOPICS_FILE": self.base / "missing.md",
                            "warmup_scheduler": None, "continue_manager": None, "login_manager": None}.items():
            patcher = patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        main.init_db()
        self.runner = Mock()
        self.runner.start_run.return_value = ("sidecar", "worker")
        self.runner.wait_worker.return_value = 0
        self.runner.read_worker_status.return_value = {}
        self.runner.query_quota.side_effect = AssertionError("自动路径禁止主动查询")
        self.guard = main.QuotaGuard(self.runner)
        self.scheduler = main.Scheduler(self.runner)
        for name, value in (("quota_guard", self.guard), ("scheduler", self.scheduler), ("runner", self.runner)):
            patcher = patch.object(main, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        client = Mock()
        client.refresh_usage.side_effect = AssertionError("自动路径禁止 cc2api usage 刷新")
        patcher = patch.object(main, "cc2api_client", client)
        patcher.start()
        self.addCleanup(patcher.stop)
        conn = main.get_db()
        with conn:
            conn.execute("INSERT INTO accounts(id,name,profile_path,enabled) VALUES(1,'fixture','fixture',1)")
            conn.execute("INSERT INTO topics(id,no,title,description) VALUES(1,1,'原题','原始描述')")
        self.account = dict(conn.execute("SELECT * FROM accounts WHERE id=1").fetchone())
        conn.close()
        profile = main.PROFILES_DIR / "fixture"
        profile.mkdir(parents=True)
        (profile / ".claude.json").write_text(json.dumps({"oauthAccount": {"accountUuid": "脱敏身份", "organizationUuid": "组织"}}))
        (profile / ".credentials.json").write_text(json.dumps({"claudeAiOauth": {"accessToken": "测试替身AT", "refreshToken": "测试替身RT"}}))

    def _run(self, rid="original", kind="normal", batch=False, status="queued"):
        conn = main.get_db()
        with conn:
            if batch:
                conn.execute("INSERT OR IGNORE INTO task_batches(id,account_id,name,concurrency,timeout_sec) VALUES(1,1,'批次',1,1800)")
            task_id = conn.execute("INSERT INTO tasks(topic_no,title,prompt,account_id,batch_id,timeout_sec) VALUES(1,'原题','保持原 prompt',1,?,1800)", (1 if batch else None,)).lastrowid
            conn.execute("INSERT INTO runs(id,task_id,account_id,batch_id,topic_id,run_kind,status,claude_code_version,claude_effort_level) VALUES(?,?,1,?,1,?,?,'2.1.62','high')", (rid, task_id, 1 if batch else None, kind, status))
            if batch:
                conn.execute("INSERT INTO task_batch_items(batch_id,topic_id,task_id,run_id,prompt,status) VALUES(1,1,?,?,'保持原 prompt',?)", (task_id, rid, status))
            if kind == "warmup":
                conn.execute("UPDATE accounts SET warmup_enabled=1,cc2api_account_id=7,warmup_last_run_id=? WHERE id=1", (rid,))
                self.account = dict(conn.execute("SELECT * FROM accounts WHERE id=1").fetchone())
        conn.close()
        return {"id": task_id, "prompt": "保持原 prompt", "timeout_sec": 1800,
                "claude_code_version": "2.1.62", "claude_effort_level": "high", "capture_full_http": kind == "capture"}

    def _state(self, headers, now=None, status=429):
        now = now or time.time()
        self.guard._observe(self.account, main._quota_identity(self.account), quota_observation(headers, status, now))

    def _expire(self):
        conn = main.get_db()
        row = conn.execute("SELECT state_json FROM account_quota_states WHERE account_id=1").fetchone()
        state = json.loads(row["state_json"])
        for window in state.get("windows", {}).values():
            window["reset_at"] = time.time() - 1
        with conn:
            conn.execute("UPDATE account_quota_states SET state_json=? WHERE account_id=1", (json.dumps(state),))
            conn.execute("UPDATE runs SET quota_resume_at=? WHERE status='quota_wait'", (time.time() - 1,))
        conn.close()
        self.guard._publish(self.account)

    def test_unknown_account_runs_normally_without_usage(self) -> None:
        """首次未知账号允许既有正常运行，返回 None。"""
        task = self._run()
        self.scheduler._execute("original", self.account, task)
        self.assertEqual("success", main.get_run("original")["status"])
        self.runner.start_run.assert_called_once()
        self.assertFalse(main.list_accounts()[0]["passive_quota"]["known"])

    def test_control_fallback_keeps_reset_and_hold_without_observation_log(self) -> None:
        """独立控制补证保留真实 reset；封号不会转成自动额度恢复。"""
        now = time.time()
        source = "run:original:0"
        state = quota_observation(quota_headers(now, 600, rejected=True), 429, now)
        payload = {"source": source, "status": "quota_wait", "quota_state": state}
        self.guard.record_control_state(self.account, "旧来源", payload)
        self.assertFalse(self.guard.snapshot(self.account)["blocked"])
        self.guard.record_control_state(self.account, source, payload)
        self.assertEqual(now + 600, self.guard.snapshot(self.account)["resume_at"])
        self.guard.record_control_state(self.account, source, {
            **payload, "quota_state": {"account_error": "account_on_hold"}})
        snapshot = self.guard.snapshot(self.account)
        self.assertEqual("account_on_hold", snapshot["account_error"])
        self.assertTrue(snapshot["blocked"])
        self.assertFalse(snapshot["retry_ready"])
        self.assertIsNone(snapshot["resume_at"])

    def test_continue_control_blocks_input_before_background_consumption(self) -> None:
        """控制文件先到时直接拒绝输入，异常文件关闭会话且不复活。"""
        self._run(status="success")
        self.runner.start_continue.return_value = ("sidecar", "worker")
        manager = main.ContinueManager(self.runner)
        with patch.object(main, "_find_latest_claude_session_id", return_value="original-session"):
            session = manager.start(main.get_run("original"), self.account)
        source = f"continue:{session.sid}:0"
        path = main._quota_control("original", source) / "pause.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        path.write_text(json.dumps({"source": source, "status": "quota_wait",
            "quota_state": quota_observation(quota_headers(now, 600, rejected=True), 429, now)}))
        raw = Mock()
        self.assertFalse(manager.send_input(session, 0, raw, "拒绝此次输入".encode()))
        raw.send.assert_not_called()
        self.assertEqual("quota_wait", session.status)
        self.assertEqual(now + 600, self.guard.snapshot(self.account)["resume_at"])
        self._expire()
        session.connected = True
        manager.quota_tick(self.account)
        self.assertEqual("running", session.status)
        source = f"continue:{session.sid}:{session.generation}"
        path = main._quota_control("original", source) / "pause.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]")
        self.assertFalse(manager.send_input(session, session.generation, raw, "仍不发送".encode()))
        self.assertEqual("closed", session.status)
        before = self.runner.start_continue.call_count
        manager.quota_tick(self.account)
        self.assertEqual(before, self.runner.start_continue.call_count)

    def test_single_batch_rerun_capture_and_warmup_share_start_guard(self) -> None:
        """不同 run 来源共用启动前门禁，阻断时不创建 worker。"""
        for rid, kind, batch in (("single", "normal", False), ("again", "normal", False),
                                 ("batch", "normal", True), ("capture", "capture", False)):
            with self.subTest(rid=rid):
                task = self._run(rid, kind, batch)
                self._state(quota_headers(time.time(), 600, 1000, True))
                self.scheduler._execute(rid, self.account, task)
                self.assertEqual("quota_wait", main.get_run(rid)["status"])
        task = self._run("warmup", "warmup")
        self._state(quota_headers(time.time(), 600, rejected=True))
        self.scheduler._execute("warmup", self.account, task)
        self.assertEqual("quota_wait", main.get_run("warmup")["status"])
        self.runner.start_run.assert_not_called()
        self.assertEqual(0, main.list_task_batches()[0]["done_count"])

    def test_quota_change_while_waiting_for_semaphore_is_rechecked(self) -> None:
        """排队期间新拒绝仍阻断真实启动。"""
        task = self._run()
        sem = Mock()
        sem.acquire.side_effect = lambda: self._state(quota_headers(time.time(), 600, rejected=True))
        with patch.object(self.scheduler, "_sem", return_value=sem):
            self.scheduler._execute("original", self.account, task)
        self.runner.start_run.assert_not_called()
        self.assertEqual("quota_wait", main.get_run("original")["status"])

    def test_runtime_quota_wins_exit_zero_and_keeps_same_run(self) -> None:
        """额度状态优先于历史错误退出码 0，恢复原 run/会话及快照。"""
        task = self._run(batch=True)
        self.runner.read_worker_status.return_value = {"status": "quota_wait", "error": "被动识别额度耗尽:five_hour"}
        self.scheduler._execute("original", self.account, task)
        self.assertEqual("quota_wait", main.get_run("original")["status"])
        self.assertEqual(0, main.list_task_batches()[0]["done_count"])
        # 合成错误无 reset 时即使多次 tick 也不探测、不建新题。
        before = self.runner.start_run.call_count
        self.guard.tick()
        self.guard.tick()
        self.assertEqual(before, self.runner.start_run.call_count)
        session = main.WORKSPACES_DIR / "original/.claude-home/projects/-workspace/same-session.jsonl"
        session.parent.mkdir(parents=True)
        session.write_text('{"message":{"role":"assistant"}}\n')
        self._expire()
        self.scheduler.submit = Mock()
        self.guard.tick()
        rid, account, payload = self.scheduler.submit.call_args.args
        self.assertEqual("original", rid)
        self.assertEqual(task["id"], payload["id"])
        self.assertEqual("保持原 prompt", payload["prompt"])
        self.assertEqual("high", payload["claude_effort_level"])
        self.assertEqual(1, payload["quota_attempt"])
        self.runner.read_worker_status.return_value = {}
        # 真实成功响应解除恢复认领，其它等待才可运行。
        def successful_response(_worker):
            self._state(quota_headers(time.time(), 600, 1000), status=200)
            return 0
        self.runner.wait_worker.side_effect = successful_response
        self.scheduler._execute(rid, account, payload)
        self.assertEqual("same-session", self.runner.start_run.call_args.args[2]["resume_session_id"])
        self.assertEqual(main.get_run(rid)["execution_model"], self.runner.start_run.call_args.args[2]["model_override"])
        self.assertEqual("success", main.get_run(rid)["status"])
        conn = main.get_db()
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
        conn.close()

    def test_due_recovery_claim_is_one_account_wide(self) -> None:
        """两个等待任务仅认领一份正常执行，返回 None。"""
        for rid in ("first", "second"):
            self._run(rid, status="quota_wait")
        now = time.time() - 100
        self._state(quota_headers(now, 1, rejected=True), now)
        self.scheduler.submit = Mock()
        self.guard.tick()
        self.guard.tick()
        self.scheduler.submit.assert_called_once()
        self.assertEqual("quota_wait", main.get_run("second")["status"])

    def test_pause_stop_disable_and_deleted_task_prevent_resume(self) -> None:
        """用户取消优先于到期自动恢复，返回 None。"""
        self._run(batch=True, status="quota_wait")
        now = time.time() - 100
        self._state(quota_headers(now, 1, rejected=True), now)
        main.pause_task_batch(1)
        self.scheduler.submit = Mock()
        self.guard.tick()
        self.scheduler.submit.assert_not_called()
        self.assertEqual("stopped", main.get_run("original")["status"])
        self._run("stoppable", status="quota_wait")
        main.stop_run("stoppable")
        self.guard.tick()
        self.assertEqual("stopped", main.get_run("stoppable")["status"])
        self._run("deleted-parent", status="quota_wait")
        conn = main.get_db()
        with conn:
            conn.execute("UPDATE tasks SET deleted_at=? WHERE id=(SELECT task_id FROM runs WHERE id='deleted-parent')", (time.time(),))
        conn.close()
        self.guard.tick()
        self.scheduler.submit.assert_not_called()

    def test_disabled_account_waits_while_other_account_runs_normally(self) -> None:
        """账号门禁互相隔离，停用账号的到期任务也不恢复。"""
        self._run(status='quota_wait')
        self._state(quota_headers(time.time(), 600, rejected=True))
        other_task = self._run('other-account-run')
        conn = main.get_db()
        with conn:
            conn.execute("INSERT INTO accounts(id,name,profile_path,enabled) VALUES(2,'another','another',1)")
            conn.execute("UPDATE tasks SET account_id=2 WHERE id=?", (other_task['id'],))
            conn.execute("UPDATE runs SET account_id=2 WHERE id='other-account-run'")
        other_account = dict(conn.execute('SELECT * FROM accounts WHERE id=2').fetchone())
        conn.close()
        self.scheduler._execute('other-account-run', other_account, other_task)
        self.assertEqual('success', main.get_run('other-account-run')['status'])
        self.assertEqual('quota_wait', main.get_run('original')['status'])
        self._expire()
        conn = main.get_db()
        with conn:
            conn.execute('UPDATE accounts SET enabled=0 WHERE id=1')
        conn.close()
        self.scheduler.submit = Mock()
        self.guard.tick()
        self.scheduler.submit.assert_not_called()
        self.assertEqual('quota_wait', main.get_run('original')['status'])

    def test_cursor_half_line_rotation_identity_and_no_secret_log(self) -> None:
        """部分行、身份和游标重启正确，日志不含凭据明文。"""
        flow_dir = main.FLOWS_DIR / "fixture/1/original"
        self.guard.prepare(self.account, "run:original:0", flow_dir, self.base / "control")
        path = flow_dir / "passive-quota.jsonl"
        now = time.time()
        event = {"source": "run:original:0", "identity": main._quota_identity(self.account),
                 "ts": now, "status": 429, "headers": quota_headers(now, 600, rejected=True)}
        serialized = json.dumps(event)
        path.write_text(serialized)
        self.guard.consume(self.account)
        self.assertFalse(self.guard.snapshot(self.account)["known"])
        with path.open("a") as handle:
            handle.write("\n")
        self.guard.consume(self.account)
        self.assertTrue(self.guard.snapshot(self.account)["blocked"])
        main.QuotaGuard(self.runner).consume(self.account)
        self.assertTrue(self.guard.snapshot(self.account)["blocked"])
        path.unlink()
        event.update(ts=now - 1, status=200, headers=quota_headers(now - 1, 300))
        path.write_text(json.dumps(event) + "\n")
        self.guard.consume(self.account)
        self.assertTrue(self.guard.snapshot(self.account)["blocked"])
        public = json.dumps(main.list_accounts())
        shared = (self.base / "quota/1/state.json").read_text()
        for secret in ("测试替身AT", "测试替身RT", "token_hashes", "脱敏身份"):
            self.assertNotIn(secret, public)
        self.assertNotIn("测试替身AT", shared)
        # 切换绑定使旧身份观察失效，不把旧额度套到新账号。
        changed = {**self.account, "cc2api_account_id": 9}
        self.assertFalse(self.guard.snapshot(changed)["known"])

    def test_restart_cleans_old_worker_before_restoring_wait(self) -> None:
        """崩溃遗留运行收口为等待，清理失败不启用恢复。"""
        self._run(status="running")
        self._state(quota_headers(time.time(), 600, rejected=True))
        self.guard.recover()
        self.runner.cleanup_quota_run.assert_called_with("original")
        self.assertEqual("quota_wait", main.get_run("original")["status"])
        self.runner.cleanup_quota_run.side_effect = RuntimeError("Docker 暂不可用")
        with self.assertRaises(RuntimeError):
            self.guard.recover()

    def test_restart_recovers_control_when_observation_log_was_not_written(self) -> None:
        """日志未落盘即崩溃时，控制补证仍让原 run 等待而不提前投放。"""
        self._run(status="running")
        source = main._quota_source("original", 0)
        path = main._quota_control("original", source) / "pause.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        path.write_text(json.dumps({"source": source, "status": "quota_wait",
            "quota_state": quota_observation(quota_headers(now, 600, rejected=True), 429, now)}))
        self.guard.recover()
        self.assertEqual("quota_wait", main.get_run("original")["status"])
        self.assertEqual(now + 600, self.guard.snapshot(self.account)["resume_at"])
        self.scheduler.submit = Mock()
        self.guard.tick()
        self.scheduler.submit.assert_not_called()
        path.write_text(json.dumps({"source": source, "status": "quota_wait",
            "quota_state": {"account_error": "account_on_hold"}}))
        self.guard.recover()
        self.assertEqual("auth_failed", main.get_run("original")["status"])
        self.assertFalse(self.guard.snapshot(self.account)["retry_ready"])

    def test_restart_with_failed_control_does_not_resume_waiting_run(self) -> None:
        """已等待执行的控制文件损坏时按失败收口，不重新创建 worker。"""
        self._run(status="quota_wait")
        source = main._quota_source("original", 0)
        path = main._quota_control("original", source) / "pause.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]")
        self.guard.recover()
        self.assertEqual("failed", main.get_run("original")["status"])
        self.scheduler.submit = Mock()
        self.guard.tick()
        self.scheduler.submit.assert_not_called()

    def test_runner_keeps_empty_frozen_model_after_global_setting_change(self) -> None:
        """空模型快照表示沿用 Claude 默认，恢复时不能读取新的全局覆盖。"""
        task = self._run()
        containers = Mock()
        containers.run.side_effect = [Mock(id="sidecar"), Mock(id="worker")]
        client = Mock(containers=containers)
        with patch.object(main.docker, "from_env", return_value=client), \
                patch.object(main, "_wait_sidecar_ready"), \
                patch.object(main, "effective_runtime_model", return_value="后来设置的模型") as current:
            actual_runner = main.Runner()
            actual_runner.start_run("original", self.account, {**task, "model_override": ""})
        environment = containers.run.call_args_list[-1].kwargs["environment"]
        self.assertNotIn("CLAUDE_MODEL_OVERRIDE", environment)
        current.assert_not_called()

    def test_warmup_known_block_does_not_select_topic_or_sync(self) -> None:
        """等待扫描不产生重复题目和主动凭据动作。"""
        conn = main.get_db()
        with conn:
            conn.execute("UPDATE accounts SET cc2api_account_id=7,warmup_enabled=1,warmup_next_run_at=0 WHERE id=1")
        self.account = dict(conn.execute("SELECT * FROM accounts WHERE id=1").fetchone())
        conn.close()
        self._state(quota_headers(time.time(), 600, rejected=True))
        warmup = main.WarmupScheduler(self.scheduler)
        with patch.object(warmup, "_select_topic") as choose, patch.object(main, "_sync_bound_account_credentials") as sync:
            self.assertFalse(warmup.trigger_account(1)["started"])
            self.assertFalse(warmup.trigger_account(1)["started"])
            choose.assert_not_called()
            sync.assert_not_called()

    def test_synthetic_auth_and_api_error_override_success(self) -> None:
        """历史退出码 0 不覆盖明确错误，封号不参与额度恢复。"""
        for rid, hint in (("api-error", {"status": "failed", "error": "合成 API 错误"}),
                          ("hold", {"status": "auth_failed", "error": "account_on_hold"})):
            task = self._run(rid)
            self.runner.read_worker_status.return_value = hint
            self.scheduler._execute(rid, self.account, task)
            self.assertEqual(hint["status"], main.get_run(rid)["status"])
        self.assertFalse(self.guard.snapshot(self.account)["retry_ready"])
        self.assertTrue(self.guard.snapshot(self.account)["blocked"])

    def test_continue_wait_blocks_both_input_types_and_auto_resumes(self) -> None:
        """续聊不创建等待 worker，到期恢复同会话且关闭后不复活。"""
        self._run(status="success")
        run = main.get_run("original")
        self._state(quota_headers(time.time(), 600, rejected=True))
        manager = main.ContinueManager(self.runner)
        self.runner.start_continue.return_value = ("continue-sidecar", "continue-worker")
        with patch.object(main, "_find_latest_claude_session_id", return_value="original-session"):
            session = manager.start(run, self.account)
        self.runner.start_continue.assert_not_called()
        raw = Mock()
        for data in (b"text", b"\x01\x02"):
            self.assertFalse(manager.send_input(session, 0, raw, data))
        raw.send.assert_not_called()
        session.connected = True
        self._expire()
        manager.quota_tick(self.account)
        self.assertEqual("running", session.status)
        self.assertEqual("original-session", self.runner.start_continue.call_args.args[3])
        self.assertTrue(manager.send_input(session, 0, raw, b"new-input"))
        self._state(quota_headers(time.time(), 600, rejected=True))
        self.assertFalse(manager.send_input(session, 0, raw, b"discard-input"))
        self.assertEqual("quota_wait", session.status)
        before = self.runner.start_continue.call_count
        manager.cleanup(session.sid)
        manager.quota_tick(self.account)
        self.assertEqual(before, self.runner.start_continue.call_count)
        raw.send.assert_called_once_with(b"new-input")

    def test_actual_websocket_discards_text_and_binary_while_waiting(self) -> None:
        """执行真实 WS 路由，等待输入均不进入 Docker exec。"""
        self._run(status="success")
        self._state(quota_headers(time.time(), 600, rejected=True))
        manager = main.ContinueManager(self.runner)
        with patch.object(main, "_find_latest_claude_session_id", return_value="same-session"):
            session = manager.start(main.get_run("original"), self.account)

        class Browser:
            """模拟已连接浏览器，输入后主动断开。"""

            client_state = main.WebSocketState.CONNECTED

            def __init__(self):
                self.sent = []
                self.ready = asyncio.Event()
                self.messages = iter((
                    {"type": "websocket.receive", "text": json.dumps({"type": "input", "data": "不能重放"})},
                    {"type": "websocket.receive", "bytes": b"binary-input"},
                    {"type": "websocket.disconnect"},
                ))

            async def accept(self):
                """接受连接，返回 None。"""

            async def send_text(self, text):
                """记录服务端状态，参数为消息，返回 None。"""
                self.sent.append(json.loads(text))
                self.ready.set()

            async def receive(self):
                """等待状态事件后发送下一帧，返回帧字典。"""
                await self.ready.wait()
                return next(self.messages)

            async def close(self):
                """关闭连接，返回 None。"""
                self.client_state = main.WebSocketState.DISCONNECTED

        async def exercise():
            browser = Browser()
            with patch.object(main, "continue_manager", manager):
                await main.continue_run_ws(browser, session.sid)
            return browser

        browser = asyncio.run(exercise())
        self.assertEqual("quota_wait", browser.sent[0]["status"])
        self.runner.client.api.exec_create.assert_not_called()
        self.assertIsNone(manager.get(session.sid))

    def test_pending_batch_and_original_batch_progress_resume_in_order(self) -> None:
        """先恢复已投放原题，终态后才继续 pending 项目。"""
        self._run(batch=True, status="quota_wait")
        self._state(quota_headers(time.time(), 600, rejected=True))
        conn = main.get_db()
        with conn:
            conn.execute("UPDATE task_batches SET status='quota_wait' WHERE id=1")
            conn.execute("INSERT INTO task_batch_items(batch_id,topic_id,prompt,status) VALUES(1,1,'后一题','pending')")
        conn.close()
        self._expire()
        self.scheduler.submit = Mock()
        self.scheduler.submit_batch = Mock()
        self.guard.tick()
        self.scheduler.submit.assert_called_once()
        self.scheduler.submit_batch.assert_not_called()
        conn = main.get_db()
        with conn:
            conn.execute("UPDATE runs SET status='success' WHERE id='original'")
            conn.execute("UPDATE task_batch_items SET status='success' WHERE run_id='original'")
        conn.close()
        self._state(quota_headers(time.time(), 600, 1000), status=200)
        self.guard.tick()
        self.scheduler.submit_batch.assert_called_once_with(1)
        self.assertEqual("active", main.list_task_batches()[0]["status"])
        self.assertEqual(1, main.list_task_batches()[0]["done_count"])

    def test_unknown_quota_window_does_not_guess_time_or_override_real_header(self) -> None:
        """无窗口的 hit-your-limit 保持等待，有真实窗口时优先用真实事实。"""
        self.guard.record_worker_limit(self.account, "unknown")
        state = self.guard.snapshot(self.account)
        self.assertTrue(state["blocked"])
        self.assertIsNone(state["resume_at"])
        self._state(quota_headers(time.time(), 600, 1000), status=200)
        self.assertFalse(self.guard.snapshot(self.account)["blocked"])
        self._state(quota_headers(time.time(), 600, rejected=True))
        self.guard.record_worker_limit(self.account, "unknown")
        self.assertEqual(["five_hour"], self.guard.snapshot(self.account)["exhausted"])

    def test_late_rejection_cannot_overwrite_newer_real_allowed_response(self) -> None:
        """无额度头的恢复成功同样保护本窗口的最新观察时刻。"""
        now = time.time() - 100
        self._state(quota_headers(now, 1, rejected=True), now)
        self._state({}, now + 20, status=200)
        self._state(quota_headers(now + 10, 600, rejected=True), now + 10)
        self.assertFalse(self.guard.snapshot(self.account)["blocked"])

    def test_restart_of_recovery_after_allowed_response_preserves_original(self) -> None:
        """允许响应已落库后崩溃仍清掉旧 worker，再恢复原 run。"""
        self._run(status="running")
        conn = main.get_db()
        with conn:
            conn.execute("UPDATE runs SET quota_attempt=1 WHERE id='original'")
        conn.close()
        self._state(quota_headers(time.time(), 600, 1000), status=200)
        self.guard.recover()
        self.assertEqual("quota_wait", main.get_run("original")["status"])
        self.scheduler.submit = Mock()
        self.guard.tick()
        self.assertEqual("original", self.scheduler.submit.call_args.args[0])
        self.assertEqual(2, self.scheduler.submit.call_args.args[2]["quota_attempt"])

    def test_capture_recovery_preserves_serial_cooldown_and_snapshot(self) -> None:
        """抓包恢复保持 15 分钟冷却、串行与原配置。"""
        self._run(kind="capture", status="running")
        self._state(quota_headers(time.time(), 2, rejected=True))
        self.scheduler._mark_quota_wait("original", self.account, 0)
        run = main.get_run("original")
        self.assertGreaterEqual(run["quota_resume_at"], time.time() + 899)
        self.scheduler.submit = Mock()
        self._expire()
        self._run("other-capture", "capture", status="running")
        self.guard.tick()
        self.scheduler.submit.assert_not_called()
        conn = main.get_db()
        with conn:
            conn.execute("UPDATE runs SET status='success' WHERE id='other-capture'")
        conn.close()
        self.guard.tick()
        self.scheduler.submit.assert_called_once()
        payload = self.scheduler.submit.call_args.args[2]
        self.assertTrue(payload["capture_full_http"])
        self.assertEqual("2.1.62", payload["claude_code_version"])
        self.assertEqual("high", payload["claude_effort_level"])

    def test_capture_continue_auto_resume_obeys_cooldown_and_serial_gate(self) -> None:
        """抓包续聊和 run 恢复共享串行、120 秒间隔及 15 分钟暂停。"""
        self._run('capture-history', kind='capture', status='success')
        self._state(quota_headers(time.time(), 600, rejected=True))
        manager = main.ContinueManager(self.runner)
        self.runner.start_continue.return_value = ('sidecar', 'worker')
        with patch.object(main, 'continue_manager', manager), \
                patch.object(main, '_find_latest_claude_session_id', return_value='original-session'):
            session = manager.start(main.get_run('capture-history'), self.account)
            session.connected = True
            self._expire()
            manager.quota_tick(self.account)
            self.runner.start_continue.assert_not_called()
            session.resume_not_before = time.time() - 1
            self._run('other-capture', kind='capture', status='running')
            manager.quota_tick(self.account)
            self.runner.start_continue.assert_not_called()
            conn = main.get_db()
            with conn:
                conn.execute("UPDATE runs SET status='success',started_at=? WHERE id='other-capture'", (time.time(),))
            conn.close()
            manager.quota_tick(self.account)
            self.runner.start_continue.assert_not_called()
            conn = main.get_db()
            with conn:
                conn.execute("UPDATE runs SET started_at=? WHERE id='other-capture'", (time.time() - 121,))
            conn.close()
            manager.quota_tick(self.account)
            self.assertEqual('running', session.status)
            self.runner.start_continue.assert_called_once()
            self.assertFalse(self.guard.capture_resume_ready('another-waiting-run'))
            manager.cleanup(session.sid)
            self.assertFalse(self.guard.capture_resume_ready('another-waiting-run'))
            manager._capture_started_at = time.time() - 121
            self.assertTrue(self.guard.capture_resume_ready('another-waiting-run'))

    def test_first_wait_freezes_model_and_identity_change_cancels_old_work(self) -> None:
        """首次等待就固定模型，旧任务不能自动在新身份上执行。"""
        task = self._run()
        self._state(quota_headers(time.time(), 600, rejected=True))
        with patch.object(main, "effective_runtime_model", return_value="opus"):
            self.scheduler._execute("original", self.account, task)
        run = main.get_run("original")
        self.assertEqual("opus", run["execution_model"])
        self.assertEqual(main._quota_identity(self.account), run["quota_identity"])
        top = main.PROFILES_DIR / "fixture/.claude.json"
        top.write_text(json.dumps({"oauthAccount": {"accountUuid": "新的脱敏身份", "organizationUuid": "组织"}}))
        self.scheduler.submit = Mock()
        self.guard.tick()
        self.scheduler.submit.assert_not_called()
        self.assertEqual("auth_failed", main.get_run("original")["status"])

    def test_explicit_manual_usage_updates_unknown_reset_without_automatic_query(self) -> None:
        """用户主动查询可补可信窗口，自动路径仍没有查询调用。"""
        self.guard.record_worker_limit(self.account, "unknown")
        now = time.time()
        usage = {"ok": True, "five_hour": {"utilization": 10, "resets_at": now + 600},
                 "seven_day": {"utilization": 20, "resets_at": now + 1000}}
        self.guard.record_manual_usage(self.account, usage)
        self.assertFalse(self.guard.snapshot(self.account)["blocked"])
        self.assertEqual("manual", main.list_accounts()[0]["passive_quota"]["source"])
        self.runner.query_quota.assert_not_called()

    def test_resume_does_not_choose_subagent_or_copied_profile_history(self) -> None:
        """主会话恢复排除子代理及首轮未写入的账号旧历史。"""
        self._run()
        directory = main.WORKSPACES_DIR / "original/.claude-home/projects/-workspace"
        directory.mkdir(parents=True)
        main_session = directory / "main-session.jsonl"
        main_session.write_text("旧会话\n")
        nested = directory / "main-session/subagents/agent-id.jsonl"
        nested.parent.mkdir(parents=True)
        nested.write_text("新子代理\n")
        self.assertEqual("main-session", main._find_latest_claude_session_id("original"))
        baseline = main.WORKSPACES_DIR / "original/.bench-session-baseline.json"
        baseline.write_text(json.dumps({"main-session.jsonl": main_session.stat().st_size}))
        self.assertIsNone(main._find_latest_claude_session_id("original"))
        with main_session.open("a") as handle:
            handle.write("本 run 新内容\n")
        self.assertEqual("main-session", main._find_latest_claude_session_id("original"))


class WorkerCompletionTests(unittest.TestCase):
    """执行 worker 真正的内嵌 Python，验证脱敏 JSONL。"""

    def _classify(self, entry, baseline=False):
        root = Path(__file__).resolve().parents[1]
        script = (root / "images/worker/entrypoint.sh").read_text()
        match = re.search(r'classify_claude_completion\(\).*?<<\'PY\'\n(.*?)\nPY', script, re.S)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / "session.jsonl"
            path.write_text(json.dumps(entry) + "\n")
            env = dict(os.environ)
            if baseline:
                offset = project / "baseline.json"
                offset.write_text(json.dumps({str(path): path.stat().st_size}))
                env["COMPLETION_BASELINE"] = str(offset)
            result = subprocess.run([sys.executable, "-c", match.group(1), str(project), "0"], env=env, capture_output=True, text=True)
        return result.returncode, result.stdout.strip()

    def test_synthetic_errors_never_complete(self) -> None:
        """10-2 的限额/封号与未知 API 错误均不得成功。"""
        for error, text, expected in (("rate_limit", "Session limit exhausted", 4),
                                      ("rate_limit", "You've hit your limit · resets 9am (America/Los_Angeles)", 4),
                                      ("account_on_hold", "Account on hold", 2),
                                      ("invalid_grant", "凭据失效", 2),
                                      ("rate_limit", "Too many requests", 5),
                                      ("unknown", "API Error: 500", 5),
                                      ("timeout", "Request timed out", 3),
                                      ("auth", "API Error: 401", 2)):
            with self.subTest(error=error):
                code, _ = self._classify({"isApiErrorMessage": True, "error": error,
                    "message": {"role": "assistant", "model": "<synthetic>", "content": text}})
                self.assertEqual(expected, code)

    def test_normal_final_message_and_old_attempt_baseline(self) -> None:
        """真正 assistant 回答可完成，恢复时旧回答不可完成。"""
        entry = {"message": {"role": "assistant", "model": "claude", "content": "交付完成", "stop_reason": "end_turn"}}
        self.assertEqual(0, self._classify(entry)[0])
        self.assertEqual(1, self._classify(entry, baseline=True)[0])


if __name__ == "__main__":
    unittest.main()
