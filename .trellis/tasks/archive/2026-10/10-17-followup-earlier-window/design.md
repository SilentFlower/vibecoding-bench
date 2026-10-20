# 前移随机补充时间窗口的兼容设计

## 依据与入口

- 已确认产品窗口为 5%～30%，详见 prd.md 的 R1。
- `orchestrator/topic_library.py:168` 的 `sample_followup_timing(messages, timeout_sec, wrapup_sec) -> str` 是普通运行、批次和养号的共用生成入口。
- `orchestrator/topic_library.py:184` 的 `decode_followup_timing(raw, count) -> dict | None` 同时供 Runner 和详情 API 使用；`images/worker/task_followups.py:403` 的 `_process_timed` 在镜像内独立校验时间对象。
- `orchestrator/main.py:3855` 按原运行快照向 worker 传递时间对象及收尾预算。前端已按 offsets_sec 展示实际冻结目标，不依赖固定区间。

## 时间对象与兼容策略

不新增数据库列，沿用 nullable `runs.followup_timing_json`，不改变现有函数签名和公开进度结构。时间对象继续使用 `schema, offsets_sec, timeout_sec, wrapup_sec` 四个字段：

| 时间 schema | 使用范围 | 合法投递区间 |
| --- | --- | --- |
| NULL | 无时间快照的历史运行 | 原阶段模式 |
| 1 | 已冻结的旧定时运行 | ceil(T/10)～floor(6T/10) |
| 2 | 本轮之后创建的新定时运行 | ceil(T/20)～floor(3T/10) |

仅生成入口改为 schema 2；管理端解码和 worker 校验同时支持 1/2，按版本选择上下界。未知版本、类型不符、数量/顺序/范围错误或与执行预算冲突继续明确拒绝，不重新抽签，也不降级旧模式。

时间对象 schema 与阶段文件 schema 分别表达策略和执行证据，不能混用。阶段文件仍为 schema 2，timing_digest 继续对原时间对象规范 JSON 计算。旧对象不增加默认字段或改 schema，原摘要、主会话、时钟和 pending/queued 恢复门禁保持。

## 抽样及收尾

新运行一次性在闭区间内抽取不重复整数秒，排序后与已选正文前缀一一对应；正文前缀和顺序不变，初始需求实际发送后 start 才固定时钟。

用户已批准首次 Brief，并确认降低0次概率的增量分布为0次10%、1次45%、2次45%。三个创建入口共用 `sample_followups`，恢复只读已冻结数组。实现用均匀整数0～99划分为0～9、10～54、55～99三个区间，仅抽一次；候选只有一条时把2次截为1次，形成0次10%、1次90%。没有候选维持空数组且不调用随机数。该边界不新增消息或重抽历史次数，增加100个离散值的完整映射及三入口一致性回归。

有补充时按对应版本的上界预留 5 秒提交/轮询余量，沿用 `min(max(0,原收尾设置), max(0,T-上界-5))`；不修改全局设置。零补充沿用原设置。正常 1800 秒任务原 600 秒收尾保持不变；较短任务使用新上界计算保护。不增加依赖首轮结束、工具调用或内容推断的动态时机。

## 影响文件与验证边界

- 产品实现主要为 `orchestrator/topic_library.py` 与 `images/worker/task_followups.py` 的版本化范围校验；不为仅两个分发环境引入新的共享包。
- 后端回归覆盖三个创建入口、Runner 传参、QuotaGuard 恢复、详情 API、新旧边界与未知版本。
- 正式 driver/tmux 的合成验证同时覆盖新时间 schema 与旧时间 schema；页面用合成运行核对较早 offsets 的展示，复用已有 XSS、暗色/亮色和窄屏检查。
- 不读取真实凭据或发模型请求；原原生 CLI 输入/队列探针可作为机制未变的基线，新版本投递仍须用正式镜像 driver 验证。

## 交付与回退

管理和账号镜像须同批交付。按既有 Actions/v3 流程在空闲窗口部署，保留历史/活动运行；沿用用户不新增服务器备份的约束，保存摘要证据。上线后核对历史 schema 1/NULL 未回填，并验证新镜像能解码 schema 2；不为上线验收主动创建真实模型运行。

旧镜像不能理解新时间 schema 2。回退前先收口或隔离这些新运行及等待记录，保留原时间对象和阶段证据；不把新对象改写为旧版本，不整库恢复。已有运行 `490232362377` 的 schema 1 / 860 秒计划必须原样兼容。
