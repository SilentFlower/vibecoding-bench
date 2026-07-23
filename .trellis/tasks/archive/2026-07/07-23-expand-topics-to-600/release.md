# Release Operations

## Conclusion
Release operations exist.

## Evidence Checked
- task.json / brief.md / prd.md / design.md / implement.md
- research/remote-sync-log.md（远程备份与 upsert 记录）
- git commits `68ca264`（题库+同步脚本+spec）、`8fd9894`（任务记录）
- 无 schema migration；`topics` 按 `no` 数据 upsert
- 远程操作：`23.80.83.23` 上 `topics.md` + `data/db.sqlite` 已同步；batch #45（7-19 / 600 topics）已启动；旧 batch #44 已 pause

## Drift Check
Missing release.md prior to this audit. Written from task artifacts + remote-sync-log + git.

## SQL Changes
None（无 DDL/migration；为 SQLite `topics` 行级 upsert 数据变更，见批处理节）

## Configuration Changes
None（未改远程 `.env` / 服务端口 / 鉴权）

## Batch / Deployment Scripts / Data Repair
- 远程同步题库：`scripts/sync-topics-db.py --topics topics.md --db data/db.sqlite --apply`（已执行）
  - 备份：`data/db.sqlite.bak-20260723-005928`、`data/db.sqlite.bak-20260723-011618`
  - 结果：`enabled=600`，`MAX(no)=600`
- 训练批次（运维已执行，非代码仓部署）：
  - pause `task_batches` #44（300 topics）
  - create #45 `batch acc#15 · 600 topics`（account 7-19，concurrency=2，interval 600–800s，timeout 2000s）

## External Systems / Dependent Platforms
None（未依赖第三方平台配置变更；训练跑在既有 remote orchestrator）

## Release Order
1. 代码入库 `topics.md` + sync 脚本/解析契约（已完成）
2. 远程 scp `topics.md` / 必要时 sync 脚本 → dry-run → `--apply`（已完成）
3. 按需新建 600 题 batch 或依赖 warmup 自动抽全库（#45 已开；warmup 自动读全库）

## Rollback Notes
- 代码：回滚 git 至扩容前 commit
- 远程题库：用 `data/db.sqlite.bak-20260723-005928`（或 `011618`）覆盖 `data/db.sqlite` 后重启/确认 orchestrator 可读
- 批次：pause/delete #45；必要时 resume #44（仅 300 题进度）

## Post-release Verification
- WebUI / API：`/api/topics` 启用条数 600
- `SELECT COUNT(*), MAX(no) FROM topics WHERE deleted_at IS NULL AND enabled=1` → 600 / 600
- batch #45：`status=active`，item 数 600，runs 正常推进
- 养号账号（如 7-12）：warmup 从全库 600 抽题（无需重建配置）
