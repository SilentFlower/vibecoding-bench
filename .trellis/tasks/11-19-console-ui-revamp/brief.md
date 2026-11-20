# Brief — 控制台 UI 改版（第二版定稿落地）· 最终复核与关闭

## Goal

- 7 个子任务已全部完成。本轮做父任务的最终一致性复核：清掉过渡期遗留，跑全量 UI 回归和截图矩阵，然后关闭父任务。

## Scope

- 旧原型退役：
  - 删除 `doc/design/flower2api-concept.html`；
  - 退役 `audit_full_design.py`；
  - `verify_design_parity.py` 改用常量分组与页签。
- 旧层清零：
  - shadcn 变量与 `@theme` 色名映射、`--font-body/--font-mono`、阅读尺寸旧块（`--ui-font-body/small/...`、`--ui-control-height/...`）；
  - 剩余 7 处旧工具类；
  - 删除 3 个无引用组件（tabs、separator、label）；
  - 新增静态断言防回归。
- 图标与死代码：
  - 代理页两个文件的 lucide 图标改用 sprite，移除 `lucide-vue-next` 依赖；
  - 逐个复核后删除死类；
  - 删除验证脚本里早已失效的 `vibebench-theme` 写入：17 个直接删；`verify_management_ui` 改用真实的系统深浅；有意模拟升级用户的 `verify_workspace_experience` 保留。
- 规范：`ui-guidelines.md` 改为单一第二版基准，写入「旧层已删除」合同、根字号三档规则和 6 条第二版设计决定；复核 legacy-web 规范中的过渡期表述。
- 复核证据：
  - 69 个 UI 脚本的全量回归；
  - 浅色、深色改前改后逐像素比对；
  - 设计稿与产品浅色 / 深色 × 1440 / 390 的截图矩阵对照页；
  - 父 PRD 9 条验收逐条勾选。
- 最终提交，并把父任务目录（目前从未入库）纳入任务记录，关闭父任务。

## Non-Goals

- 合并到 `flower2api` 主线、发版和部署。分支目前比 `flower2api` 多 22 个提交、少 31 个提交，需要另行决定。
- 部署后在深色下核对真实 Claude CLI 终端输出，由发布流程承接。
- 工作区里 8 个旧任务的归档移动（58 个删除加对应新增）保持原样，不随本次提交。
- 需要真实 Chrome 配置或独立管理栈的 `*_browser` 类脚本，不属于本地 UI 回归。
- 任何业务行为、API 或交互的变化。

## Technical Overview

- **根字号**：删除阅读尺寸旧块后，`html` 根字号改为 `calc(14px + var(--ui-tier) * 1px)`，保持 14/15/16px 三档（断点同为 1920 / 2560）。Tailwind 的间距按 rem 计，所以这里必须与原值完全一致。
- **Tailwind 字体映射**：`@theme` 只保留 Tailwind 自己的 `--font-sans/--font-mono`，改指 `--ui-font-family(-mono)`。全局边框和焦点色由 `@apply border-border outline-ring/50` 改为直接取 token，取值不变。
- **静态断言**：`theme.test.mjs` 断言样式与组件中不再出现旧层变量名、shadcn 色名工具类和 `lucide-vue-next` 导入。
- **回归 runner**：沿用深色任务的工具，去掉 `audit_full_design`，补上漏跑的 5 个第二版设计脚本（`verify_account_page_design`、`verify_nodes_settings_design`、`verify_records_pages_design`、`verify_ui_kit`、`verify_ui_shell`）。

## Context & Decisions

- 盘点结果（2026-11-20）：
  - 颜色和圆角字面量已清零；
  - `!important` 从 136 处降到 23 处，都是规范登记的例外；
  - 遗留只剩上述旧原型、旧层、2 个 lucide 文件和约 50 个疑似死类（含 Vue 过渡类、xterm、拼接类名等误报）。
- **【关键决定】`audit_full_design.py` 直接退役，不改写。** 它对 5 个已迁移页面与旧原型比对，现在比对项全部不同，实际只剩「无报错、无横向滚动」两条断言。这 5 个页面已有对应的第二版设计脚本。
- **【关键决定】根字号固定为三档，不接到主题字号。** 接到主题种子会让 Tailwind 的 rem 间距随用户在主题设置里调整的基础字号一起缩放，改变现有布局行为。
- **【关键决定】浅色只在代理相关图标处有可见变化：** 检测中的转圈图标由 lucide `LoaderCircle` 换成项目惯例的 sprite `RefreshCw`；`ProxyPicker` 的地球、下拉箭头、对勾换成 sprite 字形（描边 2 → 1.8），后者为实施中补登记。运行详情弹窗标题改写为 `calc(var(--ui-font-size-heading) - 2px)`，取值不变（设计稿未画该弹窗）。
- 设计、规范和父 PRD 已约定：旧原型和旧层在最终复核时删除，lucide 在迁移时改用 sprite。本轮是执行既有决定，不新增产品取舍。

## Risks

- **【交付风险】删除 `@theme` 色名映射后，仍在使用的 Tailwind 工具类会静默失效（不报错，只是不生成样式）。** 靠静态断言加浅色、深色逐像素比对兜底。
- 死类可能通过字符串拼接引用。只删确认无字面量、无拼接前缀的类，有疑问的保留并在实际结果中列出。
- 全量回归原有 3 个已登记失败（`verify_forwarding` 缺参数、`verify_management_polish` 系统更新写入断言、`verify_agy_request_records` 缺参数），期望不变；出现新失败则逐个判定，不放宽业务断言。

## Acceptance

- `flower2api-concept.html` 与 `audit_full_design.py` 已删除，仓库内（任务归档除外）不再引用旧原型。
- 旧层变量名、shadcn 色名工具类、`lucide-vue-next` 在代码中清零，`theme.test.mjs` 断言通过。`lucide-vue-next` 已从依赖中移除，构建通过。
- 69 个 UI 脚本的全量回归只剩 3 个基线已登记失败，原因不变。
- 浅色、深色改前改后逐像素比对，差异只出现在登记位置。截图矩阵对照页覆盖全部画面的浅色 / 深色 × 1440 / 390。
- `ui-guidelines.md` 为单一第二版基准，含 6 条设计决定和「旧层已删除」合同。
- 父 PRD 9 条验收全部勾选并有证据。父任务目录随任务记录提交，父任务关闭（`completed` + `closed`）。

## Next Step

- 启动父任务后，复制回归和截图工具到 `.deploy/console-ui-revamp/final-review/`，截取浅色、深色改前基线。
