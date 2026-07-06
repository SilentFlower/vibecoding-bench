# Design — cc2api Haiku 半槽并发与展示

## Architecture

本任务保持 `Account.concurrency` 的外部语义不变，在 `AccountQueue` 内部引入固定比例的槽位单位：

- `SLOT_UNIT_SCALE = 2`
- 普通请求：`2` 个内部单位，即 `1.0` 标准并发槽
- Haiku 请求：`1` 个内部单位，即 `0.5` 标准并发槽

这样无需数据库迁移，也不需要管理员调整已有账号配置。

## Backend Flow

1. `GatewayService::handle_request_inner` 解析请求 body 后，保留现有本地拦截顺序。
2. 只有未被本地拦截、准备进入上游转发链路的请求，才根据模型 ID 计算 `slot_units`。
3. `GatewayService::acquire_account_admission` 接收 `slot_units`，调用 `AccountQueue::acquire(timeout, slot_units)`。
4. `AccountQueue` 使用 `Semaphore::acquire_many_owned(slot_units)` 获取内部单位，返回现有 `OwnedSemaphorePermit`。
5. 槽位成功后继续执行现有 RPM admission；失败路径仍不消耗 RPM。
6. 响应体生命周期继续由 `SlotReleaseGuard` 和 `SlotGuardBody` 释放 permit。

## AccountQueue Changes

- `slots` 容量从 `concurrency` 改为 `concurrency * SLOT_UNIT_SCALE`。
- `queue_cap` 继续按等待请求数限制，容量保持 `2 * concurrency`，避免半槽改动把等待请求数也翻倍。
- 新增或调整统计方法：
  - `active_units()`：当前占用内部单位。
  - `active_standard_slots()`：`active_units / 2.0`。
  - `waiting_count()`：等待请求数，保留现有语义。
  - `waiting_units()`：等待请求预计需要的内部单位。
  - 可选 `active_request_count()`：用于 UI 展示活跃请求数。
- `adjust_capacity` 以标准 `concurrency` 为输入，但对 `slots` 使用内部单位目标；对 `queue_cap` 使用等待请求数目标。

## Request Weight Rule

`GatewayService` 中新增小型 helper：

```text
request_slot_units(path, body_map) -> u32
```

规则：

- 如果请求路径是 `/v1/messages` 相关，并且 `body.model` 小写后包含 `haiku`，返回 `1`。
- 其他进入上游的请求返回 `2`。
- 本地拦截路径在调用 admission 前已经返回，因此不需要特殊权重。

## Scheduling And API Contract

账号调度评分从 `active_count()` 改为使用内部单位：

```text
concurrency_load_pct = (active_units + waiting_units) / (concurrency * 2) * 100
full = active_units >= concurrency * 2
```

管理 API 在保留 `current_concurrency` / `queued_requests` 的同时，增加结构化字段用于前端展示：

- `current_concurrency`：标准槽位数，可为小数，例如 `1.5`。
- `current_concurrency_units`：当前内部单位，例如 `3`。
- `max_concurrency_units`：最大内部单位，例如 `6`。
- `active_requests`：活跃请求数。
- `queued_request_units`：等待请求预计内部单位。

前端不根据 `concurrency` 自行推导内部单位，只消费后端字段。

## Frontend UX

`Accounts.vue` 的账号卡片并发区域：

- 默认展示：`1.5/3`，数值保留最多 1 位小数，整数不显示 `.0`。
- 鼠标悬浮展示 tooltip：
  - 当前标准槽位：`1.5 / 3`
  - 内部单位：`3 / 6`
  - 活跃请求数：`2`
  - 排队请求：`1`
  - 排队单位：`2`
  - 规则：`普通请求 = 1 并发，Haiku = 0.5 并发`

## Compatibility

- 不改 DB schema。
- 老前端字段 `current_concurrency` 仍存在，但类型从整数语义扩展为数字标准槽位；TypeScript `number` 无需改类型，只需更新展示格式和新增字段。
- 现有账号配置不需要迁移。

## Risks

- `Semaphore::acquire_many_owned(2)` 具有公平性语义：如果队首普通/Opus 请求等待 2 个单位，即使有 1 个单位空闲，后续 Haiku 也不会插队。该行为保持 FIFO，但可能产生轻微队首阻塞；这是公平性优先的可接受取舍。
- 例子：账号并发为 5 时内部容量是 10 单位。9 个 Haiku 占用 9 单位后只剩 1 单位；新 Opus 需要 2 单位，因此必须等待。若队首已有 Opus 等待，后续 Haiku 也不应绕过它抢占剩余 1 单位。
- 等待队列保持请求数语义。账号并发为 5 时等待位仍为 10 个请求；这避免 Haiku 半槽把等待队列扩大到 20 个请求，导致单账号积压过深。
- 缩容沿用现有不强杀策略。`concurrency` 变小时，内部单位 target 会降低，但已持有 permit 的请求继续完成，后台 shrinker 在请求释放后逐步吞掉多余 permit。
- 如果只修改容量不修改每请求获取单位，会让所有请求都变成半槽，这是必须避免的错误。
- 如果调度负载仍按请求数计算，UI 和调度会与真实容量不一致。
