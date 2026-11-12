//! 原生错误的独立日志边界，仅接纳固定枚举及有界原因链。

use serde::{Deserialize, Serialize};
use serde_json::Value;

const STAGES: &[&str] = &[
    "input",
    "context",
    "construction",
    "dispatch",
    "response_headers",
    "response_body",
    "unknown",
];
const NAMES: &[&str] = &[
    "Error",
    "TypeError",
    "RangeError",
    "SyntaxError",
    "AbortError",
    "TimeoutError",
    "DOMException",
    "AggregateError",
    "BridgeError",
    "unknown",
];
const CODES: &[&str] = &[
    "ECONNREFUSED",
    "ECONNRESET",
    "ECONNABORTED",
    "EPIPE",
    "ETIMEDOUT",
    "ENOTFOUND",
    "EAI_AGAIN",
    "EHOSTUNREACH",
    "ENETUNREACH",
    "ENOENT",
    "EACCES",
    "EPERM",
    "EADDRINUSE",
    "CERT_NOT_YET_VALID",
    "CERT_HAS_EXPIRED",
    "DEPTH_ZERO_SELF_SIGNED_CERT",
    "SELF_SIGNED_CERT_IN_CHAIN",
    "UNABLE_TO_VERIFY_LEAF_SIGNATURE",
    "UNABLE_TO_GET_ISSUER_CERT_LOCALLY",
    "ERR_TLS_CERT_ALTNAME_INVALID",
    "ERR_TLS_CERT_SIGNATURE_ALGORITHM_UNSUPPORTED",
    "ERR_SSL_WRONG_VERSION_NUMBER",
    "ERR_SSL_SSLV3_ALERT_HANDSHAKE_FAILURE",
    "ConnectionRefused",
    "ConnectionClosed",
    "ConnectionReset",
    "SocketClosed",
    "ERR_STREAM_PREMATURE_CLOSE",
    "ABORT_ERR",
    "UND_ERR_CONNECT_TIMEOUT",
    "UND_ERR_SOCKET",
    "request_timeout",
    "runtime_protocol",
    "native_configuration",
    "native_construction",
    "native_identity",
    "unsupported_parameter",
    "context_conflict",
    "unknown",
];

/// 跨进程传来的单层白名单异常类型与错误码。
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct NativeErrorCause {
    name: String,
    code: String,
}

/// 经独立校验后可写普通日志的原生异常摘要。
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct NativeErrorDiagnostics {
    schema_version: u8,
    pub stage: String,
    causes: Vec<NativeErrorCause>,
    chain_truncated: bool,
    cycle_detected: bool,
    inspection_failed: bool,
}

/// 诊断可用性与安全投影，缺口不改变本次业务响应。
pub(crate) struct NativeErrorProjection {
    pub state: &'static str,
    pub details: Option<NativeErrorDiagnostics>,
}

/// 从私有事件重建可公开记录的诊断，拒绝扩展字段与超限载荷。
/// @param payload 已校验请求归属的原生错误事件。
/// @return available、unavailable 或 invalid 以及对应安全摘要。
pub(crate) fn project(payload: &Value) -> NativeErrorProjection {
    let Some(value) = payload.get("diagnostics") else {
        return NativeErrorProjection {
            state: if payload.get("diagnostics_state").is_some() {
                "invalid"
            } else {
                "unavailable"
            },
            details: None,
        };
    };
    // 在反序列化前限制原因链和字段规模，避免复制任意原生错误对象。
    let bounded = value.as_object().is_some_and(|object| object.len() == 6)
        && value.get("schema_version").and_then(Value::as_u64) == Some(1)
        && value
            .get("stage")
            .and_then(Value::as_str)
            .is_some_and(|stage| STAGES.contains(&stage))
        && ["chain_truncated", "cycle_detected", "inspection_failed"]
            .iter()
            .all(|field| value.get(field).is_some_and(Value::is_boolean))
        && value
            .get("causes")
            .and_then(Value::as_array)
            .is_some_and(|causes| {
                !causes.is_empty()
                    && causes.len() <= 8
                    && causes.iter().all(|cause| {
                        cause.as_object().is_some_and(|object| object.len() == 2)
                            && cause
                                .get("name")
                                .and_then(Value::as_str)
                                .is_some_and(|name| NAMES.contains(&name))
                            && cause
                                .get("code")
                                .and_then(Value::as_str)
                                .is_some_and(|code| CODES.contains(&code))
                    })
            });
    let details = bounded
        .then(|| serde_json::from_value::<NativeErrorDiagnostics>(value.clone()).ok())
        .flatten();
    NativeErrorProjection {
        state: if details.is_some() {
            "available"
        } else {
            "invalid"
        },
        details,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn shared_contract_and_secret_fields_are_checked_before_logging() {
        let fixture: Value = serde_json::from_str(include_str!(
            "../../tests/fixtures/native-error-diagnostics.json"
        ))
        .unwrap();
        assert_eq!(json!(STAGES), fixture["stages"]);
        assert_eq!(json!(NAMES), fixture["names"]);
        assert_eq!(json!(CODES), fixture["codes"]);
        let valid = fixture["diagnostics"].clone();
        let projection = project(&json!({"diagnostics":valid}));
        assert_eq!(projection.state, "available");
        assert_eq!(projection.details.unwrap().stage, "dispatch");
        assert_eq!(
            project(&json!({"error":"synthetic-private-secret"})).state,
            "unavailable"
        );
        assert_eq!(
            project(&json!({"diagnostics_state":"invalid"})).state,
            "invalid"
        );
        assert_eq!(
            project(&json!({"diagnostics_state":"synthetic-private-secret"})).state,
            "invalid"
        );
        for field in [
            "stage",
            "schema_version",
            "causes",
            "chain_truncated",
            "cycle_detected",
            "inspection_failed",
        ] {
            let mut invalid = valid.clone();
            invalid[field] = json!("synthetic-private-secret");
            let projection = project(&json!({"diagnostics":invalid}));
            assert_eq!(projection.state, "invalid");
            assert!(projection.details.is_none());
        }
        for invalid in [
            json!({"message":"synthetic-private-secret"}),
            {
                let mut v = valid.clone();
                v["message"] = json!("synthetic-private-secret");
                v
            },
            {
                let mut v = valid.clone();
                v["causes"][0]["message"] = json!("synthetic-private-secret");
                v
            },
            {
                let mut v = valid.clone();
                v["causes"][0]["name"] = json!("synthetic-private-secret");
                v
            },
            {
                let mut v = valid.clone();
                v["causes"][0]["code"] = json!("synthetic-private-secret");
                v
            },
            {
                let mut v = valid.clone();
                v["causes"] = json!([]);
                v
            },
            {
                let mut v = valid.clone();
                v["causes"] = json!(vec![valid["causes"][0].clone(); 9]);
                v
            },
        ] {
            let projection = project(&json!({"diagnostics":invalid}));
            assert_eq!(projection.state, "invalid");
            assert!(projection.details.is_none());
        }
    }
}
