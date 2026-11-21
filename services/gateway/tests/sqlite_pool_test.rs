//! Gateway SQLite 连接池与真实存储级联回归。
use claude_code_gateway::store::account_store::AccountStore;
use claude_code_gateway::store::db;
use claude_code_gateway::store::proxy_store::ProxyStore;
use sqlx::AnyPool;
use std::env::temp_dir;
use std::fs::remove_dir_all;
use uuid::Uuid;

async fn assert_child_owners(pool: &AnyPool, accounts: &[i64], proxies: &[&str]) {
    for table in [
        "account_credential_states",
        "gateway_session_bindings",
        "gateway_account_send_state",
        "oauth_account_ownerships",
        "oauth_credential_imports",
        "oauth_handoff_operations",
        "usage_records",
    ] {
        let query = format!("SELECT account_id FROM {table} ORDER BY account_id");
        let owners = sqlx::query_scalar::<_, i64>(&query)
            .fetch_all(pool)
            .await
            .unwrap();
        assert_eq!(owners, accounts, "{table}");
    }
    let owners =
        sqlx::query_scalar::<_, String>("SELECT proxy_id FROM proxy_route_sync ORDER BY proxy_id")
            .fetch_all(pool)
            .await
            .unwrap();
    assert_eq!(owners, proxies);
}

#[tokio::test]
async fn sqlite_pool_enforces_foreign_keys_during_concurrent_deletes() {
    sqlx::any::install_default_drivers();
    let root = temp_dir().join(format!("gateway-sqlite-pool-{}", Uuid::new_v4()));
    let file = root.join("gateway.sqlite");
    let pool = db::init_db("sqlite", file.to_str().unwrap()).await.unwrap();
    db::migrate(&pool, "sqlite").await.unwrap();
    sqlx::raw_sql(
        "INSERT INTO accounts(id,email,token,device_id) VALUES
            (1,'one@example.test','one','one'),(2,'two@example.test','two','two');
        INSERT INTO account_credential_states(account_id,updated_at_ms) VALUES(1,1),(2,1);
        INSERT INTO gateway_session_bindings VALUES('one',1,'1',1,1,1),('two',2,'1',1,1,1);
        INSERT INTO gateway_account_send_state VALUES(1,1),(2,1);
        INSERT INTO oauth_account_ownerships VALUES(1,'{}'),(2,'{}');
        INSERT INTO oauth_credential_imports VALUES('one',1,'hash','now'),('two',2,'hash','now');
        INSERT INTO oauth_handoff_operations VALUES('one',1,'{}'),('two',2,'{}');
        INSERT INTO usage_records(record_id,account_id,started_at,finished_at,model,input_tokens,output_tokens,
            cache_read_tokens,cache_write_tokens,cache_write_5m_tokens,cache_write_1h_tokens,partial,price_version)
            VALUES('one',1,'now','now','test',0,0,0,0,0,0,0,'1'),('two',2,'now','now','test',0,0,0,0,0,0,0,'1');
        INSERT INTO proxy_routes(id,name,connection,public_url,revision,created_at,updated_at) VALUES
            ('one','one','http://127.0.0.1:10001','http://127.0.0.1:10001','1','now','now'),
            ('two','two','http://127.0.0.1:10002','http://127.0.0.1:10002','1','now','now');
        INSERT INTO proxy_route_sync VALUES('one','one','{}','{}','[]','now'),('two','two','{}','{}','[]','now');",
    )
    .execute(&pool)
    .await
    .unwrap();
    assert_child_owners(&pool, &[1, 2], &["one", "two"]).await;

    let mut held = Vec::new();
    for _ in 0..pool.options().get_max_connections() {
        let mut connection = pool.acquire().await.unwrap();
        let foreign_keys: i64 = sqlx::query_scalar("PRAGMA foreign_keys")
            .fetch_one(&mut *connection)
            .await
            .unwrap();
        assert_eq!(foreign_keys, 1);
        held.push(connection);
    }
    held.pop().unwrap().close().await.unwrap();
    let mut replacement = pool.acquire().await.unwrap();
    let foreign_keys: i64 = sqlx::query_scalar("PRAGMA foreign_keys")
        .fetch_one(&mut *replacement)
        .await
        .unwrap();
    assert_eq!(foreign_keys, 1);
    let journal_mode: String = sqlx::query_scalar("PRAGMA journal_mode")
        .fetch_one(&mut *replacement)
        .await
        .unwrap();
    assert_eq!(journal_mode, "wal");

    // 保持其余租约占用，使两个删除从有限的可用连接取连接。
    drop(replacement);
    drop(held.pop().unwrap());
    let accounts = AccountStore::new(pool.clone(), "sqlite".into());
    let proxies = ProxyStore::new(pool.clone());
    let (account_result, proxy_result) =
        tokio::join!(accounts.delete(1), proxies.delete("one", "1"));
    account_result.unwrap();
    proxy_result.unwrap();
    assert_child_owners(&pool, &[2], &["two"]).await;
    drop(held);
    pool.close().await;
    remove_dir_all(root).unwrap();
}
