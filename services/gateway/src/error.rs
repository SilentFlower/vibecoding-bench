use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use serde_json::json;
use tracing::error;

/// 应用统一错误类型及其 HTTP 响应映射。
#[derive(Clone, Debug, thiserror::Error)]
pub enum AppError {
    #[error("not found")]
    NotFound,
    #[error("bad request: {0}")]
    BadRequest(String),
    /// 账号交互 CLI 无法保留此请求的输入语义，准备阶段拒绝且未提交模型。
    #[error("此请求的内容或工具约定尚不受当前交互式 V2 支持")]
    TuiInputUnsupported,
    /// 绑定的准备源按 native293 业务合同拒绝输入，仅公开预先登记的错误分类。
    #[error("{message}")]
    TuiInput {
        status: StatusCode,
        code: &'static str,
        message: &'static str,
    },
    /// 当前账号的物理容量已经被此子代理所依赖的父链占满。
    #[error(
        "当前 V2 账号没有可供同步子代理的交互进程额度。请提高账号并发及内存额度，或改用后台 Agent"
    )]
    TuiSubagentCapacity,
    /// 同形工具等不到可核验的 Agent 配对，必须在投递模型前拒绝。
    #[error("同提示子代理缺少可核验的工具归属。请使用不同提示，或等待后台启动配对")]
    TuiSubagentAmbiguous,
    /// AGY 输入拒绝的公开分类和允许披露的字段路径。
    #[error("{message}")]
    AgyInput {
        reason: &'static str,
        message: &'static str,
        field: Option<String>,
    },
    /// 管理视图已过期，刷新后才能继续同一记录。
    #[error("{0}")]
    Conflict(String),
    #[error("unauthorized")]
    Unauthorized,
    #[error("too many requests: {0}")]
    TooManyRequests(String),
    /// AGY 模型返回的确证限流或配额耗尽。
    #[error("AGY 上游额度不足或触发限流")]
    AgyUpstreamQuota,
    /// AGY 本地控制接口实际返回的 HTTP 错误状态。
    #[error("AGY 控制接口请求失败")]
    AgyControl(StatusCode),
    /// 已经接纳回填的原生工具轮未能正常收尾。
    #[error("AGY已接纳回填，但原工具轮收尾失败")]
    AgyToolTurnFailed,
    /// 续轮已有归属，但原响应无法从网关的短期缓存继续读取。
    #[error("AGY 工具轮的原响应暂时无法重读，请查询原请求状态")]
    AgyToolReplayUnavailable,
    /// 已有提交回执，公开响应的字节已到期回收。
    #[error("AGY 原工具回填响应已过期，请查询原请求状态")]
    AgyToolResponseExpired,
    /// 原工具续轮已经越过安全恢复边界，回包带可核对的 HTTP 根。
    #[error("AGY_TOOL_CONTINUATION_TERMINAL：{reason}（原请求 {request_id}）")]
    AgyToolContinuationTerminal {
        request_id: String,
        reason: &'static str,
    },
    /// 本地准入拒绝，携带保守重试提示，保持账号绑定。
    #[error("本地准入容量不足或等待超时")]
    AdmissionLimited { retry_after: u64 },
    /// 当前 sender 的独立模型提供方要求在此期限内暂停提交。
    #[error("本机模型提供方仍在限流等待期")]
    TuiProviderBackoff { retry_after: u64 },
    /// 发送前绑定 CAS 冲突，仅供网关重新选择，不能盲目提交。
    #[error("会话绑定已变化")]
    SchedulingConflict,
    #[error("bad gateway: {0}")]
    BadGateway(String),
    #[error("service unavailable: {0}")]
    ServiceUnavailable(String),
    /// 账号凭据已永久失效，需要停用账号并由管理员重新授权。
    #[error("permanent credential failure: {0}")]
    PermanentCredential(String),
    #[error("internal: {0}")]
    Internal(String),
}

impl From<sqlx::Error> for AppError {
    fn from(e: sqlx::Error) -> Self {
        match e {
            sqlx::Error::RowNotFound => AppError::NotFound,
            _ => AppError::Internal(e.to_string()),
        }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        if let Self::TuiInput {
            status,
            code,
            message,
        } = self
        {
            return (
                status,
                axum::Json(json!({"type":"error","error":{
                    "type":"invalid_request_error","code":code,"message":message
                }})),
            )
                .into_response();
        }
        if let Self::TuiProviderBackoff { retry_after } = &self {
            return (
                StatusCode::TOO_MANY_REQUESTS,
                [("retry-after", retry_after.to_string())],
                axum::Json(json!({"type":"error","error":{"type":"rate_limit_error","message":self.to_string()}})),
            ).into_response();
        }
        if let AppError::AdmissionLimited { retry_after } = &self {
            return (StatusCode::TOO_MANY_REQUESTS, [("retry-after", retry_after.to_string())], axum::Json(json!({"type":"error","error":{"type":"rate_limit_error","message":"本地准入容量不足或等待超时，请稍后重试"}}))).into_response();
        }
        if matches!(&self, AppError::TuiSubagentCapacity) {
            return (
                StatusCode::UNPROCESSABLE_ENTITY,
                axum::Json(json!({"type":"error","error":{
                    "type":"invalid_request_error", "code":"tui_subagent_capacity", "message":self.to_string()
                }})),
            ).into_response();
        }
        if matches!(&self, AppError::TuiSubagentAmbiguous) {
            return (
                StatusCode::BAD_REQUEST,
                axum::Json(json!({"type":"error","error":{
                    "type":"invalid_request_error", "code":"tui_subagent_ambiguous", "message":self.to_string()
                }})),
            ).into_response();
        }

        let (status, msg) = match &self {
            AppError::NotFound => (StatusCode::NOT_FOUND, "not found"),
            AppError::BadRequest(_) | AppError::AgyInput { .. } => (StatusCode::BAD_REQUEST, ""),
            AppError::TuiInputUnsupported => (StatusCode::UNPROCESSABLE_ENTITY, ""),
            AppError::TuiInput { .. } | AppError::TuiSubagentCapacity | AppError::TuiSubagentAmbiguous => unreachable!(),
            AppError::Conflict(_) => (StatusCode::CONFLICT, ""),
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, "unauthorized"),
            AppError::AdmissionLimited { .. } | AppError::TuiProviderBackoff { .. } => {
                unreachable!()
            }
            AppError::SchedulingConflict => {
                (StatusCode::SERVICE_UNAVAILABLE, "会话绑定已更新，请重试")
            }
            AppError::TooManyRequests(_) | AppError::AgyUpstreamQuota => {
                (StatusCode::TOO_MANY_REQUESTS, "")
            }
            AppError::BadGateway(_) | AppError::AgyToolTurnFailed => (StatusCode::BAD_GATEWAY, ""),
            AppError::AgyControl(status) => (*status, ""),
            AppError::AgyToolResponseExpired => (StatusCode::GONE, ""),
            AppError::AgyToolContinuationTerminal { .. } => (StatusCode::BAD_REQUEST, ""),
            AppError::ServiceUnavailable(_) | AppError::AgyToolReplayUnavailable => {
                (StatusCode::SERVICE_UNAVAILABLE, "")
            }
            AppError::PermanentCredential(_) => (StatusCode::SERVICE_UNAVAILABLE, ""),
            AppError::Internal(detail) => {
                error!("internal error: {}", detail);
                (StatusCode::INTERNAL_SERVER_ERROR, "internal error")
            }
        };
        let body =
            json!({"error": if msg.is_empty() { self.to_string() } else { msg.to_string() }});
        (status, axum::Json(body)).into_response()
    }
}
