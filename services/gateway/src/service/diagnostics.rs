//! 请求诊断旁路：使用请求作用域关联重试，响应观察不改变转发字节。

use std::pin::Pin;
use std::sync::{Arc, Mutex, MutexGuard};
use std::task::{Context, Poll};
use std::time::Instant;

use axum::body::{Body, Bytes};
use axum::http::{HeaderMap, HeaderValue};
use axum::response::Response;
use chrono::{Duration as ChronoDuration, SecondsFormat, Utc};
use http_body::{Body as HttpBody, Frame, SizeHint};
#[cfg(all(target_os = "linux", feature = "v3-verification"))]
use libc::{CLOCK_MONOTONIC, clock_gettime, timespec};
use serde_json::Value;
#[cfg(all(target_os = "linux", feature = "v3-verification"))]
use serde_json::json;
use sha2::{Digest, Sha256};
#[cfg(all(target_os = "linux", feature = "v3-verification"))]
use std::env::var;
#[cfg(all(target_os = "linux", feature = "v3-verification"))]
use std::io::{Write, stderr};
use uuid::Uuid;

use crate::error::AppError;
use crate::model::account::Account;
use crate::model::identity::device_profile;
use crate::model::request_diagnostics::{
    AttemptDiagnostic, DiagnosticContext, DiagnosticParameters, DiagnosticSessions,
    DiagnosticTokens, ExecutionLocation, NativeRejection, NativeRequestObservation,
    RequestDiagnostic, RequestLogMode, TuiBodySource, TuiSessionOrigin, normalize_correlation_id,
    safe_model,
};
use crate::service::native_capture;
use crate::service::request_session::RequestSession;
use crate::service::rewriter::extract_session_id_from_body;
use crate::service::system_update::InferenceCutover;
use crate::service::tui_backend::TUI_V2;
use crate::service::usage::UsageCapture;
use crate::service::v3_scheduling::SchedulingRequest;
use crate::service::version_profile::profile_for_version;
use crate::store::cache::UpstreamSessionPoolResolve;
use crate::store::diagnostics_store::{ActiveDiagnostic, DiagnosticEvent, DiagnosticsStore};

pub(crate) mod agy;

/// 在同一请求入口冻结日志级别与拒绝正文范围。
#[derive(Clone, Copy, Default)]
pub(crate) struct RequestDiagnosticsConfig {
    pub(crate) mode: RequestLogMode,
    pub(crate) full_rejected_ingress: bool,
}

tokio::task_local! {
    /// 独立于诊断存储的请求模式，保证旁路故障时内容策略仍生效。
    pub(crate) static CURRENT_LOG_MODE: RequestLogMode;
    /// 只在当前请求的异步调用链中可见，不向后台遥测任务传播。
    pub(crate) static CURRENT_TRACE: TraceContext;
}

/// 获取入口冻结模式；独立后台任务默认沿摘要策略。
/// @return 当前请求模式。
pub(crate) fn current_log_mode() -> RequestLogMode {
    CURRENT_LOG_MODE.try_with(|mode| *mode).unwrap_or_default()
}

/// 返回当前消息请求的根标识，不创建新的诊断请求。
/// @return 无请求作用域时为空。
pub(crate) fn current_request_id() -> Option<String> {
    CURRENT_TRACE
        .try_with(|trace| trace.lock().request.request_id.clone())
        .ok()
}

/// 将当前请求的切换原因传给转发流。@return 未登记诊断时为空。
pub(super) fn current_cutover() -> Option<InferenceCutover> {
    CURRENT_TRACE
        .try_with(|trace| trace.cutover.clone())
        .ok()
        .flatten()
}

struct TraceState {
    retention: Option<ActiveDiagnostic>,
    request: RequestDiagnostic,
    request_session_recorded: bool,
    profile_selection: String,
    sessions: DiagnosticSessions,
    local_outcome: Option<&'static str>,
    tui_submission_unknown: bool,
    next_retry: Option<&'static str>,
    last_attempt: Option<(u32, String, Option<String>)>,
    pending_ingress: Option<PendingIngress>,
}

struct PendingIngress {
    headers: HeaderMap,
    body: Option<Bytes>,
    token: String,
    full: bool,
}

/// 可跨响应生命周期持有的请求上下文，只存白名单摘要。
#[derive(Clone)]
pub(crate) struct TraceContext {
    store: Arc<DiagnosticsStore>,
    state: Arc<Mutex<TraceState>>,
    cutover: Option<InferenceCutover>,
}

impl TraceContext {
    /// 创建 Messages 请求 UUID，平台由正文解码后的路由确定。
    /// @param store 独立诊断存储。
    /// @return 当前请求的观测上下文。
    pub(crate) fn new(store: Arc<DiagnosticsStore>) -> Self {
        Self::new_for_entry(store, None, "anthropic_messages")
    }

    /// 在首次入队前冻结真实入口，保持筛选投影一致。@param store 诊断存储。@param platform 已知平台。@param protocol 已知入口。@return 根上下文。
    pub(crate) fn for_protocol(
        store: Arc<DiagnosticsStore>,
        platform: &str,
        protocol: &str,
    ) -> Self {
        Self::new_for_entry(store, Some(platform), protocol)
    }

    fn new_for_entry(store: Arc<DiagnosticsStore>, platform: Option<&str>, protocol: &str) -> Self {
        let request_id = Uuid::new_v4().to_string();
        let retention = store.track_request(&request_id);
        let trace = Self {
            store,
            cutover: None,
            state: Arc::new(Mutex::new(TraceState {
                retention: Some(retention),
                request: RequestDiagnostic {
                    context: Some(DiagnosticContext {
                        platform: platform.map(str::to_owned),
                        entry_protocol: Some(protocol.into()),
                        ..Default::default()
                    }),
                    native_rejection: None,
                    last_attempt: None,
                    log_mode: Some(current_log_mode()),
                    request_id,
                    original_session_id: None,
                    derived_session_id: None,
                    started_at: now(),
                    finished_at: None,
                    status_code: None,
                    account_id: None,
                    account_name: None,
                    account_email: None,
                    response_request_id: None,
                    outcome: "in_progress".into(),
                    error_stage: None,
                    attempt_count: 0,
                },
                profile_selection: "unresolved".into(),
                request_session_recorded: false,
                sessions: DiagnosticSessions::default(),
                local_outcome: None,
                tui_submission_unknown: false,
                next_retry: None,
                last_attempt: None,
                pending_ingress: None,
            })),
        };
        trace.emit(None);
        trace
    }

    /// 关联当前 HTTP 请求的实际切换原因。@param cutover 入口订阅。@return 原诊断上下文。
    pub(super) fn with_cutover(mut self, cutover: Option<InferenceCutover>) -> Self {
        self.cutover = cutover;
        self
    }

    fn interrupted_by_update(&self, end: &str) -> bool {
        end == "cancelled"
            && self
                .cutover
                .as_ref()
                .is_some_and(InferenceCutover::interrupted)
    }

    /// 仅在 Debug 保留已鉴权入站，终态若为本地拒绝才写入证据。@param headers 原始头。@param token 入口密钥。@param full 是否保存完整拒绝正文。
    pub(crate) fn remember_ingress(&self, headers: &HeaderMap, token: &str, full: bool) {
        if current_log_mode() == RequestLogMode::Debug
            && self.store.rejected_ingress_dir().is_some()
        {
            self.lock().pending_ingress = Some(PendingIngress {
                headers: headers.clone(),
                body: None,
                token: token.into(),
                full,
            });
        }
    }

    fn lock(&self) -> MutexGuard<'_, TraceState> {
        // 观测锁不包裹 await；即使异常展开污染锁，也不能中断业务转发。
        self.state.lock().unwrap_or_else(|error| error.into_inner())
    }

    /// 为重试保留本地 HTTP 根和原生成关联，零次上游尝试。
    /// @param account_id 原账号。@param request_id 原生成根。@param attempt_id 原尝试。
    /// @param submission_state 已观察到的发送状态。@return 无。
    pub(super) fn agy_replayed(
        &self,
        account_id: i64,
        request_id: &str,
        attempt_id: Option<&str>,
        submission_state: &'static str,
    ) {
        let mut state = self.lock();
        state.local_outcome = Some("cache_hit");
        state.request.account_id = Some(account_id);
        state.request.error_stage = Some("tool_continuation".into());
        if let Some(context) = state.request.context.as_mut() {
            context.replay_of_request_id = Some(request_id.to_owned());
            context.replay_of_attempt_id = attempt_id.map(str::to_owned);
            context.replay_submission_state = Some(submission_state.into());
        }
        drop(state);
        self.emit(None);
    }

    /// SSE 已发头时保留原响应的失败终态。@return 无。
    pub(super) fn agy_replay_failed(&self) {
        self.lock().local_outcome = Some("incomplete");
    }

    fn save_rejected_ingress(
        &self,
        state: &mut TraceState,
        reason: Option<String>,
        full_only: bool,
    ) -> bool {
        if full_only
            && !state
                .pending_ingress
                .as_ref()
                .is_some_and(|entry| entry.full)
        {
            return false;
        }
        let Some(directory) = self.store.rejected_ingress_dir() else {
            return false;
        };
        let Some(pending) = state.pending_ingress.take() else {
            return false;
        };
        let id = &state.request.request_id;
        let status = native_capture::record_gateway_rejection(
            directory,
            id,
            pending.headers,
            pending.body,
            pending.token,
            pending.full,
        );
        if full_only && status == "dropped" {
            return false;
        }
        state.request.native_rejection = Some(NativeRejection {
            capture_id: id.clone(),
            reason,
            capture_status: status.into(),
        });
        true
    }

    fn emit(&self, attempt: Option<AttemptDiagnostic>) {
        self.store.submit(DiagnosticEvent {
            request: self.lock().request.clone(),
            attempt,
        });
    }

    fn finish(&self, end: &'static str) {
        {
            let mut state = self.lock();
            if state.request.finished_at.is_some() {
                return;
            }
            if self.interrupted_by_update(end) {
                state.request.error_stage = Some("system_update".into());
                state.request.status_code.get_or_insert(503);
            }
            let success = state
                .request
                .status_code
                .is_some_and(|status| (200..300).contains(&status));
            state.request.outcome = if end != "complete" {
                end.into()
            } else if state.tui_submission_unknown {
                "transport_error".into()
            } else if !success && state.request.attempt_count == 0 {
                "local_rejected".into()
            } else if let Some(local) = state.local_outcome {
                local.into()
            } else if let Some((_, result, _)) = &state.last_attempt {
                result.clone()
            } else if state.request.attempt_count == 0 {
                "local_response".into()
            } else {
                "incomplete".into()
            };
            if !success && state.request.outcome == "success" {
                state.request.outcome = "local_rejected".into();
            }
            if success {
                state.request.native_rejection = None;
            }
            if ["success", "mock", "cache_hit"].contains(&state.request.outcome.as_str()) {
                state.request.error_stage = None;
                state.request.native_rejection = None;
            }
            if state.request.error_stage.is_none()
                && !["success", "mock", "cache_hit"].contains(&state.request.outcome.as_str())
            {
                state.request.error_stage = if end != "complete" {
                    if end == "body_error" {
                        state
                            .last_attempt
                            .as_ref()
                            .and_then(|(_, _, stage)| stage.clone())
                            .or_else(|| Some("downstream_body".into()))
                    } else {
                        Some("downstream_body".into())
                    }
                } else {
                    state
                        .last_attempt
                        .as_ref()
                        .and_then(|(_, _, stage)| stage.clone())
                };
            }
            if state.request.outcome == "local_rejected" && state.request.error_stage.is_none() {
                state.request.error_stage = Some("admission".into());
            }
            if let Some(context) = state.request.context.as_mut()
                && context.entry_protocol.as_deref() == Some("anthropic_messages")
            {
                // 正文解码前终结的请求沿现有 Messages 入口平台记账。
                context.platform.get_or_insert_with(|| "claude_code".into());
            }
            state.request.finished_at = Some(now());
            state.retention.take();
        }
        self.emit(None);
    }
}

/// 获取显式后台传递的根上下文。@return 当前HTTP的诊断上下文，旁路未装配时为空。
pub(crate) fn current_trace() -> Option<TraceContext> {
    CURRENT_TRACE.try_with(Clone::clone).ok()
}

/// 冻结入口的平台、协议和原请求模型。@param platform 实际入口平台。@param protocol 实际协议。@param model 已校验原模型。@return 无。
pub(crate) fn request_context(platform: &str, protocol: &str, model: Option<&str>) {
    let _ = CURRENT_TRACE.try_with(|trace| {
        let mut state = trace.lock();
        let context = state.request.context.get_or_insert_with(Default::default);
        context.platform = Some(platform.into());
        context.entry_protocol = Some(protocol.into());
        if context.requested_model.is_none() {
            context.requested_model = model.map(str::to_owned);
        }
        drop(state);
        trace.emit(None);
    });
}

/// 记录 Claude 入口及该次请求的会话。
/// @param session 入站解析结果。
/// @param body 已解码且尚未映射的请求正文。
/// @return 无。
pub(super) fn claude_request_session(session: &RequestSession, body: &Value) {
    request_context(
        "claude_code",
        "anthropic_messages",
        body.get("model")
            .and_then(Value::as_str)
            .and_then(safe_model)
            .as_deref(),
    );
    record_request_session(session.original(), session.derived());
}

/// 冻结根记录的客户端值或已有归属校验的派生值。
/// @param original 合法的入站会话。@param derived 当前路由所用派生键。@return 无。
pub(super) fn record_request_session(original: Option<&str>, derived: Option<&str>) {
    let _ = CURRENT_TRACE.try_with(|trace| {
        let mut state = trace.lock();
        if state.request_session_recorded {
            return;
        }
        state.request_session_recorded = true;
        // 缺失值已随入口记录入队，避免额外写入相同摘要。
        if original.is_none() && derived.is_none() {
            return;
        }
        state.request.original_session_id = original.map(str::to_owned);
        state.request.derived_session_id =
            derived.filter(|_| original.is_none()).map(str::to_owned);
        drop(state);
        trace.emit(None);
    });
}

/// 设置请求的固定画像选择方式，不在结束时重读配置。
/// @param client_version 是否按客户端版本选择画像。
/// @return 无返回值。
pub(crate) fn profile_selection(client_version: bool) {
    let _ = CURRENT_TRACE.try_with(|trace| {
        trace.lock().profile_selection = if client_version {
            "client_version"
        } else {
            "account"
        }
        .into()
    });
}

/// 记录当前选择的账号，包含选中后由本地返回的请求。
/// @param account_id 本轮调度实际选中的账号。
/// @return 无返回值。
pub(crate) fn selected_account(account_id: i64) {
    let _ = CURRENT_TRACE.try_with(|trace| {
        let mut state = trace.lock();
        state.request.account_id = Some(account_id);
        // 换号后的错误必须归属新一次选择，不能沿用前一账号的拒绝采集。
        state.request.native_rejection = None;
    });
}

/// 标记本地响应的来源，避免把模拟或缓存命中记为上游推理。
/// @param outcome 代码内固定的结果枚举。
/// @return 无返回值。
pub(crate) fn local_outcome(outcome: &'static str) {
    let _ = CURRENT_TRACE.try_with(|trace| trace.lock().local_outcome = Some(outcome));
}

/// 记录即将执行的重试原因或错误阶段。
/// @param reason 代码内固定原因，不接受上游任意错误文本。
/// @return 无返回值。
pub(crate) fn retry_reason(reason: &'static str) {
    let _ = CURRENT_TRACE.try_with(|trace| trace.lock().next_retry = Some(reason));
}

/// 记录本地准备或授权恢复错误阶段。
/// @param stage 代码内固定阶段。
/// @return 无返回值。
pub(crate) fn error_stage(stage: &'static str) {
    let _ = CURRENT_TRACE.try_with(|trace| trace.lock().request.error_stage = Some(stage.into()));
}

/// 写入隔离验证的单调时钟事件。@param stage 固定阶段。@param id sender 预留 ID。
/// @param request 仅网关持有的公开请求 ID。@param result 固定阶段结果。@return 无。
pub(super) fn tui_startup_event(
    stage: &'static str,
    id: &str,
    request: Option<&str>,
    result: Option<&'static str>,
) {
    #[cfg(all(target_os = "linux", feature = "v3-verification"))]
    if var("FLOWER_V2_STARTUP_TRACE").as_deref() == Ok("1") {
        let mut clock = timespec {
            tv_sec: 0,
            tv_nsec: 0,
        };
        // 与同一隔离容器中的 Python 探针使用同一个单调时钟。
        if unsafe { clock_gettime(CLOCK_MONOTONIC, &mut clock) } == 0 {
            let ticks = clock.tv_sec as u64 * 1_000_000_000 + clock.tv_nsec as u64;
            let mut event = json!({"event": "tui_startup", "stage": stage,
                "monotonic_ns": ticks, "reservation_id": id});
            if let Some(request) = request {
                event["request_id"] = json!(request);
            }
            if let Some(result) = result {
                event["result"] = json!(result);
            }
            let line = format!("{event}\n");
            let _ = stderr().lock().write_all(line.as_bytes());
        }
    }
    #[cfg(not(all(target_os = "linux", feature = "v3-verification")))]
    let _ = (stage, id, request, result);
}

/// 关联当前公开请求和账号发送器预留。@param id 网关生成的预留 ID。@return 无。
pub(super) fn tui_reservation(id: &str) {
    #[cfg(all(target_os = "linux", feature = "v3-verification"))]
    if let Some(request) = current_request_id() {
        tui_startup_event("gateway_reservation", id, Some(&request), None);
    }
    let _ = CURRENT_TRACE.try_with(|trace| {
        let mut state = trace.lock();
        let context = state.request.context.get_or_insert_with(Default::default);
        context.tui_reservation_id = Some(id.to_owned());
        drop(state);
        trace.emit(None);
    });
}

/// 记录已发起私有提交后失去响应头的边界。@return 无。
pub(super) fn tui_submission_unknown() {
    let _ = CURRENT_TRACE.try_with(|trace| {
        let mut state = trace.lock();
        state.tui_submission_unknown = true;
        state.request.error_stage = Some("tui_send_http".into());
        state.request.native_rejection = None;
    });
}

/// 记录 sender 已验证的本地拒绝及采集归属，保持零上游尝试。
/// @param reason 固定原因码，未知时为空。
/// @param capture_id 当前已提交的原生作业 UUID。
/// @param capture_status 私有采集队列的即时状态。
/// @return 无返回值。
pub(crate) fn native_rejection(
    reason: Option<&'static str>,
    capture_id: &str,
    capture_status: &str,
) {
    let _ = CURRENT_TRACE.try_with(|trace| {
        let mut state = trace.lock();
        // 发送器只有在对应账号允许内容采集时才回执 queued。
        if capture_status == "queued"
            && trace.save_rejected_ingress(&mut state, reason.map(str::to_owned), true)
        {
            return;
        }
        state.request.native_rejection = Some(NativeRejection {
            reason: reason.map(str::to_owned),
            capture_id: capture_id.to_owned(),
            capture_status: capture_status.to_owned(),
        });
    });
}

/// 记录已经完成读取的逻辑正文，清理和脱敏延后到本地拒绝终态。@param bytes 原逻辑正文。
pub(crate) fn remember_ingress_body(bytes: &Bytes) {
    if current_log_mode() == RequestLogMode::Debug {
        let _ = CURRENT_TRACE.try_with(|trace| {
            if let Some(ingress) = trace.lock().pending_ingress.as_mut() {
                ingress.body = Some(bytes.clone());
            }
        });
    }
}

/// 检查是否已打开本地拒绝入站采集。@return 仅已装配的 Debug 请求返回真。
pub(crate) fn observes_rejected_ingress() -> bool {
    CURRENT_TRACE
        .try_with(|trace| trace.lock().pending_ingress.is_some())
        .unwrap_or(false)
}

/// 记录既有 session 解析结果，绝不额外解析或刷新池 TTL。
/// @param account_id 已选定账号。
/// @param original 原始消息体中的真实 session。
/// @param resolved 已有上游池解析结果。
/// @return 无返回值。
pub(crate) fn session_context(
    account_id: i64,
    original: Option<&str>,
    resolved: Option<&UpstreamSessionPoolResolve>,
) {
    let _ = CURRENT_TRACE.try_with(|trace| {
        trace.lock().sessions = DiagnosticSessions {
            real_session_hash: original.map(|value| identity_hash(account_id, "session", value)),
            upstream_session_hash: resolved
                .and_then(|value| value.upstream_session_id.as_deref())
                .or(original)
                .map(|value| identity_hash(account_id, "session", value)),
            mapping_action: Some(
                resolved
                    .map(|value| value.action.as_str())
                    .unwrap_or("passthrough")
                    .into(),
            ),
            previous_message_hash: None,
        };
    });
}

/// 一次真实发送的观察器，离开作用域时也会记录取消。
pub(crate) struct AttemptTrace {
    trace: TraceContext,
    record: Option<AttemptDiagnostic>,
    capture: Option<UsageCapture>,
    start: Instant,
    committed: bool,
    feedback: Option<SchedulingRequest>,
}

/// 预处理白名单观察参数；尚不记录 attempt，丢弃也不记取消。
/// @param account 实际用于协议改写的账号副本。
/// @param body 最终上游请求字节，只临时解析，不持久化。
/// @return 有请求作用域时返回未提交的观察器。
pub(crate) fn prepare_attempt(account: &Account, body: &[u8]) -> Option<AttemptTrace> {
    CURRENT_TRACE.try_with(|_| ()).ok()?;
    let body: Value = serde_json::from_slice(body).unwrap_or(Value::Null);
    prepare_observation(account, &body, false)
}

/// 为显式标准化的 V2 回包记录真实发送和正文终态。
/// @param account 原绑定账号。@param body 交给 sender 的请求已解析结构。
/// @return 请求诊断作用域内尚未提交的观察器。
pub(crate) fn prepare_tui_attempt(account: &Account, body: &Value) -> Option<AttemptTrace> {
    let mut attempt = prepare_observation(account, body, true)?;
    if let Some(context) = attempt
        .record
        .as_mut()
        .and_then(|record| record.context.as_mut())
    {
        context.kernel = Some(TUI_V2.to_owned());
        // 事件源自报的能力不等于已证明的官方 CLI 版本。
        context.kernel_version = None;
    }
    Some(attempt)
}

// 观察器只读取明确来源的临时参数，完整业务正文不进入诊断存储。
fn prepare_observation(
    account: &Account,
    body: &Value,
    prefer_frozen_session: bool,
) -> Option<AttemptTrace> {
    CURRENT_TRACE
        .try_with(|trace| {
            let state = trace.lock();
            let mut sessions = state.sessions.clone();
            // V2 观察器读取原入站结构，实际出站会话来自已冻结的 sender 提交决策。
            if !prefer_frozen_session || sessions.mapping_action.is_none() {
                sessions.upstream_session_hash = extract_session_id_from_body(body)
                    .map(|value| identity_hash(account.id, "session", &value));
            }
            sessions.previous_message_hash = body
                .pointer("/thread/previous_message_id")
                .and_then(Value::as_str)
                .map(|value| identity_hash(account.id, "message", value));
            let record = AttemptDiagnostic {
                context: Some(DiagnosticContext {
                    submitted_model: DiagnosticParameters::from_request(body).model,
                    kernel: Some(
                        if account.request_backend == "native" {
                            "cc"
                        } else {
                            "legacy"
                        }
                        .into(),
                    ),
                    kernel_version: Some(
                        profile_for_version(&device_profile(account).env.version)
                            .key
                            .into(),
                    ),
                    ..state.request.context.clone().unwrap_or_default()
                }),
                execution_location: None,
                runtime: None,
                log_mode: state.request.log_mode,
                capture_status: None,
                attempt_id: Uuid::new_v4().to_string(),
                request_id: state.request.request_id.clone(),
                ordinal: 0,
                account_id: account.id,
                account_name: None,
                account_email: None,
                profile_version: profile_for_version(&device_profile(account).env.version)
                    .key
                    .into(),
                profile_selection: state.profile_selection.clone(),
                parameters: DiagnosticParameters::from_request(body),
                sessions,
                started_at: now(),
                finished_at: None,
                ttft_ms: None,
                first_output_ms: None,
                duration_ms: None,
                status_code: None,
                upstream_request_id: None,
                response_model: None,
                response_message_hash: None,
                stop_reason: None,
                tokens: DiagnosticTokens::default(),
                partial: true,
                outcome: "in_progress".into(),
                error_stage: None,
                error_type: None,
                retry_reason: None,
            };
            drop(state);
            AttemptTrace {
                trace: trace.clone(),
                record: Some(record),
                capture: Some(UsageCapture::observer(body)),
                start: Instant::now(),
                committed: false,
                feedback: None,
            }
        })
        .ok()
}

/// 从固定运行时组装阶段的实际白名单摘要建立诊断，来源不冒充最终写出。
/// @param account 实际承载账号。
/// @param observation sender 从 cc_prepared 提取的有界摘要。
/// @param attempt_id 私有作业及 sender 证据共用的 UUID。
/// @return 未提交的原生观察器，摘要损坏时保持缺口可见。
pub(crate) fn prepare_native_attempt(
    account: &Account,
    observation: NativeRequestObservation,
    attempt_id: &str,
) -> Option<AttemptTrace> {
    if Uuid::parse_str(attempt_id).is_err()
        || observation
            .runtime
            .as_ref()
            .is_some_and(|runtime| !runtime.is_valid())
        || observation.schema_version != 1
        || observation.body_sha256.len() != 64
        || !observation
            .body_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
        || observation
            .session_id
            .as_ref()
            .is_some_and(|id| id.len() > 512)
        || observation
            .previous_message_id
            .as_ref()
            .is_some_and(|id| id.len() > 512)
    {
        return None;
    }
    let session_mismatch = CURRENT_TRACE
        .try_with(|trace| {
            let expected = trace.lock().sessions.upstream_session_hash.clone();
            let actual = observation
                .session_id
                .as_deref()
                .map(|session| identity_hash(account.id, "session", session));
            expected.is_some() && expected != actual
        })
        .unwrap_or(false);
    if session_mismatch {
        error_stage("native_session_observation");
        return None;
    }
    let context = serde_json::json!({"model":observation.parameters.model,"stream":observation.parameters.stream,
        "metadata":{"user_id":serde_json::json!({"session_id":observation.session_id}).to_string()},
        "thread":{"previous_message_id":observation.previous_message_id}});
    let mut attempt = prepare_observation(account, &context, false)?;
    let record = attempt.record.as_mut()?;
    record.attempt_id = attempt_id.to_owned();
    record.profile_version = observation.source_version.as_str().into();
    if let Some(context) = record.context.as_mut() {
        context.kernel = Some("cc".into());
        context.kernel_version = Some(record.profile_version.clone());
    }
    record.profile_selection = format!(
        "native{}_cc_prepared",
        observation.source_version.as_str().rsplit('.').next()?
    );
    record.parameters = observation.parameters;
    record.capture_status = observation.capture_status;
    record.runtime = observation.runtime;
    Some(attempt)
}

/// 保留旧观察器测试的即时开始入口。
/// @param account 合成账号。
/// @param body 合成请求正文。
/// @return 已提交的测试观察器。
#[cfg(test)]
fn begin_attempt(account: &Account, body: &[u8]) -> Option<AttemptTrace> {
    let mut attempt = prepare_attempt(account, body)?;
    attempt.commit();
    Some(attempt)
}

impl AttemptTrace {
    /// 将同一 sender 私有预留与已提交尝试关联。@param id 原预留 UUID。@param status 可选采集状态。
    pub(super) fn tui_capture(&mut self, id: String, status: Option<&str>) {
        if let Some(record) = &mut self.record {
            record.attempt_id = id;
            record.capture_status = status.map(str::to_owned);
        }
    }

    /// 记录已绑定发送器确认的同轮归属。
    /// @param source 实际正文来源。@param origin 实际会话来源。@return 无。
    pub(super) fn tui_sources(
        &mut self,
        source: Option<TuiBodySource>,
        origin: Option<TuiSessionOrigin>,
    ) {
        if let Some(record) = self.record.as_mut()
            && (source.is_some() || origin.is_some())
        {
            let context = record.context.get_or_insert_with(Default::default);
            context.tui_body_source = source;
            context.tui_session_origin = origin;
        }
    }

    /// 用发送器确认的降级更新出站思考参数。@return 无。
    pub(super) fn tui_thinking_removed(&mut self) {
        if let Some(record) = self.record.as_mut() {
            record.parameters.thinking_type = None;
            record.parameters.thinking_budget = None;
        }
    }

    /// 记录同一次实际提交的冻结定位，保留诊断的旁路语义。
    /// @param location 原已核验发送通道提供的非秘密定位。
    /// @return 无。
    pub(crate) fn with_execution_location(&mut self, location: Option<ExecutionLocation>) {
        if let Some(record) = self.record.as_mut() {
            record.execution_location = location;
        }
    }

    /// 在真正提交边界发布一次 attempt；大正文解析已在准入前完成。
    /// @return 无，重复调用不重复计数。
    pub(crate) fn commit(&mut self) {
        self.commit_started(Instant::now(), now());
    }

    /// 原生摘要在响应头时回传，保留实际提交起点并只增加一次尝试。
    /// @param started 网关开始该次原生提交的单调时间。
    /// @return 无。
    pub(crate) fn commit_native(&mut self, started: Instant) {
        let timestamp = (Utc::now()
            - ChronoDuration::from_std(started.elapsed()).unwrap_or_default())
        .to_rfc3339_opts(SecondsFormat::Millis, true);
        self.commit_started(started, timestamp);
    }

    fn commit_started(&mut self, started: Instant, timestamp: String) {
        if self.committed {
            return;
        }
        let Some(record) = self.record.as_mut() else {
            return;
        };
        let mut state = self.trace.lock();
        state.request.attempt_count = state.request.attempt_count.saturating_add(1);
        state.request.error_stage = None;
        record.ordinal = state.request.attempt_count;
        record.retry_reason = state.next_retry.take().map(str::to_owned);
        record.started_at = timestamp;
        self.start = started;
        self.committed = true;
        drop(state);
        self.trace.emit(Some(record.clone()));
    }

    /// 让现有响应观察器在完整结束后回灌反馈，不新增 SSE 解析路径。
    /// @param request 当前调度租约。
    /// @return 无。
    pub(crate) fn with_feedback(&mut self, request: SchedulingRequest) {
        self.feedback = Some(request);
    }

    /// 返回供 sender 证据复用的内部 UUID。
    /// @return 当前尝试 UUID。
    pub(crate) fn id(&self) -> &str {
        self.record
            .as_ref()
            .map(|record| record.attempt_id.as_str())
            .unwrap_or_default()
    }

    /// 记录实际收到的响应头摘要，不复制任何完整 headers。
    /// @param status 上游状态码。
    /// @param headers 原始响应头。
    /// @param codings 既有传输路径解析的编码顺序。
    /// @return 无返回值。
    pub(crate) fn headers(&mut self, status: u16, headers: &HeaderMap, codings: Vec<String>) {
        if let Some(record) = self.record.as_mut() {
            record.status_code = Some(status);
            record.ttft_ms = Some(self.start.elapsed().as_millis() as u64);
            record.upstream_request_id = ["request-id", "x-request-id"]
                .iter()
                .find_map(|name| headers.get(*name).and_then(|v| v.to_str().ok()))
                .map(normalize_correlation_id);
        }
        if let Some(capture) = self.capture.as_mut() {
            capture.configure_codings(&codings);
        }
        if let Some(record) = self.record.as_ref() {
            self.trace.emit(Some(record.clone()));
        }
    }

    fn observe(&mut self, bytes: &[u8]) {
        if let Some(capture) = self.capture.as_mut() {
            capture.observe(bytes);
        }
    }

    /// 观察既有分支已缓冲的响应，不额外读取网络或修改编码。
    /// @param bytes 上游原始字节。
    /// @param complete 原有读取是否正常完成。
    /// @return 无返回值。
    pub(crate) fn buffered(&mut self, bytes: &[u8], complete: bool) {
        self.observe(bytes);
        self.finish(if complete { "complete" } else { "body_error" });
    }

    /// 记录传输错误，提交状态未知时不伪造上游 HTTP 状态。
    /// @return 无返回值。
    pub(crate) fn transport_error(&mut self) {
        self.finish("transport_error");
    }

    /// 把观察器绑定到原始响应体生命周期。
    /// @param response 保持字节和传输头不变的响应。
    /// @return 具有相同响应内容的旁路包装。
    pub(crate) fn wrap(self, response: Response) -> Response {
        let (parts, body) = response.into_parts();
        Response::from_parts(
            parts,
            Body::new(DiagnosticBody {
                inner: body,
                request: None,
                attempt: Some(self),
            }),
        )
    }

    fn finish(&mut self, end: &'static str) {
        if !self.committed {
            self.record.take();
            self.capture.take();
            return;
        }
        let Some(mut record) = self.record.take() else {
            return;
        };
        if let Some(capture) = self.capture.take() {
            let observed = capture.observation(end == "complete");
            record.first_output_ms = observed.first_output_at.map(|at| {
                at.saturating_duration_since(self.start)
                    .as_millis()
                    .min(u128::from(u64::MAX)) as u64
            });
            record.tokens = observed.tokens.into();
            record.partial = observed.partial;
            record.response_model = observed.response_model.as_deref().and_then(safe_model);
            record.response_message_hash = observed
                .message_id
                .as_deref()
                .map(|id| identity_hash(record.account_id, "message", id));
            record.stop_reason = observed.stop_reason;
            if observed.observation_error.is_some() {
                self.trace.store.observation_failed();
            }
            record.error_type = if observed.policy_reason.is_some()
                && !matches!(record.status_code, Some(401 | 429))
            {
                Some("session_policy_refusal".into())
            } else {
                observed
                    .error_type
                    .or_else(|| observed.observation_error.map(str::to_owned))
            };
        }
        record.outcome = if end != "complete" {
            end.into()
        } else if record.error_type.as_deref() == Some("session_policy_refusal")
            || record.status_code.is_some_and(|value| value >= 400)
        {
            "upstream_rejected".into()
        } else if record.error_type.as_deref().is_some_and(|kind| {
            !["sampling_limit", "decode_error", "invalid_payload"].contains(&kind)
        }) {
            "upstream_error".into()
        } else if record.partial {
            "incomplete".into()
        } else {
            "success".into()
        };
        record.error_stage = match record.outcome.as_str() {
            "success" => None,
            "cancelled" if self.trace.interrupted_by_update(end) => Some("system_update".into()),
            "transport_error" => Some("transport".into()),
            "upstream_rejected" => Some("upstream_headers".into()),
            _ => Some("upstream_body".into()),
        };
        record.duration_ms = Some(self.start.elapsed().as_millis().min(u64::MAX as u128) as u64);
        // 本机模型的 HTTP 鉴权、限流和同类 SSE 错误属于它自己的凭据。
        // 即使响应体异常中断，也不能用它给承载 TUI 的订阅账号扣健康分。
        let provider_rejection = record
            .context
            .as_ref()
            .and_then(|context| context.kernel.as_deref())
            == Some(TUI_V2)
            && (matches!(record.status_code, Some(401 | 403 | 429))
                || record.status_code == Some(200)
                    && matches!(
                        record.error_type.as_deref(),
                        Some("authentication_error" | "permission_error" | "rate_limit_error")
                    ));
        if let Some(feedback) = self.feedback.take().filter(|_| !provider_rejection) {
            feedback.finish_observed_attempt(
                record.account_id,
                record.status_code,
                &record.outcome,
                record.error_type.as_deref(),
                record.first_output_ms,
                record.duration_ms,
            );
        }
        record.finished_at = Some(now());
        {
            let mut state = self.trace.lock();
            if state
                .last_attempt
                .as_ref()
                .is_none_or(|(ordinal, _, _)| *ordinal <= record.ordinal)
            {
                state.last_attempt = Some((
                    record.ordinal,
                    record.outcome.clone(),
                    record.error_stage.clone(),
                ));
            }
        }
        self.trace.emit(Some(record));
    }
}

impl Drop for AttemptTrace {
    fn drop(&mut self) {
        self.finish("cancelled");
    }
}

/// 请求准备期和下游响应期共用的终结保护，覆盖客户端提前取消。
pub(crate) struct RequestTraceGuard {
    trace: TraceContext,
    active: bool,
}

impl RequestTraceGuard {
    /// 持有请求终结责任。
    /// @param trace 当前请求上下文。
    /// @return 生命周期保护器。
    pub(crate) fn new(trace: TraceContext) -> Self {
        Self {
            trace,
            active: true,
        }
    }

    /// 记录受控本地错误类别，不读取错误中的任意文本。
    /// @param error 网关返回的原始错误。
    /// @return 无返回值。
    pub(crate) fn error(&self, error: &AppError) {
        let stage = match error {
            AppError::AdmissionLimited { .. }
            | AppError::SchedulingConflict
            | AppError::TuiSubagentCapacity => "admission",
            AppError::BadRequest(_)
            | AppError::Conflict(_)
            | AppError::AgyInput { .. }
            | AppError::TuiInput { .. }
            | AppError::TuiInputUnsupported
            | AppError::TuiSubagentAmbiguous => "request",
            AppError::Unauthorized | AppError::PermanentCredential(_) => "credentials",
            AppError::TooManyRequests(_) => "admission",
            AppError::AgyUpstreamQuota | AppError::TuiProviderBackoff { .. } => "upstream_model",
            AppError::AgyControl(_) => "native_control",
            AppError::AgyToolTurnFailed
            | AppError::AgyToolReplayUnavailable
            | AppError::AgyToolContinuationTerminal { .. }
            | AppError::AgyToolResponseExpired => "tool_continuation",
            AppError::BadGateway(_) => "transport",
            // 503 可来自凭据、环境或原生准备，具体阶段由失败边界记录。
            AppError::ServiceUnavailable(_) => "gateway",
            AppError::Internal(_) | AppError::NotFound => "gateway",
        };
        let mut state = self.trace.lock();
        if let (AppError::AgyInput { reason, field, .. }, Some(context)) =
            (error, state.request.context.as_mut())
        {
            context.input_rejection_reason = Some((*reason).into());
            context.input_rejection_field = field.clone();
        }
        if state.request.error_stage.is_none() {
            state.request.error_stage = Some(stage.into());
        }
    }

    /// 附加下游关联头并把终结责任移交给响应体。
    /// @param response 原有网关响应。
    /// @return 保留已有上游请求 ID 的响应。
    pub(crate) fn wrap(self, mut response: Response) -> Response {
        let id = self.trace.lock().request.request_id.clone();
        if let Ok(value) = HeaderValue::from_str(&id) {
            response
                .headers_mut()
                .insert("x-cc2api-request-id", value.clone());
            if !response.headers().contains_key("x-request-id") {
                response.headers_mut().insert("x-request-id", value);
            }
        }
        {
            let mut state = self.trace.lock();
            state.request.status_code = Some(response.status().as_u16());
            state.request.response_request_id = response
                .headers()
                .get("x-request-id")
                .and_then(|v| v.to_str().ok())
                .map(normalize_correlation_id);
            if (response.status().is_client_error() || response.status().is_server_error())
                && state.request.attempt_count == 0
                && !state.tui_submission_unknown
                && state.request.native_rejection.is_none()
            {
                let reason = state
                    .request
                    .context
                    .as_ref()
                    .and_then(|context| context.input_rejection_reason.clone())
                    .or_else(|| state.request.error_stage.clone());
                self.trace.save_rejected_ingress(&mut state, reason, false);
            }
            state.pending_ingress = None;
        }
        let (parts, body) = response.into_parts();
        Response::from_parts(
            parts,
            Body::new(DiagnosticBody {
                inner: body,
                request: Some(self),
                attempt: None,
            }),
        )
    }

    fn finish(&mut self, end: &'static str) {
        if self.active {
            self.active = false;
            self.trace.finish(end);
        }
    }
}

impl Drop for RequestTraceGuard {
    fn drop(&mut self) {
        self.finish("cancelled");
    }
}

struct DiagnosticBody {
    inner: Body,
    request: Option<RequestTraceGuard>,
    attempt: Option<AttemptTrace>,
}

impl DiagnosticBody {
    fn finish(&mut self, end: &'static str) {
        if let Some(mut attempt) = self.attempt.take() {
            attempt.finish(end);
        }
        if let Some(mut request) = self.request.take() {
            request.finish(end);
        }
    }
}

impl HttpBody for DiagnosticBody {
    type Data = Bytes;
    type Error = axum::Error;

    fn poll_frame(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
    ) -> Poll<Option<Result<Frame<Bytes>, Self::Error>>> {
        let result = Pin::new(&mut self.inner).poll_frame(cx);
        match &result {
            Poll::Ready(Some(Ok(frame))) => {
                if let (Some(attempt), Some(bytes)) = (self.attempt.as_mut(), frame.data_ref()) {
                    attempt.observe(bytes);
                }
                if self.inner.is_end_stream() {
                    self.finish("complete");
                }
            }
            Poll::Ready(None) => self.finish("complete"),
            Poll::Ready(Some(Err(_))) => self.finish("body_error"),
            Poll::Pending => {}
        }
        result
    }

    fn is_end_stream(&self) -> bool {
        self.inner.is_end_stream()
    }
    fn size_hint(&self) -> SizeHint {
        self.inner.size_hint()
    }
}

impl Drop for DiagnosticBody {
    fn drop(&mut self) {
        self.finish(if self.inner.is_end_stream() {
            "complete"
        } else {
            "cancelled"
        });
    }
}

fn now() -> String {
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn identity_hash(account: i64, kind: &str, value: &str) -> String {
    let digest =
        Sha256::digest(format!("cc2api-diagnostics-v1:{account}:{kind}:{value}").as_bytes());
    hex::encode(&digest[..16])
}

#[cfg(test)]
mod tests {
    use super::{
        CURRENT_LOG_MODE, CURRENT_TRACE, RequestTraceGuard, TraceContext, begin_attempt,
        claude_request_session, error_stage, identity_hash, local_outcome, native_rejection, now,
        prepare_tui_attempt, profile_selection, selected_account, session_context, tui_reservation,
        tui_submission_unknown,
    };
    use crate::error::AppError;
    use crate::model::account::Account;
    use crate::model::request_diagnostics::{AttemptDiagnostic, DiagnosticQuery, RequestLogMode};
    use crate::service::request_session::RequestSession;
    use crate::service::usage::USAGE_BUFFER_LIMIT;
    use crate::service::v3_scheduling::{SchedulingCandidate, V3Scheduler, now_ms};
    use crate::store::cache::{UpstreamSessionPoolAction, UpstreamSessionPoolResolve};
    use crate::store::db::migrate;
    use crate::store::diagnostics_store::DiagnosticsStore;
    use crate::store::scheduling_store::SchedulingStore;
    use axum::body::{Body, Bytes, to_bytes};
    use axum::http::{HeaderMap, HeaderValue};
    use axum::response::{IntoResponse, Response};
    use flate2::Compression;
    use flate2::write::GzEncoder;
    use http_body_util::BodyExt;
    use serde_json::json;
    use sqlx::any::AnyPoolOptions;
    use std::convert::Infallible;
    use std::io::Write;
    use std::sync::Arc;
    use std::time::Duration;
    use tokio_stream::StreamExt;
    use uuid::Uuid;

    async fn store() -> Arc<DiagnosticsStore> {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        Arc::new(DiagnosticsStore::new(pool))
    }

    fn account() -> Account {
        serde_json::from_value(json!({
            "id":7,"name":"合成测试","email":"fixture@example.invalid","status":"active","device_id":"synthetic-device",
            "canonical_env":{"version":"2.1.293"},"canonical_prompt_env":{},"canonical_process":{},"billing_mode":"strip",
            "created_at":now(),"updated_at":now()
        })).unwrap()
    }

    /// 输入拒绝的采集归属随请求持久化，成功收口清除旧失败摘要。
    /// @return 无；零尝试、历史兼容或收口行为改变时失败。
    #[tokio::test]
    async fn rejected_input_is_persisted_without_creating_upstream_attempts() {
        let store = store().await;
        for success in [false, true] {
            let capture_id = Uuid::new_v4().to_string();
            let trace = TraceContext::new(store.clone());
            let guard = RequestTraceGuard::new(trace.clone());
            let response = CURRENT_TRACE
                .scope(trace, async {
                    native_rejection(Some("native_entrypoint_unsupported"), &capture_id, "queued");
                    error_stage("native_prepare");
                    guard.wrap(
                        Response::builder()
                            .status(if success { 200 } else { 422 })
                            .body(Body::empty())
                            .unwrap(),
                    )
                })
                .await;
            let id = response.headers()["x-cc2api-request-id"]
                .to_str()
                .unwrap()
                .to_owned();
            let _ = to_bytes(response.into_body(), 1024).await.unwrap();
            store.flush().await.unwrap();
            let detail = store.detail(&id).await.unwrap();
            assert_eq!(detail.request.attempt_count, 0);
            assert!(detail.attempts.is_empty());
            if success {
                assert!(detail.request.native_rejection.is_none());
            } else {
                let rejection = detail.request.native_rejection.unwrap();
                assert_eq!(
                    rejection.reason.as_deref(),
                    Some("native_entrypoint_unsupported")
                );
                assert_eq!(rejection.capture_id, capture_id);
            }
        }
    }

    /// 本地 503 保留失败边界，通用错误使用兜底阶段，响应和持久摘要保持一致。
    /// @return 无；阶段被覆盖、凭据泄露或虚构尝试时失败。
    #[tokio::test]
    async fn diagnostics_local_503_preserves_failure_stage_and_uses_generic_fallback() {
        let store = store().await;
        for stage in [
            None,
            Some("account_selection"),
            Some("credentials"),
            Some("runtime_prepare"),
            Some("native_prepare"),
        ] {
            let trace = TraceContext::new(store.clone());
            let guard = RequestTraceGuard::new(trace.clone());
            let error = AppError::ServiceUnavailable("合成环境故障".into());
            let response = CURRENT_TRACE
                .scope(trace, async {
                    selected_account(7);
                    if let Some(stage) = stage {
                        error_stage(stage);
                    }
                    guard.error(&error);
                    guard.wrap(error.into_response())
                })
                .await;
            let id = response.headers()["x-cc2api-request-id"]
                .to_str()
                .unwrap()
                .to_owned();
            assert_eq!(response.status(), 503);
            let body = to_bytes(response.into_body(), 1024).await.unwrap();
            assert_eq!(
                serde_json::from_slice::<serde_json::Value>(&body).unwrap(),
                json!({"error":"service unavailable: 合成环境故障"})
            );
            store.flush().await.unwrap();
            let detail = store.detail(&id).await.unwrap();
            assert_eq!(
                detail.request.error_stage.as_deref(),
                Some(stage.unwrap_or("gateway"))
            );
            assert_eq!(detail.request.status_code, Some(503));
            assert_eq!(detail.request.outcome, "local_rejected");
            assert_eq!(detail.request.attempt_count, 0);
            assert!(detail.attempts.is_empty());
            assert!(
                !serde_json::to_string(&detail)
                    .unwrap()
                    .contains("合成环境故障")
            );
        }
    }

    /// 私有提交结果未知时，零观测也保留传输归因和原预留。@return 无。
    #[tokio::test]
    async fn unknown_tui_submission_is_not_a_local_rejection() {
        let store = store().await;
        let trace = TraceContext::new(store.clone());
        let guard = RequestTraceGuard::new(trace.clone());
        let reservation = Uuid::new_v4().to_string();
        let response = CURRENT_TRACE
            .scope(trace, async {
                selected_account(7);
                tui_reservation(&reservation);
                tui_submission_unknown();
                let error = AppError::BadGateway("V2 请求提交状态未知".into());
                guard.error(&error);
                guard.wrap(error.into_response())
            })
            .await;
        assert_eq!(response.status(), 502);
        let id = response.headers()["x-cc2api-request-id"]
            .to_str()
            .unwrap()
            .to_owned();
        let _ = to_bytes(response.into_body(), 1024).await.unwrap();
        store.flush().await.unwrap();
        let detail = store.detail(&id).await.unwrap();
        assert_eq!(detail.request.request_id, id);
        assert_eq!(
            detail.request.response_request_id.as_deref(),
            Some(id.as_str())
        );
        assert_eq!(detail.request.outcome, "transport_error");
        assert_eq!(detail.request.error_stage.as_deref(), Some("tui_send_http"));
        assert_eq!(detail.request.status_code, Some(502));
        assert!(detail.request.native_rejection.is_none());
        assert_eq!(detail.request.attempt_count, 0);
        assert!(detail.attempts.is_empty());
        assert_eq!(
            detail.request.context.unwrap().tui_reservation_id,
            Some(reservation)
        );
    }

    /// 入站会话按原值冻结，异常值及重复头保持未知，两种日志模式均可查询。
    #[tokio::test]
    async fn original_session_diagnostics_freeze_ingress_and_validate_boundaries() {
        let store = store().await;
        let cases = [
            (
                Some("json-session".to_owned()),
                vec!["header-session"],
                Some("json-session".to_owned()),
            ),
            (
                Some(" exact-session ".to_owned()),
                vec![],
                Some(" exact-session ".to_owned()),
            ),
            (Some("x".repeat(256)), vec![], Some("x".repeat(256))),
            (Some("x".repeat(257)), vec!["header-session"], None),
            (Some("会".repeat(85)), vec![], Some("会".repeat(85))),
            (Some("会".repeat(86)), vec![], None),
            (Some(" \t ".to_owned()), vec![], None),
            (Some("session\ncontrol".to_owned()), vec![], None),
            (
                None,
                vec!["header-session"],
                Some("header-session".to_owned()),
            ),
            (None, vec!["header-session", "header-session"], None),
            (None, vec![], None),
        ];
        for mode in [RequestLogMode::Info, RequestLogMode::Debug] {
            for (session, values, expected) in &cases {
                CURRENT_LOG_MODE.scope(mode, async {
                    let trace = TraceContext::new(store.clone());
                    let id = trace.lock().request.request_id.clone();
                    let guard = RequestTraceGuard::new(trace.clone());
                    let mut headers = HeaderMap::new();
                    for value in values {
                        headers.append("x-claude-code-session-id", HeaderValue::from_str(value).unwrap());
                    }
                    let body = session.as_ref().map(|session| json!({"metadata":{"user_id":json!({"session_id":session}).to_string()}})).unwrap_or_else(|| json!({}));
                    let response = CURRENT_TRACE.scope(trace, async {
                        claude_request_session(&RequestSession::claude(None, &headers, &body), &body);
                        // 后续解析与映射只能补充匿名尝试，不能改写入口原值或未知结果。
                        let later = json!({"metadata":{"user_id":"user_session_later-session"}});
                        claude_request_session(&RequestSession::claude(None, &HeaderMap::new(), &later), &later);
                        session_context(7, Some("mapped-session"), None);
                        local_outcome("mock");
                        guard.wrap(Response::new(Body::empty()))
                    }).await;
                    to_bytes(response.into_body(), 1024).await.unwrap();
                    store.flush().await.unwrap();
                    let detail = store.detail(&id).await.unwrap();
                    assert_eq!(&detail.request.original_session_id, expected);
                    assert_eq!(detail.request.log_mode, Some(mode));
                    assert_eq!(detail.request.outcome, "mock");
                    assert!(detail.attempts.is_empty());
                    let page = store.list(DiagnosticQuery { correlation_id: Some(id), ..Default::default() }).await.unwrap();
                    assert_eq!(&page.items[0].original_session_id, expected);
                }).await;
            }
        }
        for (body, headers, expected) in [
            (
                json!({"metadata":{"user_id":"user_synthetic_session_legacy-session"}}),
                HeaderMap::new(),
                Some("legacy-session"),
            ),
            (
                json!({}),
                HeaderMap::from_iter([(
                    "x-claude-code-session-id".parse().unwrap(),
                    HeaderValue::from_bytes(b"\xff").unwrap(),
                )]),
                None,
            ),
        ] {
            let trace = TraceContext::new(store.clone());
            CURRENT_TRACE
                .scope(trace.clone(), async {
                    claude_request_session(&RequestSession::claude(None, &headers, &body), &body);
                })
                .await;
            assert_eq!(
                trace.lock().request.original_session_id.as_deref(),
                expected
            );
        }
    }

    /// 头部立即到达但首内容延迟时，两项时间分开记录，响应字节保持不变且旧记录可读。
    #[tokio::test]
    async fn first_output_diagnostics_measure_content_after_headers_and_read_old_records() {
        let store = store().await;
        let trace = TraceContext::new(store.clone());
        let guard = RequestTraceGuard::new(trace.clone());
        let scheduler = Arc::new(V3Scheduler::new(Arc::new(SchedulingStore::new(
            AnyPoolOptions::new()
                .connect_lazy("sqlite::memory:")
                .unwrap(),
        ))));
        let first = b"data: {\"type\":\"ping\"}\n\ndata: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":1,\"output_tokens\":0}}}\n\n";
        let output = b"data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"synthetic\"}}\n\ndata: {\"type\":\"message_delta\",\"usage\":{\"output_tokens\":1}}\n\ndata: {\"type\":\"message_stop\"}\n\n";
        let response = CURRENT_TRACE
            .scope(trace, async {
                let mut attempt = begin_attempt(&account(), br#"{"stream":true}"#).unwrap();
                attempt.with_feedback(scheduler.begin(0, None));
                let stream = tokio_stream::once(Ok::<_, Infallible>(Bytes::from_static(first)))
                    .chain(tokio_stream::once(Ok(Bytes::from_static(output))).then(
                        |part| async move {
                            tokio::time::sleep(Duration::from_millis(25)).await;
                            part
                        },
                    ));
                let response = Response::new(Body::from_stream(stream));
                attempt.headers(200, response.headers(), vec![]);
                guard.wrap(attempt.wrap(response))
            })
            .await;
        let id = response.headers()["x-cc2api-request-id"]
            .to_str()
            .unwrap()
            .to_owned();
        assert_eq!(
            to_bytes(response.into_body(), 65536)
                .await
                .unwrap()
                .as_ref(),
            [first.as_slice(), output.as_slice()].concat()
        );
        store.flush().await.unwrap();
        let detail = store.detail(&id).await.unwrap();
        let record = &detail.attempts[0];
        assert_eq!(record.outcome, "success");
        assert!(record.first_output_ms.unwrap() >= record.ttft_ms.unwrap() + 20);
        let candidate = SchedulingCandidate {
            account: account(),
            active_units: 0,
            max_units: 8,
            queued: 0,
            queued_units: 0,

            next_send_ms: 0,
        };
        let factor = scheduler
            .factors(&candidate, &scheduler.config(), now_ms())
            .latency;
        assert!(
            (factor - 1.0 / (1.0 + record.first_output_ms.unwrap() as f64 / 10000.0)).abs() < 1e-9
        );
        let mut old = serde_json::to_value(record).unwrap();
        old.as_object_mut().unwrap().remove("first_output_ms");
        let old: AttemptDiagnostic = serde_json::from_value(old).unwrap();
        assert_eq!(old.first_output_ms, None);
        assert_eq!(old.ttft_ms, record.ttft_ms);
    }

    /// 响应包装在请求作用域外仍可收口，原始字节与头值保持不变，记录仅含白名单。
    #[tokio::test]
    async fn diagnostics_preserve_bytes_and_correlate_anonymous_sessions() {
        let store = store().await;
        let trace = TraceContext::new(store.clone());
        let guard = RequestTraceGuard::new(trace.clone());
        let response = CURRENT_TRACE.scope(trace, async {
            profile_selection(true);
            selected_account(7);
            let resolved = UpstreamSessionPoolResolve {real_session_id:"source-session-secret".into(),upstream_session_id:Some("shared-session-secret".into()),
                action:UpstreamSessionPoolAction::Mapped,active_count:4,oldest_last_seen_ms:None,newest_last_seen_ms:None};
            session_context(7, Some("source-session-secret"), Some(&resolved));
            let request = json!({"model":"claude-sonnet-5-5","max_tokens":4096,"thinking":{"type":"enabled","budget_tokens":1024},
                "output_config":{"effort":"high"},"stream":false,"tools":[{"input_schema":{"secret":"tool-input-secret"}}],
                "system":"prompt-secret","messages":[{"role":"user","content":"prompt-secret"}],
                "metadata":{"user_id":json!({"session_id":"shared-session-secret"}).to_string()},"thread":{"previous_message_id":"msg_parent_secret"}});
            let mut attempt = begin_attempt(&account(), &serde_json::to_vec(&request).unwrap()).unwrap();
            let response = Response::builder().header("x-request-id","header-secret").header("request-id","req_fixture123")
                .body(Body::from(r#"{"id":"msg_response_secret","type":"message","model":"claude-sonnet-5-5","stop_reason":"end_turn","content":[{"text":"response-secret"}],"usage":{"input_tokens":123,"output_tokens":8}}"#)).unwrap();
            attempt.headers(200, response.headers(), vec![]);
            guard.wrap(attempt.wrap(response))
        }).await;
        let id = response.headers()["x-cc2api-request-id"]
            .to_str()
            .unwrap()
            .to_owned();
        assert_eq!(response.headers()["x-request-id"], "header-secret");
        let bytes = to_bytes(response.into_body(), 65536).await.unwrap();
        assert!(String::from_utf8_lossy(&bytes).contains("response-secret"));
        store.flush().await.unwrap();
        let detail = store.detail(&id).await.unwrap();
        assert_eq!(detail.request.outcome, "success");
        assert_eq!(detail.attempts.len(), 1);
        let attempt = &detail.attempts[0];
        assert_eq!(attempt.profile_version, "2.1.293");
        assert_eq!(attempt.profile_selection, "client_version");
        assert_eq!(attempt.parameters.max_tokens, Some(4096));
        assert_eq!(attempt.parameters.thinking_budget, Some(1024));
        assert_eq!(attempt.parameters.effort.as_deref(), Some("high"));
        assert_eq!(attempt.parameters.tools_count, Some(1));
        assert_eq!(attempt.tokens.input_tokens, Some(123));
        assert_eq!(attempt.tokens.output_tokens, Some(8));
        assert_eq!(attempt.tokens.cache_read_tokens, None);
        assert_eq!(attempt.stop_reason.as_deref(), Some("end_turn"));
        assert_eq!(attempt.sessions.mapping_action.as_deref(), Some("mapped"));
        assert_ne!(
            attempt.sessions.real_session_hash,
            attempt.sessions.upstream_session_hash
        );
        assert!(attempt.response_message_hash.is_some());
        let serialized = serde_json::to_string(&detail).unwrap();
        for secret in [
            "source-session-secret",
            "shared-session-secret",
            "msg_parent_secret",
            "msg_response_secret",
            "tool-input-secret",
            "prompt-secret",
            "response-secret",
            "header-secret",
            "synthetic-device",
            "fixture@example.invalid",
        ] {
            assert!(!serialized.contains(secret), "诊断不应含合成秘密：{secret}");
        }
        let page = store
            .list(DiagnosticQuery {
                correlation_id: Some("header-secret".into()),
                ..Default::default()
            })
            .await
            .unwrap();
        assert_eq!(page.total, 1);
        assert_eq!(page.items[0].request_id, id);
    }

    /// SSE 内错误、读取异常及客户端取消必须独立于 HTTP 200 判定。
    #[tokio::test]
    async fn diagnostics_record_stream_errors_and_cancellation_once() {
        use crate::service::system_update::CutoverScope;

        let store = store().await;
        for end in ["sse_error", "read_error", "cancelled", "system_update"] {
            let (epoch, receiver) = tokio::sync::watch::channel(None);
            let mut cutover = super::InferenceCutover::new(receiver);
            let trace = TraceContext::new(store.clone()).with_cutover(Some(cutover.clone()));
            let guard = RequestTraceGuard::new(trace.clone());
            let response=CURRENT_TRACE.scope(trace,async {
                let mut attempt=begin_attempt(&account(),br#"{"model":"claude-sonnet-5","stream":true}"#).unwrap();
                let first=Bytes::from_static(b"data: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":10,\"output_tokens\":0}}}\n\n");
                let body=if end=="sse_error" {
                    let tail=Bytes::from_static(b"data: {\"type\":\"error\",\"error\":{\"type\":\"overloaded_error\",\"message\":\"arbitrary-error-secret\"}}\n\n");
                    Body::from_stream(tokio_stream::iter(vec![Ok::<_,Infallible>(first),Ok(tail)]))
                } else if end=="read_error" {
                    Body::from_stream(tokio_stream::iter(vec![Ok(first),Err(std::io::Error::other("arbitrary-error-secret"))]))
                } else {
                    Body::from_stream(tokio_stream::iter(vec![Ok::<_,Infallible>(first)]).chain(tokio_stream::pending()))
                };
                let response=Response::new(body);
                attempt.headers(200,response.headers(),vec![]);
                guard.wrap(attempt.wrap(response))
            }).await;
            let id = response.headers()["x-cc2api-request-id"]
                .to_str()
                .unwrap()
                .to_owned();
            let mut body = response.into_body();
            if matches!(end, "cancelled" | "system_update") {
                assert!(body.frame().await.unwrap().is_ok());
                if end == "system_update" {
                    epoch.send_replace(Some(CutoverScope {
                        epoch: uuid::Uuid::new_v4(),
                        preserve_tui: false,
                    }));
                    cutover.interrupt().await;
                }
                drop(body);
            } else {
                assert_eq!(to_bytes(body, 65536).await.is_err(), end == "read_error");
            }
            store.flush().await.unwrap();
            let detail = store.detail(&id).await.unwrap();
            assert_eq!(detail.attempts.len(), 1);
            assert_eq!(detail.attempts[0].tokens.input_tokens, Some(10));
            assert!(detail.attempts[0].partial);
            assert_eq!(
                detail.request.outcome,
                match end {
                    "sse_error" => "upstream_error",
                    "read_error" => "body_error",
                    _ => "cancelled",
                }
            );
            if end == "read_error" {
                assert_eq!(detail.request.error_stage.as_deref(), Some("upstream_body"));
            }
            if matches!(end, "cancelled" | "system_update") {
                let (request_stage, attempt_stage) = if end == "system_update" {
                    ("system_update", "system_update")
                } else {
                    ("downstream_body", "upstream_body")
                };
                assert_eq!(detail.request.error_stage.as_deref(), Some(request_stage));
                assert_eq!(
                    detail.attempts[0].error_stage.as_deref(),
                    Some(attempt_stage)
                );
                assert_eq!(detail.request.status_code, Some(200));
            }
            assert!(
                !serde_json::to_string(&detail)
                    .unwrap()
                    .contains("arbitrary-error-secret")
            );
        }
    }

    /// 请求准备阶段取消和后台异步写入故障不改变业务响应。
    #[tokio::test]
    async fn diagnostics_cover_early_cancellation_and_unavailable_storage() {
        let store = store().await;
        let trace = TraceContext::new(store.clone());
        let id = trace.lock().request.request_id.clone();
        drop(RequestTraceGuard::new(trace));
        store.flush().await.unwrap();
        assert_eq!(
            store.detail(&id).await.unwrap().request.outcome,
            "cancelled"
        );
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        let unavailable = Arc::new(DiagnosticsStore::new(pool.clone()));
        let trace = TraceContext::new(unavailable.clone());
        let response =
            RequestTraceGuard::new(trace).wrap(Response::new(Body::from("正常业务结果")));
        // 关闭连接池后，诊断写入失败也不能阻断已经构造的业务响应。
        pool.close().await;
        assert_eq!(
            to_bytes(response.into_body(), 1024).await.unwrap(),
            "正常业务结果"
        );
        unavailable.flush().await.unwrap();
        assert!(unavailable.list(DiagnosticQuery::default()).await.is_err());
    }

    /// 既有缓冲分支复用相同解码与事件解析，传输未完成时仍保守终结。
    /// @return 无；重复终结、丢用量或根状态错误时失败。
    #[tokio::test]
    async fn diagnostics_buffered_compression_uses_the_same_event_observer() {
        let source = b"data: {\"type\":\"message_start\",\rdata: \"message\":{\"model\":\"claude-sonnet-5\",\"usage\":{\"input_tokens\":123,\"output_tokens\":0}}}\r\rdata: {\"type\":\"message_delta\",\"usage\":{\"output_tokens\":8}}\r\rdata: {\"type\":\"message_stop\"}\r\r";
        let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(source).unwrap();
        let wire = encoder.finish().unwrap();
        let store = store().await;
        for complete in [true, false] {
            let trace = TraceContext::new(store.clone());
            let guard = RequestTraceGuard::new(trace.clone());
            let response = CURRENT_TRACE
                .scope(trace, async {
                    let mut attempt =
                        begin_attempt(&account(), br#"{"model":"claude-sonnet-5"}"#).unwrap();
                    let response = Response::builder()
                        .header("content-encoding", "gzip")
                        .body(Body::from(wire.clone()))
                        .unwrap();
                    attempt.headers(200, response.headers(), vec!["gzip".into()]);
                    attempt.buffered(&wire, complete);
                    drop(attempt);
                    guard.wrap(response)
                })
                .await;
            let id = response.headers()["x-cc2api-request-id"]
                .to_str()
                .unwrap()
                .to_owned();
            assert_eq!(to_bytes(response.into_body(), 4096).await.unwrap(), wire);
            store.flush().await.unwrap();
            let detail = store.detail(&id).await.unwrap();
            assert_eq!(detail.attempts.len(), 1);
            let attempt = &detail.attempts[0];
            assert_eq!(attempt.tokens.input_tokens, Some(123));
            assert_eq!(attempt.tokens.output_tokens, Some(8));
            assert_eq!(attempt.partial, !complete);
            assert_eq!(
                attempt.outcome,
                if complete { "success" } else { "body_error" }
            );
            assert_eq!(detail.request.outcome, attempt.outcome);
        }
        assert_eq!(
            store.list(DiagnosticQuery::default()).await.unwrap().total,
            2
        );
    }

    /// 显式标准化的 V2 流已接收的真实用量可见，200 错误帧仍标记失败。@return 无。
    #[tokio::test]
    async fn gateway_id_diagnostics_records_stream_error_not_success() {
        let store = store().await;
        let trace = TraceContext::new(store.clone());
        let guard = RequestTraceGuard::new(trace.clone());
        let wire = br#"data: {"type":"message_start","message":{"id":"msg_synthetic","usage":{"input_tokens":5,"output_tokens":2,"cache_read_input_tokens":3}}}

event: error
data: {"type":"error","error":{"type":"overloaded_error","message":"synthetic failure"}}

"#;
        let response = CURRENT_TRACE
            .scope(trace, async {
                let resolved = UpstreamSessionPoolResolve {
                    real_session_id: "source-session".into(),
                    upstream_session_id: Some("pool-session".into()),
                    action: UpstreamSessionPoolAction::Mapped,
                    active_count: 1,
                    oldest_last_seen_ms: None,
                    newest_last_seen_ms: None,
                };
                session_context(7, Some("source-session"), Some(&resolved));
                let body = json!({"model":"claude-sonnet-5","stream":true,
                    "metadata":{"user_id":json!({"session_id":"source-session"}).to_string()}});
                let mut attempt = prepare_tui_attempt(&account(), &body).unwrap();
                attempt.commit();
                let response =
                    ([("content-type", "text/event-stream")], wire.as_slice()).into_response();
                attempt.headers(200, response.headers(), Vec::new());
                guard.wrap(attempt.wrap(response))
            })
            .await;
        let root = response.headers()["x-cc2api-request-id"]
            .to_str()
            .unwrap()
            .to_owned();
        assert_eq!(
            to_bytes(response.into_body(), 1024).await.unwrap(),
            wire.as_slice()
        );
        store.flush().await.unwrap();
        let detail = store.detail(&root).await.unwrap();
        assert_eq!(detail.request.outcome, "upstream_error");
        let attempt = &detail.attempts[0];
        assert_eq!(attempt.outcome, "upstream_error");
        assert_eq!(attempt.error_type.as_deref(), Some("overloaded_error"));
        assert_eq!(attempt.tokens.cache_read_tokens, Some(3));
        assert!(attempt.partial);
        assert_eq!(
            attempt.sessions.real_session_hash,
            Some(identity_hash(7, "session", "source-session"))
        );
        assert_eq!(
            attempt.sessions.upstream_session_hash,
            Some(identity_hash(7, "session", "pool-session"))
        );
        assert_eq!(attempt.sessions.mapping_action.as_deref(), Some("mapped"));
        let context = attempt.context.as_ref().unwrap();
        assert_eq!(context.kernel.as_deref(), Some("tui_v2"));
        assert!(context.kernel_version.is_none());
    }

    /// V2 独立模型错误仍有尝试记录，宿主订阅的调度健康分只接受可归属的反馈。
    #[tokio::test]
    async fn tui_local_auth_and_rate_errors_keep_account_health_on_stream_and_http_failure() {
        let store = store().await;
        let scheduler = Arc::new(V3Scheduler::new(Arc::new(SchedulingStore::new(
            AnyPoolOptions::new()
                .connect_lazy("sqlite::memory:")
                .unwrap(),
        ))));
        let candidate = SchedulingCandidate {
            account: account(),
            active_units: 0,
            max_units: 8,
            queued: 0,
            queued_units: 0,
            next_send_ms: 0,
        };
        for (status, end, kind) in [
            (401, "body_error", "api_error"),
            (403, "body_error", "api_error"),
            (429, "body_error", "rate_limit_error"),
            (200, "complete", "rate_limit_error"),
            (200, "complete", "authentication_error"),
            (200, "complete", "permission_error"),
            (200, "complete", "overloaded_error"),
        ] {
            let trace = TraceContext::new(store.clone());
            CURRENT_TRACE
                .scope(trace, async {
                    let mut attempt =
                        prepare_tui_attempt(&candidate.account, &json!({"stream":true})).unwrap();
                    attempt.with_feedback(scheduler.begin(0, None));
                    attempt.commit();
                    attempt.headers(status, &HeaderMap::new(), Vec::new());
                    let event = json!({"type":"error","error":{"type":kind,"message":"fixture"}});
                    attempt.observe(format!("event: error\ndata: {event}\n\n").as_bytes());
                    attempt.finish(end);
                })
                .await;
            let health = scheduler
                .factors(&candidate, &scheduler.config(), now_ms())
                .health;
            if kind == "overloaded_error" {
                assert!(health < 1.0);
            } else {
                assert_eq!(health, 1.0, "{status} {kind}");
            }
        }
    }

    /// 损坏压缩、采样超限和非法 JSON 应报告观察缺口，同时保留原始响应。
    #[tokio::test]
    async fn diagnostics_report_observation_failures_without_changing_bytes() {
        let store = store().await;
        for reason in ["decode_error", "sampling_limit", "invalid_payload"] {
            let raw = match reason {
                "decode_error" => b"bad-gzip".to_vec(),
                "sampling_limit" => vec![b'{'; USAGE_BUFFER_LIMIT + 1],
                _ => b"{bad-json".to_vec(),
            };
            let trace = TraceContext::new(store.clone());
            let guard = RequestTraceGuard::new(trace.clone());
            let response = CURRENT_TRACE
                .scope(trace, async {
                    let mut attempt =
                        begin_attempt(&account(), br#"{"model":"claude-sonnet-5"}"#).unwrap();
                    let response = Response::new(Body::from(raw.clone()));
                    attempt.headers(
                        200,
                        response.headers(),
                        if reason == "decode_error" {
                            vec!["gzip".into()]
                        } else {
                            vec![]
                        },
                    );
                    guard.wrap(attempt.wrap(response))
                })
                .await;
            let id = response.headers()["x-cc2api-request-id"]
                .to_str()
                .unwrap()
                .to_owned();
            assert_eq!(
                to_bytes(response.into_body(), USAGE_BUFFER_LIMIT + 2)
                    .await
                    .unwrap(),
                raw
            );
            store.flush().await.unwrap();
            let detail = store.detail(&id).await.unwrap();
            assert_eq!(detail.attempts.len(), 1);
            assert_eq!(detail.attempts[0].error_type.as_deref(), Some(reason));
            assert!(detail.attempts[0].partial);
            assert_eq!(detail.request.outcome, "incomplete");
        }
        assert_eq!(
            store
                .list(DiagnosticQuery::default())
                .await
                .unwrap()
                .health
                .observation_failures,
            3
        );
    }
}
