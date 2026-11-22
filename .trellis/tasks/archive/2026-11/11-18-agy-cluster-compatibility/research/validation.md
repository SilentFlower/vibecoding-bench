# 兼容集成验证证据

## 冻结来源与集成范围

- AGY 来源：ca198ee979ec968bcd7d1a2063c872edb05850f7。
- 集群目标：0764b5fa75e0df6c5c12969fdc40b53d3bbf734c。
- 集成分支：merge/agy-into-flower2api；业务合并提交 `ceead61288063780f0117496e9758dd58435576a` 已推送，双父顺序及210个文件集合已核对。
- 文本冲突 20 个文件已解决。37 个交集路径的逐文件身份与合并策略见 overlap-review.json。
- 原集群和网关步骤 1—4、8 个纯定义文件与目标逐字节一致，见 frozen-definitions.json。
- 全部验证使用本地合成材料。实际供应商模型调用数为 0。

## 验证记录

| 编号 | 实际入口或证据 | 当前结果 | 验收 |
| --- | --- | --- | --- |
| V01 | verify_database_definitions.py | 通过，bench5/gateway6 | AC02、AC04 |
| V02 | cargo test --locked --manifest-path services/gateway/Cargo.toml | 17 个测试组，983 通过，13 忽略，0 失败 | AC05、AC06、AC07 |
| V03 | cargo fmt --check；cargo build --locked --bin claude-code-gateway --bin account-sender | 通过 | AC07 |
| V04 | npm --prefix apps/web run build | vue-tsc 与 Vite 通过 | AC06、AC07 |
| V05 | 初轮 deploy/flower2api unittest discover | 源码清单补齐后的整组复验 265 项，264 通过、1 跳过 | AC04、AC07 |
| V06 | test_database_migrations + test_agy_environment + test_cluster_environment_management | 最终受影响 5 个模块汇总 45 项通过，包含新增迁移和远程维护用例 | AC02、AC03、AC05 |
| V07 | old-cluster-bench.json | 实际旧集群执行器在 bench5 库返回 compatible_newer，旧账号写入与节点触发器、AGY 映射、原台账均保持 | AC02、AC03 |
| V08 | verify_agy_request_records.py --image flower2api-agy-auth:task-smoke --baseline .trellis/.runtime/agy-records-baseline-gateway | 9 个场景通过；旧网关读写、真实 UI/API/SQLite、19 个历史请求；外部模型 0 | AC03、AC06 |
| V09 | verify_agy_gemini.py --image flower2api-agy-auth:task-smoke | 通过，20 次隔离合成发送，真实 HTTP/SQLite，外部模型 0 | AC05、AC06 |
| V10 | verify_cluster_request_ui.py | 4 个场景通过，CC 节点、历史未知、AGY 上下文与本机位置、1440/390 布局 | AC06 |
| V11 | verify_cluster_ui.py | 10 个节点与迁移管理场景通过，外部模型 0 | AC05、AC06 |
| V12 | verify_environment_ui.py | 25 个场景通过，包括 CPU 草稿/CAS、采集、CRIU、平台内核只读、维护确认/取消/代次、1440/720/390、迟到回执与离页清理 | AC05、AC06 |
| V13 | test_cluster_environment + test_cluster_main | 13 项通过 | AC05 |
| V14 | test_cluster_quiesce | 补齐运行时替身的真实数据库接口后 9 项通过 | AC05 |
| V15 | test_cluster_draft_schema | 明确版本 4 迁移与故障注入目标后 6 项通过 | AC02、AC03 |
| V16 | services/orchestrator 全量 unittest discover | 首轮 2031 项暴露 6 个适配失败；修复后完整 discover 集合分四个独立进程复验，2034 项中 2024 通过、10 跳过，0 失败，集合覆盖逐项核对一致 | AC07 |
| V17 | test_system_workflow 的仓库外独立导入 | 补充 system_release 导入后重现缺少 agy_environment_schema；源码清单补齐后仓库外 -I 导入及整组 265 项复验通过 | AC04 |

| V18 | gateway-four-upgrade.json | 冻结定义版本4库经真实CLI升级到6，重复迁移、原账号与台账、历史CC平台保持；旧二进制按目标4规划返回compatible_newer | AC02、AC03 |

完整原始输出位于本工作区 gitignored `.trellis/.runtime/agy-cluster-merge/`。完整用例身份见 python-batch-0—3.json；并集与 discover 集合一致见 python-final-aggregate.json，源码及日志摘要见 validation-evidence.json。

## 集成语义复核

- bench 正式链沿集群 1—4 追加 AGY 5；开发分支 AGY 2 同号异身份受控拒绝。专门用例验证拒绝前后整库 iterdump 一致。
- system_release 只有一个 BENCH_SCHEMA_SOURCES，涵盖所有正式步骤，保留严格来源和符号链接检查。
- 构建保留目标运行时平台版本读取与缓存，再增加 AGY 认证制品 SHA。宿主固定源码包同时包含集群和 AGY 迁移模块。
- main 的维护请求把冻结代次交给所属 Node；中央在租约之前检查，Node 按实际 scope.generation 再检查。旧客户端省略字段沿原协议。
- AGY 尝试初始记录从已核验 TransportBinding 冻结 execution_location，与 context 同时写入，认证恢复也采用本次原绑定。
- 资源收口同时取消 AGY 清理任务和关闭集群迁移操作；AGY API 环境与工程账号命名空间保持独立。
- 遗留 UI 探针由独立内核激活/回退断言更新为实际只读平台内核合同，维护确认/取消/代次及迟到事务通过现有维护入口继续覆盖。

## 后续授权边界

真实供应商登录、Google 接受性、真实到期、生产升级及节点版本换批继续由既有 EXT01—EXT07 和部署 SOP 承接。AGY 远程节点调度及旧开发分支 AGY 2 的真实数据库转换属于独立范围。

## 完成链

- Check-All：full，三维通过，CHK 0 / FBK 0 / DOC 0。
- Spec：written，仅更新两个既有权威规范场景，六节完整并反查源码与测试；规范diff检查通过。
- Git：精确计划已确认，业务合并提交/推送及双父、文件集合复核已完成。

## Git方向与空白复核

- 最终第一父提交为集群目标，第二父提交为AGY来源。完整索引树与方向调整前的候选树完全相同，cached空白检查通过。
- 三处文件末尾空行已规范化，两个Python文件AST保持相同。此机械整理沿原全面检查证据加定向语法/相关测试复验。

- 最终机械调整复检通过：两个Python桥语法及16项相关单测通过；整树身份和cached空白校验通过。Spec后续复核为no-op，原written合同仍有效。
