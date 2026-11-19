# 技术设计：系统更新弹窗与步骤记录

依据父任务 `../11-19-console-ui-revamp/design.md` §4。画面基准是 `doc/design/console-v2/mock.html#update` 与 `#update-progress`（样式在同目录 `mock.css` 的 `.um`、`.u-*`、`.strip`、`.pill`、`.live`）。

## 1. 边界

| 层 | 改动 |
| --- | --- |
| 更新器 `deploy/flower2api/system_updater.py` | `_record` 追加步骤，`_public_operation` 公开 `steps` |
| 管理桥、网关 | 不改动：`/api/system-updates/*` 原样转发更新器 JSON（`services/orchestrator/system_updates.py:458-500`） |
| 路由 `apps/web/src/router.ts` | `updates` 子路由改为渲染账号页，弹窗由外壳打开 |
| 外壳 `Dashboard.vue` | 原生 `<dialog>` + 内嵌 `SystemUpdates` 换成 `SystemUpdateDialog`，补 `/updates` 打开 / 关闭逻辑 |
| 新组件 | `components/SystemUpdateDialog.vue`（业务）、`components/ui/notice-strip/NoticeStrip.vue`（组合组件） |
| 纯函数 | `lib/updateSteps.ts`：步骤表推导 |
| 样式 | `src/system-update.css`（新，`@layer components`）；`kit.css` 加 `.fui-strip*`；删除旧更新样式 |
| 删除 | `components/SystemUpdates.vue` 及其专属样式 |

## 2. 后端步骤记录

### 2.1 写入点

`_record` 是全部阶段写入的唯一落盘口：`_phase`、`_finish` 以及宿主经回调 `save()` 写入（`system_update_host.py:1103-1110` 的 `restoring_data` → `restoring`）都经过它。在这里比较阶段：

```python
STEP_LIMIT = 64

def _record(self, operation: dict) -> None:
    with self.lock:
        ...  # 原有 cancel_requested 合并
        steps = operation.setdefault('steps', [])
        # 只在阶段变化时追加；排空等待每 0.5 秒重写同一阶段，不应产生重复步骤。
        if not steps or steps[-1]['phase'] != operation['phase']:
            steps.append({'phase': operation['phase'], 'at': utc_now()})
            del steps[:-STEP_LIMIT]
        atomic_json(path, operation)
        self._persist()
```

- `submit` 首次落盘即记下 `preparing`。
- 取消接口在控制线程读盘后 `_record`，阶段未变，不追加。
- 恢复路径（`_recover`）和执行线程用的是同一个操作对象，步骤连续。
- 旧操作文件没有 `steps`：读取时公开为 `null`。若旧操作再被恢复，从当时阶段开始记录。
- 上限 64：正常安装最多 10 步左右，恢复反复进入时截掉最早的记录。每条约 60 字节，远低于 8 MiB 读取上限。

### 2.2 公开字段

`_public_operation` 的键白名单加 `steps`，类型 `list[{phase: str, at: str}] | None`，`at` 为 `utc_now()` 的 ISO 时间。`api.ts` 的 `SystemUpdateOperation` 加 `steps?: Array<{ phase: string; at: string }> | null`。

### 2.3 单测

`deploy/flower2api/test_system_updater.py`（`FakeDeployment` 下执行生产实现）：

- 正常安装：步骤依次为 `preparing, draining, switching, verifying, committing, cleaning, succeeded`。`drained` 先返回两次未就绪，`draining` 只记一次。每条带时间，`status()['operation']['steps']` 与之相同。
- 宿主恢复路径：`FakeDeployment.restore` 模拟宿主写 `restoring_data` 再写 `restoring` 并调用 `save()`，健康检查失败后步骤为 `…, verifying, restoring, restoring_data, restoring, restored`。
- 旧操作：手写不含 `steps` 的操作文件并设为 `last_operation`，`status()` 返回 `steps is None` 且不报错。
- 上限：对同一操作交替写入 70 次不同阶段，保留最后 64 条。

`deploy/flower2api/test_system_migrations.py`：迁移安装（策略 schema 2）的步骤含 `draining, switching, snapshotting, migrating, switching, verifying`，两次 `switching` 都保留。

## 3. 前端

### 3.1 挂载与路由

- `router.ts`：`{ path: 'updates', name: 'updates', component: () => import('./components/Accounts.vue') }`。网关已登记的 `/updates` SPA 路径、书签和验证夹具都不受影响。
- `Dashboard.vue`：
  - `updatesOpen` 为真时挂载 `<SystemUpdateDialog v-model:open="updatesOpen" />`（异步组件）；关闭即卸载，沿用「弹窗打开才轮询」。
  - 版本号点击：没按修饰键时 `preventDefault`，打开弹窗、关闭移动抽屉，地址不变。
  - 路由监听：`route.fullPath` 变化时令 `updatesOpen = route.name === 'updates'`。直接访问或改址到 `/updates` 会打开，离开其他页面会关闭。弹窗内的 router-link（如「管理环境」）跳转后弹窗自然关闭。
  - 关闭：若当前路由是 `updates`，`router.replace({ name: 'accounts' })`；之后照旧 `refreshMetadata(true)` 刷新版本号角标。
- 标题表保留 `updates: '系统更新'`，移动端应用栏在弹窗打开期间显示「系统更新」。

### 3.2 组件结构

`SystemUpdateDialog.vue`（中文 docstring 说明 props / 事件）：

- 外层 `ModalDialog`：标题「系统更新」，说明「检查版本、阅读发布说明，选择合适的时间安装。」，宽 768。`media` 插槽放成功色图标块（`IconTile tone="success" size="lg"` + `ArrowUpCircle`）。面板类名 `system-update-dialog`。关闭按钮沿用 `DialogContent` 的「关闭」。
- 数据与动作整体搬自 `SystemUpdates.vue`，逻辑不变：`refresh` 串行轮询与退避、`check`、`cancel`、`connect`、`operationId`、`releaseLabel`、`releaseHighlights`、`currentVersion`、`environmentSources`。
- 新增 `view: 'overview' | 'progress' | 'history' | 'maintenance' | 'details'` 和 `followed`（本次弹窗内观察到处于维护中的操作 ID）。

### 3.3 视图选择与底栏

| 视图 | 何时显示 | 内容 | 底栏 |
| --- | --- | --- | --- |
| 读取中 / 未接入 / 不可用 | `loading`；`installed=false`；状态读取失败（`status` 为空） | 读取文案；未接入时「首次接入系统更新」+ 说明；三者都显示「当前版本：x」，错误见顶部提示条 | 无 |
| 概览 `overview` | 默认 | 版本区（标签 + 四格摘要 + 兼容提示条）；检查错误提示条；发布说明区；安装方式区；上次操作紧凑提示条（有操作且不在进度视图时） | 版本记录与回退、运行组件与维护详情 ·· 检查更新、安装更新 |
| 进度 `progress` | 见下方规则 | 进度区（标签 + 四格摘要 + 维护说明 / 结局提示条）；步骤列表（「更新进度 n / m」+ 实时标记）；阻塞原因；节点同步进度 | 操作详情与数据库快照 ·· 取消等待、恢复操作、主按钮（维护中为禁用的「更新中…」；结束后为「完成」，回到概览；从「查看记录」进入时为「返回」；等待对账、清理待重试时不显示，由「恢复操作」承担） |
| 版本记录 `history` | 底栏进入 | 可用版本列表（最新与当前突出，其余在「查看历史版本与回退」下），单条展开详情，非当前版本「安装更新」；已安装版本与回退 | 返回 |
| 维护详情 `maintenance` | 底栏进入 | 账号运行环境（运行数、管理环境链接、镜像来源）、CLI 与请求内核 | 返回 |
| 操作详情 `details` | 进度底栏或上次操作提示条进入 | 目标发行、操作 ID、更新时间、数据库快照、各库迁移状态 | 返回 |

进度视图规则（按顺序判断）：

1. 没有操作记录（含 `busy` 为真但 `operation` 为空）：概览，标签显示「正在执行维护」。
2. `status.busy` 为真，或操作阶段是 `reconcile` / `succeeded_cleanup_pending`：强制进度视图，此时二级视图仍可进入。维护期间的错误与恢复先于发布说明呈现（`ui-guidelines.md` 工作区场景合同）。
3. 本次弹窗内观察到该操作在维护中（`followed === operation_id`）：结束后仍停在进度视图显示结局，用户点「完成」才回概览。
4. 其他已结束的操作：概览底部显示上次操作提示条，例如「上次操作 · 更新完成 · v1.0.1 · 11/12 13:31」，「查看记录」进入进度视图。这对应规范「成功记录紧凑呈现」。

### 3.4 安装、回退与恢复

冻结请求的合同不变（`platform-online-update.md` 冻结操作节）：请求体为 `operation_id, expected_revision, target_release, target_manifest_sha256, drain_timeout_seconds`；同一冻结对象重试沿用原 UUID；409 不自动重放。

- **安装最新版本（直接安装）**：
  - 概览底栏「安装更新」一次完成冻结和提交，等待上限取自安装方式区的 `NumberInput`（min 1、max 120、step 1，默认 1）。
  - 显示条件：最新版本不是当前版本。按钮文案和禁用条件沿用旧版本列表（`SystemUpdates.vue:281`）：目录不新鲜时禁用并显示「先检查更新」，数据不兼容时禁用并显示「待验证兼容」，维护中或提交中禁用。
  - 等待上限不是 1～120 的整数时，输入框标红，弹窗内提示「等待期限应为 1～120 分钟」，不提交。
  - 提交后（`sent`）锁定输入框与按钮文案「正在登记…」。成功后 `followed` 设为该操作并切到进度视图。
  - 网络结果不确定时保留冻结对象，再点「安装更新」重发同一请求。
  - 409 时在安装方式区下方显示提示「现场版本已经变化，请关闭窗口并刷新后重新选择」，按钮禁用。关闭弹窗时清除冻结对象。
- **回退、版本记录列表中的安装（含最新版本）、恢复**：在当前弹窗之上打开 `ConfirmationDialog`。列表视图看不到安装方式区，所以列表安装一律二次确认。
  - 标题分别为「确认版本回退」「确认安装更新」「恢复本次操作」。
  - 正文为目标版本、发行标识与原有说明文案；回退和列表安装多一个等待上限 `NumberInput`，默认 1。
  - 确认按钮为「确认执行」或「开始恢复」；409 用组件的 `error` 显示，并以新增的可选属性 `confirmDisabled`（默认 false，其他调用方不变）禁用确认、保留取消；提交中不可关闭（组件已支持 `busy`）。
  - 恢复只提交 `expected_revision`，沿用原操作 ID。
- **取消等待**：进度底栏，条件不变（`busy` 且阶段为 `preparing` / `draining`）。已请求取消时显示「正在取消…」。

### 3.5 步骤表推导（`lib/updateSteps.ts`）

```ts
/** 一行步骤：phase 原始阶段；state 已完成 / 进行中 / 待执行；at 进入时间（ISO，未知为 null）。 */
export interface UpdateStepRow { phase: string; state: 'done' | 'active' | 'pending'; at: string | null }
/** 由操作与安装能力推导步骤表与结局。@param operation 公开操作。@param options 是否有快照 / 迁移步骤、是否维护中。@return 行与计数。 */
export function updateSteps(operation: SystemUpdateOperation, options: { snapshot: boolean; migrate: boolean; busy: boolean }): { rows: UpdateStepRow[]; done: number; total: number; outcome: string | null }
```

- 规范顺序：`preparing → draining → [snapshotting → migrating] → switching → verifying → committing → cleaning`。
  - `snapshot` 取 `status.migration_capability`。
  - `migrate` 取目录中目标版本的 `migrations?.length > 0`，或步骤中出现过 `migrating`。
- 结局阶段 `succeeded, succeeded_cleanup_pending, failed, cancelled, restored, reconcile, prepared` 不成行，作为 `outcome` 交给标签与提示条。恢复中的 `restoring`、`restoring_data` 成行。
- 有 `steps` 时：
  - 去掉结局阶段后，同一阶段只保留最后一次出现及其时间。第一次 `switching`（越过取消边界）由此并入后面真正的切换，与父设计「第一次 switching 不单独成行」一致；恢复中反复进入的阶段同理。
  - 维护中时最后一行为「进行中」，其余为「已完成」。
  - 当前阶段属于规范顺序时，在其后补上规范顺序中尚未出现的阶段，记为「待执行」。
- 无 `steps`（旧操作）：
  - 当前阶段在规范顺序中：之前的阶段记为已完成，时间为空；当前阶段为进行中（维护中）或已完成；之后的阶段待执行。
  - `succeeded`：规范顺序全部已完成，时间为空。
  - 其他结局：不出行，只显示结局提示条。
- `done` / `total` 只在正向流程（当前阶段属于规范顺序或为 `succeeded`）时用于「n / m」；恢复与失败流程不显示计数。
- 行内说明只用真实数据：
  - `draining` 进行中时为「仍有 N 项在途工作，新工作已暂缓」（N 为 `blockers.length`，为 0 时显示「等待在途工作自然结束」）。
  - `snapshotting` 有快照时为「快照已校验 · x MiB」，或「快照状态：…」。
  - `migrating` 为各库「平台数据库 / 网关数据库 + 迁移状态」。
  - 其余为空。
- 阶段名沿用现有 `phases` 文案表（如「下载与校验」「等待在途完成」「正在恢复数据库」）；未知阶段显示原值。

`apps/web/tests/update-steps.test.mjs`（`node --experimental-strip-types --test`）覆盖：

- 正向含迁移、维护中进行中行与待执行补齐、两次 `switching` 合并。
- 恢复路径、旧操作无 `steps`（进行中与已完成两种）、未知阶段、上限截断后的列表。

### 3.6 状态与提示

- **概览标签**沿用 `updateSummary` 的七种状态，`role="status"`：
  - 有可用更新：成功色。
  - 检查中：信息色。
  - 检查遇到问题：警告色。
  - 其他：中性。
- **兼容提示条**：
  - 目录新鲜且兼容：成功，「兼容性检查通过 · 安装前自动保存平台与网关数据库快照」。迁移能力为假时去掉快照半句。
  - 不兼容：警告，「兼容性待核对」+ 具体原因（沿用 `compatibility_reason` 两条文案）。
  - 目录不新鲜：中性，「版本目录待刷新」。
- **检查错误**：`catalog.check_error ?? status.check_error` 以警告提示条显示在版本区下方，版本记录视图同样显示。
- **进度标签与提示条**：
  - 维护中：标签「更新中」（信息色），提示条「维护期间新工作暂缓，在途工作自然结束后继续。」（中性）。
  - 结局：标签与提示条用 `phases` 文案。`succeeded` 为成功色；`cancelled` 为中性；`restored`、`reconcile`、`succeeded_cleanup_pending` 为警告色；`failed` 为危险色。有 `error` 时另起一条危险色提示条显示原文（`role="alert"`）。
- **实时标记**：维护中且尚未到结局时显示，最近一次轮询成功为「实时」，失败为「重新连接中」；进度标签的转圈图标同样只在此时显示（等待对账等结局状态不显示）。连接错误沿用 `error` 文案，以 `role="alert"` 警告提示条显示在弹窗顶部（含「平台正在切换，正在重新连接…」）。

### 3.7 样式

- `src/system-update.css`（`@layer components`，`main.ts` 在 `console-shell.css` 之后引入）。类名前缀 `su-`，只取 token：
  - `.su-section`：设计稿 `.u-sec`，底色 `--ui-color-fill-subtle`，圆角 `calc(var(--ui-radius-block) + 2px)`。
  - `.su-head`、`.su-tiles`、`.su-notes`、`.su-plan`、`.su-log`（`done` / `active` / `pending` 三态，待执行圆点 `--ui-color-fill-strong`）、`.su-live`、`.su-pill`（成功 / 信息 / 警告 / 危险 / 中性）。
  - 二级视图的列表与详情块沿用 `.fui-entity-block` 式浅灰块，复用 token。
  - 窄屏（≤600）时四格摘要改两列，步骤行时间列收窄、说明换行，安装方式区改纵向排列。
- `NoticeStrip`：`kit.css` 加 `.fui-strip`（类名避开已被通知浮层占用的 `.fui-notice`；设计稿 `.strip`：高 36、圆角 10、12.5px / 650），tone 为 `success | warning | danger | info | neutral`。插槽：默认插槽放图标与文字，`end` 插槽放靠右的徽标。演示页「组合组件」区加示例，`verify_ui_kit.py` 加比对对（tasks 画面的 `.strip.s`、update-progress 画面的 `.strip.n`）。

## 4. 删除的旧代码

- `components/SystemUpdates.vue` 整个文件（逻辑搬入新组件）。
- `approved-design.css` 两段旧更新样式（「系统更新采用原型的标题与正文层次…」段、「更新状态、说明、平台与记录各自成区…」段，约 60 条）。
- `style.css` 两段：`update-overview-heading`…`update-release-latest` 段，以及「定稿更新工作区…」段。
- 删除前逐条 grep，确认类名只被旧更新组件与 `Dashboard.vue` 的原生 dialog 使用；`.account-configuration` 等相邻规则不动。

## 5. 脚本依赖的钩子

| 钩子 | 用途 |
| --- | --- |
| `.system-update-dialog` | 弹窗面板（取代 `.approved-update-dialog`） |
| `[data-update-view=overview\|progress\|history\|maintenance\|details\|uninstalled]` | 当前视图（`uninstalled` 含更新服务暂不可用） |
| `[data-update-tile=current\|latest\|published\|checked\|target\|operation\|updated]` | 摘要格（取代 `.approved-platform dd`） |
| `[data-update-step][data-state]` | 步骤行 |
| `[data-release-card]`、`[data-release-details]` | 版本卡与展开详情（保持） |
| 无障碍名称 | 「关闭」「安装更新」「检查更新」「版本记录与回退」「运行组件与维护详情」「操作详情与数据库快照」「返回」「查看完整发布说明 / 收起完整发布说明」「查看历史版本与回退」「回退到此版本」「取消等待」「恢复操作」「确认执行」「开始恢复」「在途等待上限」（数字输入） |

## 6. 验证

### 6.1 单测与构建

- `cd deploy/flower2api && PYTHONPATH=../../services/orchestrator /tmp/uikit-venv/bin/python -m unittest test_system_updater test_system_migrations`。
- `node --experimental-strip-types --test apps/web/tests/theme.test.mjs apps/web/tests/update-steps.test.mjs`；`npm --prefix apps/web run build`。

### 6.2 脚本分诊

规则同子任务 1、2：样式采样移到新基准，行为断言不放宽。

| 脚本 | 集合 | 处理 |
| --- | --- | --- |
| `verify_update_design.py` | 回归集 | 改写：对 `mock.html#update`、`#update-progress` 逐项比对计算样式（弹窗宽、头部、区块、四格、提示条、发布说明、安装方式、底栏、三态步骤行、实时标记、标签）。保留：说明展开 / 收起、文本转义、点击安装前零写入、1440 / 720 / 390 无横向溢出。必要的 `KNOWN` 写明原因 |
| `verify_system_update_browser.py` | 集合外 | 改写为弹窗流程，场景与断言一一保留：直接安装默认 60 秒、改 30 分钟提交 1800、双击幂等、断线重连、快照 / 迁移在详情视图、`restoring_data`、完成、刷新后显示上次操作、409、未接入、回退（二次确认默认 1 分钟）与取消等待、恢复居中。新增步骤行与时间断言 |
| `verify_design_parity.py` | 回归集 | 删除对旧原型更新弹窗的比对与截图，以及原确认框的选择流程（分别由 `verify_update_design.py`、`verify_system_update_browser.py` 覆盖），账号部分不动；「品牌更新保持路由」与零写入断言改用新钩子保留 |
| `verify_management_ui.py` | 回归集 | 更新段改为从运行环境页点版本号打开弹窗（`/updates` 背后是账号页，该夹具未声明账号接口；深链接由 `verify_system_update_browser.py` 覆盖），在版本记录视图操作：版本卡展开、历史展开、列表安装的二次确认取消零写入；截图保留。失败点须与基线相同 |
| `verify_frontend_navigation.py` | 回归集 | 进入 `/updates` 后先断言弹窗打开，关闭后地址为 `/`，再遍历导航；关闭按钮名改「关闭」。失败点须与基线相同（`#theme-toggle`） |
| `verify_accounts_design.py`、`verify_workspace_experience.py`、`verify_ui_shell.py` | 回归集 / 集合外 / 新 | 选择器换成 `.system-update-dialog`，关闭按钮名改「关闭」 |
| `verify_runtime_platform_version.py` | 集合外 | `.approved-platform dd` 改为 `[data-update-tile=current]`；未接入「当前版本：x」文案保持 |
| `export_frontend_preview.py`、`verify_stack.py`、`verify_environment_ui.py`、`verify_dashboard_update.py` | — | 只读路由或只看角标，预计不改；回归确认 |

### 6.3 回归

- 改动前在当前 HEAD 跑回归集（37）与集合外（26）作基线。改动后逐项对照：新增失败要么修复，要么证明是更新页采样并按上表分诊。
- `verify_system_update.py`（真实 Docker 端到端）本机不跑，与子任务 1、2 相同；字段变化由单测覆盖。

## 7. 规范与文档同步

- `.trellis/spec/platform/deploy/platform-online-update.md`：
  - 公开操作字段加 `steps` 及其语义（阶段变化时追加、去重、上限 64、旧操作为空）。
  - 管理页面 `/updates` 改为「打开系统更新弹窗」。
  - 必需验证中 `verify_system_update_browser.py` 的场景描述同步。
- `.trellis/spec/web/frontend/ui-guidelines.md`：
  - 「深层弹窗排版约束」中的系统更新段改为新弹窗合同：视图、直接安装与二次确认、步骤表规则、钩子、验证脚本。
  - 外壳节的 `/updates` 入口描述同步。
  - 组合组件表加 `NoticeStrip`。
- `deploy/flower2api/SYSTEM-UPDATES.md`：「系统更新页面」等措辞改为弹窗，按钮名与现状一致（「恢复操作」）。

## 8. 兼容与回滚

- 后端字段只增不改；旧前端忽略 `steps`，新前端兼容无 `steps` 的旧操作。更新器与控制镜像可以分别发版。
- 前后端在同一提交中，回滚整体回退本任务提交。`steps` 已写入的操作文件对旧更新器无害，旧更新器只是不再追加。
