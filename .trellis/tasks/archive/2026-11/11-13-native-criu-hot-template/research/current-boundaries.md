# 规划阶段接入边界

本文保留实施前源码基线与研究限制。实施后验收及实际类型见 implementation-progress.md、acceptance-evidence.md 和本目录 Bookworm 安全摘要。

## 已有实现

- `services/gateway/src/service/native_runtime.rs:353`：Worker 持有具体 tokio Child、ChildStdin、ChildStdout 和私有目录；当前退出等待依赖直属子进程，恢复进程需要新的明确所有权表示。
- `services/gateway/src/service/native_runtime.rs:687`：Worker::start 完成私有目录、代理、固定环境及精确 FD 启动。
- `services/gateway/src/service/native_runtime.rs:807`：ready 中的 pid 当前必须等于 Child::id，恢复到独立 PID 命名空间需要新增经过验证的映射合同。
- `services/gateway/src/service/native_runtime.rs:827`：执行体核验四个 seals；共享 exec 分支额外校验 dev/inode。CRIU 研究补丁重建执行体 memfd，需要明确恢复分支的等效身份准入。
- `services/gateway/src/service/native_runtime.rs:1801`：submit_validated 在 checkout 后唯一 execute，随后等待流与 worker_idle 收口。CRIU 创建应接在 execute 之前。
- `services/runtime/src/runtime/293/worker.ts:41`：worker_id 在启动时冻结；当前 ready 在 bootstrap 后发出。恢复副本需要新身份绑定与新握手，不能重用快照前的 ready。
- `services/runtime/src/shared/protocol.ts:92`：工作进程事件当前按 schema_version=2 与 worker_id 解码。新增恢复能力应有共享类型、解码器及实际消费者兼容。
- `services/orchestrator/account_isolation.py:257`：原生 sender 以 UID 1001 启动；启用 TLS observer 时受信任入口使用 SYS_ADMIN/SETUID/SETGID 及显式 seccomp，业务子进程降权。当前 seccomp=2 环境与 CRIU 控制器的 seccomp=0 要求应分离处理。

## 证据与约束

- `criu-memfd-summary.json`、`criu-memfd-feasibility.md` 和 `criu-memfd-executable.patch` 保存本轮隔离验证的安全数据、来源及补丁。
- 原始完整日志与执行体保存在 `/tmp/flower2api-criu-research-9amnj8l_/memfd-followup/`。原生二进制、快照、官方提取模块及账号内存不进入任务提交。
- 原版 CRIU 4.2 在 exe_file_id 的普通文件类型查找阶段失败；研究补丁兼容 MEMFD 后三轮独立快照恢复均成功。
- 现有实验尚未覆盖同模板重复及并发副本、独立恢复握手、进程池共享映像身份合同、完整 TLS 和生产权限预检。实施以这些明确的技术验证门槛推进。
- 恢复命令中位数 145.92 ms 与共享 exec 至 ready 中位数 1074.73 ms 属于不同阶段口径。任务验收比较完整到可接单的配对准备耗时。

## 规范入口

- `.trellis/spec/orchestrator/backend/account-runtime-v3.md`：账号环境、原生进程池与内核切换生命周期。
- `.trellis/spec/runtime/backend/runtime-contract.md`：固定来源、原生 ready、会话隔离、唯一提交及执行体封存。
- `.trellis/spec/runtime/backend/logging-guidelines.md`：实际 TLS、进程归属及诊断证据层级。
- `.trellis/spec/gateway/backend/service-architecture.md`：NativePool、容量、截止、取消及准备阶段。
