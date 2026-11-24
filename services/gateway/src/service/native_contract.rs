//! 原生 sender 的跨平台私有合同；平台执行实现由 native_runtime 选择。

use crate::error::AppError;
use crate::model::request_diagnostics::RequestLogMode;
use crate::service::runtime_transport::PreparedRequest;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs::File;

/// 共享执行映像及 sender 的基础 RAM 份额，包含首次解压余量。
pub const POOL_MEMORY_MIB: u64 = 256;
/// 每个独立进程的堆和缓冲预算；共享代码计入池基础份额。
pub const WORKER_MEMORY_MIB: u64 = 192;

/// 管理端同步的账号级空闲回收策略，独立于进程身份和业务正文。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct NativeIdlePolicy {
    pub account_id: i64,
    pub environment_id: String,
    pub generation: u64,
    pub idle_timeout_secs: u64,
}

/// 核验额外空闲进程的回收秒数。@param seconds 管理端配置值。@return 合法值或参数错误。
pub(crate) fn validate_idle_timeout(seconds: u64) -> Result<u64, AppError> {
    if !(30..=3600).contains(&seconds) {
        return Err(AppError::BadRequest(
            "额外空闲进程回收时间必须是30到3600秒的整数".into(),
        ));
    }
    Ok(seconds)
}

/// 原生源版本的报文与历史诊断标识，缺省为 293。
#[derive(
    Clone, Copy, Debug, Default, Deserialize, Serialize, PartialEq, Eq, Hash, PartialOrd, Ord,
)]
pub enum NativeSourceVersion {
    #[serde(rename = "2.1.280")]
    Cc280,
    #[default]
    #[serde(rename = "2.1.293")]
    Cc293,
}

impl NativeSourceVersion {
    /// 校验私有执行信封中的版本。@return 293 可提交，退役版本在接触进程前拒绝。
    pub(crate) fn require_executable(self) -> Result<(), AppError> {
        if self != Self::Cc293 {
            return Err(AppError::BadRequest("原生执行内核仅支持 2.1.293".into()));
        }
        Ok(())
    }

    /// 判断是否采用历史省略版本合同。@param self 当前源版本。@return 是否为293。
    pub fn is_default(&self) -> bool {
        *self == Self::Cc293
    }
    /// 返回准确的官方源版本。@return 固定版本字符串。
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Cc280 => "2.1.280",
            Self::Cc293 => "2.1.293",
        }
    }
}

/// 编排端为单版冻结的安装路径及历史兼容字段。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativeRuntimeConfig {
    pub binary_path: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub release: Option<NativeReleaseRef>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kernel_generation: Option<String>,
}

/// 兼容历史发行引用；执行身份统一由平台内置清单决定。
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct NativeReleaseRef {
    pub release: String,
    pub launcher_sha256: String,
}

/// 部署侧冻结的原生池配置；预算必须与 sender 的 cgroup 上限一致。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativeSenderConfig {
    #[serde(default, skip_serializing_if = "NativeSourceVersion::is_default")]
    pub source_version: NativeSourceVersion,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub runtimes: BTreeMap<NativeSourceVersion, NativeRuntimeConfig>,
    pub binary_path: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub release: Option<NativeReleaseRef>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kernel_generation: Option<String>,
    pub work_root: String,
    /// 显式零表示账号无限内存，正数记录 sender 的实际有限额度。
    pub memory_mib: u64,
    pub max_workers: usize,
}

/// 受信任网关冻结的原始请求及当前授权；此类型禁止派生 Debug。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativeSubmission {
    #[serde(default, skip_serializing_if = "NativeSourceVersion::is_default")]
    pub source_version: NativeSourceVersion,
    /// 网关按本次全局设置冻结的已有缓存TTL策略；省略表示 off。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cache_ttl_rewrite: Option<String>,
    /// 受信任网关冻结的消息断点策略，preserve或sub2api；省略沿用保留布局。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub message_cache_policy: Option<String>,
    /// 网关在映射前冻结的有界脱敏入口预览；缺失表示本次未采集。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ingress_capture: Option<Value>,
    /// 仅由受信任网关冻结，不从调用方信封读取。
    #[serde(default)]
    pub log_mode: RequestLogMode,
    pub request: PreparedRequest,
    pub input: Value,
    pub bearer: String,
    pub device_id: String,
    pub account_uuid: Option<String>,
    pub organization_uuid: Option<String>,
    pub email: String,
    pub concurrency: i32,
}

/// 零模型准备的账号身份与绑定；秘密仅在受鉴权私有接口传递。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativePreparation {
    #[serde(default, skip_serializing_if = "NativeSourceVersion::is_default")]
    pub source_version: NativeSourceVersion,
    pub account_id: i64,
    pub environment_id: String,
    pub generation: u64,
    pub preparation_id: String,
    pub deadline_unix_ms: u64,
    pub bearer: String,
    pub device_id: String,
    pub account_uuid: Option<String>,
    pub organization_uuid: Option<String>,
    pub email: String,
    pub concurrency: i32,
}

/// 取消操作只携带准备归属，不能取消其它代次或业务请求。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativePreparationControl {
    #[serde(default, skip_serializing_if = "NativeSourceVersion::is_default")]
    pub source_version: NativeSourceVersion,
    pub account_id: i64,
    pub environment_id: String,
    pub generation: u64,
    pub preparation_id: String,
}

/// 实际进程握手后的准备结果；busy 表示当前业务持有全部暖进程。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativePreparationStatus {
    pub state: String,
    pub account_id: i64,
    pub environment_id: String,
    pub generation: u64,
    pub preparation_id: String,
    pub version: String,
    pub raw_input_protocol: u32,
    pub pid: Option<u32>,
    pub idle_workers: usize,
    pub reused: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub release: Option<NativeReleaseRef>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub kernel_generation: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub image_sha256: Option<String>,
}

/// 当前身份对应的实时池状态；只携带安全观测，不启动模型作业。
#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NativeReadinessStatus {
    #[serde(default, skip_serializing_if = "NativeSourceVersion::is_default")]
    pub source_version: NativeSourceVersion,
    pub state: String,
    pub account_id: i64,
    pub environment_id: String,
    pub generation: u64,
    pub kernel_generation: Option<String>,
    pub release: Option<NativeReleaseRef>,
    pub checked_at_ms: u64,
    pub idle_workers: usize,
    pub live_workers: usize,
    pub pid: Option<u32>,
    pub reason: Option<String>,
    /// 当前环境的实际TLS槽；旧发送器缺字段时保留兼容。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tls_observer: Option<serde_json::Value>,
    /// 同代恢复模板的真实状态；旧发送器省略时协调器显示未知。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub restore: Option<Value>,
}

impl NativeSenderConfig {
    /// 校验当前平台、资源模式及已登记分发体。
    /// @return 保持打开的精确执行文件，或明确的准备错误。
    pub fn verify(&self) -> Result<File, AppError> {
        super::native_runtime::verify_distribution(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// 293历史合同保持原报文，280显式携带版本，未知值拒绝。@return 无。
    #[test]
    fn native_source_version_preserves_legacy_wire_contract() {
        let original = json!({"binary_path":"/usr/local/bin/ccrb-runtime","work_root":"/native",
            "memory_mib":0,"max_workers":6});
        let mut config: NativeSenderConfig = serde_json::from_value(original.clone()).unwrap();
        assert_eq!(config.source_version, NativeSourceVersion::Cc293);
        assert_eq!(serde_json::to_value(&config).unwrap(), original);
        config.source_version = NativeSourceVersion::Cc280;
        assert_eq!(
            serde_json::to_value(&config).unwrap()["source_version"],
            "2.1.280"
        );
        assert!(serde_json::from_value::<NativeSourceVersion>(json!("2.1.281")).is_err());
    }
}
