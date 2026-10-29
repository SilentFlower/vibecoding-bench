# cc2api：依据原生抓包对齐 TLS 指纹

## Goal

在抓包升级并补齐原生握手证据后，对齐 cc2api 与目标 Claude Code 版本的 TLS 行为。

## Background

- 用户要求先登记，待抓包升级后再做；本轮主线继续第二批差异评审。
- [第一轮评审](../10-29-cc2api-vm2api-wire-differential-study/research/alignment-review/round-01.md)已确认当前 cc2api 使用固定模板；本地 280 .flow 的部分 TLS 元数据不足以还原完整指纹，293 远端原件待核查。
- [既有 303 TLS／正文核查](../10-28-cc2api-303-tls-body-alignment/prd.md)提供研究背景；本任务只负责依据原生证据进行 TLS 对齐。

## Preconditions

1. 完成抓包升级：新增 `tls_clienthello.jsonl`，保存 ClientHello 内容、有序字段及版本／run／连接／HTTP flow 关联。实现及固定 11.1.3 验证已在[采集升级任务](../10-30-v3-capture-tls-clienthello/prd.md)完成；部署与实际样本以该任务交付记录为准。
2. 补齐原生 280／293 客户端侧握手，并与无解密透传条件对照；区分 CLI→sidecar 和 sidecar→上游。
3. 证据就绪后再补齐设计、实施计划和 Brief；本轮不激活或实施本任务。

## Requirements

- R1：按精确版本和运行条件比较 cipher suites、有序扩展、signature_algorithms、supported_groups、key_share 的组／顺序／长度、ALPN、SNI 及新建／恢复连接行为。
- R2：保留 ClientHello 内容及独立解析依据，注明记录封装是否合成；JA3／JA4 仅辅助比较。
- R3：只修改原生证据证明的差异；根据实际结果决定是否按版本区分 TLS 模板，不根据 UA 或 vm2api 预设猜测目标。
- R4：保持账号代理、证书／主机名验证、密钥交换及连接生命周期；明确记录未知和未覆盖条件。
- R5：补采和部署分别遵守项目 SOP；本次登记不启动真实账号调用、采集或部署。

## Acceptance Criteria

- [ ] AC1：抓包升级及目标版本握手样本有可验证产物。
- [ ] AC2：原生 CLI、cc2api 与本地 vm2api 参考的逐项差异明确来源、版本和连接方向。
- [ ] AC3：需修改、可保留及未覆盖项均有证据与说明。
- [ ] AC4：实现后通过独立 ClientHello 解析和本地完整 TLS 握手回归，覆盖受影响的组、ALPN、证书验证和恢复／连接行为。
- [ ] AC5：完成必要检查、Spec 与 Git 流程；未完成正式采集或部署时不标记为原生线上对齐通过。

## Non-Goals

- 本轮立即修改 TLS、升级画像或部署。
- metadata.user_id、CCH、billing、模型能力或未知正文键治理。
- 未经原生核对就复制 vm2api 的算法列表和 key_share 配置。
