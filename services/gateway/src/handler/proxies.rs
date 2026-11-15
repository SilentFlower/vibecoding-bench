//! 代理管理接口：公开摘要、分页与账号所有权保护。
use std::collections::HashMap;

use axum::Json;
use axum::extract::{Path, Query, State};
use serde::Deserialize;
use serde_json::{Value, json};

use crate::error::AppError;
use crate::handler::router::AppState;
use crate::model::proxy::{ProxyConnection, ProxyConnectionInput, ProxySyncTarget, expiry};
use crate::service::runtime_bridge;
use crate::store::proxy_store::ProxyRecord;

/// 有界代理搜索；搜索字段均为公开信息。
#[derive(Deserialize)]
pub struct ListQuery {
    page: Option<i64>,
    page_size: Option<i64>,
    q: Option<String>,
    usage: Option<bool>,
}

/// 创建及编辑连接载荷；认证字段缺省保留原值。
#[derive(Deserialize)]
pub struct ProxyInput {
    name: String,
    #[serde(flatten)]
    connection: ProxyConnectionInput,
    expires_at: Option<String>,
    revision: Option<String>,
}

/// 单条识别或多行导入的原始内容，仅在本次请求内使用。
#[derive(Deserialize)]
pub struct TextInput {
    text: String,
}

/// 删除必须携带界面确认时的版本。
#[derive(Deserialize)]
pub struct RevisionInput {
    revision: String,
}

struct References {
    by_connection: HashMap<String, Vec<Value>>,
    previous: HashMap<String, String>,
    complete: bool,
}

async fn references(state: &AppState) -> Result<References, AppError> {
    let mut result = References {
        by_connection: HashMap::new(),
        previous: HashMap::new(),
        complete: true,
    };
    let (accounts, runtime, pending) = tokio::join!(
        state.account_svc.list_accounts(),
        runtime_bridge::proxy_references(),
        state.proxy_svc.store.pending_sync()
    );
    for operation in pending? {
        result.previous.insert(
            operation.destination.fingerprint(),
            operation.source.fingerprint(),
        );
    }
    let active_counts = state.account_svc.active_request_counts().await;
    for account in accounts? {
        if account.proxy_url.is_empty() {
            continue;
        }
        let Ok(connection) = ProxyConnection::parse(&account.proxy_url) else {
            result.complete = false;
            continue;
        };
        result
            .by_connection
            .entry(connection.fingerprint())
            .or_default()
            .push(json!({
                "kind":"gateway", "id":account.id.to_string(), "name":account.name,
                "status":account.status, "in_flight":active_counts.get(&account.id).copied().unwrap_or(0)
            }));
    }
    for (id, raw) in state.oauth_flow_svc.proxy_references() {
        if let Ok(connection) = ProxyConnection::parse(&raw) {
            result.by_connection.entry(connection.fingerprint()).or_default().push(json!({
                "kind":"authorization", "id":id, "name":"授权登录", "status":"pending", "in_flight":null
            }));
        } else {
            result.complete = false;
        }
    }
    match runtime {
        Ok(value) => {
            result.complete &= value["complete"] == true;
            if let Some(items) = value["references"].as_array() {
                for item in items {
                    let Some(fingerprint) = item["fingerprint"]
                        .as_str()
                        .filter(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()))
                    else {
                        result.complete = false;
                        continue;
                    };
                    if !matches!(item["kind"].as_str(), Some("task" | "draft"))
                        || !item["id"].is_string()
                        || !item["name"].is_string()
                    {
                        result.complete = false;
                        continue;
                    }
                    // 只提取允许公开的字段，内部摘要和运行时扩展字段不能穿透到浏览器。
                    result
                        .by_connection
                        .entry(fingerprint.into())
                        .or_default()
                        .push(json!({
                            "kind":item["kind"], "id":item["id"], "name":item["name"],
                            "status":item["status"], "in_flight":item["in_flight"]
                        }));
                }
            } else {
                result.complete = false;
            }
        }
        Err(_) => result.complete = false,
    }
    Ok(result)
}

fn users_for(fingerprint: &str, refs: &References) -> Vec<Value> {
    let mut users = refs
        .by_connection
        .get(fingerprint)
        .cloned()
        .unwrap_or_default();
    if let Some(previous) = refs.previous.get(fingerprint) {
        for user in refs.by_connection.get(previous).into_iter().flatten() {
            if !users
                .iter()
                .any(|existing| existing["kind"] == user["kind"] && existing["id"] == user["id"])
            {
                users.push(user.clone());
            }
        }
    }
    users
}

fn public(record: &ProxyRecord, refs: &References) -> Value {
    let fingerprint = record.connection.fingerprint();
    let users = users_for(&fingerprint, refs);
    let active = users
        .iter()
        .filter(|item| item["in_flight"].as_i64().unwrap_or(0) > 0)
        .count();
    let in_flight: i64 = users
        .iter()
        .filter_map(|item| item["in_flight"].as_i64())
        .sum();
    json!({"id":record.id, "name":record.name, "protocol":record.connection.protocol,
        "host":record.connection.host, "port":record.connection.port, "public_url":record.connection.public_url,
        "has_username":!record.connection.username.is_empty(), "has_password":!record.connection.password.is_empty(),
        "expires_at":record.expires_at, "revision":record.revision, "observation":record.observation,
        "checked_at":record.checked_at, "status":record.status, "created_at":record.created_at, "updated_at":record.updated_at,
        "users":users, "references_complete":refs.complete, "active_accounts":active, "in_flight":in_flight,"sync_pending":refs.previous.contains_key(&fingerprint)})
}

fn valid_name(name: &str) -> Result<&str, AppError> {
    let name = name.trim();
    if name.is_empty() || name.chars().count() > 100 || name.chars().any(char::is_control) {
        return Err(AppError::BadRequest("代理名称须为1～100个字符".into()));
    }
    Ok(name)
}

fn ensure_unreferenced(record: &ProxyRecord, refs: &References) -> Result<(), AppError> {
    if !refs.complete {
        return Err(AppError::ServiceUnavailable(
            "使用情况待核对，请稍后再试".into(),
        ));
    }
    if !users_for(&record.connection.fingerprint(), refs).is_empty()
        || refs.previous.contains_key(&record.connection.fingerprint())
    {
        return Err(AppError::BadRequest(
            "线路正在被账号或登录草稿使用，请先在账号中切换代理".into(),
        ));
    }
    Ok(())
}

/// 查询公开线路及一次聚合的使用情况。
/// @param state 管理服务。@param query 分页搜索。@return 公开分页数据。
pub async fn list(
    State(state): State<AppState>,
    Query(query): Query<ListQuery>,
) -> Result<Json<Value>, AppError> {
    let page = query.page.unwrap_or(1);
    let size = query.page_size.unwrap_or(20);
    let search = query.q.unwrap_or_default();
    if page < 1 || !(1..=100).contains(&size) || search.len() > 256 {
        return Err(AppError::BadRequest("代理分页或搜索参数无效".into()));
    }
    let (records, refs, summary) = tokio::join!(
        state.proxy_svc.store.list(page, size, search.trim()),
        async {
            if query.usage == Some(false) {
                Ok(References {
                    by_connection: HashMap::new(),
                    previous: HashMap::new(),
                    complete: false,
                })
            } else {
                references(&state).await
            }
        },
        async {
            if query.usage == Some(false) {
                Ok(Vec::new())
            } else {
                state.proxy_svc.store.summary_index().await
            }
        }
    );
    let (records, total) = records?;
    let refs = refs?;
    let counts = if query.usage == Some(false) {
        Value::Null
    } else {
        directory_counts(&summary?, &refs)
    };
    Ok(Json(
        json!({"data": records.iter().map(|record| public(record, &refs)).collect::<Vec<_>>(),
        "total":total, "page":page, "page_size":size, "total_pages":(total + size - 1) / size,
        "references_complete":refs.complete,"counts":counts}),
    ))
}

/// 按完整目录聚合，未知引用保持null，私有连接不进入返回对象。
fn directory_counts(index: &[(String, String)], refs: &References) -> Value {
    let mut used = 0;
    let mut complete = refs.complete;
    for (raw, _) in index {
        match ProxyConnection::parse(raw) {
            Ok(connection) => {
                if !users_for(&connection.fingerprint(), refs).is_empty() {
                    used += 1;
                }
            }
            Err(_) => complete = false,
        }
    }
    json!({"all":index.len(),"available":index.iter().filter(|(_,status)|status=="ready").count(),
        "used":complete.then_some(used)})
}

#[cfg(test)]
mod summary_tests {
    use super::{References, directory_counts};
    use crate::model::proxy::ProxyConnection;
    use serde_json::json;
    use std::collections::HashMap;

    /// 总览使用完整目录，停用账号仍计入使用，未知引用不显示零。
    #[test]
    fn counts_keep_unavailable_usage_distinct_from_zero() {
        let connection =
            ProxyConnection::parse("http://private-user:private-pass@proxy.invalid:8080").unwrap();
        let mut refs = References {
            by_connection: HashMap::new(),
            previous: HashMap::new(),
            complete: true,
        };
        refs.by_connection
            .insert(connection.fingerprint(), vec![json!({"status":"disabled"})]);
        let index = vec![
            (connection.private_url.clone(), "ready".into()),
            ("http://second.invalid:80".into(), "unknown".into()),
        ];
        let value = directory_counts(&index, &refs);
        assert_eq!(value, json!({"all":2,"available":1,"used":1}));
        assert!(!value.to_string().contains("private-pass"));
        refs.complete = false;
        assert!(directory_counts(&index, &refs)["used"].is_null());
    }
}

/// 新建单条连接。@param state 管理服务。@param input 连接字段。@return 创建身份。
pub async fn create(
    State(state): State<AppState>,
    Json(input): Json<ProxyInput>,
) -> Result<Json<Value>, AppError> {
    let name = valid_name(&input.name)?.to_owned();
    let connection = ProxyConnection::from_input(&input.connection, None)?;
    let expires = expiry(input.expires_at.as_deref())?;
    let _guard = state.proxy_svc.mutations.lock().await;
    let ids = state
        .proxy_svc
        .store
        .insert_many(&[(name, connection, expires)])
        .await?;
    Ok(Json(json!({"id":ids[0]})))
}

/// 编辑线路；使用者通过持久任务在空闲后同步，版本冲突保持原配置。
/// @param state 管理服务。@param id 线路身份。@param input 表单。@return 更新身份。
pub async fn update(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(input): Json<ProxyInput>,
) -> Result<Json<Value>, AppError> {
    let name = valid_name(&input.name)?;
    let expires = expiry(input.expires_at.as_deref())?;
    let _guard = state.proxy_svc.mutations.lock().await;
    let previous = state.proxy_svc.store.get(&id).await?;
    if input.revision.as_deref() != Some(previous.revision.as_str()) {
        return Err(AppError::BadRequest(
            "代理已被修改，请刷新后重新编辑".into(),
        ));
    }
    let connection = ProxyConnection::from_input(&input.connection, Some(&previous.connection))?;
    let targets = if connection.private_url != previous.connection.private_url {
        let refs = references(&state).await?;
        if !refs.complete {
            return Err(AppError::ServiceUnavailable(
                "使用情况暂不可核对，请稍后保存".into(),
            ));
        }
        users_for(&previous.connection.fingerprint(), &refs)
            .into_iter()
            .map(serde_json::from_value::<ProxySyncTarget>)
            .collect::<Result<Vec<_>, _>>()
            .map_err(|_| AppError::ServiceUnavailable("关联账号身份待核对".into()))?
    } else {
        Vec::new()
    };
    state
        .proxy_svc
        .store
        .update_and_queue(&previous, name, &connection, expires.as_deref(), &targets)
        .await?;
    let sync_pending = state
        .proxy_svc
        .store
        .pending_sync()
        .await?
        .iter()
        .any(|operation| operation.proxy_id == id);
    super::proxy_sync::start(state.clone());
    Ok(Json(json!({"id":id,"sync_pending":sync_pending})))
}

/// 删除无引用的原版本。@param state 管理服务。@param id 线路身份。@param input 确认版本。@return 成功回执。
pub async fn delete(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(input): Json<RevisionInput>,
) -> Result<Json<Value>, AppError> {
    let _guard = state.proxy_svc.mutations.lock().await;
    let previous = state.proxy_svc.store.get(&id).await?;
    ensure_unreferenced(&previous, &references(&state).await?)?;
    state.proxy_svc.store.delete(&id, &input.revision).await?;
    Ok(Json(json!({"ok":true})))
}

/// 检测真实出口，返回公开观测。@param state 管理服务。@param id 线路身份。@return 实际检测状态。
pub async fn probe(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Result<Json<Value>, AppError> {
    let record = state.proxy_svc.store.get(&id).await?;
    let result = state.proxy_svc.probe(&record).await?;
    Ok(Json(
        json!({"id":id, "status":result.status, "observation":result.observation, "checked_at":result.checked_at}),
    ))
}

fn parse_line(raw: &str) -> Result<ProxyConnection, AppError> {
    let raw = raw.trim();
    if raw.len() > 8192 || raw.chars().any(char::is_whitespace) {
        return Err(AppError::BadRequest("代理格式无效，请输入单条连接".into()));
    }
    if raw.contains("://") {
        return ProxyConnection::parse(raw);
    }
    let parts: Vec<_> = raw.splitn(4, ':').collect();
    if parts.len() == 4 && !raw.contains('@') && !raw.contains('[') {
        return ProxyConnection::from_input(
            &ProxyConnectionInput {
                protocol: "http".into(),
                host: parts[0].into(),
                port: parts[1]
                    .parse()
                    .map_err(|_| AppError::BadRequest("代理端口无效".into()))?,
                username: Some(parts[2].into()),
                password: Some(parts[3].into()),
            },
            None,
        );
    }
    if raw
        .trim_end_matches('/')
        .rsplit(':')
        .next()
        .and_then(|port| port.parse::<u16>().ok())
        .is_none()
    {
        return Err(AppError::BadRequest("省略协议时请提供主机和端口".into()));
    }
    ProxyConnection::parse(&format!("http://{raw}"))
}

/// 识别用户刚提交的地址，仅向同一管理员返回其输入的认证字段。
/// @param input 原连接。@return 结构化字段；不保存。
pub async fn identify(Json(input): Json<TextInput>) -> Result<Json<Value>, AppError> {
    let connection = parse_line(&input.text)?;
    Ok(Json(
        json!({"protocol":connection.protocol,"host":connection.host,"port":connection.port,
        "username":connection.username,"password":connection.password}),
    ))
}

/// 原子批量导入，非法行仅返回行号。
/// @param state 管理服务。@param input 多行连接。@return 创建条数。
pub async fn import(
    State(state): State<AppState>,
    Json(input): Json<TextInput>,
) -> Result<Json<Value>, AppError> {
    let lines: Vec<_> = input
        .text
        .lines()
        .enumerate()
        .filter(|(_, line)| !line.trim().is_empty())
        .collect();
    if lines.is_empty() || lines.len() > 200 {
        return Err(AppError::BadRequest("每次导入1～200条代理".into()));
    }
    let mut values = Vec::with_capacity(lines.len());
    for (index, line) in lines {
        let connection = parse_line(line)
            .map_err(|_| AppError::BadRequest(format!("第{}行代理格式无效", index + 1)))?;
        values.push((connection.host.clone(), connection, None));
    }
    let _guard = state.proxy_svc.mutations.lock().await;
    let ids = state.proxy_svc.store.insert_many(&values).await?;
    Ok(Json(json!({"created":ids.len()})))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn import_supports_uri_and_common_provider_formats() {
        let parsed = parse_line("example.test:8080:user:pass").unwrap();
        assert_eq!(parsed.username, "user");
        assert_eq!(parsed.password, "pass");
        assert_eq!(parsed.public_url, "http://example.test:8080");
        assert!(parse_line("http://example.test:8080/path").is_err());
        assert_eq!(
            parse_line("user:pass@example.test:8080")
                .unwrap()
                .private_url,
            parsed.private_url
        );
        assert!(parse_line("example.test:0").is_err());
    }
}
