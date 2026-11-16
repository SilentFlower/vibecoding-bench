//! 会话策略封禁的兼容新增迁移，固定定义独立于业务配置。

use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

const KEYS: &str = "CREATE TABLE IF NOT EXISTS session_policy_block_keys (
    session_key TEXT PRIMARY KEY,
    revision BIGINT NOT NULL DEFAULT 0
)";
const BLOCKS: &str = "CREATE TABLE IF NOT EXISTS session_policy_blocks (
    id TEXT PRIMARY KEY,
    session_key TEXT NOT NULL REFERENCES session_policy_block_keys(session_key),
    api_token_id BIGINT NOT NULL,
    account_id BIGINT NOT NULL,
    model TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_request_id TEXT,
    blocked_at_ms BIGINT NOT NULL,
    expires_at_ms BIGINT NOT NULL,
    released_at_ms BIGINT,
    blocked_request_count BIGINT NOT NULL DEFAULT 0,
    last_blocked_at_ms BIGINT
)";

/// 计算纯定义的登记摘要。
/// @return SHA256 十六进制摘要。
pub fn checksum() -> String {
    let source = include_str!("session_policy_block_schema.rs")
        .split(concat!("#[cfg(", "test)]"))
        .next()
        .unwrap_or_default();
    format!("{:x}", Sha256::digest(source.as_bytes()))
}

/// 在迁移事务中建立状态、历史及缺省配置。
/// @param connection 当前数据库连接。
/// @return DDL 与默认配置写入结果。
pub async fn apply(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    for statement in [
        KEYS,
        BLOCKS,
        "CREATE INDEX IF NOT EXISTS session_policy_blocks_lookup ON session_policy_blocks(session_key, expires_at_ms)",
        "CREATE INDEX IF NOT EXISTS session_policy_blocks_history ON session_policy_blocks(blocked_at_ms, id)",
        "INSERT INTO settings(key,value) VALUES('session_policy_block_enabled','true') ON CONFLICT(key) DO NOTHING",
        "INSERT INTO settings(key,value) VALUES('session_policy_block_duration_minutes','1440') ON CONFLICT(key) DO NOTHING",
    ] {
        sqlx::query(statement).execute(&mut *connection).await?;
    }
    verify_connection(connection).await
}

/// 核对新增表必要字段。
/// @param connection 当前迁移事务连接。
/// @return 结构验证结果。
pub async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    sqlx::query("SELECT session_key,revision FROM session_policy_block_keys LIMIT 0")
        .fetch_all(&mut *connection)
        .await?;
    sqlx::query("SELECT id,session_key,api_token_id,account_id,model,reason,source_request_id,blocked_at_ms,expires_at_ms,released_at_ms,blocked_request_count,last_blocked_at_ms FROM session_policy_blocks LIMIT 0")
        .fetch_all(&mut *connection).await?;
    Ok(())
}

/// 核对已登记结构。
/// @param pool 当前数据库池。
/// @return 结构验证结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let mut connection = pool.acquire().await?;
    verify_connection(&mut connection).await
}
