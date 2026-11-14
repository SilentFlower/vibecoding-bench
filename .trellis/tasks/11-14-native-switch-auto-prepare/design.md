# 显式切换后的后台准备

## 边界与数据流

1. 网关拥有配置事务、RuntimeConfigPermit 和 NativePrewarmer；编排服务拥有唯一账号映射、环境启动、sender 配置及预算预检。
2. 覆盖普通账号更新与 status 快捷出口。成功保存明确 native293 选择且最终 active 后，释放原配置门禁，再发出允许唤醒的准备意图。失败保存不发起唤醒；切回 legacy 或停用仅失效原工作。
3. 扩展现有准备提示以区分显式唤醒和普通检查，仅携带账号归属与意图，不携带凭据。复用并行 2、队列 128、去重、取消及失败退避。
4. 出队重读权威账号、更新门禁和凭据所有权。显式意图调用现有 runtime_transport::prepare 和编排 transport 路径准备环境；普通扫描、5/20/60 秒补偿、20 秒巡检及 GET 检查仍调用 prepare_existing / wake=false。
5. 得到当前绑定后复用 readiness / prepare_native；完成真实握手及回池，沿原路径准备符合准入的 CRIU 模板。发布 ready 前重读账号与绑定。后台准备不调用 execute。
6. 维护等待与失败退避保留当前显式意图；取消、停用、切回 legacy 或身份变化使旧意图失效。原环境就绪通知保留按环境/代次去重，避免准备过程自触发无限循环。
7. 管理员重试经编排服务校验环境和唯一账号绑定后代理到现有管理员准备接口，进入同一有界队列。

## 状态与错误

- 环境摘要区分安全目标后端与实际 sender 布局。GET 列表只读取事实，不唤醒或刷新凭据。
- 目标 native293 而本地配置仍普通时，原生准备区显示“已选择原生运行时，等待环境准备”，再展示当前后台状态。旧接口缺新增字段时保持兼容。
- ready、PID、进程数及模板仅来自同代新鲜证据；原生基础就绪、CRIU 模板、TLS 采集各自判断。
- 补齐受控资源/绑定/维护失败原因和通用未知失败；不把所有 503 当作预算问题，不直接显示异常原文、URL、代理或凭据。
- 准备失败保留已选 native293、HOME、身份、资源和原对账门禁，沿现有退避及显式重试恢复。

## 已落实的内部接口

- 账号准备事件为 `(account_id, invalidate, wake)`；现有通知默认 wake=false，成功切换及明确重试发送 wake=true。
- 管理员 POST `/admin/accounts/:id/native-preparation?wake=true` 允许唤醒；旧调用省略参数继续只读运行绑定。`cancel=true` 撤销准备及失败唤醒重试，wake/cancel 同时为真拒绝。人工停止先撤销当前意图。
- 任务侧 POST `/api/environments/{environment_id}/native-preparation` 校验唯一绑定与当前目标后入队。
- 内部 transport 的 `x-v3-runtime-reason` 只透传三个资源白名单码：native_sender_budget_missing、native_sender_budget_insufficient、account_memory_insufficient；未知错误保持通用失败。环境列表附加安全 request_backend 目标字段。

## 默认策略衔接

- 纳入本轮已实现的创建载荷与两个新增本地记录入口：native293、5h85/7d80；两处额度独立，默认常量共用。既有值及 NULL 保持实际事实，无 schema 迁移。
- 当前纳入的 5 个 dirty 文件为 main.py、test_main.py、test_login_drafts.py、account-runtime-v3.md、database-guidelines.md。其余 397 个路径保留。

## 资源限制与回退

- 11-14 当前 1536 MiB 有限 RAM 和空 sender 预算会先被既有预检拒绝。4 并发对应 8 worker，普通原生 sender 最低 1792 MiB，加网络 256 MiB、CLI 512 MiB，总计最低 2560 MiB；CRIU 另行准入。线上资源调整独立决定，本任务明确展示阻断。
- 回退修复恢复原惰性准备行为，数据库后端和额度保持原事实。准备/取消无法确认则保留对账材料，禁止重放模型请求。

## CHK-001 修复设计

- projects_submissions 和独立 warmup_projects_submissions 均为已有 SQLite rowid 表。读取按 created_at DESC、rowid DESC 排序；插入顺序仅作为时间相同的确定性次序，UUID 保持身份用途。
- 同步验收进度和工作详情的提交历史列表。无新增列及迁移，原时间、提交 ID、阶段事件过滤和耗时合同保持。
