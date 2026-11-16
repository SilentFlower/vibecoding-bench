//! 跨服务选线的一次性授权，迟到请求不能重新取得已释放的目录许可。
use std::collections::HashMap;
use std::sync::{Arc, Mutex, Weak};

use tokio::sync::OwnedMutexGuard;
use uuid::Uuid;

use crate::error::AppError;

/// 操作票据持有目录许可；回调强引用覆盖外层请求超时。
pub(crate) struct TaskProxyTicket {
    pub id: String,
    task_id: i64,
    revision: String,
    connection: String,
    claimed_binding: Mutex<Option<Option<i64>>>,
    _permit: OwnedMutexGuard<()>,
}

/// 弱引用登记不延长事务；失效票据在下次登记时清理。
#[derive(Default)]
pub(crate) struct TaskProxyTickets(Mutex<HashMap<String, Weak<TaskProxyTicket>>>);

fn unavailable() -> AppError {
    AppError::BadRequest("代理切换授权已失效，请重新读取后操作".into())
}

impl TaskProxyTickets {
    /// 冻结已解析的选择。@param task_id 任务身份。@param revision 原版本。@param connection 目标。@param permit 目录许可。@return 活动票据。
    pub fn reserve(
        &self,
        task_id: i64,
        revision: &str,
        connection: &str,
        permit: OwnedMutexGuard<()>,
    ) -> Result<Arc<TaskProxyTicket>, AppError> {
        let ticket = Arc::new(TaskProxyTicket {
            id: Uuid::new_v4().simple().to_string(),
            task_id,
            revision: revision.into(),
            connection: connection.into(),
            claimed_binding: Mutex::new(None),
            _permit: permit,
        });
        let mut tickets = self.0.lock().map_err(|_| unavailable())?;
        tickets.retain(|_, value| value.strong_count() > 0);
        tickets.insert(ticket.id.clone(), Arc::downgrade(&ticket));
        Ok(ticket)
    }

    fn get(&self, id: &str) -> Result<Arc<TaskProxyTicket>, AppError> {
        self.0
            .lock()
            .map_err(|_| unavailable())?
            .get(id)
            .and_then(Weak::upgrade)
            .ok_or_else(unavailable)
    }

    /// 运行时登记活动后只能领取一次。@param id 操作身份。@param task_id 任务身份。@param binding 当前绑定。@param revision 原版本。@param connection 目标。@return 领取结果。
    pub fn claim(
        &self,
        id: &str,
        task_id: i64,
        binding: Option<i64>,
        revision: &str,
        connection: &str,
    ) -> Result<(), AppError> {
        let ticket = self.get(id)?;
        if ticket.task_id != task_id
            || ticket.revision != revision
            || ticket.connection != connection
        {
            return Err(unavailable());
        }
        let mut claimed = ticket.claimed_binding.lock().map_err(|_| unavailable())?;
        if claimed.is_some() {
            return Err(unavailable());
        }
        *claimed = Some(binding);
        Ok(())
    }

    /// 最终回调持有强引用，目录删除必须等待其提交完成。@param id 操作身份。@param binding 网关账号。@param connection 冻结目标。@return 包含目录许可的票据。
    pub fn gateway_commit(
        &self,
        id: &str,
        binding: i64,
        connection: &str,
    ) -> Result<Arc<TaskProxyTicket>, AppError> {
        let ticket = self.get(id)?;
        if *ticket.claimed_binding.lock().map_err(|_| unavailable())? != Some(Some(binding))
            || ticket.connection != connection
        {
            return Err(unavailable());
        }
        Ok(ticket)
    }
}

#[cfg(test)]
mod tests {
    use super::TaskProxyTickets;
    use std::sync::Arc;
    use tokio::sync::Mutex;

    #[tokio::test]
    async fn late_claim_is_revoked_and_running_callback_keeps_directory_locked() {
        let registry = TaskProxyTickets::default();
        let directory = Arc::new(Mutex::new(()));
        let ticket = registry
            .reserve(1, "version", "target", directory.clone().lock_owned().await)
            .unwrap();
        let id = ticket.id.clone();
        assert!(registry.gateway_commit(&id, 2, "target").is_err());
        assert!(
            registry
                .claim(&id, 3, Some(2), "version", "target")
                .is_err()
        );
        registry
            .claim(&id, 1, Some(2), "version", "target")
            .unwrap();
        assert!(
            registry
                .claim(&id, 1, Some(2), "version", "target")
                .is_err()
        );
        assert!(registry.gateway_commit(&id, 3, "target").is_err());
        let callback = registry.gateway_commit(&id, 2, "target").unwrap();
        drop(ticket);
        assert!(directory.try_lock().is_err());
        drop(callback);
        assert!(directory.try_lock().is_ok());
        assert!(
            registry
                .claim(&id, 1, Some(2), "version", "target")
                .is_err()
        );
        assert!(registry.gateway_commit(&id, 2, "target").is_err());
    }
}
