# Directory Structure

> 本项目前端代码的组织方式。

---

## Overview

前端是**纯静态资源 + 原生 JavaScript**,**零构建** —— 没有 npm、没有 webpack/vite、没有 framework、没有 TypeScript、没有 bundler。三个文件直接由 FastAPI 的 `StaticFiles` 在 `/` 下挂出。

**核心理念**:WebUI 只服务 P1 内部使用,加载几十个题目卡片 + 一个 SSE 长连。为这点交互引 React 工具链反而拖慢迭代。**只要三个文件够用,就保持三个文件**。

环境模块已独立为 `apps/legacy-web/environments.js`、`apps/legacy-web/environments.css`，由 `index.html` 顺序装载；共享 state、API、路由与时段表单仍在 `app.js`。该模块的行为和样式作用域见 [组件规范](component-guidelines.md) 的环境页场景。

---

## Directory Layout

```
apps/legacy-web/
├── index.html        所有视图模板 + modal + 外部依赖(xterm.js CDN)
├── app.js            路由 + state + 4 个 render* + login 两步流 + 主题/时钟/快捷键
└── style.css         基础样式 + 末尾「第二版通用部件」(只引用 `--ui-*` token)
```

外部依赖通过 CDN 引,**不打包**,**不本地化**:
- `xterm@5.3.0` + `xterm-addon-fit@0.8.0`:OAuth 登录 step 2 的内嵌 PTY 终端
- 字体取 `--ui-font-family` / `--ui-font-family-mono`(定义在 `ui-foundation.css`),不再单独引入 Google Fonts

后端 `services/orchestrator/main.py` 把 `apps/legacy-web/` 挂到 `/`:

```python
if WEBUI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEBUI_DIR), html=True), name="ui")
```

所以浏览器访问 `http://orchestrator:8000/` = 直接 fetch `index.html`,API 调用走 `/api/...`(由 FastAPI 路由优先匹配)。

---

## Module Organization

`app.js` 内部按"功能区"水平组织,每节用 `// ===== 节名 =====` 分隔。顺序固定:

```
// ============ API 调用与 DOM 工具 ============
const API = (path, opts) => fetch...
const $ / $$              // querySelector 简写

// ============ 全局 state ============
const state = { accounts, topics, tasks, runs, topicFilter, runsEventSource }

// ============ 路由 ============
const ROUTES = { accounts: renderAccounts, topics: renderTopics, ... }
function currentTab() / navigate()

// ============ Accounts(含 OAuth 登录两步流) ============
async function renderAccounts()
function openAccLoginModal() / showAccStep() / startAccLogin() / attachAccLoginTerminal()
                          / commitAccLogin() / endAccLogin()

// ============ Topics ============
async function renderTopics() / openTaskModal()

// ============ Tasks ============
async function renderTasks()

// ============ Runs(SSE 实时) ============
function renderRuns() / paintRuns() / openRunDetail()

// ============ Modal helpers ============
function openModal() / closeModal() + 全局点击委托

// ============ utils ============
function escapeHTML() / formatSize()

// ============ chrome(clock / shortcuts)============
function startClock() / bindShortcuts()

// ============ 启动 ============
navigate(); startClock(); bindShortcuts();
```

**何时新增节** vs **何时塞进现有节**:
- 新增一个 tab(`/api/<resource>` 的资源)→ 新建 `// ============ <Name> ============` 节,加 `render<Name>` 函数,注册到 `ROUTES`,在 `index.html` 加 `<template id="tpl-<name>">` 和 nav `<a>`
- 现有 tab 内增功能(新按钮、新弹窗动作)→ 塞进对应节,新函数放在该节末尾

**何时该把 app.js 拆成多文件**(当前完全不需要):
- 超过 ~1500 行 + 单 tab 节自身 >300 行 → 拆 `apps/legacy-web/app-<feature>.js`,在 `index.html` 顺序引入(原生 JS 没有模块系统时按依赖序排)
- 真要 ES Module → 改 `<script type="module">`,但要承担"CORS 必须走 http 不能 file://"的代价
- **不要为"工程美感"提前拆**

`style.css` 也按节组织,节标题为 `/* ===== <节名> ===== */`:reset → 模块栏(品牌与状态行) → main/view → buttons → tables → forms → status pills → modal → detail panel → batch scheduler → hintbar → scrollbar → responsive → 内嵌 OAuth 登录 → `[data-theme=light]` 补充规则 → Auth → Paste-helper → Auth 与粘贴助手的 `[data-theme=light]` 补充规则 → 物理特征、运行时段与工程页 → 末尾「第二版通用部件」。

`index.html` 内的 `<template>` 命名约定 `tpl-<tab>`,modal 命名 `<feature>-modal`(`#modal` 是通用详情弹窗、`#acc-modal` 是账号登录两步流弹窗、`#task-modal` 是创建任务弹窗)。

---

## Naming Conventions

- **文件名**:`index.html` / `app.js` / `style.css`,全部小写
- **JS 函数**:`camelCase`,如 `renderAccounts` / `openTaskModal` / `attachAccLoginTerminal`
- **JS 全局**:`state`(对象)、`API`、`ROUTES`(常量对象)、`$` / `$$`(DOM 简写)
- **JS 临时常量**:`UPPER_SNAKE`,如 `TAB_KEYS`
- **HTML id**:`kebab-case`,如 `#topic-filter` / `#acc-login-cancel` / `#runs-body`
- **HTML class**:语义优先 + kebab-case,如 `.view-head` / `.topic-card` / `.modal-card-md` / `.pill-running`
- **CSS variable**:原生 CSS 不再定义自己的变量,只引用 `ui-foundation.css` 中的第二版 token(取值规则见 [组件规范](component-guidelines.md) 的 Styling Patterns):
  - 颜色:`--ui-color-*`(表面 `surface / layout / fill-*`、文字 `text / text-2..4`、线 `line`、主色 `primary*`、状态 `success / warning / danger / info` 及其 `-bg / -text`、墨色 `ink*`)
  - 字号与字体:`--ui-font-size-*`、`--ui-font-family` / `--ui-font-family-mono`
  - 尺寸:`--ui-control-sm / md / lg`、`--ui-space-unit`
  - 圆角与阴影:`--ui-radius-btn / control / block / card`、`--ui-shadow-*`
- **状态徽章**:`.pill.pill-<status>`,status 取值 `queued | running | success | failed | timeout`,后端 `runs.status` 列直接拼进 class
- **template id**:`tpl-<tabname>`,如 `tpl-accounts` / `tpl-topics` / `tpl-tasks` / `tpl-runs`
- **modal id**:`<feature>-modal` 或通用 `#modal`
- **data 属性**:`data-tab` 标 tab 按钮、`data-del` 标删除按钮、`data-run` 标运行按钮、`data-detail` 标详情按钮、`data-close` 标"关闭哪个 modal" —— 全部用于事件委托

---

## Examples

- **新增一个 tab 的全套改动**:`renderTasks()` 的实现 + `ROUTES.tasks` 注册 + `<template id="tpl-tasks">` + `.tabs <a data-tab="tasks">`
- **典型列表渲染**:`paintRuns()` 展示了"`map(item => template-literal HTML).join('') || empty-state HTML`"的标准写法
- **modal 两步流**:`openAccLoginModal → startAccLogin → attachAccLoginTerminal → commitAccLogin → endAccLogin` 是"前端两步流 + 后端 session 容器"的完整范式
- **CSS 深浅切换**:原生 CSS 只引用 `--ui-*` token,浅色默认值在 `ui-foundation.css` 的 `:root`,深色在 `:root[data-ui-scheme=dark]`(只写与浅色不同的值);文档根 `data-ui-scheme` 由 `index.html` 首帧脚本写入,组件 CSS 无须为深色重写或加限定
