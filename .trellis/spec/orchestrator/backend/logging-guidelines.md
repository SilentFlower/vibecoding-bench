# Logging Guidelines

> 本项目后端的日志策略。

---

## Overview

**P1 阶段刻意保持极简**:orchestrator 几乎不主动写日志,**真相在 SQLite + 落盘文件里**,不在日志里。

- **没有引入 logging 库**(无 `import logging`、无 `loguru`、无 `structlog`)
- **没有 `print` 调试痕迹**(发现 `print(...)` 一律视为 P1 调试残留,在提交前清理)
- **唯一允许的"日志"** 来自三处:
  1. **uvicorn 默认 access log**:每个 HTTP 请求一行,自带状态码 / 耗时,够用
  2. **FastAPI 未捕获异常的 traceback**:进程标准错误,运维捞 `docker logs orchestrator` 看
  3. **mitmproxy 写的 `stats.jsonl`**:由 sidecar 容器维护,记录每条 API 调用的 token / status,这是**业务可观测的真正来源**,不是 orchestrator 写

业务事件(run 状态变化、login 进度)通过**写 SQLite 的 status 字段** + **SSE 推前端**让用户看见,不靠 log。

---

## Log Levels

如果未来引入 `logging`(P2+),约定:

| Level | 何时用 |
|-------|--------|
| `DEBUG` | 默认关。开发时定位时序问题用,合并前关掉 |
| `INFO` | 进程级里程碑:启动 / lifespan 完成 / 调度器接到第一个 run / 一次 OAuth login 成功落库。**不要**记每个 HTTP 请求(uvicorn 已记) |
| `WARNING` | 可恢复异常:cleanup 路径里的非致命失败、SSE 流断开重连、第一次 MITM CA 生成等待超时 |
| `ERROR` | 不可恢复 + 已经返回失败给用户:docker daemon 失联、SQLite IO 错误、PTY 桥两端都崩 |
| `CRITICAL` | 进程级失败,即将退出(目前没有) |

**没有 `TRACE` / `VERBOSE`**。

---

## Structured Logging

P2 引入 `logging` 时,**直接用 `logging.Formatter` 加固定字段**,不引入 structlog:

```
%(asctime)s %(levelname)-7s %(name)s run=%(run_id)s acc=%(acc)s -- %(message)s
```

公共字段约定:
- `run_id`(12 位 hex) —— run 维度操作必带
- `acc`(账号名) —— 账号维度操作必带
- `sid`(login session id) —— OAuth 引导维度必带
- `container`(docker 容器名前缀)—— 涉及容器生命周期时带

用 `logging.LoggerAdapter` 或 `extra={...}` 注入,避免每条 log 都 string-format。

**禁止**:
- JSON-only 日志(本地 `docker logs` 看会发疯,P1 流量小不值得)
- 多行 traceback 拼成单行(看不清,直接让 `logger.exception()` 多行输出)

---

## What to Log

如果决定加 log,**只加这几类**:

1. **进程生命周期**:`lifespan` 启动结束、`LoginManager.cleanup_stale()` 清掉的残留容器数量
2. **业务边界结果**(不是每一步,只是边界):一次 run 终态(`status=success/failed/timeout` + exit_code)、一次 OAuth login commit 落库
3. **预期外异常**:`Scheduler._execute` 里 `except Exception` 兜底分支抛出的 `e`,带 `run_id`
4. **docker 操作失败**:容器起不来 / 拉不到镜像

**不要 log**:
- 每个 HTTP 请求(uvicorn 已经做了)
- 每个 SQL 语句(SQLite 没那么慢,看 traceback 就够)
- SSE 每一帧推送
- 1Hz 轮询的"无变化"心跳

---

## What NOT to Log

**绝对不能进日志**(包括 traceback 里):

| 字段 | 在哪 | 替代办法 |
|------|------|----------|
| `upstream_socks5_pass` | `AccountIn.upstream_socks5_pass`、`LoginStartIn.upstream_socks5_pass` | 全字段日志时手动 redact 成 `***` |
| OAuth token / refresh token | profile 目录里 `~/.claude/` 的 JSON | 永远不读取它来打 log,只让 worker 容器自己用 |
| MITM 解出的 Anthropic API 原文 | sidecar 写的 `.flow` 文件 | 只保留在 `data/flows/`,**不要 cat 进 stdout** |
| transcript 全文 | `.bench-transcript.log` | 只在 WebUI `/api/runs/{rid}/transcript` 端点对外开放,**不进 server log** |
| 完整请求 body(可能含 prompt 中的私密信息) | `TaskIn.prompt` | 如要 log 任务创建,只记 `topic_no + account_id`,不记 prompt |
| `.env` 内容、环境变量 dump | 配置加载阶段 | 启动时若想确认配置,只 log **键名 + 是否非空**,不 log 值 |

**前端展示的容器名 / 代理 scheme + host:port** 不算敏感,可以 log。

---

## Common Mistakes

| 反模式 | 为什么不要 | 怎么改 |
|--------|------------|--------|
| `print("debug: ...")` 留到提交 | 没有过滤、没有时间戳、混在 uvicorn access log 里看不到 | 调试完删掉;真要留就接 logger |
| `logger.info(f"creating account {body}")` | `body.upstream_socks5_pass` 被一起记入日志 | 只 log `body.name`,或对 BaseModel 显式 `model_dump(exclude={"upstream_socks5_pass"})` |
| `try: ... except: logger.error(traceback.format_exc())` | traceback 进 message,格式器再叠一次,行宽爆炸 | 用 `logger.exception("...")`,formatter 自动接 traceback |
| 在 1Hz SSE 循环里 `logger.debug(...)` | 1Hz × 长跑 = 几十万行噪音 | 只在状态**变化**时 log,不变化沉默 |
| log 完整 SQL 包含值 | SQL 注入审计混乱、且可能含敏感数据 | 只 log SQL 模板 + 关键参数键 |
| 给 mitmproxy 的 stats.jsonl 也接一份后端 logger | 重复来源,且字段不同步 | stats.jsonl 是数据,不是日志,只在 `/api/runs/{rid}/stats` 端点聚合读 |
