"""固定环境状态及故障收口测试，不使用真实账号或 Docker daemon。"""
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_runtime import AccountRuntime, atomic_json
import main


class AccountRuntimeTests(unittest.TestCase):
    """验证不可变身份、旧代回调和排空失败的安全边界。"""

    def setUp(self) -> None:
        """创建独立数据目录及合成 SQLite。@return None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

        def database():
            """返回带行对象的独立测试连接。"""
            connection = sqlite3.connect(self.root / "test.sqlite")
            connection.row_factory = sqlite3.Row
            return connection

        self.database = database
        with database() as connection:
            connection.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY, name TEXT, cc2api_account_id INTEGER)")
            connection.execute("INSERT INTO accounts VALUES(1,'synthetic',7)")
        self.client = Mock()
        self.gateway = Mock()
        self.fingerprint = Mock(return_value={"hostname": "fixed", "machine_id": "a" * 32, "mac": "02:00:00:00:00:01", "tz": "UTC", "lang": "en_US.UTF-8"})
        environment = patch.dict(os.environ, {"V3_DEPLOYMENT_ID": "test", "V3_ACCOUNT_IMAGE": "v3-test",
            "V3_NETWORK": "vibebench-v3-test", "V3_MAX_ACTIVE_ACCOUNTS": "1",
            "V3_ACCOUNT_MEMORY": "4g", "V3_ACCOUNT_SWAP": "0"})
        environment.start()
        self.addCleanup(environment.stop)
        self.runtime = AccountRuntime(self.client, self.root, self.root, database, self.fingerprint, self.gateway)
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)

    def test_rename_keeps_environment_and_frozen_fingerprint(self) -> None:
        """改名和重复读取不能重新派生身份。@return None。"""
        initial = self.runtime._row("synthetic", 1)
        renamed = self.runtime._row("renamed", 1)
        self.assertEqual(initial["environment_id"], renamed["environment_id"])
        self.assertEqual(initial["fingerprint_json"], renamed["fingerprint_json"])
        self.assertEqual(renamed["name"], "renamed")
        self.fingerprint.assert_called_once_with("synthetic")

    def test_ram_and_swap_limits_remain_frozen_when_global_budget_changes(self) -> None:
        """新账号使用选定总额度，后续全局预算不能改变既有身份或限额。

        :return: None
        """
        with patch.dict(os.environ, {"V3_ACCOUNT_MEMORY": "1536m", "V3_ACCOUNT_SWAP": "2048m"}):
            row = self.runtime._row("synthetic", 1)
        self.runtime.release_id = "test"
        self.client.images.get.return_value.attrs = {"Config": {"Labels": {
            "vibebench.product": "v3", "vibebench.role": "account", "vibebench.release": "test"}}}
        container = Mock(id="new-container", status="running")
        container.exec_run.return_value = SimpleNamespace(exit_code=0)
        self.client.containers.run.return_value = container
        with patch.object(self.runtime, "_make_room"), patch.object(self.runtime, "_sender_active", return_value=0), patch.object(self.runtime, "_ensure_version"):
            current, _ = self.runtime.ensure({"id": 1, "name": "synthetic"}, "2.1.280")
        limits = self.client.containers.run.call_args.kwargs
        self.assertEqual(limits["mem_limit"], 1536 * 1024**2)
        self.assertEqual(limits["memswap_limit"], 3584 * 1024**2)
        self.assertEqual(current["fingerprint_json"], row["fingerprint_json"])

    def test_old_fingerprint_missing_swap_preserves_no_swap(self) -> None:
        """已有记录缺 swap 时不能随新全局配置开放额外额度。

        :return: None
        """
        row = self.runtime._row("synthetic", 1)
        fingerprint = json.loads(row["fingerprint_json"])
        del fingerprint["swap"]
        self.runtime._update(row, fingerprint_json=json.dumps(fingerprint))
        self.runtime.release_id = "test"
        self.client.images.get.return_value.attrs = {"Config": {"Labels": {
            "vibebench.product": "v3", "vibebench.role": "account", "vibebench.release": "test"}}}
        container = Mock(id="legacy-container", status="running")
        container.exec_run.return_value = SimpleNamespace(exit_code=0)
        self.client.containers.run.return_value = container
        with patch.dict(os.environ, {"V3_ACCOUNT_SWAP": "2048m"}), patch.object(self.runtime, "_make_room"), patch.object(self.runtime, "_sender_active", return_value=0), patch.object(self.runtime, "_ensure_version"):
            self.runtime.ensure({"id": 1, "name": "synthetic"}, "2.1.280")
        limits = self.client.containers.run.call_args.kwargs
        self.assertEqual(limits["mem_limit"], 4 * 1024**3)
        self.assertEqual(limits["memswap_limit"], limits["mem_limit"])

    def test_unlimited_swap_is_rejected_before_account_registration(self) -> None:
        """非法预算不能留下新账号环境记录。

        :return: None
        """
        with patch.dict(os.environ, {"V3_ACCOUNT_SWAP": "-1"}):
            with self.assertRaisesRegex(ValueError, "无限额"):
                self.runtime._row("synthetic", 1)
        with self.database() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM account_environments").fetchone()[0], 0)

    def test_quota_resume_preserves_evidence_and_aggregates_run_once(self) -> None:
        """两代 run 统计累加一次，抓包保留各代文件，续聊不污染 run 统计。

        :return: None
        """
        account = {"id": 1, "name": "synthetic"}
        flows = self.root / "flows" / "synthetic" / "1" / "resumed-run"
        old = self.runtime.execution_flows(account, "run:resumed-run:0", flows)
        (old / "stats.jsonl").write_text(json.dumps({"phase": "response", "flow_id": "old", "usage": {"input_tokens": 10, "output_tokens": 2}}) + "\n")
        (old / "capture.flow").write_bytes(b"old flow")
        atomic_json(old / "capture_index.json", {"entries": [{"flow_id": "old"}], "cc_versions": ["9.9.9"]})
        before = {path.name: path.read_bytes() for path in old.iterdir()}
        target = flows.resolve()
        new = self.runtime.execution_flows(account, "run:resumed-run:1", flows)
        self.assertEqual(target, flows.resolve())
        self.assertNotEqual(old, new)
        (new / "stats.jsonl").write_text(json.dumps({"phase": "response", "flow_id": "new", "usage": {"input_tokens": 20, "output_tokens": 3}}) + "\n")
        (new / "capture.flow").write_bytes(b"new flow")
        atomic_json(new / "capture_index.json", {"entries": [{"flow_id": "new"}], "cc_versions": ["9.9.9"]})
        continuation = self.runtime.execution_flows(account, "continue:sid:0", flows / "continue-sid")
        (continuation / "stats.jsonl").write_text(json.dumps({"flow_id": "continue", "usage": {"input_tokens": 1000}}) + "\n")
        atomic_json(continuation / "capture_index.json", {"entries": [{"flow_id": "continue"}]})
        with self.database() as connection:
            connection.execute("CREATE TABLE runs(id TEXT, deleted_at REAL, run_kind TEXT, flows_dir TEXT, capture_summary_path TEXT)")
            connection.execute("INSERT INTO runs VALUES('resumed-run',NULL,'capture',?,?)", (str(flows), str(flows / "capture_index.json")))
        with patch.object(main, "FLOWS_DIR", self.root / "flows"), patch.object(main, "get_db", self.database):
            stats = main.get_stats("resumed-run")
            capture = main.get_capture("resumed-run")
        self.assertEqual((30, 5, 2), (stats["tokens_in"], stats["tokens_out"], stats["requests"]))
        self.assertEqual(3, capture["index"]["total_flows"])
        self.assertEqual(2, len([item for item in capture["files"] if item["path"].endswith("capture.flow")]))
        self.assertEqual(before, {path.name: path.read_bytes() for path in old.iterdir()})

    def test_execution_flows_preserves_flat_history_and_rejects_wrong_binding(self) -> None:
        """迁入平铺证据不删除历史，跨目录链接继续拒绝。

        :return: None
        """
        account = {"id": 1, "name": "synthetic"}
        flows = self.root / "flows" / "synthetic" / "1" / "history-run"
        flows.mkdir(parents=True)
        (flows / "capture.flow").write_bytes(b"history")
        self.runtime.execution_flows(account, "run:history-run:0", flows)
        self.assertEqual(b"history", (flows / "capture.flow").read_bytes())
        wrong = flows.parent / "other-run"
        wrong.symlink_to(flows.resolve(), target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "绑定冲突"):
            self.runtime.execution_flows(account, "run:other-run:0", wrong)

    def test_quota_cursor_tracks_each_execution_file(self) -> None:
        """生产额度登记使用实际分代路径，同一续聊恢复保留旧游标。

        :return: None
        """
        account = {"id": 1, "name": "synthetic"}
        with self.database() as connection:
            connection.execute("CREATE TABLE quota_observation_cursors(source TEXT PRIMARY KEY,account_id INTEGER,identity TEXT,path TEXT,byte_offset INTEGER)")
        guard = main.QuotaGuard(Mock())
        flows = self.root / "flows" / "synthetic" / "1" / "run" / "continue-sid"
        runner = main.Runner.__new__(main.Runner)
        with patch.object(main, "account_runtime", self.runtime), patch.object(main, "quota_guard", guard), patch.object(main, "get_db", self.database), patch.object(main, "BENCH_DATA", self.root), patch.object(main, "HOST_BENCH_DATA", self.root), patch.object(guard, "_publish", return_value={"identity": "test-identity"}):
            for generation in range(2):
                runner._quota_mounts(account, "run", f"continue:sid:{generation}", flows)
        with self.database() as connection:
            cursors = [dict(row) for row in connection.execute("SELECT * FROM quota_observation_cursors ORDER BY source")]
        self.assertEqual(2, len(cursors))
        self.assertNotEqual(cursors[0]["path"], cursors[1]["path"])
        self.assertTrue(all(Path(row["path"]).parent.is_dir() for row in cursors))

    def test_stale_cleanup_cannot_stop_new_execution_in_same_container(self) -> None:
        """固定容器 ID 相同仍须匹配执行来源。@return None。"""
        row = self.runtime._row("synthetic", 1)
        row["container_id"] = "same-container"
        self.runtime.jobs[row["environment_id"]] = {"row": row, "token": "same-container:new"}
        self.runtime.cleanup("same-container:old")
        self.client.containers.get.assert_not_called()
        self.assertIn(row["environment_id"], self.runtime.jobs)

    def test_quota_cleanup_snapshot_cannot_stop_replacement_job(self) -> None:
        """实际 Runner 旧快照清理不得回退到容器 ID 并停止新代。@return None。"""
        row = self.runtime._row("synthetic", 1)
        row["container_id"] = "same-container"
        old = {"row": row, "token": "same-container:old", "run_id": "old-run"}
        new = {"row": row, "token": "same-container:new", "run_id": "new-run"}
        self.runtime.jobs[row["environment_id"]] = old

        class SwapLock:
            """在快照锁释放时模拟新执行注册。"""

            def __enter__(lock):
                """返回测试锁，参数为锁对象。"""
                return lock

            def __exit__(lock, *args):
                """替换执行；返回 False 以保留测试异常。"""
                self.runtime.jobs[row["environment_id"]] = new
                return False

        runner = main.Runner.__new__(main.Runner)
        with patch.object(self.runtime, "lock", SwapLock()), patch.object(main, "account_runtime", self.runtime):
            runner.cleanup_quota_run("old-run")
        self.client.containers.get.assert_not_called()
        self.assertIs(self.runtime.jobs[row["environment_id"]], new)
        self.runtime.cleanup("same-container")
        self.client.containers.get.assert_not_called()

    def test_repeated_rebuild_without_container_is_idempotent(self) -> None:
        """已移除的固定容器仍能重复维护，不能使用空容器 ID 生成句柄。@return None。"""
        row = self.runtime._row("synthetic", 1)
        with self.database() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=NULL WHERE id=1")
        self.runtime.maintenance(row["environment_id"], "rebuild")
        self.runtime.maintenance(row["environment_id"], "rebuild")
        self.client.containers.get.assert_not_called()
        self.assertFalse(self.runtime.jobs)
        self.assertIsNone(self.runtime._row("synthetic", 1)["container_id"])

    def test_proxy_edit_replaces_stopped_container_without_resetting_home(self) -> None:
        """cc2api 编辑代理后自动同步并替换停止实例，持久身份不变。@return None。"""
        with self.database() as connection:
            for field in ("upstream_proxy_scheme", "upstream_socks5_host", "upstream_socks5_port", "upstream_socks5_user", "upstream_socks5_pass"):
                connection.execute(f"ALTER TABLE accounts ADD COLUMN {field} TEXT")
        self.runtime.release_id = "test"
        self.client.images.get.return_value.attrs = {"Config": {"Labels": {"vibebench.product": "v3", "vibebench.role": "account", "vibebench.release": "test"}}}
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, generation=3, container_id="old-container")
        root = self.runtime._root(row)
        (root / "home").mkdir(parents=True)
        (root / "home" / "marker").write_text("preserved")
        atomic_json(root / "runtime" / "sender.json", {"proxy_url": "http://old.invalid:80", "binding": {}})
        old = Mock(id="old-container", status="exited", labels={**self.runtime._labels(row), "vibebench.release": "test"})
        new = Mock(id="new-container", status="running")
        new.exec_run.return_value = SimpleNamespace(exit_code=0)
        self.client.containers.get.return_value = old
        self.client.containers.run.return_value = new
        self.gateway._request.return_value = {"proxy_url": "http://u%40name:p%3Aword@new.invalid:8080", "auth_type": "oauth", "status": "active"}
        account = {"id": 1, "name": "synthetic", "cc2api_account_id": 7, "upstream_socks5_host": "old.invalid"}
        with patch.object(self.runtime, "_make_room"), patch.object(self.runtime, "_sender_active", return_value=0), patch.object(self.runtime, "_ensure_version"):
            current, _ = self.runtime.ensure(account, "2.1.280")
        old.remove.assert_called_once_with()
        self.assertEqual(current["generation"], 4)
        self.assertEqual(current["fingerprint_json"], row["fingerprint_json"])
        self.assertEqual((root / "home" / "marker").read_text(), "preserved")
        self.assertEqual(self.client.containers.run.call_args.kwargs["environment"]["UPSTREAM_SOCKS5_USER"], "u@name")
        with self.database() as connection:
            saved = dict(connection.execute("SELECT * FROM accounts WHERE id=1").fetchone())
        self.assertEqual(self.runtime._proxy(saved), self.gateway._request.return_value["proxy_url"])

    def test_slow_other_account_setup_does_not_block_lease_heartbeat(self) -> None:
        """实际 ensure 在等待容器时，另一个账号仍能在正常周期续租。@return None。"""
        with self.database() as connection:
            connection.execute("INSERT INTO accounts VALUES(2,'other',NULL)")
        self.runtime.release_id = "test"
        self.client.images.get.return_value.attrs = {"Config": {"Labels": {"vibebench.product": "v3", "vibebench.role": "account", "vibebench.release": "test"}}}
        entered, finish, renewed = threading.Event(), threading.Event(), threading.Event()
        errors = []
        container = Mock(id="other-container", status="running")

        def exec_run(command):
            """模拟容器准备缓慢，最长等待十秒防止测试残留。"""
            entered.set()
            finish.wait(10)
            return SimpleNamespace(exit_code=0)

        container.exec_run.side_effect = exec_run
        self.client.containers.run.return_value = container
        row = self.runtime._row("synthetic", 1)
        job = {"row": row, "account": {"cc2api_account_id": 7}, "claimed": True,
            "lease": {"owner": "run:healthy", "generation": "same-lease"}}
        self.runtime.jobs[row["environment_id"]] = job

        def heartbeat(*args):
            """成功续期并通知主测试。"""
            renewed.set()
            return {"lease": {"owner": "run:healthy", "generation": "same-lease", "expires_at": 9999999999}}

        self.gateway._request.side_effect = heartbeat

        def setup_other():
            """执行真实环境准备，记录线程异常。"""
            try:
                self.runtime.ensure({"id": 2, "name": "other"}, "2.1.280")
            except Exception as error:
                errors.append(error)

        with patch.object(self.runtime, "_make_room"), patch.object(self.runtime, "_sender_active", return_value=0), patch.object(self.runtime, "_ensure_version"):
            setup = threading.Thread(target=setup_other)
            setup.start()
            try:
                self.assertTrue(entered.wait(2))
                self.runtime.start()
                self.assertTrue(renewed.wait(6), "其它账号慢启动阻塞了心跳")
                self.assertFalse(job.get("heartbeat_failed"))
            finally:
                self.runtime.stopping.set()
                self.runtime.heartbeat.join(timeout=2)
                finish.set()
                setup.join(timeout=2)
        self.assertFalse(errors)

    def test_drain_timeout_releases_gate_without_stopping_accepted_api(self) -> None:
        """排空失败时 CLI 未启动，不得截断已接受的流。@return None。"""
        row = self.runtime._row("synthetic", 1)
        row["container_id"] = "accepted-api-container"
        lease = {"owner": "run:test", "generation": "lease-generation"}
        self.gateway._request.return_value = {"active": 1, "lease": lease}
        with patch("account_runtime.time.monotonic", side_effect=[0, 0, 121]):
            with self.assertRaisesRegex(ValueError, "既有请求未完成"):
                self.runtime.claim(row, {"id": 1, "name": "synthetic", "cc2api_account_id": 7}, "run:test", exclusive=True)
        self.client.containers.get.assert_not_called()
        self.assertEqual(self.gateway._request.call_args.args[2]["operation"], "release")
        self.assertFalse(self.runtime.jobs)

    def test_shared_warmup_claims_while_api_is_active_and_waiting(self) -> None:
        """养号与 API 独立，认领与释放均不检查发送器空闲。@return None。"""
        row = self.runtime._row("synthetic", 1)
        row["container_id"] = "container"
        lease = {"owner": "warmup:test", "generation": "shared", "exclusive": False}
        self.gateway._request.side_effect = lambda method, path, *args: {
            "active": 2, "waiting": 1, "lease": None if method == "GET" else lease}
        with patch.object(self.runtime, "_running_sender_active") as sender:
            job = self.runtime.claim(row, {"cc2api_account_id": 7}, "warmup:test", idle_only=True)
            self.assertFalse(job["exclusive"])
            self.assertFalse(json.loads((self.runtime._root(row) / "runtime" / "execution.json").read_text())["exclusive"])
            with self.assertRaisesRegex(ValueError, "其它工作"):
                self.runtime.claim(row, {"cc2api_account_id": 7}, "run:other")
            self.runtime.release(job)
            sender.assert_not_called()
        self.assertIn("prepare-cli", [call.args[2]["operation"] for call in self.gateway._request.call_args_list if len(call.args) > 2])
        self.client.containers.get.assert_not_called()
        self.assertFalse(self.runtime.jobs)

    def test_idle_maintenance_refuses_api_waiting(self) -> None:
        """停机仍不能排空低优先级之前的 API 等待请求。@return None。"""
        row = self.runtime._row("synthetic", 1)
        self.gateway._request.return_value = {"active": 0, "waiting": 1, "lease": None}
        with self.assertRaisesRegex(ValueError, "顺延"):
            self.runtime.claim(row, {"cc2api_account_id": 7}, "idle:test", idle_only=True, exclusive=True)
        self.gateway._request.assert_called_once_with("GET", "/admin/runtime/accounts/7/lease")
        self.assertFalse(self.runtime.jobs)

    def test_shared_cleanup_and_restart_leave_api_container_running(self) -> None:
        """重启通过持久执行句柄只收口 CLI，不能停止独立 API。@return None。"""
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, container_id="container", generation=4, state="ready")
        lease = {"owner": "run:shared", "generation": "shared", "exclusive": False}
        self.gateway._request.return_value = {"active": 3, "waiting": 1, "lease": lease}
        job = self.runtime.claim(row, {"cc2api_account_id": 7}, "run:shared")
        job["handle"] = "synthetic-handle"
        self.runtime.register_exec(job["token"], "old-cli-exec")
        (self.runtime._root(row) / "runtime" / "job-synthetic-handle.pid").write_text("200")
        container = Mock(status="running")
        container.exec_run.return_value = SimpleNamespace(exit_code=1)
        self.client.api.exec_inspect.side_effect = [{"Running": True}] + [{"Running": False}] * 6
        self.runtime.jobs.clear()
        with patch.object(self.runtime, "_container", return_value=container), patch.object(self.runtime, "_configure_recorder"), patch.object(self.runtime, "_running_sender_active") as sender:
            self.runtime.reconcile()
            sender.assert_not_called()
        container.stop.assert_not_called()
        container.exec_run.assert_any_call(["kill", "-TERM", "--", "-200"])
        self.assertEqual(self.runtime._row("synthetic", 1)["state"], "ready")
        self.assertFalse((self.runtime._root(row) / "runtime" / "execution.json").exists())

    def test_shared_heartbeat_failure_blocks_cli_without_stopping_api(self) -> None:
        """租约失联后只隔离 CLI，旧心跳不能收口替代作业。@return None。"""
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, container_id="container", state="ready")
        lease = {"owner": "run:shared", "generation": "shared", "exclusive": False}
        self.gateway._request.return_value = {"active": 1, "lease": lease}
        job = self.runtime.claim(row, {"cc2api_account_id": 7}, "run:shared")
        container = Mock(status="running")
        container.exec_run.return_value = SimpleNamespace(exit_code=1)
        self.gateway._request.side_effect = OSError("synthetic unavailable")
        with patch.object(self.runtime, "_container", return_value=container), patch.object(self.runtime, "_configure_recorder"):
            self.runtime._renew_job(job)
        container.stop.assert_not_called()
        self.assertEqual(self.runtime._row("synthetic", 1)["state"], "cli_reconcile")
        self.assertTrue((self.runtime._root(row) / "runtime" / "execution.json").exists())
        with self.assertRaisesRegex(ValueError, "对账"):
            self.runtime.claim(row, {"cc2api_account_id": 7}, "run:new")
        replacement = {"row": row, "token": "container:new"}
        self.runtime.jobs[row["environment_id"]] = replacement
        with patch.object(self.runtime, "cleanup") as cleanup:
            self.runtime._renew_job(job)
            cleanup.assert_not_called()
        self.assertIs(self.runtime.jobs[row["environment_id"]], replacement)

    def test_shared_recorder_failure_preserves_api_and_fences_next_cli(self) -> None:
        """诊断撤销失败不得停止账号发送器或放行下一 CLI。@return None。"""
        row = self.runtime._row("synthetic", 1)
        row["container_id"] = "container"
        self.gateway._request.return_value = {"active": 1, "lease": {"owner": "run:shared", "generation": "shared"}}
        job = self.runtime.claim(row, {"cc2api_account_id": 7}, "run:shared")
        container = Mock()
        container.exec_run.return_value = SimpleNamespace(exit_code=1)
        with patch.object(self.runtime, "_container", return_value=container), patch.object(self.runtime, "_configure_recorder", side_effect=ValueError("synthetic recorder failure")):
            with self.assertRaisesRegex(ValueError, "recorder failure"):
                self.runtime.cleanup(job["token"])
        container.stop.assert_not_called()
        self.assertEqual(row["state"], "cli_reconcile")
        self.assertFalse(self.runtime.jobs)

    def test_stale_persistent_shared_execution_cannot_stop_current_container(self) -> None:
        """旧落盘代次不得清理新容器上的 CLI 或 API。@return None。"""
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, container_id="new-container", generation=2, state="ready")
        atomic_json(self.runtime._root(row) / "runtime" / "execution.json", {
            "source": "run:old", "exclusive": False, "container_id": "old-container", "generation": 1})
        container = Mock(status="running")
        with patch.object(self.runtime, "_container", return_value=container):
            self.runtime.reconcile()
        container.stop.assert_not_called()
        container.exec_run.assert_not_called()
        self.assertEqual(self.runtime._row("synthetic", 1)["state"], "cli_reconcile")

    def test_legacy_execution_recovery_retains_exclusive_behavior(self) -> None:
        """旧记录没有模式，仍按排他执行保守收口。@return None。"""
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, container_id="legacy-container", generation=1, state="ready")
        atomic_json(self.runtime._root(row) / "runtime" / "execution.json", {"source": "login:old", "lease": None})
        container = Mock(status="running")
        with patch.object(self.runtime, "_container", return_value=container):
            self.runtime.reconcile()
        container.stop.assert_called_once_with(timeout=5)
        self.assertEqual(self.runtime._row("synthetic", 1)["state"], "stopped")

    def test_api_transport_never_installs_cli_and_preserves_cli_reconciliation(self) -> None:
        """CLI 安装失败或待对账不应阻止健康发送器。@return None。"""
        self.runtime.release_id = "test"
        self.client.images.get.return_value.attrs = {"Config": {"Labels": {"vibebench.product": "v3", "vibebench.role": "account", "vibebench.release": "test"}}}
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, container_id="container", generation=1, state="cli_reconcile")
        configuration = {"proxy_url": "", "binding": {"account_id": 7}, "quota_identity": ""}
        atomic_json(self.runtime._root(row) / "runtime" / "sender.json", configuration)
        container = Mock(status="running", labels={**self.runtime._labels(row), "vibebench.release": "test"})
        container.exec_run.return_value = SimpleNamespace(exit_code=0)
        self.client.containers.get.return_value = container
        self.gateway._request.return_value = {"proxy_url": "", "auth_type": "oauth", "status": "active"}
        account = {"id": 1, "name": "synthetic", "cc2api_account_id": 7,
            "upstream_proxy_scheme": "socks5", "upstream_socks5_host": "", "upstream_socks5_port": 1080,
            "upstream_socks5_user": "", "upstream_socks5_pass": ""}
        with patch.object(self.runtime, "_sender_active", return_value=2), patch.object(self.runtime, "_ensure_version", side_effect=ValueError("CLI unavailable")) as installer:
            self.assertEqual(self.runtime.transport(account, "9.9.9"), configuration["binding"])
            installer.assert_not_called()
        self.assertEqual(self.runtime._row("synthetic", 1)["state"], "cli_reconcile")

    def test_atomic_json_concurrent_writers_leave_complete_private_document(self) -> None:
        """凭据写入并发时不得共用临时文件或留下半个 JSON。@return None。"""
        path = self.root / "private" / "credentials.json"
        errors = []

        def write(index):
            """模拟独立发布者并记录实际错误。"""
            try:
                atomic_json(path, {"version": index, "payload": "x" * 2000})
            except Exception as error:
                errors.append(error)

        threads = [threading.Thread(target=write, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)
        self.assertEqual(json.loads(path.read_text())["payload"], "x" * 2000)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual([item.name for item in path.parent.iterdir()], ["credentials.json"])

    def test_owner_transition_fences_both_bindings_until_transaction_finishes(self) -> None:
        """改绑写库前停止旧实例，写库后才释放两端入场门禁。@return None。"""
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, container_id="old-instance")
        lease = {"owner": "binding:test", "generation": "synthetic-generation"}
        self.gateway._request.return_value = {"active": 0, "waiting": 0, "lease": lease}
        # GET 空闲后 prepare 原子设门禁，事务中的 lease 一直存在。
        self.gateway._request.side_effect = lambda method, path, *args: {"active": 0, "waiting": 0, "lease": None if method == "GET" else lease}
        container = Mock()
        with patch.object(self.runtime, "_container", return_value=container), patch.object(self.runtime, "_running_sender_active", return_value=0):
            with self.runtime.owner_transition({"id": 1, "name": "synthetic", "cc2api_account_id": 7}, 8):
                container.stop.assert_called_once()
                self.assertFalse(any(call.args[2].get("operation") == "release" for call in self.gateway._request.call_args_list if len(call.args) > 2))
                with self.database() as connection:
                    connection.execute("UPDATE accounts SET cc2api_account_id=8 WHERE id=1")
        released = [call.args[1] for call in self.gateway._request.call_args_list if len(call.args) > 2 and call.args[2].get("operation") == "release"]
        self.assertEqual(released, ["/admin/runtime/accounts/8/lease", "/admin/runtime/accounts/7/lease"])

    def test_owner_transition_busy_refuses_before_stopping_container(self) -> None:
        """API 活动状态不能被绑定操作截断。@return None。"""
        self.gateway._request.return_value = {"active": 1, "waiting": 0, "lease": None}
        with self.assertRaisesRegex(ValueError, "活动"):
            with self.runtime.owner_transition({"id": 1, "name": "synthetic", "cc2api_account_id": 7}, None):
                self.fail("不得进入绑定事务")
        self.client.containers.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
