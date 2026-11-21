//! Anthropic Messages 与现有 AGY Gemini 执行边界的双向转换。

use std::collections::HashMap;
use std::fmt::Write;
use std::io::Error as IoError;
use std::mem::replace;

use axum::Json;
use axum::body::{Body, Bytes};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use futures_util::{Stream, StreamExt, stream};
use serde_json::{Map, Value, json};
use uuid::Uuid;

use crate::error::AppError;

fn invalid(message: &str) -> AppError {
    AppError::BadRequest(message.into())
}

fn text(value: &Value) -> Result<&str, AppError> {
    value
        .as_str()
        .ok_or_else(|| invalid("Messages 文本字段无效"))
}

fn required_name(value: &Value) -> Result<&str, AppError> {
    text(value).and_then(|name| {
        if name.is_empty() {
            Err(invalid("Messages 工具名或调用 ID 为空"))
        } else {
            Ok(name)
        }
    })
}

fn system_parts(value: &Value) -> Result<Vec<Value>, AppError> {
    if let Some(value) = value.as_str() {
        return Ok(vec![json!({"text": value})]);
    }
    value
        .as_array()
        .ok_or_else(|| invalid("Messages 系统提示无效"))?
        .iter()
        .map(|block| {
            if block["type"] != "text" {
                return Err(invalid("Messages 系统提示只支持文本"));
            }
            Ok(json!({"text": text(&block["text"])?}))
        })
        .collect()
}

/// 投影已识别的 Messages 请求。@param request 原始请求。@return Gemini 正文。
pub(super) fn convert_request(request: &Value) -> Result<Value, AppError> {
    let messages = request["messages"]
        .as_array()
        .filter(|items| !items.is_empty())
        .ok_or_else(|| invalid("Messages 历史为空或无效"))?;
    let mut contents = Vec::with_capacity(messages.len());
    let mut call_names = HashMap::new();
    let mut system = request
        .get("system")
        .filter(|value| !value.is_null())
        .map(system_parts)
        .transpose()?
        .unwrap_or_default();
    for message in messages {
        let role = match message["role"].as_str() {
            Some("user") => "user",
            Some("assistant") => "model",
            Some("system") => {
                // Claude Code 可能将环境提示附在用户之后，Gemini 通过同一系统指令接收它。
                system.extend(system_parts(&message["content"])?);
                continue;
            }
            _ => return Err(invalid("Messages 消息角色无效")),
        };
        let content = &message["content"];
        let mut parts = Vec::new();
        if let Some(content) = content.as_str() {
            parts.push(json!({"text": content}));
        } else {
            let blocks = content
                .as_array()
                .ok_or_else(|| invalid("Messages 内容块无效"))?;
            for block in blocks {
                let part = match (role, block["type"].as_str()) {
                    (_, Some("text")) => json!({"text": text(&block["text"])?}),
                    ("user", Some("image")) if block["source"]["type"] == "base64" => json!({
                        "inlineData": {
                            "mimeType": text(&block["source"]["media_type"])?,
                            "data": text(&block["source"]["data"])?,
                        },
                    }),
                    ("model", Some("thinking")) => {
                        let mut part = json!({"text": text(&block["thinking"])?, "thought": true});
                        if let Some(signature) =
                            block["signature"].as_str().filter(|s| !s.is_empty())
                        {
                            part["thoughtSignature"] = json!(signature);
                        }
                        part
                    }
                    ("model", Some("tool_use")) => {
                        let id = required_name(&block["id"])?;
                        let name = required_name(&block["name"])?;
                        if !block["input"].is_object() || call_names.insert(id, name).is_some() {
                            return Err(invalid("Messages 函数参数无效或调用 ID 重复"));
                        }
                        let mut part = json!({"functionCall": {"id": id, "name": name, "args": block["input"]}});
                        if let Some(signature) =
                            block["signature"].as_str().filter(|s| !s.is_empty())
                        {
                            part["thoughtSignature"] = json!(signature);
                        }
                        part
                    }
                    ("user", Some("tool_result")) => {
                        let id = required_name(&block["tool_use_id"])?;
                        let name = call_names
                            .get(id)
                            .ok_or_else(|| invalid("Messages 工具结果缺少原调用"))?;
                        let result = match block.get("content") {
                            None => json!(""),
                            Some(v) if v.is_string() || v.is_array() => v.clone(),
                            _ => return Err(invalid("Messages 工具结果格式无效")),
                        };
                        let mut response = json!({"result": result});
                        if let Some(is_error) = block.get("is_error") {
                            response["is_error"] = json!(
                                is_error
                                    .as_bool()
                                    .ok_or_else(|| invalid("Messages 工具错误标记无效"))?
                            );
                        }
                        json!({"functionResponse": {"id": id, "name": name, "response": response}})
                    }
                    _ => return Err(invalid("反重力 Messages 暂不支持此类内容块")),
                };
                parts.push(part);
            }
        }
        if parts.is_empty() {
            return Err(invalid("Messages 内容为空"));
        }
        contents.push(json!({"role": role, "parts": parts}));
    }

    if contents.is_empty() {
        return Err(invalid("Messages 缺少对话消息"));
    }
    let mut body = json!({"contents": contents});
    if !system.is_empty() {
        body["systemInstruction"] = json!({"parts": system});
    }
    if let Some(tools) = request.get("tools") {
        let definitions = tools.as_array().ok_or_else(|| invalid("Messages 工具声明无效"))?
            .iter().map(|tool| {
                if tool.get("type").is_some_and(|kind| kind != "custom") || !tool["input_schema"].is_object() {
                    return Err(invalid("反重力 Messages 此入口需要普通函数声明"));
                }
                let mut definition = json!({"name": required_name(&tool["name"])?, "parameters": tool["input_schema"]});
                if let Some(description) = tool.get("description") {
                    definition["description"] = json!(text(description)?);
                }
                Ok(definition)
            }).collect::<Result<Vec<_>, AppError>>()?;
        if !definitions.is_empty() {
            body["tools"] = json!([{"functionDeclarations": definitions}]);
        }
    }
    if let Some(choice) = request.get("tool_choice") {
        let mode = match choice["type"].as_str() {
            Some("auto") => "AUTO",
            Some("none") => "NONE",
            _ => return Err(invalid("反重力 Messages 仅支持 auto 和 none 工具选择")),
        };
        body["toolConfig"] = json!({"functionCallingConfig": {"mode": mode}});
    }
    let mut config = Map::new();
    for (source, target) in [
        ("max_tokens", "maxOutputTokens"),
        ("temperature", "temperature"),
        ("top_p", "topP"),
    ] {
        if let Some(value) = request.get(source) {
            config.insert(target.into(), value.clone());
        }
    }
    if !config.is_empty() {
        body["generationConfig"] = Value::Object(config);
    }
    Ok(body)
}

/// 核对 Messages 的流式选项。@param request 原始请求。@return 是否使用 SSE。
pub(super) fn streaming(request: &Value) -> Result<bool, AppError> {
    request.get("stream").map_or(Ok(false), |v| {
        v.as_bool()
            .ok_or_else(|| invalid("Messages stream 必须为布尔值"))
    })
}

/// 分配本次 Messages 响应标识。@return 兼容 Claude 的公开 ID。
pub(super) fn message_id() -> String {
    format!("msg_{}", Uuid::new_v4().simple())
}

fn usage(source: &Value) -> Value {
    let count = |field: &str| source[field].as_u64().unwrap_or(0);
    let cached = count("cachedContentTokenCount");
    json!({
        "input_tokens": count("promptTokenCount").saturating_sub(cached),
        "cache_read_input_tokens": cached,
        "output_tokens": count("candidatesTokenCount").saturating_add(count("thoughtsTokenCount")),
    })
}

fn stop_reason(reason: Option<&str>, used_tool: bool) -> &'static str {
    match reason {
        Some("MAX_TOKENS") => "max_tokens",
        Some("SAFETY" | "BLOCKLIST" | "PROHIBITED_CONTENT" | "RECITATION" | "SPII") => "refusal",
        _ if used_tool => "tool_use",
        _ => "end_turn",
    }
}

fn content_block(part: &Value) -> Option<Value> {
    if let Some(call) = part.get("functionCall") {
        Some(
            json!({"type": "tool_use", "id": call["id"], "name": call["name"], "input": call["args"].as_object().cloned().unwrap_or_default()}),
        )
    } else if part["thought"] == true {
        Some(
            json!({"type": "thinking", "thinking": part["text"].as_str().unwrap_or(""),
            "signature": part["thoughtSignature"].as_str().unwrap_or("")}),
        )
    } else {
        part["text"]
            .as_str()
            .map(|text| json!({"type": "text", "text": text}))
    }
}

/// 输出原生结果对应的 Messages JSON。@param output 已聚合的 Gemini 帧。@param model 公开模型。@return Anthropic 响应。
pub(super) fn json_response(output: &Value, model: &str) -> Response {
    let candidate = &output["candidates"][0];
    let content: Vec<_> = candidate["content"]["parts"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(content_block)
        .collect();
    let used_tool = content.iter().any(|block| block["type"] == "tool_use");
    Json(json!({
        "id": message_id(), "type": "message", "role": "assistant", "model": model,
        "stop_reason": stop_reason(candidate["finishReason"].as_str(), used_tool), "stop_sequence": null,
        "content": content, "usage": usage(&output["usageMetadata"]),
    })).into_response()
}

/// 输出 Messages 入口的协议错误。@param status HTTP 状态。@param message 脱敏文案。@return 错误 JSON。
pub(super) fn error_response(status: StatusCode, message: &str) -> Response {
    (status, Json(error_payload(status, message))).into_response()
}

fn error_payload(status: StatusCode, message: &str) -> Value {
    let kind = match status {
        StatusCode::BAD_REQUEST => "invalid_request_error",
        StatusCode::UNAUTHORIZED => "authentication_error",
        StatusCode::FORBIDDEN => "permission_error",
        StatusCode::NOT_FOUND => "not_found_error",
        StatusCode::TOO_MANY_REQUESTS => "rate_limit_error",
        StatusCode::SERVICE_UNAVAILABLE => "overloaded_error",
        _ => "api_error",
    };
    json!({"type": "error", "error": {"type": kind, "message": message}})
}

fn event(buffer: &mut String, name: &str, value: Value) {
    let _ = write!(buffer, "event: {name}\ndata: {value}\n\n");
}

/// 输出已完成的服务端工具回包。@param message 含调用和结果的完整消息。@return Anthropic SSE。
pub(super) fn tool_stream(mut message: Value) -> Response {
    let blocks = replace(&mut message["content"], json!([]));
    let reason = replace(&mut message["stop_reason"], Value::Null);
    let usage = message["usage"].clone();
    let mut output = String::new();
    event(
        &mut output,
        "message_start",
        json!({"type":"message_start","message":message}),
    );
    for (index, block) in blocks.as_array().into_iter().flatten().enumerate() {
        let mut block = block.clone();
        let input = if block["type"] == "server_tool_use" {
            Some(replace(&mut block["input"], json!({})))
        } else {
            None
        };
        event(
            &mut output,
            "content_block_start",
            json!({"type":"content_block_start","index":index,"content_block":block}),
        );
        if let Some(input) = input {
            event(
                &mut output,
                "content_block_delta",
                json!({"type":"content_block_delta","index":index,
                "delta":{"type":"input_json_delta","partial_json":input.to_string()}}),
            );
        }
        event(
            &mut output,
            "content_block_stop",
            json!({"type":"content_block_stop","index":index}),
        );
    }
    event(
        &mut output,
        "message_delta",
        json!({"type":"message_delta","delta":{"stop_reason":reason,"stop_sequence":null},"usage":usage}),
    );
    event(&mut output, "message_stop", json!({"type":"message_stop"}));
    (
        [
            ("content-type", "text/event-stream"),
            ("cache-control", "no-cache"),
        ],
        output,
    )
        .into_response()
}

struct MessageStream {
    model: String,
    id: String,
    index: usize,
    open: Option<&'static str>,
    started: bool,
    failed: bool,
    used_tool: bool,
    finish: Option<String>,
    usage: Value,
}

impl MessageStream {
    fn close_block(&mut self, output: &mut String) {
        if self.open.take().is_some() {
            event(
                output,
                "content_block_stop",
                json!({"type":"content_block_stop", "index":self.index}),
            );
            self.index += 1;
        }
    }

    fn start_block(&mut self, output: &mut String, kind: &'static str, block: Value) {
        self.close_block(output);
        self.open = Some(kind);
        event(
            output,
            "content_block_start",
            json!({"type":"content_block_start", "index":self.index,"content_block":block}),
        );
    }

    fn delta(&self, output: &mut String, delta: Value) {
        event(
            output,
            "content_block_delta",
            json!({"type":"content_block_delta", "index":self.index,"delta":delta}),
        );
    }

    fn push(&mut self, frame: Value, output: &mut String) {
        if frame["usageMetadata"].is_object() {
            self.usage = usage(&frame["usageMetadata"]);
        }
        if !self.started {
            self.started = true;
            event(
                output,
                "message_start",
                json!({"type":"message_start","message":{
                    "id":self.id,"type":"message","role":"assistant","model":self.model,"content":[],
                    "stop_reason":null,"stop_sequence":null,"usage":self.usage,
                }}),
            );
        }
        let candidate = &frame["candidates"][0];
        if let Some(reason) = candidate["finishReason"].as_str() {
            self.finish = Some(reason.to_owned());
        }
        for part in candidate["content"]["parts"]
            .as_array()
            .into_iter()
            .flatten()
        {
            if let Some(call) = part.get("functionCall") {
                self.used_tool = true;
                let mut block = content_block(part).expect("函数帧可映射为工具块");
                block["input"] = json!({});
                self.start_block(output, "tool_use", block);
                let arguments = call["args"]
                    .as_object()
                    .map_or_else(|| "{}".into(), |a| json!(a).to_string());
                self.delta(
                    output,
                    json!({"type":"input_json_delta","partial_json":arguments}),
                );
                self.close_block(output);
            } else if part["thought"] == true {
                if self.open != Some("thinking") {
                    self.start_block(
                        output,
                        "thinking",
                        json!({"type":"thinking","thinking":"","signature":""}),
                    );
                }
                if let Some(text) = part["text"].as_str() {
                    self.delta(output, json!({"type":"thinking_delta","thinking":text}));
                }
                if let Some(signature) = part["thoughtSignature"].as_str() {
                    self.delta(
                        output,
                        json!({"type":"signature_delta","signature":signature}),
                    );
                    self.close_block(output);
                }
            } else if let Some(text) = part["text"].as_str() {
                if self.open != Some("text") {
                    self.start_block(output, "text", json!({"type":"text","text":""}));
                }
                self.delta(output, json!({"type":"text_delta","text":text}));
            }
        }
    }

    fn finish(&mut self, output: &mut String) {
        self.close_block(output);
        event(
            output,
            "message_delta",
            json!({"type":"message_delta","delta":{
            "stop_reason":stop_reason(self.finish.as_deref(),self.used_tool),"stop_sequence":null,
        },"usage":self.usage}),
        );
        event(output, "message_stop", json!({"type":"message_stop"}));
    }
}

/// 在原帧和终态上生成 Claude SSE。@param frames 原生响应。@param model 公开模型。@return 流式 HTTP 响应。
pub(super) fn stream_response(
    frames: impl Stream<Item = Result<Value, AppError>> + Send + 'static,
    model: String,
) -> Response {
    let mut state = MessageStream {
        model,
        id: message_id(),
        index: 0,
        open: None,
        started: false,
        failed: false,
        used_tool: false,
        finish: None,
        usage: usage(&Value::Null),
    };
    let stream = frames
        .map(Some)
        .chain(stream::once(async { None }))
        .map(move |item| {
            let mut output = String::new();
            match item {
                Some(Ok(frame)) if !state.failed => state.push(frame, &mut output),
                Some(Err(error)) if !state.failed => {
                    state.failed = true;
                    let (status, body) = super::gemini_error_body(error);
                    let message = body["error"]["message"]
                        .as_str()
                        .unwrap_or("AGY 原生响应失败");
                    event(&mut output, "error", error_payload(status, message));
                }
                None if state.started && !state.failed => state.finish(&mut output),
                _ => {}
            }
            Ok::<Bytes, IoError>(Bytes::from(output))
        });
    (
        [
            ("content-type", "text/event-stream"),
            ("cache-control", "no-cache"),
        ],
        Body::from_stream(stream),
    )
        .into_response()
}
