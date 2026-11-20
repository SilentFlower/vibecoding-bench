# 技术设计 — 控制台深色模式

## 1. 范围与边界

- **做**：主题模式（跟随系统 / 浅色 / 深色）、深色默认色板与派生规则、首帧防闪烁、系统切换实时跟随、侧栏快捷切换、主题设置页模式选项、全部 Vue 页与原生页（含独立 `/runtime/` 文档）、弹窗、气泡、终端、图表的深色适配，深色设计基准与验证。
- **不做**：高对比度主题；组件级 token 编辑；新增业务行为或 API。
- **已定决定**（用户确认）：
  - 深色色板为「夜幕紫灰」，草稿 `research/design-dark/` 即视觉基准；
  - 没有保存值时默认跟随系统；
  - 独立 `/runtime/` 文档跟随所选模式，仍只用默认配色、不应用自定义种子。
- **随设计稿与参考项目确定的交互**：
  - 侧栏按钮按当前实际深浅切到另一种，并保存为明确的浅色 / 深色；要回到跟随系统，在主题设置页选择。依据：第二版稿侧栏只有一个「切换深色模式」图标；参考项目同此语义。
  - 主题设置页的模式属于草稿：画板预览，保存并应用后生效，计入待应用数。依据：第二版稿把模式分段放在草稿编辑面板里；参考项目同此语义。

## 2. 深色基准

- 把 `research/design-dark/` 的 `mock.html`、`mock.css`、`palette.js` 同步到 `doc/design/console-v2/`；`icons.js` 未改动，不同步。字体路径改回 `../../../apps/web/...`。
- `derive.ts` 只留在任务 research 作推导记录。产品侧以 `createTheme(seed, 'dark')` 为准，单测断言它对六个预设与四个功能色的输出等于 `palette.js`，保证产品与确认稿同源。
- 打开方式：`mock.html?mode=dark#<画面>`。新增两个画面：`#terminal`（任务账号授权弹窗里的登录终端）与 `#palette`（色板）。不带参数仍是第二版浅色，现有脚本不受影响。

## 3. 主题运行时（`apps/web/src/theme/`）

### 3.1 模式与深浅

- 新类型：`ThemeMode = 'system' | 'light' | 'dark'`，`ThemeScheme = 'light' | 'dark'`。
- 存储：模式单独存在 `localStorage['flower2api.theme-mode']`，与种子 `flower2api.theme` 分开。
  - 原因：种子保持 `version: 1`，不用迁移；种子损坏不影响模式；独立文档只需读模式。
  - 缺失、非法或读取抛错一律按 `system` 处理。保存 `system` 时删除该键，与「默认主题不写存储」一致。
- `resolveScheme(mode, prefersDark)`：`system` 取系统偏好，其余取模式本身。
- 文档根标记 `data-ui-scheme="light|dark"`。`ui-foundation.css` 中 `:root[data-ui-scheme=dark]` 放深色默认值，并设 `color-scheme: dark`，让原生控件、滚动条、日期面板一起变深；浅色根设 `color-scheme: light`。

### 3.2 派生：`createTheme(seed, scheme = 'light')`

- **浅色**：输出与现在逐值一致。新增三类常量 token：
  - `--ui-color-knob`：开关滑块。深色下滑块不能用卡片底。
  - `--ui-color-term-fg/-dim/-cursor/-red/-green/-yellow/-blue/-magenta/-cyan`：终端配色，两种模式相同；终端底色取各自模式的 `ink`。
  - 新增值同时写进 `ui-foundation.css` 浅色块，双向一致测试照旧。
- **深色中性色**（`NEUTRALS_DARK`，手调常量，取自确认稿）：

  | token | 值 | token | 值 |
  | --- | --- | --- | --- |
  | layout | `#0f1018` | text | `#eceef6` |
  | surface | `#171824` | text-2 | `#c5c8d6` |
  | fill / fill-hover | `rgba(160, 162, 220, .085 / .13)` | text-3 | `#9a9eb2` |
  | fill-muted / fill-subtle | `#1f2130` / `#1c1d2b` | text-4 | `#6d7188` |
  | fill-strong / fill-active | `#3a3c52` / `#252738` | table-head / stripe / hover | `#20222f` / `#1a1b28` / `#232537` |
  | track / line | `#292b3c` / `#272938` | neutral-text / bg | `#b4b8c8` / `#252736` |
  | mask | `rgba(3, 4, 10, .62)` | cc-text / bg | `#eaa985` / `#2f231f` |
  | scrollbar | `#4a4d63` | agy-text / bg | `#9db6f5` / `#1e2541` |
  | ink | `#0a0b12`（比卡片更深，终端与标志块仍可区分） | feedback-surface / text | `#272a3c` / `#f3f4fa` |
  | knob | `#eceef6` | brand、on-ink、ink-text、ink-muted、term-* | 同浅色 |

- **深色主色组**（六个预设与自定义主色同一规则，与 `derive.ts` 相同）：
  1. 实色提亮到对 `surface` 对比度 ≥ 3.2（非文字对比度 3:1 留余量）。
  2. 按钮文字先取白色；白字不到 4.5 时改用 `#0f1527`，深色字仍不到 4.5 就继续提亮实色，直到深色字达标。
  3. `hover` = 实色明度 +0.05；`container` = 实色以 20% 混入 `surface`；`text` = 实色明度 +0.1 后提亮到对 `container` 与 `surface` 都 ≥ 5.5；`ring` = 实色 35% 透明度。
  - 例：花瓣紫种子 `#6c54b4` 派生出实色 `#725abb`、白字；玫瑰红派生出 `#dd5181`、深色字；石墨派生出 `#626a7c`、白字。
- **深色功能色组**：实色同上提亮到 ≥ 3.2；`bg` = 实色以 14% 混入 `surface`；`text` = 明度 +0.06 后提亮到对 `bg` 与 `surface` 都 ≥ 5.5。
- **柔光材质**：深色下同样把底色组向主色偏移 4%。
- **深色阴影**：底色取纯黑，透明度加深；`pop`、`modal`、`artboard` 另加一圈 `rgba(255, 255, 255, .07)` 细描边，`side`、`bar` 改为 1px 极淡亮线。阴影强度种子照旧按倍数缩放透明度。
- 颜色函数新增 `lightenUntil`（`darkenUntil` 的对称版本，循环有界）。纯黑等极暗颜色每步 +0.02 的明度会被 8 位舍入吞掉、原地不动，此时累加增量直到颜色变化；正常颜色每步都会变化，结果与确认稿 `palette.js` 逐值一致（改为整体累计增量会让 6 个确认取值偏差，故不用）。

### 3.3 首帧与跟随

- `apps/web/index.html` 与 `apps/legacy-web/index.html` 的 `<head>` 各有一段同步内联脚本：读模式键，结合 `matchMedia('(prefers-color-scheme: dark)')` 写 `data-ui-scheme`。
  - 样式表本来就阻塞渲染，首帧即为正确的深浅。
  - 读取失败时按系统偏好处理。
  - 键名与 `THEME_MODE_STORAGE_KEY` 一致，由单测校验。
  - 网关未设置 CSP，`legacy-web/index.html` 已有内联脚本先例。
- `initTheme()`：
  1. 解析模式与深浅，写 `data-ui-scheme`；有保存的种子时写入 `createTheme(seed, scheme)`。没有保存种子时不写内联变量，由 `ui-foundation.css` 按深浅给出默认值。
  2. 订阅系统偏好变化：模式为 `system` 时重新解析并整组重写，`createTheme` 输出键集合固定，不会残留旧值。
  3. 没有保存种子、但文档根已有内联变量（本次会话在主题设置页保存过默认主题）时同样整组重写为 `createTheme(默认, scheme)`，否则会残留另一种深浅的值。
  4. 嵌在主题画板 iframe 内（`window.parent !== window`）时不订阅系统偏好：深浅与变量由父页面按草稿写入，自行跟随会在系统切换时用已保存值覆盖草稿预览。
- 运行时导出 `setThemeMode(mode)`（保存并应用）、`applyThemeMode(mode)`（只应用，供主题设置页在两份存储都写成功后统一应用）、`currentThemeMode()`、`currentScheme()`、`onThemeModeChange(listener)`。
- 组合式 `useThemeMode()`（`composables/`）：模块级响应式 `mode` 与 `scheme`。`mode` 由 `onThemeModeChange` 更新；`scheme` 以文档根 `data-ui-scheme` 为准（MutationObserver），主题画板由父页面直接改写 iframe 根时，画板里侧栏的切换图标也随之变化。`setMode(mode)` 保存并重新应用；保存失败时提示，界面仍按本次选择显示。侧栏与主题设置页共用。

## 4. 交互

### 4.1 侧栏快捷切换

- 桌面侧栏与移动端抽屉的 `.sidebar-tools` 首位加 `button.sidebar-theme-toggle`：
  - 浅色显示 `Moon`，名称与提示为「切换到深色」；深色显示 `Sun`，为「切换到浅色」；
  - 点击调用 `setMode(scheme === 'dark' ? 'light' : 'dark')`。
- 顺序同设计稿：主题切换、折叠、退出。侧栏折叠后，工具区纵向排列的现有规则自然包含它。
- 类名与无障碍名称写入外壳类名契约。
- 三个工具按钮时「本地管理控制台」宽 80.5px、可用 80px（设计稿同尺寸，文字溢出半像素不可见），产品带省略号保护会被截断：`.sidebar-identity` 右外边距 -1px 伸进间距，工具按钮位置不变；更窄断点仍按省略号截断。

### 4.2 主题设置页

- 编辑面板「全局」顶部加「主题模式」`Segmented.theme-mode`：跟随系统（`Monitor`）、浅色（`Sun`）、深色（`Moon`）。reka 的选项本身渲染 `value` 属性，脚本用 `.theme-mode [role=radio][value=<值>]` 定位，不为此扩展共享组件。模式与已保存不同时带「已修改」与单项恢复。
- 草稿：
  - `draftMode` 与种子草稿并列。待应用数 = 种子差异字段数 + 模式是否不同。
  - 「恢复默认」把模式恢复为 `system`；「撤销草稿」回到已保存的模式；离开保护同样计入模式。
  - 保存时先写种子再写模式，两者都成功才 `applyThemeMode(draftMode)` 并提示已应用；任一失败则提示失败、控制台不变，模式写入失败时把已写入的种子恢复为原值。
  - 预设色块在深色下取派生后的主色（同设计稿深色 `#theme`；石墨种子 `#3d4352` 在深色卡片上几乎不可见），浅色仍取种子色，浅色像素不变。
- 画板：`ThemePreview` 新增 `scheme` 属性（由 `draftMode` 与系统偏好解析），注入时写 `data-ui-scheme`，并写 `createTheme(draft, scheme)`。草稿为跟随系统时，画板随系统切换。
- 页面在主题设置页时用侧栏切换：已保存的模式更新。草稿模式原本与已保存一致时同步跟随，原本不同则保留为待应用修改。
- 组件演示页 `UiPreview.vue` 的局部主题示例按当前深浅派生。

## 5. 样式层收尾

- **`apps/web/src/style.css` 旧层**：
  - 仍有引用的 shadcn 变量改为引用浅色下最接近的 `--ui-*`：
    - `--background` → `layout`，`--foreground` → `text`；
    - `--card`、`--popover` → `surface`；
    - `--primary` → `text`，`--primary-foreground` → `surface`；
    - `--secondary`、`--accent` → `fill-muted`，`--muted` → `fill-subtle`，`--muted-foreground` → `text-3`；
    - `--border`、`--input` → `line`，`--ring` → `text`，`--destructive` → `danger`。
  - 无引用的 `--sidebar-*`、`--chart-*` 连同 `@theme inline` 中的对应行删除。
  - 无引用的旧控件 token（`--ui-surface/--ui-field-surface/--ui-text/--ui-muted/--ui-border/--ui-border-hover/--ui-accent/--ui-focus/--ui-focus-shadow/--ui-selected/--ui-danger/--ui-font`）删除。
  - `.approved-run-dialog` 的写死颜色与圆角改取 token（`18px` → `radius-card`、关闭按钮 `7px` → `radius-btn` 6px）；无引用的 `.resource-grid` 规则删除；滚动条 thumb 圆角 `3px` → `999px`（6px 宽，像素不变），满足圆角静态规则。
- `apps/web/src/approved-design.css` 的 `html{color}` 改取 `--ui-color-text`。
- 上述两个文件加入 `theme.test.mjs` 的「不写死颜色」清单，全仓颜色字面量只剩 token 定义处。
- **开关滑块**：`kit.css` 的 `.fui-switch-thumb` 改取 `--ui-color-knob`；原生 CSS 如有同类滑块同步修改。
- **墨底区块文字**：`work-design.css:43,44,229,283,315,463` 与 `RunDetails.vue:134` 的 `--ui-color-text-4` 改为 `--ui-color-ink-text`。text-4 在深色下变暗，对深色墨底只有约 4.1（实测 4.08，低于 4.5）；ink-text 两种模式不变。这些区块里取 `text-*` 的子元素（如标题栏、元信息）一并改为 `ink-text` / `on-ink`。
- **浅色下的有意变化**（登记在验证里，其余浅色画面像素不变）：
  - 终端与代码块文字 `#97a0b2` → `#a7abc3`；
  - xterm 配色换成新终端色；
  - 请求诊断原生阶段的说明文字 `#848894` → text-3 `#5f6878`（原值对白底只有 3.6，未达 AA）；
  - 默认描边 `#e9e8ed` → `#e6e8f0`；
  - 运行详情弹窗的写死颜色改取 token 后的细微差异；
  - 旧层 `--background` `#f6f7fb` → layout `#f5f6fa`、`--foreground` / `--primary` `#0e1726` → text `#0f1527`（弹窗遮罩下的页面底与继承文字色，通道差 ≤ 1）；
  - 侧栏底部新增的主题切换按钮（全部 1440 页面左下 146 像素，弹窗遮罩下同一处）与主题设置页新增的「主题模式」分组。

## 6. 原生页与独立入口

- 删除 `TasksWorkspace.vue:84` 的 `host.dataset.theme='light'`，以及 `legacy-web/index.html` 写死的 `dataset.theme`，改为 §3.3 的内联脚本。
- `style.css` 中 12 处 `[data-theme="light"]` 限定符去掉：规则本来就恒定生效，取值都是 token，两种模式通用。Vue 构建由 `runtimeModule.ts` 把原生选择器限定在 `.task-runtime` 内，去掉限定不会漏到其它页面；特异性降一级后逐条核对竞争规则，结果不变（原生 72 张截图验证）。`runtimeModule.ts` 中只为 `[data-theme]` 保留的同根分支随之删除。
- 独立文档的首帧脚本同时订阅系统偏好（它不运行 Vue 的 `initTheme`），跟随系统时无需刷新。
- 内嵌任务页继承 Vue 文档根的变量与 `color-scheme`。独立文档读 `ui-foundation.css` 的默认值，跟随模式，不应用自定义种子。
- 改动过的原生资源更新 `?v=`（`20261121-dark-mode`）。不新增静态文件，桥接白名单不变。

## 7. 终端

- `legacy-web/app.js` `attachTerminal` 创建 xterm 时，从宿主元素的计算样式读取 `--ui-color-term-*` 与 `--ui-color-ink`，替换写死的旧皮肤：
  - `foreground` 取 term-fg，`cursor` 取 term-cursor，`cursorAccent` 取 ink；
  - ANSI 八色：black 取 ink，white 取 term-fg，其余对应 term-*；`brightBlack` 取 term-dim；
  - `background` 透明并开启 `allowTransparency`，底色由容器的墨色给出。切换深浅时容器底色随 CSS 改变，已打开的终端不需要重建。
- `runtimeScope.ts` 的 `ScopedTerminal` 原样透传选项，无需改动。

## 8. 验证设计

- **单测**（`theme.test.mjs`）：
  - 深色默认输出等于 `ui-foundation.css` 深色块，双向一致；
  - 六个预设与四个功能色的深色派生等于 `doc/design/console-v2/palette.js`；
  - 预设与边界色（含 `#ffee00`、`#111111` 等）在深色下：按钮文字 ≥ 4.5、实色对卡片底 ≥ 3、派生文字 ≥ 5.5、中性正文对卡片底 ≥ 4.5；
  - 模式存储矩阵：缺失、非法、抛错、写 `system` 删除键；
  - `resolveScheme`；两份 `index.html` 的内联脚本键名一致；
  - `style.css`、`approved-design.css` 无颜色字面量。
- **新脚本 `deploy/flower2api/verify_dark_mode.py`**：
  - **设计比对**：复用现有六个设计脚本的选择器对照表，深色设计稿（`?mode=dark`）对深色产品，覆盖账号、账号编辑、请求、系统更新与进度、任务与工程、运行环境、主题设置、外壳；新增终端画面（授权弹窗的终端容器、文字与 xterm 配色）。
  - **token 检查**：深色下各页面、深层弹窗、气泡的计算颜色都在深色 token 集合内，复用 `tokens_only`；抽样检查正文节点对其实际底色的对比度 ≥ 4.5。
  - **模式行为**：
    - 跟随系统时用 `emulate_media` 切换，根标记与页面底色实时变化；
    - 侧栏切换写入明确模式，刷新后保持；
    - 首帧：在 `DOMContentLoaded` 前读取根标记与 `body` 底色，确认已是深色；
    - 主题设置页的模式计入草稿，画板随草稿变化而控制台不变，保存后生效，恢复默认回到跟随系统；
    - 篡改模式键后按跟随系统处理；
    - 独立 `/runtime/#accounts` 跟随模式，主色仍为默认值。
  - **截图**：深色下 1440 / 390 的主要画面。
- **迁移旧断言**：4 个脚本断言任务宿主固定 `data-theme=light`，改为断言 `data-ui-scheme` 跟随模式，原有对比度等断言保留：
  - `verify_frontend_navigation.py:108`、`verify_native_lifecycle.py:14`、`verify_task_account_config.py:124`：系统偏好为浅色，期望 `light`；
  - `verify_workspace_experience.py:92,236`：在系统深色（`color_scheme='dark'`）下运行，改为期望 `dark`，由此获得一份深色覆盖。
  - 其余脚本写入的旧键 `vibebench-theme` 已不读取，保持不动。
  - `verify_project_browser`、`verify_followup_browser`、`verify_reauth_stack`、`verify_warmup_browser`、`verify_quota_completion_browser`、`verify_forwarding` 等按 `('dark','light')` 循环、读 `.task-runtime.dataset.theme` 或根节点 `dataset.theme` 后点击已不存在的 `#theme-toggle`：删除宿主 `data-theme` 后，`light` 分支与现有 `dark` 分支走同一路径（基线已通过），不迁移；全量回归若出现新失败再按上条口径判定。
- **全量回归**（浅色）：主集合与集合外脚本，失败集合应与基线相同（3 个已登记失败）；原生页 72 张截图与改前比对，差异只出现在 §5 登记的区域。

## 9. 兼容与回滚

- 现有用户：没有模式键，按跟随系统处理；系统为深色的用户升级后直接看到深色。种子格式不变。
- 回滚：单次提交整体回退。种子不变，回退后模式键被忽略，不留脏数据。

## 10. 规范同步

- `web/frontend/ui-guidelines.md`：
  - 主题运行时：模式键、`data-ui-scheme`、深色派生规则、首帧脚本、跟随系统；
  - 外壳类名契约补 `.sidebar-theme-toggle`；
  - 主题设置页的模式草稿；
  - 原生页：去掉固定浅色，终端 token；
  - 独立文档跟随模式；
  - Tests Required 加入新脚本。
- `legacy-web/frontend/`：
  - `component-guidelines.md:169`、`state-management.md:42` 与 `ui-guidelines.md:557,623,636` 中「固定亮色」改为跟随模式；
  - `directory-structure.md:124` 的旧主题切换描述改为 `data-ui-scheme`；
  - `hook-guidelines.md:36` 删除已不存在的 `setupTheme()`；
  - `quality-guidelines.md:12` 去掉「深色模式由子任务 7 接入」；
  - 终端配色改为取 token。
