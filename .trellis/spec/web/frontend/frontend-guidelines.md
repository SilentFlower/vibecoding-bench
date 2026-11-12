# cc2api Frontend Guidelines

## 技术栈

`apps/web/` 是 Vue 3 + TypeScript + Vite：

```text
apps/web/src/api.ts
apps/web/src/router.ts
apps/web/src/App.vue
apps/web/src/components/
apps/web/src/composables/useToast.ts
apps/web/src/style.css
```

构建产物由 Rust 后端嵌入/拷贝到 `apps/web/dist`，生产镜像只运行单个 gateway 二进制。

## API Client 契约

- 所有管理端请求统一走 `apps/web/src/api.ts` 的 `request<T>`。
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

- Trigger: 修改 `apps/web/src/components/Settings.vue` 的 setting 表单、`apps/web/src/api.ts` 的 `/admin/settings` 解析，或新增 number input 类型 setting。
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

- 前端: `cd services/gateway/web && npm run build` 必须通过，覆盖 TypeScript 和 Vite 构建。
- 后端: 涉及 Fable 周限 setting 时运行 `cd services/gateway && cargo test fable_weekly_usage_limit`，断言默认值、非法值拒绝、热加载仍成立。
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
- 5h／7d 请求与费用读取列表附加的 `request_usage`，沿用 5 秒刷新；读页面不能清空记录，过期额度显示待更新。金额、完整性与估算条件统一见 [网关请求窗口费用](../../gateway/backend/settings-database.md#scenario-网关请求窗口费用)。

### Scenario: 账号基础版本与画像选择配置展示

#### 1. Scope / Trigger

- Trigger：修改账号卡片版本展示或账号列表画像配置时适用。
- 账号持久环境与请求画像有不同含义；同账号可以承载不同客户端版本，页面必须分别标明基础版本和画像选择方式。

#### 2. Signatures

- `GET /admin/accounts?page=<页码>&page_size=<数量>`，保留既有分页响应。
- `GatewayService::profile_selection_config(&self) -> ClaudeCodeProfileSelectionConfig`（async），返回当前生效的原子配置快照。

#### 3. Contracts

- 列表顶层增加 `claude_code_profile_selection_mode: "client_version" | "account"`、`claude_code_version_profile: string`；读取网关实际缓存，不另读数据库猜测生效配置。
- 卡片中 `canonical_env.version` 标为「账号基础版本」，画像方式独立展示；客户端模式显示「默认回退」。基础版本不能当作该账号所有请求的版本。
- 账号配置展示和请求版本适配不依赖自动遥测开关。
- 沿用账号列表每 5 秒轮询。前端新增字段使用可选类型兼容旧后端；缺少配置时显示「未提供画像配置」，不硬编码模式或默认版本。

#### 4. Validation & Error Matrix

| 条件 | 展示/接口行为 |
| --- | --- |
| 基础版本 280，客户端模式，自动遥测关闭 | 展示基础版本、按客户端 UA 适配和实际默认回退版本 |
| 账号模式 | 展示「使用账号画像」，不展示客户端模式的默认回退 |
| mode/default 保存成功并 reload | 下一轮账号列表展示实际生效的新配置 |
| 设置校验失败 | 列表继续展示原有缓存配置 |
| 旧响应没有新增字段 | 展示配置缺失提示，不能硬编码 280 或客户端模式 |

#### 5. Scenarios and Examples

- 正常：卡片显示「账号基础版本：v2.1.280」「按客户端 UA 适配」「默认回退：v2.1.280」。
- 边界：自动遥测关闭仍正常显示画像配置；旧接口没有画像字段时显示配置缺失提示。
- 错误：把账号保存的 v280 当成当前所有请求版本，或用默认 280 填补旧接口缺失的配置字段。
- 正确：基础版本读取持久 env，画像方式和默认回退读取网关当前生效的配置。

#### 6. Tests Required

- 管理 API：非空账号列表保留基础版本，自动遥测关闭时仍返回画像配置；mode/default 热刷新和失败校验后列表配置符合实际缓存。
- 前端：同步 `api.ts` 可选类型和卡片配置缺失分支，通过 `npm run build`；后端通过 `cargo fmt --check` 与完整 `cargo test`。

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


## Scenario: 管理页面版本、导航与请求详情

### 1. Scope / Trigger

修改 `Dashboard.vue`、`Environments.vue`、`SystemUpdates.vue`、`RequestDiagnostics.vue` 及其共享展示工具时适用。

### 2. Signatures

- `formatLocalTime(value?: string | null): string` 按浏览者时区显示日期、秒与 IANA 时区，空值及非法值显示“未观测”。原始 UTC 值仍用于查询与追溯。
- 顶层 `/environments` 为环境列表，`/tasks?tab=accounts|topics|tasks|runs|projects|warmup` 为原任务相关页面；默认任务 Tab 使用 `/tasks`。
- iframe `/runtime/?view=environments|tasks#<tab>?account=...&environment=...&gateway_account=...` 只传受控视图及筛选参数。

### 3. Contracts

- 目标管理页面采用 vm2api 实际亮色参考：中性表面、绿色强调、系统中文字体和等宽数字。现有 token 保名换值，App 背景使用 token。环境页仅在 `environment-page` 作用域映射色板；任务页保留原 `vibebench-theme` 偏好。
- 顶层环境页隐藏重复内层导航；任务页隐藏环境子 Tab。旧内部链接通过 `runtime:navigate` 消息同步顶层 URL。父页同时核对 `origin`、当前 iframe `contentWindow` 和 Tab 白名单；忽略其它来源。
- iframe 按 source 设置 key，导航由顶层创建历史项；点击内部链接先阻止内部 hash 历史重复入栈。账号筛选以 replace 同步，刷新和前进后退均以 URL 为准。离页保留原轮询、SSE 和弹窗收口。
- `gateway_account` 表示网关账号 ID，环境列表按公开 `gateway_account_id` 精确筛选。bench 账号 ID 与网关 ID 分开处理。提供“显示全部环境”清除直达筛选。
- 请求列表紧凑显示时间、短 ID、账号、持久终态和实际总耗时；390px 保留时间、账号、结果及详情入口，其它列按宽度折叠。状态使用 outcome，空计时保持未知，实际零 token 显示 0。
- 请求详情四页签为概览、请求链路、性能、原始数据。固定标题与页签、内部滚动，支持方向键、Esc 和焦点返回。响应头耗时、首次有效输出、本地准备分别显示；本地准备包含等待与 checkout。
- 内容读取同时检查原生方式、发生时日志模式及 capture_status。disabled、info、failed、dropped 提供各自状态与指引；queued/saved/timeout 和旧状态按原合同按需读取。关闭及切换尝试使原读取代次失效，保留已有后台证据短轮询。
- 账号内容采集开关位于环境卡片，请求详情直达对应网关账号；保存窗口冻结 generation/revision，冲突后重新读取。具体后端合同见账号运行时规范“账号请求内容采集开关”。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 旧记录缺时间、模式或性能 | 保持未观测或历史未知 |
| disabled 或 info | 阶段文件读取为零，说明后续请求生效条件 |
| missing / expired | 分别显示文件缺失或已清理、超过保留期 |
| 切换尝试、关窗、离页 | 旧回执失效，关闭后焦点回到原按钮 |
| 过期配置或忙碌维护 | 展示服务端冲突，停止重放写入 |

### 5. Scenarios and Examples

- 正常：debug 请求显示“当时采集已关闭”→直达账号环境→空闲切换→后续请求使用新配置。
- 边界：上海与洛杉矶显示同一 UTC 时间的对应本地时间；历史零值与空值保持区别。
- 错误用法：把 bench 账号 ID 直接当作网关 ID。正确处理：按公开绑定字段筛选。
- 错误用法：仅凭 debug 提供采集读取按钮。正确处理：同时使用发生时采集状态。

### 6. Tests Required

- `cd services/gateway/web && npm run build`；通过 Vue/TypeScript 和生产构建。
- `python deploy/v3/verify_management_ui.py --output .deploy/management-ui/combined`：实际产物、合成 API、两个时区、390px、版本单展开、导航历史、采集开关及异步关闭。
- 原 `verify_environment_ui.py` 继续覆盖内核、时段、焦点、乱序和物理实测；所有浏览器模型调用为零。
