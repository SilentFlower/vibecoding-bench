# 扩充 topics 题库与优化提示词 - 设计

## Technical Design

本任务保持现有题库数据模型不变：`topics.md` 仍作为 seed 文件，SQLite `topics` 表仍使用 `no/title/description/category/enabled/deleted_at` 等现有字段，不新增表字段，不调整 WebUI 表单字段。

题库内容设计采用“单行增强 brief”：

- 每条题目继续使用 `- [ ] N. **标题**：描述` 格式，兼容现有 `_ITEM_RE` 解析。
- 原 1-100 保留编号和大致主题，但描述扩展为更具体的项目 brief。
- 新增 101-200 使用连续编号，分类仍沿用 Markdown 二级标题组织。
- 描述中承载核心场景、关键功能和验收方向，但避免过长，保证 WebUI 卡片可读。
- 不额外引入难度、标签、测试点字段；需要表达的难度和验收重点写进描述。

默认 prompt 生成逻辑保持在 `build_topic_prompt(topic)` 中增强：

- 仍接受现有 topic dict，不改调用方契约。
- prompt 包含题目标题、分类、描述。
- prompt 明确要求产出可运行 MVP、说明启动方式、说明验证方式、列出关键实现内容。
- prompt 要求遇到不明确细节时做合理假设并在总结中写明，而不是停下来等待人工。

远程 SQLite 同步策略采用按 `no` upsert，不重置整库：

- 先备份远程 `data/db.sqlite`。
- 从新版 `topics.md` 解析 200 条题目。
- 对已有编号 1-100 执行 `UPDATE`，保留原 topic `id`，避免破坏历史 `tasks.topic_id` / `runs.topic_id` 引用。
- 对新增编号 101-200 执行 `INSERT`。
- 不删除远程现有 topic；如果远程存在大于 200 的本地自定义题，默认保留。
- 同步后通过远程 `/api/topics` 验证返回 200 条以上且 1-200 都存在。

## Compatibility

- 本地首次启动仍可从 `topics.md` seed 全量 200 条。
- 已经 seed 过的本地或远程数据库不会自动感知 `topics.md`，需要执行 upsert 同步。
- WebUI topic 卡片继续显示 `no/title/description/category`，无需前端结构改造。
- 历史 task/run 通过 topic `id` 继续关联，按 `no` 更新不会改变已有 `id`。

## Rollout / Rollback

本地改动先验证 Markdown 解析数量、编号连续性和 prompt 输出。远程上线分两段执行：

1. 更新远程 `topics.md` 和后端代码。
2. 在备份数据库后执行一次性 upsert 同步。

回滚时恢复远程备份的 `data/db.sqlite`，并恢复旧版 `topics.md`。如只回滚题库内容，不需要重启 worker/sidecar。
