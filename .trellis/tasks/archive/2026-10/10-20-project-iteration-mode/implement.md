# 项目迭代模式实施计划

## 1. 开工与范围

- [x] 以最新 `prd.md/design.md` 派生并完整展示 `brief.md`，取得首次完整方案确认。
- [x] 确认后运行 `task.py start`，进入 `trellis-route(target=implement)`；按路由结果和上层协作限制执行，不提前自行派发代理。
- [x] 进入实现前加载 `trellis-before-dev`，核对并保留现有脏改动，记录本任务精确路径范围；新旧模式的共享代码采用局部增量。

## 2. 内容库与纯契约

- [x] 新增 `orchestrator/project_library.py`：内容解码、ID／路径／摘要校验、发布版本注册、步骤与验收定义。
- [x] 新增 `project_library/` 的 100 个项目清单、可运行 seed、合成数据、每项目至少 20 步和冻结验收。
- [x] 建立十个业务方向的内容覆盖台账，逐项目核对业务核心和路线差异；共享脚手架不能替代具体实现。
- [x] 新增 `scripts/validate-project-library.py`，执行数量／依赖／摘要／内容校验、全部基线和参考路线验证；该命令已实现，不调用付费模型生成内容。
- [x] 先用少量代表项目跑通内容契约，再扩充并完整核对 100 项；中间样例不作为最终交付。

验证目标：100 份 seed 均可启动，至少 2,000 个步骤有实际行为断言；同版本两次复制字节摘要一致，非法版本或路径拒绝注册。

## 3. 数据与持久实例

- [x] 在 `main.py` 的 schema／初始化入口新增四张表和幂等迁移；保留原 topics/tasks/runs 及历史快照。
- [x] 新增 `orchestrator/project_iteration.py`：实例与尝试访问、代次条件更新、活动项目选择、有限修复、终点收口。
- [x] 实例初始路径保持 NULL；建立按内容版本和批次的元数据，不创建账号可见项目目录。
- [x] 增加只读内容版本和 checkpoint／失败现场存储，原子发布与摘要对账均在数据库锁外。
- [x] 核对账号软删除、停用、身份变化、维护与历史引用对新表的影响。

验证目标：真实 SQLite 覆盖重复创建、两个批次隔离、重复回调、旧 generation、失败上限和重启对账。

## 4. 执行与验收闭环

- [x] 通过原 Scheduler 投放 `project_iteration` run，新任务使用冻结步骤 prompt、空 topic 补充计划和原执行设置快照。
- [x] 显式接入普通任务额度策略以及新批次父状态校验，覆盖准备、恢复、收口和认证错误分支。
- [x] 修改 `account_runtime.py` 的新模式目录／会话解析和 `Runner.start_run` 前置目录行为；门禁等待时不得提前创建工作目录。
- [x] 首次实际启动才发布实例目录；后续步骤复用目录，单实例单写入，阶段轮换后可回来继续。
- [x] 新增 `orchestrator/project_verifier.py`：无凭据独立 Docker 执行、行为结果核对、有界日志与超时；不在控制进程执行生成代码。
- [x] 业务验收通过才推进路线；保存源码、数据、差异和报告。正常 CLI 退出但验收失败的尝试自动进入有限修复。
- [x] 原 runner 严格清理并释放执行后才封存和验收；终态先于清理的窗口不能触发下一步，清理失败必须阻塞。
- [x] 原步骤额度恢复沿用原 run/session；下一业务步骤使用新输入和新主会话，防止拿到共享 cwd 中上一轮的 JSONL。
- [x] 在 lifespan 中接入恢复及停止顺序，保证暂停／停止／重启不重置目录、不重复投递。

验证目标：合成 CLI／上游夹具在正式 runner 路径完成至少两步、一次验收失败修复、阶段切换返回、quota/window_wait 与停止竞争；不能把夹具结果称为真实模型通过。

## 5. API、页面与镜像

- [x] 实现 `design.md` 定义的项目库、批次、实例、尝试成果和流接口，DTO 与中文错误消息齐全；同步 cc2api 管理桥资源白名单及拒绝路径回归。
- [x] 在 `webui/index.html/app.js/style.css` 新增独立页签，复用主题、modal、cookie API、状态流与既有运行详情。
- [x] 未开始项目不提供目录入口；已开始实例展示真实状态、路线与已有目录，历史成果使用 checkpoint。
- [x] 新模式任务拒绝通过旧再次运行／续聊绕过路线；原任务相关接口和页面保持原行为。
- [x] 将项目库和新模块加入 v3 control 构建上下文，验证镜像内目录、版本摘要与源文件一致。
- [x] 页面汇总已有 token 证据，缺失明确显示，不在刷新／验收时主动发模型或 usage 探测。

## 6. 验证计划与命令

以下脚本与开关已实现；实际命令使用独立虚拟环境和隔离数据，证据见第 9 节。

```bash
# 新增：内容库结构、全量基线与参考路线验证
python3 scripts/validate-project-library.py --all

# 新增：关键状态机与接口回归，使用真实 SQLite 和无凭据夹具
python3 -m unittest discover -s orchestrator -p 'test_project_*.py'

# 管理桥 Rust 回归，独立在 cc2api 目录执行 cargo fmt --check 与 cargo test --locked

# 既有后端回归与源码语法检查
python3 -m unittest discover -s orchestrator -p 'test_*.py'
python3 -m compileall -q orchestrator
node --check webui/app.js
bash -n images/worker/entrypoint.sh

# 新增：隔离堆栈验证项目模式 UI/API/DB/runner 的真实闭环
python3 deploy/v3/verify_stack.py --manifest <本地同批清单> --browser --project-iteration

# 既有：共享执行边界和原递进任务回归，分别运行
python3 deploy/v3/verify_stack.py --manifest <本地同批清单> --browser --run-boundaries
python3 deploy/v3/verify_stack.py --manifest <本地同批清单> --browser --topic-followups
```

- [x] 覆盖创建 100 实例但零目录、等待不建目录、启动仅出现一个目录、同版本不同实例摘要一致且互不污染。
- [x] 覆盖连续两步累积、阶段轮换与返回、最后 checkpoint 和当前失败现场同时保留。
- [x] 覆盖模型正常退出但验收失败、修改项目内测试不能改变控制端判定、验证基础设施故障不冒充通过。
- [x] 覆盖额度恢复、窗口关闭、认证失败、账号删除／停用、批次停止、在途清理失败与重启对账。
- [x] 覆盖重复接受、旧代次回调、上一主会话污染和文件路径越界。
- [x] 覆盖终态已落库但清理未完成、暂停与额度恢复交叉，以及暂停后继续原尝试而非新建任务。
- [x] 浏览器核对 1280／390px、明暗主题、转义、空状态、SSE 离开页签关闭和既有入口回归。
- [x] 新功能 Check-All 按 `trellis-route(target=check)` 进入；通过后同步项目契约和交付说明。

不为重复取证反复执行已通过的昂贵构建；扩测时记录对应变更或未解决问题。禁止用本地夹具宣称真实 OAuth、生产封禁改善或实际模型全路线通过。

## 7. 风险文件与回退点

| 路径／环节 | 风险与控制 |
| --- | --- |
| `main.py` 的 Scheduler/QuotaGuard/lifespan | 新类型漏门禁或恢复；逐分支映射普通策略并回归原模式 |
| `account_runtime.py` 与 worker 会话定位 | 共享 cwd 误用旧 JSONL、等待时建目录；独立验证首次启动和原步骤恢复 |
| `project_library/` | 数量充足但内容不可运行或验收空洞；全基线、参考路线、业务覆盖台账 |
| 文件版本／验收 | 覆盖已验收数据或执行不可信代码；只读快照、隔离执行、条件提交 |
| 其他任务的脏改动 | 不回滚、不整文件覆盖，实施与提交前各核对实际差异 |

运行回退优先停止新批次，保留内容库、实例、checkpoint 和已开始目录。旧二进制回退必须先收口新类型工作并通过 SQLite backup API 备份，不能删除数据或整库覆盖后续活动。

## 8. 完成边界

- 交付代码、100 项目完整内容、至少 2,000 步及上述验证证据。
- 按 `trellis-update-spec` 固化新模式、实例、目录、验收和恢复契约。
- 提交与发布分别遵循所属工作流；本次规划不自动授权生产部署、全量真实模型调用或向外部发送消息。

## 9. 本地验证证据（2026-10-20）

- 内容库：`/tmp/v3-project-library-final-validation.json`，100 项目、2,000 步、200 初始断言、6,000 参考断言通过，另确认 2,000 步均非初始版本已实现。内容摘要 `3a0ad12beaa09524f19e5a07de0111092d9782dc4b8cee073be0eec4ecf7bab9`。
- Python 全量：独立虚拟环境执行 `unittest discover -s orchestrator -p 'test_*.py'`，434 项通过，日志 `/tmp/project-mode-final-tests.log`。随后只对变化后的提示上下文、内容边界和隔离实例复跑专用 22 项，全部通过，日志 `/tmp/project-mode-focused-current-tests.log`。
- Rust：`cc2api` 内 `cargo fmt --check`、`cargo test --locked` 通过，647 项通过；1 项既有 PostgreSQL profile 测试因未提供独立 DSN 按原配置忽略，未涉及本次管理桥变更。日志 `/tmp/v3-project-iteration-cargo.log`。
- 静态检查：compileall、`node --check webui/app.js`、`bash -n images/worker/entrypoint.sh`、父子仓 `git diff --check` 通过。新公共定义文档覆盖检查无缺失；订阅接口参数说明已补全。
- 独立 Docker 验收器：初始程序通过、未实现步骤拒绝，证据目录 `/tmp/project-docker-check-ovgbj85c`。SQLite 专用回归覆盖业务修复成功、旧能力回归失败、严格释放、失败上限、阶段轮换及返回、暂停／额度交叉、账号认证与清理失败、旧代次、不可变历史及路径边界。
- 正式执行路径：`run_local_verification.py --project-iterations-only` 在批次 c 上通过 Scheduler、真实 driver/tmux、原生会话、严格清理、独立 Docker 验收与两步累积；日志 `/tmp/v3-project-iteration-execution-c.log`。使用合成 CLI 和测试作者修改夹具，不表示真实模型完成路线。
- 同批镜像：最终批次 d 的联合清单 `/tmp/v3-project-iteration-20261020-d.json`，镜像内项目库摘要与源码一致。c 到 d 仅增加长批次名称换行；最后 API 参数注释不改变执行逻辑。
- 项目页面：批次 d 的真实浏览器/UI/API/SQLite 验证通过，日志 `/tmp/v3-project-iteration-browser-d.log`；100 初始实例零目录，窗口等待／暂停／停止，已有目录跨重启保留，SSE 不重置滚动或路线展开，1280/390px 明暗主题及 XSS。截图 `/tmp/v3-project-iteration-{width}-{theme}.png` 已人工查看。
- 原模式：批次 c 的 `--topic-followups` 与 `--run-boundaries` 页面回归通过，日志分别为 `/tmp/v3-project-iteration-topic-followups.log` 与 `/tmp/v3-project-iteration-run-boundaries-retry.log`。边界场景首轮并发浏览器 CDP 超时，单独重跑通过；没有修改原验证器的超时配置。
- 全部场景使用本地合成账号与数据；未部署生产，未向真实模型发起请求，未把参考行为校验当作真实模型通过率或 token 结果。
