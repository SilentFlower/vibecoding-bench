"""使用合成 CLI 和真实调度器验证时段/百分比组合，不访问真实账号。"""
import hashlib
import json
import threading
import time
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import main
from account_runtime import AccountRuntime, atomic_json
from physical_features import physical_features_summary
from quota_protocol import quota_observation


def verify_physical_observation(runtime, row: dict) -> None:
    """实测当前 CLI 的 DMI、CPU 和 RAM，核对身份及凭据未变。

    :param runtime: 本次隔离运行时。
    :param row: 当前环境行。
    :return: None；来源或只读约束不满足时失败。
    """
    with runtime.database() as connection:
        row = dict(connection.execute("SELECT * FROM account_environments WHERE environment_id=?", (row["environment_id"],)).fetchone())
    credentials = runtime._root(row) / "home/.claude/.credentials.json"
    before = credentials.read_bytes()
    runtime.refresh_physical_features(row)
    snapshot = physical_features_summary(row, runtime._root(row) / "runtime/physical-features.json", time.time())
    fields = {field["key"]: field for field in snapshot["fields"]}
    assert snapshot["status"] == "cached", snapshot
    for key in ("kernel", "cpu", "manufacturer", "product", "version", "family", "serial", "uuid", "memory_bytes", "timezone", "locale"):
        assert fields[key]["status"] == "match", (key, fields[key])
    assert fields["memory_bytes"]["observed"] < fields["account_memory_bytes"]["configured"], fields
    assert credentials.read_bytes() == before
    with runtime.database() as connection:
        assert connection.execute("SELECT fingerprint_json FROM account_environments WHERE environment_id=?",
            (row["environment_id"],)).fetchone()[0] == row["fingerprint_json"]
    print("通过：真实 CLI 只读物理采集、DMI/CPU/内核/时区一致、cgroup RAM 口径及身份/凭据保留", flush=True)


def verify_run_window_completion(runtime, client, account: dict, row: dict) -> None:
    """验证忙碌任务跨过窗口与阈值、等待重启及两个门禁分别解除。

    :param runtime: 已完成合成登录的运行时。
    :param client: 本次 Docker 客户端。
    :param account: 合成账号。
    :param row: 同账号环境记录。
    :return: None；执行、保存或恢复约束不满足时失败。
    """
    with runtime.database() as connection:
        row = dict(connection.execute("SELECT * FROM account_environments WHERE environment_id=?", (row["environment_id"],)).fetchone())
    data = runtime.data
    config_path = runtime._root(row) / "home/.synthetic-followups.json"
    credentials = runtime._root(row) / "home/.claude/.credentials.json"
    identity_before, credentials_before = row["fingerprint_json"], credentials.read_bytes()
    paths = {"BENCH_DATA": data, "HOST_BENCH_DATA": runtime.host_data, "DB_PATH": data / "run-windows.sqlite",
        "PROFILES_DIR": data / "profiles", "WORKSPACES_DIR": data / "workspaces", "FLOWS_DIR": data / "flows",
        "CA_DIR": data / "ca", "TOPICS_FILE": data / "missing-topics.md"}
    with ExitStack() as stack:
        for key, value in {**paths, "V3_ENABLED": True, "TIMEOUT_WRAPUP_SEC": 0, "CLAUDE_CODE_VERSION": "9.9.9",
                "login_manager": None, "warmup_scheduler": None, "continue_manager": None}.items():
            stack.enter_context(patch.object(main, key, value))
        main.init_db()
        verified = AccountRuntime(client, data, runtime.host_data, main.get_db, runtime.fingerprint, None)
        stack.callback(verified.heartbeat_pool.shutdown)
        with main.get_db() as connection:
            connection.execute("INSERT INTO accounts(id,name,profile_path,upstream_proxy_scheme,upstream_socks5_host,"
                "upstream_socks5_port,enabled,warmup_quota_5h_limit_percent) VALUES(?,?,?,?,?,?,1,60)",
                (account["id"], account["name"], str(data / "profiles" / account["name"]), account["upstream_proxy_scheme"],
                 account["upstream_socks5_host"], account["upstream_socks5_port"]))
            columns = list(row)
            connection.execute("INSERT INTO account_environments(" + ",".join(columns) + ") VALUES(" + ",".join("?" for _ in columns) + ")", tuple(row.values()))
            connection.execute("INSERT INTO topics(id,no,title,description) VALUES(1,1,'窗口合成任务','离线交付')")
        runner, guard = main.Runner(), None
        guard = main.QuotaGuard(runner)
        scheduler = main.Scheduler(runner)
        stack.callback(lambda: scheduler.stop_window_waits())
        for key, value in (("account_runtime", verified), ("runner", runner), ("quota_guard", guard), ("scheduler", scheduler)):
            stack.enter_context(patch.object(main, key, value))
        original_snapshot = main.run_window_snapshot
        base = datetime(2026, 10, 19, 10, 59, 55, tzinfo=ZoneInfo(json.loads(row["fingerprint_json"])["tz"])).timestamp()
        started = time.monotonic()

        def local_clock(configuration, zone, now):
            """只加速业务时钟，实际进程、额度观察及网络超时仍用真实时间。"""
            return original_snapshot(configuration, zone, base + time.monotonic() - started)

        stack.enter_context(patch.object(main, "run_window_snapshot", side_effect=local_clock))
        body = main.RunWindowConfigIn(enabled=True, days=list(range(7)), intervals=[{"start": "10:00", "end": "11:00"}])
        main.update_account_run_window(account["id"], body)
        rid = "b070ff000001"
        with main.get_db() as connection:
            tid = connection.execute("INSERT INTO tasks(topic_no,title,prompt,account_id,timeout_sec) "
                "VALUES(1,'窗口合成任务','Build a local table.',?,120)", (account["id"],)).lastrowid
            timing = {"schema": 2, "offsets_sec": [6, 10], "timeout_sec": 120, "wrapup_sec": 0}
            connection.execute("INSERT INTO runs(id,task_id,account_id,status,claude_code_version,claude_effort_level,"
                "followup_plan_json,followup_timing_json) VALUES(?,?,?,'queued','9.9.9','high',?,?)",
                (rid, tid, account["id"], json.dumps(["Export the table.", "Summarize the delivered work."]), json.dumps(timing)))
            current = dict(connection.execute("SELECT * FROM accounts WHERE id=?", (account["id"],)).fetchone())
        atomic_json(config_path, {"session": rid, "busy_seconds": 14, "queued_command": True, "quota_schedule": [
            {"after": 1, "five_hour": 55, "seven_day": 40}, {"after": 3, "five_hour": 68, "seven_day": 40}]}, 0o644)
        task = {"id": tid, "prompt": "Build a local table.", "timeout_sec": 120, "claude_code_version": "9.9.9", "claude_effort_level": "high"}
        scheduler._execute(rid, current, task)
        result = main.get_run(rid)
        assert result["status"] == "success" and result["stop_requested_at"] is None, result
        assert not main._account_run_window(current)["allowed"] and guard.policy_snapshot(current, "normal")["blocked"]
        workspace = verified._root(row) / "projects" / ("project-" + hashlib.sha256(f"{row['environment_id']}:{rid}".encode()).hexdigest()[:12])
        turns = [json.loads(line) for line in (workspace / ".synthetic-turns.jsonl").read_text().splitlines()]
        assert len(turns) == 3 and turns[-1]["text"] == "Summarize the delivered work.", turns

        next_run = "b070ff000002"
        with main.get_db() as connection:
            connection.execute("INSERT INTO runs(id,task_id,account_id,status,claude_code_version,claude_effort_level) "
                "VALUES(?,?,?,'queued','9.9.9','high')", (next_run, tid, account["id"]))
        waiting = threading.Thread(target=scheduler._execute, args=(next_run, current, task), daemon=True)
        waiting.start()
        deadline = time.monotonic() + 10
        while main.get_run(next_run)["window_wait_until"] is None:
            assert time.monotonic() < deadline, "下一轮未进入窗口等待"
            time.sleep(0.1)
        scheduler.stop_window_waits()
        waiting.join(timeout=3)
        assert not waiting.is_alive() and main.get_run(next_run)["status"] == "queued"
        scheduler = main.Scheduler(runner)
        main.scheduler = scheduler
        scheduler.recover_window_waits()
        main.update_account_run_window(account["id"], main.RunWindowConfigIn(enabled=False, days=body.days, intervals=body.intervals))
        deadline = time.monotonic() + 20
        while main.get_run(next_run)["status"] != "quota_wait":
            assert time.monotonic() < deadline, "解除时间限制后未保留额度等待"
            time.sleep(0.1)
        while scheduler.is_executing(next_run, 0):
            assert time.monotonic() < deadline, "额度等待的原执行未收口"
            time.sleep(0.1)
        main.update_account_run_window(account["id"], body)
        with main.get_db() as connection:
            current = dict(connection.execute("SELECT * FROM accounts WHERE id=?", (account["id"],)).fetchone())
        now = time.time()
        guard._observe(current, main._quota_identity(current), quota_observation({
            "anthropic-ratelimit-unified-5h-utilization": "0.2", "anthropic-ratelimit-unified-5h-reset": str(now + 600),
            "anthropic-ratelimit-unified-5h-status": "allowed"}, 200, now))
        guard._resume_account(current)
        assert main.get_run(next_run)["status"] == "quota_wait", "只恢复额度不能绕过关闭的时段"
        atomic_json(config_path, {"session": next_run, "busy_seconds": 1, "queued_command": True}, 0o644)
        main.update_account_run_window(account["id"], main.RunWindowConfigIn(enabled=False, days=body.days, intervals=body.intervals))
        with main.get_db() as connection:
            current = dict(connection.execute("SELECT * FROM accounts WHERE id=?", (account["id"],)).fetchone())
        guard._resume_account(current)
        deadline = time.monotonic() + 60
        while main.get_run(next_run)["status"] not in ("success", "failed", "timeout", "auth_failed"):
            assert time.monotonic() < deadline, "两个门禁解除后原排队未完成"
            time.sleep(0.1)
        assert main.get_run(next_run)["status"] == "success", main.get_run(next_run)
        while scheduler.is_executing(next_run, main.get_run(next_run)["quota_attempt"]):
            assert time.monotonic() < deadline, "执行成功后清理未完成"
            time.sleep(0.1)
        assert credentials.read_bytes() == credentials_before
        with main.get_db() as connection:
            assert connection.execute("SELECT fingerprint_json FROM account_environments WHERE environment_id=?", (row["environment_id"],)).fetchone()[0] == identity_before
        config_path.unlink(missing_ok=True)
        print("通过：真实整轮跨关闭时刻和额度阈值、补充及收尾完成、排队重启、两个门禁分别解除和身份保留", flush=True)
