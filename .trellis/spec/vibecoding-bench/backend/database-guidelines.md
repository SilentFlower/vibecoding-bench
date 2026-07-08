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
