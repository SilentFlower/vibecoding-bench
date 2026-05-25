# Auth Design (Cookie Session)

> orchestrator 的 WebUI 鉴权契约:为什么选 cookie session、中间件豁免规则、WebSocket 间接保护。

---

## Scope / Trigger

涉及鉴权的任何改动都按本文契约:
- 改 `/api/auth/*` 路由
- 改鉴权中间件豁免范围
- 加新公开端点(static)/ 新私有端点(/api/*)
- 改 cookie / token 格式

---

## Design Decision: Cookie Session 而非 HTTP Basic Auth

### Context

最初实现用了 FastAPI Basic Auth 中间件,触发浏览器原生 401 弹窗。用户体验问题:
1. 弹窗样式跟终端实验室主题完全脱节
2. 浏览器无"登出"语义(只能关全部浏览器实例)
3. 凭据每次请求都裸传(虽然 https 可缓解)

### Options Considered

| 方案 | UI 一致 | 易实现 | 安全 | SSE/WS 友好 |
|------|---------|--------|------|------------|
| HTTP Basic Auth(中间件) | ❌(原生弹窗) | ✅✅ | △(同源 https 可) | ✅(浏览器自动带) |
| Cookie session(HMAC 签名) | ✅(自定义页) | ✅ | ✅ | ✅(同源自动带) |
| Bearer token in localStorage | ✅ | △ | △(JS 可读 = XSS 暴露) | ❌(EventSource 不能设 header) |
| OAuth(GitHub / Google) | ✅ | ❌(回调链复杂) | ✅✅ | ✅ | 

### Decision

**Cookie session + HMAC-SHA256 签名 token**。理由:
1. 自定义登录页可以走终端实验室风格(`shell prompt banner` + `┌┐` 装饰 + 闪烁 caret)
2. HTTPOnly cookie 防 XSS 偷
3. EventSource / WebSocket 同源自动带 cookie,SSE 实时刷新不破
4. 单进程 stateless(token 内含 user + exp + sig),scale 友好

---

## Signatures

### 路由

```
POST /api/auth/login   body: {user: str, pwd: str}  → 200 {ok: true, user} + Set-Cookie
                                                    → 400 auth 未启用 / 401 凭据错
POST /api/auth/logout                              → 200 {ok: true} + Set-Cookie(过期)
GET  /api/auth/me                                  → 200 {authenticated: true, user, auth_required}
                                                    → 401 未登录(仅 auth_required=true 时)
```

### Token 格式

```
base64url("user|exp_ts|hmac_sha256(user|exp_ts, WEBUI_SESSION_SECRET)")
```

- TTL: 7 天(`_SESSION_TTL = 7 * 24 * 3600`)
- 算法: SHA-256
- 编码: URL-safe base64,无 padding

### Cookie 属性

```
Name:     vb_session
HttpOnly: true     (防 JS 读 → 防 XSS 偷)
SameSite: lax      (允许同站子页跳转带 cookie,防 CSRF 跨站)
Secure:   false    (HTTPS 部署应改 true;HTTP 强制 Secure 会被浏览器丢弃)
Max-Age:  7 天
```

---

## Contracts

### 环境变量

| Key | 必填? | 默认 | 含义 |
|-----|------|------|------|
| `WEBUI_USER` | 二选一(两者都填) | `""` | 登录用户名;空 = 鉴权禁用 |
| `WEBUI_PASS` | 二选一(两者都填) | `""` | 登录密码;空 = 鉴权禁用 |
| `WEBUI_SESSION_SECRET` | 否 | `secrets.token_hex(32)`(进程启动随机) | HMAC 签名密钥;留空 = 重启注销所有 session |

`_AUTH_ENABLED = bool(WEBUI_USER and WEBUI_PASS)` —— 任一为空即旁路,保留本地开发免登。

### 中间件豁免规则(关键)

```python
@app.middleware("http")
async def session_auth_middleware(request, call_next):
    if not _AUTH_ENABLED:
        return await call_next(request)              # 鉴权未启用 → 全放行
    path = request.url.path
    # 1. 静态资源(/, /style.css, /app.js, /index.html …)放行
    #    否则首次访问连登录页都看不到
    # 2. /api/auth/* 放行(login/logout/me 自身必须可达)
    if not path.startswith("/api/") or path.startswith("/api/auth/"):
        return await call_next(request)
    # 3. 其他 /api/* 必须带合法 cookie
    if not _verify_session_token(request.cookies.get(_SESSION_COOKIE, "")):
        return JSONResponse(status_code=401, content={"detail": "auth required"})
    return await call_next(request)
```

**至关重要的两条豁免**:
- **非 /api/* 路径全放行**:否则用户首次访问 `/` 拿不到 HTML,看不到登录框,死循环
- **/api/auth/\* 放行**:login 自身要可被未登录用户调用,否则鸡生蛋

### WebSocket 不经此中间件

`@app.middleware("http")` 只处理 scope=http,WebSocket 升级请求是 scope=websocket,**bypass 中间件**。但本项目唯一的 WS 路由(`/api/accounts/login/ws/{sid}`)需要 sid,而 sid 由已鉴权的 `POST /api/accounts/login/start` 派发:

```
未登录 → POST /api/accounts/login/start → 401(中间件拦)→ 拿不到 sid → WS 无法连
已登录 → POST /api/accounts/login/start → 200 + sid → 连 WS
```

**Sid 强度**:`uuid.uuid4().hex[:12]` = 48 位熵,暴力枚举不可行。

---

## Validation & Error Matrix

| 输入 | 行为 | 状态码 |
|------|------|--------|
| auth 未启用(env 任一空) | 全放行 | 透明 |
| `POST /auth/login` body 字段缺失 | FastAPI/Pydantic 自动 422 | 422 |
| `POST /auth/login` 用户名错(密码任意) | 返回 `"invalid credentials"` | 401 |
| `POST /auth/login` 密码错(用户名对) | 返回 `"invalid credentials"`(**同上同句**,防用户名枚举) | 401 |
| `POST /auth/login` 全对 | 签 token,Set-Cookie,返回 user | 200 |
| `GET /api/*` 无 cookie | `{"detail":"auth required"}` | 401 |
| `GET /api/*` cookie 过期(exp_ts 早于 now) | 同上 | 401 |
| `GET /api/*` cookie 签名错(用户改了 secret 后旧 token) | 同上 | 401 |
| `GET /api/auth/me` 未登录 | `{"detail":"not authenticated"}` | 401 |
| `GET /api/auth/me` auth 未启用 | `{"authenticated":true,"user":null,"auth_required":false}` | 200 |
| `POST /api/auth/logout` 无 cookie | Set-Cookie 过期 + `{"ok":true}`(幂等) | 200 |

---

## Good / Base / Bad Cases

**Good**:auth 启用 + 强密码 + 显式设 `WEBUI_SESSION_SECRET`(重启不踢用户) + 反代到 HTTPS + cookie Secure=true(需要改代码或部署时通过 proxy 加 Secure header)。

**Base**:auth 启用 + 弱密码 + 默认 random session secret(重启吊销所有 session,可接受)。

**Bad**:
- WEBUI_USER/PASS 留空生产部署 → 任何人可访问
- 错凭据返回不同消息(如 "user not found" / "wrong password") → 用户名枚举
- 把 / 也加进 auth → 看不到登录页死循环
- cookie 非 HTTPOnly → XSS 一旦发生立失 session

---

## Tests Required

启动后跑这 9 条断言(参考 `orchestrator/main.py` 测试 transcript):

```
T1 无 cookie /api/auth/me            → 401
T2 无 cookie /api/topics             → 401(中间件拦截)
T3 错密码 /api/auth/login            → 401 + 'invalid credentials'
T4 对密码 /api/auth/login            → 200 + Set-Cookie vb_session
T5 带 cookie /api/auth/me            → 200 + user
T6 带 cookie /api/topics             → 200
T7 /api/auth/logout                  → 200 + cookie 过期
T8 logout 后 /api/topics             → 401
T9 静态(/ /style.css /app.js)无 auth → 200
```

额外:

- T10 错用户名 + 对密码 → 同 T3 的 "invalid credentials"(枚举防御)
- T11 修改 WEBUI_SESSION_SECRET 重启 → 旧 token 全部 401
- T12 等 7 天后用旧 token → 401(TTL)

---

## Wrong vs Correct

### ❌ Wrong:中间件把 `/` 也拦了

```python
if path.startswith("/api/"):    # ✗ 反了
    return ... 401
return await call_next(request)
```
首次访问拿不到 HTML/CSS/JS,登录页都加载不出来。

### ✅ Correct:静态放行,只拦 /api/*(且豁免 /api/auth/*)

```python
if not path.startswith("/api/") or path.startswith("/api/auth/"):
    return await call_next(request)
# 鉴权检查
```

### ❌ Wrong:错凭据返回不同消息

```python
if user != WEBUI_USER:
    raise HTTPException(401, "user not found")    # ✗ 用户名枚举
if pwd != WEBUI_PASS:
    raise HTTPException(401, "wrong password")
```

### ✅ Correct:统一 "invalid credentials" + secrets.compare_digest

```python
u_ok = secrets.compare_digest(body.user, WEBUI_USER)
p_ok = secrets.compare_digest(body.pwd, WEBUI_PASS)
if not (u_ok and p_ok):
    raise HTTPException(401, "invalid credentials")
```

### ❌ Wrong:cookie 不签名

```python
response.set_cookie("vb_user", body.user, httponly=True)
# 前端 cookie 是明文 user,无签名 → 任何能写 cookie 的攻击都能伪造身份
```

### ✅ Correct:HMAC 签名,服务端 verify

```python
token = _make_session_token(body.user)  # user|exp|hmac
response.set_cookie(_SESSION_COOKIE, token, httponly=True, samesite="lax", max_age=_SESSION_TTL)
```

---

## Common Mistakes

| 反模式 | 现象 | 修复 |
|--------|------|------|
| 留空 WEBUI_USER/PASS 但以为有 auth | 公网可访问 | bootstrapAuth 时打印 `auth_required=true/false` 让自己看清 |
| 错凭据细分提示 | 用户名枚举攻击 | 统一 `invalid credentials` |
| 没用 `secrets.compare_digest` | timing attack 理论可枚举 | 永远 compare_digest |
| 中间件拦了静态 | 看不到登录页 | 豁免 `not path.startswith("/api/")` |
| WS 路由忘记设计间接保护 | 未登录可连 WS | sid 由鉴权 endpoint 派发,无路径绕过 |
| 前端 fetch 没带 `credentials: 'same-origin'` | cookie 不发,永远 401 | API helper 默认加 |
| 后端 logout 仅删 cookie 不返 success | 前端不知何时刷新 | 返 `{"ok":true}` + 前端 reload |
| 改密码后旧 session 仍有效 | 注销不彻底 | token verify 时强校 `user == WEBUI_USER`(已实现) |
