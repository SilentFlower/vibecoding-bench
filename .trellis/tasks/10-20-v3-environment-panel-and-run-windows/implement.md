# 实施与交付顺序

## 规划与激活

- [x] 记录原始需求、代码证据及用户的本轮完成决定。
- [x] 将额度阈值调整纳入父任务，建立 P3 子任务，不修改已关闭的历史任务。
- [x] 为三个子任务准备需求、设计及实施计划。
- [x] 完整展示统一 Brief，用户已明确回复“确认”，整体范围获准。
- [x] 按 P3→P1→P2 顺序激活子任务，分别使用 route-prefs 命中的 inline，并加载 before-dev 规范。

## 子任务执行

1. P3：移除运行中百分比强停，保留下一轮门禁；同步单测、真实 driver 验证、页面及操作说明。
2. P1：实现配置/实测物理详情与只读采集，核对来源、缓存、有限截止和身份不变。
3. P2：实现时段配置、时钟、统一启动门禁及重启恢复，组合验证窗口和额度等待。

子任务只按各自最新三件套实施。统一 Brief 承载本轮完整交付范围；后续技术细节在已批准范围内细化，新增产品决定才单独确认。

## 验证和收尾

- [x] 各子任务运行聚焦检查；最终全量后端 415 项通过，Node 语法与 Python 编译通过。
- [x] 本地 UI/API/SQLite/Docker 验证覆盖物理实测、窗口与阈值组合、排队重启、配置保存重读、1280/390px 明暗主题及历史停止记录。
- [x] 子任务与最终整合完成 Full Check-All，CHK-001 修复后重检通过。
- [x] 完成 Update-Spec 及精确 Git 交付；业务代码已推送，父子任务记录按已确认计划同步完成态和 Close。
- [x] 核对初始 dirty baseline 中其它 Flower、任务和部署草稿未被覆盖：59 项逐文件哈希中仅本轮共同编辑的 `deploy/v3/README.md` 改变，其余 58 项一致；README 既有 gateway 时区段落保留。

## 风险文件

用户已选择修复 CHK-001。沿用 inline 实施路由，准备后统一复查三个入口；对已认领但确认未发起的执行退还精确来源许可，补充跨边界及旧来源不误释放回归，再复用当前检查路由重检。该修复续行不新建任务、不重走整体 Brief 确认。

`orchestrator/main.py` 同时承担三个子任务入口，按上述顺序串行修改。`deploy/v3/README.md` 有既有未提交内容，仅同步与本任务直接相关段落，保留其它更改。

## 验证证据

- `/tmp/v3-run-boundaries-unit-all.log`：`/tmp/quota-hard-stop-venv/bin/python -m unittest discover -s orchestrator`，408 项通过。
- `/tmp/v3-quota-completion-driver.log`：旧验证基础镜像加本轮挂载源码，normal 等值/跨值、warmup 7d、阈值关闭四个真实 driver 场景通过，均完成原补充与收尾；启用阈值时下一轮等待。
- `/tmp/v3-run-boundaries-20261020-b.json`、`/tmp/v3-run-boundaries-build-b.log`：本轮同批 control/account 本地构建完成。首次 a 批构建主动取消；已证实基础镜像具有全部允许时区，最终 b 批改为构建时逐项验证。
- `/tmp/v3-run-boundaries-native-b.log`：最终同批镜像及源码的物理采集、跨关闭时刻与阈值、排队调度器重启、两个门禁分别解除、完整恢复及身份保留，通过。
- `/tmp/v3-run-boundaries-browser-b.log`：真实管理桥/Chrome 时段保存、重读、关闭、环境固化时区和双时钟、物理来源/XSS/停止不唤醒、明暗与窄屏，通过。
- `/tmp/v3-quota-completion-browser-b.log`：本轮完成说明、保存重读、历史 stopped API/SQLite 原因及页面转义，通过。
- `/tmp/v3-run-boundaries-full-native-b.log`：最终 b 批全套隔离回归退出 0；17 个多轮消息场景、原生 TLS、CLI/API 独立长流、取消/重启/收口、同代理账号隔离、故障关闭发送器与重建身份保留均通过。真实 OAuth 和公网模型请求未执行。
- `/tmp/v3-window-credentials-boundary-check.log`：首次 Full Check-All 的失败取证，凭据同步前 allowed=true，同步后关闭仍启动成功，登记 CHK-001。用户随后明确选择修复；保留该历史证据，不作为修复后行为。
- `/tmp/v3-window-boundary-repair-unit-final.log`：最终代码全量 415 项通过（87.824 秒）；时段调度聚焦 20 项含七项新增回归，覆盖普通/养号/抓包、新续聊及恢复、精确来源许可退还、旧身份/来源及已使用机会保持，以及已执行任务恢复新代后关窗排队再重启。
- `/tmp/v3-window-boundary-repair-native-final.log`：b 批本地镜像作运行基础，挂载最终工作区源码，窗口/阈值/排队重启、真实物理观察、原补充与收尾及身份保留通过，退出 0；未构建或发布新的镜像批次。
- 最终 `node --check webui/app.js`、Python compileall 及 `git diff --check` 均通过。先前浏览器和完整 driver/隔离回归的未受影响证据复用；CHK-001 已关闭，无剩余 CHK/FBK，未部署生产。
