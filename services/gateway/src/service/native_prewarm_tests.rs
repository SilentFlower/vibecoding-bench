//! 隔离进程中的真实维护门禁与预热协调循环，全部账号和 HTTP 响应均为合成数据。

use std::env::{current_exe, set_var, temp_dir, var_os};
use std::fs;
use std::future::pending;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU16, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::Json;
use axum::Router;
use axum::extract::Query;
use axum::http::StatusCode;
use axum::response::IntoResponse;
use axum::routing::{get, post};
use axum::serve;
use chrono::{TimeDelta, Utc};
use serde_json::{Value, from_value, json};
use sqlx::any::{AnyPoolOptions, install_default_drivers};
use std::collections::HashMap;
use tokio::net::TcpListener;
use tokio::process::Command;
use tokio::spawn;
use tokio::task::yield_now;
use tokio::time::{Instant, sleep, timeout};
use uuid::Uuid;

use super::NativePrewarmer;
use sha2::{Digest, Sha256};
use tokio::sync::Notify;

use crate::model::account::{Account, AccountAuthType};
use crate::service::account::AccountService;
use crate::service::system_update;
use crate::store::account_store::AccountStore;
use crate::store::db::migrate;
use crate::store::memory::MemoryStore;
use crate::store::settings_store::SettingsStore;

fn publish_gate(root: &Path, value: &Value) {
    let pending = root.join("admission.pending");
    fs::write(&pending, value.to_string()).unwrap();
    fs::set_permissions(&pending, fs::Permissions::from_mode(0o600)).unwrap();
    // 与生产一样原子发布，避免测试写入一半被正确识别为损坏门禁。
    fs::rename(pending, root.join("admission.json")).unwrap();
}

async fn wait_state(
    prewarmer: &NativePrewarmer,
    id: i64,
    state: &str,
    previous: Option<&Value>,
) -> Value {
    let deadline = Instant::now() + Duration::from_secs(3);
    loop {
        let status = prewarmer.status(id);
        if status["state"] == state && previous.is_none_or(|id| status["preparation_id"] != *id) {
            return status;
        }
        assert!(Instant::now() < deadline, "等待 {state}，实际 {status}");
        sleep(Duration::from_millis(10)).await;
    }
}

/// 用真实账号写入驱动准备协调器，并验证无绑定失败的脱敏归属。@return 无。
#[tokio::test]
async fn agy_account_changes_recheck_prewarm_before_backoff_expires() {
    if var_os("CCGW_AGY_PREWARM_TEST").is_none() {
        let output = timeout(
            Duration::from_secs(20),
            Command::new(current_exe().unwrap())
                .args([
                    "--exact",
                    "service::native_prewarm::tests::agy_account_changes_recheck_prewarm_before_backoff_expires",
                    "--nocapture",
                ])
                .env("CCGW_AGY_PREWARM_TEST", "1")
                .env_remove("V3_UPDATE_GATE_DIR")
                .env("V3_INTERNAL_TOKEN", "synthetic-agy-prewarm-test-token")
                .kill_on_drop(true)
                .output(),
        )
        .await
        .unwrap()
        .unwrap();
        assert!(
            output.status.success(),
            "{}\n{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        return;
    }

    let control_status = Arc::new(AtomicU16::new(404));
    let control_reply = control_status.clone();
    let router = Router::new()
        .route("/internal/v3/agy-environments/:id", post(move || {
            let status = StatusCode::from_u16(control_reply.load(Ordering::SeqCst)).unwrap();
            async move { (status, Json(json!({"environment_id":"synthetic-agy-env","generation":3,"state":"registered"}))) }
        }))
        .route("/internal/v3/agy-auth/prepare", post(|Json(input): Json<Value>| async move {
            Json(json!({"email_address":"agy-prewarm@example.test","document":input["document"],"proxy_url":input["proxy_url"]}))
        }));
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    // 独立测试进程仅在启动控制面及数据库任务前设置回环地址。
    unsafe {
        set_var(
            "V3_RUNTIME_URL",
            format!("http://{}", listener.local_addr().unwrap()),
        )
    };
    let server = spawn(async move { serve(listener, router).await.unwrap() });
    install_default_drivers();
    let pool = AnyPoolOptions::new()
        .max_connections(1)
        .connect("sqlite::memory:")
        .await
        .unwrap();
    migrate(&pool, "sqlite").await.unwrap();
    let store = Arc::new(AccountStore::new(pool.clone(), "sqlite".into()));
    let accounts = Arc::new(AccountService::new(
        store.clone(),
        Arc::new(MemoryStore::new()),
        Arc::new(SettingsStore::new(pool)),
    ));
    let mut account: Account = from_value(json!({"id":0,"name":"反重力测试","email":"agy-prewarm@example.test",
        "platform":"antigravity","auth_type":"oauth","status":"active","access_token":"synthetic-at",
        "refresh_token":"synthetic-rt","device_id":"synthetic-device","canonical_env":{},"canonical_prompt_env":{},
        "canonical_process":{},"billing_mode":"strip","created_at":"2026-11-21T00:00:00Z","updated_at":"2026-11-21T00:00:00Z"})).unwrap();
    let expiry = Utc::now() + TimeDelta::hours(1);
    account.expires_at = Some(expiry);
    store.create(&mut account).await.unwrap();
    let id = account.id;
    let prewarmer = NativePrewarmer::new(accounts.clone(), Default::default());
    // 此处只允许真实变更通知触发即时重检，排除启动补偿与周期巡检。
    prewarmer.start_with_retries([3600, 7200, 10800]);
    let status = wait_state(&prewarmer, id, "failed", None).await;
    assert_eq!(status["scope"], "account");
    assert_eq!(status["reason"], "orchestrator_upgrade_required");
    assert!(status.get("generation").is_none());

    control_status.store(503, Ordering::SeqCst);
    accounts
        .update_agy_fields(id, &json!({"status":"disabled"}))
        .await
        .unwrap();
    let status = wait_state(&prewarmer, id, "failed", Some(&status["preparation_id"])).await;
    assert_eq!(status["reason"], "agy_environment_unavailable");
    control_status.store(200, Ordering::SeqCst);
    accounts
        .update_agy_fields(id, &json!({"status":"active"}))
        .await
        .unwrap();
    wait_state(&prewarmer, id, "registered", None).await;

    let operation = Uuid::new_v4().simple().to_string();
    accounts.begin_agy_reauth(id, &operation).await.unwrap();
    let status = wait_state(&prewarmer, id, "unprepared", None).await;
    assert_eq!(status["scope"], "account");
    assert_eq!(status["reason"], "credentials_not_ready");
    accounts
        .finish_agy_operation(
            id,
            &operation,
            &json!({"email_address":account.email,
        "document":{"token":{"access_token":"new-synthetic-at","expiry":expiry.to_rfc3339()}}}),
        )
        .await
        .unwrap();
    let registered = wait_state(&prewarmer, id, "registered", None).await;
    assert_eq!(registered["environment_id"], "synthetic-agy-env");
    assert!(registered.get("scope").is_none());
    accounts
        .update_agy_fields(id, &json!({"proxy_url":"http://127.0.0.1:12345"}))
        .await
        .unwrap();
    wait_state(
        &prewarmer,
        id,
        "registered",
        Some(&registered["preparation_id"]),
    )
    .await;

    accounts.delete_account(id).await.unwrap();
    timeout(Duration::from_secs(3), async {
        while prewarmer
            .statuses()
            .iter()
            .any(|status| status["account_id"] == id)
        {
            sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .unwrap();
    drop(prewarmer);
    server.abort();
}

#[tokio::test]
async fn maintenance_waits_without_failure_and_reopens_promptly() {
    if var_os("CCGW_PREWARM_GATE_TEST").is_none() {
        let root = temp_dir().join(format!("ccgw-prewarm-gate-{}", Uuid::new_v4()));
        fs::create_dir(&root).unwrap();
        // 环境只传给独立测试进程，完整 cargo test 的其它测试保持各自部署上下文。
        let mut child = Command::new(current_exe().unwrap());
        child
            .args(["--exact", "service::native_prewarm::tests::maintenance_waits_without_failure_and_reopens_promptly", "--nocapture"])
            .env("CCGW_PREWARM_GATE_TEST", &root)
            .env("V3_UPDATE_GATE_DIR", &root)
            .env("V3_DEPLOYMENT_ID", "synthetic-maintenance")
            .env("V3_INTERNAL_TOKEN", "synthetic-internal-token-for-maintenance-test")
            .env_remove("V3_RUNTIME_URL")
            .kill_on_drop(true);
        let result = timeout(Duration::from_secs(60), child.output()).await;
        fs::remove_dir_all(root).unwrap();
        let output = result.unwrap().unwrap();
        assert!(
            output.status.success(),
            "{}\n{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        return;
    }

    let root = PathBuf::from(var_os("CCGW_PREWARM_GATE_TEST").unwrap());
    let mut gate = json!({"schema_version":1,"deployment":"synthetic-maintenance",
        "operation_id":Uuid::new_v4().to_string(),"epoch":Uuid::new_v4().to_string(),
        "phase":"blocked","target_release":"system-ci-1-1","revision":Uuid::new_v4().to_string(),
        "created_at":"2026-11-13T00:00:00Z"});
    publish_gate(&root, &gate);
    assert!(system_update::background_admission().unwrap().is_none());
    assert!(system_update::admission().is_err());
    assert_eq!(system_update::snapshot().unwrap()["active"], 0);

    install_default_drivers();
    let pool = AnyPoolOptions::new()
        .max_connections(1)
        .connect("sqlite::memory:")
        .await
        .unwrap();
    migrate(&pool, "sqlite").await.unwrap();
    let store = Arc::new(AccountStore::new(pool.clone(), "sqlite".into()));
    let accounts = Arc::new(AccountService::new(
        store.clone(),
        Arc::new(MemoryStore::new()),
        Arc::new(SettingsStore::new(pool.clone())),
    ));
    let mut account: Account = from_value(json!({"id":0,"name":"维护测试",
        "email":"maintenance@example.test","status":"active","device_id":"synthetic-device",
        "canonical_env":{},"canonical_prompt_env":{},"canonical_process":{},"billing_mode":"strip",
        "request_backend":"native293","created_at":"2026-11-13T00:00:00Z","updated_at":"2026-11-13T00:00:00Z"})).unwrap();
    store.create(&mut account).await.unwrap();
    let prewarmer = NativePrewarmer::new(accounts.clone(), Default::default());
    prewarmer.start_with_retries([0, 1, 2]);
    let status = wait_state(&prewarmer, account.id, "maintenance", None).await;
    assert_eq!(status["reason"], "system_maintenance");
    assert_eq!(prewarmer.inspect(account.id).await["state"], "maintenance");
    sleep(Duration::from_millis(2300)).await;
    assert_eq!(prewarmer.status(account.id)["state"], "maintenance");
    assert_eq!(system_update::snapshot().unwrap()["active"], 0);

    gate["phase"] = json!("idle");
    gate["operation_id"] = Value::Null;
    gate["target_release"] = Value::Null;
    publish_gate(&root, &gate);
    let opened = Instant::now();
    wait_state(&prewarmer, account.id, "sleeping", None).await;
    assert!(opened.elapsed() < Duration::from_millis(1500));
    let activity = system_update::background_admission().unwrap().unwrap();
    assert_eq!(system_update::snapshot().unwrap()["active"], 1);
    drop(activity);
    assert_eq!(system_update::snapshot().unwrap()["active"], 0);

    gate["phase"] = json!("blocked");
    gate["operation_id"] = json!(Uuid::new_v4().to_string());
    publish_gate(&root, &gate);
    accounts.notify_native_change(account.id, true);
    wait_state(&prewarmer, account.id, "maintenance", None).await;
    publish_gate(&root, &json!({}));
    assert!(system_update::background_admission().is_err());
    assert!(system_update::admission().is_err());
    wait_state(&prewarmer, account.id, "failed", None).await;

    // 真实绑定故障进入退避；恢复门禁本身不会引入周期性 HTTP 重试风暴。
    let calls = Arc::new(AtomicUsize::new(0));
    let failing = Arc::new(AtomicBool::new(true));
    let observed = calls.clone();
    let wake_calls = Arc::new(AtomicUsize::new(0));
    let observed_wakes = wake_calls.clone();
    let fault = failing.clone();
    let router = Router::new().route(
        "/internal/v3/transport/:id",
        get(move |Query(query): Query<HashMap<String, String>>| {
            let observed = observed.clone();
            let observed_wakes = observed_wakes.clone();
            let fault = fault.clone();
            async move {
                observed.fetch_add(1, Ordering::SeqCst);
                if query.get("wake").map(String::as_str) != Some("false") {
                    observed_wakes.fetch_add(1, Ordering::SeqCst);
                    return (
                        StatusCode::SERVICE_UNAVAILABLE,
                        [("x-v3-runtime-reason", "native_sender_budget_missing")],
                        Json(Value::Null),
                    )
                        .into_response();
                }
                (
                    if fault.load(Ordering::SeqCst) {
                        StatusCode::SERVICE_UNAVAILABLE
                    } else {
                        StatusCode::OK
                    },
                    Json(Value::Null),
                )
                    .into_response()
            }
        }),
    );
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let endpoint = format!("http://{}", listener.local_addr().unwrap());
    // 当前独立进程已固定为单测试；此处只切换合成控制面端点。
    unsafe {
        set_var("V3_RUNTIME_URL", endpoint);
    }
    let server = spawn(async move {
        serve(listener, router).await.unwrap();
    });
    gate["phase"] = json!("idle");
    gate["operation_id"] = Value::Null;
    publish_gate(&root, &gate);
    let previous = prewarmer.status(account.id)["preparation_id"].clone();
    accounts.notify_native_change(account.id, true);
    wait_state(&prewarmer, account.id, "failed", Some(&previous)).await;
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    sleep(Duration::from_millis(1200)).await;
    assert_eq!(calls.load(Ordering::SeqCst), 1);

    drop(prewarmer);
    yield_now().await;
    let prewarmer = NativePrewarmer::new(accounts.clone(), Default::default());
    prewarmer.start_with_retries([0, 1, 2]);
    wait_state(&prewarmer, account.id, "failed", None).await;
    assert_eq!(calls.load(Ordering::SeqCst), 2);
    // 控制面首次启动迟到，继续沿原启动补偿恢复，保持原有启动速度。
    failing.store(false, Ordering::SeqCst);
    wait_state(&prewarmer, account.id, "sleeping", None).await;
    assert_eq!(calls.load(Ordering::SeqCst), 3);

    drop(prewarmer);
    yield_now().await;
    failing.store(true, Ordering::SeqCst);
    let prewarmer = NativePrewarmer::new(accounts.clone(), Default::default());
    prewarmer.start_with_retries([0, 1, 2]);
    let failed = wait_state(&prewarmer, account.id, "failed", None).await;
    assert_eq!(calls.load(Ordering::SeqCst), 4);
    gate["phase"] = json!("blocked");
    gate["operation_id"] = json!(Uuid::new_v4().to_string());
    publish_gate(&root, &gate);
    let maintenance = wait_state(&prewarmer, account.id, "maintenance", None).await;
    // 覆盖下一次启动补偿，维护等待保持原真实失败的次数和 40 秒截止。
    sleep(Duration::from_millis(1300)).await;
    assert_eq!(
        prewarmer.status(account.id)["preparation_id"],
        maintenance["preparation_id"]
    );
    gate["phase"] = json!("idle");
    gate["operation_id"] = Value::Null;
    publish_gate(&root, &gate);
    wait_state(&prewarmer, account.id, "failed", None).await;
    sleep(Duration::from_millis(1200)).await;
    assert_eq!(calls.load(Ordering::SeqCst), 4);
    assert_eq!(prewarmer.status(account.id)["reason"], "preparation_failed");
    assert_eq!(
        prewarmer.status(account.id)["preparation_id"],
        failed["preparation_id"]
    );
    // 显式变更仍沿原合同清除冷却，正常恢复保持可用。
    failing.store(false, Ordering::SeqCst);
    accounts.notify_native_change(account.id, true);
    wait_state(&prewarmer, account.id, "sleeping", None).await;
    assert_eq!(calls.load(Ordering::SeqCst), 5);

    gate["phase"] = json!("blocked");
    gate["operation_id"] = json!(Uuid::new_v4().to_string());
    publish_gate(&root, &gate);
    accounts.notify_native_change(account.id, true);
    wait_state(&prewarmer, account.id, "maintenance", None).await;
    gate["phase"] = json!("idle");
    gate["operation_id"] = Value::Null;
    publish_gate(&root, &gate);
    wait_state(&prewarmer, account.id, "sleeping", None).await;
    assert_eq!(calls.load(Ordering::SeqCst), 6);
    assert_eq!(wake_calls.load(Ordering::SeqCst), 0);
    // 明确切换可唤醒；普通 GET、维护等待、失败与重试都通过真实协调循环。
    let queue = accounts
        .get_or_create_queue(account.id, account.concurrency)
        .await;
    let lease = queue.runtime_gate.prepare("synthetic-config").unwrap();
    accounts.request_native_wake(account.id);
    wait_state(&prewarmer, account.id, "maintenance", None).await;
    assert_eq!(wake_calls.load(Ordering::SeqCst), 0);
    queue
        .runtime_gate
        .update(&lease.owner, &lease.generation, "release")
        .unwrap();
    let failed = wait_state(&prewarmer, account.id, "failed", None).await;
    assert_eq!(failed["reason"], "native_sender_budget_missing");
    assert_eq!(wake_calls.load(Ordering::SeqCst), 1);
    assert_eq!(prewarmer.inspect(account.id).await["state"], "sleeping");
    assert_eq!(wake_calls.load(Ordering::SeqCst), 1);
    accounts.request_native_wake(account.id);
    wait_state(
        &prewarmer,
        account.id,
        "failed",
        Some(&failed["preparation_id"]),
    )
    .await;
    assert_eq!(wake_calls.load(Ordering::SeqCst), 2);
    // 人工停止撤销失败后的唤醒重试，后续检查恢复只读绑定。
    accounts.notify_native_change(account.id, true);
    wait_state(&prewarmer, account.id, "sleeping", None).await;
    assert_eq!(wake_calls.load(Ordering::SeqCst), 2);
    account.setup_token = "synthetic-setup-token".into();
    account.request_backend = "legacy".into();
    accounts.update_account(&account).await.unwrap();
    accounts.request_native_wake(account.id);
    wait_state(&prewarmer, account.id, "disabled", None).await;
    assert_eq!(wake_calls.load(Ordering::SeqCst), 2);
    drop(prewarmer);
    server.abort();
    account.auth_type = AccountAuthType::SetupToken;
    account.request_backend = "native293".into();
    // 重新设定合成夹具时避免向刚进入关闭的原协调器发送一次实际唤醒。
    store.update(&account).await.unwrap();

    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!("http://{}", listener.local_addr().unwrap());
    let environment_id = "a".repeat(32);
    let scope = format!(
        "/cluster-transports/v2/{}/{}/{environment_id}/1",
        &format!("{:x}", Sha256::digest(b"synthetic-maintenance"))[..12],
        "b".repeat(32),
    );
    let binding = json!({"account_id":account.id,"environment_id":environment_id,"generation":7,
        "endpoint":format!("{base}{scope}"),"secret":"synthetic-sender-authentication-token",
        "release_id":"system-ci-1-1"});
    let submitted = Arc::new(Mutex::new(None::<Value>));
    let confirmed_cancel = Arc::new(AtomicBool::new(false));
    let submitted_signal = Arc::new(Notify::new());
    let router = Router::new()
        .route(
            "/internal/v3/transport/:id",
            get(move || {
                let binding = binding.clone();
                async move { Json(binding) }
            }),
        )
        .route(
            &format!("{scope}/internal/native/readiness"),
            post(|Json(input): Json<Value>| async move {
                Json(
                    json!({"state":"unprepared","account_id":input["account_id"],
                "environment_id":input["environment_id"],"generation":input["generation"],
                "checked_at_ms":1,"idle_workers":0,"live_workers":0}),
                )
            }),
        )
        .route(
            &format!("{scope}/internal/native/prepare"),
            post({
                let submitted = submitted.clone();
                let signal = submitted_signal.clone();
                move |Json(input): Json<Value>| {
                    let submitted = submitted.clone();
                    let signal = signal.clone();
                    async move {
                        *submitted.lock().unwrap() = Some(input);
                        signal.notify_one();
                        pending::<StatusCode>().await
                    }
                }
            }),
        )
        .route(
            &format!("{scope}/internal/native/prepare/cancel"),
            post({
                let confirmed = confirmed_cancel.clone();
                move |Json(input): Json<Value>| {
                    // 被取消的上一步也可能还未提交准备，发送器允许该确认幂等返回。
                    let mut submitted = submitted.lock().unwrap();
                    if submitted.as_ref().is_some_and(|original| {
                        [
                            "account_id",
                            "environment_id",
                            "generation",
                            "preparation_id",
                        ]
                        .into_iter()
                        .all(|key| input[key] == original[key])
                    }) {
                        submitted.take();
                        confirmed.store(true, Ordering::SeqCst);
                    }
                    async { StatusCode::OK }
                }
            }),
        );
    unsafe {
        set_var("V3_RUNTIME_URL", base);
        set_var("V3_RELEASE", "system-ci-1-1");
        set_var("V3_ACCOUNT_RELEASE", "system-ci-1-1");
    }
    let server = spawn(async move { serve(listener, router).await.unwrap() });
    let prewarmer = NativePrewarmer::new(accounts.clone(), Default::default());
    prewarmer.start_with_retries([3600, 7200, 10800]);
    timeout(Duration::from_secs(10), submitted_signal.notified())
        .await
        .unwrap();
    assert_eq!(system_update::snapshot().unwrap()["active"], 1);
    gate["phase"] = json!("blocked");
    gate["operation_id"] = json!(Uuid::new_v4().to_string());
    gate["epoch"] = json!(Uuid::new_v4().to_string());
    gate["target_release"] = json!("system-ci-1-1");
    publish_gate(&root, &gate);
    system_update::cutover(
        gate["operation_id"].as_str().unwrap(),
        gate["epoch"].as_str().unwrap(),
    )
    .unwrap();
    let status = wait_state(&prewarmer, account.id, "maintenance", None).await;
    assert_eq!(status["reason"], "system_maintenance");
    assert!(confirmed_cancel.load(Ordering::SeqCst));
    assert_eq!(system_update::snapshot().unwrap()["active"], 0);
    drop(prewarmer);
    server.abort();
    pool.close().await;
}
