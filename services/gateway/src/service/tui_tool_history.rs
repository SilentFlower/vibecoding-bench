//! 无显式会话时，只用原请求历史及真实响应登记的工具组核验续轮。

use serde::de::IgnoredAny;
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::mem::size_of;

use crate::service::request_body_codec::REQUEST_BODY_LIMIT;
use crate::service::request_session::hash_json;

pub(super) const SERVER_SESSION_PREFIX: &str = "gateway-tools-";
pub(super) const TITLE_SESSION_PREFIX: &str = "gateway-tools-title-";

/// 按最近一轮区分历史与回传。CLI 会在 user 工具回执后追加 system 上下文。
/// @param body 原始 Messages 正文。@return 末轮前的消息及末轮切片，均借用原文。
fn split_last_turn(body: &Value) -> Option<(&[Value], &[Value])> {
    let messages = body["messages"].as_array()?;
    let (last, before_last) = messages.split_last()?;
    let is_reply = |message: &Value| matches!(message["role"].as_str(), Some("user" | "system"));
    // 对非法末条保留原有的结果检测，以免把错误的工具回传认作普通新轮。
    let start = if is_reply(last) {
        before_last
            .iter()
            .rposition(|message| !is_reply(message))
            .map_or(0, |index| index + 1)
    } else {
        before_last.len()
    };
    Some(messages.split_at(start))
}

fn result_blocks(message: &Value) -> impl Iterator<Item = &Value> {
    message["content"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|block| block["type"] == "tool_result")
}

/// 取完整工具结果组。@param body 公开请求。@return 已排序的 ID 集合；无结果返回空值。
pub(super) fn result_ids(body: &Value) -> Option<BTreeSet<&str>> {
    let (_, replies) = split_last_turn(body)?;
    let mut ids = BTreeSet::new();
    for message in replies {
        for block in result_blocks(message) {
            if message["role"] != "user" || !ids.insert(nonempty(&block["tool_use_id"])?) {
                return None;
            }
        }
    }
    (!ids.is_empty()).then_some(ids)
}

/// 区分普通新轮和含非法结果的提交。@param body 公开请求。@return 末轮是否声明工具结果。
pub(super) fn has_result(body: &Value) -> bool {
    split_last_turn(body).is_some_and(|(_, replies)| {
        replies
            .iter()
            .any(|message| result_blocks(message).next().is_some())
    })
}

fn nonempty(value: &Value) -> Option<&str> {
    value.as_str().filter(|text| !text.is_empty())
}

fn digest(domain: &[u8], value: &Value) -> String {
    let mut hash = Sha256::new();
    hash.update(domain);
    hash_json(&mut hash, value, false);
    hex::encode(hash.finalize())
}

/// 提取原始 Messages 历史摘要，兼容字符串文本与同形文本块。@param history 原请求消息。@return 结构摘要。
pub(super) fn history_key(history: &[Value]) -> String {
    let mut hash = Sha256::new();
    hash.update(b"candidate-tool-history-v1");
    for source in history {
        let mut message = source.clone();
        if let Some(content) = message
            .as_object_mut()
            .and_then(|fields| fields.get_mut("content"))
        {
            if let Some(text) = source["content"].as_str() {
                *content = json!([{"type":"text","text":text}]);
            }
            if let Some(blocks) = content.as_array_mut() {
                for block in blocks {
                    if let Some(fields) = block.as_object_mut() {
                        fields.remove("cache_control");
                    }
                }
            }
        }
        hash_json(&mut hash, &message, false);
    }
    hex::encode(hash.finalize())
}

fn canonical_tools(tools: BTreeMap<String, Value>) -> String {
    digest(b"candidate-tool-declarations-v1", &json!(tools))
}

fn register(tools: &mut BTreeMap<String, Value>, block: &Value) -> Option<()> {
    let id = nonempty(&block["id"])?;
    let name = nonempty(&block["name"])?;
    let input = block["input"].as_object()?;
    tools
        .insert(id.into(), json!({"name":name,"input":input}))
        .is_none()
        .then_some(())
}

/// 读取末次工具结果前声明的工具组。@param body 公开 Messages。@return 紧邻的工具 ID 集合。
pub(super) fn preceding_tool_ids(body: &Value) -> Option<BTreeSet<&str>> {
    let (before, _) = split_last_turn(body)?;
    let assistant = before.last()?;
    if assistant["role"] != "assistant" {
        return None;
    }
    let ids = assistant["content"]
        .as_array()?
        .iter()
        .filter(|block| block["type"] == "tool_use")
        .map(|block| nonempty(&block["id"]))
        .collect::<Option<BTreeSet<_>>>()?;
    (!ids.is_empty()).then_some(ids)
}

/// 核对结果前一条 assistant 的工具声明与原历史前缀。@param body 公开请求。
/// @param ids 必须匹配的原工具结果组。@return 历史和工具声明摘要。
pub(super) fn continuation_proof(body: &Value, ids: &BTreeSet<&str>) -> Option<(String, String)> {
    let (before, _) = split_last_turn(body)?;
    let (assistant, history) = before.split_last()?;
    if assistant["role"] != "assistant" {
        return None;
    }
    let mut tools = BTreeMap::new();
    for block in assistant["content"]
        .as_array()?
        .iter()
        .filter(|block| block["type"] == "tool_use")
    {
        register(&mut tools, block)?;
    }
    if tools.keys().map(String::as_str).collect::<BTreeSet<_>>() != *ids {
        return None;
    }
    Some((history_key(history), canonical_tools(tools)))
}

struct Declaration {
    name: Box<str>,
    input: String,
    has_deltas: bool,
}

impl Declaration {
    fn from_block(block: &Value) -> Option<Self> {
        let name = nonempty(&block["name"])?;
        let input = match block["input"].as_object() {
            Some(input) => serde_json::to_string(input).ok()?,
            None => String::new(),
        };
        Some(Self {
            name: name.into(),
            input,
            has_deltas: false,
        })
    }

    fn retained_bytes(&self) -> usize {
        self.name.len() + self.input.capacity()
    }
}

// 每项固定记账覆盖映射节点、键和值。参数、名称和 ID 的缓冲另行记账。
const TOOL_ENTRY_BYTES: usize =
    2 * (size_of::<(u64, Box<str>, Declaration)>() + size_of::<(Box<str>, Option<Declaration>)>());

/// 单个响应共享候选工具观察预算。普通正文继续由原解码器按事件处理。
pub(super) struct ResponseTools {
    with_declarations: bool,
    retained_bytes: usize,
    pending: BTreeMap<u64, (Box<str>, Declaration)>,
    tools: BTreeMap<Box<str>, Option<Declaration>>,
}

impl ResponseTools {
    /// 建立一次工具观察。@param with_declarations 是否需要完整声明校验。@return 单响应观察器。
    pub(super) fn new(with_declarations: bool) -> Self {
        Self {
            with_declarations,
            retained_bytes: 0,
            pending: BTreeMap::new(),
            tools: BTreeMap::new(),
        }
    }

    /// 记录一个解码事件。@param event 上游响应事件或 JSON 消息。@return 观察有效性，失效时调用方释放整组。
    pub(super) fn observe(&mut self, event: &Value) -> Option<()> {
        match event["type"].as_str() {
            Some("message") => {
                for block in event["content"]
                    .as_array()?
                    .iter()
                    .filter(|block| block["type"] == "tool_use")
                {
                    self.record_whole(block)?;
                }
            }
            Some("content_block_start") if event["content_block"]["type"] == "tool_use" => {
                let block = &event["content_block"];
                if self.with_declarations {
                    let index = event["index"].as_u64()?;
                    let id = nonempty(&block["id"])?;
                    let declaration = Declaration::from_block(block)?;
                    self.charge(id, Some(&declaration))?;
                    if self
                        .pending
                        .insert(index, (id.into(), declaration))
                        .is_some()
                    {
                        return None;
                    }
                } else {
                    self.record_whole(block)?;
                }
            }
            Some("content_block_delta")
                if self.with_declarations && event["delta"]["type"] == "input_json_delta" =>
            {
                if let Some((_, declaration)) = self.pending.get_mut(&event["index"].as_u64()?) {
                    let piece = event["delta"]["partial_json"].as_str()?;
                    if !piece.is_empty() {
                        if !declaration.has_deltas {
                            // 增量参数是完整参数的来源，首段到达就释放起始占位。
                            self.retained_bytes -= declaration.input.capacity();
                            declaration.input = String::new();
                            declaration.has_deltas = true;
                        }
                        let input = &mut declaration.input;
                        let old_capacity = input.capacity();
                        let needed = input.len().checked_add(piece.len())?;
                        if needed > old_capacity {
                            let max_capacity =
                                old_capacity + REQUEST_BODY_LIMIT - self.retained_bytes;
                            if needed > max_capacity {
                                return None;
                            }
                            let capacity = needed.max(old_capacity * 2).min(max_capacity);
                            input.try_reserve_exact(capacity - input.len()).ok()?;
                            self.retained_bytes += input.capacity() - old_capacity;
                            if self.retained_bytes > REQUEST_BODY_LIMIT {
                                return None;
                            }
                        }
                        input.push_str(piece);
                    }
                }
            }
            Some("content_block_stop") if self.with_declarations => {
                if let Some((id, declaration)) = self.pending.remove(&event["index"].as_u64()?) {
                    // 只验证参数的 JSON 结构。完整参数保持为紧凑字符串，完成时逐项计算旧格式摘要。
                    if !declaration.input.trim_start().starts_with('{')
                        || serde_json::from_str::<IgnoredAny>(&declaration.input).is_err()
                        || self.tools.insert(id, Some(declaration)).is_some()
                    {
                        return None;
                    }
                }
            }
            _ => {}
        }
        Some(())
    }

    fn record_whole(&mut self, block: &Value) -> Option<()> {
        let id = nonempty(&block["id"])?;
        if self.tools.contains_key(id) {
            return (!self.with_declarations).then_some(());
        }
        let declaration = if self.with_declarations {
            block["input"].as_object()?;
            Some(Declaration::from_block(block)?)
        } else {
            None
        };
        self.charge(id, declaration.as_ref())?;
        self.tools.insert(id.into(), declaration);
        Some(())
    }

    fn charge(&mut self, id: &str, declaration: Option<&Declaration>) -> Option<()> {
        let bytes =
            TOOL_ENTRY_BYTES + id.len() + declaration.map_or(0, Declaration::retained_bytes);
        let total = self.retained_bytes.checked_add(bytes)?;
        if total > REQUEST_BODY_LIMIT {
            return None;
        }
        self.retained_bytes = total;
        Some(())
    }

    /// 判断公开响应已经开始交付工具。@return 有已观察的工具事件时为真。
    pub(super) fn started(&self) -> bool {
        !self.pending.is_empty() || !self.tools.is_empty()
    }

    /// 完成后释放工具参数并返回原格式摘要。@return 可信 ID 与可选声明摘要。
    pub(super) fn complete(self) -> Option<(Vec<String>, Option<String>)> {
        if !self.pending.is_empty() {
            return None;
        }
        let mut ids = Vec::with_capacity(self.tools.len());
        let mut hash = Sha256::new();
        hash.update(b"candidate-tool-declarations-v1{");
        for (id, declaration) in self.tools {
            if let Some(Declaration { name, input, .. }) = declaration {
                let arguments = serde_json::from_str(&input).ok()?;
                drop(input);
                let mut block = Map::new();
                block.insert("name".into(), Value::String(name.into()));
                block.insert("input".into(), arguments);
                // 与 hash_json 的对象键编码相同，保留此前已登记的声明摘要。
                hash.update(b"k");
                hash.update((id.len() as u64).to_be_bytes());
                hash.update(id.as_bytes());
                hash_json(&mut hash, &Value::Object(block), false);
            }
            ids.push(id.into());
        }
        hash.update(b"}");
        Some((
            ids,
            self.with_declarations.then(|| hex::encode(hash.finalize())),
        ))
    }
}

#[cfg(test)]
mod followup_shape_tests {
    use super::{continuation_proof, has_result, history_key, preceding_tool_ids, result_ids};
    use serde_json::json;
    use std::collections::BTreeSet;

    /// 真实 CC 可以在工具结果后追加 system 文本，同时保留首轮历史中的 system。
    #[test]
    fn trailing_context_preserves_original_tool_turn() {
        let initial = vec![
            json!({"role":"user","content":"读取文件"}),
            json!({"role":"system","content":[{"type":"text","text":"原始上下文"}]}),
        ];
        let assistant = json!({"role":"assistant","content":[
            {"type":"thinking","thinking":"思考","signature":"已签名"},
            {"type":"tool_use","id":"tool_1","name":"Read","input":{"file_path":"sample"}},
            {"type":"tool_use","id":"tool_2","name":"Read","input":{"file_path":"sample2"}}]});
        let first = json!({"role":"user","content":[{"type":"tool_result","tool_use_id":"tool_1","content":"一"}]});
        let second = json!({"role":"user","content":[{"type":"tool_result","tool_use_id":"tool_2","content":"二"}]});
        let system = json!({"role":"system","content":[{"type":"text","text":"本轮上下文"}]});
        let mut messages = initial.clone();
        messages.extend([assistant, first.clone(), second, system.clone()]);
        let body = json!({"messages":messages});
        let ids = BTreeSet::from(["tool_1", "tool_2"]);
        assert!(has_result(&body));
        assert_eq!(result_ids(&body), Some(ids.clone()));
        assert_eq!(preceding_tool_ids(&body), Some(ids.clone()));
        assert_eq!(
            continuation_proof(&body, &ids).unwrap().0,
            history_key(&initial)
        );

        let mut duplicate = messages.clone();
        duplicate.extend([first, system.clone()]);
        assert!(result_ids(&json!({"messages":duplicate})).is_none());
        messages.extend([
            json!({"role":"assistant","content":"已完成"}),
            json!({"role":"user","content":"新问题"}),
            system,
        ]);
        assert!(!has_result(&json!({"messages":messages})));
    }
}
