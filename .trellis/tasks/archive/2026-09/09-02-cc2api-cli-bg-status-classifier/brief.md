# Brief - 适配 Claude Code 后台状态分类请求

## Goal

- 为 Claude Code 2.1.257 的 Fable 5.1 `cli-bg` 状态分类请求增加默认放行、可切模拟的全局模式，并通过 cc2api 及账号代理链路验证不再因通用正文改写集中返回 429。

## Scope

- 新增 `intercept_cli_bg_status_classifier_mode=passthrough|mock`，默认 `passthrough`，完成 DB 默认、管理 API 校验、启动加载、热刷新和 Settings 页面二选一控件。
- 用原始 `x-app=cli-bg`、Claude Code UA、精确 `claude-fable-5-1`、非流式、`max_tokens=3072`、唯一 ephemeral system block 和唯一 user 状态载荷组成强特征检测。
- 放行模式继续走账号选择、RPM/concurrency、OAuth、2.1.257 header、账号 `proxy_url`、TLS 指纹、401/429 重试和响应透传；正文只做账号 metadata/upstream session identity 映射。
- 放行模式绕过空 text、system/billing/env、Git/currentDate、message cache_control、TTL、disabled thinking、API body order 和 CCH 等通用正文改写。
- 模拟模式在账号选择前返回 HTTP 200 Anthropic Message envelope，`content[0].text` 为符合 `state/detail/tempo/needs/output` 的可解析 JSON。
- 补 detector 正反例、identity-only 正文、mock schema、setting 默认/非法值/热刷新和前端构建测试。
- 代码检查通过并发布后，使用固定到 `proxy_url` 非空账号的一次性网关 token，经 `https://us.flower-cli.com/v1/messages` 发起脱敏仿真请求，验证真实上游响应不是 429。

## Non-Goals

- 不直接使用账号 OAuth token 绕过 cc2api 或账号代理请求 Anthropic。
- 不自动开放 Fable 5 / Fable 5.1 `[1m]`，不修改 `allow_1m_models`。
- 不修改旧 Auto Mode XML classifier、Fable 画像/CCH/周配额、首字节超时或全局 429 重试策略。
- 不用生产 `mock` 的 HTTP 200 冒充放行修复成功，也不承诺消除所有 Anthropic 限流或零首字节故障。
- 不提交完整抓包、真实 prompt、token、代理 URL、邮箱或账号 UUID 映射。

## Key Decisions

- 首版 detector 精确限制到 `claude-fable-5-1`，不把只在 5.1 上验证的旁路泛化到 Fable 5 或未来模型。
- “放行”不是完全原始 body 直通：保留代理账号 metadata/session 身份映射，其他正文形状保持 Claude Code 原样，避免下游身份与所选 OAuth 账号不一致。
- “必须走他的代理”按运行时证据验收：固定 `proxy_url` 非空账号，并记录脱敏 `proxy_configured=true`，不能只看 cc2api 返回 200。
- 默认模式保持真实上游 `passthrough`；`mock` 只是管理员显式切换的本地降级能力。
- mock 只读取 user 状态摘要与 assistant tail，显式 marker 优先、`Current state` 回退、未知时保守返回 working。

## Key Context

- Gateway 热路径与现有 classifier：`cc2api/src/service/gateway.rs`。
- 正文/header/identity/CCH 改写：`cc2api/src/service/rewriter.rs`。
- setting 默认与迁移：`cc2api/src/store/settings_store.rs`、`cc2api/src/store/db.rs`。
- 管理 API 与热刷新：`cc2api/src/handler/router.rs`、`cc2api/src/main.rs`。
- Settings UI：`cc2api/web/src/components/Settings.vue`。
- 研究结论：`research/cli-bg-status-classifier-design-audit.md`；线上 288 条 429 的首要差异是新增 message cache breakpoint 和 system TTL 变为 1h，但仍需生产代理 A/B 证明因果。

## Risks / Deferred

- identity-only 仍会因结构化 metadata 替换而重新序列化 JSON；若真实代理请求仍为 429，需要继续对比 identity-only 与完全原始 body，但完全原始 body 不能直接作为默认方案。
- detector 过宽会误伤普通请求，过窄会因官方文案变化漏命中；通过四层 gate 和负例控制。
- 生产全文 429/非流日志可能记录正文；验收窗口会先保存并临时关闭相关设置，结束后恢复。
- 提交、推送、镜像发布和生产 recreate 仍分别遵循 Trellis 的确认与低连接门禁。

## Acceptance

- 新旧数据库默认均为 `passthrough`，合法值可热刷新，非法值被拒绝，Settings 页面 round-trip 正常。
- 真实 Fable 5.1 `cli-bg` 样本命中，Fable 5、`[1m]`、旧 XML classifier 和各类缺失特征负例均不命中。
- 放行最终正文无新增 message cache_control、无新增 TTL，system/messages/thinking 保持原形，只允许账号 metadata/session 映射变化。
- 模拟响应 envelope 和内层状态 JSON 可解析，且不进入账号、RPM、并发槽或上游链路。
- `cargo fmt --check`、定向测试、`cargo test`、`cargo test cch` 和 `npm run build` 全部通过。
- 新镜像部署后 setting 保持 `passthrough`；仿真请求经过 `https://us.flower-cli.com` 和 `proxy_url` 非空账号获得真实非 429，日志只含脱敏旁路证据。
- 验收结束后一次性 token 删除、日志设置恢复、生产模式仍为 `passthrough`。

## Next Step

- Check-All 重检已通过；下一步进入规范同步与提交，随后按发布门禁进行生产账号代理验收。
