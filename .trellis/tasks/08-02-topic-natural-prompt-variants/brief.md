# Brief — Topic 自然提示词变体 natural-v2

## Goal

- 把自然模式从 6 个完整模板升级为低指纹的组合式生成，同时保持题目语义、交付强度、可追溯性和 canonical benchmark 可比性。

## Scope

- 用分类风格、需求表达、可运行交付、结果说明和布局片段组合自然 prompt，不新增用户可见模式。
- 将 21 个现有题库分类归并为工程、产品、数据/AI、创意和通用回退风格，规则只改变语气。
- 每个自然 prompt 随机抽取 12 个不同候选；每个候选都包含 title、category、description，并保留可运行、启动、验证和主要取舍四类语义。
- 把 topic 专属字段替换为占位符，生成 4 字符 n-gram 指纹，与最多 64 条近期持久化 prompt 比较，选择最大相似度最低的候选。
- 从现有 `tasks.prompt` 和 `task_batch_items.prompt` 只读加载近期样本；批次只查询一次，并用 `deque(maxlen=64)` 加入本批次已选指纹。
- 单任务、批次、养号和显式 natural 抓包接入相似度过滤；canonical 和自定义 prompt 继续短路，不读取历史。
- 更新后端单元测试，覆盖组合空间、分类映射、语义完整性、归一化、低相似选择、近期查询、批次窗口和既有回归契约。

## Non-Goals

- 不使用外部 LLM、embedding、向量数据库或逐题人工变体。
- 不新增数据库列、迁移、变体 ID、模式元数据或历史回填。
- 不修改 WebUI 字段与默认值、`topics.md`、worker 原样注入和调度 payload 结构。
- 不把公共完成协议移到 worker，也不保证统计意义上的绝对不可识别。

## Key Context

- `images/worker/entrypoint.sh` 会原样注入 `TASK_PROMPT`，部署规范禁止 worker 追加 bench 完成协议，因此自然候选必须自行保留完整交付语义。
- 最终 prompt 仍只生成一次并持久化；`tasks.prompt` / `task_batch_items.prompt` 是调度、恢复和查看的唯一事实来源。
- 相似度查询是无 `_db_lock` 的参数化只读 SQL；自定义覆盖和 canonical 不承担该开销。
- 性能预算固定为 12 候选 × 64 历史 × 4-gram；真实 helper 本地复测约 2.95ms/item，100 item 约 0.30 秒，600 item 约 1.77 秒。
- 查询为空、候选平分或历史包含自定义/canonical prompt 都不能阻塞任务创建。

## Acceptance

- 自然模式不再暴露少量固定整段模板或唯一收尾句，且所有候选语义完整、表达自然。
- 21 个现有分类全部映射到已定义风格或通用回退，未知分类也能生成。
- topic 专属文本被正确归一化，高相似历史存在时选择器优先返回低相似候选。
- 批次只读取一次历史，比较窗口始终不超过 64，并包含本批次近期已选 prompt。
- canonical 文本逐字不变，自定义覆盖、DTO/WebUI 默认值和养号存储/下发一致性无回归。
- 无 schema、worker、题库同步或外部依赖变更；Python 编译、后端单测、JS 语法和 Full Check-All 通过。

## Next Step

- Full Check-All 通过后进入 `trellis-update-spec`，同步 topic prompt 的 natural-v2 可执行契约。
