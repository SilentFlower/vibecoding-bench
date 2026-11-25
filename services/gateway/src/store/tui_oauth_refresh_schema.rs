//! V2 账号的已拒绝 AT 和提交结果未知的 RT。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

/// 返回追加迁移的源码摘要。@return SHA-256。
pub fn checksum() -> String {
    format!(
        "{:x}",
        Sha256::digest(include_bytes!("tui_oauth_refresh_schema.rs"))
    )
}

/// 在迁移事务中创建保护记录。@param connection 迁移连接。@return 执行结果。
pub async fn apply(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS tui_oauth_refresh (
            account_id BIGINT NOT NULL PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
            refresh_sha256 TEXT NOT NULL, rejected_access_sha256 TEXT NOT NULL,
            pending INTEGER NOT NULL CHECK (pending IN (0,1)))",
    )
    .execute(&mut *connection)
    .await?;
    Ok(())
}

/// 核验 SQLite 的凭据保护记录。@param pool 连接池。@return 结构校验结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    verify_connection(&mut *pool.acquire().await?).await
}

/// 在迁移事务内核验 SQLite 账号约束。@param connection 数据库连接。@return 结构校验结果。
pub async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    sqlx::query("SELECT account_id,refresh_sha256,rejected_access_sha256,pending FROM tui_oauth_refresh LIMIT 0")
        .execute(&mut *connection)
        .await?;
    let valid: i64 = sqlx::query_scalar(
        r#"SELECT COUNT(*) FROM pragma_table_info('tui_oauth_refresh')
           WHERE name='account_id' AND pk=1 AND "notnull"=1
             AND (SELECT COUNT(*) FROM pragma_table_info('tui_oauth_refresh') WHERE pk>0)=1
             AND EXISTS (SELECT 1 FROM pragma_foreign_key_list('tui_oauth_refresh')
                 WHERE "from"='account_id' AND "table"='accounts' AND "to"='id' AND on_delete='CASCADE')"#,
    )
    .fetch_one(&mut *connection)
    .await?;
    if valid != 1 {
        return Err(sqlx::Error::Protocol(
            "V2 OAuth 保护记录的账号约束无效".into(),
        ));
    }
    Ok(())
}
