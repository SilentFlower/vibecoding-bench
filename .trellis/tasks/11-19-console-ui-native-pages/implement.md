# 执行计划 — 原生页视觉对齐

证据目录统一为 `.deploy/console-ui-revamp/native-pages/`（git 忽略）。每步完成后在本文件勾选并写实际结果。

## 步骤

- [x] **0. 基线与迁移前证据**
  - 复制子任务 5 的回归 runner 到证据目录，新增 `verify_native_pages_design` 槽位。
  - 基线复用子任务 5 的最终回归结果（之后产品代码未变），失败集合为 7 个已登记脚本。
  - 用合成夹具截迁移前截图，作为后续像素比对的基准：
    - `/tasks` 六个页签，以及 R4 所列原生弹窗；
    - `/environments`，以及环境抽屉五个分区；
    - 独立 `/runtime/#accounts`、`/runtime/#environments`；
    - 宽度 1440 与 390。
- [x] **1. 删除无效规则（不应有视觉变化）**
  - 删除对象：
    - `style.css` 的暗色终端底稿、topbar、hintbar、扫描线、`projects-*`；
    - `console.css`、`approved-design.css`、`work-design.css` 中被后续层完全覆盖或没有对应元素的规则。
  - 判定依据：选择器在模板、JS 字符串和 Vue 组件中都搜不到，或者同一属性已被后层覆盖。
  - 重拍第 0 步的全部截图，像素差必须为 0；有差异就恢复该条规则。**回滚点 A**
- [x] **2. 图标 sprite**
  - 两份 sprite 补 `i-todo`、`i-activity`，legacy 那份补 `i-sliders`。
  - 新增单测：两份 sprite 逐字节一致。
- [x] **3. token 化**
  - 先把 legacy CSS、`native-environment.css` 和本页 Vue 组件加入 `theme.test.mjs` 静态规则，并加上「无旧变量定义块」断言，确认测试失败。
  - 生成去重后的调色板及其 token 映射，存为 `palette.json`。
  - 按 design §1.2 修改：
    - 删除旧变量定义块，引用改为 `--ui-*`；
    - 颜色字面量、圆角、旧层字号、字体变量改为 token；
    - 删除多余的 `!important`；
    - 终端容器改取墨色 token。
  - 静态规则通过即完成本步。**回滚点 B**
- [x] **4. 任务与工程画面**（design §2）
  - 页头、页签（含计数与新图标）、区块头一行化。
  - 任务账号卡：外壳与头部、徽标、节点块、提示条映射、等分操作栏。
  - 登录草稿与加载状态、其余五个页签、原生控件与原生弹窗（含「继续运行」标题、去掉终端装饰）。
  - `RunDetails.vue`、`TaskProxyDialog.vue`、`TasksWorkspace.vue` 的样式块。
- [x] **5. 运行环境**（design §3）
  - `RuntimeEnvironments.vue` 换用 `Toolbar`、`Segmented`、`EntityCard` 系列与 `Badge`，新增 `preparationTone`。
  - 环境抽屉及分区组件的样式；`native-environment.css` 改为 `@layer components`，只取 token。
- [x] **6. 独立入口与静态资源**（design §1.3、§4）
  - `environments.css`、`environment-design.css` 做 token 化与清理。
  - 改动过的原生文件把 `?v=` 改为 `20261120-native-pages`。
  - 有文件被合并删除时，同步桥接白名单、两项桥接测试、`runtimeModule.ts:9` 和 `index.html`。
  - 删除 `extract_environment_styles.py`。
- [x] **7. 验证脚本**（design §6）
  - 新增 `verify_native_pages_design.py`。
  - 迁移 6 个对旧原型做比对的脚本。
  - 修好移交的 4 个失败。
- [x] **8. 规范**
  - `legacy-web/frontend/component-guidelines.md`：
    - 改写 Styling Patterns：删除「终端皮肤硬约束」和直角 reset，写入原生部件与组件库部件的对应表、提示条和页签计数；
    - 更正 `--border` / `--muted` 的冲突说明；
    - 改写环境页场景里 `.environment-page` 的视觉描述。
  - `web/frontend/ui-guidelines.md`：新增「第二版原生页」一节，写入定位契约、≤760 规则和验证入口；静态规则清单加入本页文件；Tests Required 写入新脚本。
- [x] **9. 全量验证与对照页**
  - 运行下方全部命令。
  - 生成 `index.html` 对照页，内容为设计稿与产品 1440 并排、390 截图、深层弹窗截图、迁移前后对比。

## 验证命令

```bash
node --check apps/legacy-web/app.js && node --check apps/legacy-web/projects.js && node --check apps/legacy-web/environments.js && node --check apps/legacy-web/ui-controls.js
cd apps/web && npm run build && node --experimental-strip-types --test tests/*.test.mjs
python3 deploy/flower2api/verify_native_pages_design.py
python3 .deploy/console-ui-revamp/native-pages/run_regression.py after      # 期望只剩 3 个已登记失败
cd services/gateway && cargo test runtime_bridge                             # 仅在白名单变动时
```

## 风险与回滚点

- **原生弹窗多、设计稿未画**：第 4 步每改一类弹窗，就跑对应行为脚本（`verify_task_account_config`、`verify_task_feedback`、`verify_runtime_settings_design`、`verify_project_workspace_design`、`verify_capture_workspace_design`、`verify_run_detail_design`）。
- **层叠顺序**：legacy CSS 不分层，会压过 `@layer components`。Teleport 进原生宿主的 Vue 控件可能被原生规则误伤，比如原生 `button` 的通用规则命中 `ProxyPicker` 或分页。第 7 步的部件一致性比对能发现这类问题；修复方式是收窄原生选择器，不给 Vue 组件加覆盖。
- **回滚点**：A（死规则清理后）、B（token 化后）。最终单次提交，必要时整体回退。

## 实际结果

- **基线**：复用子任务 5 的最终回归（之后产品代码未变），7 个已登记失败。迁移前截图由截图工具 `capture_states.py` 从 HEAD 导出副本截取，共 36 个状态、72 张。同一份代码重复截图逐像素一致；`#task-modal` 没有调用方，属于不可达状态。
- **第 1 步**：静态分析按模板、原生 JS 和 Vue 源码语料删除 365 条无效规则。像素比对发现 xterm 运行时才生成的类名被误判，补回 `.xterm-host .xterm-viewport`；其余状态零差异。
- **覆盖清理（第 3 步的一部分）**：任务页根元素总带 `.console-design` 与 `[data-theme=light]`，据此删除 876 条必然被覆盖的声明，72 张截图零差异。第二轮假设「`.work-console` 总在祖先链上」被像素比对否定（独立文档的环境页签会去掉这个类），只有 `[hidden]` 一条受影响，已改为对整份文档生效，该假设已停用。
- **token 化**：596 种颜色按「所在属性 + 明度 / 色相族」映射到语义 token（映射表 `palette-css.json`、`palette-vue.json`）。46 个旧变量定义块清零；圆角按部件角色取 4 个圆角 token；`!important` 从 76 处降到 41 处（剩余为隐藏原始控件、抽屉尺寸、减少动效与 `[hidden]`，另有工程子导航的 3 条颜色和字号）。原生 CSS 从 3,707 行降到 2,565 行；`native-environment.css` 从 305 行降到 184 行，并改为 `@layer components`。
- **区域重排中的修正**：
  - 原生页签 `scrollIntoView` 会纵向滚动整页，移动端应用栏因此被滚出视口。迁移前就存在，现改为只在托盘内横向滚动。
  - `approved-design.css` 有一组规则把 Vue `ProxyPicker` 改回旧外观，已删除，只保留弹层 `z-index`。新脚本比对宿主内外的计算样式，作为回归防线。
- **验证**：
  - 新增 `verify_native_pages_design.py`：56 项设计稿比对，白名单 2 项；部件一致性 10 项；6 个页签、环境列表与侧抽屉 5 个分区、11 个深层弹窗的颜色只取 token；主题跟随与独立入口默认主题；390；资源加载。
  - 迁移 6 个对旧原型做比对的脚本；修好子任务 4 移交的 4 个失败。
  - 依赖旧环境卡结构的 5 个脚本改为新定位。
  - 全量回归：主集合 38 个（含新脚本）只剩 `verify_forwarding`、`verify_management_polish`，集合外 26 个只剩 `verify_agy_request_records`，失败点与基线逐一相同（真实发行物 2、系统更新检查写入 1）。原生页 4 个已登记失败全部转为通过。最后一轮细调（终端标签、终端边框、独立入口搜索框）之后，又对 8 个相关脚本做了定向复跑，全部通过。
  - 构建、`node:test` 26/26、4 个原生 JS 的 `node --check` 通过；桥接白名单未变，没有新增或删除静态文件，不需要跑 Rust 测试。
  - 对照页 `.deploy/console-ui-revamp/native-pages/index.html`：设计稿与应用 1440 并排、主题跟随与独立入口，以及 36 个状态迁移前后 1440 / 390 对比。

## Check-All 修复（CHK-001 至 CHK-004，用户选择「修复全部」）

- **CHK-001**：
  - 任务账号加载状态改为 `work-strip`：读取中为 neutral，失败为 danger、`role=alert`，重试按钮靠右。
  - 11 个弹窗底栏改为满宽 `fill-subtle`、无上边线：贴底的 5 个直接改底色，内缩的 6 个按各自表单内边距用负外边距铺满。
  - design §2 的 390 区块头改为实际形态（搜索与主按钮同排，放不下换行）。
- **CHK-002**：删除 `.work-console .field > input { font: inherit }`，输入字号回到 13px（同 `.fui-input`）。
- **CHK-003**：
  - `verify_native_pages_design.py` 补齐 R4 全部 21 个弹窗，其中独立文档 4 个；新增脚本内的 `ContinueFixture` 与 `BindingFixture`。
  - 补输入、下拉、数字、选线控件的一致性比对，底栏断言，以及加载失败断言。
  - 删除无差异的白名单；等待动画时跳过无限循环动画（否则独立文档的在线圆点会卡住脚本）。
  - 扩充覆盖后又暴露两处问题，已修：独立入口登录弹窗 390 溢出（迁移前就存在，提示符改为窄屏可换行）；独立入口环境工作区的外壳阴影与标题未按弹窗规格。
- **CHK-004**：`!important` 从 41 处降到 16 处，剩余全部是登记的例外（xterm 底色、`.hidden` 与 `[hidden]`、减少动效一份、原始 select / 时间 input 的视觉隐藏）。
  - 删除重复的 `[hidden]` 4 条、重复的减少动效 2 组、与通用规则同值的声明 2 条。
  - 环境抽屉、运行详情、独立入口提示、空行与工程子导航改为靠选择器特异性。
  - design §1.2 与两份规范登记了例外清单。
- **修复后全量回归**（构建产物晚于全部改动）：
  - 主集合 38 个、集合外 26 个，已登记失败仍为 `verify_forwarding`、`verify_management_polish`、`verify_agy_request_records`，失败点与基线逐字相同；`verify_native_pages_design` 通过。
  - 另有 `verify_accounts_design`、`verify_node_password_ui` 在全量 4 并发时等待 Vue 下拉选项超时。两者不涉及原生页；单独重跑和 4 并发复跑均通过，判定为负载偶发。

## Check-All 重检修复（CHK-005、CHK-006，用户选择「修复全部」）

- **CHK-005**：第 1 步的死规则清理早于第 4 步删除模板装饰，扫描线、弹窗角框删掉后对应规则未跟着删。
  - 删除三份文件中无匹配元素的 16 个选择器，以及 `.brand` 的无效 `text-shadow` 和被覆盖的 body 渐变。
  - 删除旧变量清空后留下的空 `:root` 块和无规则的标题注释，文件头与节标题改为第二版描述。
  - 死规则工具重扫只剩 xterm 运行时类名误报；36 个状态 72 张截图与修复前逐像素一致。
- **CHK-006**：`legacy-web` 的 quality-guidelines、directory-structure、component-guidelines 中仍把终端皮肤、旧变量、无圆角写成现行约定，已改为第二版 token 约定，并删除已删元素与 `#theme-toggle` 的引用。
- **验证**：构建、`node:test` 26/26；`verify_native_pages_design` 及 7 个相关行为脚本通过；对照页改用最终截图重新生成。
