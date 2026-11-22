# 当前请求记录接线证据

## 基线与边界

- HEAD c0c9122e，AGY原生业务c61d635b、同形体8348b09b。父范围和当前用户指令为继续请求记录子任务；当前任务经完整Brief到期领取后进入in_progress。
- 现有PRD、父PRD、近期提交和依赖交接已覆盖产品决定，本轮未调用历史会话检索。
- 当前上下文没有唯一auto run及untracked work。其他旧任务progress候选不属于本任务。

## 实际定义与入口

- services/gateway/src/model/request_diagnostics.rs:40、:220定义RequestDiagnostic、AttemptDiagnostic；现有DiagnosticTokens是CC六类token。safe_model限定claude-，不能直接用于Gemini原始用量及原生MODEL_*标识。
- service/diagnostics.rs:75创建根上下文，:326/395准备尝试，:475提交计数，:585由UsageCapture解释CC结果，:719在HTTP响应体生命周期终结根记录。task-local作用域不跨tokio::spawn自动继承。
- service/gateway.rs:1709—1763仅精确/v1/messages进入既有日志模式、TraceContext和RequestTraceGuard。Gemini的service/gemini.rs:374独立处理已鉴权入口，:510后的spawn持有drive，暂未接入此存储。
- service/gemini.rs:659附近校验原生事件归属，:708消费策略回执，认证恢复产生独立attempt_id；:831保留ToolTurn，previous_request_id实际指向原模型尝试。HTTP工具响应完成后drive仍等待原生job_finalized，因此原生收口具有独立观察时刻。
- store/diagnostics_store.rs的FILTER/后台队列、write_event及list/detail拥有正式分页、计数和七天保留。JSON摘要各16KiB。当前根已终结时迟到未终结快照不会覆盖；工具收口须用限定字段更新以保留该保护。
- handler/router.rs:2833—2915拥有管理员诊断和按请求核对attempt归属的采集API；runtime_bridge.rs:281桥接/internal/v3/native-captures/{account_id}/{attempt_id}。
- services/orchestrator/main.py:12703核对唯一未删除环境绑定；native_capture.py:162固定读取flows/api/cc-prepared，校验UUID、目录FD、NOFOLLOW、账号、阶段和七天，现有阶段只接受CC。
- AGY私有原始材料位于flows/api/agy-prepared的worker请求目录；gemini-input.json是已解码输入，input-mapping.json登记策略与表示，rpc.ndjson保存Cortex提交。管理端应读取独立有界脱敏快照，不能开放任意原生日志文件。
- AgySubmission已有capture_enabled；runtime_transport.rs:1407当前按sender目录覆盖该字段。实现须冻结本次日志模式与账号策略，核对生产者、消费者和旧组件缺口，不以采集故障触发模型重放。
- native_capture::ingress已实现debug门槛、有界原始逻辑入站、敏感头/重复秘密/JSON转义脱敏，可复用。完整HTTP入站与已解码Gemini必须区分。

## 前端与迁移

- apps/web/src/api.ts:409/440定义诊断DTO；RequestDiagnostics.vue沿固定四页签、服务器分页、独立AbortController/generation及焦点返回。canInspect只接受CC原生阶段；native运行时DTO的计时来源不可伪填为AGY事实。
- store/database_schema.rs是冻结baseline；新增筛选结构需独立纯定义，追加database-migration-registry.json步骤及database_migrations执行/核验分支，并同步deploy/flower2api/system_release.py的精确源码映射。当前已登记1—5。
- 平台自动迁移规范允许旧程序识别compatible_newer；新增版本仍需真实隔离旧程序读写证据。PostgreSQL沿既有初始化增量接线，SQLite与PG均保持Any绑定类型一致。

## 现有验证资产

- Rust诊断存储/router/gateway用例；deploy/flower2api/verify_management_ui.py及verify_management_polish.py覆盖原页和复制/缺失/迟到回包。
- verify_agy_gemini.py为真实HTTP/SQLite及合成发送器；verify_agy_native_loopback.py为真实网关/发送器/固定原版/本地TLS和MCP，可追加记录查询断言。
- 上任务Rust968项、部署223项、原生TLS17+1次及浏览器通过。新任务按实际变更重跑相应证据；既有python-dateutil摘要错误单独隔离。

## 实现阶段补充

- 根上下文在首次入队前冻结平台及协议，避免旧CC缺省值先落入筛选投影。
- AGY物理控制状态与工具状态使用限定字段队列补写，HTTP根和模型结果保持独立；下游取消只记录所观测的取消事实，实际原生收口缺省未知。
- SQLite新增诊断并行写入触发凭据事务读快照升级冲突。真实HTTP故障核对sqlite_busy后，凭据CAS提交与限定诊断补写在读取前取得写权限；CAS条件与RT归属保持。并发回归及20次替身提交通过。
- 原始执行材料沿临时worker目录与关闭清理；长期内容仅保留独立有界脱敏快照。入站旁路保留既有captured_at_ms，严格读取嵌套来源及白名单；入口缺失单独显示缺口。
- 旧程序副本来源c0c9122e，隔离演练完成5→6、重复迁移、compatible_newer及真实旧程序管理读写。当前镜像源AGY原版身份由原探针核对；测试镜像采用flower2api-agy-auth:task-smoke。
- 全量Python共1386项，1380通过、5跳过、1项既有python-dateutil初始摘要错误。该基线错误已在依赖任务登记；源数据摘要证据位于gitignored运行目录。

- FBK-001修复：tool_turn_finalized只更新工具状态；job_finalized独立更新物理控制。提前原生失败/取消保留尝试结果与控制未知。新增真实SQLite顺序回归核对工具完成后控制失败、取消先于回执及重复回执，保持原HTTP和尝试起止时间。
