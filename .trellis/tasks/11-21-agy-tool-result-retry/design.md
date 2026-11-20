# 设计

## Sub2API 的转发行为

- 官方公开主分支 `328db26` 的 Gemini 路由按会话信息选账号，把本次正文转发给上游，并在转发结束后释放账号槽。反重力直连为每次入站生成新的上游 `requestId`。相同正文重新到达会进行一次新转发。会话摘要保存账号归属。 [入口转发](https://github.com/Wei-Shaw/sub2api/blob/328db26f450edbdf9f8d4344a3ea903ac6396842/backend/internal/handler/gemini_v1beta_handler.go#L743-L770) [上游请求信封](https://github.com/Wei-Shaw/sub2api/blob/328db26f450edbdf9f8d4344a3ea903ac6396842/backend/internal/service/antigravity_gateway_service.go#L711-L732) [会话存储](https://github.com/Wei-Shaw/sub2api/blob/328db26f450edbdf9f8d4344a3ea903ac6396842/backend/internal/service/gateway_service.go#L1100-L1116)
- 本项目已经将工具结果交给原生进程并确认接续提交。重试绑定到实际受理的请求和帧，保留此前已经发出的下一轮工具 ID。 [原工具收尾](../../../services/gateway/src/service/gemini.rs#L102) [发送边界](../../../services/gateway/src/service/gemini.rs#L995)

## 将重试绑定到已受理的接续轮

1. 沿 `GeminiService::continuation` 对首次工具回填匹配当前令牌、账号、模型、完整历史和实际模型调用。唯一领取的接续轮按已鉴权令牌标识、原账号、公开模型和整份入站 JSON 的确定性摘要登记对应响应。读取前核对当前账号允许和屏蔽规则。新待回填轮和旧已受理轮若指向多个原请求，保持拒绝。历史归一仍只用于实际发送，比较采用归一前入站。
2. 原工具完成和接续模型发送沿用 `ContinuationClaim::finish`、已确认回执、实际目标监督器及现有时间预算。登记和首次领取在同一归属判定中完成，让并发重试共同观察一笔发送。可重试的发送前失败释放登记，保留已有的原工具完成回执。跨过原生发送后的状态未知按首次失败收口并保持归属记录，重试消费同一结果。
3. 在工具续轮响应的现有帧交付边界发布可重读的有序帧和实际终态。原生确认后登记的新工具轮须先于包含 `functionCall` 的帧交付。复用原先的 SSE 聚合和 JSON 聚合。跟随者从首帧读至原终态，慢读与断连不阻塞原发送。最后一个读取者离开时沿正常取消边界处理。已交付的工具收口沿现行监督器路径继续。
4. 响应登记使用原接续轮的单调生成截止。逐帧共享存储在有界进程内缓冲，使用已有合法帧和聚合大小检查与可回收的总预算。每个响应最多保存一份帧序列，重试方保留读取位置。容量无法保存完整结果时，保持首笔响应与一次发送记录，重试得到明确的暂时不可用。用并发大响应复核预算和淘汰。缓存到期或进程退出时回收，登记不持有原许可、发送器或凭据。

## 诊断与兼容

- 重试建立独立 HTTP 根记录，以可缺省原请求关联字段标记重读，沿既有摘要边界保留状态和阶段。内容采集按原设置执行。重试记录零发送尝试，相关正文与工具结果不进入持久重试状态或普通日志。 [请求记录合同](../../spec/gateway/backend/settings-database.md#scenario-agy多平台请求记录与受控阶段采集)
- 私有 `finish_tools`、凭据换代、账号并发许可和 Python 校验维持原合同。旧网关与现行 worker 可互换使用。回退停止当前进程内的重读功能。 [AGY 原生合同](../../spec/orchestrator/backend/account-runtime-v3.md#scenario-agy账号运行环境与gemini业务接入)
