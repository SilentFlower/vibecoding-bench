//! 原生消息断点设置的一次性默认值兼容及持久选择回归。

use claude_code_gateway::service::rewriter::MessageCacheControlRewrite;
use claude_code_gateway::store::settings_store::SettingsStore;
use sqlx::AnyPool;
use sqlx::any::AnyPoolOptions;
use std::collections::HashMap;
use std::env::{temp_dir, var};
use std::fs::remove_file;
use uuid::Uuid;

/// 验证首次关闭、隐藏标记、并发兼容和迁移后的手动选择。
/// @param pool 独立临时设置数据库。
/// @param driver 当前数据库方言。
/// @return 无；兼容行为与用户约定不符时失败。
async fn check_defaults(pool: AnyPool, driver: &str) {
    sqlx::query("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        .execute(&pool)
        .await
        .unwrap();
    let store = SettingsStore::new_with_driver(pool.clone(), driver.into());
    for old in [
        "off", "sub2api", "auto", "rolling", "stateful", "stable", "anchored", "invalid",
    ] {
        sqlx::query("DELETE FROM settings")
            .execute(&pool)
            .await
            .unwrap();
        store
            .upsert_many(&HashMap::from([
                ("message_cache_control_rewrite".into(), old.into()),
                ("synthetic_unrelated".into(), "keep".into()),
            ]))
            .await
            .unwrap();
        let (first, second) = tokio::join!(
            store.ensure_native_message_cache_defaults(),
            store.ensure_native_message_cache_defaults()
        );
        first.unwrap();
        second.unwrap();
        let current = store.get_all().await.unwrap();
        assert_eq!(current.len(), 2);
        assert_eq!(current["message_cache_control_rewrite"], "off");
        assert_eq!(current["synthetic_unrelated"], "keep");
        store
            .upsert_many(&HashMap::from([(
                "message_cache_control_rewrite".into(),
                "sub2api".into(),
            )]))
            .await
            .unwrap();
        let restarted = SettingsStore::new_with_driver(pool.clone(), driver.into());
        restarted
            .ensure_native_message_cache_defaults()
            .await
            .unwrap();
        assert_eq!(
            restarted
                .get_value("message_cache_control_rewrite", "off")
                .await
                .unwrap(),
            "sub2api"
        );
        let keys: Vec<(String,)> = sqlx::query_as("SELECT key FROM settings")
            .fetch_all(&pool)
            .await
            .unwrap();
        let internal = &keys
            .iter()
            .find(|(key,)| !current.contains_key(key))
            .unwrap()
            .0;
        assert!(
            store
                .upsert_many(&HashMap::from([(internal.clone(), "reset".into())]))
                .await
                .is_err()
        );
    }
    sqlx::query("DELETE FROM settings")
        .execute(&pool)
        .await
        .unwrap();
    store.ensure_native_message_cache_defaults().await.unwrap();
    assert_eq!(
        store.get_all().await.unwrap(),
        HashMap::from([("message_cache_control_rewrite".into(), "off".into())])
    );
    if driver == "postgres" {
        sqlx::query("DELETE FROM settings")
            .execute(&pool)
            .await
            .unwrap();
        store
            .upsert_many(&HashMap::from([(
                "message_cache_control_rewrite".into(),
                "sub2api".into(),
            )]))
            .await
            .unwrap();
        sqlx::query("CREATE FUNCTION reject_cache_reset() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic-reset-failure'; END $$").execute(&pool).await.unwrap();
        sqlx::query("CREATE TRIGGER reject_cache_reset BEFORE UPDATE ON settings FOR EACH ROW EXECUTE FUNCTION reject_cache_reset()").execute(&pool).await.unwrap();
        assert!(store.ensure_native_message_cache_defaults().await.is_err());
        let count: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM settings")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(count.0, 1);
        assert_eq!(
            store
                .get_value("message_cache_control_rewrite", "off")
                .await
                .unwrap(),
            "sub2api"
        );
        sqlx::query("DROP TRIGGER reject_cache_reset ON settings")
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("DROP FUNCTION reject_cache_reset()")
            .execute(&pool)
            .await
            .unwrap();
        store.ensure_native_message_cache_defaults().await.unwrap();
        assert_eq!(
            store
                .get_value("message_cache_control_rewrite", "invalid")
                .await
                .unwrap(),
            "off"
        );
    }
    pool.close().await;
}

/// SQLite 多连接验证重置只发生一次，后续选择跨存储实例保留。
/// @return 无；首次或重复兼容异常时失败。
#[tokio::test]
async fn sqlite_native_message_cache_defaults() {
    sqlx::any::install_default_drivers();
    let file = temp_dir().join(format!("native-cache-settings-{}.sqlite", Uuid::new_v4()));
    let pool = AnyPoolOptions::new()
        .max_connections(4)
        .connect(&format!("sqlite://{}?mode=rwc", file.display()))
        .await
        .unwrap();
    check_defaults(pool, "sqlite").await;
    remove_file(file).unwrap();
}

/// SQLite 写入失败时，重置和迁移标记整体回滚，重试可完成。
/// @return 无；失败遗留标记或重试失效时失败。
#[tokio::test]
async fn sqlite_native_message_cache_reset_rolls_back() {
    sqlx::any::install_default_drivers();
    let pool = AnyPoolOptions::new()
        .max_connections(1)
        .connect("sqlite::memory:")
        .await
        .unwrap();
    sqlx::query("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        .execute(&pool)
        .await
        .unwrap();
    let store = SettingsStore::new(pool.clone());
    store
        .upsert_many(&HashMap::from([(
            "message_cache_control_rewrite".into(),
            "sub2api".into(),
        )]))
        .await
        .unwrap();
    sqlx::query("CREATE TRIGGER reject_cache_reset BEFORE UPDATE ON settings BEGIN SELECT RAISE(FAIL, 'synthetic-reset-failure'); END").execute(&pool).await.unwrap();
    assert!(store.ensure_native_message_cache_defaults().await.is_err());
    let count: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM settings")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(count.0, 1);
    assert_eq!(
        store
            .get_value("message_cache_control_rewrite", "off")
            .await
            .unwrap(),
        "sub2api"
    );
    sqlx::query("DROP TRIGGER reject_cache_reset")
        .execute(&pool)
        .await
        .unwrap();
    store.ensure_native_message_cache_defaults().await.unwrap();
    assert_eq!(
        store
            .get_value("message_cache_control_rewrite", "invalid")
            .await
            .unwrap(),
        "off"
    );
}

/// PostgreSQL 使用独立临时数据库验证相同设置合同。
/// @return 无；需测试专用DSN，设置兼容异常时失败。
#[tokio::test]
#[ignore = "需要通过CC2API_CACHE_TEST_POSTGRES_DSN指定独立临时数据库"]
async fn postgres_native_message_cache_defaults() {
    sqlx::any::install_default_drivers();
    let dsn = var("CC2API_CACHE_TEST_POSTGRES_DSN").unwrap();
    let pool = AnyPoolOptions::new()
        .max_connections(4)
        .connect(&dsn)
        .await
        .unwrap();
    check_defaults(pool, "postgres").await;
}

/// 管理设置只接受两个显式模式，废弃值由迁移归一化。
/// @return 无；退出范围的设置仍可保存时失败。
#[test]
fn native_message_cache_setting_accepts_only_off_and_sub2api() {
    assert_eq!(
        MessageCacheControlRewrite::parse_setting("off").unwrap(),
        MessageCacheControlRewrite::Off
    );
    assert_eq!(
        MessageCacheControlRewrite::parse_setting("sub2api").unwrap(),
        MessageCacheControlRewrite::Sub2api
    );
    for value in [
        "auto", "rolling", "stateful", "stable", "anchored", "", " off", "SUB2API",
    ] {
        assert!(MessageCacheControlRewrite::parse_setting(value).is_err());
    }
}
