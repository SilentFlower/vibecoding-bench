//! 账号工作开关的增量定义，与账号健康状态及凭据独立保存。

use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

/// 返回本次增量定义的登记摘要。@return SHA256 摘要。
pub fn checksum() -> String {
    format!(
        "{:x}",
        Sha256::digest(include_str!("account_work_schema.rs").as_bytes())
    )
}

/// 建立独立工作控制表。@param connection 当前事务。@return 执行结果。
pub async fn apply(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    sqlx::query("CREATE TABLE IF NOT EXISTS account_work_controls (account_id BIGINT PRIMARY KEY, api_accepting INTEGER NOT NULL DEFAULT 1, work_enabled INTEGER NOT NULL DEFAULT 1, revision BIGINT NOT NULL DEFAULT 0)")
        .execute(&mut *connection).await?;
    verify_connection(connection).await
}

/// 核对新增控制结构。@param connection 当前连接。@return 核对结果。
pub async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    sqlx::query(
        "SELECT account_id,api_accepting,work_enabled,revision FROM account_work_controls LIMIT 0",
    )
    .fetch_all(connection)
    .await?;
    Ok(())
}

/// 核对已登记迁移。@param pool 数据库。@return 核对结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    verify_connection(&mut *pool.acquire().await?).await
}
