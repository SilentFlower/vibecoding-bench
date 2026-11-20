# 技术设计：账号页迁移

组件库、token 与层叠约定沿用子任务 1（`../11-19-console-ui-kit/design.md`，下文「kit §n」），外壳与组合组件沿用子任务 2（`../11-19-console-ui-shell/design.md`，下文「shell §n」）。本文只写本任务新增或改变的部分。

## 1. 边界

- **改的**：
  - `Accounts.vue` 的工具栏、卡片网格、空状态、分页外观。
  - 账号工作区（概览 / 配置 / 调度 / 环境与诊断）、授权登录弹窗。
  - 子组件：`AgyAccountUsage`、`AgyQuotaRow`、`UsageWindowStats`、`SchedulingDetails`、`ProxyPicker`、`PlatformBadge`、`runtime/ExecutionNodeBadge`。
  - `lib/subscription.ts` 的进度条配色函数。
  - `ModalDialog` 增加页签带插槽；外壳应用栏增加页面操作位。
- **不改的**：
  - 页头（子任务 2 已换）。
  - 账号接口、草稿与保存逻辑、轮询、分页参数。
  - 其它页面主体。
- **跨页影响**：
  - `PlatformBadge`、`ExecutionNodeBadge`、`ProxyPicker` 也出现在请求记录、令牌、运行环境、任务页。换成 token 后这些页面上的徽标与选线弹层一并换新，结构与行为不变。
  - 账号工作区也从代理管理、任务与工程嵌入打开（`workspace-account-id`），改为居中弹窗后这两处同样居中打开。

## 2. 设计基准

| 画面 | 基准 | 说明 |
| --- | --- | --- |
| 工具栏、卡片 | `doc/design/console-v2/mock.html#accounts` | `.tb`、`.seg`、`.card.acc` 及其内部类 |
| 工作区配置页 | `mock.html#account-edit` | `.modal`、`.mh`、页签带、`.mb`、`.sec-t`、`.fg`、`.field`、`.rc`、`.mf` |
| 移动端 | `mock.html#mobile` | `.m-top` 搜索按钮、短标签分段、单列卡片 |

设计稿没有画的部分，按同一视觉语言定义（§4–§6），交用户在截图中目视确认：

- 工作区的概览、调度、环境与诊断页签。
- 授权登录三步。
- 搜索行展开态。
- 卡片的停用、限流、认证错误、反重力形态。
- 390 下的工作区。

## 3. 卡片与工具栏

### 3.1 网格

- `.account-card-grid` 列规则不变：卡片最小 320px，≤760px 单列，≥1680px 四列。
- 间距由 18px 改为设计稿的 16px（`--ui-space-unit` × 4）。
- 1440 宽内容区 1136px，仍为三列。

### 3.2 卡片结构（`Card.account-card`，保留 `data-slot=card`）

账号卡不套用 `EntityCard`：

- 设计稿 `.acc` 与实体卡 `.ent` 的内边距（18/18/6 对 18/20/0）、名称字号（15 对 16）、操作栏尺寸（34px、6/8 内边距对 36px、6/10）都不同。
- 名称区是打开详情的按钮，不能放进实体卡的纯文字标题。
- 既有脚本依赖 `.account-card-topline`、`.account-identity-text h3`、`[data-slot=card]`。

所以卡片用 `Card` 容器加原子组件，布局写在页面样式里。`EntityCard` 的首个真实使用留给节点管理（子任务 4-3）与运行环境（子任务 6）。上级 PRD 中「账号卡五列操作栏在实体卡上扩展」的设想相应取消。

| 区域 | 设计稿 | 实现 |
| --- | --- | --- |
| 头部 `.account-card-topline` | `.acc-head` + `.acc-ctl` 两行 | `.account-card-topline` 改为纵向容器，内含两行（保持 `verify_execution_node_visibility` 的「开关与停用按钮在 topline 内」） |
| 头像 | `.avatar` 40px、圆角 11、右下状态点 | `IconTile size=lg`（Claude Code 用 `primary`，反重力用 `agy`）内放首字母；`.account-avatar-state` 状态点：活跃 `success`、停用 `text-4`、异常 `danger`，2.5px `surface` 描边 |
| 名称 | `.acc-name b` 15 / 760；邮箱 12.5 / 550 `text-3` | `button.account-identity-text` 内 `h3` + `p`；徽标为 `PlatformBadge` 与 `Badge`（套餐，`default`） |
| 控制行 | 「接收请求」+ 开关 + 小号危险按钮，右对齐 | `Switch`（类名保留 `.account-status-switch`，`aria-checked` 仍取 `work_control.api_accepting`，`update:modelValue` 调 `toggleScheduling`）；`Button size=sm`：停用为 `destructive`，启用为 `secondary`，类名保留 `.account-work-toggle` |
| 链接行 `.account-network` | `.links` 12.5 / 600，图标 `text-4` | 代理按钮、`ExecutionNodeBadge`、运行环境链接 |
| 整体状态 | 设计稿未画 | `.account-work-status` 保留，改为 12px `text-3` 文本；「继续停用」为 `Button size=sm variant=secondary` |
| 健康条 `.account-health` | `.strip` | `NoticeStrip`，语义色见 §3.3；「排队 N」为 `end` 插槽中的 `button.account-queue-alert`，外观同 `.tag` 警示色、`surface` 底 |
| 提示段落 | 设计稿未画 | 认证错误 `NoticeStrip tone=danger`；调度错误 `tone=warning`；凭据归属说明 12px `text-3` |
| 路由块 `.account-routing` | `.block.route` 两列 | `EntityBlock`，左「转发方式」，右侧以竖线分隔的「调度优先级」按钮 + 评分 `Badge`（有评分为 `default`，待更新为 `secondary`）；反重力右栏为「调度方式 · 低负载优先」 |
| 用量头 | `.usage-h` + `.since` | 「用量」12 / 700，右侧更新时间 `text-3` 与「刷新」`primary-text` |
| 用量窗口 | `.win`：统计行、标签 + 百分比、6px 进度条、重置时间 | 结构不变，进度条 `data-tone`（§3.4） |
| 实时指标 `.account-live-metrics` | `.metrics` 四列，数值等宽 18px / 800，上边线 | 四个按钮保留；排队大于 0 时数值为 `warning-text`；并发与 RPM 进度条 4px、宽 70%，满载时警示色 |
| 停用 / 限流原因 | 设计稿未画 | `NoticeStrip`：停用 `danger`、限流 `warning`，剩余时间放 `end` |
| 操作栏 `.account-card-actions` | `.acts` 五列 | 原生按钮与 `OperationFeedback` 保留；五列网格、上边线、外扩到卡片边；按钮 34px、`radius-button`、12.5 / 650 `text-2`；悬停 `fill`；删除 `danger-text` |

- 页面样式只取 token；字号不在档位上时用 token 加减像素的 `calc()`（shell §4）。
- 卡片固定元素的高度不随徽标显隐变化（健康条最小高 36px，排队按钮不收缩），满足 `verify_account_queue_layout` 的「排队出现前后卡片盒子不变」。

### 3.3 健康条语义色

新增纯函数 `accountHealthTone(account)`，放在 `Accounts.vue` 内，与 `statusStyle()` 相邻：

| 条件（按顺序判定） | 色调 | 图标 |
| --- | --- | --- |
| `status === 'disabled'` | `neutral` | 圆点 |
| `status === 'error'` 或 `auth_error` | `danger` | `AlertCircle` |
| 限流中、短冷却或 `v3_scheduling_error` | `warning` | `AlertCircle` |
| 其它 | `success` | `Check` |

- 文案逻辑不变。
- 认证错误由现在的警示色改为危险色，`status=error` 由现在的默认绿色改为危险色，这是本次唯一的语义变化（父 PRD「状态条按语义着色」）。
- `statusStyle()` 只保留 `label`，删除未使用的 15 处调色板类。

### 3.4 进度条配色

- `lib/subscription.ts` 的 `usageBarColor(pct): string`（返回 `bg-red-400` 等类）改为 `usageBarTone(pct): 'success' | 'warning' | 'danger'`。阈值不变：≥80 危险，≥50 警示，否则成功。
- 进度条写作 `<i :data-tone="usageBarTone(...)">`，样式按 `data-tone` 取 `success` / `warning` / `danger` 实色。
- 删除 `style.css:242-244` 的重映射。
- `AgyQuotaRow` 同步。
- `tests/subscription.test.mjs` 改为断言新函数。

### 3.5 工具栏（`Toolbar.account-toolbar`）

- **默认插槽**：
  - 平台筛选 `ChoiceSelect.account-platform-filter`，宽 150。
  - 状态分段 `Segmented.account-filter-tabs`，`label="账号状态筛选"`，选项为全部账号 / 正常 / 需要关注 / 已停用，带计数。
- **`end` 插槽**：`SearchInput`，宽 280，防抖与回车逻辑不变。
- **刷新失败提示**：`NoticeStrip tone=warning`（`role=alert` 保留）。
- **分段控件的角色变化**：由按钮组变为 `radiogroup` / `radio`。依赖 `get_by_role('button', name='已停用 1')` 的脚本改为 `radio`；`.account-filter-tabs button` 仍可匹配（reka 的选项元素为 `button`）。

### 3.6 空状态与分页

- 空状态改用 `Empty`（标题「暂无账号」，说明「点击“添加账号”开始」，图标 `users`）。
- `Pagination` 不变。

## 4. 账号工作区（`ModalDialog.account-workspace`）

### 4.1 外框

- **宽度与高度**：固定 820px，四个页签同宽（现为 470 / 860 两档抽屉）。有页签时面板固定高 `min(840px, 100dvh − 32px)`（`.account-workspace:has(> .fui-modal-nav)`），切页签时外框不动；居中弹窗按内容定高会让位置随页签上下跳。新建账号无页签，按内容高。窄屏宽 `min(820px, 100vw − 32px)`。
- **头部**：
  - `media` 插槽：40px 头像（同卡片）。
  - 标题：名称或邮箱，新建为「添加账号」。
  - `title-extra`：平台与套餐徽标。
  - 说明：邮箱。
- **页签带**：新增 `ModalDialog` 的 `nav` 插槽，见 §4.3。
  - 内放 `Segmented.account-workspace-tabs`，`label="账号工作区"`。
  - 「调度」在排队数大于 0 时带计数。
  - 反重力隐藏「调度」；新建账号不渲染页签带。
- **滚动**：内容区是唯一滚动容器，头部、页签带、底栏固定。原来各页签自带的 `.account-workspace-scroll`、`.account-editor-scroll` 不再单独滚动。
  - 类名保留在页签根元素上，供脚本定位。
  - `useActiveScrollbars` 的 `data-active-scroll` 标在 `ModalDialog` 内容区（`.fui-modal-body`）。
- **嵌入**：`workspace-account-id` 模式只渲染工作区、关闭后 `emit('close')`，逻辑不变。

### 4.2 页签内容

| 页签 | 排版 |
| --- | --- |
| 概览 | 上下文徽标行；用量区（同卡片窗口）或反重力平台额度（`expanded`）与「平台能力」`EntityBlock`；「请求配置」三格为 `EntityBlock` 内三列键值；「测试连接」「刷新用量」为 `secondary` 按钮；「账号控制」为分区标题 + `InfoTooltip`，控制行用 `Switch` 与小号按钮 |
| 配置 | 表单 `form#account-editor-form`。分区标题 `.sec-t` 14 / 760。字段网格两列，并发 / RPM / 优先级行三列（`.fg.c3`）；字段标签 12 / 700 `text-2`，说明 12 / 500 `text-3`。转发方式用 `RadioCardGroup`（`name="request_backend"`，标题加说明：原生运行时 / 现有转发通道），其余控件不变。复选项改用 `Checkbox`。「认证与高级配置」等 `details` 保留，摘要行为分区标题样式 |
| 调度 | `SchedulingDetails embedded`，见 §5 |
| 环境与诊断 | 四项摘要为 `EntityBlock` 内两列键值；错误为 `NoticeStrip tone=danger`；三个跳转为 `secondary` 按钮；「技术与调度详情」`details` 内的五格 / 三格指标改为键值网格，去掉大写字距工具类 |

- **配置页底栏**：只在配置页渲染（`<template v-if #footer>`）。
  - 内容：「修改后统一保存」12 / 600 `text-3`，「取消」`secondary`，「保存修改 / 保存中…」主按钮。
  - 主按钮 `type=submit form="account-editor-form"`，因为底栏在表单元素之外。
- **新建账号**：直接显示配置页，底栏相同。
- **编辑时的平台**：仍是禁用的 `ChoiceSelect`（读屏为禁用组合框），外观按设计稿只读输入（`fill-muted` 底、`text-3`，不半透明）；设计稿的锁图标不画。

### 4.3 `ModalDialog` 扩展

- 新增 `nav` 插槽：渲染为 `div.fui-modal-nav`，位于头部与内容区之间、不随内容滚动。
- `.fui-modal-title` 允许换行：窄屏时 `title-extra` 的徽标整体换到下一行，标题文字不被挤断（调用方把多个徽标包成一组）。
- `SegmentedOption.count` 放宽为 `number | string`，计数未知时显示「—」（与现状一致）。
  - 内边距 0 / 24 / 18（设计稿 `#account-edit` 页签带）。
  - 窄屏时分段控件可横向滚动，规则同 `.fui-toolbar > .fui-segmented`。
- 演示页 `CompositeShowcase.vue` 的弹窗示例加页签带。
- `verify_ui_kit.py` 增加页签带的比对对。

## 5. 子组件

| 组件 | 改动 |
| --- | --- |
| `PlatformBadge` | 改为 `Badge`：Claude Code 为 `cc`，反重力为 `agy`，未知为 `secondary`；保留 `data-platform-badge` 与文案；删除 scoped 十六进制 |
| `ExecutionNodeBadge` | 去掉 `var(--x, #hex)` 回退，改取 `--ui-*` token；结构不变 |
| `UsageWindowStats` | 统计行 12 / 550 `text-3`、单行省略；费用气泡沿用 `InfoTooltip` 外观，内部 `dl` 网格取 token，删除 `approved-design.css` 中气泡的十六进制覆盖 |
| `AgyAccountUsage` / `AgyQuotaRow` | 标题同「用量」头；额度行同用量窗口；进度条 `data-tone` |
| `SchedulingDetails` | 4 个指标卡改为 `EntityBlock`；阶段条与因子条用语义色 token；SVG 时间轴的描边与填充改为 `stroke: var(--ui-color-…)`（通过类名）；会话表改用 `Table` 组件；去掉 `rounded-*` 与调色板类 |
| `ProxyPicker` | 触发器外观同 `ChoiceSelect`（填充底、控件圆角、单行：名称加粗 + 地址或提示），弹层同下拉弹层（`surface`、`shadow-pop`、`radius-block`）；帮助文字移到触发器下方（设计稿 `.field .help`）；搜索、分批、加载更多与迟到隔离逻辑不变。请求记录的账号筛选弹层复用 `.proxy-picker-popup/options`，随之换新 |

## 6. 移动端（≤760px）

- **应用栏搜索按钮**：
  - `Dashboard.vue` 把菜单按钮包进 `.console-toolbar-actions`（右对齐、间距 6px，设计稿 `.m-top .r`），其前放空容器 `#console-toolbar-page-actions`（`display: contents`）。
  - `Accounts.vue` 用 `<Teleport defer to="#console-toolbar-page-actions">` 放入 36px 图标按钮 `.console-toolbar-action.account-search-toggle`（`search`，aria 名称「搜索账号」，`aria-expanded`、`aria-controls`），样式同菜单按钮，展开时主色浅底。
  - 嵌入模式不渲染；桌面由样式隐藏。
  - 页面操作由页面自己声明，外壳不感知业务，其它页面以后可复用同一容器。
- **搜索行**：点按钮展开，内含平台筛选与搜索框，同一行，搜索框占满余宽。展开时聚焦搜索框。
  - 搜索词非空或平台不是「全部平台」时保持展开，避免隐藏生效中的筛选。
  - 桌面上搜索行即工具栏本身，不受开关影响。
- **分段**：`useMediaQuery('(max-width: 760px)')` 为真时换用短标签：全部 / 正常 / 关注 / 已停用（读屏名称随之变化）。分段独占一行，超出时横向滚动。
- **卡片**：单列。指标仍四列（390 宽下每列约 80px，数值 18px 足够）；操作栏五列（每列约 70px），文字 12px 时不溢出。若实测溢出，改为只显示图标并保留 aria 名称，截图确认。
- **工作区**：宽 `100vw − 32px`；字段网格单列；单选卡纵向排列；页签带横向滚动。
- **授权登录**：宽 `min(440px, 100vw − 32px)`，沿用现有窄屏内边距。

## 7. 授权登录弹窗

- 改用 `ModalDialog`，宽 440，保留类名 `.account-oauth-dialog.approved-oauth-dialog`（`verify_interaction_parity` 断言宽 440）。
- 三步内容不变；每步原来的 `.oauth-context` 说明改作弹窗描述（「将账号接入工作空间」「完成浏览器授权后，填写返回的授权码」「授权成功」），底栏按钮经 `form="account-oauth-step"` 提交当前步骤。
  - 第一步：标签与说明为 `.field` 形态；`ProxyPicker` 同 §5。
  - 第二步：链接面板为 `EntityBlock`，含打开与复制按钮；授权码为 `Textarea`。
  - 第三步：成功提示为 `NoticeStrip tone=success`，结果键值为 `EntityBlock`。
- 错误用 `NoticeStrip tone=danger`。
- 底栏按钮放 `footer` 插槽，文案与条件不变。

## 8. CSS 组织

- **新文件** `apps/web/src/accounts.css`：
  - `@layer components`，只取 token。
  - 由 `Accounts.vue` 引入，随账号页的 chunk 加载。代理与任务页嵌入工作区时同样会引入。
  - 加入 `theme.test.mjs` 的 token-only 检查列表。
  - 子组件的少量样式（`SchedulingDetails` SVG 类、`ProxyPicker`）也写在这里，因为它们只在账号页与工作区出现。
  - 例外：`ProxyPicker` 在任务页也被使用，任务页不一定加载账号 chunk，所以它的样式写进 `kit.css` 的 `@layer components`，作为复用控件。
- **删除的旧规则**（未分层，会压过新样式）：
  - `style.css`：
    - 账号相关约 248 条：155-234、242-260、262-309、311-362、371、373-380 中账号与 ProxyPicker 部分、381-395。
    - 含 29 个 `!important`，以及 7 个死选择器：`.account-configuration`、`.account-editor-dialog`、`.account-detail-dialog`、`.form-section-title`、`.account-overview-identity`、`.usage-stats-values`、`.schedule-section`。
  - `approved-design.css`：4-65、129-166 中账号部分、181-194、206-264，约 161 条。
  - `kit.css` 末尾针对账号的未分层覆盖（`.account-toolbar .fui-search` 等）。
- **删除前检查**：
  - 每条规则先 grep 选择器，确认只服务账号页及其子组件。
  - 与代理、令牌、任务页共用的规则留到对应子任务，例如 `approved-design.css` 中 `.proxy-*`、`AccountScopePicker` 的部分。
  - `style.css:137-142` 的 `.resource-grid`、全局弹窗高度与 `[data-slot=card]` 规则其它页面仍在用，本任务不删，只在 `accounts.css` 中用更具体的选择器处理冲突。
- **`Accounts.vue` 模板**：
  - 去掉调色板类、`rounded-*`、`uppercase tracking-wider`、`text-muted-foreground` 等外观工具类，改为语义类名。
  - 布局类（`flex`、`grid`、`gap`）在不影响一致性时可保留。

## 9. 验证

1. **`node:test`**：
   - `subscription.test.mjs` 改为 `usageBarTone`。
   - `theme.test.mjs` 检查列表加入 `accounts.css`，并加入改动的子组件。
2. **`verify_ui_kit.py`**：`ModalDialog` 页签带与 `mock.html#account-edit` 比对。
3. **新增 `deploy/flower2api/verify_account_page_design.py`**：
   - 运行方式：真实构建加 `AccountDesignFixture`，与 `verify_ui_shell.py` 同构。
   - 1440×900：
     - 工具栏、分段、搜索框、卡片各区（头部、控制行、链接行、健康条、路由块、用量头与窗口、指标、操作栏）对 `mock.html#accounts` 逐项比对计算样式。
     - 网格三列、间距 16。
     - **首行三张卡片的操作栏底边不超过 900**。
   - 工作区：
     - 打开编辑：外框 820 居中，头部、页签带、分区标题、字段、单选卡、底栏对 `#account-edit` 比对。
     - 四个页签切换时宽度不变、只有内容区滚动。
     - 反重力无「调度」，新建无页签带。
   - 健康条四种色调：正常、限流、认证错误、停用，取对应 token。
   - 390×844：
     - 应用栏搜索按钮比对 `#mobile` 的 `.m-top .r span`。
     - 点击展开搜索行并聚焦，输入后完成搜索；有搜索词时收起按钮不隐藏搜索行。
     - 短标签分段、单列卡片、无横向溢出；工作区单列。
     - 其它页面应用栏无搜索按钮。
   - 白名单：结构写法不同但视觉等价处注明原因。
   - 截图：1440 / 390 各态存 `.deploy/console-ui-revamp/accounts/`（git 忽略），供目视确认未画的画面。
   - 全程零控制台错误。
4. **既有脚本**：
   - 规则同前：样式采样移到新基准，行为断言不放宽；基线已失败的脚本失败点须不变。

   | 脚本 | 处理 |
   | --- | --- |
   | `verify_exact_design.py` | 账号采样（筛选、名称、邮箱、卡片、操作栏、用量标签、名称字体）移到新脚本。剩余只有 `html` 根字号与三档无溢出，已由 `verify_console_ui.py` 覆盖，删除脚本并从回归集移除 |
   | `verify_design_parity.py` | 分区标题与页签文字断言保留（页签按标签文字，不含计数）；抽屉 x 与宽度改为居中 820；`.forwarding-options` 两个 radio 改为单选卡的两个 `radio`；其余行为不变 |
   | `verify_ui_refinements.py` | 网格列数改为按 §3.1 规则逐档断言，不再取旧原型；费用气泡改为断言 `InfoTooltip` 的 token 外观与 4 格内容；悬停改为断言卡片操作取 `fill` 底与正文色、调度优先级箭头取 `primary-text`。失败点（OAuth 载荷，基线即失败）不变，行号 54→61 |
   | `verify_diagnostic_alignment.py` | 诊断页签不再比对旧原型（设计稿未画），保留无溢出与代理页写死值断言，诊断页由新脚本截图确认 |
   | `verify_accounts_design.py` | `input[type=radio][value=native293]` 改为单选卡的选中态；`.account-editor-scroll` 的滚动断言改到弹窗内容区；其余不变 |
   | `verify_account_filters_ui.py` | 状态按钮角色改为 `radio`；≤760（720、390）先断言搜索行收起，点搜索按钮后断言聚焦、平台与搜索同行、分段独占一行，再收起；其余不变 |
   | `verify_agy_accounts_ui.py` | 进度条两个 `rgb` 期望改为 `danger` / `warning` token 实际值 |
   | `verify_viewport_interactions.py` | 无需改动（分段选项仍为 `button` 元素） |
   | `verify_shared_pagination.py`、`verify_page_sizes.py`、`verify_diagnostic_alignment.py` 等 | 工作区页签由 `button` 角色改为 `radio`；`verify_page_sizes.py` 基线即停在 L38（夹具漂移），失败点不变 |
   | `verify_workspace_stability.py` | 页签改 `radio`；标题断言改为以账号名开头（`title-extra` 徽标在 `DialogTitle` 内） |
   | `verify_frontend_navigation.py` | 卡片选择器改为 `.account-card-grid > [data-slot=card]`，页签改 `radio`；基线失败点（任务页 `#theme-toggle`）不变，行号 104→105 |
   | `verify_console_ui.py`、`verify_execution_node_visibility.py`、`verify_scheduling_preferences.py`、`verify_interaction_parity.py`、`verify_proxy_design.py` | 类名契约保留，无需改动 |
   | `verify_account_queue_layout.py` | 无需改动；首轮发现排队提示让状态条高 4px，已在样式中把状态条固定为 36px 修正 |
   | `audit_full_design.py` | 只存证不断言，账号用例差异数会变，不改 |
   | `verify_forwarding.py` | 真实栈本机不跑；用到的 `.account-identity-text h3`、`.account-workspace-tabs button`、`.account-diagnostic-technical`、弹窗关闭按钮均保留 |

5. **回归集**：子任务 1 的 37 个加集合外 26 个。先在当前 HEAD 跑基线，改动后逐项对照；`verify_exact_design` 删除后从回归集移除并在笔记中注明。

## 10. 规范同步

`.trellis/spec/web/frontend/ui-guidelines.md`：

- 「定稿响应式及字体根合同」：卡片间距 16。
- 「布局与信息组织」：账号工作区为 820 居中弹窗，页签带固定。
- 「正式控制台与账号首批迁移」：健康条四种语义色、进度条 `usageBarTone`、验证入口加新脚本。
- 组合组件表：`ModalDialog` 的 `nav` 插槽；外壳应用栏的页面操作位 `#console-toolbar-actions`。

## 11. 发布与回滚

- 单独提交、单独发版。不改后端、网关与运行时桥接。
- 回滚即回退本任务提交。
- 子任务 4-2、4-3 若复用了 `ModalDialog` 页签带或应用栏操作位，需一并回退。
