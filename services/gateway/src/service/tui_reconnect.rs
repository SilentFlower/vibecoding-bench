//! 一个真实 V2 工具续轮只读一次发送器响应，重连从相同的公开响应开头读取。

use std::collections::HashMap;
use std::future::{Future, pending};
use std::io;
use std::mem::size_of;
use std::pin::Pin;
use std::sync::atomic::Ordering;
use std::sync::{Arc, Mutex, Weak};
use std::time::Duration;

use axum::body::{Body, Bytes};
use axum::http::{HeaderMap, StatusCode};
use axum::response::Response;
use futures_util::{StreamExt, stream};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tokio::sync::{OwnedSemaphorePermit, Semaphore, mpsc, watch};
use tokio::time::{Instant, sleep_until};

use super::diagnostics;
use super::request_session::hash_json;
use super::runtime_transport::{
    TuiBodyPolicy, tui_agent_header, tui_cli_format, tui_model_headers,
};
use super::system_update::{InferenceCutover, UpdateActivity};
use super::tui_native_drain::Delivery;
use super::usage::ReconnectUsage;
use crate::error::AppError;

// 现场首次重试约 6 秒，同包后续重试在 8 秒内。此期限从最后一位有效读者离开时起算。
const GRACE: Duration = Duration::from_secs(10);
// 与 AGY 续轮缓存相同的进程级预算。预算不足时正常连接仍逐块传输。
const CACHE_BYTES: usize = 64 * 1024 * 1024;
type Key = [u8; 32];
type Chunk = Result<Bytes, &'static str>;

/// 计算一次工具结果生成的完整比较身份。@param principal 入口令牌。@param session 原会话。
/// @param body 原消息。@param headers 入站头。@param native 原生格式。@param policy 正文策略。
/// @param query 公开查询参数。@return 只用于本服务的索引摘要。
pub(super) fn key(
    principal: i64,
    session: Option<&str>,
    body: &Value,
    headers: &HeaderMap,
    native: bool,
    policy: TuiBodyPolicy,
    query: &str,
) -> Result<Key, AppError> {
    let mut hash = Sha256::new();
    let formats: Vec<_> = headers
        .get_all("accept-encoding")
        .iter()
        .map(|v| v.as_bytes())
        .collect();
    let agent = if native {
        tui_agent_header(headers)?
    } else {
        None
    };
    hash_json(
        &mut hash,
        &json!([
            principal,
            session,
            native,
            policy,
            query,
            formats,
            if native {
                tui_cli_format(headers)
            } else {
                None
            },
            agent,
            tui_model_headers(headers, true)?
        ]),
        false,
    );
    hash_json(&mut hash, body, false);
    Ok(hash.finalize().into())
}

#[derive(Clone)]
pub(super) struct Reconnects {
    entries: Arc<Mutex<HashMap<Key, Arc<Reply>>>>,
    budget: Arc<Semaphore>,
}

impl Default for Reconnects {
    fn default() -> Self {
        Self {
            entries: Default::default(),
            budget: Arc::new(Semaphore::new(CACHE_BYTES)),
        }
    }
}

struct Saved {
    bytes: Bytes,
    _permit: OwnedSemaphorePermit,
}

#[derive(Default)]
struct Output {
    original: Option<Interest>,
    headers: Option<HeaderMap>,
    prefix: Vec<Saved>,
    delivery: Option<Arc<Delivery>>,
    failed: bool,
    prepare_error: Option<AppError>,
    readers: Vec<mpsc::Sender<Chunk>>,
    overflow: bool,
    complete: bool,
    disconnected: bool,
}

pub(super) struct Reply {
    account: i64,
    binding: String,
    output: Mutex<Output>,
    changed: watch::Sender<()>,
    readers: watch::Sender<Readers>,
}

pub(super) enum Reservation {
    First(Writer),
    Existing(Arc<Reply>),
}

pub(super) struct Writer {
    index: Reconnects,
    key: Key,
    reply: Arc<Reply>,
}

impl Reconnects {
    /// 在调度前定位原账号，随后仍须经过本次访问过滤及绑定核对。@param key 请求摘要。@return 原账号。
    pub(super) fn account(&self, key: &Key) -> Option<i64> {
        self.entries.lock().unwrap().get(key).map(|v| v.account)
    }

    /// 注册唯一读模型方。@param key 请求摘要。@param account 已授权账号。@param binding 当前绑定。
    /// @return 新的写者或已存在的同轮响应。
    pub(super) fn reserve(
        &self,
        key: Key,
        account: i64,
        binding: &str,
    ) -> Result<Reservation, AppError> {
        let mut entries = self.entries.lock().unwrap();
        if let Some(entry) = entries.get(&key) {
            if entry.account != account || entry.binding != binding {
                return Err(AppError::BadRequest("原工具轮的账号绑定已变化".into()));
            }
            return Ok(Reservation::Existing(entry.clone()));
        }
        // 初次请求在等待响应头时也是有效读者，发布响应时把同一个凭证交给正文。
        let readers = watch::channel(Readers {
            active: 1,
            deadline: None,
        })
        .0;
        let reply = Arc::new(Reply {
            account,
            binding: binding.to_owned(),
            output: Mutex::new(Output {
                original: Some(Interest(readers.clone())),
                ..Output::default()
            }),
            changed: watch::channel(()).0,
            readers,
        });
        entries.insert(key, reply.clone());
        Ok(Reservation::First(Writer {
            index: self.clone(),
            key,
            reply,
        }))
    }
}

#[derive(Clone, Default)]
pub(super) struct BeforeHeaders(Arc<Mutex<Option<(Weak<Reply>, Arc<Delivery>)>>>);

struct PendingHeaders {
    operation: Option<Pin<Box<dyn Future<Output = Response> + Send>>>,
    owner: BeforeHeaders,
    cutover: Option<InferenceCutover>,
}

#[derive(Clone, Copy)]
struct Readers {
    active: usize,
    deadline: Option<Instant>,
}

async fn no_readers(mut readers: watch::Receiver<Readers>) {
    loop {
        let deadline = {
            let current = readers.borrow_and_update();
            if current
                .deadline
                .is_some_and(|deadline| Instant::now() >= deadline)
            {
                return;
            }
            current.deadline
        };
        if let Some(deadline) = deadline {
            tokio::select! {
                _ = sleep_until(deadline) => {},
                changed = readers.changed() => if changed.is_err() { return; },
            }
        } else if readers.changed().await.is_err() {
            return;
        }
    }
}

impl BeforeHeaders {
    /// 在实际提交边界登记可接回的唯一生成。@param writer 本轮写者。@param delivery 数据库步骤。
    pub(super) fn submitted(&self, writer: &Writer, delivery: &Arc<Delivery>) {
        *self.0.lock().unwrap() = Some((Arc::downgrade(&writer.reply), delivery.clone()));
    }

    /// 在公开连接上执行，只有已提交的工具轮才在连接断开时继续等待原回复。
    /// @param future 已鉴权请求。@param cutover 维护取消信号。@return 公开响应。
    pub(super) async fn run(
        self,
        future: impl Future<Output = Response> + Send + 'static,
        cutover: Option<InferenceCutover>,
    ) -> Response {
        let mut pending = PendingHeaders {
            operation: Some(Box::pin(future)),
            owner: self,
            cutover,
        };
        let response = pending.operation.as_mut().unwrap().await;
        pending.operation.take();
        response
    }
}

impl Drop for PendingHeaders {
    fn drop(&mut self) {
        let Some(operation) = self.operation.take() else {
            return;
        };
        let Some((reply, delivery)) = self.owner.0.lock().unwrap().take() else {
            return;
        };
        let Some(reply) = reply.upgrade() else { return };
        {
            let mut out = reply.output.lock().unwrap();
            out.disconnected = true;
            out.original.take();
        }
        let mut cutover = self.cutover.take();
        tokio::spawn(async move {
            let cancel = async {
                if let Some(signal) = &mut cutover {
                    if !signal.interrupted() && !signal.is_cancelled() {
                        signal.interrupt().await;
                    }
                } else {
                    pending().await
                }
            };
            tokio::select! {biased; _=cancel=>{
                if let Err(error)=delivery.cancel().await{tracing::warn!(%error,"维护取消的工具回执待核对");}
            }, _=no_readers(reply.readers.subscribe())=>{},_=operation=>{}}
        });
    }
}

struct Interest(watch::Sender<Readers>);

impl Interest {
    fn join(reply: &Reply) -> Result<Self, AppError> {
        let joined = reply.readers.send_if_modified(|readers| {
            if readers
                .deadline
                .is_some_and(|deadline| Instant::now() >= deadline)
            {
                return false;
            }
            readers.active += 1;
            readers.deadline = None;
            true
        });
        if joined {
            Ok(Self(reply.readers.clone()))
        } else {
            Err(AppError::ServiceUnavailable(
                "原回复的重连窗口已结束，请重试本轮".into(),
            ))
        }
    }
}

impl Drop for Interest {
    fn drop(&mut self) {
        self.0.send_modify(|readers| {
            readers.active -= 1;
            if readers.active == 0 {
                readers.deadline = Some(Instant::now() + GRACE);
            }
        });
    }
}

struct Reader {
    _interest: Interest,
    reply: Arc<Reply>,
    clean: bool,
}

impl Drop for Reader {
    fn drop(&mut self) {
        if !self.clean {
            self.reply.output.lock().unwrap().disconnected = true;
        }
    }
}

impl Reader {
    /// 逐块共享缓存前缀，预算耗尽后沿当前读者的有界通道继续。@return 真实下一块。
    async fn next(
        &mut self,
        position: &mut usize,
        changes: &mut watch::Receiver<()>,
        rx: &mut mpsc::Receiver<Chunk>,
    ) -> Option<Chunk> {
        loop {
            changes.borrow_and_update();
            let (overflow, complete) = {
                let out = self.reply.output.lock().unwrap();
                if let Some(saved) = out.prefix.get(*position) {
                    *position += 1;
                    return Some(Ok(saved.bytes.clone()));
                }
                (out.overflow, out.complete)
            };
            if overflow {
                if let Some(chunk) = rx.recv().await {
                    return Some(chunk);
                }
            } else if !complete {
                if changes.changed().await.is_ok() {
                    continue;
                }
            }
            let (failed, delivery) = {
                let out = self.reply.output.lock().unwrap();
                (out.failed, out.delivery.clone())
            };
            self.clean = true;
            if failed {
                return Some(Err("原模型流中断，请重试本轮"));
            }
            if let Some(delivery) = delivery
                && let Err(error) = delivery.acknowledge().await
            {
                tracing::warn!(%error,"工具回复交付确认待核对");
            }
            return None;
        }
    }
}

impl Output {
    fn check_subscription(&self, already_admitted: bool) -> Result<(), AppError> {
        if let Some(error) = &self.prepare_error {
            return Err(error.clone());
        }
        if self.failed {
            return Err(AppError::ServiceUnavailable(
                "原工具轮已中断，请重试".into(),
            ));
        }
        if self.complete && !self.disconnected && !already_admitted {
            return Err(AppError::BadRequest(
                "该工具组的回执已处理，请从上一条响应继续".into(),
            ));
        }
        if self.overflow {
            return Err(AppError::ServiceUnavailable(
                "本轮回复超过留存预算，请使用仍在读取的原连接".into(),
            ));
        }
        Ok(())
    }
}

impl Reply {
    /// 从首帧读取。@param first 是否为原订阅者。@return 原头部和字节流。
    pub(super) async fn subscribe(self: &Arc<Self>, first: bool) -> Result<Response, AppError> {
        let mut changes = self.changed.subscribe();
        let mut waiting = None;
        let (headers, delivery) = loop {
            changes.borrow_and_update();
            {
                let out = self.output.lock().unwrap();
                out.check_subscription(first || waiting.is_some())?;
                if let Some(headers) = out.headers.clone() {
                    break (headers, out.delivery.clone());
                }
                // 已通过身份和状态核验的请求可在首包前接手等待，尤其是需聚合的 JSON。
                if !first && waiting.is_none() {
                    waiting = Some(Interest::join(self)?);
                }
            }
            changes
                .changed()
                .await
                .map_err(|_| AppError::ServiceUnavailable("原回复已释放".into()))?;
        };
        if !first
            && let Some(delivery) = delivery
            && !delivery.replayable().await?
        {
            return Err(AppError::BadRequest(
                "下一组工具的回执已经推进，请从最新回复继续".into(),
            ));
        }
        let (interest, rx) = {
            let mut out = self.output.lock().unwrap();
            // 数据库核验期间，生产者可能已经耗尽缓存。只给仍可交付的回复登记读者。
            out.check_subscription(true)?;
            let interest = if first {
                let Some(original) = out.original.take() else {
                    // 原连接在首包前已断开，后台仍负责向真正接回的读者发布完整响应。
                    return Ok(Response::new(Body::empty()));
                };
                original
            } else {
                let interest = match waiting {
                    Some(interest) => interest,
                    None => Interest::join(self)?,
                };
                diagnostics::local_outcome(if out.complete {
                    "tui_reconnect_cached"
                } else {
                    "tui_reconnect_stream"
                });
                interest
            };
            let (tx, rx) = mpsc::channel(1);
            if !out.complete {
                out.readers.retain(|sender| !sender.is_closed());
                out.readers.push(tx);
            }
            (interest, rx)
        };
        let reader = Reader {
            _interest: interest,
            reply: self.clone(),
            clean: false,
        };
        let body = stream::unfold(
            (reader, 0, changes, rx),
            |(mut reader, mut position, mut changes, mut rx)| async move {
                if reader.clean {
                    return None;
                }
                let chunk = reader.next(&mut position, &mut changes, &mut rx).await?;
                Some((
                    chunk.map_err(io::Error::other),
                    (reader, position, changes, rx),
                ))
            },
        );
        let mut response = Response::new(Body::from_stream(body));
        *response.headers_mut() = headers;
        Ok(response)
    }
}

impl Drop for Writer {
    fn drop(&mut self) {
        self.release_entry();
        let mut out = self.reply.output.lock().unwrap();
        if !out.complete {
            out.failed = true;
            out.complete = true;
        }
        out.readers.clear();
        self.reply.changed.send_replace(());
    }
}

impl Writer {
    fn release_entry(&self) {
        let mut entries = self.index.entries.lock().unwrap();
        if entries
            .get(&self.key)
            .is_some_and(|entry| Arc::ptr_eq(entry, &self.reply))
        {
            entries.remove(&self.key);
        }
    }

    /// 将同次准备的真实拒绝交给等待响应头的重试。@param error 原发送器的公开错误。
    pub(super) fn rejected(&self, error: &AppError) {
        self.reply.output.lock().unwrap().prepare_error = Some(error.clone());
        self.reply.changed.send_replace(());
    }

    /// 保留真实响应的读取、用量和名额直至终态或最后一个读者离开超过窗口。
    /// @param response 已挂载原生观察器的响应。@param cutover 管理取消信号。@param delivery 原回执。
    /// @param activity 原维护活动名额。@param usage 原推理的累计用量。@return 原客户端响应。
    pub(super) async fn publish(
        self,
        response: Response,
        mut cutover: Option<InferenceCutover>,
        delivery: Arc<Delivery>,
        activity: Option<Arc<UpdateActivity>>,
        mut usage: Option<ReconnectUsage>,
    ) -> Result<Response, AppError> {
        if response.status() != StatusCode::OK {
            return Ok(response);
        }
        let (parts, body) = response.into_parts();
        {
            let mut out = self.reply.output.lock().unwrap();
            out.headers = Some(parts.headers);
            out.delivery = Some(delivery.clone());
        }
        let first = self.reply.subscribe(true).await?;
        self.reply.changed.send_replace(());
        let readers = self.reply.readers.subscribe();
        let trace = diagnostics::current_trace();
        let drive = async move {
            let copy = async {
                let mut bytes = body.into_data_stream();
                while let Some(frame) = bytes.next().await {
                    let Ok(bytes) = frame else { return false };
                    if bytes.is_empty() {
                        continue;
                    }
                    if let Some(usage) = &mut usage {
                        usage.observe(&bytes).await;
                    }
                    let sinks = {
                        let mut out = self.reply.output.lock().unwrap();
                        if !out.overflow {
                            let permit =
                                u32::try_from(bytes.len().saturating_add(2 * size_of::<Saved>()))
                                    .ok()
                                    .and_then(|n| {
                                        self.index.budget.clone().try_acquire_many_owned(n).ok()
                                    });
                            if let Some(permit) = permit {
                                out.prefix.push(Saved {
                                    bytes: Bytes::copy_from_slice(&bytes),
                                    _permit: permit,
                                });
                                self.reply.changed.send_replace(());
                                continue;
                            }
                            out.overflow = true;
                            self.reply.changed.send_replace(());
                        }
                        out.readers.retain(|s| !s.is_closed());
                        if out.readers.is_empty() {
                            return false;
                        }
                        out.readers.clone()
                    };
                    for sink in sinks {
                        let _ = sink.send(Ok(bytes.clone())).await;
                    }
                }
                delivery.verified.load(Ordering::Acquire)
            };
            let abandoned = no_readers(readers);
            let cancel = async {
                match &mut cutover {
                    Some(signal) => signal.interrupt().await,
                    None => pending().await,
                }
            };
            let (complete, cancelled) = tokio::select! {biased; _=cancel=>(false,true),_=abandoned=>(false,false),complete=copy=>(complete,false)};
            if cancelled && let Err(error) = delivery.cancel().await {
                tracing::warn!(%error,"维护取消的工具回执待核对");
            }
            {
                let mut out = self.reply.output.lock().unwrap();
                out.complete = true;
                out.failed = !complete;
                out.readers.clear();
                self.reply.changed.send_replace(());
            }
            if !complete {
                // 已知残缺的前缀不能交给重试。用量收口可能等待数据库，新的恢复继续走原绑定核验。
                self.release_entry();
            }
            if let Some(usage) = usage {
                usage.finish(complete).await;
            }
            drop(activity);
            if complete {
                no_readers(self.reply.readers.subscribe()).await;
            }
            drop(self);
        };
        tokio::spawn(async move {
            match trace {
                Some(trace) => diagnostics::CURRENT_TRACE.scope(trace, drive).await,
                None => drive.await,
            }
        });
        Ok(first)
    }
}

#[cfg(test)]
mod tests {
    use super::{GRACE, Reconnects, Reservation};
    use tokio::time::Instant;

    /// 拒绝超预算的重连后，原空闲截止时间和观察通知均保持一致。
    #[tokio::test]
    async fn rejected_reconnect_preserves_idle_deadline() {
        let index = Reconnects::default();
        let Reservation::First(writer) = index.reserve([0; 32], 1, "binding").unwrap() else {
            panic!("首请求应取得写者");
        };
        let reply = &writer.reply;
        {
            let mut out = reply.output.lock().unwrap();
            out.overflow = true;
            out.original.take();
        }
        let mut changes = reply.readers.subscribe();
        let before = changes.borrow_and_update().deadline.unwrap();
        assert!(before <= Instant::now() + GRACE);
        assert!(reply.subscribe(false).await.is_err());
        assert!(!changes.has_changed().unwrap());
        assert_eq!(changes.borrow().deadline, Some(before));
        assert_eq!(changes.borrow().active, 0);
    }
}
