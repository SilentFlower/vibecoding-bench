//! 账号 sender 持有单次预留及同容器 Unix 事件通道。

use std::collections::HashMap;
use std::io;
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use axum::body::{Body, Bytes, to_bytes};
use axum::extract::Request;
use axum::http::{HeaderMap, HeaderName, HeaderValue, StatusCode, header::CONTENT_TYPE};
use axum::response::{IntoResponse, Response};
use base64::{Engine, engine::general_purpose::STANDARD};
use futures_util::stream::unfold;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;
use tokio::sync::{SemaphorePermit, oneshot, watch};
use tokio::time::{Instant, sleep_until, timeout, timeout_at};
use uuid::Uuid;

use crate::error::AppError;
use crate::model::account::TuiSystemPromptPolicy;
use crate::model::request_diagnostics::{TuiBodySource, TuiInstructionLocation, TuiSessionOrigin};
use crate::service::diagnostics::tui_startup_event;
use crate::service::gateway::is_passive_usage_header;
use crate::service::native_capture::tui_wire::CaptureJob;
use crate::service::native_capture::{TuiCaptureInput, tui_writer};
use crate::service::native_signature_repair::{
    SIGNATURE_ERROR_BODY_LIMIT, is_signature_rejection, wire::repair_body,
};
use crate::service::request_body_codec::REQUEST_BODY_LIMIT;
use crate::service::request_session::valid_id;
use crate::service::runtime_transport::{
    REQUEST_BUDGET_MS, TUI_BODY_POLICY, TUI_GATEWAY_ID_HEADER, TUI_INPUT_FORMAT, TUI_INPUT_POLICY,
    TUI_JSON_PROJECTION_V1, TUI_MANAGED_OAUTH, TUI_OAUTH_FILE, TUI_OAUTH_FILE_LIMIT,
    TUI_SSE_PROJECTION_HEADER, TUI_SSE_PROJECTION_V1, TUI_UPSTREAM_SESSION, TUI_V2_STATUS_PROTOCOL,
    TransportBinding, TuiBodyPolicy, TuiOAuthFile, now_ms, request_budget, tui_delegates_json,
    tui_input_rejection, tui_model_headers, tui_projection_marker, valid_tui_account_token,
};
use crate::service::runtime_transport::{
    TUI_BODY_SOURCE, TUI_CAPTURE, TUI_CLI_INPUT_GUARD, TUI_CLI_SUBMISSION, TUI_ERROR_SOURCE,
    TUI_FINAL_CAPTURE, TUI_INSTRUCTION_LOCATION, TUI_MODEL_ACCEPT_OMITTED, TUI_MODEL_HEADER_POLICY,
    TUI_OPENING_USAGE_PLACEHOLDER, TUI_PREPARE_BIND, TUI_PREPARE_EXCHANGE, TUI_PREPARE_LEDGER,
    TUI_PROMPT_SUGGESTION, TUI_REPAIR_ATTEMPT, TUI_SEND_CLAIM, TUI_SENDER_CONFIG,
    TUI_SESSION_ORIGIN, TUI_SIGNATURE_REPAIR, TUI_SUBMISSION_LEDGER, TUI_SYSTEM_PROMPT_POLICY,
    TUI_TITLE_SESSION_MAPPING, TUI_WORKSPACE_BIND, TuiReceiptProbe, TuiV2Unavailable,
};
use crate::service::session_policy_block;
use crate::service::tui_sender_response;
use crate::service::tui_tool_history::{SERVER_SESSION_PREFIX, SUGGESTION_SESSION_PREFIX, auxiliary_original_session};
use axum::http::header::RETRY_AFTER;
#[path = "tui_submission_log.rs"]
mod submission_log;
#[path = "tui_workspace.rs"]
mod workspace;

const SOCKET: &str = "/run/v3/tui-v2/events.sock";
const SUBMISSION_STORAGE: &str = "/native";
const RESERVATION_HEADER: &str = "x-v3-tui-reservation";
const HANDOFF_HEADER: &str = "x-v3-tui-handoff-kind";
const CONTROL_LIMIT: usize = 4096;
const CHUNK_LIMIT: usize = 64 * 1024;
const MAX_RESERVATIONS: usize = 64;
// 保留有界的已用 ID 到原截止，防止重放重新进入工作源。
const MAX_RECORDS: usize = 1024;
const IO_TIMEOUT: Duration = Duration::from_millis(REQUEST_BUDGET_MS);

/// 私有 sender 文档中显式登记的本机事件源容量。路径由 sender 固定。
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SourceConfig {
    max_reservations: usize,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
struct Identity {
    account_id: i64,
    environment_id: String,
    generation: u64,
    principal_id: i64,
    session_id: String,
    reservation_id: String,
    deadline_unix_ms: u64,
    continuation_only: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    agent_hint: Option<String>,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    agent_summary: bool,
}

impl Identity {
    fn decode(headers: &HeaderMap, binding: &TransportBinding) -> Result<Self, AppError> {
        let mut headers = headers.get_all(RESERVATION_HEADER).iter();
        let raw = headers.next().ok_or_else(invalid_identity)?.as_bytes();
        if headers.next().is_some() || raw.len() > CONTROL_LIMIT {
            return Err(invalid_identity());
        }
        let data = STANDARD.decode(raw).map_err(|_| invalid_identity())?;
        let identity: Self = serde_json::from_slice(&data).map_err(|_| invalid_identity())?;
        let id = Uuid::parse_str(&identity.reservation_id).map_err(|_| invalid_identity())?;
        if binding.account_id <= 0
            || binding.generation == 0
            || binding.release_id.is_empty()
            || identity.principal_id <= 0
            || (identity.agent_summary
                && (identity.agent_hint.is_none() || identity.continuation_only))
            || !valid_id(&identity.session_id)
            || identity
                .agent_hint
                .as_deref()
                .is_some_and(|hint| !valid_id(hint))
            || id.to_string() != identity.reservation_id
            || identity.account_id != binding.account_id
            || identity.environment_id != binding.environment_id
            || identity.generation != binding.generation
        {
            return Err(invalid_identity());
        }
        Ok(identity)
    }

    fn deadlines(
        &self,
        binding: &TransportBinding,
        wall_now: u64,
    ) -> Result<(Instant, Instant), AppError> {
        let now = Instant::now();
        let deadline = now
            + request_budget(
                binding,
                self.account_id,
                &self.environment_id,
                self.generation,
                &self.reservation_id,
                self.deadline_unix_ms,
                wall_now,
                REQUEST_BUDGET_MS,
            )?;
        // 执行预算按共享约束取较小值。已用 ID 须覆盖整个原信封的有效期。
        let replay_until = now + Duration::from_millis(self.deadline_unix_ms - wall_now);
        Ok((deadline, replay_until))
    }
}

enum Phase {
    Preparing,
    Ready {
        connection: BufReader<UnixStream>,
        workspace: Option<workspace::Candidate>,
        session_mapping: bool,
        managed_oauth: bool,
        oauth_file: bool,
        signature_repair: Option<bool>,
        cli_submission: Option<&'static str>,
    },
    Submitted,
    RepairPending(oneshot::Sender<RepairPermit>),
    Closed,
}

struct RepairPermit {
    attempt: Uuid,
    projection: ResponseProjection,
    response: oneshot::Sender<Result<Response, AppError>>,
}

#[derive(Clone, Copy)]
struct ResponseProjection {
    json: bool,
    sse: bool,
}

impl ResponseProjection {
    fn from_headers(headers: &HeaderMap) -> Self {
        Self {
            json: tui_delegates_json(headers),
            sse: tui_projection_marker(headers, TUI_SSE_PROJECTION_HEADER, TUI_SSE_PROJECTION_V1),
        }
    }
}

type Capture = (
    PathBuf,
    TuiCaptureInput,
    i64,
    Uuid,
    SemaphorePermit<'static>,
);

struct SignatureOffer {
    source: &'static str,
    rejection: Vec<u8>,
    repaired: Vec<u8>,
    capture: Option<(Vec<(String, String)>, Vec<u8>)>,
}

enum SourceReply {
    Final { head: Value, repaired: bool },
    Signature(SignatureOffer),
}

#[derive(Clone, Copy)]
struct SourceOptions {
    projection: ResponseProjection,
    managed: bool,
    oauth_file: bool,
    wire: bool,
    cli_submission: Option<&'static str>,
    captured: bool,
}

struct Record {
    repair_attempt: Option<Uuid>,
    wire_capture: Option<CaptureJob>,
    identity: Identity,
    agent_probe: bool,
    fork_borrowed_slot: bool,
    binding_proof: [u8; 32],
    deadline: Instant,
    replay_until: Instant,
    ticket: Uuid,
    cancel: watch::Sender<bool>,
    phase: Phase,
}

type Book = Arc<Mutex<HashMap<String, Record>>>;

struct Slot {
    book: Book,
    id: String,
    ticket: Uuid,
    armed: bool,
}

impl Slot {
    fn install_wire_capture(&self, capture: CaptureJob) -> bool {
        let mut book = self.book.lock().unwrap();
        if let Some(record) = book.get_mut(&self.id).filter(|record| {
            record.ticket == self.ticket && matches!(record.phase, Phase::Submitted)
        }) {
            record.wire_capture = Some(capture);
            true
        } else {
            false
        }
    }
}

impl Drop for Slot {
    fn drop(&mut self) {
        if !self.armed {
            return;
        }
        let mut book = self.book.lock().unwrap();
        if let Some(record) = book
            .get_mut(&self.id)
            .filter(|record| record.ticket == self.ticket)
        {
            if record.replay_until <= Instant::now() {
                book.remove(&self.id);
            } else {
                record.phase = Phase::Closed;
                record.wire_capture = None;
            }
        }
    }
}

/// sender 进程的本机预留账本及固定事件通道。
pub(super) struct TuiSender {
    path: PathBuf,
    submission_storage: PathBuf,
    book: Book,
}

impl Default for TuiSender {
    fn default() -> Self {
        Self {
            path: SOCKET.into(),
            submission_storage: SUBMISSION_STORAGE.into(),
            book: Book::default(),
        }
    }
}

fn unavailable() -> AppError {
    AppError::ServiceUnavailable("V2 本机事件源未通过准备或绑定核验".into())
}

fn stage_response(error: AppError, stage: &'static str) -> Response {
    let mut response = error.into_response();
    response
        .headers_mut()
        .insert(TUI_ERROR_SOURCE, HeaderValue::from_static(stage));
    response
}

fn invalid_identity() -> AppError {
    AppError::BadRequest("V2 预留身份或正文不匹配".into())
}

fn consumed() -> AppError {
    AppError::BadRequest("V2 预留不存在、已提交或已取消".into())
}

fn limited() -> AppError {
    AppError::AdmissionLimited { retry_after: 1 }
}

fn source_error() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "V2 本机事件通道无效或提前终止")
}

fn setting(config: Option<&Value>) -> Result<SourceConfig, AppError> {
    let parsed = config
        .and_then(|value| SourceConfig::deserialize(value).ok())
        .ok_or_else(unavailable)?;
    if !(1..=MAX_RESERVATIONS).contains(&parsed.max_reservations) {
        return Err(unavailable());
    }
    Ok(parsed)
}

fn binding_proof(binding: &TransportBinding) -> [u8; 32] {
    // 绑定秘密或发行发生变化时，旧预留即使环境代次相同也不得被新配置认领。
    Sha256::digest(serde_json::to_vec(binding).expect("绑定只含 JSON 基本类型")).into()
}

fn occupied(book: &HashMap<String, Record>) -> usize {
    book.values()
        .filter(|record| !matches!(record.phase, Phase::Closed))
        .count()
}

fn prune(book: &mut HashMap<String, Record>) {
    let now = Instant::now();
    book.retain(|_, record| {
        match record.phase {
            Phase::Submitted | Phase::RepairPending(_) => return true,
            Phase::Preparing => {
                if record.deadline <= now {
                    record.cancel.send_replace(true);
                }
                // 等待原任务丢弃正文及连接后再释放名额。
                return true;
            }
            Phase::Ready { .. } if record.deadline <= now => record.phase = Phase::Closed,
            _ => {}
        }
        record.replay_until > now
    });
}

async fn open(path: &Path) -> io::Result<BufReader<UnixStream>> {
    let owner = unsafe { libc::geteuid() };
    let directory = tokio::fs::symlink_metadata(path.parent().ok_or_else(source_error)?).await?;
    let socket = tokio::fs::symlink_metadata(path).await?;
    if !directory.is_dir()
        || directory.uid() != owner
        || directory.mode() & 0o777 != 0o700
        || !socket.file_type().is_socket()
        || socket.uid() != owner
        || socket.mode() & 0o077 != 0
    {
        return Err(source_error());
    }
    let connection = UnixStream::connect(path).await?;
    let peer = connection.peer_cred()?;
    if peer.uid() != owner || !peer.pid().is_some_and(|pid| pid > 0) {
        return Err(source_error());
    }
    Ok(BufReader::new(connection))
}

async fn write_json(connection: &mut BufReader<UnixStream>, value: &Value) -> io::Result<()> {
    let mut wire = serde_json::to_vec(value).map_err(|_| source_error())?;
    wire.push(b'\n');
    connection.get_mut().write_all(&wire).await
}

async fn read_json(connection: &mut BufReader<UnixStream>) -> io::Result<Value> {
    let mut wire = Vec::new();
    connection
        .take(CONTROL_LIMIT as u64 + 1)
        .read_until(b'\n', &mut wire)
        .await?;
    if wire.len() > CONTROL_LIMIT || wire.last() != Some(&b'\n') {
        return Err(source_error());
    }
    serde_json::from_slice(&wire).map_err(|_| source_error())
}

fn handshake(binding: &TransportBinding) -> Value {
    json!({"protocol": TUI_V2_STATUS_PROTOCOL, "nonce": Uuid::new_v4().to_string(), "account_id": binding.account_id,
        "environment_id": binding.environment_id, "generation": binding.generation,
        "release_id": binding.release_id})
}

fn verify_reply(reply: &Value, proof: &Value) -> io::Result<bool> {
    if !proof
        .as_object()
        .is_some_and(|fields| fields.iter().all(|(key, field)| reply[key] == *field))
        || reply["ready"] != true
    {
        return Err(source_error());
    }
    reply["idle"].as_bool().ok_or_else(source_error)
}

/// 解码仅用于已认领私有提交的完整 OAuth 文件帧。
/// @param headers 受信账号发送头。@return 验证过的原始凭据字节或旧协议空值。
fn oauth_file_payload(headers: &HeaderMap) -> Result<Option<Vec<u8>>, AppError> {
    let mut values = headers.get_all(TUI_OAUTH_FILE).iter();
    let Some(value) = values.next() else {
        return Ok(None);
    };
    if values.next().is_some() || value.len() > TUI_OAUTH_FILE_LIMIT.div_ceil(3) * 4 {
        return Err(invalid_identity());
    }
    let raw = STANDARD
        .decode(value.as_bytes())
        .map_err(|_| invalid_identity())?;
    if raw.len() > TUI_OAUTH_FILE_LIMIT {
        return Err(invalid_identity());
    }
    let file: TuiOAuthFile = serde_json::from_slice(&raw).map_err(|_| invalid_identity())?;
    if !file.valid_format() {
        return Err(invalid_identity());
    }
    Ok(Some(raw))
}

struct VerifiedSource {
    connection: BufReader<UnixStream>,
    proof: Value,
    idle: bool,
    receipt_idle: Option<bool>,
    model_headers: bool,
    model_header_policy: bool,
    capture_http: bool,
    body_policy: bool,
    input_policy: bool,
    agent_scope: bool,
    agent_summary: bool,
    session_mapping: bool,
    title_session_mapping: bool,
    prompt_suggestion: bool,
    managed_oauth: bool,
    oauth_file: bool,
    signature_repair: bool,
    system_prompt_policy: bool,
    direct_https: bool,
}

async fn verify_source(
    path: &Path,
    binding: &TransportBinding,
    action: &str,
    receipt: Option<&TuiReceiptProbe>,
) -> io::Result<VerifiedSource> {
    let mut connection = open(path).await?;
    let proof = handshake(binding);
    let mut control = proof.clone();
    control["action"] = json!(action);
    if let Some(receipt) = receipt {
        control["receipt"] = json!(receipt);
    }
    write_json(&mut connection, &control).await?;
    let reply = read_json(&mut connection).await?;
    let idle = verify_reply(&reply, &proof)?;
    // 旧候选在绑定时声明外部正文交付。当前源只在确认冷导入的预留中声明 CLI 采集。
    if reply["capture_cli_submission_protocol"].as_u64() == Some(1) {
        return Err(source_error());
    }
    Ok(VerifiedSource {
        connection,
        proof,
        idle,
        receipt_idle: reply["receipt_idle"].as_bool(),
        capture_http: reply["capture_http_protocol"].as_u64() == Some(1),
        model_headers: reply["model_headers_protocol"].as_u64() == Some(1),
        model_header_policy: reply["model_header_policy_protocol"].as_u64() == Some(1),
        body_policy: reply["body_policy_protocol"].as_u64() == Some(1),
        input_policy: reply["input_policy_protocol"].as_u64() == Some(1),
        agent_scope: reply["agent_scope_protocol"].as_u64() == Some(1),
        agent_summary: reply["agent_summary_protocol"].as_u64() == Some(1),
        session_mapping: reply["upstream_session_protocol"].as_u64() == Some(1),
        title_session_mapping: reply["title_session_mapping_protocol"].as_u64() == Some(1),
        prompt_suggestion: reply["prompt_suggestion_protocol"].as_u64() == Some(1),
        managed_oauth: reply["managed_oauth_protocol"].as_u64() == Some(1),
        oauth_file: reply["oauth_file_protocol"].as_u64() == Some(1),
        signature_repair: reply["signature_repair_protocol"].as_u64() == Some(1),
        system_prompt_policy: reply["client_system_prompt_policy_protocol"].as_u64() == Some(1),
        direct_https: reply["direct_https_protocol"].as_u64() == Some(1),
    })
}

impl TuiSender {
    /// 仅在已提交的原预留中取走一次写入观察。@param binding 当前已认证绑定。
    /// @param id 内层模型请求的实际尝试 ID。@return 对应的后台快照作业。
    pub(super) fn take_wire_capture(
        &self,
        binding: &TransportBinding,
        id: &str,
    ) -> Option<CaptureJob> {
        let mut book = self.book.lock().unwrap();
        // 首发沿原索引。重试仍由原槽持有，只有已批准的额外尝试可以取走观察。
        let record = if book.contains_key(id) {
            book.get_mut(id)
                .filter(|record| record.repair_attempt.is_none())?
        } else {
            let attempt = Uuid::parse_str(id).ok()?;
            book.values_mut()
                .find(|record| record.repair_attempt == Some(attempt))?
        };
        if record.wire_capture.is_some()
            && matches!(record.phase, Phase::Submitted)
            && record.binding_proof == binding_proof(binding)
        {
            record.wire_capture.take()
        } else {
            None
        }
    }
    /// 使用原预留的期限接收可选采集正文。@param binding 实际绑定。@param headers 私有头。@return 原截止。
    pub(super) fn capture_deadline(
        binding: &TransportBinding,
        headers: &HeaderMap,
    ) -> Result<Instant, AppError> {
        Ok(Identity::decode(headers, binding)?
            .deadlines(binding, now_ms())?
            .0)
    }

    /// 统计仍占用 sender 的准备或发送。@return 当前本机预留数。
    pub(super) fn active(&self) -> u64 {
        let mut book = self.book.lock().unwrap();
        prune(&mut book);
        occupied(&book) as u64
    }

    /// 探测受授权的本机事件源。@param binding 已鉴权账号。@param config 私有源配置。
    /// @param receipt 可选的原回执会话。@return 当前源可验证的账号及单轮空闲状态。
    pub(super) async fn status(
        &self,
        binding: &TransportBinding,
        config: Option<&Value>,
        receipt: Option<&TuiReceiptProbe>,
    ) -> Result<(bool, Option<bool>, bool, bool, bool), TuiV2Unavailable> {
        setting(config).map_err(|_| TuiV2Unavailable::ReadinessConfig)?;
        let deadline = Instant::now() + Duration::from_secs(1);
        timeout_at(
            deadline,
            submission_log::was_consumed(
                &self.submission_storage,
                binding,
                None,
                deadline.into_std(),
            ),
        )
        .await
        .map_err(|_| TuiV2Unavailable::ReadinessLedger)?
        .map_err(|_| TuiV2Unavailable::ReadinessLedger)?;
        let source = timeout_at(
            deadline,
            verify_source(&self.path, binding, "status", receipt),
        )
        .await
        .map_err(|_| TuiV2Unavailable::ReadinessSource)?
        .map_err(|_| TuiV2Unavailable::ReadinessSource)?;
        let inactive = self.active() == 0;
        Ok((
            source.idle && inactive,
            source.receipt_idle.map(|idle| idle && inactive),
            source.agent_summary,
            source.managed_oauth && source.system_prompt_policy,
            source.managed_oauth && source.oauth_file && source.direct_https,
        ))
    }

    fn reserve(
        &self,
        identity: Identity,
        binding: &TransportBinding,
        deadline: Instant,
        replay_until: Instant,
        maximum: usize,
    ) -> Result<(Slot, watch::Receiver<bool>), AppError> {
        let id = identity.reservation_id.clone();
        let ticket = Uuid::new_v4();
        let (cancel, signal) = watch::channel(false);
        {
            let mut book = self.book.lock().unwrap();
            prune(&mut book);
            if book.contains_key(&id) {
                return Err(consumed());
            }
            if book.len() >= MAX_RECORDS {
                return Err(limited());
            }
            // 私有身份已由账号 binding 校验。单个独立握手位让源核对子代理票据；
            // 无权启动的请求在 prepare 被拒，普通队列和工具回执各自保留原额度。
            let probe_used = book
                .values()
                .any(|record| record.agent_probe && !matches!(record.phase, Phase::Closed));
            let agent_probe = !probe_used
                && identity.agent_hint.is_some()
                && !identity.continuation_only
                && !identity.agent_summary;
            let normal_occupied = occupied(&book) - usize::from(probe_used);
            if !agent_probe && normal_occupied >= maximum {
                return Err(limited());
            }
            // 新轮排队或分支借用物理余位时，最后一个传输位置留给已核验的工具续轮。
            if !agent_probe
                && !identity.continuation_only
                && maximum > 1
                && normal_occupied == maximum - 1
            {
                let active = || {
                    book.values().filter(|record| {
                        !record.agent_probe && !matches!(record.phase, Phase::Closed)
                    })
                };
                if active().any(|record| record.fork_borrowed_slot)
                    || active().all(|record| matches!(record.phase, Phase::Preparing))
                {
                    return Err(limited());
                }
            }
            book.insert(
                id.clone(),
                Record {
                    repair_attempt: None,
                    wire_capture: None,
                    identity,
                    agent_probe,
                    fork_borrowed_slot: false,
                    binding_proof: binding_proof(binding),
                    deadline,
                    replay_until,
                    ticket,
                    cancel,
                    phase: Phase::Preparing,
                },
            );
        }
        let weak = Arc::downgrade(&self.book);
        tokio::spawn(async move {
            sleep_until(deadline).await;
            if let Some(book) = weak.upgrade() {
                prune(&mut book.lock().unwrap());
            }
        });
        Ok((
            Slot {
                book: self.book.clone(),
                id,
                ticket,
                armed: true,
            },
            signal,
        ))
    }

    /// 在读取正文前占用名额，并将原始正文发给本地预留端。
    /// @param binding 已鉴权账号。@param config 私有源配置。@param request 内部请求。@return 预留类别。
    pub(super) async fn prepare(
        &self,
        binding: &TransportBinding,
        config: Option<&Value>,
        request: Request,
    ) -> Result<Response, AppError> {
        let identity = Identity::decode(request.headers(), binding)?;
        let mut policy_headers = request.headers().get_all(TUI_BODY_POLICY).iter();
        let policy = policy_headers
            .next()
            .map(|value| {
                if value.as_bytes().len() > 256 || policy_headers.next().is_some() {
                    return Err(invalid_identity());
                }
                serde_json::from_slice::<TuiBodyPolicy>(value.as_bytes())
                    .map_err(|_| invalid_identity())
            })
            .transpose()?;
        let mut system_policy_headers = request.headers().get_all(TUI_SYSTEM_PROMPT_POLICY).iter();
        let system_prompt = system_policy_headers
            .next()
            .map(|value| {
                if system_policy_headers.next().is_some() {
                    return Err(invalid_identity());
                }
                value
                    .to_str()
                    .ok()
                    .and_then(TuiSystemPromptPolicy::parse)
                    .filter(|policy| *policy != TuiSystemPromptPolicy::Append)
                    .ok_or_else(invalid_identity)
            })
            .transpose()?;
        let observe = |stage, result| {
            tui_startup_event(stage, Some(&identity.reservation_id), None, Some(result))
        };
        observe("sender_private_prepare", "entered");
        let (deadline, replay_until) = identity.deadlines(binding, now_ms())?;
        let config = match setting(config) {
            Ok(config) => config,
            Err(error) => {
                observe(TUI_SENDER_CONFIG, "rejected");
                return Ok(stage_response(error, TUI_SENDER_CONFIG));
            }
        };
        let (mut slot, mut cancelled) = self.reserve(
            identity.clone(),
            binding,
            deadline,
            replay_until,
            config.max_reservations,
        )?;
        let capture_requested = tui_projection_marker(request.headers(), TUI_CAPTURE, "1");
        let wire_protocol = tui_projection_marker(request.headers(), TUI_FINAL_CAPTURE, "1");
        let offer_header_policy =
            tui_projection_marker(request.headers(), TUI_MODEL_HEADER_POLICY, "1");
        let repair_requested =
            if tui_projection_marker(request.headers(), TUI_SIGNATURE_REPAIR, "known") {
                Some(true)
            } else if tui_projection_marker(request.headers(), TUI_SIGNATURE_REPAIR, "1") {
                Some(false)
            } else {
                None
            };
        let mut stage = TUI_PREPARE_LEDGER;
        let prepared = async {
            observe(stage, "started");
            if submission_log::was_consumed(
                &self.submission_storage,
                binding,
                Some(&identity.reservation_id),
                deadline.into_std(),
            )
            .await
            .map_err(|_| unavailable())?
            {
                return Err(consumed());
            }
            observe(stage, "confirmed");
            // 先在将承载正文的同一个 socket 核对账号。遇到错绑时连预留信封也不送出。
            stage = TUI_PREPARE_BIND;
            observe(stage, "started");
            let VerifiedSource {
                mut connection,
                proof,
                model_headers,
                model_header_policy,
                capture_http,
                body_policy,
                input_policy,
                agent_scope,
                agent_summary,
                session_mapping,
                title_session_mapping,
                prompt_suggestion,
                managed_oauth,
                oauth_file,
                signature_repair,
                system_prompt_policy,
                direct_https,
                ..
            } = verify_source(&self.path, binding, "bind", None)
                .await
                .map_err(|_| unavailable())?;
            // 双方明确支持原生交付表示才采集。旧控制端继续使用其认识的来源。
            let offer_cli_capture = managed_oauth
                && capture_requested
                && tui_projection_marker(request.headers(), TUI_CLI_SUBMISSION, "1");
            if identity.agent_summary && !agent_summary {
                return Err(unavailable());
            }
            if identity.agent_hint.is_some() && !agent_scope {
                return Err(AppError::TuiInputUnsupported);
            }
            if policy.is_some() && !body_policy {
                return Err(unavailable());
            }
            if system_prompt.is_some() && (!managed_oauth || !system_prompt_policy) {
                return Err(unavailable());
            }
            observe(stage, "confirmed");
            stage = TUI_PREPARE_EXCHANGE;
            observe(stage, "started");
            if identity.session_id.starts_with(SUGGESTION_SESSION_PREFIX)
                && (!prompt_suggestion || identity.continuation_only || identity.agent_hint.is_some())
            {
                return Err(unavailable());
            }
            let model_header_policy = offer_header_policy && model_header_policy && model_headers;
            let option_bytes = if model_headers {
                let mut options = tui_model_headers(request.headers(), model_header_policy)?;
                if tui_projection_marker(request.headers(), TUI_MODEL_ACCEPT_OMITTED, "1") {
                    options.remove("accept");
                }
                (!options.is_empty())
                    .then(|| serde_json::to_vec(&options).expect("版本和功能声明均为字符串"))
            } else {
                None
            };
            let native_input = request
                .headers()
                .get(TUI_INPUT_FORMAT)
                .and_then(|value| value.to_str().ok())
                .filter(|format| {
                    model_headers && matches!(*format, "claude_code" | "claude_code_280")
                })
                .map(str::to_owned);
            let offer_oauth_file = managed_oauth
                && oauth_file
                && tui_projection_marker(request.headers(), TUI_OAUTH_FILE, "1");
            if direct_https && !offer_oauth_file {
                return Err(unavailable());
            }
            let body = to_bytes(request.into_body(), REQUEST_BODY_LIMIT)
                .await
                .map_err(|_| invalid_identity())?;
            if body.is_empty() {
                return Err(invalid_identity());
            }
            let mut control = proof.clone();
            control["action"] = json!("prepare");
            control["reservation"] = json!(identity);
            if managed_oauth {
                control["native_cold_history_protocol"] = json!(1);
                control["receipt_fork_session_protocol"] = json!(1);
            }
            if let Some(policy) = system_prompt {
                control["client_system_prompt_policy"] = json!(policy);
            }
            if offer_oauth_file {
                control["oauth_file_protocol"] = json!(1);
            }
            if direct_https {
                control["direct_https_protocol"] = json!(1);
            }
            control["body_len"] = json!(body.len());
            control["body_sha256"] = json!(hex::encode(Sha256::digest(&body)));
            if let Some(policy) = policy {
                control["body_policy"] = json!(policy);
            }
            if let Some(format) = native_input.as_deref() {
                control["input_format"] = json!(format);
            }
            if model_header_policy {
                control["model_header_policy"] = json!(1);
            }
            if let Some(bytes) = &option_bytes {
                // 独立分段，较长的功能清单也不挤占旧握手的 4KiB 控制帧。
                control["model_headers_len"] = json!(bytes.len());
            }
            write_json(&mut connection, &control)
                .await
                .map_err(|_| unavailable())?;
            connection
                .get_mut()
                .write_all(&body)
                .await
                .map_err(|_| unavailable())?;
            if let Some(bytes) = option_bytes {
                connection
                    .get_mut()
                    .write_all(&bytes)
                    .await
                    .map_err(|_| unavailable())?;
            }
            let reply = read_json(&mut connection)
                .await
                .map_err(|_| unavailable())?;
            verify_reply(&reply, &proof).map_err(|_| unavailable())?;
            let cold = reply["native_cold_history_protocol"].as_u64() == Some(1);
            if cold && !managed_oauth {
                return Err(unavailable());
            }
            let cli_submission =
                (offer_cli_capture && cold).then_some("request_from_interactive_cli");
            let capture_http = capture_http && !cold;
            let signature_repair = signature_repair && !cold;
            let oauth_file = reply["oauth_file_protocol"].as_u64() == Some(1);
            if oauth_file && !offer_oauth_file {
                return Err(unavailable());
            }
            if reply["error"] == "input_rejected" {
                return Err(reply["code"]
                    .as_str()
                    .and_then(tui_input_rejection)
                    .unwrap_or_else(unavailable));
            }
            if reply["error"] == "unsupported_input" {
                return Err(AppError::TuiInputUnsupported);
            }
            if reply["error"] == "capacity" {
                return Err(limited());
            }
            if reply["error"] == "local_provider_backoff" {
                let retry_after = reply["retry_after"].as_u64().ok_or_else(unavailable)?;
                return Err(AppError::TuiProviderBackoff { retry_after });
            }
            if reply["error"] == "subagent_capacity" && identity.agent_hint.is_some() {
                return Err(AppError::TuiSubagentCapacity);
            }
            if reply["error"] == "subagent_ambiguous" && identity.agent_hint.is_some() {
                return Err(AppError::TuiSubagentAmbiguous);
            }
            if reply["error"] == "subagent_binding" && identity.agent_hint.is_some() {
                return Err(invalid_identity());
            }
            let kind = match reply["kind"].as_str() {
                Some("new") if !identity.continuation_only => "new",
                Some("continuation") => "continuation",
                Some("recovered") if identity.continuation_only => "recovered",
                _ => return Err(invalid_identity()),
            };
            if let Some(policy) = system_prompt
                && reply["client_system_prompt_policy"] != policy.as_str()
            {
                return Err(unavailable());
            }
            // 支持绑定的源在准备时仅预留容量，到 send 才获得实际启动目录。
            let branch = match (
                identity.agent_hint.as_ref(),
                reply.get("agent_session"),
                reply.get("receipt_fork_session"),
            ) {
                (None, None, None) => None,
                (Some(_), Some(value), None) if agent_scope => Some(value),
                (None, None, Some(value))
                    if managed_oauth && (cold || native_input.as_deref() == Some("claude_code")) =>
                {
                    Some(value)
                }
                _ => return Err(invalid_identity()),
            };
            let fork_borrowed_slot = match reply.get("receipt_fork_borrowed_slot") {
                None => false,
                Some(Value::Bool(true))
                    if kind == "new" && reply.get("receipt_fork_session").is_some() =>
                {
                    true
                }
                _ => return Err(invalid_identity()),
            };
            let branch = branch
                .map(|value| {
                    value
                        .as_str()
                        .filter(|text| {
                            text.strip_prefix(SERVER_SESSION_PREFIX)
                                .is_some_and(|uuid| {
                                    Uuid::parse_str(uuid).is_ok_and(|id| {
                                        id.get_version_num() == 4 && id.to_string() == uuid
                                    })
                                })
                        })
                        .map(str::to_owned)
                        .ok_or_else(invalid_identity)
                })
                .transpose()?;
            let workspace = match reply.get("workspace_protocol") {
                None if branch.is_none() => None,
                Some(version) if version.as_u64() == Some(1) => {
                    let resume = match reply.get("workspace_resume") {
                        None => false,
                        Some(value) => value.as_bool().ok_or_else(invalid_identity)?,
                    };
                    Some(workspace::Candidate::from_request(
                        &body,
                        kind == "new" && !resume,
                        branch,
                    )?)
                }
                _ => return Err(unavailable()),
            };
            Ok((
                connection,
                kind,
                workspace,
                capture_http,
                cli_submission,
                input_policy,
                model_header_policy,
                session_mapping,
                title_session_mapping,
                managed_oauth,
                oauth_file,
                fork_borrowed_slot,
                if signature_repair {
                    repair_requested
                } else {
                    None
                },
            ))
        };
        let result = tokio::select! {
            biased;
            _ = cancelled.changed() => {
                observe("sender_private_prepare", "cancelled");
                return Err(consumed());
            },
            result = timeout_at(deadline, prepared) => result.unwrap_or_else(|_| Err(limited())),
        };
        let (
            connection,
            kind,
            workspace,
            capture_http,
            cli_submission,
            input_policy,
            model_header_policy,
            session_mapping,
            title_session_mapping,
            managed_oauth,
            oauth_file,
            fork_borrowed_slot,
            signature_repair,
        ) = match result {
            Ok(prepared) => {
                observe(stage, "confirmed");
                prepared
            }
            Err(error @ AppError::ServiceUnavailable(_)) => {
                observe(stage, "failed");
                return Ok(stage_response(error, stage));
            }
            Err(error) => {
                observe(stage, "rejected");
                return Err(error);
            }
        };
        let mut book = self.book.lock().unwrap();
        let record = book
            .get_mut(&slot.id)
            .filter(|record| {
                record.ticket == slot.ticket
                    && matches!(record.phase, Phase::Preparing)
                    && !*record.cancel.borrow()
                    && record.deadline > Instant::now()
            })
            .ok_or_else(consumed)?;
        record.fork_borrowed_slot = fork_borrowed_slot;
        record.phase = Phase::Ready {
            connection,
            workspace,
            session_mapping,
            managed_oauth,
            oauth_file,
            signature_repair,
            cli_submission,
        };
        slot.armed = false;
        observe("sender_private_prepare", "accepted");
        let mut response = (StatusCode::NO_CONTENT, [(HANDOFF_HEADER, kind)]).into_response();
        if identity.session_id.starts_with(SUGGESTION_SESSION_PREFIX) {
            response.headers_mut().insert(TUI_PROMPT_SUGGESTION, HeaderValue::from_static("1"));
        }
        if input_policy {
            response
                .headers_mut()
                .insert(TUI_INPUT_POLICY, HeaderValue::from_static("1"));
        }
        if model_header_policy {
            response
                .headers_mut()
                .insert(TUI_MODEL_HEADER_POLICY, HeaderValue::from_static("1"));
        }
        if session_mapping {
            response
                .headers_mut()
                .insert(TUI_UPSTREAM_SESSION, HeaderValue::from_static("1"));
        }
        if session_mapping && title_session_mapping {
            response
                .headers_mut()
                .insert(TUI_TITLE_SESSION_MAPPING, HeaderValue::from_static("1"));
        }
        if managed_oauth {
            response
                .headers_mut()
                .insert(TUI_MANAGED_OAUTH, HeaderValue::from_static("1"));
        }
        if oauth_file {
            response
                .headers_mut()
                .insert(TUI_OAUTH_FILE, HeaderValue::from_static("1"));
        }
        if signature_repair.is_some() {
            response
                .headers_mut()
                .insert(TUI_SIGNATURE_REPAIR, HeaderValue::from_static("1"));
        }
        if capture_requested && (capture_http || cli_submission.is_some()) {
            if wire_protocol && cli_submission.is_none() {
                response
                    .headers_mut()
                    .insert(TUI_FINAL_CAPTURE, HeaderValue::from_static("1"));
            }
            response
                .headers_mut()
                .insert(TUI_CAPTURE, HeaderValue::from_static("1"));
        }
        if policy.is_some() {
            response
                .headers_mut()
                .insert(TUI_BODY_POLICY, HeaderValue::from_static("1"));
        }
        if system_prompt.is_some() {
            response
                .headers_mut()
                .insert(TUI_SYSTEM_PROMPT_POLICY, HeaderValue::from_static("1"));
        }
        Ok(response)
    }

    fn claim(
        &self,
        binding: &TransportBinding,
        identity: &Identity,
        requires_session_mapping: bool,
        has_account_token: bool,
        has_oauth_file: bool,
    ) -> Result<
        (
            Slot,
            BufReader<UnixStream>,
            Option<workspace::Candidate>,
            Option<bool>,
            Option<&'static str>,
        ),
        AppError,
    > {
        let mut book = self.book.lock().unwrap();
        prune(&mut book);
        let record = book
            .get_mut(&identity.reservation_id)
            .ok_or_else(consumed)?;
        if record.identity != *identity || record.binding_proof != binding_proof(binding) {
            return Err(invalid_identity());
        }
        let Phase::Ready {
            session_mapping,
            managed_oauth,
            oauth_file,
            ..
        } = &record.phase
        else {
            return Err(consumed());
        };
        if (requires_session_mapping && !session_mapping)
            || *managed_oauth != (has_account_token || has_oauth_file)
            || *oauth_file != has_oauth_file
            || (has_account_token && has_oauth_file)
        {
            return Err(unavailable());
        }
        let Phase::Ready {
            connection,
            workspace,
            signature_repair,
            cli_submission,
            ..
        } = std::mem::replace(&mut record.phase, Phase::Submitted)
        else {
            unreachable!()
        };
        Ok((
            Slot {
                book: self.book.clone(),
                id: identity.reservation_id.clone(),
                ticket: record.ticket,
                armed: true,
            },
            connection,
            workspace,
            signature_repair,
            cli_submission,
        ))
    }

    /// 单次认领原 socket 并按需交付真实字节。@param binding 已鉴权账号。
    /// @param config 私有源配置。@param headers 原预留信封。@return 事件源的内容类型和流。
    pub(super) async fn send(
        &self,
        binding: &TransportBinding,
        config: Option<&Value>,
        headers: &HeaderMap,
        capture: Option<(PathBuf, TuiCaptureInput)>,
    ) -> Result<Response, AppError> {
        let identity = Identity::decode(headers, binding)?;
        let reservation_id = identity.reservation_id.clone();
        let observe = |stage, result| tui_startup_event(stage, Some(&reservation_id), None, Some(result));
        observe("sender_private_send", "entered");
        let (deadline, _) = identity.deadlines(binding, now_ms())?;
        if let Err(error) = setting(config) {
            return Ok(stage_response(error, TUI_SENDER_CONFIG));
        }
        let mut session_headers = headers.get_all(TUI_UPSTREAM_SESSION).iter();
        let upstream_session = session_headers
            .next()
            .map(|value| {
                let value = value.to_str().map_err(|_| invalid_identity())?;
                let original = auxiliary_original_session(&identity.session_id)
                    .unwrap_or(&identity.session_id);
                if session_headers.next().is_some()
                    || value.len() != 36
                    || Uuid::parse_str(value).is_err()
                    || original.len() != 36
                    || Uuid::parse_str(original).is_err()
                {
                    return Err(invalid_identity());
                }
                Ok(value)
            })
            .transpose()?;
        let mut token_headers = headers.get_all(TUI_MANAGED_OAUTH).iter();
        let account_token = token_headers
            .next()
            .map(|value| {
                let token = value.to_str().map_err(|_| invalid_identity())?;
                if token_headers.next().is_some() || !valid_tui_account_token(token) {
                    return Err(invalid_identity());
                }
                Ok(token)
            })
            .transpose()?;
        let oauth_file = oauth_file_payload(headers)?;
        observe("sender_send_claim", "started");
        let (slot, mut connection, workspace, signature_repair, cli_submission) = match self.claim(
            binding,
            &identity,
            upstream_session.is_some(),
            account_token.is_some(),
            oauth_file.is_some(),
        ) {
            Ok(claimed) => {
                observe("sender_send_claim", "accepted");
                claimed
            }
            Err(error @ AppError::ServiceUnavailable(_)) => {
                observe("sender_send_claim", "rejected");
                return Ok(stage_response(error, TUI_SEND_CLAIM));
            }
            Err(error) => {
                observe("sender_send_claim", "rejected");
                return Err(error);
            }
        };
        // 先同步提交事实。进程退出或回包丢失后，重放的 prepare 与 send 仍无法触发第二次提交。
        observe("sender_submission_ledger", "started");
        let committed = timeout_at(
            deadline,
            submission_log::consume(
                &self.submission_storage,
                binding,
                &identity.reservation_id,
                identity.deadline_unix_ms,
                deadline.into_std(),
                submission_log::Terminal::Submitted,
            ),
        )
        .await
        .unwrap_or_else(|_| Err(io::ErrorKind::TimedOut.into()));
        let committed = match committed {
            Ok(committed) => {
                observe("sender_submission_ledger", if committed { "committed" } else { "already_consumed" });
                committed
            }
            Err(error) => {
                observe("sender_submission_ledger", if error.kind() == io::ErrorKind::TimedOut { "deadline" } else { "failed" });
                let error = match error.kind() {
                    io::ErrorKind::TimedOut => limited(),
                    kind => {
                        tracing::warn!(
                            account_id = binding.account_id,
                            reservation_id = %identity.reservation_id,
                            ?kind,
                            "V2 发送前写入提交账本失败"
                        );
                        unavailable()
                    }
                };
                // 账本失败时尚未向事件源发送 send，网关可以安全归还原工具回执。
                return Ok(stage_response(error, TUI_SUBMISSION_LEDGER));
            }
        };
        if !committed {
            return Err(consumed());
        }
        if Instant::now() >= deadline {
            return Err(limited());
        }
        let mut command = json!({"action": "send", "reservation_id": identity.reservation_id});
        if let Some(upstream_session) = upstream_session {
            command["upstream_session_id"] = json!(upstream_session);
        }
        if let Some(token) = account_token {
            command["account_token"] = json!(token);
        }
        if let Some(file) = &oauth_file {
            command["oauth_file_len"] = json!(file.len());
        }
        // 两种受管凭据都交给账号发送器。私有凭据帧不属于采集正文。
        let managed_oauth = account_token.is_some() || oauth_file.is_some();
        let mut capture = capture.and_then(|(directory, input)| {
            let id = Uuid::parse_str(&identity.reservation_id).ok()?;
            Some((directory, input, identity.account_id, id, tui_writer()?))
        });
        let retry_capture = capture.as_ref().and_then(|(dir, input, account, _, _)| {
            signature_repair
                .is_some()
                .then(|| (dir.clone(), input.clone(), *account))
        });
        let wire_protocol =
            cli_submission.is_none() && tui_projection_marker(headers, TUI_FINAL_CAPTURE, "1");
        let wire_captured = if managed_oauth && wire_protocol {
            capture
                .take()
                .is_some_and(|(directory, input, _, _, permit)| {
                    slot.install_wire_capture(CaptureJob {
                        directory,
                        input,
                        permit,
                    })
                })
        } else {
            false
        };
        if wire_captured {
            command["capture_assembly"] = json!(true);
        }
        if capture.is_some() {
            if cli_submission.is_some() {
                command["capture_cli_submission"] = json!(true);
            } else {
                command["capture_http"] = json!(true);
            }
        }
        if let Some(known) = signature_repair {
            command["signature_repair"] = json!(known);
        }
        let options = SourceOptions {
            projection: ResponseProjection::from_headers(headers),
            managed: managed_oauth,
            oauth_file: oauth_file.is_some(),
            wire: wire_protocol,
            cli_submission,
            captured: capture.is_some() || wire_captured,
        };
        if let Some(candidate) = workspace {
            observe("sender_workspace_bind", "started");
            let root = self.submission_storage.clone();
            let launch = tokio::task::spawn_blocking(move || candidate.bind(&root, &identity));
            let resolved = timeout_at(deadline, async { launch.await.map_err(|_| unavailable())? })
                .await
                .unwrap_or_else(|_| Err(limited()));
            command["workspace"] = match resolved {
                Ok(workspace) if Instant::now() < deadline => {
                    observe("sender_workspace_bind", "bound");
                    workspace
                }
                Ok(_) => {
                    observe("sender_workspace_bind", "deadline");
                    return Ok(stage_response(limited(), TUI_WORKSPACE_BIND));
                }
                Err(error @ AppError::ServiceUnavailable(_))
                | Err(error @ AppError::AdmissionLimited { .. }) => {
                    observe("sender_workspace_bind", if matches!(error, AppError::AdmissionLimited { .. }) { "deadline" } else { "failed" });
                    // 预留已认领，但事件源还没收到 send。网关可以归还原回执。
                    return Ok(stage_response(error, TUI_WORKSPACE_BIND));
                }
                Err(error) => {
                    observe("sender_workspace_bind", "rejected");
                    return Err(error);
                }
            };
        } else {
            observe("sender_workspace_bind", "skipped");
        }
        observe("sender_unix_send", "started");
        let reply = timeout(IO_TIMEOUT, async {
            write_json(&mut connection, &command).await?;
            if let Some(file) = &oauth_file {
                connection.get_mut().write_all(file).await?;
            }
            read_initial_reply(&mut connection, signature_repair, managed_oauth).await
        })
        .await
        .ok()
        .and_then(Result::ok)
        .ok_or_else(|| AppError::BadGateway("V2 本机事件源提交结果待核对".into()))?;
        let (head, repaired) = match reply {
            SourceReply::Final { head, repaired } => (head, repaired),
            SourceReply::Signature(offer) => {
                return self.pause_for_signature_repair(
                    slot,
                    connection,
                    offer,
                    capture,
                    retry_capture,
                    options,
                    deadline,
                );
            }
        };
        let mut response = Self::source_response(head, connection, slot, capture, options).await?;
        if repaired {
            response
                .headers_mut()
                .insert(TUI_SIGNATURE_REPAIR, HeaderValue::from_static("applied"));
        }
        Ok(response)
    }

    fn pause_for_signature_repair(
        &self,
        slot: Slot,
        mut connection: BufReader<UnixStream>,
        offer: SignatureOffer,
        capture: Option<Capture>,
        retry_capture: Option<(PathBuf, TuiCaptureInput, i64)>,
        options: SourceOptions,
        deadline: Instant,
    ) -> Result<Response, AppError> {
        let (permit, wait) = oneshot::channel::<RepairPermit>();
        {
            let mut book = self.book.lock().unwrap();
            let record = book
                .get_mut(&slot.id)
                .filter(|record| {
                    record.ticket == slot.ticket && matches!(record.phase, Phase::Submitted)
                })
                .ok_or_else(consumed)?;
            record.phase = Phase::RepairPending(permit);
        }
        let SignatureOffer {
            source,
            rejection,
            repaired,
            capture: first,
        } = offer;
        let mut response = (
            StatusCode::BAD_REQUEST,
            [(CONTENT_TYPE, "application/json")],
            rejection,
        )
            .into_response();
        response
            .headers_mut()
            .insert(TUI_SIGNATURE_REPAIR, HeaderValue::from_static("pending"));
        response
            .headers_mut()
            .insert(TUI_ERROR_SOURCE, HeaderValue::from_static(source));
        if options.projection.json {
            response.headers_mut().insert(
                TUI_GATEWAY_ID_HEADER,
                HeaderValue::from_static(TUI_JSON_PROJECTION_V1),
            );
        }
        let first_capture = if let (Some(capture), Some((pairs, raw))) = (capture, first) {
            save_provider_capture(capture, pairs, raw, options);
            true
        } else {
            options.wire && options.managed && options.captured
        };
        if first_capture {
            response
                .headers_mut()
                .insert(TUI_CAPTURE, HeaderValue::from_static("queued"));
        }
        // 许可送达前由同一任务持有原连接、进程和活动位。取消与过期使用同一收口。
        tokio::spawn(async move {
            let Ok(Ok(permit)) = timeout_at(deadline, wait).await else {
                let _ = timeout_at(deadline, write_repair_body(&mut connection, None, None)).await;
                return;
            };
            let RepairPermit {
                attempt,
                projection,
                response,
            } = permit;
            if Instant::now() >= deadline || response.is_closed() {
                let _ = timeout_at(deadline, write_repair_body(&mut connection, None, None)).await;
                let _ = response.send(Ok(repair_declined()));
                return;
            }
            let result = async {
                let mut capture = retry_capture.and_then(|(directory, input, account)| {
                    Some((directory, input, account, attempt, tui_writer()?))
                });
                let captured = if options.managed && options.wire {
                    capture
                        .take()
                        .is_some_and(|(directory, input, _, _, permit)| {
                            slot.install_wire_capture(CaptureJob {
                                directory,
                                input,
                                permit,
                            })
                        })
                } else {
                    capture.is_some()
                };
                let head = timeout_at(deadline, async {
                    write_repair_body(&mut connection, Some(&repaired), Some(attempt)).await?;
                    read_json(&mut connection).await
                })
                .await
                .ok()
                .and_then(Result::ok)
                .ok_or_else(|| AppError::BadGateway("V2 签名修复提交状态未知".into()))?;
                let attempt_id = attempt.to_string();
                if head["repair_attempt_id"] != attempt_id {
                    // 许可送达后，原进程或冻结凭据仍可能在写出前失效，来源此时交回首个拒绝。
                    if head["repair_attempt_id"].is_null() && head["status"] == 400 {
                        return Ok(repair_declined());
                    }
                    return Err(AppError::BadGateway("V2 签名修复缺少可核验的回包".into()));
                }
                let mut result = Self::source_response(
                    head,
                    connection,
                    slot,
                    capture,
                    SourceOptions {
                        projection,
                        captured,
                        ..options
                    },
                )
                .await?;
                result.headers_mut().insert(
                    TUI_REPAIR_ATTEMPT,
                    HeaderValue::from_str(&attempt_id).expect("UUID 可编码为头值"),
                );
                Ok(result)
            }
            .await;
            let _ = response.send(result);
        });
        Ok(response)
    }

    /// 消费同一预留的额外发送许可。@param binding 当前受信绑定。@param headers 原预留和实际尝试。
    /// @return 原轮的恢复响应，等待已失效时明确拒绝。
    pub(super) async fn repair(
        &self,
        binding: &TransportBinding,
        headers: &HeaderMap,
    ) -> Result<Response, AppError> {
        let identity = Identity::decode(headers, binding)?;
        let mut ids = headers.get_all(TUI_REPAIR_ATTEMPT).iter();
        let id = ids
            .next()
            .and_then(|id| id.to_str().ok())
            .ok_or_else(invalid_identity)?;
        let attempt = Uuid::parse_str(id).map_err(|_| invalid_identity())?;
        if ids.next().is_some() || attempt.to_string() != id || id == identity.reservation_id {
            return Err(invalid_identity());
        }
        let permit = {
            let mut book = self.book.lock().unwrap();
            let duplicate_attempt = book.contains_key(id)
                || book
                    .values()
                    .any(|record| record.repair_attempt == Some(attempt));
            let Some(record) = book.get_mut(&identity.reservation_id) else {
                return Ok(repair_declined());
            };
            if record.identity != identity || record.binding_proof != binding_proof(binding) {
                return Err(invalid_identity());
            }
            if record.deadline <= Instant::now() || !matches!(record.phase, Phase::RepairPending(_))
            {
                return Ok(repair_declined());
            }
            if duplicate_attempt {
                return Err(invalid_identity());
            }
            let Phase::RepairPending(permit) =
                std::mem::replace(&mut record.phase, Phase::Submitted)
            else {
                unreachable!()
            };
            record.repair_attempt = Some(attempt);
            permit
        };
        let (response, wait) = oneshot::channel();
        if permit
            .send(RepairPermit {
                attempt,
                projection: ResponseProjection::from_headers(headers),
                response,
            })
            .is_err()
        {
            return Ok(repair_declined());
        }
        wait.await
            .map_err(|_| AppError::BadGateway("V2 签名修复提交状态未知".into()))?
    }

    async fn source_response(
        head: Value,
        connection: BufReader<UnixStream>,
        slot: Slot,
        capture: Option<Capture>,
        options: SourceOptions,
    ) -> Result<Response, AppError> {
        let status = head["status"]
            .as_u64()
            .and_then(|status| u16::try_from(status).ok())
            .and_then(|status| StatusCode::from_u16(status).ok())
            .filter(|status| {
                *status == StatusCode::OK || status.is_client_error() || status.is_server_error()
            })
            .ok_or_else(|| AppError::BadGateway("V2 本机事件源响应状态无效".into()))?;
        let content_type = match head["content_type"].as_str() {
            Some("text/event-stream") => "text/event-stream",
            Some("application/json") => "application/json",
            _ => return Err(AppError::BadGateway("V2 本机事件源内容类型无效".into())),
        };
        // 省略此字段是旧协议。显式声明必须能核验，以免未知模式静默退回原字节。
        let gateway_ids = match head.get("message_id_mode") {
            None => false,
            Some(Value::String(mode)) if mode == "gateway" => true,
            Some(_) => {
                return Err(AppError::BadGateway("V2 本机事件源消息 ID 模式无效".into()));
            }
        };
        let body = Body::from_stream(unfold(
            Some((connection, slot, capture)),
            move |state| async move {
                let (mut connection, slot, capture) = state?;
                let chunk = timeout(IO_TIMEOUT, read_chunk(&mut connection))
                    .await
                    .unwrap_or_else(|_| Err(source_error()));
                match chunk {
                    Ok(Some(bytes)) => Some((Ok(bytes), Some((connection, slot, capture)))),
                    Ok(None) => {
                        if let Some(capture) = capture {
                            let (_, _, account, id, _) = &capture;
                            let (account, id) = (*account, *id);
                            tokio::spawn(async move {
                                match timeout(IO_TIMEOUT, read_capture_footer(&mut connection))
                                    .await
                                {
                                    Ok(Ok((pairs, raw))) => {
                                        save_provider_capture(capture, pairs, raw, options)
                                    }
                                    _ => {
                                        tracing::warn!(account_id=account, attempt_id=%id, "V2 提供方请求缺少已提交观察")
                                    }
                                }
                            });
                        }
                        None
                    }
                    Err(error) => Some((Err(error), None)),
                }
            },
        ));
        if !gateway_ids {
            return Ok((status, [(CONTENT_TYPE, content_type)], body).into_response());
        }
        // 分开协商 JSON 和 SSE，使旧 Gateway 仍收到它接受的投影格式。
        let (mut response, mode) = if content_type == "application/json" && options.projection.json
        {
            (
                (status, [(CONTENT_TYPE, content_type)], body).into_response(),
                TUI_JSON_PROJECTION_V1,
            )
        } else if content_type == "text/event-stream" && options.projection.sse {
            (
                (status, [(CONTENT_TYPE, content_type)], body).into_response(),
                TUI_SSE_PROJECTION_V1,
            )
        } else {
            (
                tui_sender_response::project(status, content_type, body).await,
                "gateway",
            )
        };
        response
            .headers_mut()
            .insert(TUI_GATEWAY_ID_HEADER, HeaderValue::from_static(mode));
        if status.is_success() {
            if let Some(source) = head["body_source"].as_str().and_then(TuiBodySource::from_wire) {
                response
                    .headers_mut()
                    .insert(TUI_BODY_SOURCE, HeaderValue::from_static(source.as_str()));
                if options.managed
                    && source == TuiBodySource::InteractiveCli
                    && status == StatusCode::OK
                    && content_type == "text/event-stream"
                    && head["opening_usage_placeholder"].as_bool() == Some(true)
                {
                    response
                        .headers_mut()
                        .insert(TUI_OPENING_USAGE_PLACEHOLDER, HeaderValue::from_static("1"));
                }
            }
            if let Some(origin) = head["session_origin"]
                .as_str()
                .and_then(TuiSessionOrigin::from_wire)
            {
                response
                    .headers_mut()
                    .insert(TUI_SESSION_ORIGIN, HeaderValue::from_static(origin.as_str()));
            }
            if let Some(location) = head["instruction_location"]
                .as_str()
                .and_then(TuiInstructionLocation::from_wire)
            {
                response.headers_mut().insert(
                    TUI_INSTRUCTION_LOCATION,
                    HeaderValue::from_static(location.as_str()),
                );
            }
        }
        if options.captured {
            response
                .headers_mut()
                .insert(TUI_CAPTURE, HeaderValue::from_static("queued"));
        }
        // 只采信已绑定源的私有控制帧；不从入站头、错误正文或任意模型扩展提取等待期。
        if !status.is_success() && content_type == "application/json" {
            let origin = match head["error_source"].as_str() {
                Some("local_provider_http") => Some("local_provider_http"),
                Some("managed_oauth_http") if options.managed => Some("managed_oauth_http"),
                Some("oauth_file_before_model")
                    if options.oauth_file && status == StatusCode::SERVICE_UNAVAILABLE =>
                {
                    Some("oauth_file_before_model")
                }
                Some("local_provider_backoff") if status == StatusCode::TOO_MANY_REQUESTS => {
                    Some("local_provider_backoff")
                }
                Some(TUI_CLI_INPUT_GUARD) if status == StatusCode::UNPROCESSABLE_ENTITY => {
                    Some(TUI_CLI_INPUT_GUARD)
                }
                Some("local_provider_event") => Some("local_provider_event"),
                _ => None,
            };
            if let Some(origin) = origin {
                response
                    .headers_mut()
                    .insert(TUI_ERROR_SOURCE, HeaderValue::from_static(origin));
                if status == StatusCode::TOO_MANY_REQUESTS
                    && origin != "local_provider_event"
                    && let Some(seconds) = head["retry_after"].as_u64()
                {
                    response
                        .headers_mut()
                        .insert(RETRY_AFTER, HeaderValue::from(seconds));
                }
            }
        }
        // 额度跟随同一次受管预留。开发提供方和本机合成的限流回复都不具备该归属。
        if options.managed
            && (status == StatusCode::OK
                || status == StatusCode::TOO_MANY_REQUESTS
                    && tui_projection_marker(
                        response.headers(),
                        TUI_ERROR_SOURCE,
                        "managed_oauth_http",
                    ))
            && let Some(quota) = head["quota_headers"].as_object()
        {
            for (name, value) in quota {
                if is_passive_usage_header(name)
                    && let Ok(name) = HeaderName::from_bytes(name.as_bytes())
                    && let Some(value) = value
                        .as_str()
                        .and_then(|value| HeaderValue::from_str(value).ok())
                {
                    response.headers_mut().insert(name, value);
                }
            }
        }
        Ok(response)
    }

    /// 在确认回复前持久化取消。@param binding 已鉴权账号。@param headers 原预留信封。@return HTTP 204。
    pub(super) async fn cancel(
        &self,
        binding: &TransportBinding,
        headers: &HeaderMap,
    ) -> Result<StatusCode, AppError> {
        let identity = Identity::decode(headers, binding)?;
        let proof = binding_proof(binding);
        let wall_now = now_ms();
        let deadlines = (identity.deadline_unix_ms > wall_now)
            .then(|| identity.deadlines(binding, wall_now))
            .transpose()?;
        {
            let mut book = self.book.lock().unwrap();
            prune(&mut book);
            if let Some(record) = book.get_mut(&identity.reservation_id) {
                if record.identity != identity || record.binding_proof != proof {
                    return Err(invalid_identity());
                }
                match record.phase {
                    Phase::Preparing => {
                        record.cancel.send_replace(true);
                    }
                    Phase::Ready { .. } => record.phase = Phase::Closed,
                    // 关闭决定信道，由等待任务回收原连接和容量。
                    Phase::RepairPending(_) => record.phase = Phase::Submitted,
                    _ => {}
                }
            } else if let Some((deadline, replay_until)) = deadlines {
                if book.len() >= MAX_RECORDS {
                    return Err(limited());
                }
                // 取消可能先到。先封住本进程，再在共享记录中与发送竞争终态。
                book.insert(
                    identity.reservation_id.clone(),
                    Record {
                        repair_attempt: None,
                        wire_capture: None,
                        identity: identity.clone(),
                        agent_probe: false,
                        fork_borrowed_slot: false,
                        binding_proof: proof,
                        deadline,
                        replay_until,
                        ticket: Uuid::new_v4(),
                        cancel: watch::channel(true).0,
                        phase: Phase::Closed,
                    },
                );
            }
        }
        if let Some((_, replay_until)) = deadlines {
            // 已记录发送仍返回幂等取消回执，原流继续运行。
            timeout_at(
                replay_until,
                submission_log::consume(
                    &self.submission_storage,
                    binding,
                    &identity.reservation_id,
                    identity.deadline_unix_ms,
                    replay_until.into_std(),
                    submission_log::Terminal::Cancelled,
                ),
            )
            .await
            .map_err(|_| limited())?
            .map_err(|_| unavailable())?;
        }
        Ok(StatusCode::NO_CONTENT)
    }
}

fn repair_declined() -> Response {
    (StatusCode::CONFLICT, [(TUI_SIGNATURE_REPAIR, "declined")]).into_response()
}

fn save_provider_capture(
    capture: Capture,
    pairs: Vec<(String, String)>,
    raw: Vec<u8>,
    options: SourceOptions,
) {
    let (directory, input, account, attempt, permit) = capture;
    tokio::task::spawn_blocking(move || {
        let _permit = permit;
        let format = if let Some(format) = options.cli_submission {
            format
        } else if options.managed {
            "request_to_account_sender"
        } else {
            "http_request_written_to_loopback_provider"
        };
        if input
            .save(
                &directory,
                account,
                attempt,
                pairs,
                raw,
                format,
                !options.wire && options.cli_submission.is_none(),
                None,
            )
            .is_err()
        {
            tracing::warn!(account_id=account, attempt_id=%attempt, "V2 提供方请求采集未保存");
        }
    });
}

async fn read_sized_field(
    connection: &mut BufReader<UnixStream>,
    field: &Value,
    limit: usize,
) -> io::Result<Vec<u8>> {
    let size = field
        .as_u64()
        .and_then(|size| usize::try_from(size).ok())
        .filter(|size| *size <= limit)
        .ok_or_else(source_error)?;
    let mut bytes = vec![0; size];
    connection.read_exact(&mut bytes).await?;
    Ok(bytes)
}

async fn write_repair_body(
    connection: &mut BufReader<UnixStream>,
    body: Option<&[u8]>,
    attempt: Option<Uuid>,
) -> io::Result<()> {
    let mut head = json!({"body_len": body.map_or(0, <[u8]>::len)});
    if let Some(attempt) = attempt {
        head["attempt_id"] = json!(attempt.to_string());
    }
    write_json(connection, &head).await?;
    if let Some(body) = body {
        connection.get_mut().write_all(body).await?;
    }
    Ok(())
}

async fn read_initial_reply(
    connection: &mut BufReader<UnixStream>,
    repair: Option<bool>,
    managed_oauth: bool,
) -> io::Result<SourceReply> {
    let mut head = read_json(connection).await?;
    let mut repaired = false;
    if head["signature_repair"] == "known" {
        if repair != Some(true) {
            return Err(source_error());
        }
        let raw = read_sized_field(connection, &head["body_len"], REQUEST_BODY_LIMIT).await?;
        let updated = repair_body(&raw).filter(|body| body.len() <= REQUEST_BODY_LIMIT);
        repaired = updated.is_some();
        write_repair_body(connection, updated.as_deref(), None).await?;
        head = read_json(connection).await?;
    }
    if head["signature_repair"] != "rejected" {
        return Ok(SourceReply::Final { head, repaired });
    }
    if repair.is_none() {
        return Err(source_error());
    }
    let source = if managed_oauth {
        "managed_oauth_http"
    } else {
        "local_provider_http"
    };
    if head["error_source"] != source {
        return Err(source_error());
    }
    let raw = read_sized_field(connection, &head["body_len"], REQUEST_BODY_LIMIT).await?;
    let rejection =
        read_sized_field(connection, &head["error_len"], SIGNATURE_ERROR_BODY_LIMIT).await?;
    let headers =
        read_sized_field(connection, &head["capture_headers_len"], REQUEST_BODY_LIMIT).await?;
    let policy_refusal = serde_json::from_slice(&rejection)
        .ok()
        .as_ref()
        .and_then(session_policy_block::classify)
        .is_some();
    if !policy_refusal
        && is_signature_rejection(&rejection)
        && let Some(repaired) = repair_body(&raw).filter(|body| body.len() <= REQUEST_BODY_LIMIT)
    {
        return Ok(SourceReply::Signature(SignatureOffer {
            source,
            rejection,
            repaired,
            capture: serde_json::from_slice(&headers)
                .ok()
                .map(|pairs| (pairs, raw)),
        }));
    }
    // 仅明确拒绝且可降级的正文才暂停原轮，其他错误由来源沿原路径交付。
    write_repair_body(connection, None, None).await?;
    let head = read_json(connection).await?;
    Ok(SourceReply::Final { head, repaired })
}

/// 从同一次已鉴权发送的正文结束符后读取独立采集，保持首帧和终帧实时交付。
async fn read_capture_footer(
    connection: &mut BufReader<UnixStream>,
) -> io::Result<(Vec<(String, String)>, Vec<u8>)> {
    let headers_len = connection.read_u32().await? as usize;
    let body_len = connection.read_u32().await? as usize;
    if headers_len > REQUEST_BODY_LIMIT || body_len == 0 || body_len > REQUEST_BODY_LIMIT {
        return Err(source_error());
    }
    let mut header = vec![0; headers_len];
    connection.read_exact(&mut header).await?;
    let headers = serde_json::from_slice(&header)?;
    let mut body = vec![0; body_len];
    connection.read_exact(&mut body).await?;
    Ok((headers, body))
}

async fn read_chunk(connection: &mut BufReader<UnixStream>) -> io::Result<Option<Bytes>> {
    let size = connection.read_u32().await? as usize;
    if size == 0 {
        return Ok(None);
    }
    if size > CHUNK_LIMIT {
        return Err(source_error());
    }
    let mut bytes = vec![0; size];
    connection.read_exact(&mut bytes).await?;
    Ok(Some(Bytes::from(bytes)))
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::fs::{Permissions, create_dir, remove_dir_all, set_permissions};
    use std::os::unix::fs::PermissionsExt;

    use http_body_util::BodyExt;
    use tokio::net::UnixListener;
    use tokio::sync::oneshot;

    struct Source {
        sender: TuiSender,
        listener: UnixListener,
        binding: TransportBinding,
        config: Value,
    }

    impl Source {
        fn new() -> Self {
            let folder = std::env::temp_dir().join(format!("tui-{}", Uuid::new_v4()));
            create_dir(&folder).unwrap();
            set_permissions(&folder, Permissions::from_mode(0o700)).unwrap();
            let path = folder.join("events.sock");
            let listener = UnixListener::bind(&path).unwrap();
            set_permissions(&path, Permissions::from_mode(0o600)).unwrap();
            let binding = TransportBinding {
                account_id: 42,
                environment_id: "d".repeat(32),
                generation: 5,
                endpoint: "http://localhost:8091".into(),
                secret: "synthetic-binding".repeat(3),
                release_id: "test-release".into(),
            };
            Self {
                sender: TuiSender {
                    path,
                    submission_storage: folder,
                    book: Book::default(),
                },
                listener,
                binding,
                config: json!({"max_reservations": 1}),
            }
        }

        fn identity(&self) -> Identity {
            Identity {
                account_id: self.binding.account_id,
                environment_id: self.binding.environment_id.clone(),
                generation: self.binding.generation,
                principal_id: 91,
                session_id: "test-session".into(),
                reservation_id: Uuid::new_v4().to_string(),
                deadline_unix_ms: now_ms() + 30_000,
                continuation_only: false,
                agent_summary: false,
                agent_hint: None,
            }
        }

        async fn prepare(
            &self,
            identity: &Identity,
            body: &'static [u8],
        ) -> Result<Response, AppError> {
            let request = Request::builder()
                .header(RESERVATION_HEADER, header(identity))
                .body(Body::from(body))
                .unwrap();
            self.sender
                .prepare(&self.binding, Some(&self.config), request)
                .await
        }

        async fn send(&self, identity: &Identity) -> Result<Response, AppError> {
            self.sender
                .send(&self.binding, Some(&self.config), &headers(identity), None)
                .await
        }

        async fn cancel(&self, identity: &Identity) -> Result<StatusCode, AppError> {
            self.sender.cancel(&self.binding, &headers(identity)).await
        }

        async fn receive(&self, action: &str) -> (BufReader<UnixStream>, Value) {
            let (connection, _) = self.listener.accept().await.unwrap();
            let mut connection = BufReader::new(connection);
            let mut control = read_json(&mut connection).await.unwrap();
            if action == "prepare" {
                assert_eq!(control["action"], "bind");
                assert!(control.get("reservation").is_none() && control.get("body_len").is_none());
                let nonce = control["nonce"].clone();
                control["signature_repair_protocol"] = json!(1);
                control["ready"] = json!(true);
                control["idle"] = json!(false);
                write_json(&mut connection, &control).await.unwrap();
                control = read_json(&mut connection).await.unwrap();
                assert_eq!(control["nonce"], nonce);
            }
            assert_eq!(control["action"], action);
            control.as_object_mut().unwrap().remove("action");
            control["ready"] = json!(true);
            control["idle"] = json!(false);
            (connection, control)
        }
    }

    /// 明确拒绝在原连接等待许可。取消和重复控制都遵守同一预留的单次认领。
    #[tokio::test]
    async fn signature_repair_retains_original_source_until_resolution() {
        let source = Source::new();
        let raw = br#"{"thinking":{"type":"adaptive"},"messages":[{"role":"assistant","content":[{"type":"thinking","thinking":"sample","signature":"old"}]}]}"#;
        let rejection = br#"{"type":"error","error":{"type":"invalid_request_error","message":"Invalid signature in thinking block"}}"#;
        for (approve, observed) in [(true, true), (true, false), (false, false)] {
            let id = source.identity();
            let attempt = Uuid::new_v4();
            let request = Request::builder()
                .header(RESERVATION_HEADER, header(&id))
                .header(TUI_SIGNATURE_REPAIR, "1")
                .body(Body::from(raw.as_slice()))
                .unwrap();
            let (prepared, mut socket) = tokio::join!(
                source
                    .sender
                    .prepare(&source.binding, Some(&source.config), request),
                async {
                    let (mut socket, mut reply) = source.receive("prepare").await;
                    let mut prepared = vec![0; raw.len()];
                    socket.read_exact(&mut prepared).await.unwrap();
                    assert_eq!(prepared, raw);
                    reply["kind"] = json!("continuation");
                    write_json(&mut socket, &reply).await.unwrap();
                    socket
                }
            );
            assert_eq!(prepared.unwrap().headers()[TUI_SIGNATURE_REPAIR], "1");
            tokio::join!(
                async {
                    let mut control = headers(&id);
                    control.insert(
                        TUI_GATEWAY_ID_HEADER,
                        HeaderValue::from_static(TUI_JSON_PROJECTION_V1),
                    );
                    let first = source
                        .sender
                        .send(&source.binding, Some(&source.config), &control, None)
                        .await
                        .unwrap();
                    assert_eq!(first.status(), StatusCode::BAD_REQUEST);
                    assert_eq!(first.headers()[TUI_SIGNATURE_REPAIR], "pending");
                    assert_eq!(
                        first.into_body().collect().await.unwrap().to_bytes(),
                        rejection.as_slice()
                    );
                    assert_eq!(source.sender.active(), 1);
                    assert!(source.send(&id).await.is_err());
                    control.insert(
                        TUI_REPAIR_ATTEMPT,
                        HeaderValue::from_str(&attempt.to_string()).unwrap(),
                    );
                    let mut foreign = source.binding.clone();
                    foreign.release_id = "different".into();
                    assert!(source.sender.repair(&foreign, &control).await.is_err());
                    if approve {
                        let second = source
                            .sender
                            .repair(&source.binding, &control)
                            .await
                            .unwrap();
                        if observed {
                            assert_eq!(second.status(), StatusCode::OK);
                            assert_eq!(second.headers()[TUI_REPAIR_ATTEMPT], attempt.to_string());
                            assert_eq!(
                                second.into_body().collect().await.unwrap().to_bytes(),
                                b"{}".as_slice()
                            );
                        } else {
                            assert_eq!(second.status(), StatusCode::CONFLICT);
                        }
                    } else {
                        assert_eq!(source.cancel(&id).await.unwrap(), StatusCode::NO_CONTENT);
                    }
                    let duplicate = source
                        .sender
                        .repair(&source.binding, &control)
                        .await
                        .unwrap();
                    assert_eq!(duplicate.status(), StatusCode::CONFLICT);
                },
                async {
                    let command = read_json(&mut socket).await.unwrap();
                    assert_eq!(command["action"], "send");
                    assert_eq!(command["signature_repair"], false);
                    write_json(&mut socket, &json!({
                        "signature_repair":"rejected","body_len":raw.len(),
                        "error_len":rejection.len(),"error_source":"local_provider_http","capture_headers_len":0
                    })).await.unwrap();
                    socket.get_mut().write_all(raw).await.unwrap();
                    socket.get_mut().write_all(rejection).await.unwrap();
                    let decision = read_json(&mut socket).await.unwrap();
                    if approve {
                        assert_eq!(decision["attempt_id"], attempt.to_string());
                        let body = read_sized_field(
                            &mut socket,
                            &decision["body_len"],
                            REQUEST_BODY_LIMIT,
                        )
                        .await
                        .unwrap();
                        assert_eq!(
                            serde_json::from_slice::<Value>(&body).unwrap()["messages"][0]["content"]
                                [0]["text"],
                            "sample"
                        );
                        if observed {
                            write_json(&mut socket, &json!({
                                "status":200,"content_type":"application/json","message_id_mode":"gateway",
                                "repair_attempt_id":attempt.to_string()
                            })).await.unwrap();
                            socket
                                .get_mut()
                                .write_all(b"\x00\x00\x00\x02{}\x00\x00\x00\x00")
                                .await
                                .unwrap();
                        } else {
                            write_json(&mut socket, &json!({"status":400}))
                                .await
                                .unwrap();
                        }
                    } else {
                        assert_eq!(decision, json!({"body_len":0}));
                    }
                }
            );
        }
    }

    /// 真实来源在准备阶段可拒绝不支持的输入，此时没有可提交的预留。@return 无。
    #[tokio::test]
    async fn source_rejects_unsupported_input_before_submission() {
        let source = Source::new();
        let identity = source.identity();
        let body = b"{}";
        let (prepared, ()) = tokio::join!(source.prepare(&identity, body), async {
            let (mut socket, mut reply) = source.receive("prepare").await;
            let mut input = [0; 2];
            socket.read_exact(&mut input).await.unwrap();
            assert_eq!(&input, body);
            reply["error"] = json!("unsupported_input");
            write_json(&mut socket, &reply).await.unwrap();
        });
        assert!(matches!(prepared, Err(AppError::TuiInputUnsupported)));
        assert_eq!(source.sender.active(), 0);
        assert!(source.send(&identity).await.is_err());
    }

    /// 受信准备源返回可公开的业务分类，未知码保持私有，全部为零投递。
    #[tokio::test]
    async fn input_policy_rejection_preserves_status_without_submitting() {
        let source = Source::new();
        for (reason, status) in [
            ("invalid_context_management", Some(StatusCode::BAD_REQUEST)),
            (
                "unsupported_parameter",
                Some(StatusCode::UNPROCESSABLE_ENTITY),
            ),
            ("untrusted", None),
        ] {
            let id = source.identity();
            let (prepared, ()) = tokio::join!(source.prepare(&id, b"{}"), async {
                let (mut socket, mut reply) = source.receive("prepare").await;
                socket.read_exact(&mut [0; 2]).await.unwrap();
                reply["error"] = json!("input_rejected");
                reply["code"] = json!(reason);
                write_json(&mut socket, &reply).await.unwrap();
            });
            match (prepared, status) {
                (Err(AppError::TuiInput { code, status, .. }), Some(expected)) => {
                    assert_eq!((code, status), (reason, expected));
                }
                (Ok(response), None) => assert_stage(response, TUI_PREPARE_EXCHANGE),
                _ => panic!("准备错误映射不符"),
            }
            assert_eq!(source.sender.active(), 0);
            assert!(source.send(&id).await.is_err());
        }
    }

    /// 绑定的本机提供方在预留前退避，实际模型尚无可投递的句柄。@return 无。
    #[tokio::test]
    async fn provider_backoff_preserves_wait_without_preparing() {
        let source = Source::new();
        let identity = source.identity();
        let (prepared, ()) = tokio::join!(source.prepare(&identity, b"{}"), async {
            let (mut socket, mut reply) = source.receive("prepare").await;
            socket.read_exact(&mut [0; 2]).await.unwrap();
            reply["error"] = json!("local_provider_backoff");
            reply["retry_after"] = json!(41);
            write_json(&mut socket, &reply).await.unwrap();
        });
        assert!(matches!(
            prepared,
            Err(AppError::TuiProviderBackoff { retry_after: 41 })
        ));
        assert_eq!(source.sender.active(), 0);
        assert!(source.send(&identity).await.is_err());
    }

    /// AT 只在受管来源握手通过、原预留匹配后交付一次。@return 无。
    #[tokio::test]
    async fn account_token_requires_negotiated_source_and_bound_reservation() {
        let source = Source::new();
        let identity = source.identity();
        let (prepared, mut socket) = tokio::join!(source.prepare(&identity, b"{}"), async {
            let (socket, _) = source.listener.accept().await.unwrap();
            let mut socket = BufReader::new(socket);
            let mut proof = read_json(&mut socket).await.unwrap();
            assert_eq!(proof["action"], "bind");
            proof["ready"] = json!(true);
            proof["idle"] = json!(false);
            proof["managed_oauth_protocol"] = json!(1);
            write_json(&mut socket, &proof).await.unwrap();
            let prepare = read_json(&mut socket).await.unwrap();
            assert!(prepare.get("account_token").is_none());
            socket.read_exact(&mut [0; 2]).await.unwrap();
            proof["kind"] = json!("new");
            write_json(&mut socket, &proof).await.unwrap();
            socket
        });
        assert_eq!(prepared.unwrap().headers()[TUI_MANAGED_OAUTH], "1");
        assert_stage(source.send(&identity).await.unwrap(), TUI_SEND_CLAIM);
        let mut credential_headers = headers(&identity);
        let token = "synthetic-account-at";
        credential_headers.insert(TUI_MANAGED_OAUTH, HeaderValue::from_static(token));
        credential_headers.insert(
            TUI_SSE_PROJECTION_HEADER,
            HeaderValue::from_static(TUI_SSE_PROJECTION_V1),
        );
        let mut wrong_identity = identity.clone();
        wrong_identity.account_id += 1;
        let mut wrong_headers = headers(&wrong_identity);
        wrong_headers.insert(TUI_MANAGED_OAUTH, HeaderValue::from_static(token));
        let send = |headers| {
            source
                .sender
                .send(&source.binding, Some(&source.config), headers, None)
        };
        assert!(send(&wrong_headers).await.is_err());
        let (response, ()) = tokio::join!(send(&credential_headers), async {
            let command = read_json(&mut socket).await.unwrap();
            assert_eq!(command["reservation_id"], identity.reservation_id);
            assert_eq!(command["account_token"], token);
            write_json(
                &mut socket,
                &json!({
                    "status":200, "content_type":"text/event-stream", "message_id_mode":"gateway",
                    "body_source":"account_sender",
                    "session_origin":"live_process",
                    "instruction_location":"system",
                    "quota_headers":{
                        "anthropic-ratelimit-unified-5h-utilization":"0.25",
                        "anthropic-ratelimit-unified-5h-reset":"2030-01-01T12:00:00Z",
                        "anthropic-ratelimit-unified-7d-reset":"bad\r\nvalue",
                        "anthropic-ratelimit-unified-overage-status":"rejected",
                        "authorization":"synthetic-unapproved"
                    }
                }),
            )
            .await
            .unwrap();
            chunk(&mut socket, b"data: test\n\n").await;
            chunk(&mut socket, b"").await;
        });
        let response = response.unwrap();
        assert_eq!(response.headers()[TUI_BODY_SOURCE], "account_sender");
        assert_eq!(response.headers()[TUI_SESSION_ORIGIN], "live_process");
        assert_eq!(response.headers()[TUI_INSTRUCTION_LOCATION], "system");
        assert_eq!(
            response.headers()["anthropic-ratelimit-unified-5h-utilization"],
            "0.25"
        );
        assert_eq!(
            response.headers()["anthropic-ratelimit-unified-5h-reset"],
            "2030-01-01T12:00:00Z"
        );
        for name in [
            "anthropic-ratelimit-unified-7d-reset",
            "anthropic-ratelimit-unified-overage-status",
            "authorization",
        ] {
            assert!(!response.headers().contains_key(name));
        }
        assert_eq!(
            response.into_body().collect().await.unwrap().to_bytes(),
            "data: test\n\n"
        );
        assert!(send(&credential_headers).await.is_err());
    }

    /// 完整文件只交给原身份的私有帧，采集只保留已脱敏的账号发送阶段。@return 无。
    #[tokio::test]
    async fn oauth_file_requires_exact_reserved_protocol_and_owner() {
        let source = Source::new();
        let identity = source.identity();
        let request = Request::builder()
            .header(RESERVATION_HEADER, header(&identity))
            .header(TUI_OAUTH_FILE, "1")
            .header(TUI_CAPTURE, "1")
            .body(Body::from("{}"))
            .unwrap();
        let (prepared, mut socket) = tokio::join!(
            source
                .sender
                .prepare(&source.binding, Some(&source.config), request),
            async {
                let (socket, _) = source.listener.accept().await.unwrap();
                let mut socket = BufReader::new(socket);
                let mut proof = read_json(&mut socket).await.unwrap();
                proof["ready"] = json!(true);
                proof["idle"] = json!(false);
                proof["managed_oauth_protocol"] = json!(1);
                proof["oauth_file_protocol"] = json!(1);
                proof["capture_http_protocol"] = json!(1);
                write_json(&mut socket, &proof).await.unwrap();
                let prepare = read_json(&mut socket).await.unwrap();
                assert_eq!(prepare["oauth_file_protocol"], 1);
                assert!(prepare.get("oauth_file_len").is_none());
                socket.read_exact(&mut [0; 2]).await.unwrap();
                proof["kind"] = json!("new");
                write_json(&mut socket, &proof).await.unwrap();
                socket
            }
        );
        let prepared = prepared.unwrap();
        assert_eq!(prepared.headers()[TUI_OAUTH_FILE], "1");
        assert_eq!(prepared.headers()[TUI_CAPTURE], "1");
        let mut legacy = headers(&identity);
        let file = TuiOAuthFile {
            access_token: "a".repeat(2048),
            refresh_token: "r".repeat(2048),
            expires_at: now_ms() + 20_000,
            subscription_type: Some("max".into()),
            rate_limit_tier: Some("verified-tier".into()),
            profile: Some(serde_json::Map::from_iter([(
                "scopes".into(),
                json!(["user:inference", "user:profile"]),
            )])),
        };
        let send = |headers| {
            source
                .sender
                .send(&source.binding, Some(&source.config), headers, None)
        };
        legacy.insert(TUI_MANAGED_OAUTH, HeaderValue::from_static("legacy-at"));
        assert_stage(send(&legacy).await.unwrap(), TUI_SEND_CLAIM);
        let value = file.header().unwrap();
        assert!(value.is_sensitive());
        let mut both = legacy.clone();
        both.insert(TUI_OAUTH_FILE, value.clone());
        assert_stage(send(&both).await.unwrap(), TUI_SEND_CLAIM);
        let mut private = headers(&identity);
        private.insert(TUI_OAUTH_FILE, value);
        private.insert(
            TUI_SSE_PROJECTION_HEADER,
            HeaderValue::from_static(TUI_SSE_PROJECTION_V1),
        );
        let mut another = identity.clone();
        another.generation += 1;
        let mut stale = headers(&another);
        stale.insert(TUI_OAUTH_FILE, file.header().unwrap());
        assert!(send(&stale).await.is_err());
        let encoded =
            TuiCaptureInput::encode(&HeaderMap::new(), b"{}", &json!({}), &[], false).unwrap();
        let capture = serde_json::from_slice(&encoded).unwrap();
        let capture_dir = source.sender.submission_storage.join("capture");
        let sending = source.sender.send(
            &source.binding,
            Some(&source.config),
            &private,
            Some((capture_dir.clone(), capture)),
        );
        let (response, ()) = tokio::join!(sending, async {
            let header = read_json(&mut socket).await.unwrap();
            assert_eq!(header["reservation_id"], identity.reservation_id);
            assert_eq!(header["capture_http"], true);
            assert!(header.get("account_token").is_none());
            let mut raw = vec![0; header["oauth_file_len"].as_u64().unwrap() as usize];
            assert!(raw.len() > CONTROL_LIMIT);
            socket.read_exact(&mut raw).await.unwrap();
            let received: TuiOAuthFile = serde_json::from_slice(&raw).unwrap();
            assert_eq!(
                (
                    &received.access_token,
                    &received.refresh_token,
                    received.expires_at
                ),
                (&file.access_token, &file.refresh_token, file.expires_at)
            );
            write_json(
                &mut socket,
                &json!({
                    "status":200, "content_type":"text/event-stream", "message_id_mode":"gateway",
                    "quota_headers":{"anthropic-ratelimit-unified-7d-utilization":"0.43"}
                }),
            )
            .await
            .unwrap();
            chunk(&mut socket, b"data: fixture\\n\\n").await;
            chunk(&mut socket, b"").await;
            let headers = serde_json::to_vec(&[(
                "Authorization",
                format!("Bearer {}", received.access_token),
            )])
            .unwrap();
            let wire = socket.get_mut();
            wire.write_u32(headers.len() as u32).await.unwrap();
            wire.write_u32(2).await.unwrap();
            wire.write_all(&headers).await.unwrap();
            wire.write_all(b"{}").await.unwrap();
        });
        let response = response.unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(response.headers()[TUI_CAPTURE], "queued");
        assert!(!response.headers().contains_key(TUI_BODY_SOURCE));
        assert!(!response.headers().contains_key(TUI_SESSION_ORIGIN));
        assert!(!response.headers().contains_key(TUI_INSTRUCTION_LOCATION));
        assert_eq!(
            response.headers()["anthropic-ratelimit-unified-7d-utilization"],
            "0.43"
        );
        response.into_body().collect().await.unwrap();
        let capture_path = capture_dir.join(format!("{}.json", identity.reservation_id));
        let stored = timeout(Duration::from_secs(5), async {
            loop {
                match tokio::fs::read_to_string(&capture_path).await {
                    Ok(stored) => break stored,
                    Err(error) if error.kind() == io::ErrorKind::NotFound => {
                        tokio::time::sleep(Duration::from_millis(10)).await;
                    }
                    Err(error) => panic!("读取 V2 采集失败：{error}"),
                }
            }
        })
        .await
        .unwrap();
        let snapshot: Value = serde_json::from_str(&stored).unwrap();
        assert_eq!(
            snapshot["stages"][1]["representation"],
            "http_request_to_local_provider"
        );
        assert_eq!(
            snapshot["stages"][1]["submission_format"],
            "request_to_account_sender"
        );
        assert_eq!(snapshot["stages"][2]["status"], "unavailable");
        assert!(!stored.contains(&file.access_token));
        assert!(!stored.contains(&file.refresh_token));
        assert!(send(&private).await.is_err());
    }

    /// 绑定模型 429 携带原退避。仅受管订阅 429 同时携带额度。@return 无。
    #[tokio::test]
    async fn provider_http_retry_after_from_bound_send_head() {
        let source = Source::new();
        for (origin, managed, seconds) in [
            ("local_provider_http", false, Some(72)),
            ("local_provider_event", true, None),
            ("managed_oauth_http", true, Some(72)),
            ("unknown", false, None),
        ] {
            let identity = source.identity();
            let (prepared, mut socket) = tokio::join!(source.prepare(&identity, b"{}"), async {
                let (mut socket, mut reply) = source.receive("bind").await;
                if managed {
                    reply["managed_oauth_protocol"] = json!(1);
                }
                write_json(&mut socket, &reply).await.unwrap();
                assert_eq!(read_json(&mut socket).await.unwrap()["action"], "prepare");
                socket.read_exact(&mut [0; 2]).await.unwrap();
                reply["kind"] = json!("new");
                write_json(&mut socket, &reply).await.unwrap();
                socket
            });
            assert!(prepared.is_ok());
            let mut send_headers = headers(&identity);
            if managed {
                send_headers.insert(
                    TUI_MANAGED_OAUTH,
                    HeaderValue::from_static("synthetic-account-at"),
                );
            }
            let send =
                source
                    .sender
                    .send(&source.binding, Some(&source.config), &send_headers, None);
            let (response, ()) = tokio::join!(send, async {
                let command = read_json(&mut socket).await.unwrap();
                assert_eq!(command["action"], "send");
                assert_eq!(command.get("account_token").is_some(), managed);
                write_json(
                    &mut socket,
                    &json!({"status":429, "content_type":"application/json",
                    "message_id_mode":"gateway", "error_source":origin, "retry_after":72,
                    "quota_headers":{"anthropic-ratelimit-unified-5h-status":"rejected"}}),
                )
                .await
                .unwrap();
                chunk(
                    &mut socket,
                    br#"{"type":"error","error":{"type":"rate_limit_error","message":"busy"}}"#,
                )
                .await;
                chunk(&mut socket, b"").await;
            });
            let response = response.unwrap();
            assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
            assert_eq!(
                response
                    .headers()
                    .contains_key("anthropic-ratelimit-unified-5h-status"),
                origin == "managed_oauth_http"
            );
            assert_eq!(
                response.headers().get(RETRY_AFTER).map(|value| value
                    .to_str()
                    .unwrap()
                    .parse::<u64>()
                    .unwrap()),
                seconds
            );
            assert!(source.send(&identity).await.is_err());
        }
    }

    /// 新来源单独接收同轮的协议声明，大于控制帧的 beta 清单仍保留；私有凭据始终留在 sender。
    #[tokio::test]
    async fn negotiated_model_headers_follow_intact_body_only() {
        let source = Source::new();
        let id = source.identity();
        let policy = json!({"sub2api":true,"ttl":"5m","adaptive":true});
        let option = "x".repeat(CONTROL_LIMIT + 1);
        let request = Request::builder()
            .header(RESERVATION_HEADER, header(&id))
            .header("anthropic-version", "2023-06-01")
            .header("anthropic-beta", "first")
            .header("anthropic-beta", &option)
            .header("authorization", "fixture-local-only")
            .header("x-api-key", "fixture-client-only")
            .header(TUI_INPUT_FORMAT, "claude_code")
            .header(TUI_MODEL_HEADER_POLICY, "1")
            .header("anthropic-dangerous-direct-browser-access", "false")
            .header(TUI_BODY_POLICY, policy.to_string())
            .body(Body::from("{}"))
            .unwrap();
        let (prepared, ()) = tokio::join!(
            source
                .sender
                .prepare(&source.binding, Some(&source.config), request),
            async {
                let (mut socket, mut reply) = source.receive("bind").await;
                reply["model_headers_protocol"] = json!(1);
                reply["model_header_policy_protocol"] = json!(1);
                reply["body_policy_protocol"] = json!(1);
                reply["input_policy_protocol"] = json!(1);
                write_json(&mut socket, &reply).await.unwrap();
                let control = read_json(&mut socket).await.unwrap();
                assert_eq!(control["input_format"], "claude_code");
                assert_eq!(control["model_header_policy"], 1);
                assert_eq!(control["body_policy"], policy);
                let mut original = [0; 2];
                socket.read_exact(&mut original).await.unwrap();
                assert_eq!(&original, b"{}");
                let mut data = vec![0; control["model_headers_len"].as_u64().unwrap() as usize];
                socket.read_exact(&mut data).await.unwrap();
                assert_eq!(
                    serde_json::from_slice::<Value>(&data).unwrap(),
                    json!({"anthropic-version":"2023-06-01","anthropic-beta":format!("first,{option}"),
                        "anthropic-dangerous-direct-browser-access":"false"})
                );
                reply["kind"] = json!("new");
                write_json(&mut socket, &reply).await.unwrap();
            }
        );
        let response = prepared.unwrap();
        assert_eq!(response.status(), StatusCode::NO_CONTENT);
        assert_eq!(response.headers()[TUI_BODY_POLICY], "1");
        assert_eq!(response.headers()[TUI_INPUT_POLICY], "1");
        assert_eq!(response.headers()[TUI_MODEL_HEADER_POLICY], "1");
        assert_eq!(source.cancel(&id).await.unwrap(), StatusCode::NO_CONTENT);
    }

    /// 映射只随已协商的 send 到达，旧源和重复头不消费预留。@return 无。
    #[tokio::test]
    async fn upstream_session_mapping_requires_same_reserved_source() {
        for supported in [false, true] {
            let source = Source::new();
            let mut id = source.identity();
            id.session_id = Uuid::new_v4().to_string();
            let mapped = Uuid::new_v4().to_string();
            let (prepared, mut socket) = tokio::join!(source.prepare(&id, b"{}"), async {
                let (socket, _) = source.listener.accept().await.unwrap();
                let mut socket = BufReader::new(socket);
                let mut reply = read_json(&mut socket).await.unwrap();
                assert_eq!(
                    reply.as_object_mut().unwrap().remove("action"),
                    Some(json!("bind"))
                );
                reply["ready"] = json!(true);
                reply["idle"] = json!(true);
                if supported {
                    reply["upstream_session_protocol"] = json!(1);
                }
                write_json(&mut socket, &reply).await.unwrap();
                let prepare = read_json(&mut socket).await.unwrap();
                assert_eq!(prepare["action"], "prepare");
                assert_eq!(prepare["reservation"]["session_id"], id.session_id);
                assert!(prepare.get("upstream_session_id").is_none());
                socket.read_exact(&mut [0; 2]).await.unwrap();
                reply["kind"] = json!("new");
                write_json(&mut socket, &reply).await.unwrap();
                socket
            });
            assert_eq!(
                prepared
                    .unwrap()
                    .headers()
                    .contains_key(TUI_UPSTREAM_SESSION),
                supported
            );
            let mut send_headers = headers(&id);
            send_headers.append(TUI_UPSTREAM_SESSION, mapped.parse().unwrap());
            send_headers.append(TUI_UPSTREAM_SESSION, mapped.parse().unwrap());
            assert!(
                source
                    .sender
                    .send(&source.binding, Some(&source.config), &send_headers, None)
                    .await
                    .is_err()
            );
            send_headers.insert(TUI_UPSTREAM_SESSION, mapped.parse().unwrap());
            if !supported {
                assert_stage(
                    source
                        .sender
                        .send(&source.binding, Some(&source.config), &send_headers, None)
                        .await
                        .unwrap(),
                    TUI_SEND_CLAIM,
                );
                send_headers.remove(TUI_UPSTREAM_SESSION);
            }
            let (sent, ()) = tokio::join!(
                source
                    .sender
                    .send(&source.binding, Some(&source.config), &send_headers, None),
                async {
                    let send = read_json(&mut socket).await.unwrap();
                    assert_eq!(send["action"], "send");
                    assert_eq!(send["reservation_id"], id.reservation_id);
                    assert_eq!(
                        send["upstream_session_id"].as_str(),
                        supported.then_some(mapped.as_str())
                    );
                    write_json(
                        &mut socket,
                        &json!({"status":200,"content_type":"text/event-stream"}),
                    )
                    .await
                    .unwrap();
                    socket.write_all(&0u32.to_be_bytes()).await.unwrap();
                }
            );
            assert_eq!(sent.unwrap().status(), StatusCode::OK);
            assert!(source.send(&id).await.is_err());
        }
    }

    /// 老账号源遇到启用的正文策略在提交前拒绝并释放预留。@return 无。
    #[tokio::test]
    async fn body_policy_requires_source_support_before_body_transfer() {
        let source = Source::new();
        let id = source.identity();
        let request = Request::builder()
            .header(RESERVATION_HEADER, header(&id))
            .header(
                TUI_BODY_POLICY,
                r#"{"sub2api":true,"ttl":"off","adaptive":false}"#,
            )
            .body(Body::from("原文"))
            .unwrap();
        let (result, ()) = tokio::join!(
            source
                .sender
                .prepare(&source.binding, Some(&source.config), request),
            async {
                let (mut socket, reply) = source.receive("bind").await;
                write_json(&mut socket, &reply).await.unwrap();
                let mut remaining = Vec::new();
                socket.read_to_end(&mut remaining).await.unwrap();
                assert!(remaining.is_empty());
            }
        );
        assert_stage(result.unwrap(), TUI_PREPARE_BIND);
        assert_eq!(source.sender.active(), 0);
    }

    /// 唯一物理进程正在等工具时，排队的新握手必须让原工具续轮获得最后一个位置。
    #[tokio::test]
    async fn queued_prepares_leave_room_for_a_registered_tool_return() {
        let source = Source::new();
        let deadline = Instant::now() + Duration::from_secs(5);
        let reserve = |identity| {
            source
                .sender
                .reserve(identity, &source.binding, deadline, deadline, 2)
        };
        let _waiting = reserve(source.identity()).unwrap();
        assert!(matches!(
            reserve(source.identity()),
            Err(AppError::AdmissionLimited { .. })
        ));
        let mut child = source.identity();
        child.agent_hint = Some("unverified-child".into());
        let (probe, _) = reserve(child).unwrap();
        let mut duplicate_hint = source.identity();
        duplicate_hint.agent_hint = Some("another-unverified-child".into());
        assert!(matches!(
            reserve(duplicate_hint),
            Err(AppError::AdmissionLimited { .. })
        ));
        let mut original = source.identity();
        original.continuation_only = true;
        let _returning = reserve(original).unwrap();
        assert_eq!(source.sender.active(), 3);
        // 来源拒绝未关联的线索时，prepare 的 RAII 同步关闭专用位置。
        drop(probe);
        assert_eq!(source.sender.active(), 2);
        let mut retry = source.identity();
        retry.agent_hint = Some("verified-at-source".into());
        let _next_probe = reserve(retry).unwrap();
        assert_eq!(source.sender.active(), 3);
    }

    /// 已借用物理余位的分支运行时，保留最后一个传输位置。@return 无。
    #[tokio::test]
    async fn borrowed_receipt_fork_preserves_the_last_sender_slot() {
        let source = Source::new();
        let deadline = Instant::now() + Duration::from_secs(5);
        let reserve = |identity| {
            source
                .sender
                .reserve(identity, &source.binding, deadline, deadline, 2)
        };
        let (fork, _) = reserve(source.identity()).unwrap();
        {
            let mut book = source.sender.book.lock().unwrap();
            let record = book.get_mut(&fork.id).unwrap();
            record.fork_borrowed_slot = true;
            record.phase = Phase::Submitted;
        }
        assert!(matches!(
            reserve(source.identity()),
            Err(AppError::AdmissionLimited { .. })
        ));
        let mut parent = source.identity();
        parent.continuation_only = true;
        let (returning, _) = reserve(parent).unwrap();
        assert_eq!(source.sender.active(), 2);
        drop(returning);
        drop(fork);
        assert!(reserve(source.identity()).is_ok());
    }

    impl Drop for Source {
        fn drop(&mut self) {
            let _ = remove_dir_all(self.sender.path.parent().unwrap());
        }
    }

    fn header(identity: &Identity) -> HeaderValue {
        HeaderValue::from_str(&STANDARD.encode(serde_json::to_vec(identity).unwrap())).unwrap()
    }

    fn headers(identity: &Identity) -> HeaderMap {
        let mut headers = HeaderMap::new();
        headers.insert(RESERVATION_HEADER, header(identity));
        headers
    }

    fn assert_stage(response: Response, stage: &str) {
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(response.headers()[TUI_ERROR_SOURCE], stage);
    }

    /// 旧候选的源在绑定阶段关闭，外部正文与发送指令都留在发送器内。@return 无。
    #[tokio::test]
    async fn retired_cli_body_override_is_rejected_before_prepare() {
        let source = Source::new();
        let identity = source.identity();
        let (response, ()) = tokio::join!(source.prepare(&identity, b"{}"), async {
            let (socket, _) = source.listener.accept().await.unwrap();
            let mut socket = BufReader::new(socket);
            let mut proof = read_json(&mut socket).await.unwrap();
            assert_eq!(proof["action"], "bind");
            proof["ready"] = json!(true);
            proof["idle"] = json!(true);
            proof["managed_oauth_protocol"] = json!(1);
            proof["capture_cli_submission_protocol"] = json!(1);
            write_json(&mut socket, &proof).await.unwrap();
            assert_eq!(socket.read(&mut [0_u8; 1]).await.unwrap(), 0);
        });
        assert_stage(response.unwrap(), TUI_PREPARE_BIND);
        assert_eq!(source.sender.active(), 0);
        assert!(source.send(&identity).await.is_err());
    }

    async fn chunk(connection: &mut BufReader<UnixStream>, bytes: &[u8]) {
        connection
            .get_mut()
            .write_u32(bytes.len() as u32)
            .await
            .unwrap();
        connection.get_mut().write_all(bytes).await.unwrap();
    }

    /// 准备与取消不落盘，只有认领发送后才可获得当前主体的工作目录。
    /// @return 无。
    #[tokio::test]
    async fn workspace_is_bound_only_at_authenticated_send() {
        let source = Source::new();
        let body = br#"{"messages":[{"role":"user","content":"hello"}]}"#;
        let base = source.sender.submission_storage.join("tui-workspaces");
        for cancel in [true, false] {
            let identity = source.identity();
            let (prepared, mut socket) = tokio::join!(source.prepare(&identity, body), async {
                let (mut socket, mut reply) = source.receive("prepare").await;
                let mut bytes = vec![0; body.len()];
                socket.read_exact(&mut bytes).await.unwrap();
                assert_eq!(bytes, body);
                reply["kind"] = json!("new");
                reply["workspace_protocol"] = json!(1);
                write_json(&mut socket, &reply).await.unwrap();
                socket
            });
            assert_eq!(prepared.unwrap().status(), StatusCode::NO_CONTENT);
            assert!(!base.exists());
            if cancel {
                assert_eq!(
                    source.cancel(&identity).await.unwrap(),
                    StatusCode::NO_CONTENT
                );
                assert!(!base.exists());
                continue;
            }
            let other = Identity {
                principal_id: identity.principal_id + 1,
                ..identity.clone()
            };
            assert!(source.send(&other).await.is_err());
            assert!(!base.exists());
            let (response, ()) = tokio::join!(source.send(&identity), async {
                let command = read_json(&mut socket).await.unwrap();
                assert_eq!(command["reservation_id"], identity.reservation_id);
                let launch = &command["workspace"];
                assert_eq!(launch["version"], 1);
                assert!(Path::new(launch["work_dir"].as_str().unwrap()).is_dir());
                let record: Value = serde_json::from_slice(
                    &std::fs::read(launch["binding_file"].as_str().unwrap()).unwrap(),
                )
                .unwrap();
                assert_eq!(record["native_session_id"], launch["native_session_id"]);
                write_json(
                    &mut socket,
                    &json!({"status":200,"content_type":"text/event-stream"}),
                )
                .await
                .unwrap();
                socket.get_mut().write_u32(0).await.unwrap();
            });
            assert_eq!(response.unwrap().status(), StatusCode::OK);
        }
    }

    /// 原工具预留的绑定暂缺时关闭已准备的 Unix 连接，并报告确定的发送前拒绝。@return 无。
    #[tokio::test]
    async fn unavailable_workspace_does_not_send_authenticated_tool_receipt() {
        let source = Source::new();
        let root = &source.sender.submission_storage;
        let body = b"{}";
        let owner = source.identity();
        let workspace = workspace::Candidate::from_request(body, true, None)
            .unwrap()
            .bind(root, &owner)
            .unwrap();
        let binding = Path::new(workspace["binding_file"].as_str().unwrap());
        let original = std::fs::read(binding).unwrap();
        let base = binding.parent().unwrap();
        for target in [base, binding] {
            let held = target.with_extension("fixture-held");
            std::fs::rename(target, &held).unwrap();
            let identity = Identity {
                continuation_only: true,
                reservation_id: Uuid::new_v4().to_string(),
                ..owner.clone()
            };
            let (prepared, mut socket) = tokio::join!(source.prepare(&identity, body), async {
                let (mut socket, mut reply) = source.receive("prepare").await;
                let mut raw = [0; 2];
                socket.read_exact(&mut raw).await.unwrap();
                assert_eq!(&raw, body);
                reply["kind"] = json!("recovered");
                reply["workspace_protocol"] = json!(1);
                write_json(&mut socket, &reply).await.unwrap();
                socket
            });
            assert_eq!(prepared.unwrap().status(), StatusCode::NO_CONTENT);
            let (response, ()) = tokio::join!(source.send(&identity), async {
                assert_eq!(
                    socket.read_u8().await.unwrap_err().kind(),
                    io::ErrorKind::UnexpectedEof
                );
            });
            let response = response.unwrap();
            assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
            assert_eq!(response.headers()[TUI_ERROR_SOURCE], TUI_WORKSPACE_BIND);
            assert!(!target.exists());
            std::fs::rename(&held, target).unwrap();
            assert_eq!(std::fs::read(binding).unwrap(), original);
        }
    }

    /// 同一预留在发送前占用名额，响应按源字节逐段返回，发送后仍可安全重放取消。@return 无。
    /// 测试单轮证明可在另一个会话驻留时独立返回。@return 无。
    #[tokio::test]
    async fn source_status_returns_exact_receipt_idle_independently() {
        let source = Source::new();
        let probe = TuiReceiptProbe {
            principal_id: 1,
            session_id: "original".into(),
        };
        let (status, ()) = tokio::join!(
            source
                .sender
                .status(&source.binding, Some(&source.config), Some(&probe)),
            async {
                let (mut socket, mut reply) = source.receive("status").await;
                assert_eq!(
                    reply["receipt"],
                    json!({"principal_id":1,"session_id":"original"})
                );
                reply["idle"] = json!(false);
                reply["agent_summary_protocol"] = json!(1);
                reply["receipt_idle"] = json!(true);
                write_json(&mut socket, &reply).await.unwrap();
            }
        );
        assert_eq!(status, Ok((false, Some(true), true, false, false)));
    }

    #[tokio::test]
    async fn accepted_socket_delivers_original_frames_once() {
        let source = Source::new();
        let body = "{\n \"text\":\"一\"\n}".as_bytes();
        let (idle, ()) = tokio::join!(
            source
                .sender
                .status(&source.binding, Some(&source.config), None),
            async {
                let (mut socket, mut reply) = source.receive("status").await;
                reply["idle"] = json!(true);
                write_json(&mut socket, &reply).await.unwrap();
            }
        );
        assert_eq!(idle, Ok((true, None, false, false, false)));
        let mut identity = source.identity();
        identity.continuation_only = true;
        let (prepared, mut socket) = tokio::join!(source.prepare(&identity, body), async {
            let (mut socket, mut reply) = source.receive("prepare").await;
            assert_eq!(reply["reservation"], json!(&identity));
            assert_eq!(reply["body_len"], body.len());
            assert_eq!(reply["body_sha256"], hex::encode(Sha256::digest(body)));
            let mut actual = vec![0; body.len()];
            socket.read_exact(&mut actual).await.unwrap();
            assert_eq!(actual, body);
            reply["kind"] = json!("continuation");
            write_json(&mut socket, &reply).await.unwrap();
            socket
        });
        let prepared = prepared.unwrap();
        assert_eq!(prepared.status(), StatusCode::NO_CONTENT);
        assert_eq!(prepared.headers()[HANDOFF_HEADER], "continuation");
        assert_eq!(source.sender.active(), 1);
        assert!(matches!(
            source.prepare(&source.identity(), body).await,
            Err(AppError::AdmissionLimited { .. })
        ));
        assert!(source.prepare(&identity, b"{}").await.is_err());
        let other = Identity {
            principal_id: 92,
            ..identity.clone()
        };
        assert!(source.send(&other).await.is_err());
        assert!(source.cancel(&other).await.is_err());
        let new_binding = TransportBinding {
            secret: "rotated-binding".repeat(3),
            ..source.binding.clone()
        };
        assert!(
            source
                .sender
                .send(
                    &new_binding,
                    Some(&source.config),
                    &headers(&identity),
                    None
                )
                .await
                .is_err()
        );

        let large_chunk = vec![b'x'; CHUNK_LIMIT];
        let chunks = 10 * 1024 * 1024 / CHUNK_LIMIT + 1;
        let (release, waiting) = oneshot::channel();
        let (_done, ()) = tokio::join!(
            async {
                let response = source.send(&identity).await.unwrap();
                assert_eq!(response.headers()[CONTENT_TYPE], "text/event-stream");
                let mut stream = response.into_body();
                assert_eq!(
                    stream.frame().await.unwrap().unwrap().into_data().unwrap(),
                    "data: 行\n\n"
                );
                assert_eq!(
                    source.cancel(&identity).await.unwrap(),
                    StatusCode::NO_CONTENT
                );
                assert!(source.send(&identity).await.is_err());
                assert_eq!(source.sender.active(), 1);
                release.send(()).unwrap();
                assert_eq!(
                    stream.frame().await.unwrap().unwrap().into_data().unwrap(),
                    r#"data: {"type":"content_block_delta","delta":{"type":"text_delta","text":""#,
                );
                // 一个超 10 MiB 的原始事件仍由 64 KiB UDS 块逐个交付。
                for _ in 0..chunks {
                    assert_eq!(
                        stream.frame().await.unwrap().unwrap().into_data().unwrap(),
                        large_chunk.as_slice(),
                    );
                }
                assert_eq!(stream.collect().await.unwrap().to_bytes(), "\"}}\n\n");
            },
            async {
                assert_eq!(
                    read_json(&mut socket).await.unwrap(),
                    json!({"action":"send","reservation_id":identity.reservation_id})
                );
                write_json(
                    &mut socket,
                    &json!({"status":200,"content_type":"text/event-stream"}),
                )
                .await
                .unwrap();
                chunk(&mut socket, "data: 行\n\n".as_bytes()).await;
                waiting.await.unwrap();
                chunk(
                    &mut socket,
                    br#"data: {"type":"content_block_delta","delta":{"type":"text_delta","text":""#,
                )
                .await;
                for _ in 0..chunks {
                    chunk(&mut socket, &large_chunk).await;
                }
                chunk(&mut socket, b"\"}}\n\n").await;
                chunk(&mut socket, b"").await;
            }
        );
        assert_eq!(source.sender.active(), 0);
        assert!(source.send(&identity).await.is_err());
        assert!(source.prepare(&identity, body).await.is_err());
    }

    /// 只有已绑定来源的 send 回包能开启转换。@return 无。
    #[tokio::test]
    async fn gateway_id_opt_in_is_read_from_bound_send_head_only() {
        let source = Source::new();
        let request = br#"{"model":"fixture","messages":[{"role":"user","content":[{"type":"text","text":"cache prefix","cache_control":{"type":"ephemeral","ttl":"1h"}}]}]}"#;
        let wire = br#" { "type":"message", "id":"msg_original", "content":[], "usage":{"cache_read_input_tokens":42} } "#;
        for (status, mode) in [
            (200, None),
            (400, None),
            (200, Some(json!("unknown"))),
            (200, Some(Value::Null)),
            (200, Some(json!(true))),
            (200, Some(json!("gateway"))),
        ] {
            let gateway_ids = mode.as_ref().and_then(Value::as_str) == Some("gateway");
            let rejected = mode.is_some() && !gateway_ids;
            let identity = source.identity();
            let (prepared, mut socket) = tokio::join!(source.prepare(&identity, request), async {
                let (mut socket, mut reply) = source.receive("prepare").await;
                assert_eq!(reply["body_sha256"], hex::encode(Sha256::digest(request)));
                let mut actual = vec![0; request.len()];
                socket.read_exact(&mut actual).await.unwrap();
                assert_eq!(actual, request);
                reply["kind"] = json!("new");
                reply["message_id_mode"] = json!("gateway");
                write_json(&mut socket, &reply).await.unwrap();
                socket
            });
            assert_eq!(prepared.unwrap().status(), StatusCode::NO_CONTENT);
            let (reply, ()) = tokio::join!(source.send(&identity), async {
                assert_eq!(
                    read_json(&mut socket).await.unwrap(),
                    json!({"action":"send","reservation_id":identity.reservation_id})
                );
                let mut head = json!({"status":status,"content_type":"application/json"});
                if let Some(mode) = mode {
                    head["message_id_mode"] = mode;
                }
                write_json(&mut socket, &head).await.unwrap();
                if rejected {
                    assert_eq!(
                        timeout(Duration::from_secs(2), socket.read(&mut [0]))
                            .await
                            .unwrap()
                            .unwrap(),
                        0
                    );
                } else {
                    chunk(&mut socket, wire).await;
                    chunk(&mut socket, b"").await;
                }
            });
            if rejected {
                assert!(
                    matches!(reply, Err(AppError::BadGateway(detail)) if detail.contains("消息 ID 模式"))
                );
                assert_eq!(source.sender.active(), 0);
                assert!(source.send(&identity).await.is_err());
                continue;
            }
            let reply = reply.unwrap();
            assert_eq!(reply.status().as_u16(), status);
            assert_eq!(
                reply
                    .headers()
                    .get(TUI_GATEWAY_ID_HEADER)
                    .map(|value| value.to_str().unwrap()),
                gateway_ids.then_some("gateway")
            );
            let bytes = reply.into_body().collect().await.unwrap().to_bytes();
            if gateway_ids {
                let body: Value = serde_json::from_slice(&bytes).unwrap();
                let id = body["id"].as_str().unwrap();
                assert!(id.starts_with("msg_"));
                assert_ne!(id, "msg_original");
                assert_eq!(body["usage"]["cache_read_input_tokens"], 42);
            } else {
                assert_eq!(bytes, wire.as_slice());
            }
        }
    }

    /// 只有新网关协商委托后，原始 SSE 政策码才进入私有链路。@return 无。
    #[tokio::test]
    async fn raw_sse_preserves_policy_code_only_when_gateway_negotiated() {
        let source = Source::new();
        let frame = b"event: error\ndata: {\"type\":\"error\",\"error\":{\"upstream_code\":\"cyber_policy\"}}\n\n";
        for delegated in [true, false] {
            let identity = source.identity();
            let (prepared, mut socket) = tokio::join!(source.prepare(&identity, b"{}"), async {
                let (mut socket, mut reply) = source.receive("prepare").await;
                socket.read_exact(&mut [0; 2]).await.unwrap();
                reply["kind"] = json!("new");
                write_json(&mut socket, &reply).await.unwrap();
                socket
            });
            prepared.unwrap();
            let mut negotiated = headers(&identity);
            if delegated {
                negotiated.insert(
                    TUI_SSE_PROJECTION_HEADER,
                    HeaderValue::from_static(TUI_SSE_PROJECTION_V1),
                );
            }
            let (reply, ()) = tokio::join!(
                source
                    .sender
                    .send(&source.binding, Some(&source.config), &negotiated, None),
                async {
                    assert_eq!(read_json(&mut socket).await.unwrap()["action"], "send");
                    write_json(&mut socket, &json!({
                        "status": 200, "content_type": "text/event-stream", "message_id_mode": "gateway"
                    })).await.unwrap();
                    chunk(&mut socket, frame).await;
                    chunk(&mut socket, b"").await;
                }
            );
            let reply = reply.unwrap();
            let expected = if delegated {
                TUI_SSE_PROJECTION_V1
            } else {
                "gateway"
            };
            assert_eq!(reply.headers()[TUI_GATEWAY_ID_HEADER], expected);
            let wire = reply.into_body().collect().await.unwrap().to_bytes();
            assert_eq!(
                String::from_utf8_lossy(&wire).contains("cyber_policy"),
                delegated
            );
        }
    }

    /// 已认领的 JSON 从 UDS 逐块交付，准入到期不截断同一次提交。@return 无。
    #[tokio::test]
    async fn gateway_id_json_arrives_after_admission_deadline() {
        let source = Source::new();
        let identity = Identity {
            deadline_unix_ms: now_ms() + 3_000,
            ..source.identity()
        };
        let (prepared, mut socket) = tokio::join!(source.prepare(&identity, b"{}"), async {
            let (mut socket, mut head) = source.receive("prepare").await;
            let mut actual = [0; 2];
            socket.read_exact(&mut actual).await.unwrap();
            assert_eq!(&actual, b"{}");
            head["kind"] = json!("new");
            write_json(&mut socket, &head).await.unwrap();
            socket
        });
        assert_eq!(prepared.unwrap().status(), StatusCode::NO_CONTENT);
        let deadline = source.sender.book.lock().unwrap()[&identity.reservation_id].deadline;

        let mut negotiated = headers(&identity);
        negotiated.insert(
            TUI_GATEWAY_ID_HEADER,
            HeaderValue::from_static(TUI_JSON_PROJECTION_V1),
        );
        let (head_seen, wait_head) = oneshot::channel();
        let (reply, ()) = tokio::join!(
            async {
                let private = source
                    .sender
                    .send(&source.binding, Some(&source.config), &negotiated, None)
                    .await
                    .unwrap();
                assert!(Instant::now() < deadline);
                assert_eq!(
                    private.headers()[TUI_GATEWAY_ID_HEADER],
                    TUI_JSON_PROJECTION_V1
                );
                head_seen.send(()).unwrap();
                tui_sender_response::project(
                    private.status(),
                    "application/json",
                    private.into_body(),
                )
                .await
            },
            async {
                assert_eq!(
                    read_json(&mut socket).await.unwrap(),
                    json!({"action":"send","reservation_id":identity.reservation_id})
                );
                write_json(
                &mut socket,
                &json!({"status":200,"content_type":"application/json","message_id_mode":"gateway"}),
            )
            .await
            .unwrap();
                // Gateway 能在准入截止前读到私有头。任何正文都在截止之后交给它。
                timeout_at(deadline, wait_head).await.unwrap().unwrap();
                sleep_until(deadline + Duration::from_millis(200)).await;
                assert!(Instant::now() > deadline);
                assert_eq!(source.sender.active(), 1);
                chunk(
                    &mut socket,
                    br#"{"type":"message","id":"msg_source","role":"assistant","model":"fixture","#,
                )
                .await;
                chunk(&mut socket, br#""content":[],"stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":10,"output_tokens":2,"cache_read_input_tokens":5}}"#).await;
                chunk(&mut socket, b"").await;
            }
        );
        assert_eq!(reply.status(), StatusCode::OK);
        let body = reply.into_body().collect().await.unwrap().to_bytes();
        let body: Value = serde_json::from_slice(&body).unwrap();
        let id = body["id"].as_str().unwrap().strip_prefix("msg_").unwrap();
        assert!(Uuid::parse_str(id).is_ok());
        assert_eq!(body["usage"]["cache_read_input_tokens"], 5);
        assert_eq!(source.sender.active(), 0);
    }

    /// 迟到的准备、显式取消与截止回收都关闭本机通道。@return 无。
    #[tokio::test]
    async fn cancelled_or_expired_reservations_never_submit() {
        let mut source = Source::new();
        let early = source.identity();
        assert_eq!(source.cancel(&early).await.unwrap(), StatusCode::NO_CONTENT);
        assert!(source.prepare(&early, b"{}").await.is_err());
        let waiting = source.identity();
        let (result, ()) = tokio::join!(source.prepare(&waiting, b"{}"), async {
            let (mut socket, _) = source.receive("prepare").await;
            let mut body = [0; 2];
            socket.read_exact(&mut body).await.unwrap();
            assert_eq!(
                source.cancel(&waiting).await.unwrap(),
                StatusCode::NO_CONTENT
            );
            assert_eq!(
                source.cancel(&waiting).await.unwrap(),
                StatusCode::NO_CONTENT
            );
            assert_eq!(socket.read(&mut [0]).await.unwrap(), 0);
        });
        assert!(result.is_err());
        assert_eq!(source.sender.active(), 0);
        let expiring = Identity {
            deadline_unix_ms: now_ms() + 1000,
            ..source.identity()
        };
        let (result, ()) = tokio::join!(source.prepare(&expiring, b"{}"), async {
            let (mut socket, mut reply) = source.receive("prepare").await;
            socket.read_exact(&mut [0; 2]).await.unwrap();
            reply["kind"] = json!("new");
            write_json(&mut socket, &reply).await.unwrap();
            assert_eq!(
                timeout(Duration::from_secs(2), socket.read(&mut [0]))
                    .await
                    .unwrap()
                    .unwrap(),
                0
            );
        });
        assert_eq!(result.unwrap().status(), StatusCode::NO_CONTENT);
        assert_eq!(source.sender.active(), 0);
        // 本机通道按单调时钟关闭，取消回执按墙钟签发。先确认信封的绝对截止已过。
        let remaining_ms = expiring.deadline_unix_ms.saturating_sub(now_ms());
        tokio::time::sleep(Duration::from_millis(remaining_ms + 1)).await;
        assert!(now_ms() >= expiring.deadline_unix_ms);
        assert!(source.send(&expiring).await.is_err());
        assert_eq!(
            source.cancel(&expiring).await.unwrap(),
            StatusCode::NO_CONTENT
        );

        let disk: Value = serde_json::from_slice(
            &std::fs::read(
                source
                    .sender
                    .submission_storage
                    .join("tui-v2-submissions.json"),
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(
            disk,
            json!({"account_id":source.binding.account_id,
            "environment_id":source.binding.environment_id,"committed":{},"cancelled":{
                (&early.reservation_id):early.deadline_unix_ms,
                (&waiting.reservation_id):waiting.deadline_unix_ms,
            }})
        );
        source.sender.book = Book::default();
        for identity in [&early, &waiting] {
            assert!(identity.deadline_unix_ms > now_ms());
            assert!(matches!(
                source.prepare(identity, b"{}").await,
                Err(AppError::BadRequest(_))
            ));
            assert!(matches!(
                source.send(identity).await,
                Err(AppError::BadRequest(_))
            ));
            assert_eq!(
                source.cancel(identity).await.unwrap(),
                StatusCode::NO_CONTENT
            );
        }
        assert!(
            timeout(Duration::from_millis(100), source.listener.accept())
                .await
                .is_err()
        );
    }

    /// 错绑事件源失去就绪资格，发出部分正文后提前结束会报告传输错误。@return 无。
    #[tokio::test]
    async fn bad_source_proof_and_truncated_stream_are_rejected() {
        let source = Source::new();
        assert_eq!(
            source.sender.status(&source.binding, None, None).await,
            Err(TuiV2Unavailable::ReadinessConfig)
        );
        let (idle, ()) = tokio::join!(
            source
                .sender
                .status(&source.binding, Some(&source.config), None),
            async {
                let (mut socket, mut reply) = source.receive("status").await;
                reply["generation"] = json!(0);
                write_json(&mut socket, &reply).await.unwrap();
            }
        );
        assert_eq!(idle, Err(TuiV2Unavailable::ReadinessSource));
        let identity = source.identity();
        let (prepared, mut socket) = tokio::join!(source.prepare(&identity, b"{}"), async {
            let (mut socket, mut reply) = source.receive("prepare").await;
            socket.read_exact(&mut [0; 2]).await.unwrap();
            reply["kind"] = json!("new");
            write_json(&mut socket, &reply).await.unwrap();
            socket
        });
        assert!(prepared.is_ok());
        let (sent, ()) = tokio::join!(source.send(&identity), async {
            assert_eq!(read_json(&mut socket).await.unwrap()["action"], "send");
            write_json(
                &mut socket,
                &json!({"status":200,"content_type":"text/event-stream"}),
            )
            .await
            .unwrap();
            chunk(&mut socket, b"partial").await;
            drop(socket);
        });
        let mut body = sent.unwrap().into_body();
        assert_eq!(
            body.frame().await.unwrap().unwrap().into_data().unwrap(),
            "partial"
        );
        assert!(body.frame().await.unwrap().is_err());
        assert_eq!(source.sender.active(), 0);
        assert!(source.send(&identity).await.is_err());
    }

    /// 同 UID 的错绑事件源只能见到绑定握手。@return 无。
    #[tokio::test]
    async fn wrong_bind_receives_neither_reservation_nor_body() {
        let source = Source::new();
        for (field, value) in [("generation", json!(6)), ("account_id", json!(97))] {
            let identity = source.identity();
            let (prepared, received) =
                tokio::join!(source.prepare(&identity, b"private body"), async {
                    let (mut socket, mut reply) = source.receive("bind").await;
                    assert!(reply.get("reservation").is_none() && reply.get("body_len").is_none());
                    reply[field] = value;
                    write_json(&mut socket, &reply).await.unwrap();
                    let mut received = Vec::new();
                    socket.read_to_end(&mut received).await.unwrap();
                    received
                });
            assert_stage(prepared.unwrap(), TUI_PREPARE_BIND);
            assert!(received.is_empty());
            assert_eq!(source.sender.active(), 0);
        }
    }

    /// 回包前断开，新的 sender 仍从持久提交事实拒绝原未过期两步重放。@return 无。
    #[tokio::test]
    async fn lost_reply_then_restart_rejects_prepare_and_send_replay() {
        let mut source = Source::new();
        let identity = source.identity();
        let (prepared, mut socket) = tokio::join!(source.prepare(&identity, b"{}"), async {
            let (mut socket, mut reply) = source.receive("prepare").await;
            socket.read_exact(&mut [0; 2]).await.unwrap();
            reply["kind"] = json!("new");
            write_json(&mut socket, &reply).await.unwrap();
            socket
        });
        assert!(prepared.is_ok());
        let (sent, ()) = tokio::join!(source.send(&identity), async {
            assert_eq!(read_json(&mut socket).await.unwrap()["action"], "send");
            assert!(
                submission_log::was_consumed(
                    &source.sender.submission_storage,
                    &source.binding,
                    Some(&identity.reservation_id),
                    (Instant::now() + Duration::from_secs(1)).into_std(),
                )
                .await
                .unwrap()
            );
            drop(socket);
        });
        assert!(matches!(sent, Err(AppError::BadGateway(_))));
        source.sender = TuiSender {
            path: source.sender.path.clone(),
            submission_storage: source.sender.submission_storage.clone(),
            book: Book::default(),
        };
        assert!(identity.deadline_unix_ms > now_ms());
        assert!(matches!(
            source.prepare(&identity, b"{}").await,
            Err(AppError::BadRequest(_))
        ));
        assert!(matches!(
            source.send(&identity).await,
            Err(AppError::BadRequest(_))
        ));
        assert!(
            timeout(Duration::from_millis(100), source.listener.accept())
                .await
                .is_err()
        );
        assert_eq!(source.sender.active(), 0);
    }

    /// 合法恢复续轮沿原截止等待账本锁，锁内提交后才通知事件源。@return 无。
    #[tokio::test]
    async fn recovered_send_waits_for_ledger_within_its_deadline() {
        let source = Source::new();
        let mut identity = source.identity();
        identity.continuation_only = true;
        let (prepared, mut socket) = tokio::join!(source.prepare(&identity, b"{}"), async {
            let (mut socket, mut reply) = source.receive("prepare").await;
            socket.read_exact(&mut [0; 2]).await.unwrap();
            reply["kind"] = json!("recovered");
            write_json(&mut socket, &reply).await.unwrap();
            socket
        });
        assert_eq!(prepared.unwrap().status(), StatusCode::NO_CONTENT);
        let lock = submission_log::lock(&source.sender.submission_storage).unwrap();
        let (sent, ()) = tokio::join!(source.send(&identity), async {
            assert!(
                timeout(Duration::from_millis(1250), read_json(&mut socket))
                    .await
                    .is_err()
            );
            drop(lock);
            let command = read_json(&mut socket).await.unwrap();
            assert_eq!(command["action"], "send");
            assert_eq!(command["reservation_id"], identity.reservation_id);
            assert!(
                submission_log::was_consumed(
                    &source.sender.submission_storage,
                    &source.binding,
                    Some(&identity.reservation_id),
                    (Instant::now() + Duration::from_secs(1)).into_std(),
                )
                .await
                .unwrap()
            );
            write_json(
                &mut socket,
                &json!({"status":200,"content_type":"text/event-stream"}),
            )
            .await
            .unwrap();
            socket.get_mut().write_u32(0).await.unwrap();
        });
        assert_eq!(sent.unwrap().status(), StatusCode::OK);
        assert!(matches!(
            source.send(&identity).await,
            Err(AppError::BadRequest(_))
        ));
    }

    /// 写账本失败有独立阶段，私有事件源在该失败中收不到发送指令。@return 无。
    #[tokio::test]
    async fn ledger_failure_stops_before_source_submission() {
        let source = Source::new();
        let identity = source.identity();
        let (prepared, mut socket) = tokio::join!(source.prepare(&identity, b"{}"), async {
            let (mut socket, mut reply) = source.receive("prepare").await;
            socket.read_exact(&mut [0; 2]).await.unwrap();
            reply["kind"] = json!("new");
            write_json(&mut socket, &reply).await.unwrap();
            socket
        });
        assert_eq!(prepared.unwrap().status(), StatusCode::NO_CONTENT);
        let path = source
            .sender
            .submission_storage
            .join("tui-v2-submissions.lock");
        std::fs::write(&path, b"").unwrap();
        set_permissions(&path, Permissions::from_mode(0o644)).unwrap();
        let response = source.send(&identity).await.unwrap();
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(response.headers()[TUI_ERROR_SOURCE], TUI_SUBMISSION_LEDGER);
        assert_eq!(socket.read(&mut [0]).await.unwrap(), 0);
        assert_eq!(source.sender.active(), 0);
    }

    /// 等锁耗尽本次预算时，截止后释放锁也不会补写提交事实。@return 无。
    #[tokio::test]
    async fn ledger_lock_deadline_leaves_no_submission() {
        let source = Source::new();
        let root = &source.sender.submission_storage;
        let lock = submission_log::lock(root).unwrap();
        let identity = source.identity();
        let result = submission_log::consume(
            root,
            &source.binding,
            &identity.reservation_id,
            identity.deadline_unix_ms,
            (Instant::now() + Duration::from_millis(30)).into_std(),
            submission_log::Terminal::Submitted,
        )
        .await;
        assert_eq!(result.unwrap_err().kind(), io::ErrorKind::TimedOut);
        drop(lock);
        assert!(
            !submission_log::was_consumed(
                root,
                &source.binding,
                Some(&identity.reservation_id),
                (Instant::now() + Duration::from_secs(1)).into_std(),
            )
            .await
            .unwrap()
        );
    }

    /// 两种终态共享文件锁。写入新终态时清除两类已过期记录。@return 无。
    #[tokio::test]
    async fn send_and_cancel_share_durable_admission_and_expiry_cleanup() {
        let source = Source::new();
        let log = source
            .sender
            .submission_storage
            .join("tui-v2-submissions.json");
        let expired = [Uuid::new_v4().to_string(), Uuid::new_v4().to_string()];
        std::fs::write(
            &log,
            serde_json::to_vec(&json!({"account_id":source.binding.account_id,
            "environment_id":source.binding.environment_id,"committed":{(&expired[0]):1},
            "cancelled":{(&expired[1]):1}}))
            .unwrap(),
        )
        .unwrap();
        set_permissions(&log, Permissions::from_mode(0o600)).unwrap();
        let identity = source.identity();
        let record = |terminal| {
            submission_log::consume(
                &source.sender.submission_storage,
                &source.binding,
                &identity.reservation_id,
                identity.deadline_unix_ms,
                (Instant::now() + Duration::from_secs(5)).into_std(),
                terminal,
            )
        };
        let (sent, cancelled) = tokio::join!(
            record(submission_log::Terminal::Submitted),
            record(submission_log::Terminal::Cancelled)
        );
        let sent = sent.unwrap();
        assert_ne!(sent, cancelled.unwrap());
        let disk: Value = serde_json::from_slice(&std::fs::read(log).unwrap()).unwrap();
        let (winner, loser) = if sent {
            ("committed", "cancelled")
        } else {
            ("cancelled", "committed")
        };
        assert_eq!(
            disk[winner],
            json!({(&identity.reservation_id): identity.deadline_unix_ms})
        );
        assert_eq!(disk[loser], json!({}));
    }

    /// 存储失效时不给出已取消的确认。@return 无。
    #[tokio::test]
    async fn cancel_requires_writable_private_storage() {
        let source = Source::new();
        set_permissions(
            &source.sender.submission_storage,
            Permissions::from_mode(0o750),
        )
        .unwrap();
        assert!(matches!(
            source.cancel(&source.identity()).await,
            Err(AppError::ServiceUnavailable(_))
        ));
    }
}
