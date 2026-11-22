# 共同改动审查

范围来自 `overlap-paths.json`，比较共同基线至两个冻结提交；当前结果另与两侧分别比较。

| 文件 | 已核对的整合结果 | 验证依据 |
| --- | --- | --- |
| account-runtime-v3.md | 完整保留暂停迁移与 AGY 两组场景；同步措辞更新为原地切换；定义版本为 bench5/gateway6 | 定义扫描、冻结定义证明、对应行为测试 |
| platform-online-update.md | 临时清单定义和现有 AGY 迁移来源表、宿主依赖合同共存 | 定义扫描、宿主隔离导入测试 |
| ui-guidelines.md | 新节点管理图标与阶段显示条款和原 AGY 控件合同共存 | 节点、环境与请求页面探针 |
| api.ts | 新 cluster_nodes 公开投影和原 AGY 类型共存 | Web 类型检查与生产构建 |
| system_update_host.py | 远程环境交原节点维护，本机 AGY 平台支持检查与身份映射仍保留；还原路径保留上游元数据处理 | 部署更新状态机测试 |
| test_system_release.py | 导入同时覆盖重定向/下载校验、签名和 AGY 制品变化；保留双方用例 | 部署发行测试 |
| test_system_workflow.py | 保留 GH_TOKEN 受控传递及原 AGY 发行流水线断言 | 部署工作流测试 |
| runtime_bridge.rs | 节点同步只接受登记 POST；AGY 传输路径保持原实现 | Rust 白名单、传输及 Gemini 测试 |
| account_runtime.py | 上游大画像读取与并发变化拒绝逻辑保留；AGY 环境维护在代次核对后分派 | 编排全量测试、AGY 环境聚焦回归 |
| main.py | 保留 runtime.cluster_service 注入、节点同步启动和 AGY 清理任务；退出沿原取消与 ClusterService.close 收口 | 编排 API/生命周期相关测试与源码调用链核对 |
| system_updates.py | 远程环境消费节点实际证据；本机 AGY 保留凭据、许可与实际发送器活动检查；CC 暂停迁移租约按原标记核对 | 快照锁、暂停维护及新增 AGY 集群共存测试 |

## 字节保留与证据复用

- `preservation.json` 核对 AGY 单侧改动 223 个路径。唯一追加改动为 `test_agy_environment.py` 的共存回归。
- 上游单侧 63 个路径与冻结上游逐字节一致，v1.18.3 发行元数据一致。
- 两库迁移执行器、合同、纯定义和网关 store 共 32 个源文件与原集成结果一致。旧库升级、幂等、旧版兼容读写沿用原实跑证据，并绑定文件摘要。
- `frozen-definitions.json` 单独核对上游两库步骤 1–4 和 8 个纯定义文件。

## 新增回归

`test_cluster_update_snapshot_keeps_agy_local_and_waits_for_activity` 使用真实 SQLite、ClusterStore、ClusterService 和 AccountRuntime。断言 AGY 归属本机、公开平台身份正确；active、waiting、lease 或凭据 reconcile 分别阻断平台更新。
