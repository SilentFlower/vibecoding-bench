# 实施进度与恢复指针

- 用户已对完整 Brief 回复“确认”；任务已通过 `task.py start` 进入 in_progress，route helper 选中 inline（个人偏好）。不能重新询问首次 Brief。
- 已读取 `trellis-route`、`trellis-before-dev`、相关规范、共享指南、Phase 2.1；实施后默认应继续 route(target=check)，当前 pre-check 无 hold。
- 产品改动在 `orchestrator/account_runtime.py`、`project_review_runtime.py`、`resource_budget.py`；验证改动在两个测试文件及 `deploy/v3/run_local_verification.py`、`verify_local.py`、`verify_project_scenarios.py`、`fixtures/mock_cli.py`。原 `account_isolation.py` 的普通创建与旧布局 reader 已满足兼容，无需修改；现有 Scheduler 的 RuntimeBusy 重排队可复用。
- 新机制：非共享 CLI 租约（不排空 API），root 私有串行交接记录，先停固定 CLI，再运行私有评审，停净后恢复同一固定 CLI，最后退租；普通及旧预留布局均核验实际配置，不创建新静态预留。已补恢复、维护唤醒及待评审优先的门禁。
- 开工前记录的 262 个既有脏文件不得改动；规划、验证及推送阶段已逐 SHA/模式/状态核对。本任务未部署生产、未调用真实模型。

## 已完成验证

- 最终组合：178 项运行器／私有评审／场景／评审协议／旧项目计划单测通过，日志 `.deploy/v3-account-review-serial-20261022/unit-runtime-final.log`。
- 另新增跨批次1项与缺失交接记录1项，共180个不同用例；最新保护路径相关27项已重跑通过，日志 `unit-private-review-guard-final.log`。27项与组合测试重叠，不重复相加。
- 部署工具30项通过（工具输出已留）；此前79／119／106／23项为迭代期间的有效子集，不重复相加。
- 本地衍生双镜像 `.deploy/v3-account-review-serial-20261022/manifest-d.json`，release `account-review-serial-local-20261022-d`。本次运行器和账号脚本覆盖当前源码，沿用同一 cc2api commit 的本地二进制，只作隔离验证，不是正式发布构建。
- SDK/测试解释器：`.deploy/project-iteration-repairs/venv/bin/python`；实际 Chrome 位于 `/usr/bin/google-chrome`，现有浏览器脚本用 CDP/websockets，不依赖该 venv 中的 Playwright。

## 实际发现并修正的验证问题

1. 第一衍生镜像覆盖脚本后漏执行权限，容器启动失败；已按生产 Dockerfile 的 chmod 恢复权限。保留 build-a 和首轮失败日志。
2. 旧验证夹具在登录前已绑定 account_id，未真正覆盖新号草稿；已调整元数据为 account_id=NULL，经 begin_login、commit_login 后再核同环境/代次/容器/指纹。
3. 登录回执最初写在 data 下，外层收集器期待 /verify 顶层；已统一顶层路径，没有移动运行中的原件强行放行。
4. C轮真实执行在 Q3 后发现“主会话消息父链冲突”；源码证据表明替身以 session＋PID＋进程内计数生成消息ID，重启 PID 命名空间后会重复。已改替身为 uuid4，保持正式父链检查。两轮采用旧替身的 D 验证已主动 SIGINT，正常清理本次标签资源；退出码130不是通过。`fixture-parent-collision.json` 是诊断记录，活跃两轮尚未出现冲突，不能把其空列表冒充已捕获冲突原件。
5. 私有挂载审计已补 host_data 路径映射，避免跨命名空间比较路径导致虚假隔离证明。

## 已结束的最终 Docker 验证

- 容量1＋失败注入／重启：exec session20978，退出0；目录 `.deploy/v3-account-review-serial-20261022/capacity-1-final-attempt-02`。6任务／8次评审通过，无执行/评审重叠，原API流保持，running/exited/missing重启恢复均通过。
- 容量2＋真实页面/API/SQLite对账：exec session45399，退出0；目录 `.deploy/v3-account-review-serial-20261022/capacity-2-browser-attempt-02`。6任务／8次评审通过，最大holder2且候选/评审不重叠，浏览器及SQLite回执通过。
- 最新缺失交接记录保护：manifest-e、exec session34826，退出0；目录 `.deploy/v3-account-review-serial-20261022/recovery-final-attempt-01`。新登录、三种私有容器恢复和交接记录缺失阻断均通过。E相对D仅补缺失记录时的恢复确认，主路径沿用上述完整链路证据；最新受影响恢复路径已在E独立实际执行。
- 完整两轮使用新的 UUID 替身和 manifest-d；运行时 `/source` 只读挂载仓库。原始回执位于各证据目录，执行结束后临时SQLite和专属容器／网络均由原验证器清理。
- 已结束的 C轮 session80098 失败，D旧替身 session38216／71084 被中止。其目录全部保留，不能复用为成功证据。
- 完整流程包含真实60秒超时和多次CLI启动；进程退出及场景／浏览器／DB回执均已核对，不涉及真实模型调用或生产数据。

## Check-All 首次发现与本轮修复

- 正式 route 为 `check-all-inline`，requested=auto、effective=full、confidence=high；新增持久状态与并发时序触发 full，pre-check hold 已清除。
- FBK-001（P1）已确定性复现：`AccountRuntime._cli_setup` 的串行状态检查和画像检查在认领前，未由同一个环境锁保护；另一线程可在此窗口停固定CLI，画像exec收到APIError409，无法作为RuntimeBusy重排队。
- 复现原件 `.deploy/v3-account-review-serial-20261022/check-profile-claim-race.json`；使用真实运行器方法、临时SQLite和容器接口替身，没有真实Docker或模型调用。结果为 cli_status=exited、raised_type=APIError、retryable_busy=false。
- 用户已回复“修复全部”，按 `trellis-check-all/references/repair-and-recheck.md` 沿当前任务续行，没有新建任务或重审初始Brief。`_cli_setup` 的状态检查、画像探针和认领已放入同一个环境锁，版本安装仍在锁外。
- 确定性并发用例 `test_review_cannot_stop_cli_between_profile_check_and_claim` 在修复前稳定产生APIError409，原件 `unit-profile-claim-before-fix.log`；修复后相关96项通过，见 `unit-profile-claim-after-fix.log`。后续给同一用例追加版本安装期间可取锁的断言，已纳入最终组合回归。
- F验证镜像为 `account-review-serial-local-20261022-f`，源码内容摘要 `61ee0b3758713fa995d24287b7e53b326218c740562e93692360391866211f49`。exec session30056退出0，目录 `.deploy/v3-account-review-serial-20261022/recovery-race-final-attempt-01`；真实画像探针、普通CLI命令、评审可重试等待、安装锁外执行及原恢复路径全部通过，`real_model_calls=0`。
- 最终组合回归 exec session70223 退出0，181项通过，用时117.093秒，日志 `unit-serial-repair-final.log`。复检沿用 `check-all-inline`，requested=auto、effective=full、confidence=high；并发时序变化按full审查，未受影响的完整D场景及30项部署测试按源码和覆盖关系复用。
- 本轮复检三维通过，FBK-001 已闭合，无剩余CHK/FBK；编译、范围内diff格式、262个既有脏文件的内容/模式/Git状态均通过。F验证器已清理全部本次容器，实际模型调用仍为0。部署后真实OAuth及首项目闭环另行验收，不以合成账号证据替代。
- DOC-002继续同步实施记录中的实际测试数和检查状态；DOC-001保留开工前证据的基线标签。Update-Spec结果written：仅更新既有backend的account-runtime-v3.md及project-iterations.md，规范diff／源码签名／写入边界核验通过。
- 用户已确认精确Push计划；9个代码／测试文件及上述2个规范已提交并推送到origin/v3，当前任务9个产物按确认范围同步独立完成记录。任务完成态及Close以task.json为准；生产部署与真实号闭环尚未执行。
- 首次Check-All时262个既有脏文件已逐SHA／模式／状态核对保持，当时HEAD为2d5a990且未提交、未推送、未部署；本轮业务推送后再次核对262个文件保持。

## 开工时记录的后续步骤（当前状态以上节为准）

1. 完成最终两轮验证；若失败先解释准确差异并修复本任务范围内问题，保留原始失败证据，不改评分或生产数据。
2. 对跨批次、普通Tasks竞争检查覆盖是否充分，必要时补针对性机制回归；避免只凭单个批次推断全部调度行为。
3. 同步 implement.md 的实际文件范围、已完成项和命令；Brief初次批准已存在，范围不变的同步不触发重审。
4. Phase 2.1 focused verification 完成后进入 `trellis-route(target=check)`，再按 `trellis-check-all` 的 depth-routing/full-profile/verification/reporting执行；当前只读取了入口SKILL，没有正式启动Check-All或生成报告。
5. Check-All之后按其停止/处置规则继续；生产部署与真实号验收不在本次实现授权内，不能报告为已完成。
