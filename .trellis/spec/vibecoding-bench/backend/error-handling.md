# Error Handling

> 本项目后端的错误处理约定。

---

## Overview

后端错误处理是**两套策略并存**,因为业务场景天然分两类:

1. **API 请求路径**:用 `fastapi.HTTPException(status, detail)` 把错误抛出去,FastAPI 自动转 `{"detail": "..."}` JSON 响应。前端拿到 `r.json().detail` 弹 `alert`
2. **后台 / 清理路径**(`Runner.cleanup`、`LoginManager.cleanup`、SSE 轮询、PTY 桥):**故意吞异常**,因为这些路径出错不能让主流程崩。每个 `try` 包一段尽量小的代码,`except Exception: pass`

**不自定义错误类型**。P1 阶段所有错误要么 `HTTPException(code, msg)`,要么 `ValueError(msg)`,要么裸 `Exception`,通过 status code + msg 区分语义就够。

---

## Error Types

| 类型 | 在哪用 | 例子 |
|------|--------|------|
| `HTTPException(400, "...")` | 用户输入错误、违反业务约束 | `HTTPException(400, "profile empty or missing: ...")` |
| `HTTPException(404, "...")` | 资源不存在 | `HTTPException(404, "task not found")` |
| `HTTPException(500, "...")` | 内部子系统失败但仍想给前端有意义提示 | `HTTPException(500, f"exec failed: {e}")` |
| `ValueError("...")` | 在非 FastAPI 路径(`LoginManager.start`)的输入校验 | `ValueError("invalid account name: must match ...")`,调用方再翻译成 `HTTPException(400, str(e))` |
| 裸 `Exception` | 不知具体类型的下游错误(docker SDK / sqlite / socket) | 由调用方 `except Exception as e` 决定吞还是转 |

**不引入** 自定义异常基类、不引入 `BenchException(Exception)` 之类的等级结构。P1 业务面太小,加抽象只是噪音。

---

## Error Handling Patterns

### Pattern 1:API 路由 —— 验证 + 转 HTTPException

```python
@app.post("/api/tasks")
def create_task(body: TaskIn):
    topic_row = conn.execute(
        "SELECT * FROM topics WHERE no=? AND deleted_at IS NULL",
        (body.topic_no,),
    ).fetchone()
    if not topic_row:
        raise HTTPException(404, f"topic {body.topic_no} not found")
    # ...继续主逻辑
```

要点:
- **早返回**:校验失败立即 `raise`,不写 `else` 嵌套
- **错误消息可被前端展示**:用户能看懂的中英文短句,**带上关键值**(哪个 id、哪个名字),不要只写 "invalid input"
- **不在路由里捕获 `Exception` 后吞掉**,让 FastAPI 默认 500 处理,这样还能在 server log 看到 traceback

### Pattern 2:内层抛 `ValueError`,路由层翻译

`LoginManager.start()` 这种业务逻辑层不该依赖 FastAPI,所以抛通用异常:

```python
# LoginManager 层
def start(self, name: str, socks5: dict) -> LoginSession:
    if not _ACC_NAME_RE.match(name):
        raise ValueError("invalid account name: must match [a-zA-Z0-9_-]+")
    # ...

# 路由层翻译
try:
    session = login_manager.start(body.name, {...})
except ValueError as e:
    raise HTTPException(400, str(e))
except Exception as e:
    raise HTTPException(500, f"failed to start login session: {e}")
```

### Pattern 3:清理路径必须吞异常

容器清理、连接关闭、文件删除这类**幂等终止操作**,**永远不应让上层流程因清理失败而崩**:

```python
def cleanup(self, sidecar_id: Optional[str], worker_id: Optional[str]) -> None:
    for cid in (worker_id, sidecar_id):
        if not cid:
            continue
        try:
            c = self.client.containers.get(cid)
            try:
                c.stop(timeout=5)
            except Exception:
                pass                  # 已经停了/网络抽风,无所谓
            c.remove(force=True)
        except Exception:
            pass                      # 容器可能已经被 remove
```

要点:
- **嵌套 try**:外层兜 "容器消失",内层兜 "停容器失败"
- **不写 log**(因为路径太热,SSE 1Hz 触发,日志会噪)
- **注释说明意图**:为什么这里 pass 是有意为之

### Pattern 4:`try/finally` 保证资源释放

```python
conn = get_db()
try:
    # do stuff
finally:
    conn.close()
```

```python
sem.acquire()
try:
    # run worker
finally:
    sem.release()
```

**不要用 contextmanager 包装**(不增加可读性,只增加抽象)。直接 `try/finally` 最清晰。

---

## API Error Responses

FastAPI 默认行为已经够用:

```json
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"detail": "profile empty or missing: /data/profiles/foo. Run scripts/init-account.sh foo first."}
```

前端约定:

```js
const API = (path, opts) => fetch('/api' + path, opts).then(async (r) => {
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const j = await r.json(); msg = j.detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
});
```

后端**只用 `detail` 字段**,不要扩展成 `{code, message, data}` 之类的自定义 envelope —— FastAPI/前端约定已经简单可用,扩展只徒增前后端契约。

**429 / 限流**:目前没做。若引入,沿用 `HTTPException(429, "rate limited: try after Xs")`。

---

## Common Mistakes

| 反模式 | 为什么不要 | 怎么改 |
|--------|------------|--------|
| 路由里 `except Exception: return {"error": "..."}` | 200 OK + error body 让前端必须双重判定 | 直接 `raise HTTPException(...)` |
| 清理路径不吞异常 | 一次清理失败让整个 `_execute` 退出,sem 释放也走不到 → 信号量泄漏 | 清理路径所有外部调用都包 `try/except Exception: pass` |
| 路由里直接抛 `ValueError` | FastAPI 转 500,前端拿不到原信息 | 翻译成 `HTTPException` |
| 错误消息仅 `"failed"` / `"error"` | 前端用户看到一脸懵 | 带上**做什么时失败的**(`"failed to start login session: <e>"`) + **关键标识**(账号名、run id) |
| 用 `assert` 当业务校验 | Python `-O` 跳过 assert,生产可能直接放行 | 校验用 `if ... raise HTTPException(...)` |
| 把 docker SDK 的 `APIError` 漏给前端原文 | 信息冗长,可能含敏感路径 | 用 `f"docker error: {e}"` 包一下,需要细节看 server log |
| 用全局 try 包整个函数体 | 错误来源被屏蔽,traceback 不准 | 只 try 真会抛的小段 |
