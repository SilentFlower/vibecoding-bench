# 专项规范摘录

本文件从当前规范按相关章节摘录，避免长文件注入截断遗漏关键契约。源文件为权威来源；实现前根据实际改动读取其他相关章节，规范变更后重建摘录。

## 绑定与养号

来源：`.trellis/spec/vibecoding-bench/backend/database-guidelines.md:175` 至第 235 行。源文件 SHA256：`04d92eacd52cf3b886ae665184ae6771eee524ec9ce33787c3526abfd192e80c`。


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


## 被动额度与原任务恢复

来源：`.trellis/spec/vibecoding-bench/backend/database-guidelines.md:498` 至第 547 行。源文件 SHA256：`04d92eacd52cf3b886ae665184ae6771eee524ec9ce33787c3526abfd192e80c`。

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



## 首次引导及 managed OAuth

来源：`.trellis/spec/vibecoding-bench/deploy/image-build-push.md:416` 至第 556 行。源文件 SHA256：`4328cde7ff43f073bb9b07ea72d9b81396919ad3809700ecb530784a096778e3`。

## Scenario: Claude 首次 Auto 默认模式推荐

### 1. Scope / Trigger

修改 worker 首屏引导、顶层配置预置或权限模式启动参数时适用。Claude Code 2.1.293 的首次 Auto 推荐菜单默认选中接受；题目注入的回车可能被菜单消费，同时将运行模式和长期默认模式改为 Auto。

### 2. Signatures

- orchestrator：`_DEFAULT_CLAUDE_TOP_CONFIG`、`_persist_default_claude_top_config(profile_dir: Path) -> None`。
- worker：`patch_top_config_gates()`、`handle_claude_startup_gates()`、`inject_tmux_prompt(buffer, text)`。
- 启动命令：`claude --permission-mode "$CLAUDE_PERMISSION_MODE"`；未设置环境变量时使用 `bypassPermissions`。
- 顶层文件：账号 `data/profiles/<account>/.claude.json`，运行副本 `$HOME/.claude.json`。

### 3. Contracts

- orchestrator 与 worker 都在已有顶层配置中写入 `"hasSeenAutoDefaultNudge": true`；该字段不属于 `.claude/settings.json`，也不表示启用 Auto 模式。
- 合并必须保留 `oauthAccount`、其他项目和 `/workspace` 已有状态。顶层文件缺失时不凭空创建账号身份，继续由终端引导检测兜底。
- 识别当前可见 pane 的 `Make auto mode your default permission mode?` 时只发送一次 `Escape`。该菜单的取消回调保留当前模式；禁止用提交题目的回车接受推荐。
- 检测到引导后，菜单消失且连续三个轮询未命中引导，才允许提交题目。75 次轮询内推荐菜单仍未清除时返回失败；调用方跳过题目注入并以非零退出。
- 任务指定的权限模式继续由创建时快照传入。跳过推荐不能把显式 `auto` / `plan` 改成 bypass；成功注入的 `TASK_PROMPT` 保持原样。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|------|------|
| 已有顶层配置缺少推荐标记或标记为 false | 补为 true，身份和已有项目字段保留 |
| 预置未生效，推荐菜单仍出现 | 发送一次 Escape，保留当前模式，等待菜单清除 |
| 菜单取消后消失 | 原样提交题目，不丢失首条 user message |
| 菜单收到取消后仍停留到轮询上限 | 启动失败，不粘贴或提交题目 |
| 本次任务显式指定 auto / plan | 保留指定模式，取消的只是首次默认模式推荐 |

### 5. Scenarios and Examples

- 正常：旧账号 profile 缺少标记，启动前补齐后直接进入 bypass 输入界面。
- 边界：配置预置未生效但出现推荐菜单，Escape 取消后提交原始题目；显式 Auto 任务仍处于 Auto。
- 错误用法：仅等待几秒后直接粘贴题目并发送 Enter，菜单可能接受 Auto 且吞掉题目。
- 正确处理：先预置顶层标记，再由首屏检测取消推荐，确认引导清除后调用 `inject_tmux_prompt`。

```json
{
  "hasCompletedOnboarding": true,
  "bypassPermissionsModeAccepted": true,
  "hasSeenAutoDefaultNudge": true
}
```

以上是顶层配置的引导字段片段，不能用于覆盖包含账号身份的完整文件。

### 6. Tests Required

- `bash -n images/worker/entrypoint.sh`。
- `orchestrator/test_main.py`：顶层配置合并后推荐标记为 true，账号身份、其他项目及当前项目字段保留。
- `orchestrator/test_worker_startup.py`：执行真实 shell 函数，验证 bypass / auto / plan 模式保留、题目原样提交、菜单未清除时禁止提交，以及 worker 合并配置不覆盖身份。
- 真实首轮验证检查 session 存在 user message，且 settings 与 TUI 的权限模式符合任务快照；只看到进程的 `--permission-mode` 参数不能证明没有被首次菜单改写。

---

## Scenario: cc2api managed OAuth worker

### 1. Scope / Trigger

- 修改 `images/worker/entrypoint.sh` 的 credentials 同步、401 恢复、task/continue 启动环境，或 orchestrator 的 managed watcher 时适用。
- 只要 bench 账号绑定了 `cc2api_account_id` 就进入 managed 模式，与是否开启定时养号无关。

### 2. Signatures

worker 环境和工作区标记：

```text
CC2API_MANAGED_OAUTH=1
/workspace/.cc2api-oauth-refresh-request.json
/workspace/.cc2api-oauth-refresh-result.json
/workspace/.bench-status.json
```

orchestrator 入口：

```python
Runner.watch_managed_oauth_refresh(run_id, account, stop_event)
Runner.sync_managed_credentials_to_worker(worker_id)
_sync_bound_account_credentials(account, min_validity_seconds, force_refresh=False)
```

### 3. Contracts

- 持久 profile 的 `.credentials.json` 保存 cc2api 当前完整 AT/RT，便于后续启动；复制进 task/continue worker 的运行副本必须删除 `refreshToken`。
- managed 模式禁止 worker 调 OAuth token endpoint，也禁止 run home `.credentials.json` 反向覆盖 profile；`settings.json` 和 `.claude.json` 仍按白名单回写。
- profile -> run home 同步只接受可解析 JSON 和有效 `claudeAiOauth.accessToken`，同步后再次删除运行副本 RT。
- worker 首次检测到 401 时只写一次 refresh request 并等待 result；orchestrator watcher 调 cc2api `force_refresh=true`，原子更新 profile 后写 result。
- watcher 成功后 worker 同步新 AT 并只注入一次重试提示；第二次 401 或 result 失败时写 `auth_failed` 并以 42 退出。
- request/result/status 文件不得包含 AT、RT、管理密码、完整 prompt 或账号身份字段；错误只保留脱敏摘要。
- managed 模式与普通模式必须在同一 entrypoint 中明确分支，不能让普通账号失去现有本地 RT 刷新和新鲜度回写能力。

### 4. Validation & Error Matrix

| 条件 | worker 行为 |
|------|-------------|
| `CC2API_MANAGED_OAUTH=1` 且 profile 有完整 AT/RT | run home 只保留 AT，不保留 RT |
| managed 运行副本产生新的 credentials | 不回写 profile credentials |
| 首次 401，watcher 成功写新 AT | 同步后注入一次重试提示 |
| watcher 返回 `invalid_grant` | 写 `auth_failed`，不调用本地 refresh |
| 第二次 401 | 直接 `auth_failed`，不再创建第二个 refresh request |
| 普通未绑定账号 | 保持原本 profile/local 双向新鲜度同步与本地 refresh |

### 5. Good/Base/Bad Cases

- Good：worker 的运行副本没有 RT，401 时由 watcher 调 cc2api 刷新；新 AT 写入 profile 后同步到运行副本，任务只重试一次。
- Base：未绑定账号不设置 `CC2API_MANAGED_OAUTH`，继续沿用原有 Claude Code RT 轮换链路。
- Bad：仅在 `warmup_enabled=1` 时设置 managed 模式；关闭养号但仍绑定的账号会恢复本地 RT 刷新，破坏单一所有权。
- Bad：managed worker 退出时把运行副本 credentials 覆盖 profile，可能把缺失 RT 或旧 AT 写回。

### 6. Tests Required

- `bash -n images/worker/entrypoint.sh`。
- 用脱敏 profile fixture 启动 managed 分支，断言 run home `refreshToken` 被删除，profile RT 保持不变。
- 模拟 profile AT 更新，断言 run home 接受新 AT 后仍无 RT。
- 模拟 request/result 文件，断言 watcher 只调用一次 `force_refresh=true`，第二次 401 进入 `auth_failed`。
- 覆盖 task、capture、continue 三条 worker 创建路径都按绑定状态注入 managed 环境。
- 扫描 workspace/status/transcript，断言不出现脱敏 fixture 中的 AT/RT 原值。

### 7. Wrong vs Correct

#### Wrong

```bash
if [ "$WARMUP_ENABLED" = "1" ]; then
  export CC2API_MANAGED_OAUTH=1
fi
```

#### Correct

```python
if account.get("cc2api_account_id") is not None:
    worker_env["CC2API_MANAGED_OAUTH"] = "1"
```

worker entrypoint 读取该变量后执行 `strip_managed_refresh_token`。是否 managed 只由绑定关系决定，养号开关只控制调度。

---



## 版本组合与回滚契约

来源：`.trellis/spec/vibecoding-bench/deploy/remote-deploy.md:621` 至第 654 行。源文件 SHA256：`2b5861f5b37335786660837b43673ad446580faf71fbd0b82feb509bfbf531c6`。

### 2. Signatures

联合回滚依赖以下配置和持久化键：

```text
vibecoding-bench SQLite:
  app_settings.key = 'claude_code_version'

cc2api SQLite:
  settings.key = 'claude_code_version_profile'
  settings.key = 'allowed_claude_code_versions'

部署配置:
  VIBEBENCH_TAG=<旧镜像 tag>
  CLAUDE_CODE_VERSION=<兼容旧网关的 CLI 版本>
```

SQLite 回滚前快照必须使用数据库 API，不能直接复制在线数据库文件：

```bash
sqlite3 "$db_path" ".backup '$snapshot_path'"
sqlite3 "$db_path" ".restore '$rollback_backup'"
```

### 3. Contracts

- 回滚前先确定 `rollback_cli_version`：它必须落在旧 cc2api 的 `allowed_claude_code_versions` 范围内，并优先等于旧 worker 镜像内实际执行 `claude --version` 的结果。
- WebUI 保存的 `app_settings.claude_code_version` 优先于 `.env` 的 `CLAUDE_CODE_VERSION`。恢复旧 vibecoding-bench 数据库后，必须显式把页面覆盖值固定为 `rollback_cli_version`；只修改 `.env` 不能保证旧 worker 使用兼容版本。
- 顺序固定为：确认无活跃 run 和残留 worker/sidecar -> 停止 orchestrator -> 快照当前 bench 数据库与部署配置 -> 恢复旧 bench 数据库并固定 CLI 页面覆盖值 -> 校验旧 Compose、旧 worker 镜像和 CLI 版本但保持 orchestrator 停止 -> 确认 cc2api 连接进入低窗口 -> 停止并快照当前 cc2api 数据库 -> 恢复旧 cc2api 数据库和镜像 -> 校验旧网关版本画像及允许范围 -> 最后启动并校验旧 orchestrator。
- 不得先回滚 cc2api，除非已经证明所有可能连入的 worker CLI 均不高于旧网关允许上限；否则会制造旧网关拒绝新 worker 的版本断层。
- 两套 SQLite 在 `.restore` 前都必须创建当前状态快照，并执行 `PRAGMA integrity_check`。快照目录权限设为 `700`，数据库快照权限设为 `600`，便于回滚失败后恢复到操作前状态。
- 回滚不得删除 Docker volume、bench `data/`、账号 profile 或 workspace。旧镜像、旧 Compose、旧数据库备份任一缺失时停止操作并回报，不得用猜测值继续。
- cc2api 切换期间 orchestrator 必须保持停止；只有旧网关 HTTP 健康、版本画像和允许范围均匹配 `rollback_cli_version` 后才能重新启动。
