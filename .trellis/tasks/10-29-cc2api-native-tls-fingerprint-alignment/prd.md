# cc2api：依据原生抓包对齐 TLS 指纹

## Goal

让 cc2api 的统一出站 TLS 模板与原版 Claude Code 2.1.293 主请求的实际 ClientHello 一致，并保持完整安全握手与请求转发。

## Background

- 本任务原按用户要求登记为 F05，等待采集升级；[采集升级](../10-30-v3-capture-tls-clienthello/prd.md)已上线 `ci-40947973262-1`，本次用户明确要求依据新证据开始对齐。
- 六代执行共58条具有原生 HTTP 关联的握手，确认主 messages 新连接 `1523504b38f0fae0d881d4b6554aac1b`、恢复连接 `ae5f2d34331c18f27df379f7d4b72e35`；部分辅助请求另有两种指纹，不能混作同一客户端形状。
- 原版2.1.293精确二进制在隔离容器、空HOME、无真实凭据和外网条件下直接向本地监听器发送握手，主请求字段及JA3与线上一致。公开数值和摘要见 `research/`，原始票据及请求正文不进入仓库。
- `cc2api/src/tlsfp/tlsfp.rs` 目前维护统一的旧Node模板；账号代理、连接池、正式gateway和v3发送器共享该工厂。旧模板cipher、扩展顺序、签名算法、组及key_share与目标均不同。
- [第一轮评审](../10-29-cc2api-vm2api-wire-differential-study/research/alignment-review/round-01.md)和[303核查](../10-28-cc2api-303-tls-body-alignment/prd.md)保留历史背景；本轮以实际293证据为准。

## Requirements

- R1：按原生293主请求对齐有序cipher、扩展、signature_algorithms、supported_groups、key_share组／顺序／长度、ALPN、legacy_version、supported_versions及EC点格式。SNI仍来自真实目标，随机数和密钥必须由本次真实握手生成。
- R2：保留可追溯证据、独立解析和JA3复算；区分新连接与真实恢复时末尾PSK扩展，不伪造票据、binder或恢复状态。
- R3：维持现有统一TLS模板和客户端工厂接口，将目标基线明确为293主请求；本轮不引入按辅助端点或CLI版本路由的多套模板，不把该结果宣称为280／303或全部辅助接口已对齐。
- R4：混合组4588真实参与密钥交换，保留X25519及已声明曲线的可用性；恢复和HRR遵守协议，拒绝不合法peer key，维持证书／主机名验证、代理失败关闭、连接池、保活和流式行为。
- R5：完成定向和完整Rust回归、Check-All及Spec；沿用户既有连续交付要求，按子仓→父仓顺序推送，匹配Actions打包后部署us v3，保留工程、会话、身份、计划和历史抓包。

## Acceptance Criteria

- AC1：真实293成功messages握手与无MITM原版二进制对照的字段、封装、来源和摘要可核对；旧模板逐项差异有记录。
- AC2：实际cc2api发出的新连接JA3匹配 `1523504b38f0fae0d881d4b6554aac1b`，独立解析全部目标字段及有序扩展一致，不只比较常量或摘要。
- AC3：完整本地TLS1.2／1.3 HTTPS成功；TLS1.3第二连接真实会话恢复、PSK末尾位置和key_share稳定；HRR可成功，混合组真实双方秘密一致，非法peer与证书／主机名失败明确拒绝。
- AC4：同代理复用／异代理隔离、非法代理无直连、长流与取消的现有回归保持；无测试凭据或原始抓包入库。
- AC5：精确提交及匹配联合镜像成功上线，健康、身份／计划保留和镜像收尾通过；实际镜像发出的握手独立复算与目标相符，未覆盖项如实记录。

## Non-Goals

- HTTP请求头、User-Agent、billing／CCH、正文、身份、账号默认版本、设置UI与数据库迁移。
- JA4或握手随机字节相等，复制真实票据／PSK／私钥，未经实测把vm2api或其他版本模板作为正式基线。
- 280／303补采及辅助端点多模板分流；完整TLS record分片、DTLS／QUIC／ECH行为对齐。
