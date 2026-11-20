# 执行计划：主题设置页

按 design.md 执行，每步完成后勾选。只在 Push 阶段一次性提交。

## 环境

- Python：`/tmp/uikit-venv/bin/python`；运行验证脚本时设 `PYTHONPATH=services/orchestrator`。
- Dev server：`npm --prefix apps/web run dev -- --host 127.0.0.1 --port 4187`（未运行则启动）。
- 证据目录：`.deploy/console-ui-revamp/theme-settings/`（git 忽略）。回归运行器从 `../pages-acceptance/run_regression.py` 复制，脚本清单加入 `verify_theme_settings`。

## 步骤

- [x] **0. 基线**
  - 记录 HEAD。
  - 回归集 36 个与集合外 26 个各跑一次，存为 `regression-before.json`。预期只有已登记的 7 个既有失败。
  - 实际：HEAD `a04759be` 与子任务 4 验收最后一次回归（`1273c207`）之间只有任务记录提交、产品代码相同，直接复用 `../pages-acceptance/regression-*-after.json` 作为基线，失败恰为登记的 7 个。
- [x] **1. 编辑器纯函数**（design §3）
  - 写 `theme/editor.ts` 并从 `theme/index.ts` 导出。
  - 在 `tests/theme.test.mjs` 补用例。
  - 运行 `node --experimental-strip-types --test apps/web/tests/*.test.mjs`，确认通过。
- [x] **2. 路由与入口**（design §1）
  - 改 `router.ts`、`AppNavigation.vue`、`Dashboard.vue` 的 `titles`。
  - 改网关 `router.rs` 的 SPA 列表与测试。
  - 运行 `cargo test --manifest-path services/gateway/Cargo.toml frontend_routes`。
- [x] **3. 页面与编辑面板**（design §2、§3）
  - 写 `ThemeSettings.vue` 与 `theme-settings.css`：页头、预设、材质、三个分类字段、「已修改」与单项恢复、校验、保存。
- [x] **4. 预览画板**（design §4）
  - 写 `ThemePreview.vue`：iframe 注入、缩放与平移、只读。
  - `Dashboard.vue` 加预览标记，画板内跳过自动检查更新。
- [x] **5. 离开保护**（design §5）
  - 站内导航用确认框，刷新与关闭用 `beforeunload`。
- [x] **6. 静态检查与构建**
  - `theme.test.mjs` 静态规则加入新文件。
  - 运行 `npm --prefix apps/web run build`，确认通过。
  - grep 新文件，没有十六进制色值和圆角字面量。
- [x] **7. 浏览器验证**（design §6）
  - 写 `verify_theme_settings.py`，连续通过两次。
  - `verify_ui_shell.py` 加入「主题设置」后通过。
  - 截 1440 与 390，并与 `mock.html#theme` 生成对照页。
  - 实际：`verify_theme_settings.py` 单独连续通过两次，回归里再通过一次；21 组计算样式比对无差异，零控制台错误。对照页 `.deploy/console-ui-revamp/theme-settings/index.html`。
- [x] **8. 全量复核**
  - 构建、`node:test`、网关路由测试。
  - 回归 36 + 26 个与基线逐项对照：没有新增失败，7 个既有失败的失败点不变。负载敏感的脚本单独重跑。
  - 实际：
    - 构建、`node:test` 24/24、网关路由测试均通过。
    - 回归集 37 个（含新脚本）、集合外 26 个：失败恰为登记的 7 个，失败点与基线逐一相同。
    - 4 个脚本并行时偶发失败，失败点都是时序断言，与本页无关：`verify_accounts_design`（滚动条淡出 2 秒超时）、`verify_management_ui`（采集开关确认后状态）、`verify_proxy_design`（弹窗关闭计数）、`verify_tokens_design`（元素重渲染）。串行重跑各连续两次通过。
    - `verify_ui_shell`、`verify_ui_kit`、`verify_ui_controls` 和三个设计稿比对脚本串行全部通过。
- [x] **9. 规范**
  - `ui-guidelines.md` 写入主题设置页合同（草稿语义、预览 iframe 与预览标记、离开保护），补测试清单，更新侧栏说明 `:187`。

## 风险与回滚点

- **iframe 注入时机**：如果画板偶尔显示已保存主题而不是草稿，检查 `load` 事件与 iframe 内路由守卫的先后顺序。必要时在注入后再监听 iframe 根的 `data-ui-theme` 变化补注入，并在验证里加反复切换的断言。
- **画板内请求**：预览标记只跳过自动检查更新。如果发现其它写请求（验证脚本记录 iframe 发出的非 GET 请求），登记后再处理，不扩大到无关业务。
- **回滚**：未提交前按文件 `git restore`，新文件直接删除。
