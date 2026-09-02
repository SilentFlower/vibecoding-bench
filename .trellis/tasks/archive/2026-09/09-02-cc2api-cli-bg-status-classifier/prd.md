# 适配 Claude Code 后台状态分类请求

## Goal

为 Claude Code 2.1.257 的 `cli-bg` Agent 状态分类请求增加全局“放行 / 模拟”模式。默认放行时仍完整经过 cc2api 的账号、OAuth、请求头画像、TLS/账号代理和重试链路，但绕过会改变该辅助请求正文指纹的通用改写，消除当前集中出现的上游 429；模拟模式返回 Claude Code 可解析的本地状态分类结果。

## Background

- 线上近 6 小时观测到 288 条同形 429，均为 `model=claude-fable-5-1`、非流式、`max_tokens=3072`、`x-app=cli-bg`、`X-Stainless-Retry-Count=0`。
- 429 来自 Anthropic 上游，错误体仅为通用 `rate_limit_error: Error`。四个活跃 OAuth 账号各出现 72 次，Fable 周用量低于 50% 控制线，因此不是单账号、全局账号配额或 cc2api 本地白名单拒绝。
- 该请求的 system 提示词要求把 Agent 尾部状态分类为 `working / blocked / done / failed`，并只输出固定 JSON；user 内容包含 `Current state:` 与 `Assistant message tail`。
- 当前线上 `cache_control_ttl_rewrite=1h`、`message_cache_control_rewrite=sub2api`。进入普通 `/v1/messages` 改写后，system 的 ephemeral cache_control 被补成 `ttl=1h`，messages 又被增加缓存断点；这两个变化与真实 Claude Code 请求形状不一致。
- 现有 Auto Mode classifier 只识别 XML `<block>` / `<severity>` 协议和其他 token 范围，不能复用其检测或 mock 响应。
- 用户明确调整验证顺序：先实现，再仿真 Claude Code 请求；验收请求必须经过 cc2api 自身代理链路和所选账号的 `proxy_url`，不允许直接绕过代理请求 Anthropic，也不能用本地模拟结果替代真实放行验证。

## Requirements

### R1. 强特征识别

- 只在精确 `/v1/messages`、`ClientType::ClaudeCode`、原始 `x-app=cli-bg`、精确 `model=claude-fable-5-1`、非流式、`max_tokens=3072` 时继续检查正文。
- system 必须是唯一 text block，带 `cache_control.type=ephemeral`，并同时包含状态分类用途、四状态集合和“仅返回 JSON”的稳定标记。
- messages 必须恰好一条 user 消息且 content 为单一文本；内容以 `Current state:` 开始，并同时包含 `Tool calls so far:`、`User's most recent ask:` 与 `Assistant message tail`。
- 普通 Fable 主请求、Fable 5、带 `[1m]` 的模型 ID、旧 Auto Mode classifier、仅在历史 transcript 中出现相似文字的请求不得误命中。
- 检测不得依赖完整 prompt 逐字相等、完整 hash 或精确字符数，避免官方文案小改导致失效；也不得只依赖 `max_tokens`、模型或单个关键词。

### R2. 全局模式配置

- 新增 setting `intercept_cli_bg_status_classifier_mode`，只允许 `passthrough` 和 `mock`。
- 默认值为 `passthrough`；旧数据库迁移只补缺失 key，不覆盖管理员已有值。
- `/admin/settings` 必须返回默认值、拒绝非法值，并在保存后热刷新 Gateway 内存配置。
- Settings 页面提供“放行”和“模拟”二选一控件，保存值必须使用后端真实 key。

### R3. 放行模式

- 命中后仍执行账号选择、sticky/RPM/concurrency admission、OAuth token 获取、Claude Code 2.1.257 header 画像、账号 proxy/TLS、上游转发、401 恢复和 429 换号重试。
- 对正文只保留代理账号所需的 `metadata.user_id` / upstream session 身份映射；不得执行空 text 清理、system 环境/billing 改写、Git reminder 清洗、currentDate 治理、message cache_control 重打、ephemeral TTL 覆盖、disabled-thinking 改写、API body 排序或 CCH 计算/刷新。
- 必须保留客户端原始 `x-app=cli-bg` 和该请求已有的 system/message/cache_control/thinking 形状；不得新增 message cache_control，也不得给原始 ephemeral cache_control 增加 `ttl`。
- 命中日志只能记录模式、模型、尺寸、消息数、重试计数、短 hash 和 `proxy_configured` 等脱敏摘要，不输出完整 prompt、代理 URL、token、Authorization、Cookie 或账号标识映射。

### R4. 模拟模式

- 命中后在账号选择、RPM、并发槽和上游请求之前返回 HTTP 200，不消耗账号额度。
- 返回标准 Anthropic Message JSON envelope；`content[0].text` 必须是可再次解析的 JSON 字符串，字段符合请求约定的 `state/detail/tempo/needs/output`。
- 本地分类只读取唯一 user 消息中的状态摘要与 assistant tail，优先处理明确的 blocked / working / done / failed 标记，再回退到 `Current state:`；无法可靠解析时保守返回 `working`，避免误报完成或无故通知用户。
- `needs` 仅在 blocked 时出现；working 时 `output` 为空对象；done/failed 可以包含简短 `output.result`。

### R5. 回归边界

- 不改变现有 Warmup、Suggestion、Haiku probe、Auto Mode classifier Stage 1/2 和 assistant prefill 的检测、模式或响应协议。
- 不改变 Fable 5 / Fable 5.1 模型画像、CCH、1M allowlist、周配额、上游首字节超时或全局 429 重试策略。
- 普通 Claude Code `/v1/messages` 继续使用管理员现有的缓存、TTL、thinking 和 currentDate 设置。

### R6. 代理链路验证

- 本地测试和构建通过后，按 cc2api 发布流程构建并部署新镜像到 `us.flower-cli.com`。
- 生产验证通过管理 API 创建一次性网关 token，并用 `allowed_accounts` 固定一个已确认 `proxy_url` 非空的活跃账号；token 只保存在远端进程变量中，不得打印、写入任务文件或落入 shell tracing，验收后立即删除。
- 仿真请求使用 Claude Code 2.1.257 UA、`x-app=cli-bg`、非流式、`max_tokens=3072`、Fable 5.1 和合成的脱敏状态分类正文，经 `https://us.flower-cli.com/v1/messages` 进入 cc2api。
- 验收前临时关闭全文 429/非流请求日志或将 body limit 置 0，验收后恢复原值，避免合成 prompt 之外的并发请求正文继续落盘。
- 放行验收必须以上游真实非 429 响应、命中旁路日志和 `proxy_configured=true` 为依据；本地 `mock` 的 HTTP 200 不能算作放行成功。若仍返回 429，应继续对比最终出站摘要并修正旁路范围，不把任务标记完成。

## Acceptance Criteria

- [ ] 新数据库和旧数据库迁移后的 `intercept_cli_bg_status_classifier_mode` 均默认为 `passthrough`，管理员已有合法值不被覆盖。
- [ ] 管理 API 接受 `passthrough` / `mock`、拒绝其他值，并在更新后无需重启即可改变 Gateway 行为。
- [ ] Settings 页面可在“放行 / 模拟”间切换，加载、保存和重新加载均与后端一致。
- [ ] Fable 5.1 的真实 `cli-bg` 状态分类最小样本命中；普通 Fable 主请求、Fable 5、`[1m]`、旧 XML classifier、错误 path/UA/x-app/stream/max_tokens 和只含局部关键词的请求均不命中。
- [ ] 放行模式的最终正文保留原 system cache_control 且无新增 `ttl`，messages 无新增 cache_control，thinking 与其他业务字段保持原形；只允许代理账号身份/session 映射发生变化。
- [ ] 放行模式仍使用 cc2api 账号 OAuth、header 画像、账号 proxy/TLS、RPM/concurrency 和上游 429 重试链路。
- [ ] 模拟模式返回 HTTP 200 Anthropic Message envelope，`content[0].text` 是符合状态分类 schema 的 JSON，且不进入账号选择、RPM、并发槽或上游。
- [ ] `cargo fmt --check`、定向 classifier/settings/rewriter 测试、`cargo test`、`cargo test cch` 与 `cc2api/web` 的 `npm run build` 全部通过。
- [ ] 新镜像部署后服务健康、setting 为 `passthrough`；仿真 Claude Code 请求完整经过 `https://us.flower-cli.com` 和 `proxy_url` 非空的固定账号，获得真实非 429 响应，日志显示命中正文旁路且不含敏感内容。
- [ ] 验收结束后一次性 token 已删除、日志设置已恢复、生产模式保持 `passthrough`；不以生产 `mock` 作为放行验收结果。

## Out of Scope

- 不直接使用账号 OAuth token 绕过 cc2api 或账号 `proxy_url` 请求 Anthropic。
- 不自动开放 Fable 5 / Fable 5.1 `[1m]`，不修改账号 `allow_1m_models`。
- 不修改旧 Auto Mode classifier 的 XML 协议或四种现有模式。
- 不承诺消除 Anthropic 的所有上游限流或零首字节故障；本任务只处理该强特征辅助请求因 cc2api 正文改写造成的兼容问题。
- 不提交完整抓包、完整真实 prompt、Authorization、Cookie、API token、OAuth token、代理 URL、邮箱或账号 UUID 映射。
