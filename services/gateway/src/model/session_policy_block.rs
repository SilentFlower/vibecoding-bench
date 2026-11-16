//! 会话策略封禁的安全管理摘要，不包含原始会话或业务正文。

use serde::Serialize;
use serde_json::Value;

/// 一轮持久封禁及管理查询投影。
#[derive(Debug, Clone, Serialize)]
pub struct SessionPolicyBlock {
    pub id: String,
    pub session_key: String,
    pub api_token_id: i64,
    pub token_name: Option<String>,
    pub account_id: i64,
    pub account_name: Option<String>,
    pub model: String,
    pub reason: String,
    pub source_request_id: Option<String>,
    pub blocked_at_ms: i64,
    pub expires_at_ms: i64,
    pub released_at_ms: Option<i64>,
    pub blocked_request_count: i64,
    pub last_blocked_at_ms: Option<i64>,
    pub state: String,
}

/// 封禁分页结果，时间以服务端同一快照为准。
#[derive(Serialize)]
pub struct SessionPolicyBlockPage {
    pub items: Vec<SessionPolicyBlock>,
    pub total: i64,
    pub page: i64,
    pub page_size: i64,
    pub observed_at_ms: i64,
}

/// 原始请求冻结的匿名身份与安全参数。
#[derive(Clone)]
pub(crate) struct SessionPolicyIdentity {
    pub session_key: String,
    pub api_token_id: i64,
    pub model: String,
    pub source_request_id: Option<String>,
}

/// 从实际响应的结构化字段识别策略拒答，普通回答文本不参与。
/// @param value 已完整解析的 JSON 或 SSE data 事件。
/// @return 有限的安全原因分类。
pub(crate) fn classify_policy_refusal(value: &Value) -> Option<&'static str> {
    if value
        .get("stop_reason")
        .or_else(|| value.pointer("/delta/stop_reason"))
        .and_then(Value::as_str)
        == Some("refusal")
        || value["type"].as_str() == Some("refusal")
        || value["content"]
            .as_array()
            .is_some_and(|blocks| blocks.iter().any(|b| b["type"] == "refusal"))
        || value.pointer("/content_block/type").and_then(Value::as_str) == Some("refusal")
    {
        return Some("refusal");
    }
    let error = value
        .get("error")
        .filter(|v| v.is_object())
        .or_else(|| (value["type"] == "error").then_some(value))?;
    let codes = [
        error["code"].as_str(),
        error["upstream_code"].as_str(),
        error["type"].as_str(),
    ];
    // 认证故障优先保留原分类，避免错误详情引用政策文案引发误封。
    if codes.contains(&Some("authentication_error")) {
        return None;
    }
    if codes.contains(&Some("reasoning_extraction")) {
        return Some("reasoning_extraction");
    }
    if codes.iter().flatten().any(|c| {
        matches!(
            *c,
            "content_policy"
                | "content_filter"
                | "content_filter_refusal"
                | "cyber_policy"
                | "moderation_blocked"
                | "safety_violation"
                | "usage_policy"
        )
    }) {
        return Some("content_policy");
    }
    let message = error["message"]
        .as_str()
        .unwrap_or_default()
        .to_ascii_lowercase();
    if message.contains("reasoning_extraction") {
        return Some("reasoning_extraction");
    }
    if message.contains("safeguards flagged") {
        return Some("safeguard");
    }
    if message.contains("legal/aup")
        || message.contains("usage policy")
        || message.contains("violate our usage")
    {
        return Some("usage_policy");
    }
    None
}
