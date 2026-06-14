# Directory Structure

> 本项目前端代码的组织方式。

---

## Overview

前端是**纯静态资源 + 原生 JavaScript**,**零构建** —— 没有 npm、没有 webpack/vite、没有 framework、没有 TypeScript、没有 bundler。三个文件直接由 FastAPI 的 `StaticFiles` 在 `/` 下挂出。

**核心理念**:WebUI 只服务 P1 内部使用,加载几十个题目卡片 + 一个 SSE 长连。为这点交互引 React 工具链反而拖慢迭代。**只要三个文件够用,就保持三个文件**。

---

## Directory Layout

```
webui/
├── index.html        所有视图模板 + 三个 modal + 外部依赖(xterm.js / Google Fonts CDN)
├── app.js            路由 + state + 4 个 render* + login 两步流 + 主题/时钟/快捷键
└── style.css         终端实验室皮肤(暗色主) + [data-theme=light] override
```

外部依赖通过 CDN 引,**不打包**,**不本地化**:
- `xterm@5.3.0` + `xterm-addon-fit@0.8.0`:OAuth 登录 step 2 的内嵌 PTY 终端
- Google Fonts:`JetBrains Mono`(等宽主)+ `Fraunces`(展示)

后端 `orchestrator/main.py` 把 `webui/` 挂到 `/`:

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

// ============ chrome(theme / clock / shortcuts)============
function setupTheme() / startClock() / bindShortcuts()

// ============ 启动 ============
navigate(); setupTheme(); startClock(); bindShortcuts();
```

**何时新增节** vs **何时塞进现有节**:
- 新增一个 tab(`/api/<resource>` 的资源)→ 新建 `// ============ <Name> ============` 节,加 `render<Name>` 函数,注册到 `ROUTES`,在 `index.html` 加 `<template id="tpl-<name>">` 和 nav `<a>`
- 现有 tab 内增功能(新按钮、新弹窗动作)→ 塞进对应节,新函数放在该节末尾

**何时该把 app.js 拆成多文件**(当前完全不需要):
- 超过 ~1500 行 + 单 tab 节自身 >300 行 → 拆 `webui/app-<feature>.js`,在 `index.html` 顺序引入(原生 JS 没有模块系统时按依赖序排)
- 真要 ES Module → 改 `<script type="module">`,但要承担"CORS 必须走 http 不能 file://"的代价
- **不要为"工程美感"提前拆**

`style.css` 也按节组织,顺序见文件顶部注释:reset → scanline → topbar → main/view → buttons → tables → forms → topic cards → pills → modal → detail panel → hintbar → scrollbar → responsive → 内嵌 OAuth 登录 → theme toggle → `[data-theme=light]` override 区。

`index.html` 内的 `<template>` 命名约定 `tpl-<tab>`,modal 命名 `<feature>-modal`(`#modal` 是通用详情弹窗、`#acc-modal` 是账号登录两步流弹窗、`#task-modal` 是创建任务弹窗)。

---

## Naming Conventions

- **文件名**:`index.html` / `app.js` / `style.css`,全部小写
- **JS 函数**:`camelCase`,如 `renderAccounts` / `openTaskModal` / `attachAccLoginTerminal`
- **JS 全局**:`state`(对象)、`API`、`ROUTES`(常量对象)、`$` / `$$`(DOM 简写)
- **JS 临时常量**:`UPPER_SNAKE`,如 `TAB_KEYS`
- **HTML id**:`kebab-case`,如 `#topic-filter` / `#acc-login-cancel` / `#runs-body`
- **HTML class**:语义优先 + kebab-case,如 `.view-head` / `.topic-card` / `.modal-card-md` / `.pill-running`
- **CSS variable**:`--<purpose>` 全部小写 + 短横线,主题相关变量分组:
  - 表面:`--bg / --bg-soft / --surface / --surface-2 / --surface-3`
  - 边框:`--border / --border-bright / --border-amber`
  - 文本:`--text / --text-dim / --text-faint / --text-muted`
  - 强调色:`--amber / --amber-soft / --amber-deep / --amber-glow`
  - 状态:`--running / --success / --failed / --timeout / --queued`(各自带 `*-glow` 变体)
  - 字体:`--mono / --display`
- **状态徽章**:`.pill.pill-<status>`,status 取值 `queued | running | success | failed | timeout`,后端 `runs.status` 列直接拼进 class
- **template id**:`tpl-<tabname>`,如 `tpl-accounts` / `tpl-topics` / `tpl-tasks` / `tpl-runs`
- **modal id**:`<feature>-modal` 或通用 `#modal`
- **data 属性**:`data-tab` 标 tab 按钮、`data-del` 标删除按钮、`data-run` 标运行按钮、`data-detail` 标详情按钮、`data-close` 标"关闭哪个 modal" —— 全部用于事件委托

---

## Examples

- **新增一个 tab 的全套改动**:`renderTasks()` 的实现 + `ROUTES.tasks` 注册 + `<template id="tpl-tasks">` + `.tabs <a data-tab="tasks">`
- **典型列表渲染**:`paintRuns()` 展示了"`map(item => template-literal HTML).join('') || empty-state HTML`"的标准写法
- **modal 两步流**:`openAccLoginModal → startAccLogin → attachAccLoginTerminal → commitAccLogin → endAccLogin` 是"前端两步流 + 后端 session 容器"的完整范式
- **CSS 主题切换**:`:root { ... }` 暗色为默认,`[data-theme="light"] { --bg: ...; ... }` 在 line 942+ 仅覆写颜色变量,组件 CSS 全部走 `var(--xxx)`,无须为浅色重写组件
