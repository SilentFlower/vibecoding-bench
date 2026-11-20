# 技术设计（父任务）

现状证据见 `research/frontend-architecture.md`（下文标「调研 §n」），参考形态见 `research/reference-and-design.md`。本文只定跨子任务的边界与约定，细节由各子任务的 `design.md` 展开。

## 1. 组件库分层

```
apps/legacy-web/ui-foundation.css   默认 token（浅色）+ 三档阅读尺寸，Vue 与独立 /runtime/ 文档共用
        ▲ 默认值一致性由单测保证
apps/web/src/theme/                 主题核心（纯函数）+ 浏览器运行时
        │ createTheme(seed) → { '--ui-*': value }
        │ applyTheme(el, vars) / loadTheme() / saveTheme()
        ▼
apps/web/src/components/ui/*        组件（原地演进，保留导入路径与公开 props）
        ▼
业务页面 / 原生任务页               只用组件与 var(--ui-*)，不写死颜色和圆角
```

- **唯一 token 命名空间 `--ui-*`**：沿用规范已有前缀（`ui-guidelines.md` 视觉 token 节），新 token 带分类前缀（`--ui-color-*`、`--ui-font-size-*`、`--ui-radius-*` 等，见子任务 1 design §2.1）。
  - 现有 4 套 token（调研 §1.3）分两步收敛：
    - 子任务 1 合并重复定义（`style.css` 重复的 `:root` 块、`approved-design.css:4` 的覆盖），删除只服务旧组件的 `--button-*`。
    - 页面仍在引用的 shadcn 变量、旧控件 token、阅读尺寸作为「旧层」冻结取值，由子任务 2、4、6 随页面迁移改用新 token，最终复核时删除。
  - 冻结而不是别名到新色板，是为了让未迁移页面继续与旧原型一致（§6、§7）；修订记录见子任务 1 design §1、§8。
- **默认值放在 `ui-foundation.css`**：它已被 `main.ts:2` 全局引入，并被独立文档以 `<link>` 引用（调研 §3.2）。用它承载默认 token，不用新增运行时桥接白名单。
- **主题核心是纯 TS 函数**：用 `node:test` 测试（仓库已有 `node --experimental-strip-types --test` 先例），并断言 `createTheme(默认)` 与 `ui-foundation.css` 的默认值逐项相等，避免两处漂移。
- **主题持久化**：
  - 存 `localStorage['flower2api.theme']` = 种子（含 `version`）。只存种子：派生是同步纯函数，加载时重算，避免算法升级后读到过期派生值。
  - `main.ts` 在 `createApp` 前同步读取，校验种子的类型、范围与格式后派生并写到 `document.documentElement`；无效就忽略，回退默认。
  - 应用在挂载前已就位，界面不会以默认主题闪一下。不改 `index.html`，因为 `system_release.py:101-103` 判断控制镜像要不要重建时不看它（调研 §7）。
- **局部主题**：`applyTheme(el, vars)` 写在任意容器上，供主题设置的预览画板使用，自定义属性只向下继承。
- **样式层叠**：新组件样式进 `@layer components`。现存未分层的业务 CSS 会压过它（调研 §1.2），所以子任务 1 必须同时删掉与组件冲突的全局覆盖（如 `style.css:534-570` 的 `[data-slot=button]`）。页面级旧规则随子任务 4、6 逐页删除。
- **颜色全部语义化**：阴影、描边、遮罩、滚动条也走 token，为子任务 7 的深色模式只换值。

## 2. 图标

沿用 SVG sprite（`components/ui/icon`，调研 §4.2），补齐设计稿新增的图标：palette、sun、moon、monitor、arrow-up-circle、history、undo、rotate、save、terminal、minus、fit、pause。
- Vue 与 legacy 两份 sprite 同步补齐，legacy 那份同时补上缺的 `i-server`。
- 仍直接用 `lucide-vue-next` 的 10 个文件，在迁移到对应页面时改用 sprite。

## 3. 原生页

- **任务与工程**：Vue 内嵌，同文档挂载，CSS 经 `runtimeModule.ts` 改写作用域（调研 §3.1–3.3），能继承根上的 `--ui-*` 变量。
  - 子任务 6 把 legacy CSS 的写死颜色改为 `var(--ui-*)`，并处理与 Vue 同名冲突的 `--border`、`--muted`。
  - `TasksWorkspace.vue:84` 固定 `data-theme='light'` 的约定，由子任务 7 改为跟随主题。
- **运行环境**：是 Vue 页面（`RuntimeEnvironments.vue`），只沿用原生类名，样式在 `src/native-environment.css`，不经过运行时桥接白名单。
- **独立 `/runtime/` 文档**：属于兼容入口，只读取 `ui-foundation.css` 的默认 token，不应用用户自定义主题。
- **终端**：xterm 配色写死在 `legacy-web/app.js:1591-1603`，浅色下仍保持深色终端（`style.css:1257-1273`），本次浅色阶段不动，由子任务 7 统一定终端配色。

## 4. 系统更新（子任务 3）

- **现状**：
  - 版本号已能打开原生 `<dialog>`，里面内嵌了 `SystemUpdates`（`Dashboard.vue:114,152-155`）。
  - 另有整页路由 `router.ts:49`，网关登记了 `/updates`。
- **改造方案**：
  - 重做为新组件弹窗。
  - `/updates` 路由保留，渲染控制台并自动打开弹窗，书签、网关路由和验证夹具都不受影响。
- **步骤记录**：
  - 在 `system_updater.py` 的 `_record` 落盘处，发现 `phase` 与上一条记录不同就追加 `{phase, at}`。
  - 放在这里，同时覆盖 `_phase` 路径和宿主直接写 `phase` 的恢复路径（`system_update_host.py:1103,1108`），也自然去掉了在途等待时每 0.5 秒重复写入的同名步骤。
  - 记录条数设上限；新字段加入 `_public_operation` 的键白名单（`:233-235`），并同步 `api.ts` 的 `SystemUpdateOperation` 类型。
- **前端步骤展示**：
  - 实际顺序是 draining → switching（越过取消边界）→ snapshotting → migrating → switching → verifying → committing → cleaning（`system_updater.py:405-444`）。
  - 前端按「是否含数据库迁移」生成规范步骤表；第一次 switching 视为「等待在途完成」结束，不单独成行。

## 5. 新路由

- `/theme`（子任务 5）：Vue `router.ts` 加路由；网关 `router.rs:145-161` 登记 SPA 页面，并补 `:4289-4315` 的路由测试（调研 §7）。

## 6. 验证策略与设计基准

- **新基准**：
  - 第二版设计稿成为新的唯一视觉基准，由子任务 1 从 `research/design-v2/` 复制到 `doc/design/console-v2/`（research 副本保留为调研快照）。
  - 登录页沿用第一版设计（父 PRD R7），子任务 2 把第一版设计稿复制到 `doc/design/console-v2/v1/`，只有其中 `#login` 画面作为基准。
  - 旧 `doc/design/flower2api-concept.html` 在全部页面迁移完成前保留，供尚未迁移页面的原型对比脚本使用，最终复核时删除。
- **比对方式**：
  - 13 个原型对比脚本做的是「原型与产品的计算样式逐项比对」（调研 §6.2）。新设计稿的 DOM 结构与产品不同，这种比法无法延续。
  - 已迁移页面改为三类验证：
    1. token 断言：关键元素的计算样式等于 token 取值。
    2. 1440 / 390 截图，供人工对照设计稿。
    3. 行为断言保持不变。
  - 原型对比脚本随所属页面的迁移改写或退役。
- **写死样式的行为脚本**：如 `verify_shared_pagination.py:14-43` 的 `#77648f`（调研 §6.3），随所属子任务改为读取 token 或更新期望；业务断言不放宽。
- **组件演示页**：`ui-preview.html` 不进生产构建（调研 §6.1），仍用 dev server 验证（`verify_ui_controls.py`）。

## 7. 发布与过渡态

- 每个子任务完成后可单独发版。
- 子任务 1 发版后，按钮、输入、弹窗等基础组件先换成新外观，页面布局在子任务 2、4、6 完成前仍是旧结构。这是预期的过渡态，不做功能开关。
- 回滚按子任务回退提交；回退子任务 1 时，依赖它的后续子任务一并回退。

## 8. 最终复核（子任务 1–7 完成后，父任务唯一的直接改动）

7 个子任务完成后盘点（2026-11-20）的现状：
- 颜色与圆角字面量已清零：十六进制和 rgba 只出现在 `ui-foundation.css` 的 token 定义和 `UiPreview.vue` 的演示种子里，`border-radius` 全部取 token。
- `!important` 从 136 处降到 23 处，余下的都是规范登记的例外。
- 下面几项仍是过渡期遗留，由本节收尾。本节不改变任何业务行为，浅色和深色外观只允许在 §8.3 登记的位置变化。

### 8.1 旧原型退役

- 删除 `doc/design/flower2api-concept.html`。`doc/design/font-licenses.txt` 是本地字体的许可说明，规范仍引用，保留。
- 退役 `deploy/flower2api/audit_full_design.py`。
  - 它对 5 个已迁移页面与旧原型比对，现在比对项 100% 不同（账号 53/53），只剩「无页面错误、无横向滚动」两条断言。
  - 这 5 个页面已由第二版脚本覆盖：`verify_account_page_design.py` / `verify_accounts_design.py`、`verify_proxy_design.py`、`verify_records_pages_design.py`、`verify_tokens_design.py`、`verify_nodes_settings_design.py`。
- `verify_design_parity.py` 只用旧原型读取账号编辑的分组标题和页签名。改为与当前一致的常量 `['基础配置', '用量与调度', '请求与模型', '上游 Session 池']`、`['概览', '配置', '调度', '环境与诊断']`。第二版设计稿只画出部分分组，不能当来源。其余断言不变。

### 8.2 旧层清零（规范「旧层（过渡期冻结）」约定父任务最终复核时按旧名删除）

- **`style.css`**：
  - 删除 shadcn 变量块（`--background`…`--ring`、`--radius`）与 `@theme inline` 中对应的 `--color-*`、`--radius-*`、`--text-xs/sm` 映射。
  - `--font-body` / `--font-mono` 删除。`@theme` 只保留 Tailwind 自身名字 `--font-sans`、`--font-mono`，改指 `--ui-font-family(-mono)`，让 Tailwind 预检的字体栈不回退到它的默认值。
  - 全局 `@apply border-border outline-ring/50` 改为直接写 `border-color: var(--ui-color-line)` 与 `outline-color: color-mix(in srgb, var(--ui-color-text) 50%, transparent)`，取值不变。
  - `body` 的字号同下。
- **阅读尺寸**：
  - 删除 `ui-foundation.css` 的旧层块（`--ui-font-small/body/card/heading/page`、`--ui-control-height/compact/space` 及两档媒体查询）。
  - 根字号保持 14/15/16px 三档不变（Tailwind 间距按 rem 计）：改为 `calc(14px + var(--ui-tier) * 1px)`。`--ui-tier` 的断点与旧块相同（1920 / 2560）。
  - 不接到 `--ui-font-size-*`：那组随主题种子的基础字号变化，接上去会让 rem 布局跟着用户字号缩放，改变现有行为。
  - `approved-design.css` 的 `html` 与 `style.css` 的 `body` 同样取这个值。
  - `.approved-run-dialog` 标题改为 `calc(var(--ui-font-size-heading) - 2px)`，移动端为 `--ui-font-size-card`，默认取值仍是 18/20/22 与 16/17/18。设计稿没有画运行详情弹窗，所以保持原值，不向通用弹窗标题（20px / 780）靠拢。
- **剩余工具类**：
  - `App.vue` 外层的 `bg-background` 直接删除：`body` 已取同色 `--ui-color-layout`，画面不变。
  - `NativeStageDetails.vue` 的 6 处 `text-muted-foreground` 改为 `request-records.css` 新增的 `.request-wire-note`（取 `--ui-color-text-3`）。证据区块里没有其它规则设置这几行的颜色，两者等价。
- **`@custom-variant dark`**：shadcn 遗留，删除 tabs 组件后已无 `dark:` 用法；深浅由 `data-ui-scheme` 决定，一并删除。
- **无引用组件**：删除 `components/ui/tabs`、`components/ui/separator`、`components/ui/label`（全仓无导入）。
- **静态防回归**：`theme.test.mjs` 新增断言，`apps/web/src` 与 `apps/legacy-web` 的样式、组件中不出现：
  - 旧层变量名；
  - shadcn 色名工具类（`bg-background`、`text-muted-foreground`、`border-border` 等）；
  - `lucide-vue-next` 导入。

### 8.3 图标与死代码

- **lucide 改用 sprite**：
  - `ProxyPicker.vue` 的 `Globe`、`ChevronDown`、`Check` 改从 `@/components/ui/icon` 导入（sprite 已有）。
  - `Proxies.vue` 检测中的 `LoaderCircle`（状态徽标与检测按钮两处）改为项目惯例 `RefreshCw` 加旋转（`fui-spinning`，减少动态效果时停止）。
  - 登记的浅色可见变化：上面这两处检测中图标的字形；`ProxyPicker` 的地球、下拉箭头、对勾换成 sprite 字形（描边 2 → 1.8）。后者是改用 sprite 的必然结果，规划时漏登记，实施中补登记。
  - 移除 `lucide-vue-next` 依赖（`npm uninstall`，同步 `package-lock.json`）。`components.json` 是 shadcn CLI 配置，不参与构建，不改。
- **死类**：
  - 逐个复核扫描出的约 50 个疑似未引用类选择器，确认是死类再删除。确认标准：全仓 JS / Vue / HTML 中既无字面量，也无模板拼接前缀。
  - 已知的误报不删：Vue 过渡类 `fui-toast-enter-*`、xterm 生成的 `xterm-viewport`、`pill-${状态}` 拼接、`request-header-${kind}` 拼接、`env-${tone}` 生成的 `env-warning`。
  - 实际删除的死类：
    - `projects-*` 共 14 个，是旧工程页遗留；
    - `env-toolbar`、`env-metric`、`env-operation-summary`、`warmup-quota-panel`、`choice-compact`、`fui-popover`。
  - 分组选择器只摘掉死项，`:is()` 列表里只删其中的死类。改前改后按「@media 上下文、选择器、声明」结构比对，结果恰好等于去掉死选择器。
  - `verify_pi_projects_browser.py`（需要真实 Chrome 和独立工程栈，不在本地回归内）查询的 `.projects-settings > details` 在现有页面里本来就不存在，属于既有问题，不在本次范围。
  - 改动的原生 CSS 同步 `index.html` 的 `?v=`。
- **验证脚本废键**：20 个脚本的初始化脚本写入应用早已不读的 `vibebench-theme`。
  - 1 个随 `audit_full_design.py` 一起退役。
  - `verify_workspace_experience.py` 保留：它有意模拟存有旧偏好的升级用户，验证旧键不生效。
  - `verify_management_ui.py` 用该值给截图命名（浅色 / 深色），改为 `new_context(color_scheme=theme)` 实现原意。
  - 其余 17 个直接删除这行（Playwright 默认浅色，删除后行为不变）。

### 8.4 规范与基准

- `ui-guidelines.md`：
  - 设计基准改为单一第二版（删除「过渡期两套并存」与「未迁移页面以 flower2api-concept 为准」）。
  - 「旧层（过渡期冻结）」改为「旧层已删除」的合同，并写明 §8.2 的静态断言。
  - 根字号合同改写为 `--ui-tier` 三档。
  - 删除失效的 `--ui-font`、`--body-font` 表述。
  - 新增「第二版设计决定」一节列出 6 条：白色侧栏、紫色填充主按钮、卡片去边框改阴影、页头去分组名、更紧凑的字号与控件高、系统更新改弹窗。
  - Tests Required 中去掉 `audit_full_design.py`。
- 原生组件规范、legacy-web 其余规范：复核过渡期表述，有失效内容同步改掉。

### 8.5 复核证据

- **全量 UI 回归**：
  - 深色任务统一回归的 65 个脚本（主集合 39 + 集合外 26），减去退役的 `audit_full_design`，加上未纳入统一回归的 5 个第二版设计脚本（`verify_account_page_design`、`verify_nodes_settings_design`、`verify_records_pages_design`、`verify_ui_kit`、`verify_ui_shell`），共 69 个。
  - 期望只剩 3 个基线已登记的失败，原因不变。
  - 需要真实 Chrome 配置或独立管理栈的 `*_browser` 等脚本不属于本地 UI 回归，不纳入。
- **浅色、深色改前改后逐像素比对**（Vue 主要页面与原生 36 个状态）：差异只允许出现在 §8.3 登记的图标处。
- **计算样式探针**（`probe_styles.py`）：浅色、深色各取 1440 / 1920 / 2560，采样根字号、body 字号 / 字体 / 颜色 / 背景、默认描边与轮廓色，以及 code / kbd / pre / `.font-mono` 字体栈，改前改后逐项一致。
- **截图矩阵**：第二版设计稿浅色 / 深色与产品浅色 / 深色并排，覆盖 1440 和 390、全部画面，生成对照页（证据目录 `.deploy/console-ui-revamp/final-review/`，不入库）。
- 父 PRD 9 条验收逐条对应证据后勾选；发现不一致按 Check-All 处置，不放宽。
