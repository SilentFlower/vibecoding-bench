# 原生队列附件的证据归一化

## 入口和边界

复用 read_dialogue(path, offset=0, include_queue=False)、_ordered(items, parents)、_evidence(state, project, expected) 及 process(..., timing=None)，不另建扫描器、不改公开 API/数据库结构。主要实现位于 images/worker/task_followups.py，管理端继续只读有限状态摘要。

## 原生输入契约

识别 type=attachment、attachment.type=queued_command；确认 sessionId 对应当前文件，非旁支/元记录，具有可追溯 uuid/parentUuid，prompt 为字符串，commandMode=prompt、origin.kind=human、humanTurn=true。复用 _matches_input 精确比较原冻结正文或完整合法粘贴包装。未知来源/形状不猜测，不从 rendered 或工具文字抽取输入。

有效附件在公共解析结果归一化为用户输入，保留原 uuid/parentUuid、文件字节 key/end 及时间；父链优先于落盘和时钟。enqueue 仅入队，remove 不代表消费。tool_use、synthetic/API 错误和非正常回复过滤及稳定窗口保持。

## 状态和兼容

旧阶段 schema 1、定时阶段 schema 2 复用 input_entry/reply_entry，附件 input_entry 指向原附件字节位置，不伪造 user 行、不覆盖原日志。时间 schema 1/2、摘要、started_at 和投递游标保持。

有效附件使 pending/queued 转 consumed，关联稳定最终回复才 completed；两条可共享回复。恢复先复核原附件，再应用未消费队列不重发保护；仅 enqueue/remove 仍拒绝恢复。重复、异会话、丢失/截断和不确定父链保持拒绝；已完成普通 user 仍核验原键。

## 测试与跨层

orchestrator/test_topic_followups.py 覆盖原生消费/完成、双条和混合输入、旧版本、原 queued 恢复、乱序及反向归属；将 helper 真实生成的状态交给 _public_followup_progress 验证计数，尽量不改 main.py。

deploy/v3/fixtures/mock_cli.py 增加忙碌消费写 remove + queued_command 的模式，保持真实键盘/driver；verify_followups.py 增加一条/两条附件和共享回复，保留普通 user 夹具。正式 control/account 同步同一 helper；浏览器/API/SQLite回归确认进度显示。

## 交付与回退

v3 同批两镜像，沿用最终 Actions、自然空闲部署和无新增服务器备份约束；保留 HOME、凭据、历史计划和阶段文件，不改历史 timeout、不重跑/补发。状态结构兼容，但旧解析器不识别附件 input_entry；未完成附件运行不能盲目回退旧 worker，需自然收口并核对证据。

## 风险

宽松识别会误认工具/上下文；用类型、来源、会话、正文、字节边界与父链共同约束。CLI 格式可能变化，本轮只支持已观察的明确形状，未知形状保守处理，正式夹具纳入真实格式。
