"""用部署者拥有的合成配置检查本机提供方的地址和文件归属边界。"""

from contextlib import nullcontext
from hashlib import sha256
from http.client import HTTPResponse
import json
import os
from subprocess import run
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.utils import formatdate
from pathlib import Path
from socket import SHUT_WR, socketpair
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
from unittest import TestCase, skipUnless
from unittest.mock import patch

import tui_sender_launch as launch
from tui_direct_admin import update_binding
from tui_direct_selection import DIRECT_DIRECTORY


class ManagedOAuthTests(TestCase):
    """受管凭据只随匹配的账号模型请求走原 sender。"""

    @skipUnless(os.geteuid() == 0, '管理员选择器测试需要 root')
    def test_direct_proxy_uses_each_current_sender_and_node(self):
        """同节点和跨节点的选择器保持原策略、代次及对应代理。@return 无。"""
        engine = Path(launch.__file__).with_name('tui-direct-mod') / 'hooks/engine.js'
        hook = sha256(engine.read_bytes()).hexdigest()
        with TemporaryDirectory() as directory, patch.dict(os.environ, {
                'V3_TUI_DIRECT': '1', 'V3_TUI_MANAGED_POLICY': '1'}):
            root = Path(directory)
            central, remote = root / 'central', root / 'remote'
            central.mkdir()
            remote.mkdir()
            cases = [(central, 12, 'a' * 32, 3), (central, 21, 'b' * 32, 7), (remote, 13, 'c' * 32, 9)]
            for node, account, environment, _ in cases:
                update_binding(node, account_id=account, environment_id=environment, publish=True)
            for node, account, environment, generation in cases:
                identity = {'account_id': account, 'environment_id': environment}
                binding = {**identity, 'generation': generation}
                proxy = f'socks5://192.0.2.{account}:1080'
                policy = {**identity, 'managed_order': True, 'direct_hook_sha256': hook}
                config = {'binding': binding, 'proxy_url': proxy, 'allowed_origin': launch.ACCOUNT_ORIGIN,
                          'tui_direct': True, 'tui_managed_policy': policy}
                config_path = root / f'{account}.json'
                config_path.write_text(json.dumps(config))
                other = remote if node == central else central
                with (patch.object(launch, 'DIRECT_SELECTION', node / DIRECT_DIRECTORY),
                      patch.dict(os.environ, {'V3_SENDER_CONFIG': str(config_path)})):
                    self.assertEqual(launch.direct_proxy(binding), proxy)
                    for mismatch in ({'account_id': 22}, {'environment_id': 'd' * 32}, {'generation': generation + 1}):
                        with self.assertRaisesRegex(ValueError, '账号绑定已变化'):
                            launch.direct_proxy({**binding, **mismatch})
                    with patch.object(launch, 'DIRECT_SELECTION', other / DIRECT_DIRECTORY):
                        with self.assertRaisesRegex(ValueError, '直发开关已关闭'):
                            launch.direct_proxy(binding)
                    config_path.write_text(json.dumps({**config, 'tui_managed_policy': {**policy, 'account_id': 23}}))
                    with self.assertRaisesRegex(ValueError, '管理员 Mod'):
                        launch.direct_proxy(binding)
                    config_path.write_text(json.dumps(config))
                    if account == 12:
                        update_binding(node, account_id=account, environment_id=environment, publish=False)
                        with self.assertRaisesRegex(ValueError, '直发开关已关闭'):
                            launch.direct_proxy(binding)
                        config_path.write_text(json.dumps({**config, 'tui_direct_from_release': True}))
                        self.assertEqual(launch.direct_proxy(binding), proxy)
                        with self.assertRaisesRegex(ValueError, '账号绑定已变化'):
                            launch.direct_proxy({**binding, 'account_id': 21})

    def test_managed_policy_guard_requires_same_account_and_generation(self):
        """策略守卫只在真实账号模式和本代预留同时成立时启用。@return 无。"""
        binding = {'account_id': 42, 'environment_id': 'account-environment', 'generation': 3}
        command = {'workspace': {'native_session_id': 'e9067436-4d42-4582-bd00-e864bfc29d66'}}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'sender.json'
            hook = Path(launch.__file__).with_name("tui-direct-mod") / "hooks/engine.js"
            policy = {'account_id': 42, 'environment_id': 'account-environment', 'managed_order': True,
                      'direct_hook_sha256': sha256(hook.read_bytes()).hexdigest()}
            config.write_text(json.dumps({'binding': binding, 'allowed_origin': launch.ACCOUNT_ORIGIN,
                'tui_managed_policy': policy, 'tui_direct': True, 'tui_direct_from_release': True}))
            with (patch.object(launch, 'STORAGE', root / 'native'), patch.dict(os.environ, {
                    'V3_TUI_MANAGED_POLICY': '1', 'V3_TUI_MANAGED_OAUTH': '1', 'V3_TUI_DIRECT': '1',
                    'V3_SENDER_CONFIG': str(config)}),
                  patch.object(launch, 'launch_workspace_cli') as workspace,
                  patch.object(launch, '_open_program', side_effect=lambda: nullcontext((None, 9))),
                  patch.object(launch, '_loopback_channel', side_effect=lambda port: nullcontext((
                      ['--oauth-loopback', str(port), '8'], (8,))))):
                home, mod = launch.session_paths(command)
                options = {'arguments': [], 'config_dir': home / '.claude', 'environment': {}, 'resume': False, 'terminal_fd': 7,
                    'mod_dir': mod, 'model_endpoint': ('http://127.0.0.1:8476/model/current', '')}
                for mismatch in ({'account_id': 41}, {'environment_id': 'other'}, {'generation': 2}):
                    with self.assertRaisesRegex(ValueError, '账号绑定已变化'):
                        launch.launch_session({**binding, **mismatch}, command, oauth_file=True, **options)
                with self.assertRaisesRegex(ValueError, '完整账号凭据'):
                    launch.launch_session(binding, command, **options)
                workspace.assert_not_called()
                launch.launch_session(binding, command, oauth_file=True, **options)
                self.assertEqual(workspace.call_args.kwargs['arguments'][:4],
                                 ['--oauth-loopback', '8476', '8', '--managed-policy'])
                self.assertEqual(workspace.call_args.kwargs['inherited_fds'], (8,))
                environment = workspace.call_args.kwargs['environment']
                self.assertEqual(environment['HTTPS_PROXY'], 'http://127.0.0.1:8476')
                self.assertEqual(environment['ANTHROPIC_BASE_URL'], launch.ACCOUNT_ORIGIN)
                self.assertEqual(environment['FLOWER_TUI_DIRECT_REQUIRED'], '1')
                self.assertNotIn('CLAUDE_CODE_OAUTH_TOKEN', environment)
                workspace.reset_mock()
                with patch.dict(os.environ, {'V3_TUI_DIRECT': '0'}):
                    self.assertFalse(launch.account_ready())
                    with self.assertRaisesRegex(ValueError, "需要已授权的 CLI 直发"):
                        launch.launch_session(binding, command, oauth_file=True, **options)
                workspace.assert_not_called()
                with patch.dict(os.environ, {'V3_TUI_MANAGED_POLICY': ''}):
                    self.assertFalse(launch.account_ready())
                    with self.assertRaisesRegex(ValueError, "缺少同发行的管理员 Mod"):
                        launch.launch_session(binding, command, oauth_file=True, **options)
                workspace.assert_not_called()

    def test_model_error_completeness_follows_http_framing(self):
        """同一签名 400 的修复资格取决于完整 HTTP 正文。@return 无。"""
        body = b'{"error":{"type":"invalid_request_error","message":"Invalid signature in thinking block"}}'
        chunk = f"{len(body):x}\r\n".encode() + body + b"\r\n"
        for framing, payload, complete in (
            (b"Connection: close", body, True),
            (b"Connection: close", body + b" ", False),
            (f"Content-Length: {len(body)}".encode(), body, True),
            (f"Content-Length: {len(body) + 1}".encode(), body, False),
            (b"Content-Length: invalid", body, False),
            (b"Transfer-Encoding: chunked", chunk + b"0\r\n\r\n", True),
            (b"Transfer-Encoding: chunked", chunk, False),
        ):
            with self.subTest(framing=framing, size=len(payload)):
                client, server = socketpair()
                with client, server, HTTPResponse(client) as response, patch.object(launch, "BODY_LIMIT", len(body)):
                    server.sendall(b"HTTP/1.1 400 Bad Request\r\n" + framing + b"\r\n\r\n" + payload)
                    server.shutdown(SHUT_WR)
                    response.begin()
                    raw, finished = launch._read_model_error(response)
                    self.assertEqual(finished, complete)
                    error = launch.ModelResponseError(400, raw, source="local_provider_http", complete=finished)
                    self.assertEqual(error.signature_evidence is not None, complete)

    def test_complete_oauth_file_is_atomic_rotatable_and_idempotent(self):
        """完整凭据同版替换，原快照重复发放复用文件。@return 无。"""
        with TemporaryDirectory() as folder:
            config = Path(folder)
            path = config / ".credentials.json"
            initial = {"access_token": "synthetic-a1", "refresh_token": "synthetic-r1",
                       "expires_at": time.time_ns() // 1_000_000 + 60_000,
                       "subscription_type": "gateway-tier", "rate_limit_tier": "recorded-tier",
                       "profile": {"scopes": ["user:profile", "user:inference"], "subscriptionType": "max",
                                   "futureProfileField": {"label": "fixture"}}}
            self.assertTrue(launch.publish_oauth_file(config, initial))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            inode = path.stat().st_ino
            self.assertFalse(launch.publish_oauth_file(config, initial))
            self.assertEqual(path.stat().st_ino, inode)
            self.assertTrue(launch.publish_oauth_file(config, {
                **initial, "access_token": "synthetic-a2", "refresh_token": "synthetic-r2",
            }))
            oauth = json.loads(path.read_bytes())["claudeAiOauth"]
            self.assertEqual((oauth["accessToken"], oauth["refreshToken"], oauth["expiresAt"]),
                             ("synthetic-a2", "synthetic-r2", initial["expires_at"]))
            self.assertEqual((oauth["subscriptionType"], oauth["rateLimitTier"]), ("max", "recorded-tier"))
            self.assertEqual(oauth["scopes"], ["user:profile", "user:inference"])
            self.assertEqual(oauth["futureProfileField"], {"label": "fixture"})
            self.assertNotEqual(path.stat().st_ino, inode)
            with self.assertRaisesRegex(ValueError, "已过期"):
                launch.publish_oauth_file(config, {**initial, "expires_at": 1})
            self.assertEqual(json.loads(path.read_bytes())["claudeAiOauth"], oauth)
            staged = config / (".credentials.json." + "a" * 32)
            staged.write_text("synthetic fixture")
            retained = config / ".claude.json"
            retained.write_text("{}")
            launch.clear_oauth_file(config)
            self.assertEqual(set(config.iterdir()), {retained})

@skipUnless(os.geteuid() == 0, "需要与生产配置发布相同的文件所有者")
class LocalProviderTests(TestCase):
    """只允许当前账号只读配置中显式登记的本机开发服务。"""

    def setUp(self):
        """准备临时控制端配置。@return 无。"""
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "provider.json"
        self.enterContext(patch.object(launch, "STORAGE", Path(temp.name) / "native"))
        self.enterContext(patch.object(launch, "LOCAL_PROVIDER", self.path))
        self.enterContext(patch.dict(os.environ, {"V3_TUI_LOCAL_PROVIDER_CONFIG": str(self.path)}))

    def write(self, url):
        """写入合成地址。@param url 受测配置值。@return 无。"""
        self.path.write_text(json.dumps({"base_url": url, "local_bearer": "test-local-user"}))
        self.path.chmod(0o640)

    def test_numeric_loopback_only(self):
        """显式 IPv4 和 IPv6 回环可用，公网、命名地址、子路径与内嵌认证均拒绝。@return 无。"""
        for address in ("http://127.0.0.1:8900", "http://[::1]:8900/"):
            self.write(address)
            url, _, _, port = launch._loopback_provider()
            self.assertEqual((url, port), (address.rstrip("/"), 8900))
        for address in ("http://127.0.0.1", "http://example.test:8900", "https://127.0.0.1:8900",
                        "http://192.0.2.1:8900", "http://user@127.0.0.1:8900", "http://127.0.0.1:8900/x"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                self.write(address)
                launch._loopback_provider()

    def test_configuration_requires_explicit_opt_in_and_private_nonlinked_file(self):
        """无授权、宽权限及指向其他文件的链接不提供就绪。@return 无。"""
        self.write("http://127.0.0.1:8900")
        with patch.dict(os.environ, {"V3_TUI_LOCAL_PROVIDER_CONFIG": ""}):
            self.assertFalse(launch.account_ready())
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            launch._loopback_provider()
        self.path.chmod(0o640)
        copy = self.path.with_name("other")
        os.link(self.path, copy)
        with self.assertRaises(ValueError):
            launch._loopback_provider()
        self.path.unlink()
        self.path.symlink_to(copy)
        with self.assertRaises(OSError):
            launch._loopback_provider()

    def test_model_submission_preserves_body_headers_and_arrival_order(self):
        """以真实 HTTP 核对原始字节、功能声明和上游暂停时的流交付。@return 无。"""
        calls, release, capture = [], Event(), []

        class Provider(BaseHTTPRequestHandler):
            """本机可暂停的独立模型。"""

            def do_POST(self):
                """记录请求后先发一个事件，等消费者读到再结束。@return 无。"""
                calls.append((self.path, self.rfile.read(int(self.headers["Content-Length"])), self.headers))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b"data: first\n\n")
                self.wfile.flush()
                release.wait(3)
                self.wfile.write(b"data: last\n\n")

            def log_message(self, *args):
                """省略测试 HTTP 访问日志。@return 无。"""

        with ThreadingHTTPServer(("127.0.0.1", 0), Provider) as server:
            self.write(f"http://127.0.0.1:{server.server_port}")
            thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            thread.start()
            body = '{"model":"local", "system":[{"type":"text","text":"真实字节 🌸"}]}'.encode()
            try:
                with launch.local_model_response(body, headers={"anthropic-beta": "feature-a,feature-b"}, capture=capture) as response:
                    self.assertEqual(response.readline(), b"data: first\n")
                    release.set()
                    self.assertEqual(response.read(), b"\ndata: last\n\n")
                for header in ("Authorization", "x-api-key", "Host", "Proxy-Authorization"):
                    with self.assertRaises(ValueError):
                        with launch.local_model_response(body, headers={header: "client"}):
                            pass
            finally:
                release.set()
                server.shutdown()
                thread.join()
        self.assertEqual(len(calls), 1)
        path, sent, headers = calls[0]
        self.assertEqual((path, sent), ("/v1/messages", body))
        self.assertEqual(capture, [(list(headers.raw_items()), sent)])
        self.assertEqual(headers["Authorization"], "Bearer test-local-user")
        self.assertEqual(headers["anthropic-beta"], "feature-a,feature-b")
        self.assertEqual(headers["anthropic-version"], "2023-06-01")

    def test_provider_http_errors_and_owner_scoped_wait(self):
        """真实回环 401/403 一次交付，429 的等待期跨调用保留，过期后恢复。@return 无。"""
        calls = []
        now = 1_800_000_000
        clock = self.enterContext(patch.object(launch.time, "time_ns", return_value=now * 10**9))

        class Provider(BaseHTTPRequestHandler):
            """按测试顺序给出明确的 HTTP 状态与响应头。"""

            def do_POST(self):
                """记录每次实际投递。@return 无。"""
                status = [401, 403, 429, 200][len(calls)]
                calls.append(status)
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(status)
                self.send_header("Retry-After", formatdate(now + 65, usegmt=True))
                self.end_headers()
                self.wfile.write(b'{"error":{"type":"api_error","message":"provider","secret":"private"}}')

            def log_message(self, *args):
                """省略测试访问日志。@return 无。"""

        with ThreadingHTTPServer(("127.0.0.1", 0), Provider) as server:
            self.write(f"http://127.0.0.1:{server.server_port}")
            worker = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
            worker.start()
            try:
                for status in (401, 403, 429):
                    with self.assertRaises(launch.ModelResponseError) as caught, launch.local_model_response(b"{}"):
                        self.fail("错误状态应在源端认定")
                    error = caught.exception
                    self.assertEqual((error.source, error.status), ("local_provider_http", status))
                    self.assertEqual(error.retry_after, 65 if status == 429 else None)
                    self.assertNotIn(b"private", error.body)
                clock.return_value += 1_500_000_000
                with self.assertRaises(launch.ModelResponseError) as blocked:
                    launch.check_provider_backoff()
                self.assertEqual((blocked.exception.source, blocked.exception.retry_after), ("local_provider_backoff", 64))
                with self.assertRaises(launch.ModelResponseError), launch.local_model_response(b"{}"):
                    self.fail("等待期内不能投递")
                self.assertEqual(calls, [401, 403, 429])
                url, _, host, port = launch._loopback_provider()
                self.assertEqual(launch._provider_wait((url, "other-local-owner", host, port)), 0)
                self.assertEqual(launch._provider_wait(launch._loopback_provider(), seconds=2), 64)
                clock.return_value = (now + 65) * 10**9
                with launch.local_model_response(b"{}") as response:
                    self.assertEqual(response.status, 200)
                self.assertEqual(calls, [401, 403, 429, 200])
            finally:
                server.shutdown()
                worker.join()

    def test_retry_after_bounds_and_malformed_values(self):
        """重复、过期、零、超大数和不完整值不能截短已经存在的等待期。@return 无。"""
        with patch.object(launch.time, "time_ns", return_value=1_800_000_000 * 10**9):
            for values, expected in [
                ([], None), (["1", "5"], None), (["-1"], None), (["+3"], None),
                (["1, 2"], None), (["1.5"], None), (["七"], None),
                (["0"], 0), (["00002"], 2), (["9" * 6000], 2**64 - 1),
                ([formatdate(1_700_000_000, usegmt=True)], 0),
            ]:
                with self.subTest(values=str(values)[:30]):
                    self.assertEqual(launch._retry_seconds(values), expected)

    def test_new_process_observes_saved_provider_deadline(self):
        """新的 sender 进程读取同账号卷中的退避，无需重新投递模型。@return 无。"""
        self.write("http://127.0.0.1:8900")
        self.assertEqual(launch._provider_wait(launch._loopback_provider(), seconds=120), 120)
        account_dir = Path(launch.__file__).resolve().parent
        check = """from pathlib import Path
import sys
sys.path[:0] = sys.argv[1:3]
import tui_sender_launch as launch
launch.STORAGE, launch.LOCAL_PROVIDER = map(Path, sys.argv[3:])
try:
    launch.check_provider_backoff()
except launch.ModelResponseError as error:
    print(error.source, error.retry_after)
"""
        result = run([sys.executable, "-I", "-c", check, str(account_dir),
                      str(account_dir.parents[1] / "services/orchestrator"), str(launch.STORAGE), str(self.path)],
                     capture_output=True, check=True, text=True, timeout=5)
        source, seconds = result.stdout.split()
        self.assertEqual(source, "local_provider_backoff")
        self.assertTrue(0 < int(seconds) <= 120)
