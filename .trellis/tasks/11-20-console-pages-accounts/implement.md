# 执行计划：账号页迁移

按 design.md 落地。每步完成后勾选；未提交前用 `git diff` 定位回滚点，本任务只在 Push 阶段一次性提交。

## 环境

- Python：`/tmp/uikit-venv/bin/python`（子任务 1 已建），运行验证脚本时设 `PYTHONPATH=services/orchestrator`。缺失时按 `.trellis/spec/web/frontend/ui-guidelines.md` 的运行环境说明重建。
- Dev server：`npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187`（演示页 `http://127.0.0.1:4187/ui-preview.html`）。
- 证据目录：`.deploy/console-ui-revamp/accounts/`（git 忽略）。回归运行器从 `../update-dialog/run_regression.py` 复制，输出目录指向本目录。

## 步骤

- [x] **0. 基线**
  - `npm --prefix apps/web run build`；`node --experimental-strip-types --test apps/web/tests/*.test.mjs`。
  - 在当前 HEAD 跑回归集 37 个与集合外 26 个，保存为 `regression-baseline.json` / `regression-extra-baseline.json`，失败项与失败点记入 `baseline-notes.md`。
  - 用当前构建截 1440 / 390 的账号页、工作区四个页签、授权登录三步，作改动前对照。
  - `git archive HEAD` 导出改动前副本到 `/tmp/accounts-base`（软链 `node_modules`）。
- [x] **1. 组件扩展**（design §4.3、§6）
  - `ModalDialog` 加 `nav` 插槽与 `kit.css` 的 `.fui-modal-nav`；演示页弹窗示例加页签带；`verify_ui_kit.py` 加比对对。
  - `Dashboard.vue` 应用栏加 `.console-toolbar-actions`（包住菜单按钮）与页面操作位 `#console-toolbar-page-actions`，`console-shell.css` 补布局。
  - 验证：构建；`verify_ui_kit.py --url http://127.0.0.1:4187/ui-preview.html`；`verify_ui_shell.py`。
- [x] **2. 共用子组件**（design §3.4、§5）
  - `lib/subscription.ts` 改为 `usageBarTone`，同步 `subscription.test.mjs`、`AgyQuotaRow`。
  - `PlatformBadge` 改用 `Badge`；`ExecutionNodeBadge` 去十六进制回退。
  - `ProxyPicker` 样式迁到 `kit.css`。
  - `UsageWindowStats`、`AgyAccountUsage` 按新排版。
  - 验证：构建；`subscription.test.mjs`；`verify_tokens_design.py`、`verify_task_feedback.py`（共用组件的其它页面）。
- [x] **3. 工具栏、卡片与移动端搜索**（design §3、§6）
  - 新建 `src/accounts.css`（`@layer components`），在 `Accounts.vue` 引入，加入 `theme.test.mjs` 检查列表。
  - 工具栏换 `Toolbar` + `Segmented`；卡片按 §3.2 重排；`accountHealthTone`；`statusStyle()` 去掉调色板类；空状态换 `Empty`。
  - 应用栏搜索按钮（Teleport）、搜索行、短标签分段。
  - 验证：构建；`verify_accounts_design.py`、`verify_account_queue_layout.py`、`verify_execution_node_visibility.py`、`verify_account_filters_ui.py`（先按第 7 步改角色与 390 断言）。
- [x] **4. 账号工作区与授权登录**（design §4、§7）
  - 工作区换 `ModalDialog`（820、页签带、唯一滚动区、配置页底栏 `form` 属性提交）。
  - 四个页签按 §4.2 排版；转发方式 `RadioCardGroup`；复选项 `Checkbox`。
  - 授权登录换 `ModalDialog`（440）。
  - 验证：构建；`verify_accounts_design.py`、`verify_design_parity.py`、`verify_interaction_parity.py`、`verify_proxy_design.py`、`verify_workspace_stability.py`、`verify_agy_accounts_ui.py`。
- [x] **5. 调度详情**（design §5）
  - `SchedulingDetails` 指标卡、阶段条、因子条、SVG 时间轴、会话表换 token 与组件。
  - 验证：`verify_scheduling_preferences.py`、`verify_page_sizes.py`（调度页签 50 行段）、`verify_shared_pagination.py`。
- [x] **6. 删除旧样式**（design §8）
  - 按清单逐段删除 `style.css`、`approved-design.css`、`kit.css` 末尾的账号规则；每条先 grep 选择器确认只服务账号页。
  - 验证：构建；`theme.test.mjs`；对 `style.css`、`approved-design.css` grep `account`、`usage-`、`scheduling-`、`proxy-picker` 残留并逐条说明保留原因。
- [x] **7. 验证脚本**（design §9）
  - 新增 `verify_account_page_design.py`。
  - 改写 `verify_design_parity.py`、`verify_ui_refinements.py`、`verify_diagnostic_alignment.py`、`verify_accounts_design.py`、`verify_account_filters_ui.py`、`verify_agy_accounts_ui.py`；`verify_shared_pagination.py`、`verify_page_sizes.py`、`verify_workspace_stability.py`、`verify_frontend_navigation.py` 只改定位（页签 `radio`、网格类名、标题前缀）；删除 `verify_exact_design.py`。`verify_viewport_interactions.py` 无需改动。
  - 每处改动注明由哪个脚本覆盖或改了什么。
  - 验证：逐个运行，新脚本与改写脚本通过；分诊脚本通过或停在与基线相同的失败点。
- [x] **8. 回归**
  - 改动后跑回归集（去掉 `verify_exact_design`）与集合外，与基线逐项对照。新增失败要么修复，要么证明属于账号页采样并按规则分诊。
  - 负载敏感脚本（`verify_accounts_design`、`verify_interaction_parity`、`verify_prime_history_ui`、`verify_tokens_design`）失败时单独重跑。
- [x] **9. 规范同步**（design §10）
  - `ui-guidelines.md` 的响应式合同、布局与信息组织、账号迁移、组合组件表、测试命令。
- [x] **10. 收尾检查**
  - 构建；`node:test` 全部；`verify_ui_kit.py`、`verify_ui_shell.py`、`verify_account_page_design.py`。
  - 对改动文件 grep 十六进制色值、`border-radius` 字面量、Tailwind 调色板类，确认新增内容只取 token。
  - 1440 / 390 截图交用户目视：卡片（正常、限流、认证错误、停用、反重力）、工具栏与搜索行、工作区四个页签、授权登录三步、删除确认、空状态。

## 风险与回滚点

- **旧规则删除不全**：未分层旧规则会压过 `@layer components` 的新样式。由新脚本的逐项计算样式比对兜底；发现残留就继续删，不加 `!important`。
- **共用组件波及其它页面**：`PlatformBadge`、`ExecutionNodeBadge`、`ProxyPicker` 改动后，跑令牌、任务、请求记录、运行环境相关脚本确认结构与行为不变（第 2 步与第 8 步）。
- **分段与单选卡的角色变化**：脚本中按 `button` 角色定位状态筛选、按原生 `input[type=radio]` 定位转发方式的断言要改为 `radio` 角色；只改定位，不放宽断言。
- **工作区滚动容器变化**：`useActiveScrollbars` 依赖真实滚动事件，内容区成为唯一滚动容器后，`data-active-scroll` 断言改到 `.fui-modal-body`，先确认事件捕获仍生效。
- **回滚**：未提交前按文件 `git restore`；提交后整体回退本任务提交。
