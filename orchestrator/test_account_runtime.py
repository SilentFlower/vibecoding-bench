"""固定环境状态及故障收口测试，不使用真实账号或 Docker daemon。"""
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from account_runtime import AccountRuntime, atomic_json, derive_v3_fingerprint, locale_for_timezone
from account_isolation import ROLE_COLUMNS, role_labels
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
            connection.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY, name TEXT, cc2api_account_id INTEGER, enabled INTEGER DEFAULT 1, deleted_at REAL)")
            connection.execute("CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO accounts(id,name,cc2api_account_id) VALUES(1,'synthetic',7)")
        self.client = Mock()
        self.client.containers.list.return_value = []
        self.gateway = Mock()
        self.fingerprint = Mock(return_value={"profile_version": 2, "hostname": "fixed", "machine_id": "a" * 32,
            "mac": "02:00:00:00:00:01", "tz": "UTC", "lang": "en_US.UTF-8"})
        environment = patch.dict(os.environ, {"V3_DEPLOYMENT_ID": "test", "V3_ACCOUNT_IMAGE": "v3-test",
            "V3_NETWORK": "vibebench-v3-test", "V3_MAX_ACTIVE_ACCOUNTS": "1",
            "V3_ACCOUNT_MEMORY": "4g", "V3_ACCOUNT_SWAP": "0"})
        environment.start()
        self.addCleanup(environment.stop)
        self.runtime = AccountRuntime(self.client, self.root, self.root, database, self.fingerprint, self.gateway)
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)

    def _isolated_docker(self, network=None) -> dict:
        """提供具有独立角色、标签及来源网络的 Docker 替身。@return 容器登记。"""
        self.runtime.release_id = "test"
        self.client.images.get.return_value.attrs = {"Config": {"Labels": {
            "vibebench.product": "v3", "vibebench.role": "account", "vibebench.release": "test",
            "vibebench.isolation-version": "2"}}}
        self.client.networks.get.return_value.attrs = {"IPAM": {"Config": [{"Gateway": "192.0.2.1"}]}}
        self.client.containers.list.return_value = []
        containers = {}

        def create(image, **options):
            """模拟实际独立容器创建，保留配置供断言。"""
            role = options["labels"]["vibebench.role"]
            container = network if role == "account-network" and network is not None else Mock()
            container.id, container.status, container.labels = role + "-new", "running", options["labels"]
            if container is not network:
                container.exec_run.return_value = SimpleNamespace(exit_code=0, output=b"")
            containers[container.id] = container
            return container

        self.client.containers.run.side_effect = create
        self.client.containers.get.side_effect = lambda identifier: containers[identifier]
        return containers

    def test_rename_keeps_environment_and_frozen_fingerprint(self) -> None:
        """改名和重复读取不能重新派生身份。@return None。"""
        initial = self.runtime._row("synthetic", 1)
        renamed = self.runtime._row("renamed", 1)
        self.assertEqual(initial["environment_id"], renamed["environment_id"])
        self.assertEqual(initial["fingerprint_json"], renamed["fingerprint_json"])
        self.assertEqual(renamed["name"], "renamed")
        self.fingerprint.assert_called_once_with(None)

    def _identity_configuration(self) -> tuple[dict, Path, Path]:
        """准备无任务、无抓包记录的合成官方登录身份。

        :return: 固定环境、HOME 配置与管理 profile 配置路径
        """
        row = self.runtime._row("synthetic", 1)
        home = self.runtime._root(row) / "home" / ".claude.json"
        profile = self.root / "profiles" / row["name"] / ".claude.json"
        top = {"userID": "d" * 64, "machineID": "e" * 64,
            "oauthAccount": {"accountUuid": "synthetic-account", "emailAddress": "synthetic@example.invalid"}}
        atomic_json(home, top)
        atomic_json(profile, top)
        return row, home, profile

    def test_native_cli_identity_import_needs_no_capture_or_model_task(self) -> None:
        """完成登录即可导出同一 userID，不能生成或混用 machineID。@return None。"""
        row, home, profile = self._identity_configuration()
        before = (home.read_bytes(), profile.read_bytes())
        container = Mock()
        container.exec_run.side_effect = [SimpleNamespace(exit_code=0, output=json.dumps({
            "platform_raw": "linux", "arch": "x64", "node_version": "v22", "linux_kernel": "synthetic"}).encode()),
            SimpleNamespace(exit_code=0, output=json.dumps({'constrained_memory': 4 * 1024 ** 3, 'observation': {
                'source': 'v3:procfs:cli', 'environment_id': row['environment_id'], 'cli_version': '2.1.293',
                'observed_at': time.time(), 'sample_count': 0, 'sampled_at': None,
                'rss_bytes': None, 'rss_min_bytes': None, 'rss_max_bytes': None}}).encode())]
        self.runtime.ensure = Mock(return_value=(row, container))
        exported = self.runtime.identity_import({"id": 1, "name": "synthetic"}, "2.1.293")
        self.assertEqual("d" * 64, exported["device_id"])
        self.assertEqual("cli:2.1.293:config.userID", exported["source"])
        self.assertEqual(row["environment_id"], exported["environment_id"])
        self.assertFalse((self.runtime._root(row) / "runtime/identity.json").exists())
        self.assertEqual(before, (home.read_bytes(), profile.read_bytes()))
        self.assertEqual(2, container.exec_run.call_count)
        self.assertEqual(4 * 1024 ** 3, exported['canonical_process']['constrained_memory'])
        self.assertIsNone(exported['canonical_process']['observation']['rss_bytes'])

    def test_cli_identity_rejects_invalid_device_or_different_login(self) -> None:
        """缺失、异常字段与账号归属变化不能使用另一个设备字段兜底。@return None。"""
        for value in (None, [], 123, "D" * 64, "d" * 32):
            with self.subTest(value=value):
                row, home, _ = self._identity_configuration()
                top = json.loads(home.read_text())
                top["userID"] = value
                atomic_json(home, top)
                with self.assertRaisesRegex(ValueError, "缺少有效设备身份"):
                    self.runtime.read_cli_identity(row, "2.1.293")
        row, home, profile = self._identity_configuration()
        atomic_json(profile, {"oauthAccount": {"accountUuid": "another-account"}})
        with self.assertRaisesRegex(ValueError, "账号归属不一致"):
            self.runtime.read_cli_identity(row, "2.1.293")
        home.write_text("{")
        with self.assertRaisesRegex(ValueError, "缺失或损坏"):
            self.runtime.read_cli_identity(row, "2.1.293")

    def test_local_identity_never_overrides_malformed_or_conflicting_observation(self) -> None:
        """已有请求证据的格式、来源、账号与设备冲突均保持拒绝。@return None。"""
        row, _, _ = self._identity_configuration()
        path = self.runtime._root(row) / "runtime/identity.json"
        observed = {"device_id": "d" * 64, "account_uuid": "synthetic-account",
            "source": "cli:/v1/messages:metadata.user_id.device_id"}
        for value in (None, [], {**observed, "conflict": True}, {**observed, "device_id": "e" * 64},
                {**observed, "device_id": []}, {**observed, "source": "unknown"},
                {**observed, "account_uuid": "another-account"}):
            with self.subTest(observation=value):
                path.parent.mkdir(exist_ok=True)
                path.write_text(json.dumps(value))
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    self.runtime.read_cli_identity(row, "2.1.293")
                self.assertEqual(before, path.read_bytes())
        atomic_json(path, observed)
        self.assertEqual("d" * 64, self.runtime.read_cli_identity(row, "2.1.293")["device_id"])

    def test_unverified_cli_version_requires_real_request_evidence(self) -> None:
        """未知版本不能猜测 userID 映射，但保留已有正式请求观察的兼容。@return None。"""
        row, _, _ = self._identity_configuration()
        with self.assertRaisesRegex(ValueError, "版本.*尚未验证"):
            self.runtime.read_cli_identity(row, "9.9.9")
        observed = {"device_id": "f" * 64, "account_uuid": "synthetic-account",
            "source": "cli:/v1/messages:metadata.user_id.device_id"}
        atomic_json(self.runtime._root(row) / "runtime/identity.json", observed)
        self.assertEqual(observed, self.runtime.read_cli_identity(row, "9.9.9"))

    def test_environment_identity_status_is_readonly_and_does_not_wait_for_maintenance(self) -> None:
        """环境列表不唤醒容器；维护期间返回待核对状态并释放已取得的锁。@return None。"""
        row, _, _ = self._identity_configuration()
        with patch.object(main, "get_db", self.database), patch.object(main, "account_runtime", self.runtime), \
                patch.object(main, "effective_claude_code_version", return_value="2.1.293"):
            self.assertEqual("已确认 CLI 本地设备身份", main.v3_environments()[0]["identity_status"])
            guard = main._profile_lock(row["name"])
            with guard:
                self.assertIn("正在维护", main.v3_environments()[0]["identity_status"])
            self.assertTrue(main._oauth_owner_lock(row["name"]).acquire(blocking=False))
            main._oauth_owner_lock(row["name"]).release()
            atomic_json(self.runtime._root(row) / "runtime/identity.json", {"conflict": True})
            self.assertIn("冲突", main.v3_environments()[0]["identity_status"])
        self.client.containers.run.assert_not_called()
        self.client.containers.get.assert_not_called()

    def test_profile_v2_is_random_and_locale_matches_timezone(self) -> None:
        """新画像字段必须独立随机，美国与伦敦时区使用一致 locale。@return None。"""
        first = derive_v3_fingerprint("America/Los_Angeles")
        default = derive_v3_fingerprint()
        self.assertEqual("America/Los_Angeles", default["tz"])
        self.assertEqual("en_US.UTF-8", default["lang"])
        self.assertEqual("UTC", derive_v3_fingerprint("UTC")["tz"])
        self.assertEqual("ja_JP.UTF-8", derive_v3_fingerprint("Asia/Tokyo")["lang"])
        second = derive_v3_fingerprint("America/Los_Angeles")
        self.assertEqual(2, first["profile_version"])
        self.assertEqual("en_US.UTF-8", first["lang"])
        self.assertEqual("en_GB.UTF-8", locale_for_timezone("Europe/London"))
        self.assertEqual("UTC", main._normalize_account_timezone("UTC"))
        self.assertRegex(first["hostname"], r"^[0-9a-f]{12}$")
        self.assertRegex(first["machine_id"], r"^[0-9a-f]{32}$")
        self.assertRegex(first["mac"], r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")
        self.assertEqual(0x02, int(first["mac"].split(":")[0], 16) & 0x03)
        self.assertNotEqual(
            (first["hostname"], first["machine_id"], first["mac"]),
            (second["hostname"], second["machine_id"], second["mac"]),
        )

    def test_statusline_snapshot_is_persisted_and_original_settings_are_restored(self) -> None:
        """状态栏采集先保存执行证明，收口仅恢复自己的字段。@return None。"""
        account = {"id": 1, "name": "synthetic", "cc2api_account_id": None}
        row = self.runtime._row("synthetic", 1)
        settings = self.runtime._root(row) / "home/.claude/settings.json"
        original = {"model": "original-model", "env": {"CUSTOM": "keep"},
            "statusLine": {"type": "command", "command": "printf original", "padding": 2}}
        atomic_json(settings, original)
        source = "run:synthetic:0"
        job = {"row": row, "account": account, "source": source, "lease": None, "exclusive": False}
        flows = self.runtime.execution_flows(account, source, self.root / "flows/synthetic/1/synthetic")
        self.runtime._install_cli_quota(job, "/home/node/projects/project-synthetic", flows, "synthetic-identity")
        installed = json.loads(settings.read_text())
        record = json.loads((self.runtime._root(row) / "runtime/execution.json").read_text())
        self.assertEqual(original["statusLine"], record["statusline_before"]["value"])
        self.assertIn("v3-cli-quota", installed["statusLine"]["command"])
        self.assertEqual(original["model"], installed["model"])
        self.assertEqual(0o700, (flows / "cli").stat().st_mode & 0o777)
        self.assertEqual(0o710, flows.stat().st_mode & 0o777)
        self.assertEqual("printf original", json.loads((flows / "cli/config.json").read_text())["previous_command"])
        self.runtime._restore_cli_quota({"row": row, **record})
        self.assertEqual(original, json.loads(settings.read_text()))

    def test_effective_timezone_uses_saved_environment_without_allocating(self) -> None:
        """默认展示不创建环境，已有画像优先于改名和临时配置。@return None。"""
        with patch.object(main, "account_runtime", self.runtime):
            self.assertEqual("America/Los_Angeles", main._effective_account_timezone("new"))
            self.assertEqual("Asia/Tokyo", main._effective_account_timezone("new", "Asia/Tokyo"))
            with self.database() as connection:
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM account_environments").fetchone()[0])
            row = self.runtime._row("synthetic", 1)
            self.assertEqual("UTC", main._effective_account_timezone({"id": 1, "name": "renamed"}, "Asia/Tokyo"))
            self.assertEqual(row["fingerprint_json"], self.runtime._row("renamed", 1)["fingerprint_json"])

    def test_session_view_removes_only_empty_or_verified_legacy_home(self) -> None:
        """空目录可移除；非空、外部链接及未知 session 链接保留。@return None。"""
        row = self.runtime._row("synthetic", 1)
        cwd = self.runtime._project_view(row, "cleanup-test")
        legacy = self.runtime._root(row) / "workspaces/cleanup-test/.claude-home"
        legacy.mkdir()
        self.runtime._session_view(row, "cleanup-test", cwd)
        self.assertFalse(legacy.exists())
        legacy.mkdir()
        (legacy / "user.txt").write_text("keep")
        self.runtime._session_view(row, "cleanup-test", cwd)
        self.assertEqual("keep", (legacy / "user.txt").read_text())
        (legacy / "user.txt").unlink()
        legacy.rmdir()
        outside = self.root / "outside"
        outside.mkdir()
        legacy.symlink_to(outside, target_is_directory=True)
        self.runtime._session_view(row, "cleanup-test", cwd)
        self.assertTrue(legacy.is_symlink())
        self.assertTrue(outside.is_dir())
        legacy.unlink()
        (legacy / "projects").mkdir(parents=True)
        view = legacy / "projects/-workspace"
        view.symlink_to(outside, target_is_directory=True)
        self.runtime._session_view(row, "cleanup-test", cwd)
        self.assertTrue(view.is_symlink())
        view.unlink()
        session = self.runtime._root(row) / "home/.claude/projects" / cwd.replace("/", "-")
        view.symlink_to(session, target_is_directory=True)
        self.runtime._session_view(row, "cleanup-test", cwd)
        self.assertFalse(legacy.exists())
        self.assertTrue(session.is_dir())

    def test_statusline_restore_preserves_explicit_user_change(self) -> None:
        """运行期间用户替换状态栏时，旧快照不能覆盖用户的新配置。@return None。"""
        row = self.runtime._row("synthetic", 1)
        settings = self.runtime._root(row) / "home/.claude/settings.json"
        current = {"statusLine": {"type": "command", "command": "printf user-change"}}
        atomic_json(settings, current)
        self.runtime._restore_cli_quota({"row": row, "statusline_before": {"present": False, "value": None},
            "statusline_command": "managed-command"})
        self.assertEqual(current, json.loads(settings.read_text()))

    def test_project_view_uses_opaque_physical_directory(self) -> None:
        """CLI 的真实 cwd 不含 run ID，旧路径只保留宿主兼容链接。@return None。"""
        row = self.runtime._row("synthetic", 1)
        configuration = self.runtime._root(row) / "home" / ".claude.json"
        original = {"oauthAccount": {"accountUuid": "synthetic"}, "userID": "fixed-user",
            "projects": {"/other/project": {"allowedTools": ["Read"]}}}
        atomic_json(configuration, original)
        compatibility = self.runtime._root(row) / "workspaces" / "internal-run-id"
        compatibility.mkdir(parents=True)
        (compatibility / "fixture.txt").write_text("synthetic")
        cwd = self.runtime._project_view(row, "internal-run-id")
        alias = Path(cwd).name
        physical = self.runtime._root(row) / "projects" / alias
        self.assertRegex(cwd, r"^/home/node/projects/project-[0-9a-f]{12}$")
        self.assertTrue(compatibility.is_symlink())
        self.assertEqual(physical.resolve(), compatibility.resolve())
        self.assertEqual("synthetic", (physical / "fixture.txt").read_text())
        self.assertNotIn("internal-run-id", cwd)
        self.assertEqual([alias], [path.name for path in physical.parent.iterdir()])
        persisted = json.loads(configuration.read_text())
        self.assertEqual(original["oauthAccount"], persisted["oauthAccount"])
        self.assertEqual(original["userID"], persisted["userID"])
        self.assertEqual(original["projects"]["/other/project"], persisted["projects"]["/other/project"])
        self.assertTrue(persisted["projects"][cwd]["hasTrustDialogAccepted"])
        with self.database() as connection:
            connection.execute("CREATE TABLE runs(id TEXT PRIMARY KEY,environment_id TEXT)")
            connection.execute("INSERT INTO runs VALUES(?,?)", ("internal-run-id", row["environment_id"]))
        self.runtime._session_view(row, "internal-run-id", cwd)
        self.assertTrue(self.runtime.run_session_path("internal-run-id").is_dir())
        self.assertFalse((physical / ".claude-home").exists())

    def test_reprofile_requires_empty_unbound_environment_and_preserves_credentials(self) -> None:
        """显式校正保留 HOME 凭据，不人为要求重新授权。@return None。"""
        with self.database() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=NULL WHERE id=1")
            connection.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY,account_id INTEGER)")
            connection.execute("CREATE TABLE runs(id TEXT PRIMARY KEY,account_id INTEGER)")
        row = self.runtime._row("synthetic", 1)
        legacy = json.loads(row["fingerprint_json"])
        legacy.pop("profile_version")
        self.runtime._update(row, fingerprint_json=json.dumps(legacy))
        replacement = {"profile_version": 2, "hostname": "b" * 12, "machine_id": "c" * 32,
            "mac": "02:10:20:30:40:50", "tz": "America/Los_Angeles", "lang": "en_US.UTF-8"}
        self.fingerprint.return_value = replacement
        credentials = self.runtime._root(row) / "home" / ".claude" / ".credentials.json"
        credentials.parent.mkdir(parents=True)
        credentials.write_text('{"claudeAiOauth":{"accessToken":"synthetic"}}')
        before = credentials.read_bytes()
        self.runtime.maintenance(row["environment_id"], "reprofile")
        current = self.runtime._row("synthetic", 1)
        self.assertEqual("stopped", current["state"])
        self.assertEqual("b" * 12, json.loads(current["fingerprint_json"])["hostname"])
        self.assertEqual(before, credentials.read_bytes())
        with self.assertRaisesRegex(ValueError, "profile v2"):
            self.runtime.maintenance(row["environment_id"], "reprofile")

    def test_generated_v3_driver_does_not_install_private_stop_hook(self) -> None:
        """实际生成 driver 并执行设置片段，防止 CLI 写私有控制目录而反复触发 Stop。@return None。"""
        row = self.runtime._row("synthetic", 1)
        root = self.runtime._root(row)
        settings = root / "home/.claude/settings.json"
        atomic_json(settings, {"model": "opus[1m]"})
        with self.database() as connection:
            connection.execute("CREATE TABLE runs(id TEXT PRIMARY KEY,environment_id TEXT,environment_generation INTEGER,execution_source TEXT,runtime_release TEXT)")
            connection.execute("INSERT INTO runs(id) VALUES('driver-test')")
        container = Mock(id="synthetic-container")
        job = {"row": row, "token": "synthetic-token", "source": "run:driver-test:0"}
        self.client.api.exec_create.return_value = {"Id": "synthetic-exec"}
        source = Path(__file__).resolve().parents[1] / "images/worker/entrypoint.sh"
        runner = object.__new__(main.Runner)
        runner.client = self.client
        runner._quota_mounts = Mock(return_value=({"QUOTA_IDENTITY": "synthetic-identity"}, {}, {}))
        with patch.object(self.runtime, "_cli_setup") as setup, \
                patch.object(self.runtime, "sync_credentials"), \
                patch.object(self.runtime, "_save_execution"), \
                patch.object(self.runtime, "_configure_network_context"), \
                patch.multiple(main, account_runtime=self.runtime, BENCH_DATA=self.root, HOST_BENCH_DATA=self.root,
                    WORKSPACES_DIR=self.root / "workspaces", FLOWS_DIR=self.root / "flows", CA_DIR=self.root / "ca"), \
                patch.dict(os.environ, {"V3_WORKER_SCRIPT": str(source)}):
            setup.return_value.__enter__.return_value = (row, container, job)
            with patch.object(main, "derive_fingerprint", return_value={"tz": "Asia/Tokyo", "lang": "ja_JP.UTF-8"}):
                runner.start_run("driver-test", {"id": 1, "name": "synthetic"},
                    {"id": 1, "prompt": "Synthetic only", "claude_code_version": "2.1.293", "model_override": ""})
        self.assertFalse((root / "workspaces/driver-test/.claude-home").exists())
        executed = self.client.api.exec_create.call_args.kwargs["environment"]
        self.assertEqual("UTC", executed["TZ"])
        self.assertEqual("en_US.UTF-8", executed["LANG"])
        self.assertEqual("en_US.UTF-8", executed["LC_ALL"])
        script = (root / "runtime/drivers" / f"job-{job['handle']}.sh").read_text()
        defaults = re.search(r"^write_default_settings\(\) \{.*?^\}$", script, re.M | re.S)
        self.assertIsNotNone(defaults)
        local_defaults = defaults.group(0).replace(f"/run/v3/jobs/{job['handle']}/", str(root / "runtime/jobs" / job["handle"]) + "/")
        subprocess.run(["bash", "-c", local_defaults + "\nwrite_default_settings\n"],
            env={**os.environ, "CLAUDE_DIR": str(settings.parent), "CLAUDE_CODE_EFFORT_LEVEL": "max"},
            capture_output=True, text=True, check=True, timeout=10)
        self.assertEqual(job["statusline_command"], json.loads(settings.read_text())["statusLine"]["command"])
        fragment = re.search(r'node - "\$CLAUDE_DIR/settings.json" <<\x27JS\x27\n(.*?)\nJS', script, re.S)
        self.assertIsNotNone(fragment)
        result = subprocess.run(["node", "-", str(settings)], input=fragment.group(1),
            capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)

        persisted = json.loads(settings.read_text())
        self.assertEqual(job["statusline_command"], persisted["statusLine"]["command"])
        self.assertNotIn("Stop", persisted["hooks"])
        self.assertEqual("opus[1m]", persisted["model"])
        subprocess.run(["bash", "-n"], input=script, text=True, check=True, timeout=10)
        session = root / "home/.claude/projects" / job["cwd"].replace("/", "-") / "complete.jsonl"
        session.parent.mkdir(parents=True, exist_ok=True)
        session.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": "Task complete."}], "stop_reason": "end_turn"}}) + "\n")
        classifier = re.search(r"^classify_claude_completion\(\) \{.*?^\}", script, re.M | re.S)
        self.assertIsNotNone(classifier)
        result = subprocess.run(["bash", "-c", classifier.group(0) + "\nclassify_claude_completion 0\n"],
            env={**os.environ, "CLAUDE_DIR": str(root / "home/.claude")},
            capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_cli_setup_disables_autoupdater_and_preserves_other_settings(self) -> None:
        """真实 CLI 准备关闭自动更新，其他模型、env 与 hooks 保持。@return None。"""
        row = self.runtime._row("synthetic", 1)
        settings = self.runtime._root(row) / "home/.claude/settings.json"
        original = {"model": "sonnet", "env": {"CLAUDE_CODE_EFFORT_LEVEL": "xhigh", "DISABLE_AUTOUPDATER": "0",
            "TZ": "Asia/Tokyo", "LANG": "ja_JP.UTF-8", "LC_ALL": "ja_JP.UTF-8"},
            "hooks": {"UserPromptSubmit": []}}
        atomic_json(settings, original)
        container = Mock()
        job = {"row": row, "token": "synthetic-token"}
        self.runtime.jobs[row["environment_id"]] = job
        with patch.object(self.runtime, "ensure", return_value=(row, container)), \
                patch.object(self.runtime, "claim", return_value=job), \
                patch.object(self.runtime, "_ensure_version"):
            with self.runtime._cli_setup({"id": 1, "name": "synthetic"}, "run:test", "2.1.293"):
                current = json.loads(settings.read_text())
        self.assertEqual("1", current["env"]["DISABLE_AUTOUPDATER"])
        self.assertEqual("UTC", current["env"]["TZ"])
        self.assertEqual("en_US.UTF-8", current["env"]["LANG"])
        self.assertEqual("en_US.UTF-8", current["env"]["LC_ALL"])
        self.assertEqual(original["env"]["CLAUDE_CODE_EFFORT_LEVEL"], current["env"]["CLAUDE_CODE_EFFORT_LEVEL"])
        self.assertEqual(original["model"], current["model"])
        self.assertEqual(original["hooks"], current["hooks"])

    def test_reprofile_rejects_existing_task_history(self) -> None:
        """已有任务历史时不能旋转画像。@return None。"""
        with self.database() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=NULL WHERE id=1")
            connection.execute("CREATE TABLE tasks(id INTEGER PRIMARY KEY,account_id INTEGER)")
            connection.execute("CREATE TABLE runs(id TEXT PRIMARY KEY,account_id INTEGER)")
            connection.execute("INSERT INTO tasks(account_id) VALUES(1)")
        row = self.runtime._row("synthetic", 1)
        legacy = json.loads(row["fingerprint_json"])
        legacy.pop("profile_version")
        self.runtime._update(row, fingerprint_json=json.dumps(legacy))
        with self.assertRaisesRegex(ValueError, "任务或运行历史"):
            self.runtime.maintenance(row["environment_id"], "reprofile")

    def test_environment_api_checks_reprofile_before_redacting_fingerprint_json(self) -> None:
        """环境响应先完成画像门禁判断，再移除内部 JSON 字段。@return None。"""
        self.runtime._row("synthetic", 1)
        with patch.object(main, "get_db", self.database), patch.object(main, "account_runtime", self.runtime):
            environment = main.v3_environments()[0]
        self.assertIn("fingerprint", environment)
        self.assertNotIn("fingerprint_json", environment)
        self.assertFalse(environment["can_reprofile"])
        self.assertIn("profile v2", environment["reprofile_message"])

    def test_environment_api_hides_deleted_accounts_and_preserves_history(self) -> None:
        """隐藏已删除账号，保留停用账号、登录草稿及历史数据。@return None。"""
        with closing(self.database()) as connection, connection:
            connection.executemany("INSERT INTO accounts(id,name,enabled,deleted_at) VALUES(?,?,?,?)", [
                (2, "disabled", 0, None),
                (3, "deleted", 0, 1.0),
                (4, "removed", 1, None),
            ])
            connection.execute("CREATE TABLE runs(id TEXT PRIMARY KEY,account_id INTEGER,environment_id TEXT)")
        self.runtime._row("synthetic", 1)
        self.runtime._row("disabled", 2)
        deleted = self.runtime._row("deleted", 3)
        self.runtime._row("removed", 4)
        self.runtime._row("pending")
        evidence = self.runtime._root(deleted) / "flows" / "history.txt"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("历史证据")
        with closing(self.database()) as connection, connection:
            connection.execute("DELETE FROM accounts WHERE id=4")
            connection.execute("INSERT INTO runs VALUES(?,?,?)", ("historical-run", 3, deleted["environment_id"]))
        with patch.object(main, "get_db", self.database), patch.object(main, "account_runtime", self.runtime):
            environments = main.v3_environments()
        self.assertEqual(["disabled", "pending", "synthetic"], [row["name"] for row in environments])
        with closing(self.database()) as connection:
            self.assertEqual(5, connection.execute("SELECT COUNT(*) FROM account_environments").fetchone()[0])
            self.assertEqual(1.0, connection.execute("SELECT deleted_at FROM accounts WHERE id=3").fetchone()[0])
            history = connection.execute("SELECT account_id,environment_id FROM runs WHERE id='historical-run'").fetchone()
        self.assertEqual((3, deleted["environment_id"]), tuple(history))
        self.assertEqual("历史证据", evidence.read_text())

    def test_legacy_reprofile_gate_is_removed_on_restart_reconcile(self) -> None:
        """管理服务重启迁回正常生命周期，画像与凭据保持。@return None。"""
        with self.database() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=NULL WHERE id=1")
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, state="profile_reauth")
        self.runtime.reconcile()
        current = self.runtime._row("synthetic", 1)
        self.assertEqual("stopped", current["state"])
        self.assertEqual(row["fingerprint_json"], current["fingerprint_json"])

    def test_reprofile_reconcile_failure_keeps_separate_gate(self) -> None:
        """遗留登录无法收口时保留画像门禁，并阻止直接开始新登录。@return None。"""
        with self.database() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=NULL WHERE id=1")
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, container_id="legacy-container", generation=1, state="profile_reauth")
        atomic_json(self.runtime._root(row) / "runtime" / "execution.json", {
            "source": "login:old", "lease": None,
        })
        container = Mock()
        container.stop.side_effect = ValueError("synthetic stop failure")
        with patch.object(self.runtime, "_container", return_value=container):
            self.runtime.reconcile()
        current = self.runtime._row("synthetic", 1)
        self.assertEqual("reconcile", current["state"])
        self.assertTrue((self.runtime._root(row) / "runtime" / "execution.json").exists())
        self.runtime._update(current, state="profile_reauth_reconcile")
        with patch.object(self.runtime, "_container", return_value=container):
            with self.assertRaisesRegex(ValueError, "对账未完成"):
                self.runtime.maintenance(current["environment_id"], "reconcile")

    def test_reprofile_active_login_is_cleaned_without_losing_gate(self) -> None:
        """重启收口遗留登录后仍回到画像重授权门禁。@return None。"""
        with self.database() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=NULL WHERE id=1")
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, container_id="legacy-container", generation=1, state="profile_reauth")
        atomic_json(self.runtime._root(row) / "runtime" / "execution.json", {
            "source": "login:old", "lease": None,
        })
        container = Mock(status="running")
        with patch.object(self.runtime, "_container", return_value=container):
            self.runtime.reconcile()
        container.stop.assert_called_once_with(timeout=5)
        self.assertEqual("stopped", self.runtime._row("synthetic", 1)["state"])
        self.assertFalse((self.runtime._root(row) / "runtime" / "execution.json").exists())

    def test_ram_and_swap_limits_remain_frozen_when_global_budget_changes(self) -> None:
        """新账号使用选定总额度，后续全局预算不能改变既有身份或限额。

        :return: None
        """
        with patch.dict(os.environ, {"V3_ACCOUNT_MEMORY": "1536m", "V3_ACCOUNT_SWAP": "2048m"}):
            row = self.runtime._row("synthetic", 1)
        self._isolated_docker()
        with patch.object(self.runtime, "_make_room"), patch.object(self.runtime, "_sender_active", return_value=0), patch.object(self.runtime, "_ensure_version"):
            current, _ = self.runtime.ensure({"id": 1, "name": "synthetic", "upstream_socks5_host": "192.0.2.2", "upstream_socks5_port": 1080}, "2.1.280")
        limits = [call.kwargs for call in self.client.containers.run.call_args_list]
        self.assertEqual(sum(item["mem_limit"] for item in limits), 1536 * 1024**2)
        self.assertEqual(sum(item["memswap_limit"] for item in limits), 3584 * 1024**2)
        self.assertEqual(current["fingerprint_json"], row["fingerprint_json"])

    def test_old_fingerprint_missing_swap_preserves_no_swap(self) -> None:
        """已有记录缺 swap 时不能随新全局配置开放额外额度。

        :return: None
        """
        row = self.runtime._row("synthetic", 1)
        fingerprint = json.loads(row["fingerprint_json"])
        del fingerprint["swap"]
        self.runtime._update(row, fingerprint_json=json.dumps(fingerprint))
        self._isolated_docker()
        with patch.dict(os.environ, {"V3_ACCOUNT_SWAP": "2048m"}), patch.object(self.runtime, "_make_room"), patch.object(self.runtime, "_sender_active", return_value=0), patch.object(self.runtime, "_ensure_version"):
            self.runtime.ensure({"id": 1, "name": "synthetic", "upstream_socks5_host": "192.0.2.2", "upstream_socks5_port": 1080}, "2.1.280")
        limits = [call.kwargs for call in self.client.containers.run.call_args_list]
        self.assertEqual(sum(item["mem_limit"] for item in limits), 4 * 1024**3)
        self.assertTrue(all(item["memswap_limit"] == item["mem_limit"] for item in limits))

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
        self.assertEqual(4, len(cursors))
        self.assertEqual(4, len({row["path"] for row in cursors}))
        for row in cursors:
            path = Path(row["path"])
            self.assertTrue((path.parent.parent if row["source"].startswith("cli:") else path.parent).is_dir())

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
        containers = self._isolated_docker()
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, generation=3, isolation_version=2,
            **{column: "old-" + role for role, column in ROLE_COLUMNS.items()})
        root = self.runtime._root(row)
        (root / "home").mkdir(parents=True)
        (root / "home/marker").write_text("preserved")
        atomic_json(self.runtime._sender_config(row), {"proxy_url": "http://old.invalid:80", "binding": {}})
        for role, column in ROLE_COLUMNS.items():
            containers[row[column]] = Mock(id=row[column], status="exited", labels=role_labels(self.runtime, row, role))
        old = list(containers.values())
        self.gateway._request.return_value = {"proxy_url": "http://u%40name:p%3Aword@new.invalid:8080", "auth_type": "oauth", "status": "active"}
        account = {"id": 1, "name": "synthetic", "cc2api_account_id": 7, "upstream_socks5_host": "old.invalid"}
        with patch("account_isolation.socket.getaddrinfo", return_value=[(None,None,None,None,("192.0.2.3",8080))]), patch.object(self.runtime, "_make_room"), patch.object(self.runtime, "_sender_active", return_value=0), patch.object(self.runtime, "_ensure_version"):
            current, _ = self.runtime.ensure(account, "2.1.280")
        for container in old:
            container.remove.assert_called_once_with()
        self.assertEqual(current["generation"], 4)
        self.assertEqual(current["fingerprint_json"], row["fingerprint_json"])
        self.assertEqual((root / "home" / "marker").read_text(), "preserved")
        self.assertEqual(self.client.containers.run.call_args_list[0].kwargs["environment"]["UPSTREAM_SOCKS5_USER"], "u@name")
        with self.database() as connection:
            saved = dict(connection.execute("SELECT * FROM accounts WHERE id=1").fetchone())
        self.assertEqual(self.runtime._proxy(saved), self.gateway._request.return_value["proxy_url"])

    def test_slow_other_account_setup_does_not_block_lease_heartbeat(self) -> None:
        """实际 ensure 在等待容器时，另一个账号仍能在正常周期续租。@return None。"""
        with self.database() as connection:
            connection.execute("INSERT INTO accounts(id,name,cc2api_account_id) VALUES(2,'other',NULL)")
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
        self._isolated_docker(container)
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
                self.runtime.ensure({"id": 2, "name": "other", "upstream_socks5_host": "192.0.2.2", "upstream_socks5_port": 1080}, "2.1.280")
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
        with patch.object(self.runtime, "_container", return_value=container), patch.object(self.runtime, "_configure_network_context"), patch.object(self.runtime, "_running_sender_active") as sender:
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
        with patch.object(self.runtime, "_container", return_value=container), patch.object(self.runtime, "_configure_network_context"):
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
        with patch.object(self.runtime, "_container", return_value=container), patch.object(self.runtime, "_configure_network_context", side_effect=ValueError("synthetic network failure")):
            with self.assertRaisesRegex(ValueError, "network failure"):
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
        containers = self._isolated_docker()
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, isolation_version=2, generation=1, state="cli_reconcile",
            **{column: role for role, column in ROLE_COLUMNS.items()})
        configuration = {"proxy_url": "", "binding": {"account_id": 7}, "quota_identity": ""}
        atomic_json(self.runtime._sender_config(row), configuration)
        for role in ROLE_COLUMNS:
            container = Mock(status="running", labels=role_labels(self.runtime, row, role))
            container.exec_run.return_value = SimpleNamespace(exit_code=0)
            containers[role] = container
        self.gateway._request.return_value = {"proxy_url": "", "auth_type": "oauth", "status": "active"}
        account = {"id": 1, "name": "synthetic", "cc2api_account_id": 7,
            "upstream_proxy_scheme": "socks5", "upstream_socks5_host": "", "upstream_socks5_port": 1080,
            "upstream_socks5_user": "", "upstream_socks5_pass": ""}
        with patch.object(self.runtime, "_sender_active", return_value=2), patch.object(self.runtime, "_ensure_version", side_effect=ValueError("CLI unavailable")) as installer:
            self.assertEqual(self.runtime.transport(account, "9.9.9"), configuration["binding"])
            installer.assert_not_called()
        self.assertEqual(self.runtime._row("synthetic", 1)["state"], "cli_reconcile")

    def test_three_role_permissions_and_secret_mount_boundaries(self) -> None:
        """普通角色不携带网络权限或其他角色秘密，配额合计保持。@return None。"""
        self._isolated_docker()
        account = {"id": 1, "name": "synthetic", "upstream_socks5_host": "192.0.2.2", "upstream_socks5_port": 1080,
            "upstream_socks5_user": "synthetic-user", "upstream_socks5_pass": "synthetic-password"}
        with patch.object(self.runtime, "_make_room"), patch.object(self.runtime, "_sender_active", return_value=0):
            row, _ = self.runtime.ensure(account)
        roles = {call.kwargs["labels"]["vibebench.role"]: call.kwargs for call in self.client.containers.run.call_args_list}
        self.assertEqual(3, len(roles))
        for role, uid in (("account", "1000:1000"), ("account-sender", "1001:1001")):
            options = roles[role]
            self.assertEqual(uid, options["user"])
            self.assertEqual(["ALL"], options["cap_drop"])
            self.assertTrue(options["read_only"])
            self.assertEqual(["no-new-privileges:true"], options["security_opt"])
            self.assertNotIn("devices", options)
            self.assertNotIn("UPSTREAM_SOCKS5_PASS", options["environment"])
        cli = roles["account"]
        mounted = {value["bind"]: value["mode"] for value in cli["volumes"].values()}
        self.assertEqual("ro", mounted["/flows/api"])
        self.assertNotIn("/ca", mounted)
        self.assertNotIn(str(self.runtime._sender_config(row).parent), cli["volumes"])
        self.assertEqual(2_000_000_000, sum(value["nano_cpus"] for value in roles.values()))
        network = roles["account-network"]
        self.assertNotIn("/home/node", {value["bind"] for value in network["volumes"].values()})

    def test_partial_creation_retains_evidence_and_stops_known_roles(self) -> None:
        """发送器创建失败不能留下可运行业务或假报 ready。@return None。"""
        containers = self._isolated_docker()
        original = self.client.containers.run.side_effect

        def fail_sender(image, **options):
            """只在第三角色注入 Docker 创建故障。"""
            if options["labels"]["vibebench.role"] == "account-sender":
                raise RuntimeError("synthetic create failure")
            return original(image, **options)

        self.client.containers.run.side_effect = fail_sender
        with patch.object(self.runtime, "_make_room"), self.assertRaisesRegex(RuntimeError, "create failure"):
            self.runtime.ensure({"id": 1, "name": "synthetic", "upstream_socks5_host": "192.0.2.2", "upstream_socks5_port": 1080})
        row = self.runtime._row("synthetic", 1)
        self.assertEqual("reconcile", row["state"])
        self.assertIsNone(row["sender_container_id"])
        self.assertEqual(2, len(containers))
        for container in containers.values():
            container.stop.assert_called_once_with(timeout=5)
        # 先核对所有归属再执行停止，避免一半已停、另一半其实属于其他部署。
        containers[row["container_id"]].labels["vibebench.deployment"] = "foreign"
        for container in containers.values():
            container.stop.reset_mock()
        with self.assertRaisesRegex(ValueError, "归属"):
            self.runtime._stop_environment(row, remove=True)
        for container in containers.values():
            container.stop.assert_not_called()

    def test_rebuild_collects_exact_orphan_after_create_registration_gap(self) -> None:
        """创建后登记前中断的角色可按精确标签收口，不漏预算或留下名称冲突。@return None。"""
        self._isolated_docker()
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, isolation_version=2, state="reconcile")
        orphan = Mock(id="orphan", labels=role_labels(self.runtime, row, "network"))
        self.client.containers.list.return_value = [orphan]
        self.runtime._stop_environment(row, remove=True)
        orphan.stop.assert_called_once_with(timeout=5)
        orphan.remove.assert_called_once_with()
        self.assertTrue(all(row[column] is None for column in ROLE_COLUMNS.values()))

    def test_legacy_upgrade_requires_explicit_rebuild_and_preserves_latest_home(self) -> None:
        """旧环境只在显式排空重建升级，备份不回写凭据。@return None。"""
        self._isolated_docker()
        with self.database() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=NULL WHERE id=1")
        row = self.runtime._row("synthetic", 1)
        self.runtime._update(row, generation=8, container_id="legacy", state="stopped")
        root = self.runtime._root(row)
        atomic_json(root / "home/.claude.json", {"userID": "d" * 64})
        atomic_json(root / "home/.claude/.credentials.json", {"latest": "synthetic-latest-rotation"})
        before = (root / "home/.claude/.credentials.json").read_bytes()
        old = Mock(id="legacy", labels=self.runtime._labels(row), status="exited")
        self.client.containers.get.side_effect = lambda identifier: old
        with self.assertRaisesRegex(ValueError, "空闲重建"):
            self.runtime.ensure({"id": 1, "name": "synthetic"})
        self.runtime.maintenance(row["environment_id"], "rebuild")
        current = self.runtime._row("synthetic", 1)
        self.assertEqual(2, current["isolation_version"])
        self.assertEqual(8, current["generation"])
        self.assertEqual(row["fingerprint_json"], current["fingerprint_json"])
        self.assertEqual(before, (root / "home/.claude/.credentials.json").read_bytes())
        self.assertTrue((root / "runtime/isolation-upgrade/before.sqlite").is_file())
        self.assertIsNone(current["container_id"])
        old.remove.assert_called_once_with()

    def test_atomic_json_and_identity_reject_link_parent_escape(self) -> None:
        """JSON 读写不能沿业务链接访问宿主其他目录，最终文件替换不改变链接目标。@return None。"""
        outside = self.root / "private-other"
        outside.mkdir()
        target = outside / "identity.json"
        atomic_json(target, {"userID": "e" * 64})
        before = target.read_bytes()
        link = self.root / "account-link"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            atomic_json(link / "identity.json", {"bad": True})
        self.assertEqual(before, target.read_bytes())
        row, home, _ = self._identity_configuration()
        home.unlink()
        home.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "缺失或损坏"):
            self.runtime.read_cli_identity(row, "2.1.293")
        atomic_json(home, {"local": True})
        self.assertFalse(home.is_symlink())
        self.assertEqual(before, target.read_bytes())

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
