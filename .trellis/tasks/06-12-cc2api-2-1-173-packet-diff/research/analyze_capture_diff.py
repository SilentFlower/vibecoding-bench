#!/usr/bin/env python3
"""生成 2.1.173 抓包差异的脱敏摘要。"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
import ast
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import xxhash
from mitmproxy import http, io


SEED_2156 = 0x4D659218E32A3268
SEED_LEGACY = 0x6E52736AC806831E
CCH_RE = re.compile(rb"cch=[a-f0-9]{5}")
BILLING_RE = re.compile(r"cc_version=([^;\s]+).*?cc_entrypoint=([^;\s]+).*?cch=([a-f0-9]{5})")
SAFE_HEADER_VALUES = {
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
    "content-encoding",
    "transfer-encoding",
}


@dataclass(frozen=True)
class Sample:
    """单条抓包样本配置。"""

    label: str
    path: Path
    declared_model: str
    group: str


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def path_only(value: str | None) -> str:
    return (value or "").split("?", 1)[0]


def query_map(record: dict[str, Any]) -> dict[str, str]:
    request = record.get("request") or {}
    query_repr = request.get("query") or ""
    # recorder.py 保存的是 MultiDictView[...] 的 repr；失败时退回空字典。
    if query_repr.startswith("MultiDictView[") and query_repr.endswith("]"):
        inner = query_repr.removeprefix("MultiDictView[").removesuffix("]")
        try:
            pairs = ast.literal_eval(inner)
            return {str(k): str(v) for k, v in pairs}
        except Exception:
            return {}
    raw_path = request.get("path") or ""
    if "?" in raw_path:
        return {k: v for k, v in parse_qsl(raw_path.split("?", 1)[1], keep_blank_values=True)}
    return {}


def request_headers(record: dict[str, Any]) -> dict[str, str]:
    headers = ((record.get("request") or {}).get("headers") or {})
    return {str(k): str(v) for k, v in headers.items()}


def response_headers(record: dict[str, Any]) -> dict[str, str]:
    headers = ((record.get("response") or {}).get("headers") or {})
    return {str(k): str(v) for k, v in headers.items()}


def header_get(headers: dict[str, str], name: str) -> str:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return ""


def safe_header_values(headers: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in SAFE_HEADER_VALUES:
            out[key] = value
    return out


def request_body_text(record: dict[str, Any]) -> str:
    request = record.get("request") or {}
    text = request.get("body_text")
    if isinstance(text, str):
        return text
    b64 = request.get("body_base64")
    if isinstance(b64, str):
        try:
            return base64.b64decode(b64).decode("utf-8", errors="replace")
        except Exception:
            return ""
    return ""


def request_body_bytes(record: dict[str, Any]) -> bytes:
    text = request_body_text(record)
    if text:
        return text.encode("utf-8")
    request = record.get("request") or {}
    b64 = request.get("body_base64")
    if isinstance(b64, str):
        try:
            return base64.b64decode(b64)
        except Exception:
            return b""
    return b""


def response_json(record: dict[str, Any]) -> dict[str, Any] | None:
    response = record.get("response") or {}
    text = response.get("body_text")
    if not isinstance(text, str):
        b64 = response.get("body_base64")
        if isinstance(b64, str):
            try:
                data = base64.b64decode(b64)
                if header_get(response_headers(record), "content-encoding").lower() == "gzip":
                    data = gzip.decompress(data)
                text = data.decode("utf-8", errors="replace")
            except Exception:
                return None
    try:
        value = json.loads(text)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def parse_body_json(record: dict[str, Any]) -> dict[str, Any] | None:
    text = request_body_text(record)
    if not text:
        return None
    try:
        value = json.loads(text)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def iter_message_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if path_only((record.get("request") or {}).get("path")) == "/v1/messages"]


def extract_billing(body: dict[str, Any] | None) -> dict[str, str] | None:
    if not body:
        return None
    for item in body.get("system") or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        match = BILLING_RE.search(text)
        if match:
            return {
                "cc_version": match.group(1),
                "cc_entrypoint": match.group(2),
                "cch": match.group(3),
            }
    return None


def first_user_text(body: dict[str, Any] | None) -> str:
    if not body:
        return ""
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


def js_index_chars(text: str, positions: list[int]) -> str:
    units = text.encode("utf-16-le", errors="surrogatepass")
    picked = []
    for pos in positions:
        off = pos * 2
        if off + 2 <= len(units):
            code_unit = int.from_bytes(units[off : off + 2], "little")
            try:
                picked.append(chr(code_unit))
            except ValueError:
                picked.append("\ufffd")
        else:
            picked.append("0")
    return "".join(picked)


def cc_suffix(text: str, version: str) -> str:
    picked = js_index_chars(text, [4, 7, 20])
    digest = hashlib.sha256(f"59cf53e54c78{picked}{version}".encode()).hexdigest()
    return digest[:3]


def cch_seed(version: str) -> int:
    base = ".".join(version.split(".")[:3])
    if base in {"2.1.156", "2.1.169", "2.1.172", "2.1.173"}:
        return SEED_2156
    return SEED_LEGACY


def scan_json_string_end(body: bytes, start: int) -> int | None:
    if start >= len(body) or body[start] != ord('"'):
        return None
    idx = start + 1
    escaped = False
    while idx < len(body):
        byte = body[idx]
        if escaped:
            escaped = False
        elif byte == ord("\\"):
            escaped = True
        elif byte == ord('"'):
            return idx + 1
        idx += 1
    return None


def scan_json_value_end(body: bytes, start: int) -> int | None:
    idx = start
    depth = 0
    in_string = False
    escaped = False
    while idx < len(body):
        byte = body[idx]
        if in_string:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                in_string = False
            idx += 1
            continue
        if byte == ord('"'):
            in_string = True
        elif byte in (ord("{"), ord("[")):
            depth += 1
        elif byte in (ord("}"), ord("]")):
            if depth == 0:
                return idx
            depth -= 1
        elif byte == ord(",") and depth == 0:
            return idx
        idx += 1
    return idx


def skip_ws(body: bytes, idx: int) -> int:
    while idx < len(body) and body[idx] in b" \n\r\t":
        idx += 1
    return idx


def find_top_level_field(body: bytes, field: str) -> tuple[int, int, int] | None:
    idx = skip_ws(body, 0)
    if idx >= len(body) or body[idx] != ord("{"):
        return None
    idx += 1
    while True:
        idx = skip_ws(body, idx)
        if idx >= len(body) or body[idx] == ord("}"):
            return None
        if body[idx] == ord(","):
            idx += 1
            continue
        if body[idx] != ord('"'):
            return None
        key_start = idx
        key_end = scan_json_string_end(body, key_start)
        if key_end is None:
            return None
        try:
            key = json.loads(body[key_start:key_end].decode("utf-8"))
        except Exception:
            return None
        idx = skip_ws(body, key_end)
        if idx >= len(body) or body[idx] != ord(":"):
            return None
        value_start = skip_ws(body, idx + 1)
        value_end = scan_json_value_end(body, value_start)
        if value_end is None:
            return None
        if key == field:
            return key_start, value_start, value_end
        idx = skip_ws(body, value_end)
        if idx < len(body) and body[idx] == ord(","):
            idx += 1


def replace_top_level_string_value(body: bytes, field: str, replacement: bytes) -> bytes:
    found = find_top_level_field(body, field)
    if not found:
        return body
    _, value_start, value_end = found
    return body[:value_start] + replacement + body[value_end:]


def remove_top_level_field(body: bytes, field: str) -> bytes:
    found = find_top_level_field(body, field)
    if not found:
        return body
    key_start, _, value_end = found
    start = key_start
    end = value_end
    next_idx = skip_ws(body, end)
    if next_idx < len(body) and body[next_idx] == ord(","):
        end = next_idx + 1
    else:
        prev = start
        while prev > 0 and body[prev - 1] in b" \n\r\t":
            prev -= 1
        if prev > 0 and body[prev - 1] == ord(","):
            start = prev - 1
    return body[:start] + body[end:]


def normalize_cch_input(body: bytes, mode: str) -> bytes:
    body = CCH_RE.sub(b"cch=00000", body, count=1)
    if mode == "full":
        return body
    body = replace_top_level_string_value(body, "model", b'""')
    body = remove_top_level_field(body, "max_tokens")
    if mode == "model_max_fallbacks":
        body = remove_top_level_field(body, "fallbacks")
    return body


def compute_cch(body: bytes, version: str, mode: str) -> str:
    normalized = normalize_cch_input(body, mode)
    return f"{xxhash.xxh64(normalized, seed=cch_seed(version)).intdigest() & 0xFFFFF:05x}"


def header_order_from_flow(flow_file: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    safe_values: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    http_versions: dict[str, Counter[str]] = defaultdict(Counter)
    statuses: dict[str, Counter[str]] = defaultdict(Counter)
    with flow_file.open("rb") as handle:
        for flow in io.FlowReader(handle).stream():
            if not isinstance(flow, http.HTTPFlow):
                continue
            host = (flow.request.pretty_host or flow.request.host or "").lower()
            if "anthropic" not in host:
                continue
            endpoint = flow.request.path.split("?", 1)[0]
            names: list[str] = []
            for raw_key, raw_value in flow.request.headers.fields:
                key = raw_key.decode("latin1") if isinstance(raw_key, bytes) else str(raw_key)
                value = raw_value.decode("latin1") if isinstance(raw_value, bytes) else str(raw_value)
                names.append(key)
                if key.lower() in SAFE_HEADER_VALUES:
                    safe_values[endpoint][key][value] += 1
            grouped[endpoint][tuple(names)] += 1
            http_versions[endpoint][flow.request.http_version] += 1
            statuses[endpoint][str(flow.response.status_code if flow.response else None)] += 1
    result: dict[str, list[dict[str, Any]]] = {}
    for endpoint, orders in grouped.items():
        result[endpoint] = [
            {
                "count": count,
                "headers": list(headers),
                "http_versions": dict(http_versions[endpoint]),
                "statuses": dict(statuses[endpoint]),
                "safe_values": {
                    name: dict(counter)
                    for name, counter in safe_values[endpoint].items()
                },
            }
            for headers, count in orders.most_common()
        ]
    return result


def flow_file_for(sample_dir: Path) -> Path | None:
    matches = sorted(sample_dir.glob("*.flow"))
    return matches[0] if matches else None


def collect_telemetry(records: list[dict[str, Any]]) -> dict[str, Any]:
    event_names: Counter[str] = Counter()
    env_versions: Counter[str] = Counter()
    env_bases: Counter[str] = Counter()
    build_times: Counter[str] = Counter()
    models: Counter[str] = Counter()
    flags: Counter[str] = Counter()
    betas: Counter[str] = Counter()
    pre_normalized: Counter[str] = Counter()
    endpoints: Counter[str] = Counter()
    header_variants: Counter[tuple[str, ...]] = Counter()
    header_values: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        request = record.get("request") or {}
        path = path_only(request.get("path"))
        if path != "/api/event_logging/v2/batch":
            continue
        endpoints[path] += 1
        headers = request_headers(record)
        header_variants[tuple(headers.keys())] += 1
        for key, value in safe_header_values(headers).items():
            header_values[key][value] += 1
        body = parse_body_json(record)
        for event in (body or {}).get("events") or []:
            if not isinstance(event, dict):
                continue
            data = event.get("event_data")
            if not isinstance(data, dict):
                continue
            name = data.get("event_name") or event.get("event_type")
            if isinstance(name, str):
                event_names[name] += 1
            model = data.get("model")
            if isinstance(model, str):
                models[model] += 1
            beta = data.get("betas")
            if isinstance(beta, str):
                betas[beta] += 1
            env = data.get("env")
            if isinstance(env, dict):
                for key, counter in [
                    ("version", env_versions),
                    ("version_base", env_bases),
                    ("build_time", build_times),
                ]:
                    value = env.get(key)
                    if isinstance(value, str):
                        counter[value] += 1
            metadata = decode_additional_metadata(data.get("additional_metadata"))
            if isinstance(metadata, dict):
                pn = metadata.get("preNormalizedModel")
                if isinstance(pn, str):
                    pre_normalized[pn] += 1
                flag = metadata.get("flags")
                if isinstance(flag, str):
                    flags[flag] += 1
                cli_flag = metadata.get("cli_flag")
                if isinstance(cli_flag, str):
                    flags[f"cli_flag={cli_flag}"] += 1
    return {
        "endpoint_counts": dict(endpoints),
        "header_orders": [{"count": n, "headers": list(h)} for h, n in header_variants.most_common()],
        "safe_header_values": {k: dict(v) for k, v in header_values.items()},
        "event_names_top": dict(event_names.most_common(20)),
        "env_versions": dict(env_versions),
        "env_version_bases": dict(env_bases),
        "build_times": dict(build_times),
        "models": dict(models),
        "pre_normalized_models": dict(pre_normalized),
        "flags": dict(flags),
        "betas": dict(betas.most_common(10)),
    }


def decode_additional_metadata(value: Any) -> dict[str, Any] | None:
    """解码 telemetry additional_metadata，只用于安全字段聚合。"""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        decoded = base64.b64decode(value).decode("utf-8", errors="replace")
        parsed = json.loads(decoded)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def collect_bootstrap(records: list[dict[str, Any]]) -> dict[str, Any]:
    out: list[dict[str, Any]] = []
    for record in records:
        request = record.get("request") or {}
        if path_only(request.get("path")) != "/api/claude_cli/bootstrap":
            continue
        headers = request_headers(record)
        resp_headers = response_headers(record)
        body = response_json(record) or {}
        client_data = body.get("client_data") if isinstance(body, dict) else None
        cedar = None
        if isinstance(client_data, dict):
            cedar = client_data.get("cedar_lagoon")
        options = body.get("additional_model_options") if isinstance(body, dict) else None
        models = []
        if isinstance(options, list):
            for item in options:
                if isinstance(item, dict) and isinstance(item.get("model"), str):
                    models.append(item["model"])
        out.append(
            {
                "query": query_map(record),
                "request_headers": safe_header_values(headers),
                "response_headers": safe_header_values(resp_headers),
                "client_data_cedar_lagoon": cedar,
                "additional_model_options": models,
                "cwk_cfg_key": body.get("cwk_cfg_key") if isinstance(body, dict) else None,
            }
        )
    return {"items": out}


def collect_messages(records: list[dict[str, Any]]) -> dict[str, Any]:
    message_records = iter_message_records(records)
    endpoint_count = len(message_records)
    models: Counter[str] = Counter()
    beta_by_model: dict[str, Counter[str]] = defaultdict(Counter)
    body_key_orders: Counter[tuple[str, ...]] = Counter()
    header_orders: Counter[tuple[str, ...]] = Counter()
    safe_values: dict[str, Counter[str]] = defaultdict(Counter)
    cc_versions: Counter[str] = Counter()
    cc_suffix = {"checked": 0, "matched": 0, "mismatches": Counter()}
    cch = {
        "checked": 0,
        "full": 0,
        "model_max": 0,
        "model_max_fallbacks": 0,
        "by_model": defaultdict(lambda: {"checked": 0, "full": 0, "model_max": 0, "model_max_fallbacks": 0}),
    }
    top_fields: dict[str, Counter[str]] = defaultdict(Counter)
    for record in message_records:
        headers = request_headers(record)
        header_orders[tuple(headers.keys())] += 1
        for key, value in safe_header_values(headers).items():
            safe_values[key][value] += 1
        body = parse_body_json(record)
        if not body:
            continue
        body_key_orders[tuple(body.keys())] += 1
        model = str(body.get("model") or "<none>")
        models[model] += 1
        beta = header_get(headers, "anthropic-beta")
        if beta:
            beta_by_model[model][beta] += 1
        for field in ["max_tokens", "fallbacks", "thinking", "stream"]:
            if field in body:
                value = body[field]
                if field == "fallbacks" and isinstance(value, list):
                    top_fields[field][json.dumps([item.get("model") if isinstance(item, dict) else None for item in value], ensure_ascii=False)] += 1
                elif field == "thinking" and isinstance(value, dict):
                    top_fields[field][json.dumps({k: value.get(k) for k in sorted(value.keys())}, ensure_ascii=False, sort_keys=True)] += 1
                else:
                    top_fields[field][json.dumps(value, ensure_ascii=False, sort_keys=True)] += 1
        billing = extract_billing(body)
        if not billing:
            continue
        version = billing["cc_version"].rsplit(".", 1)[0]
        suffix = billing["cc_version"].rsplit(".", 1)[-1]
        cc_versions[billing["cc_version"]] += 1
        cc_suffix["checked"] += 1
        expected_suffix = cc_suffix_for_body(body, version)
        if expected_suffix == suffix:
            cc_suffix["matched"] += 1
        else:
            cc_suffix["mismatches"][f"{model}:{version}:{suffix}->{expected_suffix}"] += 1
        body_bytes = request_body_bytes(record)
        real_cch = billing["cch"]
        cch["checked"] += 1
        cch["by_model"][model]["checked"] += 1
        for mode, key in [
            ("full", "full"),
            ("model_max", "model_max"),
            ("model_max_fallbacks", "model_max_fallbacks"),
        ]:
            if compute_cch(body_bytes, version, mode) == real_cch:
                cch[key] += 1
                cch["by_model"][model][key] += 1
    return {
        "count": endpoint_count,
        "models": dict(models),
        "header_orders": [{"count": n, "headers": list(h)} for h, n in header_orders.most_common()],
        "safe_header_values": {k: dict(v) for k, v in safe_values.items()},
        "body_key_orders": [{"count": n, "keys": list(k)} for k, n in body_key_orders.most_common()],
        "top_fields": {k: dict(v) for k, v in top_fields.items()},
        "betas_by_model": {k: dict(v) for k, v in beta_by_model.items()},
        "cc_versions": dict(cc_versions),
        "cc_suffix": {
            "checked": cc_suffix["checked"],
            "matched": cc_suffix["matched"],
            "mismatches_top": dict(cc_suffix["mismatches"].most_common(10)),
        },
        "cch": {
            "checked": cch["checked"],
            "full": cch["full"],
            "model_max": cch["model_max"],
            "model_max_fallbacks": cch["model_max_fallbacks"],
            "by_model": dict(cch["by_model"]),
        },
    }


def cc_suffix_for_body(body: dict[str, Any], version: str) -> str:
    return cc_suffix(first_user_text(body), version)


def summarize_sample(sample: Sample) -> dict[str, Any]:
    records = load_jsonl(sample.path / "http_capture.jsonl")
    index_path = sample.path / "capture_index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    flow_path = flow_file_for(sample.path)
    endpoints = Counter(
        f"{(record.get('request') or {}).get('host') or ''} {path_only((record.get('request') or {}).get('path'))}"
        for record in records
    )
    files = {
        child.name: child.stat().st_size
        for child in sorted(sample.path.iterdir())
        if child.is_file()
    }
    wire = header_order_from_flow(flow_path) if flow_path else {}
    return {
        "label": sample.label,
        "group": sample.group,
        "declared_model": sample.declared_model,
        "path": str(sample.path),
        "files": files,
        "index_total_flows": index.get("total_flows"),
        "record_count": len(records),
        "endpoint_counts_top": dict(endpoints.most_common(12)),
        "messages": collect_messages(records),
        "telemetry": collect_telemetry(records),
        "bootstrap": collect_bootstrap(records),
        "wire": {
            endpoint: orders
            for endpoint, orders in wire.items()
            if endpoint in {
                "/v1/messages",
                "/api/event_logging/v2/batch",
                "/api/claude_cli/bootstrap",
                "/api/eval/sdk-zAZezfDKGoZuXXKe",
                "/v1/code/triggers",
                "/v1/mcp_servers",
                "/mcp-registry/v0/servers",
                "/api/oauth/account/settings",
                "/api/claude_code_grove",
                "/api/claude_code_penguin_mode",
                "/",
            }
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("samples", nargs="*")
    args = parser.parse_args()

    default_samples = [
        Sample("3075-172-opus", Path("data/flows/pingguo-1/3075/a773a0d683a6"), "default(opus[1m])", "old"),
        Sample("3078-172-fable", Path("data/flows/pingguo-1/3078/715232eae9e8"), "claude-fable-5", "old"),
        Sample("3085-172-fable-todo", Path("data/flows/pingguo-1/3085/03373b8d8c65"), "claude-fable-5", "old"),
        Sample("3088-172-fable-1m", Path("data/flows/pingguo-1/3088/09383cec8ea7"), "claude-fable-5[1m]", "old"),
        Sample("3125-173-opus", Path("data/flows/pingguo-1/3125/bca74ce4196b"), "default(opus[1m])", "new"),
        Sample("3126-173-fable", Path("data/flows/pingguo-1/3126/6e65bb7cb888"), "claude-fable-5", "new"),
        Sample("3127-173-fable-1m", Path("data/flows/pingguo-1/3127/7445da8ab9af"), "claude-fable-5[1m]", "new"),
    ]
    selected = default_samples
    summary = {"samples": [summarize_sample(sample) for sample in selected]}
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
