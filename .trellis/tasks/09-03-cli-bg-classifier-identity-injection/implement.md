# 实施计划

## 1. 设置与迁移

- [x] 在 `cc2api/src/store/settings_store.rs` 增加默认关闭常量。
- [x] 在 `cc2api/src/store/db.rs` 把新 key 加入默认 settings，补充“缺失时插入、已有值不覆盖”的迁移测试。
- [x] 在 `cc2api/src/service/gateway.rs` 增加 `CliBgStatusClassifierConfig`，把 mode 与 identity 开关放入同一 `RwLock`，实现带完整文档的 reload 和测试 accessor。
- [x] 在 `cc2api/src/main.rs` 改为启动加载完整 classifier config。
- [x] 在 `cc2api/src/handler/router.rs` 补 GET 默认值、`true/false` 校验、更新后的热刷新和管理 API 测试。

## 2. Detector 分层

- [x] 保留或重命名当前窄 Fable 5.1 detector，确保 mock/passthrough 现有行为不扩大。
- [x] 新增通用 classifier detector，支持 `x-app=cli|cli-bg`、stream 缺失/false、billing/identity/classifier system 组合和唯一 user 输入。
- [x] 复用现有 `is_haiku_model_id` 判断注入资格。
- [x] 添加真实 Haiku 抓包形状、Fable/Opus/Sonnet 形状和普通主请求/未知 system/多消息等正反单测。

## 3. 身份与归因前缀补齐

- [x] 在 `cc2api/src/service/rewriter.rs` 扩展 identity-only 正文入口，严格使用现有 `Account`、`UpstreamSessionRewrite`、billing builder 和版本画像定义。
- [x] 缺少 billing 时复用 API 模式生成标准 billing/CCH，缺少 identity 时插入精确身份块，最终顺序固定为 billing、identity、classifier，且不加入 expansion。
- [x] 最终序列化后处理 CCH：新建 billing 生成有效值；已有 billing/CCH 刷新；已有 billing 但无 CCH 保持原样。
- [x] 覆盖 metadata/session 变化、system 顺序、cache_control/thinking/fallbacks 保持、无重复块、billing 新建和 CCH 生成/重算测试。

## 4. Gateway 接线与隐私

- [x] 在 body parse 后同时计算 narrow/generic match，并一次读取 classifier config 快照。
- [x] 保持 narrow mock 提前返回；未进入新补齐分支时保持 narrow passthrough 旧旁路。
- [x] 对 generic + passthrough + enabled + non-Haiku 使用前缀补齐旁路，并确保其优先于 narrow passthrough 旧旁路。
- [x] 注入命中使用 `SummaryOnly`，跳过 non-stream probe cache，并输出不含正文和凭据的结构化摘要。
- [x] 增加 gateway 集成测试：开关关闭、开启、Haiku、已有 identity、mock、普通请求、账号代理链路。

## 5. Settings UI

- [x] 在 `cc2api/web/src/components/Settings.vue` 增加布尔 ref、默认加载和字符串保存。
- [x] 在现有后台状态分类区域增加独立 checkbox；mock 时 disabled 但保留已保存值。
- [x] 更新说明文案，清楚区分 mode 的窄事故画像和通用身份注入范围。

## 6. 文档与验证

- [x] 更新管理员可见的 setting 文档或 README 配置说明。
- [x] 运行格式化与定向测试。
- [x] 运行完整 Rust 测试、CCH 测试和前端构建。
- [x] 检查 git diff，确认不包含抓包正文、凭据、代理 URL 或无关文件。

## Validation Commands

```bash
cd cc2api && cargo fmt --check
cd cc2api && cargo test cli_bg_status_classifier
cd cc2api && cargo test identity_only
cd cc2api && cargo test cch
cd cc2api && cargo test settings
cd cc2api && cargo test
cd cc2api/web && npm run build
```

## Risky Files And Rollback Points

- `cc2api/src/service/gateway.rs`: detector 与转发决策集中，必须先保证原 narrow mock/passthrough 测试不变。
- `cc2api/src/service/rewriter.rs`: billing/identity 补齐后必须在最终正文上生成或刷新 CCH；失败时回滚到原 body，而不是发送部分改写结果。
- `cc2api/src/store/db.rs`: 新 setting 只补缺失值，不能覆盖生产管理员配置。
- `cc2api/web/src/components/Settings.vue`: payload 必须提交字符串 `true|false`，不能提交布尔导致后端契约漂移。

## Pre-Start Check

- [x] 模式保留 `passthrough | mock`，默认不变。
- [x] 身份注入为独立开关，默认关闭。
- [x] mock 范围不扩大，注入只在 passthrough 生效。
- [x] 通用 detector 与窄 mode detector 分离。
- [x] Haiku 永不注入。
- [x] 缺少 billing 时按 API 模式生成 billing/CCH；存在 billing CCH 时刷新。
- [x] 本任务不自动部署生产环境。
