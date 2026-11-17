# Native 429 处理设计

## 边界与现状

GatewayService::handle_request_inner 是本项主入口。账号选择、并发/RPM、请求截止、额度观察和限流分类继续使用当前公共实现。native 分支提前返回，使其跳过外层429循环；finish_forward_response 只投影退避时长，使 PassThrough 在原有外层丢失。参考 AccountSelectionContext、RateLimitDecision、SchedulingRequest、GatewayAccountAdmission 和 SlotReleaseGuard 的现有定义。

## 处理流程

1. finish_forward_response 在完整缓冲429后保持原有被动额度采集和 AccountService::handle_rate_limit_with_context 分类；响应扩展携带完整分类结果。
2. 两种发送入口在交付响应前消费同一分类。以现有私有类型承载决策并收敛有限的共用处理，避免复制整个发送管线。
3. PassThrough 直接返回当前429；Quarantined 和 RetryOtherAccount 按原循环排除当前账号并保留末次响应；RequestBackoff 复用账号软退避及每账号一次重试记录。分类调用失败的既有兜底行为在特征测试中冻结。
4. native 的签名修复仍由 forward_native_messages 收口，其返回响应再进入429分支。非429响应保持 SlotGuardBody、UsageCapture、策略拒答观察和诊断归属。
5. 重试前释放当前槽位及凭据活动。重新选号、准备和发送复用原 SchedulingRequest 的截止，计入新的真实 attempt；模型和原始业务输入在同一请求内保持稳定，目标账号身份按该次账号重建。

## 兼容与状态

产品方向为全 native。现有公共选号合同继续作为基准，执行以实际配置账号为准；本项不引入新的跨后端产品机制或账号迁移。Fable开关关闭、精确模型匹配、普通5h/7d优先级、API Token allow/block和候选耗尽返回顺序沿用原有规则。当前规范中的Fable模型描述与源码5/5.1范围核对后同步事实。

会话绑定继续在现有 claim/admit 和真实提交位置处理。模型级限流保持账号全局状态，账号级拒绝按现有分类记录冷却。临时限流10秒、同账号一次退避重试，测试用受控时钟验证；原准入期限优先。

## 风险与回滚

关键风险为重复提交、旧许可占槽、截止被重置、绑定迁移和诊断归属漂移。对完整429的重试与超时/断线提交未知分别验证。此项代码改动可按精确补丁回退；账号冷却状态依旧服从已发布的真实上游观察，代码回退不伪造状态撤销。
