//! Claude WebSearch 子请求与原生工具等候许可的归属。

use std::collections::HashMap;
use std::sync::Arc;

use axum::Json;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use reqwest::Url;
use serde::Deserialize;
use serde_json::{Value, json};
use tokio::sync::Mutex;
use tokio::time::Instant;
use uuid::Uuid;

use super::{Admission, EventReader, GeminiService, PreparedTransport, messages};
use crate::error::AppError;
use crate::model::account::Account;
use crate::model::api_token::ApiToken;
use crate::service::system_update::InferenceCutover;

const SEARCH_TOOL: &str = "web_search_20250305";
const CLAUDE_QUERY_PREFIX: &str = "Perform a web search for the query: ";
const GOOGLE_GROUNDING_REDIRECT_HOST: &str = "vertexaisearch.cloud.google.com";

/// 从单工具 Messages 请求取得搜索参数。
pub(super) struct SearchRequest {
    pub query: String,
    allowed: Vec<String>,
    blocked: Vec<String>,
}

impl SearchRequest {
    /// 识别独立搜索请求。@param body 原始 Messages。@return 搜索参数或普通请求标记。
    pub(super) fn from_messages(body: &Value) -> Result<Option<Self>, AppError> {
        let Some(tools) = body["tools"].as_array() else {
            return Ok(None);
        };
        let Some(tool) = tools.iter().find(|tool| tool["type"] == SEARCH_TOOL) else {
            return Ok(None);
        };
        if tools.len() != 1 || tool["name"] != "web_search" {
            return Err(super::invalid(
                "反重力 WebSearch 需要独立的 web_search 声明",
            ));
        }
        if tool
            .get("max_uses")
            .is_some_and(|max| max.as_u64().is_none_or(|max| max == 0))
        {
            return Err(super::invalid("WebSearch max_uses 必须为正整数"));
        }
        let user = body["messages"]
            .as_array()
            .and_then(|items| {
                items
                    .iter()
                    .rev()
                    .find(|message| message["role"] != "system")
            })
            .filter(|message| message["role"] == "user")
            .ok_or_else(|| super::invalid("WebSearch 缺少用户查询"))?;
        let content = &user["content"];
        let query = match content.as_str() {
            Some(text) => text.to_owned(),
            None => content
                .as_array()
                .and_then(|blocks| {
                    blocks
                        .iter()
                        .map(|block| {
                            (block["type"] == "text")
                                .then(|| block["text"].as_str())
                                .flatten()
                        })
                        .collect::<Option<Vec<_>>>()
                        .map(|texts| texts.join("\n"))
                })
                .ok_or_else(|| super::invalid("WebSearch 需要文本查询"))?,
        };
        let query = query.trim();
        let query = query
            .strip_prefix(CLAUDE_QUERY_PREFIX)
            .unwrap_or(query)
            .trim();
        if query.is_empty() || body["tool_choice"]["type"] == "none" {
            return Err(super::invalid("WebSearch 查询为空或调用被禁用"));
        }
        if tool.get("allowed_domains").is_some() && tool.get("blocked_domains").is_some() {
            return Err(super::invalid("WebSearch 域名只能声明一种过滤方式"));
        }
        Ok(Some(Self {
            query: query.to_owned(),
            allowed: domains(tool.get("allowed_domains"))?,
            blocked: domains(tool.get("blocked_domains"))?,
        }))
    }

    /// 将同一次工具回执封装成 Claude 支持的响应。@param model 公开模型。
    /// @param receipt 已完成的搜索。@param streaming 是否使用 SSE。@return Claude Messages 响应。
    pub(super) fn response(
        &self,
        model: &str,
        receipt: Option<&SearchReceipt>,
        streaming: bool,
    ) -> Response {
        let id = format!("srvtoolu_{}", Uuid::new_v4().simple());
        let call = json!({"type":"server_tool_use","id":id,"name":"web_search","input":{"query":self.query}});
        let has_domain_filters = !self.allowed.is_empty() || !self.blocked.is_empty();
        let content = receipt.map_or_else(
            || json!({"type":"web_search_tool_result_error","error_code":"unavailable"}),
            |receipt| {
                json!(receipt.sources.iter().filter_map(|source| {
                let url = Url::parse(&source.url).ok()?;
                let host = url.host_str()?.trim_end_matches('.');
                // 原版轨迹中的 Google 跳转只提供跳转域，无法满足针对来源域的过滤规则。
                if !matches!(url.scheme(), "http" | "https")
                    || !url.username().is_empty() || url.password().is_some()
                    || (has_domain_filters && host == GOOGLE_GROUNDING_REDIRECT_HOST)
                    || (!self.allowed.is_empty() && !includes(&self.allowed, host))
                    || includes(&self.blocked, host)
                {
                    return None;
                }
                Some(json!({"type":"web_search_result","url":source.url,"title":source.title,
                    "encrypted_content":"","page_age":null}))
            }).collect::<Vec<_>>())
            },
        );
        let result = json!({"type":"web_search_tool_result","tool_use_id":id,"content":content});
        let mut usage = receipt.map_or(json!({"input_tokens":0,"output_tokens":0}), |receipt| {
            receipt.usage.clone()
        });
        usage["server_tool_use"] = json!({"web_search_requests":u32::from(receipt.is_some())});
        let message = json!({"type":"message","id":messages::message_id(),"model":model,
            "role":"assistant","stop_reason":"end_turn","stop_sequence":null,
            "content":[call,result],"usage":usage});
        if streaming {
            messages::tool_stream(message)
        } else {
            Json(message).into_response()
        }
    }
}

fn domains(value: Option<&Value>) -> Result<Vec<String>, AppError> {
    let Some(value) = value else {
        return Ok(Vec::new());
    };
    let invalid = || super::invalid("WebSearch 域名格式无效");
    value
        .as_array()
        .ok_or_else(invalid)?
        .iter()
        .map(|value| {
            let text = value
                .as_str()
                .filter(|text| {
                    !text.is_empty()
                        && !text.contains(['/', '\\', ':', '@', '?', '#', '%', '*'])
                        && !text.chars().any(char::is_whitespace)
                })
                .ok_or_else(invalid)?;
            let url = Url::parse(&format!("https://{text}/")).map_err(|_| invalid())?;
            url.domain()
                .map(|domain| domain.trim_end_matches('.').to_owned())
                .filter(|domain| !domain.is_empty())
                .ok_or_else(invalid)
        })
        .collect()
}

fn includes(domains: &[String], host: &str) -> bool {
    domains.iter().any(|domain| {
        host == domain
            || host
                .strip_suffix(domain)
                .is_some_and(|part| part.ends_with('.'))
    })
}

/// 发送器对同一次原版搜索提供的已核验来源与 Usage。
#[derive(Clone, Deserialize)]
pub(super) struct SearchReceipt {
    sources: Vec<SearchSource>,
    usage: Value,
}

#[derive(Clone, Deserialize)]
struct SearchSource {
    url: String,
    title: String,
}

/// 仅在发送器回收搜索作业后使用结果。@param response 受信私有流。@param request_id 本次提交 ID。
/// @param account_id 选中的账号。@param deadline 原截止。@return 已核验的来源或搜索失败。
pub(super) async fn read_receipt(
    response: reqwest::Response,
    request_id: &str,
    account_id: i64,
    deadline: Instant,
) -> Option<SearchReceipt> {
    if !response.status().is_success() {
        return None;
    }
    let mut reader = EventReader {
        stream: Box::pin(response.bytes_stream()),
        pending: Vec::new(),
        deadline,
    };
    let mut receipt = None;
    while let Some(event) = reader.next().await.ok()? {
        if event["request_id"] != request_id || event["account_id"].as_i64() != Some(account_id) {
            return None;
        }
        match event["type"].as_str() {
            Some("search_result") if receipt.is_none() => {
                receipt = serde_json::from_value::<SearchReceipt>(event["result"].clone()).ok();
            }
            Some("job_finalized") if event["status"] == "completed" => return receipt,
            Some("job_finalized" | "rejected" | "search_result") => return None,
            _ => {}
        }
    }
    None
}

type Receipts = HashMap<String, Option<SearchReceipt>>;

/// 原主回合等待期间的搜索队列和按查询去重的结果。
pub(super) struct SearchTurn {
    pub session: String,
    pub active: usize,
    receipts: Arc<Mutex<Receipts>>,
}

impl SearchTurn {
    /// 为可以由 Claude 回调的工具轮保存归属。@param session 已认证的显式会话键。
    /// @param calls 原 AGY 工具调用。@return 待回填的搜索状态。
    pub(super) fn new(session: String, calls: &[Value]) -> Option<Self> {
        calls
            .iter()
            .any(|call| web_query(call).is_some())
            .then(|| Self {
                session,
                active: 0,
                receipts: Arc::default(),
            })
    }
}

fn web_query(call: &Value) -> Option<&str> {
    matches!(call["name"].as_str(), Some("WebSearch" | "web_search"))
        .then(|| call["args"]["query"].as_str().map(str::trim))
        .flatten()
}

/// 在原工具轮持有的账号和发送器上执行搜索。
pub(super) struct SearchClaim {
    service: Arc<GeminiService>,
    turn_id: String,
    pub account: Account,
    pub admission: Arc<Admission>,
    pub resolved_model: String,
    pub transport: Arc<PreparedTransport>,
    pub previous_request_id: String,
    pub deadline: Instant,
    pub cutover: Option<InferenceCutover>,
    pub receipts: Arc<Mutex<Receipts>>,
}

impl Drop for SearchClaim {
    fn drop(&mut self) {
        if let Some(search) = self
            .service
            .registry()
            .turns
            .get_mut(&self.turn_id)
            .and_then(|turn| turn.search.as_mut())
        {
            search.active -= 1;
        }
    }
}

impl GeminiService {
    /// 以令牌、显式会话和查询冻结唯一原账号。@param token 当前令牌。@param model 公开模型。
    /// @param session 已解析会话键。@param query 本次查询。@return 关联搜索许可或独立请求。
    pub(super) fn claim_search(
        self: &Arc<Self>,
        token: &ApiToken,
        model: &str,
        session: Option<&str>,
        query: &str,
    ) -> Result<Option<SearchClaim>, AppError> {
        let Some(session) = session else {
            return Ok(None);
        };
        let mut registry = self.registry();
        let scoped = registry.turns.iter_mut().filter(|(_, turn)| {
            turn.token_id == token.id
                && turn.model.requested == model
                && turn.deadline > Instant::now()
                && turn
                    .search
                    .as_ref()
                    .is_some_and(|search| search.session == session)
        });
        let mismatch = || super::invalid("WebSearch 查询缺少唯一的原工具关联");
        let mut found = None;
        let mut has_pending_search = false;
        for (id, turn) in scoped {
            has_pending_search = true;
            if turn.calls.iter().any(|call| web_query(call) == Some(query)) {
                if found.is_some() {
                    return Err(mismatch());
                }
                found = Some((id, turn));
            }
        }
        let Some((id, turn)) = found else {
            return if has_pending_search {
                Err(mismatch())
            } else {
                Ok(None)
            };
        };
        if token.blocked_account_ids().contains(&turn.account.id) || {
            let allowed = token.allowed_account_ids();
            !allowed.is_empty() && !allowed.contains(&turn.account.id)
        } {
            return Err(AppError::AgyControl(StatusCode::FORBIDDEN));
        }
        if turn.claimed
            || turn
                .cutover
                .as_ref()
                .is_some_and(InferenceCutover::is_cancelled)
        {
            return Err(AppError::AgyControl(StatusCode::CONFLICT));
        }
        let search = turn.search.as_mut().expect("已按搜索会话匹配");
        search.active += 1;
        Ok(Some(SearchClaim {
            service: self.clone(),
            turn_id: id.clone(),
            account: turn.account.clone(),
            admission: turn.admission.clone(),
            resolved_model: turn.model.resolved.clone(),
            transport: turn.transport.clone(),
            previous_request_id: turn.previous_request_id.clone(),
            deadline: turn.deadline,
            cutover: turn.cutover.clone(),
            receipts: search.receipts.clone(),
        }))
    }
}
