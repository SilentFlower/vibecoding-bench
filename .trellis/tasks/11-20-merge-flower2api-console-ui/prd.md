# 合并 flower2api 主线并把新功能移植到第二版控制台

## Goal

把 `flower2api` 主线（`origin/flower2api` @ `9c80a39a`，独有 34 个提交，含 v1.21.0–v1.26.1）合并进 `feat/console-ui-revamp`。主线的全部新功能都要保留，同时以第二版控制台的结构、组件和 token 呈现。主线功能与第二版改版都不能回退。

## Background

- **分叉情况**：分叉点 `3b29c19b`。本分支独有 24 个提交（控制台 UI 改版 7 个子任务加父任务复核），主线独有 34 个提交（AGY、系统更新、集群、发行等）。
- **合并现状**：
  - 已执行 `git merge --no-ff --no-commit origin/flower2api`，现场停在 `MERGE_HEAD`，有 11 个冲突文件，其余文件已自动合并。
  - `system_updater.py`、`SYSTEM-UPDATES.md` 两处已按并集合好。
- **旧任务归档**：工作区原有的 8 个旧任务归档移动（58 删 + 58 增），与主线 `f7cb9e9c chore(task): gc closed tasks` 逐字节相同。合并前已撤掉本地副本，由合并带入同一结果；备份在 `/tmp/console-ui-pre-merge-backup`。
- **冲突来源**：本分支把这些页面重写成第二版结构（PageHeader、EntityCard、ModalDialog、token 样式），主线在旧结构上叠加了功能。
  - **系统更新**（`20ecf733`、`c48a66bf`、`b77de2af`）：
    - 安装改为两步：「下载更新」，下载校验完成后「立即重启 / 安装更新」；
    - 待重启回执（`prepared_candidate`）；
    - 快速切换文案（`fast_transition`）；
    - 后台准备期间平台继续接单；
    - 「账号后台更新」列表与单项重试（`account_rollout`、`retry-account`）；
    - 远程节点后台独立更新；
    - 操作详情里的网关 / 调度器健康探测（`control_health`）与暂停 / 恢复接单时间。
    - 旧页面 `SystemUpdates.vue` 在本分支已被 `SystemUpdateDialog.vue` 取代（modify/delete 冲突）。
  - **账号页**（`aa2ad36e`、`0f5f7712`、`fa51c7ca`、`409298b7`）：
    - 进入列表时逐个刷新反重力账号额度，失败只在卡片提示；
    - 用量刷新可并发；
    - 反重力账号也有调度入口、调度页签与调度详情（`antigravity` 口径）；
    - 新增「GIF 抽帧兼容」「使用 AGY 原生安全开关」两项配置。
  - **调度详情**：反重力口径，不显示额度分、会话列表与额度提示，文案改为优先级说明。
  - **请求记录**：
    - 拒绝正文采集范围设置（debug 时可选限长预览 / 完整正文）；
    - 新的拒绝原因文案；
    - `input_rejection_reason` 提示、`RESOURCE_EXHAUSTED` 说明、采集状态 `saved`；
    - 原 `request-design.css` 新增 `.request-diagnostics-settings`（本分支已删该文件）。
  - **请求证据**（`NativeStageDetails.vue`）：AGY 实际出站证据（`agy_http_transport` / `agy_native_tls`），只有入口阶段的快照，头部处理的阶段列。
  - **运行环境**：
    - 卡片名称取网关账号名；
    - 反重力的空闲热进程、正在预热状态与内核摘要；
    - 本机执行节点显示（`fe2296f9`）；
    - `.environment-feature-row` 单按钮布局。
- **自动合并进来、仍需按第二版规则核对的前端文件**：`EnvironmentKernel.vue`（单环境切换请求内核）、`AgyAccountUsage.vue`、`Settings.vue` 与 `settingsSchema.ts`、`Nodes.vue`、`AccountNodeSelector.vue`、`EnvironmentResources.vue`、`environmentLabels.ts`、`runtimeApi.ts`、`api.ts`。
- **验证脚本**：主线改了 `verify_system_update_browser.py`、`verify_execution_node_visibility.py`、`verify_cluster_ui.py`、`verify_system_update.py` 等，可能仍按旧页面结构断言。

## Requirements

- **R1 主线功能完整保留**：上面列出的主线行为全部可用。字段、接口、默认值、轮询节奏、错误文案与主线一致。后端（`system_updater.py` 等）保持主线逻辑，并保留本分支的更新步骤记录（`steps`）。
- **R2 第二版呈现**：
  - 移植的界面使用第二版组件与 token：不写死颜色和圆角，不用 shadcn 色名工具类，不用 lucide；
  - 遵守 `ui-guidelines.md` 与 `theme.test.mjs` 的静态规则；
  - 浅色、深色都可读。
  - 没有设计稿的新状态沿用弹窗、实体卡与数据表的现有视觉语言。
- **R3 系统更新弹窗承接两步流程**：
  - **主按钮**：按目标版本与下载回执切换「先检查更新 / 待验证兼容 / 下载更新 / 立即重启 / 安装更新」。
  - **下载**：直接提交，平台继续接单。
  - **立即重启**：说明会断开正在执行的推理，不再询问在途等待上限。
  - **兼容安装**：保留在途等待上限（1–120 分钟）。
  - **状态与进度**：概览状态、进度视图提示与步骤名称按主线文案呈现（后台准备、待重启 / 已下载更新、正在关闭推理连接、平台已恢复接单）。
  - **账号后台更新**：在弹窗主视图中显示，可单项重试；进行中按 2 秒轮询。
  - **远程节点**：后台更新时显示说明与「查看节点进度」入口。
  - **操作详情**：显示健康检查探测与接单暂停 / 恢复时间。
  - **版本记录**：其中的安装 / 回退同样按下载回执选择动作。
  - 不恢复整页 `SystemUpdates.vue`。
- **R4 冲突解决不回退本分支改版**：第二版结构、旧层删除合同、深色模式与主题保持原样。`request-design.css`、`SystemUpdates.vue` 保持删除，主线对它们的改动移植到现有文件。
- **R5 验证脚本与规范同步**：
  - 主线修改过的验证脚本改用第二版选择器，业务断言不放宽；
  - `ui-guidelines.md` 的系统更新弹窗、账号、请求记录、运行环境各节补充移植后的合同；
  - 主线自带的规范改动原样保留。
- **R6 合并提交**：解决完所有冲突并通过验证后，由 Trellis Push 计划确认，完成合并提交并推送 `feat/console-ui-revamp`。本任务不合入主线、不发版。

## Acceptance Criteria

- [ ] `git ls-files -u` 为空，没有冲突标记；`SystemUpdates.vue`、`request-design.css` 保持删除，其余主线文件全部带入。
- [ ] 前端构建与全部前端单测通过（含 `theme.test.mjs` 静态规则）；原生脚本 `node --check` 通过。
- [ ] 主线触及系统更新的后端测试通过（`test_system_updater.py` 等），步骤记录字段与主线新字段同时出现在公开操作中。
- [ ] 系统更新弹窗用合成夹具验证通过以下场景：
  - 下载更新、已下载后的立即重启与兼容安装三条路径，提交载荷与主线一致（`prepare` / `install` + `prepared_operation_id` / 等待期限）；
  - 账号后台更新的显示与单项重试；
  - 健康探测详情；
  - 远程节点后台更新入口。
- [ ] 以下 4 项移植后的行为由验证脚本或定向浏览器检查覆盖：
  - 账号页：进入列表自动刷新反重力额度（失败只在卡片提示）、反重力调度入口与调度详情口径、两项新配置的读写；
  - 请求记录：拒绝正文范围设置与新的拒绝说明；
  - 请求证据：AGY 实际出站证据；
  - 运行环境：账号名、空闲热进程、预热状态、本机执行节点。
- [ ] 全量 UI 回归（深色任务以来的 69 个脚本加主线修改过的 UI 脚本）只剩基线已登记的失败，原因不变；主线修改过的脚本全部通过或给出已登记的环境原因。
- [ ] 浅色、深色下，移植区域截图与第二版视觉语言一致；主线未改动的页面逐像素与合并前一致。
- [ ] 规范同步；合并提交只含本次合并结果，推送后 `feat/console-ui-revamp` 包含主线 `9c80a39a`。

## Out of Scope

- 把 `feat/console-ui-revamp` 合入 `flower2api`、发版与部署。
- 主线功能本身的改动或缺陷修复（只移植，不改行为）；发现问题记录为风险。
- 为新状态另出设计稿。
