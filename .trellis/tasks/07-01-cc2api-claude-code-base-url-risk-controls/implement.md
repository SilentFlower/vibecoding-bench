# Implementation Plan: cc2api Claude Code base URL 风险控制

## Checklist

1. 设置与配置结构
   - 在 `settings_store.rs` 增加默认常量 `DEFAULT_CLAUDE_CODE_CONTEXT_SANITIZER_MODE = "report_only"`。
   - 在 `db.rs` 默认 settings 插入新 key。
   - 在 `handler/router.rs` 的 GET 默认值和 PUT 校验中接入新 key。
   - 在 `GatewayService` 增加 `RwLock` 配置、默认值函数、reload 方法，并在 settings 更新后调用 reload。

2. 请求体扫描与规范化
   - 在 `rewriter.rs` 定义模式 enum / config / finding 摘要结构。
   - 在 Claude Code 客户端模式的 `rewrite_messages` 中接入扫描入口。
   - 实现 `scan_or_normalize_current_date_context`，只遍历 `system` 和 `messages[].content` 的 text。
   - `report_only` 只日志；`normalize` 修改命中句式并日志。
   - 确保该逻辑在最终 CCH / `cc_version` 刷新前执行。

3. Telemetry denylist
   - 扩展 `telemetry.rs::sensitive_key`。
   - 增加 URL/host value 判断函数，命中非官方 base URL/proxy/gateway 痕迹时丢弃字段。
   - 补 sanitizer 单测。

4. 管理页
   - 在 `Settings.vue` 增加状态变量、load/save、合法值兜底和单选控件。
   - 如需要，`api.ts` 保持 `Record<string,string>` 无需新增类型。

5. 测试
   - `rewriter.rs` 单测：report_only 不改 body；normalize 改写；普通用户正文不误改；非 Claude Code 模式不触发。
   - `telemetry.rs` 单测：新增 key/value 被清洗；官方 host 不被误删。
   - 运行：
     - `cd cc2api && cargo fmt --check`
     - `cd cc2api && cargo test`
     - `cd cc2api/web && npm run build`

## Risk Files

```text
cc2api/src/service/rewriter.rs
cc2api/src/service/gateway.rs
cc2api/src/service/telemetry.rs
cc2api/src/store/settings_store.rs
cc2api/src/store/db.rs
cc2api/src/handler/router.rs
cc2api/web/src/components/Settings.vue
```

## Rollback

- 将 setting 默认值改回 `off` 可快速关闭请求扫描/规范化。
- telemetry denylist 是低风险清洗；如误删，回滚 value 判断函数或收窄 key 列表。
- 不涉及 DB schema，只涉及 settings 默认插入，回滚无需迁移。
