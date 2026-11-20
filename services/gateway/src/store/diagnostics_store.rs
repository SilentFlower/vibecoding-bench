use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use chrono::{DateTime, Duration as ChronoDuration, SecondsFormat, Utc};
use serde::de::DeserializeOwned;
use sqlx::any::AnyRow;
use sqlx::{AnyPool, Row};
use tokio::sync::{mpsc, oneshot};
use tracing::warn;

use crate::error::AppError;
use crate::model::request_diagnostics::{
    AgyRequestUsage, AgyUsageWindow, AttemptDiagnostic, DiagnosticCounts, DiagnosticDetail,
    DiagnosticHealth, DiagnosticPage, DiagnosticQuery, RequestDiagnostic, ToolTurnDiagnostic,
    normalize_correlation_id,
};
use crate::service::native_capture;

const QUEUE_CAPACITY: usize = 1024;
const MAX_RECORD_BYTES: usize = 16 * 1024;
const FILTER: &str = "WHERE ($1=0 OR r.account_id=$1 OR EXISTS(SELECT 1 FROM request_diagnostic_attempts a WHERE a.request_id=r.request_id AND a.account_id=$1))
 AND ($2='' OR r.request_id=$2 OR r.response_request_id=$2 OR EXISTS(SELECT 1 FROM request_diagnostic_attempts a WHERE a.request_id=r.request_id AND a.upstream_request_id=$2))
 AND ($3='' OR r.outcome=$3 OR ($3='errors' AND r.outcome IN ('incomplete','upstream_error','upstream_rejected','local_rejected','transport_error','body_error'))) AND ($4='' OR r.started_at >= $4) AND ($5='' OR r.started_at < $5)
 AND (r.started_at >= $6 OR $7 LIKE '%\"' || r.request_id || '\"%')
 AND ($8='' OR COALESCE(r.platform,'history_unknown')=$8)
 AND ($9='' OR COALESCE(r.entry_protocol,'history_unknown')=$9)
 AND ($10='' OR EXISTS(SELECT 1 FROM request_diagnostic_attempts k WHERE k.request_id=r.request_id AND COALESCE(k.kernel_version,'history_unknown')=$10) OR ($10='history_unknown' AND NOT EXISTS(SELECT 1 FROM request_diagnostic_attempts k WHERE k.request_id=r.request_id)))
 AND ($11='' OR COALESCE(r.requested_model,'history_unknown')=$11)
 AND ($12='' OR EXISTS(SELECT 1 FROM request_diagnostic_attempts m WHERE m.request_id=r.request_id AND COALESCE(m.actual_model,'history_unknown')=$12) OR ($12='history_unknown' AND NOT EXISTS(SELECT 1 FROM request_diagnostic_attempts m WHERE m.request_id=r.request_id)))";

/// 当前进程真实请求的保留许可，终结与异常 Drop 均释放。
pub(crate) struct ActiveDiagnostic {
    active: Arc<Mutex<HashSet<String>>>,
    id: String,
}

impl Drop for ActiveDiagnostic {
    fn drop(&mut self) {
        self.active
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .remove(&self.id);
    }
}

/// 一次无正文的诊断写入；尝试完成时同时保证父请求存在。
pub(crate) struct DiagnosticEvent {
    pub request: RequestDiagnostic,
    pub attempt: Option<AttemptDiagnostic>,
}

enum WriteCommand {
    Record(DiagnosticEvent),
    ToolTurn {
        attempt_id: String,
        account_id: i64,
        turn: ToolTurnDiagnostic,
    },
    CaptureStatus {
        attempt_id: String,
        account_id: i64,
        status: String,
    },
    ControlState {
        attempt_id: String,
        account_id: i64,
        status: String,
        observed_at: String,
    },
    Flush(oneshot::Sender<()>),
}

/// 独立诊断持久化与有界后台写入，不参与费用统计。
pub struct DiagnosticsStore {
    pool: AnyPool,
    sender: mpsc::Sender<WriteCommand>,
    dropped: Arc<AtomicU64>,
    failures: Arc<AtomicU64>,
    observation_failures: AtomicU64,
    active: Arc<Mutex<HashSet<String>>>,
    rejected_ingress_dir: Option<PathBuf>,
}

impl DiagnosticsStore {
    /// 创建后台写入器，须在 Tokio 运行时内调用。
    /// @param pool 已迁移的共享数据库连接池。
    /// @return 可供网关与管理查询共享的存储。
    pub fn new(pool: AnyPool) -> Self {
        Self::with_rejected_ingress_dir(pool, None)
    }

    /// 创建诊断写入器并装配本地拒绝归档。@param pool 已迁移的连接池。@param directory 与摘要分离的私有目录。@return 可用的诊断存储。
    pub fn with_rejected_ingress_dir(pool: AnyPool, directory: Option<PathBuf>) -> Self {
        let (sender, mut receiver) = mpsc::channel(QUEUE_CAPACITY);
        let dropped = Arc::new(AtomicU64::new(0));
        let failures = Arc::new(AtomicU64::new(0));
        let writer_pool = pool.clone();
        let writer_failures = failures.clone();
        let active = Arc::new(Mutex::new(HashSet::new()));
        let writer_active = active.clone();
        let writer_directory = directory.clone();
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(Duration::from_secs(3600));
            loop {
                tokio::select! {
                    command = receiver.recv() => match command {
                        Some(WriteCommand::Record(event)) => {
                            if write_event(&writer_pool, &event).await.is_err() {
                                writer_failures.fetch_add(1, Ordering::Relaxed);
                                warn!(request_id = %event.request.request_id, "请求诊断写入失败");
                            }
                        }
                        Some(WriteCommand::ToolTurn {attempt_id, account_id, turn}) => {
                            if update_attempt_fact(&writer_pool, &attempt_id, account_id, Some(&turn),None,None).await.is_err() {
                                writer_failures.fetch_add(1, Ordering::Relaxed);
                                warn!("原生工具诊断更新失败");
                            }
                        }
                        Some(WriteCommand::CaptureStatus {attempt_id,account_id,status}) => {
                            if update_attempt_fact(&writer_pool,&attempt_id,account_id,None,Some(&status),None).await.is_err() {writer_failures.fetch_add(1,Ordering::Relaxed);}
                        }
                        Some(WriteCommand::ControlState {attempt_id,account_id,status,observed_at}) => {
                            if update_attempt_fact(&writer_pool,&attempt_id,account_id,None,None,Some((&status,&observed_at))).await.is_err() {writer_failures.fetch_add(1,Ordering::Relaxed);}
                        }
                        Some(WriteCommand::Flush(done)) => { let _ = done.send(()); }
                        None => break,
                    },
                    _ = interval.tick() => {
                        if prune(&writer_pool, Utc::now(), &writer_active).await.is_err() {
                            writer_failures.fetch_add(1, Ordering::Relaxed);
                            warn!("请求诊断历史清理失败");
                        }
                        if let Some(directory) = &writer_directory {
                            native_capture::prune_gateway_rejections(directory.clone());
                        }
                    }
                }
            }
        });
        Self {
            pool,
            sender,
            dropped,
            failures,
            observation_failures: AtomicU64::new(0),
            active,
            rejected_ingress_dir: directory,
        }
    }

    /// 返回可写入或读取的本地拒绝目录。@return 缺省未装配。
    pub(crate) fn rejected_ingress_dir(&self) -> Option<&Path> {
        self.rejected_ingress_dir.as_deref()
    }

    /// 在首条记录入队前登记真实请求，历史 unfinished 记录不产生许可。
    /// @param id 当前网关生成的内部请求 UUID。
    /// @return 随请求终结释放的许可。
    pub(crate) fn track_request(&self, id: &str) -> ActiveDiagnostic {
        self.active
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .insert(id.to_owned());
        ActiveDiagnostic {
            active: self.active.clone(),
            id: id.to_owned(),
        }
    }

    /// 幂等创建 SQLite/PostgreSQL 共用的诊断表与索引。
    /// @param pool 数据库连接池。
    /// @return 迁移结果。
    pub async fn migrate(pool: &AnyPool) -> Result<(), sqlx::Error> {
        super::database_schema::migrate_diagnostics(pool).await?;
        let mut tx = pool.begin().await?;
        let driver = if pool.connect_options().database_url.scheme() == "sqlite" {
            "sqlite"
        } else {
            "postgres"
        };
        super::request_records_schema::apply(&mut tx, driver).await?;
        tx.commit().await
    }

    /// 汇总反重力账号已落库的用量。@param accounts 当前页反重力账号。@param now 固定查询时刻。@return 以账号 ID 为键的滚动窗口。
    pub async fn agy_request_usage(
        &self,
        accounts: &[i64],
        now: DateTime<Utc>,
    ) -> Result<HashMap<i64, AgyRequestUsage>, AppError> {
        let mut result = accounts
            .iter()
            .map(|&id| (id, AgyRequestUsage::default()))
            .collect::<HashMap<_, _>>();
        if accounts.is_empty() {
            return Ok(result);
        }
        let (source, tokens, partial) = if self.pool.connect_options().database_url.scheme()
            == "sqlite"
        {
            (
                "json_extract(a.summary_json,'$.context.usage.source')",
                "CASE WHEN json_type(a.summary_json,'$.context.usage.total_tokens')='integer'
                  AND typeof(json_extract(a.summary_json,'$.context.usage.total_tokens'))='integer'
                  AND json_extract(a.summary_json,'$.context.usage.total_tokens')>=0
                  THEN json_extract(a.summary_json,'$.context.usage.total_tokens') END",
                "COALESCE(json_extract(a.summary_json,'$.partial'),1)<>0
                  OR COALESCE(json_extract(a.summary_json,'$.context.usage.complete'),0)<>1",
            )
        } else {
            (
                "a.summary_json::jsonb #>> '{context,usage,source}'",
                "CASE WHEN jsonb_typeof(a.summary_json::jsonb #> '{context,usage,total_tokens}')='number'
                  AND (a.summary_json::jsonb #>> '{context,usage,total_tokens}') ~ '^[0-9]{1,20}$'
                  THEN (a.summary_json::jsonb #>> '{context,usage,total_tokens}')::numeric END",
                "(a.summary_json::jsonb -> 'partial') IS DISTINCT FROM 'false'::jsonb
                  OR (a.summary_json::jsonb #> '{context,usage,complete}') IS DISTINCT FROM 'true'::jsonb",
            )
        };
        let ids = (4..4 + accounts.len())
            .map(|index| format!("${index}"))
            .collect::<Vec<_>>()
            .join(",");
        // 同账号的 HTTP 请求合并为一行，每次已终结尝试的源总量各计一次。
        let sql = format!(
            "WITH attempts AS (
               SELECT a.account_id,r.request_id,r.started_at,
                 CASE WHEN ({source})='gemini_usage_metadata' THEN ({tokens}) END AS tokens,
                 CASE WHEN ({partial}) THEN 1 ELSE 0 END AS partial
               FROM request_diagnostics r JOIN request_diagnostic_attempts a ON a.request_id=r.request_id
               WHERE r.platform='antigravity' AND r.entry_protocol='gemini' AND r.finished_at IS NOT NULL
                 AND r.started_at >= $1 AND r.started_at < $2 AND a.platform='antigravity'
                 AND a.finished_at IS NOT NULL AND a.account_id IN ({ids})
             ), requests AS (
               SELECT account_id,request_id,started_at,SUM(tokens) AS tokens,
                 MAX(CASE WHEN tokens IS NULL THEN 1 ELSE partial END) AS partial
               FROM attempts GROUP BY account_id,request_id,started_at
             )
             SELECT CAST(account_id AS BIGINT) AS account_id,
               CAST(SUM(CASE WHEN started_at >= $3 THEN 1 ELSE 0 END) AS TEXT) AS short_requests,
               CAST(SUM(CASE WHEN started_at >= $3 THEN tokens END) AS TEXT) AS short_tokens,
               CAST(SUM(CASE WHEN started_at >= $3 THEN partial ELSE 0 END) AS TEXT) AS short_partial,
               CAST(COUNT(*) AS TEXT) AS long_requests,CAST(SUM(tokens) AS TEXT) AS long_tokens,
               CAST(SUM(partial) AS TEXT) AS long_partial
             FROM requests GROUP BY account_id"
        );
        let mut query = sqlx::query(&sql)
            .bind(retention_cutoff(now))
            .bind(now.to_rfc3339_opts(SecondsFormat::Millis, true))
            .bind((now - ChronoDuration::hours(5)).to_rfc3339_opts(SecondsFormat::Millis, true));
        for id in accounts {
            query = query.bind(*id);
        }
        for row in query.fetch_all(&self.pool).await? {
            let window = |requests, tokens, partial| {
                Ok::<_, AppError>(AgyUsageWindow {
                    requests: usage_count(&row, requests)?.unwrap_or(0),
                    tokens: usage_count(&row, tokens)?,
                    partial_requests: usage_count(&row, partial)?.unwrap_or(0),
                })
            };
            result.insert(
                row.try_get("account_id")?,
                AgyRequestUsage {
                    five_hour: window("short_requests", "short_tokens", "short_partial")?,
                    seven_day: window("long_requests", "long_tokens", "long_partial")?,
                },
            );
        }
        Ok(result)
    }

    /// 尝试入队，队列饱和时只记录失败计数，不阻塞转发。
    /// @param event 已完成白名单提取的诊断事件。
    /// @return 无返回值。
    pub(crate) fn submit(&self, event: DiagnosticEvent) {
        if self.sender.try_send(WriteCommand::Record(event)).is_err() {
            let count = self.dropped.fetch_add(1, Ordering::Relaxed) + 1;
            if count == 1 || count % 100 == 0 {
                warn!(dropped_records = count, "请求诊断队列不可用或已满");
            }
        }
    }

    /// 按原attempt和账号更新工具最近观测，保留HTTP终态。@param attempt_id 原尝试。@param account_id 原账号。@param turn 受控工具事实。@return 无。
    pub(crate) fn tool_turn(&self, attempt_id: &str, account_id: i64, turn: ToolTurnDiagnostic) {
        if self
            .sender
            .try_send(WriteCommand::ToolTurn {
                attempt_id: attempt_id.into(),
                account_id,
                turn,
            })
            .is_err()
        {
            self.dropped.fetch_add(1, Ordering::Relaxed);
        }
    }

    /// 仅补同次采集结果，保留原业务终态。@param attempt_id 尝试。@param account_id 账号。@param status 受控采集状态。@return 无。
    pub(crate) fn capture_status(&self, attempt_id: &str, account_id: i64, status: &str) {
        if self
            .sender
            .try_send(WriteCommand::CaptureStatus {
                attempt_id: attempt_id.into(),
                account_id,
                status: status.into(),
            })
            .is_err()
        {
            self.dropped.fetch_add(1, Ordering::Relaxed);
        }
    }

    /// 独立记录原生物理控制收口，保留HTTP与模型结果。@param attempt_id 尝试。@param account_id 账号。@param status 控制终态。@param observed_at 实际观测时刻。@return 无。
    pub(crate) fn control_state(
        &self,
        attempt_id: &str,
        account_id: i64,
        status: &str,
        observed_at: &str,
    ) {
        if self
            .sender
            .try_send(WriteCommand::ControlState {
                attempt_id: attempt_id.into(),
                account_id,
                status: status.into(),
                observed_at: observed_at.into(),
            })
            .is_err()
        {
            self.dropped.fetch_add(1, Ordering::Relaxed);
        }
    }

    /// 计数有界采样或解码失败，只输出固定诊断文案。
    /// @return 无返回值。
    pub(crate) fn observation_failed(&self) {
        let count = self.observation_failures.fetch_add(1, Ordering::Relaxed) + 1;
        if count == 1 || count % 100 == 0 {
            warn!(observation_failures = count, "请求诊断响应采样不完整");
        }
    }

    /// 等待此前队列中的写入结束，用于受控收尾和验证。
    /// @return 写入器可用且队列已消费，或明确的存储不可用错误。
    pub async fn flush(&self) -> Result<(), AppError> {
        let (done, wait) = oneshot::channel();
        tokio::time::timeout(Duration::from_secs(5), async {
            self.sender
                .send(WriteCommand::Flush(done))
                .await
                .map_err(|_| unavailable())?;
            wait.await.map_err(|_| unavailable())
        })
        .await
        .map_err(|_| unavailable())?
    }

    /// 分页读取诊断，不触发清理或上游请求。
    /// @param query 管理员提供的过滤条件。
    /// @return 请求列表、总数与采集失败计数。
    pub async fn list(&self, query: DiagnosticQuery) -> Result<DiagnosticPage, AppError> {
        let page = query.page.unwrap_or(1);
        let page_size = query.page_size.unwrap_or(50);
        if page == 0 || !(1..=200).contains(&page_size) || query.account_id.is_some_and(|v| v <= 0)
        {
            return Err(AppError::BadRequest("无效的诊断分页或账号参数".into()));
        }
        let platform = query_filter(
            query.platform,
            &["claude_code", "antigravity", "history_unknown"],
        )?;
        let protocol = query_filter(
            query.entry_protocol,
            &["anthropic_messages", "gemini", "history_unknown"],
        )?;
        let kernel = query_filter(query.kernel_version, &[])?;
        let requested_model = query_filter(query.requested_model, &[])?;
        let actual_model = query_filter(query.actual_model, &[])?;
        let id = query.correlation_id.unwrap_or_default();
        if id.len() > 128 {
            return Err(AppError::BadRequest("关联标识过长".into()));
        }
        let id = if id.is_empty() {
            id
        } else {
            normalize_correlation_id(&id)
        };
        let outcome = query.outcome.unwrap_or_default();
        if !outcome.is_empty()
            && ![
                "errors",
                "in_progress",
                "success",
                "local_rejected",
                "local_response",
                "mock",
                "cache_hit",
                "upstream_rejected",
                "upstream_error",
                "transport_error",
                "body_error",
                "cancelled",
                "incomplete",
            ]
            .contains(&outcome.as_str())
        {
            return Err(AppError::BadRequest("未知的诊断结果".into()));
        }
        let since = query_time(query.since)?;
        let until = query_time(query.until)?;
        if !since.is_empty() && !until.is_empty() && since >= until {
            return Err(AppError::BadRequest("诊断时间范围无效".into()));
        }
        let account = query.account_id.unwrap_or(0);
        let cutoff = retention_cutoff(Utc::now());
        let active = active_json(&self.active);
        let sql = format!("SELECT CAST(COUNT(*) AS BIGINT) FROM request_diagnostics r {FILTER}");
        let total: i64 = sqlx::query_scalar(&sql)
            .bind(account)
            .bind(&id)
            .bind(&outcome)
            .bind(&since)
            .bind(&until)
            .bind(&cutoff)
            .bind(&active)
            .bind(&platform)
            .bind(&protocol)
            .bind(&kernel)
            .bind(&requested_model)
            .bind(&actual_model)
            .fetch_one(&self.pool)
            .await
            .map_err(|_| unavailable())?;
        let sql = format!(
            "SELECT r.summary_json,COALESCE((SELECT latest.summary_json FROM request_diagnostic_attempts latest WHERE latest.request_id=r.request_id ORDER BY latest.ordinal DESC LIMIT 1),'') AS last_attempt,COALESCE(a.name,'') AS account_name,COALESCE(a.email,'') AS account_email
             FROM request_diagnostics r LEFT JOIN accounts a ON a.id=r.account_id
             {FILTER} ORDER BY r.started_at DESC,r.request_id DESC LIMIT $13 OFFSET $14"
        );
        let rows = sqlx::query(&sql)
            .bind(account)
            .bind(&id)
            .bind(&outcome)
            .bind(&since)
            .bind(&until)
            .bind(&cutoff)
            .bind(&active)
            .bind(&platform)
            .bind(&protocol)
            .bind(&kernel)
            .bind(&requested_model)
            .bind(&actual_model)
            .bind(i64::from(page_size))
            .bind(i64::from(page - 1) * i64::from(page_size))
            .fetch_all(&self.pool)
            .await
            .map_err(|_| unavailable())?;
        let items = rows
            .iter()
            .map(|row| {
                let mut item: RequestDiagnostic =
                    decode(row.try_get("summary_json").map_err(|_| unavailable())?)?;
                (item.account_name, item.account_email) = account_display(row)?;
                let attempt: String = row.try_get("last_attempt").map_err(|_| unavailable())?;
                item.last_attempt = if attempt.is_empty() {
                    None
                } else {
                    Some(Box::new(decode(attempt)?))
                };
                Ok(item)
            })
            .collect::<Result<_, AppError>>()?;
        let counts = sqlx::query(&format!("SELECT CAST(COUNT(*) AS BIGINT) AS total,CAST(COALESCE(SUM(CASE WHEN r.outcome IN ('incomplete','upstream_error','upstream_rejected','local_rejected','transport_error','body_error') THEN 1 ELSE 0 END),0) AS BIGINT) AS errors,CAST(COALESCE(SUM(CASE WHEN r.outcome='in_progress' THEN 1 ELSE 0 END),0) AS BIGINT) AS processing FROM request_diagnostics r {FILTER}"))
            .bind(account).bind(&id).bind("").bind(&since).bind(&until).bind(&cutoff).bind(&active)
            .bind(&platform).bind(&protocol).bind(&kernel).bind(&requested_model).bind(&actual_model)
            .fetch_one(&self.pool).await.map_err(|_| unavailable())?;
        Ok(DiagnosticPage {
            items,
            total,
            page,
            page_size,
            counts: DiagnosticCounts {
                all: counts.try_get("total").map_err(|_| unavailable())?,
                errors: counts.try_get("errors").map_err(|_| unavailable())?,
                processing: counts.try_get("processing").map_err(|_| unavailable())?,
            },
            health: DiagnosticHealth {
                dropped_records: self.dropped.load(Ordering::Relaxed),
                write_failures: self.failures.load(Ordering::Relaxed),
                observation_failures: self.observation_failures.load(Ordering::Relaxed),
            },
        })
    }

    /// 按内部请求 UUID 获取完整尝试链。
    /// @param request_id 列表或响应返回的内部请求 UUID。
    /// @return 请求详情；不存在时返回 NotFound。
    pub async fn detail(&self, request_id: &str) -> Result<DiagnosticDetail, AppError> {
        let row =
            sqlx::query("SELECT r.summary_json,COALESCE(a.name,'') AS account_name,COALESCE(a.email,'') AS account_email
                FROM request_diagnostics r LEFT JOIN accounts a ON a.id=r.account_id
                WHERE r.request_id=$1 AND (r.started_at >= $2 OR $3 LIKE '%\"' || r.request_id || '\"%')")
                .bind(request_id)
                .bind(retention_cutoff(Utc::now()))
                .bind(active_json(&self.active))
                .fetch_optional(&self.pool)
                .await
                .map_err(|_| unavailable())?;
        let row = row.ok_or(AppError::NotFound)?;
        let mut request: RequestDiagnostic =
            decode(row.try_get("summary_json").map_err(|_| unavailable())?)?;
        (request.account_name, request.account_email) = account_display(&row)?;
        let rows = sqlx::query("SELECT d.summary_json,COALESCE(a.name,'') AS account_name,COALESCE(a.email,'') AS account_email
            FROM request_diagnostic_attempts d LEFT JOIN accounts a ON a.id=d.account_id
            WHERE d.request_id=$1 ORDER BY d.ordinal,d.attempt_id")
            .bind(request_id).fetch_all(&self.pool).await.map_err(|_| unavailable())?;
        let attempts = rows
            .iter()
            .map(|row| {
                let mut item: AttemptDiagnostic =
                    decode(row.try_get("summary_json").map_err(|_| unavailable())?)?;
                (item.account_name, item.account_email) = account_display(row)?;
                Ok(item)
            })
            .collect::<Result<_, AppError>>()?;
        Ok(DiagnosticDetail { request, attempts })
    }
}

fn account_display(row: &AnyRow) -> Result<(Option<String>, Option<String>), AppError> {
    // 只投影读取时的安全资料；持久摘要及业务热路径继续保持原来的匿名边界。
    let name: String = row.try_get("account_name").map_err(|_| unavailable())?;
    let email: String = row.try_get("account_email").map_err(|_| unavailable())?;
    Ok((
        (!name.trim().is_empty()).then_some(name),
        (!email.trim().is_empty()).then_some(email),
    ))
}

fn unavailable() -> AppError {
    AppError::ServiceUnavailable("请求诊断存储不可用".into())
}

fn decode<T: DeserializeOwned>(value: String) -> Result<T, AppError> {
    serde_json::from_str(&value).map_err(|_| unavailable())
}

fn query_time(value: Option<String>) -> Result<String, AppError> {
    value
        .map(|value| {
            DateTime::parse_from_rfc3339(&value)
                .map(|value| {
                    value
                        .with_timezone(&Utc)
                        .to_rfc3339_opts(SecondsFormat::Millis, true)
                })
                .map_err(|_| AppError::BadRequest("诊断时间须为 RFC3339".into()))
        })
        .transpose()
        .map(|v| v.unwrap_or_default())
}

fn query_filter(value: Option<String>, choices: &[&str]) -> Result<String, AppError> {
    let value = value.unwrap_or_default();
    if value.is_empty() {
        return Ok(value);
    }
    if value.len() > 128
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b))
        || (!choices.is_empty() && !choices.contains(&value.as_str()))
    {
        return Err(AppError::BadRequest("诊断筛选值无效".into()));
    }
    Ok(value)
}

async fn update_attempt_fact(
    pool: &AnyPool,
    attempt_id: &str,
    account_id: i64,
    turn: Option<&ToolTurnDiagnostic>,
    capture: Option<&str>,
    control: Option<(&str, &str)>,
) -> Result<(), sqlx::Error> {
    let mut tx = pool.begin().await?;
    if pool.connect_options().database_url.scheme() == "sqlite" {
        // 与凭据提交共享SQLite写权限，防止限定字段补写使用过期读快照。
        sqlx::query("UPDATE request_diagnostic_attempts SET ordinal=ordinal WHERE 1=0")
            .execute(&mut *tx)
            .await?;
    }
    let row = sqlx::query("SELECT summary_json FROM request_diagnostic_attempts WHERE attempt_id=$1 AND account_id=$2")
        .bind(attempt_id).bind(account_id).fetch_optional(&mut *tx).await?;
    if let Some(row) = row {
        let raw: String = row.try_get("summary_json")?;
        let mut attempt: AttemptDiagnostic = serde_json::from_str(&raw)
            .map_err(|_| sqlx::Error::Protocol("工具诊断摘要损坏".into()))?;
        let mut changed = false;
        if let Some(status) = capture {
            attempt.capture_status = Some(status.into());
            changed = true;
        }
        if let (Some(context), Some(turn)) = (attempt.context.as_mut(), turn) {
            let previous = context.tool_turn.as_ref();
            // 终态不可被晚到的waiting覆盖，重复收口保持原观测时刻。
            if previous.is_none_or(|old| old.state == "waiting" || old.state == "continuation") {
                context.tool_turn = Some(turn.clone());
                changed = true;
            }
        }
        if let (Some(context), Some((status, observed_at))) = (attempt.context.as_mut(), control) {
            if context.control_state.is_none() {
                context.control_state = Some(status.into());
                context.control_observed_at = Some(observed_at.into());
                changed = true;
            }
        }
        if changed {
            let raw = serde_json::to_string(&attempt)
                .map_err(|_| sqlx::Error::Protocol("工具诊断编码失败".into()))?;
            if raw.len() > MAX_RECORD_BYTES {
                return Err(sqlx::Error::Protocol("工具诊断超限".into()));
            }
            sqlx::query("UPDATE request_diagnostic_attempts SET summary_json=$1 WHERE attempt_id=$2 AND account_id=$3")
                    .bind(raw).bind(attempt_id).bind(account_id).execute(&mut *tx).await?;
        }
    }
    tx.commit().await
}

async fn write_event(pool: &AnyPool, event: &DiagnosticEvent) -> Result<(), sqlx::Error> {
    let request = &event.request;
    let json = serde_json::to_string(request)
        .map_err(|_| sqlx::Error::Protocol("诊断序列化失败".into()))?;
    let attempt_json = event
        .attempt
        .as_ref()
        .map(serde_json::to_string)
        .transpose()
        .map_err(|_| sqlx::Error::Protocol("诊断序列化失败".into()))?;
    if json.len() > MAX_RECORD_BYTES
        || attempt_json
            .as_ref()
            .is_some_and(|json| json.len() > MAX_RECORD_BYTES)
    {
        return Err(sqlx::Error::Protocol("诊断摘要超出上限".into()));
    }
    let mut tx = pool.begin().await?;
    // 迟到的尝试不能把已经终结的请求重新写成进行中。
    sqlx::query("INSERT INTO request_diagnostics(request_id,started_at,finished_at,response_request_id,outcome,summary_json,account_id,platform,entry_protocol,requested_model)
        VALUES($1,$2,NULLIF($3,''),NULLIF($4,''),$5,$6,NULLIF($7,0),NULLIF($8,''),NULLIF($9,''),NULLIF($10,'')) ON CONFLICT(request_id) DO UPDATE SET
        finished_at=COALESCE(excluded.finished_at,request_diagnostics.finished_at),
        response_request_id=COALESCE(excluded.response_request_id,request_diagnostics.response_request_id),
        account_id=COALESCE(excluded.account_id,request_diagnostics.account_id),
        platform=COALESCE(request_diagnostics.platform,excluded.platform),entry_protocol=COALESCE(request_diagnostics.entry_protocol,excluded.entry_protocol),requested_model=COALESCE(request_diagnostics.requested_model,excluded.requested_model),
        outcome=CASE WHEN excluded.finished_at IS NOT NULL THEN excluded.outcome ELSE request_diagnostics.outcome END,
        summary_json=CASE WHEN excluded.finished_at IS NOT NULL OR request_diagnostics.finished_at IS NULL THEN excluded.summary_json ELSE request_diagnostics.summary_json END")
        // SQLx Any 的空值使用 i32 编码；绑定类型固定，再用 NULLIF 还原未知值，避免 PG 缓存参数类型漂移。
        .bind(&request.request_id).bind(&request.started_at).bind(request.finished_at.as_deref().unwrap_or_default()).bind(request.response_request_id.as_deref().unwrap_or_default())
        .bind(&request.outcome).bind(json).bind(request.account_id.unwrap_or(0))
        .bind(request.context.as_ref().and_then(|c|c.platform.as_deref()).unwrap_or_default())
        .bind(request.context.as_ref().and_then(|c|c.entry_protocol.as_deref()).unwrap_or_default())
        .bind(request.context.as_ref().and_then(|c|c.requested_model.as_deref()).unwrap_or_default()).execute(&mut *tx).await?;
    if let Some(attempt) = &event.attempt {
        sqlx::query("INSERT INTO request_diagnostic_attempts(attempt_id,request_id,ordinal,account_id,started_at,upstream_request_id,summary_json,finished_at,platform,kernel_version,actual_model)
            VALUES($1,$2,$3,$4,$5,NULLIF($6,''),$7,NULLIF($8,''),NULLIF($9,''),NULLIF($10,''),NULLIF($11,'')) ON CONFLICT(attempt_id) DO UPDATE SET
            finished_at=COALESCE(excluded.finished_at,request_diagnostic_attempts.finished_at),
            platform=COALESCE(request_diagnostic_attempts.platform,excluded.platform),kernel_version=COALESCE(request_diagnostic_attempts.kernel_version,excluded.kernel_version),actual_model=COALESCE(request_diagnostic_attempts.actual_model,excluded.actual_model),
            upstream_request_id=COALESCE(excluded.upstream_request_id,request_diagnostic_attempts.upstream_request_id),
            summary_json=CASE WHEN excluded.finished_at IS NOT NULL OR request_diagnostic_attempts.finished_at IS NULL THEN excluded.summary_json ELSE request_diagnostic_attempts.summary_json END")
            .bind(&attempt.attempt_id).bind(&attempt.request_id).bind(i64::from(attempt.ordinal)).bind(attempt.account_id)
            .bind(&attempt.started_at).bind(attempt.upstream_request_id.as_deref().unwrap_or_default()).bind(attempt_json.unwrap_or_default()).bind(attempt.finished_at.as_deref().unwrap_or_default())
            .bind(attempt.context.as_ref().and_then(|c|c.platform.as_deref()).unwrap_or_default())
            .bind(attempt.context.as_ref().and_then(|c|c.kernel_version.as_deref()).unwrap_or_default())
            .bind(attempt.context.as_ref().and_then(|c|c.submitted_model.as_deref()).unwrap_or_default())
            .execute(&mut *tx).await?;
    }
    tx.commit().await
}

fn retention_cutoff(now: DateTime<Utc>) -> String {
    (now - ChronoDuration::days(7)).to_rfc3339_opts(SecondsFormat::Millis, true)
}

fn usage_count(row: &AnyRow, key: &str) -> Result<Option<u64>, AppError> {
    // 通过十进制字符串读取，避开 SQLx Any 在两库上的 NUMERIC 类型差异。
    row.try_get::<Option<String>, _>(key)?
        .map(|value| {
            value
                .parse()
                .map_err(|_| AppError::Internal("反重力用量统计数值超出范围".into()))
        })
        .transpose()
}

fn active_json(active: &Mutex<HashSet<String>>) -> String {
    // 请求 ID 为内部标准 UUID；JSON 引号分隔成员，SQL 参数保持固定字符串类型。
    serde_json::to_string(&*active.lock().unwrap_or_else(|error| error.into_inner()))
        .unwrap_or_default()
}

async fn prune(
    pool: &AnyPool,
    now: DateTime<Utc>,
    active: &Mutex<HashSet<String>>,
) -> Result<(), sqlx::Error> {
    let cutoff = retention_cutoff(now);
    let active = active_json(active);
    let mut tx = pool.begin().await?;
    sqlx::query("DELETE FROM request_diagnostic_attempts WHERE request_id IN (SELECT request_id FROM request_diagnostics WHERE started_at < $1 AND $2 NOT LIKE '%\"' || request_id || '\"%')")
        .bind(&cutoff).bind(&active).execute(&mut *tx).await?;
    sqlx::query("DELETE FROM request_diagnostics WHERE started_at < $1 AND $2 NOT LIKE '%\"' || request_id || '\"%'")
        .bind(cutoff)
        .bind(active)
        .execute(&mut *tx)
        .await?;
    tx.commit().await
}

#[cfg(test)]
mod tests {
    use super::{
        DiagnosticEvent, DiagnosticsStore, QUEUE_CAPACITY, prune, update_attempt_fact, write_event,
    };
    use crate::error::AppError;
    use crate::model::request_diagnostics::{
        AttemptDiagnostic, DiagnosticContext, DiagnosticParameters, DiagnosticQuery,
        DiagnosticSessions, DiagnosticTokens, GeminiDiagnosticUsage, RequestDiagnostic,
        ToolTurnDiagnostic,
    };
    use crate::store::db::migrate;
    use chrono::{DateTime, Duration as ChronoDuration, SecondsFormat, Utc};
    use sqlx::any::AnyPoolOptions;
    use std::sync::atomic::Ordering;
    use uuid::Uuid;

    fn request(at: DateTime<Utc>) -> RequestDiagnostic {
        let request_id = Uuid::new_v4().to_string();
        RequestDiagnostic {
            context: None,
            native_rejection: None,
            original_session_id: None,
            last_attempt: None,
            log_mode: None,
            request_id: request_id.clone(),
            started_at: at.to_rfc3339_opts(SecondsFormat::Millis, true),
            finished_at: Some(at.to_rfc3339_opts(SecondsFormat::Millis, true)),
            status_code: Some(200),
            account_id: Some(7),
            account_name: None,
            account_email: None,
            response_request_id: Some(request_id),
            outcome: "success".into(),
            error_stage: None,
            attempt_count: 1,
        }
    }

    fn attempt(request: &RequestDiagnostic) -> AttemptDiagnostic {
        AttemptDiagnostic {
            context: None,
            execution_location: None,
            runtime: None,
            log_mode: None,
            capture_status: None,
            attempt_id: Uuid::new_v4().to_string(),
            request_id: request.request_id.clone(),
            ordinal: 1,
            account_id: 7,
            account_name: None,
            account_email: None,
            profile_version: "2.1.293".into(),
            profile_selection: "client_version".into(),
            parameters: DiagnosticParameters::default(),
            sessions: DiagnosticSessions::default(),
            started_at: request.started_at.clone(),
            finished_at: request.finished_at.clone(),
            ttft_ms: Some(10),
            first_output_ms: Some(15),
            duration_ms: Some(20),
            status_code: Some(200),
            upstream_request_id: Some("req_synthetic0".into()),
            response_model: None,
            response_message_hash: None,
            stop_reason: Some("end_turn".into()),
            tokens: DiagnosticTokens::default(),
            partial: false,
            outcome: "success".into(),
            error_stage: None,
            error_type: None,
            retry_reason: None,
        }
    }

    async fn storage_contract(dsn: &str) {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(2)
            .connect(dsn)
            .await
            .unwrap();
        migrate(
            &pool,
            if dsn.starts_with("sqlite:") {
                "sqlite"
            } else {
                "postgres"
            },
        )
        .await
        .unwrap();
        DiagnosticsStore::migrate(&pool).await.unwrap();
        // 用未来一天作为裁剪参考，使后台真实时钟不会影响精确边界断言。
        let now = Utc::now() + ChronoDuration::days(1);
        let old = request(now - ChronoDuration::days(7) - ChronoDuration::seconds(1));
        let mut boundary = request(now - ChronoDuration::days(7));
        boundary.account_id = None;
        boundary.attempt_count = 0;
        let mut current = request(now);
        current.original_session_id = Some("synthetic-original-session".into());
        let attempted = attempt(&current);
        let event = DiagnosticEvent {
            request: current.clone(),
            attempt: Some(attempted.clone()),
        };
        // 真实入口先写全部可空字段为空的开始记录，再在同连接的缓存语句中写终态。
        let mut started = boundary.clone();
        started.finished_at = None;
        started.response_request_id = None;
        started.outcome = "in_progress".into();
        let mut started_attempt = attempted.clone();
        started_attempt.finished_at = None;
        started_attempt.upstream_request_id = None;
        started_attempt.outcome = "in_progress".into();
        started_attempt.partial = true;
        write_event(
            &pool,
            &DiagnosticEvent {
                request: started,
                attempt: None,
            },
        )
        .await
        .unwrap();
        let mut started_current = current.clone();
        started_current.finished_at = None;
        started_current.response_request_id = None;
        started_current.outcome = "in_progress".into();
        write_event(
            &pool,
            &DiagnosticEvent {
                request: started_current,
                attempt: Some(started_attempt),
            },
        )
        .await
        .unwrap();
        write_event(
            &pool,
            &DiagnosticEvent {
                request: old.clone(),
                attempt: Some(attempt(&old)),
            },
        )
        .await
        .unwrap();
        write_event(
            &pool,
            &DiagnosticEvent {
                request: boundary.clone(),
                attempt: None,
            },
        )
        .await
        .unwrap();
        write_event(&pool, &event).await.unwrap();
        write_event(&pool, &event).await.unwrap();
        let mut late = current.clone();
        late.finished_at = None;
        late.outcome = "in_progress".into();
        write_event(
            &pool,
            &DiagnosticEvent {
                request: late,
                attempt: None,
            },
        )
        .await
        .unwrap();
        prune(&pool, now, &Default::default()).await.unwrap();
        let store = DiagnosticsStore::new(pool.clone());
        store.flush().await.unwrap();
        let by_id = store
            .list(DiagnosticQuery {
                correlation_id: Some("req_synthetic0".into()),
                ..Default::default()
            })
            .await
            .unwrap();
        assert_eq!(by_id.total, 1);
        assert_eq!(by_id.items[0].request_id, current.request_id);
        assert_eq!(by_id.items[0].outcome, "success");
        assert_eq!(
            store
                .list(DiagnosticQuery {
                    account_id: Some(7),
                    ..Default::default()
                })
                .await
                .unwrap()
                .total,
            1
        );
        assert_eq!(
            store
                .list(DiagnosticQuery {
                    since: Some(boundary.started_at.clone()),
                    ..Default::default()
                })
                .await
                .unwrap()
                .total,
            2
        );
        let page = store
            .list(DiagnosticQuery {
                page: Some(2),
                page_size: Some(1),
                ..Default::default()
            })
            .await
            .unwrap();
        assert_eq!(page.total, 2);
        assert_eq!(page.items[0].request_id, boundary.request_id);
        assert!(matches!(
            store.detail(&old.request_id).await,
            Err(AppError::NotFound)
        ));
        for query in [
            DiagnosticQuery {
                page: Some(0),
                ..Default::default()
            },
            DiagnosticQuery {
                page_size: Some(201),
                ..Default::default()
            },
            DiagnosticQuery {
                since: Some("错误时间".into()),
                ..Default::default()
            },
            DiagnosticQuery {
                outcome: Some("未知结果".into()),
                ..Default::default()
            },
        ] {
            assert!(matches!(
                store.list(query).await,
                Err(AppError::BadRequest(_))
            ));
        }
        drop(store);
        pool.close().await;
        let reader = AnyPoolOptions::new()
            .max_connections(1)
            .connect(dsn)
            .await
            .unwrap();
        let reopened = DiagnosticsStore::new(reader.clone());
        let detail = reopened.detail(&current.request_id).await.unwrap();
        assert_eq!(
            detail.request.original_session_id,
            current.original_session_id
        );
        assert_eq!(detail.attempts.len(), 1);
        assert_eq!(detail.attempts[0].attempt_id, attempted.attempt_id);
        assert!(detail.request.account_name.is_none());
        assert!(detail.attempts[0].account_email.is_none());

        // 名称邮箱只在读取时关联；同一根请求的各次重试保留各自实际账号。
        for (id, name, email) in [
            (7_i64, "演示账号甲", "first@example.test"),
            (8, "演示账号乙", "second@example.test"),
        ] {
            sqlx::query("INSERT INTO accounts(id,name,email,token,device_id) VALUES($1,$2,$3,'synthetic-private-account-token','synthetic-device')")
                .bind(id).bind(name).bind(email).execute(&reader).await.unwrap();
        }
        let mut retried = current.clone();
        retried.account_id = Some(8);
        retried.attempt_count = 2;
        let mut second = attempt(&retried);
        second.account_id = 8;
        second.ordinal = 2;
        write_event(
            &reader,
            &DiagnosticEvent {
                request: retried,
                attempt: Some(second),
            },
        )
        .await
        .unwrap();
        let detail = reopened.detail(&current.request_id).await.unwrap();
        assert_eq!(detail.request.account_name.as_deref(), Some("演示账号乙"));
        assert_eq!(
            detail.request.account_email.as_deref(),
            Some("second@example.test")
        );
        assert_eq!(
            detail.attempts[0].account_name.as_deref(),
            Some("演示账号甲")
        );
        assert_eq!(
            detail.attempts[0].account_email.as_deref(),
            Some("first@example.test")
        );
        assert_eq!(detail.attempts[1].account_name, detail.request.account_name);
        assert!(
            !serde_json::to_string(&detail)
                .unwrap()
                .contains("synthetic-private-account-token")
        );
        let page = reopened
            .list(DiagnosticQuery {
                account_id: Some(7),
                ..Default::default()
            })
            .await
            .unwrap();
        assert_eq!(page.total, 1);
        assert_eq!(page.items[0].account_id, Some(8));
        assert_eq!(
            page.items[0].original_session_id,
            current.original_session_id
        );
        assert_eq!(page.items[0].account_name, detail.request.account_name);
        assert_eq!(page.counts.all, 1);
        assert_eq!(page.counts.errors, 0);
        assert_eq!(page.items[0].last_attempt.as_ref().unwrap().ordinal, 2);
        let errors = reopened
            .list(DiagnosticQuery {
                account_id: Some(7),
                outcome: Some("errors".into()),
                ..Default::default()
            })
            .await
            .unwrap();
        assert_eq!(errors.total, 0);
        // 快捷计数保留账号条件，并独立于当前结果筛选。
        assert_eq!(errors.counts.all, 1);
        assert_eq!(errors.counts.errors, 0);
        let mut failed = current.clone();
        failed.request_id = uuid::Uuid::new_v4().to_string();
        failed.account_id = Some(7);
        failed.outcome = "transport_error".into();
        let failed_id = failed.request_id.clone();
        write_event(
            &reader,
            &DiagnosticEvent {
                request: failed,
                attempt: None,
            },
        )
        .await
        .unwrap();
        let errors = reopened
            .list(DiagnosticQuery {
                account_id: Some(7),
                outcome: Some("errors".into()),
                ..Default::default()
            })
            .await
            .unwrap();
        assert_eq!(errors.total, 1);
        assert_eq!(errors.counts.all, 2);
        assert_eq!(errors.counts.errors, 1);
        assert_eq!(errors.items[0].request_id, failed_id);
        sqlx::query("DELETE FROM request_diagnostics WHERE request_id=$1")
            .bind(failed_id)
            .execute(&reader)
            .await
            .unwrap();

        sqlx::query("UPDATE accounts SET name=$1,email='' WHERE id=$2")
            .bind("已改名账号")
            .bind(8_i64)
            .execute(&reader)
            .await
            .unwrap();
        sqlx::query("UPDATE accounts SET name='' WHERE id=$1")
            .bind(7_i64)
            .execute(&reader)
            .await
            .unwrap();
        let renamed = reopened.detail(&current.request_id).await.unwrap();
        assert_eq!(renamed.request.account_name.as_deref(), Some("已改名账号"));
        assert!(renamed.request.account_email.is_none());
        assert!(renamed.attempts[0].account_name.is_none());
        assert_eq!(
            renamed.attempts[0].account_email.as_deref(),
            Some("first@example.test")
        );
        let raw: String =
            sqlx::query_scalar("SELECT summary_json FROM request_diagnostics WHERE request_id=$1")
                .bind(&current.request_id)
                .fetch_one(&reader)
                .await
                .unwrap();
        assert!(
            !raw.contains("account_name")
                && !raw.contains("account_email")
                && !raw.contains("@example.test")
        );
        let raw_attempts: Vec<String> = sqlx::query_scalar(
            "SELECT summary_json FROM request_diagnostic_attempts WHERE request_id=$1",
        )
        .bind(&current.request_id)
        .fetch_all(&reader)
        .await
        .unwrap();
        assert!(
            raw_attempts
                .iter()
                .all(|raw| !raw.contains("account_email") && !raw.contains("@example.test"))
        );

        sqlx::query("DELETE FROM accounts WHERE id=$1 OR id=$2")
            .bind(7_i64)
            .bind(8_i64)
            .execute(&reader)
            .await
            .unwrap();
        let deleted = reopened.detail(&current.request_id).await.unwrap();
        assert_eq!(deleted.request.account_id, Some(8));
        assert!(deleted.request.account_name.is_none() && deleted.request.account_email.is_none());
        assert_eq!(deleted.attempts.len(), 2);
        assert!(
            deleted
                .attempts
                .iter()
                .all(|item| item.account_name.is_none() && item.account_email.is_none())
        );
        let unknown = reopened.detail(&boundary.request_id).await.unwrap();
        let mut agy = request(Utc::now());
        agy.context = Some(DiagnosticContext {
            platform: Some("antigravity".into()),
            entry_protocol: Some("gemini".into()),
            requested_model: Some("claude-synthetic".into()),
            ..Default::default()
        });
        let mut sent = attempt(&agy);
        sent.context = Some(DiagnosticContext {
            platform: Some("antigravity".into()),
            kernel_version: Some("1.5.9".into()),
            submitted_model: Some("MODEL_SYNTHETIC".into()),
            tool_turn: Some(ToolTurnDiagnostic {
                state: "waiting".into(),
                observed_at: agy.started_at.clone(),
                ..Default::default()
            }),
            ..Default::default()
        });
        write_event(
            &reader,
            &DiagnosticEvent {
                request: agy.clone(),
                attempt: Some(sent.clone()),
            },
        )
        .await
        .unwrap();
        let filtered = reopened
            .list(DiagnosticQuery {
                platform: Some("antigravity".into()),
                entry_protocol: Some("gemini".into()),
                kernel_version: Some("1.5.9".into()),
                requested_model: Some("claude-synthetic".into()),
                actual_model: Some("MODEL_SYNTHETIC".into()),
                ..Default::default()
            })
            .await
            .unwrap();
        assert_eq!(filtered.total, 1);
        assert_eq!(filtered.counts.all, 1);
        assert_eq!(filtered.items[0].request_id, agy.request_id);
        let hidden = reopened
            .list(DiagnosticQuery {
                platform: Some("antigravity".into()),
                actual_model: Some("wrong-model".into()),
                ..Default::default()
            })
            .await
            .unwrap();
        assert_eq!(hidden.total, 0);
        let turn = ToolTurnDiagnostic {
            state: "completed".into(),
            observed_at: agy.finished_at.clone().unwrap(),
            ..Default::default()
        };
        update_attempt_fact(&reader, &sent.attempt_id, 7, Some(&turn), None, None)
            .await
            .unwrap();
        update_attempt_fact(&reader, &sent.attempt_id, 7, None, Some("saved"), None)
            .await
            .unwrap();
        update_attempt_fact(
            &reader,
            &sent.attempt_id,
            7,
            None,
            None,
            Some(("completed", &turn.observed_at)),
        )
        .await
        .unwrap();
        update_attempt_fact(
            &reader,
            &sent.attempt_id,
            7,
            None,
            None,
            Some(("error", &turn.observed_at)),
        )
        .await
        .unwrap();
        let late = ToolTurnDiagnostic {
            state: "waiting".into(),
            ..turn.clone()
        };
        update_attempt_fact(&reader, &sent.attempt_id, 7, Some(&late), None, None)
            .await
            .unwrap();
        let finalized = reopened.detail(&agy.request_id).await.unwrap();
        assert_eq!(finalized.request.finished_at, agy.finished_at);
        assert_eq!(finalized.request.outcome, "success");
        assert_eq!(finalized.request.attempt_count, 1);
        assert_eq!(
            finalized.attempts[0]
                .context
                .as_ref()
                .unwrap()
                .control_state
                .as_deref(),
            Some("completed")
        );
        assert_eq!(
            finalized.attempts[0]
                .context
                .as_ref()
                .unwrap()
                .control_observed_at
                .as_deref(),
            Some(turn.observed_at.as_str())
        );
        assert_eq!(
            finalized.attempts[0]
                .context
                .as_ref()
                .unwrap()
                .tool_turn
                .as_ref()
                .unwrap()
                .state,
            "completed"
        );
        assert_eq!(finalized.attempts[0].duration_ms, sent.duration_ms);
        assert_eq!(
            finalized.attempts[0].capture_status.as_deref(),
            Some("saved")
        );
        assert!(unknown.request.original_session_id.is_none());
        assert!(unknown.request.account_id.is_none() && unknown.request.account_name.is_none());
        agy_usage_contract(&reopened, &reader, now).await;
        drop(reopened);
        reader.close().await;
    }

    async fn agy_usage_contract(
        store: &DiagnosticsStore,
        pool: &sqlx::AnyPool,
        now: DateTime<Utc>,
    ) {
        let agy_request = |at| {
            let mut root = request(at);
            root.context = Some(DiagnosticContext {
                platform: Some("antigravity".into()),
                entry_protocol: Some("gemini".into()),
                ..Default::default()
            });
            root
        };
        let recent = agy_request(now - ChronoDuration::hours(5));
        let older = agy_request(now - ChronoDuration::days(7));
        let future = agy_request(now);
        let empty = agy_request(now - ChronoDuration::hours(1));
        for (root, account_id, total) in [
            (&recent, 71, Some(3_000_000_000)),
            (&recent, 71, None),
            (&recent, 72, Some(0)),
            (&older, 71, Some(11)),
            (&future, 71, Some(500)),
        ] {
            let mut a = attempt(root);
            a.account_id = account_id;
            a.context = Some(DiagnosticContext {
                platform: Some("antigravity".into()),
                usage: Some(GeminiDiagnosticUsage {
                    source: "gemini_usage_metadata".into(),
                    total_tokens: total,
                    thoughts_tokens: Some(700),
                    complete: total.is_some(),
                    ..Default::default()
                }),
                ..Default::default()
            });
            let event = DiagnosticEvent {
                request: root.clone(),
                attempt: Some(a),
            };
            write_event(pool, &event).await.unwrap();
            write_event(pool, &event).await.unwrap();
        }
        write_event(
            pool,
            &DiagnosticEvent {
                request: empty,
                attempt: None,
            },
        )
        .await
        .unwrap();
        let stats = store.agy_request_usage(&[71, 72, 73], now).await.unwrap();
        assert_eq!(stats[&71].five_hour.requests, 1);
        assert_eq!(stats[&71].five_hour.tokens, Some(3_000_000_000));
        assert_eq!(stats[&71].five_hour.partial_requests, 1);
        assert_eq!(stats[&71].seven_day.requests, 2);
        assert_eq!(stats[&71].seven_day.tokens, Some(3_000_000_011));
        assert_eq!(stats[&72].five_hour.requests, 1);
        assert_eq!(stats[&72].five_hour.tokens, Some(0));
        assert_eq!(stats[&73].seven_day.requests, 0);
        assert_eq!(stats[&73].seven_day.tokens, None);
    }

    /// 验证 SQLite 独立连接、重启、重复终结、查询和七天保留。
    #[tokio::test]
    async fn sqlite_diagnostics_storage_contract() {
        let path = std::env::temp_dir().join(format!("cc2api-diagnostics-{}.db", Uuid::new_v4()));
        storage_contract(&format!("sqlite:{}?mode=rwc", path.display())).await;
        let _ = std::fs::remove_file(path);
    }

    /// 真实许可保护在途请求，结束后隐藏并回收，重启遗留 unfinished 按时间处理。
    #[tokio::test]
    async fn retention_protects_live_requests_and_expires_stale_unfinished_records() {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        let store = DiagnosticsStore::new(pool.clone());
        store.flush().await.unwrap();
        let now = Utc::now();
        let mut live = request(now - ChronoDuration::days(8));
        live.finished_at = None;
        live.outcome = "in_progress".into();
        let stale = request(now - ChronoDuration::days(8));
        let guard = store.track_request(&live.request_id);
        for item in [&live, &stale] {
            write_event(
                &pool,
                &DiagnosticEvent {
                    request: item.clone(),
                    attempt: Some(attempt(item)),
                },
            )
            .await
            .unwrap();
        }
        assert_eq!(
            store.list(DiagnosticQuery::default()).await.unwrap().total,
            1
        );
        assert!(matches!(
            store.detail(&stale.request_id).await,
            Err(AppError::NotFound)
        ));
        prune(&pool, now, &store.active).await.unwrap();
        assert_eq!(
            store.detail(&live.request_id).await.unwrap().attempts.len(),
            1
        );
        drop(guard);
        assert!(matches!(
            store.detail(&live.request_id).await,
            Err(AppError::NotFound)
        ));
        prune(&pool, now, &store.active).await.unwrap();
        assert_eq!(
            sqlx::query_scalar::<_, i64>(
                "SELECT CAST(COUNT(*) AS BIGINT) FROM request_diagnostic_attempts"
            )
            .fetch_one(&pool)
            .await
            .unwrap(),
            0
        );
        drop(store);
        pool.close().await;
    }

    /// 在独立临时 PostgreSQL 上执行完全相同的存储契约。
    #[tokio::test]
    #[ignore = "须提供 CC2API_DIAGNOSTICS_TEST_POSTGRES_DSN 指向独立临时数据库"]
    async fn postgres_diagnostics_storage_contract() {
        let dsn = std::env::var("CC2API_DIAGNOSTICS_TEST_POSTGRES_DSN").unwrap();
        storage_contract(&dsn).await;
    }

    /// 队列饱和必须立即返回，并显式报告丢弃和数据库故障。
    #[tokio::test]
    async fn diagnostics_overload_and_write_failures_are_observable() {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        let store = DiagnosticsStore::new(pool.clone());
        let root = request(Utc::now());
        for _ in 0..QUEUE_CAPACITY + 5 {
            store.submit(DiagnosticEvent {
                request: root.clone(),
                attempt: None,
            });
        }
        assert!(store.dropped.load(Ordering::Relaxed) >= 5);
        store.flush().await.unwrap();
        let page = store.list(DiagnosticQuery::default()).await.unwrap();
        assert!(page.health.dropped_records >= 5);
        sqlx::query("DROP TABLE request_diagnostic_attempts")
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("DROP TABLE request_diagnostics")
            .execute(&pool)
            .await
            .unwrap();
        store.submit(DiagnosticEvent {
            request: root,
            attempt: None,
        });
        store.flush().await.unwrap();
        assert!(store.failures.load(Ordering::Relaxed) > 0);
        assert!(store.list(DiagnosticQuery::default()).await.is_err());
    }
}
