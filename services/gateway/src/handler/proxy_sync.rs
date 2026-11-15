//! 使用中线路的持久关联同步，逐个目标持有原配置维护门禁。
use std::sync::atomic::Ordering;
use std::time::Duration;

use crate::error::AppError;
use crate::model::proxy::{ProxyConnection, ProxySyncTarget};
use crate::service::{runtime_bridge, system_update};
use crate::store::proxy_store::ProxySyncOperation;

use super::router::{AppState, config_permit};

/// 启动单一恢复任务，启动服务和保存线路共用入口。
/// @param state 当前服务。@return 无；全部同步后释放服务引用。
pub(super) fn start(state: AppState) {
    if state.proxy_svc.sync_running.swap(true, Ordering::SeqCst) {
        return;
    }
    tokio::spawn(async move {
        loop {
            let operations = {
                let _guard = state.proxy_svc.mutations.lock().await;
                match state.proxy_svc.store.pending_sync().await {
                    Ok(operations) if operations.is_empty() => {
                        // 和保存共用锁，避免空队列退出与新任务入队之间丢失唤醒。
                        state.proxy_svc.sync_running.store(false, Ordering::SeqCst);
                        return;
                    }
                    Ok(operations) => operations,
                    Err(_) => Vec::new(),
                }
            };
            for operation in operations {
                let mut remaining = Vec::new();
                for target in &operation.remaining {
                    let _guard = state.proxy_svc.mutations.lock().await;
                    match synchronize(&state, &operation, target).await {
                        Ok(Some(next)) => remaining.push(next),
                        Ok(None) => {}
                        // 保留目标并退避；下轮从实际状态恢复，错误不携带私有连接。
                        Err(_) => remaining.push(target.clone()),
                    }
                }
                let _guard = state.proxy_svc.mutations.lock().await;
                let _ = state
                    .proxy_svc
                    .store
                    .save_sync_progress(&operation.id, &remaining)
                    .await;
            }
            tokio::time::sleep(Duration::from_secs(3)).await;
        }
    });
}

async fn synchronize(
    state: &AppState,
    operation: &ProxySyncOperation,
    target: &ProxySyncTarget,
) -> Result<Option<ProxySyncTarget>, AppError> {
    // 后台同步也登记部署活动，平台更新开始后把剩余目标留到恢复时处理。
    let _activity = system_update::admission()?;
    match target.kind.as_str() {
        "gateway" => {
            let id = target
                .id
                .parse()
                .map_err(|_| AppError::BadRequest("关联账号身份无效".into()))?;
            let account = match state.account_svc.get_account(id).await {
                Ok(account) => account,
                Err(AppError::NotFound) => return Ok(None),
                Err(error) => return Err(error),
            };
            if account.proxy_url.is_empty()
                || ProxyConnection::parse(&account.proxy_url)?.fingerprint()
                    != operation.source.fingerprint()
            {
                return Ok(None);
            }
            let _permit = config_permit(state, &account, true).await?;
            state
                .account_svc
                .synchronize_proxy_connection(&account, &operation.destination.private_url)
                .await?;
            Ok(None)
        }
        "authorization" => {
            if state.oauth_flow_svc.synchronize_proxy_connection(
                &target.id,
                &operation.source.fingerprint(),
                &operation.destination.private_url,
            ) {
                Ok(None)
            } else {
                Ok(Some(target.clone()))
            }
        }
        "task" | "draft" => {
            let result = runtime_bridge::synchronize_proxy(
                target,
                &operation.source.fingerprint(),
                &operation.destination.private_url,
            )
            .await?;
            if result["complete"] == true {
                return Ok(None);
            }
            if let Some(id) = result["gateway_account_id"].as_i64().filter(|id| *id > 0) {
                return Ok(Some(ProxySyncTarget {
                    kind: "gateway".into(),
                    id: id.to_string(),
                }));
            }
            if let Some(id) = result["task_account_id"].as_i64().filter(|id| *id > 0) {
                return Ok(Some(ProxySyncTarget {
                    kind: "task".into(),
                    id: id.to_string(),
                }));
            }
            Ok(Some(target.clone()))
        }
        _ => Err(AppError::BadRequest("关联账号类型无效".into())),
    }
}
