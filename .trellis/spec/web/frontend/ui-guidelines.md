# 控制台 UI 与复用控件

## 1. Scope / Trigger

- 修改账号、代理、令牌、任务、环境、授权登录的布局、表单、菜单、气泡或滚动行为时读取本规范。
- 设计基准（过渡期两套并存）：组件库、外壳与已迁移页面以 `doc/design/console-v2/mock.html`（第二版定稿，`#<画面>` 切换）为准；登录页以 `doc/design/console-v2/v1/mock.html#login`（第一版，仅该画面有效）为准；尚未迁移的页面主体在迁移前仍以 `doc/design/flower2api-concept.html` 为准。用户已基本认可账号页，后续增量以任务记录的最新决定为准。
- 组件库：`apps/web/src/components/ui/`（样式集中在 `components/ui/kit.css`）；主题运行时：`apps/web/src/theme/`。实际运行示例：`apps/web/ui-preview.html`、`apps/web/src/previews/UiPreview.vue`、`KitShowcase.vue` 与 `CompositeShowcase.vue`（组合组件）。外壳样式：`apps/web/src/console-shell.css`。
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
| `NumberInput` | `modelValue?: number \| string`，`label: string`，`id?`，`min?`，`max?`，`step?: number = 1`，`disabled?`，`readonly?`，`invalid?`；`update:modelValue(number \| string)`；`label-extra` 插槽 | 并发、RPM、百分比、端口、TTL等数值 |
| `ChoiceSelect` | `modelValue?: string`，`options: readonly ChoiceOption[]`，`label`，`name?`，`placeholder?`，`disabled?`，`required?`，`invalid?`，`portalTarget?: HTMLElement \| string`；`update:modelValue(string)`；`label-extra` 插槽 | 有限枚举单选，如认证、Billing、订阅类型 |
| `InfoTooltip` | `label: string`，`title?`，`delay?: number = 150`，`portalTarget?`；`trigger`插槽与默认内容插槽 | 只读完整统计、字段口径说明 |
| `SearchInput` | `modelValue: string`，`label`，`placeholder?`，`disabled?`；`update:modelValue(string)`、`search(string)` | 列表或会话搜索，业务方决定请求时机 |

新增组件（`@/components/ui/<目录>` 导入）：

| 组件 | 输入与事件 | 说明 |
| --- | --- | --- |
| `Segmented` | `modelValue: string`，`options: readonly SegmentedOption[]`（`value/label/count?/icon?/disabled?`；`count` 为数字或「—」等占位文字），`label`（无障碍名），`disabled?`；`update:modelValue(string)` | reka RadioGroup；托盘加白色滑块，可带计数 |
| `Switch` | `modelValue: boolean`，`label?`，`disabled?`，`id?`；`update:modelValue(boolean)` | 无关联可见文字时必须传 `label` |
| `Checkbox` | `modelValue: boolean \| 'indeterminate'`，`disabled?`，`id?`；默认插槽为文字；`update:modelValue(boolean)` | |
| `RadioCardGroup` | `modelValue?: string`，`options: readonly RadioCardOption[]`（`value/label/description?/disabled?`），`label`，`name?`，`disabled?` | 单选卡 |
| `InputGroup` | `prefix` / 默认 / `suffix` 插槽，内部放 `Input` | 整组 `:focus-within` 一个焦点框 |
| `Empty` | `title`，`description?`；`icon`、`actions` 插槽 | 空态 |
| `Skeleton` | 尺寸由 class 决定 | 减少动效时静止 |

组合组件（`@/components/ui/<目录>` 导入，样式在 `kit.css`）：

| 组件 | 输入与插槽 | 说明 |
| --- | --- | --- |
| `PageHeader`（`page-header`） | `title`，`description?`；`actions`、`description` 插槽 | 页面唯一 h1；底边距 18px；≤760px 标题与说明仅读屏可见（应用栏显示标题），无操作时不占高度 |
| `OverviewGrid` / `OverviewCard`（`overview`） | 卡片：`label`，`value?`，`unit?`，`caption?`，`tone?`（primary/success/warning/danger/info），`interactive?`；`icon`、`value`、`caption` 插槽 | 网格 4 列，≤1000px 2 列，≤600px 1 列。`interactive` 时根元素为 `button type=button`（正文与标签改为 `span` 并显式成块，外观不变），带悬停底色、`primary` 聚焦环与禁用态，`disabled`、`aria-label` 与点击由调用方传入（请求页「后续请求日志」卡） |
| `IconTile`（`icon-tile`） | `tone?`（另含 cc/agy/neutral），`size?: 'sm' \| 'md' \| 'lg'`（32 / 36 / 40px；sm 圆角 `block − 3px`、图标 14px，用于表格行内）；默认插槽为图标 | 装饰性，`aria-hidden` |
| `Toolbar`（`toolbar`） | 默认插槽（左）、`end` 插槽（右） | 窄屏换行；直接子级的 `Segmented` 横向可滚动 |
| `EntityCard` / `EntityBlock` / `EntityAction`（`entity-card`） | 卡片：`title`，`subtitle?`；`media`、`title-extra`、`subtitle`、`status`、默认、`actions` 插槽。操作：`tone?: 'default' \| 'primary' \| 'danger'`，`disabled?`，点击经属性透传 | 操作底栏按动作数等分，≤600px 按 96px 最小宽换行 |
| `TableCard`（`table-card`） | `title?`，`count?`；`toolbar`、默认（`Table`）、`footer`（分页）插槽 | 表格区横向滚动；最右列的 `TableHead` / `TableCell` 加 `fui-table-actions` 即固定在右侧，底色跟随行状态。省略 `title` 时头部加 `.is-bare`、工具栏占满整行，放一个 `Toolbar`（分段在左、`end` 插槽靠右，设计稿 `#requests`、`#blocks`）。单元格工具类（`kit.css`）：`.fui-table-fixed`（`table-layout:fixed`，单元格超长省略；列宽写在 `TableHead` 的宽度类上，窄屏隐藏列连同表头一起隐藏）、`.fui-table-num`（等宽数字）、`.fui-table-mono`、`.fui-table-strong`（700）、`.fui-table-end`（右对齐）、`.fui-table-ops`（行操作 flex 靠右、间距 4px）、`.fui-table-sub`（辅助值） |
| `FloatingSaveBar`（`save-bar`） | `count: number`，`hint?`，`cleanLabel?`（默认「已同步」）；`actions` 插槽 | 吸底；`count > 0` 显示「N 项待保存」并 `data-dirty=true` |
| `ModalDialog`（`modal`） | `title`，`description?`，`width?`（默认 820），`placement?: 'center' \| 'side'`；`v-model:open`；`media`、`title-extra`、`description`、`nav`、默认、`footer` 插槽；其余属性透传到弹窗面板 | 头部、`nav` 页签带（`.fui-modal-nav`，内边距 0 / 24 / 18，放 `Segmented`）与通栏浅灰底栏固定，只有内容区（`.fui-modal-body`）滚动；`title-extra` 在 `DialogTitle` 内，窄屏整组换行（多个徽标请包一层）；最大高 `min(840px, 100dvh − 32px)`。`placement=side` 为贴右抽屉：上下右各留 14px、高 `100dvh − 28px`、宽 `min(width, 100vw − 28px)`，定位用工具类覆盖 `DialogContent` 的居中定位（utilities 层压过组件层），高度由 `kit.css` 末尾未分层的 `[data-slot=dialog-content].fui-modal[data-placement=side]` 设置；`description` 插槽用于带按钮的说明（如完整请求 ID 与复制）。`style.css` 的全局 `[data-slot=dialog-content] { max-height; overflow-y: auto }` 未分层，`kit.css` 末尾用未分层的 `[data-slot=dialog-content].fui-modal` 覆盖，层内规则做不到 |
| `NoticeStrip`（`notice-strip`） | `tone?: 'success' \| 'warning' \| 'danger' \| 'info' \| 'neutral'`（默认 neutral）；默认插槽（图标 + 文字）、`end` 插槽（靠右徽标） | 设计稿 `.strip`：单行高 36px（9px 上下内边距 + 18px 行高），长文本换行增高。类名 `.fui-strip`——`.fui-notice` 已被通知浮层占用；原生模板可直接用该类 |

既有组件只做增量扩展：`Button` 新增 variant `soft`、`destructive-ghost`（`outline`/`secondary` 为次要填充、`ghost` 为文字、`destructive` 为危险浅底）；`Badge` 新增 variant `success/warning/info/cc/agy` 与 `dot` prop。表格单元格内「主值下一行」的辅助值用 `fui-table-sub`，字段说明用 `fui-field-help`。

主题运行时（`@/theme`）：`createTheme(seed): ThemeVars`、`parseThemeSeed(value): ThemeSeed | null`、`isValidSeedNumber(value, key)`、`readStoredTheme()`、`writeStoredTheme(seed | null): boolean`、`applyTheme(element, vars)`、`initTheme()`，以及 `DEFAULT_THEME_SEED`、`THEME_PRESETS`、`THEME_SEED_LIMITS`。主题设置页的编辑器纯函数（`theme/editor.ts`）：`THEME_SEED_KEYS`（12 个可编辑字段，界面与计数顺序）、`changedSeedKeys(draft, saved): ThemeSeedKey[]`、`normalizeHexInput(text): string | null`（大小写 `#rgb` / `#rrggbb` → 6 位小写）、`parseSeedNumber(key, input): number | null`（空串、非数、越界、步长不齐为 null，不钳制）、`presetIdOf(primary): ThemePresetId | null`。

`ChoiceOption = { value: string; label: string; disabled?: boolean }`。同一菜单的 `value` 必须唯一。空字符串是合法的业务选项值；`undefined` 表示尚未选择。

`NumberInput` / `ChoiceSelect` 的 `label-extra` 插槽（如「已修改」徽标）渲染在 `<label>` 元素之后的 `.fui-label-row` 内（flex，间距 3px，最小高 22px，徽标出现不跳动），不进入控件的无障碍名称；未传插槽时结构不变。`NumberInput` 的 `name`、`required`、`aria-describedby` 等原生属性透传到内部输入框。`SearchInput` 同样向内部输入框透传原生属性。调用方负责业务字段规整与提交，不在控件内部请求 API。

原生/静态稿当前复用入口：`renderNumberControl()`、`renderChoiceSelect(name, label, options, value, compact=false, searchable=false)`、`showUsageBubble()`、`renderDateTimeControl(name, label, value)`、`refreshDateControl(input)`。原生页面保持自身渲染和事件清理模式，不通过复制 Vue 的生命周期实现复用。

## 3. Contracts

### 视觉 Token 与层次

新 token 的默认值在 `apps/legacy-web/ui-foundation.css`（Vue 由 `main.ts` 全局引入，独立 `/runtime/` 文档以 `<link>` 引用，已在运行时桥接白名单），与 `apps/web/src/theme/tokens.ts` 的 `createTheme(DEFAULT_THEME_SEED)` 逐项一致，由 `apps/web/tests/theme.test.mjs` 校验。命名带分类前缀：

| 分类 | 前缀 / 名称 | 默认取值（第二版浅色） |
| --- | --- | --- |
| 颜色 | `--ui-color-*`：`layout/surface/fill/fill-hover/fill-muted/fill-subtle/fill-strong/track/line/mask/scrollbar`、`text/text-2/text-3/text-4`、`table-head/table-stripe/table-hover`、`primary/primary-hover/primary-container/primary-text/primary-ring/on-primary`、`success\|warning\|danger\|info` 及其 `-text`、`-bg`、`neutral-text/neutral-bg`、`cc-*/agy-*`、`brand/ink`、`on-ink/ink-text/ink-muted`（墨底文字，不随主题）、`fill-active`（侧栏选中底，柔光材质下随主色偏移）、`feedback-surface/feedback-text` | 主色 #6c54b4，正文 #0f1527，页面底 #f5f6fa |
| 字号 | `--ui-font-size-xs/sm/meta/md/title/card/heading/page` | 11.5 / 12 / 12.5 / 13 / 14 / 16 / 20 / 28px |
| 控件高 | `--ui-control-sm/md/lg` | 32 / 38 / 44px |
| 圆角 | `--ui-radius-btn/control/block/card` | 6 / 8 / 12 / 18px |
| 阴影 | `--ui-shadow-card/pop/modal/raised/knob/side/bar`（side 侧栏、bar 移动端应用栏） | 见 ui-foundation.css |
| 其它 | `--ui-space-unit`（4px）、`--ui-font-family`、`--ui-font-family-mono` | |

- 字号与控件高 = 种子 + 阅读档位（`--ui-tier` 由三档媒体查询设为 0/1/2）。派生块挂在 `:root, [data-ui-theme]` 上，局部主题容器能独立重算。
- 页面与组件只引用新 token，不写死颜色和圆角；悬停、按下等设计稿未给的状态色用 `color-mix()` 由 token 混合。`theme.test.mjs` 静态校验 `components/ui`、`kit.css`、`console-shell.css`、`ui-foundation.css`、`pagination.css` 及 `Dashboard.vue`、`AppNavigation.vue`、`Login.vue` 中颜色字面量只出现在 `--ui-color-*`/`--ui-shadow-*` 定义里，`border-radius` 只取 token。
- **旧层（过渡期冻结）**：未迁移页面仍引用的 shadcn 变量（`--primary/--border/--muted-foreground…`）、旧控件 token（`--ui-accent/--ui-border/--ui-text…`）与阅读尺寸（`--ui-font-body/--ui-control-height…`）合并在 `style.css` 与 `ui-foundation.css` 的旧层块，取值不变、不跟主题变化；页面迁移时改用新 token，父任务最终复核时按旧名清零删除。
  - 组件换新使未迁移页面外观倒退时（例：`SystemUpdates.vue` 的 Card 传 `shadow-none`，组件又去掉了描边，卡片失去边界），在页面层用旧层 token 或工具类恢复原外观（该例加 `border`），并随页面迁移删除；不回改组件。
- **层叠**：组件样式在 `kit.css` 的 `@layer components`；业务传入的 Tailwind 工具类可覆盖组件默认值，未分层的页面规则在页面迁移前仍压过组件。不得新增未限定页面作用域的 `[data-slot=…]`、`.fui-*` 全局覆盖。全局兜底焦点框在 `@layer base`。
- 卡片、弹窗、表格的根元素不设颜色、行高、字体等可继承属性，内部内容由页面基准决定；组件自带的文字部件（标题、说明、表头、辅助值）显式设置。第二版页面基准为 13px / 1.55 / `--ui-color-text`。
- **主题运行时**：浏览器只保存种子（`localStorage['flower2api.theme']`，`version: 1`），任一字段非法、存储读取抛错时整体回退默认；`main.ts` 在 `createApp` 前调用 `initTheme()`，首次渲染即为用户主题。`applyTheme(el, vars)` 写内联变量并标记 `data-ui-theme`，用在容器上只影响子树；弹层默认 Teleport 到 body，局部主题内需传 `portalTarget`。派生文字色与按钮文字对比度不低于 4.5（白字不足时改深色字，两者都不足时压暗主色）。

- 按CSS视口采用三档阅读尺寸：小于1920px、1920～2559px、2560px及以上。新组件：正文/按钮/输入 13/14/15px，辅助文字 12/13/14px，弹窗标题 20/22/24px，页标题 28/30/32px；控件高 38/40/42px（小号 32/34/36px）。旧层阅读尺寸（正文 14/15/16px、控件 40/42/44px）在页面迁移前保持不变，html 根字号仍取旧层 `--ui-font-body`。禁止整页zoom或按物理像素缩放。
- 常用间距采用4/8/12/16/24px，页面容器24–40px；窄屏16–20px。页面主内容使用柔和浅底，内容卡片使用白色和轻边框。
- 字体采用 Inter Variable 与明确的中文系统回退；关键数字使用等宽数字或 JetBrains Mono Variable。字体资源本地托管，许可证参考 `doc/design/font-licenses.txt`。控件当前通过 `--ui-font` 使用字体栈，实际字体资产接入由页面迁移完成。
- 成功/执行状态用绿色，等待/临近到期用琥珀色，失败/已过期用红色，紫色用于选中与偏好。颜色同时配文字含义。
- 焦点只画在完整交互容器上：数字输入、带图标的搜索栏用 `:focus-within`；内部输入框去掉重复 outline/shadow。键盘焦点必须可见，强制颜色模式保留系统高亮。
- 组件状态约定：键盘焦点为 2px 主色外框（输入类为主色细环加 `primary-ring` 外圈）；禁用不透明度 .45、`not-allowed`；加载沿用 `aria-busy`；过渡 .15s，`prefers-reduced-motion` 下无过渡与动画；`forced-colors` 下保留系统高亮。

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
- 使用“全部/错误/处理中”分段（`Segmented`，`radio` 角色，名称为标签加计数，如「错误 7」）快捷选择，保留账号、时间与关联ID条件；具体结果与快捷结果属于同一维度：选了具体结果时分段值为空（无选中项），避免相互叠加成无意的空集合。
- 账号匹配覆盖请求账号与各次尝试账号；完整关联ID匹配请求、响应及上游ID。实际诊断接口支持 `outcome=errors` 六类错误集合；分页返回独立于当前结果维度的 `counts.all/errors/processing`，保留其余查询条件。每条记录的 `last_attempt` 由存储查询投影；不得在单页数据上伪造全量统计或制造逐行详情请求。
- 详情与列表采用清晰对比度：主值用 `--ui-color-text`，辅助标签用 `--ui-color-text-3`，不对内容容器使用透明度统一弱化正文。
- 头部处理保留动作文字：删除行 `danger-bg` 底、左侧 3px `danger` 竖线与危险色标签，保留为 `success`、运行时处理为 `primary-container`、提取上下文为 `info`。筛选动作时高亮继续生效，不能只靠颜色传达含义。
- 采集按发生时模式和capture_status判断，模式切换只影响后续请求；组装中间值与最终TLS证据分开。空字段展示未观测，0毫秒/0Token保留真实零值。

### 会话封禁列表

- `SessionPolicyBlocks.vue` 的每5秒轮询沿用已提交的会话前缀；搜索框草稿仅在显式查询时提交。后台读取使用独立请求状态防止重叠，保持刷新按钮文字、分页可用状态和已有空态；手动查询可取消后台读取，迟到回包沿代次丢弃。
- 空态使用单层 `TableRow > TableCell.session-block-empty` 内放 `Empty`（图标、标题、说明与重置查询）。`TableEmpty` 自带表格行，不能再包进 `TableRow`。页面样式在 `src/session-blocks.css`（`@layer components`），组件不再有 scoped 样式。
- 状态为 `Segmented`（label「封禁状态」）四段：封禁中 / 已到期 / 已解除 / 全部记录，计数取接口 `counts.active/expired/released/all`（同一前缀、不随状态筛选变化），缺失显示「—」。表格单元格时间省略时区后缀，时区与 5 秒刷新只在工具栏末尾说明一次。
- 验证入口 `python3 deploy/flower2api/verify_session_policy_blocks_ui.py`：覆盖390/1440/1920/2560px，慢读取期间按钮与面板尺寸稳定、轮询跳过未完成读取、搜索草稿保持、空态与重置、解除确认、分页及设置字符串保存。

### 系统设置表单与草稿

- `.settings-inline-note` 统一使用块级布局，链接与段落共享顶部分隔线和垂直间距；行内链接的顶部边框会覆盖上一行说明。`verify_session_policy_blocks_ui.py` 在390/1440/1920/2560px断言封禁记录链接的边框顶部不小于时长说明底部，避免仅检查 `text-decoration:none` 漏掉相邻元素覆盖。
- 以现有 `Settings.vue::saveSettings` 的真实键集合核对完整性，按用途分组。保存载荷为 `fieldBindings` 全部键（`settingsSchema` 57 项加会话封禁 2 项，共 59，与页头「59 项配置」一致）；新增字段时同步 `verify_remaining_pages.py` 的计数断言。新增分组或换肤不能删除字段、访问预设或预热记录入口。
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
- 1680px及以上账号采用四列，卡片按可用宽度均分。390px单列；1280px两列；1340–1600px三列。同排卡片等高，运行指标和操作栏对齐。单列卡片按自身内容撑开。禁止以提高列数压缩卡片信息。
- 所有可点击按钮、链接、页签与菜单项使用手型指针。实际disabled按钮显示禁用指针并由浏览器禁止点击；组件型禁用链接维持原有事件屏蔽。
- 原生任务与环境复用 `apps/legacy-web/ui-controls.js`，保留原生字段的name/value、约束及input/change事件。菜单、时间面板的Escape先关闭最上层；选择和时间取消不修改原字段。
- 原生页和Vue页滚动条在滚动时显示，800ms无滚动后隐藏滑块；轨道宽度保持稳定。
- 回归入口：`verify_viewport_interactions.py`、`verify_runtime_workspace_design.py`、`verify_remaining_pages.py`；使用合成接口。

### 外壳与登录页（第二版）

- **类名契约**：行为脚本与业务代码依赖以下类名与无障碍名称，改外壳时保留，只改样式：`.console-shell`（`.sidebar-collapsed`、`.console-native-tasks`）、`.console-sidebar`、`.console-brand-row`、`.brand-update`（有新版本时类名恰为 `brand-update has-update`）、`.navigation-item.is-active`、`.navigation-count`、`.navigation-running`、`.sidebar-exit`、`.desktop-sidebar-toggle`、`.mobile-navigation-panel`、`.toolbar-page`、`#console-content`、`#admin-password`、`.settings-save-bar`；「flower2api 首页」「系统更新」「打开主导航」「收起侧边栏 / 展开侧边栏」「退出」「显示密码 / 隐藏密码」。
- **尺寸与断点**：侧栏宽 248px（761–1000px 为 224px，≥1920px 为 264px，≥2560px 为 280px），折叠 76px；≤760px 隐藏侧栏，显示应用栏（标志、页面标题、菜单按钮）与抽屉。内容区内边距 24 / 28 / 48px（按 `--ui-space-unit`），任务页（`.console-native-tasks`）为 0。
- **侧栏**：`position: fixed` 占满视口高；品牌行与底部管理员区不收缩，只有导航区 `overflow-y: auto`。品牌行只有标志方块是首页链接（名称与版本号同一行，不能嵌套链接）。标志沿用品牌合同（[frontend-guidelines.md](./frontend-guidelines.md)）的 `public/favicon.svg?v=flower2api-pink-04`，放在 `ink` 方块上，透明的花心与通道透出墨色；只有侧栏与登录品牌区的图片带 `alt="flower2api 标志"`，应用栏、抽屉等装饰位置为空 alt。版本号常态 `fill` 底、`text-2`；有新版本 `success-bg` / `success-text` 并带 `arrow-up-circle`；折叠后只显示图标。运行中徽标为 0 时用中性色（`data-idle=true`）。底部单独一组为「主题设置」（`Palette`）与「系统设置」。
- **移动端抽屉**：继续用 `Dialog`（焦点圈定、Esc、路由切换关闭）。定位通过传入工具类覆盖 `DialogContent` 的居中定位，`console-shell.css` 末尾用未分层、更具体的 `[data-slot=dialog-content].mobile-navigation-panel` 铺满视口高——全局弹窗高度规则未分层，层内规则压不过它。不用 `!important`。
- **应用栏标题**：取 `Dashboard.vue` 的标题表，与各页页头一致（账号为「账号管理」）；新增路由时同步补表。
- **应用栏页面操作位**：`#console-toolbar-page-actions`（`display: contents`，位于 `.console-toolbar-actions` 内、菜单按钮之前，间距 6px）。页面用 `<Teleport defer to="#console-toolbar-page-actions">` 放 36px 图标按钮，类名 `.console-toolbar-action`（外观同菜单按钮，`aria-expanded=true` 时主色浅底）；外壳不感知业务。桌面应用栏隐藏，按钮随之不可见；嵌入模式（如 `workspace-account-id`）不放。目前只有账号页的「搜索账号」。
- **登录页**：两列（深墨品牌区 + 表单），品牌区纹理为内联 SVG（第一版 canvas 几何），表单控件为组件库大号控件 44px。登录行为、错误文案、凭据存储（`localStorage['claude-code-gateway_auth']`，退出清除）不变。品牌区不显示版本号：版本接口需登录后访问。≤760px 隐藏品牌区，表单上方显示标志与名称。

### 系统更新弹窗

- **入口与路由**：`SystemUpdateDialog.vue`（基于 `ModalDialog`，宽 768，面板类名 `.system-update-dialog`）由 `Dashboard.vue` 在 `updatesOpen` 为真时挂载，关闭即卸载并停止轮询。`router.ts` 的 `updates` 子路由渲染 `Accounts.vue` 作背景；`route.fullPath` 变化时 `updatesOpen = route.name === 'updates'`。关闭时若仍在 `updates` 则 `router.replace({ name: 'accounts' })`，并刷新版本号角标。弹窗内 router-link 跳转后自然关闭。
- **视图**：`[data-update-view=overview|progress|history|maintenance|details]`；未接入或更新服务不可用时为 `uninstalled`，始终显示「当前版本：x」。主视图规则：没有操作记录→概览；`busy`、`reconcile`、`succeeded_cleanup_pending`，或本次弹窗内观察到该操作在维护中（`followed`）→进度；其余已结束操作在概览显示一行「上次操作 · 阶段 · 版本 · 时间」，「查看记录」进入进度。版本记录、维护详情、操作详情是带「返回」的二级视图（返回栈）。
- **写请求**：冻结合同同 [平台在线更新](../../platform/deploy/platform-online-update.md)。概览底栏「安装更新」直接冻结并提交最新版本，等待上限取安装方式区的 `NumberInput`（「在途等待上限（分钟）」，1～120，默认 1）；提交后锁定输入，网络不确定时重发同一冻结对象；409 显示「现场版本已经变化…」并禁用安装，不自动重放。版本记录列表中的安装（含最新）、回退、恢复都先打开 `ConfirmationDialog`（「确认安装更新 / 确认版本回退 / 恢复本次操作」），前两者带等待上限，默认 1。
- **步骤表**：`lib/updateSteps.ts` 的 `updateSteps(operation, { snapshot, migrate, busy })` 返回 `{ rows, done, total, outcome }`。规范顺序 `preparing → draining → [snapshotting → migrating] → switching → verifying → committing → cleaning`（`snapshot` 取 `status.migration_capability`，`migrate` 取目录中目标版本的 `migrations` 或记录中出现过 `migrating`）。结局阶段（succeeded、succeeded_cleanup_pending、failed、cancelled、restored、reconcile、prepared）不成行；带快照部署越过取消边界的第一次 `switching` 不成行，进行中仍显示「等待在途完成」；重复阶段只留最后一次；维护中补「待执行」；无 `steps` 的旧操作按当前阶段推出（时间显示「—」）。行内说明只取真实数据（阻塞数、快照、各库迁移状态）。行为 `[data-update-step][data-state=done|active|pending]`。
- **钩子**：摘要格 `[data-update-tile=current|latest|published|checked|target|operation|updated]`，版本卡 `[data-release-card]`、展开详情 `[data-release-details]`；关闭按钮名「关闭」。样式在 `src/system-update.css`（`@layer components`，类名前缀 `su-`，只取 token）。
- **示例**：带快照部署的记录 `preparing, draining, switching, snapshotting, migrating, switching, verifying` 已记录部分显示为 `preparing, draining, snapshotting, migrating, switching, verifying` 6 行（维护中再补 `committing, cleaning` 待执行），第一次 `switching` 并入真正的切换。错误用法：把 `steps` 原样逐条成行，越过取消边界的切换会显示成「切换平台服务」已完成、快照仍待执行；正确处理：一律经 `updateSteps` 推导。错误用法：自动化脚本 `goto('/updates')` 后直接点背景页导航（被模态挡住）；正确处理：先关闭弹窗，等地址回到 `/`。

### 主题设置页

- **入口**：`/theme`（`name: 'theme'`，`ThemeSettings.vue`）。网关 `router.rs` 的 SPA 列表与 `frontend_routes_support_direct_navigation_and_reload` 同步登记 `/theme`、`/theme/`；应用栏标题表 `theme: '主题设置'`。
- **草稿语义**：
  - `saved = readStoredTheme() ?? DEFAULT_THEME_SEED`；`draft` 是可编辑种子。只有通过 `normalizeHexInput` / `parseSeedNumber` 的值写进 `draft`；无效输入只记错误（`#theme-<键>-error`），画板不变，保存禁用。
  - 页头 `[data-theme-sync]` 显示「N 处修改待应用」（N = `changedSeedKeys(draft, saved).length`）；有无效输入时追加「M 项输入无效」（`data-invalid=true`，错误色）；都没有时为「已同步」。分类分段的 `count` 为该分类已修改或无效的字段数（同系统设置分类计数），无效输入藏在其它分类时也能定位。≤760px 时页头说明仅读屏可见，由 `.theme-mobile-state` 补一行可见状态。
  - 「已修改」与单项恢复（「恢复已保存的<字段>」）都相对已保存值；撤销草稿回到已保存；恢复默认只改草稿，仍需保存。
  - 保存：先 `writeStoredTheme(等于默认 ? null : draft)`；返回 false 时提示失败，控制台不变。成功后 `applyTheme(document.documentElement, createTheme(draft))`。
  - 预设只写主色，选中态由 `presetIdOf(draft.primary)` 反查（`[data-preset=<id>][aria-pressed]`）。
- **预览画板**（`theme/ThemePreview.vue`）：
  - 同源 `<iframe src="/?theme-preview=1">` 固定 1440×900。`load` 与草稿深度变化时，把 `createTheme(draft)` 写进 iframe 文档根，覆盖它自己 `initTheme` 应用的保存值。
  - iframe 设 `inert`、`tabindex=-1`、`pointer-events: none`。画布负责缩放（10%–150%：按钮以中心为锚 ±10 个百分点，滚轮以指针为锚、每 100px ±10）、拖动平移与「适应画布」（`[data-theme-zoom]` 显示百分比）。
  - `Dashboard.vue` 读到 `route.query['theme-preview'] === '1'` 时以 `checkUpdates=false` 挂载，画板内不发 `POST /runtime/api/system-updates/check`，只读摘要照常读取。
- **离开保护**：`onBeforeRouteLeave` 在有改动或有无效输入时打开 `ConfirmationDialog`（「放弃未保存的主题修改？」/「放弃并离开」）；去往 `login` 直接放行，因为 `logout()` 已先撤销会话。有改动时登记 `beforeunload`。
- **过渡态**：任务与工程、运行环境在子任务 6 前写死颜色，不随主题变化。
- **示例**：
  - 错误用法：在当前文档里直接渲染 `Accounts.vue` 做预览，Teleport、固定定位和媒体查询都会逃出画板，外壳也按真实视口排版。正确处理：用 iframe 隔离。
  - 错误用法：`Number('')` 得 0 后写进草稿（圆角 0 合法，会悄悄改值）。正确处理：经 `parseSeedNumber`，空串为 null。
  - 错误用法：用 `fixture.checks` 判断画板是否检查更新（刷新后顶层外壳会合法地再检查一次）。正确处理：按 `request.frame.parent_frame` 归属记录子框架请求。

### 布局与信息组织

- 左侧为可折叠导航，右侧直接从页面标题开始。当前基准取消“我的工作空间”卡片和重复顶部工具栏；折叠/展开放到侧栏底部管理员区域。
- 品牌旁保留版本与系统更新入口；折叠后可见，图标入口有可访问名称。移动端保留紧凑导航按钮，所有模块仍可达。
- 侧栏按视口高度布局；预览条滚出后释放对应高度。长菜单在侧栏内部滚动，不在页面底部露出侧栏背景缺口。
- 详情/编辑工作区固定标题和页签，仅正文滚动；复杂表单在桌面扩宽并分组。保留草稿、取消和保存语义；不以删除字段或隐藏功能入口换取简洁。
- 同一账号的概览、配置、调度、环境与诊断使用同一工作区：820px 居中 `ModalDialog`（面板类 `.account-workspace`），页签为 `nav` 插槽中的 `Segmented.account-workspace-tabs`（role=radio，「调度」有排队时带排队数）。有页签时面板固定高 `min(840px, 100dvh − 32px)`，切页签只换内容区、外框不动；新建账号无页签、按内容高。页内导航保持上下文，二级弹窗主要用于独立确认。
- 转发方式与代理选择属于主要配置；认证字段放在高级配置。排队数量直接可见。
- 账号状态栏使用单行弹性布局，长状态文字省略显示，排队按钮保持可见且不收缩。徽标显隐和数字变化保持状态栏行高、卡片尺寸及相邻卡片位置稳定，避免轮询刷新引发布局跳动。
- 滚动条在滚动时显示，停止800ms后250ms淡出，轨道宽度稳定。采用减少动画偏好时缩短动画，高对比模式采用系统颜色。这一行为目前在静态稿中实现，正式迁移时沿用同样验收。

### 正式控制台与账号首批迁移

- 账号卡片顶部展示平台徽标（名称旁），其下控制行右对齐展示“接收请求”开关与“停用账号／启用账号”按钮；开关只改变 API 准入，账号按钮沿整体工作控制。卡片及概览在正常启用时省略整体状态提示。收尾时显示「正在收尾」及尚未结束的已接纳请求数，已停用和待核对各自显示对应状态。
- 反重力卡片展示平台额度及重置时间。网关请求数和 Token 在账号概览的「网关用量」展示。记录缺口随实际窗口标识，真实零保留为零。
- `ExecutionNodeBadge` 统一为 `i-server` 图标加单行节点名称的 `/nodes` 链接。账号页并入代理与环境信息栏，环境卡片并入标题下的账号信息栏。节点 key、类型与观察说明放入提示框，异常图标保留提醒。历史请求沿自身 `execution_location` 展示；本机缺名称时显示“默认本机”，其它节点缺名称时使用原节点 key；缺节点时保留未观测或无执行尝试。
- 反重力账号卡片和账号概览展示固定的本机 API 执行归属。名称读取 `/runtime/api/nodes` 中 `kind=local` 的节点。目录暂不可用时保留已取得的名称，首次读取失败时显示「默认本机」。Claude Code 账号继续按任务账号绑定及缓存观察展示。浏览器回归覆盖无任务账号绑定的反重力、本机名称、读取失败、详情和节点管理跳转。
- 账号与环境卡片使用 `PlatformBadge(platform)` 独立标注 Claude Code／反重力，分别为棕色／蓝色，套餐独立展示。请求列表使用发生时 `context.platform`，缺失显示“平台未记录”；账号名称单行省略，资料气泡保留完整名称和邮箱。`verify_execution_node_visibility.py` 覆盖三入口跳转、历史节点、平台未知、顶部独立控制、提示框关闭与1440/720/390px布局。

- 节点管理导航和卡片使用共用SVG sprite的i-server；运行环境继续使用i-box。节点页先显示概览卡和节点实体卡，账号归属/迁移区保持原确认与轮询（第二版合同见下方「第二版节点管理与系统设置」）。主机指纹、认证方式、路径及批次收进详情；同批已就绪节点隐藏相同来源到目标的箭头。stopping显示停止原组件，旧协议backed_up显示已停止待切换。

- `apps/web/src/style.css` 保留旧层主题变量名（过渡期冻结）；外壳为第二版白色侧栏与浅色内容区（`console-shell.css`）。字体来自 `src/assets/fonts/` 中的本地 WOFF2，许可一并保留；离线导出须把同源字体内嵌，不能依赖构建目录外链。
- `Dashboard.vue` 在品牌旁保留 `/updates` 入口：普通点击打开系统更新弹窗、地址不变，按住修饰键在新标签打开 `/updates`（见「系统更新弹窗」节）。版本优先使用 `usePlatformVersion` 读取的当前控制镜像版本；旧端回退到已验签目录精确匹配的current_release，缺省显示“版本”。移动入口缺省显示“系统更新”。桌面折叠位于管理员区域，偏好键为 `flower2api-sidebar-collapsed`，存储失败仍保持本次会话选择。移动导航保留原七个模块。
- 正式账号仍使用既有分页及每5秒读取。卡片显示三种额度窗口，7天Sonnet数据类型继续兼容；完整旧配置/画像/评分等信息位于详情。代理公共摘要仅含protocol/host，编辑及OAuth代理输入默认遮蔽认证信息。
- 账号数字草稿由 `numberDrafts` 保存 `number|string`，`applyNumberDrafts()` 在提交边界检查非空整数再写入原数字字段；原范围校验与 `accountUpdateDelta` 继续生效。认证编辑默认收起，新建默认展开，全部旧字段保留。
- `useActiveScrollbars()` 由应用根调用一次，通过捕获真实scroll标记容器，800ms后清理；卸载清理监听器及全部计时器。窗口标题/页脚固定，正文独立滚动。
- **第二版账号页（`Accounts.vue` + `src/accounts.css`，`@layer components`，只取 token，由 `Accounts.vue` 引入）**：
  - 卡片用 `Card.account-card` 加原子组件，不套 `EntityCard`（设计稿 `.acc` 与 `.ent` 内边距、名称字号、操作栏尺寸不同，且名称区是打开详情的按钮）。网格 `.account-card-grid`（不再带 `.resource-grid`，其未分层卡片规则会压过新样式）。
  - 类名契约（脚本与业务依赖，只改样式）：`.account-card-grid > [data-slot=card]`、`.account-card-topline`（纵向含身份行与 `.account-work-controls`）、`.account-identity-text h3 / p`、`.account-status-switch`（`Switch`，`aria-checked` 取 `work_control.api_accepting`）、`.account-work-toggle`、`.account-network`、`.account-health`（`NoticeStrip`，固定 36px）、`.account-queue-alert`、`.account-routing`、`.account-live-metrics button`、`.account-card-actions`、`.account-workspace`、`.account-workspace-tabs`、`.account-form-section > h3`、`.forwarding-options [role=radio]`、`.account-diagnostic-summary / -actions / -technical`、`.approved-oauth-dialog`（440px）。
  - 健康条色调 `accountHealthTone(account)`：`status=disabled`→neutral；`status=error` 或 `auth_error`→danger；限流 / 短冷却 / `v3_scheduling_error`→warning；其余 success。文案逻辑不变。`statusStyle()` 只返回 `label`。
  - 进度条色调 `usageBarTone(pct)`（`lib/subscription.ts`）：≥80 danger，≥50 warning，否则 success；写作 `<i :data-tone>`，样式按 `data-tone` 取 token。数值文字色调函数（`rpmClass` 等）返回 `is-warning / is-danger / is-success / is-muted`。
  - 共用子组件：`PlatformBadge` 为 `Badge`（cc / agy / secondary，保留 `data-platform-badge`）；`ExecutionNodeBadge` 的 scoped 样式在 `@layer components` 内，字号默认 `--ui-font-size-sm`，所在区域可覆盖；`ProxyPicker`（账号编辑、授权登录、任务选线与请求筛选弹层共用 `.proxy-picker-*`）样式在 `kit.css`，帮助文字在触发器下方。
  - ≤760px：分段换短标签（全部 / 正常 / 关注 / 已停用，`useMediaQuery`）；平台筛选与搜索框组成的搜索行默认收起，由应用栏「搜索账号」展开并聚焦，搜索词非空或平台不是「全部平台」时保持展开。
- **第二版请求记录、代理、令牌、会话封禁（各页一份 `@layer components` 样式：`src/request-records.css`、`proxies.css`、`tokens.css`、`session-blocks.css`，只取 token，由页面组件引入）**：
  - 页面结构：概览卡（`OverviewGrid`，请求与代理）→ `TableCard`（请求、封禁无标题；代理「代理线路 total / all 条」、令牌「访问令牌 N 个令牌」）→ `Table.fui-table-fixed`，单元格主值加 `.fui-table-sub` 辅助值，分页在 `footer`。弹窗换 `ModalDialog`：代理编辑 680、批量导入 520、令牌编辑 760（底栏按钮用 `form` 属性提交）；请求详情为 `placement=side` 宽 1020 的抽屉，页签保留 `tablist / tab / tabpanel` 与方向键切换，外观借用 `.fui-segmented` / `.fui-segmented-item[data-state]`。
  - 请求页：概览卡全部 / 错误 / 处理中取 `counts`，第 4 张「后续请求日志」为 `interactive` 卡，点击在 info / debug 间保存 `request_diagnostics_log_mode`，读取中或保存中禁用并显示「保存中…」，失败用 `NoticeStrip role=alert`；页头不再放日志下拉。列宽 15 / 13 / 13 / 13 / 10 / 15 / 5 / 9 / 7（账号列放平台与执行节点徽标，徽标不截断、放不下换行）；Token 列两行辅助值（缓存读 · `[data-cache-write]` 缓存写；`[data-average-tps]` 平均 TPS）。
  - 代理页：第 4 张卡取 `counts.expiring`，说明「另有 N 条已过期」/「暂无已过期线路」，缺失为「—」与「按到期时间统计」；延迟 >120ms 为 `warning-text`、有值为 `success-text`；到期徽标已过期 danger、7 天内 warning、其余中性。列宽 16 / 13 / 9 / 9 / 13 / 20 / 20，使用情况列含前两位使用者（网关账号为按钮）、处理中请求数与展开图标按钮（无障碍名称「查看使用账号 / 收起账号」）。
  - 令牌页：名称搜索只过滤已读取的令牌，计数「m / N 个令牌」，无结果「没有匹配的令牌」；启停为 `Switch`（名称「{令牌名}启用状态」）。`AccountScopePicker` 样式在 `tokens.css`。
  - 定位契约（脚本与组件逻辑依赖，只改样式）：`.request-records`（表头 9 个 `th`、详情关闭时页面只有一个 `tbody`）、`.request-extra`、`.request-account-identity`（内容恰为账号名）、`.request-workspace`（`InfoTooltip` 的 `portal-target`）、`request-tab-* / request-panel-*`、`data-request-copy`、`.request-definitions`、`.request-attempt-summary`、`.request-chain-card`、`.request-performance-card`、`.request-token-metrics`、`[data-native-stages]` 及 `NativeStageDetails` 的 `request-*` 类；`.proxy-page`、`.proxy-panel`、`tr[data-proxy-id]`、`.proxy-row-actions`、`.proxy-user-chips`、`.proxy-expand`、`.proxy-expanded`、`.proxy-account-identity`、`.proxy-editor`；`tr.token-row`、`.approved-token-editor`、`.token-name`；`.session-block-panel`、`.session-block-records[aria-busy]`、`.session-block-empty`、`tr[data-block-id]`。
  - ≤760px：请求表只留时间、账号、结果、操作；代理表只留线路、到期、操作，状态徽标与可点击的使用摘要 `.proxy-mobile-usage` 移到线路名称下方，后者是展开使用账号的入口（使用情况列收起后不能丢失该入口），行操作只显示图标、文字留给读屏；令牌表隐藏可用账号与创建时间（范围移到名称下）；封禁表隐藏令牌、封禁时间与本地拦截（补充行显示在首列与状态列）。单元格改为可换行、高度随内容，页面无横向滚动。
- **第二版节点管理与系统设置（`src/nodes.css` 由 `Nodes.vue` 引入，承载 `AccountNodeSelector` / `AccountNodeMigration` 与两个节点弹窗；`src/settings.css` 由 `Settings.vue` 引入，替代已删除的 `settings-design.css`；均为 `@layer components`，只取 token）**：
  - 节点概览卡（`OverviewGrid.nodes-overview`，全部由已读取的节点列表计算）：节点（说明「N 台本机 · N 台远程」）、远程服务器（远程节点中待处理数 >0 为「N 台待处理」，否则「全部正常」，无远程节点为「尚未添加」）、归属账号（`totalAccounts`，反重力归属读取失败为「—」）、待处理。待处理按 `attention(node)` 每台只计一类原因：有 `removal` 时仅 `needs_check` 计「移除待重试」；`enabled=false` 不计；无观测、`stale` 或 `unreachable` 计「需检查连接」；`preparation.state` 为 `failed / needs_check` 计「组件异常」。说明行只有一类原因时为「需检查连接 / 组件同步异常 / 移除待重试」，多类时按该顺序「N 台需检查连接 · N 台组件异常 · N 台移除待重试」，为 0 时「全部正常」；说明允许换行。
  - 节点卡为 `EntityCard.node-card`（`IconTile size=lg`；远程副标题 `.node-address` 等宽），状态文案沿 `state()` 不变，徽标 `Badge dot` 色调 `stateVariant(node)`：连接正常 success；待检查、观测已过期 warning；连接异常、移除待重试 destructive；移除中 info；已暂停接单、已移除 secondary。资源 `dl.node-resources` 四列（「未采集」为 `.is-empty` 弱化色），最近检查 / Docker / 运行组件在 `EntityBlock.node-meta`（用 `span / time / b`，不用 `dd`，卡内 `dd` 末项保持「归属账号」）。操作为 `.node-actions` 一行 `Button size=sm`（不用等分底栏），「改名」ghost、「移除」`destructive-ghost` 靠右；按钮名称与禁用条件不变。添加 SSH 节点 `ModalDialog` 640（`form#node-editor-form`），修改名称 420（`form#node-rename-form`；说明取打开时冻结的 `renameAddress`——`ModalDialog` 关闭淡出期间内容仍在渲染，从已清空的 `renaming` 用模板字符串拼接会显示 `undefined@undefined:undefined`），保存中不可关闭靠 `show-close-button`、`escape-key-down`、`interact-outside` 透传到弹窗面板。
  - 设置页：搜索框（`.settings-header-tools > .fui-search`，宽 320；`SearchInput` 的 class 落在内部 input 上，宽度规则须写在包装元素上）与「N 项配置」（`.settings-total`）在页头操作区；分类导航 `.system-settings-nav` 选中项为表面色加卡片阴影，有待保存字段的分类尾部 `em.is-dirty`（琥珀色，`aria-hidden`，分类按钮名称保持分类名），预热记录尾部为条数；分类模式没有工作区标题行，搜索时显示 `.settings-search-result`「搜索结果 · 找到 N 项配置」，段落卡头部带 `Badge.settings-result-category`。段落卡头部为 `IconTile size=lg` + h3 + 说明。被修改字段（`dirtyKeys`）在标签行显示 `Badge warning`「已修改」：数字与下拉用 `label-extra` 插槽，文本 / 文本域为 `label for="setting-{key}"` + 徽标，布尔字段为标签 + `Switch :label="field.label"`（`id="setting-{key}"`，点击标签可切换）。预设按钮为 `Button size=sm variant=soft`。预热记录结果为 `Badge dot`：成功 success、跳过 secondary、失败 destructive。
  - 定位契约（脚本与组件逻辑依赖，只改样式）：`.node-card`、`.node-state`、`.node-actions`、`.node-editor`、`.node-rename`、`.account-node-selector`、`.node-migration`、`.migration-status`；`.system-settings-nav`、`.settings-total`、`.settings-section-card`、`.settings-save-bar`、`.settings-prime-records`、`.setting-help`、`.setting-error`、`[data-settings-field]`、字段 `name`。
  - ≤760px：节点卡单列，资源保持四列，按钮行换行；设置页搜索框占满内容宽，分类导航横向滚动，字段单列；页面无横向滚动。概览卡沿用组件库断点。
- 验证入口：`deploy/flower2api/verify_account_page_design.py` 对设计稿 `#accounts`、`#account-edit`、`#mobile` 逐项比对计算样式并覆盖首屏、健康条、工作区外框与移动端搜索行；`deploy/flower2api/verify_accounts_design.py`，覆盖真实Vue组件与合成管理接口的字段保存、取消、分页、OAuth、调度筛选、费用气泡、字体、侧栏和1440/720/390px布局；沿用管理/环境/导航回归。

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
| 账号排队数在 0、1、8 间切换 | 卡片宽高及相邻位置稳定；排队入口可打开调度详情 |
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
node --experimental-strip-types --test apps/web/tests/theme.test.mjs
npm --prefix apps/web run build
npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187 --strictPort
python3 deploy/flower2api/verify_ui_controls.py --url http://127.0.0.1:4187/ui-preview.html
python3 deploy/flower2api/verify_ui_kit.py --url http://127.0.0.1:4187/ui-preview.html
python3 deploy/flower2api/verify_ui_shell.py
python3 deploy/flower2api/verify_account_page_design.py
python3 deploy/flower2api/verify_records_pages_design.py
python3 deploy/flower2api/verify_nodes_settings_design.py
python3 deploy/flower2api/verify_theme_settings.py
node --experimental-strip-types --test apps/web/tests/update-steps.test.mjs
python3 deploy/flower2api/verify_update_design.py
python3 deploy/flower2api/verify_system_update_browser.py --output <证据目录>
```

- `theme.test.mjs`：默认主题与 ui-foundation.css 双向一致、预设与边界色对比度、尺寸派生、种子校验与存储失败矩阵、编辑器纯函数（差异、hex 规整、数值校验、预设反查）、组件与已迁移页面样式不写死颜色与圆角。
- `verify_ui_kit.py`：与 `doc/design/console-v2/mock.html` 逐项比对计算样式（结构等价项在脚本白名单中注明原因），组件各状态取值、预设与自定义主色、柔光材质、局部主题隔离、刷新保持、存储缺失/损坏/越界/抛错回退、减少动效，以及真实构建入口首屏即为保存的主题（需先 `npm --prefix apps/web run build`）。
- `verify_ui_shell.py`（需先构建）：真实构建加合成夹具，1440 下侧栏、品牌行、版本号两态、导航、计数徽标、底部区、内容区与页头对 `mock.html#accounts` 逐项比对；9 个页面页头无分组名且样式一致；系统设置保存栏比对与「1 项待保存 / 配置已同步」；折叠保持、1440×560 导航内部滚动；390 应用栏比对、抽屉贴左铺满并在导航后关闭；登录页对 `v1/mock.html#login` 比对及空密码、错误密码、成功、显示密码四条路径；零控制台错误。
- `verify_account_page_design.py`（需先构建）：`InteractionFixture` 的 13 个账号（第 4–6 号设为限流、认证错误、停用）。1440×900 对 `#accounts`、`#account-edit` 比对 79 项计算样式（白名单：设计稿 `.acc-name span` 误命中徽标的文字色与字号、99px 全圆）；三列、间距 16、首行三张卡片操作栏底边 ≤ 900；健康条四种色调与 36px；工作区 820 视口居中、滚动内容区时页签带不动、切换页签外框不变、新建无页签带；授权登录 440；390 对 `#mobile` 比对，搜索行展开、聚焦、有搜索词时不收起，其它页面无搜索按钮；零控制台错误；设计稿未画的画面截图存 `--output`。
- `verify_records_pages_design.py`（需先构建）：`RemainingPagesFixture`（第 2 条代理已过期、第 3 条未设到期）与 `BlockFixture`。1440×900 对 `#requests`、`#proxies`、`#tokens`、`#blocks` 比对 63 项计算样式（白名单：99px 全圆开关）；日志卡点击写 PUT、保存中禁用与新值；快捷分段 `outcome=errors`；详情抽屉宽 1020、上右下 14px、面板 `overflow:hidden` 而 `.fui-modal-body` 滚动、四个页签切换外框不变；代理第 4 卡 19 /「另有 1 条已过期」与旧网关缺字段时「—」；代理编辑 680 居中、令牌编辑 760；令牌名称搜索无结果；封禁四段计数与切换；四页 390 无横向滚动及保留列数（请求 4、代理 3、令牌 4、封禁 3），代理 390 点击使用摘要后展开行与账号入口可见；零控制台错误；截图存 `--output`（默认 `.deploy/console-ui-revamp/records/verify`）。
- `verify_nodes_settings_design.py`（需先构建）：1440×900 对 `#nodes`、`#settings` 逐项比对 55 组计算样式（白名单为空）；`StatesFixture` 八种节点状态断言待处理为 5、说明「3 台需检查连接 · 1 台组件异常 · 1 台移除待重试」、远程服务器「5 台待处理」与各状态徽标色，单节点时为「全部正常 / 尚未添加」；节点添加 640、改名 420 居中，改名按 Escape 后淡出期间说明始终为原地址；设置页修改数字与开关后「已修改」、分类计数与保存栏计数递增，撤销清零且零写入，搜索结果行与分类标签、草稿保留、搜索空态、预热记录；两页 390 无横向滚动、节点卡单列、设置搜索满宽与导航横向滚动；零控制台错误。截图在 `.deploy/console-ui-revamp/nodes-settings/verify/`。
- `verify_theme_settings.py`（需先构建）：`ThemeFixture`（`ShellFixture` 加 `/theme` 页面地址与子框架写请求记录）。覆盖以下内容：
  - 侧栏底部组顺序与选中；
  - 6 个预设逐个切换后，iframe 根 `--ui-color-primary` 变化、页面根不变，画板主按钮背景（等过渡结束）；
  - 1440×900 对 `#theme` 比对 21 组计算样式（白名单为空），面板宽 340、两列同行、不超出视口；
  - 字号改值、单项恢复、越界 / 清空 / 小数拒绝（页头「1 处修改待应用 · 1 项输入无效」，切到颜色分类后尺寸分段计数 1、恢复后消失），阴影步长 0.3 拒绝、1.25 生效；hex `#12` 拒绝、`#ABC` 规整，取色器写入；
  - 撤销草稿；保存后存储种子正确，刷新到 `domcontentloaded` 时根上已有内联主色；恢复默认后保存清除存储；
  - 缩放按钮、滚轮、拖动 60/40、适应，iframe 不可命中、`inert`；子框架写请求只有 `POST /admin/runtime/session`；
  - 离开确认的取消 / 放弃 / 无草稿直达，`beforeunload` 有草稿触发、无草稿不触发；有草稿时退出登录不拦截；
  - 存储损坏、越界回退默认，`setItem` 抛错时提示失败且根不变；
  - 390 应用栏标题、可见同步状态、单列、画布 320 高、无横向溢出；零控制台错误。
  - 截图在 `.deploy/console-ui-revamp/theme-settings/verify/`。
- `update-steps.test.mjs`：正向含迁移、维护中进行中与待执行、越过取消边界的切换合并、无快照部署、恢复路径、旧操作无 `steps`、未知阶段、截断记录。
- `verify_update_design.py`、`verify_system_update_browser.py`（需先构建）：前者对设计稿 `#update`、`#update-progress` 比对 45 项计算样式并检查说明展开、转义与零写入；后者覆盖版本记录与嵌套确认 Esc、居中与矮视口、直接安装默认 60 秒 / 30 分钟 1800 秒 / 双击幂等、步骤与时间、断线重连、快照与迁移、数据恢复、完成与刷新、409、未接入、回退与取消等待、等待对账与恢复。
- 迁移期改造旧原型对比脚本：组件库负责的属性在脚本内用 `component_keys`（采样名 → 属性集合）跳过，并注明已由 `verify_ui_kit.py` 覆盖；页面级属性继续与旧原型比对。写死的组件颜色改为在被测节点内插入探针元素读取 token 实际渲染值（`verify_shared_pagination.py::token`），不得把旧色值改成新色值再写死。业务断言不放宽。外壳尺寸（侧栏宽、内容区边距）推算出的页面宽度断言改为读取实际值（如卡片区铺满 `#console-content` 内容宽度、右边距等于其实际 `padding-right`），外壳本身由 `verify_ui_shell.py` 对照设计稿核对。
- 脚本读取气泡与弹窗的约定：
  - `InfoTooltip`、`ExecutionNodeBadge` 的气泡内容先悬停触发器，再读 `.fui-info-content`（例如请求列表 `tbody .request-account-identity button` 后的账号邮箱、执行节点徽标后的 `code` 节点键），读完用 `Escape` 加 `page.mouse.move(0, 0)` 收起。不要用 `get_by_role('tooltip')`：reka 的 `role=tooltip` 只是视觉隐藏的纯文本副本，不含 `code` 等子元素。
  - `ModalDialog` 的内容层带 `duration-200`（`DialogContent.vue`，0.2s 且不限定属性），`set_viewport_size` 后立即截图会拍到弹窗宽度与位置变化的中途，须传 `animations='disabled'`。
  - 夹具数量会被继承链改写（如 `TokenDesignFixture` 把账号补到 101 个），分页期望从 `len(fixture.accounts)` 等实际数据算出，不写死条数。
- 运行环境：`verify_shared_pagination.py`、`verify_page_sizes.py`、`verify_task_account_config.py` 会导入 `services/orchestrator` 的测试夹具，需先安装 `services/orchestrator/requirements.txt`（含 `docker`、`sse-starlette`）；`verify_task_account_config.py` 另需 `PYTHONPATH=services/orchestrator`。`verify_management_polish.py` 必须传 `--output`，`verify_system_update_browser.py` 同样需要 `--output`。合成夹具（`verify_environment_ui.Fixture` 一系）只响应已登记的页面地址：`/session-blocks`、`/nodes` 等页面须从 `/` 经侧栏链接进入，直接 `goto` 会因 `dist/<路径>` 不存在而超时；夹具缺的接口在脚本内的子类夹具补齐（如 `verify_ui_shell.py::ShellFixture` 补 `/admin/session-policy-blocks`、`/runtime/api/nodes`）。

- `verify_ui_controls.py`验证真实Vue组件：数字上下界、空值、小数步长、禁用；空选项原值、菜单键盘与禁用选项；搜索焦点、输入法、清空；气泡和原生dialog浮层；720/390px与触屏。测试不得发业务API请求。
- `verify_account_queue_layout.py`使用真实构建与合成接口，在 2248/1440/390px 下切换排队数 0→1→8→0，比较全部卡片的宽高和坐标，验证页面横向边界及排队按钮打开调度详情。
- 静态稿对应检查位于当前任务的 `research/verify_concept.py`、`verify_account_controls.py`、`verify_account_workspace.py`、`verify_proxy_revision.py`、`verify_request_preview.py`、`verify_settings_preview.py`；只在改动该概念稿时运行对应范围。
- 当前组件证据在 `.deploy/frontend-sidebar-refresh/ui-controls/verification.json`；静态稿证据在 `.deploy/frontend-sidebar-refresh/concept/`。旧截图或过期检查不能替代本次变更验证。
- `research/verify_check_repairs.py`（当前前端任务）覆盖删除全部任务账号后创建、可选上限、跨模块历史、双入口时区与迟到授权、认证代理导入、独立任务/草稿占用及删除前复核；同时要求零浏览器异常和零外部网络请求。
- 新页面采用组件后，补充该页面的保存/取消、权限、错误、异步和接口合同检查。组件测试通过不等价于业务页面迁移完成。

## 正式组件交互细节补充

- Button的默认variant显式为default。外观取 token：主要为 `primary` 填充、悬停 `primary-hover`；次要为 `fill` 填充无描边、悬停 `fill-hover`；6px 圆角、38/32px 两档，默认及悬停都不加阴影和位移。禁用和键盘焦点独立，减少动效偏好关闭过渡。页面迁移前，带页面级覆盖的按钮仍是旧外观。
- `DateTimeControl`使用reka-ui日历及现有NumberInput，`modelValue:string|null`为ISO瞬时，界面为浏览器本地时间。打开建立草稿，确定才提交，Esc只关闭日期浮层；清除返回null。日历通过`@internationalized/date`真实日期类型处理。
- `ProxyPicker`接收`ProxyRoute|null|undefined`；undefined保留原配置，null直连，具体记录表示草稿选择。20条分批搜索、取消与迟到响应隔离，提交由账号边界写proxy_id/proxy_revision。
- 授权登录第一步440px，普通表单标签、代理输入和右对齐主按钮。真实交换成功后填入配置；关闭中止客户端读取并拒绝旧代次回填。授权结果默认隐藏凭据，仅原复制操作可主动获取。
- `runtime/RunDetails.vue`是顶层复用弹窗，900×740上限、固定标题/身份/页签/页脚、正文独立滚动。Teleport根容器尺寸放全局class，禁止仅依赖后代scoped样式。测试必须断言计算后的width/height，行为测试通过不能替代尺寸对照。
- 运行日志仅在日志页签读取最近128KiB、最多渲染1500行，文件列表不超过每10秒刷新，关闭或路由切换取消请求与轮询。终态补读保留落盘延迟兼容。
- `verify_interaction_parity.py`逐项比对定稿按钮默认与hover六项属性，并验证授权尺寸/关闭竞态/移动端；`verify_run_detail_design.py`验证顶层尺寸、页签与退出清理。

## 一比一迁移的取值与验收

`apps/web/src/approved-design.css`只保留全局排版与交互指针合同；账号、请求、代理、令牌、会话封禁的页面样式已迁到各自的第二版样式文件。`ui/icon`使用第二版设计稿图标路径（`doc/design/console-v2/icons.js`，描边1.8），`apps/web/src/assets/approved-icons.svg` 与 `apps/legacy-web/approved-icons.svg` 保持同一内容；符号表通过Vite `?url&no-inline`发布到已有assets路由；不要把SVG符号表内联为data URL后用于use引用。快照导出必须把外部use改写为快照内符号。

`AccountScopePicker`接收modelValue CSV、accounts、label与help，只更新表单草稿。历史已选ID不在当前资料时显示账号编号并保留移除能力。父页负责完整分页、取消和保存。

账号页已按第二版设计稿迁移，旧原型逐项对照脚本 `verify_exact_design.py` 已删除（账号采样由 `verify_account_page_design.py` 接管，根字号与三档无溢出由 `verify_console_ui.py`、`verify_accounts_design.py` 覆盖）。逐项比对通过只证明对应元素；完成声明还需覆盖全部页面、弹窗、操作状态以及布局边界。

### 定稿响应式及字体根合同

应用与内容区铺满视口，账号卡片最小320px、间隔16px（第二版设计稿 `.grid`）；760px及以下强制单列，1680px及以上四列。侧栏在1920px/2560px断点为264px/280px，折叠宽度仍76px。验证需包含列数切换附近1340/1680px与1920/2560/3440px，不能只验1440/390px。

html根字号与原型共用`--ui-font-body`的14/15/16px三档规则，font-family为同一字体栈、font-synthesis:none。仅body字体相同不能保证rem控件一致。字体验收需核对浏览器实际平台字体，不能只看CSS声明。费用气泡专用class使用足够的选择器优先级，避免异步加载的通用控件样式覆盖。

授权登录选择代理与账号编辑共用ProxyPicker；代理选择在生成链接时冻结，成功后账号草稿沿用同一目录ID与revision。服务端处理目录凭据，浏览器只接触公开投影。

### 令牌与任务原型对齐（2026-11-15）

- 令牌页已换成第二版数据表（见「正式控制台与账号首批迁移」中的四页合同），不再与旧原型对齐。Tailwind的`--muted`是背景色，次要文字使用`--muted-foreground`；原生工作区的同名变量单独限定作用域。
- 任务工作区的定稿声明集中在`apps/legacy-web/work-design.css`，按原型CSSOM取值。主路由断点按实际浏览器视口响应，主区域宽度由侧栏占位确定。桌面1440px下任务账号三列。
- 新布局保留原表单ID、字段name与API处理，工程和养号空间继续分别维护配置、草稿及SSE清理。新增搜索仅过滤列表；题库的创建任务只预选题目并打开批次表单，提交前保持零写入。
- 旧`.view`的flex间距、旧页签底色以及高优先级按钮规则不能叠加进新工作区；校验卡片底栏按钮自身样式与宽度，不能只校验父容器。
- 运行配置与新建抓包使用两个独立入口。账号名称提供完整技术详情，登录草稿单独呈现；额度窗口区分真实0与未提供，不展示7天Sonnet。
- 增量验证：`audit_token_task_design.py`断言任务六入口和工程五分区的渲染样式并保存截图（令牌用例已移除，改由 `verify_records_pages_design.py` 对第二版设计稿核对）；`verify_runtime_workspace_design.py`覆盖原操作、详情、搜索、草稿、题目预选、独立抓包创建、响应式与键盘层级；`verify_tokens_design.py`覆盖令牌真实载荷与取消语义。

## 完整视口弹窗与跨文档组件复用

- 未迁移页面的视觉基准为 `doc/design/flower2api-concept.html` 的实际渲染结果；组件库与已迁移页面以 `doc/design/console-v2/mock.html` 为准。逐页核对内部结构、字重、字号、字体、行高、控件默认/悬停/焦点/选中状态与关键弹窗。仅采样外层容器不能作为一比一还原的验收证据。
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

通用原生工作区、运行详情与令牌编辑标题共用`--ui-font-heading`的18/20/22px，沿原650字重、行高及字距。代理编辑宽度680px，表单提示位于控件之后，同排输入保持共同基线。关闭图标使用同一SVG；原生委托事件通过closest定位按钮，沿原清理入口退出。共享输入框焦点由组件库提供（主色细环加 `primary-ring` 外圈），避免残留默认黑色焦点框。

系统更新弹窗的排版以第二版设计稿 `mock.html#update`、`#update-progress` 为基准（见「系统更新弹窗」节），由 `verify_update_design.py` 逐项比对计算样式，并覆盖说明展开 / 收起、文本转义与浏览零安装写入。

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
- 当前页使用 `--ui-color-primary` 背景、`--ui-color-on-primary` 文字及`aria-current=page`；普通页 `fill-subtle` 底、正文色，禁用项 `fill-muted` 底、`text-4` 文字；上一页 / 下一页为 32px 纯图标方块，文字只保留在无障碍名称。长页码保留首尾与当前邻页、省略号；禁止横向溢出。各宿主（含任务工作区）不得再写死分页颜色。
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
- `ConfirmationDialog`接受open/title/message/confirmLabel/danger/busy/error/confirmDisabled（默认 false；请求已失效时禁用确认、取消仍可用，如系统更新 409）；发confirm/cancel，业务组件拥有请求。`useConfirmation().ask(options, signal?) -> Promise<boolean>`仅明确执行返回true。
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
- 系统更新弹窗优先呈现当前 / 可用状态与检查动作；有新版时显示安装方式并可直接安装。完整说明、组件维护和版本历史在弹窗内独立展开或进入二级视图。活动维护与需恢复的操作先于发布说明（直接显示进度），已结束操作在概览紧凑呈现；原 UUID / revision / SHA、取消、恢复和回退合同保持。

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
