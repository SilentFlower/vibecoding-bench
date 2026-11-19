//! 固定AGY内核仅支持Linux x86_64，其余平台受控拒绝。
use axum::response::Response;
use serde_json::{Value, json};
use tokio::time::Instant;

use crate::error::AppError;
use crate::service::agy_contract::{AgySubmission, AgyToolCompletion};
use crate::service::runtime_transport::SenderConfig;

/// 保持账号发送器在非目标平台上的接口可编译。
#[derive(Default)]
pub struct AgyPool;

impl AgyPool {
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
    /// 拒绝不支持的平台执行。@param config 账号配置。@param submission 原请求。@param deadline 原截止。@param prepare 是否准备。@return 固定不可用错误。
    pub async fn submit(
        &self,
        _config: &SenderConfig,
        _submission: AgySubmission,
        _deadline: Instant,
        _prepare: bool,
    ) -> Result<Response, AppError> {
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
