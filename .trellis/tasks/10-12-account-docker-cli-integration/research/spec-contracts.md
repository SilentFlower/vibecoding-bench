# v3 关键规范摘录

本文件为规划时原规范的逐字摘录，避免大文件注入截断。原规范是权威来源；实施前若源文件变化，重读对应位置并刷新摘录。

## 来源：.trellis/spec/vibecoding-bench/backend/database-guidelines.md:175–242


### 1. Scope / Trigger

- 修改 `accounts.cc2api_account_id`、`warmup_*` 字段、`runs.run_kind='warmup'`、养号认领/终态回调，或绑定账号 worker 启动顺序时适用。
- 目标是让 cc2api 成为绑定账号 AT/RT 的唯一刷新所有者，同时保证调度跨重启恢复且同账号不会创建并行养号 run。

### 2. Signatures

账号绑定与调度字段：

```text
accounts.cc2api_account_id             INTEGER NULL UNIQUE
accounts.warmup_enabled                INTEGER DEFAULT 0
accounts.warmup_interval_min_hours     INTEGER DEFAULT 3
accounts.warmup_interval_max_hours     INTEGER DEFAULT 5
accounts.warmup_next_run_at            REAL NULL
accounts.warmup_last_attempt_at        REAL NULL
accounts.warmup_last_run_id            TEXT NULL
accounts.warmup_last_status            TEXT NULL
accounts.warmup_last_error             TEXT NULL
accounts.warmup_auth_failures          INTEGER DEFAULT 0
runs.run_kind                           TEXT; warmup 表示养号真实 run
```

进程内串行入口：

```python
_oauth_owner_lock(account_name)
_profile_lock(account_name)
_cc2api_binding_lock
_require_cc2api_binding_available(bench_account_id, cc2api_account_id)
WarmupScheduler.trigger_account(account_id, require_due=False)
WarmupScheduler.handle_run_started(run_id)
WarmupScheduler.handle_run_terminal(run_id, expected_cc2api_account_id=None)
```

### 3. Contracts

- `init_db()` 必须先 `_ensure_column` 补齐所有绑定/养号列，再创建 `cc2api_account_id IS NOT NULL` 的唯一索引；旧账号默认未绑定且养号关闭。
- 只要 `cc2api_account_id` 非空，即使 `warmup_enabled=0`，bench 后台和 worker 也不得使用 RT 本地刷新。
- 绑定、改绑、解绑与 worker 创建共用 `_oauth_owner_lock(account_name)`；worker 必须在锁内重新读取账号、同步 cc2api 最终凭据并完成 `Runner.start_run`，绑定接口必须在同一把锁内检查 active run/continue/login 后再写 DB。
- 不同 bench 账号的绑定或改绑还必须经过 `_cc2api_binding_lock` 串行化，并在 resolve/profile 写入前调用 `_require_cc2api_binding_available`。唯一索引是最终兜底，不能等 profile 已经写入其它账号的 AT/RT 后才依赖索引报错。
- 已绑定账号调用“同步到 cc2api”时，当前 `accounts.cc2api_account_id` 是权威来源；只能校验并同步这个 ID。改绑必须走显式选择接口，不能重新按 profile 身份静默匹配到另一个 cc2api 账号。
- `_oauth_owner_lock` 可以包住 cc2api HTTP 和 profile I/O，但不得包住 `_db_lock` 下的长事务；所有 cc2api HTTP 仍在 `_db_lock` 外执行。锁顺序固定为 `owner lock -> profile lock`，禁止反向获取。
- 养号到期认领时把 `warmup_next_run_at=NULL`、状态写为 `preparing`；预同步成功后创建 queued run，但 queued run 拿到账号 semaphore 时必须再次同步，不能用“已准备”标记跳过。
- `handle_run_started` 只把仍启用且 `warmup_last_run_id` 匹配的账号写为 `running`。用户已主动关闭时保持 `off`。
- 终态后按配置随机写下一次时间；普通失败/超时/停止继续调度，连续 3 次 `auth_failed` 暂停，包含 `invalid_grant`、账号不存在/禁用或凭据结构错误的首个认证失败立即暂停。
- 终态回调必须携带本次 run 启动时的 `expected_cc2api_account_id`，并在写入认证失败计数、暂停状态或下一次时间前确认当前绑定仍相同。run 写入终态后到回调执行前允许用户改绑，旧 run 不能污染新绑定的调度状态。
- `stop_run` 把 run 写成 `stopped` 后必须立即调用终态 helper，不能等待原调度线程稍后收口。

### 4. Validation & Error Matrix

| 条件 | 数据库行为 |
|------|------------|
| 同一 cc2api ID 绑定第二个 bench 账号 | profile 写入前返回 409；唯一索引继续做最终兜底 |
| 已绑定账号同步时 profile 身份指向另一个 cc2api 账号 | 返回 409，原绑定和 profile AT/RT 保持不变 |
| 绑定切换时存在 queued/running/stopping run | 拒绝切换，原绑定不变 |
| 存在 active continue/login 会话 | 拒绝绑定切换或解绑 |
| 到期账号已有 active warmup run | 不新建 run，账号最近状态指向已有 run |
| 预同步成功但排队期间 RT 已轮换 | semaphore 后再次同步，worker 使用最终 AT/RT 快照 |
| cc2api 临时网络失败 | 不建 task/run，状态 `sync_failed`，`now + WARMUP_SYNC_RETRY_SEC` 重试 |
| 首次 `auth_failed` 含 `invalid_grant` | `warmup_enabled=0`、状态 `paused`、next 置空 |
| 用户关闭养号后旧 run 收口 | 保持 `off`，不得改成 `paused` |
| cc2api#7 的旧 run 终态前账号已改绑到 cc2api#8 | 旧回调直接返回，不修改 cc2api#8 的状态或失败计数 |

### 5. Good/Base/Bad Cases

- Good：养号 run 排队 20 分钟后获得 semaphore，启动前重新 resolve；期间 cc2api 已轮换 RT，最终 profile 和 worker 都使用新快照。

## 来源：.trellis/spec/vibecoding-bench/backend/database-guidelines.md:498–562

### 1. Scope / Trigger

- 修改额度采集、5h/7d 门禁、quota_wait、自动恢复、worker 完成判定、继续对话或相应容器挂载时适用。
- 单次、批次、再次运行、养号、抓包和继续对话共用账号事实；自动路径只消费正式请求的响应，不调用 usage、cc2api refresh_usage、查询 worker 或模型探测。

### 2. Signatures

```text
account_quota_states(account_id INTEGER PRIMARY KEY, identity TEXT,
  state_json TEXT, recovery_source TEXT, updated_at REAL)
quota_observation_cursors(source TEXT PRIMARY KEY, account_id INTEGER,
  identity TEXT, path TEXT, file_identity TEXT, byte_offset INTEGER DEFAULT 0)
runs.execution_model TEXT NULL
runs.quota_attempt INTEGER NOT NULL DEFAULT 0
runs.quota_resume_at REAL NULL
runs.quota_identity TEXT NULL
```

新表用 `CREATE TABLE IF NOT EXISTS`，四个 run 列由 `init_db()` 的 `_ensure_column()` 幂等补齐，不删除历史数据。

纯协议真实源为 `orchestrator/quota_protocol.py`，`scripts/sync-quota-protocol.py` 同步到 sidecar 独立构建上下文；两个 Dockerfile 必须复制该模块。

```python
quota_observation(headers: dict, status: int, now: float) -> dict
merge_quota_observation(existing: dict, incoming: dict) -> dict
quota_decision(state: dict, now: float) -> dict
QuotaGuard.admit(account: dict, source: str) -> bool
QuotaGuard.consume(account: dict) -> None
QuotaGuard.record_control_state(account: dict, source: str, payload: dict) -> None
QuotaGuard.recover() -> None
QuotaGuard.capture_resume_ready(run_id: str) -> bool
```

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

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 无首次观察 | 正常任务可以启动，页面显示未知 |
| 排队后才耗尽 | semaphore 后最终门禁拒绝，不创建 worker |
| 两窗口耗尽且仅一个到期 | 保持等待 |
| 明确拒绝但 reset 缺失 | 保留该窗口旧未来 reset，否则无限等待有效证据 |
| 已接受流携带 100% | 本流可完成，下一条模型请求本地阻断 |
| 控制已写但 JSONL 故障，随后重启 | 原 reset/封号分类由控制恢复，清旧容器后再调度 |
| 恢复后再次拒绝 | 同一 run 重新等待，不换题或循环探测 |
| 封号/invalid_grant | auth_failed，无额度自动恢复 |
| 等待期 WS 文本或二进制输入 | 丢弃，恢复后只接收新输入 |
| 用户停止、关闭或身份变化 | 不复活原工作 |


## 来源：.trellis/spec/vibecoding-bench/deploy/image-build-push.md:90–106

### Compose Image Wiring

`docker-compose.remote.yml` 只有 orchestrator 是 Compose service。worker / sidecar 由 orchestrator 通过 Docker SDK 启动,镜像地址分别来自 orchestrator environment 的 `WORKER_IMAGE` / `SIDECAR_IMAGE`。

因此 `docker compose ... config --images` 只输出 orchestrator 是正常行为,不能据此误判 worker / sidecar 镜像未配置。完整验证必须同时检查:

```bash
docker compose -f docker-compose.remote.yml --env-file .env.example config --quiet
docker compose -f docker-compose.remote.yml --env-file .env.example config --images
docker compose -f docker-compose.remote.yml --env-file .env.example config \
  | grep -E 'WORKER_IMAGE:|SIDECAR_IMAGE:'
```

三处值必须使用同一个 `VIBEBENCH_TAG`,并分别指向 `ghcr.io/silentflower/vibebench-{orchestrator,worker,sidecar}`。

---


## 来源：.trellis/spec/vibecoding-bench/deploy/image-build-push.md:499–508

### 3. Contracts

- 持久 profile 的 `.credentials.json` 保存 cc2api 当前完整 AT/RT，便于后续启动；复制进 task/continue worker 的运行副本必须删除 `refreshToken`。
- managed 模式禁止 worker 调 OAuth token endpoint，也禁止 run home `.credentials.json` 反向覆盖 profile；`settings.json` 和 `.claude.json` 仍按白名单回写。
- profile -> run home 同步只接受可解析 JSON 和有效 `claudeAiOauth.accessToken`，同步后再次删除运行副本 RT。
- worker 首次检测到 401 时只写一次 refresh request 并等待 result；orchestrator watcher 调 cc2api `force_refresh=true`，原子更新 profile 后写 result。
- watcher 成功后 worker 同步新 AT 并只注入一次重试提示；第二次 401 或 result 失败时写 `auth_failed` 并以 42 退出。
- request/result/status 文件不得包含 AT、RT、管理密码、完整 prompt 或账号身份字段；错误只保留脱敏摘要。
- managed 模式与普通模式必须在同一 entrypoint 中明确分支，不能让普通账号失去现有本地 RT 刷新和新鲜度回写能力。


## 来源：.trellis/spec/cc2api/backend/service-architecture.md:178–191

### 3. Contracts

- `Account.concurrency` 的外部语义是标准并发槽位数；管理员填 `5` 表示最多 5 个普通请求，而不是内部单位数。
- 内部单位固定为 `1 标准槽 = 2 内部单位`；普通/Opus 请求占 2 单位，Haiku 请求占 1 单位。不要把 `concurrency` 存成或显示成翻倍值。
- Gateway 正常上游路径必须先计算 `slot_units` 并获得 `AccountSlotPermit`，再调用 `acquire_account_rpm`。
- 本地拦截路径（assistant prefill、warmup、Auto Mode classifier、telemetry 假响应等）必须在账号槽位获取前返回，不得新增并发槽位消耗。
- 处于 `AccountQueue::acquire(...)` 等待阶段的请求不得递增 RPM。
- 等待队列容量仍按请求数计，保持 `2 × concurrency` 个等待请求；不要按半槽权重扩大为 `4 × concurrency`。
- `AccountQueue` 必须使用 `Semaphore::acquire_many_owned(slot_units)` 保持 Tokio semaphore FIFO 公平性。若队首普通请求需要 2 单位而当前只剩 1 单位，后续 Haiku 请求不得绕过队首。
- 调度的满载判断和 `concurrency_pct` 必须按内部单位计算：`(active_units + waiting_units) / max_units × 100`。
- `QueueWaitError::QueueFull` / `QueueWaitError::Timeout` / `QueueWaitError::Closed` 发生时，该账号 RPM 不得变化。
- 非粘性请求拿到槽位后若 RPM 饱和并返回 `AppError::ServiceUnavailable`，必须释放当前账号槽位并排除该账号后重新选号。
- 粘性请求拿到槽位后若 RPM 饱和，仍按 `acquire_account_rpm` 的等待/本地 429 语义处理，不得随意切号。


## 来源：.trellis/spec/cc2api/backend/service-architecture.md:890–895

## 后台任务边界

- `UsagePollerService` 负责 OAuth usage 主动刷新，不应写网关热路径状态。
- `PrimePollerService` 负责峰值预热调度，发出的请求也可能命中网关治理规则；新增拦截规则时必须说明是否影响预热。
- Telemetry 自动代发必须遵守隐私边界，不发送 prompt、tool input、响应正文、token 或 cookie。
