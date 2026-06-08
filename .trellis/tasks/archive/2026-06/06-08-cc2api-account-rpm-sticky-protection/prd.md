# cc2api 账号级 RPM 粘性保护

## Goal

为 cc2api 增加账号级 RPM 削峰能力，参考 sub2api 的账号 RPM 思路，在请求发往 Anthropic 上游之前限制单账号每分钟请求突发，减少真实 429 和“短冷却”反复出现。同时必须保护 Claude Code 粘性会话：RPM 不应随意把已有会话切到其他账号，避免 Anthropic prompt cache 因账号空间变化而重写。

## Background / Known Context

- us-ai 线上已确认出现上游真实 429，随后 cc2api 将账号标记为“速率限制（短冷却）”。这不是本地限流误判，而是上游返回 `rate_limit_error`。
- cc2api 当前主要有账号并发槽位和 429 后冷却；并发只能限制“同时跑几个请求”，不能限制“一分钟内总共打多少请求”。
- Claude Code 并行 tool / subagent 会在短时间内产生大量小请求。请求很快结束并释放并发槽位时，单账号 RPM 仍可能过高。
- sub2api 的账号 RPM 是账号级总请求数，Redis key 形态为 `rpm:{accountID}:{minuteTimestamp}`，不包含模型维度。
- sub2api 的模型相关限流是另一套 `model_rate_limits`，用于某个模型/模型族被上游限流后的临时不可调度；它不参与账号 RPM 计数。
- 本任务优先解决账号级突发削峰，不做模型级 RPM 细分。

## Assumptions

- 账号级 RPM 用于保护同一 Anthropic OAuth/SetupToken 账号，不区分 Sonnet/Haiku/Opus。
- 真实 Claude Code 会话的 prompt cache 与账号强相关；已有粘性会话被 RPM 切号会显著增加缓存重建概率。
- 单账号场景下，RPM 达到阈值后等待比继续打上游更可控；多账号场景下，新会话可跳过高 RPM 账号。
- RPM 计数失败时应失败开放或降级为仅日志告警，不能因为 Redis/内存计数异常直接阻断正常请求。
- cc2api 管理端已有 Vue 账号页面，适合在账号列表/编辑区域展示 RPM 配置和当前分钟状态。

## Open Questions

- 粘性会话超过账号 RPM 后的最大等待时间需要定一个默认值；推荐先用短等待上限，超时后返回本地 429，而不是切号。

## Requirements

- 增加账号级 RPM 配置，默认关闭，配置值为 0 时保持现有行为。
- RPM 计数应按账号和分钟窗口聚合，不按模型拆分。
- 新会话或无粘性请求可根据 RPM 状态跳过高负载账号，选择其他可用账号。
- 已绑定粘性会话命中原账号时，RPM 不得直接触发切号。
- 粘性账号达到 RPM 阈值时，应优先等待/排队削峰；只有账号不可调度、上游 429 后冷却、手动停用、OAuth 无效、5h/7d 撞墙等硬失败时才允许解除粘性或换号。
- RPM 逻辑需要和现有并发槽位兼容，避免拿到并发槽位后长时间等待 RPM 造成槽位浪费。
- 日志需要可读，能看出账号、当前 RPM、限制、会话是否粘性、动作是 allow/wait/skip/reject。
- 管理端账号 API 需要返回账号 RPM 配置、当前分钟已用数量、限制值、剩余数量和是否已满。
- 管理端账号页面需要能配置账号 RPM，并直观展示当前分钟 `已用 / 总量`，最好同时展示剩余数量或已满状态。
- 现有短冷却逻辑仍保留，用于处理上游实际 429；账号 RPM 是前置削峰，不替代上游错误分类。

## Acceptance Criteria

- [ ] 账号可配置 RPM 限制，默认关闭后行为与当前版本一致。
- [ ] 账号列表或账号详情能展示当前分钟 RPM `已用 / 总量`；关闭 RPM 时显示为未限制或等价状态。
- [ ] 前端可编辑账号 RPM 限制，保存后后端调度立即按新配置生效。
- [ ] RPM 计数按 `account_id + minute` 统计，同一账号下不同模型请求共享同一个 RPM 预算。
- [ ] 非粘性请求在候选账号 RPM 已满时会跳过该账号或等待，不主动制造上游 429。
- [ ] 粘性请求命中原账号时，RPM 超限不会直接切到另一个账号导致缓存空间变化。
- [ ] 单账号场景下 RPM 超限有明确等待/拒绝行为和可读日志。
- [ ] 多账号场景下新会话能优先分配到 RPM 未满账号。
- [ ] 429 短冷却、5h/7d 撞墙、手动停用、OAuth 失效等硬失败仍能让账号不可调度。
- [ ] 单元测试覆盖账号 RPM 计数、粘性不切号、新会话跳过、关闭 RPM 的回归行为。
- [ ] 关键路径验证命令通过。

## Out of Scope

- 不实现按模型独立 RPM，例如 Sonnet RPM 和 Haiku RPM 分开计数。
- 不改变 Anthropic prompt cache 断点策略。
- 不移除现有 429 短冷却逻辑。
- 不引入跨账号共享 prompt cache 的假设。
- 不做 RPM 历史趋势图、分钟级折线图或长期统计报表；本任务只展示当前分钟状态。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
