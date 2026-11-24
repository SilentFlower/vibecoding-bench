//! 已绑定 Unix 事件源显式选择的 Messages 响应转换。

use std::borrow::Cow;
use std::collections::HashMap;
use std::convert::Infallible;
use std::error::Error;
use std::mem::take;
use std::ops::Range;

use axum::body::{Body, Bytes, to_bytes};
use axum::http::{StatusCode, header::CONTENT_TYPE};
use axum::response::{IntoResponse, Response};
use bytes::Buf;
use futures_util::{StreamExt, stream::unfold};
use http_body_util::LengthLimitError;
use serde_json::value::RawValue;
use serde_json::{Value, json};
use uuid::Uuid;

use crate::error::AppError;
use crate::service::session_policy_block;

// opt-in 改写按单个完整 JSON 或一个 SSE 事件聚合原始字节。这是本地缓冲输入预算。
// SSE 每派发一条事件就归零。CRLF 的收尾 LF 若单独透传，不占事件缓冲。
// 账户并发内存仍由运行环境的资源策略管理。
const NORMALIZATION_UNIT_LIMIT: usize = 10 * 1024 * 1024;

type Object<'a> = HashMap<String, &'a RawValue>;
const INVALID_RESPONSE: &str = "V2 本机事件源响应无效或提前终止";

/// 按来源的响应信封生成独立消息 ID，并将确定的错误收口成 Messages 格式。
/// @param status 来源 HTTP 状态。@param content_type 已核验类型。@param body 原来源分片。
/// @return 可直接交付的 HTTP 响应。
pub(super) async fn project(status: StatusCode, content_type: &str, body: Body) -> Response {
    project_observed(status, content_type, body, None)
        .await
        .unwrap_or_else(IntoResponse::into_response)
}

/// 在改写模型消息与错误之前按原会话登记拒答。旧式 sender 可省略网关会话。
/// @param status 来源状态。@param content_type 已核验类型。@param body 原来源分片。
/// @param policy_account 已核验来源的实际账号。@return 公开 Messages 响应或持久化错误。
pub(super) async fn project_observed(
    status: StatusCode,
    content_type: &str,
    body: Body,
    policy_account: Option<i64>,
) -> Result<Response, AppError> {
    let body = match policy_account {
        // V1 的观察器在每个完整拒答事件交付前落盘，普通流帧可以立即交付。
        Some(account) if status.is_success() => {
            session_policy_block::observe_response(Response::new(body), account, Vec::new())
                .into_body()
        }
        _ => body,
    };
    if status == StatusCode::OK && content_type == "text/event-stream" {
        let stream = unfold(
            Some((Sse::default(), body.into_data_stream())),
            |state| async move {
                let (mut sse, mut source) = state?;
                let output = loop {
                    match sse.next() {
                        Ok(Some(bytes)) => {
                            return Some((Ok::<_, Infallible>(bytes), Some((sse, source))));
                        }
                        Ok(None) => match source.next().await {
                            Some(Ok(bytes)) => sse.pending = bytes,
                            None if sse.stopped && sse.record.is_empty() => return None,
                            _ => break messages_error(None, StatusCode::BAD_GATEWAY),
                        },
                        Err(error) => break error,
                    }
                };
                Some((Ok(error_frame(&output)), None))
            },
        );
        return Ok((
            status,
            [(CONTENT_TYPE, "text/event-stream")],
            Body::from_stream(stream),
        )
            .into_response());
    }

    let error_status = if status == StatusCode::OK {
        StatusCode::BAD_GATEWAY
    } else {
        status
    };
    // 来源流已对每块设置空闲超时。此处累计的是一个 JSON 响应的源字节。
    let bytes = match to_bytes(body, NORMALIZATION_UNIT_LIMIT).await {
        Err(error)
            if error
                .source()
                .is_some_and(|cause| cause.is::<LengthLimitError>()) =>
        {
            return Ok((
                error_status,
                axum::Json(normalization_limit_error("JSON 响应")),
            )
                .into_response());
        }
        result => result.ok(),
    };
    if status == StatusCode::OK
        && let Some(body) = bytes.as_ref()
        && let Ok(fields) = serde_json::from_slice::<Object<'_>>(body)
        && event_type(&fields).as_deref() == Some("message")
    {
        let edit = message_id(body, body, &fields);
        return Ok((
            status,
            [(CONTENT_TYPE, "application/json")],
            edit.apply(body),
        )
            .into_response());
    }

    let error = bytes.and_then(|body| serde_json::from_slice::<Value>(&body).ok());
    // JSON 主轮可能在首个事件后已发送 200。此时常规拒答已由流观察器记录，
    // 唯有源端为残缺错误保留的私有字段需要在这里分类，避免把原始详情交付客户。
    let evidence = error.as_ref().and_then(|value| {
        value
            .get("_tui_policy_evidence")
            .or_else(|| (!status.is_success()).then_some(value))
    });
    let reason = policy_account
        .filter(|_| !matches!(status.as_u16(), 401 | 429))
        .zip(evidence.and_then(session_policy_block::classify));
    let mut response = (
        error_status,
        axum::Json(messages_error(error.as_ref(), error_status)),
    )
        .into_response();
    if let Some((account, reason)) = reason {
        session_policy_block::remember_current(account, reason).await?;
        response
            .extensions_mut()
            .insert(session_policy_block::PolicyRefusal);
    }
    Ok(response)
}

fn event_type(fields: &Object<'_>) -> Option<String> {
    serde_json::from_str(fields.get("type")?.get()).ok()
}

fn messages_error(source: Option<&Value>, status: StatusCode) -> Value {
    let error = source.and_then(|value| value.get("error"));
    let fallback = match status.as_u16() {
        400 | 422 => "invalid_request_error",
        413 => "request_too_large",
        401 => "authentication_error",
        403 => "permission_error",
        404 => "not_found_error",
        429 => "rate_limit_error",
        529 => "overloaded_error",
        _ => "api_error",
    };
    let kind = error
        .and_then(|error| error.get("type"))
        .and_then(Value::as_str)
        .filter(|kind| {
            matches!(
                *kind,
                "invalid_request_error"
                    | "authentication_error"
                    | "permission_error"
                    | "not_found_error"
                    | "request_too_large"
                    | "rate_limit_error"
                    | "api_error"
                    | "overloaded_error"
                    | "billing_error"
                    | "timeout_error"
            )
        })
        .unwrap_or(fallback);
    let message = error
        .and_then(|error| error.get("message").unwrap_or(error).as_str())
        .or_else(|| {
            source
                .and_then(|value| value.get("message"))
                .and_then(Value::as_str)
        })
        .filter(|message| !message.is_empty())
        .unwrap_or(INVALID_RESPONSE);
    error_body(kind, message)
}

fn normalization_limit_error(unit: &str) -> Value {
    let limit_mib = NORMALIZATION_UNIT_LIMIT / (1024 * 1024);
    let message = format!("V2 本机事件源的{unit}超过正常化缓冲上限 {limit_mib} MiB");
    error_body("api_error", &message)
}

fn error_body(kind: &str, message: &str) -> Value {
    json!({"type":"error","error":{"type":kind,"message":message}})
}

fn error_frame(error: &Value) -> Bytes {
    Bytes::from(format!("event: error\ndata: {error}\n\n"))
}

struct JsonEdit {
    range: Range<usize>,
    replacement: String,
}

impl JsonEdit {
    fn apply(self, bytes: &[u8]) -> Bytes {
        let mut out = Vec::with_capacity(bytes.len() - self.range.len() + self.replacement.len());
        out.extend_from_slice(&bytes[..self.range.start]);
        out.extend_from_slice(self.replacement.as_bytes());
        out.extend_from_slice(&bytes[self.range.end..]);
        Bytes::from(out)
    }
}

fn message_id(payload: &[u8], object: &[u8], fields: &Object<'_>) -> JsonEdit {
    let id = format!("\"msg_{}\"", Uuid::new_v4().simple());
    // RawValue 借用已解析的原始 JSON。只替换 ID 的字节区间，避免重编码其他字段。
    if let Some(previous) = fields.get("id") {
        let start = previous.get().as_ptr().addr() - payload.as_ptr().addr();
        return JsonEdit {
            range: start..start + previous.get().len(),
            replacement: id,
        };
    }
    let brace = object
        .iter()
        .position(|byte| *byte == b'{')
        .expect("已验证 JSON 对象");
    let start = object.as_ptr().addr() - payload.as_ptr().addr() + brace + 1;
    let comma = if fields.is_empty() { "" } else { "," };
    JsonEdit {
        range: start..start,
        replacement: format!("\"id\":{id}{comma}"),
    }
}

fn sse_fields(record: &[u8]) -> impl Iterator<Item = (&[u8], &[u8])> {
    record
        .strip_prefix(b"\xef\xbb\xbf")
        .unwrap_or(record)
        .split(|byte| matches!(*byte, b'\r' | b'\n'))
        .map(|line| {
            let Some(colon) = line.iter().position(|byte| *byte == b':') else {
                return (line, &b""[..]);
            };
            let value = &line[colon + 1..];
            (&line[..colon], value.strip_prefix(b" ").unwrap_or(value))
        })
}

fn data_lines(record: &[u8]) -> impl Iterator<Item = &[u8]> {
    sse_fields(record).filter_map(|(field, value)| (field == b"data").then_some(value))
}

fn patch_event(record: &[u8], mut edit: JsonEdit) -> Option<Bytes> {
    let mut start = 0;
    for line in data_lines(record) {
        let end = start + line.len();
        if edit.range.start >= start && edit.range.end <= end {
            let offset = line.as_ptr().addr() - record.as_ptr().addr();
            edit.range = (offset + edit.range.start - start)..(offset + edit.range.end - start);
            return Some(edit.apply(record));
        }
        // SSE 多个 data 行在逻辑 JSON 中以单个 LF 相连。
        start = end + 1;
    }
    None
}

#[derive(Default)]
struct Sse {
    pending: Bytes,
    record: Vec<u8>,
    line_len: usize,
    after_cr: bool,
    started: bool,
    stopped: bool,
}

impl Sse {
    fn next(&mut self) -> Result<Option<Bytes>, Value> {
        while let Some(&byte) = self.pending.first() {
            if take(&mut self.after_cr) && byte == b'\n' {
                // CR 已经结束上一行。即使上一帧已交付，也要保留紧随其后的 LF。
                if self.record.is_empty() {
                    return Ok(Some(self.pending.split_to(1)));
                }
                self.append(byte)?;
                continue;
            }
            self.append(byte)?;
            if matches!(byte, b'\r' | b'\n') {
                self.after_cr = byte == b'\r';
                if take(&mut self.line_len) == 0 {
                    let frame = take(&mut self.record);
                    return self.project_frame(frame).map(Some);
                }
            } else {
                self.line_len += 1;
            }
        }
        Ok(None)
    }

    fn append(&mut self, byte: u8) -> Result<(), Value> {
        if self.record.len() == NORMALIZATION_UNIT_LIMIT {
            return Err(normalization_limit_error("单条 SSE 事件"));
        }
        if self.record.len() == self.record.capacity() {
            let capacity = (self.record.capacity() * 2).clamp(8, NORMALIZATION_UNIT_LIMIT);
            self.record.reserve_exact(capacity - self.record.len());
        }
        self.record.push(byte);
        self.pending.advance(1);
        Ok(())
    }

    fn project_frame(&mut self, record: Vec<u8>) -> Result<Bytes, Value> {
        let invalid = || messages_error(None, StatusCode::BAD_GATEWAY);
        let event_name = sse_fields(&record)
            .filter_map(|(name, value)| (name == b"event").then_some(value))
            .last();
        let mut lines = data_lines(&record);
        // 常见的单 data 行直接借用事件缓冲。多行按 SSE 规则拼接。
        let mut payload = Cow::Borrowed(lines.next().unwrap_or_default());
        for line in lines {
            let payload = payload.to_mut();
            payload.push(b'\n');
            payload.extend_from_slice(line);
        }
        if event_name == Some(b"error") {
            let error = serde_json::from_slice(&payload).ok();
            return Err(messages_error(error.as_ref(), StatusCode::BAD_GATEWAY));
        }
        if payload.is_empty() || self.stopped && payload.trim_ascii() == b"[DONE]" {
            return Ok(Bytes::from(record));
        }
        let fields = serde_json::from_slice::<Object<'_>>(&payload).map_err(|_| invalid())?;
        match event_type(&fields).as_deref() {
            Some("error") => {
                let error = serde_json::from_slice(&payload).ok();
                Err(messages_error(error.as_ref(), StatusCode::BAD_GATEWAY))
            }
            Some("message_start") if !self.started => {
                let message = fields.get("message").ok_or_else(invalid)?.get().as_bytes();
                let message_fields =
                    serde_json::from_slice::<Object<'_>>(message).map_err(|_| invalid())?;
                let edit = message_id(&payload, message, &message_fields);
                self.started = true;
                patch_event(&record, edit).ok_or_else(invalid)
            }
            Some("message_start") => Err(invalid()),
            Some("message_stop") if self.started => {
                self.stopped = true;
                Ok(Bytes::from(record))
            }
            Some("message_stop") => Err(invalid()),
            _ => Ok(Bytes::from(record)),
        }
    }
}

#[cfg(test)]
mod tests {
    use std::io;
    use std::time::Duration;

    use futures_util::{Stream, stream::iter};
    use http_body_util::BodyExt;
    use tokio::sync::oneshot;
    use tokio::time::timeout;

    use super::*;
    use crate::service::usage::UsageCapture;

    fn inspect(body: &[u8]) -> UsageCapture {
        let mut usage = UsageCapture::observer(&Value::Null);
        for part in body.chunks(7) {
            usage.observe(part);
        }
        usage
    }

    // 用本机源实际协议的 64 KiB 分块形状驱动正常化器。
    const TEST_CHUNK_BYTES: usize = 64 * 1024;

    fn padded_payload(prefix: &[u8], suffix: &[u8], size: usize) -> Bytes {
        let mut bytes = Vec::with_capacity(size);
        bytes.extend_from_slice(prefix);
        bytes.resize(size - suffix.len(), b'x');
        bytes.extend_from_slice(suffix);
        Bytes::from(bytes)
    }

    fn uds_chunks(bytes: Bytes) -> impl Stream<Item = io::Result<Bytes>> + Send {
        iter(
            (0..bytes.len())
                .step_by(TEST_CHUNK_BYTES)
                .map(move |start| {
                    Ok(bytes.slice(start..(start + TEST_CHUNK_BYTES).min(bytes.len())))
                }),
        )
    }

    #[tokio::test]
    async fn gateway_id_json_enforces_local_normalization_limit_inclusively() {
        let head = br#"{"type":"message","id":"msg_source","content":[{"type":"text","text":""#;
        let tail = br#""}]}"#;
        let exact = padded_payload(head, tail, NORMALIZATION_UNIT_LIMIT);
        let response = project(
            StatusCode::OK,
            "application/json",
            Body::from_stream(uds_chunks(exact)),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = response.into_body().collect().await.unwrap().to_bytes();
        // 上限按源字节检查。生成的 ID 可以比来源 ID 长。
        assert!(body.len() > NORMALIZATION_UNIT_LIMIT);
        let payload: Object<'_> = serde_json::from_slice(&body).unwrap();
        let id: String = serde_json::from_str(payload["id"].get()).unwrap();
        assert!(Uuid::parse_str(id.strip_prefix("msg_").unwrap()).is_ok());
        assert!(body.ends_with(tail));

        let oversized = padded_payload(head, tail, NORMALIZATION_UNIT_LIMIT + 1);
        let response = project(
            StatusCode::OK,
            "application/json",
            Body::from_stream(uds_chunks(oversized)),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
        let body = response.into_body().collect().await.unwrap().to_bytes();
        let payload: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(payload["error"]["type"], "api_error");
        assert_eq!(
            payload["error"]["message"],
            "V2 本机事件源的JSON 响应超过正常化缓冲上限 10 MiB"
        );
    }

    const TEST_START: &[u8] =
        b"data: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":3}}}\n\n";
    const TEST_STOP: &[u8] = b"data: {\"type\":\"message_stop\"}\n\n";
    const TEXT_DELTA: &[u8] =
        br#"data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":""#;
    const TEXT_DELTA_END: &[u8] = b"\"}}\n\n";

    #[tokio::test]
    async fn gateway_id_sse_limits_only_the_current_event() {
        for oversize in [false, true] {
            let event = padded_payload(
                TEXT_DELTA,
                TEXT_DELTA_END,
                NORMALIZATION_UNIT_LIMIT + usize::from(oversize),
            );
            let source = uds_chunks(Bytes::from_static(TEST_START))
                .chain(uds_chunks(event.clone()))
                .chain(uds_chunks(Bytes::from_static(TEST_STOP)));
            let response = project(
                StatusCode::OK,
                "text/event-stream",
                Body::from_stream(source),
            )
            .await;
            assert_eq!(response.status(), StatusCode::OK);
            let mut body = response.into_body();
            let start = body.frame().await.unwrap().unwrap().into_data().unwrap();
            assert!(start.windows(4).any(|part| part == b"msg_"));
            let next = body.frame().await.unwrap().unwrap().into_data().unwrap();
            if oversize {
                assert_eq!(
                    next,
                    error_frame(&normalization_limit_error("单条 SSE 事件"))
                );
            } else {
                assert_eq!(next, event);
                assert_eq!(
                    body.frame().await.unwrap().unwrap().into_data().unwrap(),
                    TEST_STOP
                );
            }
            // 超界只交付一个错误事件。来源中即使还有成功终态也不能继续透传。
            assert!(body.frame().await.is_none());
        }
    }

    #[tokio::test]
    async fn gateway_id_sse_cumulative_payload_can_exceed_local_buffer_limit() {
        let delta = padded_payload(TEXT_DELTA, TEXT_DELTA_END, 768 * 1024);
        let event_count = NORMALIZATION_UNIT_LIMIT / delta.len() + 1;
        let end = Bytes::from_static(
            br#"data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":9,"cache_read_input_tokens":4,"cache_creation_input_tokens":7,"cache_creation":{"ephemeral_5m_input_tokens":2,"ephemeral_1h_input_tokens":5}}}

data: {"type":"message_stop"}

"#,
        );
        let source = uds_chunks(Bytes::from_static(TEST_START))
            .chain(
                iter((0..event_count).map({
                    let delta = delta.clone();
                    move |_| uds_chunks(delta.clone())
                }))
                .flatten(),
            )
            .chain(uds_chunks(end));
        let response = project(
            StatusCode::OK,
            "text/event-stream",
            Body::from_stream(source),
        )
        .await;
        let mut body = response.into_body();
        let mut usage = UsageCapture::observer(&Value::Null);
        let first = body.frame().await.unwrap().unwrap().into_data().unwrap();
        usage.observe(&first);
        let mut total = 0;
        for _ in 0..event_count {
            let frame = body.frame().await.unwrap().unwrap().into_data().unwrap();
            assert_eq!(frame, delta);
            total += frame.len();
            usage.observe(&frame);
        }
        assert!(total > NORMALIZATION_UNIT_LIMIT);
        while let Some(frame) = body.frame().await {
            usage.observe(&frame.unwrap().into_data().unwrap());
        }
        let observation = usage.observation(true);
        assert_eq!(
            observation.tokens,
            [Some(3), Some(9), Some(4), Some(7), Some(2), Some(5)]
        );
        assert!(observation.error_type.is_none());
        assert!(!observation.partial);
    }

    #[tokio::test]
    async fn gateway_id_stream_keeps_tools_signatures_cache_and_late_usage() {
        let (release, awaiting) = oneshot::channel();
        let start = b"\xef\xbb\xbf: before\r\nid: transport-id\r\nevent: message_start\r\ndata: {\"type\":\"message_start\",\r\ndata: \"message\":{\"id\": null, \"content\":[],\"usage\":{\"input_tokens\":100,\"cache_read_input_tokens\":25}}}\r\n\r\n";
        let tail = br#"event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"tool_use","id":"toolu_original","name":"Read","input":{},"cache_control":{"type":"ephemeral","ttl":"1h"}}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"input_json_delta","partial_json":"{\"id\":\"literal\"}"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"thinking","thinking":"\u4e2d"}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"signature_delta","signature":"abc/xyz=="}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"tool_use"},
data: "usage":{"output_tokens":7,"cache_read_input_tokens":41,"cache_creation_input_tokens":34,"cache_creation":{"ephemeral_5m_input_tokens":13,"ephemeral_1h_input_tokens":21}}}

event: message_stop
data: {"type":"message_stop"}

"#;
        let source = iter(
            start
                .chunks(1)
                .map(|part| Ok::<_, io::Error>(Bytes::copy_from_slice(part))),
        )
        .chain(futures_util::stream::once(async move {
            awaiting.await.unwrap();
            Ok(Bytes::from_static(tail))
        }));
        let mut body = project(
            StatusCode::OK,
            "text/event-stream",
            Body::from_stream(source),
        )
        .await
        .into_body();
        let frame = timeout(Duration::from_secs(2), body.frame())
            .await
            .unwrap()
            .unwrap()
            .unwrap()
            .into_data()
            .unwrap();
        let mut edited = frame.to_vec();
        let start_usage = inspect(&[edited.as_slice(), b"\n"].concat()).observation(false);
        let id = start_usage.message_id.unwrap();
        let independent = id.strip_prefix("msg_").unwrap();
        assert!(Uuid::parse_str(independent).is_ok());
        let exact_prefix = String::from_utf8_lossy(start).replacen("null", &format!("\"{id}\""), 1);
        assert_eq!(edited, &exact_prefix.as_bytes()[..exact_prefix.len() - 1]);
        release.send(()).unwrap();
        edited.extend(body.collect().await.unwrap().to_bytes());
        assert_eq!(edited, [exact_prefix.as_bytes(), tail].concat());
        let observed = inspect(&edited).observation(true);
        assert_eq!(
            observed.tokens,
            [Some(100), Some(7), Some(41), Some(34), Some(13), Some(21)]
        );
        assert_eq!(observed.stop_reason.as_deref(), Some("tool_use"));
        assert!(!observed.partial);
    }

    #[tokio::test]
    async fn gateway_id_json_changes_top_level_id_only_and_uses_fresh_ids() {
        let payload = r#"  { "type":"message", "id":"msg_original", "content":[{"type":"tool_use","id":"toolu_7","input":{"id":"same","x":1.23000e3},"cache_control":{"type":"ephemeral","ttl":"5m"}},{"type":"thinking","thinking":"\u4e2d","signature":"sig=="}], "usage":{"input_tokens":100,"output_tokens":7,"cache_read_input_tokens":41,"cache_creation_input_tokens":34,"cache_creation":{"ephemeral_5m_input_tokens":13,"ephemeral_1h_input_tokens":21}} } "#;
        let mut first_id = None;
        for original in [
            payload.to_owned(),
            payload.replace("\"id\":\"msg_original\", ", ""),
        ] {
            let response = project(
                StatusCode::OK,
                "application/json",
                Body::from(original.clone()),
            )
            .await;
            assert_eq!(response.status(), StatusCode::OK);
            let wire = response.into_body().collect().await.unwrap().to_bytes();
            let usage = inspect(&wire).observation(true);
            let id = usage.message_id.unwrap();
            assert!(Uuid::parse_str(id.strip_prefix("msg_").unwrap()).is_ok());
            assert_ne!(first_id, Some(id.clone()));
            if first_id.is_none() {
                assert_eq!(wire, payload.replace("msg_original", &id));
                first_id = Some(id);
            } else {
                assert_eq!(
                    wire,
                    original.replacen('{', &format!("{{\"id\":\"{id}\","), 1)
                );
            }
            assert_eq!(
                usage.tokens,
                [Some(100), Some(7), Some(41), Some(34), Some(13), Some(21)]
            );
            assert!(!usage.partial);
        }
    }

    #[tokio::test]
    async fn gateway_id_errors_terminate_stream_and_report_partial_usage() {
        let begin = b"data: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":123,\"output_tokens\":7,\"cache_read_input_tokens\":25}}}\n\n";
        for (tail, kind) in [
            (
                b"event: error\ndata: {\"error\":{\"type\":\"overloaded_error\",\"message\":\"fixture busy\"}}\n\ndata: {\"type\":\"message_stop\"}\n\n".as_slice(),
                "overloaded_error",
            ),
            (b"data: {\"type\":\"error\",\"message\":\"fixture failed\"}\n\n", "api_error"),
            (b"data: {\"type\":\"message_delta\"", "api_error"),
            (b"", "api_error"),
        ] {
            let reply = project(StatusCode::OK, "text/event-stream", Body::from([begin.as_slice(), tail].concat())).await;
            let wire = reply.into_body().collect().await.unwrap().to_bytes();
            let text = std::str::from_utf8(&wire).unwrap();
            assert_eq!(text.matches("event: error\n").count(), 1);
            assert!(!text.contains("message_stop"), "{text}");
            let usage = inspect(&wire).observation(true);
            assert_eq!(usage.error_type.as_deref(), Some(kind));
            assert_eq!(usage.tokens[2], Some(25));
            assert!(usage.partial);
        }
    }

    #[tokio::test]
    async fn gateway_id_broken_stream_preserves_late_usage_and_marks_partial() {
        let start = br#"data: {"type":"message_start","message":{"usage":{"input_tokens":3,"cache_read_input_tokens":2}}}

data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},
data: "usage":{"output_tokens":4,"cache_read_input_tokens":5,"cache_creation_input_tokens":7,"cache_creation":{"ephemeral_5m_input_tokens":3,"ephemeral_1h_input_tokens":4}}}

"#;
        let stop = b"data: {\"type\":\"message_stop\"}\r\n\r\n";
        for stopped in [false, true] {
            let prefix = if stopped {
                [start.as_slice(), stop].concat()
            } else {
                start.to_vec()
            };
            let source = iter([
                Ok(Bytes::from(prefix)),
                Err(io::Error::from(io::ErrorKind::UnexpectedEof)),
            ]);
            let response = project(
                StatusCode::OK,
                "text/event-stream",
                Body::from_stream(source),
            )
            .await;
            let wire = response.into_body().collect().await.unwrap().to_bytes();
            let usage = inspect(&wire).observation(true);
            assert_eq!(usage.error_type.as_deref(), Some("api_error"));
            assert_eq!(
                usage.tokens,
                [Some(3), Some(4), Some(5), Some(7), Some(3), Some(4)]
            );
            assert!(usage.partial);
        }
    }

    #[tokio::test]
    async fn gateway_id_normalizes_http_errors_and_never_assigns_an_error_id() {
        for (status, source, expected, kind) in [
            (
                StatusCode::UNAUTHORIZED,
                r#"{"error":"fixture refusal"}"#,
                StatusCode::UNAUTHORIZED,
                "authentication_error",
            ),
            (
                StatusCode::TOO_MANY_REQUESTS,
                "{}",
                StatusCode::TOO_MANY_REQUESTS,
                "rate_limit_error",
            ),
            (
                StatusCode::OK,
                r#"{"type":"error","error":{"type":"overloaded_error","message":"fixture busy"}}"#,
                StatusCode::BAD_GATEWAY,
                "overloaded_error",
            ),
        ] {
            let response = project(status, "application/json", Body::from(source)).await;
            assert_eq!(response.status(), expected);
            let body = response.into_body().collect().await.unwrap().to_bytes();
            let value: Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(value["type"], "error");
            assert_eq!(value["error"]["type"], kind);
            assert!(
                value["error"]["message"]
                    .as_str()
                    .is_some_and(|message| !message.is_empty())
            );
            assert!(value.get("id").is_none());
        }
    }
}
