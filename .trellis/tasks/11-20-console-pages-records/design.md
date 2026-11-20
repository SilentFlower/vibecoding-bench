# 技术设计：请求记录、代理、令牌与会话封禁页迁移

组件库、token 与层叠约定沿用子任务 1（`../11-19-console-ui-kit/design.md`），外壳与组合组件沿用子任务 2（`../11-19-console-ui-shell/design.md`），弹窗页签带与应用栏页面操作位沿用 4-1（`../11-20-console-pages-accounts/design.md`，下文「accounts §n」）。本文只写本任务新增或改变的部分。

## 1. 边界

- **改的**：
  - 前端四页：`RequestDiagnostics.vue`、`Proxies.vue`、`Tokens.vue`、`SessionPolicyBlocks.vue` 的概览、表格卡片、表格、空状态与弹窗。
  - 页内子组件：`NativeStageDetails.vue`（请求详情「原始数据」页签）、`AccountScopePicker.vue`（令牌编辑）。
  - 组件库扩展（§2）：`OverviewCard` 可点击形态、`TableCard` 无标题头部、`IconTile` 小号、表格单元格工具类、`ModalDialog` 靠右摆放与说明插槽。
  - 网关两处只读计数（§8）与前端 `api.ts` 类型。
- **不改的**：
  - 页头（子任务 2 已换）。
  - 四页的查询参数、轮询、分页、复制、保存、删除、解除、批量检测、导入与识别逻辑。
  - 接口旧字段与筛选语义；数据库表结构与迁移（`*_schema.rs` 一律不动，迁移登记存有源码摘要）。
- **跨页影响**：
  - 组件库扩展只增加可选能力，默认行为不变；`verify_ui_kit.py` 与演示页同步。
  - `PlatformBadge`、`ExecutionNodeBadge`、`ProxyPicker` 已在 4-1 换好，本任务只使用不改。
  - `AccountFilterSelect` 的弹层样式在 `kit.css`（`.proxy-picker-*`、`.account-proxy-picker`），清理 `proxy-*` 旧规则时保留。
  - 代理页内嵌账号工作区不变；`Proxies.vue` 用 `tr[data-proxy-id]`、`.proxy-expanded`、`.proxy-expand` 恢复焦点，这三个钩子保留。

### 1.1 定位契约（保留）

沿用 4-1「类名契约保留」的做法：以下类名、属性与无障碍名称被组件逻辑或既有脚本依赖，迁移后挂在对应的新元素上，样式另写，不作为样式钩子以外的约束。

| 页 | 保留项 |
| --- | --- |
| 请求记录 | `.request-records`（表头 9 个 `th`，详情关闭时页面只有一个 `tbody`）、`.request-extra`、`tbody [data-cache-write]`、`tbody [data-average-tps]`、`.request-account-identity`（内容恰为账号名，辅助行放在它外面）、`.request-account-name`、`.request-empty`、`#request-filters`；按钮名「刷新」「查询」「筛选」「详情」「复制请求 {id}」「复制原始 Session ID {id}」；分页名「请求记录分页」 |
| 请求详情 | 抽屉面板 `.request-workspace`（性能页 `InfoTooltip` 的 `portal-target`、复制回退的 `[role=dialog]` 宿主依赖它）、`request-tab-*` / `request-panel-*` 与 `tablist / tab / tabpanel` 语义、`data-request-copy`、`.request-definitions`、`.request-attempt-summary`、`.request-chain-card`（`dl/dt/dd` 结构）、`.request-performance-card`、`.request-token-metrics`、`[data-native-runtime] .request-runtime-metrics`、`[data-gemini-usage]`、`NativeStageDetails` 的类与 `data-native-stages`；按钮名「查看链路」「阶段证据」「读取阶段证据」「查看入站请求」「复制完整请求 ID」 |
| 代理管理 | `.proxy-page`、`.proxy-panel`、`tr[data-proxy-id]`、`.proxy-row-actions`、`.proxy-user-chips`、`.proxy-expand`、`.proxy-expanded`、`.proxy-account-identity`、`.proxy-editor`、`.proxy-recognize`；按钮名「查看使用账号 / 收起账号」「保存代理」「确认删除」；分页名「代理列表分页」 |
| 访问令牌 | `.token-row`（挂在表格行上）、`.approved-token-editor`、`.token-name`；按钮名「编辑权限」「保存权限」；页面不出现 `.account-search-toggle`。底栏改为 `ModalDialog` 通栏 `.fui-modal-foot`，`verify_tokens_design.py` 按名称定位取消与保存 |
| 会话封禁 | `.session-block-panel`、`.session-block-records[aria-busy]`、`.session-block-empty`、`tr[data-block-id]`；搜索框名「搜索会话」；分页名「会话封禁分页」 |

## 2. 组件库扩展

| 组件 | 扩展 | 默认行为 |
| --- | --- | --- |
| `OverviewCard` | 新增 `interactive?: boolean`：根元素改为 `button type=button`，内部结构不变；有悬停底色、`primary-ring` 聚焦环与禁用态；`disabled` 透传。点击事件由调用方处理。 | 仍为 `article` |
| `TableCard` | `title` 改为可选。省略时不渲染 `h3`，工具栏占满头部（`flex:1`），供「分段在最左」的头部使用；有标题时布局不变。 | 不变 |
| `IconTile` | `size` 增加 `sm`：32×32、圆角 `calc(var(--ui-radius-block) - 3px)`、图标 14px（设计稿表格内图标块）。 | md |
| 表格工具类（kit.css） | `.fui-table-fixed`（`table-layout:fixed`）、`.fui-table-num`（等宽数字）、`.fui-table-mono`、`.fui-table-strong`（700）；单元格主值超长省略、`.fui-table-sub` 已有。 | 无 |
| `ModalDialog` | 新增 `placement?: 'center' \| 'side'`：`side` 时贴右、上下右各留 14px、占满视口高，宽度取 `min(width, 100vw - 28px)`；头部、页签带、内容区、底栏结构不变。新增 `description` 插槽（存在时替代 `description` 属性文字）。 | center |

演示页 `previews/` 补对应示例，`verify_ui_kit.py` 增加比对对：可点击概览卡、无标题表格卡片头部、32px 图标块、靠右弹窗外框。

## 3. 设计基准

| 画面 | 基准 | 说明 |
| --- | --- | --- |
| 请求记录列表 | `mock.html#requests` | `.grid.g4 .ov`、`.tcard`、`.tcard-h`、`.seg`、`.t`、`.sub`、`.tfoot` |
| 代理管理列表 | `mock.html#proxies` | 同上，另有 `.tile` 32/9 与延迟、到期着色 |
| 访问令牌列表 | `mock.html#tokens` | `.tcard` 标题 + 计数、`.switch` |
| 会话封禁列表 | `mock.html#blocks` | `.tcard-h` 分段 + 搜索 + 说明 |

设计稿没有画的部分按同一视觉语言定义（§4–§7），交用户在截图中目视确认：请求详情四个页签、请求筛选展开、代理展开使用账号、代理编辑与批量导入、令牌编辑、空状态与读取失败、四页 390 形态。

设计稿与现有信息不一致处，以「信息结构与业务行为不变」为准：

- 请求列表保留平台徽标、执行节点徽标、缓存写与平均 TPS（`ui-guidelines.md` 请求列表与诊断详情的规定），Token 列因此有两行辅助值。
- 代理延迟着色阈值沿用现有 120ms（设计稿示例为 150ms），代理列表保留分页、检测时间与处理中请求数。
- 会话封禁保留四种状态（设计稿只画三种），说明文字保留「重复拦截保持原到期时间」。
- 请求列表原「N 条匹配记录 · 本页成功 · 本页错误 · 保留 7 天」摘要行由概览卡与分页「共 N 条」替代，不再单独显示本页成功 / 错误数。

## 4. 请求记录（`RequestDiagnostics.vue`）

### 4.1 概览卡（`OverviewGrid`）

| 卡 | 数值 | 说明 | 图标 / 色调 |
| --- | --- | --- | --- |
| 全部记录 | `counts.all` | 保留 7 天 | activity / primary |
| 错误 | `counts.errors` | 六类错误集合 | alert / danger |
| 处理中 | `counts.processing` | 按当前筛选统计 | clock / info |
| 后续请求日志 | `info · 摘要` / `debug · 脱敏内容` / `读取中` | 仅影响后续请求 · 点击切换；保存中显示「保存中…」 | sliders / warning |

- 计数缺失（`counts` 为 null）显示「—」，与现有分段一致。
- 第 4 张卡用 `interactive`：点击调用现有 `saveMode()`，在 info / debug 间切换；`mode==='unknown'` 或保存中禁用。数值字号 `--ui-font-size-heading`（设计稿 20px）。无障碍名称写明当前值与切换目标，例如「后续请求日志：info · 摘要，点击切换为 debug · 脱敏内容」。
- 页头 `actions` 里的日志下拉删除；读取或保存失败的 `modeError` 改为概览下方 `NoticeStrip tone=danger role=alert`。
- 采集健康 `health` 有非零项时，在表格卡片上方显示 `NoticeStrip tone=warning role=status`，文字不变。

### 4.2 表格卡片（`TableCard.request-records`，无标题）

- 头部（`Toolbar` 排列）：
  - 左：`Segmented`（label「请求快捷筛选」，全部 / 错误 / 处理中带计数）。选了「具体结果」筛选时，分段值为空（无选中项），与现有「快捷与具体结果同一维度」一致。
  - 右：`SearchInput`（label「请求关联 ID」，宽 380）、「筛选」按钮（`aria-expanded`、`aria-controls=request-filters`，有生效条件时带圆点）、「查询」主按钮、刷新图标按钮（`aria-label=刷新`）。
- 筛选区 `#request-filters`：头部下方展开，字段与顺序不变（账号、平台、协议、内核版本、请求模型、实际模型、具体结果、开始 / 结束时间），三列网格；底部说明与「重置条件」保留。列表读取错误改为卡片内 `NoticeStrip tone=danger`。
- 表格：`Table.fui-table-fixed`，列宽写在 `TableHead` 的宽度类上。账号列要完整放下平台与执行节点徽标（`verify_execution_node_visibility.py` 断言徽标不截断），由设计稿 15 / 10 / 15 / 13 / 10 / 16 / 5 / 9 / 7 调为 15 / 13 / 13 / 13 / 10 / 15 / 5 / 9 / 7（%），徽标放不下时换到第二行，单元格上下留 8px。

| 列 | 主值 | 辅助值 |
| --- | --- | --- |
| 时间 / 请求 | 本地时间（`fui-table-num`，省略时区） | 等宽短 ID + 复制图标按钮 + 日志模式中性徽标 |
| 账号 | 账号名（`fui-table-strong`，`InfoTooltip` 触发器不变） | `PlatformBadge` + `ExecutionNodeBadge compact` |
| 模型 / 转发方式 | 模型 | 转发方式 · 版本 |
| 结果 | 结果徽标（带圆点，点击打开详情）+ 等宽状态码 | — |
| 总耗时 / 首输出 | 总耗时（strong） | 首输出 |
| Token（末次） | 输入 / 输出 | 第一行「缓存读 · 写」（写带 `data-cache-write`），第二行平均 TPS（`data-average-tps`） |
| 尝试 | 次数（右对齐） | — |
| 原始 Session ID | 等宽值 + 复制按钮；缺失为 text-4「未提供」 | — |
| 操作 | 「详情 →」小号文字按钮（`fui-table-actions`） | — |

- 结果色调：`success`、`cache_hit` 为 success；`in_progress` 为 info；其余为 danger（沿用 `outcomeTone` 三分法，只换成 `Badge` 变体）。
- 空状态：`TableEmpty` 内放 `Empty`（图标、标题、说明、「重置查询」），文字不变。
- 底部：左侧说明「模型、节点、Token、首输出取末次尝试；总耗时按请求起止时间计算。」，右侧 `Pagination`（label「请求记录分页」）。

### 4.3 请求详情（`ModalDialog placement=side width=1020`，保留右侧抽屉）

- 外框：贴右全高，宽 `min(1020px, 100vw - 28px)`，头部、页签带固定，内容区唯一滚动；关闭后焦点回到打开它的按钮（`close-auto-focus` 处理不变）。
- 头部：标题「请求详情」，`description` 插槽放完整请求 ID（等宽）与复制按钮（保留 `data-request-copy`）；`media` 放请求图标块。
- 页签带（`nav` 插槽）：保留现有手写 `tablist / tab / tabpanel`、`request-tab-*` / `request-panel-*` 关联与 `tabKeys` 方向键切换，外观借用 `.fui-segmented` / `.fui-segmented-item[data-state]` 的胶囊托盘（选中项 surface 底 + 阴影）。不换成 `Segmented`：详情是真正的页签面板，`tab` 语义更准确，且 6 个脚本约 27 处按 `tab` / `tabpanel` 定位。
- 页签内容（字段与条件渲染逐项不变，只换外观）：
  - 概览：结果徽标 + 账号 + 总耗时的摘要块；错误阶段与发送前拒绝改为 `NoticeStrip tone=danger`（拒绝条内保留「查看入站请求」）；定义列表两列网格；上游尝试为 `EntityBlock` 式行（序号块、账号、模型、采集状态、执行节点、三个操作）。
  - 请求链路：每次尝试一张块卡，头部序号 + 账号 + 结果徽标，下方定义列表。
  - 性能：每次尝试一张块卡，四格耗时指标、原生进程区、Token 指标、Gemini 用量与原始用量折叠块。
  - 原始数据：尝试选择 + 读取按钮；不可读取时 `Empty`；阶段证据交给 `NativeStageDetails`（其「原文阶段」按钮组保留 `role=group` + `aria-pressed`，只换外观）；脱敏字段折叠块。
- 旧 `.btn` / `.btn.small` 换 `Button`（outline，sm）；「内容采集设置」保留为文字链接（`router-link.request-text-button`，token 样式）；「前往该账号环境配置」用 `Button` 的 `as-child` 包裹 `router-link`。
- `NativeStageDetails` 的类（`request-stages`、`request-header-*`、`request-evidence-*`、`request-wire-content`、`request-stage-tabs`、`request-definitions`、`request-section*`、`request-code-block`、`request-empty-capture`）类名保留、规则改写为 token，随请求页样式一起放进新文件；`text-amber-700` 换成 token 类。

### 4.4 390 形态

- 概览卡按 kit 断点降列。表格卡片头部：分段独占一行（可横向滚动），搜索框独占一行，按钮一行。
- 表格只保留时间、账号、结果、操作四列（现有 `request-extra` 折叠规则），不出现页面横向滚动。
- 详情抽屉铺满视口宽（左右各 14px），页签带可横向滚动。

## 5. 代理管理（`Proxies.vue`）

### 5.1 概览卡

| 卡 | 数值 | 说明 | 图标 / 色调 |
| --- | --- | --- | --- |
| 代理 | `counts.all` | 条线路 | globe / primary |
| 可用 | `counts.available`，单位「/ all」 | 出口信息来自最近一次检测 | check / success |
| 被使用 | `counts.used`（null 显示「—」） | 条线路有账号绑定；引用不完整时为「部分使用情况待核对」 | users / info |
| 7 天内到期 | `counts.expiring` | `counts.expired > 0` 时「另有 N 条已过期」，否则「暂无已过期线路」 | calendar / warning |

- 字段缺失（旧网关）时数值显示「—」、说明不写数字，不用当前页推算。
- 现有摘要行 `.proxy-summary` 删除，「部分使用情况待核对」并入第 3 张卡说明。

### 5.2 表格卡片（`TableCard.proxy-panel`，标题「代理线路」，计数「total / all 条」）

- 工具栏：`SearchInput`（label「搜索代理」，宽 300，防抖查询不变）、「批量检测」按钮。
- 批量检测进度：卡片内 `NoticeStrip tone=info role=status`，末尾「停止后续检测」。读取错误：`NoticeStrip tone=danger role=alert`，末尾「重试」。
- 表格列宽由设计稿 20 / 13 / 9 / 9 / 14 / 13 / 22 调为 16 / 13 / 9 / 9 / 13 / 20 / 20（%），给使用情况列放下使用者、处理中请求数与展开按钮：

| 列 | 主值 | 辅助值 |
| --- | --- | --- |
| 代理线路 | `IconTile size=sm`（globe）+ 名称（strong） | 等宽公开地址 |
| 出口 IP / 地区 | 等宽 IP（缺失「—」） | 国家代码（strong）+ 地区；非可用状态加「上次成功结果」；未检测为「等待检测」 |
| 检测延迟 | 等宽 16px 数值 + text-4「ms」；>120 为 warning-text，有值为 success-text，缺失为 text-4 | 最近检测时刻（悬停提示「最近检测时间」）/ 尚未检测 |
| 连接状态 | 带圆点徽标：可用 success、检测失败 danger、待检测 neutral、检测中 info（带旋转图标） | — |
| 到期时间 | 徽标：已过期 danger、7 天内 warning、其余与未设置 neutral | 本地日期 |
| 账号使用情况 | 「N 个使用 · M 个活跃」+ 右侧展开图标按钮（无障碍名称「查看使用账号 / 收起账号」，类 `.proxy-expand`） | 前两位使用者（网关账号为按钮）+「+N」· K 个处理中（无使用者时「暂无账号」）；全文放悬停提示 |
| 操作 | 同步中徽标（info）+「检测」「编辑」（outline sm）+「删除」（destructive-ghost sm） | — |

- 展开行 `tr.proxy-expanded`：整行块区，标题与说明不变，使用账号以 `EntityBlock` 式网格排列（头像、名称、类型 · ID、状态徽标、处理中请求数、账号配置入口）。
- 底部：左侧说明「检测延迟为经该代理访问出口观测服务的往返耗时；到期提醒用于维护管理。」，右侧 `Pagination`（label「代理列表分页」）。
- 删除 `Proxies.vue:186` 的 `text-amber-700`。

### 5.3 弹窗

- 代理编辑：`ModalDialog.proxy-editor`（宽 680，沿用现值，`form#proxy-editor-form`，底栏按钮用 `form` 属性提交）。一键识别、同步提示（`NoticeStrip`）、两列字段、替换认证 `Checkbox`、到期时间与快速延长、底栏说明文字不变。
- 批量导入：`ModalDialog.proxy-import-dialog`（宽 520），文本框与错误提示不变。
- 删除确认：`ConfirmationDialog` 不变。

### 5.4 390 形态

隐藏出口、延迟、使用情况、状态列，只留线路、到期、操作（52 / 30 / 18%）；线路图标块隐藏、地址单行省略，状态徽标移到线路名称下方（桌面隐藏，与状态列不会同时出现）；操作按钮纵向排列、只显示图标，文字保留给读屏。线路名称下方还显示可点击的使用摘要「N 个使用 · M 个活跃 · K 个处理中」（`.proxy-mobile-usage`，`aria-expanded`，无障碍名称以「查看使用账号 / 收起账号」开头），作为窄屏的展开入口；使用账号从展开行打开。展开行单列。账号工作区关闭后焦点回到当前可见的展开入口。

## 6. 访问令牌（`Tokens.vue`）

- 无概览卡。`TableCard.token-panel`：标题「访问令牌」，计数「N 个令牌」（搜索时「m / N 个令牌」）。
- 工具栏：`SearchInput`（label「搜索令牌」，placeholder「搜索令牌名称」，宽 260）。在已读取的全部令牌中按名称过滤（去首尾空格、不区分大小写；未命名令牌按「未命名令牌」匹配），不发请求、不改分页读取。
- 读取失败：卡片上方 `NoticeStrip tone=danger`，末尾「重试」。
- 表格 `colgroup` 20 / 20 / 20 / 11 / 10 / 19（%），行为 `tr.token-row`：

| 列 | 内容 |
| --- | --- |
| 名称 | `IconTile size=sm`（key）+ 名称（strong），缺失为「未命名令牌」 |
| 令牌 | 等宽遮蔽值 + 中性小按钮「复制 / 已复制」（复制逻辑不变） |
| 可用账号 | 「全部可用账号」或「仅允许 …」，有排除时追加「 · 排除 …」，超长省略、`title` 显示全文 |
| 创建时间 | `created_at` 本地日期 yyyy/mm/dd（text-3，等宽） |
| 状态 | `Switch`（无障碍名称「{名称}启用状态」）+「启用 / 停用」文字，停用为 text-3 |
| 操作 | 「编辑权限」（outline sm）、「删除」（destructive-ghost sm） |

- 空状态：`Empty`，读取中「正在读取令牌…」、无令牌「还没有令牌，可创建客户端凭据。」、搜索无结果「没有匹配的令牌」。
- 令牌编辑：`ModalDialog.approved-token-editor`（宽 760，沿用现值，`form#token-editor-form`，底栏 `.token-editor-footer`）；名称输入、账号范围读取错误与重试、两个 `AccountScopePicker` 不变。`AccountScopePicker` 样式改写为 token，加入 token-only 检查。
- 390：隐藏可用账号、创建时间列。

## 7. 会话封禁（`SessionPolicyBlocks.vue`）

- 无概览卡。`TableCard.session-block-panel`（无标题，`form` 包住头部以保留回车查询）：
  - `Segmented`（label「封禁状态」）：封禁中 / 已到期 / 已解除 / 全部记录，计数取接口 `counts.active / expired / released / all`，缺失为「—」。切换仍触发 `load(1)`。
  - `SearchInput`（label「搜索会话」，宽 320）、「查询」主按钮、「刷新」按钮。
  - 末尾说明（text-3，sm）：「时间按本地时区显示 · 每 5 秒刷新 · 重复拦截保持原到期时间」，空间不足时换到第二行。页面其它位置不再重复。
- 读取失败：卡片内 `NoticeStrip tone=danger`，保留「当前保留上次读取结果」与「重试」。
- 表格 `colgroup` 24 / 15 / 19 / 15 / 15 / 12（%），行保留 `data-block-id`：

| 列 | 主值 | 辅助值 |
| --- | --- | --- |
| 会话 / 触发来源 | 等宽前 12 位（`InfoTooltip` 显示完整标识） | 原因 · 模型 |
| 访问令牌 / 账号 | 令牌名（默认调用域 / 访问令牌 N） | 账号 |
| 封禁状态 | 带圆点徽标：封禁中 danger、已到期 neutral、已解除 success | 剩余时间 +「到期时间」提示触发器 |
| 封禁时间 | 本地时间（num，省略时区后缀，时区只在工具栏说明） | — |
| 本地拦截 | 「N 次」（strong） | 最近一次时间 |
| 操作 | 「关联请求」「解除封禁」（outline sm），都没有时「—」 | — |

- 空状态：`Empty`，四种文案与「重置查询」不变。
- 390：隐藏令牌、封禁时间、本地拦截列，首列与状态列显示移动端补充行（现有 `block-mobile-source` 语义）。

## 8. 网关计数

### 8.1 代理目录 `counts`

- `proxy_store::summary_index` 改为 `SELECT connection,status,COALESCE(expires_at,'') AS expires_at`，返回 `(connection, status, Option<String>)`，空串经 `optional_text` 还原为 `None`。
- `handler::proxies::directory_counts(index, refs, now: DateTime<Utc>)`：在内存中用 `DateTime::parse_from_rfc3339` 解析：
  - `expired`：`t <= now`。
  - `expiring`：`now < t < now + 7 天`（严格小于，与前端 `soon` 判定一致）。
  - 未设置或解析失败不计入。
  - 两项不受引用完整性影响；`used` 仍在引用不完整时为 null。
- `list` 开头取一次 `Utc::now()` 传入；`usage=false` 分支不变，`counts` 仍为 null。
- 不用 SQL 比较：`expires_at` 是 TEXT，小数秒位数不定，字符串比较在两种数据库的排序规则下不可靠，而 `summary_index` 本来就读全表。

### 8.2 会话封禁 `counts`

- `model::session_policy_block` 新增 `SessionPolicyBlockCounts { active, expired, released, all: i64 }`（`Debug, Default, Serialize`），`SessionPolicyBlockPage` 增加 `counts`。
- `session_policy_block_store::list` 增加一条聚合查询：复用 `{JOINS} {FILTER}`，`$1` 固定绑 `'all'`，`$2`（前缀）、`$3`（now）与列表相同；`SUM(CASE …)` 的三个条件与 `FILTER` 三个分支一致，加注释要求两处同步。
  - 列别名用 `all_count` 等（`all` 是保留字）；`SUM` 套 `COALESCE(…,0)`；沿用本文件「转 TEXT 再解析」的读法。
  - `total` 由聚合结果按 `state` 取值，删除原独立总数查询，使 `total` 与 `counts` 来自同一快照（未知 state 已在 handler 拒绝）。
- handler 与路由不变。

### 8.3 前端类型

- `api.ts`：`listProxies` 返回的 `counts` 改为 `{ all; available; used: number | null; expiring?: number; expired?: number } | null`；`SessionPolicyBlockPage` 增加 `counts?: { active; expired; released; all }`。新字段可选，旧网关下页面显示「—」。

## 9. CSS 组织

新文件都在 `@layer components`，只取 token，加入 `theme.test.mjs` 的 token-only 列表（同时加入四页组件、`NativeStageDetails.vue`、`AccountScopePicker.vue`）：

| 新文件 | 引入处 | 替代 |
| --- | --- | --- |
| `src/request-records.css` | `RequestDiagnostics.vue`、`NativeStageDetails.vue` | `request-design.css` 全文（含与 `NativeStageDetails` 共享的类）、`RequestDiagnostics.vue` 的 scoped 样式（死样式） |
| `src/proxies.css` | `Proxies.vue` | `proxy-design.css` 全文（同时删 `main.ts` 引入）、`style.css` 代理规则、`approved-design.css` 代理残留 |
| `src/tokens.css` | `Tokens.vue`、`AccountScopePicker.vue` | `approved-design.css` 的令牌列表、令牌编辑、`AccountScopePicker` 规则 |
| `src/session-blocks.css` | `SessionPolicyBlocks.vue` | `SessionPolicyBlocks.vue` 的 scoped 样式 |

- 删除顺序：每段先 grep 选择器确认只服务本页，再删。保留 `approved-design.css` 的全局排版与指针规则、`style.css` 的 `.approved-run-dialog`、`.resource-grid`、全局弹窗高度规则，`kit.css` 的 `.proxy-picker-*` 与 `.account-proxy-picker`。
- `apps/legacy-web/pagination.css` 的 `.request-list-footer>div` 规则随旧类名删除（先 grep 确认 legacy-web 无使用者）。
- 未分层旧规则会压过新样式，因此必须删除，不加 `!important`。
- 页面根元素显式设正文 `--ui-font-size-md` / 1.55，抵消 `approved-design.css` 全局行高 normal。

## 10. 验证

### 10.1 新脚本 `deploy/flower2api/verify_records_pages_design.py`

照搬 `verify_account_page_design.py` 的 `PAIRS = (画面, 设计稿选择器, 页面选择器, 属性)` 结构与 KNOWN 白名单：

- 1440×900 对 `#requests`、`#proxies`、`#tokens`、`#blocks` 逐项比对概览卡、表格卡片头部、分段、表头、单元格主值与辅助值、徽标、行操作按钮、图标块、分页的计算样式。
- 行为：日志卡点击发出 `request_diagnostics_log_mode` 保存且保存中禁用；分段计数与切换；筛选展开；代理第 4 卡读取 `expiring / expired`（含缺失显示「—」）；令牌名称搜索过滤与计数；封禁分段四态计数与切换；详情抽屉贴右全高、宽 1020、页签切换与内容区唯一滚动；编辑弹窗居中。
- 390×844：四页无页面横向滚动，折叠列与保留列符合 §4–§7。
- 零控制台错误；截图输出到 `.deploy/console-ui-revamp/records/verify/`。

### 10.2 既有脚本分诊

保留 §1.1 的定位契约后，多数脚本零改。集合：S = 回归集，E = 集合外，— = 两边都不在。

| 脚本 | 集合 | 分诊 | 说明 |
| --- | --- | --- | --- |
| `verify_request_detail_design` | S | 删除旧原型比对 | 删 `flower2api-concept.html` 打开、计算样式比对与「无差异」断言（L13、L15-26、L35）；业务断言（尝试数、查看链路跳页签、阶段证据、1440/720/390 不溢出、Esc 关闭）全部保留 |
| `verify_dialog_typography` | S | 删除旧原型比对（代理部分） | 删代理编辑的旧原型比对（L14、L17-19）；宽度 680 改读 `offsetWidth`（入场缩放动画期间 `getBoundingClientRect` 为 646）；抓包弹窗部分保留 |
| `audit_token_task_design` | S | 删除旧原型比对（令牌用例） | 删令牌映射（L25），L39 只等任务页就绪；任务页用例保留 |
| `audit_environment_proxy_design` | S | 删除旧原型比对（代理用例） | 删代理用例，环境页用例留到原生页迁移 |
| `verify_diagnostic_alignment` | S | 改写期望到第二版 | L14 写死 `12px`、L15 写死删除悬停 `rgb(253, 240, 243)` 改为读取 token 实际值（探针法，见 `ui-guidelines.md` 迁移期规则）；三个操作带图标可点的断言保留 |
| `verify_tokens_design` | E | 改写期望到第二版 | 行改为 `tr.token-row`；底栏布局断言按 `ModalDialog` 底栏定位；补名称搜索过滤与计数断言；载荷、启停、删除确认、三档不溢出保留 |
| `verify_session_policy_blocks_ui` | E | 改写期望到第二版 | L148-160 的 `combobox 封禁状态` + option 改为 `radio`（名称带计数，如「封禁中 21」）；夹具补 `counts`；服务端时钟、分页、解除、静默刷新外框稳定、读取失败保留等断言保留 |
| `verify_remaining_pages` | E | 只改定位 | L58-59 的 `button 错误 7 / 全部 53` 改为 `radio`；基线失败点 L52 在请求段之前，保持不变 |
| `verify_proxy_design` | S | 夹具补计数 | 定位契约保留后零改；夹具 `counts` 加 `expiring / expired`，`usage=false` 返回 `None`（该夹具是多数脚本的基类） |
| `verify_management_ui` | S | 只改定位（按需） | 失败点 L475 之前的 `verify_request_metadata`（L182-237）须仍通过；账号辅助行不放邮箱，失败点保持 L475 |
| `verify_page_sizes`、`verify_execution_node_visibility`、`verify_console_ui`、`verify_workspace_stability`、`verify_management_polish`、`verify_rejected_request_ui`、`verify_cluster_request_ui`、`verify_agy_request_records`、`verify_native_diagnostics_cpu` | S / E | 不受影响 | 依赖项均在 §1.1；基线失败点（page_sizes L38、management_polish L87、cluster L76、agy L177）不变 |
| `verify_shared_pagination`、`verify_viewport_interactions`、`verify_datetime_boundary`、`verify_frontend_navigation`、`audit_full_design`、`verify_ui_shell`、`verify_account_page_design` 及只把 `/requests` 当离页目标的环境脚本 | S / E / — | 不受影响 | 分页名、`取消` 唯一、无 counts 夹具下请求页不报错；`audit_full_design` 差异数会变，不断言 |

- 夹具：`verify_proxy_design.py:72-76`（`ProxyDesignFixture`，派生出大部分页面夹具）补到期计数；`verify_session_policy_blocks_ui.py:43-56` 补 `counts`（同前缀、不受状态筛选影响）；`verify_ui_shell.py` 空列表可不补（显示「—」）。请求诊断夹具不变，无 `counts` 的夹具继续回归「—」路径。
- 新脚本测日志卡切换用 `verify_remaining_pages.py` 的设置夹具（记录 PUT 并回显，`settings_gate` 卡住保存以断言保存中禁用）；旧网关缺到期计数用实例上替换 `directory_counts` 覆盖。实际比对 63 项，白名单只有开关 99px / 999px 全圆一项。
- `management_ui`、`remaining_pages`、`page_sizes` 的请求 / 代理段在基线中跑不到，改定位后单独核对，不以回归结果为证。

### 10.3 网关测试

- `cd services/gateway && cargo fmt --check`。
- 聚焦：`cargo test --locked --lib handler::proxies`、`store::proxy_store`、`session_policy_block`、`handler::router::tests::session_policy_block_admin_contract`；收尾跑一次 `cargo test --locked`（SQLite 夹具锁冲突时加 `-- --test-threads=4` 重跑）。
- 新增与改写的测试：
  - `summary_tests` 整体相等断言补 `expiring / expired`；新增到期边界表（now、now−1s、now+1s、now+7d−1ms、now+7d、None、非法串），以及引用不完整时 `used=null` 而到期两项仍为数字。
  - `proxy_store` 测试断言 `summary_index` 读回 `Some` 与 `None`。
  - 路由测试：建两条代理（已过期、1 天后到期），`GET /admin/proxies` 的 `counts.expired=1`、`expiring=1`；`usage=false` 时 `counts` 为 null。
  - 存储测试 `session_policy_block_counts_match_list_filters`：多前缀、到期边界（`expires_at_ms == now` 计入已到期）、已解除（含已解除且已到期只计已解除）；每个前缀四个 state 的 `list(...).total == counts.<state>`，且 counts 不随 state 参数变化。
  - `session_policy_block_admin_contract` 补解除前后的 `counts` 断言。
- PostgreSQL 路径无自动化覆盖，按 `testing-quality.md` 人工核对 SQL。

## 11. 规范同步

- `.trellis/spec/web/frontend/ui-guidelines.md`：组件库扩展（§2）；四页第二版合同（概览卡口径、表格卡片头部、单元格主辅值、色调映射、390 折叠、详情抽屉）；会话封禁段落改为分段计数；测试命令加入新脚本。
- `.trellis/spec/web/frontend/frontend-guidelines.md`：请求列表段落（Token 列两行辅助值、详情页签角色）。
- `.trellis/spec/gateway/backend/proxy-directory.md`：`counts` 增加 `expiring / expired` 口径与测试。
- `.trellis/spec/gateway/backend/service-architecture.md`：会话封禁列表返回 `counts`，与列表同一 now 与前缀、不随 state 变化；Tests Required 补新测试名。

## 12. 发布与回滚

- 网关字段为纯增量；前端对字段缺失兜底，前后端可分别回退。
- 回滚：未提交前按文件 `git restore`；提交后整体回退本任务提交（网关与前端同一提交）。
