# 控制台 UI 与复用控件

## 1. Scope / Trigger

- 修改账号、代理、令牌、任务、环境、授权登录的布局、表单、菜单、气泡或滚动行为时读取本规范。
- 设计基准：`doc/design/flower2api-concept.html`。用户已基本认可账号页，后续增量以任务记录的最新决定为准。
- 已实现的 Vue 通用控件：`apps/web/src/components/ui/controls/`。实际运行示例：`apps/web/ui-preview.html`、`apps/web/src/previews/UiPreview.vue`。
- 静态稿中的代理检测、到期配置和授权步骤是本地模拟。其业务页面与后端的正式迁移仍属当前任务后续实施，不能把视觉预览作为生产能力证据。
- 本规范规定新设计及逐页迁移的视觉/交互合同。现有 API、权限、错误恢复、原生页面生命周期规则继续遵守 [frontend-guidelines.md](./frontend-guidelines.md) 和 [原生组件规范](../../legacy-web/frontend/component-guidelines.md)。

## 2. Signatures

统一导入路径：

```ts
import { NumberInput, ChoiceSelect, InfoTooltip, SearchInput, DateTimeControl } from '@/components/ui/controls';
import type { ChoiceOption } from '@/components/ui/controls';
```

| 组件 | 输入与事件 | 使用范围 |
| --- | --- | --- |
| `NumberInput` | `modelValue?: number \| string`，`label: string`，`id?`，`min?`，`max?`，`step?: number = 1`，`disabled?`，`readonly?`，`invalid?`；`update:modelValue(number \| string)` | 并发、RPM、百分比、端口、TTL等数值 |
| `ChoiceSelect` | `modelValue?: string`，`options: readonly ChoiceOption[]`，`label`，`name?`，`placeholder?`，`disabled?`，`required?`，`invalid?`，`portalTarget?: HTMLElement \| string`；`update:modelValue(string)` | 有限枚举单选，如认证、Billing、订阅类型 |
| `InfoTooltip` | `label: string`，`title?`，`delay?: number = 150`，`portalTarget?`；`trigger`插槽与默认内容插槽 | 只读完整统计、字段口径说明 |
| `SearchInput` | `modelValue: string`，`label`，`placeholder?`，`disabled?`；`update:modelValue(string)`、`search(string)` | 列表或会话搜索，业务方决定请求时机 |

`ChoiceOption = { value: string; label: string; disabled?: boolean }`。同一菜单的 `value` 必须唯一。空字符串是合法的业务选项值；`undefined` 表示尚未选择。

`NumberInput` 的 `name`、`required`、`aria-describedby` 等原生属性透传到内部输入框。`SearchInput` 同样向内部输入框透传原生属性。调用方负责业务字段规整与提交，不在控件内部请求 API。

原生/静态稿当前复用入口：`renderNumberControl()`、`renderChoiceSelect(name, label, options, value, compact=false, searchable=false)`、`showUsageBubble()`、`renderDateTimeControl(name, label, value)`、`refreshDateControl(input)`。原生页面保持自身渲染和事件清理模式，不通过复制 Vue 的生命周期实现复用。

## 3. Contracts

### 视觉 Token 与层次

控件颜色 token 的唯一代码源是 `apps/web/src/components/ui/controls/controls.css`。阅读尺寸与反馈表面来自 `apps/legacy-web/ui-foundation.css`，Vue、独立文档及原型共同引用。`--ui-*` 前缀隔离存量主题，页面不逐个写死控件颜色。

| Token | 当前值 | 用途 |
| --- | --- | --- |
| `--ui-surface` | `#fff` | 菜单、气泡、内容表面 |
| `--ui-field-surface` | `#fbfcfe` | 表单输入背景 |
| `--ui-text` | `#46546b` | 控件正文 |
| `--ui-muted` | `#7d879a` | 标签及次要信息 |
| `--ui-border` | `#e2e6ed` | 默认边框 |
| `--ui-border-hover` | `#cfd5df` | 悬停边框 |
| `--ui-accent` | `#856b9e` | 选中项及辅助强调 |
| `--ui-focus` | `#ad9bc4` | 焦点细边框 |
| `--ui-focus-shadow` | `0 0 0 3px #a28eb414` | 轻量焦点光晕 |
| `--ui-selected` | `#f5f2fa` | 选项高亮背景 |
| `--ui-danger` | `#b45b67` | 错误边界 |

- 按CSS视口采用三档阅读尺寸：小于1920px、1920～2559px、2560px及以上。正文/输入/主要按钮14/15/16px，辅助文字12/13/14px，卡片标题16/17/18px，分区标题18/20/22px，页标题28/30/32px；标准控件高40/42/44px，紧凑控件34/36/38px。控件圆角8px、菜单9px、气泡12px。禁止整页zoom或按物理像素缩放。
- 常用间距采用4/8/12/16/24px，页面容器24–40px；窄屏16–20px。页面主内容使用柔和浅底，内容卡片使用白色和轻边框。
- 字体采用 Inter Variable 与明确的中文系统回退；关键数字使用等宽数字或 JetBrains Mono Variable。字体资源本地托管，许可证参考 `doc/design/font-licenses.txt`。控件当前通过 `--ui-font` 使用字体栈，实际字体资产接入由页面迁移完成。
- 成功/执行状态用绿色，等待/临近到期用琥珀色，失败/已过期用红色，紫色用于选中与偏好。颜色同时配文字含义。
- 焦点只画在完整交互容器上：数字输入、带图标的搜索栏用 `:focus-within`；内部输入框去掉重复 outline/shadow。键盘焦点必须可见，强制颜色模式保留系统高亮。

### 控件行为

**数字输入**

- 保留 `type=number` 与原生 `min/max/step/required` 校验，使用清晰的减/加按钮替代系统微型箭头。
- `''` 代表用户清空。不得转换为0、自动提交或偷偷钳制手输越界值；表单提交时展示真实校验结果。
- 步进调用原生 `stepUp(direction)`，保留小数步长。达到上下限禁用对应按钮；`disabled/readonly` 同时禁止步进。
- 组件的 v-model 可返回数字。SettingsMap 一类字符串 API 必须在业务边界转成字符串，沿用现有设置合同。

**单选菜单**

- Vue 使用现有 reka-ui 的 Select 能力，避免每页维护一套焦点、键盘和浮层代码。
- 内部编码不得泄露到业务 v-model 或 `FormData`。例如“未设置”的业务值 `''` 必须原样提交。
- 支持键盘方向键、文字定位、Enter选择、Esc关闭及焦点返回；禁用项禁止选中。选择暂时移到其他候选但取消时保持原值。
- `modelValue` 不在当前选项中时显示“当前选项不可用”，不自动改成第一项。最终提交的选项白名单仍由业务层校验。
- 少量枚举用 `ChoiceSelect`；大量代理线路用可搜索、限高、分批加载的专用选择器。不要把几百条代理直接铺进表单。

**信息气泡**

- 需要设计样式的完整数据提示使用 `InfoTooltip`，不使用浏览器原生 `title` 承载大段核心信息。
- 支持悬停、键盘焦点及触屏点击；指针可进入气泡阅读。内容仅用于只读文本，含表单或操作按钮的内容应采用Popover/Dialog。
- 原生 `<dialog>` 中必须通过 `portalTarget` 指向该dialog，确保浮层处于正确的模态范围；普通页面默认portal到body。
- Esc先关闭当前浮层并阻止同次按键关闭父dialog。滚动、切换或卸载后不得留下脱离触发器的浮层。
- 账号请求数、Token、折算及预计费用均保留；紧凑卡片固定单行，超长省略，气泡与详情展示完整信息。真实0、未知、过期和未设置分别呈现。

**搜索输入**

- 图标、输入和清空按钮使用一个完整焦点边框；内部不再画第二层边框。
- 输入事件只更新文本。`search` 只在普通Enter时触发；中文输入法确认阶段不触发业务搜索。
- 清空后输入框继续获得焦点。组件不推测搜索字段、不自行调用API；业务方负责过滤、分页重置、异步代次与错误提示。
- 搜索代理时只使用名称、公开地址、出口IP和地区等公开信息，凭据不进入列表、搜索文本或提示日志。

### 日期时间与账号筛选

- 请求开始/结束时间与代理到期时间共用 `renderDateTimeControl`，提供月份切换、日期网格、时分、今天、清空与确定。
- 隐藏表单字段存储浏览器本地 `YYYY-MM-DDTHH:mm` 或空字符串；提交时由业务所有者转换ISO。不得直接截取UTC字符串作为本地值。
- 选择过程中只修改草稿；Escape、外部关闭保持原值。确定时校验小时0–23、分钟0–59，拒绝本地夏令时缺失时段的静默归一化。日历支持方向键，弹窗中的Escape先关闭日期面板。
- 请求时间范围为起点包含、终点不包含，开始必须早于结束。代理延长按原到期时间或当前时间的较晚者计算，保存后生效；这些规则属于业务层。
- 账号条件用名称/邮箱搜索选择，“全部账号”对应空内部值。ID只用于接口关联，不让用户通过记忆ID完成常规筛选。缺失历史资料保留追溯标签。
- `renderChoiceSelect(..., searchable=true)`在选择菜单中提供搜索；候选高亮序号与实际选项值分别维护，过滤后选择仍提交原ID。无匹配、取消、键盘操作保持完整语义。
- Vue 的 `DateTimeControl` 使用 reka-ui Calendar 与 `@internationalized/date`，接受 `modelValue: string | null`、`label`、`disabled?`、`portalTarget?`，确认时输出ISO或清空null。请求查询与代理到期共用此组件。原生运行时段使用 `ui-controls.js` 的时间面板，确认后仍提交原 `HH:mm` 字段；取消及Escape保持原字段。

### 请求列表与诊断详情

- 既有请求页同时展示CC及AGY，平台与模型分别表达；AGY上的Claude模型保持Antigravity标记。高级筛选追加平台、协议、内核版本、请求模型和实际模型，沿用服务端计数与分页。账号选择器仅该入口显式platform=all并展示平台标记。
- 四页签复用现有布局，展示源usageMetadata、冻结策略、工具前驱及独立控制收口。历史事实未知、真实0和采集缺口分别展示；已解码Gemini、Cortex提交与最终TLS阶段按来源区分。具体字段及权限沿网关settings-database的AGY请求记录合同。
- 列表核心字段包括时间/请求ID、账号、模型/转发、持久结果/响应码、总耗时/首输出、Token及尝试数。模型、Token与首输出注明末次尝试口径；总耗时只按请求起止观测计算。
- 增加“原始 Session ID”列，直接读取根记录 `original_session_id`，支持完整值复制，详情概览同步展示。缺失和旧记录显示“未提供”，长值可省略并通过详情查看完整值；复制始终使用原始完整字符串。
- “模型 / 转发方式”沿现有列显示“原生运行时 · 2.1.280”或“原有转发 · 2.1.293”，版本取 `last_attempt.profile_version`，缺失显示“未观测”。账号基础版本、客户端 UA 或配置默认值不作为实际尝试版本的替代来源。
- “Token（末次）”列下方及性能详情展示平均 TPS：`output_tokens * 1000 / duration_ms`，包含该次尝试首输出等待，一位小数并注明 token/s。仅 success、partial=false、有效非负安全整数输出 token 和有限正耗时时展示；真实零输出保留 0.0，缺失、处理中或不完整记录为“未观测”。列表与详情共用计算入口。
- “Token（末次）”列同步展示缓存读与缓存写，分别读取`last_attempt.tokens.cache_read_tokens/cache_write_tokens`；真实0显示0，null或历史缺失显示“—”，性能详情沿同次尝试显示“未观测”。`verify_management_ui.py::verify_request_metadata`覆盖2400、0、null及缺失四种缓存写值，并保留Session ID、版本和TPS回归。
- 时间列按浏览者时区显示日期时间，省略 IANA 时区后缀；详情保留时区与原始时间。窄屏继续保留核心列，其余信息由详情查看。
- 使用“全部/错误/处理中”带图标的快捷选择，保留账号、时间与关联ID条件；具体结果与快捷结果属于同一维度，避免相互叠加成无意的空集合。
- 账号匹配覆盖请求账号与各次尝试账号；完整关联ID匹配请求、响应及上游ID。实际诊断接口支持 `outcome=errors` 六类错误集合；分页返回独立于当前结果维度的 `counts.all/errors/processing`，保留其余查询条件。每条记录的 `last_attempt` 由存储查询投影；不得在单页数据上伪造全量统计或制造逐行详情请求。
- 详情与列表采用清晰对比度：主值采用深蓝灰（如`#405670`），辅助标签采用中蓝灰（如`#68788e`），关键耗时采用`#344f6d`。不对内容容器使用透明度统一弱化正文。
- 头部处理保留动作文字：删除行浅红底（当前`#fff4f5`）与红色标签，保留绿色、运行时处理紫色、提取上下文蓝色。筛选动作时高亮继续生效，不能只靠颜色传达含义。
- 采集按发生时模式和capture_status判断，模式切换只影响后续请求；组装中间值与最终TLS证据分开。空字段展示未观测，0毫秒/0Token保留真实零值。

### 会话封禁列表

- `SessionPolicyBlocks.vue` 的每5秒轮询沿用已提交的会话前缀；搜索框草稿仅在显式查询时提交。后台读取使用独立请求状态防止重叠，保持刷新按钮文字、分页可用状态和已有空态；手动查询可取消后台读取，迟到回包沿代次丢弃。
- 空态使用单层 `TableRow > TableCell`，居中显示图标、标题、说明与重置查询。`TableEmpty` 自带表格行，不能再包进 `TableRow`。表格排版通过页面容器的 `:deep(table/th/td)` 作用到组件内部，避免将父级 scoped 选择器绑定到内部 class 导致样式失效。
- 验证入口 `python3 deploy/flower2api/verify_session_policy_blocks_ui.py`：覆盖390/1440/1920/2560px，慢读取期间按钮与面板尺寸稳定、轮询跳过未完成读取、搜索草稿保持、空态与重置、解除确认、分页及设置字符串保存。

### 系统设置表单与草稿

- `.settings-inline-note` 统一使用块级布局，链接与段落共享顶部分隔线和垂直间距；行内链接的顶部边框会覆盖上一行说明。`verify_session_policy_blocks_ui.py` 在390/1440/1920/2560px断言封禁记录链接的边框顶部不小于时长说明底部，避免仅检查 `text-decoration:none` 漏掉相邻元素覆盖。
- 以现有 `Settings.vue::saveSettings` 的真实键集合核对完整性，按用途分组。新增分组或换肤不能删除字段、访问预设或预热记录入口。
- 静态实现使用 `settingsFields` 定义控件与约束，`settingsSaved` / `settingsDraft` 分别维护已保存值和草稿。搜索、分类切换与页面往返保留草稿，保存栏显示全局待保存项数。
- 所有设置提交值规整为字符串；数字清空保留空值并在保存时校验。非法字段定位到实际分类，搜索条件清空后让错误控件可见。
- 依赖项禁用只阻止编辑，不清除已有值：Hello探测关闭后保留严格模式/TTL；后台分类为mock时保留身份注入开关，切回放行后恢复。
- 智能调度权重为0–10、最多一位小数，有效主权重总和大于0。新增额度重置、排队等待主系数默认0，5小时／周窗口权重默认1；两类窗口都为0时重置偏好关闭。旧模式选择与兼容排序权重退出页面及保存载荷，精度错误定位到对应字段。
- 版本/UA/模型/JSON规则沿原业务校验；画像选择模式与版本变化保留原账号模式准入范围联动。访问预设只修改草稿，统一保存后生效。
- 请求日志模式与请求记录页共享同一设置语义，历史请求的发生时模式保持冻结。
- messages 缓存断点只显示 off/sub2api；默认“关闭（保留原生布局）”，说明额外改写可按需启用、保存后续请求生效及 TTL 独立。历史非法值在页面归为 off，提交保持字符串；一次性重置及请求冻结沿[原生消息缓存设置](../../gateway/backend/settings-database.md#scenario-原生消息缓存设置与一次性关闭)。
- 本地保存只提交点击时的快照；保存期间新增编辑继续作为草稿。撤销恢复当前已保存值，原生页面和Vue迁移均应验证相同行为。
- 预热记录读取原 `PrimeLogEntry`；模型预热展示在设置页，零模型进程准备状态由环境页承接。`success=false`且`error_message`以`skipped:`开头时显示跳过，成功、跳过、失败分别以文字和语义色表达，沿原HTTP成功口径。
- 预热记录复用Table/Button/Badge/InfoTooltip与`--ui-*`阅读尺寸，完整展示已有error_message与长模型名。桌面保留六列，窄屏将触发时点、模型和耗时并入核心列；0ms保持真实值，刷新保持当前记录，加载与空态分别显示。原生title由可点击及键盘可关闭的信息气泡承接。
- `verify_prime_history_ui.py`使用真实产物与合成接口，覆盖390/1440/1920/2560px、状态、长字段、完整原因、键盘/触屏、刷新加载、单行空态及零保存；浏览器模型调用为0。

### 宽屏与操作指针（2026-11-15用户补充）

- 控制台与主内容随视口铺满，侧栏固定在视口左侧。用户最新决定覆盖原型1920px应用上限及1510px内容上限；常规视口继续复用定稿间距。
- 1680px及以上账号采用四列，卡片按可用宽度均分。390px单列；1280px两列；1340–1600px三列。禁止以提高列数压缩卡片信息。
- 所有可点击按钮、链接、页签与菜单项使用手型指针。实际disabled按钮显示禁用指针并由浏览器禁止点击；组件型禁用链接维持原有事件屏蔽。
- 原生任务与环境复用 `apps/legacy-web/ui-controls.js`，保留原生字段的name/value、约束及input/change事件。菜单、时间面板的Escape先关闭最上层；选择和时间取消不修改原字段。
- 原生页和Vue页滚动条在滚动时显示，800ms无滚动后隐藏滑块；轨道宽度保持稳定。
- 回归入口：`verify_viewport_interactions.py`、`verify_runtime_workspace_design.py`、`verify_remaining_pages.py`；使用合成接口。

### 布局与信息组织

- 左侧为可折叠导航，右侧直接从页面标题开始。当前基准取消“我的工作空间”卡片和重复顶部工具栏；折叠/展开放到侧栏底部管理员区域。
- 品牌旁保留版本与系统更新入口；折叠后可见，图标入口有可访问名称。移动端保留紧凑导航按钮，所有模块仍可达。
- 侧栏按视口高度布局；预览条滚出后释放对应高度。长菜单在侧栏内部滚动，不在页面底部露出侧栏背景缺口。
- 详情/编辑工作区固定标题和页签，仅正文滚动；复杂表单在桌面扩宽并分组。保留草稿、取消和保存语义；不以删除字段或隐藏功能入口换取简洁。
- 同一账号的概览、配置、调度、环境与诊断使用同一工作区。页内导航保持上下文，二级弹窗主要用于独立确认。
- 转发方式与代理选择属于主要配置；认证字段放在高级配置。排队数量直接可见。
- 滚动条在滚动时显示，停止800ms后250ms淡出，轨道宽度稳定。采用减少动画偏好时缩短动画，高对比模式采用系统颜色。这一行为目前在静态稿中实现，正式迁移时沿用同样验收。

### 正式控制台与账号首批迁移

- `apps/web/src/style.css` 保留现有主题变量名，采用已确认紫色强调、深色侧栏与浅色内容区。字体来自 `src/assets/fonts/` 中的本地 WOFF2，许可一并保留；离线导出须把同源字体内嵌，不能依赖构建目录外链。
- `Dashboard.vue` 在品牌旁保留 `/updates` 入口，版本优先使用 `usePlatformVersion` 读取的当前控制镜像版本；旧端回退到已验签目录精确匹配的current_release，缺省显示“版本”。移动入口缺省显示“系统更新”。桌面折叠位于管理员区域，偏好键为 `flower2api-sidebar-collapsed`，存储失败仍保持本次会话选择。移动导航保留原七个模块。
- 正式账号仍使用既有分页及每5秒读取。卡片显示三种额度窗口，7天Sonnet数据类型继续兼容；完整旧配置/画像/评分等信息位于详情。代理公共摘要仅含protocol/host，编辑及OAuth代理输入默认遮蔽认证信息。
- 账号数字草稿由 `numberDrafts` 保存 `number|string`，`applyNumberDrafts()` 在提交边界检查非空整数再写入原数字字段；原范围校验与 `accountUpdateDelta` 继续生效。认证编辑默认收起，新建默认展开，全部旧字段保留。
- `useActiveScrollbars()` 由应用根调用一次，通过捕获真实scroll标记容器，800ms后清理；卸载清理监听器及全部计时器。窗口标题/页脚固定，正文独立滚动。
- 验证入口：`deploy/flower2api/verify_accounts_design.py`，覆盖真实Vue组件与合成管理接口的字段保存、取消、分页、OAuth、调度筛选、费用气泡、字体、侧栏和1440/720/390px布局；沿用管理/环境/导航回归。

### 预览状态与连续操作合同

- `renderNumberControl(name,label,value,min,max,step=1,required=true)` 默认必填；可选字段显式传 `required=false`。养号 `interval_max_minutes` 留空保存 `null`，填写时校验不小于下限；不能使用 `Number('')` 将空值变成0。
- `createWorkSpace(mode,id,sample=false)` 为每个新账号生成独立对象。新建账号先准备完整账号与工程/养号空间，再统一写入。账号ID单调分配，删除后不复用历史身份；禁止复制某个可删除账号的配置作为默认值。
- `accountsUsingProxy(id)` 返回带 `kind: gateway|task|draft` 的引用集合，供使用列表、摘要和删除前检查共用。已绑定任务账号按网关有效代理归属去重；独立任务账号及登录草稿均阻止删除。跳转入口保留所属域，禁止只用数字ID推断账号类型。
- `importProxyPreview(form)` 复用 `parseProxyInput(text)` 校验整批输入，全部成功后写入；失败保留输入和原列表，只展示行号及安全原因。公开 `url` 不含认证信息，`username/password` 独立保存并可在编辑中回填。
- `workTimezone(account)` 优先读取 `workEnvironmentRefs` 指向的环境时区；无映射时读取任务配置。卡片、搜索和重授权回填使用同一读取入口。环境保存同步任务镜像；已绑定账号的授权提交沿用当前环境时区，避免旧草稿覆盖新的设置。
- `navigate(page,syncLocation=true)` 同步主路由；任务子页共享 `workLocationHash()`。相同地址的重绘不新增历史。`restorePreviewLocation()` 恢复页面并关闭旧浮层，恢复过程不再次入栈。

### 复用与业务边界

- 先复用已有 Button/Input/Dialog/Card，新增通用控件放在 `components/ui/`；当前四个控件通过 `controls/index.ts` 导出。
- 调度评分、配额状态、代理到期策略、账号关联、认证请求属于业务层，不能塞进通用输入控件或工具提示组件。
- 不把整个账号卡片抽成包含账号、代理、任务开关的万能组件。先抽稳定的原子控件，再根据真实多处使用提取布局组合。
- 组件演示页用于开发与验证，正常生产构建入口仍是 `index.html`。正式账号页已使用 NumberInput、ChoiceSelect 和 InfoTooltip，调度详情使用 ChoiceSelect 和 SearchInput。其他页面按迁移进度接入。

## 4. Validation & Error Matrix

| 条件 | 必须呈现/保留的行为 |
| --- | --- |
| 数字清空、越界或步长非法 | 保留用户输入和原生校验；不自动变为0 |
| 数字达到min/max，或disabled/readonly | 对应步进按钮禁用 |
| 单选值为 `''` | 正确显示对应选项，FormData仍为 `''` |
| 未提供选项/缺失历史值/禁用选项 | 空态、不可用提示、禁止选中；不猜测值 |
| 下拉或气泡位于原生dialog | portal指向父dialog；Esc只关闭当前层 |
| 390px窄屏、菜单贴近下边缘 | 菜单碰撞避让并限高；主页面无横向溢出 |
| 搜索聚焦 | 外框轻量高亮，内部无重复紫色矩形 |
| 输入法Enter确认 | 仅确认输入，不触发搜索 |
| 单行统计超宽 | 省略显示，预计费用仍在数据中且完整内容可访问 |
| 识别失败/取消编辑 | 业务草稿或原配置保持，不提交请求 |

## 5. Scenarios and Examples

常规使用：

```vue
<script setup lang="ts">
import { ref } from 'vue';
import { NumberInput, ChoiceSelect, InfoTooltip, SearchInput, DateTimeControl } from '@/components/ui/controls';

const concurrency = ref<number | string>(3);
const mode = ref('oauth');
const query = ref('');
</script>

<template>
  <NumberInput v-model="concurrency" label="并发上限" name="concurrency" :min="1" required />
  <ChoiceSelect v-model="mode" label="认证方式" name="auth_type"
    :options="[{ value: 'oauth', label: 'OAuth' }, { value: 'setup_token', label: 'Setup Token' }]" />
  <SearchInput v-model="query" label="搜索代理" placeholder="名称、出口 IP 或地区" />
  <InfoTooltip label="查看完整费用" title="费用口径">
    <template #trigger>折算 $4.85 · 预计 $15.16</template>
    预计费用按网关费用与官方已用比例估算。
  </InfoTooltip>
</template>
```

- 边界：订阅类型含 `{ value: '', label: '未设置' }` 时，使用原始空字符串完成编辑，不构造业务侧特殊哨兵值。
- 错误：`Number(modelValue)` 将清空变成0。正确：提交前明确校验空值，再按接口合同规整。
- 错误：搜索栏外框和内部input各画一层强焦点框。正确：统一由外框`:focus-within`承担焦点。
- 错误：直接复制静态稿的全局事件委托到Vue组件。正确：复用reka-ui处理菜单/气泡生命周期，并由Vue组件管理状态。
- 错误：在原生dialog中将浮层一律portal到body，再用超大z-index补救。正确：传入父dialog作为`portalTarget`，并验证Esc层级与焦点。

## 6. Tests Required

```bash
npm --prefix apps/web run build
npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187 --strictPort
python3 deploy/flower2api/verify_ui_controls.py --url http://127.0.0.1:4187/ui-preview.html
```

- `verify_ui_controls.py`验证真实Vue组件：数字上下界、空值、小数步长、禁用；空选项原值、菜单键盘与禁用选项；搜索焦点、输入法、清空；气泡和原生dialog浮层；720/390px与触屏。测试不得发业务API请求。
- 静态稿对应检查位于当前任务的 `research/verify_concept.py`、`verify_account_controls.py`、`verify_account_workspace.py`、`verify_proxy_revision.py`、`verify_request_preview.py`、`verify_settings_preview.py`；只在改动该概念稿时运行对应范围。
- 当前组件证据在 `.deploy/frontend-sidebar-refresh/ui-controls/verification.json`；静态稿证据在 `.deploy/frontend-sidebar-refresh/concept/`。旧截图或过期检查不能替代本次变更验证。
- `research/verify_check_repairs.py`（当前前端任务）覆盖删除全部任务账号后创建、可选上限、跨模块历史、双入口时区与迟到授权、认证代理导入、独立任务/草稿占用及删除前复核；同时要求零浏览器异常和零外部网络请求。
- 新页面采用组件后，补充该页面的保存/取消、权限、错误、异步和接口合同检查。组件测试通过不等价于业务页面迁移完成。

## 正式组件交互细节补充

- Button的默认variant显式为default。主按钮默认#0e1726、悬停#494057；描边按钮白底、#e0dfe6边框，悬停#f6f4fa底、#c6bbdf边框。默认及悬停都不加阴影和位移，8px圆角；禁用和键盘焦点独立，减少动效偏好关闭过渡。不可用旧页面的橙色按钮类覆盖已确认流程。
- `DateTimeControl`使用reka-ui日历及现有NumberInput，`modelValue:string|null`为ISO瞬时，界面为浏览器本地时间。打开建立草稿，确定才提交，Esc只关闭日期浮层；清除返回null。日历通过`@internationalized/date`真实日期类型处理。
- `ProxyPicker`接收`ProxyRoute|null|undefined`；undefined保留原配置，null直连，具体记录表示草稿选择。20条分批搜索、取消与迟到响应隔离，提交由账号边界写proxy_id/proxy_revision。
- 授权登录第一步440px，普通表单标签、代理输入和右对齐主按钮。真实交换成功后填入配置；关闭中止客户端读取并拒绝旧代次回填。授权结果默认隐藏凭据，仅原复制操作可主动获取。
- `runtime/RunDetails.vue`是顶层复用弹窗，900×740上限、固定标题/身份/页签/页脚、正文独立滚动。Teleport根容器尺寸放全局class，禁止仅依赖后代scoped样式。测试必须断言计算后的width/height，行为测试通过不能替代尺寸对照。
- 运行日志仅在日志页签读取最近128KiB、最多渲染1500行，文件列表不超过每10秒刷新，关闭或路由切换取消请求与轮询。终态补读保留落盘延迟兼容。
- `verify_interaction_parity.py`逐项比对定稿按钮默认与hover六项属性，并验证授权尺寸/关闭竞态/移动端；`verify_run_detail_design.py`验证顶层尺寸、页签与退出清理。

## 一比一迁移的取值与验收

`apps/web/src/approved-design.css`集中存放对照定稿后的页面排版规则；参考为`doc/design/flower2api-concept.html`渲染结果。`ui/icon`复用原型SVG路径，符号表通过Vite `?url&no-inline`发布到已有assets路由；不要把SVG符号表内联为data URL后用于use引用。快照导出必须把外部use改写为快照内符号。

`AccountScopePicker`接收modelValue CSV、accounts、label与help，只更新表单草稿。历史已选ID不在当前资料时显示账号编号并保留移除能力。父页负责完整分页、取消和保存。

`verify_exact_design.py`通过原型提取同数据进行CSS属性对照和三档截图。通过的采样只证明对应元素；完成声明还需覆盖全部页面、弹窗、操作状态以及布局边界。

### 定稿响应式及字体根合同

应用与内容区铺满视口，账号卡片最小320px、间隔18px；760px及以下强制单列，1680px及以上四列。侧栏在1920px/2560px断点为264px/280px，折叠宽度仍76px。验证需包含列数切换附近1340/1680px与1920/2560/3440px，不能只验1440/390px。

html根字号与原型共用`--ui-font-body`的14/15/16px三档规则，font-family为同一字体栈、font-synthesis:none。仅body字体相同不能保证rem控件一致。字体验收需核对浏览器实际平台字体，不能只看CSS声明。费用气泡专用class使用足够的选择器优先级，避免异步加载的通用控件样式覆盖。

授权登录选择代理与账号编辑共用ProxyPicker；代理选择在生成链接时冻结，成功后账号草稿沿用同一目录ID与revision。服务端处理目录凭据，浏览器只接触公开投影。

### 令牌与任务原型对齐（2026-11-15）

- 令牌桌面同行展示身份与直接操作；换行规则限定在窄屏媒体查询内。Tailwind的`--muted`是背景色，次要文字使用`--muted-foreground`；原生工作区的同名变量单独限定作用域。
- 任务工作区的定稿声明集中在`apps/legacy-web/work-design.css`，按原型CSSOM取值。主路由断点按实际浏览器视口响应，主区域宽度由侧栏占位确定。桌面1440px下任务账号三列。
- 新布局保留原表单ID、字段name与API处理，工程和养号空间继续分别维护配置、草稿及SSE清理。新增搜索仅过滤列表；题库的创建任务只预选题目并打开批次表单，提交前保持零写入。
- 旧`.view`的flex间距、旧页签底色以及高优先级按钮规则不能叠加进新工作区；校验卡片底栏按钮自身样式与宽度，不能只校验父容器。
- 运行配置与新建抓包使用两个独立入口。账号名称提供完整技术详情，登录草稿单独呈现；额度窗口区分真实0与未提供，不展示7天Sonnet。
- 增量验证：`audit_token_task_design.py`断言令牌、任务六入口和工程五分区的渲染样式并保存截图；`verify_runtime_workspace_design.py`覆盖原操作、详情、搜索、草稿、题目预选、独立抓包创建、响应式与键盘层级；`verify_tokens_design.py`覆盖令牌真实载荷与取消语义。

## 完整视口弹窗与跨文档组件复用

- 唯一视觉基准为 `doc/design/flower2api-concept.html` 的实际渲染结果。逐页核对内部结构、字重、字号、字体、行高、控件默认/悬停/焦点/选中状态与关键弹窗。仅采样外层容器不能作为一比一还原的验收证据。
- 原生文档的按钮、输入、选择和文本域必须显式继承 `--body-font`，防止用户代理样式回退到 Arial。字体资源与主后台同源、自托管。
- 原生Vue环境与任务模块在主文档展示弹窗，遮罩覆盖完整视口。任务局部观察器只同步Vue控件宿主；弹窗打开保持背景位置，关闭返回原入口，卸载清理观察器。原独立文档保留自身弹窗。
- 跨文档复用使用 Vue `Teleport` 挂入明确的专属宿主。原生代码仅管理宿主之外的状态文案，不得用 `textContent/innerHTML/replaceChildren` 删除由 Vue 管理的子树。
- `ProxyPicker` 增加 `portalTarget?: HTMLElement`，支持任务授权与账号编辑复用。跨文档浮层同时处理内容节点的 Esc，保留父授权窗口。目录只同步公开 ID/revision，手动连接保持独立折叠入口。
- `runtime/CaptureWorkspace.vue` 同时承载普通运行及工程/养号抓包。CSS 统一来自 `apps/legacy-web/capture-workspace.css`，通过 Vite 与原生文档共同加载。三个分区为请求索引、采集文件、TLS 握手；索引每页20条；文件读取独立取消，快速切换与卸载丢弃旧响应。
- TLS 展示统一经过 `runtime/captureEvidence.ts::tlsFields` 白名单。文件预览限脱敏索引、收尾状态及 TLS 元数据；保留原始文件信息，禁用原始正文预览。错误、重试、未知、空值及真实零分别展示。
- 新原生 CSS、JS、字体与 SVG 必须同步 `runtime_bridge.rs::browser_path_allowed` 的精确只读白名单及静态版本参数，并验证真实桥接路径。

### 运行配置整合保存

运行配置集中显示版本、默认模型与思考预算；原独立保存、回退及生效来源保留在各项展开区。整合保存只提交发生变化的设置，沿用三个原接口；部分失败保持窗口及失败草稿，重试只提交未成功项。提交期间同层关闭入口受控，离页后的回执不修改新页面。取消再打开以实际保存值初始化。

### 深层弹窗排版约束

通用原生工作区、运行详情与令牌编辑标题共用`--ui-font-heading`的18/20/22px，沿原650字重、行高及字距。代理编辑宽度680px，表单提示位于控件之后，同排输入保持共同基线。关闭图标使用同一SVG；原生委托事件通过closest定位按钮，沿原清理入口退出。共享输入框焦点采用#AD9BC4边框及浅紫外圈，避免残留默认黑色焦点框。

系统更新正文共用`--ui-font-body`，头部22×28px、内容28px；真实发布说明按段落呈现摘要，完整原文、安装计划、取消、历史回退及维护信息保持可达。样式回归使用verify_dialog_typography.py与verify_update_design.py逐控件读取原型实际计算样式，并覆盖说明收起、文本转义和取消零写入。

### 代理局部账号工作区与刷新稳定性

- `Accounts.vue` 的 `workspaceAccountId?: number` 允许在代理页复用完整账号窗口。该模式只读取目标账号，隐藏账号列表，保留原配置/调度/诊断提交和取消语义；`close`返回原触发按钮，`refresh`刷新代理引用。网关使用者的查看与配置保持代理URL、分页、筛选和展开，任务配置的明确跳转入口仍可导航。关闭/离页用代次丢弃目标账号迟到回执。
- 账号诊断先展示实际关联环境、CLI、请求内核和时段四条摘要，按 `gateway_account_id`匹配。三个操作在摘要下方，技术与调度详情折叠保留。请求诊断带账号筛选，环境时段直达携带 `section=schedule`，原生白名单校验后只读打开。
- 嵌入首屏先显示静态结构；同源、当前文档的 `runtime:ready` 表示路由结构就绪，字体与各区数据独立加载。读取失败在对应区域反馈并提供重试。弹窗观察器只处理窗口/登录步骤/组件宿主变动，忽略普通计时文字。当前任务与环境已采用原生路由，迁移合同见下节。

### 统一每页条数

- 共用 `PageSizeSelect`，以现有 `ChoiceSelect`提供组件菜单；支持所在文档的浮层宿主。样式从 `apps/legacy-web/pagination.css` 同时供Vite和原生文档使用，静态资源同步Rust精确白名单。
- 账号默认12条，可选12/24/48/96；代理、请求、绑定会话与抓包默认20条，可选10/20/50/100；工程历史默认10条、交互默认20条。接口调用保持原上限及默认值兼容。已有分页即使只有一页也允许调整条数。
- 切大小回第一页、保留筛选并取消/隔离旧请求。工程游标页变更清理旧游标；失败恢复原页大小和快照，并保留期间收到的真实增量。抓包按绝对索引预览，改变条数后仍可访问全部记录。
- 回归证据：`verify_workspace_stability.py`（代理路由、草稿、焦点、滚动、节点身份和迟到响应）、`verify_diagnostic_alignment.py`（原型六控件与按钮状态）、`verify_page_sizes.py`（七个分页区及失败恢复）。


## 公共分页与原生运行工作区（2026-11-15）

### Pagination

- 导出位置：`components/ui/controls/Pagination.vue`。受控属性`page/pageSize/total/pageSizes/disabled/label/unit`；默认条数选项10/20/50/100，账号显式传12/24/48/96。事件`update:page`和`update:pageSize`分别表达一次意图。
- 当前页使用`#77648f`背景、白字及`aria-current=page`。普通页白底深色字，禁用项独立浅色底。长页码保留首尾与当前邻页、省略号；窄屏前后按钮使用图标及无障碍名称，禁止横向溢出。
- 条数改变由列表所有者回到第一页、保留筛选、取消旧请求及丢弃迟到响应；组件不请求接口。首尾、零记录、加载中及当前页点击保持有效边界。
- `mode=cursor`用于工程历史和交互记录：传`hasPrevious/hasNext/canLatest`，监听`latest`；只显示真实当前页，不伪造总数或通过数字计算游标。原项目控制器保留快照、上一页栈、新记录提示与条数失败恢复。
- 账号、代理、请求、绑定会话、抓包索引、工程历史、交互记录共用组件。禁止再次复制页码/上一页/下一页HTML。菜单沿最近dialog投射，关闭菜单保持父窗口。

### 原生工作区生命周期

- 原生后端沿历史native293键，账号文案为“280 / 293 自动匹配”。内核按native_kernels选择280/293，操作冻结source_version和CAS；换版取消旧发行读取。两版共用忙碌/维护门禁，准备及进程数按实际版本展示；旧响应沿293别名。诊断内容入口同时接纳native280_cc_prepared与native293_cc_prepared。`verify_native_runtime_versions.py`覆盖版本、旧回执、部分就绪、诊断与明暗390/1280px。

- `/environments`使用`RuntimeEnvironments.vue`，资源/内核/时段为独立Vue编辑组件。访问过的分区保持挂载，CPU输入和时段草稿不随轮询或切区重建。CAS失败禁止重放原版本，提供重新读取；页签/关闭在提交中受控。
- 环境列表每轮成功读取后，隔离布局2的卡片自动通过既有`GET /runtime/api/environments/{id}/cpu-resources`补齐三角色实际CPU配额，每轮最多并行3个环境。缓存按环境ID和generation核对；换代或移除时清理，旧页面/旧请求/代次不符回执拒绝覆盖，编辑器读取或保存的新回执优先于并发摘要。列表轮询只刷新卡片，不覆盖表单草稿。配额显示真实核数，首读为“读取中”，单环境错误为“读取失败”并保留错误提示，历史布局为“未提供”；工具栏刷新和后续轮询可重试，离页取消请求。合同与CAS规则沿用[三角色在线CPU](../../orchestrator/backend/account-runtime-v3.md#scenario-三角色在线cpu与重建恢复)。
- `/tasks`使用`TasksWorkspace.vue`。构建插件`runtimeModule.ts`从单份原任务模板/控制器编译ES模块；主路由直接挂载DOM，运行时不创建iframe、不执行脚本字符串。CSS选择器通过AST限定在任务根，禁止正则替换误伤属性和类名；逗号组前导空格不能改变根类组合。
- `createRuntimeScope`拥有局部查询根、路由、事件、计时器、请求、DOM观察、SSE、WebSocket、终端。同路由子页共享实例；离开路由统一释放。全局应用DOM和主题不归任务控制器修改。原生路由仍使用网关交换的同源会话。
- 控制器的 `history.replaceState`只更新作用域地址快照，真实浏览历史由Vue Router统一写入。顶层工程/养号入口保留当前账号；重复、空白、非法及不可用account继续拒绝，不能静默选择首个账号。主状态与初始快照读取期间禁用账号选择，避免迟到预选覆盖用户输入。模型及项目池独立读取，未就绪的配置表单保持 inert。
- Docker前端构建同时复制原生源至 `/source/cc2api/legacy-web/`，与 `/source/cc2api/web/` 保持本地构建使用的相邻目录关系。Rust显式注册 `/tasks`、`/requests`等管理SPA入口，直达和刷新使用同一管理应用。
- 授权/续聊时才动态加载xterm及fit插件。保持原短票据、心跳、重连、输入许可及取消/恢复语义。读取页面不启动模型。脚本加载失败可在原窗口反馈。
- 标记`data-vue-managed`的目录选择、抓包与分页宿主由Vue拥有；旧控件增强器跳过宿主和`.fui-field`，避免双重包装。业务模块刷新不得删除这些组件内部节点。
- 运行详情及抓包复用已有Vue组件，代理选择继续提交ID/revision。旧`/runtime/`地址保留独立运行兼容。
- `TimeControl`保存当地`HH:mm`，确认才写入。时段关闭保留原已保存星期和区间，不把未提交草稿写回。

验证入口：`verify_shared_pagination.py`、`verify_page_sizes.py`、`verify_native_environments.py`、`verify_runtime_workspace_design.py`、`verify_task_login_design.py`、`verify_project_workspace_design.py`；使用合成接口、真实构建和隔离SQLite交付。

CPU首屏摘要回归：`verify_environment_cpu_summary.py`覆盖自动读取、并发上限、单环境失败恢复、编辑器回填优先、保存同步、换代与迟到响应、代次不符、历史布局及离页；`verify_native_environments.py`继续覆盖CPU草稿和CAS失败重读。

### 任务深层弹窗与工程现场一致性

- 任务账号配置按原型采用920px宽、17px圆角，名称、版本、网关/环境/额度三个入口和默认折叠的高级维护。名称使用独立display_name，原身份字段沿[账号CLI设置契约](../../orchestrator/backend/account-runtime-v3.md#scenario-账号-cli-版本与迭代抓包)。取消零写入；额度子窗关闭保留父草稿，网关及环境使用局部工作区并保持任务路由。工程执行配置只写版本及本空间抓包字段。
- `verify_task_account_config.py`直接比对原型的窗口、标题、字段、按钮、页脚等十组计算样式，并覆盖1440/720/390px。旧dark偏好及系统深色下仍固定亮色，正文、标签和操作文字对比度至少4.5；成功状态与错误状态分别着色。
- 额度详情复用原型`work-quota-*`结构：600px宽、身份栏、5小时/7天双卡38px主值、横跨的Fable25px主值、剩余值与北京时间重置、底部查询时间和显式刷新。真实0、窗口缺失和重置未提供分别表达；关闭、重开、导航使旧刷新回执失效。
- 任务账号的运行时段使用`RuntimeEnvironments`局部环境工作区，自动选择时段分区并保持任务路由；按任务账号ID定位真实环境。养号额度及独立旧入口的时段表单使用920px表单、固定标题/操作栏与可滚动正文。switch-field显式横向排版，避免旧form label的列布局覆盖。星期、最多8区间、环境时区及关闭时保留原配置沿用原合同。工程养号仅提交阈值；worker分支保留开关与小时区间。
- 任务账号切换代理使用专用`TaskProxyDialog`，复用`ProxyPicker`；关联与独立任务均可选目录或直连。主URL、任务根、卡片节点及焦点保持；保存后发送`runtime:accounts-refresh`局部回读，禁止触发整个navigate。目录选择提交ID/revision及任务快照版本，沿原服务端维护门禁。完整账号编辑继续使用局部Accounts工作区。
- 工程/养号的交互记录共用work-events/upgrade-events结构，分页位于记录后；独立验收的阶段取agent.verification，空态呈现三步待开始。计时仅替换文本并保留节点。
- 运行条件按真实admission展示状态；缺少CLI占用投影时显示未采集。目标列表读取当前work、passed、available_objectives和waiting_objectives，按项目与目标去重；禁止从目录排序推断完成/可执行状态。空交付记录采用带图标、标题与说明的居中空态。
- 验证：verify_task_feedback.py覆盖保存与取消、0/未知值、刷新迟到、局部代理、两空间及390/720px；verify_task_feedback_styles.py直接比对原型关键节点计算样式。

## Scenario: 共享操作反馈与任务选线

### 1. Scope / Trigger

修改通知、确认、账号测试结果、任务卡片目录摘要或代理窗口时适用。

### 2. Signatures

- `useToast().show(message, type='error', duration?) -> number`；type为success/error/info/warning，返回独立消息ID；dismiss/pause/resume按ID操作。
- `ConfirmationDialog`接受open/title/message/confirmLabel/danger/busy/error；发confirm/cancel，业务组件拥有请求。`useConfirmation().ask(options, signal?) -> Promise<boolean>`仅明确执行返回true。
- `OperationFeedback`接受status/message/label/identity及可选`buttonVariant`（共享Button变体），status为idle/loading/success/error；action仅由初次点击或明确重试发出。
- `TaskProxyDialog(accountId, accountName?)`发close/saved；API合同见[任务代理选择](../../gateway/backend/proxy-directory.md#scenario-任务账号选择与超时事务保护)。
- `createRuntimeScope(..., feedback?)`注入nativeNotify/nativeConfirm，离页取消未决确认；refreshAccounts发局部事件。

### 3. Contracts

- 全局单个FeedbackHost，底部居中最多显示3条、最多保留12条；相同类型和文本去重。success/info默认4000ms，error/warning默认手动关闭；悬停、键盘阅读及隐藏排队暂停计时。
- 通知DOM进入当前模态焦点范围，通过手动Popover顶层保持视口定位。父窗关闭、隐藏、移除和路由切换都要重新选宿主；观察器不能只匹配open状态。F8进入消息，通知内Esc只关闭消息并返回原控件。
- 账号测试以账号ID和请求身份隔离，同账号在途去重，离页撤销并丢弃迟到回执。结果显示在固定操作区，完整文本进入气泡；测试结束不改变卡片高度。
- 账号概览使用共享Button呈现操作层级：测试连接为主按钮，刷新用量为描边按钮，调度详情为轻量入口，停用为危险操作。测试结果气泡挂载在触发按钮所在的弹窗内，重试可通过键盘操作，Esc只关闭气泡并将焦点还给触发按钮。
- 账号卡片和概览以紧凑标签展示智能评分 `factors.score × 100`（一位小数）；摘要缺失时显示「评分待更新」。调度详情按新系数显示重置、排队因素，基础分与等待排序分分开标明；预计等待为null时展示压力回退和时长未知，旧响应缺新增字段时保持已有因素。
- 代理卡片名称及费用摘要单行省略，InfoTooltip展示完整信息。旧DOM增量刷新保留data-vue-managed属性及子树，Vue负责组件内部节点。
- 通知与错误以文本渲染；确认busy阻止关闭和重复执行，错误保留窗口。关闭和取消零业务写入。

### 4. Validation & Error Matrix

- 选线读取失败/版本冲突：保留候选并提供重新读取；重新读取成功后以服务端快照重置草稿。
- 测试业务失败/HTTP失败：独立错误状态及完整文本；一个账号结果不清除另一个账号结果。
- 父窗关闭/离页：持久通知保持可见；原生未决确认按取消收口。

### 5. Scenarios and Examples

正确：`show('已保存','success')`；失败使用error并保留阅读时间。错误：共享三秒计时器清除所有账号结果；正确处理是每个账号独立请求和状态。错误：把通知留在已移除的dialog中；正确处理是迁到当前有效宿主。智能分0.675显示「智能评分 67.5」；摘要缺失时显示「评分待更新」。

### 6. Tests Required

`verify_console_ui.py`覆盖七页七档、四列、过期代理、选线取消/冲突、独立账号测试、父窗取消/Esc/离页通知与焦点；`verify_ui_controls.py`验证组件预览。`verify_dialog_typography.py`及`verify_task_feedback_styles.py`与同步原型对比关键计算样式；`npm --prefix apps/web run build`验证类型与产物。
账号概览定向浏览器验证覆盖桌面与390px：四个操作尺寸一致且体现层级，测试中禁用，结果可查看及重试，Esc关闭气泡并恢复焦点；卡片和概览按当前模式展示评分，并区分零分与未观测。


## Scenario: 工作区分区加载与阅读布局

### 1. Scope / Trigger

调整任务首屏、会话交换、工程分区加载、主导航、交付阅读或更新面板时适用。

### 2. Signatures

- `api.openRuntime(): Promise<{ok: boolean}>` 交换 `POST /admin/runtime/session`。
- 正式账号与草稿分别读取 `GET /runtime/api/accounts`、`GET /runtime/api/accounts/login-drafts`。
- 工程主状态、项目池、模型与历史继续使用原 `/projects`、`/projects/catalog`、`/settings/project-requester`、`/projects/agents/{id}/work/page`；养号沿原 namespace 映射。

### 3. Contracts

- `TasksWorkspace.connect`先装入静态模板，以根节点inert控制会话交换期间的动作；成功后挂载控制器。失败显示重新连接，离页丢弃回执。字体就绪不门控页面可见性。
- `openRuntime`仅合并当前在途Promise，成功/失败后释放；鉴权凭据改变清除旧引用。后续入口重新交换，禁止将成功结果作为长期会话缓存。
- 正式账号与登录草稿独立完成和重试；草稿不能进入正式账号选择。工程主状态、目录、模型、历史分别加载；目录/模型未初始化时相应表单inert，模型读取完成前禁止启动。历史失败重试保留配置输入。
- 初始重试、页面、账号、空间、候选及文件读取均核对本轮归属。每次空间挂载清空上个空间的摘要；主状态和历史更新继续保留原表单草稿、节点与焦点。
- 任务及独立入口固定亮色，移除主题偏好和切换逻辑。六入口采用内容宽度页签、aria-current和focus-visible；窄屏局部横向滚动，选中项可达。
- 终端底栏的重复交付历史按钮移除。当前/最近目标提供交付入口，历史分区继续可达；两者共用冻结读取。完成、停止、待复验标签放入目标卡片，未知状态保留实际值。
- 交付弹窗位于各分区共同父层，禁止放在可隐藏的历史分区内。桌面宽度min(1440px,视口-32px)，高度视口-32px；窄屏边距8px。标题与候选固定，文件导航与源码/报告分区滚动，保留关闭、Esc、焦点恢复及旧回执失效。
- 系统更新优先呈现当前/可用状态与检查动作；有新版时显示安装计划。单行长说明使用普通正文；完整说明、组件维护和版本历史独立展开。活动维护与错误先于发布说明，成功记录紧凑呈现；原UUID/revision/SHA、取消、恢复和回退合同保持。

### 4. Validation & Error Matrix

| 条件 | 期望 |
| --- | --- |
| 会话慢或失败 | 框架可见，动作受控；重新连接重新交换 |
| 字体、草稿、模型、目录或历史慢 | 已完成区域可用，等待/错误归属本区域 |
| 草稿或历史失败后重试 | 正式账号可用，配置草稿保留 |
| 账号/空间切换或窗口关闭 | 原读取回执失效，后台工作保持原许可 |
| 旧dark偏好、窄屏与长内容 | 固定亮色，局部滚动，页面不横向溢出 |
| 更新已最新/陈旧/检查中/失败 | 主状态正确，原安装准入与恢复动作保持 |

### 5. Scenarios and Examples

正常：`Promise.all([api.openRuntime(), api.openRuntime()])`只产生同批一次交换；结束后的下一次调用重新交换。边界：历史等待期间编辑指南，历史失败重试后输入保持。错误用法：等待`document.fonts.ready`才显示整个页面；正确处理是结构先显示、字体独立完成。错误用法：从总览打开位于隐藏历史分区里的弹窗；正确处理是弹窗放在共同父层。

### 6. Tests Required

`verify_workspace_experience.py`覆盖1500ms慢请求、去重与失败重连、独立入口、区域重试、两空间目标状态、三视口及长内容。`verify_workspace_stability.py`覆盖草稿/节点/焦点与迟到响应。原型审计`audit_token_task_design.py`及更新/交付/配置浏览器回归继续执行；只读自动检查与安装等业务写入分别断言。完整后端测试中的抓包渲染提取使用函数边界，禁止依赖可变的分节注释。
