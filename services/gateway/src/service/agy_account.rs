//! 在既有账号服务中按平台适配原生凭据，CC 调用保持原路径。
use std::collections::BTreeSet;

use chrono::{DateTime, Utc};
use serde_json::{Value, json};
use uuid::Uuid;

use super::{
    AccountService, OAUTH_LOCK_TTL, OAUTH_WAIT_ATTEMPTS, OAUTH_WAIT_RETRY,
    build_oauth_credential_snapshot, validate_account_usage_limits,
};
use crate::error::AppError;
use crate::model::account::{Account, AccountAuthType, AccountStatus};
use crate::model::api_token::ApiToken;
use crate::model::proxy::ProxyConnection;
use crate::service::agy_contract::{AGY_REQUEST_SECONDS, AgyAccessSnapshot, AgyModelId};
use crate::service::runtime_bridge::agy_request;
use tokio::time::sleep;

// AGY 1.5.9 离线启动实测在剩余 299 秒时要求登录，310 秒时可就绪。
// 预留原请求预算，避免无刷新令牌的业务进程在准备或执行时触及该窗口。
const AGY_ACCESS_VALIDITY_SECONDS: i64 = 310 + AGY_REQUEST_SECONDS;

/// 将权威账号转换为原生私有输入。@param account 原账号。@return 严格原生凭据对象。
pub(super) fn native_document(account: &Account) -> Result<Value, AppError> {
    if !account.is_antigravity()
        || account.auth_type != AccountAuthType::Oauth
        || account.access_token.is_empty()
        || account.refresh_token.is_empty()
    {
        return Err(AppError::BadRequest("AGY 账号需要完整 OAuth 凭据".into()));
    }
    let expiry = account
        .expires_at
        .ok_or_else(|| AppError::BadRequest("AGY 凭据缺少有效期".into()))?;
    Ok(
        json!({"auth_method":"consumer","id_token_email":account.email,"token":{
        "access_token":account.access_token,"refresh_token":account.refresh_token,"token_type":"Bearer",
        "expiry":expiry.to_rfc3339(),"expires_in":(expiry-Utc::now()).num_seconds().max(0)}}),
    )
}

fn apply_document(account: &mut Account, value: &Value) -> Result<(), AppError> {
    let token = &value["token"];
    let access = token["access_token"]
        .as_str()
        .filter(|value| !value.is_empty() && value.len() <= 16384)
        .ok_or_else(|| AppError::ServiceUnavailable("AGY 原生访问凭据无效".into()))?;
    let refresh = token["refresh_token"]
        .as_str()
        .filter(|value| !value.is_empty() && value.len() <= 16384)
        .unwrap_or(&account.refresh_token);
    let expiry = token["expiry"]
        .as_str()
        .and_then(|value| DateTime::parse_from_rfc3339(value).ok())
        .map(|value| value.with_timezone(&Utc))
        .filter(|value| *value > Utc::now())
        .ok_or_else(|| AppError::ServiceUnavailable("AGY 原生有效期无效".into()))?;
    account.access_token = access.to_owned();
    account.refresh_token = refresh.to_owned();
    account.expires_at = Some(expiry);
    Ok(())
}

fn verify_identity(account: &Account, result: &Value) -> Result<(), AppError> {
    let email = result["email_address"]
        .as_str()
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| AppError::ServiceUnavailable("AGY 原生身份缺失".into()))?;
    if !email.trim().eq_ignore_ascii_case(account.email.trim()) {
        return Err(AppError::BadRequest("AGY 已认证账号与目标账号不符".into()));
    }
    Ok(())
}

fn apply_capabilities(account: &mut Account, capabilities: &Value) {
    // 原生凭据续期不查询平台额度，保留最近一次管理侧读数。
    let mut usage = json!({"platform":"antigravity","capabilities":capabilities});
    if let Some(quota) = account.usage_data.get("platform_quota") {
        usage["platform_quota"] = quota.clone();
    }
    account.usage_data = usage;
}

/// 采用同一次原生观测的身份、凭据、线路及能力。
fn apply_observation(account: &mut Account, result: &Value) -> Result<(), AppError> {
    verify_identity(account, result)?;
    apply_document(account, &result["document"])?;
    if let Some(proxy) = result.get("proxy_url").and_then(Value::as_str) {
        account.proxy_url = if proxy.is_empty() {
            String::new()
        } else {
            ProxyConnection::parse(proxy)?.private_url
        };
    }
    if let Some(capabilities) = result.get("capabilities").filter(|value| !value.is_null()) {
        apply_capabilities(account, capabilities);
    }
    Ok(())
}

fn verify_retirement(
    id: i64,
    operation: &str,
    generation: i64,
    result: &Value,
) -> Result<(), AppError> {
    if result["retired"] != true
        || result["account_id"].as_i64() != Some(id)
        || result["generation"].as_i64() != Some(generation)
        || result["operation_id"].as_str() != Some(operation)
        || !matches!(result["phase"].as_str(), Some("not_started" | "retired"))
    {
        return Err(AppError::ServiceUnavailable(
            "AGY 原操作终止证明无效".into(),
        ));
    }
    Ok(())
}

impl AccountService {
    /// 在原刷新锁内读取同代AT与代次，业务侧仅取得AT。@param id 原账号。@param force 是否请求一次认证恢复。@return AT-only快照。
    pub async fn resolve_agy_access(
        &self,
        id: i64,
        force: bool,
    ) -> Result<AgyAccessSnapshot, AppError> {
        let _activity = self.upstream_activity(id).await?;
        let initial = self.store.agy_credential_state(id).await?;
        let key = format!("oauth:refresh:account:{id}");
        let owner = Uuid::new_v4().to_string();
        for attempt in 0..=OAUTH_WAIT_ATTEMPTS {
            if self
                .cache
                .acquire_lock(&key, &owner, OAUTH_LOCK_TTL)
                .await?
            {
                let result = async {
                    let account = self.store.get_by_id(id).await?;
                    if !account.is_antigravity() || account.status != AccountStatus::Active {
                        return Err(AppError::ServiceUnavailable("AGY账号当前不可用".into()));
                    }
                    let current = self.store.agy_credential_state(id).await?;
                    self.resolve_agy_credentials(
                        &account,
                        AGY_ACCESS_VALIDITY_SECONDS,
                        force && initial.generation == current.generation,
                    )
                    .await?;
                    let state = self.store.agy_credential_state(id).await?;
                    let resolved = self.store.get_by_id(id).await?;
                    if state.phase != "ready" {
                        return Err(AppError::ServiceUnavailable("AGY凭据待对账".into()));
                    }
                    let snapshot = AgyAccessSnapshot {
                        account_id: id,
                        credential_generation: state.generation,
                        access_token: resolved.access_token,
                        expires_at: resolved
                            .expires_at
                            .map(|expiry| expiry.timestamp_millis())
                            .unwrap_or(0),
                        email: resolved.email,
                    };
                    snapshot.validate(Utc::now().timestamp_millis() as u64)?;
                    Ok(snapshot)
                }
                .await;
                self.cache.release_lock(&key, &owner).await;
                return result;
            }
            if attempt < OAUTH_WAIT_ATTEMPTS {
                sleep(OAUTH_WAIT_RETRY).await;
            }
        }
        Err(AppError::ServiceUnavailable("AGY凭据解析等待超时".into()))
    }

    /// 按令牌权限和真实模型映射读取候选。@param token 当前令牌。@param models 按优先级排列的公开名，空列表用于读取目录。@param media 请求包含的内嵌媒体类型。@return 合资格账号及命中的模型位置。
    pub async fn agy_candidates(
        &self,
        token: &ApiToken,
        models: &[String],
        media: &BTreeSet<&str>,
    ) -> Result<Vec<(usize, Account)>, AppError> {
        let allowed = token.allowed_account_ids();
        let blocked = token.blocked_account_ids();
        let mut result = Vec::new();
        let mut has_catalog = false;
        let mut has_model = false;
        let mut media_rejected = false;
        let mut media_unknown = false;
        for account in self.store.list_all_platforms().await? {
            if !account.is_antigravity()
                || blocked.contains(&account.id)
                || (!allowed.is_empty() && !allowed.contains(&account.id))
            {
                continue;
            }
            let model_index = if models.is_empty() {
                0
            } else {
                // 先核对令牌可见目录，停用或冷却中的已知模型仍走原可用性判断。
                let Some(index) = models
                    .iter()
                    .position(|name| Self::agy_model(&account, name).is_some())
                else {
                    has_catalog |= account.usage_data["capabilities"]["model_mappings"]
                        .as_object()
                        .is_some_and(|mapping| !mapping.is_empty());
                    continue;
                };
                has_model = true;
                index
            };
            if account.status != AccountStatus::Active
                || account
                    .rate_limit_reset_at
                    .is_some_and(|until| until > Utc::now())
            {
                continue;
            }
            if self.store.agy_credential_state(account.id).await?.phase != "ready" {
                continue;
            }
            let model_index = if !media.is_empty() {
                let supported =
                    models
                        .iter()
                        .enumerate()
                        .skip(model_index)
                        .find_map(|(index, name)| {
                            Self::agy_model(&account, name)?;
                            match Self::agy_media_support(
                                &account,
                                name,
                                media,
                                account.agy_gif_frames_enabled,
                            ) {
                                Some(true) => Some(index),
                                Some(false) => None,
                                None => {
                                    media_unknown = true;
                                    None
                                }
                            }
                        });
                let Some(index) = supported else {
                    media_rejected = true;
                    continue;
                };
                index
            } else {
                model_index
            };
            result.push((model_index, account));
        }
        if has_catalog && !has_model {
            return Err(AppError::NotFound);
        }
        if result.is_empty() && media_rejected {
            return Err(Self::agy_media_error(media, media_unknown));
        }
        let counts = self.active_request_counts().await;
        result.sort_by_key(|(model_index, account)| {
            (
                *model_index,
                counts.get(&account.id).copied().unwrap_or(0),
                account.id,
            )
        });
        Ok(result)
    }

    /// 读取已观测的公开模型和原生枚举对应。@param account 原账号。@param model 公开名。@return 经结构校验的原生ID。
    pub fn agy_model(account: &Account, model: &str) -> Option<AgyModelId> {
        let value = account
            .usage_data
            .get("capabilities")?
            .get("model_mappings")?
            .get(model)?;
        let identifier: AgyModelId = serde_json::from_value(value.clone()).ok()?;
        identifier.is_valid().then_some(identifier)
    }

    /// 核对同一实际型号是否识别所有将发送的附件。@param account 已绑定账号。@param model 实际型号。@param media 输入 MIME。@param gif_frames 是否转换 GIF。@return 支持、拒绝或未知。
    pub(crate) fn agy_media_support(
        account: &Account,
        model: &str,
        media: &BTreeSet<&str>,
        gif_frames: bool,
    ) -> Option<bool> {
        let capabilities = &account.usage_data["capabilities"];
        let mut known = true;
        for &input in media {
            let mime = if input == "image/gif" && gif_frames {
                "image/png"
            } else {
                input
            };
            let mut support = capabilities["media_inputs"][model][mime].as_bool();
            if support.is_none() && mime == "image/png" {
                support = capabilities["png_inputs"][model].as_bool();
            }
            match support {
                Some(false) => return Some(false),
                None => known = false,
                Some(true) => {}
            }
        }
        known.then_some(true)
    }

    /// 构造型号媒体能力错误。@param media 原始请求 MIME。@param unknown 能力缺少观测。@return 允许公开的拒绝分类。
    pub(crate) fn agy_media_error(media: &BTreeSet<&str>, unknown: bool) -> AppError {
        let (reason, message) = match (media.len() == 1 && media.contains("image/png"), unknown) {
            (true, true) => (
                "AGY_PNG_CAPABILITY_UNKNOWN",
                "AGY 模型的 PNG 能力尚未观测，请刷新账号能力",
            ),
            (true, false) => ("AGY_PNG_UNSUPPORTED", "AGY 模型不支持内嵌 PNG"),
            (false, true) => (
                "AGY_MEDIA_CAPABILITY_UNKNOWN",
                "AGY 模型的媒体能力尚未观测，请刷新账号能力",
            ),
            (false, false) => ("AGY_MEDIA_UNSUPPORTED", "AGY 模型不支持请求中的媒体类型"),
        };
        AppError::AgyInput {
            reason,
            message,
            field: Some("contents".into()),
        }
    }
    /// 查询不含令牌的 AGY 管理状态。@param id 账号。@return 持久代次与阶段。
    pub async fn agy_state(&self, id: i64) -> Result<Value, AppError> {
        if !self.store.get_by_id(id).await?.is_antigravity() {
            return Err(AppError::BadRequest("该账号属于其他平台".into()));
        }
        serde_json::to_value(self.store.agy_credential_state(id).await?)
            .map_err(|_| AppError::ServiceUnavailable("AGY 状态读取失败".into()))
    }

    /// 冻结原账号的重授权操作。@param id 账号。@param operation 原生会话。@return 冻结代次。
    pub async fn begin_agy_reauth(&self, id: i64, operation: &str) -> Result<i64, AppError> {
        let (key, owner) = self.acquire_oauth_credential_lock(id).await?;
        let result = async {
            let account = self.store.get_by_id(id).await?;
            self.store
                .begin_agy_credentials(&account, operation, "reauth")
                .await
        }
        .await;
        self.cache.release_lock(&key, &owner).await;
        result
    }

    /// 原生结果写回原账号，保留配置与绑定。@param id 账号。@param operation 原会话。@param result 已核验原生结果。@return 提交结果。
    pub async fn finish_agy_operation(
        &self,
        id: i64,
        operation: &str,
        result: &Value,
    ) -> Result<(), AppError> {
        let (key, owner) = self.acquire_oauth_credential_lock(id).await?;
        let outcome = async {
            let current = self.store.get_by_id(id).await?;
            let state = self.store.agy_credential_state(id).await?;
            if !current.is_antigravity() || state.operation_id.as_deref() != Some(operation) {
                return Err(AppError::BadRequest("AGY 授权会话已被替代".into()));
            }
            let mut updated = current.clone();
            apply_observation(&mut updated, result)?;
            let generation = if state.phase == "ready" {
                state.generation - 1
            } else {
                state.generation
            };
            self.store
                .complete_agy_observation(&current, operation, generation, &updated)
                .await
        }
        .await;
        self.cache.release_lock(&key, &owner).await;
        outcome
    }

    /// 根据持久归属撤销原授权。@param operation 原会话。@param phase 驱动取消终态。@return 状态保存结果。
    pub async fn cancel_agy_operation(&self, operation: &str, phase: &str) -> Result<(), AppError> {
        if let Some(id) = self.store.agy_operation_account(operation).await? {
            if phase == "cancelled" {
                self.store.cancel_agy_reauth(id, operation).await?;
            } else {
                self.store.reconcile_agy_credentials(id, operation).await?;
            }
        }
        Ok(())
    }

    /// 先取得同归属终止证明，再允许原账号重新授权。@param id 账号。@return 当前脱敏状态。
    pub async fn retire_agy_operation(&self, id: i64) -> Result<Value, AppError> {
        let (key, owner) = self.acquire_oauth_credential_lock(id).await?;
        let result = async {
            self.agy_state(id).await?;
            let state = self.store.agy_credential_state(id).await?;
            if state.phase != "ready" {
                let operation = state.operation_id.ok_or_else(|| AppError::ServiceUnavailable("AGY 原操作缺失".into()))?;
                let result = agy_request("retire", &json!({"operation_id":operation,"account_id":id,"generation":state.generation})).await?;
                verify_retirement(id, &operation, state.generation, &result)?;
                self.store.retire_agy_credentials(id, &operation, state.generation).await?;
            }
            self.agy_state(id).await
        }.await;
        self.cache.release_lock(&key, &owner).await;
        result
    }

    /// 按原操作恢复已有私有结果。@param id 账号。@return 当前脱敏状态。
    pub async fn recover_agy_operation(&self, id: i64) -> Result<Value, AppError> {
        let state = self.store.agy_credential_state(id).await?;
        if state.phase == "ready" {
            return self.agy_state(id).await;
        }
        let operation = state
            .operation_id
            .ok_or_else(|| AppError::ServiceUnavailable("AGY 对账操作缺失".into()))?;
        let result = agy_request(
            "recover",
            &json!({"operation_id":operation,"account_id":id,"generation":state.generation}),
        )
        .await?;
        if result["retired"] == true {
            verify_retirement(id, &operation, state.generation, &result)?;
            self.store
                .retire_agy_credentials(id, &operation, state.generation)
                .await?;
        } else {
            self.finish_agy_operation(id, &operation, &result).await?;
        }
        self.agy_state(id).await
    }
    /// 使用原生状态核验 AGY 账号及平台能力。@param account 创建或编辑候选。@return 核验结果。
    pub async fn verify_agy_account(&self, account: &mut Account) -> Result<(), AppError> {
        if !account.proxy_url.is_empty() {
            account.proxy_url = ProxyConnection::parse(&account.proxy_url)?.private_url;
        }
        if account.auth_type != AccountAuthType::Oauth || !account.has_valid_oauth_access_token(60)
        {
            return Err(AppError::BadRequest(
                "AGY 账号需要有效 OAuth 凭据及到期时间".into(),
            ));
        }
        let document = native_document(account)?;
        validate_account_usage_limits(account)?;
        let result = agy_request(
            "verify",
            &json!({"document":document,"proxy_url":account.proxy_url}),
        )
        .await?;
        verify_identity(account, &result)?;
        apply_capabilities(account, &result["capabilities"]);
        if let Some(reading) = result["platform_quota"].as_object() {
            let mut snapshot = account.usage_data["platform_quota"]
                .as_object()
                .cloned()
                .unwrap_or_default();
            // 共享额度和单模型额度独立刷新，缺失的部分继续保留上次观测。
            snapshot.extend(reading.clone());
            account.usage_data["platform_quota"] = Value::Object(snapshot);
        }
        Ok(())
    }

    /// 刷新账号能力与平台额度。@param id 原账号。@return 同次持久化的用量视图。
    pub(super) async fn refresh_agy_usage(&self, id: i64) -> Result<Value, AppError> {
        let state = self.store.agy_credential_state(id).await?;
        let mut account = self.store.get_by_id(id).await?;
        let original_proxy = account.proxy_url.clone();
        self.verify_agy_account(&mut account).await?;
        let (key, owner) = self.acquire_oauth_credential_lock(id).await?;
        let result = async {
            // 网络等待留在锁外，提交前复核原代次和出口，避免迟到观测覆盖后来的刷新。
            let state_now = self.store.agy_credential_state(id).await?;
            let current = self.store.get_by_id(id).await?;
            if state_now.phase != "ready"
                || state_now.generation != state.generation
                || current.access_token != account.access_token
                || current.proxy_url != original_proxy
            {
                return Err(AppError::ServiceUnavailable(
                    "账号凭据或出口已更新，请重新刷新".into(),
                ));
            }
            if current.usage_data["capabilities"]["observed_at_ms"].as_i64()
                > account.usage_data["capabilities"]["observed_at_ms"].as_i64()
            {
                return Ok(current.usage_data);
            }
            // 较晚发起的局部失败仍须保留前一次并发刷新成功的独立读数。
            for source in ["groups", "models"] {
                let latest = &current.usage_data["platform_quota"][source];
                if latest["observed_at_ms"].as_i64()
                    > account.usage_data["platform_quota"][source]["observed_at_ms"].as_i64()
                {
                    account.usage_data["platform_quota"][source] = latest.clone();
                }
            }
            self.store
                .update_usage(id, &account.usage_data.to_string())
                .await?;
            Ok(account.usage_data)
        }
        .await;
        self.cache.release_lock(&key, &owner).await;
        result
    }

    /// 按提交差异修改 AGY 账号，当前凭据在锁内重读。@param id 账号。@param updates 已解析代理的字段差异。@return 当前账号。
    pub async fn update_agy_fields(&self, id: i64, updates: &Value) -> Result<Account, AppError> {
        let (key, owner) = self.acquire_oauth_credential_lock(id).await?;
        let result = self.update_agy_fields_locked(id, updates).await;
        self.cache.release_lock(&key, &owner).await;
        result
    }

    async fn update_agy_fields_locked(
        &self,
        id: i64,
        updates: &Value,
    ) -> Result<Account, AppError> {
        let current = self.store.get_by_id(id).await?;
        let fields = updates
            .as_object()
            .ok_or_else(|| AppError::BadRequest("账号更新必须为对象".into()))?;
        let allowed = [
            "platform",
            "name",
            "email",
            "auth_type",
            "access_token",
            "refresh_token",
            "expires_at",
            "proxy_url",
            "status",
            "concurrency",
            "priority",
            "rpm_limit",
            "agy_system_prompt_homoglyph_enabled",
            "agy_gif_frames_enabled",
        ];
        if !current.is_antigravity() || fields.keys().any(|key| !allowed.contains(&key.as_str())) {
            return Err(AppError::BadRequest("该字段不属于 AGY 账号配置".into()));
        }
        if fields
            .get("platform")
            .is_some_and(|value| value.as_str() != Some("antigravity"))
            || fields
                .get("email")
                .is_some_and(|value| value.as_str() != Some(current.email.as_str()))
            || fields
                .get("auth_type")
                .is_some_and(|value| value.as_str() != Some("oauth"))
        {
            return Err(AppError::BadRequest(
                "AGY 平台、认证方式和已核验账号身份保持固定".into(),
            ));
        }
        let mut value = serde_json::to_value(&current)
            .map_err(|_| AppError::ServiceUnavailable("AGY 账号配置读取失败".into()))?;
        for (key, field) in fields {
            value[key] = field.clone();
        }
        let mut candidate: Account = serde_json::from_value(value)
            .map_err(|_| AppError::BadRequest("AGY 账号配置类型无效".into()))?;
        if !candidate.proxy_url.is_empty() {
            candidate.proxy_url = ProxyConnection::parse(&candidate.proxy_url)?.private_url;
        }
        if !(1..=64).contains(&candidate.concurrency)
            || candidate.rpm_limit < 0
            || candidate.priority < 0
        {
            return Err(AppError::BadRequest("AGY 账号容量配置无效".into()));
        }
        validate_account_usage_limits(&candidate)?;
        let state = self.store.agy_credential_state(id).await?;
        if state.phase != "ready" {
            return Err(AppError::ServiceUnavailable("AGY 原凭据操作待核对".into()));
        }
        let credentials_changed = ["access_token", "refresh_token", "expires_at", "proxy_url"]
            .iter()
            .any(|key| fields.contains_key(*key));
        let options: Vec<&str> = fields
            .keys()
            .map(String::as_str)
            .filter(|key| {
                ![
                    "platform",
                    "email",
                    "auth_type",
                    "access_token",
                    "refresh_token",
                    "expires_at",
                    "status",
                    "proxy_url",
                ]
                .contains(key)
            })
            .collect();
        if credentials_changed {
            let document = native_document(&candidate)?;
            // 先在同操作中关闭刷新，再核验候选；普通字段只写本次差异，保留并发编辑。
            let operation = Uuid::new_v4().simple().to_string();
            let generation = self
                .store
                .begin_agy_credentials(&current, &operation, "reauth")
                .await?;
            let prepared = agy_request(
                "prepare",
                &json!({"operation_id":operation,"account_id":id,
                "generation":generation,"document":document,"proxy_url":candidate.proxy_url}),
            )
            .await;
            let prepared = match prepared {
                Ok(value) => value,
                Err(error) => {
                    self.store.reconcile_agy_credentials(id, &operation).await?;
                    return Err(error);
                }
            };
            if let Err(error) = apply_observation(&mut candidate, &prepared) {
                self.store.reconcile_agy_credentials(id, &operation).await?;
                return Err(error);
            }
            let commit = async {
                self.store.update_options(&candidate, &options).await?;
                self.store
                    .complete_agy_observation(&current, &operation, generation, &candidate)
                    .await
            }
            .await;
            if let Err(error) = commit {
                self.store.reconcile_agy_credentials(id, &operation).await?;
                return Err(error);
            }
        } else {
            self.store.update_options(&candidate, &options).await?;
        }
        if fields.contains_key("status") {
            self.store.update_status(id, candidate.status).await?;
        }
        self.store.get_by_id(id).await
    }

    /// 在已持有的账号刷新锁内解析 AGY 凭据。@param account 当前账号。@param validity 最小有效期。@param force 是否强制刷新。@return 最终权威快照。
    pub(super) async fn resolve_agy_credentials(
        &self,
        account: &Account,
        validity: i64,
        force: bool,
    ) -> Result<super::OAuthCredentialSnapshot, AppError> {
        let state = self.store.agy_credential_state(account.id).await?;
        if state.phase != "ready" {
            return Err(AppError::ServiceUnavailable(
                "AGY 凭据结果待对账或重新授权".into(),
            ));
        }
        if !force && account.has_valid_oauth_access_token(validity) {
            return build_oauth_credential_snapshot(account, validity);
        }
        let document = native_document(account)?;
        let operation = Uuid::new_v4().simple().to_string();
        let generation = self
            .store
            .begin_agy_credentials(account, &operation, "refresh_pending")
            .await?;
        let result = agy_request(
            "refresh",
            &json!({"operation_id":operation,"account_id":account.id,
            "generation":generation,"document":document,"proxy_url":account.proxy_url}),
        )
        .await;
        let commit = async {
            let result = result?;
            let mut updated = account.clone();
            apply_observation(&mut updated, &result)?;
            self.store
                .complete_agy_observation(account, &operation, generation, &updated)
                .await?;
            build_oauth_credential_snapshot(&self.store.get_by_id(account.id).await?, validity)
        }
        .await;
        if commit.is_err() {
            self.store
                .reconcile_agy_credentials(account.id, &operation)
                .await?;
        }
        commit
    }
}
