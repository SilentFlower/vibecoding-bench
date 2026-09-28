# 任务 Brief

## Goal

保留现有后台状态分类请求的“透传 / 模拟”模式，并新增一个独立、默认关闭的身份注入开关。开关开启时，只对强特征命中的非 Haiku Claude Code 状态分类请求补齐缺失的 billing/CCH 归因块和官方 identity 块，使 Fable 5.1、Opus、Sonnet 等非 Haiku classifier 继续经过真实账号代理链路时具备标准 Claude Code system 前缀，降低无细节 429。

## Scope

- 保留 `intercept_cli_bg_status_classifier_mode=passthrough|mock`，默认仍为 `passthrough`。
- 新增 `intercept_cli_bg_status_classifier_identity_injection_enabled=true|false`，默认 `false`，打通数据库默认值、管理 API 校验、Gateway 热刷新和 Settings UI。
- 保留现有窄 Fable 5.1 detector，只用于当前已确认事故画像的 mock 与旧透传旁路。
- 新增通用 classifier detector，只用于非 Haiku 透传前缀补齐，支持 `x-app=cli|cli-bg`、`stream=false` 或省略，不固定模型和 `max_tokens`。
- 开关开启且通用 detector 命中非 Haiku 请求时，继续走真实账号、OAuth、账号代理/TLS、限流与重试链路，并执行最小正文改写。
- 缺少 billing 时复用 API 模式生成标准 billing 和有效 CCH；已有 billing/CCH 时在最终正文上刷新 CCH；已有 billing 但无 CCH 时保持原历史格式。
- 缺少 identity 时插入精确官方身份块，最终 system 顺序为 billing、identity、classifier；不生成 expansion。
- 命中请求使用 `SummaryOnly` 捕获，只输出脱敏结构摘要。
- 补充设置、迁移、detector、rewriter、Gateway、CCH 和前端构建验证，并更新管理员配置说明。

## Non-Goals

- 不扩大本地 mock 到 Haiku、Opus、Sonnet 或未来模型。
- 不改写普通 `/v1/messages` 主请求，也不只凭 UA 或单段提示词命中。
- 不对 Haiku classifier 注入 billing 或 identity。
- 不修改 Claude Code 客户端、vibecoding-bench worker 环境变量或 small-fast 模型选择。
- 不修改 Fable 5/Fable 5.1 模型画像、`[1m]`、周配额、thinking、缓存或全局 429 重试策略。
- 不在本任务中自动部署生产环境。

## Key Decisions

1. 只有两个配置项：现有处理模式和新增身份注入开关，不增加第三个 billing 开关。
2. 新开关默认关闭；关闭时请求行为必须与当前版本一致，便于即时回滚。
3. 窄 detector 与通用 detector 分责。通用 detector 不改变 mock 范围，只决定是否执行透传前缀补齐。
4. 通用 detector 要求 Claude Code 客户端、正确 path/x-app、非流式请求、唯一 classifier system block、最多一个 billing、最多一个精确 identity，以及唯一且带稳定标签的 user 输入；出现未知或重复 system block 时不命中。
5. 补齐资格为 `passthrough + enabled + generic match + non-Haiku`，不以“缺少 identity”作为进入条件，因此已有 identity 但缺 billing 的请求也会补齐 billing/CCH。
6. 缺少 billing 时复用现有 API 模式 billing builder 和所选账号的 Claude Code 版本画像；不得复制其他账号身份，也不得运行完整 API system expansion。
7. 所有正文变化完成后再计算 CCH。新建 billing 生成有效 CCH；已有 billing 且含 `cch=` 时刷新；已有 billing 无 CCH 时不擅自升级格式。
8. identity 文本固定为 `You are Claude Code, Anthropic's official CLI for Claude.`，不带 `cache_control`，且保持幂等。
9. 新补齐分支优先于 narrow passthrough 旧旁路；narrow mock 仍最先本地返回。这样开关开启时 Fable 5.1 事故画像可真正得到 billing/identity 补齐，关闭时仍走原路径。

## Key Context

- 当前窄 detector 位于 `cc2api/src/service/gateway.rs`，固定匹配 `x-app=cli-bg`、Fable 5.1、显式 `stream=false`、`max_tokens=3072` 等事故画像。
- Claude Code 2.1.257 二进制显示后台 classifier 可因远端配置从 small-fast 切到当前主模型，非 small-fast 路径可形成 `max_tokens=3072`。
- 真实 Haiku 抓包使用 `x-app=cli`、省略 `stream`、`max_tokens=1024`、billing + classifier、无 identity，且返回 200；因此 Haiku 必须识别但不注入。
- 早期 Claude Code `sideQuery` 路径会在 `skipSystemPromptPrefix` 下保留 billing、跳过 identity，说明这类请求确实可能缺身份块。
- API 模式已有 billing 构造与 2.1.257 CCH 计算能力，应抽取或复用现有逻辑，避免另写不一致算法。
- 预计主要修改 `cc2api/src/service/gateway.rs`、`rewriter.rs`、`settings_store.rs`、`db.rs`、`router.rs`、`main.rs`、`web/src/components/Settings.vue` 及配置文档；实现前仍需逐项核对现有类型和方法签名。

## Risks / Deferred

- Claude Code 判断仍包含 UA 特征，无法作为密码学身份证明；system allowlist 和结构约束用于降低仿冒请求误伤。
- 官方 classifier prompt 未来变化可能造成漏识别；采用多组稳定标记，不依赖完整 prompt hash。
- billing/CCH 生成或刷新顺序错误仍可能触发 429，必须以最终序列化正文做定向测试。
- 本地测试只能验证改写契约，真实上游 429 是否消失需要在后续明确部署后通过生产代理链路抓包验证。

## Acceptance

- 新 setting 在新旧数据库中默认 `false`，已有值不被覆盖，管理 API 只接受字符串 `true|false`，保存后无需重启即可生效。
- Settings 页面保留透传/模拟切换并新增独立开关；mock 模式禁用编辑但保留已保存值。
- 原窄 detector、mock 响应和开关关闭时的 passthrough 行为不回归。
- 通用 detector 正确命中已知 Fable 与 Haiku classifier 结构，并排除流式、API UA、错误 path/x-app、普通主请求、未知/重复 system block、多消息和缺少稳定标记的请求。
- 开关开启时，非 Haiku classifier 的最终 system 为 billing、identity、classifier；缺块只补一次，不加入 expansion，Haiku 永不补齐。
- billing 缺失时生成有效 CCH；已有 CCH 时基于最终正文刷新；metadata/session 映射与账号代理链路保留。
- classifier、user、thinking、fallbacks、cache_control 和未知顶层字段不被无关改写；日志与捕获不泄露正文或凭据。
- Rust 格式化、定向测试、完整测试、CCH 测试和 `cc2api/web` 构建全部通过。

## Next Step

用户确认本 Brief 后，将任务状态切换为 `in_progress`，再按 Trellis implement 路由进入实现；完成实现与检查后，部署仍需单独明确指令。
