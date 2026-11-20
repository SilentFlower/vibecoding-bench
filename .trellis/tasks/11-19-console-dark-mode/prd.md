# 控制台深色模式

## Goal

在组件库全部走 token 的基础上加入深色主题与主题模式切换，深色外观以用户确认的「夜幕紫灰」深色稿为准。对应父任务 `../11-19-console-ui-revamp/prd.md` 的 R10。

## Background

- **token 覆盖现状**：组件库、外壳、全部已迁移 Vue 页与原生页的样式都只取 `--ui-*`（`apps/web/tests/theme.test.mjs` 静态校验）。全仓剩余的颜色字面量只有：
  - `apps/web/src/style.css` 的旧 shadcn 变量层（`--background/--foreground/--border/--muted-foreground…`，取值冻结为浅色），以及 `.approved-run-dialog`、`.resource-grid` 的写死颜色；
  - `apps/web/src/approved-design.css:2` 的 `html{color:#0e1726}`；
  - 仍引用旧变量的 Tailwind 类：`ui/tabs/TabsTrigger.vue`、`TabsList.vue`、`ui/separator/Separator.vue`、`NativeStageDetails.vue`、`runtime/RunDetails.vue`、`App.vue`。
- **主题运行时**（`apps/web/src/theme/`）：
  - 浏览器只保存种子 `localStorage['flower2api.theme']`（`version: 1`）；`main.ts` 在挂载前调用 `initTheme()`，`index.html` 没有内联脚本。
  - `createTheme(seed)` 的中性色是固定浅色常量（`tokens.ts` 的 `NEUTRALS`），主色组与功能色组按浅色规则派生。默认值同时写在 `apps/legacy-web/ui-foundation.css`，与派生结果逐项一致。
- **原生页**：
  - 任务与工程宿主写死 `data-theme='light'`（`TasksWorkspace.vue:84`），独立 `/runtime/` 文档同样写死（`apps/legacy-web/index.html:22`）；`style.css` 有 12 处 `[data-theme="light"]` 限定的规则。
  - 4 个验证脚本断言任务宿主固定 `data-theme=light`，其中 `verify_workspace_experience.py` 在系统深色下运行。
- **终端**：xterm 配色写死为旧终端皮肤（`apps/legacy-web/app.js:1595-1608`，底 `#0a0b09`、琥珀光标）。终端与代码块容器取 `--ui-color-ink`，其中文字取 `--ui-color-text-4`（`work-design.css:43,44,229,283,315,463`、`RunDetails.vue:134`），深色下会变暗。
- **其它**：
  - 图表只有调度详情的内联 SVG（`SchedulingDetails.vue`），已只取 token。
  - 开关滑块取 `--ui-color-surface`（`kit.css:172`），深色下会变成深色滑块。
- **已定稿的入口**：第二版设计稿侧栏底部已有「切换深色模式」图标，主题设置编辑面板已有「主题模式」分段（跟随系统 / 浅色 / 深色）。参考项目 codex-proxy-rs 同样默认跟随系统、侧栏按当前深浅直接切换、模式属于主题草稿。

## Requirements

- **R1 深色基准**：
  - 深色外观以用户确认的「夜幕紫灰」深色稿为准：页面底 `#0f1018`、卡片 `#171824`，中性色带紫灰偏向，与墨色同色相。
  - 草稿在 `research/design-dark/`：`mock.html?mode=dark#<画面>` 为深色，不带参数为第二版浅色；含第二版全部画面，另新增 `#terminal`（任务账号授权弹窗里的登录终端）与 `#palette`（取值、对比度、六个预设的派生结果）。评审对照页在 `.deploy/console-ui-revamp/dark-mode/draft/index.html`。
  - 实施时同步到 `doc/design/console-v2/`，成为深色的唯一视觉基准。
- **R2 主题模式**：
  - 三种模式：跟随系统、浅色、深色。选择保存在当前浏览器。没有保存值（包括全部现有用户升级后第一次打开）时为跟随系统。
  - 跟随系统时，系统切换深浅，控制台无需刷新即随之切换。
  - 刷新后保持所选模式，首帧即为正确的深浅，不先闪一下浅色。
- **R3 切换入口**：
  - 侧栏底部（含移动端抽屉）提供快捷切换：按当前实际深浅切到另一种，并保存为明确的浅色或深色。
  - 主题设置页「全局」加入模式选项：模式属于草稿，在画板中预览，「保存并应用」后生效，计入待应用数；恢复默认回到跟随系统。
- **R4 深色派生**：
  - 六个预设与自定义主色按同一规则自动调整为深色下可读的亮度：实色对卡片底 ≥ 3:1；按钮文字白字不足时改深色字，再不足继续提亮；主色文字 ≥ 5.5。
  - 功能色、柔光材质、阴影同样有深色派生。
- **R5 适配范围**：全部 Vue 页（含登录页、组件演示页）、外壳、原生页（任务与工程、运行环境）、弹窗、气泡、通知、终端（xterm）、图表在深色下取深色 token。
  - 独立 `/runtime/` 文档跟随所选模式，配色仍为默认主题、不应用自定义种子。
  - 终端两种模式都是墨色底，ANSI 配色统一取 token，替换旧终端皮肤。
- **R6 收尾**：样式中剩余的写死颜色与旧变量引用改为 token，全仓颜色字面量只出现在 token 定义处。

## Acceptance Criteria

- [ ] 深色下账号、账号编辑、请求、系统更新与进度、任务与工程（含深层弹窗与登录终端）、运行环境、主题设置、外壳与 390 移动端，与深色稿的计算样式一致；其余页面、弹窗、气泡的颜色只取深色 token（R1、R5）。
- [ ] 深色下正文对其实际底色的对比度 ≥ 4.5；六个预设与边界色在深色下按钮文字 ≥ 4.5、实色对卡片底 ≥ 3（R4）。
- [ ] 跟随系统时切换系统深浅，控制台、内嵌任务页与独立 `/runtime/` 文档随之切换；侧栏切换后刷新保持；首帧在脚本挂载前已是所选深浅；模式存储缺失或被篡改时按跟随系统处理（R2、R3、R5）。
- [ ] 主题设置页修改模式后，画板随之变化而控制台不变，待应用数加一；保存后生效，撤销草稿与恢复默认按约定回退（R3）。
- [ ] 浅色下既有验证全部通过（失败集合与基线相同）；浅色画面只在 design §5 登记的区域有变化（R5、R6）。
- [ ] 前端构建与单测通过，全仓样式无颜色字面量（token 定义处除外），规范与设计基准已同步（R1、R6）。

## Dependencies

依赖子任务 1–6 全部完成（已完成）；最后交付。

## Out of Scope

- 高对比度主题。
- 组件级 token 编辑。
- 独立 `/runtime/` 文档应用自定义种子（仍只用默认配色）。
