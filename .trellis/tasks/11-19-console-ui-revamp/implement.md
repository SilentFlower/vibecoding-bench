# 执行计划（父任务）

父任务本身不直接改代码，负责子任务顺序、跨子任务的交接条件和最终复核。各子任务有自己的 `prd.md` / `design.md` / `implement.md`，开工前各自走规划评审。最终复核是父任务唯一的直接改动，细节见 design §8。

## 顺序

```
1 组件库与主题运行时
 ├─> 2 外壳与通用业务组件
 │    ├─> 3 系统更新弹窗（前端部分）
 │    ├─> 4 Vue 业务页迁移（可按页分批）
 │    ├─> 5 主题设置页
 │    └─> 6 原生页对齐
 └─> 3 系统更新步骤记录（后端部分，可与 1、2 并行）
1–6 全部完成 ─> 7 深色模式（先出深色稿，经用户确认后实施）
```

- 子任务 2 完成后，3、4、5、6 互不依赖，可以按优先级依次或并行推进。
- 子任务 4 按页面分批提交：账号 → 请求 / 代理 / 令牌 / 会话封禁 → 节点 / 设置 / 移动端。

## 每个子任务的交接条件

7 个子任务均已按下列条件完成并关闭（各自的 `implement.md` 实际结果有证据）。

- [x] 该子任务验收条件全部勾选，附 1440×900 与 390×844 截图对照设计稿。
- [x] `cd apps/web && npm run build`（即 `vue-tsc -b && vite build`）通过。
- [x] 受影响的 `deploy/flower2api/verify_*` / `audit_*` 脚本已按新视觉更新期望值并通过；业务行为相关断言不放宽。
- [x] 本子任务范围内的规范（`ui-guidelines.md`、原生组件规范）与设计基准已同步。
- [x] 新增颜色、圆角全部来自 token（对改动文件 grep 十六进制色值与 `border-radius` 字面量）。

## 最终复核（子任务 1–7 完成后）

证据目录 `.deploy/console-ui-revamp/final-review/`（git 忽略）。每步完成后勾选并写实际结果。

- [x] **0. 基线**
  - 复制深色任务的回归 runner 和截图工具（`run_regression.py`、`capture_mock.py`、`capture_vue.py`、`capture_states.py`、`pixel_diff.py`）到证据目录。
  - runner 去掉 `audit_full_design`，加入 5 个第二版设计脚本。
  - 用当前 HEAD 导出构建，截 Vue 主要页面与原生 36 个状态的浅色、深色改前图。
- [x] **1. 旧原型退役**（design §8.1）
  - 删除 `flower2api-concept.html` 与 `audit_full_design.py`。
  - `verify_design_parity.py` 改用常量分组与页签。
- [x] **2. 旧层清零**（design §8.2）
  - 先在 `theme.test.mjs` 写静态断言并确认失败。
  - 清理 `style.css`、`ui-foundation.css` 旧层块、`approved-design.css`、`App.vue`、`NativeStageDetails.vue`、`.approved-run-dialog`。
  - 删除 tabs / separator / label 三个无引用组件。
  - 断言通过即完成。**回滚点 A**
- [x] **3. 图标与死代码**（design §8.3）
  - lucide 改用 sprite，移除依赖。
  - 逐个复核疑似死类后删除，同步原生 `?v=`。
  - 删除 20 个脚本中的 `vibebench-theme` 写入。
- [x] **4. 规范**（design §8.4）
  - 改 `ui-guidelines.md`（单一基准、旧层合同、根字号、6 条决定、Tests Required）。
  - 复核 legacy-web 规范中的过渡期表述。
- [x] **5. 全量验证与截图矩阵**（design §8.5）
  - 运行下方全部命令。
  - 浅色、深色改前改后逐像素比对，差异只在登记位置。
  - 生成设计稿与产品浅色 / 深色 × 1440 / 390 的对照页。
  - 父 PRD 验收逐条对应证据后勾选。

## 验证命令

```bash
node --check apps/legacy-web/app.js && node --check apps/legacy-web/projects.js && node --check apps/legacy-web/environments.js && node --check apps/legacy-web/ui-controls.js
cd apps/web && npm run build && node --experimental-strip-types --test tests/*.test.mjs
python3 .deploy/console-ui-revamp/final-review/run_regression.py after          # 主集合
python3 .deploy/console-ui-revamp/final-review/run_regression.py after-extra --extra
# 期望：69 个脚本只剩 3 个基线已登记失败（verify_forwarding、verify_management_polish、verify_agy_request_records），原因不变
```

不新增静态文件，桥接白名单不变，不需要跑 `cargo test runtime_bridge`。

## 风险与回滚点

- **删除 `@theme` 映射后 Tailwind 工具类静默失效**：已删除的色名工具类不会报错，只是不生成。由第 2 步的静态断言兜底，再用浅色、深色逐像素比对确认。
- **根字号改写**：rem 基准一旦变化，Tailwind 间距会整体位移。逐像素比对覆盖三种宽度（1440 / 1920 / 2560 抽查）。
- **死类误删**：拼接类名查不到字面量。只删确认标准下的死类，有疑问的保留并在实际结果中列出。
- **回滚**：最终复核为单次提交，必要时整体回退，不影响 7 个子任务的提交。

## 回滚

每个子任务独立提交、独立发版；出问题按子任务回退其提交。子任务 1 改动 token 来源，回退时需连同依赖它的后续子任务一并回退。

## 实际结果（最终复核）

- **0 基线**：
  - 产品代码与 HEAD 一致，用当前构建截取改前图：Vue 10 页、原生 36 个状态，浅色、深色各 1440 / 390，共 184 张。全部稳定，无页面错误。
  - 另用 `probe_styles.py` 采样 72 项改前计算样式：三档根字号、body 字体 / 颜色 / 背景、默认描边与轮廓色、code / kbd / pre / `.font-mono` 字体栈。
- **1 旧原型退役**：
  - 已删除 `flower2api-concept.html` 与 `audit_full_design.py`。
  - `verify_design_parity.py` 改用常量后通过。
  - 旧原型的剩余引用只在任务历史记录里。
- **2 旧层清零**：
  - 新增静态断言，先确认失败，再清理到通过。命中项与盘点一致；`tokens.ts` 的 `fill-muted` 是 token 键名，规则中去掉 `fill/stroke` 前缀消除误报。
  - 删除三个无引用组件。`git rm` 写入暂存区后已撤回，提交前暂存区保持为空。
  - `@custom-variant dark` 一并删除。
  - 探针 72 项改前改后逐项一致，产物中无旧名残留。**回滚点 A**
- **3 图标与死代码**：
  - **lucide**：`Proxies.vue` 两处 `LoaderCircle`（状态徽标与检测按钮）改为 `RefreshCw` 加 `fui-spinning`，`ProxyPicker.vue` 三个图标改从 sprite 导入，`npm uninstall` 只移除 `lucide-vue-next` 一项。
  - **死类**：删除 20 个死类，共 100 个选择器 / 规则，涉及 6 个文件。按选择器粒度删除，`:is()` 列表只摘死项。改前改后结构比对，结果恰好等于去掉死选择器。工具初版把规则前的注释算进选择器，误删了注释，已恢复文件、修正工具后重做。
  - 原生 6 份样式的 `?v=` 改为 `20261122-final-review`。
  - **废键**：17 个脚本删除 `vibebench-theme` 写入；`verify_management_ui` 改用 `color_scheme=theme`；`verify_workspace_experience` 保留（有意模拟升级用户）。
- **4 规范**：
  - `ui-guidelines.md`：
    - 单一第二版基准；
    - 新增「第二版设计决定」6 条；
    - 「旧层已删除」合同含错误与正确示例；
    - 根字号写为 `--ui-tier` 三档；
    - 运行详情标题改为 `calc`；
    - 删除失效的 `--ui-font`、`--body-font`、Tailwind `--muted` 表述；
    - 旧原型脚本已全部退役；
    - Tests Required 补充静态断言。
  - `frontend-guidelines.md`：失效的 vm2api 绿色方案与 `vibebench-theme` 条目改为指向现行合同。
  - legacy-web 规范复核后没有失效表述。
- **5 全量验证**：
  - `node --check` 4 个原生脚本、构建、前端单测 33 / 33 均通过。
  - **全量回归**：69 个脚本（主集合 43 + 集合外 26）。失败恰为基线已登记的 3 个（`verify_forwarding`、`verify_management_polish`、`verify_agy_request_records`），末行错误与深色任务基线逐字相同。
  - **新纳入的 `verify_nodes_settings_design`** 首轮在 4 路并发下超时。原因是脚本自身的竞态：先 `count()` 再用等待式 `inner_text()`，弹窗在两次调用之间移除就会等满 30 秒。改为不等待的 `all_inner_texts()`，断言不变，之后单独连跑 3 次、经 runner 补跑 1 次都通过。
  - **逐像素比对**：Vue 40 张零差异；原生 144 张中只有 `dlg-add-account`、`dlg-task-proxy` 各两种宽度 × 两种深浅共 8 张有差异（140–155 像素，高 14px），即 `ProxyPicker` 的地球和下拉箭头换成 sprite 字形，属于已登记变化。
  - 定向截图确认代理检测中的两个图标都是 sprite `i-refresh` 加 `fui-spinning`（浅色、深色）。
  - **对照页**：`.deploy/console-ui-revamp/final-review/index.html`，233 张截图，包括：
    - 12 个画面 × 设计稿浅色 / 深色 × 产品浅色 / 深色 × 1440 / 390；
    - 移动端设计稿；
    - 账号编辑、更新进度、授权终端的脚本证据；
    - 原生 36 个状态；
    - 改前改后差异与登记变化截图。
