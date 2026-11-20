# 执行计划：请求记录、代理、令牌与会话封禁页迁移

按 design.md 落地。每步完成后勾选；未提交前用 `git diff` 定位回滚点，本任务只在 Push 阶段一次性提交（网关与前端同一提交）。

## 环境

- Python：`/tmp/uikit-venv/bin/python`，运行验证脚本时设 `PYTHONPATH=services/orchestrator`。
- Dev server：`npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187`（演示页 `http://127.0.0.1:4187/ui-preview.html`）。
- 网关：`/root/.cargo/bin/cargo`（1.96）。首次 `cargo test` 全量编译并联网补齐依赖，耗时长，放后台跑；`target` 已被 gitignore，不复用主仓库的 target。
- 证据目录：`.deploy/console-ui-revamp/records/`（git 忽略）。回归运行器从 `../accounts/run_regression.py` 复制，输出目录指向本目录。

## 步骤

- [x] **0. 基线**
  - `npm --prefix apps/web run build`；`node --experimental-strip-types --test apps/web/tests/*.test.mjs`。
  - 在当前 HEAD 跑回归集 36 个与集合外 26 个，保存为 `regression-baseline.json` / `regression-extra-baseline.json`，失败项与失败点记入 `baseline-notes.md`（预期与 4-1 改动后一致）。
  - 后台启动 `cd services/gateway && cargo test --locked --no-run` 预编译；完成后跑一次聚焦测试记录基线。
  - 用当前构建截 1440 / 390 的四页、请求详情四个页签、代理编辑与导入、令牌编辑，作改动前对照。
  - `git archive HEAD` 导出改动前副本到 `/tmp/records-base`。
- [x] **1. 网关计数**（design §8）
  - `proxy_store::summary_index` 多返回 `expires_at`；`directory_counts` 加 `now` 参数并统计 `expiring / expired`；`list` 取一次 `Utc::now()`。
  - `SessionPolicyBlockCounts` 与 `SessionPolicyBlockPage.counts`；store `list` 聚合查询，`total` 由聚合结果按 state 取值。
  - 测试按 design §10.3：`summary_tests` 更新与边界表、`proxy_store` 读回、路由两处断言、`session_policy_block_counts_match_list_filters`、`session_policy_block_admin_contract` 补断言。
  - 验证：`cargo fmt --check`；四组聚焦测试；人工核对 PostgreSQL 语法（别名、`COALESCE`、绑定类型）。
- [x] **2. 组件库扩展**（design §2）
  - `OverviewCard interactive`、`TableCard` 可选标题、`IconTile size=sm`、表格工具类、`ModalDialog placement=side` 与 `description` 插槽。
  - 演示页补示例；`verify_ui_kit.py` 加比对对。
  - 验证：构建；`verify_ui_kit.py --url http://127.0.0.1:4187/ui-preview.html`；`verify_account_page_design.py`（确认账号页弹窗不受影响）。
- [x] **3. 前端类型与夹具**
  - `api.ts` 两处 `counts` 类型；`Proxies.vue` 本地 ref 类型。
  - `verify_proxy_design.py` 夹具补 `expiring / expired`、`usage=false` 返回 `None`；`verify_session_policy_blocks_ui.py` 夹具补 `counts`。
- [x] **4. 会话封禁**（design §7）
  - 新建 `src/session-blocks.css`，删除组件 scoped 样式；分段计数、表格卡片、表格、空状态、390。
  - 验证：构建；`verify_session_policy_blocks_ui.py`（先按 §10.2 改 L148-160）。
- [x] **5. 访问令牌**（design §6）
  - 新建 `src/tokens.css`；表格、名称搜索、`Switch`、`ModalDialog` 编辑；`AccountScopePicker` 样式迁入；删除 `approved-design.css` 对应规则。
  - 验证：构建；`verify_tokens_design.py`（按 §10.2 改写）、`verify_console_ui.py`、`verify_frontend_navigation.py`（失败点不变）。
- [x] **6. 代理管理**（design §5）
  - 新建 `src/proxies.css`；概览卡、表格卡片、表格、展开行、两个弹窗、390；删除 `proxy-design.css`（含 `main.ts` 引入）、`style.css` 代理规则、`approved-design.css` 代理残留；删除 `text-amber-700`。
  - 验证：构建；`verify_proxy_design.py`、`verify_diagnostic_alignment.py`（按 §10.2 改写）、`verify_workspace_stability.py`、`verify_datetime_boundary.py`、`verify_dialog_typography.py`（删代理旧原型比对）、`verify_shared_pagination.py`、`verify_page_sizes.py`。
- [x] **7. 请求记录与详情**（design §4）
  - 新建 `src/request-records.css`（含 `NativeStageDetails` 共享类）；概览卡与日志卡切换、表格卡片头部与筛选区、表格、空状态、底部；详情抽屉换 `ModalDialog placement=side`、页签带外观、四个页签内容、按钮；`NativeStageDetails` 换 token；删除 `request-design.css`、组件死样式、`legacy-web/pagination.css` 的 `.request-list-footer>div`（先 grep）。
  - 验证：构建；`verify_request_detail_design.py`（删旧原型比对）、`verify_remaining_pages.py`（改 radio）、`verify_management_ui.py`（L182-237 通过、失败点 L475 不变）、`verify_management_polish.py`、`verify_execution_node_visibility.py`、`verify_rejected_request_ui.py`、`verify_native_diagnostics_cpu.py`、`verify_cluster_request_ui.py`（失败点 L76 不变）、`verify_viewport_interactions.py`。
- [x] **8. 旧样式收尾与 token 检查**
  - `theme.test.mjs` 加入四个新 css 与四页组件、`NativeStageDetails.vue`、`AccountScopePicker.vue`。
  - 对 `style.css`、`approved-design.css`、`legacy-web/pagination.css` grep `request-`、`proxy-`、`token-`、`session-block`、`block-`、`approved-token`、`picker-`，逐条说明保留原因。
  - 审计脚本：`audit_token_task_design.py`、`audit_environment_proxy_design.py` 删除对应旧原型用例。
- [x] **9. 新验证脚本**（design §10.1）
  - 新增 `verify_records_pages_design.py`：四页 1440 逐项比对 + KNOWN 白名单、行为断言、390 无横向滚动、零控制台错误、截图。
  - 验证：连续三次通过。
- [x] **10. 回归**
  - 改动后跑回归集与集合外，与基线逐项对照。新增失败要么修复，要么证明属于本任务页面采样并按 §10.2 分诊。
  - 负载敏感脚本失败时单独重跑；基线中跑不到的请求 / 代理段（`management_ui`、`remaining_pages`、`page_sizes`）单独核对。
  - 网关收尾：`cargo fmt --check && cargo test --locked`（锁冲突时 `-- --test-threads=4` 重跑）。
- [x] **11. 规范同步**（design §11）
  - `ui-guidelines.md`、`frontend-guidelines.md`、`proxy-directory.md`、`service-architecture.md`。
- [x] **12. 收尾检查**
  - 构建；`node:test` 全部；`verify_ui_kit.py`、`verify_ui_shell.py`、`verify_records_pages_design.py`、`verify_account_page_design.py`。
  - 对改动文件 grep 十六进制色值、`border-radius` 字面量、Tailwind 调色板类，确认新增内容只取 token。
  - 1440 / 390 截图交用户目视：四页列表、请求筛选展开、请求详情四个页签、代理展开行、代理编辑与导入、令牌编辑与搜索无结果、封禁四种状态、空状态与读取失败。

## 风险与回滚点

- **旧规则删除不全**：未分层旧规则会压过 `@layer components` 的新样式。由新脚本的逐项计算样式比对兜底；发现残留就继续删，不加 `!important`。
- **共享类名**：`request-design.css` 的一部分类同时服务 `NativeStageDetails`；`kit.css` 的 `.proxy-picker-*` 服务 `ProxyPicker` 与 `AccountFilterSelect`。删除前 grep 全仓使用者。
- **定位契约**：§1.1 列出的类名、属性与无障碍名称改动前先查脚本；只改定位，不放宽断言。
- **基线跑不到的段**：`management_ui`（L475 之后）、`remaining_pages`（L52 之后）、`page_sizes`（L38 之后）的请求与代理段在基线中不执行，改定位后用临时跳过失败点的本地副本核对一次，记录在证据目录，不提交副本。
- **网关首次编译**：全量编译时间长，第 0 步后台预编译；SQLite 夹具锁冲突按规范降并发重跑。
- **回滚**：未提交前按文件 `git restore`；提交后整体回退本任务提交。
