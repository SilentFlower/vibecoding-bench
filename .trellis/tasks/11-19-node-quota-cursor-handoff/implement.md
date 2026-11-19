# 实施计划

## 顺序

- [x] 完成 Brief 评审，运行 task.py start 并进入 trellis-route 的实现路由。
- [x] 先用隔离 SQLite 和双数据根复现已有本机来源登记与远程镜像的路径冲突，覆盖已保存远程镜像游标的历史故障形态。
- [x] 读取相关真实类和全部调用者，集中精确 API 登记规则，接入本机及远程位置衔接。
- [x] 核对归属切换、迟到消费写回和历史样本重读，保留原额度／认证／恢复许可事实。
- [x] 增加连续迁移、回迁、幂等重试、身份与未知路径拒绝及中断恢复回归。
- [x] 在现有工程／养号计划夹具验证原启动恢复入口与其他门禁，保留工作进度和计划配置。
- [x] 复用审计场景添加旧认证错误重放回归，验证人工核验、较新错误与恢复机会的时序保护。
- [x] 实现结构化上传状态及原迁移 transfer 检查点的受控新尝试，覆盖本机／SSH 上传、重启、完整回包未知、取消和发布边界。
- [x] 实现已结束工程抓包的只读位置衔接，同步所有 Node 操作白名单，验证双空间、双向／连续迁移与旧节点离线。
- [x] 执行下列聚焦验证，按实际变更补充必要测试并写入证据。
- [x] 通过 trellis-route 的检查路由进入 Check-All，完成全面检查及 Spec 评估。
- [x] 收敛精确 Git 范围：修复涉及前置未跟踪集群基础文件，main.py 含其他会话增量；分支还有本任务之外的 Flower 更新 ahead。先整合前置改动，再进入提交确认。
- [x] 编写 `release.md`：同批部署范围、11-14 只读核对、原启动／恢复动作、真实成功判据与回滚点。线上执行在部署流程相应授权后记录。

## 本轮验证证据

- 主回归：`test_cluster_quota test_quota test_cluster_migration_files test_cluster_migrations test_cluster_migration_runner test_cluster_project_capture test_cluster_projects_terminal test_cluster_terminal_sessions test_projects_schedule test_projects_engine_cycles test_cluster_agent test_cluster_ssh`，177 项通过，103.312 秒。
- 历史读取补充：`test_cluster_project_capture test_cluster_projects_terminal`，12 项通过，10.218 秒，包含真实归档迁移和旧节点离线的新用例。
- 上传边界补充：`test_cluster_migration_files test_cluster_migration_runner`，21 项通过，11.141 秒，包含新尝试 CAS、取消后拒绝、已核验包保护。
- 远程→远程额度：`RemoteApiQuotaTests.test_remote_to_remote_handoff_reads_new_node_and_keeps_logical_source`，通过。两个实际 Node 数据根和 SQLite 投影参与。
- 上述实际验证去重覆盖 182 个不同用例。全面检查三个维度通过；CHK=0，FBK=0。Spec 结果为 written，固定路径交接、认证时序、上传检查点和历史只读操作已写入账号运行时规范并通过追加边界及差异校验。
- 真实 SSH／轻量客户端／UDS Actor／文件读取的新历史抓包链路通过；Docker exec 由显式命令替身承载，测试保持合成身份和隔离本机 SSH。
- 相关 Python 文件语法解析及 tracked 增量空白检查通过。前期暴露的测试夹具代次、节点网络和旧账本过滤前提已按实际定义修正并重验。

## 验收映射

| 验收 | 证据 |
| --- | --- |
| A1、A2 | 实际 QuotaGuard 的本机→远程→本机→远程及双 Node 额度样本消费；原镜像轮转／半行回归 |
| A3、A4、A9 | 旧位置迟到写入拒绝、未知路径保留、旧认证错误重读及新错误仍触发门禁 |
| A5 | 原工程计划、双空间轮次及额度门禁回归；原进度和计划配置沿既有入口 |
| A6 | release.md 的部署、11-14 原入口恢复与成功判据，上线后结果待实际执行 |
| A7 | 真实部分文件、新尝试持久登记、完整上传回包丢失、协调器重建续接、取消及已核验包保护 |
| A8 | 两空间实际文件、真实迁移归档、旧节点离线、原执行账本保留及真实 SSH 只读链路 |

## 验证命令

从仓库根执行，使用项目现有 `.venv`：

```bash
PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_cluster_quota test_quota
PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_cluster_migrations test_cluster_migration_runner test_cluster_terminal_sessions test_projects_schedule test_projects_engine_cycles
PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest test_cluster_migration_files test_cluster_projects_terminal test_cluster_terminal test_cluster_agent test_cluster_ssh
git diff --check -- services/orchestrator/main.py services/orchestrator/cluster_quota.py services/orchestrator/test_cluster_quota.py services/orchestrator/test_quota.py
```

测试均使用合成身份、原真实消费器、临时 SQLite 和文件。新用例首先证明原缺陷可复现。涉及并发的验证使用确定性同步，避免靠 sleep 竞争。按实际运行记录结果；完整服务测试仅在聚焦结果及变更影响要求时追加。

## 检查重点

- 写锁／事务／连接关闭与既有锁序一致；网络不进入全局数据库写锁。
- 仅合法系统路径可交接，账号／身份／环境与当前归属分别核对。
- 同路径重复消费保持游标；不同位置不沿用不兼容的文件身份或字节进度。
- 重读历史文件保留较新窗口、认证门禁和恢复机会；迟到消费不能覆盖新位置。
- 修复后原启动／恢复仍执行全套门禁，原工程通过事实和计划配置保持。
- 上传新尝试先登记后执行，旧部分文件与原已核验／发布操作保持。真实 SSH 覆盖新上传状态和历史抓包请求的全部白名单。
- 历史抓包按实际资料归属和空间读取；查询保持零环境准备，原活动执行未知状态继续单独核对。
- 发布步骤区分代码验证与线上已执行结果，保护生产凭据与账号身份资料。

## 回滚点

产品实现前后保留本任务的精确增量。回滚仅撤销本任务差异；当前工作区其他任务已有变更继续保留。线上回滚按 release.md 的原归属和额度事实核对执行。


## 最新远端兼容适配准备

- 只读预检基准：`origin/flower2api`，提交 `c462479a9800f71b1badd14b1f3832482608a09b`。该基准已包含前置集群实现；当前分支与该基准 ahead 2、behind 59。
- 已从实施前快照提取本任务 17 个 Python 文件增量和单独 Spec 追加，共 18 文件补丁。`main.py` 中其他会话的 `list_accounts` 改动已从补丁排除。
- 补丁、逐文件前后版本、哈希清单和工作区只读计划位于 `.trellis/.runtime/node-migration-01a1f273-handoff/`。
- 在临时目录导出的上述远端文件上执行 `git apply --check`，发现五个文件的补丁上下文重叠：`cluster_migration_io.py`、`cluster_migration_runner.py`、`cluster_agent_client.py`、`cluster_ssh.py`、`test_cluster_migration_files.py`。下一步按最新定义适配，并验证适配后的差异。
- 用户明确选择在当前工作区、当前分支 `flower2api` 内继续。此前独立工作区计划已取消。提取的任务补丁与逐文件快照继续用于精确归属核对。
- 当前工作区只读归属审计：664 个 dirty 文件内容与远端相同；110 个在远端存在且内容有差异；478 个仅在当前工作区存在。整合包含多个任务的共享变更，整合范围须与五项修复提交范围分别核对。详细结果位于运行时材料的 `current-workspace-audit.json`。
- 当前工作区后续顺序：收敛现有分支的远端整合范围；按本任务补丁核对五处重叠；复验实际整合结果；按精确 Git 计划进入提交门禁；按 release.md 完成部署及账号恢复验证。
- 当前 182 用例及 Check-All 结果对应源工作区实现。新基准上的适配验证结果按实际执行补记。


## 当前工作区整合与补充修复

- 远端预览基准更新为 `58e707e9b3e0fc43f4dd032fb6546f0a78abd7c5`。通过实施前基线做三方合并，业务代码四处重叠自动合并；剩余一处为测试方法插入位置冲突，保留两组测试。
- 复核真实 `ImportActivation` 及 `NodeExecution.activate_import` 发现：新传输尝试已写入检查点，激活请求仍使用 execution 初始 transfer_id。真实节点按已发布目录和身份核对，会拒绝旧尝试。原测试替身直接回传激活参数，遗漏此边界。
- [x] 增强实际协调器回归，验证部分上传换尝试后的最终激活，以及 committed 后丢失回包、重建协调器的续接。
- [x] 激活请求读取持久化的当前 transfer 检查点；旧账本继续沿原 execution 初始值。
- [x] 在当前源码及最新远端合并预览分别验证，补记实际结果并重新检查本轮增量。
- 分支历史只读三方预检存在两个 Flower 版本记录冲突：本地 beta.21，远端 beta.19。后续整合优先保持当前已安装 beta.21 及其真实锁定记录，具体 Git 动作单独进入精确计划。


### 本轮实际验证及提交边界

- 增强测试在修复前，两条真实协调器用例均因激活 transfer_id 不等于已准备尝试而失败。修复后当前源码 `test_cluster_migration_runner test_cluster_migration_files test_cluster_migrations` 共 34 项通过，28.513 秒。
- 最新远端基准合并预览执行原 12 个模块回归，共 186 项、123.714 秒。首次导出缺少 images 构建上下文，导致其中三个测试、十处错误；其余 183 项通过。补齐同一提交的 worker／sidecar 构建上下文后，三个受影响测试重验通过，0.399 秒。合并预览去重覆盖 186 项通过。
- 远端预览单独迁移协调器回归 19 项通过，19.561 秒。当前业务修复与上游画像传输、SSH操作白名单及新增scratchpad迁移测试兼容。
- 17 个 Python 文件语法解析通过；18 文件完整补丁逆向 `git apply --check` 通过；`git diff --check` 及 Spec 空白检查通过。
- 本轮全面检查三维通过，CHK=0、FBK=0。Spec结果 written，补齐新尝试最终激活及 committed 后恢复合同、错误矩阵、场景和测试断言。
- 最新兼容补丁 `.trellis/.runtime/node-migration-01a1f273-integration/compatibility.patch`，逐文件哈希及真实测试证据见同目录 `verification.json`。原交接包继续保留历史版本。
- 当前分支仍为 `flower2api`，ahead 2、behind 60。物理任务GC提交经只读审计 verified；已有 `1a031b939c2c6f7371ea8b0424dcd6bab80bda30` Flower beta.21升级提交涉及14个受管文件，属于原有任务之外的历史提交。普通推送的归属需用户确认。
- 实际分支整合、提交与部署继续按对应门禁推进。当前186项证据属于合并预览，分支整合后的内容须与其核对后使用。


### 当前分支待提交合并（用户已确认升级归属）

- 用户明确回复“纳入”，授权现有 Flower beta.21 升级提交随本次后续推送发布。当前版本与锁定记录保持 beta.21。
- 已冻结合并父提交：本地 `1a031b939c2c6f7371ea8b0424dcd6bab80bda30`，远端 `166ccdc1ed1258aa277e21a84470b4bdd9f5599a`。远端相对已验证基准新增的一个提交仅调整 CI 物理退出观察窗口。
- 对原工作区 1252 个 dirty 文件保存完整逐文件快照，并保存 Git stash 收据 `d440a956d73b1e02b39c8be5eeb732067f48ba0f`。随后用 `git merge --no-commit --no-ff -Xours` 准备分支合并，冲突清零；逐文件恢复原内容并核对 SHA256。
- 已准备合并的索引树为 `e043912dcc39ea781711664d9d7b6553f770262c`。在独立索引副本应用本任务18文件补丁后，提交预览树为 `390d67d082c41e48a4cf9bd2d3b72899033164ff`，全部18文件 SHA256 与实际测试预览一致。
- 为保留同文件内的其它会话修改，拟采用索引补丁方式完成当前双父合并：在已核对索引应用 `compatibility.patch`，核对最终树和1124个first-parent文件后执行合并提交。该操作仅写待提交索引；工作区中的572处后续dirty内容继续保留。具体命令与范围进入本轮人工精确确认。
- 整体 HEAD→索引空白检查发现远端既有研究日志的CR、尾空白和EOF空行。保留日志原始证据字节；以远端父提交为基准检查本地新增差异通过。该检查口径在人工Git计划中明确确认。
- 本轮计划为一个业务合并提交及一个独立任务记录提交。实际commit/push、任务完成态和Close由精确计划执行后按真实结果写入。


### 已确认计划的本地执行与远端记录续接

- 用户明确确认索引补丁提交方式及原始日志检查口径。已按原计划创建业务双父合并提交 `c8909a11eac110cb430d407e27ec592762d3f78a`；树为 `390d67d082c41e48a4cf9bd2d3b72899033164ff`，1124个first-parent路径与计划完全一致。572处保留差异逐项SHA256核验通过。
- 确认等待期间，远端新增 `a861d9b503e87058afc93deeee6296ab21864650`，只更新 `11-19-agy-ci-prepare-timeout` 的6个任务记录文件。已准备无冲突待提交合并，暂存文件逐字节等于远端对应文件，整体暂存空白检查通过。
- 这次续接的父提交为 `c8909a11eac110cb430d407e27ec592762d3f78a` 与 `a861d9b503e87058afc93deeee6296ab21864650`，暂存树 `d119891e7c73a3017bfac733799dc42d42482793`。业务代码与18文件修复内容保持已验证版本。
- 续接只需完成6文件记录合并、推送已有修复及已纳入升级，然后按原计划单独提交当前任务9个记录文件。当前任务完成态与Close在业务推送成功后由helper原子写入。


### 业务交付已推送

- 修复合并提交 `c8909a11eac110cb430d407e27ec592762d3f78a` 与记录续接合并 `5e356e00f13f2807a83574c91d986c44ace2a0d3` 已成功推送至 `origin/flower2api`。用户确认纳入的 Flower beta.21 升级及已验证自动GC随同发布。
- 修复提交的父提交、树哈希、1124个first-parent文件范围及18文件验证哈希均与确认计划一致。记录续接的6个文件逐字节等于原远端记录。
- 推送后572处保留改动再次逐项SHA256核对一致，暂存区为空。原工作区1252份快照与stash收据保留。
- 当前任务9个记录文件按同一已确认计划同步完成态与Close，再独立提交和推送。生产部署及11-14恢复由release.md的上线流程承接。
