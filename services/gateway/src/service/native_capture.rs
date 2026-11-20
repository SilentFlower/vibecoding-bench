//! 保存有界的 CC 组装与网关拒绝快照，预览只通过管理员接口读取。

use std::cmp::Reverse;
use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, OpenOptions};
use std::io::{self, Read, Write};
#[cfg(unix)]
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::sync::{LazyLock, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

#[cfg(unix)]
use libc::{O_NOFOLLOW, O_NONBLOCK};
use regex::Regex;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tokio::sync::Semaphore;
use tokio::task::{JoinHandle, spawn_blocking};
use uuid::Uuid;

use crate::model::request_diagnostics::RequestLogMode;
use crate::service::gemini::BODY_LIMIT as GEMINI_BODY_LIMIT;
use crate::service::native_contract::NativeSubmission;
use axum::body::Bytes;
use axum::http::HeaderMap;

const BODY_LIMIT: usize = 2 * 1024 * 1024;
const INGRESS_PREVIEW_LIMIT: usize = 1024 * 1024;
const SNAPSHOT_LIMIT: usize = 6 * 1024 * 1024;
// 完整入站只存一份正文，为脱敏替换、JSON 字符串转义及请求头预留空间。
const REJECTED_SNAPSHOT_LIMIT: usize = 4 * GEMINI_BODY_LIMIT;
const HEADER_LIMIT: usize = 128 * 1024;
const STORAGE_LIMIT: u64 = 1024 * 1024 * 1024;
const GATEWAY_RETENTION: Duration = Duration::from_secs(7 * 86400);
static WRITERS: Semaphore = Semaphore::const_new(2);
static STORAGE: Mutex<()> = Mutex::new(());

/// 私有缓存诊断仅接受控制枚举、位置和计数。
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct MessageCacheDecision {
    mode: String,
    action: String,
    reason: String,
    selected: Vec<MessageCachePosition>,
    breakpoints: Option<u64>,
    ttl: Option<String>,
}

/// 单个协议消息块的位置。
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct MessageCachePosition {
    message: u32,
    block: u32,
}

/// 校验并投影原生返回的缓存决策，保持诊断有界且无业务文本。
/// @param value 私有事件中的缓存决策。
/// @return 已知合同的安全快照，畸形决策返回None。
pub(crate) fn message_cache_policy(value: &Value) -> Option<Value> {
    if value.as_object()?.len() != 6 || value["selected"].as_array()?.len() > 2 {
        return None;
    }
    let decision: MessageCacheDecision = serde_json::from_value(value.clone()).ok()?;
    if decision.selected.len() > 2 {
        return None;
    }
    let valid = match (
        decision.mode.as_str(),
        decision.action.as_str(),
        decision.reason.as_str(),
    ) {
        ("preserve", "preserved", "policy_preserve") => {
            decision.selected.is_empty() && decision.ttl.is_none()
        }
        ("sub2api", "applied", "sub2api_tail") => {
            !decision.selected.is_empty()
                && decision.breakpoints.is_some_and(|count| count <= 4)
                && matches!(decision.ttl.as_deref(), Some("5m" | "1h"))
        }
        (
            "sub2api",
            "skipped",
            "caller_message_breakpoints"
            | "root_cache_control_present"
            | "unsupported_cache_control"
            | "no_available_slots"
            | "no_cacheable_blocks",
        ) => decision.selected.is_empty() && decision.ttl.is_none(),
        _ => false,
    };
    valid.then(|| serde_json::to_value(decision).ok()).flatten()
}
static TOKEN: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"sk-ant-[A-Za-z0-9_-]+").unwrap());
static SECRET_STRING: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
    r#"(?i)("[^"\\]*(?:authorization|cookie|api[-_]?key|token|password|secret|credential)[^"\\]*"\s*:\s*)"(?:\\.|[^"\\])*""#
).unwrap()
});
static SECRET_SCALAR: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
    r#"(?i)("(?:authorization|cookie|api[-_]?key|access[-_]?token|refresh[-_]?token|password|secret|credential|token)"\s*:\s*)(?:-?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null)"#
).unwrap()
});
static PROXY: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"://[^\s/:]+:[^\s/@]+@").unwrap());

fn sensitive(name: &str) -> bool {
    let name = name.to_ascii_lowercase().replace('-', "_");
    [
        "authorization",
        "cookie",
        "api_key",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "credential",
    ]
    .iter()
    .any(|part| name.contains(part))
        || name == "token"
        || name.ends_with("_token")
}

fn collect(value: &Value, secrets: &mut Vec<String>) {
    match value {
        Value::Object(fields) => {
            for (name, value) in fields {
                if sensitive(name) {
                    if let Some(value) = value.as_str() {
                        add_secret(value, secrets);
                    }
                }
                collect(value, secrets);
            }
        }
        Value::Array(values) => {
            // 原生输入以有序二元组保存请求头；过滤后的出站头已无法补齐这些入站秘密。
            if let [Value::String(name), Value::String(value)] = values.as_slice() {
                if sensitive(name) {
                    add_secret(value, secrets);
                }
            }
            for value in values {
                collect(value, secrets);
            }
        }
        _ => {}
    }
}

fn redact_sensitive_fields(value: &mut Value) {
    match value {
        Value::Object(fields) => {
            for (name, field) in fields {
                if sensitive(name) {
                    *field = json!("[REDACTED]");
                } else {
                    redact_sensitive_fields(field);
                }
            }
        }
        Value::Array(values) => {
            for value in values {
                redact_sensitive_fields(value);
            }
        }
        _ => {}
    }
}

fn add_secret(value: &str, secrets: &mut Vec<String>) {
    if value.len() >= 4 {
        secrets.push(value.to_owned());
    }
    if let Some((scheme, token)) = value.split_once(' ') {
        if scheme.eq_ignore_ascii_case("bearer") && token.len() >= 4 {
            secrets.push(token.to_owned());
        }
    }
}

fn text(value: &str, secrets: &[String]) -> String {
    let mut value = value.to_owned();
    for secret in secrets {
        value = value.replace(secret, "[REDACTED]");
    }
    PROXY
        .replace_all(&TOKEN.replace_all(&value, "[REDACTED]"), "://[REDACTED]@")
        .into_owned()
}

fn prefix(value: &str, limit: usize) -> (&str, bool) {
    let mut end = value.len().min(limit);
    while !value.is_char_boundary(end) {
        end -= 1;
    }
    (&value[..end], end < value.len())
}

/// 对原文进行统一秘密替换，保留键顺序与空白。@param original 原文。@param secrets 已知秘密。@return 脱敏原文。
fn redact_body(original: &str, secrets: &[String]) -> io::Result<String> {
    let escaped: Vec<String> = secrets
        .iter()
        .map(|secret| {
            serde_json::to_string(secret).map(|encoded| encoded[1..encoded.len() - 1].to_owned())
        })
        .collect::<Result<_, _>>()?;
    let body = text(&text(original, &escaped), secrets);
    let body = SECRET_STRING.replace_all(&body, "${1}\"[REDACTED]\"");
    Ok(SECRET_SCALAR
        .replace_all(&body, "${1}\"[REDACTED]\"")
        .into_owned())
}

/// 有界脱敏有序头。@param pairs 原始头。@param secrets 已知秘密。@return 脱敏头与截断标志。
fn redact_headers(pairs: &[(String, String)], secrets: &[String]) -> (Vec<(String, String)>, bool) {
    let mut headers = Vec::new();
    let mut bytes = 0;
    for (name, value) in pairs {
        if name.len() + value.len() > HEADER_LIMIT.saturating_sub(bytes) {
            return (headers, true);
        }
        let name = text(name, secrets);
        let value = if sensitive(&name) {
            "[REDACTED]".into()
        } else {
            text(value, secrets)
        };
        bytes += name.len() + value.len();
        if bytes > HEADER_LIMIT {
            return (headers, true);
        }
        headers.push((name, value));
    }
    (headers, false)
}

/// 在会话映射前冻结有界脱敏入口，info在复制前返回。@param mode 同次模式。@param headers 入站头。@param raw 原始逻辑字节。@param parsed 已解析正文。@param bearer 当前上游秘密。@return 可选入口预览。
pub(crate) fn ingress(
    mode: RequestLogMode,
    headers: &[(String, String)],
    raw: &[u8],
    parsed: &Value,
    bearer: &str,
) -> Option<Value> {
    if mode != RequestLogMode::Debug {
        return None;
    }
    ingress_snapshot(headers, raw, parsed, bearer, false)
}

fn ingress_snapshot(
    headers: &[(String, String)],
    raw: &[u8],
    parsed: &Value,
    bearer: &str,
    full: bool,
) -> Option<Value> {
    let original = std::str::from_utf8(raw).ok()?;
    let mut secrets = vec![bearer.to_owned()];
    collect(parsed, &mut secrets);
    for (name, value) in headers {
        if sensitive(name) {
            add_secret(value, &mut secrets);
        }
    }
    secrets.retain(|secret| secret.len() >= 4);
    secrets.sort_by_key(|secret| Reverse(secret.len()));
    secrets.dedup();
    let (body, representation) = if full && !raw.is_empty() {
        let mut safe = parsed.clone();
        redact_sensitive_fields(&mut safe);
        (
            redact_body(&serde_json::to_string(&safe).ok()?, &secrets).ok()?,
            "redacted_json",
        )
    } else {
        (redact_body(original, &secrets).ok()?, "http_logical_bytes")
    };
    let (body, body_truncated) = if full {
        (body.as_str(), false)
    } else {
        prefix(&body, INGRESS_PREVIEW_LIMIT)
    };
    let (headers, headers_truncated) = redact_headers(headers, &secrets);
    Some(
        json!({"source":"gateway_http_ingress","representation":representation,
        "captured_at_ms":SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis() as u64,
        "headers":headers,"body":body,"body_truncated":body_truncated,"headers_truncated":headers_truncated,
        "original_body_bytes":raw.len(),"original_body_sha256":format!("{:x}",Sha256::digest(raw))}),
    )
}

/// 保存内核实际决策的有界副本。@param decisions 同次决策。@return 明确完整性及数量的快照。
pub(crate) fn header_policy(decisions: &[Value]) -> Value {
    let mut stored = Vec::new();
    let mut bytes = 0;
    for decision in decisions.iter().take(1024) {
        bytes += decision.to_string().len();
        if bytes > HEADER_LIMIT {
            break;
        }
        stored.push(decision.clone());
    }
    json!({"source":"native_header_policy","status":if stored.len()==decisions.len(){"complete"}else{"truncated"},
        "observed_count":decisions.len(),"stored_count":stored.len(),"decisions":stored})
}

/// 仅生成有界字段路径差异，字段值由脱敏阶段原文提供。@param before 入口JSON。@param after 组装JSON。@return 观察差异及完整性。
fn body_changes(before: &Value, after: &Value) -> Value {
    fn visit(
        before: Option<&Value>,
        after: Option<&Value>,
        path: String,
        depth: usize,
        nodes: &mut usize,
        items: &mut Vec<Value>,
        truncated: &mut bool,
    ) {
        if before == after {
            return;
        }
        *nodes += 1;
        if *nodes > 4096 || depth > 16 || items.len() >= 128 || path.len() > 2048 {
            *truncated = true;
            return;
        }
        if let (Some(Value::Object(left)), Some(Value::Object(right))) = (before, after) {
            let keys: BTreeSet<_> = left.keys().chain(right.keys()).collect();
            for key in keys {
                if *nodes > 4096 || items.len() >= 128 {
                    *truncated = true;
                    break;
                }
                let escaped = key.replace('~', "~0").replace('/', "~1");
                visit(
                    left.get(key),
                    right.get(key),
                    format!("{path}/{escaped}"),
                    depth + 1,
                    nodes,
                    items,
                    truncated,
                );
            }
            return;
        }
        if let (Some(Value::Array(left)), Some(Value::Array(right))) = (before, after) {
            if left.len() == right.len() {
                for (index, (left, right)) in left.iter().zip(right).enumerate() {
                    if *nodes > 4096 || items.len() >= 128 {
                        *truncated = true;
                        break;
                    }
                    visit(
                        Some(left),
                        Some(right),
                        format!("{path}/{index}"),
                        depth + 1,
                        nodes,
                        items,
                        truncated,
                    );
                }
                return;
            }
        }
        let action = if before.is_none() {
            "added"
        } else if after.is_none() {
            "removed"
        } else {
            "changed"
        };
        let reason = if action == "removed"
            && matches!(path.as_str(), "/settings" | "/claude_settings" | "/env")
        {
            "调用方根本机设置已清理"
        } else {
            "入口与原生组装结果的实际字段差异"
        };
        items.push(json!({"path":path,"action":action,"reason":reason}));
    }
    let mut items = Vec::new();
    let mut truncated = false;
    visit(
        Some(before),
        Some(after),
        String::new(),
        0,
        &mut 0,
        &mut items,
        &mut truncated,
    );
    json!({"source":"observed_diff","status":if truncated{"truncated"}else{"complete"},"items":items})
}

fn snapshot(submission: &NativeSubmission, payload: &Value) -> io::Result<Value> {
    let rejected = payload["type"] == "error";
    let pairs: Vec<(String, String)> = if rejected {
        Vec::new()
    } else {
        serde_json::from_value(payload["headers"].clone())?
    };
    let body_value: Value = if rejected {
        Value::Null
    } else {
        serde_json::from_str(payload["body"].as_str().ok_or(io::ErrorKind::InvalidData)?)?
    };
    let mut secrets = vec![submission.bearer.clone()];
    collect(&submission.input, &mut secrets);
    collect(&body_value, &mut secrets);
    if let Some(wire) = payload.get("_wire_final").filter(|_| !rejected) {
        collect(&wire["headers"], &mut secrets);
        if let Some(body) = wire["body"]
            .as_str()
            .and_then(|body| serde_json::from_str::<Value>(body).ok())
        {
            collect(&body, &mut secrets);
        }
    }
    for (name, value) in &pairs {
        if sensitive(name) {
            add_secret(value, &mut secrets);
        }
    }
    secrets.retain(|value| value.len() >= 4);
    secrets.sort_by_key(|value| Reverse(value.len()));
    secrets.dedup();
    // 保留组装正文的顺序和空白，仅替换秘密，避免把重新序列化的结果称为原始快照。
    let original = if rejected {
        ""
    } else {
        payload["body"].as_str().ok_or(io::ErrorKind::InvalidData)?
    };
    let redacted = redact_body(original, &secrets)?;
    let (body, truncated) = prefix(&redacted, BODY_LIMIT);
    let (headers, headers_truncated) = redact_headers(&pairs, &secrets);
    let mut value = json!({"schema_version":1,"stage":if rejected {"ingress_rejected"} else {"cc_prepared"}, "account_id":submission.request.account_id,
        "attempt_id":submission.request.request_id,"captured_at_ms":SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis() as u64,
        "headers":headers,"body":body,"body_truncated":truncated,"headers_truncated":headers_truncated,
        "original_body_bytes":if rejected {Value::Null} else {payload["body_bytes"].clone()},"original_body_sha256":if rejected {Value::Null} else {payload["body_sha256"].clone()}});
    if let Some(policy) = payload.get("cache_policy").filter(|_| !rejected) {
        value["cache_policy"] = message_cache_policy(policy).ok_or(io::ErrorKind::InvalidData)?;
    }
    let mut ingress_status = "unavailable";
    if let Some(ingress) = submission.ingress_capture.as_ref() {
        let input = ingress["body"].as_str().ok_or(io::ErrorKind::InvalidData)?;
        let digest = ingress["original_body_sha256"]
            .as_str()
            .ok_or(io::ErrorKind::InvalidData)?;
        if input.len() > 1024 * 1024
            || ingress["captured_at_ms"].as_u64().is_none_or(|at| {
                at == 0
                    || at
                        > value["captured_at_ms"]
                            .as_u64()
                            .unwrap_or(0)
                            .saturating_add(300_000)
            })
            || ingress["original_body_bytes"].as_u64().is_none()
            || digest.len() != 64
            || !digest.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !ingress["body_truncated"].is_boolean()
            || !ingress["headers_truncated"].is_boolean()
            || ingress["headers"]
                .as_array()
                .is_none_or(|pairs| pairs.len() > 4096)
        {
            return Err(io::ErrorKind::InvalidData.into());
        }
        // 只投影定义过的字段，私有报文的额外键也不能成为未脱敏落盘旁路。
        let mut preview = json!({"source":"gateway_http_ingress","representation":"http_logical_bytes",
            "captured_at_ms":ingress["captured_at_ms"],"original_body_bytes":ingress["original_body_bytes"],
            "original_body_sha256":digest});
        let cleaned = redact_body(input, &secrets)?;
        let changes = if !rejected && ingress["body_truncated"] == false {
            serde_json::from_str::<Value>(&cleaned)
                .ok()
                .and_then(|before| {
                    serde_json::from_str::<Value>(&redacted)
                        .ok()
                        .map(|after| body_changes(&before, &after))
                })
        } else {
            None
        };
        let (input, clipped) = prefix(
            &cleaned,
            BODY_LIMIT.saturating_sub(body.len()).min(1024 * 1024),
        );
        preview["body"] = json!(input);
        preview["body_truncated"] = json!(clipped || ingress["body_truncated"] == true);
        let input_headers: Vec<(String, String)> =
            serde_json::from_value(ingress["headers"].clone())?;
        let (pairs, clipped_headers) = redact_headers(&input_headers, &secrets);
        preview["headers"] = json!(pairs);
        preview["headers_truncated"] =
            json!(clipped_headers || ingress["headers_truncated"] == true);
        ingress_status =
            if preview["body_truncated"] == true || preview["headers_truncated"] == true {
                "truncated"
            } else {
                "complete"
            };
        preview["status"] = json!(ingress_status);
        value["ingress"] = preview;
        value["body_changes"] = changes.unwrap_or_else(|| json!({"source":"observed_diff","status":"unavailable","items":[],"note":if rejected {"本次在原生组装前拒绝，仅保存入站证据"} else {"入口预览截断或缺少可解析JSON"}}));
    } else {
        value["body_changes"] = json!({"source":"observed_diff","status":"unavailable","items":[],"note":"本次未采集入口正文"});
    }
    let mut path_truncated = false;
    if let Some(items) = value["body_changes"]["items"].as_array_mut() {
        for item in items {
            if let Some(path) = item["path"].as_str() {
                let cleaned = text(path, &secrets);
                let (bounded, clipped) = prefix(&cleaned, 2048);
                item["path"] = json!(bounded);
                path_truncated |= clipped;
            }
        }
    }
    if path_truncated {
        value["body_changes"]["status"] = json!("truncated");
    }
    let mut policy = payload.get("_header_policy").cloned().unwrap_or_else(|| json!({"source":"native_header_policy","status":"unavailable","decisions":[],"note":"历史或本次头部决策未采集"}));
    let observed_policy = policy["status"] != "unavailable";
    if let Some(decisions) = policy["decisions"]
        .as_array_mut()
        .filter(|_| observed_policy)
    {
        for decision in decisions {
            for field in ["name", "reason"] {
                if let Some(raw) = decision[field].as_str() {
                    decision[field] = json!(text(raw, &secrets));
                }
            }
        }
        // 秘密替换可能增大字符串，落盘前再次应用相同预算，并保留原观察数量。
        let observed = policy["observed_count"].clone();
        let previous_truncated = policy["status"] == "truncated";
        let mut bounded = header_policy(policy["decisions"].as_array().unwrap());
        bounded["observed_count"] = observed;
        if previous_truncated {
            bounded["status"] = json!("truncated");
        }
        policy = bounded;
    }
    value["header_policy"] = policy;
    value["stages"] = json!([
        {"stage":"ingress","source":"gateway_http_ingress","representation":"http_logical_bytes","status":ingress_status,"note":"网关会话映射前的入站逻辑正文"},
        {"stage":"header_policy","source":"native_header_policy","representation":"json","status":value["header_policy"]["status"],"note":"内核实际返回的逐字段处理决策"},
        {"stage":"cc_prepared","source":"native_cc_prepared","representation":"json_before_native_transport","status":if rejected {"unavailable"} else if truncated || headers_truncated {"truncated"} else {"complete"},"note":if rejected {"本次在原生组装前拒绝"} else {"原生最终传输前的中间值"}},
        {"stage":"wire_final","source":"unavailable","representation":"unavailable","status":"unavailable","note":"平台本次未取得独立最终TLS写出采集"}
    ]);
    if let Some(policy) = value.get("cache_policy") {
        let note = format!(
            "原生最终传输前的中间值；消息缓存策略 {} / {}，新增断点 {} 个",
            policy["mode"].as_str().unwrap_or_default(),
            policy["reason"].as_str().unwrap_or_default(),
            policy["selected"].as_array().map_or(0, Vec::len)
        );
        value["stages"][2]["note"] = json!(note);
    }
    if let Some(wire) = payload.get("_wire_final").filter(|_| !rejected) {
        append_wire(&mut value, wire, &secrets)?;
        if wire["complete"] == true && wire["body_truncated"] == false {
            if let Some(after) = wire["body"]
                .as_str()
                .and_then(|body| serde_json::from_str::<Value>(body).ok())
            {
                let mut changes = body_changes(&body_value, &after);
                let mut clipped = false;
                for item in changes["items"].as_array_mut().unwrap() {
                    let cleaned = text(item["path"].as_str().unwrap_or(""), &secrets);
                    let (path, cut) = prefix(&cleaned, 2048);
                    clipped |= cut;
                    item["path"] = json!(path);
                    item["reason"] = json!("原生组装与TLS接受正文的实际字段差异");
                }
                if clipped {
                    changes["status"] = json!("truncated");
                }
                value["final_body_changes"] = changes;
            }
        }
        if wire["complete"] == true {
            let final_pairs: Vec<(String, String)> =
                serde_json::from_value(wire["headers"].clone())?;
            let group = |pairs: &[(String, String)]| {
                let mut fields = BTreeMap::<String, Vec<String>>::new();
                for (name, value) in pairs {
                    fields
                        .entry(name.to_ascii_lowercase())
                        .or_default()
                        .push(value.clone());
                }
                fields
            };
            let before = group(&pairs);
            let after = group(&final_pairs);
            let names: BTreeSet<_> = before.keys().chain(after.keys()).collect();
            let mut items = Vec::new();
            let mut truncated = false;
            let mut bytes = 0;
            for name in names {
                if before.get(name) == after.get(name) {
                    continue;
                }
                let action = if !before.contains_key(name) {
                    "added"
                } else if !after.contains_key(name) {
                    "removed"
                } else {
                    "changed"
                };
                let cleaned = text(name, &secrets);
                let (name, clipped) = prefix(&cleaned, 4096);
                if items.len() >= 128 || bytes + name.len() > HEADER_LIMIT {
                    truncated = true;
                    break;
                }
                bytes += name.len();
                truncated |= clipped;
                items.push(
                    json!({"name":name,"action":action,"reason":"原生组装与TLS接受头的实际差异"}),
                );
            }
            value["final_header_changes"] = json!({"source":"observed_diff","status":if truncated {"truncated"} else {"complete"},"items":items});
        }
    }
    Ok(value)
}

/// 对最终证据做独立白名单投影与共同预算分配。@param value 同次快照。@param wire 私有观测。@param secrets 已登记秘密。@return 归属后的有界快照或类型错误。
fn append_wire(value: &mut Value, wire: &Value, secrets: &[String]) -> io::Result<()> {
    let complete = wire["complete"]
        .as_bool()
        .ok_or(io::ErrorKind::InvalidData)?;
    let status = wire["status"].as_str().ok_or(io::ErrorKind::InvalidData)?;
    let original = wire["body"].as_str().ok_or(io::ErrorKind::InvalidData)?;
    let pairs: Vec<(String, String)> = serde_json::from_value(wire["headers"].clone())?;
    let truncated = wire["body_truncated"]
        .as_bool()
        .ok_or(io::ErrorKind::InvalidData)?;
    let header_truncated = wire["headers_truncated"]
        .as_bool()
        .ok_or(io::ErrorKind::InvalidData)?;
    if wire["source"] != "native_tls_uprobe"
        || wire["representation"] != "http_entity_from_tls_accepted_write"
        || !matches!(status, "complete" | "incomplete" | "unavailable")
        || (status == "complete") != complete
        || (complete && !wire["reason"].is_null())
        || !wire["flushed"].is_null()
        || original.len() > BODY_LIMIT
        || pairs.len() > 4096
        || pairs
            .iter()
            .map(|(name, value)| name.len() + value.len())
            .sum::<usize>()
            > HEADER_LIMIT
    {
        return Err(io::ErrorKind::InvalidData.into());
    }
    if complete {
        let bytes = wire["observed_body_bytes"]
            .as_u64()
            .ok_or(io::ErrorKind::InvalidData)?;
        let hash = wire["body_sha256"]
            .as_str()
            .ok_or(io::ErrorKind::InvalidData)?;
        if bytes < original.len() as u64
            || (!truncated && bytes != original.len() as u64)
            || hash.len() != 64
            || !hash.bytes().all(|byte| byte.is_ascii_hexdigit())
            || (!truncated && hash != format!("{:x}", Sha256::digest(original.as_bytes())))
        {
            return Err(io::ErrorKind::InvalidData.into());
        }
    } else if !wire["observed_body_bytes"].is_null() || !wire["body_sha256"].is_null() {
        return Err(io::ErrorKind::InvalidData.into());
    }
    // 仅连续的HTTP前缀可以截断展示；其余不完整证据清空原文，避免事件缺口绕过整串凭据脱敏。
    let unsafe_preview = !complete && wire["reason"].as_str() != Some("HTTP_PARTIAL");
    let original = if unsafe_preview { "" } else { original };
    let preview_pairs = if unsafe_preview { &[][..] } else { &pairs[..] };
    // 预览在帮助进程内限长。去掉末尾未闭合字符串，防止未知秘密的残片越过脱敏器。
    let mut quote = None;
    let mut escaped = false;
    if truncated || !complete {
        for (index, byte) in original.bytes().enumerate() {
            if escaped {
                escaped = false;
            } else if quote.is_some() && byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                quote = if quote.is_some() { None } else { Some(index) };
            }
        }
    }
    let cleaned = redact_body(&original[..quote.unwrap_or(original.len())], secrets)?;
    let (body, clipped) = prefix(&cleaned, BODY_LIMIT);
    let (headers, headers_clipped) = redact_headers(preview_pairs, secrets);
    let reason = wire["reason"].as_str().filter(|reason| {
        matches!(
            *reason,
            "OBSERVER_NOT_CONFIGURED"
                | "OBSERVER_CONFIGURATION"
                | "OBSERVER_START_FAILED"
                | "OBSERVER_CHANNEL"
                | "OBSERVER_START_TIMEOUT"
                | "OBSERVER_UNAVAILABLE"
                | "OBSERVER_FRAME_INVALID"
                | "OBSERVER_BINDING"
                | "OBSERVER_FINISH_TIMEOUT"
                | "IMAGE_NOT_ADMITTED"
                | "IMAGE_MISMATCH"
                | "WORKER_OWNERSHIP"
                | "WORKER_UNAVAILABLE"
                | "PROBE_ARTIFACT"
                | "BPF_LOAD_FAILED"
                | "RING_UNAVAILABLE"
                | "PROBE_ATTACH_FAILED"
                | "EVENT_INVALID"
                | "EVENT_OWNERSHIP"
                | "EVENT_SEQUENCE"
                | "CONNECTION_LIMIT"
                | "RING_FAILED"
                | "PROBE_DETACH_FAILED"
                | "COUNTS_UNAVAILABLE"
                | "EVENT_LOSS"
                | "REQUEST_AMBIGUOUS"
                | "REQUEST_NOT_OBSERVED"
                | "COMMAND_INVALID"
                | "OBSERVER_FAILED"
                | "CAPTURE_INTERRUPTED"
                | "CAPTURE_PENDING"
                | "CAPTURE_PREPARING"
                | "HTTP_HEADER_LIMIT"
                | "HTTP_UNSUPPORTED"
                | "HTTP_INVALID"
                | "HTTP_LENGTH_UNKNOWN"
                | "HTTP_EXTRA_BYTES"
                | "HTTP_PARTIAL"
                | "BODY_ENCODING"
        )
    });
    let mut final_value = json!({"source":"native_tls_uprobe","representation":"http_entity_from_tls_accepted_write",
        "status":status,"reason":reason.or(if complete { None } else { Some("OBSERVER_FAILED") }),
        "headers":headers,"body":body,"body_truncated":truncated || clipped || quote.is_some() || (unsafe_preview && !wire["body"].as_str().unwrap_or("").is_empty()),
        "headers_truncated":header_truncated || headers_clipped || (unsafe_preview && !pairs.is_empty()),
        "observed_body_bytes":wire["observed_body_bytes"],"body_sha256":wire["body_sha256"],
        "original_body_bytes":wire["observed_body_bytes"],"original_body_sha256":wire["body_sha256"],
        "complete":complete,"flushed":null});
    if let (Some(bytes), Some(hash)) = (
        wire["observed_http_bytes"].as_u64(),
        wire["http_sha256"].as_str(),
    ) {
        if !complete
            || bytes < wire["observed_body_bytes"].as_u64().unwrap_or(u64::MAX)
            || hash.len() != 64
            || !hash.bytes().all(|byte| byte.is_ascii_hexdigit())
        {
            return Err(io::ErrorKind::InvalidData.into());
        }
        final_value["observed_http_bytes"] = json!(bytes);
        final_value["http_sha256"] = json!(hash);
    }
    for field in [
        "worker_pid",
        "captured_at_ms",
        "accepted_write_count",
        "binding_generation",
    ] {
        if let Some(number) = wire[field].as_u64() {
            final_value[field] = json!(number);
        }
    }
    for field in ["worker_id", "request_id", "capture_id", "connection_id"] {
        if let Some(raw) = wire[field].as_str().filter(|raw| raw.len() <= 128) {
            final_value[field] = json!(text(raw, secrets));
        }
    }
    let final_len = body.len();
    let (prepared, clipped_prepared) = prefix(
        value["body"].as_str().unwrap_or(""),
        BODY_LIMIT.saturating_sub(final_len),
    );
    value["body"] = json!(prepared);
    value["body_truncated"] = json!(value["body_truncated"] == true || clipped_prepared);
    let remaining =
        BODY_LIMIT.saturating_sub(final_len + value["body"].as_str().unwrap_or("").len());
    let mut ingress_clipped = false;
    if let Some(input) = value.get_mut("ingress") {
        let (body, clipped) = prefix(input["body"].as_str().unwrap_or(""), remaining);
        input["body"] = json!(body);
        input["body_truncated"] = json!(input["body_truncated"] == true || clipped);
        if clipped {
            ingress_clipped = true;
            input["status"] = json!("truncated");
        }
    }
    for stage in value["stages"]
        .as_array_mut()
        .ok_or(io::ErrorKind::InvalidData)?
    {
        if stage["stage"] == "wire_final" {
            *stage = json!({"stage":"wire_final","source":"native_tls_uprobe","representation":"http_entity_from_tls_accepted_write",
                "status":if complete && (final_value["body_truncated"] == true || final_value["headers_truncated"] == true) {"truncated"} else {status},
                "note":"原生TLS实际接受的HTTP明文；网络刷出与上游实收保持独立"});
        } else if (stage["stage"] == "cc_prepared" && clipped_prepared)
            || (stage["stage"] == "ingress" && ingress_clipped)
        {
            stage["status"] = json!("truncated");
        }
    }
    value["wire_final"] = final_value;
    Ok(())
}

fn save(directory: &Path, submission: &NativeSubmission, payload: &Value) -> io::Result<()> {
    let id =
        Uuid::parse_str(&submission.request.request_id).map_err(|_| io::ErrorKind::InvalidInput)?;
    let value = snapshot(submission, payload)?;
    save_snapshot(directory, id, &value)
}

fn save_snapshot(directory: &Path, id: Uuid, value: &Value) -> io::Result<()> {
    let rejected = value["stage"] == "ingress_rejected";
    let suffix = if rejected { ".rejected.json" } else { ".json" };
    let limit = if rejected {
        REJECTED_SNAPSHOT_LIMIT
    } else {
        SNAPSHOT_LIMIT
    };
    let bytes = serde_json::to_vec(&value)?;
    if bytes.len() > limit {
        return Err(io::ErrorKind::InvalidData.into());
    }
    let _guard = STORAGE.lock().map_err(|_| io::ErrorKind::Other)?;
    fs::create_dir_all(directory)?;
    if fs::symlink_metadata(directory)?.file_type().is_symlink() {
        return Err(io::ErrorKind::PermissionDenied.into());
    }
    #[cfg(unix)]
    fs::set_permissions(directory, fs::Permissions::from_mode(0o700))?;
    // 初始250ms慢写可能晚于最终采集完成；同一把锁内保留更完整的同请求证据。
    let destination = directory.join(format!("{id}{suffix}"));
    {
        let mut options = OpenOptions::new();
        options.read(true);
        #[cfg(unix)]
        options.custom_flags(O_NOFOLLOW | O_NONBLOCK);
        match options.open(&destination) {
            Ok(file) => {
                if !file.metadata()?.is_file() {
                    return Err(io::ErrorKind::InvalidData.into());
                }
                let mut previous = Vec::new();
                file.take(limit as u64 + 1).read_to_end(&mut previous)?;
                if previous.len() <= limit {
                    if let Ok(previous) = serde_json::from_slice::<Value>(&previous) {
                        let rank = |wire: &Value| match wire["status"].as_str() {
                            Some("complete") => 3,
                            Some("incomplete") => 2,
                            Some("unavailable") => 1,
                            _ => 0,
                        };
                        if previous["account_id"] == value["account_id"]
                            && previous["attempt_id"] == value["attempt_id"]
                            && rank(&previous["wire_final"]) > rank(&value["wire_final"])
                        {
                            return Ok(());
                        }
                    }
                }
            }
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
    }
    let mut files = Vec::new();
    for entry in fs::read_dir(directory)? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().is_some_and(|ext| ext == "tmp")
            && path
                .file_stem()
                .and_then(|name| name.to_str())
                .is_some_and(|name| Uuid::parse_str(name).is_ok())
        {
            // 同一把锁覆盖所有写入，遗留临时文件来自中断的旧写入。
            fs::remove_file(&path)?;
            continue;
        }
        if path.extension().is_some_and(|ext| ext == "json")
            && path
                .file_stem()
                .and_then(|name| name.to_str())
                .is_some_and(|name| Uuid::parse_str(name.trim_end_matches(".rejected")).is_ok())
        {
            let metadata = match fs::symlink_metadata(&path) {
                Ok(metadata) => metadata,
                Err(error) if error.kind() == io::ErrorKind::NotFound => continue,
                Err(error) => return Err(error),
            };
            if !metadata.is_file() {
                return Err(io::ErrorKind::InvalidData.into());
            }
            let protected = path
                .file_stem()
                .and_then(|name| name.to_str())
                .is_some_and(|name| name.ends_with(".rejected"));
            files.push((protected, metadata.modified()?, path, metadata.len()));
        }
    }
    // 拒绝证据优先于正常快照；正常请求不能通过容量轮转清掉失败入站。
    files.sort_by_key(|(protected, modified, _, _)| (*protected, *modified));
    let mut total: u64 = files.iter().map(|(_, _, _, length)| length).sum();
    for (protected, _, path, length) in files {
        if total + bytes.len() as u64 <= STORAGE_LIMIT {
            break;
        }
        if protected && !rejected {
            continue;
        }
        // 独立的按天清理可能已回收该旧文件，缺失仍代表空间已释放。
        match fs::remove_file(path) {
            Ok(()) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
        total -= length;
    }
    if total + bytes.len() as u64 > STORAGE_LIMIT {
        return Err(io::ErrorKind::Other.into());
    }
    let temporary = directory.join(format!("{id}.tmp"));
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    options.mode(0o600);
    let result = (|| {
        let mut file = options.open(&temporary)?;
        file.write_all(&bytes)?;
        fs::rename(&temporary, destination)
    })();
    if result.is_err() {
        let _ = fs::remove_file(temporary);
    }
    result
}

/// 后台保存已鉴权的本地拒绝入站。@param directory 私有网关目录。@param id 根请求。@param headers 原始头。@param raw 已读取的正文。@param token 需要脱敏的入口密钥。@param full 是否保存完整正文。@return 采集队列状态。
pub(crate) fn record_gateway_rejection(
    directory: &Path,
    id: &str,
    headers: HeaderMap,
    raw: Option<Bytes>,
    token: String,
    full: bool,
) -> &'static str {
    let Ok(id) = Uuid::parse_str(id) else {
        return "dropped";
    };
    let Ok(permit) = WRITERS.try_acquire() else {
        return "dropped";
    };
    let directory = directory.to_path_buf();
    spawn_blocking(move || {
        let _permit = permit;
        let headers: Vec<(String, String)> = headers
            .iter()
            .filter_map(|(name, value)| Some((name.as_str().into(), value.to_str().ok()?.into())))
            .collect();
        let json_body = raw
            .as_ref()
            .and_then(|raw| serde_json::from_slice::<Value>(raw).ok());
        let (body, parsed) = json_body
            .as_ref()
            .map_or((&[][..], &Value::Null), |parsed| {
                (raw.as_deref().unwrap_or_default(), parsed)
            });
        let Some(mut preview) = ingress_snapshot(&headers, body, parsed, &token, full) else {
            return;
        };
        let available = json_body.is_some();
        if !available {
            preview["original_body_bytes"] = json!(raw.as_ref().map(Bytes::len));
            preview["original_body_sha256"] =
                json!(raw.as_ref().map(|raw| format!("{:x}", Sha256::digest(raw))));
        }
        let status = if !available {
            "unavailable"
        } else if preview["body_truncated"] == true {
            "truncated"
        } else {
            "complete"
        };
        let mut stage = json!({"stage":"ingress","source":"gateway_http_ingress","representation":preview["representation"],"status":status});
        if !available {
            stage["note"] = json!("已保存入站头部，正文读取、解码或 JSON 解析未完成");
        }
        let mut snapshot = if full { json!({}) } else { preview.clone() };
        snapshot["schema_version"] = json!(1);
        snapshot["stage"] = json!("ingress_rejected");
        snapshot["attempt_id"] = json!(id.to_string());
        snapshot["ingress"] = preview;
        snapshot["stages"] = json!([stage]);
        if let Err(error) = save_snapshot(&directory, id, &snapshot) {
            tracing::warn!(request_id=%id, reason=?error.kind(), "网关拒绝的入站采集保存失败");
        }
    });
    "queued"
}

/// 读取有界且匹配根请求的网关拒绝快照。@param directory 私有网关目录。@param id 根请求。@return 状态及脱敏证据。
pub(crate) async fn read_gateway_rejection(directory: &Path, id: &str) -> Value {
    let Ok(id) = Uuid::parse_str(id) else {
        return json!({"state":"missing"});
    };
    let path = directory.join(format!("{id}.rejected.json"));
    spawn_blocking(move || {
        let mut options = OpenOptions::new();
        options.read(true);
        #[cfg(unix)]
        options.custom_flags(O_NOFOLLOW | O_NONBLOCK);
        let Ok(file) = options.open(path) else {
            return json!({"state":"missing"});
        };
        let Ok(metadata) = file.metadata() else {
            return json!({"state":"missing"});
        };
        if !metadata.is_file() || metadata.len() > REJECTED_SNAPSHOT_LIMIT as u64 {
            return json!({"state":"missing"});
        }
        if metadata
            .modified()
            .ok()
            .and_then(|at| at.elapsed().ok())
            .is_some_and(|age| age >= GATEWAY_RETENTION)
        {
            return json!({"state":"expired"});
        }
        let mut bytes = Vec::new();
        if file
            .take(REJECTED_SNAPSHOT_LIMIT as u64 + 1)
            .read_to_end(&mut bytes)
            .is_err()
            || bytes.len() > REJECTED_SNAPSHOT_LIMIT
        {
            return json!({"state":"missing"});
        }
        let Ok(value) = serde_json::from_slice::<Value>(&bytes) else {
            return json!({"state":"missing"});
        };
        if value["stage"] != "ingress_rejected" || value["attempt_id"] != id.to_string() {
            return json!({"state":"missing"});
        }
        let mut result = json!({"state":"saved"});
        result["snapshot"] = value;
        result
    })
    .await
    .unwrap_or_else(|_| json!({"state":"missing"}))
}

/// 随诊断保留周期清理过期正文。@param directory 网关私有目录。
pub(crate) fn prune_gateway_rejections(directory: PathBuf) {
    spawn_blocking(move || {
        let Ok(_guard) = STORAGE.lock() else { return };
        let Ok(info) = fs::symlink_metadata(&directory) else {
            return;
        };
        if !info.is_dir() {
            return;
        }
        let Ok(entries) = fs::read_dir(&directory) else {
            return;
        };
        for entry in entries.flatten() {
            let name = entry.file_name();
            if !name
                .to_str()
                .and_then(|name| name.strip_suffix(".rejected.json"))
                .is_some_and(|id| Uuid::parse_str(id).is_ok())
            {
                continue;
            }
            let path = entry.path();
            if fs::symlink_metadata(&path).is_ok_and(|info| {
                info.is_file()
                    && info
                        .modified()
                        .ok()
                        .and_then(|at| at.elapsed().ok())
                        .is_some_and(|age| age >= GATEWAY_RETENTION)
            }) && let Err(error) = fs::remove_file(path)
            {
                tracing::warn!(reason=?error.kind(), "过期入站快照清理失败");
            }
        }
    });
}

/// 有界保存已验证事件；失败只影响采集状态。
/// @param directory 账号配置的私有目录；省略时关闭。
/// @param submission 当前尝试的归属与已知凭据。
/// @param payload 二进制输出的组装快照。
/// @param policy 同次内核实际头部决策。
/// @return 后台写入句柄，或disabled/dropped准入原因。
fn schedule(
    directory: Option<&str>,
    submission: &NativeSubmission,
    payload: &Value,
    policy: Option<&Value>,
) -> Result<JoinHandle<io::Result<()>>, &'static str> {
    // 在克隆正文和申请磁盘写入之前执行同次模式门控。
    if submission.log_mode != RequestLogMode::Debug {
        return Err("disabled");
    }
    let Some(directory) = directory else {
        return Err("disabled");
    };
    let Ok(permit) = WRITERS.try_acquire() else {
        return Err("dropped");
    };
    let directory = directory.to_owned();
    let submission = submission.clone();
    let mut payload = payload.clone();
    if let Some(policy) = policy {
        payload["_header_policy"] = policy.clone();
    }
    let write = spawn_blocking(move || {
        let _permit = permit;
        let result = save(Path::new(&directory), &submission, &payload);
        if let Err(error) = &result {
            tracing::warn!(request_id = %submission.request.request_id, account_id = submission.request.account_id,
                layer = "native_tls_capture", reason = ?error.kind(), "原生私有采集保存失败");
        }
        result
    });
    Ok(write)
}

/// 将私有快照排入有界后台写入。@param directory 私有目录。@param submission 当前归属。@param payload 原生快照。@param policy 同次决策。@return queued或即时拒绝原因。
pub(crate) fn record_queued(
    directory: Option<&str>,
    submission: &NativeSubmission,
    payload: &Value,
    policy: Option<&Value>,
) -> String {
    match schedule(directory, submission, payload, policy) {
        Ok(_) => "queued".into(),
        Err(reason) => reason.into(),
    }
}

/// 有界等待私有保存结果，适用于后台最终收口。@param directory 私有目录。@param submission 当前归属。@param payload 原生快照。@param policy 同次决策。@return 保存状态。
pub(crate) async fn record(
    directory: Option<&str>,
    submission: &NativeSubmission,
    payload: &Value,
    policy: Option<&Value>,
) -> String {
    let write = match schedule(directory, submission, payload, policy) {
        Ok(write) => write,
        Err(reason) => return reason.into(),
    };
    // 磁盘阻塞时及时交还模型响应，后台写入仍持有有界许可。
    let result = tokio::time::timeout(Duration::from_millis(250), write).await;
    if result.is_err() {
        return "timeout".into();
    }
    if matches!(result, Ok(Ok(Ok(())))) {
        "saved"
    } else {
        "failed"
    }
    .into()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 发送前拒绝仍保存脱敏入站，明确标记组装与TLS尚未发生。
    /// @return 无；原始哈希、秘密脱敏或阶段归属变化时失败。
    #[tokio::test]
    async fn rejected_input_keeps_private_ingress_without_fabricated_outbound() {
        let mut submission = submission();
        let raw = "{ \"metadata\": {\"api_key\":\"synthetic-bearer\"}, \"messages\": [] }";
        submission.ingress_capture = ingress(
            RequestLogMode::Debug,
            &[("Authorization".into(), "Bearer synthetic-bearer".into())],
            raw.as_bytes(),
            &serde_json::from_str(raw).unwrap(),
            &submission.bearer,
        );
        let payload = json!({"type":"error","error":"private-runtime-error", "body":"untrusted-error-body", "body_bytes":99});
        let directory = std::env::temp_dir().join(format!("native-rejected-{}", Uuid::new_v4()));
        let result = record(directory.to_str(), &submission, &payload, None).await;
        assert!(matches!(result.as_str(), "saved" | "timeout"));
        let path = directory.join(format!("{}.rejected.json", submission.request.request_id));
        for _ in 0..100 {
            if path.exists() {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
        let stored = fs::read_to_string(path).unwrap();
        assert!(!stored.contains("synthetic-bearer"));
        assert!(!stored.contains("private-runtime-error"));
        assert!(!stored.contains("untrusted-error-body"));
        let value: Value = serde_json::from_str(&stored).unwrap();
        assert_eq!(value["stage"], "ingress_rejected");
        assert_eq!(
            value["ingress"]["original_body_sha256"],
            format!("{:x}", Sha256::digest(raw.as_bytes()))
        );
        assert_eq!(
            value["ingress"]["body"],
            raw.replace("synthetic-bearer", "[REDACTED]")
        );
        assert_eq!(value["stages"][2]["status"], "unavailable");
        assert_eq!(value["stages"][3]["status"], "unavailable");
        assert_eq!(value["body"], "");
        assert!(value["original_body_sha256"].is_null());
        submission.log_mode = RequestLogMode::Info;
        assert_eq!(
            record(directory.to_str(), &submission, &payload, None).await,
            "disabled"
        );
        fs::remove_dir_all(directory).unwrap();
    }

    /// 缓存诊断只持久化已知枚举与有界位置，私有扩展和畸形结构受控拒绝。
    /// @return 无；秘密扩展可进入快照或诊断丢失时失败。
    #[test]
    fn message_cache_policy_snapshot_is_bounded_and_explicit() {
        let policy = json!({"mode":"sub2api","action":"applied","reason":"sub2api_tail",
            "selected":[{"message":2,"block":0},{"message":4,"block":0}],"breakpoints":2,"ttl":"1h"});
        assert_eq!(message_cache_policy(&policy), Some(policy.clone()));
        for (key, bad) in [
            ("reason", json!("synthetic-private-secret")),
            ("selected", json!([{"message":-1,"block":0}])),
            (
                "selected",
                json!([{"message":0,"block":0,"secret":"synthetic"}]),
            ),
            ("breakpoints", json!(5)),
            ("ttl", json!(["1h"])),
            ("secret", json!("synthetic-private-secret")),
        ] {
            let mut invalid = policy.clone();
            invalid[key] = bad;
            assert!(message_cache_policy(&invalid).is_none());
        }
        let payload = json!({"headers":[],"body":"{\"messages\":[]}","cache_policy":policy});
        let stored = snapshot(&submission(), &payload).unwrap();
        assert_eq!(stored["cache_policy"], policy);
        assert!(
            stored["stages"][2]["note"]
                .as_str()
                .unwrap()
                .contains("sub2api")
        );
    }

    #[tokio::test]
    async fn info_short_circuits_before_creating_capture_files() {
        let mut submission = submission();
        submission.log_mode = RequestLogMode::Info;
        let root = std::env::temp_dir().join(format!("info-capture-{}", Uuid::new_v4()));
        assert_eq!(
            record(
                root.to_str(),
                &submission,
                &json!({"body":"无效采集输入"}),
                None
            )
            .await,
            "disabled"
        );
        assert!(!root.exists());
        let mut value = serde_json::to_value(&submission).unwrap();
        value.as_object_mut().unwrap().remove("log_mode");
        assert_eq!(
            serde_json::from_value::<NativeSubmission>(value.clone())
                .unwrap()
                .log_mode,
            RequestLogMode::Info
        );
        value["log_mode"] = json!("trace");
        assert!(serde_json::from_value::<NativeSubmission>(value).is_err());
    }

    fn submission() -> NativeSubmission {
        serde_json::from_value(json!({
            "request":{"account_id":7,"environment_id":"synthetic","generation":1,"request_id":Uuid::new_v4().to_string(),
                "deadline_unix_ms":1,"method":"POST","target_url":"https://api.anthropic.com/v1/messages","headers":[],"preserve_header_casing":false},
            "log_mode":"debug","input":{"body":{"metadata":{"access_token":"echo-secret"}}},"bearer":"synthetic-bearer",
            "device_id":"a".repeat(64),"account_uuid":null,"organization_uuid":null,"email":"fixture@example.test","concurrency":2
        })).unwrap()
    }

    #[test]
    fn snapshot_preserves_duplicate_headers_and_masks_credentials_before_clipping() {
        let submission = submission();
        let body = json!({"model":"claude-sonnet-4-6","max_tokens":64,"messages":[{"role":"user","content":"synthetic-bearer echo-secret cookie-secret sk-ant-test"}],"metadata":{"password":"private-password"}}).to_string();
        let payload = json!({"headers":[["Authorization","Bearer synthetic-bearer"],["Cookie","cookie-secret"],["x-custom","first"],["x-custom","second"]],"body":body,"body_bytes":body.len(),"body_sha256":"a".repeat(64)});
        let value = snapshot(&submission, &payload).unwrap();
        let serialized = value.to_string();
        for secret in [
            "synthetic-bearer",
            "echo-secret",
            "cookie-secret",
            "private-password",
            "sk-ant-test",
        ] {
            assert!(!serialized.contains(secret));
        }
        assert_eq!(value["headers"][2], json!(["x-custom", "first"]));
        assert_eq!(value["headers"][3], json!(["x-custom", "second"]));
        let body: Value = serde_json::from_str(value["body"].as_str().unwrap()).unwrap();
        assert_eq!(body["max_tokens"], 64);
        assert_eq!(value["stage"], "cc_prepared");
        assert_eq!(value["body_truncated"], false);
        assert_eq!(value["header_policy"]["status"], "unavailable");
        let original = "{ \"z\": 1, \"a\": 2, \"password\": 1234, \"api_key\": \"x\" }";
        let ordered = snapshot(&submission, &json!({"headers":[],"body":original})).unwrap();
        assert_eq!(
            ordered["body"],
            "{ \"z\": 1, \"a\": 2, \"password\": \"[REDACTED]\", \"api_key\": \"[REDACTED]\" }"
        );
        let payload =
            json!({"headers":[],"body":json!({"content":"中".repeat(BODY_LIMIT)}).to_string()});
        let clipped = snapshot(&submission, &payload).unwrap();
        assert_eq!(clipped["body_truncated"], true);
        assert!(clipped["body"].as_str().unwrap().len() <= BODY_LIMIT);
    }

    /// 最终副本经脱敏保存，慢到的组装写入和缺证收口保持已有完整证据。@return 无。
    #[test]
    fn tls_final_is_redacted_bounded_and_monotonic() {
        let submission = submission();
        let directory = std::env::temp_dir().join(format!("native-wire-{}", Uuid::new_v4()));
        let body = r#"{ "password": "synthetic-hidden", "text": "ok", "cch": "final" }"#;
        let mut payload = json!({"headers":[["authorization","Bearer synthetic-native-token"]],"body":"{\"cch\":\"00000\"}",
            "_wire_final":{"source":"native_tls_uprobe","representation":"http_entity_from_tls_accepted_write","status":"complete",
            "complete":true,"flushed":null,"headers":[["Authorization","Bearer synthetic-native-token"],["Host","api.anthropic.com"]],
            "body":body,"body_truncated":false,"headers_truncated":false,"observed_body_bytes":body.len(),
            "body_sha256":format!("{:x}",Sha256::digest(body)),"reason":null}});
        save(&directory, &submission, &payload).unwrap();
        let path = directory.join(format!("{}.json", submission.request.request_id));
        let bytes = fs::read(&path).unwrap();
        let value: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(value["wire_final"]["headers"][0][1], "[REDACTED]");
        assert!(!String::from_utf8_lossy(&bytes).contains("synthetic-hidden"));
        assert!(!String::from_utf8_lossy(&bytes).contains("synthetic-native-token"));
        assert_eq!(value["wire_final"]["observed_body_bytes"], body.len());
        assert!(
            value["final_body_changes"]["items"]
                .as_array()
                .unwrap()
                .iter()
                .any(|item| item["path"] == "/cch")
        );
        payload.as_object_mut().unwrap().remove("_wire_final");
        save(&directory, &submission, &payload).unwrap();
        assert_eq!(fs::read(&path).unwrap(), bytes);
        payload["_wire_final"] = json!({"source":"native_tls_uprobe","representation":"http_entity_from_tls_accepted_write",
            "status":"unavailable","complete":false,"flushed":null,"headers":[],"body":"","body_truncated":false,
            "headers_truncated":false,"observed_body_bytes":null,"body_sha256":null,"reason":"CAPTURE_INTERRUPTED"});
        save(&directory, &submission, &payload).unwrap();
        assert_eq!(fs::read(&path).unwrap(), bytes);
        fs::remove_dir_all(directory).unwrap();
    }

    /// 缺口不生成全量哈希，截断秘密残片及共同正文预算得到保护。@return 无。
    #[test]
    fn tls_partial_and_shared_budget_preserve_unknown_ranges() {
        let submission = submission();
        let partial = "{\"password\":\"synthetic-partial";
        let mut payload = json!({"headers":[],"body":"{}","_wire_final":{
            "source":"native_tls_uprobe","representation":"http_entity_from_tls_accepted_write","status":"incomplete",
            "complete":false,"flushed":null,"reason":"HTTP_PARTIAL","headers":[],"body":partial,
            "body_truncated":true,"headers_truncated":false,"observed_body_bytes":null,"body_sha256":null}});
        let value = snapshot(&submission, &payload).unwrap();
        assert!(!value.to_string().contains("synthetic-partial"));
        assert!(value["wire_final"]["body_sha256"].is_null());
        payload["_wire_final"]["body_sha256"] = json!("a".repeat(64));
        assert!(snapshot(&submission, &payload).is_err());
        payload["_wire_final"]["body_sha256"] = Value::Null;
        payload["_wire_final"]["body"] = json!("x".repeat(BODY_LIMIT));
        payload["_wire_final"]["reason"] = Value::Null;
        payload["_wire_final"]["complete"] = json!(true);
        payload["_wire_final"]["status"] = json!("complete");
        payload["_wire_final"]["observed_body_bytes"] = json!(BODY_LIMIT);
        payload["_wire_final"]["body_sha256"] =
            json!(format!("{:x}", Sha256::digest("x".repeat(BODY_LIMIT))));
        let value = snapshot(&submission, &payload).unwrap();
        assert_eq!(value["body"], "");
        assert_eq!(value["body_truncated"], true);
        assert_eq!(
            value["wire_final"]["body"].as_str().unwrap().len(),
            BODY_LIMIT
        );
    }

    /// 缺口后的合法JSON及扩展头也丢弃，持久文件排除凭据残片。@return 无。
    #[test]
    fn tls_discontinuous_previews_are_withheld_before_persistence() {
        for reason in [
            "EVENT_SEQUENCE",
            "EVENT_LOSS",
            "EVENT_INVALID",
            "COUNTS_UNAVAILABLE",
            "HTTP_EXTRA_BYTES",
        ] {
            let submission = submission();
            let directory = std::env::temp_dir().join(format!("native-gap-{}", Uuid::new_v4()));
            let payload = json!({"headers":[],"body":"{}","_wire_final":{
                "source":"native_tls_uprobe","representation":"http_entity_from_tls_accepted_write",
                "status":"incomplete","complete":false,"flushed":null,"reason":reason,
                "headers":[["x-custom","synthetic-credential-prefix"]],
                "body":"{\"text\":\"synthetic-credential-prefix\"}","body_truncated":false,
                "headers_truncated":false,"observed_body_bytes":null,"body_sha256":null}});
            save(&directory, &submission, &payload).unwrap();
            let bytes = fs::read(directory.join(format!("{}.json", submission.request.request_id)))
                .unwrap();
            assert!(!String::from_utf8_lossy(&bytes).contains("synthetic-credential-prefix"));
            let value: Value = serde_json::from_slice(&bytes).unwrap();
            assert_eq!(value["wire_final"]["body"], "");
            assert_eq!(value["wire_final"]["headers"], json!([]));
            assert_eq!(value["wire_final"]["body_truncated"], true);
            assert_eq!(value["wire_final"]["headers_truncated"], true);
            assert_eq!(value["wire_final"]["reason"], reason);
            assert!(value["wire_final"]["body_sha256"].is_null());
            fs::remove_dir_all(directory).unwrap();
        }
    }

    /// 核对被过滤的入站凭据在正文和扩展头中重复出现时仍先脱敏。
    /// @return 私有文件、普通头顺序及转发输入均符合合同。
    #[tokio::test]
    async fn incoming_header_credentials_are_redacted_across_persisted_content() {
        let directory = std::env::temp_dir().join(format!("native-capture-{}", Uuid::new_v4()));
        let mut submission = submission();
        submission.input["headers"] = json!([
            ["aUtHoRiZaTiOn", "bEaReR synthetic-client-key"],
            ["Cookie", "synthetic-client-cookie"],
            ["X-API-Key", "synthetic-client-api-key"],
            ["x-custom", "ordinary-value"]
        ]);
        let original = "{ \"z\": 1, \"messages\": [{\"role\":\"user\",\"content\":\"synthetic-client-key synthetic-client-cookie synthetic-client-api-key ordinary-value\"}], \"max_tokens\":64 }";
        let payload = json!({"headers":[
            ["authorization","Bearer synthetic-bearer"],
            ["x-reference","synthetic-client-key synthetic-client-cookie synthetic-client-api-key"],
            ["x-custom","first"],["x-custom","second"]
        ],"body":original,"body_bytes":original.len(),"body_sha256":"a".repeat(64)});
        let input_before = submission.input.clone();
        let payload_before = payload.clone();
        assert_eq!(
            record(directory.to_str(), &submission, &payload, None).await,
            "saved"
        );
        let stored =
            fs::read_to_string(directory.join(format!("{}.json", submission.request.request_id)))
                .unwrap();
        for secret in [
            "synthetic-client-key",
            "synthetic-client-cookie",
            "synthetic-client-api-key",
            "synthetic-bearer",
        ] {
            assert!(!stored.contains(secret));
        }
        let value: Value = serde_json::from_str(&stored).unwrap();
        assert_eq!(value["headers"][1][1], "[REDACTED] [REDACTED] [REDACTED]");
        assert_eq!(value["headers"][2], json!(["x-custom", "first"]));
        assert_eq!(value["headers"][3], json!(["x-custom", "second"]));
        assert_eq!(
            value["body"],
            original
                .replace("synthetic-client-key", "[REDACTED]")
                .replace("synthetic-client-cookie", "[REDACTED]")
                .replace("synthetic-client-api-key", "[REDACTED]")
        );
        assert_eq!(value["original_body_bytes"], original.len());
        assert_eq!(submission.input, input_before);
        assert_eq!(payload, payload_before);
        fs::remove_dir_all(directory).unwrap();
    }

    /// 入口、实际头部决策与字段差异保持同次归属，已过滤秘密在所有阶段统一脱敏。
    /// @return 保存结果与原始观测摘要一致。
    #[test]
    fn stages_preserve_actual_policy_and_observed_changes_without_secret_echoes() {
        let mut submission = submission();
        let before = json!({"model":"claude-sonnet-4-6","settings":{"secret":"private-setting"},"env":{"PATH":"synthetic"},
            "messages":[{"role":"user","content":"synthetic-client-key synthetic-bearer"}],
            "tools":[{"name":"fixture","input_schema":{"properties":{"env":{"type":"string"}}}}],
            "metadata":{"user_id":"original-user"}});
        let raw = before.to_string();
        let headers = vec![
            ("Authorization".into(), "Bearer synthetic-client-key".into()),
            ("new-api-user".into(), "ordinary-value".into()),
        ];
        submission.input = json!({"body":before,"headers":headers});
        submission.ingress_capture = ingress(
            RequestLogMode::Debug,
            &headers,
            raw.as_bytes(),
            &before,
            &submission.bearer,
        );
        assert!(
            ingress(
                RequestLogMode::Info,
                &headers,
                raw.as_bytes(),
                &before,
                &submission.bearer
            )
            .is_none()
        );
        let mut after = before.clone();
        after.as_object_mut().unwrap().remove("settings");
        after.as_object_mut().unwrap().remove("env");
        after["metadata"]["user_id"] = json!("generated-user");
        let body = after.to_string();
        let decisions = json!([
            {"name":"Authorization","action":"drop","reason":"调用方凭据不作为上游凭据"},
            {"name":"new-api-user","action":"drop","reason":"调用方请求头未登记到协议白名单"},
            {"name":"new-api-user","action":"drop","reason":"调用方请求头未登记到协议白名单"}
        ]);
        let payload = json!({"headers":[["authorization","Bearer synthetic-bearer"]],"body":body,"body_bytes":body.len(),
            "body_sha256":format!("{:x}",Sha256::digest(body.as_bytes())),"_header_policy":header_policy(decisions.as_array().unwrap())});
        let value = snapshot(&submission, &payload).unwrap();
        for secret in [
            "synthetic-client-key",
            "synthetic-bearer",
            "private-setting",
        ] {
            assert!(!value.to_string().contains(secret));
        }
        assert_eq!(
            value["ingress"]["original_body_sha256"],
            format!("{:x}", Sha256::digest(raw.as_bytes()))
        );
        assert_eq!(value["ingress"]["original_body_bytes"], raw.len());
        assert_eq!(value["header_policy"]["decisions"], decisions);
        let changes = value["body_changes"]["items"].as_array().unwrap();
        for path in ["/settings", "/env"] {
            assert!(
                changes
                    .iter()
                    .any(|item| item["path"] == path && item["action"] == "removed")
            );
        }
        assert!(
            changes
                .iter()
                .any(|item| item["path"] == "/metadata/user_id")
        );
        assert!(
            !changes
                .iter()
                .any(|item| item["path"].as_str().unwrap().starts_with("/tools"))
        );
        assert_eq!(value["stages"][0]["status"], "complete");
        assert_eq!(value["stages"][3]["status"], "unavailable");
        let mut legacy_request = submission.clone();
        legacy_request.ingress_capture = None;
        let legacy = snapshot(&legacy_request, &payload).unwrap();
        assert_eq!(legacy["body_changes"]["status"], "unavailable");
    }

    /// 预算耗尽和损坏入口明确暴露，额外私有字段不落盘。
    /// @return 截断、差异数量和入口投影符合共享上限。
    #[test]
    fn stage_budgets_and_invalid_private_previews_are_visible() {
        let mut request = submission();
        let raw = json!({"content":"中".repeat(400_000)}).to_string();
        request.ingress_capture = ingress(
            RequestLogMode::Debug,
            &[],
            raw.as_bytes(),
            &serde_json::from_str::<Value>(&raw).unwrap(),
            &request.bearer,
        );
        request.ingress_capture.as_mut().unwrap()["unexpected_secret"] =
            json!("never-persist-this-field");
        let body = json!({"content":"中".repeat(BODY_LIMIT)}).to_string();
        let payload = json!({"headers":[],"body":body});
        let value = snapshot(&request, &payload).unwrap();
        assert_eq!(value["body_truncated"], true);
        assert_eq!(value["ingress"]["body_truncated"], true);
        assert!(
            value["body"].as_str().unwrap().len()
                + value["ingress"]["body"].as_str().unwrap().len()
                <= BODY_LIMIT
        );
        assert_eq!(value["body_changes"]["status"], "unavailable");
        assert!(!value.to_string().contains("never-persist-this-field"));
        let many = (0..1100)
            .map(|index| json!({"name":format!("x-{index}"),"action":"drop","reason":"未登记"}))
            .collect::<Vec<_>>();
        let bounded = header_policy(&many);
        assert_eq!(bounded["status"], "truncated");
        assert_eq!(bounded["observed_count"], 1100);
        assert_eq!(bounded["stored_count"], 1024);
        let before = json!({});
        let after: Value = (0..200)
            .map(|index| (format!("field-{index}"), json!(index)))
            .collect();
        let changes = body_changes(&before, &after);
        assert_eq!(changes["status"], "truncated");
        assert_eq!(changes["items"].as_array().unwrap().len(), 128);
        let captured = request.ingress_capture.as_ref().unwrap()["captured_at_ms"].clone();
        request.ingress_capture.as_mut().unwrap()["captured_at_ms"] = json!(0);
        assert!(snapshot(&request, &payload).is_err());
        request.ingress_capture.as_mut().unwrap()["captured_at_ms"] = captured;
        request.ingress_capture.as_mut().unwrap()["original_body_sha256"] = json!("invalid");
        assert!(snapshot(&request, &payload).is_err());
    }

    #[tokio::test]
    async fn retention_is_bounded_and_storage_failure_is_visible() {
        let directory = std::env::temp_dir().join(format!("native-capture-{}", Uuid::new_v4()));
        let mut submission = submission();
        let payload = json!({"headers":[],"body":"{}","body_bytes":2,"body_sha256":"a".repeat(64)});
        assert_eq!(record(None, &submission, &payload, None).await, "disabled");
        for _ in 0..51 {
            submission.request.request_id = Uuid::new_v4().to_string();
            save(&directory, &submission, &payload).unwrap();
        }
        assert_eq!(fs::read_dir(&directory).unwrap().count(), 51);
        let metadata =
            fs::metadata(directory.join(format!("{}.json", submission.request.request_id)))
                .unwrap();
        #[cfg(unix)]
        assert_eq!(metadata.permissions().mode() & 0o777, 0o600);
        // 稀疏文件覆盖总量上限，避免测试实际写入大正文。
        for _ in 0..2 {
            let path = directory.join(format!("{}.json", Uuid::new_v4()));
            fs::File::create(path)
                .unwrap()
                .set_len(STORAGE_LIMIT / 2 + 1)
                .unwrap();
        }
        submission.request.request_id = Uuid::new_v4().to_string();
        save(&directory, &submission, &payload).unwrap();
        let total: u64 = fs::read_dir(&directory)
            .unwrap()
            .map(|entry| entry.unwrap().metadata().unwrap().len())
            .sum();
        assert!(total <= STORAGE_LIMIT);
        let invalid = directory.join("ordinary-file");
        fs::write(&invalid, b"blocked").unwrap();
        assert_eq!(
            record(invalid.to_str(), &submission, &payload, None).await,
            "failed"
        );
        fs::remove_dir_all(directory).unwrap();
    }

    /// 正常请求容量轮转只回收正常快照，拒绝入站优先保留且总量仍有界。
    /// @return 无；正常流量挤掉拒绝证据或超出总量时失败。
    #[test]
    fn normal_snapshots_cannot_evict_rejected_ingress() {
        let directory = std::env::temp_dir().join(format!("native-capture-{}", Uuid::new_v4()));
        let mut submission = submission();
        let rejected = json!({"type":"error","error":"private-error"});
        save(&directory, &submission, &rejected).unwrap();
        let protected = directory.join(format!("{}.rejected.json", submission.request.request_id));
        let payload = json!({"headers":[],"body":"{}"});
        for _ in 0..2 {
            let path = directory.join(format!("{}.json", Uuid::new_v4()));
            fs::File::create(path)
                .unwrap()
                .set_len(STORAGE_LIMIT / 2 + 1)
                .unwrap();
        }
        submission.request.request_id = Uuid::new_v4().to_string();
        save(&directory, &submission, &payload).unwrap();
        assert!(protected.exists());
        // 拒绝证据占满预算时放弃正常副本，不影响业务也不删除失败证据。
        fs::OpenOptions::new()
            .write(true)
            .open(&protected)
            .unwrap()
            .set_len(STORAGE_LIMIT)
            .unwrap();
        submission.request.request_id = Uuid::new_v4().to_string();
        assert!(save(&directory, &submission, &payload).is_err());
        assert!(protected.exists());
        save(&directory, &submission, &rejected).unwrap();
        assert!(!protected.exists());
        assert!(
            directory
                .join(format!("{}.rejected.json", submission.request.request_id))
                .exists()
        );
        let total: u64 = fs::read_dir(&directory)
            .unwrap()
            .map(|entry| entry.unwrap().metadata().unwrap().len())
            .sum();
        assert!(total <= STORAGE_LIMIT);
        fs::remove_dir_all(directory).unwrap();
    }
}
