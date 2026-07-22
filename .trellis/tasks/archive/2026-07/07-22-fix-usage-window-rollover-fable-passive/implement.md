# 实施计划

## 1. 被动采集与跨周期合并

- [ ] 在 `gateway.rs` 抽取单窗口解析 helper，补充 `7d_oi -> seven_day_fable`，校验 utilization 和 reset。
- [ ] 在 `account.rs` 增加内部观察类型与可注入时间的纯合并 helper，覆盖 `five_hour`、`seven_day`、`seven_day_fable` rollover。
- [ ] 修改 `update_passive_usage` 接收观察类型，并保留未包含窗口及原始 usage 扩展字段。
- [ ] 修改 `refresh_usage`，让显式主动查询结果也经过统一 rollover 合并后落库，同时原样返回最终持久化结果。

## 2. Gateway 与 PrimePoller 接线

- [ ] 成功响应以 `Allowed` 写入被动窗口。
- [ ] 429 响应按窗口生成 `RejectedWindows`，仅真实拒绝窗口保留高位并参与限流；其他窗口继续执行 rollover 保护。
- [ ] PrimePoller 成功和 429 路径使用相同观察类型，不再以“429 会主动查 usage”为由跳过持久化。
- [ ] 更新所有 `update_passive_usage` 调用点和现有调度测试 fixture。

## 3. 删除隐式主动查询

- [ ] 删除 Gateway 的 Fable 延迟刷新常量、上下文、spawn helper 和响应完成触发点。
- [ ] 删除 AccountService 的机会式刷新方法、节流 map、常量与对应测试。
- [ ] 确认 `refresh_usage` 只剩 `UsagePollerService` 和管理端手动接口等显式调用点。
- [ ] 保持 `auto_poll_usage` 过滤条件和手动刷新接口行为不变。

## 4. 自动化验证

- [ ] Gateway 单测覆盖 5h/7d/7d_oi 完整解析、缺失字段、非法数值和异常 reset。
- [ ] AccountService 单测覆盖旧 99/100 + 过期 reset、新 reset + 旧高值被置 0；新周期已下降值被采用；同 reset 后续值正常更新；429 高值可信；`seven_day_sonnet` 不丢失。
- [ ] 429/Fable 调度测试覆盖 `7d_oi` 模型级换号和通用 5h/7d 账号级冷却。
- [ ] 静态搜索确认普通请求链路不存在 Fable 请求后 `refresh_usage` 调用。
- [ ] 运行 `cd cc2api && cargo fmt --check`。
- [ ] 运行相关定向测试，再运行 `cd cc2api && cargo test`。
- [ ] 运行 `git diff --check`。

## 5. 规范同步与质量检查

- [ ] 更新 `.trellis/spec/cc2api/backend/service-architecture.md` 的 OAuth Usage 与 Fable fallback 场景，删除机会式主动刷新要求，补充 `7d_oi` 和 rollover 契约。
- [ ] 通过 `trellis-check-all` 全范围检查，根据结果修复并复检。

## 风险点

- rollover 判断过宽会把新周期真实高用量错误清零，因此只对“旧 reset 已到期、新 reset 推进、成功类样本仍处于高位”启用保护。
- 429 是响应级状态而拒绝是窗口级状态；不能把整份 429 全部视为拒绝，也不能对真实拒绝窗口套用清零规则。
- 主动 usage 返回包含额外字段，合并时不能只保留四个窗口而丢掉 `limits`、`spend`、`extra_usage`。
- Gateway 流式 body 生命周期中删除刷新上下文时，必须保持并发 permit、telemetry 和 stateful cache 完成逻辑不变。

## 回滚点

- 代码可回滚到当前版本；没有 schema 或配置迁移。
- 回滚后会恢复 Fable 请求后机会式 usage 刷新，因此生产回滚需要接受主动调用行为重新出现。
