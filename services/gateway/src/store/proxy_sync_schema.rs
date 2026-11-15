//! 已使用代理修改的可恢复关联同步台账，独立于已冻结的目录版本2。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

const CREATE: &str = "CREATE TABLE IF NOT EXISTS proxy_route_sync (
    id TEXT PRIMARY KEY,
    proxy_id TEXT NOT NULL UNIQUE REFERENCES proxy_routes(id) ON DELETE CASCADE,
    source_connection TEXT NOT NULL,
    target_connection TEXT NOT NULL,
    remaining TEXT NOT NULL,
    created_at TEXT NOT NULL
)";

/// 返回同步台账迁移的固定摘要。@return SHA256。
pub fn checksum() -> String {
    let source = include_str!("proxy_sync_schema.rs")
        .split("#[cfg(test)]")
        .next()
        .unwrap_or_default();
    format!("{:x}", Sha256::digest(source.as_bytes()))
}

/// 在既有迁移事务内创建同步台账。@param connection 当前事务连接。@return DDL结果。
pub async fn apply(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    sqlx::query(CREATE).execute(&mut *connection).await?;
    sqlx::query("SELECT id,proxy_id,source_connection,target_connection,remaining,created_at FROM proxy_route_sync LIMIT 0").fetch_all(&mut *connection).await?;
    Ok(())
}

/// 读取已登记台账的必要结构。@param pool 当前数据库。@return 校验结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let mut connection = pool.acquire().await?;
    verify_connection(&mut connection).await
}

/// 核对SQLite同步身份与单线路唯一性。@param connection 迁移事务。@return 约束校验。
pub async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    let unique: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM pragma_index_list('proxy_route_sync') AS indexes WHERE indexes.\"unique\"=1 AND (SELECT GROUP_CONCAT(name,',') FROM pragma_index_info(indexes.name))='proxy_id'").fetch_one(&mut *connection).await?;
    let primary: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM pragma_table_info('proxy_route_sync') WHERE name='id' AND type='TEXT' AND pk=1").fetch_one(&mut *connection).await?;
    if unique == 0 || primary != 1 {
        return Err(sqlx::Error::Protocol("代理同步台账约束无效".into()));
    }
    sqlx::query("SELECT id,proxy_id,source_connection,target_connection,remaining,created_at FROM proxy_route_sync LIMIT 0").fetch_all(&mut *connection).await?;
    Ok(())
}
