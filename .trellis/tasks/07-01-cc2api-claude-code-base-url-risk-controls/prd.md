# cc2api Claude Code base URL 风险控制

## Goal

在 `cc2api` 中为 Claude Code 因 `ANTHROPIC_BASE_URL` / 非官方 base URL 产生的隐藏上下文标记提供低风险治理能力：默认只做风险扫描和脱敏日志，不改变请求语义；同时扩展 telemetry 清洗，减少 base URL / gateway / proxy 痕迹被上报；提供显式 `currentDate` 规范化开关，管理员确认后可把 Claude Code 自动注入日期恢复成稳定格式。

## Background

- Claude Code `2.1.195` native binary 中确认存在读取 `ANTHROPIC_BASE_URL` hostname、判断 `Asia/Shanghai` / `Asia/Urumqi`、命中编码域名表/关键词表后改变 `Today...date...` 字符串标点和日期分隔符的逻辑。
- 该逻辑发生在客户端生成请求上下文之前，`cc2api` 无法阻止本地 CLI 读取环境变量；`cc2api` 能做的是在 `/v1/messages` 网关改写阶段进行扫描、记录、可选规范化，并继续保证 CCH / `cc_version` 基于最终 body 刷新。
- 现有 `cc2api/src/service/rewriter.rs` 已在 Claude Code 客户端模式中改写 `metadata.user_id`、system prompt、billing/CCH、环境字段和 `<system-reminder>`；这是承接 currentDate 扫描/规范化的正确边界。
- 现有 `cc2api/src/service/telemetry.rs` 已有 `sanitize_telemetry_payload`，并按 key/value 丢弃 token、email、prompt、tool input、response body 等字段；需要扩展 base URL / gateway / proxy denylist。
- 新 setting 必须同步默认值、DB 默认插入、管理接口校验、Gateway 热缓存、前端设置页和测试。

## Requirements

### R1. 风险扫描与 report-only 日志

- 新增 Claude Code context sanitizer 配置，至少支持 `off`、`report_only`、`normalize` 三种模式。
- 默认模式为 `report_only`。
- 在 `/v1/messages` 且识别为 Claude Code 客户端时扫描 `system` 和 `messages[].content[].text` 中的 Claude Code 自动注入日期上下文标记。
- 扫描命中时只输出脱敏结构化 warning：包含模式、命中类型、字段路径、是否规范化、文本 hash / 长度等摘要，不输出完整 prompt、完整 system 文本、token、邮箱或账号 UUID 原文。
- `report_only` 模式不得修改请求体。

### R2. `currentDate` 规范化开关

- `normalize` 模式下，仅规范化 Claude Code 自动注入的日期上下文文本，不处理普通用户正文。
- 规范化目标是去掉隐藏布尔编码造成的撇号差异和日期分隔符差异，恢复为稳定格式，例如 `Today's date is YYYY-MM-DD.`。
- 规范化必须发生在 CCH / `cc_version` 最终刷新之前。
- 规范化应尽量精确，避免替换用户自然语言里的普通 `Today...date` 文本。

### R3. telemetry denylist 扩展

- 扩展 telemetry sanitizer 的敏感 key/value 识别，覆盖 base URL、gateway、proxy、host 等代理痕迹字段。
- 至少覆盖 key：`baseUrl`、`baseURL`、`base_url`、`ANTHROPIC_BASE_URL`、`anthropic_base_url`、`apiBaseUrl`、`gateway`、`gatewayHost`、`proxyHost`、`proxy_url`。
- 对字符串值中的 URL/host 做保守识别：命中非官方 base URL / proxy/gateway 痕迹时丢弃该字段，避免只靠 key 名称。
- 继续保持现有允许字段行为，不把常规 `api.anthropic.com` / `anthropic.com` 作为风险值误删。

### R4. 设置链路与管理页

- 新增 setting key：`claude_code_context_sanitizer_mode`。
- GET `/admin/settings` 返回默认值；PUT `/admin/settings` 校验只允许 `off|report_only|normalize`。
- `GatewayService` 用 `RwLock` 缓存该 setting，并在 `update_settings` 后热刷新。
- 前端 `Settings.vue` 展示三档模式并保存；说明默认观测、不默认改写。

### R5. 测试与质量

- 后端新增单测覆盖：扫描命中但 `report_only` 不改 body；`normalize` 改写目标文本；非 Claude Code / 普通用户正文不误改；telemetry 扩展 denylist 能删除 base URL / proxy 痕迹。
- 跑 `cd cc2api && cargo fmt --check && cargo test`。
- 若修改 `cc2api/web`，跑 `cd cc2api/web && npm run build`。

## Acceptance Criteria

- [ ] 默认 `claude_code_context_sanitizer_mode=report_only` 可通过 `/admin/settings` 读取。
- [ ] `report_only` 模式下，命中可疑 currentDate 标记时只记录脱敏 warning，不改变最终转发 body。
- [ ] `normalize` 模式下，命中的 Claude Code currentDate 标记会规范化，并且规范化发生在 CCH / `cc_version` 刷新之前。
- [ ] telemetry sanitizer 会删除 base URL / gateway / proxy 相关 key/value，且不删除正常 `api.anthropic.com` 相关公开字段。
- [ ] 管理页可以切换 `off|report_only|normalize` 并保存，保存后热路径立即生效。
- [ ] 后端和前端验证命令通过，或明确记录未能运行的原因。

## Out Of Scope

- 不 patch Claude Code binary，不试图隐藏本地 CLI 对 `ANTHROPIC_BASE_URL` 的读取。
- 不改变 `cc2api` 默认 Claude Code 版本画像、beta 顺序、CCH seed 或账号迁移策略。
- 不默认启用 normalize；除非管理员显式切换，否则只观测和清洗 telemetry。
- 不记录完整请求体、完整 prompt、完整 system prompt 或真实敏感标识。

## Open Question

- 默认模式推荐为 `report_only`。如果用户明确要求更激进安全策略，可改为默认 `normalize`，但会改变默认请求体行为并提高误改风险。
