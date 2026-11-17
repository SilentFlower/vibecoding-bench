/// 隔离sender夹具驱动真实网关，核对分类、身份、绑定与资源生命周期。
mod rate_limit_tests {
    use super::{create_setup_gateway_account, test_gateway_service_with_scheduling};
    use crate::model::account::AccountAuthType;
    use crate::model::api_token::{ApiToken, ApiTokenStatus};
    use crate::store::memory::MemoryStore;
    use axum::body::{self, Body};
    use axum::extract::Request;
    use axum::http::StatusCode;
    use chrono::{Duration as ChronoDuration, Utc};
    use reqwest::Client;
    use serde_json::{Value, json};
    use std::collections::HashMap;
    use std::sync::Arc;
    use std::time::{Duration, Instant};
    use tokio::spawn;
    use tokio::time::{sleep, timeout};
    use uuid::Uuid;

    /// 以两个原生账号覆盖明确429、业务透传及原请求截止。
    /// @return 无；实际提交、诊断、身份、槽位或会话绑定错误时失败。
    #[tokio::test]
    #[ignore = "由 tests/native_rate_limit_fixture.py 提供独立回环sender"]
    async fn native_rate_limit_gateway_roundtrip() {
        assert_eq!(std::env::var("FLOWER_RATE_LIMIT_FIXTURE").unwrap(), "1");
        let client = Client::builder().no_proxy().build().unwrap();
        let observations = format!("{}/observations", std::env::var("V3_RUNTIME_URL").unwrap());
        for version in ["2.1.280", "2.1.293"] {
            let mut cases = vec![
                ("capacity", 200, 2),
                ("fable", 200, 2),
                ("business", 429, 1),
                ("exhausted", 429, 2),
                ("restricted", 429, 1),
                ("fablequota", 200, 1),
                ("signature-capacity", 200, 4),
                ("unknown", 502, 1),
                ("deadline", 429, 1),
                ("cancel", 429, 1),
            ];
            if version == "2.1.293" {
                cases.push(("transient", 200, 2));
            }
            for (scenario, expected_status, expected_attempts) in cases {
                let (service, store) = test_gateway_service_with_scheduling(
                    Arc::new(MemoryStore::new()),
                    "https://api.anthropic.com".into(),
                    "http://127.0.0.1:1".into(),
                    true,
                )
                .await;
                let service = Arc::new(service);
                let session = Uuid::new_v4().to_string();
                let label = format!("{scenario}-{version}-{session}");
                let mut primary = create_setup_gateway_account(
                    &service,
                    "rate-primary@example.invalid",
                    &format!("synthetic-primary-{label}"),
                    10,
                )
                .await;
                let mut backup = create_setup_gateway_account(
                    &service,
                    "rate-backup@example.invalid",
                    &format!("synthetic-backup-{label}"),
                    20,
                )
                .await;
                let primary_id = primary.id;
                for account in [&mut primary, &mut backup] {
                    account.request_backend = "native293".into();
                    if scenario.starts_with("fable") {
                        account.auth_type = AccountAuthType::Oauth;
                        account.access_token = account.setup_token.clone();
                        account.setup_token.clear();
                        account.refresh_token = format!("synthetic-refresh-{}-{label}", account.id);
                        account.expires_at = Some(Utc::now() + ChronoDuration::hours(1));
                    }
                    if scenario == "fablequota" && account.id == primary_id {
                        account.usage_data = json!({"seven_day_fable":{"utilization":60,
                            "resets_at":(Utc::now()+ChronoDuration::days(1)).to_rfc3339()}});
                    }
                    store.update(account).await.unwrap();
                    if scenario == "fablequota" {
                        store
                            .update_usage(account.id, &account.usage_data.to_string())
                            .await
                            .unwrap();
                    }
                }
                if scenario == "deadline" {
                    service
                        .settings_store
                        .upsert_many(&HashMap::from([(
                            "v3_admission_wait_seconds".into(),
                            "1".into(),
                        )]))
                        .await
                        .unwrap();
                    service
                        .account_svc
                        .scheduler()
                        .unwrap()
                        .reload(&service.settings_store)
                        .await
                        .unwrap();
                }
                let token = ApiToken {
                    id: 123,
                    name: "合成账号范围".into(),
                    token: "synthetic-token".into(),
                    allowed_accounts: if scenario == "restricted" {
                        primary.id.to_string()
                    } else {
                        String::new()
                    },
                    blocked_accounts: String::new(),
                    status: ApiTokenStatus::Active,
                    created_at: Utc::now(),
                    updated_at: Utc::now(),
                };
                let mut payload = json!({"model":if scenario.starts_with("fable") {"claude-fable-5-1"} else {"claude-sonnet-4-6"},
                    "max_tokens":128,"stream":false,"metadata":{"user_id":json!({"session_id":session}).to_string()},
                    "messages":[{"role":"user","content":label}]});
                if scenario == "signature-capacity" {
                    payload["messages"].as_array_mut().unwrap().push(json!({"role":"assistant",
                        "content":[{"type":"thinking","thinking":"合成历史","signature":"synthetic-invalid"},{"type":"text","text":"合成回答"}]}));
                    payload["messages"]
                        .as_array_mut()
                        .unwrap()
                        .push(json!({"role":"user","content":"继续"}));
                }
                let make_request = || {
                    Request::builder()
                        .method("POST")
                        .uri("/v1/messages")
                        .header(
                            "user-agent",
                            format!("claude-cli/{version} (external, cli)"),
                        )
                        .header("content-type", "application/json")
                        .body(Body::from(payload.to_string()))
                        .unwrap()
                };
                let started = Instant::now();
                let response = if matches!(scenario, "transient" | "cancel") {
                    let running = service.clone();
                    let request = make_request();
                    let sending_token = token.clone();
                    let pending = spawn(async move {
                        running.handle_request(request, Some(&sending_token)).await
                    });
                    timeout(Duration::from_secs(3), async {
                        loop {
                            let capacity = service
                                .account_svc
                                .get_account_capacity_info(&primary)
                                .await;
                            if capacity.transient_backoff_waiting > 0 {
                                assert_eq!(capacity.current_concurrency_units, 0);
                                break;
                            }
                            sleep(Duration::from_millis(10)).await;
                        }
                    })
                    .await
                    .unwrap();
                    if scenario == "cancel" {
                        pending.abort();
                        assert!(pending.await.unwrap_err().is_cancelled());
                        let capacity = service
                            .account_svc
                            .get_account_capacity_info(&primary)
                            .await;
                        assert_eq!(capacity.current_concurrency_units, 0);
                        assert_eq!(capacity.transient_backoff_waiting, 0);
                        let all: Vec<Value> = client
                            .get(&observations)
                            .send()
                            .await
                            .unwrap()
                            .json()
                            .await
                            .unwrap();
                        assert_eq!(
                            all.iter().filter(|record| record["label"] == label).count(),
                            1
                        );
                        continue;
                    }
                    timeout(Duration::from_secs(15), pending)
                        .await
                        .unwrap()
                        .unwrap()
                } else {
                    service.handle_request(make_request(), Some(&token)).await
                };
                assert_eq!(response.status().as_u16(), expected_status, "{label}");
                let request_id = response.headers()["x-cc2api-request-id"]
                    .to_str()
                    .unwrap()
                    .to_string();
                if scenario == "transient" {
                    assert!(started.elapsed() >= Duration::from_secs(10));
                }
                if scenario == "deadline" {
                    assert!(started.elapsed() < Duration::from_secs(3));
                }
                let response_body = body::to_bytes(response.into_body(), 8192).await.unwrap();
                if scenario == "business" {
                    let value: Value = serde_json::from_slice(&response_body).unwrap();
                    assert_eq!(
                        value["error"]["message"],
                        "long context requires usage credits"
                    );
                }
                let all: Vec<Value> = client
                    .get(&observations)
                    .send()
                    .await
                    .unwrap()
                    .json()
                    .await
                    .unwrap();
                let sent: Vec<_> = all
                    .iter()
                    .filter(|record| record["label"] == label)
                    .collect();
                assert_eq!(sent.len(), expected_attempts, "{label}");
                let expected_accounts = match scenario {
                    "capacity" | "fable" | "exhausted" => vec![primary.id, backup.id],
                    "fablequota" => vec![backup.id],
                    "signature-capacity" => vec![primary.id, primary.id, backup.id, backup.id],
                    "transient" => vec![primary.id, primary.id],
                    _ => vec![primary.id],
                };
                for (record, account_id) in sent.iter().zip(expected_accounts) {
                    assert_eq!(record["account_id"], account_id, "{label}");
                    assert_eq!(record["version"], version, "{label}");
                    assert_eq!(record["body"]["model"], payload["model"]);
                    assert_eq!(record["body"]["messages"][0], payload["messages"][0]);
                    let expected = if account_id == primary.id {
                        &primary
                    } else {
                        &backup
                    };
                    assert_eq!(record["device_id"], expected.device_id);
                }
                for account in [&primary, &backup] {
                    assert_eq!(
                        service
                            .account_svc
                            .get_account_capacity_info(account)
                            .await
                            .current_concurrency_units,
                        0,
                        "{label}"
                    );
                }
                let current = service.account_svc.get_account(primary.id).await.unwrap();
                assert_eq!(
                    current.rate_limit_reset_at.is_some(),
                    matches!(
                        scenario,
                        "capacity" | "exhausted" | "restricted" | "signature-capacity"
                    ),
                    "{label}"
                );
                let diagnostics = service.diagnostics_store().unwrap();
                diagnostics.flush().await.unwrap();
                let detail = diagnostics.detail(&request_id).await.unwrap();
                let observed_attempts = if scenario == "unknown" {
                    0
                } else {
                    expected_attempts
                };
                assert_eq!(
                    detail.request.attempt_count as usize, observed_attempts,
                    "{label}"
                );
                if matches!(scenario, "capacity" | "fable") {
                    assert_eq!(detail.attempts[0].status_code, Some(429));
                    assert_eq!(
                        detail.attempts[1].retry_reason.as_deref(),
                        Some("account_rate_limit")
                    );
                    // 再次使用同一会话，通过真实发送账号验证绑定已迁移到替代账号。
                    let next = service.handle_request(make_request(), Some(&token)).await;
                    assert_eq!(next.status(), StatusCode::OK);
                    body::to_bytes(next.into_body(), 8192).await.unwrap();
                    let all: Vec<Value> = client
                        .get(&observations)
                        .send()
                        .await
                        .unwrap()
                        .json()
                        .await
                        .unwrap();
                    assert_eq!(all.last().unwrap()["account_id"], backup.id);
                }
            }
        }
    }
}
