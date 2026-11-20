# 执行计划：节点管理与系统设置页迁移

按 design.md 落地，每步完成后勾选。本任务只在 Push 阶段一次性提交，提交前用 `git diff` 定位回滚点。

## 环境

- Python：`/tmp/uikit-venv/bin/python`；运行验证脚本时设 `PYTHONPATH=services/orchestrator`。
- Dev server：`npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187`，已在运行。演示页为 `http://127.0.0.1:4187/ui-preview.html`。
- 证据目录：`.deploy/console-ui-revamp/nodes-settings/`（git 忽略），已有 `peek.py` 与 `baseline/` 截图。回归运行器从 `../records/run_regression.py` 复制，输出目录指向本目录。

## 步骤

- [x] **0. 基线**
  - `npm --prefix apps/web run build`；`node --experimental-strip-types --test apps/web/tests/*.test.mjs`。
  - 回归基线沿用 `../records/regression-after.json` 与 `regression-extra-after.json`（业务代码未变），写入 `baseline-notes.md`。
  - 单独跑一次 `verify_cluster_ui.py`、`verify_node_password_ui.py`、`verify_remaining_pages.py`、`verify_scheduling_preferences.py`、`verify_prime_history_ui.py`，记录通过情况与失败点。
  - `git archive HEAD` 导出改动前副本到 `/tmp/nodes-settings-base`。
- [x] **1. 组件库扩展**（design §2）
  - `NumberInput` / `ChoiceSelect` 加 `label-extra` 插槽；演示页示例；`verify_ui_kit.py` 比对对。
  - 验证：构建；`verify_ui_kit.py --url http://127.0.0.1:4187/ui-preview.html`。
- [x] **2. 节点管理**（design §4）
  - 新建 `src/nodes.css`。
  - 概览卡与 `attention()`、实体卡、徽标色表、资源与信息块、操作行。
  - 账号执行节点与迁移面板的外观；两个弹窗换 `ModalDialog`；删除三个组件的样式块。
  - 查 `verify_node_password_ui` L36 的原因。
  - 验证：构建；`verify_cluster_ui.py`（先改 L184）、`verify_node_password_ui.py`、`verify_cluster_draft_ui.py`、`verify_execution_node_visibility.py`、`verify_ui_shell.py`。
- [x] **3. 系统设置**（design §5）
  - 新建 `src/settings.css`，删除 `settings-design.css`（先 grep）。
  - 页头搜索与计数、导航计数与图标、去掉分类标题行、搜索结果行。
  - 段落卡头部、字段标签行与「已修改」、`Switch`、预设按钮、预热记录徽标、390。
  - 验证：构建；`verify_remaining_pages.py`（核对后改 L52）、`verify_scheduling_preferences.py`、`verify_session_policy_blocks_ui.py`、`verify_prime_history_ui.py`、`verify_ui_shell.py`、`verify_frontend_navigation.py`（失败点不变）、`verify_console_ui.py`。
- [x] **4. token 检查**
  - `theme.test.mjs` 加入两个 css 与四个组件。
  - 对改动文件 grep 十六进制与 `rgb()` 色值、`border-radius` 字面量、`!important`、Tailwind 调色板类。
- [x] **5. 新验证脚本**（design §7.1）
  - 新增 `verify_nodes_settings_design.py`。
  - 验证：连续三次通过。
- [x] **6. 回归**
  - 跑回归集 36 个与集合外 26 个，与基线逐项对照。
  - 负载敏感脚本失败时单独重跑。
- [x] **7. 规范同步**（design §8）
  - `ui-guidelines.md`。
- [x] **8. 收尾检查**
  - 构建；`node:test` 全部；`verify_ui_kit.py`、`verify_ui_shell.py`、`verify_nodes_settings_design.py`、`verify_records_pages_design.py`、`verify_account_page_design.py`。
  - 1440 / 390 截图交用户目视：
    - 节点：两页、八种状态的节点卡、添加与改名弹窗、迁移面板；
    - 设置：已修改状态、搜索结果与空态、预热记录。

## 风险与回滚点

- **旧规则残留**：`settings-design.css` 是未分层的旧规则，必须整体删除而不是覆盖。由新脚本的计算样式比对兜底。
- **无障碍名称**：「已修改」标签放在 `label` 元素之外，避免改变 `get_by_label` / `get_by_role(name=…)` 的匹配结果。
- **`ModalDialog` 关闭拦截**：节点弹窗保存中不可关闭，先确认事件透传，再迁移。
- **回滚**：未提交前按文件 `git restore`；提交后整体回退本任务提交。
