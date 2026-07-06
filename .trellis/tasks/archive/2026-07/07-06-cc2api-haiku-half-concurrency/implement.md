# Implement — cc2api Haiku 半槽并发与展示

## Checklist

1. 在 `cc2api/src/service/account.rs` 为账号队列引入内部单位常量，调整 `AccountQueue::new`、`adjust_capacity`、`acquire` 和统计方法。
2. 在 `cc2api/src/service/gateway.rs` 增加请求槽位权重 helper，把 `slot_units` 传入 `acquire_account_admission`。
3. 保持本地拦截在 admission 前返回，确认 Haiku probe / warmup 不进入账号槽位。
4. 调整账号调度评分和 `AccountScoreInfo`，按内部单位计算满载和负载百分比，同时提供标准槽位、内部单位、活跃请求数、排队单位等字段。
5. 更新 `cc2api/src/handler/router.rs` 的账号列表 API 输出。
6. 更新 `cc2api/web/src/api.ts` 账号类型。
7. 更新 `cc2api/web/src/components/Accounts.vue` 并发显示和悬浮 tooltip，文案使用中文，说明普通请求和 Haiku 权重。
8. 补充或调整后端测试：
   - 普通请求占满完整槽位。
   - 两个 Haiku 请求可共享一个标准槽位。
   - 普通与 Haiku 混合按内部单位满载。
   - 队首普通/Opus 请求等待 2 单位时，后续 Haiku 不绕过队首请求。
   - 等待队列容量继续按请求数限制。
   - 缩容不强杀已有请求，并在释放后收敛到新内部容量。
   - 槽位等待中、超时、队列满不消耗 RPM。
   - 调度负载按内部单位计算。
9. 运行格式和测试。

## Validation Commands

```bash
cd cc2api
cargo fmt --check
cargo test
```

```bash
cd cc2api/web
npm run build
```

## Risk Points

- `AccountQueue::adjust_capacity` 的缩容逻辑依赖 `slots_cap` 和 target atomic，改成内部单位后必须保持扩容/缩容不会丢 permit。
- `GatewayAdmissionError::Rpm` 路径必须释放已获取的 permit，不能改变既有 drop 释放语义。
- 前端悬浮展示不要显示内部实现成“管理员需要配置两倍并发”，管理员配置语义必须保持为标准并发槽。
