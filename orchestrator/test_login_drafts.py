"""登录草稿的真实 SQLite/目录回归；Docker 为隔离替身。"""
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from account_runtime import AccountRuntime, atomic_json, derive_v3_fingerprint
from login_drafts import LoginDraftStore
import main


class LoginDraftTests(unittest.TestCase):
    """验证未提交环境可见、删除归属与失败重试。"""

    def setUp(self) -> None:
        """创建私有数据库和环境，不连接真实服务器。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

        def database():
            """返回测试数据库连接。@return SQLite connection。"""
            connection = sqlite3.connect(self.root / "db.sqlite")
            connection.row_factory = sqlite3.Row
            return connection

        self.database = database
        with database() as connection:
            connection.executescript(main._SCHEMA)
        self.client = Mock()
        env = patch.dict(os.environ, {"V3_DEPLOYMENT_ID": "draft-unit", "V3_ACCOUNT_IMAGE": "fake",
            "V3_NETWORK": "fake", "V3_RELEASE": "fake", "V3_ACCOUNT_MEMORY": "1536m"})
        env.start()
        self.addCleanup(env.stop)
        self.runtime = AccountRuntime(self.client, self.root, self.root, database,
            lambda timezone: {"profile_version": 2, "hostname": "fixed", "machine_id": "a" * 32,
                "mac": "02:00:00:00:00:01", "tz": timezone or "Asia/Tokyo", "lang": "ja_JP.UTF-8"}, Mock())
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)
        self.row = self.runtime._row("new-draft")
        self.runtime._update(self.row, container_id="draft-container", generation=1, state="ready")
        self.container = Mock(id="draft-container", status="running", labels=self.runtime._labels(self.row))
        self.container.exec_run.side_effect = lambda argv, **kwargs: SimpleNamespace(exit_code=1 if argv[0] == "pgrep" else 0, output=b"")
        self.client.containers.get.return_value = self.container
        self.runtime._running_sender_active = Mock(return_value=0)
        self.runtime._configure_network_context = Mock()
        self.envroot = self.runtime._root(self.row)
        (self.envroot / "home" / ".claude").mkdir(parents=True)
        atomic_json(self.envroot / "runtime" / "sender.json", {"proxy_url": "", "binding": {"account_id": 0}})
        self.manager = main.LoginManager(self.client)
        globals_patch = patch.multiple(main, BENCH_DATA=self.root, PROFILES_DIR=self.root / "profiles",
            get_db=database, account_runtime=self.runtime, login_manager=self.manager, V3_ENABLED=True)
        globals_patch.start()
        self.addCleanup(globals_patch.stop)

    def _start(self):
        @contextmanager
        def setup(account, source, version, **kwargs):
            job = {"row": self.row, "account": account, "source": source, "lease": None, "claimed": True,
                "exclusive": True, "exec": None, "token": self.runtime.execution_token(self.container.id, source)}
            self.runtime.jobs[self.row["environment_id"]] = job
            yield self.row, self.container, job
        self.runtime._cli_setup = setup
        self.runtime.capture_login_pane = Mock(return_value="synthetic terminal")
        self.runtime.login_terminal_alive = Mock(return_value=True)
        self.manager.auth_status = Mock(return_value={"loggedIn": False})
        return main.login_start(main.LoginStartIn(name=self.row["name"]))

    def test_start_refresh_resume_restart_and_old_generation(self) -> None:
        """刷新继续原 SID，重新登录新 SID 但保留固定环境，旧代不能删除。@return None。"""
        first = self._start()
        draft = main.list_login_drafts()[0]
        self.assertEqual(main.resume_login_draft(self.row["environment_id"], main.LoginDraftActionIn(generation=draft["generation"]))["session_id"], first["session_id"])
        second = main.restart_login_draft(self.row["environment_id"], main.LoginDraftActionIn(generation=draft["generation"]))
        self.assertNotEqual(second["session_id"], first["session_id"])
        self.assertEqual(second["environment_id"], first["environment_id"])
        with self.assertRaises(HTTPException):
            main.delete_login_draft(self.row["environment_id"], draft["generation"])
        main.login_cancel(second["session_id"])
        self.assertEqual(main.list_login_drafts()[0]["state"], "cancelled")

    def test_new_login_uses_default_fingerprint_without_turning_auto_into_manual(self) -> None:
        """登录草稿默认洛杉矶，账号请求仍保留自动配置语义。@return None。"""
        self.runtime.fingerprint = derive_v3_fingerprint

        def begin(sid, account, version, force):
            """替代 Docker 登录，保留真实新草稿创建及已传入账号字段。"""
            self.assertIsNone(account["timezone"])
            row = self.runtime._row(account["name"], timezone=account["timezone"])
            profile = self.runtime._root(row) / "home/.claude"
            profile.mkdir(parents=True)
            return row, self.container, profile, "/home/node"

        with patch.object(self.runtime, "begin_login", side_effect=begin):
            session = self.manager.start("new-default", {})
        row = self.runtime._row(session.name)
        fingerprint = json.loads(row["fingerprint_json"])
        self.assertEqual("America/Los_Angeles", fingerprint["tz"])
        self.assertEqual("en_US.UTF-8", fingerprint["lang"])

    def test_active_legacy_session_is_adopted_before_commit(self) -> None:
        """旧活跃会话继续时补齐标记，仍用原 SID 并能正常提交。@return None。"""
        first = self._start()
        session = self.manager.get(first["session_id"])
        session.environment_id, session.draft_generation = None, None
        (self.root / "login-drafts" / (self.row["environment_id"] + ".json")).unlink()
        draft = main.list_login_drafts()[0]
        resumed = main.resume_login_draft(self.row["environment_id"], main.LoginDraftActionIn(generation=draft["generation"]))
        self.assertEqual(resumed["session_id"], first["session_id"])
        self.assertNotEqual(resumed["draft_generation"], draft["generation"])
        atomic_json(session.profile_dir / ".credentials.json", {"claudeAiOauth": {"accessToken": "synthetic", "refreshToken": "synthetic-rt"}})
        self.manager.auth_status.return_value = {"loggedIn": True}
        self.manager.persist_top_config = Mock()
        self.assertIn("id", main.login_commit(session.sid, main.LoginStartIn(name=session.name)))

    def test_preparing_draft_is_visible_while_start_owns_lock(self) -> None:
        """耗时初始化期间列表仍能读准备快照，不能被 owner 锁卡住。@return None。"""
        self._start()
        session = next(iter(self.manager.sessions.values()))
        main.login_cancel(session.sid)
        original = self.runtime.begin_login
        entered, proceed = threading.Event(), threading.Event()
        failures = []

        def begin(*args, **kwargs):
            entered.set()
            self.assertTrue(proceed.wait(3))
            return original(*args, **kwargs)

        def start():
            try:
                main.login_start(main.LoginStartIn(name=self.row["name"]))
            except Exception as error:
                failures.append(error)

        with patch.object(self.runtime, "begin_login", side_effect=begin):
            worker = threading.Thread(target=start)
            worker.start()
            self.assertTrue(entered.wait(2))
            before = time.monotonic()
            try:
                draft = main.list_login_drafts()[0]
                self.assertLess(time.monotonic() - before, 1)
                self.assertEqual(draft["state"], "preparing")
                self.assertFalse(draft["can_delete"])
            finally:
                proceed.set()
                worker.join(3)
        self.assertEqual(failures, [])
        self.assertFalse(worker.is_alive())

    def test_pending_local_commit_cannot_cancel_delete_or_restart(self) -> None:
        """保存失败保留意图，原 SID 可重试完成，不能用清理绕过。@return None。"""
        first = self._start()
        sid = first["session_id"]
        session = self.manager.get(sid)
        atomic_json(session.profile_dir / ".credentials.json", {"claudeAiOauth": {"accessToken": "synthetic", "refreshToken": "synthetic-rt"}})
        self.manager.auth_status.return_value = {"loggedIn": True}
        self.manager.persist_top_config = Mock()
        with patch.object(self.manager, "persist_profile_files", side_effect=OSError("synthetic IO")):
            with self.assertRaises(HTTPException):
                main.login_commit(sid, main.LoginStartIn(name=session.name))
        draft = main.list_login_drafts()[0]
        self.assertEqual(draft["state"], "submitting")
        for action in (lambda: main.login_cancel(sid),
            lambda: main.delete_login_draft(self.row["environment_id"], draft["generation"]),
            lambda: main.restart_login_draft(self.row["environment_id"], main.LoginDraftActionIn(generation=draft["generation"]))):
            with self.assertRaises(HTTPException):
                action()
        result = main.login_commit(sid, main.LoginStartIn(name=session.name))
        self.assertEqual(main.list_login_drafts(), [])
        self.assertEqual(main.login_commit(sid, main.LoginStartIn(name=session.name)), result)
        with self.assertRaises(HTTPException):
            main.delete_login_draft(self.row["environment_id"], draft["generation"])

    def test_delete_waits_for_commit_and_then_protects_saved_account(self) -> None:
        """实际请求线程竞争 owner 锁，提交先完成时删除拒绝正式环境。@return None。"""
        first = self._start()
        session = self.manager.get(first["session_id"])
        atomic_json(session.profile_dir / ".credentials.json", {"claudeAiOauth": {"accessToken": "synthetic", "refreshToken": "synthetic-rt"}})
        self.manager.auth_status.return_value = {"loggedIn": True}
        self.manager.persist_top_config = Mock()
        draft = main.list_login_drafts()[0]
        entered, proceed, deleted = threading.Event(), threading.Event(), threading.Event()
        original = self.manager.persist_profile_files
        failures = []

        def persist(sid):
            entered.set()
            self.assertTrue(proceed.wait(3))
            original(sid)

        def commit():
            try:
                main.login_commit(session.sid, main.LoginStartIn(name=session.name))
            except Exception as error:
                failures.append(error)

        def delete():
            try:
                main.delete_login_draft(self.row["environment_id"], draft["generation"])
            except HTTPException as error:
                failures.append(error.status_code)
            finally:
                deleted.set()

        with patch.object(self.manager, "persist_profile_files", side_effect=persist):
            save_thread = threading.Thread(target=commit)
            save_thread.start()
            self.assertTrue(entered.wait(2))
            delete_thread = threading.Thread(target=delete)
            delete_thread.start()
            self.assertFalse(deleted.wait(0.1))
            proceed.set()
            save_thread.join(3)
            delete_thread.join(3)
        self.assertFalse(save_thread.is_alive() or delete_thread.is_alive())
        self.assertEqual(failures, [409])
        self.container.remove.assert_not_called()

    def test_new_start_cannot_skip_commit_record_after_account_insert(self) -> None:
        """DB 已保存但 HOME 未完成时，新登录不得绕过原提交门禁。@return None。"""
        first = self._start()
        session = self.manager.get(first["session_id"])
        atomic_json(session.profile_dir / ".credentials.json", {"claudeAiOauth": {"accessToken": "synthetic", "refreshToken": "synthetic-rt"}})
        self.manager.auth_status.return_value = {"loggedIn": True}
        self.manager.persist_top_config = Mock()
        with patch.object(self.runtime, "commit_login", side_effect=OSError("synthetic HOME failure")):
            with self.assertRaises(OSError):
                main.login_commit(session.sid, main.LoginStartIn(name=session.name))
        self.assertEqual(main.list_accounts(), [])
        with self.database() as connection:
            pending_id = connection.execute("SELECT id FROM accounts").fetchone()[0]
            self.assertIsNone(main._get_available_account(connection, pending_id))
            connection.execute("UPDATE accounts SET enabled=1 WHERE id=?", (pending_id,))
            connection.commit()
            self.assertIsNone(main._get_available_account(connection, pending_id))
        # 模拟重启丢失内存名称占用；持久提交意图仍必须生效。
        another = main.LoginManager(self.client)
        with patch.object(main, "login_manager", another):
            with self.assertRaises(HTTPException):
                main.login_start(main.LoginStartIn(name=session.name))
        self.assertEqual(main.list_login_drafts()[0]["state"], "submitting")
        result = main.login_commit(session.sid, main.LoginStartIn(name=session.name))
        self.assertEqual(main.list_login_drafts(), [])
        with self.database() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT account_id FROM account_environments").fetchone()[0], result["id"])
            self.assertIsNotNone(main._get_available_account(connection, result["id"]))

    def test_restart_discovers_marker_and_validates_retained_credentials(self) -> None:
        """管理器内存丢失后从标记找 HOME，实际认证检查失败不得宣称待提交。@return None。"""
        first = self._start()
        session = self.manager.get(first["session_id"])
        atomic_json(session.profile_dir / ".credentials.json", {"synthetic": True})
        main.login_cancel(session.sid)
        new_manager = main.LoginManager(self.client)
        new_manager.auth_status = Mock(return_value={"loggedIn": False})
        self.runtime.recover_login = Mock(return_value=(self.row, self.container))
        with patch.object(main, "login_manager", new_manager):
            draft = main.list_login_drafts()[0]
            self.assertFalse(draft["credentials_ready"])
            with self.assertRaises(HTTPException):
                main.resume_login_draft(self.row["environment_id"], main.LoginDraftActionIn(generation=draft["generation"]))
            self.assertFalse(main.list_login_drafts()[0]["credentials_ready"])
            new_manager.auth_status.return_value = {"loggedIn": True}
            draft = main.list_login_drafts()[0]
            result = main.resume_login_draft(self.row["environment_id"], main.LoginDraftActionIn(generation=draft["generation"]))
            self.assertNotEqual(result["session_id"], first["session_id"])
            self.assertFalse(result["reconnectable"])
            self.assertTrue(main.list_login_drafts()[0]["credentials_ready"])

    def test_internal_cli_symlinks_can_be_removed_safely(self) -> None:
        """npm 的本树链接允许清理，跨目录链接仍由独立用例拒绝。@return None。"""
        (self.envroot / "cli").mkdir()
        (self.envroot / "cli/real-cli").write_text("synthetic")
        (self.envroot / "cli/claude").symlink_to("real-cli")
        draft = main.list_login_drafts()[0]
        self.assertTrue(main.delete_login_draft(self.row["environment_id"], draft["generation"])["ok"])

    def test_marker_cleanup_failure_after_db_delete_remains_retryable(self) -> None:
        """最后一个文件删除失败时，环境外标记仍可见且重复清理可完成。@return None。"""
        draft = main.list_login_drafts()[0]
        marker = self.root / "login-drafts" / (self.row["environment_id"] + ".json")
        original = Path.unlink

        def unlink(path, *args, **kwargs):
            if path == marker:
                raise OSError("synthetic marker IO failure")
            return original(path, *args, **kwargs)

        with patch.object(Path, "unlink", unlink):
            with self.assertRaises(HTTPException):
                main.delete_login_draft(self.row["environment_id"], draft["generation"])
        self.assertEqual(main.list_login_drafts()[0]["state"], "deleting")
        self.assertFalse(self.envroot.exists())
        self.assertTrue(main.delete_login_draft(self.row["environment_id"], draft["generation"])["ok"])
        self.assertEqual(main.list_login_drafts(), [])

    def test_invalid_metadata_is_visible_and_does_not_hide_healthy_accounts(self) -> None:
        """单条记录损坏/错归属只隔离该草稿，正式列表继续可用。@return None。"""
        with self.database() as connection:
            connection.execute("INSERT INTO accounts(name,profile_path) VALUES('healthy','profiles/healthy')")
        marker = self.root / "login-drafts" / (self.row["environment_id"] + ".json")
        for content in ("{", json.dumps({"environment_id": "b" * 32, "name": self.row["name"],
            "phase": "interrupted", "generation": "synthetic"}),
            json.dumps({"environment_id": self.row["environment_id"], "name": self.row["name"],
                "phase": "interrupted", "generation": "synthetic", "home": None})):
            marker.parent.mkdir(exist_ok=True)
            marker.write_text(content)
            draft = main.list_login_drafts()[0]
            self.assertEqual(draft["state"], "reconcile")
            self.assertFalse(draft["can_delete"] or draft["can_resume"] or draft["can_restart"])
            self.assertEqual([account["name"] for account in main.list_accounts()], ["healthy"])
            with self.assertRaises(HTTPException):
                main.delete_login_draft(self.row["environment_id"], "synthetic")
        self.container.remove.assert_not_called()
        with self.database() as connection:
            connection.execute("DELETE FROM account_environments")
        marker.write_text("{")
        self.assertEqual(main.list_login_drafts()[0]["state"], "reconcile")

    def test_legacy_status_keeps_existing_credentials_ready_contract(self) -> None:
        """旧模式仍报告已有凭据，v3 的真实认证检查由独立用例保证。@return None。"""
        session = main.LoginSession("abcdef123456", self.row["name"], None, "synthetic", {},
            self.envroot / "home/.claude", False)
        self.manager.sessions[session.sid] = session
        with patch.object(main, "account_runtime", None):
            self.assertFalse(main.login_status(session.sid, Response())["credentials_ready"])
            atomic_json(session.profile_dir / ".credentials.json", {"claudeAiOauth": {"accessToken": "synthetic"}})
            self.assertTrue(main.login_status(session.sid, Response())["credentials_ready"])

    def test_restart_preserves_not_found_after_owner_lock_race(self) -> None:
        """锁内重读不存在时保留 404，不伪称草稿仍留存。@return None。"""
        with patch.object(LoginDraftStore, "row", side_effect=[self.row, None]):
            with self.assertRaises(HTTPException) as error:
                main.restart_login_draft(self.row["environment_id"], main.LoginDraftActionIn(generation="synthetic"))
        self.assertEqual(error.exception.status_code, 404)

    def test_legacy_draft_visible_without_formal_account(self) -> None:
        """旧未提交环境能发现，且没有正式账号或可调度 ID。@return None。"""
        rows = main.list_login_drafts()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "new-draft")
        self.assertEqual(rows[0]["state"], "interrupted")
        self.assertNotIn("account_id", rows[0])
        with self.database() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 0)

    def test_delete_is_complete_and_idempotent(self) -> None:
        """删除清理唯一容器、完整 HOME/profile 和数据库，重复不越界。@return None。"""
        profile = self.root / "profiles" / self.row["name"]
        profile.mkdir(parents=True)
        (profile / ".credentials.json").write_text("synthetic")
        draft = main.list_login_drafts()[0]
        result = main.delete_login_draft(self.row["environment_id"], draft["generation"])
        self.assertTrue(result["ok"])
        self.container.stop.assert_called_once()
        self.container.remove.assert_called_once()
        self.assertFalse(self.envroot.exists())
        self.assertFalse(profile.exists())
        self.assertEqual(main.list_login_drafts(), [])
        self.assertTrue(main.delete_login_draft(self.row["environment_id"], draft["generation"])["ok"])

    def test_partial_delete_stays_visible_and_blocks_start(self) -> None:
        """Docker 清理失败不得假成功，草稿留存且阻止新登录穿过。@return None。"""
        draft = main.list_login_drafts()[0]
        self.container.remove.side_effect = OSError("synthetic Docker fault")
        with self.assertRaises(HTTPException):
            main.delete_login_draft(self.row["environment_id"], draft["generation"])
        self.assertEqual(main.list_login_drafts()[0]["state"], "deleting")
        with self.assertRaises(HTTPException):
            main.login_start(main.LoginStartIn(name=self.row["name"]))
        self.assertEqual(main.list_login_drafts()[0]["state"], "deleting")
        self.container.remove.side_effect = None
        self.assertTrue(main.delete_login_draft(self.row["environment_id"], draft["generation"])["ok"])

    def test_formal_soft_deleted_history_and_pending_are_protected(self) -> None:
        """正式/软删除、历史和未知提交都不能进入草稿删除路径。@return None。"""
        generation = main.list_login_drafts()[0]["generation"]
        for deleted in (None, 1.0):
            with self.database() as connection:
                connection.execute("INSERT INTO accounts(name,profile_path,deleted_at) VALUES(?,?,?)",
                    (self.row["name"], "profiles/" + self.row["name"], deleted))
            with self.assertRaises(HTTPException):
                main.delete_login_draft(self.row["environment_id"], generation)
            with self.database() as connection:
                connection.execute("DELETE FROM accounts")
        with self.database() as connection:
            connection.execute("INSERT INTO runs(id,task_id,account_id,environment_id) VALUES('history',1,999,?)",
                (self.row["environment_id"],))
        with self.assertRaises(HTTPException):
            main.delete_login_draft(self.row["environment_id"], generation)
        with self.database() as connection:
            connection.execute("DELETE FROM runs")
        atomic_json(self.envroot / "runtime" / "login-commit.json", {"phase": "submitting"})
        with self.assertRaises(HTTPException):
            main.delete_login_draft(self.row["environment_id"], generation)
        self.container.remove.assert_not_called()

    def test_wrong_labels_symlink_and_stale_generation_do_not_delete(self) -> None:
        """错误归属、外部链接和旧页面的换代请求在清理前拒绝。@return None。"""
        draft = main.list_login_drafts()[0]
        self.container.labels = {**self.runtime._labels(self.row), "vibebench.deployment": "other"}
        with self.assertRaises(HTTPException):
            main.delete_login_draft(self.row["environment_id"], draft["generation"])
        self.container.labels = self.runtime._labels(self.row)
        outside = self.root / "outside"
        outside.mkdir()
        (self.envroot / "home" / "danger").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(HTTPException):
            main.delete_login_draft(self.row["environment_id"], draft["generation"])
        (self.envroot / "home" / "danger").unlink()
        with self.assertRaises(HTTPException):
            main.delete_login_draft(self.row["environment_id"], "obsolete-generation")
        self.container.remove.assert_not_called()

    def test_code_http_validation_duplicate_and_unknown_delivery(self) -> None:
        """真实 ASGI 验证安全错误体与回执，重复及未知结果不能再注入。@return None。"""
        sid = self._start()["session_id"]
        self.runtime.send_login_code = Mock()
        token = "synthetic-service-token" * 2
        with patch.dict(os.environ, {"V3_INTERNAL_TOKEN": token}):
            client = TestClient(main.app)
            self.addCleanup(client.close)
            headers = {"Authorization": "Bearer " + token}
            path = f"/api/accounts/login/{sid}/code"
            self.assertEqual(client.post(path, json={"request_id": "a" * 32, "code": "private-test-code"}).status_code, 401)
            for code in ("", "private-test-code\n", 123, {"secret": "private-test-code"}, "x" * 8193):
                result = client.post(path, headers=headers, json={"request_id": "a" * 32, "code": code})
                self.assertEqual(result.status_code, 422)
                self.assertNotIn("private-test-code", result.text)
            too_large = client.post(path, headers=headers, content=b"x" * 65537)
            self.assertEqual(too_large.status_code, 413)
            self.runtime.send_login_code.assert_not_called()
            result = client.post(path, headers=headers, json={"request_id": "a" * 32, "code": "private-test-code"})
            self.assertEqual(result.json()["status"], "delivered")
            self.assertEqual(result.headers["cache-control"], "no-store")
            self.assertNotIn("private-test-code", result.text)
            duplicate = client.post(path, headers=headers, json={"request_id": "a" * 32, "code": "different-code"})
            self.assertEqual(duplicate.json(), result.json())
            self.runtime.send_login_code.assert_called_once()
            self.runtime.send_login_code.side_effect = RuntimeError("synthetic lost response")
            unknown = client.post(path, headers=headers, json={"request_id": "b" * 32, "code": "private-test-code"})
            self.assertEqual(unknown.json()["status"], "uncertain")
            queried = client.get(path + "/" + "b" * 32, headers=headers)
            self.assertEqual(queried.json(), unknown.json())
            client.post(path, headers=headers, json={"request_id": "b" * 32, "code": "private-test-code"})
            self.assertEqual(self.runtime.send_login_code.call_count, 2)

    def test_code_receipt_limit_and_expired_session(self) -> None:
        """有界回执不淘汰旧标识；会话过期拒绝新投递。@return None。"""
        sid = self._start()["session_id"]
        session = self.manager.get(sid)
        self.runtime.send_login_code = Mock()
        for number in range(32):
            result = main._send_login_code(sid, main.LoginCodeIn(request_id=f"{number:032x}", code="synthetic"))
            self.assertEqual(result["status"], "delivered")
        with self.assertRaises(HTTPException):
            main._send_login_code(sid, main.LoginCodeIn(request_id="f" * 32, code="synthetic"))

        self.assertEqual(main._send_login_code(sid, main.LoginCodeIn(request_id="0" * 32, code="synthetic"))["status"], "delivered")
        self.assertEqual(self.runtime.send_login_code.call_count, 32)
        session.code_receipts.clear()
        session.created_at = 0
        with self.assertRaises(HTTPException):
            main._send_login_code(sid, main.LoginCodeIn(request_id="f" * 32, code="synthetic"))

    def test_concurrent_code_requests_deliver_once(self) -> None:
        """两个同时到达的相同请求只注入一次，并返回同一回执。@return None。"""
        sid = self._start()["session_id"]
        entered, release = threading.Event(), threading.Event()
        receipts, errors = [], []

        def deliver(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("synthetic deadline")

        def submit():
            try:
                receipts.append(main._send_login_code(sid, main.LoginCodeIn(request_id="a" * 32, code="synthetic")))
            except Exception as error:
                errors.append(error)

        self.runtime.send_login_code = Mock(side_effect=deliver)
        first, second = threading.Thread(target=submit), threading.Thread(target=submit)
        first.start()
        try:
            self.assertTrue(entered.wait(2))
            second.start()
        finally:
            release.set()
            first.join(3)
            if second.ident is not None:
                second.join(3)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(receipts), 2)
        self.assertEqual(receipts[0], receipts[1])
        self.runtime.send_login_code.assert_called_once()

    def test_runtime_code_uses_stdin_original_tmux_and_clears_buffer(self) -> None:
        """完整执行证明绑定原 tmux，秘密不进 argv，失败后仍删 buffer。@return None。"""
        sid = self._start()["session_id"]
        session = self.manager.get(sid)
        raw = Mock()
        raw.recv.return_value = b""
        stream = Mock(_sock=raw)
        self.client.api.exec_create.return_value = {"Id": "code-exec"}
        self.client.api.exec_start.return_value = stream
        self.client.api.exec_inspect.return_value = {"Running": False, "ExitCode": 0}
        self.runtime.send_login_code(session, "a" * 32, "private-test-code")
        raw.sendall.assert_called_once_with(b"private-test-code")
        self.assertNotIn("private-test-code", str(self.client.api.exec_create.call_args))
        self.assertIn(f"/tmp/v3-login-{sid}.sock", self.client.api.exec_create.call_args.args[1])
        self.assertTrue(any("paste-buffer" in call.args[0] for call in self.container.exec_run.call_args_list))
        self.assertIn("delete-buffer", self.container.exec_run.call_args.args[0])
        stream.close.assert_called_once()
        self.runtime._update(self.row, generation=2)
        with self.assertRaises(ValueError):
            self.runtime.send_login_code(session, "b" * 32, "private-test-code")
        self.assertEqual(raw.sendall.call_count, 1)

    def test_buffer_cleanup_failure_is_uncertain_after_delivery(self) -> None:
        """可能已注入后的清理异常不能假报未发送，相同标识不得补发。@return None。"""
        sid = self._start()["session_id"]
        raw = Mock()
        raw.recv.return_value = b""
        self.client.api.exec_create.return_value = {"Id": "code-exec"}
        self.client.api.exec_start.return_value = Mock(_sock=raw)
        self.client.api.exec_inspect.return_value = {"Running": False, "ExitCode": 0}

        def execute(argv, **kwargs):
            if "delete-buffer" in argv:
                raise ValueError("synthetic buffer cleanup fault")
            return SimpleNamespace(exit_code=0, output=b"node")

        self.container.exec_run.side_effect = execute
        body = main.LoginCodeIn(request_id="a" * 32, code="synthetic")
        self.assertEqual(main._send_login_code(sid, body)["status"], "uncertain")
        self.assertEqual(main._send_login_code(sid, body)["status"], "uncertain")
        raw.sendall.assert_called_once_with(b"synthetic")

    def test_reconcile_failed_cleanup_releases_original_name_and_preserves_home(self) -> None:
        """真实目录/DB 验证旧草稿恢复，不能被遗留名称占用挡住。@return None。"""
        sid = self._start()["session_id"]
        identity = self.envroot / "home" / ".claude.json"
        atomic_json(identity, {"userID": "synthetic-fixed"})
        before = identity.read_bytes()
        self.runtime._configure_network_context.side_effect = ValueError("synthetic cleanup fault")
        with self.assertRaises(HTTPException):
            main.login_cancel(sid)
        self.assertTrue(self.manager.has_active_name(self.row["name"]))
        draft = main.list_login_drafts()[0]
        self.assertEqual(draft["state"], "reconcile")
        self.assertTrue(draft["can_reconcile"])
        self.container.status = "exited"
        result = main.reconcile_login_draft(self.row["environment_id"], main.LoginDraftActionIn(generation=draft["generation"]))
        self.assertTrue(result["ok"])
        self.assertIsNone(self.manager.get(sid))
        self.assertFalse(self.manager.has_active_name(self.row["name"]))
        self.assertEqual(identity.read_bytes(), before)
        restored = main.list_login_drafts()[0]
        self.assertEqual(restored["state"], "cancelled")
        self.assertTrue(restored["can_restart"])
        self.assertTrue(restored["can_delete"])

    def test_reconcile_rejects_live_work_unknown_proof_and_old_generation(self) -> None:
        """活跃工作、旧页面与未知证明不能经恢复入口解除保护。@return None。"""
        sid = self._start()["session_id"]
        store = LoginDraftStore(self.runtime, self.database, main._db_lock)
        record = store.record(self.row)
        body = main.LoginDraftActionIn(generation=record["generation"])
        with self.assertRaises(HTTPException):
            main.reconcile_login_draft(self.row["environment_id"], body)
        self.runtime.jobs.clear()
        self.runtime._update(self.row, state="reconcile")
        path = self.envroot / "runtime" / "execution.json"
        proof = json.loads(path.read_text())
        proof["source"] = "login:another-sid"
        atomic_json(path, proof)
        self.assertFalse(main.list_login_drafts()[0]["can_reconcile"])
        with self.assertRaises(HTTPException):
            main.reconcile_login_draft(self.row["environment_id"], body)
        proof["source"] = "login:" + sid
        atomic_json(path, proof)
        with self.assertRaises(HTTPException):
            main.reconcile_login_draft(self.row["environment_id"], main.LoginDraftActionIn(generation="old"))
        self.container.stop.assert_not_called()

    def test_proxy_summary_is_redacted_and_missing_is_unknown(self) -> None:
        """草稿代理地址可见，认证信息不进入 JSON，读取失败不冒充直连。@return None。"""
        self._start()
        path = self.envroot / "runtime" / "sender.json"
        atomic_json(path, {"proxy_source": "http://private-user:private-password@proxy.invalid:8081"})
        draft = main.list_login_drafts()[0]
        self.assertEqual(draft["proxy_summary"], "http://proxy.invalid:8081")
        self.assertTrue(draft["proxy_known"])
        self.assertNotIn("private-user", json.dumps(draft))
        self.assertNotIn("private-password", json.dumps(draft))
        path.unlink()
        self.assertFalse(main.list_login_drafts()[0]["proxy_known"])

    def test_status_ended_and_credentials_are_distinct(self) -> None:
        """终端死亡仍明确返回终态，文件存在不能冒充成功登录。@return None。"""
        session = main.LoginSession("abcdef123456", self.row["name"], "draft-container", "draft-container",
            {}, self.envroot / "home" / ".claude", False)
        self.manager.sessions[session.sid] = session
        self.runtime.capture_login_pane = Mock(side_effect=ValueError("ended"))
        self.manager.auth_status = Mock(return_value={"loggedIn": False})
        status = main.login_status(session.sid, Response())
        self.assertEqual(status["phase"], "ended")
        self.assertFalse(status["reconnectable"])
        atomic_json(session.profile_dir / ".credentials.json", {"synthetic": True})
        status = main.login_status(session.sid, Response())
        self.assertFalse(status["credentials_ready"])
