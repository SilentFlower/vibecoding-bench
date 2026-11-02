# 原生293 TLS对齐依据

## 已验证事实

- 正式采集方向为原生CLI到Recorder。六代执行58条具HTTP关联的293握手，主messages新连接JA3为`1523504b38f0fae0d881d4b6554aac1b`，恢复连接为`ae5f2d34331c18f27df379f7d4b72e35`；后者在末尾多真实PSK扩展41。公开向量和原始本体摘要见native-fingerprint-summary.json。
- 原版二进制实际`2.1.293 (Claude Code)`，SHA256为`8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978`。空HOME、network=none、合成API key、回环纯TCP监听取得首个ClientHello，无MITM；主要向量和JA3完全一致。只在SNI与对应长度上按localhost变化。没有真实模型调用或挂载账号HOME。见native-loopback-verification.json。
- 部分辅助调用为无ALPN、18项cipher和窄扩展的另两种JA3；这是证据事实，本轮不新增按端点／版本选模。现有工厂统一TLS模板，本轮目标为主请求；不把辅助或280/303标为已对齐。

## 当前代码差异与边界

- `cc2api/src/tlsfp/tlsfp.rs`的旧NODEJS_CIPHER为52项、旧NODEJS_EXTENSION为12项，签名26项、点格式3项、groups8项，均不同于原生主请求；ALPN的http/1.1和supported_versions772/771已匹配。
- Provider已实现真实混合组4588、client1216／server1120／secret64字节，但旧fake X448只会返回错误；去除未观察组后Provider保持真实可用集合。混合X25519现有代码未拒绝全零秘密，需要在实际启用/验证混合组时补齐协议校验。
- `build_tls_config_with_roots`是生产与测试共同入口，`request_client_builder`保留证书验证、30s建连、TCP保活、无整体长流超时。缓存仅按代理URL且可全局关闭，代理解析错误传播不直连。
- 所有主gateway、v3 account-sender的`send_direct`、OAuth、Session Hello、telemetry均调用同一工厂；本轮保持接口与调用点，不改HTTP画像／账号版本。
- craftls `client/tls13.rs::initial_key_share`优先缓存上次kx_hint，`CraftExtension::KeyShare`又优先消费非首组origin，导致后续连接偏离显式模板。仅显式覆盖key_share时先选模板首个真实组；无覆盖保留原hint，HRR仍沿显式服务端组重试。
- craftls在计算binder前patch扩展，必须把Optional PreSharedKey放到最后；Optional Cookie保留真实HRR数据。不得伪造PSK／binder或删除已有恢复状态。

## 标准与验证

- RFC10024 §4：X25519MLKEM768的client为ML-KEM公钥后接X25519，server为ciphertext后接X25519，secret为ML-KEM秘密后接X25519；拒绝全零X25519。https://datatracker.ietf.org/doc/html/rfc10024#section-4
- RFC9846 TLS1.3：PSK扩展最后、服务端真实ticket及binder、HRR单一要求组、证书与主机名验证。https://datatracker.ietf.org/doc/html/rfc9846
- 独立wire parser与完整TLS/HTTPS验收须在实现后完成；不能把上述原版CLI对照当cc2api已对齐。现有`runtime_transport::tests::local_https_*`使用本地CA、模拟响应并断言证书／主机名失败和取消；扩充同样的本地边界。
