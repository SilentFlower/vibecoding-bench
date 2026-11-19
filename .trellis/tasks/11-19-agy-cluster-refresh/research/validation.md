# 本轮验证证据

来源与目标冻结于 `merge-inspection.json`。命令、源码摘要、日志摘要和完成链状态见 `validation-evidence.json`。

| 验证 | 结果 | 范围 |
| --- | --- | --- |
| 编排完整 discover | 2074 项最终覆盖，2064 通过、10 跳过 | 4 批原集合及新增 AGY 环境用例；逐 ID 及重复次数与当前 discover 一致 |
| AGY 环境聚焦 | 8 通过 | 新增集群归属与平台更新排空共存回归 |
| 网关 Rust | 983 通过、13 ignored | 17 个测试集合；cargo test --locked |
| 部署工具 | 274 通过、1 跳过 | 275 项完整 unittest discover |
| 格式及定义 | 通过 | cargo fmt、Python 编译、git diff --check、数据库定义扫描 |
| Web | 通过 | vue-tsc 与 Vite 构建 |
| 节点页面 | 13 场景通过 | 自动同步、未准备迁移、确认、恢复、未知提交和窄屏 |
| 环境页面 | 25 场景通过 | 维护、代次、资源草稿、晚到回执及 1440/720/390 布局 |
| 请求链路页面 | 4 场景通过 | 节点、实际代次、AGY 上下文和历史未知 |
| 冻结与保留 | 通过 | 8 个纯定义、两库前 4 步、AGY 单侧及上游单侧文件保留 |
| 旧库兼容读写 | 复用有效证据 | 32 个依赖文件与原集成逐字节一致；证据与源摘要见 preservation.json |

## 首轮失败与复验

- 首轮第 3 批的 `test_missing_checkpoint_blocks_without_rebuilding_seed` 预期接续证明错误，实际得到启动状态校验错误。
- 单项独立复验 1 项通过；同模块复验 31 项通过。首次失败原因仍待确认。
- 相关 `project_iteration.py/project_plans.py/test_project_plans.py/test_project_iterations.py` 与两侧冻结基线一致，当前结论使用复验结果；首轮失败保留在 `python-batch-3.json`。
- 完整集合匹配和最终结果见 `python-final-aggregate.json`，包括全部跳过项、复验数量及相关源码摘要。

## 环境边界

- 编排的 10 项跳过涉及显式 Docker 验证开关、固定 Pi SDK、nose2 等专用环境条件，逐项理由保存在批次与汇总 JSON。
- 外部真实模型提交为 0。验证采用临时库、隔离文件和本地服务。
- 首轮及复验原始日志位于 `.trellis/.runtime/agy-cluster-refresh/`，当前机器证据绑定其 SHA256。
