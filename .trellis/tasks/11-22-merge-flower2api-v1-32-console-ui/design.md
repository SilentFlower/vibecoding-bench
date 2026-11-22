# 技术设计 — 再次合并 flower2api（v1.32.1）

## 1. 总体做法

- 继续当前停在提交前的合并现场（HEAD `70432a22`，MERGE_HEAD `faa53196`）。
- 冲突文件以第二版（HEAD）为底，按「`9c80a39a` → `faa53196`」的主线差异逐条重放，不整块采用主线旧结构。
- 自动合并文件只做第二版规则核对；后端与非前端文件保持自动合并结果，用编译与单测兜底。
- 回滚点：合并提交前随时 `git merge --abort`；本任务目录是未跟踪文件，不受影响。

## 2. 冲突文件解决

### 2.1 `Accounts.vue`

- 取 HEAD 块（第二版表单：`Checkbox`、`account-form-actions`、`ChevronRight`、`#account-editor-form`）。
- 在反重力配置区「系统提示词同形体转换」之后插入：
  `<Checkbox v-model="form.agy_system_prompt_as_user_reminder" class="account-check"><strong>系统提示词移入用户消息（试验）</strong><small>用于 Messages。与同形体转换同时开启时，先转换原系统提示词，再移入用户消息。</small></Checkbox>`
- 脚本部分（默认值、回填、`agyFormKeys`、载荷、`agyNodes` / `agyAssignments` 归属读取、`nodeStatus` 文案）已自动合并，保持主线逻辑。

### 2.2 `Nodes.vue`

- 主线语义：后端 `account_count` 已包含反重力账号，前端不再累加。
- 删除 HEAD 的 `accountCount()`，卡片「归属账号」直接显示 `node.account_count`；`totalAccounts` 采用主线写法（纯数字求和）。
- 保留 HEAD 的 `attention` / `attentionCaption` / `remoteCaption` / `remoteNodes` 与实体卡模板。
- `agyAccounts` 继续用于节点选择器账号选项与读取失败提示，不变。

### 2.3 `RequestDiagnostics.vue`

冲突块跨度大，直接以 `git show HEAD:` 版本为底，手工重放主线 5 处改动：

1. 导入 `agyToolContinuationLabels`（`./runtime/runtimeApi`）与 `RequestSessionId`。
2. 列表「原始 Session ID」单元格换成 `<RequestSessionId :request="row" @copy="copy" />`。
3. 详情概览定义列表换成 `<RequestSessionId :request="selected" full @copy="copy" />`。
4. 链路卡片「原生控制收口」追加控制 HTTP 状态与 `unexpected_eof` →「响应读取中断」；新增「原生流状态」「工具续轮」两组定义（文案同主线）。
5. 性能页 `request-runtime`：标题按 `warm_hit` / `start_source` 区分四种，PID 行附启动方式，「进程启动 / 进程恢复」标签切换。保留 HEAD 的 `request-runtime-head` 类。

### 2.4 `RequestSessionId.vue`（主线新增）与样式

- 改成第二版表格写法：`code` 加 `fui-table-mono`（仅列表态），复制按钮加 `request-copy`，列表缺省用 `<span class="request-missing">未提供</span>`，详情缺省 `<span>未提供</span>`，与 HEAD 原内联写法一致。
- 「网关派生」用 `<small class="request-session-source">`，规则写入 `request-records.css`：`flex: none; color: var(--ui-color-text-3); font-size: var(--ui-font-size-sm);`。列表列较窄，有该标记时 `.request-session` 改为两列网格（`minmax(0, 1fr) auto`），标记放在 ID 下一行，ID 与复制按钮保留首行；详情态保持同行。
- 复制按钮 aria-label 保持主线「复制原始 / 派生 Session ID …」，图标尺寸跟随 HEAD 的 12。
- `request-design.css`：`git rm`，保持删除。

### 2.5 `runtime/EnvironmentKernel.vue`

- 导入取并集：`ChoiceSelect, type ChoiceOption` + `agyToolContinuationLabels`、`AgyToolContinuationPolicy`。
- 保留 HEAD 的 `kernelOptions`，并入主线续轮策略状态、`loadToolPolicy`、`saveToolPolicy`、`watch`、`applyKernel` 后刷新策略。
- 模板：沿用主线的续轮控件行，`ChoiceSelect` 与 HEAD 内核选择保持一致——加 `class="environment-kernel-select"`，不传 `portal-target`（第二版环境详情是 reka `Dialog`，同面板的内核选择已验证无需 portal），同时去掉只为 portal 存在的 `toolPolicyRoot`。

### 2.6 验证脚本

- `verify_agy_accounts_ui.py`：两条断言都保留（`调度优先级` 与 `原生运行时 Antigravity`，HEAD 卡片两者同时存在）。
- `verify_execution_node_visibility.py`：采用主线期望文案（`已读取 AGY 所属节点的实际环境`、`反重力执行节点`），选择器保留 HEAD 的 `.fui-entity-card-head`。

## 3. 自动合并文件核对

- `AccountNodeSelector.vue`、`AccountNodeMigration.vue`：只有脚本与文案变化，模板结构沿用已有第二版样式，无需改动。
- `RuntimeEnvironments.vue`：`preparationLabel` 改写为主线多行版本，第二版卡片已通过 `stateLabel` 呈现，无模板冲突。
- `environmentLabels.ts`、`nodeApi.ts`、`runtimeApi.ts`、`api.ts`：类型与接口新增，直接保留。
- `verify_agy_environment_ui.py`：卡片标题 `get_by_role('heading', level=2)` 改为 `level=3`（第二版 `EntityCard` 标题是 `h3`），其余断言保持；若其他断言也依赖旧结构，按第二版选择器调整，业务断言不放宽。
- `verify_ui_shell.py` 的 `ShellFixture`（主题、深色模式脚本复用）补登记 `/runtime/api/agy-accounts/nodes`，为夹具中的反重力账号返回本机归属：账号页改读该接口后，未登记会产生 404 控制台错误。
- 静态规则：`theme.test.mjs` 兜底写死颜色、旧工具类与 lucide。

## 4. 漏页与遗漏核对

- 解决冲突后运行 `/tmp/merge-audit/copy_coverage.py`，改为只看「`9c80a39a` → `faa53196` 新增的文案」是否全部出现在合并结果中。
- 同步核对主线新增的标识符（`derived_session_id`、`start_source`、`tool_continuation_*`、`observed_control_http_status`、`native_receive_ended`、`preparation_reason`、`agy_system_prompt_as_user_reminder`、`agyAssignments`、`migration_ready`）在模板或脚本中有使用点。

## 5. 规范

- `ui-guidelines.md` 主线两处改动已自动合并。追加第二版位置说明：
  - 运行环境 · 反重力内核面板：工具续轮模式位于请求内核行下方，`ChoiceSelect` + 「保存模式」，不支持时只允许领取续轮；
  - 请求记录：派生 Session ID 的「网关派生」标记样式与列表 / 详情的类名约定；
  - 节点页：归属账号直接使用后端 `account_count`，前端不再累加反重力账号。

## 6. 风险

- **漏移植**：以主线差异为清单逐条重放，并用文案 / 标识符覆盖核对兜底。
- **网关自动合并**：本分支与主线都改了 `router.rs`，以 `cargo check --tests` 与相关单测验证。
- **ChoiceSelect 弹层**：去掉主线的 `portal-target` 后，以 `verify_agy_environment_ui.py` 在弹窗内实际选择验证。
