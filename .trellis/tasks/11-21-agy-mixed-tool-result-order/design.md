# 设计

## 活跃工具轮

- `GeminiService::continuation` 继续校验 Token、原账号可见性、原历史和入站模型。`match_tool_turn` 继续核对模型部件的调用名称、参数及存在的 ID，并返回本轮结果与调用的配对位置。
- 对已校验完整的响应批次先按显式 ID 及支持的 ID 别名占用调用位置。同一位置只能领取一次。随后按客户端回填出现顺序为缺 ID 项领取同名组内尚未匹配的最早调用。收齐后按原调用索引传给原生工具执行。显式 ID 指向的结果先占位，防止前面的无 ID 项取走它。
- 保留真实 ID、函数名和别名的原校验，复用 `runtime_tool_contents` 已有的原生历史归一。如果结果以真实 ID 配对但客户历史省略了对应调用的 ID，私有历史也补入已核实的 ID。原客户端正文继续用于归属和重读摘要。业务错误沿原原因码返回。 [续轮入口](../../../services/gateway/src/service/gemini.rs#L787)
- Sub2API 的 Gemini 直连将原有 `functionResponse` 数组随请求封装发往反重力。Flower2API 的发送器需要本地完成待回填工具调用，因此两端按本节规则核实配对。 [Sub2API 直连源码](https://github.com/Wei-Shaw/sub2api/blob/328db26f450edbdf9f8d4344a3ea903ac6396842/backend/internal/service/antigravity_gateway_gemini.go#L128-L177)

## 原生接续与历史

- `continuation_results` 和 `native_history` 共用 Python 批次匹配。前者把结果排序到实际调用索引。后者在本轮结果收齐时完成配对并按原调用顺序生成 Cortex 工具步骤，允许现有的连续多个用户内容承载一个工具轮。
- 历史中的文本、图片、思考签名和已明确识别的旧 ID 格式沿已有结构校验。批次未收齐时遇到下一条完整业务消息仍沿原拒绝。新的组内顺序规则沿用已有同名无 ID 的顺序前提，并允许区分不同函数名。 [历史导入](../../../services/orchestrator/agy_runtime/gemini_contract.py#L142) [原生接续](../../../services/orchestrator/agy_runtime/gemini_contract.py#L286)

## US 更新

- US 当前 `v1.28.0` 已装机。请求在网关到达发送器之前拒绝。账号级 `stage-agy-kernel` 只覆盖账号运行时。两端使用同批 control/account 镜像交付，走已签名发行和既有 US 系统更新入口。
- 现有更新器预检候选与在途工作，按原流程准备、安装和恢复，并检查控制服务与账号后台更新。以失败前实际接单的账号 15 为起点，安装前读取接单账号和环境归属。切换后核对运行时版本、实际容器批次、网关健康和相关账号发送器就绪。用户本人用新工具轮复测，生产只读观察实际请求。 [受信发行流程](../../spec/platform/deploy/platform-online-update.md#scenario-构建与手动发布解耦及-v3-升级连续性) [本机账号后台更新](../../spec/platform/deploy/platform-online-update.md#scenario-分步下载与本机账号后台更新)
