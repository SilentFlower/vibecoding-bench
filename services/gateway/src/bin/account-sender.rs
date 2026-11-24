//! 固定账号容器中的 HTTPS 发送进程，沿用网关 crate 的 HTTP/TLS 实现。

use claude_code_gateway::service::runtime_transport::serve_sender;
use tracing_subscriber::EnvFilter;

#[cfg(target_os = "linux")]
async fn supervise_tui_source(config: String, mut stop: tokio::sync::oneshot::Receiver<()>) {
    use std::process::Stdio;
    use std::time::Duration;
    use tokio::process::Command;
    use tokio::time::{Instant, sleep};

    let mut delay = Duration::from_secs(1);
    loop {
        let started = Instant::now();
        let child = Command::new("/usr/local/bin/python3")
            .args(["-I", "/opt/flower/tui/tui_source.py", &config])
            .stdin(Stdio::null())
            .kill_on_drop(true)
            .spawn();
        match child {
            Ok(mut child) => {
                tokio::select! {
                    _ = &mut stop => {
                        if let Some(pid) = child.id() {
                            // 先让源释放正在监管的 TUI，再遵循账号容器现有的停止预算。
                            unsafe { libc::kill(pid as i32, libc::SIGTERM); }
                        }
                        if tokio::time::timeout(Duration::from_secs(5), child.wait()).await.is_err() {
                            let _ = child.kill().await;
                        }
                        return;
                    }
                    status = child.wait() => tracing::warn!(?status, "账号 TUI 事件源已退出"),
                }
            }
            Err(error) => tracing::warn!(%error, "账号 TUI 事件源启动失败"),
        }
        if started.elapsed() >= delay {
            delay = Duration::from_secs(1);
        }
        tokio::select! {
            _ = &mut stop => return,
            _ = sleep(delay) => {}
        }
        delay = (delay * 2).min(Duration::from_secs(30));
    }
}

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
    #[cfg(target_os = "linux")]
    let source = (std::env::var("V3_TUI_SESSION_HOST").as_deref() == Ok("1")).then(|| {
        let (stop, receiver) = tokio::sync::oneshot::channel();
        (
            stop,
            tokio::spawn(supervise_tui_source(path.clone(), receiver)),
        )
    });
    let result = serve_sender(listener, path).await;
    #[cfg(target_os = "linux")]
    if let Some((stop, task)) = source {
        let _ = stop.send(());
        let _ = task.await;
    }
    result.expect("账号发送器退出");
}
