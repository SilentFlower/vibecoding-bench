//! 平台镜像内置制品的固定执行合同。

use std::path::PathBuf;

/// 内置程序的精确分发与执行映像身份。
pub(super) struct ReleaseArtifact {
    pub path: PathBuf,
    pub launcher_sha256: String,
    pub launcher_bytes: u64,
    pub image_sha256: String,
    pub image_bytes: u64,
}
