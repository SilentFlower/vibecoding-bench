# cc2api Fable 周用量全局上限 - 实施计划

## 前置上下文

- [x] 读取 `prd.md`、`design.md` 和本任务 `implement.jsonl`。
- [x] 读取 cc2api 后端 service、settings/database、testing 规范及前端 Settings 规范。
- [x] 全量搜索 `AccountSelectionContext {`、`account_fable_quota_exhausted`、`fable_quota_reset_at` 和 `fable_sticky_quota_fallback_enabled`，确认所有调用方。

## 实施步骤

### 1. 新增全局百分比 setting

- [x] 在 `cc2api/src/store/settings_store.rs` 新增 `DEFAULT_FABLE_WEEKLY_USAGE_LIMIT_PERCENT = "50"` 及中文公开文档。
- [x] 在 `cc2api/src/store/db.rs` 默认 settings 插入列表加入 `fable_weekly_usage_limit_percent`，并补充默认值迁移测试。
- [x] 在 `cc2api/src/handler/router.rs::get_settings` 回填默认值。
- [x] 在 `update_settings` 校验该 key 为 `1～100` 整数；覆盖 `0`、`101`、小数和非数字错误。

### 2. 接入 Gateway 热缓存

- [x] 在 `GatewayService` 增加百分比 `RwLock<u32>`，使用默认 `50` 初始化。
- [x] 新增带中文 Javadoc 的 reload 方法；读取存量非法值时回退默认值，避免热路径 panic。
- [x] 在 `cc2api/src/main.rs` 启动加载百分比。
- [x] 在 `update_settings` 写入新 key 后触发 reload。
- [x] `/v1/messages` 构造 `AccountSelectionContext` 时传入当前百分比，其他入口保持 disabled 上下文。

### 3. 泛化 Fable 账号可用性判断

- [x] 扩展 `AccountSelectionContext`，同步所有构造器、结构体字面量和测试 helper。
- [x] 将固定 100% 判断改为接受配置阈值的辅助函数，保留 OAuth、未来 reset 和非法数据防护。
- [x] 账号选择中的 sticky 与非 sticky 过滤统一使用请求上下文阈值。
- [x] 把本地 429 文案从“耗尽”改为“达到 Fable 周用量上限”，必要时包含阈值。
- [x] 保持开关关闭、非 Fable、SetupToken、RPM 和既有综合评分行为不变。
- [x] 429 分类继续保持通用窗口优先和模型级 `RetryOtherAccount` 语义；如读取 Fable reset，使用同一配置阈值。

### 4. 更新 Settings 页面

- [x] 在 `cc2api/web/src/components/Settings.vue` 增加百分比 ref、加载和保存字段，默认 `50`。
- [x] 增加整数 `1～100` 前端校验和现有 toast 提示。
- [x] 在现有 Fable 小节内增加数字输入并更新说明文案；总开关关闭时保留数值。
- [x] 确认 `SettingsMap` 已覆盖新字段，不做无必要的 `api.ts` 改动。

### 5. 补充回归测试

- [x] 调度测试覆盖阈值边界：49% 保持 sticky、50% 切换替代账号。
- [x] 覆盖非 sticky 过滤、所有候选达到阈值返回 429、无替代账号保留 sticky。
- [x] 覆盖开关关闭、阈值 100、非 Fable、SetupToken、过期或不完整窗口。
- [x] 更新现有 `AccountSelectionContext` 和 Fable 429 单测，确认通用 5h/7d、credit、RPM 行为不回归。
- [x] settings/DB 测试覆盖默认值、合法值和非法范围。

## 检查与验证

- [x] `cd cc2api && cargo fmt --check`
- [x] `cd cc2api && cargo test`
- [x] `cd cc2api/web && npm run build`
- [x] `git -C cc2api diff --check`
- [x] 静态检查所有新 public API 和 public 字段具备中文 doc comment，复杂分支说明“为什么”。
- [x] 静态检查未新增 Gateway 请求后主动调用 usage API 的路径。

## 风险与回滚点

- `AccountSelectionContext` 是共享结构，漏改字面量会导致编译失败；先机械搜索再编译。
- 新 setting 必须同时完成默认值、数据库补齐、管理 API、reload 和 UI，任一层遗漏都会造成显示与运行不一致。
- 默认 50% 是有意的行为变化；回滚时先把百分比改为 `100`，或关闭现有 Fable 配额开关。
- 不修改账号表、usage JSON 格式和非 Fable 调度，避免扩大迁移与回归范围。
