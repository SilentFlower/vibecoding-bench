//! 只观察AGY的Gemini源帧和控制事实，复用现有诊断队列。
use std::time::Instant;

use serde_json::{Map, Value, json};
use uuid::Uuid;

use super::{TraceContext, identity_hash, now};
use crate::error::AppError;
use crate::model::account::Account;
use crate::model::request_diagnostics::{
    AttemptDiagnostic, DiagnosticContext, DiagnosticParameters, DiagnosticSessions,
    DiagnosticTokens, ExecutionLocation, GeminiDiagnosticUsage, NativeRuntimeObservation,
    SystemPromptDiagnostic, ToolTurnDiagnostic,
};
use crate::service::agy_contract::{AGY_SOURCE_SHA256, AgyModelId, AgySystemPromptPolicy};
use crate::service::v3_scheduling::SchedulingRequest;

/// 持有一次真实AGY提交的观察归属，HTTP结束后仅补工具收口。
pub(crate) struct AgyAttemptTrace {
    trace: TraceContext,
    record: AttemptDiagnostic,
    started: Instant,
    finished: bool,
    source_terminal: bool,
    source_error: bool,
    policy: AgySystemPromptPolicy,
    scheduling: Option<SchedulingRequest>,
    model_started_ms: Option<u64>,
}

impl AgyAttemptTrace {
    /// 在实际发送边界建立独立尝试。@param trace HTTP根。@param account 已选账号。@param model 请求模型。@param native_model 实际枚举。@param execution_location 已核验通道的实际位置。@param generation AT代次。@param policy 冻结策略。@param id 尝试UUID。@param body 原始Gemini对象。@param streaming 公共SSE。@return 可选观察器。
    pub(crate) fn begin(
        trace: Option<&TraceContext>,
        account: &Account,
        model: &str,
        native_model: &AgyModelId,
        execution_location: Option<ExecutionLocation>,
        generation: i64,
        policy: &AgySystemPromptPolicy,
        id: &str,
        body: &Value,
        streaming: bool,
    ) -> Option<Self> {
        let trace = trace?.clone();
        let mut state = trace.lock();
        state.request.attempt_count = state.request.attempt_count.saturating_add(1);
        state.request.account_id = Some(account.id);
        state.request.error_stage = None;
        let submitted_model = match native_model {
            AgyModelId::Name(name) => name.clone(),
            AgyModelId::Number(id) => id.to_string(),
        };
        let record = AttemptDiagnostic {
            execution_location,
            context: Some(DiagnosticContext {
                platform: Some("antigravity".into()),
                entry_protocol: Some("gemini".into()),
                requested_model: Some(model.into()),
                kernel: Some("agy".into()),
                kernel_version: Some("1.5.9".into()),
                source_sha256: Some(AGY_SOURCE_SHA256.into()),
                submitted_model: Some(submitted_model),
                credential_generation: Some(generation),
                system_prompt_policy: Some(SystemPromptDiagnostic {
                    enabled: policy.enabled,
                    rule_version: policy.rule_version.clone(),
                    rule_sha256: None,
                    source: None,
                    changed: None,
                    replaced_codepoints: None,
                    system_codepoints: None,
                }),
                response_headers_source: Some("agy_account_sender".into()),
                ..Default::default()
            }),
            runtime: None,
            log_mode: state.request.log_mode,
            capture_status: None,
            attempt_id: id.into(),
            request_id: state.request.request_id.clone(),
            ordinal: state.request.attempt_count,
            account_id: account.id,
            account_name: None,
            account_email: None,
            profile_version: "1.5.9".into(),
            profile_selection: "agy_native".into(),
            parameters: DiagnosticParameters {
                model: Some(model.into()),
                max_tokens: body
                    .pointer("/generationConfig/maxOutputTokens")
                    .and_then(Value::as_u64),
                stream: Some(streaming),
                tools_count: body["tools"].as_array().map(|groups| {
                    groups
                        .iter()
                        .filter_map(|g| g["functionDeclarations"].as_array())
                        .map(Vec::len)
                        .sum()
                }),
                ..Default::default()
            },
            sessions: DiagnosticSessions::default(),
            started_at: now(),
            finished_at: None,
            ttft_ms: None,
            first_output_ms: None,
            duration_ms: None,
            status_code: None,
            upstream_request_id: None,
            response_model: None,
            response_message_hash: None,
            stop_reason: None,
            tokens: DiagnosticTokens::default(),
            partial: true,
            outcome: "in_progress".into(),
            error_stage: None,
            error_type: None,
            retry_reason: state.next_retry.take().map(str::to_owned),
        };
        drop(state);
        trace.emit(Some(record.clone()));
        Some(Self {
            trace,
            record,
            started: Instant::now(),
            finished: false,
            source_terminal: false,
            source_error: false,
            policy: policy.clone(),
            scheduling: None,
            model_started_ms: None,
        })
    }

    /// 记录实际私有响应头时刻，明确其来源。@param status sender实际HTTP状态。@return 无。
    pub(crate) fn headers(&mut self, status: u16) {
        self.record.ttft_ms = Some(self.elapsed());
        self.record.status_code = Some(status);
        self.publish();
    }

    /// 接收已核对归属的控制事件白名单。@param native 原生事件。@param envelope 监督器身份。@return 无。
    pub(crate) fn native(&mut self, native: &Value, envelope: &Value) {
        if let Some(status) = native["capture_status"]
            .as_str()
            .filter(|v| matches!(*v, "queued" | "saved" | "disabled" | "dropped" | "failed"))
        {
            self.capture_status(status);
        }
        if self.finished {
            return;
        }
        match native["type"].as_str() {
            Some("request_prepared") => {
                if let Ok(runtime) =
                    serde_json::from_value::<NativeRuntimeObservation>(native["runtime"].clone())
                {
                    if runtime.is_valid()
                        && native["worker_id"].as_str() == Some(runtime.worker_id.as_str())
                        && native["generation"].as_str() == runtime.kernel_generation.as_deref()
                    {
                        self.record.runtime = Some(runtime);
                        self.publish();
                    }
                }
                return;
            }
            Some("model_start") => {
                if self.model_started_ms.is_none() {
                    self.model_started_ms = Some(self.elapsed());
                    if let Some(request) = &self.scheduling {
                        request.submitted(self.record.account_id);
                    }
                }
                return;
            }
            _ => {}
        }
        if !matches!(
            native["type"].as_str(),
            Some(
                "request_accepted"
                    | "completed"
                    | "error"
                    | "cancelled"
                    | "tool_turn_finalized"
                    | "capture_status"
            )
        ) {
            return;
        }
        let context = self.record.context.as_mut().expect("AGY固定上下文");
        context.environment_id = uuid(envelope["environment_id"].as_str());
        context.environment_generation = envelope["environment_generation"].as_u64();
        context.worker_id = uuid(native["worker_id"].as_str());
        context.worker_generation = uuid(native["generation"].as_str());
        if let Some(id) = uuid(native["native_cascade_id"].as_str()) {
            context.conversation_id = Some(id);
        }
        if let Some(id) = uuid(native["native_trajectory_id"].as_str()) {
            context.trajectory_id = Some(id);
        }
        if let Some(calls) = native["native_model_calls"].as_u64() {
            context.native_model_calls = Some(calls);
        }
        let control_code = match native["type"].as_str() {
            Some("completed") => native["control_error_code"].as_str(),
            Some("error" | "cancelled" | "tool_turn_finalized") => native["code"].as_str(),
            _ => None,
        };
        if let Some(code) = control_code.filter(|code| {
            matches!(
                *code,
                "cancelled"
                    | "cancel_timeout"
                    | "native_request_failed"
                    | "native_transport_error"
                    | "native_control_timeout"
                    | "native_not_idle"
                    | "native_process_exited"
                    | "native_protocol_error"
                    | "native_stream_incomplete"
                    | "native_delivery_error"
                    | "native_start_rejected"
                    | "tool_protocol_error"
                    | "native_tool_yield_timeout"
                    | "native_tool_yield_failed"
                    | "ambiguous_parallel_function_calls"
                    | "unsupported_gemini_candidate_count"
                    | "invalid_native_gemini_parts"
                    | "native_safety_endpoint_rejected"
                    | "native_safety_egress_unobserved"
                    | "kernel_internal_error"
            )
        }) {
            context.control_error_code = Some(code.into());
            context.control_recovery = native["control_recovery"]
                .as_str()
                .filter(|reason| {
                    matches!(
                        *reason,
                        "kept"
                            | "ineligible_error"
                            | "unsupported_protocol"
                            | "cancelled"
                            | "compatibility_error"
                            | "model_call_count"
                            | "missing_model_eof"
                            | "model_error"
                            | "tool_pending"
                            | "source_error"
                            | "missing_stop"
                            | "missing_text"
                            | "missing_usage"
                            | "delivery_error"
                            | "model_http_status"
                            | "observer_before_eof"
                    )
                })
                .map(str::to_owned);
        }
        let report = &native["system_prompt_policy"];
        if self.policy.matches_report(report) {
            context.system_prompt_policy = Some(SystemPromptDiagnostic {
                enabled: self.policy.enabled,
                rule_version: self.policy.rule_version.clone(),
                rule_sha256: report["rule_sha256"].as_str().map(str::to_owned),
                source: Some("cortex_custom_system".into()),
                changed: report["changed"].as_bool(),
                replaced_codepoints: report["replaced_codepoints"].as_u64(),
                system_codepoints: report["system_codepoints"].as_u64(),
            });
        }
        self.publish();
    }

    /// 观察源帧，累计计数取最大值并保留未知。@param frame 已解析Gemini帧。@return 无。
    pub(crate) fn frame(&mut self, frame: &Value) {
        if self.finished {
            return;
        }
        let first_output = self.record.first_output_ms;
        let terminal = self.source_terminal;
        if frame.get("error").is_some() {
            self.source_error = true;
            self.record.error_type = Some("gemini_source_error".into());
        }
        for candidate in frame["candidates"].as_array().into_iter().flatten() {
            if let Some(reason) = candidate["finishReason"].as_str().filter(|r| {
                matches!(
                    *r,
                    "STOP"
                        | "MAX_TOKENS"
                        | "SAFETY"
                        | "RECITATION"
                        | "OTHER"
                        | "BLOCKLIST"
                        | "PROHIBITED_CONTENT"
                        | "SPII"
                        | "MALFORMED_FUNCTION_CALL"
                        | "UNEXPECTED_TOOL_CALL"
                        | "TOO_MANY_TOOL_CALLS"
                )
            }) {
                self.source_terminal = true;
                self.record.stop_reason = Some(reason.into());
            }
            let output = candidate["content"]["parts"]
                .as_array()
                .is_some_and(|parts| {
                    parts.iter().any(|p| {
                        p["text"].as_str().is_some_and(|t| !t.is_empty())
                            || p.get("functionCall").is_some()
                    })
                });
            if output && self.record.first_output_ms.is_none() {
                self.record.first_output_ms = Some(self.elapsed());
            }
        }
        if frame
            .pointer("/promptFeedback/blockReason")
            .and_then(Value::as_str)
            .is_some_and(|r| matches!(r, "SAFETY" | "OTHER" | "BLOCKLIST" | "PROHIBITED_CONTENT"))
        {
            self.source_terminal = true;
        }
        if let Some(version) = label(frame["modelVersion"].as_str()) {
            self.record.response_model = Some(version.clone());
            self.record.context.as_mut().unwrap().response_model_version = Some(version);
        }
        if let Some(usage) = frame["usageMetadata"].as_object() {
            for (key, target) in [
                ("promptTokenCount", &mut self.record.tokens.input_tokens),
                (
                    "candidatesTokenCount",
                    &mut self.record.tokens.output_tokens,
                ),
                (
                    "cachedContentTokenCount",
                    &mut self.record.tokens.cache_read_tokens,
                ),
            ] {
                if let Some(value) = usage.get(key).and_then(Value::as_u64) {
                    *target = Some(target.unwrap_or(0).max(value));
                }
            }
            let (raw, complete) = usage_metadata(usage);
            let context = self.record.context.as_mut().unwrap();
            let previous = context.usage.as_ref();
            let maximum =
                |key: &str, old: Option<u64>| match (usage.get(key).and_then(Value::as_u64), old) {
                    (Some(a), Some(b)) => Some(a.max(b)),
                    (a, b) => a.or(b),
                };
            let total = maximum("totalTokenCount", previous.and_then(|u| u.total_tokens));
            let thoughts = maximum(
                "thoughtsTokenCount",
                previous.and_then(|u| u.thoughts_tokens),
            );
            context.usage = Some(GeminiDiagnosticUsage {
                source: "gemini_usage_metadata".into(),
                usage_metadata: raw,
                total_tokens: total,
                thoughts_tokens: thoughts,
                complete,
            });
        }
        // 文本分块不产生新摘要事实，减少队列压力以保留终态写入容量。
        if first_output != self.record.first_output_ms
            || terminal != self.source_terminal
            || frame.get("usageMetadata").is_some()
            || frame.get("error").is_some()
        {
            self.publish();
        }
    }

    /// 登记已验证的跨HTTP前驱。@param root 原HTTP根。@param attempt 原尝试。@return 无。
    pub(crate) fn continuation(&mut self, root: &str, attempt: &str) {
        self.record.context.as_mut().unwrap().tool_turn = Some(ToolTurnDiagnostic {
            continuation_of_request_id: uuid(Some(root)),
            previous_attempt_id: uuid(Some(attempt)),
            state: "continuation".into(),
            observed_at: now(),
            call_hashes: vec![],
        });
        self.publish();
    }

    /// 记录本次采集状态。@param status 受控采集结果。@return 无。
    pub(crate) fn capture_status(&mut self, status: &str) {
        if self.finished {
            self.trace.store.capture_status(
                &self.record.attempt_id,
                self.record.account_id,
                status,
            );
        } else {
            self.record.capture_status = Some(status.into());
            self.publish();
        }
    }

    /// 原认证尝试终结后标记下一真实提交的恢复原因。@return 无。
    pub(crate) fn recovery(&mut self) {
        self.finish("upstream_error", Some("upstream_body"));
        self.trace.lock().next_retry = Some("oauth_recovery");
    }

    /// 源与控制终态完成一次模型尝试，工具等待另持状态。@param pending 是否等待真实工具。@param calls 源函数调用。@return 无。
    pub(crate) fn completed(&mut self, pending: bool, calls: &[Value]) {
        if pending {
            let mut turn = self
                .record
                .context
                .as_mut()
                .unwrap()
                .tool_turn
                .take()
                .unwrap_or_default();
            turn.state = "waiting".into();
            turn.observed_at = now();
            turn.call_hashes = calls
                .iter()
                .take(64)
                .map(|c| {
                    identity_hash(
                        self.record.account_id,
                        "tool",
                        c["id"].as_str().unwrap_or_default(),
                    )
                })
                .collect();
            self.record.context.as_mut().unwrap().tool_turn = Some(turn);
        }
        let success = self.source_terminal && !self.source_error;
        self.finish(
            if success { "success" } else { "incomplete" },
            if success {
                None
            } else {
                Some("native_control")
            },
        );
    }

    /// 记录工具自身结果，物理控制状态继续等待作业回执。@param status 实际工具终态。@return 无。
    pub(crate) fn tool_finalized(&mut self, status: &str) {
        if let Some(mut turn) = self
            .record
            .context
            .as_ref()
            .and_then(|c| c.tool_turn.clone())
            .filter(|t| t.state == "waiting")
        {
            turn.state = match status {
                "completed" => "completed",
                "cancelled" => "cancelled",
                _ => "error",
            }
            .into();
            turn.observed_at = now();
            self.record.context.as_mut().unwrap().tool_turn = Some(turn.clone());
            self.trace
                .store
                .tool_turn(&self.record.attempt_id, self.record.account_id, turn);
        }
    }

    /// 仅由实际job_finalized回执登记物理收口。@param status 实际控制终态。@return 无。
    pub(crate) fn finalized(&mut self, status: &str) {
        let status = match status {
            "completed" => "completed",
            "cancelled" => "cancelled",
            _ => "error",
        };
        self.tool_finalized(status);
        if !self.finished {
            self.finish("incomplete", Some("native_control"));
        }
        self.trace.store.control_state(
            &self.record.attempt_id,
            self.record.account_id,
            status,
            &now(),
        );
    }

    /// 记录模型提交前的受控输入拒绝。@param error 已投影的错误。@return 无。
    pub(crate) fn input_rejected(&mut self, error: &AppError) {
        if let (AppError::AgyInput { reason, field, .. }, Some(context)) =
            (error, self.record.context.as_mut())
        {
            self.record.error_type = Some((*reason).into());
            context.input_rejection_reason = Some((*reason).into());
            context.input_rejection_field = field.clone();
            context.native_model_calls = Some(0);
            // 账号侧确认内容采集后，才允许网关持久化该次完整入口。
            if matches!(
                self.record.capture_status.as_deref(),
                Some("queued" | "saved")
            ) {
                self.trace.save_rejected_ingress(
                    &mut self.trace.lock(),
                    Some((*reason).into()),
                    true,
                );
            }
        }
        self.finish("local_rejected", Some("native_input"));
    }

    /// 保存已核实的上游额度或限流标记。@return 无。
    pub(crate) fn upstream_quota(&mut self) {
        if !self.finished {
            self.record.error_type = Some("RESOURCE_EXHAUSTED".into());
            self.finish("upstream_error", Some("upstream_model"));
        }
    }

    /// 将控制错误记为实际尝试状态。@param status 已核对的控制 HTTP 状态。@param cancelled 是否取消。@return 无。
    pub(crate) fn control_failed(&mut self, status: Option<u16>, cancelled: bool) {
        if self.finished {
            return;
        }
        if let Some(status) = status {
            self.record.status_code = Some(status);
        }
        let outcome = if cancelled {
            "cancelled"
        } else {
            "upstream_error"
        };
        self.finish(outcome, Some("native_control"));
    }

    /// 终结异常尝试，重复终结保持首次结果。@param outcome 受控结果。@param stage 实际阶段。@return 无。
    pub(crate) fn finish(&mut self, outcome: &str, stage: Option<&str>) {
        if self.finished {
            return;
        }
        self.finished = true;
        self.record.outcome = outcome.into();
        self.record.error_stage = stage.map(str::to_owned);
        self.record.finished_at = Some(now());
        self.record.duration_ms = Some(self.elapsed());
        self.record.partial = !self.source_terminal
            || self.source_error
            || self
                .record
                .context
                .as_ref()
                .and_then(|c| c.usage.as_ref())
                .is_none_or(|u| !u.complete);
        if let (Some(request), Some(model_started)) =
            (self.scheduling.as_ref(), self.model_started_ms)
        {
            // 预算不足是请求自己的终止原因。进程准备时间也不计入模型首输出样本。
            if self.record.error_type.as_deref() == Some("RESOURCE_EXHAUSTED") {
                request.capacity_rejected(self.record.account_id);
            } else if self.record.stop_reason.as_deref() != Some("MAX_TOKENS")
                || outcome == "success"
            {
                request.finish_observed_attempt(
                    self.record.account_id,
                    None,
                    outcome,
                    self.record.error_type.as_deref(),
                    self.record
                        .first_output_ms
                        .and_then(|ms| ms.checked_sub(model_started)),
                    self.record
                        .duration_ms
                        .and_then(|ms| ms.checked_sub(model_started)),
                );
            }
        }
        let mut state = self.trace.lock();
        if state
            .last_attempt
            .as_ref()
            .is_none_or(|(ordinal, _, _)| *ordinal <= self.record.ordinal)
        {
            state.last_attempt = Some((
                self.record.ordinal,
                self.record.outcome.clone(),
                self.record.error_stage.clone(),
            ));
        }
        drop(state);
        self.publish();
    }

    /// 将本次可核验的原生模型终态反馈给选号器。@param request 当前调度租约。@return 无。
    pub(crate) fn track_scheduling(&mut self, request: SchedulingRequest) {
        self.scheduling = Some(request);
    }

    fn elapsed(&self) -> u64 {
        self.started.elapsed().as_millis().min(u64::MAX as u128) as u64
    }
    fn publish(&self) {
        self.trace.emit(Some(self.record.clone()));
    }
}

impl Drop for AgyAttemptTrace {
    /// 观察路径提前结束时保留不完整结果。@return 无。
    fn drop(&mut self) {
        self.finish(
            if self.source_error {
                "upstream_error"
            } else {
                "incomplete"
            },
            Some("native_control"),
        );
    }
}

fn uuid(value: Option<&str>) -> Option<String> {
    value
        .and_then(|v| Uuid::parse_str(v).ok())
        .map(|id| id.to_string())
}
fn label(value: Option<&str>) -> Option<String> {
    value
        .filter(|v| {
            v.len() <= 128
                && !v.starts_with("sk-")
                && v.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"-_.".contains(&b))
        })
        .map(str::to_owned)
}

fn usage_metadata(raw: &Map<String, Value>) -> (Value, bool) {
    let mut result = Map::new();
    let mut complete = [
        "promptTokenCount",
        "candidatesTokenCount",
        "totalTokenCount",
    ]
    .iter()
    .all(|key| raw.get(*key).and_then(Value::as_u64).is_some());
    for (name, value) in raw.iter().take(32) {
        if label(Some(name)).is_none() {
            complete = false;
            continue;
        }
        if value.as_u64().is_some() {
            result.insert(name.clone(), value.clone());
        } else if let Some(rows) = value.as_array() {
            let mut items = vec![];
            for row in rows.iter().take(32) {
                let modality = row["modality"]
                    .as_str()
                    .filter(|v| matches!(*v, "TEXT" | "IMAGE" | "VIDEO" | "AUDIO" | "DOCUMENT"));
                if let (Some(modality), Some(count)) = (modality, row["tokenCount"].as_u64()) {
                    items.push(json!({"modality":modality,"tokenCount":count}));
                } else {
                    complete = false;
                }
            }
            complete &= rows.len() <= 32;
            result.insert(name.clone(), Value::Array(items));
        } else {
            complete = false;
        }
    }
    complete &= raw.len() <= 32;
    let value = Value::Object(result);
    if value.to_string().len() > 4096 {
        (Value::Null, false)
    } else {
        (value, complete)
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use axum::body::{Body, to_bytes};
    use axum::response::Response;
    use serde_json::json;
    use sqlx::any::AnyPoolOptions;
    use uuid::Uuid;

    use super::{AgyAttemptTrace, usage_metadata};
    use crate::model::account::Account;
    use crate::model::request_diagnostics::ExecutionLocation;
    use crate::service::agy_contract::{AgyModelId, AgySystemPromptPolicy};
    use crate::service::diagnostics::{RequestTraceGuard, TraceContext};
    use crate::store::db::migrate;
    use crate::store::diagnostics_store::DiagnosticsStore;

    /// 建立真实SQLite诊断和合成提交。@return 观察器、存储与HTTP根。
    async fn fixture() -> (AgyAttemptTrace, Arc<DiagnosticsStore>, TraceContext) {
        sqlx::any::install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        migrate(&pool, "sqlite").await.unwrap();
        let store = Arc::new(DiagnosticsStore::new(pool));
        let trace = TraceContext::for_protocol(store.clone(), "antigravity", "gemini");
        let account: Account = serde_json::from_value(json!({
            "id":7,"name":"合成测试","email":"fixture@example.invalid","status":"active","device_id":"synthetic-device",
            "canonical_env":{},"canonical_prompt_env":{},"canonical_process":{},"billing_mode":"strip",
            "created_at":"2026-11-18T00:00:00Z","updated_at":"2026-11-18T00:00:00Z"
        })).unwrap();
        let policy = AgySystemPromptPolicy::default();
        let observer = AgyAttemptTrace::begin(
            Some(&trace),
            &account,
            "claude-sonnet",
            &AgyModelId::Name("MODEL_SYNTHETIC".into()),
            Some(ExecutionLocation {
                node_key: "local".into(),
                environment_id: "synthetic-agy".into(),
                generation: 3,
                assignment_revision: None,
            }),
            1,
            &policy,
            &Uuid::new_v4().to_string(),
            &json!({}),
            false,
        )
        .unwrap();
        (observer, store, trace)
    }

    /// 保存 AGY 真实恢复观测，兼容版本较旧的执行记录。@return 无。
    #[tokio::test]
    async fn keeps_verified_runtime_start_source() {
        for source in [None, Some("criu_restore"), Some("unverified")] {
            let (mut observer, store, _) = fixture().await;
            let worker = Uuid::new_v4().to_string();
            let generation = Uuid::new_v4().to_string();
            let mut event = json!({
                "type": "request_prepared", "worker_id": worker, "generation": generation,
                "runtime": {"worker_id": worker, "worker_pid": 12, "kernel_generation": generation,
                    "warm_hit": false, "preparation_wait_ms": 2, "checkout_ms": 310,
                    "worker_start_ms": 300, "prepared_ms": 330}
            });
            if let Some(source) = source {
                event["runtime"]["start_source"] = json!(source);
            }
            observer.native(&event, &json!({}));
            observer.finish("success", None);
            store.flush().await.unwrap();
            let detail = store.detail(&observer.record.request_id).await.unwrap();
            let runtime = serde_json::to_value(&detail.attempts[0].runtime).unwrap();
            if source == Some("unverified") {
                assert!(runtime.is_null());
            } else {
                assert_eq!(runtime["worker_pid"], 12);
                assert_eq!(runtime["checkout_ms"], 310);
                assert_eq!(runtime["start_source"].as_str(), source);
            }
        }
    }

    /// 重复累计帧保留真实零值，异常扩展保持缺口并拒绝字符串。@return 无。
    #[tokio::test]
    async fn source_usage_keeps_zero_maximum_and_unknown_separate() {
        let (mut observer, _, _) = fixture().await;
        assert_eq!(
            observer
                .record
                .execution_location
                .as_ref()
                .unwrap()
                .node_key,
            "local"
        );
        assert_eq!(
            observer
                .record
                .context
                .as_ref()
                .unwrap()
                .platform
                .as_deref(),
            Some("antigravity")
        );
        assert_eq!(observer.record.tokens.input_tokens, None);
        assert!(observer.record.context.as_ref().unwrap().usage.is_none());
        let frame = json!({"usageMetadata":{"promptTokenCount":0,"candidatesTokenCount":4,"totalTokenCount":4,"cachedContentTokenCount":0,"thoughtsTokenCount":0}});
        observer.frame(&frame);
        observer.frame(&frame);
        assert_eq!(observer.record.tokens.input_tokens, Some(0));
        assert_eq!(observer.record.tokens.output_tokens, Some(4));
        assert_eq!(observer.record.tokens.cache_read_tokens, Some(0));
        observer.frame(&json!({"usageMetadata":{"promptTokenCount":0,"candidatesTokenCount":2,"totalTokenCount":2}}));
        assert_eq!(observer.record.tokens.output_tokens, Some(4));
        assert_eq!(
            observer
                .record
                .context
                .as_ref()
                .unwrap()
                .usage
                .as_ref()
                .unwrap()
                .total_tokens,
            Some(4)
        );
        observer.frame(&json!({"candidates":[{"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":-1,"candidatesTokenCount":"synthetic-secret"}}));
        observer.completed(false, &[]);
        assert!(observer.record.partial);
        assert_eq!(observer.record.outcome, "success");
        assert!(
            !serde_json::to_string(&observer.record)
                .unwrap()
                .contains("synthetic-secret")
        );
    }

    /// 工具完成后仍等待物理回执，后续失败与重复回执保持独立归属。@return 无。
    #[tokio::test]
    async fn tool_completion_waits_for_job_receipt_and_preserves_http_result() {
        for status in ["completed", "error"] {
            let (mut observer, store, trace) = fixture().await;
            observer.frame(&json!({"candidates":[{"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":1,"totalTokenCount":2}}));
            observer.completed(true, &[json!({"id":"synthetic-tool"})]);
            let response = RequestTraceGuard::new(trace).wrap(Response::new(Body::empty()));
            to_bytes(response.into_body(), 1024).await.unwrap();
            store.flush().await.unwrap();
            let before = store.detail(&observer.record.request_id).await.unwrap();
            observer.tool_finalized("completed");
            store.flush().await.unwrap();
            let waiting = store.detail(&observer.record.request_id).await.unwrap();
            let context = waiting.attempts[0].context.as_ref().unwrap();
            assert_eq!(context.tool_turn.as_ref().unwrap().state, "completed");
            assert!(context.control_state.is_none());
            assert!(context.control_observed_at.is_none());
            observer.finalized(status);
            store.flush().await.unwrap();
            let first = store.detail(&observer.record.request_id).await.unwrap();
            observer.finalized(if status == "completed" {
                "error"
            } else {
                "completed"
            });
            store.flush().await.unwrap();
            let final_record = store.detail(&observer.record.request_id).await.unwrap();
            let context = final_record.attempts[0].context.as_ref().unwrap();
            assert_eq!(context.control_state.as_deref(), Some(status));
            assert_eq!(
                context.control_observed_at,
                first.attempts[0]
                    .context
                    .as_ref()
                    .unwrap()
                    .control_observed_at
            );
            assert_eq!(context.tool_turn.as_ref().unwrap().state, "completed");
            assert_eq!(final_record.request.finished_at, before.request.finished_at);
            assert_eq!(final_record.request.started_at, before.request.started_at);
            assert_eq!(final_record.request.outcome, "success");
            assert_eq!(final_record.request.attempt_count, 1);
            assert_eq!(
                final_record.attempts[0].finished_at,
                before.attempts[0].finished_at
            );
            assert_eq!(
                final_record.attempts[0].duration_ms,
                before.attempts[0].duration_ms
            );
        }
    }

    /// 保存白名单控制码，并在收到退役回执后保留真实的模型成功结果。@return 无。
    #[tokio::test]
    async fn completed_source_preserves_control_failure_independently() {
        let (mut observer, store, trace) = fixture().await;
        observer.native(
            &json!({"type":"error","code":"opaque-credential"}),
            &json!({}),
        );
        assert!(
            observer
                .record
                .context
                .as_ref()
                .unwrap()
                .control_error_code
                .is_none()
        );
        observer.frame(&json!({"candidates":[{"finishReason":"STOP","content":{"parts":[{"text":"合成模型结果"}]}}],
            "usageMetadata":{"promptTokenCount":12,"candidatesTokenCount":2,"totalTokenCount":14}}));
        observer.native(&json!({"type":"completed","control_error_code":"native_request_failed","control_recovery":"kept","native_model_calls":1}), &json!({}));
        observer.completed(false, &[]);
        let response = RequestTraceGuard::new(trace).wrap(Response::new(Body::empty()));
        to_bytes(response.into_body(), 1024).await.unwrap();
        observer.finalized("error");
        store.flush().await.unwrap();
        let detail = store.detail(&observer.record.request_id).await.unwrap();
        let attempt = &detail.attempts[0];
        let context = attempt.context.as_ref().unwrap();
        assert_eq!(detail.request.outcome, "success");
        assert_eq!(attempt.outcome, "success");
        assert!(!attempt.partial);
        assert_eq!(context.control_state.as_deref(), Some("error"));
        assert_eq!(
            context.control_error_code.as_deref(),
            Some("native_request_failed")
        );
        assert_eq!(context.native_model_calls, Some(1));
        assert_eq!(context.control_recovery.as_deref(), Some("kept"));
    }

    /// 原生取消先于idle时，只记录已观测的尝试取消。@return 无。
    #[tokio::test]
    async fn native_cancellation_keeps_physical_closure_unknown_until_receipt() {
        let (mut observer, store, _) = fixture().await;
        observer.finish("cancelled", Some("native_control"));
        store.flush().await.unwrap();
        let before = store.detail(&observer.record.request_id).await.unwrap();
        assert_eq!(before.attempts[0].outcome, "cancelled");
        assert!(
            before.attempts[0]
                .context
                .as_ref()
                .unwrap()
                .control_state
                .is_none()
        );
        observer.finalized("cancelled");
        store.flush().await.unwrap();
        let after = store.detail(&observer.record.request_id).await.unwrap();
        assert_eq!(
            after.attempts[0]
                .context
                .as_ref()
                .unwrap()
                .control_state
                .as_deref(),
            Some("cancelled")
        );
        assert_eq!(
            after.attempts[0].finished_at,
            before.attempts[0].finished_at
        );
        assert_eq!(after.attempts[0].outcome, "cancelled");
    }

    /// 字节及条目预算保持明确的不完整标记。@return 无。
    #[test]
    fn source_usage_rejects_invalid_and_oversized_fields() {
        let raw = json!({"promptTokenCount":0,"candidatesTokenCount":0,"totalTokenCount":0});
        assert!(usage_metadata(raw.as_object().unwrap()).1);
        assert!(!usage_metadata(json!({}).as_object().unwrap()).1);
        let mut raw = raw.as_object().unwrap().clone();
        raw.insert("private".into(), json!("synthetic-secret"));
        let (safe, complete) = usage_metadata(&raw);
        assert!(!complete);
        assert!(safe.get("private").is_none());
        for index in 0..40 {
            raw.insert(format!("extension{index}"), json!(index));
        }
        let (safe, complete) = usage_metadata(&raw);
        assert!(!complete);
        assert!(safe.as_object().unwrap().len() <= 32);
    }
}
