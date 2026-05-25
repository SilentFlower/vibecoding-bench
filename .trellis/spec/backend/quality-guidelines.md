# Quality Guidelines

> 本项目后端的代码质量与评审标准。

---

## Overview

后端代码质量目标按优先级:

1. **跑得起来**(P1 是 MVP,功能正确 > 一切)
2. **可读**(同事/未来 AI 看得懂,中文注释解释 "为什么")
3. **可演进**(P2/P3 加功能时不必推倒重来)
4. **抗误用**(API 别人乱传也不能让 orchestrator 挂)

**故意没有**:lint 工具配置、CI、单元测试、mypy。P1 通过**真跑**(`docker compose up` + 浏览器点)做验证,质量靠人工 review + 小规模团队约定保证。

---

## Forbidden Patterns

| 模式 | 为什么禁止 |
|------|-----------|
| 引入 ORM(SQLAlchemy / Tortoise / SQLModel) | 项目刻意保持 SQLite + 裸 `sqlite3`,加 ORM 反而把"哪条 SQL 真正执行"藏起来,出问题难调 |
| 引入新的全局任务队列(Celery / RQ / Arq) | 当前 `threading.Thread + Semaphore` 已经 cover 单节点 P1 全部场景,引入更复杂的队列 = 额外部署 |
| 在路由里直接 `time.sleep(N)` 或 `await asyncio.sleep(N)` 卡几秒以上 | 阻塞 uvicorn worker;后台时序等待应放到 Scheduler 线程内 |
| 用 `print()` 当 log | 见 logging-guidelines.md,P1 不写 log,真要写就引 logging |
| `eval()` / `exec()` / `subprocess.run(..., shell=True, user_input)` | 经典 RCE。需要执行外部命令一律用 docker SDK 或 `subprocess.run([...], shell=False)` |
| SQL 字符串拼接含**用户**值 | 见 database-guidelines.md,永远参数化 |
| `assert` 当业务校验 | `python -O` 会跳过,生产不可靠 |
| 路由函数 `async def` 但内部全是同步 IO(`conn.execute` / `time.sleep`) | 同步 IO 在 async 路由里会阻塞事件循环,本项目大多数路由是 `def`(同步),只有真要异步流的(SSE / WebSocket)才 `async def` |
| 在 `_db_lock` 持有期间做长 IO(docker API、http 请求) | 锁延长会让所有写 DB 的线程卡住;只在锁内做 SQL,IO 挪出去 |
| `from xxx import *` | import 来源不可追;PEP8 也禁,且 IDE 跳转失败 |
| 全限定名(`fastapi.FastAPI()` 而不是 `from fastapi import FastAPI`) | 见全局指令 §2,本项目用显式 import |

---

## Required Patterns

| 模式 | 为什么必须 |
|------|-----------|
| 任何 `INSERT/UPDATE/DELETE` 必须包在 `with _db_lock: ... conn = get_db(); try: with conn: ... finally: conn.close()` | 防 `database is locked` + 保证事务提交 + 防连接泄漏 |
| 所有 SQL 用 `?` 占位 + 元组传值 | 防注入,无例外 |
| 所有外部 IO(docker / socket / file 写)在清理/cleanup 路径都包 `try/except Exception: pass` | 见 error-handling.md Pattern 3 |
| 容器命名必须以 `bench-` 前缀开头 | 启动时 `LoginManager.cleanup_stale()` 按前缀清残留;非 `bench-` 前缀的容器永远不动 |
| 用户名 / 账号名匹配 `_ACC_NAME_RE = ^[a-zA-Z0-9_-]+$` | 这个名字会被拼进容器名、卷路径、文件夹名,必须收紧字符集防注入 |
| Pydantic `BaseModel` 描述请求体 | FastAPI 自动校验 + 文档;DTO 进路由前必过 |
| 容器内路径 `BENCH_DATA` ≠ 宿主路径 `HOST_BENCH_DATA`,挂卷给子容器**必须用宿主路径** | docker daemon 站在宿主视角解析挂卷点,容器内路径它看不见 |
| 给子容器调 `containers.run(network_mode="container:X", ...)` 时,**不能**同时传 `hostname=`(Docker 会报 `conflicting options: hostname and the network mode`);hostname 由 netns 持有者 X 决定,共享 netns 的容器自动继承 | 设 hostname 时只在 sidecar(netns 持有者)上设;worker 留空即可继承。MAC 同理:`mac_address=` 也只在 netns 持有者上有效 |
| HTTP 鉴权用 cookie session(`@app.middleware("http")` + HMAC 签名 token),**禁止**新加 HTTP Basic Auth | Basic Auth 浏览器原生弹窗破坏 UI 风格,且 EventSource/WS 同源 cookie 比 Basic header 更稳。详见 [deploy/auth-design.md](../deploy/auth-design.md) |
| 鉴权中间件豁免规则:**非 `/api/*` 全放行 + `/api/auth/*` 放行**;其他 `/api/*` 校验 cookie | 静态资源拦了首次访问看不到登录页;`/api/auth/login` 自身被拦就鸡生蛋无法登录。WebSocket 经 starlette scope=websocket 不进 HTTP 中间件,需路由层用 sid(uuid4 hex,~48 位熵)间接保护 |
| 凭据校验用 `secrets.compare_digest(a, b)`,**禁止**用 `==` | 防 timing attack;另外凭据错统一返回 `"invalid credentials"`,不区分"用户名错"/"密码错",防用户名枚举 |
| FastAPI 设/清 cookie 用注入的 `response: Response` 参数 + `response.set_cookie(...)`,**不要**自己拼 Set-Cookie header | set_cookie 自动处理 Max-Age / Expires / HttpOnly / SameSite 等;HTTPOnly + SameSite=lax 是必须默认 |
| 长跑后台任务用 `threading.Thread(..., daemon=True)`(不是 asyncio task) | 主进程退出时不阻塞;且现有逻辑用 docker SDK 同步 API,asyncio 包装反而麻烦 |
| 每账号信号量 `threading.Semaphore(PER_ACCOUNT_CONCURRENCY)` 持有期间必须 `try/finally release` | sem 泄漏 = 账号被永久锁死 |
| 中文注释解释 "为什么"(为什么这里 sleep,为什么这里吞异常) | 见全局指令 §3,中文注释 + WHY 非 WHAT |
| 路由函数顶部一行 docstring 说明用途(中文) | 见 `login_start` / `login_ws` / `login_commit` 范式 |

---

## Testing Requirements

**P1:无自动化测试**。**测试 = 真跑 + 浏览器点**。验收必经路径:

| 路径 | 怎么验 |
|------|--------|
| 账号 CRUD | WebUI 账号页 → + 添加 / 删除 |
| OAuth 内嵌登录 | WebUI 账号页 → 走完两步流 → 浏览器看 step 2 PTY 终端能收到 URL → 浏览器完成 OAuth → 粘回授权码 → commit & save 落库 |
| 题库解析 | WebUI 题库页 → 看到 100 道题、能过滤、能点开创建任务 |
| 任务运行(单 run) | 题库 → 选账号 + repeat_n=1 → 任务页 ▶ run → 运行页看到 queued → running → success,详情面板有 transcript + token 统计 |
| 任务运行(并发) | 单账号 repeat_n=4 → 一次提交 → 运行页同账号最多 2 个 running,其余 queued |
| 失败兜底 | 故意停 docker daemon → 单次 ▶ run → 应当 failed 而不是 orchestrator 崩 |

**P2 引入自动化测试时**:优先 `pytest` + `httpx.AsyncClient` 对 FastAPI 端点做 in-process 测试(不起 docker);docker 调度路径太重,只手测 / 单独脚本化。

---

## Code Review Checklist

提交前自查 + Reviewer 必看:

- [ ] **schema 改动**:`_SCHEMA` 里的 CREATE 是否幂等(`IF NOT EXISTS`)?新增列是否补了兼容的默认值?需不需要 `data/db.sqlite` 删了重建?
- [ ] **新路由**:挂在 `/api/<resource>` 下?用 `BaseModel` 描述请求体?路由按 "create / list / get / update / delete / 子操作" 排序?
- [ ] **新后台任务**:是否 `daemon=True`?是否有兜底 try/finally?是否需要 `_db_lock` 写状态?
- [ ] **docker 容器命名**:`bench-<role>-<id>` 前缀?cleanup 路径在 `__exit__` / `finally` 有调用?
- [ ] **挂卷路径**:用了 `HOST_BENCH_DATA` 而不是 `BENCH_DATA`?
- [ ] **错误消息**:面向用户的 `HTTPException(detail)` 用人话写明白了**做什么时失败 + 关键 ID/名字**?
- [ ] **日志/print**:没有 `print(...)` 留到提交?没有泄漏密码 / token / prompt?
- [ ] **并发**:写 DB 的代码在 `_db_lock` 内?长 IO 在锁外?信号量 `acquire/release` 配对?
- [ ] **资源释放**:`conn.close()` / `sock.close()` / `container.remove(force=True)` 都在 finally?
- [ ] **类型注解**:函数签名带 `-> ReturnType`?变量在跨节传递时带类型提示?
- [ ] **中文注释**:复杂逻辑、为什么 sleep、为什么吞异常,有没有写明 WHY?
- [ ] **API 契约**:前端 `app.js` 的对应调用还跑得通吗?字段名变了要前端同步改吗?
