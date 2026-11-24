"""用部署者拥有的合成配置检查本机提供方的地址和文件归属边界。"""

from base64 import b64decode
from http.client import HTTPConnection
import json
import os
from subprocess import run
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email.utils import formatdate
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest import TestCase, skipUnless
from unittest.mock import patch

import tui_sender_launch as launch


class ManagedOAuthTests(TestCase):
    """受管凭据只随匹配的账号模型请求走原 sender。"""

    def test_oauth_forward_uses_bound_sender_with_frozen_body(self):
        """实际 HTTP 验证对应的 AT、正文和脱敏采集。@return 无。"""
        calls = []
        body = b'{ "messages": [{"role":"user","content":"synthetic"}] }'
        token = "synthetic-account-at"
        binding = {"account_id": 42, "environment_id": "test-environment", "generation": 3}
        reservation = {**binding, "reservation_id": "test-round", "deadline_unix_ms": 55}

        class Sender(BaseHTTPRequestHandler):
            """接收本次模型请求的私有 sender。"""

            def log_message(self, *_):
                """省略验收 HTTP 日志。@return 无。"""

            def do_POST(self):
                """记录私有发送请求。@return 无。"""
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                calls.append((self.path, self.headers["Authorization"], raw,
                              json.loads(b64decode(self.headers["x-v3-request"]))))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b"data: isolated\n\n")

        capture = []
        with TemporaryDirectory() as root, ThreadingHTTPServer(("127.0.0.1", 0), Sender) as server:
            config = Path(root) / "sender.json"
            config.write_text(json.dumps({"binding": {**binding, "secret": "private-sender-binding"},
                                          "allowed_origin": launch.ACCOUNT_ORIGIN}))
            thread = Thread(target=server.serve_forever)
            thread.start()
            try:
                with (patch.dict(os.environ, {"V3_SENDER_CONFIG": str(config)}),
                      patch.object(launch, "HTTPConnection",
                                   side_effect=lambda host, _, **opts: HTTPConnection(host, server.server_port, **opts))):
                    with launch.managed_model_response(
                        body, account_token=token, reservation=reservation,
                        headers={"anthropic-beta": "test-beta", "x-claude-code-session-id": "test-session"},
                        capture=capture,
                    ) as response:
                        self.assertEqual(response.read(), b"data: isolated\n\n")
                    with self.assertRaises(ValueError), launch.managed_model_response(
                        body, account_token=token, reservation={**reservation, "account_id": 43}, headers={},
                    ):
                        self.fail("错绑请求不能到达 sender")
            finally:
                server.shutdown()
                thread.join()

        (path, auth, actual, meta), = calls
        self.assertEqual((path, auth, actual), ("/internal/send", "Bearer private-sender-binding", body))
        self.assertEqual({key: meta[key] for key in binding}, binding)
        self.assertEqual(meta["request_id"], reservation["reservation_id"])
        self.assertEqual(meta["deadline_unix_ms"], reservation["deadline_unix_ms"])
        self.assertEqual(meta["target_url"], "https://api.anthropic.com/v1/messages")
        headers = dict(meta["headers"])
        self.assertEqual(headers["authorization"], "Bearer " + token)
        self.assertEqual(headers["anthropic-beta"], "test-beta,oauth-2025-04-20")
        self.assertEqual(headers["x-claude-code-session-id"], "test-session")
        self.assertNotIn(token, repr(capture))


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
