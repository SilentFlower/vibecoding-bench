//! 真实账号发送器路由的AGY权限与代次拒绝验证，模型提交为零。
use std::fs;
use std::path::PathBuf;

use axum::body::Body;
use axum::http::{Request, StatusCode};
use claude_code_gateway::service::agy_contract::{
    AGY_SOURCE_SHA256, AgyAccessSnapshot, AgySubmission,
};
use claude_code_gateway::service::runtime_transport::sender_router;
use serde_json::{Value, json};
use tower::ServiceExt;
use uuid::Uuid;

/// 创建单账号配置和受信提交。@return 配置路径、独立工作根与原请求。
fn fixture() -> (PathBuf, PathBuf, Value) {
    let root = std::env::temp_dir().join(format!("agy-sender-{}", Uuid::new_v4()));
    fs::create_dir(&root).unwrap();
    let work = root.join("native");
    let path = root.join("sender.json");
    let binding = json!({"account_id":17,"environment_id":"synthetic-env","generation":2,
        "endpoint":"http://localhost:8091","secret":"synthetic-service-secret-at-least-32-bytes","release_id":"synthetic"});
    fs::write(&path, serde_json::to_vec(&json!({"binding":binding,"proxy_url":"", "allowed_origin":"https://cloudcode-pa.googleapis.com",
        "agy":{"protocol_version":1,"source_sha256":AGY_SOURCE_SHA256,"module_root":"/synthetic/agy/modules",
        "binary_path":"/synthetic/agy/binary","work_root":work,"max_workers":1,"memory_mib":0}})).unwrap()).unwrap();
    let request = json!({"request":{"account_id":17,"environment_id":"synthetic-env","generation":2,
        "request_id":Uuid::new_v4().to_string(),"deadline_unix_ms":chrono::Utc::now().timestamp_millis()+60000,
        "method":"POST","target_url":"https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent",
        "headers":[],"preserve_header_casing":false},"api_token_id":4,
        "credential_snapshot":{"account_id":17,"credential_generation":3,"access_token":"synthetic-at",
        "expires_at":4070908800000_i64,"email":"synthetic@example.test"},
        "model":"gemini-synthetic","native_model":"MODEL_PLACEHOLDER_M36","body":{"contents":[{"parts":[{"text":"合成问题"}]}]}});
    (path, root, request)
}

/// 校验受信证明和环境代次，拒绝路径不创建原生工作目录。@return 无。
#[tokio::test]
async fn authentication_binding_and_snapshot_fail_before_native_preparation() {
    let (path, root, original) = fixture();
    let router = sender_router(path.to_string_lossy().into_owned());
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/internal/agy/prepare")
                .header("content-type", "application/json")
                .body(Body::from(original.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    for changes in ["environment", "generation", "snapshot", "model"] {
        let mut request = original.clone();
        match changes {
            "environment" => request["request"]["environment_id"] = json!("wrong-env"),
            "generation" => request["request"]["generation"] = json!(1),
            "snapshot" => request["credential_snapshot"]["account_id"] = json!(18),
            "model" => request["native_model"] = json!("guessed-model"),
            _ => unreachable!(),
        }
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/internal/agy/prepare")
                    .header(
                        "authorization",
                        "Bearer synthetic-service-secret-at-least-32-bytes",
                    )
                    .header("content-type", "application/json")
                    .body(Body::from(request.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST, "{changes}");
    }
    assert!(!root.join("native").exists());
    fs::remove_dir_all(root).unwrap();
}

/// 容量应用只接收服务鉴权和磁盘当前配置。@return 无。
#[tokio::test]
async fn capacity_requires_authenticated_current_layout() {
    let (path, root, _) = fixture();
    let router = sender_router(path.to_string_lossy().into_owned());
    for (secret, generation, max_workers, status) in [
        ("missing", 2, 1, StatusCode::UNAUTHORIZED),
        (
            "synthetic-service-secret-at-least-32-bytes",
            1,
            1,
            StatusCode::BAD_REQUEST,
        ),
        (
            "synthetic-service-secret-at-least-32-bytes",
            2,
            2,
            StatusCode::BAD_REQUEST,
        ),
    ] {
        let input = json!({"account_id":17,"environment_id":"synthetic-env","generation":generation,
            "max_workers":max_workers});
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/internal/agy/capacity")
                    .header("authorization", format!("Bearer {secret}"))
                    .header("content-type", "application/json")
                    .body(Body::from(input.to_string()))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), status);
    }
    assert!(!root.join("native").exists());
    fs::remove_dir_all(root).unwrap();
}

/// AGY配置拒绝普通透传，避免跨平台绕过原生业务。@return 无。
#[tokio::test]
async fn agy_configuration_cannot_use_legacy_transport() {
    let (path, root, _) = fixture();
    let response = sender_router(path.to_string_lossy().into_owned())
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/internal/send")
                .header(
                    "authorization",
                    "Bearer synthetic-service-secret-at-least-32-bytes",
                )
                .body(Body::from("synthetic-body"))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert!(!root.join("native").exists());
    fs::remove_dir_all(root).unwrap();
}

/// 运行快照的反序列化拒绝RT和无效代次，保护唯一刷新所有者。@return 无。
#[test]
fn runtime_snapshot_never_accepts_refresh_tokens() {
    let (_, root, original) = fixture();
    let mut value = original["credential_snapshot"].clone();
    value["refresh_token"] = json!("synthetic-rt");
    assert!(serde_json::from_value::<AgyAccessSnapshot>(value).is_err());
    let mut snapshot: AgyAccessSnapshot =
        serde_json::from_value(original["credential_snapshot"].clone()).unwrap();
    snapshot.credential_generation = 0;
    assert!(snapshot.validate(1).is_err());
    fs::remove_dir_all(root).unwrap();
}

/// 历史默认信封保持关闭，未知规则在创建原生目录之前拒绝。@return 无。
#[tokio::test]
async fn system_prompt_extension_defaults_off_and_rejects_unknown_rules() {
    let (path, root, original) = fixture();
    let submission: AgySubmission = serde_json::from_value(original.clone()).unwrap();
    assert!(!submission.system_prompt_policy.enabled);
    assert!(
        serde_json::to_value(&submission)
            .unwrap()
            .get("system_prompt_policy")
            .is_none()
    );
    let mut invalid = original;
    invalid["system_prompt_policy"] =
        json!({"schema_version":1,"enabled":true,"rule_version":"unknown"});
    let response = sender_router(path.to_string_lossy().into_owned())
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/internal/agy/prepare")
                .header(
                    "authorization",
                    "Bearer synthetic-service-secret-at-least-32-bytes",
                )
                .header("content-type", "application/json")
                .body(Body::from(invalid.to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert!(!root.join("native").exists());
    fs::remove_dir_all(root).unwrap();
}
