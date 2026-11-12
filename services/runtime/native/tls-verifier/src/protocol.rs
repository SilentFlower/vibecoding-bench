//! 私有 JSONL 合同；业务 HTTP 不能提供这些控制字段。

use serde::{Deserialize, Serialize};

/// 启动侧冻结的上游 HTTP CONNECT 代理。
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Proxy {
    pub host: String,
    pub port: u16,
    pub authorization: Option<String>,
}

/// 私有监听、证书、目标和观测上限。
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Setup {
    pub target_host: String,
    pub target_port: u16,
    pub authority: String,
    pub host_header: String,
    pub certificate_file: String,
    pub key_file: String,
    pub ca_file: Option<String>,
    pub proxy: Option<Proxy>,
    pub authorization: String,
    pub capture_bytes: usize,
}

/// 一轮作业与实际物理进程的归属。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub request_id: String,
    pub worker_id: String,
    pub worker_pid: u32,
}

/// 原版已准备正文的长度、哈希及唯一原生 CCH 槽位。
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Expected {
    pub request_id: String,
    pub body_bytes: usize,
    pub body_sha256: String,
    pub cch_offset: Option<usize>,
    pub headers: Vec<(String, String)>,
}

/// 控制操作；不包含业务正文或上游账号的替换指令。
#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operation {
    Init {
        config: Setup,
    },
    Begin {
        binding: Binding,
    },
    Expected {
        expected: Expected,
    },
    Finish {
        request_id: String,
        close_connections: bool,
    },
    Shutdown,
}

/// 控制帧封套。
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Command {
    pub schema_version: u8,
    pub instance_id: String,
    pub command_id: u64,
    pub operation: Operation,
}

/// 只统计成功交给最后 TLS 写入器的字节，完整性与刷出分开。
#[derive(Serialize)]
pub struct Capture {
    pub binding: Binding,
    pub connection_id: u64,
    pub sequence: u64,
    pub body_preview_b64: String,
    pub head_b64: String,
    pub headers: Vec<(String, String)>,
    pub body_bytes: usize,
    pub body_sha256: String,
    pub normalized_sha256: String,
    pub http_bytes: usize,
    pub http_sha256: String,
    pub complete: bool,
    pub flushed: bool,
    pub verified: bool,
    pub captured_unix_ms: u64,
    pub reason: String,
}

/// 辅助程序输出；错误原因仅允许固定代码，不携带凭据或 URL。
#[derive(Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum Event {
    Ready {
        command_id: u64,
        profile: &'static str,
        pid: u32,
        port: u16,
    },
    Ack {
        command_id: u64,
        error: Option<&'static str>,
    },
    Capture {
        capture: Capture,
    },
    Failure {
        binding: Option<Binding>,
        reason: &'static str,
    },
}
