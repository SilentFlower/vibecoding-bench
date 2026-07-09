# cc2api Fable 配额耗尽时粘性会话智能切换 - 实施计划

## 前置检查

- [ ] 读取 `.trellis/spec/cc2api/backend/service-architecture.md`，确认 Gateway 热路径、RPM 和 sticky 语义。
- [ ] 读取 `.trellis/spec/cc2api/backend/settings-database.md`，确认新增 setting 同步清单。
- [ ] 读取 `.trellis/spec/cc2api/frontend/frontend-guidelines.md`，确认 Settings 页面规则和构建要求。
- [ ] 对照 `prd.md` / `design.md`，确认功能开关默认开启、无替代账号不删除 sticky、429 后不同步 usage。

## 实施步骤

### 1. 新增全局 setting

- [ ] 在 `cc2api/src/store/settings_store.rs` 新增 `DEFAULT_FABLE_STICKY_QUOTA_FALLBACK_ENABLED = "true"`。
- [ ] 在 `cc2api/src/store/db.rs` 默认 settings 插入列表加入 `fable_sticky_quota_fallback_enabled`。
- [ ] 在 `cc2api/src/handler/router.rs::get_settings` 回填该 key 的默认值。
- [ ] 在 `cc2api/src/handler/router.rs::update_settings` 将该 key 纳入布尔校验列表。
- [ ] 在 `update_settings` 中检测该 key 变化后调用 Gateway reload。

### 2. Gateway 配置热缓存

- [ ] 在 `GatewayService` 增加 `RwLock<bool>` 配置字段。
- [ ] 在 `GatewayService::new` 使用默认值初始化。
- [ ] 新增 `reload_fable_sticky_quota_fallback_enabled()`，从 settings 读取并解析布尔值。
- [ ] 在 `cc2api/src/main.rs` 启动 reload 清单中调用新 reload 方法。
- [ ] 在 Gateway `/v1/messages` 账号选择前读取该配置，传入账号选择上下文。

### 3. Fable 模型级耗尽判断

- [ ] 新增或复用辅助函数判断请求模型是否为 Fable，覆盖 `claude-fable-5` 和 `claude-fable-5[...]`。
- [ ] 新增辅助函数判断账号 `usage_data.seven_day_fable` 是否明确耗尽：
  - `utilization >= 100`
  - `resets_at` 为未来 RFC3339 时间
  - 缺字段、非法值、过期 reset 均返回未耗尽
- [ ] 确认该函数不使用 `USAGE_HIT_THRESHOLD = 97.0`。

### 4. 账号选择与 sticky fallback

- [ ] 扩展账号选择上下文，保持旧 `select_account` / `select_account_with_context` 调用兼容。
- [ ] Fable + 开关开启时，sticky 命中账号若明确耗尽，则本轮临时排除该账号，但不删除 session 绑定。
- [ ] 非 sticky Fable 候选过滤明确耗尽账号；全部候选耗尽时返回 429/可识别错误，不能无限循环。
- [ ] 替代账号实际进入上游路径后，继续复用现有 `bind_selected_session` 覆盖 session。
- [ ] 功能关闭时完全走旧账号选择行为。

### 5. Fable 429 处理

- [ ] 让 429 分类能拿到请求模型上下文。
- [ ] Fable 请求且账号缓存 `seven_day_fable >= 100` 时，返回模型级耗尽决策，不写账号全局 `rate_limit_reset_at`。
- [ ] Fable 429 且本地 usage 未满时，不同步查询 OAuth usage；只触发后台节流刷新。
- [ ] 保留通用 `five_hour` / `seven_day` 撞墙、`retry-after` 和瞬时 429 既有行为。
- [ ] 保留 sticky RPM 饱和等待/本地 429，不把 RPM 饱和纳入 Fable fallback。

### 6. Settings 页面

- [ ] 在 `cc2api/web/src/components/Settings.vue` 新增 `fableStickyQuotaFallbackEnabled` ref，默认 `true`。
- [ ] `loadSettings()` 读取 `fable_sticky_quota_fallback_enabled`，缺省为开启。
- [ ] `saveSettings()` 提交 `fable_sticky_quota_fallback_enabled`。
- [ ] 在“评分权重”卡片内新增“Fable 配额切换”小节：
  - 开启显示 `已启用`
  - 关闭显示 `保持粘性`
  - 说明文字使用 PRD 决策文案
- [ ] 如 `api.ts` 类型需要补充，保持 `SettingsMap = Record<string, string>` 的现有接口形态。

### 7. 测试

- [ ] 补充账号选择单测：Fable sticky 已满时选替代账号并标记非 sticky 选择结果可重绑。
- [ ] 补充账号选择单测：无替代账号时不删除旧 sticky。
- [ ] 补充账号选择单测：功能关闭时仍命中原 sticky。
- [ ] 补充账号选择单测：非 Fable 请求不受 `seven_day_fable` 满影响。
- [ ] 补充 429 分类单测：Fable + cached `seven_day_fable >= 100` + `credit` 文案不走单请求透传。
- [ ] 保留或扩展 sticky RPM 饱和不切号回归测试。
- [ ] 前端保存/加载开关至少通过构建验证覆盖。

## 验证命令

```bash
cd cc2api
cargo fmt --check
cargo test
cd web
npm run build
```

## 风险点

- 账号选择 API 改动会影响 `count_tokens` 和现有测试；实现时应保留旧入口或提供默认上下文，避免大范围改调用方。
- Fable 耗尽判断不能复用通用 97% 阈值，否则违背用户决策。
- 429 后后台 usage refresh 不能绕过现有账号级节流。
- Settings 新 key 写入后必须 reload，否则 UI 显示保存成功但热路径仍用旧值。
