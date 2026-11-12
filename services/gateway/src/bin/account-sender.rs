//! 固定账号容器中的 HTTPS 发送进程，沿用网关 crate 的 HTTP/TLS 实现。

use claude_code_gateway::service::runtime_transport::sender_router;
use tracing_subscriber::EnvFilter;

/// 初始化账号发送器日志并提供受限的内部服务。
/// @return 服务停止后结束进程。
#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .json()
        .with_ansi(false)
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .init();
    let path = std::env::var("V3_SENDER_CONFIG").unwrap_or_else(|_| "/run/v3/sender.json".into());
    let address = std::env::var("V3_SENDER_LISTEN").unwrap_or_else(|_| "0.0.0.0:8091".into());
    let listener = tokio::net::TcpListener::bind(&address)
        .await
        .expect("绑定账号内部端口失败");
    tracing::info!(
        layer = "native_sender",
        reason = "sender_started",
        "账号发送器已启动"
    );
    axum::serve(listener, sender_router(path))
        .await
        .expect("账号发送器退出");
}
