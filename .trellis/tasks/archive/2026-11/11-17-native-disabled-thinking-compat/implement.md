# Native disabled thinking 实施计划

## 实施顺序

- [x] 记录用户对无真实样例仍继续适配的决定，冻结当前源码、设置及双版本执行体证据范围。
- [x] 用原生执行体和回环夹具核对disabled及adaptive构造与发送，建立前后对照。
- [x] 复用现有开关/精确名单和最小改写函数，接入native业务副本。
- [x] 核对签名修复、缓存布局、TTL、ingress及cc_prepared归属。
- [x] 同步相关注释、合同及验证证据。

## 验证矩阵

- 开关off/on、命中/未命中完整模型名、含[1m]的完整模型名。
- thinking省略/disabled/enabled/adaptive及附加子字段。
- 带签名历史、签名修复重试、缓存断点和TTL组合。
- 280/293、普通API/完整原生输入、tool_choice组合。
- 原始ingress与实际出站改写值、唯一业务调用及非零CCH。

## 验证命令与通过条件

services/gateway：cargo test --locked --lib service::rewriter::tests::disabled_thinking 和对应新增native用例，最终cargo test --locked。services/runtime：bun run typecheck、bun test tests/unit，适配器受影响时使用bun run test:native的隔离入口。真实执行体与回环TLS证据独立列出；本轮验收核对280/293的实际构造和发送、配置控制、诊断归属及重试一致性。真实上游复现与实际兼容效果列为后续验证项。

## 依赖与回滚

排在R2/R3之后，以当时实际发送路径为准实现；默认开关保持现值。关闭开关用于业务回退，代码补丁和共享合同变化单独记录。外部真实调用或生产数据访问先遵循对应授权边界。

## 当前验证证据

- 280/293实际原生回环通过：33次模型发送，分别为15/18次。覆盖普通API与完整原生输入、关闭/开启/未命中/再次关闭、原始入站与cc_prepared、TLS实收、签名修复及学习后首发、429退避期间配置冻结，结合sub2api和1h TTL验证。日志及报告为/tmp/native-thinking-tls-current.log、/tmp/native-thinking-tls-current-report.json。
- 验证使用与当前正式清单匹配的accepted-current双版执行体，测试源码沿59e0c26f加本项精确补丁。293分发SHA为9a5eb46175762bbcc84ad069601c9626b35a9bbf41aa53f08e96d32fdcf3198a，280为21e7c3f85c698138c027622e1abc1f20b4f684847cce000d5f3ba9ecd9654229。
- Rust全量949项通过、13项条件用例忽略：/tmp/native-thinking-rust-current-full.log。随后仅将新增方法的类型拼写改为已有显式导入Value；最终6项定向回归通过：/tmp/native-thinking-focused-final.log。
- 运行时类型检查和200项单元测试通过：/tmp/native-thinking-runtime-typecheck.log、/tmp/native-thinking-runtime-unit.log。最终格式检查通过：/tmp/native-thinking-fmt-final.log。
- 补充运行时联调最终50项通过，其中隔离常驻池子批次20项通过，真实上游请求为0：/tmp/native-thinking-runtime-integration-final.log及测试副本artifacts/local-pool-offline-proof.json。首次批次有一项forwarder_start启动错误；定向复测通过后完整重跑通过，原始记录保存在/tmp/native-thinking-runtime-integration.log和/tmp/native-thinking-runtime-integration-retry.log。
