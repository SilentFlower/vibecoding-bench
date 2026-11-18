//! 在既有账号服务中按平台适配原生凭据，CC 调用保持原路径。
use chrono::{DateTime, Utc};
use serde_json::{Value, json};
use uuid::Uuid;

use super::{AccountService, build_oauth_credential_snapshot, validate_account_usage_limits};
use crate::error::AppError;
use crate::model::account::{Account, AccountAuthType};
use crate::model::proxy::ProxyConnection;
use crate::service::runtime_bridge::agy_request;

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
        account.usage_data = json!({"platform":"antigravity","capabilities":capabilities});
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
        account.usage_data =
            json!({"platform":"antigravity","capabilities":result["capabilities"]});
        Ok(())
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
        if candidate.concurrency < 1 || candidate.rpm_limit < 0 || candidate.priority < 0 {
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
