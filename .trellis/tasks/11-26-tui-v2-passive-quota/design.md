# V2 请求被动额度采集设计

## 链路与归属

受管 V2 用当次账号凭据经容器内 `/internal/send` 获取实际模型响应。该入口复制上游响应头，并为编排层写单独的 API 观测证据。账号页读取网关 `Account.usage_data` 和 `usage_fetched_at`。由同一 V2 回包交付额度样本，可以在当前账号绑定和提交生命周期内回写，中央网关也能及时读到远程节点请求的观察。[受管模型发送](../../../images/account/tui_sender_launch.py#L237) · [账号发送器](../../../services/gateway/src/service/runtime_transport.rs#L3019) · [节点转接](../../../services/orchestrator/cluster_transport.py#L323)

1. Python 事件源在受管请求取得上游 HTTP 200 或 429 时抽取额度。白名单限定 `anthropic-ratelimit-unified-` 下 `5h`、`7d`、`7d_oi` 的 `utilization`、`reset`、`status` 和 `surpassed-threshold`。使用可选的 `quota_headers` 控制帧字段保留原始字符串。正常 SSE 和 JSON 在各自首个控制帧携带观察。首帧前的 429 随既有受管错误来源携带观察。样本与本次预留绑定，源端在发布模型首帧前完成采集。
2. 同一个 Unix 连接的 sender 按原预留与受管凭据校验归属，在私有 HTTP 回包中交付白名单额度头。旧事件源省略该字段。仅采信受管模型的 200 和 `managed_oauth_http` 来源的 429。节点转接沿现有私有 HTTP 头传输。
3. 网关在 `tui_public_response` 重建公开响应之前，从已绑定的受管 sender 回包解析观察。共用 `extract_passive_usage`、`extract_rejected_passive_usage_windows` 与 `AccountService::update_passive_usage`。按照现有规则异步合并进原账号。数据库写入失败记录诊断，模型结果照常交付。窗口解析、重置判断及显示字段沿现有合同。

## 兼容与边界

- 私有观察字段可选。新旧事件源、sender 和网关混用时，可按现有格式完成投递。收到完整样本的新网关更新快照。两端完整支持后具备自动更新能力。
- 额度旁路受现有 4096 字节 Unix 控制帧预算约束。发送端只打包该预算内的已知头，忽略重复或不能安全传输的值。接收端按固定名单构建内部 HTTP 头。合法窗口仍由现有解析器独立判定。
- 本地开发提供方、本地生成错误以及外部调用方传入的同名头都没有官方额度写入权限。账号取自当前已验证的请求绑定。公开响应继续由现有投影函数生成。
- 真实 429 继续按 V2 现有方式返回。额度持久化复用逐窗口标记，供后续调度和页面使用。同轮模型重试、换号和本地拒绝沿原有路径。
- 网关继续使用同一份账号快照供调度和管理页面读取。数据库表结构沿用现有定义。回退代码与制品后，旧版本从已保存的同结构额度继续读取。
