//! AGY 工具批次回执，状态更新只接受当前请求所有者。
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use sqlx::{AnyPool, Row};

use crate::error::AppError;
use crate::service::runtime_transport::now_ms;

use super::replay::SortedJson;
use super::{AGY_REQUEST_SECONDS, AGY_TOOL_WAIT_LIMIT};

/// 原始批次及允许查找的别名。
pub(super) struct BatchKey {
    pub(super) exact: String,
    token: i64,
    calls: String,
    prefix: String,
    pub(super) shape: String,
}

impl BatchKey {
    /// 基于同一调用范围记录严格身份、稳定 ID 及缺 ID 的历史别名。
    /// @param token 调用方。@param model 公开型号。@param prefix 原历史。@param calls 按序调用。@return 已规范化的键。
    pub(super) fn new(token: i64, model: &str, prefix: &[Value], calls: &[Value]) -> Self {
        let prefix: Vec<_> = prefix.iter().map(SortedJson).collect();
        let empty = Value::Object(Default::default());
        let arguments: Vec<_> = calls
            .iter()
            .map(|call| {
                (
                    &call["name"],
                    SortedJson(call.get("args").unwrap_or(&empty)),
                )
            })
            .collect();
        let ids: Option<Vec<_>> = calls
            .iter()
            .map(|call| call["id"].as_str().filter(|id| !id.is_empty()))
            .collect();
        // 别名也要能发现其他令牌持有的旧批次，严格主键才按调用人隔离。
        let by_prefix = digest((model, &prefix, &arguments));
        Self {
            exact: digest((token, &by_prefix, &ids)),
            token,
            calls: ids.map_or_else(String::new, |ids| digest((model, ids))),
            prefix: by_prefix,
            shape: digest(&arguments),
        }
    }
}

pub(super) fn digest(value: impl Serialize) -> String {
    let mut hash = Sha256::new();
    serde_json::to_writer(&mut hash, &value).expect("已验证的 JSON 可序列化");
    format!("{:x}", hash.finalize())
}

/// 单条受信回执的快照。
#[derive(Clone)]
pub(super) struct Receipt {
    pub(super) key: String,
    pub(super) token: i64,
    pub(super) account: i64,
    pub(super) scope: String,
    pub(super) shape: String,
    pub(super) source: String,
    pub(super) attempt: String,
    pub(super) body: String,
    pub(super) phase: String,
    pub(super) recovered: bool,
    pub(super) signatures: Vec<Option<String>>,
}

#[derive(Clone)]
pub(super) struct ReceiptStore(pub(super) AnyPool);

fn storage_error(error: sqlx::Error) -> AppError {
    tracing::error!(error = %error, "AGY工具回执存储失败");
    AppError::ServiceUnavailable("AGY工具回执暂时不可用".into())
}

fn expires() -> i64 {
    (now_ms() + (AGY_TOOL_WAIT_LIMIT.as_secs() + AGY_REQUEST_SECONDS as u64) * 1000) as i64
}

pub(super) fn session_scope(session: Option<&str>) -> String {
    session.map_or_else(String::new, digest)
}

impl ReceiptStore {
    /// 登记实际发布的工具批次或合法的历史起点。
    /// @param key 批次身份。@param account 已授权账号。@param scope 会话摘要。
    /// @param source 原生工具轮的 HTTP 根。@param signatures 源签名摘要。@return 当前请求成功登记时为真。
    pub(super) async fn insert(
        &self,
        key: &BatchKey,
        account: i64,
        scope: &str,
        source: Option<&str>,
        signatures: &[Option<String>],
    ) -> Result<bool, AppError> {
        sqlx::query("DELETE FROM agy_tool_receipts WHERE expires_ms <= $1")
            .bind(now_ms() as i64)
            .execute(&self.0)
            .await
            .map_err(storage_error)?;
        let new = sqlx::query(
            "INSERT INTO agy_tool_receipts VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'','',$9,0,$10,$11,$12)
             ON CONFLICT(batch_key) DO NOTHING",
        )
        .bind(&key.exact)
        .bind(&key.calls)
        .bind(&key.prefix)
        .bind(&key.shape)
        .bind(key.token)
        .bind(account)
        .bind(scope)
        .bind(source.unwrap_or_default())
        .bind(if source.is_some() { "waiting" } else { "ready" })
        .bind(i64::from(source.is_none()))
        .bind(expires())
        .bind(serde_json::to_string(signatures).expect("固定的签名摘要可序列化"))
        .execute(&self.0)
        .await
        .map_err(storage_error)?;
        Ok(new.rows_affected() == 1)
    }

    /// 严格身份优先，省略 ID 时用同前缀且唯一的批次。
    /// @param key 入站批次身份。@return 严格或唯一别名，多个别名属冲突。
    pub(super) async fn find(&self, key: &BatchKey) -> Result<Option<Receipt>, AppError> {
        let rows = sqlx::query(
            "SELECT batch_key,call_shape,token_id,account_id,session_scope,source_id,attempt_id,body_key,phase,recovered,signature_keys
             FROM agy_tool_receipts
             WHERE expires_ms > $4 AND (batch_key=$1 OR (call_key=$2 AND $2<>'')
                 OR (prefix_key=$3 AND ($2='' OR call_key='')))
             ORDER BY CASE WHEN batch_key=$1 THEN 0 ELSE 1 END LIMIT 2",
        )
        .bind(&key.exact).bind(&key.calls).bind(&key.prefix).bind(now_ms() as i64)
        .fetch_all(&self.0).await.map_err(storage_error)?;
        let Some(row) = rows.first() else {
            return Ok(None);
        };
        let found: String = row.try_get("batch_key").map_err(storage_error)?;
        if found != key.exact && rows.len() > 1 {
            return Err(super::tool_mismatch(None));
        }
        let signatures: String = row.try_get("signature_keys").map_err(storage_error)?;
        let signatures = serde_json::from_str(&signatures)
            .map_err(|_| AppError::ServiceUnavailable("AGY工具签名回执无效".into()))?;
        Ok(Some(Receipt {
            key: found,
            token: row.try_get("token_id").map_err(storage_error)?,
            account: row.try_get("account_id").map_err(storage_error)?,
            scope: row.try_get("session_scope").map_err(storage_error)?,
            shape: row.try_get("call_shape").map_err(storage_error)?,
            source: row.try_get("source_id").map_err(storage_error)?,
            attempt: row.try_get("attempt_id").map_err(storage_error)?,
            body: row.try_get("body_key").map_err(storage_error)?,
            phase: row.try_get("phase").map_err(storage_error)?,
            recovered: row.try_get::<i64, _>("recovered").map_err(storage_error)? != 0,
            signatures,
        }))
    }

    /// 比较并取得原批次的准备权。@param previous 原快照。@param attempt 本次请求。@param body 正文摘要。@return 取得准备权。
    pub(super) async fn prepare(
        &self,
        previous: &Receipt,
        attempt: &str,
        body: &str,
        scope: &str,
    ) -> Result<bool, AppError> {
        let row = sqlx::query(
            "UPDATE agy_tool_receipts SET phase='preparing',attempt_id=$1,body_key=$2,
                recovered=$3,expires_ms=$4,session_scope=CASE WHEN session_scope='' THEN $9 ELSE session_scope END
             WHERE batch_key=$5 AND (phase=$6 OR ($6='waiting' AND phase='ready'))
                 AND attempt_id=$7 AND expires_ms>$8
                 AND (session_scope='' OR session_scope=$9)",
        )
        .bind(attempt).bind(body).bind(i64::from(previous.recovered || previous.phase == "retry"))
        .bind(expires()).bind(&previous.key).bind(&previous.phase).bind(&previous.attempt)
        .bind(now_ms() as i64).bind(scope).execute(&self.0).await.map_err(storage_error)?;
        Ok(row.rows_affected() == 1)
    }

    /// 准备失败时只恢复当前准备权持有者的旧状态。@param previous 原快照。@param attempt 本次请求。@return 回执更新。
    pub(super) async fn abandon(&self, previous: &Receipt, attempt: &str) -> Result<(), AppError> {
        self.restore(previous, attempt, "preparing").await
    }

    /// 撤销已确认未进入模型调用的输入拒绝。@param previous 原快照。@param attempt 本次请求。@return 更新结果。
    pub(super) async fn rejected_input(
        &self,
        previous: &Receipt,
        attempt: &str,
    ) -> Result<(), AppError> {
        self.restore(previous, attempt, "sending").await
    }

    async fn restore(
        &self,
        previous: &Receipt,
        attempt: &str,
        phase: &str,
    ) -> Result<(), AppError> {
        sqlx::query(
            "UPDATE agy_tool_receipts SET phase=CASE WHEN $1='waiting' AND source_closed=1 THEN 'ready' ELSE $1 END,
                attempt_id=$2,body_key=$3,recovered=$4
             WHERE batch_key=$5 AND attempt_id=$6 AND phase=$7",
        )
        .bind(&previous.phase).bind(&previous.attempt).bind(&previous.body)
        .bind(i64::from(previous.recovered)).bind(&previous.key).bind(attempt)
        .bind(phase)
        .execute(&self.0).await.map_err(storage_error)?;
        Ok(())
    }

    /// 以原尝试身份交接发送边界或终态。@param key 批次。@param attempt 请求。@param from 旧阶段。@param to 新阶段。@return 交接成功。
    pub(super) async fn transition(
        &self,
        key: &str,
        attempt: &str,
        from: &str,
        to: &str,
    ) -> Result<bool, AppError> {
        let row = sqlx::query(
            "UPDATE agy_tool_receipts SET phase=$1,expires_ms=$2
             WHERE batch_key=$3 AND attempt_id=$4 AND phase=$5",
        )
        .bind(to)
        .bind(expires())
        .bind(key)
        .bind(attempt)
        .bind(from)
        .execute(&self.0)
        .await
        .map_err(storage_error)?;
        Ok(row.rows_affected() == 1)
    }

    /// 只有同一原生源轮结束才能解除等待状态。
    /// @param key 批次。@param source 原 HTTP 根。@return 状态更新。
    pub(super) async fn source_closed(&self, key: &str, source: &str) -> Result<(), AppError> {
        sqlx::query(
            "UPDATE agy_tool_receipts SET source_closed=1,phase=CASE WHEN phase='waiting' THEN 'ready' ELSE phase END
             WHERE batch_key=$1 AND source_id=$2",
        )
        .bind(key).bind(source).execute(&self.0).await.map_err(storage_error)?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;
    use sqlx::any::{AnyPoolOptions, install_default_drivers};

    use super::{BatchKey, ReceiptStore};

    async fn exercise(dsn: &str, driver: &str) {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(if driver == "sqlite" { 1 } else { 4 })
            .connect(dsn)
            .await
            .unwrap();
        crate::store::db::migrate(&pool, driver).await.unwrap();
        let store = ReceiptStore(pool.clone());
        let source = uuid::Uuid::new_v4().to_string();
        let calls = [json!({"id":source,"name":"Read","args":{"n":1}})];
        let prefix = [json!({"role":"user","parts":[{"text":"Fixture"}]})];
        let key = BatchKey::new(7, "fixture", &prefix, &calls);
        assert!(
            store
                .insert(&key, 18, "session", Some(&source), &[None])
                .await
                .unwrap()
        );
        let waiting = store.find(&key).await.unwrap().unwrap();
        assert_eq!(waiting.phase, "waiting");
        assert!(
            !store
                .prepare(&waiting, "wrong-session", "same-body", "other")
                .await
                .unwrap()
        );
        store
            .source_closed(&key.exact, "different-source")
            .await
            .unwrap();
        assert_eq!(store.find(&key).await.unwrap().unwrap().phase, "waiting");
        store.source_closed(&key.exact, &source).await.unwrap();
        let ready = store.find(&key).await.unwrap().unwrap();
        assert_eq!(ready.phase, "ready");
        let (left, right) = tokio::join!(
            store.prepare(&ready, "first", "same-body", "session"),
            store.prepare(&ready, "parallel", "same-body", "session"),
        );
        let winner = if left.unwrap() {
            assert!(!right.unwrap());
            "first"
        } else {
            assert!(right.unwrap());
            "parallel"
        };
        assert!(
            store
                .transition(&key.exact, winner, "preparing", "sending")
                .await
                .unwrap()
        );
        store.abandon(&ready, winner).await.unwrap();
        assert_eq!(store.find(&key).await.unwrap().unwrap().phase, "sending");
        assert!(
            store
                .transition(&key.exact, winner, "sending", "retry")
                .await
                .unwrap()
        );

        // 新服务只持有同一数据库的记录，旧尝试的帧及内存许可已丢失。
        let restarted = ReceiptStore(pool.clone());
        let retry = restarted.find(&key).await.unwrap().unwrap();
        assert_eq!(retry.body, "same-body");
        assert!(
            restarted
                .prepare(&retry, "recovery", "same-body", "session")
                .await
                .unwrap()
        );
        assert!(
            !restarted
                .prepare(&retry, "duplicate", "same-body", "session")
                .await
                .unwrap()
        );
        assert!(
            restarted
                .transition(&key.exact, "recovery", "preparing", "sending")
                .await
                .unwrap()
        );
        assert!(
            restarted
                .transition(&key.exact, "recovery", "sending", "failed")
                .await
                .unwrap()
        );
        let final_entry = restarted.find(&key).await.unwrap().unwrap();
        assert_eq!(final_entry.phase, "failed");
        assert!(final_entry.recovered);
        let other_token = BatchKey::new(8, "fixture", &prefix, &calls);
        assert_eq!(
            restarted.find(&other_token).await.unwrap().unwrap().token,
            7
        );
        let omitted = [json!({"name":"Read","args":{"n":1}})];
        let other_token = BatchKey::new(8, "fixture", &prefix, &omitted);
        assert_eq!(
            restarted.find(&other_token).await.unwrap().unwrap().token,
            7
        );
        pool.close().await;
    }

    #[tokio::test]
    async fn sqlite_receipt_claim_and_recovery_are_atomic() {
        exercise("sqlite::memory:", "sqlite").await;
    }

    #[tokio::test]
    #[ignore = "需要独立 PostgreSQL 测试库"]
    async fn postgres_receipt_claim_and_recovery_are_atomic() {
        exercise(
            &std::env::var("AGY_RECEIPT_TEST_POSTGRES").unwrap(),
            "postgres",
        )
        .await;
    }
}
