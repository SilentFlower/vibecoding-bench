# 扩充 topic 题库并随机出题

## Goal

将 `topics.md` 题目库从 200 道扩充到 300 道，并精简默认题目 prompt，避免用过多常驻规则干扰 benchmark；同时避免题库按固定编号顺序执行，降低连续批量任务的题型偏序影响。

## Background / Known Context

- 用户希望扩充 topic 题目库。
- 用户明确希望题目库新增到 300 道。
- 用户对提示词不满意，并确认不希望默认 topic prompt 加太多规则。
- 默认 topic prompt 应尽量保持中性，只提供题目上下文、可运行 MVP 目标、启动/验证/取舍总结要求。
- 真实 bench 设计应遵循“参赛 prompt 尽量薄，harness / evaluator 承担控制和评价”的原则，避免默认 prompt 把所有 agent 塑造成同一种解法。
- “如果时间接近超时，请立即停止扩展功能，补齐最小可交付状态，并输出最终总结”更适合保留在 worker 的超时收尾 prompt 中，而不是每个 topic 的默认 prompt 中。
- 用户希望题目库不要按固定顺序执行，而是随机出题。
- 用户希望 Claude Code 思考预算默认值从 `xhigh` 改为 `max`。
- 当前 `topics.md` 已包含 200 个题目，编号 1..200；本次需要新增 201..300。
- `orchestrator/main.py` 的 `build_topic_prompt()` 当前包含 7 条常驻要求，本次应做精简和去噪，而不是继续强化。
- 题库 API 当前按 `topics.no` 排序返回，适合题库浏览和编辑。
- 批次创建时当前按数据库返回的 topic 行顺序插入 `task_batch_items`，调度时按 `task_batch_items.id` 执行，因此批量运行存在固定顺序。
- 当前 `CLAUDE_CODE_EFFORT_LEVEL` 默认值分布在 `orchestrator/main.py`、`images/worker/entrypoint.sh`、`docker-compose*.yml`、`.env.example` 和 README，默认均描述为 `xhigh`。

## Assumptions

- 题库浏览、编辑、搜索仍保持按编号稳定展示，随机只影响批次运行顺序。
- 随机执行应发生在批次创建时：同一个批次创建后顺序固定，便于追踪；新批次重新随机。
- 不在本次引入复杂的“全局抽题历史 / 抽完一轮再洗牌”机制，除非用户明确要求。

## Requirements

- 扩充 `topics.md` 到 300 道题，新增 201..300 必须延续现有 Markdown 格式、连续编号、分类标题和简短描述风格。
- 新增题目应更偏真实用户场景，避免只有技术名词堆砌；描述需要能引导 AI 产出可运行 MVP。
- 精简默认 topic prompt，避免加入过多实现策略、超时策略或 benchmark 干预规则。
- 超时收敛逻辑保留在 worker 层的 `TIMEOUT_WRAPUP_PROMPT`，不作为每个 topic 的常驻默认 prompt。
- bench 控制项保留在 harness 层：超时时间、临近超时收尾、思考预算、工具权限、网络/容器环境、transcript 和产物采集，不写入默认 topic prompt。
- 题库描述应像真实需求 brief：包含用户场景、核心主链路、自然扩展点和可观察结果，但不指定技术方案、表结构或组件拆分。
- 批量创建任务时，选中的 topic 应随机写入批次执行队列，避免按编号或 UI 顺序固定运行。
- 单题创建、题库浏览、题库编辑和历史 task/run 引用不应受到随机顺序影响。
- 已运行过的实例仍可通过现有 `scripts/sync-topics-db.py --apply` 同步新版题库。
- README、WebUI 静态文案和题库统计需要从旧数量同步到 300，避免用户看到 100/200 等过期描述。
- Claude Code 思考预算默认值改为 `max`，但保留通过 `CLAUDE_CODE_EFFORT_LEVEL` 环境变量覆盖的能力。

## Acceptance Criteria

- [ ] `topics.md` 校验通过，题目总数为 300，编号 1..300 连续且无重复。
- [ ] 新增题目能被现有 `load_seed_topics()` / `scripts/sync-topics-db.py` 解析。
- [ ] 默认 topic prompt 精简为题目上下文、可运行 MVP、启动方式、验证方式和关键取舍说明。
- [ ] 默认 topic prompt 不包含临近超时收尾要求；超时收敛仍由 worker 的超时收尾 prompt 负责。
- [ ] 新建批次的 `task_batch_items` 插入顺序不再固定跟随 topic 编号或前端选择顺序。
- [ ] 题库列表 API 和前端展示仍按编号稳定展示。
- [ ] 相关 README 或界面文案同步说明批次会随机执行选中 topic。
- [ ] README / WebUI 中面向用户的题库数量文案更新为 300。
- [ ] `CLAUDE_CODE_EFFORT_LEVEL` 在本地 compose、远程 compose、orchestrator 默认值、worker 默认值、`.env.example` 和 README 中统一为默认 `max`。

## Definition of Done

- 校验题库解析命令通过。
- 后端语法检查或可用测试通过。
- 涉及的前端/文档文案保持中文。

## Out of Scope

- 不新增复杂抽题策略配置页。
- 不实现跨批次去重、账号级抽题历史或失败题目自动重排。
- 不重构题库存储模型。
- 不实现 evaluator / judge / 自动评分体系；本任务只保持 prompt 与产物采集对后续评价友好。
