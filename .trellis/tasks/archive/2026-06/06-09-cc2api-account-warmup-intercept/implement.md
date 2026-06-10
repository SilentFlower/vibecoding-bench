# cc2api 全局预热请求拦截实现计划

## Implementation Checklist

- [x] 在 `settings_store.rs` / `db.rs` 增加三个预热拦截 settings 默认值。
- [x] 在 `GatewayService` 增加 `WarmupInterceptConfig` 内存缓存和 reload 方法。
- [x] 在 `/admin/settings` GET/PUT 中返回、校验、保存并 reload 三个新 key。
- [x] 实现预热请求识别函数，覆盖标题预热、Suggestion Mode、Haiku 探测三类。
- [x] 标题预热识别中同时覆盖旧 sub2api 文本标题模式和 `data/flows` 里的新版 Claude Code JSON 标题 system prompt。
- [x] 实现 Anthropic messages 非流式 mock 响应。
- [x] 实现 Anthropic messages SSE mock 响应。
- [x] 在账号选择后、RPM/并发/token/上游前接入拦截。
- [x] 设置页新增三个全局开关。
- [x] 增加后端单元测试覆盖识别规则和 mock 响应关键字段。
- [x] 用 `data/flows` 中提取的代表性请求补充测试样本：
  - Haiku `max_tokens=1` 非流式 quota 探测返回 `#`。
  - 新版 Claude Code JSON 标题请求返回 `{"title":"New Conversation"}`。
  - `SUGGESTION MODE` 请求返回空文本。
  - 普通 `/v1/messages` 请求不命中。

## Validation

- `cargo fmt --check`
- `cargo test`
- `npm --prefix web run build`
- `git diff --check`

## Review Gates

- 三个子规则默认值已确认：全部关闭。
- 检查不会误拦截普通用户消息。
- 检查命中拦截时不会发起上游请求。
