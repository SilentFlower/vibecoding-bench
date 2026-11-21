//! 追加跨网关重启的 AGY 工具批次回执。表内不保存请求或响应正文。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

/// 返回冻结的迁移摘要。@return SHA256。
pub fn checksum() -> String {
    format!(
        "{:x}",
        Sha256::digest(include_bytes!("agy_tool_receipts_schema.rs"))
    )
}

/// 建立工具批次回执和查找索引。@param connection 当前事务。@return 迁移结果。
pub async fn apply(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    for statement in [
        "CREATE TABLE IF NOT EXISTS agy_tool_receipts (
            batch_key TEXT PRIMARY KEY NOT NULL, call_key TEXT NOT NULL, prefix_key TEXT NOT NULL, call_shape TEXT NOT NULL,
            token_id BIGINT NOT NULL, account_id BIGINT NOT NULL, session_scope TEXT NOT NULL, source_id TEXT NOT NULL,
            attempt_id TEXT NOT NULL, body_key TEXT NOT NULL, phase TEXT NOT NULL,
            recovered BIGINT NOT NULL, source_closed BIGINT NOT NULL, expires_ms BIGINT NOT NULL,
            signature_keys TEXT NOT NULL
        )",
        "CREATE INDEX IF NOT EXISTS idx_agy_tool_receipts_calls ON agy_tool_receipts(call_key)",
        "CREATE INDEX IF NOT EXISTS idx_agy_tool_receipts_prefix ON agy_tool_receipts(prefix_key)",
        "CREATE INDEX IF NOT EXISTS idx_agy_tool_receipts_expiry ON agy_tool_receipts(expires_ms)",
    ] {
        sqlx::query(statement).execute(&mut *connection).await?;
    }
    Ok(())
}

/// 核对已登记的回执结构。@param pool 数据库连接池。@return 校验结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let columns: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM pragma_table_info('agy_tool_receipts')")
            .fetch_one(pool)
            .await?;
    if columns != 15 {
        return Err(sqlx::Error::Protocol("AGY 工具批次回执结构无效".into()));
    }
    Ok(())
}
