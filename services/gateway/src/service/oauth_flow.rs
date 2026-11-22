use std::collections::HashMap;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use base64::Engine;
use rand::Rng;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tracing::debug;

use crate::error::AppError;
use crate::model::proxy::ProxyConnection;
use crate::service::runtime_bridge::agy_request;
use serde_json::{Value, json};

// ---------------------------------------------------------------------------
// OAuth 常量
// ---------------------------------------------------------------------------

const CLIENT_ID: &str = "9d1c250a-e61b-44d9-88ed-5944d1962f5e";
const AUTHORIZE_URL: &str = "https://claude.ai/oauth/authorize";
const TOKEN_URL: &str = "https://platform.claude.com/v1/oauth/token";
const REDIRECT_URI: &str = "https://platform.claude.com/oauth/code/callback";

const SCOPE_FULL: &str =
    "user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload";
const SCOPE_INFERENCE: &str = "user:inference";

/// 会话 TTL（30 分钟）。
const SESSION_TTL: Duration = Duration::from_secs(30 * 60);

/// Setup-Token 有效期（1 年）。
const SETUP_TOKEN_EXPIRES_IN: i64 = 365 * 24 * 60 * 60;

// ---------------------------------------------------------------------------
// PKCE 工具
// ---------------------------------------------------------------------------

/// base64url 编码（无填充）。
fn base64url_encode(data: &[u8]) -> String {
    base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(data)
}

/// 生成 PKCE code_verifier（32 字节随机 → 43 字符 base64url）。
fn generate_code_verifier() -> String {
    let mut buf = [0u8; 32];
    rand::thread_rng().fill(&mut buf);
    base64url_encode(&buf)
}

/// 计算 S256 code_challenge。
fn generate_code_challenge(verifier: &str) -> String {
    let hash = Sha256::digest(verifier.as_bytes());
    base64url_encode(&hash)
}

/// 生成随机 state。
fn generate_state() -> String {
    let mut buf = [0u8; 32];
    rand::thread_rng().fill(&mut buf);
    base64url_encode(&buf)
}

/// 生成 session_id。
fn generate_session_id() -> String {
    let mut buf = [0u8; 16];
    rand::thread_rng().fill(&mut buf);
    hex::encode(buf)
}

// ---------------------------------------------------------------------------
// 会话存储
// ---------------------------------------------------------------------------

#[derive(Clone)]
struct OAuthSession {
    native: bool,
    account_id: Option<i64>,
    replace_proxy: bool,
    state: String,
    code_verifier: String,
    scope: String,
    proxy_url: String,
    created_at: Instant,
}

/// 内存级 OAuth 会话存储，带 TTL 自动清理。
struct SessionStore {
    sessions: Mutex<HashMap<String, OAuthSession>>,
}

impl SessionStore {
    fn new() -> Self {
        Self {
            sessions: Mutex::new(HashMap::new()),
        }
    }

    fn set(&self, id: &str, session: OAuthSession) {
        let mut map = self.sessions.lock().unwrap();
        // 顺便清理过期会话
        map.retain(|_, s| s.created_at.elapsed() < SESSION_TTL);
        map.insert(id.to_string(), session);
    }

    fn take(&self, id: &str) -> Option<OAuthSession> {
        let mut map = self.sessions.lock().unwrap();
        map.remove(id)
    }
}

// ---------------------------------------------------------------------------
// 请求 / 响应
// ---------------------------------------------------------------------------

/// 生成授权 URL 的请求。
#[derive(Deserialize)]
pub struct GenerateAuthUrlRequest {
    pub platform: Option<String>,
    pub account_id: Option<i64>,
    pub proxy_url: Option<String>,
    pub proxy_id: Option<String>,
    pub proxy_revision: Option<String>,
    #[serde(default)]
    pub replace_proxy: bool,
}

/// 生成授权 URL 的响应。
#[derive(Serialize)]
pub struct GenerateAuthUrlResponse {
    pub auth_url: String,
    pub session_id: String,
}

/// 交换 code 的请求。
#[derive(Deserialize)]
pub struct ExchangeCodeRequest {
    pub session_id: String,
    pub code: String,
}

/// 交换 code 的响应。
#[derive(Serialize)]
pub struct ExchangeCodeResponse {
    /// 同次AGY原生身份核验的有来源能力，CC响应沿原字段集合。
    #[serde(skip_serializing_if = "Option::is_none")]
    pub capabilities: Option<Value>,
    pub access_token: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub refresh_token: String,
    pub expires_in: i64,
    pub expires_at: i64,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub scope: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub account_uuid: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub organization_uuid: String,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub email_address: String,
}

/// 平台 token exchange 原始响应。
#[derive(Deserialize)]
struct TokenExchangeResponse {
    access_token: String,
    #[serde(default)]
    refresh_token: String,
    #[serde(default)]
    expires_in: i64,
    #[serde(default)]
    scope: String,
    account: Option<TokenAccount>,
    organization: Option<TokenOrganization>,
}

#[derive(Deserialize)]
struct TokenAccount {
    uuid: String,
    #[serde(default)]
    email_address: String,
}

#[derive(Deserialize)]
struct TokenOrganization {
    uuid: String,
}

// ---------------------------------------------------------------------------
// OAuthFlowService
// ---------------------------------------------------------------------------

/// 处理 OAuth 授权链接生成和 code 交换。
pub struct OAuthFlowService {
    store: SessionStore,
}

impl OAuthFlowService {
    /// 在目录配置锁内更新尚未交换的授权连接，过期会话无需重建。
    /// @param id 授权会话。@param source 原指纹。@param destination 新连接。@return 目标已收口。
    pub fn synchronize_proxy_connection(&self, id: &str, source: &str, destination: &str) -> bool {
        let mut sessions = self.store.sessions.lock().unwrap();
        sessions.retain(|_, session| session.created_at.elapsed() < SESSION_TTL);
        let Some(session) = sessions.get_mut(id) else {
            return true;
        };
        let Ok(connection) = ProxyConnection::parse(&session.proxy_url) else {
            return false;
        };
        if session.native && connection.fingerprint() == source {
            return false;
        }
        if connection.fingerprint() == source {
            session.proxy_url = destination.to_owned();
        }
        true
    }
    pub fn new() -> Self {
        Self {
            store: SessionStore::new(),
        }
    }

    /// 读取未过期授权流程的私有代理连接，供目录引用保护使用。
    /// @return 私有会话身份与连接，调用方只公开白名单身份。
    pub fn proxy_references(&self) -> Vec<(String, String)> {
        let mut sessions = self.store.sessions.lock().unwrap();
        sessions.retain(|_, session| session.created_at.elapsed() < SESSION_TTL);
        sessions
            .iter()
            .filter(|(_, session)| !session.proxy_url.is_empty())
            .map(|(id, session)| (id.clone(), session.proxy_url.clone()))
            .collect()
    }

    /// 按可选平台复用原授权入口。@param req 平台、代理和目标。@return 既有链接与会话响应。
    pub async fn generate_platform_auth_url(
        &self,
        req: &GenerateAuthUrlRequest,
        generation: Option<i64>,
    ) -> Result<GenerateAuthUrlResponse, AppError> {
        match req.platform.as_deref().unwrap_or("claude_code") {
            "claude_code" => Ok(self.generate_auth_url(req)),
            "antigravity" => {
                let mut input = json!({"proxy_url":req.proxy_url.as_deref().unwrap_or(""),
                    "account_id":req.account_id,"generation":generation});
                if req.replace_proxy {
                    // 新选线需要原生端保存可供重启对账的线路回执。
                    input["replace_proxy"] = json!(true);
                }
                let result = agy_request("start", &input).await?;
                let auth_url = result["auth_url"]
                    .as_str()
                    .ok_or_else(|| AppError::ServiceUnavailable("AGY 原生授权链接缺失".into()))?
                    .to_owned();
                let session_id = result["session_id"]
                    .as_str()
                    .filter(|value| {
                        value.len() == 32 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
                    })
                    .ok_or_else(|| AppError::ServiceUnavailable("AGY 原生会话身份无效".into()))?
                    .to_owned();
                self.store.set(
                    &session_id,
                    OAuthSession {
                        native: true,
                        account_id: req.account_id,
                        replace_proxy: req.replace_proxy,
                        state: String::new(),
                        code_verifier: String::new(),
                        scope: String::new(),
                        proxy_url: req.proxy_url.clone().unwrap_or_default(),
                        created_at: Instant::now(),
                    },
                );
                Ok(GenerateAuthUrlResponse {
                    auth_url,
                    session_id,
                })
            }
            _ => Err(AppError::BadRequest("授权平台无效".into())),
        }
    }

    /// 读取原生会话绑定。@param id 原会话。@return 冻结的目标账号及私有线路。
    pub fn native_target(&self, id: &str) -> Option<(i64, String)> {
        self.store
            .sessions
            .lock()
            .unwrap()
            .get(id)
            .filter(|session| session.native && session.created_at.elapsed() < SESSION_TTL)
            .and_then(|session| {
                session
                    .account_id
                    .map(|account_id| (account_id, session.proxy_url.clone()))
            })
    }

    /// 收尾持久原生会话。@param id 原会话。@return 驱动终态。
    pub async fn cancel_native_session(&self, id: &str) -> Result<String, AppError> {
        let result = agy_request("cancel", &json!({"session_id":id})).await?;
        self.store.take(id);
        Ok(result["phase"].as_str().unwrap_or("reconcile").to_owned())
    }

    /// 取消原会话并结束原生进程。@param id 原会话。@return 原生阶段或普通取消终态。
    pub async fn cancel_session(&self, id: &str) -> Result<String, AppError> {
        let session = self.store.sessions.lock().unwrap().get(id).cloned();
        if session.is_some_and(|session| session.native) {
            let result = agy_request("cancel", &json!({"session_id":id})).await?;
            self.store.take(id);
            return Ok(result["phase"].as_str().unwrap_or("reconcile").to_owned());
        }
        self.store.take(id);
        Ok("cancelled".into())
    }

    /// 生成 OAuth 授权 URL（完整 scope）。
    pub fn generate_auth_url(&self, req: &GenerateAuthUrlRequest) -> GenerateAuthUrlResponse {
        self.build_auth_url(SCOPE_FULL, req.proxy_url.as_deref().unwrap_or(""))
    }

    /// 生成 Setup-Token 授权 URL（仅 user:inference）。
    pub fn generate_setup_token_url(
        &self,
        req: &GenerateAuthUrlRequest,
    ) -> GenerateAuthUrlResponse {
        self.build_auth_url(SCOPE_INFERENCE, req.proxy_url.as_deref().unwrap_or(""))
    }

    /// 交换 code 获取 OAuth token（完整 scope）。
    pub async fn exchange_code(
        &self,
        req: &ExchangeCodeRequest,
    ) -> Result<ExchangeCodeResponse, AppError> {
        self.do_exchange(&req.session_id, &req.code, false).await
    }

    /// 交换 code 获取 Setup-Token。
    pub async fn exchange_setup_token_code(
        &self,
        req: &ExchangeCodeRequest,
    ) -> Result<ExchangeCodeResponse, AppError> {
        self.do_exchange(&req.session_id, &req.code, true).await
    }

    // --- 内部实现 ---

    fn build_auth_url(&self, scope: &str, proxy_url: &str) -> GenerateAuthUrlResponse {
        let state = generate_state();
        let code_verifier = generate_code_verifier();
        let code_challenge = generate_code_challenge(&code_verifier);
        let session_id = generate_session_id();

        self.store.set(
            &session_id,
            OAuthSession {
                native: false,
                account_id: None,
                replace_proxy: false,
                state: state.clone(),
                code_verifier,
                scope: scope.to_string(),
                proxy_url: proxy_url.to_string(),
                created_at: Instant::now(),
            },
        );

        let encoded_redirect = percent_encode(REDIRECT_URI);
        let encoded_scope = scope.replace(' ', "+");

        let auth_url = format!(
            "{}?code=true&client_id={}&response_type=code&redirect_uri={}&scope={}&code_challenge={}&code_challenge_method=S256&state={}",
            AUTHORIZE_URL, CLIENT_ID, encoded_redirect, encoded_scope, code_challenge, state
        );

        debug!("generated auth URL for session {}", session_id);

        GenerateAuthUrlResponse {
            auth_url,
            session_id,
        }
    }

    async fn do_exchange(
        &self,
        session_id: &str,
        raw_code: &str,
        is_setup_token: bool,
    ) -> Result<ExchangeCodeResponse, AppError> {
        let native = self
            .store
            .sessions
            .lock()
            .unwrap()
            .get(session_id)
            .filter(|session| session.native)
            .cloned();
        if let Some(session) = native {
            if is_setup_token || session.created_at.elapsed() >= SESSION_TTL {
                return Err(AppError::BadRequest("AGY 授权会话无效或已过期".into()));
            }
            let result = agy_request(
                "exchange",
                &json!({"session_id":session_id,"code":raw_code}),
            )
            .await?;
            let observed_proxy = result.get("proxy_url").and_then(Value::as_str);
            if observed_proxy.is_some_and(|proxy| proxy != session.proxy_url)
                || (session.replace_proxy && observed_proxy.is_none())
            {
                return Err(AppError::ServiceUnavailable(
                    "AGY 原授权线路需要核对".into(),
                ));
            }
            let token = &result["document"]["token"];
            let text = |key: &str| {
                token[key]
                    .as_str()
                    .filter(|value| !value.is_empty())
                    .map(str::to_owned)
                    .ok_or_else(|| AppError::ServiceUnavailable("AGY 原生授权结果缺少凭据".into()))
            };
            let access_token = text("access_token")?;
            let refresh_token = text("refresh_token")?;
            let expires_at = chrono::DateTime::parse_from_rfc3339(&text("expiry")?)
                .map_err(|_| AppError::ServiceUnavailable("AGY 原生有效期无效".into()))?
                .timestamp();
            let email_address = result["email_address"]
                .as_str()
                .filter(|value| !value.is_empty())
                .ok_or_else(|| AppError::ServiceUnavailable("AGY 原生账号身份缺失".into()))?
                .to_owned();
            return Ok(ExchangeCodeResponse {
                capabilities: result.get("capabilities").cloned(),
                access_token,
                refresh_token,
                expires_in: expires_at - chrono::Utc::now().timestamp(),
                expires_at,
                email_address,
                scope: String::new(),
                account_uuid: String::new(),
                organization_uuid: String::new(),
            });
        }
        let session = self
            .store
            .take(session_id)
            .ok_or_else(|| AppError::BadRequest("invalid or expired session_id".into()))?;

        if session.created_at.elapsed() >= SESSION_TTL {
            return Err(AppError::BadRequest("session expired".into()));
        }

        // code 可能携带 state：code#state
        let (auth_code, code_state) = if let Some(idx) = raw_code.find('#') {
            (&raw_code[..idx], &raw_code[idx + 1..])
        } else {
            (raw_code, "")
        };

        // 构建 token exchange 请求体
        let mut body = json!({
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": session.code_verifier,
        });

        if !code_state.is_empty() {
            body["state"] = serde_json::Value::String(code_state.to_string());
        } else {
            body["state"] = serde_json::Value::String(session.state.clone());
        }

        if is_setup_token {
            body["expires_in"] = json!(SETUP_TOKEN_EXPIRES_IN);
        }

        debug!("exchanging code for session {}", session_id);

        // 发送 token exchange 请求
        let client = crate::tlsfp::get_request_client(&session.proxy_url)
            .map_err(|_| AppError::Internal("token exchange request client unavailable".into()))?;
        let resp = client
            .post(TOKEN_URL)
            .header("Content-Type", "application/json")
            .json(&body)
            .send()
            .await
            .map_err(|e| AppError::Internal(format!("token exchange request failed: {}", e)))?;

        let status = resp.status();
        if !status.is_success() {
            let text = resp.text().await.unwrap_or_default();
            return Err(AppError::Internal(format!(
                "token exchange failed: status {} {}",
                status, text
            )));
        }

        let token_resp: TokenExchangeResponse = resp
            .json()
            .await
            .map_err(|e| AppError::Internal(format!("token exchange parse failed: {}", e)))?;

        let expires_in = if token_resp.expires_in > 0 {
            token_resp.expires_in
        } else {
            3600
        };
        let expires_at = chrono::Utc::now().timestamp() + expires_in;

        Ok(ExchangeCodeResponse {
            capabilities: None,
            access_token: token_resp.access_token,
            refresh_token: token_resp.refresh_token,
            expires_in,
            expires_at,
            scope: token_resp.scope,
            account_uuid: token_resp
                .account
                .as_ref()
                .map(|a| a.uuid.clone())
                .unwrap_or_default(),
            email_address: token_resp
                .account
                .as_ref()
                .map(|a| a.email_address.clone())
                .unwrap_or_default(),
            organization_uuid: token_resp
                .organization
                .as_ref()
                .map(|o| o.uuid.clone())
                .unwrap_or_default(),
        })
    }
}

/// 简易 percent-encode（仅编码 URL 不安全字符）。
fn percent_encode(input: &str) -> String {
    let mut result = String::with_capacity(input.len() * 3);
    for b in input.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                result.push(b as char);
            }
            _ => {
                result.push_str(&format!("%{:02X}", b));
            }
        }
    }
    result
}

#[cfg(test)]
mod directory_tests {
    use super::*;

    #[test]
    fn selected_connection_is_frozen_for_original_authorization_session() {
        let service = OAuthFlowService::new();
        let request = GenerateAuthUrlRequest {
            platform: None,
            account_id: None,
            proxy_url: Some("socks5://user:secret@synthetic.invalid:1080".into()),
            proxy_id: None,
            proxy_revision: None,
            replace_proxy: false,
        };
        let response = service.generate_auth_url(&request);
        let references = service.proxy_references();
        assert_eq!(references[0].0, response.session_id);
        let session = service.store.take(&response.session_id).unwrap();
        assert_eq!(session.proxy_url, request.proxy_url.unwrap());
        assert!(service.proxy_references().is_empty());
    }
}
