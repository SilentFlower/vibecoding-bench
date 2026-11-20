# Native messages 缓存断点 off 与 sub2api

## Goal

让系统设置中的 off／sub2api 控制 native messages 缓存断点行为，默认关闭额外改写，作为遇到缓存问题时可手动开启的备用策略。

## Background

实施前，gateway 的原生 worker 启动配置固定 CCRB_CACHE_POLICY=preserve。原生运行时已有 preserve／sub2api 策略实现。TTL 已经通过独立字段接入。

行为差异已核对：原有 Rewriter::rewrite_message_cache_control 的 Sub2api 分支先 strip_message_cache_control，再重新选点。原生 applyCachePolicy 在调用方 messages 含任何缓存断点时直接保留现有布局并报告 caller_message_breakpoints。两者选点均以末条 message 和消息数达到4时的倒数第二个 user message 为主要候选，整体预算受已有 tools/system 断点影响。

设计依据：.trellis/spec/runtime/backend/runtime-contract.md:362 的可选 sub2api 消息缓存策略合同明确规定调用方消息断点优先，只替换本轮 SDK 自动生成的断点；services/runtime/docs/api.md:146 同步记载该规则。原生保留优先是实施前的明确合同。gateway 固定 preserve 且未传入系统设置属于实施前的独立集成边界。用户本轮已确认对齐原有转发的显式改写语义，实现时需同步相应合同及测试，并明确共享运行时的适用入口。

## Requirements

- R2.1：优先接入 off／sub2api。
- R2.2：沿用系统设置入口，保持与 TTL 策略的组合关系清晰。
- R2.3：用户已确认 off 保留现有布局；显式选择 sub2api 后按原有转发清理 messages 断点并重新选点。system/tools 的断点按原有 sub2api 规则保留。
- R2.4：用户已确认系统设置页只保留 off／sub2api 两个选项，auto／rolling／stateful 退出可选范围。存量值统一转为off。
- R2.5：设置保存后沿用系统设置对后续请求热生效的交互，具体传递和能力核验机制在设计中确定。
- R2.6：用户已确认存量 auto／rolling／stateful 统一转换为 off，保持当前 native 的 preserve 行为。历史 stable／anchored 别名按废弃模式一并归入该兼容处理。
- R2.7：默认模式为 off，保留 native 原生缓存布局；管理员可在遇到缓存问题时手动选择 sub2api，随后可切回 off。设置页应说明关闭的是额外断点改写，原生缓存继续按原有布局工作。
- R2.8：首次接入时，升级前已保存的 sub2api 一次性重置为 off，保持现有 native 行为。兼容处理完成后，管理员新保存的 sub2api 持久保留，服务重启及重复兼容处理均按该选择运行。

## Acceptance Criteria

- [ ] off 保留原有缓存布局；sub2api 对调用方已有 messages 断点执行清理与重新选点。
- [ ] sub2api 选点、总断点预算和 TTL 组合按确认后的合同验证。
- [ ] 策略应用结果可通过已有诊断核对。
- [ ] 设置页展示、保存校验与实际生效模式统一为 off／sub2api。
- [ ] 保存后的后续请求采用新模式；已经发送的请求按原冻结模式执行。
- [ ] 首次接入时，存量 sub2api 及废弃模式统一转换为 off；显式 off 保持。
- [ ] 新安装与缺失设置默认 off；手动开启和关闭后，后续请求分别按 sub2api 和原生保留布局执行。
- [ ] 一次性兼容成功后手动保存 sub2api，重复启动和兼容处理仍保留该选择；兼容失败重试保持原子性。

## Non-Goals

- auto／rolling／stateful 策略退出本项公开可选范围。
- 软件发布、线上部署和内核激活由独立SOP承接。本项交付代码、文档、本地配套候选及验证证据。
- 缓存命中及成本收益作为后续真实用量对照项；本项验收以实际请求断点、生效模式和兼容行为为准。
