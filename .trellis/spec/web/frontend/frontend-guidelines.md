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

- 前端: `npm --prefix apps/web run build` 必须通过，覆盖 TypeScript 和 Vite 构建。
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
- `RequestDiagnostics.copy(value: string, event: MouseEvent): Promise<void>` 复制按钮对应的完整请求 ID，事件提供当前焦点域。
- 顶层 `/environments` 为环境列表，`/tasks` 默认内部 accounts；`/tasks?tab=topics|tasks|runs|projects|warmup` 显式选择其它内部页面，兼容 `tab=accounts`。
- iframe `/runtime/?view=environments|tasks#<tab>?account=...&environment=...&gateway_account=...` 只传受控视图及筛选参数。

### 3. Contracts

- 目标管理页面采用 vm2api 实际亮色参考：中性表面、绿色强调、系统中文字体和等宽数字。现有 token 保名换值，App 背景使用 token。环境页仅在 `environment-page` 作用域映射色板；任务页保留原 `vibebench-theme` 偏好。
- 品牌文字为小写 flower2api；登录、主导航和 favicon 共用粉红五瓣节点花图形 `public/favicon.svg`，颜色 `#ED6EA7`，通道透明。三个消费者同步版本参数 `?v=flower2api-pink-04`，资源更新时共同更新缓存标识。
- SystemUpdates 的原生 `dialog.showModal()` 显式设置 `margin:auto`，避免 Tailwind preflight 的零外边距覆盖浏览器居中；最大高度为视口减 2rem，内容超高时内部滚动。安装、回退和恢复继续沿用冻结操作、冲突保护及取消/Esc/遮罩收口。
- 系统安装与回退确认每次打开默认一分钟，冻结请求为60秒；可选1/5/15/30/60/120分钟，已登记操作与恢复继续使用原参数。后端默认及冲突合同见[平台在线更新](../../platform/deploy/platform-online-update.md)。
- 顶层环境页隐藏重复内层导航；任务页隐藏环境子 Tab。旧内部链接通过 `runtime:navigate` 消息同步顶层 URL。父页同时核对 `origin`、当前 iframe `contentWindow` 和 Tab 白名单；忽略其它来源。
- iframe 仅按文档 view（environments/tasks）设置 key，src 在同一 view 内固定。顶层 URL 变化通过同源 location.replace 同步内部 hash；初次加载完成再核对最新目标。二级导航保持 iframe 元素与文档身份。
- 点击内部链接先阻止内部 hash 入栈；数字键、搜索、账号直达及创建后的程序化跳转统一走 `navigateTo(hash)`，嵌入时由 `runtime:navigate` 创建唯一顶层历史项，独立页面继续 hash 导航。账号筛选以 replace 同步，刷新和前进后退均以 URL 为准。
- 切页递增 viewGeneration，账号/题库/任务/运行的迟到列表、运行流和首屏 GET 不写入新页面。关闭普通详情、关联、养号配置、题目和任务弹窗，使运行详情刷新失效；专用环境及项目窗口沿原收口入口。交互登录与续聊继续由各自显式关闭流程管理。
- `gateway_account` 表示网关账号 ID，环境列表按公开 `gateway_account_id` 精确筛选。bench 账号 ID 与网关 ID 分开处理。提供“显示全部环境”清除直达筛选。
- 请求列表紧凑显示时间、短 ID、账号、持久终态和实际总耗时；390px 保留时间、账号、结果及详情入口，其它列按宽度折叠。状态使用 outcome，空计时保持未知，实际零 token 显示 0。
- 请求账号统一显示当前名称和邮箱，覆盖桌面/390px列表、概览、链路、性能及尝试选择器。名称为空时使用邮箱，两者相同去重；缺资料显示“账号信息缺失（ID n）”，未选账号显示“未知账号”。列表、详情按各自实际账号字段展示，ID继续用于筛选及环境直达；长文本换行、选择器限制在容器内。查询安全字段与持久匿名合同见[请求级诊断](../../gateway/backend/settings-database.md#scenario-请求级诊断与发送尝试关联)。
- 请求详情四页签为概览、请求链路、性能、原始数据。固定标题与页签、内部滚动，支持方向键、Esc 和焦点返回。响应头耗时、首次有效输出、本地准备分别显示；本地准备包含等待与 checkout。
- 请求 ID 复制在安全上下文优先调用 Clipboard API；接口缺失或拒绝时用临时只读 textarea 和 `execCommand('copy')` 降级。临时节点属于触发按钮所在的活动 dialog，结束后清理并恢复焦点及选择。只有写入 Promise 成功或复制命令返回 true 才显示成功；全部失败保留手动选择提示。
- 内容读取同时检查原生方式、发生时日志模式及 capture_status。disabled、info、failed、dropped 提供各自状态与指引；queued/saved/timeout 和旧状态按原合同按需读取。关闭及切换尝试使原读取代次失效，保留已有后台证据短轮询。
- 账号内容采集开关位于环境卡片，请求详情直达对应网关账号；保存窗口冻结 generation/revision，冲突后重新读取。具体后端合同见账号运行时规范“账号请求内容采集开关”。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 旧记录缺时间、模式或性能 | 保持未观测或历史未知 |
| 账号资料缺失 / 账号为空 / 跨账号重试 | 明确提示及 ID / 未知账号 / 分别展示各次实际资料 |
| 修改等待期限后取消重开 / 直接确认 | 恢复默认一分钟 / 提交60秒 |
| disabled 或 info | 阶段文件读取为零，说明后续请求生效条件 |
| missing / expired | 分别显示文件缺失或已清理、超过保留期 |
| 切换尝试、关窗、离页 | 旧回执失效，关闭后焦点回到原按钮 |
| 过期配置或忙碌维护 | 展示服务端冲突，停止重放写入 |
| 任务默认入口 / 显式 tab=tasks | accounts / 普通任务页面 |
| 二级点击、数字键、搜索或账号直达 | 复用文档，一次导航对应一个顶层历史项 |
| 已打开普通弹窗后退或切页 / 旧详情回包 | 关闭旧窗口 / 保持关闭且刷新状态失效 |
| HTTP 缺少 Clipboard API，或 HTTPS 写入拒绝 | 在当前焦点域尝试选中复制，成功值须为完整 ID |
| 复制命令失败或异常 | 清理临时节点并恢复焦点，显示手动复制提示 |

### 5. Scenarios and Examples

- 正常：debug 请求显示“当时采集已关闭”→直达账号环境→空闲切换→后续请求使用新配置。
- 边界：上海与洛杉矶显示同一 UTC 时间的对应本地时间；历史零值与空值保持区别。
- 错误用法：把 bench 账号 ID 直接当作网关 ID。正确处理：按公开绑定字段筛选。
- 错误用法：仅凭 debug 提供采集读取按钮。正确处理：同时使用发生时采集状态。
- 错误用法：把降级 textarea 放到弹窗外，或仅凭点击显示复制成功。正确处理：保持弹窗焦点域，以真实复制结果决定提示。

- 正常：重试链显示两个账号各自名称邮箱；取消更新确认后重开恢复一分钟。错误用法：把最终账号资料套用到每次尝试，或用上次未提交的期限作为新确认默认值。正确处理：每次尝试独立读取投影，新确认使用统一默认值。
- 正常：从账号页打开额度窗口，后退到题库后窗口关闭。错误用法：数字键先写 iframe hash 再 push 顶层，或用完整 source 重建文档。正确处理：程序化导航先交给顶层，同 view 只替换内部 hash。

### 6. Tests Required

- `npm --prefix apps/web run build`；通过 Vue/TypeScript 和生产构建。
- `python deploy/flower2api/verify_management_ui.py --output .deploy/management-ui/combined`：实际产物、合成 API、两个时区、390px、版本单展开、导航历史、采集开关及异步关闭；覆盖长名称邮箱、跨账号尝试、资料缺失与空账号及原 ID 直达。
- 同一浏览器验证覆盖默认 accounts、六个内部页面、真实 iframe/文档身份、深链接参数、刷新/连续后退/前进、快捷键/搜索/账号直达、独立页面兼容、已打开弹窗与迟到详情收口，以及实际 app.js 静态版本标识。
- 原 `verify_environment_ui.py` 继续覆盖内核、时段、焦点、乱序和物理实测；所有浏览器模型调用为零。
- `verify_management_polish.py` 使用实际构建产物，覆盖 HTTPS、HTTP、权限拒绝和全部失败的列表/弹窗复制；独立安全页回读实际剪贴板，核对完整 ID 或失败时原值，断言临时节点清理及焦点恢复。品牌验收覆盖三个入口、24/40px 和深浅背景。
- `verify_system_update_browser.py` 核对 1280×900、390×900、390×300 的弹窗中心及按钮滚动可达性，取消/Esc/遮罩零安装写入，初开及取消重开默认一分钟、直接提交60秒、显式30分钟提交1800秒；恢复请求继续使用原操作 ID。
