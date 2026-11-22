# 技术设计

## 会话键解析

解析边界是完成鉴权并拿到原始入站 JSON 后、正文改写和账号选择之前。Claude 使用既有 `metadata.user_id` 提取器，随后读取唯一合法的 `X-Claude-Code-Session-Id`。两入口均支持可选 `X-Session-Id`，协议自带 ID 优先。对新接纳的头复用已有原始 ID 有效性边界（唯一值、完整 UTF-8 不超过 256 字节、非空白且无控制字符）。既有 Claude 正文绑定算法保留升级兼容，原始记录继续按已定义的展示边界校验。网关会话头在网关消费，保持出站协议字段约定。 [原始值解析](../../../services/gateway/src/service/diagnostics.rs#L341) [V3 键域](../../../services/gateway/src/service/v3_scheduling.rs#L488)

纯 API 从请求模型、工具、系统指令与首条有效用户内容取得稳定投影。Claude 读取 `messages[].content`，Gemini 读取 `contents[].parts`，Gemini 省略角色的入站 user 形状沿现有语义处理。规范化 JSON 的对象键与等价空值，保留数组顺序与多模态内容。已知 Claude `cache_control` 装饰按协议结构排除，类型化内容中的正文、图片与工具定义保留自身语义。后续回复、工具回填、stream 与用量选项不参与锚点。复用已解析正文并将稳定投影流式写入摘要，新增计算无需复制整段历史。缺少显式值及有效首条用户内容时按原来的逐请求调度。

以 SHA-256 和确定性字段边界提供匿名键。键空间按平台、已鉴权 Token 与显式/内容来源隔离。Claude 正文和合法会话头使用同一现有显式命名空间，已有行可继续命中。内容回退采用稳定前缀的做法。请求只带新问题、替换开场或改变锚点项时可能得到新键。内容完全一样的两个独立会话可能共享选号结果，支持客户端用显式 ID 区分。

## 选号与并发

1. Claude 将解析出的会话键传给现有 V3 绑定流程。保留与发送许可同事务的 CAS、基于修订号的续租及冲突重选。现有 `session_hash`、封禁和上游 Session 池继续走各自的客户端会话逻辑。方案只接入精确 `/v1/messages` 的 V3 路径。 [Claude 选号](../../../services/gateway/src/service/account.rs#L1656) [发送许可](../../../services/gateway/src/store/scheduling_store.rs#L196)
2. 反重力普通生成从现有 `gateway_session_bindings` 读同键归属，在平台、Token、账号状态、凭据、工作门禁和模型档位约束内优先复用。保留既有请求预算、模型优先档、并发许可和 RPM 算法。若绑定可用而仅有临时容量压力，沿现有粘性等待或本地限流处理。暂停接单期间保留绑定并返回相应的本地结果。 [反重力候选](../../../services/gateway/src/service/agy_account.rs#L207)
3. 反重力复用现有版本条件写入，抽取与发送间隔解耦的绑定原子操作，复用同一表、60 分钟闲置期限和清理循环。校验身份、取得并发许可并准备发送器后，先完成绑定认领，再进入既有 RPM 和私有发送边界。并行冲突在相同截止前释放该候选资源、重读胜出绑定并重选。临时 RPM 竞争失败沿原账号限流。存储不可用时返回既有调度错误。Claude 的发送节拍与绑定依然共事务。 [发送准备](../../../services/gateway/src/service/gemini.rs#L1029) [绑定存储](../../../services/gateway/src/store/scheduling_store.rs#L65)
4. 工具回填的 `ToolTurn` 和已受理回填的重放登记拥有归属权。与当前合入基线对齐这两条路径，携带已验证的会话显示关联，回填和重放不重新选号或凭正文指纹抢走绑定。并发调度冲突只可重试普通请求的发送准备。 [工具回填重试任务](../11-21-agy-tool-result-retry/design.md)

## 诊断与升级

- `RequestDiagnostic.original_session_id` 继续表示本次入站的客户端 ID。增加可选 `derived_session_id` 保存实际解析到的匿名派生键。合法显式 ID 直接用于展示，已验证的工具关联可给缺少本次显式值的请求保留原派生键。两个字段在根摘要一次冻结，换号和上游映射不重写。使用现有 `summary_json` 和管理权限，无需改表或回填。 [诊断数据模型](../../../services/gateway/src/model/request_diagnostics.rs#L40)
- 列表与详情共享同一选择规则。派生值旁用文字标出「网关派生」，复制完整字符串，保留窄屏从详情查看的现有入口。 [页面](../../../apps/web/src/components/RequestDiagnostics.vue#L361)
- 旧程序忽略新增的可选 JSON 字段，Claude 原有绑定仍可由旧程序读取。回退后旧程序按原路径选号，新命名空间的绑定随既有闲置期限清理。工作区内的相邻改动以实际基线为准，尤其是反重力工具重放及账号工作门禁。
