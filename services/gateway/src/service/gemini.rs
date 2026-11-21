//! Gemini入口的账号许可、原生帧保真与跨HTTP工具轮归属。
mod messages;
mod replay;
mod websearch;

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
use tokio::sync::{OwnedSemaphorePermit, Semaphore, mpsc, watch};
use tokio::time::{Instant, sleep_until, timeout_at};
use tokio_stream::wrappers::ReceiverStream;
use uuid::Uuid;

use crate::error::AppError;
use crate::handler::router::AppState;
use crate::model::account::Account;
use crate::model::api_token::{ApiToken, ApiTokenStatus};
use crate::model::request_diagnostics::{ExecutionLocation, RequestLogMode};
use crate::service::account::{
    AccountService, AccountSlotPermit, CredentialActivity, DEFAULT_REQUEST_SLOT_UNITS,
};
use crate::service::agy_contract::{
    AGY_REQUEST_SECONDS, AGY_SOURCE_SHA256, AgyAccessSnapshot, AgyModelId, AgyOperation,
    AgySystemPromptPolicy, AgyToolContinuationMode,
};
use crate::service::diagnostics::agy::AgyAttemptTrace;
use crate::service::diagnostics::{
    self, CURRENT_LOG_MODE, CURRENT_TRACE, RequestTraceGuard, TraceContext,
};
use crate::service::request_session::RequestSession;
use crate::service::runtime_transport::{self, PreparedTransport};
use crate::service::system_update::{self, InferenceCutover, UpdateActivity};
use crate::service::v3_scheduling::{RequestPhase, SchedulingRequest};
use crate::service::{native_capture, runtime_bridge};
use replay::{ReplayKey, ToolReplay};
use websearch::{SearchRequest, SearchTurn};

pub(crate) const BODY_LIMIT: usize = 16 * 1024 * 1024;
const FRAME_LIMIT: usize = 64 * 1024 * 1024;
const AGY_TOOL_WAIT_LIMIT: Duration = Duration::from_secs(3600);
const AGY_IMAGE_MIME_TYPES: [&str; 8] = [
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "image/avif",
];

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

#[derive(Clone, Copy)]
enum ResponseProtocol {
    Gemini,
    Messages,
}

/// 已通过 Messages 鉴权和正文解码的输入。
pub(super) struct MessagesIngress {
    pub request: Value,
    pub raw: Bytes,
    pub headers: HeaderMap,
    pub session: RequestSession,
    pub started: Instant,
    pub cutover: Option<InferenceCutover>,
    pub full_egress: bool,
}

struct GenerationInput {
    raw: Bytes,
    headers: HeaderMap,
    body: Value,
    session: RequestSession,
    started: Instant,
    cutover: Option<InferenceCutover>,
    full_egress: bool,
    streaming: bool,
    protocol: ResponseProtocol,
    messages_tier: Option<&'static str>,
    search: Option<SearchRequest>,
}

/// 完成账号、凭据与发送器准备的生成请求。
struct PreparedGeneration {
    account: Account,
    admission: Arc<Admission>,
    claim: Option<ContinuationClaim>,
    model: RoutedModel,
    scheduling: SchedulingRequest,
    snapshot: AgyAccessSnapshot,
    native_model: AgyModelId,
    transport: Arc<PreparedTransport>,
    gif_frames: bool,
    ingress: Option<Value>,
}

/// 仍在等待客户端工具结果的原生请求归属。
struct ToolTurn {
    token_id: i64,
    derived_session_id: Option<String>,
    account: Account,
    model: RoutedModel,
    contents: Value,
    runtime_contents: Option<Value>,
    calls: Vec<Value>,
    call_signatures: Vec<Option<String>>,
    deadline: Instant,
    admission: Option<Arc<Admission>>,
    transport: Arc<PreparedTransport>,
    previous_request_id: String,
    receipt_body: Option<Value>,
    retained: bool,
    claimed: bool,
    cutover: Option<InferenceCutover>,
    search: Option<SearchTurn>,
    configured_mode: AgyToolContinuationMode,
    mode: AgyToolContinuationMode,
    native_model: AgyModelId,
    history_closed: Option<watch::Receiver<bool>>,
    session_scope: Option<String>,
    _history_bytes: Option<OwnedSemaphorePermit>,
}

/// 只采纳原发送器对同一代次和同一作业的关闭证明。
struct HistoryClosure {
    signal: watch::Sender<bool>,
    environment: ExecutionLocation,
    generation: String,
    request_seq: u64,
}

impl HistoryClosure {
    fn confirmed(&self, envelope: &Value, attempt_id: &str) -> bool {
        let proof = &envelope["history_closed"];
        envelope["environment_id"] == self.environment.environment_id
            && envelope["environment_generation"].as_u64() == Some(self.environment.generation)
            && proof["request_id"] == attempt_id
            && proof["generation"] == self.generation
            && proof["request_seq"].as_u64() == Some(self.request_seq)
    }
}

struct ContinuationClaim {
    service: Arc<GeminiService>,
    key: Option<String>,
    resolved_model: String,
    runtime_contents: Option<Value>,
    replay_key: ReplayKey,
    replay: Arc<ToolReplay>,
    configured_mode: AgyToolContinuationMode,
    mode: AgyToolContinuationMode,
    used_history: bool,
    original_location: Option<ExecutionLocation>,
    original_native_model: AgyModelId,
}

enum Continuation {
    Generate(Account, Option<Arc<Admission>>, ContinuationClaim),
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
        &mut self,
        token_id: i64,
        body: &Value,
        deadline: Instant,
        gif_frames: bool,
    ) -> Result<(), AppError> {
        let key = self
            .key
            .as_ref()
            .ok_or_else(|| invalid("原工具归属已释放"))?;
        let (transport, previous, finished, previous_deadline, history_closed) = {
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
                turn.history_closed.clone(),
            )
        };
        if !finished {
            let mut runtime_body = body.clone();
            if let Some(contents) = &self.runtime_contents {
                runtime_body["contents"] = contents.clone();
            }
            let until = deadline.min(previous_deadline);
            self.used_history = match self.mode {
                AgyToolContinuationMode::Claim => {
                    transport
                        .finish_agy_tools(&previous, token_id, runtime_body, until, gif_frames)
                        .await?;
                    false
                }
                AgyToolContinuationMode::History => {
                    if !wait_for_history_closure(history_closed, until).await {
                        return Err(AppError::ServiceUnavailable("AGY原工具轮关闭未确认".into()));
                    }
                    true
                }
                AgyToolContinuationMode::ClaimWithHistory => {
                    let finish = transport.finish_agy_tools(
                        &previous,
                        token_id,
                        runtime_body,
                        until,
                        gif_frames,
                    );
                    tokio::pin!(finish);
                    // 旧轮退出证明和领取回执在不同流上到达。兜底仍持有同一次回填的提交权。
                    tokio::select! {
                        biased;
                        closed = wait_for_history_closure(history_closed.clone(), until) => {
                            if !closed {
                                finish.await?;
                            }
                            closed
                        }
                        result = &mut finish => {
                            match result {
                                Ok(()) => false,
                                Err(error @ (AppError::AgyToolTurnFailed | AppError::ServiceUnavailable(_) | AppError::BadRequest(_))) => {
                                    if !wait_for_history_closure(history_closed, until).await {
                                        return Err(error);
                                    }
                                    true
                                }
                                Err(error) => return Err(error),
                            }
                        }
                    }
                }
            };
            let mut registry = self.service.registry();
            let turn = registry
                .turns
                .get_mut(key)
                .ok_or_else(|| invalid("原工具轮已到期"))?;
            // 领取回执有副作用，发送前失败的重试仍需匹配同一正文。
            if !self.used_history {
                turn.receipt_body = Some(body.clone());
            }
        }
        Ok(())
    }

    fn begin_submission(&mut self, attempt_id: &str) -> Option<Arc<ToolReplay>> {
        let previous = self.key.take()?;
        {
            // 同一锁内交接归属。连接中断时仍保留已进入发送边界的原尝试。
            let mut registry = self.service.registry();
            self.replay.mark_sending(attempt_id);
            registry.turns.remove(&previous);
        }
        let service = Arc::downgrade(&self.service);
        let replay = Arc::downgrade(&self.replay);
        let deadline = self.replay.deadline;
        let receipt_deadline = self.replay.receipt_deadline;
        let key = self.replay_key.clone();
        tokio::spawn(async move {
            sleep_until(deadline).await;
            if let Some(response) = replay.upgrade() {
                response.expire_frames();
            }
            sleep_until(receipt_deadline).await;
            if let (Some(service), Some(replay)) = (service.upgrade(), replay.upgrade()) {
                service.registry().remove_replay(&key, &replay);
            }
        });
        Some(self.replay.clone())
    }
}

async fn wait_for_history_closure(signal: Option<watch::Receiver<bool>>, until: Instant) -> bool {
    let Some(mut signal) = signal else {
        return false;
    };
    matches!(
        timeout_at(until, signal.wait_for(|closed| *closed)).await,
        Ok(Ok(_))
    ) && Instant::now() < until
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
    receipt_budget: Arc<Semaphore>,
    history_budget: Arc<Semaphore>,
}

impl Default for GeminiService {
    fn default() -> Self {
        Self {
            registry: Mutex::default(),
            replay_budget: Arc::new(Semaphore::new(FRAME_LIMIT)),
            receipt_budget: Arc::new(Semaphore::new(FRAME_LIMIT)),
            history_budget: Arc::new(Semaphore::new(FRAME_LIMIT)),
        }
    }
}

impl GeminiService {
    fn registry(&self) -> MutexGuard<'_, ToolRegistry> {
        self.registry
            .lock()
            .unwrap_or_else(|error| error.into_inner())
    }

    fn reserve_history(
        &self,
        contents: &Value,
        client_contents: Option<&Value>,
        tool_bytes: usize,
    ) -> Result<OwnedSemaphorePermit, AppError> {
        let mut bytes = tool_bytes;
        for contents in [Some(contents), client_contents].into_iter().flatten() {
            bytes += serde_json::to_vec(contents)
                .map_err(|_| invalid("AGY历史无效"))?
                .len();
        }
        let bytes = u32::try_from(bytes).map_err(|_| AppError::AgyToolReplayUnavailable)?;
        self.history_budget
            .clone()
            .try_acquire_many_owned(bytes)
            .map_err(|_| AppError::ServiceUnavailable("AGY历史续轮记录容量不足".into()))
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
                replay.expire_frames();
                return replay.attempt().is_some();
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
        error @ AppError::AgyToolResponseExpired => {
            (StatusCode::GONE, "FAILED_PRECONDITION", error.to_string())
        }
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

fn gemini_thinking_level_tier(level: &str) -> Option<&'static str> {
    match level.to_ascii_lowercase().as_str() {
        "minimal" | "low" => Some("low"),
        "medium" => Some("medium"),
        "high" => Some("high"),
        "xhigh" => Some("xhigh"),
        _ => None,
    }
}

fn gemini_thinking_budget_tier(budget: i64) -> Option<&'static str> {
    // 沿用 Sub2API 的预算区间，只选择档位，原生执行仍由目录型号决定。
    match budget {
        -1 | 8193.. => Some("high"),
        0..=1024 => Some("low"),
        1025..=8192 => Some("medium"),
        _ => None,
    }
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
        .map(|value| {
            value
                .as_str()
                .and_then(gemini_thinking_level_tier)
                .ok_or_else(|| invalid("Gemini thinkingLevel 无效"))
        })
        .transpose()?;
    let budget_tier = config
        .get("thinkingBudget")
        .map(|value| {
            value
                .as_i64()
                .and_then(gemini_thinking_budget_tier)
                .ok_or_else(|| invalid("Gemini thinkingBudget 无效"))
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
    let supported_non_images = [
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
                    if !AGY_IMAGE_MIME_TYPES.contains(&mime)
                        && !supported_non_images.contains(&mime)
                    {
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

fn pair_tool_responses(calls: &[Value], responses: &[&Value]) -> Option<Vec<usize>> {
    if calls.len() != responses.len() {
        return None;
    }
    let mut claimed = vec![false; calls.len()];
    let mut indices = vec![None; responses.len()];
    // 先保留可由 ID 唯一核对的位置，避免较早到达的无 ID 结果占用它。
    for (response, index) in responses.iter().zip(&mut indices) {
        let name = response["name"].as_str().filter(|name| !name.is_empty())?;
        if !response["response"].is_object() {
            return None;
        }
        let has_name = calls.iter().any(|call| call["name"] == name);
        let identifier = match response.get("id") {
            Some(id) => id.as_str().filter(|id| !id.is_empty())?,
            None if !has_name => name,
            None => continue,
        };
        let mut matches = calls
            .iter()
            .enumerate()
            .filter(|(_, call)| (!has_name || call["name"] == name) && call["id"] == identifier);
        let call_index = matches.next()?.0;
        if matches.next().is_some() || claimed[call_index] {
            return None;
        }
        claimed[call_index] = true;
        *index = Some(call_index);
    }
    // 不同工具可交错完成，无 ID 的结果只跟随同名调用的相对顺序。
    for (response, index) in responses.iter().zip(&mut indices) {
        if index.is_some() {
            continue;
        }
        let call_index = calls
            .iter()
            .zip(&claimed)
            .position(|(call, used)| !used && call["name"] == response["name"])?;
        claimed[call_index] = true;
        *index = Some(call_index);
    }
    indices.into_iter().collect()
}

#[cfg(test)]
#[test]
fn parallel_results_reserve_ids_and_follow_order_within_each_name() {
    let calls = [
        json!({"name": "List", "id": "list"}),
        json!({"name": "Read", "id": "first", "args": {"path": "a.txt"}}),
        json!({"name": "Read", "id": "second", "args": {"path": "b.txt"}}),
        json!({"name": "Read", "id": "third", "args": {"path": "c.txt"}}),
    ];
    let read = json!({"name": "Read", "response": {}});
    let list = json!({"name": "List", "response": {}});
    let first = json!({"name": "Read", "id": "first", "response": {}});
    let second = json!({"name": "second", "response": {}});
    assert_eq!(
        pair_tool_responses(&calls, &[&read, &read, &read, &list]),
        Some(vec![1, 2, 3, 0])
    );
    assert_eq!(
        pair_tool_responses(&calls, &[&read, &list, &second, &first]),
        Some(vec![3, 0, 2, 1])
    );
    let wrong_id = json!({"name": "Read", "id": "list", "response": {}});
    let unknown_id = json!({"name": "Read", "id": "unknown", "response": {}});
    for responses in [
        [&read, &read, &read, &read],
        [&read, &first, &first, &list],
        [&read, &read, &wrong_id, &list],
        [&read, &read, &unknown_id, &list],
    ] {
        assert_eq!(pair_tool_responses(&calls, &responses), None);
    }
    assert_eq!(pair_tool_responses(&calls, &[&read, &read, &list]), None);
}

fn match_tool_turn(turn: &ToolTurn, model: &str, body: &Value) -> Option<Vec<usize>> {
    let old = turn.contents.as_array()?;
    let new = body["contents"].as_array()?;
    if turn.model.requested != model || new.len() != old.len() + 2 || new[..old.len()] != old[..] {
        return None;
    }
    let calls: Vec<_> = new[old.len()]["parts"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|part| part.get("functionCall"))
        .collect();
    if calls.len() != turn.calls.len()
        || new[old.len()]["role"] != "model"
        || new[old.len() + 1]
            .get("role")
            .is_some_and(|role| role != "user")
    {
        return None;
    }
    if turn.history_closed.is_some()
        && new[old.len()]["parts"]
            .as_array()?
            .iter()
            .filter(|part| part.get("functionCall").is_some())
            .zip(&turn.call_signatures)
            .any(|(part, original)| {
                part.get("thoughtSignature").is_some()
                    && part["thoughtSignature"].as_str() != original.as_deref()
            })
    {
        return None;
    }
    let empty = json!({});
    if !calls.iter().zip(&turn.calls).all(|(call, expected)| {
        call["name"] == expected["name"]
            && call.get("args").unwrap_or(&empty) == expected.get("args").unwrap_or(&empty)
            && call
                .get("id")
                .is_none_or(|id| Some(id) == expected.get("id"))
    }) {
        return None;
    }
    let responses: Vec<_> = new[old.len() + 1]["parts"]
        .as_array()?
        .iter()
        .filter_map(|part| part.get("functionResponse"))
        .collect();
    pair_tool_responses(&turn.calls, &responses)
}

/// 将已校验的 ID 补入原生历史。@param turn 原工具归属。@param body 客户端正文。
/// @param indices 按结果顺序给出的调用位置。@return 有变更时的原生历史。
fn runtime_tool_contents(turn: &ToolTurn, body: &Value, indices: &[usize]) -> Option<Value> {
    let contents = body["contents"].as_array()?;
    let start = contents.len().checked_sub(2)?;
    let client_calls: Vec<_> = contents[start]["parts"]
        .as_array()?
        .iter()
        .filter_map(|part| part.get("functionCall"))
        .collect();
    let corrections: Vec<_> = contents[start + 1]["parts"]
        .as_array()?
        .iter()
        .enumerate()
        .filter_map(|(index, part)| {
            part.get("functionResponse")
                .map(|response| (index, response))
        })
        .zip(indices.iter().copied())
        .filter_map(|((part_index, response), call_index)| {
            let call = &turn.calls[call_index];
            // 原生历史也需要能用回填携带的真实 ID 找到该次调用。
            let missing_id =
                response.get("id").is_some() && client_calls[call_index].get("id").is_none();
            (turn.history_closed.is_some() || missing_id || response["name"] != call["name"])
                .then_some((part_index, call_index))
        })
        .collect();
    if corrections.is_empty()
        && turn.runtime_contents.is_none()
        && !turn.call_signatures.iter().any(Option::is_some)
    {
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
        .filter(|part| part.get("functionCall").is_some())
        .collect();
    for (part, signature) in calls.iter_mut().zip(&turn.call_signatures) {
        if let Some(signature) = signature {
            // Claude 客户端只会回传标准 tool_use 字段，补回原生调用的签名。
            part["thoughtSignature"] = json!(signature);
        }
    }
    for (part_index, call_index) in corrections {
        let expected = &turn.calls[call_index];
        calls[call_index]["functionCall"]["id"] = expected["id"].clone();
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
        explicit_session: Option<&str>,
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
            .filter_map(|(key, turn)| {
                if turn.token_id != token.id
                    || !eligible(turn.account.id)
                    || turn
                        .session_scope
                        .as_deref()
                        .is_some_and(|session| Some(session) != explicit_session)
                    || turn
                        .cutover
                        .as_ref()
                        .is_some_and(InferenceCutover::is_cancelled)
                {
                    return None;
                }
                match_tool_turn(turn, model, body).map(|indices| (key.clone(), indices))
            })
            .collect();
        let mismatch = || AppError::AgyInput {
            reason: "AGY_TOOL_RESULT_MISMATCH",
            message: "工具结果缺少唯一原请求归属",
            field: Some(format!("contents[{index}]")),
        };
        if let Some(replay) = registry
            .replays
            .get(&replay_key)
            .filter(|entry| entry.retained(Instant::now()))
        {
            if !eligible(replay.account_id)
                || replay
                    .session_scope
                    .as_deref()
                    .is_some_and(|session| Some(session) != explicit_session)
                || matches.iter().any(|(key, _)| key != &replay.previous_turn)
            {
                return Err(mismatch());
            }
            return Ok(Some(Continuation::Replay(replay.clone())));
        }
        let [(key, indices)] = matches.as_slice() else {
            return Err(mismatch());
        };
        let turn = registry
            .turns
            .get_mut(key)
            .ok_or_else(|| invalid("工具轮已结束"))?;
        if turn
            .search
            .as_ref()
            .is_some_and(|search| search.active != 0)
        {
            return Err(AppError::AdmissionLimited { retry_after: 1 });
        }
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
        let mut replay = ToolReplay::new(
            turn.account.id,
            request_id.to_owned(),
            key.clone(),
            turn.derived_session_id.clone(),
            deadline,
            cutover,
            self.replay_budget.clone(),
        );
        replay.session_scope = turn
            .session_scope
            .clone()
            .or_else(|| explicit_session.map(str::to_owned));
        replay.reserve_receipt(&replay_key, &self.receipt_budget)?;
        turn.claimed = true;
        turn.retained = true;
        let replay = Arc::new(replay);
        let continuation = Continuation::Generate(
            turn.account.clone(),
            turn.admission.clone(),
            ContinuationClaim {
                service: self.clone(),
                key: Some(key.clone()),
                resolved_model: turn.model.resolved.clone(),
                runtime_contents: runtime_tool_contents(turn, body, indices),
                replay_key: replay_key.clone(),
                replay: replay.clone(),
                configured_mode: turn.configured_mode,
                mode: turn.mode,
                used_history: false,
                original_location: turn.transport.execution_location(),
                original_native_model: turn.native_model.clone(),
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
    validate_model(model)?;
    let streaming = match action {
        "generateContent" => false,
        "streamGenerateContent" => true,
        _ => return Err(AppError::NotFound),
    };
    diagnostics::request_context("antigravity", "gemini", Some(model));
    let (parts, ingress_body) = request.into_parts();
    let raw = axum::body::to_bytes(ingress_body, BODY_LIMIT)
        .await
        .map_err(|_| invalid("Gemini正文超过上限"))?;
    diagnostics::remember_ingress_body(&raw);
    let body: Value = serde_json::from_slice(&raw).map_err(|_| invalid("Gemini正文必须为JSON"))?;
    if !body.is_object() || !body["contents"].is_array() {
        return Err(invalid("Gemini contents无效"));
    }
    let session = RequestSession::gemini(token.id, &parts.headers, model, &body);
    execute(
        state.gemini_svc,
        state.account_svc,
        token,
        model,
        GenerationInput {
            raw,
            headers: parts.headers,
            body,
            session,
            started,
            cutover,
            full_egress,
            streaming,
            protocol: ResponseProtocol::Gemini,
            messages_tier: None,
            search: None,
        },
    )
    .await
}

/// 在原准入边界执行 Messages 请求。@param service 当前会话服务。@param account_svc 账号服务。
/// @param token 已认证的访问范围。@param input 已解码入站。@return Anthropic Messages 响应。
pub(super) async fn generate_messages(
    service: Arc<GeminiService>,
    account_svc: Arc<AccountService>,
    token: ApiToken,
    input: MessagesIngress,
) -> Response {
    let result = async {
        if token.status != ApiTokenStatus::Active {
            return Err(AppError::Unauthorized);
        }
        diagnostics::error_stage("messages_conversion");
        let model = input.request["model"].as_str().unwrap_or_default();
        validate_model(model)?;
        let streaming = messages::streaming(&input.request)?;
        let search = SearchRequest::from_messages(&input.request)?;
        let (body, messages_tier, summary) = if search.is_some() {
            (Value::Null, None, None)
        } else {
            let (body, summary) = messages::convert_request(&input.request)?;
            (body, messages::thinking_tier(&input.request), summary)
        };
        if let Some(summary) = summary {
            let models = gemini_model_names(model, None);
            let media = requested_media(&body)?;
            let deadline = input.started + Duration::from_secs(AGY_REQUEST_SECONDS as u64);
            let accounts = timeout_at(
                deadline,
                account_svc.agy_candidates(&token, &models, &media),
            )
            .await
            .map_err(|_| AppError::AdmissionLimited { retry_after: 1 })??;
            if accounts.is_empty() {
                return Err(AppError::ServiceUnavailable("AGY账号不可用".into()));
            }
            // 摘要重带已经完成的结果，只生成本地状态。工具归属和响应缓存继续由主请求持有。
            diagnostics::error_stage("agy_agent_summary");
            diagnostics::local_outcome("local_response");
            let frame = json!({"candidates":[{
                "content":{"parts":[{"text":summary}]},"finishReason":"STOP"
            }]});
            return Ok(if streaming {
                messages::stream_response(
                    futures_util::stream::once(async { Ok(frame) }),
                    model.into(),
                )
            } else {
                messages::json_response(&frame, model)
            });
        }
        execute(
            service,
            account_svc,
            token,
            model,
            GenerationInput {
                raw: input.raw,
                headers: input.headers,
                body,
                session: input.session,
                started: input.started,
                cutover: input.cutover,
                full_egress: input.full_egress,
                streaming,
                protocol: ResponseProtocol::Messages,
                messages_tier,
                search,
            },
        )
        .await
    }
    .await;
    match result {
        Ok(response) => response,
        Err(error) => {
            let (status, body) = gemini_error_body(error);
            messages::error_response(
                status,
                body["error"]["message"].as_str().unwrap_or("AGY 请求失败"),
            )
        }
    }
}

fn validate_model(model: &str) -> Result<(), AppError> {
    if model.is_empty()
        || model.len() > 128
        || !model
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"-_.".contains(&byte))
    {
        return Err(invalid("模型名称无效"));
    }
    Ok(())
}

async fn execute(
    service: Arc<GeminiService>,
    account_svc: Arc<AccountService>,
    token: ApiToken,
    model: &str,
    input: GenerationInput,
) -> Result<Response, AppError> {
    let GenerationInput {
        raw,
        headers,
        mut body,
        session,
        started,
        cutover,
        full_egress,
        streaming,
        protocol,
        messages_tier,
        search,
    } = input;
    let ingress_headers = headers
        .iter()
        .filter_map(|(name, value)| {
            value
                .to_str()
                .ok()
                .map(|value| (name.as_str().to_string(), value.to_string()))
        })
        .collect::<Vec<_>>();
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
    let mut deadline = started + Duration::from_secs(AGY_REQUEST_SECONDS as u64);
    let explicit_session = session.original().and(session.key());
    let search_binding = search
        .as_ref()
        .map(|search| service.claim_search(&token, model, explicit_session, &search.query))
        .transpose()?
        .flatten();
    let mut search_receipts = if let Some(binding) = &search_binding {
        deadline = deadline.min(binding.deadline);
        Some(
            timeout_at(deadline, binding.receipts.lock())
                .await
                .map_err(|_| AppError::AdmissionLimited { retry_after: 1 })?,
        )
    } else {
        None
    };
    if let Some(search) = &search
        && let Some(receipt) = search_receipts
            .as_ref()
            .and_then(|results| results.get(&search.query))
    {
        if let Some(binding) = &search_binding {
            diagnostics::selected_account(binding.account.id);
        }
        diagnostics::local_outcome("agy_search_replayed");
        return Ok(search.response(model, receipt.as_ref(), streaming));
    }
    let http_request_id =
        diagnostics::current_request_id().unwrap_or_else(|| Uuid::new_v4().to_string());
    let continuation = service.continuation(
        &token,
        model,
        &body,
        explicit_session,
        &http_request_id,
        deadline,
        cutover.clone(),
    );
    let derived_session_id = match &continuation {
        Ok(Some(Continuation::Replay(replay))) => replay.derived_session_id.clone(),
        Ok(Some(Continuation::Generate(_, _, claim))) => claim.replay.derived_session_id.clone(),
        _ => session.derived().map(str::to_owned),
    };
    diagnostics::record_request_session(session.original(), derived_session_id.as_deref());
    let mut tool_turn = match continuation? {
        Some(Continuation::Replay(replay)) => {
            let trace = diagnostics::current_trace();
            if let Some(trace) = trace.as_ref() {
                let attempt = replay.attempt();
                let state = match &attempt {
                    Some(attempt) if attempt.model_observed => "model_observed",
                    Some(_) => "sending",
                    None => "preparing",
                };
                trace.agy_replayed(
                    replay.account_id,
                    &replay.request_id,
                    attempt.as_ref().map(|value| value.id.as_str()),
                    state,
                );
            }
            if let Some(error) = replay.response_error() {
                return Err(error);
            }
            let stream = replay.read().inspect(move |frame| {
                if frame.is_err()
                    && let Some(trace) = trace.as_ref()
                {
                    trace.agy_replay_failed();
                }
            });
            return gemini_response(stream, replay.deadline, streaming, protocol, model).await;
        }
        Some(Continuation::Generate(account, admission, claim)) => {
            Some((account, admission, claim))
        }
        None => None,
    };

    let mut model_names = gemini_model_names(model, messages_tier.or(requested_tier));
    if messages_tier.is_some() {
        // Claude 客户端可默认发送 effort。目录缺少该档位时保留 Messages 原来可用的型号。
        for candidate in gemini_model_names(model, None) {
            if !model_names.contains(&candidate) {
                model_names.push(candidate);
            }
        }
    }
    let log_mode = diagnostics::current_log_mode();
    let capture_requested = log_mode == RequestLogMode::Debug;
    let full_egress = capture_requested && full_egress;
    let PreparedGeneration {
        account: current,
        admission,
        mut claim,
        model,
        scheduling,
        snapshot,
        native_model,
        transport,
        gif_frames,
        ingress,
    } = loop {
        diagnostics::error_stage("account_selection");
        let (account, admission, claim, resolved_model, scheduling) =
            if let Some((account, admission, mut claim)) = tool_turn.take() {
                let resolved_model = claim.resolved_model.clone();
                let current = if media.is_empty() {
                    account
                } else {
                    account_svc.get_account(account.id).await?
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
                let scheduling = account_svc.begin_agy_scheduling(None, &resolved_model, streaming);
                scheduling.selected(&current, None);
                diagnostics::selected_account(current.id);
                scheduling.phase(RequestPhase::Preparing);
                diagnostics::error_stage("tool_continuation");
                let gif_frames = current.agy_gif_frames_enabled && media.contains("image/gif");
                claim.finish(token.id, &body, deadline, gif_frames).await?;
                let admission = match admission {
                    Some(admission) => admission,
                    None => acquire_admission(&account_svc, &current, deadline).await?,
                };
                (current, admission, Some(claim), resolved_model, scheduling)
            } else if let Some(binding) = &search_binding {
                let scheduling =
                    account_svc.begin_agy_scheduling(None, &binding.resolved_model, streaming);
                scheduling.selected(&binding.account, None);
                (
                    binding.account.clone(),
                    binding.admission.clone(),
                    None,
                    binding.resolved_model.clone(),
                    scheduling,
                )
            } else {
                let (model_index, account, scheduling) = timeout_at(deadline, async {
                    let accounts = account_svc
                        .agy_candidates(&token, &model_names, &media)
                        .await?;
                    account_svc
                        .select_agy_smart(session.key(), &model_names, accounts, streaming)
                        .await
                })
                .await
                .map_err(|_| AppError::AdmissionLimited { retry_after: 1 })??;
                let admission = acquire_admission(&account_svc, &account, deadline).await?;
                (
                    account,
                    admission,
                    None,
                    model_names[model_index].clone(),
                    scheduling,
                )
            };
        scheduling.phase(RequestPhase::Preparing);
        let gif_frames = account.agy_gif_frames_enabled && media.contains("image/gif");
        diagnostics::selected_account(account.id);
        diagnostics::error_stage("credentials");
        let snapshot = timeout_at(
            deadline,
            account_svc.resolve_agy_access_with_admission(
                account.id,
                false,
                Some(&admission.credentials),
            ),
        )
        .await
        .map_err(|_| AppError::ServiceUnavailable("AGY凭据等待超时".into()))??;
        let current = account_svc.get_account(account.id).await?;
        let media_support =
            AccountService::agy_media_support(&current, &resolved_model, &media, gif_frames);
        if media_support != Some(true) {
            return Err(AccountService::agy_media_error(
                &media,
                media_support.is_none(),
            ));
        }
        let ingress = (search.is_none())
            .then(|| {
                native_capture::ingress(
                    log_mode,
                    &ingress_headers,
                    &raw,
                    &body,
                    &snapshot.access_token,
                )
            })
            .flatten();
        let native_model =
            AccountService::agy_model(&current, &resolved_model).ok_or(AppError::NotFound)?;
        if claim
            .as_ref()
            .is_some_and(|claim| claim.used_history && claim.original_native_model != native_model)
        {
            return Err(AppError::ServiceUnavailable(
                "AGY原工具轮的原生模型已变化".into(),
            ));
        }
        diagnostics::error_stage("runtime_prepare");
        let transport = if let Some(binding) = &search_binding {
            binding.transport.clone()
        } else {
            Arc::new(
                timeout_at(
                    deadline,
                    runtime_transport::prepare(
                        &current,
                        deadline.saturating_duration_since(Instant::now()),
                    ),
                )
                .await
                .map_err(|_| AppError::ServiceUnavailable("AGY环境准备超时".into()))??,
            )
        };
        if claim.as_ref().is_some_and(|claim| {
            claim.used_history && claim.original_location != transport.execution_location()
        }) {
            return Err(AppError::ServiceUnavailable(
                "AGY原工具轮的环境绑定已变化".into(),
            ));
        }
        let sticky = scheduling.key().is_some();
        if sticky {
            diagnostics::error_stage("account_selection");
            scheduling.phase(RequestPhase::WaitingSend);
            match timeout_at(deadline, scheduling.claim_binding(current.id)).await {
                Ok(Err(AppError::SchedulingConflict)) => continue,
                Ok(result) => result?,
                Err(_) => return Err(AppError::AdmissionLimited { retry_after: 1 }),
            }
        }
        // 绑定竞争失败的候选不会占用发送次数，已有绑定等本账号的临时限流。
        timeout_at(
            deadline,
            account_svc.acquire_account_rpm(&current, sticky, scheduling.key().unwrap_or("")),
        )
        .await
        .map_err(|_| AppError::AdmissionLimited { retry_after: 1 })??;
        break PreparedGeneration {
            account: current,
            admission,
            claim,
            model: RoutedModel {
                requested: model.to_owned(),
                resolved: resolved_model,
            },
            scheduling,
            snapshot,
            native_model,
            transport,
            gif_frames,
            ingress,
        };
    };
    if let Some(search) = search {
        diagnostics::error_stage("agy_web_search");
        let request_id = Uuid::new_v4().to_string();
        let previous = search_binding
            .as_ref()
            .map(|binding| binding.previous_request_id.as_str());
        let mut closing = search_binding
            .as_ref()
            .and_then(|binding| binding.cutover.clone())
            .or(cutover);
        if let Some(receipts) = search_receipts.as_mut() {
            // 上游接收状态不明时，同一原工具查询保留一次执行归属。
            receipts.insert(search.query.clone(), None);
        }
        scheduling.phase(RequestPhase::Running);
        let result = tokio::select! {
            biased;
            _ = async {
                match closing.as_mut() {
                    Some(signal) => signal.cancelled().await,
                    None => std::future::pending().await,
                }
            } => None,
            result = async {
                let upstream = transport.send_agy(
                    &request_id, token.id, snapshot, &model.resolved, native_model,
                    json!({"query":search.query,"previous_request_id":previous}),
                    AgySystemPromptPolicy::default(), deadline, false, false, false, false,
                    AgyOperation::Search,
                ).await.ok()?;
                websearch::read_receipt(upstream, &request_id, current.id, deadline).await
            } => result,
        };
        diagnostics::local_outcome(if result.is_some() {
            "agy_search_completed"
        } else {
            "agy_search_failed"
        });
        if let Some(receipts) = search_receipts.as_mut() {
            receipts.insert(search.query.clone(), result.clone());
        }
        return Ok(search.response(&model.requested, result.as_ref(), streaming));
    }
    // 发送器直接执行已选的目录型号。只在原始入站采集后消费路由字段，兼容现有运行镜像。
    if has_thinking_config {
        if let Some(config) = body
            .get_mut("generationConfig")
            .and_then(Value::as_object_mut)
        {
            config.remove("thinkingConfig");
        }
    }
    let mut system_prompt_policy =
        AgySystemPromptPolicy::new(current.agy_system_prompt_homoglyph_enabled);
    if matches!(protocol, ResponseProtocol::Messages) && current.agy_system_prompt_as_user_reminder
    {
        system_prompt_policy.user_reminder_index = messages::system_reminder_target(&body);
    }
    let disable_safety_filtering = current.agy_disable_safety_filtering;
    let request_id = Uuid::new_v4().to_string();
    let trace = diagnostics::current_trace();
    let previous_turn = claim
        .as_ref()
        .and_then(|claim| claim.key.as_ref())
        .and_then(|key| {
            service
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
        if let Some(claim) = &claim {
            let reason =
                if claim.used_history && claim.mode == AgyToolContinuationMode::ClaimWithHistory {
                    Some("original_closed")
                } else if claim.configured_mode != claim.mode {
                    Some("web_search")
                } else {
                    None
                };
            observer.continuation_path(claim.configured_mode, claim.used_history, reason);
        }
    }
    let client_contents = claim
        .as_mut()
        .and_then(|claim| claim.runtime_contents.take())
        .map(|contents| replace(&mut body["contents"], contents));
    let (sender, receiver) = mpsc::channel(2);
    let mut output = GeminiOutput {
        primary: Some(sender),
        replay: claim
            .as_mut()
            .and_then(|claim| claim.begin_submission(&request_id)),
    };
    let response_model = model.requested.clone();
    let explicit_session = explicit_session.map(str::to_owned);
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
                    full_egress, gif_frames, disable_safety_filtering, AgyOperation::Generate,
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
                account_svc,
                snapshot,
                native_model,
                system_prompt_policy,
                gif_frames,
                disable_safety_filtering,
                scheduling,
                derived_session_id,
                protocol,
                explicit_session,
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
        } else if let Some(turn) = registry.turns.get_mut(&http_request_id)
            && turn.history_closed.is_some()
        {
            // 原私有流已经退出。状态不明时仍保留有界归属供对账，账号许可随私有流归还。
            turn.admission.take();
        }
    });
    gemini_response(
        ReceiverStream::new(receiver),
        deadline,
        streaming,
        protocol,
        &response_model,
    )
    .await
}

async fn acquire_admission(
    account_svc: &AccountService,
    account: &Account,
    deadline: Instant,
) -> Result<Arc<Admission>, AppError> {
    let queue = account_svc
        .get_or_create_queue(account.id, account.concurrency)
        .await;
    let slot = queue
        .acquire(
            deadline.saturating_duration_since(Instant::now()),
            DEFAULT_REQUEST_SLOT_UNITS,
        )
        .await
        .map_err(|_| AppError::AdmissionLimited { retry_after: 1 })?;
    Ok(Arc::new(Admission {
        _slot: slot,
        credentials: account_svc.upstream_activity(account.id).await?,
        _maintenance: system_update::admission()?,
    }))
}

/// 首发与重读使用相同的公开 SSE 和 JSON 聚合。
/// @param frames 响应帧。@param deadline 原截止。@param streaming 是否返回事件流。
/// @param protocol 入口协议。@param model 公开模型。@return HTTP 响应或首帧前错误。
async fn gemini_response(
    frames: impl Stream<Item = Result<Value, AppError>> + Send + 'static,
    deadline: Instant,
    streaming: bool,
    protocol: ResponseProtocol,
    model: &str,
) -> Result<Response, AppError> {
    let mut frames = Box::pin(frames.fuse());
    let mut output = Value::Null;
    let mut size = 0;
    loop {
        let frame = timeout_at(deadline, frames.next())
            .await
            .map_err(|_| AppError::ServiceUnavailable("AGY响应超时".into()))?;
        let Some(frame) = frame else {
            if response_terminal(&output) {
                break;
            }
            return Err(AppError::BadGateway("AGY响应提前结束".into()));
        };
        let frame = frame?;
        let deliverable = response_ready(&frame, protocol);
        if deliverable && output.is_null() {
            output = frame;
            break;
        }
        // 只包含用量或结束原因时等控制结果。已经交付真实内容的流仍即时发送。
        aggregate_bounded(&mut output, &mut size, frame)?;
        if deliverable {
            break;
        }
    }
    if streaming {
        let stream = futures_util::stream::once(async { Ok(output) }).chain(frames);
        if matches!(protocol, ResponseProtocol::Messages) {
            return Ok(messages::stream_response(stream, model.to_owned()));
        }
        let stream = stream.map(|event| {
            let value = match event {
                Ok(value) => value,
                Err(
                    error @ (AppError::AgyUpstreamQuota
                    | AppError::AgyControl(_)
                    | AppError::AgyToolResponseExpired
                    | AppError::AgyToolReplayUnavailable),
                ) => gemini_error_body(error).1,
                Err(_) => {
                    json!({"error":{"code":503,"status":"UNAVAILABLE","message":"AGY原生请求失败"}})
                }
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
    while let Some(event) = timeout_at(deadline, frames.next())
        .await
        .map_err(|_| AppError::BadGateway("AGY响应超时".into()))?
    {
        aggregate_bounded(&mut output, &mut size, event?)?;
    }
    Ok(match protocol {
        ResponseProtocol::Gemini => Json(output).into_response(),
        ResponseProtocol::Messages => messages::json_response(&output, model),
    })
}

fn response_ready(frame: &Value, protocol: ResponseProtocol) -> bool {
    frame["candidates"][0]["content"]["parts"]
        .as_array()
        .into_iter()
        .flatten()
        .any(|part| match protocol {
            ResponseProtocol::Messages => messages::deliverable_part(part),
            ResponseProtocol::Gemini => part.as_object().is_some_and(|part| {
                part.iter().any(|(key, value)| {
                    if key == "text" {
                        value.as_str().is_some_and(|text| !text.trim().is_empty())
                    } else {
                        key != "thought" && !value.is_null()
                    }
                })
            }),
        })
}

fn response_terminal(frame: &Value) -> bool {
    prompt_blocked(frame)
        || frame["candidates"][0]["finishReason"]
            .as_str()
            .is_some_and(|reason| !matches!(reason, "" | "FINISH_REASON_UNSPECIFIED"))
}

fn prompt_blocked(frame: &Value) -> bool {
    frame["promptFeedback"]["blockReason"]
        .as_str()
        .is_some_and(|reason| !matches!(reason, "" | "BLOCK_REASON_UNSPECIFIED"))
}

fn aggregate_bounded(output: &mut Value, size: &mut usize, frame: Value) -> Result<(), AppError> {
    *size += serde_json::to_vec(&frame)
        .map_err(|_| invalid("Gemini响应无效"))?
        .len();
    if *size > FRAME_LIMIT {
        return Err(AppError::BadGateway("AGY响应超过聚合上限".into()));
    }
    aggregate(output, frame)
}

#[cfg(test)]
#[tokio::test]
async fn usage_prefix_retains_http_error_until_the_first_deliverable_frame() {
    use axum::body::to_bytes;
    use futures_util::stream::iter;

    let deadline = Instant::now() + Duration::from_secs(2);
    let usage = json!({"usageMetadata":{"promptTokenCount":14,"cachedContentTokenCount":9}});
    let payload = json!({"candidates":[{"content":{"parts":[{"text":"合成结果"}]}}]});
    for protocol in [ResponseProtocol::Messages, ResponseProtocol::Gemini] {
        for streaming in [true, false] {
            let prefix = iter(vec![
                Ok(usage.clone()),
                Err(AppError::AgyControl(StatusCode::INTERNAL_SERVER_ERROR)),
            ]);
            assert!(matches!(
                gemini_response(prefix, deadline, streaming, protocol, "fixture").await,
                Err(AppError::AgyControl(StatusCode::INTERNAL_SERVER_ERROR))
            ));
            let terminator = iter(vec![
                Ok(json!({"candidates":[{"finishReason":"STOP"}]})),
                Err(AppError::AgyControl(StatusCode::INTERNAL_SERVER_ERROR)),
            ]);
            assert!(matches!(
                gemini_response(terminator, deadline, streaming, protocol, "fixture").await,
                Err(AppError::AgyControl(StatusCode::INTERNAL_SERVER_ERROR))
            ));
        }
    }
    let stream = iter(vec![
        Ok(usage),
        Ok(payload),
        Err(AppError::AgyControl(StatusCode::INTERNAL_SERVER_ERROR)),
    ]);
    let response = gemini_response(
        stream,
        deadline,
        true,
        ResponseProtocol::Messages,
        "fixture",
    )
    .await
    .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = to_bytes(response.into_body(), 8192).await.unwrap();
    let body = String::from_utf8(bytes.to_vec()).unwrap();
    assert!(body.contains("\"cache_read_input_tokens\":9") && body.contains("合成结果"));
    assert!(body.contains("event: error") && !body.contains("event: message_stop"));
}

#[cfg(test)]
#[tokio::test]
async fn history_closure_requires_the_original_worker_and_request() {
    let (signal, receiver) = watch::channel(false);
    let closure = HistoryClosure {
        signal,
        environment: ExecutionLocation {
            node_key: "local".into(),
            environment_id: "fixture-environment".into(),
            generation: 7,
            assignment_revision: None,
        },
        generation: "fixture-worker".into(),
        request_seq: 1,
    };
    let mut envelope = json!({"environment_id":"fixture-environment","environment_generation":7,
        "history_closed":{"request_id":"fixture-attempt","generation":"fixture-worker","request_seq":1}});
    assert!(closure.confirmed(&envelope, "fixture-attempt"));
    assert!(!closure.confirmed(&envelope, "foreign-attempt"));
    envelope["history_closed"]["request_seq"] = json!(2);
    assert!(!closure.confirmed(&envelope, "fixture-attempt"));
    drop(closure);
    assert!(
        !wait_for_history_closure(Some(receiver), Instant::now() + Duration::from_secs(1)).await
    );
    let (_signal, closed) = watch::channel(true);
    assert!(!wait_for_history_closure(Some(closed), Instant::now()).await);
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
        None,
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
    derived_session_id: Option<String>,
    protocol: ResponseProtocol,
    explicit_session: Option<String>,
    mut cutover: Option<InferenceCutover>,
    output: &mut GeminiOutput,
) -> Result<(), AppError> {
    let mut reader = EventReader {
        stream: Box::pin(upstream.bytes_stream()),
        pending: Vec::new(),
        deadline,
    };
    let mut calls = Vec::new();
    let mut call_signatures = Vec::new();
    let mut pending_tool_frames = Vec::new();
    let mut pending_tool_bytes = 0;
    let mut completed = false;
    let mut attempt_id = initial_attempt_id;
    let mut attempted_recovery = false;
    let mut forwarded = 0;
    let mut policy_acknowledged = system_prompt_policy.is_disabled();
    let mut ingress_sent = false;
    let mut cutting_over = false;
    let mut history_closure: Option<HistoryClosure> = None;
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
            if !cutting_over
                && let Some(closure) = history_closure
                    .take()
                    .filter(|closure| closure.confirmed(&event, &attempt_id))
                && let Some(turn) = service.registry().turns.get_mut(request_id)
            {
                // 保留工具归属的同时归还账号许可。历史续轮提交时重新准入。
                turn.admission.take();
                closure.signal.send_replace(true);
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
            if completed && history_closure.is_some() {
                continue;
            }
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
            system_prompt_requested = !system_prompt_policy.is_disabled(),
            system_prompt_rule = system_prompt_policy.rule_version.as_str(),
            system_prompt_source = native["system_prompt_policy"]["source"].as_str(),
            system_prompt_changed = native["system_prompt_policy"]["changed"].as_bool(),
            system_prompt_replaced = native["system_prompt_policy"]["replaced_codepoints"].as_u64(),
            system_prompt_rule_sha256 = native["system_prompt_policy"]["rule_sha256"].as_str(),
            "AGY原生事件"
        );
        match native["type"].as_str() {
            Some("model_start") => {
                if let Some(replay) = output.replay.as_ref() {
                    replay.mark_model_observed(&attempt_id);
                }
            }
            Some("request_accepted") => {
                if let Some(report) = native
                    .get("system_prompt_policy")
                    .filter(|value| !value.is_null())
                {
                    if !system_prompt_policy.matches_report(report) {
                        return Err(AppError::BadGateway("AGY系统文本策略回执不符".into()));
                    }
                    policy_acknowledged = true;
                } else if !system_prompt_policy.is_disabled() {
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
                            AgyOperation::Generate,
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
                    policy_acknowledged = system_prompt_policy.is_disabled();
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
                            if matches!(protocol, ResponseProtocol::Messages)
                                || transport.tool_continuation_mode()
                                    != AgyToolContinuationMode::Claim
                            {
                                call_signatures
                                    .push(part["thoughtSignature"].as_str().map(str::to_owned));
                            }
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
                    let configured_mode = transport.tool_continuation_mode();
                    let search = matches!(protocol, ResponseProtocol::Messages)
                        .then(|| explicit_session.clone())
                        .flatten()
                        .and_then(|session| SearchTurn::new(session, &calls));
                    let mode = if search.is_some() {
                        AgyToolContinuationMode::Claim
                    } else {
                        configured_mode
                    };
                    let (history_closed, history_bytes) = if mode == AgyToolContinuationMode::Claim
                    {
                        (None, None)
                    } else {
                        let environment = transport
                            .execution_location()
                            .filter(|location| {
                                event["environment_id"] == location.environment_id
                                    && event["environment_generation"].as_u64()
                                        == Some(location.generation)
                            })
                            .ok_or_else(|| {
                                AppError::BadGateway("AGY历史工具轮环境归属缺失".into())
                            })?;
                        let generation = native["generation"]
                            .as_str()
                            .filter(|id| !id.is_empty())
                            .ok_or_else(|| {
                                AppError::BadGateway("AGY历史工具轮内核身份缺失".into())
                            })?;
                        let request_seq = native["request_seq"].as_u64().ok_or_else(|| {
                            AppError::BadGateway("AGY历史工具轮请求序号缺失".into())
                        })?;
                        let bytes = service.reserve_history(
                            &body["contents"],
                            client_contents.as_ref(),
                            pending_tool_bytes,
                        )?;
                        let (signal, receiver) = watch::channel(false);
                        history_closure = Some(HistoryClosure {
                            signal,
                            environment,
                            generation: generation.into(),
                            request_seq,
                        });
                        (Some(receiver), Some(bytes))
                    };
                    if let Some(observer) = observation.as_mut() {
                        observer.continuation_path(
                            configured_mode,
                            mode == AgyToolContinuationMode::History,
                            (configured_mode != mode).then_some("web_search"),
                        );
                    }
                    service.registry().turns.insert(
                        request_id.into(),
                        ToolTurn {
                            token_id,
                            derived_session_id: derived_session_id.clone(),
                            account: account.clone(),
                            model: model.clone(),
                            runtime_contents: client_contents
                                .as_ref()
                                .map(|_| body["contents"].clone()),
                            contents: client_contents
                                .take()
                                .unwrap_or_else(|| body["contents"].clone()),
                            calls: calls.clone(),
                            call_signatures: call_signatures.clone(),
                            deadline: tool_deadline,
                            admission: (mode != AgyToolContinuationMode::History)
                                .then(|| admission.clone()),
                            transport: transport.clone(),
                            previous_request_id: attempt_id.clone(),
                            receipt_body: None,
                            retained: false,
                            claimed: false,
                            cutover: cutover.clone(),
                            search,
                            configured_mode,
                            mode,
                            native_model: native_model.clone(),
                            session_scope: explicit_session.clone(),
                            history_closed,
                            _history_bytes: history_bytes,
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
                    if mode != AgyToolContinuationMode::Claim
                        && let Some(turn) = service.registry().turns.get_mut(request_id)
                    {
                        // 工具已交付。旧轮结束后仍须保留来源和签名供历史接续校验。
                        turn.retained = true;
                    }
                    completed = true;
                    output.finish(Ok(()));
                    if mode == AgyToolContinuationMode::History {
                        // 取消登记与关闭证明使用独立连接。登记回包丢失时继续读取原作业。
                        reader.deadline = tool_deadline
                            .min(Instant::now() + Duration::from_secs(AGY_REQUEST_SECONDS as u64));
                        let (transport, original, until) =
                            (transport.clone(), attempt_id.clone(), reader.deadline);
                        tokio::spawn(async move {
                            if transport
                                .cancel_agy(&original, token_id, until)
                                .await
                                .is_err()
                            {
                                tracing::warn!(attempt_id = %original, "AGY历史续轮取消登记待核对");
                            }
                        });
                    }
                    continue;
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
