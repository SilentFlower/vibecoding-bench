use chrono::Utc;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::time::{Instant, sleep};
use tracing::{debug, info, warn};

use crate::model::account::{AccountAuthType, AccountStatus, UsageQuotaState};
use crate::service::account::AccountService;
use crate::service::system_update;

/// 账户间隔,避免瞬间打爆 Anthropic usage 端点。
const PER_ACCOUNT_GAP: Duration = Duration::from_millis(500);
/// 重置扫描与失败重试分开，避免旧窗口未更新时频繁查询上游。
const RESET_SCAN_INTERVAL: Duration = Duration::from_secs(15);
const RESET_RETRY_INTERVAL: Duration = Duration::from_secs(300);

/// 旧实例按账号开关轮询，v3 仅补充已结束周期的观测。
#[derive(Clone, Copy, PartialEq, Eq)]
enum PollMode {
    Disabled,
    ConfiguredAccounts,
    ResetWindows,
}

/// 后台按账号配置或旧周期结束状态补充 OAuth 用量观测。
pub struct UsagePollerService {
    account_svc: Arc<AccountService>,
    interval: Duration,
    mode: PollMode,
}

impl UsagePollerService {
    /// 构造可由部署模式关闭的后台用量服务。
    /// @param account_svc 既有账号服务。
    /// @param interval 旧实例轮询间隔。
    /// @param enabled 是否允许按账号开关进行全量轮询。
    /// @return 后台服务实例，不修改账号的历史轮询开关。
    pub fn new(account_svc: Arc<AccountService>, interval: Duration, enabled: bool) -> Self {
        Self {
            account_svc,
            interval,
            mode: if enabled {
                PollMode::ConfiguredAccounts
            } else {
                PollMode::Disabled
            },
        }
    }

    /// 创建仅刷新旧周期已结束账号的 v3 后台服务。
    /// @param account_svc 复用手动刷新与凭据归属规则的账号服务。
    /// @return 每 15 秒扫描、同账号至少间隔 5 分钟的刷新服务。
    pub fn for_resets(account_svc: Arc<AccountService>) -> Self {
        Self {
            account_svc,
            interval: RESET_SCAN_INTERVAL,
            mode: PollMode::ResetWindows,
        }
    }

    /// 启动后台循环；显式禁用时直接返回。
    /// @return 无返回值，启用时持续轮询。
    pub async fn run(self: Arc<Self>) {
        if self.mode == PollMode::Disabled {
            return;
        }
        info!("usage poller: started, interval = {:?}", self.interval);
        // 启动后先等一个 interval,避免和应用冷启动抢资源
        sleep(self.interval).await;
        let mut attempts = HashMap::new();
        loop {
            self.tick(&mut attempts).await;
            sleep(self.interval).await;
        }
    }

    async fn tick(&self, attempts: &mut HashMap<i64, Instant>) {
        let Ok(_update_activity) = system_update::admission() else {
            return;
        };
        let accounts = match self.account_svc.list_accounts().await {
            Ok(list) => list,
            Err(e) => {
                warn!("usage poller: list accounts failed: {}", e);
                return;
            }
        };

        attempts.retain(|id, _| accounts.iter().any(|account| account.id == *id));
        let now = Utc::now().timestamp_millis();
        let targets: Vec<i64> = accounts
            .iter()
            .filter(|a| {
                a.auth_type == AccountAuthType::Oauth
                    && a.status == AccountStatus::Active
                    && match self.mode {
                        PollMode::ConfiguredAccounts => a.auto_poll_usage,
                        PollMode::ResetWindows => {
                            a.usage_quota(now).state == UsageQuotaState::ResetPending
                                && attempts
                                    .get(&a.id)
                                    .is_none_or(|at| at.elapsed() >= RESET_RETRY_INTERVAL)
                        }
                        PollMode::Disabled => false,
                    }
            })
            .map(|a| a.id)
            .collect();

        debug!("usage poller: polling {} oauth accounts", targets.len());

        for id in targets {
            if self.mode == PollMode::ResetWindows {
                attempts.insert(id, Instant::now());
                // 手动刷新或业务被动观测可能已推进周期，发送前重新读取以避免重复查询。
                let Ok(account) = self.account_svc.get_account(id).await else {
                    continue;
                };
                if account.status != AccountStatus::Active
                    || account.usage_quota(Utc::now().timestamp_millis()).state
                        != UsageQuotaState::ResetPending
                {
                    continue;
                }
            }
            match self.account_svc.refresh_usage(id).await {
                Ok(_) => debug!("usage poller: refreshed account {}", id),
                Err(e) => warn!("usage poller: account {} failed: {}", id, e),
            }
            sleep(PER_ACCOUNT_GAP).await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{RESET_RETRY_INTERVAL, UsagePollerService};
    use crate::service::account::AccountService;
    use crate::store::account_store::AccountStore;
    use crate::store::db;
    use crate::store::memory::MemoryStore;
    use crate::store::settings_store::SettingsStore;
    use chrono::{Duration as ChronoDuration, Utc};
    use serde_json::json;
    use sqlx::any::{AnyPoolOptions, install_default_drivers};
    use std::collections::HashMap;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::time::Duration;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;
    use tokio::time::{Instant, timeout};

    /// 重置扫描只请求到期的活动 OAuth 账号，失败冷却后重试，新观测到来后停止。
    #[tokio::test]
    async fn reset_refresh_targets_expired_windows_and_throttles_retries() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        db::migrate(&pool, "sqlite").await.unwrap();
        let proxy = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let proxy_url = format!("http://{}", proxy.local_addr().unwrap());
        let expired = json!({"five_hour":{"utilization":90,"resets_at":Utc::now()-ChronoDuration::seconds(1)}});
        let fresh =
            json!({"five_hour":{"utilization":20,"resets_at":Utc::now()+ChronoDuration::hours(1)}});
        for (id, status, auth_type, poll, usage) in [
            (1, "active", "oauth", 0, expired.clone()),
            (2, "active", "oauth", 1, fresh.clone()),
            (3, "active", "oauth", 1, json!({})),
            (4, "disabled", "oauth", 1, expired.clone()),
            (5, "active", "setup_token", 1, expired.clone()),
            (
                6,
                "active",
                "oauth",
                1,
                json!({"five_hour":{"utilization":0,"resets_at":null}}),
            ),
        ] {
            sqlx::query("INSERT INTO accounts(id,name,email,token,device_id,status,auth_type,access_token,refresh_token,oauth_expires_at,proxy_url,auto_poll_usage,usage_data) VALUES($1,$2,$3,'synthetic','synthetic-device',$4,$5,'synthetic','synthetic-refresh','2050-01-01T00:00:00Z',$6,$7,$8)")
                .bind(id).bind(format!("合成账号-{id}")).bind(format!("reset-{id}@example.invalid"))
                .bind(status).bind(auth_type).bind(&proxy_url).bind(poll).bind(usage.to_string())
                .execute(&pool).await.unwrap();
        }
        let service = Arc::new(AccountService::new(
            Arc::new(AccountStore::new(pool.clone(), "sqlite".into())),
            Arc::new(MemoryStore::new()),
            Arc::new(SettingsStore::new(pool.clone())),
        ));
        let poller = UsagePollerService::for_resets(service);
        let connections = Arc::new(AtomicUsize::new(0));
        let observed = connections.clone();
        let responder = tokio::spawn(async move {
            loop {
                let (mut stream, _) = proxy.accept().await.unwrap();
                let mut headers = [0; 4096];
                stream.read(&mut headers).await.unwrap();
                observed.fetch_add(1, Ordering::SeqCst);
                stream.write_all(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").await.unwrap();
            }
        });
        let mut attempts = HashMap::new();
        timeout(Duration::from_secs(5), poller.tick(&mut attempts))
            .await
            .unwrap();
        assert_eq!(connections.load(Ordering::SeqCst), 1);
        assert_eq!(attempts.len(), 1);
        poller.tick(&mut attempts).await;
        assert_eq!(connections.load(Ordering::SeqCst), 1);
        attempts.insert(1, Instant::now() - RESET_RETRY_INTERVAL);
        timeout(Duration::from_secs(5), poller.tick(&mut attempts))
            .await
            .unwrap();
        assert_eq!(connections.load(Ordering::SeqCst), 2);
        sqlx::query("UPDATE accounts SET usage_data=$1 WHERE id=1")
            .bind(fresh.to_string())
            .execute(&pool)
            .await
            .unwrap();
        attempts.insert(1, Instant::now() - RESET_RETRY_INTERVAL);
        poller.tick(&mut attempts).await;
        assert_eq!(connections.load(Ordering::SeqCst), 2);
        responder.abort();
        let _ = responder.await;
    }

    /// 同一真实轮询账号在 v3 禁用时零连接，在旧模式仍能请求所配置代理。
    /// @return 测试成功无返回值。
    #[tokio::test]
    async fn disabled_mode_does_not_poll_account_but_legacy_mode_does() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .expect("pool");
        db::migrate(&pool, "sqlite").await.expect("schema");
        let proxy = TcpListener::bind("127.0.0.1:0").await.expect("proxy");
        let url = format!("http://{}", proxy.local_addr().expect("address"));
        sqlx::query("INSERT INTO accounts(name,email,token,device_id,auth_type,access_token,refresh_token,oauth_expires_at,proxy_url,auto_poll_usage) VALUES('fixture','fixture@example.invalid','synthetic','synthetic-device','oauth','synthetic','synthetic-refresh','2050-01-01T00:00:00Z',$1,1)")
            .bind(url)
            .execute(&pool)
            .await
            .expect("account");
        let account_svc = Arc::new(AccountService::new(
            Arc::new(AccountStore::new(pool.clone(), "sqlite".into())),
            Arc::new(MemoryStore::new()),
            Arc::new(SettingsStore::new(pool)),
        ));
        let account = account_svc
            .list_accounts()
            .await
            .expect("accounts")
            .remove(0);
        assert!(account.auto_poll_usage, "fixture must enable polling");
        assert!(
            account.expires_at.is_some(),
            "fixture token must have expiry"
        );
        let disabled = Arc::new(UsagePollerService::new(
            account_svc.clone(),
            Duration::from_millis(1),
            false,
        ));
        timeout(Duration::from_millis(100), disabled.run())
            .await
            .expect("disabled service must return");
        assert!(
            timeout(Duration::from_millis(25), proxy.accept())
                .await
                .is_err()
        );
        let enabled = Arc::new(UsagePollerService::new(
            account_svc.clone(),
            Duration::from_millis(1),
            true,
        ));
        let task = tokio::spawn(enabled.run());
        let connection = timeout(Duration::from_secs(3), proxy.accept()).await;
        task.abort();
        let _ = task.await;
        assert!(
            connection.is_ok(),
            "legacy polling must still use its proxy"
        );
    }
}
