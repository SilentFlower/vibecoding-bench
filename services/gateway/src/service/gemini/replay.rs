//! 已受理工具续轮的进程内响应缓存。

use std::mem::size_of;
use std::sync::{Arc, Mutex};

use futures_util::{Stream, stream};
use serde::ser::{Serialize, SerializeMap, Serializer};
use serde_json::Value;
use sha2::{Digest, Sha256};
use tokio::sync::{OwnedSemaphorePermit, Semaphore, watch};
use tokio::time::{Instant, timeout_at};

use crate::error::AppError;
use crate::service::system_update::InferenceCutover;

/// 重试比对使用入站 JSON，原生历史的归一化不改变它。
#[derive(Clone, PartialEq, Eq, Hash)]
pub(super) struct ReplayKey {
    token_id: i64,
    model: String,
    body_digest: [u8; 32],
}

impl ReplayKey {
    /// 计算已鉴权请求的正文身份，不保留正文副本。
    /// @param token_id 入口令牌 ID。@param model 公开模型。@param body 完整入站 JSON。
    /// @return 用于定位已受理响应的身份。
    pub(super) fn new(token_id: i64, model: &str, body: &Value) -> Result<Self, AppError> {
        let mut digest = Sha256::new();
        serde_json::to_writer(&mut digest, &SortedJson(body))
            .map_err(|_| AppError::BadRequest("Gemini正文无效".into()))?;
        Ok(Self {
            token_id,
            model: model.to_owned(),
            body_digest: digest.finalize().into(),
        })
    }
}

struct SortedJson<'a>(&'a Value);

impl Serialize for SortedJson<'_> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        match self.0 {
            Value::Object(object) => {
                // 只排序借用的字段，避免改写实际入站或为大正文保留额外副本。
                let mut ordered: Vec<_> = object.iter().collect();
                ordered.sort_unstable_by_key(|(name, _)| *name);
                let mut map = serializer.serialize_map(Some(ordered.len()))?;
                for (name, value) in ordered {
                    map.serialize_entry(name, &SortedJson(value))?;
                }
                map.end()
            }
            Value::Array(items) => serializer.collect_seq(items.iter().map(SortedJson)),
            value => value.serialize(serializer),
        }
    }
}

struct StoredFrame {
    encoded: Box<[u8]>,
    _reservation: OwnedSemaphorePermit,
}

#[derive(Default)]
struct ReplayFrames {
    frames: Vec<Arc<StoredFrame>>,
    terminal: Option<Result<(), AppError>>,
}

/// 同一生成的已交付帧、出站边界和读者进度。
pub(super) struct ToolReplay {
    pub(super) account_id: i64,
    pub(super) request_id: String,
    pub(super) previous_turn: String,
    pub(super) derived_session_id: Option<String>,
    pub(super) deadline: Instant,
    pub(super) cutover: Option<InferenceCutover>,
    budget: Arc<Semaphore>,
    frames: Mutex<ReplayFrames>,
    changes: watch::Sender<()>,
}

impl ToolReplay {
    /// 在工具轮领取时冻结响应归属和预算。
    /// @param account_id 原账号。@param request_id 接续轮 HTTP 根。@param previous_turn 原工具轮。
    /// @param derived_session_id 工具原归属的派生会话。@param deadline 接续轮截止。
    /// @param cutover 维护清理信号。@param budget 共享帧缓存预算。
    /// @return 等待发送的响应记录。
    pub(super) fn new(
        account_id: i64,
        request_id: String,
        previous_turn: String,
        derived_session_id: Option<String>,
        deadline: Instant,
        cutover: Option<InferenceCutover>,
        budget: Arc<Semaphore>,
    ) -> Self {
        Self {
            account_id,
            request_id,
            previous_turn,
            derived_session_id,
            deadline,
            cutover,
            budget,
            frames: Mutex::new(ReplayFrames::default()),
            changes: watch::channel(()).0,
        }
    }

    /// 保留一份紧凑帧。容量不足只关闭重读，首笔仍沿原通道交付。
    /// @param frame 可公开的源帧。@return 无。
    pub(super) fn push(&self, frame: &Value) {
        let mut state = self
            .frames
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if state.terminal.is_some() {
            return;
        }
        let stored = serde_json::to_vec(frame).ok().and_then(|encoded| {
            let encoded = encoded.into_boxed_slice();
            // 预算同时覆盖每帧的分配与向量槽，防止极小帧绕过字节限制。
            let bytes = encoded.len() + size_of::<StoredFrame>() + 4 * size_of::<usize>();
            let reservation = self
                .budget
                .clone()
                .try_acquire_many_owned(bytes.try_into().ok()?)
                .ok()?;
            Some(Arc::new(StoredFrame {
                encoded,
                _reservation: reservation,
            }))
        });
        if let Some(stored) = stored {
            state.frames.push(stored);
        } else {
            *state = ReplayFrames {
                frames: Vec::new(),
                terminal: Some(Err(AppError::AgyToolReplayUnavailable)),
            };
        }
        self.changes.send_replace(());
    }

    /// 唤醒读者并保留首个终态。@param result 原生成的终态。@return 无。
    pub(super) fn finish(&self, result: Result<(), AppError>) {
        let mut state = self
            .frames
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if state.terminal.is_none() {
            state.terminal = Some(result);
            self.changes.send_replace(());
        }
    }

    /// 回收响应字节并通知仍在读取的连接。@return 无。
    pub(super) fn expire(&self) {
        let mut state = self
            .frames
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        *state = ReplayFrames {
            frames: Vec::new(),
            terminal: Some(Err(AppError::AgyToolReplayUnavailable)),
        };
        self.changes.send_replace(());
    }

    /// 检查首笔断开后是否仍有重试方在读取。@return 存在重试读者时为真。
    pub(super) fn has_readers(&self) -> bool {
        self.changes.receiver_count() != 0
    }

    /// 等待当前重试读者都离开。@return 无。
    pub(super) async fn readers_closed(&self) {
        self.changes.closed().await;
    }

    /// 从首帧读取，慢读者仅保留自身游标。
    /// @return 带原终态及原截止的响应流。
    pub(super) fn read(self: &Arc<Self>) -> impl Stream<Item = Result<Value, AppError>> + use<> {
        let cursor = (self.clone(), self.changes.subscribe(), 0);
        stream::unfold(Some(cursor), |cursor| async move {
            let (replay, mut changes, index) = cursor?;
            loop {
                if Instant::now() >= replay.deadline {
                    return Some((Err(AppError::AgyToolReplayUnavailable), None));
                }
                let (frame, terminal) = {
                    let state = replay
                        .frames
                        .lock()
                        .unwrap_or_else(|error| error.into_inner());
                    (state.frames.get(index).cloned(), state.terminal.clone())
                };
                if let Some(frame) = frame {
                    let value = serde_json::from_slice(&frame.encoded)
                        .map_err(|_| AppError::AgyToolReplayUnavailable);
                    return Some((value, Some((replay, changes, index + 1))));
                }
                if let Some(terminal) = terminal {
                    return terminal.err().map(|error| (Err(error), None));
                }
                if !matches!(
                    timeout_at(replay.deadline, changes.changed()).await,
                    Ok(Ok(()))
                ) {
                    return Some((Err(AppError::AgyToolReplayUnavailable), None));
                }
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::{ReplayKey, ToolReplay};
    use crate::error::AppError;
    use axum::http::StatusCode;
    use futures_util::{StreamExt, poll};
    use serde_json::json;
    use std::sync::Arc;
    use std::time::Duration;
    use tokio::sync::Semaphore;
    use tokio::time::Instant;

    fn response(budget: Arc<Semaphore>, deadline: Instant) -> Arc<ToolReplay> {
        Arc::new(ToolReplay::new(
            1,
            "request".into(),
            "previous".into(),
            None,
            deadline,
            None,
            budget,
        ))
    }

    #[test]
    fn replay_key_covers_the_complete_json_model_and_token() {
        let first = json!({"tools": [], "contents": [{"role": "user", "text": "合成"}]});
        let same = json!({"contents": [{"text": "合成", "role": "user"}], "tools": []});
        let changed =
            json!({"contents": [{"role": "user", "text": "合成"}], "tools": [{"name": "other"}]});
        let key = ReplayKey::new(1, "model", &first).unwrap();
        assert!(key == ReplayKey::new(1, "model", &same).unwrap());
        assert!(key != ReplayKey::new(1, "model", &changed).unwrap());
        assert!(key != ReplayKey::new(2, "model", &first).unwrap());
        assert!(key != ReplayKey::new(1, "another-model", &first).unwrap());
    }

    #[tokio::test]
    async fn replay_stream_keeps_order_and_the_actual_failure() {
        let deadline = Instant::now() + Duration::from_secs(10);
        let response = response(Arc::new(Semaphore::new(8192)), deadline);
        let first = json!({"text": "首帧"});
        let second = json!({"text": "次帧"});
        response.push(&first);
        let mut early = Box::pin(response.read());
        assert_eq!(early.next().await.unwrap().unwrap(), first);
        assert!(poll!(early.next()).is_pending());
        response.push(&second);
        response.finish(Err(AppError::AgyControl(StatusCode::BAD_REQUEST)));
        assert_eq!(early.next().await.unwrap().unwrap(), second);
        let mut late = Box::pin(response.read());
        assert_eq!(late.next().await.unwrap().unwrap(), first);
        assert_eq!(late.next().await.unwrap().unwrap(), second);
        for reader in [&mut early, &mut late] {
            assert!(matches!(
                reader.next().await,
                Some(Err(AppError::AgyControl(StatusCode::BAD_REQUEST)))
            ));
            assert!(reader.next().await.is_none());
        }
        assert!(!response.has_readers());
    }

    #[tokio::test]
    async fn shared_budget_and_expiry_reclaim_frames_for_other_responses() {
        let capacity = 1536 * 1024;
        let budget = Arc::new(Semaphore::new(capacity));
        let deadline = Instant::now() + Duration::from_secs(10);
        let first = response(budget.clone(), deadline);
        let second = response(budget.clone(), deadline);
        let frame = json!({"text": "a".repeat(1024 * 1024)});
        first.push(&frame);
        second.push(&frame);
        let mut blocked = Box::pin(second.read());
        assert!(matches!(
            blocked.next().await,
            Some(Err(AppError::AgyToolReplayUnavailable))
        ));
        first.expire();
        assert_eq!(budget.available_permits(), capacity);
        let third = response(budget.clone(), deadline);
        third.push(&frame);
        third.finish(Ok(()));
        let mut reader = Box::pin(third.read());
        assert_eq!(reader.next().await.unwrap().unwrap(), frame);
        assert!(reader.next().await.is_none());
        let expired = response(budget, Instant::now());
        let mut reader = Box::pin(expired.read());
        assert!(matches!(
            reader.next().await,
            Some(Err(AppError::AgyToolReplayUnavailable))
        ));
    }
}
