#!/usr/bin/env python3
"""生成 Claude Code 2.1.257 与 2.1.260 抓包的脱敏协议摘要。"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import xxhash
from mitmproxy import http, io


_SEED_2156 = 0x4D659218E32A3268
_CCH_RE = re.compile(rb"cch=[a-f0-9]{5}")
_BILLING_RE = re.compile(
    r"cc_version=([^;\s]+).*?cc_entrypoint=([^;\s]+).*?cch=([a-f0-9]{5})"
)
_SAFE_REQUEST_HEADER_VALUES = {
    "accept",
    "accept-encoding",
    "content-type",
    "user-agent",
    "x-stainless-package-version",
    "x-stainless-runtime",
    "x-stainless-runtime-version",
    "x-stainless-timeout",
    "anthropic-beta",
    "anthropic-version",
    "anthropic-dangerous-direct-browser-access",
    "anthropic-client-platform",
    "x-app",
    "x-service-name",
}
_SAFE_RESPONSE_HEADER_VALUES = {
    "content-type",
    "content-encoding",
    "transfer-encoding",
}


@dataclass(frozen=True)
class _Sample:
    """描述一份本地原始抓包及其已知运行元数据。"""

    run_id: str
    version: str
    declared_model: str
    terminal_status: str
    path: Path


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _path_only(value: str | None) -> str:
    return (value or "").split("?", 1)[0]


def _normalized_path(value: str | None) -> str:
    path = _path_only(value)
    path = re.sub(r"(/v1/code/sessions/)[^/]+", r"\1{id}", path)
    path = re.sub(r"(/v1/sessions/)[^/]+", r"\1{id}", path)
    path = re.sub(r"^/api/eval/[^/]+$", "/api/eval/{id}", path)
    return path


def _request(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("request")
    return value if isinstance(value, dict) else {}


def _response(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("response")
    return value if isinstance(value, dict) else {}


def _headers(container: dict[str, Any]) -> dict[str, str]:
    value = container.get("headers")
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _header_get(headers: dict[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return ""


def _safe_headers(headers: dict[str, str], allowed: set[str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() in allowed}


def _body_bytes(container: dict[str, Any]) -> bytes:
    text = container.get("body_text")
    if isinstance(text, str):
        return text.encode("utf-8")
    encoded = container.get("body_base64")
    if isinstance(encoded, str):
        try:
            return base64.b64decode(encoded)
        except Exception:
            return b""
    return b""


def _body_json(
    container: dict[str, Any], headers: dict[str, str]
) -> dict[str, Any] | None:
    data = _body_bytes(container)
    if not data:
        return None
    if _header_get(headers, "content-encoding").lower() == "gzip":
        try:
            data = gzip.decompress(data)
        except Exception:
            return None
    try:
        value = json.loads(data.decode("utf-8", errors="replace"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _extract_billing(body: dict[str, Any] | None) -> dict[str, str] | None:
    if not body:
        return None
    system = body.get("system")
    if not isinstance(system, list):
        return None
    for item in system:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        match = _BILLING_RE.search(item["text"])
        if match:
            return {
                "cc_version": match.group(1),
                "cc_entrypoint": match.group(2),
                "cch": match.group(3),
            }
    return None


def _first_user_text(body: dict[str, Any]) -> str:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for item in reversed(content):
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    return item["text"]
    return ""


def _javascript_index_chars(text: str, positions: tuple[int, ...]) -> str:
    encoded = text.encode("utf-16-le", errors="surrogatepass")
    picked: list[str] = []
    for position in positions:
        offset = position * 2
        if offset + 2 > len(encoded):
            picked.append("0")
            continue
        code_unit = int.from_bytes(encoded[offset : offset + 2], "little")
        if 0xD800 <= code_unit <= 0xDFFF:
            picked.append("\ufffd")
        else:
            picked.append(chr(code_unit))
    return "".join(picked)


def _cc_version_suffix(text: str, version: str) -> str:
    picked = _javascript_index_chars(text, (4, 7, 20))
    value = f"59cf53e54c78{picked}{version}".encode()
    return hashlib.sha256(value).hexdigest()[:3]


def _scan_json_string_end(body: bytes, start: int) -> int | None:
    if start >= len(body) or body[start] != ord('"'):
        return None
    escaped = False
    index = start + 1
    while index < len(body):
        byte = body[index]
        if escaped:
            escaped = False
        elif byte == ord("\\"):
            escaped = True
        elif byte == ord('"'):
            return index + 1
        index += 1
    return None


def _scan_json_value_end(body: bytes, start: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    index = start
    while index < len(body):
        byte = body[index]
        if in_string:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                in_string = False
            index += 1
            continue
        if byte == ord('"'):
            in_string = True
        elif byte in (ord("{"), ord("[")):
            depth += 1
        elif byte in (ord("}"), ord("]")):
            if depth == 0:
                return index
            depth -= 1
        elif byte == ord(",") and depth == 0:
            return index
        index += 1
    return index


def _skip_json_whitespace(body: bytes, index: int) -> int:
    while index < len(body) and body[index] in b" \n\r\t":
        index += 1
    return index


def _find_top_level_field(body: bytes, field: str) -> tuple[int, int, int] | None:
    index = _skip_json_whitespace(body, 0)
    if index >= len(body) or body[index] != ord("{"):
        return None
    index += 1
    while True:
        index = _skip_json_whitespace(body, index)
        if index >= len(body) or body[index] == ord("}"):
            return None
        if body[index] == ord(","):
            index += 1
            continue
        key_start = index
        key_end = _scan_json_string_end(body, key_start)
        if key_end is None:
            return None
        try:
            key = json.loads(body[key_start:key_end].decode())
        except Exception:
            return None
        index = _skip_json_whitespace(body, key_end)
        if index >= len(body) or body[index] != ord(":"):
            return None
        value_start = _skip_json_whitespace(body, index + 1)
        value_end = _scan_json_value_end(body, value_start)
        if value_end is None:
            return None
        if key == field:
            return key_start, value_start, value_end
        index = _skip_json_whitespace(body, value_end)


def _replace_top_level_value(body: bytes, field: str, replacement: bytes) -> bytes:
    found = _find_top_level_field(body, field)
    if found is None:
        return body
    _, value_start, value_end = found
    return body[:value_start] + replacement + body[value_end:]


def _remove_top_level_field(body: bytes, field: str) -> bytes:
    found = _find_top_level_field(body, field)
    if found is None:
        return body
    key_start, _, value_end = found
    start = key_start
    end = value_end
    next_index = _skip_json_whitespace(body, end)
    if next_index < len(body) and body[next_index] == ord(","):
        end = next_index + 1
    else:
        previous = start
        while previous > 0 and body[previous - 1] in b" \n\r\t":
            previous -= 1
        if previous > 0 and body[previous - 1] == ord(","):
            start = previous - 1
    return body[:start] + body[end:]


def _normalized_cch_input(body: bytes, drop_fallbacks: bool) -> bytes:
    normalized = _CCH_RE.sub(b"cch=00000", body, count=1)
    normalized = _replace_top_level_value(normalized, "model", b'""')
    normalized = _remove_top_level_field(normalized, "max_tokens")
    if drop_fallbacks:
        normalized = _remove_top_level_field(normalized, "fallbacks")
    return normalized


def _compute_cch(body: bytes, mode: str) -> str:
    if mode == "full":
        normalized = _CCH_RE.sub(b"cch=00000", body, count=1)
    elif mode == "model_max_keep_fallbacks":
        normalized = _normalized_cch_input(body, drop_fallbacks=False)
    elif mode == "model_max_drop_fallbacks":
        normalized = _normalized_cch_input(body, drop_fallbacks=True)
    else:
        raise ValueError(f"未知 CCH 模式: {mode}")
    digest = xxhash.xxh64(normalized, seed=_SEED_2156).intdigest()
    return f"{digest & 0xFFFFF:05x}"


def _contains_title_schema(value: Any) -> bool:
    if isinstance(value, dict):
        required = value.get("required")
        properties = value.get("properties")
        if (
            required == ["title"]
            and isinstance(properties, dict)
            and "title" in properties
        ):
            return True
        return any(_contains_title_schema(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_title_schema(item) for item in value)
    return False


def _request_type(body: dict[str, Any], headers: dict[str, str]) -> str:
    model = str(body.get("model") or "")
    tools = body.get("tools")
    max_tokens = body.get("max_tokens")
    stream = body.get("stream") is True
    thinking = body.get("thinking")
    app = _header_get(headers, "x-app")
    tools_empty = tools is None or (isinstance(tools, list) and not tools)
    if app == "cli-bg":
        return "cli_bg"
    if "haiku" in model and tools_empty and max_tokens == 1 and not stream:
        return "haiku_probe"
    if (
        "haiku" in model
        and tools_empty
        and max_tokens == 32000
        and stream
        and isinstance(thinking, dict)
        and thinking.get("type") == "disabled"
        and _contains_title_schema(body.get("output_config"))
    ):
        return "haiku_title"
    if "haiku" in model and tools_empty and max_tokens == 1024 and not stream:
        return "haiku_non_stream_aux"
    if "haiku" in model:
        return "haiku_main"
    return "main"


def _safe_shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_shape(item) for item in value]
    if value is None:
        return "null"
    return type(value).__name__


def _message_structure(body: dict[str, Any]) -> str:
    messages = body.get("messages")
    if not isinstance(messages, list):
        return "messages=0"
    roles: Counter[str] = Counter()
    content_types: Counter[str] = Counter()
    for message in messages:
        if not isinstance(message, dict):
            continue
        roles[str(message.get("role") or "<none>")] += 1
        content = message.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    content_types[str(item.get("type") or "<none>")] += 1
        elif isinstance(content, str):
            content_types["text_string"] += 1
    role_text = ",".join(f"{key}:{value}" for key, value in sorted(roles.items()))
    type_text = ",".join(
        f"{key}:{value}" for key, value in sorted(content_types.items())
    )
    return f"messages={len(messages)};roles={role_text};blocks={type_text}"


def _response_shape(record: dict[str, Any]) -> str:
    response = _response(record)
    status = response.get("status_code")
    if status is None:
        status = response.get("status")
    headers = _headers(response)
    body = _body_bytes(response)
    content_type = _header_get(headers, "content-type").split(";", 1)[0]
    if not body:
        size_bucket = "zero"
    elif len(body) < 2_000:
        size_bucket = "lt_2k"
    elif len(body) < 16_000:
        size_bucket = "2k_16k"
    elif len(body) < 64_000:
        size_bucket = "16k_64k"
    else:
        size_bucket = "gte_64k"
    message_stop = b"event: message_stop" in body or b'"type":"message_stop"' in body
    return (
        f"status={status};content_type={content_type};bytes={size_bucket};"
        f"message_stop={str(message_stop).lower()}"
    )


def _collect_messages(records: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = defaultdict(
        lambda: {
            "count": 0,
            "betas": Counter(),
            "header_orders": Counter(),
            "safe_headers": defaultdict(Counter),
            "body_orders": Counter(),
            "max_tokens": Counter(),
            "fallbacks": Counter(),
            "thinking": Counter(),
            "thinking_orders": Counter(),
            "context_management": Counter(),
            "output_config_effort": Counter(),
            "tools_count": Counter(),
            "system_count": Counter(),
            "output_config_shapes": Counter(),
            "diagnostics_shapes": Counter(),
            "message_structures": Counter(),
            "response_shapes": Counter(),
            "cc_version_checked": 0,
            "cc_version_matched": 0,
            "cch_checked": 0,
            "cch_full": 0,
            "cch_keep_fallbacks": 0,
            "cch_drop_fallbacks": 0,
        }
    )
    for record in records:
        request = _request(record)
        if _path_only(request.get("path")) != "/v1/messages":
            continue
        headers = _headers(request)
        body = _body_json(request, headers)
        if body is None:
            continue
        model = str(body.get("model") or "<none>")
        request_type = _request_type(body, headers)
        key = f"{model}|{request_type}"
        item = aggregate[key]
        item["count"] += 1
        item["header_orders"][tuple(headers.keys())] += 1
        for name, value in _safe_headers(headers, _SAFE_REQUEST_HEADER_VALUES).items():
            item["safe_headers"][name][value] += 1
        beta = _header_get(headers, "anthropic-beta")
        if beta:
            item["betas"][beta] += 1
        item["body_orders"][tuple(body.keys())] += 1
        item["max_tokens"][json.dumps(body.get("max_tokens"), ensure_ascii=True)] += 1
        item["fallbacks"][
            json.dumps(body.get("fallbacks"), ensure_ascii=True, sort_keys=True)
        ] += 1
        thinking = body.get("thinking")
        safe_thinking = (
            thinking if isinstance(thinking, dict) else _safe_shape(thinking)
        )
        item["thinking"][
            json.dumps(safe_thinking, ensure_ascii=True, sort_keys=True)
        ] += 1
        if isinstance(thinking, dict):
            item["thinking_orders"][tuple(thinking.keys())] += 1
        item["context_management"][
            json.dumps(
                body.get("context_management"), ensure_ascii=True, sort_keys=True
            )
        ] += 1
        output_config = body.get("output_config")
        effort = (
            output_config.get("effort") if isinstance(output_config, dict) else None
        )
        item["output_config_effort"][json.dumps(effort, ensure_ascii=True)] += 1
        tools = body.get("tools")
        item["tools_count"][str(len(tools) if isinstance(tools, list) else 0)] += 1
        system = body.get("system")
        item["system_count"][str(len(system) if isinstance(system, list) else 0)] += 1
        item["output_config_shapes"][
            json.dumps(_safe_shape(body.get("output_config")), sort_keys=True)
        ] += 1
        item["diagnostics_shapes"][
            json.dumps(_safe_shape(body.get("diagnostics")), sort_keys=True)
        ] += 1
        item["message_structures"][_message_structure(body)] += 1
        item["response_shapes"][_response_shape(record)] += 1

        billing = _extract_billing(body)
        if billing is None:
            continue
        version, suffix = billing["cc_version"].rsplit(".", 1)
        item["cc_version_checked"] += 1
        if _cc_version_suffix(_first_user_text(body), version) == suffix:
            item["cc_version_matched"] += 1
        raw_body = _body_bytes(request)
        item["cch_checked"] += 1
        if _compute_cch(raw_body, "full") == billing["cch"]:
            item["cch_full"] += 1
        if _compute_cch(raw_body, "model_max_keep_fallbacks") == billing["cch"]:
            item["cch_keep_fallbacks"] += 1
        if _compute_cch(raw_body, "model_max_drop_fallbacks") == billing["cch"]:
            item["cch_drop_fallbacks"] += 1

    result: dict[str, Any] = {}
    for key, item in sorted(aggregate.items()):
        result[key] = {
            "count": item["count"],
            "betas": dict(item["betas"]),
            "header_orders": [
                {"count": count, "keys": list(keys)}
                for keys, count in item["header_orders"].most_common()
            ],
            "safe_headers": {
                name: dict(values) for name, values in item["safe_headers"].items()
            },
            "body_orders": [
                {"count": count, "keys": list(keys)}
                for keys, count in item["body_orders"].most_common()
            ],
            "max_tokens": dict(item["max_tokens"]),
            "fallbacks": dict(item["fallbacks"]),
            "thinking": dict(item["thinking"]),
            "thinking_orders": [
                {"count": count, "keys": list(keys)}
                for keys, count in item["thinking_orders"].most_common()
            ],
            "context_management": dict(item["context_management"]),
            "output_config_effort": dict(item["output_config_effort"]),
            "tools_count": dict(item["tools_count"]),
            "system_count": dict(item["system_count"]),
            "output_config_shapes": dict(item["output_config_shapes"]),
            "diagnostics_shapes": dict(item["diagnostics_shapes"]),
            "message_structures": dict(item["message_structures"]),
            "response_shapes": dict(item["response_shapes"]),
            "cc_version": {
                "checked": item["cc_version_checked"],
                "matched": item["cc_version_matched"],
            },
            "cch": {
                "checked": item["cch_checked"],
                "full": item["cch_full"],
                "model_max_keep_fallbacks": item["cch_keep_fallbacks"],
                "model_max_drop_fallbacks": item["cch_drop_fallbacks"],
            },
        }
    return result


def _decode_metadata(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        decoded = base64.b64decode(value).decode("utf-8", errors="replace")
        result = json.loads(decoded)
    except Exception:
        return None
    return result if isinstance(result, dict) else None


def _collect_telemetry(records: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate: dict[str, Counter[str]] = defaultdict(Counter)
    body_orders: Counter[tuple[str, ...]] = Counter()
    event_data_orders: Counter[tuple[str, ...]] = Counter()
    metadata_shapes: Counter[str] = Counter()
    count = 0
    for record in records:
        request = _request(record)
        if _path_only(request.get("path")) != "/api/event_logging/v2/batch":
            continue
        count += 1
        headers = _headers(request)
        body = _body_json(request, headers)
        if body is None:
            continue
        body_orders[tuple(body.keys())] += 1
        events = body.get("events")
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            data = event.get("event_data")
            if not isinstance(data, dict):
                continue
            event_data_orders[tuple(data.keys())] += 1
            for field in ("event_name", "model", "betas", "entrypoint", "client_type"):
                value = data.get(field)
                if isinstance(value, str):
                    aggregate[field][value] += 1
            env = data.get("env")
            if isinstance(env, dict):
                for field in ("version", "version_base", "build_time", "node_version"):
                    value = env.get(field)
                    if isinstance(value, str):
                        aggregate[f"env.{field}"][value] += 1
            metadata = _decode_metadata(data.get("additional_metadata"))
            if metadata is not None:
                metadata_shapes[json.dumps(_safe_shape(metadata), sort_keys=True)] += 1
                for field in ("preNormalizedModel", "flags", "cli_flag"):
                    value = metadata.get(field)
                    if isinstance(value, str):
                        aggregate[f"metadata.{field}"][value] += 1
    return {
        "request_count": count,
        "values": {key: dict(values) for key, values in aggregate.items()},
        "body_orders": [
            {"count": count, "keys": list(keys)}
            for keys, count in body_orders.most_common()
        ],
        "event_data_orders": [
            {"count": count, "keys": list(keys)}
            for keys, count in event_data_orders.most_common(10)
        ],
        "additional_metadata_shapes": dict(metadata_shapes.most_common(10)),
    }


def _collect_bootstrap(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for record in records:
        request = _request(record)
        if _path_only(request.get("path")) != "/api/claude_cli/bootstrap":
            continue
        request_headers = _headers(request)
        response = _response(record)
        response_headers = _headers(response)
        body = _body_json(response, response_headers) or {}
        options: list[str] = []
        raw_options = body.get("additional_model_options")
        if isinstance(raw_options, list):
            for option in raw_options:
                if isinstance(option, str):
                    options.append(option)
                elif isinstance(option, dict) and isinstance(option.get("model"), str):
                    options.append(option["model"])
        client_data = body.get("client_data")
        cedar_basin = None
        cedar_lagoon_shape: Any = "null"
        if isinstance(client_data, dict):
            cedar_basin = client_data.get("cedar_basin")
            cedar_lagoon_shape = _safe_shape(client_data.get("cedar_lagoon"))
        result.append(
            {
                "path": request.get("path"),
                "request_headers": _safe_headers(
                    request_headers, _SAFE_REQUEST_HEADER_VALUES
                ),
                "response_headers": _safe_headers(
                    response_headers, _SAFE_RESPONSE_HEADER_VALUES
                ),
                "response_status": response.get("status_code", response.get("status")),
                "response_body_bytes": len(_body_bytes(response)),
                "response_keys": list(body.keys()),
                "additional_model_options": options,
                "cwk_cfg_key": body.get("cwk_cfg_key"),
                "cedar_basin": cedar_basin,
                "cedar_lagoon_shape": cedar_lagoon_shape,
            }
        )
    return result


def _collect_endpoint_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str, str, str]] = Counter()
    for record in records:
        request = _request(record)
        response = _response(record)
        status = response.get("status_code", response.get("status"))
        key = (
            str(request.get("method") or ""),
            str(request.get("host") or ""),
            _normalized_path(request.get("path")),
            str(status),
        )
        counter[key] += 1
    return [
        {
            "count": count,
            "method": key[0],
            "host": key[1],
            "path": key[2],
            "status": key[3],
        }
        for key, count in counter.most_common()
    ]


def _collect_wire(sample_path: Path) -> dict[str, Any]:
    flow_files = sorted(sample_path.glob("*.flow"))
    if not flow_files:
        return {}
    aggregate: dict[str, Any] = defaultdict(
        lambda: {
            "orders": Counter(),
            "http_versions": Counter(),
            "statuses": Counter(),
            "safe_headers": defaultdict(Counter),
        }
    )
    with flow_files[0].open("rb") as handle:
        for flow in io.FlowReader(handle).stream():
            if not isinstance(flow, http.HTTPFlow):
                continue
            host = (flow.request.pretty_host or flow.request.host or "").lower()
            if "anthropic" not in host:
                continue
            path = _normalized_path(flow.request.path)
            item = aggregate[path]
            order: list[str] = []
            for raw_key, raw_value in flow.request.headers.fields:
                key = (
                    raw_key.decode("latin1")
                    if isinstance(raw_key, bytes)
                    else str(raw_key)
                )
                value = (
                    raw_value.decode("latin1")
                    if isinstance(raw_value, bytes)
                    else str(raw_value)
                )
                order.append(key)
                if key.lower() in _SAFE_REQUEST_HEADER_VALUES:
                    item["safe_headers"][key][value] += 1
            item["orders"][tuple(order)] += 1
            item["http_versions"][flow.request.http_version] += 1
            status = flow.response.status_code if flow.response else None
            item["statuses"][str(status)] += 1
    result: dict[str, Any] = {}
    for path, item in sorted(aggregate.items()):
        result[path] = {
            "orders": [
                {"count": count, "keys": list(keys)}
                for keys, count in item["orders"].most_common()
            ],
            "http_versions": dict(item["http_versions"]),
            "statuses": dict(item["statuses"]),
            "safe_headers": {
                key: dict(values) for key, values in item["safe_headers"].items()
            },
        }
    return result


def _collect_flow_reconciliation(
    sample_path: Path,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    indexed_requests: Counter[tuple[str, str, str]] = Counter()
    for record in records:
        request = _request(record)
        fingerprint = (
            str(request.get("method") or ""),
            str(request.get("path") or ""),
            hashlib.sha256(_body_bytes(request)).hexdigest(),
        )
        indexed_requests[fingerprint] += 1

    flow_files = sorted(sample_path.glob("*.flow"))
    if not flow_files:
        return {
            "raw_anthropic_flow_count": None,
            "structured_record_count": len(records),
            "raw_only_flow_count": None,
            "structured_only_record_count": None,
            "raw_only_by_endpoint": [],
            "raw_only_messages": [],
        }
    raw_flow_count = 0
    raw_only_by_endpoint: dict[tuple[str, str, str], dict[str, Any]] = {}
    message_groups: dict[str, dict[str, Any]] = {}
    with flow_files[0].open("rb") as handle:
        for flow in io.FlowReader(handle).stream():
            if not isinstance(flow, http.HTTPFlow):
                continue
            host = (flow.request.pretty_host or flow.request.host or "").lower()
            if "anthropic" not in host:
                continue
            raw_body = flow.request.raw_content or b""
            digest = hashlib.sha256(raw_body).hexdigest()
            fingerprint = (flow.request.method, flow.request.path, digest)
            raw_flow_count += 1
            if indexed_requests[fingerprint] > 0:
                indexed_requests[fingerprint] -= 1
                continue

            path = _normalized_path(flow.request.path)
            if path == "/v1/messages":
                category = "messages"
            elif path.endswith("/events/stream"):
                category = "background_stream"
            else:
                category = "background_request"
            endpoint_key = (flow.request.method, path, category)
            endpoint = raw_only_by_endpoint.setdefault(
                endpoint_key,
                {
                    "method": flow.request.method,
                    "path": path,
                    "category": category,
                    "count": 0,
                    "statuses": Counter(),
                    "response_body": Counter(),
                    "flow_errors": 0,
                },
            )
            response_body = (flow.response.raw_content or b"") if flow.response else b""
            status = flow.response.status_code if flow.response else None
            endpoint["count"] += 1
            endpoint["statuses"][str(status)] += 1
            endpoint["response_body"]["zero" if not response_body else "nonzero"] += 1
            endpoint["flow_errors"] += int(flow.error is not None)

            if path != "/v1/messages":
                continue
            try:
                body = json.loads(raw_body)
            except Exception:
                continue
            if not isinstance(body, dict):
                continue
            headers = {
                str(key): str(value) for key, value in flow.request.headers.items()
            }
            model = str(body.get("model") or "<none>")
            key = f"{model}|{_request_type(body, headers)}|{digest}"
            item = message_groups.setdefault(
                key,
                {
                    "model": model,
                    "request_type": _request_type(body, headers),
                    "count": 0,
                    "message_counts": Counter(),
                    "statuses": Counter(),
                    "response_body_bytes": Counter(),
                    "message_stop": Counter(),
                    "headers_wait_sec": [],
                    "request_ids": set(),
                    "starts": [],
                    "flow_errors": 0,
                    "cc_version_checked": 0,
                    "cc_version_matched": 0,
                    "cch_checked": 0,
                    "cch_keep_fallbacks": 0,
                    "cch_drop_fallbacks": 0,
                },
            )
            item["count"] += 1
            messages = body.get("messages")
            item["message_counts"][
                str(len(messages) if isinstance(messages, list) else 0)
            ] += 1
            item["statuses"][str(status)] += 1
            item["response_body_bytes"][str(len(response_body))] += 1
            item["message_stop"][
                str(
                    b"event: message_stop" in response_body
                    or b'"type":"message_stop"' in response_body
                ).lower()
            ] += 1
            if flow.response and flow.response.timestamp_start:
                item["headers_wait_sec"].append(
                    flow.response.timestamp_start - flow.request.timestamp_start
                )
            if flow.response:
                request_id = flow.response.headers.get(
                    "request-id"
                ) or flow.response.headers.get("x-request-id")
                if request_id:
                    item["request_ids"].add(
                        hashlib.sha256(request_id.encode()).hexdigest()
                    )
            item["starts"].append(flow.request.timestamp_start)
            item["flow_errors"] += int(flow.error is not None)

            billing = _extract_billing(body)
            if billing is None:
                continue
            version, suffix = billing["cc_version"].rsplit(".", 1)
            item["cc_version_checked"] += 1
            if _cc_version_suffix(_first_user_text(body), version) == suffix:
                item["cc_version_matched"] += 1
            item["cch_checked"] += 1
            if _compute_cch(raw_body, "model_max_keep_fallbacks") == billing["cch"]:
                item["cch_keep_fallbacks"] += 1
            if _compute_cch(raw_body, "model_max_drop_fallbacks") == billing["cch"]:
                item["cch_drop_fallbacks"] += 1

    raw_only_messages: list[dict[str, Any]] = []
    for item in message_groups.values():
        starts = sorted(item["starts"])
        gaps = [
            round(starts[index] - starts[index - 1], 3)
            for index in range(1, len(starts))
        ]
        waits = item["headers_wait_sec"]
        raw_only_messages.append(
            {
                "model": item["model"],
                "request_type": item["request_type"],
                "same_body_attempts": item["count"],
                "message_counts": dict(item["message_counts"]),
                "statuses": dict(item["statuses"]),
                "response_body_bytes": dict(item["response_body_bytes"]),
                "message_stop": dict(item["message_stop"]),
                "headers_wait_sec": {
                    "min": round(min(waits), 3) if waits else None,
                    "max": round(max(waits), 3) if waits else None,
                },
                "retry_start_gaps_sec": gaps,
                "distinct_request_ids": len(item["request_ids"]),
                "flow_errors": item["flow_errors"],
                "cc_version": {
                    "checked": item["cc_version_checked"],
                    "matched": item["cc_version_matched"],
                },
                "cch": {
                    "checked": item["cch_checked"],
                    "model_max_keep_fallbacks": item["cch_keep_fallbacks"],
                    "model_max_drop_fallbacks": item["cch_drop_fallbacks"],
                },
            }
        )
    endpoint_result = [
        {
            "method": item["method"],
            "path": item["path"],
            "category": item["category"],
            "count": item["count"],
            "statuses": dict(item["statuses"]),
            "response_body": dict(item["response_body"]),
            "flow_errors": item["flow_errors"],
        }
        for item in raw_only_by_endpoint.values()
    ]
    return {
        "raw_anthropic_flow_count": raw_flow_count,
        "structured_record_count": len(records),
        "raw_only_flow_count": sum(item["count"] for item in endpoint_result),
        "structured_only_record_count": sum(indexed_requests.values()),
        "raw_only_by_endpoint": sorted(
            endpoint_result,
            key=lambda item: (item["category"], item["method"], item["path"]),
        ),
        "raw_only_messages": sorted(
            raw_only_messages,
            key=lambda item: (item["model"], item["request_type"]),
        ),
    }


def _summarize_sample(sample: _Sample) -> dict[str, Any]:
    records = _load_jsonl(sample.path / "http_capture.jsonl")
    index_path = sample.path / "capture_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    flow_reconciliation = _collect_flow_reconciliation(sample.path, records)
    return {
        "run_id": sample.run_id,
        "version": sample.version,
        "declared_model": sample.declared_model,
        "terminal_status": sample.terminal_status,
        "files": {
            child.name: child.stat().st_size
            for child in sorted(sample.path.iterdir())
            if child.is_file()
        },
        "index_total_flows": index.get("total_flows"),
        "index_entry_count": len(index.get("entries") or []),
        "record_count": len(records),
        "endpoints": _collect_endpoint_summary(records),
        "messages": _collect_messages(records),
        "telemetry": _collect_telemetry(records),
        "bootstrap": _collect_bootstrap(records),
        "wire": _collect_wire(sample.path),
        "flow_reconciliation": flow_reconciliation,
    }


def main() -> None:
    """读取固定样本矩阵并写入脱敏 JSON 摘要。

    :return: 无返回值，分析结果写入 ``--out`` 指定路径。
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    samples = [
        _Sample(
            "0c3beffc2f35",
            "2.1.257",
            "opus[1m]",
            "success",
            Path("data/evidence/claude-code-2.1.257/0c3beffc2f35"),
        ),
        _Sample(
            "2b9aeab66d11",
            "2.1.257",
            "claude-fable-5",
            "success",
            Path("data/evidence/claude-code-2.1.257/2b9aeab66d11"),
        ),
        _Sample(
            "9333aa5d1fe3",
            "2.1.257",
            "claude-fable-5-1",
            "success",
            Path("data/flows/7-24/9591/9333aa5d1fe3"),
        ),
        _Sample(
            "ea6d8e9bb665",
            "2.1.257",
            "haiku",
            "success",
            Path("data/flows/7-12/9600/ea6d8e9bb665"),
        ),
        _Sample(
            "12a15859fced",
            "2.1.260",
            "opus[1m]",
            "success",
            Path("data/evidence/claude-code-2.1.260/12a15859fced"),
        ),
        _Sample(
            "1349e36bdf19",
            "2.1.260",
            "sonnet",
            "stopped",
            Path("data/evidence/claude-code-2.1.260/1349e36bdf19"),
        ),
        _Sample(
            "8b6129adc9fa",
            "2.1.260",
            "claude-fable-5-1",
            "success",
            Path("data/evidence/claude-code-2.1.260/8b6129adc9fa"),
        ),
        _Sample(
            "aed307de9913",
            "2.1.260",
            "claude-fable-5-1",
            "success",
            Path("data/evidence/claude-code-2.1.260/aed307de9913"),
        ),
        _Sample(
            "2c2117af211c",
            "2.1.260",
            "haiku",
            "success",
            Path("data/evidence/claude-code-2.1.260/2c2117af211c"),
        ),
    ]
    output = {"samples": [_summarize_sample(sample) for sample in samples]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
