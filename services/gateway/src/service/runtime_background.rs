//! 绑定账号的受限后台发送，复用原账号节点、HTTP/TLS客户端及提交未知边界。

use std::time::Duration;

use reqwest::{Client, Request, Response};

use crate::error::AppError;
use crate::model::account::Account;
use crate::service::oauth::OAUTH_TOKEN_URL;
use crate::service::runtime_transport::{self, PreparedRequest};
use crate::service::tui_backend::TUI_V2;
use crate::service::version_profile::EVENT_LOGGING_V2_PATH;
use crate::tlsfp::TlsProfileId;

pub(crate) const BACKGROUND_HEADER: &str = "x-v3-background-purpose";
pub(crate) const USAGE_URL: &str = "https://api.anthropic.com/api/oauth/usage";
pub(crate) const TOKEN_TEST_URL: &str = "https://api.anthropic.com/v1/messages?beta=true";
pub(crate) const TELEMETRY_BASE: &str = "https://api.anthropic.com";
pub(crate) const GROWTHBOOK_CLIENT_KEY: &str = "sdk-zAZezfDKGoZuXXKe";

/// 节点允许承接的固定后台动作，目标与方法由服务端常量决定。
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum BackgroundPurpose {
    OAuthRefresh,
    Usage,
    TokenTest,
    TelemetryBatch,
    TelemetryEval,
}

impl BackgroundPurpose {
    /// 返回内部固定动作标识。@return 固定私有头值。
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::OAuthRefresh => "oauth-refresh",
            Self::Usage => "usage",
            Self::TokenTest => "token-test",
            Self::TelemetryBatch => "telemetry-batch",
            Self::TelemetryEval => "telemetry-eval",
        }
    }

    /// 解析服务端固定动作。@param value 私有头值。@return 合法动作或发送前拒绝。
    pub(crate) fn parse(value: &str) -> Result<Self, AppError> {
        match value {
            "oauth-refresh" => Ok(Self::OAuthRefresh),
            "usage" => Ok(Self::Usage),
            "token-test" => Ok(Self::TokenTest),
            "telemetry-batch" => Ok(Self::TelemetryBatch),
            "telemetry-eval" => Ok(Self::TelemetryEval),
            _ => Err(AppError::BadRequest("后台发送动作无效".into())),
        }
    }

    fn target(self) -> String {
        match self {
            Self::OAuthRefresh => OAUTH_TOKEN_URL.into(),
            Self::Usage => USAGE_URL.into(),
            Self::TokenTest => TOKEN_TEST_URL.into(),
            Self::TelemetryBatch => format!("{TELEMETRY_BASE}{EVENT_LOGGING_V2_PATH}"),
            Self::TelemetryEval => format!("{TELEMETRY_BASE}/api/eval/{GROWTHBOOK_CLIENT_KEY}"),
        }
    }

    /// 核对精确固定目的地，并提供原通用绑定校验所需的origin。
    /// @param method 原请求方法。
    /// @param target 原完整URL。
    /// @return 已核对的固定origin。
    pub(crate) fn validate(self, method: &str, target: &str) -> Result<String, AppError> {
        let expected = self.target();
        let expected_method = if self == Self::Usage { "GET" } else { "POST" };
        if method != expected_method || target != expected {
            return Err(AppError::BadRequest(
                "后台发送方法或目标与固定动作不一致".into(),
            ));
        }
        let url = reqwest::Url::parse(&expected)
            .map_err(|_| AppError::Internal("后台发送固定目标无效".into()))?;
        Ok(url.origin().ascii_serialization())
    }
}

/// 经原账号通道执行一次后台请求，v3准备失败保留关闭状态。
/// @param account 已确定的原账号。
/// @param client 原HTTP/TLS客户端，独立部署继续使用它。
/// @param request 原已构造的请求和正文。
/// @param purpose 原固定后台动作。
/// @param tls_profile 原调用冻结的TLS画像。
/// @return 原响应或明确的提交边界错误。
pub(crate) async fn execute(
    account: &Account,
    client: Client,
    request: Request,
    purpose: BackgroundPurpose,
    tls_profile: TlsProfileId,
) -> Result<Response, AppError> {
    if purpose == BackgroundPurpose::TokenTest && account.request_backend == TUI_V2 {
        return Err(AppError::BadRequest("V2 账号请用 OAuth 用量接口检查凭据".into()));
    }
    let v3 = !std::env::var("V3_RUNTIME_URL")
        .unwrap_or_default()
        .is_empty()
        || !std::env::var("V3_DEPLOYMENT_ID")
            .unwrap_or_default()
            .is_empty();
    if !v3 {
        return client
            .execute(request)
            .await
            .map_err(|_| AppError::BadGateway("后台请求提交结果未知".into()));
    }
    purpose.validate(request.method().as_str(), request.url().as_str())?;
    let body = match request.body() {
        None => Vec::new(),
        Some(body) => body
            .as_bytes()
            .ok_or_else(|| AppError::BadRequest("后台发送只接受原有界正文".into()))?
            .to_vec(),
    };
    let headers = request
        .headers()
        .iter()
        .map(|(name, value)| {
            value
                .to_str()
                .map(|value| (name.to_string(), value.to_string()))
                .map_err(|_| AppError::BadRequest("后台发送头格式无效".into()))
        })
        .collect::<Result<Vec<_>, _>>()?;
    let prepared = PreparedRequest {
        account_id: account.id,
        environment_id: String::new(),
        generation: 0,
        request_id: String::new(),
        deadline_unix_ms: 0,
        method: request.method().to_string(),
        target_url: request.url().to_string(),
        headers,
        preserve_header_casing: false,
        tls_profile,
    };
    runtime_transport::prepare(account, Duration::from_secs(120))
        .await?
        .submit_background(prepared, &body, Duration::from_secs(30), purpose)
        .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn purpose_requires_exact_original_method_url_and_query() {
        for purpose in [
            BackgroundPurpose::OAuthRefresh,
            BackgroundPurpose::Usage,
            BackgroundPurpose::TokenTest,
            BackgroundPurpose::TelemetryBatch,
            BackgroundPurpose::TelemetryEval,
        ] {
            assert_eq!(BackgroundPurpose::parse(purpose.as_str()).unwrap(), purpose);
            let method = if purpose == BackgroundPurpose::Usage {
                "GET"
            } else {
                "POST"
            };
            assert!(purpose.validate(method, &purpose.target()).is_ok());
            assert!(purpose.validate("DELETE", &purpose.target()).is_err());
            assert!(
                purpose
                    .validate(method, &(purpose.target() + "&extra=1"))
                    .is_err()
            );
            assert!(
                purpose
                    .validate(method, "http://169.254.169.254/api/metadata")
                    .is_err()
            );
        }
        assert!(BackgroundPurpose::parse("arbitrary-url").is_err());
    }
}
