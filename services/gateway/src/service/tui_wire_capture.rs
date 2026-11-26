//! 受管 V2 单次模型请求的 TLS 写出；解析、摘要和保存均在后台执行。

use super::{BODY_LIMIT, HEADER_LIMIT, SNAPSHOT_LIMIT, TuiCaptureInput};
use axum::body::Bytes;
use hyper::ext::AcceptedWrite;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use tokio::sync::{SemaphorePermit, mpsc};
use uuid::Uuid;

const CHUNK: usize = 64 * 1024;

/// 与现有私有快照共享写入名额，只有已提交的原预留可以一次性取走。
pub(crate) struct CaptureJob {
    pub directory: PathBuf,
    pub input: TuiCaptureInput,
    pub permit: SemaphorePermit<'static>,
}

impl CaptureJob {
    /// 在实际内层提交时启动后台观察。@param account 账号。@param attempt 原尝试。
    /// @param generation 环境代次。@param submitted 提交头。@param body 实际提交正文。
    /// @return 仅随本次 HTTPS 请求交给 HTTP/1 连接的观察句柄。
    pub(crate) fn start(
        mut self,
        account: i64,
        attempt: Uuid,
        generation: u64,
        submitted: Vec<(String, String)>,
        body: Bytes,
        assembly: Option<bool>,
    ) -> AcceptedWrite {
        // 复用单快照字节预算。只在队列有空间时复制，拥塞不阻塞业务。
        let (tx, mut rx) = mpsc::channel::<Bytes>(SNAPSHOT_LIMIT / CHUNK);
        let lost = Arc::new(AtomicBool::new(false));
        let loss = lost.clone();
        tokio::task::spawn_blocking(move || {
            let _permit = self.permit;
            let mut observation = WireEntity::default();
            let mut result = Ok(());
            while let Some(chunk) = rx.blocking_recv() {
                if result.is_ok() {
                    result = observation.accept(&chunk);
                }
            }
            let reason = if loss.load(Ordering::Acquire) {
                Some("EVENT_LOSS")
            } else {
                result.err()
            };
            let mut wire = observation.finish(reason);
            wire["request_id"] = json!(attempt.to_string());
            wire["binding_generation"] = json!(generation);
            self.input.assembly = assembly;
            if self
                .input
                .save(
                    &self.directory,
                    account,
                    attempt,
                    submitted,
                    body.to_vec(),
                    "request_to_account_sender",
                    false,
                    Some(wire),
                )
                .is_err()
            {
                tracing::warn!(account_id=account, attempt_id=%attempt, "V2 写出证据保存失败");
            }
        });
        AcceptedWrite::new(move |bytes| enqueue(&tx, &lost, bytes))
    }
}

fn enqueue(tx: &mpsc::Sender<Bytes>, lost: &AtomicBool, bytes: &[u8]) {
    if lost.load(Ordering::Relaxed) {
        return;
    }
    for part in bytes.chunks(CHUNK) {
        let Ok(slot) = tx.try_reserve() else {
            lost.store(true, Ordering::Release);
            break;
        };
        slot.send(Bytes::copy_from_slice(part));
    }
}

#[derive(Default)]
struct WireEntity {
    head: Vec<u8>,
    headers: Vec<(String, String)>,
    length: Option<u64>,
    body_bytes: u64,
    preview: Vec<u8>,
    http_hash: Sha256,
    body_hash: Sha256,
}

impl WireEntity {
    fn accept(&mut self, mut bytes: &[u8]) -> Result<(), &'static str> {
        self.http_hash.update(bytes);
        if self.length.is_none() {
            let old = self.head.len();
            let take = bytes.len().min(HEADER_LIMIT - old);
            self.head.extend_from_slice(&bytes[..take]);
            let start = old.saturating_sub(3);
            let Some(pos) = self.head[start..].windows(4).position(|x| x == b"\r\n\r\n") else {
                return if self.head.len() == HEADER_LIMIT {
                    Err("HTTP_HEADER_LIMIT")
                } else {
                    Ok(())
                };
            };
            let end = start + pos + 4;
            self.head.truncate(end);
            // 请求头按 HTTP 字节表示读取，正文继续按 UTF-8 校验。
            let head: String = self.head[..end - 4]
                .iter()
                .copied()
                .map(char::from)
                .collect();
            let mut lines = head.split("\r\n");
            if lines.next() != Some("POST /v1/messages HTTP/1.1") {
                return Err("HTTP_UNSUPPORTED");
            }
            for line in lines {
                let (name, value) = line.split_once(':').ok_or("HTTP_INVALID")?;
                let value = value.trim_matches([' ', '\t']);
                if name.eq_ignore_ascii_case("transfer-encoding") {
                    return Err("HTTP_UNSUPPORTED");
                }
                if name.eq_ignore_ascii_case("content-length") {
                    if self.length.is_some() {
                        return Err("HTTP_INVALID");
                    }
                    self.length = Some(value.parse().map_err(|_| "HTTP_INVALID")?);
                }
                if self.headers.len() >= 4096 {
                    return Err("HTTP_HEADER_LIMIT");
                }
                self.headers.push((name.to_owned(), value.to_owned()));
            }
            self.length.ok_or("HTTP_LENGTH_UNKNOWN")?;
            bytes = &bytes[end - old..];
        }
        self.body_bytes += bytes.len() as u64;
        if self.body_bytes > self.length.expect("已读到 HTTP 实体头") {
            return Err("HTTP_EXTRA_BYTES");
        }
        self.body_hash.update(bytes);
        self.preview
            .extend_from_slice(&bytes[..bytes.len().min(BODY_LIMIT - self.preview.len())]);
        Ok(())
    }

    fn finish(self, error: Option<&'static str>) -> Value {
        let mut reason = error;
        if reason.is_none() && self.length != Some(self.body_bytes) {
            reason = Some(if self.head.is_empty() {
                "REQUEST_NOT_OBSERVED"
            } else {
                "HTTP_PARTIAL"
            });
        }
        let clipped = self.body_bytes != self.preview.len() as u64;
        let body = match std::str::from_utf8(&self.preview) {
            Ok(value) => value,
            Err(error) if clipped && error.error_len().is_none() => {
                std::str::from_utf8(&self.preview[..error.valid_up_to()])
                    .expect("已验证 UTF-8 前缀")
            }
            Err(_) => {
                reason.get_or_insert("BODY_ENCODING");
                ""
            }
        };
        let complete = reason.is_none();
        let status = if complete {
            "complete"
        } else if self.head.is_empty() {
            "unavailable"
        } else {
            "incomplete"
        };
        let mut wire = json!({"source":"tui_sender_tls","representation":"http_entity_from_tls_accepted_write",
            "status":status,"reason":reason,"complete":complete,"flushed":null,
            "headers":[],"body":"","headers_truncated":!complete,"body_truncated":clipped || !complete,
            "observed_body_bytes":null,"body_sha256":null});
        if complete {
            wire["headers"] = json!(self.headers);
            wire["body"] = json!(body);
            wire["observed_body_bytes"] = json!(self.body_bytes);
            wire["body_sha256"] = json!(hex::encode(self.body_hash.finalize()));
            wire["observed_http_bytes"] = json!(self.head.len() as u64 + self.body_bytes);
            wire["http_sha256"] = json!(hex::encode(self.http_hash.finalize()));
        }
        wire
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 队列拥塞直接丢弃后续副本，消费者恢复后仍保留单次观察的缺口。
    #[test]
    fn saturated_queue_stays_incomplete() {
        let (tx, mut rx) = mpsc::channel(1);
        let lost = AtomicBool::new(false);
        enqueue(&tx, &lost, &vec![0; CHUNK + 1]);
        assert!(lost.load(Ordering::Acquire));
        assert_eq!(rx.try_recv().unwrap().len(), CHUNK);
        enqueue(&tx, &lost, b"later");
        assert!(rx.try_recv().is_err());
    }

    /// 每个字节都可成为一次短写，完整报文以独立构造的 HTTP 摘要核对。
    #[test]
    fn split_headers_and_duplicate_fields() {
        let http = b"POST /v1/messages HTTP/1.1\r\nx-test: first\r\nX-Test: second\r\nAccept-Language: caf\xe9\r\nContent-Length: 2\r\n\r\n{}";
        for width in [1, 3, 64, http.len()] {
            let mut entity = WireEntity::default();
            for part in http.chunks(width) {
                entity.accept(part).unwrap();
            }
            let wire = entity.finish(None);
            assert_eq!(wire["http_sha256"], hex::encode(Sha256::digest(http)));
            assert_eq!(wire["body_sha256"], hex::encode(Sha256::digest(b"{}")));
            assert_eq!(wire["observed_http_bytes"], http.len());
            assert_eq!(wire["headers"][0], json!(["x-test", "first"]));
            assert_eq!(wire["headers"][1], json!(["X-Test", "second"]));
            assert_eq!(wire["headers"][2], json!(["Accept-Language", "café"]));
        }
    }

    /// 半包、队列缺口和未写出分别收口，敏感前缀与完整摘要都不投影。
    #[test]
    fn gaps_never_claim_a_complete_entity() {
        let absent = WireEntity::default().finish(None);
        assert_eq!(absent["status"], "unavailable");
        for reason in [None, Some("EVENT_LOSS")] {
            let mut entity = WireEntity::default();
            entity.accept(b"POST /v1/messages HTTP/1.1\r\nAuthorization: Bearer synthetic\r\nContent-Length: 9\r\n\r\nabc").unwrap();
            let wire = entity.finish(reason);
            assert_eq!(wire["status"], "incomplete");
            assert_eq!(wire["reason"], reason.unwrap_or("HTTP_PARTIAL"));
            assert_eq!(wire["headers"], json!([]));
            assert!(wire["body_sha256"].is_null() && wire["http_sha256"].is_null());
        }
    }
}
