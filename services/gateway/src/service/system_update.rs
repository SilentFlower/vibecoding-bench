//! 部署级维护准入。流响应持有活动证明直到 EOF 或断连。

#[cfg(unix)]
use std::fs::OpenOptions;
#[cfg(unix)]
use std::io::Read;
#[cfg(unix)]
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::Path;
use std::pin::Pin;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, LazyLock, Mutex};
use std::task::{Context, Poll};

use axum::body::{Body, Bytes};
use axum::extract::Request;
use axum::http::{Method, StatusCode};
use axum::middleware::Next;
use axum::response::{IntoResponse, Response};
use axum::{Error as AxumError, Json};
use http_body::{Body as HttpBody, Frame, SizeHint};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use subtle::ConstantTimeEq;
use tokio::sync::watch;
use uuid::Uuid;

use crate::error::AppError;
use crate::service::runtime_bridge::{update_admitted, update_control_admitted};

static ACTIVITIES: LazyLock<Mutex<usize>> = LazyLock::new(|| Mutex::new(0));
static INFERENCE_CUTOVER: LazyLock<watch::Sender<Option<Uuid>>> =
    LazyLock::new(|| watch::channel(None).0);

/// 维护前接纳的推理和预热使用同一代关闭信号。
#[derive(Clone, Debug)]
pub(crate) struct InferenceCutover {
    epoch: watch::Receiver<Option<Uuid>>,
    interrupted: Arc<AtomicBool>,
}

impl InferenceCutover {
    /// 将同一请求的切换订阅与实际中断标记绑定。@param epoch 切换代次订阅。@return 请求信号。
    pub(super) fn new(epoch: watch::Receiver<Option<Uuid>>) -> Self {
        Self {
            epoch,
            interrupted: Arc::new(AtomicBool::new(false)),
        }
    }

    /// 在登记活动前订阅，避免错过关闭准入后发布的信号。@return 当前代的订阅。
    pub(crate) fn subscribe() -> Self {
        Self::new(INFERENCE_CUTOVER.subscribe())
    }

    /// 等待原请求之后发布的切换信号。@return 本次推理进入维护取消。
    pub(crate) async fn cancelled(&mut self) {
        let _ = self.epoch.changed().await;
    }

    /// 核对是否已发布切换信号。@return 本次推理应当停止时为真。
    pub(crate) fn is_cancelled(&self) -> bool {
        self.epoch.has_changed().unwrap_or(true)
    }

    /// HTTP 边界实际选中切换时记录原因，普通断连继续沿原诊断。@return 已进入维护中断。
    pub(super) async fn interrupt(&mut self) {
        self.cancelled().await;
        self.interrupted.store(true, Ordering::Release);
    }

    /// 读取当前请求是否由 HTTP 切换分支中断。@return 已由切换中断时为真。
    pub(crate) fn interrupted(&self) -> bool {
        self.interrupted.load(Ordering::Acquire)
    }
}

/// 由 root 更新服务原子发布的双方共用门禁。
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DeploymentGate {
    schema_version: u32,
    deployment: String,
    operation_id: Option<String>,
    epoch: String,
    phase: String,
    target_release: Option<String>,
    revision: String,
    created_at: String,
}

/// 一项真实在途活动的 RAII 证明。
pub struct UpdateActivity;

struct TrackedBody {
    inner: Body,
    activity: Option<UpdateActivity>,
    cutover: Option<Pin<Box<dyn Future<Output = ()> + Send>>>,
}

impl HttpBody for TrackedBody {
    type Data = Bytes;
    type Error = AxumError;

    fn poll_frame(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
    ) -> Poll<Option<Result<Frame<Bytes>, Self::Error>>> {
        let this = self.get_mut();
        if let Some(cutover) = this.cutover.as_mut()
            && cutover.as_mut().poll(cx).is_ready()
        {
            // 先丢弃上游流，允许原传输收尾，再归还网关活动证明。
            this.cutover = None;
            this.inner = Body::empty();
            this.activity.take();
            return Poll::Ready(Some(Err(AxumError::new(std::io::Error::other(
                "平台更新已中断推理流",
            )))));
        }
        let result = Pin::new(&mut this.inner).poll_frame(cx);
        if matches!(&result, Poll::Ready(None) | Poll::Ready(Some(Err(_)))) {
            this.activity.take();
        }
        result
    }

    fn is_end_stream(&self) -> bool {
        self.inner.is_end_stream()
    }
    fn size_hint(&self) -> SizeHint {
        self.inner.size_hint()
    }
}

impl Drop for UpdateActivity {
    fn drop(&mut self) {
        let mut active = ACTIVITIES.lock().unwrap_or_else(|error| error.into_inner());
        *active = active.saturating_sub(1);
    }
}

#[cfg(unix)]
/// 读取由宿主发布的私有更新记录。@param path 固定路径。@param limit 最大字节数。@return 校验后的记录。
pub(crate) fn read_update_record<T: serde::de::DeserializeOwned>(
    path: &Path,
    limit: u64,
) -> Result<T, AppError> {
    let error = || AppError::ServiceUnavailable("平台维护状态需要对账".into());
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)
        .map_err(|_| error())?;
    let info = file.metadata().map_err(|_| error())?;
    if !info.is_file()
        || info.len() > limit
        || info.mode() & 0o077 != 0
        || info.nlink() != 1
        || info.uid() != unsafe { libc::geteuid() }
    {
        return Err(error());
    }
    let mut raw = Vec::new();
    file.by_ref()
        .take(limit + 1)
        .read_to_end(&mut raw)
        .map_err(|_| error())?;
    if raw.len() as u64 > limit {
        return Err(error());
    }
    serde_json::from_slice(&raw).map_err(|_| error())
}

#[cfg(unix)]
fn read_gate(path: &Path, deployment: &str) -> Result<DeploymentGate, AppError> {
    let gate: DeploymentGate = read_update_record(path, 8192)?;
    if gate.schema_version != 1
        || deployment.is_empty()
        || gate.deployment != deployment
        || !matches!(gate.phase.as_str(), "idle" | "blocked")
        || Uuid::parse_str(&gate.epoch).is_err()
        || Uuid::parse_str(&gate.revision).is_err()
        || (gate.phase == "blocked"
            && gate
                .operation_id
                .as_ref()
                .is_none_or(|value| Uuid::parse_str(value).is_err()))
        || (gate.phase == "idle" && (gate.operation_id.is_some() || gate.target_release.is_some()))
    {
        return Err(AppError::ServiceUnavailable("平台维护状态需要对账".into()));
    }
    Ok(gate)
}

#[cfg(not(unix))]
fn read_gate(_path: &Path, _deployment: &str) -> Result<DeploymentGate, AppError> {
    Err(AppError::ServiceUnavailable(
        "当前平台未接入 Linux 系统更新底座".into(),
    ))
}

fn gate() -> Result<Option<DeploymentGate>, AppError> {
    let directory = std::env::var("V3_UPDATE_GATE_DIR").unwrap_or_default();
    if directory.is_empty() {
        return Ok(None);
    }
    read_gate(
        &Path::new(&directory).join("admission.json"),
        &std::env::var("V3_DEPLOYMENT_ID").unwrap_or_default(),
    )
    .map(Some)
}

/// 数据库初始化前核对底座维护记录，未知门禁禁止继续启动。
/// @return 已明确识别启用状态或门禁错误。
pub fn validate_startup() -> Result<(), AppError> {
    gate().map(|_| ())
}

/// 在同一锁内核验准入并登记活动，后台调用亦使用该入口。
/// @return 活动证明；维护中拒绝新工作。
pub fn admission() -> Result<UpdateActivity, AppError> {
    background_admission()?
        .ok_or_else(|| AppError::ServiceUnavailable("平台正在维护，请稍后重试".into()))
}

/// 在原活动锁内区分合法维护等待与门禁故障，后台等待不占用活动名额。
/// @return 开放时的活动证明、合法维护时的 None，或需要对账的门禁错误。
pub(crate) fn background_admission() -> Result<Option<UpdateActivity>, AppError> {
    let mut active = ACTIVITIES.lock().unwrap_or_else(|error| error.into_inner());
    if gate()?.is_some_and(|value| value.phase != "idle") {
        return Ok(None);
    }
    *active += 1;
    Ok(Some(UpdateActivity))
}

/// 允许原在途账号任务完成必要凭据解析，和 ACK 共用登记锁。
/// @param admitted 只读复核原账号仍持有活动或运行租约。
/// @return 被跟踪的有限续接活动。
pub fn continuation(admitted: impl FnOnce() -> bool) -> Result<UpdateActivity, AppError> {
    let mut active = ACTIVITIES.lock().unwrap_or_else(|error| error.into_inner());
    if gate()?.is_some_and(|value| value.phase != "idle") && !admitted() {
        return Err(AppError::ServiceUnavailable(
            "平台维护中，账号没有在途工作".into(),
        ));
    }
    *active += 1;
    Ok(UpdateActivity)
}

/// 登记有限内部认领后核对原运行作业，防止暂停时打断原 CLI 准备。
/// @param account_id 原账号。
/// @param owner 原作业来源。
/// @return 已跟踪且有实际登记的续接活动。
pub async fn cli_admission(account_id: i64, owner: &str) -> Result<UpdateActivity, AppError> {
    let (activity, blocked) = {
        let mut active = ACTIVITIES.lock().unwrap_or_else(|error| error.into_inner());
        let blocked = gate()?.is_some_and(|value| value.phase != "idle");
        *active += 1;
        (UpdateActivity, blocked)
    };
    if blocked && !update_admitted(account_id, owner).await? {
        return Err(AppError::ServiceUnavailable(
            "平台维护中，原任务登记已经失效".into(),
        ));
    }
    Ok(activity)
}

/// 在实际准入锁内返回 ACK 和活动计数，未知状态保持明确失败。
/// @return 当前门禁及进程活动。
pub fn snapshot() -> Result<Value, AppError> {
    let active = ACTIVITIES.lock().unwrap_or_else(|error| error.into_inner());
    let Some(gate) = gate()? else {
        return Ok(json!({"enabled":false,"phase":"idle","epoch":null,"active":*active}));
    };
    let mut value =
        serde_json::to_value(gate).map_err(|_| AppError::Internal("维护状态编码失败".into()))?;
    value["active"] = json!(*active);
    value["enabled"] = json!(true);
    value["inference_cutover"] = json!(true);
    Ok(value)
}

/// 在宿主已经封闭准入的同一代发布推理关闭信号。
/// @param operation 原维护操作。@param epoch 原维护代次。@return 同代接管证明。
pub(crate) fn cutover(operation: &str, epoch: &str) -> Result<Value, AppError> {
    let _active = ACTIVITIES.lock().unwrap_or_else(|error| error.into_inner());
    let current = gate()?.ok_or_else(|| AppError::BadRequest("未启用平台更新门禁".into()))?;
    if current.phase != "blocked"
        || current.operation_id.as_deref() != Some(operation)
        || current.epoch != epoch
    {
        return Err(AppError::BadRequest("更新操作或代次已经变化".into()));
    }
    let epoch_id =
        Uuid::parse_str(epoch).map_err(|_| AppError::BadRequest("更新代次无效".into()))?;
    INFERENCE_CUTOVER.send_if_modified(|active_epoch| {
        if *active_epoch == Some(epoch_id) {
            return false;
        }
        *active_epoch = Some(epoch_id);
        true
    });
    Ok(json!({"operation_id":operation,"epoch":epoch,"accepted":true}))
}

fn exempt(method: &Method, path: &str) -> bool {
    path == "/admin/runtime/system-update/status"
        || path == "/admin/runtime/system-update/ack"
        || path == "/admin/runtime/system-update/cutover"
        || path.starts_with("/runtime/api/system-updates/")
        || path == "/runtime/logout"
        || path == "/admin/runtime/session"
        || (path.starts_with("/runtime/api/accounts/login/")
            && (path.ends_with("/code") || path.ends_with("/commit") || *method == Method::DELETE))
        || (path.starts_with("/admin/runtime/accounts/") && path.ends_with("/lease"))
        || (path.starts_with("/admin/accounts/") && path.ends_with("/oauth-credentials/resolve"))
        || (matches!(*method, Method::GET | Method::HEAD)
            && (path == "/"
                || path == "/login"
                || path == "/updates"
                || path == "/environments"
                || path.starts_with("/assets/")
                || path.starts_with("/admin/")
                || path.starts_with("/runtime/")))
}

/// 在 HTTP 边界登记完整请求和响应流，管理员观察与受证恢复独立准入。
/// @param request 当前 HTTP 请求。
/// @param next 原处理链。
/// @return 原始响应或维护错误，业务字节保持原样。
pub async fn middleware(mut request: Request, next: Next) -> Response {
    if exempt(request.method(), request.uri().path()) {
        return next.run(request).await;
    }
    // 先订阅再登记，避免请求跨越关闭准入与发布信号之间的窗口。
    let path = request.uri().path();
    let inference = request.method() == Method::POST
        && (matches!(path, "/v1/messages" | "/v1/messages/count_tokens")
            || path.strip_prefix("/v1beta/models/").is_some_and(|action| {
                action.ends_with(":generateContent") || action.ends_with(":streamGenerateContent")
            }));
    let cutover = inference.then(InferenceCutover::subscribe);
    let activity = match admission() {
        Ok(activity) => activity,
        Err(_) => {
            let closing_inference = inference
                && gate().ok().flatten().is_some_and(|current| {
                    current.phase == "blocked"
                        && Uuid::parse_str(&current.epoch).ok().as_ref()
                            == INFERENCE_CUTOVER.borrow().as_ref()
                });
            let admission_id = request
                .headers()
                .get("x-v3-update-admission")
                .and_then(|value| value.to_str().ok())
                .unwrap_or("");
            let supplied = request
                .headers()
                .get("x-v3-service-token")
                .and_then(|value| value.to_str().ok())
                .unwrap_or("");
            let expected = std::env::var("V3_INTERNAL_TOKEN").unwrap_or_default();
            let valid = !closing_inference
                && admission_id.len() == 32
                && admission_id.bytes().all(|value| value.is_ascii_hexdigit())
                && expected.len() >= 32
                && bool::from(expected.as_bytes().ct_eq(supplied.as_bytes()));
            let continuation = if valid {
                let activity = {
                    let mut active = ACTIVITIES.lock().unwrap_or_else(|error| error.into_inner());
                    if gate().is_ok() {
                        *active += 1;
                        Some(UpdateActivity)
                    } else {
                        None
                    }
                };
                if activity.is_some()
                    && update_control_admitted(admission_id).await.unwrap_or(false)
                {
                    activity
                } else {
                    None
                }
            } else {
                None
            };
            let Some(activity) = continuation else {
                return (
                    StatusCode::SERVICE_UNAVAILABLE,
                    [("retry-after", "5")],
                    Json(json!({
                    "type":"error", "error":{"type":"overloaded_error","code":"system_maintenance",
                    "message":"平台正在维护，请稍后重试"}})),
                )
                    .into_response();
            };
            // 私有续接核验期间也可能发布切换信号，继续使用入口订阅。
            activity
        }
    };
    let mut wait = cutover.map(|mut signal| {
        request.extensions_mut().insert(signal.clone());
        Box::pin(async move { signal.interrupt().await })
            as Pin<Box<dyn Future<Output = ()> + Send>>
    });
    let response = if let Some(stop) = wait.as_mut() {
        tokio::select! {
            biased;
            _ = stop => return AppError::ServiceUnavailable("平台更新已中断推理，请重试".into()).into_response(),
            response = next.run(request) => response,
        }
    } else {
        next.run(request).await
    };
    let (parts, body) = response.into_parts();
    Response::from_parts(
        parts,
        Body::new(TrackedBody {
            inner: body,
            activity: Some(activity),
            cutover: wait,
        }),
    )
}

#[cfg(all(test, unix))]
mod tests {
    use super::{ACTIVITIES, InferenceCutover, TrackedBody, UpdateActivity, read_gate};
    use axum::body::{Body, Bytes};
    use futures_util::stream;
    use http_body_util::BodyExt;
    use serde_json::json;
    use std::env::temp_dir;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::time::Duration;
    use tokio::sync::{mpsc, watch};
    use tokio_stream::wrappers::ReceiverStream;

    #[tokio::test]
    async fn response_guard_remains_until_body_eof_or_error() {
        let mut body = {
            *ACTIVITIES.lock().unwrap() += 1;
            TrackedBody {
                inner: Body::from_stream(stream::iter([
                    Ok::<_, std::io::Error>(Bytes::from_static(b"first")),
                    Ok(Bytes::from_static(b"last")),
                ])),
                activity: Some(UpdateActivity),
                cutover: None,
            }
        };
        assert_eq!(
            body.frame().await.unwrap().unwrap().into_data().unwrap(),
            "first"
        );
        assert!(body.activity.is_some());
        assert_eq!(
            body.frame().await.unwrap().unwrap().into_data().unwrap(),
            "last"
        );
        assert!(body.activity.is_some());
        assert!(body.frame().await.is_none());
        assert!(body.activity.is_none());
        *ACTIVITIES.lock().unwrap() += 1;
        let mut failed = TrackedBody {
            inner: Body::from_stream(stream::iter([Err::<Bytes, _>(std::io::Error::other(
                "合成断流",
            ))])),
            activity: Some(UpdateActivity),
            cutover: None,
        };
        assert!(failed.frame().await.unwrap().is_err());
        assert!(failed.activity.is_none());
    }

    #[tokio::test]
    async fn cutover_drops_hung_inference_upstream_and_keeps_new_subscribers_open() {
        let (sender, signal) = watch::channel(None);
        let (tx, rx) = mpsc::channel::<Result<Bytes, std::io::Error>>(1);
        let mut cutover = InferenceCutover::new(signal);
        let mut body = TrackedBody {
            inner: Body::from_stream(ReceiverStream::new(rx)),
            activity: None,
            cutover: Some(Box::pin(async move { cutover.cancelled().await })),
        };
        assert!(
            tokio::time::timeout(Duration::from_millis(10), body.frame())
                .await
                .is_err()
        );

        sender.send_replace(Some(uuid::Uuid::new_v4()));
        let result = tokio::time::timeout(Duration::from_secs(1), body.frame())
            .await
            .unwrap();
        assert!(result.unwrap().is_err());
        assert!(tx.is_closed());
        assert!(!InferenceCutover::new(sender.subscribe()).is_cancelled());
    }

    #[test]
    fn gate_contract_rejects_missing_unknown_and_bad_owner() {
        let path = temp_dir().join(format!("v3-update-gate-{}.json", uuid::Uuid::new_v4()));
        assert!(read_gate(&path, "test").is_err());
        let mut value = json!({"schema_version":1,"deployment":"test","operation_id":null,
            "epoch":uuid::Uuid::new_v4().to_string(),"phase":"idle","target_release":null,
            "revision":uuid::Uuid::new_v4().to_string(),"created_at":"2026-11-11T00:00:00Z"});
        fs::write(&path, value.to_string()).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(read_gate(&path, "test").is_ok());
        assert!(read_gate(&path, "other").is_err());
        value["phase"] = json!("unknown");
        fs::write(&path, value.to_string()).unwrap();
        assert!(read_gate(&path, "test").is_err());
        value["phase"] = json!("idle");
        value["extra"] = json!(true);
        fs::write(&path, value.to_string()).unwrap();
        assert!(read_gate(&path, "test").is_err());
        fs::remove_file(path).unwrap();
    }
}
