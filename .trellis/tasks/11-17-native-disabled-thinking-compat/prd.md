# Native thinking disabled 最小兼容

## Goal

将原有按模型范围控制的 thinking.type=disabled 最小兼容接入native转发，提供默认关闭、可手动启用的改写能力。

## Background

原有路径有独立的 disabled thinking 开关和模型列表。native 分流绕过对应 Rewriter 分支。

原有 rewrite_disabled_thinking_to_adaptive（services/gateway/src/service/rewriter.rs:6104）仅在开关开启且完整模型名精确命中列表时，将顶层 thinking.type 从 disabled 改为 adaptive；其余顶层子字段原样保留，历史 thinking 签名块保持。原生运行时另有普通API disabled 字段保留适配（services/runtime/src/runtime/293/job.ts:196），两者目的和作用入口需要分别验证。

当前出厂开关为false，模型名单为claude-fable-5（services/gateway/src/store/settings_store.rs:77）。本轮代码及历史材料核对见research/evidence-inventory.md。

## Requirements

- R4.1：使用固定版本原生执行体与隔离回环上游验证兼容前后的构造和实际发送，记录输入、源版本、响应与发送次数。
- R4.2：用户已确认沿用原有显式开关和精确模型名单，在命中请求上将顶层 thinking.type 从 disabled 改为 adaptive，允许模型自适应思考。
- R4.3：历史消息、签名块、其他 thinking 子字段及未命中模型按原规则保持。
- R4.4：保存后的配置用于后续请求，原始入站诊断继续展示改写前输入。
- R4.5：出厂默认关闭，已有管理员选择保持；单请求冻结配置，首次发送、429换号及签名修复沿同一配置执行。
- R4.6：真实上游失败与实际兼容效果作为后续验证记录，当前交付以可核对的原生构造、TLS发送及配置控制证据验收。

## Acceptance Criteria

- [x] 280/293原生执行体在隔离回环中按开关和名单正确发送disabled或adaptive，保留可核对的前后对照。
- [x] 默认关闭、完整模型名精确匹配、保存后续请求生效及单请求配置冻结经过验证。
- [x] 原始入站与实际改写值分别可核对，历史签名、其他thinking子字段、缓存和TTL符合既有合同。
- [x] 首次发送、429换号及签名修复重试沿同一改写配置，实际发送次数与CCH正确。

## 验证范围与决定

2026-11-17用户确认目前没有真实失败样例，并明确要求继续适配。该决定将真实上游复现调整为后续验证项，当前任务继续接入既有显式开关和模型名单。

原生执行体、合成凭据、隔离网络和回环上游用于本轮验证。模拟拒绝与真实上游事件分别登记。生产账号、外部付费调用和正式部署由独立授权边界承接；取得真实失败记录后补充模型行为与实际兼容效果证据。

## Out of Scope

本项复用已有开关及精确模型名单。自动探测模型能力、扩大默认名单、调整既有历史签名修复规则及正式部署由独立范围承接。
