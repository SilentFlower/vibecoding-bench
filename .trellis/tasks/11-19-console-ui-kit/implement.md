# 执行计划：组件库与主题运行时

设计见 `design.md`（下文 §n 指其章节）。本任务只动 `apps/web`、`apps/legacy-web` 的前端资源、`deploy/flower2api` 的验证脚本、`doc/design/` 与规范文档；不改后端、网关、镜像构建。

证据目录：`.deploy/console-ui-revamp/ui-kit/`（git 忽略）。

## 回归集

以下 37 个脚本触及基础组件选择器、原型比对或写死的样式值，改动前后各跑一次：

```
audit_environment_proxy_design audit_full_design audit_token_task_design
verify_account_filters_ui verify_accounts_design verify_agy_accounts_ui verify_cluster_draft_ui
verify_console_ui verify_datetime_boundary verify_design_parity verify_diagnostic_alignment
verify_dialog_typography verify_exact_design verify_execution_node_visibility verify_followup_browser
verify_forwarding verify_frontend_navigation verify_interaction_parity verify_management_polish
verify_management_ui verify_page_sizes verify_prime_history_ui verify_proxy_design
verify_quota_completion_browser verify_request_detail_design verify_run_detail_design
verify_scheduling_preferences verify_shared_pagination verify_task_account_config verify_task_feedback
verify_task_feedback_styles verify_task_login_design verify_ui_controls verify_ui_refinements
verify_update_design verify_viewport_interactions verify_workspace_stability
```

- 除 `verify_ui_controls`（用 dev server，`--url http://127.0.0.1:4187/ui-preview.html`）外，都依赖 `apps/web/dist`，从仓库根执行 `python3 deploy/flower2api/<名>.py`。
- 结果写入证据目录的 `regression-<阶段>.json`（脚本名 → 通过 / 失败 + 摘要）。

## 步骤

### 0. 基线

- [x] 确认 `apps/web/node_modules` 可用，`npm --prefix apps/web run build` 在当前 HEAD 通过。
- [x] 跑回归集，存为 `regression-baseline.json`。
  - 基线已失败的脚本（如缺少本 worktree 外的 `.deploy/.../reference.json`）记录原因，不算本任务引入；能在本 worktree 补齐前置产物的先补齐再记基线。
- [x] 跑 `node --experimental-strip-types --test apps/web/tests/*.test.mjs`，记录基线。

### 1. 设计基准

- [x] 复制 `../11-19-console-ui-revamp/research/design-v2/{mock.html,mock.css,icons.js}` 到 `doc/design/console-v2/`，`mock.css` 字体路径改为 `../../../apps/web/src/assets/fonts/…`。
- [x] 浏览器打开 `doc/design/console-v2/mock.html#accounts` 确认字体与图标正常。

### 2. 主题核心（先写测试）

- [x] `apps/web/tests/theme.test.mjs`：默认值与 CSS 一致（先跳过，第 3 步解除）、对比度保证、尺寸 / 圆角派生与钳制、`parseThemeSeed` 失败矩阵、静态样式规则（第 6 步后启用）。
- [x] `apps/web/src/theme/color.ts`、`tokens.ts`（§2.4、§3.1）。派生参数以 5 组手调色校准，校准结果写在测试输出中备查。
- [x] 验证：`node --experimental-strip-types --test apps/web/tests/theme.test.mjs`。

### 3. Token CSS 与旧层整理

- [x] `ui-foundation.css`：新增 §2.2 默认值、`--ui-tier` 三档媒体查询、`:root, [data-ui-theme]` 派生块；原阅读尺寸保持不变。
- [x] `style.css`：
  - shadcn 变量合并为一个 `:root` 块，取当前层叠后的生效值（含 `approved-design.css:4` 的覆盖）。
  - 迁入 `controls.css:2-15` 的旧控件 token。
  - 全局滚动条改用新 token。
  - 标注「旧层：页面迁移后删除」。
- [x] 删除 `approved-design.css:4` 与 `style.css` 中被合并的重复 `:root` 块。
- [x] 解除默认值一致性测试的跳过。
- [x] **检查点 A**：
  - 构建通过，单测通过。
  - 回归集中原型对比类脚本（13 个 + `verify_interaction_parity`）与基线一致：此时组件尚未改样式，页面必须零视觉变化。

### 4. 主题运行时

- [x] `theme/runtime.ts`、`theme/index.ts`（§3.2–3.3）。
- [x] `main.ts`、`previews/ui-preview.ts` 在 `createApp` 前调用 `initTheme()`。
- [x] 验证：单测覆盖 `readStoredTheme` 的缺失 / 损坏 / 抛错，构建通过。

### 5. 图标

- [x] 逐个比对 `icons.js` 与 Vue sprite 的符号（§6）；同形保留，缺的新增（含 `chevron-down`、`chevron-left`）。
- [x] 两份 sprite 写成同一内容（含 `i-server`）。
- [x] `ui/icon/index.ts` 增加新图标导出。
- [x] 验证：两文件 md5 一致；构建通过。

### 6. 组件

- [x] 新建 `components/ui/kit.css`（`@layer components`），在 `main.ts`、`ui-preview.ts` 中紧跟 `style.css` 引入。
- [x] 迁移 `controls.css` 规则后删除该文件，并移除各控件中的引用。
- [x] 按 §5 清单逐个改写：Button → Input / Textarea / InputGroup → controls（含 Pagination 与 `legacy-web/pagination.css`）→ Badge → Card → Table → Dialog → feedback（含 `ui-foundation.css` 的 `.fui-*`）。
- [x] 新增：Segmented、Switch、Checkbox、RadioCardGroup、Empty、Skeleton。
- [x] `ui/` 内部 lucide 图标换 sprite。
- [x] 删除 `style.css:534-570` 的全局按钮覆盖与 `--button-*`，以及其它未限定页面作用域的 `[data-slot=…]` / `.fui-*` 全局规则；带页面前缀的覆盖不动。
- [x] legacy `index.html` 中 `ui-foundation.css`、`pagination.css` 的 `?v=` 更新。
- [x] 启用静态样式规则测试。
- [x] 验证：单测、构建通过；`grep -rnE "lucide-vue-next" apps/web/src/components/ui` 无结果。

### 7. 演示页

- [x] 重写 `previews/UiPreview.vue`（可拆成 `previews/` 下若干分节组件）：
  - 保留 `verify_ui_controls.py` 依赖的现有示例及其标签。
  - 新增各组件的默认 / 选中 / 禁用 / 加载示例；悬停与焦点保持可交互。
  - 顶部工具条：6 个预设、自定义主色、表面材质、保存 / 恢复默认（走真实 `writeStoredTheme`）。
  - 一个应用了不同预设的局部主题示例区。
- [x] 验证：dev server 下手动走查 1440 / 390；`verify_ui_controls.py` 通过。

### 8. 新验证脚本

- [x] `deploy/flower2api/verify_ui_kit.py`，覆盖 §7 第 2 层全部检查。
  - 设计稿取值（如主按钮 rgb(108,84,180)、高 38、圆角 6、13px / 700）只在本脚本中作为默认主题基准写一次。
  - 截图存证据目录。
- [x] 验证：脚本通过，零控制台错误、零业务请求。

### 9. 用户目视确认（评审关口）

- [x] 把演示页 1440 / 390 截图交用户确认：
  - 设计稿未覆盖的组件（复选、空态、骨架、气泡、通知、确认框）；
  - 柔光材质；
  - 5 个派生预设；
  - 暮光橙等预设的主按钮文字颜色。
- [x] 按反馈调整后重跑第 8 步。用户确认前不进入第 10 步。

### 10. 回归集复跑与分诊

- [x] 重新构建，跑回归集，存为 `regression-after.json`，与基线逐项比较，新增失败按下列规则处理：
  - 原型对比中的基础组件采样：移出原型比对，在脚本中注明「已迁至 `verify_ui_kit.py`」。页面级采样不动。
  - 写死组件样式值的断言：改为读取 token 实际值后比较，例如 `verify_shared_pagination.py:14-43`、`verify_interaction_parity.py` 的按钮属性、`verify_diagnostic_alignment.py:14-19`。
  - 布局受组件尺寸变化影响（如控件高 40 → 38）：确认属于预期后更新期望值，并在脚本中注明来源。
  - 业务行为失败：修代码，不放宽断言。
- [x] 全部新增失败处理完后再跑一次，直到与基线相比没有新增失败。

### 11. 规范与文档

- [x] `.trellis/spec/web/frontend/ui-guidelines.md`：
  - 视觉 token 节改为新来源与新取值，说明旧层及其退役方式。
  - 设计基准改为两套并存。
  - Button 默认色（`:257`）、分页当前页色（`:330`）、输入焦点色（`:307`）改为 token 描述。
  - 新组件签名。
  - 测试命令补 `theme.test.mjs` 与 `verify_ui_kit.py`。
- [x] `.trellis/spec/legacy-web/frontend/component-guidelines.md`：原生页可直接使用的 `--ui-color-*` 等新 token、sprite 同步要求。

## 完成前验证（全部通过才算完成）

```bash
node --experimental-strip-types --test apps/web/tests/*.test.mjs
npm --prefix apps/web run build
npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187 --strictPort   # 后台运行
python3 deploy/flower2api/verify_ui_controls.py --url http://127.0.0.1:4187/ui-preview.html
python3 deploy/flower2api/verify_ui_kit.py --url http://127.0.0.1:4187/ui-preview.html
md5sum apps/web/src/assets/approved-icons.svg apps/legacy-web/approved-icons.svg   # 两值相同
# 回归集：与 regression-baseline.json 相比无新增失败
```

## 风险与回退点

| 风险 | 位置 | 应对 |
| --- | --- | --- |
| 共享文件改坏原生独立文档 | `ui-foundation.css`、`pagination.css`、legacy sprite | 第 6 步后用 `verify_task_login_design`、`verify_shared_pagination` 覆盖 `/runtime/` 与内嵌任务页；必要时单独回退这三个文件 |
| 旧层合并时取错生效值，导致页面变色 | `style.css` 旧层块 | 检查点 A 要求原型对比结果与基线一致，不一致即回退第 3 步 |
| 删除全局覆盖后，页面依赖其布局效果 | `style.css:534-570` 等 | 回归集分诊；页面确需的布局规则改写为带页面前缀的规则，暂留页面 CSS 并随页面迁移删除 |
| 回归集耗时长或前置产物缺失 | 第 0、10 步 | 基线阶段记录无法运行的脚本及原因，交付时如实列出 |

回退：各步骤文件范围互不重叠，可按步骤回退对应文件。整体回退 = 撤销本任务全部改动；旧层取值未变，页面恢复原状。
