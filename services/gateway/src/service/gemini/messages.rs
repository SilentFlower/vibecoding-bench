//! Anthropic Messages 与现有 AGY Gemini 执行边界的双向转换。

use std::borrow::Cow;
use std::collections::HashMap;
use std::fmt::Write;
use std::io::{Error as IoError, copy, sink};
use std::mem::replace;
use std::sync::LazyLock;

use axum::Json;
use axum::body::{Body, Bytes};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use base64::alphabet;
use base64::engine::DecodePaddingMode;
use base64::engine::general_purpose::{GeneralPurpose, GeneralPurposeConfig};
use base64::read::DecoderReader;
use futures_util::{Stream, StreamExt, stream};
use regex::Regex;
use serde_json::{Map, Value, json};
use uuid::Uuid;

use crate::error::AppError;

use super::{AGY_IMAGE_MIME_TYPES, gemini_thinking_budget_tier, gemini_thinking_level_tier};

const IMAGE_BASE64: GeneralPurpose = GeneralPurpose::new(
    &alphabet::STANDARD,
    GeneralPurposeConfig::new().with_decode_padding_mode(DecodePaddingMode::Indifferent),
);
const USER_PROMPT_SUBMIT_CONTEXT_PREFIX: &str = "UserPromptSubmit hook additional context: ";
static READ_TRUNCATION_NOTICE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"^\[Truncated: .*\blines [0-9]+[-–][0-9]+ of [0-9]+ total\b.*\bRead with offset=[0-9]+ limit=[0-9]+\b.*\]$",
    )
    .unwrap()
});

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

fn append_turn_context(contents: &mut [Value], turn_context: &mut Vec<Value>) {
    if let Some(parts) = contents
        .last_mut()
        .filter(|content| content["role"] == "user")
        .and_then(|content| content["parts"].as_array_mut())
    {
        parts.append(turn_context);
    }
}

fn has_read_result_in_user_turn(contents: &[Value]) -> bool {
    contents
        .iter()
        .rev()
        .take_while(|content| content["role"] == "user")
        .flat_map(|content| content["parts"].as_array().into_iter().flatten())
        .any(|part| part["functionResponse"]["name"] == "Read")
}

/// 投影已识别的 Messages 请求。@param request 原始请求。@return Gemini 正文。
pub(super) fn convert_request(request: &Value) -> Result<Value, AppError> {
    let messages = request["messages"]
        .as_array()
        .filter(|items| !items.is_empty())
        .ok_or_else(|| invalid("Messages 历史为空或无效"))?;
    let mut contents = Vec::with_capacity(messages.len());
    let mut call_names = HashMap::new();
    let mut turn_context = Vec::new();
    let mut system = request
        .get("system")
        .filter(|value| !value.is_null())
        .map(system_parts)
        .transpose()?
        .unwrap_or_default();
    for message in messages {
        let role = match message["role"].as_str() {
            Some("user") => "user",
            Some("assistant") => {
                append_turn_context(&mut contents, &mut turn_context);
                "model"
            }
            Some("system") => {
                let has_user_turn = contents
                    .last()
                    .is_some_and(|content| content["role"] == "user");
                for part in system_parts(&message["content"])? {
                    if has_user_turn
                        && part["text"].as_str().is_some_and(|text| {
                            text.starts_with(USER_PROMPT_SUBMIT_CONTEXT_PREFIX)
                                || (READ_TRUNCATION_NOTICE.is_match(text)
                                    && has_read_result_in_user_turn(&contents))
                        })
                    {
                        // 当轮补充文本随工具结果发送，使旧的系统提示和对话前缀可继续复用。
                        turn_context.push(part);
                    } else {
                        system.push(part);
                    }
                }
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
    append_turn_context(&mut contents, &mut turn_context);

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

/// 读取供原生目录选号的思考档位。@param request Claude 请求。@return 可映射的档位。
pub(super) fn thinking_tier(request: &Value) -> Option<&'static str> {
    let thinking = &request["thinking"];
    if thinking["type"] == "enabled"
        && let Some(budget) = thinking["budget_tokens"]
            .as_i64()
            .filter(|budget| *budget > 0)
    {
        return gemini_thinking_budget_tier(budget);
    }
    let effort = request.pointer("/output_config/effort")?.as_str()?.trim();
    if effort.eq_ignore_ascii_case("max") {
        Some("xhigh")
    } else if effort.eq_ignore_ascii_case("none") {
        Some("low")
    } else {
        gemini_thinking_level_tier(effort)
    }
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

fn response_text(part: &Value) -> Option<Cow<'_, str>> {
    if let Some(text) = part["text"].as_str() {
        return Some(Cow::Borrowed(text));
    }
    let image = part.get("inlineData").or_else(|| part.get("inline_data"))?;
    let mime = image
        .get("mimeType")
        .or_else(|| image.get("mime_type"))
        .and_then(Value::as_str)
        .unwrap_or_default();
    if !mime.is_empty() && !mime.starts_with("image/") {
        return None;
    }
    let data = image["data"].as_str().unwrap_or_default();
    // 分块校验编码，避免为图片正文再分配一份解码缓冲区。
    let mut decoder = DecoderReader::new(data.as_bytes(), &IMAGE_BASE64);
    if !AGY_IMAGE_MIME_TYPES.contains(&mime) || !matches!(copy(&mut decoder, &mut sink()), Ok(1..))
    {
        tracing::warn!("AGY Messages 收到格式无效或不支持的内嵌图片");
        return None;
    }
    Some(Cow::Owned(format!("![image](data:{mime};base64,{data})")))
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
        response_text(part).map(|text| json!({"type": "text", "text": text}))
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
            } else if let Some(text) = response_text(part) {
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

#[cfg(test)]
mod tests {
    use super::{convert_request, response_text, thinking_tier};
    use serde_json::json;

    #[test]
    fn messages_prompt_hook_keeps_system_and_tool_continuation_prefix_stable() {
        let main = json!({
            "system": "固定规则",
            "messages": [
                {"role": "user", "content": "查询项目资料"},
                {"role": "system", "content": "项目环境"}
            ]
        });
        let previous = convert_request(&main).unwrap();
        assert_eq!(
            previous["systemInstruction"]["parts"],
            json!([{"text": "固定规则"}, {"text": "项目环境"}])
        );
        let context = "UserPromptSubmit hook additional context: 当前没有活跃任务。";
        for hook_content in [json!(context), json!([{"type": "text", "text": context}])] {
            let mut continuation = main.clone();
            continuation["messages"].as_array_mut().unwrap().extend([
                json!({"role": "assistant", "content": [
                    {"type": "tool_use", "id": "search", "name": "WebSearch", "input": {}},
                    {"type": "tool_use", "id": "read", "name": "Read", "input": {}}
                ]}),
                json!({"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": "read", "content": "读取结果"},
                    {"type": "tool_result", "tool_use_id": "search", "content": "搜索结果"}
                ]}),
                json!({"role": "system", "content": hook_content}),
            ]);
            let converted = convert_request(&continuation).unwrap();
            let contents = converted["contents"].as_array().unwrap();
            let prefix = previous["contents"].as_array().unwrap();
            assert_eq!(
                converted["systemInstruction"],
                previous["systemInstruction"]
            );
            assert_eq!(contents.len(), prefix.len() + 2);
            assert_eq!(&contents[..prefix.len()], prefix);
            assert_eq!(
                contents.last().unwrap(),
                &json!({"role": "user", "parts": [
                    {"functionResponse": {"id": "read", "name": "Read", "response": {"result": "读取结果"}}},
                    {"functionResponse": {"id": "search", "name": "WebSearch", "response": {"result": "搜索结果"}}},
                    {"text": context}
                ]})
            );
        }
    }

    #[test]
    fn messages_prompt_hook_follows_split_tool_results_in_history() {
        let context = "UserPromptSubmit hook additional context: 追加任务状态。";
        let request = json!({"messages": [
            {"role": "user", "content": "读取两份资料"},
            {"role": "assistant", "content": [
                {"type": "tool_use", "id": "first", "name": "Read", "input": {}},
                {"type": "tool_use", "id": "second", "name": "Read", "input": {}}
            ]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "first"}]},
            {"role": "system", "content": context},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "second"}]},
            {"role": "assistant", "content": "已读取。"},
            {"role": "user", "content": "继续。"}
        ]});
        let converted = convert_request(&request).unwrap();
        assert!(converted.get("systemInstruction").is_none());
        assert_eq!(
            converted["contents"][2]["parts"].as_array().unwrap().len(),
            1
        );
        assert_eq!(
            converted["contents"][3]["parts"][0]["functionResponse"]["id"],
            "second"
        );
        assert_eq!(converted["contents"][3]["parts"][1]["text"], context);
        assert_eq!(converted["contents"][4]["role"], "model");
    }

    #[test]
    fn messages_read_truncation_notice_keeps_its_position_across_tool_turns() {
        let notice = "[Truncated: /fixture/large.txt. Showing lines 1–200 of 420 total (24000 tokens). Read with offset=201 limit=200 for the next portion.]";
        let main = json!({
            "system": "固定规则",
            "messages": [
                {"role": "user", "content": "读取资料"},
                {"role": "system", "content": "项目环境"}
            ],
            "tools": [
                {"name": "Read", "input_schema": {"type": "object"}},
                {"name": "Bash", "input_schema": {"type": "object"}}
            ]
        });
        let previous = convert_request(&main).unwrap();
        let mut continuation = main;
        continuation["messages"].as_array_mut().unwrap().extend([
            json!({"role": "assistant", "content": [
                {"type": "tool_use", "id": "read", "name": "Read", "input": {"file_path": "/fixture/large.txt"}},
                {"type": "tool_use", "id": "check", "name": "Bash", "input": {}}
            ]}),
            json!({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "read", "content": "文件片段"},
                {"type": "tool_result", "tool_use_id": "check", "content": "检查结果"}
            ]}),
            json!({"role": "system", "content": [{"type": "text", "text": notice, "cache_control": {"type": "ephemeral"}}]}),
        ]);

        let mut unrelated = continuation.clone();
        unrelated["messages"][2]["content"][0]["name"] = json!("Bash");
        let unrelated = convert_request(&unrelated).unwrap();
        assert_eq!(unrelated["systemInstruction"]["parts"][2]["text"], notice);
        assert_eq!(
            unrelated["contents"][2]["parts"].as_array().unwrap().len(),
            2
        );

        let converted = convert_request(&continuation).unwrap();
        let contents = converted["contents"].as_array().unwrap();
        assert_eq!(
            converted["systemInstruction"],
            previous["systemInstruction"]
        );
        assert_eq!(converted["tools"], previous["tools"]);
        assert_eq!(contents.len(), 3);
        assert_eq!(contents[0], previous["contents"][0]);
        assert_eq!(
            contents[2]["parts"],
            json!([
                {"functionResponse": {"id": "read", "name": "Read", "response": {"result": "文件片段"}}},
                {"functionResponse": {"id": "check", "name": "Bash", "response": {"result": "检查结果"}}},
                {"text": notice}
            ])
        );

        continuation["messages"][4]["content"] = json!(notice);
        continuation["messages"].as_array_mut().unwrap().extend([
            json!({"role": "assistant", "content": "已读取。"}),
            json!({"role": "user", "content": "继续读取。"}),
        ]);
        let next = convert_request(&continuation).unwrap();
        assert_eq!(next["systemInstruction"], converted["systemInstruction"]);
        assert_eq!(next["tools"], converted["tools"]);
        assert_eq!(
            &next["contents"].as_array().unwrap()[..contents.len()],
            contents
        );
    }

    #[test]
    fn messages_thinking_tier_prefers_valid_manual_budget() {
        for (budget, expected) in [(1024, "low"), (1025, "medium"), (8193, "high")] {
            let request = json!({
                "thinking": {"type": "enabled", "budget_tokens": budget},
                "output_config": {"effort": "max"},
            });
            assert_eq!(thinking_tier(&request), Some(expected));
        }
        let adaptive = json!({
            "thinking": {"type": "adaptive", "display": "updates"},
            "output_config": {"effort": "max"},
        });
        assert_eq!(thinking_tier(&adaptive), Some("xhigh"));
        assert_eq!(
            thinking_tier(&json!({"output_config": {"effort": "unknown"}})),
            None
        );
        assert_eq!(thinking_tier(&json!({})), None);
    }

    #[test]
    fn image_text_preserves_large_data_and_rejects_malformed_parts() {
        // 让校验跨过解码缓冲区边界，并保留末尾无填充字节。
        let data = "YWJj".repeat(16_384) + "YQ";
        let part = json!({"inlineData": {"mimeType": "image/png", "data": data}});
        let expected = format!("![image](data:image/png;base64,{data})");
        assert_eq!(response_text(&part).as_deref(), Some(expected.as_str()));

        for (mime, data) in [
            ("image/svg+xml", "YQ=="),
            ("image/png", "YQ==)"),
            ("image/png", ""),
        ] {
            let part = json!({"inlineData": {"mimeType": mime, "data": data}});
            assert!(response_text(&part).is_none());
        }
    }
}
