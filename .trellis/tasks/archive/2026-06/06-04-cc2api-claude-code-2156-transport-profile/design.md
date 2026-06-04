# cc2api Claude Code 2.1.156 传输层与 Header Wire 指纹优化设计

## Technical Design

### Wire 摘要格式

每条 flow 只记录：

- method、path、status、HTTP version。
- request header 的顺序和大小写。
- header 值只记录安全枚举或 hash；`authorization`、cookie、prompt 相关字段不记录原文。
- body length、content type、content encoding。
- 时间间隔和连接复用线索。

### 对比流程

1. 从真实抓包生成 endpoint wire profile。
2. 用 cc2api 本地 dummy upstream 捕获同类请求，生成 cc2api wire profile。
3. 用脚本生成 diff：header 缺失/多余、顺序差异、大小写差异、encoding 差异、HTTP version 差异。
4. 只对低风险差异进入实现；TLS/HTTP 栈差异先记录，不贸然修改。

### 代码边界

- `version_profile.rs`：维护 endpoint profile 常量。
- `rewriter.rs`：负责 header 值、大小写和必要顺序相关结构。
- `tlsfp.rs`：仅在确认需要且有测试时调整底层 client profile。
- `oauth.rs` / `telemetry.rs`：调用统一 header profile，避免重复硬编码。

### 风险控制

- header 顺序在 Rust `HashMap` 中天然不稳定；如需要稳定 wire 顺序，应引入有序 header 表达，而不是继续依赖 `HashMap`。
- TLS 指纹属于高风险变更，必须先通过抓包对比确认当前差异。
- `Bun/1.3.14` UA 只说明该 endpoint 的应用层 UA，不等于必须完全模拟 Bun 传输层。

## Rollout / Rollback

- 第一阶段只产出 wire profile 和 diff，不改传输层。
- 第二阶段只修 header profile 中已确认的低风险差异。
- 第三阶段再评估 `tlsfp.rs` 是否需要调整。
- 如出现兼容问题，可回退到父任务已经实现的 endpoint header profile。
