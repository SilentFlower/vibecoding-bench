//! 代理目录存储；连接凭据不进入错误文本或公开摘要。
use chrono::Utc;
use sqlx::any::AnyRow;
use sqlx::{AnyPool, Row};
use uuid::Uuid;

use crate::error::AppError;
use crate::model::proxy::{ProxyConnection, ProxyObservation, ProxySyncTarget};

/// 目录内部记录，私有连接仅供受控配置与探测使用。
#[derive(Clone)]
pub struct ProxyRecord {
    pub id: String,
    pub name: String,
    pub connection: ProxyConnection,
    pub expires_at: Option<String>,
    pub revision: String,
    pub observation: Option<ProxyObservation>,
    pub checked_at: Option<String>,
    pub status: String,
    pub created_at: String,
    pub updated_at: String,
}

/// 通过现有数据库保存代理目录，事务兼容SQLite与PostgreSQL。
pub struct ProxyStore {
    pool: AnyPool,
}

/// 可恢复的私有同步任务；重试只处理仍未完成的固定身份。
pub struct ProxySyncOperation {
    pub id: String,
    pub proxy_id: String,
    pub source: ProxyConnection,
    pub destination: ProxyConnection,
    pub remaining: Vec<ProxySyncTarget>,
}

const COLUMNS: &str = "id,name,connection,public_url,COALESCE(expires_at,'') AS expires_at,revision,observation,COALESCE(checked_at,'') AS checked_at,status,created_at,updated_at";

impl ProxyStore {
    /// 创建目录存储。@param pool 现有管理数据库池。@return 存储实例。
    pub fn new(pool: AnyPool) -> Self {
        Self { pool }
    }

    /// 读取单条目录记录。@param id 代理UUID。@return 完整私有记录。
    pub async fn get(&self, id: &str) -> Result<ProxyRecord, AppError> {
        let row = sqlx::query(&format!("SELECT {COLUMNS} FROM proxy_routes WHERE id=$1"))
            .bind(id)
            .fetch_one(&self.pool)
            .await
            .map_err(database_error)?;
        decode(&row)
    }

    /// 搜索公开字段并在数据库内分页。
    /// @param page 从1开始的页码。
    /// @param size 已校验的每页条数。
    /// @param query 名称、公开地址或出口观测子串。
    /// @return 当前页及全部匹配数。
    pub async fn list(
        &self,
        page: i64,
        size: i64,
        query: &str,
    ) -> Result<(Vec<ProxyRecord>, i64), AppError> {
        let pattern = format!(
            "%{}%",
            query
                .replace('!', "!!")
                .replace('%', "!%")
                .replace('_', "!_")
        );
        let filter = "LOWER(name) LIKE LOWER($1) ESCAPE '!' OR LOWER(public_url) LIKE LOWER($1) ESCAPE '!' OR LOWER(observation) LIKE LOWER($1) ESCAPE '!'";
        let total: i64 =
            sqlx::query_scalar(&format!("SELECT COUNT(*) FROM proxy_routes WHERE {filter}"))
                .bind(&pattern)
                .fetch_one(&self.pool)
                .await
                .map_err(database_error)?;
        let rows = sqlx::query(&format!("SELECT {COLUMNS} FROM proxy_routes WHERE {filter} ORDER BY created_at,id LIMIT $2 OFFSET $3"))
            .bind(&pattern).bind(size).bind((page - 1).saturating_mul(size))
            .fetch_all(&self.pool).await.map_err(database_error)?;
        Ok((
            rows.iter().map(decode).collect::<Result<Vec<_>, _>>()?,
            total,
        ))
    }

    /// 只为目录总览读取连接指纹输入及状态，分页和搜索不影响总览口径。
    /// @return 私有连接与状态，仅限服务端聚合使用。
    pub async fn summary_index(&self) -> Result<Vec<(String, String)>, AppError> {
        let rows = sqlx::query("SELECT connection,status FROM proxy_routes")
            .fetch_all(&self.pool)
            .await
            .map_err(database_error)?;
        rows.iter()
            .map(|row| {
                Ok((
                    row.try_get("connection").map_err(database_error)?,
                    row.try_get("status").map_err(database_error)?,
                ))
            })
            .collect()
    }

    /// 批量映射当前账号页的规范连接，避免逐账号查询目录。
    /// @param connections 已规范的私有连接集合。@return 匹配的目录记录。
    pub async fn matching(&self, connections: &[String]) -> Result<Vec<ProxyRecord>, AppError> {
        if connections.is_empty() {
            return Ok(Vec::new());
        }
        let placeholders = (1..=connections.len())
            .map(|index| format!("${index}"))
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!(
            "SELECT {COLUMNS} FROM proxy_routes WHERE connection IN ({placeholders}) OR id IN (SELECT proxy_id FROM proxy_route_sync WHERE source_connection IN ({placeholders}))"
        );
        let mut query = sqlx::query(&sql);
        for connection in connections {
            query = query.bind(connection);
        }
        let rows = query.fetch_all(&self.pool).await.map_err(database_error)?;
        let mut records = rows.iter().map(decode).collect::<Result<Vec<_>, _>>()?;
        // 同步期间仍使用旧连接的账号保留同一目录身份，避免卡片变成未知线路。
        for operation in self.pending_sync().await? {
            if connections.contains(&operation.source.private_url) {
                if let Some(record) = records
                    .iter()
                    .find(|record| record.id == operation.proxy_id)
                {
                    let mut alias = record.clone();
                    alias.connection = operation.source;
                    records.push(alias);
                }
            }
        }
        Ok(records)
    }

    /// 创建一批已校验记录，任一连接重复时整批回滚。
    /// @param values 名称、私有连接及到期时间。
    /// @return 创建的UUID列表。
    pub async fn insert_many(
        &self,
        values: &[(String, ProxyConnection, Option<String>)],
    ) -> Result<Vec<String>, AppError> {
        let mut transaction = self.pool.begin().await.map_err(database_error)?;
        let mut ids = Vec::with_capacity(values.len());
        for (name, connection, expiry) in values {
            let pending: i64 = sqlx::query_scalar(
                "SELECT COUNT(*) FROM proxy_route_sync WHERE source_connection=$1",
            )
            .bind(&connection.private_url)
            .fetch_one(&mut *transaction)
            .await
            .map_err(database_error)?;
            if pending != 0 {
                return Err(AppError::BadRequest(
                    "原线路正在同步，请完成后再复用该连接".into(),
                ));
            }
            let id = Uuid::new_v4().to_string();
            let now = Utc::now().to_rfc3339();
            sqlx::query("INSERT INTO proxy_routes(id,name,connection,public_url,expires_at,revision,created_at,updated_at) VALUES($1,$2,$3,$4,NULLIF($5,''),$6,$7,$7)")
                .bind(&id).bind(name).bind(&connection.private_url).bind(&connection.public_url)
                .bind(expiry.as_deref().unwrap_or_default()).bind(Uuid::new_v4().to_string()).bind(&now)
                .execute(&mut *transaction).await.map_err(database_error)?;
            ids.push(id);
        }
        transaction.commit().await.map_err(database_error)?;
        Ok(ids)
    }

    /// 在调用者完成引用与维护校验后按版本保存。
    /// @param original 打开编辑时的记录与版本。
    /// @param name 新名称。
    /// @param connection 已验证连接。
    /// @param expiry 新到期时间。
    /// @return 更新后的记录；并发变化时拒绝覆盖。
    pub async fn update(
        &self,
        original: &ProxyRecord,
        name: &str,
        connection: &ProxyConnection,
        expiry: Option<&str>,
    ) -> Result<ProxyRecord, AppError> {
        self.update_and_queue(original, name, connection, expiry, &[])
            .await
    }

    /// 原子保存目录与关联同步任务，后台失败后可从台账继续。
    /// @param original 原配置。@param name 名称。@param connection 新连接。@param expiry 到期时间。
    /// @param targets 本次快照中的固定使用者。@return 新配置。
    pub async fn update_and_queue(
        &self,
        original: &ProxyRecord,
        name: &str,
        connection: &ProxyConnection,
        expiry: Option<&str>,
        targets: &[ProxySyncTarget],
    ) -> Result<ProxyRecord, AppError> {
        let changed = original.connection.private_url != connection.private_url;
        let mut transaction = self.pool.begin().await.map_err(database_error)?;
        if changed {
            let pending: i64 = sqlx::query_scalar(
                "SELECT COUNT(*) FROM proxy_route_sync WHERE proxy_id=$1 OR source_connection=$2",
            )
            .bind(&original.id)
            .bind(&connection.private_url)
            .fetch_one(&mut *transaction)
            .await
            .map_err(database_error)?;
            if pending != 0 {
                return Err(AppError::BadRequest(
                    "线路正在同步关联账号，请稍后再修改连接".into(),
                ));
            }
        }
        let result = sqlx::query("UPDATE proxy_routes SET name=$1,connection=$2,public_url=$3,expires_at=NULLIF($4,''),revision=$5,observation=CASE WHEN $6=1 THEN '{}' ELSE observation END,status=CASE WHEN $6=1 THEN 'unknown' ELSE status END,checked_at=CASE WHEN $6=1 THEN NULL ELSE checked_at END,updated_at=$7 WHERE id=$8 AND revision=$9")
            .bind(name).bind(&connection.private_url).bind(&connection.public_url).bind(expiry.unwrap_or_default())
            .bind(Uuid::new_v4().to_string()).bind(i32::from(changed)).bind(Utc::now().to_rfc3339())
            .bind(&original.id).bind(&original.revision).execute(&mut *transaction).await.map_err(database_error)?;
        if result.rows_affected() != 1 {
            return Err(AppError::BadRequest(
                "代理配置已变化，请刷新后重新编辑".into(),
            ));
        }
        if changed && !targets.is_empty() {
            let remaining = serde_json::to_string(targets)
                .map_err(|_| AppError::Internal("代理同步任务编码失败".into()))?;
            sqlx::query("INSERT INTO proxy_route_sync(id,proxy_id,source_connection,target_connection,remaining,created_at) VALUES($1,$2,$3,$4,$5,$6)")
                .bind(Uuid::new_v4().to_string()).bind(&original.id).bind(&original.connection.private_url)
                .bind(&connection.private_url).bind(remaining).bind(Utc::now().to_rfc3339())
                .execute(&mut *transaction).await.map_err(database_error)?;
        }
        transaction.commit().await.map_err(database_error)?;
        self.get(&original.id).await
    }

    /// 读取重启后仍需处理的同步任务。@return 私有任务列表。
    pub async fn pending_sync(&self) -> Result<Vec<ProxySyncOperation>, AppError> {
        let rows = sqlx::query("SELECT id,proxy_id,source_connection,target_connection,remaining FROM proxy_route_sync ORDER BY created_at,id")
            .fetch_all(&self.pool).await.map_err(database_error)?;
        rows.iter()
            .map(|row| {
                let source: String = row.try_get("source_connection").map_err(database_error)?;
                let destination: String =
                    row.try_get("target_connection").map_err(database_error)?;
                let raw: String = row.try_get("remaining").map_err(database_error)?;
                let remaining: Vec<ProxySyncTarget> = serde_json::from_str(&raw)
                    .map_err(|_| AppError::ServiceUnavailable("代理关联同步记录待核对".into()))?;
                if remaining.iter().any(|target| {
                    !matches!(
                        target.kind.as_str(),
                        "gateway" | "task" | "draft" | "authorization"
                    ) || target.id.is_empty()
                        || target.id.len() > 128
                }) {
                    return Err(AppError::ServiceUnavailable(
                        "代理关联同步身份待核对".into(),
                    ));
                }
                Ok(ProxySyncOperation {
                    id: row.try_get("id").map_err(database_error)?,
                    proxy_id: row.try_get("proxy_id").map_err(database_error)?,
                    source: ProxyConnection::parse(&source)?,
                    destination: ProxyConnection::parse(&destination)?,
                    remaining,
                })
            })
            .collect()
    }

    /// 保存本批进度；全部完成才删除台账。@param id 任务身份。@param remaining 剩余目标。@return 保存结果。
    pub async fn save_sync_progress(
        &self,
        id: &str,
        remaining: &[ProxySyncTarget],
    ) -> Result<(), AppError> {
        if remaining.is_empty() {
            sqlx::query("DELETE FROM proxy_route_sync WHERE id=$1")
                .bind(id)
                .execute(&self.pool)
                .await
                .map_err(database_error)?;
        } else {
            let payload = serde_json::to_string(remaining)
                .map_err(|_| AppError::Internal("代理同步进度编码失败".into()))?;
            sqlx::query("UPDATE proxy_route_sync SET remaining=$1 WHERE id=$2")
                .bind(payload)
                .bind(id)
                .execute(&self.pool)
                .await
                .map_err(database_error)?;
        }
        Ok(())
    }

    /// 保存探测结果；连接或元数据版本变化时丢弃迟到结果。
    /// @param original 探测开始时的记录。
    /// @param observation 新的成功观测；失败时为空并保留历史观测。
    /// @return 成功写入为true，迟到结果为false。
    pub async fn observe(
        &self,
        original: &ProxyRecord,
        observation: Option<&ProxyObservation>,
    ) -> Result<bool, AppError> {
        let payload = encode_observation(observation)?;
        let result = sqlx::query("UPDATE proxy_routes SET observation=CASE WHEN $1='{}' THEN observation ELSE $1 END,checked_at=$2,status=$3 WHERE id=$4 AND revision=$5")
            .bind(payload).bind(Utc::now().to_rfc3339()).bind(if observation.is_some() { "ready" } else { "failed" })
            .bind(&original.id).bind(&original.revision).execute(&self.pool).await.map_err(database_error)?;
        Ok(result.rows_affected() == 1)
    }

    /// 在完整引用检查之后删除指定版本。
    /// @param id 代理UUID。
    /// @param revision 用户确认的版本。
    /// @return 删除结果。
    pub async fn delete(&self, id: &str, revision: &str) -> Result<(), AppError> {
        let result = sqlx::query("DELETE FROM proxy_routes WHERE id=$1 AND revision=$2")
            .bind(id)
            .bind(revision)
            .execute(&self.pool)
            .await
            .map_err(database_error)?;
        if result.rows_affected() != 1 {
            return Err(AppError::BadRequest(
                "代理配置已变化，请刷新后重新操作".into(),
            ));
        }
        Ok(())
    }
}

fn encode_observation(value: Option<&ProxyObservation>) -> Result<String, AppError> {
    value
        .map(serde_json::to_string)
        .transpose()
        .map(|value| value.unwrap_or_else(|| "{}".into()))
        .map_err(|_| AppError::Internal("代理观测编码失败".into()))
}

fn optional_text(row: &AnyRow, name: &str) -> Result<Option<String>, AppError> {
    let value: String = row.try_get(name).map_err(database_error)?;
    Ok((!value.is_empty()).then_some(value))
}

fn decode(row: &AnyRow) -> Result<ProxyRecord, AppError> {
    let raw: String = row.try_get("connection").map_err(database_error)?;
    let observation: String = row.try_get("observation").map_err(database_error)?;
    Ok(ProxyRecord {
        id: row.try_get("id").map_err(database_error)?,
        name: row.try_get("name").map_err(database_error)?,
        connection: ProxyConnection::parse(&raw)?,
        expires_at: optional_text(row, "expires_at")?,
        revision: row.try_get("revision").map_err(database_error)?,
        observation: if observation == "{}" {
            None
        } else {
            Some(
                serde_json::from_str(&observation)
                    .map_err(|_| AppError::Internal("代理观测格式无效".into()))?,
            )
        },
        checked_at: optional_text(row, "checked_at")?,
        status: row.try_get("status").map_err(database_error)?,
        created_at: row.try_get("created_at").map_err(database_error)?,
        updated_at: row.try_get("updated_at").map_err(database_error)?,
    })
}

fn database_error(error: sqlx::Error) -> AppError {
    match error {
        sqlx::Error::RowNotFound => AppError::NotFound,
        sqlx::Error::Database(ref value) if value.is_unique_violation() => {
            AppError::BadRequest("相同代理连接已存在".into())
        }
        // 数据库唯一约束错误可能包含连接值，禁止直接记录原错误。
        _ => AppError::Internal("代理目录存储操作失败".into()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::store::database_migrations;
    use sqlx::any::{AnyPoolOptions, install_default_drivers};

    /// 线路与同步台账同事务保存，重新创建存储后继续读取剩余目标。
    #[tokio::test]
    async fn proxy_sync_survives_restart_and_preserves_cas() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        database_migrations::apply(&pool, &Uuid::new_v4().to_string(), None)
            .await
            .unwrap();
        let store = ProxyStore::new(pool.clone());
        let old = ProxyConnection::parse("http://old.test:8080").unwrap();
        let new = ProxyConnection::parse("socks5://new.test:1080").unwrap();
        let id = store
            .insert_many(&[("线路".into(), old.clone(), None)])
            .await
            .unwrap()
            .remove(0);
        let record = store.get(&id).await.unwrap();
        let targets = vec![
            ProxySyncTarget {
                kind: "gateway".into(),
                id: "1".into(),
            },
            ProxySyncTarget {
                kind: "draft".into(),
                id: "a".repeat(32),
            },
        ];
        let changed = store
            .update_and_queue(&record, "线路", &new, None, &targets)
            .await
            .unwrap();
        let recovered = ProxyStore::new(pool.clone());
        let pending = recovered.pending_sync().await.unwrap().remove(0);
        assert_eq!(pending.remaining.len(), 2);
        assert_eq!(pending.source.private_url, old.private_url);
        assert_eq!(pending.destination.private_url, new.private_url);
        assert!(
            recovered
                .matching(&[old.private_url.clone()])
                .await
                .unwrap()
                .iter()
                .any(|item| item.id == id && item.connection.private_url == old.private_url)
        );
        assert!(
            store
                .insert_many(&[("重复".into(), old.clone(), None)])
                .await
                .is_err()
        );
        assert!(
            store
                .update_and_queue(&record, "过期", &new, None, &targets)
                .await
                .is_err()
        );
        assert!(
            store
                .update(&changed, "第二次连接", &old, None)
                .await
                .is_err()
        );
        let metadata = store
            .update(&changed, "改名", &new, Some("2026-12-01T00:00:00Z"))
            .await
            .unwrap();
        assert_eq!(metadata.name, "改名");
        recovered
            .save_sync_progress(&pending.id, &targets[1..])
            .await
            .unwrap();
        assert_eq!(store.pending_sync().await.unwrap()[0].remaining.len(), 1);
        recovered
            .save_sync_progress(&pending.id, &[])
            .await
            .unwrap();
        assert!(store.pending_sync().await.unwrap().is_empty());
        assert!(
            store
                .insert_many(&[("旧连接可重新添加".into(), old, None)])
                .await
                .is_ok()
        );
    }

    #[tokio::test]
    async fn directory_preserves_credentials_pagination_and_probe_versions() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        database_migrations::apply(&pool, &Uuid::new_v4().to_string(), None)
            .await
            .unwrap();
        let store = ProxyStore::new(pool.clone());
        let connection = ProxyConnection::parse("http://user:secret@proxy.test:8080").unwrap();
        let id = store
            .insert_many(&[("A%_!".into(), connection.clone(), None)])
            .await
            .unwrap()
            .remove(0);
        assert_eq!(store.list(1, 10, "secret").await.unwrap().1, 0);
        assert_eq!(store.list(1, 10, "%_!").await.unwrap().1, 1);
        assert_eq!(store.list(2, 1, "").await.unwrap().0.len(), 0);
        let before = store.get(&id).await.unwrap();
        let observation = ProxyObservation {
            ip: "203.0.113.2".into(),
            latency_ms: 42,
            ..Default::default()
        };
        store.observe(&before, Some(&observation)).await.unwrap();
        store.observe(&before, None).await.unwrap();
        let current = store.get(&id).await.unwrap();
        assert_eq!(current.status, "failed");
        assert_eq!(current.observation.unwrap().ip, "203.0.113.2");
        // 编辑名称不能把提交表单前的旧观测写回去。
        let updated = store
            .update(&before, "新名称", &connection, None)
            .await
            .unwrap();
        assert_eq!(updated.observation.unwrap().ip, "203.0.113.2");
        assert!(!store.observe(&before, Some(&observation)).await.unwrap());
        assert!(store.delete(&id, &before.revision).await.is_err());
        assert!(
            store
                .update(&before, "旧表单", &connection, None)
                .await
                .is_err()
        );
        let new_connection = ProxyConnection::parse("socks5://new.test:1080").unwrap();
        let current = store.get(&id).await.unwrap();
        let changed = store
            .update(&current, "新连接", &new_connection, None)
            .await
            .unwrap();
        assert!(changed.observation.is_none());
        assert_eq!(changed.status, "unknown");
        assert!(
            store
                .insert_many(&[
                    ("先插入".into(), connection, None),
                    ("重复".into(), new_connection, None)
                ])
                .await
                .is_err()
        );
        assert_eq!(store.list(1, 10, "").await.unwrap().1, 1);
        store.delete(&id, &changed.revision).await.unwrap();
        assert_eq!(store.list(1, 10, "").await.unwrap().1, 0);
    }
}
