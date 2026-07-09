# cc2api Fable 配额耗尽时粘性会话智能切换

## 目标

当同一 Claude Code 粘性会话绑定的账号已耗尽 Fable 周用量时，cc2api 能识别“当前模型在该账号上不可用”，自动避开该账号并切换到仍有 Fable 配额的账号，同时保留 RPM 饱和时的既有粘性会话保护语义。

核心问题：用户有两个账号，其中一个账号 Fable 用量耗尽后，粘性会话仍持续命中该账号，导致请求不能智能切到另一个可用账号。

## 背景

- 现有账号选择会优先读取 `session_hash -> account_id` 的粘性绑定；只检查账号是否可调度、是否被 token 规则排除、是否在 allowed 列表内。证据：`cc2api/src/service/account.rs:705`、`cc2api/src/service/account.rs:718`。
- 非粘性新会话会过滤当前分钟 RPM 已满账号，但没有模型级 Fable 配额过滤。证据：`cc2api/src/service/account.rs:756`。
- Gateway 主请求循环在 429 后会排除当前账号并重试下一个账号。证据：`cc2api/src/service/gateway.rs:1200`、`cc2api/src/service/gateway.rs:1708`。
- 429 分类当前只区分 `seven_day` 和 `five_hour`，没有 `seven_day_fable` 模型级窗口。证据：`cc2api/src/service/account.rs:1520`、`cc2api/src/service/account.rs:1530`。
- 429 文案含 `credit` 时当前会当成单请求级拒绝并透传；这对 Sonnet 长上下文 credits 是合理防护，但 Fable 周配额耗尽也可能带有 fallback/credit 相关文案，存在被误判为“无需换号”的风险。证据：`cc2api/src/service/account.rs:1277`。
- Fable 周用量已经被规范化为稳定字段 `seven_day_fable`；规范明确 Fable 周用量不能从普通 `anthropic-ratelimit-unified-*` 响应头可靠推导，OAuth Fable 2xx 响应结束后会异步刷新 usage。证据：`.trellis/spec/cc2api/backend/service-architecture.md:149`、`.trellis/spec/cc2api/backend/service-architecture.md:157`、`cc2api/src/service/account.rs:1011`、`cc2api/src/service/gateway.rs:4878`。
- 既有规范明确：RPM 饱和下，非粘性可以换号，粘性请求不得随意切号。证据：`.trellis/spec/cc2api/backend/service-architecture.md:65`、`.trellis/spec/cc2api/backend/service-architecture.md:66`。
- Fable 主请求的模型 ID 稳定为 `claude-fable-5`；`claude-fable-5[1m]` 在主 `/v1/messages` 请求中也归一到 `claude-fable-5`。证据：`.trellis/tasks/archive/2026-06/06-12-cc2api-2-1-173-packet-diff/research/cc2api-2-1-173-capture-diff.md:103`。
- 新增全局 setting 必须同步默认值、DB 默认插入、管理 API 校验、Gateway 内存热缓存和 Settings 页面控件。证据：`.trellis/spec/cc2api/backend/settings-database.md:21`、`.trellis/spec/cc2api/backend/service-architecture.md:203`。

## 第一性原则

- 粘性会话的价值是保护 prompt cache、减少同一会话在多个账号之间无意义漂移。
- Fable 周配额耗尽不是瞬时 RPM，也不是本地队列压力；它表示“该账号暂时无法服务当前模型”。
- 模型级不可用的优先级应高于粘性绑定，否则用户有可用账号也无法继续请求。
- 不能把 Fable 模型级配额满简单写入账号全局 `rate_limit_reset_at`，否则会错误影响同账号的非 Fable 模型请求。

## 技术方案约束

- 在账号选择阶段引入“请求模型上下文”，至少包含 `model_id` 是否为 Fable。
- 对 Fable `/v1/messages` 请求，在粘性命中前检查该账号的 `usage_data.seven_day_fable` 是否明确耗尽且 reset 仍在未来：
  - 未满：保留粘性绑定。
  - 已满：本轮临时忽略该 sticky 账号，把该账号加入本轮排除列表或视为不可用，继续选择其他账号；只有找到新账号并真正承载请求后，才覆盖旧 session 绑定。
- 对非粘性 Fable 请求，优先过滤掉 Fable 周用量明确已满账号；如果所有候选都满，则返回本地 429，并尽量用最早 `resets_at` 构造可理解错误。
- 对 Fable 请求的上游 429，分类逻辑应能识别 `seven_day_fable`，并让当前请求排除该账号重试下一个账号；不能因为响应体含 `credit` 就直接透传。
- 当 Fable 429 发生但本地 usage 缓存还没显示 `seven_day_fable >= 100` 时，不在 Gateway 热路径同步调用 OAuth usage；本轮继续按 429 排除当前账号并重试其他账号，同时后台触发一次节流的 usage 刷新，供后续请求选择前识别。
- 不使用“接近耗尽”的过滤线；未明确耗尽的账号不因 `seven_day_fable` 接近满而被硬过滤。
- 增加全局开关控制该策略，关闭时保持现有粘性会话和 429 行为，不执行 Fable 模型级 sticky 打破、预过滤或重绑。
- Settings 页面将开关放在“评分权重”卡片内的“Fable 配额切换”小节，作为账号调度策略的一部分。
- 保留当前 RPM 粘性语义：RPM 饱和仍不作为打破粘性的理由。

## 需求

- R1：Fable `/v1/messages` 请求必须能识别账号级 `usage_data.seven_day_fable` 明确耗尽且 `resets_at` 在未来的状态。
- R2：Fable 请求命中粘性账号且该账号 Fable 周配额已满时，必须打破本次粘性绑定并尝试选择其他允许账号。
- R3：Fable 请求重新选择账号后，应把新的实际承载账号绑定回 session，避免下一次仍命中旧的已满账号。
- R4：非粘性 Fable 请求应优先避开 Fable 周配额已满账号；当所有允许账号都已满时，应返回明确的本地 429 或透传最后一个 429，但不能无限重试。
- R5：Fable 请求上游返回 429 时，若最新 usage 或账号缓存能判断 `seven_day_fable` 已满，应按模型级不可用处理并允许换号重试。
- R6：Fable 模型级配额满不得污染账号全局 `rate_limit_reset_at`，除非同时确认通用 `five_hour` 或 `seven_day` 撞墙。
- R7：保留 RPM 粘性语义：粘性账号 RPM 饱和时仍按现有等待/本地 429 处理，不把 RPM 饱和作为模型级换号理由。
- R8：保留 SetupToken、`count_tokens`、bootstrap、非 Fable 请求的现有行为。
- R9：补充后端测试覆盖 Fable 模型级配额、粘性解绑重选、429 分类和 RPM 粘性不回归。
- R10：新增全局配置开关，用于启用/关闭 Fable 模型级配额 sticky fallback 策略。
- R11：全局开关必须支持管理端读取、写入和热刷新；写入后无需重启即可影响 Gateway 热路径。
- R12：全局开关关闭时，不应执行本任务新增的 Fable sticky 打破、账号预过滤、模型级 429 换号或重绑逻辑。
- R13：Fable 429 处理不得在 Gateway 热路径同步调用 OAuth usage API；可以触发已有节流保护下的后台 usage 刷新。
- R14：如果 Fable sticky 账号已满但没有任何可用替代账号，不应删除旧 sticky 绑定；只有替代账号实际承载请求后才覆盖绑定。

## 验收标准

- [ ] 两个 OAuth 账号中，账号 A 的 `usage_data.seven_day_fable.utilization >= 100` 且 reset 在未来，session 已粘到 A；新的 Fable `/v1/messages` 请求应避开 A 并选择账号 B。
- [ ] 上述重选成功后，session 绑定更新为账号 B；下一次同 session Fable 请求不再命中账号 A。
- [ ] 如果账号 A 已满且没有可用替代账号，本轮返回 429，但旧 session 绑定仍保留；配额 reset 后可继续按原绑定恢复。
- [ ] 如果账号 A 只有 `seven_day_fable` 满、通用 `five_hour` / `seven_day` 未满，非 Fable 请求仍可使用账号 A。
- [ ] 如果所有允许账号的 `seven_day_fable` 都已满，返回 429，且不会在账号之间无限循环。
- [ ] Fable 429 中即使响应体包含 `credit`，只要 `seven_day_fable` 判断为满，也不会被当成单请求级拒绝直接透传。
- [ ] Fable 429 且本地 `seven_day_fable` 尚未满时，本次请求不阻塞等待 OAuth usage；应继续按 429 排除当前账号重试，并触发后台 usage 刷新。
- [ ] 粘性账号仅 RPM 饱和时，仍保持现有等待/本地 429 行为，不因为本任务改动而切号。
- [ ] 管理端 Settings 提供全局开关；保存后 Gateway 热路径按新值生效。
- [ ] Settings 页面开关位于“评分权重”卡片内“Fable 配额切换”小节；开启显示“已启用”，关闭显示“保持粘性”。
- [ ] 全局开关关闭时，存在 `seven_day_fable >= 100` 的粘性账号仍按旧逻辑命中该账号，不执行本任务新增切换行为。
- [ ] `cd cc2api && cargo fmt --check` 通过。
- [ ] `cd cc2api && cargo test` 通过；如环境限制无法全量完成，至少运行账号调度、gateway 429、usage 相关定向测试并说明原因。

## 非目标

- 不改变 Fable 请求画像、CCH、beta、fallbacks 或 `claude-fable-5[1m]` 归一规则。
- 不把模型级配额状态落库为新的账号字段，优先复用 `usage_data` 与必要的进程内短期状态。
- 不改变 token allowed/blocked account 规则。

## 已确认决策

- D1：当粘性会话的 Fable 账号已满时，允许“主动打破粘性并重绑到可用账号”作为默认行为。
  - 理由：模型级不可用比 sticky 更高优先级；否则用户有第二个可用账号也无法继续。
  - 代价：这一次会话可能损失原账号上的 prompt cache，但换来请求可用性。
- D2：不使用 `97%` 这类“接近撞墙”的 Fable 硬过滤线；接近满但未明确耗尽时，不主动打破粘性。
  - 理由：避免过早浪费仍可用的 Fable 配额，也避免因为 usage 数据略有延迟就频繁切号。
  - 代价：临近耗尽账号可能仍承担最后几次请求，真正耗尽后再切号。
- D3：当 `usage_data.seven_day_fable.utilization >= 100` 且 `resets_at` 在未来时，可以视为 Fable 明确耗尽，并在账号选择前打破粘性或过滤该账号。
  - 理由：后台 usage 已经刷新到 100% 后，不需要再让下一次请求先撞一次上游 429。
  - 代价：如果 usage 缓存有短暂误差，可能提前切一次；该风险比 `97%` 阈值小。
- D4：新增全局配置开关控制本策略。
  - 理由：这是粘性会话行为变更，管理员需要保留回退到旧行为的能力。
  - 代价：需要同步后端 settings、Gateway 热缓存和前端 Settings 控件，任务范围扩大为跨后端和前端。
- D5：全局配置开关默认开启。
  - 理由：该策略修复“有可用账号却无法自动切换”的可用性问题，默认开启能让升级后的用户直接受益。
  - 代价：升级后默认行为会变化；管理员可通过开关回退旧行为。
- D6：Fable 429 后不在 Gateway 热路径同步刷新 usage。
  - 理由：避免 429 处理路径阻塞外部 OAuth usage API，也避免放大 usage API 压力。
  - 代价：第一次遇到耗尽时可能仍依赖本轮 429 排除账号重试；后台刷新完成后，后续请求才能在选择前直接识别耗尽账号。
- D7：如果 Fable sticky 账号已满但没有任何可用替代账号，不立即删除旧 sticky 绑定；只有新账号实际承载请求后才覆盖绑定。
  - 理由：没有替代账号时删除 sticky 没有可用性收益，反而会让配额 reset 后丢掉原会话绑定和潜在 cache。
  - 代价：所有账号都满期间，每次请求都会重新判断一次 sticky 账号已满。
- D8：全局开关放在 Settings 页“评分权重”卡片内，作为“Fable 配额切换”小节展示。
  - 文案：开启显示“已启用”，关闭显示“保持粘性”；说明为“Fable 周用量明确耗尽时，允许打破粘性会话并切换到其他可用账号；RPM 饱和仍保持粘性等待。”
  - 理由：该功能属于账号调度策略，和评分权重同属选择账号行为；放进 429 观测或 bootstrap 会误导用户。
  - 代价：评分权重卡片会稍微变长。

## 待决策问题

- 暂无阻塞实现的待决策问题。
