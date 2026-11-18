//! Gemini入口认证、源帧聚合与认证恢复判定的合成回归。
use axum::http::{HeaderMap, HeaderValue};
use claude_code_gateway::service::gemini::{aggregate, api_key, verified_auth_failure};
use serde_json::json;

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
