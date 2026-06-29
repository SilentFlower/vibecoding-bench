#!/usr/bin/env python3
"""生成 Claude Code telemetry 的脱敏字段目录。"""

from __future__ import annotations

import argparse
import base64
import collections
import json
from pathlib import Path
from typing import Any


SAFE_SOURCES = {
    "renderer_mode": ("客户端本地不可得", "低"),
    "subscription_type": ("账号 profile 可推导", "低"),
    "model": ("请求体可推导", "低"),
    "preNormalizedModel": ("请求体可推导", "低"),
    "betas": ("请求 header 可推导", "低"),
    "provider": ("网关运行时可推导", "低"),
    "requestId": ("网关运行时可推导", "低"),
    "previousRequestId": ("网关运行时可推导", "低"),
    "queryChainId": ("网关运行时可推导", "低"),
    "queryDepth": ("网关运行时可推导", "低"),
    "messageID": ("网关运行时可推导", "低"),
    "durationMs": ("响应可推导", "低"),
    "durationMsIncludingRetries": ("响应可推导", "低"),
    "ttftMs": ("响应可推导", "低"),
    "attempt": ("网关运行时可推导", "低"),
    "stop_reason": ("响应可推导", "低"),
    "inputTokens": ("响应 usage 可推导", "低"),
    "outputTokens": ("响应 usage 可推导", "低"),
    "messageTokens": ("响应 usage 可推导", "低"),
    "cachedInputTokens": ("响应 usage 可推导", "低"),
    "uncachedInputTokens": ("响应 usage 可推导", "低"),
    "toolName": ("请求工具 schema 可推导", "低"),
    "toolInputSizeBytes": ("请求体可推导但需避免正文", "中"),
    "toolResultSizeBytes": ("响应可推导但需避免正文", "中"),
    "permissionMode": ("客户端本地不可得", "低"),
    "querySource": ("客户端本地不可得", "低"),
    "thinkingType": ("请求体可推导", "低"),
    "messagesLength": ("请求体可推导", "低"),
    "messageCount": ("请求体可推导", "低"),
    "textContentLength": ("请求体可推导但需避免正文", "中"),
    "inputTextCharLength": ("请求体可推导但需避免正文", "中"),
    "estimatedInputTokens": ("请求体可推导但需避免正文", "中"),
    "blockCount": ("请求体可推导", "低"),
    "staticBlockLength": ("请求体可推导但需避免正文", "中"),
    "dynamicBlockLength": ("请求体可推导但需避免正文", "中"),
    "totalMessageCount": ("请求体可推导", "低"),
    "markerCount": ("请求体可推导", "低"),
}


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def decode_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        decoded = base64.b64decode(value)
        parsed = json.loads(decoded)
    except Exception:
        return {"<decode_error>": "true"}
    return parsed if isinstance(parsed, dict) else {"<non_object>": value_type(parsed)}


def iter_event_batches(capture: Path):
    with capture.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            request = record.get("request") or {}
            if request.get("path") != "/api/event_logging/v2/batch":
                continue
            body = request.get("body_text")
            if not body:
                continue
            yield float(record.get("ts") or 0), json.loads(body).get("events", [])


def build_catalog(capture: Path) -> dict[str, Any]:
    event_counts: collections.Counter[str] = collections.Counter()
    metadata_counts: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    metadata_types: dict[tuple[str, str], collections.Counter[str]] = collections.defaultdict(collections.Counter)
    top_level_keys: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    batch_sizes: list[int] = []
    gaps: list[float] = []
    previous_ts: float | None = None

    for ts, events in iter_event_batches(capture):
        batch_sizes.append(len(events))
        if previous_ts is not None:
            gaps.append(round(ts - previous_ts, 3))
        previous_ts = ts
        for event in events:
            data = event.get("event_data") or {}
            name = data.get("event_name") or event.get("event_type") or "<missing>"
            event_counts[name] += 1
            for key in data:
                if key != "additional_metadata":
                    top_level_keys[name][key] += 1
            metadata = decode_metadata(data.get("additional_metadata"))
            for key, value in metadata.items():
                metadata_counts[name][key] += 1
                metadata_types[(name, key)][value_type(value)] += 1

    return {
        "batch": {
            "count": len(batch_sizes),
            "event_total": sum(batch_sizes),
            "size_min": min(batch_sizes) if batch_sizes else 0,
            "size_median": sorted(batch_sizes)[len(batch_sizes) // 2] if batch_sizes else 0,
            "size_max": max(batch_sizes) if batch_sizes else 0,
            "gap_min": min(gaps) if gaps else 0,
            "gap_median": sorted(gaps)[len(gaps) // 2] if gaps else 0,
            "gap_max": max(gaps) if gaps else 0,
        },
        "event_counts": event_counts,
        "metadata_counts": metadata_counts,
        "metadata_types": metadata_types,
        "top_level_keys": top_level_keys,
    }


def source_and_sensitivity(key: str) -> tuple[str, str]:
    return SAFE_SOURCES.get(key, ("待分级或客户端本地不可得", "中"))


def write_markdown(catalog: dict[str, Any], output: Path) -> None:
    batch = catalog["batch"]
    event_counts: collections.Counter[str] = catalog["event_counts"]
    metadata_counts = catalog["metadata_counts"]
    metadata_types = catalog["metadata_types"]

    lines = [
        "# Claude Code 2.1.195 telemetry 脱敏事件目录",
        "",
        "## 输入边界",
        "",
        "- 来源：`23594999fa77` 本地 evidence 的 `http_capture.jsonl`。",
        "- 本目录只记录 endpoint、事件名、字段名、字段类型、出现次数、来源和敏感等级。",
        "- 不记录 token、Cookie、Authorization、邮箱、完整账号 UUID、prompt、tool input、响应正文或原始抓包 body。",
        "",
        "## Batch 摘要",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| batch 数 | {batch['count']} |",
        f"| 事件总数 | {batch['event_total']} |",
        f"| batch size min/median/max | {batch['size_min']} / {batch['size_median']} / {batch['size_max']} |",
        f"| batch 间隔 min/median/max | {batch['gap_min']}s / {batch['gap_median']}s / {batch['gap_max']}s |",
        "",
        "## 事件名分布",
        "",
        "| event_name | 数量 |",
        "|---|---:|",
    ]
    for name, count in event_counts.most_common():
        lines.append(f"| `{name}` | {count} |")

    focus_events = [
        "tengu_api_before_normalize",
        "tengu_api_after_normalize",
        "tengu_api_query",
        "tengu_api_success",
        "tengu_api_cache_breakpoints",
        "tengu_sysprompt_boundary_found",
        "tengu_tool_use_can_use_tool_allowed",
        "tengu_tool_use_success",
        "tengu_attachment_compute_duration",
        "tengu_file_operation",
        "tengu_api_slow_first_byte",
    ]
    lines.extend(["", "## 重点事件 additional_metadata", ""])
    for event_name in focus_events:
        total = event_counts.get(event_name, 0)
        if total == 0:
            continue
        lines.extend(
            [
                f"### `{event_name}`",
                "",
                "| key | 出现 | 类型 | 来源 | 敏感等级 |",
                "|---|---:|---|---|---|",
            ]
        )
        for key, count in metadata_counts[event_name].most_common():
            types = ", ".join(
                f"{name}:{type_count}"
                for name, type_count in metadata_types[(event_name, key)].most_common()
            )
            source, sensitivity = source_and_sensitivity(key)
            lines.append(f"| `{key}` | {count}/{total} | {types} | {source} | {sensitivity} |")
        lines.append("")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    write_markdown(build_catalog(args.capture), args.output)


if __name__ == "__main__":
    main()
