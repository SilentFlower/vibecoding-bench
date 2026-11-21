//! 数据库连接及版本化迁移的兼容入口。
use sqlx::any::{AnyConnectOptions, AnyPoolOptions};
use sqlx::sqlite::SqliteConnectOptions;
use sqlx::{AnyPool, ConnectOptions};
use std::path::{Path, PathBuf};

pub use super::database_migrations::migrate;

/// 创建数据库连接池，SQLite 使用持久 WAL 并对每条连接启用外键。
/// @param driver 原数据库驱动。
/// @param dsn 原数据库连接配置。
/// @return SQLx 连接池或连接错误。
pub async fn init_db(driver: &str, dsn: &str) -> Result<AnyPool, sqlx::Error> {
    if driver == "sqlite" {
        let (options, filename) = sqlite_connection_options(dsn, false)?;
        connect_sqlite(options, &filename).await
    } else {
        AnyPool::connect(dsn).await
    }
}

/// 将 SQLite 配置解析为统一的连接选项和实际文件名。
/// @param dsn 文件路径或 SQLite DSN。
/// @param read_only 离线检查是否强制只读。
/// @return 连接选项与物理路径，或配置解析错误。
pub(super) fn sqlite_connection_options(
    dsn: &str,
    read_only: bool,
) -> Result<(AnyConnectOptions, PathBuf), sqlx::Error> {
    let mut options: AnyConnectOptions = if dsn.starts_with("sqlite:") {
        dsn.parse()?
    } else {
        format!("sqlite:{dsn}").parse()?
    };
    let url = &mut options.database_url;
    let filename = SqliteConnectOptions::from_url(url)?
        .get_filename()
        .into_owned();
    if read_only {
        // 离线检查以命令的只读意图为准，保留 DSN 中与访问模式无关的选项。
        let other_pairs: Vec<_> = url
            .query_pairs()
            .into_owned()
            .filter(|(key, _)| key != "mode")
            .collect();
        url.query_pairs_mut()
            .clear()
            .extend_pairs(other_pairs)
            .append_pair("mode", "ro");
    } else if !url.query_pairs().any(|(key, _)| key == "mode") {
        url.query_pairs_mut().append_pair("mode", "rwc");
    }
    Ok((options, filename))
}

/// 为启动和离线写入准备目录并初始化同一 SQLite 连接池。
/// @param options 已解析的连接选项。
/// @param filename 与选项一致的 SQLite 文件路径。
/// @return 已设置外键的连接池或连接错误。
pub(super) async fn connect_sqlite(
    options: AnyConnectOptions,
    filename: &Path,
) -> Result<AnyPool, sqlx::Error> {
    if options
        .database_url
        .query_pairs()
        .any(|(key, value)| key == "mode" && value == "rwc")
        && let Some(parent) = filename.parent()
    {
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
        .connect_with(options)
        .await?;
    sqlx::query("PRAGMA journal_mode=WAL")
        .execute(&pool)
        .await
        .ok();
    Ok(pool)
}
