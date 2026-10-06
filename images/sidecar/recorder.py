"""
mitmproxy addon：抽取 Anthropic API 流量的 token / 状态码，按行落盘 stats.jsonl。
分析抓包模式下额外保存完整 HTTP 请求/响应体和轻量索引。
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from mitmproxy import http
from quota_protocol import merge_quota_observation, quota_decision, quota_observation

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
    """构造完整 HTTP 抓包记录。"""
    host = _record_host(flow)
    response_body = _capture_body(flow.response)
    response_text = response_body.get("body_text") or ""
    return {
        "ts": time.time(),
        "flow_id": flow.id,
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

    def _quota_state(self) -> dict:
        try:
            state = json.loads(Path(self.quota_state_file).read_text())
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

    def _pause_quota(self, decision: dict, status: str = "quota_wait") -> None:
        if not self.quota_signal_file:
            return
        path = Path(self.quota_signal_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"source": self.quota_source, "status": status,
                   "error": decision["message"], "resume_at": decision["resume_at"],
                   "exhausted": decision["exhausted"], "quota_state": self.quota_local}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False))
        tmp.replace(path)

    def _quota_gate(self, flow: http.HTTPFlow) -> None:
        state = self._quota_state()
        if not self._owns_model_request(flow, state):
            return
        if not self.quota_state_valid:
            # 状态挂载失效时不把账号伪装成未知可用；此处是执行故障而非额度耗尽。
            self._pause_quota({"message": "额度门禁不可读取，已停止当前执行", "resume_at": None, "exhausted": []}, "failed")
            flow.response = http.Response.make(503, b'{"type":"error","error":{"type":"api_error","message":"quota guard unavailable"}}',
                                               {"content-type": "application/json", "x-vibebench-quota-blocked": "1"})
            return
        merged = merge_quota_observation(state, self.quota_local) if self.quota_local else state
        if self.quota_local.get("account_error"):
            merged["account_error"] = self.quota_local["account_error"]
        decision = quota_decision(merged, time.time())
        if merged.get("account_error"):
            decision.update(blocked=True, retry_ready=False, resume_at=None, exhausted=[],
                            message=f"{merged['account_error']}：账号异常，需人工处理")
        if not decision["blocked"] and (not decision["retry_ready"]
                or state.get("recovery_source") == self.quota_source):
            return
        self._pause_quota(decision)
        flow.response = http.Response.make(429, json.dumps({
            "type": "error", "error": {"type": "rate_limit_error",
            "message": decision["message"] or "等待账号原任务更新额度"},
        }).encode(), {"content-type": "application/json", "x-vibebench-quota-blocked": "1"})

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
        self._quota_gate(flow)
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

    def response(self, flow: http.HTTPFlow) -> None:
        """
        保存原有响应统计，并以有限错误码补充明确账号停用事实。

        :param flow: mitmproxy 流
        :return: None
        """
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
            if CAPTURE_FULL_HTTP and _should_capture_full_http(flow):
                record = _capture_record(flow)
                _jsonl_append(CAPTURE_FILE, record)
                _write_capture_index(_capture_index_entry(record))
        except Exception as e:
            # 记录失败但不影响转发
            try:
                _jsonl_append(STATS_FILE, {"ts": time.time(), "error": str(e)})
            except Exception:
                pass


addons = [Recorder()]
