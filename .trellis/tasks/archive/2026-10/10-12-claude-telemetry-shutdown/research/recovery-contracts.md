# 本任务规范摘录

来源：`.trellis/spec/vibecoding-bench/backend/database-guidelines.md`，摘录日期 2026-10-12。原规范为权威来源；实现时若原文变化，应重新读取对应章节。摘录用于避免长文件上下文注入截断，不修改原规范。

## 原规范第 372–391 行

### 3. Contracts

- 普通、批量和养号入口创建每个 run 时，版本取 `effective_claude_code_version()`，思考预算取 `effective_runtime_effort()`；两个规范化结果都必须同时写入 `runs` 和该 run 的 scheduler task payload，新 run 的两个字段必须非空。
- 抓包入口的版本仍取 `effective_claude_code_version()`；思考预算取 `CaptureRunIn.effort_level`，空值必须回退进程启动时的 `.env` 常量 `CLAUDE_CODE_EFFORT_LEVEL`，不得读取 WebUI 普通/批量 run 的运行时覆盖。
- 抓包入口的 `permission_mode` 只允许 Claude Code 2.1.280 CLI 暴露的 `manual`、`acceptEdits`、`plan`、`auto`、`dontAsk` 与 `bypassPermissions`，缺省为 `bypassPermissions`；选定值必须同时写入 `runs.capture_permission_mode` 和 scheduler task payload。普通、批量、养号、登录、quota 与 OAuth refresh 不提供单次模式入口。
- 抓包页面必须从 `GET /api/settings/runtime-effort` 的 `allowed_efforts` 生成独立选择器，并提供“默认 `.env`”选项。该选择只覆盖当前抓包 run；窄屏布局必须换行，不能裁切选择器。
- 抓包页面的权限模式选择器默认提交 `bypassPermissions`，抓包创建响应和抓包详情都返回实际 `permission_mode`；索引暂不可用时仍须展示该快照。
- `Runner.start_run()` 必须读取 `task["claude_code_version"]`、`task["claude_effort_level"]` 和可选 `task["capture_permission_mode"]`，并分别注入 worker 环境；普通 run 缺少权限字段时固定回退 `bypassPermissions`。从创建到真正取得 semaphore 期间，即使 WebUI 覆盖或 `.env` 改变，已排队 run 仍使用创建时快照。
- 同一 task 再次运行会创建新的 run；新 run 使用再次运行时的当前有效运行身份，不继承旧 run 快照，也不修改旧 run。
- `POST /api/runs/{rid}/continue/start` 必须在启动 worker 前依次调用 `_ensure_run_claude_code_version(run)` 和 `_ensure_run_claude_effort_level(run)`；`Runner.start_continue()` 只使用 run 字典中的三个快照，不得无条件读取当前全局配置。
- continue worker 使用 `WORKER_MODE=login` 空转，真正恢复会话的是 WebSocket 路径里的独立 `claude --resume`。因此权限模式既要保存到 `ContinueSession` 并传入 exec 环境，也要在该命令上显式追加 `--permission-mode "$CLAUDE_PERMISSION_MODE"`；只给容器设置环境变量并不会自动改变 Claude CLI 权限模式。
- 历史 run 允许两个快照字段为 NULL。首次继续时，在 `_db_lock` 内重新读取数据库，并通过对应的 `WHERE id=? AND ... IS NULL` 条件各补写一次：版本取当前有效版本，思考预算取 `.env` 常量。后续继续必须复用已补写值，即使第一次 worker 启动失败或全局配置再次改变。
- 历史 run 的 `capture_permission_mode` 为空时解释为 `bypassPermissions`，无需把 Auto 推断或补写到旧会话。
- `_resolve_run_claude_code_version()` 和 `_resolve_run_claude_effort_level()` 的空值回退只用于历史测试或旧内部调用兼容；所有生产 run 创建入口都必须显式传递两个快照，不能把回退当作正常调度路径。
- run 列表/详情通过现有 `SELECT *` 返回三个快照；抓包创建响应和抓包详情必须显式返回 `claude_code_version`、`claude_effort_level` 与 `permission_mode`。抓包索引暂不可用时，详情仍必须展示这些运行身份字段。
- worker 的 `CLAUDE_CODE_EFFORT_LEVEL` 必须使用 run 快照；`PROFILE_CLAUDE_CODE_EFFORT_LEVEL` 仍使用 `.env` 常量，二者不能混用。
- 所选抓包模式只通过当前 Claude CLI 的 `--permission-mode <mode>` 生效。orchestrator 与 worker 写入账号 profile 的 `permissions.defaultMode` 必须继续保持 `bypassPermissions`，禁止把单次抓包模式持久化到后续普通 run。
- 登录、额度查询和后台 OAuth refresh 是非 run 临时 worker，没有可恢复的 run 身份，应在各自启动时读取当前有效版本，不继承某个历史 run 的快照。
- worker entrypoint 仍负责核对并安装精确版本；指定版本安装失败时 run 明确失败，不得静默退回镜像内版本。


## 原规范第 531–547 行

### 3. Contracts

- 身份由 bench ID、绑定 ID、profile 的账号/组织 UUID 构成，不使用轮换 AT/RT。run 固化 quota_identity，身份变化不得自动在新身份执行旧工作。来源为 `run:<rid>:<attempt>` 或 `continue:<sid>:<generation>`。
- sidecar 仅观察当前 OAuth AT 所属的 `api.anthropic.com/v1/messages`。内部白名单 JSONL 保存 source、identity、ts、status、额度头及有限 account_error，不保存 AT/RT 或任意错误正文。dummy key、其它域名及 OAuth 路径不能污染账号额度。
- 每窗口保存 observed_at、utilization（百分比）、reset_at（UTC 秒）、rejected、exhausted。响应头比例乘 100；秒、毫秒、带时区 RFC3339 均可解析。缺失/非法窗口保留既有事实，按窗口自身时间合并，乱序或同时间允许不能清掉拒绝；跨周期高位残留按真实允许响应归零。
- 429 的 rejected 优先，allowed 排除该窗口的高位猜测；普通 RPM 429 不形成通用耗尽。仅 seven_day_fable / 7d_oi 耗尽不阻断通用窗口。通用窗口达到 100% 或明确拒绝后阻止后续正式请求；已接受的成功流可以完成。
- 多窗口耗尽取全部 reset 及可信 retry-after 的最晚值。无可信 reset 时保持等待，不猜 now+5h/7d。明确 limit 但窗口未知时保存 unknown 补证；已有真实耗尽窗口不再追加未知阻断。
- 到期仅为 retry_ready，不写成恢复或 0%。共同门禁先认领一个已有正式执行；其真实允许响应合并后，未再耗尽才放行其它工作。执行失败释放本代认领，不能批量冲上游。
- quota_wait 是非终态，不计批次完成。自动恢复沿用 run/task/prompt、workspace/session、CLI/effort/权限/模型快照；首次额度判定前固化 execution_model，空串也属于有效快照，不能重新读取全局覆盖。恢复使用原主会话并按本次新增 JSONL 判断完成，排除子代理和复制的旧历史。
- worker 优先处理独立暂停信号，保存状态后以 43 退出。rate_limit、account_on_hold、invalid_grant 及其它 synthetic API 错误不能判 success；明确封号/invalid_grant 固化永久门禁、暂停批次并关闭养号，不按额度到期恢复。
- 停止、暂停、关闭养号/续聊、账号停用及删除优先。代次/status/父任务/stop_requested_at 必须在恢复与收口时复查；绑定和重授权的活跃检查包含 quota_wait。等待不占 semaphore 或长期 owner/profile lock。
- 共享状态为 `BENCH_DATA/quota/<aid>/state.json`，原子替换并挂只读目录。控制为 `BENCH_DATA/quota-controls/<rid>/<source_hash>/pause.json`，位于可写 workspace 外，sidecar RW、worker RO；宿主挂载使用 HOST_BENCH_DATA。sidecar 使用 QUOTA_SOURCE、QUOTA_IDENTITY、QUOTA_STATE_FILE、QUOTA_SIGNAL_FILE、QUOTA_OBSERVATIONS_FILE、QUOTA_CREDENTIALS_FILE；worker 仅消费来源和信号文件。
- 日志优先写入，再发布控制；控制携带归一化 quota_state，日志故障仍保留真实 reset 和封号分类。服务启动在清理原容器前后消费观察与控制补证，严格清理失败不得恢复。控制损坏或门禁不可读按执行失败收口。
- continue HTTP 可返回不占 worker 的等待 session；WS 的 quota_state 事件包含 status、message、resume_at、generation，running 只在 PTY 打开后通知。服务端拒绝等待期文本/二进制输入且不重放；关闭/断连取消重建。抓包 run 与抓包续聊自动恢复共同遵守串行、120 秒间隔和异常后至少 15 分钟暂停。
- accounts/run/batch API 的 passive_quota 只返回 source、known、windows、observed_at、blocked、exhausted、resume_at、retry_ready、message、account_error，不暴露内部身份或哈希；页面渲染、刷新、SSE 不触发主动查询，显式手动查询仍可更新来源为 manual 的记录。
- 配套交付 orchestrator、worker、sidecar 和 WebUI。回滚旧版前先停止等待工作并备份 SQLite；旧版不识别 quota_wait，不能将等待记录批量改为 active，不删除 profile/workspace/flows。
