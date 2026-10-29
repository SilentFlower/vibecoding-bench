# Dataset合成SQLite业务场景设计

> 状态说明：本文保留设计阶段记录，实际验证与准入以[本项目准入记录](dataset-admission.json)为准。

## 来源与范围

固定 `pudo/dataset@db592cc041014762bba55fd544e982170831f227`，完整37文件和MIT许可。已读取Database的连接、事务、提交、回滚、close与query，以及Table的insert_many、_sync_columns、_check_ensure、upsert、create_index、find、find_one、columns的真实定义。环境固定当前SQLAlchemy 2.1.5等真实离线依赖，完整61项原生通过只覆盖当前SQLite适用路径，不声称其他数据库方言运行。

## 四场景八任务

| 场景 | 任务 | 实际业务与合法结果 |
| --- | --- | --- |
| DS-S01 订单输入与列规则 | DS-U01 理解 | 异构字典列表的列并集、缺失列填空及调用方字典不变 |
| DS-S01 | DS-C01 咨询 | ensure=False会过滤未知列，不是严格拒绝字段；应用层必须先校验 |
| DS-S01 | DS-D01 诊断 | 导入无异常却零行，先取输入类型、消费状态和实际循环；披露后定位一次生成器被预扫描耗尽，调用契约是Sequence |
| DS-S02 合成导入事务 | DS-U02 理解 | 异常越过with db边界会回滚；内部捕获后正常退出会提交，不能从最终日志反推回滚 |
| DS-S02 | DS-P01 方案 | 预建schema、校验未知字段、有限批次和真正事务；DDL及外部副作用不从SQLite样例推广保证 |
| DS-S03 业务身份与upsert | DS-U03 理解 | 现有两个相同业务键记录均被update，不自动归并为一行 |
| DS-S03 | DS-C02 咨询 | 自动普通索引不等于唯一约束，update后insert不是数据库原子冲突操作；明确并发保证来源 |
| DS-S04 可重复订单查询 | DS-U04 理解 | order_by稳定次序、limit/offset及命名绑定的业务字面，SQL条件不由值拼接 |

四场景八项均为只读、requires为空；不要求修补已有明确Sequence输入契约。DS-D01提供normal、diagnose_only、unavailable入口，仅在真实披露后提供输入类型与完整复现。全部数据库位于原生容器专用临时目录，每次显式指定SQLite URL，绝不读取DATABASE_URL或真实账号。

## 验收

七项独立程序事实在当前目标镜像实测；诊断按消费对话评审，不预泄露缺失输入。完整61项原生、实际业务、模拟产品链、页面／API／数据库以及Git／Docker准入分别记证。无工程目标，不捏造公开修复测试、错误候选或代码接受。
