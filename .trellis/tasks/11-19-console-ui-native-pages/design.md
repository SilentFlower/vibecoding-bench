# 技术设计 — 原生页视觉对齐

证据与现状数字见 `prd.md` Background。父任务边界见 `../11-19-console-ui-revamp/design.md` §1、§3。

## 1. 样式架构

### 1.1 原生类名保留，原生 CSS 只取 token（关键决定）

- 任务与工程的模板（`index.html`）和 JS 字符串继续使用原生类名（`.btn`、`.native-choice-trigger`、`.modal-card`、`.work-*` 等）。原生 CSS 重写为只引用 `--ui-*`，不在原生模板里改用 `.fui-*` 类。原因：
  - 独立 `/runtime/` 文档不加载 Vue 的 `kit.css`，`.fui-*` 类在那里没有样式。
  - 模板与 JS 里共有约 125 处 `.btn`（JS 字符串 39 处），几十个验证脚本也按原类名定位；只改样式风险最低。
- **原生部件与组件库部件一一对应**：尺寸、字重、圆角、颜色、状态（悬停 / 焦点 / 禁用 / 选中）取 `kit.css` 同名部件的同一组 token 与表达式。对应关系写进规范，验证脚本在同一页面上比对两者的计算样式（§6）。

| 原生 | 组件库 | 要点 |
| --- | --- | --- |
| `.btn` / `.btn-sm` / `.btn-primary` / `.btn-danger` | `.fui-button` / `-sm` / `-default` / `-destructive` | 无描边，`--ui-radius-btn`，高 `--ui-control-md/sm` |
| `.field input`、`textarea`、`.work-search`、原生 `<select>` | `.fui-input` / `.fui-textarea` / `.fui-search` | 填充底，`--ui-radius-control`，焦点主色细环加 `primary-ring` |
| `.native-choice-trigger` / 菜单 | `.fui-choice` / `.fui-choice-menu` | 弹层 `--ui-shadow-pop` |
| `.native-number` | `.fui-number` | `:focus-within` |
| `.native-time-trigger` | `.fui-date-trigger` | |
| 复选 / 单选 | `.fui-checkbox-box` 外观 | 用 `accent-color: var(--ui-color-primary)`，保持原生控件 |
| `.work-navigation` | `.fui-segmented` | 托盘按内容排列，选中项为表面色加 `--ui-shadow-raised` |
| `.work-badge`、`.pill-*` | `.fui-badge` + dot | 语义色取 `*-bg` / `*-text` |
| `.work-strip[data-tone]`（新增） | `.fui-strip[data-tone]` | 36px，`radius-control + 2px` |
| `table.data` / `.table-frame` | `.fui-table` / `.fui-table-card` | 圆角表头条、斑马行、悬停行 |
| `.work-panel.work-account` | `.fui-entity-card` | 无描边，`--ui-radius-card` + `--ui-shadow-card` |
| `.modal-card` / `.modal-titlebar` / 底部按钮行 | `.fui-modal` / `-head` / `-foot` | 圆角 card，标题 `--ui-font-size-heading`/780，底栏 `--ui-color-fill-subtle` |
| `.work-empty` | `.fui-empty-state` | |

- 运行环境是 Vue 页，直接换用组件：`Segmented`、`Toolbar`、`EntityCard`、`EntityBlock`、`EntityAction`、`IconTile`、`Badge`。`native-environment.css` 改为 `@layer components`，只取 token，与子任务 4 的页面样式一致。

### 1.2 变量与字面量

- **删除全部旧变量定义块**：`style.css:6`、`:1280`，`console.css:2`，`approved-design.css:4`，`environments.css:2`，`work-design.css:14,575`，`environment-design.css:173`，`native-environment.css:174,279`。引用处直接改成 `--ui-*`；`--border`、`--muted` 不再在作用域根上重定义，同名冲突随之消失。

| 旧变量族 | 新 token |
| --- | --- |
| `--ink`、`--text`、`--work-ink` | `--ui-color-text` |
| `--text-dim`、`--muted`、`--work-muted`、`--text-muted` | `--ui-color-text-3`（次要正文 `--ui-color-text-2`，弱提示 `--ui-color-text-4`） |
| `--line`、`--border*` | `--ui-color-line` |
| `--bg*`、`--surface-2/3` | `--ui-color-layout` / `--ui-color-fill-subtle` / `--ui-color-fill` |
| `--surface` | `--ui-color-surface` |
| `--accent`、`--violet`、`--amber*` | `--ui-color-primary` / `-text` / `-container` |
| `--running/success/failed/queued/timeout`、`--green` | `--ui-color-success\|danger\|info\|warning` 及其 `-text` / `-bg`；`*-glow` 删除 |
| `--body-font`、`--display`、`--env-font` | `--ui-font-family` |
| `--mono` | `--ui-font-family-mono` |
| `--env-*` | 按用途归入以上各族 |

- **颜色字面量**：
  - 先列出去重后的调色板，按用途（正文层级、描边、填充、主色、状态色）逐一映射到 token；映射表在实施时生成，作为证据保存在 `.deploy/console-ui-revamp/native-pages/palette.json`。
  - 设计稿没给的悬停、按下色用 `color-mix()` 由 token 混合。
  - 遮罩用 `--ui-color-mask`，滚动条用 `--ui-color-scrollbar`。
- **圆角**：按部件角色取 `--ui-radius-btn/control/block/card`，圆点与胶囊保留 `50%` / `999px`。
- **字号**：旧层字号（`--ui-font-small/body/card/heading`）换成新字号 token。页面基准 13px / 1.55 / `--ui-color-text` 设在 `.runtime-body`。
- **`!important`**：只保留以下必需的例外，其余靠选择器特异性或删除：xterm viewport 底色（覆盖第三方行内样式）、`.hidden` 工具类与 `[hidden]`、`prefers-reduced-motion` 全局重置（一份）、原始 `select.native-choice-source` / `input.native-time-source` 的视觉隐藏；Vue 运行环境页的分区 `[hidden]`。
- **终端**：`.xterm-host`、`.work-terminal`、`.upgrade-terminal`、`#acc-login-xterm` 统一取 `--ui-color-ink`，文字取 `--ui-color-ink-text`。xterm 自身的 JS 配色不动（子任务 7）。

### 1.3 文件

- **保留文件名**：`runtimeModule.ts` 的 styles 列表、独立 `index.html` 的 `<link>` 和桥接白名单都不变。
  - 每份文件按职责整理并删除无效规则。
  - 清理后为空或只剩几条的文件并入相邻文件后删除，并同步：桥接白名单匹配臂、`design_assets_remain_available_through_runtime_bridge` / `environment_assets_are_exact_and_read_only` 测试、`runtimeModule.ts:9`、`index.html` 的 `<link>`。
- **改动过的原生 CSS** 在 `index.html` 把 `?v=` 改为 `20261120-native-pages`。
- **`extract_environment_styles.py` 删除**：它把旧原型的 CSSOM 写回 `environment-design.css`，再运行会覆盖本次迁移。
- **图标 sprite**：两份 sprite 补上 `i-todo`、`i-activity`（路径取 `doc/design/console-v2/icons.js`），legacy 那份补上漂移缺失的 `i-sliders`。新增单测断言两份文件逐字节一致。

## 2. 任务与工程

- **页头**：删除 `p.page-eyebrow`。`.runtime-heading` 的 h1 与说明取 `.fui-page-header` 的规格（`--ui-font-size-page`/800、`--ui-font-size-md`/550 `text-3`）。上边距与 Vue 页头对齐。
- **页签** `nav.work-navigation`：
  - 改为分段托盘，按内容宽度排列，保留 `<a data-tab>` 与 `aria-current` 语义。
  - 图标 users / box / zap / todo / activity / list，只改 sprite 引用。
  - 「任务账号」后加 `<em class="work-tab-count" hidden>`。`renderAccounts()` 读取成功后写入账号数并显示；读取前和失败时隐藏。
  - ≤760px 托盘横向滚动、不换行。
  - 嵌入模式下隐藏的第 7 项「运行环境」保持现状。
- **区块头**：`.work-list-title` 与其后的 `.work-list-toolbar` 由同一网格排成一行：标题与说明在左，搜索（300px）与主按钮在右。必要时在模板里把二者包进同一容器，id、焦点顺序与事件绑定不变。≤760px 工具栏占满一行，搜索与主按钮同排、放不下时换行（Check-All CHK-001 后按实际形态更新）。
- **任务账号卡** `article.work-panel.work-account`（`app.js:693-703`，只改样式类与少量包装）：
  - **外壳**：实体卡；网格三列，间距 16。
  - **头部**：
    - `.initial` 用图标块样式（40px，`primary-container`）。
    - 名称按钮用 `--ui-font-size-card`/760；`small` 为副标题。
    - `.work-badge` 为带圆点的徽标：「整体已启用」success，「新工作已关闭」neutral。
  - **代理行**：线路名在左，「切换代理」用 `primary-text`。
  - **节点块** `.work-account-node`：`fill-subtle` + `radius-block`。
  - **键值行**：名称 `text-3`，值 `text`。
  - **链接与养号按钮**：`primary-text`。
  - **网关区** `.work-gateway-actions`：放在 `fill-subtle` 块里，状态 `<p>` 换为 `<p class="work-strip" data-tone role="status">`（带图标）：

    | 条件（取自现有 `message` 计算，`app.js:692`） | tone | 文案 |
    | --- | --- | --- |
    | `passive_quota.account_error` | danger | 原 `passive_quota.message` |
    | `passive_quota.source==='manual'` | info | 额度已手动更新。 |
    | 其余（已关联 / 未关联） | neutral | 原提示语 |

    已关联时「重新授权并同步」「解绑」保留在提示条上方；未关联时保留「创建网关账号」「关联已有账号」。「凭据交接对账」链接不变。
  - **底部 7 个按钮**：`footer` 改为等分操作栏，规格同 `.fui-entity-card-actions` / `.fui-entity-action`（顶边分隔线、无描边按钮、悬停填充）。每行最少 96px，放不下时换行，「删除」为 danger 色。按钮的 data 属性与文案不变。
- **登录草稿区与加载状态**：
  - `#work-login-drafts` 为普通卡片。
  - `#accounts-load-status` 读取中为中性提示条；失败时为 danger 提示条，重试按钮保留。
- **其余五个页签**：
  - 面板为卡片（`--ui-radius-card` + `--ui-shadow-card`，无描边）；表格按 `.fui-table` 规格；状态 pill 为语义徽标；空态按 `.fui-empty-state`。
  - 养号、工程、交付等区块的结构和字段顺序不变。
  - 已由 Vue 托管的分页（`pagination.css`）不改。
- **原生弹窗**：
  - `.modal` 遮罩取 `--ui-color-mask`；`.modal-card` 取表面色、`--ui-radius-card`、`--ui-shadow-modal`，无描边。
  - 标题栏为 `--ui-font-size-heading`/780，无底边线；底部按钮行为 `fill-subtle` 底栏。各弹窗宽度不变（脚本断言 600 / 880 / 900 / 920 等）。
  - `.modal-frame` 角框、`.scanlines`、提示符装饰删除。
  - `#continue-modal` 标题「run / continue」改为「继续运行」。
  - 独立入口专用的 `#auth-modal` 只换外观，文案不变。
- **Vue 弹窗**：
  - `RunDetails.vue`、`TaskProxyDialog.vue` 的 `<style>` 改为只取 token，结构、宽高与行为不变。
  - `CaptureWorkspace.vue` 通过 `capture-workspace.css` 同步改。
  - `TasksWorkspace.vue` 的 `<style>`（连接中提示条等）同样只取 token。

## 3. 运行环境

- **工具栏**：
  - `Toolbar` 内依次是 `Segmented`（全部环境 / 就绪 / 需要关注 / 已停止，带计数，`label="环境状态筛选"`）、结果计数文本、spacer、`SearchInput`（280px）。
  - 「显示全部环境」按钮跟在计数后面。≤760px 时搜索换行并占满。
  - 原 `button[aria-pressed]` 改为 `role=radio`，相关脚本随之更新。
- **卡片** `EntityCard.environment-rich`：保留 `data-environment`、`aria-label`；标题由 h2 变为 h3，脚本随之更新。
  - **头部**：
    - 媒体位是 `IconTile`，色调取平台 cc / agy；标题后接 `PlatformBadge`。
    - 副标题为「网关账号 #N / 任务账号 #N / 待提交的授权环境」加 `ExecutionNodeBadge`。
    - 状态位为 `Badge dot`，tone 沿用 `tone(row)` 的四类映射。
  - **信息行**：环境 ID（等宽）与「第 N 代」。
  - **三组件托盘** `.environment-role-strip`：
    - 托盘 `fill-subtle`、`radius-control + 2px`；每段为表面色。
    - 运行中：成功圆点加 `success-text`；其余：圆点与文字为 `text-4`。
  - **资源四格**：数值 800 / `--ui-font-size-card`+1px。≤760px 两列。
  - **版本行**：「内核 ›」按钮为 `primary-text`。
  - **预热块** `.environment-readiness`：改由新函数 `preparationTone(row)` 决定，与显示的 `preparationLabel(row)` 同源：
    - `ready` 为 success；
    - `failed` 为 warning；
    - 其余（准备中、等待准备、休眠、停用、维护、待检查、AGY 无摘要）为 neutral。
  - **CRIU / 内容采集、运行时段行**：按钮外观，入口与参数不变。
  - **操作栏**：四个 `EntityAction`（环境详情为 primary）。
- **环境管理侧抽屉**（`runtime-environment-dialog`，宽 940，全高贴右）：
  - 头部、上下文行、左侧分区导航（选中项与系统设置分类导航一致：表面色加卡片阴影）、内容区、键值属性、`details` 折叠块、物理特征表（`.fui-table` 规格）、维护选项行，全部取 token。
  - `EnvironmentResources`、`EnvironmentKernel`、`RunWindowForm` 用到的类同步。
- **布局**：网格 >1150px 两列、≥1800px 三列，保持不变；≤760px 单列。

## 4. 独立 `/runtime/` 入口

- 共享的原生样式迁完后，独立入口自动显示第二版默认主题（`ui-foundation.css` 的默认值）。
- 环境页签专用的 `environments.css`、`environment-design.css` 只做 token 化和死规则清理，结构不变；`:root.environment-page` 作用域保留。
- `index.html` 内联的 `data-theme='light'` 保持（子任务 7）。

## 5. 390 宽（设计稿未画，按账号移动稿和已迁页面的规则推导）

- 两页单列，页面无横向滚动。
- 任务页：页签托盘横向滚动，区块头换行，卡片操作栏自动换行。
- 环境页：工具栏换行，资源两列。
- 弹窗沿用现有 `min(宽, 100vw - 28px)`。
- 截图作为证据，供用户目视确认。

## 6. 验证

- **新脚本 `deploy/flower2api/verify_native_pages_design.py`**（写法同 `verify_records_pages_design.py`）：
  - **设计稿比对**：`PAIRS` 对照 `mock.html#tasks` 与 `#environments`，覆盖页头、页签托盘、页签项与选中项、区块标题、搜索、主按钮、卡片外壳、头部、图标块、名称、副标题、徽标、节点块、键值行、提示条、环境分段、托盘与分段、资源格、预热块 s / n / w、操作栏。
  - **白名单 `KNOWN`**：逐条写原因，例如设计稿内联 style 与组件规格的差异、产品比设计稿多的元素。
  - **部件一致性**：同一 `/tasks` 页上，原生 `.btn`（默认 / sm / primary / danger）、输入、选择、数字输入与 Vue 页头按钮、`ProxyPicker` 等同类部件逐项比对计算样式。
  - **主题跟随**：写入非默认主题（蓝色主色、圆角 4、字号 14）后刷新，断言 `/tasks` 主按钮、页签选中项、卡片圆角、弹窗圆角，以及 `/environments` 徽标和操作栏随之变化；独立 `/runtime/#accounts` 仍为默认主色。
  - **深层弹窗**：逐个打开 R4 所列弹窗（独立入口专用的两个在 `/runtime/` 下打开）和环境抽屉各分区，断言圆角 card 和无描边，并截 1440 / 390 图。
  - **390 宽**：两页加弹窗无横向溢出，零 pageerror。
- **静态规则**（`apps/web/tests/theme.test.mjs`）：
  - sheets 加入 legacy 7 份 CSS（style、environments、console、approved-design、work-design、environment-design、capture-workspace）与 `native-environment.css`。
  - shell 列表加入 `RuntimeEnvironments.vue`、`TasksWorkspace.vue`、`CaptureWorkspace.vue`、`runtime/RunDetails.vue`、`runtime/TaskProxyDialog.vue`、`runtime/EnvironmentResources.vue`、`runtime/EnvironmentKernel.vue`、`runtime/RunWindowForm.vue`。
  - 新增断言：legacy CSS 中没有旧变量定义块（例如 `--ink:`、`--line:`、`--muted:`）。
- **迁移旧原型比对脚本**：
  - `verify_task_account_config`、`verify_task_feedback_styles`、`audit_token_task_design`、`verify_dialog_typography` 删除对 `flower2api-concept.html` 的样式比对，留注释指向新脚本，行为断言保留。
  - `audit_full_design`、`audit_environment_proxy_design` 的任务 / 环境用例同样处理。
  - 写死布局值的断言只在设计确实改变该值时修改，并写明原因。
- **修好移交的 4 个失败**（按现行合同，不放宽行为断言）：
  - `verify_task_login_design`：先关闭选线弹层，再点名称输入。
  - `verify_native_environment_edges`：标题期望改为不含徽标的名称节点，分段改用 radio。
  - `verify_native_lifecycle`：URL 期望带 `&account=1`；删除 `#theme-toggle` 步骤，改为断言宿主 `data-theme=light`。
  - `verify_frontend_navigation`：删除主题切换按钮断言（该按钮已于先前版本移除，子任务 7 另立模式切换）。
- **回归**：
  - 基线复用子任务 5 的最终回归（产品代码未变），runner 复制到 `.deploy/console-ui-revamp/native-pages/`，加入新脚本。
  - 期望只剩 3 个已登记失败（真实发行物 2 个、系统更新检查写入 1 个），失败点不变。
- **其它**：
  - `node --check` 检查 4 个原生 JS。
  - 构建。
  - 白名单若有变动，跑 `cargo test` 中的桥接测试。

## 7. 回滚

单次提交。回退该提交即可恢复原生页旧样式；不涉及数据和接口。
