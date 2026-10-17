# 实施与验证计划

## 已完成的规划

- [x] 只读核对运行 490232362377，区分计划偏晚和实际投递延迟。
- [x] 用户确认 5%～30% 窗口，同步 PRD 并消除待决定项。
- [x] 读取共用生成/解码、worker 校验、三个创建入口及现有回归定义。
- [x] 明确新时间 schema 2 与旧 schema 1/NULL 兼容，保持阶段证据格式。

## 实施顺序

- [x] 首次 Brief 已展示，用户明确回复确认；后续范围调整沿用增量决定，不重问原时间窗口。
- [x] 用户已确认0次10%、1次45%、2次45%，一条候选10%/90%；增量材料已同步。
- [x] task.py start 后由 trellis-route 恢复 inline 默认，加载 before-dev 规范并实施。
- [x] 新运行抽样为 schema 2 / 5%～30%，按对应上界保护短预算收尾；解码保留旧版范围。
- [x] 同步 worker 的版本化校验，保留原摘要/时钟、恢复和门禁行为。
- [x] 按确认的比例更新共用次数抽样，仅影响新run；100个离散值验证10/45/45与一条候选10/90，无候选不抽样。
- [x] 新旧边界/未知版本/非法类型在管理端及worker的校验一致，三个创建入口及双版本额度恢复回归通过；旧860秒快照时钟和摘要保持。
- [x] 正式driver/tmux的7个新旧定时场景及真实浏览器合成验证通过；覆盖新窗口计划、首轮提前结束、忙时双补充和认证门禁，旧收尾机制由双版本单元测试及原基线覆盖。
- [x] Check-All全面检查通过，并以written同步权威题库/时间契约；规范仅改一个文件，签名/边界/六节结构及写入范围验证通过。
- [ ] 按精确文件范围完成Git交付，再等待Actions并按release.md执行部署。

## 验证证据

使用既有 `/tmp/topic-followups-venv` 或等价依赖环境，先核对可用性。重点为 `orchestrator/test_topic_followups.py`、`test_quota.py`、`test_account_runtime.py`，通过后执行后端全量回归，防止版本校验影响 Runner 和恢复。

按 `deploy/v3/manage.py build --release <本轮唯一批次> --manifest <绝对清单>` 构建正式 control/account 镜像，运行 `deploy/v3/run_local_verification.py --manifest <清单> --timed-followups-only` 与 `deploy/v3/verify_stack.py --manifest <清单> --browser --topic-followups`。若原生输入/队列代码无变，复用已验证的原生 CLI 基线，不发真实模型请求。

静态检查为 Python 编译及 `git diff --check`；不得为仅时间常量编写镜像实现的重复测试，应以新旧边界、入口快照、正式 driver 和页面/API/SQLite 的行为断言为依据。

## 当前验证事实

- 后端全量348项通过，实际命令 `/tmp/topic-followups-venv/bin/python -m unittest discover -p 'test_*.py'`，工作目录 `orchestrator`；日志 `/tmp/followup-earlier-backend.log`，46.357秒。
- 正式双镜像本地批次 `followups-earlier-20261017-a` 已构建，清单 `/tmp/followup-earlier-local.json`；镜像内共用库、helper源码与工作区字节一致，命令链接有效。
- 真实浏览器/API/SQLite演练通过，包含新版90/540秒目标、旧阶段、未知/损坏提示、XSS及1280/390px明暗主题；日志 `/tmp/followup-earlier-browser.log`。
- 正式driver/tmux的7个场景全部通过：旧时间版本单条/两条/认证失败，新时间版本0/1/2条/认证失败；日志 `/tmp/followup-earlier-driver.log`。同时通过脚本自带的三角色隔离、系统画像及本地TLS转发断言，测试资源已清理。产品输入/队列过程未改，沿用既有原生CLI机制基线；本轮测试没有真实模型请求。
- Check-All按interactive/auto/full执行：时间策略及持久化版本变化触发hard-full，三维通过，剩余CHK/FBK为0；自动同步本文件验证状态及design行号。上线后的历史快照/持久资料核验由release.md承接。

## 上线与回退检查点

部署前再次核对自然空闲、API 租约、历史时间快照和持久摘要，等待活动运行自然结束；不强停、不修改冻结计划、不新增服务器备份。只使用成功 Actions 的同批正式镜像。

上线后核对来源批次、管理桥、历史 schema 1/NULL、持久资料及无关服务；用断网合成镜像验证 schema 2。回退前须先核对新 schema 2 运行/等待记录，不将其交给旧镜像，也不恢复旧数据库或凭据。
