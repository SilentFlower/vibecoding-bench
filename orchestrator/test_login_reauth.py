"""关联重授权的 API/数据库/凭据文件及终端断线回归，全部使用合成数据。"""
import asyncio
import json
import os
import shutil
import socket
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from fastapi import Response, WebSocket
from account_runtime import AccountRuntime, atomic_json
from login_terminal import authorization_url
import main


def synthetic_url() -> str:
    """生成公开合成 PKCE 链接，仅供解析/展示验证。

    :return: 无真实授权数据的官方域名样本
    """
    return "https://claude.ai/oauth/authorize?" + urlencode({"client_id": "synthetic-client",
        "response_type": "code", "redirect_uri": "https://platform.claude.com/oauth/code/callback",
        "scope": "user:profile user:inference", "code_challenge": "c" * 43,
        "code_challenge_method": "S256", "state": "s" * 43})


class AuthorizationURLTests(unittest.TestCase):
    """验证完整链接、终端换行与非授权链接拒绝。"""

    def test_complete_ansi_and_hard_wrapped_link(self) -> None:
        """ANSI 和屏幕换行不能截断 query；不输出样本全文。@return None。"""
        url = synthetic_url()
        self.assertEqual(authorization_url("\x1b[32m" + url + "\x1b[0m\nPaste code here >"), url)
        wrapped = "\n".join(url[index:index + 93] for index in range(0, len(url), 93))
        self.assertEqual(authorization_url(wrapped + "\nPaste code here >"), url)

    def test_rejects_partial_malicious_and_non_https_urls(self) -> None:
        """截断 state、重复参数和主机冒充必须拒绝。@return None。"""
        url = synthetic_url()
        for invalid in (url[:-20], url.replace("https://claude.ai", "http://claude.ai"),
            url.replace("claude.ai/", "claude.ai.attacker.invalid/"), url + "&state=duplicate",
            url.replace("/oauth/authorize", "/oauth/code/callback"), url + "#fragment"):
            self.assertIsNone(authorization_url(invalid))


class BoundReauthTests(unittest.TestCase):
    """使用真实 SQLite 和 AccountRuntime 文件写入验证绑定重授权。"""

    def setUp(self) -> None:
        """隔离所有数据库和凭据，Docker exec 与远端仅为合成替身。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

        def database():
            """打开本用例的真实 SQLite。"""
            connection = sqlite3.connect(self.root / "test.sqlite")
            connection.row_factory = sqlite3.Row
            return connection

        self.database = database
        self.gateway = Mock()
        self.environment = patch.dict(os.environ, {"V3_DEPLOYMENT_ID": "reauth-unit", "V3_ACCOUNT_IMAGE": "synthetic",
            "V3_RELEASE": "synthetic-reauth", "V3_NETWORK": "synthetic-network", "V3_ACCOUNT_MEMORY": "1536m", "V3_ACCOUNT_SWAP": "2048m", "V3_MAX_ACTIVE_ACCOUNTS": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        globals_patch = patch.multiple(main, BENCH_DATA=self.root, PROFILES_DIR=self.root / "profiles", get_db=database,
            cc2api_client=self.gateway, V3_ENABLED=True, continue_manager=None)
        globals_patch.start()
        self.addCleanup(globals_patch.stop)
        main.init_db()
        with database() as connection:
            connection.execute("INSERT INTO accounts(id,name,profile_path,cc2api_account_id,enabled,warmup_enabled) VALUES(1,'synthetic','profiles/synthetic',7,0,0)")
            connection.execute("INSERT INTO account_quota_states(account_id,identity,state_json,updated_at) VALUES(1,'synthetic-identity','{\"blocked\":true}',1)")
        self.client = Mock()
        self.runtime = AccountRuntime(self.client, self.root, self.root, database,
            lambda name: {"hostname": "fixed", "machine_id": "a" * 32, "mac": "02:00:00:00:00:01", "tz": "UTC", "lang": "en_US.UTF-8"}, self.gateway)
        self.addCleanup(self.runtime.heartbeat_pool.shutdown)
        self.row = self.runtime._row("synthetic", 1)
        self.runtime._update(self.row, container_id="fixed-container", generation=1, state="ready")
        self.profile = self.root / "profiles" / "synthetic"
        self.home = self.runtime._root(self.row) / "home"
        self.identity = {"email": "synthetic@example.invalid", "account_uuid": "synthetic-account", "organization_uuid": "synthetic-org"}
        self.original = {"claudeAiOauth": {"accessToken": "old-access", "refreshToken": "old-refresh", "expiresAt": int(time.time() * 1000) + 3600000}}
        atomic_json(self.profile / ".credentials.json", self.original)
        atomic_json(self.profile / ".claude.json", {"userID": "d" * 64, "preserved": True,
            "oauthAccount": {"emailAddress": self.identity["email"], "accountUuid": self.identity["account_uuid"], "organizationUuid": self.identity["organization_uuid"]}})
        self.home.mkdir(parents=True)
        shutil.copy2(self.profile / ".claude.json", self.home / ".claude.json")
        self.runtime.sync_credentials(self.row, {"name": "synthetic", "cc2api_account_id": 7})
        self.container = Mock(id="fixed-container", labels=self.runtime._labels(self.row), status="running")
        self.container.exec_run.side_effect = lambda argv, **kwargs: SimpleNamespace(exit_code=1 if argv[0] == "pgrep" else 0, output=b"")
        self.client.containers.get.return_value = self.container
        self.client.images.get.return_value.attrs = {"Config": {"Labels": {"vibebench.product": "v3", "vibebench.role": "account", "vibebench.release": "synthetic-reauth"}}}
        self.runtime._configure_recorder = Mock()
        self.runtime._running_sender_active = Mock(return_value=0)
        self.lease = None
        self.snapshot = None
        self.gateway._request.side_effect = self.gateway_request
        self.gateway.import_credentials.side_effect = self.import_credentials
        self.gateway.import_status.side_effect = lambda account_id, operation_id: self.snapshot

        @contextmanager
        def cli_setup(account, source, version, **kwargs):
            """仅替代容器认领，仍执行真实 begin_login 和凭据文件逻辑。"""
            self.lease = {"owner": source, "generation": "synthetic-lease", "exclusive": True, "phase": "claimed", "expires_at": int(time.time()) + 1800}
            job = {"row": self.row, "account": dict(account), "source": source, "lease": dict(self.lease), "claimed": True,
                "exclusive": True, "exec": None, "lease_lock": threading.RLock(), "token": self.runtime.execution_token(self.container.id, source)}
            self.runtime.jobs[self.row["environment_id"]] = job
            yield self.row, self.container, job

        self.runtime._cli_setup = cli_setup
        self.manager = main.LoginManager(self.client)
        self.manager.auth_status = Mock(return_value={"loggedIn": True, "authMethod": "oauth"})
        self.runtime.capture_login_pane = Mock(return_value=synthetic_url())
        login_patch = patch.multiple(main, account_runtime=self.runtime, login_manager=self.manager)
        login_patch.start()
        self.addCleanup(login_patch.stop)

    def gateway_request(self, method: str, path: str, body=None) -> dict:
        """模拟门禁与身份配置，并检查释放前已销毁暂存 RT。

        :param method: HTTP 方法
        :param path: 受控管理路径
        :param body: 租约操作
        :return: 无真实凭据的配置/租约
        """
        if path.endswith("/config"):
            return {"account_id": 7, "auth_type": "oauth", "status": "disabled", "proxy_url": "", **self.identity}
        if method == "POST":
            if body["operation"] == "fence":
                self.lease["phase"] = "reconcile"
            elif body["operation"] == "release":
                self.assertFalse(any((self.home / ".v3-login").glob("*/.claude/.credentials.json")))
                self.lease = None
        return {"lease": self.lease, "active": 0, "waiting": 0, "importing": 0}

    def import_credentials(self, account_id: int, payload: dict) -> dict:
        """模拟原关联账号事务成功，不访问外部 OAuth。

        :param account_id: 原关联 ID
        :param payload: 合成凭据输入
        :return: 最小权威快照
        """
        self.assertEqual(account_id, 7)
        self.snapshot = {"account_id": 7, **{key: payload[key] for key in ("access_token", "refresh_token", "expires_at")}}
        return self.snapshot

    def start_login(self, authenticate: bool = True) -> main.LoginSession:
        """执行真实 start，并可注入合成 CLI 登录产物。

        :param authenticate: 是否模拟 CLI 已完成登录
        :return: 本次登录会话
        """
        result = main.login_start(main.LoginStartIn(name="synthetic", force_reauth=True))
        session = self.manager.get(result["session_id"])
        self.assertNotIn("oauthAccount", json.loads((session.profile_dir.parent / ".claude.json").read_text()))
        if authenticate:
            atomic_json(session.profile_dir / ".credentials.json", {"claudeAiOauth": {"accessToken": "new-access", "refreshToken": "new-refresh", "expiresAt": int(time.time() * 1000) + 3600000}})
            atomic_json(session.profile_dir.parent / ".claude.json", {"userID": "unexpected-new-device",
                "oauthAccount": {"emailAddress": self.identity["email"], "accountUuid": self.identity["account_uuid"], "organizationUuid": self.identity["organization_uuid"]}})
        return session

    def test_bound_commit_syncs_same_account_preserves_policy_and_only_publishes_at(self) -> None:
        """API 到管理 profile/HOME/DB 的完整本地路径。@return None。"""
        session = self.start_login()
        result = main.login_commit(session.sid, main.LoginStartIn(name="synthetic", force_reauth=True))
        self.assertEqual(result["cc2api_account_id"], 7)
        self.assertTrue(result["credentials_synced"])
        self.assertEqual(json.loads((self.profile / ".credentials.json").read_text())["claudeAiOauth"]["refreshToken"], "new-refresh")
        runtime_oauth = json.loads((self.home / ".claude" / ".credentials.json").read_text())["claudeAiOauth"]
        self.assertEqual(runtime_oauth["accessToken"], "new-access")
        self.assertNotIn("refreshToken", runtime_oauth)
        self.assertEqual(json.loads((self.home / ".claude.json").read_text())["userID"], "d" * 64)
        with self.database() as connection:
            account = connection.execute("SELECT * FROM accounts WHERE id=1").fetchone()
            self.assertEqual((account["enabled"], account["warmup_enabled"], account["cc2api_account_id"]), (0, 0, 7))
            self.assertEqual(connection.execute("SELECT state_json FROM account_quota_states WHERE account_id=1").fetchone()[0], '{"blocked":true}')
        self.assertEqual(main.login_commit(session.sid, main.LoginStartIn(name="synthetic")), result)
        self.gateway.import_credentials.assert_called_once()

    def test_wrong_login_and_missing_uuid_do_not_overwrite_original_credentials(self) -> None:
        """身份不符时提交前拒绝，取消也保留旧 profile。@return None。"""
        session = self.start_login()
        atomic_json(session.profile_dir.parent / ".claude.json", {"oauthAccount": {"emailAddress": self.identity["email"]}})
        with self.assertRaises(main.HTTPException):
            main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
        self.gateway.import_credentials.assert_not_called()
        self.assertEqual(json.loads((self.profile / ".credentials.json").read_text()), self.original)
        main.login_cancel(session.sid)
        self.assertFalse(session.profile_dir.exists())

    def test_identity_conflicts_and_changed_binding_are_rejected_before_import(self) -> None:
        """错 UUID/邮箱/组织和提交前绑定变化均不能写入其它账号。@return None。"""
        for field in ("accountUuid", "emailAddress", "organizationUuid"):
            with self.subTest(field=field):
                session = self.start_login()
                top = json.loads((session.profile_dir.parent / ".claude.json").read_text())
                top["oauthAccount"][field] = "wrong-identity"
                atomic_json(session.profile_dir.parent / ".claude.json", top)
                with self.assertRaises(main.HTTPException) as failure:
                    main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
                self.assertEqual(failure.exception.status_code, 409)
                self.gateway.import_credentials.assert_not_called()
                main.login_cancel(session.sid)
        session = self.start_login()
        with self.database() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=8 WHERE id=1")
        with self.assertRaises(main.HTTPException) as failure:
            main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
        self.assertEqual(failure.exception.status_code, 409)
        self.gateway.import_credentials.assert_not_called()
        with self.database() as connection:
            connection.execute("UPDATE accounts SET cc2api_account_id=7 WHERE id=1")
        main.login_cancel(session.sid)

    def test_lost_import_reply_retries_from_receipt_without_reimporting(self) -> None:
        """远端成功但响应丢失时保留数据，通过回执幂等完成。@return None。"""
        session = self.start_login()

        def dropped_reply(account_id, payload):
            """事务完成后模拟连接中断。"""
            self.import_credentials(account_id, payload)
            raise ConnectionError("合成断网")

        self.gateway.import_credentials.side_effect = dropped_reply
        with self.assertRaises(main.HTTPException) as failure:
            main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
        self.assertEqual(failure.exception.status_code, 503)
        self.assertTrue(session.commit_context["path"].exists())
        self.assertTrue(session.profile_dir.exists())
        self.manager.sweep_expired()
        self.assertIs(self.manager.get(session.sid), session)
        result = main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
        self.assertTrue(result["credentials_synced"])
        self.gateway.import_credentials.assert_called_once()

    def test_cancel_unknown_commit_fences_and_mirrors_confirmed_result(self) -> None:
        """取消已提交会话只关闭终端，不回滚新凭据。@return None。"""
        session = self.start_login()

        def dropped_reply(account_id, payload):
            """保存回执后丢失响应。"""
            self.import_credentials(account_id, payload)
            raise ConnectionError("合成断网")

        self.gateway.import_credentials.side_effect = dropped_reply
        with self.assertRaises(main.HTTPException):
            main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
        main.login_cancel(session.sid)
        self.assertEqual(json.loads((self.profile / ".credentials.json").read_text())["claudeAiOauth"]["refreshToken"], "new-refresh")
        self.assertFalse(session.commit_context["path"].exists())
        self.assertIsNone(self.lease)

    def test_login_status_recovers_link_without_ws_and_rejects_expired_session(self) -> None:
        """未连接终端也能取得链接；状态不可缓存。@return None。"""
        session = self.start_login(authenticate=False)
        response = Response()
        state = main.login_status(session.sid, response)
        self.assertEqual(state["authorization_url"], synthetic_url())
        self.assertEqual(response.headers["cache-control"], "no-store")
        session.created_at -= 1801
        with self.assertRaises(main.HTTPException) as expired:
            main.login_status(session.sid, Response())
        self.assertEqual(expired.exception.status_code, 410)

    def test_local_partial_write_keeps_stage_and_retry_uses_remote_receipt(self) -> None:
        """管理 profile 成功而 HOME 写入失败时不释放门禁。@return None。"""
        session = self.start_login()

        def failed_home_write(path, value, mode=0o600):
            """只在第二阶段 HOME 写入处模拟磁盘错误。"""
            if path == self.home / ".claude.json":
                raise OSError("合成磁盘失败")
            atomic_json(path, value, mode)

        with patch("account_runtime.atomic_json", side_effect=failed_home_write):
            with self.assertRaises(main.HTTPException) as failed:
                main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
        self.assertEqual(failed.exception.status_code, 500)
        self.assertTrue(session.profile_dir.exists())
        self.assertIsNotNone(self.lease)
        self.assertEqual(json.loads((self.profile / ".credentials.json").read_text())["claudeAiOauth"]["refreshToken"], "new-refresh")
        self.assertTrue(main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))["credentials_synced"])
        self.gateway.import_credentials.assert_called_once()

    def test_restart_reconciles_committed_record_without_login_manager_memory(self) -> None:
        """遗留持久记录先对账，再清暂存和释放门禁。@return None。"""
        session = self.start_login()

        def dropped_reply(account_id, payload):
            """成功提交后丢弃 HTTP 响应。"""
            self.import_credentials(account_id, payload)
            raise ConnectionError("合成断网")

        self.gateway.import_credentials.side_effect = dropped_reply
        with self.assertRaises(main.HTTPException):
            main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
        self.runtime.jobs.clear()
        self.manager.sessions.clear()
        self.manager._name_locks.clear()
        self.runtime.reconcile()
        self.assertEqual(json.loads((self.profile / ".credentials.json").read_text())["claudeAiOauth"]["refreshToken"], "new-refresh")
        self.assertFalse(session.commit_context["path"].exists())
        self.assertFalse(session.profile_dir.exists())
        self.assertIsNone(self.lease)

    def test_unknown_reconcile_stays_closed_until_receipt_is_confirmed(self) -> None:
        """不能查询回执时保留暂存；明确未提交后才允许取消。@return None。"""
        session = self.start_login()
        self.gateway.import_credentials.side_effect = ConnectionError("合成请求未到达")
        with self.assertRaises(main.HTTPException):
            main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
        self.gateway.import_status.side_effect = ConnectionError("合成查询断网")
        self.runtime.reconcile()
        self.assertTrue(session.commit_context["path"].exists())
        self.assertTrue(session.profile_dir.exists())
        self.assertIsNotNone(self.lease)
        self.assertEqual(self.runtime._row("synthetic", 1)["state"], "reconcile")
        self.gateway.import_status.side_effect = lambda account_id, operation_id: None
        self.runtime.reconcile()
        self.assertFalse(session.commit_context["path"].exists())
        self.assertIsNone(self.lease)
        self.assertEqual(json.loads((self.profile / ".credentials.json").read_text()), self.original)

    def test_environment_reconcile_clears_old_session_and_reuses_commit_receipt(self) -> None:
        """实际环境维护入口可收口待提交登录，并给旧页面返回幂等结果。@return None。"""
        session = self.start_login()

        def dropped_reply(account_id, payload):
            """远端成功后丢失响应。"""
            self.import_credentials(account_id, payload)
            raise ConnectionError("合成断网")

        self.gateway.import_credentials.side_effect = dropped_reply
        with self.assertRaises(main.HTTPException):
            main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))
        main.v3_environment_maintenance(self.row["environment_id"], {"operation": "reconcile"})
        self.assertFalse(self.manager.has_active_name("synthetic"))
        self.assertTrue(main.login_commit(session.sid, main.LoginStartIn(name="synthetic"))["credentials_synced"])

    def test_normal_execution_keeps_rejecting_inactive_bound_account(self) -> None:
        """登录专用放行不能扩大普通执行准入。@return None。"""
        with self.assertRaisesRegex(ValueError, "状态不可用"):
            self.runtime.ensure({"id": 1, "name": "synthetic", "cc2api_account_id": 7})

    def test_environment_reconcile_waits_for_account_credential_owner(self) -> None:
        """环境页对账不能在同账号提交/绑定仍持锁时开始镜像。@return None。"""
        started, entered = threading.Event(), threading.Event()
        failures = []
        self.runtime.maintenance = Mock(side_effect=lambda *args: entered.set())

        def maintenance():
            """在另一请求线程调用真实维护入口，捕获错误供主线程断言。"""
            started.set()
            try:
                main.v3_environment_maintenance(self.row["environment_id"], {"operation": "reconcile"})
            except Exception as error:
                failures.append(error)

        with main._oauth_owner_lock("synthetic"):
            worker = threading.Thread(target=maintenance)
            worker.start()
            self.assertTrue(started.wait(2))
            self.assertFalse(entered.wait(0.1))
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertTrue(entered.is_set())
        self.assertEqual(failures, [])


class LoginWebSocketTests(unittest.TestCase):
    """验证首个转发结束会取消另一方向，断线不销毁登录会话。"""

    def test_pty_eof_closes_half_open_ws_without_cleaning_login(self) -> None:
        """真实 socket EOF 不能让 WS receive 永久挂起。@return None。"""
        async def exercise():
            """运行实际异步路由，不调用 Docker。"""
            raw, peer = socket.socketpair()
            raw.setblocking(False)
            peer.sendall(b"synthetic terminal\r\n")
            peer.close()
            output = []
            connected = False

            async def receive():
                """模拟浏览器保持打开且没有新输入。"""
                nonlocal connected
                if not connected:
                    connected = True
                    return {"type": "websocket.connect"}
                await asyncio.Future()

            async def send(message):
                """收集实际 WS 消息。"""
                output.append(message)

            websocket = WebSocket({"type": "websocket", "path": "/api/accounts/login/ws/abcdef123456", "headers": []}, receive, send)
            session = SimpleNamespace(worker_id="synthetic", home="/home/node", sidecar_id=None, phase="authorizing", created_at=time.time())
            manager = Mock()
            manager.get.return_value = session
            manager.client.api.exec_create.return_value = {"Id": "synthetic-exec"}
            manager.client.api.exec_start.return_value = raw
            with patch.multiple(main, login_manager=manager, account_runtime=Mock(), V3_ENABLED=False):
                await asyncio.wait_for(main.login_ws(websocket, "abcdef123456"), timeout=2)
            self.assertTrue(any(message.get("bytes") == b"synthetic terminal\r\n" for message in output))
            manager.cleanup.assert_not_called()
            self.assertEqual(raw.fileno(), -1)

        asyncio.run(exercise())
