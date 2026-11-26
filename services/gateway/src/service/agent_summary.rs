//! Claude Code 的后台动作摘要，只描述本次请求已携带的工具动作。
use serde_json::Value;
use std::collections::BTreeMap;

pub(super) const AGENT_SUMMARY_HEADER: &str = "Describe your most recent action in 3-5 words using present tense (-ing). Name the file or function, not the branch. Do not use tools.\n";
pub(super) const AGENT_SUMMARY_EXAMPLES: &str = r#"
Good: "Reading runAgent.ts"
Good: "Fixing null check in validate.ts"
Good: "Running auth module tests"
Good: "Adding retry logic to fetchUser"

Bad (past tense): "Analyzed the branch diff"
Bad (too vague): "Investigating the issue"
Bad (too long): "Reviewing full branch diff and AgentTool.tsx integration"
Bad (branch name): "Analyzed adam/background-summary branch diff""#;

/// 核对官方模板和可选的上一条摘要。@param text 客户端完整指令。@return 是否为进度查询。
pub(super) fn is_summary_prompt(text: &str) -> bool {
    let Some(previous) = text
        .strip_prefix(AGENT_SUMMARY_HEADER)
        .and_then(|tail| tail.strip_suffix(AGENT_SUMMARY_EXAMPLES))
    else {
        return false;
    };
    previous.is_empty()
        || previous
            .strip_prefix("\nPrevious: \"")
            .and_then(|value| value.strip_suffix("\" — say something NEW.\n"))
            .is_some_and(|value| !value.is_empty() && !value.contains('\n'))
}

/// 根据最后一个工具结果生成本地摘要。@param name 工具名。@param args 原参数。@param failed 执行失败。@return 动作描述。
pub(super) fn describe_action(name: &str, args: &Value, failed: bool) -> String {
    let (action, fallback) = match (failed, name) {
        (true, _) => return "Checking a tool error".into(),
        (_, "Read") => ("Reading", "Reading a local file"),
        (_, "Edit" | "MultiEdit") => ("Editing", "Editing a local file"),
        (_, "Write") => ("Writing", "Writing a local file"),
        (_, "Bash") => return "Running a shell command".into(),
        (_, "Grep" | "Glob" | "WebSearch" | "web_search") => {
            return "Searching for matching results".into();
        }
        _ => return "Checking the tool result".into(),
    };
    let file = args["file_path"]
        .as_str()
        .and_then(|path| path.rsplit(['/', '\\']).next())
        .filter(|file| {
            !file.is_empty()
                && file.len() <= 80
                && file
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
        });
    match file {
        Some(file) => format!("{action} file {file}"),
        None => fallback.into(),
    }
}

/// 核对 Messages 的辅助查询布局及紧邻的整组回执。@param body 公开请求。@return 动作及规范工具组。
pub(super) fn messages_summary(body: &Value) -> Option<(String, Vec<&str>)> {
    let (last, history) = body["messages"].as_array()?.split_last()?;
    if last["role"] != "user" {
        return None;
    }
    let (prompt, results) = if let Some(text) = last["content"].as_str() {
        (text, &[][..])
    } else {
        let (block, rest) = last["content"].as_array()?.split_last()?;
        if block["type"] != "text" {
            return None;
        }
        (block["text"].as_str()?, rest)
    };
    if !is_summary_prompt(prompt) {
        return None;
    }
    let (results, history) = if results.is_empty() {
        let (user, history) = history.split_last()?;
        if user["role"] != "user" {
            return None;
        }
        (user["content"].as_array()?.as_slice(), history)
    } else {
        (results, history)
    };
    let previous = history.last()?;
    if previous["role"] != "assistant" {
        return None;
    }
    let mut calls = BTreeMap::new();
    for block in previous["content"]
        .as_array()?
        .iter()
        .filter(|b| b["type"] == "tool_use")
    {
        let id = block["id"].as_str().filter(|id| !id.is_empty())?;
        if calls.insert(id, block).is_some() {
            return None;
        }
    }
    if calls.len() != results.len() {
        return None;
    }
    let ids = calls.keys().copied().collect();
    let mut latest = None;
    for result in results {
        if result["type"] != "tool_result" {
            return None;
        }
        let block = calls.remove(result["tool_use_id"].as_str()?)?;
        let failed = match result.get("is_error") {
            Some(v) => v.as_bool()?,
            None => false,
        };
        latest = Some((block, failed));
    }
    let (block, failed) = latest?;
    Some((
        describe_action(block["name"].as_str()?, &block["input"], failed),
        ids,
    ))
}

#[cfg(test)]
mod tests {
    use super::{AGENT_SUMMARY_EXAMPLES, AGENT_SUMMARY_HEADER, messages_summary};
    use serde_json::json;

    /// 摘要可独立成行或接在完整的多工具结果后。普通追加文字仍属业务续轮。
    #[test]
    fn recognizes_only_complete_native_summary_batches() {
        let prompt = format!("{AGENT_SUMMARY_HEADER}{AGENT_SUMMARY_EXAMPLES}");
        let result = |id| json!({"type":"tool_result","tool_use_id":id,"content":"合成结果"});
        let text = |s: &str| json!({"type":"text","text":s});
        let mut body = json!({"messages":[
            {"role":"assistant","content":[
                {"type":"tool_use","id":"b","name":"Read","input":{"file_path":"/fixture/main.rs"}},
                {"type":"tool_use","id":"a","name":"Bash","input":{}}
            ]},
            {"role":"user","content":[result("a"),result("b"),text(&prompt)]}
        ]});
        let expected = Some(("Reading file main.rs".to_owned(), vec!["a", "b"]));
        assert_eq!(messages_summary(&body), expected);
        for content in [
            json!([result("b"), text(&prompt)]),
            json!([result("a"), result("a"), text(&prompt)]),
            json!([result("a"), result("b"), text("继续处理")]),
            json!([
                result("a"),
                result("b"),
                text("额外业务输入"),
                text(&prompt)
            ]),
        ] {
            body["messages"][1]["content"] = content;
            assert_eq!(messages_summary(&body), None);
        }
        body["messages"][1]["content"] = json!([result("a"), result("b")]);
        body["messages"]
            .as_array_mut()
            .unwrap()
            .push(json!({"role":"user","content":prompt}));
        assert_eq!(messages_summary(&body), expected);
    }
}
