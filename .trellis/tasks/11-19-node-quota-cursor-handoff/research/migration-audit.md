# 节点迁移边界审计

日期：2026-11-19。用户在额度游标修复规划期间要求排查类似迁移缺陷。

## 证据范围

本报告基于当前工作区源码、真实临时 SQLite／文件及现有合成执行夹具。迁移命令、Gateway 租约和远程传输使用已有替身。四项补充发现均完成本地隔离复现。用户随后明确要求在同一个任务内修复全部已确认问题，最新范围以 prd.md 为准。

线上 `11-14` 的额度来源路径冲突已由前一轮只读查询确认。下列补充问题的线上影响账号范围待核对。

## M1：迁回本机后继续消费旧远程镜像

- 优先级：高。属于原额度路径缺陷的反向路径，已在当前 R1／A2 范围。
- 触发：远程 API 游标已经登记，账号回迁本机后追加新的本机 API 额度观察。
- 根因：`services/orchestrator/main.py:3331` 使用 INSERT OR IGNORE。原逻辑来源键已经存在时，本机新路径未进入登记，消费器继续读取远程镜像。
- 复现：复用 `test_cluster_quota.RemoteApiQuotaTests`。先消费远程 20% 样本，再把临时归属切回 local，写入时间更新的本机 60% 样本，通过真实 QuotaGuard.consume 消费。
- 结果：

```json
{"case":"远程迁回本机后的额度消费","before_percent":20.0,"new_local_percent":60,"after_percent":20.0,"registered_local_file":false}
```

- 用户影响：页面可能继续展示旧额度；后续任务与养号按旧事实判断门禁。

## M2：部分上传后“继续原迁移”反复命中同一损坏暂存

- 优先级：高。独立于额度路径登记，属于迁移恢复完整性缺口。
- 触发：源已隔离，上传阶段留下不完整 environment.tar，随后继续原迁移。
- 根因：`services/orchestrator/cluster_migration_files.py:207` 拒绝部分上传并要求新的上传尝试；`services/orchestrator/cluster_migration_runner.py:205` 每次从已冻结 execution 读取相同 transfer_id。账本恢复只回到原阶段，缺少合法创建新传输尝试的动作。
- 复现：复用 `MigrationCoordinatorTests` 的真实中央账本与租约替身。上传端调用真实 MigrationFiles.stage，写入 partial 文件后模拟断线，连续两次恢复同一操作。
- 结果：

```json
{"case":"上传中断后原操作续接","errors":["合成上传中断","目标暂存包含不完整上传，请使用新的上传尝试","目标暂存包含不完整上传，请使用新的上传尝试"],"attempt_count":3,"distinct_transfer_ids":1,"assignment_phase":"reconcile"}
```

- 用户影响：点击继续持续重复报错，账号保留维护／待对账状态。修复须保留原部分文件与操作证据，同时给同一迁移建立受控的新传输尝试。

## M3：本机历史工程迁出后抓包入口失去可用定位

- 优先级：中。影响历史排障和抓包读取。
- 触发：本机已结束工程没有 remote_execution 账本，账号迁往 SSH 节点后打开该历史工程的抓包。
- 根因：`services/orchestrator/cluster_projects_terminal.py:51` 按账号当前归属判定缺少远程执行定位；已结束的本机历史工作因此在读文件前报错。`services/orchestrator/projects.py:1044` 使用该路由，`projects_api.py:166` 将其转换为公开 404。
- 复现：复用 `ClusterProjectsTerminalTests`，先验证本机已结束工作的抓包可读，再更新临时节点归属为 SSH，读取同一工作。抓包内容读取使用原本机接口替身，归属和执行账本为真实 SQLite。
- 结果：

```json
{"case":"本机历史工程迁出后的抓包入口","before":{"files":["合成历史抓包"]},"after":"远程工程缺少原执行定位，请先核对启动结果"}
```

- 用户影响：历史抓包入口报告不存在／归属不符。本项复现确认的是路由失败，文件实际保全另由迁移归档验证。

## M4：环境换代重读历史证据会重新触发已解除的认证门禁

- 优先级：高。与当前 R2／A3 的历史重读保真直接相关。
- 触发：API 历史文件包含已消费的 account_on_hold；后续完整人工额度核验解除该门禁；迁移或环境重建改变读取 scope，使镜像从头重读。
- 根因：`services/orchestrator/cluster_quota.py:176` 在 scope 变化后重读。`services/orchestrator/main.py:3284` 对 account_error 的写入缺少观察时间判定，`:3375` 又对历史错误无条件调用 record_auth_failure。
- 复现：复用 `RemoteApiQuotaTests`。先消费时间 1000 的合成认证错误，在时间 1001 调用真实 record_manual_usage 完整核验两个窗口，然后同步提升中央与节点的临时环境代次，触发真实远程镜像重读。
- 结果：

```json
{"case":"环境代次变化后重读历史认证错误","historical_error":"account_on_hold","after_explicit_verification":null,"after_generation_change":"account_on_hold","latest_observation_time":1001.0}
```

- 用户影响：原已解除的认证门禁再次生效。record_auth_failure 还会收口额度等待任务、暂停批次和旧养号开关，需在修复中保护最新人工核验及已用恢复机会。

## 现有保护与后续范围

源码已具备迁移归属 CAS、目标身份核验、源隔离、未知激活回执恢复及绑定／独立凭据所有权保护。本轮补充发现集中在资料交接后的消费入口和失败恢复衔接。

- M1 和 M4 纳入当前额度修复既有验收边界。
- M2 和 M3 已按用户最新指令合并到当前任务 R6／R7，统一实施和验收。
- 磁盘布局、全部历史 Run／续聊读取、跨不同物理宿主的全部组合仍需按后续修复影响选择实际验证。

## 现有回归复核

执行命令：

```bash
PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_cluster_migration_files test_cluster_migration_runner test_cluster_projects_terminal test_cluster_quota
```

结果：36 项测试全部通过，耗时 25.552 秒。四项补充隔离复现暴露了现有回归覆盖之外的交接场景，后续修复需补充相应验证。
