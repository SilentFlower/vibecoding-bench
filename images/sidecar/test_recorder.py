"""用轻量 mitmproxy 替身验证上游归属和即时额度拦截。"""

import hashlib
import base64
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
mitmproxy.tls = SimpleNamespace()
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

    def test_capture_persists_request_before_response_and_marks_interruption(self) -> None:
        """先保存请求，异常及停止更新同一索引，JSONL 只追加真实阶段。:return: None。"""
        capture = self.base / 'http_capture.jsonl'
        index = self.base / 'capture_index.json'
        with patch.multiple(recorder, CAPTURE_FULL_HTTP=True, CAPTURE_FILE=str(capture), CAPTURE_INDEX_FILE=str(index)):
            flow = self._flow()
            flow.request.scheme, flow.request.query = 'https', {}
            flow.request.get_text = lambda strict=False: '{}'
            flow.response = None
            self.addon.request(flow)
            self.assertEqual('pending', json.loads(index.read_text())['entries'][0]['capture_state'])
            self.addon.error(flow)
            entries = json.loads(index.read_text())['entries']
            self.assertEqual(1, len(entries))
            self.assertEqual('interrupted', entries[0]['capture_state'])
            self.assertIsNone(entries[0]['response']['status'])
            flow.response = ResponseFactory.make(200, b'partial response', {})
            self.addon.response(flow)
            self.assertEqual('interrupted', json.loads(index.read_text())['entries'][0]['capture_state'])
            records = [json.loads(line) for line in capture.read_text().splitlines()]
            self.assertEqual(['pending', 'interrupted', 'interrupted'], [item['capture_state'] for item in records])
            flow.id = 'next-flow'
            self.addon.request(flow)
            self.addon.done()
            entries = json.loads(index.read_text())['entries']
            self.assertEqual(2, len(entries))
            self.assertTrue(all(item['capture_state'] == 'interrupted' for item in entries))

    def test_capture_response_updates_index_without_double_counting_request(self) -> None:
        """响应完成覆盖同流索引状态，追加记录保留先前请求。:return: None。"""
        capture, index = self.base / 'http_capture.jsonl', self.base / 'capture_index.json'
        with patch.multiple(recorder, CAPTURE_FULL_HTTP=True, CAPTURE_FILE=str(capture), CAPTURE_INDEX_FILE=str(index)):
            flow = self._flow()
            flow.request.scheme, flow.request.query = 'https', {}
            flow.request.get_text = lambda strict=False: '{}'
            response, flow.response = flow.response, None
            self.addon.request(flow)
            flow.response = response
            self.addon.response(flow)
            value = json.loads(index.read_text())
            self.assertEqual(1, value['total_flows'])
            self.assertEqual('complete', value['entries'][0]['capture_state'])
            self.assertEqual(2, len(capture.read_text().splitlines()))

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

    def test_identity_observation_accepts_ip_host_with_verified_domain_and_rejects_other_domain(self) -> None:
        """透明代理 IP 不能丢失身份采集；相似域名不得作为有效来源。@return None。"""
        identity_path = self.base / "identity.json"
        actual_path = Path

        def path(value):
            """把容器专用身份路径映射到测试私有目录。"""
            return identity_path if value == "/run/v3/identity.json" else actual_path(value)

        body = json.dumps({"metadata": {"user_id": json.dumps({"device_id": "a" * 64, "account_uuid": "synthetic-account"})}}).encode()
        with patch.dict(os.environ, {"V3_ACCOUNT": "1"}), patch.object(recorder, "Path", side_effect=path):
            wrong = self._flow(host="evil-anthropic.com")
            wrong.request.raw_content = body
            self.addon.request(wrong)
            self.assertFalse(identity_path.exists())
            flow = self._flow(host="198.18.0.10")
            flow.request.headers["host"] = "api.anthropic.com:443"
            flow.server_conn.sni = "api.anthropic.com"
            flow.request.raw_content = body
            self.addon.request(flow)
        self.assertEqual(json.loads(identity_path.read_text())["device_id"], "a" * 64)

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

    def test_v3_identity_accepts_only_explicit_device_and_keeps_conflict(self) -> None:
        """userID/machineID 不推测映射；设备或账号归属变化后保持冲突。"""
        identity_file = self.base / "identity.json"
        flow = self._flow()
        with patch.dict(os.environ, {"V3_ACCOUNT": "1"}), patch.object(recorder, "Path", return_value=identity_file):
            flow.request.raw_content = json.dumps({"metadata": {"user_id": json.dumps({"machineID": "a" * 64})}}).encode()
            self.addon.request(flow)
            self.assertFalse(identity_file.exists())
            identity = {"device_id": "a" * 64, "account_uuid": "synthetic-one"}
            flow.request.raw_content = json.dumps({"metadata": {"user_id": json.dumps(identity)}}).encode()
            self.addon.request(flow)
            self.assertEqual(json.loads(identity_file.read_text())["device_id"], "a" * 64)
            identity["account_uuid"] = "synthetic-two"
            flow.request.raw_content = json.dumps({"metadata": {"user_id": json.dumps(identity)}}).encode()
            self.addon.request(flow)
            self.assertTrue(json.loads(identity_file.read_text())["conflict"])
            identity["account_uuid"] = "synthetic-one"
            flow.request.raw_content = json.dumps({"metadata": {"user_id": json.dumps(identity)}}).encode()
            self.addon.request(flow)
            self.assertTrue(json.loads(identity_file.read_text())["conflict"])

    def test_unreadable_shared_state_does_not_forward_owned_model_request(self) -> None:
        """门禁文件失效停止当前执行，不标成可用额度或继续转发。"""
        self.addon._quota_state()
        self.state.unlink()
        flow = self._flow()
        self.addon.requestheaders(flow)
        self.assertEqual(503, flow.response.status_code)
        self.assertEqual("failed", json.loads(self.signal.read_text())["status"])


class RecorderTLSCaptureTests(unittest.TestCase):
    """真实观察 hook 的落盘、来源快照和 HTTP 一对多连接关联。"""

    def setUp(self) -> None:
        """准备私有执行目录及冻结版本，不连接外部服务。:return: None。"""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.capture, self.index = self.base / "http_capture.jsonl", self.base / "capture_index.json"
        self.tls_path = self.base / "tls_clienthello.jsonl"
        self.context = {"schema": 1, "source": "projects:work:3", "claude_code_version": "2.1.303",
                        "namespace": "projects", "work_id": "work", "claude_code_version_source": "account"}
        patcher = patch.dict(os.environ, {"CAPTURE_CONTEXT": json.dumps(self.context),
            "QUOTA_SOURCE": self.context["source"], "QUOTA_WARMUP": "0", "V3_ACCOUNT": "0"})
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.multiple(recorder, CAPTURE_FULL_HTTP=True, CAPTURE_FILE=str(self.capture),
            CAPTURE_INDEX_FILE=str(self.index), CAPTURE_SCOPE="anthropic", STATS_FILE=str(self.base / "stats.jsonl"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addon = recorder.Recorder()

    def _event(self, sni="api.anthropic.com", raw=None):
        body = b"\x03\x03" + b"R" * 32 + b"\x00\x00\x02\x13\x01\x01\x00"
        if sni:
            name = sni.encode("ascii")
            names = b"\x00" + len(name).to_bytes(2, "big") + name
            payload = len(names).to_bytes(2, "big") + names
            extension = b"\x00\x00" + len(payload).to_bytes(2, "big") + payload
            body += len(extension).to_bytes(2, "big") + extension

        def raw_bytes(wrap_in_record=True):
            self.assertFalse(wrap_in_record)
            return body if raw is None else raw

        return SimpleNamespace(context=SimpleNamespace(client=SimpleNamespace(id="client-connection")),
                               client_hello=SimpleNamespace(raw_bytes=raw_bytes))

    def _flow(self, flow_id):
        return SimpleNamespace(id=flow_id, client_conn=SimpleNamespace(id="client-connection", sni="api.anthropic.com"),
            server_conn=SimpleNamespace(sni="api.anthropic.com"), request=SimpleNamespace(
                method="GET", scheme="https", host="api.anthropic.com", pretty_host="api.anthropic.com",
                path="/v1/mock", query={}, headers={}, raw_content=b"", get_text=lambda strict=False: ""),
            response=ResponseFactory.make(200, b"{}", {"content-type": "application/json"}))

    def test_client_hello_and_multiple_http_flows_share_frozen_connection_and_context(self) -> None:
        """一条握手关联多个流；后续环境变化不能改写本执行版本。:return: None。"""
        with patch.dict(os.environ, {"CAPTURE_CONTEXT": "{}", "QUOTA_SOURCE": "warmup:other:4"}):
            self.addon.tls_clienthello(self._event())
            for flow_id in ("one", "two"):
                flow = self._flow(flow_id)
                self.addon.request(flow)
                self.addon.response(flow)
        tls_record = json.loads(self.tls_path.read_text())
        self.assertEqual("client_to_recorder", tls_record["direction"])
        self.assertEqual("target", tls_record["target_status"])
        self.assertEqual("ok", tls_record["parse_status"])
        self.assertEqual(self.context, tls_record["capture_context"])
        self.assertEqual("ok", tls_record["capture_context_status"])
        self.assertIsNone(tls_record["capture_context_error"])
        self.assertEqual(0o600, self.tls_path.stat().st_mode & 0o777)
        records = [json.loads(line) for line in self.capture.read_text().splitlines()]
        self.assertEqual(4, len(records))
        entries = json.loads(self.index.read_text())["entries"]
        self.assertEqual(2, len(entries))
        for record in [*records, *entries]:
            self.assertEqual(tls_record["client_connection_id"], record["client_connection_id"])
            self.assertEqual(self.context, record["capture_context"])
        self.assertNotIn("raw_base64", self.index.read_text())
        self.assertTrue(all(item["analysis"]["cc_version"] is None for item in entries))

    def test_target_scope_and_capture_off_do_not_change_http_scope(self) -> None:
        """非目标 SNI 被跳过，无 SNI 明确待归因；关闭抓包不读握手。:return: None。"""
        self.addon.tls_clienthello(self._event("example.invalid"))
        self.assertFalse(self.tls_path.exists())
        self.addon.tls_clienthello(self._event(None))
        self.assertEqual("unclassified", json.loads(self.tls_path.read_text())["target_status"])
        with patch.object(recorder, "CAPTURE_SCOPE", "all"):
            self.addon.tls_clienthello(self._event("example.invalid"))
        records = [json.loads(line) for line in self.tls_path.read_text().splitlines()]
        self.assertEqual("non_target", records[1]["target_status"])
        old = self.tls_path.read_bytes()
        with patch.object(recorder, "CAPTURE_FULL_HTTP", False):
            self.addon.tls_clienthello(None)
        self.assertEqual(old, self.tls_path.read_bytes())

    def test_bad_vector_keeps_raw_without_blocking_or_fake_ja3(self) -> None:
        """解析失败仍追加可复核本体，握手配置和连接对象均不修改。:return: None。"""
        event = self._event(raw=b"\x03\x03incomplete")
        self.addon.tls_clienthello(event)
        result = json.loads(self.tls_path.read_text())
        self.assertEqual("error", result["parse_status"])
        self.assertIsNone(result["ja3"])
        self.assertEqual(b"\x03\x03incomplete", base64.b64decode(result["raw_base64"]))
        self.assertEqual({"context", "client_hello"}, set(vars(event)))

    def test_tls_write_failure_has_fixed_diagnostic_and_http_still_completes(self) -> None:
        """观察写盘故障不会拒绝 HTTP；统计中不能泄漏底层异常原文。:return: None。"""
        with patch.object(recorder, "append_private_jsonl", side_effect=OSError("private-error-canary")):
            self.addon.tls_clienthello(self._event())
        self.assertFalse(self.tls_path.exists())
        flow = self._flow("after-error")
        self.addon.requestheaders(flow)
        self.addon.request(flow)
        self.addon.response(flow)
        self.assertEqual(200, flow.response.status_code)
        self.assertEqual("complete", json.loads(self.index.read_text())["entries"][0]["capture_state"])
        stats = (self.base / "stats.jsonl").read_text()
        self.assertIn("tls_clienthello_capture_failed", stats)
        self.assertNotIn("private-error-canary", stats)

    def test_unsupported_sdk_transport_is_explicit(self) -> None:
        """SDK 不支持的传输不伪造原始封装或成功指纹。:return: None。"""
        event = self._event()
        event.client_hello.raw_bytes = lambda wrap_in_record=False: (_ for _ in ()).throw(NotImplementedError())
        self.addon.tls_clienthello(event)
        record = json.loads(self.tls_path.read_text())
        self.assertEqual("unsupported", record["parse_status"])
        self.assertIsNone(record["ja3"])
        self.assertNotIn("raw_base64", record)


class RecorderWarmupTests(unittest.TestCase):
    """验证真实 addon 的单次请求和收尾门禁，不继承重复的旧测试。"""

    _write_state = RecorderQuotaTests._write_state
    _headers = RecorderQuotaTests._headers

    def setUp(self) -> None:
        """复用独立状态夹具并启用当前执行的养号作用域。@return None。"""
        RecorderQuotaTests.setUp(self)
        patcher = patch.dict(os.environ, {"QUOTA_WARMUP": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sequence = 0
        self.limits = {"five_hour": 30, "seven_day": None}
        self._policy()
        self.addon = recorder.Recorder()

    def _flow(self, **options):
        """构造正在代理中的独立流；参数为请求/响应选项，返回替身。"""
        self.sequence += 1
        flow = RecorderQuotaTests._flow(self, **options)
        flow.id = f"warmup-{self.sequence}"
        flow.live = True
        return flow

    def _policy(self, windows=None, admission=None) -> None:
        """保存模拟管理端策略；参数为窗口/许可，返回 None。"""
        decision = recorder.warmup_quota_decision({"windows": windows or {}}, self.limits, time.time())
        if admission is None:
            admission = {"identity": "identity", "source": "run:original:0",
                         **{key: decision[key] for key in ("policy_key", "window_key")}}
        self._write_state({"windows": windows or {}, "warmup_quota": {**decision, "admission": admission}})

    def test_unknown_allows_one_request_then_waits_for_actual_proxy_end(self) -> None:
        """未知仅一次，response 钩子时仍 live 的成功请求不会被提前杀掉。@return None。"""
        first = self._flow()
        self.addon.requestheaders(first)
        self.assertEqual(200, first.response.status_code)
        self.assertTrue(self.signal.with_name("warmup-sample.json").exists())
        second = self._flow()
        self.addon.requestheaders(second)
        self.assertEqual(429, second.response.status_code)
        self.assertFalse(self.signal.exists())
        self.assertTrue(self.signal.with_name("warmup-draining.json").exists())
        self.addon.responseheaders(first)
        self.addon.response(first)
        self.assertFalse(self.signal.exists())
        first.live = False
        self.addon._check_warmup_pause()
        self.assertTrue(json.loads(self.signal.read_text())["warmup_wait"])
        self.assertFalse(self.signal.with_name("warmup-draining.json").exists())

    def test_v3_idle_window_without_reset_keeps_terminal_and_requests_available(self) -> None:
        """v3 空闲窗口没有 reset 时正常启动，不套用旧 runner 的未知单次许可。@return None。"""
        windows = {"five_hour": {"utilization": 0, "reset_at": None, "usage_idle": True},
            "seven_day": {"utilization": 0, "reset_at": time.time() + 86400}}
        self._write_state({"windows": windows, "warmup_quota": {
            "limits": {"five_hour": 55, "seven_day": 90}, "policy_key": "v3-passive-recovery",
            "sample_required": False, "admission": None}})
        self.addon._check_warmup_pause()
        self.assertFalse(self.signal.exists())
        for _ in range(2):
            flow = self._flow()
            self.addon.requestheaders(flow)
            self.assertEqual(200, flow.response.status_code)
        self.assertFalse(self.signal.with_name("warmup-sample.json").exists())

    def test_v3_expired_threshold_recovery_is_once_across_recorder_restart(self) -> None:
        """已命中的旧窗口到期只放行其持久许可，重启不能再次发放。@return None。"""
        reset = time.time() - 10
        windows = {"five_hour": {"utilization": 80, "reset_at": reset}}
        admission = {"identity": "identity", "source": "run:original:0", "policy_key": "v3-passive-recovery",
            "window_key": json.dumps({"five_hour": [reset, True, 30]}, sort_keys=True)}
        self._write_state({"windows": windows, "warmup_quota": {
            "limits": self.limits, "policy_key": "v3-passive-recovery", "admission": admission}})
        first = self._flow()
        self.addon.requestheaders(first)
        self.assertEqual(200, first.response.status_code)
        self.assertTrue(self.signal.with_name("warmup-sample.json").exists())
        restarted = recorder.Recorder()
        denied = self._flow()
        restarted.requestheaders(denied)
        self.assertEqual(429, denied.response.status_code)

    def test_v3_common_exhaustion_recovery_stays_once_with_thresholds_disabled(self) -> None:
        """关闭百分比阈值不能取消真实共同耗尽到期的单次恢复约束。@return None。"""
        reset = time.time() - 10
        admission = {"identity": "identity", "source": "run:original:0", "policy_key": "v3-passive-recovery",
            "window_key": json.dumps({"common:unknown": [reset]}, sort_keys=True)}
        self._write_state({"windows": {"unknown": {"exhausted": True, "reset_at": reset}},
            "recovery_source": "run:original:0", "warmup_quota": {"limits": {"five_hour": None, "seven_day": None},
                "policy_key": "v3-passive-recovery", "admission": admission}})
        first = self._flow()
        self.addon.requestheaders(first)
        self.assertEqual(200, first.response.status_code)
        self.assertTrue(self.signal.with_name("warmup-sample.json").exists())
        second = self._flow()
        self.addon.requestheaders(second)
        self.assertEqual(429, second.response.status_code)

    def test_v3_published_policy_does_not_hide_a_new_threshold_hit(self) -> None:
        """管理端旧快照未命中时，抓包的最新真实用量仍能阻止后续请求。@return None。"""
        self._write_state({"windows": {"five_hour": {"utilization": 10, "reset_at": time.time() + 600}},
            "warmup_quota": {"limits": self.limits, "policy_key": "v3-passive-recovery", "admission": None,
                "blocked": False, "sample_required": False}})
        self.addon.quota_local = {"windows": {"five_hour": {"utilization": 40,
            "reset_at": time.time() + 600, "observed_at": time.time()}}}
        flow = self._flow()
        self.addon.requestheaders(flow)
        self.assertEqual(429, flow.response.status_code)

    def test_valid_first_response_permits_normal_followup(self) -> None:
        """第一次正式请求拿到低于阈值的真实额度后继续，不另做探测。@return None。"""
        first = self._flow()
        self.addon.requestheaders(first)
        first.response.headers = self._headers(False)
        first.response.headers["anthropic-ratelimit-unified-5h-utilization"] = "0.2"
        self.addon.responseheaders(first)
        self.addon.response(first)
        first.live = False
        self.addon._check_warmup_pause()
        self.assertFalse(self.signal.exists())
        second = self._flow()
        self.addon.requestheaders(second)
        self.assertEqual(200, second.response.status_code)
        self.assertEqual(1, len(self.observations.read_text().splitlines()))

    def test_threshold_defers_until_all_parallel_streams_finish(self) -> None:
        """多个已接受流都结束才暂停，新的请求立即在本地阻断。@return None。"""
        self._policy({"five_hour": {"utilization": 20, "reset_at": time.time() + 600}})
        first, second = self._flow(), self._flow()
        self.addon.requestheaders(first)
        self.addon.requestheaders(second)
        first.response.headers = self._headers(False)
        first.response.headers["anthropic-ratelimit-unified-5h-utilization"] = "0.3"
        self.addon.responseheaders(first)
        denied = self._flow()
        self.addon.requestheaders(denied)
        self.assertEqual(429, denied.response.status_code)
        self.assertFalse(self.signal.exists())
        self.addon.response(first)
        first.live = False
        self.addon._check_warmup_pause()
        self.assertFalse(self.signal.exists())
        self.addon.response(second)
        second.live = False
        self.addon._check_warmup_pause()
        self.assertTrue(self.signal.exists())
        self.assertEqual([], json.loads(self.signal.read_text())["exhausted"])

    def test_marker_survives_recorder_restart_and_corruption_fails_closed(self) -> None:
        """重启不得再次发送未知请求，损坏标记按执行故障处理。@return None。"""
        first = self._flow()
        self.addon.requestheaders(first)
        restarted = recorder.Recorder()
        denied = self._flow()
        restarted.requestheaders(denied)
        self.assertEqual(429, denied.response.status_code)
        self.signal.with_name("warmup-sample.json").write_text("损坏")
        broken = self._flow()
        restarted.requestheaders(broken)
        self.assertEqual(503, broken.response.status_code)
        self.assertEqual("failed", json.loads(self.signal.read_text())["status"])

    def test_unrelated_request_does_not_consume_one_opportunity(self) -> None:
        """其它域名和项目假 key 不消费当前账号的单次正式机会。@return None。"""
        for options in ({"host": "example.invalid"}, {"token": "project-dummy"}, {"path": "/api/oauth/usage"}):
            self.addon.requestheaders(self._flow(**options))
        self.assertFalse(self.signal.with_name("warmup-sample.json").exists())
        self.assertFalse(self.addon.warmup_flows)

    def test_normal_execution_does_not_inherit_warmup_policy(self) -> None:
        """同一账号正常任务忽略养号阈值与已用标记。@return None。"""
        self._policy({"five_hour": {"utilization": 40, "reset_at": time.time() + 600}})
        with patch.dict(os.environ, {"QUOTA_WARMUP": "0"}):
            normal = recorder.Recorder()
        flow = self._flow()
        normal.requestheaders(flow)
        self.assertEqual(200, flow.response.status_code)
        self.assertFalse(self.signal.exists())

    def test_shared_api_update_pauses_without_another_cli_request(self) -> None:
        """共享 API 更新达到阈值时，也能等待当前 CLI 响应后暂停。@return None。"""
        self._policy({"five_hour": {"utilization": 20, "reset_at": time.time() + 600}})
        current = self._flow()
        self.addon.requestheaders(current)
        self._policy({"five_hour": {"utilization": 40, "reset_at": time.time() + 600}})
        self.addon._check_warmup_pause()
        self.assertFalse(self.signal.exists())
        with patch.object(recorder, "_should_record", return_value=False):
            self.addon.response(current)
        current.live = False
        self.addon._check_warmup_pause()
        self.assertTrue(self.signal.exists())

    def test_control_io_failure_cannot_forward_and_stays_closed(self) -> None:
        """控制落盘故障仍生成本地拒绝，不能因异常跳过请求门禁。@return None。"""
        self._policy({"five_hour": {"utilization": 40, "reset_at": time.time() + 600}})
        flow = self._flow()
        with patch.object(Path, "write_text", side_effect=OSError("合成写入故障")):
            self.addon.requestheaders(flow)
        self.assertEqual(503, flow.response.status_code)
        self.assertTrue(self.addon.quota_control_failed)
        self._policy({"five_hour": {"utilization": 10, "reset_at": time.time() + 600}})
        retry = self._flow()
        self.addon.requestheaders(retry)
        self.assertEqual(503, retry.response.status_code)

    def test_malformed_window_is_an_execution_error(self) -> None:
        """身份匹配但窗口结构损坏时拒绝，不能当作未知机会直接发送。@return None。"""
        self._policy()
        state = json.loads(self.state.read_text())
        state["windows"] = []
        self.state.write_text(json.dumps(state))
        flow = self._flow()
        self.addon.requestheaders(flow)
        self.assertEqual(503, flow.response.status_code)


if __name__ == "__main__":
    unittest.main()
