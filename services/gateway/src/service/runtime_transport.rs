//! v3 账号容器传输边界：复用原 HTTP/TLS 发送规则，不负责协议改写或重试。

use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{Error as IoError, Write};
use std::iter::once;
#[cfg(unix)]
use std::os::unix::fs::OpenOptionsExt;
use std::path::Path;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{LazyLock, Mutex};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::net::TcpListener;
#[cfg(unix)]
use tokio::signal::unix::{SignalKind, signal};
use tokio::sync::{OwnedRwLockReadGuard, RwLock};
use tokio::time::{Instant, timeout, timeout_at};
use uuid::Uuid;

use axum::Json;
use axum::Router;
#[cfg(target_os = "linux")]
use axum::body::to_bytes;
use axum::body::{Body, Bytes};
use axum::extract::{DefaultBodyLimit, Request, State};
use axum::http::header::{
    CONNECTION, CONTENT_ENCODING, CONTENT_LENGTH, CONTENT_TYPE, RETRY_AFTER, USER_AGENT,
};
use axum::http::{HeaderMap, HeaderValue, Method};
use axum::middleware::{Next, from_fn_with_state};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use base64::Engine;
use base64::engine::general_purpose::STANDARD;
use futures_util::StreamExt;
use futures_util::stream::{empty, once as stream_once, unfold};
use regex::Regex;
use reqwest::redirect::Policy;
use reqwest::{Body as RequestBody, Client, Response as PrivateResponse, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;

use crate::error::AppError;
use crate::model::account::{Account, AccountAuthType, TuiSystemPromptPolicy};
use crate::model::request_diagnostics::{ExecutionLocation, RequestLogMode};
use crate::service::account::{AccountService, CredentialActivity};
use crate::service::agy_contract::{
    AGY_REQUEST_SECONDS, AgyAccessSnapshot, AgyModelId, AgyOperation, AgySenderConfig,
    AgySubmission, AgySystemPromptPolicy, AgyToolCompletion, AgyToolContinuationMode,
    AgyWarmPreparation,
};
use crate::service::agy_runtime::AgyPool;
use crate::service::gemini::agy_input_rejection;
use crate::service::native_contract::{NativeIdlePolicy, validate_idle_timeout};
use crate::service::native_contract::{
    NativePreparation, NativePreparationControl, NativePreparationStatus, NativeReadinessStatus,
    NativeSourceVersion,
};
use crate::service::native_runtime::{NativePool, NativeSenderConfig, NativeSubmission};
#[cfg(target_os = "linux")]
use crate::service::request_session::valid_id;
use crate::service::rewriter::{CacheControlTtlRewrite, MessageCacheControlRewrite};
use crate::service::runtime_background::{BACKGROUND_HEADER, BackgroundPurpose};
use crate::service::runtime_bridge::config as runtime_management_config;
use crate::service::tui_backend::TUI_V2;
use crate::service::tui_reconnect::BeforeHeaders;
#[cfg(target_os = "linux")]
use crate::service::tui_sender::TuiSender;
use crate::service::tui_sender_response;
use crate::service::tui_tool_history::{SUGGESTION_SESSION_PREFIX, auxiliary_original_session};
use crate::tlsfp::{
    TlsProfileId, get_background_request_client_for_profile, get_request_client_for_profile,
};

const AGY_TOOL_INPUT_REJECTION: &str = "x-flower2api-agy-input-rejection";
const AGY_TOOL_FINALIZATION_FAILED: &str = "x-flower2api-agy-finalization-failed";
pub(super) const TUI_V2_STATUS_PROTOCOL: u8 = 1;
// 仅由已绑定 sender 的私有 HTTP 回包转递。公开响应白名单不会交付此头。
pub(super) const TUI_GATEWAY_ID_HEADER: &str = "x-v3-tui-message-id-mode";
pub(super) const TUI_CAPTURE: &str = "x-v3-tui-http-capture";
pub(super) const TUI_BODY_SOURCE: &str = "x-v3-tui-body-source";
pub(super) const TUI_OPENING_USAGE_PLACEHOLDER: &str = "x-v3-tui-opening-usage-placeholder";
pub(super) const TUI_SESSION_ORIGIN: &str = "x-v3-tui-session-origin";
pub(super) const TUI_INSTRUCTION_LOCATION: &str = "x-v3-tui-instruction-location";
pub(super) const TUI_FINAL_CAPTURE: &str = "x-v3-tui-final-capture";
pub(super) const TUI_CLI_SUBMISSION: &str = "x-v3-tui-cli-submission";
pub(super) const TUI_UPSTREAM_SESSION: &str = "x-v3-tui-upstream-session";
pub(super) const TUI_TITLE_SESSION_MAPPING: &str = "x-v3-tui-title-session-mapping";
pub(super) const TUI_PROMPT_SUGGESTION: &str = "x-v3-tui-prompt-suggestion";
pub(super) const TUI_MANAGED_OAUTH: &str = "x-v3-tui-managed-oauth";
pub(super) const TUI_SYSTEM_PROMPT_POLICY: &str = "x-v3-tui-system-prompt-policy";
pub(super) const TUI_MODEL_HEADER_POLICY: &str = "x-v3-tui-model-header-policy";
pub(super) const TUI_MODEL_ACCEPT_OMITTED: &str = "x-v3-tui-model-accept-omitted";
pub(super) const TUI_OAUTH_FILE: &str = "x-v3-tui-oauth-file";
pub(super) const TUI_ACCOUNT_EXPIRY: &str = "x-v3-tui-account-expiry";
const TUI_ACCOUNT_MODEL: &str = "x-v3-tui-account-model";
pub(super) const TUI_SIGNATURE_REPAIR: &str = "x-v3-tui-signature-repair";
pub(super) const TUI_REPAIR_ATTEMPT: &str = "x-v3-tui-repair-attempt";
pub(super) const TUI_ERROR_SOURCE: &str = "x-v3-tui-error-source";
pub(super) const TUI_CLI_INPUT_GUARD: &str = "tui_cli_input_guard";
pub(super) const TUI_SENDER_CONFIG: &str = "tui_sender_config";
pub(super) const TUI_PREPARE_LEDGER: &str = "tui_prepare_ledger";
pub(super) const TUI_PREPARE_BIND: &str = "tui_prepare_bind";
pub(super) const TUI_PREPARE_EXCHANGE: &str = "tui_prepare_exchange";
pub(super) const TUI_SEND_CLAIM: &str = "tui_send_claim";
pub(super) const TUI_SUBMISSION_LEDGER: &str = "tui_submission_ledger";
pub(super) const TUI_WORKSPACE_BIND: &str = "tui_workspace_bind";
pub(super) const TUI_JSON_PROJECTION_V1: &str = "gateway-json-v1";
pub(super) const TUI_SSE_PROJECTION_HEADER: &str = "x-v3-tui-sse-projection";
pub(super) const TUI_SSE_PROJECTION_V1: &str = "gateway-sse-v1";
const TUI_LEDGER_REPLY_WINDOW: Duration = Duration::from_millis(250);

/// 限制私有 V2 帧的 Bearer 令牌格式。@param token 账号凭据。@return 是否可安全编码。
pub(super) fn valid_tui_account_token(token: &str) -> bool {
    !token.is_empty()
        && token.len() <= 2048
        && token
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b"-._~+/=".contains(&byte))
}

/// 生成仅供已协商的 sender 使用的凭据头。@param token 账号 AT。@return 标记为敏感的私有头。
pub(super) fn tui_account_token_header(token: &str) -> Result<HeaderValue, AppError> {
    let invalid = || AppError::ServiceUnavailable("V2 账号凭据格式无效".into());
    if !valid_tui_account_token(token) {
        return Err(invalid());
    }
    let mut header = HeaderValue::from_str(token).map_err(|_| invalid())?;
    header.set_sensitive(true);
    Ok(header)
}

/// 按同一次账号读取冻结的完整 V2 OAuth 凭据，仅供已认证的账号发送链使用。
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct TuiOAuthFile {
    pub(super) access_token: String,
    pub(super) refresh_token: String,
    pub(super) expires_at: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) subscription_type: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) rate_limit_tier: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(super) profile: Option<Map<String, Value>>,
}

// 两个既有 2048 字节的令牌及原始账号画像字段走独立帧，避免挤占旧的 4KiB 控制头。
pub(super) const TUI_OAUTH_FILE_LIMIT: usize = 8192;

impl TuiOAuthFile {
    /// 校验本轮快照可以交付。@return 令牌与实际到期时间有效。
    pub(super) fn valid(&self) -> bool {
        self.valid_format() && self.expires_at > now_ms()
    }

    /// 在发送器边界验证线协议结构。@return 凭据字段和毫秒时间均可读取。
    pub(super) fn valid_format(&self) -> bool {
        valid_tui_account_token(&self.access_token)
            && valid_tui_account_token(&self.refresh_token)
            && self.expires_at > 0
            && self
                .subscription_type
                .as_ref()
                .is_none_or(|value| !value.is_empty())
            && self
                .rate_limit_tier
                .as_ref()
                .is_none_or(|value| !value.is_empty())
            && self.profile.as_ref().is_none_or(|profile| {
                !["accessToken", "refreshToken", "expiresAt"]
                    .iter()
                    .any(|key| profile.contains_key(*key))
                    && profile.get("scopes").is_none_or(|scopes| {
                        scopes.as_array().is_some_and(|scopes| {
                            scopes
                                .iter()
                                .all(|value| value.as_str().is_some_and(|scope| !scope.is_empty()))
                        })
                    })
            })
    }

    /// 编码协商后的私有提交头。@return 包含完整凭据的敏感头。
    pub(super) fn header(&self) -> Result<HeaderValue, AppError> {
        let invalid = || AppError::ServiceUnavailable("V2 账号凭据无效或已过期".into());
        if !self.valid() {
            return Err(invalid());
        }
        let payload = serde_json::to_vec(self).map_err(|_| invalid())?;
        if payload.len() > TUI_OAUTH_FILE_LIMIT {
            return Err(invalid());
        }
        let mut header = HeaderValue::from_str(&STANDARD.encode(payload)).map_err(|_| invalid())?;
        header.set_sensitive(true);
        Ok(header)
    }
}

/// 核对已鉴权私有链路的 JSON 委托版本。@param headers 私有头。
/// @return 双方已协商的单值标记是否存在。
pub(super) fn tui_delegates_json(headers: &HeaderMap) -> bool {
    tui_projection_marker(headers, TUI_GATEWAY_ID_HEADER, TUI_JSON_PROJECTION_V1)
}

/// 核对私有协商标记，重复或未知值不构成委托。
/// @param headers 私有头。@param name 头名。@param expected 协商版本。@return 是否明确选择该版本。
pub(super) fn tui_projection_marker(headers: &HeaderMap, name: &str, expected: &str) -> bool {
    let mut values = headers.get_all(name).iter();
    values.next().is_some_and(|value| value == expected) && values.next().is_none()
}

/// 核对账号源在模型认领前发出的 CLI 输入拒绝。@param response 已绑定的私有响应。
/// @return 是否有受信的单值来源和匹配的 HTTP 状态。
pub(super) fn tui_cli_input_rejected(response: &PrivateResponse) -> bool {
    response.status() == StatusCode::UNPROCESSABLE_ENTITY
        && tui_projection_marker(response.headers(), TUI_ERROR_SOURCE, TUI_CLI_INPUT_GUARD)
}

/// 读取已绑定 sender 的单值失败阶段。@param headers 私有响应头。
/// @param permitted 当前私有入口的固定阶段。@return 已核验的阶段。
pub(super) fn tui_failure_stage(
    headers: &HeaderMap,
    permitted: &[&'static str],
) -> Option<&'static str> {
    permitted
        .iter()
        .copied()
        .find(|stage| tui_projection_marker(headers, TUI_ERROR_SOURCE, stage))
}

/// 构造已发出私有提交但尚未确认回复时使用的公开错误。@return 提交状态未知的错误。
pub(super) fn tui_submission_unknown_error() -> AppError {
    AppError::BadGateway("V2 请求提交状态未知".into())
}

/// 内部响应模式，供公开路由采用正文终态记账。
#[derive(Clone)]
pub(super) struct TuiGatewayIds;

/// 已鉴权直发响应的首帧用量由投影补齐。
#[derive(Clone, Copy)]
pub(super) struct TuiOpeningUsagePlaceholder;

const META_HEADER: &str = "x-v3-request";
const ERROR_HEADER: &str = "x-v3-transport-error";
/// 核对可信 sender 在原生提交前的显式拒绝。@param response 绑定的私有响应。@return 未进入发送边界。
pub(super) fn agy_rejected_before_send(response: &reqwest::Response) -> bool {
    response
        .headers()
        .get(ERROR_HEADER)
        .is_some_and(|value| value == "before-send")
}
const NODE_RELAY_PREFIX: &str = "/cluster-transports/v2/";
/// 私有请求最多持有的单调执行预算。
pub(crate) const REQUEST_BUDGET_MS: u64 = 120_000;
/// 绑定校验允许的跨进程墙钟偏差。
pub(crate) const CLOCK_SKEW_MS: u64 = 5_000;

/// 由调度器登记的单账号传输实例；秘密仅用于服务间鉴权。
#[derive(Clone, Deserialize, Serialize)]
pub struct TransportBinding {
    pub account_id: i64,
    pub environment_id: String,
    pub generation: u64,
    pub endpoint: String,
    pub secret: String,
    #[serde(default)]
    pub release_id: String,
}

/// 管理面返回的业务绑定，续轮策略在单次派发内冻结。
#[derive(Deserialize)]
struct RuntimeBinding {
    #[serde(flatten)]
    binding: TransportBinding,
    #[serde(default)]
    agy_tool_continuation_mode: AgyToolContinuationMode,
    #[serde(default)]
    agy_tool_continuation_protocol: u32,
    #[serde(default)]
    agy_generation_seconds: u64,
    #[serde(default)]
    tui_predecessors: Vec<TuiBindingProof>,
    tui_oauth_profile: Option<Map<String, Value>>,
}

/// 编排器核对过的源位置，仅用于比较原绑定，不能访问源发送器。
#[derive(Deserialize)]
struct TuiBindingProof {
    account_id: i64,
    environment_id: String,
    generation: u64,
    endpoint: String,
    release_id: String,
}

impl TuiBindingProof {
    fn key(self) -> String {
        tui_sender_key(
            &TransportBinding {
                account_id: self.account_id,
                environment_id: self.environment_id,
                generation: self.generation,
                endpoint: self.endpoint,
                release_id: self.release_id,
                secret: String::new(),
            },
            false,
        )
    }
}

/// 回切许可依赖实际运行状态，已停止环境应用后继续按需启动。
#[derive(Debug, PartialEq, Eq)]
pub(super) enum TuiRollbackReadiness {
    Running,
    Stopped,
}

#[derive(Deserialize)]
struct TuiRollbackProof {
    scope: TuiBindingProof,
    predecessors: Vec<TuiBindingProof>,
    stopped: bool,
}

/// 请求元信息与原始 body 分开传输，避免重新序列化改变协议字节。
#[derive(Clone, Deserialize, Serialize)]
pub struct PreparedRequest {
    pub account_id: i64,
    pub environment_id: String,
    pub generation: u64,
    pub request_id: String,
    pub deadline_unix_ms: u64,
    pub method: String,
    pub target_url: String,
    pub headers: Vec<(String, String)>,
    pub preserve_header_casing: bool,
    /// 网关冻结的已注册 TLS 标识；历史报文缺字段时保留原内置默认。
    #[serde(default)]
    pub tls_profile: TlsProfileId,
}

/// 账号进程的受限配置；由管理进程原子写入，CLI 用户不可读取。
#[derive(Clone, Deserialize, Serialize)]
pub struct SenderConfig {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agy: Option<AgySenderConfig>,
    #[serde(default)]
    pub native: Option<NativeSenderConfig>,
    #[serde(default)]
    pub native_capture_dir: Option<String>,
    #[serde(default)]
    pub native_adaptive_prewarm: bool,
    pub binding: TransportBinding,
    pub proxy_url: String,
    pub allowed_origin: String,
    #[serde(default)]
    pub evidence_file: Option<String>,
    #[serde(default)]
    pub quota_identity: String,
}

/// 私有 sender 就绪与绑定核验的失败类别。
#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum TuiV2Unavailable {
    NotConfigured,
    NotRunning,
    BindingUnverified,
    MessagesToolAndUsageEventsUnavailable,
    ReadinessUnverified,
    ReadinessConfig,
    ReadinessLedger,
    ReadinessSource,
}

impl TuiV2Unavailable {
    fn into_error(self) -> AppError {
        AppError::ServiceUnavailable(
            match self {
                Self::NotConfigured | Self::NotRunning => "V2 没有已配置并运行的账号发送器",
                Self::BindingUnverified => "V2 账号发送器绑定未通过校验",
                Self::MessagesToolAndUsageEventsUnavailable => {
                    "V2 缺少官方交互终端的完整 Messages 工具和用量事件源"
                }
                Self::ReadinessUnverified
                | Self::ReadinessConfig
                | Self::ReadinessLedger
                | Self::ReadinessSource => "V2 账号发送器就绪状态待核对",
            }
            .into(),
        )
    }

    fn readiness_stage(self) -> &'static str {
        match self {
            Self::BindingUnverified => "tui_v2_binding",
            Self::ReadinessConfig => "tui_readiness_config",
            Self::ReadinessLedger => "tui_readiness_ledger",
            Self::ReadinessSource => "tui_readiness_source",
            _ => "tui_v2_readiness",
        }
    }

    fn admission_branch(self) -> &'static str {
        match self {
            Self::NotConfigured => "tui_readiness_not_configured",
            Self::NotRunning => "tui_readiness_not_running",
            Self::MessagesToolAndUsageEventsUnavailable => "tui_readiness_events_unavailable",
            Self::ReadinessUnverified => "tui_readiness_unverified",
            _ => self.readiness_stage(),
        }
    }
}

fn tui_binding_present(binding: &TransportBinding) -> bool {
    binding.account_id > 0
        && binding.environment_id.len() == 32
        && binding
            .environment_id
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
        && binding.generation > 0
        && !binding.release_id.is_empty()
}

fn tui_v2_sender_status(config: &SenderConfig) -> Value {
    let binding = &config.binding;
    let reason = if !tui_binding_present(binding) {
        TuiV2Unavailable::BindingUnverified
    } else if config.agy.is_some() {
        TuiV2Unavailable::NotConfigured
    } else {
        TuiV2Unavailable::MessagesToolAndUsageEventsUnavailable
    };
    // MessageDisplay 提供已完成的文本行。V2 就绪还需要完整的 Messages 工具和用量事件。
    json!({"protocol": TUI_V2_STATUS_PROTOCOL, "ready": false, "idle": null,
        "reason": reason, "account_id": binding.account_id, "release_id": binding.release_id})
}

fn record_headers(
    config: &SenderConfig,
    prepared: &PreparedRequest,
    upstream: &reqwest::Response,
) -> Result<(), AppError> {
    record_response_headers(
        config,
        prepared,
        upstream.status().as_u16(),
        upstream.headers(),
    )
}

fn record_response_headers(
    config: &SenderConfig,
    prepared: &PreparedRequest,
    status: u16,
    response_headers: &HeaderMap,
) -> Result<(), AppError> {
    let Some(path) = &config.evidence_file else {
        return Ok(());
    };
    let headers: serde_json::Map<String, serde_json::Value> = response_headers
        .iter()
        .filter(|(name, _)| {
            name.as_str().starts_with("anthropic-ratelimit-unified-")
                || name.as_str() == "retry-after"
        })
        .filter_map(|(name, value)| {
            value
                .to_str()
                .ok()
                .map(|value| (name.to_string(), serde_json::json!(value)))
        })
        .collect();
    let record = serde_json::json!({"source": format!("api:{}:{}", config.binding.environment_id, config.quota_identity),
        "identity": config.quota_identity, "origin": "api", "environment_id": config.binding.environment_id,
        "account_id": config.binding.account_id, "generation": config.binding.generation,
        "request_id": prepared.request_id, "ts": now_ms() as f64 / 1000.0,
        "status": status, "headers": headers});
    let path = Path::new(path);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|_| AppError::Internal("API evidence unavailable".into()))?;
    }
    // 有界保留最近证据；消费者按 inode 重置游标，避免长期账号无限增长。
    if fs::metadata(path)
        .map(|value| value.len() >= 16 * 1024 * 1024)
        .unwrap_or(false)
    {
        fs::rename(path, path.with_extension("jsonl.previous"))
            .map_err(|_| AppError::Internal("API evidence rotation unavailable".into()))?;
    }
    let mut options = OpenOptions::new();
    options.create(true).append(true);
    #[cfg(unix)]
    options.mode(0o600);
    let mut file = options
        .open(path)
        .map_err(|_| AppError::Internal("API evidence unavailable".into()))?;
    let mut bytes = serde_json::to_vec(&record)
        .map_err(|_| AppError::Internal("API evidence unavailable".into()))?;
    bytes.push(b'\n');
    file.write_all(&bytes)
        .map_err(|_| AppError::Internal("API evidence unavailable".into()))
}

/// 使用现有客户端发送已经完成改写的请求，不增加重试。
///
/// @param proxy_url 当前账号的上游代理。
/// @param prepared 已冻结的方法、地址和有序请求头。
/// @param body 最终上游 body 字节。
/// @return 上游原始响应；发送失败不表明请求未被上游接受。
pub async fn send_direct(
    proxy_url: &str,
    prepared: &PreparedRequest,
    body: Vec<u8>,
) -> Result<reqwest::Response, AppError> {
    let client = get_request_client_for_profile(proxy_url, prepared.tls_profile)
        .map_err(|_| AppError::BadGateway("upstream request client unavailable".into()))?;
    send_with_client(&client, prepared, body).await
}

async fn send_with_client(
    client: &Client,
    prepared: &PreparedRequest,
    body: impl Into<RequestBody>,
) -> Result<reqwest::Response, AppError> {
    send_observed(client, prepared, body, None, false).await
}

async fn send_observed(
    client: &Client,
    prepared: &PreparedRequest,
    body: impl Into<RequestBody>,
    observer: Option<hyper::ext::AcceptedWrite>,
    tui_account_model: bool,
) -> Result<reqwest::Response, AppError> {
    let method = Method::from_bytes(prepared.method.as_bytes())
        .map_err(|_| AppError::BadRequest("invalid upstream method".into()))?;
    let mut request = client.request(method, &prepared.target_url);
    if let Some(observer) = observer {
        request = request.https_accepted_write(observer);
    }
    if prepared.preserve_header_casing {
        request = request.http1_header_casing(
            prepared
                .headers
                .iter()
                .map(|(name, _)| name.as_str())
                .chain(once("Content-Length")),
        );
    }
    for (name, value) in &prepared.headers {
        if name.eq_ignore_ascii_case("authorization") {
            let mut authorization = HeaderValue::from_str(value)
                .map_err(|_| AppError::BadRequest("上游凭据格式无效".into()))?;
            authorization.set_sensitive(true);
            request = request.header(name, authorization);
        } else if tui_account_model {
            request = request.header(name, tui_header_value(value)?);
        } else {
            request = request.header(name, value);
        }
    }
    request
        .body(body)
        .send()
        .await
        .map_err(|_| AppError::BadGateway("upstream submission status unknown".into()))
}

/// 已完成环境准备的发送通道；不持有正文或发送许可。
pub struct PreparedTransport {
    account_id: i64,
    route: PreparedRoute,
    tool_continuation_mode: AgyToolContinuationMode,
    long_agy_generation: bool,
    tui_predecessors: Vec<TuiBindingProof>,
    tui_oauth_profile: Option<Map<String, Value>>,
}

impl PreparedTransport {
    /// 读取发送器和已选内核共同支持的生成预算。@return 原生生成时长。
    pub(super) fn agy_generation_budget(&self) -> Duration {
        Duration::from_millis(if self.long_agy_generation {
            AGY_REQUEST_SECONDS as u64 * 1000
        } else {
            REQUEST_BUDGET_MS
        })
    }

    /// 核对编排器授予的 AGY 后台绑定。@param account_id 权威账号。
    /// @param binding 已运行或首次获准启动的环境。@param client 内部管理客户端。
    /// @param secret 私有转接认证。@return 只用于当前已确认环境的发送通道。
    pub(super) fn for_agy_preparation(
        account_id: i64,
        binding: TransportBinding,
        client: Client,
        secret: &str,
    ) -> Result<Self, AppError> {
        validate_binding(
            &binding,
            account_id,
            &std::env::var("V3_DEPLOYMENT_ID").unwrap_or_default(),
            &configured_account_release(),
        )?;
        let client = binding_client(client, &binding, secret)?;
        Ok(Self {
            account_id,
            route: PreparedRoute::V3 { client, binding },
            tool_continuation_mode: AgyToolContinuationMode::Claim,
            long_agy_generation: false,
            tui_predecessors: Vec::new(),
            tui_oauth_profile: None,
        })
    }

    /// 只读核对绑定和实际池。@return 当前环境的发送器状态。
    pub(super) async fn agy_preparation_status(&self) -> Result<Value, AppError> {
        let unavailable = || AppError::ServiceUnavailable("agy_status_failed".into());
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Err(unavailable());
        };
        let status: Value = client
            .get(format!("{}/internal/status", binding.endpoint))
            .bearer_auth(&binding.secret)
            .timeout(Duration::from_secs(10))
            .send()
            .await
            .and_then(reqwest::Response::error_for_status)
            .map_err(|_| unavailable())?
            .json()
            .await
            .map_err(|_| unavailable())?;
        if status["environment_id"].as_str() != Some(binding.environment_id.as_str())
            || status["generation"].as_u64() != Some(binding.generation)
            || !status["agy"].is_object()
        {
            return Err(unavailable());
        }
        Ok(status)
    }

    /// 请求同一绑定的零模型热准备。@param request_id 本次控制请求。
    /// @param snapshot 同代 AT。@param deadline 原单调截止。@param capture_enabled 当前采集模式。
    /// @return 已完成真实握手的 PID，业务占用时为空。
    pub(super) async fn warm_agy(
        &self,
        request_id: &str,
        snapshot: AgyAccessSnapshot,
        deadline: Instant,
        capture_enabled: bool,
    ) -> Result<Option<u64>, AppError> {
        let failed = || AppError::ServiceUnavailable("agy_warm_failed".into());
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Err(failed());
        };
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(failed());
        }
        let input = AgyWarmPreparation {
            account_id: self.account_id,
            environment_id: binding.environment_id.clone(),
            generation: binding.generation,
            request_id: request_id.into(),
            deadline_unix_ms: now_ms().saturating_add(remaining.as_millis() as u64),
            credential_snapshot: snapshot,
            capture_enabled,
        };
        let mut response = client
            .post(format!("{}/internal/agy/warm", binding.endpoint))
            .bearer_auth(&binding.secret)
            .json(&input)
            .timeout(remaining)
            .send()
            .await
            .map_err(|_| failed())?;
        if response.status() == StatusCode::NOT_FOUND {
            return Err(AppError::ServiceUnavailable(
                "sender_upgrade_required".into(),
            ));
        }
        if !response.status().is_success() {
            return Err(failed());
        }
        // 准备协议只返回带归属的握手及终态两条短事件。
        let mut body = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|_| failed())? {
            if body.len() + chunk.len() > 4096 {
                return Err(failed());
            }
            body.extend_from_slice(&chunk);
        }
        read_agy_warm_receipt(&body, &input).ok_or_else(failed)
    }

    /// 读取管理面本次派发选择。@return 冻结的工具续轮策略。
    pub(crate) fn tool_continuation_mode(&self) -> AgyToolContinuationMode {
        self.tool_continuation_mode
    }

    /// 向原发送器登记取消，原事件流负责接收实际收口。@param request_id 原尝试。@param api_token_id 原调用方。@param deadline 截止。@return 取消已登记。
    pub(crate) async fn cancel_agy(
        &self,
        request_id: &str,
        api_token_id: i64,
        deadline: Instant,
    ) -> Result<(), AppError> {
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Err(AppError::ServiceUnavailable("原AGY环境不可用".into()));
        };
        let response = timeout_at(
            deadline,
            client
                .post(format!("{}/internal/agy/cancel", binding.endpoint))
                .bearer_auth(&binding.secret)
                .json(&AgyCancellation {
                    account_id: self.account_id,
                    environment_id: binding.environment_id.clone(),
                    generation: binding.generation,
                    request_id: request_id.into(),
                    api_token_id,
                })
                .send(),
        )
        .await
        .map_err(|_| AppError::ServiceUnavailable("AGY取消登记超时".into()))?
        .map_err(|_| AppError::ServiceUnavailable("AGY取消登记待核对".into()))?;
        if response.status() != StatusCode::NO_CONTENT {
            return Err(AppError::ServiceUnavailable("AGY发送器拒绝取消登记".into()));
        }
        Ok(())
    }

    /// 无新凭据地回填原工具轮，并等待真实收口。@param previous 原私有请求。@param api_token_id 原调用方。@param body 真实工具结果。@param deadline 原冻结截止。@param gif_frames 下一轮 GIF 预检策略。@return 原工具已结束。
    pub async fn finish_agy_tools(
        &self,
        previous: &str,
        api_token_id: i64,
        body: Value,
        deadline: Instant,
        gif_frames: bool,
    ) -> Result<(), AppError> {
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Err(AppError::ServiceUnavailable("原AGY环境不可用".into()));
        };
        let id = Uuid::new_v4().to_string();
        let deadline = deadline.min(Instant::now() + Duration::from_millis(REQUEST_BUDGET_MS));
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(AppError::BadRequest("原工具轮已到期".into()));
        }
        let input = AgyToolCompletion {
            request: PreparedRequest {
                account_id: self.account_id,
                environment_id: binding.environment_id.clone(),
                generation: binding.generation,
                request_id: id.clone(),
                deadline_unix_ms: now_ms() + remaining.as_millis() as u64,
                method: "POST".into(),
                target_url: "https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent"
                    .into(),
                headers: vec![],
                preserve_header_casing: false,
                tls_profile: TlsProfileId::default(),
            },
            api_token_id,
            previous_request_id: previous.into(),
            body,
            gif_frames,
        };
        let response = timeout_at(
            deadline,
            client
                .post(format!("{}/internal/agy/tools", binding.endpoint))
                .bearer_auth(&binding.secret)
                .json(&input)
                .send(),
        )
        .await
        .map_err(|_| AppError::ServiceUnavailable("AGY工具回填结果待对账".into()))?
        .map_err(|_| AppError::ServiceUnavailable("AGY工具回填结果待对账".into()))?;
        if !response.status().is_success() {
            if response.status() == StatusCode::BAD_REQUEST {
                if let Some(code) = response
                    .headers()
                    .get(AGY_TOOL_INPUT_REJECTION)
                    .and_then(|header| header.to_str().ok())
                {
                    return Err(agy_input_rejection(code));
                }
            }
            if response.status() == StatusCode::BAD_GATEWAY
                && response
                    .headers()
                    .contains_key(AGY_TOOL_FINALIZATION_FAILED)
            {
                return Err(AppError::AgyToolTurnFailed);
            }
            if response.status().is_server_error() {
                return Err(AppError::ServiceUnavailable(
                    "AGY原工具轮状态暂时不可用".into(),
                ));
            }
            return Err(AppError::BadRequest("AGY原工具轮拒绝回填".into()));
        }
        let result: Value = timeout_at(deadline, response.json())
            .await
            .map_err(|_| AppError::ServiceUnavailable("AGY工具收口超时".into()))?
            .map_err(|_| AppError::ServiceUnavailable("AGY工具收口回执无效".into()))?;
        if result["finished"] != true
            || result["request_id"] != id
            || result["previous_request_id"] != previous
        {
            return Err(AppError::ServiceUnavailable("AGY工具收口归属无效".into()));
        }
        Ok(())
    }
    /// 在既有受信绑定中提交AGY请求。@param request_id 公共请求身份。@param api_token_id 调用方。@param snapshot AT-only快照。@param model 公开模型。@param native_model 观测枚举。@param body 操作正文。@param system_prompt_policy 本HTTP冻结的账号策略。@param deadline 原单调截止。@param capture 采集策略。@param full_egress 保存完整脱敏出站正文。@param gif_frames 冻结的 GIF 策略。@param disable_safety_filtering 冻结的原生安全策略。@param operation 目标操作。@return 持续到原生作业收口的私有事件流。
    pub(super) async fn send_agy(
        &self,
        request_id: &str,
        api_token_id: i64,
        snapshot: AgyAccessSnapshot,
        model: &str,
        native_model: AgyModelId,
        body: Value,
        system_prompt_policy: AgySystemPromptPolicy,
        deadline: Instant,
        capture: bool,
        full_egress: bool,
        gif_frames: bool,
        disable_safety_filtering: bool,
        operation: AgyOperation,
    ) -> Result<reqwest::Response, AppError> {
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Err(AppError::ServiceUnavailable(
                "AGY需要受管账号运行环境".into(),
            ));
        };
        let budget = if operation == AgyOperation::Generate {
            self.agy_generation_budget()
        } else {
            Duration::from_millis(REQUEST_BUDGET_MS)
        };
        let deadline = deadline.min(Instant::now() + budget);
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(AppError::AdmissionLimited { retry_after: 1 });
        }
        let submission = AgySubmission {
            request: PreparedRequest {
                account_id: self.account_id,
                environment_id: binding.environment_id.clone(),
                generation: binding.generation,
                request_id: request_id.into(),
                deadline_unix_ms: now_ms() + remaining.as_millis() as u64,
                method: "POST".into(),
                target_url: "https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent"
                    .into(),
                headers: vec![],
                preserve_header_casing: false,
                tls_profile: TlsProfileId::default(),
            },
            api_token_id,
            credential_snapshot: snapshot,
            model: model.into(),
            native_model,
            body,
            system_prompt_policy,
            capture_enabled: capture,
            full_egress: false,
            gif_frames,
            disable_safety_filtering,
        };
        let mut request = client
            .post(format!("{}{}", binding.endpoint, operation.path()))
            .bearer_auth(&binding.secret)
            .json(&submission);
        if full_egress {
            request = request.header("x-v3-agy-egress-body", "full");
        }
        timeout_at(deadline, request.send())
            .await
            .map_err(|_| AppError::ServiceUnavailable("AGY发送等待超时".into()))?
            .map_err(|_| AppError::BadGateway("AGY提交状态待对账".into()))
    }
}

/// 已确认归属的内部通道或原有直连兼容通道。
enum PreparedRoute {
    Direct(String),
    V3 {
        client: Client,
        binding: TransportBinding,
    },
}

/// 准备传输环境，供 v3 在环境就绪后取得平滑发送许可。
/// @param account 已选定账号。
/// @param preparation_timeout 本请求剩余准入预算。
/// @return 已验证账号、环境、代次和发布归属的通道。
pub async fn prepare(
    account: &Account,
    preparation_timeout: Duration,
) -> Result<PreparedTransport, AppError> {
    let base = std::env::var("V3_RUNTIME_URL").unwrap_or_default();
    if base.is_empty() {
        if !std::env::var("V3_DEPLOYMENT_ID")
            .unwrap_or_default()
            .is_empty()
        {
            return Err(AppError::ServiceUnavailable(
                "v3 runtime is required".into(),
            ));
        }
        return Ok(PreparedTransport {
            account_id: account.id,
            route: PreparedRoute::Direct(account.proxy_url.clone()),
            tool_continuation_mode: AgyToolContinuationMode::Claim,
            long_agy_generation: false,
            tui_predecessors: Vec::new(),
            tui_oauth_profile: None,
        });
    }
    let secret = std::env::var("V3_INTERNAL_TOKEN").map_err(|_| {
        AppError::ServiceUnavailable("v3 runtime authentication unavailable".into())
    })?;
    // 内部传输不继承代理或上游 TLS，也不设置会误杀长流的总超时。
    let client = Client::builder()
        .no_proxy()
        .redirect(Policy::none())
        .no_gzip()
        .no_brotli()
        .no_deflate()
        .connect_timeout(Duration::from_secs(10))
        .build()
        .map_err(|_| AppError::ServiceUnavailable("v3 bridge unavailable".into()))?;
    let deployment = std::env::var("V3_DEPLOYMENT_ID").unwrap_or_default();
    let release = configured_account_release();
    prepare_from_runtime(
        account,
        client,
        &base,
        &secret,
        &deployment,
        &release,
        preparation_timeout,
    )
    .await
}

const TUI_CANDIDATE_RELEASE: &str = "fixture-tui-v2-candidate";

/// 检查是否配置了可信编排登记。@return 是否可读取账号运行绑定。
pub fn tui_runtime_configured() -> bool {
    std::env::var("V3_RUNTIME_URL").is_ok_and(|value| !value.is_empty())
}

/// 检查账号是否属于 Claude 的已配置运行环境。@param account 已授权账号。@return 是否进入切换管控。
pub(crate) fn tui_scope(account: &Account) -> bool {
    account.is_claude_code()
        && if configured_account_release() == TUI_CANDIDATE_RELEASE {
            tui_fixture(account)
        } else {
            tui_runtime_configured()
        }
}

/// 区分显式隔离夹具与正常账号 sender。@param account 已授权账号。@return 是否使用回环夹具。
pub(super) fn tui_fixture(account: &Account) -> bool {
    #[cfg(feature = "tui-v2-candidate")]
    {
        tui_candidate_scope(account)
    }
    #[cfg(not(feature = "tui-v2-candidate"))]
    {
        let _ = account;
        false
    }
}

/// 候选入口只接受显式回环验证运行时及合成账号。@param account 当前账号。@return 是否在候选范围。
#[cfg(feature = "tui-v2-candidate")]
fn tui_candidate_scope(account: &Account) -> bool {
    account.is_claude_code()
        && account.auth_type == AccountAuthType::SetupToken
        && account.setup_token.starts_with("fixture-")
        && tui_candidate_configured()
}

/// 核对显式候选标识与固定回环登记地址。@return 配置是否进入候选范围。
#[cfg(feature = "tui-v2-candidate")]
fn tui_candidate_configured() -> bool {
    configured_account_release() == TUI_CANDIDATE_RELEASE
        && std::env::var("V3_RUNTIME_URL")
            .ok()
            .and_then(|value| reqwest::Url::parse(&value).ok())
            .is_some_and(|url| {
                url.scheme() == "http"
                    && url.host_str() == Some("127.0.0.1")
                    && url.username().is_empty()
                    && url.password().is_none()
                    && url.path() == "/"
                    && url.query().is_none()
                    && url.fragment().is_none()
            })
}

/// sender 预留所需的受信账号、主体、原会话与截止时间。
#[derive(Serialize)]
struct TuiReservationIdentity<'a> {
    account_id: i64,
    environment_id: &'a str,
    generation: u64,
    principal_id: i64,
    session_id: &'a str,
    reservation_id: String,
    deadline_unix_ms: u64,
    continuation_only: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    agent_hint: Option<&'a str>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    agent_summary: bool,
}

#[cfg(feature = "tui-v2-candidate")]
fn tui_candidate_client(binding: &TransportBinding) -> Result<Client, AppError> {
    let endpoint = reqwest::Url::parse(&binding.endpoint)
        .map_err(|_| AppError::ServiceUnavailable("候选 sender 地址无效".into()))?;
    let host = endpoint
        .host_str()
        .filter(|_| {
            endpoint.scheme() == "http" && endpoint.path() == "/" && endpoint.port() == Some(8091)
        })
        .filter(|_| binding.release_id == TUI_CANDIDATE_RELEASE)
        .ok_or_else(|| AppError::ServiceUnavailable("候选 sender 绑定不符".into()))?;
    // 登记仍使用真实 v3 合同，候选数据通道固定解析到当前命名空间的回环。
    Client::builder()
        .no_proxy()
        .http1_only()
        .redirect(Policy::none())
        .resolve(host, std::net::SocketAddr::from(([127, 0, 0, 1], 8091)))
        .build()
        .map_err(|_| AppError::ServiceUnavailable("候选 sender 通道不可用".into()))
}

const TUI_RECEIPT_PROBE_HEADER: &str = "x-v3-tui-receipt-probe";

/// 只在原 sender 的内部状态请求中使用的会话身份。
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct TuiReceiptProbe {
    pub(super) principal_id: i64,
    pub(super) session_id: String,
}

impl TuiReceiptProbe {
    #[cfg(target_os = "linux")]
    fn from_headers(headers: &HeaderMap) -> Result<Option<Self>, AppError> {
        let mut values = headers.get_all(TUI_RECEIPT_PROBE_HEADER).iter();
        let Some(value) = values.next() else {
            return Ok(None);
        };
        let invalid = || AppError::BadRequest("V2 回执探测身份无效".into());
        if values.next().is_some() || value.len() > 2304 {
            return Err(invalid());
        }
        let raw = STANDARD.decode(value.as_bytes()).map_err(|_| invalid())?;
        let probe: Self = serde_json::from_slice(&raw).map_err(|_| invalid())?;
        if probe.principal_id <= 0 || !valid_id(&probe.session_id) {
            return Err(invalid());
        }
        Ok(Some(probe))
    }
}

async fn tui_status(
    client: &Client,
    binding: &TransportBinding,
    fixture: bool,
    probe: Option<&TuiReceiptProbe>,
) -> Result<(bool, bool, bool, bool), TuiV2Unavailable> {
    let mut request = client
        .get(format!(
            "{}/internal/status",
            binding.endpoint.trim_end_matches('/')
        ))
        .bearer_auth(&binding.secret)
        .timeout(Duration::from_secs(2));
    if let Some(probe) = probe {
        let value = serde_json::to_vec(probe).expect("纯会话身份可编码");
        request = request.header(TUI_RECEIPT_PROBE_HEADER, STANDARD.encode(value));
    }
    let response = request
        .send()
        .await
        .map_err(|_| TuiV2Unavailable::ReadinessUnverified)?;
    match response.status() {
        StatusCode::UNAUTHORIZED | StatusCode::FORBIDDEN => {
            return Err(TuiV2Unavailable::BindingUnverified);
        }
        StatusCode::SERVICE_UNAVAILABLE => return Err(TuiV2Unavailable::NotConfigured),
        StatusCode::OK => {}
        _ => return Err(TuiV2Unavailable::ReadinessUnverified),
    }
    let status = response
        .json()
        .await
        .map_err(|_| TuiV2Unavailable::ReadinessUnverified)?;
    let idle = tui_status_snapshot(binding, &status, fixture)?;
    let summary = status["tui_v2"]["agent_summary_protocol"] == 1;
    let system_prompt_policy = status["tui_v2"]["client_system_prompt_policy_protocol"] == 1;
    let direct_https = !fixture && status["tui_v2"]["direct_https_protocol"] == 1;
    if probe.is_some() {
        if !fixture && status["evidence_ok"] != true {
            return Err(TuiV2Unavailable::ReadinessUnverified);
        }
        // 旧 sender 没有逐轮报告，只有完全空闲才能证明原轮已退出。
        return Ok((
            status["tui_v2"]["receipt_idle"].as_bool().unwrap_or(idle),
            summary,
            system_prompt_policy,
            direct_https,
        ));
    }
    Ok((idle, summary, system_prompt_policy, direct_https))
}

fn tui_status_snapshot(
    binding: &TransportBinding,
    status: &Value,
    fixture: bool,
) -> Result<bool, TuiV2Unavailable> {
    let tui = &status["tui_v2"];
    if tui["protocol"] != TUI_V2_STATUS_PROTOCOL {
        return Err(TuiV2Unavailable::ReadinessUnverified);
    }
    if status["environment_id"] != binding.environment_id
        || status["generation"] != binding.generation
        || (!fixture
            && (tui["account_id"] != binding.account_id || tui["release_id"] != binding.release_id))
    {
        return Err(TuiV2Unavailable::BindingUnverified);
    }
    if tui["ready"] == false {
        return Err(serde_json::from_value(tui["reason"].clone())
            .unwrap_or(TuiV2Unavailable::ReadinessUnverified));
    }
    if tui["ready"] != true || (!fixture && tui["event_source"] != "local_unix") {
        return Err(TuiV2Unavailable::ReadinessUnverified);
    }
    let idle = tui["idle"]
        .as_bool()
        .ok_or(TuiV2Unavailable::ReadinessUnverified)?;
    if fixture {
        return Ok(idle);
    }
    let active = status["active"]
        .as_u64()
        .ok_or(TuiV2Unavailable::ReadinessUnverified)?;
    Ok(idle && active == 0)
}

struct TuiTransport {
    client: Client,
    binding: TransportBinding,
    fixture: bool,
    predecessors: Vec<String>,
    tui_oauth_profile: Option<Map<String, Value>>,
}

async fn tui_transport(
    account: &Account,
    wake_wait: Option<Duration>,
    registered: Option<&str>,
    include_profile: bool,
) -> Result<TuiTransport, TuiV2Unavailable> {
    if !tui_scope(account) {
        return Err(TuiV2Unavailable::NotConfigured);
    }
    let fixture = tui_fixture(account);
    let transport = if let Some(wait) = wake_wait {
        prepare(account, wait).await.map(Some)
    } else {
        prepare_existing_binding(account, registered, include_profile).await
    }
    .map_err(|_| TuiV2Unavailable::BindingUnverified)?;
    let Some(PreparedTransport {
        route: PreparedRoute::V3 { client, binding },
        tui_predecessors,
        tui_oauth_profile,
        ..
    }) = transport
    else {
        return Err(TuiV2Unavailable::NotRunning);
    };
    if !tui_binding_present(&binding) || (!fixture && binding.release_id == TUI_CANDIDATE_RELEASE) {
        return Err(TuiV2Unavailable::BindingUnverified);
    }
    #[cfg(feature = "tui-v2-candidate")]
    let client = if fixture {
        tui_candidate_client(&binding).map_err(|_| TuiV2Unavailable::BindingUnverified)?
    } else {
        client
    };
    let predecessors = if fixture {
        Vec::new()
    } else {
        tui_predecessor_keys(&binding, tui_predecessors)
    };
    Ok(TuiTransport {
        client,
        binding,
        fixture,
        predecessors,
        tui_oauth_profile,
    })
}

async fn probe_tui_account(
    account: &Account,
    budget: Duration,
    registered: Option<&str>,
    probe: Option<&TuiReceiptProbe>,
) -> Result<TuiBindingStatus, TuiV2Unavailable> {
    timeout(budget, async {
        let TuiTransport {
            client,
            binding,
            fixture,
            predecessors,
            ..
        } = tui_transport(account, None, registered, false).await?;
        let (idle, _, system_prompt_policy, direct_https) =
            tui_status(&client, &binding, fixture, probe).await?;
        Ok(TuiBindingStatus {
            key: tui_sender_key(&binding, fixture),
            idle,
            system_prompt_policy,
            direct_https,
            predecessors,
        })
    })
    .await
    .map_err(|_| TuiV2Unavailable::ReadinessUnverified)?
}

/// 只探测已经登记的账号 sender。@param account 已授权账号。@return 可核验的绑定和空闲状态。
pub(crate) async fn tui_account_status(account: &Account) -> Result<(String, bool), AppError> {
    probe_tui_account(account, Duration::from_secs(2), None, None)
        .await
        .map(|status| (status.key, status.idle))
        .map_err(TuiV2Unavailable::into_error)
}

/// 当前真实发送器及经控制端授权的前驱。无需启动或重绑定账号。
#[derive(Debug)]
pub(super) struct TuiBindingStatus {
    pub(super) key: String,
    pub(super) idle: bool,
    pub(super) system_prompt_policy: bool,
    pub(super) direct_https: bool,
    predecessors: Vec<String>,
}

impl TuiBindingStatus {
    /// 判断原绑定已获准推进。@param registered 原绑定。@return 本次证据覆盖原登记。
    pub(super) fn can_advance(&self, registered: &str) -> bool {
        tui_same_binding(registered, &self.key)
            || tui_later_generation(registered, &self.key)
            || self
                .predecessors
                .iter()
                .any(|key| tui_same_binding(registered, key))
    }
}

/// 只读查询可用于变更的同账号绑定证明。@param account 账号。@return 当前状态与前驱。
pub(super) async fn tui_transition_status(account: &Account) -> Result<TuiBindingStatus, AppError> {
    probe_tui_account(account, Duration::from_secs(2), None, None)
        .await
        .map_err(TuiV2Unavailable::into_error)
}

/// 核对离开 V2 所需的空闲和原绑定。@param account 当前账号。@param registered 原登记。
/// @return 可切回的实际状态，或等待更多证据。
pub(super) async fn tui_rollback_readiness(
    account: &Account,
    registered: &str,
) -> Result<Option<TuiRollbackReadiness>, AppError> {
    let current = match probe_tui_account(account, Duration::from_secs(2), None, None).await {
        Ok(status) if !status.idle => return Ok(None),
        Ok(status) if status.can_advance(registered) => {
            return Ok(Some(TuiRollbackReadiness::Running));
        }
        Ok(status) => Some(status.key),
        Err(TuiV2Unavailable::NotRunning) => None,
        Err(error) => return Err(error.into_error()),
    };
    let generation = tui_sender_key_parts(registered).map_or(0, |(_, generation, _, _)| generation);
    let (base, secret, client) = runtime_management_config()?;
    let unavailable = || AppError::ServiceUnavailable("V2 回切环境待核对".into());
    let proof = client
        .get(format!("{base}/internal/v3/transport/{}", account.id))
        .query(&[
            ("wake", "false".to_owned()),
            ("tui_rollback_generation", generation.to_string()),
        ])
        .bearer_auth(secret)
        .timeout(Duration::from_secs(2))
        .send()
        .await
        .and_then(reqwest::Response::error_for_status)
        .map_err(|_| unavailable())?
        .json::<Option<TuiRollbackProof>>()
        .await
        .map_err(|_| unavailable())?;
    Ok(proof.and_then(|proof| proof.confirm(account.id, registered, current.as_deref())))
}

impl TuiRollbackProof {
    fn confirm(
        self,
        account: i64,
        registered: &str,
        current: Option<&str>,
    ) -> Option<TuiRollbackReadiness> {
        if self.scope.account_id != account || self.scope.generation == 0 {
            return None;
        }
        let environment = self.scope.environment_id.clone();
        let generation = self.scope.generation;
        let scope = self.scope.key();
        let readiness = match current {
            Some(current) if !self.stopped && current == scope => TuiRollbackReadiness::Running,
            None if self.stopped => TuiRollbackReadiness::Stopped,
            _ => return None,
        };
        // 空闲观测与归属凭据须指向同一个当前发送器。旧版凭据只用于收口原登记。
        let matches =
            |key: &str| tui_same_binding(registered, key) || tui_later_generation(registered, key);
        (matches(&scope)
            || self.predecessors.into_iter().any(|proof| {
                proof.account_id == account
                    && proof.environment_id == environment
                    && proof.generation > 0
                    && (proof.generation < generation
                        || self.stopped && proof.generation == generation)
                    && matches(&proof.key())
            }))
        .then_some(readiness)
    }
}

/// 只核对本轮登记过的实际 sender，包括滚动期间受限保留的旧远端。
/// @param account 原账号。@param registered 回执绑定。@param probe 原轮身份。@return 已认证的 sender 状态。
pub(super) async fn tui_receipt_status(
    account: &Account,
    registered: &str,
    probe: Option<&TuiReceiptProbe>,
) -> Result<TuiBindingStatus, AppError> {
    probe_tui_account(account, Duration::from_secs(4), Some(registered), probe)
        .await
        .map_err(TuiV2Unavailable::into_error)
}

/// 保存切换时按需唤醒同一账号，以实际 sender 状态核对绑定。
/// @param account 本次选择的账号。@return 同账号就绪状态。
pub(super) async fn tui_switch_status(account: &Account) -> Result<TuiBindingStatus, AppError> {
    // 保存可以等待远端只读检查完成，列表和详情仍沿用短预算。
    match probe_tui_account(account, Duration::from_secs(12), None, None).await {
        Err(TuiV2Unavailable::NotRunning) if !tui_fixture(account) => {
            // 查询结果为空只允许按需准备，提交切换仍需核对实际 sender 和原轮归属。
            let sender = ready_tui_sender(
                account,
                Instant::now() + Duration::from_millis(REQUEST_BUDGET_MS),
                true,
                None,
            )
            .await?;
            Ok(TuiBindingStatus {
                key: sender.key,
                idle: sender.idle,
                system_prompt_policy: sender.system_prompt_policy,
                direct_https: sender.direct_https,
                predecessors: sender.predecessors,
            })
        }
        result => result.map_err(TuiV2Unavailable::into_error),
    }
}

fn reject_tui(account: i64, reason: TuiV2Unavailable) -> AppError {
    tracing::warn!(
        layer = "tui_v2",
        account_id = account,
        ?reason,
        "发送前拒绝 V2 请求"
    );
    reason.into_error()
}

/// 诊断未由管理动作绑定的 V2 账号。@param account 已授权账号。@return 发送前的不可用原因。
pub(super) async fn tui_unbound(account: &Account) -> AppError {
    let reason = probe_tui_account(account, Duration::from_secs(2), None, None)
        .await
        .err()
        .unwrap_or(TuiV2Unavailable::BindingUnverified);
    reject_tui(account.id, reason)
}

fn tui_binding_key(binding: &TransportBinding, fixture: bool) -> String {
    if fixture {
        return format!("{}:{}", binding.environment_id, binding.generation);
    }
    // 固定代次、发行和节点分配；私有 bearer 仅留在传输边界。
    format!(
        "v1:{:x}",
        Sha256::digest(
            serde_json::to_vec(&(
                binding.account_id,
                &binding.environment_id,
                binding.generation,
                &binding.release_id,
                &binding.endpoint,
            ))
            .expect("纯绑定字段可编码")
        )
    )
}

fn tui_sender_key(binding: &TransportBinding, fixture: bool) -> String {
    let exact = tui_binding_key(binding, fixture);
    if fixture {
        return exact;
    }
    let digest = exact.strip_prefix("v1:").expect("正式传输绑定带摘要");
    // 远端路径含节点身份和分配修订。本机使用已核验的账号 sender 端点。
    let location = Sha256::digest(
        serde_json::to_vec(&(
            binding.account_id,
            &binding.environment_id,
            &binding.release_id,
            &binding.endpoint,
        ))
        .expect("纯绑定字段可编码"),
    );
    format!(
        "v3:{}:{}:{location:x}:{digest}",
        binding.environment_id, binding.generation
    )
}

fn tui_sender_key_parts(key: &str) -> Option<(&str, u64, &str, &str)> {
    let mut parts = key.strip_prefix("v3:")?.splitn(4, ':');
    Some((
        parts.next()?,
        parts.next()?.parse().ok()?,
        parts.next()?,
        parts.next()?,
    ))
}

fn tui_predecessor_keys(current: &TransportBinding, proofs: Vec<TuiBindingProof>) -> Vec<String> {
    proofs
        .into_iter()
        .take(4)
        .filter_map(|proof| {
            if proof.account_id != current.account_id
                || proof.environment_id != current.environment_id
                || proof.generation == 0
                || proof.generation >= current.generation
                || proof.endpoint.is_empty()
                || proof.release_id.is_empty()
            {
                return None;
            }
            Some(proof.key())
        })
        .collect()
}

/// 确认实际与已登记的完整 sender 绑定相同。@param registered 已保存的键。@param actual 实际键。@return 是否同代同绑定。
pub(super) fn tui_same_binding(registered: &str, actual: &str) -> bool {
    if registered == actual {
        return true;
    }
    let Some((environment, generation, _, exact)) = tui_sender_key_parts(actual) else {
        return false;
    };
    registered.strip_prefix("v1:") == Some(exact)
        || registered == format!("v2:{environment}:{generation}:{exact}")
}

/// 校验账号、环境、发行和节点分配相同且代次严格前进。
/// @param registered 原登记键。@param actual 由当前受信登记生成的键。@return 是否仅推进代次。
pub(super) fn tui_later_generation(registered: &str, actual: &str) -> bool {
    let Some((environment, generation, location, _)) = tui_sender_key_parts(registered) else {
        return false;
    };
    tui_sender_key_parts(actual).is_some_and(|(current, next, binding, _)| {
        environment == current && generation < next && location == binding
    })
}

/// 已核验能力的当前 sender。后续准备直接复用同一已认证传输。
pub(super) struct TuiReadySender {
    client: Client,
    binding: TransportBinding,
    pub(super) key: String,
    pub(super) idle: bool,
    agent_summary: bool,
    system_prompt_policy: bool,
    direct_https: bool,
    predecessors: Vec<String>,
    tui_oauth_profile: Option<Map<String, Value>>,
}

impl TuiReadySender {
    /// 核对当前受信传输是否允许推进原登记。@param registered 旧键。@return 有已授权前驱时为真。
    pub(super) fn can_advance(&self, registered: &str) -> bool {
        tui_later_generation(registered, &self.key)
            || self
                .predecessors
                .iter()
                .any(|key| tui_same_binding(registered, key))
    }
    /// 报告真实 sender 与账号原绑定之间的冲突。@return 提交前的不可用错误。
    pub(super) fn binding_unavailable(&self) -> AppError {
        reject_tui(self.binding.account_id, TuiV2Unavailable::BindingUnverified)
    }
}

/// 解析账号登记并核验 sender 的实际能力。@param account 已授权账号。
/// @param deadline 请求的单调时钟截止。@param wake 是否允许沿编排合同唤醒。
/// @param registered 原回执已登记的绑定。@return 原传输及其就绪证明，新轮只使用当前发行。
pub(super) async fn ready_tui_sender(
    account: &Account,
    deadline: Instant,
    wake: bool,
    registered: Option<&str>,
) -> Result<TuiReadySender, AppError> {
    let deadline_reached = || {
        super::diagnostics::tui_admission_rejected("tui_readiness_deadline");
        AppError::AdmissionLimited { retry_after: 1 }
    };
    let budget = deadline
        .checked_duration_since(Instant::now())
        .ok_or_else(deadline_reached)?;
    let (transport, (idle, agent_summary, system_prompt_policy, direct_https)) = timeout(budget, async {
        let transport = tui_transport(account, wake.then_some(budget), registered, true).await?;
        if registered.is_none()
            && !transport.fixture
            && transport.binding.release_id != configured_account_release()
        {
            // 滚动更新的旧本机绑定仍可被发现。仅已登记回执可以继续使用该发行的发送器。
            return Err(TuiV2Unavailable::BindingUnverified);
        }
        let idle = tui_status(
            &transport.client,
            &transport.binding,
            transport.fixture,
            None,
        )
        .await?;
        Ok((transport, idle))
    })
    .await
    .map_err(|_| deadline_reached())?
    .map_err(|reason| {
        super::diagnostics::tui_admission_rejected(reason.admission_branch());
        super::diagnostics::error_stage(reason.readiness_stage());
        reject_tui(account.id, reason)
    })?;
    let TuiTransport {
        client,
        binding,
        fixture,
        predecessors,
        tui_oauth_profile,
    } = transport;
    let key = tui_sender_key(&binding, fixture);
    Ok(TuiReadySender {
        client,
        binding,
        key,
        idle,
        agent_summary,
        system_prompt_policy,
        direct_https,
        predecessors,
        tui_oauth_profile,
    })
}

/// 预留随本次 Gateway 请求持有，发出提交请求前可通知 sender 取消。
pub(super) struct TuiReservation {
    client: Client,
    binding: TransportBinding,
    identity_header: String,
    admission_deadline: Instant,
    pub(super) attempt_id: String,
    pub(super) capture_state: Option<&'static str>,
    pub(super) wire_capture: bool,
    capture: Option<Bytes>,
    agent_header_used: bool,
    submission_started: bool,
    signature_repair: bool,
    pub(super) repair_pending: bool,
    input_policy: bool,
    model_header_policy: bool,
    session_mapping: bool,
    title_session_mapping: bool,
    upstream_session: Option<String>,
    pub(super) managed_oauth: bool,
    pub(super) oauth_file: bool,
    tui_oauth_profile: Option<Map<String, Value>>,
    pub(super) continuation: bool,
    pub(super) recovered: bool,
}

impl TuiReservation {
    /// 按原预留的账号和已协商模式取本轮凭据。
    /// @param accounts 原账号服务。@param original_tool 是否交还原工具。
    /// @return 私有头、供账号恢复比较的已发 AT，以及覆盖本轮的活动许可。
    pub(super) async fn resolve_account_credentials(
        &self,
        accounts: &AccountService,
        original_tool: bool,
    ) -> Result<(Option<HeaderValue>, Option<String>, CredentialActivity), AppError> {
        let id = self.binding.account_id;
        if self.oauth_file {
            let (mut file, activity) = accounts.resolve_tui_oauth_file(id, original_tool).await?;
            file.profile = self.tui_oauth_profile.clone();
            Ok((Some(file.header()?), Some(file.access_token), activity))
        } else if self.managed_oauth {
            let (bearer, activity) = accounts
                .resolve_tui_upstream_token(id, original_tool)
                .await?;
            Ok((Some(tui_account_token_header(&bearer)?), None, activity))
        } else {
            Ok((
                None,
                None,
                accounts.upstream_tui_activity(id, original_tool).await?,
            ))
        }
    }
    /// 查询原来源是否确认出站会话映射协议。@return 是否支持本轮映射。
    pub(super) fn supports_session_mapping(&self) -> bool {
        self.session_mapping
    }

    /// 查询来源是否可从标题的执行键恢复出站映射的原会话。@return 是否支持标题映射。
    pub(super) fn supports_title_session_mapping(&self) -> bool {
        self.session_mapping && self.title_session_mapping
    }

    /// 设置只在单次提交时传递的账号池结果。@param session 已解析的上游 UUID。
    pub(super) fn set_upstream_session(&mut self, session: &str) {
        debug_assert!(self.session_mapping);
        self.upstream_session = Some(session.to_owned());
    }

    /// 验证会改变隐私或字段准入的请求已由配套源完成准备。@param body 已解析入站。
    /// @return 旧源处理的普通文本可继续；受影响的请求在模型提交前返回升级提示。
    pub(super) fn verify_input_policy(&self, body: &Value) -> Result<(), AppError> {
        if self.input_policy || legacy_tui_input_compatible(body) {
            return Ok(());
        }
        Err(AppError::ServiceUnavailable(
            "当前 V2 sender 或事件源缺少输入校验能力，请升级账号内核".into(),
        ))
    }

    fn request(&self, action: &str) -> reqwest::RequestBuilder {
        self.client
            .post(format!(
                "{}/internal/tui-v2/{action}",
                self.binding.endpoint.trim_end_matches('/')
            ))
            .bearer_auth(&self.binding.secret)
            .header("x-v3-tui-reservation", &self.identity_header)
    }

    /// 只为已协商并启用采集的账号生成本轮入站观察。@param headers 原始入站头。@param raw 解码实体。@param parsed 正文对象。
    pub(super) fn observe_ingress(
        &mut self,
        headers: &HeaderMap,
        raw: &[u8],
        parsed: &Value,
        session_header: Option<&str>,
    ) {
        if self.capture_state == Some("available") {
            let context = [
                self.agent_header_used.then_some("x-claude-code-agent-id"),
                session_header,
            ];
            self.capture = super::native_capture::TuiCaptureInput::encode(
                headers,
                raw,
                parsed,
                &context,
                self.model_header_policy,
            );
            self.capture_state = Some(if self.capture.is_some() {
                "queued"
            } else {
                "dropped"
            });
        }
    }

    /// 使用已准备的单次预留发出实际请求。@param timeout 回包头期限。@return 原 sender 响应。
    #[cfg(test)]
    pub(super) async fn submit(
        mut self,
        ttfb_timeout: Duration,
    ) -> Result<reqwest::Response, AppError> {
        self.submit_with_account_credentials(Instant::now() + ttfb_timeout, None, None)
            .await
    }

    /// 提交原预留，按原来源协商的凭据协议发放本轮凭据。
    /// @param ttfb_deadline 公开回包头截止。@param credentials 敏感私有凭据头。
    /// @param reconnect 已登记可重连的工具回复。@return 原 sender 响应。
    pub(super) async fn submit_with_account_credentials(
        &mut self,
        ttfb_deadline: Instant,
        credentials: Option<HeaderValue>,
        reconnect: Option<&BeforeHeaders>,
    ) -> Result<reqwest::Response, AppError> {
        if self.managed_oauth != credentials.is_some() {
            return Err(AppError::ServiceUnavailable("V2 账号凭据协议未确认".into()));
        }
        // 发出请求后，断连或超时也可能已有 sender 接管。交由 sender 收尾，避免误取消原轮。
        self.submission_started = true;
        // 即使附带受信采集元数据，提交仍使用不可重放的流。
        let request = self
            .request("send")
            .header(TUI_GATEWAY_ID_HEADER, TUI_JSON_PROJECTION_V1)
            .header(TUI_SSE_PROJECTION_HEADER, TUI_SSE_PROJECTION_V1);
        let request = if let Some(credentials) = credentials {
            let name = if self.oauth_file {
                TUI_OAUTH_FILE
            } else {
                TUI_MANAGED_OAUTH
            };
            request.header(name, credentials)
        } else {
            request
        };
        let request = if let Some(session) = &self.upstream_session {
            request.header(TUI_UPSTREAM_SESSION, session)
        } else {
            request
        };
        let request = if let Some(bytes) = self.capture.take() {
            let request = if self.wire_capture { request.header(TUI_FINAL_CAPTURE, "1") } else { request };
            request.header(TUI_CAPTURE, "1")
                .body(reqwest::Body::wrap_stream(futures_util::stream::once(
                    async move { Ok::<_, IoError>(bytes) },
                )))
        } else {
            request.body(reqwest::Body::wrap_stream(empty::<Result<Bytes, IoError>>()))
        };
        // 等账本锁与网关准入共用截止。仅给明确的发送前拒绝留出私有回包时间。
        let reply_deadline = if self.continuation && ttfb_deadline == self.admission_deadline {
            ttfb_deadline + TUI_LEDGER_REPLY_WINDOW
        } else {
            ttfb_deadline
        };
        let private_deadline = Instant::now() + Duration::from_millis(REQUEST_BUDGET_MS);
        let sending = request.send();
        tokio::pin!(sending);
        let response = match timeout_at(reply_deadline, &mut sending).await {
            Ok(response) => response,
            Err(_) => {
                let reconnect = reconnect.ok_or_else(tui_submission_unknown_error)?;
                // 公开 502 后继续同一个不可重放的 HTTP future，保留正在生成的回复。
                reconnect.public_timeout().await;
                timeout_at(private_deadline, &mut sending)
                    .await
                    .map_err(|_| tui_submission_unknown_error())?
            }
        }
        .map_err(|_| tui_submission_unknown_error())?;
        // 定时器与响应可能同时就绪，须按实际观察时间核对迟到的私有回包。
        let observed = Instant::now();
        if observed >= reply_deadline
            || (observed >= ttfb_deadline
                && (response.status() != StatusCode::TOO_MANY_REQUESTS
                    || !tui_projection_marker(
                        response.headers(),
                        TUI_ERROR_SOURCE,
                        TUI_SUBMISSION_LEDGER,
                    )))
        {
            let reconnect = reconnect.ok_or_else(tui_submission_unknown_error)?;
            reconnect.public_timeout().await;
        }
        self.repair_pending = self.signature_repair
            && response.status() == StatusCode::BAD_REQUEST
            && tui_projection_marker(response.headers(), TUI_SIGNATURE_REPAIR, "pending");
        Ok(response)
    }

    /// 恢复已暂停的原轮。@param attempt 额外发送 UUID。@param remaining 原请求剩余时间。
    /// @return 已关联的第二次响应或明确拒绝提交。
    pub(super) async fn submit_signature_repair(
        &mut self,
        attempt: Uuid,
        remaining: Duration,
    ) -> Result<Option<reqwest::Response>, AppError> {
        debug_assert!(self.repair_pending);
        let id = attempt.to_string();
        let request = self
            .request("repair")
            .header(TUI_REPAIR_ATTEMPT, &id)
            .header(TUI_GATEWAY_ID_HEADER, TUI_JSON_PROJECTION_V1)
            .header(TUI_SSE_PROJECTION_HEADER, TUI_SSE_PROJECTION_V1)
            .body(reqwest::Body::wrap_stream(empty::<Result<Bytes, IoError>>()));
        let unknown = || AppError::BadGateway("V2 签名修复提交状态未知".into());
        let response = timeout(remaining, request.send())
            .await
            .map_err(|_| unknown())?
            .map_err(|_| unknown())?;
        if tui_projection_marker(response.headers(), TUI_REPAIR_ATTEMPT, &id) {
            self.repair_pending = false;
            return Ok(Some(response));
        }
        if response.status() == StatusCode::CONFLICT
            && tui_projection_marker(response.headers(), TUI_SIGNATURE_REPAIR, "declined")
        {
            self.repair_pending = false;
            return Ok(None);
        }
        if tui_projection_marker(response.headers(), ERROR_HEADER, "before-send") {
            // 旧中继明确未转发恢复请求，原发送器仍在等待，需要按原预留取消。
            return Ok(None);
        }
        Err(unknown())
    }
}

impl Drop for TuiReservation {
    fn drop(&mut self) {
        if (!self.submission_started || self.repair_pending)
            && let Ok(runtime) = tokio::runtime::Handle::try_current()
        {
            let request = self.request("cancel").timeout(Duration::from_secs(2));
            // 原 sender 按同一预留 ID 幂等取消，并保留自己的有界过期机制。
            runtime.spawn(async move {
                let _ = request.send().await;
            });
        }
    }
}

/// 只采信一份非负十进制秒数，日期已经由实际 HTTP 接收端在收到限流时换算。
fn tui_retry_seconds(headers: &HeaderMap) -> Option<u64> {
    let mut values = headers.get_all(RETRY_AFTER).iter();
    let raw = values.next()?.to_str().ok()?;
    if values.next().is_some() || !raw.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    raw.parse().ok()
}

/// 仅将绑定 Sender 的真实上游认证拒绝交给原账号恢复。
/// @param accounts 账号服务。@param id 原预留账号。@param failed_token 文件模式已发 AT。
/// @param response 受信私有响应头。@return 恢复尝试的生命周期独立于原请求取消。
pub(super) async fn recover_tui_oauth_after_response(
    accounts: &Arc<AccountService>,
    id: i64,
    failed_token: Option<String>,
    response: &reqwest::Response,
) {
    if let Some(token) = failed_token
        && response.status() == StatusCode::UNAUTHORIZED
        && tui_projection_marker(response.headers(), TUI_ERROR_SOURCE, "managed_oauth_http")
    {
        // 保证下一轮能看到拒绝。本轮只等待本地记账，上游刷新随后台任务继续。
        let accounts = accounts.clone();
        let (recorded, ready) = tokio::sync::oneshot::channel();
        tokio::spawn(async move {
            let state = accounts.record_tui_oauth_rejection(id, &token).await;
            let _ = recorded.send(());
            match state {
                Ok(true) => {
                    if accounts
                        .recover_upstream_token_after_unauthorized(id, &token)
                        .await
                        .is_err()
                    {
                        tracing::warn!(account_id = id, "V2 账号凭据恢复待处理");
                    }
                }
                Ok(false) => {}
                Err(_) => tracing::warn!(account_id = id, "V2 账号凭据拒绝登记失败"),
            }
        });
        let _ = ready.await;
    }
}

/// 在 sender 回包头到达之后投影已委托的原始响应，按原始事件判断会话拒答。
/// @param response 绑定且已鉴权的 sender HTTP 响应。@param account_id 正式账号。@return 公开 Messages 响应。
pub(super) async fn tui_public_response(
    response: reqwest::Response,
    account_id: Option<i64>,
) -> Result<Response, AppError> {
    let headers = response.headers();
    let retry_after = (response.status() == StatusCode::TOO_MANY_REQUESTS
        && (tui_projection_marker(headers, TUI_ERROR_SOURCE, "local_provider_http")
            || tui_projection_marker(headers, TUI_ERROR_SOURCE, "managed_oauth_http")
            || tui_projection_marker(headers, TUI_ERROR_SOURCE, TUI_SUBMISSION_LEDGER)
            || tui_projection_marker(headers, TUI_ERROR_SOURCE, TUI_WORKSPACE_BIND)
            || tui_projection_marker(headers, TUI_ERROR_SOURCE, "local_provider_backoff")))
    .then(|| tui_retry_seconds(headers))
    .flatten()
    .map(HeaderValue::from);
    let delegated = if tui_delegates_json(headers) {
        Some("application/json")
    } else if tui_projection_marker(headers, TUI_GATEWAY_ID_HEADER, TUI_SSE_PROJECTION_V1) {
        Some("text/event-stream")
    } else {
        None
    };
    if let Some(content_type) = delegated {
        if !response
            .headers()
            .get(CONTENT_TYPE)
            .is_some_and(|value| value == content_type)
            || response.headers().contains_key(CONTENT_ENCODING)
        {
            return Err(AppError::BadGateway("V2 sender 的委托响应头无效".into()));
        }
        // 私有控制面故障与模型策略拒绝都可能返回 403，仅模型给出的错误触发封禁。
        let policy_account = account_id.filter(|_| {
            response.status().is_success()
                || tui_projection_marker(headers, TUI_ERROR_SOURCE, "local_provider_http")
                || tui_projection_marker(headers, TUI_ERROR_SOURCE, "local_provider_event")
                || tui_projection_marker(headers, TUI_ERROR_SOURCE, "managed_oauth_http")
        });
        // 内部首响应期限已经结束。正文沿 sender 的分块空闲期限和正常化大小预算读取。
        let mut public = tui_sender_response::project_observed(
            response.status(),
            content_type,
            tui_private_body(response),
            policy_account,
        )
        .await?;
        public.extensions_mut().insert(TuiGatewayIds);
        if public.status() == StatusCode::TOO_MANY_REQUESTS
            && let Some(value) = retry_after
        {
            public.headers_mut().insert(RETRY_AFTER, value);
        }
        return Ok(public);
    }
    let mut public = Response::builder().status(response.status());
    if let Some(value) = retry_after {
        public = public.header(RETRY_AFTER, value);
    }
    if response
        .headers()
        .get(TUI_GATEWAY_ID_HEADER)
        .is_some_and(|value| value == "gateway")
    {
        public = public.extension(TuiGatewayIds);
    }
    for name in [CONTENT_TYPE, CONTENT_ENCODING] {
        if let Some(value) = response.headers().get(&name) {
            public = public.header(name, value);
        }
    }
    public
        .body(tui_private_body(response))
        .map_err(|_| AppError::BadGateway("V2 sender 响应头无效".into()))
}

/// 在投影前观察私有 HTTP 正文的实际读取结果。@param response 原私有响应。@return 原字节流。
fn tui_private_body(response: reqwest::Response) -> Body {
    #[cfg(all(target_os = "linux", feature = "v3-verification"))]
    if std::env::var("FLOWER_V2_STARTUP_TRACE").as_deref() == Ok("1") {
        use super::diagnostics::tui_reply_event;

        let result = if response.status().is_success() {
            "received"
        } else {
            "received_error"
        };
        let body = unfold(
            (Box::pin(response.bytes_stream()), false),
            move |(mut source, failed)| async move {
                match source.next().await {
                    Some(frame) => {
                        if frame.is_err() && !failed {
                            tui_reply_event("gateway_tui_private_body", "read_failed");
                        }
                        let failed = failed || frame.is_err();
                        Some((frame, (source, failed)))
                    }
                    None => {
                        if !failed {
                            tui_reply_event("gateway_tui_private_body", result);
                        }
                        None
                    }
                }
            },
        );
        return Body::from_stream(body);
    }
    Body::from_stream(response.bytes_stream())
}

/// 同一公开请求的原文和解析线索；身份、路由与认证始终由预留绑定独立校验。
pub(super) struct TuiMessagesInput<'a> {
    pub body: &'a Bytes,
    pub headers: &'a HeaderMap,
    pub native_cc: bool,
    pub agent_summary: bool,
    pub oauth_file: bool,
    pub body_policy: TuiBodyPolicy,
    pub system_prompt_policy: TuiSystemPromptPolicy,
    pub signature_repair: Option<bool>,
}

/// 仅在已鉴权的预留链路传递本轮生效的系统设置。
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct TuiBodyPolicy {
    sub2api: bool,
    ttl: CacheControlTtlRewrite,
    adaptive: bool,
}

impl TuiBodyPolicy {
    /// 冻结账号源的策略。@param layout 管理员断点策略。@param ttl 断点时长。
    /// @param adaptive 当前模型和顶层 thinking 是否命中兼容设置。@return 仅限本轮的决策。
    pub(super) fn new(
        layout: MessageCacheControlRewrite,
        ttl: CacheControlTtlRewrite,
        adaptive: bool,
    ) -> Self {
        Self {
            sub2api: layout == MessageCacheControlRewrite::Sub2api,
            ttl,
            adaptive,
        }
    }
}

pub(super) const TUI_BODY_POLICY: &str = "x-v3-tui-body-policy";
pub(super) const TUI_INPUT_POLICY: &str = "x-v3-tui-input-policy";
pub(super) const TUI_INPUT_FORMAT: &str = "x-v3-tui-input-format";
const TUI_PREPARE_REASON: &str = "x-v3-tui-prepare-reason";

/// 将受信 V2 准备错误还原为和 V1 一致的状态及错误码。
/// @param reason 源端固定错误码。@return 匹配的公开错误，未知来源值不可披露。
pub(super) fn tui_input_rejection(reason: &str) -> Option<AppError> {
    use StatusCode as S;
    const REASONS: &[(&str, S, &str)] = &[
        ("outstanding_tool", S::CONFLICT, "该轮已开始交付新的工具。请提交该工具 ID 的执行结果后继续"),
        ("recovery_used", S::CONFLICT, "本轮替代生成已提交，请先核对该次响应"),
        ("unrecoverable_tool", S::BAD_REQUEST, "缺少原工具轮的有效恢复记录，请核对原会话和工具结果"),
        ("invalid_header", S::BAD_REQUEST, "请求头格式不合法"),
        ("duplicate_header", S::BAD_REQUEST, "单值协议请求头重复"),
        ("invalid_model", S::BAD_REQUEST, "model 必须为非空字符串"),
        ("invalid_messages", S::BAD_REQUEST, "messages 必须为非空数组"),
        ("invalid_message", S::BAD_REQUEST, "消息角色无效"),
        ("invalid_content", S::BAD_REQUEST, "消息 content 必须为文本或内容块数组"),
        ("invalid_system", S::BAD_REQUEST, "system 必须为文本或文本块数组"),
        ("invalid_tools", S::BAD_REQUEST, "tools 必须为对象数组"),
        ("invalid_max_tokens", S::BAD_REQUEST, "max_tokens 必须为有限数值"),
        ("invalid_temperature", S::BAD_REQUEST, "temperature 必须为有限数值"),
        ("invalid_stream", S::BAD_REQUEST, "stream 必须为布尔值"),
        (
            "invalid_context_management",
            S::BAD_REQUEST,
            "context_management 参数结构不合法",
        ),
        (
            "invalid_metadata",
            S::BAD_REQUEST,
            "metadata 必须含合法的会话信息",
        ),
        (
            "context_conflict",
            S::BAD_REQUEST,
            "metadata 会话与已登记的会话不一致",
        ),
        ("invalid_parameter", S::BAD_REQUEST, "消息参数结构不合法"),
        (
            "unsupported_parameter",
            S::UNPROCESSABLE_ENTITY,
            "当前接口不支持该业务字段或策略",
        ),
        (
            "invalid_native_request",
            S::UNPROCESSABLE_ENTITY,
            "原生 CC 正文格式不合法",
        ),
    ];
    REASONS
        .iter()
        .find(|(code, _, _)| *code == reason)
        .map(|&(code, status, message)| AppError::TuiInput {
            code,
            status,
            message,
        })
}

/// 判断正文是否自报原生 billing 格式。@param body 入站正文。@return 是否含原生格式标记。
pub(super) fn has_tui_billing_marker(body: &Value) -> bool {
    let system = &body["system"];
    let marked = |s: &str| s.trim_start().starts_with("x-anthropic-billing-header:");
    system.as_str().is_some_and(marked)
        || system.as_array().is_some_and(|blocks| {
            blocks
                .iter()
                .any(|block| block["text"].as_str().is_some_and(marked))
        })
}

/// 旧源仅放行已知不会在新合同中删除字段或改变准入的基本 Messages 形状。
fn legacy_tui_input_compatible(body: &Value) -> bool {
    body.as_object().is_some_and(|obj| {
        obj.keys().all(|k| {
            matches!(
                k.as_str(),
                "model"
                    | "messages"
                    | "max_tokens"
                    | "stream"
                    | "tools"
                    | "tool_choice"
                    | "thinking"
                    | "temperature"
                    | "system"
                    | "output_config"
            )
        })
    }) && body["messages"].as_array().is_some_and(|rows| {
        rows.iter().all(|row| {
            row.as_object()
                .is_some_and(|obj| obj.keys().all(|k| matches!(k.as_str(), "role" | "content")))
        })
    }) && !has_tui_billing_marker(body)
        && !body["system"].as_array().is_some_and(|blocks| {
            blocks.iter().any(|block| {
                !block.as_object().is_some_and(|fields| {
                    fields
                        .keys()
                        .all(|key| matches!(key.as_str(), "type" | "text"))
                })
            })
        })
}

/// 无 billing 的原生格式还须匹配固定 CLI 版本和入口，宽泛客户端分类仅用于工具归属。
/// @param headers 原始入口头。@return 已验证的私有来源线索。
pub(super) fn tui_cli_format(headers: &HeaderMap) -> Option<&'static str> {
    static CLI: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(r"^claude-cli/2\.1\.(280|293) \(external, (?:cli|sdk-cli|claude-vscode)(?:, agent-sdk/[0-9A-Za-z.+-]+)?\)$")
            .expect("固定 CLI 来源表达式")
    });
    let mut values = headers.get_all(USER_AGENT).iter();
    let ua = values.next()?.to_str().ok()?;
    if values.next().is_some() {
        return None;
    }
    Some(if &CLI.captures(ua)?[1] == "293" {
        "claude_code"
    } else {
        "claude_code_280"
    })
}

fn tui_agent_hint<'a>(input: &TuiMessagesInput<'a>) -> Result<Option<&'a str>, AppError> {
    if !input.native_cc {
        return Ok(None);
    }
    tui_agent_header(input.headers)
}

/// 读取唯一且有效的原生子代理标识。@param headers 公开入口头。@return 可选的标识。
pub(super) fn tui_agent_header(headers: &HeaderMap) -> Result<Option<&str>, AppError> {
    let mut hints = headers.get_all("x-claude-code-agent-id").iter();
    let Some(value) = hints.next() else {
        return Ok(None);
    };
    let invalid = || AppError::BadRequest("V2 客户端代理标识无效".into());
    let value = value.to_str().map_err(|_| invalid())?;
    if hints.next().is_some() || !super::request_session::valid_id(value) {
        return Err(invalid());
    }
    Ok(Some(value))
}

/// 在取得 HTTP 槽前，让受信 sender 准备原轮或保留新进程。
/// @param sender 同次核验且已按账号登记的传输。@param principal_id 真实入口令牌 ID。
/// @param session_id 已解析的显式会话。@param input 同轮入站正文与协议选项。@param deadline 原请求截止。
/// @param continuation_only 是否只接纳已登记的原轮。@return 绑定原 sender、主体与正文的单次预留。
pub(super) async fn prepare_tui(
    sender: TuiReadySender,
    principal_id: i64,
    session_id: &str,
    input: TuiMessagesInput<'_>,
    deadline: Instant,
    continuation_only: bool,
) -> Result<TuiReservation, AppError> {
    let limited = || AppError::AdmissionLimited { retry_after: 1 };
    let remaining = || {
        deadline
            .checked_duration_since(Instant::now())
            .ok_or_else(limited)
    };
    if input.agent_summary && !sender.agent_summary {
        super::diagnostics::tui_admission_rejected("tui_prepare_agent_summary_capability");
        return Err(AppError::ServiceUnavailable(
            "原生进度请求需要支持独立摘要的账号发送器".into(),
        ));
    }
    let explicit_system_policy =
        !input.native_cc && input.system_prompt_policy != TuiSystemPromptPolicy::Append;
    if explicit_system_policy && !sender.system_prompt_policy {
        super::diagnostics::tui_admission_rejected("tui_prepare_system_prompt_capability");
        return Err(AppError::ServiceUnavailable(
            "原生账号发送器尚未支持客户端系统提示词动作".into(),
        ));
    }
    let TuiReadySender {
        client,
        binding,
        tui_oauth_profile,
        ..
    } = sender;
    let agent_hint = tui_agent_hint(&input)?;
    if agent_hint.is_some()
        && session_id.starts_with(super::tui_tool_history::SERVER_SESSION_PREFIX)
    {
        return Err(AppError::BadRequest(
            "V2 子代理需要已登记的客户端会话".into(),
        ));
    }
    let identity = TuiReservationIdentity {
        account_id: binding.account_id,
        environment_id: &binding.environment_id,
        generation: binding.generation,
        principal_id,
        session_id,
        reservation_id: Uuid::new_v4().to_string(),
        deadline_unix_ms: now_ms().saturating_add(
            remaining()
                .inspect_err(|_| super::diagnostics::tui_admission_rejected("tui_prepare_deadline"))?
                .as_millis() as u64,
        ),
        continuation_only,
        agent_hint,
        agent_summary: input.agent_summary,
    };
    let identity_header = STANDARD.encode(
        serde_json::to_vec(&identity)
            .map_err(|_| AppError::Internal("V2 预留身份编码失败".into()))?,
    );
    let attempt_id = identity.reservation_id.clone();
    super::diagnostics::tui_reservation(&attempt_id);
    let mut reservation = TuiReservation {
        client,
        binding,
        identity_header,
        admission_deadline: deadline,
        attempt_id,
        agent_header_used: agent_hint.is_some(),
        capture_state: None,
        wire_capture: false,
        capture: None,
        input_policy: false,
        model_header_policy: false,
        session_mapping: false,
        title_session_mapping: false,
        upstream_session: None,
        managed_oauth: false,
        oauth_file: false,
        tui_oauth_profile,
        submission_started: false,
        signature_repair: false,
        repair_pending: false,
        continuation: false,
        recovered: false,
    };
    let mut prepare = reservation.request("prepare");
    if let Some(known) = input.signature_repair {
        prepare = prepare.header(TUI_SIGNATURE_REPAIR, if known { "known" } else { "1" });
    }
    if input.oauth_file {
        prepare = prepare.header(TUI_OAUTH_FILE, "1");
    }
    let observe = super::diagnostics::current_log_mode() == RequestLogMode::Debug;
    if observe {
        prepare = prepare.header(TUI_CAPTURE, "1").header(TUI_CLI_SUBMISSION, "1");
        // 辅助轮沿用账号转发正文。这里只观察入口和组装，保留最终写出未采集的边界。
        if auxiliary_original_session(session_id).is_none() {
            prepare = prepare.header(TUI_FINAL_CAPTURE, "1");
        }
    }
    let apply_policy = input.body_policy != TuiBodyPolicy::default();
    if apply_policy {
        prepare = prepare.header(
            TUI_BODY_POLICY,
            serde_json::to_string(&input.body_policy)
                .map_err(|_| AppError::Internal("V2 本轮正文设置无法编码".into()))?,
        );
    }
    if explicit_system_policy {
        prepare = prepare.header(
            TUI_SYSTEM_PROMPT_POLICY,
            input.system_prompt_policy.as_str(),
        );
    }
    if input.native_cc
        && let Some(format) = tui_cli_format(input.headers)
    {
        prepare = prepare.header(TUI_INPUT_FORMAT, format);
    }
    prepare = prepare.header(TUI_MODEL_HEADER_POLICY, "1");
    let model_headers = tui_model_headers(input.headers, true)?;
    // 私有 HTTP 客户端会自动补 Accept；在此保留公开入口筛选后的真实缺省状态。
    if !model_headers.contains_key("accept") {
        prepare = prepare.header(TUI_MODEL_ACCEPT_OMITTED, "1");
    }
    for (name, value) in model_headers {
        prepare = prepare.header(name, tui_header_value(&value)?);
    }
    let response = prepare
        .body(input.body.clone())
        .timeout(remaining()?)
        .send()
        .await
        .map_err(|error| {
            super::diagnostics::error_stage("tui_prepare_http");
            if error.is_timeout() {
                limited()
            } else {
                AppError::ServiceUnavailable("V2 sender 准备通道不可用".into())
            }
        })?;
    if matches!(
        response.status(),
        StatusCode::SERVICE_UNAVAILABLE | StatusCode::TOO_MANY_REQUESTS
    ) {
        let stage = tui_failure_stage(
            response.headers(),
            &[
                TUI_SENDER_CONFIG,
                TUI_PREPARE_LEDGER,
                TUI_PREPARE_BIND,
                TUI_PREPARE_EXCHANGE,
            ],
        );
        if let Some(stage) = stage.or_else(|| {
            (response.status() == StatusCode::SERVICE_UNAVAILABLE).then_some("tui_prepare")
        }) {
            super::diagnostics::error_stage(stage);
        }
    }
    if let Some(error @ AppError::TuiInput { status, .. }) = response
        .headers()
        .get(TUI_PREPARE_REASON)
        .and_then(|value| value.to_str().ok())
        .and_then(tui_input_rejection)
        && response.status() == status
    {
        return Err(error);
    }
    match response.status() {
        StatusCode::NO_CONTENT => {
            if session_id.starts_with(SUGGESTION_SESSION_PREFIX)
                && !tui_projection_marker(response.headers(), TUI_PROMPT_SUGGESTION, "1")
            {
                super::diagnostics::error_stage(TUI_PREPARE_EXCHANGE);
                return Err(AppError::ServiceUnavailable("V2 建议请求需要支持独立建议的账号发送器".into()));
            }
            reservation.managed_oauth =
                tui_projection_marker(response.headers(), TUI_MANAGED_OAUTH, "1");
            reservation.oauth_file = tui_projection_marker(response.headers(), TUI_OAUTH_FILE, "1");
            if reservation.oauth_file && (!input.oauth_file || !reservation.managed_oauth) {
                return Err(AppError::ServiceUnavailable("V2 文件凭据协议不匹配".into()));
            }
            reservation.input_policy =
                tui_projection_marker(response.headers(), TUI_INPUT_POLICY, "1");
            reservation.model_header_policy =
                tui_projection_marker(response.headers(), TUI_MODEL_HEADER_POLICY, "1");
            reservation.session_mapping =
                tui_projection_marker(response.headers(), TUI_UPSTREAM_SESSION, "1");
            reservation.title_session_mapping =
                tui_projection_marker(response.headers(), TUI_TITLE_SESSION_MAPPING, "1");
            reservation.signature_repair = input.signature_repair.is_some()
                && tui_projection_marker(response.headers(), TUI_SIGNATURE_REPAIR, "1");
            if observe {
                reservation.wire_capture = tui_projection_marker(response.headers(), TUI_FINAL_CAPTURE, "1");
                reservation.capture_state = match response
                    .headers()
                    .get(TUI_CAPTURE)
                    .map(HeaderValue::as_bytes)
                {
                    Some(b"1") => Some("available"),
                    Some(b"disabled") => Some("disabled"),
                    _ => None,
                };
            }
            if apply_policy
                && response
                    .headers()
                    .get(TUI_BODY_POLICY)
                    .is_none_or(|v| v != "1")
            {
                return Err(AppError::ServiceUnavailable(
                    "V2 sender 未确认本轮正文设置".into(),
                ));
            }
            if explicit_system_policy
                && !tui_projection_marker(response.headers(), TUI_SYSTEM_PROMPT_POLICY, "1")
            {
                return Err(AppError::ServiceUnavailable(
                    "V2 sender 未确认客户端系统提示词动作".into(),
                ));
            }
            match response
                .headers()
                .get("x-v3-tui-handoff-kind")
                .map(HeaderValue::as_bytes)
            {
                Some(b"continuation") => reservation.continuation = true,
                Some(b"recovered") if continuation_only => {
                    reservation.continuation = true;
                    reservation.recovered = true;
                }
                Some(b"new") if !continuation_only => {}
                _ => {
                    return Err(AppError::ServiceUnavailable(
                        "V2 sender 未确认预留类别".into(),
                    ));
                }
            }
            Ok(reservation)
        }
        StatusCode::TOO_MANY_REQUESTS
            if response
                .headers()
                .get(TUI_PREPARE_REASON)
                .is_some_and(|value| value == "local_provider_backoff") =>
        {
            match tui_retry_seconds(response.headers()) {
                Some(retry_after) => Err(AppError::TuiProviderBackoff { retry_after }),
                None => Err(AppError::BadGateway(
                    "V2 sender 的提供方退避期限无效".into(),
                )),
            }
        }
        StatusCode::TOO_MANY_REQUESTS => Err(limited()),
        StatusCode::UNPROCESSABLE_ENTITY
            if response
                .headers()
                .get(TUI_PREPARE_REASON)
                .is_some_and(|value| value == "subagent_capacity") =>
        {
            Err(AppError::TuiSubagentCapacity)
        }
        StatusCode::UNPROCESSABLE_ENTITY => Err(AppError::TuiInputUnsupported),
        StatusCode::BAD_REQUEST
            if response
                .headers()
                .get(TUI_PREPARE_REASON)
                .is_some_and(|value| value == "subagent_ambiguous") =>
        {
            Err(AppError::TuiSubagentAmbiguous)
        }
        StatusCode::BAD_REQUEST | StatusCode::FORBIDDEN | StatusCode::CONFLICT => {
            Err(AppError::BadRequest("V2 sender 拒绝请求归属".into()))
        }
        _ => Err(AppError::ServiceUnavailable("V2 sender 未准备就绪".into())),
    }
}

const TUI_LEGACY_MODEL_HEADERS: &[&str] = &["anthropic-version", "anthropic-beta"];
const TUI_PROTOCOL_HEADERS: &[&str] = &[
    "anthropic-version",
    "anthropic-beta",
    "accept",
    "accept-language",
    "cache-control",
    "anthropic-dangerous-direct-browser-access",
    "x-claude-code-prev-tool-durations",
    "x-claude-code-compaction",
    "x-claude-code-context-compacted",
];

/// 按协商版本选取 Messages 协议头。@param headers HTTP 入站头。
/// @param full_policy 是否使用 V1 的完整协议头规则。@return 可送往账号事件源的选项。
pub(super) fn tui_model_headers(
    headers: &HeaderMap,
    full_policy: bool,
) -> Result<BTreeMap<&'static str, String>, AppError> {
    let fields = if full_policy {
        TUI_PROTOCOL_HEADERS
    } else {
        TUI_LEGACY_MODEL_HEADERS
    };
    let connection = headers.get_all(CONNECTION);
    let connection_fields: Vec<_> = connection
        .iter()
        .flat_map(|value| value.as_bytes().split(|byte| *byte == b','))
        .map(|name| name.trim_ascii())
        .collect();
    let mut options: BTreeMap<_, String> = BTreeMap::new();
    for &name in fields {
        if full_policy
            && connection_fields
                .iter()
                .any(|field| field.eq_ignore_ascii_case(name.as_bytes()))
        {
            continue;
        }
        for raw in headers.get_all(name) {
            let value = if full_policy {
                // 与 V1 的信封采用同一字节表示，保留合法的 HTTP 扩展字节。
                raw.as_bytes()
                    .trim_ascii()
                    .iter()
                    .copied()
                    .map(char::from)
                    .collect()
            } else {
                raw.to_str()
                    .map_err(|_| AppError::BadRequest("Messages 协议头格式无效".into()))?
                    .trim()
                    .replace('\t', " ")
            };
            match options.get_mut(name) {
                None => {
                    options.insert(name, value);
                }
                Some(previous) if name == "anthropic-beta" => {
                    previous.push(',');
                    previous.push_str(&value);
                }
                Some(previous)
                    if full_policy
                        && matches!(name, "accept" | "accept-language" | "cache-control") =>
                {
                    previous.push_str(", ");
                    previous.push_str(&value);
                }
                Some(_) if full_policy => {
                    return Err(tui_input_rejection("duplicate_header").expect("已登记重复头错误"));
                }
                Some(previous) if *previous == value => {}
                Some(_) => return Err(AppError::BadRequest("Messages 协议版本声明冲突".into())),
            }
        }
    }
    if full_policy
        && options
            .get("anthropic-version")
            .is_some_and(|version| version != "2023-06-01")
    {
        return Err(tui_input_rejection("unsupported_parameter").expect("已登记不支持参数错误"));
    }
    Ok(options)
}

fn tui_header_value(value: &str) -> Result<HeaderValue, AppError> {
    let invalid = || tui_input_rejection("invalid_header").expect("已登记请求头格式错误");
    if value.is_ascii() {
        return HeaderValue::from_str(value).map_err(|_| invalid());
    }
    let bytes = value
        .chars()
        .map(|character| u8::try_from(u32::from(character)))
        .collect::<Result<Vec<_>, _>>()
        .map_err(|_| invalid())?;
    HeaderValue::from_bytes(&bytes).map_err(|_| invalid())
}

/// 只解析已经运行的账号环境，后台准备不会唤醒休眠环境。
/// @param account 当前账号快照。
/// @return 已验证绑定；环境停止或未配置 V3 时为空。
pub(crate) async fn prepare_existing(
    account: &Account,
) -> Result<Option<PreparedTransport>, AppError> {
    prepare_existing_binding(account, None, false).await
}

fn wants_tui_oauth_profile(account: &Account) -> bool {
    account.request_backend == TUI_V2 && account.auth_type == AccountAuthType::Oauth
}

async fn prepare_existing_binding(
    account: &Account,
    registered: Option<&str>,
    include_profile: bool,
) -> Result<Option<PreparedTransport>, AppError> {
    let base = std::env::var("V3_RUNTIME_URL").unwrap_or_default();
    if base.is_empty() {
        return Ok(None);
    }
    let secret = std::env::var("V3_INTERNAL_TOKEN").map_err(|_| {
        AppError::ServiceUnavailable("v3 runtime authentication unavailable".into())
    })?;
    let client = Client::builder()
        .no_proxy()
        .redirect(Policy::none())
        .no_gzip()
        .no_brotli()
        .no_deflate()
        .connect_timeout(Duration::from_secs(5))
        .build()
        .map_err(|_| AppError::ServiceUnavailable("v3 bridge unavailable".into()))?;
    let wire: Option<RuntimeBinding> = client
        .get(format!(
            "{}/internal/v3/transport/{}?wake=false",
            base.trim_end_matches('/'),
            account.id
        ))
        .query(&[(
            "tui_oauth_profile",
            include_profile && wants_tui_oauth_profile(account),
        )])
        .query(
            &registered
                .map(|_| ("tui_previous_release", true))
                .into_iter()
                .collect::<Vec<_>>(),
        )
        .bearer_auth(&secret)
        .timeout(Duration::from_secs(10))
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("运行绑定读取失败".into()))?
        .error_for_status()
        .map_err(|_| AppError::ServiceUnavailable("运行绑定未就绪".into()))?
        .json()
        .await
        .map_err(|_| AppError::ServiceUnavailable("运行绑定无效".into()))?;
    let Some(RuntimeBinding {
        binding,
        tui_predecessors,
        tui_oauth_profile,
        ..
    }) = wire
    else {
        return Ok(None);
    };
    validate_existing_binding(
        &binding,
        account.id,
        &std::env::var("V3_DEPLOYMENT_ID").unwrap_or_default(),
        &configured_account_release(),
        registered,
    )?;
    let client = binding_client(client, &binding, &secret)?;
    Ok(Some(PreparedTransport {
        account_id: account.id,
        route: PreparedRoute::V3 { client, binding },
        tool_continuation_mode: AgyToolContinuationMode::Claim,
        long_agy_generation: false,
        tui_predecessors,
        tui_oauth_profile,
    }))
}

/// 分离配置来源与传输，测试可注入仅解析到回环地址的客户端。
/// @param account 当前账号。
/// @param client 不继承代理的内部客户端。
/// @param base 调度器入口。
/// @param secret 内部鉴权值。
/// @param deployment 部署归属。
/// @param release 发布归属。
/// @param preparation_timeout 剩余准备期限。
/// @return 身份验证后的发送通道。
async fn prepare_from_runtime(
    account: &Account,
    client: Client,
    base: &str,
    secret: &str,
    deployment: &str,
    release: &str,
    preparation_timeout: Duration,
) -> Result<PreparedTransport, AppError> {
    let response = client
        .get(format!(
            "{}/internal/v3/transport/{}",
            base.trim_end_matches('/'),
            account.id
        ))
        .query(&[("tui_oauth_profile", wants_tui_oauth_profile(account))])
        .bearer_auth(secret)
        .timeout(preparation_timeout.min(Duration::from_secs(120)))
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("account environment unavailable".into()))?;
    if !response.status().is_success() {
        // 内部错误仅接受明确资源码，未知状态不能伪装成预算不足。
        let reason = response
            .headers()
            .get("x-v3-runtime-reason")
            .and_then(|value| value.to_str().ok())
            .filter(|value| {
                matches!(
                    *value,
                    "native_sender_budget_missing"
                        | "native_sender_budget_insufficient"
                        | "account_memory_insufficient"
                )
            })
            .unwrap_or("account environment not ready");
        return Err(AppError::ServiceUnavailable(reason.into()));
    }
    let RuntimeBinding {
        binding,
        agy_tool_continuation_mode,
        agy_tool_continuation_protocol,
        agy_generation_seconds,
        tui_predecessors,
        tui_oauth_profile,
    } = response
        .json()
        .await
        .map_err(|_| AppError::ServiceUnavailable("invalid runtime binding".into()))?;
    validate_binding(&binding, account.id, deployment, release)?;
    if agy_tool_continuation_mode != AgyToolContinuationMode::Claim
        && agy_tool_continuation_protocol != 1
    {
        return Err(AppError::ServiceUnavailable(
            "当前 AGY 发送器或请求内核暂不支持所选续轮模式".into(),
        ));
    }
    let client = binding_client(client, &binding, secret)?;
    Ok(PreparedTransport {
        account_id: account.id,
        route: PreparedRoute::V3 { client, binding },
        tool_continuation_mode: agy_tool_continuation_mode,
        long_agy_generation: agy_generation_seconds == AGY_REQUEST_SECONDS as u64,
        tui_predecessors,
        tui_oauth_profile,
    })
}

impl PreparedTransport {
    /// 从已经验证的绑定提取本次实际发送位置，不公开地址或认证材料。
    /// @return 原节点、环境和代次；直连兼容通道为空。
    pub(crate) fn execution_location(&self) -> Option<ExecutionLocation> {
        let PreparedRoute::V3 { binding, .. } = &self.route else {
            return None;
        };
        let endpoint = reqwest::Url::parse(&binding.endpoint).ok()?;
        let (node_key, assignment_revision) =
            if let Some(rest) = endpoint.path().strip_prefix(NODE_RELAY_PREFIX) {
                let parts: Vec<_> = rest.split('/').collect();
                (parts.get(1)?.to_string(), Some(parts.get(3)?.parse().ok()?))
            } else {
                ("local".into(), None)
            };
        Some(ExecutionLocation {
            node_key,
            environment_id: binding.environment_id.clone(),
            generation: binding.generation,
            assignment_revision,
        })
    }

    /// 经已验证运行绑定同步空闲策略，兼容尚在切换的旧sender。
    /// @param seconds 已验证的全局回收秒数。
    /// @return 支持该接口时返回true，旧sender返回false，传输故障返回错误。
    pub(crate) async fn sync_native_idle_timeout(&self, seconds: u64) -> Result<bool, AppError> {
        validate_idle_timeout(seconds)?;
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Err(AppError::ServiceUnavailable("空闲策略需要V3 sender".into()));
        };
        let response = client
            .post(format!(
                "{}/internal/native/idle-policy",
                binding.endpoint.trim_end_matches('/')
            ))
            .bearer_auth(&binding.secret)
            .json(&NativeIdlePolicy {
                account_id: self.account_id,
                environment_id: binding.environment_id.clone(),
                generation: binding.generation,
                idle_timeout_secs: seconds,
            })
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|_| AppError::ServiceUnavailable("空闲策略同步通道不可用".into()))?;
        if response.status() == StatusCode::NOT_FOUND {
            return Ok(false);
        }
        let value: Value = response
            .error_for_status()
            .map_err(|_| AppError::ServiceUnavailable("空闲策略同步失败".into()))?
            .json()
            .await
            .map_err(|_| AppError::ServiceUnavailable("空闲策略回执无效".into()))?;
        if value["ok"] != true || value["idle_timeout_secs"] != seconds {
            return Err(AppError::ServiceUnavailable("空闲策略回执不符".into()));
        }
        Ok(true)
    }

    /// 核对两次只读解析是否仍指向同一受信任 sender。
    /// @param other 当前重新读取的传输绑定。
    /// @return 账号、代次、服务与鉴权配置完全一致时为 true。
    pub(crate) fn same_binding(&self, other: &Self) -> bool {
        match (&self.route, &other.route) {
            (PreparedRoute::V3 { binding: left, .. }, PreparedRoute::V3 { binding: right, .. }) => {
                self.account_id == other.account_id
                    && left.account_id == right.account_id
                    && left.environment_id == right.environment_id
                    && left.generation == right.generation
                    && left.endpoint == right.endpoint
                    && left.secret == right.secret
                    && left.release_id == right.release_id
            }
            _ => false,
        }
    }

    /// 只读取已绑定 sender 的当前身份就绪状态。
    /// @param identity 当前权威账号身份，绑定由此 transport 冻结。
    /// @return 新鲜安全状态；不支持或检查失败时明确报错。
    pub(crate) async fn native_readiness(
        &self,
        mut identity: NativePreparation,
    ) -> Result<NativeReadinessStatus, AppError> {
        identity.source_version.require_executable()?;
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Err(AppError::ServiceUnavailable(
                "原生检查需要 V3 sender".into(),
            ));
        };
        identity.account_id = self.account_id;
        identity.environment_id = binding.environment_id.clone();
        identity.generation = binding.generation;
        let status: NativeReadinessStatus = client
            .post(format!(
                "{}/internal/native/readiness",
                binding.endpoint.trim_end_matches('/')
            ))
            .bearer_auth(&binding.secret)
            .json(&identity)
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|_| AppError::ServiceUnavailable("原生检查通道不可用".into()))?
            .error_for_status()
            .map_err(|_| AppError::ServiceUnavailable("原生检查失败或能力不支持".into()))?
            .json()
            .await
            .map_err(|_| AppError::ServiceUnavailable("原生检查回执无效".into()))?;
        if status.source_version != identity.source_version
            || status.account_id != self.account_id
            || status.environment_id != binding.environment_id
            || status.generation != binding.generation
            || !matches!(
                status.state.as_str(),
                "ready" | "busy" | "preparing" | "unprepared" | "failed"
            )
            || (status.state == "ready" && (status.pid.is_none() || status.idle_workers == 0))
        {
            return Err(AppError::ServiceUnavailable("原生检查回执归属不符".into()));
        }
        Ok(status)
    }

    /// 使用已绑定环境准备一个原生进程，不提交模型作业。
    /// @param preparation 网关冻结的账号身份与准备标识。
    /// @return 真实握手后的准备状态。
    pub(crate) async fn prepare_native(
        &self,
        mut preparation: NativePreparation,
    ) -> Result<NativePreparationStatus, AppError> {
        preparation.source_version.require_executable()?;
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Err(AppError::ServiceUnavailable(
                "原生准备需要 V3 sender".into(),
            ));
        };
        preparation.account_id = self.account_id;
        preparation.environment_id = binding.environment_id.clone();
        preparation.generation = binding.generation;
        let request = client
            .post(format!(
                "{}/internal/native/prepare",
                binding.endpoint.trim_end_matches('/')
            ))
            .bearer_auth(&binding.secret)
            .json(&preparation);
        let response = request
            .timeout(Duration::from_secs(110))
            .send()
            .await
            .map_err(|_| AppError::ServiceUnavailable("原生准备通道不可用".into()))?
            .error_for_status()
            .map_err(|_| AppError::ServiceUnavailable("原生准备失败".into()))?;
        let status: NativePreparationStatus = response
            .json()
            .await
            .map_err(|_| AppError::ServiceUnavailable("原生准备回执无效".into()))?;
        if status.account_id != self.account_id
            || status.environment_id != binding.environment_id
            || status.generation != binding.generation
            || status.preparation_id != preparation.preparation_id
            || status.version != preparation.source_version.as_str()
            || status.raw_input_protocol != 1
            || !matches!(status.state.as_str(), "ready" | "busy")
            || (status.state == "ready" && (status.pid.is_none() || status.idle_workers == 0))
        {
            return Err(AppError::ServiceUnavailable("原生准备回执归属不符".into()));
        }
        Ok(status)
    }

    /// 取消当前绑定中指定的准备，保留在途业务。
    /// @param preparation_id 本次准备 UUID。
    /// @return 已提交取消控制或明确通道错误。
    pub(crate) async fn cancel_native_preparation(
        &self,
        preparation_id: &str,
    ) -> Result<(), AppError> {
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Ok(());
        };
        client
            .post(format!(
                "{}/internal/native/prepare/cancel",
                binding.endpoint.trim_end_matches('/')
            ))
            .bearer_auth(&binding.secret)
            .json(&NativePreparationControl {
                source_version: Default::default(),
                account_id: self.account_id,
                environment_id: binding.environment_id.clone(),
                generation: binding.generation,
                preparation_id: preparation_id.into(),
            })
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .map_err(|_| AppError::ServiceUnavailable("原生准备取消失败".into()))?
            .error_for_status()
            .map_err(|_| AppError::ServiceUnavailable("原生准备取消被拒绝".into()))?;
        Ok(())
    }

    /// 在发送准入之前校验账号原生能力，准备失败不记录模型提交。
    /// @return 已验证原始输入协议和环境代次，或明确准备错误。
    pub async fn native_ready(&self) -> Result<(), AppError> {
        let PreparedRoute::V3 { client, binding } = &self.route else {
            return Err(AppError::ServiceUnavailable(
                "原生方式需要 V3 账号 sender".into(),
            ));
        };
        let capability = client
            .get(format!(
                "{}/internal/native/status",
                binding.endpoint.trim_end_matches('/')
            ))
            .bearer_auth(&binding.secret)
            .send()
            .await
            .map_err(|_| AppError::ServiceUnavailable("原生 sender 能力不可用".into()))?;
        if !capability.status().is_success() {
            return Err(AppError::ServiceUnavailable("原生 sender 准备失败".into()));
        }
        let capability: serde_json::Value = capability
            .json()
            .await
            .map_err(|_| AppError::ServiceUnavailable("原生 sender 能力无效".into()))?;
        if capability["raw_input_protocol"] != 1
            || capability["environment_id"] != binding.environment_id
            || capability["generation"] != binding.generation
        {
            return Err(AppError::ServiceUnavailable(
                "原生 sender 能力或代次不匹配".into(),
            ));
        }
        let version = NativeSourceVersion::Cc293.as_str();
        let available = match capability.get("versions") {
            Some(versions) => versions[version]["available"] == true,
            // 旧的单版 sender 可以省略版本。显式声明的内核仍须匹配。
            None => capability
                .get("version")
                .is_none_or(|declared| declared == version),
        };
        if !available {
            return Err(AppError::ServiceUnavailable(
                "原生运行时 2.1.293 尚未就绪".into(),
            ));
        }
        Ok(())
    }

    /// 向具备原始输入能力的 V3 sender 提交一次请求。
    /// @param submission 已冻结的调用方信封与当前账号授权。
    /// @param ttfb_timeout 包括能力检查及首次响应的预算。
    /// @return 上游响应；缺能力或提交失败时返回明确错误。
    pub async fn submit_native(
        self,
        mut submission: NativeSubmission,
        ttfb_timeout: Duration,
    ) -> Result<reqwest::Response, AppError> {
        submission.source_version.require_executable()?;
        let PreparedRoute::V3 { client, binding } = self.route else {
            return Err(AppError::ServiceUnavailable(
                "原生方式需要 V3 账号 sender".into(),
            ));
        };
        let operation = async {
            submission.request.account_id = self.account_id;
            submission.request.environment_id = binding.environment_id;
            submission.request.generation = binding.generation;
            submission.request.deadline_unix_ms =
                now_ms() + ttfb_timeout.as_millis().min(REQUEST_BUDGET_MS as u128) as u64;
            let response = client
                .post(format!(
                    "{}/internal/native/messages",
                    binding.endpoint.trim_end_matches('/')
                ))
                .bearer_auth(binding.secret)
                .json(&submission)
                .send()
                .await
                .map_err(|_| AppError::BadGateway("原生请求提交状态未知".into()))?;
            if let Some(error) = response.headers().get(ERROR_HEADER) {
                return Err(if error == "before-send" {
                    AppError::ServiceUnavailable("原生请求准备失败".into())
                } else {
                    AppError::BadGateway("原生请求提交状态未知".into())
                });
            }
            Ok(response)
        };
        timeout(ttfb_timeout, operation)
            .await
            .map_err(|_| AppError::BadGateway("原生请求响应超时，提交状态未知".into()))?
    }

    /// 提交冻结请求；调用者必须已经完成本次准入。
    /// @param prepared 不再改写的协议元信息。
    /// @param body 不再修改的原始传输字节。
    /// @param ttfb_timeout 从本次提交开始的响应头期限。
    /// @return 上游响应或提交未知错误；不会自动重放。
    pub async fn submit(
        self,
        prepared: PreparedRequest,
        body: &[u8],
        ttfb_timeout: Duration,
    ) -> Result<reqwest::Response, AppError> {
        self.submit_inner(prepared, body, ttfb_timeout, None).await
    }

    /// 提交固定后台动作，并为整个后台响应保留有界期限。
    /// @param prepared 原冻结请求。
    /// @param body 原字节。
    /// @param ttfb_timeout 原后台期限。
    /// @param purpose 服务端固定动作。
    /// @return 原响应及明确提交边界。
    pub(crate) async fn submit_background(
        self,
        prepared: PreparedRequest,
        body: &[u8],
        ttfb_timeout: Duration,
        purpose: BackgroundPurpose,
    ) -> Result<reqwest::Response, AppError> {
        purpose.validate(&prepared.method, &prepared.target_url)?;
        self.submit_inner(prepared, body, ttfb_timeout, Some(purpose))
            .await
    }

    async fn submit_inner(
        self,
        mut prepared: PreparedRequest,
        body: &[u8],
        ttfb_timeout: Duration,
        purpose: Option<BackgroundPurpose>,
    ) -> Result<reqwest::Response, AppError> {
        let PreparedRoute::V3 { client, binding } = self.route else {
            let PreparedRoute::Direct(proxy_url) = self.route else {
                unreachable!()
            };
            return timeout(
                ttfb_timeout,
                send_direct(&proxy_url, &prepared, body.to_vec()),
            )
            .await
            .map_err(|_| AppError::BadGateway("upstream TTFB timeout".into()))?;
        };
        if prepared.request_id.is_empty() {
            prepared.request_id = Uuid::new_v4().to_string();
        } else if Uuid::parse_str(&prepared.request_id).is_err() {
            return Err(AppError::BadRequest("内部请求标识无效".into()));
        }
        prepared.deadline_unix_ms = now_ms() + ttfb_timeout.as_millis() as u64;
        prepared.account_id = self.account_id;
        prepared.environment_id = binding.environment_id;
        prepared.generation = binding.generation;
        let meta = STANDARD.encode(
            serde_json::to_vec(&prepared)
                .map_err(|_| AppError::Internal("serialize runtime request".into()))?,
        );
        let mut request = client
            .post(format!(
                "{}/internal/send",
                binding.endpoint.trim_end_matches('/')
            ))
            .bearer_auth(binding.secret)
            .header(META_HEADER, meta)
            .body(body.to_vec());
        if let Some(purpose) = purpose {
            request = request
                .header(BACKGROUND_HEADER, purpose.as_str())
                .timeout(ttfb_timeout);
        }
        let response = timeout(ttfb_timeout, request.send())
            .await
            .map_err(|_| AppError::BadGateway("account submission status unknown".into()))?
            .map_err(|_| AppError::BadGateway("account submission status unknown".into()))?;
        if let Some(error) = response.headers().get(ERROR_HEADER) {
            return Err(if error == "before-send" {
                AppError::ServiceUnavailable("account request rejected before submission".into())
            } else {
                AppError::BadGateway("account submission status unknown".into())
            });
        }
        Ok(response)
    }
}

/// 兼容发送入口，环境准备与原有 TTFB 分开计时。
/// @param account 已选定账号。
/// @param prepared 冻结的传输元信息。
/// @param body 原始 body 字节。
/// @param ttfb_timeout 提交后的响应头期限。
/// @return 原有传输响应或错误。
pub async fn send(
    account: &Account,
    prepared: PreparedRequest,
    body: &[u8],
    ttfb_timeout: Duration,
) -> Result<reqwest::Response, AppError> {
    prepare(account, Duration::from_secs(120))
        .await?
        .submit(prepared, body, ttfb_timeout)
        .await
}

/// 获取底座已明确配置的账号来源；legacy 继续使用联合发布身份。
/// @return 当前账号镜像的精确来源批次。
fn configured_account_release() -> String {
    if !std::env::var("V3_UPDATE_GATE_DIR")
        .unwrap_or_default()
        .is_empty()
    {
        return std::env::var("V3_ACCOUNT_RELEASE").unwrap_or_default();
    }
    std::env::var("V3_RELEASE").unwrap_or_default()
}

#[cfg(unix)]
fn authorized_previous_release(
    binding: &TransportBinding,
    deployment: &str,
    release: &str,
) -> bool {
    let Ok(directory) = std::env::var("V3_UPDATE_GATE_DIR") else {
        return false;
    };
    let Ok(control) = std::env::var("V3_RELEASE") else {
        return false;
    };
    let valid_build = control
        .strip_prefix("ci-")
        .and_then(|build| build.split_once('-'))
        .is_some_and(|(run, attempt)| {
            [run, attempt].into_iter().all(|part| {
                part.as_bytes()
                    .first()
                    .is_some_and(|byte| (b'1'..=b'9').contains(byte))
                    && part.bytes().all(|byte| byte.is_ascii_digit())
            })
        });
    if directory.is_empty() || !valid_build {
        return false;
    }
    let path = Path::new(&directory).join(format!("account-rollout-{control}.json"));
    let Ok(record) =
        crate::service::system_update::read_update_record::<Value>(&path, 8 * 1024 * 1024)
    else {
        return false;
    };
    rollout_matches(&record, binding, deployment, &control, release)
}

#[cfg(any(unix, test))]
fn rollout_matches(
    record: &Value,
    binding: &TransportBinding,
    deployment: &str,
    control: &str,
    release: &str,
) -> bool {
    let entry = &record["environments"][&binding.environment_id];
    record["schema_version"] == 1
        && record["deployment"] == deployment
        && record["control_release"] == control
        && record["account_release"] == release
        && entry["gateway_account_id"].as_i64() == Some(binding.account_id)
        && entry["generation"].as_u64() == Some(binding.generation)
        && entry["origin"]["release"] == binding.release_id
        && entry["origin"]["environment_id"] == binding.environment_id
        && entry["origin"]["protocol"] == 1
}

#[cfg(not(unix))]
fn authorized_previous_release(
    _binding: &TransportBinding,
    _deployment: &str,
    _release: &str,
) -> bool {
    false
}

/// 按调度器的短 DNS 名核对部署归属，防止旧前缀条件拒绝合法账号环境。
fn validate_binding(
    binding: &TransportBinding,
    account_id: i64,
    deployment: &str,
    release: &str,
) -> Result<(), AppError> {
    validate_existing_binding(binding, account_id, deployment, release, None)
}

fn validate_existing_binding(
    binding: &TransportBinding,
    account_id: i64,
    deployment: &str,
    release: &str,
    registered: Option<&str>,
) -> Result<(), AppError> {
    let endpoint = reqwest::Url::parse(&binding.endpoint)
        .map_err(|_| AppError::ServiceUnavailable("invalid sender endpoint".into()))?;
    let deployment_key = format!("{:x}", Sha256::digest(deployment.as_bytes()));
    // 新名称省略 account 段以满足 DNS 标签长度；旧精确名称保留历史部署读取能力。
    let hosts = [
        format!(
            "flower2api-{}-{}",
            &deployment_key[..12],
            binding.environment_id
        ),
        format!(
            "v3-{}-account-{}",
            &deployment_key[..12],
            binding.environment_id
        ),
    ];
    let local_endpoint = hosts
        .iter()
        .any(|host| endpoint.host_str() == Some(host.as_str()))
        && endpoint.scheme() == "http"
        && endpoint.port() == Some(8091)
        && endpoint.path() == "/";
    let remote_endpoint = std::env::var("V3_RUNTIME_URL")
        .ok()
        .and_then(|value| reqwest::Url::parse(&value).ok())
        .is_some_and(|base| {
            remote_endpoint_matches(
                &endpoint,
                &base,
                &binding.environment_id,
                &deployment_key[..12],
            )
        });
    // 旧远端只用于已登记回执。摘要包含同一原账号、代次、发行和节点中继位置。
    let retained_remote = remote_endpoint
        && registered.is_some_and(|key| tui_same_binding(key, &tui_sender_key(binding, false)));
    if deployment.is_empty()
        || release.is_empty()
        || binding.environment_id.len() != 32
        || !binding
            .environment_id
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
        || !(local_endpoint || remote_endpoint)
        || binding.account_id != account_id
        || binding.secret.len() < 32
        || !endpoint.username().is_empty()
        || endpoint.password().is_some()
        || endpoint.query().is_some()
        || endpoint.fragment().is_some()
        || (binding.release_id != release
            && !(local_endpoint && authorized_previous_release(binding, deployment, release))
            && !retained_remote)
    {
        return Err(AppError::ServiceUnavailable(
            "runtime binding mismatch".into(),
        ));
    }
    Ok(())
}

fn remote_endpoint_matches(
    endpoint: &reqwest::Url,
    base: &reqwest::Url,
    environment_id: &str,
    deployment_key: &str,
) -> bool {
    if endpoint.origin() != base.origin()
        || !matches!(base.scheme(), "http" | "https")
        || base.path() != "/"
        || !base.username().is_empty()
        || base.password().is_some()
        || base.query().is_some()
        || base.fragment().is_some()
    {
        return false;
    }
    let Some(rest) = endpoint.path().strip_prefix(NODE_RELAY_PREFIX) else {
        return false;
    };
    let parts: Vec<_> = rest.split('/').collect();
    parts.len() == 4
        && parts[0] == deployment_key
        && parts[1].len() == 32
        && parts[1].bytes().all(|value| value.is_ascii_hexdigit())
        && parts[2] == environment_id
        && parts[3]
            .parse::<u64>()
            .is_ok_and(|revision| revision > 0 && revision.to_string() == parts[3])
}

fn binding_client(
    client: Client,
    binding: &TransportBinding,
    secret: &str,
) -> Result<Client, AppError> {
    let endpoint = reqwest::Url::parse(&binding.endpoint)
        .map_err(|_| AppError::ServiceUnavailable("invalid sender endpoint".into()))?;
    if !endpoint.path().starts_with(NODE_RELAY_PREFIX) {
        return Ok(client);
    }
    // 中央认证只发送给已核对 origin 的内部转接；账号 bearer 继续由 sender 独立核验。
    let mut headers = HeaderMap::new();
    let mut value = HeaderValue::from_str(secret).map_err(|_| {
        AppError::ServiceUnavailable("node relay authentication unavailable".into())
    })?;
    value.set_sensitive(true);
    headers.insert("x-v3-relay-token", value);
    Client::builder()
        .no_proxy()
        .redirect(Policy::none())
        .no_gzip()
        .no_brotli()
        .no_deflate()
        .default_headers(headers)
        .connect_timeout(Duration::from_secs(10))
        .build()
        .map_err(|_| AppError::ServiceUnavailable("node relay unavailable".into()))
}

/// 账号发送器运行状态；活跃计数覆盖响应流生命周期。
#[derive(Clone)]
struct SenderState {
    config_path: String,
    native_pool: Arc<NativePool>,
    agy_pool: Arc<AgyPool>,
    native_transition: Arc<RwLock<()>>,
    active: Arc<AtomicU64>,
    evidence_error: Arc<AtomicBool>,
    evidence_lock: Arc<Mutex<()>>,
    #[cfg(target_os = "linux")]
    tui: Arc<TuiSender>,
}

struct ActiveRequest(Arc<AtomicU64>);

impl Drop for ActiveRequest {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
    }
}

/// 读取账号角色当前冻结的私有发送配置。@param path 私有路径。@return 已校验配置。
pub(super) fn read_config(path: &str) -> Result<SenderConfig, AppError> {
    Ok(read_sender_document(path)?.config)
}

#[derive(Deserialize)]
struct SenderDocument {
    #[serde(flatten)]
    config: SenderConfig,
    #[cfg(target_os = "linux")]
    tui_v2: Option<Value>,
}

fn read_sender_document(path: &str) -> Result<SenderDocument, AppError> {
    let bytes = std::fs::read(path)
        .map_err(|_| AppError::ServiceUnavailable("sender configuration unavailable".into()))?;
    let mut document: SenderDocument = serde_json::from_slice(&bytes)
        .map_err(|_| AppError::ServiceUnavailable("invalid sender configuration".into()))?;
    let config = &mut document.config;
    if let Some(agy) = &config.agy {
        agy.validate()?;
        if config.native.is_some() {
            return Err(AppError::ServiceUnavailable(
                "账号发送器平台配置冲突".into(),
            ));
        }
    }
    if let Some(native) = &mut config.native {
        // 历史字段兼容解码，执行身份统一由本平台固定清单决定。
        native.release = None;
        native.kernel_generation = None;
        // 老安装表可把 293 单独登记，剩余条目均为退役内核。280 单版根路径保留原身份，按不可用处理。
        if let Some(runtime) = native.runtimes.remove(&NativeSourceVersion::Cc293) {
            native.binary_path = runtime.binary_path;
            native.source_version = NativeSourceVersion::Cc293;
        }
        native.runtimes.clear();
    }
    Ok(document)
}

fn authenticate(headers: &HeaderMap, config: &SenderConfig) -> Result<(), AppError> {
    let actual = headers
        .get("authorization")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.strip_prefix("Bearer "))
        .unwrap_or_default();
    if config.binding.secret.len() < 32
        || !bool::from(actual.as_bytes().ct_eq(config.binding.secret.as_bytes()))
    {
        return Err(AppError::Unauthorized);
    }
    Ok(())
}

/// 在读取私有 POST 正文前验证账号证明，handler 仍在提交前重读当前配置。
/// @param state 发送器状态。@param request 未读取的请求。@param next 下游路由。
/// @return 已授权的处理结果，或发送前拒绝。
async fn authenticate_sender_post(
    State(state): State<SenderState>,
    request: Request,
    next: Next,
) -> Response {
    let authenticated =
        read_config(&state.config_path).and_then(|config| authenticate(request.headers(), &config));
    match authenticated {
        Ok(()) => next.run(request).await,
        Err(error) => {
            let mut response = error.into_response();
            response
                .headers_mut()
                .insert(ERROR_HEADER, HeaderValue::from_static("before-send"));
            response
        }
    }
}

/// 返回当前 Unix 毫秒，用于私有请求的同一时钟截止。@return UTC 毫秒。
pub(crate) fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

/// 核对私有请求归属、时限和目标，并冻结本次单调截止。
/// @param prepared 冻结元信息。
/// @param config 当前账号绑定。
/// @return 剩余预算不超过120秒的单调截止；过期或超出时钟偏差时拒绝。
pub(crate) fn validate_request(
    prepared: &PreparedRequest,
    config: &SenderConfig,
) -> Result<Instant, AppError> {
    let monotonic_now = Instant::now();
    validate_request_at(prepared, config, now_ms()).map(|budget| monotonic_now + budget)
}

fn validate_request_at(
    prepared: &PreparedRequest,
    config: &SenderConfig,
    wall_now_ms: u64,
) -> Result<Duration, AppError> {
    validate_request_budget(prepared, config, wall_now_ms, REQUEST_BUDGET_MS)
}

fn validate_request_budget(
    prepared: &PreparedRequest,
    config: &SenderConfig,
    wall_now_ms: u64,
    budget_ms: u64,
) -> Result<Duration, AppError> {
    let url = reqwest::Url::parse(&prepared.target_url)
        .map_err(|_| AppError::BadRequest("invalid upstream URL".into()))?;
    let allowed = reqwest::Url::parse(&config.allowed_origin)
        .map_err(|_| AppError::ServiceUnavailable("invalid allowed origin".into()))?;
    // AGY官方路径使用冒号动作，必须在原归属校验内按平台放行精确目标。
    let allowed_path = if config.agy.is_some() {
        url.path() == "/v1internal:streamGenerateContent"
    } else {
        ["/v1/", "/api/"]
            .iter()
            .any(|prefix| url.path().starts_with(prefix))
    };
    if url.origin() != allowed.origin()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.fragment().is_some()
        || !allowed_path
    {
        return Err(AppError::BadRequest(
            "runtime request binding or target mismatch".into(),
        ));
    }
    request_budget(
        &config.binding,
        prepared.account_id,
        &prepared.environment_id,
        prepared.generation,
        &prepared.request_id,
        prepared.deadline_unix_ms,
        wall_now_ms,
        budget_ms,
    )
}

/// 核对绑定、UUID 和原截止。@param binding 当前账号证明。@param account_id 请求账号。
/// @param environment_id 环境。@param generation 原代次。@param request_id 请求 UUID。
/// @param deadline_ms 请求截止。@param wall_now_ms 当前墙钟。@param budget_ms 协议上限。@return 剩余预算。
pub(super) fn request_budget(
    binding: &TransportBinding,
    account_id: i64,
    environment_id: &str,
    generation: u64,
    request_id: &str,
    deadline_ms: u64,
    wall_now_ms: u64,
    budget_ms: u64,
) -> Result<Duration, AppError> {
    if Uuid::parse_str(request_id).is_err()
        || deadline_ms <= wall_now_ms
        || deadline_ms > wall_now_ms.saturating_add(budget_ms + CLOCK_SKEW_MS)
        || account_id != binding.account_id
        || environment_id != binding.environment_id
        || generation != binding.generation
    {
        return Err(AppError::BadRequest(
            "runtime request binding or target mismatch".into(),
        ));
    }
    // 跨进程的墙钟可能回拨；偏差只用于接纳，实际等待仍钳制为原预算。
    Ok(Duration::from_millis(
        (deadline_ms - wall_now_ms).min(budget_ms),
    ))
}

fn read_agy_warm_receipt(body: &[u8], input: &AgyWarmPreparation) -> Option<Option<u64>> {
    let mut events = body.strip_suffix(b"\n")?.split(|byte| *byte == b'\n');
    let mut owned = || {
        let event: Value = serde_json::from_slice(events.next()?).ok()?;
        (event["protocol"] == "agy-account-supervisor"
            && event["schema_version"] == 1
            && event["account_id"] == input.account_id
            && event["environment_id"] == input.environment_id
            && event["environment_generation"] == input.generation
            && event["request_id"] == input.request_id)
            .then_some(event)
    };
    let prepared = owned()?;
    let finalized = owned()?;
    if events.next().is_some()
        || prepared["type"] != "prepared"
        || finalized["type"] != "job_finalized"
        || finalized["status"] != "prepared"
    {
        return None;
    }
    match prepared["preparation_state"].as_str()? {
        "ready" => prepared["native_pid"]
            .as_u64()
            .filter(|pid| *pid > 0)
            .map(Some),
        "busy" if prepared["native_pid"].is_null() => Some(None),
        _ => None,
    }
}

async fn status(
    State(state): State<SenderState>,
    headers: HeaderMap,
) -> Result<Json<Value>, AppError> {
    let document = read_sender_document(&state.config_path)?;
    let config = &document.config;
    authenticate(&headers, config)?;
    #[cfg(target_os = "linux")]
    let receipt_probe = TuiReceiptProbe::from_headers(&headers)?;
    let tui_v2 = tui_v2_sender_status(config);
    let active = state
        .active
        .load(Ordering::SeqCst)
        .max(state.agy_pool.active().await);
    #[cfg(target_os = "linux")]
    let (tui_v2, active) = {
        let mut status = tui_v2;
        let mut tui_active = state.tui.active();
        if status["reason"] == json!(TuiV2Unavailable::MessagesToolAndUsageEventsUnavailable)
            && let Some(configuration) = document.tui_v2.as_ref()
        {
            match state
                .tui
                .status(&config.binding, Some(configuration), receipt_probe.as_ref())
                .await
            {
                Ok((idle, receipt_idle, agent_summary, system_prompt_policy, direct_https)) => {
                    if agent_summary {
                        status["agent_summary_protocol"] = json!(1);
                    }
                    if system_prompt_policy {
                        status["client_system_prompt_policy_protocol"] = json!(1);
                    }
                    if direct_https {
                        status["direct_https_protocol"] = json!(1);
                    }
                    status["ready"] = json!(true);
                    status["idle"] = json!(idle);
                    if let Some(receipt_idle) = receipt_idle {
                        status["receipt_idle"] = json!(receipt_idle && active == 0);
                    }
                    status["event_source"] = json!("local_unix");
                    status.as_object_mut().unwrap().remove("reason");
                    tui_active = state.tui.active().max(u64::from(!idle));
                }
                Err(reason) => status["reason"] = json!(reason),
            }
        }
        (status, active + tui_active)
    };
    Ok(Json(serde_json::json!({"active": active,
        "environment_id": config.binding.environment_id, "generation": config.binding.generation,
        "tui_v2": tui_v2,
        "evidence_ok": !state.evidence_error.load(Ordering::SeqCst),
        "agy_capture_available": config.agy.is_some() && config.native_capture_dir.is_some(),
        "agy":if config.agy.is_some() {Some(state.agy_pool.status(config).await)} else {None}})))
}

#[cfg(target_os = "linux")]
fn tui_document(state: &SenderState, headers: &HeaderMap) -> Result<SenderDocument, AppError> {
    let document = read_sender_document(&state.config_path)?;
    authenticate(headers, &document.config)?;
    if headers.get_all("authorization").iter().count() != 1 || document.config.agy.is_some() {
        return Err(AppError::Unauthorized);
    }
    if !tui_binding_present(&document.config.binding) {
        return Err(AppError::ServiceUnavailable(
            "V2 账号发送器绑定未通过校验".into(),
        ));
    }
    Ok(document)
}

#[cfg(target_os = "linux")]
async fn tui_prepare(
    State(state): State<SenderState>,
    request: Request,
) -> Result<Response, AppError> {
    let document = tui_document(&state, request.headers())?;
    let prepared = state
        .tui
        .prepare(&document.config.binding, document.tui_v2.as_ref(), request)
        .await;
    match prepared {
        Err(
            error @ (AppError::TuiInput { .. }
            | AppError::TuiSubagentCapacity
            | AppError::TuiSubagentAmbiguous
            | AppError::TuiProviderBackoff { .. }),
        ) => {
            let reason = match error {
                AppError::TuiInput { code, .. } => code,
                AppError::TuiSubagentCapacity => "subagent_capacity",
                AppError::TuiProviderBackoff { .. } => "local_provider_backoff",
                _ => "subagent_ambiguous",
            };
            let mut reply = error.into_response();
            reply
                .headers_mut()
                .insert(TUI_PREPARE_REASON, HeaderValue::from_static(reason));
            Ok(reply)
        }
        Ok(mut reply)
            if document.config.native_capture_dir.is_none()
                && reply.headers().contains_key(TUI_CAPTURE) =>
        {
            reply
                .headers_mut()
                .insert(TUI_CAPTURE, HeaderValue::from_static("disabled"));
            Ok(reply)
        }
        other => other,
    }
}

#[cfg(target_os = "linux")]
async fn tui_control_request(request: Request, rejection: &str) -> Result<HeaderMap, AppError> {
    let (parts, body) = request.into_parts();
    // 认证中间件已核验账号。空分块流须读到结束，任何数据字节都拒绝。
    if !matches!(
        timeout(Duration::from_secs(2), to_bytes(body, 0)).await,
        Ok(Ok(_))
    ) {
        return Err(AppError::BadRequest(rejection.into()));
    }
    Ok(parts.headers)
}

#[cfg(target_os = "linux")]
async fn tui_send(
    State(state): State<SenderState>,
    request: Request,
) -> Result<Response, AppError> {
    let (headers, observation) = if tui_projection_marker(request.headers(), TUI_CAPTURE, "1") {
        // 采集信封由绑定的网关生成，先鉴权再读取有界正文；取消与旧版发送仍只接受空流。
        let document = tui_document(&state, request.headers())?;
        let deadline = TuiSender::capture_deadline(&document.config.binding, request.headers())?;
        let (parts, body) = request.into_parts();
        let value = timeout_at(
            deadline,
            to_bytes(body, super::native_capture::SNAPSHOT_LIMIT),
        )
        .await
        .ok()
        .and_then(Result::ok)
        .and_then(|v| serde_json::from_slice(&v).ok())
        .ok_or_else(|| AppError::BadRequest("V2 采集信封无效".into()))?;
        (parts.headers, Some(value))
    } else {
        (
            tui_control_request(request, "V2 发送只接收原预留信封").await?,
            None,
        )
    };
    // 读完结束符后重读配置，避免把在途的旧信封交给新代。
    let document = tui_document(&state, &headers)?;
    state
        .tui
        .send(
            &document.config.binding,
            document.tui_v2.as_ref(),
            &headers,
            document
                .config
                .native_capture_dir
                .map(std::path::PathBuf::from)
                .zip(observation),
        )
        .await
}

#[cfg(target_os = "linux")]
async fn tui_cancel(
    State(state): State<SenderState>,
    request: Request,
) -> Result<StatusCode, AppError> {
    let headers = tui_control_request(request, "V2 取消只接收原预留信封").await?;
    let document = tui_document(&state, &headers)?;
    state.tui.cancel(&document.config.binding, &headers).await
}

#[cfg(target_os = "linux")]
async fn tui_repair(
    State(state): State<SenderState>,
    request: Request,
) -> Result<Response, AppError> {
    let headers = tui_control_request(request, "V2 签名修复只接收原预留信封").await?;
    let document = tui_document(&state, &headers)?;
    state.tui.repair(&document.config.binding, &headers).await
}

async fn forward(State(state): State<SenderState>, headers: HeaderMap, body: Bytes) -> Response {
    let mut submitted = false;
    let result =
        async {
            let mut config = read_config(&state.config_path)?;
            authenticate(&headers, &config)?;
            if config.agy.is_some() {
                return Err(AppError::BadRequest("AGY账号只接受对应原生执行协议".into()));
            }
            if state.evidence_error.load(Ordering::SeqCst) {
                return Err(AppError::ServiceUnavailable(
                    "API evidence requires maintenance".into(),
                ));
            }
            let meta = headers
                .get(META_HEADER)
                .and_then(|value| value.to_str().ok())
                .ok_or_else(|| AppError::BadRequest("missing runtime request".into()))?;
            let bytes = STANDARD
                .decode(meta)
                .map_err(|_| AppError::BadRequest("invalid runtime request".into()))?;
            let mut prepared: PreparedRequest = serde_json::from_slice(&bytes)
                .map_err(|_| AppError::BadRequest("invalid runtime request".into()))?;
            let tui_account_model = headers.contains_key(TUI_ACCOUNT_MODEL);
            let oauth_expiry = headers
                .get(TUI_ACCOUNT_EXPIRY)
                .map(|value| {
                    if !tui_account_model || headers.get_all(TUI_ACCOUNT_EXPIRY).iter().count() != 1
                    {
                        return Err(AppError::BadRequest("V2 账号到期时间的发送归属无效".into()));
                    }
                    value
                        .to_str()
                        .ok()
                        .and_then(|value| value.parse::<u64>().ok())
                        .ok_or_else(|| AppError::BadRequest("V2 账号到期时间无效".into()))
                })
                .transpose()?;
            let purpose = headers
                .get(BACKGROUND_HEADER)
                .map(|value| {
                    if headers.get_all(BACKGROUND_HEADER).iter().count() != 1 {
                        return Err(AppError::BadRequest("后台发送动作头重复".into()));
                    }
                    let value = value
                        .to_str()
                        .map_err(|_| AppError::BadRequest("后台发送动作头无效".into()))?;
                    BackgroundPurpose::parse(value)
                })
                .transpose()?;
            if let Some(purpose) = purpose {
                config.allowed_origin = purpose.validate(&prepared.method, &prepared.target_url)?;
            }
            if tui_account_model {
                if !tui_projection_marker(&headers, TUI_ACCOUNT_MODEL, "1")
                    || purpose.is_some()
                    || prepared.method != "POST"
                    || prepared.target_url != "https://api.anthropic.com/v1/messages"
                    || config.proxy_url.trim().is_empty()
                    || prepared
                        .headers
                        .iter()
                        .any(|(name, _)| name.eq_ignore_ascii_case(CONTENT_LENGTH.as_str()))
                {
                    return Err(AppError::BadRequest(
                        "V2 账号模型发送的目的或协议无效".into(),
                    ));
                }
                prepared
                    .headers
                    .push((CONTENT_LENGTH.as_str().into(), body.len().to_string()));
            }
            let deadline = validate_request(&prepared, &config)?;
            #[cfg(target_os = "linux")]
            let observer = if tui_account_model {
                state
                    .tui
                    .take_wire_capture(&config.binding, &prepared.request_id)
                    .and_then(|job| {
                        let attempt = Uuid::parse_str(&prepared.request_id).ok()?;
                        // 还原本入口收到的提交头。该入口已验证 Content-Length 只能由本发送器添加。
                        let submitted = prepared
                            .headers
                            .iter()
                            .filter(|(name, _)| !name.eq_ignore_ascii_case("content-length"))
                            .cloned()
                            .collect();
                        let assembly = match headers
                            .get("x-v3-tui-assembly")
                            .and_then(|v| v.to_str().ok())
                        {
                            Some("explicit-version") => Some(true),
                            Some("default-version") => Some(false),
                            _ => None,
                        };
                        Some(job.start(
                            prepared.account_id,
                            attempt,
                            prepared.generation,
                            submitted,
                            body.clone(),
                            assembly,
                        ))
                    })
            } else {
                None
            };
            #[cfg(not(target_os = "linux"))]
            let observer = None;
            state.active.fetch_add(1, Ordering::SeqCst);
            let guard = ActiveRequest(state.active.clone());
            submitted = oauth_expiry.is_none();
            let upstream = timeout_at(deadline, async {
                if tui_account_model {
                    // 固定目标和一次性正文同时防止重定向或客户端重放已认领的模型请求。
                    let client = get_background_request_client_for_profile(
                        &config.proxy_url,
                        prepared.tls_profile,
                    )
                    .map_err(|_| AppError::BadGateway("V2 账号模型客户端不可用".into()))?;
                    if oauth_expiry.is_some_and(|expiry| expiry <= now_ms()) {
                        return Err(AppError::ServiceUnavailable("V2 账号凭据已过期".into()));
                    }
                    submitted = true;
                    let stream = stream_once(async move { Ok::<_, IoError>(body) });
                    send_observed(
                        &client,
                        &prepared,
                        RequestBody::wrap_stream(stream),
                        observer,
                        true,
                    )
                    .await
                } else if purpose.is_some() {
                    let client = get_background_request_client_for_profile(
                        &config.proxy_url,
                        prepared.tls_profile,
                    )
                    .map_err(|_| AppError::BadGateway("后台账号客户端不可用".into()))?;
                    send_with_client(&client, &prepared, body.to_vec()).await
                } else {
                    send_direct(&config.proxy_url, &prepared, body.to_vec()).await
                }
            })
            .await
            .map_err(|_| AppError::BadGateway("upstream submission status unknown".into()))??;
            let code = upstream.status();
            {
                let _lock = state.evidence_lock.lock().unwrap();
                // 遥测、usage和刷新成功不能充当模型额度恢复证据。
                if (purpose.is_none() || purpose == Some(BackgroundPurpose::TokenTest))
                    && record_headers(&config, &prepared, &upstream).is_err()
                {
                    // 当前 API 响应仍保持原样，故障通过健康状态阻止下一作业或新提交。
                    state.evidence_error.store(true, Ordering::SeqCst);
                }
            }
            let response_headers = upstream.headers().clone();
            // guard 跟随流；下游取消会 drop reqwest 流并关闭该响应，不在这里重放。
            let stream = unfold(
                (upstream.bytes_stream(), guard),
                |(mut stream, guard)| async move {
                    stream.next().await.map(|item| (item, (stream, guard)))
                },
            );
            let mut response = Response::new(Body::from_stream(stream));
            *response.status_mut() = code;
            *response.headers_mut() = response_headers;
            response.headers_mut().remove("transfer-encoding");
            // 发送状态由本地发送器签发，不能采用上游响应中的同名头。
            response.headers_mut().remove(ERROR_HEADER);
            Ok::<Response, AppError>(response)
        }
        .await;
    result.unwrap_or_else(|error| {
        let mut response = error.into_response();
        response.headers_mut().insert(
            ERROR_HEADER,
            if submitted {
                "uncertain"
            } else {
                "before-send"
            }
            .parse()
            .unwrap(),
        );
        response
    })
}

async fn native_status(
    State(state): State<SenderState>,
    headers: HeaderMap,
) -> Result<Json<Value>, AppError> {
    let config = read_config(&state.config_path)?;
    authenticate(&headers, &config)?;
    let native = config
        .native
        .as_ref()
        .ok_or_else(|| AppError::ServiceUnavailable("未配置原生运行时".into()))?;
    if state.evidence_error.load(Ordering::SeqCst) {
        return Err(AppError::ServiceUnavailable("账号证据写入异常".into()));
    }
    let available = state.native_pool.verify(native).is_ok();
    Ok(Json(
        serde_json::json!({"raw_input_protocol":1,"version":"2.1.293","environment_id":config.binding.environment_id,"generation":config.binding.generation,
            "versions":{"2.1.293":{"available":available,"version":"2.1.293"}},
            "release":config.native.as_ref().and_then(|native| native.release.as_ref()),
            "tls_observer":state.native_pool.tls_status(&config)}),
    ))
}

/// 在现有服务鉴权与绑定边界内执行零模型准备。
/// @param state sender 状态。
/// @param headers 服务鉴权头。
/// @param preparation 账号身份和准备截止。
/// @return 实际进程握手结果。
async fn native_prepare(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(preparation): Json<NativePreparation>,
) -> Result<Json<NativePreparationStatus>, AppError> {
    let _guard = state.native_transition.read().await;
    prepare_sender(&state, &headers, preparation).await
}

/// 在私有鉴权和精确绑定内只检查原生池，页面检查不触发进程启动。
/// @param state sender 状态。
/// @param headers 服务鉴权头。
/// @param preparation 当前身份和检查截止。
/// @return 实时进程状态。
async fn native_readiness(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(preparation): Json<NativePreparation>,
) -> Result<Json<NativeReadinessStatus>, AppError> {
    let config = read_config(&state.config_path)?;
    authenticate(&headers, &config)?;
    preparation.source_version.require_executable()?;
    let pool = &state.native_pool;
    if state.evidence_error.load(Ordering::SeqCst) {
        return Err(AppError::ServiceUnavailable("账号证据写入异常".into()));
    }
    let identity = preparation_identity(preparation, &config);
    let deadline = validate_request(&identity.request, &config)?;
    let status = timeout_at(deadline, pool.readiness(&config, &identity))
        .await
        .map_err(|_| AppError::ServiceUnavailable("原生检查超时".into()))??;
    if serde_json::to_vec(&read_config(&state.config_path)?).ok()
        != serde_json::to_vec(&config).ok()
    {
        return Err(AppError::ServiceUnavailable(
            "原生检查期间环境配置已变化".into(),
        ));
    }
    Ok(Json(status))
}

/// 管理端在运行绑定内同步回收策略，保持账号身份和活动请求的原生命周期。
/// @param state 当前sender。@param headers 私有鉴权。@param policy 账号及代次绑定。
/// @return 已应用的秒数，错误绑定或非法值拒绝。
async fn native_idle_policy(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(policy): Json<NativeIdlePolicy>,
) -> Result<Json<Value>, AppError> {
    let config = read_config(&state.config_path)?;
    authenticate(&headers, &config)?;
    if config.native.is_none()
        || policy.account_id != config.binding.account_id
        || policy.environment_id != config.binding.environment_id
        || policy.generation != config.binding.generation
    {
        return Err(AppError::ServiceUnavailable(
            "空闲策略环境归属已变化".into(),
        ));
    }
    validate_idle_timeout(policy.idle_timeout_secs)?;
    state.native_pool.set_idle_timeout(policy.idle_timeout_secs);
    Ok(Json(
        json!({"ok":true,"idle_timeout_secs":policy.idle_timeout_secs}),
    ))
}

async fn prepare_sender(
    state: &SenderState,
    headers: &HeaderMap,
    preparation: NativePreparation,
) -> Result<Json<NativePreparationStatus>, AppError> {
    let config = read_config(&state.config_path)?;
    authenticate(headers, &config)?;
    preparation.source_version.require_executable()?;
    let pool = &state.native_pool;
    if state.evidence_error.load(Ordering::SeqCst) {
        return Err(AppError::ServiceUnavailable("账号证据写入异常".into()));
    }
    pool.verify(
        config
            .native
            .as_ref()
            .ok_or_else(|| AppError::ServiceUnavailable("未配置原生运行时".into()))?,
    )?;
    // 这里只借用既有绑定与截止校验结构；input 没有业务正文，也不会进入 execute。
    let identity = preparation_identity(preparation, &config);
    let deadline = validate_request(&identity.request, &config)?;
    let status = pool.prepare(config.clone(), identity, deadline).await?;
    let current = read_config(&state.config_path)?;
    if serde_json::to_vec(&current).ok() != serde_json::to_vec(&config).ok() {
        return Err(AppError::ServiceUnavailable(
            "原生准备期间环境配置已变化".into(),
        ));
    }
    Ok(Json(status))
}

/// 准备和只读检查使用同一身份信封，避免字段映射分叉。
fn preparation_identity(preparation: NativePreparation, config: &SenderConfig) -> NativeSubmission {
    NativeSubmission {
        source_version: preparation.source_version,
        cache_ttl_rewrite: None,
        message_cache_policy: None,
        ingress_capture: None,
        log_mode: RequestLogMode::Info,
        request: PreparedRequest {
            account_id: preparation.account_id,
            environment_id: preparation.environment_id,
            generation: preparation.generation,
            request_id: preparation.preparation_id.clone(),
            deadline_unix_ms: preparation.deadline_unix_ms,
            method: "POST".into(),
            target_url: format!("{}/v1/messages", config.allowed_origin),
            headers: Vec::new(),
            preserve_header_casing: false,
            tls_profile: TlsProfileId::default(),
        },
        input: serde_json::json!({"schema_version":1,"request_id":preparation.preparation_id}),
        bearer: preparation.bearer,
        device_id: preparation.device_id,
        account_uuid: preparation.account_uuid,
        organization_uuid: preparation.organization_uuid,
        email: preparation.email,
        concurrency: preparation.concurrency,
    }
}

/// 只取消本账号及当前环境代次的准备。
/// @param state sender 状态。
/// @param headers 服务鉴权头。
/// @param control 准备归属和 UUID。
/// @return 已登记撤销，覆盖准备尚未到达的情况。
async fn native_prepare_cancel(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(control): Json<NativePreparationControl>,
) -> Result<Json<Value>, AppError> {
    let config = read_config(&state.config_path)?;
    authenticate(&headers, &config)?;
    if control.account_id != config.binding.account_id
        || control.environment_id != config.binding.environment_id
        || control.generation != config.binding.generation
        || Uuid::parse_str(&control.preparation_id).is_err()
    {
        return Err(AppError::BadRequest("准备取消归属不匹配".into()));
    }
    control.source_version.require_executable()?;
    if !state.native_pool.cancel_preparation(&control) {
        return Err(AppError::ServiceUnavailable("原生准备撤销登记已满".into()));
    }
    Ok(Json(serde_json::json!({"cancelled":true})))
}

/// 沿现有账号鉴权和环境准入分派AGY私有请求。@param state 发送器。@param headers 服务证明。@param submission 冻结信封。@param operation 目标操作。@return 原生私有事件流。
async fn agy_operation(
    state: SenderState,
    headers: HeaderMap,
    mut submission: AgySubmission,
    operation: AgyOperation,
) -> Response {
    let mut started = false;
    let result = async {
        let transition = state.native_transition.clone().read_owned().await;
        let config = read_config(&state.config_path)?;
        authenticate(&headers, &config)?;
        if config.agy.is_none() {
            return Err(AppError::ServiceUnavailable(
                "该账号环境未配置AGY内核".into(),
            ));
        }
        let budget_ms = if operation == AgyOperation::Generate {
            AGY_REQUEST_SECONDS as u64 * 1000
        } else {
            REQUEST_BUDGET_MS
        };
        let now = Instant::now();
        let deadline =
            now + validate_request_budget(&submission.request, &config, now_ms(), budget_ms)?;
        submission.validate(now_ms())?;
        let target = reqwest::Url::parse(&submission.request.target_url)
            .map_err(|_| AppError::BadRequest("AGY目标无效".into()))?;
        if submission.request.method != "POST"
            || target.path() != "/v1internal:streamGenerateContent"
            || target.query().is_some()
        {
            return Err(AppError::BadRequest("AGY目标与冻结业务协议不符".into()));
        }
        state.active.fetch_add(1, Ordering::SeqCst);
        let guard = ActiveRequest(state.active.clone());
        submission.capture_enabled = submission.capture_enabled
            && operation != AgyOperation::Search
            && config.native_capture_dir.is_some();
        submission.full_egress = operation == AgyOperation::Generate
            && submission.capture_enabled
            && headers
                .get("x-v3-agy-egress-body")
                .is_some_and(|value| value == "full");
        started = true;
        let response = state
            .agy_pool
            .submit(&config, &state.config_path, submission, deadline, operation)
            .await?;
        Ok::<Response, AppError>(hold_agy_stream(response, guard, transition))
    }
    .await;
    result.unwrap_or_else(|error| {
        let mut response = error.into_response();
        response.headers_mut().insert(
            ERROR_HEADER,
            if started { "uncertain" } else { "before-send" }
                .parse()
                .unwrap(),
        );
        response
    })
}

fn hold_agy_stream(
    response: Response,
    guard: ActiveRequest,
    transition: OwnedRwLockReadGuard<()>,
) -> Response {
    let (parts, body) = response.into_parts();
    let stream = unfold(
        (body.into_data_stream(), guard, transition),
        |(mut stream, guard, transition)| async move {
            stream
                .next()
                .await
                .map(|item| (item, (stream, guard, transition)))
        },
    );
    Response::from_parts(parts, Body::from_stream(stream))
}

/// 按私有环境身份准备可复用进程。@param state 发送器。
/// @param headers 服务证明。@param input 冻结环境及凭据。@return 私有握手及终态事件。
async fn agy_warm(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(mut input): Json<AgyWarmPreparation>,
) -> Result<Response, AppError> {
    let transition = state.native_transition.clone().read_owned().await;
    let config = read_config(&state.config_path)?;
    authenticate(&headers, &config)?;
    if config.agy.is_none() {
        return Err(AppError::ServiceUnavailable(
            "该账号环境未配置AGY内核".into(),
        ));
    }
    let monotonic_now = Instant::now();
    let wall_now_ms = now_ms();
    let budget = request_budget(
        &config.binding,
        input.account_id,
        &input.environment_id,
        input.generation,
        &input.request_id,
        input.deadline_unix_ms,
        wall_now_ms,
        REQUEST_BUDGET_MS,
    )?;
    input.credential_snapshot.validate(wall_now_ms)?;
    if input.credential_snapshot.account_id != input.account_id {
        return Err(AppError::BadRequest("AGY准备凭据归属不匹配".into()));
    }
    input.capture_enabled &= config.native_capture_dir.is_some();
    state.active.fetch_add(1, Ordering::SeqCst);
    let guard = ActiveRequest(state.active.clone());
    let response = state
        .agy_pool
        .warm(&config, &state.config_path, input, monotonic_now + budget)
        .await?;
    Ok(hold_agy_stream(response, guard, transition))
}

/// 只准备AGY进程，模型提交为零。@param state 发送器。@param headers 服务证明。@param submission 准备身份。@return 准备事件流。
async fn agy_prepare(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(submission): Json<AgySubmission>,
) -> Response {
    agy_operation(state, headers, submission, AgyOperation::Prepare).await
}

/// 验证原环境并完成工具回填，独立于新凭据发布。@param state 发送器。@param headers 受信证明。@param input 原工具归属。@return 真实收口回执。
async fn agy_tools(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(input): Json<AgyToolCompletion>,
) -> Result<Response, AppError> {
    let _transition = state.native_transition.clone().read_owned().await;
    let config = read_config(&state.config_path)?;
    authenticate(&headers, &config)?;
    if config.agy.is_none() {
        return Err(AppError::ServiceUnavailable("原AGY环境不可用".into()));
    }
    let deadline = validate_request(&input.request, &config)?;
    let target = reqwest::Url::parse(&input.request.target_url)
        .map_err(|_| AppError::BadRequest("AGY工具目标无效".into()))?;
    if input.request.method != "POST"
        || target.path() != "/v1internal:streamGenerateContent"
        || target.query().is_some()
    {
        return Err(AppError::BadRequest("AGY工具目标与原协议不符".into()));
    }
    state.active.fetch_add(1, Ordering::SeqCst);
    let _guard = ActiveRequest(state.active.clone());
    let result = match state.agy_pool.finish_tools(input, deadline).await {
        Err(error @ AppError::AgyToolTurnFailed) => {
            let mut response = error.into_response();
            response
                .headers_mut()
                .insert(AGY_TOOL_FINALIZATION_FAILED, HeaderValue::from_static("1"));
            return Ok(response);
        }
        result => result?,
    };
    if let Some(code) = result["input_rejection"].as_str() {
        let mut response = AppError::BadRequest("AGY原工具轮拒绝回填".into()).into_response();
        if let Ok(value) = HeaderValue::from_str(code) {
            response
                .headers_mut()
                .insert(AGY_TOOL_INPUT_REJECTION, value);
        }
        return Ok(response);
    }
    Ok(Json(result).into_response())
}

/// 投递AGY模型业务。@param state 发送器。@param headers 服务证明。@param submission 冻结请求。@return 私有原生事件流。
async fn agy_generate(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(submission): Json<AgySubmission>,
) -> Response {
    agy_operation(state, headers, submission, AgyOperation::Generate).await
}

/// 执行同代账号的原版搜索。@param state 发送器。@param headers 服务证明。
/// @param submission 查询和账号归属。@return 搜索收口事件流。
async fn agy_search(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(submission): Json<AgySubmission>,
) -> Response {
    agy_operation(state, headers, submission, AgyOperation::Search).await
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct AgyCancellation {
    account_id: i64,
    environment_id: String,
    generation: u64,
    request_id: String,
    api_token_id: i64,
}

/// 核对原发送器、尝试及调用方，再向原监督器登记取消。
/// @param state 发送器。@param headers 服务证明。@param input 原请求归属。@return 已接受取消登记。
async fn agy_cancel(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(input): Json<AgyCancellation>,
) -> Result<StatusCode, AppError> {
    let config = read_config(&state.config_path)?;
    authenticate(&headers, &config)?;
    if config.agy.is_none()
        || input.account_id != config.binding.account_id
        || input.environment_id != config.binding.environment_id
        || input.generation != config.binding.generation
        || Uuid::parse_str(&input.request_id).is_err()
    {
        return Err(AppError::BadRequest("AGY取消归属无效".into()));
    }
    state
        .agy_pool
        .cancel(&input.request_id, input.api_token_id)
        .await?;
    Ok(StatusCode::NO_CONTENT)
}

/// 受信配置生效时核对当前环境与期望的上限。
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AgyCapacityControl {
    account_id: i64,
    environment_id: String,
    generation: u64,
    max_workers: usize,
}

/// 将当前文件的容量应用到此发送器的原监督器。@param state 发送器。@param headers 服务证明。@param input 已冻结的归属与上限。@return 实际生效回执。
async fn agy_capacity(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(input): Json<AgyCapacityControl>,
) -> Result<Json<Value>, AppError> {
    let max_workers = state
        .agy_pool
        .apply_capacity(&state.config_path, |config| {
            authenticate(&headers, config)?;
            if input.account_id != config.binding.account_id
                || input.environment_id != config.binding.environment_id
                || input.generation != config.binding.generation
                || config.agy.as_ref().map(|agy| agy.max_workers) != Some(input.max_workers)
            {
                return Err(AppError::BadRequest("AGY容量配置或发送器代次已变化".into()));
            }
            Ok(())
        })
        .await?;
    Ok(Json(
        json!({"account_id":input.account_id,"environment_id":input.environment_id,
        "generation":input.generation,"max_workers":max_workers}),
    ))
}

async fn native_forward(
    State(state): State<SenderState>,
    headers: HeaderMap,
    Json(submission): Json<NativeSubmission>,
) -> Response {
    let mut submitted = false;
    let operation = async {
        let transition = state.native_transition.clone().read_owned().await;
        let config = read_config(&state.config_path)?;
        authenticate(&headers, &config)?;
        submission.source_version.require_executable()?;
        let pool = &state.native_pool;
        let deadline = validate_request(&submission.request, &config)?;
        let target = reqwest::Url::parse(&submission.request.target_url)
            .map_err(|_| AppError::BadRequest("原生目标无效".into()))?;
        if submission.request.method != "POST"
            || target.path() != "/v1/messages"
            || target.query().is_some()
        {
            return Err(AppError::BadRequest("原生方式只支持 Messages".into()));
        }
        if state.evidence_error.load(Ordering::SeqCst) {
            return Err(AppError::ServiceUnavailable("账号证据写入异常".into()));
        }
        pool.verify(
            config
                .native
                .as_ref()
                .ok_or_else(|| AppError::ServiceUnavailable("未配置原生运行时".into()))?,
        )?;
        state.active.fetch_add(1, Ordering::SeqCst);
        let guard = ActiveRequest(state.active.clone());
        submitted = true;
        let response = pool
            .submit_validated(config.clone(), submission.clone(), deadline)
            .await?;
        // 共用额度证据格式，进程池和响应流由同一活动许可覆盖。
        {
            let _lock = state.evidence_lock.lock().unwrap();
            if record_response_headers(
                &config,
                &submission.request,
                response.status().as_u16(),
                response.headers(),
            )
            .is_err()
            {
                state.evidence_error.store(true, Ordering::SeqCst);
            }
        }
        let (parts, body) = response.into_parts();
        let stream = unfold(
            (body.into_data_stream(), guard, transition),
            |(mut stream, guard, transition)| async move {
                stream
                    .next()
                    .await
                    .map(|item| (item, (stream, guard, transition)))
            },
        );
        Ok::<Response, AppError>(Response::from_parts(parts, Body::from_stream(stream)))
    };
    operation.await.unwrap_or_else(|error| {
        // 准备类错误在写入业务指令前产生；活动计数已经覆盖启动阶段。
        let before_send = !submitted
            || matches!(
                &error,
                AppError::ServiceUnavailable(_) | AppError::BadRequest(_) | AppError::Unauthorized
            );
        let mut response = error.into_response();
        response.headers_mut().insert(
            ERROR_HEADER,
            if before_send {
                "before-send"
            } else {
                "uncertain"
            }
            .parse()
            .unwrap(),
        );
        response
    })
}

/// 构建只服务单个账号环境的内部发送器路由。
///
/// @param config_path root 所有的账号配置文件路径。
/// @return 包含发送与活动状态接口的 Router。
/// 组装独立账号发送器路由。@param config_path 私有绑定文件。@return 发送器路由。
pub fn sender_router(config_path: String) -> Router {
    sender_components(config_path).0
}

/// 提供账号发送服务，正常停止时让原监督器写入真实退出回执。
/// @param listener 已绑定的账号内部端口。@param config_path 私有绑定文件。
/// @return HTTP 服务的退出结果。
pub async fn serve_sender(listener: TcpListener, config_path: String) -> std::io::Result<()> {
    let (router, agy_pool) = sender_components(config_path);
    #[cfg(unix)]
    let mut terminate = signal(SignalKind::terminate())?;
    let result = axum::serve(listener, router)
        .with_graceful_shutdown(async move {
            #[cfg(unix)]
            tokio::select! {
                _ = terminate.recv() => {}
                _ = tokio::signal::ctrl_c() => {}
            }
            #[cfg(not(unix))]
            let _ = tokio::signal::ctrl_c().await;
        })
        .await;
    agy_pool.shutdown_idle().await;
    result
}

fn sender_components(config_path: String) -> (Router, Arc<AgyPool>) {
    let agy_pool = Arc::new(AgyPool::default());
    let state = SenderState {
        config_path,
        native_pool: Arc::new(NativePool::default()),
        agy_pool: agy_pool.clone(),
        native_transition: Arc::new(RwLock::new(())),
        active: Arc::new(AtomicU64::new(0)),
        evidence_error: Arc::new(AtomicBool::new(false)),
        evidence_lock: Arc::new(Mutex::new(())),
        #[cfg(target_os = "linux")]
        tui: Arc::new(TuiSender::default()),
    };
    let router = Router::new()
        .route("/internal/send", post(forward))
        .route("/internal/agy/prepare", post(agy_prepare))
        .route("/internal/agy/warm", post(agy_warm))
        .route("/internal/agy/generate", post(agy_generate))
        .route("/internal/agy/search", post(agy_search))
        .route("/internal/agy/tools", post(agy_tools))
        .route("/internal/agy/cancel", post(agy_cancel))
        .route("/internal/agy/capacity", post(agy_capacity))
        .route("/internal/native/prepare", post(native_prepare))
        .route("/internal/native/readiness", post(native_readiness))
        .route("/internal/native/idle-policy", post(native_idle_policy))
        .route(
            "/internal/native/prepare/cancel",
            post(native_prepare_cancel),
        )
        .route("/internal/native/messages", post(native_forward));
    #[cfg(target_os = "linux")]
    let router = router
        .route("/internal/tui-v2/prepare", post(tui_prepare))
        .route("/internal/tui-v2/send", post(tui_send))
        .route("/internal/tui-v2/repair", post(tui_repair))
        .route("/internal/tui-v2/cancel", post(tui_cancel));
    let router = router
        .route_layer(from_fn_with_state(state.clone(), authenticate_sender_post))
        .route("/internal/native/status", get(native_status))
        .route("/internal/status", get(status))
        .layer(DefaultBodyLimit::max(128 * 1024 * 1024))
        .with_state(state);
    (router, agy_pool)
}

#[cfg(test)]
mod tests {
    use super::*;

    use crate::service::agy_contract::AGY_SOURCE_SHA256;
    use crate::tlsfp::{parse_test_clienthello, test_request_client};
    use rustls_pki_types::CertificateDer;
    use serde_json::{Value, json};
    use std::env::temp_dir;
    use std::io::{BufRead, BufReader};
    use std::net::{Ipv4Addr, SocketAddr};
    use std::path::PathBuf;
    use std::process::{Child, Command, Stdio};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    #[test]
    fn tui_transition_requires_exact_trusted_predecessor() {
        let binding =
            |account_id, environment_id: &str, generation, release: &str, endpoint: &str| {
                TransportBinding {
                    account_id,
                    environment_id: environment_id.into(),
                    generation,
                    release_id: release.into(),
                    endpoint: endpoint.into(),
                    secret: String::new(),
                }
            };
        let environment = "a".repeat(32);
        let local = "http://flower2api-local:8091";
        let remote = "http://orchestrator:8000/cluster-transports/v2/synthetic";
        let old = binding(17, &environment, 1, "old-release", local);
        let old_key = tui_sender_key(&old, false);
        for (release, endpoint) in [
            ("new-release", local),
            ("old-release", remote),
            ("old-release", local),
        ] {
            let current = binding(17, &environment, 2, release, endpoint);
            let proof = |account_id, environment_id: &str, generation| TuiBindingProof {
                account_id,
                environment_id: environment_id.into(),
                generation,
                release_id: old.release_id.clone(),
                endpoint: old.endpoint.clone(),
            };
            let mut state = TuiBindingStatus {
                key: tui_sender_key(&current, false),
                idle: true,
                system_prompt_policy: false,
                direct_https: false,
                predecessors: tui_predecessor_keys(
                    &current,
                    vec![
                        proof(18, &environment, 1),
                        proof(17, &"b".repeat(32), 1),
                        proof(17, &environment, 2),
                    ],
                ),
            };
            assert!(state.predecessors.is_empty());
            assert_eq!(
                state.can_advance(&old_key),
                release == "old-release" && endpoint == local
            );
            state.predecessors = tui_predecessor_keys(&current, vec![proof(17, &environment, 1)]);
            assert!(state.can_advance(&old_key));
            let unrelated = binding(17, &environment, 1, "other-release", local);
            assert!(!state.can_advance(&tui_sender_key(&unrelated, false)));
        }
    }

    /// 已鉴权状态还须核对代次与发行，心跳及候选就绪不可充当正式诊断。@return 无。
    #[test]
    fn tui_v2_status_confirms_binding_without_inventing_readiness() {
        let config: SenderConfig = serde_json::from_value(json!({
            "binding": {"account_id": 17, "environment_id": "c".repeat(32), "generation": 2,
                "endpoint": "http://localhost:8091", "secret": "synthetic-transport-secret".repeat(2),
                "release_id": "local-test"},
            "proxy_url": "", "allowed_origin": "https://api.anthropic.com"
        }))
        .unwrap();
        let binding = &config.binding;
        let mut status = json!({"active": 0, "environment_id": binding.environment_id,
            "generation": binding.generation});
        assert_eq!(
            tui_status_snapshot(binding, &status, false),
            Err(TuiV2Unavailable::ReadinessUnverified)
        );
        status["tui_v2"] = tui_v2_sender_status(&config);
        assert_eq!(
            tui_status_snapshot(binding, &status, false),
            Err(TuiV2Unavailable::MessagesToolAndUsageEventsUnavailable)
        );
        status["tui_v2"]["release_id"] = json!("wrong-release");
        assert_eq!(
            tui_status_snapshot(binding, &status, false),
            Err(TuiV2Unavailable::BindingUnverified)
        );
        status["tui_v2"] = json!({"protocol": 1, "ready": true, "idle": true});
        assert_eq!(
            tui_status_snapshot(binding, &status, false),
            Err(TuiV2Unavailable::BindingUnverified)
        );
        status["tui_v2"]["account_id"] = json!(binding.account_id);
        status["tui_v2"]["release_id"] = json!(binding.release_id);
        assert_eq!(
            tui_status_snapshot(binding, &status, false),
            Err(TuiV2Unavailable::ReadinessUnverified)
        );
        status["tui_v2"]["event_source"] = json!("local_unix");
        assert_eq!(tui_status_snapshot(binding, &status, false), Ok(true));
        status["active"] = json!(1);
        assert_eq!(tui_status_snapshot(binding, &status, false), Ok(false));
        status["generation"] = json!(binding.generation + 1);
        assert_eq!(
            tui_status_snapshot(binding, &status, false),
            Err(TuiV2Unavailable::BindingUnverified)
        );
    }

    /// 覆盖同一已登记位置换代、节点分配变化、发行变化与历史摘要。
    #[test]
    fn tui_sender_generation_keeps_registered_account_environment_node_and_release() {
        let environment_id = "a".repeat(32);
        let node = "b".repeat(32);
        let endpoint = format!(
            "http://runtime.test/cluster-transports/v2/0123456789ab/{node}/{environment_id}/3"
        );
        let original = TransportBinding {
            account_id: 7,
            environment_id,
            generation: 8,
            endpoint,
            secret: "synthetic-secret".into(),
            release_id: "synthetic-release".into(),
        };
        let mut replacement = original.clone();
        replacement.generation += 1;
        replacement.secret = "rotated-internal-secret".into();
        let registered = tui_sender_key(&original, false);
        let current = tui_sender_key(&replacement, false);
        assert!(tui_same_binding(&registered, &registered));
        assert!(!tui_same_binding(&registered, &current));
        assert!(tui_later_generation(&registered, &current));
        assert!(!tui_later_generation(&registered, &registered));
        assert!(!tui_later_generation(&current, &registered));
        for changed in [
            TransportBinding {
                account_id: 8,
                ..replacement.clone()
            },
            TransportBinding {
                environment_id: "c".repeat(32),
                ..replacement.clone()
            },
            TransportBinding {
                endpoint: replacement
                    .endpoint
                    .replacen("runtime.test", "other-runtime.test", 1),
                ..replacement.clone()
            },
            TransportBinding {
                endpoint: replacement.endpoint.replace(&node, &"d".repeat(32)),
                ..replacement.clone()
            },
            TransportBinding {
                endpoint: format!("{}/4", replacement.endpoint.rsplit_once('/').unwrap().0),
                ..replacement.clone()
            },
            TransportBinding {
                release_id: "different-release".into(),
                ..replacement.clone()
            },
        ] {
            assert!(!tui_later_generation(
                &registered,
                &tui_sender_key(&changed, false)
            ));
        }
        let legacy = tui_binding_key(&original, false);
        let legacy_v2 = format!(
            "v2:{}:{}:{}",
            original.environment_id,
            original.generation,
            legacy.strip_prefix("v1:").unwrap(),
        );
        for stored in [legacy, legacy_v2] {
            assert!(tui_same_binding(&stored, &registered));
            assert!(!tui_same_binding(&stored, &current));
            assert!(!tui_later_generation(&stored, &current));
        }
        let fixture = tui_sender_key(&original, true);
        assert!(tui_same_binding(&fixture, &fixture));
        assert!(!tui_later_generation(&fixture, &current));
    }

    /// 历史凭据覆盖原位置的早期代次。新状态仍要和实际空闲观测吻合。
    #[test]
    fn tui_rollback_requires_original_scope_and_current_observation() {
        let environment = "a".repeat(32);
        let endpoint = format!("http://flower2api-0123456789ab-{environment}:8091");
        let binding = |generation, release: &str| TuiBindingProof {
            account_id: 7,
            environment_id: environment.clone(),
            generation,
            endpoint: endpoint.clone(),
            release_id: release.into(),
        };
        let old = binding(168, "older-release").key();
        let current = binding(174, "current-release").key();
        let proof = |stopped, predecessors| TuiRollbackProof {
            scope: binding(174, "current-release"),
            stopped,
            predecessors,
        };
        assert_eq!(
            proof(false, vec![binding(172, "previous-release")]).confirm(7, &old, Some(&current)),
            None
        );
        assert_eq!(
            proof(false, vec![binding(171, "older-release")]).confirm(7, &old, Some(&current)),
            Some(TuiRollbackReadiness::Running)
        );
        assert_eq!(
            proof(true, vec![binding(171, "older-release")]).confirm(7, &old, None),
            Some(TuiRollbackReadiness::Stopped)
        );
        assert_eq!(
            proof(true, vec![]).confirm(7, &current, Some(&current)),
            None
        );
        assert_eq!(proof(false, vec![]).confirm(7, &current, None), None);
        assert_eq!(proof(true, vec![]).confirm(8, &current, None), None);
        let later = binding(175, "current-release").key();
        assert_eq!(
            proof(false, vec![binding(171, "older-release")]).confirm(7, &old, Some(&later)),
            None
        );
        let mut different_assignment = binding(171, "older-release");
        different_assignment.endpoint.push_str("/different");
        assert_eq!(
            proof(true, vec![different_assignment]).confirm(7, &old, None),
            None
        );
    }

    /// 公开 V2 错误保持 sender 原状态和字节，提交超时之后也不调用取消。
    #[tokio::test]
    async fn tui_reservation_sends_once_and_only_cancels_before_submission() {
        use axum::body::to_bytes;
        use futures_util::stream::once;
        use tokio::sync::{Notify, mpsc, oneshot};
        use tokio::time::sleep_until;

        let (observations, mut events) = mpsc::unbounded_channel();
        let app = Router::new().route(
            "/internal/tui-v2/cancel",
            post(move |headers: HeaderMap| {
                let observations = observations.clone();
                async move {
                    observations
                        .send(("cancel", headers["x-v3-tui-reservation"].clone()))
                        .unwrap();
                    StatusCode::NO_CONTENT
                }
            }),
        );
        let (sends, mut sent) = mpsc::unbounded_channel();
        let release_body = Arc::new(Notify::new());
        let sender_barrier = release_body.clone();
        let (late_replies, mut late_reply) = mpsc::unbounded_channel();
        let app = app.route(
            "/internal/tui-v2/send",
            post(move |headers: HeaderMap| {
                let sends = sends.clone();
                let sender_barrier = sender_barrier.clone();
                let late_replies = late_replies.clone();
                async move {
                    assert!(tui_delegates_json(&headers));
                    let reservation = headers["x-v3-tui-reservation"].to_str().unwrap().to_owned();
                    sends.send(reservation.clone()).unwrap();
                    if reservation == "legacy-relay" {
                        return (
                            StatusCode::BAD_REQUEST,
                            [(TUI_SIGNATURE_REPAIR, "pending")],
                            "首个签名拒绝",
                        )
                            .into_response();
                    }
                    if reservation == "delegated" {
                        let body = Body::from_stream(once(async move {
                            sender_barrier.notified().await;
                            Ok::<_, IoError>(Bytes::from_static(br#"{"id":"msg_upstream","type":"message","content":[],"usage":{"cache_read_input_tokens":4210}}"#))
                        }));
                        return ([(CONTENT_TYPE.as_str(), "application/json"), (TUI_GATEWAY_ID_HEADER, TUI_JSON_PROJECTION_V1)], body).into_response();
                    }
                    if reservation == "unknown" {
                        tokio::time::sleep(Duration::from_secs(1)).await;
                    }
                    if reservation.starts_with("late-") {
                        let (release, ready) = oneshot::channel();
                        late_replies.send(release).unwrap();
                        let _ = ready.await;
                        if reservation == "late-model" {
                            return StatusCode::OK.into_response();
                        }
                        let stage = if reservation == "late-provider" {
                            "local_provider_http"
                        } else {
                            TUI_SUBMISSION_LEDGER
                        };
                        let mut response = (
                            StatusCode::TOO_MANY_REQUESTS,
                            [(TUI_ERROR_SOURCE, stage), (RETRY_AFTER.as_str(), "1")],
                        ).into_response();
                        if reservation == "late-duplicate-ledger" {
                            response.headers_mut().append(TUI_ERROR_SOURCE, HeaderValue::from_static(stage));
                        }
                        return response;
                    }
                    if reservation == "delegated429" {
                        return (
                            StatusCode::TOO_MANY_REQUESTS,
                            [(CONTENT_TYPE.as_str(), "application/json"), (TUI_GATEWAY_ID_HEADER, TUI_JSON_PROJECTION_V1),
                             (TUI_ERROR_SOURCE, "local_provider_http"), (RETRY_AFTER.as_str(), "0")],
                            r#"{"type":"error","error":{"type":"rate_limit_error","message":"busy"}}"#,
                        ).into_response();
                    }
                    let status =
                        StatusCode::from_bytes(reservation.as_bytes()).unwrap_or(StatusCode::OK);
                    let mut response =
                        (status, [(CONTENT_TYPE, "application/json")], "原始错误字节")
                            .into_response();
                    response.headers_mut().insert(TUI_ERROR_SOURCE, HeaderValue::from_static("local_provider_http"));
                    response.headers_mut().insert(RETRY_AFTER, HeaderValue::from_static("57"));
                    if reservation == "projected" {
                        response
                            .headers_mut()
                            .insert(TUI_GATEWAY_ID_HEADER, HeaderValue::from_static("gateway"));
                    }
                    response
                }
            }),
        )
        .route(
            "/internal/tui-v2/repair",
            post(async |headers: HeaderMap| {
                assert_eq!(headers["x-v3-tui-reservation"], "legacy-relay");
                assert!(Uuid::parse_str(headers[TUI_REPAIR_ATTEMPT].to_str().unwrap()).is_ok());
                (StatusCode::NOT_FOUND, [(ERROR_HEADER, "before-send")])
            }),
        );
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let reservation = |id: &str| TuiReservation {
            client: Client::builder()
                .no_proxy()
                .redirect(Policy::none())
                .build()
                .unwrap(),
            binding: TransportBinding {
                account_id: 1,
                environment_id: "synthetic".into(),
                generation: 1,
                endpoint: endpoint.clone(),
                secret: "synthetic-private".into(),
                release_id: "synthetic".into(),
            },
            identity_header: id.into(),
            admission_deadline: Instant::now() + Duration::from_secs(5),
            attempt_id: id.into(),
            agent_header_used: false,
            capture_state: None,
            wire_capture: false,
            capture: None,
            input_policy: false,
            model_header_policy: false,
            session_mapping: false,
            title_session_mapping: false,
            upstream_session: None,
            managed_oauth: false,
            oauth_file: false,
            tui_oauth_profile: None,
            submission_started: false,
            signature_repair: false,
            repair_pending: false,
            continuation: false,
            recovered: false,
        };
        drop(reservation("before-send"));
        let (action, identity) = timeout(Duration::from_secs(2), events.recv())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            (action, identity.to_str().unwrap()),
            ("cancel", "before-send")
        );
        let mut legacy_relay = reservation("legacy-relay");
        legacy_relay.signature_repair = true;
        let first = legacy_relay
            .submit_with_account_credentials(Instant::now() + Duration::from_secs(2), None, None)
            .await
            .unwrap();
        assert_eq!(first.status(), StatusCode::BAD_REQUEST);
        assert!(legacy_relay.repair_pending);
        assert_eq!(sent.recv().await.unwrap(), "legacy-relay");
        assert!(
            legacy_relay
                .submit_signature_repair(Uuid::new_v4(), Duration::from_secs(2))
                .await
                .unwrap()
                .is_none()
        );
        drop(legacy_relay);
        let (action, identity) = timeout(Duration::from_secs(2), events.recv())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(
            (action, identity.to_str().unwrap()),
            ("cancel", "legacy-relay")
        );
        assert_eq!(first.text().await.unwrap(), "首个签名拒绝");
        for status in [401, 403, 429] {
            let id = status.to_string();
            let response = reservation(&id)
                .submit(Duration::from_secs(2))
                .await
                .unwrap();
            let public = tui_public_response(response, None).await.unwrap();
            assert_eq!(public.status().as_u16(), status);
            assert_eq!(
                public.headers().get(RETRY_AFTER).map(HeaderValue::as_bytes),
                (status == 429).then_some(b"57".as_slice())
            );
            assert!(!public.headers().contains_key(TUI_ERROR_SOURCE));
            assert_eq!(
                to_bytes(public.into_body(), 1024).await.unwrap(),
                "原始错误字节"
            );
            assert_eq!(sent.recv().await.unwrap(), id);
        }
        let response = reservation("delegated429")
            .submit(Duration::from_secs(2))
            .await
            .unwrap();
        let public = tui_public_response(response, None).await.unwrap();
        assert_eq!(public.status(), StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(public.headers()[RETRY_AFTER], "0");
        assert!(!public.headers().contains_key(TUI_ERROR_SOURCE));
        assert_eq!(sent.recv().await.unwrap(), "delegated429");
        let projected = reservation("projected")
            .submit(Duration::from_secs(2))
            .await
            .unwrap();
        let public = tui_public_response(projected, None).await.unwrap();
        assert!(public.extensions().get::<TuiGatewayIds>().is_some());
        assert!(!public.headers().contains_key(TUI_GATEWAY_ID_HEADER));
        assert_eq!(sent.recv().await.unwrap(), "projected");

        let budget = Duration::from_secs(2);
        let expiry = Instant::now() + budget;
        let delegated = reservation("delegated").submit(budget).await.unwrap();
        assert!(Instant::now() < expiry);
        assert!(tui_delegates_json(delegated.headers()));
        let (public, ()) = tokio::join!(tui_public_response(delegated, None), async {
            sleep_until(expiry + Duration::from_millis(100)).await;
            assert!(Instant::now() > expiry);
            release_body.notify_one();
        });
        let public = public.unwrap();
        assert_eq!(public.status(), StatusCode::OK);
        assert!(public.extensions().get::<TuiGatewayIds>().is_some());
        assert!(!public.headers().contains_key(TUI_GATEWAY_ID_HEADER));
        let body: Value =
            serde_json::from_slice(&to_bytes(public.into_body(), 1024).await.unwrap()).unwrap();
        assert!(
            Uuid::parse_str(body["id"].as_str().unwrap().strip_prefix("msg_").unwrap()).is_ok()
        );
        assert_eq!(body["usage"]["cache_read_input_tokens"], 4210);
        assert_eq!(sent.recv().await.unwrap(), "delegated");
        for (id, shared, continuation, expected_rejection) in [
            ("late-ledger", true, true, true),
            ("late-provider", true, true, false),
            ("late-model", true, true, false),
            ("late-duplicate-ledger", true, true, false),
            ("late-ledger", false, true, false),
            ("late-ledger", true, false, false),
        ] {
            let mut prepared = reservation(id);
            prepared.continuation = continuation;
            let deadline = Instant::now() + Duration::from_millis(150);
            if shared {
                prepared.admission_deadline = deadline;
            }
            let (result, ()) = tokio::join!(
                prepared.submit_with_account_credentials(deadline, None, None),
                async {
                    assert_eq!(sent.recv().await.unwrap(), id);
                    let release = late_reply.recv().await.unwrap();
                    sleep_until(deadline + Duration::from_millis(25)).await;
                    let _ = release.send(());
                }
            );
            if expected_rejection {
                let response = result.unwrap();
                assert_eq!(
                    tui_failure_stage(response.headers(), &[TUI_SUBMISSION_LEDGER]),
                    Some(TUI_SUBMISSION_LEDGER)
                );
                let public = tui_public_response(response, None).await.unwrap();
                assert_eq!(public.status(), StatusCode::TOO_MANY_REQUESTS);
                assert_eq!(public.headers()[RETRY_AFTER], "1");
                assert!(!public.headers().contains_key(TUI_ERROR_SOURCE));
            } else {
                assert!(
                    matches!(result, Err(AppError::BadGateway(_))),
                    "{id} 共用截止={shared} 原工具回执={continuation}"
                );
            }
        }
        let mut unknown = reservation("unknown");
        let deadline = Instant::now() + Duration::from_millis(500);
        unknown.continuation = true;
        unknown.admission_deadline = deadline;
        let failed = unknown
            .submit_with_account_credentials(deadline, None, None)
            .await;
        assert!(matches!(failed, Err(AppError::BadGateway(_))));
        assert_eq!(sent.recv().await.unwrap(), "unknown");
        drop(unknown);
        assert!(
            timeout(Duration::from_millis(100), events.recv())
                .await
                .is_err()
        );
        assert!(sent.try_recv().is_err());
        server.abort();
    }

    /// 真实 sender 路由接受空分块信封，并在记录提交或取消前拒绝附带的数据。
    #[cfg(target_os = "linux")]
    #[tokio::test]
    async fn tui_sender_control_routes_accept_empty_chunked_requests() {
        use futures_util::stream::iter;
        use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
        use tokio::net::TcpStream;

        let config_path = std::env::temp_dir().join(format!("tui-control-{}.json", Uuid::new_v4()));
        let secret = "synthetic-tui-control-sender-secret";
        let config = json!({
            "binding": {
                "account_id": 7, "environment_id": "a".repeat(32), "generation": 5,
                "endpoint": "http://localhost:8091", "secret": secret, "release_id": "synthetic",
            },
            "proxy_url": "", "allowed_origin": "https://api.anthropic.com",
        });
        fs::write(&config_path, config.to_string()).unwrap();
        let app = sender_router(config_path.to_str().unwrap().into());
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let origin = format!("http://{address}");
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let client = Client::builder().no_proxy().http1_only().build().unwrap();

        for (action, message) in [
            ("send", "V2 发送只接收原预留信封"),
            ("cancel", "V2 取消只接收原预留信封"),
        ] {
            let request = || {
                client
                    .post(format!("{origin}/internal/tui-v2/{action}"))
                    .bearer_auth(secret)
                    .timeout(Duration::from_secs(3))
            };
            let empty = request()
                .body(reqwest::Body::wrap_stream(empty::<Result<Bytes, IoError>>()))
                .send()
                .await
                .unwrap();
            assert_eq!(empty.status(), StatusCode::BAD_REQUEST);
            assert!(
                empty
                    .text()
                    .await
                    .unwrap()
                    .contains("V2 预留身份或正文不匹配")
            );
            let nonempty = request()
                .body(reqwest::Body::wrap_stream(iter([Ok::<_, IoError>(
                    Bytes::from_static(b"x"),
                )])))
                .send()
                .await
                .unwrap();
            assert_eq!(nonempty.status(), StatusCode::BAD_REQUEST);
            assert!(nonempty.text().await.unwrap().contains(message));

            // 不发送分块结束符也必须在读取预算内返回，避免半开的控制请求占住 sender。
            let mut stalled = BufReader::new(TcpStream::connect(address).await.unwrap());
            let headers = format!(
                "POST /internal/tui-v2/{action} HTTP/1.1\r\nHost: {address}\r\nAuthorization: Bearer {secret}\r\nTransfer-Encoding: chunked\r\n\r\n"
            );
            stalled
                .get_mut()
                .write_all(headers.as_bytes())
                .await
                .unwrap();
            let mut head = String::new();
            timeout(Duration::from_secs(4), stalled.read_line(&mut head))
                .await
                .unwrap()
                .unwrap();
            assert!(head.starts_with("HTTP/1.1 400"), "{head}");
        }
        server.abort();
        fs::remove_file(config_path).unwrap();
    }

    /// 精确AGY动作通过共享准入，跨平台路径和不同上游继续拒绝。@return 无。
    #[test]
    fn agy_action_uses_platform_specific_target_admission() {
        let mut config: SenderConfig = serde_json::from_value(json!({
            "binding":{"account_id":17,"environment_id":"synthetic-env","generation":2,
                "endpoint":"http://localhost:8091","secret":"synthetic-private-secret","release_id":"synthetic"},
            "proxy_url":"","allowed_origin":"https://cloudcode-pa.googleapis.com",
            "agy":{"protocol_version":1,"source_sha256":AGY_SOURCE_SHA256,
                "module_root":"/synthetic/modules","binary_path":"/synthetic/binary","work_root":"/synthetic/work",
                "max_workers":1,"memory_mib":0}
        })).unwrap();
        let mut prepared: PreparedRequest = serde_json::from_value(json!({
            "account_id":17,"environment_id":"synthetic-env","generation":2,
            "request_id":Uuid::new_v4().to_string(),"deadline_unix_ms":now_ms()+60000,
            "method":"POST","target_url":"https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent",
            "headers":[],"preserve_header_casing":false
        })).unwrap();
        assert!(validate_request(&prepared, &config).is_ok());
        for target in [
            "https://cloudcode-pa.googleapis.com/v1/messages",
            "https://cloudcode-pa.googleapis.com/v1internal:generateContent",
            "https://other.example.test/v1internal:streamGenerateContent",
        ] {
            prepared.target_url = target.into();
            assert!(validate_request(&prepared, &config).is_err());
        }
        prepared.target_url =
            "https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent".into();
        config.agy = None;
        assert!(validate_request(&prepared, &config).is_err());
    }

    /// 历史root和每版发行选择兼容解码，执行配置收敛为平台内置。@return 无。
    #[test]
    fn legacy_release_selections_are_normalized_before_sender_execution() {
        let path = temp_dir().join(format!("builtin-sender-{}.json", Uuid::new_v4()));
        let reference = json!({"release":"v0.1.0-beta.6","launcher_sha256":"a".repeat(64)});
        let value = json!({"binding":{"account_id":7,"environment_id":"synthetic","generation":3,
            "endpoint":"http://localhost:8091","secret":"synthetic-private-secret","release_id":"synthetic"},
            "proxy_url":"socks5://127.0.0.1:1080","allowed_origin":"https://api.anthropic.com",
            "native":{"binary_path":"/usr/local/bin/ccrb-runtime","work_root":"/native","memory_mib":0,
                "max_workers":6,"release":reference,"kernel_generation":"old-root",
                "runtimes":{"2.1.280":{"binary_path":"/usr/local/bin/ccrb-runtime-280",
                    "release":reference,"kernel_generation":"old-280"}}}});
        fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
        let config = read_config(path.to_str().unwrap()).unwrap();
        let native = config.native.as_ref().unwrap();
        assert!(native.release.is_none());
        assert!(native.kernel_generation.is_none());
        assert!(native.runtimes.is_empty());
        assert_eq!(native.max_workers, 6);
        assert_eq!(native.source_version, NativeSourceVersion::Cc293);
        assert_eq!(native.binary_path, "/usr/local/bin/ccrb-runtime");
        fs::remove_file(path).unwrap();
    }

    /// 固定后台动作的方法、目标、认证及旧分配在发送前被核对。@return 无。
    #[tokio::test]
    async fn background_sender_rejects_wrong_purpose_target_and_binding_before_upstream() {
        let path = temp_dir().join(format!("background-sender-{}.json", Uuid::new_v4()));
        let secret = "synthetic-background-private-service-secret";
        let proxy = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let config: SenderConfig = serde_json::from_value(json!({
            "binding":{"account_id":7,"environment_id":"synthetic","generation":3,
                "endpoint":"http://localhost:8091","secret":secret,"release_id":"synthetic"},
            "proxy_url":format!("http://{}",proxy.local_addr().unwrap()),"allowed_origin":"https://api.anthropic.com"
        })).unwrap();
        fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let server = tokio::spawn(
            axum::serve(listener, sender_router(path.to_string_lossy().into_owned())).into_future(),
        );
        let prepared = PreparedRequest {
            account_id: 7,
            environment_id: "synthetic".into(),
            generation: 3,
            request_id: Uuid::new_v4().to_string(),
            deadline_unix_ms: now_ms() + 5000,
            method: "GET".into(),
            target_url: crate::service::runtime_background::USAGE_URL.into(),
            headers: vec![],
            preserve_header_casing: false,
            tls_profile: TlsProfileId::ClaudeCode293,
        };
        for (purpose, token, change) in [
            ("arbitrary-url", secret, ""),
            ("usage", secret, "url"),
            ("usage", secret, "generation"),
            ("oauth-refresh", secret, ""),
            ("usage", "wrong", ""),
        ] {
            let mut request = prepared.clone();
            if change == "url" {
                request.target_url = "https://api.anthropic.com/v1/messages".into();
            }
            if change == "generation" {
                request.generation = 2;
            }
            let meta = STANDARD.encode(serde_json::to_vec(&request).unwrap());
            let response = Client::new()
                .post(format!("{endpoint}/internal/send"))
                .bearer_auth(token)
                .header(META_HEADER, meta)
                .header(BACKGROUND_HEADER, purpose)
                .send()
                .await
                .unwrap();
            assert!(!response.status().is_success());
            assert_eq!(response.headers().get(ERROR_HEADER).unwrap(), "before-send");
        }
        assert!(
            timeout(Duration::from_millis(50), proxy.accept())
                .await
                .is_err()
        );
        server.abort();
        let _ = server.await;
        fs::remove_file(path).unwrap();
    }

    /// 实际HTTP桥收到原后台purpose和绑定，正文及原TLS画像保持同一次冻结。@return 无。
    #[tokio::test]
    async fn background_transport_preserves_original_scope_and_fixed_purpose() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let router = Router::new().route(
            "/internal/send",
            post(|headers: HeaderMap, body: Bytes| async move {
                assert_eq!(headers.get(BACKGROUND_HEADER).unwrap(), "usage");
                assert_eq!(
                    headers.get("authorization").unwrap(),
                    "Bearer synthetic-background-secret"
                );
                let decoded = STANDARD.decode(headers.get(META_HEADER).unwrap()).unwrap();
                let request: PreparedRequest = serde_json::from_slice(&decoded).unwrap();
                assert_eq!(request.account_id, 7);
                assert_eq!(request.environment_id, "original-environment");
                assert_eq!(request.generation, 9);
                assert_eq!(request.tls_profile, TlsProfileId::ClaudeCode293);
                assert_eq!(
                    request.target_url,
                    crate::service::runtime_background::USAGE_URL
                );
                assert_eq!(body, Bytes::new());
                Json(json!({"window":"original-usage"}))
            }),
        );
        let server = tokio::spawn(axum::serve(listener, router).into_future());
        let transport = PreparedTransport {
            tool_continuation_mode: AgyToolContinuationMode::Claim,
            long_agy_generation: false,
            tui_predecessors: Vec::new(),
            tui_oauth_profile: None,
            account_id: 7,
            route: PreparedRoute::V3 {
                client: Client::new(),
                binding: TransportBinding {
                    account_id: 7,
                    environment_id: "original-environment".into(),
                    generation: 9,
                    endpoint,
                    secret: "synthetic-background-secret".into(),
                    release_id: "synthetic".into(),
                },
            },
        };
        let request = PreparedRequest {
            account_id: 0,
            environment_id: String::new(),
            generation: 0,
            request_id: String::new(),
            deadline_unix_ms: 0,
            method: "GET".into(),
            target_url: crate::service::runtime_background::USAGE_URL.into(),
            headers: vec![],
            preserve_header_casing: false,
            tls_profile: TlsProfileId::ClaudeCode293,
        };
        let response = transport
            .submit_background(
                request,
                &[],
                Duration::from_secs(5),
                BackgroundPurpose::Usage,
            )
            .await
            .unwrap();
        assert_eq!(
            response.json::<Value>().await.unwrap()["window"],
            "original-usage"
        );
        server.abort();
        let _ = server.await;
    }

    /// 真实HTTP策略同步检查鉴权、账号代次、范围及旧sender兼容。@return 无。
    #[tokio::test]
    async fn native_idle_policy_requires_authentication_and_exact_binding() {
        let path = temp_dir().join(format!("native-idle-policy-{}.json", Uuid::new_v4()));
        let secret = "synthetic-idle-policy-private-service-secret";
        let config: SenderConfig = serde_json::from_value(json!({
            "native":{"binary_path":"/unused","work_root":"/unused","memory_mib":0,"max_workers":8},
            "binding":{"account_id":7,"environment_id":"synthetic","generation":1,
                "endpoint":"http://localhost:8091","secret":secret,"release_id":"synthetic"},
            "proxy_url":"","allowed_origin":"https://api.anthropic.com"
        }))
        .unwrap();
        fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let server = tokio::spawn(
            axum::serve(listener, sender_router(path.to_string_lossy().into_owned())).into_future(),
        );
        let transport = PreparedTransport {
            tool_continuation_mode: AgyToolContinuationMode::Claim,
            long_agy_generation: false,
            tui_predecessors: Vec::new(),
            tui_oauth_profile: None,
            account_id: 7,
            route: PreparedRoute::V3 {
                client: Client::new(),
                binding: TransportBinding {
                    endpoint: endpoint.clone(),
                    ..config.binding.clone()
                },
            },
        };
        assert!(transport.sync_native_idle_timeout(60).await.unwrap());
        assert!(transport.sync_native_idle_timeout(300).await.unwrap());
        for (token, account_id, generation, seconds, expected) in [
            ("wrong", 7, 1, 120, StatusCode::UNAUTHORIZED),
            (secret, 8, 1, 120, StatusCode::SERVICE_UNAVAILABLE),
            (secret, 7, 2, 120, StatusCode::SERVICE_UNAVAILABLE),
            (secret, 7, 1, 0, StatusCode::BAD_REQUEST),
            (secret, 7, 1, 3601, StatusCode::BAD_REQUEST),
        ] {
            let response = Client::new().post(format!("{endpoint}/internal/native/idle-policy"))
                .bearer_auth(token).json(&json!({"account_id":account_id,"environment_id":"synthetic","generation":generation,"idle_timeout_secs":seconds}))
                .send().await.unwrap();
            assert_eq!(response.status(), expected);
        }
        server.abort();
        let _ = server.await;
        fs::remove_file(path).unwrap();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let old = tokio::spawn(async move {
            axum::serve(listener, Router::new()).await.unwrap();
        });
        let transport = PreparedTransport {
            tool_continuation_mode: AgyToolContinuationMode::Claim,
            long_agy_generation: false,
            tui_predecessors: Vec::new(),
            tui_oauth_profile: None,
            account_id: 7,
            route: PreparedRoute::V3 {
                client: Client::new(),
                binding: TransportBinding {
                    endpoint,
                    ..config.binding
                },
            },
        };
        assert!(!transport.sync_native_idle_timeout(120).await.unwrap());
        old.abort();
        let _ = old.await;
    }

    /// 老 sender 的单版默认和双版报告均须能定位 293。显式的 280 单版报告不能通过。
    #[tokio::test]
    async fn native_ready_requires_293_in_legacy_or_versioned_capabilities() {
        let app = Router::new().route(
            "/:case/internal/native/status",
            get(
                |axum::extract::Path(case): axum::extract::Path<String>| async move {
                    let mut reply =
                        json!({"raw_input_protocol":1,"environment_id":"synthetic","generation":1});
                    match case.as_str() {
                        "legacy-default" => {}
                        "legacy-293" => reply["version"] = json!("2.1.293"),
                        "legacy-280" => reply["version"] = json!("2.1.280"),
                        "dual" => {
                            reply["versions"] =
                                json!({"2.1.280":{"available":true},"2.1.293":{"available":true}})
                        }
                        "missing-293" => reply["versions"] = json!({"2.1.280":{"available":true}}),
                        _ => unreachable!(),
                    }
                    Json(reply)
                },
            ),
        );
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let origin = format!("http://{}", listener.local_addr().unwrap());
        let server = tokio::spawn(axum::serve(listener, app).into_future());
        for (case, ready) in [
            ("legacy-default", true),
            ("legacy-293", true),
            ("legacy-280", false),
            ("dual", true),
            ("missing-293", false),
        ] {
            let transport = PreparedTransport {
                tool_continuation_mode: AgyToolContinuationMode::Claim,
                long_agy_generation: false,
                tui_predecessors: Vec::new(),
                tui_oauth_profile: None,
                account_id: 7,
                route: PreparedRoute::V3 {
                    client: Client::builder().no_proxy().build().unwrap(),
                    binding: TransportBinding {
                        environment_id: "synthetic".into(),
                        generation: 1,
                        account_id: 7,
                        endpoint: format!("{origin}/{case}"),
                        secret: "fixture".into(),
                        release_id: "fixture".into(),
                    },
                },
            };
            assert_eq!(transport.native_ready().await.is_ok(), ready, "{case}");
        }
        server.abort();
    }

    /// 鉴权后的每个原生入口拒绝显式 280，历史双版配置只公布 293 能力。
    #[tokio::test]
    async fn native_sender_rejects_retired_version_before_any_execution() {
        let directory = temp_dir().join(format!("retired-worker-{}", Uuid::new_v4()));
        fs::create_dir(&directory).unwrap();
        let path = directory.join("sender.json");
        let work = directory.join("workers");
        let secret = "synthetic-retired-private-service-secret";
        fs::write(&path, json!({
            "binding":{"account_id":7,"environment_id":"synthetic","generation":1,
                "endpoint":"http://localhost:8091","secret":secret,"release_id":"synthetic"},
            "proxy_url":"","allowed_origin":"https://api.anthropic.com",
            "native":{"binary_path":"/missing-293","work_root":work,"memory_mib":0,"max_workers":8,
                "runtimes":{"2.1.280":{"binary_path":"/retired-280"}}}
        }).to_string()).unwrap();
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let origin = format!("http://{}/internal/native", listener.local_addr().unwrap());
        let server = tokio::spawn(
            axum::serve(listener, sender_router(path.to_string_lossy().into_owned())).into_future(),
        );
        let client = Client::builder().no_proxy().build().unwrap();
        let status: Value = client
            .get(format!("{origin}/status"))
            .bearer_auth(secret)
            .send()
            .await
            .unwrap()
            .json()
            .await
            .unwrap();
        assert_eq!(
            status["versions"],
            json!({"2.1.293":{"available":false,"version":"2.1.293"}})
        );
        let id = Uuid::new_v4().to_string();
        let deadline = now_ms() + 30_000;
        let control = json!({"source_version":"2.1.280","account_id":7,"environment_id":"synthetic",
            "generation":1,"preparation_id":id});
        let mut prepare = control.clone();
        prepare.as_object_mut().unwrap().extend(
            json!({"deadline_unix_ms":deadline,
            "bearer":"synthetic-bearer","device_id":"a".repeat(64),"email":"test@example.invalid",
            "concurrency":4})
            .as_object()
            .unwrap()
            .clone(),
        );
        let submission = serde_json::to_value(preparation_identity(
            serde_json::from_value(prepare.clone()).unwrap(),
            &read_config(path.to_str().unwrap()).unwrap(),
        ))
        .unwrap();
        for (route, body) in [
            ("prepare", &prepare),
            ("readiness", &prepare),
            ("prepare/cancel", &control),
            ("messages", &submission),
        ] {
            let reply = client
                .post(format!("{origin}/{route}"))
                .bearer_auth(secret)
                .json(body)
                .send()
                .await
                .unwrap();
            assert_eq!(reply.status(), StatusCode::BAD_REQUEST, "{route}");
            if route == "messages" {
                assert_eq!(reply.headers()[ERROR_HEADER], "before-send");
            }
            assert!(reply.text().await.unwrap().contains("2.1.293"), "{route}");
        }
        assert!(!work.exists());
        server.abort();
        fs::remove_dir_all(directory).unwrap();
    }

    /// 旧账号从历史版本表取回 293 路径和原额度，缺少 293 时明确拒绝执行。
    #[test]
    fn legacy_native_installations_admit_only_the_registered_293_runtime() {
        let path = temp_dir().join(format!("legacy-sender-{}.json", Uuid::new_v4()));
        let mut document = json!({
            "native":{"source_version":"2.1.280","binary_path":"/usr/local/bin/ccrb-runtime-280",
                "work_root":"/native","memory_mib":128,"max_workers":8},
            "binding":{"account_id":7,"environment_id":"synthetic","generation":1,
                "endpoint":"http://localhost:8091","secret":"synthetic","release_id":"synthetic"},
            "proxy_url":"","allowed_origin":"https://api.anthropic.com"
        });
        fs::write(&path, document.to_string()).unwrap();
        let retired = read_config(path.to_str().unwrap()).unwrap().native.unwrap();
        assert_eq!(retired.source_version, NativeSourceVersion::Cc280);
        assert!(retired.verify().is_err());
        document["native"]["runtimes"] = json!({
            "2.1.280":{"binary_path":"/unused-old-worker"},
            "2.1.293":{"binary_path":"/registered-293"}
        });
        fs::write(&path, document.to_string()).unwrap();
        let native = read_config(path.to_str().unwrap()).unwrap().native.unwrap();
        assert_eq!(native.source_version, NativeSourceVersion::Cc293);
        assert_eq!(
            (native.binary_path.as_str(), native.work_root.as_str()),
            ("/registered-293", "/native")
        );
        assert!(native.runtimes.is_empty());
        assert_eq!((native.memory_mib, native.max_workers), (128, 8));
        fs::remove_file(path).unwrap();
    }

    #[tokio::test]
    async fn sender_preserves_tls_profile_legacy_default_and_rejects_unknown_before_submission() {
        let proxy = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let proxy_url = format!("http://{}", proxy.local_addr().unwrap());
        let capture = tokio::spawn(async move {
            let mut records = Vec::new();
            for _ in 0..3 {
                let (mut stream, _) = proxy.accept().await.unwrap();
                let mut connect = Vec::new();
                while !connect.ends_with(b"\r\n\r\n") {
                    assert!(connect.len() < 8192);
                    let mut byte = [0];
                    stream.read_exact(&mut byte).await.unwrap();
                    connect.extend_from_slice(&byte);
                }
                assert!(connect.starts_with(b"CONNECT api.anthropic.com:443 "));
                stream
                    .write_all(b"HTTP/1.1 200 Connection established\r\n\r\n")
                    .await
                    .unwrap();
                let mut header = [0; 5];
                stream.read_exact(&mut header).await.unwrap();
                let size = usize::from(u16::from_be_bytes([header[3], header[4]]));
                assert!(size <= 16384);
                let mut wire = header.to_vec();
                wire.resize(5 + size, 0);
                stream.read_exact(&mut wire[5..]).await.unwrap();
                records.push(wire);
            }
            // 不再接受上游；若未知 ID 错误放行，将表现为提交失败而不是预期的本地400。
            records
        });
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let config = SenderConfig {
            agy: None,
            native: None,
            binding: TransportBinding {
                account_id: 7,
                environment_id: "synthetic-tls".into(),
                generation: 1,
                endpoint: endpoint.clone(),
                secret: "synthetic-private-sender-key".repeat(3),
                release_id: "test".into(),
            },
            proxy_url,
            allowed_origin: "https://api.anthropic.com".into(),
            evidence_file: None,
            native_capture_dir: None,
            native_adaptive_prewarm: false,
            quota_identity: String::new(),
        };
        let path = temp_dir().join(format!("sender-tls-{}.json", Uuid::new_v4()));
        fs::write(&path, serde_json::to_vec(&config).unwrap()).unwrap();
        let app = sender_router(path.to_string_lossy().into_owned());
        let sender = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        let request = PreparedRequest {
            account_id: 7,
            environment_id: config.binding.environment_id.clone(),
            generation: 1,
            request_id: Uuid::new_v4().to_string(),
            deadline_unix_ms: now_ms() + 30_000,
            method: "POST".into(),
            target_url: "https://api.anthropic.com/v1/messages".into(),
            headers: vec![("Content-Type".into(), "application/json".into())],
            preserve_header_casing: true,
            tls_profile: TlsProfileId::default(),
        };
        let client = Client::builder().no_proxy().build().unwrap();
        for profile in [
            Some(TlsProfileId::ClaudeCode293),
            Some(TlsProfileId::TestReordered),
            None,
        ] {
            let mut meta = serde_json::to_value(&request).unwrap();
            match profile {
                Some(profile) => meta["tls_profile"] = serde_json::to_value(profile).unwrap(),
                None => {
                    meta.as_object_mut().unwrap().remove("tls_profile");
                }
            }
            let response = client
                .post(format!("{endpoint}/internal/send"))
                .bearer_auth(&config.binding.secret)
                .header(
                    META_HEADER,
                    STANDARD.encode(serde_json::to_vec(&meta).unwrap()),
                )
                .body("{}")
                .send()
                .await
                .unwrap();
            assert_eq!(response.status().as_u16(), 502);
        }
        let records = timeout(Duration::from_secs(5), capture)
            .await
            .unwrap()
            .unwrap();
        let parsed: Vec<Value> = records
            .iter()
            .map(|wire| parse_test_clienthello(wire))
            .collect();
        assert_eq!(parsed[0]["ja3"]["md5"], "1523504b38f0fae0d881d4b6554aac1b");
        assert_ne!(parsed[0]["ja3"], parsed[1]["ja3"]);
        assert_eq!(parsed[0]["ja3"], parsed[2]["ja3"]);
        let mut meta = serde_json::to_value(&request).unwrap();
        meta["tls_profile"] = json!("unknown-unregistered");
        let response = client
            .post(format!("{endpoint}/internal/send"))
            .bearer_auth(&config.binding.secret)
            .header(
                META_HEADER,
                STANDARD.encode(serde_json::to_vec(&meta).unwrap()),
            )
            .body("{}")
            .send()
            .await
            .unwrap();
        assert_eq!(response.status().as_u16(), 400);
        assert_eq!(response.headers()[ERROR_HEADER], "before-send");
        let status: Value = client
            .get(format!("{endpoint}/internal/status"))
            .bearer_auth(&config.binding.secret)
            .send()
            .await
            .unwrap()
            .json()
            .await
            .unwrap();
        assert_eq!(status["active"], 0);
        sender.abort();
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn execution_location_freezes_remote_identity_and_omits_secrets() {
        let environment_id = "e".repeat(32);
        let node_key = "a".repeat(32);
        let binding = TransportBinding {
            account_id: 7,
            environment_id: environment_id.clone(),
            generation: 5,
            endpoint: format!(
                "http://orchestrator:8000/cluster-transports/v2/0123456789ab/{node_key}/{environment_id}/3"
            ),
            secret: "synthetic-private-transport-secret".into(),
            release_id: "synthetic-release".into(),
        };
        let mut transport = PreparedTransport {
            tool_continuation_mode: AgyToolContinuationMode::Claim,
            long_agy_generation: false,
            tui_predecessors: Vec::new(),
            tui_oauth_profile: None,
            account_id: 7,
            route: PreparedRoute::V3 {
                client: Client::new(),
                binding,
            },
        };
        let frozen = transport.execution_location().unwrap();
        assert_eq!(
            frozen,
            ExecutionLocation {
                node_key,
                environment_id,
                generation: 5,
                assignment_revision: Some(3)
            }
        );
        let public = serde_json::to_string(&frozen).unwrap();
        assert!(!public.contains("secret"));
        assert!(!public.contains("orchestrator"));
        if let PreparedRoute::V3 { binding, .. } = &mut transport.route {
            binding.endpoint = "http://flower2api-local:8091".into();
            binding.generation = 6;
        }
        let local = transport.execution_location().unwrap();
        assert_eq!(local.node_key, "local");
        assert_eq!(local.assignment_revision, None);
        assert_eq!(frozen.generation, 5);
        assert!(
            PreparedTransport {
                tool_continuation_mode: AgyToolContinuationMode::Claim,
                long_agy_generation: false,
                tui_predecessors: Vec::new(),
                tui_oauth_profile: None,
                account_id: 7,
                route: PreparedRoute::Direct(String::new())
            }
            .execution_location()
            .is_none()
        );
    }

    #[test]
    fn node_relay_endpoint_requires_fixed_origin_and_full_identity() {
        let base = reqwest::Url::parse("http://orchestrator:8000").unwrap();
        let environment_id = "e".repeat(32);
        let node_key = "a".repeat(32);
        let deployment_key = "0123456789ab";
        let endpoint = format!(
            "http://orchestrator:8000/cluster-transports/v2/{deployment_key}/{node_key}/{environment_id}/3"
        );
        let matches = |value: &str| {
            remote_endpoint_matches(
                &reqwest::Url::parse(value).unwrap(),
                &base,
                &environment_id,
                deployment_key,
            )
        };
        assert!(matches(&endpoint));
        for invalid in [
            endpoint.replace("orchestrator", "foreign-node"),
            endpoint.replace(":8000", ":8001"),
            endpoint.replace("http:", "https:"),
            endpoint.replace(deployment_key, "other-release"),
            endpoint.replace(&node_key, "short-node"),
            endpoint.replace(&environment_id, &"f".repeat(32)),
            endpoint.replace("/3", "/03"),
            endpoint.replace("/3", "/0"),
            endpoint.replace("/3", "/-1"),
            format!("{endpoint}/internal/send"),
        ] {
            assert!(!matches(&invalid), "accepted {invalid}");
        }
    }

    #[test]
    fn previous_account_source_requires_the_same_environment_and_generation() {
        let mut binding = TransportBinding {
            account_id: 7,
            environment_id: "a".repeat(32),
            generation: 2,
            endpoint: String::new(),
            secret: String::new(),
            release_id: "ci-1-1".into(),
        };
        let record = json!({
            "schema_version": 1, "deployment": "isolated", "control_release": "ci-2-1", "account_release": "ci-2-1",
            "environments": { (&binding.environment_id): { "gateway_account_id": 7, "generation": 2,
                "origin": { "environment_id": &binding.environment_id, "release": "ci-1-1", "protocol": 1 } } }
        });
        let matches = |binding: &TransportBinding| {
            rollout_matches(&record, binding, "isolated", "ci-2-1", "ci-2-1")
        };
        assert!(matches(&binding));
        assert!(!rollout_matches(
            &record, &binding, "isolated", "ci-3-1", "ci-2-1"
        ));
        binding.generation = 3;
        assert!(!matches(&binding));
        binding.generation = 2;
        binding.account_id = 8;
        assert!(!matches(&binding));
        binding.account_id = 7;
        binding.environment_id = "b".repeat(32);
        assert!(!matches(&binding));
    }

    #[test]
    fn gateway_accepts_short_account_dns_and_rejects_foreign_bindings() {
        let deployment = "synthetic-deployment";
        let key = format!("{:x}", Sha256::digest(deployment.as_bytes()));
        let environment_id = "a".repeat(32);
        let binding = TransportBinding {
            account_id: 7,
            environment_id: environment_id.clone(),
            generation: 2,
            endpoint: format!("http://v3-{}-account-{environment_id}:8091", &key[..12]),
            secret: "synthetic-secret-".repeat(4),
            release_id: "test".into(),
        };
        assert!(validate_binding(&binding, 7, deployment, "test").is_ok());
        let renamed = TransportBinding {
            endpoint: format!("http://flower2api-{}-{environment_id}:8091", &key[..12]),
            ..binding.clone()
        };
        assert!(validate_binding(&renamed, 7, deployment, "test").is_ok());
        assert!(validate_binding(&renamed, 8, deployment, "test").is_err());
        assert!(validate_binding(&renamed, 7, "other-deployment", "test").is_err());
        assert!(validate_binding(&binding, 8, deployment, "test").is_err());
        assert!(validate_binding(&binding, 7, "other-deployment", "test").is_err());
        assert!(validate_binding(&binding, 7, deployment, "other-release").is_err());
        assert!(validate_binding(&binding, 7, "", "test").is_err());
        assert!(validate_binding(&binding, 7, deployment, "").is_err());
        for endpoint in [
            format!("http://vibebench-v3-{deployment}-account-{environment_id}:8091"),
            format!(
                "http://flower2api-{}-account-{environment_id}:8091",
                &key[..12]
            ),
            format!("http://flower2api-{}-{}:8091", &key[..12], "b".repeat(32)),
            format!("http://v3-{}-account-{}:8091", &key[..12], "b".repeat(32)),
            binding.endpoint.replace(":8091", ":8092"),
            binding.endpoint.replace("http://", "https://"),
            format!("{}/internal/send", binding.endpoint),
            format!("{}?token=synthetic", binding.endpoint),
            format!("{}#fragment", binding.endpoint),
            binding.endpoint.replace("http://", "http://synthetic@"),
        ] {
            let invalid = TransportBinding {
                endpoint,
                ..binding.clone()
            };
            assert!(validate_binding(&invalid, 7, deployment, "test").is_err());
        }
        let invalid = TransportBinding {
            secret: "short".into(),
            ..binding.clone()
        };
        assert!(validate_binding(&invalid, 7, deployment, "test").is_err());
        let invalid = TransportBinding {
            environment_id: "z".repeat(32),
            ..binding
        };
        assert!(validate_binding(&invalid, 7, deployment, "test").is_err());
    }

    /// 私有临时证书和回环 TLS 服务，退出时收口进程并删除资料。
    struct TlsFixture {
        root: PathBuf,
        child: Child,
        address: SocketAddr,
    }

    impl TlsFixture {
        fn start() -> Self {
            let root = std::env::temp_dir().join(format!("v3-tls-{}", Uuid::new_v4()));
            fs::create_dir(&root).unwrap();
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).unwrap();
            }
            let child = Command::new("python3")
                .arg(Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/tls_http.py"))
                .arg(&root)
                .stdin(Stdio::null())
                .stdout(Stdio::piped())
                .spawn()
                .unwrap();
            let mut fixture = Self {
                root,
                child,
                address: SocketAddr::from((Ipv4Addr::LOCALHOST, 0)),
            };
            let mut line = String::new();
            BufReader::new(fixture.child.stdout.take().unwrap())
                .read_line(&mut line)
                .unwrap();
            let value: serde_json::Value = serde_json::from_str(&line).unwrap();
            fixture
                .address
                .set_port(value["port"].as_u64().unwrap().try_into().unwrap());
            fixture
        }

        fn client(&self, trusted: bool, hostname: &str) -> Client {
            let certificate =
                trusted.then(|| CertificateDer::from(fs::read(self.root.join("ca.der")).unwrap()));
            test_request_client(certificate, hostname, self.address).unwrap()
        }

        fn request(&self, hostname: &str, path: &str) -> PreparedRequest {
            PreparedRequest {
                tls_profile: TlsProfileId::default(),
                account_id: 7,
                environment_id: "synthetic".into(),
                generation: 1,
                request_id: Uuid::new_v4().to_string(),
                deadline_unix_ms: now_ms() + 5000,
                method: "POST".into(),
                target_url: format!("https://{hostname}:{}{path}", self.address.port()),
                headers: vec![
                    ("Authorization".into(), "Bearer synthetic".into()),
                    ("Content-Type".into(), "application/json".into()),
                    ("X-Order-A".into(), "a".into()),
                    ("X-Order-B".into(), "b".into()),
                ],
                preserve_header_casing: true,
            }
        }
    }

    impl Drop for TlsFixture {
        fn drop(&mut self) {
            let _ = self.child.kill();
            let _ = self.child.wait();
            let _ = fs::remove_dir_all(&self.root);
        }
    }

    #[tokio::test]
    async fn local_https_preserves_bytes_and_rejects_untrusted_or_wrong_hostname() {
        let fixture = TlsFixture::start();
        let prepared = fixture.request("api.anthropic.com", "/v1/messages");
        let body = b"{ \"synthetic\" : true }\n".to_vec();
        let response = timeout(
            Duration::from_secs(5),
            send_with_client(
                &fixture.client(true, "api.anthropic.com"),
                &prepared,
                body.clone(),
            ),
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(response.status().as_u16(), 429);
        assert_eq!(response.headers()["x-tls-fixture"], "verified");
        assert_eq!(response.bytes().await.unwrap(), body);
        let record = fs::read_to_string(fixture.root.join("requests.jsonl")).unwrap();
        let record: serde_json::Value =
            serde_json::from_str(record.lines().next().unwrap()).unwrap();
        let headers = record["headers"].as_array().unwrap();
        assert!(
            headers
                .iter()
                .position(|key| key == "Authorization")
                .unwrap()
                < headers
                    .iter()
                    .position(|key| key == "Content-Type")
                    .unwrap()
        );
        assert!(
            headers.iter().position(|key| key == "X-Order-A").unwrap()
                < headers.iter().position(|key| key == "X-Order-B").unwrap()
        );
        assert!(
            timeout(
                Duration::from_secs(5),
                send_with_client(
                    &fixture.client(false, "api.anthropic.com"),
                    &prepared,
                    vec![]
                )
            )
            .await
            .unwrap()
            .is_err()
        );
        let wrong = fixture.request("wrong.invalid", "/v1/messages");
        assert!(
            timeout(
                Duration::from_secs(5),
                send_with_client(&fixture.client(true, "wrong.invalid"), &wrong, vec![])
            )
            .await
            .unwrap()
            .is_err()
        );
        assert_eq!(
            fs::read_to_string(fixture.root.join("requests.jsonl"))
                .unwrap()
                .lines()
                .count(),
            1
        );
    }

    #[tokio::test]
    async fn local_https_stream_cancel_closes_connection_without_replay() {
        let fixture = TlsFixture::start();
        let prepared = fixture.request("api.anthropic.com", "/stream");
        let client = fixture.client(true, "api.anthropic.com");
        let mut response = timeout(
            Duration::from_secs(5),
            send_with_client(&client, &prepared, b"{}".to_vec()),
        )
        .await
        .unwrap()
        .unwrap();
        assert_eq!(
            timeout(Duration::from_secs(2), response.chunk())
                .await
                .unwrap()
                .unwrap()
                .unwrap(),
            &b"data: a\n\n"[..]
        );
        drop(response);
        timeout(Duration::from_secs(5), async {
            while !fixture.root.join("stream_closed").exists() {
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
        assert_eq!(
            fs::read_to_string(fixture.root.join("requests.jsonl"))
                .unwrap()
                .lines()
                .count(),
            1
        );
    }

    #[test]
    fn rejects_wrong_environment_and_arbitrary_target() {
        let binding = TransportBinding {
            account_id: 7,
            environment_id: "env-a".into(),
            generation: 2,
            endpoint: "http://account-a:8091".into(),
            secret: "x".repeat(64),
            release_id: "test".into(),
        };
        let config = SenderConfig {
            agy: None,
            native: None,
            binding,
            proxy_url: String::new(),
            allowed_origin: "https://api.anthropic.com".into(),
            evidence_file: None,
            native_capture_dir: None,
            native_adaptive_prewarm: false,
            quota_identity: String::new(),
        };
        let mut prepared = PreparedRequest {
            tls_profile: TlsProfileId::default(),
            account_id: 7,
            environment_id: "env-a".into(),
            generation: 2,
            request_id: Uuid::new_v4().to_string(),
            deadline_unix_ms: now_ms() + 30_000,
            method: "POST".into(),
            target_url: "https://api.anthropic.com/v1/messages?beta=true".into(),
            headers: vec![],
            preserve_header_casing: true,
        };
        assert!(validate_request(&prepared, &config).is_ok());
        // 真实宿主采集到约1.3秒回拨；相同合法信封在接收时仍应保持有界预算。
        let issued = 1_800_000_000_000;
        prepared.deadline_unix_ms = issued + 120_000;
        assert_eq!(
            validate_request_at(&prepared, &config, issued - 1275).unwrap(),
            Duration::from_secs(120)
        );
        assert_eq!(
            validate_request_at(&prepared, &config, issued - CLOCK_SKEW_MS).unwrap(),
            Duration::from_secs(120)
        );
        assert!(validate_request_at(&prepared, &config, issued - CLOCK_SKEW_MS - 1).is_err());
        assert!(validate_request_at(&prepared, &config, issued + 120_000).is_err());
        assert!(validate_request_at(&prepared, &config, issued + 120_001).is_err());
        assert_eq!(
            validate_request_at(&prepared, &config, issued + 119_000).unwrap(),
            Duration::from_secs(1)
        );
        let agy_budget_ms = AGY_REQUEST_SECONDS as u64 * 1000;
        prepared.deadline_unix_ms = issued + agy_budget_ms;
        assert!(validate_request_at(&prepared, &config, issued).is_err());
        assert_eq!(
            validate_request_budget(&prepared, &config, issued - CLOCK_SKEW_MS, agy_budget_ms)
                .unwrap(),
            Duration::from_secs(240)
        );
        assert!(
            validate_request_budget(
                &prepared,
                &config,
                issued - CLOCK_SKEW_MS - 1,
                agy_budget_ms
            )
            .is_err()
        );
        assert!(
            validate_request_budget(&prepared, &config, issued + agy_budget_ms, agy_budget_ms)
                .is_err()
        );
        prepared.deadline_unix_ms = now_ms() + 30_000;
        prepared.generation = 1;
        assert!(validate_request(&prepared, &config).is_err());
        prepared.generation = 2;
        prepared.target_url = "http://169.254.169.254/api/metadata".into();
        assert!(validate_request(&prepared, &config).is_err());
    }
    /// 冷环境 HTTP 请求同时就绪后，真实提交仍经过同一账号闸门，压缩流字节不改变。
    #[tokio::test]
    async fn cold_environment_ready_cohort_still_submits_smoothly() {
        use crate::service::v3_scheduling::{RequestPhase, V3Scheduler};
        use crate::store::scheduling_store::SchedulingStore;
        use flate2::{Compression, write::GzEncoder};
        use futures_util::future::join_all;
        use sqlx::any::AnyPoolOptions;
        use std::sync::atomic::AtomicUsize;
        use std::time::Instant as StdInstant;
        use tokio::sync::Barrier;

        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        sqlx::query(
            "CREATE TABLE accounts(id BIGINT PRIMARY KEY,rpm_limit INTEGER NOT NULL DEFAULT 300)",
        )
        .execute(&pool)
        .await
        .unwrap();
        sqlx::query("INSERT INTO accounts(id) VALUES(7)")
            .execute(&pool)
            .await
            .unwrap();
        SchedulingStore::migrate(&pool).await.unwrap();
        let scheduler = Arc::new(V3Scheduler::new(Arc::new(SchedulingStore::new(
            pool.clone(),
        ))));
        let account:Account=serde_json::from_value(json!({"id":7,"name":"合成账号","email":"runtime@example.invalid","status":"active","device_id":"synthetic","canonical_env":{},"canonical_prompt_env":{},"canonical_process":{},"billing_mode":"strip","concurrency":4,"rpm_limit":300,"created_at":chrono::Utc::now(),"updated_at":chrono::Utc::now()})).unwrap();
        let ip = Ipv4Addr::new(
            127,
            77,
            rand::random::<u8>().max(1),
            rand::random::<u8>().max(1),
        );
        let listener = tokio::net::TcpListener::bind(SocketAddr::from((ip, 8091)))
            .await
            .unwrap();
        let deployment = "synthetic-deployment";
        let release = "synthetic-release";
        let env = "abcdef0123456789abcdef0123456789";
        let hash = format!("{:x}", Sha256::digest(deployment.as_bytes()));
        let host = format!("v3-{}-account-{env}", &hash[..12]);
        let binding = TransportBinding {
            account_id: 7,
            environment_id: env.into(),
            generation: 3,
            endpoint: format!("http://{host}:8091"),
            secret: "s".repeat(32),
            release_id: release.into(),
        };
        let ready = Arc::new(AtomicUsize::new(0));
        let barrier = Arc::new(Barrier::new(5));
        let received = Arc::new(Mutex::new(Vec::<StdInstant>::new()));
        let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
        encoder
            .write_all(b"data: {\"type\":\"message_stop\"}\n\n")
            .unwrap();
        let compressed = encoder.finish().unwrap();
        let app = Router::new()
            .route(
                "/internal/v3/transport/:id",
                get({
                    let binding = binding.clone();
                    let ready = ready.clone();
                    let barrier = barrier.clone();
                    move || {
                        let binding = binding.clone();
                        let ready = ready.clone();
                        let barrier = barrier.clone();
                        async move {
                            ready.fetch_add(1, Ordering::SeqCst);
                            barrier.wait().await;
                            Json(binding)
                        }
                    }
                }),
            )
            .route(
                "/internal/send",
                post({
                    let received = received.clone();
                    let compressed = compressed.clone();
                    move |headers: HeaderMap, body: Bytes| {
                        let received = received.clone();
                        let compressed = compressed.clone();
                        async move {
                            let meta: PreparedRequest = serde_json::from_slice(
                                &STANDARD.decode(headers[META_HEADER].as_bytes()).unwrap(),
                            )
                            .unwrap();
                            assert_eq!(meta.account_id, 7);
                            assert_eq!(meta.generation, 3);
                            assert_eq!(meta.target_url, "https://synthetic.invalid/v1/messages");
                            assert_eq!(body.as_ref(), b"{\"synthetic\":true}");
                            received.lock().unwrap().push(StdInstant::now());
                            (
                                [
                                    ("content-type", "text/event-stream"),
                                    ("content-encoding", "gzip"),
                                ],
                                compressed,
                            )
                                .into_response()
                        }
                    }
                }),
            );
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        let client = Client::builder()
            .no_proxy()
            .no_gzip()
            .no_brotli()
            .no_deflate()
            .resolve(&host, SocketAddr::from((ip, 8091)))
            .build()
            .unwrap();
        let base = format!("http://{ip}:8091");
        let mut jobs = Vec::new();
        for _ in 0..4 {
            let scheduler = scheduler.clone();
            let account = account.clone();
            let client = client.clone();
            let base = base.clone();
            jobs.push(tokio::spawn(async move {
                let request = scheduler.begin(1, None);
                request.selected(&account, None);
                request.phase(RequestPhase::Preparing);
                let transport = prepare_from_runtime(
                    &account,
                    client,
                    &base,
                    "synthetic-control",
                    deployment,
                    release,
                    Duration::from_secs(5),
                )
                .await
                .unwrap();
                let permit = request.admit(&account).await.unwrap();
                let prepared = PreparedRequest {
                    account_id: 7,
                    environment_id: String::new(),
                    generation: 0,
                    request_id: Uuid::new_v4().to_string(),
                    deadline_unix_ms: 0,
                    method: "POST".into(),
                    target_url: "https://synthetic.invalid/v1/messages".into(),
                    headers: vec![("Content-Type".into(), "application/json".into())],
                    preserve_header_casing: true,
                    tls_profile: TlsProfileId::default(),
                };
                permit.submitted();
                transport
                    .submit(prepared, b"{\"synthetic\":true}", Duration::from_secs(5))
                    .await
                    .unwrap()
                    .bytes()
                    .await
                    .unwrap()
            }));
        }
        timeout(Duration::from_secs(5), async {
            while ready.load(Ordering::SeqCst) < 4 {
                tokio::task::yield_now().await;
            }
        })
        .await
        .unwrap();
        assert!(scheduler.snapshot(7).events.is_empty());
        barrier.wait().await;
        for result in join_all(jobs).await {
            assert_eq!(result.unwrap().as_ref(), compressed.as_slice());
        }
        let observed = received.lock().unwrap();
        assert_eq!(observed.len(), 4);
        assert!(observed[3].duration_since(observed[0]) >= Duration::from_millis(400));
        let events = scheduler.snapshot(7).events;
        assert_eq!(events.len(), 4);
        assert!(
            events
                .windows(2)
                .all(|pair| pair[1].submitted_at_ms - pair[0].submitted_at_ms >= 195)
        );
        server.abort();
    }

    /// 源端能力缺失时拒绝生效的策略。关闭策略时向老 sender 交付原文并丢弃客户端冒充的私有头。
    #[tokio::test]
    async fn tui_body_policy_requires_ack_and_ignores_ingress_private_header() {
        use tokio::sync::mpsc;

        let (seen, mut requests) = mpsc::unbounded_channel();
        let app = Router::new().route(
            "/internal/tui-v2/prepare",
            post(move |headers: HeaderMap, body: Bytes| {
                let seen = seen.clone();
                async move {
                    seen.send((headers.get(TUI_BODY_POLICY).cloned(), body))
                        .unwrap();
                    (StatusCode::NO_CONTENT, [("x-v3-tui-handoff-kind", "new")])
                }
            }),
        );
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let body = Bytes::from_static(br#"{ "model":"m", "messages":[] }"#);
        let mut headers = HeaderMap::new();
        headers.insert(TUI_BODY_POLICY, HeaderValue::from_static("client"));
        let enabled = TuiBodyPolicy::new(
            MessageCacheControlRewrite::Sub2api,
            CacheControlTtlRewrite::OneHour,
            true,
        );
        for body_policy in [TuiBodyPolicy::default(), enabled] {
            let binding = TransportBinding {
                account_id: 3,
                environment_id: "env".into(),
                generation: 1,
                endpoint: endpoint.clone(),
                secret: "fixture".into(),
                release_id: "test".into(),
            };
            let sender = TuiReadySender {
                client: Client::builder().no_proxy().build().unwrap(),
                key: tui_sender_key(&binding, true),
                binding,
                idle: true,
                agent_summary: false,
                system_prompt_policy: false,
                direct_https: false,
                predecessors: Vec::new(),
                tui_oauth_profile: None,
            };
            let input = TuiMessagesInput {
                body: &body,
                headers: &headers,
                native_cc: false,
                signature_repair: None,
                agent_summary: false,
                oauth_file: false,
                system_prompt_policy: TuiSystemPromptPolicy::Append,
                body_policy,
            };
            let result = prepare_tui(
                sender,
                1,
                "test-session",
                input,
                Instant::now() + Duration::from_secs(2),
                false,
            )
            .await;
            let (option, original) = requests.recv().await.unwrap();
            assert_eq!(original, body);
            if body_policy == enabled {
                assert_eq!(
                    serde_json::from_slice::<TuiBodyPolicy>(option.unwrap().as_bytes()).unwrap(),
                    enabled
                );
                assert!(matches!(result, Err(AppError::ServiceUnavailable(_))));
            } else {
                assert!(option.is_none());
                let old = result.unwrap();
                let base = json!({"model":"m","messages":[{"role":"user","content":"x"}]});
                old.verify_input_policy(&base).unwrap();
                for (field, value) in [
                    ("metadata", json!({"private":123})),
                    ("context_management", json!({})),
                    ("mcp_servers", json!([])),
                    ("top_p", json!(0.9)),
                ] {
                    let mut changed = base.clone();
                    changed[field] = value;
                    assert!(matches!(
                        old.verify_input_policy(&changed),
                        Err(AppError::ServiceUnavailable(_))
                    ));
                }
                let mut extra = base.clone();
                extra["messages"][0]["custom"] = json!(true);
                assert!(old.verify_input_policy(&extra).is_err());
            }
        }
        server.abort();
    }

    /// 对照 V1 的协议头、连接级过滤、重复和版本错误。
    #[test]
    fn tui_model_header_policy_matches_v1_field_and_value_rules() {
        let mut headers = HeaderMap::new();
        headers.append("accept", HeaderValue::from_static("application/json"));
        headers.append("accept", HeaderValue::from_static("text/event-stream"));
        headers.append(
            "accept-language",
            HeaderValue::from_bytes(b"caf\xe9").unwrap(),
        );
        headers.append("cache-control", HeaderValue::from_static("no-cache"));
        headers.append("connection", HeaderValue::from_static("CACHE-Control"));
        headers.append("anthropic-version", HeaderValue::from_static("2023-06-01"));
        headers.append("anthropic-beta", HeaderValue::from_static("one"));
        headers.append("anthropic-beta", HeaderValue::from_static("two"));
        headers.append(
            "anthropic-dangerous-direct-browser-access",
            HeaderValue::from_static("false"),
        );
        headers.append(
            "x-claude-code-prev-tool-durations",
            HeaderValue::from_static("Read=12"),
        );
        headers.append("x-claude-code-compaction", HeaderValue::from_static("true"));
        headers.append(
            "x-claude-code-context-compacted",
            HeaderValue::from_static("true"),
        );
        headers.append("x-stainless-arch", HeaderValue::from_static("caller"));
        headers.append("authorization", HeaderValue::from_static("synthetic"));
        headers.append("anthropic-other", HeaderValue::from_static("ignored"));
        let selected = tui_model_headers(&headers, true).unwrap();
        assert_eq!(selected.len(), 8);
        assert_eq!(selected["accept"], "application/json, text/event-stream");
        assert_eq!(selected["anthropic-beta"], "one,two");
        assert_eq!(
            selected["anthropic-dangerous-direct-browser-access"],
            "false"
        );
        assert_eq!(
            tui_header_value(&selected["accept-language"])
                .unwrap()
                .as_bytes(),
            b"caf\xe9"
        );
        assert_eq!(tui_model_headers(&headers, false).unwrap().len(), 2);
        headers.append("anthropic-version", HeaderValue::from_static("2023-06-01"));
        assert!(matches!(
            tui_model_headers(&headers, true),
            Err(AppError::TuiInput {
                code: "duplicate_header",
                status: StatusCode::BAD_REQUEST,
                ..
            })
        ));
        assert!(tui_model_headers(&headers, false).is_ok());
        headers.insert("anthropic-version", HeaderValue::from_static("2024-01-01"));
        assert!(matches!(
            tui_model_headers(&headers, true),
            Err(AppError::TuiInput {
                code: "unsupported_parameter",
                status: StatusCode::UNPROCESSABLE_ENTITY,
                ..
            })
        ));
    }

    /// 无 billing 的原生输入只接收 V1 已认识的单个 UA；重复声明仍按普通 API 校验。
    #[test]
    fn tui_cli_format_requires_one_recognized_version_and_entry() {
        for (ua, expected) in [
            ("claude-cli/2.1.293 (external, cli)", Some("claude_code")),
            (
                "claude-cli/2.1.293 (external, sdk-cli, agent-sdk/0.2.1)",
                Some("claude_code"),
            ),
            (
                "claude-cli/2.1.280 (external, claude-vscode)",
                Some("claude_code_280"),
            ),
            ("claude-cli/2.1.293 (external, anything)", None),
        ] {
            let mut headers = HeaderMap::new();
            headers.append(USER_AGENT, ua.parse().unwrap());
            assert_eq!(tui_cli_format(&headers), expected);
            headers.append(USER_AGENT, ua.parse().unwrap());
            assert_eq!(tui_cli_format(&headers), None);
        }
    }

    /// 普通 API 自报头保持无权，官方形状的重复标识明确拒绝。
    #[test]
    fn tui_agent_hint_is_a_single_native_ingress_hint() {
        let mut headers = HeaderMap::new();
        let body = Bytes::new();
        headers.append("x-claude-code-agent-id", "agent-a".parse().unwrap());
        assert_eq!(
            tui_agent_hint(&TuiMessagesInput {
                body: &body,
                headers: &headers,
                native_cc: true,
                signature_repair: None,
                agent_summary: false,
                oauth_file: false,
                system_prompt_policy: TuiSystemPromptPolicy::Append,
                body_policy: TuiBodyPolicy::default(),
            })
            .unwrap(),
            Some("agent-a")
        );
        assert_eq!(
            tui_agent_hint(&TuiMessagesInput {
                body: &body,
                headers: &headers,
                native_cc: false,
                signature_repair: None,
                agent_summary: false,
                oauth_file: false,
                system_prompt_policy: TuiSystemPromptPolicy::Append,
                body_policy: TuiBodyPolicy::default(),
            })
            .unwrap(),
            None
        );
        headers.append("x-claude-code-agent-id", "agent-b".parse().unwrap());
        assert!(
            tui_agent_hint(&TuiMessagesInput {
                body: &body,
                headers: &headers,
                native_cc: true,
                signature_repair: None,
                agent_summary: false,
                oauth_file: false,
                system_prompt_policy: TuiSystemPromptPolicy::Append,
                body_policy: TuiBodyPolicy::default(),
            })
            .is_err()
        );
    }
}
