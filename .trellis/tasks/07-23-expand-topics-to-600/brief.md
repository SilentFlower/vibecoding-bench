# Brief — 扩充题库到600条并同步远程

## Goal

- 将 `topics.md` 从 300 扩充到 600（新增 301–600），策略 A 只加厚现有 21 类，去重且避开禁区题材，并同步远程 SQLite。

## Scope

- 1–300 正文冻结；仅更新文首/分类题数/文末统计。
- 按 PRD 配额在 21 类末尾追加 301–600（单行 brief 格式）。
- 去重：不与 1–300 标题/核心场景重复。
- 禁区（收紧后）：生物/基因研究与临床诊断决策；证券/加密货币等投研交易盘面；政治宗教色情赌博等敏感题材。预约/工单/档案/记账/退款等管理系统允许。Check 后已改写近重题 401/419/497/537。
- 本地 `sync-topics-db.py --validate-only` 通过后，同步远程 `topics.md` + upsert `data/db.sqlite`（先备份）。
- 任务 `research/` 记录旧题审计、去重结果、远程备份路径。

## Non-Goals

- 不改写 1–300；不新增分类；不改表结构/WebUI/prompt 逻辑。
- 不中断远程训练 batch；不删除远程自定义 topic。

## Key Context

- Seed：`topics.md`；同步：`scripts/sync-topics-db.py`（dry-run / `--apply` 内置备份）。
- 远程：`.deploy/vibecoding-bench.env` → `23.80.83.23:/root/vibecoding-bench`。
- 旧题 23/66/180/201/202/214 用户定性为可接受管理系统；60 行情盘面新题少做。
- 格式必须兼容 `_ITEM_RE` / `_CAT_RE`。

## Acceptance

- 解析 600 条、编号 1..600 连续；分类仅 21 类；301–600 去重 + 禁区扫描通过。
- 远程启用题 ≥600 且 `MAX(no)=600`；有 DB 备份路径与同步记录。

## Next Step

- 用户已确认 planning；执行 `task.py start` 后分批写入 301–600，校验并远程同步。
