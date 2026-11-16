//! 按固定官方源版本核验签署制品；路径来自只读发布目录。

use crate::error::AppError;
use crate::service::native_contract::{NativeReleaseRef, NativeSourceVersion};
use ring::signature::{ED25519, UnparsedPublicKey};
use serde::Deserialize;
use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};

pub(super) const ROOT: &str = "/runtime-releases";
const ASSET: &str = "ccrb-runtime-linux-x64";
const SOURCE: &str = "8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978";

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema_version: u8,
    release: String,
    platform: String,
    asset: String,
    source_version: String,
    source_sha256: String,
    launcher_sha256: String,
    launcher_bytes: u64,
    image_sha256: String,
    image_bytes: u64,
    worker_schema: u8,
    raw_input_protocol: u8,
    resource_contract: u8,
}

/// 已核验清单提供的精确文件与执行体合同。
pub(super) struct ReleaseArtifact {
    pub path: PathBuf,
    pub launcher_sha256: String,
    pub launcher_bytes: u64,
    pub image_sha256: String,
    pub image_bytes: u64,
}

fn invalid() -> AppError {
    AppError::ServiceUnavailable("原生内核发布身份核验失败".into())
}

fn read_capped(path: &Path, limit: u64) -> Result<Vec<u8>, AppError> {
    let mut bytes = Vec::new();
    File::open(path)
        .and_then(|file| file.take(limit + 1).read_to_end(&mut bytes))
        .map_err(|_| invalid())?;
    if bytes.len() as u64 > limit {
        return Err(invalid());
    }
    Ok(bytes)
}

fn is_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn load(
    root: &Path,
    key: &[u8],
    reference: &NativeReleaseRef,
    version: NativeSourceVersion,
) -> Result<ReleaseArtifact, AppError> {
    let tag = reference
        .release
        .strip_prefix("v0.1.0-beta.")
        .ok_or_else(invalid)?;
    if tag.is_empty()
        || tag.len() > 9
        || tag.starts_with('0')
        || !tag.bytes().all(|b| b.is_ascii_digit())
        || !is_digest(&reference.launcher_sha256)
    {
        return Err(invalid());
    }
    let dir = root
        .join(&reference.release)
        .join(&reference.launcher_sha256);
    let bytes = read_capped(&dir.join("runtime-release.json"), 4096)?;
    let signature = read_capped(&dir.join("runtime-release.sig"), 64)?;
    UnparsedPublicKey::new(&ED25519, key)
        .verify(&bytes, &signature)
        .map_err(|_| invalid())?;
    let manifest: Manifest = serde_json::from_slice(&bytes).map_err(|_| invalid())?;
    if manifest.schema_version != 1
        || manifest.release != reference.release
        || manifest.platform != "linux-x64"
        || manifest.asset != ASSET
        || manifest.source_version != version.as_str()
        || manifest.source_sha256
            != match version {
                NativeSourceVersion::Cc293 => SOURCE,
                NativeSourceVersion::Cc280 => {
                    "1e08503dbdf3c2cb0d706d32f3408277388d1c76ef108673e8fe42c1b322925b"
                }
            }
        || manifest.launcher_sha256 != reference.launcher_sha256
        || !(1..=27_933_052).contains(&manifest.launcher_bytes)
        || !is_digest(&manifest.image_sha256)
        || !(1..=134_217_728).contains(&manifest.image_bytes)
        || manifest.worker_schema != 2
        || manifest.raw_input_protocol != 1
        || manifest.resource_contract != 1
    {
        return Err(invalid());
    }
    Ok(ReleaseArtifact {
        path: dir.join(ASSET),
        launcher_sha256: manifest.launcher_sha256,
        launcher_bytes: manifest.launcher_bytes,
        image_sha256: manifest.image_sha256,
        image_bytes: manifest.image_bytes,
    })
}

impl ReleaseArtifact {
    /// 从独立部署信任根解析只读发布制品。
    /// @param reference 已冻结的发布标签和分发摘要。
    /// @param version 本次选定的官方源版本。
    /// @return 通过签名和协议准入的制品身份。
    pub(super) fn signed(
        reference: &NativeReleaseRef,
        version: NativeSourceVersion,
    ) -> Result<Self, AppError> {
        let key = std::env::var("V3_NATIVE_RELEASE_PUBLIC_KEY")
            .ok()
            .and_then(|value| hex::decode(value).ok())
            .filter(|value| value.len() == 32)
            .ok_or_else(invalid)?;
        #[cfg(test)]
        if let Ok(directory) = std::env::var("CCRB_TEST_RELEASE_ROOT") {
            return load(Path::new(&directory), &key, reference, version);
        }
        load(Path::new(ROOT), &key, reference, version)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ring::rand::SystemRandom;
    use ring::signature::{Ed25519KeyPair, KeyPair};
    use serde_json::json;
    use std::fs;
    use uuid::Uuid;

    /// 真实验签按目标源版本准入，签名与版本错配在读取执行文件前拒绝。@return 无。
    #[test]
    fn native_signed_release_binds_each_source_version() {
        let root = std::env::temp_dir().join(format!("native-release-{}", Uuid::new_v4()));
        let key = Ed25519KeyPair::from_pkcs8(
            Ed25519KeyPair::generate_pkcs8(&SystemRandom::new())
                .unwrap()
                .as_ref(),
        )
        .unwrap();
        let reference = NativeReleaseRef {
            release: "v0.1.0-beta.99".into(),
            launcher_sha256: "a".repeat(64),
        };
        let directory = root
            .join(&reference.release)
            .join(&reference.launcher_sha256);
        fs::create_dir_all(&directory).unwrap();
        for (version, source, other) in [
            (
                NativeSourceVersion::Cc280,
                "1e08503dbdf3c2cb0d706d32f3408277388d1c76ef108673e8fe42c1b322925b",
                NativeSourceVersion::Cc293,
            ),
            (
                NativeSourceVersion::Cc293,
                SOURCE,
                NativeSourceVersion::Cc280,
            ),
        ] {
            let bytes = serde_json::to_vec(&json!({"schema_version":1,"release":reference.release,
                "platform":"linux-x64","asset":ASSET,"source_version":version.as_str(),"source_sha256":source,
                "launcher_sha256":reference.launcher_sha256,"launcher_bytes":1,"image_sha256":"b".repeat(64),
                "image_bytes":1,"worker_schema":2,"raw_input_protocol":1,"resource_contract":1})).unwrap();
            fs::write(directory.join("runtime-release.json"), &bytes).unwrap();
            fs::write(
                directory.join("runtime-release.sig"),
                key.sign(&bytes).as_ref(),
            )
            .unwrap();
            assert!(load(&root, key.public_key().as_ref(), &reference, version).is_ok());
            assert!(load(&root, key.public_key().as_ref(), &reference, other).is_err());
            fs::write(directory.join("runtime-release.sig"), [0_u8; 64]).unwrap();
            assert!(load(&root, key.public_key().as_ref(), &reference, version).is_err());
        }
        fs::remove_dir_all(root).unwrap();
    }
}
