# 技术设计：外壳与通用业务组件

现状证据见父任务 `../11-19-console-ui-revamp/research/frontend-architecture.md`（下文标「调研 §n」）。组件库、token 与层叠约定沿用子任务 1 的 `../11-19-console-ui-kit/design.md`（下文标「kit §n」）。本文只写本任务新增或改变的部分。

## 1. 边界与过渡

- **本任务改的**：
  - 外壳：侧栏、移动端应用栏与抽屉、内容区边距与底色。
  - 8 个 Vue 页面的页头。
  - 系统设置的保存栏。
  - 登录页。
  - 新增 8 组组合组件（含页头、保存栏、居中弹窗）及其演示。
- **不改的**：
  - 页面主体保持原样，概览卡、工具栏、实体卡、数据表卡片的真实接入留给子任务 4、6。
  - 任务与工程的原生页头留给子任务 6，`/updates` 整页与更新面板留给子任务 3。
- **过渡态**：页头与外壳换新后，页面主体仍是旧样式（父设计 §7 预期）。新页头的标题、说明、操作按钮全部取新 token，页面级的按钮外观覆盖在页头范围内删除。
- **类名契约**：既有行为脚本依赖的类名、aria 名称保持不变，只删除旧样式规则：
  - 外壳：`.console-shell`、`.sidebar-collapsed`、`.console-native-tasks`、`.console-sidebar`、`.console-brand-row`、`.brand-update` / `.has-update`、`.navigation-item` / `.is-active`、`.sidebar-exit`、`.mobile-navigation-panel`、`.toolbar-page`、`#console-content`。
  - aria 名称：「打开主导航」「收起侧边栏」「展开侧边栏」「退出」「系统更新」「flower2api 首页」。
  - 登录与设置：`#admin-password`、`.settings-save-bar`。
  - 这些类名不再承载旧样式，由新样式文件按同名重写。

## 2. 设计基准

| 画面 | 基准 | 说明 |
| --- | --- | --- |
| 侧栏、页头、内容区 | `doc/design/console-v2/mock.html#accounts` | `.sb*`、`.ph`、`.page` |
| 移动端应用栏 | `mock.html#mobile` | `.m-top` |
| 概览卡、数据表卡片 | `mock.html#proxies` | `.ov`、`.tcard` |
| 工具栏 | `mock.html#accounts` | `.tb` |
| 实体卡 | `mock.html#environments` | `.ent` |
| 浮动保存栏 | `mock.html#settings` | `.savebar` |
| 居中弹窗 | `mock.html#account-edit` | `.modal`、`.mh`、`.mb`、`.mf` |
| 登录页 | `doc/design/console-v2/v1/mock.html#login`（新增） | 从主工作区 `.deploy/ui-revamp/after-v1/` 复制 `mock.html`、`mock.css`，修正字体相对路径；只有 `#login` 画面作为基准，其余第一版画面已被第二版取代 |

- 移动端抽屉、侧栏折叠态、移动端页头、登录页 390px 形态，设计稿没有画。按同一视觉语言定义（§3、§5、§6），交用户在截图中目视确认。

## 3. 外壳

### 3.1 结构（`Dashboard.vue`、`AppNavigation.vue`）

```
.console-shell[.sidebar-collapsed][.console-native-tasks]
├─ aside.console-sidebar
│   ├─ .console-brand-row
│   │   ├─ router-link.console-brand-mark [aria-label=flower2api 首页]  墨色方块 + 品牌图标
│   │   └─ .console-brand-text
│   │       ├─ .console-brand-name  "flower2api" + a.brand-update[.has-update]
│   │       └─ small.sidebar-tagline
│   ├─ nav.console-navigation（内部滚动）  分组名 + .navigation-item（含计数徽标）
│   └─ .sidebar-footer  头像 · 身份 · 折叠 · 退出
└─ .console-workspace
    ├─ header.console-toolbar（仅移动端显示）  标志 · .toolbar-page · 菜单按钮
    └─ main#console-content.console-content
```

- **品牌行**：
  - 现在整个品牌区是一个链接，版本号是并列的另一个链接。设计稿把版本号放在名称同一行，嵌套链接不合法，所以改为：只有标志方块是首页链接（沿用 aria 名称「flower2api 首页」），名称为普通文字，版本号链接紧随名称。
  - 品牌标志沿用品牌合同（`frontend-guidelines.md`：登录、主导航与网站图标共用 `public/favicon.svg?v=flower2api-pink-04`），放在 40px `ink` 方块上；图标的花心与通道是透明的，透出墨色，与设计稿 `flower()` 的墨色花心一致。只有侧栏与登录品牌区的图片带 `alt="flower2api 标志"`（`verify_management_polish.py` 依赖），其余装饰位置为空 alt。
- **版本号** `a.brand-update`：
  - 链接目标与点击逻辑不变（`openUpdatePanel`）。
  - 常态：填充底、`text-2`、等宽 10.5px。
  - `.has-update`：`success-bg` / `success-text`，并带 `arrow-up-circle` 图标。去掉现在的右上角小圆点。
  - 折叠态只显示图标：有更新时为 `arrow-up-circle`，否则为 `chevron`；保留 `title` 提示。
- **导航**：
  - 分组「网关 / 资源 / 工作区」带分组名；「系统设置」单独成组，与上方间隔 14px，无分组名。
  - 「主题设置」入口由子任务 5 随页面加入同一组，放在「系统设置」上方。
  - 选中项：底色 `fill-active`（§7 新增）、字重 720、图标 `primary`。悬停（设计稿未画）：底色 `fill`、文字 `text`。
  - 账号数徽标：`fill` 底，选中项内改为 `surface` 底。
  - 运行中徽标：`success-bg` 加圆点；运行数为 0 时用中性色（`fill` 底、`text-3`、圆点 `text-4`）。
  - 折叠态隐藏文字与徽标，分组名改为仅读屏可见（沿用现状）。
- **底部管理员区**：`fill-subtle` 圆角块，内含头像（`primary-container`）、「管理员 / 本地管理控制台」、折叠与退出两个 26px 图标按钮。折叠态隐藏头像与身份，两个按钮纵向排列。
- **内容区**：
  - 外壳底色取 `layout`，内边距 24 / 28 / 48（按 `space-unit` 计算）。
  - `console-native-tasks` 下内边距仍为 0（任务页全宽，`TasksWorkspace.vue` 的现有规则保留）。

### 3.2 尺寸与断点（与现状一致，只统一写法）

| 视口 | 侧栏宽 | 说明 |
| --- | --- | --- |
| ≤760px | 不显示 | 移动端：应用栏 + 抽屉 |
| 761–1000px | 224px | 内边距收窄 |
| 1001–1919px | 248px | 设计稿取值（现为 252px） |
| 1920–2559px | 264px | 沿用 |
| ≥2560px | 280px | 沿用 |
| 折叠 | 76px | 沿用 |

- 现状有 760 与 767 两个断点并存，靠 761–767 的补丁规则对齐。新样式统一为 760，删除补丁。
- 侧栏 `position: fixed` 占满视口高度。品牌行与底部区不收缩，导航区 `flex: 1; min-height: 0; overflow-y: auto`。视口变矮时只有导航滚动，底部区始终可见。
- 折叠偏好仍存 `localStorage['flower2api-sidebar-collapsed']`，逻辑不动。

### 3.3 移动端（≤760px）

- **应用栏** `header.console-toolbar`：
  - 布局：34px 墨色标志方块、页面标题 `.toolbar-page`（17px / 800）、右侧 36px 菜单按钮（填充底）。
  - 设计稿右侧的搜索按钮属于账号页，随子任务 4。
  - 应用栏不吸顶，与现状一致。
- **页面标题**：Dashboard 的标题表补齐 `session-blocks`、`nodes`（现在缺失，会回落为「管理控制台」），并改用页面标题：账号显示「账号管理」，其余页面与导航名相同。
- **抽屉**：
  - 继续使用 `Dialog`（焦点圈定、Esc 关闭、路由切换自动关闭不变）。
  - 位置与尺寸用传入的工具类覆盖 `DialogContent` 的居中定位（`cn` 合并会去掉冲突类），不再用 `!important`。
  - 内容与桌面侧栏相同：品牌行（`DialogTitle` 即名称）、`AppNavigation`、底部管理员区（无折叠按钮），白底，宽 `min(300px, 88vw)`。

## 4. 组合组件（`apps/web/src/components/ui/`）

样式写入 `kit.css` 的 `@layer components`，颜色、圆角、阴影只取 token（kit §4 的静态规则覆盖）。字号不在档位上时，用 token 加减像素的 `calc()` 表达，与 kit 现有写法一致（如 15px = `font-size-title + 1px`）。

| 组件 | 位置 | 公开 API | 设计稿取值要点 |
| --- | --- | --- | --- |
| PageHeader | `page-header/` | props `title`、`description?`；插槽 `actions`、`description`（覆盖说明文字，供子任务 5 显示待应用数） | 标题 h1 28px / 34px / 800；说明 14px / 550 / `text-3`；操作区靠右，间距 8；底边距 18px |
| OverviewGrid | `overview/` | 默认插槽 | 4 列、间距 16；≤1000px 2 列；≤600px 1 列 |
| OverviewCard | `overview/` | props `label`、`value?`、`unit?`、`caption?`、`tone?`（primary / success / warning / danger / info，默认 primary）；插槽 `icon`、`value`、`caption` | 内边距 16 / 18；标签 12 / 700；数值等宽 26px / 800；单位 13px `text-4`；说明 12px；右上图标块 36px |
| IconTile | `icon-tile/` | props `tone?`（同上，另含 cc / agy / neutral）、`size?`（md = 36px、lg = 40px）；默认插槽为图标 | 圆角分别为 `block − 2px`、`block − 1px`；底色与图标取对应语义色 |
| Toolbar | `toolbar/` | 默认插槽（左）、`end` 插槽（右） | 间距 10；`end` 靠右；窄屏换行 |
| EntityCard | `entity-card/` | props `title`、`subtitle?`；插槽 `media`、`title-extra`、`subtitle`、`status`、默认（信息区）、`actions` | 内边距 18 / 20 / 0；头部图标块 40px；名称 16 / 760；副标题 12.5 / 550；状态徽标靠右；信息区间距 12 |
| EntityBlock | `entity-card/` | 默认插槽 | `fill-subtle`、block 圆角、内边距 12 / 14 |
| EntityAction | `entity-card/` | props `tone?`（default / primary / danger）、`disabled?`；`click` 透传；默认插槽为图标 + 文字 | 操作底栏按动作数等分、上边线 `line`、36px、12.5 / 650；悬停 `fill` |
| TableCard | `table-card/` | props `title`、`count?`；插槽 `toolbar`（标题右侧）、默认（`Table`）、`footer`（分页） | 内边距 18 / 20 / 14、间距 14；标题 16 / 760，计数等宽 12px `text-4`；表格外包横向滚动容器 |
| FloatingSaveBar | `save-bar/` | props `count`、`hint?`、`cleanLabel?`（默认「已同步」）；插槽 `actions` | 吸底（`sticky`，底距 20）、上外边距 18、圆角 14、`shadow-pop`；标题 13 / 720，前置 8px 圆点（有待保存为 `warning`，否则 `success`）；说明 12px `text-3` |
| ModalDialog | `modal/` | props `title`、`description?`、`width?`（默认 820）；`v-model:open`；插槽 `media`、`title-extra`、默认（内容区）、`footer`；其余属性透传到弹窗面板 | 基于 `Dialog`：头部内边距 22 / 24 / 16、图标与标题间距 12；内容区内边距 4 / 24 / 20、单独滚动；通栏底栏 `fill-subtle`、内边距 14 / 24；最大高度 `min(840px, 100dvh − 32px)` |

- **页头的移动端形态**（设计稿未画）：≤760px 时标题与说明改为仅读屏可见（应用栏已显示标题，避免重复），只保留操作区；没有操作的页头不占高度。
- **数据表操作列固定**：`kit.css` 新增 `.fui-table-actions`，给最右列的 `TableHead` / `TableCell` 使用。它 `sticky; right: 0`，背景按行状态取 `surface` / `table-stripe` / `table-hover`，横向滚动时操作列不被遮住。
- **既有组件复用**：表格本体、分页、徽标、按钮、搜索、分段沿用子任务 1 的组件；组合组件只负责布局与组合层的样式，不复制基础控件样式。
- **居中弹窗的滚动**：`style.css` 的全局弹窗规则 `[data-slot=dialog-content] { max-height; overflow-y: auto }` 未分层，会让整个弹窗一起滚动。`kit.css` 末尾用一条未分层、选择器更具体的规则覆盖，只让内容区滚动。
- **子任务 1 的过渡白名单**：`verify_ui_kit.py` 中弹窗底栏 `.mf` 的白名单改为与居中弹窗比对后删除。
- **业务页接入后的扩展**：概览卡点击切换（请求记录的日志级别卡）、账号卡的五列操作栏等变体由子任务 4 在接入时扩展，并同步演示页。

## 5. 页头替换清单

8 个页面换成 `PageHeader`，去掉分组名（`page-eyebrow`），操作按钮去掉页面级外观覆盖，只用组件变体：

| 页面 | 文件 | 说明 |
| --- | --- | --- |
| 账号管理 | `Accounts.vue` | 「授权登录」用 outline（次要）、「添加账号」用 default，去掉 `bg-primary … rounded-xl` 等工具类与 `.account-authorize-button` 颜色规则 |
| 请求记录 | `RequestDiagnostics.vue` | 日志级别选择暂放 `actions` 插槽，子任务 4 移入概览卡 |
| 会话封禁 | `SessionPolicyBlocks.vue` | 删除组件内 `.page-heading` 的 scoped 规则 |
| 访问令牌 | `Tokens.vue` | |
| 代理管理 | `Proxies.vue` | |
| 运行环境 | `RuntimeEnvironments.vue` | 删除 `native-environment.css` 中 `.runtime-page-heading` 的规则 |
| 节点管理 | `Nodes.vue` | `.nodes-actions` 作为 `actions` 插槽内容保留布局 |
| 系统设置 | `Settings.vue` | 无操作；同时把保存栏换成 `FloatingSaveBar` |

- 标题统一为 h1（现在有 5 个页面用 h2）。页面内其它标题层级不变。
- **保存栏**：`<FloatingSaveBar class="settings-save-bar" :count="dirtyKeys.length" hint="修改将统一应用到网关" clean-label="配置已同步">`，操作仍是现有的「撤销修改」「保存配置 / 保存中…」按钮与禁用条件。删除 `style.css`、`settings-design.css` 中 `.settings-save-bar` 及无引用的 `.system-settings-savebar` 规则。

## 6. 登录页（`Login.vue`）

- **布局**：两列 1.05fr / 1fr，最小高度 100dvh。
- **左侧品牌区**（`ink` 底，内边距 56 / 64）：
  - 顶部：品牌图标 32px + 「flower2api」20 / 650。
  - 底部：大标题「让每一次调用 / 井然有序」40px / 1.15 / 650；说明「账号、环境与任务，在一个清晰的控制台里管理。」15px `ink-text`；页脚「本地管理控制台」「仅管理员可访问」12.5px `ink-muted`。
  - 第一版页脚的版本号不显示：版本接口经运行时桥接需要登录，本次不新增接口（父 PRD 范围）。
  - 背景纹理：第一版用 canvas 绘制，改为同几何的内联 SVG（`viewBox 0 0 756 900`、`slice` 铺满）。花瓣 `fill: brand` 并按原透明度，同心圆 `stroke: on-ink`、透明度 .05，整体 `aria-hidden`。好处是不依赖脚本、随分辨率清晰。
- **右侧表单**（`surface` 底，360px 居中，间距 22）：
  - 文字：「登录控制台」24 / 650；说明 13.5px `text-3`；字段标签用 `fui-label`。
  - 输入：`InputGroup` 44px，前缀锁图标，后缀显示 / 隐藏密码按钮（aria 名称「显示密码」 / 「隐藏密码」，`aria-pressed`）。输入框保持 `#admin-password`，`autocomplete="current-password"`，默认 `type=password`。
  - 切换按钮沿用设计稿的 `eye` 图标，密码可见时按压态取主色。sprite 没有 eye-off，不为此新增图标。
  - 错误提示：`role=alert`，`danger-text`。
  - 按钮：44px 主按钮，全宽，文案「登录」 / 「登录中...」。
  - 底部说明：「登录凭据保存在当前浏览器，退出后清除」（与 `router.ts` 的 `localStorage` 保存与退出清除一致）。
- **行为不变**：`submit()`、空密码「请输入密码」、失败「密码错误」、`login()` 调用与凭据存储全部沿用。
- **≤760px**：隐藏左侧品牌区，表单区内边距 24，标题上方加一行 34px 墨色标志方块 + 名称，代替被隐藏的品牌区。

## 7. 新增 token

| token | 默认值 | 主题行为 | 用途 |
| --- | --- | --- | --- |
| `--ui-color-fill-active` | `#eceef5` | 柔光材质下与其它底色组一样向主色偏移 4% | 侧栏选中项（设计稿 `.sb-item.on`） |
| `--ui-color-on-ink` | `#ffffff` | 不随主题 | 墨色底上的文字与纹理描边 |
| `--ui-color-ink-text` | `#a7abc3` | 不随主题 | 登录品牌区说明 |
| `--ui-color-ink-muted` | `#6c708e` | 不随主题 | 登录品牌区页脚 |
| `--ui-shadow-side` | `2px 0 12px -10px rgba(14,23,38,.12)` | 乘阴影强度 | 侧栏 |
| `--ui-shadow-bar` | `0 2px 12px -10px rgba(14,23,38,.2)` | 乘阴影强度 | 移动端应用栏 |

- 同步 `tokens.ts`（`NEUTRALS`、`SOFT_TINTED`、阴影派生）与 `ui-foundation.css` 默认值。`theme.test.mjs` 的双向一致性断言自动覆盖新 token。
- `ui-foundation.css` 内容变化，legacy `index.html` 中它的 `?v=` 同步更新（kit §7）。

## 8. CSS 组织

- **新文件** `apps/web/src/console-shell.css`：
  - 内容：侧栏、导航、移动端应用栏与抽屉、内容区、登录页。
  - 层：`@layer components`。在 `main.ts` 中紧跟 `kit.css` 引入，`ui-preview.ts` 不引入。
  - 唯一例外：文件末尾的 `[data-slot=dialog-content].mobile-navigation-panel { height / max-height: 100dvh }` 不分层。`style.css` 的全局弹窗高度规则未分层，层内规则压不过它，抽屉只能用同样未分层、选择器更具体的规则铺满视口高。
  - 与 `kit.css` 同受 `theme.test.mjs` 静态规则约束：颜色字面量只能出现在 token 声明里，圆角只用 token。
  - 外壳容器自身（侧栏、应用栏、抽屉）设置字体、行高、颜色，因为里面没有页面内容；内容区 `main` 不设可继承的文字属性（kit §5 的继承规则）。
- **删除的旧规则**（未分层，会压过新样式）：
  - `style.css`：
    - 外壳两段：`.console-shell` 至 `.console-frame`，以及「已确认设计的正式控制台外壳」整段中除 `body` 字号以外的部分。
    - `.page-heading` / `.page-description` / `.page-eyebrow`。
    - `.mobile-*` 与 `.login-*` 及其移动端媒体查询。
    - `.settings-save-bar`。
    - `.page-heading [data-slot=button]` 圆角。
    - `.account-authorize-button` 颜色。
    - 无引用的 `.console-metrics` 规则。
  - `approved-design.css`：侧栏、品牌、版本号、导航、计数、底部区、页头、`.console-content` 内边距，各断点下的同类规则，761–767 补丁。
  - `request-design.css`：`.request-page-heading` 系列（`.request-mode` 布局保留）。
  - `native-environment.css`：`.runtime-page-heading` 系列。
  - `settings-design.css`：`.settings-save-bar`、`.system-settings-savebar` 系列。
  - `SessionPolicyBlocks.vue`：`.page-heading` 的两处规则。
- **删除前检查**：每条规则先 grep 选择器确认只服务于外壳、页头或保存栏，账号卡片等页面主体规则不动。

## 9. 验证

1. **`node:test`**（`apps/web/tests/theme.test.mjs`）：新 token 双向一致（自动）；静态规则的检查文件增加 `console-shell.css`。
2. **`verify_ui_kit.py` 扩充**（dev server 演示页）：
   - 演示页新增「组合组件」区（`previews/CompositeShowcase.vue`），按设计稿数据给出页头、概览卡、工具栏、实体卡、数据表卡片（含固定操作列与横向滚动）、居中弹窗、浮动保存栏示例。
   - 对 `mock.html` 的 accounts / proxies / environments / settings / account-edit 画面逐项比对计算样式，新增 34 组。
3. **新增 `deploy/flower2api/verify_ui_shell.py`**：
   - 运行方式：真实构建（`dist`），夹具 `ShellFixture` 继承 `verify_dashboard_update.py` 的 `DashboardUpdateFixture`，补齐会话封禁与节点列表，并对密码 `wrong-password` 返回 401。夹具不提供深链接页面，各页经侧栏导航进入。
   - 白名单：版本号与名称的 7px 间距（设计稿为父级 flex 间距，外壳为网格左外边距）；登录表单文字颜色取第二版 token；登录输入与按钮统一为组件库大号 44px（第一版 40px）。
   - 1440×900：
     - 侧栏、品牌行、版本号、导航选中与悬停、两种计数徽标、底部区、内容区边距，对 `mock.html#accounts` 逐项比对。
     - 版本号「有更新 / 无更新」两态。
     - 折叠 / 展开，以及刷新后保持。
     - 1440×560 矮视口下导航内部滚动，底部区可见。
   - 8 个页面：页头无分组名，标题、说明、操作按钮的计算样式等于设计稿。
   - 系统设置：保存栏比对 `mock.html#settings`；修改一项后显示「1 项待保存」，撤销后显示「配置已同步」。
   - 390×844：
     - 应用栏比对 `mock.html#mobile`，标题随路由变化。
     - 抽屉打开、导航、自动关闭；页面无横向溢出；页头只剩操作。
   - 登录：
     - 1440 比对 `v1/mock.html#login`：品牌区、标题、说明、标签、底部说明；输入与按钮按 kit token 取值。
     - 390 形态。
     - 空密码、错误密码、成功登录三条行为路径。
     - 显示 / 隐藏密码切换。
   - 全程零控制台错误。
   - 1440 / 390 截图存 `.deploy/console-ui-revamp/ui-shell/`（git 忽略）。
4. **既有脚本分诊**（规则同 kit §7：外壳与页头的样式采样移出旧原型比对，行为断言不放宽）：
   - `verify_exact_design.py`：移除品牌标志、品牌文字、版本按钮、品牌说明、页面标题、页面说明、眉题、侧栏文字、侧栏分组、页头主按钮采样，字体回退核对去掉页面标题（由 `verify_ui_shell.py` 覆盖）。
   - `verify_ui_refinements.py`：
     - 卡片区宽度原先与旧原型比对，实际量的是侧栏宽与内容区边距，改为核对卡片区铺满内容区；列数仍与定稿逐断点一致。
     - 用量气泡阴影属于组件库，移出比对；移除侧栏悬停采样。
   - `verify_viewport_interactions.py`：卡片区右边距原先写死 40，改为等于内容区实际右内边距。
   - `verify_frontend_navigation.py`：`.toolbar-page` 期望改为页面标题（账号为「账号管理」）。
   - `verify_workspace_stability.py`、`verify_native_environment_edges.py`：`.runtime-page-heading button` 改为页头内的刷新按钮定位。
   - `audit_full_design.py` 未受影响，无需改动。
   - 业务断言不放宽。
5. **回归集**：
   - 子任务 1 的 37 个脚本回归集，加集合外 26 个脚本。
   - 先在当前 HEAD 跑基线，改动后对比。基线已失败的脚本，核对失败点是否相同。

## 10. 发布与回滚

- 单独提交、单独发版。不改后端、网关、运行时桥接白名单与镜像构建。
- 新增 `doc/design/console-v2/v1/`（登录基准），以及 legacy `index.html` 中 `ui-foundation.css` 的 `?v=` 更新。
- 回滚即回退本任务提交：外壳与页头恢复旧样式，新增 token 随之移除；子任务 3–6 若已依赖本任务，需一并回退（父设计 §7）。
