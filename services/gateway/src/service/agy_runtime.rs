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
use crate::service::runtime_transport::{SenderConfig, now_ms};

/// 单账号监督进程池；热配置更换前要求原活动已收口。
#[derive(Default)]
pub struct AgyPool {
    controller: Mutex<Option<Arc<Controller>>>,
}

struct Subscriber {
    sender: mpsc::Sender<(Value, OwnedSemaphorePermit)>,
    api_token_id: i64,
}

struct Controller {
    identity: String,
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
            Some("job_finalized" | "rejected" | "tools_finished" | "control_error")
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
            controller.send(&json!({"schema_version":1,"type":"finish_tools","request_id":id,
                "account_id":input.request.account_id,"environment_id":input.request.environment_id,
                "environment_generation":input.request.generation,"api_token_id":input.api_token_id,
                "previous_request_id":input.previous_request_id,"body":input.body})).await?;
            let (event,_permit)=timeout_at(deadline,receiver.recv()).await.map_err(|_|unavailable())?.ok_or_else(unavailable)?;
            if event["type"]!="tools_finished" {return Err(AppError::BadRequest("AGY原工具轮回填失败".into()));}
            Ok(json!({"finished":true,"request_id":id,"previous_request_id":input.previous_request_id}))
        }.await;
        controller.requests.lock().await.remove(&id);
        result
    }

    async fn controller(&self, config: &SenderConfig) -> Result<Arc<Controller>, AppError> {
        let native = config.agy.as_ref().ok_or_else(unavailable)?;
        native.validate()?;
        let identity = format!(
            "{:x}",
            Sha256::digest(
                serde_json::to_vec(
                    &json!({"agy":native,"binding":config.binding,"proxy_url":config.proxy_url})
                )
                .map_err(|_| unavailable())?
            )
        );
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
            "proxy_url":config.proxy_url,"capture_enabled":false,"capture_root":"/flows/api/agy-prepared"}),
        )?;
        let mut child = Command::new("python3")
            .args(["-m", "agy_runtime.supervisor", "--config"])
            .arg(&path)
            .env_clear()
            .env("PATH", "/usr/local/bin:/usr/bin:/bin")
            .env("TMPDIR", &generation_root)
            .env(
                "PYTHONPATH",
                format!("{}:/usr/local/bin", native.module_root),
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

    /// 发送独立AGY请求并交付原生私有事件流。@param config 原账号配置。@param submission 已准入信封。@param deadline 原单调截止。@param prepare 是否只准备。@return 私有NDJSON响应。
    pub async fn submit(
        &self,
        config: &SenderConfig,
        submission: AgySubmission,
        deadline: Instant,
        prepare: bool,
    ) -> Result<Response, AppError> {
        submission.validate(now_ms())?;
        let controller = timeout_at(deadline, self.controller(config))
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

    /// 查询已有监督器的实际状态，保持休眠环境。@return 只读资源分项或当前状态。
    pub async fn status(&self, config: &SenderConfig) -> Value {
        let state = self.controller.lock().await;
        let Some(controller) = state.as_ref() else {
            let stale = config.agy.as_ref().is_some_and(|agy| {
                requires_reconciliation(Path::new(&agy.work_root)).unwrap_or(true)
            });
            return json!({"state":if stale {"reconcile"} else {"unprepared"},"workers":0,"active":0});
        };
        if controller.closed.load(Ordering::Acquire) {
            return json!({"state":"unknown","active":controller.active.lock().await.len()});
        }
        let id = Uuid::new_v4().to_string();
        let (sender, mut receiver) = mpsc::channel(1);
        controller.requests.lock().await.insert(
            id.clone(),
            Subscriber {
                sender,
                api_token_id: 0,
            },
        );
        let result = async {
            controller
                .send(&json!({"schema_version":1,"type":"status","request_id":id}))
                .await?;
            timeout(Duration::from_secs(2), receiver.recv())
                .await
                .map_err(|_| unavailable())?
                .ok_or_else(unavailable)
        }
        .await;
        controller.requests.lock().await.remove(&id);
        result
            .map(|(event, _permit)| event["status"].clone())
            .unwrap_or(json!({"state":"unknown"}))
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
