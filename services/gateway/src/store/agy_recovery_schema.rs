//! 追加反重力凭据原操作的脱敏诊断。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

/// 返回冻结定义的摘要。@return 迁移源码的 SHA256。
pub fn checksum() -> String {
    format!(
        "{:x}",
        Sha256::digest(include_bytes!("agy_recovery_schema.rs"))
    )
}

/// 补齐已有及新库的诊断字段。@param connection 迁移事务。@param driver 数据库驱动。@return 执行结果。
pub async fn apply(connection: &mut AnyConnection, driver: &str) -> Result<(), sqlx::Error> {
    for name in ["first_failure", "recovery_status"] {
        if driver == "sqlite" {
            let present: i64 = sqlx::query_scalar(
                "SELECT COUNT(*) FROM pragma_table_info('account_credential_states') WHERE name=$1",
            )
            .bind(name)
            .fetch_one(&mut *connection)
            .await?;
            if present > 0 {
                continue;
            }
        }
        let optional = if driver == "sqlite" {
            ""
        } else {
            "IF NOT EXISTS "
        };
        sqlx::query(&format!(
            "ALTER TABLE account_credential_states ADD COLUMN {optional}{name} TEXT NOT NULL DEFAULT ''"
        ))
        .execute(&mut *connection)
        .await?;
    }
    Ok(())
}

/// 核对已登记的 SQLite 回执结构。@param pool 本库连接。@return 核验结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let count: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM pragma_table_info('account_credential_states') WHERE name IN ('first_failure','recovery_status') AND type='TEXT' AND \"notnull\"=1 AND dflt_value=$1",
    )
    .bind("''")
    .fetch_one(pool)
    .await?;
    if count != 2 {
        return Err(sqlx::Error::Protocol("AGY 恢复诊断结构无效".into()));
    }
    Ok(())
}
