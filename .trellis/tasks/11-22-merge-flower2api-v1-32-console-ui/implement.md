# 执行计划 — 再次合并 flower2api（v1.32.1）

证据目录 `.deploy/merge-flower2api-v132/`（git 忽略）。复用上次的工具 `.deploy/merge-flower2api/`（`run_regression.py`、`capture_vue.py`、`capture_states.py`、`pixel_diff.py` 等）。每步完成后勾选并写实际结果。

## 步骤

- [x] **0. 基线**
  - 记录合并现场：HEAD、MERGE_HEAD、冲突清单、自动合并的前端与脚本清单 → `merge-state.txt`。
  - 从 `70432a22` 导出合并前构建，截取 Vue 主要页面与原生状态的浅色、深色基线（`before-*`）。
  - 实际结果：`merge-state.txt` 记录 HEAD `70432a22`、MERGE_HEAD `faa53196`、BASE `9c80a39a`、7 个冲突。基线从 `70432a22` 导出到 `/tmp/merge132-pre-root` 构建，`before-vue-{light,dark}` 各 20 张、`before-native-{light,dark}` 各 72 张（36 个状态，1 个不可达，同上次）。
- [x] **1. 冲突解决**（design §2）
  - `Accounts.vue`：取 HEAD 块，插入试验开关 `Checkbox`。
  - `Nodes.vue`：删 `accountCount`，采用主线 `totalAccounts`，保留 HEAD 汇总与实体卡。
  - `RequestDiagnostics.vue`：以 HEAD 版本为底重放主线 5 处改动。
  - `RequestSessionId.vue` 改第二版类名；`.request-session-source` 写入 `request-records.css`；`git rm apps/web/src/request-design.css`。
  - `EnvironmentKernel.vue`：导入并集、保留 `kernelOptions`、并入续轮策略与控件（无 `portal-target`）。
  - 两个验证脚本按 design §2.6 合并。
  - 实际结果（每个文件的重放项）：
    - `Accounts.vue`：冲突块取 HEAD，反重力配置区在同形体转换之后加试验开关 `Checkbox`。脚本部分（`agyNodes` / `agyAssignments` 归属读取、`nodeStatus` 五种文案、表单默认值 4 处、回填、`agyFormKeys`、载荷）为自动合并，与主线差异逐条一致。
    - `Nodes.vue`：删 `accountCount()`，卡片「归属账号」取 `node.account_count`，`totalAccounts` 纯数字求和并注明原因；HEAD 汇总、`attention` 与实体卡保持。
    - `RequestDiagnostics.vue`：导入 `agyToolContinuationLabels`、`RequestSessionId`（自动合并）；列表与详情 Session ID 换组件；链路追加控制 HTTP、`unexpected_eof`、原生流状态、工具续轮；性能页四种启动标题、PID 后启动方式、「进程恢复 / 进程启动」切换。
    - `RequestSessionId.vue`：列表 `fui-table-mono` / `request-copy` / `request-missing`，详情 `.request-session-full`；补组件注释。
    - `request-records.css`：`.request-session-source` 取 token。浏览器截图发现窄列里标记会把 ID 挤到不可见，改为列表态有标记时两列网格、标记在 ID 下一行（第二版「主值下一行」规则），详情同行。
    - `EnvironmentKernel.vue`：导入并集，`kernelOptions` 与续轮策略状态、读写、`watch`、切换内核后刷新并存；控件去掉 `toolPolicyRoot` / `portal-target`，加 `.environment-kernel-select`，`toolOptions` 标注 `ChoiceOption[]`。
    - 验证脚本：`verify_agy_accounts_ui.py` 两条断言并存；`verify_execution_node_visibility.py` 主线文案 + `.fui-entity-card-head`。
- [x] **2. 自动合并核对与脚本适配**（design §3）
  - 静态规则、`vue-tsc` 构建；`verify_agy_environment_ui.py` 适配第二版标题层级等选择器。
  - 实际结果：构建与 33 项单测（含静态规则）通过。`verify_agy_environment_ui.py` 卡片标题改 `level=3`。全量回归暴露本分支自有夹具 `verify_ui_shell.ShellFixture` 未登记主线新接口 `/runtime/api/agy-accounts/nodes`（账号页有反重力账号时请求，404 进控制台错误，导致 `verify_theme_settings`、`verify_dark_mode` 失败），补登记为本机归属后两者通过。其余自动合并文件无需改动。
- [x] **3. 漏页与遗漏核对**（design §4）
  - 跑主线新增文案 / 标识符覆盖，结果写入 `coverage.txt`；有遗漏就补到第二版对应位置。
  - 实际结果：主线 `9c80a39a..faa53196` 新增的文案全部在合并结果中；标识符只缺 `toolPolicyRoot`（design §2.5 有意移除）。全量文案缺口与合并前（对 `9c80a39a`）完全相同，均为改版时有意替换的旧文案，没有新的漏页。
- [x] **4. 规范**（design §5）：`ui-guidelines.md` 追加三处第二版位置说明。
  - 实际结果：请求记录 Session ID（`RequestSessionId` 类名、派生标记样式与窄列布局）、运行环境（工具续轮模式位置与提交、AGY 准备原因与空闲数口径）、节点页（归属账号直接取后端 `account_count`，删去「读取失败为 —」）。
- [x] **5. 全量验证与对照**
  - 运行下方全部命令。
  - 定向检查 `check_ported.py`（浅色、深色）：试验开关、反重力归属、节点计数、派生 Session ID、链路新字段、性能启动来源、准备原因、工具续轮模式在弹窗内选择保存。
  - 浅色、深色改前改后像素比对：差异只出现在移植区域，逐项登记。
  - 实际结果：
    - 无冲突残留；`node --check` 4 个原生脚本通过；`npm ci`、构建、33 项单测通过；网关 `cargo check --tests` 通过；`test_system_*` 159 项通过（1 项跳过）。
    - 主线改过的 5 个 UI 脚本（账号、执行节点、集群、管理页、AGY 环境）全部通过。
    - 全量回归：主集合 43 个剩 `verify_forwarding`（缺 `--manifest`）、`verify_management_polish`（首屏两次检查更新）；扩展集合 26 个剩 `verify_agy_request_records`（缺 `--image/--baseline`），均为基线已登记、原因不变。首轮并行时 `verify_interaction_parity` 因其他脚本重建 `dist` 偶发失败，串行复跑通过。
    - 定向检查 `check_ported.py` 浅色、深色通过（截图在 `ported/`）：试验开关位置与组件、派生 Session ID（token 色、类名、ID 可读宽度与复制按钮同行）、链路新字段、CRIU 恢复与命中热进程两种性能展示、准备失败原因与提醒色、续轮模式与请求内核同宽、弹窗内选择历史续轮并按代次和版本提交、不支持时禁用历史续轮。
    - 像素对照：原生 144 张全部一致；Vue 40 张只有节点页 4 张不同，为本机节点「归属账号」由前端累加的 2 变为后端计数 1（主线口径）。深色主题页一次截图因预览画板里检查更新返回时机不同出现版本角标差异，两次重截均与基线一致。

- [x] **Check-All 修复**：CHK-001 反重力准备块颜色仍按原始 `state` 判定，主线细分后 `state=ready` 时的「等待准备 / 状态待核对 / 正在预热 / 等待工具结果」都显示成功色。
  - 修复：`RuntimeEnvironments.vue` 的 `preparationTone` 反重力分支按 `preparationLabel` 的判定顺序着色，只有空闲热进程大于 0 的「热进程就绪」为 success；`ui-guidelines.md` 预热块合同同步。
  - 测试：`check_ported.py` 增加五种状态的 `data-tone` 断言（四种中性、热进程就绪为成功），浅色、深色通过。
  - 定向回归：`verify_agy_environment_ui`、`verify_native_environments`、`verify_environment_workspace_design`、`verify_native_pages_design`、`verify_environment_cpu_summary`、`verify_native_environment_edges`、`verify_dark_mode` 串行通过；构建与 33 项单测通过；重截 184 张截图，差异仍只有节点页 4 张。

## 验证命令

```bash
git diff --name-only --diff-filter=U        # 为空
grep -rn '^<<<<<<<\|^>>>>>>>' apps deploy services .trellis/spec || true   # 无输出
node --check apps/legacy-web/app.js && node --check apps/legacy-web/projects.js && node --check apps/legacy-web/environments.js && node --check apps/legacy-web/ui-controls.js
cd apps/web && npm ci && npm run build && node --experimental-strip-types --test tests/*.test.mjs
cd services/gateway && cargo check --tests
PYTHONPATH=services/orchestrator:deploy/flower2api /tmp/uikit-venv/bin/python -m unittest discover -s deploy/flower2api -p 'test_system_*.py'
/tmp/uikit-venv/bin/python deploy/flower2api/verify_agy_accounts_ui.py
/tmp/uikit-venv/bin/python deploy/flower2api/verify_execution_node_visibility.py
/tmp/uikit-venv/bin/python deploy/flower2api/verify_cluster_ui.py
/tmp/uikit-venv/bin/python deploy/flower2api/verify_management_ui.py
/tmp/uikit-venv/bin/python deploy/flower2api/verify_agy_environment_ui.py
python3 .deploy/merge-flower2api/run_regression.py after            # 全量 UI 回归
python3 .deploy/merge-flower2api/run_regression.py after-extra --extra
```

脚本的具体入参以各脚本 `--help` / 上次回归记录为准。期望：回归只剩基线已登记的失败（`verify_forwarding`、`verify_management_polish`、`verify_agy_request_records`），原因不变；主线修改过的 UI 脚本全部通过。

## 风险与回滚点

- **漏移植**：主线差异逐条打勾，覆盖核对兜底，实际结果列出每个文件的重放项。
- **网关合并**：`cargo check --tests` 不过时，只修合并造成的问题，不改主线行为。
- **回滚点**：合并提交前随时 `git merge --abort`。合并提交为单次提交，任务进度另提交。
