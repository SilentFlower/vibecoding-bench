# 原生页视觉对齐

## Goal

让「任务与工程」和「运行环境」两页改用第二版 token 与组件样式，外观与其余页面一致，并跟随用户在当前浏览器保存的主题；业务行为不变。对应父任务 `../11-19-console-ui-revamp/prd.md` 的 R8，画面见设计稿 `doc/design/console-v2/mock.html` 的 `#tasks` 与 `#environments`。按用户决定一次交付，不再拆子任务。

## Background

### 加载方式

- **任务与工程**（`/tasks`）：
  - `apps/legacy-web` 原生模块，由 `TasksWorkspace.vue` 在 Vue 文档内挂载。
  - 8 份 CSS 构建时加 `.task-runtime` 作用域打包（`runtimeModule.ts:9`），能继承根上的 `--ui-*`。
  - 宿主固定 `data-theme=light`（`TasksWorkspace.vue:84`），由子任务 7 改为跟随主题。
  - 代理切换（`runtime/TaskProxyDialog.vue`）、运行详情（`runtime/RunDetails.vue`）、抓包（`CaptureWorkspace.vue` + `capture-workspace.css`）、分页、代理气泡已是 Vue 组件，经 Teleport 挂进原生宿主。
  - 前两个组件的 `<style>` 里共有 137 处写死颜色、17 处圆角字面量。
- **运行环境**（`/environments`）：
  - 纯 Vue 页 `RuntimeEnvironments.vue`，沿用原生类名，样式只来自 `src/native-environment.css`。环境管理弹窗的分区组件 `EnvironmentResources`、`EnvironmentKernel`、`RunWindowForm` 也用这份样式。
  - 同一组件也作为任务账号的「环境详情」弹窗，被 `TasksWorkspace.vue:21` 复用。
- **独立 `/runtime/` 兼容入口**：仍受支持（`ui-guidelines.md:477`），没有重定向。
  - 用 `<link>` 加载同一组 legacy CSS 和 `ui-foundation.css`，**读不到 Vue 的组件库样式（`kit.css`）和用户主题**。
  - 静态文件受运行时桥接精确白名单约束：`runtime_bridge.rs:426-450`，测试在 `:1139`、`:1187`。

### 样式现状

| 文件 | 行 | 颜色字面量 | 圆角字面量 | `!important` |
| --- | ---: | ---: | ---: | ---: |
| style.css | 1748 | 116 | 0 | 9 |
| environments.css | 250 | 27 | 14 | 18 |
| console.css | 148 | 132 | 33 | 4 |
| approved-design.css | 282 | 311 | 60 | 29 |
| work-design.css | 958 | 489 | 82 | 6 |
| environment-design.css | 276 | 124 | 28 | 10 |
| capture-workspace.css | 45 | 43 | 4 | 0 |
| native-environment.css（Vue） | 305 | 173 | 40 | 11 |

- **主题不起作用**：旧文件引用的 `--ui-*` 几乎全是旧层字号，所以主题运行时对两页的颜色和圆角完全不起作用。
- **旧变量**：46 个旧变量名分散在 9 处定义块。
  - 其中 `--border`、`--muted` 与 Vue 的 shadcn 变量同名但语义不同，内嵌的 Vue 组件会继承旧值。
  - `legacy-web/component-guidelines.md:162` 说两者「不冲突」，这与实际不符。
- **疑似无效规则约 400 条**：
  - `style.css` 的暗色终端底稿、topbar、hintbar、扫描线、`projects-*`；
  - `console.css`、`approved-design.css`、`work-design.css` 中的大段规则。
  - `environments.css` 与 `environment-design.css` 只服务独立入口的环境页签：Vue 内这个页签跳转到 `/environments`。`environment-design.css` 由 `extract_environment_styles.py` 从旧原型生成。
- **终端**：xterm 配色写死在 `app.js:1597-1603`，终端容器底色有 4 种互不一致的写法（`style.css:1257-1273`，`work-design.css:64,488,749`）。

### 设计稿与现状

- **设计稿范围**：只有 1440 桌面图。
  - `#tasks` 只画了「任务账号」页签；
  - `#environments` 只画了卡片列表；
  - 两页都没有 390 稿，也没有任务页深层弹窗。
  - 可参照的通用规格：弹窗看 `#account-edit`，移动规则看 `#mobile`。
- **任务与工程，设计稿与现状的差异**：
  - 页头：现状有分组名「工作区」（`index.html:29`），设计稿没有。
  - 页签：设计稿是带图标、按内容排列的分段托盘，「任务账号」带计数。现状是拉满一行的描边托盘，「题库」和「普通任务」共用一个图标。
  - 区块头：设计稿是一行，标题与说明在左，搜索（300px）和主按钮在右。现状把搜索另起一行。
  - 任务账号卡：
    - 设计稿是实体卡、带圆点的状态标签、节点浅灰块，网关区里有提示条。
    - 现状（`app.js:693-703`）是描边卡，网关状态是无语义色的 `<p role=status>`。
    - 设计稿卡片底部没有操作栏，产品有 7 个按钮。
- **运行环境，设计稿与现状的差异**：
  - 设计稿是实体卡，三组件状态是托盘分段，预热块按**预热状态**着色。
  - 现状是描边卡、分隔线条，预热块按**环境状态** `tone(row)` 着色，所以会出现环境就绪但「准备状态待核对」也显示成绿色。
  - 现状的结果计数单独占一行。1440 下已是两列。
- **产品有而设计稿没画的**（功能保留，只统一外观）：
  - 任务页：养号条件按钮、登录草稿区、创建 / 关联网关账号、凭据交接对账，以及其余五个页签。
  - 环境页：AGY 文案、CPU 读取中 / 失败、「显示全部环境」、环境管理侧抽屉的五个分区。
- **设计稿有而产品没有数据的**（不新增）：卡片状态「运行中 / 空闲」、网关「最近同步 3 分钟前」。

### 验证现状

- **对旧原型 `flower2api-concept.html` 断言零差异**（新视觉下必然失败）：
  - `verify_task_account_config.py:88-110,169`
  - `verify_task_feedback_styles.py:13-25`
  - `audit_token_task_design.py:25-47`
  - `verify_dialog_typography.py:20-27`
- **只采样旧原型、不断言**：`audit_full_design.py`、`audit_environment_proxy_design.py:15`（后者注释写明环境用例「留到原生页迁移」）。
- **子任务 4 移交的 4 个已登记失败**（`11-19-console-ui-pages` 进度备注）：
  - `verify_task_login_design` L32：ProxyPicker 弹层挡住名称输入。
  - `verify_native_environment_edges` L39：标题含平台徽标，期望值已过时。
  - `verify_native_lifecycle` L14：URL 多了 `&account=1`，且 `#theme-toggle` 已删除。
  - `verify_frontend_navigation` L105-108：`#theme-toggle` 已删除。

## Requirements

- **R1 运行环境页**：
  - 筛选改为带计数的分段控件，与结果计数、搜索（280px）放在同一工具栏。
  - 卡片改实体卡：平台图标块、标题带平台徽标、副标题带节点、带圆点的状态徽标。
  - 三组件状态改托盘分段，未运行的组件置灰。
  - 资源四格、版本行、CRIU / 内容采集、运行时段行按设计稿排版；底部四等分操作栏，第一项用主色。
  - 预热块按预热状态着色：就绪绿、失败琥珀、其余灰。
  - 1440 两列。
  - 环境管理侧抽屉（宽 940）及其分区组件统一外观。
- **R2 任务与工程页面骨架**：
  - 页头去分组名，外观与 `PageHeader` 一致。
  - 六个页签改为带图标的分段托盘。图标依次为 users / box / zap / todo / activity / list；「任务账号」页签显示账号数。
  - 各页签区块头一行化：标题与说明在左，搜索与主按钮在右。
- **R3 任务账号卡片**：
  - 卡片外壳、头部、状态徽标、节点块、键值行、链接与其余实体卡一致。
  - 网关状态改为语义提示条：凭据异常为红色并显示原因，同区保留「重新授权并同步 / 解绑」；手动更新额度为蓝色；其余为中性提示。原有按钮与「凭据交接对账」保留。
  - 底部 7 个按钮保留，改为等分操作栏（放不下时换行），「删除」用危险色。
- **R4 其余页签、原生控件与深层弹窗**：
  - 工程、养号、普通任务、运行记录、题库五个页签的卡片、表格、徽标、空态统一外观，结构不变。
  - 原生按钮、输入、选择、数字输入、时间选择、搜索、复选与组件库同名部件外观一致。
  - 原生弹窗共 19 个容器（`index.html`），按通用弹窗规格统一，宽度不变：任务账号配置、运行配置、通用详情（账号详情 / 额度）、关联网关账号、抓包、新建抓包、内容采集、CPU、运行时段、养号额度、题目编辑、添加任务账号（含授权登录）、新建任务、批量新建、续聊、交付、工程研究，以及仅独立入口使用的登录和环境工作区。
  - Vue 弹窗（运行详情、代理切换、抓包工作区）同样只取 token。
  - 保持原生渲染与事件清理方式。
- **R5 旧样式清理与主题跟随**：
  - legacy CSS、`native-environment.css` 和上述 Vue 组件样式不再写死颜色与圆角，只取 `--ui-*`，主题对两页生效。
  - 删除旧变量定义块（同时消除 `--border`、`--muted` 冲突）和无效、被替代的规则。
  - 终端容器统一取墨色 token。
  - 文件增删时同步运行时桥接白名单、测试、`runtimeModule.ts` 和静态版本参数。
- **R6 独立 `/runtime/` 入口**：继续可用，外观随共享样式变为第二版默认主题。其环境页签的两份专用样式只做 token 化与清理，不按新稿重排。
- **R7 验证与规范**：
  - 新增两页设计稿比对与主题跟随验证；把对旧原型断言的脚本迁到新基准；修好移交的 4 个失败脚本。
  - 静态样式规则覆盖本页文件；更新原生组件规范与 `ui-guidelines.md`。

## Acceptance Criteria

- [ ] 两页 1440×900 与设计稿逐项比对无差异（白名单逐条注明原因）。390×844 单列、无横向溢出。深层弹窗 1440 / 390 截图外观统一（R1–R4）。
- [ ] 在主题设置保存非默认主题后，两页及深层弹窗的主色、圆角、字号随之变化；独立 `/runtime/` 显示默认主题（R5、R6）。
- [ ] 静态规则校验 legacy CSS、`native-environment.css` 与本页 Vue 组件：除 token 定义外没有颜色字面量，圆角只取 token；旧变量定义块清零（R5）。
- [ ] 原生页既有行为验证全部通过，移交的 4 个失败修好。回归集合与基线相比没有新增失败。真实桥接路径可加载全部原生资源，独立入口可用（R4–R7）。
- [ ] 原生组件规范与 `ui-guidelines.md` 已同步（R7）。

## Dependencies

依赖子任务 1（token 与主题运行时）、子任务 2（实体卡、提示条、分段等组件）。与子任务 5 无依赖。

## Out of Scope

- 原生页功能变化。设计稿里产品没有数据的「运行中 / 空闲」状态和「最近同步」不新增，弹窗宽度与交互不变。
- xterm 配色、`data-theme` 跟随与深色模式（子任务 7）。
- 独立入口环境页签按新稿重排；把原生模块改写为 Vue。
