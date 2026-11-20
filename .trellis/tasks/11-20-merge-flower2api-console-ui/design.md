# 技术设计 — 合并 flower2api 并移植到第二版控制台

## 1. 合并方式

- 继续当前 `git merge --no-commit` 现场（`MERGE_HEAD` = `9c80a39a`）。解决冲突时以本分支的第二版文件为底，按「分叉点 → 主线」的差异逐条重放主线行为，不整块采用主线版本。
- 没有冲突、已自动合并的主线改动保留原样；违反第二版规则的地方在原文件里改为 token 写法。
- 解决完的文件按 Git 合并惯例标记为已解决，但不提交。合并提交与推送由 Push 计划确认后执行（`trellis-push` 只完成已就绪的合并）。
- 工作区原有的旧任务归档与主线 `f7cb9e9c` 相同，合并后自然一致，不另行处理。

## 2. 已解决

- `deploy/flower2api/system_updater.py`：
  - `STEP_LIMIT` 与 `FAST_CUTOVER_SETTLE_SECONDS` 都保留；
  - `_public_operation` 的白名单为并集：本分支的 `steps`，加上主线的 `control_health`、`fast_transition`、`admission_blocked_at`、`admission_reopened_at`；
  - 主线的账号后台更新方法照单保留；
  - 步骤记录在 `_record` 落盘处统一追加，主线新阶段同样适用。
- `deploy/flower2api/SYSTEM-UPDATES.md`：主线新增的「候选验收超时探测」「旧版兼容安装节点回执」两段保留，对账段用本分支的弹窗措辞（「恢复操作」）。

## 3. 系统更新弹窗（`SystemUpdates.vue` 保持删除，功能并入 `SystemUpdateDialog.vue`）

**状态与动作**
- `Action` 增加 `'prepare'`，`Frozen` 增加 `restart: boolean`。
- 新增三个函数，与主线同名同义：
  - `preparedFor(release)`：回执的 `target_release` 与 `manifest_sha256` 都匹配才算；
  - `updateAction(release)`：`staged_updates` 且无匹配回执时为 `'prepare'`，否则为 `'install'`；
  - `updateButton(release, legacy)`：依次判断「先检查更新 / 待验证兼容 / 下载更新 / 立即重启 / 安装更新 / legacy」。
- `freeze` 安装已下载候选时，请求体带 `prepared_operation_id`，`restart = prepared.fast_transition === true`。
- `submit`：
  - `prepare` 与 `restart` 不校验、不写入等待期限，保持冻结时的默认值，与主线一致；
  - 成功提示为 `'已开始下载更新'`（prepare）或 `'操作已登记'`（其它，沿主线新文案）；
  - 重复点击同一冻结的 prepare 时整份重发（沿用现有的不确定重试语义）。

**概览视图**
- 主按钮（底栏 `installLatest`）文字取 `updateButton(latest, '安装更新')`，动作取 `updateAction(latest)`。
- 「安装方式」区 `.su-plan` 按动作切换文案：
  - **下载**：图标 Download，标题「先在后台下载并校验」，说明「平台继续接单；下载完成后再选择重启时间。刷新页面或更新器重启后仍可继续。」，不显示等待上限。
  - **立即重启**（`prepared.fast_transition`）：图标 RotateCcw，标题「重启并切换版本」，说明「重启会断开正在执行的推理，控制服务就绪后可重新请求。」，不显示等待上限。
  - **兼容安装**：保留现有文案与「在途等待上限（分钟）」。
- 状态标签：
  - 概览 `summary` 有匹配回执时为「待重启」或「已下载更新」（success）。
  - 维护中弹窗总在进度视图，所以「正在后台准备」（preparing，info）与「平台已恢复接单」（cleaning 且已有 `admission_reopened_at`，success）放在进度视图的状态标签 `progressPill`，其余维护中仍为「更新中」。

**进度视图**
- **阶段文案**：`UPDATE_PHASE_LABELS.prepared` 改为「待重启」。新增 `phaseText(operation, phase)`：
  - draining 且 `fast_transition` → 「正在关闭推理连接」；
  - prepared 且非快速 → 「已下载更新」。
  - 状态标签、步骤行和结局提示都用它。
- **维护提示**：现有固定的「维护期间新工作暂缓…」改为主线的 `maintenanceMessage`，有 5 种情况：
  - preparing；
  - prepared；
  - 已恢复接单；
  - draining（区分快速 / 普通）；
  - 其它。
  - 维护中，或 `admission_reopened_at` 已有时显示。
- **远程节点**：`cluster_nodes.phase === 'background'` 时，节点列表换成一行说明（「远程节点将在中央切换后独立更新」/「远程节点独立更新」）加 `router-link` 到节点页「查看节点进度」。否则沿用现有节点列表。

**账号后台更新**（新增 `.su-rollout` 分区）
- 在概览与进度两个主视图的末尾都显示，条件是 `status.account_rollout?.accounts.length`。
- 分区头为「账号后台更新」，右侧显示「<版本> 已生效」。
- 列表每行：名称、错误说明、状态徽标，以及「重试」按钮（outline sm）。
  - 状态徽标：queued / updating 为 info，updated 为 success，stopped 为 neutral，waiting / needs_check 为 warning。
  - 重试按钮在 `retryable !== false` 且状态为 waiting / needs_check 时显示；维护中或写入中禁用。
- 重试调用 `api.systemUpdateRetryAccount(operation_id, environment_id, revision)`，失败用 toast 提示。
- 轮询：有 queued / updating 时 2 秒一次。

**操作详情视图**
- 在现有字段前加「新版本健康检查」「恢复原版本健康检查」小节，每个服务（网关 / 调度器）一行，内容为状态、HTTP 码、耗时秒数、第 N 次。
- 加「暂停接单 / 恢复接单」时间。

**版本记录视图**：可用版本的按钮文字取 `updateButton(release, '安装更新')`，按 `updateAction` 分两路：
- `prepare`：直接提交；
- `install`：走现有的二次确认框。
  - 确认框在 `restart` 时标题改为「重启并切换版本」，正文改为重启说明，不显示等待上限，按钮为「立即重启」。

**样式**：新增 `.su-rollout`、`.su-health` 等规则只放在 `system-update.css`，只取 token，并加入 `theme.test.mjs` 已覆盖的样式文件。

**钩子**：`[data-update-plan=prepare|restart|install]`、`[data-update-maintenance]`、`[data-update-nodes=background]`、`[data-rollout-state]`、`[data-update-health=candidate|restore]`，供脚本定位。

## 4. 其余冲突文件

- **`Accounts.vue`**（以第二版为底）：
  - 表单默认值、编辑回填、`agyFormKeys` 与保存载荷加入 `agy_gif_frames_enabled`、`agy_disable_safety_filtering`；
  - 反重力配置分区新增两项，控件与现有 `agy_system_prompt_homoglyph_enabled` 相同；
  - `refreshingUsage` 改为 `Set`，新增 `usageRefreshErrors`、`refreshEntryUsage`，首次 `load` 后逐个刷新可用的反重力账号；
  - `AgyAccountUsage` 传入 `refreshing` 与 `refresh-error`；
  - 反重力卡片的调度入口统一为「调度优先级 → 调度详情」，工作区页签不再排除调度，`SchedulingDetails` 传入 `:antigravity`；
  - `testAlive` 改名为 `accountAlive`。
- **`SchedulingDetails.vue`**（第二版为底）：重放 `antigravity` 属性逻辑，即额度分、会话列表、额度提示的条件，以及说明文案。颜色改用页面类或 token，不用 `text-amber-*`、`text-muted-foreground`。
- **`RequestDiagnostics.vue`**（第二版为底）：
  - 页头操作区加入拒绝正文范围的 `ChoiceSelect`（仅 debug 时显示），保存函数为 `saveDiagnostics`；
  - 拒绝原因文案表、`input_rejection_reason`、`RESOURCE_EXHAUSTED`、`saved` 采集状态按主线重放；
  - `.request-diagnostics-settings` 写进 `request-records.css`（token 间距）；
  - `request-design.css` 保持删除。
- **`NativeStageDetails.vue`**：
  - 重放 `ingressOnly`、`rawStages`、`tlsWire`、`agyWire`、`label` 分支和头部阶段列；
  - 新增的「实际出站证据」区块使用 `.request-wire-note`、`.request-wire-reason`。
- **`RuntimeEnvironments.vue`**（第二版 EntityCard 为底）：
  - 重放 `environmentName`、`agyIdleWorkers`、`kernelLabel`、`preparationLabel` 与概览统计「空闲热进程」；
  - 主线对卡片结构的其它改动按第二版卡片的对应位置移植。
- **`native-environment.css`**：
  - 以第二版 token 版本为底；
  - 重放 `.environment-feature-row:has(> button:only-child)` 与 `> button` 选择器收窄，颜色取 token。
- **`verify_execution_node_visibility.py`**：保留第二版选择器（`.fui-entity-card-head`），期望值采用主线的本机执行节点文案。

## 4.1 实施中的补充

- **`EnvironmentKernel.vue`**（自动合并）：主线新增的反重力内核候选切换用原生 `<select>`。按第二版规范改为 `ChoiceSelect`「请求内核」（`.environment-kernel-select`），选项、取值与提交载荷不变。
- **设置项计数**：主线新增 `request_diagnostics_rejected_body`，`settingsSchema` 变为 58 项，页头为「60 项配置」。按规范同步 `verify_remaining_pages.py` 的计数断言。
- **主线未更新的旧脚本**：以下脚本在主线上同样失败，按主线新行为同步，业务断言不放宽：
  - `verify_agy_accounts_ui.py`：反重力卡片为「调度优先级」，工作区有「调度」页签；
  - `verify_environment_ui.py` 的夹具：补 `GET /environments/<id>/agy-kernel` 只读目录，供 `verify_agy_environment_ui.py` 等使用。
- **`verify_system_update_browser.py`**：主线新增的三个用例按弹窗结构重写，并补「已下载的兼容安装」与「版本记录下载 / 重启确认框」两个用例；夹具中下载操作只记录 `preparing` 一步。

## 5. 自动合并文件的核对

- `theme.test.mjs` 静态规则覆盖 `apps/web/src` 全部样式与组件；违规项在原文件改为 token 写法。
- 主线新增或修改的模板文案、交互不动。
- 视觉回归：Vue 主要页面与原生 36 个状态的浅色、深色截图与合并前对比。差异只允许出现在主线功能带来的区域，并逐项登记。

## 6. 规范

- `ui-guidelines.md`：
  - 「系统更新弹窗」节补充两步动作、按钮矩阵、账号后台更新、健康探测、远程节点后台入口；
  - 账号、请求记录、运行环境相关节补充移植后的类名与条件。
- 主线已改的 3 份规范（`account-runtime-v3.md`、`platform-online-update.md`、`logging-guidelines.md`）原样保留。其中涉及「页面」的措辞在不改语义的前提下对齐「弹窗」。

## 7. 回滚

合并提交之前可用 `git merge --abort` 回到 `b0858810`，再从 `/tmp/console-ui-pre-merge-backup` 恢复旧任务的归档现场。推送后需要撤销时，对合并提交执行 `git revert -m 1`。
