# implement.md

## Implementation Checklist

- [x] 阅读 cc2api 相关代码：`rewriter.rs`、`gateway.rs`、`settings_store.rs`、`db.rs`、`router.rs`、`Settings.vue`。
- [x] 将 `MessageCacheControlRewrite` 增加 `Rolling` 枚举值，解析允许 `rolling`。
- [x] 实现 `add_rolling_message_cache_control`：按顶层 message content block 从尾部选择最多可用数量的断点。
- [x] 统计 system/tools 已有 `cache_control` 数量，保证总断点数不超过 4。
- [x] 保持 `stable` 旧行为，`rolling` 走新算法，`off` 透传。
- [x] 更新后端 settings 默认、校验错误文案、README 或设置说明。
- [x] 更新前端设置页类型、回显、单选项和说明文案。
- [x] 增加或更新 Rust 单元测试：parse、rolling 断点距离、system/tools 占用、TTL 覆盖、非 Claude Code 忽略、CCH 重新计算。
- [x] 运行后端测试与前端可用的构建/检查命令。
- [x] 确认本轮实现未新增强制串行 tool 模式。

## 二次修复 Checklist

- [x] 修正 rolling 策略：请求根级 `cache_control` 不再计入 message history 断点 slot。
- [x] 修正 rolling 策略：存在根级 `cache_control` 时仍优先给尾部最后一个可缓存 message block 打断点。
- [x] 在可用 slot 未用满时，为 Claude Code 首个 user message 的自动注入块末尾补边界断点。
- [x] 更新单元测试覆盖根级 `cache_control`、system/tools slot、短 history 尾部断点和自动注入边界。
- [x] 更新 README 中 rolling 策略说明。

## 三次修复 Checklist

- [x] 在 `rolling` 策略下稳定化 `tools[]` 顺序，按 `name` 排序且保留对象内容。
- [x] 在 `rolling` 策略下稳定化 skills 列表文本顺序。
- [x] 在 `rolling` 策略下稳定化 deferred tools 列表文本顺序。
- [x] 更新 README，说明 `rolling` 也会稳定化 Claude Code cache prefix。
- [x] 增加 Rust 单元测试覆盖同一工具/列表集合不同输入顺序 rewrite 后一致。

## 四次修复 Checklist

- [x] 新增独立 `anchored` 模式，不覆盖现有 `rolling` 行为。
- [x] 将无状态 `rolling` 步距从 10 个真实顶层 message content block 调整为 19 个。
- [x] `anchored` 按账号 + Claude Code session_id 记录上一轮实际发往上游的 message 断点指纹。
- [x] `anchored` 下一轮以最新旧断点为读缓存锚点，按 19-block 步距桥接到当前尾部，并强制补当前尾部断点。
- [x] `anchored` 指纹计算剥离 `cache_control` 字段，避免本轮新建断点污染下一轮匹配。
- [x] 新增 Rust 单元测试覆盖 anchored 复用、跨 session 隔离、无 session fallback、TTL 覆盖和 CCH 重算。
- [x] 更新前端设置页增加“会话锚定”选项。
- [x] 更新 README 说明 `anchored` 的单进程内存状态限制。

## 五次修复 Checklist

- [x] 废弃第四轮 `anchored` 独立运行路径，保留历史记录仅用于说明问题演进。
- [x] 将最终可选模式收敛为 `off / auto / rolling`。
- [x] `auto` 作为推荐保守策略：稳定化 prefix，清理旧断点，优先 text 边界，不主动选择 `assistant tool_use`。
- [x] `rolling` 保留为更积极对照：稳定化 prefix，尾部允许最新 `user tool_result`，窗口先选 text，仅在窗口无 text 时兜底 `user tool_result`，不允许 `assistant tool_use`。
- [x] 历史配置字符串 `stable` / `anchored` 兼容解析为 `auto`，不再保留独立运行路径。
- [x] 前端设置页只展示 `off / auto / rolling`，旧值加载时回显为 `auto`。
- [x] 更新 Rust 单元测试，覆盖 auto 尾部 `tool_result` 选点、rolling text 优先与无 text 窗口兜底、旧 stable alias 与 CCH/TTL 组合。

## Validation

- `cargo test`
- 如前端存在构建脚本：`npm run build`
- 手工检查设置接口接受 `message_cache_control_rewrite=auto|rolling` 并可回显；历史 `stable|anchored` 会兼容归一为 `auto`。

## Review Gates

- 实现前必须先启动任务：`python3 ./.trellis/scripts/task.py start .trellis/tasks/06-07-proxy-fix-claude-code-parallel-cache`。
- 实现前需按 Trellis 路由选择 implement 模式。
- 提交前需按 Trellis 路由选择 check 模式，并完成质量检查。

## Rollback Points

- 新策略默认 `off`，配置回滚即可恢复透传。
- 若 `auto` 线上表现不稳定，切回 `rolling` 或 `off` 对照。
