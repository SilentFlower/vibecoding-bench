# 实施与验证计划

## 实施顺序

- [x] Brief 评审生效后启动任务，进入 trellis-route(target=implement)，按 trellis-before-dev 读取相关规范。
- [x] 复核 RuntimePayload、worker/job 错误出口、Rust execute、sender 入口与可达日志定义。
- [x] 实现集中安全摘要、可选事件合同和实际阶段记录，保持原始状态与取消语义。
- [x] sender 初始化日志，独立校验诊断，记录请求及进程关联字段，审查可达日志。
- [x] 跨语言验证新旧事件、非法摘要、秘密、循环、截断；实际 sender 入口验证日志落地。
- [x] 完成定向原生离线验证及必要完整检查，记录配套内核发布前提。
- [x] trellis-route(target=check) 进入 Check-All，修复及重检后继续 Spec 评价和精确 Push 计划。

## 验证命令

gateway 模块：

```bash
cargo fmt --check
cargo test --locked
```

runtime 模块：

```bash
bun run typecheck
bun test tests/unit
bun run test:integration
bun run test:native
```

原生验证沿现有构建脚本与 unshare 回环网络，使用合成身份、本地 TLS 服务和代理；拒绝、重置/提前断开、TLS 错误及 cause 验证核对实际发送次数。真实 sender 测试使用独立临时配置和日志。

## 范围与回退点

- gateway：src/bin/account-sender.rs、src/service/native_runtime.rs、必要安全投影模块与测试。
- runtime：src/shared 合同/异常摘要/解码、runtime/293 worker/job 和对应测试。
- 文档：私有协议说明、gateway 服务架构、runtime 日志规范。
- 诊断为可选字段，旧内核兼容由测试保护。源码回退恢复原日志行为；制品与生产选择沿独立发布流程。
- 保留本轮前已有工作区改动及其他任务资料。本轮采用内联实现和检查。
