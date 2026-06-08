# cc2api 账号级 RPM 粘性保护设计

## Technical Design

本任务在 cc2api 的账号调度链路中增加一层“账号级 RPM admission control”。它位于账号选择之后、真实上游请求之前，用来削平单账号一分钟内请求突发。它不替代现有并发槽位，也不替代上游 429 后的短冷却。

设计边界：

- RPM 维度：`account_id + minute`，不包含模型。这个行为对齐 sub2api 的账号 RPM：sub2api Redis key 为 `rpm:{accountID}:{minuteTimestamp}`。
- 配置维度：账号级 `rpm_limit` 或等价字段，默认 `0` 表示关闭。
- 生效对象：Anthropic OAuth/SetupToken 账号。其他账号类型默认旁路。
- 粘性约束：已绑定 session 的请求不能因为 RPM 满而直接切账号。

账号选择分两类：

1. 粘性会话：
   - 若 session 已绑定账号且账号仍可调度，继续使用该账号。
   - 若账号 RPM 未满，直接进入后续流程。
   - 若账号 RPM 已满，进入短等待或本地 429，不把请求切到其他账号。
   - 只有账号硬不可用时才允许清理/绕过粘性绑定，例如手动停用、OAuth 无效、5h/7d 撞墙、上游明确冷却。

2. 非粘性请求 / 新会话：
   - 在候选账号评分前后加入 RPM 可调度性判断。
   - RPM 未满账号优先进入评分。
   - RPM 已满账号从普通候选中跳过。
   - 如果所有账号都 RPM 已满，可以等待最近窗口释放，或返回本地 429；MVP 推荐有限等待后返回本地 429。

## Counter Contract

需要给现有 `CacheStore` 增加 RPM 相关能力，Redis 和内存实现都要支持：

- 获取当前账号当前分钟 RPM。
- 原子递增当前账号当前分钟 RPM，并设置短 TTL。
- 可选：尝试预占一个 RPM 名额，超过限制时不增加计数。

为了避免“先发上游后计数”导致突发继续打到上游，cc2api 更适合在请求发上游前做预占。请求失败是否回滚需要谨慎：为了保护上游，MVP 可以不回滚或仅对本地改写前失败回滚；这会略保守，但不会让 RPM 削峰失效。

## Relationship With Existing Limits

- 并发槽位：控制同时活跃请求数。
- 账号 RPM：控制一分钟内请求总数。
- 短冷却：处理已经发生的上游 429。
- 5h/7d 用量撞墙：继续由现有 usage 分类负责。
- 模型级限流：本任务不新增。若未来需要，可作为独立 `model_rate_limits` 或 `account_id + model + minute` 机制，不混入本次账号 RPM。

## Logging

RPM 日志需要面向线上排障可读，建议格式：

```text
[RPM] 账号=auto-3 id=14 当前=6 限制=6 粘性=true 动作=wait 等待=842ms session=abc123
[RPM] 账号=auto-3 id=14 当前=6 限制=6 粘性=false 动作=skip
[RPM] 账号=auto-3 id=14 当前=7 限制=6 粘性=true 动作=reject 原因=wait_timeout
```

日志不得输出 token、OAuth 信息、完整 session id；session 只输出短 hash。

## Admin UI / API

账号列表接口或账号详情接口需要携带当前 RPM 状态，建议返回：

- `rpm_limit`：账号配置的 RPM 上限，`0` 表示未限制。
- `rpm_current`：当前分钟已计数请求数。
- `rpm_remaining`：当前分钟剩余额度；未限制时可为 `null` 或等价值。
- `rpm_window_reset_at`：当前分钟窗口结束时间，用于前端展示刷新节奏。
- `rpm_saturated`：当前分钟是否已达到或超过限制。

前端账号页面展示为紧凑状态，例如 `RPM 4 / 8`、`RPM 未限制`、`RPM 已满`。该展示只反映当前分钟，不承诺历史趋势。为了避免误解，当前分钟计数可随页面刷新或现有轮询更新；本任务不新增历史图表。

## Rollout / Rollback

默认 `rpm_limit=0`，升级后不改变现有线上行为。上线后可先给单个账号配置保守 RPM，观察本地 RPM wait/skip/reject 与上游 429 是否下降。回滚方式是把账号 RPM 设回 0 或回滚镜像。
