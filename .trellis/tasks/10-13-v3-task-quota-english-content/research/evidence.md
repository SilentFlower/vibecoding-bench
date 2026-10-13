# 规划证据

## 额度现状

- `.trellis/spec/vibecoding-bench/backend/database-guidelines.md` 的现有契约明确写明阈值只作用于 `run_kind='warmup'`，普通任务不消费该门禁。
- `QuotaGuard.admit(..., warmup=False)` 只在 `warmup=True` 时调用 `_admit_warmup()`；`Scheduler._execute()` 对普通 run 传 false。
- `_mark_quota_wait()`、`_resume_account()`、批次 `quota_wait` 和身份保护已经提供可复用状态机；普通任务无需新增状态枚举。
- 运行中 worker 的阈值暂停由 `QUOTA_WARMUP=1` 和 Recorder 控制。普通任务不启用该信号即可满足“运行中收尾、后续等待”。

## 题库与 prompt 现状

- `topics.md` 可解析 600 题、编号集合 1～600、21 个中文分类。
- `main.load_seed_topics()` 与 `scripts/sync-topics-db.py` 各有一套只识别中文分类标题的 `_CAT_RE`，英文标题必须同步修改两处并测试一致性。
- 同步工具按 topic.no 原位更新，当前备份使用普通文件复制；规划要求升级为 SQLite backup API 以覆盖 WAL 一致性。
- 明确高风险外观候选：#39 写作风格迁移、#73 多站点账号自动签到、#76 抢课/抢号监控。其它网页/RSS/公开日志采集属于正常产品场景，但英文描述需加公开数据或授权边界。
- natural/canonical 默认 prompt 全在 `orchestrator/main.py`；四类运行时注入默认值全在 `images/worker/entrypoint.sh`。
- 生产 `/opt/vibebench-v3-us/v3.env` 和旧版 `.env` 当前均未定义四类提示覆盖键，代码默认文本会直接生效。

## 数据与发布边界

- v3 生产题库位于 `/srv/vibebench-v3-us/bench/db.sqlite`；旧版题库位于 `/root/vibecoding-bench/data/db.sqlite`，本任务只同步前者。
- 历史 tasks 保存最终 prompt，runs 引用 task；只更新 topics 表不会改写已持久化 prompt。
- 当前开发分支和交付目标均为 `v3`；cc2api 子仓不需要改动。
