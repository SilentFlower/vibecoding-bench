# 技术设计：组件库与主题运行时

现状证据见父任务 `../11-19-console-ui-revamp/research/frontend-architecture.md`（下文标「调研 §n」）。跨子任务约定见父任务 `design.md`，本文在其基础上细化，并修订其中两处（§8）。

## 1. 边界与过渡策略

本任务只改「组件长什么样」和「主题从哪来」，不改页面。

- **新 token 层**：组件与已迁移页面专用，由主题运行时驱动。
- **旧 token 层（冻结）**：页面仍在用的 shadcn 变量（`--background/--primary/--border/--muted-foreground…`）、旧控件 token（`--ui-accent/--ui-border/--ui-text…`，页面 CSS 共 63 处引用）、阅读尺寸（`--ui-font-body/--ui-control-height…`），**取值保持现状**，不跟主题变化。
  - 理由：父设计 §6 要求未迁移页面继续用旧原型 `flower2api-concept.html` 做计算样式对比，§7 规定先换组件外观、页面在子任务 2/4/6 之前保持旧样子。旧层一旦跟随新色板或新字号，13 个原型对比脚本对未迁移页面全部失效，回归保护提前丢失。
  - 代价：
    - 过渡期主题切换只影响组件和已迁移页面；新组件（13px、紫色主按钮）会和旧页面文字（14px、旧色）并存。
    - 页面级覆盖同样保留到页面迁移：未分层的页面 CSS（约 96 条按钮颜色规则，如 `.account-authorize-button`）和模板传入的颜色工具类（如账号页「添加账号」的 `bg-primary`）会继续压过组件样式。这些位置的按钮、弹窗、表格在所属页面迁移前仍是旧外观；没有页面覆盖的组件立即换新。
  - 退役：子任务 2/4/6 迁移页面时把引用改为新 token；父任务最终复核时删除旧层（grep 旧层变量名清零）。
- 本任务对旧层只做「去重」：重复定义合并为一处（取当前生效值，视觉零变化）；只服务于组件的 token 组（`--button-*`、`controls.css` 的 `:root` 块）随组件重写删除或迁入旧层块。

## 2. Token 设计

### 2.1 命名

新 token 一律带分类前缀，与旧层的扁平名不冲突，便于最终 grep 清理：

| 分类 | 前缀 | 例 |
| --- | --- | --- |
| 颜色 | `--ui-color-*` | `--ui-color-primary`、`--ui-color-text-3` |
| 字号 | `--ui-font-size-*` | `--ui-font-size-md` |
| 字体 | `--ui-font-family`、`--ui-font-family-mono` | |
| 控件高 | `--ui-control-sm/md/lg` | |
| 间距单位 | `--ui-space-unit` | |
| 圆角 | `--ui-radius-btn/control/block/card` | |
| 阴影 | `--ui-shadow-card/pop/modal/raised/knob` | |
| 运行时内部 | `--ui-font-size-base`、`--ui-control-base`、`--ui-size-step`、`--ui-tier` | 只供派生，不直接用于组件 |

### 2.2 颜色（默认 = 第二版浅色，取自 `mock.css:5-42` 与组件规则中的字面值）

| 组 | token（省略 `--ui-color-` 前缀）= 默认值 |
| --- | --- |
| 中性 | `layout` #f5f6fa · `surface` #ffffff · `fill` rgba(98,96,158,.075) · `fill-hover` rgba(98,96,158,.11) · `fill-muted` #f1f2f7 · `fill-subtle` #f7f8fb · `fill-strong` #d8dce8 · `track` #e9ebf3 · `line` #e6e8f0 · `mask` rgba(14,23,38,.3) · `scrollbar` #aab2c2（沿用现滚动条实际可见色） |
| 文字 | `text` #0f1527 · `text-2` #414a5c · `text-3` #5f6878 · `text-4` #97a0b2 |
| 表格 | `table-head` #eff1f8 · `table-stripe` #f8f9fc · `table-hover` #f0f1f9 |
| 主色 | `primary` #6c54b4 · `primary-hover` #5f479f · `primary-container` #f3f0fb · `primary-text` #5b44a3 · `primary-ring` rgba(108,84,180,.18) · `on-primary` #ffffff |
| 功能色 ×4 | `success` #12b981 / `success-text` #067655 / `success-bg` #ecf9f5；`warning` #f59e0b / #955900 / #fef7eb；`danger` #ef4444 / #c32d32 / #fef0f0；`info` #5983f4 / #3f5fcb / #f2f5fe |
| 中性标签 | `neutral-text` #535b67 · `neutral-bg` #f1f3f7 |
| 平台 | `cc-text` #9a5634 · `cc-bg` #fbf1ea · `agy-text` #3f62b0 · `agy-bg` #eef3fd（不随主题） |
| 品牌 | `brand` #ed6ea7 · `ink` #191b2c（不随主题） |
| 通知 | `feedback-surface`（取 ink）· `feedback-text` #ffffff |

- 悬停、按下等设计稿没给的状态色，组件里用 `color-mix()` 由上表 token 混合得到，不新增 token、不写字面值（如柔和按钮悬停 = `color-mix(in srgb, var(--ui-color-primary-container), var(--ui-color-primary) 8%)`）。
- 阴影颜色基于 rgb(14,23,38)，强度乘以种子 `shadow`；默认值等于 `mock.css:37-39` 及分段滑块 `0 1px 3px rgba(14,23,38,.08)`、开关圆钮 `0 1px 2px rgba(0,0,0,.18)`。

### 2.3 尺寸与三档阅读尺寸

运行时只写种子级数值；`ui-foundation.css` 用 `calc()` 结合 `--ui-tier`（媒体查询设为 0 / 1 / 2，对应 <1920 / 1920–2559 / ≥2560）派生：

| token | 公式（F = font-size-base，默认 13） | 1440 下 |
| --- | --- | --- |
| `--ui-font-size-xs` | F − 1.5 + tier | 11.5（标签、徽标） |
| `--ui-font-size-sm` | F − 1 + tier | 12（辅助文字、字段标签、表头） |
| `--ui-font-size-meta` | F − 0.5 + tier | 12.5（分段、卡片副标题、操作链接） |
| `--ui-font-size-md` | F + tier | 13（正文、按钮、输入） |
| `--ui-font-size-title` | F + 1 + tier | 14（区块标题） |
| `--ui-font-size-card` | F + 3 + tier | 16（卡片、表格卡片标题） |
| `--ui-font-size-heading` | F + 7 + 2·tier | 20（弹窗标题） |
| `--ui-font-size-page` | F + 15 + 2·tier | 28（页标题） |
| `--ui-control-sm/md/lg` | base ∓ step + 2·tier | 32 / 38 / 44 |

- 圆角由种子 R（默认 8）在 JS 里算好写入：btn = max(R−2, 0)、control = R、block = R+4、card = R+10 → 6 / 8 / 12 / 18。复选框、分段滑块等更小的圆角用 `calc()` 基于这些 token 得到。
- 间距：组件内边距与间隙写成 `calc(var(--ui-space-unit) * k)`，k = 设计稿 px ÷ 4，默认单位 4 时与设计稿逐像素一致。三档阅读尺寸不放大间距，与现有机制一致。
- html 根字号仍由旧层 `--ui-font-body` 决定（14/15/16），Tailwind 的 rem 布局不受影响；`verify_console_ui.py:126` 的根字号断言保持有效。
- 派生块的选择器是 `:root, [data-ui-theme]`：CSS 自定义属性按声明处计算后再继承，局部容器必须在自身重新计算派生值，否则会继承根的结果（§3.3）。

### 2.4 种子与预设

```ts
interface ThemeSeed {
  version: 1;
  primary: string;        // #rrggbb，默认 #6c54b4
  success: string; warning: string; danger: string; info: string;
  surface: 'default' | 'soft';
  fontSize: number;       // 12–16 整数，默认 13
  spaceUnit: number;      // 3–6 整数，默认 4
  controlHeight: number;  // 32–44 整数，默认 38
  sizeStep: number;       // 4–8 整数，默认 6
  radius: number;         // 0–12 整数，默认 8
  shadow: number;         // 0–2，步长 0.25，默认 1
}
```

- **预设只是主色取值**：花瓣紫 #6c54b4（默认）、深海蓝 #2f6bd8、松石绿 #0f9f8f、暮光橙 #e2742b、玫瑰红 #d64a7b、石墨 #3d4352（`mock.html:254`）。当前预设由主色反查，主色不匹配任何预设即为「自定义」。不另存预设 ID。
- **色组来源**：主色和四个功能色若等于默认值，使用设计稿手调色组（5 组，保证默认主题与设计稿完全一致）；其它颜色（5 个非默认预设、自定义色）走派生算法。
- **派生算法**（自写，约百行，不引入色彩库）：
  - 在 OKLCH / OKLab 空间运算：hover = 明度 −0.05；container / bg = 与 surface 按约 8% 混合；ring = 原色 18% 透明度。
  - `*-text` 从原色开始逐步降低明度，直到对 container/bg 与 surface 的对比度都 ≥ 4.5。
  - `on-primary` 先取白色；白字不足 4.5 时改用 `text` 深色字（松石绿、暮光橙）；两者都不足 4.5 时，把主色按 OKLCH 逐步压暗直到白字达标（玫瑰红 #d64a7b → 约 #c83c6f）。
  - 参数以 5 组手调值校准，使派生结果与手调值接近。
- **表面材质「柔光」**（设计稿未给，本任务定义、交用户目视确认）：layout、fill-muted、fill-subtle、line 与表格三色向主色色相混合约 4%，卡片阴影强度减半；文字色与控件不变。

## 3. 主题运行时

### 3.1 模块（`apps/web/src/theme/`）

| 文件 | 职责 |
| --- | --- |
| `color.ts` | hex ↔ OKLCH / OKLab、混合、WCAG 对比度（纯函数） |
| `tokens.ts` | `ThemeSeed` 类型、`DEFAULT_THEME_SEED`、`THEME_PRESETS`、`THEME_SEED_LIMITS`（取值范围，供校验与子任务 5 的界面共用）、`createTheme(seed): ThemeVars`、`parseThemeSeed(value): ThemeSeed \| null` |
| `runtime.ts` | `readStoredTheme()`、`writeStoredTheme(seed \| null)`、`applyTheme(el, vars)`、`initTheme()` |
| `index.ts` | 统一导出 |

- `color.ts` / `tokens.ts` 不访问 DOM，相互导入带 `.ts` 扩展名、不用 `@/` 别名，以便 `node --experimental-strip-types --test` 直接加载（同 `tests/accountUpdate.test.mjs` 的方式；`tsconfig.app.json` 已开 `allowImportingTsExtensions`、`erasableSyntaxOnly`）。
- `createTheme` 输出全部可主题化 token 的完整集合，每次应用都整组覆盖，不会残留旧值。

### 3.2 持久化与首屏

- 存储：`localStorage['flower2api.theme'] = JSON.stringify(seed)`，`seed.version` 为 1。只存种子；派生是同步纯函数，加载时重算，算法升级后不会读到过期派生值。
- `parseThemeSeed`：类型、范围、整数、步长、hex 格式任一不符即整体返回 null（整体回退默认，不做逐字段合并）；未知字段忽略。
- `readStoredTheme` 把 `localStorage` 访问与 `JSON.parse` 放在 try/catch 里（隐私模式、禁用存储会抛错），失败返回 null。
- `initTheme()`：读到有效种子就 `applyTheme(document.documentElement, createTheme(seed))`；读不到就什么都不写，由 CSS 默认值生效。
- `main.ts` 与 `previews/ui-preview.ts` 在 `createApp()` 之前调用。应用在首次挂载前已就位，界面不会先以默认主题渲染。
  - 不改 `index.html`（父设计 §1，`system_release.py:101-103`）。
  - 已知局限：模块脚本执行前浏览器可能先画一帧空白页底色；浅色下与默认底色只差柔光材质的约 4% 色相，可以接受。深色模式（子任务 7）若要消除这一帧，需要在那时另行评估 `index.html` 内联脚本。

### 3.3 应用到元素

- `applyTheme(el, vars)`：逐个 `el.style.setProperty`，并设置 `data-ui-theme` 属性，让 §2.3 的派生块在该元素上重新计算。
- 用在根上即全局主题；用在任意容器上即局部主题，只影响其子树（子任务 5 的预览画板）。
- 限制：弹层默认 Teleport 到 `body`，会脱离局部容器。子任务 5 需要给画板内组件传 `portalTarget`（现有控件都支持）。

## 4. CSS 组织与层叠

| 文件 | 内容 | 层 |
| --- | --- | --- |
| `apps/legacy-web/ui-foundation.css` | 新 token 默认值 + `--ui-tier` 媒体查询 + 派生块；原有阅读尺寸（旧层）；`.fui-notice / .fui-confirm-* / .fui-operation-*` 改用新 token | 不分层（避免抢先声明层序，它在 `main.ts` 里先于 Tailwind 加载） |
| `apps/web/src/style.css` | 旧层：shadcn 变量合并为一个 `:root` 块（取当前生效值），旧控件 token 从 `controls.css` 迁入；删除 `:534-570` 全局按钮覆盖与 `--button-*`；全局滚动条改用新 token | 现状 |
| `apps/web/src/components/ui/kit.css`（新） | 全部组件样式（含原 `controls.css` 内容），类名沿用 `fui-` 前缀 | `@layer components` |
| `apps/legacy-web/pagination.css` | 分页与条数选择改用新 token（Vue 与原生文档共用） | 不分层（现状） |
| `apps/web/src/approved-design.css` | 删除 `:4` 的旧变量覆盖（并入 style.css 旧层块） | 现状 |

- `kit.css` 在 `main.ts` 与 `ui-preview.ts` 中紧跟 `style.css` 全局引入；`controls.css` 删除，各控件里的 `import './controls.css'` 移除。
- 组件模板只保留结构与动画类工具类（定位、flex、`animate-in` 等）；颜色、圆角、阴影、边框、字号、高度一律由 `fui-*` 类取 token。否则 utilities 层会压过 components 层。
- 业务传入的 Tailwind 类仍可覆盖组件默认值（utilities 层在 components 之上）。
- 全局覆盖的处理：未限定页面作用域的 `[data-slot=…]`、`.fui-*` 规则在本任务删除；带页面容器前缀的覆盖（如 `.oauth-actions [data-slot=button]`）属于页面级，随页面迁移删除。
  - 实际删除：`style.css` 的全局按钮规则与 `--button-*`、全局遮罩色、`:where(input,textarea)[data-slot]:focus-visible` 旧聚焦样式、`.fui-date-trigger:hover`；`approved-design.css` 的全局按钮尺寸与禁用规则；`TasksWorkspace.vue` 中把任务页共享分页当前页写死为 #77648f 的规则（否则任务页分页不随主题、与其它入口不一致）；全局弹窗规则只去掉写死的白底，`max-height` / `overflow` 保留。
  - 全局兜底焦点框 `:where(button, a, input, select, textarea):focus-visible` 移入 `@layer base`：未分层时它会压过组件层的焦点样式；进入 base 层后只对没有自定义焦点样式的元素生效。

## 5. 组件清单

原地演进，导入路径与现有 props / 事件不变，只做增量扩展。

| 组件 | 位置 | 做法 | 公开 API |
| --- | --- | --- | --- |
| Button（含图标按钮） | `ui/button` | 重写样式；`buttonVariants` 保留导出，输出 `fui-button` 加变体类 | variant：default=主要、outline / secondary=次要（填充无描边）、ghost=文字、link=文字链接、destructive=危险；新增 `soft`（柔和）、`destructive-ghost`（文字危险）。size：default 38、sm 32、lg 44、icon / icon-sm / icon-lg 同高方形 |
| Input、Textarea | `ui/input`、`ui/textarea` | 重写样式：静止填充，聚焦为白底加主色细环与外圈 | 不变 |
| InputGroup | `ui/input/InputGroup.vue`（新） | 前缀、后缀插槽，整组 `:focus-within` 一个焦点框 | 新增 |
| NumberInput、ChoiceSelect、SearchInput、InfoTooltip、DateTimeControl、TimeControl、PageSizeSelect、Pagination | `ui/controls` | 重写样式；内部 lucide 图标换 sprite；分页上一页 / 下一页按设计稿改为 32px 纯图标方块（文字保留在无障碍名称）；新增字段说明样式 `fui-field-help` | 不变 |
| Segmented | `ui/segmented`（新） | reka-ui `RadioGroup`，托盘加白色滑块，可带计数与图标 | `modelValue: string`、`options: readonly { value; label; count?; icon?; disabled? }[]`、`label`（无障碍名）；`update:modelValue` |
| Badge（标签 / 状态徽标） | `ui/badge` | 重写样式 | 保留 default / secondary / destructive / outline，新增 success、warning、info、cc、agy；新增 `dot?: boolean` |
| Switch | `ui/switch`（新） | reka-ui `Switch`，36×20 | `modelValue: boolean`、`label`、`disabled?` |
| Checkbox | `ui/checkbox`（新） | reka-ui `Checkbox` | `modelValue: boolean \| 'indeterminate'`、`disabled?`；默认插槽为文字 |
| RadioCardGroup | `ui/radio-card`（新） | reka-ui `RadioGroup`，单选卡 | `modelValue: string`、`options: readonly { value; label; description?; disabled? }[]`、`label`、`name?` |
| 气泡 | InfoTooltip、ChoiceSelect 菜单、日历、OperationFeedback 结果 | 共用 `.fui-popover` 表面（surface、block 圆角、`shadow-pop`） | 不变 |
| Dialog 系列 | `ui/dialog` | 18px 圆角、`shadow-modal`、遮罩 `mask`；标题 heading / 780；Footer 为普通右对齐按钮行（账号编辑等页面会把内容区内边距改为 0，负外边距贴边会撑出弹窗，所以通栏浅灰底栏只在结构受控的确认框里实现，统一的居中弹窗底栏由子任务 2 的组合组件提供）；关闭按钮改为文字型 32px 图标按钮并用 sprite | 不变 |
| ConfirmationDialog、FeedbackHost（通知）、OperationFeedback | `ui/feedback` + `ui-foundation.css` | 换 token；通知保持现有深色浮条形态（底色取 ink） | 不变 |
| Table 系列 | `ui/table` | 圆角表头条、斑马行、悬停行、单元格 60px；`fui-table-sub` 为单元格内「主值下一行」的辅助值（设计稿 `.t .sub`） | 不变 |
| Card 系列 | `ui/card` | 去边框、`shadow-card`、card 圆角 | 不变 |
| Empty | `ui/empty`（新） | 图标块、标题、说明、操作插槽 | `title`、`description?`；`icon`、`actions` 插槽 |
| Skeleton | `ui/skeleton`（新） | 填充色微光；减少动效时静止 | 无 props，尺寸由 class 控制 |

- **未纳入**：页头、概览卡、实体卡、数据表组合、浮动保存栏（子任务 2）；`label` / `separator` / `tabs` 当前无业务引用，保持原样。
- **文字基准与继承**：设计稿正文 13px / 1.55，颜色 `text`。
  - 卡片、弹窗、表格是容器，根元素不设颜色、行高、字体等可继承属性：内部是页面内容，由页面基准决定（迁移后的页面使用 13px / 1.55），避免未迁移页面被连带改变。表格字号沿用旧版由组件决定的做法，取 `font-size-md`。
  - 组件自带的文字部件显式设置：弹窗标题与说明、卡片标题与说明、表头、`fui-table-sub`、单选卡、字段标签与说明、浮层、空态、复选文字为 1.55；按钮、徽标、分段等定高居中的控件为 1。
- **状态约定**（设计稿只画了静止态，以下统一定义）：
  - 键盘焦点：交互控件为 `outline: 2px solid primary; outline-offset: 2px`；输入类为主色细环加 `primary-ring` 外圈，由外框 `:focus-within` 承担。
  - 禁用：不透明度 .45、`cursor: not-allowed`。
  - 加载：沿用现有 `aria-busy` 写法，样式为 `cursor: wait`，不新增 `loading` prop。
  - 过渡 .15s；`prefers-reduced-motion` 下 `transition` / `animation` 为 none。
  - `forced-colors` 下保留系统高亮。
- **设计稿没有的组件**（复选、空态、骨架、气泡、通知、确认框）按同一视觉语言（填充无描边、柔和阴影）定义，在演示页交用户目视确认。

## 6. 图标

- 以设计稿 `icons.js` 的 52 个为全集，路径一律取设计稿画法（用户 2026-11-19 确认）：
  - sprite 中已有语义相同的 28 个符号保留原 id，路径换成设计稿画法（如 `i-edit` ← `pencil`、`i-wave` ← `activity`、`i-settings` ← `sliders`、`i-task` ← `todo`），控制台各页（含原生页）的这些图标形状随之更新。
  - 其余按 `icons.js` 新增，id 用 kebab 名（如 `arrow-up-circle`）；`chevron-down` 取 `down`，`chevron-left` 按同一画法补齐。设计稿没有的 `i-spark` 保持原样。
  - 图标组件默认线宽从 1.7 调为设计稿的 1.8。
- `apps/web/src/assets/approved-icons.svg` 与 `apps/legacy-web/approved-icons.svg` 改为同一份内容（md5 一致），legacy 同时补上缺的 `i-server`。文件名不变，不涉及运行时桥接白名单。
- `ui/` 内部（Dialog 关闭、ChoiceSelect、DateTimeControl、TimeControl、Pagination）改用 sprite；业务页的 lucide 随页面迁移替换。

## 7. 原生页、基准与验证

- **原生页取值**：token 默认值放在已被 `<link>` 引用、并已登记在白名单中的 `ui-foundation.css`（`runtime_bridge.rs:436,1142`，`legacy-web/index.html:19`），不新增白名单条目。
  - `ui-foundation.css`、`pagination.css` 内容有变，legacy `index.html` 中两者的 `?v=` 静态版本参数同步更新。
  - Vue 内嵌任务页同文档继承根变量；新 token 名不与 legacy 的 `--border` / `--muted` 冲突。
- **设计基准**：
  - 把 `research/design-v2/` 复制到 `doc/design/console-v2/`，修正 `mock.css` 的字体相对路径。research 副本保留为调研快照。
  - 过渡期两套基准并存：已迁移的组件与页面看 console-v2，未迁移页面仍看 `flower2api-concept.html`。
- **验证分层**：
  1. `node:test`（`apps/web/tests/theme.test.mjs`）：
     - 默认主题与 `ui-foundation.css` 默认值双向逐项相等。
     - 各预设与边界色（极亮、极暗、高饱和）的对比度保证。
     - 尺寸、圆角派生及钳制。
     - 存储解析失败矩阵。
     - 静态规则：组件 CSS 与 `ui/**/*.vue` 中颜色字面量只允许出现在 `--ui-color-*` / `--ui-shadow-*` 声明里，`border-radius` 只能是 token、`calc` / `max` 表达式、`50%`、`999px`、`0` 或 `inherit`。
  2. 新增 `deploy/flower2api/verify_ui_kit.py`（dev server 演示页）：
     - 与 `doc/design/console-v2/mock.html` 逐项比对：在代理、请求、账号、账号编辑、设置画面与演示页之间按对应元素读取计算样式；结构写法不同但视觉等价的属性（卡片内边距所在层、分页图标间距、99/999px 全圆）与弹窗通栏底栏列入白名单并注明原因。
     - 默认主题下各组件、各状态的计算样式与设计稿取值一致。
     - 切换预设、自定义主色、柔光材质。
     - 局部容器隔离。
     - 存储缺失 / 损坏 / 越界 / 抛错均回退默认。
     - 键盘焦点可见、减少动效。
     - 1440 / 390 截图；零控制台错误、零业务请求。
     - 另在真实构建入口（dist + 现有合成夹具）检查首屏：`#app` 首次出现子节点时根变量已是存储值。
  3. 回归集（下节）。
- **既有脚本的处理规则**：
  - 原型对比脚本里属于基础组件的采样（按钮、输入、选择、弹窗外壳、分页、标签）移出原型比对，改由 `verify_ui_kit.py` 做 token 断言；页面级采样保持原型比对。
  - 写死组件样式值的行为脚本（如 `verify_shared_pagination.py:14-43` 的 #77648f、`verify_interaction_parity.py` 的按钮六项属性）改为读取 token 的实际值后比较。
  - 业务行为断言不放宽。
  - 改动前先跑基线，基线已失败的脚本单独记录，不算本任务引入。

## 8. 对父任务 design.md 的修订

- §1「shadcn 变量改为 `--primary: var(--ui-primary)` 这类别名」：改为本文 §1 的旧层冻结策略，别名化随页面迁移进行；新 token 采用 §2.1 的分类前缀。
- §1 持久化 `{ version, seed, vars }`：改为只存种子（§3.2）。

## 9. 发布与回滚

- 单独提交、单独发版；不改后端、网关与镜像构建。
- 回滚即回退本任务提交：旧层取值未变，回退后组件恢复旧外观；依赖本任务的后续子任务需一并回退（父设计 §7）。
