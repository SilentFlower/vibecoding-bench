# Native 429 实施计划

## 实施顺序

- [x] 重读当前热路径和工作区差异，确认现有改动归属，建立原有429行为特征测试。
- [x] 扩展现有响应决策载体，覆盖四种 RateLimitDecision，修复原有 PassThrough 丢失。
- [x] native 响应进入共用429决策执行及外层换号循环，保留签名修复和非429响应生命周期。
- [x] 验证账号资格、Fable阈值、软退避、会话 claim、准入截止、末次429和诊断 attempt。
- [x] 补齐规范事实与测试证据，完成 Check-All 和 Spec 评估。

## 验证矩阵

| 场景 | 预期 |
| --- | --- |
| native A明确容量429，B成功 | 按规则冷却/排除A，B真实发送一次，账号身份与记录对应 |
| Fable OAuth模型级429 | 切换本次账号，普通全局状态保持现有合同 |
| credits/long context 被分类为PassThrough | 两种路径均单次发送并返回该429正文和必要响应头 |
| 临时429 | 复用10秒软退避；同账号最多一次该类退避重试，槽位在等待前释放 |
| 候选耗尽/准入到期 | 与原有返回优先级一致，所有尝试共用截止 |
| 超时/断线提交未知/已有下游输出 | 保持各自错误边界，429重试机制只消费明确429 |
| 签名修复后429/取消/并发绑定冲突 | 各阶段归属明确，槽位与许可终态正确 |

## 验证命令

先在 services/gateway 使用 cargo test --locked --lib service::account::tests 和 service::gateway::tests 的相关筛选。新增native用例优先扩展回环sender夹具与 tests/native_signature_fixture.py 的隔离方式。真实二进制消费者复用 services/runtime/scripts/testing/cc2api-native.ts 的独立网络命名空间入口，按其已有配置提供已核验执行体。常规单测不能替代该链路证据。

完成本项后运行 cargo fmt --check、cargo test --locked 和 git diff --check；记录既有格式问题并保持精确修改范围。整个任务树后续构建仅在新增变化需要时重跑受影响集合。

## 评审与回滚点

开工前读取本项brief并完成交接门禁，按trellis-route选择执行模式。实现期间保留当前工作区他人改动。Check-All关注真实发送计数、绑定、状态、槽位及deadline。业务变更按已核对文件/补丁独立交付，推送执行按单独Git计划授权。

## 实施验证结果

- `cargo test --locked`：945项通过，12项按环境条件忽略。新增业务透传回归在修复前复现429被换号覆盖为200，修复后通过。
- `python3 services/gateway/tests/native_rate_limit_fixture.py`：21组场景通过，覆盖280/293、换号、Fable、业务拒绝、软退避、期限、取消、绑定、Token范围及未知提交。
- `python3 services/gateway/tests/native_signature_fixture.py`：签名修复回归通过。
- `CCRB_TEST_RATE_LIMIT_ONLY=1 bun scripts/testing/cc2api-native.ts`：使用登记的280/293执行体完成4次隔离TLS实收，独立身份及CCH校验通过。
- `cargo fmt --check`、新增Rust测试文件格式检查、Python夹具编译、runtime的`bun run typecheck`和`git diff --check`通过。
- Check-All采用full深度，CHK/FBK/DOC均为0。规范已补充完整429决策传递、资源释放、原截止及测试合同。
