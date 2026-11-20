//! AGY专属私有请求合同，完整RT继续由现有管理服务独占。
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::Path;

use crate::error::AppError;
use crate::service::runtime_transport::PreparedRequest;

/// 固定原版执行体身份，适配资源与业务来源分别记录。
pub const AGY_SOURCE_SHA256: &str =
    "39816d49d5ab92229952987225c23ea3fed7580699dcb4a444e0388e0ac1ce43";

/// 公共生成请求共用的原生执行预算。
pub(super) const AGY_REQUEST_SECONDS: i64 = 120;

/// 首版固定映射标识，字符表由原生适配的受管理资源持有。
pub const AGY_SYSTEM_PROMPT_RULE: &str = "new-api-homoglyph-v1";

/// 同一HTTP请求及认证恢复共用的账号系统文本策略。
#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AgySystemPromptPolicy {
    pub schema_version: u8,
    pub enabled: bool,
    pub rule_version: String,
}

impl Default for AgySystemPromptPolicy {
    /// 历史信封缺省关闭。@return 首版关闭策略。
    fn default() -> Self {
        Self::new(false)
    }
}

impl AgySystemPromptPolicy {
    /// 从已准入账号冻结开关。@param enabled 当前账号配置。@return 独立策略快照。
    pub fn new(enabled: bool) -> Self {
        Self {
            schema_version: 1,
            enabled,
            rule_version: AGY_SYSTEM_PROMPT_RULE.into(),
        }
    }

    /// 关闭策略省略私有扩展以保持历史默认发送兼容。@return 是否关闭。
    pub fn is_disabled(&self) -> bool {
        !self.enabled
    }

    /// 拒绝未知规则并保持发送前失败。@return 合同校验结果。
    pub fn validate(&self) -> Result<(), AppError> {
        if self.schema_version != 1 || self.rule_version != AGY_SYSTEM_PROMPT_RULE {
            return Err(AppError::BadRequest("AGY系统文本策略版本无效".into()));
        }
        Ok(())
    }

    /// 核对内核实际处理回执及计数一致性。@param report 私有原生回执。@return 是否对应冻结策略。
    pub fn matches_report(&self, report: &Value) -> bool {
        let Some(replaced) = report["replaced_codepoints"].as_u64() else {
            return false;
        };
        report["schema_version"].as_u64() == Some(u64::from(self.schema_version))
            && report["enabled"].as_bool() == Some(self.enabled)
            && report["rule_version"].as_str() == Some(self.rule_version.as_str())
            && report["source"].as_str() == Some("cortex_custom_system")
            && report["changed"].as_bool() == Some(replaced > 0)
            && (self.enabled || replaced == 0)
            && report["system_codepoints"]
                .as_u64()
                .is_some_and(|count| count >= replaced)
            && report["rule_sha256"].as_str().is_some_and(|hash| {
                hash.len() == 64
                    && hash
                        .bytes()
                        .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
            })
    }
}

/// 回填原工具轮的私有信封，沿原许可执行并且不发布新凭据。
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgyToolCompletion {
    pub request: PreparedRequest,
    pub api_token_id: i64,
    pub previous_request_id: String,
    pub body: Value,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub gif_frames: bool,
}

/// 管理端冻结的账号内AGY执行配置。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgySenderConfig {
    pub protocol_version: u8,
    pub source_sha256: String,
    pub module_root: String,
    pub binary_path: String,
    pub work_root: String,
    pub max_workers: usize,
    /// 显式零沿现有资源策略表示无限，正数为sender实际限额。
    pub memory_mib: u64,
}

impl AgySenderConfig {
    /// 核对固定协议与受控绝对路径。@return 配置校验结果。
    pub fn validate(&self) -> Result<(), AppError> {
        if self.protocol_version != 1
            || self.source_sha256 != AGY_SOURCE_SHA256
            || self.max_workers == 0
            || self.max_workers > 64
            || [&self.module_root, &self.binary_path, &self.work_root]
                .iter()
                .any(|value| !Path::new(value).is_absolute())
        {
            return Err(AppError::ServiceUnavailable("AGY执行配置身份无效".into()));
        }
        Ok(())
    }
}

/// 从原生模型目录冻结的枚举标识。
#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(untagged)]
pub enum AgyModelId {
    Name(String),
    Number(u32),
}

impl AgyModelId {
    /// 核对原生枚举JSON形状。@return 标识是否可接受。
    pub fn is_valid(&self) -> bool {
        match self {
            Self::Name(value) => {
                value.starts_with("MODEL_")
                    && value.len() > 6
                    && value.len() <= 128
                    && value.bytes().all(|byte| {
                        byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'_'
                    })
            }
            Self::Number(value) => *value > 0 && *value <= i32::MAX as u32,
        }
    }
}

/// 同一账号锁内取得的AT-only运行快照；禁止派生Debug。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgyAccessSnapshot {
    pub account_id: i64,
    pub credential_generation: i64,
    pub access_token: String,
    pub expires_at: i64,
    pub email: String,
}

impl AgyAccessSnapshot {
    /// 核对正代次及当前有效AT。@param now 当前UTC毫秒。@return 快照校验结果。
    pub fn validate(&self, now: u64) -> Result<(), AppError> {
        if self.account_id < 1
            || self.credential_generation < 1
            || self.expires_at <= now as i64
            || self.access_token.is_empty()
            || self.access_token.len() > 16384
            || !self
                .access_token
                .bytes()
                .all(|byte| (33..127).contains(&byte))
        {
            return Err(AppError::ServiceUnavailable("AGY运行凭据快照无效".into()));
        }
        Ok(())
    }
}

/// 网关在同次准入内冻结的Gemini请求，秘密仅传入账号发送器。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgySubmission {
    pub request: PreparedRequest,
    pub api_token_id: i64,
    pub credential_snapshot: AgyAccessSnapshot,
    pub model: String,
    pub native_model: AgyModelId,
    pub body: Value,
    #[serde(default, skip_serializing_if = "AgySystemPromptPolicy::is_disabled")]
    pub system_prompt_policy: AgySystemPromptPolicy,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub gif_frames: bool,
    #[serde(default)]
    pub capture_enabled: bool,
    /// 来自受信发送请求头的正文显示策略，对旧发送器保持兼容。
    #[serde(skip)]
    pub full_egress: bool,
    /// 本次模型生成冻结的账号原生安全开关。
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub disable_safety_filtering: bool,
}

impl AgySubmission {
    /// 核对调用方、模型和同账号快照。@param now 当前UTC毫秒。@return 业务信封校验结果。
    pub fn validate(&self, now: u64) -> Result<(), AppError> {
        self.credential_snapshot.validate(now)?;
        self.system_prompt_policy.validate()?;
        if self.api_token_id < 1
            || self.request.account_id != self.credential_snapshot.account_id
            || !self.native_model.is_valid()
            || !["gemini-", "claude-", "gpt-"]
                .iter()
                .any(|prefix| self.model.starts_with(prefix))
            || self.model.is_empty()
            || self.model.len() > 128
            || !self
                .model
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
            || !self.body.is_object()
        {
            return Err(AppError::BadRequest("AGY请求归属或模型无效".into()));
        }
        Ok(())
    }
}
