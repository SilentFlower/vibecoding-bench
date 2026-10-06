"""用轻量 mitmproxy 替身验证上游归属和即时额度拦截。"""

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class ResponseFactory:
    """提供真实 addon 使用的 Response.make 替身。"""

    @staticmethod
    def make(status, body, headers):
        """构建响应；参数为 HTTP 状态、正文和头，返回响应对象。"""
        return SimpleNamespace(status_code=status, raw_content=body, headers=headers,
                               get_text=lambda strict=False: body.decode())


mitmproxy = ModuleType("mitmproxy")
mitmproxy.http = SimpleNamespace(Response=ResponseFactory)
with patch.dict(sys.modules, {"mitmproxy": mitmproxy}):
    import recorder


class RecorderQuotaTests(unittest.TestCase):
    """直接执行 addon 钩子，不请求真实上游。"""

    def setUp(self) -> None:
        """创建只含假凭据的共享文件和观察目录，返回 None。"""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state.json"
        self.signal = self.base / "pause.json"
        self.observations = self.base / "quota.jsonl"
        self.credentials = self.base / ".credentials.json"
        self.token = "仅用于测试的AT"
        self.credentials.write_text(json.dumps({"claudeAiOauth": {"accessToken": self.token}}))
        self._write_state({})
        patcher = patch.dict(os.environ, {
            "QUOTA_SOURCE": "run:original:0", "QUOTA_IDENTITY": "identity",
            "QUOTA_STATE_FILE": str(self.state), "QUOTA_SIGNAL_FILE": str(self.signal),
            "QUOTA_OBSERVATIONS_FILE": str(self.observations), "QUOTA_CREDENTIALS_FILE": str(self.credentials),
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(recorder, "STATS_FILE", str(self.base / "stats.jsonl"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addon = recorder.Recorder()

    def _write_state(self, payload):
        self.state.write_text(json.dumps({"identity": "identity", "token_hashes": [hashlib.sha256(self.token.encode()).hexdigest()], **payload}))

    def _flow(self, status=200, headers=None, token=None, host="api.anthropic.com", path="/v1/messages"):
        return SimpleNamespace(id="flow", request=SimpleNamespace(
            host=host, pretty_host=host, headers={"authorization": "Bearer " + (token or self.token), "host": host},
            method="POST", path=path, raw_content=b"{}"),
            response=ResponseFactory.make(status, b"{}", headers or {}),
            server_conn=SimpleNamespace(sni=host), client_conn=SimpleNamespace(sni=None))

    def _headers(self, rejected=True):
        return {"anthropic-ratelimit-unified-5h-status": "rejected" if rejected else "allowed",
                "anthropic-ratelimit-unified-5h-utilization": "1",
                "anthropic-ratelimit-unified-5h-reset": str(time.time() + 600)}

    def test_first_rejection_signals_before_retry_and_future_request_is_local(self) -> None:
        """第一次拒绝发暂停信号，下一次请求产生本地响应。"""
        flow = self._flow(429, self._headers())
        self.addon.responseheaders(flow)
        self.assertEqual("quota_wait", json.loads(self.signal.read_text())["status"])
        retry = self._flow()
        self.addon.requestheaders(retry)
        self.assertEqual("1", retry.response.headers["x-vibebench-quota-blocked"])
        self.assertEqual(429, retry.response.status_code)
        self.addon.responseheaders(retry)
        self.assertEqual(1, len(self.observations.read_text().splitlines()))
        self.assertNotIn(self.token, self.observations.read_text())

    def test_successful_stream_at_100_finishes_but_next_request_is_blocked(self) -> None:
        """已接受流不发暂停信号，后续模型请求被挡住。"""
        flow = self._flow(200, self._headers(False))
        self.addon.responseheaders(flow)
        self.assertEqual(200, flow.response.status_code)
        self.assertFalse(self.signal.exists())
        next_flow = self._flow()
        self.addon.requestheaders(next_flow)
        self.assertEqual(429, next_flow.response.status_code)
        self.assertTrue(self.signal.exists())

    def test_dummy_keys_other_hosts_and_oauth_do_not_update_account(self) -> None:
        """项目自测及非模型路径不污染账号额度。"""
        for options in ({"token": "dummy-key"}, {"host": "evil-anthropic.com"}, {"path": "/api/oauth/usage"}):
            with self.subTest(options=options):
                self.addon.responseheaders(self._flow(429, self._headers(), **options))
        self.assertFalse(self.observations.exists())
        self.assertFalse(self.signal.exists())

    def test_only_recovery_owner_can_pass_expired_shared_window(self) -> None:
        """窗口到期不同时放行其它执行。"""
        payload = {"windows": {"five_hour": {"exhausted": True, "reset_at": time.time() - 1}},
                   "recovery_source": "run:another:1"}
        self._write_state(payload)
        denied = self._flow()
        self.addon.requestheaders(denied)
        self.assertEqual(429, denied.response.status_code)
        payload["recovery_source"] = "run:original:0"
        self._write_state(payload)
        permitted = self._flow()
        self.addon.requestheaders(permitted)
        self.assertEqual(200, permitted.response.status_code)

    def test_rotated_local_access_token_remains_attributable(self) -> None:
        """既有刷新更换 AT 后仍能被动采集，不请求刷新。"""
        self.credentials.write_text(json.dumps({"claudeAiOauth": {"accessToken": "轮换后的假AT"}}))
        self.addon.responseheaders(self._flow(200, self._headers(False), token="轮换后的假AT"))
        self.assertTrue(self.observations.exists())
        self.assertNotIn("轮换后的假AT", self.observations.read_text())

    def test_hold_body_writes_only_safe_error_code(self) -> None:
        """明确封号写有限分类，不保存任意敏感错误正文。"""
        flow = self._flow(401)
        flow.response = ResponseFactory.make(401, json.dumps({"error": {"type": "account_on_hold", "message": "账号异常，私密内容"}}).encode(), {})
        self.addon.response(flow)
        observation = json.loads(self.observations.read_text())
        self.assertEqual("account_on_hold", observation["account_error"])
        self.assertNotIn("私密内容", self.observations.read_text())

    def test_observation_write_failure_preserves_reset_in_control(self) -> None:
        """日志故障不丢 reset，下一条模型请求仍被本地阻断。"""
        headers = self._headers()
        with patch.object(recorder, "_jsonl_append", side_effect=OSError("测试磁盘故障")):
            self.addon.responseheaders(self._flow(429, headers))
        payload = json.loads(self.signal.read_text())
        self.assertEqual(float(headers["anthropic-ratelimit-unified-5h-reset"]), payload["resume_at"])
        self.assertTrue(payload["quota_state"]["windows"]["five_hour"]["rejected"])
        self.assertFalse(self.observations.exists())
        next_flow = self._flow()
        self.addon.requestheaders(next_flow)
        self.assertEqual(429, next_flow.response.status_code)

    def test_hold_survives_observation_write_failure_and_blocks_next_request(self) -> None:
        """封号分类随控制信号保存，日志故障也不会再转发模型请求。"""
        flow = self._flow(403)
        flow.response = ResponseFactory.make(403, b'{"error":{"type":"account_on_hold"}}', {})
        with patch.object(recorder, "_jsonl_append", side_effect=OSError("测试磁盘故障")):
            self.addon.response(flow)
        payload = json.loads(self.signal.read_text())
        self.assertEqual("account_on_hold", payload["quota_state"]["account_error"])
        next_flow = self._flow()
        self.addon.requestheaders(next_flow)
        self.assertEqual(429, next_flow.response.status_code)
        self.assertIn("account_on_hold", self.signal.read_text())

    def test_unreadable_shared_state_does_not_forward_owned_model_request(self) -> None:
        """门禁文件失效停止当前执行，不标成可用额度或继续转发。"""
        self.addon._quota_state()
        self.state.unlink()
        flow = self._flow()
        self.addon.requestheaders(flow)
        self.assertEqual(503, flow.response.status_code)
        self.assertEqual("failed", json.loads(self.signal.read_text())["status"])


if __name__ == "__main__":
    unittest.main()
