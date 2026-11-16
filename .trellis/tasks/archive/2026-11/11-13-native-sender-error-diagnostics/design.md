# 技术设计

## 边界与数据流

原生 job 失败边界 → worker 有界安全摘要 → 私有 error 事件可选 diagnostics → TypeScript 共享解码器 / Rust sender 校验 → sender 结构化日志。网关已有根 request_id → native_job_id 的提交日志提供跨进程关联。

## 诊断合同

- error 新增可选 diagnostics。既有 schema_version、error、code、status 保持原语义。
- 摘要 schema_version=1；stage 固定为 input、context、construction、dispatch、response_headers、response_body、unknown。
- causes 最多八项，每项只含白名单 name/code；另有循环与截断标记。未知值归 unknown。系统及 TLS 代码复用现有受控目录，按实际 Bun/Node 错误定义补充有限代码。
- 只读取已知标量，不序列化任意对象。getter 失败安全降级，访问集合检测 cause 循环；不读取或输出 stack、URL 和任意 message。仅有固定 message 的 Bun 错误若需分类，使用已验证完整固定文案匹配及固定输出。
- 阶段按实际操作边界记录，保留原始 BridgeError 的 code/status 与取消语义。
- TypeScript 共享 protocol 校验新合同，Rust 独立重建安全对象。缺省诊断记 unavailable，畸形诊断记 invalid；Rust 不输出原对象或因此重放业务。
- TypeScript 先校验基础错误与归属，再重建安全 error 载荷。畸形摘要移除后附加可选 diagnostics_state=invalid，保留原 code/status。decodeWorkerFrame 与 decodeLocalDriverFrame 必须交付该规范化载荷；Rust 同时识别规范化失效标记。

## sender 日志

- account-sender 初始化 tracing-subscriber，默认 info，支持 RUST_LOG，使用 JSON 并关闭 ANSI。
- native_error_event 保留原 code/SHA，增加诊断状态、安全 causes、阶段、worker PID、账号 ID 和环境代次；native_job_id 对应 attempt UUID。
- 在退役前输出到 sender 标准日志，沿 Docker 原有轮转保存；进程目录继续按现有规则清理。
- 审查启用日志后可达的 tracing 调用，保持受控字段；不启用原始头部或 IPC 转储。

## 兼容与交付

- 旧内核 error/code/status 正常处理，并明确 diagnostics unavailable。新增诊断为可选字段。
- 本仓 runtime 源码与 gateway 消费者配套验证。固定内核 SHA、签名接纳、探针偏移及线上选择沿原合同。
- 完整 cause 摘要在后续构建、验签接纳和激活配套内核后生效。sender 更新可恢复已有日志及诊断缺省状态。
- 交付源码、测试与合同文档。生产发布及签名内核发行属于后续独立操作。

## 风险与控制

- 错误对象可能含秘密、循环和异常 getter：有界白名单提取，跨语言再次校验。
- 旧二进制缺少新字段：兼容降级并明确缺省，历史记录保持原证据。
- 日志初始化激活现有调用：审查可达路径，用合成秘密验证实际输出。
