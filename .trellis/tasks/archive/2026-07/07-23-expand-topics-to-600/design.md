# Design：扩充题库到 600 条并同步远程

## Technical Design

### 数据模型

保持不变：

- Markdown seed：`topics.md`，分类标题 `## 一、分类名（N 题）`，条目 `- [ ] N. **标题**：描述`
- SQLite：`topics(no, title, description, category, enabled, deleted_at, …)`
- 同步：`scripts/sync-topics-db.py` 按 `no` UPDATE，否则 INSERT；默认 dry-run，`--apply` 写库并备份

分类标题中的「（N 题）」需随扩容更新（如 10→20），解析器 `_CAT_RE` 只取分类名，括号内数量不影响 category 字段。

### 内容设计

1. **1–300 冻结**：不改正文，只改文首总述与文末进度统计。
2. **301–600**：按 PRD 配额写入对应分类章节末尾（同一 `##` 分类块内追加），保持编号全局连续。
3. **去重基线**：从现有 300 提取 `no/title/description` 集合；新题标题归一化后比对（去空格、大小写、常见同义词）。
4. **安全过滤**：对 301–600 跑关键词扫描（金融投资、医疗生物、敏感词）；失败则改写或替换。
5. **灵感来源**：在既有 21 类内延伸子场景；必要时联网检索「indie hacker tools / OSS side projects」类灵感，但产出必须中文 brief 且避开禁区。

### 远程同步流程

```
本地校验 topics.md
  → scp 更新远程 topics.md
  → scp sync-topics-db.py（若远程缺少/过旧）
  → 远程 dry-run 看 insert≈300 update≈300
  → 远程 --apply（内置 backup）
  → 查询 COUNT / MAX(no) / 抽样 301、600
```

连接信息来自 `.deploy/vibecoding-bench.env`（`REMOTE_HOST` 等）。**不在设计中回写明文密码到文档。**

### 失败回滚

- 使用 `db.sqlite.bak-<timestamp>` 覆盖回滚。
- `topics.md` 可用 git 或同步前远程拷贝回滚。

## Compatibility

- 历史 `tasks.topic_id` / `runs.topic_id` 不因 INSERT 新 no 而破坏；UPDATE 1–300 若 description 未改则实质无变化。
- 正在跑的 batch 引用旧 topic id 不受影响；新 batch 可选 600 题。
- 本地空库 seed 会读到 600 条。

## Risks

| 风险 | 缓解 |
|------|------|
| 近义重复 | 标题集合 + 抽样人工审 |
| 敏感误入 | 关键词扫描 + 行业白名单偏好 |
| 远程 DB 锁 | 同步时检查进程；必要时短暂停 orchestrator 只读写 topics |
| 分类计数标题写错 | 校验脚本断言每类 count 与标题数字一致（可选软检查） |
