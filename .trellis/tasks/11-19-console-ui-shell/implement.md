# 执行计划：外壳与通用业务组件

按 design.md 落地。每步完成后勾选；回滚点为每步结束时的工作区状态（未提交前用 `git diff` 定位，本任务只在 Push 阶段一次性提交）。

## 环境

- Python：`/tmp/uikit-venv/bin/python`（子任务 1 已建：`--system-site-packages` + `services/orchestrator/requirements.txt`），运行验证脚本时设 `PYTHONPATH=services/orchestrator`。缺失时按 `.trellis/spec/web/frontend/ui-guidelines.md` 的运行环境说明重建。
- Dev server：`npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187`（演示页 `http://127.0.0.1:4187/ui-preview.html`）。
- 证据目录：`.deploy/console-ui-revamp/ui-shell/`（git 忽略），回归运行器从 `../ui-kit/run_regression.py` 复制后把输出目录指向本目录。

## 步骤

- [x] **0. 基线**
  - `npm --prefix apps/web run build`。
  - 在当前 HEAD 跑回归集（子任务 1 的 37 个脚本）与集合外 26 个脚本，保存为 `regression-baseline.json` / `regression-extra-baseline.json`，基线失败项与失败点记入 `baseline-notes.md`。
  - `git archive HEAD` 导出改动前副本到 `/tmp/uishell-base`（软链 `node_modules`），供集合外脚本对照。
- [x] **1. 设计基准**
  - 把主工作区 `.deploy/ui-revamp/after-v1/mock.html`、`mock.css` 复制到 `doc/design/console-v2/v1/`，`mock.css` 字体路径改为 `../../../../apps/web/src/assets/fonts/`。
  - 浏览器打开 `v1/mock.html#login` 确认字体与纹理正常。
- [x] **2. 新增 token**（design §7）
  - `tokens.ts`：`NEUTRALS` 加 `fill-active`、`on-ink`、`ink-text`、`ink-muted`；`SOFT_TINTED` 加 `fill-active`；阴影加 `--ui-shadow-side`、`--ui-shadow-bar`。
  - `ui-foundation.css` 同步默认值；legacy `index.html` 中 `ui-foundation.css` 的 `?v=` 改为 `20261120-console-ui-shell`。
  - `theme.test.mjs`：静态规则文件列表加 `apps/web/src/console-shell.css`（文件在第 5 步创建，先建空文件占位）。
  - 验证：`node --experimental-strip-types --test apps/web/tests/theme.test.mjs`。
- [x] **3. 组合组件**（design §4）
  - 新增 `ui/page-header`、`ui/overview`（OverviewGrid、OverviewCard）、`ui/icon-tile`、`ui/toolbar`、`ui/entity-card`（EntityCard、EntityBlock、EntityAction）、`ui/table-card`、`ui/save-bar`、`ui/modal`（ModalDialog，实施中补上的父任务 R3 居中弹窗），各带 `index.ts` 导出。
  - `kit.css` 写入对应 `fui-*` 样式与 `.fui-table-actions`。
  - 公开组件带中文 docstring（用途、props、插槽）。
  - 验证：`npm --prefix apps/web run build`；`theme.test.mjs` 静态规则通过。
- [x] **4. 演示页**
  - `previews/` 新增「组合组件」区（新文件 `CompositeShowcase.vue`，在 `UiPreview.vue` 中挂载），数据取自设计稿 accounts / proxies / environments / settings 画面：
    - 页头。
    - 四张概览卡。
    - 工具栏（筛选 + 分段 + 搜索）。
    - 两张实体卡。
    - 代理数据表卡片：含辅助值、固定操作列，窄宽下横向滚动。
    - 居中弹窗（账号编辑画面）。
    - 浮动保存栏。
  - 元素加 `data-testid` 供比对。
  - dev server 目视检查 1440 / 390。
- [x] **5. 外壳**（design §3、§8）
  - 品牌标志用 `public/favicon.svg?v=flower2api-pink-04` 放在墨色方块上（品牌合同，见 design §3.1）。
  - 新建 `src/console-shell.css`（`@layer components`），`main.ts` 在 `kit.css` 之后引入。
  - 改写 `Dashboard.vue`：
    - 品牌行拆分、版本号两态与折叠态图标。
    - 应用栏：标志、标题、菜单。
    - 标题表补齐并改用页面标题。
    - 抽屉改用工具类定位。
    - 底部区结构调整。
    - 数据读取、更新面板、退出逻辑不动。
  - 改写 `AppNavigation.vue`：「系统设置」单独成组，运行数为 0 时用中性样式（加 `data-idle` 等状态钩子）。
  - 删除 `style.css`、`approved-design.css` 中的外壳旧规则（design §8 清单，逐条 grep 确认只服务外壳）。
  - 验证：
    - 构建通过。
    - `verify_frontend_navigation.py`、`verify_dashboard_update.py`、`verify_runtime_platform_version.py`、`verify_console_ui.py`、`verify_browser.py` 先跑一遍，确认类名契约未破。
- [x] **6. 页头替换**（design §5）
  - 8 个页面换 `PageHeader`，去掉分组名与页头按钮的页面级覆盖。
  - 删除 `style.css`、`approved-design.css`、`request-design.css`、`native-environment.css`、`SessionPolicyBlocks.vue` 中对应规则。
  - 验证：构建；逐页打开 1440 / 390 目视；跑 `verify_accounts_design.py`、`verify_remaining_pages.py`、`verify_workspace_stability.py`、`verify_native_environment_edges.py`（必要的选择器先按第 9 步改）。
- [x] **7. 浮动保存栏**
  - `Settings.vue` 换 `FloatingSaveBar`（保留 `settings-save-bar` 类与原按钮、禁用条件）。
  - 删除 `style.css`、`settings-design.css` 中的旧保存栏规则。
  - 验证：`verify_remaining_pages.py`、`verify_scheduling_preferences.py`。
- [x] **8. 登录页**（design §6）
  - 改写 `Login.vue` 模板与样式，脚本逻辑只加密码显示切换。
  - 删除 `style.css` 中 `.login-*` 旧规则。
  - 验证：`verify_browser.py`、`export_frontend_preview.py` 的登录等待点；手动走空密码、错误密码、成功三条路径。
- [x] **9. 验证脚本**
  - `verify_ui_kit.py`：`DESIGN_PAIRS` 增加组合组件对 `mock.html` 的比对对，必要时补 `KNOWN` 白名单（注明原因）。
  - 新增 `verify_ui_shell.py`（design §9.3），默认输出 `.deploy/console-ui-revamp/ui-shell/verify`，参数 `--output`。
  - 既有脚本分诊（design §9.4），每处改动注明「已由 verify_ui_shell.py / verify_ui_kit.py 覆盖」。
- [x] **10. 回归**
  - 改动后跑回归集与集合外脚本，与基线逐项对照。新增失败要么修复，要么证明是外壳 / 页头采样并按规则分诊。
  - 负载敏感脚本（`verify_interaction_parity`、`verify_prime_history_ui`）失败时单独重跑。
- [x] **11. 规范同步**
  - `.trellis/spec/web/frontend/ui-guidelines.md`：
    - 新增「外壳与组合组件」节：类名契约、断点与宽度、折叠与滚动、版本号两态、移动端应用栏与抽屉、页头移动端形态、组合组件 API、登录页约定、登录基准位置。
    - token 表补 6 个新 token。
    - 测试命令补 `verify_ui_shell.py`。
  - 父任务 `design.md` §6 补记登录页基准 `doc/design/console-v2/v1/`。
- [x] **12. 收尾检查**
  - `npm --prefix apps/web run build`。
  - `node --experimental-strip-types --test apps/web/tests/theme.test.mjs`。
  - `verify_ui_kit.py --url http://127.0.0.1:4187/ui-preview.html`。
  - `verify_ui_shell.py`。
  - 对改动文件 grep 十六进制色值与 `border-radius` 字面量，确认新增内容只取 token。
  - 1440 / 390 截图（侧栏展开 / 折叠、有更新、移动抽屉、8 个页头、设置保存栏、登录）交用户对照设计稿目视确认。

## 风险与回滚点

- **旧外壳规则删除不全**：未分层旧规则会压过 `@layer components` 的新样式。第 5、6 步后，用 `verify_ui_shell.py` 的计算样式比对兜底；发现残留就继续删旧规则，不在新样式里加 `!important`。
- **页头替换牵动页面布局**：页面根容器的 `space-y-*` 工具类会覆盖页头底边距，属于预期过渡态。页面主体错位要回到第 6 步检查是否误删页面规则。
- **抽屉定位**：`cn` 合并后仍有残留居中类时，改为给 `DialogContent` 传 `class` 覆盖并在 `verify_ui_shell.py` 断言抽屉贴左，不用 `!important`。
- **回滚**：未提交前按文件 `git restore`；提交后整体回退本任务提交。
