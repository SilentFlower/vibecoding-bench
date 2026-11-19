//! 追加请求诊断筛选投影，历史摘要及既有迁移保持原身份。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool, Row};

/// 计算本步骤源码身份。@return 测试定义之前的SHA256。
pub fn checksum() -> String {
    let source = include_str!("request_records_schema.rs")
        .split(concat!("#[cfg(", "test)]"))
        .next()
        .unwrap_or_default();
    format!("{:x}", Sha256::digest(source.as_bytes()))
}

/// 追加可空筛选投影及索引，保留历史事实未知。@param connection 迁移事务连接。@param driver 数据库类型。@return 校验结果。
pub async fn apply(connection: &mut AnyConnection, driver: &str) -> Result<(), sqlx::Error> {
    for (table, columns) in [
        (
            "request_diagnostics",
            &["platform", "entry_protocol", "requested_model"][..],
        ),
        (
            "request_diagnostic_attempts",
            &["platform", "kernel_version", "actual_model"][..],
        ),
    ] {
        for name in columns {
            if driver == "sqlite" {
                let rows = sqlx::query(&format!("PRAGMA table_info({table})"))
                    .fetch_all(&mut *connection)
                    .await?;
                if rows.iter().any(|row| {
                    row.try_get::<String, _>("name")
                        .is_ok_and(|value| value == *name)
                }) {
                    continue;
                }
                sqlx::query(&format!("ALTER TABLE {table} ADD COLUMN {name} TEXT"))
                    .execute(&mut *connection)
                    .await?;
            } else {
                sqlx::query(&format!(
                    "ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} TEXT"
                ))
                .execute(&mut *connection)
                .await?;
            }
        }
    }
    for sql in [
        "CREATE INDEX IF NOT EXISTS request_diagnostics_platform ON request_diagnostics(platform,entry_protocol,started_at)",
        "CREATE INDEX IF NOT EXISTS request_diagnostics_model ON request_diagnostics(requested_model,started_at)",
        "CREATE INDEX IF NOT EXISTS request_attempts_kernel ON request_diagnostic_attempts(kernel_version,request_id)",
        "CREATE INDEX IF NOT EXISTS request_attempts_model ON request_diagnostic_attempts(actual_model,request_id)",
    ] {
        sqlx::query(sql).execute(&mut *connection).await?;
    }
    verify_connection(connection).await
}

/// 核对追加字段可读，损坏结构保持失败。@param connection 当前连接。@return 最低结构检查结果。
pub async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    sqlx::query("SELECT platform,entry_protocol,requested_model FROM request_diagnostics LIMIT 0")
        .fetch_all(&mut *connection)
        .await?;
    sqlx::query(
        "SELECT platform,kernel_version,actual_model FROM request_diagnostic_attempts LIMIT 0",
    )
    .fetch_all(&mut *connection)
    .await?;
    Ok(())
}

/// 核验已登记的请求诊断结构。@param pool 当前数据库池。@return 检查结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    verify_connection(&mut *pool.acquire().await?).await
}
