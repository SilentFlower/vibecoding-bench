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
use tokio::runtime::Handle;
use tracing::warn;
use uuid::Uuid;

use crate::error::AppError;
use crate::service::request_session::valid_id;
use crate::service::tui_tool_history::{
    continuation_proof, has_result, history_key, preceding_tool_ids, result_ids,
};
use crate::service::usage::UsageCapture;
use crate::service::v3_scheduling::now_ms;
use crate::store::scheduling_store::BINDING_TTL_MS;

pub(super) const TUI_V2_RECEIPT_VERSION: &str = "tui-v2:2.1.293:1";
const BACKGROUND_AGENT_LIMIT: usize = 1024;
const RECEIPT_MISMATCH: &str = "工具回执与登记轮次不符，请使用原入口令牌、原会话和完整工具组继续";
const RECEIPT_COMPLETE: &str = "该工具组的回执已处理，请从上一条响应继续";

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
    remember_receipt: bool,
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

/// 有匹配的待处理轮时，只校验该归属可能重放的终态。缺少匹配时仍全局阻止历史重新导入。
async fn terminal_exists(
    pool: &AnyPool,
    tools: &str,
    owner: Option<(i64, Option<&str>)>,
) -> Result<bool, AppError> {
    let count = sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*) FROM tui_native_turns WHERE tools LIKE '#%'
         AND substr(tools,2,20)>$1 AND substr(tools,23)=$2
         AND substr(tools,22,1)<>'A'
         AND principal_id=COALESCE($3,principal_id) AND session_id=COALESCE($4,session_id)
         AND ($5=0 OR substr(tools,22,1)<>'E')",
    )
    .bind(format!("{:020}", now_ms()))
    .bind(tool_digest(tools))
    .bind(owner.map(|(principal, _)| principal))
    .bind(owner.and_then(|(_, session)| session))
    // 已核验的无头候选只排除明确属于显式会话的终态。旧记录和无头重放仍保守拒绝。
    .bind(i64::from(matches!(owner, Some((_, None)))))
    .fetch_one(pool)
    .await?;
    Ok(count != 0)
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
            if terminal_exists(&pool, &tools, None).await?
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
    if terminal_exists(&pool, &tools, (!candidates.is_empty()).then_some(owner)).await? {
        return Err(AppError::BadRequest(RECEIPT_COMPLETE.into()));
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
        if terminal_exists(&pool, &tools, (!candidates.is_empty()).then_some(owner)).await? {
            return Err(AppError::BadRequest(RECEIPT_COMPLETE.into()));
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
        remember_receipt: false,
    })
}

impl Drop for NativeTurn {
    fn drop(&mut self) {
        if self.submitted.load(Ordering::Acquire) {
            return;
        }
        if let Ok(runtime) = Handle::try_current() {
            let (pool, id, previous) = (
                self.pool.clone(),
                self.id.clone(),
                self.previous_tools.take(),
            );
            runtime.spawn(async move {
                let result = match previous {
                    Some(tools) => {
                        sqlx::query("UPDATE tui_native_turns SET tools=$1 WHERE id=$2 AND tools=$3")
                            .bind(&tools)
                            .bind(&id)
                            .bind(format!("!{tools}"))
                            .execute(&pool)
                            .await
                    }
                    None => {
                        sqlx::query("DELETE FROM tui_native_turns WHERE id=$1 AND tools=''")
                            .bind(&id)
                            .execute(&pool)
                            .await
                    }
                };
                if let Err(error) = result {
                    warn!(%error,"未提交的候选工具轮待对账");
                }
            });
        }
    }
}

impl NativeTurn {
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
        if tools.is_empty() {
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
        Ok(())
    }

    /// 在转交原响应终态前落下原工具组或关闭轮次。@param response sender 原 HTTP 响应。
    /// @param codings 原压缩编码。@return 保留原网络帧内容的流。
    pub(super) fn observe_response(self, response: Response, codings: &[String]) -> Response {
        if !self.submitted.load(Ordering::Acquire) || !response.status().is_success() {
            return response;
        }
        let (parts, body) = response.into_parts();
        let mut capture = UsageCapture::native_turn(self.stateless_history.is_some());
        capture.configure_codings(codings);
        let stream = unfold(
            (body, Some((self, capture))),
            |(mut body, mut info)| async move {
                let frame = body.frame().await;
                if let Some((_, capture)) = info.as_mut()
                    && let Some(Ok(frame)) = frame.as_ref()
                    && let Some(data) = frame.data_ref()
                    && !capture.observe_native(data)
                {
                    // 观察已不可恢复，释放解码状态和计量缓冲，原响应帧继续交付。
                    info = None;
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
                    return Some((Err(axum::Error::new(error)), (body, None)));
                }
                frame.map(|frame| (frame, (body, info)))
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
