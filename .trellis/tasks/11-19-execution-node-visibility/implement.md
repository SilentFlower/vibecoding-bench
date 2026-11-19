# 实施计划：执行节点可见性

## 顺序与依赖

- [x] 前置交接：读取兄弟任务最终的账号公开模型，节点功能的验收保持独立。
- [x] 通过本任务 Brief 审阅并启动，按 trellis-route、trellis-before-dev 加载相关上下文。
- [x] 核对任务账号、网关账号、环境列表、节点目录和请求尝试的真实字段及查询定义。
- [x] 补齐任务账号安全节点投影与网关账号使用的任务账号节点摘要类型，保留现有批量读取和轮询周期。
- [x] 更新账号卡片及详情、环境卡片及详情的节点展示。
- [x] 更新请求列表末次节点与链路逐次节点，统一已知本机、远程节点、未观测及无实际尝试的文案。
- [x] 验证迁移、远端不可达、读取失败和旧数据兼容，完成浏览器主要视口检查。
- [x] 完成检查、Spec 评估与控制解耦的联合验收。
- [x] 按精确 Push 计划完成 Git 交付。

## 预期影响文件

- `services/orchestrator/main.py`、`cluster_store.py` 账号公开投影及节点批量只读查询。
- `apps/web/src/api.ts`、`Accounts.vue`、`RuntimeEnvironments.vue`、`RequestDiagnostics.vue`。
- 必要的安全投影类型复用 `components/runtime/nodeApi.ts` 和 `runtimeApi.ts`。
- 任务账号沿 `apps/legacy-web/app.js` 的现有承载更新，环境兼容视图按现有原路由核对。

## 验证

```bash
python3 -m unittest discover -s services/orchestrator -p 'test_cluster_main.py'
python3 -m unittest discover -s services/orchestrator -p 'test_cluster_nodes.py'
npm --prefix apps/web run build
```

复用现有 `verify_accounts_design.py`、`verify_environment_workspace_design.py`、`verify_cluster_request_ui.py` 的真实浏览器模式，根据实际参数完成节点展示断言。验证本机/SSH 归属、失联时可读、旧日志未观测、无尝试请求、迁移后历史节点、跨节点多次尝试以及手机布局。

## 完成条件

- 本任务 AC1–AC5 有当前代码的验证记录。
- 父任务联合回归确认开关变化后节点归属与请求历史保持真实。
- 既有账号分页、筛选、独立工作区和环境详情可正常使用。

## 当前验证

- 节点存储、中央账号入口与控制恢复定向测试：32 项通过。
- 生产前端构建通过；新增真实浏览器工具 `verify_execution_node_visibility.py` 覆盖8个场景、1440/720/390px、账号与环境失联、请求迁移历史、多次尝试、未知/无尝试、读取失败与任务账号配置。
- 既有账号设计与请求链路浏览器回归通过。全量 Python 回归1976项完成，结果OK、跳过2项。
- 用户要求保证美观：已逐张检查实际截图，并优化手机请求列表与节点标识换行。

## 已授权修复与重检

- CHK-001：`AccountNodeSummary.node` 收窄为 `Omit<AccountNodeAssignment, 'account_id'>`，账号身份继续读取外层 id。前端类型检查与构建通过。
- FBK-001：单运行锁改为 RLock；清理回调的同线程重复停止沿既有 stopping 分支返回，跨线程仍串行。原递归停止、并发单次清理、失败重试和项目计划回归共45项通过。
- 首轮全量回归在原递归停止用例死锁后中断。修复后全量1976项结果OK、跳过2项；此前错误标记对应模块及递归停止均通过。日志 `.trellis/.runtime/execution-node-repair-python-full.log`。

- 全量期间两处迁移源码发生变化，已补跑全部直接消费者及迁移/传输回归48项，结果OK、跳过1项；补充验证期间源码保持一致。
- 三件套实现、接口假设和完整性重检通过；CHK-001、FBK-001全部闭合。DOC-001已机械更新规范中的迁移校验版本。新提交基线的最终版本为bench5/gateway7。
- 兼容环境入口的卡片与详情通过独立浏览器检查；CDN请求由本地夹具拦截，真实模型调用为0。

## 提交基线集成

- 提交对象为基于 `468c5969c82155d57c2ad54500eb3ba2357638ae` 的精确功能快照，共41个业务文件。同文件其它工作区差异保留原内容。
- 网关账号工作迁移顺延为 `gateway.account-work.7`，保留已发布平台版本5和请求记录版本6。数据库定义入口校验结果bench5/gateway7，定义回归9项通过。
- 新基线Python定向回归90项通过；前端生产构建、节点8场景三档宽度、账号设计、请求链路含AGY上下文、环境工作区浏览器回归通过。真实模型调用为0。
- Rust全量991项通过、13项按原条件跳过；新增版本6升级至7的台账保留用例独立核验。
