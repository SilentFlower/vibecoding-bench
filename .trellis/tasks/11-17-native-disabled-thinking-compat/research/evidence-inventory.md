# R4 复现证据核对

## 已核对的实现事实

- 既有设置默认关闭，默认精确模型名单为`claude-fable-5`：`services/gateway/src/store/settings_store.rs:77`。
- 原改写仅修改顶层`thinking.type`，模型按完整字符串相等匹配：`services/gateway/src/service/rewriter.rs:6104`。
- native账号在旧改写配置读取前分流：`services/gateway/src/service/gateway.rs:2467`、`:2629`。
- native首次发送与签名修复共用`forward_native_messages_once`，原始入站与实际业务副本已分别传递：`services/gateway/src/service/gateway.rs:3796`、`:3906`。
- 普通API的原生构造器对恰为`{type:'disabled'}`且原生结果省略thinking的情况补齐原值：`services/runtime/src/runtime/293/job.ts:196`。这项保留输入合同与disabled转adaptive是两种独立行为。
- `services/runtime/tests/native/tls-verifier.test.ts:190`起的既有用例覆盖disabled的JSON/SSE和工具历史保留；这组用例使用模拟上游，证据类别是原生构造与发送保留。

## 真实上游证据与后续验证

- 本次按disabled拒绝文本及改写设置检索任务Markdown、项目文档和部署验证材料，并核对匹配结果。当前R4三件套仍将真实上游失败记录标为待核对。
- `trellis mem search 'thinking.type=disabled' --platform codex --since 2026-11-14 --limit 5 --json`返回本会话的规划讨论。该范围内的命中内容为功能盘点和复现前置约定。
- 需要关联同次请求的模型完整ID、280/293源版本、原始thinking形状、失败发生阶段、HTTP状态与脱敏拒绝原因。
- 优先使用已有失败请求ID或脱敏历史记录。普通API构造拒绝、模拟400/422及真实上游拒绝分别登记。
- 2026-11-17用户确认目前没有可提供的真实失败请求ID或脱敏报错，随后明确要求继续适配。真实上游复现调整为后续验证项。
- 本轮交付证据以固定280/293原生执行体的构造、实际TLS发送和配置控制为准。后续取得真实记录时补充源版本、模型、阶段、拒绝原因及兼容前后效果。
