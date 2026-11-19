//! v3 管理桥：管理员交换短会话，浏览器不接触调度器服务秘密。

use axum::body::{Body, Bytes};
use axum::extract::ws::{Message, WebSocket};
use axum::extract::{OriginalUri, State, WebSocketUpgrade};
use axum::http::{HeaderMap, Method, header};
use axum::response::{IntoResponse, Response};
use axum::routing::{any, get};
use axum::{Json, Router};
use futures_util::{SinkExt, StreamExt};
use reqwest::redirect::Policy;
use reqwest::{Client, Error as ReqwestError};
use serde_json::{Value, json};
use std::sync::LazyLock;
use std::time::Duration;
use tokio::sync::Semaphore;
use tokio_tungstenite::connect_async;
use tokio_tungstenite::tungstenite::Message as UpstreamMessage;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use uuid::Uuid;

use crate::error::AppError;
use crate::handler::router::AppState;
use crate::model::proxy::ProxySyncTarget;
use crate::service::runtime_lease::RuntimeLease;
use crate::store::proxy_store::ProxyRecord;

mod task_proxy;

const SESSION_TIMEOUT: Duration = Duration::from_secs(5);
const STATUS_TIMEOUT: Duration = Duration::from_secs(10);

/// 核对维护前已经登记的 CLI 作业，拒绝旧 owner 的迟到重放。
/// @param account_id 原账号。
/// @param owner 原执行来源。
/// @return 运行时仍拥有原作业时为 true。
pub async fn update_admitted(account_id: i64, owner: &str) -> Result<bool, AppError> {
    let (base, token, client) = config()?;
    let response = client
        .post(format!("{base}/internal/v3/system-updates/admitted"))
        .bearer_auth(token)
        .json(&json!({"account_id":account_id,"owner":owner}))
        .timeout(STATUS_TIMEOUT)
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("原任务登记暂不可核对".into()))?
        .error_for_status()
        .map_err(|_| AppError::ServiceUnavailable("原任务登记核对失败".into()))?;
    let value: Value = response
        .json()
        .await
        .map_err(|_| AppError::ServiceUnavailable("原任务登记格式无效".into()))?;
    Ok(value["admitted"] == true)
}

/// 核对原控制请求仍被调度器实际持有，用于完成维护前开始的有限事务。
/// @param admission_id 私有活动身份。
/// @return 原活动实际存在时为 true。
pub async fn update_control_admitted(admission_id: &str) -> Result<bool, AppError> {
    let (base, token, client) = config()?;
    let response = client
        .post(format!(
            "{base}/internal/v3/system-updates/admitted-control"
        ))
        .bearer_auth(token)
        .json(&json!({"admission_id":admission_id}))
        .timeout(STATUS_TIMEOUT)
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("原控制活动暂不可核对".into()))?
        .error_for_status()
        .map_err(|_| AppError::ServiceUnavailable("原控制活动核对失败".into()))?;
    let value: Value = response
        .json()
        .await
        .map_err(|_| AppError::ServiceUnavailable("原控制活动格式无效".into()))?;
    Ok(value["admitted"] == true)
}
/// 只共享连接池，认证材料始终在单次请求上设置，不进入默认头或缓存。
static MANAGEMENT_CLIENT: LazyLock<Result<Client, ReqwestError>> = LazyLock::new(|| {
    Client::builder()
        .no_proxy()
        .redirect(Policy::none())
        .connect_timeout(SESSION_TIMEOUT)
        .build()
});

static AGY_INGRESS_WRITERS: Semaphore = Semaphore::const_new(2);

/// 独立发布已脱敏入口，缺口仅记录诊断。@param account_id 已确认账号。@param attempt_id 实际尝试。@param generation 原环境代次。@param ingress 有界脱敏预览。@return 无。
pub(crate) fn publish_agy_ingress(
    account_id: i64,
    attempt_id: &str,
    generation: u64,
    ingress: Value,
) {
    let Ok(permit) = AGY_INGRESS_WRITERS.try_acquire() else {
        return;
    };
    let Ok((base, token, client)) = config() else {
        return;
    };
    let path = format!("{base}/internal/v3/agy-ingress/{account_id}/{attempt_id}");
    tokio::spawn(async move {
        let _permit = permit;
        let result = client
            .post(path)
            .bearer_auth(token)
            .timeout(Duration::from_millis(250))
            .json(&json!({"environment_generation":generation,"ingress":ingress}))
            .send()
            .await;
        if !result.is_ok_and(|response| response.status().is_success()) {
            tracing::warn!("AGY入站采集不可用");
        }
    });
}

/// 配置事务持有门禁时收口对应账号实例，阻止已解析的旧请求跨过修改。
/// @param account_id 修改的账号 ID。
/// @param lease 当前配置事务的门禁证明。
/// @return 空闲实例已停止；忙或未知时拒绝修改。
pub async fn quiesce(account_id: i64, lease: &RuntimeLease) -> Result<(), AppError> {
    let (base, token, client) = config()?;
    let response = client
        .post(format!("{base}/internal/v3/quiesce/{account_id}"))
        .bearer_auth(token)
        .json(&serde_json::json!({"owner": lease.owner, "generation": lease.generation}))
        .timeout(Duration::from_secs(20))
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("account maintenance unavailable".into()))?;
    if !response.status().is_success() {
        return Err(AppError::BadRequest(
            "account runtime is busy or requires reconciliation".into(),
        ));
    }
    Ok(())
}

/// 只读聚合任务账号及登录草稿的代理引用。
/// @return 内部摘要；未配置运行时的独立网关返回空引用。
pub async fn proxy_references() -> Result<Value, AppError> {
    if std::env::var("V3_RUNTIME_URL")
        .unwrap_or_default()
        .is_empty()
    {
        return Ok(json!({"references": [], "complete": true}));
    }
    let (base, token, client) = config()?;
    let response = client
        .get(format!("{base}/internal/v3/proxy-references"))
        .bearer_auth(token)
        .timeout(STATUS_TIMEOUT)
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("任务代理引用暂不可核对".into()))?
        .error_for_status()
        .map_err(|_| AppError::ServiceUnavailable("任务代理引用核对失败".into()))?;
    response
        .json()
        .await
        .map_err(|_| AppError::ServiceUnavailable("任务代理引用格式无效".into()))
}

/// 通过内部证明更新空闲任务账号或草稿，忙碌状态交回持久队列重试。
/// @param target 固定身份。@param source 原连接摘要。@param destination 新私有连接。@return 同步状态及可能的新网关身份。
pub async fn synchronize_proxy(
    target: &ProxySyncTarget,
    source: &str,
    destination: &str,
) -> Result<Value, AppError> {
    let (base, token, client) = config()?;
    client
        .post(format!("{base}/internal/v3/proxy-sync"))
        .bearer_auth(token)
        .json(&json!({"target":target,"source":source,"destination":destination}))
        .timeout(Duration::from_secs(20))
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("线路关联同步待重试".into()))?
        .error_for_status()
        .map_err(|_| AppError::ServiceUnavailable("线路关联同步待重试".into()))?
        .json()
        .await
        .map_err(|_| AppError::ServiceUnavailable("线路同步回执无效".into()))
}

fn config() -> Result<(String, String, reqwest::Client), AppError> {
    let base = std::env::var("V3_RUNTIME_URL").unwrap_or_default();
    let token = std::env::var("V3_INTERNAL_TOKEN").unwrap_or_default();
    if base.is_empty() || token.len() < 32 {
        return Err(AppError::ServiceUnavailable(
            "v3 management is not configured".into(),
        ));
    }
    let client = MANAGEMENT_CLIENT
        .as_ref()
        .map_err(|_| AppError::ServiceUnavailable("v3 management unavailable".into()))?
        .clone();
    Ok((base.trim_end_matches('/').into(), token, client))
}

/// 调用受信管理侧的 AGY 原生适配。@param action 固定操作名。@param input 私有请求。@return 有界原生结果或脱敏错误。
pub async fn agy_request(action: &str, input: &Value) -> Result<Value, AppError> {
    if ![
        "start", "exchange", "cancel", "verify", "refresh", "recover", "prepare", "retire",
    ]
    .contains(&action)
    {
        return Err(AppError::BadRequest("AGY 管理操作无效".into()));
    }
    let (base, token, client) = config()?;
    let response = client
        .post(format!("{base}/internal/v3/agy-auth/{action}"))
        .bearer_auth(token)
        .json(input)
        .timeout(Duration::from_secs(90))
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("AGY 管理结果待核对".into()))?;
    if !response.status().is_success() {
        return Err(AppError::ServiceUnavailable(
            "AGY 原生授权或凭据操作未完成，请查询原会话".into(),
        ));
    }
    if response
        .content_length()
        .is_some_and(|length| length > 2 * 1024 * 1024)
    {
        return Err(AppError::ServiceUnavailable("AGY 管理响应超限".into()));
    }
    let mut response = response;
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| AppError::ServiceUnavailable("AGY 管理响应未完整接收".into()))?
    {
        if bytes.len() + chunk.len() > 2 * 1024 * 1024 {
            return Err(AppError::ServiceUnavailable("AGY 管理响应超限".into()));
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes)
        .map_err(|_| AppError::ServiceUnavailable("AGY 管理响应格式无效".into()))
}

fn cookie(headers: &HeaderMap) -> &str {
    headers
        .get(header::COOKIE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
}

fn check_origin(headers: &HeaderMap) -> Result<(), AppError> {
    if let Some(origin) = headers.get(header::ORIGIN) {
        let origin = origin
            .to_str()
            .ok()
            .and_then(|value| reqwest::Url::parse(value).ok())
            .ok_or(AppError::Unauthorized)?;
        let host = headers
            .get(header::HOST)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| reqwest::Url::parse(&format!("{}://{value}", origin.scheme())).ok())
            .ok_or(AppError::Unauthorized)?;
        if origin.origin() != host.origin() {
            return Err(AppError::Unauthorized);
        }
    }
    Ok(())
}

async fn authenticated(headers: &HeaderMap) -> Result<(), AppError> {
    let (base, token, client) = config()?;
    check_origin(headers)?;
    let response = client
        .get(format!("{base}/internal/v3/session/verify"))
        .bearer_auth(token)
        .header(header::COOKIE, cookie(headers))
        .timeout(SESSION_TIMEOUT)
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("v3 session unavailable".into()))?;
    if !response.status().is_success() {
        return Err(AppError::Unauthorized);
    }
    // 校验端只返回小型 {ok:true}；读完响应体后，认证连接才能归还共享池复用。
    response
        .bytes()
        .await
        .map_err(|_| AppError::ServiceUnavailable("v3 session unavailable".into()))?;
    Ok(())
}

fn response(upstream: reqwest::Response) -> Response {
    let status = upstream.status();
    let headers = upstream.headers().clone();
    let mut output = Response::new(Body::from_stream(upstream.bytes_stream()));
    *output.status_mut() = status;
    *output.headers_mut() = headers;
    for key in ["connection", "transfer-encoding", "upgrade", "keep-alive"] {
        output.headers_mut().remove(key);
    }
    output
}

/// 使用服务鉴权读取指定尝试的组装快照。
/// @param account_id 已由诊断记录确认的账号。
/// @param attempt_id 已由诊断记录确认的尝试 UUID。
/// @return 有界 JSON 内容；缺失和读取失败保持明确状态。
pub async fn native_capture(
    account_id: i64,
    attempt_id: &str,
) -> Result<serde_json::Value, AppError> {
    read_native_capture(account_id, attempt_id, false).await
}

/// 按持久平台读取AGY快照。@param account_id 已确认账号。@param attempt_id 已确认尝试。@return 有界快照。
pub async fn agy_capture(account_id: i64, attempt_id: &str) -> Result<Value, AppError> {
    read_native_capture(account_id, attempt_id, true).await
}

async fn read_native_capture(
    account_id: i64,
    attempt_id: &str,
    agy: bool,
) -> Result<Value, AppError> {
    let (base, token, client) = config()?;
    let mut response = client
        .get(format!(
            "{base}/internal/v3/native-captures/{account_id}/{attempt_id}{}",
            if agy { "?platform=antigravity" } else { "" }
        ))
        .bearer_auth(token)
        .timeout(STATUS_TIMEOUT)
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("采集服务读取失败".into()))?;
    if response.status() == reqwest::StatusCode::NOT_FOUND {
        return Ok(
            serde_json::json!({"state":"missing", "message":"采集文件缺失、尚未生成或已清理"}),
        );
    }
    if response.status() == reqwest::StatusCode::GONE {
        return Ok(serde_json::json!({"state":"expired", "message":"采集内容已超过七天保留期"}));
    }
    if !response.status().is_success() {
        return Err(AppError::ServiceUnavailable("采集文件读取失败".into()));
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| AppError::ServiceUnavailable("采集文件读取失败".into()))?
    {
        if bytes.len() + chunk.len() > 6 * 1024 * 1024 {
            return Err(AppError::ServiceUnavailable("采集文件超出读取上限".into()));
        }
        bytes.extend_from_slice(&chunk);
    }
    let snapshot: serde_json::Value = serde_json::from_slice(&bytes)
        .map_err(|_| AppError::ServiceUnavailable("采集文件格式无效".into()))?;
    if snapshot["account_id"] != account_id
        || snapshot["attempt_id"] != attempt_id
        || !(if agy {
            snapshot["stage"] == "agy_prepared"
        } else {
            matches!(
                snapshot["stage"].as_str(),
                Some("cc_prepared" | "ingress_rejected")
            )
        })
    {
        return Err(AppError::ServiceUnavailable("采集文件归属无效".into()));
    }
    Ok(serde_json::json!({"state":"saved", "snapshot":snapshot}))
}

/// 已经通过 admin_auth 的管理员换取独立 v3 浏览器会话。
/// @return HttpOnly cookie；响应不包含管理密码或服务秘密。
pub async fn grant_session() -> Result<Response, AppError> {
    let (base, token, client) = config()?;
    let upstream = client
        .post(format!("{base}/internal/v3/session"))
        .bearer_auth(token)
        .timeout(SESSION_TIMEOUT)
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("v3 session unavailable".into()))?;
    Ok(response(upstream))
}

/// 统一退出时撤销当前 v3 会话；未启用 v3 的旧部署保持兼容。
/// @param headers 含浏览器 Cookie 的管理请求头。
/// @return 撤销结果与清除 Cookie；服务失败时不假报退出成功。
pub async fn revoke_session(headers: HeaderMap) -> Result<Response, AppError> {
    if std::env::var("V3_RUNTIME_URL")
        .unwrap_or_default()
        .is_empty()
    {
        return Ok(Json(serde_json::json!({"ok": true})).into_response());
    }
    check_origin(&headers)?;
    let (base, token, client) = config()?;
    let upstream = client
        .post(format!("{base}/api/auth/logout"))
        .bearer_auth(token)
        .header(header::COOKIE, cookie(&headers))
        .timeout(Duration::from_secs(5))
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("v3 logout unavailable".into()))?;
    if !upstream.status().is_success() {
        return Err(AppError::ServiceUnavailable("v3 logout unavailable".into()));
    }
    Ok(response(upstream))
}

fn browser_path_allowed(method: &Method, path: &str) -> bool {
    // URL 库会规整点段和编码；先拒绝这些形式，防止白名单校验后跳入内部路径。
    if path.contains(['%', '\\']) || path.split('/').any(|part| part == "." || part == "..") {
        return false;
    }
    if matches!(*method, Method::GET | Method::HEAD)
        && matches!(
            path,
            "" | "/"
                | "/index.html"
                | "/app.js"
                | "/environments.js"
                | "/environments.css"
                | "/projects.js"
                | "/style.css"
                | "/ui-foundation.css"
                | "/console.css"
                | "/approved-design.css"
                | "/work-design.css"
                | "/environment-design.css"
                | "/capture-workspace.css"
                | "/pagination.css"
                | "/approved-icons.svg"
                | "/ui-controls.js"
                | "/fonts/inter-variable.woff2"
                | "/fonts/jetbrains-mono-variable.woff2"
                | "/vendor/xterm.js"
                | "/vendor/xterm.css"
                | "/vendor/xterm-addon-fit.js"
        )
    {
        return true;
    }
    if path == "/api/auth/me" {
        return *method == Method::GET;
    }
    if path == "/api/auth/logout" {
        return *method == Method::POST;
    }
    let Some(api_path) = path.strip_prefix("/api/") else {
        return false;
    };
    if let Some(account) = api_path.strip_prefix("accounts/") {
        let mut parts = account.split('/');
        let id = parts.next().unwrap_or_default();
        let resource = parts.next();
        if matches!(resource, Some("node" | "node-migrations")) {
            if id.is_empty()
                || !id.bytes().all(|value| value.is_ascii_digit())
                || !id.parse::<i64>().is_ok_and(|value| value > 0)
            {
                return false;
            }
            if resource == Some("node") {
                return parts.next().is_none() && matches!(*method, Method::GET | Method::PUT);
            }
            let Some(operation) = parts.next() else {
                return matches!(*method, Method::GET | Method::POST);
            };
            if operation.len() != 32
                || !operation
                    .bytes()
                    .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
            {
                return false;
            }
            return match parts.next() {
                None => *method == Method::GET,
                Some("resume" | "cancel") => *method == Method::POST && parts.next().is_none(),
                _ => false,
            };
        }
    }
    if api_path == "nodes" {
        return matches!(*method, Method::GET | Method::POST);
    }
    if matches!(api_path, "nodes/host-keys" | "nodes/synchronize") {
        return *method == Method::POST;
    }
    if let Some(node) = api_path.strip_prefix("nodes/") {
        let mut parts = node.split('/');
        let id = parts.next().unwrap_or_default();
        if id.is_empty() || id.len() > 19 || !id.bytes().all(|value| value.is_ascii_digit()) {
            return false;
        }
        let action = parts.next();
        if parts.next().is_some() {
            return false;
        }
        return match action {
            None => *method == Method::DELETE,
            Some("check" | "prepare") => *method == Method::POST,
            Some("enabled") => *method == Method::PUT,
            _ => false,
        };
    }
    if let Some(environment) = api_path
        .strip_prefix("environments/")
        .and_then(|value| value.strip_suffix("/content-capture"))
    {
        return matches!(*method, Method::GET | Method::POST)
            && environment.len() == 32
            && environment.bytes().all(|value| value.is_ascii_hexdigit());
    }
    if let Some(rest) = api_path.strip_prefix("system-updates/") {
        return match *method {
            Method::GET => {
                matches!(rest, "status" | "releases" | "version")
                    || rest
                        .strip_prefix("operations/")
                        .is_some_and(|value| Uuid::parse_str(value).is_ok())
            }
            Method::POST => {
                matches!(rest, "check" | "prepare" | "install" | "rollback")
                    || rest.strip_prefix("operations/").is_some_and(|value| {
                        value.split_once('/').is_some_and(|(id, action)| {
                            Uuid::parse_str(id).is_ok() && matches!(action, "cancel" | "recover")
                        })
                    })
            }
            _ => false,
        };
    }
    matches!(
        *method,
        Method::GET | Method::POST | Method::PUT | Method::DELETE
    ) && matches!(
        api_path.split('/').next().unwrap_or_default(),
        "accounts"
            | "cc2api"
            | "settings"
            | "topics"
            | "tasks"
            | "task-batches"
            | "captures"
            | "runs"
            | "runs-stream"
            | "run-continue"
            | "terminal-ticket"
            | "environments"
            | "project-catalog"
            | "project-iteration-batches"
            | "project-instances"
            | "project-step-attempts"
            | "project-iterations-stream"
            | "projects"
    )
}

/// 只有明确有限的 JSON 状态读取使用总期限，不能误截断 SSE 或后台长操作。
/// @param method 已通过白名单的 HTTP 方法。
/// @param path 不含查询字符串的管理路径。
/// @return 普通状态读取的期限，其它请求沿用既有生命周期。
fn status_timeout(method: &Method, path: &str) -> Option<Duration> {
    let account_node_status = path.strip_prefix("/api/accounts/").is_some_and(|value| {
        matches!(value.split('/').nth(1), Some("node" | "node-migrations"))
            && browser_path_allowed(method, path)
    });
    if *method == Method::GET && (path.starts_with("/api/system-updates/") || account_node_status) {
        return Some(STATUS_TIMEOUT);
    }
    (*method == Method::GET
        && matches!(
            path,
            "/api/projects" | "/api/projects/catalog" | "/api/accounts/warmup/pi" | "/api/accounts"
        ))
    .then_some(STATUS_TIMEOUT)
}

/// 把目录选择转换为运行时既有登录字段；私有连接仅存在于服务端请求中。
/// @param body 用户的登录配置。@param record 本次锁内读取的目录记录。
/// @return 经过版本校验的运行时载荷。
fn translate_login_proxy(mut body: Value, record: Option<&ProxyRecord>) -> Result<Value, AppError> {
    let object = body
        .as_object_mut()
        .ok_or_else(|| AppError::BadRequest("登录配置无效".into()))?;
    if object.keys().any(|key| key.starts_with("upstream_")) {
        return Err(AppError::BadRequest(
            "代理目录选择与手动连接不能同时提交".into(),
        ));
    }
    match record {
        Some(proxy) => {
            if object.get("proxy_id").and_then(Value::as_str) != Some(proxy.id.as_str())
                || object.get("proxy_revision").and_then(Value::as_str)
                    != Some(proxy.revision.as_str())
            {
                return Err(AppError::BadRequest("所选代理已变化，请重新选择".into()));
            }
            let connection = &proxy.connection;
            object.insert("upstream_proxy_scheme".into(), json!(connection.protocol));
            object.insert("upstream_socks5_host".into(), json!(connection.host));
            object.insert("upstream_socks5_port".into(), json!(connection.port));
            object.insert("upstream_socks5_user".into(), json!(connection.username));
            object.insert("upstream_socks5_pass".into(), json!(connection.password));
        }
        None => {
            if object.get("proxy_id") != Some(&Value::Null)
                || object
                    .get("proxy_revision")
                    .is_some_and(|value| !value.is_null())
            {
                return Err(AppError::BadRequest("请选择有效代理或直连".into()));
            }
        }
    }
    object.remove("proxy_id");
    object.remove("proxy_revision");
    Ok(body)
}

async fn http_bridge(
    State(state): State<AppState>,
    OriginalUri(uri): OriginalUri,
    method: Method,
    headers: HeaderMap,
    body: Bytes,
) -> Result<Response, AppError> {
    let browser_path = uri
        .path()
        .strip_prefix("/runtime")
        .ok_or(AppError::NotFound)?;
    if !browser_path_allowed(&method, browser_path) {
        return Err(AppError::NotFound);
    }
    authenticated(&headers).await?;
    if browser_path.ends_with("/proxy-selection") {
        let id = task_proxy::identity(browser_path).ok_or(AppError::NotFound)?;
        // 用户关闭页面后已经受理的保存继续持有目录锁，直到受控事务收口。
        return tokio::spawn(task_proxy::selection(state, id, method, body, headers))
            .await
            .map_err(|_| AppError::ServiceUnavailable("代理选择操作中断，请重新读取".into()))?;
    }
    let project_accounts = method == Method::GET && browser_path == "/api/accounts";
    let login = if method == Method::POST && browser_path == "/api/accounts/login/start" {
        Some(
            serde_json::from_slice::<Value>(&body)
                .map_err(|_| AppError::BadRequest("登录配置无效".into()))?,
        )
    } else {
        None
    };
    let selected = login
        .as_ref()
        .is_some_and(|value| value.get("proxy_id").is_some());
    // 目录选择与删改共用锁，直到启动回执返回后，草稿引用才已由运行时登记。
    let _proxy_guard = if selected {
        Some(state.proxy_svc.mutations.lock().await)
    } else {
        None
    };
    let body = if selected {
        let value = login.unwrap();
        let record = match value.get("proxy_id") {
            Some(Value::String(id)) => Some(state.proxy_svc.store.get(id).await?),
            Some(Value::Null) => None,
            _ => return Err(AppError::BadRequest("请选择有效代理或直连".into())),
        };
        Bytes::from(
            serde_json::to_vec(&translate_login_proxy(value, record.as_ref())?)
                .map_err(|_| AppError::BadRequest("登录配置无效".into()))?,
        )
    } else {
        body
    };
    let (base, token, client) = config()?;
    let timeout = status_timeout(&method, browser_path);
    let path = uri
        .path_and_query()
        .map(|value| value.as_str())
        .unwrap_or("/runtime/")
        .strip_prefix("/runtime")
        .ok_or(AppError::NotFound)?;
    let mut request = client
        .request(
            method,
            format!("{base}{}", if path.is_empty() { "/" } else { path }),
        )
        .bearer_auth(token)
        .header(header::COOKIE, cookie(&headers));
    for key in [header::CONTENT_TYPE, header::ACCEPT, header::CACHE_CONTROL] {
        if let Some(value) = headers.get(&key) {
            request = request.header(key, value);
        }
    }
    if let Some(timeout) = timeout {
        request = request.timeout(timeout);
    }
    let upstream = request
        .body(body)
        .send()
        .await
        .map_err(|_| AppError::ServiceUnavailable("v3 management request failed".into()))?;
    if selected {
        // 下游校验错误可能回显请求内容，目录账密一律不随原始响应返回浏览器。
        if !upstream.status().is_success() {
            if upstream.status().is_server_error() {
                return Err(AppError::ServiceUnavailable(
                    "登录准备尚未确认，请刷新草稿并恢复检查".into(),
                ));
            }
            return Err(AppError::BadRequest(
                "登录启动失败，请核对账号状态和所选代理后重试".into(),
            ));
        }
        let value: Value = upstream
            .json()
            .await
            .map_err(|_| AppError::ServiceUnavailable("登录启动回执无效".into()))?;
        let mut output = json!({});
        for key in [
            "session_id",
            "ws_path",
            "has_sidecar",
            "name",
            "reconnectable",
            "cc2api_account_id",
            "environment_id",
            "draft_generation",
            "node_id",
            "node_name",
        ] {
            if let Some(item) = value.get(key) {
                output[key] = item.clone();
            }
        }
        return Ok(Json(output).into_response());
    }
    if project_accounts {
        return task_proxy::accounts(&state, upstream).await;
    }
    Ok(response(upstream))
}

async fn ws_bridge(
    OriginalUri(uri): OriginalUri,
    headers: HeaderMap,
    upgrade: WebSocketUpgrade,
) -> Result<Response, AppError> {
    authenticated(&headers).await?;
    let (base, token, _) = config()?;
    let path = uri
        .path_and_query()
        .unwrap()
        .as_str()
        .strip_prefix("/runtime")
        .unwrap()
        .to_owned();
    let upstream = base.replacen("http", "ws", 1) + &path;
    let cookie = cookie(&headers).to_owned();
    Ok(upgrade.on_upgrade(move |socket| websocket_bridge(socket, upstream, base, token, cookie)))
}

async fn websocket_bridge(
    socket: WebSocket,
    url: String,
    base: String,
    token: String,
    cookie: String,
) {
    let session_token = token.clone();
    let session_cookie = cookie.clone();
    let Ok(mut request) = url.into_client_request() else {
        return;
    };
    let Ok(authorization) = format!("Bearer {token}").parse() else {
        return;
    };
    let Ok(cookie) = cookie.parse() else {
        return;
    };
    request
        .headers_mut()
        .insert(header::AUTHORIZATION, authorization);
    request.headers_mut().insert(header::COOKIE, cookie);
    let Ok((upstream, _)) = connect_async(request).await else {
        return;
    };
    let (mut browser_out, mut browser_in) = socket.split();
    let (mut upstream_out, mut upstream_in) = upstream.split();
    let to_upstream = async {
        while let Some(Ok(message)) = browser_in.next().await {
            let message = match message {
                Message::Text(value) => UpstreamMessage::Text(value),
                Message::Binary(value) => UpstreamMessage::Binary(value),
                Message::Ping(value) => UpstreamMessage::Ping(value),
                Message::Pong(value) => UpstreamMessage::Pong(value),
                Message::Close(_) => break,
            };
            if upstream_out.send(message).await.is_err() {
                break;
            }
        }
    };
    let to_browser = async {
        while let Some(Ok(message)) = upstream_in.next().await {
            let message = match message {
                UpstreamMessage::Text(value) => Message::Text(value),
                UpstreamMessage::Binary(value) => Message::Binary(value),
                UpstreamMessage::Ping(value) => Message::Ping(value),
                UpstreamMessage::Pong(value) => Message::Pong(value),
                _ => break,
            };
            if browser_out.send(message).await.is_err() {
                break;
            }
        }
    };
    let session_valid = async {
        let client = reqwest::Client::builder()
            .no_proxy()
            .redirect(Policy::none())
            .build();
        let Ok(client) = client else {
            return;
        };
        loop {
            tokio::time::sleep(Duration::from_secs(3)).await;
            let result = client
                .get(format!("{base}/internal/v3/session/verify"))
                .bearer_auth(&session_token)
                .header(header::COOKIE, &session_cookie)
                .timeout(Duration::from_secs(5))
                .send()
                .await;
            if !matches!(result, Ok(response) if response.status().is_success()) {
                return;
            }
        }
    };
    tokio::select! { _ = to_upstream => (), _ = to_browser => (), _ = session_valid => () }
}

/// 构建 HTTP/SSE/WS 管理路由，使用独立浏览器会话验证。
/// @return 可合入主路由的 v3 管理桥。
pub fn routes() -> Router<AppState> {
    Router::new()
        .route("/runtime", any(http_bridge))
        .route("/runtime/", any(http_bridge))
        .route("/runtime/*rest", any(http_bridge))
        .route("/runtime/api/accounts/login/ws/:sid", get(ws_bridge))
        .route("/runtime/api/run-continue/ws/:sid", get(ws_bridge))
}

#[cfg(test)]
mod tests {
    use super::{MANAGEMENT_CLIENT, STATUS_TIMEOUT, browser_path_allowed, status_timeout};
    use axum::http::Method;
    use std::time::Duration;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    #[test]
    fn node_management_paths_require_exact_actions() {
        for (method, path) in [
            (Method::GET, "/api/nodes"),
            (Method::POST, "/api/nodes"),
            (Method::POST, "/api/nodes/host-keys"),
            (Method::POST, "/api/nodes/synchronize"),
            (Method::POST, "/api/nodes/2/check"),
            (Method::POST, "/api/nodes/2/prepare"),
            (Method::PUT, "/api/nodes/2/enabled"),
            (Method::DELETE, "/api/nodes/2"),
        ] {
            assert!(browser_path_allowed(&method, path), "{path}");
        }
        for (method, path) in [
            (Method::GET, "/api/nodes/2/private-key"),
            (Method::POST, "/api/nodes/2/shell"),
            (Method::GET, "/api/nodes/host-keys"),
            (Method::GET, "/api/nodes/synchronize"),
            (Method::POST, "/api/nodes/2/check/extra"),
            (Method::POST, "/api/nodes/../check"),
            (Method::POST, "/api/nodes/2%2fcheck"),
        ] {
            assert!(!browser_path_allowed(&method, path), "{path}");
        }
    }
    use tokio::net::TcpListener;
    use tokio::time::timeout;

    /// 平台版本只开放精确只读入口，沿既有管理会话验证与有限读取期限。
    #[test]
    fn platform_version_route_is_read_only_and_exact() {
        let path = "/api/system-updates/version";
        assert!(browser_path_allowed(&Method::GET, path));
        assert_eq!(status_timeout(&Method::GET, path), Some(STATUS_TIMEOUT));
        for method in [Method::POST, Method::PUT, Method::DELETE, Method::HEAD] {
            assert!(!browser_path_allowed(&method, path));
        }
        for invalid in [
            "/api/system-updates/version/",
            "/api/system-updates/version/private",
            "/api/system-updates/versions",
        ] {
            assert!(!browser_path_allowed(&Method::GET, invalid));
        }
    }

    /// 目录代理在服务端展开，冲突和手动混用均在发送前拒绝。
    #[test]
    fn login_directory_translation_preserves_private_boundary() {
        use crate::model::proxy::ProxyConnection;
        use crate::store::proxy_store::ProxyRecord;
        use serde_json::json;
        let proxy = ProxyRecord {
            id: "route-1".into(),
            name: "线路".into(),
            connection: ProxyConnection::parse(
                "socks5://private-user:private-password@proxy.example.test:1080",
            )
            .unwrap(),
            expires_at: None,
            revision: "revision-1".into(),
            observation: None,
            checked_at: None,
            status: "unknown".into(),
            created_at: String::new(),
            updated_at: String::new(),
        };
        let value=super::translate_login_proxy(json!({"name":"test","force_reauth":false,"node_id":2,"proxy_id":"route-1","proxy_revision":"revision-1"}),Some(&proxy)).unwrap();
        assert_eq!(value["node_id"], 2);
        assert_eq!(value["upstream_socks5_pass"], "private-password");
        assert_eq!(value["upstream_socks5_port"], 1080);
        assert!(value.get("proxy_id").is_none());
        for body in [
            json!({"proxy_id":"route-1","proxy_revision":"stale"}),
            json!({"proxy_id":"route-1","proxy_revision":"revision-1","upstream_socks5_host":"other"}),
            json!({"proxy_id":"other","proxy_revision":"revision-1"}),
        ] {
            assert!(super::translate_login_proxy(body, Some(&proxy)).is_err());
        }
        assert_eq!(
            super::translate_login_proxy(json!({"name":"direct","proxy_id":null}), None).unwrap(),
            json!({"name":"direct"})
        );
        assert!(super::translate_login_proxy(json!({"proxy_id":"missing"}), None).is_err());
    }

    /// 有限状态 GET 设置期限，流式读取、长写操作及相似路径保持原生命周期。
    #[test]
    fn management_status_timeouts_preserve_streams_and_long_operations() {
        for path in [
            "/api/projects",
            "/api/projects/catalog",
            "/api/accounts/warmup/pi",
            "/api/accounts",
            "/api/accounts/1/node",
            "/api/accounts/1/node-migrations",
            "/api/accounts/1/node-migrations/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ] {
            assert_eq!(status_timeout(&Method::GET, path), Some(STATUS_TIMEOUT));
            assert_eq!(status_timeout(&Method::POST, path), None);
        }
        for path in [
            "/api/runs-stream",
            "/api/project-iterations-stream",
            "/api/projects/stream",
            "/api/projects/agents/1/events",
            "/api/projects/catalogue",
            "/api/accounts/1/node-migrations/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/resume",
        ] {
            assert_eq!(status_timeout(&Method::GET, path), None);
        }
    }

    /// 两次借用的管理客户端复用同一 TCP 连接，避免每次认证和转发重新建池。
    #[tokio::test]
    async fn management_client_reuses_connection_without_default_credentials() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            for _ in 0..2 {
                let mut request = Vec::new();
                while !request.ends_with(b"\r\n\r\n") {
                    let mut byte = [0];
                    assert_eq!(socket.read(&mut byte).await.unwrap(), 1);
                    request.push(byte[0]);
                    assert!(request.len() < 4096);
                }
                let headers = String::from_utf8(request).unwrap().to_ascii_lowercase();
                assert!(!headers.contains("authorization:") && !headers.contains("cookie:"));
                socket
                    .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
                    .await
                    .unwrap();
            }
        });
        for _ in 0..2 {
            let client = MANAGEMENT_CLIENT.as_ref().unwrap().clone();
            let response = client
                .get(format!("http://{address}/status"))
                .timeout(Duration::from_secs(2))
                .send()
                .await
                .unwrap();
            assert_eq!(response.text().await.unwrap(), "ok");
        }
        timeout(Duration::from_secs(2), server)
            .await
            .unwrap()
            .unwrap();
    }

    #[test]
    fn management_bridge_rejects_internal_and_encoded_paths() {
        for path in [
            "/internal/v3/session",
            "/internal/v3/transport/1",
            "/api/../internal/v3/session",
            "/api/%2e%2e/internal/v3/session",
            "/api/%252e%252e/internal/v3/session",
            "/api\\..\\internal/v3/session",
            "/api/auth/login",
            "/unknown",
        ] {
            assert!(!browser_path_allowed(&Method::GET, path), "{path}");
            assert!(!browser_path_allowed(&Method::POST, path), "{path}");
        }
        assert!(browser_path_allowed(&Method::GET, "/api/runs-stream"));
        assert!(browser_path_allowed(
            &Method::POST,
            "/api/accounts/login/start"
        ));
        assert!(browser_path_allowed(&Method::GET, "/vendor/xterm.js"));
        assert!(browser_path_allowed(&Method::GET, "/projects.js"));
        assert!(!browser_path_allowed(&Method::POST, "/projects.js"));
        assert!(!browser_path_allowed(&Method::POST, "/app.js"));
    }

    /// 节点归属与人工迁移只开放精确管理动作，操作ID及层级保持规范。
    #[test]
    fn account_node_migration_routes_require_exact_scope_and_method() {
        let operation = "a".repeat(32);
        let path = format!("/api/accounts/1/node-migrations/{operation}");
        assert!(browser_path_allowed(&Method::GET, "/api/accounts/1/node"));
        assert!(browser_path_allowed(&Method::PUT, "/api/accounts/1/node"));
        assert!(browser_path_allowed(
            &Method::POST,
            "/api/accounts/1/node-migrations"
        ));
        assert!(browser_path_allowed(&Method::GET, &path));
        assert!(browser_path_allowed(
            &Method::POST,
            &format!("{path}/resume")
        ));
        assert!(browser_path_allowed(
            &Method::POST,
            &format!("{path}/cancel")
        ));
        for (method, invalid) in [
            (Method::POST, "/api/accounts/1/node".to_owned()),
            (Method::DELETE, "/api/accounts/1/node-migrations".to_owned()),
            (Method::POST, path.clone()),
            (Method::GET, format!("{path}/resume")),
            (Method::POST, format!("{path}/force")),
            (Method::POST, format!("{path}/cancel/extra")),
            (Method::GET, "/api/accounts/0/node".to_owned()),
            (
                Method::GET,
                "/api/accounts/9223372036854775808/node".to_owned(),
            ),
            (
                Method::GET,
                "/api/accounts/1/node-migrations/ABC".to_owned(),
            ),
        ] {
            assert!(!browser_path_allowed(&method, &invalid), "{invalid}");
        }
    }

    /// 新界面依赖的精确资源仅允许只读，不扩展为任意目录访问。
    #[test]
    fn design_assets_remain_available_through_runtime_bridge() {
        for path in [
            "/console.css",
            "/ui-foundation.css",
            "/approved-design.css",
            "/work-design.css",
            "/environment-design.css",
            "/capture-workspace.css",
            "/pagination.css",
            "/approved-icons.svg",
            "/ui-controls.js",
            "/fonts/inter-variable.woff2",
            "/fonts/jetbrains-mono-variable.woff2",
        ] {
            assert!(browser_path_allowed(&Method::GET, path), "{path}");
            assert!(browser_path_allowed(&Method::HEAD, path), "{path}");
            assert!(!browser_path_allowed(&Method::POST, path), "{path}");
        }
        for path in [
            "/fonts/private",
            "/fonts/../private",
            "/fonts/%2e%2e/private",
            "/unknown.css",
        ] {
            assert!(!browser_path_allowed(&Method::GET, path), "{path}");
        }
    }

    /// 采集开关只开放精确环境资源和读写方法。
    #[test]
    fn content_capture_bridge_is_scoped_to_one_environment() {
        let path = format!("/api/environments/{}/content-capture", "a".repeat(32));
        assert!(browser_path_allowed(&Method::GET, &path));
        assert!(browser_path_allowed(&Method::POST, &path));
        for method in [Method::PUT, Method::DELETE, Method::PATCH] {
            assert!(!browser_path_allowed(&method, &path));
        }
        for environment in ["short", "../internal", "invalid-environment-identifier-xx"] {
            assert!(!browser_path_allowed(
                &Method::POST,
                &format!("/api/environments/{environment}/content-capture")
            ));
        }
    }

    /// 环境页静态资源仅接受精确只读路径，拼写近似和写方法继续拒绝。
    /// @return 白名单与资源请求方式一致。
    #[test]
    fn environment_assets_are_exact_and_read_only() {
        for path in ["/environments.js", "/environments.css"] {
            assert!(browser_path_allowed(&Method::GET, path));
            assert!(browser_path_allowed(&Method::HEAD, path));
            for method in [Method::POST, Method::PUT, Method::PATCH, Method::DELETE] {
                assert!(!browser_path_allowed(&method, path));
            }
        }
        for path in [
            "/environment.js",
            "/environments.js/extra",
            "/nested/environments.css",
            "/%65nvironments.js",
            "/environments.css/../internal/v3/session",
        ] {
            assert!(!browser_path_allowed(&Method::GET, path));
        }
    }

    /// 项目模式仅增加管理资源，编码穿越和内部服务入口继续拒绝。
    #[test]
    fn project_iteration_resources_use_authenticated_management_bridge() {
        for path in [
            "/api/project-catalog",
            "/api/project-catalog/project-001",
            "/api/project-instances/1/usage",
            "/api/project-step-attempts/1/artifacts",
            "/api/project-iterations-stream",
            "/api/projects",
            "/api/projects/catalog",
            "/api/projects/agents/1/events",
            "/api/projects/stream?account_id=1",
        ] {
            assert!(browser_path_allowed(&Method::GET, path), "{path}");
        }
        assert!(browser_path_allowed(
            &Method::POST,
            "/api/project-iteration-batches/1/start"
        ));
        for path in [
            "/api/project-instances/../internal/v3/transport/1",
            "/api/project-instances/%2e%2e/internal/v3/session",
            "/internal/v3/project-catalog",
            "/api/projects/%2e%2e/internal/v3/session",
        ] {
            assert!(!browser_path_allowed(&Method::GET, path), "{path}");
        }
    }
}
