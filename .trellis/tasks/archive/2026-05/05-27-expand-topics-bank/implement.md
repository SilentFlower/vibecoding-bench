# 扩充 topics 题库与优化提示词 - 执行计划

## Implementation Checklist

- [x] 阅读后端 topics seed、prompt 生成和 API CRUD 相关代码，确认字段与解析规则。
- [x] 重写 `topics.md`：保留原 1-100 主题并增强描述，新增 101-200。
- [x] 更新 `topics.md` 文档标题、使用方式和统计信息到 200 条。
- [x] 增强 `orchestrator/main.py` 的 `build_topic_prompt(topic)`，保持入参和返回类型不变。
- [x] 增加或使用脚本校验 `topics.md` 解析结果：数量 200、编号 1-200 连续、标题非空、分类非空、描述非空。
- [x] 准备远程 SQLite upsert 同步命令或脚本，默认先只本地验证，不直接执行远程写入。
- [x] 更新 `implement.jsonl` / `check.jsonl`，提供实现和检查需要的 spec 上下文。

## Validation

- `python3 - <<'PY' ...` 调用 `orchestrator.main.load_seed_topics()`，断言解析 200 条。
- 校验编号集合等于 `1..200`，标题、描述、分类均非空。
- 抽样调用 `build_topic_prompt()`，确认 prompt 包含标题、分类、描述、启动方式、验证方式、合理假设要求。
- 如改动后端代码，至少运行 `python3 -m py_compile orchestrator/main.py`。
- 远程同步前运行只读检查：远程 `topics.md` 数量、远程 DB topics 数量、API `/api/topics` 数量。

## Review Gates

- 开始实现前，PRD / design / implement 需要用户确认。
- 远程写入前，必须再次向用户确认，并先备份远程 `data/db.sqlite`。
- 远程同步后，需要验证 `/api/topics` 返回目标数量并保留数据库备份路径。
