# Research: 场景与评审真实Docker模拟验收入口

- Query: 怎样最小复用现有setup/fixture/helper，接入真实Scheduler→Docker→driver的schema3候选/评审模拟CLI，并验证容量1/2；如何更新account内嵌helper且不调用真实模型？
- Scope: internal；只读现有验收脚本、夹具、运行接口和镜像构建入口，只写本文件；不改产品/规范，不运行Docker、构建、模型或产品测试。
- Date: 2026-10-21

## Findings

### 1. 推荐路径与现有入口

最小路径是**复用 `run_local_verification.py` 的外层随机隔离环境，以 `verify_project_scheduling.py` 的内层setup建立新schema3专项验收函数，并给测试专用mock CLI增加schema3分支**。保留真实Runner.wait_worker、driver与机械验收；不要采用wait结束后代写源码的旧验证方式。

| 当前文件/精确入口 | 能复用的能力 | 新场景接入注意事项 |
| --- | --- | --- |
| `deploy/v3/run_local_verification.py:17`，`main() -> None` | 新随机deployment；无公网`internal=True`网络；本地mock代理/DNS/TLS；专属临时数据；控制容器挂Docker socket；精确本次标签清理。 | 当前只有`--project-iterations-only/--project-scheduling-only/--project-catalog-only`，**没有**scenario专项参数。建议加独立专项路由，勿让新场景替代旧schema1回归。 |
| `deploy/v3/verify_local.py:235`，`verify() -> None` | 建合成账号、SQLite、9.9.9缓存、真实三角色、合成登录；向专项函数传`runtime/client/account/row`。 | 目前在`:284`先普通ensure，`:348`之后才按mode分支。scenario专项必须在首次ensure时选scenario_resources，或空闲显式rebuild再ensure；不能继承无预留旧布局直接测review。 |
| `deploy/v3/verify_project_scheduling.py:18`，`verify_project_scheduling(runtime, client, account: dict, row: dict, *, catalog_only: bool=False) -> None` | 独立完整main schema、真实Scheduler/Runner/QuotaGuard、ProjectIterationManager、真实定向control、并发观察、受控循环和线程排空。 | 这是最合适的setup骨架。其create_project_fixture与start_fixture目前只懂schema1，不能原样给schema2。 |
| `deploy/v3/verify_project_execution.py:17`，`verify_project_execution(runtime, client, account: dict, row: dict) -> None` | 相似隔离DB/调度setup、暂停/续跑断言思路。 | `finish_fixture()`（`:66`）在真实wait之后向workspace补实现，再供旧验收检查；它不能证明新场景回答封存/评审交接。新专项不能复用这个替身wait。 |
| `deploy/v3/verify_local.py:92`，`wait_cli_started(runtime: AccountRuntime, client, token: str) -> str` | 检查真实exec运行、tmux pane出现`Synthetic task pane`、失败时打印本次transcript。 | 当前固定调用runtime._container(row)，只适合candidate。review应按role选runtime.reviews.container(job)，不能在固定CLI里寻找review的tmux。 |
| `deploy/v3/fixtures/mock_cli.py:21`，`run_followup_fixture() -> None` | 真tmux字节/括号粘贴；原生user/assistant父链；固定session与--session-id/--resume检查；确定性usage；模拟延迟/超时/被动quota。 | 需要在旧配置解析前分派schema3；见下文。 |

建议新增函数的名字可以是 `verify_project_scenarios(runtime, client, account, row, *, capacity)`；这是本研究建议，**当前不存在该函数或专项命令**。

### 2. 内层setup的确切复用点

`verify_project_scheduling.py:28–79` 已有可按顺序复制/提取的完整setup：

1. `ExitStack` patch `main.BENCH_DATA/HOST_BENCH_DATA/DB_PATH/PROFILES_DIR/WORKSPACES_DIR/FLOWS_DIR/CA_DIR/TOPICS_FILE`；补 `V3_ENABLED=True`、`TIMEOUT_WRAPUP_SEC=0`、`CLAUDE_CODE_VERSION='9.9.9'`；登录/续聊/养号控制器设None。使用专项SQLite文件，避免复用外层极简test.sqlite的表形状。
2. `main.init_db()`，创建 `AccountRuntime(client,data,runtime.host_data,main.get_db,runtime.fingerprint,None,main._quota_identity)`，将合成account和已确认row按真实列复制入新DB；gateway=None且账号未绑定cc2api。
3. `runner=main.Runner()`、`scheduler=main.Scheduler(runner)`、`guard=main.QuotaGuard(runner)`，patch回main全局。让scheduler.submit开启真实_execute线程；不要伪造Run终态或只直接调用state manager。
4. 加载专项schema2临时ProjectLibrary，使用实际构造器：

```text
ProjectIterationManager(data, library, database, write_lock,
    submit, settings, identity, stop_run, verifier, is_executing,
    admission=None, execution_control=None, schedule_admission=None,
    concurrency_limit=2)
ProjectVerifier(client, data: Path, host_data: Path, image: str)
```

对应传值沿旧scheduling脚本：`database=main.get_db`，`write_lock=main._db_lock`，`submit=scheduler.submit`，settings返回`claude_code_version=9.9.9,claude_effort_level=high,execution_model=''`，`identity=main._quota_identity`，`stop_run=main._stop_project_run`，`is_executing=scheduler.is_executing`，admission/control/schedule_admission沿`main._project_admission/_project_execution_control/_project_schedule_admission`。

5. `verified.set_project_iterations(manager)`；当前实现会设置 `manager.review_admission=verified.reviews.admission`（`account_runtime.py:1899`）。新专项若测试本地owner刷新，还需沿正式startup（`main.py`初始化段）设置 `manager.review_refresh=lambda account: verified.reviews.retry_owner_refresh(account,runner.refresh_account_oauth_token)`；基础正常链不必触发真实OAuth。
6. patch `main.project_iterations=manager`。沿原脚本注册 `manager.stop`、`scheduler.stop_window_waits`、`verified.heartbeat_pool.shutdown` 和 `finish_executions`：在退出patch作用域之前停止当前Run、严格cleanup并有界等scheduler._executing清空，避免后台线程落到恢复后的main.DB_PATH。
7. 真实 `manager.create_batch(... policy={'concurrency':capacity,...})`→transition start→循环manager.tick。保留原`await_condition(condition,seconds=180)`的整体有界等待/短SQLite locked重试，改成scenario/evaluation/execution/source的证据投影。

不要把所有failed Run一概当专项失败：timeout/格式错误/有限infra恢复矩阵会故意产生旧失败Run，按具体case预期核对，不能吞掉非预期失败。

### 3. 容量1/2必须同时控制的三层参数

- `main.PER_ACCOUNT_CONCURRENCY` 在main导入时从环境读取（`main.py:83`）；`Scheduler._sem(account_id)`（`:6411`）首次创建Semaphore时使用该值。
- `AccountRuntime.__init__`（`account_runtime.py:193`）从进程环境读取PER_ACCOUNT_CONCURRENCY为cli_limit，只允许1或2。
- `ProjectIterationManager(...,concurrency_limit=capacity)`和本次policy.concurrency也需要同值。

最稳妥是容量1/2分别运行两次外层随机部署，在**创建inner runner容器时**传 `PER_ACCOUNT_CONCURRENCY='1'/'2'`，确保main导入与两个AccountRuntime构造读一致；当前outer脚本未转发该环境，需小接线。只将batch.concurrency改1，不能证明账号总共享容量为1。

资源布局沿 `runtime.ensure(account, version='9.9.9', scenario_resources=True)`（真实签名还有既有可选参数）在首次创建时准备。outer当前RAM1536m/swap2048m，在新静态分配中是固定CLI640MiB、review512MiB、network256MiB、sender128MiB；这只是配置守恒，不表示目标CLI峰值已通过。容量2保留一个review子池，并不要求两个review并行。

专项最低场景：

| 容量 | 必须真正观察的事实 |
| --- | --- |
| 1 | candidate原生回答→冻结→原holder/全部进程释放→review子容器入场→原生严格JSON→review释放→任务通过/下一任务；最大活跃job=1，无持candidate等review。 |
| 2 | 至少两个独立项目；先两个candidate重叠，其中A完成后review与仍工作的B重叠；冻结/清理A不暂停B；最大活跃job<=2且只有一个review。 |
| 两者 | 同账号、同9.9.9/effort/空model快照；私有HOME/native/control正确；真实source释放；原生回答与review usage分列；没有伪造问答代码checkpoint。 |

为了使容量2重叠有确定观察窗口，测试专用fixture可给B更长的有限delay、A/review较短delay；不要依赖瞬时线程顺序碰巧出现重叠。原`control_fixture()`（`verify_project_scheduling.py:107`）检查freeze期间兄弟进程仍exists且非T/t/Z，可直接复用这一观察思路，容器按job role定位。

### 4. mock CLI的最小新增分支

现有mock的两个不能直接兼容之处：

- `run_followup_fixture()`在`:26–28`遇PROJECT_PLAN_JSON就先读取固定HOME的`.synthetic-projects/<session>.json`；review是全新私有HOME，没有这份测试文件。
- 旧plan路径在`:158–164`用正则要求`Current step: step-(\d+)`；新业务task_key/prompt不保证这个格式。

应在这两步之前根据 `plan.get('workflow_schema')==3`进入测试专用场景fixture，不改变正式driver的prompt契约。复用现有终端读入/括号粘贴逻辑与JSONL父链写入方式。

- 固定session取`plan['session_id']`；确认CLI参数--session-id或--resume与之相同；native目录仍是HOME/.claude/projects/<cwd编码>。恢复时先读已有native尾部父节点，不能从空previous开始制造另一条脱离原问题的链。
- candidate按临时fixture中的公开源码事实产生确定性回答；只写原生user/assistant证据及受控测试日志。**不要写cwd下`.synthetic-turns.jsonl`**：旧mock在`:35/:138`写这个文件，新问答allowed_paths=[]会被真实scope验收拒绝。测试日志移到专属HOME测试子树或直接用原生日志。
- review只在它的私有容器中读取固定`/input/package.json`，按真实REVIEW_IDENTITY原样回显，逐条生成rubric criterion及合法evidence，明确decision/outcome/branch_id/feedback_codes。由mock输出单个严格JSON到原生assistant.text，再由原`parse_review`和真实冻结/释放链路判定，不能直接调用manager._apply_result。
- JSONL至少提供真实形状的`type/uuid/parentUuid/timestamp/message.role/content/stop_reason='end_turn'`；用固定而明确的usage（例如输入7、输出11/评审13、独立缓存字段）让对账可检验。usage是合成证据，不是模型消费。
- 需要超时case时在mock消费输入后保留受允许的半成品并有限忙碌；让真实driver触发timeout。不要在wait后UPDATE runs SET timeout冒充运行行为。

`mock_cli.py:277–282`已有基于PROJECT_PLAN_JSON调用fixture的入口，schema3分支可放此处或run_followup_fixture最前面，必须早于旧配置读取。mock是测试挂载/缓存副本，不进入正式account镜像。

### 5. 内容与离线环境夹具的可复用边界

- `project_test_content.create_project_fixture(root: Path) -> ProjectLibrary`（`orchestrator/project_test_content.py:37`）明确生成旧schema1的100×20测试库；不能当成新schema2素材或正式内容。
- `test_project_scenario_content.scenario_fixture(root: Path) -> Path`（`:17`）可参考新catalog/project/scenarios/rubric结构，但不能原样跑Docker：其`python='3.12'`不是实际完整patch版本，artifact是假wheel，当前还未提供固定requirements。
- `prepare_scenario_python()`（`account_runtime.py:1491`）将 `platform.python_version()`与profile.python精确比较，并执行offline pip；`validate_environment()`（`project_scenario_content.py:261`）要求artifacts非空；requirements如给出也必须固定非空精确版本。`verify_native()`（`project_verifier.py:161`）同样要求非空冻结requirements。不能建议空制品/空依赖来绕过这条实际链。
- 最小可运行临时环境：用zipfile在测试目录生成一个合法纯Python wheel，含测试模块及对应dist-info的METADATA/WHEEL/RECORD；固定requirements为该测试包的`name==1.0.0`，计算真实SHA256。profile.python从本次account容器的python3实测读取，不猜patch版本。无需访问PyPI或下载真实项目依赖。
- 临时native脚本可读取候选`example.py`/冻结answer输出可比较JSON，并导入该测试wheel模块，证明独立Docker验收和offline pip真实执行。问答不改源码；若还测modify，单独指定allowed_paths与相反行为测试。
- 建两个很小的临时schema2项目供容量2重叠，一个项目可有理解任务和依赖它的方案任务。不要为了机制验收重新填满100仓或替换已物化真实内容。

### 6. 新account helper的现有构建入口

需要构建新account镜像的原因：outer已经通过`V3_WORKER_SCRIPT=/source/images/worker/entrypoint.sh`读取当前工作区driver，但account内部 `/usr/local/bin/v3-project-plan`、task_followups.py、v3-cli-control、v3-cli-quota等是镜像COPY，单挂`/source`不会更新它们。

| 现有入口 | 签名/调用方式 | 用途 |
| --- | --- | --- |
| `deploy/v3/manage.py:198` | `build(release: str, manifest_path: Path) -> None` | 冻结当前源码，复制images/account/worker/v3与orchestrator等，统一构建control/account，再生成新清单，禁止覆盖现有批次。 |
| `scripts/v3-stack` | `scripts/v3-stack build --release <唯一测试批次> --manifest <全新本地清单>` | 上述正式本地构建入口，不包含publish/up。 |
| `images/v3/Dockerfile:58`起的account target | manage内部实际`docker build ... --target account --build-arg V3_RELEASE=... --build-arg V3_PARENT_REV=... --build-arg V3_GATEWAY_REV=...` | COPY `images/account/project_plan.py`至v3-project-plan（约`:88`），task_followups.py及其它helper；复用Docker已有层缓存。 |
| `deploy/v3/verify_forwarding.py:49` | `build_verification(release, destination)`；现成CLI为`python3 deploy/v3/verify_forwarding.py --build --release <唯一批次> --manifest <全新清单>` | 复用manage源码快照/清单，但最终target替换为verification-control/verification-account，标verification_only。只有需要其本地额外CA功能时才使用；`--build`分支不执行官方CLI验收，不需要cli-binary。 |

基本scenario模拟链不需要额外CA目标：原local harness的TLS探针预期收ClientHello后失败，并没有调用真实模型。测试镜像/新清单必须同批匹配；不能把旧清单的account reference临时指向未记录的新helper镜像后声称清单一致。

### 7. 不调用真实模型的现有保障与证据落点

1. 外层 `run_local_verification.py:58`创建internal Docker网络；mock_network提供SOCKS/DNS和本地HTTP/TLS，不转发真实Anthropic模型服务；账号代理固定为本次mock IP。
2. `verify_local.py:270–276`仅将`/fixtures/mock_cli.py`复制到本次账号`cli/9.9.9/node_modules/.bin/claude`并touch `.ready`；`images/account/cli-version.sh`见ready即不执行npm安装。新review只读挂同一版本缓存，使用相同替身。
3. settings明确固定9.9.9、空model、合成账号/AT/RT；不加载生产env、已有profile或真实账号数据；不触发本地真实RT/OAuth刷新。若验刷新case，用明确mock owner回调/本地端点，不用真实凭据。
4. 保留真实Scheduler、AccountRuntime、driver、tmux、v3-project-plan、监督器、程序验收和私有review容器；仅替换产生业务回答的CLI程序。UI/质量/成本证据中标“模拟CLI”，不能把机制通过计作真实模型评分。
5. outer当前`--evidence-dir`保存manifest/runtime/runner.log与本次角色日志，但只额外复制`catalog-*`顶层报告（`:111–113`）。新专项如生成`scenario-*.json`摘要，需要扩展显式报告白名单或从runner stdout收集；不要期待临时目录退出后DB/原生日志自动保留。
6. 建议摘要保存case、capacity、固定镜像ID/helper内容摘要、实际最大job数、候选/review次数、Run/source释放、session复用、预算/用量分列和通过/失败。不输出AT/RT、隐藏package全文或rubric到共享候选路径。

### 8. 相关规范与外部资料

- `.trellis/workflow.md`及任务`implement.md`阶段6：本地模拟机制证据与真实模型/内容验收分开。
- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`：随机隔离部署、真实Docker/source监督、镜像同批、共享容量及私有证据。
- `.trellis/spec/vibecoding-bench/deploy/index.md`指向v3交付契约；本次未执行发布/部署操作。
- 外部资料：本次完全基于仓库实际脚本和方法签名，未访问外部资料。

## Caveats / Not Found

- 当前尚无可直接调用的schema3专项Docker验收函数/参数；上文新增路由和mock分支是实施建议，不是已存在能力。
- 未运行构建、容器、产品测试或真实模型；现成harness是否在当前宿主通过仍需主会话实际执行。
- 最小纯Python wheel、精确Python档案和容量2可观察延迟仍需实现；单元测试的假wheel与短版本不能代替真实离线环境证据。
