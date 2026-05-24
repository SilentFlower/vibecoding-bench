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
TARGET_HOST_KEYWORDS = ("anthropic.com",)


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


class Recorder:
    def response(self, flow: http.HTTPFlow) -> None:
        host = flow.request.host or ""
        if not any(k in host for k in TARGET_HOST_KEYWORDS):
            return
        try:
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
