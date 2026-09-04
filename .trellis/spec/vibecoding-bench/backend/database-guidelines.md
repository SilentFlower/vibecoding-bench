# Database Guidelines

> 本项目数据库的写法与约定。

---

## Overview

- **数据库**:SQLite 单文件,位于 `data/db.sqlite`(容器内为 `/data/db.sqlite`)
- **驱动**:Python 标准库 `sqlite3`,**不用任何 ORM**(无 SQLAlchemy / Tortoise / Peewee)
- **schema 定义**:`orchestrator/main.py` 顶部一个 `_SCHEMA` 字符串常量,内含 `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`
- **migration**:**没有 migration 系统**。P1 阶段表结构小、迭代少,直接改 `_SCHEMA` + 手动 ALTER 或推倒重来。P2 真要 migration 时再引入(候选:yoyo-migrations / 手写脚本)
- **连接**:每次操作 `get_db()` 新建一个 `sqlite3.Connection`,**用完显式 close**(放进 `try/finally`)
- **行类型**:`conn.row_factory = sqlite3.Row` —— 取出的行可以按列名访问(`row["name"]`),返回前 `dict(row)` 转为 JSON 友好
- **并发写**:全局 `_db_lock = threading.Lock()` 保护所有写入(SQLite 写本来就是串行的,加锁是为了让 Python 这一层也不会拿到 `database is locked`)

---

## Query Patterns

### 写入(必须加 `_db_lock`)

```python
with _db_lock:
    conn = get_db()
    try:
        with conn:                       # with conn → 自动 commit / rollback
            cur = conn.execute(
                "INSERT INTO accounts(name, profile_path, enabled) VALUES(?,?,?)",
                (name, path, 1),
            )
            return {"id": cur.lastrowid}
    except sqlite3.IntegrityError as e:
        raise HTTPException(400, f"account exists: {e}")
    finally:
        conn.close()
```

### 读取(不需要 `_db_lock`)

```python
conn = get_db()
try:
    rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
    return [dict(r) for r in rows]
finally:
    conn.close()
```

### 动态字段 UPDATE(`Scheduler._update` 模式)

调度器要按需更新 runs 的若干列,用这种"列名拼字符串、值用占位符"的写法:

```python
def _update(self, run_id: str, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)   # 列名拼接(只接受内部传参,不来自用户)
    params = list(fields.values()) + [run_id]
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                conn.execute(f"UPDATE runs SET {cols} WHERE id=?", params)
        finally:
            conn.close()
```

> **安全要点**:列名是 f-string 拼接,**只允许来自代码内部 `**fields` 的 keyword**,**绝不能**把用户输入(如 query 参数 / body 字段)直接作为列名拼进 SQL。

### 参数化:永远用 `?`,绝不字符串拼接值

```python
# ✓ 正确
conn.execute("SELECT * FROM tasks WHERE id=?", (tid,))

# ✗ 错误(SQL 注入)
conn.execute(f"SELECT * FROM tasks WHERE id={tid}")
```

---

## Migrations

**P1 无 migration**。改 schema 的当前流程:

1. 直接编辑 `_SCHEMA` 字符串里的 `CREATE TABLE IF NOT EXISTS`
2. 如果是**新表**或**新增 nullable 列**,加 `ALTER TABLE ... ADD COLUMN ...` 到 `init_db()` 末尾,用 `try/except sqlite3.OperationalError: pass` 兜底(列已存在会报错)
3. **破坏性变更**(改列类型、改约束):停服务,删 `data/db.sqlite`,重启自动重建。**P1 数据不重要,允许丢**
4. P2 持久化数据有价值后,再引入正式 migration 框架,届时把上面这条约定作废

`init_db()` 永远幂等:重启不应破坏现有数据。

---

## Naming Conventions

- **表名**:复数 + 小写 + 下划线,如 `accounts` / `tasks` / `runs`
- **主键**:除 `runs` 外都用 `id INTEGER PRIMARY KEY AUTOINCREMENT`。`runs.id` 是 `TEXT PRIMARY KEY`(`uuid.uuid4().hex[:12]`,12 位 hex 短 ID,方便 URL / 日志显示)
- **外键列**:`<table>_id`,如 `account_id` / `task_id`。**SQLite 默认不校验外键**(若需校验自行 `PRAGMA foreign_keys=ON`),但仍写 `FOREIGN KEY(...) REFERENCES ...` 表达意图
- **时间戳**:`created_at REAL DEFAULT (julianday('now'))` / `started_at REAL` / `ended_at REAL`,Julian Day 浮点数,客户端按需转。**不存时区**,默认 UTC
- **布尔**:存 `INTEGER`(0 / 1),Python 侧用 `bool(int(...))` 或 `int(bool)` 互转
- **索引**:`idx_<table>_<col>`,如 `idx_runs_status` / `idx_runs_account` / `idx_runs_task`。只为 SSE 流端点和 list 端点的 ORDER BY / WHERE 列加索引,**不要预先全列建索引**

---

## Account Soft Deletion Contract

### 1. Scope / Trigger

账号删除必须区分"无历史引用的物理删除"和"有历史引用的软删除"。只要账号被 `tasks`、`runs` 或 `task_batches` 引用,就不能直接硬删账号行,否则历史任务 / 运行记录会留下无法解释的 `account_id`。

### 2. Signatures

- DB: `accounts.deleted_at REAL`
- 可用账号 SQL: `SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL`
- 账号列表 API: `GET /api/accounts` 默认只返回 `deleted_at IS NULL`
- 删除 API: `DELETE /api/accounts/{aid}` 无引用时物理删除;有引用时 `UPDATE accounts SET enabled=0, deleted_at=? WHERE id=?`

### 3. Contracts

- 软删除账号仍保留 `accounts.id` 和 `accounts.name`,用于历史任务 / 运行记录引用。
- 软删除账号必须退出所有新工作入口:创建任务、创建批次、抓包 run、旧任务再次运行、继续对话、额度查询、后台 OAuth access token 刷新。
- 同名重新添加 / 登录时,如果存在同名软删除账号,恢复原行并设置 `enabled=1, deleted_at=NULL`,避免 `accounts.name UNIQUE` 造成不可恢复的重复账号错误。
- 前端依赖 `/api/accounts` 作为可选账号来源;后端过滤后,账号页和下拉应自然隐藏软删除账号。

### 4. Validation & Error Matrix

| 条件 | 行为 |
|------|------|
| 删除账号无 `tasks` / `runs` / `task_batches` 引用 | `DELETE FROM accounts WHERE id=?` |
| 删除账号仍有历史引用 | `enabled=0, deleted_at=<now>` 并返回删除成功语义 |
| 新工作入口收到软删除账号 ID | 返回 `404 account not found or disabled`,不启动 worker / sidecar |
| 后台 OAuth refresh 扫描账号 | 只查询 `enabled=1 AND deleted_at IS NULL` |
| 同名软删除账号重新添加 / 登录 | 恢复原 `accounts.id`,清空 `deleted_at` |

### 5. Good/Base/Bad Cases

**Good**:删除有历史 run 的账号后,账号页和任务下拉不再出现该账号,后台 refresh 不再读取它,历史运行列表仍可用 `acc#<id>` fallback 展示。

**Base**:删除没有任何历史引用的测试账号时,直接物理删除账号行。

**Bad**:只把 `enabled=0` 当删除。这样账号仍会出现在 `/api/accounts` 和前端下拉里,用户看到"已停用"但没有真正从视图移除。

**Bad**:有历史引用时直接 `DELETE FROM accounts`。SQLite 默认不强制外键,这不会立刻报错,但会制造孤儿任务和运行记录。

### 6. Tests Required

- 旧 DB 启动后 `accounts.deleted_at` 会被 `init_db()` 幂等补列。
- 删除有历史引用账号后,`/api/accounts` 不返回该账号,`_get_available_account()` 返回 `None`。
- 软删除账号调用额度查询、创建任务、创建批次、抓包、旧任务 run、继续对话时返回 404,且不启动 worker / sidecar。
- 同名重新添加 / 登录软删除账号时恢复原 `accounts.id`,并清空 `deleted_at`。
- 删除无历史引用账号时,账号行被物理删除。

### 7. Wrong vs Correct

#### Wrong

```python
row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
```

#### Correct

```python
row = conn.execute(
    "SELECT * FROM accounts WHERE id=? AND enabled=1 AND deleted_at IS NULL",
    (account_id,),
).fetchone()
```

---

## Scenario: cc2api 绑定与定时养号状态机

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
- Good：两个 bench 账号同时尝试绑定同一个 cc2api ID，绑定锁让其中一个先完成，另一个在 resolve 和 profile 写入前收到 409。
- Base：未绑定老账号继续走原本本地 OAuth 刷新和普通 run 路径，所有新增列保持默认值。
- Bad：在认领阶段同步一次后给 task 写 `credentials_prepared=true`，真正启动时跳过同步；排队期间轮换的 RT 会被遗漏。
- Bad：解绑只检查一次 DB 后直接 UPDATE；检查与 worker 创建之间的竞态会同时产生 cc2api 和 Claude Code 两个 RT 刷新所有者。
- Bad：已绑定账号点击同步时重新按 UUID/邮箱匹配，先写入新账号凭据，再由 DB 拒绝改绑；这会让 profile 与绑定 ID 短暂或长期不一致。
- Bad：终态回调只检查 `warmup_last_run_id`，不检查 run 启动时的绑定 ID；旧 `invalid_grant` 可能暂停刚改绑的新账号。

### 6. Tests Required

- 旧 SQLite 幂等升级后断言新增列和唯一索引存在。
- 并发模拟慢旧 resolve 与快新 resolve，断言 resolve + profile 写入整体串行且最终文件是新快照。
- worker 创建阶段阻塞并并发解绑，断言解绑等待 owner lock，随后因 active run 返回 409。
- 覆盖已绑定账号同步不会重新匹配其它 cc2api ID，错误前后 profile AT/RT 不变。
- 覆盖重复绑定在 resolve/profile 写入前返回 409，且未调用 cc2api 凭据解析。
- 覆盖 active run、continue、login 分别阻止绑定切换/解绑。
- 覆盖 warmup 预同步后启动前再次同步、账号状态进入 `running`、停止后立即安排 next。
- 覆盖首个永久认证错误立即暂停、第三个普通 `auth_failed` 暂停、用户关闭后终态保持 `off`。
- 覆盖旧绑定 run 终态晚于改绑完成时，新的绑定状态、next 和认证失败计数均保持不变。

### 7. Wrong vs Correct

#### Wrong

```python
snapshot = cc2api_client.resolve_credentials(account_id, 2400)
with _profile_lock(name):
    write_profile(snapshot)
```

resolve 在锁外时，慢旧响应可能最后写回并覆盖新凭据。

#### Correct

```python
with _profile_lock(name):
    snapshot = cc2api_client.resolve_credentials(account_id, 2400)
    write_profile_locked(snapshot)
```

绑定所有权切换还必须再包外层 `_oauth_owner_lock(name)`，并让 worker 启动使用同一把 owner lock。

#### Wrong：终态回调使用当前绑定作为更新条件

```python
account = load_account(run["account_id"])
update_warmup_state(account["cc2api_account_id"], run["status"])
```

run 进入终态后、回调执行前可能已经改绑；此时“当前绑定”不是该 run 的凭据所有者。

#### Correct：用 run 启动时的绑定快照保护回调

```python
def handle_run_terminal(run_id, expected_cc2api_account_id):
    account = load_account_for_update(run_id)
    if account["cc2api_account_id"] != expected_cc2api_account_id:
        return
    update_warmup_state(account, run_id)
```

---

## Scenario: run Claude Code 版本快照与继续对话

### 1. Scope / Trigger

- 修改 `runs.claude_code_version`、Claude Code 版本运行时设置、普通/批量/养号/抓包 run 创建、调度 payload、worker 启动或继续对话时适用。
- 版本属于 run 的可恢复执行身份。页面覆盖或 `.env` 是创建新 run 时的输入，不能在排队启动或继续历史会话时重新解释，否则同一会话会因全局设置变化漂移到另一个 CLI 版本。

### 2. Signatures

数据库字段与兼容升级：

```text
runs.claude_code_version TEXT NULL
init_db() -> _ensure_column(conn, "runs", "claude_code_version", "TEXT")
```

版本解析与 worker 边界：

```python
effective_claude_code_version() -> str
_resolve_run_claude_code_version(value: Optional[str]) -> str
_ensure_run_claude_code_version(run: dict) -> str
Runner.start_run(run_id: str, account: dict, task: dict) -> tuple[str, str]
Runner.start_continue(
    sid: str,
    run: dict,
    account: dict,
    session_id: str,
) -> tuple[str, str]
```

相关 API：

```text
POST /api/tasks/{tid}/run
POST /api/captures/run
POST /api/runs/{rid}/continue/start
GET  /api/runs
GET  /api/runs/{rid}
GET  /api/runs/{rid}/capture
```

### 3. Contracts

- 普通、批量、养号和抓包入口必须在创建每个 run 时调用一次 `effective_claude_code_version()`，把规范化结果同时写入 `runs.claude_code_version` 和该 run 的 scheduler task payload。新 run 的字段必须非空。
- `Runner.start_run()` 必须优先读取 `task["claude_code_version"]`。从创建到真正取得 semaphore 期间，即使 WebUI 覆盖或 `.env` 改变，已排队 run 仍使用创建时快照。
- 同一 task 再次运行会创建新的 run；新 run 使用再次运行时的当前有效版本，不继承旧 run 快照，也不修改旧 run。
- `POST /api/runs/{rid}/continue/start` 必须在启动 worker 前调用 `_ensure_run_claude_code_version(run)`；`Runner.start_continue()` 只使用返回并写回 run 字典的快照，不得无条件调用当前全局有效版本。
- 历史 run 允许 `claude_code_version IS NULL`。首次继续时，在 `_db_lock` 内重新读取数据库；若仍为空，则把当前有效版本通过 `WHERE id=? AND claude_code_version IS NULL` 补写一次。后续继续必须复用已补写值，即使第一次 worker 启动失败或全局版本再次改变。
- `_resolve_run_claude_code_version()` 的空值回退只用于历史测试或旧内部调用兼容；所有生产 run 创建入口都必须显式传递快照，不能把该回退当作正常调度路径。
- run 列表/详情通过现有 `SELECT *` 返回快照；抓包创建响应和抓包详情必须显式返回 `claude_code_version`，便于把运行目标版本与 flow 中观察到的 `cc_version` 分开核验。
- 登录、额度查询和后台 OAuth refresh 是非 run 临时 worker，没有可恢复的 run 身份，应在各自启动时读取当前有效版本，不继承某个历史 run 的快照。
- worker entrypoint 仍负责核对并安装精确版本；指定版本安装失败时 run 明确失败，不得静默退回镜像内版本。

### 4. Validation & Error Matrix

| 条件 | 行为 |
|------|------|
| 新建普通/批量/养号/抓包 run | DB 行和 scheduler payload 保存同一个非空版本 |
| run 排队后页面覆盖或 `.env` 改变 | 已排队 run 使用原快照；之后新建 run 使用新版本 |
| 已有快照的 run 点击继续 | continue worker 使用原快照，不读取当前全局版本 |
| 历史 run 快照为空 | 首次继续解析当前有效版本并原子补写；后续固定使用补写值 |
| 并发触发同一历史 run 的首次继续 | `_db_lock` 内重新读取，只有第一个空值补写生效，后续读取已保存值 |
| run 中保存的版本格式无效 | 继续接口返回 400，不启动 worker |
| run 不存在、未结束或账号不可用 | 沿用 continue 接口的 404/400，不执行版本补写和 worker 启动 |
| worker 无法安装快照指定版本 | run/continue 明确失败，不降级到镜像默认版本 |

### 5. Good/Base/Bad Cases

- Good：以 `2.1.260` 创建抓包 run，关闭 worker 后把页面设置改成 `2.1.257`；继续该 run 仍启动 `2.1.260`，随后新建的 run 使用 `2.1.257`。
- Good：历史 NULL run 首次继续时当前版本为 `2.1.260`，即使启动失败并在第二次继续前把全局版本改成 `2.1.257`，第二次仍使用已补写的 `2.1.260`。
- Base：页面没有覆盖值时，新 run 使用 `.env` 的 `CLAUDE_CODE_VERSION`；页面保存合法版本后，只有之后创建的新 run 使用覆盖值。
- Bad：在 `Runner.start_run()` 或 `Runner.start_continue()` 中直接调用 `effective_claude_code_version()`。排队等待或关闭后继续会把可变全局配置误当成 run 身份。
- Bad：只把版本放进内存 task payload，不写入 `runs`。进程重启或继续历史会话后无法恢复原版本。
- Bad：历史 NULL run 每次继续都回退当前版本但不补写。相同 Claude session 会随页面设置反复漂移。

### 6. Tests Required

- 新库断言 `_SCHEMA` 含 `runs.claude_code_version`；旧 SQLite 连续执行两次 `init_db()` 后断言列存在且数据完整。
- 普通、批量、养号和抓包四类创建入口分别断言 DB 快照非空，并与 scheduler payload、抓包创建响应完全一致。
- run 创建后修改 `effective_claude_code_version()` 的返回值，再启动 worker，断言环境变量 `CLAUDE_CODE_VERSION` 仍为创建快照。
- 覆盖抓包 run 以 `2.1.260` 创建、当前全局改为 `2.1.257` 后继续，断言 continue worker 为 `2.1.260`。
- 历史 NULL run 首次继续补写 `2.1.260`，全局改为 `2.1.257` 后再次调用，断言 DB 和返回值仍为 `2.1.260`。
- 同一 task 在设置变化前后创建两个 run，断言旧 run 保留旧版本，新 run 保存新版本。
- 登录、额度查询和 OAuth refresh 测试断言它们使用各自启动时的当前有效版本，不受 run 快照约束。

### 7. Wrong vs Correct

#### Wrong

```python
def start_continue(self, sid, run, account, session_id):
    claude_code_version = effective_claude_code_version()
    worker = self.client.containers.run(
        WORKER_IMAGE,
        environment={"CLAUDE_CODE_VERSION": claude_code_version},
    )
```

继续对话发生时全局设置可能已变化，这会让原 Claude session 换用另一个 CLI 版本。

#### Correct

```python
@app.post("/api/runs/{rid}/continue/start")
def continue_run_start(rid: str):
    run = dict(run_row)
    _ensure_run_claude_code_version(run)
    session = continue_manager.start(run, account)

def start_continue(self, sid: str, run: dict, account: dict, session_id: str):
    claude_code_version = _resolve_run_claude_code_version(
        run.get("claude_code_version")
    )
    worker = self.client.containers.run(
        WORKER_IMAGE,
        environment={"CLAUDE_CODE_VERSION": claude_code_version},
    )
```

先在持久化边界确保快照存在，再由 worker 启动边界消费同一个值，才能保证排队、进程重启和继续会话后的版本一致性。

---

## Common Mistakes

| 反模式 | 为什么不要 | 怎么改 |
|--------|------------|--------|
| 在 `with _db_lock:` 里再起一个 `with _db_lock:` | 死锁(threading.Lock 不可重入) | 拆开:外层只做 DB,业务/外部调用挪出 lock 外 |
| 写操作不加 `_db_lock` | 多线程 worker 可能撞 `database is locked` | 任何 `INSERT/UPDATE/DELETE` 都加 lock |
| 读操作加 `_db_lock` | 读读互不冲突,加 lock 拖慢 SSE 1Hz 轮询 | 只读路径不加 lock |
| 忘记 `conn.close()` | SQLite 连接泄漏,长期跑会撞 max connections | 永远 `try/finally` |
| 字符串拼接列值 | SQL 注入 | 永远用 `?` 占位 + 元组传参 |
| ORM 风格幻想(`Account.objects.create(...)`) | 项目刻意不用 ORM | 用裸 `conn.execute(SQL, params)` |
| `SELECT *` 后用下标取列 | 加列后下标错位 | `row["col_name"]` 按列名 |
| 自己写时间戳字符串 | 难比较、难统计 | 用 `julianday('now')` 或 Python `time.time()` |
| 给 SSE 流端点加 `_db_lock` 保护读 | 1Hz 轮询里加锁会阻塞写线程 | SSE 只 select,**不加锁**,容忍读到刚 commit 前一瞬的状态 |
