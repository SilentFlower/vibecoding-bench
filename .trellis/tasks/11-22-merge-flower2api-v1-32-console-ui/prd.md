# 再次合并 flower2api 主线（v1.32.1）并移植新功能到第二版控制台

## Goal

把 `origin/flower2api`（`faa53196`，v1.26.1 → v1.32.1）合并进 `feat/console-ui-revamp`。主线新功能全部保留，并以第二版控制台的结构和 token 呈现，让本分支达到可以正式合回主线的状态。

## Background

- **分叉情况**：上次合并带入主线 `9c80a39a`。之后主线新增约 60 个提交（v1.27.0 至 v1.32.1），绝大多数是 AGY、网关、编排与集群后端改动。本地 `flower2api` 与 `origin/flower2api` 同为 `faa53196`。
- **合并现场**：已执行 `git merge --no-ff --no-commit origin/flower2api`，现场停在 `MERGE_HEAD`。共 7 个冲突文件，其余已自动合并：
  - `apps/web/src/components/Accounts.vue`
  - `apps/web/src/components/Nodes.vue`
  - `apps/web/src/components/RequestDiagnostics.vue`
  - `apps/web/src/components/runtime/EnvironmentKernel.vue`
  - `apps/web/src/request-design.css`（本分支已删除、主线修改）
  - `deploy/flower2api/verify_agy_accounts_ui.py`
  - `deploy/flower2api/verify_execution_node_visibility.py`
- **主线触及前端的 7 个提交**及其界面内容：
  - `07783508` 系统提示词位置试验：账号表单新增「系统提示词移入用户消息（试验）」，字段 `agy_system_prompt_as_user_reminder`。
  - `3a5061d4`、`79225c30` 默认登记运行环境并持续补热：运行环境卡片准备状态附带原因（`preparation_reason` → `agyPreparationReasons`），新增 `preparing` / `failed` / `disabled` 状态，空闲数不再由 `workers - active` 推算。
  - `4a318b49` 工具续轮模式：内核面板新增「工具续轮模式」选择与保存（`/agy-tool-continuation`）；请求链路新增控制 HTTP 状态、响应读取中断、原生流状态、工具续轮路径；性能页区分 CRIU 恢复与普通启动（`start_source`）。
  - `efcd59ef` 会话粘性：新组件 `RequestSessionId.vue`，原始 Session ID 缺省时显示 `derived_session_id` 并标记「网关派生」；样式原写在 `request-design.css`。
  - `f2b7828c` 反重力账号双向节点迁移：账号页按 `/runtime/api/agy-accounts/nodes` 显示反重力归属；节点页不再额外累加反重力账号数；节点选择器与迁移组件支持反重力账号（`agy` 路径、版本 `1.5.9`、`migration_ready`）。
  - `cc19a7e7` 环境卡片显示网关账号名（上次合并已带入，本次仅脚本与夹具更新）。
- **自动合并、需按第二版规则核对的前端文件**：`api.ts`、`RuntimeEnvironments.vue`、`runtime/AccountNodeMigration.vue`、`runtime/AccountNodeSelector.vue`、`runtime/environmentLabels.ts`、`runtime/nodeApi.ts`、`runtime/runtimeApi.ts`、`RequestSessionId.vue`（新增）。
- **漏页排查结果**：主线 `apps/web/src` 里本分支没有的文件，除已决定删除的旧页 / 旧样式（`SystemUpdates.vue`、`request-design.css`、`proxy-design.css`、`settings-design.css`、旧 `ui/label|separator|tabs`、`controls.css`）外，只有新增的 `RequestSessionId.vue`。所有路由页（账号、代理、请求、会话策略、令牌、主题、设置、运行环境、节点、任务）在本分支都已是第二版结构。主线界面文案覆盖对比中，本次之前就缺的只有改版时有意替换的旧文案（例如旧系统更新页的横幅句，对应功能都在弹窗中）。
- **非前端交叉**：本分支改过 `services/gateway/src/handler/router.rs` 等网关文件，主线也改了 `router.rs`，已自动合并，需编译验证。
- **验证脚本**：主线改过的 UI 脚本中，`verify_cluster_ui.py`、`verify_management_ui.py` 已自动合并为第二版选择器；`verify_agy_environment_ui.py` 断言卡片 `h2`，第二版实体卡标题为 `h3`，需要适配。

## Requirements

- **R1 主线功能完整保留**：上面列出的主线界面行为全部可用。字段、接口路径、默认值、轮询与请求序号保护、错误文案与主线一致。后端与非前端文件保持主线逻辑，同时保留本分支的改动。
- **R2 第二版呈现**：
  - 移植的界面使用第二版组件与 token：不写死颜色和圆角，不用 shadcn 色名工具类，不用 lucide；
  - 遵守 `ui-guidelines.md` 与 `theme.test.mjs` 的静态规则；浅色、深色都可读；
  - 新状态沿用所在区域现有的视觉语言（账号表单的 `Checkbox`、内核面板的 `ChoiceSelect` + 按钮行、请求表的 `fui-table-mono` / `request-copy` / `request-missing`、节点实体卡）。
- **R3 冲突解决不回退本分支改版**：第二版结构、深色模式与主题保持原样。`request-design.css` 保持删除，主线新增的 `.request-session-source` 规则以 token 写入 `request-records.css`。
- **R4 补齐遗漏**：解决冲突后重新做一次「主线文案 / 标识符覆盖」核对，主线这次新增的界面文案在合并结果里全部能找到；发现遗漏就在第二版对应位置补上。
- **R5 验证脚本与规范同步**：
  - 冲突脚本合并两边断言，选择器用第二版，业务断言不放宽；
  - 主线修改过的 UI 脚本若按旧结构断言，改用第二版选择器；
  - `ui-guidelines.md` 主线自带改动原样保留，补充第二版位置说明（工具续轮模式、派生 Session ID 标记、反重力归属与节点计数）。
- **R6 合并提交**：解决完所有冲突并通过验证后，由 Trellis Push 计划确认，完成合并提交并推送 `feat/console-ui-revamp`。

## Acceptance Criteria

- [ ] `git ls-files -u` 为空，没有冲突标记；`request-design.css`、`SystemUpdates.vue` 保持删除；主线其余改动全部带入。
- [ ] 前端 `npm ci`、构建与全部前端单测通过（含 `theme.test.mjs` 静态规则）；原生脚本 `node --check` 通过；网关 `cargo check --tests` 通过。
- [ ] 主线这次新增的界面文案覆盖核对无遗漏（只允许有意替换的旧文案）。
- [ ] 以下移植行为由验证脚本覆盖并通过：
  - 账号：试验开关的读写与载荷、Claude Code 账号不显示该开关（`verify_agy_accounts_ui.py`）；反重力账号归属显示与读取失败（`verify_execution_node_visibility.py`）；
  - 节点：每台节点直接显示后端归属数、反重力账号迁移与取消（`verify_cluster_ui.py`）；
  - 请求记录：派生 Session ID 标记与复制（`verify_management_ui.py`）；
  - 运行环境：账号名、等待原因、准备失败、热进程就绪、内核与工具续轮模式控件（`verify_agy_environment_ui.py`）。
- [ ] 请求链路新字段（控制 HTTP、响应读取中断、原生流状态、工具续轮）与性能页启动来源用合成夹具定向检查，浅色、深色截图与第二版视觉一致。
- [ ] 全量 UI 回归只剩基线已登记的失败（`verify_forwarding`、`verify_management_polish`、`verify_agy_request_records`），原因不变。
- [ ] 主线未改动的页面在浅色、深色下与合并前逐像素一致；差异只出现在本次移植区域并逐项登记。
- [ ] 规范同步；Push 计划确认后完成合并提交，`feat/console-ui-revamp` 包含主线 `faa53196`。

## Out of Scope

- 把 `feat/console-ui-revamp` 正式合回 `flower2api`、发版、部署与线上升级：它们有对外影响，完成本任务后另行确认再做。
- 修改主线功能行为或修复主线缺陷：只移植，发现问题记为风险。
- 为新状态另出设计稿。
