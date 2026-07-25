# Brief — 升级 cc2api 至 Claude Code 2.1.220

## Goal

- 基于 Opus 5 与重新抓取的 Fable 5 真实流量，将 cc2api 默认协议画像升级到 `2.1.220`，保证旧画像可回滚，并让模型请求继续兼容 `Claude Code -> new-api -> cc2api` 链路。

## Scope

- 新增并启用 `2.1.220` identity、access policy、request、billing、telemetry 和 bootstrap 画像，保留 `2.1.197` 及更早内置画像。
- 按账号选中画像生成 beta、Stainless runtime、Fable fallback、max tokens、body order、TokenTester 请求和自动 telemetry。
- 更新 system-role/assistant-prefill 全局默认模型及精确旧值迁移，成对迁移 2.1.197 profile/allowed range 和账号 canonical env。
- 将 2.1.220 接入现有 `cc_version`/CCH 分支，不改变已由 69 个样本验证的算法、seed 和 top-level 规范化规则。
- 对齐 configured bootstrap 的 `cedar_basin`、Fable `marigold`、Opus 5 `belladonna`，保持 passthrough/hide_fable/gzip 兼容。
- cc2api 增加无鉴权 `GET/HEAD /api/hello`，覆盖直接访问 cc2api 的部署形态和健康检查。
- 同步 cc2api Settings fallback/default 和 vibecoding-bench worker、compose、orchestrator、WebUI、README 的兜底版本到 2.1.220。

## Non-Goals

- 本任务不执行远程部署，不修改远程数据库或 `.env`。
- 不全量仿制 Claude Code 客户端本地 telemetry 事件，不伪造 Fable CLI flag 或 skill 事件。
- 不支持任意版本字符串画像，也不提交完整抓包或敏感请求内容。
- 不把 `/api/hello` 做成无鉴权通用 relay，不硬编码 cc2api 渠道、渠道 ID 或远程地址。

## Key Context

- 实现依据：Opus run `1512e30eb37c`、新 Fable run `a0f3cfd653ea`；旧 Fable run 已废弃。
- 2.1.220 identity：build time `2026-07-24T22:17:45Z`、Node `v26.3.0`、Stainless `0.94.0`、Bun `1.4.0`。
- Opus 5 通用 beta 新增 `fallback-credit-2026-06-01`；Fable fallback 改为 `claude-opus-5`，body 中 `fallbacks` 位于 `context_management` 与 `output_config` 之间。
- CCH/cc_version 共 69/69 抓包样本命中现有算法；实现只增加 2.1.220 版本映射，CCH 仍在最终 body 字节上计算。
- 原生 telemetry wire shape 不变；自动 telemetry 的基础 beta 和启动模型需要改为版本画像来源。
- settings 迁移只匹配精确旧默认值，必须保留管理员自定义和显式旧 profile 回滚。
- 本地 2.1.220 探针和抓包复核确认：`HEAD /api/hello` 固定请求 `https://api.anthropic.com/api/hello`，不会使用 `ANTHROPIC_BASE_URL`；`/v1/messages` 才会进入配置的 new-api base URL。
- 因此当前不修改 new-api，也不存在为 hello 在多个渠道 Base URL 中选路的问题；后续只有客户端行为变化时再重新评估。
- new-api 配套任务：`/root/project/new-api/.trellis/tasks/07-25-claude-code-api-hello`。

## Acceptance

- 默认 profile/UA/canonical env/allowed range/Settings 均为 2.1.220，旧画像回滚测试通过。
- Opus、Fable、Haiku 的 beta/runtime/max tokens/fallback/body order，以及 2.1.220 cc_version/CCH 均有定向回归测试。
- Bootstrap Fable/Opus/hide/gzip、settings migration、自动/原生 telemetry 测试通过。
- cc2api 的无鉴权 GET/HEAD hello 契约通过；GET 返回精确 JSON，HEAD 返回空 body 和正确长度，其他鉴权与模型 relay 行为不变。
- `cargo fmt --check`、`cargo test`、`cargo test cch`、cc2api 前端 build、bench Python/compose 检查通过。
- 最终 diff 不包含完整抓包、Authorization、Cookie、邮箱、账号标识、完整 prompt 或响应正文。

## Next Step

- 进入 Check-All，核对实际 diff、版本回滚、迁移和验证证据。
