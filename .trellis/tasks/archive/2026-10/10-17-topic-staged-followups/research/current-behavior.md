# 当前证据与决定

- 当前主仓分支 v3，HEAD d785a4f；cc2api 子仓不变。原有 55 个 dirty 文件已由 runner protected-retained 固化。
- `orchestrator/main.py:1335` topics 只有基础字段；tasks:1347 保存最终 prompt，batch items:1379 保存初始 prompt，runs:1399 保存运行身份。`init_db` 用 `_ensure_column` 做兼容迁移。
- `load_seed_topics():1558` 与 `scripts/sync-topics-db.py:parse_topics` 为两条题库解析路径；只改 Markdown 不会更新已 seed 数据库。`TopicIn:9501` 和更新 API 尚无补充字段。
- `run_task:10100` 每次生成新 run。批次准备在 9755 附近提前冻结最终文本，`Scheduler._create_batch...:6280` 才创建 task/run；养号 `_create_task_and_run:7240` 同时创建两者。`QuotaGuard._resume_account:3560` 从历史 task/run 重建 payload，不能再随机。
- `Runner.start_run:3783` 下发 TASK_PROMPT/TIMEOUT_SEC；v3 `AccountRuntime.start_run:1101` 生成实际 driver，把 `/workspace` 与临时控制路径映射至原 cwd 和私有 runtime/runs/jobs。
- `images/worker/entrypoint.sh:944` 使用主项目 JSONL 的最后对话、稳定窗口与启动基线判完成；`inject_tmux_prompt:1511` 使用 bracketed paste；正常初始任务在 tmux TUI 里执行，并非 `-p`。
- driver 1903 附近首个稳定 assistant 即置 completion_done，最后清理 tmux。实现多轮须同时改变完成判定、下一输入确认和恢复游标；仅把第二段写入 description 无法产生中途消息。
- `_project_view:1488` 已将同一 run 目录固定；`begin_continue:1933` 复用该目录。无需新增手动项目管理。
- `images/v3/Dockerfile` control 内打包 `/opt/v3/worker.sh`，account 内当前没有新阶段模块；旧 `images/worker/Dockerfile` 也需同步分发，防止脚本引用不存在 helper。
- 只读线上示例 aade1180bd9d 的主需求是渠道线索评分。当前 CLI 已有单个日期窗口、CSV/JSON 导出、样本量门槛；未见双窗口比较和离线 HTML 对比报告，适合作为两条新增需求。只读观察不修改原 run。
- 题库初筛 78 条 AI/LLM 候选、93 条可能依赖输入的候选；`topic-audit-candidates.json` 只是定位清单，不代表自动判定或替换结果。两个 AI 分类需普通主题重写；经典小游戏算法不等于大模型，按完整语义处理。
- 自然模式普通/批量/养号使用新候选；canonical 与手写 prompt 保持单轮，是对已有稳定评测与原样覆盖契约的兼容选择（DEC-0001）。
