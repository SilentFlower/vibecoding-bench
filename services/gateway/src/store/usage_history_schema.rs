//! 让用量明细沿原账号 ID 独立保留，沿用原有统计窗口和时间索引。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

/// 返回用量历史迁移的源码摘要。@return SHA256。
pub fn checksum() -> String {
    format!(
        "{:x}",
        Sha256::digest(include_bytes!("usage_history_schema.rs"))
    )
}

/// 解除账号删除对历史明细的级联。@param connection 迁移事务。@param driver 数据库驱动。@return 迁移结果。
pub async fn apply(connection: &mut AnyConnection, driver: &str) -> Result<(), sqlx::Error> {
    if driver != "sqlite" {
        sqlx::query(
            "ALTER TABLE usage_records DROP CONSTRAINT IF EXISTS usage_records_account_id_fkey",
        )
        .execute(connection)
        .await?;
        return Ok(());
    }

    // SQLite 将外键写在建表定义内。一次事务复制全部历史列，替换表和索引后再登记版本。
    let schema_objects: Vec<String> = sqlx::query_scalar(
        "SELECT sql FROM sqlite_master WHERE tbl_name='usage_records' AND type IN ('index','trigger')
            AND name NOT IN ('usage_records_time','usage_records_account_time') AND sql IS NOT NULL ORDER BY type,name",
    ).fetch_all(&mut *connection).await?;
    let columns: Vec<String> =
        sqlx::query_scalar("SELECT name FROM pragma_table_xinfo('usage_records') ORDER BY cid")
            .fetch_all(&mut *connection)
            .await?;
    sqlx::query("CREATE TABLE usage_history_migration (
            record_id TEXT PRIMARY KEY, account_id BIGINT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT NOT NULL, model TEXT NOT NULL,
            input_tokens BIGINT NOT NULL, output_tokens BIGINT NOT NULL, cache_read_tokens BIGINT NOT NULL,
            cache_write_tokens BIGINT NOT NULL, cache_write_5m_tokens BIGINT NOT NULL, cache_write_1h_tokens BIGINT NOT NULL,
            cost_usd DOUBLE PRECISION, partial BIGINT NOT NULL, price_version TEXT NOT NULL
        )").execute(&mut *connection).await?;
    // 依原列名复制，发现额外业务列时在原表仍完整的事务内拒绝替换。
    let names = columns
        .iter()
        .map(|name| format!("\"{}\"", name.replace('"', "\"\"")))
        .collect::<Vec<_>>()
        .join(",");
    sqlx::query(&format!(
        "INSERT INTO usage_history_migration ({names}) SELECT {names} FROM usage_records"
    ))
    .execute(&mut *connection)
    .await?;
    sqlx::query("DROP TABLE usage_records")
        .execute(&mut *connection)
        .await?;
    sqlx::query("ALTER TABLE usage_history_migration RENAME TO usage_records")
        .execute(&mut *connection)
        .await?;
    sqlx::query("CREATE INDEX usage_records_account_time ON usage_records(account_id,started_at)")
        .execute(&mut *connection)
        .await?;
    sqlx::query("CREATE INDEX usage_records_time ON usage_records(started_at)")
        .execute(&mut *connection)
        .await?;
    for statement in schema_objects {
        sqlx::query(&statement).execute(&mut *connection).await?;
    }
    verify_connection(connection).await
}

/// 验证 SQLite 历史账号标识不再级联且统计索引可用。@param pool 网关连接池。@return 核验结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let mut connection = pool.acquire().await?;
    verify_connection(&mut connection).await
}

async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    let valid: i64 = sqlx::query_scalar(
        "SELECT NOT EXISTS (SELECT 1 FROM pragma_foreign_key_list('usage_records') WHERE \"from\"='account_id')
            AND (SELECT COUNT(*) FROM pragma_index_list('usage_records')
                WHERE name IN ('usage_records_time','usage_records_account_time'))=2",
    ).fetch_one(connection).await?;
    if valid != 1 {
        return Err(sqlx::Error::Protocol("历史用量的账号关联或索引无效".into()));
    }
    Ok(())
}
