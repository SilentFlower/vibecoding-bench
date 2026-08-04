# cc2api Frontend Guidelines

## 技术栈

`cc2api/web/` 是 Vue 3 + TypeScript + Vite：

```text
web/src/api.ts
web/src/router.ts
web/src/App.vue
web/src/components/
web/src/composables/useToast.ts
web/src/style.css
```

构建产物由 Rust 后端嵌入/拷贝到 `web/dist`，生产镜像只运行单个 gateway 二进制。

## API Client 契约

- 所有管理端请求统一走 `web/src/api.ts` 的 `request<T>`。
- 管理端鉴权使用 `Authorization: Bearer <admin password>`，由 `setAuth` 写入内存。
- 新增后端字段必须先更新 TypeScript interface，再更新组件。
- API path 以 `/admin/...` 为准；普通 Anthropic 代理请求不走前端 API client。
- 错误体优先读取 `{ error }`，后端本地错误要保持这个 shape。

## Router / Auth

- `router.ts` 负责恢复 `localStorage` 中的 `claude-code-gateway_auth` 并用 `api.getDashboard()` 校验。
- 需要登录的页面放在 dashboard children 下并设置 `meta.requiresAuth`。
- 不要在组件里绕过 router auth 直接判断密码；统一使用 `login` / `logout`。

## Settings 页面规则

新增 setting UI 必须：

1. 使用后端实际 setting key，不发临时别名。
2. 控件类型匹配值域：布尔用开关/选择，枚举用 select，数字用 number input。
3. 保存前做前端基础校验，但以后端校验为最终真相。
4. 说明文字聚焦风险和作用范围，不写营销式描述。
5. 与 `settings_store.rs` 默认值、`router.rs` 校验和 `GatewayService::reload_*` 同步。

### Scenario: Settings 表单字符串契约

#### 1. Scope / Trigger

- Trigger: 修改 `web/src/components/Settings.vue` 的 setting 表单、`web/src/api.ts` 的 `/admin/settings` 解析，或新增 number input 类型 setting。
- 目的: `settings` 表持久化值是字符串，但 Vue number input / 历史响应 / 代理响应在运行时可能给前端带来 `number | boolean | null`，不能让表单代码直接假设 `.trim()` 一定存在。

#### 2. Signatures

- `api.getSettings(): Promise<SettingsMap>`
- `api.updateSettings(data: SettingsMap): Promise<{ ok: boolean }>`
- `type SettingsMap = Record<string, string>`
- `Input.vue` 的 `modelValue?: string | number`，`update:modelValue` 也允许 `string | number`。

#### 3. Contracts

- `/admin/settings` 的前端入口必须把原始响应规整成 `SettingsMap`，再暴露给组件。
- `Settings.vue` 内部保存到 settings 的 payload 必须全部是字符串。
- `type="number"` 的 setting 控件可以用于 UI，但校验和保存前必须先经过表单字符串规整函数，不能直接调用 `ref.value.trim()`。
- 后端仍是最终校验者；前端只做基础输入反馈，不能放宽 `router.rs` 的范围校验。

#### 4. Validation & Error Matrix

| 条件 | 前端处理 | 后端处理 |
| --- | --- | --- |
| `fable_weekly_usage_limit_percent` 为 `"50"` | 校验通过并保存 `"50"` | 通过 |
| `fable_weekly_usage_limit_percent` 为 `50` | 前端先转成 `"50"`，不得报 `.trim is not a function` | 若提交为 `"50"` 则通过 |
| 值为空、`0`、`101`、`50.5`、`invalid` | 前端 toast 基础错误 | `update_settings` 返回 BadRequest |
| `/admin/settings` 响应包含 `null` | 前端规整为空字符串，由具体 setting 默认值或校验处理 | 不应写入无效值 |

#### 5. Good/Base/Bad Cases

- Good: 用户打开 Settings，修改 Fable 周用量 number input 后保存，不出现运行时异常，payload 中该 key 是字符串。
- Base: 后端返回默认 `"50"`，页面正常加载和保存。
- Bad: 组件直接执行 `fableWeeklyUsageLimitPercent.value.trim()`，number input 把值变成 `50` 后点击保存时报错。

#### 6. Tests Required

- 前端: `cd cc2api/web && npm run build` 必须通过，覆盖 TypeScript 和 Vite 构建。
- 后端: 涉及 Fable 周限 setting 时运行 `cd cc2api && cargo test fable_weekly_usage_limit`，断言默认值、非法值拒绝、热加载仍成立。
- 手动/自动交互验证: 修改 number input 后点击保存，确认不会出现 `.trim is not a function`，且请求体里的 setting 值是字符串。

#### 7. Wrong vs Correct

Wrong:

```typescript
const isValidLimit = computed(() => {
  const raw = fableWeeklyUsageLimitPercent.value.trim();
  return /^\d+$/.test(raw);
});
```

Correct:

```typescript
function trimFormString(value: unknown): string {
  return value == null ? '' : String(value).trim();
}

const isValidLimit = computed(() => {
  const raw = trimFormString(fableWeeklyUsageLimitPercent.value);
  return /^\d+$/.test(raw);
});
```

## 账号与凭据展示

- `access_token`、`refresh_token`、setup token、proxy password 默认不完整展示。
- 邮箱、账号 UUID、organization UUID 可以展示，但不要和 token 一起导出到日志。
- usage、RPM、并发和队列状态应标明窗口来源，避免把 5h/7d/RPM 混在一起。

## UI 风格

- 这是运维管理后台，优先信息密度和可扫描性。
- 新功能应放进已有 Accounts / Tokens / Settings / Dashboard 结构，不新增营销页。
- 使用已有 toast 模式提示保存、错误和测试结果。
- 表格/卡片按钮文字要短，危险操作保留确认。

## Common Mistakes

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 后端加字段但 `api.ts` 不更新 | TypeScript 构建失败或 UI 无数据 | 先同步 interface |
| settings 控件发错 key | 保存成功但服务不生效 | 对照 `settings_store.rs` key |
| 组件直接 fetch | 鉴权和错误处理不一致 | 统一走 `api.ts` |
| 显示完整 token | 凭据泄露 | 默认脱敏，必要时用户主动复制 |
