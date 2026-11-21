//! 追加默认关闭的 AGY 系统提示词位置试验选项。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

/// 计算冻结迁移定义的摘要。
/// @return 迁移源码的 SHA256。
pub fn checksum() -> String {
    format!(
        "{:x}",
        Sha256::digest(include_bytes!("agy_system_reminder_schema.rs"))
    )
}

/// 为现有账号和新账号提供关闭的初始值。
/// @param connection 当前迁移事务。
/// @param driver 数据库驱动。
/// @return 迁移及结构校验结果。
pub async fn apply(connection: &mut AnyConnection, driver: &str) -> Result<(), sqlx::Error> {
    if driver != "sqlite" {
        sqlx::query(
            "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS agy_system_prompt_as_user_reminder INTEGER NOT NULL DEFAULT 0",
        )
        .execute(&mut *connection)
        .await?;
        return Ok(());
    }
    let present: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM pragma_table_info('accounts') WHERE name='agy_system_prompt_as_user_reminder'",
    )
    .fetch_one(&mut *connection)
    .await?;
    if present == 0 {
        sqlx::query(
            "ALTER TABLE accounts ADD COLUMN agy_system_prompt_as_user_reminder INTEGER NOT NULL DEFAULT 0",
        )
        .execute(&mut *connection)
        .await?;
    }
    verify_connection(connection).await
}

/// 检查已登记的 SQLite 账号列。
/// @param pool 当前数据库连接池。
/// @return 结构校验结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let mut connection = pool.acquire().await?;
    verify_connection(&mut connection).await
}

async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    let valid: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM pragma_table_info('accounts') WHERE name='agy_system_prompt_as_user_reminder' AND type='INTEGER' AND \"notnull\"=1 AND dflt_value='0'",
    )
    .fetch_one(connection)
    .await?;
    if valid != 1 {
        return Err(sqlx::Error::Protocol(
            "AGY 系统提示词位置账号开关定义无效".into(),
        ));
    }
    Ok(())
}
