//! 账号级转发切换。生效值继续由 accounts.request_backend 持有。

use serde_json::{Value, json};
use std::sync::Arc;
use std::sync::atomic::Ordering;
use std::time::Duration;
use tokio::sync::{MutexGuard, OwnedRwLockReadGuard, broadcast};
use tokio::time::{MissedTickBehavior, interval};
use tracing::{debug, warn};

use crate::error::AppError;
use crate::model::account::{Account, TuiSystemPromptPolicy};
use crate::service::account::{AccountQueue, AccountService};
use crate::service::runtime_bridge::{account_config_permit, account_route_config_permit};
use crate::service::runtime_transport::{
    TuiBindingStatus, TuiReadySender, tui_fixture, tui_input_rejection, tui_same_binding,
    tui_scope, tui_switch_status, tui_transition_status,
};
use crate::service::tui_native_drain::{self, NativeTurn, TUI_V2_RECEIPT_VERSION};
use crate::store::account_store::TuiBackendSnapshot;

pub(crate) const TUI_V2: &str = "tui_v2";
pub(super) const LEGACY_BINDING: &str = "legacy:gateway";

/// 在普通槽位等待期间冻结原账号路由和 sender 代次。
pub(super) struct TuiRequestRoute {
    _route: OwnedRwLockReadGuard<()>,
    queue: Arc<AccountQueue>,
    pub(super) binding: String,
}

impl TuiRequestRoute {
    /// 在提交 V1 前登记或认领原工具组。@param service 账号服务。@param account 当前账号。
    /// @param owner 入口主体及原会话。@param version 执行合同。@param body 公开 Messages。
    /// @param binding 本次实际传输代次。@return 原生轮次。
    pub(super) async fn begin_v1(
        &self,
        service: &AccountService,
        account: &Account,
        owner: (i64, Option<&str>),
        version: &str,
        body: &Value,
        binding: String,
    ) -> Result<NativeTurn, AppError> {
        let _config = self.queue.tui_config.lock().await;
        let state = service.tui_backend(account.id).await?;
        let draining = !state.target.is_empty();
        if state.active != account.request_backend
            || (draining && tui_fixture(account) && binding != state.binding)
        {
            return Err(AppError::ServiceUnavailable(
                "原工具轮执行路径或环境代次待核对".into(),
            ));
        }
        let allow_untracked_history = !tui_fixture(account) || owner.1.is_some();
        tui_native_drain::claim(
            service.tui_database(),
            account.id,
            owner,
            version,
            body,
            binding,
            draining,
            allow_untracked_history,
        )
        .await
    }

    /// 判断该轮能否通过登记唤醒环境。@param service 账号服务。@param account 当前账号。
    /// @param continuation 是否为原工具回传。@return 是否允许唤醒。
    pub(super) async fn may_wake_v2(
        &self,
        service: &AccountService,
        account: &Account,
        continuation: bool,
    ) -> Result<bool, AppError> {
        if tui_fixture(account) {
            return Ok(true);
        }
        if continuation {
            return Ok(false);
        }
        if self.queue.runtime_gate.node_migration_draining() {
            return Err(AppError::AdmissionLimited { retry_after: 1 });
        }
        let _config = self.queue.tui_config.lock().await;
        let state = service.tui_backend(account.id).await?;
        if !state.target.is_empty() {
            return Err(AppError::AdmissionLimited { retry_after: 1 });
        }
        Ok(!tui_native_drain::occupied(service.tui_database(), account.id).await?)
    }

    /// 登记已核验 sender 上的本轮。@param service 账号服务。@param account 当前账号。
    /// @param owner 要登记的入口主体与会话。@param body 公开 Messages。@param sender 已核验 sender。
    /// @param continuation 是否为工具回传。@return 冻结的绑定、轮次和当前排空状态。
    pub(super) async fn begin_v2(
        &self,
        service: &AccountService,
        account: &Account,
        owner: Option<(i64, Option<&str>)>,
        body: &Value,
        sender: &TuiReadySender,
        continuation: bool,
        recovery: Option<tui_native_drain::ReceiptRow>,
    ) -> Result<(String, Option<NativeTurn>, bool), AppError> {
        let _config = self.queue.tui_config.lock().await;
        let mut state = service.tui_backend(account.id).await?;
        let unavailable = || sender.binding_unavailable();
        if state.active != TUI_V2 || state.binding.is_empty() {
            return Err(unavailable());
        }
        let draining = !state.target.is_empty();
        if draining && !continuation {
            return Err(AppError::AdmissionLimited { retry_after: 1 });
        }
        let same = tui_same_binding(&state.binding, &sender.key);
        if !same
            && (continuation
                || state.binding != self.binding
                || !sender.can_advance(&state.binding))
        {
            return Err(unavailable());
        }
        if state.binding != sender.key
            && !continuation
            && sender.idle
            && let Ok(_permit) = account_route_config_permit(service, account).await
            && !tui_native_drain::occupied(service.tui_database(), account.id).await?
            && idle_binding(account, &state.binding).await.as_deref() == Some(sender.key.as_str())
        {
            // 排空许可内重读编排登记和 sender 状态，确保保存的就是本次准备的代次。
            state = service
                .update_tui_backend(account.id, &state, TUI_V2, "", &sender.key)
                .await?;
        }
        if !tui_same_binding(&state.binding, &sender.key) {
            return Err(unavailable());
        }
        // 无显式会话时，原轮登记需要消息数组生成历史摘要。结构错误应保留公开输入分类。
        if !body["messages"].is_array() {
            return Err(tui_input_rejection("invalid_messages").expect("固定 Messages 输入分类"));
        }
        let turn = if let (Some(row), Some(owner)) = (recovery, owner) {
            Some(row.pending(
                service.tui_database(),
                account.id,
                &state.binding,
                owner,
                body,
            )?)
        } else if let Some(owner) = owner {
            Some(
                tui_native_drain::claim(
                    service.tui_database(),
                    account.id,
                    owner,
                    TUI_V2_RECEIPT_VERSION,
                    body,
                    state.binding.clone(),
                    draining,
                    false,
                )
                .await?,
            )
        } else {
            None
        };
        // 与对账共用路由锁；探测期间开始的任何发送都必须使旧空闲证明失效。
        self.queue
            .tui_turn_generation
            .fetch_add(1, Ordering::Relaxed);
        Ok((state.binding, turn, draining))
    }

    /// 取得发送边界的配置锁并重新确认意向。@param service 账号服务。@param id 当前账号。
    /// @param binding 本轮冻结的实际绑定。@param continuation 受信 sender 确认的原轮类别。
    /// @return 持有到发送许可确认的锁。
    pub(super) async fn allow_submit(
        &self,
        service: &AccountService,
        id: i64,
        binding: &str,
        continuation: bool,
    ) -> Result<MutexGuard<'_, ()>, AppError> {
        let config = self.queue.tui_config.lock().await;
        let state = service.tui_backend(id).await?;
        if state.active != TUI_V2 || state.binding != binding {
            return Err(AppError::ServiceUnavailable("V2 原轮环境代次待核对".into()));
        }
        if !state.target.is_empty() && !continuation {
            return Err(AppError::AdmissionLimited { retry_after: 1 });
        }
        Ok(config)
    }
}

async fn reconcile_locked(
    service: &AccountService,
    account: &Account,
    queue: &AccountQueue,
    state: TuiBackendSnapshot,
) -> Result<TuiBackendSnapshot, AppError> {
    if state.target.is_empty() {
        return Ok(state);
    }
    // 没通过响应头的旧请求仍持读锁。普通 HTTP 响应和等待工具结果分别由旧门禁与 sender 核对。
    let Ok(_route) = queue.tui_route.try_write() else {
        return Ok(state);
    };
    let fixture = tui_fixture(account);
    let unbound_v2 = state.active == TUI_V2 && state.target != TUI_V2 && state.binding.is_empty();
    if fixture
        && (tui_native_drain::occupied(service.tui_database(), account.id).await?
            || idle_binding(account, &state.binding).await.is_none())
    {
        return Ok(state);
    }
    let permit = if fixture {
        account_config_permit(service, account, true, None).await
    } else {
        // 转发方式只改 Gateway 路由，继续由编排器管理已有容器生命周期。
        account_route_config_permit(service, account)
            .await
            .map(Some)
    };
    let Ok(permit) = permit else {
        return Ok(state);
    };
    if !fixture && tui_native_drain::occupied(service.tui_database(), account.id).await? {
        return Ok(state);
    }
    let confirmed = if fixture || unbound_v2 {
        state.binding.clone()
    } else {
        let Some(binding) = idle_binding(account, &state.binding).await else {
            return Ok(state);
        };
        binding
    };
    let next_binding = if state.target == TUI_V2 {
        &confirmed
    } else {
        ""
    };
    let saved = service
        .update_tui_backend(account.id, &state, &state.target, "", next_binding)
        .await?;
    drop(permit);
    if saved.active == "native293" {
        service.request_native_wake(account.id);
    }
    Ok(saved)
}

async fn idle_binding(account: &Account, registered: &str) -> Option<String> {
    let status = tui_transition_status(account).await.ok()?;
    (status.idle && status.can_advance(registered)).then_some(status.key)
}

/// 登记、取消或尝试提交账号配置。调用方持同账号的配置序列锁。
/// @param service 账号服务。@param account 原账号。@param queue 同账号队列。
/// @param target 转发方式。@param expected 编辑时读取的修订。@return 账号管理视图。
pub(crate) async fn change_locked(
    service: &AccountService,
    account: &Account,
    queue: &AccountQueue,
    target: &str,
    expected: Option<i64>,
) -> Result<Value, AppError> {
    if !tui_scope(account) {
        return Err(AppError::BadRequest("账号没有已配置的 V2 运行环境".into()));
    }
    if expected.is_none() && !tui_fixture(account) {
        return Err(AppError::BadRequest("请提供账号转发方式的当前修订".into()));
    }
    let before = service.tui_backend(account.id).await?;
    if !matches!(target, "legacy" | "native293" | TUI_V2) {
        return Err(AppError::BadRequest("未知转发方式".into()));
    }
    let pending = if target == before.active { "" } else { target };
    // 相同意向的重试不推进配置，也不会重新执行 quiesce。
    if pending == before.target {
        let ready = tui_transition_status(account).await;
        return Ok(view(account, &before, ready.as_ref().ok()));
    }
    if expected.is_some_and(|version| version != before.revision) {
        return Err(AppError::SchedulingConflict);
    }
    let crosses_v2 = !pending.is_empty()
        && (target == TUI_V2 || before.active == TUI_V2 && !before.binding.is_empty());
    let ready = if crosses_v2 {
        tui_switch_status(account).await
    } else {
        tui_transition_status(account).await
    };
    if target == TUI_V2 && target != before.active && ready.is_err() {
        return Err(ready.unwrap_err());
    }
    let binding = if pending.is_empty() && before.active != TUI_V2 {
        ""
    } else if before.active == TUI_V2 || !before.binding.is_empty() {
        before.binding.as_str()
    } else {
        ready
            .as_ref()
            .map(|status| status.key.as_str())
            .unwrap_or("")
    };
    let saved = service
        .update_tui_backend(account.id, &before, &before.active, pending, binding)
        .await?;
    let state = reconcile_locked(service, account, queue, saved).await?;
    Ok(view(account, &state, ready.as_ref().ok()))
}

fn view(
    account: &Account,
    state: &TuiBackendSnapshot,
    runtime: Option<&TuiBindingStatus>,
) -> Value {
    let mut value = json!(account);
    attach_status(&mut value, account, state, runtime);
    value
}

/// 回报 V1 已验证的固定动作。@param value 账号管理视图。@param backend 当前生效的转发方式。@return 无。
pub(crate) fn append_v1_system_prompt(value: &mut Value, backend: &str) {
    if backend == "native293" {
        value["client_system_prompt_policy"] = json!(TuiSystemPromptPolicy::Replace);
    } else if let Some(fields) = value.as_object_mut() {
        fields.remove("client_system_prompt_policy");
    }
}

fn attach_status(
    value: &mut Value,
    account: &Account,
    state: &TuiBackendSnapshot,
    runtime: Option<&TuiBindingStatus>,
) {
    value["request_backend"] = json!(state.active);
    value["request_backend_pending"] = json!((!state.target.is_empty()).then_some(&state.target));
    value["request_backend_revision"] = json!(state.revision);
    value["tui_v2_available"] = json!(runtime.is_some_and(|status| {
        (state.active != TUI_V2 && state.binding.is_empty())
            || tui_same_binding(&state.binding, &status.key)
            || (status.idle && status.can_advance(&state.binding))
    }));
    if state.active == TUI_V2 {
        value["client_system_prompt_policy"] = json!(account.tui_system_prompt_policy);
        value["tui_system_prompt_policy_available"] = json!(runtime.is_some_and(|status| {
            status.system_prompt_policy && tui_same_binding(&state.binding, &status.key)
        }));
    } else {
        append_v1_system_prompt(value, &state.active);
    }
    if !state.target.is_empty() {
        value["request_backend_wait_reason"] = json!(if runtime
            .is_some_and(|status| status.can_advance(&state.binding))
        {
            "draining"
        } else {
            "runtime_unconfirmed"
        });
    }
}

/// 为真实账号管理视图只读查询持久状态和运行能力。
/// @param service 账号服务。@param account 原账号。@param value 原管理视图。@return 读取结果。
pub(crate) async fn append_view(
    service: &AccountService,
    account: &Account,
    value: &mut Value,
) -> Result<(), AppError> {
    if !tui_scope(account) {
        return Ok(());
    }
    let state = service.tui_backend(account.id).await?;
    attach_status(
        value,
        account,
        &state,
        tui_transition_status(account).await.as_ref().ok(),
    );
    Ok(())
}

/// 响应退场优先对账该账号。定期扫描用于补查未明状态及进程恢复后的持久意向。
/// @param service 网关账号服务。@param retirements 已归还槽位的通知。@return 持续运行至进程退出。
pub(super) async fn reconcile_intents(
    service: Arc<AccountService>,
    mut retirements: broadcast::Receiver<i64>,
) {
    let mut timer = interval(Duration::from_secs(1));
    timer.set_missed_tick_behavior(MissedTickBehavior::Skip);
    let mut terminal_cleanup = interval(Duration::from_secs(60));
    terminal_cleanup.set_missed_tick_behavior(MissedTickBehavior::Skip);
    loop {
        let (accounts, trigger) = tokio::select! {
            retired = retirements.recv() => match retired {
                Ok(id) => (vec![id], "response_retired"),
                // 通知有界。落盘意向由下次周期对账继续处理。
                Err(broadcast::error::RecvError::Lagged(_)) => continue,
                Err(broadcast::error::RecvError::Closed) => return,
            },
            _ = terminal_cleanup.tick() => {
                if let Err(error) = tui_native_drain::prune_terminal(service.tui_database()).await {
                    warn!(%error, "V2 过期终态摘要待清理");
                }
                continue;
            }
            _ = timer.tick() => {
                let accounts = sqlx::query_scalar::<_, i64>(
                    "SELECT account_id FROM tui_backend_intents WHERE target<>''",
                )
                .fetch_all(&service.tui_database())
                .await;
                let Ok(accounts) = accounts else {
                    warn!("V2 切换意向暂时无法读取");
                    continue;
                };
                (accounts, "periodic")
            }
        };
        for id in accounts {
            if let Err(error) = reconcile_account(&service, id, trigger).await {
                warn!(account_id=id, %error, "V2 切换暂待对账");
            }
        }
    }
}

async fn reconcile_account(
    service: &AccountService,
    id: i64,
    trigger: &str,
) -> Result<(), AppError> {
    let original = service.get_account(id).await?;
    if !tui_scope(&original) {
        return Ok(());
    }
    if service.tui_backend(id).await?.target.is_empty() {
        return Ok(());
    }
    let queue = service.get_or_create_queue(id, original.concurrency).await;
    let Ok(_config) = queue.tui_config.try_lock() else {
        return Ok(());
    };
    let account = service.get_account(id).await?;
    if tui_scope(&account) {
        let state = service.tui_backend(id).await?;
        if !state.target.is_empty() {
            debug!(
                account_id = id,
                trigger,
                reason = "tui_reconcile_attempt",
                "检查 V2 待切账号"
            );
            let revision = state.revision;
            let result = reconcile_locked(service, &account, &queue, state).await?;
            if result.revision != revision {
                debug!(
                    account_id = id,
                    trigger,
                    reason = "tui_reconcile_applied",
                    "已应用 V2 切换"
                );
            }
        }
    }
    Ok(())
}

/// 新请求在取得普通 HTTP 槽前只冻结生效值。V1 和 V2 续轮分别由各自可信收口数据验证。
/// @param service 账号服务。@param account 已选定账号。@return 生效账号及路由快照。
pub(super) async fn request_route(
    service: &AccountService,
    mut account: Account,
) -> Result<(Account, Option<TuiRequestRoute>), AppError> {
    if !tui_scope(&account) {
        if account.request_backend == TUI_V2 {
            return Err(AppError::ServiceUnavailable("V2 环境不可用".into()));
        }
        return Ok((account, None));
    }
    let queue = service
        .get_or_create_queue(account.id, account.concurrency)
        .await;
    // 登记和冻结在同一序列中。请求读锁不占 HTTP 槽，已有工具续轮可以同时取得读锁。
    let config = queue.tui_config.lock().await;
    account = service.get_account(account.id).await?;
    let state = service.tui_backend(account.id).await?;
    let route = queue.tui_route.clone().read_owned().await;
    drop(config);
    account.request_backend = state.active;
    let continuation_only = !state.target.is_empty();
    if continuation_only
        && tui_fixture(&account)
        && !matches!(account.request_backend.as_str(), TUI_V2 | "native293")
    {
        return Err(AppError::AdmissionLimited { retry_after: 1 });
    }
    Ok((
        account,
        Some(TuiRequestRoute {
            _route: route,
            queue,
            binding: state.binding,
        }),
    ))
}
