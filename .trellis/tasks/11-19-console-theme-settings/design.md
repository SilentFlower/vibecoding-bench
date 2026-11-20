# 技术设计：主题设置页

跨子任务约定见父任务 `../11-19-console-ui-revamp/design.md`，主题运行时细节见子任务 1 `../11-19-console-ui-kit/design.md` §2–§3。本文只定本页的结构、状态与验证。

## 1. 改动范围

| 文件 | 改动 |
| --- | --- |
| `apps/web/src/theme/editor.ts`（新） | 编辑器纯函数（§3），由 `theme/index.ts` 导出 |
| `apps/web/src/components/ThemeSettings.vue`（新） | 页面：草稿状态、页头、编辑面板、离开保护 |
| `apps/web/src/components/theme/ThemePreview.vue`（新） | 预览画板：iframe、缩放、平移、草稿注入 |
| `apps/web/src/theme-settings.css`（新） | 页面样式，`@layer components`，只取 token |
| `apps/web/src/router.ts` | 外壳子路由 `{ path: 'theme', name: 'theme' }` |
| `apps/web/src/components/AppNavigation.vue` | 底部组改为「主题设置」（`Palette`）+「系统设置」，更新注释 |
| `apps/web/src/components/Dashboard.vue` | `titles` 加 `theme: '主题设置'`；预览标记下跳过自动检查更新（§4.3） |
| `services/gateway/src/handler/router.rs` | SPA 列表加 `/theme`（尾斜杠别名由循环自动登记）；路由测试加 `/theme`、`/theme/` |
| `apps/web/tests/theme.test.mjs` | 编辑器纯函数用例；静态样式规则的文件清单加入三个新文件 |
| `deploy/flower2api/verify_theme_settings.py`（新） | 浏览器验证（§6） |
| `deploy/flower2api/verify_ui_shell.py` | 侧栏与应用栏标题清单（`:90`）加「主题设置」 |
| `.trellis/spec/web/frontend/ui-guidelines.md` | 主题设置页合同、测试清单、侧栏说明（`:187`） |

不改主题运行时的派生与存储格式（`tokens.ts`、`runtime.ts`、`ui-foundation.css`），不新增依赖。

## 2. 页面结构

```
ThemeSettings.vue
├─ PageHeader  标题 · 说明 + 状态（N 处修改待应用 · M 项输入无效 / 已同步） · 撤销草稿 / 恢复默认 / 保存并应用
├─ .theme-layout（桌面两列 340px + 1fr，390 单列）
│  ├─ aside.theme-panel（Card）
│  │  ├─ 主题预设：6 张卡片（三列），选中态 = 主色等于该预设
│  │  ├─ 表面材质：Segmented 默认 / 柔光
│  │  ├─ Segmented 颜色 / 尺寸 / 风格（各带已修改或无效字段数）
│  │  └─ 当前分类的字段列表
│  └─ ThemePreview（Card）：标题「实时预览」+ 说明 · 缩放条 · 画布
└─ ConfirmationDialog（离开确认）
```

- **颜色字段**（设计稿 `.tf`）：色块是原生 `<input type="color">`（去掉默认外观，`aria-label`「品牌主色取色器」等），右侧 hex 用 `Input`（等宽字体，`aria-label`「品牌主色 hex 值」）。名称后挂「已修改」`Badge` 和单项恢复按钮。
- **数值字段**：`NumberInput`，`min` / `max` / `step` 取自 `THEME_SEED_LIMITS`。「已修改」与恢复按钮放在 `label-extra` 插槽，沿用 `Settings.vue:834`。
- **单项恢复按钮**：图标按钮（`Undo`），`aria-label`「恢复已保存的 <字段名>」，只在该字段已修改或无效时出现。
- **标记位置**：表面材质的「已修改」挂在分组标题后；主色的「已修改」只挂在颜色分类的「品牌主色」行，预设卡片不挂。
- **字段文案**：

| 分类 | 字段（种子键） | 说明 |
| --- | --- | --- |
| 颜色 | 品牌主色 `primary` | 完整色阶与界面基调 |
| 颜色 | 成功色 `success` / 警告色 `warning` / 错误色 `danger` / 信息色 `info` | 成功反馈与状态 / 额度与风险提醒 / 失败与破坏性操作 / 系统与请求信息 |
| 尺寸 | 基础字号 `fontSize` · 控件高度 `controlHeight` · 尺寸步长 `sizeStep` · 基础间距 `spaceUnit` | 单位 px |
| 风格 | 通用圆角 `radius` · 阴影强度 `shadow` | 圆角单位 px，阴影为倍数 |

- **尺寸分组加控件高度**：参考项目的尺寸分组只有字号、间距、步长，但本项目种子已有 `controlHeight` 及其范围（子任务 1 design §2.4 写明供本页共用）。尺寸步长只决定 sm / md / lg 三档的差值（`ui-foundation.css` 中 `--ui-control-sm/md/lg = base ∓ step`），不开放控件高度就无法调整控件主高度。
- **预设卡片样式**：预设色经内联自定义属性 `--theme-preset` 传入（数据而非样式字面量）。色带用 `linear-gradient` 混合 `--theme-preset`、`color-mix(... var(--ui-color-surface))` 与 `--ui-color-fill-muted`。卡片底与选中外圈分别取 `fill-subtle` 与 `--theme-preset`。
- **画布样式**：点阵用 `--ui-color-fill-strong`，画板阴影用 `--ui-shadow-pop`，不照搬设计稿的写死颜色。

## 3. 状态与纯函数（`theme/editor.ts`）

```ts
/** 种子中可编辑的字段，顺序即界面与计数顺序。 */
export const THEME_SEED_KEYS: readonly (keyof Omit<ThemeSeed, 'version'>)[];
/** 返回 draft 与 saved 不同的字段。 */
export function changedSeedKeys(draft: ThemeSeed, saved: ThemeSeed): ThemeSeedKey[];
/** 大小写的 #rgb / #rrggbb → 6 位小写；其它返回 null。 */
export function normalizeHexInput(text: string): string | null;
/** 文本 → 数值；为空、非数、越界或不对齐步长返回 null。 */
export function parseSeedNumber(key: NumericSeedKey, text: string | number): number | null;
/** 主色对应的预设 ID，不匹配返回 null。 */
export function presetIdOf(primary: string): string | null;
```

- **页面状态**：
  - `saved`：`readStoredTheme() ?? DEFAULT_THEME_SEED`，保存成功后更新。
  - `draft`：`reactive` 种子，进入页面时复制 `saved`。只有通过校验的值才写入 `draft`。
  - `inputs` / `errors`：每个颜色和数值字段的输入文本与错误文案。输入无效时 `draft` 保留上次的有效值，画板不变。
- **派生量**：
  - `changed = changedSeedKeys(draft, saved)`，页头 N = `changed.length`。
  - `invalid = 存在 errors`。
  - `atDefault = changedSeedKeys(draft, DEFAULT_THEME_SEED).length === 0`。
- **操作**：

| 操作 | 结果 | 可用条件 |
| --- | --- | --- |
| 改字段 | 校验通过写 `draft`，否则写 `errors` | — |
| 单项恢复 | 该字段 `draft`、`inputs` 回到 `saved`，清除错误 | 字段已修改或无效 |
| 撤销草稿 | `draft = saved`，清空 `inputs` 与 `errors` | `changed > 0` 或 `invalid` |
| 恢复默认 | `draft = DEFAULT_THEME_SEED`，清空错误，需再保存 | 不是 `atDefault`，或存在 `invalid` |
| 保存并应用 | 见下 | `changed > 0` 且非 `invalid` |

- **保存并应用**：
  1. 调用 `writeStoredTheme(atDefault ? null : draft)`。
  2. 返回 `false` 时提示「当前浏览器无法保存主题」，草稿保留，控制台不变。
  3. 成功时执行 `applyTheme(document.documentElement, createTheme(draft))`，令 `saved = draft`，并提示「主题已保存并应用」。
  4. 保存默认主题时根上仍写默认变量，与 CSS 默认值相同；刷新后不再有内联变量。

## 4. 预览画板（`ThemePreview.vue`）

### 4.1 隔离方式

- **嵌入方式**：同源 `<iframe src="/?theme-preview=1">` 固定 1440×900，按缩放比例 `transform` 放入画布。这是用户确认的方案：渲染真实首页。
- **草稿注入**：iframe 的 `load` 事件里，以及 `draft` 深度变化时，执行 `applyTheme(frame.contentDocument.documentElement, createTheme(draft))`。
  - iframe 内应用自身的 `initTheme()` 先应用已保存主题；`createTheme` 输出完整键集，注入后整组覆盖，不残留。
  - 模块脚本在 `load` 之前执行，不会被应用自身的初始化反向覆盖。
- **为什么用 iframe**：不在当前文档里直接渲染页面组件。iframe 天然隔离以下内容：
  - CSS 变量、Teleport 弹层（Teleport 到 iframe 自己的 body）、`position: fixed`；
  - 媒体查询与阅读档位：iframe 视口 1440 宽，`--ui-tier` 为 0，与设计稿一致。
  在当前文档里内嵌页面组件做不到这些，且外壳会按真实视口宽度排版。
- **只读**：iframe 设 `inert`、`tabindex="-1"`、`pointer-events: none`、`title="主题预览画板"`。指针事件全部落在画布上，用于平移，画板内无法误触业务操作。
- **认证**：同源 iframe 读取同一份 `localStorage` 凭据与 Cookie，与多开一个标签页等价。`grant_session` 每次只签发，不撤销已有会话（`service/runtime_bridge.rs:383-393`），不影响当前页。

### 4.2 缩放与平移

- **状态**：`scale`（10%–150%；390 宽适应约需 19%，下限因此取 10%）与 `offset {x, y}`。画板变换为 `translate(x, y) scale(s)`，原点在左上。
- **缩放方式**：
  - 进入页面和点「适应」时：`s = min((W − 48) / 1440, (H − 48) / 900)`，然后居中。
  - 画布尺寸变化（`ResizeObserver`）时，只有尚未手动缩放或平移才重新适应。
  - 减 / 加按钮以画布中心为锚点，每次 ±10 个百分点。
  - 滚轮在画布上以指针为锚点，每格 ±10 个百分点，并 `preventDefault`，页面不随之滚动。
  - 百分比显示为 `Math.round(s × 100)%`。
- **平移**：在画布上 `pointerdown` 后 `setPointerCapture`，`pointermove` 累加位移。
- **按钮**：缩放条的按钮都有 `aria-label`（缩小、放大、适应画布）。到达范围边界时对应按钮禁用。
- **画布提示**：左下角显示「拖动画布平移 · 滚轮缩放」。画板不接收指针，拖动画板本身也平移，所以不沿用设计稿的「拖动空白处」。

### 4.3 画板内外壳的副作用

- **问题**：`Dashboard.vue` 挂载时会调用 `refreshMetadata(false, true)`。没有在途检查时，这会发起 `POST` 自动检查更新（`api.systemUpdateCheck`）。
- **处理**：画板里的外壳不应重复这个写入。`Dashboard.vue` 读取 `route.query['theme-preview'] === '1'`，为真时以 `checkUpdates = false` 调用，其余只读摘要照常读取，侧栏数据保持真实。
- **代价**：打开主题页时多一组只读请求，包括账号列表、概览、运行摘要和账号页轮询。离开主题页时 iframe 随组件卸载，请求随之停止。

## 5. 离开保护

- **站内导航**：`onBeforeRouteLeave` 中，有未保存的改动（`changed > 0 || invalid`）时打开 `ConfirmationDialog`：
  - 标题「放弃未保存的主题修改？」，说明「草稿只在本页有效，离开后丢失。」，确认文案「放弃并离开」，`danger`。
  - 守卫返回一个 Promise，由确认或取消决定放行或拦截。
- **退出登录不拦截**：去往 `login` 的导航直接放行，草稿丢弃。
  - 原因：`logout()`（`router.ts`）先撤销会话、清除凭据，再跳转登录页。如果此时拦截并让用户留下，页面会停在已失去凭据的状态。
  - 修改 `logout()` 的顺序会影响所有页面，草稿也只是本地临时数据，所以不改。
- **刷新与关闭**：有改动时注册 `beforeunload`（`preventDefault` 加 `returnValue = ''`），没有改动或组件卸载时移除。

## 6. 验证

- **`node:test`**（`tests/theme.test.mjs`）：
  - `changedSeedKeys`：无差异、单字段、全部字段。
  - `normalizeHexInput`：`#ABC` → `#aabbcc`；`#2F6BD8` → 小写；`2f6bd8`、`#12345`、`#ggg`、空串 → null。
  - `parseSeedNumber`：边界值、越界、不对齐步长（如 `shadow` 0.3）、空串、非数。
  - `presetIdOf`：6 个预设命中，自定义色返回 null。
  - 静态样式规则的文件清单加入 `theme-settings.css`、`ThemeSettings.vue`、`theme/ThemePreview.vue`。
- **浏览器验证** `verify_theme_settings.py`：
  - 真实构建加合成接口，夹具复用账号页夹具，并把 `/theme` 加入 SPA 路径。
  - 断言点：

| 流程 | 断言 |
| --- | --- |
| 入口 | 侧栏「主题设置」在「系统设置」之前，选中态正确；直接访问与刷新 `/theme` 可用；390 应用栏标题为「主题设置」 |
| 预览隔离 | 选「深海蓝」后，iframe 根 `--ui-color-primary` = `#2f6bd8`，页面根仍为默认；画板内主按钮背景随之变化 |
| 计数与标记 | 页头显示「1 处修改待应用」，品牌主色行有「已修改」；再改字号后为 2；单项恢复后回到 1 |
| 撤销 / 默认 | 撤销草稿后显示「已同步」，iframe 回到已保存值；恢复默认后草稿为默认、仍待保存 |
| 保存 | 保存后页面根变为新主色，`localStorage['flower2api.theme']` 为对应种子；刷新后首屏（`DOMContentLoaded` 时）根上已是新主色 |
| 保存默认 | 存储键被删除 |
| 校验 | hex 输入 `#12` 与数值越界、不对齐步长都提示且保存禁用，iframe 变量不变；`#ABC` 规范为 `#aabbcc` |
| 存储异常 | 写入篡改值或非 JSON 后进入页面，回退默认且控制台无报错；`setItem` 抛错时保存提示失败、根不变 |
| 离开保护 | 有草稿时点侧栏「账号」出现确认：取消则留在本页，确认则离开；无草稿时直接离开；有草稿时退出登录不弹确认 |
| 画板 | 缩放按钮、滚轮、适应改变百分比；拖动改变位移；iframe 不可聚焦；画板内外壳没有发出 `POST /runtime/api/system-updates/check`（`api.ts:703`） |
| 布局 | 1440×900 与 390×844 截图；390 单列、无横向溢出；零控制台错误 |

- **截图对照**：截 1440 与 `mock.html#theme` 的对照，放在 `.deploy/console-ui-revamp/theme-settings/`（git 忽略）。
  - 设计稿中的「全局 / 组件」页签、Token 搜索、主题模式和「组件校样」不在首版范围，对照时注明。
- **既有回归**：
  - `verify_ui_shell.py` 加入新条目后通过。
  - 回归运行器的 36 + 26 个脚本与基线对照，没有新增失败；已登记的 7 个既有失败保持原失败点。

## 7. 兼容与回滚

- 存储格式不变，旧版本保存的种子照常读取。回退本子任务后，已保存的主题仍由 `initTheme()` 生效，只是没有编辑入口。
- 回滚方式：回退本子任务提交。网关路由与前端一起回退。
