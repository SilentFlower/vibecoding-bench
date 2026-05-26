"""
mitmproxy addon：抽取 Anthropic API 流量的 token / 状态码，按行落盘 stats.jsonl
完整 flow 已由 --save-stream-file 保存到 .flow 文件，这里只做摘要便于 orchestrator 聚合
"""
from __future__ import annotations
import json
import os
import time
from typing import Any

from mitmproxy import http

STATS_FILE = os.environ.get("STATS_FILE", "/flows/stats.jsonl")
TARGET_HOST_KEYWORDS = ("anthropic.com", "claude.com")
TARGET_API_PATH_PREFIXES = ("/v1/", "/api/oauth/", "/api/eval/")


def _safe_json_loads(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        return None


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
    if any(keyword in host for host in hosts for keyword in TARGET_HOST_KEYWORDS):
        return True
    path = flow.request.path or ""
    return any(path.startswith(prefix) for prefix in TARGET_API_PATH_PREFIXES)


def _record_host(flow: http.HTTPFlow) -> str:
    """优先返回可读域名，避免 stats.jsonl 里只剩 IP。"""
    for host in _flow_host_values(flow):
        if any(keyword in host for keyword in TARGET_HOST_KEYWORDS):
            return host
    return flow.request.host or ""


class Recorder:
    def requestheaders(self, flow: http.HTTPFlow) -> None:
        """
        在请求阶段先落一条记录。

        响应解析失败或长流被中断时仍能统计请求数，避免 UI 永远显示 0。
        """
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
            with open(STATS_FILE, "a") as f:
                f.write(json.dumps(stat, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def response(self, flow: http.HTTPFlow) -> None:
        if not _should_record(flow):
            return
        try:
            host = _record_host(flow)
            body = flow.response.get_text() or ""
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
            with open(STATS_FILE, "a") as f:
                f.write(json.dumps(stat, ensure_ascii=False) + "\n")
        except Exception as e:
            # 记录失败但不影响转发
            try:
                with open(STATS_FILE, "a") as f:
                    f.write(json.dumps({"ts": time.time(), "error": str(e)}) + "\n")
            except Exception:
                pass


addons = [Recorder()]
