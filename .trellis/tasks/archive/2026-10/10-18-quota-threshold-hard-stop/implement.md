# 实施与验证计划

## 当前状态

任务已在用户确认完整 Brief 后启动。implement route 命中个人默认 inline，check route 命中 check-all-inline，均由当前会话执行。核心实现和页面说明已完成；14 项专项、372 项后端全量通过，最终本轮联合镜像的四场景真实 driver 及浏览器／API／SQLite 验收通过。Full Check-All 通过（CHK 0、FBK 0，任务事实 DOC 2 已同步），权威额度规范更新完成。精确范围已获确认，业务提交已推送；任务记录同步后等待最终 Actions 并按已有授权部署，尚未宣称线上更新。

## 顺序

- [x] 核对线上 55% → 68% 任务与阈值启动门禁／恢复许可。
- [x] 调研 QuotaGuard、真实 v3 wait／cleanup、批次 pending 投放、养号终态与页面旧文案。
- [x] 记录用户第 2 种选择，收敛 PRD、设计与本计划。
- [x] 通过 trellis-task-brief 展示完整 Brief，用户明确确认后运行 task.py start；trellis-route(target=implement) 返回 inline / route-prefs，进入 trellis-before-dev。
- [x] 先补失败回归：旧实现缺少活跃检查回调和强制终止入口，7 项失败证据已保存。
- [x] 在现有 v3 exec 等待路径接入归属校验的阈值观察及停止，持久化停止意图、命中原因，复用本代进程清理；不让异常转 quota_wait 自动续原 run。
- [x] 配套 Scheduler／批次／WarmupScheduler 终态和恢复：原轮 stopped；命中期阻止下一题，窗口与原间隔允许后只投放下一 pending item。
- [x] 更新账号额度说明、缓存版本及部署 README，说明强制结束与被动观察限制。
- [x] 聚焦和后端回归、真实双镜像 busy driver／tmux 与浏览器／API／SQLite 验证。
- [x] 完成 Check-All、Update-Spec、精确 Push 计划确认及业务推送；本次同步独立任务记录与确定性 Close。
- 后续交付：等待最终 Actions 并按已有授权部署 v3，随后只读核对镜像、服务和页面版本；不新增服务器备份，不重试受限账号。部署结果以本轮交付回读及会话报告为准。

## 预计文件范围

核心 orchestrator/main.py、orchestrator/account_runtime.py；按实际执行证据决定是否需要 images/worker/entrypoint.sh 的控制兼容，不扩大抓包／API 策略。为避免与旧额度暂停测试混淆，运行中永久中断用例集中到 orchestrator/test_quota_hard_stop.py，复用 test_quota 的真实 SQLite 夹具；原 test_warmup_quota.py、test_account_runtime.py、test_cli_quota.py、test_quota.py 继续回归。正式 driver 夹具沿 deploy/v3/fixtures/mock_cli.py 与现有 v3 验证入口补充独立强制中断场景。

页面 webui/app.js、webui/index.html，配套 deploy/v3/README.md。真实验证新增 deploy/v3/verify_quota_hard_stop.py、verify_quota_hard_stop_browser.py，并接入 run_local_verification.py、verify_local.py、verify_stack.py 的独立选项；使用正式 statusLine 的合成读数，不直接修改额度状态。旧 test_auto_usage.py 的完成替身适配可选活跃回调，保留自然完成断言。权威规范 .trellis/spec/vibecoding-bench/backend/database-guidelines.md，必要时同步 account-runtime-v3.md 对应行为。cc2api 子仓和 baseline 55 项无关变更保持原样。

## 验证命令与场景

- 本机旧 /tmp/topic-followups-venv 已不存在；本轮依赖环境为 /tmp/quota-hard-stop-venv。工作目录 orchestrator，执行 python -m unittest test_quota_hard_stop test_warmup_quota test_account_runtime test_cli_quota test_quota，新增中断用例具有旧实现失败证据。
- 后端 python -m unittest discover -p 'test_*.py'，只在产品实现完成后执行一次完整有效回归；新增变更或失败需要时再针对重跑。
- Python 编译、node --check webui/app.js、git diff --check。
- 使用本轮源码构建正式 v3 联合清单，核对 control／account 批次及实际 worker 字节；真实 driver／tmux 合成忙碌任务验证 normal／warmup、5h／7d、等值／跨阈值、文件保留与无后续输入。
- 阈值命中后原 run／item stopped；重启和 reset 不提交原 run；下一 pending 只在合法恢复机会与原间隔后投放一次。旧补充正文、已发送记录和 session 不回退。
- 浏览器／API／SQLite 验证阈值表单文案、停止详情、XSS 与明暗／窄屏，无需为纯文案编写镜像实现的单测。
- 自动路径将 usage／真实模型探测设为调用即失败，观察与公开结果不含凭据。

## 失败与交付约束

清理失败要保留门禁，禁止同账号新 CLI；持久 stopping 意图不能被旧 quota_wait 恢复逻辑覆盖。用户停止／删除、身份变化、认证失败和自然终态须优先或正确归属，所有清理只针对原 source／token。

不新增生产备份，不强停为部署制造空闲，不改 disabled／deleted 账号或历史任务，不为上线测试发送真实模型请求。未成功完整收口的执行禁止反复部署或盲目重建；沿已有操作证据补核。

## 已有验证证据

- /tmp/quota-hard-stop-red.log：旧实现 7 项失败，缺运行中强制终止和等待回调。
- /tmp/quota-hard-stop-focused.log：相关 142 项通过；后续补充真实配置提交竞争后，/tmp/quota-hard-stop-extra.log 的 14 项专项通过。
- /tmp/quota-hard-stop-backend-final.log：当前核心行为全量 372 项通过，108.496 秒；随后仅修改 Runtime 参数说明注释。
- /tmp/quota-hard-stop-fixture-preflight.log：现有同批角色镜像挂载本轮源码，真实 5h=60、5h=68、7d=80 停止及关闭阈值正常完成均通过；仅夹具预跑，不冒充本轮最终镜像验证。
- /tmp/quota-hard-stop-local-b.json：最终本轮 control／account 联合镜像，source_content_sha256=7dd55efa398a85feb783b4be3399a6c2b6f5d5f31fc02b8040510a910ee3a882；核心、页面及 worker 字节经核对一致，HTML 仅含 Dockerfile 固定的三条本地资源替换。
- /tmp/quota-hard-stop-driver-final.log：本轮双镜像实际 driver／tmux 的四场景全部通过，三项强制中断在合成读数产生后两秒内认领停止；文件、会话保留，命中后未再输入补充；关闭阈值正常完成补充。
- /tmp/quota-hard-stop-browser-final.log：本轮真实管理栈页面、阈值保存重读、stopped 原因的 API／SQLite、XSS、1280／390px 明暗主题通过。
- 当前 Python 编译、node --check 及本轮文件 git diff --check 通过；普通核心、API 及旧 runner 的行为证据复用 372 项全量回归，不重复运行相同测试。
