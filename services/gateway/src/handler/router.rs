use crate::handler::proxies;
use crate::handler::session_policy_blocks;
use crate::model::proxy::ProxyConnection;
use crate::service::account::{AccountCapacityInfo, AccountQueue};
use crate::service::oauth_flow::GenerateAuthUrlRequest;
use crate::service::proxy::ProxyService;
use crate::service::runtime_lease::RuntimeLease;
use crate::service::session_policy_block::SessionPolicyBlockConfig;
use crate::store::settings_store::{
    DEFAULT_SESSION_POLICY_BLOCK_DURATION_MINUTES, DEFAULT_SESSION_POLICY_BLOCK_ENABLED,
};
use axum::extract::{Path, Query, Request, State};
use axum::http::{HeaderMap, HeaderValue, StatusCode};
use axum::middleware::{self, Next};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post, put};
use axum::{Json, Router};
use chrono::{TimeZone, Utc};
use rust_embed::Embed;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::HashMap;
use std::sync::Arc;
use subtle::ConstantTimeEq;
use tracing::warn;
use uuid::Uuid;

use crate::config::Config;
use crate::error::AppError;
use crate::middleware::auth::{admin_auth, extract_key};
use crate::model::account::{
    Account, AccountAuthType, AccountStatus, CanonicalEnvData, CanonicalProcessData,
    CanonicalPromptEnvData, CliProcessImport, DEFAULT_ALLOW_1M_MODELS,
    DEFAULT_UPSTREAM_SESSION_POOL_SIZE, DEFAULT_UPSTREAM_SESSION_REFRESH_POLICY,
    DEFAULT_UPSTREAM_SESSION_TTL_MINUTES, OAuthCredentialImport,
};
use crate::model::api_token::{self, ApiToken};
use crate::model::credential_ownership::CredentialOwnershipInput;
use crate::model::request_diagnostics::{
    AgyRequestUsage, DiagnosticDetail, DiagnosticPage, DiagnosticQuery, RequestLogMode,
};
use crate::service::access_policy::{
    DEFAULT_ALLOWED_CLAUDE_CODE_VERSIONS, DEFAULT_ALLOWED_USER_AGENTS,
    DEFAULT_BLOCKED_CLAUDE_CODE_VERSIONS, validate_blocked_claude_code_versions,
    validate_claude_code_versions, validate_user_agent_patterns,
};
use crate::service::account::AccountService;
use crate::service::account_work::{AccountWorkSnapshot, AccountWorkUpdate};
use crate::service::gateway::{
    AutoModeClassifierMode, BootstrapModelOptionsMode, CliBgStatusClassifierMode, GatewayService,
    parse_bootstrap_additional_model_options,
};
use crate::service::gemini::{self, GeminiService};
use crate::service::native_capture;
use crate::service::native_contract::validate_idle_timeout;
use crate::service::oauth::TokenTester;
use crate::service::oauth_flow::OAuthFlowService;
use crate::service::rewriter::{
    CacheControlTtlRewrite, ClaudeCodeContextSanitizerMode, MessageCacheControlRewrite,
};
use crate::service::runtime_bridge;
use crate::service::system_update;
use crate::service::telemetry::TelemetryService;
use crate::service::v3_scheduling::{PhaseCounts, SchedulingConfig, now_ms};
use crate::service::version_profile::{
    ClaudeCodeProfileSelectionMode, all_profiles, profile_for_key,
};
use crate::store::prime_log_store::PrimeLogStore;
use crate::store::settings_store::{
    DEFAULT_BOOTSTRAP_ADDITIONAL_MODEL_OPTIONS, DEFAULT_BOOTSTRAP_MODEL_OPTIONS_MODE,
    DEFAULT_CACHE_CONTROL_TTL_REWRITE, DEFAULT_CLAUDE_CODE_CONTEXT_SANITIZER_MODE,
    DEFAULT_CLAUDE_CODE_PROFILE_SELECTION_MODE_SETTING,
    DEFAULT_CLAUDE_CODE_VERSION_PROFILE_SETTING, DEFAULT_FABLE_STICKY_QUOTA_FALLBACK_ENABLED,
    DEFAULT_FABLE_WEEKLY_USAGE_LIMIT_PERCENT, DEFAULT_INTERCEPT_ASSISTANT_PREFILL_ENABLED,
    DEFAULT_INTERCEPT_ASSISTANT_PREFILL_MODELS, DEFAULT_INTERCEPT_AUTO_MODE_CLASSIFIER_STAGE1_MODE,
    DEFAULT_INTERCEPT_AUTO_MODE_CLASSIFIER_STAGE2_MODE,
    DEFAULT_INTERCEPT_CLI_BG_STATUS_CLASSIFIER_IDENTITY_INJECTION_ENABLED,
    DEFAULT_INTERCEPT_CLI_BG_STATUS_CLASSIFIER_MODE,
    DEFAULT_INTERCEPT_CLI_BG_STATUS_CLASSIFIER_MODELS,
    DEFAULT_INTERCEPT_WARMUP_HAIKU_PROBE_ENABLED, DEFAULT_INTERCEPT_WARMUP_SUGGESTION_ENABLED,
    DEFAULT_INTERCEPT_WARMUP_TITLE_ENABLED, DEFAULT_LOG_429_REQUEST_BODY_LIMIT,
    DEFAULT_LOG_429_REQUEST_ENABLED, DEFAULT_LOG_NON_STREAM_REQUEST_ENABLED,
    DEFAULT_MESSAGE_BODY_ORDER_FINGERPRINT_ENABLED, DEFAULT_MESSAGE_CACHE_CONTROL_REWRITE,
    DEFAULT_MESSAGE_TOP_FIELD_FILTER_ENABLED, DEFAULT_NON_STREAM_PROBE_CACHE_ENABLED,
    DEFAULT_PROXY_CLIENT_POOL_ENABLED, DEFAULT_REWRITE_DISABLED_THINKING_ENABLED,
    DEFAULT_REWRITE_DISABLED_THINKING_MODELS, DEFAULT_SESSION_HELLO_PROBE_ENABLED,
    DEFAULT_SESSION_HELLO_PROBE_FAILURE_COOLDOWN_SECS, DEFAULT_SESSION_HELLO_PROBE_STRICT,
    DEFAULT_SESSION_HELLO_PROBE_SUCCESS_TTL_SECS, DEFAULT_SESSION_HELLO_PROBE_TIMEOUT_SECS,
    DEFAULT_STREAM_KEEPALIVE_ENABLED, DEFAULT_STREAM_KEEPALIVE_INTERVAL_SECS,
    DEFAULT_STREAM_UPSTREAM_IDLE_TIMEOUT_SECS, SettingsStore,
    normalize_message_top_field_filter_enabled,
};
use crate::store::settings_store::{OBSOLETE_SCHEDULING_KEYS, V3_SCHEDULING_DEFAULTS};
use crate::store::token_store::TokenStore;

const OBSOLETE_SETTINGS_KEYS: &[&str] = &[
    "intercept_warmup_non_stream_aux_enabled",
    "intercept_warmup_non_stream_aux_mode",
];

#[derive(Clone)]
pub struct AppState {
    pub gemini_svc: Arc<GeminiService>,
    pub gateway_svc: Arc<GatewayService>,
    pub account_svc: Arc<AccountService>,
    pub token_tester: Arc<TokenTester>,
    pub token_store: Arc<TokenStore>,
    pub settings_store: Arc<SettingsStore>,
    pub prime_log_store: Arc<PrimeLogStore>,
    pub oauth_flow_svc: Arc<OAuthFlowService>,
    pub telemetry_svc: Arc<TelemetryService>,
    pub proxy_svc: Arc<ProxyService>,
    pub admin_password: String,
}

pub fn build_router(
    cfg: &Config,
    gateway_svc: Arc<GatewayService>,
    account_svc: Arc<AccountService>,
    token_tester: Arc<TokenTester>,
    token_store: Arc<TokenStore>,
    settings_store: Arc<SettingsStore>,
    prime_log_store: Arc<PrimeLogStore>,
    oauth_flow_svc: Arc<OAuthFlowService>,
    telemetry_svc: Arc<TelemetryService>,
) -> Router {
    let proxy_svc = Arc::new(ProxyService::new(settings_store.database_pool()));
    let state = AppState {
        gemini_svc: Arc::new(GeminiService::default()),
        proxy_svc,
        gateway_svc,
        account_svc,
        token_tester,
        token_store,
        settings_store,
        prime_log_store,
        oauth_flow_svc,
        telemetry_svc,
        admin_password: cfg.admin.password.clone(),
    };

    let admin_password = state.admin_password.clone();
    super::proxy_sync::start(state.clone());

    // 前端页面（显式注册 SPA 路由）
    let mut frontend_routes = Router::new().route("/", get(spa_handler));
    for path in [
        "/login",
        "/tokens",
        "/requests",
        "/session-blocks",
        "/tasks",
        "/settings",
        "/proxies",
        "/updates",
        "/environments",
        "/nodes",
    ] {
        // 只为实际页面登记尾斜杠别名，API与未知路径继续沿原网关鉴权。
        frontend_routes = frontend_routes
            .route(path, get(spa_handler))
            .route(&format!("{path}/"), get(spa_handler));
    }

    // 前端静态资源
    let asset_routes = Router::new()
        .route("/assets/*rest", get(asset_handler))
        .route("/favicon.svg", get(asset_handler));

    // 管理 API（密码认证，完整路径注册）
    let admin_routes = Router::new()
        .route("/admin/proxies", get(proxies::list).post(proxies::create))
        .route("/admin/proxies/import", post(proxies::import))
        .route("/admin/proxies/identify", post(proxies::identify))
        .route(
            "/admin/proxies/:id",
            put(proxies::update).delete(proxies::delete),
        )
        .route("/admin/proxies/:id/probe", post(proxies::probe))
        .route(
            "/admin/runtime/system-update/status",
            get(system_update_status),
        )
        .route(
            "/admin/runtime/system-update/ack",
            post(system_update_status),
        )
        .route("/admin/accounts", get(list_accounts).post(create_account))
        .route(
            "/admin/accounts/:id",
            get(get_account).put(update_account).delete(delete_account),
        )
        .route("/admin/accounts/:id/test", post(test_account))
        .route("/admin/accounts/:id/usage", post(refresh_usage))
        .route("/admin/accounts/:id/scheduling", get(account_scheduling))
        .route(
            "/admin/accounts/:id/native-preparation",
            get(native_preparation_status).post(request_native_preparation),
        )
        .route(
            "/admin/native-preparations",
            get(native_preparation_snapshots),
        )
        .route(
            "/admin/accounts/:id/scheduling/sessions",
            get(account_scheduling_sessions),
        )
        .route(
            "/admin/accounts/:id/cli-process/import",
            post(import_cli_process),
        )
        .route(
            "/admin/runtime/accounts/:id/lease",
            get(runtime_lease_status).post(runtime_lease_update),
        )
        .route(
            "/admin/accounts/:id/work-control",
            get(get_account_work).put(update_account_work),
        )
        .route(
            "/admin/runtime/accounts/:id/config",
            get(runtime_account_config),
        )
        .route(
            "/admin/runtime/accounts/:id/proxy-selection",
            post(commit_task_proxy_selection),
        )
        .route(
            "/admin/runtime/task-proxy-operations/:operation/claim",
            post(claim_task_proxy_selection),
        )
        .route(
            "/admin/accounts/:id/oauth-credentials/resolve",
            post(resolve_oauth_credentials),
        )
        .route(
            "/admin/runtime/credential-capabilities",
            get(credential_capabilities),
        )
        .route(
            "/admin/accounts/:id/oauth-ownership",
            get(credential_ownership).post(credential_handoff),
        )
        .route(
            "/admin/accounts/:id/oauth-credentials/import",
            post(import_oauth_credentials),
        )
        .route(
            "/admin/accounts/:id/oauth-credentials/import/:operation_id",
            get(oauth_import_status),
        )
        .route("/admin/tokens", get(list_tokens).post(create_token))
        .route(
            "/admin/tokens/:id",
            put(update_token).delete(delete_token_handler),
        )
        .route("/admin/dashboard", get(get_dashboard))
        .route(
            "/admin/runtime/session",
            post(runtime_bridge::grant_session),
        )
        .route("/runtime/logout", post(runtime_bridge::revoke_session))
        .route(
            "/admin/oauth/generate-auth-url",
            post(oauth_generate_auth_url),
        )
        .route(
            "/admin/oauth/generate-setup-token-url",
            post(oauth_generate_setup_token_url),
        )
        .route("/admin/oauth/exchange-code", post(oauth_exchange_code))
        .route(
            "/admin/oauth/:session_id/cancel",
            post(oauth_cancel_session),
        )
        .route(
            "/admin/accounts/:id/agy-credentials",
            get(agy_credential_status),
        )
        .route(
            "/admin/accounts/:id/agy-credentials/recover",
            post(agy_credential_recover),
        )
        .route(
            "/admin/oauth/exchange-setup-token-code",
            post(oauth_exchange_setup_token_code),
        )
        .route("/admin/settings", get(get_settings).put(update_settings))
        .route(
            "/admin/session-policy-blocks",
            get(session_policy_blocks::list),
        )
        .route(
            "/admin/session-policy-blocks/:id/release",
            post(session_policy_blocks::release),
        )
        .route("/admin/prime-logs", get(get_prime_logs))
        .route("/admin/request-diagnostics", get(list_request_diagnostics))
        .route(
            "/admin/request-diagnostics/:request_id/captures/:attempt_id",
            get(request_native_capture),
        )
        .route(
            "/admin/request-diagnostics/:request_id",
            get(request_diagnostic_detail),
        )
        .layer(middleware::from_fn(move |req, next: Next| {
            let pwd = admin_password.clone();
            admin_auth(pwd, req, next)
        }))
        .with_state(state.clone());

    // 组合路由：前端 + 管理 API + 其余全部透传网关
    Router::new()
        .merge(frontend_routes)
        .merge(asset_routes)
        .merge(admin_routes)
        .merge(
            if std::env::var("V3_RUNTIME_URL")
                .unwrap_or_default()
                .is_empty()
            {
                Router::new()
            } else {
                runtime_bridge::routes()
            },
        )
        .route("/api/hello", get(hello_get).head(hello_head))
        .route("/v1beta/models", get(gemini::models))
        .route("/v1beta/models/:action", post(gemini::generate))
        .route("/v1/messages/count_tokens", post(gateway_count_tokens))
        .fallback(gateway_fallback)
        .layer(middleware::from_fn(system_update::middleware))
        .with_state(state)
}

// --- Handlers ---

/// 读取双端维护接管证明；管理员鉴权沿用管理路由。
/// @return 精确 epoch 和完整响应生命周期内的进程活动数。
async fn system_update_status() -> Result<Json<Value>, AppError> {
    Ok(Json(system_update::snapshot()?))
}

const CLAUDE_CODE_HELLO_BODY: &[u8] = br#"{"message": "hello"}"#;

/// 返回 Claude Code 连通性预检的 GET 响应。
async fn hello_get() -> Response {
    hello_response(true)
}

/// 返回 Claude Code 连通性预检的 HEAD 响应。
async fn hello_head() -> Response {
    hello_response(false)
}

fn hello_response(include_body: bool) -> Response {
    Response::builder()
        .status(StatusCode::OK)
        .header("content-type", "application/json; charset=utf-8")
        .header("content-length", CLAUDE_CODE_HELLO_BODY.len().to_string())
        .body(axum::body::Body::from(if include_body {
            CLAUDE_CODE_HELLO_BODY
        } else {
            &[]
        }))
        .expect("固定 hello 响应必须可构造")
}

/// 网关透传 fallback：鉴权 + 代理上游
async fn gateway_fallback(State(state): State<AppState>, req: Request) -> Response {
    let api_token = match authenticate_gateway_token(&state, extract_key(&req)).await {
        Ok(t) => t,
        Err(resp) => return resp,
    };
    state
        .gateway_svc
        .handle_request(req, Some(&api_token))
        .await
}

/// count_tokens 专用入口：鉴权 + 代理 Anthropic token counting API。
async fn gateway_count_tokens(State(state): State<AppState>, req: Request) -> Response {
    let api_token = match authenticate_gateway_token(&state, extract_key(&req)).await {
        Ok(t) => t,
        Err(resp) => return resp,
    };
    state
        .gateway_svc
        .handle_count_tokens_request(req, Some(&api_token))
        .await
}

/// 校验网关 API token。
async fn authenticate_gateway_token(state: &AppState, key: String) -> Result<ApiToken, Response> {
    if key.is_empty() {
        return Err(err_json(StatusCode::UNAUTHORIZED, "missing api key"));
    }
    match state.token_store.get_by_token(&key).await {
        Ok(Some(t)) => Ok(t),
        Ok(None) => Err(err_json(StatusCode::UNAUTHORIZED, "invalid api key")),
        Err(_) => Err(err_json(
            StatusCode::INTERNAL_SERVER_ERROR,
            "authentication failed",
        )),
    }
}

/// 统一 JSON 错误响应
fn err_json(status: StatusCode, msg: &str) -> Response {
    (status, Json(serde_json::json!({"error": msg}))).into_response()
}

// --- Account Handlers ---

#[derive(Deserialize)]
struct PageQuery {
    page: Option<i64>,
    page_size: Option<i64>,
}

/// 管理账号筛选参数，旧分页请求仍可省略新增字段。
#[derive(Deserialize)]
struct AccountListQuery {
    platform: Option<String>,
    page: Option<i64>,
    page_size: Option<i64>,
    q: Option<String>,
    status: Option<String>,
}

/// 分页返回账号和网关当前生效的画像配置。
///
/// @param state 管理应用状态。
/// @param query 分页参数。
/// @return 账号分页与只读画像配置。
async fn list_accounts(
    State(state): State<AppState>,
    Query(query): Query<AccountListQuery>,
) -> Result<Json<serde_json::Value>, AppError> {
    let page = query.page.unwrap_or(1).max(1);
    let page_size = query.page_size.unwrap_or(12).clamp(1, 100);
    let search = query.q.as_deref().unwrap_or("").trim();
    let status = query.status.as_deref().unwrap_or("");
    let platform = query.platform.as_deref().unwrap_or("claude_code");
    if !["claude_code", "antigravity", "all"].contains(&platform) {
        return Err(AppError::BadRequest("账号平台筛选无效".into()));
    }
    if search.chars().count() > 256 || !["", "active", "error", "disabled"].contains(&status) {
        return Err(AppError::BadRequest("账号搜索或状态参数无效".into()));
    }
    let (accounts, total) = state
        .account_svc
        .list_accounts_filtered(page, page_size, search, status, platform)
        .await?;
    let total_pages = (total + page_size - 1) / page_size;
    let profile_config = state.gateway_svc.profile_selection_config().await;
    let request_usage = match state.gateway_svc.request_usage(&accounts).await {
        Ok(stats) => Some(stats),
        Err(error) => {
            warn!("账号用量统计读取失败: {}", error);
            None
        }
    };
    let agy_ids = accounts
        .iter()
        .filter(|account| account.is_antigravity())
        .map(|account| account.id)
        .collect::<Vec<_>>();
    let agy_usage = agy_account_usage(&state, &agy_ids).await;
    let profile_selection_mode = match profile_config.mode {
        ClaudeCodeProfileSelectionMode::ClientVersion => "client_version",
        ClaudeCodeProfileSelectionMode::Account => "account",
    };

    let binding_counts = if let Some(scheduler) = state.account_svc.scheduler() {
        scheduler
            .store
            .counts(&accounts.iter().map(|a| a.id).collect::<Vec<_>>(), now_ms())
            .await
            .ok()
    } else {
        None
    };

    let credential_ownerships = state.account_svc.credential_ownerships().await?;
    let connections = accounts
        .iter()
        .filter_map(|account| {
            ProxyConnection::parse(&account.proxy_url)
                .ok()
                .map(|value| value.private_url)
        })
        .collect::<Vec<_>>();
    let proxy_records = state.proxy_svc.store.matching(&connections).await?;

    // 为每个账号附加遥测会话过期时间 + 调度评分信息
    let mut data: Vec<serde_json::Value> = Vec::with_capacity(accounts.len());
    for a in &accounts {
        let mut obj = serde_json::to_value(a).unwrap_or_default();
        obj["work_control"] =
            serde_json::to_value(state.account_svc.work_controls.snapshot(a.id).await?)
                .map_err(|_| AppError::Internal("账号工作状态编码失败".into()))?;
        if let Ok(connection) = ProxyConnection::parse(&a.proxy_url) {
            if let Some(proxy) = proxy_records
                .iter()
                .find(|proxy| proxy.connection.private_url == connection.private_url)
            {
                obj["proxy_id"] = json!(proxy.id);
                obj["proxy_name"] = json!(proxy.name);
            }
        }

        if !a.is_claude_code() {
            if a.is_antigravity() {
                obj["credential_state"] = state.account_svc.agy_state(a.id).await?;
                obj["agy_request_usage"] = json!(agy_usage.get(&a.id));
                append_account_live_metrics(&state.account_svc, a, &mut obj).await;
            }
            data.push(obj);
            continue;
        }

        obj["credential_ownership"] = credential_ownerships
            .get(&a.id)
            .map(|value| json!({"owner":value.owner,"phase":value.phase,"protocol":value.protocol}))
            .unwrap_or(Value::Null);
        obj["request_usage"] = request_usage
            .as_ref()
            .and_then(|stats| stats.get(&a.id))
            .map(|stats| serde_json::to_value(stats).unwrap_or_default())
            .unwrap_or_default();
        if let Some(expires) = state.telemetry_svc.get_session_expires_at(a.id).await {
            obj["telemetry_expires_at"] = serde_json::json!(expires.to_rfc3339());
        }
        // 附加实时调度评分和并发/排队状态
        let si = append_account_live_metrics(&state.account_svc, a, &mut obj).await;
        if state.account_svc.scheduler().is_some() {
            match binding_counts.as_ref() {
                Some(counts) => match state
                    .account_svc
                    .v3_summary(a, &si, counts.get(&a.id).copied().unwrap_or(0))
                    .await
                {
                    Ok(summary) => {
                        obj["v3_scheduling"] = serde_json::to_value(summary).unwrap_or_default()
                    }
                    Err(_) => obj["v3_scheduling_error"] = serde_json::json!("调度观测不可用"),
                },
                None => obj["v3_scheduling_error"] = serde_json::json!("调度观测不可用"),
            }
        }
        match state.account_svc.get_upstream_session_pool_status(a).await {
            Ok(pool) => {
                obj["upstream_session_pool_active_count"] = serde_json::json!(pool.active_count);
                obj["upstream_session_pool_capacity"] =
                    serde_json::json!(a.upstream_session_pool_size.max(0));
                obj["upstream_session_pool_oldest_last_seen_ms"] =
                    serde_json::json!(pool.oldest_last_seen_ms);
                obj["upstream_session_pool_newest_last_seen_ms"] =
                    serde_json::json!(pool.newest_last_seen_ms);
            }
            Err(e) => {
                warn!(
                    "upstream session pool status read failed: account={} error={}",
                    a.id, e
                );
                obj["upstream_session_pool_active_count"] = serde_json::json!(0);
                obj["upstream_session_pool_capacity"] =
                    serde_json::json!(a.upstream_session_pool_size.max(0));
            }
        }
        data.push(obj);
    }

    Ok(Json(serde_json::json!({
        "account_counts": state.account_svc.platform_counts(platform).await?,
        "data": data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "claude_code_profile_selection_mode": profile_selection_mode,
        "claude_code_version_profile": profile_config.default_profile.key,
    })))
}

/// 管理端创建账号载荷，省略账号用量控制线时默认关闭。
#[derive(Deserialize)]
struct CreateAccountRequest {
    platform: Option<String>,
    agy_system_prompt_homoglyph_enabled: Option<bool>,
    agy_gif_frames_enabled: Option<bool>,
    cli_identity: Option<CliIdentityImport>,
    credential_ownership: Option<CredentialOwnershipInput>,
    name: Option<String>,
    email: String,
    token: Option<String>,
    setup_token: Option<String>,
    auth_type: Option<String>,
    access_token: Option<String>,
    refresh_token: Option<String>,
    expires_at: Option<i64>,
    proxy_url: Option<String>,
    proxy_id: Option<String>,
    proxy_revision: Option<String>,
    billing_mode: Option<String>,
    request_backend: Option<String>,
    account_uuid: Option<String>,
    organization_uuid: Option<String>,
    subscription_type: Option<String>,
    rate_limit_tier: Option<String>,
    concurrency: Option<i32>,
    priority: Option<i32>,
    rpm_limit: Option<i32>,
    #[serde(default)]
    five_hour_usage_limit_percent: i32,
    #[serde(default)]
    seven_day_usage_limit_percent: i32,
    auto_telemetry: Option<bool>,
    auto_poll_usage: Option<bool>,
    allow_1m_models: Option<String>,
    allow_fast_mode: Option<bool>,
    upstream_session_pool_enabled: Option<bool>,
    upstream_session_pool_size: Option<i32>,
    upstream_session_ttl_minutes: Option<i32>,
    upstream_session_refresh_policy: Option<String>,
}

/// 受控 CLI 导入，只接受已经观测到的设备字段和实际基础环境。
#[derive(Deserialize)]
struct CliIdentityImport {
    device_id: String,
    environment_id: String,
    source: String,
    canonical_env: CanonicalEnvData,
    canonical_prompt: CanonicalPromptEnvData,
    canonical_process: Option<CanonicalProcessData>,
}

impl CliIdentityImport {
    /// 核对请求观察或已通过官方 CLI 实测的本地字段来源。
    /// @return 来源与版本相符时为 true；未知映射保持拒绝。
    fn has_confirmed_source(&self) -> bool {
        self.source == "cli:/v1/messages:metadata.user_id.device_id"
            || (self.source == "cli:2.1.293:config.userID"
                && self.canonical_env.version == "2.1.293"
                && self.canonical_env.version_base == "2.1.293")
    }
}

const DEFAULT_OAUTH_CREDENTIAL_VALIDITY_SECONDS: i64 = 2400;

/// 凭据导入只允许可信 v3 服务调用，管理密码本身不能替代服务证明。
/// @param headers 服务请求头。
/// @return 服务证明有效时返回空值。
fn require_v3_credential_service(headers: &HeaderMap) -> Result<(), AppError> {
    let expected = std::env::var("V3_INTERNAL_TOKEN").unwrap_or_default();
    let supplied = headers
        .get("x-v3-service-token")
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default();
    if std::env::var("V3_RUNTIME_URL")
        .unwrap_or_default()
        .is_empty()
        || expected.len() < 32
        || !bool::from(expected.as_bytes().ct_eq(supplied.as_bytes()))
    {
        return Err(AppError::Unauthorized);
    }
    Ok(())
}

/// 将真实 CLI 重授权凭据提交到原关联账号。
/// @param state 应用服务。
/// @param id 原账号 ID。
/// @param headers 可信服务证明。
/// @param input 身份、新凭据与登录租约。
/// @return 最终持久化的最小凭据快照。
async fn import_oauth_credentials(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    headers: HeaderMap,
    Json(input): Json<OAuthCredentialImport>,
) -> Result<Json<serde_json::Value>, AppError> {
    require_v3_credential_service(&headers)?;
    let snapshot = state
        .account_svc
        .import_oauth_credentials(id, &input)
        .await?;
    Ok(Json(
        serde_json::json!({"imported": true, "account_id": snapshot.account_id,
        "operation_id": input.operation_id, "access_token": snapshot.access_token,
        "refresh_token": snapshot.refresh_token, "expires_at": snapshot.expires_at}),
    ))
}

/// 查询持久提交回执，不将网络错误误当作未提交。
/// @param state 应用服务。
/// @param id 账号 ID。
/// @param operation_id 唯一操作 ID。
/// @param headers 可信服务证明。
/// @return 未提交结果或当前权威凭据快照。
async fn oauth_import_status(
    State(state): State<AppState>,
    Path((id, operation_id)): Path<(i64, String)>,
    headers: HeaderMap,
) -> Result<Json<serde_json::Value>, AppError> {
    require_v3_credential_service(&headers)?;
    let snapshot = state
        .account_svc
        .oauth_import_status(id, &operation_id)
        .await?;
    Ok(Json(match snapshot {
        Some(value) => serde_json::json!({"imported": true, "account_id": value.account_id,
            "operation_id": operation_id, "access_token": value.access_token,
            "refresh_token": value.refresh_token, "expires_at": value.expires_at}),
        None => {
            serde_json::json!({"imported": false, "account_id": id, "operation_id": operation_id})
        }
    }))
}

/// 受信任调度器对单账号占用租约的操作。
#[derive(Deserialize)]
struct RuntimeLeaseInput {
    operation: String,
    owner: String,
    generation: Option<String>,
}

/// 查询账号门禁，便于在服务重启后对账。
/// @param state 管理服务状态。
/// @param id 当前账号 ID。
/// @return 持久租约和活动请求数。
async fn runtime_lease_status(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, AppError> {
    let account = state.account_svc.get_account(id).await?;
    let queue = state
        .account_svc
        .get_or_create_queue(id, account.concurrency)
        .await;
    let mut snapshot = queue.runtime_gate.snapshot();
    snapshot["waiting"] = serde_json::json!(queue.waiting_count());
    Ok(Json(snapshot))
}

/// 提供账号配置的唯一来源，避免调度器使用已经漂移的代理。
/// @param id 绑定账号 ID。
/// @return 不包含 OAuth 凭据的配置。
async fn runtime_account_config(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, AppError> {
    let account = state.account_svc.get_account(id).await?;
    if account.is_antigravity() {
        return Ok(Json(
            json!({"account_id":account.id,"platform":account.platform,"proxy_url":account.proxy_url,
            "auth_type":account.auth_type,"status":account.status,"email":account.email,"concurrency":account.concurrency,
            "request_backend":"agy159","credential_state":state.account_svc.agy_state(id).await?}),
        ));
    }
    Ok(Json(
        serde_json::json!({"account_id": account.id, "proxy_url": account.proxy_url,
        "auth_type": account.auth_type, "status": account.status, "email": account.email,
        "request_backend": account.request_backend, "concurrency": account.concurrency,
        "account_uuid": account.account_uuid, "organization_uuid": account.organization_uuid,
        "credential_ownership_protocol":1,
        "credential_ownership":state.account_svc.credential_ownership(id).await?}),
    ))
}

/// 编排持有任务身份锁，外层管理桥持有目录锁的内部选线回调。
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TaskProxyCommit {
    operation_id: String,
    expected_connection: String,
    connection: String,
}

/// 运行时在登记活动后请求领取固定任务的选择。字段只用于内部核对。
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct TaskProxyClaim {
    account_id: i64,
    gateway_account_id: Option<i64>,
    selection_revision: String,
    connection: String,
}

/// 拒绝超时后才到达或重复领取的请求。@param state 服务。@param operation 票据。@param headers 内部证明。@param input 冻结选择。@return 领取结果。
async fn claim_task_proxy_selection(
    State(state): State<AppState>,
    Path(operation): Path<String>,
    headers: HeaderMap,
    Json(input): Json<TaskProxyClaim>,
) -> Result<Json<Value>, AppError> {
    require_v3_credential_service(&headers)?;
    state.proxy_svc.task_selections.claim(
        &operation,
        input.account_id,
        input.gateway_account_id,
        &input.selection_revision,
        &input.connection,
    )?;
    Ok(Json(json!({"claimed":true})))
}

/// 在原配置许可内按原连接比较更新，禁止将账号凭据快照整行写回。
/// @param state 应用状态。@param id 网关身份。@param headers 内部服务证明。@param input 原连接和目标。
/// @return 明确的单字段写入回执。
async fn commit_task_proxy_selection(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    headers: HeaderMap,
    Json(input): Json<TaskProxyCommit>,
) -> Result<Json<Value>, AppError> {
    require_v3_credential_service(&headers)?;
    let _ticket = state.proxy_svc.task_selections.gateway_commit(
        &input.operation_id,
        id,
        &input.connection,
    )?;
    if !input.connection.is_empty() {
        ProxyConnection::parse(&input.connection)?;
    }
    let account = state.account_svc.get_account(id).await?;
    if !account.is_claude_code() {
        return Err(AppError::BadRequest(
            "此运行接口仅适用于 Claude Code".into(),
        ));
    }
    if account.proxy_url != input.expected_connection {
        return Err(AppError::BadRequest("账号代理已变化，请重新读取".into()));
    }
    if account.proxy_url == input.connection {
        return Ok(Json(json!({"ok":true})));
    }
    if state
        .account_svc
        .credential_ownership(id)
        .await?
        .is_some_and(|ownership| !ownership.gateway_ready())
    {
        return Err(AppError::BadRequest(
            "账号凭据正在维护，请完成后再切换代理".into(),
        ));
    }
    let _permit = config_permit(&state, &account, true).await?;
    let current = state.account_svc.get_account(id).await?;
    if current.proxy_url != input.expected_connection {
        return Err(AppError::BadRequest("账号代理已变化，请重新读取".into()));
    }
    if current.proxy_url != input.connection
        && !state
            .account_svc
            .synchronize_proxy_connection(&current, &input.connection)
            .await?
    {
        return Err(AppError::BadRequest("账号代理保存冲突，请重新读取".into()));
    }
    Ok(Json(json!({"ok":true})))
}

/// 管理共享 CLI 租约与排他维护；只有维护原子关闭 API 入场。
/// @param state 管理服务状态。
/// @param id 当前账号 ID。
/// @param input owner、代次和操作。
/// @return 当前租约及活动数；不同 owner/旧代次拒绝。
async fn runtime_lease_update(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(input): Json<RuntimeLeaseInput>,
) -> Result<Json<serde_json::Value>, AppError> {
    if std::env::var("V3_RUNTIME_URL")
        .unwrap_or_default()
        .is_empty()
    {
        return Err(AppError::BadRequest("v3 runtime is not configured".into()));
    }
    let _update_activity = if matches!(
        input.operation.as_str(),
        "prepare" | "prepare-cli" | "prepare-cli-shared"
    ) {
        Some(system_update::cli_admission(id, &input.owner).await?)
    } else {
        None
    };
    let account = state.account_svc.get_account(id).await?;
    if account.is_antigravity()
        && (!input.owner.starts_with("maintenance:")
            || !matches!(
                input.operation.as_str(),
                "prepare" | "claim" | "heartbeat" | "release"
            ))
    {
        return Err(AppError::BadRequest("AGY账号仅开放环境维护许可".into()));
    }
    if matches!(
        input.operation.as_str(),
        "prepare" | "prepare-cli" | "prepare-cli-shared" | "claim"
    ) {
        if let Some(ownership) = state.account_svc.credential_ownership(id).await? {
            let controlled = input.owner.starts_with("binding:")
                || (ownership.phase == "reauth"
                    && ownership.lease_owner.as_deref() == Some(input.owner.as_str()));
            if !ownership.gateway_ready() && !controlled {
                return Err(AppError::ServiceUnavailable(
                    "账号凭据正在交接或需要核对，不能启动普通 CLI 作业".into(),
                ));
            }
        }
    }
    let queue = state
        .account_svc
        .get_or_create_queue(id, account.concurrency)
        .await;
    if input.operation == "prepare" {
        queue.runtime_gate.prepare(&input.owner)?;
    } else if input.operation == "prepare-cli" {
        queue.runtime_gate.prepare_cli(&input.owner)?;
    } else if input.operation == "prepare-cli-shared" {
        queue.runtime_gate.prepare_shared_cli(&input.owner)?;
    } else {
        queue.runtime_gate.update(
            &input.owner,
            input.generation.as_deref().unwrap_or_default(),
            &input.operation,
        )?;
    }
    let mut snapshot = queue.runtime_gate.snapshot();
    snapshot["waiting"] = serde_json::json!(queue.waiting_count());
    Ok(Json(snapshot))
}
const MIN_OAUTH_CREDENTIAL_VALIDITY_SECONDS: i64 = 60;
const MAX_OAUTH_CREDENTIAL_VALIDITY_SECONDS: i64 = 7200;

/// 管理端解析 OAuth 凭据的请求体。
#[derive(Deserialize)]
struct ResolveOAuthCredentialsRequest {
    min_validity_seconds: Option<i64>,
    force_refresh: Option<bool>,
}

/// 管理端返回给受信任消费者的最小 OAuth 凭据快照。
#[derive(Serialize)]
struct ResolveOAuthCredentialsResponse {
    account_id: i64,
    access_token: String,
    refresh_token: String,
    expires_at: i64,
}

fn normalize_oauth_credential_validity_seconds(value: Option<i64>) -> Result<i64, AppError> {
    let value = value.unwrap_or(DEFAULT_OAUTH_CREDENTIAL_VALIDITY_SECONDS);
    if !(MIN_OAUTH_CREDENTIAL_VALIDITY_SECONDS..=MAX_OAUTH_CREDENTIAL_VALIDITY_SECONDS)
        .contains(&value)
    {
        return Err(AppError::BadRequest(format!(
            "min_validity_seconds 必须为 {}-{}",
            MIN_OAUTH_CREDENTIAL_VALIDITY_SECONDS, MAX_OAUTH_CREDENTIAL_VALIDITY_SECONDS
        )));
    }
    Ok(value)
}

/// 校验账号选择的请求构造方式，未知值不得降级成旧后端。
fn validate_request_backend(value: &str) -> Result<String, AppError> {
    match value {
        "legacy" | "native293" => Ok(value.into()),
        _ => Err(AppError::BadRequest(
            "request_backend 只支持 legacy 或 native293".into(),
        )),
    }
}

/// 附加两平台共用的实时容量和速率数据。@param service 账号服务。@param account 当前账号。@param view 账号视图。@return 调度摘要可复用的容量快照。
async fn append_account_live_metrics(
    service: &AccountService,
    account: &Account,
    view: &mut Value,
) -> AccountCapacityInfo {
    let capacity = service.get_account_capacity_info(account).await;
    view["current_concurrency"] = json!(capacity.current_concurrency);
    view["current_concurrency_units"] = json!(capacity.current_concurrency_units);
    view["max_concurrency_units"] = json!(capacity.max_concurrency_units);
    view["active_requests"] = json!(capacity.active_requests);
    view["queued_requests"] = json!(capacity.queued);
    view["queued_request_units"] = json!(capacity.queued_request_units);
    view["transient_backoff_waiting"] = json!(capacity.transient_backoff_waiting);
    view["transient_backoff_remaining_ms"] = json!(capacity.transient_backoff_remaining_ms);
    if let Ok(rpm) = service.get_account_rpm_status(account).await {
        view["rpm_current"] = json!(rpm.current);
        view["rpm_remaining"] = json!(rpm.remaining);
        view["rpm_window_reset_at"] = json!(rpm.window_reset_at.to_rfc3339());
        view["rpm_saturated"] = json!(rpm.saturated);
    }
    capacity
}

/// 读取当前账号视图的已记录用量。@param state 网关状态。@param ids 反重力账号。@return 缺失表示诊断统计不可用。
async fn agy_account_usage(state: &AppState, ids: &[i64]) -> HashMap<i64, AgyRequestUsage> {
    let Some(store) = state.gateway_svc.diagnostics_store() else {
        return HashMap::new();
    };
    match store.agy_request_usage(ids, Utc::now()).await {
        Ok(stats) => stats,
        Err(error) => {
            warn!(%error, "反重力网关用量统计读取失败");
            HashMap::new()
        }
    }
}

/// 按身份读取配置供跨页直达编辑。@param state 服务。@param id 身份。@return 账号配置。
async fn get_account(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Value>, AppError> {
    let account = state.account_svc.get_account(id).await?;
    let mut value = json!(account);
    if account.is_antigravity() {
        value["credential_state"] = state.account_svc.agy_state(id).await?;
        value["agy_request_usage"] = json!(agy_account_usage(&state, &[id]).await.get(&id));
        append_account_live_metrics(&state.account_svc, &account, &mut value).await;
    }
    value["work_control"] =
        serde_json::to_value(state.account_svc.work_controls.snapshot(id).await?)
            .map_err(|_| AppError::Internal("账号工作状态编码失败".into()))?;
    Ok(Json(value))
}

/// 读取独立工作控制。@param state 服务。@param id 账号。@return 实际准入与收尾状态。
async fn get_account_work(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<AccountWorkSnapshot>, AppError> {
    state.account_svc.get_account(id).await?;
    Ok(Json(state.account_svc.work_controls.snapshot(id).await?))
}

/// 热更新接单；关联部署的整体工作由编排协调。@param state 服务。@param id 账号。@param headers 内部证明。@param input 增量。@return 已保存状态。
async fn update_account_work(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    headers: HeaderMap,
    Json(input): Json<AccountWorkUpdate>,
) -> Result<Json<AccountWorkSnapshot>, AppError> {
    state.account_svc.get_account(id).await?;
    if input.work_enabled.is_some()
        && std::env::var("V3_RUNTIME_URL").is_ok_and(|value| !value.is_empty())
    {
        require_v3_credential_service(&headers)?;
    }
    let snapshot = state.account_svc.work_controls.update(id, input).await?;
    Ok(Json(snapshot))
}

async fn create_account(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CreateAccountRequest>,
) -> Result<(StatusCode, Json<Account>), AppError> {
    let _proxy_guard = state.proxy_svc.mutations.lock().await;
    let selected_proxy = if let Some(id) = req.proxy_id.as_deref() {
        if req.proxy_url.is_some() {
            return Err(AppError::BadRequest("代理ID与地址不能同时提交".into()));
        }
        let proxy = state.proxy_svc.store.get(id).await?;
        if req
            .proxy_revision
            .as_deref()
            .is_some_and(|revision| revision != proxy.revision)
        {
            return Err(AppError::BadRequest("所选代理已变化，请重新选择".into()));
        }
        Some(proxy.connection.private_url)
    } else {
        req.proxy_url
    };
    let backend = validate_request_backend(req.request_backend.as_deref().unwrap_or("legacy"))?;
    if req.email.is_empty() {
        return Err(AppError::BadRequest("email is required".into()));
    }
    let platform = req.platform.as_deref().unwrap_or("claude_code");
    if !["claude_code", "antigravity"].contains(&platform) {
        return Err(AppError::BadRequest("账号平台无效".into()));
    }
    if platform == "antigravity" && req.auth_type.as_deref() != Some("oauth") {
        return Err(AppError::BadRequest("AGY 账号仅支持原生 OAuth".into()));
    }
    if platform == "claude_code" && req.agy_system_prompt_homoglyph_enabled == Some(true) {
        return Err(AppError::BadRequest("同形体开关仅适用于 AGY 账号".into()));
    }
    if platform == "antigravity"
        && (req.cli_identity.is_some()
            || req.credential_ownership.is_some()
            || req
                .request_backend
                .as_deref()
                .is_some_and(|value| value != "legacy")
            || req.auto_telemetry == Some(true)
            || req.auto_poll_usage == Some(true)
            || req.five_hour_usage_limit_percent != 0
            || req.seven_day_usage_limit_percent != 0)
    {
        return Err(AppError::BadRequest(
            "AGY 账号配置包含 Claude Code 专用字段".into(),
        ));
    }
    if platform != "antigravity" && req.agy_gif_frames_enabled == Some(true) {
        return Err(AppError::BadRequest("GIF 抽帧仅适用于 AGY 账号".into()));
    }
    let auth_type = req.auth_type.unwrap_or_else(|| "setup_token".into()).into();
    let setup_token = req.setup_token.or(req.token).unwrap_or_default();
    let mut account = Account {
        platform: platform.into(),
        agy_system_prompt_homoglyph_enabled: req
            .agy_system_prompt_homoglyph_enabled
            .unwrap_or(false),
        agy_gif_frames_enabled: req.agy_gif_frames_enabled.unwrap_or_default(),
        id: 0,
        name: req.name.unwrap_or_default(),
        email: req.email,
        status: AccountStatus::Active,
        auth_type,
        setup_token,
        access_token: req.access_token.unwrap_or_default(),
        refresh_token: req.refresh_token.unwrap_or_default(),
        expires_at: req.expires_at.and_then(timestamp_millis_to_utc),
        oauth_refreshed_at: None,
        auth_error: String::new(),
        proxy_url: selected_proxy.unwrap_or_default(),
        device_id: String::new(),
        canonical_env: serde_json::json!({}),
        canonical_prompt: serde_json::json!({}),
        canonical_process: serde_json::json!({}),
        request_backend: backend,
        billing_mode: req.billing_mode.unwrap_or_else(|| "strip".into()).into(),
        account_uuid: req.account_uuid,
        organization_uuid: req.organization_uuid,
        subscription_type: req.subscription_type,
        rate_limit_tier: req.rate_limit_tier,
        concurrency: req.concurrency.unwrap_or(3),
        priority: req.priority.unwrap_or(50),
        rpm_limit: req.rpm_limit.unwrap_or(0).max(0),
        five_hour_usage_limit_percent: req.five_hour_usage_limit_percent,
        seven_day_usage_limit_percent: req.seven_day_usage_limit_percent,
        rate_limited_at: None,
        rate_limit_reset_at: None,
        disable_reason: String::new(),
        auto_telemetry: req.auto_telemetry.unwrap_or(false),
        auto_poll_usage: req.auto_poll_usage.unwrap_or(false),
        allow_1m_models: req
            .allow_1m_models
            .unwrap_or_else(|| DEFAULT_ALLOW_1M_MODELS.to_string()),
        allow_fast_mode: req.allow_fast_mode.unwrap_or(false),
        upstream_session_pool_enabled: req.upstream_session_pool_enabled.unwrap_or(false),
        upstream_session_pool_size: req
            .upstream_session_pool_size
            .unwrap_or(DEFAULT_UPSTREAM_SESSION_POOL_SIZE),
        upstream_session_ttl_minutes: req
            .upstream_session_ttl_minutes
            .unwrap_or(DEFAULT_UPSTREAM_SESSION_TTL_MINUTES),
        upstream_session_refresh_policy: req
            .upstream_session_refresh_policy
            .unwrap_or_else(|| DEFAULT_UPSTREAM_SESSION_REFRESH_POLICY.to_string()),
        telemetry_count: 0,
        usage_data: serde_json::json!({}),
        usage_fetched_at: None,
        created_at: chrono::Utc::now(),
        updated_at: chrono::Utc::now(),
    };
    if let Some(identity) = req.cli_identity {
        let expected = std::env::var("V3_INTERNAL_TOKEN").unwrap_or_default();
        let supplied = headers
            .get("x-v3-service-token")
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default();
        if expected.len() < 32
            || !bool::from(expected.as_bytes().ct_eq(supplied.as_bytes()))
            || identity.environment_id.len() != 32
            || !identity
                .environment_id
                .bytes()
                .all(|value| value.is_ascii_hexdigit())
            || !identity.has_confirmed_source()
        {
            return Err(AppError::Unauthorized);
        }
        account.device_id = identity.device_id;
        account.canonical_env = serde_json::to_value(identity.canonical_env)
            .map_err(|_| AppError::BadRequest("invalid CLI environment".into()))?;
        account.canonical_prompt = serde_json::to_value(identity.canonical_prompt)
            .map_err(|_| AppError::BadRequest("invalid CLI prompt environment".into()))?;
        if let Some(process) = identity.canonical_process {
            let version = account.canonical_env["version"]
                .as_str()
                .unwrap_or_default();
            if !process.has_valid_cli_observation(&identity.environment_id, version) {
                return Err(AppError::BadRequest(
                    "invalid CLI process observation".into(),
                ));
            }
            account.canonical_process = serde_json::to_value(process)
                .map_err(|_| AppError::BadRequest("invalid CLI process observation".into()))?;
        }
        let ownership = req
            .credential_ownership
            .as_ref()
            .ok_or_else(|| AppError::BadRequest("CLI 账号创建需要凭据交接协议 1".into()))?;
        if ownership.identity.environment_id != identity.environment_id {
            return Err(AppError::BadRequest("创建归属与 CLI 环境不一致".into()));
        }
        state
            .account_svc
            .create_cli_account_owned(&mut account, Some(ownership))
            .await?;
    } else {
        state.account_svc.create_account(&mut account).await?;
    }
    Ok((StatusCode::CREATED, Json(account)))
}

/// 仅导入已绑定账号的进程实测值，不调用凭据解析或停止发送器。
/// @param state 当前应用服务。
/// @param id 原关联账号 ID。
/// @param headers 管理鉴权与内部服务证明。
/// @param input 独立进程指标载荷。
/// @return 更新后的进程指标，不含凭据。
async fn import_cli_process(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    headers: HeaderMap,
    Json(input): Json<CliProcessImport>,
) -> Result<Json<serde_json::Value>, AppError> {
    require_v3_credential_service(&headers)?;
    let account = state.account_svc.get_account(id).await?;
    let queue = state
        .account_svc
        .get_or_create_queue(id, account.concurrency)
        .await;
    let lease = queue
        .runtime_gate
        .prepare(&format!("gateway-config:{}", Uuid::new_v4()))?;
    let permit = RuntimeConfigPermit { queue, lease };
    if permit.queue.runtime_gate.snapshot()["active"]
        .as_i64()
        .unwrap_or(0)
        != 0
        || permit.queue.waiting_count() != 0
    {
        return Err(AppError::BadRequest(
            "账号当前有活动请求，请稍后更新进程指标".into(),
        ));
    }
    let process = state.account_svc.import_cli_process(id, &input).await?;
    Ok(Json(
        serde_json::json!({"ok": true, "account_id": id, "canonical_process": process}),
    ))
}

/// 配置修改期间阻止新推理进入，检查和写库之间不能出现新活动请求。
pub(super) struct RuntimeConfigPermit {
    queue: Arc<AccountQueue>,
    lease: RuntimeLease,
}

impl Drop for RuntimeConfigPermit {
    fn drop(&mut self) {
        if self
            .queue
            .runtime_gate
            .update(&self.lease.owner, &self.lease.generation, "release")
            .is_err()
        {
            warn!("v3 configuration lease requires reconciliation");
        }
    }
}

/// 持有原账号配置门禁并核对当前活动。
/// @param state 应用服务。@param account 当前账号。@param force 强制核对独立网关队列。
/// @return 维护许可，释放时恢复原接单状态。
pub(super) async fn config_permit(
    state: &AppState,
    account: &Account,
    force: bool,
) -> Result<Option<RuntimeConfigPermit>, AppError> {
    if account.is_antigravity() {
        if state.account_svc.agy_state(account.id).await?["phase"] != "ready" {
            return Err(AppError::BadRequest("AGY 原凭据操作待核对".into()));
        }
    }
    if !force
        && state.account_svc.scheduler().is_none()
        && std::env::var("V3_RUNTIME_URL")
            .unwrap_or_default()
            .is_empty()
    {
        return Ok(None);
    }
    let queue = state
        .account_svc
        .get_or_create_queue(account.id, account.concurrency)
        .await;
    let lease = queue
        .runtime_gate
        .prepare(&format!("gateway-config:{}", Uuid::new_v4()))?;
    let permit = RuntimeConfigPermit { queue, lease };
    if permit.queue.runtime_gate.snapshot()["active"]
        .as_i64()
        .unwrap_or(0)
        != 0
        || permit.queue.waiting_count() != 0
    {
        return Err(AppError::BadRequest("account runtime is busy".into()));
    }
    if !force
        || !std::env::var("V3_RUNTIME_URL")
            .unwrap_or_default()
            .is_empty()
    {
        runtime_bridge::quiesce(account.id, &permit.lease).await?;
    }
    Ok(Some(permit))
}

/// 解码可选套餐字段，区分未提交与明确清除。
/// @param updates 原始增量载荷。
/// @param key 受控字段名。
/// @return 外层为空表示保持原值，内层为空表示清除。
fn subscription_update(
    updates: &serde_json::Value,
    key: &str,
) -> Result<Option<Option<String>>, AppError> {
    let Some(value) = updates.get(key) else {
        return Ok(None);
    };
    if value.is_null() {
        return Ok(Some(None));
    }
    let raw = value
        .as_str()
        .ok_or_else(|| AppError::BadRequest(format!("{key} 必须为文本或空值")))?;
    if raw.len() > 256 || raw.chars().any(char::is_control) {
        return Err(AppError::BadRequest(format!(
            "{key} 必须为不含控制字符的短文本"
        )));
    }
    Ok(Some(
        (!raw.trim().is_empty()).then(|| raw.trim().to_string()),
    ))
}

async fn update_account(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(updates): Json<serde_json::Value>,
) -> Result<Json<Account>, AppError> {
    let _proxy_guard = if updates.get("proxy_id").is_some() || updates.get("proxy_url").is_some() {
        Some(state.proxy_svc.mutations.lock().await)
    } else {
        None
    };
    let mut updates = updates;
    if let Some(selected) = updates.get("proxy_id").cloned() {
        if updates.get("proxy_url").is_some() {
            return Err(AppError::BadRequest("代理ID与地址不能同时提交".into()));
        }
        let url = if selected.is_null() {
            String::new()
        } else {
            let id = selected
                .as_str()
                .ok_or_else(|| AppError::BadRequest("代理ID格式无效".into()))?;
            let proxy = state.proxy_svc.store.get(id).await?;
            if updates
                .get("proxy_revision")
                .and_then(Value::as_str)
                .is_some_and(|revision| revision != proxy.revision)
            {
                return Err(AppError::BadRequest("所选代理已变化，请重新选择".into()));
            }
            proxy.connection.private_url
        };
        let object = updates
            .as_object_mut()
            .ok_or_else(|| AppError::BadRequest("账号更新必须是对象".into()))?;
        object.remove("proxy_id");
        object.remove("proxy_revision");
        object.insert("proxy_url".into(), json!(url));
    }
    let mut existing = state.account_svc.get_account(id).await?;
    if !existing.is_claude_code() && !existing.is_antigravity() {
        return Err(AppError::BadRequest("未知账号平台，请核对原记录".into()));
    }
    if existing.is_antigravity() {
        let runtime_changed = updates
            .get("proxy_url")
            .is_some_and(|value| value.as_str() != Some(existing.proxy_url.as_str()))
            || updates
                .get("concurrency")
                .is_some_and(|value| value.as_i64() != Some(existing.concurrency as i64));
        let _runtime_permit = if runtime_changed {
            config_permit(&state, &existing, false).await?
        } else {
            None
        };
        return Ok(Json(
            state.account_svc.update_agy_fields(id, &updates).await?,
        ));
    }

    if updates
        .get("platform")
        .is_some_and(|value| value.as_str() != Some(existing.platform.as_str()))
    {
        return Err(AppError::BadRequest("账号平台在创建后保持固定".into()));
    }
    if let Some(fields) = updates.as_object_mut() {
        fields.remove("platform");
    }
    if updates.get("agy_gif_frames_enabled").is_some() {
        return Err(AppError::BadRequest("GIF 抽帧仅适用于 AGY 账号".into()));
    }
    if let Some(value) = updates.get("agy_system_prompt_homoglyph_enabled") {
        if !existing.is_antigravity() {
            return Err(AppError::BadRequest("同形体策略仅用于 AGY 账号".into()));
        }
        existing.agy_system_prompt_homoglyph_enabled = value
            .as_bool()
            .ok_or_else(|| AppError::BadRequest("同形体开关必须为布尔值".into()))?;
    }
    let mut option_fields: Vec<&str> = updates
        .as_object()
        .ok_or_else(|| AppError::BadRequest("账号更新必须是对象".into()))?
        .keys()
        .map(String::as_str)
        .collect();
    if let Some(value) = updates.get("request_backend") {
        existing.request_backend = validate_request_backend(
            value
                .as_str()
                .ok_or_else(|| AppError::BadRequest("request_backend 必须为文本".into()))?,
        )?;
    }
    let subscription = subscription_update(&updates, "subscription_type")?;
    let tier = subscription_update(&updates, "rate_limit_tier")?;
    if (subscription.is_some() || tier.is_some())
        && updates.as_object().is_some_and(|fields| {
            fields
                .keys()
                .all(|key| matches!(key.as_str(), "subscription_type" | "rate_limit_tier"))
        })
    {
        // 同步套餐不能顺便写回旧 AT/RT；元数据使用独立 SQL 和刷新锁。
        state
            .account_svc
            .update_subscription_metadata(id, subscription, tier)
            .await?;
        return Ok(Json(state.account_svc.get_account(id).await?));
    }
    if let Some(value) = &subscription {
        if value != &existing.subscription_type && tier.is_none() {
            existing.rate_limit_tier = None;
            option_fields.push("rate_limit_tier");
        }
        existing.subscription_type = value.clone();
    }
    if let Some(value) = &tier {
        existing.rate_limit_tier = value.clone();
    }
    // 先校验新字段，避免状态快捷操作或其它配置先写入后才发现限额无效。
    for (key, limit) in [
        (
            "five_hour_usage_limit_percent",
            &mut existing.five_hour_usage_limit_percent,
        ),
        (
            "seven_day_usage_limit_percent",
            &mut existing.seven_day_usage_limit_percent,
        ),
    ] {
        if let Some(value) = updates.get(key) {
            let number = value
                .as_i64()
                .filter(|number| (0..=100).contains(number))
                .ok_or_else(|| AppError::BadRequest(format!("{key} 必须是 0～100 的整数")))?;
            *limit = number as i32;
        }
    }
    let runtime_update = [
        "request_backend",
        "email",
        "proxy_url",
        "auth_type",
        "access_token",
        "refresh_token",
        "status",
        "token",
        "setup_token",
        "account_uuid",
        "organization_uuid",
        "expires_at",
    ]
    .iter()
    .any(|key| updates.get(key).is_some());
    // 普通限额、优先级等仍可热改；受管凭据只能在已确认的网关归属下修改。
    let credential_update = [
        "email",
        "auth_type",
        "access_token",
        "refresh_token",
        "token",
        "setup_token",
        "account_uuid",
        "organization_uuid",
        "expires_at",
    ]
    .iter()
    .any(|key| updates.get(key).is_some());
    let _credential_activity = if credential_update {
        Some(state.account_svc.upstream_activity(existing.id).await?)
    } else {
        None
    };
    let _runtime_permit = if runtime_update {
        config_permit(&state, &existing, updates.get("request_backend").is_some()).await?
    } else {
        None
    };

    if let Some(name) = updates.get("name").and_then(|v| v.as_str()) {
        if !name.is_empty() {
            existing.name = name.to_string();
        }
    }
    if let Some(email) = updates.get("email").and_then(|v| v.as_str()) {
        if !email.is_empty() {
            existing.email = email.to_string();
        }
    }
    if let Some(auth_type) = updates.get("auth_type").and_then(|v| v.as_str()) {
        existing.auth_type = auth_type.to_string().into();
        match existing.auth_type {
            AccountAuthType::SetupToken => {
                existing.access_token.clear();
                existing.refresh_token.clear();
                existing.expires_at = None;
                existing.oauth_refreshed_at = None;
                existing.auth_error.clear();
            }
            AccountAuthType::Oauth => {
                existing.setup_token.clear();
            }
        }
    }
    if let Some(token) = updates.get("token").and_then(|v| v.as_str()) {
        existing.setup_token = token.to_string();
    }
    if let Some(setup_token) = updates.get("setup_token").and_then(|v| v.as_str()) {
        existing.setup_token = setup_token.to_string();
    }
    if let Some(access_token) = updates.get("access_token").and_then(|v| v.as_str()) {
        existing.access_token = access_token.to_string();
    }
    if let Some(refresh_token) = updates.get("refresh_token").and_then(|v| v.as_str()) {
        existing.refresh_token = refresh_token.to_string();
    }
    if updates.get("expires_at").is_some() {
        existing.expires_at = updates
            .get("expires_at")
            .and_then(|v| v.as_i64())
            .and_then(timestamp_millis_to_utc);
    }
    if let Some(proxy_url) = updates.get("proxy_url").and_then(|v| v.as_str()) {
        existing.proxy_url = proxy_url.to_string();
    }
    for (key, target, minimum) in [
        ("concurrency", &mut existing.concurrency, 1),
        ("priority", &mut existing.priority, 1),
        ("rpm_limit", &mut existing.rpm_limit, 0),
    ] {
        if let Some(value) = updates.get(key) {
            *target = value
                .as_i64()
                .and_then(|number| i32::try_from(number).ok())
                .filter(|number| *number >= minimum)
                .ok_or_else(|| {
                    AppError::BadRequest(format!("{key} 必须是 {minimum}～{} 的整数", i32::MAX))
                })?;
        }
    }
    if let Some(status) = updates.get("status").and_then(|v| v.as_str()) {
        if !status.is_empty() {
            if status == "active" {
                state.account_svc.enable_account(id).await?;
            } else if status == "disabled" {
                state
                    .account_svc
                    .disable_account(id, AccountStatus::Disabled, "手动停用", None)
                    .await?;
            } else {
                existing.status = status.to_string().into();
            }
            if status == "active" || status == "disabled" {
                if updates.get("five_hour_usage_limit_percent").is_some()
                    || updates.get("seven_day_usage_limit_percent").is_some()
                {
                    // 只写控制线，不能把状态操作前的旧凭据或状态整行写回。
                    state
                        .account_svc
                        .update_account_usage_limits(&existing)
                        .await?;
                }
                if subscription.is_some() || tier.is_some() {
                    state
                        .account_svc
                        .update_subscription_metadata(id, subscription.clone(), tier.clone())
                        .await?;
                }
                if updates.get("request_backend").is_some() {
                    state
                        .account_svc
                        .update_account_options(&existing, &["request_backend"])
                        .await?;
                }
                existing = state.account_svc.get_account(id).await?;
                drop(_runtime_permit);
                if updates.get("request_backend").is_some()
                    && existing.request_backend == "native293"
                    && existing.status == AccountStatus::Active
                {
                    state.account_svc.request_native_wake(id);
                }
                return Ok(Json(existing));
            }
        }
    }
    if let Some(billing_mode) = updates.get("billing_mode").and_then(|v| v.as_str()) {
        if !billing_mode.is_empty() {
            existing.billing_mode = billing_mode.to_string().into();
        }
    }
    if updates.get("account_uuid").is_some() {
        existing.account_uuid = updates
            .get("account_uuid")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
    }
    if updates.get("organization_uuid").is_some() {
        existing.organization_uuid = updates
            .get("organization_uuid")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
    }
    if let Some(auto_telemetry) = updates.get("auto_telemetry").and_then(|v| v.as_bool()) {
        existing.auto_telemetry = auto_telemetry;
    }
    if let Some(auto_poll_usage) = updates.get("auto_poll_usage").and_then(|v| v.as_bool()) {
        existing.auto_poll_usage = auto_poll_usage;
    }
    if let Some(allow_1m_models) = updates.get("allow_1m_models").and_then(|v| v.as_str()) {
        existing.allow_1m_models = allow_1m_models.to_string();
    }
    if let Some(allow_fast_mode) = updates.get("allow_fast_mode").and_then(|v| v.as_bool()) {
        existing.allow_fast_mode = allow_fast_mode;
    }
    if let Some(enabled) = updates
        .get("upstream_session_pool_enabled")
        .and_then(|v| v.as_bool())
    {
        existing.upstream_session_pool_enabled = enabled;
    }
    if let Some(size) = updates
        .get("upstream_session_pool_size")
        .and_then(|v| v.as_i64())
    {
        existing.upstream_session_pool_size = i32::try_from(size).unwrap_or(i32::MIN);
    }
    if let Some(ttl_minutes) = updates
        .get("upstream_session_ttl_minutes")
        .and_then(|v| v.as_i64())
    {
        existing.upstream_session_ttl_minutes = i32::try_from(ttl_minutes).unwrap_or(i32::MIN);
    }
    if let Some(policy) = updates
        .get("upstream_session_refresh_policy")
        .and_then(|v| v.as_str())
    {
        existing.upstream_session_refresh_policy = policy.to_string();
    }

    if runtime_update {
        state.account_svc.update_account(&existing).await?;
    } else {
        state
            .account_svc
            .update_account_options(&existing, &option_fields)
            .await?;
    }
    existing = state.account_svc.get_account(id).await?;
    // 准备会反向读取环境及凭据，必须在配置排他门禁释放后才允许唤醒。
    drop(_runtime_permit);
    if updates.get("request_backend").is_some()
        && existing.request_backend == "native293"
        && existing.status == AccountStatus::Active
    {
        state.account_svc.request_native_wake(id);
    }
    Ok(Json(existing))
}

/// 在 cc2api 账号锁内解析满足有效期要求的 OAuth 凭据。
///
/// @param state 应用状态。
/// @param id cc2api 账号 ID。
/// @param req 最小有效期和强制刷新选项。
/// @return 同一次最终落库状态中的 AT、RT 和过期时间。
async fn resolve_oauth_credentials(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(req): Json<ResolveOAuthCredentialsRequest>,
) -> Result<Json<ResolveOAuthCredentialsResponse>, AppError> {
    let account = state.account_svc.get_account(id).await?;
    let queue = state
        .account_svc
        .get_or_create_queue(id, account.concurrency)
        .await;
    let _update_activity = system_update::continuation(|| {
        let snapshot = queue.runtime_gate.snapshot();
        snapshot["active"].as_u64().unwrap_or(0) > 0
            || !snapshot["lease"].is_null()
            || snapshot["holders"]
                .as_array()
                .is_some_and(|items| !items.is_empty())
    })?;
    let min_validity_seconds =
        normalize_oauth_credential_validity_seconds(req.min_validity_seconds)?;
    let snapshot = state
        .account_svc
        .resolve_oauth_credentials(id, min_validity_seconds, req.force_refresh.unwrap_or(false))
        .await?;
    Ok(Json(ResolveOAuthCredentialsResponse {
        account_id: snapshot.account_id,
        access_token: snapshot.access_token,
        refresh_token: snapshot.refresh_token,
        expires_at: snapshot.expires_at,
    }))
}

async fn delete_account(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, AppError> {
    let account = state.account_svc.get_account(id).await?;
    let _runtime_permit = config_permit(&state, &account, false).await?;
    state.account_svc.delete_account(id).await?;
    Ok(Json(serde_json::json!({"status": "deleted"})))
}

/// 返回受信任交接能力，不接触账号令牌。
/// @param headers 管理及服务证明。@return 当前协议版本。
async fn credential_capabilities(headers: HeaderMap) -> Result<Json<Value>, AppError> {
    require_v3_credential_service(&headers)?;
    Ok(Json(json!({"credential_ownership_protocol":1})))
}

/// 查询原账号凭据归属，不触发刷新。
/// @param state 服务。@param id 原账号。@param headers 服务证明。@return 脱敏归属。
async fn credential_ownership(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    headers: HeaderMap,
) -> Result<Json<Value>, AppError> {
    require_v3_credential_service(&headers)?;
    Ok(Json(
        json!({"protocol":1,"ownership":state.account_svc.credential_ownership(id).await?}),
    ))
}

/// 推进同代交接或查询回执；完整凭据只返回内部受信任调用方。
/// @param state 服务。@param id 原账号。@param headers 服务证明。@param input 操作。
/// @return 同操作回执与允许的凭据快照。
async fn credential_handoff(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    headers: HeaderMap,
    Json(input): Json<CredentialOwnershipInput>,
) -> Result<Json<Value>, AppError> {
    require_v3_credential_service(&headers)?;
    Ok(Json(
        state.account_svc.credential_handoff(id, &input).await?,
    ))
}

async fn test_account(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, AppError> {
    if !state
        .account_svc
        .work_controls
        .snapshot(id)
        .await?
        .work_enabled
    {
        return Err(AppError::BadRequest("账号已整体停用".into()));
    }
    let _credential_activity = state.account_svc.upstream_activity(id).await?;
    let account = state.account_svc.get_account(id).await?;
    if account.is_antigravity() {
        let usage = state.account_svc.refresh_usage(id).await?;
        return Ok(Json(json!({"status":"ok","usage":usage})));
    }
    let token = match state.account_svc.resolve_upstream_token(id).await {
        Ok(token) => token,
        Err(e) => {
            return Ok(Json(
                serde_json::json!({"status": "error", "message": e.to_string()}),
            ));
        }
    };
    match state.token_tester.test_token(&token, &account).await {
        Ok(()) => Ok(Json(serde_json::json!({"status": "ok"}))),
        Err(e) => Ok(Json(
            serde_json::json!({"status": "error", "message": e.to_string()}),
        )),
    }
}

async fn refresh_usage(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, AppError> {
    match state.account_svc.refresh_usage(id).await {
        Ok(usage) => Ok(Json(serde_json::json!({"status": "ok", "usage": usage}))),
        Err(e) => {
            let message = match &e {
                AppError::TooManyRequests(_) => "用量查询接口超限，请一分钟后再试".to_string(),
                _ => e.to_string(),
            };
            Ok(Json(
                serde_json::json!({"status": "error", "message": message}),
            ))
        }
    }
}

// --- Token Handlers ---

async fn list_tokens(
    State(state): State<AppState>,
    Query(query): Query<PageQuery>,
) -> Result<Json<serde_json::Value>, AppError> {
    let page = query.page.unwrap_or(1).max(1);
    let page_size = query.page_size.unwrap_or(20).clamp(1, 100);
    let total = state.token_store.count().await?;
    let tokens = state.token_store.list_paged(page, page_size).await?;
    let total_pages = (total + page_size - 1) / page_size;
    Ok(Json(serde_json::json!({
        "data": tokens,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    })))
}

#[derive(Deserialize)]
struct CreateTokenRequest {
    name: Option<String>,
    allowed_accounts: Option<String>,
    blocked_accounts: Option<String>,
}

async fn create_token(
    State(state): State<AppState>,
    Json(req): Json<CreateTokenRequest>,
) -> Result<(StatusCode, Json<ApiToken>), AppError> {
    let mut token = ApiToken {
        id: 0,
        name: req.name.unwrap_or_default(),
        token: api_token::generate_token(),
        allowed_accounts: req.allowed_accounts.unwrap_or_default(),
        blocked_accounts: req.blocked_accounts.unwrap_or_default(),
        status: api_token::ApiTokenStatus::Active,
        created_at: chrono::Utc::now(),
        updated_at: chrono::Utc::now(),
    };
    state.token_store.create(&mut token).await?;
    Ok((StatusCode::CREATED, Json(token)))
}

async fn update_token(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Json(updates): Json<serde_json::Value>,
) -> Result<Json<ApiToken>, AppError> {
    let mut existing = state.token_store.get_by_id(id).await?;

    if let Some(name) = updates.get("name").and_then(|v| v.as_str()) {
        existing.name = name.to_string();
    }
    if let Some(allowed) = updates.get("allowed_accounts").and_then(|v| v.as_str()) {
        existing.allowed_accounts = allowed.to_string();
    }
    if let Some(blocked) = updates.get("blocked_accounts").and_then(|v| v.as_str()) {
        existing.blocked_accounts = blocked.to_string();
    }
    if let Some(status) = updates.get("status").and_then(|v| v.as_str()) {
        if !status.is_empty() {
            existing.status = status.to_string().into();
        }
    }

    state.token_store.update(&existing).await?;
    Ok(Json(existing))
}

async fn delete_token_handler(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, AppError> {
    state.token_store.delete(id).await?;
    Ok(Json(serde_json::json!({"status": "deleted"})))
}

// --- Dashboard ---

async fn get_dashboard(State(state): State<AppState>) -> Result<Json<serde_json::Value>, AppError> {
    let accounts = state.account_svc.list_accounts().await?;
    let token_count = state.token_store.count().await.unwrap_or(0);

    let mut active = 0;
    let mut err_count = 0;
    let mut disabled = 0;
    for a in &accounts {
        match a.status {
            AccountStatus::Active => active += 1,
            AccountStatus::Error => err_count += 1,
            AccountStatus::Disabled => disabled += 1,
        }
    }

    Ok(Json(serde_json::json!({
        "accounts": {
            "total": accounts.len(),
            "active": active,
            "error": err_count,
            "disabled": disabled,
        },
        "tokens": token_count,
    })))
}

// --- OAuth Flow Handlers ---

/// 从目录解析授权线路，私有认证仅传入服务器内存会话。
/// @param state 管理服务。@param req 原授权请求。@return 完整私有授权配置。
async fn resolve_oauth_proxy(
    state: &AppState,
    mut req: GenerateAuthUrlRequest,
) -> Result<GenerateAuthUrlRequest, AppError> {
    if let Some(id) = req.proxy_id.as_deref() {
        if req.proxy_url.is_some() {
            return Err(AppError::BadRequest("代理ID与地址不能同时提交".into()));
        }
        let proxy = state.proxy_svc.store.get(id).await?;
        if req
            .proxy_revision
            .as_deref()
            .is_some_and(|revision| revision != proxy.revision)
        {
            return Err(AppError::BadRequest("所选代理已变化，请重新选择".into()));
        }
        req.proxy_url = Some(proxy.connection.private_url);
    }
    Ok(req)
}

async fn oauth_generate_auth_url(
    State(state): State<AppState>,
    Json(req): Json<crate::service::oauth_flow::GenerateAuthUrlRequest>,
) -> Result<Json<crate::service::oauth_flow::GenerateAuthUrlResponse>, AppError> {
    let _guard = state.proxy_svc.mutations.lock().await;
    let mut req = resolve_oauth_proxy(&state, req).await?;
    if req.platform.as_deref() == Some("antigravity") {
        if let Some(proxy) = req.proxy_url.as_mut().filter(|value| !value.is_empty()) {
            *proxy = ProxyConnection::parse(proxy)?.private_url;
        }
    }
    let generation = if req.platform.as_deref() == Some("antigravity") {
        if let Some(id) = req.account_id {
            let account = state.account_svc.get_account(id).await?;
            if !account.is_antigravity()
                || account.proxy_url != req.proxy_url.as_deref().unwrap_or("")
            {
                return Err(AppError::BadRequest("AGY 重授权须保持原账号及代理".into()));
            }
            let status = state.account_svc.agy_state(id).await?;
            if status["phase"] == "reconcile" {
                state.account_svc.retire_agy_operation(id).await?;
            } else if status["phase"] != "ready" {
                return Err(AppError::BadRequest("请先结束或核对原凭据操作".into()));
            }
            status["generation"].as_i64()
        } else {
            None
        }
    } else {
        if req.account_id.is_some() {
            return Err(AppError::BadRequest("此目标参数仅适用于 AGY 授权".into()));
        }
        None
    };
    let result = state
        .oauth_flow_svc
        .generate_platform_auth_url(&req, generation)
        .await?;
    if let Some(id) = req.account_id {
        match state
            .account_svc
            .begin_agy_reauth(id, &result.session_id)
            .await
        {
            Ok(actual) if Some(actual) == generation => {}
            other => {
                let phase = state
                    .oauth_flow_svc
                    .cancel_session(&result.session_id)
                    .await?;
                state
                    .account_svc
                    .cancel_agy_operation(&result.session_id, &phase)
                    .await?;
                other?;
                return Err(AppError::BadRequest("AGY 原账号代次已变化，请重试".into()));
            }
        }
    }
    Ok(Json(result))
}

async fn oauth_generate_setup_token_url(
    State(state): State<AppState>,
    Json(req): Json<crate::service::oauth_flow::GenerateAuthUrlRequest>,
) -> Result<Json<crate::service::oauth_flow::GenerateAuthUrlResponse>, AppError> {
    let _guard = state.proxy_svc.mutations.lock().await;
    let req = resolve_oauth_proxy(&state, req).await?;
    if req.platform.as_deref().unwrap_or("claude_code") != "claude_code" || req.account_id.is_some()
    {
        return Err(AppError::BadRequest(
            "Setup Token 仅适用于 Claude Code".into(),
        ));
    }
    Ok(Json(state.oauth_flow_svc.generate_setup_token_url(&req)))
}

async fn oauth_exchange_code(
    State(state): State<AppState>,
    Json(req): Json<crate::service::oauth_flow::ExchangeCodeRequest>,
) -> Result<Json<crate::service::oauth_flow::ExchangeCodeResponse>, AppError> {
    let _guard = state.proxy_svc.mutations.lock().await;
    let target = state.oauth_flow_svc.native_target(&req.session_id);
    let resp = state.oauth_flow_svc.exchange_code(&req).await?;
    if let Some(id) = target {
        let expiry = chrono::DateTime::from_timestamp(resp.expires_at, 0)
            .ok_or_else(|| AppError::ServiceUnavailable("AGY 授权有效期无效".into()))?;
        state.account_svc.finish_agy_operation(id, &req.session_id, &json!({
            "email_address":resp.email_address,"capabilities":resp.capabilities,"document":{"token":{"access_token":resp.access_token,
            "refresh_token":resp.refresh_token,"expiry":expiry.to_rfc3339()}}})).await?;
    }
    Ok(Json(resp))
}

/// 授权取消的冻结平台。
#[derive(Deserialize)]
struct OAuthCancelQuery {
    platform: Option<String>,
}

/// 关闭原授权会话及其原生进程。@param state 服务。@param session_id 原会话。@return 终态。
async fn oauth_cancel_session(
    State(state): State<AppState>,
    Path(session_id): Path<String>,
    Query(query): Query<OAuthCancelQuery>,
) -> Result<Json<Value>, AppError> {
    let phase = if query.platform.as_deref() == Some("antigravity") {
        state
            .oauth_flow_svc
            .cancel_native_session(&session_id)
            .await?
    } else {
        state.oauth_flow_svc.cancel_session(&session_id).await?
    };
    state
        .account_svc
        .cancel_agy_operation(&session_id, &phase)
        .await?;
    Ok(Json(json!({"phase":phase})))
}

/// 读取 AGY 管理操作。@param state 服务。@param id 账号。@return 脱敏状态。
async fn agy_credential_status(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Value>, AppError> {
    Ok(Json(state.account_svc.agy_state(id).await?))
}

/// 恢复原操作已产生的结果。@param state 服务。@param id 账号。@return 脱敏终态。
async fn agy_credential_recover(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Value>, AppError> {
    Ok(Json(state.account_svc.recover_agy_operation(id).await?))
}

async fn oauth_exchange_setup_token_code(
    State(state): State<AppState>,
    Json(req): Json<crate::service::oauth_flow::ExchangeCodeRequest>,
) -> Result<Json<crate::service::oauth_flow::ExchangeCodeResponse>, AppError> {
    let _guard = state.proxy_svc.mutations.lock().await;
    let resp = state.oauth_flow_svc.exchange_setup_token_code(&req).await?;
    Ok(Json(resp))
}

// --- 内嵌前端静态资源 ---

#[derive(Embed)]
#[folder = "../../apps/web/dist"]
struct Assets;

/// SPA 页面：返回 index.html
async fn spa_handler() -> impl IntoResponse {
    match Assets::get("index.html") {
        Some(index) => Response::builder()
            .header("content-type", "text/html")
            .body(axum::body::Body::from(index.data.to_vec()))
            .unwrap(),
        None => Response::builder()
            .status(StatusCode::NOT_FOUND)
            .body(axum::body::Body::from("frontend not built"))
            .unwrap(),
    }
}

/// 前端静态资源：/assets/*
async fn asset_handler(req: Request) -> impl IntoResponse {
    let path = req.uri().path().trim_start_matches('/');
    if let Some(file) = Assets::get(path) {
        let mime = mime_from_path(path);
        return Response::builder()
            .header("content-type", mime)
            .body(axum::body::Body::from(file.data.to_vec()))
            .unwrap();
    }
    Response::builder()
        .status(StatusCode::NOT_FOUND)
        .body(axum::body::Body::from("not found"))
        .unwrap()
}

fn mime_from_path(path: &str) -> &'static str {
    match path.rsplit('.').next() {
        Some("html") => "text/html",
        Some("css") => "text/css",
        Some("js") => "application/javascript",
        Some("json") => "application/json",
        Some("png") => "image/png",
        Some("jpg" | "jpeg") => "image/jpeg",
        Some("svg") => "image/svg+xml",
        Some("ico") => "image/x-icon",
        Some("woff") => "font/woff",
        Some("woff2") => "font/woff2",
        Some("ttf") => "font/ttf",
        _ => "application/octet-stream",
    }
}

fn timestamp_millis_to_utc(ts: i64) -> Option<chrono::DateTime<chrono::Utc>> {
    chrono::Utc.timestamp_millis_opt(ts).single()
}

/// 获取单账号只读调度快照，不续期或触发上游调用。
/// @param state 已通过管理员认证的状态。
/// @param id 正式账号 ID。
/// @return 真实状态、最近事件与完整性信息。
async fn account_scheduling(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, AppError> {
    let account = state.account_svc.get_account(id).await?;
    let scheduler = state
        .account_svc
        .scheduler()
        .ok_or_else(|| AppError::ServiceUnavailable("当前部署未启用 v3 调度".into()))?;
    let score = state.account_svc.get_account_capacity_info(&account).await;
    let counts = scheduler.store.counts(&[id], now_ms()).await?;
    let summary = state
        .account_svc
        .v3_summary(&account, &score, counts.get(&id).copied().unwrap_or(0))
        .await?;
    Ok(Json(
        serde_json::json!({"summary":summary,"snapshot":scheduler.snapshot(id)}),
    ))
}

/// 会话查询仅接受有界分页、活跃状态和十六进制匿名摘要前缀。
#[derive(Deserialize)]
struct SchedulingSessionQuery {
    page: Option<i64>,
    page_size: Option<i64>,
    state: Option<String>,
    prefix: Option<String>,
}

/// 分页读取网关绑定及阶段数，不返回原会话 ID 或凭据。
/// @param state 管理员状态。
/// @param id 正式账号 ID。
/// @param query 已解码查询参数。
/// @return 绑定列表、总数与观测时间。
async fn account_scheduling_sessions(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Query(query): Query<SchedulingSessionQuery>,
) -> Result<Json<serde_json::Value>, AppError> {
    state.account_svc.get_account(id).await?;
    let scheduler = state
        .account_svc
        .scheduler()
        .ok_or_else(|| AppError::ServiceUnavailable("当前部署未启用 v3 调度".into()))?;
    let page = query.page.unwrap_or(1);
    let page_size = query.page_size.unwrap_or(20);
    let prefix = query.prefix.unwrap_or_default().to_ascii_lowercase();
    if page < 1
        || !(1..=100).contains(&page_size)
        || prefix.len() > 64
        || !prefix.bytes().all(|c| c.is_ascii_hexdigit())
    {
        return Err(AppError::BadRequest("会话分页或摘要筛选不合法".into()));
    }
    let active = match query.state.as_deref().unwrap_or("all") {
        "all" => None,
        "active" => Some(true),
        "idle" => Some(false),
        _ => return Err(AppError::BadRequest("会话状态筛选不合法".into())),
    };
    let now = now_ms();
    let snapshot = scheduler.snapshot(id);
    let active_keys = scheduler.active_keys(id);
    let (bindings, total) = scheduler
        .store
        .sessions(id, now, page, page_size, &prefix, &active_keys, active)
        .await?;
    let items=bindings.into_iter().map(|b| {
        let requests=snapshot.requests.iter().filter(|r|r.bound && r.session_key.as_deref()==Some(b.session_key.as_str()));
        serde_json::json!({"session_key":b.session_key,"account_id":b.account_id,"created_at_ms":b.created_at_ms,"last_seen_at_ms":b.last_seen_at_ms,"expires_at_ms":b.expires_at_ms,"phases":PhaseCounts::of(requests)})
    }).collect::<Vec<_>>();
    Ok(Json(
        serde_json::json!({"items":items,"total":total,"page":page,"page_size":page_size,"observed_at_ms":now}),
    ))
}

// --- Settings Handlers ---

/// 获取所有设置项。
async fn get_settings(State(state): State<AppState>) -> Result<Json<serde_json::Value>, AppError> {
    let mut settings = state.settings_store.get_all().await?;
    settings
        .entry("session_policy_block_enabled".into())
        .or_insert_with(|| DEFAULT_SESSION_POLICY_BLOCK_ENABLED.into());
    settings
        .entry("session_policy_block_duration_minutes".into())
        .or_insert_with(|| DEFAULT_SESSION_POLICY_BLOCK_DURATION_MINUTES.into());
    for (key, value) in V3_SCHEDULING_DEFAULTS {
        settings
            .entry((*key).to_string())
            .or_insert_with(|| (*value).to_string());
    }
    for key in OBSOLETE_SETTINGS_KEYS
        .iter()
        .chain(OBSOLETE_SCHEDULING_KEYS)
    {
        settings.remove(*key);
    }
    settings
        .entry("allow_system_role_models".into())
        .or_insert_with(|| {
            crate::store::settings_store::DEFAULT_ALLOW_SYSTEM_ROLE_MODELS.to_string()
        });
    settings
        .entry("allowed_claude_code_versions".into())
        .or_insert_with(|| DEFAULT_ALLOWED_CLAUDE_CODE_VERSIONS.to_string());
    settings
        .entry("blocked_claude_code_versions".into())
        .or_insert_with(|| DEFAULT_BLOCKED_CLAUDE_CODE_VERSIONS.to_string());
    settings
        .entry("claude_code_version_profile".into())
        .or_insert_with(|| DEFAULT_CLAUDE_CODE_VERSION_PROFILE_SETTING.to_string());
    settings
        .entry("claude_code_profile_selection_mode".into())
        .or_insert_with(|| DEFAULT_CLAUDE_CODE_PROFILE_SELECTION_MODE_SETTING.to_string());
    settings.insert(
        "claude_code_version_profiles".into(),
        serde_json::to_string(&claude_code_version_profile_options())
            .unwrap_or_else(|_| "[]".into()),
    );
    settings
        .entry("allowed_user_agents".into())
        .or_insert_with(|| DEFAULT_ALLOWED_USER_AGENTS.to_string());
    settings
        .entry("claude_code_context_sanitizer_mode".into())
        .or_insert_with(|| DEFAULT_CLAUDE_CODE_CONTEXT_SANITIZER_MODE.to_string());
    settings
        .entry("passthrough_shell".into())
        .or_insert_with(|| crate::store::settings_store::DEFAULT_PASSTHROUGH_SHELL.to_string());
    settings
        .entry("passthrough_os_version".into())
        .or_insert_with(|| {
            crate::store::settings_store::DEFAULT_PASSTHROUGH_OS_VERSION.to_string()
        });
    settings
        .entry("passthrough_working_dir".into())
        .or_insert_with(|| {
            crate::store::settings_store::DEFAULT_PASSTHROUGH_WORKING_DIR.to_string()
        });
    settings
        .entry("cache_control_ttl_rewrite".into())
        .or_insert_with(|| DEFAULT_CACHE_CONTROL_TTL_REWRITE.to_string());
    let message_cache = settings
        .entry("message_cache_control_rewrite".into())
        .or_insert_with(|| DEFAULT_MESSAGE_CACHE_CONTROL_REWRITE.to_string());
    *message_cache = MessageCacheControlRewrite::parse_setting(message_cache)
        .unwrap_or(MessageCacheControlRewrite::Off)
        .as_str()
        .into();
    settings
        .entry("message_body_order_fingerprint_enabled".into())
        .or_insert_with(|| DEFAULT_MESSAGE_BODY_ORDER_FINGERPRINT_ENABLED.to_string());
    let top_field_filter = settings
        .entry("message_top_field_filter_enabled".into())
        .or_insert_with(|| DEFAULT_MESSAGE_TOP_FIELD_FILTER_ENABLED.to_string());
    *top_field_filter = normalize_message_top_field_filter_enabled(top_field_filter).into();
    settings
        .entry("fable_sticky_quota_fallback_enabled".into())
        .or_insert_with(|| DEFAULT_FABLE_STICKY_QUOTA_FALLBACK_ENABLED.to_string());
    settings
        .entry("fable_weekly_usage_limit_percent".into())
        .or_insert_with(|| DEFAULT_FABLE_WEEKLY_USAGE_LIMIT_PERCENT.to_string());
    settings
        .entry("proxy_client_pool_enabled".into())
        .or_insert_with(|| DEFAULT_PROXY_CLIENT_POOL_ENABLED.to_string());
    settings
        .entry("intercept_warmup_title_enabled".into())
        .or_insert_with(|| DEFAULT_INTERCEPT_WARMUP_TITLE_ENABLED.to_string());
    settings
        .entry("intercept_warmup_suggestion_enabled".into())
        .or_insert_with(|| DEFAULT_INTERCEPT_WARMUP_SUGGESTION_ENABLED.to_string());
    settings
        .entry("intercept_warmup_haiku_probe_enabled".into())
        .or_insert_with(|| DEFAULT_INTERCEPT_WARMUP_HAIKU_PROBE_ENABLED.to_string());
    settings
        .entry("intercept_auto_mode_classifier_stage1_mode".into())
        .or_insert_with(|| DEFAULT_INTERCEPT_AUTO_MODE_CLASSIFIER_STAGE1_MODE.to_string());
    settings
        .entry("intercept_auto_mode_classifier_stage2_mode".into())
        .or_insert_with(|| DEFAULT_INTERCEPT_AUTO_MODE_CLASSIFIER_STAGE2_MODE.to_string());
    settings
        .entry("intercept_cli_bg_status_classifier_mode".into())
        .or_insert_with(|| DEFAULT_INTERCEPT_CLI_BG_STATUS_CLASSIFIER_MODE.to_string());
    settings
        .entry("intercept_cli_bg_status_classifier_models".into())
        .or_insert_with(|| DEFAULT_INTERCEPT_CLI_BG_STATUS_CLASSIFIER_MODELS.to_string());
    settings
        .entry("intercept_cli_bg_status_classifier_identity_injection_enabled".into())
        .or_insert_with(|| {
            DEFAULT_INTERCEPT_CLI_BG_STATUS_CLASSIFIER_IDENTITY_INJECTION_ENABLED.to_string()
        });
    settings
        .entry("rewrite_disabled_thinking_enabled".into())
        .or_insert_with(|| DEFAULT_REWRITE_DISABLED_THINKING_ENABLED.to_string());
    settings
        .entry("rewrite_disabled_thinking_models".into())
        .or_insert_with(|| DEFAULT_REWRITE_DISABLED_THINKING_MODELS.to_string());
    settings
        .entry("intercept_assistant_prefill_enabled".into())
        .or_insert_with(|| DEFAULT_INTERCEPT_ASSISTANT_PREFILL_ENABLED.to_string());
    settings
        .entry("intercept_assistant_prefill_models".into())
        .or_insert_with(|| DEFAULT_INTERCEPT_ASSISTANT_PREFILL_MODELS.to_string());
    settings.insert(
        "request_diagnostics_log_mode".into(),
        state.gateway_svc.request_log_mode().await.as_str().into(),
    );
    settings
        .entry("log_429_request_enabled".into())
        .or_insert_with(|| DEFAULT_LOG_429_REQUEST_ENABLED.to_string());
    settings
        .entry("log_non_stream_request_enabled".into())
        .or_insert_with(|| DEFAULT_LOG_NON_STREAM_REQUEST_ENABLED.to_string());
    settings
        .entry("non_stream_probe_cache_enabled".into())
        .or_insert_with(|| DEFAULT_NON_STREAM_PROBE_CACHE_ENABLED.to_string());
    settings
        .entry("log_429_request_body_limit".into())
        .or_insert_with(|| DEFAULT_LOG_429_REQUEST_BODY_LIMIT.to_string());
    settings
        .entry("stream_keepalive_enabled".into())
        .or_insert_with(|| DEFAULT_STREAM_KEEPALIVE_ENABLED.to_string());
    settings
        .entry("stream_keepalive_interval_secs".into())
        .or_insert_with(|| DEFAULT_STREAM_KEEPALIVE_INTERVAL_SECS.to_string());
    settings
        .entry("stream_upstream_idle_timeout_secs".into())
        .or_insert_with(|| DEFAULT_STREAM_UPSTREAM_IDLE_TIMEOUT_SECS.to_string());
    settings.insert(
        "native_idle_timeout_secs".into(),
        state.gateway_svc.native_idle_timeout().to_string(),
    );
    settings
        .entry("bootstrap_model_options_mode".into())
        .or_insert_with(|| DEFAULT_BOOTSTRAP_MODEL_OPTIONS_MODE.to_string());
    settings
        .entry("bootstrap_additional_model_options".into())
        .or_insert_with(|| DEFAULT_BOOTSTRAP_ADDITIONAL_MODEL_OPTIONS.to_string());
    settings
        .entry("session_hello_probe_enabled".into())
        .or_insert_with(|| DEFAULT_SESSION_HELLO_PROBE_ENABLED.to_string());
    settings
        .entry("session_hello_probe_strict".into())
        .or_insert_with(|| DEFAULT_SESSION_HELLO_PROBE_STRICT.to_string());
    settings
        .entry("session_hello_probe_timeout_secs".into())
        .or_insert_with(|| DEFAULT_SESSION_HELLO_PROBE_TIMEOUT_SECS.to_string());
    settings
        .entry("session_hello_probe_success_ttl_secs".into())
        .or_insert_with(|| DEFAULT_SESSION_HELLO_PROBE_SUCCESS_TTL_SECS.to_string());
    settings
        .entry("session_hello_probe_failure_cooldown_secs".into())
        .or_insert_with(|| DEFAULT_SESSION_HELLO_PROBE_FAILURE_COOLDOWN_SECS.to_string());
    Ok(Json(serde_json::json!(settings)))
}

/// 构造前端可选 Claude Code 版本画像列表。
///
/// @return 可序列化的版本画像摘要列表。
fn claude_code_version_profile_options() -> Vec<serde_json::Value> {
    all_profiles()
        .iter()
        .map(|profile| {
            serde_json::json!({
                "key": profile.key,
                "version": profile.identity.version,
                "version_base": profile.identity.version_base,
                "build_time": profile.identity.build_time,
                "allowed_claude_code_versions": profile.access_policy.allowed_claude_code_versions,
                "growthbook_user_agent": profile.telemetry.growthbook_user_agent,
                "telemetry_shape": profile.telemetry.shape.as_str(),
            })
        })
        .collect()
}

/// 批量更新设置项。
async fn update_settings(
    State(state): State<AppState>,
    Json(mut body): Json<std::collections::HashMap<String, String>>,
) -> Result<Json<serde_json::Value>, AppError> {
    for key in OBSOLETE_SETTINGS_KEYS
        .iter()
        .chain(OBSOLETE_SCHEDULING_KEYS)
    {
        body.remove(*key);
    }
    let _v3_settings_guard = if body.keys().any(|key| key.starts_with("v3_")) {
        Some(state.account_svc.lock_v3_settings().await)
    } else {
        None
    };
    if body
        .keys()
        .any(|key| key.starts_with("session_policy_block_"))
    {
        let mut merged = state.settings_store.get_all().await?;
        merged.extend(body.clone());
        SessionPolicyBlockConfig::parse(&merged)?;
    }
    // 峰值预热开关:仅允许 "true" / "false"
    if let Some(val) = body.get("peak_prime_enabled") {
        if val != "true" && val != "false" {
            return Err(AppError::BadRequest(
                "'peak_prime_enabled' 必须是 true 或 false".into(),
            ));
        }
    }
    // 峰值预热小时列表:逗号分隔,每段必须是 0-23 整数;允许空串(等价于禁用)
    if let Some(val) = body.get("peak_prime_hours") {
        for seg in val.split(',').map(|s| s.trim()).filter(|s| !s.is_empty()) {
            match seg.parse::<u32>() {
                Ok(h) if h < 24 => {}
                _ => {
                    return Err(AppError::BadRequest(format!(
                        "'peak_prime_hours' 包含非法小时: {}",
                        seg
                    )));
                }
            }
        }
    }
    // 峰值预热模型:非空字符串,具体模型名由 Anthropic 侧校验
    if let Some(val) = body.get("peak_prime_model") {
        if val.trim().is_empty() {
            return Err(AppError::BadRequest("'peak_prime_model' 不能为空".into()));
        }
    }
    // 允许 messages[].role=system 的模型列表:逗号分隔,允许为空;非空项必须是模型 ID 安全集。
    if let Some(val) = body.get("allow_system_role_models") {
        validate_model_id_list("allow_system_role_models", val)?;
    }
    if let Some(val) = body.get("claude_code_profile_selection_mode") {
        ClaudeCodeProfileSelectionMode::parse(val)?;
    }
    let selected_profile = if let Some(val) = body.get("claude_code_version_profile") {
        Some(profile_for_key(val)?)
    } else {
        None
    };
    if let Some(val) = body.get("allowed_claude_code_versions") {
        validate_claude_code_versions(val)?;
    }
    if let Some(val) = body.get("blocked_claude_code_versions") {
        validate_blocked_claude_code_versions(val)?;
    }
    if let Some(val) = body.get("allowed_user_agents") {
        validate_user_agent_patterns(val)?;
    }
    // 系统提示词环境透传开关:仅允许 "true" / "false"
    for key in &[
        "passthrough_shell",
        "passthrough_os_version",
        "passthrough_working_dir",
    ] {
        if let Some(val) = body.get(*key) {
            if val != "true" && val != "false" {
                return Err(AppError::BadRequest(format!(
                    "'{}' 必须是 true 或 false",
                    key
                )));
            }
        }
    }
    if let Some(val) = body.get("cache_control_ttl_rewrite") {
        CacheControlTtlRewrite::parse(val)?;
    }
    if let Some(val) = body.get("request_diagnostics_log_mode") {
        if RequestLogMode::parse(val).is_none() {
            return Err(AppError::BadRequest(
                "request_diagnostics_log_mode 必须是 info 或 debug".into(),
            ));
        }
    }
    if let Some(val) = body.get("message_cache_control_rewrite") {
        MessageCacheControlRewrite::parse_setting(val)?;
    }
    if let Some(val) = body.get("claude_code_context_sanitizer_mode") {
        ClaudeCodeContextSanitizerMode::parse(val)?;
    }
    if let Some(val) = body.get("proxy_client_pool_enabled") {
        if val != "true" && val != "false" {
            return Err(AppError::BadRequest(
                "'proxy_client_pool_enabled' 必须是 true 或 false".into(),
            ));
        }
    }
    if let Some(val) = body.get("fable_weekly_usage_limit_percent") {
        validate_usize_range("fable_weekly_usage_limit_percent", val, 1, 100)?;
    }
    for key in &[
        "intercept_warmup_title_enabled",
        "intercept_warmup_suggestion_enabled",
        "intercept_warmup_haiku_probe_enabled",
        "rewrite_disabled_thinking_enabled",
        "intercept_assistant_prefill_enabled",
        "log_429_request_enabled",
        "log_non_stream_request_enabled",
        "non_stream_probe_cache_enabled",
        "stream_keepalive_enabled",
        "message_body_order_fingerprint_enabled",
        "message_top_field_filter_enabled",
        "fable_sticky_quota_fallback_enabled",
        "session_hello_probe_enabled",
        "session_hello_probe_strict",
        "intercept_cli_bg_status_classifier_identity_injection_enabled",
    ] {
        if let Some(val) = body.get(*key) {
            if val != "true" && val != "false" {
                return Err(AppError::BadRequest(format!(
                    "'{}' 必须是 true 或 false",
                    key
                )));
            }
        }
    }
    if let Some(val) = body.get("rewrite_disabled_thinking_models") {
        validate_model_id_list("rewrite_disabled_thinking_models", val)?;
    }
    if let Some(val) = body.get("intercept_assistant_prefill_models") {
        validate_model_id_list("intercept_assistant_prefill_models", val)?;
    }
    if let Some(val) = body.get("intercept_cli_bg_status_classifier_models") {
        validate_model_id_list("intercept_cli_bg_status_classifier_models", val)?;
    }
    if let Some(val) = body.get("log_429_request_body_limit") {
        validate_usize_range("log_429_request_body_limit", val, 0, 1_048_576)?;
    }
    if let Some(val) = body.get("stream_keepalive_interval_secs") {
        validate_usize_range("stream_keepalive_interval_secs", val, 5, 240)?;
    }
    if let Some(val) = body.get("stream_upstream_idle_timeout_secs") {
        validate_usize_range("stream_upstream_idle_timeout_secs", val, 30, 1800)?;
    }
    if let Some(val) = body.get("native_idle_timeout_secs") {
        let seconds = val.parse::<u64>().map_err(|_| {
            AppError::BadRequest("额外空闲进程回收时间必须是30到3600秒的整数".into())
        })?;
        validate_idle_timeout(seconds)?;
    }
    if let Some(val) = body.get("session_hello_probe_timeout_secs") {
        validate_usize_range("session_hello_probe_timeout_secs", val, 1, 30)?;
    }
    if let Some(val) = body.get("session_hello_probe_success_ttl_secs") {
        validate_usize_range("session_hello_probe_success_ttl_secs", val, 60, 86_400)?;
    }
    if let Some(val) = body.get("session_hello_probe_failure_cooldown_secs") {
        validate_usize_range("session_hello_probe_failure_cooldown_secs", val, 10, 3_600)?;
    }
    if let Some(val) = body.get("intercept_auto_mode_classifier_stage1_mode") {
        AutoModeClassifierMode::parse(val)?;
    }
    if let Some(val) = body.get("intercept_auto_mode_classifier_stage2_mode") {
        AutoModeClassifierMode::parse(val)?;
    }
    if let Some(val) = body.get("intercept_cli_bg_status_classifier_mode") {
        CliBgStatusClassifierMode::parse(val)?;
    }
    if let Some(val) = body.get("bootstrap_model_options_mode") {
        BootstrapModelOptionsMode::parse(val)?;
    }
    if let Some(val) = body.get("bootstrap_additional_model_options") {
        parse_bootstrap_additional_model_options(val)?;
    }
    let v3_config_update = if body.keys().any(|key| key.starts_with("v3_")) {
        let mut merged = state.settings_store.get_all().await?;
        merged.extend(body.clone());
        Some(SchedulingConfig::parse(&merged)?)
    } else {
        None
    };
    state
        .settings_store
        .upsert_many_with_profile(&body, selected_profile)
        .await?;
    if let Some(config) = v3_config_update {
        state.account_svc.apply_scheduling_config(config);
    }

    if selected_profile.is_some()
        || body.contains_key("claude_code_profile_selection_mode")
        || body.contains_key("allowed_claude_code_versions")
        || body.contains_key("blocked_claude_code_versions")
        || body.contains_key("allowed_user_agents")
    {
        state.gateway_svc.reload_access_profile_config().await?;
    }
    if let Some(val) = body.get("proxy_client_pool_enabled") {
        crate::tlsfp::set_request_client_pool_enabled(val == "true");
    }
    if body.contains_key("allow_system_role_models") {
        state.gateway_svc.reload_system_role_models().await?;
    }
    if body.contains_key("passthrough_shell")
        || body.contains_key("passthrough_os_version")
        || body.contains_key("passthrough_working_dir")
    {
        state.gateway_svc.reload_env_passthrough().await?;
    }
    if body.contains_key("cache_control_ttl_rewrite") {
        state.gateway_svc.reload_cache_control_ttl_rewrite().await?;
    }
    if body.contains_key("message_cache_control_rewrite") {
        state
            .gateway_svc
            .reload_message_cache_control_rewrite()
            .await?;
    }
    if body.contains_key("message_body_order_fingerprint_enabled") {
        state
            .gateway_svc
            .reload_message_body_order_fingerprint_enabled()
            .await?;
    }
    if body.contains_key("message_top_field_filter_enabled") {
        state
            .gateway_svc
            .reload_message_top_field_filter_enabled()
            .await?;
    }
    if body.contains_key("fable_sticky_quota_fallback_enabled") {
        state
            .gateway_svc
            .reload_fable_sticky_quota_fallback_enabled()
            .await?;
    }
    if body.contains_key("fable_weekly_usage_limit_percent") {
        state
            .gateway_svc
            .reload_fable_weekly_usage_limit_percent()
            .await?;
    }
    if body.contains_key("claude_code_context_sanitizer_mode") {
        state.gateway_svc.reload_context_sanitizer_config().await?;
    }
    if body.contains_key("intercept_warmup_title_enabled")
        || body.contains_key("intercept_warmup_suggestion_enabled")
        || body.contains_key("intercept_warmup_haiku_probe_enabled")
        || body.contains_key("intercept_auto_mode_classifier_stage1_mode")
        || body.contains_key("intercept_auto_mode_classifier_stage2_mode")
    {
        state.gateway_svc.reload_warmup_intercept_config().await?;
    }
    if body.contains_key("intercept_cli_bg_status_classifier_mode")
        || body.contains_key("intercept_cli_bg_status_classifier_models")
        || body.contains_key("intercept_cli_bg_status_classifier_identity_injection_enabled")
    {
        state
            .gateway_svc
            .reload_cli_bg_status_classifier_config()
            .await?;
    }
    if body.contains_key("rewrite_disabled_thinking_enabled")
        || body.contains_key("rewrite_disabled_thinking_models")
    {
        state.gateway_svc.reload_disabled_thinking_rewrite().await?;
    }
    if body.contains_key("intercept_assistant_prefill_enabled")
        || body.contains_key("intercept_assistant_prefill_models")
    {
        state
            .gateway_svc
            .reload_assistant_prefill_intercept_config()
            .await?;
    }
    if body.contains_key("request_diagnostics_log_mode") {
        state.gateway_svc.reload_request_log_mode().await?;
    }
    if body.contains_key("log_429_request_enabled")
        || body.contains_key("log_non_stream_request_enabled")
        || body.contains_key("log_429_request_body_limit")
    {
        state
            .gateway_svc
            .reload_rate_limit_request_log_config()
            .await?;
    }
    if body.contains_key("non_stream_probe_cache_enabled") {
        state
            .gateway_svc
            .reload_non_stream_probe_cache_config()
            .await?;
    }
    if body.contains_key("stream_keepalive_enabled")
        || body.contains_key("stream_keepalive_interval_secs")
        || body.contains_key("stream_upstream_idle_timeout_secs")
    {
        state.gateway_svc.reload_stream_stability_config().await?;
    }
    if body.contains_key("bootstrap_model_options_mode")
        || body.contains_key("bootstrap_additional_model_options")
    {
        state.gateway_svc.reload_bootstrap_profile_config().await?;
    }
    if body.contains_key("session_hello_probe_enabled")
        || body.contains_key("session_hello_probe_strict")
        || body.contains_key("session_hello_probe_timeout_secs")
        || body.contains_key("session_hello_probe_success_ttl_secs")
        || body.contains_key("session_hello_probe_failure_cooldown_secs")
    {
        state
            .gateway_svc
            .reload_session_hello_probe_config()
            .await?;
    }
    if body
        .keys()
        .any(|key| key.starts_with("session_policy_block_"))
    {
        state
            .gateway_svc
            .reload_session_policy_block_config()
            .await?;
    }
    // 通知 AccountService 刷新缓存
    if body.contains_key("native_idle_timeout_secs") {
        state.gateway_svc.reload_native_idle_timeout().await?;
    }
    Ok(Json(serde_json::json!({"ok": true})))
}

/// 校验逗号分隔的模型 ID 列表。
///
/// @param key 设置项 key,用于错误提示。
/// @param raw 原始逗号分隔字符串。
/// @return 校验通过返回 `Ok(())`,否则返回业务错误。
fn validate_model_id_list(key: &str, raw: &str) -> Result<(), AppError> {
    for item in raw.split(',').map(str::trim).filter(|s| !s.is_empty()) {
        if !item
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || matches!(c, '-' | '_' | '.' | ':'))
        {
            return Err(AppError::BadRequest(format!(
                "'{}' 包含非法模型 ID: {}",
                key, item
            )));
        }
    }
    Ok(())
}

/// 校验 usize 数字范围。
///
/// @param key 设置项 key,用于错误提示。
/// @param raw 原始字符串。
/// @param min 允许的最小值。
/// @param max 允许的最大值。
/// @return 校验通过返回 `Ok(())`,否则返回业务错误。
fn validate_usize_range(key: &str, raw: &str, min: usize, max: usize) -> Result<(), AppError> {
    match raw.trim().parse::<usize>() {
        Ok(value) if value >= min && value <= max => Ok(()),
        _ => Err(AppError::BadRequest(format!(
            "'{}' 必须是 {} 到 {} 之间的整数",
            key, min, max
        ))),
    }
}

/// 显式管理员重试可允许唤醒；旧环境就绪通知缺省仅检查运行绑定。
#[derive(Deserialize, Default)]
struct NativePreparationQuery {
    #[serde(default)]
    wake: bool,
    #[serde(default)]
    cancel: bool,
}

/// 将账号准备入队，调用方不等待本地加载。
/// @param state 已鉴权服务。@param id 账号。@param query 明确唤醒选择。
/// @return 入队确认及当前安全状态。
async fn request_native_preparation(
    State(state): State<AppState>,
    Path(id): Path<i64>,
    Query(query): Query<NativePreparationQuery>,
) -> Result<Json<serde_json::Value>, AppError> {
    state.account_svc.get_account(id).await?;
    if query.wake && query.cancel {
        return Err(AppError::BadRequest("准备与取消不能同时请求".into()));
    }
    if query.cancel {
        state.account_svc.notify_native_change(id, true);
    } else if query.wake {
        state.account_svc.request_native_wake(id);
    } else {
        state.account_svc.notify_native_change(id, false);
    }
    Ok(Json(
        serde_json::json!({"queued":true,"preparation":state.gateway_svc.native_preparation_status(id)}),
    ))
}

/// 查询独立的原生进程准备状态。
/// @param state 已通过管理鉴权的共享服务。
/// @param id 当前账号 ID。
/// @return 真实准备阶段的受控摘要。
async fn native_preparation_status(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<serde_json::Value>, AppError> {
    state.account_svc.get_account(id).await?;
    Ok(Json(state.gateway_svc.inspect_native_preparation(id).await))
}

/// 环境列表批量读取最近检查状态，避免逐账号串行访问 sender。
/// @param state 已通过管理鉴权的共享服务。
/// @return 安全状态快照数组。
async fn native_preparation_snapshots(
    State(state): State<AppState>,
) -> Result<Json<Vec<serde_json::Value>>, AppError> {
    let snapshots = state.gateway_svc.native_preparation_snapshots();
    let accounts = state.account_svc.list_accounts().await?;
    Ok(Json(
        accounts
            .into_iter()
            .map(|account| {
                let mut value = snapshots
                    .iter()
                    .find(|item| item["account_id"] == account.id)
                    .cloned()
                    .unwrap_or_else(|| json!({"account_id":account.id,"state":"unprepared"}));
                value["request_backend"] = json!(account.request_backend);
                value
            })
            .collect(),
    ))
}

/// 分页查询已鉴权业务请求的白名单诊断。
/// @param state 管理端共享状态。
/// @param query 时间、账号、关联 ID 和结果筛选。
/// @return 诊断列表及采集健康状态。
async fn list_request_diagnostics(
    State(state): State<AppState>,
    Query(query): Query<DiagnosticQuery>,
) -> Result<Json<DiagnosticPage>, AppError> {
    let store = state
        .gateway_svc
        .diagnostics_store()
        .ok_or_else(|| AppError::ServiceUnavailable("请求诊断尚未装配".into()))?;
    Ok(Json(store.list(query).await?))
}

/// 读取单次请求的实际发送与重试链。
/// @param state 管理端共享状态。
/// @param request_id 诊断列表中的内部请求 UUID。
/// @return 请求摘要及各次尝试。
async fn request_diagnostic_detail(
    State(state): State<AppState>,
    Path(request_id): Path<String>,
) -> Result<Json<DiagnosticDetail>, AppError> {
    let store = state
        .gateway_svc
        .diagnostics_store()
        .ok_or_else(|| AppError::ServiceUnavailable("请求诊断尚未装配".into()))?;
    Ok(Json(store.detail(&request_id).await?))
}

/// 读取属于指定请求的私有组装快照。
/// @param state 管理共享状态。
/// @param request_id 已保存的请求 UUID。
/// @param attempt_id 属于本请求的尝试 UUID。
/// @return 禁止缓存的管理员快照。
async fn request_native_capture(
    State(state): State<AppState>,
    Path((request_id, attempt_id)): Path<(String, String)>,
) -> Result<Response, AppError> {
    let store = state
        .gateway_svc
        .diagnostics_store()
        .ok_or_else(|| AppError::ServiceUnavailable("请求诊断尚未装配".into()))?;
    let detail = store.detail(&request_id).await?;
    if let Some(rejected) = detail
        .request
        .native_rejection
        .as_ref()
        .filter(|rejected| rejected.capture_id == attempt_id)
    {
        let value = if detail.request.log_mode == Some(RequestLogMode::Info) {
            serde_json::json!({"state":"summary", "message":"本次请求仅保存摘要"})
        } else if rejected.capture_status == "disabled" {
            serde_json::json!({"state":"disabled", "message":"本次请求发生时内容采集已关闭"})
        } else if rejected.capture_id == detail.request.request_id {
            if let Some(directory) = store.rejected_ingress_dir() {
                native_capture::read_gateway_rejection(directory, &rejected.capture_id).await
            } else {
                serde_json::json!({"state":"missing", "message":"本地入站快照不可用"})
            }
        } else {
            let account_id = detail.request.account_id.ok_or(AppError::NotFound)?;
            runtime_bridge::native_capture(account_id, &rejected.capture_id).await?
        };
        let mut response = Json(value).into_response();
        response
            .headers_mut()
            .insert("cache-control", HeaderValue::from_static("no-store"));
        return Ok(response);
    }
    let attempt = detail
        .attempts
        .iter()
        .find(|attempt| attempt.attempt_id == attempt_id)
        .ok_or(AppError::NotFound)?;
    let value = if attempt.capture_status.as_deref() == Some("disabled") {
        serde_json::json!({"state":"disabled", "message":"本次请求发生时账号内容采集已关闭，设置对后续请求生效"})
    } else if attempt.log_mode == Some(RequestLogMode::Info) {
        serde_json::json!({"state":"summary", "message":"本次请求仅保存摘要"})
    } else if attempt.context.as_ref().and_then(|c| c.platform.as_deref()) == Some("antigravity") {
        runtime_bridge::agy_capture(attempt.account_id, &attempt.attempt_id).await?
    } else if matches!(
        attempt.profile_selection.as_str(),
        "native280_cc_prepared" | "native293_cc_prepared"
    ) {
        runtime_bridge::native_capture(attempt.account_id, &attempt.attempt_id).await?
    } else {
        serde_json::json!({"state":"unsupported", "message":"此尝试使用其他转发方式"})
    };
    let mut response = Json(value).into_response();
    response
        .headers_mut()
        .insert("cache-control", HeaderValue::from_static("no-store"));
    Ok(response)
}

/// 获取最近 50 条峰值预热调用记录,按时间倒序。
async fn get_prime_logs(
    State(state): State<AppState>,
) -> Result<Json<serde_json::Value>, AppError> {
    let logs = state.prime_log_store.list_recent(50).await?;
    Ok(Json(serde_json::json!(logs)))
}

#[cfg(test)]
mod tests {
    use super::{
        ClaudeCodeContextSanitizerMode, CliBgStatusClassifierMode, CliIdentityImport,
        DEFAULT_INTERCEPT_CLI_BG_STATUS_CLASSIFIER_MODELS, MAX_OAUTH_CREDENTIAL_VALIDITY_SECONDS,
        MIN_OAUTH_CREDENTIAL_VALIDITY_SECONDS, build_router, hello_get, hello_head,
        normalize_oauth_credential_validity_seconds, validate_model_id_list,
    };
    use crate::config::{AdminConfig, Config, DatabaseConfig, ServerConfig};
    use crate::model::account::{Account, CanonicalEnvData, CanonicalPromptEnvData};
    use crate::service::account::{AccountSelectionContext, AccountService};
    use crate::service::gateway::GatewayService;
    use crate::service::oauth::TokenTester;
    use crate::service::oauth_flow::OAuthFlowService;
    use crate::service::rewriter::Rewriter;
    use crate::service::telemetry::TelemetryService;
    use crate::service::v3_scheduling::{RequestPhase, SchedulingConfig, V3Scheduler, now_ms};
    use crate::service::version_profile::ClaudeCodeProfileSelectionMode;
    use crate::store::account_store::AccountStore;
    use crate::store::diagnostics_store::DiagnosticsStore;
    use crate::store::memory::MemoryStore;
    use crate::store::prime_log_store::PrimeLogStore;
    use crate::store::scheduling_store::SchedulingStore;
    use crate::store::settings_store::OBSOLETE_SCHEDULING_KEYS;
    use crate::store::settings_store::SettingsStore;
    use crate::store::token_store::TokenStore;
    use crate::store::usage_store::UsageStore;
    use axum::Router;
    use axum::body::{self, Body};
    use axum::http::{Method, Request, StatusCode, header};
    use chrono::{Duration as ChronoDuration, Utc};
    use serde_json::{Value, json};
    use sqlx::AnyPool;
    use sqlx::any::AnyPoolOptions;
    use std::collections::HashMap;
    use std::sync::Arc;
    use std::time::Duration;
    use tower::ServiceExt;
    use uuid::Uuid;

    async fn test_router_with_gateway() -> (Router, Arc<GatewayService>) {
        let (router, gateway, _, _) = test_router_with_gateway_and_settings().await;
        (router, gateway)
    }

    /// 构造可校验历史设置与 Gateway 热刷新的管理路由。
    /// @return 管理路由、网关、设置存储及隔离内存连接池。
    async fn test_router_with_gateway_and_settings()
    -> (Router, Arc<GatewayService>, Arc<SettingsStore>, AnyPool) {
        let (router, gateway, settings, pool, _) = test_router_with_scheduling(false).await;
        (router, gateway, settings, pool)
    }

    /// 在隔离数据库中按需装配新调度，保留所有旧路由测试的原行为。
    /// @param enabled 是否启用 v3 调度。
    /// @return 路由、网关、设置、池与账号服务。
    async fn test_router_with_scheduling(
        enabled: bool,
    ) -> (
        Router,
        Arc<GatewayService>,
        Arc<SettingsStore>,
        AnyPool,
        Arc<AccountService>,
    ) {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .expect("连接测试数据库");
        crate::store::db::migrate(&pool, "sqlite")
            .await
            .expect("初始化测试数据库");
        let account_store = Arc::new(AccountStore::new(pool.clone(), "sqlite".into()));
        let settings_store = Arc::new(SettingsStore::new(pool.clone()));
        let cache = Arc::new(MemoryStore::new());
        let mut account_service =
            AccountService::new(account_store.clone(), cache.clone(), settings_store.clone());
        if enabled {
            let scheduler = Arc::new(V3Scheduler::new(Arc::new(SchedulingStore::new(
                pool.clone(),
            ))));
            scheduler.reload(&settings_store).await.unwrap();
            account_service = account_service.with_scheduler(scheduler);
        }
        let account_svc = Arc::new(account_service);
        let telemetry_svc = Arc::new(TelemetryService::new(account_store, account_svc.clone()));
        let gateway_svc = Arc::new(
            GatewayService::new(
                account_svc.clone(),
                Arc::new(Rewriter::new()),
                telemetry_svc.clone(),
                settings_store.clone(),
                cache,
                Arc::new(UsageStore::new(pool.clone())),
            )
            .with_diagnostics(Arc::new(DiagnosticsStore::new(pool.clone()))),
        );
        let cfg = Config {
            server: ServerConfig {
                port: 0,
                host: "127.0.0.1".into(),
                tls_cert: None,
                tls_key: None,
            },
            database: DatabaseConfig {
                driver: Some("sqlite".into()),
                dsn: Some("sqlite::memory:".into()),
                host: String::new(),
                port: 0,
                user: String::new(),
                password: String::new(),
                dbname: String::new(),
            },
            redis: None,
            admin: AdminConfig {
                password: "admin".into(),
            },
            log_level: "info".into(),
            usage_poll_interval: Duration::from_secs(300),
        };

        let router = build_router(
            &cfg,
            gateway_svc.clone(),
            account_svc.clone(),
            Arc::new(TokenTester::new()),
            Arc::new(TokenStore::new(pool.clone(), "sqlite".into())),
            settings_store.clone(),
            Arc::new(PrimeLogStore::new(pool.clone())),
            Arc::new(OAuthFlowService::new()),
            telemetry_svc,
        );
        (router, gateway_svc, settings_store, pool, account_svc)
    }

    /// 诊断查询只对管理员开放，并支持关联 ID 反查和受控参数错误。
    #[tokio::test]
    async fn diagnostics_routes_require_admin_and_expose_committed_requests() {
        let (app, gateway) = test_router_with_gateway().await;
        let response = gateway
            .handle_request(
                Request::builder()
                    .uri("/v1/messages")
                    .header("user-agent", "synthetic-denied-client")
                    .body(Body::empty())
                    .unwrap(),
                None,
            )
            .await;
        let id = response.headers()["x-cc2api-request-id"]
            .to_str()
            .unwrap()
            .to_owned();
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        let _ = body::to_bytes(response.into_body(), 4096).await.unwrap();
        gateway.diagnostics_store().unwrap().flush().await.unwrap();
        for path in [
            "/admin/request-diagnostics".to_owned(),
            format!("/admin/request-diagnostics/{id}"),
        ] {
            let denied = app
                .clone()
                .oneshot(Request::builder().uri(&path).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);
            let accepted = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri(&path)
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(accepted.status(), StatusCode::OK);
            let value: serde_json::Value =
                serde_json::from_slice(&body::to_bytes(accepted.into_body(), 65536).await.unwrap())
                    .unwrap();
            if path.ends_with(&id) {
                assert_eq!(value["request"]["outcome"], "local_rejected");
                assert_eq!(value["attempts"], serde_json::json!([]));
            } else {
                assert_eq!(value["total"], 1);
            }
        }
        let capture_path = format!(
            "/admin/request-diagnostics/{id}/captures/{}",
            Uuid::new_v4()
        );
        let denied = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri(&capture_path)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);
        for (path, expected) in [
            (capture_path, StatusCode::NOT_FOUND),
            (
                format!("/admin/request-diagnostics?correlation_id={id}"),
                StatusCode::OK,
            ),
            (
                "/admin/request-diagnostics?page=0".into(),
                StatusCode::BAD_REQUEST,
            ),
            (
                "/admin/request-diagnostics?since=bad".into(),
                StatusCode::BAD_REQUEST,
            ),
            (
                "/admin/request-diagnostics/missing".into(),
                StatusCode::NOT_FOUND,
            ),
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri(path)
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), expected);
        }
    }

    /// 管理封禁列表沿用鉴权，设置校验失败保持原值，解除保留历史。
    #[tokio::test]
    async fn session_policy_block_admin_contract() {
        let (app, _, settings, pool) = test_router_with_gateway_and_settings().await;
        let page = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/session-blocks")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(page.status(), StatusCode::OK);
        assert!(
            page.headers()[header::CONTENT_TYPE]
                .to_str()
                .unwrap()
                .contains("text/html")
        );
        let denied = app
            .clone()
            .oneshot(
                Request::builder()
                    .uri("/admin/session-policy-blocks")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);
        let (status, value) =
            account_admin_json(&app, Method::GET, "/admin/settings", json!({})).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["session_policy_block_duration_minutes"], "1440");
        for raw in ["0", "-1", "1.5", "", "9223372036854775807"] {
            let (status, _) = account_admin_json(
                &app,
                Method::PUT,
                "/admin/settings",
                json!({"session_policy_block_duration_minutes":raw}),
            )
            .await;
            assert_eq!(status, StatusCode::BAD_REQUEST);
        }
        assert_eq!(
            settings
                .get_value("session_policy_block_duration_minutes", "missing")
                .await
                .unwrap(),
            "1440"
        );
        let (status, _) = account_admin_json(
            &app,
            Method::PUT,
            "/admin/settings",
            json!({"session_policy_block_duration_minutes":"60"}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        let id = Uuid::new_v4().to_string();
        let key = "a".repeat(64);
        let now = Utc::now().timestamp_millis();
        sqlx::query("INSERT INTO session_policy_block_keys(session_key) VALUES($1)")
            .bind(&key)
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("INSERT INTO session_policy_blocks(id,session_key,api_token_id,account_id,model,reason,blocked_at_ms,expires_at_ms) VALUES($1,$2,21,7,'synthetic-model','usage_policy',$3,$4)")
            .bind(&id).bind(&key).bind(now).bind(now+86_400_000).execute(&pool).await.unwrap();
        let (status, page) = account_admin_json(
            &app,
            Method::GET,
            "/admin/session-policy-blocks?state=active&page=1&page_size=20",
            json!({}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(page["total"], 1);
        assert_eq!(page["items"][0]["session_key"], key);
        for query in [
            "state=unknown",
            "page=0",
            "page_size=101",
            "session_prefix=%25",
            "page=9223372036854775807",
        ] {
            let (status, _) = account_admin_json(
                &app,
                Method::GET,
                &format!("/admin/session-policy-blocks?{query}"),
                json!({}),
            )
            .await;
            assert_eq!(status, StatusCode::BAD_REQUEST);
        }
        let (status, released) = account_admin_json(
            &app,
            Method::POST,
            &format!("/admin/session-policy-blocks/{id}/release"),
            json!({}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(released["state"], "released");
        let (_, page) = account_admin_json(
            &app,
            Method::GET,
            "/admin/session-policy-blocks?state=released",
            json!({}),
        )
        .await;
        assert_eq!(page["total"], 1);
    }

    /// 授权从目录解析连接并保护未完成会话，公开回执不泄露账密。
    #[tokio::test]
    async fn oauth_directory_selection_validates_revision_and_registers_reference() {
        let (app, _, _, pool, _) = test_router_with_scheduling(false).await;
        let (status, created) = account_admin_json(
            &app,
            Method::POST,
            "/admin/proxies",
            json!({
                "name":"合成授权线路", "protocol":"socks5", "host":"synthetic.invalid", "port":1080,
                "username":"synthetic-user", "password":"synthetic-secret"
            }),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        let id = created["id"].as_str().unwrap();
        let revision: String = sqlx::query_scalar("SELECT revision FROM proxy_routes WHERE id=$1")
            .bind(id)
            .fetch_one(&pool)
            .await
            .unwrap();
        for path in [
            "/admin/oauth/generate-auth-url",
            "/admin/oauth/generate-setup-token-url",
        ] {
            let (status, _) = account_admin_json(
                &app,
                Method::POST,
                path,
                json!({"proxy_id":id,"proxy_revision":"stale"}),
            )
            .await;
            assert_eq!(status, StatusCode::BAD_REQUEST);
            let (status, result) = account_admin_json(
                &app,
                Method::POST,
                path,
                json!({"proxy_id":id,"proxy_revision":revision}),
            )
            .await;
            assert_eq!(status, StatusCode::OK);
            assert!(result["session_id"].is_string());
            assert!(!result.to_string().contains("synthetic-secret"));
        }
        let (_, list) = account_admin_json(&app, Method::GET, "/admin/proxies", json!({})).await;
        assert_eq!(list["data"][0]["users"].as_array().unwrap().len(), 2);
        assert_eq!(list["data"][0]["users"][0]["kind"], "authorization");
        assert!(!list.to_string().contains("synthetic-secret"));
        let (status, _) = account_admin_json(
            &app,
            Method::POST,
            "/admin/oauth/generate-auth-url",
            json!({"proxy_id":id,"proxy_url":"http://other.invalid:80"}),
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
    }

    /// 调用管理 JSON 接口并读取受限大小的返回值。
    /// @param app 测试路由。
    /// @param method HTTP 方法。
    /// @param path 管理接口路径。
    /// @param payload 合成请求载荷。
    /// @return 状态码和 JSON；反序列化拒绝可能返回非 JSON，此时以 null 表示。
    async fn account_admin_json(
        app: &Router,
        method: Method,
        path: &str,
        payload: Value,
    ) -> (StatusCode, Value) {
        let response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(method)
                    .uri(path)
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(payload.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status();
        let bytes = body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        (
            status,
            serde_json::from_slice(&bytes).unwrap_or(Value::Null),
        )
    }

    /// 忙碌账号保留旧连接，空闲后后台真实同步；公开响应不包含认证字段。
    #[tokio::test]
    async fn used_proxy_edit_queues_until_idle_and_synchronizes() {
        let (app, _, _, pool, accounts) = test_router_with_scheduling(true).await;
        let (_,proxy)=account_admin_json(&app,Method::POST,"/admin/proxies",json!({"name":"同步线路","protocol":"http","host":"old.test","port":8080,"username":"demo","password":"synthetic-private"})).await;
        let proxy_id = proxy["id"].as_str().unwrap();
        let revision: String = sqlx::query_scalar("SELECT revision FROM proxy_routes WHERE id=$1")
            .bind(proxy_id)
            .fetch_one(&pool)
            .await
            .unwrap();
        let (status,created)=account_admin_json(&app,Method::POST,"/admin/accounts",json!({"name":"保持名称","email":"sync@example.invalid","auth_type":"oauth","access_token":"synthetic-access","refresh_token":"synthetic-refresh","expires_at":(Utc::now()+ChronoDuration::hours(2)).timestamp_millis(),"proxy_id":proxy_id,"proxy_revision":revision,"concurrency":2})).await;
        assert_eq!(status, StatusCode::CREATED, "{created}");
        let id = created["id"].as_i64().unwrap();
        let queue = accounts.get_or_create_queue(id, 2).await;
        let active = queue.acquire(Duration::from_secs(1), 1).await.unwrap();
        let (status,saved)=account_admin_json(&app,Method::PUT,&format!("/admin/proxies/{proxy_id}"),json!({"name":"同步线路","protocol":"socks5","host":"new.test","port":1080,"revision":revision})).await;
        assert_eq!(status, StatusCode::OK, "{saved}");
        assert_eq!(saved["sync_pending"], true);
        let (_, list) = account_admin_json(&app, Method::GET, "/admin/proxies", json!({})).await;
        assert_eq!(list["data"][0]["users"].as_array().unwrap().len(), 1);
        assert_eq!(list["data"][0]["sync_pending"], true);
        assert!(!list.to_string().contains("synthetic-private"));
        assert!(
            accounts
                .get_account(id)
                .await
                .unwrap()
                .proxy_url
                .contains("old.test")
        );
        drop(active);
        tokio::time::timeout(Duration::from_secs(10), async {
            loop {
                let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM proxy_route_sync")
                    .fetch_one(&pool)
                    .await
                    .unwrap();
                if count == 0 {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        })
        .await
        .unwrap();
        let account = accounts.get_account(id).await.unwrap();
        assert!(account.proxy_url.contains("new.test:1080"));
        assert_eq!(account.name, "保持名称");
        assert_eq!(account.access_token, "synthetic-access");
    }

    /// bench 现有创建载荷省略新字段时继续成功，后续局部更新不覆盖已保存限制。
    /// @return 无；旧 API 载荷、默认值或局部更新兼容性异常时测试失败。
    #[tokio::test]
    async fn usage_limits_bench_creation_and_partial_update_are_compatible() {
        let (app, _) = test_router_with_gateway().await;
        let payload = json!({
            "name": "synthetic-bench", "email": "bench-created@example.invalid",
            "auth_type": "oauth", "access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
            "expires_at": (Utc::now() + ChronoDuration::hours(2)).timestamp_millis(),
            "proxy_url": "", "account_uuid": "synthetic-account", "organization_uuid": "synthetic-org",
            "subscription_type": "max", "allow_fast_mode": false, "billing_mode": "rewrite",
            "upstream_session_pool_enabled": true, "upstream_session_pool_size": 4,
            "upstream_session_refresh_policy": "owner_only", "concurrency": 4, "rpm_limit": 50,
        });
        let (status, account) =
            account_admin_json(&app, Method::POST, "/admin/accounts", payload).await;
        assert_eq!(status, StatusCode::CREATED);
        assert_eq!(account["five_hour_usage_limit_percent"], 0);
        assert_eq!(account["seven_day_usage_limit_percent"], 0);
        for (key, value) in [
            ("concurrency", 4),
            ("rpm_limit", 50),
            ("upstream_session_pool_size", 4),
        ] {
            assert_eq!(account[key], value);
        }
        assert_eq!(account["billing_mode"], "rewrite");
        assert_eq!(account["upstream_session_refresh_policy"], "owner_only");
        let path = format!("/admin/accounts/{}", account["id"].as_i64().unwrap());
        for payload in [
            json!({"five_hour_usage_limit_percent": 80, "seven_day_usage_limit_percent": 60}),
            json!({"proxy_url": "", "name": "bench-updated"}),
        ] {
            let (status, updated) = account_admin_json(&app, Method::PUT, &path, payload).await;
            assert_eq!(status, StatusCode::OK);
            assert_eq!(updated["five_hour_usage_limit_percent"], 80);
            assert_eq!(updated["seven_day_usage_limit_percent"], 60);
            assert_eq!(updated["rpm_limit"], 50);
            assert_eq!(updated["concurrency"], 4);
        }
        let (status, updated) = account_admin_json(
            &app,
            Method::PUT,
            &path,
            json!({"five_hour_usage_limit_percent": 0}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(updated["five_hour_usage_limit_percent"], 0);
        assert_eq!(updated["seven_day_usage_limit_percent"], 60);
        let (status, listed) = account_admin_json(
            &app,
            Method::GET,
            "/admin/accounts?page=1&page_size=100",
            Value::Null,
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(listed["data"][0]["seven_day_usage_limit_percent"], 60);
        for (status, payload, expected) in [
            (
                "disabled",
                json!({"five_hour_usage_limit_percent": 70}),
                (70, 60),
            ),
            (
                "active",
                json!({"seven_day_usage_limit_percent": 50}),
                (70, 50),
            ),
        ] {
            let mut update = payload;
            update["status"] = json!(status);
            let (code, updated) = account_admin_json(&app, Method::PUT, &path, update).await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(updated["status"], status);
            assert_eq!(updated["five_hour_usage_limit_percent"], expected.0);
            assert_eq!(updated["seven_day_usage_limit_percent"], expected.1);
            assert_eq!(updated["rpm_limit"], 50);
        }
    }

    /// 活动 API 与 CLI 不妨碍普通配置保存，真正身份修改仍须排空且不能覆盖轮换凭据。
    #[tokio::test]
    async fn account_options_hot_update_preserves_active_api_cli_and_credentials() {
        let (app, _, _, pool, accounts) = test_router_with_scheduling(true).await;
        let (status, created) = account_admin_json(&app, Method::POST, "/admin/accounts", json!({
            "name":"hot-options", "email":"hot-options@example.invalid", "auth_type":"oauth",
            "access_token":"synthetic-old-access", "refresh_token":"synthetic-old-refresh",
            "expires_at":(Utc::now() + ChronoDuration::hours(2)).timestamp_millis(), "concurrency":3
        })).await;
        assert_eq!(status, StatusCode::CREATED);
        let id = created["id"].as_i64().unwrap();
        let path = format!("/admin/accounts/{id}");
        let queue = accounts.get_or_create_queue(id, 3).await;
        let active = queue.acquire(Duration::from_secs(1), 2).await.unwrap();
        let cli = queue
            .runtime_gate
            .prepare_shared_cli("run:synthetic-hot-edit")
            .unwrap();
        sqlx::query("UPDATE accounts SET access_token='synthetic-new-access', refresh_token='synthetic-new-refresh', status='error' WHERE id=$1")
            .bind(id).execute(&pool).await.unwrap();
        let (code, updated) = account_admin_json(
            &app,
            Method::PUT,
            &path,
            json!({
                "concurrency":1,"rpm_limit":17,"priority":23,"name":"hot-updated",
                "five_hour_usage_limit_percent":81,"auto_telemetry":true,
                "subscription_type":"ultra", "rate_limit_tier":null
            }),
        )
        .await;
        assert_eq!(code, StatusCode::OK, "{updated}");
        assert_eq!(updated["rpm_limit"], 17);
        assert_eq!(updated["priority"], 23);
        assert_eq!(updated["concurrency"], 1);
        assert_eq!(queue.active_request_count(), 1);
        assert_eq!(queue.max_units(), 2);
        assert_eq!(accounts.get_or_create_queue(id, 3).await.max_units(), 2);
        let saved = accounts.get_account(id).await.unwrap();
        assert_eq!(saved.access_token, "synthetic-new-access");
        assert_eq!(saved.refresh_token, "synthetic-new-refresh");
        assert_eq!(saved.status.to_string(), "error");
        assert_eq!(saved.subscription_type.as_deref(), Some("ultra"));
        assert!(saved.rate_limit_tier.is_none());
        for protected in [
            json!({"proxy_url":"http://synthetic.invalid:1"}),
            json!({"access_token":"must-not-write"}),
        ] {
            let (code, _) = account_admin_json(&app, Method::PUT, &path, protected).await;
            assert!(!code.is_success());
        }
        // 维护尝试失败不能释放已有 CLI 租约，也不能取消 API。
        assert_eq!(queue.active_request_count(), 1);
        queue
            .runtime_gate
            .update(&cli.owner, &cli.generation, "release")
            .unwrap();
        let (code, _) = account_admin_json(
            &app,
            Method::PUT,
            &path,
            json!({"proxy_url":"http://synthetic.invalid:1"}),
        )
        .await;
        assert_eq!(code, StatusCode::BAD_REQUEST);
        drop(active);
        for (key, value) in [
            ("rpm_limit", json!(-1)),
            ("priority", json!(0)),
            ("concurrency", json!(i64::MAX)),
        ] {
            let mut update = json!({"name":"must-not-write"});
            update[key] = value;
            assert_eq!(
                account_admin_json(&app, Method::PUT, &path, update).await.0,
                StatusCode::BAD_REQUEST
            );
        }
        assert_eq!(accounts.get_account(id).await.unwrap().name, "hot-updated");
    }

    /// 管理接口严格拒绝错误类型和范围，不能静默忽略或部分写入。
    /// @return 无；非法控制线被接受、账号被额外创建或原配置变化时测试失败。
    #[tokio::test]
    async fn usage_limits_admin_rejects_invalid_values_before_any_write() {
        let (app, _) = test_router_with_gateway().await;
        let (status, account) = account_admin_json(&app, Method::POST, "/admin/accounts", json!({
            "name": "original", "email": "limits-validation@example.invalid", "setup_token": "synthetic-setup",
            "five_hour_usage_limit_percent": 80, "seven_day_usage_limit_percent": 60,
        })).await;
        assert_eq!(status, StatusCode::CREATED);
        let path = format!("/admin/accounts/{}", account["id"].as_i64().unwrap());
        for key in [
            "five_hour_usage_limit_percent",
            "seven_day_usage_limit_percent",
        ] {
            for value in [
                json!(-1),
                json!(101),
                json!(50.5),
                json!("80"),
                json!(true),
                Value::Null,
                json!(i64::MAX),
            ] {
                let mut update = json!({"name": "must-not-save", "status": "disabled"});
                update[key] = value.clone();
                let (status, _) = account_admin_json(&app, Method::PUT, &path, update).await;
                assert_eq!(status, StatusCode::BAD_REQUEST);
                let mut create = json!({"email": "invalid-create@example.invalid", "setup_token": "synthetic-setup"});
                create[key] = value;
                assert!(
                    !account_admin_json(&app, Method::POST, "/admin/accounts", create)
                        .await
                        .0
                        .is_success()
                );
            }
        }
        let (_, listed) =
            account_admin_json(&app, Method::GET, "/admin/accounts", Value::Null).await;
        assert_eq!(listed["total"], 1);
        let unchanged = &listed["data"][0];
        assert_eq!(unchanged["name"], "original");
        assert_eq!(unchanged["status"], "active");
        assert_eq!(unchanged["five_hour_usage_limit_percent"], 80);
        assert_eq!(unchanged["seven_day_usage_limit_percent"], 60);
    }

    /// 接单热更新可在真实活动槽位中完成，账号健康与环境配置保持独立。
    /// @return 无。
    #[tokio::test]
    async fn account_work_route_changes_admission_while_runtime_is_active() {
        let (app, _, _, _, accounts) = test_router_with_scheduling(true).await;
        let (status, created) = account_admin_json(&app, Method::POST, "/admin/accounts",
            json!({"email":"work-route@example.invalid","setup_token":"synthetic-work","auto_telemetry":false})).await;
        assert!(status.is_success());
        let id = created["id"].as_i64().unwrap();
        let queue = accounts.get_or_create_queue(id, 3).await;
        let held = queue
            .acquire(Duration::from_secs(1), 2)
            .await
            .unwrap()
            .with_work_admission(accounts.work_controls.admit(id).await.unwrap());
        let (status, saved) = account_admin_json(
            &app,
            Method::PUT,
            &format!("/admin/accounts/{id}/work-control"),
            json!({"api_accepting":false,"expected_revision":0}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(saved["admitted_requests"], 1);
        assert_eq!(saved["work_enabled"], true);
        assert!(accounts.work_controls.admit(id).await.is_err());
        let (_, account) = account_admin_json(
            &app,
            Method::GET,
            &format!("/admin/accounts/{id}"),
            Value::Null,
        )
        .await;
        assert_eq!(account["status"], "active");
        assert_eq!(account["setup_token"], "synthetic-work");
        assert_eq!(account["work_control"]["api_accepting"], false);
        assert_eq!(queue.runtime_gate.snapshot()["active"], 1);
        drop(held);
        assert_eq!(
            accounts
                .work_controls
                .snapshot(id)
                .await
                .unwrap()
                .admitted_requests,
            0
        );
    }

    /// 账号列表随刷新返回本地用量，不把读取转换成主动额度查询。
    /// @return 无；窗口字段缺失、读取失败或主动查询污染时间时测试失败。
    #[tokio::test]
    async fn accounts_list_exposes_both_usage_windows_without_triggering_usage_refresh() {
        let (app, _) = test_router_with_gateway().await;
        let response=app.clone().oneshot(Request::builder().method(Method::POST).uri("/admin/accounts")
            .header(header::AUTHORIZATION,"Bearer admin").header(header::CONTENT_TYPE,"application/json")
            .body(Body::from(serde_json::json!({"email":"usage@example.invalid","setup_token":"synthetic-setup","auto_telemetry":false,"auto_poll_usage":false}).to_string())).unwrap()).await.unwrap();
        assert!(response.status().is_success());
        for _ in 0..2 {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri("/admin/accounts")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let value: serde_json::Value = serde_json::from_slice(
                &body::to_bytes(response.into_body(), 1024 * 1024)
                    .await
                    .unwrap(),
            )
            .unwrap();
            let usage = &value["data"][0]["request_usage"];
            assert!(usage["recorded_since"].is_string());
            for key in ["five_hour", "seven_day"] {
                assert_eq!(usage[key]["requests"], 0);
                assert_eq!(usage[key]["basis"], "rolling");
                assert!(usage[key]["estimated_total_cost_usd"].is_null());
            }
            assert!(value["data"][0]["usage_fetched_at"].is_null());
        }
    }

    /// 反重力账号列表和详情复用实际网关槽位与 RPM。@return 无。
    #[tokio::test]
    async fn agy_account_views_report_live_capacity() {
        let (app, _, _, pool, service) = test_router_with_scheduling(true).await;
        let (status, saved) = account_admin_json(
            &app,
            Method::POST,
            "/admin/accounts",
            json!({"email":"agy-capacity@example.invalid","setup_token":"synthetic","rpm_limit":16}),
        )
        .await;
        assert!(status.is_success());
        let id = saved["id"].as_i64().unwrap();
        sqlx::query("UPDATE accounts SET platform='antigravity',auth_type='oauth' WHERE id=$1")
            .bind(id)
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("INSERT INTO account_credential_states(account_id,generation,phase,updated_at_ms) VALUES($1,1,'ready',0)")
            .bind(id).execute(&pool).await.unwrap();
        let account = service.get_account(id).await.unwrap();
        let queue = service.get_or_create_queue(id, account.concurrency).await;
        let _held = queue.acquire(Duration::from_secs(1), 2).await.unwrap();
        service
            .acquire_account_rpm(&account, false, "")
            .await
            .unwrap();
        let (status, listed) = account_admin_json(
            &app,
            Method::GET,
            "/admin/accounts?platform=antigravity",
            Value::Null,
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        let (status, detail) = account_admin_json(
            &app,
            Method::GET,
            &format!("/admin/accounts/{id}"),
            Value::Null,
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        for view in [&listed["data"][0], &detail] {
            assert_eq!(view["current_concurrency"].as_f64(), Some(1.0));
            assert_eq!(view["active_requests"], 1);
            assert_eq!(view["queued_requests"], 0);
            assert_eq!(view["rpm_current"], 1);
            assert_eq!(view["agy_request_usage"]["seven_day"]["requests"], 0);
            assert!(view.get("v3_scheduling").is_none());
        }
    }

    /// 已验证字段映射必须与精确版本绑定，旧请求观察继续兼容。
    /// @return 无；来源或版本判断异常时测试失败。
    #[test]
    fn cli_identity_sources_require_verified_version() {
        let mut identity = CliIdentityImport {
            device_id: "d".repeat(64),
            environment_id: "a".repeat(32),
            source: "cli:2.1.293:config.userID".into(),
            canonical_env: CanonicalEnvData {
                version: "2.1.293".into(),
                version_base: "2.1.293".into(),
                ..Default::default()
            },
            canonical_prompt: CanonicalPromptEnvData::default(),
            canonical_process: None,
        };
        assert!(identity.has_confirmed_source());
        identity.canonical_env.version = "2.1.294".into();
        assert!(!identity.has_confirmed_source());
        identity.canonical_env.version = "2.1.293".into();
        identity.canonical_env.version_base = "2.1.294".into();
        assert!(!identity.has_confirmed_source());
        for source in [
            "cli:2.1.294:config.userID",
            "cli:config.machineID",
            "unknown",
        ] {
            identity.source = source.into();
            assert!(!identity.has_confirmed_source());
        }
        identity.source = "cli:/v1/messages:metadata.user_id.device_id".into();
        assert!(identity.has_confirmed_source());
    }

    /// 普通管理鉴权不能代替受信任 v3 服务证明。
    /// @return 无；未授权导入被接受时测试失败。
    #[tokio::test]
    async fn cli_identity_import_requires_internal_service_proof() {
        let (app, _) = test_router_with_gateway().await;
        let payload = serde_json::json!({
            "email": "synthetic@example.invalid",
            "auth_type": "oauth",
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "cli_identity": {
                "device_id": "d".repeat(64),
                "environment_id": "a".repeat(32),
                "source": "cli:2.1.293:config.userID",
                "canonical_env": CanonicalEnvData {
                    version: "2.1.293".into(),
                    version_base: "2.1.293".into(),
                    ..Default::default()
                },
                "canonical_prompt": CanonicalPromptEnvData::default(),
            },
        });
        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/admin/accounts")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(payload.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn settings_selection_mode_validates_and_hot_reloads_with_default_profile() {
        let (app, gateway) = test_router_with_gateway().await;
        for (payload, status, mode, profile) in [
            (
                serde_json::json!({"claude_code_profile_selection_mode":"invalid", "claude_code_version_profile":"2.1.260"}),
                StatusCode::BAD_REQUEST,
                ClaudeCodeProfileSelectionMode::ClientVersion,
                "2.1.293",
            ),
            (
                serde_json::json!({"claude_code_profile_selection_mode":"account"}),
                StatusCode::OK,
                ClaudeCodeProfileSelectionMode::Account,
                "2.1.293",
            ),
            (
                serde_json::json!({"claude_code_version_profile":"2.1.260"}),
                StatusCode::OK,
                ClaudeCodeProfileSelectionMode::Account,
                "2.1.260",
            ),
            (
                serde_json::json!({"claude_code_profile_selection_mode":"client_version"}),
                StatusCode::OK,
                ClaudeCodeProfileSelectionMode::ClientVersion,
                "2.1.260",
            ),
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::PUT)
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(Body::from(payload.to_string()))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), status);
            let config = gateway.profile_selection_config().await;
            assert_eq!(config.mode, mode);
            assert_eq!(config.default_profile.key, profile);
            let account_response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri("/admin/accounts")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(account_response.status(), StatusCode::OK);
            let account_bytes = body::to_bytes(account_response.into_body(), usize::MAX)
                .await
                .unwrap();
            let account_list: serde_json::Value = serde_json::from_slice(&account_bytes).unwrap();
            assert_eq!(
                ClaudeCodeProfileSelectionMode::parse(
                    account_list["claude_code_profile_selection_mode"]
                        .as_str()
                        .unwrap()
                )
                .unwrap(),
                mode
            );
            assert_eq!(account_list["claude_code_version_profile"], profile);
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let settings: serde_json::Value = serde_json::from_slice(
                &body::to_bytes(response.into_body(), 1024 * 1024)
                    .await
                    .unwrap(),
            )
            .unwrap();
            assert_eq!(settings["claude_code_version_profile"], profile);
            assert_eq!(
                settings["claude_code_profile_selection_mode"],
                if mode == ClaudeCodeProfileSelectionMode::Account {
                    "account"
                } else {
                    "client_version"
                }
            );
        }
    }

    async fn test_router() -> Router {
        test_router_with_gateway().await.0
    }

    #[tokio::test]
    async fn account_backend_defaults_validate_and_obey_busy_gate() {
        let (app, _, _, _, accounts) = test_router_with_scheduling(false).await;
        let request = |method: Method, path: &str, value: serde_json::Value| {
            Request::builder()
                .method(method)
                .uri(path)
                .header(header::AUTHORIZATION, "Bearer admin")
                .header(header::CONTENT_TYPE, "application/json")
                .body(Body::from(value.to_string()))
                .unwrap()
        };
        let first = app.clone().oneshot(request(Method::POST, "/admin/accounts", json!({"email":"native-a@example.test","setup_token":"synthetic","auto_telemetry":false}))).await.unwrap();
        assert_eq!(first.status(), StatusCode::CREATED);
        let first: Account =
            serde_json::from_slice(&body::to_bytes(first.into_body(), usize::MAX).await.unwrap())
                .unwrap();
        assert_eq!(first.request_backend, "legacy");
        let second = app.clone().oneshot(request(Method::POST, "/admin/accounts", json!({"email":"native-b@example.test","setup_token":"synthetic","request_backend":"native293","auto_telemetry":false}))).await.unwrap();
        assert_eq!(second.status(), StatusCode::CREATED);
        let second: Account = serde_json::from_slice(
            &body::to_bytes(second.into_body(), usize::MAX)
                .await
                .unwrap(),
        )
        .unwrap();
        assert_eq!(second.request_backend, "native293");
        let path = format!("/admin/accounts/{}", first.id);
        for backend in [json!("invalid"), json!(true)] {
            let response = app
                .clone()
                .oneshot(request(
                    Method::PUT,
                    &path,
                    json!({"request_backend":backend}),
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        }
        let queue = accounts
            .get_or_create_queue(first.id, first.concurrency)
            .await;
        let permit = queue.acquire(Duration::from_secs(1), 2).await.unwrap();
        let response = app
            .clone()
            .oneshot(request(
                Method::PUT,
                &path,
                json!({"request_backend":"native293"}),
            ))
            .await
            .unwrap();
        assert!(!response.status().is_success());
        assert_eq!(
            accounts
                .get_account(first.id)
                .await
                .unwrap()
                .request_backend,
            "legacy"
        );
        drop(permit);
        let mut changes = accounts.subscribe_native_changes();
        for backend in ["native293", "legacy"] {
            let response = app
                .clone()
                .oneshot(request(
                    Method::PUT,
                    &path,
                    json!({"request_backend":backend}),
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            assert_eq!(
                accounts
                    .get_account(first.id)
                    .await
                    .unwrap()
                    .request_backend,
                backend
            );
            assert_eq!(
                accounts
                    .get_account(second.id)
                    .await
                    .unwrap()
                    .request_backend,
                "native293"
            );
            let mut wakes = 0;
            while let Ok((id, _, wake)) = changes.try_recv() {
                assert_eq!(id, first.id);
                wakes += usize::from(wake);
            }
            assert_eq!(wakes, usize::from(backend == "native293"));
            assert!(queue.runtime_gate.snapshot()["lease"].is_null());
        }
        for status in ["active", "disabled"] {
            let response = app
                .clone()
                .oneshot(request(
                    Method::PUT,
                    &path,
                    json!({"request_backend":"native293","status":status}),
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let mut wakes = 0;
            while let Ok((_, _, wake)) = changes.try_recv() {
                wakes += usize::from(wake);
            }
            assert_eq!(wakes, usize::from(status == "active"));
            assert!(queue.runtime_gate.snapshot()["lease"].is_null());
        }
    }

    #[tokio::test]
    async fn target_profile_settings_round_trip_and_invalid_rule_is_atomic() {
        let (app, gateway) = test_router_with_gateway().await;
        let target = serde_json::json!({
            "claude_code_profile_selection_mode":"client_version",
            "claude_code_version_profile":"2.1.293",
            "allowed_claude_code_versions":"2.1.89-2.1.293",
            "blocked_claude_code_versions":"2.1.89-2.1.279,2.1.281-2.1.292",
            "allowed_user_agents":"synthetic-client*"
        });
        for (payload, status) in [
            (target.clone(), StatusCode::OK),
            (
                serde_json::json!({"claude_code_version_profile":"2.1.280", "blocked_claude_code_versions":"invalid"}),
                StatusCode::BAD_REQUEST,
            ),
        ] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::PUT)
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(Body::from(payload.to_string()))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), status);
            let config = gateway.profile_selection_config().await;
            assert_eq!(config.mode, ClaudeCodeProfileSelectionMode::ClientVersion);
            assert_eq!(config.default_profile.key, "2.1.293");
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let settings: serde_json::Value = serde_json::from_slice(
                &body::to_bytes(response.into_body(), 1024 * 1024)
                    .await
                    .unwrap(),
            )
            .unwrap();
            for (key, value) in target.as_object().unwrap() {
                assert_eq!(&settings[key], value);
            }
        }
    }

    #[tokio::test]
    async fn account_list_reports_base_version_and_effective_profile_configuration() {
        let app = test_router().await;
        let created = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/admin/accounts")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        serde_json::json!({
                            "email": "account-display@example.invalid",
                            "setup_token": "test-token",
                            "auto_telemetry": false
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(created.status(), StatusCode::CREATED);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/admin/accounts?page=1&page_size=12")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let bytes = body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let payload: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(
            payload["claude_code_profile_selection_mode"],
            "client_version"
        );
        assert_eq!(payload["claude_code_version_profile"], "2.1.293");
        assert_eq!(payload["total"], 1);
        assert_eq!(payload["data"][0]["canonical_env"]["version"], "2.1.293");
        assert_eq!(payload["data"][0]["auto_telemetry"], false);
    }

    #[tokio::test]
    async fn hello_get_returns_capture_compatible_json() {
        let response = hello_get().await;

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers()[header::CONTENT_TYPE],
            "application/json; charset=utf-8"
        );
        assert_eq!(response.headers()[header::CONTENT_LENGTH], "20");
        let body = body::to_bytes(response.into_body(), 1024).await.unwrap();
        assert_eq!(body.as_ref(), br#"{"message": "hello"}"#);
    }

    #[tokio::test]
    async fn hello_head_returns_length_without_body() {
        let response = hello_head().await;

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()[header::CONTENT_LENGTH], "20");
        let body = body::to_bytes(response.into_body(), 1024).await.unwrap();
        assert!(body.is_empty());
    }

    #[tokio::test]
    async fn frontend_routes_support_direct_navigation_and_reload() {
        let app = test_router().await;
        for path in [
            "/",
            "/login",
            "/tokens",
            "/requests",
            "/session-blocks",
            "/tasks",
            "/settings",
            "/proxies",
            "/updates",
            "/environments",
            "/nodes",
            "/nodes/",
            "/tasks/",
            "/environments/",
            "/settings/",
            "/tasks?tab=warmup&account=42",
        ] {
            let response = app
                .clone()
                .oneshot(Request::builder().uri(path).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK, "{path}");
            assert_eq!(response.headers()[header::CONTENT_TYPE], "text/html");
            let html = body::to_bytes(response.into_body(), 1024 * 1024)
                .await
                .unwrap();
            assert!(
                String::from_utf8_lossy(&html).contains("id=\"app\""),
                "{path}"
            );
        }
    }

    #[tokio::test]
    async fn assembled_router_keeps_hello_public_and_fallback_authenticated() {
        let app = test_router().await;
        let get_response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/api/hello")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let head_response = app
            .clone()
            .oneshot(
                Request::builder()
                    .method(Method::HEAD)
                    .uri("/api/hello")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let fallback_response = app
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/not-registered")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(get_response.status(), StatusCode::OK);
        assert_eq!(head_response.status(), StatusCode::OK);
        assert_eq!(head_response.headers()[header::CONTENT_LENGTH], "20");
        assert!(
            body::to_bytes(head_response.into_body(), 1024)
                .await
                .unwrap()
                .is_empty()
        );
        assert_eq!(fallback_response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn settings_return_session_hello_probe_defaults() {
        let response = test_router()
            .await
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/admin/settings")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let value: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(value["session_hello_probe_enabled"], "false");
        assert_eq!(value["session_hello_probe_strict"], "false");
        assert_eq!(value["session_hello_probe_timeout_secs"], "5");
        assert_eq!(value["session_hello_probe_success_ttl_secs"], "3600");
        assert_eq!(value["session_hello_probe_failure_cooldown_secs"], "300");
    }

    /// 日志模式默认摘要，非法值在批量写入前拒绝，合法模式可热保存。
    #[tokio::test]
    async fn log_mode_setting_validates_atomically_and_defaults_to_info() {
        let app = test_router().await;
        let update = |mode: &str| {
            Request::builder().method(Method::PUT).uri("/admin/settings")
            .header(header::AUTHORIZATION, "Bearer admin").header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(serde_json::json!({"request_diagnostics_log_mode":mode,"log_429_request_enabled":"true"}).to_string())).unwrap()
        };
        assert_eq!(
            app.clone().oneshot(update("trace")).await.unwrap().status(),
            StatusCode::BAD_REQUEST
        );
        for expected in ["info", "debug"] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            let value: serde_json::Value = serde_json::from_slice(
                &body::to_bytes(response.into_body(), 1024 * 1024)
                    .await
                    .unwrap(),
            )
            .unwrap();
            assert_eq!(value["request_diagnostics_log_mode"], expected);
            if expected == "info" {
                assert_eq!(
                    value["log_429_request_enabled"], "false",
                    "无效模式不能部分写入同批设置"
                );
                assert_eq!(
                    app.clone().oneshot(update("debug")).await.unwrap().status(),
                    StatusCode::OK
                );
            }
        }
    }

    #[tokio::test]
    async fn settings_return_fable_weekly_usage_limit_default() {
        let response = test_router()
            .await
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/admin/settings")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let value: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(value["fable_weekly_usage_limit_percent"], "50");
    }

    #[tokio::test]
    async fn settings_return_cli_bg_status_classifier_default() {
        let response = test_router()
            .await
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/admin/settings")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap();
        let value: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(
            value["intercept_cli_bg_status_classifier_mode"],
            "passthrough"
        );
        assert_eq!(
            value["intercept_cli_bg_status_classifier_models"],
            DEFAULT_INTERCEPT_CLI_BG_STATUS_CLASSIFIER_MODELS
        );
        assert_eq!(
            value["intercept_cli_bg_status_classifier_identity_injection_enabled"],
            "false"
        );
    }

    #[tokio::test]
    async fn settings_reject_invalid_cli_bg_status_classifier_mode() {
        for value in ["", "error", "mock_allow"] {
            let response = test_router()
                .await
                .oneshot(
                    Request::builder()
                        .method(Method::PUT)
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(Body::from(
                            serde_json::json!({
                                "intercept_cli_bg_status_classifier_mode": value
                            })
                            .to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "value={value}");
        }
    }

    #[tokio::test]
    async fn settings_reject_invalid_cli_bg_status_classifier_models() {
        let response = test_router()
            .await
            .oneshot(
                Request::builder()
                    .method(Method::PUT)
                    .uri("/admin/settings")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        serde_json::json!({
                            "intercept_cli_bg_status_classifier_models": "claude-opus-5-5,bad/model"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn settings_reject_invalid_cli_bg_status_classifier_identity_injection_flag() {
        for value in ["", "1", "yes"] {
            let response = test_router()
                .await
                .oneshot(
                    Request::builder()
                        .method(Method::PUT)
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(Body::from(
                            serde_json::json!({
                                "intercept_cli_bg_status_classifier_identity_injection_enabled": value
                            })
                            .to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "value={value}");
        }
    }

    #[tokio::test]
    async fn settings_update_hot_reloads_cli_bg_status_classifier_mode() {
        let (app, gateway_svc) = test_router_with_gateway().await;
        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::PUT)
                    .uri("/admin/settings")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        serde_json::json!({
                            "intercept_cli_bg_status_classifier_mode": "mock",
                            "intercept_cli_bg_status_classifier_models": "claude-opus-5-5",
                            "intercept_cli_bg_status_classifier_identity_injection_enabled": "true"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            gateway_svc.cli_bg_status_classifier_mode_for_test().await,
            CliBgStatusClassifierMode::Mock
        );
        assert_eq!(
            gateway_svc.cli_bg_status_classifier_models_for_test().await,
            ["claude-opus-5-5"]
        );
        assert!(
            gateway_svc
                .cli_bg_status_classifier_identity_injection_enabled_for_test()
                .await
        );
    }

    /// 非法新开关在其它设置写入前被拒绝，防止同次请求部分保存。
    /// @return 无；校验或原子拒绝失效时失败。
    #[tokio::test]
    async fn settings_message_top_field_filter_rejects_invalid_values_atomically() {
        let app = test_router().await;
        for value in ["", "TRUE", "1", " true", "false "] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::PUT)
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(Body::from(
                            json!({
                                "message_top_field_filter_enabled":value,
                                "allow_system_role_models":"synthetic-no-partial-write"
                            })
                            .to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "值={value:?}");
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            let payload: Value = serde_json::from_slice(
                &body::to_bytes(response.into_body(), 1024 * 1024)
                    .await
                    .unwrap(),
            )
            .unwrap();
            assert_ne!(
                payload["allow_system_role_models"],
                "synthetic-no-partial-write"
            );
        }
    }

    /// 管理 GET 规范存量值，PUT 字符串开关保存后立即刷新 Gateway。
    /// @return 无；展示、生效值或字符串保存合同失配时失败。
    #[tokio::test]
    async fn settings_message_top_field_filter_normalizes_get_and_hot_reloads_put() {
        let (app, gateway, settings, pool) = test_router_with_gateway_and_settings().await;
        for (stored, expected) in [
            (None, "true"),
            (Some("invalid"), "true"),
            (Some("TRUE"), "true"),
            (Some("false"), "false"),
            (Some("true"), "true"),
        ] {
            sqlx::query("DELETE FROM settings WHERE key=$1")
                .bind("message_top_field_filter_enabled")
                .execute(&pool)
                .await
                .unwrap();
            if let Some(stored) = stored {
                settings
                    .upsert_many(&HashMap::from([(
                        "message_top_field_filter_enabled".into(),
                        stored.into(),
                    )]))
                    .await
                    .unwrap();
            }
            gateway
                .reload_message_top_field_filter_enabled()
                .await
                .unwrap();
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let payload: Value = serde_json::from_slice(
                &body::to_bytes(response.into_body(), 1024 * 1024)
                    .await
                    .unwrap(),
            )
            .unwrap();
            assert_eq!(payload["message_top_field_filter_enabled"], expected);
            assert_eq!(
                gateway.message_top_field_filter_enabled_for_test().await,
                expected == "true"
            );
        }
        for expected in ["false", "true", "false"] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::PUT)
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(Body::from(
                            json!({"message_top_field_filter_enabled":expected}).to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            assert_eq!(
                settings
                    .get_value("message_top_field_filter_enabled", "missing")
                    .await
                    .unwrap(),
                expected
            );
            assert_eq!(
                gateway.message_top_field_filter_enabled_for_test().await,
                expected == "true"
            );
        }
    }

    /// 消息缓存模式经管理接口校验并热加载，旧模式和内部标记均受控。
    /// @return 无；非法批次写入、标记泄露或运行期失配时失败。
    #[tokio::test]
    async fn native_message_cache_settings_validate_and_hot_reload() {
        let (app, gateway, settings, _) = test_router_with_gateway_and_settings().await;
        settings
            .ensure_native_message_cache_defaults()
            .await
            .unwrap();
        for mode in ["sub2api", "off"] {
            let (status, _) = account_admin_json(
                &app,
                Method::PUT,
                "/admin/settings",
                json!({"message_cache_control_rewrite":mode}),
            )
            .await;
            assert_eq!(status, StatusCode::OK);
            assert_eq!(gateway.message_cache_mode_for_test().await.as_str(), mode);
            let (_, response) =
                account_admin_json(&app, Method::GET, "/admin/settings", Value::Null).await;
            assert_eq!(response["message_cache_control_rewrite"], mode);
            assert!(response.get("_internal_native_message_cache_v1").is_none());
        }
        for value in [
            "auto", "rolling", "stateful", "stable", "anchored", "invalid",
        ] {
            let (status, _) = account_admin_json(
                &app,
                Method::PUT,
                "/admin/settings",
                json!({"message_cache_control_rewrite":value,"synthetic_cache_atomic":"changed"}),
            )
            .await;
            assert_eq!(status, StatusCode::BAD_REQUEST);
            assert!(
                !settings
                    .get_all()
                    .await
                    .unwrap()
                    .contains_key("synthetic_cache_atomic")
            );
            assert_eq!(gateway.message_cache_mode_for_test().await.as_str(), "off");
        }
        let (status, _) = account_admin_json(
            &app,
            Method::PUT,
            "/admin/settings",
            json!({"_internal_native_message_cache_v1":"reset"}),
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        settings
            .upsert_many(&HashMap::from([(
                "message_cache_control_rewrite".into(),
                "invalid".into(),
            )]))
            .await
            .unwrap();
        gateway
            .reload_message_cache_control_rewrite()
            .await
            .unwrap();
        let (_, response) =
            account_admin_json(&app, Method::GET, "/admin/settings", Value::Null).await;
        assert_eq!(response["message_cache_control_rewrite"], "off");
        assert_eq!(gateway.message_cache_mode_for_test().await.as_str(), "off");
    }

    #[tokio::test]
    async fn settings_reject_invalid_fable_weekly_usage_limits() {
        for value in ["0", "101", "50.5", "invalid"] {
            let response = test_router()
                .await
                .oneshot(
                    Request::builder()
                        .method(Method::PUT)
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(Body::from(
                            serde_json::json!({
                                "fable_weekly_usage_limit_percent": value
                            })
                            .to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "value={value}");
        }
    }

    /// 新默认、持久化、热刷新及非法值原子拒绝沿真实管理路由验证。@return 无。
    #[tokio::test]
    async fn native_idle_settings_default_reload_and_atomic_validation() {
        let (app, gateway, settings, _) = test_router_with_gateway_and_settings().await;
        gateway.reload_native_idle_timeout().await.unwrap();
        assert_eq!(gateway.native_idle_timeout(), 120);
        assert_eq!(
            settings
                .get_value("native_idle_timeout_secs", "missing")
                .await
                .unwrap(),
            "120"
        );
        for value in ["30", "60", "300", "3600", "120"] {
            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::PUT)
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(Body::from(
                            json!({"native_idle_timeout_secs":value}).to_string(),
                        ))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            assert_eq!(gateway.native_idle_timeout(), value.parse::<u64>().unwrap());
            gateway.reload_native_idle_timeout().await.unwrap();
            assert_eq!(
                settings
                    .get_value("native_idle_timeout_secs", "missing")
                    .await
                    .unwrap(),
                value
            );
        }
        for value in ["", "0", "29", "3601", "60.5", "bad", "-1", " 120"] {
            let response = app.clone().oneshot(Request::builder()
                .method(Method::PUT).uri("/admin/settings")
                .header(header::AUTHORIZATION, "Bearer admin")
                .header(header::CONTENT_TYPE, "application/json")
                .body(Body::from(json!({"native_idle_timeout_secs":value,"stream_keepalive_interval_secs":"100"}).to_string())).unwrap()).await.unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "值={value}");
            assert_eq!(gateway.native_idle_timeout(), 120);
            assert_ne!(
                settings
                    .get_value("stream_keepalive_interval_secs", "45")
                    .await
                    .unwrap(),
                "100"
            );
        }
        settings
            .upsert_many(&HashMap::from([(
                "native_idle_timeout_secs".into(),
                "invalid".into(),
            )]))
            .await
            .unwrap();
        gateway.reload_native_idle_timeout().await.unwrap();
        assert_eq!(gateway.native_idle_timeout(), 120);
        let response = app
            .oneshot(
                Request::builder()
                    .uri("/admin/settings")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn settings_update_hot_reloads_fable_weekly_usage_limit() {
        let (app, gateway_svc) = test_router_with_gateway().await;
        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::PUT)
                    .uri("/admin/settings")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        serde_json::json!({
                            "fable_weekly_usage_limit_percent": "75"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            gateway_svc
                .fable_weekly_usage_limit_percent_for_test()
                .await,
            75
        );
    }

    #[tokio::test]
    async fn settings_reject_session_hello_probe_ranges() {
        for (key, value) in [
            ("session_hello_probe_timeout_secs", "0"),
            ("session_hello_probe_success_ttl_secs", "59"),
            ("session_hello_probe_failure_cooldown_secs", "3601"),
        ] {
            let response = test_router()
                .await
                .oneshot(
                    Request::builder()
                        .method(Method::PUT)
                        .uri("/admin/settings")
                        .header(header::AUTHORIZATION, "Bearer admin")
                        .header(header::CONTENT_TYPE, "application/json")
                        .body(Body::from(serde_json::json!({key: value}).to_string()))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST, "key={key}");
        }
    }

    #[tokio::test]
    async fn settings_update_hot_reloads_session_hello_probe_config() {
        let (app, gateway_svc) = test_router_with_gateway().await;
        let response = app
            .oneshot(
                Request::builder()
                    .method(Method::PUT)
                    .uri("/admin/settings")
                    .header(header::AUTHORIZATION, "Bearer admin")
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(
                        serde_json::json!({
                            "session_hello_probe_enabled": "true",
                            "session_hello_probe_strict": "true",
                            "session_hello_probe_timeout_secs": "7",
                            "session_hello_probe_success_ttl_secs": "7200",
                            "session_hello_probe_failure_cooldown_secs": "600"
                        })
                        .to_string(),
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let config = gateway_svc.session_hello_probe_config_for_test().await;
        assert!(config.enabled);
        assert!(config.strict);
        assert_eq!(config.timeout, Duration::from_secs(7));
        assert_eq!(config.success_ttl, Duration::from_secs(7200));
        assert_eq!(config.failure_cooldown, Duration::from_secs(600));
    }

    #[test]
    fn model_id_list_allows_empty_and_valid_ids() {
        assert!(validate_model_id_list("allow_system_role_models", "").is_ok());
        assert!(
            validate_model_id_list(
                "allow_system_role_models",
                "claude-opus-4-8, claude.test:model_1"
            )
            .is_ok()
        );
    }

    #[test]
    fn model_id_list_rejects_unsafe_chars() {
        let err = validate_model_id_list("allow_system_role_models", "claude-opus-4-8, bad/model")
            .unwrap_err();

        assert!(err.to_string().contains("bad/model"));
    }

    #[test]
    fn context_sanitizer_mode_accepts_only_known_values() {
        assert_eq!(
            ClaudeCodeContextSanitizerMode::parse("report_only").unwrap(),
            ClaudeCodeContextSanitizerMode::ReportOnly
        );
        assert_eq!(
            ClaudeCodeContextSanitizerMode::parse("normalize").unwrap(),
            ClaudeCodeContextSanitizerMode::Normalize
        );
        assert!(ClaudeCodeContextSanitizerMode::parse("rewrite").is_err());
    }

    #[test]
    fn oauth_credential_validity_uses_default_and_rejects_out_of_range() {
        assert_eq!(
            normalize_oauth_credential_validity_seconds(None).unwrap(),
            2400
        );
        assert!(
            normalize_oauth_credential_validity_seconds(Some(
                MIN_OAUTH_CREDENTIAL_VALIDITY_SECONDS - 1
            ))
            .is_err()
        );
        assert!(
            normalize_oauth_credential_validity_seconds(Some(
                MAX_OAUTH_CREDENTIAL_VALIDITY_SECONDS + 1
            ))
            .is_err()
        );
    }
    /// 会话观察经过真实管理员路由；只读查询不续租，不把请求数当会话数。
    #[tokio::test]
    async fn scheduling_routes_are_admin_only_bounded_and_read_only() {
        use sqlx::Row;
        let (app, _, _, pool, accounts) = test_router_with_scheduling(true).await;
        let rows=sqlx::query("INSERT INTO accounts(name,email,token,device_id) VALUES('合成账号','scheduling@example.invalid','synthetic','synthetic-device') RETURNING id").fetch_all(&pool).await.unwrap();
        let id: i64 = rows[0].get(0);
        let account = accounts.get_account(id).await.unwrap();
        let scheduler = accounts.scheduler().unwrap();
        let first = scheduler.begin(1, Some("synthetic-private-session"));
        first.selected(&account, None);
        first.admit(&account).await.unwrap().submitted();
        let second = scheduler.begin(1, Some("synthetic-private-session"));
        accounts
            .select_v3_account(&second, &[], &[], &AccountSelectionContext::disabled(), 2)
            .await
            .unwrap();
        second.phase(RequestPhase::WaitingSend);
        let before = scheduler
            .store
            .binding(first.key().unwrap(), now_ms())
            .await
            .unwrap()
            .unwrap();
        for path in [
            format!("/admin/accounts/{id}/scheduling"),
            format!("/admin/accounts/{id}/scheduling/sessions"),
        ] {
            let denied = app
                .clone()
                .oneshot(Request::builder().uri(&path).body(Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(denied.status(), StatusCode::UNAUTHORIZED);
        }
        let (status, detail) = account_admin_json(
            &app,
            Method::GET,
            &format!("/admin/accounts/{id}/scheduling"),
            Value::Null,
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(detail["summary"]["bound_sessions"], 1);
        assert_eq!(detail["summary"]["active_sessions"], 1);
        assert_eq!(detail["summary"]["phases"]["running"], 1);
        assert_eq!(detail["summary"]["phases"]["waiting_send"], 1);
        assert_eq!(detail["snapshot"]["events"].as_array().unwrap().len(), 1);
        let (status, sessions) = account_admin_json(
            &app,
            Method::GET,
            &format!("/admin/accounts/{id}/scheduling/sessions?state=active"),
            Value::Null,
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(sessions["total"], 1);
        assert!(!sessions.to_string().contains("synthetic-private-session"));
        let after = scheduler
            .store
            .binding(first.key().unwrap(), now_ms())
            .await
            .unwrap()
            .unwrap();
        assert_eq!(before.expires_at_ms, after.expires_at_ms);
        assert_eq!(before.last_seen_at_ms, after.last_seen_at_ms);
        for suffix in ["page=0", "page_size=101", "prefix=not-hex", "state=unknown"] {
            let (status, _) = account_admin_json(
                &app,
                Method::GET,
                &format!("/admin/accounts/{id}/scheduling/sessions?{suffix}"),
                Value::Null,
            )
            .await;
            assert_eq!(status, StatusCode::BAD_REQUEST);
        }
        let (status, list) =
            account_admin_json(&app, Method::GET, "/admin/accounts", Value::Null).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(list["data"][0]["v3_scheduling"]["bound_sessions"], 1);
    }

    /// 新偏好经管理接口原子生效，旧评分键和分数退出公开合同。
    #[tokio::test]
    async fn scheduling_preferences_hot_reload_and_retired_scores_are_removed() {
        let (app, _, _, _, accounts) = test_router_with_scheduling(true).await;
        let (status, _) = account_admin_json(
            &app,
            Method::PUT,
            "/admin/settings",
            json!({
                "v3_smart_weight_reset":"1.2", "v3_smart_weight_queue":"0.8",
                "v3_smart_reset_weight_5h":"1", "v3_smart_reset_weight_7d":"0"
            }),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        let config = accounts.scheduler().unwrap().config();
        assert_eq!(config.reset_weight, 1.2);
        assert_eq!(config.queue_weight, 0.8);
        assert_eq!(config.reset_window_weights, [1.0, 0.0]);
        let (status, _) = account_admin_json(
            &app,
            Method::PUT,
            "/admin/settings",
            json!({"v3_smart_weight_queue":"0.01"}),
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(accounts.scheduler().unwrap().config().queue_weight, 0.8);
        let (status, _) = account_admin_json(
            &app,
            Method::PUT,
            "/admin/settings",
            json!({"v3_scheduling_mode":"legacy_score","score_weight_7d":"10"}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        let (_, settings) =
            account_admin_json(&app, Method::GET, "/admin/settings", Value::Null).await;
        for key in OBSOLETE_SCHEDULING_KEYS {
            assert!(settings.get(*key).is_none());
        }
        let (_, list) = account_admin_json(&app, Method::GET, "/admin/accounts", Value::Null).await;
        for account in list["data"].as_array().unwrap() {
            assert!(account.get("scheduling_score").is_none());
            assert!(account.get("scheduling_detail").is_none());
        }
    }

    /// 并发局部设置更新不能共同持久化出全零权重。
    #[tokio::test]
    async fn scheduling_settings_merge_validate_and_apply_atomically() {
        let (app, _, settings, _, accounts) = test_router_with_scheduling(true).await;
        let left = account_admin_json(
            &app,
            Method::PUT,
            "/admin/settings",
            json!({"v3_smart_weight_load":"0","v3_smart_weight_quota":"0"}),
        );
        let right = account_admin_json(
            &app,
            Method::PUT,
            "/admin/settings",
            json!({"v3_smart_weight_health":"0","v3_smart_weight_latency":"0"}),
        );
        let (left, right) = tokio::join!(left, right);
        assert!(
            (left.0 == StatusCode::OK && right.0 == StatusCode::BAD_REQUEST)
                || (right.0 == StatusCode::OK && left.0 == StatusCode::BAD_REQUEST)
        );
        let stored = settings.get_all().await.unwrap();
        let config = SchedulingConfig::parse(&stored).unwrap();
        assert_eq!(
            config.weights,
            accounts.scheduler().unwrap().config().weights
        );
        let (status, _) = account_admin_json(
            &app,
            Method::PUT,
            "/admin/settings",
            json!({"v3_scheduling_mode":"legacy_score","v3_admission_wait_seconds":"10"}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(accounts.scheduler().unwrap().config().mode, "smart");
        let (status, _) = account_admin_json(
            &app,
            Method::PUT,
            "/admin/settings",
            json!({"v3_admission_wait_seconds":"121"}),
        )
        .await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(accounts.scheduler().unwrap().config().wait_seconds, 10);
    }
    /// 管理接口元数据更新保留最新凭据，非法元数据不能先改变账号状态。
    /// @return 无；创建、局部更新、清除或拒绝顺序异常时失败。
    #[tokio::test]
    async fn subscription_metadata_admin_roundtrip_and_atomic_validation() {
        let (app, _, _, pool, _) = test_router_with_scheduling(false).await;
        let (status, account) = account_admin_json(
            &app,
            Method::POST,
            "/admin/accounts",
            json!({
                "name":"synthetic-tier", "email":"tier-admin@example.invalid", "auth_type":"oauth",
                "access_token":"synthetic-old-access", "refresh_token":"synthetic-old-refresh",
                "subscription_type":"max", "rate_limit_tier":"default_claude_max_20x"
            }),
        )
        .await;
        assert_eq!(status, StatusCode::CREATED);
        assert_eq!(account["rate_limit_tier"], "default_claude_max_20x");
        let id = account["id"].as_i64().unwrap();
        let path = format!("/admin/accounts/{id}");
        sqlx::query("UPDATE accounts SET access_token='synthetic-rotated-access',refresh_token='synthetic-rotated-refresh' WHERE id=$1")
            .bind(id).execute(&pool).await.unwrap();
        let (status, updated) = account_admin_json(
            &app,
            Method::PUT,
            &path,
            json!({"rate_limit_tier":"default_claude_max_5x"}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(updated["refresh_token"], "synthetic-rotated-refresh");
        assert_eq!(updated["subscription_type"], "max");
        assert_eq!(updated["rate_limit_tier"], "default_claude_max_5x");
        for value in [json!(7), json!("bad\nvalue"), json!("x".repeat(257))] {
            let (status, _) = account_admin_json(
                &app,
                Method::PUT,
                &path,
                json!({"status":"disabled","rate_limit_tier":value}),
            )
            .await;
            assert_eq!(status, StatusCode::BAD_REQUEST);
        }
        let (_, list) = account_admin_json(&app, Method::GET, "/admin/accounts", Value::Null).await;
        assert_eq!(list["data"][0]["status"], "active");
        let (_, updated) = account_admin_json(
            &app,
            Method::PUT,
            &path,
            json!({"subscription_type":"ultra"}),
        )
        .await;
        assert!(updated.get("rate_limit_tier").is_none());
        assert_eq!(updated["refresh_token"], "synthetic-rotated-refresh");
    }
}
