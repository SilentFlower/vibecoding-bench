//! 隔离进程中的真实维护门禁与预热协调循环，全部账号和 HTTP 响应均为合成数据。

use std::env::{current_exe, set_var, temp_dir, var_os};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::time::Duration;

use axum::Json;
use axum::Router;
use axum::http::StatusCode;
use axum::routing::get;
use axum::serve;
use serde_json::{Value, from_value, json};
use sqlx::any::{AnyPoolOptions, install_default_drivers};
use tokio::net::TcpListener;
use tokio::process::Command;
use tokio::spawn;
use tokio::task::yield_now;
use tokio::time::{Instant, sleep, timeout};
use uuid::Uuid;

use super::NativePrewarmer;
use crate::model::account::Account;
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
    let prewarmer = NativePrewarmer::new(accounts.clone());
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
    let fault = failing.clone();
    let router = Router::new().route(
        "/internal/v3/transport/:id",
        get(move || {
            let observed = observed.clone();
            let fault = fault.clone();
            async move {
                observed.fetch_add(1, Ordering::SeqCst);
                (
                    if fault.load(Ordering::SeqCst) {
                        StatusCode::SERVICE_UNAVAILABLE
                    } else {
                        StatusCode::OK
                    },
                    Json(Value::Null),
                )
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
    let prewarmer = NativePrewarmer::new(accounts.clone());
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
    let prewarmer = NativePrewarmer::new(accounts.clone());
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
    drop(prewarmer);
    server.abort();
    pool.close().await;
}
