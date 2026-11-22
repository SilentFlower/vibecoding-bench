//! 固定AGY内核仅支持Linux x86_64，其余平台受控拒绝。
use axum::response::Response;
use serde_json::{Value, json};
use tokio::time::Instant;

use crate::error::AppError;
use crate::service::agy_contract::{
    AgyOperation, AgySubmission, AgyToolCompletion, AgyWarmPreparation,
};
use crate::service::runtime_transport::SenderConfig;

/// 保持账号发送器在非目标平台上的接口可编译。
#[derive(Default)]
pub struct AgyPool;

impl AgyPool {
    /// 收口无执行体的平台。@return 空池已结束。
    pub(super) async fn shutdown_idle(&self) {}

    /// 拒绝非目标平台的工具回填。@param input 原输入。@param deadline 原截止。@return 固定错误。
    pub async fn finish_tools(
        &self,
        _input: AgyToolCompletion,
        _deadline: Instant,
    ) -> Result<Value, AppError> {
        Err(AppError::ServiceUnavailable(
            "AGY内核需要Linux x86_64环境".into(),
        ))
    }
    /// 拒绝不支持的平台执行。@param config 账号配置。@param config_path 私有配置。@param submission 原请求。@param deadline 原截止。@param operation 原操作。@return 固定不可用错误。
    pub(super) async fn submit(
        &self,
        _config: &SenderConfig,
        _config_path: &str,
        _submission: AgySubmission,
        _deadline: Instant,
        _operation: AgyOperation,
    ) -> Result<Response, AppError> {
        Err(AppError::ServiceUnavailable(
            "AGY内核需要Linux x86_64环境".into(),
        ))
    }

    /// 拒绝非目标平台的预热。@param config 账号配置。@param config_path 私有配置。
    /// @param input 准备信封。@param deadline 原截止。@return 固定不可用错误。
    pub(super) async fn warm(
        &self,
        _config: &SenderConfig,
        _config_path: &str,
        _input: AgyWarmPreparation,
        _deadline: Instant,
    ) -> Result<Response, AppError> {
        Err(AppError::ServiceUnavailable(
            "AGY内核需要Linux x86_64环境".into(),
        ))
    }

    /// 拒绝非目标平台的容量操作。@param config_path 私有配置入口。@param authorize 原鉴权。@return 固定不可用错误。
    pub(super) async fn apply_capacity(
        &self,
        _config_path: &str,
        _authorize: impl FnOnce(&SenderConfig) -> Result<(), AppError>,
    ) -> Result<usize, AppError> {
        Err(AppError::ServiceUnavailable(
            "AGY内核需要Linux x86_64环境".into(),
        ))
    }

    /// 返回本平台已知的零进程活动。@return 零。
    pub async fn active(&self) -> u64 {
        0
    }

    /// 返回受控平台状态。@return 不支持状态。
    pub async fn status(&self, _config: &SenderConfig) -> Value {
        json!({"state":"unsupported"})
    }
}
