//! 原生签名修复只记住已由上游拒绝且降级后取得2xx的历史摘要。

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

const CAPACITY: usize = 4096;
const TTL: Duration = Duration::from_secs(7 * 24 * 60 * 60);

/// 已完整收到的明确签名拒绝标记，不保存上游任意错误文本。
#[derive(Clone)]
pub(crate) struct SignatureRejection;

/// 仅按真实会话和失效历史隔离的有界内存提示，进程重启后重新学习。
#[derive(Default)]
pub(crate) struct NativeSignatureRepairs {
    entries: Mutex<HashMap<[u8; 32], Instant>>,
}

impl NativeSignatureRepairs {
    /// 查询当前历史是否仍含已确认失效的完整 thinking 前缀。
    /// @param session_id 改写前的真实会话标识。
    /// @param body 当前尚未映射的请求正文。
    /// @return 命中时应在首次发送前应用相同降级。
    pub(crate) fn contains(&self, session_id: &str, body: &Value) -> bool {
        let keys = history_keys(session_id, body);
        let now = Instant::now();
        let mut entries = self
            .entries
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        entries.retain(|_, expires| *expires > now);
        keys.iter().any(|key| entries.contains_key(key))
    }

    /// 仅在同账号修复取得2xx后记住被拒绝历史的最后一个前缀摘要。
    /// @param session_id 与查询相同的真实会话标识。
    /// @param body 首次收到明确签名拒绝的原始正文。
    /// @return 无；没有 thinking 历史时不新增提示。
    pub(crate) fn remember(&self, session_id: &str, body: &Value) {
        let Some(key) = history_keys(session_id, body).pop() else {
            return;
        };
        self.remember_at(key, Instant::now());
    }

    fn remember_at(&self, key: [u8; 32], now: Instant) {
        let mut entries = self
            .entries
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        entries.retain(|_, expires| *expires > now);
        if entries.len() >= CAPACITY && !entries.contains_key(&key) {
            if let Some(oldest) = entries
                .iter()
                .min_by_key(|(_, expires)| **expires)
                .map(|(key, _)| *key)
            {
                entries.remove(&oldest);
            }
        }
        entries.insert(key, now + TTL);
    }
}

fn history_keys(session_id: &str, body: &Value) -> Vec<[u8; 32]> {
    if session_id.trim().is_empty() {
        return Vec::new();
    }
    let mut digest = Sha256::new();
    digest.update((session_id.len() as u64).to_le_bytes());
    digest.update(session_id.as_bytes());
    let mut keys = Vec::new();
    for message in body
        .get("messages")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if message["role"] != "assistant" {
            continue;
        }
        for block in message
            .get("content")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            if !matches!(
                block["type"].as_str(),
                Some("thinking" | "redacted_thinking")
            ) {
                continue;
            }
            // 完整思考文本及签名共同参与摘要；缓存边界变化和新增普通消息不改变已失效前缀。
            for field in ["type", "thinking", "signature", "data"] {
                let value = block.get(field).and_then(Value::as_str).unwrap_or_default();
                digest.update((value.len() as u64).to_le_bytes());
                digest.update(value.as_bytes());
            }
            keys.push(digest.clone().finalize().into());
        }
    }
    keys
}

/// 识别完整官方错误体中的 thinking 签名拒绝，普通 400 保持原路径。
/// @param body 已解码的有界错误正文。
/// @return 仅明确 invalid_request_error 的签名故障返回真。
pub(crate) fn is_signature_rejection(body: &[u8]) -> bool {
    let Ok(value) = serde_json::from_slice::<Value>(body) else {
        return false;
    };
    if value.pointer("/error/type").and_then(Value::as_str) != Some("invalid_request_error") {
        return false;
    }
    let message = value
        .pointer("/error/message")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    message.contains("signature")
        && (message.contains("thinking") || message.contains("thought_signature"))
        && (message.contains("invalid") || message.contains("corrupt"))
}

#[cfg(test)]
mod tests {
    use super::{CAPACITY, NativeSignatureRepairs, TTL, history_keys, is_signature_rejection};
    use serde_json::json;
    use std::time::Instant;

    /// 同会话跨模型复用已确认历史，新增轮次仍命中，其他会话和变更历史独立判断。
    #[test]
    fn history_hints_match_prefix_and_isolate_changed_content() {
        let cache = NativeSignatureRepairs::default();
        let body = json!({"model":"claude-opus-5-5","messages":[{"role":"user","content":"合成问题"},{"role":"assistant","content":[{"type":"thinking","thinking":"合成思考","signature":"synthetic-signature"}]}]});
        assert!(!cache.contains("session-a", &body));
        cache.remember("session-a", &body);
        let mut continuation = body.clone();
        continuation["messages"].as_array_mut().unwrap().extend([json!({"role":"user","content":"继续"}),json!({"role":"assistant","content":[{"type":"thinking","thinking":"新的思考","signature":"new-signature"}]})]);
        assert!(cache.contains("session-a", &continuation));
        assert!(!cache.contains("session-b", &body));
        let mut different_model = body.clone();
        different_model["model"] = json!("claude-sonnet-4-6");
        assert!(cache.contains("session-a", &different_model));
        assert!(!cache.contains("session-a", &json!({"messages":[]})));
        cache.remember("", &body);
        assert!(!cache.contains("", &body));
        assert!(!NativeSignatureRepairs::default().contains("session-a", &body));
        for (path, value) in [
            ("/messages/1/content/0/thinking", "改变的思考"),
            ("/messages/1/content/0/signature", "different-signature"),
        ] {
            let mut changed = body.clone();
            *changed.pointer_mut(path).unwrap() = json!(value);
            assert!(!cache.contains("session-a", &changed));
        }
    }

    /// 时间到期和容量上限实际回收，错误分类仅接纳明确供应商拒绝。
    #[test]
    fn history_hints_expire_and_remain_bounded() {
        let cache = NativeSignatureRepairs::default();
        let body = json!({"messages":[{"role":"assistant","content":[{"type":"thinking","thinking":"fixture","signature":"fixture"}]}]});
        cache.remember_at(
            history_keys("scope", &body)[0],
            Instant::now() - TTL - std::time::Duration::from_secs(1),
        );
        assert!(!cache.contains("scope", &body));
        for index in 0..=CAPACITY {
            cache.remember(&index.to_string(), &body);
        }
        assert_eq!(cache.entries.lock().unwrap().len(), CAPACITY);
        assert!(is_signature_rejection(br#"{"error":{"type":"invalid_request_error","message":"messages.2.content.0: Invalid `signature` in `thinking` block"}}"#));
        for raw in [br#"{"error":{"type":"invalid_request_error","message":"max_tokens invalid"}}"#.as_slice(), br#"{"error":{"type":"native_request_error","message":"Invalid signature in thinking"}}"#, b"incomplete"] { assert!(!is_signature_rejection(raw)); }
    }
}
