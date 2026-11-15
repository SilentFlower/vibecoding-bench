//! 代理目录连接契约，私有认证与公开摘要分开。
use chrono::{DateTime, Utc};
use percent_encoding::percent_decode_str;
use reqwest::Url;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::error::AppError;

/// 管理连接字段；更新时未提交认证字段表示沿用。
#[derive(Clone, Deserialize)]
pub struct ProxyConnectionInput {
    pub protocol: String,
    pub host: String,
    pub port: u16,
    pub username: Option<String>,
    pub password: Option<String>,
}

/// 关联同步的固定目标身份；私有连接保留在服务端台账。
#[derive(Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct ProxySyncTarget {
    pub kind: String,
    pub id: String,
}

/// 已验证连接，同时保留不会泄露认证信息的公开地址。
#[derive(Clone)]
pub struct ProxyConnection {
    pub private_url: String,
    pub public_url: String,
    pub protocol: String,
    pub host: String,
    pub port: u16,
    pub username: String,
    pub password: String,
}

impl ProxyConnection {
    /// 解析历史连接并规范化，错误文本不包含原地址。
    /// @param raw 私有地址。
    /// @return 验证后的连接。
    pub fn parse(raw: &str) -> Result<Self, AppError> {
        let url = Url::parse(raw).map_err(|_| invalid_connection())?;
        for part in [url.username(), url.password().unwrap_or_default()] {
            let bytes = part.as_bytes();
            for (index, value) in bytes.iter().enumerate() {
                if *value == b'%'
                    && (index + 2 >= bytes.len()
                        || !bytes[index + 1].is_ascii_hexdigit()
                        || !bytes[index + 2].is_ascii_hexdigit())
                {
                    return Err(invalid_connection());
                }
            }
        }
        let username = percent_decode_str(url.username())
            .decode_utf8()
            .map_err(|_| invalid_connection())?
            .into_owned();
        let password = percent_decode_str(url.password().unwrap_or_default())
            .decode_utf8()
            .map_err(|_| invalid_connection())?
            .into_owned();
        if !url.path().is_empty() && url.path() != "/"
            || url.query().is_some()
            || url.fragment().is_some()
        {
            return Err(invalid_connection());
        }
        Self::from_input(
            &ProxyConnectionInput {
                protocol: url.scheme().into(),
                host: url
                    .host_str()
                    .unwrap_or_default()
                    .trim_matches(['[', ']'])
                    .into(),
                port: url
                    .port()
                    .unwrap_or(if url.scheme() == "http" { 80 } else { 1080 }),
                username: Some(username),
                password: Some(password),
            },
            None,
        )
    }

    /// 为跨服务引用匹配生成私有摘要，公开接口不返回此值。
    /// @return 规范连接字段的SHA256。
    pub fn fingerprint(&self) -> String {
        let fields = serde_json::json!([
            self.protocol,
            self.host,
            self.port,
            self.username,
            self.password
        ]);
        format!("{:x}", Sha256::digest(fields.to_string().as_bytes()))
    }

    /// 完整校验结构化连接，未提供认证字段时保留原值。
    /// @param input 输入字段。
    /// @param previous 原连接。
    /// @return 规范连接与公开摘要。
    pub fn from_input(
        input: &ProxyConnectionInput,
        previous: Option<&Self>,
    ) -> Result<Self, AppError> {
        let host = input.host.trim().trim_matches(['[', ']']);
        if !["http", "socks5", "socks5h"].contains(&input.protocol.as_str())
            || input.port == 0
            || host.is_empty()
            || host.len() > 253
            || host
                .chars()
                .any(|c| c.is_whitespace() || "/@?#".contains(c))
        {
            return Err(invalid_connection());
        }
        let authority = if host.contains(':') {
            format!("[{host}]")
        } else {
            host.into()
        };
        // SOCKS属于URL非特殊协议；先按网络主机规范化大小写、IDNA和IPv6，保证跨服务摘要一致。
        let network = Url::parse(&format!("http://{authority}:{}", input.port))
            .map_err(|_| invalid_connection())?;
        let canonical_host = network.host_str().ok_or_else(invalid_connection)?;
        let mut url = Url::parse(&format!(
            "{}://{}:{}",
            input.protocol, canonical_host, input.port
        ))
        .map_err(|_| invalid_connection())?;
        let username = input
            .username
            .clone()
            .unwrap_or_else(|| previous.map(|p| p.username.clone()).unwrap_or_default());
        let password = input
            .password
            .clone()
            .unwrap_or_else(|| previous.map(|p| p.password.clone()).unwrap_or_default());
        if username.len() > 1024 || password.len() > 4096 {
            return Err(invalid_connection());
        }
        let public_url = url.as_str().trim_end_matches('/').to_string();
        url.set_username(&username)
            .map_err(|_| invalid_connection())?;
        url.set_password(if password.is_empty() {
            None
        } else {
            Some(&password)
        })
        .map_err(|_| invalid_connection())?;
        Ok(Self {
            private_url: url.as_str().trim_end_matches('/').into(),
            public_url,
            protocol: input.protocol.clone(),
            host: url
                .host_str()
                .unwrap_or_default()
                .trim_matches(['[', ']'])
                .into(),
            port: input.port,
            username,
            password,
        })
    }
}

fn invalid_connection() -> AppError {
    AppError::BadRequest("代理类型、主机、端口或认证格式无效".into())
}

/// 仅允许返回经过白名单提取的出口观测。
#[derive(Clone, Default, Serialize, Deserialize)]
pub struct ProxyObservation {
    pub ip: String,
    pub country: Option<String>,
    pub country_code: Option<String>,
    pub region: Option<String>,
    pub city: Option<String>,
    pub latency_ms: u64,
    pub observed_at: String,
}

/// 校验并规范化可选到期时间。
/// @param value RFC3339到期时间或空值。
/// @return UTC时间或未设置。
pub fn expiry(value: Option<&str>) -> Result<Option<String>, AppError> {
    value
        .filter(|s| !s.is_empty())
        .map(|s| {
            DateTime::parse_from_rfc3339(s)
                .map(|time| time.with_timezone(&Utc).to_rfc3339())
                .map_err(|_| AppError::BadRequest("代理到期时间无效".into()))
        })
        .transpose()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn connection_normalizes_auth_and_hides_credentials() {
        let connection = ProxyConnection::parse("socks5h://demo%40user:p%3Ass@[::1]:1080").unwrap();
        assert_eq!(connection.username, "demo@user");
        assert_eq!(connection.password, "p:ss");
        assert_eq!(connection.public_url, "socks5h://[::1]:1080");
        assert_eq!(
            ProxyConnection::parse(&connection.private_url)
                .unwrap()
                .private_url,
            connection.private_url
        );
        assert!(ProxyConnection::parse("ftp://host:80").is_err());
        assert!(ProxyConnection::parse("http://host:80/path").is_err());
        assert!(expiry(Some("invalid")).is_err());
        assert!(ProxyConnection::parse("http://user:%zz@host:80").is_err());
        assert_eq!(
            ProxyConnection::parse("socks5://EXAMPLE.TEST:1080")
                .unwrap()
                .host,
            "example.test"
        );
        assert_eq!(
            ProxyConnection::parse("http://user:secret@proxy.test:8080")
                .unwrap()
                .fingerprint(),
            "77a4708442efc2b5983be2ad91de19293e3029e936ccde3a8dedf8c2fcb1de2f"
        );
    }
}
