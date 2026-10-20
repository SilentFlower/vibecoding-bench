# 原验收证据与代码核对

## 证据来源

- 原会话 `01a156c1-7190-70c1-97f2-20ae75b93ac7` 及本会话原始工具记录。
- `.deploy/v3-production-simulation-report-20261020/report.md`、`findings.md`、`evidence/resume/`。该目录为 gitignored 本地证据，不作为唯一可恢复知识；本文件保留必要事实。
- 原发布 `ci-39390842316-1`，主仓 `ce9c5bd6468b8c4ef42c2572445c2237c5591bee`；生产前端字节与本分支一致，已排除部署滞后。

## 运行缺陷

1. `ProjectPlans._decision()` 每次调度均调用 `write_document()`，之后才对路径 chown/chmod。后者 mkstemp 生成 root:root 0600 临时文件，再 os.replace。相同发布镜像确定性复现：替换后 UID1000 errno13；改为 root:1000 0640 后可读。多个实际失败 Run 的 stderr 也指向决定文件 Permission denied。
2. driver `_read()` 在打开后要求 `st_nlink==1`。相同镜像中在 open 与 fstat 之间 replace，旧 fd 链接数为0，稳定复现“计划文件类型或大小无效”。实际 Run `d749b182e390` 同样报错，后续新 Run 接续完成；实际故障当时未采集 inode，不能宣称完整还原其时序。
3. `_block()` 写入局部 blocked 后无条件调用 `stop_run()`；后者先读状态、长 IO 后无条件写 stopping。原批次错误为 `HTTPException: 400: 运行 08a9c1e914d3 当前不是 queued/running 状态`。外层 tick 把异常升级为整批 blocked。`_settle()` 把内部停止与人工取消混为一类，再由 `_finish_failure()` 覆盖实例错误。

## 界面缺陷

- `paintProjectBatch()` 将全部非 active 状态写成等待启动，并无条件使用历史 next_launch_at。
- 运行时段启用 checkbox 实测宽767px、label宽774px；启用项与星期标签继承 `.form label` 的纵向布局。checkbox 实测 padding 为0，不能将 padding 作为已证实根因。
- 现有 `.toggle-line` 已有同行布局，前端无需新组件体系；现有 run_window.config 的 enabled/days/intervals 及服务端 timezone 足以支撑修复。

## 验证边界

- 原单批第二轮：849接受步骤、40完成／45开始项目，47 Run（40success、3failed、4stopped）；最大实际CLI并发2，无重复接受。原生/API用量均96932，unknown0。
- 后续跨实例：100个独立会话和目录、2000唯一接受步骤、原生/API输出均231066合成token。此结果只证明内容覆盖，不证明单批稳定。
- 原规模实例使用1秒完成稳定等待；生产默认10秒对照40步全部通过，只证明有限样本未复现。
- 原临时6容器、网络、运行数据已清理；3977原业务行、36原凭据文件、20原容器均核对无变化。生产展示账号6、批次1／3／4保留。

## 已找到的复用点

- `orchestrator/project_library.py:72` 是项目文档的原子写入口；`orchestrator/account_runtime.py:131` 已示范在临时 fd 上设置权限后 replace 的方式，但不应让 project_library 反向依赖账号运行时。
- `orchestrator/test_project_plans.py` 已装载实际 driver，并用真实 SQLite、原生会话文件和线程驱动验证；`test_project_iterations.py` 提供独立实例夹具。
- `deploy/v3/verify_project_scheduling.py` 已有两CLI并行、冻结兄弟保护、同Run两步及真实60秒超时接续。`verify_project_browser.py` 已覆盖 SSE、主题和窄屏。
- `deploy/v3/run_local_verification.py` 外层默认等待1200秒；百项目默认10秒稳定等待明显超过该上限，规模入口须单独有界配置，不能把外层超时当产品失败或改短生产等待来凑通过。
