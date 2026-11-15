//! 独立追加的代理目录迁移，保留已冻结的网关基线。
use sha2::{Digest, Sha256};
use sqlx::{AnyConnection, AnyPool};

const CREATE: &str = "CREATE TABLE IF NOT EXISTS proxy_routes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    connection TEXT NOT NULL,
    public_url TEXT NOT NULL,
    expires_at TEXT,
    revision TEXT NOT NULL,
    observation TEXT NOT NULL DEFAULT '{}',
    checked_at TEXT,
    status TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)";

/// 返回独立迁移源码摘要，测试代码不进入持久合同。
/// @return SHA256摘要。
pub fn checksum() -> String {
    let source = include_str!("proxy_schema.rs")
        .split("#[cfg(test)]")
        .next()
        .unwrap_or_default();
    format!("{:x}", Sha256::digest(source.as_bytes()))
}

/// 在调用者的迁移事务内创建目录。
/// @param connection 当前迁移连接。
/// @return 创建及结构校验结果。
pub async fn apply(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    sqlx::query(CREATE).execute(&mut *connection).await?;
    sqlx::query(
        "CREATE UNIQUE INDEX IF NOT EXISTS proxy_routes_connection ON proxy_routes(connection)",
    )
    .execute(&mut *connection)
    .await?;
    sqlx::query("CREATE INDEX IF NOT EXISTS proxy_routes_name_id ON proxy_routes(name,id)")
        .execute(&mut *connection)
        .await?;
    sqlx::query("SELECT id,name,connection,public_url,expires_at,revision,observation,checked_at,status,created_at,updated_at FROM proxy_routes LIMIT 0")
        .fetch_all(&mut *connection).await?;
    Ok(())
}

/// 校验已登记目录的最低结构。
/// @param pool 当前库连接池。
/// @return 目录可读时成功。
pub async fn verify(pool: &AnyPool) -> Result<(), sqlx::Error> {
    let mut connection = pool.acquire().await?;
    verify_connection(&mut connection).await
}

/// 在SQLite迁移提交前复核约束，异常时整个步骤回滚。
/// @param connection 当前事务连接。@return 校验结果。
pub async fn verify_connection(connection: &mut AnyConnection) -> Result<(), sqlx::Error> {
    let unique: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM pragma_index_list('proxy_routes') AS indexes WHERE indexes.\"unique\"=1 AND (SELECT GROUP_CONCAT(name,',') FROM pragma_index_info(indexes.name))='connection'")
        .fetch_one(&mut *connection).await?;
    let primary: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM pragma_table_info('proxy_routes') WHERE name='id' AND type='TEXT' AND pk=1")
        .fetch_one(&mut *connection).await?;
    if unique == 0 || primary != 1 {
        return Err(sqlx::Error::Protocol("代理目录唯一约束或主键无效".into()));
    }

    sqlx::query("SELECT id,name,connection,public_url,expires_at,revision,observation,checked_at,status,created_at,updated_at FROM proxy_routes LIMIT 0")
        .fetch_all(&mut *connection).await?;
    Ok(())
}
