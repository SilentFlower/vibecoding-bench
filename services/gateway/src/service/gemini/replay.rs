//! 已受理工具续轮的提交回执和短期响应缓存。

use std::mem::size_of;
use std::sync::{Arc, Mutex, OnceLock};

use futures_util::{Stream, stream};
use serde::ser::{Serialize, SerializeMap, Serializer};
use serde_json::Value;
use sha2::{Digest, Sha256};
use tokio::sync::{OwnedSemaphorePermit, Semaphore, watch};
use tokio::time::{Instant, timeout_at};

use crate::error::AppError;
use crate::service::system_update::InferenceCutover;

use super::AGY_TOOL_WAIT_LIMIT;

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

    /// 编码持久回执的正文摘要。@return 固定十六进制。
    pub(super) fn digest(&self) -> String {
        self.body_digest
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect()
    }
}

pub(super) struct SortedJson<'a>(pub(super) &'a Value);

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

/// 有界保留实际原生历史，供有物理收口证明的失败恢复。
pub(super) struct RuntimeContents {
    pub(super) value: Arc<Value>,
    _reservation: OwnedSemaphorePermit,
}

#[derive(Default)]
struct ReplayState {
    frames: Vec<Arc<StoredFrame>>,
    unavailable: bool,
    terminal: Option<Result<(), AppError>>,
    attempt: Option<ReplayAttempt>,
}

/// 已进入发送边界的原尝试。观察到模型启动后才能确认原生已执行。
#[derive(Clone)]
pub(super) struct ReplayAttempt {
    pub(super) id: String,
    pub(super) model_observed: bool,
}

/// 同一生成的已交付帧、出站边界和读者进度。
pub(super) struct ToolReplay {
    pub(super) account_id: i64,
    pub(super) request_id: String,
    pub(super) derived_session_id: Option<String>,
    pub(super) session_scope: Option<String>,
    pub(super) body_key: String,
    runtime: Mutex<Option<Arc<RuntimeContents>>>,
    planned_deadline: Instant,
    sender_deadline: OnceLock<Instant>,
    pub(super) cutover: Option<InferenceCutover>,
    budget: Arc<Semaphore>,
    _receipt_reservation: Option<OwnedSemaphorePermit>,
    frames: Mutex<ReplayState>,
    changes: watch::Sender<()>,
}

impl ToolReplay {
    /// 在工具轮领取时冻结响应归属和预算。
    /// @param account_id 原账号。@param request_id 接续轮 HTTP 根。
    /// @param derived_session_id 工具原归属的派生会话。@param deadline 接续轮截止。
    /// @param cutover 维护清理信号。@param budget 共享帧缓存预算。
    /// @return 等待发送的响应记录。
    pub(super) fn new(
        account_id: i64,
        request_id: String,
        derived_session_id: Option<String>,
        deadline: Instant,
        cutover: Option<InferenceCutover>,
        budget: Arc<Semaphore>,
    ) -> Self {
        Self {
            account_id,
            request_id,
            derived_session_id,
            session_scope: None,
            body_key: String::new(),
            runtime: Mutex::default(),
            planned_deadline: deadline,
            sender_deadline: OnceLock::new(),
            cutover,
            budget,
            _receipt_reservation: None,
            frames: Mutex::new(ReplayState::default()),
            changes: watch::channel(()).0,
        }
    }

    /// 保留需要复用的已规范化历史。@param value 原生历史。@param permit 字节预算。@return 无。
    pub(super) fn keep_runtime_contents(&self, value: Arc<Value>, permit: OwnedSemaphorePermit) {
        *self
            .runtime
            .lock()
            .unwrap_or_else(|error| error.into_inner()) = Some(Arc::new(RuntimeContents {
            value,
            _reservation: permit,
        }));
    }

    /// 返回失败恢复需要的原生历史。@return 可用时持有预算的快照。
    pub(super) fn runtime_contents(&self) -> Option<Arc<RuntimeContents>> {
        self.runtime
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .clone()
    }

    /// 成功或明确终止恢复后释放历史字节，回执摘要继续保留。@return 无。
    pub(super) fn discard_runtime_contents(&self) {
        self.runtime
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .take();
    }

    /// 冻结实际协商的 sender 截止。@param deadline 同一生成的单调截止。@return 无。
    pub(super) fn set_sender_deadline(&self, deadline: Instant) {
        let _ = self
            .sender_deadline
            .set(deadline.min(self.planned_deadline));
        self.changes.send_replace(());
    }

    /// 读取已知的真实生成截止。@return 原准备或实际 sender 截止。
    pub(super) fn deadline(&self) -> Instant {
        self.sender_deadline
            .get()
            .copied()
            .unwrap_or(self.planned_deadline)
    }

    /// 返回轻量内存回执清理时刻。@return 原生成及工具等待窗口。
    pub(super) fn receipt_deadline(&self) -> Instant {
        self.deadline() + AGY_TOOL_WAIT_LIMIT
    }

    /// 在领取原批次之前为提交回执保留共享内存预算。
    /// @param key 规范化的重读键。@param budget 轻量回执独立预算。@return 可接纳回填时成功。
    pub(super) fn reserve_receipt(
        &mut self,
        key: &str,
        budget: &Arc<Semaphore>,
    ) -> Result<(), AppError> {
        // 原尝试与 HTTP 根同为 UUID，键还需由到期任务保存一份。
        let bytes = size_of::<Self>()
            + 2 * (key.len() + self.request_id.len())
            + self.body_key.len()
            + self.derived_session_id.as_ref().map_or(0, String::len)
            + self.session_scope.as_ref().map_or(0, String::len);
        let bytes = u32::try_from(bytes).map_err(|_| AppError::AgyToolReplayUnavailable)?;
        self._receipt_reservation = Some(
            budget
                .clone()
                .try_acquire_many_owned(bytes)
                .map_err(|_| AppError::AgyToolReplayUnavailable)?,
        );
        Ok(())
    }

    /// 在撤销原待续归属时登记原尝试。@param id 首次发送编号。@return 无。
    pub(super) fn mark_sending(&self, id: &str) {
        self.frames
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .attempt = Some(ReplayAttempt {
            id: id.to_owned(),
            model_observed: false,
        });
    }

    /// 以受信原生事件确认已开始模型调用。@param id 原生尝试 ID。@return 无。
    pub(super) fn mark_model_observed(&self, id: &str) {
        let mut state = self
            .frames
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if let Some(attempt) = state.attempt.as_mut().filter(|attempt| attempt.id == id) {
            attempt.model_observed = true;
        }
    }

    /// 读取轻量的提交状态。@return 已进入发送边界的原尝试。
    pub(super) fn attempt(&self) -> Option<ReplayAttempt> {
        self.frames
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .attempt
            .clone()
    }

    /// 在执行期限之外，仅保留已进入发送边界的回执。
    /// @param now 当前单调时刻。@return 重试仍可定位原归属时为真。
    pub(super) fn retained(&self, now: Instant) -> bool {
        now < self.deadline() || (now < self.receipt_deadline() && self.attempt().is_some())
    }

    /// 保留一份紧凑帧。容量不足只关闭重读，首笔仍沿原通道交付。
    /// @param frame 可公开的源帧。@return 无。
    pub(super) fn push(&self, frame: &Value) {
        let mut state = self
            .frames
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if state.terminal.is_some() || state.unavailable || Instant::now() >= self.deadline() {
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
            state.frames = Vec::new();
            state.unavailable = true;
        }
        self.changes.send_replace(());
    }

    /// 唤醒读者并保留首个终态。@param result 原生成的终态。@return 无。
    pub(super) fn finish(&self, result: Result<(), AppError>) {
        if result.is_ok() {
            self.discard_runtime_contents();
        }
        let mut state = self
            .frames
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        if state.terminal.is_none() {
            state.terminal = Some(result);
            self.changes.send_replace(());
        }
    }

    /// 回收响应字节并通知读者。提交状态和原终态继续由回执持有。@return 无。
    pub(super) fn expire_frames(&self) {
        let mut state = self
            .frames
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        state.frames = Vec::new();
        state.unavailable = true;
        self.changes.send_replace(());
    }

    fn unavailable_error(&self, state: &ReplayState) -> Option<AppError> {
        let expired = Instant::now() >= self.deadline();
        if !expired && !state.unavailable {
            return None;
        }
        Some(match state.terminal.as_ref() {
            Some(Err(error)) => error.clone(),
            _ if expired => AppError::AgyToolResponseExpired,
            _ => AppError::AgyToolReplayUnavailable,
        })
    }

    /// 返回字节已回收时的公开结果。@return 原失败、明确过期或短期缓存故障。
    pub(super) fn response_error(&self) -> Option<AppError> {
        let state = self
            .frames
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        self.unavailable_error(&state)
    }

    /// 生成截止已过时给物理收口留一段有界时间。
    /// @param until 收口等待截止。@return 无。
    pub(super) async fn wait_terminal(&self, until: Instant) {
        let mut changes = self.changes.subscribe();
        loop {
            let finished = self
                .frames
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .terminal
                .is_some();
            if finished || !matches!(timeout_at(until, changes.changed()).await, Ok(Ok(()))) {
                return;
            }
        }
    }

    /// 从首帧读取，慢读者仅保留自身游标。
    /// @return 带原终态及原截止的响应流。
    pub(super) fn read(self: &Arc<Self>) -> impl Stream<Item = Result<Value, AppError>> + use<> {
        let cursor = (self.clone(), self.changes.subscribe(), 0);
        stream::unfold(Some(cursor), |cursor| async move {
            let (replay, mut changes, index) = cursor?;
            loop {
                let (frame, terminal) = {
                    let state = replay
                        .frames
                        .lock()
                        .unwrap_or_else(|error| error.into_inner());
                    if let Some(error) = replay.unavailable_error(&state) {
                        return Some((Err(error), None));
                    }
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
                    timeout_at(replay.deadline(), changes.changed()).await,
                    Ok(Ok(()))
                ) {
                    return Some((
                        Err(replay
                            .response_error()
                            .unwrap_or(AppError::AgyToolReplayUnavailable)),
                        None,
                    ));
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
        first.expire_frames();
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
            Some(Err(AppError::AgyToolResponseExpired))
        ));
    }

    #[test]
    fn committed_receipt_outlives_response_frames_and_preserves_the_actual_failure() {
        let now = Instant::now();
        let budget = Arc::new(Semaphore::new(8192));
        let failed = response(budget.clone(), now - Duration::from_secs(1));
        assert!(!failed.retained(now));
        failed.mark_sending("first-attempt");
        assert!(failed.retained(now));
        failed.mark_model_observed("foreign-attempt");
        assert!(!failed.attempt().unwrap().model_observed);
        failed.mark_model_observed("first-attempt");
        failed.finish(Err(AppError::AgyControl(StatusCode::INTERNAL_SERVER_ERROR)));
        failed.expire_frames();
        assert_eq!(failed.attempt().unwrap().id, "first-attempt");
        assert!(failed.attempt().unwrap().model_observed);
        assert!(matches!(
            failed.response_error(),
            Some(AppError::AgyControl(StatusCode::INTERNAL_SERVER_ERROR))
        ));
        assert!(!failed.retained(failed.receipt_deadline()));

        let succeeded = response(budget, now - Duration::from_secs(1));
        succeeded.mark_sending("original-success");
        succeeded.finish(Ok(()));
        assert!(succeeded.retained(now));
        assert!(matches!(
            succeeded.response_error(),
            Some(AppError::AgyToolResponseExpired)
        ));
    }
}
