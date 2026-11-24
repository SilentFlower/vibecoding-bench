//! 按真实入站会话隔离的限时封禁，与上游身份改写和诊断开关独立。

pub(crate) use crate::model::session_policy_block::classify_policy_refusal as classify;

use std::cell::RefCell;
use std::collections::HashMap;
use std::future::Future;
use std::sync::Arc;

use axum::body::Body;
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use chrono::{DateTime, Utc};
use http_body_util::{BodyExt, StreamBody};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tokio::sync::RwLock;

use crate::error::AppError;
use crate::model::session_policy_block::SessionPolicyIdentity;
use crate::service::diagnostics;
use crate::service::rewriter::extract_session_id_from_body;
use crate::service::usage::UsageCapture;
use crate::store::session_policy_block_store::SessionPolicyBlockStore;
use crate::store::settings_store::{
    DEFAULT_SESSION_POLICY_BLOCK_DURATION_MINUTES, DEFAULT_SESSION_POLICY_BLOCK_ENABLED,
    SettingsStore,
};

/// 已明确识别的上游策略拒答，阻止通用修复重试。
#[derive(Clone)]
pub(crate) struct PolicyRefusal;

tokio::task_local! {
    static CURRENT: RefCell<Option<RequestPolicy>>;
}

#[derive(Clone)]
struct RequestPolicy {
    service: Arc<SessionPolicyBlockService>,
    identity: SessionPolicyIdentity,
}

/// 原子热加载的封禁配置。
#[derive(Clone, Copy)]
pub(crate) struct SessionPolicyBlockConfig {
    pub enabled: bool,
    pub duration_ms: i64,
}

impl SessionPolicyBlockConfig {
    /// 从已合并设置构造配置并校验时间运算范围。
    /// @param settings 已保存或准备保存的字符串配置。
    /// @return 合法配置或明确校验错误。
    pub(crate) fn parse(settings: &HashMap<String, String>) -> Result<Self, AppError> {
        let enabled = settings
            .get("session_policy_block_enabled")
            .map(String::as_str)
            .unwrap_or(DEFAULT_SESSION_POLICY_BLOCK_ENABLED);
        if !matches!(enabled, "true" | "false") {
            return Err(AppError::BadRequest(
                "自动封禁开关必须是 true 或 false".into(),
            ));
        }
        let raw = settings
            .get("session_policy_block_duration_minutes")
            .map(String::as_str)
            .unwrap_or(DEFAULT_SESSION_POLICY_BLOCK_DURATION_MINUTES);
        let duration_ms = raw
            .parse::<i64>()
            .ok()
            .filter(|_| !raw.is_empty() && raw.bytes().all(|c| c.is_ascii_digit()))
            .filter(|v| *v > 0)
            .and_then(|v| v.checked_mul(60_000))
            .filter(|v| {
                Utc::now()
                    .timestamp_millis()
                    .checked_add(*v)
                    .and_then(DateTime::from_timestamp_millis)
                    .is_some()
            })
            .ok_or_else(|| AppError::BadRequest("封禁时长必须是有效范围内的正整数分钟".into()))?;
        Ok(Self {
            enabled: enabled == "true",
            duration_ms,
        })
    }
}

/// 管理配置和持久封禁访问。
pub(crate) struct SessionPolicyBlockService {
    pub store: SessionPolicyBlockStore,
    config: RwLock<SessionPolicyBlockConfig>,
}

impl SessionPolicyBlockService {
    /// 创建默认启用的服务。
    /// @param settings 现有设置与数据库连接来源。
    /// @return 封禁服务。
    pub(crate) fn new(settings: &SettingsStore) -> Self {
        Self {
            store: SessionPolicyBlockStore::new(settings.database_pool()),
            config: RwLock::new(
                SessionPolicyBlockConfig::parse(&HashMap::new()).expect("封禁默认值合法"),
            ),
        }
    }

    /// 串行读取并更新配置，避免较早读取覆盖较晚保存。
    /// @param settings 全局设置存储。
    /// @return 刷新结果。
    pub(crate) async fn reload(&self, settings: &SettingsStore) -> Result<(), AppError> {
        let mut config = self.config.write().await;
        *config = SessionPolicyBlockConfig::parse(&settings.get_all().await?)?;
        Ok(())
    }

    /// 冻结原始会话身份，在账号选择前完成本地拦截。
    /// @param self 共享服务。
    /// @param token_id 已鉴权调用方身份。
    /// @param body 改写前请求。
    /// @return 本地封禁响应或空。
    pub(crate) async fn begin(
        self: &Arc<Self>,
        token_id: i64,
        body: &Value,
    ) -> Result<Option<Response>, AppError> {
        let _ = CURRENT.try_with(|slot| *slot.borrow_mut() = None);
        let config = *self.config.read().await;
        if !config.enabled {
            return Ok(None);
        }
        let Some(session) = extract_session_id_from_body(body).filter(|sid| !sid.trim().is_empty())
        else {
            return Ok(None);
        };
        let mut hash = Sha256::new();
        hash.update(b"flower2api:session-policy-block:v1\0");
        hash.update(token_id.to_be_bytes());
        hash.update(session.as_bytes());
        let context = RequestPolicy {
            service: self.clone(),
            identity: SessionPolicyIdentity {
                session_key: format!("{:x}", hash.finalize()),
                api_token_id: token_id,
                model: body["model"]
                    .as_str()
                    .filter(|s| s.len() <= 256)
                    .unwrap_or_default()
                    .into(),
                source_request_id: diagnostics::current_request_id(),
            },
        };
        let _ = CURRENT.try_with(|slot| *slot.borrow_mut() = Some(context));
        check_current().await
    }
}

/// 为当前请求建立独立上下文，响应流自行持有所需快照。
/// @param future 原请求处理过程。
/// @return 原处理结果。
pub(crate) fn scope<F: Future>(future: F) -> impl Future<Output = F::Output> {
    // 网关包含多条转发状态机，将其放入堆中，避免并发组合放大请求栈占用。
    CURRENT.scope(RefCell::new(None), Box::pin(future))
}

fn current() -> Option<RequestPolicy> {
    CURRENT
        .try_with(|slot| slot.borrow().clone())
        .ok()
        .flatten()
}

/// 在实际提交前复核封禁，命中时只累计一次被拒请求。
/// @return 封禁响应或空；查询失败返回临时故障。
pub(crate) async fn check_current() -> Result<Option<Response>, AppError> {
    let Some(context) = current() else {
        return Ok(None);
    };
    if !context.service.config.read().await.enabled {
        return Ok(None);
    }
    let now = Utc::now().timestamp_millis();
    let Some(block) = context
        .service
        .store
        .hit(&context.identity.session_key, now)
        .await?
    else {
        return Ok(None);
    };
    diagnostics::error_stage("session_policy_block");
    Ok(Some((StatusCode::BAD_REQUEST,axum::Json(json!({"type":"error","error":{
        "type":"invalid_request_error","code":"session_policy_blocked","message":"当前会话处于策略封禁期，请在到期或管理员解除后继续。",
        "details":{"retryable":false,"expires_at":DateTime::from_timestamp_millis(block.expires_at_ms).map(|v|v.to_rfc3339()),"remaining_seconds":(block.expires_at_ms-now+999)/1000}
    }}))).into_response()))
}

/// 记录已解析的上游策略拒答。
/// @param account_id 实际触发账号。
/// @param reason 白名单原因。
/// @return 持久写入结果，无会话时保持原行为。
pub(crate) async fn remember_current(account_id: i64, reason: &str) -> Result<(), AppError> {
    if let Some(context) = current() {
        remember(&context, account_id, reason).await?;
    }
    Ok(())
}

async fn remember(context: &RequestPolicy, account_id: i64, reason: &str) -> Result<(), AppError> {
    // 时长在真正识别到拒答时读取，长请求也遵守管理员刚保存的新封禁策略。
    let config = *context.service.config.read().await;
    if !config.enabled {
        return Ok(());
    }
    context
        .service
        .store
        .remember(
            &context.identity,
            account_id,
            reason,
            Utc::now().timestamp_millis(),
            config.duration_ms,
        )
        .await
}

/// 独立观察真实响应帧，保留数据帧与 trailers，并在拒答帧交付前落盘。
/// @param response 原始上游响应。
/// @param account_id 实际账号。
/// @param codings 响应的编码链。
/// @return 原协议响应及独立封禁观察器。
pub(crate) fn observe_response(
    response: Response,
    account_id: i64,
    codings: Vec<String>,
) -> Response {
    if !response.status().is_success() {
        return response;
    }
    let Some(context) = current() else {
        return response;
    };
    let (parts, body) = response.into_parts();
    let mut capture = UsageCapture::observer(&json!({}));
    capture.configure_codings(&codings);
    let stream = futures_util::stream::unfold(
        (body, Some(capture), context, false),
        move |(mut body, mut capture, context, mut recorded)| async move {
            let frame = body.frame().await;
            if let Some(Ok(frame)) = &frame {
                if let Some(bytes) = frame.data_ref() {
                    capture
                        .as_mut()
                        .expect("观察器在响应结束前存在")
                        .observe(bytes);
                    if !recorded
                        && let Some(reason) =
                            capture.as_mut().and_then(UsageCapture::take_policy_reason)
                    {
                        if let Err(error) = remember(&context, account_id, reason).await {
                            return Some((
                                Err(axum::Error::new(std::io::Error::other(error.to_string()))),
                                (Body::empty(), None, context, true),
                            ));
                        }
                        recorded = true;
                    }
                }
            }
            if frame.is_none() {
                if let Some(capture) = capture.take() {
                    let observation = capture.observation(true);
                    if !recorded && let Some(reason) = observation.policy_reason {
                        if let Err(error) = remember(&context, account_id, reason).await {
                            return Some((
                                Err(axum::Error::new(std::io::Error::other(error.to_string()))),
                                (Body::empty(), None, context, true),
                            ));
                        }
                    }
                }
                return None;
            }
            frame.map(|frame| (frame, (body, capture, context, recorded)))
        },
    );
    Response::from_parts(parts, Body::new(StreamBody::new(stream)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::service::runtime_transport::{
        TUI_ERROR_SOURCE, TUI_GATEWAY_ID_HEADER, TUI_JSON_PROJECTION_V1, TUI_SSE_PROJECTION_V1,
        tui_public_response,
    };
    use bytes::Bytes;
    use flate2::{Compression, write::GzEncoder};
    use http_body::Frame;
    use sqlx::any::{AnyPoolOptions, install_default_drivers};
    use std::io::Write;

    async fn service() -> Arc<SessionPolicyBlockService> {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        crate::store::db::migrate(&pool, "sqlite").await.unwrap();
        Arc::new(SessionPolicyBlockService::new(&SettingsStore::new(pool)))
    }

    fn body(sid: &str) -> Value {
        json!({"model":"claude-opus-5-5","metadata":{"user_id":json!({"session_id":sid}).to_string()},"messages":[{"role":"user","content":"合成请求"}]})
    }

    /// 截图错误在结构化响应内识别，普通回答和认证引用保持独立。
    #[test]
    fn session_policy_block_classifies_only_refusal_evidence() {
        let message = "Opus safeguards flagged this message (https://www.anthropic.com/legal/aup). Details: [reasoning_extraction]";
        assert_eq!(
            classify(
                &json!({"type":"error","error":{"type":"invalid_request_error","message":message}})
            ),
            Some("reasoning_extraction")
        );
        assert_eq!(
            classify(&json!({"type":"message","content":[{"type":"text","text":message}]})),
            None
        );
        assert_eq!(
            classify(
                &json!({"type":"error","error":{"type":"authentication_error","message":message}})
            ),
            None
        );
        assert_eq!(
            classify(
                &json!({"type":"error","error":{"type":"rate_limit_error","message":"请求过多"}})
            ),
            None
        );
        assert_eq!(
            classify(&json!({"type":"message_delta","delta":{"stop_reason":"refusal"}})),
            Some("refusal")
        );
        assert_eq!(
            classify(&json!({"type":"error","error":{"upstream_code":"cyber_policy"}})),
            Some("content_policy")
        );
    }

    /// 默认24小时及时间范围校验明确，非法值保持拒绝。
    #[test]
    fn session_policy_block_config_rejects_invalid_duration() {
        assert_eq!(
            SessionPolicyBlockConfig::parse(&HashMap::new())
                .unwrap()
                .duration_ms,
            86_400_000
        );
        for raw in ["", "0", "-1", "1.5", "NaN", " 60", "9223372036854775807"] {
            assert!(
                SessionPolicyBlockConfig::parse(&HashMap::from([(
                    "session_policy_block_duration_minutes".into(),
                    raw.into()
                )]))
                .is_err(),
                "{raw}"
            );
        }
    }

    /// 已创建轮次只影响相同令牌和真实会话，功能关闭保留历史。
    #[tokio::test]
    async fn session_policy_block_scope_and_disable() {
        let service = service().await;
        scope(async {
            assert!(service.begin(11, &body("会话甲")).await.unwrap().is_none());
            remember_current(7, "usage_policy").await.unwrap();
            let response = service.begin(11, &body("会话甲")).await.unwrap().unwrap();
            assert_eq!(response.status(), StatusCode::BAD_REQUEST);
            let value: Value = serde_json::from_slice(
                &axum::body::to_bytes(response.into_body(), 8192)
                    .await
                    .unwrap(),
            )
            .unwrap();
            assert_eq!(value["error"]["code"], "session_policy_blocked");
            assert!(
                value["error"]["details"]["remaining_seconds"]
                    .as_i64()
                    .unwrap()
                    > 86_390
            );
            assert!(service.begin(12, &body("会话甲")).await.unwrap().is_none());
            assert!(service.begin(11, &body("会话乙")).await.unwrap().is_none());
            service.config.write().await.enabled = false;
            assert!(service.begin(11, &body("会话甲")).await.unwrap().is_none());
        })
        .await;
        let page = service
            .store
            .list("all", "", 1, 20, Utc::now().timestamp_millis())
            .await
            .unwrap();
        assert_eq!(page.total, 1);
        assert_eq!(page.items[0].blocked_request_count, 1);
        assert!(!serde_json::to_string(&page).unwrap().contains("会话甲"));
    }

    /// 压缩及分块SSE在交付拒答帧前落盘，且响应离开任务作用域后仍可观察。
    #[tokio::test]
    async fn session_policy_block_observes_encoded_stream_and_preserves_bytes() {
        for compressed in [false, true] {
            let service = service().await;
            let bytes=b"event: error\r\ndata: {\"type\":\"error\",\"error\":{\"type\":\"invalid_request_error\",\"message\":\"safeguards flagged this message [reasoning_extraction]\"}}\r\n\r\n";
            let wire = if compressed {
                let mut encoder = GzEncoder::new(Vec::new(), Compression::default());
                encoder.write_all(bytes).unwrap();
                encoder.finish().unwrap()
            } else {
                bytes.to_vec()
            };
            let chunks: Vec<_> = wire
                .chunks(7)
                .map(|chunk| Ok::<_, axum::Error>(Frame::data(Bytes::copy_from_slice(chunk))))
                .collect();
            let response = scope(async {
                service.begin(1, &body("流会话")).await.unwrap();
                let response = Response::new(Body::new(StreamBody::new(
                    futures_util::stream::iter(chunks),
                )));
                observe_response(
                    response,
                    5,
                    if compressed {
                        vec!["gzip".into()]
                    } else {
                        vec![]
                    },
                )
            })
            .await;
            let received = axum::body::to_bytes(response.into_body(), 8192)
                .await
                .unwrap();
            assert_eq!(received.as_ref(), wire.as_slice());
            let list = service
                .store
                .list("active", "", 1, 20, Utc::now().timestamp_millis())
                .await
                .unwrap();
            assert_eq!(list.total, 1);
            assert_eq!(list.items[0].reason, "reasoning_extraction");
            assert_eq!(list.items[0].account_id, 5);
        }
    }

    /// 热加载修改只影响新轮次，既有到期时间与功能关闭均符合保存值。
    #[tokio::test]
    async fn session_policy_block_duration_reload_preserves_existing_expiry() {
        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        crate::store::db::migrate(&pool, "sqlite").await.unwrap();
        let settings = SettingsStore::new(pool);
        let service = Arc::new(SessionPolicyBlockService::new(&settings));
        scope(async {
            service.begin(1, &body("旧会话")).await.unwrap();
            remember_current(7, "refusal").await.unwrap();
        })
        .await;
        let first = service
            .store
            .list("all", "", 1, 20, Utc::now().timestamp_millis())
            .await
            .unwrap()
            .items
            .remove(0);
        assert_eq!(first.expires_at_ms - first.blocked_at_ms, 86_400_000);
        settings
            .upsert_many(&HashMap::from([(
                "session_policy_block_duration_minutes".into(),
                "60".into(),
            )]))
            .await
            .unwrap();
        service.reload(&settings).await.unwrap();
        scope(async {
            assert!(service.begin(1, &body("旧会话")).await.unwrap().is_some());
            assert!(service.begin(1, &body("新会话")).await.unwrap().is_none());
            remember_current(7, "refusal").await.unwrap();
        })
        .await;
        scope(async {
            service.begin(1, &body("进行中会话")).await.unwrap();
            settings
                .upsert_many(&HashMap::from([(
                    "session_policy_block_duration_minutes".into(),
                    "30".into(),
                )]))
                .await
                .unwrap();
            service.reload(&settings).await.unwrap();
            remember_current(7, "refusal").await.unwrap();
            settings
                .upsert_many(&HashMap::from([(
                    "session_policy_block_enabled".into(),
                    "false".into(),
                )]))
                .await
                .unwrap();
            service.reload(&settings).await.unwrap();
            assert!(check_current().await.unwrap().is_none());
            remember_current(7, "refusal").await.unwrap();
        })
        .await;
        let items = service
            .store
            .list("all", "", 1, 20, Utc::now().timestamp_millis())
            .await
            .unwrap()
            .items;
        assert_eq!(
            items
                .iter()
                .find(|row| row.id == first.id)
                .unwrap()
                .expires_at_ms,
            first.expires_at_ms
        );
        assert_eq!(items.len(), 3);
        assert!(
            items
                .iter()
                .any(|row| row.expires_at_ms - row.blocked_at_ms == 3_600_000)
        );
        assert!(
            items
                .iter()
                .any(|row| row.expires_at_ms - row.blocked_at_ms == 1_800_000)
        );
    }

    /// 完整JSON在EOF确认后登记拒答，正常消息保持透传。
    #[tokio::test]
    async fn session_policy_block_observes_json_refusal() {
        let service = service().await;
        scope(async {
            service.begin(1, &body("JSON会话")).await.unwrap();
            let original =
                json!({"type":"message","stop_reason":"refusal","content":[]}).to_string();
            let response = observe_response(Response::new(Body::from(original.clone())), 5, vec![]);
            assert_eq!(
                axum::body::to_bytes(response.into_body(), 8192)
                    .await
                    .unwrap(),
                original
            );
            assert!(check_current().await.unwrap().is_some());
        })
        .await;
        service
            .store
            .list("all", "", 1, 20, Utc::now().timestamp_millis())
            .await
            .unwrap();
    }

    /// 同一已认证会话的 V2 JSON 和真实模型错误与 V1 使用同样的接受、隔离和排除条件。
    #[tokio::test]
    async fn session_policy_block_tui_delegated_json_and_errors() {
        let service = service().await;
        let error = json!({"type":"error","error":{"type":"invalid_request_error","upstream_code":"cyber_policy","message":"拒绝"}});
        let text = json!({"type":"message","content":[{"type":"text","text":"usage policy [reasoning_extraction]"}]});
        let refusal = json!({"type":"message","stop_reason":"refusal","content":[]});
        let quote = json!({"message":"usage policy"});
        let incomplete = json!({"type":"error","error":{"type":"api_error","message":"本机模型返回错误"},
            "_tui_policy_evidence":{"error":{"message":"usage policy private details"}}});
        let http = Some("local_provider_http");
        let cases = [
            (200, None, &refusal, true),
            (200, None, &text, false),
            (403, http, &error, true),
            (400, Some("local_provider_event"), &error, true),
            (401, http, &error, false),
            (429, http, &error, false),
            (403, http, &quote, false),
            (403, None, &error, false),
            (403, Some("local_provider_backoff"), &error, false),
            (400, http, &incomplete, true),
            (200, None, &incomplete, true),
        ];
        for (idx, (status, source, payload, expected)) in cases.into_iter().enumerate() {
            let request = body(&format!("JSON会话{idx}"));
            let mut raw = axum::http::Response::builder()
                .status(status)
                .header("content-type", "application/json")
                .header(TUI_GATEWAY_ID_HEADER, TUI_JSON_PROJECTION_V1);
            if let Some(source) = source {
                raw = raw.header(TUI_ERROR_SOURCE, source);
            }
            let private = raw.body(payload.to_string()).unwrap().into();
            scope(async {
                service.begin(11, &request).await.unwrap();
                let reply = tui_public_response(private, Some(7)).await.unwrap();
                let late_error = status == 200 && payload == &incomplete;
                assert_eq!(
                    reply.status().as_u16(),
                    if late_error { 502 } else { status }
                );
                assert_eq!(
                    reply.extensions().get::<PolicyRefusal>().is_some(),
                    expected && (status != 200 || late_error)
                );
                assert!(!reply.headers().contains_key(TUI_ERROR_SOURCE));
                let wire = axum::body::to_bytes(reply.into_body(), 8192).await.unwrap();
                assert!(!String::from_utf8_lossy(&wire).contains("upstream_code"));
                assert!(!String::from_utf8_lossy(&wire).contains("private details"));
                assert!(!String::from_utf8_lossy(&wire).contains("_tui_policy_evidence"));
                assert_eq!(check_current().await.unwrap().is_some(), expected);
                assert!(service.begin(12, &request).await.unwrap().is_none());
            })
            .await;
        }
    }

    /// 真流先交付普通文本，拒答帧到达时再按当时的开关和期限登记原令牌。
    #[tokio::test]
    async fn session_policy_block_tui_stream_before_refusal_and_live_disable() {
        use futures_util::StreamExt;
        use std::time::Duration;
        use tokio::sync::oneshot;
        use tokio::time::timeout;

        for enabled in [true, false] {
            let service = service().await;
            service.config.write().await.duration_ms = 120_000;
            let request = body("同一真实流式会话");
            let (release, wait) = oneshot::channel();
            let opening = Bytes::from_static(b"event: message_start\ndata: {\"type\":\"message_start\",\"message\":{\"type\":\"message\",\"id\":\"msg_private\"}}\n\n");
            let block = Bytes::from_static(b"event: content_block_start\ndata: {\"type\":\"content_block_start\",\"index\":0,\"content_block\":{\"type\":\"text\",\"text\":\"\"}}\n\n");
            let text = Bytes::from_static(b"event: content_block_delta\ndata: {\"type\":\"content_block_delta\",\"index\":0,\"delta\":{\"type\":\"text_delta\",\"text\":\"usage policy [reasoning_extraction]\"}}\n\n");
            let source = futures_util::stream::iter([opening, block.clone(), text.clone()].map(Ok::<_, std::io::Error>))
                .chain(futures_util::stream::once(async move {
                    wait.await.unwrap();
                    Ok(Bytes::from_static(b"event: error\ndata: {\"type\":\"error\",\"error\":{\"code\":\"cyber_policy\",\"message\":\"policy test\"}}\n\n"))
                }));
            let private = axum::http::Response::builder()
                .header("content-type", "text/event-stream")
                .header(TUI_GATEWAY_ID_HEADER, TUI_SSE_PROJECTION_V1)
                .body(reqwest::Body::wrap_stream(source))
                .unwrap()
                .into();
            let mut stream = scope(async {
                service.begin(11, &request).await.unwrap();
                let response = tui_public_response(private, Some(7)).await.unwrap();
                assert_eq!(response.status(), StatusCode::OK);
                response.into_body().into_data_stream()
            })
            .await;
            timeout(Duration::from_secs(2), async {
                let start = stream.next().await.unwrap().unwrap();
                assert!(start.starts_with(b"event: message_start"));
                assert_eq!(stream.next().await.unwrap().unwrap(), block);
                assert_eq!(stream.next().await.unwrap().unwrap(), text);
            })
            .await
            .unwrap();
            scope(async {
                assert!(service.begin(11, &request).await.unwrap().is_none());
            })
            .await;
            service.config.write().await.enabled = enabled;
            release.send(()).unwrap();
            let error = stream.next().await.unwrap().unwrap();
            assert!(!String::from_utf8_lossy(&error).contains("cyber_policy"));
            let page = service
                .store
                .list("all", "", 1, 10, Utc::now().timestamp_millis())
                .await
                .unwrap();
            assert_eq!(page.total, i64::from(enabled));
            if enabled {
                let row = &page.items[0];
                assert_eq!(row.expires_at_ms - row.blocked_at_ms, 120_000);
                assert_eq!((row.account_id, row.api_token_id), (7, 11));
                assert_eq!(row.reason, "content_policy");
            }
            scope(async {
                assert_eq!(
                    service.begin(11, &request).await.unwrap().is_some(),
                    enabled
                );
                assert!(service.begin(12, &request).await.unwrap().is_none());
            })
            .await;
        }
    }
}
