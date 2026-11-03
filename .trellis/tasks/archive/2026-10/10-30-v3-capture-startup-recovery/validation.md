# 验证记录

## 当前阶段

实现与定向验证通过；Check-All full strict pass，CHK/FBK/DOC 均为 0；Spec 结果为 written。精确 Push 与部署计划已获确认，业务提交 `a32b28547ee24197b75765fbd7d6ce1033d15e27` 已推送，联合发布 `ci-41034190954-1` 已交付 us。原工作通过正常管理入口恢复到控制第 31 代，实际 CLI、原生响应、完整抓包、健康、身份与镜像回收均已验证，R1～R5 验收完成。

## 定向回归

工作目录均为仓库根，Python 命令前缀为 `PYTHONPATH=orchestrator .venv/bin/python -m unittest discover`。

| 范围 | 命令后缀 | 结果 |
| --- | --- | --- |
| 网络切换与真实退出竞争 | `-s images/account -p test_network_context.py` | 5 通过 |
| 私有诊断、敏感值、权限与越界 | `-s orchestrator -p test_runtime_diagnostics.py` | 5 通过 |
| 抓包监督、网络错误协议与清理因果链 | `-s orchestrator -p test_capture_settings_runtime.py` | 10 通过 |
| 两空间启动失败与人工恢复正反例 | `-s orchestrator -p test_projects_runtime_resilience.py` | 15 通过 |
| 实际环境表、工作区注册与收口证明 | `-s orchestrator -p test_startup_recovery.py` | 5 通过 |
| 账号运行时、安全文件发布及既有边界 | `-s orchestrator -p test_account_runtime.py` | 71 通过 |
| Projects 输入、控制权与既有人工恢复 | `-s orchestrator -p test_projects_agent.py` | 39 通过 |

合计 150 项测试。相同范围重复执行不重复计数；新增真实 `/proc` 用例在修复前的 `cmdline` 和 `stat` 两个分支均报 `ProcessLookupError / errno=3`，修复后通过。历史线上事件缺少原始异常，不能用此复现冒充历史根因已确认。

`git diff --check` 通过。代码与测试之外的既有协议文档修改及其它任务不属于本任务范围。

## 真实禁网容器

```bash
.venv/bin/python deploy/v3/verify_network_context.py --image ghcr.io/silentflower/vibebench-v3-account:v3-ci-39609484070-1 --cycles 3
```

- 3 轮抓包／透传，合计 7 次真实模式切换全部通过，原监听均优雅退出，持久 CA 重复恢复和发布成功。
- `--network none`，合成来源、空运行数据，模型请求 0；仅挂载受测脚本，没有挂载账号或真实配置。
- 本地既有 account 镜像作为依赖底座，覆盖当前受测网络／诊断／透传及 Recorder 源码；测试的实际源码 SHA256 和底座镜像 ID 保存于 `research/network-switch.json`。
- 该证据证明当前源码在该固定依赖底座上的隔离行为，不代替未来正式联合镜像、生产代理、真实 CLI 和目标恢复验收。

## 上线后验证

- [x] 核对新联合镜像与清单、当前 us 归属、资源参数、空闲与身份状态。
- [x] 健康验收并完成旧镜像定向回收检查及复核；本次无合格删除候选。
- [x] 原工作经正常人工入口恢复一次，确认原工作／会话／设置、成功启动、故障解除及原生响应。

联合构建与发布：[Action 41034190954](https://github.com/SilentFlower/vibecoding-bench/actions/runs/41034190954)，来源为业务提交 `a32b2854`，父／子仓与两镜像、配置／仓库摘要和运行中实际源码一致。只修改发布四项配置，资源参数保持；未备份、未重新计算内存。

| 生产核验 | 实际证据 |
| --- | --- |
| 服务与鉴权 | gateway healthy，页面 200，未鉴权管理 API 401、鉴权后 200，两库 `quick_check=ok` |
| 持久身份 | 环境 ID、HOME 身份、冻结工程、账号、工作／session／工作区／设置及原请求器配置摘要保持；20 个其它原容器不变 |
| 真正恢复 | 既有管理入口 POST start 200，`manual_retry=27232`、控制代次 31；实际 CLI 启动于北京时间 17:49:31，环境代次 8，进程与 Docker exec 证明匹配 |
| 原故障保留／解除 | 原 `startup_unknown`、历史代次 29、失败次数 1 和原时间保留；真实启动后设置 `resolved_at`、生成 `runtime_recovered=27237` |
| 原生响应 | 验收快照中原 session 文件 1 个、有效助手记录 34、原生 API 错误 0；cwd 为原 `arrow-e0df329e` 及其 library 子目录 |
| 实际抓包 | mode／ACK 均为 capture 且 source 为原工作第 31 代；45 个 HTTP flow 中 44 complete、1 pending、0 interrupted，其中 17 个完成的模型 HTTP 200；TLS ClientHello 15 条，原生 flow 已落盘 |
| 镜像回收 | 保留当前及最近两个完整历史批次与全部容器引用，候选 0、删除 0，25 个原容器／运行状态／部署配置复核通过；空闲 `22,643,822,592` 字节 |

恢复请求由既有管理入口在验收期间发出；本次运维未再次调用 start 或补发输入，而是沿用该次有审计的正常恢复完成核验。首次源码核验误选 CLI 角色，受到 root 专用脚本权限拒绝；改由实际执行脚本的 network 角色读取，并在只读验收中接纳上述已确认执行，完整核验通过。保留首次失败记录，不降低角色隔离或修改运行状态。

私有生产证据为 `verified.json`、`launch-proof.json`、`resume-started.json`、`live-evidence.json`、`capture-evidence.json` 和 `image-cleanup/{plan,result}.json`，位于 `release.md` 中登记的操作目录。本地私有副本及摘要保存在 `.deploy/v3-capture-startup-recovery-41034190954/`，Git 记录仅保留脱敏结论。空间字节差 `-3,571,712`，本次未删除镜像，不把该负差额当作回收释放量。
