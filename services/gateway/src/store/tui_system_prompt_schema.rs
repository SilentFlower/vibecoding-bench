//! 为 V2 账号登记客户端系统提示词动作，已有账号默认追加。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

const DEFINITION: &str = "tui_system_prompt_policy TEXT NOT NULL DEFAULT 'append' CHECK(tui_system_prompt_policy IN ('append','replace','user_reminder'))";

/// 计算本次结构迁移的源码摘要。@return SHA256。
pub fn checksum() -> String {
    format!(
        "{:x}",
        Sha256::digest(include_bytes!("tui_system_prompt_schema.rs"))
    )
}

/// 为双库新旧账号补齐 V2 动作。
/// @param connection 当前事务。@param driver 数据库驱动。@return 写入及结构校验结果。
pub async fn apply(connection: &mut AnyConnection, driver: &str) -> Result<(), sqlx::Error> {
    if driver != "sqlite" {
        sqlx::query(&format!(
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS {DEFINITION}"
        ))
        .execute(&mut *connection)
        .await?;
        return Ok(());
    }
    let present: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM pragma_table_info('accounts') WHERE name='tui_system_prompt_policy'",
    )
    .fetch_one(&mut *connection)
    .await?;
    if present == 0 {
        sqlx::query(&format!("ALTER TABLE accounts ADD COLUMN {DEFINITION}"))
            .execute(&mut *connection)
            .await?;
    }
    verify_connection(connection).await
}

/// 核对已经登记的 SQLite 结构。@param pool 当前数据库连接池。@return 核对结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let mut connection = pool.acquire().await?;
    verify_connection(&mut connection).await
}

async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    let valid: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM pragma_table_info('accounts') WHERE name='tui_system_prompt_policy' AND type='TEXT' AND \"notnull\"=1 AND dflt_value=$1",
    )
    .bind("'append'")
    .fetch_one(connection)
    .await?;
    if valid != 1 {
        return Err(sqlx::Error::Protocol(
            "V2 账号系统提示词动作列定义无效".into(),
        ));
    }
    Ok(())
}
