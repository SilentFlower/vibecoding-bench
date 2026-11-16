//! 代理目录并发边界与有界出口探测。
use std::net::IpAddr;
use std::sync::Arc;
use std::sync::atomic::AtomicBool;
use std::time::{Duration, Instant};

use chrono::Utc;
use reqwest::{Proxy, redirect::Policy};
use serde_json::Value;
use sqlx::AnyPool;
use tokio::sync::{Mutex, Semaphore};

use crate::error::AppError;
use crate::model::proxy::ProxyObservation;
use crate::service::task_proxy_ticket::TaskProxyTickets;
use crate::store::proxy_store::{ProxyRecord, ProxyStore};
use crate::tlsfp::make_request_client_builder;

/// 目录写入与账号选线共用配置锁；探测拥有独立并发限制。
pub struct ProxyService {
    pub store: ProxyStore,
    pub mutations: Arc<Mutex<()>>,
    pub(crate) task_selections: TaskProxyTickets,
    pub(crate) sync_running: AtomicBool,
    probes: Semaphore,
}

impl ProxyService {
    /// 创建目录服务。@param pool 管理数据库池。@return 服务实例。
    pub fn new(pool: AnyPool) -> Self {
        Self {
            store: ProxyStore::new(pool),
            mutations: Arc::new(Mutex::new(())),
            task_selections: TaskProxyTickets::default(),
            sync_running: AtomicBool::new(false),
            probes: Semaphore::new(4),
        }
    }

    /// 经指定线路访问固定观测端点，失败保留历史观测。
    /// @param record 探测开始时的连接版本。
    /// @return 当前记录；迟到探测不覆盖编辑后的配置。
    pub async fn probe(&self, record: &ProxyRecord) -> Result<ProxyRecord, AppError> {
        let _permit = self
            .probes
            .try_acquire()
            .map_err(|_| AppError::TooManyRequests("正在检测其他线路，请稍后重试".into()))?;
        let observation = tokio::time::timeout(Duration::from_secs(10), observe(record))
            .await
            .ok()
            .and_then(Result::ok);
        self.store.observe(record, observation.as_ref()).await?;
        self.store.get(&record.id).await
    }
}

async fn observe(record: &ProxyRecord) -> Result<ProxyObservation, ()> {
    // craftls 在握手时要求指纹配置；复用统一 TLS 工厂并保留探测自身的超时边界。
    let client = make_request_client_builder()
        .redirect(Policy::none())
        .proxy(Proxy::all(&record.connection.private_url).map_err(|_| ())?)
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(8))
        .build()
        .map_err(|_| ())?;
    let start = Instant::now();
    let mut response = client
        .get("https://ipwho.is/?fields=success,ip,country,country_code,region,city")
        .send()
        .await
        .map_err(|_| ())?
        .error_for_status()
        .map_err(|_| ())?;
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| ())? {
        if bytes.len() + chunk.len() > 65536 {
            return Err(());
        }
        bytes.extend_from_slice(&chunk);
    }
    decode_observation(&bytes, start.elapsed().as_millis() as u64)
}

fn decode_observation(bytes: &[u8], latency_ms: u64) -> Result<ProxyObservation, ()> {
    let value: Value = serde_json::from_slice(bytes).map_err(|_| ())?;
    let ip = value["ip"]
        .as_str()
        .ok_or(())?
        .parse::<IpAddr>()
        .map_err(|_| ())?;
    if value["success"] != true {
        return Err(());
    }
    let field = |key: &str| {
        value[key]
            .as_str()
            .filter(|s| !s.is_empty() && s.len() <= 256 && !s.chars().any(char::is_control))
            .map(str::to_owned)
    };
    Ok(ProxyObservation {
        ip: ip.to_string(),
        country: field("country"),
        country_code: field("country_code"),
        region: field("region"),
        city: field("city"),
        latency_ms,
        observed_at: Utc::now().to_rfc3339(),
    })
}

#[cfg(test)]
mod tests {
    use super::{ProxyService, decode_observation};
    use crate::model::proxy::ProxyConnection;
    use crate::store::database_migrations;
    use sqlx::any::{AnyPoolOptions, install_default_drivers};
    use std::time::Duration;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    use tokio::net::TcpListener;
    use tokio::time::timeout;
    use uuid::Uuid;

    /// 真实 CONNECT 后发出 TLS 握手；断连按检测失败保存，并保留历史观测。
    #[tokio::test]
    async fn probe_sends_tls_clienthello_and_records_connection_failure() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let proxy = tokio::spawn(async move {
            timeout(Duration::from_secs(10), async {
                let (mut stream, _) = listener.accept().await.unwrap();
                let mut request = Vec::new();
                while !request.ends_with(b"\r\n\r\n") {
                    assert!(request.len() < 8192);
                    request.push(stream.read_u8().await.unwrap());
                }
                let request = String::from_utf8(request).unwrap();
                assert!(request.starts_with("CONNECT ipwho.is:443 HTTP/1.1\r\n"));
                assert!(
                    request
                        .to_ascii_lowercase()
                        .contains("proxy-authorization: basic ")
                );
                stream
                    .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    .await
                    .unwrap();

                // 只在本地观察 ClientHello，随后模拟连接中断，避免访问真实观测服务。
                let mut header = [0; 5];
                stream.read_exact(&mut header).await.unwrap();
                assert_eq!(header[0], 22);
                let mut body = vec![0; usize::from(u16::from_be_bytes([header[3], header[4]]))];
                stream.read_exact(&mut body).await.unwrap();
                assert_eq!(body[0], 1);
            })
            .await
            .unwrap();
        });

        install_default_drivers();
        let pool = AnyPoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        database_migrations::apply(&pool, &Uuid::new_v4().to_string(), None)
            .await
            .unwrap();
        let service = ProxyService::new(pool);
        let connection =
            ProxyConnection::parse(&format!("http://fixture:password@{address}")).unwrap();
        let id = service
            .store
            .insert_many(&[("测试线路".into(), connection, None)])
            .await
            .unwrap()
            .remove(0);
        let record = service.store.get(&id).await.unwrap();
        let previous = decode_observation(br#"{"success":true,"ip":"203.0.113.1"}"#, 42).unwrap();
        service
            .store
            .observe(&record, Some(&previous))
            .await
            .unwrap();

        let result = service.probe(&record).await.unwrap();
        proxy.await.unwrap();
        assert_eq!(result.status, "failed");
        assert!(result.checked_at.is_some());
        let observed = result.observation.unwrap();
        assert_eq!(observed.ip, previous.ip);
        assert_eq!(observed.observed_at, previous.observed_at);
    }

    #[test]
    fn probe_accepts_only_observed_ip_and_whitelisted_fields() {
        let observed = decode_observation(
            br#"{"success":true,"ip":"203.0.113.1","country":"Test","secret":"hidden"}"#,
            42,
        )
        .unwrap();
        assert_eq!(observed.latency_ms, 42);
        assert_eq!(observed.region, None);
        assert!(!serde_json::to_string(&observed).unwrap().contains("hidden"));
        assert!(decode_observation(br#"{"success":false,"ip":"203.0.113.1"}"#, 1).is_err());
        assert!(decode_observation(br#"{"success":true,"ip":"host"}"#, 1).is_err());
    }
}
