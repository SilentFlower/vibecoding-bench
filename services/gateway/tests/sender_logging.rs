//! 真实发送器入口的日志回归，使用空配置及本机随机端口。

use serde_json::Value;
use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

struct SenderProcess(Child);

impl Drop for SenderProcess {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

#[test]
fn real_sender_entry_writes_default_json_log_and_honors_filter() {
    for filter in [None, Some("warn")] {
        let mut command = Command::new(env!("CARGO_BIN_EXE_account-sender"));
        command
            .env_clear()
            .env("V3_SENDER_LISTEN", "127.0.0.1:0")
            .env(
                "V3_SENDER_CONFIG",
                "/nonexistent/synthetic-secret-config.json",
            )
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some(filter) = filter {
            command.env("RUST_LOG", filter);
        }
        let mut process = SenderProcess(command.spawn().unwrap());
        let output = process.0.stdout.take().unwrap();
        let (send, receive) = mpsc::channel();
        let reader = thread::spawn(move || {
            for line in BufReader::new(output).lines() {
                if send.send(line.unwrap()).is_err() {
                    break;
                }
            }
        });
        if filter.is_none() {
            let line = receive
                .recv_timeout(Duration::from_secs(10))
                .expect("发送器缺少默认启动日志");
            let event: Value = serde_json::from_str(&line).expect("发送器日志不是 JSON");
            assert_eq!(event["level"], "INFO");
            assert_eq!(event["fields"]["reason"], "sender_started");
            assert!(!line.contains("synthetic-secret-config"));
            assert!(!line.contains('\u{1b}'));
        } else {
            assert!(receive.recv_timeout(Duration::from_millis(300)).is_err());
            assert!(process.0.try_wait().unwrap().is_none());
        }
        drop(process);
        reader.join().unwrap();
    }
}
