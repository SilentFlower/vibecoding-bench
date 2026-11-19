# Brief — 控制台组件库与主题运行时

## Goal

- 在 `apps/web` 建立自建组件库的地基：由种子 token 派生 CSS 变量的主题运行时，加上按第二版视觉重做的基础组件与演示页，供后续 6 个子任务迁移使用。

## Scope

- 主题运行时 `apps/web/src/theme/`：
  - 种子 → token 派生；6 个预设、自定义主色、柔光材质；
  - 存储读写与校验；应用到文档根或局部容器；`main.ts` / 演示页在挂载前应用。
- 新 token 默认值与三档阅读尺寸派生，放在 `apps/legacy-web/ui-foundation.css`；旧 token 去重并合并为一个「旧层」块。
- 组件原地改样式：
  - Button、Input、Textarea、Badge、Card、Table、Dialog 系列；
  - controls 下 8 个控件；
  - feedback（确认框、通知、操作结果）；
  - 分页共享样式 `pagination.css`。
- 新增组件：InputGroup、Segmented、Switch、Checkbox、RadioCardGroup、Empty、Skeleton。
- 全部组件样式集中到 `components/ui/kit.css`（`@layer components`）；删除 `controls.css`、`--button-*`、未限定页面作用域的全局组件覆盖。
- 图标：两份 sprite 补齐设计稿 52 个图标、同义的 28 个旧图标改用设计稿画法，两份内容一致；`ui/` 内部不再用 lucide。
- 演示页 `ui-preview.html`：
  - 各组件各状态；
  - 预设 / 主色 / 材质切换；
  - 局部主题示例。
- 验证：
  - `theme.test.mjs`（派生、对比度、校验、默认值一致、静态样式规则）；
  - 新脚本 `verify_ui_kit.py`；
  - 37 个回归脚本基线对比与分诊。
- 设计稿复制到 `doc/design/console-v2/`；更新 `ui-guidelines.md` 与原生组件规范；legacy `index.html` 两个共享 CSS 的 `?v=`。

## Non-Goals

- 业务页面迁移、外壳与页头、通用业务组合组件、系统更新弹窗、主题设置页 UI、深色模式：分属子任务 2–7。
- 页面对旧层 token 的替换：本任务后，页面仍是旧颜色、旧字号，直到所属子任务迁移。
- 无业务引用的 `label`、`separator`、`tabs` 组件不改。
- 后端、网关、运行时桥接白名单、镜像构建不改。
- 页面使用新 token 的方式（CSS 变量还是 Tailwind 主题映射）留给子任务 2 首次落地时决定。

## Technical Overview

- 种子（主色、4 个功能色、材质、字号、间距单位、控件高、尺寸步长、圆角、阴影强度）经 `createTheme()` 纯函数派生出完整 token 集。
  - 默认主色与 4 个功能色直接用设计稿手调色组，保证默认主题与设计稿一致。
  - 其余颜色在 OKLCH 空间派生，并保证文字对比度 ≥ 4.5。
- 存储只放种子（`localStorage['flower2api.theme']`）。`initTheme()` 在 `createApp` 前读取并校验，有效就写到 `<html>` 内联变量；无效或抛错则什么都不写，由 CSS 默认值生效。
- 字号与控件高由 `ui-foundation.css` 中的 `calc(种子 + --ui-tier)` 派生，`--ui-tier` 由三档媒体查询设为 0/1/2。派生块同时挂在 `:root` 和 `[data-ui-theme]` 上，局部容器能独立重算。
- 组件样式在 `@layer components` 中只引用 `--ui-*` 新 token；业务传入的 Tailwind 类仍可覆盖。

## Context & Decisions

- 现状：
  - 4 套 token 并存（shadcn 变量、`controls.css`、`ui-foundation.css` 阅读尺寸、`--button-*`）；
  - 13 个脚本拿渲染结果与旧原型 `flower2api-concept.html` 逐项比对计算样式；
  - 页面 CSS 引用旧控件 token 63 处；最常用的按钮变体是 `outline`（84 处）。
- **【关键决定】过渡期旧 token 冻结，不跟新色板：页面仍用的 shadcn 变量、旧控件 token、阅读尺寸保持现值，只做去重。影响：本任务交付后，新组件（13px、紫色主按钮、填充无描边）会和旧页面文字（14px、旧色）并存；切换主题只改变组件和已迁移页面，页面要等子任务 2/4/6 迁移后才跟随主题。**
  - 理由：否则未迁移页面全部偏离旧原型，13 个原型对比脚本在页面迁移前就失去回归保护。
  - 这一条修订了父任务 design §1 原定的「shadcn 变量直接别名到新 token」，父任务 design 已同步。
- **【关键决定】新 token 一律带分类前缀（`--ui-color-*`、`--ui-font-size-*`、`--ui-radius-*`、`--ui-shadow-*` 等），与旧层扁平名（`--ui-accent`、`--ui-font-body`…）不冲突；父任务最终复核时按旧名 grep 清零。**
- **【关键决定】按钮旧变体名照常可用、外观换新：`outline` / `secondary` → 次要（浅灰填充、无描边），`ghost` → 文字，`destructive` → 浅红底红字；新增 `soft`、`destructive-ghost`。影响：现有约 120 处按钮无需改代码；没有页面级覆盖的按钮在本任务换新，带页面 CSS 覆盖（约 96 条按钮颜色规则）或模板颜色工具类（如账号页「添加账号」）的按钮，在所属页面迁移前仍是旧外观。**
- **【关键决定】派生色强制可读：主按钮文字在白字与深色字之间自动取对比度高者。影响：暮光橙等浅亮预设的主按钮会显示深色字，而不是设计稿惯用的白字。**
- **【关键决定】主题只存种子、不存派生变量，在 `main.ts` 挂载前应用，不改 `index.html`。影响：界面不会先以默认主题渲染；但模块脚本执行前浏览器可能先画一帧空白页底色（浅色下差别仅柔光材质约 4% 色相）。深色模式若要消除这一帧，由子任务 7 再评估。**
- **【重要限制】设计稿没画的部分由本任务按同一视觉语言定义：复选、空态、骨架、气泡、通知、确认框，「柔光」材质，5 个非默认预设的派生色。实现中途会停下来，把演示页截图交你目视确认，确认后才进入回归分诊。**
- **【重要限制】原型对比脚本里的基础组件采样（按钮、输入、选择、弹窗外壳、分页、标签）移出原型比对，改由 `verify_ui_kit.py` 断言 token；写死组件样式值的断言（如分页 #77648f）改为读取 token。页面级比对与业务断言不放宽。**
- 通知保持现有深色浮条形态，只换 token。控件高 40 → 38 / 32 只作用于组件，html 根字号仍为 14/15/16，Tailwind 的 rem 布局不变。
- 原生页通过已被引用、并已登记在白名单中的 `ui-foundation.css` 取值，不新增白名单条目；设计稿复制（而非移动）到 `doc/design/console-v2/`，research 副本保留。

## Risks

- **【交付风险】回归集有 37 个 Playwright 脚本，部分依赖本 worktree 外的 `.deploy/.../reference.json` 等产物，基线可能本来就跑不通。处理方式：基线阶段如实记录，交付时列出未能运行的脚本及原因，可能无法给出全量通过结论。**
- **【交付风险】`ui-foundation.css`、`pagination.css`、legacy sprite 三份文件由 Vue、内嵌任务页、独立 `/runtime/` 文档共用，改坏会同时影响原生页。处理方式：用 `verify_task_login_design`、`verify_shared_pagination` 覆盖。**
- 删除全局 `[data-slot=button]` 等覆盖后，个别页面可能依赖其布局效果。处理方式：分诊时改为带页面前缀的规则，暂留在页面 CSS。
- 旧层合并时可能取错生效值。处理方式：设置检查点 A，要求组件改样式前原型对比结果与基线一致，不一致即回退。

## Acceptance

- 演示页 1440px 下各组件各状态与设计稿取值一致（颜色、圆角 6/8/12/18、控件高 32/38/44、字号字重、阴影），由 `verify_ui_kit.py` 断言；设计稿未覆盖部分经你目视确认。
- 切换预设、自定义主色后所有组件跟随变化；局部容器主题不影响容器外。
- 刷新后首屏即为保存的主题；存储缺失、损坏、越界或抛错时回退默认，且无报错。
- 组件源码无写死颜色、圆角只用 token（单测校验）；现有组件签名与行为不变，`verify_ui_controls.py` 通过。
- 构建通过；键盘焦点可见；减少动效下无动画；两份 sprite md5 一致。
- 组件改样式前页面零视觉变化（检查点 A）；最终回归集与基线相比无新增失败。
- `ui-guidelines.md` 与原生组件规范已更新。

## Next Step

- 运行 `task.py start` 后执行 implement.md 第 0 步：在当前 HEAD 构建并跑 37 个回归脚本，记录基线。
