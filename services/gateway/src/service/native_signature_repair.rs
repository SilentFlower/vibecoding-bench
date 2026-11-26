//! 原生签名修复只记住已由上游拒绝且降级后取得2xx的历史摘要。

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

const CAPACITY: usize = 4096;
const TTL: Duration = Duration::from_secs(7 * 24 * 60 * 60);
pub(super) const CLEAR_THINKING: &str = "clear_thinking_20251015";
pub(super) const EMPTY_MESSAGE: &str = "(content removed)";
pub(super) const SIGNATURE_ERROR_BODY_LIMIT: usize = 1024 * 1024;

/// 思考历史降级时单个内容块的处理结果。
pub(super) enum ThinkingRewrite<'a> {
    Keep,
    Text(&'a str),
    Drop,
}

/// 应用签名修复的内容块规则。@param kind 块类型。@param text 思考文本。@return 降级动作。
pub(super) fn thinking_rewrite<'a>(kind: &str, text: Option<&'a str>) -> ThinkingRewrite<'a> {
    match kind {
        "redacted_thinking" => ThinkingRewrite::Drop,
        "thinking" | "" if kind == "thinking" || text.is_some() => {
            match text.filter(|text| !text.is_empty()) {
                Some(text) => ThinkingRewrite::Text(text),
                None => ThinkingRewrite::Drop,
            }
        }
        _ => ThinkingRewrite::Keep,
    }
}

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

#[cfg(target_os = "linux")]
pub(super) mod wire {
    use std::borrow::Cow;
    use std::fmt;

    use serde::de::{MapAccess, Visitor};
    use serde::ser::SerializeMap;
    use serde::{Deserialize, Deserializer, Serialize, Serializer};
    use serde_json::json;
    use serde_json::value::{RawValue, to_raw_value};

    use super::{CLEAR_THINKING, EMPTY_MESSAGE, ThinkingRewrite, thinking_rewrite};
    use crate::service::rewriter::refresh_cch_attestation;

    // 保留原键序和未修改值的 JSON 字节，避免重编码工具实参中的高精度数字。
    struct Object(Vec<(String, Box<RawValue>)>);

    impl<'de> Deserialize<'de> for Object {
        fn deserialize<D: Deserializer<'de>>(decoder: D) -> Result<Self, D::Error> {
            struct Fields;
            impl<'de> Visitor<'de> for Fields {
                type Value = Object;

                fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                    formatter.write_str("JSON 对象")
                }

                fn visit_map<M: MapAccess<'de>>(self, mut map: M) -> Result<Object, M::Error> {
                    let mut fields = Vec::new();
                    while let Some(field) = map.next_entry()? {
                        fields.push(field);
                    }
                    Ok(Object(fields))
                }
            }
            decoder.deserialize_map(Fields)
        }
    }

    impl Serialize for Object {
        fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
            let mut map = serializer.serialize_map(Some(self.0.len()))?;
            for (key, value) in &self.0 {
                map.serialize_entry(key, value)?;
            }
            map.end()
        }
    }

    impl Object {
        fn field(&mut self, name: &str) -> Option<&mut Box<RawValue>> {
            self.0
                .iter_mut()
                .find(|(key, _)| key == name)
                .map(|(_, value)| value)
        }

        fn remove(&mut self, name: &str) -> bool {
            let original = self.0.len();
            self.0.retain(|(key, _)| key != name);
            self.0.len() != original
        }
    }

    #[derive(Deserialize)]
    struct Block<'a> {
        #[serde(rename = "type", default, borrow)]
        kind: Cow<'a, str>,
        #[serde(default, borrow)]
        thinking: Option<&'a RawValue>,
    }

    fn repair_context(field: &mut Box<RawValue>) -> Option<()> {
        let mut context: Object = serde_json::from_str(field.get()).ok()?;
        let edits = context.field("edits")?;
        let mut items: Vec<Box<RawValue>> = serde_json::from_str(edits.get()).ok()?;
        let original = items.len();
        items.retain(|item| {
            !serde_json::from_str::<Block<'_>>(item.get())
                .is_ok_and(|block| block.kind == CLEAR_THINKING)
        });
        if items.len() != original {
            if items.is_empty() {
                context.remove("edits");
            } else {
                *edits = to_raw_value(&items).ok()?;
            }
            *field = to_raw_value(&context).ok()?;
        }
        Some(())
    }

    fn repair_content(message: &mut Box<RawValue>) -> Option<bool> {
        let mut row: Object = serde_json::from_str(message.get()).ok()?;
        let content = row.field("content")?;
        if !content.get().starts_with('[') {
            return Some(false);
        }
        let blocks: Vec<Box<RawValue>> = serde_json::from_str(content.get()).ok()?;
        let mut sanitized = Vec::with_capacity(blocks.len());
        let mut changed = false;
        for raw in blocks {
            let block = serde_json::from_str::<Block<'_>>(raw.get()).ok()?;
            let text: Option<Cow<'_, str>> = block
                .thinking
                .and_then(|text| serde_json::from_str(text.get()).ok());
            match thinking_rewrite(&block.kind, text.as_deref()) {
                ThinkingRewrite::Keep => sanitized.push(raw),
                ThinkingRewrite::Text(text) => {
                    sanitized.push(to_raw_value(&json!({"type":"text","text":text})).ok()?);
                    changed = true;
                }
                ThinkingRewrite::Drop => changed = true,
            }
        }
        if changed {
            if sanitized.is_empty() {
                sanitized.push(to_raw_value(&json!({"type":"text","text":EMPTY_MESSAGE})).ok()?);
            }
            *content = to_raw_value(&sanitized).ok()?;
            *message = to_raw_value(&row).ok()?;
        }
        Some(changed)
    }

    /// 降级 V2 最终出站正文。@param body 已核验、已映射的正文。@return 实质变更后的出站字节。
    pub(in crate::service) fn repair_body(body: &[u8]) -> Option<Vec<u8>> {
        let mut root: Object = serde_json::from_slice(body).ok()?;
        let mut changed = root.remove("thinking");
        if changed && let Some(context) = root.field("context_management") {
            repair_context(context);
        }
        let messages = root.field("messages")?;
        let mut rows: Vec<Box<RawValue>> = serde_json::from_str(messages.get()).ok()?;
        let mut changed_rows = false;
        for row in &mut rows {
            changed_rows |= repair_content(row)?;
        }
        if changed_rows {
            *messages = to_raw_value(&rows).ok()?;
            changed = true;
        }
        let output = changed.then(|| serde_json::to_vec(&root).ok()).flatten()?;
        Some(refresh_cch_attestation(output, "2.1.293"))
    }
}

#[cfg(test)]
mod tests {
    use super::{CAPACITY, NativeSignatureRepairs, TTL, history_keys, is_signature_rejection};
    use serde_json::json;
    use std::time::Instant;

    /// 只改思考块和依赖策略，原工具值与改写后的 CCH 可回到实际发送路径。
    #[cfg(target_os = "linux")]
    #[test]
    fn v2_repair_preserves_tool_value_bytes_and_refreshes_cch() {
        use super::wire::repair_body;
        use crate::service::rewriter::refresh_cch_attestation;
        use serde_json::Value;
        use std::str;

        let raw = br#"{
            "model":"synthetic",
            "system":[{"type":"text","text":"x-anthropic-billing-header: cc_version=2.1.293.abc; cc_entrypoint=cli; cch=00000;"}],
            "thinking":{"type":"adaptive"},
            "context_management":{"edits":[{"type":"clear_thinking_20251015"},{"type":"clear_tool_uses_20250919"}]},
            "messages":[{"role":"assistant","content":[
                {"type":"thinking","thinking":"synthetic thought","signature":"old"},
                {"type":"redacted_thinking","data":"opaque"},
                {"type":"tool_use","id":"toolu_example","input":{"amount":1.234567890123456789e9}}
            ]},{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_example","content":"done"}]}]
        }"#;
        let repaired = repair_body(raw).unwrap();
        let text = str::from_utf8(&repaired).unwrap();
        assert!(text.contains("1.234567890123456789e9"));
        assert!(!text.contains("cch=00000"));
        assert_eq!(
            repaired,
            refresh_cch_attestation(repaired.clone(), "2.1.293")
        );
        let view: Value = serde_json::from_slice(&repaired).unwrap();
        assert!(view.get("thinking").is_none());
        assert_eq!(
            view["messages"][0]["content"][0],
            json!({"type":"text","text":"synthetic thought"})
        );
        assert_eq!(view["messages"][0]["content"][1]["id"], "toolu_example");
        assert_eq!(
            view["messages"][1]["content"][0]["tool_use_id"],
            "toolu_example"
        );
        assert_eq!(
            view["context_management"]["edits"][0]["type"],
            "clear_tool_uses_20250919"
        );
        assert!(repair_body(&repaired).is_none());
    }

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
