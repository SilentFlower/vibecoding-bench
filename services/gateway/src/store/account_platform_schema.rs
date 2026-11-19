//! 追加账号平台及 AGY 凭据操作状态，保持历史迁移定义冻结。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool, Row};

/// 计算本步骤的冻结源码身份。@return 测试段之前定义的 SHA256。
pub fn checksum() -> String {
    let source = include_str!("account_platform_schema.rs")
        .split(concat!("#[cfg(", "test)]"))
        .next()
        .unwrap_or_default();
    format!("{:x}", Sha256::digest(source.as_bytes()))
}

/// 在同一迁移事务追加平台字段和操作元数据。@param connection 迁移连接。@param driver 数据库驱动。@return 结构校验结果。
pub async fn apply(connection: &mut AnyConnection, driver: &str) -> Result<(), sqlx::Error> {
    for (name, declaration) in [
        ("platform", "TEXT NOT NULL DEFAULT 'claude_code'"),
        (
            "agy_system_prompt_homoglyph_enabled",
            "INTEGER NOT NULL DEFAULT 0",
        ),
    ] {
        if driver == "sqlite" {
            let columns = sqlx::query("PRAGMA table_info(accounts)")
                .fetch_all(&mut *connection)
                .await?;
            if columns.iter().any(|row| {
                row.try_get::<String, _>("name")
                    .is_ok_and(|value| value == name)
            }) {
                continue;
            }
            sqlx::query(&format!(
                "ALTER TABLE accounts ADD COLUMN {name} {declaration}"
            ))
            .execute(&mut *connection)
            .await?;
        } else {
            sqlx::query(&format!(
                "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS {name} {declaration}"
            ))
            .execute(&mut *connection)
            .await?;
        }
    }
    // 历史重复行不能在建立约束时被静默合并，否则账号绑定和权威凭据会改变。
    let duplicates: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM (SELECT platform,email FROM accounts GROUP BY platform,email HAVING COUNT(*)>1) AS conflicts")
        .fetch_one(&mut *connection).await?;
    if duplicates > 0 {
        return Err(sqlx::Error::Protocol(
            "历史账号存在同平台重复身份，请先处理冲突".into(),
        ));
    }
    sqlx::query(
        "CREATE UNIQUE INDEX IF NOT EXISTS accounts_platform_email ON accounts(platform,email)",
    )
    .execute(&mut *connection)
    .await?;
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS account_credential_states (
        account_id BIGINT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
        generation BIGINT NOT NULL DEFAULT 1,
        phase TEXT NOT NULL DEFAULT 'ready',
        operation_id TEXT,
        updated_at_ms BIGINT NOT NULL
    )",
    )
    .execute(&mut *connection)
    .await?;
    verify_connection(connection, driver).await
}

/// 核对新字段和状态表可读取。@param connection 当前数据库连接。@return 最低结构校验结果。
pub async fn verify_connection(
    connection: &mut AnyConnection,
    driver: &str,
) -> Result<(), sqlx::Error> {
    let unique: i64 = if driver == "sqlite" {
        sqlx::query_scalar("SELECT COUNT(*) FROM pragma_index_list('accounts') AS indexes WHERE indexes.\"unique\"=1 AND (SELECT GROUP_CONCAT(name,',') FROM pragma_index_info(indexes.name))='platform,email'")
            .fetch_one(&mut *connection).await?
    } else {
        sqlx::query_scalar("SELECT COUNT(*) FROM pg_indexes WHERE schemaname=current_schema() AND tablename='accounts' AND indexdef LIKE 'CREATE UNIQUE INDEX %' AND indexdef LIKE '%(platform, email)'")
            .fetch_one(&mut *connection).await?
    };
    if unique == 0 {
        return Err(sqlx::Error::Protocol("账号平台身份唯一约束无效".into()));
    }
    if driver == "sqlite" {
        let primary: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM pragma_table_info('account_credential_states') WHERE name='account_id' AND pk=1")
            .fetch_one(&mut *connection).await?;
        if primary != 1 {
            return Err(sqlx::Error::Protocol("AGY 凭据归属主键无效".into()));
        }
    }
    sqlx::query("SELECT platform,agy_system_prompt_homoglyph_enabled FROM accounts LIMIT 0")
        .fetch_all(&mut *connection)
        .await?;
    sqlx::query("SELECT account_id,generation,phase,operation_id,updated_at_ms FROM account_credential_states LIMIT 0")
        .fetch_all(&mut *connection).await?;
    Ok(())
}

/// 检查已经登记的账号平台结构。@param pool 当前库连接池。@return 结构检查结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let mut connection = pool.acquire().await?;
    verify_connection(&mut connection, "sqlite").await
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::database_migrations;
    use sqlx::any::AnyPoolOptions;
    use uuid::Uuid;

    #[tokio::test]
    async fn duplicate_history_aborts_upgrade_and_missing_constraint_is_rejected() {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        database_migrations::apply(&pool, &Uuid::new_v4().to_string(), Some(4))
            .await
            .unwrap();
        for _ in 0..2 {
            sqlx::query("INSERT INTO accounts(email,token,device_id) VALUES('duplicate@example.test','synthetic','device')").execute(&pool).await.unwrap();
        }
        assert!(
            database_migrations::apply(&pool, &Uuid::new_v4().to_string(), None)
                .await
                .is_err()
        );
        let version: i64 = sqlx::query_scalar("SELECT MAX(version) FROM system_schema_migrations")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(version, 4);
        sqlx::query("DELETE FROM accounts WHERE id=(SELECT MAX(id) FROM accounts)")
            .execute(&pool)
            .await
            .unwrap();
        database_migrations::apply(&pool, &Uuid::new_v4().to_string(), None)
            .await
            .unwrap();
        sqlx::query("DROP INDEX accounts_platform_email")
            .execute(&pool)
            .await
            .unwrap();
        assert!(verify(&pool).await.is_err());
    }
}
