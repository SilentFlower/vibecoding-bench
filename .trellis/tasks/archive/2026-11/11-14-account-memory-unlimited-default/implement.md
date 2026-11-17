# 执行与验证

- [x] 读取运行时、部署、资源与项目生命周期规范，进入inline实现路由。
- [x] 统一unlimited默认及有限覆盖，调整部署预检和sender CPU默认1.5。
- [x] 实现旧内存策略空闲应用，核对prepare_sender两职责、在途/评审/内核维护及失败恢复。
- [x] 增加默认/显式有限、既有环境延后迁移、sender无限原生、CPU策略覆盖和混合部署预检回归。
- [x] 运行受影响Python定向及完整回归、数据库定义检查、Compose解析及真实Docker零模型验证。
- [x] Check-All、Update-Spec、精确Push计划。
- [x] 记录上线配置切换、原身份/进度验证及失败恢复操作单。

## 验证入口

- PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_native_sender test_account_runtime test_cpu_resources test_project_review_runtime test_manage test_system_update_retirement
- 依据实际发现的模块名核对完整Python发现与执行数，不能以镜像Mock代替真实Docker资源验证。
- python3 deploy/flower2api/verify_database_definitions.py；git diff --check。
- 合成Docker部署：默认无限/有限覆盖、新建/既有/停止/忙/失败、串行评审与CPU持久策略。核对HostConfig及cgroup实际无限、sender1500000000 NanoCpus、内核和热进程证据，模型调用0。

## 上线交付

- release.md描述本部署15环境的分批/空闲应用和停止保留，显式配置1536m转unlimited。
- 正式发布v1.7.0纳入本次收尾；安装及线上配置应用由后续操作指令承接。

## 实现和定向证据

- 197项定向回归通过。迁移复用原排他maintenance租约及孤儿检查；平台更新门禁关闭时延后迁移，额外定向1项通过。
- Compose实际解析默认内存unlimited，CLI/sender/network CPU分别1.5/1.5/0.5。数据库定义检查通过，双库均保持版本1。
- 实际隔离Docker通过：CLI/API活动保护、停止读取零唤醒、旧1536m空预算环境迁移、原身份及HOME保持。三个角色HostConfig为Memory=0/MemorySwap=-1，cgroup memory.max及memory.swap.max均max；sender实际1500000000 NanoCpus。原生N=4配置max_workers=8，实际ready/idle_workers=1，内置内核beta.6可见，模型调用0。
- 完整Python发现集88模块、1285项通过，跳过1项。当前源的迁移及系统更新112项补充回归通过；部署完整195项通过。

## 追加正式发布

- [x] 版本元数据递增为v1.7.0并验证发布合同，精确提交新增版本文件。
- [x] 运行v3-release.yml手动发布，核对实际源码、双镜像、6项附件、8来源演练及受信目录签名。
- [x] 实际发行验签通过后更新任务验收事实，再同步completed和Close及任务记录。

## 正式发行验收

- v1.7.0发行：https://github.com/SilentFlower/vibecoding-bench/releases/tag/system-ci-43594047518-1；流水线43594047518全部通过，绑定版本提交f47fae4d。
- 双镜像源码摘要、6项附件摘要和Ed25519签名独立核验通过；8个历史来源兼容演练证据通过。
- 两个受信目录独立核对Git blob身份和签名，迁移目录217/1、原目录196/1。线上安装与资源应用继续沿release.md操作单。
