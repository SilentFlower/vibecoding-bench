//! 为 AGY 账号追加 GIF 抽帧开关。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

/// 核对迁移源码身份。@return 冻结迁移源码的 SHA256。
pub fn checksum() -> String {
    format!(
        "{:x}",
        Sha256::digest(include_bytes!("agy_media_schema.rs"))
    )
}

/// 给新旧账号补齐默认关闭的开关。@param connection 迁移事务。@param driver 数据库驱动。@return 迁移结果。
pub async fn apply(connection: &mut AnyConnection, driver: &str) -> Result<(), sqlx::Error> {
    if driver != "sqlite" {
        sqlx::query("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS agy_gif_frames_enabled INTEGER NOT NULL DEFAULT 0")
            .execute(&mut *connection)
            .await?;
    } else {
        let present: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM pragma_table_info('accounts') WHERE name='agy_gif_frames_enabled'",
        )
        .fetch_one(&mut *connection)
        .await?;
        if present == 0 {
            sqlx::query(
                "ALTER TABLE accounts ADD COLUMN agy_gif_frames_enabled INTEGER NOT NULL DEFAULT 0",
            )
            .execute(&mut *connection)
            .await?;
        }
    }
    sqlx::query("SELECT agy_gif_frames_enabled FROM accounts LIMIT 0")
        .execute(&mut *connection)
        .await?;
    Ok(())
}

/// 核对已登记版本的实际列。@param pool SQLite 连接池。@return 结构校验结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let valid: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM pragma_table_info('accounts') WHERE name='agy_gif_frames_enabled' AND type='INTEGER' AND \"notnull\"=1 AND dflt_value='0'")
        .fetch_one(pool)
        .await?;
    if valid != 1 {
        return Err(sqlx::Error::Protocol("AGY GIF 账号开关定义无效".into()));
    }
    Ok(())
}
