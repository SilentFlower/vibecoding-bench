//! 用原发送器的只读状态收口已退出的 V2 工具轮。

use futures_util::{StreamExt, stream};
use serde::Serialize;
use std::sync::Arc;
use std::sync::atomic::Ordering;
use std::time::Duration;
use tokio::time::{MissedTickBehavior, interval};
use tracing::warn;

use crate::error::AppError;
use crate::service::account::AccountService;
use crate::service::request_session::valid_id;
use crate::service::runtime_transport::{TuiReceiptProbe, tui_receipt_status, tui_same_binding};
use crate::service::system_update;
use crate::service::tui_native_drain::{ReceiptRow, receipt_page, receipt_row, retire_orphan};

const PAGE_SIZE: usize = 24;
const PROBE_CONCURRENCY: usize = 8;

/// 单条回执核对的公开状态。
#[derive(Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum ReceiptState {
    Waiting,
    Recoverable,
    Deferred,
    BindingChanged,
    Recovered,
    RecoveredDeliveryUnknown,
}

/// 系统更新页使用的脱敏单条回执。
#[derive(Serialize)]
pub(crate) struct ReceiptView {
    id: String,
    account_id: i64,
    account_name: String,
    revision: String,
    state: ReceiptState,
}

impl ReceiptView {
    fn new(row: &ReceiptRow, account_name: String, state: ReceiptState) -> Self {
        Self {
            id: row.id.clone(),
            account_id: row.account_id,
            account_name,
            revision: row.revision(),
            state,
        }
    }
}

/// 待核对回执分页。游标仅包括上一页已公开的记录标识。
#[derive(Serialize)]
pub(crate) struct ReceiptPage {
    items: Vec<ReceiptView>,
    next: Option<String>,
}

/// 只读核对当前发送器。@param service 网关账号服务。@param row 原记录。
/// @param recover 操作者或后台已取得变更准入。@return 公开核对结果及账号名称。
async fn inspect(
    service: &AccountService,
    row: &ReceiptRow,
    recover: bool,
) -> Result<ReceiptView, AppError> {
    let account = match service.get_account(row.account_id).await {
        Ok(account) => account,
        Err(AppError::NotFound) => {
            return Ok(ReceiptView::new(
                row,
                format!("账号 #{}", row.account_id),
                ReceiptState::BindingChanged,
            ));
        }
        Err(error) => return Err(error),
    };
    let view = |state| ReceiptView::new(row, account.name.clone(), state);
    if let Some(unknown) = row.recovered() {
        return Ok(view(if unknown {
            ReceiptState::RecoveredDeliveryUnknown
        } else {
            ReceiptState::Recovered
        }));
    }
    let queue = service
        .get_or_create_queue(account.id, account.concurrency)
        .await;
    let generation = {
        let Ok(_route) = queue.tui_route.try_write() else {
            return Ok(view(ReceiptState::Waiting));
        };
        if queue.active_request_count() != 0 {
            return Ok(view(ReceiptState::Waiting));
        }
        queue.tui_turn_generation.load(Ordering::Relaxed)
    };
    let state = service.tui_backend(account.id).await?;
    if state.active != "tui_v2" || state.binding != row.binding || state.binding.is_empty() {
        return Ok(view(ReceiptState::BindingChanged));
    }
    let (principal_id, session_id) = row.sender_identity();
    let probe = (principal_id > 0 && valid_id(&session_id)).then_some(TuiReceiptProbe {
        principal_id,
        session_id,
    });
    // 原节点可能失联，远程只读请求期间不占用网关的账号或维护写入许可。
    let Ok(sender) = tui_receipt_status(&account, &row.binding, probe.as_ref()).await else {
        return Ok(view(ReceiptState::Deferred));
    };
    if !tui_same_binding(&row.binding, &sender.key) {
        return Ok(view(ReceiptState::BindingChanged));
    }
    if !sender.idle {
        return Ok(view(ReceiptState::Waiting));
    }
    if !recover {
        return Ok(view(ReceiptState::Recoverable));
    }
    let Ok(_route) = queue.tui_route.try_write() else {
        return Ok(view(ReceiptState::Waiting));
    };
    let Ok(_config) = queue.tui_config.try_lock() else {
        return Ok(view(ReceiptState::Waiting));
    };
    if queue.active_request_count() != 0
        || queue.tui_turn_generation.load(Ordering::Relaxed) != generation
    {
        return Ok(view(ReceiptState::Waiting));
    }
    let Some(_admission) = system_update::background_admission()? else {
        return Ok(view(ReceiptState::Recoverable));
    };
    let current = service.tui_backend(account.id).await?;
    if current.active != state.active
        || current.revision != state.revision
        || current.binding != state.binding
    {
        return Ok(view(ReceiptState::BindingChanged));
    }
    let pool = service.tui_database();
    if retire_orphan(&pool, row).await? {
        return Ok(view(if row.delivery_unknown() {
            ReceiptState::RecoveredDeliveryUnknown
        } else {
            ReceiptState::Recovered
        }));
    }
    match receipt_row(&pool, row.account_id, &row.id)
        .await?
        .filter(|current| current.revision() == row.revision())
        .and_then(|current| current.recovered())
    {
        Some(true) => Ok(view(ReceiptState::RecoveredDeliveryUnknown)),
        Some(false) => Ok(view(ReceiptState::Recovered)),
        None => Err(stale_receipt()),
    }
}

fn stale_receipt() -> AppError {
    AppError::Conflict("工具回执已经变化，请刷新更新页".into())
}

/// 读取管理页上的待核对回执。@param service 网关账号服务。@param after 页游标。@return 脱敏分页。
pub(crate) async fn list(service: &AccountService, after: &str) -> Result<ReceiptPage, AppError> {
    if !after.is_empty() && !valid_id(after) {
        return Err(AppError::BadRequest("工具回执页游标无效".into()));
    }
    let mut rows = receipt_page(&service.tui_database(), after, (PAGE_SIZE + 1) as i64).await?;
    let next = if rows.len() > PAGE_SIZE {
        rows.pop();
        rows.last().map(|row| row.id.clone())
    } else {
        None
    };
    let mut items = Vec::with_capacity(rows.len());
    let mut results = stream::iter(
        rows.into_iter()
            .map(|row| async move { inspect(service, &row, false).await }),
    )
    .buffered(PROBE_CONCURRENCY);
    while let Some(result) = results.next().await {
        items.push(result?);
    }
    Ok(ReceiptPage { items, next })
}

/// 立即核对并尝试恢复一条原回执。@param service 网关账号服务。@param account 原账号。
/// @param id 原记录。@param revision 管理视图看到的原阶段。@return 最终核对结果。
pub(crate) async fn recover(
    service: &AccountService,
    account: i64,
    id: &str,
    revision: &str,
) -> Result<ReceiptView, AppError> {
    if account <= 0
        || !valid_id(id)
        || revision.len() != 64
        || !revision.bytes().all(|byte| byte.is_ascii_hexdigit())
    {
        return Err(AppError::BadRequest("工具回执恢复参数无效".into()));
    }
    let row = receipt_row(&service.tui_database(), account, id)
        .await?
        .ok_or_else(stale_receipt)?;
    if row.revision() != revision || (!row.is_open() && row.recovered().is_none()) {
        return Err(stale_receipt());
    }
    inspect(service, &row, true).await
}

/// 定期分批核对持久回执，失败与失联记录保留供后续重试。@param service 网关账号服务。@return 持续运行至进程退出。
pub(super) async fn reconcile(service: Arc<AccountService>) {
    let mut timer = interval(Duration::from_secs(5));
    timer.set_missed_tick_behavior(MissedTickBehavior::Skip);
    let mut cursor = String::new();
    loop {
        timer.tick().await;
        let rows = match receipt_page(&service.tui_database(), &cursor, PAGE_SIZE as i64).await {
            Ok(rows) => rows,
            Err(error) => {
                warn!(%error, "V2 待恢复回执暂时无法读取");
                continue;
            }
        };
        if rows.len() == PAGE_SIZE {
            cursor.clone_from(&rows.last().expect("完整回执页含末条").id);
        } else {
            cursor.clear();
        }
        // 同一账号的业务锁隔离回执收口。并行探测避免失联账号拖住其他账号。
        let mut results = stream::iter(rows.into_iter().map(|row| {
            let service = service.clone();
            async move {
                if let Err(error) = inspect(&service, &row, true).await
                    && !matches!(error, AppError::Conflict(_))
                {
                    warn!(account_id = row.account_id, %error, "V2 回执暂待核对");
                }
            }
        }))
        .buffer_unordered(PROBE_CONCURRENCY);
        while results.next().await.is_some() {}
    }
}
