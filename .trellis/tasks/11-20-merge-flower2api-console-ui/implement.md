# 执行计划 — 合并 flower2api 并移植到第二版控制台

证据目录 `.deploy/merge-flower2api/`（git 忽略）。每步完成后勾选并写实际结果。

## 步骤

- [x] **0. 基线**
  - 记录合并现场：`MERGE_HEAD`、冲突清单、自动合并文件清单。
  - 从 `b0858810` 导出合并前的构建，截取 Vue 主要页面与原生 36 个状态的浅色、深色图（复用 `final-review` 的截图工具）。
  - 列出主线修改过的验证脚本，作为回归集合的补充。
  - 实际结果：现场记录在 `merge-state.txt`（HEAD `b0858810`、MERGE_HEAD `9c80a39a`、11 个冲突）。基线从 `b0858810` 导出到 `/tmp/merge-pre-root` 构建，`before-vue-{light,dark}` 各 21 张、`before-native-{light,dark}` 各 36 个状态（1 个不可达，同复核基线）。主线改过的 UI 脚本：`verify_system_update_browser`、`verify_execution_node_visibility`、`verify_cluster_ui`，都在回归集合内；`verify_system_update`、`verify_agy_*` 为 Docker / 运行时端到端，不属 UI 回归。
- [x] **1. 后端与文档**（design §2）：已合并的 `system_updater.py`、`SYSTEM-UPDATES.md` 标记为已解决；运行主线触及系统更新的后端单测。
  - 实际结果：`test_system_*.py` 158 项通过（1 项跳过），`test_cluster_system_update.py` 7 项通过。系统 Python 缺 `docker` 包，改用带 docker SDK 的 `/tmp/uikit-venv/bin/python`。
- [x] **2. 系统更新弹窗**（design §3）
  - 依次完成：`updateSteps.ts` 的阶段文案；弹窗的动作、按钮矩阵、安装方式区、状态标签、维护提示；远程节点后台入口；账号后台更新分区与重试；健康探测详情；版本记录与确认框的重启分支；`system-update.css`。
  - 删除 `SystemUpdates.vue`，保持本分支的删除。
  - 调整 `verify_system_update_browser.py`、`verify_update_design.py` 等脚本，覆盖三条安装路径的载荷、账号重试与健康探测。
  - 实际结果：按 design §3 与 §4.1 完成。`verify_system_update_browser.py` 共 12 个用例通过，含主线三个用例的弹窗版和新增两个用例：下载（`/prepare`、60 秒、无 `prepared_operation_id`）、立即重启（`/install`、带下载操作 ID、60 秒、不问期限）、已下载的兼容安装（带 ID、所选 5 分钟 = 300 秒）、版本记录下载直接提交与重启确认框、快速切换与远程节点后台、账号后台更新重试、健康探测。`verify_update_design.py` 通过。与旧整页相比不移植的只有横幅标题「发现新版本 / 更新已下载」及其说明句，由状态标签与安装方式区承担。
- [x] **3. 其余冲突**（design §4）：依次处理 `Accounts.vue`、`SchedulingDetails.vue`、`RequestDiagnostics.vue`（含 `request-design.css` 保持删除、规则写入 `request-records.css`）、`NativeStageDetails.vue`、`RuntimeEnvironments.vue`、`native-environment.css`、`verify_execution_node_visibility.py`。
  - 实际结果（每个文件的重放项）：
    - `Accounts.vue`：卡片调度入口统一、`refreshingUsage.has`（卡片 2 处、概览 1 处）、工作区调度页签不再排除反重力、概览「调度详情」对反重力可见、反重力概览「调度优先级」、两项新 `Checkbox`、`SchedulingDetails :antigravity`。脚本部分（默认值、回填、`agyFormKeys`、载荷、`refreshEntryUsage`、`accountAlive`）为自动合并。
    - `SchedulingDetails.vue`：已绑定会话卡、提交点说明、优先级说明、额度提示与会话分区的 `antigravity` 条件；脚本部分自动合并。
    - `RequestDiagnostics.vue`：`saveDiagnostics`、页头「正文采集范围」、错误阶段与 RESOURCE_EXHAUSTED、`input_rejection_field` / `input_rejection_reason`、控制错误码与恢复判定、`saved` 证据状态；`request-design.css` 保持删除，`.request-diagnostics-settings` 写入 `request-records.css`。
    - `NativeStageDetails.vue`：`tlsWire` 分支采用主线、类名用 `request-wire-note` / `request-wire-reason`；AGY 证据块改用 `request-wire-note`。
    - `RuntimeEnvironments.vue`：`environmentName`（卡片、抽屉、确认）、AGY 版本行与 `kernelLabel`、待回填 / 热进程 / 预热、特性行与运行时段条件、概览「空闲热进程」、技术详情空闲数 / PID / 正在预热。
    - `native-environment.css`：保留第二版 token 版本，重放 `:has(> button:only-child)` 与 `> button` 收窄。
    - `verify_execution_node_visibility.py`：保留 `.fui-entity-card-head`，采用主线的本机执行节点期望。
    - 冲突文件中主线新增的文案与标识符逐项比对，均已带入（系统更新只差上述横幅句）。
- [x] **4. 自动合并文件核对**（design §5）：跑静态规则，修正违规；核对主线新增界面在第二版里的位置与样式。
  - 实际结果：静态规则通过（33 项单测）；`lucide-vue-next` 只出现在已删除的 `SystemUpdates.vue`，`package.json` 保持无该依赖。`AgyAccountUsage` 的 `.agy-quota-note` 已有 token 样式；`EnvironmentKernel` 的原生 `<select>` 改为 `ChoiceSelect`（design §4.1）；设置计数 59→60 同步脚本。主线未更新的 `verify_agy_accounts_ui.py`、`verify_environment_ui.py` 夹具按新行为同步。
- [x] **5. 规范**（design §6）：同步 `ui-guidelines.md`。
  - 实际结果：系统更新弹窗（动作选择、冻结、概览、版本记录、进度文案、远程节点、账号后台更新、操作详情、钩子、错误用法）、请求记录（诊断设置与拒绝说明、AGY 实际出站证据）、账号（反重力额度刷新、调度口径、两项配置）、运行环境（反重力卡片与内核选择）、设置计数 60。`platform-online-update.md` 一处「管理页」对齐为「系统更新弹窗」。
- [x] **6. 全量验证与对照**
  - 运行下方全部命令。
  - 浅色、深色改前改后比对：差异只出现在主线功能带来的区域，并逐项登记。
  - 截取移植区域的定向截图（下载 / 重启 / 账号后台更新 / 健康探测、账号页反重力调度、请求记录诊断设置、AGY 出站证据、运行环境反重力卡片）。
  - 实际结果：
    - 无冲突残留；`node --check` 4 个原生脚本通过；`npm ci`、构建、33 项前端单测（含静态规则）通过；后端 `test_system_*` 158 项、`test_cluster_system_update` 7 项通过。
    - 全量 UI 回归：主集合 43 个中 41 个通过，扩展集合 26 个中 25 个通过；失败的 3 个即基线已登记的 `verify_forwarding`（缺 `--manifest`）、`verify_management_polish`（首屏两次检查更新）、`verify_agy_request_records`（缺 `--image/--baseline`），原因不变。首轮 `verify_nodes_settings_design` 因设置计数 59→60 失败，同步断言后通过。
    - 像素对照（184 张）：原生 144 张浅色、深色全部一致；Vue 40 张只有系统设置页 4 张有差异，为主线新增设置项带来的「59 项配置 → 60 项配置」。
    - 定向检查 `check_ported.py`（浅色、深色各一遍，截图在 `ported/`）：账号（进入列表逐个刷新反重力额度、失败只在卡片提示、两项新配置保存、反重力调度详情不读会话）、请求记录（正文采集范围保存与隐藏、输入拒绝、RESOURCE_EXHAUSTED、AGY 实际出站证据）、运行环境（账号名、热进程与预热、单项特性行、内核 `ChoiceSelect` 切换）、系统更新（下载 / 重启安装方式、恢复接单与远程节点、账号后台更新四种状态、健康探测）全部通过。

- [x] **Check-All 修复**：CHK-001 主题预览画板（`/?theme-preview=1`）里的账号页会触发反重力额度自动刷新。
  - 修复：`Accounts.vue` 读同一查询参数，画板内不做进入列表的自动刷新；规范「主题设置页 · 预览画板」补充合同。
  - 测试：`verify_theme_settings.py` 夹具在首页第一页放可用反重力账号。修复前断言失败（`POST /admin/accounts/12/usage`），修复后通过。
  - 定向回归：主题、反重力账号、账号页、深色模式、外壳 6 个脚本通过；`check_ported.py` 浅色、深色复跑通过，直接打开首页仍逐个刷新。

## 验证命令

```bash
git diff --name-only --diff-filter=U        # 为空
node --check apps/legacy-web/app.js && node --check apps/legacy-web/projects.js && node --check apps/legacy-web/environments.js && node --check apps/legacy-web/ui-controls.js
cd apps/web && npm ci && npm run build && node --experimental-strip-types --test tests/*.test.mjs
PYTHONPATH=services/orchestrator:deploy/flower2api python3 -m unittest discover -s deploy/flower2api -p 'test_system_*.py'
PYTHONPATH=services/orchestrator:deploy/flower2api python3 -m unittest discover -s deploy/flower2api -p 'test_cluster_system_update.py'
python3 .deploy/merge-flower2api/run_regression.py after            # 69 个 UI 脚本 + 主线修改过的 UI 脚本
python3 .deploy/merge-flower2api/run_regression.py after-extra --extra
```

期望：回归只剩基线已登记的失败（`verify_forwarding`、`verify_management_polish`、`verify_agy_request_records`），原因不变；主线新增或修改的 UI 脚本通过，或给出与主线相同的环境原因。

## 风险与回滚点

- **系统更新流程语义**：两步流程直接影响生产更新操作。提交载荷与主线逐字段对照，三条路径都用夹具断言请求体。
- **漏移植**：以「分叉点 → 主线」的差异为清单逐条打勾。实际结果中列出每个冲突文件的重放条目。
- **主线样式进入第二版页面**：静态规则与浅色、深色像素比对兜底。
- **回滚点**：合并提交前随时可以 `git merge --abort`，备份在 `/tmp/console-ui-pre-merge-backup`。合并提交为单次提交。
