"""v3 部署预检必须拒绝资源重叠及镜像错配；不操作真实 Docker。"""
import importlib.util
import ast
import io
import json
import socket
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("v3_manage", Path(__file__).with_name("manage.py"))
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class PreflightTests(unittest.TestCase):
    """验证独立部署的拒绝条件。"""

    def setUp(self) -> None:
        """准备空数据根和合成配置。@return None。"""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "v3-test"
        self.values = {"V3_DEPLOYMENT_ID": "test", "V3_DATA_ROOT": str(self.root),
            "V3_ADMIN_PASSWORD": "synthetic-admin" * 4, "V3_INTERNAL_TOKEN": "synthetic-internal" * 4,
            "V3_SESSION_SECRET": "synthetic-session" * 4, "V3_HOST_PORT": "0", "V3_MIN_FREE_MEMORY_BYTES": "1"}

    def test_old_mount_ancestor_rejects_before_start(self) -> None:
        """旧部署挂载包含新目录时必须拒绝，不能只比较字符串相等。@return None。"""
        old = [{"Name": "/old-account", "Config": {"Labels": {}},
            "Mounts": [{"Source": str(self.root.parent)}]}]
        with patch.object(manage, "command", side_effect=["old-id", json.dumps(old)]):
            with self.assertRaisesRegex(ValueError, "挂载"):
                manage.preflight(self.values)

    def test_foreign_network_name_rejects(self) -> None:
        """同名网络缺少本部署标签时不能复用。@return None。"""
        with patch.object(manage, "command", side_effect=["", '{"Name":"vibebench-v3-test"}', '[{"Labels":{}}]']):
            with self.assertRaisesRegex(ValueError, "网络"):
                manage.preflight(self.values)

    def test_real_occupied_port_rejects_without_changing_owner(self) -> None:
        """真实 socket 占用应在 up 之前失败。@return None。"""
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            self.values["V3_HOST_PORT"] = str(listener.getsockname()[1])
            with patch.object(manage, "command", side_effect=["", ""]):
                with self.assertRaises(OSError):
                    manage.preflight(self.values)
            self.assertTrue(listener.fileno() >= 0)

    def test_published_docker_nat_port_rejects_without_host_listener(self) -> None:
        """Docker 禁用 userland proxy 时，也必须检查 NAT 发布端口。@return None。"""
        self.values["V3_HOST_PORT"] = "18080"
        container = {"Name": "/old-api", "Config": {"Labels": {}}, "Mounts": [],
            "HostConfig": {"PortBindings": {"5674/tcp": [{"HostIp": "0.0.0.0", "HostPort": "18080"}]}}}
        with patch.object(manage, "command", side_effect=["old-id", json.dumps([container])]):
            with self.assertRaisesRegex(ValueError, "端口"):
                manage.preflight(self.values)

    def test_running_owned_gateway_port_allows_repeated_up(self) -> None:
        """重复启动可复用精确匹配的自有网关端口，不操作监听进程。@return None。"""
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            self.values.update(V3_HOST_PORT=str(listener.getsockname()[1]), V3_ACCOUNT_MEMORY="1536m")
            container = {"Name": "/vibebench-v3-test-gateway", "Config": {"Labels": {
                "vibebench.product": "v3", "vibebench.deployment": "test", "vibebench.role": "gateway"}},
                "Mounts": [], "State": {"Running": True},
                "HostConfig": {"PortBindings": {"5674/tcp": [{"HostIp": "127.0.0.1", "HostPort": self.values["V3_HOST_PORT"]}]}}}
            with patch.object(manage, "command", side_effect=["gateway", json.dumps([container]), ""]), \
                    patch.object(manage, "inspect_images", return_value={}), \
                    patch.object(manage.Path, "read_text", return_value="MemAvailable: 2097152 kB\nSwapFree: 0 kB\n"):
                self.assertEqual(self.root, manage.preflight(self.values))
            self.assertGreaterEqual(listener.fileno(), 0)

    def test_nonempty_unowned_data_directory_rejects(self) -> None:
        """不能把旧数据库目录标记成新的 v3 数据根。@return None。"""
        self.root.mkdir()
        database = self.root / "old.sqlite"
        database.write_bytes(b"unchanged")
        with patch.object(manage, "command", side_effect=["", ""]), patch.object(manage, "inspect_images", return_value={}):
            with self.assertRaisesRegex(ValueError, "非空"):
                manage.preflight(self.values)
        self.assertEqual(database.read_bytes(), b"unchanged")

    def test_image_digest_mismatch_rejects_even_if_tags_match(self) -> None:
        """不能以相同标签掩盖不同镜像内容。@return None。"""
        manifest = self.root.parent / "release.json"
        manifest.write_text(json.dumps({"schema": 3, "layout_version": 2, "release": "batch", "images": {
            "control": {"reference": "vibebench-v3-control:v3-batch", "digest": "sha256:expected"}}}))
        values = {"V3_RELEASE_MANIFEST": str(manifest), "V3_CONTROL_IMAGE": "vibebench-v3-control:v3-batch"}
        with patch.object(manage, "command", return_value='[{"Id":"sha256:other","Config":{"Labels":{}}}]'):
            with self.assertRaisesRegex(ValueError, "digest"):
                manage.inspect_images(values)

    def test_env_content_is_never_executed(self) -> None:
        """密码中的美元符号和反引号必须作为文本保留。@return None。"""
        path = self.root.parent / "test.env"
        path.write_text("V3_ADMIN_PASSWORD='literal$(id)`whoami`#value'\n")
        self.assertEqual(manage.load_environment(path)["V3_ADMIN_PASSWORD"], "literal$(id)`whoami`#value")

    def test_stop_only_uses_owned_roles_and_keeps_gateway_for_cli_cleanup(self) -> None:
        """先收口调度，再停账号和网关；不依赖 Compose 变量或宽泛项目名。@return None。"""
        path = self.root.parent / "stop.env"
        path.write_text("V3_DEPLOYMENT_ID=test\n")
        with patch.object(sys, "argv", ["manage.py", "stop", "--env", str(path)]), patch.object(manage, "command", side_effect=["scheduler", "", "account", "", "sender", "", "network", "", "gateway", ""]) as invoke:
            manage.main()
        calls = invoke.call_args_list
        self.assertEqual([calls[index].args[-1] for index in (0, 2, 4, 6, 8)],
            ["label=vibebench.role=" + role for role in ("orchestrator", "account", "account-sender", "account-network", "gateway")])
        self.assertEqual([calls[index].args for index in (1, 3, 5, 7, 9)],
            [("docker", "stop", name) for name in ("scheduler", "account", "sender", "network", "gateway")])

    def test_backup_refuses_running_deployment(self) -> None:
        """不能把正在变化的 HOME 与 SQLite 伪称一致回退点。@return None。"""
        self.root.mkdir()
        (self.root / ".v3-deployment.json").write_text('{"deployment":"test"}')
        target = self.root.parent / "backup"
        with patch.object(manage, "command", return_value="active-account"):
            with self.assertRaisesRegex(ValueError, "stop"):
                manage.backup(self.values, target)
        self.assertFalse(target.exists())

    def test_backup_keeps_wal_transactions_and_private_home_without_overwrite(self) -> None:
        """SQLite backup 必须包含 WAL 事务，且第二次不能覆盖首份快照。@return None。"""
        self.root.mkdir()
        (self.root / ".v3-deployment.json").write_text('{"deployment":"test"}')
        database = self.root / "bench/db.sqlite"
        database.parent.mkdir()
        with sqlite3.connect(database) as source:
            source.execute("PRAGMA journal_mode=WAL")
            source.execute("CREATE TABLE observations(value TEXT)")
            source.execute("INSERT INTO observations VALUES('synthetic')")
            source.commit()
            target = self.root.parent / "backup"
            manifest = {"layout_version": 1, "bridge_protocol": 1, "release": "synthetic"}
            socket_path = database.parent / "tmux.sock"
            (database.parent / "metadata.json").write_text('{"preserved":true}')
            (database.parent / "metadata-link").symlink_to("metadata.json")
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(socket_path))
                with patch.object(manage, "command", return_value=""), patch.object(manage, "inspect_images", return_value=manifest):
                    manage.backup(self.values, target)
                    with self.assertRaisesRegex(ValueError, "全新"):
                        manage.backup(self.values, target)
            with sqlite3.connect(target / "data/bench/db.sqlite") as snapshot:
                self.assertEqual(snapshot.execute("SELECT value FROM observations").fetchone()[0], "synthetic")
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)
            self.assertFalse((target / "data/bench/tmux.sock").exists())
            self.assertTrue((target / "data/bench/metadata-link").is_symlink())
            self.assertEqual('{"preserved":true}', (target / "data/bench/metadata-link").read_text())

    def test_backup_rotation_only_removes_owned_completed_siblings(self) -> None:
        """成功后只留本次完整备份，未知／跨部署／链接目录不参与轮换。@return None。"""
        self.root.mkdir()
        (self.root/'.v3-deployment.json').write_text('{"deployment":"test"}')
        (self.root/'preserved.txt').write_text('first')
        parent = self.root.parent/'backups'
        first,second = parent/'first',parent/'second'
        manifest = {'layout_version':2,'bridge_protocol':1,'release':'synthetic'}
        with patch.object(manage,'command',return_value=''),patch.object(manage,'inspect_images',return_value=manifest):
            manage.backup(self.values,first)
            foreign = parent/'foreign'
            shutil.copytree(first,foreign)
            marker = json.loads((foreign/'.v3-backup.json').read_text())
            marker['deployment'] = 'other'
            (foreign/'.v3-backup.json').write_text(json.dumps(marker))
            (parent/'unknown').mkdir()
            (parent/'alias').symlink_to(foreign,target_is_directory=True)
            (self.root/'preserved.txt').write_text('second')
            manage.backup(self.values,second)
        self.assertFalse(first.exists())
        self.assertEqual('second',(second/'data/preserved.txt').read_text())
        self.assertTrue((second/'.v3-backup.json').is_file())
        self.assertTrue(foreign.is_dir())
        self.assertTrue((parent/'unknown').is_dir())
        self.assertTrue((parent/'alias').is_symlink())

    def test_failed_new_backup_preserves_previous_snapshot(self) -> None:
        """新备份失败不淘汰原恢复点，不留下伪成功目录。@return None。"""
        self.root.mkdir()
        (self.root/'.v3-deployment.json').write_text('{"deployment":"test"}')
        parent = self.root.parent/'backups'
        first,second = parent/'first',parent/'second'
        manifest = {'layout_version':2,'bridge_protocol':1,'release':'synthetic'}
        with patch.object(manage,'command',return_value=''),patch.object(manage,'inspect_images',return_value=manifest):
            manage.backup(self.values,first)
            with patch.object(manage.shutil,'copytree',side_effect=OSError('synthetic disk full')):
                with self.assertRaises(OSError):
                    manage.backup(self.values,second)
        self.assertTrue((first/'.v3-backup.json').is_file())
        self.assertFalse(second.exists())

    def test_rotation_failure_keeps_new_complete_backup(self) -> None:
        """轮换删除失败也保留刚完成的恢复点，并向调用方返回失败。@return None。"""
        self.root.mkdir()
        (self.root/'.v3-deployment.json').write_text('{"deployment":"test"}')
        parent = self.root.parent/'backups'
        first,second = parent/'first',parent/'second'
        manifest = {'layout_version':2,'bridge_protocol':1,'release':'synthetic'}
        with patch.object(manage,'command',return_value=''),patch.object(manage,'inspect_images',return_value=manifest):
            manage.backup(self.values,first)
            with patch.object(manage.shutil,'rmtree',side_effect=OSError('synthetic permission denied')):
                with self.assertRaises(OSError):
                    manage.backup(self.values,second)
        self.assertTrue((first/'.v3-backup.json').is_file())
        self.assertTrue((second/'.v3-backup.json').is_file())


class ResourceBudgetTests(unittest.TestCase):
    """资源预检分别核对 RAM 与 swap，不能用宿主 swap 掩盖 RAM 不足。"""
    setUp = PreflightTests.setUp

    def _preflight(self, ram: int, swap: int, supported: bool = True):
        content = f"MemAvailable: {ram // 1024} kB\nSwapFree: {swap // 1024} kB\n"
        with patch.object(manage.Path, "read_text", return_value=content), patch.object(manage, "inspect_images", return_value={}), patch.object(manage, "command", side_effect=["", "", json.dumps(supported)]):
            return manage.preflight(self.values)

    def test_us_budget_accepts_available_ram_and_swap_separately(self) -> None:
        """明确的低预算通过预检，不再被固定 5 GiB 挡住。

        :return: None
        """
        self.values.update(V3_ACCOUNT_MEMORY="1536m", V3_ACCOUNT_SWAP="2048m")
        self.assertEqual(self._preflight(2804184 * 1024, 6639656 * 1024), self.root)

    def test_headroom_is_configurable_without_bypassing_other_checks(self) -> None:
        """低内存部署使用明确余量，仍保留账号 RAM 与 swap 验证。@return None。"""
        self.values.update(V3_ACCOUNT_MEMORY="1536m", V3_ACCOUNT_SWAP="2048m")
        self.assertEqual(self.root, self._preflight(2 * 1024**3, 3 * 1024**3))
        self.values["V3_MEMORY_HEADROOM_BYTES"] = str(1024**3)
        with self.assertRaisesRegex(ValueError, "内存不足"):
            self._preflight(2 * 1024**3, 3 * 1024**3)
        self.values["V3_MEMORY_HEADROOM_BYTES"] = "-1"
        with self.assertRaisesRegex(ValueError, "余量"):
            self._preflight(3 * 1024**3, 3 * 1024**3)

    def test_default_budget_still_requires_five_gib_ram(self) -> None:
        """默认 4g 账号仍预留管理服务余量，不能借 swap 越过物理预算。

        :return: None
        """
        with self.assertRaisesRegex(ValueError, "内存不足"):
            self._preflight(3 * 1024**3, 8 * 1024**3)

    def test_swap_shortage_and_missing_limit_support_refuse_start(self) -> None:
        """空闲 swap 不足或 Docker 不支持时都不能假称可用。

        :return: None
        """
        self.values.update(V3_ACCOUNT_MEMORY="1536m", V3_ACCOUNT_SWAP="2048m")
        with self.assertRaisesRegex(ValueError, "swap 不足"):
            self._preflight(3 * 1024**3, 1024**3)
        with self.assertRaisesRegex(ValueError, "不支持 swap"):
            self._preflight(3 * 1024**3, 3 * 1024**3, False)

    def test_explicit_ram_floor_and_active_accounts_are_respected(self) -> None:
        """显式更高门槛和多个账号都会增加真实资源要求。

        :return: None
        """
        self.values.update(V3_ACCOUNT_MEMORY="1536m", V3_ACCOUNT_SWAP="2048m", V3_MIN_FREE_MEMORY_BYTES=str(5 * 1024**3))
        with self.assertRaisesRegex(ValueError, "内存不足"):
            self._preflight(3 * 1024**3, 8 * 1024**3)
        self.values.update(V3_MIN_FREE_MEMORY_BYTES="1", V3_MAX_ACTIVE_ACCOUNTS="2")
        with self.assertRaisesRegex(ValueError, "swap 不足"):
            self._preflight(6 * 1024**3, 3 * 1024**3)

    def test_invalid_or_unlimited_budget_is_rejected(self) -> None:
        """不接受负数、无限或格式含糊的预算。

        :return: None
        """
        for ram, swap in (("0", "0"), ("1.5g", "0"), ("1536m", "-1"), ("1536m", "0g")):
            with self.subTest(ram=ram, swap=swap):
                with self.assertRaises(ValueError):
                    manage.account_limits(ram, swap)

    def test_frozen_existing_budget_cannot_be_hidden_by_lower_global_config(self) -> None:
        """既有大预算账号仍可能被唤醒，下调配置必须拒绝且不改其记录。

        :return: None
        """
        self.root.mkdir()
        (self.root / ".v3-deployment.json").write_text('{"deployment":"test"}')
        database = self.root / "bench/db.sqlite"
        database.parent.mkdir()
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE account_environments(fingerprint_json TEXT)")
            connection.execute("INSERT INTO account_environments VALUES(?)", (json.dumps({"mem": "4g"}),))
        self.values.update(V3_ACCOUNT_MEMORY="1536m", V3_ACCOUNT_SWAP="2048m")
        with patch.object(manage, "inspect_images", return_value={}), patch.object(manage, "command", side_effect=["", ""]):
            with self.assertRaisesRegex(ValueError, "固化预算"):
                manage.preflight(self.values)
        with sqlite3.connect(database) as connection:
            self.assertEqual(json.loads(connection.execute("SELECT fingerprint_json FROM account_environments").fetchone()[0]), {"mem": "4g"})


class OfflineAndStatusTests(unittest.TestCase):
    """验证离线资料不接管账号，以及状态入口不暴露服务秘密。"""
    setUp = PreflightTests.setUp

    def _prepare_offline(self):
        """使用实际 schema 建立停止部署，返回数据库路径与合成资料路径。"""
        self.root.mkdir()
        (self.root / ".v3-deployment.json").write_text('{"deployment":"test"}')
        database = self.root / "bench/db.sqlite"
        database.parent.mkdir()
        tree = ast.parse((manage.REPO / "orchestrator/main.py").read_text())
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_SCHEMA" for target in node.targets))
        with sqlite3.connect(database) as connection:
            connection.executescript(ast.literal_eval(assignment.value))
        source = self.root.parent / "offline.json"
        source.write_text((Path(__file__).parent / "fixtures/offline_metadata.json").read_text())
        return database, source

    def test_dry_run_leaves_database_unchanged_and_apply_is_idempotent(self) -> None:
        """默认演练回滚全部写入，重复显式导入不新增记录或凭据。@return None。"""
        database, source = self._prepare_offline()
        with patch.object(manage, "command", return_value=""):
            self.assertEqual(manage.import_offline(self.values, source), {"created": 3, "skipped": 0, "dry_run": True})
            with sqlite3.connect(database) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 0)
                self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='v3_offline_imports'").fetchone())
            first = manage.import_offline(self.values, source, apply=True)
            second = manage.import_offline(self.values, source, apply=True)
        self.assertEqual(first["created"], 3)
        self.assertEqual(second["skipped"], 3)
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("SELECT enabled,warmup_enabled,cc2api_account_id FROM accounts").fetchone(), (0, 0, None))
        self.assertFalse((self.root / "bench/profiles").exists())

    def test_imported_active_accounts_and_runs_are_not_resumed(self) -> None:
        """原资料启用或运行中也只能成为停用的历史记录。@return None。"""
        database, source = self._prepare_offline()
        payload = json.loads(source.read_text())
        payload["accounts"][0]["enabled"] = True
        payload["runs"][0]["status"] = "running"
        source.write_text(json.dumps(payload))
        with patch.object(manage, "command", return_value=""):
            manage.import_offline(self.values, source, apply=True)
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("SELECT enabled,warmup_enabled FROM accounts").fetchone(), (0, 0))
            self.assertEqual(connection.execute("SELECT status FROM runs").fetchone()[0], "stopped")
            self.assertIsNotNone(connection.execute("SELECT deleted_at FROM tasks").fetchone()[0])

    def test_credentials_and_existing_account_takeover_are_rejected(self) -> None:
        """拒绝凭据字段和非本来源账号，异常时不留下半次导入。@return None。"""
        database, source = self._prepare_offline()
        payload = json.loads(source.read_text())
        payload["accounts"][0]["refresh_token"] = "synthetic-secret"
        source.write_text(json.dumps(payload))
        with patch.object(manage, "command", return_value=""):
            with self.assertRaisesRegex(ValueError, "未允许字段"):
                manage.import_offline(self.values, source, apply=True)
            del payload["accounts"][0]["refresh_token"]
            source.write_text(json.dumps(payload))
            with sqlite3.connect(database) as connection:
                connection.execute("INSERT INTO accounts(name,profile_path,enabled,cc2api_account_id) VALUES('offline-synthetic','private',1,77)")
            with self.assertRaisesRegex(ValueError, "拒绝接管"):
                manage.import_offline(self.values, source, apply=True)
        with sqlite3.connect(database) as connection:
            self.assertEqual(connection.execute("SELECT enabled,cc2api_account_id FROM accounts").fetchone(), (1, 77))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)

    def test_changed_source_and_running_deployment_are_rejected(self) -> None:
        """同一来源记录改变不能覆盖；运行中的部署不能导入。@return None。"""
        _, source = self._prepare_offline()
        with patch.object(manage, "command", return_value=""):
            manage.import_offline(self.values, source, apply=True)
            payload = json.loads(source.read_text())
            payload["tasks"][0]["title"] = "changed"
            source.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
                manage.import_offline(self.values, source, apply=True)
        with patch.object(manage, "command", return_value="active-v3"):
            with self.assertRaisesRegex(ValueError, "stop"):
                manage.import_offline(self.values, source, apply=True)

    def test_status_includes_dynamic_accounts_leases_and_actual_digests(self) -> None:
        """两控制服务与两账号完整展示，旧容器和秘密不能进入输出。@return None。"""
        database, _ = self._prepare_offline()
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE account_environments(environment_id TEXT,name TEXT,account_id INTEGER,generation INTEGER,container_id TEXT,state TEXT)")
            for index in (1, 2):
                connection.execute("INSERT INTO accounts(id,name,profile_path,cc2api_account_id) VALUES(?,?,?,?)", (index, f"account-{index}", "private", index))
                connection.execute("INSERT INTO account_environments VALUES(?,?,?,?,?,?)", (str(index) * 32, f"account-{index}", index, index, f"account-{index}", "ready"))
        containers = []
        for role in ("gateway", "orchestrator", "account-1", "account-2", "legacy"):
            own = role != "legacy"
            account = role.startswith("account")
            containers.append({"Id": role, "Name": "/" + role, "Image": "sha256:" + "2" * 64 if account else "sha256:control", "State": {"Status": "running"},
                "Config": {"Env": ["TOKEN=synthetic-secret"], "Labels": {"vibebench.product": "v3", "vibebench.deployment": "test" if own else "old", "vibebench.role": "account" if account else role}}})
        manifest = {"release": "batch", "images": {"control": {"digest": "sha256:control"},
            "account": {"digest": "sha256:" + "1" * 64, "config_digest": "sha256:" + "2" * 64}}}
        snapshot = {"active": 1, "waiting": 2, "lease": {"owner": "run:test", "generation": "lease", "phase": "claimed", "expires_at": 123, "secret": "synthetic-secret"}}
        opener = Mock()
        opener.open.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps(snapshot).encode())
        output = io.StringIO()
        with patch.object(manage, "command", side_effect=["gateway orchestrator account-1 account-2 legacy", json.dumps(containers)]), patch.object(manage, "inspect_images", return_value=manifest), patch.object(manage.urllib.request, "build_opener", return_value=opener), redirect_stdout(output):
            result = manage.status(self.values)
        self.assertEqual(len(result["containers"]), 4)
        self.assertEqual(len(result["environments"]), 2)
        self.assertTrue(all(row["image_digest"] == "sha256:" + "2" * 64 for row in result["environments"]))
        self.assertTrue(all(row["matches_release"] for row in result["containers"]))
        self.assertEqual(result["environments"][0]["occupancy"]["active"], 1)
        self.assertEqual(result["environments"][0]["occupancy"]["lease"]["generation"], "lease")
        self.assertNotIn("synthetic-secret", output.getvalue())
        self.assertNotIn('"legacy"', output.getvalue())


class PublicSourceSnapshotTests(unittest.TestCase):
    """固定上游同名原件可交付，未知文件和链接仍然拒绝。"""

    def test_tracked_target_requires_whole_original_tree(self) -> None:
        """保留真实期望夹具，但额外文件或字节变化不能借目录例外进入。@return None。"""
        relative = Path('project_library/projects/docutils/seed/library/sandbox/odf2docutils/tests/presentationSimple/target')
        original = manage.REPO / relative
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / relative
            shutil.copytree(original, target)
            with patch.object(manage, 'REPO', root):
                self.assertEqual({'.env', 'local.log'}, manage.source_snapshot_ignore(str(target.parent), ['target', '.env', 'local.log']))
                extra = target / 'unknown.env'
                extra.write_text('synthetic-extra')
                with self.assertRaisesRegex(ValueError, '摘要'):
                    manage.source_snapshot_ignore(str(target.parent), ['target'])
                extra.unlink()
                tracked = target / 'oneTitle.rst'
                tracked.write_bytes(tracked.read_bytes() + b'changed')
                with self.assertRaisesRegex(ValueError, '摘要'):
                    manage.source_snapshot_ignore(str(target.parent), ['target'])

    def test_public_log_exception_does_not_allow_other_logs_or_env(self) -> None:
        """只允许精确路径和原始字节，改内容或换链接必须拒绝。@return None。"""
        relative = Path('project_library/projects/docutils/seed/library/sandbox/docutils_xml/global.log')
        original = manage.REPO / relative
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / relative
            target.parent.mkdir(parents=True)
            shutil.copyfile(original, target)
            with patch.object(manage, 'REPO', root):
                self.assertEqual({'.env', 'private.log'}, manage.source_snapshot_ignore(str(target.parent), ['global.log', '.env', 'private.log']))
                target.write_bytes(target.read_bytes() + b'changed')
                with self.assertRaisesRegex(ValueError, '摘要'):
                    manage.source_snapshot_ignore(str(target.parent), ['global.log'])
                target.unlink()
                target.symlink_to(original)
                with self.assertRaisesRegex(ValueError, '摘要'):
                    manage.source_snapshot_ignore(str(target.parent), ['global.log'])


if __name__ == "__main__":
    unittest.main()
