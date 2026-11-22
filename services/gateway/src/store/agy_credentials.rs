//! 复用权威账号表，AGY 操作记录只保存阶段和归属。
use chrono::{DateTime, Utc};
use serde::Serialize;
use sqlx::Row;

use super::AccountStore;
use crate::error::AppError;
use crate::model::account::Account;

/// 不含凭据的当前管理操作状态。
#[derive(Serialize)]
pub struct AgyCredentialState {
    pub generation: i64,
    pub phase: String,
    pub operation_id: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::account::AccountAuthType;
    use crate::store::db;
    use serde_json::json;
    use sqlx::any::AnyPoolOptions;
    use std::env::temp_dir;
    use std::fs::remove_file;
    use uuid::Uuid;

    async fn fixture() -> (AccountStore, Account) {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        db::migrate(&pool, "sqlite").await.unwrap();
        sqlx::query("INSERT INTO accounts(email,token,device_id,canonical_env,canonical_prompt_env,canonical_process) VALUES('same@example.test','synthetic','device','{}','{}','{}')").execute(&pool).await.unwrap();
        let store = AccountStore::new(pool, "sqlite".into());
        let mut account = store.list().await.unwrap().remove(0);
        account.id = 0;
        account.platform = "antigravity".into();
        account.auth_type = AccountAuthType::Oauth;
        account.access_token = "synthetic-at1".into();
        account.refresh_token = "synthetic-rt1".into();
        account.expires_at = Some(Utc::now() + chrono::Duration::hours(1));
        store.create(&mut account).await.unwrap();
        (store, account)
    }

    #[tokio::test]
    async fn credential_commit_keeps_cas_with_concurrent_diagnostic_writes() {
        let (_, mut candidate) = fixture().await;
        let path = temp_dir().join(format!("agy-diagnostic-write-{}.sqlite", Uuid::new_v4()));
        let pool = db::init_db("sqlite", path.to_str().unwrap()).await.unwrap();
        db::migrate(&pool, "sqlite").await.unwrap();
        let store = AccountStore::new(pool.clone(), "sqlite".into());
        candidate.id = 0;
        store.create(&mut candidate).await.unwrap();
        for iteration in 0..8 {
            let current = store.get_by_id(candidate.id).await.unwrap();
            let operation = format!("diagnostic-overlap-{iteration}");
            let generation = store
                .begin_agy_credentials(&current, &operation, "refresh_pending")
                .await
                .unwrap();
            let mut next = current.clone();
            next.access_token = format!("synthetic-at-{iteration}");
            let writer = async {
                for _ in 0..32 {
                    sqlx::query(
                        "UPDATE settings SET value=value WHERE key='request_diagnostics_log_mode'",
                    )
                    .execute(&pool)
                    .await
                    .unwrap();
                    tokio::task::yield_now().await;
                }
            };
            let (result, _) = tokio::join!(
                store.complete_agy_observation(&current, &operation, generation, &next),
                writer
            );
            result.unwrap();
            assert_eq!(
                store.get_by_id(candidate.id).await.unwrap().access_token,
                next.access_token
            );
        }
        pool.close().await;
        remove_file(path).unwrap();
    }

    #[tokio::test]
    async fn platform_identity_paging_and_independent_options() {
        let (store, account) = fixture().await;
        assert_eq!(store.list().await.unwrap().len(), 1);
        assert_eq!(
            store.list_filtered(1, 12, "", "", "all").await.unwrap().1,
            2
        );
        assert_eq!(
            store
                .list_filtered(2, 1, "", "", "antigravity")
                .await
                .unwrap()
                .0
                .len(),
            0
        );
        assert!(!account.is_schedulable());
        assert!(!account.agy_system_prompt_homoglyph_enabled);
        let mut duplicate = account.clone();
        duplicate.id = 0;
        assert!(store.create(&mut duplicate).await.is_err());
        duplicate.email = "second@example.test".into();
        store.create(&mut duplicate).await.unwrap();
        let mut changed = account.clone();
        changed.agy_system_prompt_homoglyph_enabled = true;
        store
            .update_options(&changed, &["agy_system_prompt_homoglyph_enabled"])
            .await
            .unwrap();
        assert!(
            store
                .get_by_id(account.id)
                .await
                .unwrap()
                .agy_system_prompt_homoglyph_enabled
        );
        assert!(
            !store
                .get_by_id(duplicate.id)
                .await
                .unwrap()
                .agy_system_prompt_homoglyph_enabled
        );
        assert_eq!(
            store.platform_counts("antigravity").await.unwrap()["total"],
            2
        );
    }

    #[tokio::test]
    async fn persistent_pending_survives_second_owner_and_reconcile() {
        let (store, account) = fixture().await;
        let (first, second) = tokio::join!(
            store.begin_agy_credentials(&account, "operation-a", "refresh_pending"),
            store.begin_agy_credentials(&account, "operation-b", "refresh_pending")
        );
        assert_ne!(first.is_ok(), second.is_ok());
        let state = store.agy_credential_state(account.id).await.unwrap();
        let operation = state.operation_id.unwrap();
        store
            .reconcile_agy_credentials(account.id, &operation)
            .await
            .unwrap();
        assert!(
            store
                .begin_agy_credentials(&account, "operation-c", "refresh_pending")
                .await
                .is_err()
        );
        let mut concurrent = account.clone();
        concurrent.name = "并发备注".into();
        store.update_options(&concurrent, &["name"]).await.unwrap();
        let expiry = Utc::now() + chrono::Duration::hours(2);
        store
            .complete_agy_credentials(
                &account,
                &operation,
                1,
                "synthetic-at2",
                "synthetic-rt2",
                expiry,
            )
            .await
            .unwrap();
        store
            .complete_agy_credentials(
                &account,
                &operation,
                1,
                "synthetic-at2",
                "synthetic-rt2",
                expiry,
            )
            .await
            .unwrap();
        let saved = store.get_by_id(account.id).await.unwrap();
        assert_eq!(saved.name, "并发备注");
        assert_eq!(saved.refresh_token, "synthetic-rt2");
        assert_eq!(
            store
                .agy_credential_state(account.id)
                .await
                .unwrap()
                .generation,
            2
        );
        assert!(
            store
                .complete_agy_credentials(
                    &account,
                    "old-operation",
                    1,
                    "stale-at",
                    "stale-rt",
                    expiry
                )
                .await
                .is_err()
        );
    }

    #[tokio::test]
    async fn failed_state_commit_rolls_back_tokens_and_old_cancel_is_isolated() {
        let (store, account) = fixture().await;
        store
            .begin_agy_credentials(&account, "original", "reauth")
            .await
            .unwrap();
        store.cancel_agy_reauth(account.id, "stale").await.unwrap();
        assert_eq!(
            store.agy_credential_state(account.id).await.unwrap().phase,
            "reauth"
        );
        sqlx::query("CREATE TRIGGER synthetic_commit_failure BEFORE UPDATE OF generation ON account_credential_states BEGIN SELECT RAISE(ABORT,'synthetic'); END").execute(&store.pool).await.unwrap();
        assert!(
            store
                .complete_agy_credentials(
                    &account,
                    "original",
                    1,
                    "synthetic-at2",
                    "synthetic-rt2",
                    Utc::now() + chrono::Duration::hours(2)
                )
                .await
                .is_err()
        );
        assert_eq!(
            store.get_by_id(account.id).await.unwrap().refresh_token,
            "synthetic-rt1"
        );
        store
            .cancel_agy_reauth(account.id, "original")
            .await
            .unwrap();
        assert_eq!(
            store.agy_credential_state(account.id).await.unwrap().phase,
            "ready"
        );
        assert_eq!(
            json!(store.agy_credential_state(account.id).await.unwrap())["operation_id"],
            serde_json::Value::Null
        );
    }

    #[tokio::test]
    async fn observations_proxy_and_credentials_commit_or_rollback_together() {
        let (store, account) = fixture().await;
        let mut created = account.clone();
        created.id = 0;
        created.email = "observed@example.test".into();
        created.usage_data = json!({"platform":"antigravity","capabilities":{"source":"synthetic","observed_at_ms":1000,"models":["gemini-first"]}});
        store.create(&mut created).await.unwrap();
        assert_eq!(
            store.get_by_id(created.id).await.unwrap().usage_data,
            created.usage_data
        );
        assert!(
            store
                .get_by_id(created.id)
                .await
                .unwrap()
                .usage_fetched_at
                .is_some()
        );
        store
            .begin_agy_credentials(&created, "observed-operation", "reauth")
            .await
            .unwrap();
        let mut candidate = created.clone();
        candidate.access_token = "synthetic-observed-at".into();
        candidate.refresh_token = "synthetic-observed-rt".into();
        candidate.proxy_url = "http://new-proxy.example.test:8080".into();
        candidate.usage_data["capabilities"]["models"] = json!(["gemini-second"]);
        sqlx::query("CREATE TRIGGER synthetic_observation_failure BEFORE UPDATE OF generation ON account_credential_states BEGIN SELECT RAISE(ABORT,'synthetic'); END").execute(&store.pool).await.unwrap();
        assert!(
            store
                .complete_agy_observation(&created, "observed-operation", 1, &candidate)
                .await
                .is_err()
        );
        let unchanged = store.get_by_id(created.id).await.unwrap();
        assert_eq!(unchanged.proxy_url, created.proxy_url);
        assert_eq!(unchanged.refresh_token, created.refresh_token);
        assert_eq!(unchanged.usage_data, created.usage_data);
        sqlx::query("DROP TRIGGER synthetic_observation_failure")
            .execute(&store.pool)
            .await
            .unwrap();
        store
            .complete_agy_observation(&created, "observed-operation", 1, &candidate)
            .await
            .unwrap();
        let saved = store.get_by_id(created.id).await.unwrap();
        assert_eq!(saved.proxy_url, candidate.proxy_url);
        assert_eq!(saved.refresh_token, candidate.refresh_token);
        assert_eq!(saved.usage_data, candidate.usage_data);
    }

    #[tokio::test]
    async fn retirement_only_reopens_the_original_unfinished_generation() {
        let (store, account) = fixture().await;
        store
            .begin_agy_credentials(&account, "retired-operation", "refresh_pending")
            .await
            .unwrap();
        assert!(
            store
                .retire_agy_credentials(account.id, "retired-operation", 2)
                .await
                .is_err()
        );
        store
            .retire_agy_credentials(account.id, "retired-operation", 1)
            .await
            .unwrap();
        assert_eq!(
            store.agy_credential_state(account.id).await.unwrap().phase,
            "ready"
        );
        store
            .begin_agy_credentials(&account, "new-operation", "reauth")
            .await
            .unwrap();
        assert!(
            store
                .retire_agy_credentials(account.id, "retired-operation", 1)
                .await
                .is_err()
        );
        assert!(
            store
                .complete_agy_credentials(
                    &account,
                    "retired-operation",
                    1,
                    "stale-at",
                    "stale-rt",
                    Utc::now() + chrono::Duration::hours(1)
                )
                .await
                .is_err()
        );
        assert_eq!(
            store
                .agy_credential_state(account.id)
                .await
                .unwrap()
                .operation_id
                .as_deref(),
            Some("new-operation")
        );
    }
}

impl AccountStore {
    /// 查找同一持久操作的账号。@param operation 原操作。@return 绑定账号或空值。
    pub async fn agy_operation_account(&self, operation: &str) -> Result<Option<i64>, AppError> {
        Ok(sqlx::query_scalar(
            "SELECT account_id FROM account_credential_states WHERE operation_id=$1",
        )
        .bind(operation)
        .fetch_optional(&self.pool)
        .await?)
    }
    /// 读取当前 AGY 操作。@param id 账号。@return 阶段及代次。
    pub async fn agy_credential_state(&self, id: i64) -> Result<AgyCredentialState, AppError> {
        let row = sqlx::query("SELECT generation,phase,COALESCE(operation_id,'') AS operation_id FROM account_credential_states WHERE account_id=$1")
            .bind(id).fetch_optional(&self.pool).await?.ok_or_else(|| AppError::ServiceUnavailable("AGY 凭据归属记录缺失".into()))?;
        Ok(AgyCredentialState {
            generation: row.try_get("generation")?,
            phase: row.try_get("phase")?,
            operation_id: {
                let value: String = row.try_get("operation_id")?;
                if value.is_empty() { None } else { Some(value) }
            },
        })
    }

    /// 先持久关闭本账号的下一次刷新。@param expected 锁内权威账号。@param operation 操作ID。@param phase 新阶段。@return 冻结的原代次。
    pub async fn begin_agy_credentials(
        &self,
        expected: &Account,
        operation: &str,
        phase: &str,
    ) -> Result<i64, AppError> {
        if !expected.is_antigravity() || !["refresh_pending", "reauth"].contains(&phase) {
            return Err(AppError::BadRequest("AGY 凭据操作无效".into()));
        }
        let mut transaction = self.pool.begin().await?;
        let changed = sqlx::query("UPDATE account_credential_states SET phase=$1,operation_id=$2,updated_at_ms=$3
            WHERE account_id=$4 AND phase='ready' AND EXISTS(SELECT 1 FROM accounts WHERE id=$4 AND platform='antigravity' AND access_token=$5 AND refresh_token=$6 AND email=$7)")
            .bind(phase).bind(operation).bind(Utc::now().timestamp_millis()).bind(expected.id)
            .bind(&expected.access_token).bind(&expected.refresh_token).bind(&expected.email)
            .execute(&mut *transaction).await?.rows_affected();
        if changed != 1 {
            return Err(AppError::ServiceUnavailable(
                "AGY 原凭据操作尚待完成或对账".into(),
            ));
        }
        let generation = sqlx::query_scalar(
            "SELECT generation FROM account_credential_states WHERE account_id=$1",
        )
        .bind(expected.id)
        .fetch_one(&mut *transaction)
        .await?;
        transaction.commit().await?;
        Ok(generation)
    }

    /// 将未知结果隔离到原操作。@param id 账号。@param operation 原操作。@return 状态保存结果。
    pub async fn reconcile_agy_credentials(
        &self,
        id: i64,
        operation: &str,
    ) -> Result<(), AppError> {
        sqlx::query("UPDATE account_credential_states SET phase='reconcile',updated_at_ms=$1 WHERE account_id=$2 AND operation_id=$3 AND phase<>'ready'")
            .bind(Utc::now().timestamp_millis()).bind(id).bind(operation).execute(&self.pool).await?;
        Ok(())
    }

    /// 原子提交同代凭据及管理操作终态。@param expected 原权威账号。@param operation 原操作。@param generation 原代次。@param access 新AT。@param refresh 新RT。@param expiry 新有效期。@return 原子提交结果。
    pub async fn complete_agy_credentials(
        &self,
        expected: &Account,
        operation: &str,
        generation: i64,
        access: &str,
        refresh: &str,
        expiry: DateTime<Utc>,
    ) -> Result<(), AppError> {
        self.complete_agy_commit(
            expected, operation, generation, access, refresh, expiry, None,
        )
        .await
    }

    /// 原子提交同操作的凭据、代理及能力观测。@param expected 原权威账号。@param operation 操作。@param generation 原代次。@param candidate 已核验候选。@return 提交结果。
    pub async fn complete_agy_observation(
        &self,
        expected: &Account,
        operation: &str,
        generation: i64,
        candidate: &Account,
    ) -> Result<(), AppError> {
        let expiry = candidate
            .expires_at
            .ok_or_else(|| AppError::BadRequest("AGY 候选有效期缺失".into()))?;
        self.complete_agy_commit(
            expected,
            operation,
            generation,
            &candidate.access_token,
            &candidate.refresh_token,
            expiry,
            Some(candidate),
        )
        .await
    }

    async fn complete_agy_commit(
        &self,
        expected: &Account,
        operation: &str,
        generation: i64,
        access: &str,
        refresh: &str,
        expiry: DateTime<Utc>,
        observation: Option<&Account>,
    ) -> Result<(), AppError> {
        let mut transaction = self.pool.begin().await?;
        // 提交确认丢失后只认可同操作、同新代和完全相同的当前结果。
        if self.driver == "sqlite" {
            // 先取得写事务权限，避免诊断并发提交后把旧读快照升级为写事务时触发BUSY_SNAPSHOT。
            // 空集合更新不更改任何凭据或代次，原操作的CAS仍由下方事务一次完成。
            sqlx::query("UPDATE account_credential_states SET generation=generation WHERE 1=0")
                .execute(&mut *transaction)
                .await?;
        }
        let committed_query = format!(
            "SELECT COUNT(*) FROM accounts a JOIN account_credential_states s ON s.account_id=a.id WHERE a.id=$1 AND a.platform='antigravity' AND a.email=$2 AND a.access_token=$3 AND a.refresh_token=$4 AND s.operation_id=$5 AND s.generation=$6 AND s.phase='ready' AND a.oauth_expires_at={}",
            self.ts(7)
        );
        let committed: i64 = sqlx::query_scalar(&committed_query)
            .bind(expected.id)
            .bind(&expected.email)
            .bind(access)
            .bind(refresh)
            .bind(operation)
            .bind(generation + 1)
            .bind(self.fmt_time(expiry))
            .fetch_one(&mut *transaction)
            .await?;
        if committed == 1 {
            transaction.commit().await?;
            return Ok(());
        }
        // usage_fetched_at在历史PG结构中也是TEXT，与OAuth时间列分别使用自身类型。
        let query = format!("UPDATE accounts SET access_token=$1,refresh_token=$2,oauth_expires_at={},oauth_refreshed_at={},auth_error='',updated_at={},proxy_url=CASE WHEN $11=1 THEN $12 ELSE proxy_url END,
            usage_data=CASE WHEN $13=1 THEN $14 ELSE usage_data END,usage_fetched_at=CASE WHEN $13=1 THEN $4 ELSE usage_fetched_at END
            WHERE id=$5 AND platform='antigravity' AND email=$6 AND access_token=$7 AND refresh_token=$8
              AND EXISTS(SELECT 1 FROM account_credential_states WHERE account_id=$5 AND generation=$9 AND operation_id=$10 AND phase IN ('refresh_pending','reauth','reconcile'))", self.ts(3), self.ts(4), self.now_expr());
        let changed = sqlx::query(&query)
            .bind(access)
            .bind(refresh)
            .bind(self.fmt_time(expiry))
            .bind(self.fmt_time(Utc::now()))
            .bind(expected.id)
            .bind(&expected.email)
            .bind(&expected.access_token)
            .bind(&expected.refresh_token)
            .bind(generation)
            .bind(operation)
            .bind(i32::from(observation.is_some()))
            .bind(
                observation
                    .map(|value| value.proxy_url.as_str())
                    .unwrap_or(""),
            )
            .bind(i32::from(observation.is_some_and(|value| {
                // 仅凭据核验沿用旧观测，保持用量与原采集时间对应。
                value.usage_data != expected.usage_data
                    && value
                        .usage_data
                        .get("capabilities")
                        .is_some_and(|capabilities| !capabilities.is_null())
            })))
            .bind(
                observation
                    .map(|value| value.usage_data.to_string())
                    .unwrap_or_else(|| "null".into()),
            )
            .execute(&mut *transaction)
            .await?
            .rows_affected();
        if changed != 1 {
            return Err(AppError::BadRequest(
                "AGY 凭据代次已变化，请读取当前状态".into(),
            ));
        }
        let changed = sqlx::query("UPDATE account_credential_states SET phase='ready',generation=generation+1,updated_at_ms=$1 WHERE account_id=$2 AND generation=$3 AND operation_id=$4")
            .bind(Utc::now().timestamp_millis()).bind(expected.id).bind(generation).bind(operation)
            .execute(&mut *transaction).await?.rows_affected();
        if changed != 1 {
            return Err(AppError::BadRequest("AGY 原操作提交冲突".into()));
        }
        transaction.commit().await?;
        Ok(())
    }

    /// 按驱动持久终止证明解除同代门禁。@param id 账号。@param operation 原操作。@param generation 原代次。@return 条件提交结果。
    pub async fn retire_agy_credentials(
        &self,
        id: i64,
        operation: &str,
        generation: i64,
    ) -> Result<(), AppError> {
        let changed = sqlx::query("UPDATE account_credential_states SET phase='ready',operation_id=NULL,updated_at_ms=$1 WHERE account_id=$2 AND operation_id=$3 AND generation=$4 AND phase IN ('refresh_pending','reauth','reconcile')")
            .bind(Utc::now().timestamp_millis()).bind(id).bind(operation).bind(generation).execute(&self.pool).await?.rows_affected();
        if changed != 1 {
            return Err(AppError::BadRequest("AGY 原操作已被后续代次替代".into()));
        }
        Ok(())
    }

    /// 撤销尚未提交授权码的原操作。@param id 账号。@param operation 会话。@return 原操作是否已恢复。
    pub async fn cancel_agy_reauth(&self, id: i64, operation: &str) -> Result<(), AppError> {
        sqlx::query("UPDATE account_credential_states SET phase='ready',operation_id=NULL,updated_at_ms=$1 WHERE account_id=$2 AND operation_id=$3 AND phase='reauth'")
            .bind(Utc::now().timestamp_millis()).bind(id).bind(operation).execute(&self.pool).await?;
        Ok(())
    }
}
