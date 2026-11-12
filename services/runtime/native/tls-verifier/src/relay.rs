//! 一条原生连接对应一条上游连接，HTTP 字节从不重新序列化。

use crate::profile::{PROFILE_ID, client_config};
use crate::protocol::{Binding, Capture, Event, Expected, Setup};
use base64::{Engine, engine::general_purpose::STANDARD};
use rustls::{RootCertStore, ServerConfig};
use rustls_pki_types::ServerName;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fs::{File, read_dir, read_link, read_to_string};
use std::future::pending;
use std::io::{BufReader, Result as IoResult, Write, stdout};
use std::process;
use std::result::Result as StdResult;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, copy, split};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{Notify, watch};
use tokio::task::{JoinHandle, spawn};
use tokio::{pin, select};
use tokio_rustls::{TlsAcceptor, TlsConnector};

type Result<T> = StdResult<T, &'static str>;
const HEAD_LIMIT: usize = 128 * 1024;

struct Active {
    binding: Binding,
    expected: Option<Expected>,
    reserved: bool,
}

struct Connection {
    worker_id: String,
    cancel: watch::Sender<bool>,
    task: JoinHandle<()>,
}

/// 单实例状态，只能由私有控制帧改变活动作业。
pub struct Relay {
    instance: String,
    setup: Setup,
    acceptor: TlsAcceptor,
    connector: TlsConnector,
    active: Mutex<Option<Active>>,
    expected_ready: Notify,
    connections: Mutex<HashMap<u64, Connection>>,
    next_connection: AtomicU64,
    sequence: AtomicU64,
}

impl Relay {
    /// 建立限定目标的私有监听器，保留上游证书校验。
    /// @param instance 父进程的实例标识。
    /// @param setup 经过启动校验的不可变配置。
    /// @return 已配置的中继和回环监听器；配置无效时返回固定错误。
    pub async fn create(instance: String, setup: Setup) -> Result<(Arc<Self>, TcpListener)> {
        if setup.capture_bytes < 1024
            || setup.capture_bytes > 8 * 1024 * 1024
            || setup.target_host.is_empty()
            || setup.target_port == 0
            || setup.authorization.is_empty()
        {
            return Err("invalid_configuration");
        }
        let mut certificate = BufReader::new(
            File::open(&setup.certificate_file).map_err(|_| "certificate_unavailable")?,
        );
        let certificates = rustls_pemfile::certs(&mut certificate)
            .collect::<IoResult<Vec<_>>>()
            .map_err(|_| "certificate_invalid")?;
        let mut key =
            BufReader::new(File::open(&setup.key_file).map_err(|_| "certificate_unavailable")?);
        let key = rustls_pemfile::private_key(&mut key)
            .map_err(|_| "certificate_invalid")?
            .ok_or("certificate_invalid")?;
        let mut server = ServerConfig::builder()
            .with_no_client_auth()
            .with_single_cert(certificates, key)
            .map_err(|_| "certificate_invalid")?;
        server.alpn_protocols = vec![b"http/1.1".to_vec()];
        let mut roots = RootCertStore::empty();
        roots.extend(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
        if let Some(path) = &setup.ca_file {
            let mut reader = BufReader::new(File::open(path).map_err(|_| "ca_unavailable")?);
            let mut count = 0;
            for certificate in rustls_pemfile::certs(&mut reader) {
                roots
                    .add(certificate.map_err(|_| "ca_invalid")?)
                    .map_err(|_| "ca_invalid")?;
                count += 1;
            }
            if count == 0 {
                return Err("ca_invalid");
            }
        }
        let listener = TcpListener::bind(("127.0.0.1", 0))
            .await
            .map_err(|_| "listen_failed")?;
        Ok((
            Arc::new(Self {
                instance,
                setup,
                acceptor: TlsAcceptor::from(Arc::new(server)),
                connector: TlsConnector::from(Arc::new(client_config(roots))),
                active: Mutex::new(None),
                expected_ready: Notify::new(),
                connections: Mutex::new(HashMap::new()),
                next_connection: AtomicU64::new(1),
                sequence: AtomicU64::new(1),
            }),
            listener,
        ))
    }

    /// 输出受信任私有事件；管道失效后退出，不能继续盲目转发。
    /// @param event 已构造事件。
    /// @return 无。
    pub fn emit(&self, event: Event) {
        let mut output = stdout().lock();
        let frame = json!({ "schema_version": 1, "instance_id": self.instance, "event": event });
        if serde_json::to_writer(&mut output, &frame).is_err()
            || output.write_all(b"\n").is_err()
            || output.flush().is_err()
        {
            process::exit(1);
        }
    }

    /// 绑定作业；同实例只接受一个串行原生发送器。
    /// @param binding 实际工作进程及请求标识。
    /// @return 绑定成功或明确拒绝。
    pub fn begin(&self, binding: Binding) -> Result<()> {
        let mut active = self.active.lock().unwrap();
        if active.is_some()
            || binding.request_id.is_empty()
            || binding.worker_id.is_empty()
            || binding.worker_pid == 0
        {
            return Err("binding_invalid");
        }
        *active = Some(Active {
            binding,
            expected: None,
            reserved: false,
        });
        Ok(())
    }

    /// 接收原生构造点证据，唤醒尚未执行任何上游写入的连接。
    /// @param expected 同次 cc_prepared 的长度、哈希和有序头。
    /// @return 接收成功或拒绝重复、错误归属。
    pub fn expected(&self, expected: Expected) -> Result<()> {
        let mut active = self.active.lock().unwrap();
        let current = active.as_mut().ok_or("binding_missing")?;
        if current.binding.request_id != expected.request_id
            || current.expected.is_some()
            || expected.body_sha256.len() != 64
            || expected.cch_offset.is_some_and(|offset| {
                offset
                    .checked_add(5)
                    .is_none_or(|end| end > expected.body_bytes)
            })
        {
            return Err("expected_invalid");
        }
        current.expected = Some(expected);
        self.expected_ready.notify_waiters();
        Ok(())
    }

    /// 停止当前作业，取消时先收集连接上的部分写出再确认。
    /// @param request_id 活动作业。
    /// @param close_connections 是否退休此物理进程的连接。
    /// @return 连接收口且当前作业已清除。
    pub async fn finish(&self, request_id: &str, close_connections: bool) -> Result<()> {
        let binding = {
            let active = self.active.lock().unwrap();
            let current = active.as_ref().ok_or("binding_missing")?;
            if current.binding.request_id != request_id {
                return Err("binding_invalid");
            }
            current.binding.clone()
        };
        if close_connections {
            self.close_connections(Some(&binding.worker_id)).await;
        }
        *self.active.lock().unwrap() = None;
        self.expected_ready.notify_waiters();
        Ok(())
    }

    async fn close_connections(&self, worker: Option<&str>) {
        let tasks = {
            let mut connections = self.connections.lock().unwrap();
            let ids: Vec<_> = connections
                .iter()
                .filter(|(_, connection)| worker.is_none_or(|id| connection.worker_id == id))
                .map(|(id, _)| *id)
                .collect();
            ids.into_iter()
                .filter_map(|id| connections.remove(&id))
                .collect::<Vec<_>>()
        };
        for connection in &tasks {
            let _ = connection.cancel.send(true);
        }
        for connection in tasks {
            let _ = connection.task.await;
        }
    }

    /// 结束所有私有连接；EOF 与显式关闭使用相同路径。
    /// @return 所有连接任务退出。
    pub async fn shutdown(&self) {
        self.close_connections(None).await;
    }

    /// 接收私有 CONNECT；每连接的归属在接入时固定。
    /// @param listener 已绑定的回环监听器。
    /// @return 监听失败时退出，不重试业务。
    pub async fn listen(self: Arc<Self>, listener: TcpListener) {
        while let Ok((socket, _)) = listener.accept().await {
            let binding = self
                .active
                .lock()
                .unwrap()
                .as_ref()
                .map(|active| active.binding.clone());
            let Some(binding) = binding else {
                continue;
            };
            let id = self.next_connection.fetch_add(1, Ordering::SeqCst);
            let (cancel, mut canceled) = watch::channel(false);
            let relay = self.clone();
            let worker_id = binding.worker_id.clone();
            let task = spawn(async move {
                let progress = Arc::new(Mutex::new(None));
                let result = select! {
                    result = relay.connection(socket, id, &binding, progress.clone()) => result,
                    _ = canceled.changed() => Err("connection_canceled"),
                };
                if let Some(observation) = progress.lock().unwrap().take() {
                    relay.capture(
                        id,
                        observation,
                        false,
                        result.err().unwrap_or("connection_incomplete"),
                    );
                } else if let Err(reason) = result
                    && !matches!(
                        reason,
                        "connection_closed"
                            | "connection_canceled"
                            | "peer_identity_failed"
                            | "connect_rejected"
                    )
                {
                    // 复用连接的故障属于当时的活动作业，不能固定归给建立连接的第一轮。
                    let current = relay
                        .active
                        .lock()
                        .unwrap()
                        .as_ref()
                        .filter(|active| active.binding.worker_id == binding.worker_id)
                        .map(|active| active.binding.clone());
                    if current.is_some() {
                        relay.emit(Event::Failure {
                            binding: current,
                            reason,
                        });
                    }
                }
            });
            let mut connections = self.connections.lock().unwrap();
            connections.retain(|_, connection| !connection.task.is_finished());
            connections.insert(
                id,
                Connection {
                    worker_id,
                    cancel,
                    task,
                },
            );
        }
    }

    async fn upstream(&self, native_connect: &[u8]) -> Result<TcpStream> {
        if let Some(proxy) = &self.setup.proxy {
            let mut stream = TcpStream::connect((proxy.host.as_str(), proxy.port))
                .await
                .map_err(|_| "proxy_connect_failed")?;
            stream.set_nodelay(true).map_err(|_| "socket_failed")?;
            let connect = proxy_connect(native_connect, proxy.authorization.as_deref());
            stream
                .write_all(&connect)
                .await
                .map_err(|_| "proxy_connect_failed")?;
            let head = read_head(&mut stream).await?;
            let line = head
                .split(|byte| *byte == b'\n')
                .next()
                .ok_or("proxy_rejected")?;
            if !line.starts_with(b"HTTP/1.1 200 ") && !line.starts_with(b"HTTP/1.0 200 ") {
                return Err("proxy_rejected");
            }
            Ok(stream)
        } else {
            let stream =
                TcpStream::connect((self.setup.target_host.as_str(), self.setup.target_port))
                    .await
                    .map_err(|_| "upstream_connect_failed")?;
            stream.set_nodelay(true).map_err(|_| "socket_failed")?;
            Ok(stream)
        }
    }

    async fn connection(
        &self,
        mut socket: TcpStream,
        id: u64,
        binding: &Binding,
        progress: Arc<Mutex<Option<Observation>>>,
    ) -> Result<()> {
        verify_peer(&socket, binding.worker_pid)?;
        socket.set_nodelay(true).map_err(|_| "socket_failed")?;
        let connect = read_head(&mut socket).await?;
        let (line, headers) = parse_head(&connect)?;
        if line != format!("CONNECT {} HTTP/1.1", self.setup.authority)
            || headers
                .iter()
                .filter(|(name, _)| name.eq_ignore_ascii_case("proxy-authorization"))
                .map(|(_, value)| value.as_str())
                .collect::<Vec<_>>()
                != vec![self.setup.authorization.as_str()]
        {
            return Err("connect_rejected");
        }
        socket
            .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            .await
            .map_err(|_| "local_write_failed")?;
        let local = self
            .acceptor
            .accept(socket)
            .await
            .map_err(|_| "local_tls_failed")?;
        // 先确认是本作业的 HTTP，再连接目标；TLS 失败不能导致业务自动重放。
        let (mut local_read, mut local_write) = split(local);
        let head = read_head(&mut local_read).await?;
        let (expected, current) = self.reserve(&head, binding).await?;
        *progress.lock().unwrap() = Some(Observation::new(
            current,
            expected,
            head.clone(),
            self.setup.capture_bytes,
        )?);
        let upstream = self.upstream(&connect).await?;
        let server =
            ServerName::try_from(self.setup.target_host.clone()).map_err(|_| "target_invalid")?;
        let upstream = self
            .connector
            .connect(server, upstream)
            .await
            .map_err(|_| "upstream_tls_failed")?;
        let (mut upstream_read, mut upstream_write) = split(upstream);
        let outgoing = async {
            let mut head = head;
            loop {
                write_observed(&mut upstream_write, &head, false, &progress).await?;
                let length = progress
                    .lock()
                    .unwrap()
                    .as_ref()
                    .ok_or("capture_missing")?
                    .expected
                    .body_bytes;
                let mut remaining = length;
                let mut buffer = [0u8; 16 * 1024];
                while remaining > 0 {
                    let next = remaining.min(buffer.len());
                    let count = local_read
                        .read(&mut buffer[..next])
                        .await
                        .map_err(|_| "local_read_failed")?;
                    if count == 0 {
                        return Err("body_incomplete");
                    }
                    write_observed(&mut upstream_write, &buffer[..count], true, &progress).await?;
                    remaining -= count;
                }
                upstream_write
                    .flush()
                    .await
                    .map_err(|_| "upstream_flush_failed")?;
                let observation = progress.lock().unwrap().take().ok_or("capture_missing")?;
                self.capture(id, observation, true, "flushed");
                head = match read_head(&mut local_read).await {
                    Ok(head) => head,
                    Err("connection_closed") => {
                        // 客户端写半边结束后，仍允许上游把已发送请求的响应完整返回。
                        upstream_write
                            .shutdown()
                            .await
                            .map_err(|_| "upstream_flush_failed")?;
                        return pending::<Result<()>>().await;
                    }
                    Err(reason) => return Err(reason),
                };
                let (expected, current) = self.reserve(&head, binding).await?;
                *progress.lock().unwrap() = Some(Observation::new(
                    current,
                    expected,
                    head.clone(),
                    self.setup.capture_bytes,
                )?);
            }
        };
        let incoming = async {
            copy(&mut upstream_read, &mut local_write)
                .await
                .map_err(|_| "response_copy_failed")?;
            local_write
                .shutdown()
                .await
                .map_err(|_| "local_write_failed")?;
            Ok(())
        };
        select! { result = outgoing => result, result = incoming => result }
    }

    async fn reserve(&self, head: &[u8], connection: &Binding) -> Result<(Expected, Binding)> {
        let (line, headers) = parse_head(head)?;
        if !line.starts_with("POST /") || !line.ends_with(" HTTP/1.1") {
            return Err("http_unsupported");
        }
        loop {
            let notified = self.expected_ready.notified();
            pin!(notified);
            // 先登记等待者再检查状态，避免另一线程的 expected 恰好落在检查与 await 之间。
            notified.as_mut().enable();
            {
                let mut active = self.active.lock().unwrap();
                let current = active.as_mut().ok_or("binding_missing")?;
                if current.binding.worker_id != connection.worker_id
                    || current.binding.worker_pid != connection.worker_pid
                    || current.reserved
                {
                    return Err("binding_invalid");
                }
                if let Some(expected) = &current.expected {
                    let values = |name: &str| {
                        headers
                            .iter()
                            .filter(|(key, _)| key.eq_ignore_ascii_case(name))
                            .map(|(_, value)| value.as_str())
                            .collect::<Vec<_>>()
                    };
                    if values("host") != vec![self.setup.host_header.as_str()]
                        || values("content-length")
                            != vec![expected.body_bytes.to_string().as_str()]
                        || !values("transfer-encoding").is_empty()
                    {
                        return Err("http_framing_invalid");
                    }
                    // 原生新增的 Host/长度/压缩头允许存在，已准备的业务头必须全部保持。
                    for (name, value) in &expected.headers {
                        if !headers.iter().any(|(actual, content)| {
                            actual.eq_ignore_ascii_case(name) && content == value
                        }) {
                            return Err("header_mismatch");
                        }
                    }
                    current.reserved = true;
                    return Ok((expected.clone(), current.binding.clone()));
                }
            }
            notified.await;
        }
    }

    fn capture(&self, id: u64, observation: Observation, flushed: bool, reason: &str) {
        let body_sha256 = hex::encode(observation.body_hash.finalize());
        let normalized_sha256 = hex::encode(observation.normalized.finalize());
        let complete = observation.body_bytes == observation.expected.body_bytes
            && observation.http_bytes == observation.head.len() + observation.expected.body_bytes;
        let verified = complete
            && flushed
            && normalized_sha256 == observation.expected.body_sha256
            && (observation.expected.cch_offset.is_none()
                || (observation.cch.len() == 5
                    && observation.cch.iter().all(u8::is_ascii_hexdigit)
                    && observation.cch != b"00000"));
        let head_complete = observation.http_bytes >= observation.head.len();
        self.emit(Event::Capture {
            capture: Capture {
                binding: observation.binding,
                connection_id: id,
                sequence: self.sequence.fetch_add(1, Ordering::SeqCst),
                body_preview_b64: STANDARD.encode(observation.preview),
                head_b64: STANDARD.encode(
                    &observation.head[..observation.http_bytes.min(observation.head.len())],
                ),
                headers: if head_complete {
                    observation.headers
                } else {
                    vec![]
                },
                body_bytes: observation.body_bytes,
                body_sha256,
                normalized_sha256,
                http_bytes: observation.http_bytes,
                http_sha256: hex::encode(observation.http_hash.finalize()),
                complete,
                flushed,
                verified,
                captured_unix_ms: SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_millis() as u64,
                reason: if flushed && !verified {
                    "integrity_mismatch".into()
                } else {
                    reason.into()
                },
            },
        });
    }
}

struct Observation {
    binding: Binding,
    expected: Expected,
    head: Vec<u8>,
    headers: Vec<(String, String)>,
    preview: Vec<u8>,
    limit: usize,
    body_bytes: usize,
    http_bytes: usize,
    body_hash: Sha256,
    normalized: Sha256,
    http_hash: Sha256,
    cch: Vec<u8>,
}

impl Observation {
    fn new(binding: Binding, expected: Expected, head: Vec<u8>, limit: usize) -> Result<Self> {
        let (_, headers) = parse_head(&head)?;
        Ok(Self {
            binding,
            expected,
            head,
            headers,
            preview: vec![],
            limit,
            body_bytes: 0,
            http_bytes: 0,
            body_hash: Sha256::new(),
            normalized: Sha256::new(),
            http_hash: Sha256::new(),
            cch: vec![],
        })
    }

    fn record(&mut self, bytes: &[u8], body: bool) {
        self.http_hash.update(bytes);
        self.http_bytes += bytes.len();
        if !body {
            return;
        }
        self.body_hash.update(bytes);
        self.preview.extend_from_slice(
            &bytes[..bytes
                .len()
                .min(self.limit.saturating_sub(self.preview.len()))],
        );
        if let Some(offset) = self.expected.cch_offset {
            let start = offset.max(self.body_bytes);
            let end = (offset + 5).min(self.body_bytes + bytes.len());
            if start < end {
                self.normalized.update(&bytes[..start - self.body_bytes]);
                self.normalized.update(&b"00000"[..end - start]);
                self.cch
                    .extend_from_slice(&bytes[start - self.body_bytes..end - self.body_bytes]);
                self.normalized.update(&bytes[end - self.body_bytes..]);
            } else {
                self.normalized.update(bytes);
            }
        } else {
            self.normalized.update(bytes);
        }
        self.body_bytes += bytes.len();
    }
}

async fn write_observed<W: AsyncWrite + Unpin>(
    writer: &mut W,
    bytes: &[u8],
    body: bool,
    progress: &Arc<Mutex<Option<Observation>>>,
) -> Result<()> {
    let mut offset = 0;
    while offset < bytes.len() {
        let count = writer
            .write(&bytes[offset..])
            .await
            .map_err(|_| "upstream_write_failed")?;
        if count == 0 {
            return Err("upstream_write_failed");
        }
        progress
            .lock()
            .unwrap()
            .as_mut()
            .ok_or("capture_missing")?
            .record(&bytes[offset..offset + count], body);
        offset += count;
    }
    Ok(())
}

async fn read_head<R: AsyncRead + Unpin>(reader: &mut R) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    let mut byte = [0u8; 1];
    while bytes.len() < HEAD_LIMIT {
        if reader
            .read(&mut byte)
            .await
            .map_err(|_| "head_read_failed")?
            == 0
        {
            return Err("connection_closed");
        }
        bytes.push(byte[0]);
        if bytes.ends_with(b"\r\n\r\n") {
            return Ok(bytes);
        }
    }
    Err("head_unsupported")
}

fn parse_head(bytes: &[u8]) -> Result<(String, Vec<(String, String)>)> {
    // Latin-1 是 HTTP 字段的逐字节观测表示；禁止重新编码这个字符串后转发。
    let text: String = bytes.iter().map(|byte| char::from(*byte)).collect();
    let mut lines = text.split("\r\n");
    let line = lines.next().ok_or("head_invalid")?.to_string();
    let mut headers = Vec::new();
    for line in lines {
        if line.is_empty() {
            break;
        }
        let (name, value) = line.split_once(':').ok_or("head_invalid")?;
        if name.is_empty()
            || name
                .bytes()
                .any(|byte| !byte.is_ascii_alphanumeric() && !b"!#$%&'*+-.^_`|~".contains(&byte))
        {
            return Err("head_invalid");
        }
        headers.push((
            name.to_string(),
            value.trim_matches([' ', '\t']).to_string(),
        ));
    }
    Ok((line, headers))
}

fn verify_peer(socket: &TcpStream, pid: u32) -> Result<()> {
    let peer = socket.peer_addr().map_err(|_| "peer_identity_failed")?;
    let local = socket.local_addr().map_err(|_| "peer_identity_failed")?;
    if !peer.ip().is_loopback() || !peer.is_ipv4() {
        return Err("peer_identity_failed");
    }
    let table =
        read_to_string(format!("/proc/{pid}/net/tcp")).map_err(|_| "peer_identity_failed")?;
    let expected_local = format!("0100007F:{:04X}", peer.port());
    let expected_remote = format!("0100007F:{:04X}", local.port());
    let inode = table
        .lines()
        .skip(1)
        .find_map(|line| {
            let columns: Vec<_> = line.split_whitespace().collect();
            if columns.len() > 9
                && columns[1] == expected_local
                && columns[2] == expected_remote
                && columns[3] == "01"
            {
                Some(columns[9].to_string())
            } else {
                None
            }
        })
        .ok_or("peer_identity_failed")?;
    let expected_socket = format!("socket:[{inode}]");
    let descriptors = read_dir(format!("/proc/{pid}/fd")).map_err(|_| "peer_identity_failed")?;
    if descriptors.filter_map(|entry| entry.ok()).any(|entry| {
        read_link(entry.path())
            .ok()
            .is_some_and(|target| target.to_string_lossy() == expected_socket)
    }) {
        Ok(())
    } else {
        Err("peer_identity_failed")
    }
}

fn proxy_connect(native: &[u8], authorization: Option<&str>) -> Vec<u8> {
    let mut output = Vec::with_capacity(native.len());
    for line in native.split_inclusive(|byte| *byte == b'\n') {
        if let Some(colon) = line.iter().position(|byte| *byte == b':')
            && line[..colon].eq_ignore_ascii_case(b"proxy-authorization")
        {
            // 保留原生 CONNECT 的顺序及连接特征，仅把本地私有代理凭据换回冻结的上游代理凭据。
            if let Some(value) = authorization {
                output.extend_from_slice(&line[..colon + 1]);
                output.push(b' ');
                output.extend_from_slice(value.as_bytes());
                output.extend_from_slice(b"\r\n");
            }
        } else {
            output.extend_from_slice(line);
        }
    }
    output
}

/// 固定画像名称，供握手帧统一使用。
/// @return 已登记画像 ID。
pub fn profile() -> &'static str {
    PROFILE_ID
}

#[cfg(test)]
mod tests {
    use super::{
        Binding, Expected, Observation, Result, parse_head, proxy_connect, write_observed,
    };
    use sha2::{Digest, Sha256};
    use std::io::{Error, ErrorKind, Result as IoResult};
    use std::pin::Pin;
    use std::sync::{Arc, Mutex};
    use std::task::{Context, Poll};
    use tokio::io::AsyncWrite;

    fn observation(body: &[u8], offset: Option<usize>) -> Observation {
        Observation::new(
            Binding {
                request_id: "request".into(),
                worker_id: "worker".into(),
                worker_pid: 1,
            },
            Expected {
                request_id: "request".into(),
                body_bytes: body.len(),
                body_sha256: hex::encode(Sha256::digest(body)),
                cch_offset: offset,
                headers: vec![],
            },
            b"POST /v1/messages HTTP/1.1\r\nHost: fixture.local\r\n\r\n".to_vec(),
            64,
        )
        .unwrap()
    }

    #[test]
    fn cch_normalization_crosses_write_boundaries() {
        let original = b"prefix-00000-tail";
        let actual = b"prefix-abcde-tail";
        let mut observed = observation(original, Some(7));
        for part in actual.chunks(3) {
            observed.record(part, true);
        }
        assert_eq!(observed.body_bytes, actual.len());
        assert_eq!(
            hex::encode(observed.body_hash.finalize()),
            hex::encode(Sha256::digest(actual))
        );
        assert_eq!(
            hex::encode(observed.normalized.finalize()),
            hex::encode(Sha256::digest(original))
        );
        assert_eq!(observed.preview, actual);
        assert_eq!(observed.cch, b"abcde");
    }

    #[test]
    fn duplicate_header_order_and_latin_one_are_observed_without_reencoding() -> Result<()> {
        let (_, headers) =
            parse_head(b"POST / HTTP/1.1\r\nX-Repeat: a\r\nX-Repeat: b\r\nX-Latin: \xe9\r\n\r\n")?;
        assert_eq!(
            headers,
            vec![
                ("X-Repeat".into(), "a".into()),
                ("X-Repeat".into(), "b".into()),
                ("X-Latin".into(), "é".into())
            ]
        );
        Ok(())
    }

    #[test]
    fn connect_keeps_native_bytes_and_only_selects_upstream_proxy_credential() {
        let native = b"CONNECT fixture.local:443 HTTP/1.1\r\nHost: fixture.local:443\r\nProxy-Authorization: Basic local\r\nProxy-Connection: Keep-Alive\r\n\r\n";
        assert_eq!(proxy_connect(native, None), b"CONNECT fixture.local:443 HTTP/1.1\r\nHost: fixture.local:443\r\nProxy-Connection: Keep-Alive\r\n\r\n");
        assert_eq!(proxy_connect(native, Some("Basic upstream")), b"CONNECT fixture.local:443 HTTP/1.1\r\nHost: fixture.local:443\r\nProxy-Authorization: Basic upstream\r\nProxy-Connection: Keep-Alive\r\n\r\n");
    }

    struct FailingWriter {
        accepted: usize,
    }
    impl AsyncWrite for FailingWriter {
        fn poll_write(
            mut self: Pin<&mut Self>,
            _: &mut Context<'_>,
            bytes: &[u8],
        ) -> Poll<IoResult<usize>> {
            if self.accepted == 7 {
                return Poll::Ready(Err(Error::new(ErrorKind::BrokenPipe, "合成写入中断")));
            }
            let count = bytes.len().min(3).min(7 - self.accepted);
            self.accepted += count;
            Poll::Ready(Ok(count))
        }
        fn poll_flush(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<IoResult<()>> {
            Poll::Ready(Ok(()))
        }
        fn poll_shutdown(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<IoResult<()>> {
            Poll::Ready(Ok(()))
        }
    }

    #[tokio::test]
    async fn failed_writer_never_counts_queued_but_unaccepted_bytes() {
        let bytes = b"0123456789abcdef";
        let progress = Arc::new(Mutex::new(Some(observation(bytes, None))));
        let mut writer = FailingWriter { accepted: 0 };
        assert_eq!(
            write_observed(&mut writer, bytes, true, &progress).await,
            Err("upstream_write_failed")
        );
        let observed = progress.lock().unwrap().take().unwrap();
        assert_eq!(observed.body_bytes, 7);
        assert_eq!(observed.http_bytes, 7);
        assert_eq!(observed.preview, &bytes[..7]);
        assert_eq!(
            hex::encode(observed.body_hash.finalize()),
            hex::encode(Sha256::digest(&bytes[..7]))
        );
    }
}
