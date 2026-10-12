"""v3 服务与终端鉴权测试，不创建账号或连接 Docker。"""
import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import Request, Response, WebSocket
from account_runtime import AccountRuntime
import main


class V3AuthTests(unittest.TestCase):
    """验证 SID 不能替代登录、票据限定路径且不同于服务秘密。"""

    def setUp(self) -> None:
        """使用公开合成秘密，隔离所有真实配置。@return None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

        def database():
            """返回隔离的会话与账号数据库。"""
            connection = sqlite3.connect(self.root / "test.sqlite")
            connection.row_factory = sqlite3.Row
            return connection

        self.database = database
        with database() as connection:
            connection.execute("CREATE TABLE accounts(id INTEGER PRIMARY KEY, name TEXT, deleted_at REAL, cc2api_account_id INTEGER)")
        db_patch = patch.object(main, "get_db", database)
        db_patch.start()
        self.addCleanup(db_patch.stop)
        self.secret = "synthetic-internal-token-" * 3
        context = patch.multiple(main, V3_ENABLED=True, WEBUI_USER="v3", WEBUI_PASS="synthetic-password", _SESSION_SECRET="synthetic-session-key",
            _SESSION_COOKIE="vb_v3_session")
        context.start()
        self.addCleanup(context.stop)
        environment = patch.dict(os.environ, {"V3_INTERNAL_TOKEN": self.secret})
        environment.start()
        self.addCleanup(environment.stop)
        self.cookie = main._make_session_token("v3")

    def _request(self, path="/api/topics", secret=None) -> Request:
        headers = [(b"cookie", f"vb_v3_session={self.cookie}".encode())]
        if secret:
            headers.append((b"authorization", f"Bearer {secret}".encode()))
        return Request({"type": "http", "method": "GET", "path": path,
            "scheme": "http", "server": ("test", 80), "query_string": b"", "headers": headers})

    def test_private_http_rejects_browser_cookie_without_service_auth(self) -> None:
        """浏览器不能直接靠 cookie 调用内部服务。@return None。"""
        called = []

        async def next_handler(request):
            """记录是否进入实际业务路由。"""
            called.append(request)

        response = asyncio.run(main.session_auth_middleware(self._request(), next_handler))
        self.assertEqual(response.status_code, 401)
        self.assertFalse(called)

    def test_terminal_ticket_is_bound_to_path_cookie_and_expiration(self) -> None:
        """合法登录 cookie 和具体路径票据缺一不可。@return None。"""
        path = "/api/accounts/login/ws/abcdef123456"
        ticket = main.v3_terminal_ticket(self._request(), {"path": path})["ticket"]
        scope = {"type": "websocket", "path": path, "scheme": "ws", "server": ("test", 80),
            "query_string": ("ticket=" + ticket).encode(),
            "headers": [(b"authorization", f"Bearer {self.secret}".encode()),
                (b"cookie", f"vb_v3_session={self.cookie}".encode())]}
        websocket = WebSocket(scope, Mock(), Mock())
        self.assertTrue(main._v3_websocket_authorized(websocket))
        changed = dict(scope, path="/api/run-continue/ws/abcdef123456")
        self.assertFalse(main._v3_websocket_authorized(WebSocket(changed, Mock(), Mock())))
        self.assertFalse(main._v3_websocket_authorized(WebSocket(dict(scope, query_string=b""), Mock(), Mock())))
        self.assertFalse(main._v3_websocket_authorized(WebSocket(dict(scope, headers=[]), Mock(), Mock())))
        with patch("main.time.time", return_value=2**40):
            self.assertFalse(main._v3_websocket_authorized(websocket))

    def test_session_exchange_sets_separate_httponly_cookie_without_secret(self) -> None:
        """统一后台只交换会话，不向前端返回服务凭据。@return None。"""
        response = main.v3_session_grant()
        self.assertEqual(json.loads(response.body), {"ok": True})
        cookie = response.headers["set-cookie"]
        self.assertIn("vb_v3_session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Path=/runtime", cookie)
        self.assertNotIn(self.secret, cookie)

    def test_logout_revokes_replayed_cookie_and_previously_issued_ticket(self) -> None:
        """清除 Cookie 后，复制的旧 Cookie 和既有票据也不能再次使用。@return None。"""
        self.assertEqual(main._verify_session_token(self.cookie), "v3")
        response = Response()
        main.auth_logout(self._request(), response)
        self.assertIn("Path=/runtime", response.headers["set-cookie"])
        self.assertIsNone(main._verify_session_token(self.cookie))
        with self.assertRaises(main.HTTPException) as error:
            main.v3_terminal_ticket(self._request(), {"path": "/api/accounts/login/ws/abcdef123456"})
        self.assertEqual(error.exception.status_code, 401)
        self.assertEqual(main.auth_logout(self._request(), Response()), {"ok": True})

    def test_password_rotation_invalidates_session_and_other_sessions_remain_on_logout(self) -> None:
        """退出只撤销当前会话，管理密码轮换撤销所有旧签名。@return None。"""
        other = main._make_session_token("v3")
        self.assertNotEqual(self.cookie, other)
        main.auth_logout(self._request(), Response())
        self.assertEqual(main._verify_session_token(other), "v3")
        with patch.object(main, "WEBUI_PASS", "rotated-synthetic-password"):
            self.assertIsNone(main._verify_session_token(other))

    def test_web_login_passes_runtime_account_proxy_fields(self) -> None:
        """执行真实登录入口和 LoginManager，验证 DTO 到 Runtime 的边界。@return None。"""
        runtime = Mock()
        container = Mock(id="synthetic-container")
        runtime.begin_login.return_value = ({}, container, self.root / ".claude", "/home/node")
        manager = main.LoginManager(Mock())
        with patch.multiple(main, account_runtime=runtime, login_manager=manager), patch.object(main, "effective_claude_code_version", return_value="2.1.280"):
            result = main.login_start(main.LoginStartIn(name="synthetic", timezone="Asia/Tokyo", upstream_proxy_scheme="http",
                upstream_socks5_host="proxy.invalid", upstream_socks5_port=8080,
                upstream_socks5_user="u@name", upstream_socks5_pass="p:word"))
        account = runtime.begin_login.call_args.args[1]
        self.assertEqual(AccountRuntime._proxy(account), "http://u%40name:p%3Aword@proxy.invalid:8080")
        self.assertEqual(account["timezone"], "Asia/Tokyo")
        self.assertIn(result["session_id"], manager.sessions)


if __name__ == "__main__":
    unittest.main()
