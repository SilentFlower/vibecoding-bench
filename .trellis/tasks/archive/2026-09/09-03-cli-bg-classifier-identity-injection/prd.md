# 为 cli-bg 分类请求增加可选身份块注入

## Goal

为 Claude Code 后台 Agent 状态分类请求增加独立、默认关闭的身份块注入开关。在管理员选择真实透传且显式开启该开关时，对强特征命中的非 Haiku 分类请求补齐 Claude Code billing/CCH 归因块与官方身份块，修复分类器因切换到 Fable、Opus、Sonnet 等 premium 模型但省略标准 system 前缀而触发上游裸 429 的兼容问题，同时保留现有“透传 / 模拟”模式及其回滚能力。

## Background

- 当前 `intercept_cli_bg_status_classifier_mode` 支持 `passthrough | mock`，默认 `passthrough`；现有 detector 在 `cc2api/src/service/gateway.rs:4340` 只匹配 `x-app=cli-bg`、`claude-fable-5-1`、显式 `stream=false`、`max_tokens=3072`、单 system block 的已确认事故画像。
- Claude Code 2.1.257 当前二进制的后台分类器默认使用 small-fast 模型，但远端 `tengu_bg_classifier_config.useSmallFastModel` 可令其改用当前主模型；`max_tokens=3072` 与 `1024` 输出额度加 `2048` thinking 预算的非 small-fast 路径一致。
- `/root/project/claude-code/src/services/awaySummary.ts:49` 的早期同类辅助请求固定使用 `getSmallFastModel()`；`/root/project/claude-code/src/utils/model/model.ts:36` 证明该模型默认是 Haiku。
- `/root/project/claude-code/src/utils/sideQuery.ts:151` 表明内部 classifier 使用 `skipSystemPromptPrefix` 时会保留 billing attribution，但省略 `You are Claude Code, Anthropic's official CLI for Claude.` 身份块。这对 Haiku 可正常工作，但非 Haiku OAuth 请求可能返回无细节的 429。
- 抓包 `data/flows/7-12/9600/ea6d8e9bb665/http_capture.jsonl` 中有 4 次真实 Haiku 状态分类请求：`x-app=cli`、省略 `stream`、`max_tokens=1024`、system 为 billing + classifier 两块、无身份块，均返回 200。
- Fable 5.1 主请求抓包的 system 顺序是 billing、identity、其他 prompt；身份块本身无 `cache_control`。因此分类器注入应复用 billing、identity、classifier 的官方组装顺序。
- cc2api 未把 Haiku 自动映射成 Fable 5.1；vibecoding-bench 只通过 `--model` 选择主模型，不设置 `ANTHROPIC_SMALL_FAST_MODEL`。

## Requirements

### R1. 保留现有处理模式

- 保留 setting `intercept_cli_bg_status_classifier_mode` 及 `passthrough | mock` 两个值，默认仍为 `passthrough`。
- Settings 页面继续提供“透传 / 模拟”二选一控件。
- 现有 mock 和 passthrough 正文旁路只继续处理当前已确认的 Fable 5.1 事故画像，不因新增通用 detector 自动扩大本地模拟范围。
- `mock` 命中后仍在账号选择和上游调用之前返回本地 Anthropic Message；身份注入开关在 `mock` 模式下不生效。

### R2. 独立身份注入开关

- 新增全局 setting `intercept_cli_bg_status_classifier_identity_injection_enabled`，只接受字符串 `true | false`，默认 `false`。
- 新数据库写入默认值；旧数据库迁移只补缺失 key，不覆盖管理员已有值。
- `/admin/settings` 返回该默认值、拒绝非法值，并在保存后热刷新 Gateway 内存配置，无需重启。
- Settings 页面在后台状态分类区域增加独立布尔开关；关闭时显示“保持原始身份块”，开启时显示“缺失时注入身份块”，并说明开启后会一并补齐缺失的 billing/CCH 归因块。
- 当处理模式为 `mock` 时，UI 明确显示注入不会参与本地模拟；切回 `passthrough` 后保留此前保存的开关值。

### R3. 通用分类请求识别

- 新增只服务于身份注入的通用 classifier detector，不替换现有窄模式 detector。
- wire 特征要求：精确 `/v1/messages`、`ClientType::ClaudeCode`、`x-app` 为 `cli-bg` 或 `cli`、请求为非流式；`stream=false` 和省略 `stream` 都视为非流式，`stream=true` 必须排除。
- 不写死模型 ID、`max_tokens` 或完整 prompt hash，以覆盖 Fable、Opus、Sonnet 及未来非 Haiku 模型，同时兼容 Haiku 抓包的 `1024` 与 Fable 抓包的 `3072`。
- system 必须是数组，并且恰好包含一个带 `cache_control.type=ephemeral` 的 classifier text block；该 block 同时包含 Agent 状态分类用途、四状态集合、仅输出 JSON 的约束及 `state/detail/tempo/needs/output` 字段标记。
- classifier block 之外只允许最多一个已识别的 billing attribution block和最多一个精确 Claude Code identity block；出现重复块、普通 prompt、工具说明或其他未知 system block 时不得命中。
- messages 必须恰好一条 user 消息，content 为字符串、单一 text block 或单元素 text 数组；文本以 `Current state:` 开始，并包含 `Tool calls so far:`、`User's most recent ask:` 与 `Assistant message tail`。
- 普通主请求、旧 Auto Mode XML classifier、Haiku probe、Warmup、Suggestion、assistant prefill、仅在 transcript 中复制分类提示词的请求不得误命中。

### R4. 身份与归因前缀补齐

- 仅当模式为 `passthrough`、新开关开启、通用 detector 命中且模型不是 Haiku 时进入前缀补齐；是否已有 billing 或 identity 只决定具体补齐动作，不影响资格判断。
- Haiku 判断复用现有 `is_haiku_model_id` 语义；模型 ID 大小写规整后包含 `haiku` 即视为 Haiku，永不注入。
- system 缺少 billing attribution 时，复用 API 模式的 billing 构造能力，按所选账号的 Claude Code 版本画像生成标准 billing block，并在最终正文上生成有效 CCH；不得复制另一账号或入站请求中的身份值。
- system 已有 billing attribution 时保留其结构；其中存在 `cch=` 时，必须在全部正文改写结束后按所选账号的版本画像刷新 CCH。
- 身份块文本精确为 `You are Claude Code, Anthropic's official CLI for Claude.`，不添加 `cache_control`，不添加 expansion block。
- system 缺少精确身份块时插入；最终 system 顺序固定为 billing、identity、classifier。
- system 已含精确身份块时必须幂等放行，不重复插入。

### R5. 透传正文边界与 CCH

- 新开关关闭时，所有请求行为与当前版本一致。
- 开关开启且命中注入时，继续执行账号选择、OAuth、sticky/RPM/concurrency、账号 proxy/TLS、header 画像、401 恢复和 429 换号重试。
- 正文只允许现有 `metadata.user_id` / upstream session 身份映射、缺失 billing block 的标准生成、缺失 identity system block 的插入，以及最终 CCH 计算或刷新；不得执行普通 system 环境改写、message cache_control 重打、TTL 覆盖、disabled-thinking 改写、字段重排或其他 prompt 清洗。
- 缺少 billing 时，生成的标准 billing 必须包含最终有效 CCH；已有 billing 且包含 `cch=` 时必须在最终序列化正文上重新计算。已有 billing 但本身不含 `cch=` 时不擅自改造成另一种历史格式。
- 保留原 classifier block、user message、thinking、fallbacks、cache_control 及未知顶层字段；不承诺保留原始 JSON 空白。

### R6. 日志与隐私

- 通用 detector 和注入日志只记录模式、模型、是否 Haiku、是否已有 identity、是否有 billing/CCH、system/message 数量、请求尺寸、短 hash、是否注入和 `proxy_configured` 等摘要。
- 不记录完整 system/user prompt、Authorization、Cookie、OAuth token、代理 URL、邮箱、账号 UUID 或 metadata 映射原值。
- 命中身份注入的请求继续使用 `SummaryOnly` 请求捕获策略，避免现有非流式/429全文日志记录分类内容。

### R7. UI 与文档

- Settings 控件使用后端真实 key，布尔值以字符串保存，加载非法/缺失值时回退 `false`。
- 更新后台状态分类说明，区分：处理模式决定现有 Fable 5.1 事故画像是透传还是模拟；身份注入开关只在透传的通用非 Haiku classifier 上生效。
- 更新需要管理员了解的新 setting 文档，不改变其他模型、1M、Fable 周配额和缓存配置说明。

## Acceptance Criteria

- [ ] 新旧数据库均得到 `intercept_cli_bg_status_classifier_identity_injection_enabled=false`，已有值不被迁移覆盖。
- [ ] `/admin/settings` 返回默认 `false`，接受 `true/false`、拒绝其他值，更新后 Gateway 无需重启即可读取新值。
- [ ] Settings 页面保留“透传 / 模拟”切换，并提供独立、默认关闭的身份注入开关；保存、重新加载和模式切换后状态一致。
- [ ] 现有 Fable 5.1 `cli-bg + stream=false + max_tokens=3072` 事故画像仍命中原 mode detector；原 mock 响应和 passthrough 旁路行为不回归。
- [ ] 通用 detector 能识别 Fable 5.1 单 classifier block 画像，以及 Haiku 抓包的 `x-app=cli`、省略 stream、billing + classifier 画像。
- [ ] 通用 detector 不命中流式请求、API UA、错误 path/x-app、普通主请求、含未知 system block、多消息、多 user content block、缺少任一稳定 prompt/user 标记的请求。
- [ ] 开关关闭时非 Haiku classifier 正文不新增 billing 或 identity；开启且模式为 passthrough 时，Fable/Opus/Sonnet classifier 均进入前缀补齐且补齐结果幂等。
- [ ] Haiku classifier 永不补齐；已有 identity 的非 Haiku classifier 不重复插入；mock 模式不进入补齐或上游链路。
- [ ] 缺少 billing 时生成标准 billing 和有效 CCH；缺少 identity 时插入精确身份块；最终顺序为 billing、identity、classifier，identity 不带 cache_control，且不生成 expansion。
- [ ] 已有 billing/CCH 时保留 billing 结构并刷新 CCH；已有 billing 但无 CCH 时不新增 CCH。
- [ ] 补齐后 metadata/session 仍按代理账号映射，classifier/user/thinking/fallbacks/cache_control 保持原值；生成或刷新后的 CCH 通过 2.1.257 CCH 测试。
- [ ] 命中请求只产生脱敏摘要日志，并使用 `SummaryOnly` 捕获策略。
- [ ] `cargo fmt --check`、定向 settings/detector/rewriter/gateway 测试、`cargo test`、`cargo test cch` 和 `cc2api/web` 的 `npm run build` 全部通过。

## Out of Scope

- 不把所有缺少 system identity 的普通 `/v1/messages` 请求都改写；只有通用 classifier 强特征命中才处理。
- 不修改 Claude Code 客户端、vibecoding-bench worker 环境变量或强制 `ANTHROPIC_SMALL_FAST_MODEL=haiku`。
- 不扩大现有 mock 到 Haiku、Opus、Sonnet 或其他未来模型，不改变 mock 分类算法和响应协议。
- 不修改 Fable 5 / Fable 5.1 模型画像、`[1m]` 处理、周配额、thinking 全局策略、缓存策略或全局 429 重试。
- 本任务不自动部署生产环境；部署需在本地检查完成后按单独的明确指令执行。
