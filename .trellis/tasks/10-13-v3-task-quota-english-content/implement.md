# v3 任务额度门禁与全英文内容改造 — 实施计划

## 1. 开始条件

- [x] 最新 PRD、设计和本实施计划通过 Brief 评审后，才运行 `task.py start`。
- [x] 通过 `trellis-route(target=implement)` 选择执行模式，读取任务 JSONL、对应规范和完整类/DTO 定义。
- [x] 固定 baseline：保留任务创建前的 22 项无关 dirty；确认 cc2api clean 且父仓从 `v3` 当前 HEAD 开始。

## 2. 普通任务额度门禁

- [x] Q1（R1）：抽取通用账号 policy snapshot，保留养号 admission wrapper；普通任务对未知/到期窗口 fail-closed，养号继续一次正式请求。
- [x] Q2（R1）：在 `Scheduler._execute`、`_mark_quota_wait`、`_resume_account`、重启恢复和批次状态中接入 `run_kind='normal'`；抓包、继续对话、API 明确不接入。
- [x] Q3（R2）：更新账号公开摘要和配置文案，说明运行中收尾、后续等待及 API 不受影响；保存接口保持旧字段兼容。
- [x] Q4（A1–A4）：扩展 quota 单测、并发/恢复/批次测试和浏览器阈值表单验证；断言门禁发生在 worker 创建前。

## 3. 安全英文题库与 prompt

- [x] E1（R3、R6）：更新两套 Markdown 解析器以兼容新旧分类标题；先新增 600/21/编号/无 CJK/风险词校验及解析器一致性测试。
- [x] E2（R3）：将 `topics.md` 的说明、分类、600 个标题和描述翻译为英文；固定替换 #39/#73/#76，对风险扫描命中逐项复核。
- [x] E3（R4）：把 natural/canonical prompt 资产、分类映射、回退和指纹占位符改为英文，并更新 topic prompt 单测。
- [x] E4（R5）：把 worker 的 resume、wrap-up、auth retry、API stall 默认提示改为英文，增加脚本级无 CJK 和触发语义回归。
- [x] E5（A5–A7）：在临时数据库跑 validate-only、dry-run/apply/重复 apply/备份恢复；反向核对 topic id、task/run prompt 和其它表不变。

## 4. 集成验证

```bash
python3 scripts/sync-topics-db.py --topics topics.md --validate-only
node --check webui/app.js
python3 -m py_compile orchestrator/main.py orchestrator/quota_protocol.py scripts/sync-topics-db.py
PYTHONPATH=orchestrator python3 -m unittest orchestrator.test_main orchestrator.test_warmup_quota orchestrator.test_quota
git diff --check
```

- [x] 构建最终双镜像并确认 frozen source hash 与当前源码一致。
- [x] 跑 `run_local_verification.py`，覆盖固定账号环境、普通 run、API/CLI 隔离和同 run 恢复。
- [x] 跑 `verify_stack.py --browser --warmup-quota`，覆盖 1280/390、明暗主题、保存重读及任务等待摘要。
- [x] 用合成额度观察覆盖：低于阈值、等于阈值、未知、窗口到期、手动查询恢复、关闭阈值、批次和运行中收尾。
- [ ] 扫描最终镜像及目标 v3 环境的四个 prompt 覆盖键，只报告键名和是否存在，不输出秘密配置。

## 5. 检查、发布与回滚

- [x] 通过 `trellis-route(target=check)` 进入 Check-All，完整核对调度状态机、历史兼容、600 题完整性和跨层数据流。
- [x] `trellis-update-spec` 更新账号阈值从养号专用到普通任务的契约，以及英文题库/prompt 同步契约。
- [x] `trellis-push` 精确提交任务代码、数据、规范和任务记录，保留 baseline。
- [ ] Actions/GHCR 成功后部署 v3；升级前确认无活动 run/登录，停机备份，重建旧批次账号容器但保留 HOME/指纹。
- [ ] 生产 v3 数据库先 dry-run 后 apply，同步后核对 600 题、账号/设置/历史 prompt 和旧服务基线。
- [ ] 回滚同时使用上一批双镜像和本次 topic 数据库备份；禁止只回镜像而保留不兼容的题库解析假设。
