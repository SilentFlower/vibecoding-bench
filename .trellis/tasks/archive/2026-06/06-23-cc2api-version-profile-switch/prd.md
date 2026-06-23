# cc2api 版本特征切换

## Goal

在 cc2api 管理后台的系统设置中提供 Claude Code 版本特征切换能力。管理员选择目标版本后，系统需要统一切换请求画像、账号 canonical env、允许的 Claude Code 版本范围和自动遥测画像，确保不同抓包版本之间可控、可回滚、可审计地切换。

首批候选版本来自已抓包验证过的版本，例如 `2.1.185` 和 `2.1.173`。切换后不应出现“设置页显示新版本，但请求、账号、允许版本范围或 telemetry 仍混用旧版本”的状态。

## Confirmed Facts

- cc2api 已有集中版本画像源头 `src/service/version_profile.rs`，当前默认版本画像会被 `model/identity.rs`、`service/rewriter.rs`、`service/telemetry.rs`、`service/gateway.rs` 等链路引用。
- 当前实现只有编译期默认画像常量，尚无运行时 `version_profile` setting 或内置画像枚举。
- 现有规范要求版本画像升级必须覆盖 `DEFAULT_CLAUDE_CODE_VERSION`、`DEFAULT_CLAUDE_CODE_VERSION_BASE`、`DEFAULT_CLAUDE_CODE_BUILD_TIME`、`claude_code_user_agent(version)`、`DEFAULT_ALLOWED_CLAUDE_CODE_VERSIONS_SETTING`。
- 现有规范明确版本画像相关迁移必须更新已有账号的 `canonical_env.version/version_base/build_time`，不能只改新账号默认值。
- 管理后台新增 setting 需要同步默认值、数据库迁移、后端校验、热刷新缓存、前端类型和 Settings 控件。
- 历史任务已经覆盖 `2.1.173` 和 `2.1.185` 的抓包/升级/telemetry 画像对齐，当前任务应复用这些结论，而不是重新猜测协议字段。
- `2.1.173` 与 `2.1.185` 均沿用既有 `cc_version` 后缀公式和 `2.1.172+` CCH 输入规范化规则，但 build_time、UA 版本、默认允许范围和部分 telemetry/GrowthBook 画像值不同。
- 用户已确认：切换版本时强制覆盖 `allowed_claude_code_versions` 为目标画像的默认允许范围；`allowed_user_agents` 不随版本切换，保留管理员现有配置。
- 最近 cc2api commit 显示 `2.1.185` 不是只改 UA：`b2b34ce` 将默认画像升级到 `2.1.185`，同时把 GrowthBook UA 从 `Bun/1.3.14` 改为 `Bun/1.4.0`，并把 `2.1.185` 纳入 CCH 分支；`014c0e5` 专门对齐 `2.1.185` telemetry 结构，涉及 event payload 和 GrowthBook payload shape。

## Requirements

- 在系统设置中新增一个版本特征切换控件，支持选择已内置且已验证的 Claude Code 版本画像。
- 首批内置版本至少包括 `2.1.185` 和 `2.1.173`；每个版本画像必须包含版本号、version_base、build_time、默认允许版本范围、User-Agent 生成规则、GrowthBook UA、请求 header/body/billing/telemetry 所需的非敏感画像字段。
- 切换版本后，网关新请求必须使用目标版本的请求特征，包括 `User-Agent`、`x-anthropic-billing-header` 中的 `cc_version` 基础版本、CCH/`cc_version` 计算输入所需版本参数、`anthropic-beta` 规则、自动 telemetry 的 env 版本字段。
- 切换版本后，自动 telemetry 必须使用目标版本对应的结构，不得只替换 `env.version`。至少要覆盖 event logging 的 `email` 是否出现、`betas` 默认值、`additional_metadata` 编码、`env.shell` / `is_running_with_bun` 字段，以及 GrowthBook eval 的 `User-Agent` 和 payload 顶层 shape。
- 切换版本后，所有账号的 `canonical_env.version`、`canonical_env.version_base`、`canonical_env.build_time` 必须同步到目标版本画像。
- 切换版本后，允许的 Claude Code 版本范围必须同步更新为目标版本画像对应的安全默认值。
- 切换版本不得改写 `allowed_user_agents`；非 Claude Code/CLI 客户端 UA 策略继续由管理员独立维护。
- 切换动作必须可重复执行、可从 `2.1.185` 切回 `2.1.173`，并避免部分成功导致新旧版本混用。
- 后端必须拒绝未知版本或不完整画像，不能允许前端提交任意字符串拼出协议画像。
- 版本画像体系必须支持后续新增版本、新请求特征、新遥测结构和新 endpoint 特征；新增版本应通过新增内置 profile 和显式测试矩阵完成，不能继续散落修改全局常量或临时 if/else。
- 版本切换不得记录 token、Cookie、Authorization、完整 prompt、完整响应正文或完整抓包内容。
- Settings 保存后必须热刷新，不要求重启服务；如账号批量更新失败，应返回明确错误并避免静默只更新 setting。

## Acceptance Criteria

- [ ] 管理后台 Settings 页面可以看到版本特征切换控件，并可在 `2.1.185` 与 `2.1.173` 间切换。
- [ ] 后端 settings API 只接受内置版本 key；提交未知版本返回 `{ error }` 形态的 4xx 错误。
- [ ] 新增版本画像时有单一注册入口，profile 必须显式声明请求画像、CCH/`cc_version` 画像、telemetry 画像、GrowthBook UA 和默认准入范围；缺字段无法通过单测或编译期校验。
- [ ] 切换到 `2.1.173` 后，新 `/v1/messages` Claude Code 请求的上游 `User-Agent`、billing header 版本、`cc_version` 后缀输入版本、CCH 输入规则和 telemetry env 版本字段均来自 `2.1.173` 画像。
- [ ] 切换到 `2.1.185` 后，上述字段全部恢复到 `2.1.185` 画像。
- [ ] 切换到 `2.1.173` 后，GrowthBook UA 使用 `Bun/1.3.14`，event logging / GrowthBook payload 不继续发送 `014c0e5` 引入的 `2.1.185` 专用结构。
- [ ] 切换到 `2.1.185` 后，GrowthBook UA 使用 `Bun/1.4.0`，event logging 不发送 email，`betas` 非空，`additional_metadata` 是 base64 JSON，env 包含 `shell` 与 `is_running_with_bun`，GrowthBook payload 使用 `forcedVariations`、数组 `forcedFeatures` 和 `url`。
- [ ] 切换后已有账号的 `canonical_env.version/version_base/build_time` 分布全部等于目标画像值，新创建账号也使用目标画像值。
- [ ] 切换后 `allowed_claude_code_versions` 被强制覆盖为目标画像默认范围；`allowed_user_agents` 保持切换前原值不变。
- [ ] 保存设置不需要重启，网关热路径读取到新画像。
- [ ] 单测覆盖版本画像解析、非法版本拒绝、账号 canonical env 批量同步、settings 热刷新、请求重写/telemetry 使用选中画像。
- [ ] 前端构建通过，后端 `cargo fmt --check`、`cargo test`、`cargo test cch` 通过。

## Notes

- 本任务是复杂跨层功能，需要补 `design.md` 和 `implement.md` 后再进入实现。
- 抓包结论只能记录脱敏摘要和字段差异，不提交完整抓包。

## Open Questions

- 当前无阻塞问题。
