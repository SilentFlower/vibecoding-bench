# Native 消息缓存实施计划

## 实施顺序

- [x] 核对实际设置、NativeSubmission和worker协议，冻结默认off及off/sub2api请求级语义。
- [x] 增加双库一次性重置与事务完成标记，统一GET/PUT、默认值和运行期加载，保留迁移后管理员手动开启的选择。
- [x] 贯通受信任请求策略、能力握手、恢复握手和旧worker拒绝边界。
- [x] 更新原生选点器以执行显式重排，复用原有断点算法，维护TTL和诊断。
- [x] 收敛设置页选项、类型和说明，保持草稿、全局保存和保存期间编辑合同。
- [x] 更新共享文档和配套执行体构建验证材料。
- [x] 为真实CLI集成的进程准备与25次连续请求匹配测试等待预算，保留原单次池期限和全部业务断言。

## 验证矩阵

- off/sub2api × 无断点/已有messages断点/已有system-tools断点/预算耗尽。
- 字符串content、user tool_result、assistant尾部、带签名thinking、嵌套业务同名字段。
- TTL off/5m/1h组合，输入原对象、根级缓存和未知结构边界。
- 保存后同一暖worker连续切换模式、并发请求、280/293和恢复握手。
- 旧能力worker在强制模式发送前失败；诊断包含实际mode/action/位置及确定原因。
- SQLite/PostgreSQL存量sub2api、废弃模式、历史别名、off、缺键、重复归一化和非法PUT。
- 一次性重置后手动开启sub2api并重启，事务失败重试、并发启动、迁移标记及无关设置保持。
- 新安装与缺失设置默认off，备用策略手动开启及切回off，设置说明与实际原生缓存行为一致。

## 验证命令与证据

services/gateway：cargo test --locked（开发中优先相关设置、rewriter和native协议测试）。services/runtime：bun run typecheck、bun test tests/unit、bun run test:integration，最后按 scripts/test-native.ts 的隔离方式运行 bun run test:native。apps/web：npm --prefix apps/web run build，并以合成设置接口核验选项、草稿和保存交互。

跨消费者验收复用 scripts/testing/cc2api-native.ts 的回环TLS入口；记录真实执行体、实际出站正文、非零CCH和280/293来源。配套构建只产生本地候选，发布、部署和激活保持独立流程。

## 评审与回滚点

本项读取R1完成后的公共循环，适配当时工作区。Check-All关注生效快照、能力缺失、双库兼容和真实TLS证据。数据库兼容和公开枚举收敛须在交付说明中记录；代码回滚与已迁移值恢复分别处理。


## 验证证据

- HEAD加本任务精确补丁的交付副本Rust全量942项通过，13项条件用例忽略；工作区含并行任务的全量950项通过。格式检查通过。SQLite默认值、一次性重置、并发、回滚和持久选择通过；独立PostgreSQL临时库验证含失败回滚通过。
- runtime单元测试197项通过；官方原版280/293各69项离线原生测试通过。最终配套候选280/293分别独立构建两次，分发与执行映像摘要一致；候选各69项离线原生回归通过。
- 隔离副本仅替换本地候选固定身份后，真实Gateway→sender→原生执行体→TLS完成15次请求。覆盖双版、API/完整原生输入、off/sub2api/off、TTL及暖PID复用；429后切设置保持原请求重试快照，下一请求采用新值。诊断与实收断点相符，独立CCH验证通过。
- Web构建通过，1440/390px浏览器验证默认off、两项选择、草稿/撤销、字符串保存、刷新持久选择及手动关闭通过。
- 常驻池集成初次出现归因计数与超时失败，两项独立复测通过；按真实CLI场景调整测试总等待预算后，最终完整runtime集成50项通过、0失败（/tmp/native-cache-runtime-integration-budget-final.log），保留25次调用和500毫秒单次池期限。
- 共用脏文件以实施前副本区分归属，HEAD基线加本任务精确补丁的独立副本通过交付范围复核；最终真实TLS日志为/tmp/native-cache-own-gateway-tls.log，报告为/tmp/native-cache-own-gateway-report.json（code=0、15次实际请求）。

- 最终独立Engine能力检查后，280/293候选各2项定向原生测试通过。启动及恢复握手共同声明并严格校验消息策略能力；恢复准入沿现有身份、随机挑战及PID合同核对。配套候选的bridge_sources逐项与当前源码摘要一致。
