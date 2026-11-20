# Native 消息缓存策略设计

## 配置与数据流

沿用 message_cache_control_rewrite 字符串设置，公开可选值收敛为 off/sub2api。Settings.vue、settingsSchema.ts、管理API校验、设置加载和运行期快照保持同一枚举范围。off 对应运行时 preserve；显式 sub2api 对应已确认的消息断点重排。

默认值统一为 off，作为管理员排查缓存问题时可手动启用的备用策略。设置页标明 off 保留原生缓存布局，切回 off 后恢复该布局；独立 TTL 设置继续按自身配置执行。

配置在单个请求构造时冻结，经 NativeSubmission、sender校验和私有 request_input 指令传入worker。该传递位于已有TTL策略旁，使用NativeSubmission.message_cache_policy及request_input.message_cache_policy（preserve/sub2api），worker_ready.message_cache_policy_protocol=1声明新版能力。能力检查覆盖280/293、启动和CRIU恢复握手。旧worker仅允许已能确认的preserve；强制sub2api缺能力时发送前返回明确503。

独立运行时显式启动sub2api同样核对新版策略能力，旧语义内核按配置错误拒绝。worker启动配置继续作为独立运行时的默认策略，受信任逐请求指令可覆盖本次模式；调用方HTTP正文及请求头保持原控制边界。策略在原生CCH封口前执行，实际组装快照和诊断应用结果来自同次处理。

## 策略合同

off保留消息缓存布局，独立TTL设置仍可覆盖已有TTL。sub2api清理协议messages内容块的已有断点，再按原有算法选末条message及消息数至少4时的倒数第二个user尾部可缓存块。system/tools断点继续占用总计4个的预算；thinking、图片和tool_use按原有可缓存判断处理。业务schema/tool input中的同名字段保持其业务意义。

原生现有“调用方messages已有断点则整体跳过”的规则与本次明确决定冲突，须同时更新共享处理器、测试和文档，明确显式sub2api的新语义。根级缓存、未知结构、TTL混排等边界以原有算法和已存在协议约束共同核对，越界输入使用受控结果；实现不得自行扩大重写范围。

## 存量处理

首次接入时，auto/rolling/stateful、stable/anchored历史别名及存量sub2api统一转换off，保留显式off；新安装和缺键同样补齐off。复用既有settings兼容补齐入口，在SQLite/PostgreSQL各自的现有settings存储内，以同一事务完成一次性迁移标记及设置重置。并发启动只有首次取得该标记的处理执行重置；事务失败整体回滚，后续可安全重试。完成后管理员手动保存sub2api，后续启动和兼容调用均保留该值。内部标记为_internal_native_message_cache_v1，由get_all过滤并在公开保存入口拒绝覆盖。

冻结数据库基线与登记摘要保持。PUT拒绝退出范围的值；GET与运行期读取同一最终值。缺失/非法值沿明确默认off兜底。迁移验证覆盖首次接入、重复执行、失败重试、并发启动、迁移后手动开启及无关设置保持。

## 风险与回滚

旧内核能力、常驻worker策略串请求、恢复握手、TTL组合和共享独立运行时的显式sub2api语义为重点。代码回滚前保存旧值转换记录；off可随时恢复保留布局。新适配器需本地构建、真实执行体核验及280/293回环验证，软件发布与线上激活走独立SOP。

## 验证预算

真实CLI联调中，次数与参数透传用例包含冷进程准备和25次连续调用，测试等待预算按60秒配置；完整离线CLI组按420秒配置。假池500毫秒单次网络期限、25次实收与参数断言保持原值。该调整仅用于验证进程等待，业务期限沿原合同执行。

诊断验收按异步队列最终落盘等待，最多30秒；同时断言写入失败与丢弃均为0，核对完整尝试终态。该等待仅发生在隔离验证，模型发送次数及业务期限保持原值。
