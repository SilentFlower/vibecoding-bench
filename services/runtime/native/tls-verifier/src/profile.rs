//! 固定原版 2.1.293 的公开握手画像与真实混合密钥交换实现。

use ml_kem::kem::{Decapsulate, DecapsulationKey};
use ml_kem::{EncodedSizeUser, KemCore, MlKem768, MlKem768Params};
use rand::thread_rng;
use rustls::client::Resumption;
use rustls::craft::{
    CraftExtension, ExtensionSpec, Fingerprint, GreaseOrCipher, GreaseOrCurve, GreaseOrVersion,
    KeepExtension, OCSP_REQ,
};
use rustls::crypto::{ActiveKeyExchange, SharedSecret, SupportedKxGroup};
use rustls::internal::msgs::base::Payload;
use rustls::internal::msgs::enums::{ECPointFormat, ExtensionType, PSKKeyExchangeMode};
use rustls::internal::msgs::handshake::{ClientExtension, ClientSessionTicket};
use rustls::{
    CipherSuite, ClientConfig, Error, NamedGroup, ProtocolVersion, RootCertStore, SignatureScheme,
};
use static_init::dynamic;
use std::fmt::{Debug, Formatter, Result as FmtResult};
use std::sync::Arc;
use x25519_dalek::{PublicKey, StaticSecret};
use zeroize::Zeroizing;

/// 已独立对照的模型传输画像标识，不能按请求改成其他版本。
pub const PROFILE_ID: &str = "claude-code-2.1.293";
const HYBRID_GROUP: NamedGroup = NamedGroup::Unknown(0x11ec);

#[derive(Debug)]
struct HybridGroup;

struct HybridExchange {
    decapsulation: DecapsulationKey<MlKem768Params>,
    x25519: StaticSecret,
    public: Vec<u8>,
}

impl Debug for HybridExchange {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> FmtResult {
        formatter.write_str("HybridExchange")
    }
}

impl SupportedKxGroup for HybridGroup {
    fn start(&self) -> Result<Box<dyn ActiveKeyExchange>, Error> {
        let mut random = thread_rng();
        let (decapsulation, encapsulation) = MlKem768::generate(&mut random);
        let x25519 = StaticSecret::random_from_rng(&mut random);
        let mut public = encapsulation.as_bytes().to_vec();
        public.extend_from_slice(PublicKey::from(&x25519).as_bytes());
        Ok(Box::new(HybridExchange {
            decapsulation,
            x25519,
            public,
        }))
    }

    fn name(&self) -> NamedGroup {
        HYBRID_GROUP
    }
}

impl ActiveKeyExchange for HybridExchange {
    fn complete(self: Box<Self>, peer: &[u8]) -> Result<SharedSecret, Error> {
        if peer.len() != 1120 {
            return Err(Error::General("混合密钥响应长度不合法".into()));
        }
        let ciphertext = peer[..1088]
            .try_into()
            .map_err(|_| Error::General("ML-KEM 密文不合法".into()))?;
        let mut secret = Zeroizing::new(
            self.decapsulation
                .decapsulate(&ciphertext)
                .map_err(|_| Error::General("ML-KEM 交换失败".into()))?
                .to_vec(),
        );
        let public: [u8; 32] = peer[1088..]
            .try_into()
            .map_err(|_| Error::General("X25519 公钥不合法".into()))?;
        let x25519 = self.x25519.diffie_hellman(&PublicKey::from(public));
        // 混合算法仍须拒绝低阶 X25519 输入，不能让另一半秘密掩盖无效交换。
        if !x25519.was_contributory() {
            return Err(Error::General("X25519 交换无效".into()));
        }
        secret.extend_from_slice(x25519.as_bytes());
        Ok(SharedSecret::from(secret.as_slice()))
    }

    fn pub_key(&self) -> &[u8] {
        &self.public
    }
    fn group(&self) -> NamedGroup {
        HYBRID_GROUP
    }
}

static HYBRID: HybridGroup = HybridGroup;
static KEY_SHARES: &[GreaseOrCurve] = &[
    GreaseOrCurve::T(HYBRID_GROUP),
    GreaseOrCurve::T(NamedGroup::X25519),
];
static VERSIONS: &[GreaseOrVersion] = &[
    GreaseOrVersion::T(ProtocolVersion::TLSv1_3),
    GreaseOrVersion::T(ProtocolVersion::TLSv1_2),
];

#[dynamic]
static CIPHERS: Vec<GreaseOrCipher> = [
    4865, 4866, 4867, 49195, 49199, 49196, 49200, 52393, 52392, 49161, 49171, 49162, 49172, 156,
    157, 47, 53,
]
.into_iter()
.map(|value| GreaseOrCipher::T(CipherSuite::from(value)))
.collect();

#[dynamic]
static EXTENSIONS: Vec<ExtensionSpec> = vec![
    ExtensionSpec::Keep(KeepExtension::Must(ExtensionType::ServerName)),
    ExtensionSpec::Rustls(ClientExtension::ExtendedMasterSecretRequest),
    ExtensionSpec::Craft(CraftExtension::RenegotiationInfo),
    ExtensionSpec::Rustls(ClientExtension::NamedGroups(vec![
        HYBRID_GROUP,
        NamedGroup::X25519,
        NamedGroup::secp256r1,
        NamedGroup::secp384r1,
    ])),
    ExtensionSpec::Rustls(ClientExtension::EcPointFormats(vec![
        ECPointFormat::Uncompressed,
    ])),
    ExtensionSpec::Keep(KeepExtension::OrDefault(
        ExtensionType::SessionTicket,
        ClientExtension::SessionTicket(ClientSessionTicket::Offer(Payload(vec![]))),
    )),
    ExtensionSpec::Craft(CraftExtension::Protocols(&[b"http/1.1"])),
    ExtensionSpec::Rustls(ClientExtension::CertificateStatusRequest(OCSP_REQ.clone())),
    ExtensionSpec::Rustls(ClientExtension::SignatureAlgorithms(
        [1027, 2052, 1025, 1283, 2053, 1281, 2054, 1537, 513]
            .into_iter()
            .map(SignatureScheme::from)
            .collect(),
    )),
    ExtensionSpec::Craft(CraftExtension::SignedCertificateTimestamp),
    ExtensionSpec::Craft(CraftExtension::KeyShare(KEY_SHARES)),
    ExtensionSpec::Rustls(ClientExtension::PresharedKeyModes(vec![
        PSKKeyExchangeMode::PSK_DHE_KE,
    ])),
    ExtensionSpec::Craft(CraftExtension::SupportedVersions(VERSIONS)),
    ExtensionSpec::Keep(KeepExtension::Optional(ExtensionType::Cookie)),
    ExtensionSpec::Keep(KeepExtension::Optional(ExtensionType::PreSharedKey)),
];

#[dynamic]
static FINGERPRINT: Fingerprint = Fingerprint {
    extensions: &EXTENSIONS,
    cipher: &CIPHERS,
    shuffle_extensions: false,
};

/// 构造固定画像客户端，保留证书校验和真实密码学交换。
/// @param roots 经过启动配置选定的信任根。
/// @return 不额外启用会话恢复的已验证画像配置。
pub fn client_config(roots: RootCertStore) -> ClientConfig {
    let mut config = ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth()
        .with_fingerprint(FINGERPRINT.builder());
    let mut provider = config.provider.as_ref().clone();
    provider.kx_groups.insert(0, &HYBRID);
    provider.kx_groups.retain(|group| {
        matches!(
            group.name(),
            HYBRID_GROUP | NamedGroup::X25519 | NamedGroup::secp256r1 | NamedGroup::secp384r1
        )
    });
    config.provider = Arc::new(provider);
    config.resumption = Resumption::disabled();
    config
}

#[cfg(test)]
mod tests {
    use super::HYBRID;
    use ml_kem::kem::{Encapsulate, EncapsulationKey};
    use ml_kem::{EncodedSizeUser, MlKem768Params};
    use rand::thread_rng;
    use rustls::crypto::SupportedKxGroup;
    use x25519_dalek::{PublicKey, StaticSecret};

    #[test]
    fn hybrid_exchange_derives_both_real_shared_secrets() {
        let client = HYBRID.start().unwrap();
        let offered = client.pub_key();
        assert_eq!(offered.len(), 1216);
        let key =
            EncapsulationKey::<MlKem768Params>::from_bytes(&offered[..1184].try_into().unwrap());
        let (ciphertext, kem_secret) = key.encapsulate(&mut thread_rng()).unwrap();
        let server = StaticSecret::random_from_rng(thread_rng());
        let client_public: [u8; 32] = offered[1184..].try_into().unwrap();
        let x_secret = server.diffie_hellman(&PublicKey::from(client_public));
        let mut peer = ciphertext.to_vec();
        peer.extend_from_slice(PublicKey::from(&server).as_bytes());
        let mut expected = kem_secret.to_vec();
        expected.extend_from_slice(x_secret.as_bytes());
        let shared = client.complete(&peer).unwrap();
        assert_eq!(shared.secret_bytes(), expected);
    }

    #[test]
    fn hybrid_exchange_rejects_invalid_lengths_and_low_order_x25519() {
        assert!(HYBRID.start().unwrap().complete(&[0; 1119]).is_err());
        assert!(HYBRID.start().unwrap().complete(&[0; 1120]).is_err());
    }
}
