# 设计：子任务 4 整体验收

本任务的三个子任务已交付页面迁移。整体验收只做跨批次复核和 4 个既有失败脚本的修复，不重做页面。

## 1. 边界

- **脚本**：只改 R-A1 的 4 个脚本（`deploy/flower2api/verify_management_ui.py`、`verify_page_sizes.py`、`verify_ui_refinements.py`、`verify_cluster_request_ui.py`）。其它脚本只运行，不改。
- **产品代码**：默认不改。只有当 4 个脚本跑通后，暴露出本任务七个页面上的真实问题时才修，修复限于所属页面及其样式文件。若问题落在本任务页面以外，或需要产品取舍，先登记再询问，不在本次自行扩大。
- **已关闭子任务**：不 reopen，不回改它们的文档与 `task.json`。
- **父任务目录**：`11-19-console-ui-revamp/` 不提交，不改。

## 2. 脚本修复原则

逐个脚本处理：先修第一个失败点，再运行，直到全部断言跑通。每处改动都要能指出依据。

| 失败类型 | 处理 | 依据 |
| --- | --- | --- |
| 期望过时：产品合同已改，脚本没跟上 | 按现合同改断言，保留原来的验证意图 | 规范条款或引入变化的提交 |
| 夹具漂移：夹具数据与断言的数量对不上 | 从夹具实际数据算出期望值，不写死新数字 | 夹具源码 |
| 结构变化：类名或层级随迁移改变 | 改用稳定定位（role、label、规范登记的类名契约） | `ui-guidelines.md` 类名契约 |
| 真实问题：产品行为不符合现合同 | 修产品代码，脚本断言不动 | 规范条款 |

已知的 3 处依据：

- `verify_management_ui` L475：`frontend-guidelines.md`「请求账号保留当前名称和邮箱」条规定，列表只显示单行名称，资料气泡提供完整名称和邮箱。改为打开该行资料气泡，断言其中有 `primary@example.test`，详情页标题下的邮箱照旧检查。
- `verify_ui_refinements` L61：`Accounts.vue` 的 `generateOAuthUrl` 按多平台改造总是带 `platform`（新建时没有 `account_id`，序列化时会省掉）。期望体改为 `{proxy_id, proxy_revision, platform}`，直连场景同理。
- `verify_cluster_request_ui` L76：`ExecutionNodeBadge` 精简形态已不再有 `.execution-node-heading > span`。改为对徽标的可见文本断言「默认本机」，`code` 的 `local` 断言保留。

`verify_page_sizes` L38 的原因在执行时核对夹具账号总数和默认页大小后确定。

断言放宽的判断标准：改动前后，被检查的业务事实（数量、提交体字段、文本、零写入）必须相同或更严。只要有一条变弱，就按「真实问题」处理。

## 3. 全量复核

- **回归运行器**：从 `.deploy/console-ui-revamp/nodes-settings/run_regression.py` 复制到 `.deploy/console-ui-revamp/pages-acceptance/`，输出指向该目录（git 忽略）。
- **基线**：沿用 `nodes-settings/regression-after.json` 与 `regression-extra-after.json`（HEAD `2afbe5b1` 的业务代码与当前一致）。
- **期望结果**：集合内 36 个、集合外 26 个，失败只剩 7 个已登记脚本，且失败点不变。负载敏感脚本（`verify_console_ui`、`verify_prime_history_ui`、`verify_interaction_parity`）并行失败时单独重跑两次。
- **其它检查**：
  - `npm --prefix apps/web run build`。
  - `node --experimental-strip-types --test apps/web/tests/*.test.mjs`。
  - 三个设计稿比对脚本、`verify_ui_kit.py`、`verify_ui_shell.py`。

## 4. 截图矩阵

- **应用侧**：取三个设计稿比对脚本在最终提交上的输出。缺 1440×900 或 390×844 的画面，由辅助脚本用同一夹具补拍。
- **设计稿侧**：辅助脚本按同视口截取 `doc/design/console-v2/mock.html` 的对应画面。设计稿没画的画面（例如节点异常状态、设置搜索结果）只列应用侧，并注明「设计稿未画」。
- **产出**：辅助脚本与 `index.html` 对照页放在 `.deploy/console-ui-revamp/pages-acceptance/screens/`（git 忽略），不入库。

## 5. 样式检查

- **范围**：子任务 4 改动的页面样式：`accounts.css`、`request-records.css`、`proxies.css`、`session-blocks.css`、`nodes.css`、`settings.css`，以及七个页面组件和三个 runtime 组件的 `<style>` 块。
- **检查项**：grep 十六进制色值、`rgb()` / `rgba()`、`border-radius` 数值字面量、`!important`、Tailwind 调色板类。
- **处置**：命中的先判断是否属于 token 定义或无障碍覆盖。确属页面写死的值，按「真实问题」修。

## 6. 验收矩阵

`research/acceptance-matrix.md` 逐行记录本任务 Requirements 9 条、R-A1–R-A5 和 4 条 Acceptance：每行写对应子任务、业务提交、证据（脚本与结果、截图路径、grep 结果）和结论。

## 7. 提交

- **业务提交**：
  - 4 个修好的脚本；
  - 跑通后修的产品文件（如有）；
  - 规范改动（如有）。
- **任务记录提交**：本任务目录。包括 `prd.md`、`design.md`、`implement.md`、`brief.md`、两个 jsonl、`research/acceptance-matrix.md` 与 `task.json`。

## 8. 回滚

- 脚本改动彼此独立，按文件 `git restore`。
- 产品修复按页面文件回退。
- 提交后按提交整体回退，不影响三个子任务的提交。
