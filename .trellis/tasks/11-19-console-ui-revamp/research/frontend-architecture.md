# Research: 控制台前端架构现状（为组件库 / 主题运行时改版做准备）

- **Query**: 样式入口与层次、现有组件、原生页加载、字体图标、终端、验证体系、构建发布、系统更新接口与步骤记录
- **Scope**: internal
- **Date**: 2026-11-19

---

## 1. 样式入口与层次

### 1.1 入口文件与引入顺序

| 入口 | 引入的 CSS（按顺序） | 证据 |
|---|---|---|
| `apps/web/index.html` | 无 `<link>`、无内联脚本，只挂 `/src/main.ts` | `apps/web/index.html:11` |
| `apps/web/src/main.ts` | ① `../../legacy-web/ui-foundation.css` → ② `./style.css` → ③ `./approved-design.css` → ④ `./proxy-design.css` | `apps/web/src/main.ts:2-5` |
| `apps/web/ui-preview.html` → `src/previews/ui-preview.ts` | ① `ui-foundation.css` → ② `style.css`（**不含** approved-design / proxy-design） | `apps/web/ui-preview.html:10`、`apps/web/src/previews/ui-preview.ts:3-4` |

按路由 / 组件懒加载（Vite 拆成独立 CSS chunk，进入页面时才插入 `<link>`，因此层叠顺序与访问顺序有关）：

| CSS | 引入方 | 证据 |
|---|---|---|
| `components/ui/controls/controls.css` | NumberInput / ChoiceSelect / InfoTooltip / SearchInput / DateTimeControl / TimeControl | `NumberInput.vue:3`、`ChoiceSelect.vue:6`、`SearchInput.vue:4` 等 |
| `apps/legacy-web/pagination.css` | `PageSizeSelect.vue` | `components/ui/controls/PageSizeSelect.vue:4` |
| `apps/legacy-web/capture-workspace.css` | `runtime/CaptureWorkspace.vue` | `components/runtime/CaptureWorkspace.vue:7` |
| `src/settings-design.css` | `Settings.vue` | `components/Settings.vue:20` |
| `src/request-design.css` | `RequestDiagnostics.vue` | `components/RequestDiagnostics.vue:7` |
| `src/native-environment.css` | `RuntimeEnvironments.vue` | `components/RuntimeEnvironments.vue:18` |
| `xterm/css/xterm.css` + `virtual:task-runtime-style.css`（legacy 8 个 CSS 经作用域改写） | `TasksWorkspace.vue` | `components/TasksWorkspace.vue:16-17` |

另有 13 个 Vue 文件带 `<style>` / `<style scoped>`（Nodes、TasksWorkspace、PlatformBadge、OperationFeedback、TaskProxyDialog、SessionPolicyBlocks、RequestDiagnostics、UiPreview、RunDetails、AccountNodeSelector、AccountNodeMigration、ExecutionNodeBadge、TimeControl）。其中 `TasksWorkspace.vue:109`、`TaskProxyDialog.vue:56`、`Nodes.vue:290` 为非 scoped 全局块。

构建产物确认：`dist/index.html` 只引入一个入口 CSS `index-*.css`，另有 11 个按需 chunk CSS（CaptureWorkspace、Nodes、RequestDiagnostics、RunDetails、RuntimeEnvironments、SessionPolicyBlocks、Settings、TasksWorkspace、controls、PlatformBadge、ExecutionNodeBadge）。

### 1.2 Tailwind 4 配置方式

- 无 `tailwind.config.*`；通过 Vite 插件 `@tailwindcss/vite` 接入（`apps/web/vite.config.ts:8`，`components.json` 中 `tailwind.config` 为空串、`css` 指向 `src/style.css`）。
- `src/style.css:1-2`：`@import "tailwindcss"; @import "tw-animate-css";`。`tw-animate-css` 提供 `animate-in / fade-in-0 / zoom-in-95` 等类，被 `ui/dialog/DialogContent.vue` 使用。
- `src/style.css:7`：`@custom-variant dark (&:is(.dark *));`（类名驱动；全仓没有任何代码给元素加 `.dark`，也没有 `prefers-color-scheme` 规则）。
- `src/style.css:9-48`：`@theme inline` 把 shadcn 变量映射成 Tailwind 主题：`--font-sans → var(--font-body)`、`--text-xs/--text-sm → --ui-font-small/--ui-font-body`、`--radius-sm/md/lg/xl` 由 `--radius` 计算、`--color-*` 全部指向同名 CSS 变量（background、card、popover、primary、secondary、muted、accent、destructive、border、input、ring、chart-1..5、sidebar-*）。
- `src/style.css:120-124`：`@layer base { * { @apply border-border outline-ring/50; } }`。
- **层叠关系**：`style.css` 中除 `@layer base` 外的全部业务规则、以及其余 `*-design.css`、`controls.css`、`ui-foundation.css`、任务虚拟 CSS 都是**未分层（unlayered）**规则，按 CSS Cascade Layers 规则会压过 Tailwind 的 `utilities` 层。实例：`style.css:535-541` 用 `[data-slot=button][data-variant=default|outline|ghost]` 覆盖了 `ui/button/index.ts` cva 产生的 `bg-primary` 等工具类。

### 1.3 Token 家族与定义位置（当前共 4 套并存）

| 家族 | 定义位置 | 说明 |
|---|---|---|
| shadcn 语义变量 `--background/--foreground/--card/--popover/--primary/--secondary/--muted/--accent/--destructive/--border/--input/--ring/--chart-*/--sidebar-*/--radius`，以及 `--font-body/--font-mono` | `src/style.css:50-85`（第一组，oklch 绿主色）→ 被 `src/style.css:127-137` 第二个 `:root` 覆盖（`--background:#f6f7fb`、`--foreground/--primary:#0e1726`、`--sidebar:#202235` 深色侧栏、`--radius:.75rem`）→ 再被 `src/approved-design.css:4` 覆盖 `--muted-foreground:#848894; --border:#e9e8ed` | 同名变量三处重复定义，最终值取最后加载者 |
| 控件 token `--ui-surface/--ui-field-surface/--ui-text/--ui-muted/--ui-border/--ui-border-hover/--ui-accent/--ui-focus/--ui-focus-shadow/--ui-selected/--ui-danger/--ui-font` | `src/components/ui/controls/controls.css:2-15` | spec 声明的“控件 token 唯一源”（`.trellis/spec/web/frontend/ui-guidelines.md:37`） |
| 阅读尺寸 `--ui-font-small/body/card/heading/page`、`--ui-control-height/compact/space`、`--ui-feedback-surface/text` | `apps/legacy-web/ui-foundation.css:2-38`（三档：默认 / ≥1920 / ≥2560） | Vue 与原生独立文档共用；同文件还定义了 toast、确认框、操作结果气泡 `.fui-*` 样式（`ui-foundation.css:41-82`） |
| 按钮 token `--button-surface/border/text/hover/hover-border/primary/primary-hover` | `src/style.css:534` | 只被 `style.css:535-570` 的 `[data-slot=button]` 规则使用 |
| 原生 token `--bg/--surface/--surface-2/3/--border/--text/--text-dim/--muted/--line/--amber/--running/--success/--failed/--body-font/--mono` 等 46 个 | `apps/legacy-web/style.css:6-41`（暗色）、`style.css:1280`（`:root[data-theme="light"]`）、`approved-design.css:4`（`:root.console-design{...}`）、`console.css:9` 等 | 与 Vue 同名冲突的只有 `--border`、`--muted` 两个（脚本对比 legacy 8 个 CSS 与 Vue 全局 CSS 的变量名得出） |

### 1.4 shadcn 变量的使用者

- **Tailwind 工具类**（`bg-primary`、`text-muted-foreground`、`border-border` 等）按文件统计：`Accounts.vue` 58、`SystemUpdates.vue` 22、`SchedulingDetails.vue` 20、`NativeStageDetails.vue` 6、`RequestDiagnostics.vue` 2、`SessionPolicyBlocks.vue` 1、`App.vue` 1（`bg-background`，`App.vue:7`）；ui 基础组件内：button/index.ts 7、badge/index.ts 5、Input 3、Dialog*Content 各 2、table / tabs / card / separator / textarea / DialogDescription 各 1。
- **CSS `var()`**：`style.css` 内 `var(--border)` 28、`var(--muted-foreground)` 14、`var(--primary)` 10、`var(--foreground)` 10、`var(--card)` 7 等；`approved-design.css` 4 处；`settings-design.css` 1 处。
- legacy-web 的 CSS **完全不使用** shadcn 变量（`var(--primary|--background|--foreground|--card|--ring)` 计数 0），只大量使用 `--ui-font-small`（511 次）、`--ui-font-body`（121 次）；`var(--font-mono)` 3 次（带回退）。
- 硬编码颜色概况（供 R1 参考）：apps/web 6 个 CSS 文件十六进制颜色计数 style.css 297、approved-design.css 193、native-environment.css 102、proxy-design.css 66、request-design.css 18、settings-design.css 9；`!important` 计数 style.css 40、native-environment.css 11、request-design.css 8、settings-design.css 1。Vue 文件内十六进制颜色以 `runtime/RunDetails.vue`（120）最多；Tailwind 调色板类（如 `text-emerald-600`）共 63 处，其中 `Accounts.vue` 45、`SystemUpdates.vue` 7、`SchedulingDetails.vue` 5、`lib/subscription.ts` 3。

---

## 2. 现有组件

### 2.1 `apps/web/src/components/ui/` 各目录实现方式与引用量

引用文件数 = 从该目录 import 的其它文件数（排除目录自身）；标签数 = 全部 `.vue` 中 `<Tag` 出现次数。

| 目录 | 实现方式 | 引用文件数 | 主要标签次数 |
|---|---|---|---|
| `button` | cva（`button/index.ts:6-37`，6 种 variant、6 种 size）+ reka-ui `Primitive`（`Button.vue:5,23`），输出 `data-slot/data-variant/data-size` | 24 | `<Button` 120 |
| `badge` | cva（`badge/index.ts`）+ reka `Primitive` | 2（Settings、SessionPolicyBlocks） | 2 |
| `card` | 纯 Vue + Tailwind 类（`card/Card.vue`：`bg-card ... rounded-xl border py-6 shadow-sm`） | 3（Login、SystemUpdates、Accounts） | `<Card` 4 |
| `dialog` | reka-ui `DialogRoot/Portal/Content/Overlay/Close`（`dialog/DialogContent.vue:61-66`），关闭图标用 lucide `X` | 12 | `<DialogContent` 14 |
| `input` / `textarea` | 纯 Vue + `@vueuse/core` `useVModel` | 6 / 4 | `<Input` 27、`<Textarea` 5 |
| `label` / `separator` | reka-ui 包装 | 0 / 0（未被业务引用） | — |
| `tabs` | reka-ui `Tabs*` | 0（未被业务引用） | — |
| `table` | 纯 Vue；`table/utils.ts` 引 `@tanstack/vue-table`（业务未使用 tanstack） | 2（SessionPolicyBlocks、Settings） | `<TableRow` 7 |
| `controls` | 自定义 `fui-*` 类 + `controls.css`；ChoiceSelect 用 reka `Select*`，InfoTooltip 用 reka `Tooltip*`，DateTimeControl 用 reka `Popover*`+`Calendar*`，TimeControl 用 reka `Popover*`；NumberInput / SearchInput 纯 Vue；Pagination 复用 `Button` | 19 | ChoiceSelect 28、NumberInput 23、InfoTooltip 13、SearchInput 13、Pagination 7、DateTimeControl 3、TimeControl 2、PageSizeSelect 1 |
| `feedback` | FeedbackHost（原生 Popover API `popover="manual"` + `showPopover()`，`feedback/FeedbackHost.vue:23,66`）、ConfirmationDialog（复用 ui/dialog + button）、OperationFeedback（reka `Popover*`） | 10 | FeedbackHost 2、OperationFeedback 3 |
| `icon` | 自定义 SVG sprite 组件工厂（见 §4） | 24 | — |

其它：业务中还有 3 处直接使用原生 `<dialog>` + `showModal()`：`Dashboard.vue:152`（系统更新面板）、`SystemUpdates.vue:290`（安装确认）、`previews/UiPreview.vue:70`。`lib/utils.ts` 的 `cn()` = `twMerge(clsx())`。

现有组件演示页 `src/previews/UiPreview.vue`（109 行）只演示 NumberInput、ChoiceSelect、InfoTooltip、SearchInput、通知 / 确认 / OperationFeedback 与原生 dialog 内浮层（`UiPreview.vue:3-6,38-78`），样式用 `--ui-*` token（`UiPreview.vue:82-108`）。

### 2.2 `apps/web/src/components/` 业务组件清单（行数，`wc -l`；注意多数文件为长行压缩风格，行数偏小）

| 文件 | 行数 | 文件 | 行数 |
|---|---|---|---|
| Accounts.vue | 1608 | Settings.vue | 864 |
| RequestDiagnostics.vue | 405 | SystemUpdates.vue | 292 |
| Nodes.vue | 290 | SchedulingDetails.vue | 230 |
| Proxies.vue | 218 | SessionPolicyBlocks.vue | 214 |
| Tokens.vue | 203 | Dashboard.vue（外壳） | 157 |
| RuntimeEnvironments.vue | 124 | TasksWorkspace.vue | 112 |
| NativeStageDetails.vue | 85 | AgyAccountUsage.vue | 68 |
| Login.vue | 58 | UsageWindowStats.vue | 57 |
| ProxyPicker.vue | 53 | AgyQuotaRow.vue | 41 |
| AppNavigation.vue | 28 | AccountFilterSelect.vue | 26 |
| AccountScopePicker.vue | 23 | PlatformBadge.vue | 17 |
| runtime/RunDetails.vue | 154 | runtime/runtimeScope.ts | 125 |
| runtime/AccountNodeMigration.vue | 118 | runtime/AccountNodeSelector.vue | 96 |
| runtime/nodeApi.ts | 92 | runtime/TaskProxyDialog.vue | 64 |
| runtime/runtimeApi.ts | 60 | runtime/CaptureWorkspace.vue | 59 |
| runtime/EnvironmentKernel.vue | 53 | runtime/runApi.ts | 48 |
| runtime/ExecutionNodeBadge.vue | 44 | runtime/EnvironmentResources.vue | 39 |
| runtime/environmentLabels.ts | 35 | runtime/RunWindowForm.vue | 26 |
| runtime/taskProxyApi.ts | 21 | runtime/captureEvidence.ts | 12 |

此外：`api.ts` 773、`router.ts` 99、`App.vue` 8、`main.ts` 9。外壳结构：`Dashboard.vue:107-156`（`.console-shell` > `aside.console-sidebar` + `.console-workspace` > `header.console-toolbar` + `main#console-content`）；导航分组在 `AppNavigation.vue:9-14`（网关 / 资源 / 工作区 / 系统设置）。

---

## 3. 原生页加载（任务与工程、运行环境）

### 3.1 嵌入方式：**同文档挂载，不用 iframe**

- `/tasks` → `TasksWorkspace.vue`。构建期 Vite 插件 `apps/web/runtimeModule.ts` 读取 `apps/legacy-web/index.html` 的 `<body class="work-console">` 片段作为模板（`runtimeModule.ts:48-50`），把 `ui-controls.js / projects.js / environments.js / app.js` 拼成虚拟 ES 模块 `virtual:task-runtime`（`runtimeModule.ts:8,51-58`）。运行时 `TasksWorkspace.vue:83-89` 在 `div.task-runtime.console-design.embedded-tasks`（`TasksWorkspace.vue:98`）里 `innerHTML=template` 并调用 `mount(scope)`；`createRuntimeScope`（`runtime/runtimeScope.ts:13-60`）用 Proxy 把 `document.documentElement/body/querySelector` 限定到任务根。spec 明确“运行时不创建 iframe、不执行脚本字符串”（`ui-guidelines.md` “原生工作区生命周期”节）。
- `TasksWorkspace.vue:84` 固定 `host.dataset.theme='light'`；`verify_task_account_config.py:138` 断言该属性为 `light`。
- `/environments` → `RuntimeEnvironments.vue` 是**纯 Vue 实现**，只沿用原生类名（根 `.native-runtime.runtime-environments`，`RuntimeEnvironments.vue:107`），样式来自 `src/native-environment.css`（Vite 打包，不经 Rust 白名单）。
- 旧独立文档 `/runtime/`（`apps/legacy-web/index.html`）仍保留兼容（spec “旧`/runtime/`地址保留独立运行兼容”），由 orchestrator 以 StaticFiles 挂载 `/webui`（`services/orchestrator/main.py:145,14738-14739`），经网关 `/runtime/*` 桥转发（`services/gateway/src/service/runtime_bridge.rs:880-881`、`http_bridge` `:652-720`）。`app.js:195-207` 仍留有 iframe 时代的 `window.parent.postMessage` 兼容逻辑。

### 3.2 原生 CSS 的加载与提供

- **Vue 内嵌**：`runtimeModule.ts:9` 固定 8 个 legacy CSS（style、environments、console、approved-design、work-design、environment-design、capture-workspace、pagination），经 PostCSS AST 改写：删除全部 `@font-face`（`:14`）；`html → .task-runtime`、`body → .runtime-body`、`:root → .task-runtime`（`:19-20`）；其余选择器前缀 `.task-runtime `；以 `.console-design` 或 `[data-theme]` 开头的选择器直接并到根上（`.task-runtime.console-design`、`.task-runtime[data-theme=…]`，不加后代空格）（`:21-30`）；相对 `url()` 改写为 `/runtime/…`（`:34`）。图标引用 `approved-icons.svg#` 改写为 `/runtime/approved-icons.svg#`（`:50-51`）。`ui-foundation.css` **不在**该列表，它由 `main.ts:2` 全局引入（不加作用域）。
- **独立文档**：`legacy-web/index.html:8-19` 以 `<link>` 加载 xterm CDN CSS（镜像构建时改为 `vendor/`，`images/v3/Dockerfile:89`）与 9 个本地 CSS（带 `?v=20261116-workspace-experience` 版本参数），`index.html:21-22` 内联脚本设置 `data-theme='light'`。
- **Rust 白名单**：`runtime_bridge.rs:421-453` `browser_path_allowed` 对 GET/HEAD 精确匹配 `/index.html`、4 个 JS、9 个 CSS、`/approved-icons.svg`、`/fonts/inter-variable.woff2`、`/fonts/jetbrains-mono-variable.woff2`、`/vendor/xterm.{js,css}`、`/vendor/xterm-addon-fit.js`；同时拒绝 `%`、`\`、`.`/`..` 段（`:423-425`）。配套测试 `design_assets_remain_available_through_runtime_bridge`（`runtime_bridge.rs:1136-1165`）逐项断言。
- **新增原生资源的要求**（spec `ui-guidelines.md:298`）：新原生 CSS、JS、字体、SVG 必须同步 `browser_path_allowed` 精确只读白名单与静态版本参数，并验证真实桥接路径。实际需要同步的位置：① `runtime_bridge.rs:426-449` 匹配臂；② 同文件测试 `:1136-1165`；③ `legacy-web/index.html` `<link>` 及 `?v=`；④ 若需进入 Vue 内嵌任务页，还要加入 `runtimeModule.ts:9` 的 `styles`（会被改写作用域）。镜像侧 `COPY webui /webui` 整目录复制（`images/v3/Dockerfile:83`），无需改 Dockerfile。验证夹具直接从 `apps/legacy-web` 读 `/runtime/*`（`deploy/flower2api/verify_environment_ui.py:209-211`），**不经过**白名单。
- 先例：`ui-foundation.css`、`pagination.css`、`capture-workspace.css` 均放在 `apps/legacy-web/`，Vue 侧以相对路径 import、独立文档以 `<link>` 引用，同一份文件双端共用（`main.ts:2`、`PageSizeSelect.vue:4`、`CaptureWorkspace.vue:7`）。

### 3.3 原生页能否读取 Vue 文档根上的 CSS 变量

- **Vue 内嵌任务页：能**。`.task-runtime` 位于 `#app` 内，自定义属性从 `html:root` 继承；只有被 legacy CSS 在作用域根上重新定义的同名变量会被覆盖——legacy `style.css:6` 的 `:root{…}` 改写为 `.task-runtime{…}`，`approved-design.css:4` 的 `:root.console-design{…}` 改写为 `.task-runtime.console-design{…}`，`style.css:1280` 的 `:root[data-theme="light"]` 改写为 `.task-runtime[data-theme="light"]`。与 Vue 冲突的同名变量仅 `--border`、`--muted`。Teleport 进原生宿主的 Vue 组件及挂到 body 的浮层（InfoTooltip、ProxyPicker、Pagination、RunDetails 等，`TasksWorkspace.vue:99-106`）直接使用 Vue 根变量。
- **独立 `/runtime/` 文档：不能**，它是另一份文档，只能读自己 `<link>` 加载的 CSS（目前共享的只有 `ui-foundation.css`）。若要共用新 token，token 文件需放在 `apps/legacy-web/` 并走白名单（同 `ui-foundation.css` 模式）。

---

## 4. 字体与图标

### 4.1 字体

- 文件两份、内容相同（md5 一致）：`apps/web/src/assets/fonts/{inter-variable,jetbrains-mono-variable}.woff2`+`LICENSE.txt`，`apps/legacy-web/fonts/` 同名三件。
- `@font-face`：Vue 在 `apps/web/src/style.css:4-5`（构建后带 hash 输出到 `/assets/`）；原生独立文档在 `apps/legacy-web/approved-design.css:2-3`（`url('fonts/…')`，经 `/runtime/fonts/*.woff2` 白名单）。Vue 内嵌时 legacy 的 `@font-face` 被 `runtimeModule.ts:14` 删除，改用 Vue 的定义。
- 字体变量：Vue `--font-body/--font-mono`（`style.css:83-84`）、`--ui-font`（`controls.css:14`）；原生 `--body-font/--mono`（`legacy-web/approved-design.css:4`，另有旧值 `console.css:9`、`style.css:40`）。
- 设计稿 `research/design-v2/mock.css` 的 `@font-face` 用相对路径指向 `apps/web/src/assets/fonts/`。许可证说明 `doc/design/font-licenses.txt`。

### 4.2 图标

- **Vue 主体用 SVG sprite**：`components/ui/icon/index.ts:2-17` 以 `@/assets/approved-icons.svg?url&no-inline` 生成 `<svg><use href="…#i-name"></svg>` 组件（默认 19px、描边 1.7），导出 31 个 lucide 同名别名（Pencil→i-edit、Server→i-server 等，`icon/index.ts:20-52`）；24 个文件从 `ui/icon` 引入。sprite 含 29 个 symbol（panel、copy、edit、trash、globe、users、grid、key、wave、box、task、settings、arrow、chevron、plus、search、refresh、close、check、alert、shield、clock、download、menu、more、play、spark、logout、server）。
- **仍直接用 lucide-vue-next 的 10 个文件**：`Proxies.vue:4`（ChevronDown、LoaderCircle）、`ProxyPicker.vue:3`（Globe、ChevronDown、Check）、`RuntimeEnvironments.vue:5`（Sparkles）、`SystemUpdates.vue:4`（Download、ChevronDown、ChevronRight、RefreshCw、Layers、Cpu、Check、ArrowRight）、`ui/dialog/DialogContent.vue:5` 与 `DialogScrollContent.vue:5`（X）、`ui/controls/ChoiceSelect.vue:3`、`DateTimeControl.vue:4`、`TimeControl.vue:3`、`Pagination.vue:3`。
- **原生页用同名 sprite 文件** `apps/legacy-web/approved-icons.svg`（28 个 symbol，比 Vue 版少 `i-server`，两文件 md5 不同）：`index.html` 33 处 `<use href="approved-icons.svg#i-…">`，JS 中 `app.js:403` `runtimeIcon()`、`environments.js:174`、`projects.js:964`；另有 3 处内联 `<svg>`。
- 设计稿 `research/design-v2/icons.js` 是 52 个 lucide 风格内联 path（含 server、palette、sun、moon、monitor、upCircle、history 等），渲染函数为 `ic(name)` 生成内联 `<svg class="i">`。

---

## 5. 终端（xterm）

- 依赖：`xterm 5.3.0`、`xterm-addon-fit 0.8.0`（`apps/web/package.json`）。Vue 内嵌时由 `runtimeScope.ts:57` 的 `loadRuntimeTerminal` 动态 `import('xterm')`/`import('xterm-addon-fit')`，并以 `ScopedTerminal` 包装便于离页释放（`runtimeScope.ts:97-103`）；`TasksWorkspace.vue:16` 全局引入 `xterm/css/xterm.css`。独立文档用 `vendor/xterm.*`（镜像内由 npm pack 解出，`images/v3/Dockerfile:10-14,84-89`）。
- 唯一 `new Terminal` 位于 `apps/legacy-web/app.js:1591-1603`（`attachTerminal`），主题颜色**硬编码**：background `#0a0b09`、foreground `#e8e1cf`、cursor `#ffb649`，以及 black/red/green/yellow/blue/magenta/cyan/white 8 色；字体 `"JetBrains Mono Variable"` 13px。调用方：授权登录 `#acc-login-xterm`（`app.js:1395-1398`）、续聊 `#continue-xterm`（`app.js:2867`）。
- 容器样式：`legacy-web/style.css:1257-1273` `.xterm-host`（背景 `#000`；`[data-theme="light"]` 下 `#14130f`，注释“浅色模式下终端仍保持深色”）、`.xterm-viewport{background:transparent !important}`；`work-design.css:749` `#acc-login-xterm` 背景 `#272b3d`。Vue 侧无任何 xterm 主题代码。

---

## 6. 验证体系（`deploy/flower2api/`）

### 6.1 运行方式

- 全部 UI 脚本为 **Python Playwright（Chromium）**，从仓库根直接执行 `python3 deploy/flower2api/<脚本>.py`（脚本以同目录模块互相 import；本机 `playwright` Python 包可导入）。证据输出到 `.deploy/frontend-sidebar-refresh/<子目录>/`（git 忽略）。
- **依赖 dist 构建**：夹具链最终都落到 `verify_environment_ui.Fixture`（`verify_environment_ui.py:61-218`），用 `context.route('**/*')` 在浏览器前拦截：`/runtime/*` 读 `apps/legacy-web`，`/`、`/environments`、`/tasks`、`/requests`、`/updates` 返回 `apps/web/dist/index.html`，其余静态文件读 `apps/web/dist`，接口返回合成 JSON；缺 dist 时报“先执行 npm run build”（`:235-238`）。继承链示例：`export_frontend_preview.PreviewFixture(ManagementFixture)` 传入 `ROOT/'apps/web/dist'`（`export_frontend_preview.py:15-20`）→ `AccountDesignFixture` → `ProxyDesignFixture` → `InteractionFixture` → `RunDetailFixture` → `TokenDesignFixture` → `RemainingPagesFixture` → `WorkspaceFixture` → `DashboardUpdateFixture`。
- `serve_design_preview.py`：本地 `ThreadingHTTPServer`（默认 4188，`:159-165`），启动时冻结 `apps/web/dist` + `.deploy/frontend-sidebar-refresh/preview-assets` + `/design-review/` 对照截图（`:105-110`），页面白名单 `{'/','/login','/proxies','/requests','/tokens','/settings','/updates','/environments','/tasks'}`（`:111`，不含 `/nodes`、`/session-blocks`），接口走 `CaptureFixture` 合成数据。
- `verify_ui_controls.py`：**不用 dist**，访问 Vite dev server 的 `http://127.0.0.1:4187/ui-preview.html`（`:113`），spec 给出的命令为 `npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187 --strictPort`（`ui-guidelines.md` §6）。`ui-preview.html` 不在生产构建内（`vite.config.ts` 无 `rollupOptions.input`，dist 只有 `index.html`）。
- 发行校验 `verify_release_tests.py:23-28` 只跑 unittest，不含任何 UI 脚本。

### 6.2 引用 `doc/design/flower2api-concept.html` 的 13 个脚本

全部是“Playwright 打开原型 `file://` + 打开真实构建，同视口读 `getComputedStyle`/DOM 比较”，**没有脚本解析原型 CSS 文本**；唯一读 CSSOM 规则的是生成器 `extract_environment_styles.py`。

| 脚本 | 比对方式 | 是否断言 |
|---|---|---|
| `verify_exact_design.py` | 21 组选择器映射（筛选、品牌、版本按钮、侧栏、卡片、页标题、主按钮、用量…，`:10-32`），比较 11 个计算属性 fontFamily/fontSize/fontWeight/lineHeight/letterSpacing/color/backgroundColor/borderRadius/padding/gap/boxShadow（`:9`）；CDP `CSS.getPlatformFontsForNode` 比实际字体（`:70-83`）；1440/720/390 截图与横向溢出 | 断言零差异（`:91`） |
| `audit_full_design.py` | 6 个页面 + 任务各页签，收集可见 button/th/h1/h2/h3/label 计算样式并按文本配对（`:8,26-31`） | 只断言无页面错误，差异写 `differences.json` |
| `audit_token_task_design.py` | 令牌与任务入口计算样式采样（`:14`） | 无断言，仅存证据 |
| `audit_environment_proxy_design.py` | 复用上一脚本 `sample` 采样环境 / 代理 | 无断言 |
| `verify_update_design.py` | 系统更新弹窗 9 个排版属性（`:13`） | 断言零差异、只发 check 请求、无溢出（`:17-22`） |
| `verify_dialog_typography.py` | 代理编辑等弹窗 9 个排版属性（`:6`） | 断言宽 680、基线对齐、零差异（`:18-27`） |
| `verify_request_detail_design.py` | 请求详情四分区计算样式 | 断言零差异（`:33`） |
| `verify_diagnostic_alignment.py` | 诊断摘要与操作按钮计算样式 + 硬编码值（12px、`rgb(253,240,243)`） | 断言（`:14-19`） |
| `verify_task_feedback_styles.py` | 任务深层控件计算样式 | 断言零差异（`:25`） |
| `verify_task_account_config.py` | 原生任务配置弹窗计算样式 + 真实配置 API + 独立 SQLite | 断言（`:116-138`，含 `data-theme=='light'`） |
| `verify_ui_refinements.py` | 账号列数、卡片宽度、用量气泡、悬停计算样式 | 断言（`:24-50`） |
| `verify_design_parity.py` | 账号编辑分区标题 / 页签文本、抽屉宽度、更新弹窗宽度（bounding box）+ 行为 | 断言 |
| `extract_environment_styles.py` | 从原型 CSSOM 提取 `.environment-*/.workspace-*` 等规则，**写回** `apps/legacy-web/environment-design.css`（`:12-13`） | 生成器，非验证 |

### 6.3 只测行为 / 非原型对比的 UI 脚本（节选）

- 依赖 dist 的行为脚本：`verify_accounts_design`、`verify_proxy_design`、`verify_tokens_design`、`verify_remaining_pages`、`verify_runtime_workspace_design`、`verify_native_environments`、`verify_environment_cpu_summary`、`verify_page_sizes`、`verify_shared_pagination`、`verify_workspace_stability`、`verify_dashboard_update`、`verify_system_update_browser`、`verify_session_policy_blocks_ui`、`verify_cluster_ui`、`verify_management_ui`、`verify_console_ui`、`verify_viewport_interactions` 等（共 57 个 Playwright 脚本，13 个对原型）。
- 行为脚本中含**硬编码样式值**的断言（主题改值会受影响）：`verify_shared_pagination.py:14-43`（当前页 `rgb(119,100,143)`=#77648f、白字、普通页 `rgb(82,100,126)`）；`verify_agy_accounts_ui.py:88,122`（用量条 `rgb(207,89,100)`、`rgb(212,166,89)`）；`verify_console_ui.py:126`（html 字号 14/15/16px）；`verify_tokens_design.py:48`（编辑窗宽 760px）；`verify_run_detail_design.py:45`（运行详情宽 `min(900,width-28)`）；`to_have_css` 另见 `verify_viewport_interactions`、`verify_interaction_parity`、`verify_design_parity`、`verify_task_feedback`、`verify_native_runtime_versions`、`verify_agy_request_records`、`verify_accounts_design`。
- 选择器耦合：大量脚本依赖现有类名（`.brand-update`、`.approved-update-dialog`、`.console-sidebar`、`.account-card`、`.task-runtime` 等），例：`verify_dashboard_update.py:71-103`、`verify_update_design.py:21`、`verify_design_parity.py:73`、`audit_full_design.py:24`。

---

## 7. 构建与发布

- 命令：`npm run build` = `vue-tsc -b && vite build`（`apps/web/package.json`）；产物 `apps/web/dist/`（`.gitignore` 忽略）。只有 `dev/build/preview` 三个脚本，**无 lint、无测试脚本**，`node_modules/.bin` 中无 eslint / prettier / vitest。类型检查严格（`tsconfig.app.json`：`strict`、`noUnusedLocals`、`noUnusedParameters`）。
- 前端单测：`apps/web/tests/accountUpdate.test.mjs`、`subscription.test.mjs`（`node:test`，直接 import `.ts`），spec 记录的运行方式为 `node --experimental-strip-types --test web/tests/accountUpdate.test.mjs`（`.trellis/spec/gateway/backend/service-architecture.md:1608`）。
- 进入镜像：`deploy/flower2api/manage.py:510-516` 把 `apps/web`（逻辑名 `cc2api/web`）、`apps/legacy-web`（逻辑名 `webui`）复制进临时构建快照（忽略 `node_modules` 等，`manage.py:286-293`；映射见 `source_layout.py:6-15`）。`images/v3/Dockerfile:2-9` frontend 阶段 `npm ci` → 复制 web 与 legacy-web 为相邻目录 → `npm run build`；`:25` 把 dist 放到 `/source/apps/web/dist` 供 Rust `rust-embed` 编译期嵌入（`services/gateway/src/handler/router.rs:2126-2128` `#[folder = "../../apps/web/dist"]`）；`:91` 另复制到 `/app/web/dist`。**宿主无需预先构建**，镜像内自行构建。
- 网关路由：SPA 页面必须在 `router.rs:145-161` 显式登记（当前 `/login,/tokens,/requests,/session-blocks,/tasks,/settings,/proxies,/updates,/environments,/nodes`，测试 `router.rs:4289-4315`）；静态资源只开放 `/assets/*rest` 与 `/favicon.svg`（`router.rs:164-166`），`public/` 下新增其它文件不会被网关提供。网关未设置 CSP 头（全仓 grep 无 `Content-Security-Policy`）。
- 组件身份（决定 control 镜像是否需重建）：`deploy/flower2api/system_release.py:101-103` 对 control 角色只计入 `webui`、`cc2api/web/src`、`cc2api/web/package-lock.json`，**不含** `apps/web/index.html`、`runtimeModule.ts`、`vite.config.ts`、`package.json`。

---

## 8. 系统更新接口与步骤记录

### 8.1 前端类型与接口（`apps/web/src/api.ts`）

- `SystemUpdateOperation`（`api.ts:363-377`）：`operation_id`、`action: 'prepare'|'install'|'rollback'`、`phase: string`、`target_release`、`created_at`、`updated_at`、`error?`、`blockers?: string[]`、`cancel_requested?`、`cluster_nodes?: {phase, nodes[{node_id,name?,phase,running,preparation?}]}`、`database_snapshot?: {state,completed_at,bytes}`、`database_migrations?: Record<string,{state,target_version}>`、`cleanup?: {status,removed,retained?}`。**当前没有步骤历史字段**。
- `SystemUpdateStatus`（`api.ts:385-399`）含 `operation?: SystemUpdateOperation | null`、`busy`、`revision`、`history[]`、`components`、`environments`、`checked_at`、`check_error`。
- 接口（`api.ts:692-700`）：`systemUpdateStatus` GET `/runtime/api/system-updates/status`；`systemUpdateReleases` GET `.../releases`；`systemUpdateCheck` POST `.../check`；`systemUpdateInstall(action)` POST `.../install|rollback` 返回 `SystemUpdateOperation`；`systemUpdateControl(id, 'cancel'|'recover', revision)` POST `.../operations/{id}/{action}`；另有 `systemPlatformVersion` GET `.../version`（`:690`）。
- `SystemUpdates.vue`：阶段中文表 `:39-45`（含 `restoring_data`）；取消允许 `phase ∈ {preparing, draining}`（`:49`）、恢复允许 `{reconcile, succeeded_cleanup_pending}`（`:50`）；轮询 busy/检查中 2s、空闲 10s、失败指数退避上限 30s（`:134`）；等待期限 `DEFAULT_DRAIN_MINUTES = 1`（`:31`），校验 1～120 分钟（`:178-179`），后端合同允许 60～7200 秒（`services/orchestrator/system_update_contract.py:345`）。

### 8.2 更新器写入路径（`deploy/flower2api/system_updater.py`）

- 持久化：每个操作一份 `state_root/operations/<uuid>/operation.json`，`_record()` 原子写入并同时写 `state.json`（`:104-111`）；读取 `_operation()`（`:113-116`），上限 `STATE_LIMIT=8MiB`（`:36`）。
- 创建：`submit()` 初始 `phase='preparing'`、`created_at/updated_at=utc_now()`（`:366-368`），之后启动 `_execute` 线程（`:372-374`）。
- 阶段推进：`_phase()` 只做 `operation.update(phase=…, updated_at=utc_now(), **fields)` 后 `_record`（`:377-380`），**覆盖**而非追加；`_finish()` 清 `active_operation`、写 `completion_revision` 后调用 `_phase`（`:386-390`）。
- `_execute` 实际顺序（`:392-490`）：`preparing` →（prepare 动作）`prepared`（`:401`）/ 取消 `cancelled`（`:398`）→ `draining`（`:405`；等待期间每 0.5s 以相同 phase 带 `blockers` 重复调用 `_phase`，`:416-419`）→ `switching`（`:429`，作为取消边界先写一次）→ schema v2 时 `snapshotting`（`:435`）→ 目标 v2 时 `migrating`（`:439`）→ 再次 `switching`（`:441`）→ `verifying`（`:443`）→ `committing`（`:450`）→ `cleaning`（`:462`）→ `succeeded`（`:497`）或 `succeeded_cleanup_pending`（`:499`）。异常分支：`failed`（`:469,473`）、`reconcile`（`:475,487`）、`restoring`→`restored`（`:480-485`）。spec 阶段描述见 `.trellis/spec/platform/deploy/platform-online-update.md:85`。
- **绕过 `_phase` 的写入**：宿主恢复 `system_update_host.py:1103,1108` 直接赋值 `operation['phase']='restoring_data'/'restoring'` 后经 `save()`（= `lambda: self._record(operation)`）落盘，不更新 `updated_at`。
- 恢复 / 控制：`control()`（`:501-531`）、`_recover()`（`:533-570`，可写 `cleaning/failed/restoring/restored/reconcile`）、启动续接 `resume()`（`:572-587`）。终态集合 `TERMINAL={'succeeded','succeeded_cleanup_pending','failed','restored','cancelled'}`（`services/orchestrator/system_update_contract.py:35`），`DONE = TERMINAL | {'prepared'}`（`system_updater.py:35`）。

### 8.3 状态接口返回路径

浏览器 `GET /runtime/api/system-updates/status` → 网关 `http_bridge` 白名单 `system-updates/{status|releases|version|operations/<uuid>}`（`runtime_bridge.rs:543-560`）→ orchestrator `GET /api/system-updates/status`（`services/orchestrator/system_updates.py:458-463`，追加 `environments`）→ `updater_request` 经 Unix socket `updater.sock`（`system_updates.py:151-173`，响应读取上限 `MANIFEST_LIMIT=131072` 字节，`system_update_contract.py:32`）→ 更新器 `UpdateHTTPHandler` `/status`（`system_updater.py:615-616`）→ `SystemUpdater.status()`（`:210-231`）→ `operation` 字段由 `_public_operation()` 生成。

- `_public_operation()`（`system_updater.py:233-235`）是**显式键白名单**：`operation_id, action, phase, created_at, updated_at, target_release, error, blockers, cancel_requested, cleanup, environment_results, database_snapshot, database_migrations, cluster_nodes`。新增步骤记录字段必须加入此白名单才能返回前端。（`environment_results` 已返回但前端类型未声明。）
- 同一 `_public_operation` 也用于 `GET /operations/<id>`（`:237-244`）、`submit` / `control` 的返回值。

### 8.4 `/updates` 入口

- `router.ts:49`：`{ path: 'updates', name: 'updates', component: SystemUpdates.vue }`（dashboard 子路由，直接访问渲染整页）。
- `Dashboard.vue`：品牌旁版本号 `<a href="/updates" class="brand-update">`（桌面 `:114-116`，移动抽屉 `:137`），`openUpdatePanel` 拦截普通点击（修饰键放行走深链接）打开原生 `<dialog class="approved-update-dialog">` 并内嵌 `<SystemUpdates embedded>`（`:89-103,152-155`）；路由变化时关闭面板（`:103`）；页头标题映射含 `updates:'系统更新'`（`:70`）。`has-update` 由 `refreshUpdateMetadata` 比较目录首项与 `current_release` 得出（`:33-53`）。
- 网关 SPA 已登记 `/updates`（`router.rs:154`）；验证夹具亦把 `/updates` 当 SPA 页面（`verify_environment_ui.py:210`、`serve_design_preview.py:111`、`verify_system_update_browser.py:104,129`）。

---

## Related Specs

- `.trellis/spec/web/frontend/ui-guidelines.md` — 视觉 token 表（`:35-57`）、原生资源白名单条款（`:298`）、原生工作区生命周期（`:334-352`）、测试命令（`:239-253`）。
- `.trellis/spec/legacy-web/frontend/component-guidelines.md` — 原生组件规范。
- `.trellis/spec/platform/deploy/platform-online-update.md` — 更新阶段与状态字段合同（`:71`、`:85`）。

## Caveats / Not Found

- 未找到任何 ESLint / Prettier / Vitest 配置；前端质量门只有 `vue-tsc` 与两个 `node:test` 文件。
- 未发现运行时主题切换、`.dark` 类或 `prefers-color-scheme` 的现有实现；`index.html` 当前无内联脚本。
- PRD 中“`verify_exact_design.py` 按原型 CSS 逐项比对”实际是比对**渲染后的计算样式**（非解析 CSS 文本）。
- 行数统计基于 `wc -l`，多数 Vue / CSS 文件为长行风格，行数不反映代码量。
- 第 6.3 节行为脚本清单为节选，未逐一阅读其断言细节。
