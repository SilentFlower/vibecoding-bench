# 实施与验证计划

## 当前状态

实施及本地验证完成，任务为 in_progress，按用户确认启动并沿用 inline 实现和检查。358 项后端测试、17 个正式 driver/tmux 场景和真实浏览器/API/SQLite通过；尚未提交、推送或部署。只读线上核对与脱敏复现见 research/native-queue.md。

## 顺序

- [x] 核对原生附件字段、父链、回复和误判终态。
- [x] 用临时合成输入复现当前 wait/queued。
- [x] 完整展示 Brief，取得首次实施批准后 task.py start，进入 trellis-route(target=implement) 及 trellis-before-dev。
- [x] 先加原生形状失败回归，再在公共 helper 归一化严格有效附件，验证消费/完成/恢复。
- [x] 将 helper 状态交给进度 API 验证 delivered/consumed/completed，保持无须改动的产品层原样。
- [x] 扩充 Docker CLI 替身原生模式及正式 driver/tmux 一条/两条忙碌场景，保留旧形式。
- [x] 聚焦、后端全量、正式双镜像、driver/tmux、浏览器/API/SQLite验证。
- [ ] 复盘原生协议夹具缺口，依次 Check-All、Update-Spec、精确 Push 计划。
- [ ] 最终 Actions 后按既有授权自然空闲部署 v3，核验持久资料、旧计划、阶段字节及其他服务，不新增备份或真实模型测试。

## 验证入口

- /tmp/topic-followups-venv/bin/python -m unittest test_topic_followups，工作目录 orchestrator。
- /tmp/topic-followups-venv/bin/python -m unittest discover -p 'test_*.py'，工作目录 orchestrator。
- Python 编译和 git diff --check。
- deploy/v3/manage.py build 新的正式联合清单，核对镜像 helper 字节。
- deploy/v3/run_local_verification.py --manifest <本轮清单> --timed-followups-only，以及旧阶段夹具。
- deploy/v3/verify_stack.py --manifest <本轮清单> --browser --topic-followups。

## 文件范围和约束

核心预期 images/worker/task_followups.py、orchestrator/test_topic_followups.py、deploy/v3/fixtures/mock_cli.py、deploy/v3/verify_followups.py 和权威 topic-prompt-contract.md。测试矩阵扩至17场景，run_local_verification.py 的外层Docker等待由480秒调整为1200秒，场景及产品deadline不变。仅在实际证据要求时扩充同职责测试；扩大产品或真实数据边界前同步规划。

保留 55 项无关变更和 cc2api，不改 topic、概率、窗口、输入及收尾设置；缺消费禁止重发，不自动改历史终态。保留旧镜像和既有回退资料，不新增备份，不强停活动任务。

## 已完成验证证据

- 后端全量：/tmp/queued-followup-backend.log，358项，退出0。新增原生消费回归先在旧实现中失败，修复后随全量通过。
- 正式镜像：/tmp/queued-followup-local-b.json，批次queued-native-20261017-b；account helper、命令链接、control driver及当前测试源码字节一致。
- 正式driver/tmux：/tmp/queued-followup-driver.log，全部17场景通过，含旧阶段6个、普通定时7个和原生附件4个。
- 真实浏览器/API/SQLite：/tmp/queued-followup-browser.log，退出0，含进度、未知/损坏证据、XSS、明暗窄屏及数据保留。
- Python编译与git diff --check通过。全部使用本地合成资料，没有真实账号模型测试或线上写入。
