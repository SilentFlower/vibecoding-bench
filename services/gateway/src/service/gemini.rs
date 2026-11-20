//! Gemini入口的账号许可、原生帧保真与跨HTTP工具轮归属。
mod replay;

use std::collections::{BTreeSet, HashMap};
use std::io::Error as IoError;
use std::mem::replace;
use std::pin::Pin;
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::Duration;

use axum::Json;
use axum::body::{Body, Bytes};
use axum::extract::{Path, Request, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use futures_util::{Stream, StreamExt};
use serde_json::{Value, json};
use tokio::sync::{Semaphore, mpsc};
use tokio::time::{Instant, sleep_until, timeout_at};
use tokio_stream::wrappers::ReceiverStream;
use uuid::Uuid;

use crate::error::AppError;
use crate::handler::router::AppState;
use crate::model::account::Account;
use crate::model::api_token::{ApiToken, ApiTokenStatus};
use crate::model::request_diagnostics::RequestLogMode;
use crate::service::account::{
    AccountService, AccountSlotPermit, CredentialActivity, DEFAULT_REQUEST_SLOT_UNITS,
};
use crate::service::agy_contract::{
    AGY_REQUEST_SECONDS, AGY_SOURCE_SHA256, AgyAccessSnapshot, AgyModelId, AgySystemPromptPolicy,
};
use crate::service::diagnostics::agy::AgyAttemptTrace;
use crate::service::diagnostics::{
    self, CURRENT_LOG_MODE, CURRENT_TRACE, RequestTraceGuard, TraceContext,
};
use crate::service::runtime_transport::{self, PreparedTransport};
use crate::service::system_update::{self, InferenceCutover, UpdateActivity};
use crate::service::v3_scheduling::{RequestPhase, SchedulingRequest};
use crate::service::{native_capture, runtime_bridge};
use replay::{ReplayKey, ToolReplay};

pub(crate) const BODY_LIMIT: usize = 16 * 1024 * 1024;
const FRAME_LIMIT: usize = 64 * 1024 * 1024;
const AGY_TOOL_WAIT_LIMIT: Duration = Duration::from_secs(3600);

/// 随原生工具轮保留的许可，下一HTTP请求共享同一份所有权。
struct Admission {
    _slot: AccountSlotPermit,
    credentials: CredentialActivity,
    _maintenance: UpdateActivity,
}

/// 区分客户端名称和发送器实际执行的目录型号。
#[derive(Clone)]
struct RoutedModel {
    requested: String,
    resolved: String,
}

/// 仍在等待客户端工具结果的原生请求归属。
struct ToolTurn {
    token_id: i64,
    account: Account,
    model: RoutedModel,
    contents: Value,
    runtime_contents: Option<Value>,
    calls: Vec<Value>,
    deadline: Instant,
    admission: Arc<Admission>,
    transport: Arc<PreparedTransport>,
    previous_request_id: String,
    receipt_body: Option<Value>,
    retained: bool,
    claimed: bool,
    cutover: Option<InferenceCutover>,
}

struct ContinuationClaim {
    service: Arc<GeminiService>,
    key: Option<String>,
    resolved_model: String,
    runtime_contents: Option<Value>,
    replay_key: ReplayKey,
    replay: Arc<ToolReplay>,
}

enum Continuation {
    Generate(Account, Arc<Admission>, ContinuationClaim),
    Replay(Arc<ToolReplay>),
}

impl Drop for ContinuationClaim {
    fn drop(&mut self) {
        if let Some(key) = self.key.take() {
            let mut registry = self.service.registry();
            if let Some(turn) = registry.turns.get_mut(&key) {
                turn.claimed = false;
            }
            registry.remove_replay(&self.replay_key, &self.replay);
            self.replay.finish(Err(AppError::AgyToolReplayUnavailable));
        }
    }
}

impl ContinuationClaim {
    async fn finish(
        &self,
        token_id: i64,
        body: &Value,
        deadline: Instant,
        gif_frames: bool,
    ) -> Result<(), AppError> {
        let key = self
            .key
            .as_ref()
            .ok_or_else(|| invalid("原工具归属已释放"))?;
        let (transport, previous, finished, previous_deadline) = {
            let turns = self.service.registry();
            let turn = turns
                .turns
                .get(key)
                .ok_or_else(|| invalid("原工具轮已到期"))?;
            (
                turn.transport.clone(),
                turn.previous_request_id.clone(),
                turn.receipt_body.is_some(),
                turn.deadline,
            )
        };
        if !finished {
            let mut runtime_body = body.clone();
            if let Some(contents) = &self.runtime_contents {
                runtime_body["contents"] = contents.clone();
            }
            transport
                .finish_agy_tools(
                    &previous,
                    token_id,
                    runtime_body,
                    deadline.min(previous_deadline),
                    gif_frames,
                )
                .await?;
            let mut registry = self.service.registry();
            let turn = registry
                .turns
                .get_mut(key)
                .ok_or_else(|| invalid("原工具轮已到期"))?;
            turn.receipt_body = Some(body.clone());
        }
        Ok(())
    }

    fn begin_submission(&mut self) -> Option<Arc<ToolReplay>> {
        let previous = self.key.take()?;
        // 原回填已经收口。发送的连接中断也不能重新领取原轮次。
        self.service.registry().turns.remove(&previous);
        let service = Arc::downgrade(&self.service);
        let replay = Arc::downgrade(&self.replay);
        let deadline = self.replay.deadline;
        let key = self.replay_key.clone();
        tokio::spawn(async move {
            sleep_until(deadline).await;
            if let Some(replay) = replay.upgrade() {
                if let Some(service) = service.upgrade() {
                    service.registry().remove_replay(&key, &replay);
                }
                replay.expire();
            }
        });
        Some(self.replay.clone())
    }
}

#[derive(Default)]
struct ToolRegistry {
    turns: HashMap<String, ToolTurn>,
    replays: HashMap<ReplayKey, Arc<ToolReplay>>,
}

impl ToolRegistry {
    fn remove_replay(&mut self, key: &ReplayKey, replay: &Arc<ToolReplay>) {
        if self
            .replays
            .get(key)
            .is_some_and(|current| Arc::ptr_eq(current, replay))
        {
            self.replays.remove(key);
        }
    }
}

/// 每个应用独立持有工具归属和已受理的响应。
pub struct GeminiService {
    registry: Mutex<ToolRegistry>,
    replay_budget: Arc<Semaphore>,
}

impl Default for GeminiService {
    fn default() -> Self {
        Self {
            registry: Mutex::default(),
            replay_budget: Arc::new(Semaphore::new(FRAME_LIMIT)),
        }
    }
}

impl GeminiService {
    fn registry(&self) -> MutexGuard<'_, ToolRegistry> {
        self.registry
            .lock()
            .unwrap_or_else(|error| error.into_inner())
    }

    /// 清理切换时仍保留在网关的工具归属。私有流的取消信号独立释放发送端作业。
    /// @return 已登记的工具归属在当前进程中释放。
    pub(crate) fn release_tools_for_cutover(&self) {
        let mut registry = self.registry();
        registry.turns.retain(|_, turn| {
            !turn
                .cutover
                .as_ref()
                .is_some_and(InferenceCutover::is_cancelled)
        });
        registry.replays.retain(|_, replay| {
            if replay
                .cutover
                .as_ref()
                .is_some_and(InferenceCutover::is_cancelled)
            {
                replay.expire();
                return false;
            }
            true
        });
    }
}

fn invalid(message: &str) -> AppError {
    AppError::BadRequest(message.into())
}

fn gemini_error(error: AppError) -> Response {
    let (status, body) = gemini_error_body(error);
    (status, Json(body)).into_response()
}

/// 普通响应与 SSE 错误帧使用同一个公开错误合同。@param error 已分类错误。@return HTTP 状态及安全正文。
fn gemini_error_body(error: AppError) -> (StatusCode, Value) {
    if let AppError::AgyInput {
        reason,
        message,
        field,
    } = &error
    {
        let message = match field {
            Some(field) => format!("{message}（{field}，{reason}）"),
            None => format!("{message}（{reason}）"),
        };
        let mut details = vec![json!({"@type":"type.googleapis.com/google.rpc.ErrorInfo",
            "reason":reason,"domain":"flower2api"})];
        if let Some(field) = field {
            details.push(json!({"@type":"type.googleapis.com/google.rpc.BadRequest",
                "fieldViolations":[{"field":field,"description":message}]}));
        }
        return (
            StatusCode::BAD_REQUEST,
            json!({"error":{"code":400,"status":"INVALID_ARGUMENT","message":message,"details":details}}),
        );
    }
    let (code, status, message) = match error {
        AppError::Unauthorized => (
            StatusCode::UNAUTHORIZED,
            "UNAUTHENTICATED",
            "API令牌无效".to_string(),
        ),
        AppError::BadRequest(message) => (StatusCode::BAD_REQUEST, "INVALID_ARGUMENT", message),
        AppError::NotFound => (
            StatusCode::NOT_FOUND,
            "NOT_FOUND",
            "模型不存在。请通过 GET /v1beta/models 查看可用模型".into(),
        ),
        AppError::TooManyRequests(_) | AppError::AdmissionLimited { .. } => (
            StatusCode::TOO_MANY_REQUESTS,
            "RESOURCE_EXHAUSTED",
            "账号当前容量不足".into(),
        ),
        error @ AppError::AgyUpstreamQuota => (
            StatusCode::TOO_MANY_REQUESTS,
            "RESOURCE_EXHAUSTED",
            error.to_string(),
        ),
        error @ AppError::AgyToolTurnFailed => {
            (StatusCode::BAD_GATEWAY, "UNAVAILABLE", error.to_string())
        }
        error @ AppError::AgyToolReplayUnavailable => (
            StatusCode::SERVICE_UNAVAILABLE,
            "UNAVAILABLE",
            error.to_string(),
        ),
        error @ AppError::AgyControl(code) => {
            let status = match code {
                StatusCode::BAD_REQUEST => "INVALID_ARGUMENT",
                StatusCode::UNAUTHORIZED => "UNAUTHENTICATED",
                StatusCode::FORBIDDEN => "PERMISSION_DENIED",
                StatusCode::NOT_FOUND => "NOT_FOUND",
                StatusCode::CONFLICT => "ABORTED",
                StatusCode::PRECONDITION_FAILED => "FAILED_PRECONDITION",
                StatusCode::PAYLOAD_TOO_LARGE | StatusCode::TOO_MANY_REQUESTS => {
                    "RESOURCE_EXHAUSTED"
                }
                StatusCode::NOT_IMPLEMENTED => "UNIMPLEMENTED",
                StatusCode::BAD_GATEWAY | StatusCode::SERVICE_UNAVAILABLE => "UNAVAILABLE",
                StatusCode::GATEWAY_TIMEOUT => "DEADLINE_EXCEEDED",
                code if code.is_server_error() => "INTERNAL",
                _ => "UNKNOWN",
            };
            (code, status, error.to_string())
        }
        _ => (
            StatusCode::SERVICE_UNAVAILABLE,
            "UNAVAILABLE",
            "AGY请求失败，请查询原请求状态".into(),
        ),
    };
    (
        code,
        json!({"error":{"code":code.as_u16(),"status":status,"message":message}}),
    )
}

/// 仅在Gemini入口解析四种令牌来源，拒绝冲突和重复查询密钥。@param headers 原头。@param query 原查询。@return 唯一密钥。
pub fn api_key(headers: &HeaderMap, query: Option<&str>) -> Result<String, AppError> {
    let mut keys = Vec::new();
    for name in ["x-api-key", "x-goog-api-key", "authorization"] {
        for value in headers.get_all(name) {
            let value = value.to_str().map_err(|_| AppError::Unauthorized)?;
            let key = if name == "authorization" {
                value
                    .strip_prefix("Bearer ")
                    .ok_or(AppError::Unauthorized)?
            } else {
                value
            };
            if key.is_empty() {
                return Err(AppError::Unauthorized);
            }
            keys.push(key.to_string());
        }
    }
    let query: Vec<(String, String)> =
        reqwest::Url::parse(&format!("http://local/?{}", query.unwrap_or_default()))
            .map_err(|_| invalid("查询参数无效"))?
            .query_pairs()
            .map(|(key, value)| (key.into_owned(), value.into_owned()))
            .collect();
    let query_keys: Vec<_> = query.iter().filter(|(key, _)| key == "key").collect();
    if query_keys.len() > 1 {
        return Err(AppError::Unauthorized);
    }
    for (_, value) in query_keys {
        keys.push(value.clone());
    }
    let key = keys
        .first()
        .filter(|key| !key.is_empty())
        .ok_or(AppError::Unauthorized)?;
    if keys.iter().any(|value| value != key) {
        return Err(AppError::Unauthorized);
    }
    Ok(key.clone())
}

async fn authenticate(
    state: &AppState,
    headers: &HeaderMap,
    query: Option<&str>,
) -> Result<ApiToken, AppError> {
    let key = api_key(headers, query)?;
    let token = state
        .token_store
        .get_by_token(&key)
        .await?
        .ok_or(AppError::Unauthorized)?;
    if token.status != ApiTokenStatus::Active {
        return Err(AppError::Unauthorized);
    }
    Ok(token)
}

/// 按当前令牌可见的真实目录聚合 Gemini 档位。@param state 应用。@param request 原请求。@return 可请求的模型目录。
pub async fn models(State(state): State<AppState>, request: Request) -> Response {
    let (parts, _) = request.into_parts();
    let result = async {
        let token = authenticate(&state, &parts.headers, parts.uri.query()).await?;
        let accounts = state
            .account_svc
            .agy_candidates(&token, &[], &BTreeSet::new())
            .await?;
        let mut names = BTreeSet::new();
        for (_, account) in &accounts {
            if let Some(mapping) = account.usage_data["capabilities"]["model_mappings"].as_object()
            {
                for name in mapping.keys() {
                    if AccountService::agy_model(account, name).is_some() {
                        names.insert(gemini_variant_base(name).unwrap_or(name));
                    }
                }
            }
        }
        let models: Vec<_> = names
            .into_iter()
            .map(|name| {
                json!({
                    "name": format!("models/{name}"),
                    "displayName": name,
                    "version": "1.5.9",
                    "supportedGenerationMethods": ["generateContent", "streamGenerateContent"],
                })
            })
            .collect();
        Ok::<_, AppError>(Json(json!({"models": models})).into_response())
    }
    .await;
    result.unwrap_or_else(gemini_error)
}

const GEMINI_DEFAULT_TIERS: [&str; 5] = ["high", "medium", "low", "tiered", "xhigh"];

fn gemini_has_tier(model: &str) -> bool {
    model
        .rsplit_once('-')
        .is_some_and(|(_, tail)| GEMINI_DEFAULT_TIERS.contains(&tail))
}

fn gemini_variant_base(model: &str) -> Option<&str> {
    let (base, tier) = model.rsplit_once('-')?;
    let name = base.strip_prefix("gemini-")?;
    // 只公开选号时能够还原的基础名称，避免合并已经带档位的名称。
    (!name.is_empty() && GEMINI_DEFAULT_TIERS.contains(&tier) && !gemini_has_tier(base))
        .then_some(base)
}

fn gemini_thinking_tier(config: &Value) -> Result<Option<&'static str>, AppError> {
    let config = config
        .as_object()
        .ok_or_else(|| invalid("Gemini thinkingConfig 必须为对象"))?;
    if config.keys().any(|key| {
        !matches!(
            key.as_str(),
            "thinkingLevel" | "thinkingBudget" | "includeThoughts"
        )
    }) || config
        .get("includeThoughts")
        .is_some_and(|value| !value.is_boolean())
    {
        return Err(invalid("Gemini thinkingConfig 包含无效字段"));
    }
    let level = config
        .get("thinkingLevel")
        .map(
            |value| match value.as_str().map(str::to_ascii_lowercase).as_deref() {
                Some("minimal" | "low") => Ok("low"),
                Some("medium") => Ok("medium"),
                Some("high") => Ok("high"),
                Some("xhigh") => Ok("xhigh"),
                _ => Err(invalid("Gemini thinkingLevel 无效")),
            },
        )
        .transpose()?;
    let budget_tier = config
        .get("thinkingBudget")
        .map(|value| {
            // 沿用 Sub2API 的预算区间，只选择档位，原生执行仍由目录型号决定。
            match value.as_i64() {
                Some(-1 | 8193..) => Ok("high"),
                Some(0..=1024) => Ok("low"),
                Some(1025..=8192) => Ok("medium"),
                _ => Err(invalid("Gemini thinkingBudget 无效")),
            }
        })
        .transpose()?;
    Ok(level.or(budget_tier))
}

fn gemini_model_names(model: &str, tier: Option<&str>) -> Vec<String> {
    if !model.starts_with("gemini-") || gemini_has_tier(model) {
        return vec![model.to_string()];
    }
    if let Some(tier) = tier {
        return vec![format!("{model}-{tier}"), model.to_string()];
    }
    // 未指定档位时优先实际存在的同名型号，再按默认顺序找变体。
    let mut names = vec![model.to_string()];
    names.extend(
        GEMINI_DEFAULT_TIERS
            .iter()
            .map(|tier| format!("{model}-{tier}")),
    );
    names
}

fn has_tool_result(body: &Value) -> bool {
    body["contents"].as_array().is_some_and(|contents| {
        contents.iter().any(|content| {
            content["parts"].as_array().is_some_and(|parts| {
                parts
                    .iter()
                    .any(|part| part.get("functionResponse").is_some())
            })
        })
    })
}

fn requested_media(body: &Value) -> Result<BTreeSet<&str>, AppError> {
    let supported = [
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/tiff",
        "image/avif",
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/ogg",
        "audio/flac",
        "video/mp4",
        "video/webm",
        "application/pdf",
    ];
    let mut media = BTreeSet::new();
    for (index, content) in body["contents"]
        .as_array()
        .into_iter()
        .flatten()
        .enumerate()
    {
        for (part_index, part) in content["parts"]
            .as_array()
            .into_iter()
            .flatten()
            .enumerate()
        {
            for name in ["inlineData", "inline_data"] {
                if let Some(value) = part.get(name) {
                    let mime = value
                        .get("mimeType")
                        .or_else(|| value.get("mime_type"))
                        .and_then(Value::as_str);
                    let field = Some(format!("contents[{index}].parts[{part_index}].{name}"));
                    let Some(mime) = mime else {
                        return Err(AppError::AgyInput {
                            reason: "AGY_INVALID_MEDIA",
                            message: "内嵌媒体缺少 MIME 类型",
                            field,
                        });
                    };
                    if !supported.contains(&mime) {
                        return Err(AppError::AgyInput {
                            reason: "AGY_UNSUPPORTED_MEDIA_TYPE",
                            message: "AGY 入口不支持该媒体类型",
                            field,
                        });
                    }
                    media.insert(mime);
                }
            }
        }
    }
    Ok(media)
}

fn matching_tool_call(calls: &[Value], response: &Value, position: usize) -> Option<usize> {
    let name = response["name"].as_str().filter(|name| !name.is_empty())?;
    let has_name = calls.iter().any(|call| call["name"] == name);
    let mut identifier = match response.get("id") {
        Some(id) => Some(id.as_str().filter(|id| !id.is_empty())?),
        None => None,
    };
    if identifier.is_none() && !has_name && calls.iter().any(|call| call["id"] == name) {
        identifier = Some(name);
    }
    let mut matches = calls.iter().enumerate().filter(|(_, call)| {
        if let Some(identifier) = identifier {
            (!has_name || call["name"] == name) && call["id"] == identifier
        } else {
            call["name"] == name
        }
    });
    let result = matches.next()?.0;
    if matches.next().is_none() {
        return Some(result);
    }
    // 中转可能删除并行工具的 ID。回填顺序只用于同名项，并且整轮调用与结果数量仍须一致。
    (identifier.is_none() && calls.get(position).is_some_and(|call| call["name"] == name))
        .then_some(position)
}

#[cfg(test)]
#[test]
fn parallel_same_name_results_use_ids_or_the_original_order() {
    let calls = [
        json!({"name": "Read", "id": "first", "args": {"path": "a.txt"}}),
        json!({"name": "Read", "id": "second", "args": {"path": "b.txt"}}),
        json!({"name": "List", "id": "third"}),
    ];
    let read = json!({"name": "Read", "response": {}});
    assert_eq!(matching_tool_call(&calls, &read, 0), Some(0));
    assert_eq!(matching_tool_call(&calls, &read, 1), Some(1));
    assert_eq!(matching_tool_call(&calls, &read, 2), None);
    let id = json!({"name": "Read", "id": "second", "response": {}});
    assert_eq!(matching_tool_call(&calls, &id, 0), Some(1));
    let wrong_id = json!({"name": "Read", "id": "third", "response": {}});
    assert_eq!(matching_tool_call(&calls, &wrong_id, 0), None);
}

fn matches_turn(turn: &ToolTurn, model: &str, body: &Value) -> bool {
    let Some(old) = turn.contents.as_array() else {
        return false;
    };
    let Some(new) = body["contents"].as_array() else {
        return false;
    };
    if turn.model.requested != model || new.len() != old.len() + 2 || new[..old.len()] != old[..] {
        return false;
    }
    let calls: Vec<_> = new[old.len()]["parts"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|part| part.get("functionCall"))
        .collect();
    if calls.len() != turn.calls.len() {
        return false;
    }
    let empty = json!({});
    if new[old.len()]["role"] != "model"
        || new[old.len() + 1]
            .get("role")
            .is_some_and(|role| role != "user")
    {
        return false;
    }
    let responses: Vec<_> = new[old.len() + 1]["parts"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|part| part.get("functionResponse"))
        .collect();
    if responses.len() != turn.calls.len()
        || responses
            .iter()
            .any(|response| !response["response"].is_object())
    {
        return false;
    }
    let matched: Option<BTreeSet<_>> = responses
        .iter()
        .enumerate()
        .map(|(position, response)| matching_tool_call(&turn.calls, response, position))
        .collect();
    if matched.is_none_or(|indices| indices.len() != turn.calls.len()) {
        return false;
    }
    calls.iter().zip(&turn.calls).all(|(call, expected)| {
        call["name"] == expected["name"]
            && call.get("args").unwrap_or(&empty) == expected.get("args").unwrap_or(&empty)
            && call
                .get("id")
                .is_none_or(|id| Some(id) == expected.get("id"))
    })
}

/// 用已校验工具轮的真实 ID 修正原生历史。@param turn 原工具归属。@param body 已匹配的客户端正文。@return 有变更时的原生历史。
fn runtime_tool_contents(turn: &ToolTurn, body: &Value) -> Option<Value> {
    let contents = body["contents"].as_array()?;
    let start = contents.len().checked_sub(2)?;
    let aliases: Vec<_> = contents[start + 1]["parts"]
        .as_array()?
        .iter()
        .enumerate()
        .filter_map(|(part_index, part)| {
            let response = part.get("functionResponse")?;
            let alias = response["name"].as_str()?;
            if response.get("id").is_some() || turn.calls.iter().any(|call| call["name"] == alias) {
                return None;
            }
            let call_index = matching_tool_call(&turn.calls, response, 0)?;
            Some((part_index, call_index))
        })
        .collect();
    if aliases.is_empty() && turn.runtime_contents.is_none() {
        return None;
    }

    // 已确认的原生前缀跨轮复用。客户端归属和重试回执继续使用原始内容。
    let mut runtime = turn
        .runtime_contents
        .as_ref()
        .unwrap_or(&turn.contents)
        .clone();
    let mut model = contents[start].clone();
    let mut user = contents[start + 1].clone();
    let mut calls: Vec<_> = model["parts"]
        .as_array_mut()?
        .iter_mut()
        .filter_map(|part| part.get_mut("functionCall"))
        .collect();
    for (part_index, call_index) in aliases {
        let expected = &turn.calls[call_index];
        calls[call_index]["id"] = expected["id"].clone();
        let response = &mut user["parts"][part_index]["functionResponse"];
        response["id"] = expected["id"].clone();
        response["name"] = expected["name"].clone();
    }
    runtime.as_array_mut()?.extend([model, user]);
    Some(runtime)
}

impl GeminiService {
    fn continuation(
        self: &Arc<Self>,
        token: &ApiToken,
        model: &str,
        body: &Value,
        request_id: &str,
        deadline: Instant,
        cutover: Option<InferenceCutover>,
    ) -> Result<Option<Continuation>, AppError> {
        let Some((index, _)) = body["contents"]
            .as_array()
            .and_then(|contents| contents.last().map(|content| (contents.len() - 1, content)))
            .filter(|(_, content)| {
                content["parts"].as_array().is_some_and(|parts| {
                    parts
                        .iter()
                        .any(|part| part.get("functionResponse").is_some())
                })
            })
        else {
            return Ok(None);
        };
        let replay_key = ReplayKey::new(token.id, model, body)?;
        let mut registry = self.registry();
        let allowed = token.allowed_account_ids();
        let blocked = token.blocked_account_ids();
        let eligible = |account_id| {
            !blocked.contains(&account_id) && (allowed.is_empty() || allowed.contains(&account_id))
        };
        let matches: Vec<_> = registry
            .turns
            .iter()
            .filter(|(_, turn)| {
                turn.token_id == token.id
                    && eligible(turn.account.id)
                    && matches_turn(turn, model, body)
            })
            .map(|(key, _)| key.clone())
            .collect();
        let mismatch = || AppError::AgyInput {
            reason: "AGY_TOOL_RESULT_MISMATCH",
            message: "工具结果缺少唯一原请求归属",
            field: Some(format!("contents[{index}]")),
        };
        if let Some(replay) = registry
            .replays
            .get(&replay_key)
            .filter(|entry| entry.deadline > Instant::now())
        {
            if !eligible(replay.account_id)
                || matches.iter().any(|key| key != &replay.previous_turn)
            {
                return Err(mismatch());
            }
            return Ok(Some(Continuation::Replay(replay.clone())));
        }
        if matches.len() != 1 {
            return Err(mismatch());
        }
        let turn = registry
            .turns
            .get_mut(&matches[0])
            .ok_or_else(|| invalid("工具轮已结束"))?;
        if turn.claimed || turn.deadline <= Instant::now() {
            return Err(invalid("工具轮已领取或到期"));
        }
        if turn
            .receipt_body
            .as_ref()
            .is_some_and(|received| received != body)
        {
            return Err(invalid("工具回填与已确认结果不符"));
        }
        turn.claimed = true;
        turn.retained = true;
        let replay = Arc::new(ToolReplay::new(
            turn.account.id,
            request_id.to_owned(),
            matches[0].clone(),
            deadline,
            cutover,
            self.replay_budget.clone(),
        ));
        let continuation = Continuation::Generate(
            turn.account.clone(),
            turn.admission.clone(),
            ContinuationClaim {
                service: self.clone(),
                key: Some(matches[0].clone()),
                resolved_model: turn.model.resolved.clone(),
                runtime_contents: runtime_tool_contents(turn, body),
                replay_key: replay_key.clone(),
                replay: replay.clone(),
            },
        );
        registry.replays.insert(replay_key, replay);
        Ok(Some(continuation))
    }
}

/// 处理Gemini生成或SSE，许可保留到原生终态。@param state 应用。@param action 模型及动作。@param request 已限定路由。@return Gemini响应。
pub async fn generate(
    State(state): State<AppState>,
    Path(action): Path<String>,
    request: Request,
) -> Response {
    let token = match authenticate(&state, request.headers(), request.uri().query()).await {
        Ok(token) => token,
        Err(error) => return gemini_error(error),
    };
    let config = state.gateway_svc.request_diagnostics_config().await;
    CURRENT_LOG_MODE
        .scope(config.mode, async move {
            let trace = state
                .gateway_svc
                .diagnostics_store()
                .map(|store| TraceContext::for_protocol(store.clone(), "antigravity", "gemini"));
            if let Some(trace) = trace.as_ref() {
                trace.remember_ingress(
                    request.headers(),
                    &token.token,
                    config.full_rejected_ingress,
                );
            }
            let guard = trace
                .as_ref()
                .map(|trace| RequestTraceGuard::new(trace.clone()));
            let future =
                generate_inner(state, action, request, token, config.full_rejected_ingress);
            let result = if let Some(trace) = trace {
                CURRENT_TRACE.scope(trace, future).await
            } else {
                future.await
            };
            let response = match result {
                Ok(response) => response,
                Err(error) => {
                    if let Some(guard) = guard.as_ref() {
                        guard.error(&error);
                    }
                    gemini_error(error)
                }
            };
            if let Some(guard) = guard {
                guard.wrap(response)
            } else {
                response
            }
        })
        .await
}

async fn generate_inner(
    state: AppState,
    action: String,
    request: Request,
    token: ApiToken,
    full_egress: bool,
) -> Result<Response, AppError> {
    let started = Instant::now();
    let cutover = request.extensions().get::<InferenceCutover>().cloned();
    diagnostics::request_context("antigravity", "gemini", None);
    let (model, action) = action
        .rsplit_once(':')
        .ok_or_else(|| invalid("Gemini动作无效"))?;
    if model.is_empty()
        || model.len() > 128
        || !model
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"-_.".contains(&byte))
    {
        return Err(invalid("模型名称无效"));
    }
    let streaming = match action {
        "generateContent" => false,
        "streamGenerateContent" => true,
        _ => return Err(AppError::NotFound),
    };
    diagnostics::request_context("antigravity", "gemini", Some(model));
    let ingress_headers = request
        .headers()
        .iter()
        .filter_map(|(name, value)| {
            value
                .to_str()
                .ok()
                .map(|value| (name.as_str().to_string(), value.to_string()))
        })
        .collect::<Vec<_>>();
    let raw = axum::body::to_bytes(request.into_body(), BODY_LIMIT)
        .await
        .map_err(|_| invalid("Gemini正文超过上限"))?;
    diagnostics::remember_ingress_body(&raw);
    let mut body: Value =
        serde_json::from_slice(&raw).map_err(|_| invalid("Gemini正文必须为JSON"))?;
    if !body.is_object() || !body["contents"].is_array() {
        return Err(invalid("Gemini contents无效"));
    }
    let media = requested_media(&body)?;
    let thinking_config = body
        .pointer("/generationConfig/thinkingConfig")
        .filter(|_| model.starts_with("gemini-"));
    let requested_tier = thinking_config
        .map(gemini_thinking_tier)
        .transpose()?
        .flatten();
    let has_thinking_config = thinking_config.is_some();
    diagnostics::error_stage("account_selection");
    // 原工具轮按原截止完成。新一轮模型生成使用本次 HTTP 的时间预算。
    let deadline = started + Duration::from_secs(AGY_REQUEST_SECONDS as u64);
    let http_request_id =
        diagnostics::current_request_id().unwrap_or_else(|| Uuid::new_v4().to_string());
    let continuation = state.gemini_svc.continuation(
        &token,
        model,
        &body,
        &http_request_id,
        deadline,
        cutover.clone(),
    )?;
    let tool_turn = match continuation {
        Some(Continuation::Replay(replay)) => {
            let trace = diagnostics::current_trace();
            if let Some(trace) = trace.as_ref() {
                trace.agy_replayed(replay.account_id, &replay.request_id);
            }
            let stream = replay.read().inspect(move |frame| {
                if frame.is_err()
                    && let Some(trace) = trace.as_ref()
                {
                    trace.agy_replay_failed();
                }
            });
            return gemini_response(stream, replay.deadline, streaming).await;
        }
        Some(Continuation::Generate(account, admission, claim)) => {
            Some((account, admission, claim))
        }
        None => None,
    };

    let (account, admission, mut claim, resolved_model, scheduling) =
        if let Some((account, admission, claim)) = tool_turn {
            let resolved_model = claim.resolved_model.clone();
            let current = if media.is_empty() {
                account
            } else {
                state.account_svc.get_account(account.id).await?
            };
            let support = AccountService::agy_media_support(
                &current,
                &resolved_model,
                &media,
                current.agy_gif_frames_enabled,
            );
            if support != Some(true) {
                return Err(AccountService::agy_media_error(&media, support.is_none()));
            }
            let scheduling =
                state
                    .account_svc
                    .begin_agy_scheduling(token.id, &resolved_model, streaming);
            scheduling.selected(&current, None);
            (current, admission, Some(claim), resolved_model, scheduling)
        } else {
            let mut model_names = gemini_model_names(model, requested_tier);
            let accounts = state
                .account_svc
                .agy_candidates(&token, &model_names, &media)
                .await?;
            let (model_index, account, scheduling) = state
                .account_svc
                .select_agy_smart(token.id, &model_names, accounts, streaming)
                .await?;
            let queue = state
                .account_svc
                .get_or_create_queue(account.id, account.concurrency)
                .await;
            let slot = queue
                .acquire(
                    deadline.saturating_duration_since(Instant::now()),
                    DEFAULT_REQUEST_SLOT_UNITS,
                )
                .await
                .map_err(|_| AppError::AdmissionLimited { retry_after: 1 })?;
            let admission = Arc::new(Admission {
                _slot: slot,
                credentials: state.account_svc.upstream_activity(account.id).await?,
                _maintenance: system_update::admission()?,
            });
            (
                account,
                admission,
                None,
                model_names.swap_remove(model_index),
                scheduling,
            )
        };
    scheduling.phase(RequestPhase::Preparing);
    let model = RoutedModel {
        requested: model.to_string(),
        resolved: resolved_model,
    };
    let gif_frames = account.agy_gif_frames_enabled && media.contains("image/gif");
    diagnostics::selected_account(account.id);
    // 原工具收尾复用原许可和原进程；新AT发布单独检查ready，待对账期间也能完成旧工具。
    if let Some(claim) = &claim {
        diagnostics::error_stage("tool_continuation");
        claim.finish(token.id, &body, deadline, gif_frames).await?;
    }
    diagnostics::error_stage("credentials");
    let snapshot = timeout_at(
        deadline,
        state.account_svc.resolve_agy_access_with_admission(
            account.id,
            false,
            Some(&admission.credentials),
        ),
    )
    .await
    .map_err(|_| AppError::ServiceUnavailable("AGY凭据等待超时".into()))??;
    let current = state.account_svc.get_account(account.id).await?;
    let media_support =
        AccountService::agy_media_support(&current, &model.resolved, &media, gif_frames);
    if media_support != Some(true) {
        return Err(AccountService::agy_media_error(
            &media,
            media_support.is_none(),
        ));
    }
    let capture_requested = diagnostics::current_log_mode() == RequestLogMode::Debug;
    let full_egress = capture_requested && full_egress;
    let ingress = native_capture::ingress(
        diagnostics::current_log_mode(),
        &ingress_headers,
        &raw,
        &body,
        &snapshot.access_token,
    );
    // 发送器直接执行已选的目录型号。只在原始入站采集后消费路由字段，兼容现有运行镜像。
    if has_thinking_config {
        if let Some(config) = body
            .get_mut("generationConfig")
            .and_then(Value::as_object_mut)
        {
            config.remove("thinkingConfig");
        }
    }
    let system_prompt_policy =
        AgySystemPromptPolicy::new(current.agy_system_prompt_homoglyph_enabled);
    let disable_safety_filtering = current.agy_disable_safety_filtering;
    let native_model =
        AccountService::agy_model(&current, &model.resolved).ok_or(AppError::NotFound)?;
    diagnostics::error_stage("runtime_prepare");
    let transport = Arc::new(
        timeout_at(
            deadline,
            runtime_transport::prepare(
                &current,
                deadline.saturating_duration_since(Instant::now()),
            ),
        )
        .await
        .map_err(|_| AppError::ServiceUnavailable("AGY环境准备超时".into()))??,
    );
    state
        .account_svc
        .acquire_account_rpm(&current, false, "")
        .await?;
    let request_id = Uuid::new_v4().to_string();
    let trace = diagnostics::current_trace();
    let previous_turn = claim
        .as_ref()
        .and_then(|claim| claim.key.as_ref())
        .and_then(|key| {
            state
                .gemini_svc
                .registry()
                .turns
                .get(key)
                .map(|turn| (key.clone(), turn.previous_request_id.clone()))
        });
    let mut observation = AgyAttemptTrace::begin(
        trace.as_ref(),
        &current,
        &model.requested,
        &native_model,
        transport.execution_location(),
        snapshot.credential_generation,
        &system_prompt_policy,
        &request_id,
        &body,
        streaming,
    );
    if let Some(observer) = observation.as_mut() {
        observer.track_scheduling(scheduling.clone());
    }
    if let (Some(observer), Some((root, attempt))) = (observation.as_mut(), previous_turn) {
        observer.continuation(&root, &attempt);
    }
    let client_contents = claim
        .as_mut()
        .and_then(|claim| claim.runtime_contents.take())
        .map(|contents| replace(&mut body["contents"], contents));
    let (sender, receiver) = mpsc::channel(2);
    let mut output = GeminiOutput {
        primary: Some(sender),
        replay: claim.as_mut().and_then(ContinuationClaim::begin_submission),
    };
    let service = state.gemini_svc.clone();
    tokio::spawn(async move {
        let closing = cutover.clone();
        let result = async {
            let upstream = tokio::select! {
                biased;
                _ = output.closed() => {
                    if let Some(observer) = observation.as_mut() {
                        observer.finish("cancelled", Some("downstream_body"));
                    }
                    return Err(AppError::BadGateway("客户端已取消".into()));
                }
                upstream = transport.send_agy(
                    &request_id, token.id, snapshot.clone(), &model.resolved, native_model.clone(),
                    body.clone(), system_prompt_policy.clone(), deadline, capture_requested,
                    full_egress, gif_frames, disable_safety_filtering,
                ) => upstream,
            };
            let upstream = match upstream {
                Ok(response) => response,
                Err(error) => {
                    if let Some(observer) = observation.as_mut() {
                        observer.finish("transport_error", Some("transport"));
                    }
                    return Err(error);
                }
            };
            if let Some(observer) = observation.as_mut() {
                observer.headers(upstream.status().as_u16());
            }
            if !upstream.status().is_success() {
                if let Some(observer) = observation.as_mut() {
                    observer.finish("upstream_error", Some("sender_rejection"));
                }
                return Err(AppError::ServiceUnavailable("AGY账号发送器拒绝请求".into()));
            }
            drive(
                upstream,
                service.clone(),
                &http_request_id,
                request_id,
                trace,
                observation,
                streaming,
                capture_requested,
                full_egress,
                ingress,
                token.id,
                current,
                model,
                body,
                client_contents,
                deadline,
                admission,
                transport,
                state.account_svc,
                snapshot,
                native_model,
                system_prompt_policy,
                gif_frames,
                disable_safety_filtering,
                scheduling,
                cutover,
                &mut output,
            )
            .await
        }
        .await;
        if let Err(error) = result {
            output.fail(error).await;
        }
        let mut registry = service.registry();
        if closing.as_ref().is_some_and(InferenceCutover::is_cancelled)
            || registry
                .turns
                .get(&http_request_id)
                .is_none_or(|turn| !turn.retained)
        {
            registry.turns.remove(&http_request_id);
        }
    });
    gemini_response(ReceiverStream::new(receiver), deadline, streaming).await
}

/// 首发与重读使用相同的公开 SSE 和 JSON 聚合。
/// @param frames 响应帧。@param deadline 原截止。@param streaming 是否返回事件流。
/// @return Gemini HTTP 响应或首帧前错误。
async fn gemini_response(
    frames: impl Stream<Item = Result<Value, AppError>> + Send + 'static,
    deadline: Instant,
    streaming: bool,
) -> Result<Response, AppError> {
    let mut frames = Box::pin(frames);
    let first = timeout_at(deadline, frames.next())
        .await
        .map_err(|_| AppError::ServiceUnavailable("AGY响应超时".into()))?
        .ok_or_else(|| AppError::BadGateway("AGY响应提前结束".into()))??;
    if streaming {
        let stream = futures_util::stream::once(async { Ok(first) })
            .chain(frames)
            .map(|event| {
                let value = match event {
                    Ok(value) => value,
                    Err(error @ (AppError::AgyUpstreamQuota | AppError::AgyControl(_) | AppError::AgyToolReplayUnavailable)) => gemini_error_body(error).1,
                    Err(_) => json!({"error":{"code":503,"status":"UNAVAILABLE","message":"AGY原生请求失败"}}),
                };
                Ok::<Bytes, IoError>(Bytes::from(format!("data: {value}\n\n")))
            });
        return Ok((
            [
                ("content-type", "text/event-stream"),
                ("cache-control", "no-cache"),
            ],
            Body::from_stream(stream),
        )
            .into_response());
    }
    let mut output = Value::Null;
    aggregate(&mut output, first)?;
    let mut size = 0;
    while let Some(event) = timeout_at(deadline, frames.next())
        .await
        .map_err(|_| AppError::BadGateway("AGY响应超时".into()))?
    {
        let event = event?;
        size += serde_json::to_vec(&event)
            .map_err(|_| invalid("Gemini响应无效"))?
            .len();
        if size > FRAME_LIMIT {
            return Err(AppError::BadGateway("AGY响应超过聚合上限".into()));
        }
        aggregate(&mut output, event)?;
    }
    Ok(Json(output).into_response())
}

struct EventReader {
    stream: Pin<Box<dyn Stream<Item = Result<Bytes, reqwest::Error>> + Send>>,
    pending: Vec<u8>,
    deadline: Instant,
}

impl EventReader {
    async fn next(&mut self) -> Result<Option<Value>, AppError> {
        loop {
            if let Some(index) = self.pending.iter().position(|byte| *byte == b'\n') {
                let line: Vec<_> = self.pending.drain(..=index).collect();
                return serde_json::from_slice(&line)
                    .map(Some)
                    .map_err(|_| AppError::BadGateway("AGY事件格式错误".into()));
            }
            match timeout_at(self.deadline, self.stream.next())
                .await
                .map_err(|_| AppError::BadGateway("AGY原截止到期".into()))?
            {
                Some(Ok(bytes)) if self.pending.len() + bytes.len() <= FRAME_LIMIT => {
                    self.pending.extend_from_slice(&bytes)
                }
                None if self.pending.is_empty() => return Ok(None),
                _ => return Err(AppError::BadGateway("AGY事件流异常".into())),
            }
        }
    }
}

/// 将私有工具等待回执换算为本机截止。@param event 原生完成事件。@param request_deadline 旧发送器使用的生成截止。@return 工具等待截止。
fn tool_wait_deadline(event: &Value, request_deadline: Instant) -> Result<Instant, AppError> {
    let Some(expires) = event.get("tool_wait_expires_at_ms") else {
        return Ok(request_deadline);
    };
    let now = Instant::now();
    let unix_ms = runtime_transport::now_ms();
    let remaining = expires
        .as_u64()
        .and_then(|value| value.checked_sub(unix_ms))
        .filter(|value| *value > 0)
        .ok_or_else(|| AppError::BadGateway("AGY工具等待回执无效或已到期".into()))?;
    // 远程发送器的时钟偏差不能扩大本地保留窗口。
    Ok(now + Duration::from_millis(remaining).min(AGY_TOOL_WAIT_LIMIT))
}

/// 首笔调用保持原通道背压，重试连接独立读取同一份有界缓存。
struct GeminiOutput {
    primary: Option<mpsc::Sender<Result<Value, AppError>>>,
    replay: Option<Arc<ToolReplay>>,
}

impl GeminiOutput {
    async fn closed(&self) {
        match &self.primary {
            Some(primary) => primary.closed().await,
            None => std::future::pending().await,
        }
        if let Some(replay) = &self.replay {
            replay.readers_closed().await;
        }
    }

    async fn send(&self, frame: Value, deadline: Instant) -> Result<(), AppError> {
        let Some(primary) = &self.primary else {
            return Ok(());
        };
        let reader_present = self.replay.as_ref().is_some_and(|replay| {
            let reader_present = replay.has_readers();
            replay.push(&frame);
            reader_present
        });
        let sent = timeout_at(deadline, primary.send(Ok(frame)))
            .await
            .map_err(|_| AppError::BadGateway("客户端背压超时".into()))?;
        // 重试方拿到工具帧就可以关闭 SSE，保留在发布该帧时已存在的读者事实。
        if sent.is_ok()
            || reader_present
            || self
                .replay
                .as_ref()
                .is_some_and(|replay| replay.has_readers())
        {
            return Ok(());
        }
        Err(AppError::BadGateway("客户端已取消".into()))
    }

    fn finish(&mut self, terminal: Result<(), AppError>) {
        self.primary.take();
        if let Some(replay) = self.replay.take() {
            replay.finish(terminal);
        }
    }

    async fn fail(&mut self, error: AppError) {
        if let Some(replay) = self.replay.take() {
            replay.finish(Err(error.clone()));
        }
        if let Some(primary) = self.primary.take() {
            let _ = primary.send(Err(error)).await;
        }
    }
}

impl Drop for GeminiOutput {
    fn drop(&mut self) {
        self.finish(Err(AppError::AgyToolReplayUnavailable));
    }
}

#[cfg(test)]
#[tokio::test]
async fn replay_reader_keeps_the_original_output_alive_after_disconnect() {
    let deadline = Instant::now() + Duration::from_secs(10);
    let replay = Arc::new(ToolReplay::new(
        1,
        "request".into(),
        "previous".into(),
        deadline,
        None,
        Arc::new(Semaphore::new(8192)),
    ));
    let (primary, receiver) = mpsc::channel(2);
    let output = GeminiOutput {
        primary: Some(primary),
        replay: Some(replay.clone()),
    };
    let mut reader = Box::pin(replay.read());
    drop(receiver);
    assert!(futures_util::poll!(Box::pin(output.closed())).is_pending());
    output
        .send(json!({"text": "仍在生成"}), deadline)
        .await
        .unwrap();
    assert_eq!(
        reader.next().await.unwrap().unwrap(),
        json!({"text": "仍在生成"})
    );
    drop(reader);
    output.closed().await;
}

#[allow(clippy::too_many_arguments)]
async fn drive(
    upstream: reqwest::Response,
    service: Arc<GeminiService>,
    request_id: &str,
    initial_attempt_id: String,
    trace: Option<TraceContext>,
    mut observation: Option<AgyAttemptTrace>,
    streaming: bool,
    capture_requested: bool,
    full_egress: bool,
    ingress: Option<Value>,
    token_id: i64,
    account: Account,
    model: RoutedModel,
    body: Value,
    mut client_contents: Option<Value>,
    deadline: Instant,
    admission: Arc<Admission>,
    transport: Arc<PreparedTransport>,
    account_service: Arc<AccountService>,
    mut snapshot: AgyAccessSnapshot,
    native_model: AgyModelId,
    system_prompt_policy: AgySystemPromptPolicy,
    gif_frames: bool,
    disable_safety_filtering: bool,
    scheduling: SchedulingRequest,
    mut cutover: Option<InferenceCutover>,
    output: &mut GeminiOutput,
) -> Result<(), AppError> {
    let mut reader = EventReader {
        stream: Box::pin(upstream.bytes_stream()),
        pending: Vec::new(),
        deadline,
    };
    let mut calls = Vec::new();
    let mut pending_tool_frames = Vec::new();
    let mut pending_tool_bytes = 0;
    let mut completed = false;
    let mut attempt_id = initial_attempt_id;
    let mut attempted_recovery = false;
    let mut forwarded = 0;
    let mut policy_acknowledged = !system_prompt_policy.enabled;
    let mut ingress_sent = false;
    let mut cutting_over = false;
    loop {
        let event = tokio::select! {
            biased;
            _ = async {
                match cutover.as_mut() {
                    Some(signal) => signal.cancelled().await,
                    None => std::future::pending().await,
                }
            }, if !cutting_over => {
                if let Some(observer) = observation.as_mut() {
                    observer.finish("cancelled", Some("system_update"));
                }
                output.finish(Err(AppError::AgyToolReplayUnavailable));
                // 先断开客户端。保留原私有流核对 job_finalized，给宿主最后的状态核对留出时间。
                reader.deadline = Instant::now() + Duration::from_secs(25);
                transport.cancel_agy(&attempt_id, token_id, reader.deadline).await?;
                cutting_over = true;
                continue;
            }
            _ = output.closed() => {
                if let Some(observer) = observation.as_mut() {
                    observer.finish("cancelled", Some("downstream_body"));
                }
                return Err(AppError::BadGateway("客户端已取消".into()));
            }
            event = reader.next() => event?,
        };
        let Some(event) = event else {
            break;
        };
        if event["request_id"] != attempt_id || event["account_id"].as_i64() != Some(account.id) {
            return Err(AppError::BadGateway("AGY事件归属错误".into()));
        }
        if event["type"] == "job_finalized" {
            if let Some(observer) = observation.as_mut() {
                observer.finalized(event["status"].as_str().unwrap_or("error"));
            }
            if !completed && !cutting_over {
                return Err(AppError::BadGateway("AGY缺少原生终态".into()));
            }
            return Ok(());
        }
        if cutting_over {
            if event["type"] == "native_event"
                && event["event"]["type"] == "tool_turn_finalized"
                && let Some(observer) = observation.as_mut()
            {
                observer.tool_finalized(event["event"]["status"].as_str().unwrap_or("error"));
            }
            continue;
        }
        if event["type"] == "rejected" {
            if event["code"] == "stale_credential_generation" {
                return Err(AppError::ServiceUnavailable(
                    "AGY凭据代次已更新，请重新请求".into(),
                ));
            }
            return Err(invalid("AGY请求结构被拒绝"));
        }
        if event["type"] == "error" {
            return Err(AppError::BadGateway("AGY原生执行失败".into()));
        }
        if event["type"] != "native_event" {
            continue;
        }
        let native = &event["event"];
        if let Some(observer) = observation.as_mut() {
            observer.native(native, &event);
        }
        if !ingress_sent && native["capture_status"] == "queued" {
            if let (Some(ingress), Some(generation)) =
                (ingress.as_ref(), event["environment_generation"].as_u64())
            {
                runtime_bridge::publish_agy_ingress(
                    account.id,
                    &attempt_id,
                    generation,
                    transport
                        .execution_location()
                        .is_some_and(|location| location.assignment_revision.is_some()),
                    ingress.clone(),
                );
                ingress_sent = true;
            }
        }
        tracing::info!(
            platform = "antigravity",
            account_id = account.id,
            request_id,
            attempt_id,
            model = model.requested.as_str(),
            resolved_model = model.resolved.as_str(),
            credential_generation = event["credential_generation"].as_i64(),
            environment_id = event["environment_id"].as_str(),
            environment_generation = event["environment_generation"].as_u64(),
            source_sha256 = AGY_SOURCE_SHA256,
            worker_id = native["worker_id"].as_str(),
            worker_generation = native["generation"].as_str(),
            request_seq = native["request_seq"].as_u64(),
            conversation_id = native["native_cascade_id"].as_str(),
            trajectory_id = native["native_trajectory_id"].as_str(),
            tool_call_id = native["tool_call_id"].as_str(),
            tool_execution_id = native["tool_execution_id"].as_str(),
            event_type = native["type"].as_str(),
            native_model_calls = native["native_model_calls"].as_u64(),
            system_prompt_requested = system_prompt_policy.enabled,
            system_prompt_rule = system_prompt_policy.rule_version.as_str(),
            system_prompt_source = native["system_prompt_policy"]["source"].as_str(),
            system_prompt_changed = native["system_prompt_policy"]["changed"].as_bool(),
            system_prompt_replaced = native["system_prompt_policy"]["replaced_codepoints"].as_u64(),
            system_prompt_rule_sha256 = native["system_prompt_policy"]["rule_sha256"].as_str(),
            "AGY原生事件"
        );
        match native["type"].as_str() {
            Some("request_accepted") => {
                if let Some(report) = native
                    .get("system_prompt_policy")
                    .filter(|value| !value.is_null())
                {
                    if !system_prompt_policy.matches_report(report) {
                        return Err(AppError::BadGateway("AGY系统文本策略回执不符".into()));
                    }
                    policy_acknowledged = true;
                } else if system_prompt_policy.enabled {
                    return Err(AppError::BadGateway("AGY执行端缺少系统文本策略支持".into()));
                }
            }
            Some("gemini_response") => {
                if !policy_acknowledged {
                    return Err(AppError::BadGateway("AGY系统文本策略尚未确认".into()));
                }
                let raw = STANDARD
                    .decode(
                        native["data"]["data_base64"]
                            .as_str()
                            .ok_or_else(|| invalid("AGY帧缺失"))?,
                    )
                    .map_err(|_| invalid("AGY帧编码错误"))?;
                let frame: Value =
                    serde_json::from_slice(&raw).map_err(|_| invalid("AGY帧格式错误"))?;
                if let Some(observer) = observation.as_mut() {
                    observer.frame(&frame);
                }
                if frame.get("error").is_some() {
                    if frame["error"]["code"] == 429
                        && frame["error"]["status"] == "RESOURCE_EXHAUSTED"
                        && frame.get("candidates").is_none()
                        && frame.get("usageMetadata").is_none()
                    {
                        if let Some(observer) = observation.as_mut() {
                            observer.upstream_quota();
                        }
                        return Err(AppError::AgyUpstreamQuota);
                    }
                    if !verified_auth_failure(&frame)
                        || attempted_recovery
                        || completed
                        || forwarded != 0
                        || !calls.is_empty()
                        || has_tool_result(&body)
                    {
                        return Err(AppError::BadGateway("AGY上游返回错误".into()));
                    }
                    attempted_recovery = true;
                    if let Some(observer) = observation.as_mut() {
                        observer.recovery();
                    }
                    // 只有源Gemini帧的明确401可恢复；先观察原作业物理收口，再换同账号新AT。
                    let mut finalized = false;
                    while let Some(ending) = reader.next().await? {
                        if ending["request_id"] != attempt_id
                            || ending["account_id"].as_i64() != Some(account.id)
                        {
                            return Err(AppError::BadGateway("AGY恢复归属错误".into()));
                        }
                        if ending["type"] == "job_finalized" {
                            if let Some(observer) = observation.as_mut() {
                                observer.finalized(ending["status"].as_str().unwrap_or("error"));
                            }
                            finalized = true;
                            break;
                        }
                    }
                    if !finalized {
                        return Err(AppError::BadGateway("AGY原作业待对账".into()));
                    }
                    let refreshed = timeout_at(
                        deadline,
                        account_service.resolve_agy_access_with_admission(
                            account.id,
                            true,
                            Some(&admission.credentials),
                        ),
                    )
                    .await
                    .map_err(|_| AppError::ServiceUnavailable("AGY认证恢复到期".into()))??;
                    if refreshed.credential_generation <= snapshot.credential_generation
                        || refreshed.access_token == snapshot.access_token
                    {
                        return Err(AppError::ServiceUnavailable(
                            "AGY认证恢复缺少有效新代".into(),
                        ));
                    }
                    account_service
                        .acquire_account_rpm(&account, false, "")
                        .await?;
                    attempt_id = Uuid::new_v4().to_string();
                    observation = AgyAttemptTrace::begin(
                        trace.as_ref(),
                        &account,
                        &model.requested,
                        &native_model,
                        transport.execution_location(),
                        refreshed.credential_generation,
                        &system_prompt_policy,
                        &attempt_id,
                        &body,
                        streaming,
                    );
                    if let Some(observer) = observation.as_mut() {
                        observer.track_scheduling(scheduling.clone());
                    }
                    tracing::info!(
                        platform = "antigravity",
                        account_id = account.id,
                        request_id,
                        attempt_id,
                        reason = "oauth_recovery",
                        "AGY有界认证恢复"
                    );
                    let retry = transport
                        .send_agy(
                            &attempt_id,
                            token_id,
                            refreshed.clone(),
                            &model.resolved,
                            native_model.clone(),
                            body.clone(),
                            system_prompt_policy.clone(),
                            deadline,
                            capture_requested,
                            full_egress,
                            gif_frames,
                            disable_safety_filtering,
                        )
                        .await?;
                    if let Some(observer) = observation.as_mut() {
                        observer.headers(retry.status().as_u16());
                    }
                    if !retry.status().is_success() {
                        if let Some(observer) = observation.as_mut() {
                            observer.finish("upstream_error", Some("sender_rejection"));
                        }
                        return Err(AppError::ServiceUnavailable("AGY认证恢复提交失败".into()));
                    }
                    snapshot = refreshed;
                    policy_acknowledged = !system_prompt_policy.enabled;
                    ingress_sent = false;
                    reader = EventReader {
                        stream: Box::pin(retry.bytes_stream()),
                        pending: Vec::new(),
                        deadline,
                    };
                    continue;
                }
                for candidate in frame["candidates"].as_array().into_iter().flatten() {
                    for part in candidate["content"]["parts"]
                        .as_array()
                        .into_iter()
                        .flatten()
                    {
                        if let Some(call) = part.get("functionCall") {
                            calls.push(call.clone());
                        }
                    }
                }
                if !calls.is_empty() {
                    // 首个调用后的帧须等整轮归属确认，之前的内容继续即时发送。
                    pending_tool_bytes += raw.len();
                    if pending_tool_bytes > FRAME_LIMIT {
                        return Err(AppError::BadGateway("AGY工具响应超过聚合上限".into()));
                    }
                    pending_tool_frames.push(frame);
                    continue;
                }
                if output.primary.is_some() {
                    output.send(frame, deadline).await?;
                    forwarded += 1;
                }
            }
            Some("completed") => {
                let tool_pending = native["native_tool_pending"] == true;
                let has_calls = !calls.is_empty();
                if tool_pending != has_calls {
                    return Err(AppError::BadGateway("AGY工具调用归属未确认".into()));
                }
                let tool_deadline = tool_pending
                    .then(|| tool_wait_deadline(native, deadline))
                    .transpose()?;
                if (streaming || output.replay.is_some()) && pending_tool_frames.len() > 1 {
                    // AstrBot 在首条工具事件后停止读取，必须一次交付本轮的全部调用。
                    let mut response = Value::Null;
                    for frame in pending_tool_frames.drain(..) {
                        aggregate(&mut response, frame)?;
                    }
                    pending_tool_frames.push(response);
                }
                if let Some(observer) = observation.as_mut() {
                    observer.completed(tool_pending, &calls);
                }
                if let Some(tool_deadline) = tool_deadline {
                    reader.deadline = tool_deadline;
                    service.registry().turns.insert(
                        request_id.into(),
                        ToolTurn {
                            token_id,
                            account: account.clone(),
                            model: model.clone(),
                            runtime_contents: client_contents
                                .as_ref()
                                .map(|_| body["contents"].clone()),
                            contents: client_contents
                                .take()
                                .unwrap_or_else(|| body["contents"].clone()),
                            calls: calls.clone(),
                            deadline: tool_deadline,
                            admission: admission.clone(),
                            transport: transport.clone(),
                            previous_request_id: attempt_id.clone(),
                            receipt_body: None,
                            retained: false,
                            claimed: false,
                            cutover: cutover.clone(),
                        },
                    );
                    let weak = Arc::downgrade(&service);
                    let id = request_id.to_string();
                    tokio::spawn(async move {
                        sleep_until(tool_deadline).await;
                        if let Some(service) = weak.upgrade() {
                            service.registry().turns.remove(&id);
                        }
                    });
                    for frame in pending_tool_frames.drain(..) {
                        output.send(frame, deadline).await?;
                    }
                }
                completed = true;
                output.finish(Ok(()));
            }
            Some("rejected") => {
                let error = agy_input_rejection(native["code"].as_str().unwrap_or_default());
                if let Some(observer) = observation.as_mut() {
                    observer.input_rejected(&error);
                }
                return Err(error);
            }
            Some("tool_turn_finalized") => {
                if let Some(observer) = observation.as_mut() {
                    observer.tool_finalized(native["status"].as_str().unwrap_or("error"));
                }
            }
            Some("error" | "cancelled") => {
                let cancelled = native["type"] == "cancelled";
                if !cancelled && native["upstream_http_status"] == 429 {
                    if let Some(observer) = observation.as_mut() {
                        observer.upstream_quota();
                    }
                    return Err(AppError::AgyUpstreamQuota);
                }
                // 只有失败终态附带的 4xx/5xx 才能覆盖网关的兜底状态。
                let status = native["control_http_status"]
                    .as_u64()
                    .filter(|status| !cancelled && (400..600).contains(status))
                    .and_then(|status| StatusCode::from_u16(status as u16).ok());
                if let Some(observer) = observation.as_mut() {
                    observer.control_failed(status.map(|code| code.as_u16()), cancelled);
                }
                if let Some(status) = status {
                    return Err(AppError::AgyControl(status));
                }
                return Err(AppError::BadGateway("AGY原生请求失败".into()));
            }
            _ => {}
        }
    }
    Err(AppError::BadGateway("AGY原生作业提前结束".into()))
}

/// 投影受信发送器的输入错误。@param code 私有分类和字段。@return 允许公开的错误。
pub(crate) fn agy_input_rejection(code: &str) -> AppError {
    let (kind, field) = code.split_once(':').map_or((code, ""), |parts| parts);
    let (reason, message) = match kind {
        "invalid_gemini_media" => ("AGY_INVALID_MEDIA", "内嵌媒体的结构或数据无效"),
        "unsupported_gemini_media_type" => {
            ("AGY_UNSUPPORTED_MEDIA_TYPE", "AGY 入口不支持该媒体类型")
        }
        "gif_conversion_limit" => (
            "AGY_GIF_CONVERSION_LIMIT",
            "GIF 抽帧超过帧数、像素或请求大小上限",
        ),
        "invalid_gemini_png" => ("AGY_INVALID_PNG", "内嵌 PNG 的结构或数据无效"),
        "unsupported_gemini_image_type" => {
            ("AGY_UNSUPPORTED_IMAGE_TYPE", "AGY 内嵌图片仅支持 image/png")
        }
        "ambiguous_or_unknown_function_response"
        | "missing_function_response"
        | "invalid_gemini_function_response_order"
        | "invalid_function_response"
        | "invalid_gemini_function_call"
        | "invalid_gemini_function_call_order"
        | "gemini_pending_history_mismatch"
        | "gemini_pending_turn_mismatch"
        | "gemini_pending_call_mismatch"
        | "gemini_pending_results_mismatch" => {
            ("AGY_TOOL_RESULT_MISMATCH", "工具调用和回填结果无法对应")
        }
        _ => ("AGY_UNSUPPORTED_INPUT", "AGY请求包含当前内核不支持的结构"),
    };
    // 私有异常可能含调用方自定义字段，公开路径仅投影固定前缀和数组位置。
    let content_field = field.strip_prefix("/body/contents/").and_then(|rest| {
        let mut parts = rest.split('/');
        let index = parts.next()?.parse::<usize>().ok()?;
        let mut field = format!("contents[{index}]");
        if parts.next() == Some("parts") {
            let part = parts.next()?.parse::<usize>().ok()?;
            field.push_str(&format!(".parts[{part}]"));
            if let Some(
                key @ ("inlineData" | "inline_data" | "functionCall" | "functionResponse"),
            ) = parts.next()
            {
                field.push('.');
                field.push_str(key);
            }
        }
        Some(field)
    });
    let field = content_field.or_else(|| {
        let mut parts = field.strip_prefix("/body/").unwrap_or_default().split('/');
        let known = match parts.next().unwrap_or_default() {
            "generationConfig" => match parts.next() {
                Some(
                    key @ ("candidateCount"
                    | "enableEnhancedCivicAnswers"
                    | "frequencyPenalty"
                    | "imageConfig"
                    | "logprobs"
                    | "maxOutputTokens"
                    | "mediaResolution"
                    | "presencePenalty"
                    | "responseJsonSchema"
                    | "responseLogprobs"
                    | "responseMimeType"
                    | "responseModalities"
                    | "responseSchema"
                    | "seed"
                    | "speechConfig"
                    | "stopSequences"
                    | "temperature"
                    | "thinkingConfig"
                    | "thinking_config"
                    | "topK"
                    | "topP"),
                ) => {
                    return Some(format!("generationConfig.{key}"));
                }
                _ => "generationConfig",
            },
            "cachedContent" => "cachedContent",
            "contents" => "contents",
            "requests" => "requests",
            "safetySettings" => "safetySettings",
            "systemInstruction" => "systemInstruction",
            "toolConfig" => "toolConfig",
            "tools" => "tools",
            _ => match kind {
                "invalid_gemini_max_output_tokens" => "generationConfig.maxOutputTokens",
                "invalid_gemini_safety_settings"
                | "unsupported_gemini_safety_settings"
                | "unsupported_partial_safety_settings" => "safetySettings",
                "unsupported_gemini_tool_mode" => "toolConfig.functionCallingConfig.mode",
                "invalid_system_parts" | "unsupported_system_role" => "systemInstruction",
                "invalid_gemini_tools" => "tools",
                "invalid_gemini_contents"
                | "invalid_gemini_thought_signature"
                | "unsupported_gemini_last_role" => "contents",
                _ => return None,
            },
        };
        Some(known.into())
    });
    AppError::AgyInput {
        reason,
        message,
        field,
    }
}

/// 只识别原生Google源帧的完整认证错误。@param frame 原始Gemini逻辑帧。@return 是否明确401认证失败。
pub fn verified_auth_failure(frame: &Value) -> bool {
    frame["error"]["code"] == 401
        && frame["error"]["status"] == "UNAUTHENTICATED"
        && frame.get("candidates").is_none()
        && frame.get("usageMetadata").is_none()
}

/// 按原候选顺序拼接响应Parts，终态与usage只采用原生字段。@param output 聚合对象。@param frame 原生帧。@return 合同校验结果。
pub fn aggregate(output: &mut Value, frame: Value) -> Result<(), AppError> {
    if !frame.is_object() {
        return Err(invalid("Gemini响应必须为对象"));
    }
    if output.is_null() {
        *output = frame;
        return Ok(());
    }
    let target = output
        .as_object_mut()
        .ok_or_else(|| invalid("聚合状态无效"))?;
    for (key, value) in frame.as_object().ok_or_else(|| invalid("Gemini帧无效"))? {
        if key != "candidates" {
            target.insert(key.clone(), value.clone());
            continue;
        }
        let candidates = value.as_array().ok_or_else(|| invalid("Gemini候选无效"))?;
        let destination = target
            .entry("candidates")
            .or_insert(json!([]))
            .as_array_mut()
            .ok_or_else(|| invalid("候选状态无效"))?;
        for (index, candidate) in candidates.iter().enumerate() {
            if index >= destination.len() {
                destination.push(candidate.clone());
                continue;
            }
            let original = destination[index]
                .as_object_mut()
                .ok_or_else(|| invalid("候选无效"))?;
            for (key, value) in candidate.as_object().ok_or_else(|| invalid("候选无效"))? {
                if key == "content" {
                    let content = original
                        .entry("content")
                        .or_insert(json!({}))
                        .as_object_mut()
                        .ok_or_else(|| invalid("内容无效"))?;
                    for (key, value) in value.as_object().ok_or_else(|| invalid("内容无效"))? {
                        if key == "parts" {
                            content
                                .entry("parts")
                                .or_insert(json!([]))
                                .as_array_mut()
                                .ok_or_else(|| invalid("Parts无效"))?
                                .extend(
                                    value
                                        .as_array()
                                        .ok_or_else(|| invalid("Parts无效"))?
                                        .iter()
                                        .cloned(),
                                );
                        } else {
                            content.insert(key.clone(), value.clone());
                        }
                    }
                } else {
                    original.insert(key.clone(), value.clone());
                }
            }
        }
    }
    Ok(())
}
