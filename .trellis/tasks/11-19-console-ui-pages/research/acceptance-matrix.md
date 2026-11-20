# 子任务 4 验收矩阵

- **基准**：HEAD `8b4ed370`，加本次 4 个脚本改动（产品代码未改）。
- **证据目录**：`.deploy/console-ui-revamp/pages-acceptance/`（git 忽略）。

## 子任务归属

| 子任务 | 状态 | 业务提交 | 任务记录 | Check-All |
| --- | --- | --- | --- | --- |
| 4-1 账号（`11-20-console-pages-accounts`） | completed / closed | `08c84a9d` | `646a5bb3` | 通过 |
| 4-2 请求、代理、令牌、会话封禁（`11-20-console-pages-records`） | completed / closed | `9765980b` | `f640912b` | 通过 |
| 4-3 节点、设置（`11-20-console-pages-nodes-settings`） | completed / closed | `2afbe5b1` | `8b4ed370` | 通过（CHK-001 已修） |

## 需求对照

| 需求 | 子任务 | 证据（均在最终提交上运行） | 结论 |
| --- | --- | --- | --- |
| 账号：卡片字段与操作不变、状态条语义色、首屏三张操作栏、居中编辑弹窗与四页签、转发单选卡 | 4-1 | `verify_account_page_design.py` 79 组（白名单 5）含「首行三张卡片操作栏在首屏内」「健康条四种语义色」；`verify_accounts_design`、`verify_account_filters_ui`、`verify_account_queue_layout`、`verify_ui_refinements`（授权登录全流程，本次修复） | 满足 |
| 请求记录：四张概览卡与日志级别卡切换、表头工具区、主值加辅助值 | 4-2 | `verify_records_pages_design.py` 63 组（白名单 1）含「日志卡点击保存」；`verify_management_ui`（请求详情、采集状态、性能页签、账号名称与邮箱，本次修复）；`verify_request_detail_design`、`verify_cluster_request_ui`（本次修复）、`verify_execution_node_visibility` | 满足 |
| 代理：概览卡、数据表、延迟与到期着色、行操作 | 4-2 | `verify_records_pages_design.py`；`verify_proxy_design`；`verify_page_sizes` 代理 50 条（本次修复） | 满足 |
| 访问令牌：数据表、遮蔽与复制、启停开关 | 4-2 | `verify_records_pages_design.py`；`verify_tokens_design`；`verify_console_ui` | 满足 |
| 会话封禁：分段筛选带计数、时区与刷新只说明一次 | 4-2 | `verify_records_pages_design.py`；`verify_session_policy_blocks_ui` | 满足 |
| 节点：四张概览卡、「待检查」琥珀色、小号按钮 | 4-3 | `verify_nodes_settings_design.py` 55 组（白名单 0）含八种状态徽标色与待处理口径；`verify_cluster_ui`、`verify_node_password_ui`、`verify_cluster_draft_ui` | 满足 |
| 系统设置：分类导航、两列字段、「已修改」、草稿与撤销不变 | 4-3 | `verify_nodes_settings_design.py`；`verify_remaining_pages`（59 项）、`verify_scheduling_preferences`、`verify_prime_history_ui` | 满足 |
| 390 移动端 | 4-1 / 4-2 / 4-3 | 三个设计稿脚本的 390×844 检查（无横向溢出、单列、搜索入口）；截图对照见 `screens/index.html` | 满足；设计稿只画了账号页的 390 |
| 组合组件首次接入与就地扩展 | 4-1 / 4-2 / 4-3 | `verify_ui_kit`（含 `label-extra` 演示）、`verify_ui_shell` | 满足；见下方偶发说明 |

## 整体验收项

| 项 | 证据 | 结论 |
| --- | --- | --- |
| R-A1 修好 4 个既有失败脚本 | 见下节「脚本修复」 | 4 个全部断言跑通，最终改动后各至少连续通过两次（单独一次、回归一次）；未暴露页面问题，产品代码未改 |
| R-A2 全量复核 | 构建通过；`node:test` 20/20；回归集 32/36（`regression-after.json`）、集合外 23/26（`regression-extra-after.json`） | 失败只剩登记的 7 个，失败点与基线逐一相同；比基线多通过 5 个（修好的 4 个，加上次负载敏感的 `verify_console_ui`） |
| R-A3 截图矩阵 | `screens/index.html`、`screens/contact-1440.png`、`screens/contact-390.png` | 七页 1440 结构、概览卡、表格卡、配色与设计稿一致，差异只来自夹具数据；390 均单列、无横向溢出 |
| R-A4 样式检查 | 对 6 个页面样式文件和 15 个组件 grep | 十六进制、`rgb()`、`!important`、Tailwind 调色板类均为 0；圆角字面量只有 `50%` / `999px` / `inherit`，属于 `theme.test.mjs` 允许的形状值；旧 `proxy-design.css`、`request-design.css`、`settings-design.css` 已删除且无引用；全站 `!important` 从 28 处降到 9 处（原生页 8 处、减少动态效果的无障碍覆盖 1 处） |
| R-A5 验收矩阵 | 本文件 | 完成 |

## 脚本修复

| 脚本 | 位置（原行号） | 原因（类型） | 改动 | 依据 |
| --- | --- | --- | --- | --- |
| `verify_cluster_request_ui` | L76–77 | 结构变化 | 改为断言执行节点徽标 `[data-execution-node] > span` 为「默认本机」；节点键 `local` 改在悬停提示 `.fui-info-content code` 里核对 | `.execution-node-heading` 在 `f7a10d0e` 移除，节点键只在提示里展示 |
| `verify_ui_refinements` | L61、L64 | 期望过时 | 授权链接提交体加 `platform: 'claude_code'`（选线与直连两处） | `Accounts.vue` `generateOAuthUrl` 按多平台改造总带授权平台；新建账号没有 `account_id`，序列化时省掉 |
| `verify_page_sizes` | L38 | 夹具漂移 | 账号总数取 `len(fixture.accounts)`（101），由它算出第二页、末页（5 张）和 24 条首页的期望，并补查第二页查询参数 | 令牌夹具把账号补到 101 个；末页不满的检查意图保留且更严 |
| `verify_management_ui` | L475、L538 | 期望过时 | 请求列表邮箱改为悬停账号名，在资料气泡里核对 | `frontend-guidelines.md`「请求账号保留当前名称和邮箱」：列表只显示名称，资料气泡提供邮箱 |
| `verify_management_ui` | L492 | 期望过时 | 环境标题后带平台徽标：标题自身文字（不含徽标）与卡片 `aria-label` 都精确等于环境名，徽标单独断言为「Claude Code」 | 徽标在 `f7a10d0e` 加入 |
| `verify_management_ui` | L488 | 证据质量 | 请求详情截图加 `animations='disabled'` | 调整宽度后弹窗有 0.2s 过渡，原截图拍到半途（左边缘 -265px）；600ms 后复位，非页面缺陷 |

修复后，原失败点之后的断言首次在新页面上运行，覆盖以下内容，全部通过：

- 请求详情四页签、采集关闭与五种采集状态、性能页签的本机准备耗时；
- 长账号名与长邮箱在 1280 和 390 下无溢出，以及缺资料、只有邮箱、只有名称、名称与邮箱相同四种标签；
- 代理、请求记录、调度会话与抓包分页；
- 授权回填账号配置、取消不创建账号、直连；
- AGY 本机节点、凭据代次、工作进程，以及 1440 和 390 布局。

## 偶发与遗留

- **`verify_ui_kit` / `verify_ui_shell` 偶发失败**：紧接三个设计稿脚本后各失败一次，分别是演示页表格行悬停背景色和外壳版本徽标「可更新」底色。无代码改动，单独重跑各连续 3 次通过。两处都依赖过渡动画或异步检查的时序，记为时序偶发。
- **7 个既有失败脚本**：与本任务页面无关或无法在本机运行，留给子任务 6 或父任务最终复核。
  - `verify_forwarding`、`verify_agy_request_records`：需真实发行物。
  - `verify_task_login_design`、`verify_native_environment_edges`、`verify_native_lifecycle`、`verify_frontend_navigation` L105：原生页。
  - `verify_management_polish` L87：系统更新检查写入。
