# Topic 自然提示词变体 - 执行计划

## Implementation Checklist

- [x] 在 `orchestrator/main.py` 用分类风格、需求片段、交付片段、结果片段和布局片段替换完整自然模板集合。
- [x] 增加分类风格解析、12 候选组合、topic 字段归一化、4 字符 n-gram 相似度和低相似候选选择 helper。
- [x] 增加只读近期 prompt 指纹查询，覆盖非批次 tasks 与 task batch items，不修改 schema。
- [x] 扩展 `build_topic_prompt()` / `_resolve_topic_prompt()` 的可选近期指纹参数，保持 canonical 和自定义覆盖短路。
- [x] 单任务、批次、养号和显式 natural 抓包接入最多 64 条近期指纹；批次只查询一次，并用固定长度 deque 逐项追加已选指纹。
- [x] 更新 `orchestrator/test_main.py`，覆盖组合空间、四类交付语义、21 分类映射、归一化、低相似选择、近期查询和批次内去同构。
- [x] 保留并回归 DTO 默认值、非法模式、canonical 稳定、自定义覆盖和养号存储/下发一致性测试。
- [x] 搜索全部 `build_topic_prompt()`、`_resolve_topic_prompt()` 和 prompt 持久化调用点，确认无遗漏和重复生成。

## Validation

- `python3 -m py_compile orchestrator/main.py orchestrator/test_main.py`
- `cd orchestrator && python3 -m unittest test_main.py`
- `node --check webui/app.js`
- `git diff --check`
- 遍历 `load_seed_topics()` 的分类集合，确认全部映射到已定义风格。
- 构造高相似/低相似候选，确认选择器稳定选择较低风险候选。
- 构造批次多 topic，确认后续 item 的比较样本包含本批次已生成 prompt。
- 对真实 helper 做聚焦微基准，确认 `12 × 64` 比较保持毫秒级且批次窗口不会超过 64。
- 核对 canonical 输出与第一阶段文本逐字一致。
- 进入 Full Check-All，反向检查 WebUI -> DTO -> 生成器 -> SQLite -> Scheduler -> worker 数据流。

## Risk And Rollback Points

- 片段组合可能产生语法不顺或信息重复；测试必须抽样多个组合并检查精确语义标记，人工复核代表性分类输出。
- 相似度归一化顺序错误会残留 topic 正文，必须按字段长度降序替换并单测标题包含于描述的情况。
- 批次若每项重复查询历史或无限追加比较样本会放大开销；必须创建前读取一次，并使用 `deque(maxlen=64)` 滚动更新。
- 相似度只是择优，不得因查询为空或候选分数相同阻塞任务创建。
- 不修改 schema；若实现需要持久化组合 ID 或模式，应回到规划重新评审。

## Review Gates

- 实现前刷新 `brief.md` 并完成第二阶段 planning review。
- 实现后先跑聚焦测试，再进入 Trellis Check-All。
