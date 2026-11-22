//! 真实SQLite和Axum下的AGY平台、权限及AT-only快照回归。
use axum::{
    Router,
    body::Body,
    http::{Request, StatusCode},
    routing::get,
};
use chrono::Utc;
use serde_json::{Value, json};
use sqlx::AnyPool;
use std::sync::Arc;
use tower::ServiceExt;

use claude_code_gateway::handler::router::AppState;
use claude_code_gateway::service::account::AccountService;
use claude_code_gateway::service::gateway::GatewayService;
use claude_code_gateway::service::gemini::{self, GeminiService};
use claude_code_gateway::service::oauth::TokenTester;
use claude_code_gateway::service::oauth_flow::OAuthFlowService;
use claude_code_gateway::service::proxy::ProxyService;
use claude_code_gateway::service::rewriter::Rewriter;
use claude_code_gateway::service::telemetry::TelemetryService;
use claude_code_gateway::store::{
    account_store::AccountStore, db, memory::MemoryStore, prime_log_store::PrimeLogStore,
    settings_store::SettingsStore, token_store::TokenStore, usage_store::UsageStore,
};

/// 建立独立合成库，权限测试使用真实存储。@return 服务状态、连接与路径。
async fn fixture() -> (AppState, AnyPool, std::path::PathBuf) {
    sqlx::any::install_default_drivers();
    let path = std::env::temp_dir().join(format!("agy-gemini-{}.sqlite", uuid::Uuid::new_v4()));
    let pool = AnyPool::connect(&format!("sqlite:{}?mode=rwc", path.display()))
        .await
        .unwrap();
    db::migrate(&pool, "sqlite").await.unwrap();
    let store = Arc::new(AccountStore::new(pool.clone(), "sqlite".into()));
    let cache = Arc::new(MemoryStore::new());
    let settings = Arc::new(SettingsStore::new(pool.clone()));
    let accounts = Arc::new(AccountService::new(
        store.clone(),
        cache.clone(),
        settings.clone(),
    ));
    let telemetry = Arc::new(TelemetryService::new(store, accounts.clone()));
    let gateway = Arc::new(GatewayService::new(
        accounts.clone(),
        Arc::new(Rewriter::new()),
        telemetry.clone(),
        settings.clone(),
        cache,
        Arc::new(UsageStore::new(pool.clone())),
    ));
    let state = AppState {
        gemini_svc: Arc::new(GeminiService::new(pool.clone())),
        gateway_svc: gateway,
        account_svc: accounts,
        token_tester: Arc::new(TokenTester::new()),
        token_store: Arc::new(TokenStore::new(pool.clone(), "sqlite".into())),
        settings_store: settings,
        prime_log_store: Arc::new(PrimeLogStore::new(pool.clone())),
        oauth_flow_svc: Arc::new(OAuthFlowService::new()),
        telemetry_svc: telemetry,
        proxy_svc: Arc::new(ProxyService::new(pool.clone())),
        admin_password: "synthetic-admin".into(),
    };
    for (id, platform, model) in [
        (1, "antigravity", "gemini-synthetic"),
        (2, "antigravity", "claude-synthetic"),
        (3, "claude_code", "gemini-cc-only"),
    ] {
        sqlx::query("INSERT INTO accounts(id,name,email,platform,token,device_id,auth_type,access_token,refresh_token,oauth_expires_at,usage_data) VALUES($1,'synthetic',$2,$3,'','', 'oauth','synthetic-at','synthetic-rt',$4,$5)")
            .bind(id as i64).bind(format!("synthetic-{id}@example.test")).bind(platform).bind("2099-01-01T00:00:00Z")
            .bind(json!({"capabilities":{"model_mappings":{model:"MODEL_PLACEHOLDER_M36"}}}).to_string()).execute(&pool).await.unwrap();
    }
    sqlx::query("INSERT INTO account_credential_states(account_id,generation,phase,updated_at_ms) VALUES(1,1,'ready',1),(2,1,'ready',1)").execute(&pool).await.unwrap();
    sqlx::query("INSERT INTO api_tokens(name,token,allowed_accounts,blocked_accounts,status) VALUES('synthetic','synthetic-key','1,2','2','active')").execute(&pool).await.unwrap();
    (state, pool, path)
}

/// Gemini目录沿平台和白黑名单，禁用令牌以及冲突key被拒绝。@return 无。
#[tokio::test]
async fn public_models_use_real_token_and_platform_permissions() {
    let (state, pool, path) = fixture().await;
    let router = Router::new()
        .route("/v1beta/models", get(gemini::models))
        .with_state(state);
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/v1beta/models?key=synthetic-key")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let body: Value = serde_json::from_slice(
        &axum::body::to_bytes(response.into_body(), 1024 * 1024)
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(body["models"].as_array().unwrap().len(), 1);
    assert_eq!(body["models"][0]["name"], "models/gemini-synthetic");
    for query in ["", "?key=synthetic-key&key=other"] {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri(format!("/v1beta/models{query}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }
    sqlx::query("UPDATE api_tokens SET status='disabled'")
        .execute(&pool)
        .await
        .unwrap();
    let response = router
        .oneshot(
            Request::builder()
                .uri("/v1beta/models?key=synthetic-key")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    pool.close().await;
    std::fs::remove_file(path).unwrap();
}

/// 同锁读取的业务快照排除RT，pending代次阻止发布。@return 无。
#[tokio::test]
async fn access_snapshot_is_generation_bound_and_pending_blocks_publication() {
    let (state, pool, path) = fixture().await;
    let snapshot = state
        .account_svc
        .resolve_agy_access(1, false)
        .await
        .unwrap();
    let value = serde_json::to_value(snapshot).unwrap();
    assert_eq!(value["account_id"], 1);
    assert_eq!(value["credential_generation"], 1);
    assert!(value.get("refresh_token").is_none());
    sqlx::query("UPDATE account_credential_states SET generation=2,phase='reconcile',updated_at_ms=$1 WHERE account_id=1")
        .bind(Utc::now().timestamp_millis()).execute(&pool).await.unwrap();
    assert!(
        state
            .account_svc
            .resolve_agy_access(1, false)
            .await
            .is_err()
    );
    pool.close().await;
    std::fs::remove_file(path).unwrap();
}
