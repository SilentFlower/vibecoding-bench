# 技术设计：节点管理与系统设置页迁移

需求见 `prd.md`。本文只写实现方案与契约。

## 1. 边界

- 只改前端：`Nodes.vue`、`runtime/AccountNodeSelector.vue`、`runtime/AccountNodeMigration.vue`、`Settings.vue`，以及组件库两处小扩展（§2）。接口、`nodeApi.ts`、`settingsSchema.ts` 与保存逻辑不动。
- 概览数据全部来自已读取的节点列表（接口一次返回全量）与现有 `totalAccounts`，不增加请求。
- 状态文案 `state()`、`preparationState()` 与全部按钮文案、禁用条件保持原样；只改呈现。

### 1.1 定位契约（保留）

| 契约 | 使用者 |
| --- | --- |
| `.node-card`（实体卡根元素）、卡内标题为 heading、卡内 `dd` 末项为「归属账号」 | `verify_cluster_ui` |
| 按钮名：检查连接、检查并同步组件 / 准备运行组件 / 后台同步中…、暂停接单 / 恢复接单、改名、移除、重试移除、同步全部节点、刷新列表、添加节点 | `verify_cluster_ui`、`verify_node_password_ui` |
| 弹窗名：添加 SSH 节点、修改节点名称、移除节点、准备节点运行组件；字段标签：节点名称、服务器地址、SSH 端口、SSH 用户、专用 SSH 私钥、SSH 密码、SSH 认证方式、服务器主机公钥；指纹核对 checkbox | `verify_node_password_ui`、`verify_cluster_ui` |
| `.account-node-selector`、`.node-migration`、`.migration-status`，组合框名「账号」「执行节点」 | `verify_cluster_ui` |
| `.system-settings-nav`（按钮带 `aria-pressed`）、`.settings-save-bar`、`.settings-prime-records`、`.setting-help`、`.setting-error`、`[data-settings-field]`、字段 `name`、searchbox「搜索系统设置」、按钮「保存配置」「撤销修改」 | `verify_remaining_pages`、`verify_scheduling_preferences`、`verify_session_policy_blocks_ui`、`verify_prime_history_ui`、`verify_ui_shell`、`verify_frontend_navigation` |

删除的定位：`.nodes-summary`（由概览卡替代，`verify_cluster_ui` L184 改为断言概览卡）。

## 2. 组件库扩展

- `NumberInput`、`ChoiceSelect` 增加 `label-extra` 插槽：渲染在 `<label>` 元素**之后**、同一标签行内，不进入 label 文本，控件的无障碍名称保持为 `label`。用于「已修改」标签。
- 演示页 `CompositeShowcase.vue` 补一个带「已修改」标签的数字字段示例；`verify_ui_kit.py` 加对应比对对。
- 其余直接复用：`OverviewGrid/OverviewCard`、`EntityCard/EntityBlock`、`IconTile`、`Badge dot`、`Button size=sm`、`ModalDialog`、`Switch`。

## 3. 设计基准

以 `mock.html?s=nodes#nodes`、`?s=settings#settings` 的 1440 计算样式为基准（新脚本 §7.1 逐项比对）。设计稿未画的画面（弹窗、迁移面板、预热记录表、搜索结果、390）沿用组件库与前两批页面的既有规格。

## 4. 节点管理（`Nodes.vue`）

### 4.1 概览卡（`OverviewGrid.nodes-overview`）

| 卡 | 值 | 说明行 | 色调 / 图标 |
| --- | --- | --- | --- |
| 节点 | `rows.length` | `N 台本机 · N 台远程` | primary / Server |
| 远程服务器 | 远程节点数 | 远程节点中待处理数 > 0 时「N 台待处理」，否则「全部正常」；没有远程节点时「尚未添加」 | info / Globe |
| 归属账号 | `totalAccounts`（反重力归属读取失败时为「—」） | 已分配执行位置 | success / Users |
| 待处理 | 待处理节点数 | 见下 | warning / AlertCircle |

待处理判定（每台节点只计一次，按 `state()` 的优先级取第一类原因）：

```ts
/** 需管理员处理的原因；暂停接单、同步中、移除中、正常返回 null。 */
function attention(node: ExecutionNode): 'connection' | 'component' | 'removal' | null {
  if (node.removal) return node.removal.state === 'needs_check' ? 'removal' : null;
  if (!node.enabled) return null;
  if (!node.observation || node.observation.stale || node.observation.state === 'unreachable') return 'connection';
  if (node.preparation?.state === 'failed' || node.preparation?.state === 'needs_check') return 'component';
  return null;
}
```

说明行文案：只有一类原因时为「需检查连接」「组件同步异常」「移除待重试」之一；多类时按「N 台需检查连接 · N 台组件异常 · N 台移除待重试」列出非零项；为 0 时「全部正常」。组件库说明行不换行，多类原因时超出卡宽，本页允许其换行。

### 4.2 节点卡（`EntityCard.node-card`，两列网格，≤ 980 单列）

- **头部**：
  - `media` 插槽放 `IconTile size=lg`（Server，40px，与设计稿 `.tile` 一致）；
  - 标题为节点名；
  - 副标题：本机为「默认本机节点」，远程为 `user@host:port`，用等宽字体；
  - `status` 插槽放 `Badge dot`，按状态着色：

| `state()` | Badge |
| --- | --- |
| 连接正常 | success |
| 待检查、观测已过期 | warning |
| 连接异常、移除待重试 | destructive |
| 移除中 | info |
| 已暂停接单、已移除 | secondary |

- **资源**：`dl.node-resources` 四列（CPU、可用内存、可用磁盘、归属账号），「未采集」用弱化色与小一号字；`dd` 顺序不变。
- **信息块**：`EntityBlock.node-meta`，逐行显示最近检查、Docker、远程节点的运行组件。用 `span` 而不用 `dd`，以保住「卡内 `dd` 末项」契约。取值字重 900：设计稿在 600 字重的行内用 `b`（bolder），计算结果为 900，按计算值对齐。
- **其他内容**：
  - 组件版本变更说明（`old → new`）、观测原因、同步或移除原因照常显示在信息块下方；原因按语义用 danger 文字色。
  - 「主机身份与版本」保留 `<details>`，`summary` 显示为带 `›` 的链接样式，展开内容不变。
- **操作行 `.node-actions`**：
  - 不用实体卡等分底栏，与设计稿一致，改为一行 `Button size=sm`（outline），可换行；
  - 「改名」为 ghost；
  - 「移除」为 `destructive-ghost`，用 `margin-left: auto` 靠右；
  - 移除进度说明与「重试移除」位置不变。

### 4.3 账号执行节点与迁移面板

- `AccountNodeSelector` 外层换第二版卡片外观（表面色、`--ui-radius-card`、`--ui-shadow-card`，无描边），标题 16px，字段两列（≤ 600 单列），底部按钮靠右。
- `AccountNodeMigration` 的分隔线、状态块（`--ui-color-fill-subtle` + `--ui-radius-block`）、错误色换成 token。
- 两组件的 scoped 样式移入 `nodes.css`，组件内不再写样式。

### 4.4 弹窗

- 添加 SSH 节点：`ModalDialog width=640`，表单 `form#node-editor-form`，「取消」「登记节点」放进 `footer` 插槽（`form="node-editor-form"`）。保存中不可关闭：沿用现有的 `setEditor` 拦截，以及 `escape-key-down` / `interact-outside` 时的 `preventDefault`。确认 `ModalDialog` 是否透传这两个事件，不透传就补透传。
- 修改节点名称：`ModalDialog width=420`，`form#node-rename-form`，处理中不可关闭的逻辑不变。
- 字段标签改为 `label for` 显式关联，名称与现在一致。`verify_node_password_ui` 基线在 L36 失败，原因已查明：夹具没有 `/admin/accounts`，节点页读取反重力账号时请求落到静态文件路由，属脚本漂移。夹具补空列表响应，断言不变。
- 移除节点、准备运行组件沿用 `ConfirmationDialog`，不改。

### 4.5 390 形态

- 概览卡沿用组件库断点（≤1000 两列，≤600 单列，与前两批页面一致），节点卡单列，资源保持四列（数字较短），按钮行换行。
- 页头三个按钮由 `PageHeader` 在应用栏下排成一行，不新增入口。
- 不出现页面横向滚动。

## 5. 系统设置（`Settings.vue`）

### 5.1 页头

`PageHeader #actions` 放 `SearchInput`（名称「搜索系统设置」）和「N 项配置」计数（`.settings-total`）。`SearchInput` 的 class 落在内部 input 上，宽 320 写在 `.settings-header-tools > .fui-search` 包装元素上；≤760 时页头操作区与搜索框占满内容宽。删除原 `.settings-overview-bar`。390 时搜索框占满一行，计数在其后。

### 5.2 分类导航（`.system-settings-nav`）

- 每个按钮依次为图标、名称和尾部计数：
  - 有待保存字段的分类：`em.is-dirty` 显示该分类的待保存字段数，琥珀色，`aria-hidden`，让分类按钮名称保持分类名（保存栏已播报总数，脚本按 `exact` 名称点击分类）；
  - 预热记录：`em` 显示记录条数，弱化色。
- 选中项为表面色加卡片阴影，未选中项透明，悬停时用 fill 色。
- 底部说明文字保留。
- 图标：会话与调度 Activity、模型与缓存 Box、客户端与画像 ShieldCheck、连接与稳定性 Globe、预热与拦截 SlidersHorizontal、日志与观测 ListTodo、预热记录 Clock。
- ≤ 900 时导航横向滚动（沿用现有行为）。

### 5.3 工作区

- 分类模式：去掉 `.settings-workspace-heading`，直接排段落卡。
- 搜索模式：顶部一行「搜索结果 · 找到 N 项配置」。段落卡头部保留分类标签（`.settings-result-category`，改用 `Badge secondary`）。
- 段落卡 `section.settings-section-card`：
  - 卡片外观同实体卡（表面色、卡片圆角与阴影）；
  - 头部依次为 `IconTile`（分类图标）、标题（17px）、说明；
  - 字段区为 `.settings-field-grid` 两列，≤ 760 单列。
- 字段渲染：

| kind | 控件 | 「已修改」标签位置 |
| --- | --- | --- |
| number | `NumberInput` | `#label-extra` |
| select | `ChoiceSelect` | `#label-extra` |
| boolean | 行内标题 + 说明 + `Switch :label="field.label"` | 标题后 |
| text / textarea / json / models | `label for` + `Input` / `Textarea`（id 为 `setting-${key}`） | 标签行内、`label` 元素之后 |

- 「已修改」为 `Badge variant=warning`，显示条件为 `dirtyKeys.includes(field.key)`，撤销或保存成功后消失。
- 布尔字段 `updateField(key, value)` 的调用保持不变，只是事件来源由原生 change 改为 `Switch` 的 `update:modelValue`。保存失败定位的选择器 `input, textarea, button` 本就覆盖开关按钮，不改。
- 预设按钮（推荐模型、清空模型、默认 UA 白名单、关闭 UA 限制、仅允许 280 / 293）换成 `Button size=sm variant=soft`，名称不变。
- 帮助与错误：`.setting-help` 为弱化色，`.setting-error` 为 danger 色，都保留类名。

### 5.4 预热记录

保留现有表格结构与移动端明细列，换 token 样式。结果徽标改用 `Badge dot`：成功 success、跳过 secondary、失败 destructive。`.settings-log-state` 的自定义着色删除。空状态沿用现有文案。

### 5.5 390 形态

分类导航横向滚动，字段单列，浮动保存栏沿用组件库样式。不出现页面横向滚动。

## 6. CSS 组织

- 新建 `apps/web/src/nodes.css`，承载节点页、账号执行节点、迁移面板与两个节点弹窗的样式：
  - `Nodes.vue` 引入；
  - 三个组件的 scoped / 全局 `<style>` 全部删除。
- 新建 `apps/web/src/settings.css`，替代 `settings-design.css`：
  - `Settings.vue` 改为引入新文件，旧文件删除；
  - 删除前 grep 全仓，确认无其他使用者；
  - 旧文件里已无使用者的规则（如 `.settings-nav`）不迁移。
- 两个新文件只用 token，规则包在 `@layer components` 内，与前两批页面文件（`proxies.css` 等）一致。层内规则压不过未分层的旧规则，所以被替代的旧规则必须删除。不出现 `!important`、十六进制或 `rgb()` 色值、圆角字面量。
- `theme.test.mjs` 的 CSS 列表加入 `nodes.css`、`settings.css`；组件列表加入 `Nodes.vue`、`Settings.vue`、`AccountNodeSelector.vue`、`AccountNodeMigration.vue`。

## 7. 验证

### 7.1 新脚本 `deploy/flower2api/verify_nodes_settings_design.py`

- **基准比对**：沿用 `verify_records_pages_design.py` 的 PAIRS / KNOWN 模式，比对设计稿与实际页面 1440 的计算样式：
  - 节点页：概览卡、实体卡头部与徽标、资源块、信息块、小号按钮、危险文字按钮、账号执行节点卡；
  - 设置页：页头搜索、导航选中项与计数、段落卡头部、字段标签、「已修改」标签、输入框、保存栏。
  - KNOWN 只收确有理由的差异，并逐条注明。
- **自带夹具**：8 台节点，覆盖连接正常、未检查、连接异常、观测过期、组件失败、暂停且不可达、移除中、移除待重试。
- **行为断言**：
  - 待处理为 5，说明行为「3 台需检查连接 · 1 台组件异常 · 1 台移除待重试」；
  - 远程服务器说明行正确；
  - 各状态徽标颜色类别正确，其中「待检查」为 warning；
  - 设置页修改一个数字字段后：该字段出现「已修改」，导航计数为 1，保存栏显示「1 项待保存」；
  - 切换布尔开关后计数加 1；
  - 撤销后标签与计数全部消失；
  - 搜索模式显示结果行与分类标签。
- **390 与截图**：两页 390 无页面横向滚动，零控制台错误；截图存 `.deploy/console-ui-revamp/nodes-settings/verify/`。

### 7.2 既有脚本分诊

| 脚本 | 改动 |
| --- | --- |
| `verify_cluster_ui` | L184 由 `.nodes-summary` 改为断言「归属账号」概览卡值为 3；其余定位按 §1.1 保留，预期不改 |
| `verify_node_password_ui` | 夹具补 `/admin/accounts` 空列表（§4.4），断言不变 |
| `verify_prime_history_ui` | L81 点击「刷新」前把鼠标移出模型气泡触发器，避免悬停让气泡重新打开挡住按钮；断言不变 |
| `verify_remaining_pages` | L52 的字段数 56 按设置页实际提交的键集合核对后改为正确值，并注明来源 |
| `verify_scheduling_preferences`、`verify_session_policy_blocks_ui`、`verify_prime_history_ui`、`verify_ui_shell` | 预期不改；失败时只按 §1.1 调整定位 |
| `verify_frontend_navigation` | 基线失败点 L105 不变 |
| `verify_ui_kit` | 加 `label-extra` 示例的比对对 |

### 7.3 回归

- 基线：当前 HEAD 的业务代码与 4-2 提交 `9765980b` 相同，直接沿用 4-2 改动后的回归结果。
  - 回归集 36 个：28 通过 + 负载敏感的 `prime_history` 重跑通过。
  - 集合外 26 个：20 通过、6 失败。
- 改动后逐项对照，新增失败要么修复，要么按 §7.2 分诊。

## 8. 规范同步

`.trellis/spec/web/frontend/ui-guidelines.md`：

- 补 `label-extra` 插槽签名；
- 补节点页概览口径与状态色表、设置页字段与「已修改」规则、两页 390 规则；
- 测试入口加入新脚本。

## 9. 发布与回滚

- 纯前端改动，随下一次网关镜像发布。
- 回滚时整体回退本任务提交。旧 `settings-design.css` 删除与新文件引入在同一提交内，不存在中间态。
