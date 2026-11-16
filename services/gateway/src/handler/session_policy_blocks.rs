//! 管理员会话封禁列表与提前解除入口。

use axum::Json;
use axum::extract::{Path, Query, State};
use chrono::Utc;
use serde::Deserialize;
use uuid::Uuid;

use crate::error::AppError;
use crate::handler::router::AppState;
use crate::model::session_policy_block::{SessionPolicyBlock, SessionPolicyBlockPage};

/// 管理列表查询条件。
#[derive(Deserialize)]
pub(crate) struct BlockQuery {
    state: Option<String>,
    session_prefix: Option<String>,
    page: Option<i64>,
    page_size: Option<i64>,
}

/// 读取管理员可见的安全分页。
/// @param state 已鉴权应用状态。
/// @param query 用户输入的分页和状态筛选。
/// @return 安全封禁记录或参数错误。
pub(crate) async fn list(
    State(state): State<AppState>,
    Query(query): Query<BlockQuery>,
) -> Result<Json<SessionPolicyBlockPage>, AppError> {
    let filter = query.state.as_deref().unwrap_or("active");
    let prefix = query
        .session_prefix
        .unwrap_or_default()
        .to_ascii_lowercase();
    let page = query.page.unwrap_or(1);
    let size = query.page_size.unwrap_or(20);
    if !matches!(filter, "all" | "active" | "expired" | "released")
        || page < 1
        || !(1..=100).contains(&size)
        || prefix.len() > 64
        || !prefix.bytes().all(|b| b.is_ascii_hexdigit())
    {
        return Err(AppError::BadRequest("封禁列表查询条件无效".into()));
    }
    Ok(Json(
        state
            .gateway_svc
            .session_policy_block_svc
            .store
            .list(filter, &prefix, page, size, Utc::now().timestamp_millis())
            .await?,
    ))
}

/// 提前解除管理员选择的单轮封禁，保留审计记录。
/// @param state 已鉴权应用状态。
/// @param id 封禁轮次 UUID。
/// @return 最新封禁摘要。
pub(crate) async fn release(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<SessionPolicyBlock>, AppError> {
    if Uuid::parse_str(&id).is_err() {
        return Err(AppError::BadRequest("封禁记录标识无效".into()));
    }
    Ok(Json(
        state
            .gateway_svc
            .session_policy_block_svc
            .store
            .release(&id, Utc::now().timestamp_millis())
            .await?,
    ))
}
