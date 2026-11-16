//! 会话封禁的原子轮次、命中计数和安全分页。

use sqlx::{AnyPool, Row, any::AnyRow};
use uuid::Uuid;

use crate::error::AppError;
use crate::model::session_policy_block::{
    SessionPolicyBlock, SessionPolicyBlockPage, SessionPolicyIdentity,
};

const COLUMNS: &str = "b.id,b.session_key,CAST(b.api_token_id AS TEXT) AS api_token_id,
    COALESCE(t.name,'') AS token_name,CAST(b.account_id AS TEXT) AS account_id,COALESCE(a.name,'') AS account_name,
    b.model,b.reason,COALESCE(b.source_request_id,'') AS source_request_id,CAST(b.blocked_at_ms AS TEXT) AS blocked_at_ms,
    CAST(b.expires_at_ms AS TEXT) AS expires_at_ms,COALESCE(CAST(b.released_at_ms AS TEXT),'') AS released_at_ms,
    CAST(b.blocked_request_count AS TEXT) AS blocked_request_count,
    COALESCE(CAST(b.last_blocked_at_ms AS TEXT),'') AS last_blocked_at_ms";
const JOINS: &str = "FROM session_policy_blocks b LEFT JOIN api_tokens t ON t.id=b.api_token_id LEFT JOIN accounts a ON a.id=b.account_id";
const FILTER: &str =
    "WHERE ($1='all' OR ($1='active' AND b.released_at_ms IS NULL AND b.expires_at_ms>$3)
    OR ($1='expired' AND b.released_at_ms IS NULL AND b.expires_at_ms<=$3)
    OR ($1='released' AND b.released_at_ms IS NOT NULL)) AND b.session_key LIKE $2";

/// 复用现有 SQLite 或 PostgreSQL 连接池。
#[derive(Clone)]
pub struct SessionPolicyBlockStore {
    pool: AnyPool,
}

impl SessionPolicyBlockStore {
    /// 创建会话封禁存储。
    /// @param pool 已初始化的业务连接池。
    /// @return 存储实例。
    pub fn new(pool: AnyPool) -> Self {
        Self { pool }
    }

    /// 读取有效封禁并原子增加本次实际拦截计数。
    /// @param key 真实客户端会话的隔离摘要。
    /// @param now 当前 UTC 毫秒。
    /// @return 有效封禁或空；存储失败停止放行。
    pub async fn hit(&self, key: &str, now: i64) -> Result<Option<SessionPolicyBlock>, AppError> {
        let sql = format!(
            "UPDATE session_policy_blocks SET blocked_request_count=blocked_request_count+1,last_blocked_at_ms=$2 WHERE id=(SELECT id FROM session_policy_blocks WHERE session_key=$1 AND released_at_ms IS NULL AND expires_at_ms>$2 ORDER BY blocked_at_ms DESC,id DESC LIMIT 1) RETURNING id"
        );
        // RETURNING首行可能早于SQLite隐式事务提交；读完结果后才向其它连接发布拦截成功。
        let ids: Vec<String> = sqlx::query_scalar(&sql)
            .bind(key)
            .bind(now)
            .fetch_all(&self.pool)
            .await
            .map_err(unavailable)?;
        match ids.first() {
            Some(id) => self.get(id, now).await.map(Some),
            None => Ok(None),
        }
    }

    /// 原子创建一轮封禁，有效轮次内重复拒答复用原到期时间。
    /// @param identity 本次入站匿名身份。
    /// @param account_id 实际触发拒答的账号。
    /// @param reason 已校验的原因分类。
    /// @param now 当前 UTC 毫秒。
    /// @param duration_ms 首次拒答采用的封禁时长。
    /// @return 写入成功或存储错误。
    pub(crate) async fn remember(
        &self,
        identity: &SessionPolicyIdentity,
        account_id: i64,
        reason: &str,
        now: i64,
        duration_ms: i64,
    ) -> Result<(), AppError> {
        let expires = now
            .checked_add(duration_ms)
            .ok_or_else(|| AppError::BadRequest("封禁时长超出范围".into()))?;
        let mut transaction = self.pool.begin().await.map_err(unavailable)?;
        sqlx::query("INSERT INTO session_policy_block_keys(session_key) VALUES($1) ON CONFLICT(session_key) DO NOTHING")
            .bind(&identity.session_key).execute(&mut *transaction).await.map_err(unavailable)?;
        // SQLite 的写锁与 PostgreSQL 的行锁都由数据库事务持有，跨连接合并同一轮次。
        sqlx::query(
            "UPDATE session_policy_block_keys SET revision=revision+1 WHERE session_key=$1",
        )
        .bind(&identity.session_key)
        .execute(&mut *transaction)
        .await
        .map_err(unavailable)?;
        let existing: Option<String> = sqlx::query_scalar("SELECT id FROM session_policy_blocks WHERE session_key=$1 AND released_at_ms IS NULL AND expires_at_ms>$2 LIMIT 1")
            .bind(&identity.session_key).bind(now).fetch_optional(&mut *transaction).await.map_err(unavailable)?;
        if existing.is_none() {
            sqlx::query("INSERT INTO session_policy_blocks(id,session_key,api_token_id,account_id,model,reason,source_request_id,blocked_at_ms,expires_at_ms) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)")
                .bind(Uuid::new_v4().to_string()).bind(&identity.session_key).bind(identity.api_token_id)
                .bind(account_id).bind(&identity.model).bind(reason).bind(&identity.source_request_id)
                .bind(now).bind(expires).execute(&mut *transaction).await.map_err(unavailable)?;
        }
        transaction.commit().await.map_err(unavailable)?;
        Ok(())
    }

    /// 分页读取有效及历史轮次，读取保持状态不变。
    /// @param state 已校验的状态筛选。
    /// @param prefix 已校验的匿名标识前缀。
    /// @param page 从一开始的页码。
    /// @param size 每页条数。
    /// @param now 同一查询快照的 UTC 毫秒。
    /// @return 安全分页结果。
    pub async fn list(
        &self,
        state: &str,
        prefix: &str,
        page: i64,
        size: i64,
        now: i64,
    ) -> Result<SessionPolicyBlockPage, AppError> {
        let pattern = format!("{prefix}%");
        let total: String =
            sqlx::query_scalar(&format!("SELECT CAST(COUNT(*) AS TEXT) {JOINS} {FILTER}"))
                .bind(state)
                .bind(&pattern)
                .bind(now)
                .fetch_one(&self.pool)
                .await?;
        let rows = sqlx::query(&format!("SELECT {COLUMNS} {JOINS} {FILTER} ORDER BY b.blocked_at_ms DESC,b.id DESC LIMIT $4 OFFSET $5"))
            .bind(state).bind(&pattern).bind(now).bind(size).bind((page-1).checked_mul(size).ok_or_else(|| AppError::BadRequest("页码过大".into()))?)
            .fetch_all(&self.pool).await?;
        Ok(SessionPolicyBlockPage {
            items: rows
                .iter()
                .map(|r| from_row(r, now))
                .collect::<Result<_, _>>()?,
            total: total
                .parse()
                .map_err(|_| AppError::Internal("封禁计数无效".into()))?,
            page,
            page_size: size,
            observed_at_ms: now,
        })
    }

    /// 提前解除单轮封禁，重复解除保持首次时间。
    /// @param id 管理列表的轮次 UUID。
    /// @param now 当前 UTC 毫秒。
    /// @return 解除后的安全摘要。
    pub async fn release(&self, id: &str, now: i64) -> Result<SessionPolicyBlock, AppError> {
        let changed = sqlx::query("UPDATE session_policy_blocks SET released_at_ms=COALESCE(released_at_ms,$2) WHERE id=$1")
            .bind(id).bind(now).execute(&self.pool).await?;
        if changed.rows_affected() == 0 {
            return Err(AppError::NotFound);
        }
        self.get(id, now).await
    }

    async fn get(&self, id: &str, now: i64) -> Result<SessionPolicyBlock, AppError> {
        let row = sqlx::query(&format!("SELECT {COLUMNS} {JOINS} WHERE b.id=$1"))
            .bind(id)
            .fetch_one(&self.pool)
            .await
            .map_err(unavailable)?;
        from_row(&row, now)
    }
}

fn unavailable(error: sqlx::Error) -> AppError {
    tracing::error!(error=%error,"会话封禁存储访问失败");
    AppError::ServiceUnavailable("会话封禁状态暂时不可用，请稍后重试".into())
}

fn integer(row: &AnyRow, name: &str) -> Result<i64, AppError> {
    row.try_get::<String, _>(name)?
        .parse()
        .map_err(|_| AppError::Internal("封禁时间或计数无效".into()))
}

// SQLx Any 的 NULL 运行时类型需要显式文本投影，再恢复可选语义。
fn optional_text(row: &AnyRow, name: &str) -> Result<Option<String>, AppError> {
    let value: String = row.try_get(name)?;
    Ok((!value.is_empty()).then_some(value))
}

fn optional_integer(row: &AnyRow, name: &str) -> Result<Option<i64>, AppError> {
    optional_text(row, name)?
        .map(|v| {
            v.parse()
                .map_err(|_| AppError::Internal("封禁时间无效".into()))
        })
        .transpose()
}

fn from_row(row: &AnyRow, now: i64) -> Result<SessionPolicyBlock, AppError> {
    let expires_at_ms = integer(row, "expires_at_ms")?;
    let released_at_ms = optional_integer(row, "released_at_ms")?;
    Ok(SessionPolicyBlock {
        id: row.try_get("id")?,
        session_key: row.try_get("session_key")?,
        api_token_id: integer(row, "api_token_id")?,
        token_name: optional_text(row, "token_name")?,
        account_id: integer(row, "account_id")?,
        account_name: optional_text(row, "account_name")?,
        model: row.try_get("model")?,
        reason: row.try_get("reason")?,
        source_request_id: optional_text(row, "source_request_id")?,
        blocked_at_ms: integer(row, "blocked_at_ms")?,
        expires_at_ms,
        released_at_ms,
        blocked_request_count: integer(row, "blocked_request_count")?,
        last_blocked_at_ms: optional_integer(row, "last_blocked_at_ms")?,
        state: if released_at_ms.is_some() {
            "released"
        } else if expires_at_ms <= now {
            "expired"
        } else {
            "active"
        }
        .into(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::db::migrate;
    use sqlx::any::{AnyPoolOptions, install_default_drivers};
    use std::env::temp_dir;
    use std::fs::remove_file;

    async fn store() -> SessionPolicyBlockStore {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        crate::store::db::migrate(&pool, "sqlite").await.unwrap();
        SessionPolicyBlockStore::new(pool)
    }

    fn identity() -> SessionPolicyIdentity {
        SessionPolicyIdentity {
            session_key: "a".repeat(64),
            api_token_id: 21,
            model: "claude-opus-5-5".into(),
            source_request_id: None,
        }
    }

    /// 重复拒答、命中、解除、到期与新轮次保存独立历史。
    #[tokio::test]
    async fn session_policy_block_lifecycle_and_history() {
        let store = store().await;
        let identity = identity();
        let now = 1_800_000_000_000;
        store
            .remember(&identity, 7, "usage_policy", now, 60_000)
            .await
            .unwrap();
        store
            .remember(&identity, 7, "usage_policy", now + 1, 120_000)
            .await
            .unwrap();
        let first = store
            .hit(&identity.session_key, now + 2)
            .await
            .unwrap()
            .unwrap();
        assert_eq!(first.expires_at_ms, now + 60_000);
        assert_eq!(first.blocked_request_count, 1);
        assert_eq!(store.list("all", "a", 1, 20, now).await.unwrap().total, 1);
        let released = store.release(&first.id, now + 3).await.unwrap();
        assert_eq!(released.state, "released");
        assert_eq!(
            store
                .release(&first.id, now + 4)
                .await
                .unwrap()
                .released_at_ms,
            Some(now + 3)
        );
        assert!(
            store
                .hit(&identity.session_key, now + 5)
                .await
                .unwrap()
                .is_none()
        );
        store
            .remember(&identity, 8, "reasoning_extraction", now + 6, 60_000)
            .await
            .unwrap();
        assert_eq!(store.list("all", "", 1, 1, now + 7).await.unwrap().total, 2);
        assert_eq!(
            store
                .list("released", "", 1, 20, now + 7)
                .await
                .unwrap()
                .total,
            1
        );
        assert_eq!(
            store
                .list("expired", "", 1, 20, now + 60_006)
                .await
                .unwrap()
                .total,
            1
        );
        assert!(
            store
                .hit(&identity.session_key, now + 60_006)
                .await
                .unwrap()
                .is_none()
        );
        store
            .remember(&identity, 8, "usage_policy", now + 60_007, 60_000)
            .await
            .unwrap();
        assert_eq!(
            store
                .list("all", "", 1, 20, now + 60_008)
                .await
                .unwrap()
                .total,
            3
        );
        assert_eq!(
            store
                .list("active", "", 1, 20, now + 60_008)
                .await
                .unwrap()
                .total,
            1
        );
    }

    /// 命中返回前计数已经提交，独立连接立即读取也保持一致。@return 无。
    #[tokio::test]
    async fn session_policy_block_hit_is_visible_to_independent_reader() {
        install_default_drivers();
        let file = temp_dir().join(format!("session-block-hit-{}.sqlite", Uuid::new_v4()));
        let dsn = format!("sqlite:{}?mode=rwc", file.display());
        let writer = AnyPoolOptions::new()
            .max_connections(4)
            .connect(&dsn)
            .await
            .unwrap();
        migrate(&writer, "sqlite").await.unwrap();
        let reader = AnyPoolOptions::new()
            .max_connections(1)
            .connect(&dsn)
            .await
            .unwrap();
        let store = SessionPolicyBlockStore::new(writer.clone());
        let observer = SessionPolicyBlockStore::new(reader.clone());
        let identity = identity();
        let now = 1_800_000_000_000;
        store
            .remember(&identity, 7, "usage_policy", now, 60_000)
            .await
            .unwrap();
        for count in 1..=8 {
            let hit = store
                .hit(&identity.session_key, now + count)
                .await
                .unwrap()
                .unwrap();
            assert_eq!(hit.blocked_request_count, count);
            let observed = observer
                .list("active", "", 1, 20, now + count)
                .await
                .unwrap();
            assert_eq!(observed.items[0].blocked_request_count, count);
        }
        writer.close().await;
        reader.close().await;
        for suffix in ["", "-wal", "-shm"] {
            let _ = remove_file(format!("{}{suffix}", file.display()));
        }
    }

    /// 多连接竞争合并有效轮次，重新打开数据库保留封禁。
    #[tokio::test]
    async fn session_policy_block_concurrency_and_restart() {
        install_default_drivers();
        let file =
            std::env::temp_dir().join(format!("session-block-test-{}.sqlite", Uuid::new_v4()));
        let dsn = format!("sqlite:{}?mode=rwc", file.display());
        let pool = AnyPoolOptions::new()
            .max_connections(4)
            .connect(&dsn)
            .await
            .unwrap();
        crate::store::db::migrate(&pool, "sqlite").await.unwrap();
        let store = SessionPolicyBlockStore::new(pool.clone());
        let now = 1_800_000_000_000;
        let mut tasks = tokio::task::JoinSet::new();
        for _ in 0..8 {
            let store = store.clone();
            tasks.spawn(async move {
                store
                    .remember(&identity(), 9, "usage_policy", now, 86_400_000)
                    .await
            });
        }
        while let Some(result) = tasks.join_next().await {
            result.unwrap().unwrap();
        }
        assert_eq!(store.list("all", "", 1, 20, now).await.unwrap().total, 1);
        pool.close().await;
        let reopened = AnyPoolOptions::new()
            .max_connections(1)
            .connect(&dsn)
            .await
            .unwrap();
        let store = SessionPolicyBlockStore::new(reopened.clone());
        assert!(
            store
                .hit(&identity().session_key, now + 1)
                .await
                .unwrap()
                .is_some()
        );
        reopened.close().await;
        for suffix in ["", "-wal", "-shm"] {
            let _ = std::fs::remove_file(format!("{}{suffix}", file.display()));
        }
    }
}
