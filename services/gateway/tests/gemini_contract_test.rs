//! Gemini入口认证、源帧聚合与认证恢复判定的合成回归。
use axum::http::{HeaderMap, HeaderValue};
use claude_code_gateway::service::agy_contract::AgySystemPromptPolicy;
use claude_code_gateway::service::gemini::{aggregate, api_key, verified_auth_failure};
use serde_json::json;

/// 回执必须证明冻结开关、已知规则、实际来源及替换计数一致。@return 无。
#[test]
fn system_prompt_receipt_is_bound_to_frozen_policy() {
    let policy = AgySystemPromptPolicy::new(true);
    let report = json!({"schema_version":1,"enabled":true,"rule_version":"new-api-homoglyph-v1",
        "source":"cortex_custom_system","rule_sha256":"a".repeat(64),
        "changed":true,"replaced_codepoints":3,"system_codepoints":10});
    assert!(policy.matches_report(&report));
    assert!(!AgySystemPromptPolicy::new(false).matches_report(&report));
    for (field, value) in [
        ("enabled", json!(false)),
        ("rule_version", json!("unknown")),
        ("source", json!("unverified")),
        ("changed", json!(false)),
        ("system_codepoints", json!(2)),
        ("rule_sha256", json!("invalid")),
    ] {
        let mut changed = report.clone();
        changed[field] = value;
        assert!(!policy.matches_report(&changed));
    }
    assert!(
        serde_json::from_value::<AgySystemPromptPolicy>(
            json!({"schema_version":1,"enabled":"false","rule_version":"new-api-homoglyph-v1"})
        )
        .is_err()
    );
}

/// 位置试验独立冻结，并要求原生回执确认实际用户段来源。
#[test]
fn system_prompt_reminder_requires_a_receipt_even_without_homoglyphs() {
    let mut policy = AgySystemPromptPolicy::new(false);
    assert!(policy.is_disabled());
    assert!(
        serde_json::to_value(&policy)
            .unwrap()
            .get("user_reminder_index")
            .is_none()
    );
    policy.user_reminder_index = Some(0);
    assert!(!policy.is_disabled());
    assert_eq!(
        serde_json::to_value(&policy).unwrap()["user_reminder_index"],
        0
    );
    let mut report = json!({"schema_version":1,"enabled":false,"rule_version":"new-api-homoglyph-v1",
        "source":"cortex_custom_system","rule_sha256":"a".repeat(64),
        "changed":false,"replaced_codepoints":0,"system_codepoints":10});
    assert!(!policy.matches_report(&report));
    report["source"] = json!("cortex_user_reminder");
    assert!(policy.matches_report(&report));
}

/// 四种令牌来源兼容，冲突和重复查询密钥受控拒绝。@return 无。
#[test]
fn token_sources_cannot_override_each_other() {
    let mut headers = HeaderMap::new();
    headers.insert("x-goog-api-key", HeaderValue::from_static("synthetic-key"));
    assert_eq!(
        api_key(&headers, Some("alt=sse&key=synthetic-key")).unwrap(),
        "synthetic-key"
    );
    headers.insert(
        "authorization",
        HeaderValue::from_static("Bearer synthetic-key"),
    );
    assert!(api_key(&headers, None).is_ok());
    assert!(api_key(&headers, Some("key=other")).is_err());
    assert!(api_key(&headers, Some("key=synthetic-key&key=synthetic-key")).is_err());
    assert!(api_key(&HeaderMap::new(), None).is_err());
}

/// 非流式保留思考签名、函数ID、未知字段及原生终态用量。@return 无。
#[test]
fn aggregation_preserves_source_parts_and_final_usage() {
    let mut output = json!(null);
    aggregate(&mut output,json!({"responseId":"synthetic","candidates":[{"index":0,"content":{"role":"model","parts":[{"text":"思考","thought":true,"thoughtSignature":"synthetic-signature"}]}}]})).unwrap();
    aggregate(&mut output,json!({"candidates":[{"index":0,"content":{"parts":[{"functionCall":{"id":"call-1","name":"tool","args":{"x":1}},"extension":"preserved"}]},"finishReason":"STOP"}],"usageMetadata":{"totalTokenCount":8},"sourceExtension":{"a":1}})).unwrap();
    assert_eq!(
        output["candidates"][0]["content"]["parts"][0]["thoughtSignature"],
        "synthetic-signature"
    );
    assert_eq!(
        output["candidates"][0]["content"]["parts"][1]["functionCall"]["id"],
        "call-1"
    );
    assert_eq!(output["candidates"][0]["finishReason"], "STOP");
    assert_eq!(output["usageMetadata"]["totalTokenCount"], 8);
    assert_eq!(output["sourceExtension"]["a"], 1);
}

/// 仅完整的源401认证错误可进入额外恢复判定。@return 无。
#[test]
fn capacity_and_control_errors_are_not_authentication_evidence() {
    assert!(verified_auth_failure(
        &json!({"error":{"code":401,"status":"UNAUTHENTICATED"}})
    ));
    for frame in [
        json!({"error":{"code":429,"status":"RESOURCE_EXHAUSTED"}}),
        json!({"error":{"code":401}}),
        json!({"code":"native_request_failed"}),
        json!({"error":{"code":401,"status":"UNAUTHENTICATED"},"candidates":[]}),
    ] {
        assert!(!verified_auth_failure(&frame));
    }
}
