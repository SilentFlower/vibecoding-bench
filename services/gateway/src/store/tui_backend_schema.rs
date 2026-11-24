//! V2 账号切换意向、原生工具轮及其历史证明的追加迁移。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

/// 返回此次纯迁移定义的摘要。@return SHA-256。
pub fn checksum() -> String {
    format!(
        "{:x}",
        Sha256::digest(include_bytes!("tui_backend_schema.rs"))
    )
}

/// 在调用方事务内建表，兼容已运行隔离候选的数据库。@param connection 当前连接。@return 迁移结果。
pub async fn apply(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    for statement in [
        "CREATE TABLE IF NOT EXISTS tui_backend_intents (
                account_id BIGINT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
                target TEXT NOT NULL, binding TEXT NOT NULL, revision BIGINT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS tui_native_turns (
                id TEXT PRIMARY KEY, account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                principal_id BIGINT NOT NULL, session_id TEXT NOT NULL, binding TEXT NOT NULL,
                version TEXT NOT NULL, tools TEXT NOT NULL)",
        "CREATE INDEX IF NOT EXISTS tui_native_turns_account ON tui_native_turns(account_id)",
        "CREATE TABLE IF NOT EXISTS tui_stateless_turn_proofs (
                turn_id TEXT PRIMARY KEY REFERENCES tui_native_turns(id) ON DELETE CASCADE,
                history TEXT NOT NULL, declarations TEXT NOT NULL)",
    ] {
        sqlx::query(statement).execute(&mut *connection).await?;
    }
    Ok(())
}

/// 逐表核验 SQLite 的必需字段、主键与级联归属。@param connection 当前连接。@return 校验结果。
pub async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    for (table, primary, owner, parent, fields) in [
        (
            "tui_backend_intents",
            "account_id",
            "account_id",
            "accounts",
            "SELECT account_id,target,binding,revision FROM tui_backend_intents LIMIT 0",
        ),
        (
            "tui_native_turns",
            "id",
            "account_id",
            "accounts",
            "SELECT id,account_id,principal_id,session_id,binding,version,tools FROM tui_native_turns LIMIT 0",
        ),
        (
            "tui_stateless_turn_proofs",
            "turn_id",
            "turn_id",
            "tui_native_turns",
            "SELECT turn_id,history,declarations FROM tui_stateless_turn_proofs LIMIT 0",
        ),
    ] {
        sqlx::query(fields).execute(&mut *connection).await?;
        let valid: i64 = sqlx::query_scalar(
            r#"SELECT COUNT(*) FROM pragma_table_info($1)
               WHERE name=$2 AND pk=1
                 AND (SELECT COUNT(*) FROM pragma_table_info($1) WHERE pk>0)=1
                 AND EXISTS (SELECT 1 FROM pragma_foreign_key_list($1)
                     WHERE "from"=$3 AND "table"=$4 AND "to"='id' AND on_delete='CASCADE')"#,
        )
        .bind(table)
        .bind(primary)
        .bind(owner)
        .bind(parent)
        .fetch_one(&mut *connection)
        .await?;
        if valid != 1 {
            return Err(sqlx::Error::Protocol(format!(
                "V2 工具轮归属约束无效：{table}"
            )));
        }
    }
    let index: i64 = sqlx::query_scalar(
        r#"SELECT COUNT(*) FROM pragma_index_list('tui_native_turns')
           WHERE name='tui_native_turns_account'
             AND (SELECT group_concat(name, ',') FROM pragma_index_info('tui_native_turns_account'))='account_id'"#,
    ).fetch_one(&mut *connection).await?;
    if index != 1 {
        return Err(sqlx::Error::Protocol("V2 工具轮账号索引无效".into()));
    }
    Ok(())
}

/// 核对已登记的 SQLite 结构。@param pool 数据库连接池。@return 校验结果。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let mut connection = pool.acquire().await?;
    verify_connection(&mut connection).await
}
