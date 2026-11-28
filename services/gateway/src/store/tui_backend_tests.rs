use std::env;
use std::fs;

use sqlx::Row;
use sqlx::any::install_default_drivers;
use uuid::Uuid;

use crate::store::account_store::AccountStore;
use crate::store::db::{init_db, migrate};

/// 用两个账号和两个并发保存者校验真实驱动下的意向事务及重开恢复。
/// @param driver 数据库驱动。@param dsn 此次测试的隔离数据库。
async fn verify_switch_transactions(driver: &str, dsn: &str) {
    install_default_drivers();
    let pool = init_db(driver, dsn).await.unwrap();
    migrate(&pool, driver).await.unwrap();
    let store = AccountStore::new(pool.clone(), driver.into());
    let mut ids = Vec::new();
    for _ in 0..2 {
        let identity = Uuid::new_v4().to_string();
        let row = sqlx::query(
            "INSERT INTO accounts(name,email,token,device_id,request_backend)
             VALUES($1,$2,$3,$4,'native293') RETURNING id",
        )
        .bind(&identity)
        .bind(format!("{identity}@example.invalid"))
        .bind("synthetic")
        .bind("test-device")
        .fetch_one(&pool)
        .await
        .unwrap();
        ids.push(row.get::<i64, _>("id"));
    }
    let initial = store.tui_backend(ids[0]).await.unwrap();
    let left = store.update_tui_backend(ids[0], &initial, "native293", "tui_v2", "first");
    let right = store.update_tui_backend(ids[0], &initial, "native293", "tui_v2", "second");
    let (left, right) = tokio::join!(left, right);
    assert_ne!(left.is_ok(), right.is_ok(), "同一修订只能写入一次");
    let winning = left.or(right).unwrap();
    pool.close().await;

    let reopened = init_db(driver, dsn).await.unwrap();
    let store = AccountStore::new(reopened.clone(), driver.into());
    let pending = store.tui_backend(ids[0]).await.unwrap();
    assert_eq!(pending.active, "native293");
    assert_eq!(pending.target, "tui_v2");
    assert_eq!(pending.binding, winning.binding);
    assert_eq!(pending.revision, initial.revision + 1);
    sqlx::query("UPDATE accounts SET status='disabled' WHERE id IN ($1,$2)")
        .bind(ids[0])
        .bind(ids[1])
        .execute(&reopened)
        .await
        .unwrap();
    let disabled = store.tui_backend(ids[1]).await.unwrap();
    for (id, snapshot, active, target) in [
        (ids[0], &pending, "tui_v2", ""),
        (ids[1], &disabled, "native293", "tui_v2"),
    ] {
        assert!(
            store
                .update_tui_backend(id, snapshot, active, target, "disabled")
                .await
                .is_err()
        );
        let unchanged = store.tui_backend(id).await.unwrap();
        assert_eq!(unchanged.active, snapshot.active);
        assert_eq!(unchanged.target, snapshot.target);
        assert_eq!(unchanged.revision, snapshot.revision);
        assert_eq!(unchanged.binding, snapshot.binding);
    }
    sqlx::query("UPDATE accounts SET status='active' WHERE id=$1")
        .bind(ids[0])
        .execute(&reopened)
        .await
        .unwrap();
    let applied = store
        .update_tui_backend(ids[0], &pending, "tui_v2", "", "")
        .await
        .unwrap();
    assert_eq!(applied.revision, pending.revision + 1);
    assert!(
        store
            .update_tui_backend(ids[0], &pending, "native293", "", "")
            .await
            .is_err()
    );
    assert_eq!(store.tui_backend(ids[0]).await.unwrap().active, "tui_v2");
    let other = store.tui_backend(ids[1]).await.unwrap();
    assert_eq!(
        (other.active.as_str(), other.target.as_str(), other.revision),
        ("native293", "", 0)
    );
    sqlx::query("UPDATE accounts SET status='active' WHERE id=$1")
        .bind(ids[1])
        .execute(&reopened)
        .await
        .unwrap();
    let other_applied = store
        .update_tui_backend(ids[1], &other, "tui_v2", "", "other-binding")
        .await
        .unwrap();
    sqlx::query("UPDATE accounts SET status='disabled' WHERE id=$1")
        .bind(ids[0])
        .execute(&reopened)
        .await
        .unwrap();
    assert_eq!(
        store
            .update_tui_backend(ids[0], &applied, "native293", "", "")
            .await
            .unwrap()
            .active,
        "native293"
    );
    let independent = store.tui_backend(ids[1]).await.unwrap();
    assert_eq!(independent.active, "tui_v2");
    assert_eq!(independent.binding, other_applied.binding);
    assert_eq!(independent.revision, other_applied.revision);
    for id in ids {
        sqlx::query("DELETE FROM accounts WHERE id=$1")
            .bind(id)
            .execute(&reopened)
            .await
            .unwrap();
    }
    reopened.close().await;
}

/// 验证 SQLite 候选切换事务。@return 用例成功时无返回值。
#[tokio::test]
async fn sqlite_tui_switch_transactions() {
    let path = env::temp_dir().join(format!("flower-tui-switch-{}.db", Uuid::new_v4()));
    verify_switch_transactions("sqlite", path.to_str().unwrap()).await;
    fs::remove_file(path).unwrap();
}

/// 验证显式隔离 PostgreSQL 数据库中的同一事务。@return 用例成功时无返回值。
#[tokio::test]
#[ignore = "需要 FLOWER_TUI_SWITCH_TEST_PG_DSN 指向独立临时库"]
async fn postgres_tui_switch_transactions() {
    let dsn = env::var("FLOWER_TUI_SWITCH_TEST_PG_DSN").expect("须指定一次性 PostgreSQL 测试库");
    verify_switch_transactions("postgres", &dsn).await;
}
