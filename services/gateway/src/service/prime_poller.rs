use axum::http::HeaderMap;
use bytes::Bytes;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use chrono::{DateTime, Local, NaiveDate, Timelike, Utc};
use serde_json::Value;
use tokio::time::{Instant as TokioInstant, sleep, timeout, timeout_at};
use tracing::{debug, info, warn};
use uuid::Uuid;

use crate::error::AppError;
use crate::model::account::{Account, AccountAuthType, AccountStatus};
use crate::model::request_diagnostics::RequestLogMode;
use crate::service::account::{
    AccountSelectionContext, AccountService, RateLimitDecision, UsageObservationKind,
    account_fable_weekly_usage_limit_reached, account_usage_limit_reached,
};
use crate::service::gateway::{
    extract_passive_usage, extract_rejected_passive_usage_windows,
    parse_fable_weekly_usage_limit_percent, request_slot_units, response_content_codings,
};
use crate::service::native_contract::{NativeSourceVersion, NativeSubmission};
use crate::service::rewriter::{
    CacheControlTtlRewrite, ClientType, EnvPassthrough, MessageCacheControlRewrite, Rewriter,
    ordered_anthropic_headers,
};
use crate::service::runtime_transport::{self, PreparedRequest, TuiBodyPolicy, TuiMessagesInput};
use crate::service::system_update;
use crate::service::tui_backend::{self, TUI_V2, TuiRequestRoute};
use crate::service::tui_tool_history::SERVER_SESSION_PREFIX;
use crate::service::usage::UsageCapture;
use crate::service::v3_scheduling::RequestPhase;
use crate::service::version_profile::tls_profile_for_account;
use crate::store::prime_log_store::{PrimeLogEntry, PrimeLogStore};
use crate::store::settings_store::{
    DEFAULT_FABLE_STICKY_QUOTA_FALLBACK_ENABLED, DEFAULT_FABLE_WEEKLY_USAGE_LIMIT_PERCENT,
    DEFAULT_MESSAGE_BODY_ORDER_FINGERPRINT_ENABLED, SettingsStore,
};
use crate::tlsfp::configured_default_tls_profile;

/// 上游 `/v1/messages` 地址,与 gateway.rs 的 UPSTREAM_BASE 保持一致。
const UPSTREAM_URL: &str = "https://api.anthropic.com/v1/messages?beta=true";

/// 账号之间的最小间隔,防止瞬间并发打爆上游。
const PER_ACCOUNT_GAP: Duration = Duration::from_millis(500);

/// 预热请求 TTFB 超时,短于主链路的 gateway 超时(预热非关键路径,快速失败为宜)。
const PRIME_TTFB_TIMEOUT: Duration = Duration::from_secs(30);

/// 成功响应的流耗尽超时。rewriter 强制 stream=true,必须读完整个 SSE 上游才确定把
/// 这次调用计入 5h 窗口,duration_ms 也才等于完整调用时间。Haiku 512 tokens 一般 <5s,
/// 60s 给足余量;若真的超时,视为上游异常,但 ratelimit 响应头已经拿到,仍算触发成功。
const PRIME_DRAIN_TIMEOUT: Duration = Duration::from_secs(60);

/// 主循环扫描间隔。触发点为 HH:10 分,30s 扫一次足以确保分钟内命中至少一次。
const TICK_INTERVAL: Duration = Duration::from_secs(30);

/// 约定的触发分钟:每天在 HH:10 分发起预热,避免 :00/:30 的全球流量峰值。
const TRIGGER_MINUTE: u32 = 10;

/// 错误信息截断字符数。按字符而非字节截,避免多字节字符跨边界导致 panic。
const ERROR_SNIPPET_CHARS: usize = 200;

// 私有会话采用公共入口拒绝的前缀。这一主体仅用于经过账号认证的后台预留。
const TUI_PRIME_PRINCIPAL: i64 = i64::MAX;

/// 预热解析出的有效配置。
struct PrimeConfig {
    enabled: bool,
    hours: Vec<u32>,
    model: String,
    message_body_order_fingerprint_enabled: bool,
}

/// 预热结果,用于写入日志表。
struct PrimeOutcome {
    success: bool,
    error_message: String,
    duration_ms: i64,
    passive_usage: Option<serde_json::Value>,
    usage_observation_kind: UsageObservationKind,
    /// 上游 HTTP 状态码,None 表示请求没到达上游(如 token 解析失败、序列化失败)。
    /// 用于后续按状态码做 401/429/403 处理。
    status: Option<u16>,
    /// 仅用于延迟 401 的条件状态写入，不写入日志或数据库。
    failed_access_token: Option<String>,
}

/// 峰值 5h 窗口预热服务。
///
/// 每天在配置的清晨时间点(默认 4:10 / 5:10 / 6:10 本地时间)对所有活跃且未处于速率冷却
/// 期的账号逐一发送一次 Haiku `/v1/messages` 请求,借此主动启动 Anthropic 侧的 5h 速率
/// 限制窗口,让窗口重置点落在下午用户高峰之前或之中。
///
/// 旧路径的 OAuth 账号首次收到 401 时会刷新凭据并原账号重试一次。V2 只使用原账号的
/// 受信事件源，拒绝只记录这次预热结果。每次调用
/// （含成功/失败/跳过）都会写入 `prime_logs` 表,供设置页展示。最终 401 / 429 / 403 会联动
/// `AccountService` 的状态处理,和主链路行为保持一致,防止预热探测到坏账号却让真实流量
/// 继续选中它。
pub struct PrimePollerService {
    account_svc: Arc<AccountService>,
    settings_store: Arc<SettingsStore>,
    log_store: Arc<PrimeLogStore>,
    rewriter: Arc<Rewriter>,
    upstream_url: String,
}

impl PrimePollerService {
    /// 构造服务实例。
    pub fn new(
        account_svc: Arc<AccountService>,
        settings_store: Arc<SettingsStore>,
        log_store: Arc<PrimeLogStore>,
        rewriter: Arc<Rewriter>,
    ) -> Self {
        Self {
            account_svc,
            settings_store,
            log_store,
            rewriter,
            upstream_url: UPSTREAM_URL.to_string(),
        }
    }

    /// 启动后台循环。应在 main 中 tokio::spawn 调用。
    pub async fn run(self: Arc<Self>) {
        info!(
            "prime poller: started, trigger minute = :{:02}, tick = {:?}",
            TRIGGER_MINUTE, TICK_INTERVAL
        );

        // 去重键:(本地日期, 小时) 用于避免同一触发点内多次 tick 重复执行。
        let mut last_fired: Option<(NaiveDate, u32)> = None;

        loop {
            self.check_once(&mut last_fired).await;
            sleep(TICK_INTERVAL).await;
        }
    }

    /// 单次扫描:判断当前本地时间是否命中触发点,命中则执行一轮预热。
    async fn check_once(&self, last_fired: &mut Option<(NaiveDate, u32)>) {
        // 使用服务器本地时间(chrono::Local)。部署时需要确保容器 TZ 正确,
        // 否则 4/5/6 点会错位到 UTC 对应小时。
        let now = chrono::Local::now();
        self.check_at(now, last_fired).await;
    }

    /// 根据本地触发时刻执行扫描，便于固定时间验证调度去重。
    /// @param now 服务器本地当前时刻。
    /// @param last_fired 上次成功领取的日期与小时。
    /// @return 无；结果进入原预热日志。
    async fn check_at(&self, now: DateTime<Local>, last_fired: &mut Option<(NaiveDate, u32)>) {
        if now.minute() != TRIGGER_MINUTE {
            return;
        }

        let h = now.hour();
        let key = (now.date_naive(), h);
        // 同一(日期,小时)只触发一次,防止 30s 扫描在同一分钟内重复进入。
        if *last_fired == Some(key) {
            return;
        }

        let cfg = match self.load_config().await {
            Some(c) => c,
            None => return,
        };
        if !cfg.enabled || !cfg.hours.contains(&h) {
            return;
        }

        *last_fired = Some(key);
        info!(
            "prime poller: tick at {}:{:02}, model = {}",
            h, TRIGGER_MINUTE, cfg.model
        );
        self.run_round(h, &cfg.model, cfg.message_body_order_fingerprint_enabled)
            .await;
    }

    /// 读取并解析设置,解析失败或总开关关闭返回 None。
    async fn load_config(&self) -> Option<PrimeConfig> {
        let all = match self.settings_store.get_all().await {
            Ok(a) => a,
            Err(e) => {
                warn!("prime poller: load settings failed: {}", e);
                return None;
            }
        };

        let enabled = peak_prime_enabled(&all);
        let hours_raw = all
            .get("peak_prime_hours")
            .cloned()
            .unwrap_or_else(|| "4,5,6".to_string());
        let hours: Vec<u32> = hours_raw
            .split(',')
            .filter_map(|s| s.trim().parse::<u32>().ok())
            .filter(|h| *h < 24)
            .collect();
        let model = all
            .get("peak_prime_model")
            .cloned()
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "claude-haiku-4-5-20251001".to_string());
        let message_body_order_fingerprint_enabled = all
            .get("message_body_order_fingerprint_enabled")
            .map(|s| s == "true")
            .unwrap_or(DEFAULT_MESSAGE_BODY_ORDER_FINGERPRINT_ENABLED == "true");

        Some(PrimeConfig {
            enabled,
            hours,
            model,
            message_body_order_fingerprint_enabled,
        })
    }

    /// 对所有活跃账号依次发起预热请求,账号间间隔 PER_ACCOUNT_GAP。
    /// 仍处于 429 冷却期的账号会被跳过(避免续命式延长冷却),但仍写入 skip 日志。
    async fn run_round(
        &self,
        hour: u32,
        model: &str,
        message_body_order_fingerprint_enabled: bool,
    ) {
        let accounts = match self.account_svc.list_accounts().await {
            Ok(list) => list,
            Err(e) => {
                warn!("prime poller: list accounts failed: {}", e);
                return;
            }
        };

        // 只看启用状态的账号;disabled/error 与预热无关。
        // 冷却期判断在循环内做,因为要记 skip 日志。
        let targets: Vec<Account> = accounts
            .into_iter()
            .filter(|a| a.status == AccountStatus::Active)
            .collect();

        debug!("prime poller: evaluating {} active accounts", targets.len());

        for account in targets {
            let triggered_at = chrono::Local::now().to_rfc3339();
            let outcome = if account.is_schedulable() {
                self.prime_one(&account, model, message_body_order_fingerprint_enabled)
                    .await
            } else {
                // 处于速率冷却期,不发请求,但在日志里留痕,便于排查"今天没预热"的原因。
                let reset = account
                    .rate_limit_reset_at
                    .map(|t| t.to_rfc3339())
                    .unwrap_or_else(|| "unknown".into());
                PrimeOutcome {
                    success: false,
                    error_message: format!("skipped: rate-limited until {}", reset),
                    duration_ms: 0,
                    passive_usage: None,
                    usage_observation_kind: UsageObservationKind::Allowed,
                    status: None,
                    failed_access_token: None,
                }
            };

            // 落日志:success/skipped 用 info,真失败用 warn;跳过是预期行为,不该算告警。
            if outcome.success {
                info!(
                    "prime: account={} hour={} model={} success=true duration={}ms",
                    account.id, hour, model, outcome.duration_ms
                );
            } else if outcome.error_message.starts_with("skipped:") {
                info!(
                    "prime: account={} hour={} model={} {}",
                    account.id, hour, model, outcome.error_message
                );
            } else {
                warn!(
                    "prime: account={} hour={} model={} success=false duration={}ms error={}",
                    account.id, hour, model, outcome.duration_ms, outcome.error_message
                );
            }

            let entry = PrimeLogEntry {
                id: 0,
                account_id: account.id,
                account_name: account.name.clone(),
                triggered_at,
                hour: hour as i32,
                model: model.to_string(),
                success: outcome.success,
                error_message: outcome.error_message.clone(),
                duration_ms: outcome.duration_ms,
            };
            if let Err(e) = self.log_store.insert(&entry).await {
                warn!(
                    "prime poller: write log failed for account {}: {}",
                    account.id, e
                );
            }

            // 根据上游状态码联动账号状态,保持与主链路 gateway 一致:
            // - 401: OAuth 已在 prime_one 内尝试恢复一次,最终仍失败则停用账号。
            // - 429: 调用 handle_rate_limit,按账号类型/用量设置冷却窗口。
            // - 403: 若未处于 429 冷却期则永久停用,避免坏账号继续被真实流量选中。
            if let Some(code) = outcome.status {
                let rate_limit_usage = outcome.passive_usage.as_ref().map(|usage| {
                    outcome
                        .usage_observation_kind
                        .rejected_usage(usage)
                        .unwrap_or_else(|| serde_json::json!({}))
                });
                self.apply_status_side_effects(
                    &account,
                    code,
                    rate_limit_usage,
                    outcome.failed_access_token.as_deref(),
                )
                .await;
            }

            // 成功和 429 都只使用响应头被动采集；普通错误不更新窗口。
            if let (Some(status), Some(usage)) = (outcome.status, outcome.passive_usage) {
                let kind = if status == 429 {
                    Some(outcome.usage_observation_kind)
                } else if (200..300).contains(&status) {
                    Some(UsageObservationKind::Allowed)
                } else {
                    None
                };
                if let Some(kind) = kind {
                    if let Err(e) = self
                        .account_svc
                        .update_passive_usage(account.id, usage, kind)
                        .await
                    {
                        warn!(
                            "prime poller: update passive usage failed for account {}: {}",
                            account.id, e
                        );
                    }
                }
            }

            sleep(PER_ACCOUNT_GAP).await;
        }
    }

    /// 根据上游 HTTP 状态码联动账号状态。
    ///
    /// 与 `src/service/gateway.rs:359/369` 的处理保持一致:
    /// - 401 → 停用凭据已失效的账号;
    /// - 429 → `handle_rate_limit` 按类型/用量设置冷却;
    /// - 403 且未处于 429 冷却期 → `disable_account` 永久停用,防止真实流量继续选中。
    async fn apply_status_side_effects(
        &self,
        account: &Account,
        status: u16,
        passive_usage: Option<serde_json::Value>,
        failed_access_token: Option<&str>,
    ) {
        if status == 401 {
            let reason = match account.auth_type {
                AccountAuthType::Oauth => "401 OAuth 认证失败",
                AccountAuthType::SetupToken => "401 SetupToken 认证失败",
            };
            let result = if account.auth_type == AccountAuthType::Oauth {
                let Some(token) = failed_access_token else {
                    return;
                };
                self.account_svc
                    .disable_oauth_for_failed_token(account.id, token, reason)
                    .await
            } else {
                self.account_svc
                    .disable_for_auth_failure(account.id, reason)
                    .await
                    .map(|_| true)
            };
            if let Err(e) = result {
                warn!(
                    "prime poller: disable_for_auth_failure failed for account {}: {}",
                    account.id, e
                );
            } else if matches!(result, Ok(true)) {
                warn!(
                    "prime poller: account {} disabled after upstream 401",
                    account.id
                );
            }
            return;
        }
        if status == 429 {
            // 预热请求体极小,不会触发长上下文计费类 429；直接使用本次响应头判断窗口。
            match self
                .account_svc
                .handle_rate_limit(account, None, "", passive_usage)
                .await
            {
                Ok(RateLimitDecision::RequestBackoff(delay)) => {
                    info!(
                        "prime poller: transient 429 for account {}, no account quarantine, suggested delay {}s",
                        account.id,
                        delay.as_secs()
                    );
                }
                Ok(
                    RateLimitDecision::Quarantined
                    | RateLimitDecision::RetryOtherAccount
                    | RateLimitDecision::PassThrough,
                ) => {}
                Err(e) => warn!(
                    "prime poller: handle_rate_limit failed for account {}: {}",
                    account.id, e
                ),
            }
            return;
        }
        if status == 403 {
            // 账号可能已在 429 冷却期,此时 403 是冷却期的副作用响应,不做停用。
            // 该判断与 gateway.rs 完全一致,避免误判断账号。
            let is_rate_limited = account
                .rate_limit_reset_at
                .map(|reset| Utc::now() < reset)
                .unwrap_or(false);
            if is_rate_limited {
                warn!(
                    "prime poller: account {} got 403 while rate-limited, skipping disable",
                    account.id
                );
                return;
            }
            if let Err(e) = self
                .account_svc
                .disable_account(account.id, AccountStatus::Disabled, "403 认证失败", None)
                .await
            {
                warn!(
                    "prime poller: disable_account failed for account {}: {}",
                    account.id, e
                );
            } else {
                warn!(
                    "prime poller: account {} permanently disabled for 403",
                    account.id
                );
            }
        }
    }

    /// 对单个账号执行一次预热请求,不抛错,所有结果都归并到 PrimeOutcome。
    async fn prime_one(
        &self,
        account: &Account,
        model: &str,
        message_body_order_fingerprint_enabled: bool,
    ) -> PrimeOutcome {
        let mut cutover = system_update::InferenceCutover::subscribe();
        let _update_activity = match system_update::admission() {
            Ok(activity) => activity,
            Err(_) => {
                return PrimeOutcome {
                    success: false,
                    error_message: "平台维护中，预热等待下次计划".into(),
                    duration_ms: 0,
                    passive_usage: None,
                    usage_observation_kind: UsageObservationKind::Allowed,
                    status: None,
                    failed_access_token: None,
                };
            }
        };
        let started = Instant::now();
        let deadline = TokioInstant::now() + PRIME_TTFB_TIMEOUT;
        // 使用实际生效的后端，并让路由读锁覆盖预热，等待中的切换继续由原门禁管理。
        let route = timeout_at(
            deadline,
            tui_backend::request_route(&self.account_svc, account.clone(), None),
        );
        let (account, route) = match route.await {
            Ok(Ok(route)) => route,
            Ok(Err(error)) => return Self::v2_outcome(started, Err(error)),
            Err(_) => {
                return Self::v2_outcome(
                    started,
                    Err(AppError::AdmissionLimited { retry_after: 1 }),
                );
            }
        };
        if account.request_backend == TUI_V2 {
            let result = match route {
                Some(route) => tokio::select! {
                    biased;
                    _ = cutover.cancelled() => Err(AppError::ServiceUnavailable("平台维护取消 V2 预热".into())),
                    result = self.prime_v2(&account, &route, model, deadline) => result,
                },
                None => Err(AppError::ServiceUnavailable("V2 预热路由未登记".into())),
            };
            self.account_svc.notify_tui_response_retired(account.id);
            return Self::v2_outcome(started, result);
        }
        let account = &account;
        let _credential_activity = match self.account_svc.upstream_activity(account.id).await {
            Ok(permit) => permit,
            Err(_) => {
                return PrimeOutcome {
                    success: false,
                    error_message: "skipped: credential ownership unavailable".into(),
                    duration_ms: 0,
                    passive_usage: None,
                    usage_observation_kind: UsageObservationKind::Allowed,
                    status: None,
                    failed_access_token: None,
                };
            }
        };

        // 取账号凭证(OAuth 会自动刷新,SetupToken 直接返回)。
        let mut token = match self.account_svc.resolve_upstream_token(account.id).await {
            Ok(t) => t,
            Err(e) => {
                return PrimeOutcome {
                    success: false,
                    error_message: truncate_chars(
                        &format!("resolve token: {}", e),
                        ERROR_SNIPPET_CHARS,
                    ),
                    duration_ms: started.elapsed().as_millis() as i64,
                    passive_usage: None,
                    usage_observation_kind: UsageObservationKind::Allowed,
                    status: None,
                    failed_access_token: None,
                };
            }
        };

        // v3 的后台推理也遵守账号占用；permit 保持至整条响应耗尽。
        let _runtime_permit = if !std::env::var("V3_RUNTIME_URL")
            .unwrap_or_default()
            .is_empty()
        {
            let queue = self
                .account_svc
                .get_or_create_queue(account.id, account.concurrency)
                .await;
            match queue.acquire(Duration::from_secs(1), 1).await {
                Ok(permit) => Some(permit),
                Err(_) => {
                    return PrimeOutcome {
                        success: false,
                        error_message: "account runtime occupied".into(),
                        duration_ms: started.elapsed().as_millis() as i64,
                        passive_usage: None,
                        usage_observation_kind: UsageObservationKind::Allowed,
                        status: None,
                        failed_access_token: None,
                    };
                }
            }
        } else {
            None
        };

        // 构造最小请求体,其余字段交给 rewriter 补全,保证与真实 Claude Code 流量对齐:
        // - metadata.user_id 由 rewriter 注入 {device_id, account_uuid, session_id} JSON 字符串
        // - system prompt、tools、stream=true、去除 temperature 等由 rewriter 统一规范化
        let minimal_body = prime_messages(model);
        let minimal_bytes = match serde_json::to_vec(&minimal_body) {
            Ok(b) => b,
            Err(e) => {
                return PrimeOutcome {
                    success: false,
                    error_message: truncate_chars(
                        &format!("serialize body: {}", e),
                        ERROR_SNIPPET_CHARS,
                    ),
                    duration_ms: started.elapsed().as_millis() as i64,
                    passive_usage: None,
                    usage_observation_kind: UsageObservationKind::Allowed,
                    status: None,
                    failed_access_token: None,
                };
            }
        };
        // 预热请求走注入模式(ClientType::API),不触发系统提示词环境改写,
        // 故环境透传开关在此无影响,传默认值即可。
        let native = account.request_backend == "native293";
        // 原生账号由CLI装配普通API输入，避免先经旧改写器注入另一套system与身份。
        let rewritten_bytes = if native {
            minimal_bytes
        } else {
            self.rewriter.rewrite_body(
                &minimal_bytes,
                "/v1/messages",
                account,
                ClientType::API,
                EnvPassthrough::default(),
                CacheControlTtlRewrite::Off,
                MessageCacheControlRewrite::Off,
                message_body_order_fingerprint_enabled,
            )
        };
        // rewriter 已把 metadata.user_id 写成最终上游 body；header 直接从同一字段提取 session_id。
        let body_value: serde_json::Value =
            serde_json::from_slice(&rewritten_bytes).unwrap_or(serde_json::Value::Null);

        let empty_in: std::collections::HashMap<String, String> = std::collections::HashMap::new();
        let mut headers = if native {
            HashMap::new()
        } else {
            self.rewriter.rewrite_headers(
                &empty_in,
                "/v1/messages",
                account,
                ClientType::API,
                model,
                &body_value,
            )
        };
        headers.insert("authorization".into(), format!("Bearer {}", token));

        let mut resp = match self
            .send_prime_upstream(account, &headers, &rewritten_bytes)
            .await
        {
            Ok(resp) => resp,
            Err(error_message) => {
                return PrimeOutcome {
                    success: false,
                    error_message,
                    duration_ms: started.elapsed().as_millis() as i64,
                    passive_usage: None,
                    usage_observation_kind: UsageObservationKind::Allowed,
                    status: None,
                    failed_access_token: None,
                };
            }
        };

        if resp.status().as_u16() == 401 && account.auth_type == AccountAuthType::Oauth {
            drop(resp);
            let refreshed_token = match self
                .account_svc
                .recover_upstream_token_after_unauthorized(account.id, &token)
                .await
            {
                Ok(token) => token,
                Err(e) => {
                    warn!(
                        "prime poller: OAuth recovery failed for account {} after 401: {}",
                        account.id, e
                    );
                    return PrimeOutcome {
                        success: false,
                        error_message: "http 401: OAuth 认证恢复失败".into(),
                        duration_ms: started.elapsed().as_millis() as i64,
                        passive_usage: None,
                        usage_observation_kind: UsageObservationKind::Allowed,
                        status: Some(401),
                        failed_access_token: Some(token),
                    };
                }
            };
            headers.insert(
                "authorization".into(),
                format!("Bearer {}", refreshed_token),
            );
            token = refreshed_token;
            resp = match self
                .send_prime_upstream(account, &headers, &rewritten_bytes)
                .await
            {
                Ok(resp) => resp,
                Err(error_message) => {
                    return PrimeOutcome {
                        success: false,
                        error_message,
                        duration_ms: started.elapsed().as_millis() as i64,
                        passive_usage: None,
                        usage_observation_kind: UsageObservationKind::Allowed,
                        status: None,
                        failed_access_token: None,
                    };
                }
            };
        }

        let status_code = resp.status().as_u16();
        let passive_usage = extract_passive_usage(resp.headers());
        let usage_observation_kind = if status_code == 429 {
            UsageObservationKind::RejectedWindows(extract_rejected_passive_usage_windows(
                resp.headers(),
            ))
        } else {
            UsageObservationKind::Allowed
        };

        // 调试日志：打印预热响应中的 rate limit header 和解析结果，
        // 用于排查"预热成功但账号未进入 5h 窗口"问题。
        {
            let get_hdr = |n: &str| -> Option<String> {
                resp.headers()
                    .get(n)
                    .and_then(|v| v.to_str().ok())
                    .map(|s| s.to_string())
            };
            let h5u = get_hdr("anthropic-ratelimit-unified-5h-utilization");
            let h5r = get_hdr("anthropic-ratelimit-unified-5h-reset");
            let h7u = get_hdr("anthropic-ratelimit-unified-7d-utilization");
            let h7r = get_hdr("anthropic-ratelimit-unified-7d-reset");
            let h7fu = get_hdr("anthropic-ratelimit-unified-7d_oi-utilization");
            let h7fr = get_hdr("anthropic-ratelimit-unified-7d_oi-reset");
            info!(
                "prime: account={} http={} passive_captured={} \
                 5h_util={:?} 5h_reset={:?} 7d_util={:?} 7d_reset={:?} \
                 7d_oi_util={:?} 7d_oi_reset={:?}",
                account.id,
                status_code,
                passive_usage.is_some(),
                h5u,
                h5r,
                h7u,
                h7r,
                h7fu,
                h7fr,
            );
        }

        if resp.status().is_success() {
            // rewriter 强制 stream=true,若此刻立即 drop 会在首包就中断 SSE,
            // 上游是否计入 5h 窗口、计入几个 token 不可靠,duration 也退化成 TTFB。
            // 这里必须耗尽整个响应流,上游才会把本次调用完整计入 5h 窗口。
            // 带 60s 超时保护,避免极端情况下卡住整轮预热。
            match tokio::time::timeout(PRIME_DRAIN_TIMEOUT, resp.bytes()).await {
                Ok(Ok(_)) => {}
                Ok(Err(e)) => warn!(
                    "prime: account={} body drain error: {} (5h window likely still triggered)",
                    account.id, e
                ),
                Err(_) => warn!(
                    "prime: account={} body drain timeout after {}s (headers already received)",
                    account.id,
                    PRIME_DRAIN_TIMEOUT.as_secs()
                ),
            }
            PrimeOutcome {
                success: true,
                error_message: String::new(),
                duration_ms: started.elapsed().as_millis() as i64,
                passive_usage,
                usage_observation_kind,
                status: Some(status_code),
                failed_access_token: if status_code == 401 {
                    Some(token)
                } else {
                    None
                },
            }
        } else {
            // 按字符(不是字节)截断,避免多字节 UTF-8 切片 panic 把整个后台任务打掉。
            let snippet = match resp.text().await {
                Ok(t) if !t.is_empty() => truncate_chars(&t, ERROR_SNIPPET_CHARS),
                _ => String::new(),
            };
            PrimeOutcome {
                success: false,
                error_message: format!("http {}: {}", status_code, snippet),
                duration_ms: started.elapsed().as_millis() as i64,
                passive_usage,
                usage_observation_kind,
                status: Some(status_code),
                failed_access_token: if status_code == 401 {
                    Some(token)
                } else {
                    None
                },
            }
        }
    }

    /// 按目标账号后端发送一次预热，保留原账号的凭据与故障归属。
    /// @param account 本轮目标账号。
    /// @param headers 本次授权及旧转发所需请求头。
    /// @param body 按后端选定的普通API输入或已改写字节。
    /// @return 上游响应或有界发送错误。
    async fn send_prime_upstream(
        &self,
        account: &Account,
        headers: &std::collections::HashMap<String, String>,
        body: &[u8],
    ) -> Result<reqwest::Response, String> {
        if account.request_backend == "native293" {
            // 外层约束准备与首响应，sender总截止另含耗流预算，避免首包后提前截断。
            let started = Instant::now();
            let operation = async {
                let transport = runtime_transport::prepare(account, PRIME_TTFB_TIMEOUT)
                    .await
                    .map_err(|_| "原生运行环境准备不可用".to_string())?;
                transport
                    .native_ready()
                    .await
                    .map_err(|_| "原生运行时能力不可用".to_string())?;
                let bearer = headers
                    .get("authorization")
                    .and_then(|value| value.strip_prefix("Bearer "))
                    .filter(|value| !value.is_empty())
                    .ok_or_else(|| "原生预热授权不可用".to_string())?;
                let id = Uuid::new_v4().to_string();
                let body_value: Value =
                    serde_json::from_slice(body).map_err(|_| "原生预热输入无效".to_string())?;
                // beta查询参数由原生SDK负责，私有信封仅接纳固定Messages入口。
                let target_url = self
                    .upstream_url
                    .strip_suffix("?beta=true")
                    .unwrap_or(&self.upstream_url)
                    .to_string();
                let submission = NativeSubmission {
                    source_version: NativeSourceVersion::Cc293,
                    cache_ttl_rewrite: None,
                    message_cache_policy: None,
                    ingress_capture: None,
                    log_mode: RequestLogMode::Info,
                    request: PreparedRequest {
                        tls_profile: tls_profile_for_account(
                            account,
                            configured_default_tls_profile(),
                        ),
                        account_id: account.id,
                        environment_id: String::new(),
                        generation: 0,
                        request_id: id.clone(),
                        deadline_unix_ms: 0,
                        method: "POST".into(),
                        target_url,
                        headers: Vec::new(),
                        preserve_header_casing: false,
                    },
                    input: serde_json::json!({"schema_version":1,"request_id":id,"body":body_value}),
                    bearer: bearer.into(),
                    device_id: account.device_id.clone(),
                    account_uuid: account.account_uuid.clone(),
                    organization_uuid: account.organization_uuid.clone(),
                    email: account.email.clone(),
                    concurrency: account.concurrency,
                };
                transport
                    .submit_native(
                        submission,
                        (PRIME_TTFB_TIMEOUT + PRIME_DRAIN_TIMEOUT)
                            .saturating_sub(started.elapsed()),
                    )
                    .await
                    .map_err(|_| "原生预热提交状态未知".to_string())
            };
            return timeout(PRIME_TTFB_TIMEOUT, operation)
                .await
                .map_err(|_| "原生预热首响应超时".to_string())?;
        }
        let prepared = PreparedRequest {
            tls_profile: tls_profile_for_account(account, configured_default_tls_profile()),
            account_id: account.id,
            environment_id: String::new(),
            generation: 0,
            request_id: String::new(),
            deadline_unix_ms: 0,
            method: "POST".into(),
            target_url: self.upstream_url.clone(),
            headers: ordered_anthropic_headers("/v1/messages", headers),
            preserve_header_casing: false,
        };
        runtime_transport::send(account, prepared, body, PRIME_TTFB_TIMEOUT)
            .await
            .map_err(|error| {
                if error.to_string().contains("TTFB timeout") {
                    "upstream TTFB timeout".into()
                } else {
                    "upstream submission status unknown".into()
                }
            })
    }

    /// 只对本次调度的账号准备和提交一个 V2 回环轮次。
    /// @param account 生效账号。@param route 同轮路由快照。@param model 管理员配置的模型。
    /// @param deadline 峰值预热从路由解析开始的首响应期限。
    /// @return 完整 SSE 终态或可写入原预热日志的失败。
    async fn prime_v2(
        &self,
        account: &Account,
        route: &TuiRequestRoute,
        model: &str,
        deadline: TokioInstant,
    ) -> Result<(), AppError> {
        if runtime_transport::tui_fixture(account) {
            return Err(AppError::ServiceUnavailable(
                "V2 峰值预热需要已登记的正式账号发送器".into(),
            ));
        }
        let scheduler = self
            .account_svc
            .scheduler()
            .ok_or_else(|| AppError::ServiceUnavailable("V2 预热需要 v3 调度".into()))?;
        // 后台任务没有可绑定的客户端会话；发送许可仍计入该账号的正常 RPM。
        let request = scheduler.begin(0, None);
        let deadline = request.deadline().min(deadline);
        let timeout_error = || AppError::AdmissionLimited { retry_after: 1 };
        let body = prime_messages(model);
        let mut observer = UsageCapture::observer(&body);
        let prepared_run = timeout_at(deadline, async {
            let settings = self.settings_store.get_all().await?;
            if !peak_prime_enabled(&settings) {
                return Err(AppError::ServiceUnavailable("峰值预热已关闭".into()));
            }
            let selection = AccountSelectionContext {
                usage_limits_enabled: true,
                fable_quota_fallback_enabled: settings
                    .get("fable_sticky_quota_fallback_enabled")
                    .map(String::as_str)
                    .unwrap_or(DEFAULT_FABLE_STICKY_QUOTA_FALLBACK_ENABLED)
                    .trim()
                    == "true",
                fable_weekly_usage_limit_percent: parse_fable_weekly_usage_limit_percent(
                    settings
                        .get("fable_weekly_usage_limit_percent")
                        .map(String::as_str)
                        .unwrap_or(DEFAULT_FABLE_WEEKLY_USAGE_LIMIT_PERCENT),
                ),
                request_model: Some(model.to_owned()),
            };
            let slot_units = request_slot_units("/v1/messages", &body);
            let account = self
                .account_svc
                .select_v3_account(&request, &[], &[account.id], &selection, slot_units)
                .await?
                .account;
            let work = self.account_svc.work_controls.admit(account.id).await?;
            let activity = self.account_svc.upstream_activity(account.id).await?;
            request.phase(RequestPhase::Backoff);
            self.account_svc
                .wait_transient_rate_limit_backoff(&account)
                .await;
            request.phase(RequestPhase::Preparing);
            if route.binding.is_empty() {
                return Err(runtime_transport::tui_unbound(&account).await);
            }
            let wake = route
                .may_wake_v2(&self.account_svc, &account, false)
                .await?;
            let sender =
                runtime_transport::ready_tui_sender(&account, deadline, wake, None).await?;
            let (binding, _, _) = route
                .begin_v2(
                    &self.account_svc,
                    &account,
                    None,
                    &body,
                    &sender,
                    false,
                    None,
                    None,
                )
                .await?;
            let session = format!("{SERVER_SESSION_PREFIX}prime-{}", Uuid::new_v4());
            let bytes = Bytes::from(
                serde_json::to_vec(&body)
                    .map_err(|_| AppError::Internal("V2 预热请求编码失败".into()))?,
            );
            let prepared = runtime_transport::prepare_tui(
                sender,
                TUI_PRIME_PRINCIPAL,
                &session,
                TuiMessagesInput {
                    body: &bytes,
                    headers: &HeaderMap::new(),
                    native_cc: false,
                    signature_repair: None,
                    agent_summary: false,
                    oauth_file: account.auth_type == AccountAuthType::Oauth,
                    body_policy: TuiBodyPolicy::default(),
                    system_prompt_policy: Default::default(),
                },
                deadline,
                false,
            )
            .await?;
            if prepared.continuation {
                return Err(AppError::ServiceUnavailable("V2 预热预留类别错误".into()));
            }

            request.phase(RequestPhase::WaitingConcurrency);
            let queue = self
                .account_svc
                .get_or_create_queue(account.id, account.concurrency)
                .await;
            let slot = queue
                .acquire(
                    deadline.saturating_duration_since(TokioInstant::now()),
                    slot_units,
                )
                .await
                .map_err(|_| timeout_error())?
                .with_scheduling_request(request.clone())
                .with_work_admission(work);
            // 等待物理进程或发送队列期间，账号可能新增冷却或耗尽窗口。
            let current = self.account_svc.get_account(account.id).await?;
            if !current.is_schedulable()
                || account_usage_limit_reached(&current)
                || (selection.is_fable_quota_fallback_active()
                    && account_fable_weekly_usage_limit_reached(
                        &current,
                        selection.fable_weekly_usage_limit_percent,
                    ))
            {
                return Err(AppError::TooManyRequests(
                    "V2 预热账号达到用量控制线或不再可调度".into(),
                ));
            }
            let work = self.account_svc.work_controls.snapshot(account.id).await?;
            if !work.api_accepting || !work.work_enabled {
                return Err(AppError::ServiceUnavailable("该账号已关闭 API 接单".into()));
            }
            let (credentials, failed_token, _resolution) = prepared
                .resolve_account_credentials(&self.account_svc, false)
                .await?;
            let send = request.admit(&account).await?;
            let config = route
                .allow_submit(&self.account_svc, account.id, &binding, false)
                .await?;
            if !peak_prime_enabled(&self.settings_store.get_all().await?) {
                return Err(AppError::ServiceUnavailable("V2 峰值预热已取消".into()));
            }
            Ok::<_, AppError>((
                prepared,
                credentials,
                failed_token,
                slot,
                activity,
                send,
                config,
            ))
        })
        .await
        .map_err(|_| timeout_error())??;
        let (mut prepared, credentials, failed_token, _slot, _activity, send, config) =
            prepared_run;
        if deadline <= TokioInstant::now() {
            return Err(timeout_error());
        }
        send.submitted();
        drop(config);
        // 发送开始后由 sender 持有单次预留。私有首包超时仍保留提交状态未知。
        let mut response = prepared
            .submit_with_account_credentials(deadline, credentials, None)
            .await?;
        runtime_transport::recover_tui_oauth_after_response(
            &self.account_svc,
            account.id,
            failed_token,
            &response,
        )
        .await;

        let status = response.status();
        if !status.is_success() {
            return Err(AppError::BadGateway(format!(
                "V2 模型源 HTTP {}",
                status.as_u16()
            )));
        }
        observer.configure_codings(&response_content_codings(response.headers()));
        timeout(PRIME_DRAIN_TIMEOUT, async {
            while let Some(bytes) = response
                .chunk()
                .await
                .map_err(|_| AppError::BadGateway("V2 预热响应中断".into()))?
            {
                observer.observe(&bytes);
            }
            let observed = observer.observation(true);
            if observed.partial || observed.error_type.is_some() || observed.policy_reason.is_some()
            {
                return Err(AppError::BadGateway(
                    "V2 预热未成功完成 Messages 响应".into(),
                ));
            }
            Ok(())
        })
        .await
        .map_err(|_| AppError::BadGateway("V2 预热响应读取超时".into()))?
    }

    /// 隔离本机源的结果与旧 OAuth 联动字段。@param started 起点。@param result 终态。
    /// @return 原预热记录所需的数据。
    fn v2_outcome(started: Instant, result: Result<(), AppError>) -> PrimeOutcome {
        PrimeOutcome {
            success: result.is_ok(),
            error_message: result.err().map_or_else(String::new, |error| {
                truncate_chars(&error.to_string(), ERROR_SNIPPET_CHARS)
            }),
            duration_ms: started.elapsed().as_millis() as i64,
            passive_usage: None,
            usage_observation_kind: UsageObservationKind::Allowed,
            status: None,
            failed_access_token: None,
        }
    }

    /// 驱动隔离原生回环中的完整预热轮次。
    /// @param hour 合成触发小时。
    /// @param model 本轮预热模型。
    /// @return 无；结果沿正式日志存储核验。
    #[cfg(test)]
    pub(crate) async fn test_run_round(&self, hour: u32, model: &str) {
        self.run_round(hour, model, true).await;
    }
}

/// 按峰值调度的既有语义解析总开关。@param settings 同次读取的设置。@return 峰值任务已启用。
fn peak_prime_enabled(settings: &HashMap<String, String>) -> bool {
    settings
        .get("peak_prime_enabled")
        .is_none_or(|value| value == "true")
}

/// 生成既有预热的普通 Messages 输入。@param model 峰值设置选择的模型。@return 预热正文。
fn prime_messages(model: &str) -> Value {
    serde_json::json!({
        "model": model,
        "messages": [{
            "role": "user",
            "content": [{ "type": "text", "text": "hi" }]
        }],
        "max_tokens": 512,
        "stream": true
    })
}

/// 按字符截断字符串,避免直接字节切片在多字节字符上 panic。
fn truncate_chars(s: &str, max_chars: usize) -> String {
    if s.chars().count() <= max_chars {
        return s.to_string();
    }
    s.chars().take(max_chars).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::account::{
        AccountStatus, BillingMode, DEFAULT_ALLOW_1M_MODELS, DEFAULT_UPSTREAM_SESSION_POOL_SIZE,
        DEFAULT_UPSTREAM_SESSION_REFRESH_POLICY, DEFAULT_UPSTREAM_SESSION_TTL_MINUTES,
    };
    use crate::service::runtime_transport::TUI_BODY_POLICY;
    use crate::store::account_store::AccountStore;
    use crate::store::memory::MemoryStore;
    use axum::extract::State;
    use axum::http::HeaderMap;
    use axum::response::{IntoResponse, Response};
    use axum::routing::post;
    use axum::{Json, Router};
    use serde_json::json;
    use sqlx::AnyPool;
    use std::sync::atomic::{AtomicUsize, Ordering};

    /// 核对存量值和缺省配置。@return V1、V2 读取同一设置语义。
    #[test]
    fn prime_setting_preserves_existing_values_and_default() {
        assert!(peak_prime_enabled(&HashMap::new()));
        for (value, expected) in [("true", true), ("false", false), ("", false)] {
            let settings = HashMap::from([("peak_prime_enabled".into(), value.into())]);
            assert_eq!(peak_prime_enabled(&settings), expected);
        }
    }

    /// 读取私有路径计数。@param client 回环客户端。@param base 夹具地址。@return prepare、send、cancel 数。
    async fn prime_fixture_counts(client: &reqwest::Client, base: &str) -> [usize; 3] {
        client
            .get(format!("{base}/counts"))
            .send()
            .await
            .unwrap()
            .json()
            .await
            .unwrap()
    }

    async fn setup_prime_poller() -> (PrimePollerService, Arc<AccountService>) {
        setup_prime_poller_with_urls(
            UPSTREAM_URL.to_string(),
            crate::service::oauth::OAUTH_TOKEN_URL.to_string(),
        )
        .await
    }

    async fn setup_prime_poller_with_urls(
        upstream_url: String,
        oauth_token_url: String,
    ) -> (PrimePollerService, Arc<AccountService>) {
        setup_poller(upstream_url, oauth_token_url, false).await
    }

    async fn setup_poller(
        upstream_url: String,
        oauth_token_url: String,
        v3: bool,
    ) -> (PrimePollerService, Arc<AccountService>) {
        sqlx::any::install_default_drivers();
        let tmp =
            std::env::temp_dir().join(format!("ccgw_prime_poller_{}.db", rand::random::<u64>()));
        let dsn = format!("sqlite:{}?mode=rwc", tmp.display());
        let pool = AnyPool::connect(&dsn).await.expect("pool");
        crate::store::db::migrate(&pool, "sqlite")
            .await
            .expect("migrate");

        let account_store = Arc::new(AccountStore::new(pool.clone(), "sqlite".into()));
        let settings_store = Arc::new(SettingsStore::new(pool.clone()));
        let mut account_svc = AccountService::new_with_oauth_token_url(
            account_store,
            Arc::new(MemoryStore::new()),
            settings_store.clone(),
            oauth_token_url,
        );
        if v3 {
            use crate::service::v3_scheduling::V3Scheduler;
            use crate::store::scheduling_store::SchedulingStore;
            let scheduler = Arc::new(V3Scheduler::new(Arc::new(SchedulingStore::new(
                pool.clone(),
            ))));
            scheduler.reload(&settings_store).await.unwrap();
            account_svc = account_svc.with_scheduler(scheduler);
        }
        let account_svc = Arc::new(account_svc);
        let mut service = PrimePollerService::new(
            account_svc.clone(),
            settings_store,
            Arc::new(PrimeLogStore::new(pool)),
            Arc::new(Rewriter::new()),
        );
        service.upstream_url = upstream_url;
        (service, account_svc)
    }

    /// 真实后台调度、数据库、入站账号核验和 HTTP 预留的回环测试。
    /// @return 暂存于独立进程的传输环境和普通测试进程隔离。
    #[tokio::test]
    async fn prime_v2_fixed_account_admission_and_reservation_lifecycle() {
        use axum::extract::{Path, Request};
        use axum::http::StatusCode;
        use axum::routing::{any, get};
        use base64::{Engine, engine::general_purpose::STANDARD};
        use sha2::{Digest, Sha256};
        use tokio::net::TcpListener;

        const TEST: &str = "service::prime_poller::tests::prime_v2_fixed_account_admission_and_reservation_lifecycle";
        const RELEASE: &str = "local-test-prime";
        const DEPLOYMENT: &str = "local-test-prime-deployment";
        const ENV_ID: &str = "0123456789abcdef0123456789abcdef";
        const NODE_ID: &str = "ffffffffffffffffffffffffffffffff";
        const CONTROL: &str = "local-test-control-not-a-secret";
        const SENDER: &str = "local-test-sender-not-a-secret-12345";
        const MODEL: &str = "claude-haiku-4-5-20251001";
        if let Ok(base) = std::env::var("FLOWER_PRIME_TEST_RELAY") {
            assert!(base.starts_with("http://127.0.0.1:"));
            let (service, accounts) = setup_poller(
                format!("{base}/legacy"),
                format!("{base}/legacy/oauth"),
                true,
            )
            .await;
            let mut account = oauth_account("prime-v2@example.test");
            account.concurrency = 1;
            account.rpm_limit = 0;
            accounts.create_account(&mut account).await.unwrap();
            let (binding, idle) = runtime_transport::tui_account_status(&account)
                .await
                .unwrap();
            assert!(idle);
            let before = accounts.tui_backend(account.id).await.unwrap();
            accounts
                .update_tui_backend(account.id, &before, TUI_V2, "", &binding)
                .await
                .unwrap();
            let service = Arc::new(service);

            // 保留库已初始化的旧开关，并用普通请求的缓存设置对照预热原文。
            assert_eq!(
                service
                    .settings_store
                    .get_value("peak_prime_enabled", "false")
                    .await
                    .unwrap(),
                "true",
            );
            service
                .settings_store
                .upsert_many(&HashMap::from([
                    ("peak_prime_hours".into(), "4".into()),
                    ("peak_prime_model".into(), MODEL.into()),
                    ("message_cache_control_rewrite".into(), "sub2api".into()),
                    ("cache_control_ttl_rewrite".into(), "1h".into()),
                ]))
                .await
                .unwrap();
            let now = Local::now().with_hour(4).unwrap().with_minute(10).unwrap();
            let mut fired = None;
            service.check_at(now, &mut fired).await;
            service.check_at(now, &mut fired).await;
            let logs = service.log_store.list_recent(10).await.unwrap();
            assert_eq!(logs.len(), 1);
            assert!(logs[0].success, "{}", logs[0].error_message);
            assert_eq!(
                (logs[0].account_id, logs[0].model.as_str()),
                (account.id, MODEL)
            );
            let client = reqwest::Client::builder().no_proxy().build().unwrap();
            let update_peak = |enabled: bool| {
                let service = service.clone();
                async move {
                    service
                        .settings_store
                        .upsert_many(&HashMap::from([(
                            "peak_prime_enabled".into(),
                            enabled.to_string(),
                        )]))
                        .await
                        .unwrap();
                }
            };
            update_peak(false).await;
            let mut disabled_scan = None;
            service.check_at(now, &mut disabled_scan).await;
            assert!(disabled_scan.is_none());
            assert_eq!(service.log_store.list_recent(10).await.unwrap().len(), 1);
            assert_eq!(prime_fixture_counts(&client, &base).await, [1, 1, 0]);

            update_peak(true).await;
            let queue = accounts
                .get_or_create_queue(account.id, account.concurrency)
                .await;
            let held_slot = queue.acquire(Duration::from_secs(1), 2).await.unwrap();
            let queued = tokio::spawn({
                let service = service.clone();
                let account = account.clone();
                async move { service.prime_one(&account, MODEL, true).await }
            });
            timeout(Duration::from_secs(10), async {
                while accounts.get_account_capacity_info(&account).await.queued == 0 {
                    sleep(Duration::from_millis(20)).await;
                }
            })
            .await
            .expect("等待准备成功后进入普通槽位队列");
            assert_eq!(prime_fixture_counts(&client, &base).await, [2, 1, 0]);
            update_peak(false).await;
            drop(held_slot);
            let outcome = queued.await.unwrap();
            assert!(!outcome.success);
            assert!(
                outcome.error_message.contains("预热已取消"),
                "{}",
                outcome.error_message
            );
            timeout(Duration::from_secs(5), async {
                while prime_fixture_counts(&client, &base).await != [2, 1, 1] {
                    sleep(Duration::from_millis(20)).await;
                }
            })
            .await
            .expect("关闭后取消原预留且没有第二次发送");
            // 外部隔离验收可用发行 sender 和容器内 TUI 执行同一生产任务。
            if std::env::var_os("FLOWER_PRIME_TEST_ACTUAL_SENDER").is_some() {
                return;
            }
            update_peak(true).await;

            use crate::service::account_work::AccountWorkUpdate;
            for accepting in [false, true] {
                accounts
                    .work_controls
                    .update(
                        account.id,
                        AccountWorkUpdate {
                            api_accepting: Some(accepting),
                            work_enabled: None,
                            expected_revision: None,
                        },
                    )
                    .await
                    .unwrap();
                if !accepting {
                    let outcome = service.prime_one(&account, MODEL, true).await;
                    assert!(!outcome.success);
                }
            }
            let mut quota_account = accounts.get_account(account.id).await.unwrap();
            quota_account.five_hour_usage_limit_percent = 50;
            accounts
                .update_account_usage_limits(&quota_account)
                .await
                .unwrap();
            accounts.update_passive_usage(account.id, json!({
                "five_hour": { "utilization": 80.0, "resets_at": (Utc::now() + chrono::Duration::hours(1)).to_rfc3339() }
            }), UsageObservationKind::Allowed).await.unwrap();
            let outcome = service.prime_one(&account, MODEL, true).await;
            assert!(!outcome.success);
            assert!(
                outcome.error_message.contains("用量上限"),
                "{}",
                outcome.error_message
            );
            quota_account.five_hour_usage_limit_percent = 0;
            accounts
                .update_account_usage_limits(&quota_account)
                .await
                .unwrap();

            for (mode, reason) in [
                ("401", "HTTP 401"),
                ("429", "HTTP 429"),
                ("incomplete", "未成功完成"),
                ("unready", "事件源"),
                ("wrong_binding", "绑定"),
            ] {
                client
                    .post(format!("{base}/mode/{mode}"))
                    .send()
                    .await
                    .unwrap()
                    .error_for_status()
                    .unwrap();
                let outcome = service.prime_one(&account, MODEL, true).await;
                assert!(!outcome.success);
                assert!(
                    outcome.error_message.contains(reason),
                    "{mode}: {}",
                    outcome.error_message
                );
                assert!(outcome.status.is_none());
                let stored = accounts.get_account(account.id).await.unwrap();
                assert_eq!(stored.status, AccountStatus::Active);
                assert_eq!(stored.access_token, account.access_token);
            }
            client.post(format!("{base}/mode/ok")).send().await.unwrap();
            let queue = accounts
                .get_or_create_queue(account.id, account.concurrency)
                .await;
            let slot = queue.acquire(Duration::from_secs(1), 2).await.unwrap();
            let polling = tokio::spawn({
                let service = service.clone();
                async move { service.prime_one(&account, MODEL, true).await }
            });
            timeout(Duration::from_secs(5), async {
                loop {
                    let counts = prime_fixture_counts(&client, &base).await;
                    if counts[0] == 6 {
                        assert_eq!(counts, [6, 4, 1], "槽位未归还时不得执行预热");
                        break;
                    }
                    sleep(Duration::from_millis(20)).await;
                }
            })
            .await
            .expect("等待真实 prepare 回执");
            polling.abort();
            assert!(matches!(polling.await, Err(error) if error.is_cancelled()));
            drop(slot);
            timeout(Duration::from_secs(5), async {
                while prime_fixture_counts(&client, &base).await != [6, 4, 2] {
                    sleep(Duration::from_millis(20)).await;
                }
            })
            .await
            .expect("任务取消后原预留必须归还");
            return;
        }

        #[derive(Clone)]
        struct Relay {
            endpoint: String,
            state: Arc<tokio::sync::Mutex<(String, Vec<(String, String)>)>>,
        }
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let deploy = format!("{:x}", Sha256::digest(DEPLOYMENT.as_bytes()));
        let relay_path = format!(
            "/cluster-transports/v2/{}/{NODE_ID}/{ENV_ID}/1",
            &deploy[..12]
        );
        let relay = Relay {
            endpoint: format!("{base}{relay_path}"),
            state: Default::default(),
        };
        let app = Router::new()
            .route("/internal/v3/transport/:id", get(|State(relay): State<Relay>, Path(id): Path<i64>, headers: HeaderMap| async move {
                assert_eq!(headers["authorization"], format!("Bearer {CONTROL}"));
                assert_eq!(id, 1);
                Json(json!({"account_id": id, "environment_id": ENV_ID, "generation": 1,
                    "release_id": RELEASE, "endpoint": relay.endpoint, "secret": SENDER}))
            }))
            .route(&format!("{relay_path}/internal/*action"), any(|State(relay): State<Relay>, Path(action): Path<String>, req: Request| async move {
                assert_eq!(req.headers()["authorization"], format!("Bearer {SENDER}"));
                assert_eq!(req.headers()["x-v3-relay-token"], CONTROL);
                let mut state = relay.state.lock().await;
                if action == "status" {
                    return Json(json!({
                        "environment_id": ENV_ID, "generation": if state.0 == "wrong_binding" { 2 } else { 1 }, "active":0,
                        "tui_v2":{"account_id":1,"release_id":RELEASE,"protocol":1,"ready":state.0 != "unready",
                            "event_source":"local_unix","idle":true,"direct_https_protocol":1,
                            "reason":"messages_tool_and_usage_events_unavailable"}
                    })).into_response();
                }
                let encoded = req.headers()["x-v3-tui-reservation"].as_bytes();
                let identity: Value = serde_json::from_slice(&STANDARD.decode(encoded).unwrap()).unwrap();
                assert_eq!((identity["account_id"].as_i64(), identity["principal_id"].as_i64()), (Some(1), Some(TUI_PRIME_PRINCIPAL)));
                assert!(identity["session_id"].as_str().unwrap().starts_with(SERVER_SESSION_PREFIX));
                assert_eq!(identity["continuation_only"], false);
                let id = identity["reservation_id"].as_str().unwrap().to_owned();
                assert!(!req.headers().contains_key(TUI_BODY_POLICY));
                if action == "tui-v2/prepare" {
                    assert_eq!(req.headers()[runtime_transport::TUI_DIRECT_HTTPS], "1");
                    assert_eq!(req.headers()[runtime_transport::TUI_OAUTH_FILE], "1");
                }
                if action == "tui-v2/send" {
                    assert!(req.headers().contains_key(runtime_transport::TUI_OAUTH_FILE));
                }
                let body = axum::body::to_bytes(req.into_body(), 4096).await.unwrap();
                if action == "tui-v2/prepare" {
                    assert_eq!(serde_json::from_slice::<Value>(&body).unwrap(), prime_messages(MODEL));
                    state.1.push(("prepare".into(), id));
                    return (StatusCode::NO_CONTENT, [("x-v3-tui-handoff-kind", "new"),
                        (runtime_transport::TUI_DIRECT_HTTPS, "1"), (runtime_transport::TUI_OAUTH_FILE, "1"),
                        (runtime_transport::TUI_MANAGED_OAUTH, "1")]).into_response();
                }
                assert!(body.is_empty());
                assert!(state.1.iter().any(|item| item == &("prepare".into(), id.clone())));
                if action == "tui-v2/cancel" {
                    state.1.push(("cancel".into(), id));
                    return StatusCode::NO_CONTENT.into_response();
                }
                assert_eq!(action, "tui-v2/send");
                assert!(!state.1.iter().any(|item| item == &("send".into(), id.clone())));
                state.1.push(("send".into(), id));
                if let Ok(status) = state.0.parse::<u16>() {
                    return StatusCode::from_u16(status).unwrap().into_response();
                }
                let start = "data: {\"type\":\"message_start\",\"message\":{\"id\":\"msg_prime\",\"usage\":{\"input_tokens\":2}}}\n\n";
                let stop = "data: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"end_turn\"},\"usage\":{\"output_tokens\":1}}\n\ndata: {\"type\":\"message_stop\"}\n\n";
                let sse = if state.0 == "incomplete" { start.to_owned() } else { format!("{start}{stop}") };
                ([("content-type", "text/event-stream")], sse).into_response()
            }))
            .route("/mode/:mode", post(|State(relay): State<Relay>, Path(mode): Path<String>| async move {
                relay.state.lock().await.0 = mode;
                StatusCode::NO_CONTENT
            }))
            .route("/counts", get(|State(relay): State<Relay>| async move {
                let state = relay.state.lock().await;
                Json(["prepare", "send", "cancel"].map(|action| state.1.iter().filter(|event| event.0 == action).count()))
            }))
            .route("/legacy/*path", any(|| async { panic!("V2 预热不得使用旧路径"); #[allow(unreachable_code)] StatusCode::BAD_GATEWAY }))
            .with_state(relay.clone());
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        let child = tokio::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", TEST, "--nocapture"])
            .env_clear()
            .env("FLOWER_PRIME_TEST_RELAY", &base)
            .env("V3_RUNTIME_URL", &base)
            .env("V3_INTERNAL_TOKEN", CONTROL)
            .env("V3_DEPLOYMENT_ID", DEPLOYMENT)
            .env("V3_RELEASE", RELEASE)
            .kill_on_drop(true)
            .status()
            .await
            .unwrap();
        assert!(child.success());
        timeout(Duration::from_secs(3), async {
            loop {
                let state = relay.state.lock().await;
                if state.1.last().is_some_and(|(kind, id)| {
                    kind == "cancel"
                        && state.1.len() == 12
                        && state
                            .1
                            .iter()
                            .rev()
                            .find(|event| event.0 == "prepare")
                            .is_some_and(|event| event.1 == *id)
                }) {
                    break;
                }
                drop(state);
                sleep(Duration::from_millis(20)).await;
            }
        })
        .await
        .expect("提交前取消应落到原预留");
        server.abort();
    }

    #[derive(Clone)]
    struct PrimeAuthMockState {
        accept_refreshed: bool,
        authorization_headers: Arc<tokio::sync::Mutex<Vec<String>>>,
        refresh_calls: Arc<AtomicUsize>,
    }

    /// 定时扫描遵守开关、小时、日期去重及活跃与冷却范围。
    /// @return 无；错误触发、重复记录或漏记跳过时失败。
    #[tokio::test]
    async fn prime_schedule_preserves_switch_hours_dedup_and_cooldown() {
        let (base_url, state, server) = spawn_prime_auth_mock_server(true).await;
        let (service, accounts) = setup_prime_poller_with_urls(
            format!("{base_url}/v1/messages"),
            format!("{base_url}/oauth/token"),
        )
        .await;
        let mut target = setup_token_account("prime-schedule@example.test");
        accounts.create_account(&mut target).await.unwrap();
        accounts
            .set_rate_limit(target.id, Utc::now() + chrono::Duration::hours(1))
            .await
            .unwrap();
        let mut disabled = setup_token_account("prime-disabled@example.test");
        disabled.status = AccountStatus::Disabled;
        accounts.create_account(&mut disabled).await.unwrap();
        let now = Local::now().with_hour(4).unwrap().with_minute(10).unwrap();
        let mut last = None;
        for (enabled, hours) in [("false", "4"), ("true", "5")] {
            service
                .settings_store
                .upsert_many(&HashMap::from([
                    ("peak_prime_enabled".into(), enabled.into()),
                    ("peak_prime_hours".into(), hours.into()),
                ]))
                .await
                .unwrap();
            service.check_at(now, &mut last).await;
            assert!(last.is_none());
            assert!(service.log_store.list_recent(200).await.unwrap().is_empty());
        }
        service
            .settings_store
            .upsert_many(&HashMap::from([("peak_prime_hours".into(), "4".into())]))
            .await
            .unwrap();
        service
            .check_at(now.with_minute(9).unwrap(), &mut last)
            .await;
        assert!(last.is_none());
        service.check_at(now, &mut last).await;
        service.check_at(now, &mut last).await;
        let entries = service.log_store.list_recent(200).await.unwrap();
        assert_eq!(entries.len(), 1);
        assert_eq!(entries[0].account_id, target.id);
        assert!(entries[0].error_message.starts_with("skipped:"));
        assert_eq!(entries[0].duration_ms, 0);
        service
            .check_at(now + chrono::Duration::days(1), &mut last)
            .await;
        assert_eq!(service.log_store.list_recent(200).await.unwrap().len(), 2);
        assert!(state.authorization_headers.lock().await.is_empty());
        server.abort();
    }

    async fn mock_prime_response(
        State(state): State<PrimeAuthMockState>,
        headers: HeaderMap,
    ) -> Response {
        let authorization = headers
            .get("authorization")
            .and_then(|value| value.to_str().ok())
            .unwrap_or_default()
            .to_string();
        state
            .authorization_headers
            .lock()
            .await
            .push(authorization.clone());

        if authorization == "Bearer access-refreshed" && state.accept_refreshed {
            return (
                axum::http::StatusCode::OK,
                Json(json!({
                    "id": "msg_prime",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type":"text","text":"ok"}],
                    "stop_reason": "end_turn"
                })),
            )
                .into_response();
        }

        (
            axum::http::StatusCode::UNAUTHORIZED,
            Json(json!({"type":"error","error":{"type":"authentication_error","message":"invalid token"}})),
        )
            .into_response()
    }

    async fn mock_prime_oauth_refresh(
        State(state): State<PrimeAuthMockState>,
    ) -> Json<serde_json::Value> {
        state.refresh_calls.fetch_add(1, Ordering::SeqCst);
        Json(json!({
            "access_token": "access-refreshed",
            "refresh_token": "refresh-refreshed",
            "expires_in": 3600
        }))
    }

    async fn spawn_prime_auth_mock_server(
        accept_refreshed: bool,
    ) -> (String, PrimeAuthMockState, tokio::task::JoinHandle<()>) {
        let state = PrimeAuthMockState {
            accept_refreshed,
            authorization_headers: Arc::new(tokio::sync::Mutex::new(Vec::new())),
            refresh_calls: Arc::new(AtomicUsize::new(0)),
        };
        let app = Router::new()
            .route("/v1/messages", post(mock_prime_response))
            .route("/oauth/token", post(mock_prime_oauth_refresh))
            .with_state(state.clone());
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
            .await
            .expect("bind prime mock server");
        let address = listener.local_addr().expect("prime mock server address");
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.expect("serve prime mock");
        });
        (format!("http://{}", address), state, server)
    }

    fn setup_token_account(email: &str) -> Account {
        Account {
            platform: "claude_code".into(),
            agy_system_prompt_homoglyph_enabled: false,
            agy_gif_frames_enabled: false,
            agy_disable_safety_filtering: false,
            agy_system_prompt_as_user_reminder: false,
            tui_system_prompt_policy: Default::default(),
            id: 0,
            name: "Prime 测试账号".into(),
            email: email.into(),
            status: AccountStatus::Active,
            auth_type: AccountAuthType::SetupToken,
            setup_token: "sk-ant-oat01-test-token-placeholder-value".into(),
            access_token: String::new(),
            refresh_token: String::new(),
            expires_at: None,
            oauth_refreshed_at: None,
            auth_error: String::new(),
            proxy_url: String::new(),
            device_id: String::new(),
            canonical_env: json!({}),
            canonical_prompt: json!({}),
            canonical_process: json!({}),
            request_backend: "legacy".into(),
            billing_mode: BillingMode::Strip,
            account_uuid: None,
            organization_uuid: None,
            subscription_type: None,
            rate_limit_tier: None,
            concurrency: 3,
            priority: 50,
            rpm_limit: 0,
            five_hour_usage_limit_percent: 0,
            seven_day_usage_limit_percent: 0,
            rate_limited_at: Some(Utc::now()),
            rate_limit_reset_at: Some(Utc::now() + chrono::Duration::hours(1)),
            disable_reason: String::new(),
            auto_telemetry: false,
            auto_poll_usage: false,
            allow_1m_models: DEFAULT_ALLOW_1M_MODELS.into(),
            allow_fast_mode: false,
            upstream_session_pool_enabled: false,
            upstream_session_pool_size: DEFAULT_UPSTREAM_SESSION_POOL_SIZE,
            upstream_session_ttl_minutes: DEFAULT_UPSTREAM_SESSION_TTL_MINUTES,
            upstream_session_refresh_policy: DEFAULT_UPSTREAM_SESSION_REFRESH_POLICY.into(),
            telemetry_count: 0,
            usage_data: json!({}),
            usage_fetched_at: None,
            created_at: Utc::now(),
            updated_at: Utc::now(),
        }
    }

    fn oauth_account(email: &str) -> Account {
        let mut account = setup_token_account(email);
        account.auth_type = AccountAuthType::Oauth;
        account.setup_token.clear();
        account.access_token = "access-old".into();
        account.refresh_token = "refresh-old".into();
        account.expires_at = Some(Utc::now() + chrono::Duration::hours(1));
        account.rate_limited_at = None;
        account.rate_limit_reset_at = None;
        account
    }

    #[tokio::test]
    async fn oauth_unauthorized_refreshes_and_retries_prime_request() {
        let (base_url, state, server) = spawn_prime_auth_mock_server(true).await;
        let (service, account_svc) = setup_prime_poller_with_urls(
            format!("{}/v1/messages?beta=true", base_url),
            format!("{}/oauth/token", base_url),
        )
        .await;
        let mut account = oauth_account("prime-oauth-retry@example.com");
        account_svc.create_account(&mut account).await.unwrap();

        let outcome = service
            .prime_one(&account, "claude-haiku-4-5-20251001", true)
            .await;

        assert!(outcome.success);
        assert_eq!(outcome.status, Some(200));
        assert_eq!(state.refresh_calls.load(Ordering::SeqCst), 1);
        assert_eq!(
            state.authorization_headers.lock().await.as_slice(),
            ["Bearer access-old", "Bearer access-refreshed"]
        );
        let stored = account_svc.get_account(account.id).await.unwrap();
        assert_eq!(stored.status, AccountStatus::Active);
        assert_eq!(stored.access_token, "access-refreshed");
        server.abort();
    }

    /// 原生能力缺失时保持目标账号归属，禁止回落到旧请求发送。
    /// @return 无；发生旧路径模型发送或错误归属丢失时失败。
    #[tokio::test]
    async fn native_prime_requires_sender_without_legacy_fallback() {
        let (base_url, state, server) = spawn_prime_auth_mock_server(true).await;
        let (service, account_svc) = setup_prime_poller_with_urls(
            format!("{base_url}/v1/messages?beta=true"),
            format!("{base_url}/oauth/token"),
        )
        .await;
        let mut account = setup_token_account("prime-native@example.test");
        account.request_backend = "native293".into();
        account_svc.create_account(&mut account).await.unwrap();
        let outcome = service
            .prime_one(&account, "claude-haiku-4-5-20251001", true)
            .await;
        assert!(!outcome.success);
        assert_eq!(outcome.status, None);
        assert!(outcome.error_message.contains("原生运行"));
        assert!(state.authorization_headers.lock().await.is_empty());
        assert_eq!(state.refresh_calls.load(Ordering::SeqCst), 0);
        server.abort();
    }

    #[tokio::test]
    async fn repeated_oauth_unauthorized_disables_prime_account() {
        let (base_url, state, server) = spawn_prime_auth_mock_server(false).await;
        let (service, account_svc) = setup_prime_poller_with_urls(
            format!("{}/v1/messages?beta=true", base_url),
            format!("{}/oauth/token", base_url),
        )
        .await;
        let mut account = oauth_account("prime-oauth-rejected@example.com");
        account_svc.create_account(&mut account).await.unwrap();

        let outcome = service
            .prime_one(&account, "claude-haiku-4-5-20251001", true)
            .await;
        assert_eq!(outcome.status, Some(401));
        service
            .apply_status_side_effects(&account, 401, None, outcome.failed_access_token.as_deref())
            .await;

        assert_eq!(state.refresh_calls.load(Ordering::SeqCst), 1);
        assert_eq!(state.authorization_headers.lock().await.len(), 2);
        let stored = account_svc.get_account(account.id).await.unwrap();
        assert_eq!(stored.status, AccountStatus::Disabled);
        assert_eq!(stored.auth_error, "401 OAuth 认证失败");
        server.abort();
    }

    #[tokio::test]
    async fn late_prime_unauthorized_preserves_reauthorized_credentials() {
        let (base_url, _, server) = spawn_prime_auth_mock_server(false).await;
        let (service, account_svc) = setup_prime_poller_with_urls(
            format!("{}/v1/messages?beta=true", base_url),
            format!("{}/oauth/token", base_url),
        )
        .await;
        let mut account = oauth_account("late-prime@example.invalid");
        account_svc.create_account(&mut account).await.unwrap();
        let outcome = service
            .prime_one(&account, "claude-haiku-4-5-20251001", true)
            .await;
        assert_eq!(outcome.status, Some(401));
        let mut reauthorized = account_svc.get_account(account.id).await.unwrap();
        reauthorized.access_token = "reauth-access".into();
        reauthorized.refresh_token = "reauth-refresh".into();
        account_svc.update_account(&reauthorized).await.unwrap();
        service
            .apply_status_side_effects(&account, 401, None, outcome.failed_access_token.as_deref())
            .await;
        let stored = account_svc.get_account(account.id).await.unwrap();
        assert_eq!(stored.status, AccountStatus::Active);
        assert!(stored.auth_error.is_empty());
        assert_eq!(stored.access_token, "reauth-access");
        server.abort();
    }

    #[tokio::test]
    async fn prime_status_side_effects_preserve_forbidden_and_rate_limit_behavior() {
        let (service, account_svc) = setup_prime_poller().await;
        let mut forbidden = setup_token_account("prime-403@example.com");
        forbidden.rate_limited_at = None;
        forbidden.rate_limit_reset_at = None;
        account_svc.create_account(&mut forbidden).await.unwrap();

        service
            .apply_status_side_effects(&forbidden, 403, None, None)
            .await;
        assert_eq!(
            account_svc.get_account(forbidden.id).await.unwrap().status,
            AccountStatus::Disabled
        );

        let reset_at = Utc::now() + chrono::Duration::hours(4);
        let usage = json!({
            "five_hour": {
                "utilization": 100,
                "resets_at": reset_at.to_rfc3339()
            }
        });
        let mut rate_limited = setup_token_account("prime-429@example.com");
        rate_limited.rate_limited_at = None;
        rate_limited.rate_limit_reset_at = None;
        rate_limited.usage_data = usage.clone();
        account_svc.create_account(&mut rate_limited).await.unwrap();

        service
            .apply_status_side_effects(&rate_limited, 429, Some(usage), None)
            .await;
        let stored = account_svc.get_account(rate_limited.id).await.unwrap();
        assert_eq!(stored.status, AccountStatus::Active);
        assert!(
            stored
                .rate_limit_reset_at
                .is_some_and(|reset| reset > Utc::now())
        );
    }

    #[tokio::test]
    async fn final_unauthorized_disables_account_and_clears_rate_limit() {
        let (service, account_svc) = setup_prime_poller().await;
        let mut account = setup_token_account("prime-401@example.com");
        account_svc.create_account(&mut account).await.unwrap();

        service
            .apply_status_side_effects(&account, 401, None, None)
            .await;

        let stored = account_svc.get_account(account.id).await.unwrap();
        assert_eq!(stored.status, AccountStatus::Disabled);
        assert_eq!(stored.auth_error, "401 SetupToken 认证失败");
        assert_eq!(stored.disable_reason, "401 SetupToken 认证失败");
        assert!(stored.rate_limited_at.is_none());
        assert!(stored.rate_limit_reset_at.is_none());
    }
}
