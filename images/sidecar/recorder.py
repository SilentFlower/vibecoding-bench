"""
mitmproxy addon：抽取 Anthropic API 流量的 token / 状态码，按行落盘 stats.jsonl。
分析抓包模式下额外保存完整 HTTP 请求/响应体和轻量索引。
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from mitmproxy import http, tls
from quota_protocol import merge_quota_observation, passive_recovery_decision, quota_decision, quota_observation, warmup_quota_decision, warmup_sample_used
from tls_clienthello import append_private_jsonl, capture_context_snapshot, parse_clienthello

STATS_FILE = os.environ.get("STATS_FILE", "/flows/stats.jsonl")
CAPTURE_FILE = os.environ.get("CAPTURE_FILE", "/flows/http_capture.jsonl")
CAPTURE_INDEX_FILE = os.environ.get("CAPTURE_INDEX_FILE", "/flows/capture_index.json")
CAPTURE_FULL_HTTP = os.environ.get("CAPTURE_FULL_HTTP", "0") == "1"
CAPTURE_SCOPE = os.environ.get("CAPTURE_SCOPE", "anthropic").strip().lower() or "anthropic"
CAPTURE_MAX_BODY_BYTES = int(os.environ.get("CAPTURE_MAX_BODY_BYTES", "0") or "0")
TARGET_HOST_KEYWORDS = ("anthropic.com", "claude.com")
TARGET_API_PATH_PREFIXES = ("/v1/", "/api/oauth/", "/api/eval/", "/api/claude_code/")
CAPTURE_TARGETS = tuple(
    item.strip().lower()
    for item in os.environ.get("CAPTURE_TARGETS", "").split(",")
    if item.strip()
) or TARGET_HOST_KEYWORDS
_BILLING_PART_RE = re.compile(r"([^=;,\s]+)=([^;,\s]+)")
_CCH_RE = re.compile(r"(cch|fingerprint|billing|anthropic)", re.IGNORECASE)
_TELEMETRY_RE = re.compile(
    r"(telemetry|event_logging|datadog|statsig|sentry|posthog|growthbook|analytics|metrics|log|trace|rum|ws)",
    re.IGNORECASE,
)
_SENSITIVE_HEADER_RE = re.compile(
    r"(authorization|cookie|set-cookie|x-api-key|token|secret|credential|key)",
    re.IGNORECASE,
)


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _jsonl_append(path: str, data: dict[str, Any]) -> None:
    """追加写 JSONL 文件，失败交给调用方处理。"""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def _extract_usage_from_sse(text: str) -> dict[str, Any] | None:
    """从 SSE 流响应中尽量提取 usage（message_delta / message_stop 事件）"""
    usage: dict[str, Any] | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = _safe_json_loads(line[5:].strip())
        if not isinstance(data, dict):
            continue
        u = data.get("usage")
        if isinstance(u, dict):
            usage = {**(usage or {}), **u}
    return usage


def _headers_dict(headers: http.Headers | None) -> dict[str, str]:
    """
    把 mitmproxy headers 转成普通 dict。

    同名 header 罕见但可能存在；这里按 mitmproxy 合并后的可读值保存，完整
    原始现场仍可从 .flow 文件回放。
    """
    if not headers:
        return {}
    return {str(k): str(v) for k, v in headers.items()}


def _header_value(headers: dict[str, Any], name: str) -> str:
    """
    大小写无关读取 header。

    :param headers: 已转成普通 dict 的 headers
    :param name: 目标 header 名
    :return: 找到时返回 header 值，否则返回空字符串
    """
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return str(value)
    return ""


def _redact_header_value(name: str, value: Any) -> Any:
    """
    对轻量索引里的敏感 header 值做脱敏。

    :param name: header 名
    :param value: header 值
    :return: 脱敏后可写入 capture_index.json 的值
    """
    if _SENSITIVE_HEADER_RE.search(name):
        return "[redacted]"
    return value


def _redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
    """
    脱敏轻量索引中的 header 字段。

    :param headers: 原始 header dict
    :return: 脱敏后的 header dict
    """
    return {
        str(key): _redact_header_value(str(key), value)
        for key, value in headers.items()
    }


def _flow_host_values(flow: http.HTTPFlow) -> tuple[str, ...]:
    """
    返回 mitmproxy 在不同阶段可见的主机名候选。

    Claude Code 走 TUN + SOCKS5 后，request.host 可能已经是解析后的 IP，
    但 Host header / SNI 仍保留原始域名；采集过滤必须同时看这些字段。
    """
    values = [
        flow.request.host,
        flow.request.pretty_host,
        flow.request.headers.get("host"),
        flow.request.headers.get(":authority"),
        getattr(flow.server_conn, "sni", None),
        getattr(flow.client_conn, "sni", None),
    ]
    return tuple(str(v).lower() for v in values if v)


def _should_record(flow: http.HTTPFlow) -> bool:
    """
    判断是否记录 Anthropic / Claude API 流量。

    域名被代理链路改写为 IP 时，路径仍能区分 Claude API 与普通网页依赖下载。
    """
    hosts = _flow_host_values(flow)
    if any(keyword in host for host in hosts for keyword in CAPTURE_TARGETS):
        return True
    path = flow.request.path or ""
    return any(path.startswith(prefix) for prefix in TARGET_API_PATH_PREFIXES)


def _should_capture_full_http(flow: http.HTTPFlow) -> bool:
    """
    判断完整 HTTP JSONL 是否记录该 flow。

    :param flow: mitmproxy flow
    :return: capture scope 为 all 时记录所有 HTTP flow，否则沿用目标流量过滤
    """
    return CAPTURE_SCOPE == "all" or _should_record(flow)


def _record_host(flow: http.HTTPFlow) -> str:
    """优先返回可读域名，避免 stats.jsonl 里只剩 IP。"""
    for host in _flow_host_values(flow):
        if any(keyword in host for keyword in CAPTURE_TARGETS):
            return host
    return flow.request.host or ""


def _classify_flow(flow: http.HTTPFlow) -> dict[str, Any]:
    """
    给抓包索引补充分类字段，便于后续从全量 HTTP 中筛遥测和 Anthropic 主链路。

    :param flow: mitmproxy flow
    :return: 分类信息
    """
    host = _record_host(flow)
    path = flow.request.path or ""
    headers = _headers_dict(flow.request.headers)
    haystack = " ".join([
        host,
        flow.request.pretty_host or "",
        path,
        _header_value(headers, "user-agent"),
        _header_value(headers, "content-type"),
    ])
    return {
        "capture_scope": CAPTURE_SCOPE,
        "is_target": _should_record(flow),
        "is_anthropic": any(keyword in host for keyword in TARGET_HOST_KEYWORDS),
        "is_telemetry_candidate": bool(_TELEMETRY_RE.search(haystack)),
    }


def _capture_body(message: http.Message | None) -> dict[str, Any]:
    """
    编码 HTTP body，默认全文保存。

    :param message: request 或 response 对象
    :return: body_text/body_base64/body_encoding/body_bytes/body_truncated
    """
    raw = bytes(message.raw_content or b"") if message else b""
    body_bytes = len(raw)
    truncated = False
    if CAPTURE_MAX_BODY_BYTES > 0 and len(raw) > CAPTURE_MAX_BODY_BYTES:
        raw = raw[:CAPTURE_MAX_BODY_BYTES]
        truncated = True
    body_text: str | None = None
    body_base64: str | None = None
    encoding = "empty"
    if raw:
        try:
            body_text = message.get_text(strict=False) if message else raw.decode("utf-8", errors="replace")
            if CAPTURE_MAX_BODY_BYTES > 0 and body_text is not None:
                encoded = body_text.encode("utf-8")
                if len(encoded) > CAPTURE_MAX_BODY_BYTES:
                    body_text = encoded[:CAPTURE_MAX_BODY_BYTES].decode("utf-8", errors="replace")
                    truncated = True
            encoding = "text"
        except Exception:
            body_base64 = base64.b64encode(raw).decode("ascii")
            encoding = "base64"
    return {
        "body_text": body_text,
        "body_base64": body_base64,
        "body_encoding": encoding,
        "body_bytes": body_bytes,
        "body_truncated": truncated,
    }


def _parse_billing_header(value: str) -> dict[str, str]:
    """
    解析 x-anthropic-billing-header 中的 key=value 片段。

    :param value: header 原文
    :return: 解析出的字段
    """
    return {m.group(1): m.group(2) for m in _BILLING_PART_RE.finditer(value or "")}


def _extract_analysis(flow: http.HTTPFlow, body: str) -> dict[str, Any]:
    """
    提取 Claude Code 版本、入口和 CCH/指纹相关 header。

    :param flow: mitmproxy flow
    :param body: 响应文本，用于复用 usage 解析
    :return: 轻量分析字段
    """
    req_headers = _headers_dict(flow.request.headers)
    billing_header = _header_value(req_headers, "x-anthropic-billing-header")
    billing = _parse_billing_header(billing_header)
    cch_headers = {
        key: value
        for key, value in req_headers.items()
        if _CCH_RE.search(key)
    }
    resp_headers = _headers_dict(flow.response.headers if flow.response else None)
    content_type = _header_value(resp_headers, "content-type").lower()
    usage: dict[str, Any] | None = None
    if "event-stream" in content_type or body.startswith("event:"):
        usage = _extract_usage_from_sse(body)
    else:
        data = _safe_json_loads(body)
        if isinstance(data, dict) and isinstance(data.get("usage"), dict):
            usage = data["usage"]
    return {
        "billing_header": billing_header or None,
        "billing": billing,
        "cc_version": billing.get("cc_version"),
        "cc_entrypoint": billing.get("cc_entrypoint"),
        "cch_headers": cch_headers,
        "usage": usage,
    }


def _capture_record(flow: http.HTTPFlow) -> dict[str, Any]:
    """构造完整 HTTP 抓包记录。:param flow: 当前流。:return: 私有完整记录。"""
    host = _record_host(flow)
    response_body = _capture_body(flow.response)
    response_text = response_body.get("body_text") or ""
    return {
        "ts": time.time(),
        "flow_id": flow.id,
        "client_connection_id": getattr(flow.client_conn, "id", None),
        "request": {
            "method": flow.request.method,
            "scheme": flow.request.scheme,
            "host": host,
            "pretty_host": flow.request.pretty_host,
            "path": flow.request.path,
            "query": flow.request.query.__repr__(),
            "headers": _headers_dict(flow.request.headers),
            **_capture_body(flow.request),
        },
        "response": {
            "status": flow.response.status_code if flow.response else None,
            "headers": _headers_dict(flow.response.headers if flow.response else None),
            **response_body,
        },
        "analysis": _extract_analysis(flow, response_text),
        "classification": _classify_flow(flow),
    }


def _capture_index_entry(record: dict[str, Any]) -> dict[str, Any]:
    """从完整抓包记录生成轻量索引条目。"""
    request = record.get("request") if isinstance(record.get("request"), dict) else {}
    response = record.get("response") if isinstance(record.get("response"), dict) else {}
    analysis = record.get("analysis") if isinstance(record.get("analysis"), dict) else {}
    classification = record.get("classification") if isinstance(record.get("classification"), dict) else {}
    request_headers = request.get("headers") if isinstance(request.get("headers"), dict) else {}
    response_headers = response.get("headers") if isinstance(response.get("headers"), dict) else {}
    return {
        "ts": record.get("ts"),
        "flow_id": record.get("flow_id"),
        "client_connection_id": record.get("client_connection_id"),
        "capture_context": record.get("capture_context"),
        "capture_context_status": record.get("capture_context_status"),
        "capture_context_error": record.get("capture_context_error"),
        "capture_state": record.get("capture_state", "complete"),
        "capture_message": record.get("capture_message"),
        "request": {
            "method": request.get("method"),
            "host": request.get("host"),
            "path": request.get("path"),
            "headers": {
                "x-anthropic-billing-header": _redact_header_value(
                    "x-anthropic-billing-header",
                    _header_value(request_headers, "x-anthropic-billing-header"),
                ),
            },
            "body_bytes": request.get("body_bytes"),
            "body_encoding": request.get("body_encoding"),
            "body_truncated": request.get("body_truncated"),
        },
        "response": {
            "status": response.get("status"),
            "headers": {
                "content-type": _redact_header_value(
                    "content-type",
                    _header_value(response_headers, "content-type"),
                ),
            },
            "body_bytes": response.get("body_bytes"),
            "body_encoding": response.get("body_encoding"),
            "body_truncated": response.get("body_truncated"),
        },
        "analysis": {
            "cc_version": analysis.get("cc_version"),
            "cc_entrypoint": analysis.get("cc_entrypoint"),
            "cch_headers": _redact_headers(analysis.get("cch_headers") or {}),
            "usage": analysis.get("usage"),
        },
        "classification": {
            "capture_scope": classification.get("capture_scope"),
            "is_target": bool(classification.get("is_target")),
            "is_anthropic": bool(classification.get("is_anthropic")),
            "is_telemetry_candidate": bool(classification.get("is_telemetry_candidate")),
        },
    }


def _write_capture_index(entry: dict[str, Any]) -> None:
    """
    重写轻量索引文件。

    文件体量远小于完整抓包，逐条重写能让前端在 run 进行中看到最新索引。
    """
    existing: list[dict[str, Any]] = []
    if os.path.exists(CAPTURE_INDEX_FILE):
        try:
            with open(CAPTURE_INDEX_FILE, encoding="utf-8") as f:
                data = json.loads(f.read())
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                existing = [item for item in data["entries"] if isinstance(item, dict)]
        except Exception:
            existing = []
    # 请求先落盘、响应后更新同一条索引；完整 JSONL 仍按事件追加，避免改写旧证据。
    existing = [item for item in existing if item.get("flow_id") != entry.get("flow_id")]
    existing.append(entry)
    versions = sorted({
        item.get("analysis", {}).get("cc_version")
        for item in existing
        if isinstance(item.get("analysis"), dict) and item.get("analysis", {}).get("cc_version")
    })
    payload = {
        "schema_version": 1,
        "capture_mode": os.environ.get("CAPTURE_MODE", "full_http"),
        "updated_at": time.time(),
        "total_flows": len(existing),
        "cc_versions": versions,
        "entries": existing,
    }
    tmp = f"{CAPTURE_INDEX_FILE}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, CAPTURE_INDEX_FILE)


class Recorder:
    """统计流量，并对已归属当前账号的模型请求执行被动额度门禁。"""

    def __init__(self) -> None:
        """初始化本次执行的额度观察。

        :return: None
        """
        self.quota_source = os.environ.get("QUOTA_SOURCE", "")
        self.quota_identity = os.environ.get("QUOTA_IDENTITY", "")
        self.quota_state_file = os.environ.get("QUOTA_STATE_FILE", "")
        self.quota_signal_file = os.environ.get("QUOTA_SIGNAL_FILE", "")
        self.quota_file = os.environ.get("QUOTA_OBSERVATIONS_FILE", "")
        self.quota_local: dict = {}
        self.quota_cached: dict = {}
        self.quota_state_valid = False
        self.quota_warmup = os.environ.get("QUOTA_WARMUP", "0") == "1"
        self.warmup_flows: dict[str, http.HTTPFlow] = {}
        self.warmup_finished: set[str] = set()
        self._pending_quota: tuple[dict, str, bool] | None = None
        self._warmup_task: asyncio.Task | None = None
        self.quota_control_failed = False
        self.capture_pending: dict[str, http.HTTPFlow] = {}
        self.capture_closing = False
        self.capture_interrupted: set[str] = set()
        self.capture_context, self.capture_context_status, self.capture_context_error = capture_context_snapshot(
            os.environ.get("CAPTURE_CONTEXT", ""), self.quota_source)

    def tls_clienthello(self, data: tls.ClientHelloData) -> None:
        """仅观察客户端到 Recorder 的 offer，采集故障不改变 TLS 转发。

        :param data: mitmproxy 11.1.3 的客户端握手事件。
        :return: None；不修改握手策略、连接或上游 TLS。
        """
        if not CAPTURE_FULL_HTTP:
            return
        connection_id = None
        try:
            connection_id = data.context.client.id
            hello = data.client_hello
            try:
                parsed = parse_clienthello(hello.raw_bytes(wrap_in_record=False))
            except NotImplementedError:
                # 固定 SDK 尚不支持 DTLS 本体提取，不能用合成 TLS record 冒充原文。
                parsed = {"transport": "unsupported", "parse_status": "unsupported",
                          "parse_error": "clienthello_transport_unsupported", "ja3": None}
            sni = parsed.get("sni")
            target_status = ("target" if any(keyword in sni.lower() for keyword in CAPTURE_TARGETS)
                             else "non_target") if sni else "unclassified"
            if CAPTURE_SCOPE != "all" and target_status == "non_target":
                return
            record: dict[str, Any] = {
                "schema": 1, "event": "tls_clienthello", "ts": time.time(),
                "direction": "client_to_recorder", "transport": "tcp",
                "client_connection_id": connection_id,
                "capture_context": self.capture_context, "capture_context_status": self.capture_context_status,
                "capture_context_error": self.capture_context_error,
                "capture_scope": CAPTURE_SCOPE, "target_status": target_status,
            }
            record.update(parsed)
            append_private_jsonl(Path(CAPTURE_FILE).with_name("tls_clienthello.jsonl"), record)
            if record["parse_status"] != "ok":
                self._capture_tls_diagnostic("tls_clienthello_parse_failed", connection_id)
        except Exception:
            # hook 是观察者：磁盘、解析或 SDK 属性故障都不能取消已接受的业务握手。
            self._capture_tls_diagnostic("tls_clienthello_capture_failed", connection_id)

    def _capture_tls_diagnostic(self, code: str, connection_id: str | None) -> None:
        """仅写固定 TLS 诊断，不把原始异常和恢复材料放进统计。"""
        try:
            _jsonl_append(STATS_FILE, {"ts": time.time(), "event": "tls_clienthello_error",
                                      "client_connection_id": connection_id, "error": code})
        except Exception:
            pass

    def running(self) -> None:
        """启动养号状态观察；普通作业不增加后台任务。@return None。"""
        if self.quota_warmup and self._warmup_task is None:
            self._warmup_task = asyncio.create_task(self._watch_warmup())

    def done(self) -> None:
        """撤销本执行观察任务，避免上下文切换后沿用旧作业。@return None。"""
        if self._warmup_task is not None:
            self._warmup_task.cancel()
        self.capture_closing = True
        for flow in list(self.capture_pending.values()):
            self._persist_capture(flow, "interrupted", "Recorder 已停止，响应未完成")

    def _persist_capture(self, flow: http.HTTPFlow, state: str, message: str | None = None) -> None:
        """追加真实已取得的 HTTP 内容，索引只保留当前流的最新阶段。

        :param flow: 实际 HTTP 流。
        :param state: pending、complete 或 interrupted。
        :param message: 固定的中断说明，不含上游敏感错误原文。
        :return: None；落盘失败另写统计错误，不能干扰转发。
        """
        if not CAPTURE_FULL_HTTP or not _should_capture_full_http(flow):
            return
        # mitmproxy 停止时仍可能派发迟到 response；新字节可以追加，中断事实不能被覆盖。
        if state == 'complete' and (self.capture_closing or flow.id in self.capture_interrupted):
            state, message = 'interrupted', '采集已中断，仅保留实际收到的响应内容'
        if state == 'interrupted':
            self.capture_interrupted.add(flow.id)
        try:
            record = _capture_record(flow)
            record.update(capture_context=self.capture_context, capture_context_status=self.capture_context_status,
                          capture_context_error=self.capture_context_error)
            record.update(capture_state=state, capture_message=message)
            _jsonl_append(CAPTURE_FILE, record)
            _write_capture_index(_capture_index_entry(record))
            if state == "pending":
                self.capture_pending[flow.id] = flow
            else:
                self.capture_pending.pop(flow.id, None)
        except Exception:
            # 保留先前成功落盘的记录，不以索引失败阻断账号请求。
            try:
                _jsonl_append(STATS_FILE, {"ts": time.time(), "flow_id": flow.id, "error": "HTTP 抓包落盘失败"})
            except OSError:
                pass

    async def _watch_warmup(self) -> None:
        """有界读取真实共享状态，API 更新也能让养号在收尾后暂停。"""
        while True:
            await asyncio.sleep(0.2)
            try:
                self._check_warmup_pause()
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                self._pause_quota({"message": "养号额度策略或许可不可读取，已停止执行",
                                   "resume_at": None, "exhausted": []}, "failed")

    def _prune_warmup_flows(self) -> None:
        """响应钩子后仍等待代理发送结束，不能提前杀掉缓冲响应。"""
        for flow_id in list(self.warmup_finished):
            flow = self.warmup_flows.get(flow_id)
            if flow is None or not getattr(flow, "live", False):
                self.warmup_finished.discard(flow_id)
                self.warmup_flows.pop(flow_id, None)

    def _warmup_decision(self, state: dict) -> dict:
        """计算当前执行是否还有正式请求许可，不修改共用真实窗口。"""
        policy = state.get("warmup_quota")
        if not isinstance(policy, dict) or not isinstance(policy.get("limits"), dict):
            raise ValueError("养号策略上下文缺失")
        # v3 与控制端共用被动恢复规则；空闲窗口没有 reset 不代表耗掉旧 runner 的单次许可。
        decision = (passive_recovery_decision(state, policy["limits"], time.time())
            if policy.get("policy_key") == "v3-passive-recovery"
            else warmup_quota_decision(state, policy["limits"], time.time()))
        if not decision["sample_required"]:
            return decision
        admission = policy.get("admission")
        granted = (isinstance(admission, dict) and admission.get("identity") == self.quota_identity
                   and admission.get("source") == self.quota_source
                   and warmup_sample_used(decision, admission))
        marker = Path(self.quota_signal_file).with_name("warmup-sample.json")
        used = False
        if granted and marker.exists():
            saved = json.loads(marker.read_text())
            if saved != {key: admission[key] for key in ("identity", "policy_key", "window_key", "source")}:
                raise ValueError("养号单次请求标记不匹配")
            used = True
        if not granted or used:
            decision.update(blocked=True, resume_at=None,
                            message="养号单次额度更新机会已使用，等待新的真实额度或调整阈值")
        return decision

    def _check_warmup_pause(self) -> None:
        """仅在当前养号所有已接受流结束后发布等待信号。"""
        self._prune_warmup_flows()
        state = self._quota_state()
        if not self.quota_state_valid:
            raise ValueError("共享额度身份或文件无效")
        merged = merge_quota_observation(state, self.quota_local) if self.quota_local else state
        decision = self._warmup_decision(merged)
        if not decision["enabled"]:
            self._pending_quota = None
            Path(self.quota_signal_file).with_name("warmup-draining.json").unlink(missing_ok=True)
            return
        common = quota_decision(merged, time.time())
        if merged.get("account_error"):
            self.quota_local["account_error"] = merged["account_error"]
            self._pause_quota({"message": f"{merged['account_error']}：账号异常，需人工处理",
                               "resume_at": None, "exhausted": []})
            return
        if common["blocked"] or (common["retry_ready"] and state.get("recovery_source") != self.quota_source):
            self._pause_quota(common)
        elif decision["blocked"]:
            self._pause_quota({**decision, "exhausted": []}, warmup_wait=True)
        else:
            self._pending_quota = None
            Path(self.quota_signal_file).with_name("warmup-draining.json").unlink(missing_ok=True)

    def _finish_warmup_flow(self, flow: http.HTTPFlow) -> None:
        """标记代理响应/错误已结束，等待实际发送结束后再放行暂停。"""
        if self.quota_warmup and flow.id in self.warmup_flows:
            self.warmup_finished.add(flow.id)
            try:
                self._check_warmup_pause()
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                # 控制异常仍保留正常统计/认证分类，不能中断后续 response 收尾。
                self._pause_quota({"message": "养号额度策略不可读取，已停止执行",
                                   "resume_at": None, "exhausted": []}, "failed")

    def error(self, flow: http.HTTPFlow) -> None:
        """异常流同样释放收尾等待，不为失败补发请求。

        :param flow: 当前 HTTP 错误流
        :return: None
        """
        self._finish_warmup_flow(flow)
        self._persist_capture(flow, "interrupted", "HTTP 连接中断，响应未完成")

    def _quota_state(self) -> dict:
        try:
            state = json.loads(Path(self.quota_state_file).read_text())
            if not isinstance(state.get("windows", {}), dict):
                raise ValueError("额度窗口结构无效")
            self.quota_state_valid = state.get("identity") == self.quota_identity
            if self.quota_state_valid:
                self.quota_cached = state
            return self.quota_cached
        except (OSError, ValueError, AttributeError):
            self.quota_state_valid = False
            return self.quota_cached

    def _owns_model_request(self, flow: http.HTTPFlow, state: dict) -> bool:
        if not self.quota_source or flow.request.path.split("?", 1)[0] != "/v1/messages":
            return False
        if not any(host.split(":", 1)[0] == "api.anthropic.com"
                   for host in _flow_host_values(flow)):
            return False
        auth = _header_value(_headers_dict(flow.request.headers), "authorization")
        if not auth.lower().startswith("bearer "):
            return False
        hashes = set(state.get("token_hashes") or [])
        # 既有 OAuth 刷新可在一个请求内更换 AT；只读当前本地凭据，绝不刷新或记录明文。
        try:
            credentials = json.loads(Path(os.environ["QUOTA_CREDENTIALS_FILE"]).read_text())
            token = credentials.get("claudeAiOauth", {}).get("accessToken")
            if isinstance(token, str) and token:
                hashes.add(hashlib.sha256(token.encode()).hexdigest())
        except (OSError, ValueError, KeyError, AttributeError):
            pass
        return hashlib.sha256(auth[7:].strip().encode()).hexdigest() in hashes

    def _write_quota_control(self, path: Path, payload: dict) -> bool:
        """控制写入失败仍拒绝请求，不能因异常跳过本地响应而直达上游。"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False))
            temporary.replace(path)
            return True
        except (OSError, ValueError):
            self.quota_control_failed = True
            return False

    def _pause_quota(self, decision: dict, status: str = "quota_wait", warmup_wait: bool = False) -> None:
        if not self.quota_signal_file:
            return
        self._prune_warmup_flows()
        if (self.quota_warmup and status == "quota_wait" and not self.quota_local.get("account_error")
                and (warmup_wait or self.quota_cached.get("warmup_quota", {}).get("enabled"))
                and self.warmup_flows):
            pending = (decision, status, warmup_wait)
            if self._pending_quota != pending:
                path = Path(self.quota_signal_file).with_name("warmup-draining.json")
                if self._write_quota_control(path, {"source": self.quota_source, "status": "draining"}):
                    self._pending_quota = pending
            return
        path = Path(self.quota_signal_file)
        payload = {"source": self.quota_source, "status": status,
                   "error": decision["message"], "resume_at": decision["resume_at"],
                   "exhausted": decision["exhausted"], "quota_state": self.quota_local}
        if warmup_wait:
            payload["warmup_wait"] = True
        written = self._write_quota_control(path, payload)
        if self.quota_warmup and written:
            path.with_name("warmup-draining.json").unlink(missing_ok=True)
            self._pending_quota = None

    def _quota_gate(self, flow: http.HTTPFlow) -> bool:
        state = self._quota_state()
        candidate = (self.quota_source and flow.request.path.split("?", 1)[0] == "/v1/messages"
                     and any(host.split(":", 1)[0] == "api.anthropic.com" for host in _flow_host_values(flow))
                     and _header_value(_headers_dict(flow.request.headers), "authorization").lower().startswith("bearer "))
        if candidate and (not self.quota_state_valid or self.quota_control_failed):
            flow.response = http.Response.make(503, b'{"type":"error","error":{"type":"api_error","message":"quota guard unavailable"}}',
                                               {"content-type": "application/json", "x-vibebench-quota-blocked": "1"})
            self._pause_quota({"message": "额度门禁不可读取，已停止当前执行", "resume_at": None, "exhausted": []}, "failed")
            return False
        if not self._owns_model_request(flow, state):
            return True
        try:
            merged = merge_quota_observation(state, self.quota_local) if self.quota_local else state
            if self.quota_local.get("account_error"):
                merged["account_error"] = self.quota_local["account_error"]
            decision = quota_decision(merged, time.time())
        except (ValueError, TypeError, AttributeError):
            flow.response = http.Response.make(503, b'{"type":"error","error":{"type":"api_error","message":"invalid quota state"}}',
                                               {"content-type": "application/json", "x-vibebench-quota-blocked": "1"})
            self._pause_quota({"message": "额度状态结构无效，已停止执行", "resume_at": None, "exhausted": []}, "failed")
            return False
        if merged.get("account_error"):
            decision.update(blocked=True, retry_ready=False, resume_at=None, exhausted=[],
                            message=f"{merged['account_error']}：账号异常，需人工处理")
        if not decision["blocked"] and (not decision["retry_ready"]
                or state.get("recovery_source") == self.quota_source):
            if self.quota_warmup:
                try:
                    warmup = self._warmup_decision(merged)
                    if warmup["blocked"]:
                        flow.response = http.Response.make(429, json.dumps({
                            "type": "error", "error": {"type": "rate_limit_error", "message": warmup["message"]},
                        }).encode(), {"content-type": "application/json", "x-vibebench-quota-blocked": "1"})
                        self._pause_quota({**warmup, "exhausted": []}, warmup_wait=True)
                        if self.quota_control_failed:
                            flow.response = http.Response.make(503, b'{"type":"error","error":{"type":"api_error","message":"quota control unavailable"}}',
                                                               {"content-type": "application/json", "x-vibebench-quota-blocked": "1"})
                        return False
                    if warmup["sample_required"]:
                        admission = state["warmup_quota"]["admission"]
                        marker = Path(self.quota_signal_file).with_name("warmup-sample.json")
                        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(descriptor, "w") as output:
                            json.dump({key: admission[key] for key in ("identity", "policy_key", "window_key", "source")}, output)
                            output.flush()
                            os.fsync(output.fileno())
                        directory = os.open(marker.parent, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            os.fsync(directory)
                        finally:
                            os.close(directory)
                except (OSError, ValueError, TypeError, KeyError, AttributeError):
                    flow.response = http.Response.make(503, b'{"type":"error","error":{"type":"api_error","message":"warmup quota guard unavailable"}}',
                                                       {"content-type": "application/json", "x-vibebench-quota-blocked": "1"})
                    self._pause_quota({"message": "养号额度许可不可读取，已停止执行", "resume_at": None, "exhausted": []}, "failed")
                    return False
            return True
        flow.response = http.Response.make(429, json.dumps({
            "type": "error", "error": {"type": "rate_limit_error",
            "message": decision["message"] or "等待账号原任务更新额度"},
        }).encode(), {"content-type": "application/json", "x-vibebench-quota-blocked": "1"})
        self._pause_quota(decision)
        return False

    def responseheaders(self, flow: http.HTTPFlow) -> None:
        """
        流响应尚未完成时就采集额度头，避免 CLI 已开始重试而主服务尚未收到正文。

        :param flow: mitmproxy 流
        :return: None
        """
        state = self._quota_state()
        if not self._owns_model_request(flow, state) or flow.response.headers.get("x-vibebench-quota-blocked"):
            return
        headers = {key.lower(): value for key, value in _headers_dict(flow.response.headers).items()
                   if key.lower().startswith("anthropic-ratelimit-unified-") or key.lower() == "retry-after"}
        now = time.time()
        observation = quota_observation(headers, flow.response.status_code, now)
        self.quota_local = merge_quota_observation(self.quota_local, observation)
        try:
            _jsonl_append(self.quota_file, {"source": self.quota_source, "identity": self.quota_identity,
                                          "ts": now, "status": flow.response.status_code, "headers": headers})
        except OSError:
            # 观察文件故障也必须终止请求；控制文件带归一化补证，避免清容器时丢掉 reset。
            pass
        finally:
            if any(value.get("rejected") for key, value in observation["windows"].items()
                   if key in ("five_hour", "seven_day")):
                self._pause_quota(quota_decision(merge_quota_observation(state, self.quota_local), now))

    def requestheaders(self, flow: http.HTTPFlow) -> None:
        """
        在请求阶段先落一条记录。

        响应解析失败或长流被中断时仍能统计请求数，避免 UI 永远显示 0。

        :param flow: mitmproxy 流
        :return: None
        """
        admitted = self._quota_gate(flow)
        if self.quota_warmup and admitted and self._owns_model_request(flow, self.quota_cached):
            self.warmup_flows[flow.id] = flow
        if not _should_record(flow):
            return
        try:
            host = _record_host(flow)
            stat = {
                "ts": time.time(),
                "phase": "request",
                "flow_id": flow.id,
                "host": host,
                "method": flow.request.method,
                "path": flow.request.path,
                "req_bytes": len(flow.request.raw_content or b""),
            }
            _jsonl_append(STATS_FILE, stat)
        except Exception:
            pass

    def request(self, flow: http.HTTPFlow) -> None:
        """仅在 v3 保存实际 CLI 消息身份，不把 userID 或 machine-id 当成设备 ID。

        :param flow: 完整请求 body 已可读取的 CLI 流
        :return: None；缺少明确身份时保持未确认
        """
        self._persist_capture(flow, "pending")
        if os.environ.get("V3_ACCOUNT") != "1" or not any(
                host.rstrip(".") in ("api.anthropic.com", "api.anthropic.com:443")
                for host in _flow_host_values(flow)):
            return
        if flow.request.path.split("?", 1)[0] != "/v1/messages":
            return
        try:
            body = json.loads(flow.request.raw_content or b"{}")
            user_id = body.get("metadata", {}).get("user_id")
            identity = json.loads(user_id) if isinstance(user_id, str) else None
            if not isinstance(identity, dict) or not re.fullmatch(r"[a-f0-9]{64}", identity.get("device_id", "")):
                return
            observed = {"device_id": identity["device_id"], "account_uuid": identity.get("account_uuid"),
                "source": "cli:/v1/messages:metadata.user_id.device_id", "observed_at": time.time()}
            path = Path("/run/v3/identity.json")
            if path.exists():
                previous = json.loads(path.read_text())
                if previous.get("conflict") or previous.get("device_id") != observed["device_id"] or previous.get("account_uuid") != observed["account_uuid"]:
                    observed["conflict"] = True
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(observed))
            temporary.chmod(0o600)
            temporary.replace(path)
        except (ValueError, TypeError, AttributeError, OSError):
            return

    def response(self, flow: http.HTTPFlow) -> None:
        """
        保存原有响应统计，并以有限错误码补充明确账号停用事实。

        :param flow: mitmproxy 流
        :return: None
        """
        self._finish_warmup_flow(flow)
        if not _should_record(flow):
            return
        try:
            host = _record_host(flow)
            body = flow.response.get_text(strict=False) or ""
            if self._owns_model_request(flow, self._quota_state()) and flow.response.status_code in (401, 403):
                data = _safe_json_loads(body)
                error = data.get("error") if isinstance(data, dict) else None
                detail = str(error.get("message") or "").lower() if isinstance(error, dict) else ""
                if isinstance(error, dict) and (error.get("type") == "account_on_hold" or any(marker in detail for marker in (
                    "account_on_hold", "account is on hold", "account has been suspended", "organization has been disabled",
                ))):
                    self.quota_local["account_error"] = "account_on_hold"
                    try:
                        _jsonl_append(self.quota_file, {"source": self.quota_source, "identity": self.quota_identity,
                            "ts": time.time(), "status": flow.response.status_code, "headers": {}, "account_error": "account_on_hold"})
                    finally:
                        # 封号信号必须自带有限分类；日志故障或随后的清理不能丢失永久停止事实。
                        self._pause_quota({"message": "account_on_hold：账号被上游停用", "resume_at": None, "exhausted": []})
            usage: dict[str, Any] | None = None
            content_type = (flow.response.headers.get("content-type") or "").lower()
            if "event-stream" in content_type or body.startswith("event:"):
                usage = _extract_usage_from_sse(body)
            else:
                data = _safe_json_loads(body)
                if isinstance(data, dict) and isinstance(data.get("usage"), dict):
                    usage = data["usage"]

            stat = {
                "ts": time.time(),
                "phase": "response",
                "flow_id": flow.id,
                "host": host,
                "method": flow.request.method,
                "path": flow.request.path,
                "status": flow.response.status_code,
                "req_bytes": len(flow.request.raw_content or b""),
                "resp_bytes": len(flow.response.raw_content or b""),
                "usage": usage,
            }
            _jsonl_append(STATS_FILE, stat)
            self._persist_capture(flow, "complete")
        except Exception as e:
            # 记录失败但不影响转发
            try:
                _jsonl_append(STATS_FILE, {"ts": time.time(), "error": str(e)})
            except Exception:
                pass


addons = [Recorder()]
