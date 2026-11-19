//! 账号独立工作准入；开关与准入登记共用锁，已登记请求随响应许可收尾。

use std::collections::HashMap;
use std::env;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};

use serde::{Deserialize, Serialize};
use sqlx::{AnyPool, Row};
use tokio::sync::Mutex;

use crate::error::AppError;

/// 管理端的独立工作配置和实际收尾观察。
#[derive(Clone, Debug, Serialize)]
pub struct AccountWorkSnapshot {
    pub api_accepting: bool,
    pub work_enabled: bool,
    pub revision: i64,
    pub admitted_requests: usize,
    pub phase: &'static str,
    pub coordinated: bool,
}

/// 独立控制增量，未提交字段保持原值。
#[derive(Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AccountWorkUpdate {
    pub api_accepting: Option<bool>,
    pub work_enabled: Option<bool>,
    pub expected_revision: Option<i64>,
}

struct State {
    api_accepting: bool,
    work_enabled: bool,
    revision: i64,
    active: Arc<AtomicUsize>,
}

impl State {
    fn snapshot(&self) -> AccountWorkSnapshot {
        let admitted_requests = self.active.load(Ordering::Acquire);
        AccountWorkSnapshot {
            api_accepting: self.api_accepting,
            work_enabled: self.work_enabled,
            revision: self.revision,
            admitted_requests,
            coordinated: env::var("V3_RUNTIME_URL").is_ok_and(|value| !value.is_empty()),
            phase: if self.work_enabled {
                "enabled"
            } else if admitted_requests > 0 {
                "draining"
            } else {
                "disabled"
            },
        }
    }
}

/// 一次已经接纳的请求；排队、响应和取消共用一次归还。
pub struct AccountWorkAdmission(Arc<AtomicUsize>);

impl Drop for AccountWorkAdmission {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::AcqRel);
    }
}

/// 单网关账号工作控制，数据库保留偏好，内存仅保存当前进程真实许可。
pub struct AccountWorkControls {
    pool: AnyPool,
    states: Mutex<HashMap<i64, State>>,
}

impl AccountWorkControls {
    /// 创建工作控制器。@param pool 现有账号数据库。@return 控制器。
    pub fn new(pool: AnyPool) -> Self {
        Self {
            pool,
            states: Mutex::new(HashMap::new()),
        }
    }

    async fn load(&self, states: &mut HashMap<i64, State>, id: i64) -> Result<(), AppError> {
        if states.contains_key(&id) {
            return Ok(());
        }
        let row = sqlx::query("SELECT api_accepting,work_enabled,CAST(revision AS TEXT) AS revision FROM account_work_controls WHERE account_id=$1")
            .bind(id).fetch_optional(&self.pool).await?;
        let (api_accepting, work_enabled, revision) = match row {
            Some(row) => (
                row.try_get::<i32, _>("api_accepting")? != 0,
                row.try_get::<i32, _>("work_enabled")? != 0,
                row.try_get::<String, _>("revision")?
                    .parse::<i64>()
                    .map_err(|_| AppError::Internal("账号控制版本无效".into()))?,
            ),
            None => (true, true, 0),
        };
        states.insert(
            id,
            State {
                api_accepting,
                work_enabled,
                revision,
                active: Arc::new(AtomicUsize::new(0)),
            },
        );
        Ok(())
    }

    /// 读取配置与真实在途计数。@param id 账号。@return 公开快照。
    pub async fn snapshot(&self, id: i64) -> Result<AccountWorkSnapshot, AppError> {
        let mut states = self.states.lock().await;
        self.load(&mut states, id).await?;
        Ok(states[&id].snapshot())
    }

    /// 原子登记新接单，与开关保存互斥。@param id 账号。@return 随请求释放的许可。
    pub async fn admit(&self, id: i64) -> Result<AccountWorkAdmission, AppError> {
        let mut states = self.states.lock().await;
        self.load(&mut states, id).await?;
        let state = &states[&id];
        if !state.api_accepting || !state.work_enabled {
            return Err(AppError::ServiceUnavailable("该账号已关闭 API 接单".into()));
        }
        state.active.fetch_add(1, Ordering::AcqRel);
        Ok(AccountWorkAdmission(state.active.clone()))
    }

    /// 局部保存开关，保持健康状态、凭据及已有许可。@param id 账号。@param input 增量。@return 最新快照。
    pub async fn update(
        &self,
        id: i64,
        input: AccountWorkUpdate,
    ) -> Result<AccountWorkSnapshot, AppError> {
        if input.api_accepting.is_none() && input.work_enabled.is_none() {
            return Err(AppError::BadRequest("请指定工作控制开关".into()));
        }
        let mut states = self.states.lock().await;
        self.load(&mut states, id).await?;
        let state = states.get_mut(&id).unwrap();
        if input
            .expected_revision
            .is_some_and(|revision| revision != state.revision)
        {
            return Err(AppError::BadRequest(
                "账号工作状态已变化，请刷新后重试".into(),
            ));
        }
        let api_accepting = input.api_accepting.unwrap_or(state.api_accepting);
        let work_enabled = input.work_enabled.unwrap_or(state.work_enabled);
        if api_accepting == state.api_accepting && work_enabled == state.work_enabled {
            return Ok(state.snapshot());
        }
        let revision = state.revision + 1;
        sqlx::query("INSERT INTO account_work_controls(account_id,api_accepting,work_enabled,revision) VALUES($1,$2,$3,$4) ON CONFLICT(account_id) DO UPDATE SET api_accepting=excluded.api_accepting,work_enabled=excluded.work_enabled,revision=excluded.revision")
            .bind(id).bind(i32::from(api_accepting)).bind(i32::from(work_enabled)).bind(revision)
            .execute(&self.pool).await?;
        state.api_accepting = api_accepting;
        state.work_enabled = work_enabled;
        state.revision = revision;
        Ok(state.snapshot())
    }
}

#[cfg(test)]
mod tests {
    use super::{AccountWorkControls, AccountWorkUpdate};
    use crate::store::account_work_schema;
    use sqlx::any::AnyPoolOptions;

    #[tokio::test]
    async fn close_preserves_admitted_requests_and_restart_preserves_independent_flags() {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        account_work_schema::apply(&mut *pool.acquire().await.unwrap())
            .await
            .unwrap();
        let controls = AccountWorkControls::new(pool.clone());
        let first = controls.admit(1).await.unwrap();
        let queued = controls.admit(1).await.unwrap();
        let closed = controls
            .update(
                1,
                AccountWorkUpdate {
                    api_accepting: Some(false),
                    ..Default::default()
                },
            )
            .await
            .unwrap();
        assert!(closed.work_enabled);
        assert_eq!(closed.admitted_requests, 2);
        assert!(controls.admit(1).await.is_err());
        let disabled = controls
            .update(
                1,
                AccountWorkUpdate {
                    work_enabled: Some(false),
                    ..Default::default()
                },
            )
            .await
            .unwrap();
        assert_eq!(disabled.phase, "draining");
        drop(first);
        assert_eq!(controls.snapshot(1).await.unwrap().admitted_requests, 1);
        drop(queued);
        assert_eq!(controls.snapshot(1).await.unwrap().phase, "disabled");
        let restarted = AccountWorkControls::new(pool);
        let snapshot = restarted.snapshot(1).await.unwrap();
        assert!(!snapshot.api_accepting && !snapshot.work_enabled);
        restarted
            .update(
                1,
                AccountWorkUpdate {
                    work_enabled: Some(true),
                    ..Default::default()
                },
            )
            .await
            .unwrap();
        assert!(restarted.admit(1).await.is_err());
        assert!(restarted.admit(2).await.is_ok());
    }

    #[tokio::test]
    async fn stale_control_update_keeps_newer_configuration() {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        account_work_schema::apply(&mut *pool.acquire().await.unwrap())
            .await
            .unwrap();
        let controls = AccountWorkControls::new(pool);
        controls
            .update(
                1,
                AccountWorkUpdate {
                    api_accepting: Some(false),
                    expected_revision: Some(0),
                    ..Default::default()
                },
            )
            .await
            .unwrap();
        assert!(
            controls
                .update(
                    1,
                    AccountWorkUpdate {
                        api_accepting: Some(true),
                        expected_revision: Some(0),
                        ..Default::default()
                    }
                )
                .await
                .is_err()
        );
        assert!(!controls.snapshot(1).await.unwrap().api_accepting);
    }
}
