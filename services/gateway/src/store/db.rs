//! 数据库连接及版本化迁移的兼容入口。
use sqlx::AnyPool;
use sqlx::any::AnyPoolOptions;
use std::path::Path;

pub use super::database_migrations::migrate;

/// 创建数据库连接池，SQLite 使用持久 WAL 并对每条连接启用外键。
/// @param driver 原数据库驱动。
/// @param dsn 原数据库连接配置。
/// @return SQLx 连接池或连接错误。
pub async fn init_db(driver: &str, dsn: &str) -> Result<AnyPool, sqlx::Error> {
    if driver == "sqlite" {
        if let Some(parent) = Path::new(dsn).parent() {
            std::fs::create_dir_all(parent).ok();
        }
        let pool = AnyPoolOptions::new()
            .after_connect(|connection, _| {
                Box::pin(async move {
                    // 外键开关属于物理连接，连接池扩容或替换连接时也需要设置。
                    sqlx::query("PRAGMA foreign_keys=ON")
                        .execute(connection)
                        .await?;
                    Ok(())
                })
            })
            .connect(&format!("sqlite:{}?mode=rwc", dsn))
            .await?;
        sqlx::query("PRAGMA journal_mode=WAL")
            .execute(&pool)
            .await
            .ok();
        Ok(pool)
    } else {
        let pool = AnyPool::connect(dsn).await?;
        Ok(pool)
    }
}
