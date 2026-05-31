# 扩充 topic 题库并随机出题 - 设计

## Technical Design

本任务保持现有题库数据模型不变：`topics.md` 仍作为题库 seed 文件，SQLite `topics` 表仍使用 `no/title/description/category/enabled/deleted_at` 等现有字段，不新增表字段，不调整 topic CRUD 契约。

题库内容设计采用“连续编号 + 分类追加”：

- 保留现有 1..200 题编号和内容。
- 新增 201..300 共 100 题，使用现有 `- [ ] N. **标题**：描述` 格式，兼容 `_ITEM_RE` 解析。
- 新增分类放在现有第十六类之后，保持 Markdown 二级标题格式，避免影响已有分类和编号。
- 每条描述聚焦真实用户场景、核心主链路、自然扩展点和可观察结果，不写成长篇 PRD，也不新增结构化字段。
- 题目描述不指定技术方案、表结构、组件拆分或测试框架，避免把 bench 变成按固定实现模板执行。

默认 prompt 继续由 `orchestrator/main.py` 的 `build_topic_prompt(topic)` 生成，但本次方向是精简而不是强化：

- 入参仍是 topic dict，返回仍是字符串，不改 API 调用方。
- 保留标题、分类、描述三段上下文。
- 常驻要求只保留可运行 MVP、启动方式、验证方式、关键取舍说明。
- 不把“临近超时停止扩展、补齐最小可交付、输出最终总结”放进默认 topic prompt；这类行为由 worker 的 `TIMEOUT_WRAPUP_PROMPT` 在接近超时时注入。
- 不新增题目级实现策略、技术栈偏好、过度架构提醒或大型依赖限制，避免 benchmark 被统一提示词过度塑形。

bench 控制边界：

- 参赛 prompt 只表达任务本身和最小交付回报要求。
- harness 负责超时时间、临近超时收尾、思考预算、工具权限、网络/容器环境、transcript 和产物采集。
- evaluator / judge 应在后续独立任务中设计，维度可包括可运行性、主链路完成度、质量、验证、用户体验和收敛能力；本任务不实现评分。

Claude Code 思考预算默认值统一改为 `max`：

- `orchestrator/main.py` 中 `CLAUDE_CODE_EFFORT_LEVEL` 的环境变量兜底从 `xhigh` 改为 `max`。
- `images/worker/entrypoint.sh` 的兜底默认值同步改为 `max`，避免绕过 orchestrator 或单独运行 worker 时行为不一致。
- `docker-compose.yml` 和 `docker-compose.remote.yml` 的环境变量默认表达式同步为 `${CLAUDE_CODE_EFFORT_LEVEL:-max}`。
- `.env.example` 和 README 文案同步说明默认是 `max`，仍可通过 `.env` 覆盖为更低预算。

随机顺序放在批次创建层实现：

- `/api/topics` 继续 `ORDER BY no`，保障题库浏览、编辑和搜索稳定。
- `/api/task-batches` 接收前端选中的 topic id 后，查出 topic 行并在写入 `task_batch_items` 前随机打乱。
- `Scheduler._execute_batch()` 继续按 `task_batch_items.id` 执行，因此同一个批次创建后顺序固定，方便追踪和恢复；不同批次会重新随机。
- 不引入全局抽题历史、跨批次去重或策略配置。
- 当前最小实现只持久化随机后的 `task_batch_items` 顺序；后续如要严格复现实验，可新增 `shuffle_seed` 字段，本任务不做 schema 扩展。

## Compatibility

- 已有 task/run 的 `topic_id` 引用不变。
- 首次启动仍能从 `topics.md` seed 全量 300 条。
- 已经 seed 过的数据库仍需通过 `scripts/sync-topics-db.py --apply` 按 `no` upsert 新题库。
- WebUI 不新增复杂控件，只更新用户文案说明批次会随机执行选中题目。
- 思考预算仍通过同一个 `CLAUDE_CODE_EFFORT_LEVEL` 环境变量下发，不改变账号、worker 或 profile 数据结构。

## Rollout / Rollback

本地先验证 Markdown 解析、编号连续性、后端语法和批次插入顺序逻辑。远程或已有实例同步时，先备份 `data/db.sqlite`，再运行现有同步脚本写入 201..300。

回滚时恢复旧版 `topics.md` 和后端代码；如已经同步数据库，需要用同步前的 SQLite 备份回滚。
