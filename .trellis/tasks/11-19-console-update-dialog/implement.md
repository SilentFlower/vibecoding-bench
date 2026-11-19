# 执行计划：系统更新弹窗与步骤记录

按 design.md 落地。每步完成后勾选；未提交前用 `git diff` 定位回滚点，本任务只在 Push 阶段一次性提交。

## 环境

- Python：`/tmp/uikit-venv/bin/python`（子任务 1 已建），运行验证脚本时设 `PYTHONPATH=services/orchestrator`。缺失时按 `.trellis/spec/web/frontend/ui-guidelines.md` 的运行环境说明重建。
- Dev server：`npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187`（演示页 `http://127.0.0.1:4187/ui-preview.html`）。
- 证据目录：`.deploy/console-ui-revamp/update-dialog/`（git 忽略）。回归运行器从 `../ui-shell/run_regression.py` 复制，输出目录指向本目录。

## 步骤

- [x] **0. 基线**
  - `npm --prefix apps/web run build`。
  - 在当前 HEAD 跑回归集 37 个与集合外 26 个，保存为 `regression-baseline.json` / `regression-extra-baseline.json`，失败项与失败点记入 `baseline-notes.md`。
  - 跑一次 `test_system_updater`、`test_system_migrations` 作后端基线。
  - `git archive HEAD` 导出改动前副本到 `/tmp/updialog-base`（软链 `node_modules`），供对照。
- [x] **1. 后端步骤记录**（design §2）
  - `system_updater.py`：`STEP_LIMIT`、`_record` 追加去重、`_public_operation` 加 `steps`。
  - 单测：`test_system_updater.py` 加正常安装、宿主恢复路径、旧操作、上限四个用例；`test_system_migrations.py` 加迁移步骤用例。
  - 验证：`cd deploy/flower2api && PYTHONPATH=../../services/orchestrator /tmp/uikit-venv/bin/python -m unittest test_system_updater test_system_migrations`。
- [x] **2. 步骤表纯函数**（design §3.5）
  - `api.ts` 加 `steps` 类型。
  - 新增 `lib/updateSteps.ts`（含阶段文案表与行内说明），带中文 docstring。
  - 新增 `apps/web/tests/update-steps.test.mjs`。
  - 验证：`node --experimental-strip-types --test apps/web/tests/update-steps.test.mjs`。
- [x] **3. 提示条组合组件**（design §3.7）
  - `ui/notice-strip/NoticeStrip.vue` + `index.ts`，`kit.css` 加 `.fui-strip*`。
  - 演示页 `CompositeShowcase.vue` 加示例（`data-testid=notice-strip`）。
  - `verify_ui_kit.py` 加比对对。
  - 验证：构建；`verify_ui_kit.py --url http://127.0.0.1:4187/ui-preview.html`。
- [x] **4. 弹窗组件**（design §3.2–3.4、3.6）
  - 新增 `SystemUpdateDialog.vue`：搬入 `SystemUpdates.vue` 的数据与动作，按视图表实现五个视图、底栏、直接安装、`ConfirmationDialog` 二次确认、取消等待、轮询与重连。
  - 新增 `src/system-update.css`，在 `main.ts` 中于 `console-shell.css` 之后引入。
  - 验证：构建；dev server 不便挂外壳时，用第 6 步的真实构建加合成夹具目视 1440 / 390。
- [x] **5. 外壳与路由接入**（design §3.1）
  - `router.ts` 的 `updates` 子路由改为账号页。
  - `Dashboard.vue` 换成新弹窗，加 `/updates` 打开、关闭回 `/` 的逻辑，删掉原生 `<dialog>` 与 `X` 等不再使用的导入。
  - 删除 `SystemUpdates.vue`。
  - 删除 `approved-design.css`、`style.css` 中的旧更新样式（design §4，逐条 grep 确认只服务旧更新页）。
  - 验证：构建；`theme.test.mjs`；`verify_dashboard_update.py`、`verify_runtime_platform_version.py`（先按第 6 步改选择器）。
- [x] **6. 验证脚本**（design §6.2）
  - 改写 `verify_update_design.py`（新设计稿比对 + 原有行为检查）与 `verify_system_update_browser.py`（弹窗流程）。
  - 分诊 `verify_design_parity.py`、`verify_management_ui.py`、`verify_frontend_navigation.py`、`verify_accounts_design.py`、`verify_workspace_experience.py`、`verify_ui_shell.py`、`verify_runtime_platform_version.py`。每处改动注明由哪个脚本覆盖或改了什么。
  - 验证：逐个运行，改写的两个脚本通过；分诊脚本通过或停在与基线相同的失败点。
- [x] **7. 回归**
  - 改动后跑回归集与集合外，与基线逐项对照。新增失败要么修复，要么证明属于更新页采样并按规则分诊。
  - 负载敏感脚本（`verify_interaction_parity`、`verify_prime_history_ui`、`verify_tokens_design`）失败时单独重跑。
- [x] **8. 规范与文档同步**（design §7）
  - `platform-online-update.md`、`ui-guidelines.md`、`SYSTEM-UPDATES.md`。
- [x] **9. 收尾检查**
  - 构建；`theme.test.mjs` 与 `update-steps.test.mjs`；后端两组单测。
  - `verify_ui_kit.py`、`verify_update_design.py`、`verify_system_update_browser.py`、`verify_ui_shell.py`。
  - 对改动文件 grep 十六进制色值与 `border-radius` 字面量，确认新增内容只取 token。
  - 1440 / 390 截图交用户目视：概览（有更新 / 已是最新 / 检查失败）、进度（维护中 / 完成 / 失败恢复）、三个二级视图、回退确认、未接入。

## 风险与回滚点

- **旧更新样式删除不全**：未分层旧规则会压过 `@layer components` 的新样式。由 `verify_update_design.py` 的逐项计算样式比对兜底；发现残留就继续删，不加 `!important`。
- **嵌套弹窗**：`ConfirmationDialog` 叠在 `ModalDialog` 上，焦点、Esc 与遮罩点击只关闭上层。由 `verify_system_update_browser.py` 的回退 / 恢复场景断言；有问题先查 reka-ui 嵌套 Dialog 行为，不手写焦点管理。
- **`/updates` 打开模态后挡住导航**：`verify_frontend_navigation.py` 先关弹窗再遍历。若其他脚本直接访问 `/updates` 后操作背景页，也按此处理。
- **后端回滚点**：第 1 步独立，单测通过后再动前端。前端出问题可单独 `git restore` `apps/web` 与脚本，不影响后端改动。
- **回滚**：未提交前按文件 `git restore`；提交后整体回退本任务提交。
