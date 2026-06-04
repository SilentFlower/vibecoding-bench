#!/usr/bin/env python3
"""生成安全 wire 指纹摘要。

只输出 endpoint、method、HTTP version、status、header 名顺序、少量安全 header 值、
body 长度范围；不会输出 Authorization、Cookie、请求体或响应体原文。
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mitmproxy import http, io


SAFE_VALUE_HEADERS = {
    "accept",
    "accept-encoding",
    "content-type",
    "user-agent",
    "anthropic-beta",
    "anthropic-version",
    "anthropic-client-platform",
    "x-app",
    "x-service-name",
}


def _text(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return value.decode("latin1")
    return value


def summarize_flow_file(path: Path, host: str | None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with path.open("rb") as fh:
        for flow in io.FlowReader(fh).stream():
            if not isinstance(flow, http.HTTPFlow):
                continue
            req = flow.request
            resp = flow.response
            if host and req.pretty_host != host:
                continue
            endpoint = req.path.split("?", 1)[0]
            header_names: list[str] = []
            safe_values: dict[str, str] = {}
            for key, value in req.headers.fields:
                name = _text(key)
                lower = name.lower()
                header_names.append(name)
                if lower in SAFE_VALUE_HEADERS:
                    safe_values[name] = _text(value)
            grouped[endpoint].append(
                {
                    "method": req.method,
                    "http_version": req.http_version,
                    "status": resp.status_code if resp else None,
                    "header_order": header_names,
                    "safe_values": safe_values,
                    "body_bytes": len(req.raw_content or b""),
                }
            )

    output: list[dict[str, Any]] = []
    for endpoint, items in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        orders = Counter(tuple(item["header_order"]) for item in items)
        output.append(
            {
                "endpoint": endpoint,
                "flow_count": len(items),
                "methods": dict(Counter(item["method"] for item in items)),
                "http_versions": dict(Counter(item["http_version"] for item in items)),
                "statuses": dict(Counter(str(item["status"]) for item in items)),
                "header_orders": [
                    {"count": count, "headers": list(headers)}
                    for headers, count in orders.most_common()
                ],
                "safe_values": {
                    name: dict(Counter(
                        item["safe_values"].get(name)
                        for item in items
                        if name in item["safe_values"]
                    ))
                    for name in sorted({
                        name
                        for item in items
                        for name in item["safe_values"].keys()
                    })
                },
                "body_bytes": {
                    "min": min(item["body_bytes"] for item in items),
                    "max": max(item["body_bytes"] for item in items),
                },
            }
        )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("flow_file", type=Path)
    parser.add_argument("--host", default="api.anthropic.com")
    args = parser.parse_args()
    print(json.dumps(summarize_flow_file(args.flow_file, args.host), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
