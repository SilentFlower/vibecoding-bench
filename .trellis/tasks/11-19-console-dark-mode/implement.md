# 执行计划 — 控制台深色模式

证据目录统一为 `.deploy/console-ui-revamp/dark-mode/`（git 忽略）。每步完成后在本文件勾选并写实际结果。

## 步骤

- [x] **0. 基线**
  - 复制子任务 6 的回归 runner 到证据目录，新增 `verify_dark_mode` 槽位。
  - 基线复用子任务 6 的最终回归（之后产品代码未变），失败集合为 3 个已登记脚本：`verify_forwarding`、`verify_management_polish`、`verify_agy_request_records`。
  - 用 `capture_states.py` 截原生页 36 个状态 / 72 张改前图；另截 Vue 主要页面（账号、请求、代理、令牌、会话封禁、节点、设置、主题设置、系统更新、登录）1440 / 390 的浅色改前图。作为后续「浅色只在登记区域变化」的比对基准。
- [x] **1. 深色基准入库**（design §2）
  - `research/design-dark/` 的 `mock.html`、`mock.css`、`palette.js` 同步到 `doc/design/console-v2/`，字体路径改回。
  - 设计稿浅色 14 个画面改前改后逐像素一致，证明颜色字面量换成变量没有改变浅色。
  - 现有 6 个设计比对脚本照常通过。
- [x] **2. 派生与默认值**（design §3.1、§3.2）
  - 先写单测并确认失败：深色默认值双向一致、派生等于 `palette.js`、深色对比度矩阵、模式存储矩阵、`resolveScheme`、浅色新增 token。
  - `color.ts` 加 `lightenUntil`；`tokens.ts` 加 `NEUTRALS_DARK`、深色主色组与功能色组、深色阴影，`createTheme(seed, scheme)`；新增 `knob`、`term-*`。
  - `ui-foundation.css` 补浅色新 token、`:root[data-ui-scheme=dark]` 深色块与 `color-scheme`。
  - 单测通过即完成本步。**回滚点 A**
- [x] **3. 运行时、首帧与跟随**（design §3.3）
  - `runtime.ts`：模式读写、`resolveScheme`、`initTheme` 写 `data-ui-scheme` 并订阅系统偏好。
  - `composables/useThemeMode.ts`：共享 `mode`、`scheme` 与 `setMode`。
  - `apps/web/index.html` 加首帧内联脚本；单测校验键名一致。
- [x] **4. 样式收尾**（design §5）
  - `style.css` 旧层改指 token，删除无引用变量与规则；`.approved-run-dialog` 取 token；`approved-design.css` 取 token。
  - 两个文件加入静态规则清单。
  - 开关滑块改取 `knob`；墨底区块与其子元素文字改取 `ink-text` / `on-ink`。
- [x] **5. 外壳快捷切换**（design §4.1）
  - 桌面侧栏与移动端抽屉加 `.sidebar-theme-toggle`，图标与名称随深浅变化。
- [x] **6. 主题设置页**（design §4.2）
  - 模式分段与 `draftMode`：待应用数、撤销、恢复默认、离开保护、保存。
  - `ThemePreview` 增加 `scheme` 属性；草稿模式与侧栏切换的同步。
  - `UiPreview.vue` 局部主题按当前深浅派生。
- [x] **7. 原生页、独立入口与终端**（design §6、§7）
  - 删除两处写死的 `data-theme`；`legacy-web/index.html` 改为首帧内联脚本；去掉 12 处 `[data-theme="light"]` 限定符，相应节标题改名。
  - `app.js` 的 xterm 配色改为从 token 读取，背景透明。
  - 改动过的原生资源把 `?v=` 改为 `20261121-dark-mode`。
- [x] **8. 深色逐页走查**
  - 构建后在深色下逐页对照深色稿，范围：
    - Vue 页、登录页、外壳与移动端抽屉；
    - 系统更新弹窗、主题设置页；
    - 任务与工程六个页签及 21 个原生弹窗、运行环境与侧抽屉；
    - 气泡、通知、确认框、调度图表、组件演示页。
  - 修正只在深色下才暴露的取色语义问题，比如把卡片底当作有色底上的文字色。修复方式是改用正确的 token，不为深色单独加覆盖规则。
- [x] **9. 验证脚本**（design §8）
  - 新增 `verify_dark_mode.py`：设计比对（复用 6 个设计脚本的对照表，外加终端）、token 检查与正文对比度抽样、模式行为、首帧、主题设置页模式草稿、独立入口、深色 1440 / 390 截图。
  - 迁移 4 个断言 `data-theme=light` 的脚本。
- [x] **10. 规范**（design §10）
  - `ui-guidelines.md` 与 legacy-web 的 6 份规范改为跟随模式的约定；写入模式键、`data-ui-scheme`、派生规则、首帧脚本、侧栏切换契约与终端 token；Tests Required 加入新脚本。
- [x] **11. 全量验证与对照页**
  - 运行下方全部命令。
  - 生成 `index.html` 对照页：深色稿与产品深色 1440 并排、390 截图、深层弹窗与终端、浅色改前改后差异（只应出现在 design §5 登记的区域）。

## 验证命令

```bash
node --check apps/legacy-web/app.js && node --check apps/legacy-web/projects.js && node --check apps/legacy-web/environments.js && node --check apps/legacy-web/ui-controls.js
cd apps/web && npm run build && node --experimental-strip-types --test tests/*.test.mjs
python3 deploy/flower2api/verify_dark_mode.py
python3 deploy/flower2api/verify_theme_settings.py && python3 deploy/flower2api/verify_ui_shell.py && python3 deploy/flower2api/verify_native_pages_design.py
python3 .deploy/console-ui-revamp/dark-mode/run_regression.py after      # 期望只剩 3 个已登记失败
```

不新增静态文件，桥接白名单不变，不需要跑 `cargo test runtime_bridge`。

## 风险与回滚点

- **深色下的取色语义错误**：浅色下正确但深色下错误的用法，静态规则查不出来，例如把卡片底当作有色底上的文字色、把 text-4 用在墨底上。第 8 步逐页走查加第 9 步的对比度抽样是主要防线；已知的两处（开关滑块、墨底文字）在第 4 步先改。
- **首帧闪烁**：开发服务器的样式由脚本注入，看得到闪烁；验收以构建产物为准，第 9 步在 `DOMContentLoaded` 前断言。
- **浅色回归**：旧层改指 token、终端配色统一会带来少量浅色变化。第 0 步基准加第 11 步比对，确认差异只出现在登记区域。
- **脚本口径**：在系统深色下运行的脚本会开始看到深色，第 9 步已列出迁移清单；全量回归中再出现新失败，按「是否属于跟随模式的预期变化」逐个判定，不放宽业务断言。
- **回滚点**：A（派生与默认值完成后，界面尚未接入）。最终单次提交，必要时整体回退。

## 实际结果

- **0 基线**：子任务 6 的 `/tmp/uikit-venv` 已不存在，按 `services/orchestrator/requirements.txt` 重建。原生页 36 状态 / 72 张改前图（`before-native/`）；Vue 10 页 1440 / 390 改前图由 `git archive HEAD` 导出构建后截取（`before-vue/`）。`capture_vue.py` 冻结夹具进程墙钟、uuid 与随机数，同一源码树两次截图逐像素一致（初版未冻结时，账号重置倒计时、封禁时间等随墙钟变化，曾误报差异）。
- **1 深色基准**：`mock.html`、`mock.css`、`palette.js` 入库，字体路径改回。浅色 14 画面中 13 个逐像素一致；`#theme` 有 8256 像素（最大通道差 11）变化：预设色块第三段 `#f3f4f8` → `var(--fill-2)`、色块描边与画布网点改为变量，与产品主题页已用的 `fill-muted` 对齐。7 个设计比对脚本在新稿上全部通过。
- **2 派生**：单测先失败后通过。边界色 `#000000` 暴露 `lightenUntil` 被 8 位舍入卡住，改为原地不动时累加增量（整体累计增量会让 6 个确认取值偏差，未采用），见 design §3.2。
- **3–7**：按 design 实施；细节调整已同步 design（`onThemeModeChange` / `applyThemeMode`、组合式以 `data-ui-scheme` 为准、画板 iframe 内不跟随系统、无保存种子但有内联变量时整组重写、`.theme-mode [role=radio][value]` 定位、保存模式失败回滚种子、深色预设色块取派生值、侧栏身份区 -1px、`runtimeModule.ts` 删去 `[data-theme]` 同根分支、独立文档首帧脚本订阅系统偏好、滚动条与运行详情弹窗圆角取 token）。
- **8 深色走查**：Vue 10 页 1440 / 390、原生 36 状态、21 个深层弹窗、独立 `/runtime/` 三个状态均为深色 token，未发现需要改取色语义的问题。观察到：键盘打开的环境抽屉容器有浏览器默认 `:focus-visible` 环（`outline-ring/50` → `--ring` = text），浅色为灰环、深色为浅色环，属既有键盘焦点指示，未改。
- **9 验证脚本**：`verify_dark_mode.py` 通过：262+ 组计算样式比对，21 个深层弹窗，16 个视图 1134 个正文节点对比度 ≥ 4.5，模式行为全部断言通过。4 个脚本迁移为断言 `data-ui-scheme`。
- **10 规范**：`web/frontend/ui-guidelines.md` 与 legacy-web 5 份规范已改为跟随模式的约定。
- **11 全量验证**：`node --check` 4 个原生脚本通过；构建通过；前端单测 32 / 32。回归主集合 38（含 `verify_dark_mode`）+ 集合外 26：失败恰为基线已登记的 3 个（`verify_forwarding` 缺 `--manifest`、`verify_management_polish` 系统更新写入断言、`verify_agy_request_records` 缺 `--image/--baseline`），原因与基线一致。浅色改后与改前比对：Vue 只有侧栏新增按钮（73 像素）、更新弹窗遮罩下同一按钮、主题页新增「主题模式」分组；原生页差异均在 design §5 登记区域（墨底文字、xterm 配色、运行详情弹窗、旧层 `--background` / `--foreground` 改指 token 的 ≤ 1 通道差、遮罩下的侧栏按钮）。对照页 `.deploy/console-ui-revamp/dark-mode/index.html`（76 张截图）。
