# 实施与验证计划

## 0. 开工边界

- [x] 完成 PRD 收敛、设计核对与最终 Brief 展示，取得本任务首次完整方案批准后再运行 `task.py start`。
- [x] 进入 `trellis-route(target=implement)`，按当前禁止主动委派的约束采用内联执行；不自行派发子代理。
- [x] 修改对应层前通过 `trellis-before-dev` 读取实际规范、相关 DTO／类型和当前函数定义。保留现有工作区中与本任务无关的 Flower、旧任务及部署文件改动。
- [x] 记录当前父仓／子模块基线、相关文件哈希和旧数据库结构样本。本任务不启动生产模型，不创建生产账号或生产批次。

## 1. 先建立可定向收口的执行基础

- [x] 在 `images/account/cli-control.py` 增加普通用户每作业 subreaper 监督及独立启动握手，保留现有 idle／sample 行为。
- [x] 增加按容器归属、source、PID、启动时刻核对的暂停、恢复、停止与状态操作；覆盖双重 fork、setsid、PID 复用、监督器失效和重复调用。
- [x] 实际 Docker 中验证两个合成作业并行、暂停 A 时 B 继续、停止 A 时 B 继续、后台后代全部收口；不得以全 UID 清理兜底。
- [x] 修改 `AccountRuntime` 多作业登记、逐执行证明、心跳和重启对账；环境删除、维护和资源驱逐检查所有作业。
- [x] 先验证原单作业行为兼容，再使用多作业结构，不能在完成定向清理前放大公共信号量。

## 2. 网关共享 CLI 槽位及设置／网络隔离

- [x] 扩展 `runtime_lease.rs` 的持久门禁状态与管理 DTO，区分共享 CLI、CLI 专用排他、维护排他；旧 prepare-cli 保持独占语义。
- [x] 覆盖多 holder、容量拒绝、按 owner／generation 续期释放、旧文件恢复、损坏文件、导入中 fence／release 与 API 并行。
- [x] 让 Tasks 与项目执行使用同一个实际账号容量，移除 v3 强制 1，保留原批次 1～2 产品范围；配置与页面展示一致。
- [x] 为每 CLI 增加会话 settings 覆盖，按执行路由额度采集并调用原用户状态栏；实际固定 CLI 版本验证效果，不只检查参数存在。
- [x] 普通 passthrough 复用 relay，停止一个执行不重置其他执行；capture／续聊等原有独占路径继续使用正确门禁。
- [x] 回归账号身份、凭据刷新归属、采集事件身份、原生 TLS 路径和账号固定资源预算，不为并行重建环境或重抽画像。

## 3. 策略、随机队列及兼容迁移

- [x] 扩展创建请求的严格整数参数、合法范围和组合校验；冻结 schema 2 策略，省略使用设计默认值。
- [x] 创建时一次洗牌并固定初始位置，活动池与可变轮换顺序分别保存。100 个元数据创建不产生项目目录。
- [x] 增加计划、计划执行与实例在途所有权结构；事务重建尝试表解除单 Run 唯一限制，保留全部旧 ID／索引／外键／序列。
- [x] 从 schema 1 的成功、失败、超时及 quota_wait 历史样本重复执行初始化；确认旧 prompt、内容摘要、Run ID、产物目录与查阅结果不变。
- [x] 新调度按账号／批次容量补位，持久随机间隔可恢复；同截止的竞争只能投递合法数量，暂停／停止及时生效。
- [x] 连续接受步数默认 5、计划默认 2，按 2＋2＋1 截断；活动项目完成或阻塞后从固定随机队列补池。

## 4. 同一 CLI 会话的逐步业务验收

- [x] 增加 `project_plans.py` 与 driver helper `images/account/project_plan.py`，复用原生对话解析和独立 ProjectVerifier。
- [x] 一个正常计划只启动一个 CLI 进程和 Run，固定 session／cwd／模型版本，逐步投递，禁止把独立单步 Run 归组冒充实现。
- [x] 当前步骤完成后进入等待，暂停该作业完整子树，再封存、独立验收与事务接受检查点，恢复同一 CLI 并投递下一步。
- [x] 接受检查点与投递后续指令使用持久阶段序号；模拟接受后崩溃、回复丢失、输入消费不确定、重复事件及停止竞争，均不得重复接受或盲发。
- [x] 验收基础设施故障仍只本地有界重验；业务失败在同一当前步骤内有限修复，计数跨 Run 保留。
- [x] 一次执行超时覆盖整个计划内全部步骤，不因步骤通过重置；管理暂停和验收单独有界。
- [x] 第一步通过、第二步半成品超时后保留原 Run timeout、原计划 1／2、第二步代码及会话证明。恢复新 Run 只完成剩余一步；缺失会话或检查点冲突明确阻塞，不能重建 seed。
- [x] 真实 quota_wait 仍恢复原 Run／session；自设比例或当地窗口只挡后续计划，当前已投放计划完成；手动暂停／停止按设计分别处理。
- [x] 每步统计保存自己的字节边界，整个 Run 统计只聚合一次；校验两步共享 Run 时没有成倍重复 token。

## 5. API、UI 与打包

- [x] 返回规范化策略、账号上限、活动池、在途执行、计划进度、下一投放时间和等待原因；复用现有 cookie 鉴权和管理桥资源。
- [x] 创建表单对齐 Tasks，参数标签区分计划与轮换、额度来自账号设置；项目选择变化后明确展示可保存并发。
- [x] 实例详情展示 1／2 与当前未完成步骤、原失败及恢复 Run；旧批次继续可查。
- [x] 保留 SSE 页面状态、搜索选择、快捷键、明暗主题和窄屏；所有外部文本转义，不引入前端框架或构建工具。
- [x] 更新 account 镜像 COPY、必要的 Docker ignore／源码冻结清单和部署只读状态检查，使多作业证明及 helper 完整入包。

## 6. 必须执行的检查

先运行本轮改动对应的定向回归；本轮最终版本通过一次后，除代码变化、失败或未决风险外不重复扩大测试。

```bash
PYTHONPATH=orchestrator python3 -m unittest test_project_plans test_project_iterations test_account_runtime test_worker_startup test_topic_followups test_cli_quota test_quota_completion test_run_windows test_run_window_scheduling test_login_reauth test_deleted_binding test_main
node --check webui/app.js
bash -n images/worker/entrypoint.sh
git -C cc2api diff --check
git diff --check
```

Rust 在子模块目录执行，并覆盖相关共享 helper 全量回归：

```bash
cargo fmt --check
cargo test --locked
```

- [x] 新的计划控制、进程隔离及迁移测试加入相应 Python 测试模块或明确的新模块，确保上面的命令包含这些模块。
- [x] 冻结父／子源码，使用当前本地 SOP 构建同一批 control／account 验证镜像；不发布标签或镜像。
- [x] 扩展本地隔离验证入口新增 `--project-scheduling-only`：真实 Scheduler／driver／Docker／验证器，合成 CLI 检查同账号重叠执行、同会话两步、1／2 超时接续、间隔重启、额度等待及兄弟作业保护。
- [x] 在同一批镜像复用既有 `--run-boundaries`、`--topic-followups`、`--project-iterations-only`、`--run-windows-only`、`--quota-completion-only` 相关场景；具体参数归属先以现有 argparse 核对，不能混写到不同脚本。
- [x] 扩展 `verify_stack.py` 的隔离浏览器场景：真实页面→API→SQLite→执行证明→成果，明暗／窄屏、权限、随机固定、计划进度及 Runs 链接；不以浏览器 mock 代替服务端实际状态。
- [x] CLI 参数兼容检查可以使用冻结版本的非模型帮助／配置入口；真实模型质量或用量验证需要另有适用授权，合成验证结果不能称为真实模型效果。
- [x] 验证场景清理仅删除本轮随机部署的合成资源，保留报告，不触碰生产数据或无关本地账号。

## 7. 完成链与回滚点

- [x] 实现后经 `trellis-route(target=check)` 进入 Check-All，按报告处理真实缺陷。
- [ ] 经 `trellis-update-spec` 同步项目自动调度、同会话计划、暂停证明、多 CLI 租约、维护排他及统计边界契约；不让旧“必须全 Run 释放后才验收”的文字继续误导新模式。
- [ ] 报告实际变更、测试证据和剩余限制。提交／推送按 `trellis-push` 展示并确认精确 Git 范围；本次任务规划不自动继承旧版本生产发布的确认。
- [x] 本地任一阶段不能证明进程定向收口、会话一致性或迁移完整性时停止进入下一阶段，保留可复核失败证据并修正设计，不降级成表单假并发。
- [ ] 已有 schema 2 计划后禁止旧控制器直接继续新库；需要回滚时先停止并导出新增成果，使用匹配的完整旧快照，生产操作另按 SOP 执行。

## 本轮已经执行的规划验证

- Git 历史定位并发回归提交 `34f56c02`。
- 只读检查本机 Claude Code 2.1.296 的 help／version，确认会话 settings 与 session 参数存在；不是生产冻结版本的效果验证。
- `/tmp/project-scheduling-review-20261020-lahw8b6g/process-review.log`：UID 1000、无 capabilities、无网络，两个作业的定向暂停／恢复／清理与脱离进程组子进程收养全部通过。
- 以上为规划阶段的验证基线；当前实施及本地验证结果见下节，仍未调用真实模型或改动生产。

## 实施中验证记录（2026-10-20）

- 父仓基线 `b2f7a1df14d50fce3d3760aab22a7b25b07db5e7`，子模块基线 `7d71c379d91beaa0e53fac0eca97e52963206396`；内联实现与 Check-All 路由均由 helper 恢复确认。保留既有 Flower／旧任务／部署时区改动。
- Python 广泛回归 362 项通过（`/tmp/project-scheduling-final-python.log`）；随后原生会话截断、检查点缺失、quota 部分对话与输入确认丢失保护，以及 Tasks 实际容量补丁由最新 88 项计划／main 回归覆盖（`/tmp/project-scheduling-final-focused.log`）。两者存在覆盖重叠，不相加为独立测试数量。
- Rust `cargo fmt --check`、`cargo test --locked` 通过，650 项成功、1 项依赖独立 PostgreSQL 的既有测试忽略；`/tmp/project-scheduling-cargo-test.log`。源码未再变化，复用该全量证据。
- 备份轮换 26 项通过；默认版本相关 57 项、worker／补充 driver 60 项、登录草稿 28 项均通过；日志分别为 `/tmp/project-scheduling-{backup-test,version-current-test,tty-regression,login-drafts-test}.log`。
- 官方 2.1.280／2.1.293 的真实 CLI 在无外网 Docker＋本地合成 SSE 下验证 session settings、指定 session、原状态栏调用、身份映射及零 usage。证据 `/tmp/project-scheduling-verification/official-settings[-293].log`，不是 Anthropic 模型推理。
- `verify_cli_jobs.py` 的真实 UID1000 Docker 验证双重 fork／setsid、定向冻结／恢复／清理、旧 PID 证明拒绝与兄弟保护；`set +m` 修复冻结恢复后交互 shell 改写终端模式的问题，同 Run 两步的实际 tmux 交接已通过。
- 从父仓 HEAD 的原版推进器生成 success／failed／timeout／quota_wait 四类完整旧结构样本，连续两次 `init_db()` 后全部旧列、ID、prompt、版本、产物及目录摘要保持，新查询仍可查；`/tmp/project-scheduling-verification/legacy-migration-proof.log`。
- 正式 Dockerfile 的 frontend、Rust release 两个二进制与 control 目标构建成功；account 基础依赖下载过慢，已取消该次完整构建，不能记为正式 account 构建通过。本地联合验收采用已验证运行依赖＋同一冻结源码＋正式 release Rust 二进制，清单标记 `verification_only=true`，不发布。
- 当前最终本地验收清单 `/tmp/project-scheduling-verification/manifest-final3.json`，`source_content_sha256=f85aec9819c85032d443ccb54363d72f3066999f1a54c647f50eb3a771f42f4d`；988 个冻结文件与当前源码逐文件核对一致，摘要保存在同目录 `final3-source-hashes.json`。
- 首个最终清单已通过新调度主场景、项目浏览器、旧单步项目、运行窗口、额度恢复、Run 边界／业务补充浏览器与 21 条补充矩阵。后续 Project 恢复保护和 Tasks 容量／活动池展示修改后，final3 的调度主场景与真实浏览器复核均退出 0（`final3-scheduling.log`、`final3-project-browser.log`）；未变化的旧模式证据保留复用。
- 验收网络使用同一 `flock` 顺序创建，避免多个独立验证争用相同测试子网。全部账号／凭据／CLI 均为本次隔离夹具，不接触生产数据。

## 用户追加：默认版本与备份保留（2026-10-20）

- 默认 Claude Code CLI 改为 `2.1.293`，同步源码、worker、Compose、示例配置与联合清单；已有显式配置和 Run 冻结版本保持。
- 部署备份改为新备份完成并验证后，仅保留同一备份父目录中同部署、同数据根的最近一份完整成功备份；失败不淘汰旧备份，未知／跨部署目录与链接不删除。
- 本轮修改并本地验证部署流程；不登录生产删除现存备份、不修改生产环境配置或发起部署。
