use axum::http::HeaderMap;
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::service::rewriter::extract_session_id_from_body;

pub(super) const SESSION_HEADER: &str = "x-session-id";
const CLAUDE_EXPLICIT_DOMAIN: &[u8] = b"cc2api:v3:session\0";
const GEMINI_EXPLICIT_DOMAIN: &[u8] = b"cc2api:v3:agy:session\0";
const CLAUDE_CONTENT_DOMAIN: &[u8] = b"cc2api:v3:claude:content:1\0";
const GEMINI_CONTENT_DOMAIN: &[u8] = b"cc2api:v3:agy:content:1\0";

/// 入站会话的显示值及平台和令牌隔离的调度键。
pub(super) struct RequestSession {
    original: Option<String>,
    key: Option<String>,
    from_content: bool,
}

impl RequestSession {
    /// 解析 Claude 正文和会话头，保留已存在的显式绑定。
    /// @param token_id 启用 V3 调度时的入口令牌 ID。@param headers 原始头。@param body 已解码正文。
    /// @return 在账号选择、改写和重试间共用的会话。
    pub(super) fn claude(token_id: Option<i64>, headers: &HeaderMap, body: &Value) -> Self {
        let explicit = extract_session_id_from_body(body)
            .or_else(|| header_id(headers, "x-claude-code-session-id"))
            .or_else(|| token_id.and_then(|_| header_id(headers, SESSION_HEADER)));
        if let Some(id) = explicit {
            let key = token_id.map(|token_id| claude_explicit_key(token_id, &id));
            return Self::explicit(id, key);
        }

        Self::from_content(token_id.and_then(|token_id| {
            let first = first_user_content(body.get("messages")?, "content", false)?;
            let model = body.get("model")?.as_str()?.trim();
            content_key(
                CLAUDE_CONTENT_DOMAIN,
                token_id,
                model,
                [body.get("tools"), body.get("system"), Some(first)],
                true,
            )
        }))
    }

    /// 解析 Gemini 入口头与稳定首轮内容。
    /// @param token_id 入口令牌 ID。@param headers 原始头。@param model URL 请求模型。@param body 入站正文。
    /// @return 在账号选择、改写和重试间共用的会话。
    pub(super) fn gemini(token_id: i64, headers: &HeaderMap, model: &str, body: &Value) -> Self {
        if let Some(id) = header_id(headers, SESSION_HEADER) {
            let key = explicit_key(GEMINI_EXPLICIT_DOMAIN, token_id, &id);
            return Self::explicit(id, Some(key));
        }

        Self::from_content(
            body.get("contents")
                .and_then(|contents| first_user_content(contents, "parts", true))
                .and_then(|first| {
                    content_key(
                        GEMINI_CONTENT_DOMAIN,
                        token_id,
                        model,
                        [
                            body.get("tools"),
                            body.pointer("/systemInstruction/parts"),
                            Some(first),
                        ],
                        false,
                    )
                }),
        )
    }

    fn explicit(id: String, key: Option<String>) -> Self {
        Self {
            original: Some(id).filter(|id| valid_id(id)),
            key,
            from_content: false,
        }
    }

    fn from_content(key: Option<String>) -> Self {
        Self {
            original: None,
            key,
            from_content: true,
        }
    }

    /// 返回符合诊断约定的客户端原始值。@return 有效原值或空。
    pub(super) fn original(&self) -> Option<&str> {
        self.original.as_deref()
    }

    /// 返回用于实际选号的键。@return 匿名键或空。
    pub(super) fn key(&self) -> Option<&str> {
        self.key.as_deref()
    }

    /// 返回可用于缺省展示的内容派生键。@return 内容派生值或空。
    pub(super) fn derived(&self) -> Option<&str> {
        self.key().filter(|_| self.from_content)
    }
}

/// 使用原 V3 键域计算 Claude 显式绑定。
/// @param token_id 入口令牌 ID。@param id 改写前的会话 ID。
/// @return 与既有数据库绑定一致的键。
pub(super) fn claude_explicit_key(token_id: i64, id: &str) -> String {
    explicit_key(CLAUDE_EXPLICIT_DOMAIN, token_id, id)
}

fn explicit_key(domain: &[u8], token_id: i64, id: &str) -> String {
    let mut hash = Sha256::new();
    hash.update(domain);
    hash.update(token_id.to_be_bytes());
    hash.update(id.as_bytes());
    hex::encode(hash.finalize())
}

fn valid_id(id: &str) -> bool {
    id.len() <= 256 && !id.trim().is_empty() && !id.chars().any(char::is_control)
}

fn header_id(headers: &HeaderMap, name: &str) -> Option<String> {
    let mut values = headers.get_all(name).iter();
    let id = values.next()?.to_str().ok()?;
    (values.next().is_none() && valid_id(id)).then(|| id.to_owned())
}

fn first_user_content<'a>(
    messages: &'a Value,
    field: &str,
    default_user: bool,
) -> Option<&'a Value> {
    messages.as_array()?.iter().find_map(|message| {
        let user = match message.get("role") {
            Some(role) => role.as_str() == Some("user"),
            None => default_user,
        };
        let content = user.then(|| message.get(field)).flatten()?;
        let meaningful = match content {
            Value::String(text) => !text.trim().is_empty(),
            Value::Array(blocks) => blocks.iter().any(meaningful_user_block),
            _ => false,
        };
        meaningful.then_some(content)
    })
}

fn meaningful_user_block(block: &Value) -> bool {
    if let Some(text) = block.get("text") {
        return text.as_str().is_some_and(|text| !text.trim().is_empty());
    }
    block.as_object().is_some_and(|fields| {
        !fields.is_empty()
            && !fields.contains_key("functionResponse")
            && block.get("type").and_then(Value::as_str) != Some("tool_result")
    })
}

fn content_key(
    domain: &[u8],
    token_id: i64,
    model: &str,
    fields: [Option<&Value>; 3],
    ignore_cache_control: bool,
) -> Option<String> {
    if model.is_empty() {
        return None;
    }
    let mut hash = Sha256::new();
    hash.update(domain);
    hash.update(token_id.to_be_bytes());
    hash_string(&mut hash, model);
    for field in fields {
        let value = field.filter(|value| match value {
            Value::String(text) => !text.is_empty(),
            Value::Array(items) => !items.is_empty(),
            Value::Object(fields) => !fields.is_empty(),
            _ => true,
        });
        hash_json(
            &mut hash,
            value.unwrap_or(&Value::Null),
            ignore_cache_control,
        );
    }
    Some(hex::encode(hash.finalize()))
}

fn hash_string(hash: &mut Sha256, text: &str) {
    hash.update((text.len() as u64).to_be_bytes());
    hash.update(text.as_bytes());
}

fn hash_json(hash: &mut Sha256, value: &Value, ignore_cache_control: bool) {
    match value {
        Value::Null => hash.update(b"n"),
        Value::Bool(value) => hash.update([b'b', u8::from(*value)]),
        Value::Number(value) => {
            hash.update(b"d");
            hash_string(hash, &value.to_string());
        }
        Value::String(text) => {
            hash.update(b"s");
            hash_string(hash, text);
        }
        Value::Array(values) => {
            hash.update(b"[");
            for value in values {
                hash_json(hash, value, ignore_cache_control);
            }
            hash.update(b"]");
        }
        Value::Object(fields) => {
            hash.update(b"{");
            // 入站 JSON 保留键顺序，这里只排序引用以避免复制多模态数据。
            let mut ordered: Vec<_> = fields.iter().collect();
            ordered.sort_unstable_by(|(left, _), (right, _)| left.cmp(right));
            for (key, value) in ordered {
                if ignore_cache_control && key == "cache_control" {
                    continue;
                }
                hash.update(b"k");
                hash_string(hash, key);
                hash_json(hash, value, false);
            }
            hash.update(b"}");
        }
    }
}

#[cfg(test)]
mod tests {
    use axum::http::HeaderMap;
    use serde_json::json;

    use super::{RequestSession, SESSION_HEADER, claude_explicit_key};

    #[test]
    fn derived_sessions_are_stable_across_turns_and_isolated_by_scope() {
        let headers = HeaderMap::new();
        let claude_first = json!({
            "model": "test-model", "system": [{"text": "system", "type": "text"}],
            "messages": [{"role": "user", "content": [{"type": "text", "text": "first"}]}]
        });
        let claude_next = json!({
            "model": "test-model", "tools": [],
            "system": [{"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": [{"text": "first", "type": "text"}]},
                {"role": "assistant", "content": "reply"}, {"role": "user", "content": "next"}]
        });
        let first = RequestSession::claude(Some(1), &headers, &claude_first);
        assert_eq!(first.key().map(str::len), Some(64));
        assert_eq!(first.derived(), first.key());
        assert_eq!(
            RequestSession::claude(Some(1), &headers, &claude_next).key(),
            first.key()
        );
        assert_ne!(
            RequestSession::claude(Some(2), &headers, &claude_next).key(),
            first.key()
        );
        assert!(
            RequestSession::claude(None, &headers, &claude_first)
                .key()
                .is_none()
        );

        let gemini_first = json!({"contents": [{"parts":[{"text":"first"}]}]});
        let gemini_next = json!({"contents": [
            {"role":"user", "parts":[{"text":"first"}]},
            {"role":"model", "parts":[{"text":"reply"}]},
            {"role":"user", "parts":[{"text":"next"}]}]});
        let gemini = RequestSession::gemini(1, &headers, "test-model", &gemini_first);
        assert_eq!(gemini.key().map(str::len), Some(64));
        assert_ne!(gemini.key(), first.key());
        assert_eq!(
            RequestSession::gemini(1, &headers, "test-model", &gemini_next).key(),
            gemini.key()
        );
        assert_ne!(
            RequestSession::gemini(1, &headers, "other-model", &gemini_next).key(),
            gemini.key()
        );
        assert_ne!(
            RequestSession::gemini(
                1,
                &headers,
                "test-model",
                &json!({"contents":[{"parts":[{"text":"other"}]}]})
            )
            .key(),
            gemini.key()
        );
    }

    #[test]
    fn explicit_ids_take_precedence_and_invalid_headers_fall_back() {
        let mut headers = HeaderMap::new();
        headers.append(SESSION_HEADER, "shared".parse().unwrap());
        headers.append("x-claude-code-session-id", "claude-header".parse().unwrap());
        let body = json!({"metadata":{"user_id":"fixture_session_claude-body"}});
        let claude = RequestSession::claude(Some(1), &headers, &body);
        assert_eq!(claude.original(), Some("claude-body"));
        assert_eq!(
            claude.key(),
            Some(claude_explicit_key(1, "claude-body").as_str())
        );
        assert_eq!(
            RequestSession::claude(Some(1), &headers, &json!({})).original(),
            Some("claude-header")
        );
        let gemini = RequestSession::gemini(1, &headers, "gemini", &json!({}));
        assert_eq!(gemini.original(), Some("shared"));
        assert!(gemini.derived().is_none());
        headers.remove("x-claude-code-session-id");
        assert_ne!(
            RequestSession::claude(Some(1), &headers, &json!({})).key(),
            gemini.key()
        );

        headers.append(SESSION_HEADER, "duplicate".parse().unwrap());
        assert!(
            RequestSession::gemini(
                1,
                &headers,
                "gemini",
                &json!({"contents":[{"parts":[{"text":" "}]}]})
            )
            .key()
            .is_none()
        );
        let body = json!({"contents":[{"parts":[{"inlineData":{"mimeType":"image/png","data":"a".repeat(1024*1024)}}]}]});
        assert!(
            RequestSession::gemini(1, &headers, "gemini", &body)
                .derived()
                .is_some()
        );
    }
}
