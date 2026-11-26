//! 账号的公开工具轮凭证由实际转发的响应登记。

use axum::body::Body;
use axum::response::Response;
use futures_util::stream::unfold;
use http_body::Body as HttpBody;
use http_body_util::{BodyExt, StreamBody};
use serde_json::Value;
use sha2::{Digest, Sha256};
use sqlx::{AnyPool, Row};
use std::collections::BTreeSet;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, OnceLock};
use tokio::runtime::Handle;
use tracing::warn;
use uuid::Uuid;

use crate::error::AppError;
use crate::service::request_session::valid_id;
use crate::service::system_update::InferenceCutover;
use crate::service::tui_tool_history::{
    SERVER_SESSION_PREFIX, continuation_proof, has_result, history_key, preceding_tool_ids,
    result_ids,
};
use crate::service::usage::UsageCapture;
use crate::service::v3_scheduling::now_ms;
use crate::store::scheduling_store::BINDING_TTL_MS;

pub(super) const TUI_V2_RECEIPT_VERSION: &str = "tui-v2:2.1.293:1";
const BACKGROUND_AGENT_LIMIT: usize = 1024;
const RECEIPT_MISMATCH: &str = "工具回执与登记轮次不符，请使用原入口令牌、原会话和完整工具组继续";
const RECEIPT_COMPLETE: &str = "该工具组的回执已处理，请从上一条响应继续";
const RECEIPT_ORPHANED: &str = "原 V2 工具会话已退出，无法继续本组回执，请开启新会话";
const ORPHANED_WAITING: &str = "tui-v2:orphan:waiting";
const ORPHANED_UNKNOWN: &str = "tui-v2:orphan:delivery_unknown";

const UNDELIVERED: &str = "tui-v2:reply:unacknowledged";

/// 真实模型已结束和客户端已读取终帧是两个独立边界。
pub(super) struct Delivery {
    pool: AnyPool,
    id: String,
    marker: String,
    open: String,
    next_tools: OnceLock<String>,
    pub(super) verified: AtomicBool,
}

impl Delivery {
    /// 续轮已经产生下一组工具时核对它仍在等待客户端。@return 是否仍可重交此次回复。
    pub(super) async fn replayable(&self) -> Result<bool, AppError> {
        let Some(group) = self.next_tools.get() else {
            return Ok(true);
        };
        let waiting = sqlx::query_scalar::<_, i64>(
            "SELECT COUNT(*) FROM tui_native_turns WHERE id=$1 AND tools=$2 AND version=$3",
        )
        .bind(&self.id)
        .bind(group)
        .bind(TUI_V2_RECEIPT_VERSION)
        .fetch_one(&self.pool)
        .await?;
        Ok(waiting == 1)
    }

    /// 按原步骤 ID 核销仅等待交付的终态。@return 对账结果。
    pub(super) async fn acknowledge(&self) -> Result<(), AppError> {
        if self.next_tools.get().is_some() {
            return Ok(());
        }
        sqlx::query(
            "UPDATE tui_native_turns SET version=$1 WHERE id=$2 AND version=$3 AND tools=$4",
        )
        .bind(TUI_V2_RECEIPT_VERSION)
        .bind(&self.id)
        .bind(UNDELIVERED)
        .bind(&self.marker)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    /// 管理取消后终止原回执的再次生成资格。@return 条件更新结果。
    pub(super) async fn cancel(&self) -> Result<(), AppError> {
        sqlx::query("UPDATE tui_native_turns SET version=$1,tools=$2 WHERE id=$3 AND (tools=$4 OR (version=$5 AND tools=$2))")
            .bind(TUI_V2_RECEIPT_VERSION).bind(&self.marker).bind(&self.id).bind(&self.open).bind(UNDELIVERED)
            .execute(&self.pool).await?;
        Ok(())
    }
}

/// 一次已登记的公开请求。提交未知时保留原记录供对账。
pub(super) struct NativeTurn {
    pool: AnyPool,
    id: String,
    previous_tools: Option<String>,
    background_agents: Vec<String>,
    stateless_history: Option<String>,
    session_id: String,
    pub(super) binding: String,
    submitted: AtomicBool,
    released: bool,
    remember_receipt: bool,
    recovery: Option<ReceiptRow>,
    delivery: Option<Arc<Delivery>>,
}

/// 核对是否仍有等待工具、执行中或提交未知的 V1 轮。@param pool 数据库。@param account 账号。@return 是否阻止切换。
pub(super) async fn occupied(pool: AnyPool, account: i64) -> Result<bool, AppError> {
    let open =
        // 旧版本没有登记主体的已终结工具轮无法授权；只把未知执行保留为排空阻塞。
        sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM tui_native_turns WHERE account_id=$1 AND tools NOT LIKE '#%' AND (principal_id<>0 OR tools='')")
            .bind(account)
            .fetch_one(&pool)
            .await?;
    Ok(open != 0)
}

/// 判断迁移是否仍需保留本账号的 V2 原进程。@param pool 数据库。@param account 账号。@return 有待回执或未知提交。
pub(super) async fn occupied_v2(pool: AnyPool, account: i64) -> Result<bool, AppError> {
    let open = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*) FROM tui_native_turns WHERE account_id=$1 AND version=$2 AND tools NOT LIKE '#%'",
    )
    .bind(account)
    .bind(TUI_V2_RECEIPT_VERSION)
    .fetch_one(&pool)
    .await?;
    Ok(open != 0)
}

/// 查询已交付工具或正在接收工具结果的 V2 轮。@param pool 网关数据库。@return 是否仍需保留原连接。
pub(super) async fn awaiting_v2_tools(pool: AnyPool) -> Result<bool, AppError> {
    let found = sqlx::query_scalar::<_, i64>(
        "SELECT CAST(1 AS BIGINT) FROM tui_native_turns WHERE version=$1 AND tools<>'' AND tools NOT LIKE '#%' LIMIT 1",
    )
    .bind(TUI_V2_RECEIPT_VERSION)
    .fetch_optional(&pool)
    .await?;
    Ok(found.is_some())
}

/// 逐条冻结原回执身份，原工具组只在服务内参与对账。
#[derive(sqlx::FromRow)]
pub(super) struct ReceiptRow {
    pub(super) id: String,
    pub(super) account_id: i64,
    principal_id: i64,
    session_id: String,
    pub(super) binding: String,
    version: String,
    tools: String,
    stateless: i64,
}

const RECEIPT_COLUMNS: &str =
    "t.id,t.account_id,t.principal_id,t.session_id,t.binding,t.version,t.tools,
    CAST(CASE WHEN p.turn_id IS NULL THEN 0 ELSE 1 END AS BIGINT) AS stateless";

impl ReceiptRow {
    /// 生成原记录的比较凭据。@return 当前阶段与归属的摘要。
    pub(super) fn revision(&self) -> String {
        let (group, claimed) = if let Some(unknown) = self.recovered() {
            let digest = self.tools.get(22..).unwrap_or("").to_owned();
            let claimed = unknown && digest != tool_digest("");
            (digest, claimed)
        } else {
            (
                tool_digest(self.tools.strip_prefix('!').unwrap_or(&self.tools)),
                self.tools.starts_with('!'),
            )
        };
        let mut hash = Sha256::new();
        for field in [&self.id, &self.binding, &self.session_id, &group] {
            hash.update((field.len() as u64).to_be_bytes());
            hash.update(field);
        }
        hash.update(self.account_id.to_be_bytes());
        hash.update(self.principal_id.to_be_bytes());
        hash.update(self.stateless.to_be_bytes());
        hash.update([u8::from(claimed)]);
        format!("{:x}", hash.finalize())
    }

    /// 读取已恢复结果。@return 确认退出时是否存在未知投递。
    pub(super) fn recovered(&self) -> Option<bool> {
        match self.version.as_str() {
            ORPHANED_WAITING => Some(false),
            ORPHANED_UNKNOWN => Some(true),
            _ => None,
        }
    }

    /// 读取 sender 中使用的账号内会话身份。@return 原主体和精确的传输会话。
    pub(super) fn sender_identity(&self) -> (i64, String) {
        let session = if self.stateless == 0 {
            self.session_id.clone()
        } else {
            format!("{SERVER_SESSION_PREFIX}{}", self.session_id)
        };
        (self.principal_id, session)
    }

    /// 核对当前回执可进入恢复过程。@return 是否仍登记在 V2 原轮。
    pub(super) fn is_open(&self) -> bool {
        self.version == TUI_V2_RECEIPT_VERSION && !self.tools.starts_with('#')
    }

    /// 原领用已开始或未知提交，终态需保留相应结论。@return 是否可能有过派发。
    pub(super) fn delivery_unknown(&self) -> bool {
        self.tools.is_empty() || self.tools.starts_with('!')
    }
}

/// 分页读取待核对的 V2 轮。@param pool 数据库。@param after 上页的末条标识。
/// @param limit 读取条数。@return 原记录。
pub(super) async fn receipt_page(
    pool: &AnyPool,
    after: &str,
    limit: i64,
) -> Result<Vec<ReceiptRow>, AppError> {
    Ok(sqlx::query_as(&format!(
        "SELECT {RECEIPT_COLUMNS} FROM tui_native_turns t
         LEFT JOIN tui_stateless_turn_proofs p ON p.turn_id=t.id
         WHERE t.version=$1 AND t.tools NOT LIKE '#%' AND t.id>$2 ORDER BY t.id LIMIT $3"
    ))
    .bind(TUI_V2_RECEIPT_VERSION)
    .bind(after)
    .bind(limit)
    .fetch_all(pool)
    .await?)
}

/// 读取指定账号的精确记录。@param pool 数据库。@param account 账号。@param id 原记录。
/// @return 原轮或保留的恢复结果。
pub(super) async fn receipt_row(
    pool: &AnyPool,
    account: i64,
    id: &str,
) -> Result<Option<ReceiptRow>, AppError> {
    Ok(sqlx::query_as(&format!(
        "SELECT {RECEIPT_COLUMNS} FROM tui_native_turns t
         LEFT JOIN tui_stateless_turn_proofs p ON p.turn_id=t.id
         WHERE t.account_id=$1 AND t.id=$2"
    ))
    .bind(account)
    .bind(id)
    .fetch_optional(pool)
    .await?)
}

/// 在原 sender 已证实退出后收口原回执。@param pool 数据库。@param row 核对过的原记录。
/// @return 是否成功保留防重放终态。
pub(super) async fn retire_orphan(pool: &AnyPool, row: &ReceiptRow) -> Result<bool, AppError> {
    let group = row.tools.strip_prefix('!').unwrap_or(&row.tools);
    let until = now_ms().saturating_add(BINDING_TTL_MS);
    let separator = if row.stateless == 0 { 'E' } else { ':' };
    let marker = format!("#{until:020}{separator}{}", tool_digest(group));
    let version = if row.delivery_unknown() {
        ORPHANED_UNKNOWN
    } else {
        ORPHANED_WAITING
    };
    // 旧网关继续按固定位置识别期限和工具组摘要。条件写入与正常认领共用同一阶段字段。
    let changed = sqlx::query(
        "UPDATE tui_native_turns SET tools=$1,version=$2 WHERE id=$3 AND account_id=$4 AND principal_id=$5
         AND session_id=$6 AND binding=$7 AND version=$8 AND tools=$9",
    )
    .bind(marker).bind(version).bind(&row.id).bind(row.account_id).bind(row.principal_id)
    .bind(&row.session_id).bind(&row.binding).bind(TUI_V2_RECEIPT_VERSION).bind(&row.tools)
    .execute(pool).await?;
    Ok(changed.rows_affected() == 1)
}

/// 回收已过会话闲置时限的终态摘要。@param pool 账号数据库。@return 清理结果。
pub(super) async fn prune_terminal(pool: AnyPool) -> Result<(), AppError> {
    sqlx::query("DELETE FROM tui_native_turns WHERE tools LIKE '#%' AND substr(tools,2,20)<=$1")
        .bind(format!("{:020}", now_ms()))
        .execute(&pool)
        .await?;
    Ok(())
}

/// 将候选 Agent 留在同主体、同会话已登记的 V2 账号，源端仍须证明具体工具。
/// @param pool 账号数据库。@param principal 已认证主体。@param session 显式客户端会话。
/// @param hint 官方 Agent 线索，仅用于查找已经收口的后台回执。
/// @return 活动 V2 账号，多个不同账号时拒绝歧义。
pub(super) async fn active_agent_account(
    pool: AnyPool,
    principal: i64,
    session: &str,
    hint: &str,
) -> Result<Option<i64>, AppError> {
    let recorded = sqlx::query_scalar::<_, i64>(
        "SELECT DISTINCT account_id FROM tui_native_turns
         WHERE principal_id=$1 AND session_id=$2 AND version=$3
         AND tools LIKE '#%' AND substr(tools,2,20)>$4 AND substr(tools,22)=$5 LIMIT 2",
    )
    .bind(principal)
    .bind(session)
    .bind(TUI_V2_RECEIPT_VERSION)
    .bind(format!("{:020}", now_ms()))
    .bind(format!("A{}", tool_digest(hint)))
    .fetch_all(&pool)
    .await?;
    let accounts = if recorded.is_empty() {
        sqlx::query_scalar::<_, i64>(
            "SELECT DISTINCT account_id FROM tui_native_turns
         WHERE principal_id=$1 AND session_id=$2 AND version=$3 AND tools NOT LIKE '#%' LIMIT 2",
        )
        .bind(principal)
        .bind(session)
        .bind(TUI_V2_RECEIPT_VERSION)
        .fetch_all(&pool)
        .await?
    } else {
        recorded
    };
    match accounts.as_slice() {
        [] => Ok(None),
        [account] => Ok(Some(*account)),
        _ => Err(AppError::BadRequest(
            "V2 子代理的原会话账号归属有歧义".into(),
        )),
    }
}

fn tool_digest(tools: &str) -> String {
    format!("{:x}", Sha256::digest(tools.as_bytes()))
}

fn background_agent_hashes(body: &Value) -> Vec<String> {
    let Some(rows) = body["messages"].as_array() else {
        return Vec::new();
    };
    let tail = rows
        .iter()
        .rev()
        .take_while(|row| matches!(row["role"].as_str(), Some("user" | "system")))
        .count();
    let Some(assistant_index) = rows.len().checked_sub(tail + 1) else {
        return Vec::new();
    };
    let assistant = &rows[assistant_index];
    if assistant["role"] != "assistant" {
        return Vec::new();
    }
    let tool_ids: BTreeSet<_> = assistant["content"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|block| {
            block["type"] == "tool_use" && matches!(block["name"].as_str(), Some("Agent" | "Task"))
        })
        .filter_map(|block| block["id"].as_str())
        .collect();
    let mut agents = BTreeSet::new();
    for receipt in rows[rows.len() - tail..]
        .iter()
        .filter(|row| row["role"] == "user")
        .filter_map(|row| row["content"].as_array())
        .flatten()
        .filter(|block| {
            block["type"] == "tool_result"
                && matches!(block.get("is_error"), None | Some(Value::Bool(false)))
        })
    {
        if !receipt["tool_use_id"]
            .as_str()
            .is_some_and(|id| tool_ids.contains(id))
        {
            continue;
        }
        let prefix = "Async agent launched successfully.";
        let content = &receipt["content"];
        let text = match content.as_array().map(Vec::as_slice) {
            Some([first, rest @ ..])
                if first["type"] == "text"
                    && rest.iter().all(|block| {
                        block["type"] == "text"
                            && block["text"]
                                .as_str()
                                .is_some_and(|text| !text.starts_with(prefix))
                    }) =>
            {
                first["text"].as_str()
            }
            _ => content.as_str(),
        };
        let Some((heading, tail)) = text.and_then(|text| text.split_once('\n')) else {
            continue;
        };
        if heading.split(" (").next() != Some(prefix) {
            continue;
        }
        let id = tail.split('\n').next().and_then(|line| {
            line.strip_prefix("agentId: ")?
                .split_once(" (internal ID")
                .map(|(id, _)| id)
        });
        if let Some(id) =
            id.filter(|id| valid_id(id) && id.bytes().all(|byte| byte.is_ascii_alphanumeric()))
        {
            agents.insert(tool_digest(id));
            if agents.len() > BACKGROUND_AGENT_LIMIT {
                break;
            }
        }
    }
    agents.into_iter().take(BACKGROUND_AGENT_LIMIT).collect()
}

/// 查询待拒绝的历史回执。@param pool 网关数据库。@param tools 规范工具组。
/// @param owner 已验证的候选归属。@return 匹配回执的安全续接提示。
async fn terminal_receipt(
    pool: &AnyPool,
    tools: &str,
    owner: Option<(i64, Option<&str>)>,
) -> Result<Option<&'static str>, AppError> {
    let found = sqlx::query_scalar::<_, i64>(
        "SELECT CAST(CASE WHEN version IN ($6,$7) THEN 1 ELSE 0 END AS BIGINT)
         FROM tui_native_turns WHERE tools LIKE '#%'
         AND substr(tools,2,20)>$1 AND substr(tools,23)=$2
         AND substr(tools,22,1)<>'A'
         AND principal_id=COALESCE($3,principal_id) AND session_id=COALESCE($4,session_id)
         AND ($5=0 OR substr(tools,22,1)<>'E') ORDER BY 1 DESC LIMIT 1",
    )
    .bind(format!("{:020}", now_ms()))
    .bind(tool_digest(tools))
    .bind(owner.map(|(principal, _)| principal))
    .bind(owner.and_then(|(_, session)| session))
    // 已核验的无头候选只排除明确属于显式会话的终态。旧记录和无头重放仍保守拒绝。
    .bind(i64::from(matches!(owner, Some((_, None)))))
    .bind(ORPHANED_WAITING)
    .bind(ORPHANED_UNKNOWN)
    .fetch_optional(pool)
    .await?;
    Ok(found.map(|orphaned| {
        if orphaned == 1 {
            RECEIPT_ORPHANED
        } else {
            RECEIPT_COMPLETE
        }
    }))
}

async fn has_registered_group(
    pool: &AnyPool,
    tools: &str,
    declarations: &str,
) -> Result<bool, AppError> {
    let known = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*) FROM tui_native_turns t
         LEFT JOIN tui_stateless_turn_proofs p ON p.turn_id=t.id
         WHERE t.tools=$1 OR t.tools=$2 OR ($3<>'' AND p.declarations=$3)",
    )
    .bind(tools)
    .bind(format!("!{tools}"))
    .bind(declarations)
    .fetch_one(pool)
    .await?;
    Ok(known != 0)
}

/// 只读定位进度摘要所属的原 V2 工具组。@param pool 数据库。@param principal 主体。
/// @param session 显式会话。@param ids 排序后的完整工具组。@return 唯一原账号。
pub(super) async fn summary_account(
    pool: &AnyPool,
    principal: i64,
    session: &str,
    ids: &[&str],
) -> Result<Option<i64>, AppError> {
    let tools = serde_json::to_string(ids).expect("纯字符串集合可编码");
    // 消费中的组保留 ! 前缀，完成后转为有期限的摘要。三个阶段都只读。
    let rows = sqlx::query_scalar::<_, i64>(
        "SELECT DISTINCT t.account_id FROM tui_native_turns t JOIN accounts a ON a.id=t.account_id
         WHERE t.principal_id=$1 AND t.session_id=$2 AND t.version=$3 AND a.request_backend=$4
         AND a.platform='claude_code' AND a.status='active'
         AND NOT EXISTS (SELECT 1 FROM tui_stateless_turn_proofs p WHERE p.turn_id=t.id)
         AND (t.tools=$5 OR t.tools=$6 OR (t.tools LIKE '#%' AND substr(t.tools,22,1)='E'
              AND substr(t.tools,2,20)>$7 AND substr(t.tools,23)=$8)) LIMIT 2",
    )
    .bind(principal)
    .bind(session)
    .bind(TUI_V2_RECEIPT_VERSION)
    .bind(super::tui_backend::TUI_V2)
    .bind(&tools)
    .bind(format!("!{tools}"))
    .bind(format!("{:020}", now_ms()))
    .bind(tool_digest(&tools))
    .fetch_all(pool)
    .await?;
    Ok(match rows.as_slice() {
        [account] => Some(*account),
        _ => None,
    })
}

/// 从登记定位原账号，供调度过滤。@param pool 数据库。@param owner 已认证主体与可选会话。
/// @param body 公开 Messages。@return 原账号；发送前仍需核对权限、版本、代次并认领。
pub(super) async fn continuation_account(
    pool: AnyPool,
    owner: (i64, Option<&str>),
    body: &Value,
) -> Result<Option<i64>, AppError> {
    if !has_result(body) {
        return Ok(None);
    }
    let returned = result_ids(body);
    let rejected = || AppError::BadRequest(RECEIPT_MISMATCH.into());
    if let Some(declared) = preceding_tool_ids(body)
        && returned.as_ref() != Some(&declared)
    {
        // 部分或重复回传也不能使已登记的整组工具走普通 V1 历史导入。
        for group in [Some(&declared), returned.as_ref()].into_iter().flatten() {
            let tools = serde_json::to_string(group).expect("纯字符串集合可编码");
            if terminal_receipt(&pool, &tools, None).await?.is_some()
                || has_registered_group(&pool, &tools, "").await?
            {
                return Err(rejected());
            }
        }
    }
    let Some(ids) = returned else {
        return Ok(None);
    };
    let (principal, explicit) = owner;
    let tools = serde_json::to_string(&ids).expect("纯字符串集合可编码");
    let claimed = format!("!{tools}");
    let proof = continuation_proof(body, &ids);
    let declarations = proof.as_ref().map_or("", |(_, declarations)| declarations);
    let candidates = sqlx::query(
        "SELECT t.account_id, p.history, p.declarations
         FROM tui_native_turns t LEFT JOIN tui_stateless_turn_proofs p ON p.turn_id=t.id
         WHERE t.principal_id=$1 AND (t.tools=$2 OR t.tools=$3 OR ($4<>'' AND p.declarations=$4))
         AND (($5='' AND p.turn_id IS NOT NULL) OR ($5<>'' AND t.session_id=$5 AND p.turn_id IS NULL))
         LIMIT 2",
    )
    .bind(principal)
    .bind(&tools)
    .bind(&claimed)
    .bind(declarations)
    .bind(explicit.unwrap_or(""))
    .fetch_all(&pool)
    .await?;
    if let Some(message) =
        terminal_receipt(&pool, &tools, (!candidates.is_empty()).then_some(owner)).await?
    {
        return Err(AppError::BadRequest(message.into()));
    }
    match candidates.as_slice() {
        [] => {
            // 已有归属的工具不能因为换头或换令牌而落回普通选号。
            if has_registered_group(&pool, &tools, declarations).await? {
                return Err(rejected());
            }
            Ok(None)
        }
        [row] => {
            if explicit.is_none() {
                let (history, declarations) = proof.ok_or_else(rejected)?;
                if row.try_get::<String, _>("history")? != history
                    || row.try_get::<String, _>("declarations")? != declarations
                {
                    return Err(rejected());
                }
            }
            Ok(Some(row.try_get("account_id")?))
        }
        _ => Err(AppError::ServiceUnavailable("工具组归属有歧义".into())),
    }
}

/// 仅定位提交未决或有退出记录的 V2 步骤。@param pool 归属库。@param principal 原令牌。
/// @param session 外部会话。@param body 完整回执。@return 仍须由原发送器出具证明的候选。
pub(super) async fn recovery_row(
    pool: &AnyPool,
    principal: i64,
    session: Option<&str>,
    body: &Value,
) -> Result<Option<ReceiptRow>, AppError> {
    let Some(ids) = result_ids(body) else {
        return Ok(None);
    };
    if preceding_tool_ids(body).as_ref() != Some(&ids) {
        return Ok(None);
    }
    let tools = serde_json::to_string(&ids).expect("纯字符串集合可编码");
    let query = format!(
        "SELECT {RECEIPT_COLUMNS} FROM tui_native_turns t
         LEFT JOIN tui_stateless_turn_proofs p ON p.turn_id=t.id WHERE t.principal_id=$1
         AND ((t.version=$2 AND t.tools=$3) OR (t.version IN ($4,$5,$11) AND t.tools LIKE '#%'
             AND substr(t.tools,2,20)>$6 AND substr(t.tools,23)=$7))
         AND ((p.turn_id IS NULL AND $8<>'' AND t.session_id=$8)
             OR (p.turn_id IS NOT NULL AND $8='' AND p.history=$9 AND p.declarations=$10)) LIMIT 2"
    );
    let candidates = sqlx::query_as::<_, ReceiptRow>(&query)
        .bind(principal)
        .bind(TUI_V2_RECEIPT_VERSION)
        .bind(format!("!{tools}"))
        .bind(ORPHANED_WAITING)
        .bind(ORPHANED_UNKNOWN)
        .bind(format!("{:020}", now_ms()))
        .bind(tool_digest(&tools))
        .bind(session.unwrap_or(""));
    let (history, declarations) = continuation_proof(body, &ids).unwrap_or_default();
    let mut rows = candidates
        .bind(history)
        .bind(declarations)
        .bind(UNDELIVERED)
        .fetch_all(pool)
        .await?;
    if rows.len() > 1 {
        return Err(AppError::BadRequest(RECEIPT_MISMATCH.into()));
    }
    Ok(rows.pop())
}

impl ReceiptRow {
    /// 在原路由锁内生成只读预留。@param pool 数据库。@param account 原账号。@param binding 当前绑定。
    /// @param owner 当前主体与会话。@param body 已匹配的数据。@return 等待源端证明的预留。
    pub(super) fn pending(
        self,
        pool: AnyPool,
        account: i64,
        binding: &str,
        owner: (i64, Option<&str>),
        body: &Value,
    ) -> Result<NativeTurn, AppError> {
        if self.account_id != account
            || self.binding != binding
            || self.principal_id != owner.0
            || (self.stateless == 0 && owner.1 != Some(self.session_id.as_str()))
        {
            return Err(AppError::BadRequest(RECEIPT_MISMATCH.into()));
        }
        let ids = result_ids(body).ok_or_else(|| AppError::BadRequest(RECEIPT_MISMATCH.into()))?;
        Ok(NativeTurn {
            pool,
            id: Uuid::new_v4().to_string(),
            previous_tools: Some(serde_json::to_string(&ids).unwrap()),
            background_agents: if self.stateless == 0 {
                background_agent_hashes(body)
            } else {
                Vec::new()
            },
            stateless_history: if self.stateless != 0 {
                body["messages"].as_array().map(|m| history_key(m))
            } else {
                None
            },
            session_id: self.session_id.clone(),
            binding: self.binding.clone(),
            submitted: AtomicBool::new(false),
            released: false,
            remember_receipt: true,
            recovery: Some(self),
            delivery: None,
        })
    }
}

/// 认领受信的已交付工具组或登记新请求。调用方已持原账号配置锁。
/// @param pool 数据库。@param account 账号。@param owner 真实主体与可选的客户端会话。@param version 已核验的执行合同。
/// @param body 公开 Messages。@param binding 已核验代次。@param draining 是否只允许旧轮。
/// @param allow_untracked_history 是否保留现有 V1 历史导入。@return 生命周期凭证。
pub(super) async fn claim(
    pool: AnyPool,
    account: i64,
    owner: (i64, Option<&str>),
    version: &str,
    body: &Value,
    binding: String,
    draining: bool,
    allow_untracked_history: bool,
) -> Result<NativeTurn, AppError> {
    let (principal, explicit) = owner;
    let rejected = || AppError::BadRequest(RECEIPT_MISMATCH.into());
    let ids = result_ids(body);
    let returning_result = has_result(body);
    if draining && !returning_result {
        return Err(AppError::AdmissionLimited { retry_after: 1 });
    }
    if returning_result && ids.is_none() && (draining || !allow_untracked_history) {
        return Err(rejected());
    }
    if let Some(explicit) = explicit {
        // V1 内核使用 UUID；公开自报同一个 UUID 也不能覆盖服务端登记的无头会话。
        let private = sqlx::query_scalar::<_, i64>(
            "SELECT COUNT(*) FROM tui_native_turns t
             JOIN tui_stateless_turn_proofs p ON p.turn_id=t.id
             WHERE t.account_id=$1 AND t.session_id=$2",
        )
        .bind(account)
        .bind(explicit)
        .fetch_one(&pool)
        .await?;
        if private != 0 {
            return Err(rejected());
        }
    }
    let next_history = if explicit.is_none() {
        let history = body["messages"].as_array();
        if history.is_none() && !allow_untracked_history {
            return Err(rejected());
        }
        history.map(|history| history_key(history))
    } else {
        None
    };
    if let Some(ids) = ids {
        let tools = serde_json::to_string(&ids).expect("纯字符串集合可编码");
        // 先拒绝同一归属内的工具组碰撞，再校验历史。正文或自报会话都不能独立取得归属。
        let candidates = sqlx::query(
            "SELECT t.id, t.session_id, p.history, p.declarations
             FROM tui_native_turns t LEFT JOIN tui_stateless_turn_proofs p ON p.turn_id=t.id
             WHERE t.account_id=$1 AND t.principal_id=$2 AND t.binding=$3 AND t.version=$4 AND t.tools=$5
             AND (($6='' AND p.turn_id IS NOT NULL) OR ($6<>'' AND t.session_id=$6 AND p.turn_id IS NULL))
             LIMIT 2",
        ).bind(account).bind(principal).bind(&binding).bind(version).bind(&tools).bind(explicit.unwrap_or(""))
            .fetch_all(&pool).await?;
        if let Some(message) =
            terminal_receipt(&pool, &tools, (!candidates.is_empty()).then_some(owner)).await?
        {
            return Err(AppError::BadRequest(message.into()));
        }
        if let [row] = candidates.as_slice() {
            if explicit.is_none() {
                let (history, declarations) =
                    continuation_proof(body, &ids).ok_or_else(rejected)?;
                if row.try_get::<String, _>("history")? != history
                    || row.try_get::<String, _>("declarations")? != declarations
                {
                    return Err(rejected());
                }
            }
            let id: String = row.try_get("id")?;
            let session_id: String = row.try_get("session_id")?;
            // 保留正在消费的 ID 供并发归属查询，CAS 只接受尚未认领的工具组。
            let claimed =
                sqlx::query("UPDATE tui_native_turns SET tools=$1 WHERE id=$2 AND tools=$3")
                    .bind(format!("!{tools}"))
                    .bind(&id)
                    .bind(&tools)
                    .execute(&pool)
                    .await?;
            if claimed.rows_affected() != 1 {
                return Err(rejected());
            }
            return Ok(NativeTurn {
                pool,
                id,
                previous_tools: Some(tools),
                background_agents: if explicit.is_some() && version == TUI_V2_RECEIPT_VERSION {
                    background_agent_hashes(body)
                } else {
                    Vec::new()
                },
                stateless_history: next_history,
                session_id,
                binding,
                submitted: AtomicBool::new(false),
                released: false,
                recovery: None,
                delivery: None,
                remember_receipt: version != "legacy",
            });
        }
        if !candidates.is_empty() {
            return Err(AppError::ServiceUnavailable("候选工具组归属有歧义".into()));
        }
        if !allow_untracked_history || draining {
            return Err(rejected());
        }
        let declarations = continuation_proof(body, &ids).map(|(_, declarations)| declarations);
        let known = sqlx::query_scalar::<_, i64>(
            "SELECT COUNT(*) FROM tui_native_turns t
             LEFT JOIN tui_stateless_turn_proofs p ON p.turn_id=t.id
             WHERE t.account_id=$1 AND (t.tools=$2 OR t.tools=$3 OR ($4<>'' AND p.declarations=$4))",
        )
        .bind(account)
        .bind(&tools)
        .bind(format!("!{tools}"))
        .bind(declarations.as_deref().unwrap_or(""))
        .fetch_one(&pool)
        .await?;
        if known != 0 {
            return Err(rejected());
        }
    }
    if draining {
        return Err(rejected());
    }
    let id = Uuid::new_v4().to_string();
    let session_id = explicit.unwrap_or(&id).to_owned();
    let mut tx = pool.begin().await?;
    sqlx::query(
        "INSERT INTO tui_native_turns (id,account_id,principal_id,session_id,binding,version,tools)
        VALUES ($1,$2,$3,$4,$5,$6,'')",
    )
    .bind(&id)
    .bind(account)
    .bind(principal)
    .bind(&session_id)
    .bind(&binding)
    .bind(version)
    .execute(&mut *tx)
    .await?;
    if let Some(history) = &next_history {
        sqlx::query("INSERT INTO tui_stateless_turn_proofs (turn_id,history,declarations) VALUES ($1,$2,'')")
            .bind(&id).bind(history).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    Ok(NativeTurn {
        pool,
        id,
        previous_tools: None,
        background_agents: Vec::new(),
        stateless_history: next_history,
        session_id,
        binding,
        submitted: AtomicBool::new(false),
        released: false,
        recovery: None,
        delivery: None,
        remember_receipt: false,
    })
}

impl Drop for NativeTurn {
    fn drop(&mut self) {
        if self.released || self.recovery.is_some() || self.submitted.load(Ordering::Acquire) {
            return;
        }
        if let Ok(runtime) = Handle::try_current() {
            let (pool, id, previous) = (
                self.pool.clone(),
                self.id.clone(),
                self.previous_tools.take(),
            );
            runtime.spawn(async move {
                if let Err(error) = release_open_turn(&pool, &id, previous.as_deref()).await {
                    warn!(%error,"未提交的候选工具轮待对账");
                }
            });
        }
    }
}

async fn release_open_turn(
    pool: &AnyPool,
    id: &str,
    previous: Option<&str>,
) -> Result<(), AppError> {
    if let Some(tools) = previous {
        sqlx::query("UPDATE tui_native_turns SET tools=$1 WHERE id=$2 AND tools=$3")
            .bind(tools)
            .bind(id)
            .bind(format!("!{tools}"))
            .execute(pool)
            .await?;
    } else {
        sqlx::query("DELETE FROM tui_native_turns WHERE id=$1 AND tools=''")
            .bind(id)
            .execute(pool)
            .await?;
    }
    Ok(())
}

impl NativeTurn {
    /// 将已获准的 V2 工具续轮关联到真实响应读者。@return 持久交付状态。
    pub(super) fn track_delivery(&mut self) -> Arc<Delivery> {
        let until = now_ms().saturating_add(BINDING_TTL_MS);
        let separator = if self.stateless_history.is_none() {
            'E'
        } else {
            ':'
        };
        let marker = format!(
            "#{until:020}{separator}{}",
            tool_digest(self.previous_tools.as_ref().expect("已认领的工具组"))
        );
        let delivery = Arc::new(Delivery {
            pool: self.pool.clone(),
            id: self.id.clone(),
            marker,
            open: self.open_tools(),
            verified: AtomicBool::new(false),
            next_tools: OnceLock::new(),
        });
        self.delivery = Some(delivery.clone());
        delivery
    }

    /// 仅凭原发送器的冷恢复预留替换已死亡的原步骤。@param recovered 原绑定发送器的独立证明。
    /// @return 唯一替代轮凭证。旧响应观察器即使迟到也只持旧行 ID。
    pub(super) async fn confirm_recovery(&mut self, recovered: bool) -> Result<(), AppError> {
        let Some(row) = self.recovery.as_ref() else {
            return Ok(());
        };
        if !recovered {
            return Err(AppError::ServiceUnavailable(
                "原步骤仍在交付，请稍后接回".into(),
            ));
        }
        let mut tx = self.pool.begin().await?;
        let inserted=sqlx::query("INSERT INTO tui_native_turns(id,account_id,principal_id,session_id,binding,version,tools)
             SELECT $1,account_id,principal_id,session_id,binding,$2,$3 FROM tui_native_turns
             WHERE id=$4 AND binding=$5 AND tools=$6 AND version=$7")
            .bind(&self.id).bind(TUI_V2_RECEIPT_VERSION).bind(self.open_tools()).bind(&row.id).bind(&row.binding)
            .bind(&row.tools).bind(&row.version).execute(&mut *tx).await?;
        if inserted.rows_affected() != 1 {
            return Err(AppError::AdmissionLimited { retry_after: 1 });
        }
        sqlx::query("UPDATE tui_stateless_turn_proofs SET turn_id=$1 WHERE turn_id=$2")
            .bind(&self.id)
            .bind(&row.id)
            .execute(&mut *tx)
            .await?;
        let removed =
            sqlx::query("DELETE FROM tui_native_turns WHERE id=$1 AND tools=$2 AND version=$3")
                .bind(&row.id)
                .bind(&row.tools)
                .bind(&row.version)
                .execute(&mut *tx)
                .await?;
        if removed.rows_affected() != 1 {
            return Err(AppError::AdmissionLimited { retry_after: 1 });
        }
        tx.commit().await?;
        self.recovery = None;
        Ok(())
    }

    /// 准备失败时，在返回公开错误前归还仍未提交的工具轮。@return 持久归还结果。
    pub(super) async fn release_rejected_prepare(mut self) -> Result<(), AppError> {
        if self.recovery.is_none() {
            self.release_tui_before_model().await?;
            // 后续合法认领可能重用同一行和工具组，归还后析构不能再修改它。
            self.released = true;
        }
        Ok(())
    }

    /// 在 Sender 确认工具尚未交付时归还原回执。@return 已条件恢复原可领状态。
    pub(super) async fn release_tui_before_model(&self) -> Result<(), AppError> {
        release_open_turn(&self.pool, &self.id, self.previous_tools.as_deref()).await
    }

    /// 标记本次是否认领了旧工具组。@return 是否必须保留原账号。
    pub(super) fn owns_continuation(&self) -> bool {
        self.previous_tools.is_some()
    }

    /// 返回无客户端会话时冻结的服务端会话。@return 已登记的 UUID 或空值。
    pub(super) fn stateless_session(&self) -> Option<&str> {
        self.stateless_history
            .as_ref()
            .map(|_| self.session_id.as_str())
    }

    /// 进入上游提交边界，原轮由响应收口。@return 无。
    pub(super) fn mark_submitted(&self) {
        self.submitted.store(true, Ordering::Release);
    }

    fn open_tools(&self) -> String {
        self.previous_tools
            .as_ref()
            .map_or_else(String::new, |tools| format!("!{tools}"))
    }

    /// 结束已明确不交付工具的 V1 新请求。@return 轮次回收结果。
    pub(super) async fn retire_v1_error(&self) -> Result<(), AppError> {
        if !self.owns_continuation() {
            self.finish(Some((Vec::new(), None))).await?;
        }
        Ok(())
    }

    /// 收口 V2 已返回的明确 HTTP 拒绝。@return 记录后的结果。
    pub(super) async fn retire_v2_rejection(&mut self) -> Result<(), AppError> {
        self.background_agents.clear();
        self.delivery = None;
        self.finish(Some((Vec::new(), None))).await
    }

    async fn finish(
        &self,
        observed: Option<(Vec<String>, Option<String>)>,
    ) -> Result<(), AppError> {
        let Some((tools, declarations)) = observed else {
            return Ok(());
        };
        if !tools.is_empty() && self.stateless_history.is_some() && declarations.is_none() {
            return Ok(());
        }
        let open = self.open_tools();
        let mut tx = self.pool.begin().await?;
        if self.remember_receipt
            && let Some(previous) = &self.previous_tools
        {
            // 原生 V1 与 V2 共用回执摘要。切换、重启后，V1 的历史导入也要拒绝已消费组。
            let until = now_ms().saturating_add(BINDING_TTL_MS);
            // 使用既有分隔位标记显式会话，旧版本仍可按同一偏移读取期限和摘要。
            let separator = if self.stateless_history.is_none() {
                'E'
            } else {
                ':'
            };
            let marker = format!("#{until:020}{separator}{}", tool_digest(previous));
            if self.delivery.is_none() || !tools.is_empty() {
                sqlx::query(
                "INSERT INTO tui_native_turns (id,account_id,principal_id,session_id,binding,version,tools)
                 SELECT $1,account_id,principal_id,session_id,binding,version,$2 FROM tui_native_turns
                 WHERE id=$3 AND tools=$4",
            )
            .bind(Uuid::new_v4().to_string())
            .bind(marker)
            .bind(&self.id)
            .bind(&open)
            .execute(&mut *tx)
            .await?;
            }
            for hint in &self.background_agents {
                // 只给已收口的原工具回执保留路由线索，不改变源端的代次或工具授权。
                sqlx::query(
                    "INSERT INTO tui_native_turns (id,account_id,principal_id,session_id,binding,version,tools)
                     SELECT $1,t.account_id,t.principal_id,t.session_id,t.binding,t.version,$2
                     FROM tui_native_turns t WHERE t.id=$3 AND t.tools=$4
                     AND (SELECT COUNT(*) FROM tui_native_turns a
                          WHERE a.account_id=t.account_id AND a.tools LIKE '#%'
                          AND substr(a.tools,22,1)='A' AND substr(a.tools,2,20)>$5)<$6",
                )
                .bind(Uuid::new_v4().to_string())
                .bind(format!("#{until:020}A{hint}"))
                .bind(&self.id)
                .bind(&open)
                .bind(format!("{:020}", now_ms()))
                .bind(BACKGROUND_AGENT_LIMIT as i64)
                .execute(&mut *tx)
                .await?;
            }
        }
        if tools.is_empty()
            && let Some(delivery) = &self.delivery
        {
            // 原响应已经结束，外部读者仍可能只拿到了一部分。沿用原行保留无头会话的依据。
            sqlx::query("UPDATE tui_native_turns SET tools=$1,version=$2 WHERE id=$3 AND tools=$4")
                .bind(&delivery.marker)
                .bind(UNDELIVERED)
                .bind(&self.id)
                .bind(&open)
                .execute(&mut *tx)
                .await?;
        } else if tools.is_empty() {
            sqlx::query("DELETE FROM tui_native_turns WHERE id=$1 AND tools=$2")
                .bind(&self.id)
                .bind(&open)
                .execute(&mut *tx)
                .await?;
        } else {
            if let (Some(history), Some(declarations)) = (&self.stateless_history, declarations) {
                sqlx::query("UPDATE tui_stateless_turn_proofs SET history=$1,declarations=$2 WHERE turn_id=$3")
                    .bind(history).bind(declarations).bind(&self.id).execute(&mut *tx).await?;
            }
            sqlx::query("UPDATE tui_native_turns SET tools=$1 WHERE id=$2 AND tools=$3")
                .bind(serde_json::to_string(&tools).expect("纯字符串集合可编码"))
                .bind(&self.id)
                .bind(&open)
                .execute(&mut *tx)
                .await?;
        }
        tx.commit().await?;
        if let Some(delivery) = &self.delivery {
            if !tools.is_empty() {
                let _ = delivery
                    .next_tools
                    .set(serde_json::to_string(&tools).expect("已排序的工具 ID"));
            }
            delivery.verified.store(true, Ordering::Release);
        }
        Ok(())
    }

    /// 在转交原响应终态前落下原工具组或关闭轮次。@param response sender 原 HTTP 响应。
    /// @param codings 原压缩编码。@return 保留原网络帧内容的流。
    pub(super) fn observe_response(self, response: Response, codings: &[String]) -> Response {
        self.observe_v2_response(response, codings, None)
    }

    /// 在已开始交付 V2 工具的流上登记切换保护。@param response 原响应。@param codings 原编码。
    /// @param cutover 本次公开请求的切换信号。@return 原样输出的受观察响应。
    pub(super) fn observe_v2_response(
        self,
        response: Response,
        codings: &[String],
        cutover: Option<InferenceCutover>,
    ) -> Response {
        if !self.submitted.load(Ordering::Acquire) || !response.status().is_success() {
            return response;
        }
        let (parts, body) = response.into_parts();
        let mut capture = UsageCapture::native_turn(self.stateless_history.is_some());
        capture.configure_codings(codings);
        let stream = unfold(
            (body, Some((self, capture)), cutover),
            |(mut body, mut info, cutover)| async move {
                let frame = body.frame().await;
                if let Some((_, capture)) = info.as_mut()
                    && let Some(Ok(frame)) = frame.as_ref()
                    && let Some(data) = frame.data_ref()
                    && !capture.observe_native(data)
                {
                    // 观察已不可恢复，释放解码状态和计量缓冲，原响应帧继续交付。
                    info = None;
                }
                if let Some(signal) = cutover.as_ref()
                    && info
                        .as_mut()
                        .is_some_and(|(_, capture)| capture.native_tools_started())
                {
                    // 先登记保护再转发首个工具事件，避免维护只交付半个工具组。
                    signal.protect_tui();
                }
                let finished = match &frame {
                    Some(Ok(_)) => {
                        body.is_end_stream()
                            || info
                                .as_mut()
                                .is_some_and(|(_, capture)| capture.native_stopped())
                    }
                    None => true,
                    Some(Err(_)) => {
                        // 原流报错时立即释放旁路，并保留未知轮次供对账。
                        info = None;
                        false
                    }
                };
                if finished
                    && let Some((turn, capture)) = info.take()
                    && let Err(error) = turn.finish(capture.native_terminal()).await
                {
                    return Some((Err(axum::Error::new(error)), (body, None, cutover)));
                }
                frame.map(|frame| (frame, (body, info, cutover)))
            },
        );
        Response::from_parts(parts, Body::new(StreamBody::new(stream)))
    }
}

#[cfg(test)]
mod tests {
    use axum::body::Bytes;
    use futures_util::stream::iter;
    use serde_json::json;
    use sha2::{Digest, Sha256};
    use sqlx::any::{AnyPoolOptions, install_default_drivers};
    use std::io::Error;

    use super::{
        Body, BodyExt, Ordering, Response, TUI_V2_RECEIPT_VERSION, Value, active_agent_account,
        awaiting_v2_tools, claim, continuation_account, occupied, prune_terminal,
    };
    use crate::service::request_body_codec::REQUEST_BODY_LIMIT;
    use crate::store::db::migrate;

    fn sse(value: Value) -> Bytes {
        Bytes::from(format!("data: {value}\n\n"))
    }

    /// 原进程已退出时仅原发送器能替代认领，迟到观察器和并发竞争者均保留原修订。
    #[tokio::test]
    async fn reconnect_replaces_only_the_verified_turn_and_acknowledges_delivery() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        sqlx::query("INSERT INTO accounts(id,name,email,token,device_id) VALUES(1,'first','first@test.invalid','fixture','one')")
            .execute(&pool).await.unwrap();
        let group = r#"["tool_a"]"#;
        let body = json!({"model":"chosen","messages":[{"role":"user","content":"question"},
            {"role":"assistant","content":[{"type":"tool_use","id":"tool_a","name":"Bash","input":{}}]},
            {"role":"user","content":[{"type":"tool_result","tool_use_id":"tool_a","content":"done"}]}]});
        sqlx::query("INSERT INTO tui_native_turns VALUES('original',1,7,'scope','binding',$1,$2)")
            .bind(TUI_V2_RECEIPT_VERSION)
            .bind(group)
            .execute(&pool)
            .await
            .unwrap();
        let owner = (7, Some("scope"));
        let original = claim(
            pool.clone(),
            1,
            owner,
            TUI_V2_RECEIPT_VERSION,
            &body,
            "binding".into(),
            false,
            false,
        )
        .await
        .unwrap();
        original.mark_submitted();
        for (principal, session) in [(8, Some("scope")), (7, Some("sibling")), (7, None)] {
            assert!(
                super::recovery_row(&pool, principal, session, &body)
                    .await
                    .unwrap()
                    .is_none()
            );
        }
        let candidate = || super::recovery_row(&pool, 7, Some("scope"), &body);
        let pending =
            |r: super::ReceiptRow| r.pending(pool.clone(), 1, "binding", owner, &body).unwrap();
        let mut first = pending(candidate().await.unwrap().unwrap());
        let mut other = pending(candidate().await.unwrap().unwrap());
        assert!(first.confirm_recovery(false).await.is_err());
        first.confirm_recovery(true).await.unwrap();
        assert!(other.confirm_recovery(true).await.is_err());
        original.finish(Some((Vec::new(), None))).await.unwrap();
        let delivery = first.track_delivery();
        first.mark_submitted();
        first.finish(Some((Vec::new(), None))).await.unwrap();
        let row = candidate().await.unwrap().unwrap();
        assert_eq!(row.version, super::UNDELIVERED);
        delivery.acknowledge().await.unwrap();
        assert!(candidate().await.unwrap().is_none());
        assert!(continuation_account(pool, owner, &body).await.is_err());
    }

    /// 生成结束后仍在慢读的连接持有原回复，直到断开后才开始重连窗口。
    #[tokio::test]
    async fn reconnect_preserves_completed_reply_for_slow_reader() {
        use crate::service::tui_reconnect::{Reconnects, Reservation};
        use std::sync::Arc;
        use std::time::Duration;

        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        let index = Reconnects::default();
        let key = [2; 32];
        let Reservation::First(writer) = index.reserve(key, 1, "original").unwrap() else {
            panic!("应取得原写者")
        };
        let delivery = Arc::new(super::Delivery {
            pool,
            id: "slow".into(),
            marker: "marker".into(),
            open: "!tools".into(),
            next_tools: Default::default(),
            verified: true.into(),
        });
        let source = Response::new(Body::from("原回复"));
        let mut slow = writer
            .publish(source, None, delivery, None, None)
            .await
            .unwrap()
            .into_body();
        assert!(slow.frame().await.unwrap().is_ok());
        tokio::time::sleep(Duration::from_secs(11)).await;
        drop(slow);
        let Reservation::Existing(reply) = index.reserve(key, 1, "original").unwrap() else {
            panic!("慢读结束时原回复应仍可接回")
        };
        let bytes = reply
            .subscribe(false)
            .await
            .unwrap()
            .into_body()
            .collect()
            .await
            .unwrap()
            .to_bytes();
        assert_eq!(bytes.as_ref(), "原回复".as_bytes());
    }

    /// 超过缓存预算仍须向在线端逐字节交付，维护取消及时释放停滞的模型读取。
    #[tokio::test]
    async fn reconnect_keeps_large_live_response_and_observes_admin_cancel() {
        use crate::service::system_update::{CutoverScope, InferenceCutover};
        use crate::service::tui_reconnect::{Reconnects, Reservation};
        use futures_util::StreamExt;
        use std::sync::Arc;
        use tokio::sync::{mpsc, watch};
        use tokio_stream::wrappers::ReceiverStream;
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        let index = Reconnects::default();
        for cancel in [false, true] {
            let key = [u8::from(cancel); 32];
            let Reservation::First(writer) = index.reserve(key, 1, "original").unwrap() else {
                panic!("应获得初次提交权")
            };
            assert!(index.reserve(key, 2, "original").is_err());
            assert!(index.reserve(key, 1, "other").is_err());
            let (epoch, watch) = watch::channel(None);
            let (send, recv) = mpsc::channel::<Bytes>(1);
            let source = Body::from_stream(ReceiverStream::new(recv).map(Ok::<_, Error>));
            let delivery = Arc::new(super::Delivery {
                pool: pool.clone(),
                id: "turn".into(),
                marker: "marker".into(),
                open: "!tools".into(),
                next_tools: Default::default(),
                verified: (!cancel).into(),
            });
            let mut response = writer
                .publish(
                    Response::new(source),
                    Some(InferenceCutover::new(watch)),
                    delivery,
                    None,
                    None,
                )
                .await
                .unwrap()
                .into_body();
            if cancel {
                epoch.send_replace(Some(CutoverScope {
                    epoch: uuid::Uuid::new_v4(),
                    preserve_tui: false,
                }));
                assert!(
                    tokio::time::timeout(std::time::Duration::from_secs(2), response.frame())
                        .await
                        .unwrap()
                        .unwrap()
                        .is_err()
                );
                send.closed().await;
            } else {
                let first = Bytes::from_static(b"first");
                send.send(first.clone()).await.unwrap();
                assert_eq!(
                    response
                        .frame()
                        .await
                        .unwrap()
                        .unwrap()
                        .into_data()
                        .unwrap(),
                    first
                );
                drop(response);
                let Reservation::Existing(reply) = index.reserve(key, 1, "original").unwrap()
                else {
                    panic!("已有响应")
                };
                response = reply.subscribe(false).await.unwrap().into_body();
                assert_eq!(
                    response
                        .frame()
                        .await
                        .unwrap()
                        .unwrap()
                        .into_data()
                        .unwrap(),
                    first
                );
                let large = Bytes::from(vec![7; 64 * 1024 * 1024 + 1]);
                send.send(large.clone()).await.unwrap();
                assert_eq!(
                    response
                        .frame()
                        .await
                        .unwrap()
                        .unwrap()
                        .into_data()
                        .unwrap(),
                    large
                );
                let Reservation::Existing(reply) = index.reserve(key, 1, "original").unwrap()
                else {
                    panic!("已有响应")
                };
                assert!(reply.subscribe(false).await.is_err());
                drop(send);
                assert!(response.frame().await.is_none());
            }
        }
    }

    #[tokio::test]
    async fn platform_update_waits_for_offered_and_claimed_v2_tools() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        sqlx::query(
            "INSERT INTO accounts(id,name,email,token,device_id)
             VALUES(1,'synthetic','v2@example.invalid','synthetic','fixture')",
        )
        .execute(&pool)
        .await
        .unwrap();
        sqlx::query(
            "INSERT INTO tui_native_turns(id,account_id,principal_id,session_id,binding,version,tools)
             VALUES('synthetic',1,20,'session','binding',$1,'')",
        )
        .bind(TUI_V2_RECEIPT_VERSION)
        .execute(&pool)
        .await
        .unwrap();
        for (tools, pending) in [
            ("", false),
            (r#"["toolu_synthetic"]"#, true),
            (r#"!["toolu_synthetic"]"#, true),
            ("#terminal", false),
        ] {
            sqlx::query("UPDATE tui_native_turns SET tools=$1 WHERE id='synthetic'")
                .bind(tools)
                .execute(&pool)
                .await
                .unwrap();
            assert_eq!(pending, awaiting_v2_tools(pool.clone()).await.unwrap());
        }
    }

    /// 后台进度只读本主体及会话的完整 V2 工具组，覆盖认领前、认领中和终态。
    #[tokio::test]
    async fn summary_account_checks_live_claimed_and_consumed_groups() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        sqlx::query(
            "INSERT INTO accounts(id,name,email,token,device_id,request_backend)
            VALUES(1,'test','receipt@test.invalid','synthetic','one','tui_v2')",
        )
        .execute(&pool)
        .await
        .unwrap();
        let tools = r#"["one","two"]"#;
        let digest = super::tool_digest(tools);
        sqlx::query("INSERT INTO tui_native_turns VALUES('first',1,20,'session','binding',$1,$2)")
            .bind(TUI_V2_RECEIPT_VERSION)
            .bind(tools)
            .execute(&pool)
            .await
            .unwrap();
        for (value, owner) in [
            (tools.into(), Some(1)),
            (format!("!{tools}"), Some(1)),
            (
                format!("#{:020}E{digest}", super::now_ms() + 60000),
                Some(1),
            ),
            (format!("#{:020}E{digest}", 0), None),
        ] {
            sqlx::query("UPDATE tui_native_turns SET tools=$1 WHERE id='first'")
                .bind(&value)
                .execute(&pool)
                .await
                .unwrap();
            for (principal, session, ids, expected) in [
                (20, "session", &["one", "two"][..], owner),
                (21, "session", &["one", "two"][..], None),
                (20, "other", &["one", "two"][..], None),
                (20, "session", &["one"][..], None),
            ] {
                assert_eq!(
                    super::summary_account(&pool, principal, session, ids)
                        .await
                        .unwrap(),
                    expected
                );
            }
            assert_eq!(
                sqlx::query_scalar::<_, String>(
                    "SELECT tools FROM tui_native_turns WHERE id='first'"
                )
                .fetch_one(&pool)
                .await
                .unwrap(),
                value
            );
        }
    }

    /// 过期回执只收口一条，原状态变化会拒绝旧证明。@return 无。
    #[tokio::test]
    async fn recovered_receipt_preserves_original_identity_and_blocks_replay() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        sqlx::query(
            "INSERT INTO accounts(id,name,email,token,device_id) VALUES
            (1,'first','first@test.invalid','synthetic','one'),
            (2,'other','other@test.invalid','synthetic','two')",
        )
        .execute(&pool)
        .await
        .unwrap();
        let tools = r#"["toolu_orphaned"]"#;
        for (id, account, session, tools) in [
            ("first", 1, "original", tools),
            ("peer", 1, "still-running", r#"["toolu_waiting"]"#),
            ("remote", 2, "other", r#"["toolu_remote"]"#),
        ] {
            sqlx::query("INSERT INTO tui_native_turns VALUES ($1,$2,20,$3,'same-binding',$4,$5)")
                .bind(id)
                .bind(account)
                .bind(session)
                .bind(TUI_V2_RECEIPT_VERSION)
                .bind(tools)
                .execute(&pool)
                .await
                .unwrap();
        }
        let page = super::receipt_page(&pool, "first", 1).await.unwrap();
        assert_eq!(page[0].id, "peer");
        let original = super::receipt_row(&pool, 1, "first")
            .await
            .unwrap()
            .unwrap();
        assert!(
            super::receipt_row(&pool, 2, "first")
                .await
                .unwrap()
                .is_none()
        );
        sqlx::query("UPDATE tui_native_turns SET tools=$1 WHERE id='first'")
            .bind(format!("!{tools}"))
            .execute(&pool)
            .await
            .unwrap();
        assert!(!super::retire_orphan(&pool, &original).await.unwrap());
        let claimed = super::receipt_row(&pool, 1, "first")
            .await
            .unwrap()
            .unwrap();
        assert_ne!(claimed.revision(), original.revision());
        assert!(super::retire_orphan(&pool, &claimed).await.unwrap());
        assert!(!super::retire_orphan(&pool, &claimed).await.unwrap());
        let recovered = super::receipt_row(&pool, 1, "first")
            .await
            .unwrap()
            .unwrap();
        assert_eq!(recovered.revision(), claimed.revision());
        assert_eq!(recovered.recovered(), Some(true));
        assert_eq!(
            super::terminal_receipt(&pool, tools, Some((20, Some("original"))))
                .await
                .unwrap(),
            Some(super::RECEIPT_ORPHANED)
        );
        assert!(
            super::terminal_receipt(&pool, tools, Some((20, Some("still-running"))))
                .await
                .unwrap()
                .is_none()
        );
        assert_eq!(
            super::receipt_page(&pool, "", 5)
                .await
                .unwrap()
                .into_iter()
                .map(|record| record.id)
                .collect::<Vec<_>>(),
            ["peer", "remote"]
        );
        let late = json!({"messages":[{"role":"user","content":[
            {"type":"tool_result", "tool_use_id":"toolu_orphaned", "content":"late"}]}]});
        let error = continuation_account(pool.clone(), (20, Some("original")), &late)
            .await
            .unwrap_err();
        assert!(error.to_string().contains(super::RECEIPT_ORPHANED));
    }

    /// 活动子轮不得选择另一账号，同一主体撞上两个原账号时拒绝。
    #[tokio::test]
    async fn tui_agent_account_is_bound_to_the_authenticated_active_session() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        sqlx::query(
            "INSERT INTO accounts(id,name,email,token,device_id)
                    VALUES(1,'one','one@example.invalid','synthetic','fixture'),
                          (2,'two','two@example.invalid','synthetic','fixture')",
        )
        .execute(&pool)
        .await
        .unwrap();
        let messages = json!({"messages":[{"role":"user","content":"合成"}]});
        let open = |account| {
            claim(
                pool.clone(),
                account,
                (9, Some("session")),
                TUI_V2_RECEIPT_VERSION,
                &messages,
                "local".into(),
                false,
                false,
            )
        };
        let parent = open(1).await.unwrap();
        let sibling = open(1).await.unwrap();
        assert_eq!(
            active_agent_account(pool.clone(), 9, "session", "agent")
                .await
                .unwrap(),
            Some(1)
        );
        assert_eq!(
            active_agent_account(pool.clone(), 10, "session", "agent")
                .await
                .unwrap(),
            None
        );
        assert_eq!(
            active_agent_account(pool.clone(), 9, "other", "agent")
                .await
                .unwrap(),
            None
        );
        let other = open(2).await.unwrap();
        assert!(
            active_agent_account(pool.clone(), 9, "session", "agent")
                .await
                .is_err()
        );
        drop((parent, sibling, other));
    }

    /// 后台父轮退场后，只有已确认的特定线索能保持原账号。
    #[tokio::test]
    async fn tui_background_agent_routing_survives_the_parent_terminal() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        sqlx::query(
            "INSERT INTO accounts(id,name,email,token,device_id)
                 VALUES(1,'one','one@example.invalid','synthetic','fixture'),
                       (2,'two','two@example.invalid','synthetic','fixture')",
        )
        .execute(&pool)
        .await
        .unwrap();
        let body = json!({"messages":[{"role":"user","content":"合成"}]});
        let open = claim(
            pool.clone(),
            1,
            (9, Some("session")),
            TUI_V2_RECEIPT_VERSION,
            &body,
            "local".into(),
            false,
            false,
        )
        .await
        .unwrap();
        open.mark_submitted();
        open.finish(Some((vec!["first".into(), "second".into()], None)))
            .await
            .unwrap();
        let body = json!({"messages":[
            {"role":"user","content":"合成"},
            {"role":"assistant","content":[
                {"type":"tool_use","name":"Agent","id":"first","input":{"prompt":"相同合成输入"}},
                {"type":"tool_use","name":"Agent","id":"second","input":{"prompt":"相同合成输入"}}
            ]},
            {"role":"user","content":[
                {"type":"tool_result","tool_use_id":"first","content":[{
                    "type":"text","text":"Async agent launched successfully. (internal)\nagentId: agentA (internal ID)"
                }, {"type":"text","text":"客户端附加说明"}]},
                {"type":"tool_result","tool_use_id":"second","is_error":true,"content":
                    "Async agent launched successfully. (internal)\nagentId: agentB (internal ID)"
                }
            ]},
            {"role":"system","content":"上下文"}
        ]});
        let continued = claim(
            pool.clone(),
            1,
            (9, Some("session")),
            TUI_V2_RECEIPT_VERSION,
            &body,
            "local".into(),
            false,
            false,
        )
        .await
        .unwrap();
        continued.mark_submitted();
        continued.finish(Some((vec![], None))).await.unwrap();
        assert!(!super::occupied(pool.clone(), 1).await.unwrap());
        for (principal, session, hint, account) in [
            (9, "session", "agentA", Some(1)),
            (9, "session", "agentB", None),
            (10, "session", "agentA", None),
            (9, "other", "agentA", None),
        ] {
            assert_eq!(
                active_agent_account(pool.clone(), principal, session, hint)
                    .await
                    .unwrap(),
                account
            );
        }
        let competing = claim(
            pool.clone(),
            2,
            (9, Some("session")),
            TUI_V2_RECEIPT_VERSION,
            &json!({"messages":[{"role":"user","content":"另一个独立合成轮"}]}),
            "other-environment".into(),
            false,
            false,
        )
        .await
        .unwrap();
        assert!(
            super::occupied(pool.clone(), 2).await.unwrap(),
            "第二账号在同一会话已有活动轮"
        );
        assert_eq!(
            active_agent_account(pool.clone(), 9, "session", "agentA")
                .await
                .unwrap(),
            Some(1)
        );
        assert_eq!(
            active_agent_account(pool.clone(), 9, "session", "unknown")
                .await
                .unwrap(),
            Some(2)
        );
        drop(competing);
    }

    /// 续轮在提交中及终态均受原账号、会话、主体和代次的登记约束。
    #[tokio::test]
    async fn tui_receipts_bind_actor_session_generation_and_terminal() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        sqlx::query(
            "INSERT INTO accounts(id,name,email,token,device_id)
             VALUES(1,'one','one@example.invalid','synthetic','fixture'),
                   (2,'two','two@example.invalid','synthetic','fixture')",
        )
        .execute(&pool)
        .await
        .unwrap();
        let initial = json!({"messages":[{"role":"user","content":"初始请求"}]});
        for (index, (version, explicit)) in [
            (TUI_V2_RECEIPT_VERSION, None),
            (TUI_V2_RECEIPT_VERSION, Some("original-session")),
            ("2.1.293", None),
            ("2.1.293", Some("original-session")),
        ]
        .into_iter()
        .enumerate()
        {
            let tool_id = format!("toolu_{index}_{}", "very-long-id".repeat(40));
            let follow = json!({"messages":[initial["messages"][0].clone(),
                {"role":"assistant","content":[{"type":"tool_use","id":tool_id,"name":"Read","input":{"path":"fixture"}}]},
                {"role":"user","content":[{"type":"tool_result","tool_use_id":tool_id,"content":"合成结果"}]}]});
            let created = claim(
                pool.clone(),
                1,
                (7, explicit),
                version,
                &initial,
                "binding-1".into(),
                false,
                false,
            )
            .await
            .unwrap();
            let server_session = created.session_id.clone();
            created.mark_submitted();
            let ids = super::result_ids(&follow).unwrap();
            let (_, declarations) = super::continuation_proof(&follow, &ids).unwrap();
            created
                .finish(Some((vec![tool_id], Some(declarations))))
                .await
                .unwrap();
            assert!(occupied(pool.clone(), 1).await.unwrap());
            assert_eq!(
                continuation_account(pool.clone(), (7, explicit), &follow)
                    .await
                    .unwrap(),
                Some(1)
            );
            // 真实 CC 会把补充上下文放在工具结果之后。路由仍须核对原账号和主体。
            let mut with_context = follow.clone();
            with_context["messages"]
                .as_array_mut()
                .unwrap()
                .push(json!({"role":"system","content":[{"type":"text","text":"本轮附加上下文"}]}));
            assert_eq!(
                continuation_account(pool.clone(), (7, explicit), &with_context)
                    .await
                    .unwrap(),
                Some(1)
            );
            assert!(
                continuation_account(pool.clone(), (8, explicit), &with_context)
                    .await
                    .is_err()
            );
            assert!(
                continuation_account(pool.clone(), (8, explicit), &follow)
                    .await
                    .is_err()
            );
            assert!(
                continuation_account(pool.clone(), (7, Some("other-session")), &follow)
                    .await
                    .is_err()
            );
            if explicit.is_none() {
                let mut different = follow.clone();
                different["messages"][0]["content"] = json!("另一个历史");
                assert!(
                    continuation_account(pool.clone(), (7, None), &different)
                        .await
                        .is_err()
                );
            }
            for (account, binding) in [(2, "binding-1"), (1, "binding-2")] {
                assert!(
                    claim(
                        pool.clone(),
                        account,
                        (7, explicit),
                        version,
                        &follow,
                        binding.into(),
                        false,
                        false
                    )
                    .await
                    .is_err()
                );
            }
            let continuation = claim(
                pool.clone(),
                1,
                (7, explicit),
                version,
                &with_context,
                "binding-1".into(),
                true,
                false,
            )
            .await
            .unwrap();
            assert!(continuation.owns_continuation());
            assert_eq!(continuation.session_id, server_session);
            assert_eq!(
                continuation_account(pool.clone(), (7, explicit), &follow)
                    .await
                    .unwrap(),
                Some(1)
            );
            assert!(
                claim(
                    pool.clone(),
                    1,
                    (7, explicit),
                    version,
                    &follow,
                    "binding-1".into(),
                    false,
                    false
                )
                .await
                .is_err()
            );
            continuation.mark_submitted();
            continuation.finish(Some((vec![], None))).await.unwrap();
            assert!(!occupied(pool.clone(), 1).await.unwrap());
            assert!(
                continuation_account(pool.clone(), (7, explicit), &follow)
                    .await
                    .is_err()
            );
            assert!(
                claim(
                    pool.clone(),
                    2,
                    (7, explicit),
                    "legacy",
                    &follow,
                    "legacy:gateway".into(),
                    false,
                    true
                )
                .await
                .is_err()
            );
            let wrong = sqlx::query_scalar::<_, i64>(
                "SELECT COUNT(*) FROM tui_native_turns WHERE tools LIKE '#%' AND (tools LIKE '%toolu_%' OR length(tools)<>86)",
            ).fetch_one(&pool).await.unwrap();
            assert_eq!(wrong, 0);
            let deleted = sqlx::query("UPDATE tui_native_turns SET tools='#00000000000000000001:' || substr(tools,23) WHERE tools LIKE '#%'")
                .execute(&pool).await.unwrap();
            assert_eq!(deleted.rows_affected(), 1);
            prune_terminal(pool.clone()).await.unwrap();
            let remaining = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM tui_native_turns")
                .fetch_one(&pool)
                .await
                .unwrap();
            assert_eq!(remaining, 0);
        }
    }

    /// 同名工具可由各自的调用方交错完成，每次完成后仍拒绝本人的重复回执。
    #[tokio::test]
    async fn same_tool_id_is_independent_across_owners() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        sqlx::query("INSERT INTO accounts(id,name,email,token,device_id) VALUES(1,'one','one@example.invalid','synthetic','fixture')")
            .execute(&pool).await.unwrap();
        let initial = json!({"messages":[{"role":"user","content":"读取同名文件"}]});
        for (tool, owners) in [
            (
                "tool_shared_session",
                [(7, Some("same")), (8, Some("same"))],
            ),
            (
                "tool_distinct_sessions",
                [(7, Some("one")), (7, Some("two"))],
            ),
            ("tool_stateless", [(7, None), (8, None)]),
            ("tool_explicit_first", [(7, None), (7, Some("same"))]),
            ("tool_stateless_first", [(7, Some("same")), (7, None)]),
        ] {
            let follow = json!({"messages":[initial["messages"][0].clone(),
                {"role":"assistant","content":[{"type":"tool_use","id":tool,"name":"Read","input":{}}]},
                {"role":"user","content":[{"type":"tool_result","tool_use_id":tool,"content":"文件内容"}]}]});
            let ids = super::result_ids(&follow).unwrap();
            let (_, declarations) = super::continuation_proof(&follow, &ids).unwrap();
            let take = |owner, body| {
                claim(
                    pool.clone(),
                    1,
                    owner,
                    TUI_V2_RECEIPT_VERSION,
                    body,
                    "binding".into(),
                    false,
                    false,
                )
            };
            for owner in owners {
                let turn = take(owner, &initial).await.unwrap();
                turn.mark_submitted();
                turn.finish(Some((vec![tool.to_owned()], Some(declarations.clone()))))
                    .await
                    .unwrap();
            }
            for owner in owners.into_iter().rev() {
                assert_eq!(
                    continuation_account(pool.clone(), owner, &follow)
                        .await
                        .unwrap(),
                    Some(1)
                );
                let turn = take(owner, &follow).await.unwrap();
                turn.mark_submitted();
                turn.finish(Some((vec![], None))).await.unwrap();
                assert!(
                    continuation_account(pool.clone(), owner, &follow)
                        .await
                        .is_err()
                );
                assert!(take(owner, &follow).await.is_err());
            }
        }
        // 新的无头候选即使拥有同样的历史，也不能重新认领旧无头回执。
        // ':' 也是旧发行版唯一的终态分隔符，存量显式会话同样保留这项保护。
        let history = initial["messages"][0].clone();
        for tool in ["tool_stateless", "tool_distinct_sessions"] {
            if tool == "tool_distinct_sessions" {
                sqlx::query("UPDATE tui_native_turns SET tools=substr(tools,1,21) || ':' || substr(tools,23) WHERE substr(tools,22,1)='E' AND substr(tools,23)=$1")
                    .bind(super::tool_digest(&json!([tool]).to_string())).execute(&pool).await.unwrap();
            }
            let body = json!({"messages":[history.clone(),
                {"role":"assistant","content":[{"type":"tool_use","id":tool,"name":"Read","input":{}}]},
                {"role":"user","content":[{"type":"tool_result","tool_use_id":tool,"content":"文件内容"}]}]});
            let owner = (7, None);
            let turn = claim(
                pool.clone(),
                1,
                owner,
                TUI_V2_RECEIPT_VERSION,
                &initial,
                "binding".into(),
                false,
                false,
            )
            .await
            .unwrap();
            let ids = super::result_ids(&body).unwrap();
            let (_, declarations) = super::continuation_proof(&body, &ids).unwrap();
            turn.mark_submitted();
            turn.finish(Some((vec![tool.to_owned()], Some(declarations))))
                .await
                .unwrap();
            assert!(
                continuation_account(pool.clone(), owner, &body)
                    .await
                    .is_err()
            );
            assert!(
                claim(
                    pool.clone(),
                    1,
                    owner,
                    TUI_V2_RECEIPT_VERSION,
                    &body,
                    "binding".into(),
                    false,
                    false
                )
                .await
                .is_err()
            );
        }
    }

    /// 实际响应 Body 逐帧透传。长文本正常关轮，工具观察超限则保留原轮供对账。
    #[tokio::test]
    async fn native_tool_body_preserves_large_responses_and_only_retires_verified_turns() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        sqlx::query("INSERT INTO accounts(id,name,email,token,device_id) VALUES(1,'synthetic','one@example.invalid','synthetic','fixture')")
            .execute(&pool).await.unwrap();
        let input = json!({"messages":[{"role":"user","content":"fixture"}]});
        let piece = "x".repeat(REQUEST_BODY_LIMIT / 32);
        for (tool_overflow, transport_error) in [(false, false), (true, false), (false, true)] {
            let turn = claim(
                pool.clone(),
                1,
                (1, None),
                "2.1.293",
                &input,
                "fixture:1".into(),
                false,
                false,
            )
            .await
            .unwrap();
            turn.submitted.store(true, Ordering::Release);
            let id = turn.id.clone();
            let mut frames = vec![sse(
                json!({"type":"message_start","message":{"usage":{"input_tokens":1,"output_tokens":0}}}),
            )];
            if tool_overflow {
                for index in 0..2 {
                    frames.push(sse(json!({"type":"content_block_start","index":index,"content_block":
                        {"type":"tool_use","id":format!("toolu_{index}"),"name":"Read","input":{}}})));
                    frames.push(sse(
                        json!({"type":"content_block_delta","index":index,"delta":
                        {"type":"input_json_delta","partial_json":"{\"path\":\""}}),
                    ));
                }
                for index in 0..2 {
                    let delta = sse(json!({"type":"content_block_delta","index":index,"delta":
                        {"type":"input_json_delta","partial_json":piece}}));
                    frames.extend(std::iter::repeat_n(delta, 18));
                    frames.push(sse(
                        json!({"type":"content_block_delta","index":index,"delta":
                        {"type":"input_json_delta","partial_json":"\"}"}}),
                    ));
                    frames.push(sse(json!({"type":"content_block_stop","index":index})));
                }
            } else {
                frames.push(sse(json!({"type":"content_block_start","index":0,
                    "content_block":{"type":"text","text":""}})));
                let delta = sse(json!({"type":"content_block_delta","index":0,
                    "delta":{"type":"text_delta","text":piece}}));
                frames.extend(std::iter::repeat_n(delta, 36));
                frames.push(sse(json!({"type":"content_block_stop","index":0})));
            }
            let reason = if tool_overflow {
                "tool_use"
            } else {
                "end_turn"
            };
            frames.push(sse(json!({"type":"message_delta","delta":{"stop_reason":reason},"usage":{"output_tokens":10}})));
            frames.push(sse(json!({"type":"message_stop"})));
            let original_len = frames.iter().map(Bytes::len).sum::<usize>();
            assert!(original_len > REQUEST_BODY_LIMIT);
            let mut wire: Vec<_> = frames.iter().cloned().map(Ok::<_, Error>).collect();
            if transport_error {
                wire.insert(2, Err(Error::other("fixture interrupted stream")));
            }
            let stream = iter(wire);
            let response = Response::new(Body::from_stream(stream));
            let mut body = turn.observe_response(response, &[]).into_body();
            let mut delivered_len = 0;
            let mut delivered_hash = Sha256::new();
            for (index, sent) in frames.into_iter().enumerate() {
                if transport_error && index == 2 {
                    let error = body.frame().await.unwrap().unwrap_err();
                    assert!(error.to_string().contains("fixture interrupted stream"));
                }
                let received = body.frame().await.unwrap().unwrap().into_data().unwrap();
                assert_eq!(sent, received);
                delivered_len += received.len();
                delivered_hash.update(&received);
            }
            assert!(body.frame().await.is_none());
            assert_eq!(delivered_len, original_len);
            let retained: Option<String> =
                sqlx::query_scalar("SELECT tools FROM tui_native_turns WHERE id=$1")
                    .bind(id)
                    .fetch_optional(&pool)
                    .await
                    .unwrap();
            assert_eq!(
                retained.as_deref(),
                (tool_overflow || transport_error).then_some("")
            );
            println!(
                "工具超限={tool_overflow} 传输错误={transport_error} 响应={delivered_len} 字节 SHA256={:x} 待核对={}",
                delivered_hash.finalize(),
                retained.is_some()
            );
        }
    }
}
