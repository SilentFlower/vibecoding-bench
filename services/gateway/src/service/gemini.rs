//! Gemini入口的账号许可、原生帧保真与跨HTTP工具轮归属。
use std::collections::HashMap;
use std::io::Error as IoError;
use std::pin::Pin;
use std::sync::{Arc, Mutex};
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
use tokio::sync::mpsc;
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
use crate::service::system_update::{self, UpdateActivity};
use crate::service::{native_capture, runtime_bridge};

const BODY_LIMIT: usize = 16 * 1024 * 1024;
const FRAME_LIMIT: usize = 64 * 1024 * 1024;

/// 随原生工具轮保留的许可，下一HTTP请求共享同一份所有权。
struct Admission {
    _slot: AccountSlotPermit,
    _credentials: CredentialActivity,
    _maintenance: UpdateActivity,
}

struct ToolTurn {
    token_id: i64,
    account: Account,
    model: String,
    contents: Value,
    calls: Vec<Value>,
    deadline: Instant,
    admission: Arc<Admission>,
    transport: Arc<PreparedTransport>,
    previous_request_id: String,
    receipt_body: Option<Value>,
    retained: bool,
    claimed: bool,
}

struct ContinuationClaim {
    service: Arc<GeminiService>,
    key: Option<String>,
}

impl Drop for ContinuationClaim {
    fn drop(&mut self) {
        if let Some(key) = self.key.take() {
            if let Some(turn) = self
                .service
                .turns
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .get_mut(&key)
            {
                turn.claimed = false;
            }
        }
    }
}

impl ContinuationClaim {
    async fn finish(&self, token_id: i64, body: &Value, deadline: Instant) -> Result<(), AppError> {
        let key = self
            .key
            .as_ref()
            .ok_or_else(|| invalid("原工具归属已释放"))?;
        let (transport, previous, finished) = {
            let turns = self
                .service
                .turns
                .lock()
                .unwrap_or_else(|error| error.into_inner());
            let turn = turns.get(key).ok_or_else(|| invalid("原工具轮已到期"))?;
            (
                turn.transport.clone(),
                turn.previous_request_id.clone(),
                turn.receipt_body.is_some(),
            )
        };
        if !finished {
            transport
                .finish_agy_tools(&previous, token_id, body.clone(), deadline)
                .await?;
            let mut turns = self
                .service
                .turns
                .lock()
                .unwrap_or_else(|error| error.into_inner());
            let turn = turns
                .get_mut(key)
                .ok_or_else(|| invalid("原工具轮已到期"))?;
            turn.receipt_body = Some(body.clone());
        }
        Ok(())
    }
}

/// 每个应用独立持有尚未完成的工具归属，状态读取保持只读。
#[derive(Default)]
pub struct GeminiService {
    turns: Mutex<HashMap<String, ToolTurn>>,
}

fn invalid(message: &str) -> AppError {
    AppError::BadRequest(message.into())
}

fn gemini_error(error: AppError) -> Response {
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
        _ => (
            StatusCode::SERVICE_UNAVAILABLE,
            "UNAVAILABLE",
            "AGY请求失败，请查询原请求状态".into(),
        ),
    };
    (
        code,
        Json(json!({"error":{"code":code.as_u16(),"status":status,"message":message}})),
    )
        .into_response()
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

/// 列出当前令牌可见账号的真实模型映射。@param state 应用。@param request 原请求。@return Gemini模型目录。
pub async fn models(State(state): State<AppState>, request: Request) -> Response {
    let (parts, _) = request.into_parts();
    let result = async {
        let token = authenticate(&state,&parts.headers,parts.uri.query()).await?;
        let accounts = state.account_svc.agy_candidates(&token,None).await?;
        let mut models = Vec::new();
        for account in accounts {
            if let Some(mapping) = account.usage_data["capabilities"]["model_mappings"].as_object() {
                for name in mapping.keys() {
                    if AccountService::agy_model(&account,name).is_some() && !models.contains(name) { models.push(name.clone()); }
                }
            }
        }
        models.sort();
        Ok::<_,AppError>(Json(json!({"models":models.into_iter().map(|name| json!({"name":format!("models/{name}"),"displayName":name,
            "version":"1.5.9","supportedGenerationMethods":["generateContent","streamGenerateContent"]})).collect::<Vec<_>>()})).into_response())
    }.await;
    result.unwrap_or_else(gemini_error)
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

fn matches_turn(turn: &ToolTurn, model: &str, body: &Value) -> bool {
    let Some(old) = turn.contents.as_array() else {
        return false;
    };
    let Some(new) = body["contents"].as_array() else {
        return false;
    };
    if turn.model != model || new.len() != old.len() + 2 || new[..old.len()] != old[..] {
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
            .any(|response| response.get("response").is_none())
    {
        return false;
    }
    if !turn.calls.iter().all(|call| {
        responses
            .iter()
            .filter(|response| {
                response["name"] == call["name"]
                    && response
                        .get("id")
                        .is_none_or(|id| Some(id) == call.get("id"))
            })
            .count()
            == 1
    }) {
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

impl GeminiService {
    fn continuation(
        self: &Arc<Self>,
        token: &ApiToken,
        model: &str,
        body: &Value,
    ) -> Result<Option<(Account, Arc<Admission>, Instant, ContinuationClaim)>, AppError> {
        if !body["contents"]
            .as_array()
            .and_then(|contents| contents.last())
            .is_some_and(|content| {
                content["parts"].as_array().is_some_and(|parts| {
                    parts
                        .iter()
                        .any(|part| part.get("functionResponse").is_some())
                })
            })
        {
            return Ok(None);
        }
        let mut turns = self.turns.lock().unwrap_or_else(|error| error.into_inner());
        let allowed = token.allowed_account_ids();
        let blocked = token.blocked_account_ids();
        let matches: Vec<_> = turns
            .iter()
            .filter(|(_, turn)| {
                turn.token_id == token.id
                    && matches_turn(turn, model, body)
                    && !blocked.contains(&turn.account.id)
                    && (allowed.is_empty() || allowed.contains(&turn.account.id))
            })
            .map(|(key, _)| key.clone())
            .collect();
        if matches.len() != 1 {
            return Err(invalid("工具结果缺少唯一原请求归属"));
        }
        let turn = turns
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
        Ok(Some((
            turn.account.clone(),
            turn.admission.clone(),
            turn.deadline,
            ContinuationClaim {
                service: self.clone(),
                key: Some(matches[0].clone()),
            },
        )))
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
    let mode = state.gateway_svc.request_log_mode().await;
    CURRENT_LOG_MODE
        .scope(mode, async move {
            let trace = state
                .gateway_svc
                .diagnostics_store()
                .map(|store| TraceContext::for_protocol(store.clone(), "antigravity", "gemini"));
            let guard = trace
                .as_ref()
                .map(|trace| RequestTraceGuard::new(trace.clone()));
            let future = generate_inner(state, action, request, token);
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
) -> Result<Response, AppError> {
    let started = Instant::now();
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
    let body: Value = serde_json::from_slice(&raw).map_err(|_| invalid("Gemini正文必须为JSON"))?;
    if !body.is_object() || !body["contents"].is_array() {
        return Err(invalid("Gemini contents无效"));
    }
    diagnostics::error_stage("account_selection");
    let continuation = state.gemini_svc.continuation(&token, model, &body)?;
    let deadline = continuation
        .as_ref()
        .map(|(_, _, deadline, _)| *deadline)
        .unwrap_or(started + Duration::from_secs(AGY_REQUEST_SECONDS as u64));
    let (account, admission, mut claim) = if let Some((account, admission, _, claim)) = continuation
    {
        (account, admission, Some(claim))
    } else {
        let accounts = state
            .account_svc
            .agy_candidates(&token, Some(model))
            .await?;
        let mut selected = None;
        for account in accounts {
            if state
                .account_svc
                .get_account_rpm_status(&account)
                .await?
                .saturated
            {
                continue;
            }
            selected = Some(account);
            break;
        }
        let account = selected
            .ok_or_else(|| AppError::ServiceUnavailable("没有支持该模型的AGY账号".into()))?;
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
            _credentials: state.account_svc.upstream_activity(account.id).await?,
            _maintenance: system_update::admission()?,
        });
        (account, admission, None)
    };
    diagnostics::selected_account(account.id);
    // 原工具收尾复用原许可和原进程；新AT发布单独检查ready，待对账期间也能完成旧工具。
    if let Some(claim) = &claim {
        claim.finish(token.id, &body, deadline).await?;
    }
    diagnostics::error_stage("credentials");
    let snapshot = timeout_at(
        deadline,
        state.account_svc.resolve_agy_access(account.id, false),
    )
    .await
    .map_err(|_| AppError::ServiceUnavailable("AGY凭据等待超时".into()))??;
    let current = state.account_svc.get_account(account.id).await?;
    let capture_requested = diagnostics::current_log_mode() == RequestLogMode::Debug;
    let ingress = native_capture::ingress(
        diagnostics::current_log_mode(),
        &ingress_headers,
        &raw,
        &body,
        &snapshot.access_token,
    );
    let system_prompt_policy =
        AgySystemPromptPolicy::new(current.agy_system_prompt_homoglyph_enabled);
    let native_model = AccountService::agy_model(&current, model).ok_or(AppError::NotFound)?;
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
    let http_request_id =
        diagnostics::current_request_id().unwrap_or_else(|| Uuid::new_v4().to_string());
    let trace = diagnostics::current_trace();
    let previous_turn = claim
        .as_ref()
        .and_then(|claim| claim.key.as_ref())
        .and_then(|key| {
            state
                .gemini_svc
                .turns
                .lock()
                .unwrap_or_else(|e| e.into_inner())
                .get(key)
                .map(|turn| (key.clone(), turn.previous_request_id.clone()))
        });
    let mut observation = AgyAttemptTrace::begin(
        trace.as_ref(),
        &current,
        model,
        &native_model,
        transport.execution_location(),
        snapshot.credential_generation,
        &system_prompt_policy,
        &request_id,
        &body,
        streaming,
    );
    if let (Some(observer), Some((root, attempt))) = (observation.as_mut(), previous_turn) {
        observer.continuation(&root, &attempt);
    }
    // 从此刻起提交状态可能未知；只允许原监督器确认结果，禁止自动重新领取工具回填。
    let completed_turn = claim.as_mut().and_then(|claim| claim.key.take());
    let upstream = transport
        .send_agy(
            &request_id,
            token.id,
            snapshot.clone(),
            model,
            native_model.clone(),
            body.clone(),
            system_prompt_policy.clone(),
            deadline,
            capture_requested,
        )
        .await;
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
    if let Some(key) = completed_turn {
        state
            .gemini_svc
            .turns
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .remove(&key);
    }
    let (sender, mut receiver) = mpsc::channel(2);
    let service = state.gemini_svc.clone();
    let model = model.to_string();
    tokio::spawn(async move {
        let mut sender = Some(sender);
        let result = drive(
            upstream,
            service.clone(),
            &http_request_id,
            request_id.clone(),
            trace,
            observation,
            streaming,
            capture_requested,
            ingress,
            token.id,
            current,
            model,
            body,
            deadline,
            admission,
            transport,
            state.account_svc.clone(),
            snapshot,
            native_model,
            system_prompt_policy,
            &mut sender,
        )
        .await;
        if let Err(error) = result {
            if let Some(sender) = sender {
                let _ = sender.send(Err(error)).await;
            }
        }
        let mut turns = service
            .turns
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if turns
            .get(&http_request_id)
            .is_none_or(|turn| !turn.retained)
        {
            turns.remove(&http_request_id);
        }
    });
    let first = timeout_at(deadline, receiver.recv())
        .await
        .map_err(|_| AppError::ServiceUnavailable("AGY响应超时".into()))?
        .ok_or_else(|| AppError::BadGateway("AGY响应提前结束".into()))??;
    if streaming {
        let stream=futures_util::stream::once(async {Ok(first)}).chain(ReceiverStream::new(receiver)).map(|event| {
            let value=match event {Ok(value)=>value,Err(_)=>json!({"error":{"code":503,"status":"UNAVAILABLE","message":"AGY原生请求失败"}})};
            Ok::<Bytes,IoError>(Bytes::from(format!("data: {}\n\n",value)))
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
    while let Some(event) = timeout_at(deadline, receiver.recv())
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
    ingress: Option<Value>,
    token_id: i64,
    account: Account,
    model: String,
    body: Value,
    deadline: Instant,
    admission: Arc<Admission>,
    transport: Arc<PreparedTransport>,
    account_service: Arc<AccountService>,
    mut snapshot: AgyAccessSnapshot,
    native_model: AgyModelId,
    system_prompt_policy: AgySystemPromptPolicy,
    sender: &mut Option<mpsc::Sender<Result<Value, AppError>>>,
) -> Result<(), AppError> {
    let mut reader = EventReader {
        stream: Box::pin(upstream.bytes_stream()),
        pending: Vec::new(),
        deadline,
    };
    let mut calls = Vec::new();
    let mut completed = false;
    let mut attempt_id = initial_attempt_id;
    let mut attempted_recovery = false;
    let mut forwarded = 0;
    let mut policy_acknowledged = !system_prompt_policy.enabled;
    let mut ingress_sent = false;
    loop {
        let event = if let Some(channel) = sender.as_ref() {
            tokio::select! {event=reader.next()=>event?, _=channel.closed()=>{if let Some(observer)=observation.as_mut(){observer.finish("cancelled",Some("downstream_body"));}return Err(AppError::BadGateway("客户端已取消".into()));}}
        } else {
            reader.next().await?
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
            if !completed {
                return Err(AppError::BadGateway("AGY缺少原生终态".into()));
            }
            return Ok(());
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
            model,
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
                        account_service.resolve_agy_access(account.id, true),
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
                        &model,
                        &native_model,
                        transport.execution_location(),
                        refreshed.credential_generation,
                        &system_prompt_policy,
                        &attempt_id,
                        &body,
                        streaming,
                    );
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
                            &model,
                            native_model.clone(),
                            body.clone(),
                            system_prompt_policy.clone(),
                            deadline,
                            capture_requested,
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
                if let Some(sender) = sender.as_ref() {
                    timeout_at(deadline, sender.send(Ok(frame)))
                        .await
                        .map_err(|_| AppError::BadGateway("客户端背压超时".into()))?
                        .map_err(|_| AppError::BadGateway("客户端已取消".into()))?;
                    forwarded += 1;
                }
            }
            Some("completed") => {
                if let Some(observer) = observation.as_mut() {
                    observer.completed(native["native_tool_pending"] == true, &calls);
                }
                if native["native_tool_pending"] == true {
                    if calls.is_empty() {
                        return Err(AppError::BadGateway("工具调用归属缺失".into()));
                    }
                    service
                        .turns
                        .lock()
                        .unwrap_or_else(|error| error.into_inner())
                        .insert(
                            request_id.into(),
                            ToolTurn {
                                token_id,
                                account: account.clone(),
                                model: model.clone(),
                                contents: body["contents"].clone(),
                                calls: calls.clone(),
                                deadline,
                                admission: admission.clone(),
                                transport: transport.clone(),
                                previous_request_id: attempt_id.clone(),
                                receipt_body: None,
                                retained: false,
                                claimed: false,
                            },
                        );
                    let weak = Arc::downgrade(&service);
                    let id = request_id.to_string();
                    tokio::spawn(async move {
                        sleep_until(deadline).await;
                        if let Some(service) = weak.upgrade() {
                            service
                                .turns
                                .lock()
                                .unwrap_or_else(|error| error.into_inner())
                                .remove(&id);
                        }
                    });
                }
                completed = true;
                sender.take();
            }
            Some("rejected") => return Err(invalid("AGY请求包含当前内核不支持的结构")),
            Some("tool_turn_finalized") => {
                if let Some(observer) = observation.as_mut() {
                    observer.tool_finalized(native["status"].as_str().unwrap_or("error"));
                }
            }
            Some("error" | "cancelled") => {
                if let Some(observer) = observation.as_mut() {
                    observer.finish(
                        if native["type"] == "cancelled" {
                            "cancelled"
                        } else {
                            "upstream_error"
                        },
                        Some("native_control"),
                    );
                }
                return Err(AppError::BadGateway("AGY原生请求失败".into()));
            }
            _ => {}
        }
    }
    Err(AppError::BadGateway("AGY原生作业提前结束".into()))
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
