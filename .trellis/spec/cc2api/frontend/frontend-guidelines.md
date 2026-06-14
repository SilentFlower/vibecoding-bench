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
