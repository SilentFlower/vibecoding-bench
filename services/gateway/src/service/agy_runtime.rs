//! 现有账号发送器内的AGY监督协议，HTTP结束与原工具轮结束分别计数。
use std::collections::{HashMap, HashSet};
use std::fs::{self, OpenOptions};
use std::io::{Error as IoError, Result as IoResult, Write};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use axum::body::{Body, Bytes};
use axum::http::StatusCode;
use axum::response::Response;
use futures_util::StreamExt;
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tokio::io::{AsyncBufRead, AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, Command};
use tokio::runtime::Handle;
use tokio::sync::{Mutex, OwnedSemaphorePermit, Semaphore, mpsc, oneshot};
use tokio::time::{Instant, timeout, timeout_at};
use tokio_stream::wrappers::ReceiverStream;
use uuid::Uuid;

use crate::error::AppError;
use crate::service::agy_contract::{AgySubmission, AgyToolCompletion};
use crate::service::runtime_transport::{SenderConfig, now_ms, read_config};

/// 单账号监督进程池；热配置更换前要求原活动已收口。
#[derive(Default)]
pub struct AgyPool {
    controller: Mutex<Option<Arc<Controller>>>,
    capacity_lock: Mutex<()>,
}

struct Subscriber {
    sender: mpsc::Sender<(Value, OwnedSemaphorePermit)>,
    api_token_id: i64,
}

struct Controller {
    identity: String,
    module_root: String,
    input: Mutex<ChildStdin>,
    child: Mutex<Child>,
    requests: Mutex<HashMap<String, Subscriber>>,
    active: Mutex<HashSet<String>>,
    closed: AtomicBool,
    byte_budget: Arc<Semaphore>,
}

fn unavailable() -> AppError {
    AppError::ServiceUnavailable("AGY账号执行进程暂不可用".into())
}

fn controller_identity(config: &SenderConfig) -> Result<String, AppError> {
    let mut native = config.agy.as_ref().ok_or_else(unavailable)?.clone();
    native.validate()?;
    // 容量通过受信控制指令单独生效。池身份仍核对实际内核、代理和绑定。
    native.max_workers = 0;
    native.memory_mib = 0;
    let identity = json!({"agy":native,"binding":config.binding,"proxy_url":config.proxy_url});
    Ok(format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&identity).map_err(|_| unavailable())?)
    ))
}

fn restore_allowed(config_path: &str) -> Result<bool, AppError> {
    #[derive(Deserialize)]
    struct RestorePolicy {
        native_criu_enabled: Option<bool>,
    }
    let raw = fs::read(config_path).map_err(|_| unavailable())?;
    let policy: RestorePolicy = serde_json::from_slice(&raw).map_err(|_| unavailable())?;
    Ok(policy.native_criu_enabled.unwrap_or(true))
}

fn requires_reconciliation(root: &Path) -> Result<bool, AppError> {
    if !root.exists() {
        return Ok(false);
    }
    for entry in fs::read_dir(root).map_err(|_| unavailable())? {
        let entry = entry.map_err(|_| unavailable())?;
        if entry.file_type().map_err(|_| unavailable())?.is_symlink() {
            return Err(unavailable());
        }
        let path = entry.path();
        if path.join("supervisor.json").exists() && !path.join("state/stopped.json").is_file() {
            return Ok(true);
        }
    }
    Ok(false)
}

fn write_private(path: &Path, value: &Value) -> Result<(), AppError> {
    let temporary = path.with_extension(Uuid::new_v4().simple().to_string());
    let mut output = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&temporary)
        .map_err(|_| unavailable())?;
    output
        .write_all(&serde_json::to_vec(value).map_err(|_| unavailable())?)
        .and_then(|_| output.sync_all())
        .map_err(|_| unavailable())?;
    fs::rename(&temporary, path).map_err(|_| unavailable())
}

impl Controller {
    async fn send(&self, value: &Value) -> Result<(), AppError> {
        if self.closed.load(Ordering::Acquire) {
            return Err(unavailable());
        }
        let mut raw = serde_json::to_vec(value).map_err(|_| unavailable())?;
        raw.push(b'\n');
        let mut input = self.input.lock().await;
        timeout(Duration::from_secs(5), async {
            input.write_all(&raw).await?;
            input.flush().await
        })
        .await
        .map_err(|_| unavailable())?
        .map_err(|_| unavailable())
    }

    async fn dispatch(&self, event: Value, wire_bytes: usize) -> Result<(), AppError> {
        let Some(request_id) = event.get("request_id").and_then(Value::as_str) else {
            return Ok(());
        };
        let request_id = request_id.to_string();
        let terminal = matches!(
            event["type"].as_str(),
            Some(
                "job_finalized"
                    | "rejected"
                    | "tools_finished"
                    | "control_error"
                    | "capacity_applied"
                    | "status"
            )
        );
        // 活动覆盖异常收口和工具等待，直到监督层确认物理作业已结束。
        if event["type"] == "job_finalized" {
            self.active.lock().await.remove(&request_id);
        }
        if event["type"] == "rejected" {
            self.active.lock().await.remove(&request_id);
        }
        let mut requests = self.requests.lock().await;
        if let Some(subscriber) = requests.get(&request_id) {
            let sender = subscriber.sender.clone();
            let api_token_id = subscriber.api_token_id;
            if terminal {
                requests.remove(&request_id);
            }
            drop(requests);
            // 慢客户端在原预算内由流取消收口，禁止堵住其它请求的唯一读取器。
            let delivered = if let Ok(permit) = self
                .byte_budget
                .clone()
                .try_acquire_many_owned(wire_bytes.div_ceil(1024).max(1) as u32)
            {
                matches!(
                    timeout(Duration::from_millis(100), sender.send((event, permit))).await,
                    Ok(Ok(()))
                )
            } else {
                false
            };
            if !delivered {
                self.requests.lock().await.remove(&request_id);
                let _ = self.send(&json!({"schema_version":1,"type":"cancel", "request_id":request_id,"api_token_id":api_token_id})).await;
            }
        }
        Ok(())
    }

    async fn query(&self, mut message: Value) -> Result<Value, AppError> {
        let id = Uuid::new_v4().to_string();
        message["request_id"] = json!(id);
        let (sender, mut receiver) = mpsc::channel(1);
        self.requests.lock().await.insert(
            id.clone(),
            Subscriber {
                sender,
                api_token_id: 0,
            },
        );
        let result = async {
            self.send(&message).await?;
            timeout(Duration::from_secs(2), receiver.recv())
                .await
                .map_err(|_| unavailable())?
                .ok_or_else(unavailable)
        }
        .await;
        self.requests.lock().await.remove(&id);
        result.map(|(event, _permit)| event)
    }

    async fn stop(&self) {
        if self.closed.load(Ordering::Acquire) {
            let _ = self.child.lock().await.kill().await;
            return;
        }
        let _ = self
            .send(&json!({"schema_version":1,"type":"shutdown"}))
            .await;
        if timeout(Duration::from_secs(100), self.child.lock().await.wait())
            .await
            .is_err()
        {
            let _ = self.child.lock().await.kill().await;
        }
        self.closed.store(true, Ordering::Release);
    }
}

struct CancelOnDrop {
    controller: Arc<Controller>,
    request_id: String,
    api_token_id: i64,
    complete: Arc<AtomicBool>,
}

impl Drop for CancelOnDrop {
    fn drop(&mut self) {
        if self.complete.load(Ordering::Acquire) {
            return;
        }
        let controller = self.controller.clone();
        let request_id = self.request_id.clone();
        let api_token_id = self.api_token_id;
        let Ok(runtime) = Handle::try_current() else {
            return;
        };
        runtime.spawn(async move {
            let _ = controller
                .send(&json!({"schema_version":1,"type":"cancel", "request_id":request_id,"api_token_id":api_token_id}))
                .await;
        });
    }
}

impl AgyPool {
    /// 请求监督器取消原私有请求。@param request_id 原尝试身份。@param api_token_id 原调用方。@return 取消指令是否已登记。
    pub(crate) async fn cancel(&self, request_id: &str, api_token_id: i64) -> Result<(), AppError> {
        let controller = self.controller.lock().await.clone();
        let Some(controller) = controller else {
            return Ok(());
        };
        {
            let requests = controller.requests.lock().await;
            if !controller.active.lock().await.contains(request_id) {
                return Ok(());
            }
            if requests
                .get(request_id)
                .is_none_or(|request| request.api_token_id != api_token_id)
            {
                return Err(AppError::Unauthorized);
            }
        }
        controller
            .send(&json!({"schema_version":1,"type":"cancel",
            "request_id":request_id,"api_token_id":api_token_id}))
            .await
    }

    /// 沿原监督器完成工具回填，保持零模型发送。@param input 原归属和真实结果。@param deadline 原单调截止。@return 已核验的收口回执。
    pub async fn finish_tools(
        &self,
        input: AgyToolCompletion,
        deadline: Instant,
    ) -> Result<Value, AppError> {
        let controller = self
            .controller
            .lock()
            .await
            .as_ref()
            .cloned()
            .ok_or_else(unavailable)?;
        if input.api_token_id < 1
            || Uuid::parse_str(&input.previous_request_id).is_err()
            || !input.body.is_object()
        {
            return Err(AppError::BadRequest("AGY工具归属无效".into()));
        }
        let id = input.request.request_id.clone();
        let (sender, mut receiver) = mpsc::channel(1);
        {
            let mut requests = controller.requests.lock().await;
            if requests.contains_key(&id) {
                return Err(AppError::BadRequest("AGY工具控制请求重复".into()));
            }
            requests.insert(
                id.clone(),
                Subscriber {
                    sender,
                    api_token_id: input.api_token_id,
                },
            );
        }
        let result=async {
            let mut value = json!({"schema_version":1,"type":"finish_tools","request_id":id,
                "account_id":input.request.account_id,"environment_id":input.request.environment_id,
                "environment_generation":input.request.generation,"api_token_id":input.api_token_id,
                "previous_request_id":input.previous_request_id,"body":input.body});
            if input.gif_frames { value["gif_frames"] = Value::Bool(true); }
            controller.send(&value).await?;
            let (event,_permit)=timeout_at(deadline,receiver.recv()).await.map_err(|_|unavailable())?.ok_or_else(unavailable)?;
            if event["type"] == "control_error" {
                if let Some(code) = event["code"].as_str() {
                    let kind = code.split(':').next().unwrap_or_default();
                    match kind {
                        "invalid_gemini_png" | "invalid_gemini_media"
                        | "unsupported_gemini_media_type" | "unsupported_gemini_image_type"
                        | "gif_conversion_limit" | "gemini_pending_history_mismatch"
                        | "gemini_pending_turn_mismatch" | "gemini_pending_call_mismatch"
                        | "gemini_pending_results_mismatch" => {
                            return Ok(json!({"input_rejection":code}));
                        }
                        "previous_tool_turn_failed" => return Err(AppError::AgyToolTurnFailed),
                        "tool_completion_failed" | "tool_completion_pending" => {
                            return Err(unavailable());
                        }
                        _ => {}
                    }
                }
            }
            if event["type"]!="tools_finished" {return Err(AppError::BadRequest("AGY原工具轮回填失败".into()));}
            Ok(json!({"finished":true,"request_id":id,"previous_request_id":input.previous_request_id}))
        }.await;
        controller.requests.lock().await.remove(&id);
        result
    }

    async fn controller(
        &self,
        config: &SenderConfig,
        config_path: &str,
    ) -> Result<Arc<Controller>, AppError> {
        let identity = controller_identity(config)?;
        let mut state = self.controller.lock().await;
        if let Some(controller) = state.as_ref() {
            if controller.identity == identity && !controller.closed.load(Ordering::Acquire) {
                return Ok(controller.clone());
            }
            if !controller.active.lock().await.is_empty() {
                return Err(AppError::ServiceUnavailable(
                    "AGY原代次仍有活动，请等待收口".into(),
                ));
            }
        }
        // 等待池锁期间编辑可能已经完成。新进程须使用本代当前容量启动。
        let config = read_config(config_path)?;
        if controller_identity(&config)? != identity {
            return Err(unavailable());
        }
        let native = config.agy.as_ref().ok_or_else(unavailable)?;
        if let Some(controller) = state.as_ref() {
            controller.stop().await;
        }
        let root = PathBuf::from(&native.work_root);
        if requires_reconciliation(&root)? {
            return Err(AppError::ServiceUnavailable(
                "AGY原监督器异常退出，需要环境对账".into(),
            ));
        }
        fs::create_dir_all(&root).map_err(|_| unavailable())?;
        fs::set_permissions(&root, fs::Permissions::from_mode(0o700)).map_err(|_| unavailable())?;
        let generation_root = root.join(Uuid::new_v4().simple().to_string());
        fs::create_dir(&generation_root).map_err(|_| unavailable())?;
        fs::set_permissions(&generation_root, fs::Permissions::from_mode(0o700))
            .map_err(|_| unavailable())?;
        let path = generation_root.join("supervisor.json");
        write_private(
            &path,
            &json!({"account_id":config.binding.account_id,"environment_id":config.binding.environment_id,
            "environment_generation":config.binding.generation,"binary_path":native.binary_path,
            "work_root":generation_root.join("state"),"max_workers":native.max_workers,"memory_mib":native.memory_mib,
            "restore_allowed":restore_allowed(config_path)?,
            "proxy_url":config.proxy_url,"capture_enabled":false,"capture_root":"/flows/api/agy-prepared"}),
        )?;
        let mut child = Command::new("python3")
            .args(["-P", "-m", "agy_runtime.supervisor", "--config"])
            .arg(&path)
            .env_clear()
            .env("PATH", "/usr/local/bin:/usr/bin:/bin")
            .env("TMPDIR", &generation_root)
            .env("AGY_CAPTURE_NATIVE_TLS", "1")
            .env(
                "AGY_CRIU",
                if std::env::var("AGY_CRIU").as_deref() == Ok("1") {
                    "1"
                } else {
                    "0"
                },
            )
            .env(
                "PYTHONPATH",
                format!("{}:/opt/v3/python:/usr/local/bin", native.module_root),
            )
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true)
            .spawn()
            .map_err(|_| unavailable())?;
        let input = child.stdin.take().ok_or_else(unavailable)?;
        let output = child.stdout.take().ok_or_else(unavailable)?;
        let controller = Arc::new(Controller {
            identity,
            module_root: native.module_root.clone(),
            input: Mutex::new(input),
            child: Mutex::new(child),
            requests: Mutex::new(HashMap::new()),
            active: Mutex::new(HashSet::new()),
            closed: AtomicBool::new(false),
            byte_budget: Arc::new(Semaphore::new(64 * 1024)),
        });
        let (ready_sender, ready_receiver) = oneshot::channel();
        let weak = Arc::downgrade(&controller);
        let account_id = config.binding.account_id;
        let environment_id = config.binding.environment_id.clone();
        let generation = config.binding.generation;
        tokio::spawn(async move {
            let mut output = BufReader::new(output);
            let mut ready = Some(ready_sender);
            loop {
                let Ok(Some(line)) = read_bounded_line(&mut output).await else {
                    break;
                };
                let Some(controller) = weak.upgrade() else {
                    break;
                };
                let Ok(event) = serde_json::from_slice::<Value>(&line) else {
                    break;
                };
                if line.len() > 64 * 1024 * 1024
                    || event["protocol"] != "agy-account-supervisor"
                    || event["schema_version"] != 1
                    || event["account_id"].as_i64() != Some(account_id)
                    || event["environment_id"].as_str() != Some(environment_id.as_str())
                    || event["environment_generation"].as_u64() != Some(generation)
                {
                    break;
                }
                if event["type"] == "supervisor_ready" {
                    if let Some(sender) = ready.take() {
                        let _ = sender.send(());
                    }
                } else if controller.dispatch(event, line.len()).await.is_err() {
                    break;
                }
            }
            if let Some(controller) = weak.upgrade() {
                controller.closed.store(true, Ordering::Release);
                controller.requests.lock().await.clear();
            }
        });
        timeout(Duration::from_secs(10), ready_receiver)
            .await
            .map_err(|_| unavailable())?
            .map_err(|_| unavailable())?;
        *state = Some(controller.clone());
        Ok(controller)
    }

    /// 发送独立AGY请求并交付原生私有事件流。@param config 原账号配置。@param config_path 私有配置入口。@param submission 已准入信封。@param deadline 原单调截止。@param prepare 是否只准备。@return 私有NDJSON响应。
    pub async fn submit(
        &self,
        config: &SenderConfig,
        config_path: &str,
        submission: AgySubmission,
        deadline: Instant,
        prepare: bool,
    ) -> Result<Response, AppError> {
        submission.validate(now_ms())?;
        let controller = timeout_at(deadline, self.controller(config, config_path))
            .await
            .map_err(|_| unavailable())??;
        let (sender, receiver) = mpsc::channel(16);
        let complete = Arc::new(AtomicBool::new(false));
        let request_id = submission.request.request_id.clone();
        {
            let mut requests = controller.requests.lock().await;
            if requests.contains_key(&request_id)
                || controller.active.lock().await.contains(&request_id)
            {
                return Err(AppError::BadRequest("AGY请求已经登记".into()));
            }
            requests.insert(
                request_id.clone(),
                Subscriber {
                    sender,
                    api_token_id: submission.api_token_id,
                },
            );
            controller.active.lock().await.insert(request_id.clone());
        }
        let guard = CancelOnDrop {
            controller: controller.clone(),
            request_id: request_id.clone(),
            api_token_id: submission.api_token_id,
            complete,
        };
        let mut value = json!({"schema_version":1,"type":if prepare {"prepare"} else {"submit"},
            "request_id":request_id,"account_id":submission.request.account_id,
            "environment_id":submission.request.environment_id,"environment_generation":submission.request.generation,
            "api_token_id":submission.api_token_id,"credential_snapshot":submission.credential_snapshot,
            "model":submission.model,"native_model":submission.native_model,"body":submission.body,
            "deadline_unix_ms":submission.request.deadline_unix_ms,"capture_enabled":submission.capture_enabled});
        if submission.system_prompt_policy.enabled {
            value["system_prompt_policy"] = serde_json::to_value(&submission.system_prompt_policy)
                .map_err(|_| unavailable())?;
        }
        if submission.gif_frames {
            value["gif_frames"] = Value::Bool(true);
        }
        if submission.full_egress {
            value["full_egress"] = Value::Bool(true);
        }
        if submission.disable_safety_filtering {
            value["disable_safety_filtering"] = Value::Bool(true);
        }
        if let Err(error) = controller.send(&value).await {
            controller.requests.lock().await.remove(&request_id);
            return Err(error);
        }
        let delivered = guard.complete.clone();
        let stream = ReceiverStream::new(receiver).map(move |(event, _permit)| {
            if event["type"] == "job_finalized" || event["type"] == "rejected" {
                delivered.store(true, Ordering::Release);
            }
            serde_json::to_vec(&event)
                .map(|mut raw| {
                    raw.push(b'\n');
                    Bytes::from(raw)
                })
                .map_err(IoError::other)
        });
        let stream =
            futures_util::stream::unfold((stream, guard), |(mut stream, guard)| async move {
                stream.next().await.map(|item| (item, (stream, guard)))
            });
        Response::builder()
            .status(StatusCode::OK)
            .header("content-type", "application/x-ndjson")
            .body(Body::from_stream(stream))
            .map_err(|_| unavailable())
    }

    /// 读取实际仍在执行或等待工具的请求数。@return 当前物理活动数。
    pub async fn active(&self) -> u64 {
        if let Some(controller) = self.controller.lock().await.as_ref() {
            controller.active.lock().await.len() as u64
        } else {
            0
        }
    }

    /// 按受信配置应用容量，并核对监督器回执。@param config_path 私有配置入口。@param authorize 当前请求的绑定校验。@return 已实际应用的物理上限。
    pub(super) async fn apply_capacity(
        &self,
        config_path: &str,
        authorize: impl FnOnce(&SenderConfig) -> Result<(), AppError>,
    ) -> Result<usize, AppError> {
        let _change = self.capacity_lock.lock().await;
        let config = read_config(config_path)?;
        authorize(&config)?;
        let target = config.agy.as_ref().ok_or_else(unavailable)?.max_workers;
        let controller = self.controller(&config, config_path).await?;
        let result = controller
            .query(
                json!({"schema_version":1,"type":"capacity","max_workers":target,
                "restore_allowed":restore_allowed(config_path)?}),
            )
            .await?;
        if result["type"] != "capacity_applied"
            || result["max_workers"].as_u64() != Some(target as u64)
        {
            return Err(AppError::ServiceUnavailable(
                "AGY发送器暂不支持在线调整，请先升级运行环境".into(),
            ));
        }
        Ok(target)
    }

    /// 查询已有监督器的实际状态，保持休眠环境。@param config 当前绑定配置。@return 只读资源分项或当前状态。
    pub async fn status(&self, config: &SenderConfig) -> Value {
        let state = self.controller.lock().await;
        let Some(controller) = state.as_ref() else {
            let stale = config.agy.as_ref().is_some_and(|agy| {
                requires_reconciliation(Path::new(&agy.work_root)).unwrap_or(true)
            });
            return json!({"state":if stale {"reconcile"} else {"unprepared"},
                "capacity_protocol":1,"workers":0,"allocated_workers":0,"active":0,
                "max_workers":config.agy.as_ref().map(|agy| agy.max_workers)});
        };
        if controller.closed.load(Ordering::Acquire) {
            return json!({"state":"unknown","active":controller.active.lock().await.len()});
        }
        let result = controller
            .query(json!({"schema_version":1,"type":"status"}))
            .await;
        let mut status = result
            .map(|event| event["status"].clone())
            .unwrap_or(json!({"state":"unknown"}));
        if let Some(fields) = status.as_object_mut() {
            fields.insert("module_root".into(), json!(controller.module_root));
        }
        status
    }
}

/// 有界读取私有NDJSON，先限制分配再解析。@param reader 唯一协议读取器。@return 完整行、EOF或协议错误。
async fn read_bounded_line<R: AsyncBufRead + Unpin>(reader: &mut R) -> IoResult<Option<Vec<u8>>> {
    let mut line = Vec::new();
    loop {
        let buffer = reader.fill_buf().await?;
        if buffer.is_empty() {
            return if line.is_empty() {
                Ok(None)
            } else {
                Err(IoError::other("AGY协议提前结束"))
            };
        }
        let end = buffer
            .iter()
            .position(|byte| *byte == b'\n')
            .map(|index| index + 1);
        let count = end.unwrap_or(buffer.len());
        if line.len() + count > 64 * 1024 * 1024 {
            return Err(IoError::other("AGY协议帧超限"));
        }
        line.extend_from_slice(&buffer[..count]);
        reader.consume(count);
        if end.is_some() {
            return Ok(Some(line));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 取消只交给原监督器，活动直到真实终态才释放。@return 无。
    #[tokio::test]
    async fn cancel_checks_owner_and_keeps_activity_until_supervisor_finalizes() {
        let mut child = Command::new("cat")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .unwrap();
        let input = child.stdin.take().unwrap();
        let mut output = BufReader::new(child.stdout.take().unwrap());
        let (sender, mut receiver) = mpsc::channel(1);
        let request_id = Uuid::new_v4().to_string();
        let controller = Arc::new(Controller {
            identity: "synthetic".into(),
            module_root: "synthetic".into(),
            input: Mutex::new(input),
            child: Mutex::new(child),
            requests: Mutex::new(HashMap::from([(
                request_id.clone(),
                Subscriber {
                    sender,
                    api_token_id: 7,
                },
            )])),
            active: Mutex::new(HashSet::from([request_id.clone()])),
            closed: AtomicBool::new(false),
            byte_budget: Arc::new(Semaphore::new(1)),
        });
        let pool = AgyPool {
            controller: Mutex::new(Some(controller.clone())),
            ..AgyPool::default()
        };

        assert!(matches!(
            pool.cancel(&request_id, 8).await,
            Err(AppError::Unauthorized)
        ));
        pool.cancel(&request_id, 7).await.unwrap();
        let line = timeout(Duration::from_secs(1), read_bounded_line(&mut output))
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        assert_eq!(
            serde_json::from_slice::<Value>(&line).unwrap(),
            json!({"schema_version":1,"type":"cancel","request_id":request_id,"api_token_id":7})
        );
        assert_eq!(pool.active().await, 1);

        let finalized =
            json!({"type":"job_finalized","request_id":request_id,"status":"cancelled"});
        controller.dispatch(finalized.clone(), 128).await.unwrap();
        assert_eq!(pool.active().await, 0);
        assert_eq!(receiver.recv().await.unwrap().0, finalized);
    }
}
