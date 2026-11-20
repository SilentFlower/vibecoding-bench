# 执行计划：子任务 4 整体验收

按 design.md 执行，每步完成后勾选。只在 Push 阶段一次性提交。

## 环境

- Python：`/tmp/uikit-venv/bin/python`；运行验证脚本时设 `PYTHONPATH=services/orchestrator`。
- Dev server：`npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187`（已在运行）。
- 证据目录：`.deploy/console-ui-revamp/pages-acceptance/`（git 忽略）。回归运行器从 `../nodes-settings/run_regression.py` 复制。

## 步骤

- [x] **0. 归属核对**
  - 三个子任务的 `task.json`（completed / closed）、业务与任务记录提交、当前 HEAD 与 upstream 一致。
  - 记入验收矩阵草稿。
- [x] **1. 修 `verify_cluster_request_ui`**（design §2）
  - 改 L76 定位，运行到通过。
  - 如果后续断言暴露页面问题，按 design §2 分类处理。
- [x] **2. 修 `verify_ui_refinements`**
  - 先核对 `oauthPlatform` 默认值与夹具，再改 L61 与直连场景的期望体，运行到通过。
- [x] **3. 修 `verify_page_sizes`**
  - 核对夹具账号总数与默认页大小，从夹具算出期望值。
  - 运行到通过：代理、请求记录、调度会话、抓包分页都要跑到。
- [x] **4. 修 `verify_management_ui`**
  - L475 改为在资料气泡里断言邮箱。
  - 运行到通过：请求详情、采集状态、性能页签、内容采集设置直达都要跑到。
  - 这个脚本最长，后续失败逐个分类处理。
- [x] **5. 全量复核**（design §3）
  - 构建；`node:test` 全部。
  - `verify_account_page_design.py`、`verify_records_pages_design.py`、`verify_nodes_settings_design.py`、`verify_ui_kit.py`、`verify_ui_shell.py`。
  - 回归集 36 个 + 集合外 26 个，与基线逐项对照，失败只剩 7 个已登记脚本，且失败点不变。负载敏感脚本单独重跑。
  - 4 个修好的脚本各连续通过两次。
- [x] **6. 截图矩阵**（design §4）
  - 七个页面 × 1440×900 / 390×844，配设计稿对应画面，生成对照页。
- [x] **7. 样式检查**（design §5）
  - grep 并逐条处置，结果记入验收矩阵。
- [x] **8. 验收矩阵**（design §6）
  - 写 `research/acceptance-matrix.md`。
  - 在 `prd.md` 的整体验收里补实际结论。

## 风险与回滚点

- **跑通后暴露真实问题**：失败点后约 120 行断言从未对新页面运行，可能发现迁移引入的问题。限本任务页面的直接修；超出范围的登记后询问。
- **断言放宽**：每处改动对照 design §2 的判断标准，业务事实不能变弱。
- **负载敏感**：并行失败的脚本单独重跑两次再下结论。
- **回滚**：未提交前按文件 `git restore`。
