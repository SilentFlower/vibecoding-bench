# 扩充 topic 题库并随机出题 - 执行计划

## Implementation Checklist

- [x] 读取相关 Trellis spec，确认后端 SQLite、FastAPI 和静态前端约定。
- [x] 扩充 `topics.md`：新增 201..300 共 100 道题，并更新标题、使用方式或统计中的数量文案。
- [x] 精简 `build_topic_prompt(topic)`，只保留题目上下文、可运行 MVP、启动方式、验证方式和关键取舍说明。
- [x] 确认默认 topic prompt 不包含临近超时收尾要求，超时收敛继续由 worker 的 `TIMEOUT_WRAPUP_PROMPT` 负责。
- [x] 调整 `/api/task-batches` 创建逻辑，在写入 `task_batch_items` 前随机打乱选中 topic。
- [x] 将 `CLAUDE_CODE_EFFORT_LEVEL` 默认值统一改为 `max`，同步 compose、orchestrator、worker、`.env.example` 和 README。
- [x] 更新 README 和 WebUI 面向用户的题库数量、批次随机执行文案。
- [x] 校验 `topics.md` 可解析为 300 条，编号 1..300 连续，标题、描述、分类均非空。
- [x] 运行后端语法检查和可用的轻量校验。
- [x] 更新 `implement.jsonl` / `check.jsonl`，提供实现和检查需要的 spec 上下文。

## Validation

- `python3 scripts/sync-topics-db.py --topics topics.md --validate-only`
- `python3 -m py_compile orchestrator/main.py`
- 用轻量脚本验证 `load_seed_topics()` 返回 300 条，编号为 1..300。
- 用轻量脚本或 SQLite 临时库验证同一批 topic 的 `task_batch_items` 插入顺序不固定等同于编号顺序。
- 抽样调用 `build_topic_prompt()`，确认默认 prompt 未包含临近超时收尾要求。
- `rg -n "CLAUDE_CODE_EFFORT_LEVEL|xhigh|思考预算" README.md orchestrator/main.py docker-compose.yml docker-compose.remote.yml .env.example images/worker/entrypoint.sh` 检查默认值和文案一致。

## Review Gates

- 开始实现前，PRD / design / implement 需要用户确认。
- 远程或已有数据库写入前，需要先备份数据库并再次确认。
