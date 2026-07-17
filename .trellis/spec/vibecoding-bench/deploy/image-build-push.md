# Image Build & DockerHub Push

> 三镜像构建 + 双 tag 发布的可执行流程。

---

## Scope / Trigger

任何动到下列文件 → 必须重建 + 重推对应镜像:

| 改了 | 重建 |
|------|------|
| `orchestrator/main.py` 或 `orchestrator/requirements.txt` 或 `orchestrator/Dockerfile` | orchestrator |
| `images/worker/entrypoint.sh` 或 `images/worker/Dockerfile` | worker |
| `images/sidecar/start.sh` / `recorder.py` / `Dockerfile` | sidecar |
| `webui/*` 或 `topics.md` | **不需要重建**(都是 bind mount,远程 git pull 即可) |

---

## 命名 & Tag 契约(锁定)

镜像 namespace:`huajiwuyan/vibebench-{orchestrator,worker,sidecar}`

每次发版 **同时打两个 tag**:

| Tag | 语义 | 谁用 |
|-----|------|------|
| `:latest` | mutable,跟随 main 最新 | 跟随式部署(开发 / 单实例) |
| `:<git-sha-short>`(如 `158b462`) | immutable,锁死一个 commit | 生产 / 需要回滚能力 |

**关键约束**:三镜像即便只有一个改了,**全部打同一个 sha tag** —— 这样部署侧拉 `:158b462` 三件套永远配套,不会出现"orchestrator 是新的,worker 是旧的"的 sha tag 缺失情况。

---

## 完整命令序列

### Step 1: 构建本地镜像

```bash
# orchestrator(默认 service,无 profile)
docker compose build orchestrator

# worker 或 sidecar(在 build profile 下)
docker compose --profile build build worker-image     # 改了 worker 才跑
docker compose --profile build build sidecar-image    # 改了 sidecar 才跑
```

### Step 2: 打 tag

```bash
SHA=$(git rev-parse --short HEAD)
for img in orchestrator worker sidecar; do
  docker tag vibebench-$img:latest huajiwuyan/vibebench-$img:latest
  docker tag vibebench-$img:latest huajiwuyan/vibebench-$img:$SHA
done
```

> 即使 worker/sidecar 没改,也打新 sha tag,保证三件套 sha 对齐。Docker push 会复用已上传层,新 tag 推送只是 manifest 更新,秒级。

### Step 3: Push DockerHub

```bash
for img in orchestrator worker sidecar; do
  docker push huajiwuyan/vibebench-$img:latest
  docker push huajiwuyan/vibebench-$img:$SHA
done
```

worker 镜像 ~1.37 GB(node:22 基础大),首次推全量约 5–15 分钟视带宽。后续推增量,只传改了的层(几十 MB)。

---

## 账号上游代理协议契约

### 1. Scope / Trigger

修改账号代理字段、`orchestrator/main.py` 的 sidecar environment、`images/sidecar/start.sh` 的 proxychains 配置、或 WebUI 账号代理表单时必须遵守本契约。

### 2. Signatures

账号表:

| Column | Type | Default | 含义 |
|--------|------|---------|------|
| `upstream_proxy_scheme` | `TEXT` | `'socks5'` | 上游代理协议；允许 `http`、`socks5`、`socks5h` |
| `upstream_socks5_host` | `TEXT` | `NULL` | 上游代理主机；字段名保留历史兼容 |
| `upstream_socks5_port` | `INTEGER` | `NULL` | 上游代理端口；字段名保留历史兼容 |
| `upstream_socks5_user` | `TEXT` | `NULL` | 上游代理用户名 |
| `upstream_socks5_pass` | `TEXT` | `NULL` | 上游代理密码；日志必须脱敏 |

API 请求体:

```json
{
  "name": "main",
  "upstream_proxy_scheme": "http",
  "upstream_socks5_host": "proxy.example.com",
  "upstream_socks5_port": 8080,
  "upstream_socks5_user": "user",
  "upstream_socks5_pass": "pass"
}
```

sidecar environment:

| Env | 必填 | 默认 | 含义 |
|-----|------|------|------|
| `UPSTREAM_PROXY_SCHEME` | 否 | `socks5` | `http` / `socks5` / `socks5h`;`https` 不支持 |
| `UPSTREAM_SOCKS5_HOST` | 是 | - | 上游代理主机，历史变量名保留 |
| `UPSTREAM_SOCKS5_PORT` | 是 | - | 上游代理端口，历史变量名保留 |
| `UPSTREAM_SOCKS5_USER` | 否 | 空 | 上游代理用户名 |
| `UPSTREAM_SOCKS5_PASS` | 否 | 空 | 上游代理密码 |

### 3. Contracts

- 后端只接受 `http`、`socks5`、`socks5h`；空值归一化为 `socks5` 兼容旧账号。
- `init_db()` 必须对 `accounts.upstream_proxy_scheme` 做幂等 `_ensure_column(..., "TEXT DEFAULT 'socks5'")`。
- WebUI paste-helper 只自动解析 `http://`、`socks5://`、`socks5h://`；`http` 省略端口时填 `8080`，SOCKS 省略端口时填 `1080`。
- sidecar 的 proxychains 类型映射：`http -> http`，`socks5/socks5h -> socks5`。`socks5h` 的目标域名代理解析由当前 proxychains `proxy_dns` 链路承担。
- `https://proxy:443` 不是支持的上游代理入口；用户必须改填 `http://` 或 SOCKS。

### 4. Validation & Error Matrix

| 条件 | 行为 |
|------|------|
| API 未传 `upstream_proxy_scheme` | 按 `socks5` 保存 / 运行 |
| API 传 `http` / `socks5` / `socks5h` | 保存该协议并传给 sidecar |
| API 传 `https` 或其它值 | 400,提示只允许 `http, socks5, socks5h` |
| sidecar 收到 `UPSTREAM_PROXY_SCHEME=https` | FATAL 退出,提示不支持 HTTPS upstream proxy |
| WebUI 粘贴 `https://proxy.example.com:443` | 解析失败且不覆盖已手填字段 |

### 5. Good/Base/Bad Cases

**Good**:用户粘贴 `http://user:pass@proxy.example.com:8080`,表单自动填协议、host、port、user、pass;登录、quota、run、continue、OAuth refresh 都通过 `UPSTREAM_PROXY_SCHEME=http` 走同一条 sidecar 链路。

**Base**:老账号没有 `upstream_proxy_scheme`,升级后 DB 默认和后端归一化都按 `socks5` 处理。

**Bad**:只改 WebUI 支持 `http://`,但 orchestrator 仍不保存协议或 sidecar 仍固定写 `socks5`,导致 HTTP 代理被当成 SOCKS5 用。

### 6. Tests Required

- `python3 -m py_compile orchestrator/main.py`
- `bash -n images/sidecar/start.sh`
- `node --check webui/app.js`
- SQLite 冒烟:旧 `accounts` 表补列后,已有账号读取到 `upstream_proxy_scheme='socks5'`。
- URL 解析冒烟:`http://user:pass@proxy.example.com:8080`、`socks5h://proxy.example.com`、`https://proxy.example.com:443` 三个样例分别覆盖成功、默认端口、拒绝。

### 7. Wrong vs Correct

#### Wrong

```bash
cat > /etc/proxychains4.conf <<EOF
[ProxyList]
socks5 ${UPSTREAM_HOST_IP} ${UPSTREAM_SOCKS5_PORT}
EOF
```

#### Correct

```bash
case "$UPSTREAM_PROXY_SCHEME" in
  http) PROXYCHAINS_TYPE="http" ;;
  socks5|socks5h) PROXYCHAINS_TYPE="socks5" ;;
  *) exit 1 ;;
esac
cat > /etc/proxychains4.conf <<EOF
[ProxyList]
${PROXYCHAINS_TYPE} ${UPSTREAM_HOST_IP} ${UPSTREAM_SOCKS5_PORT}
EOF
```

---

## Worker 完成判定契约

### 1. Scope / Trigger

修改 `images/worker/entrypoint.sh` 的 Claude task 模式时必须遵守本契约。worker 是 run 终态的主要来源:退出码 `0` 会被 orchestrator 映射成 `success`,退出码 `124` 映射成 `timeout`,退出码 `42` 映射成 `auth_failed`,其它非 0 映射成 `failed`。worker 可在 `/workspace/.bench-status.json` 写入更细的状态提示;orchestrator 读取该文件后只允许把非成功 / 非停止状态细分成 `auth_failed`。

### 2. Signatures

task 模式环境变量:

| Env | 必填 | 含义 |
|-----|------|------|
| `TASK_PROMPT` | 是 | 原始题目 prompt |
| `RUN_ID` | 是 | 当前 run id,用于 tmux session 与日志归档 |
| `TIMEOUT_SEC` | 否 | worker 硬超时时间,默认 1800 |
| `TIMEOUT_WRAPUP_SEC` | 否 | 距离硬超时多少秒注入一次收尾提示,默认 600;`0` 关闭 |
| `OAUTH_CREDENTIAL_SYNC_INTERVAL_SEC` | 否 | 运行中按新鲜度同步账号 profile / 本地 `.credentials.json` 的间隔,默认 15;`0` 关闭 |
| `OAUTH_401_PROFILE_WAIT_SEC` | 否 | 401 强制 refresh 失败后等待后台刷新器更新 profile credentials 的最长秒数,默认 90;`0` 不等待 |
| `CLAUDE_API_STALL_WATCHDOG_SEC` | 否 | Claude Code API 连接错误或 TUI `Request timed out` 后持续无有效进展多久自动中断续跑,默认 400;`0` 关闭 |
| `CLAUDE_API_STALL_MAX_RECOVERIES` | 否 | 每个 run 最多自动中断续跑次数,默认 1;`0` 不恢复 |
| `CLAUDE_BUSY_INTERRUPT_GRACE_SEC` | 否 | 发送中断后等待 TUI 回到输入状态的秒数,默认 8 |
| `CLAUDE_API_STALL_RECOVERY_PROMPT` | 否 | API 卡死自动续跑提示;留空使用 worker 内置中文提示 |
| `COMPLETION_IDLE_SEC` | 否 | JSONL 稳定窗口,默认 10 秒 |
| `CLAUDE_CODE_VERSION` | 否 | 本次 worker 应使用的 Claude Code CLI 版本,默认 2.1.185;启动时若镜像内版本不一致,worker 会安装指定版本 |

### 3. Contracts

worker 注入 prompt 时必须保持 `TASK_PROMPT` 原样,不要把 bench 自己的完成协议、sentinel 或额外总结要求拼进题目 prompt。

Stop hook 只允许记录“Claude 停过一轮”的观测信号,不能直接 `exit 0` 或直接 touch 成功文件。成功必须解析 `.claude/projects/**/*.jsonl`,并满足:

1. 最新对话消息是 assistant。
2. assistant 内容不包含 `tool_use`。
3. `stop_reason` 不是 `tool_use`。
4. assistant 文本至少有一条非空文本行。
5. 最新 session JSONL 文件的 mtime 已稳定至少 `COMPLETION_IDLE_SEC` 秒。

成功状态只能保存在当前 worker 进程内的变量里,不能通过 `/tmp/claude-done` 这类文件判定。原因是旧 profile/settings 或 hook 残留可能在 Claude Stop hook 中写同名文件,把停在 `user tool_result` 的中间态误判成 success。

账号 profile 的 `settings.json` 只允许保存长期用户偏好和默认权限配置,禁止持久化 `hooks` / `statusLine`:

- `hooks` 只允许写到单次 run 的 `/workspace/.claude/settings.local.json`。
- `statusLine` 只允许用于临时调试,不能写回 `data/profiles/<account>/settings.json`。
- orchestrator 和 worker 合并 settings 时都必须删除 profile 中已有的 `hooks` / `statusLine`。

Claude 返回认证错误文本时不能作为最终 assistant 回复标成功。至少识别:

- `Please run /login`
- `API Error: 401`
- `Invalid authentication credentials`
- `OAuth token has expired`

task worker **禁止**在启动 run 前强制刷新 OAuth access token。启动前只校验 `.credentials.json` 的结构和 `accessToken` 是否存在,即使 access token 已过期或即将过期也不在 worker 启动阶段拒绝运行。常规临期刷新由 orchestrator 后台 `OAuthRefreshScheduler` 周期执行,并把新 `.credentials.json` 原子写回账号 profile。

task 运行期间必须双向但按新鲜度同步 credentials:
- profile → 本地:只在 profile 文件更新、`expiresAt` 明显更新,或 profile 能恢复本地缺失的 `refreshToken` 时同步,不能用旧 profile 覆盖 Claude Code 在当前 run 内刚刷新出的 token。
- 本地 → profile:只在本地凭证明显更新时原子回写,尤其要保存 Claude Code 2.x 刚轮换出的 `refreshToken`。不能无条件把 run home 的 `.credentials.json` 覆盖 profile。
- 同一账号多个 worker 并行时,强制 refresh / profile 回写必须用 profile 目录下文件锁串行化;多个账号并行互不影响。
同步前必须能解析 JSON 且存在 `claudeAiOauth`;写文件必须先写临时文件再 `rename` 原子替换。退出 / 停止路径仍只允许白名单回写 `settings.json` / `.claude.json`,credentials 只能走新鲜度判断。

运行中检测到 401 / OAuth 认证错误时,worker 先同步 profile credentials,再在 worker→sidecar→账号上游代理链路内用当前 `refreshToken` 强制 refresh 一次。refresh 成功后原子回写 profile,并向 Claude TUI 注入一次重试提示。refresh 返回 `invalid_grant` / 429 / 其它非 2xx 时,错误消息要带 HTTP 状态与 retry-after 摘要;如果后台刷新器在 `OAUTH_401_PROFILE_WAIT_SEC` 内写入更新 credentials,可同步后重试一次,否则 worker 写 `/workspace/.bench-status.json` 为 `{"status":"auth_failed","error":"..."}` 并以退出码 `42` 结束。

查询 OAuth usage API 前必须确认 sidecar 的通用 DNS resolver 已可用。sidecar/unbound 配的是通配 `forward-zone "."`,所以 readiness probe 应验证一个稳定探针域名能解析,不能把每个业务目标域名硬编码成白名单。orchestrator 可以用 `docker exec` 进 sidecar 等 `/tmp/sidecar-ready` 或通用探针解析成功,但不能用 orchestrator/宿主机网络代替 sidecar 解析。usage probe 必须在 worker 容器内按同一套 `expiresAt` 规则刷新 access token,再读 `.credentials.json` 调 usage API。实际 API URL 请求还必须有限重试,覆盖 resolver 刚启动后的瞬时 `Temporary failure in name resolution`。

不能用宿主机网络或宿主 DNS 作为 OAuth refresh / usage 的 fallback。账号相关请求和域名解析都必须留在 worker→sidecar→账号上游代理链路里,否则会从宿主原始 IP 泄漏域名查询或 HTTPS 出口。

上游代理服务器地址可以填域名。这个域名是建立代理链路之前的 bootstrap 解析,只能用 sidecar 启动时的默认 DNS 解析成 IP 后再连接代理;它和 Claude/API/WebFetch 访问的业务目标域名不是一类问题。不要为了阻断业务 DNS 泄漏而禁止代理域名。

worker 启动时必须让实际 `claude --version`、worker 运行时 `CLAUDE_CODE_VERSION`、OAuth usage 请求的 `User-Agent` 保持一致。镜像内可预装默认版本,但 WebUI / `.env` 可以覆盖版本;entrypoint 必须校验版本号格式,不一致时安装 `@anthropic-ai/claude-code@<CLAUDE_CODE_VERSION>`,安装失败要让 worker 明确失败,不能静默回退到镜像默认版本。OAuth refresh 请求不要带 `User-Agent`:实测带 `claude-code/<version>` 会触发 token endpoint 429;refresh 仍必须在 worker→sidecar→账号上游代理链路内完成。

worker 不能因为没看到最终 assistant 文本而反复向 Claude 追加 prompt；只能等待 JSONL 变化,直到完成、Claude 退出或 `TIMEOUT_SEC` 到期。

若 Claude Code session JSONL 明确出现 `system api_error` 连接错误(如 `ECONNRESET` / `Unable to connect to API`),或 TUI transcript 明确显示 `API error · Retrying ...` / `Request timed out · Retrying ...`,且之后超过 `CLAUDE_API_STALL_WATCHDOG_SEC` 没有对话或 workspace 产物进展,worker 可在 `CLAUDE_API_STALL_MAX_RECOVERIES` 上限内对 TUI 发送一次中断并注入继续提示。这是对 API 卡死的有限恢复,不是通用催促机制;没有明确 API 连接错误 / timeout 文案时禁止触发。

若 Claude Code session JSONL 最终写入 synthetic API error 消息(例如 `isApiErrorMessage=true` 且文本为 `Request timed out`),worker 必须写 `/workspace/.bench-status.json` 并以非 0 退出,让 orchestrator 标记为 `failed`。这种消息不是最终交付总结,禁止按普通 assistant 文本判定为 `success`。

临近 timeout 注入收尾提示时,如果 TUI 仍处于 busy 状态且恢复次数未用完,worker 可先中断 busy 回合再注入收尾提示,避免提示只排队在输入框。若恢复后仍超时,worker 应在 `/workspace/.bench-status.json` 写入可见错误,orchestrator 继续把 run 标为 `timeout`。

若 API 卡死恢复后 run 最终成功或被用户主动停止,orchestrator 不应把中途恢复提示写入 `runs.error`;该字段只保留非成功、非停止终态的可见错误。

### 4. Validation & Error Matrix

| 条件 | worker 退出 | orchestrator 终态 |
|------|-------------|-------------------|
| 最新对话消息是稳定的纯文本 assistant 回复 | `0` | `success` |
| 最新对话消息是 user `tool_result` | 继续等到后续完成或超时 | 非 success |
| 首次检测到 401 且后台刷新器及时写入新 credentials | 注入一次重试提示并继续等待 | 取决于后续完成结果 |
| 401 后等待 profile 刷新超时 | `42` | `auth_failed` |
| 重试后再次检测到 `/login` / 401 认证错误 | `42` | `auth_failed` |
| API 连接错误后长时间无进展且恢复次数未用完 | 中断 TUI 并注入继续提示 | 取决于后续完成结果 |
| Claude 以 0 退出但没有最终 assistant 文本 | `1` | `failed` |
| 达到 `TIMEOUT_SEC` 仍无最终 assistant 文本 | `124` | `timeout` |
| 收到 `TERM/INT` | 先白名单回写 profile,再退出 | `stopped` 或 `failed` 由 orchestrator 状态决定 |

### 5. Good/Base/Bad Cases

**Good**:Claude 写完文件、跑完检查,最终回复一段纯文本总结。JSONL 稳定窗口后,worker 退出 `0`。

**Base**:Claude 停在工具结果后,TUI 回到输入框,但 JSONL 最新消息是 user `tool_result`。worker 继续等待,不会把该 run 标成 `success`。

**Bad**:Stop hook 执行 `touch /tmp/claude-done`,worker 只看这个文件就退出 `0`。这会把“工具调用中间态”误判为成功。

**Bad**:quota/statusLine 探测把 `statusLine` 写入账号 profile 的 `settings.json` 并回写。后续 task 会加载这段运行态配置,污染被测 run。

**Bad**:access token 明明还有很久才过期,每次 task 启动都调用 OAuth refresh endpoint。这样会制造额外请求和不必要的凭据轮换。

**Bad**:task worker 启动时发现 access token 已过期或 10 分钟内过期,就直接刷新或直接失败。正确做法是让 run 启动,运行中按 profile 新鲜度同步;如果 Claude 实际遇到 401,再锁住 profile 强制刷新一次并只重试一次。

**Bad**:task 结束时无条件把 run home 里的 `.credentials.json` 覆盖真实账号 profile。后台刷新器或另一个并行 run 可能已经写入更新 token,旧 run 结束再覆盖会把新 token / 新 RT 写坏。正确做法是按 `expiresAt` / refreshToken 轮换 / 文件新鲜度判断后原子回写。

**Bad**:worker 启动前只等 `api.anthropic.com` 可解析,然后立刻刷新 OAuth token。`platform.claude.com` 尚未解析成功时会出现 `<urlopen error [Errno -3] Temporary failure in name resolution>`。

**Bad**:用 Python `urllib` 直接调用 `https://platform.claude.com/v1/oauth/token` 刷新 access token。Cloudflare 可能按浏览器签名返回 1010 `browser_signature_banned`;正确做法是在 worker 容器里按 `expiresAt` 判断后用 Node runtime 刷新,并把刷新后的 `.credentials.json` 回写 profile。

**Bad**:对 `platform.claude.com` 做 MITM 解密后再刷新 OAuth token。这样 Cloudflare 看到的是 mitmproxy/OpenSSL 的上游 TLS 指纹,不是 Claude CLI/Node 指纹,更容易触发 1010。该域名应在 sidecar 中 TLS passthrough,仍走同一个账号上游代理出口但不解密。

**Bad**:每遇到一个新网页域名就加一个 DNS 等待白名单。正确做法是验证 sidecar 的通用 resolver 可用,后续任意域名都走同一条 worker→unbound→tun→账号上游代理链路。

**Bad**:在 orchestrator 容器或宿主机上提前解析业务域名,再把解析结果当成 worker 可用。这个检查既不能证明 sidecar netns 里的 unbound 已经可用,也可能泄漏宿主 DNS 查询。

**Bad**:为了解决完成判定,把 `BENCH_DONE:<RUN_ID>` 之类的 bench sentinel 拼进题目 prompt。这样会污染被测任务的自然输出。

**Bad**:refresh endpoint 返回 `invalid_grant` 或持续 `429` 时继续重试,或直接删除真实账号 profile 里的 `.credentials.json` 再让用户重登。`invalid_grant` 表示 refresh token 已被服务端废弃,没有新 access token 可回写,必须走账号"重授权"。重授权应使用一次性 login profile 副本并移除副本里的 `.credentials.json`,迫使 `claude auth login` 进入 OAuth 流程;用户取消时真实 profile 不变,commit 成功后只把 `.credentials.json` / `settings.json` / `.claude.json` 白名单覆盖回真实 profile。

### 6. Tests Required

- `bash -n images/worker/entrypoint.sh`
- 用本地 JSONL 样例断言:
  - 最新消息是 user `tool_result` 时判未完成。
  - 最新消息是 assistant `tool_use` 时判未完成。
  - 最新消息是稳定的 assistant 文本时判完成。
  - 最新 assistant 文本包含 `Please run /login · API Error: 401 Invalid authentication credentials` 时判失败。
  - 最新 session JSONL mtime 未达到稳定窗口时判未完成。
- 用 profile settings 样例断言:合并默认 settings 后 `hooks` / `statusLine` 被删除。
- 用 worker credentials 样例断言:
  - profile -> run home 同步只接受合法 JSON 和 `claudeAiOauth`。
  - 同步写入本地 credentials 使用临时文件 + rename。
  - profile 旧 token 不覆盖 run home 中刚刷新的新 token / 新 RT。
  - run home 中刚轮换的新 accessToken / refreshToken 会按新鲜度原子回写 profile。
  - 同账号两个 worker 同时强制 refresh 时必须通过 profile 文件锁串行化。
  - 401 后强制 refresh 失败或等待新 credentials 超时会写 `.bench-status.json` 且退出码语义为 `auth_failed`。
- 用 worker/quota 启动路径断言:usage 前等待通用 DNS resolver 可用,只在 access token 快过期时刷新 OAuth,刷新不用 Python `urllib`,且 DNS/URL 临时失败有限重试。
- 用 Claude JSONL 样例断言:
  - `system api_error` 的 `ECONNRESET` 后超过 watchdog 窗口且无产物/对话进展时触发恢复。
  - transcript 中 `Request timed out · Retrying ...` 后超过 watchdog 窗口且无产物/对话进展时触发恢复。
  - synthetic `Request timed out` API error 消息判 `failed`,不判 `success`。
  - API error 后已有 assistant/tool/文件进展时不触发恢复。
  - OAuth 401 文本仍走 `auth_failed`,不走 API 卡死恢复。
- 远程发布后跑一个真实 task,检查 DB 里 `success` run 的 JSONL 最新对话消息是 assistant 文本,而不是 user `tool_result`。

### 7. Wrong vs Correct

#### Wrong

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [{ "type": "command", "command": "touch /tmp/claude-done" }] }
    ]
  }
}
```

#### Correct

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [{ "type": "command", "command": "date +%s >> /tmp/claude-stop-seen" }] }
    ]
  }
}
```

成功文件只能由 JSONL 完成判定器在确认“稳定的最终 assistant 文本”后创建。

更严格地说,新代码不应再依赖 `/tmp/claude-done` 作为成功来源;成功只应来自当前 worker 进程内对 JSONL 的即时判定结果。

#### Wrong

```json
{
  "statusLine": {
    "type": "command",
    "command": "/workspace/.bench-quota-status.sh"
  }
}
```

#### Correct

```json
{
  "permissions": {
    "defaultMode": "bypassPermissions"
  }
}
```

profile settings 中不保存 `statusLine`;额度查询走 OAuth usage API 或临时容器内的一次性脚本。

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

## Recreate 协议(关键 ⚠)

orchestrator 的 `main.py` 是 `COPY` 进镜像的(不是挂载),改了 main.py 后:

| 操作 | 效果 | 用于 |
|------|------|------|
| ❌ `docker compose restart` | 重启容器进程,但**仍用旧 image** | 改 env / 配置(本项目几乎不用) |
| ✅ `docker compose up -d --force-recreate` | 销毁容器 + 用新 image 起新容器 | 推完镜像后 |

webui/ 和 topics.md 是 bind mount → **改它们不需要 recreate**,远程 git pull 即可生效(浏览器需要 Ctrl+F5 绕缓存)。

---

## Validation & Error Matrix

| 操作 | 错误现象 | 根因 | 修复 |
|------|---------|------|------|
| `docker push` 401 | `denied: requested access to the resource is denied` | 未 `docker login` 或登错 namespace | `docker login`,确认 `~/.docker/config.json` 的 username |
| 远程 pull 慢/卡 | worker 1.37 GB 一直 0% | DockerHub 限流 / 网络慢 | 给 docker daemon 配镜像加速器 |
| recreate 后还是旧行为 | 改了代码但容器内仍是旧版 | 用了 `restart` 不是 `--force-recreate`,或镜像 tag 没动 | `docker compose pull` + `up -d --force-recreate` |
| 三镜像版本错配 | worker 调用 sidecar 接口字段对不上 | 只 push 了改的镜像,sha tag 不对齐 | 三镜像全部打同一 sha,即使没改 |

---

## Good / Base / Bad Cases

**Good**:改 orchestrator 一处 → build orchestrator → 三镜像全部 retag 新 sha → push 三镜像 latest + sha(worker/sidecar 因为内容没变,push 只是 manifest 更新,~1s 完成) → 远程 `pull && up -d --force-recreate`。

**Base**:只改 orchestrator → 只 build + push orchestrator(latest + sha) → 远程 pull orchestrator + recreate。worker/sidecar sha 滞后一个版本但 `:latest` 仍可拉。**注意**:这种情况下 sha tag 不再三件套配套,回滚 `:某 sha` 时可能只能找到 orchestrator,worker/sidecar 那个 sha 不存在 → 部署要求 sha 配套时 fallback `:latest` 或上一个有配套的 sha。

**Bad**:只 build 不 push,远程拉不到新版;或 push 了忘记远程 recreate,远程仍跑旧容器;或 recreate 时忘了先 pull,daemon 拿不到新镜像(本地无该 tag)直接报错。

---

## Tests Required(手动验)

发布完成后,**远程** 跑以下断言:

1. `docker images huajiwuyan/vibebench-orchestrator` 包含新 sha tag
2. `docker inspect vibebench-orchestrator --format='{{.Image}}'` 与刚 pull 的 image ID 一致
3. `curl http://<host>:<port>/api/auth/me` 返回符合新版本的 contract(如 `auth_required` 字段)
4. orchestrator 日志末尾出现 `Application startup complete` 且无 ERROR

---

## Wrong vs Correct

### ❌ Wrong: 改 main.py 后只 restart

```bash
# 错:用 docker compose restart
docker compose build orchestrator
docker compose restart orchestrator   # 仍是旧 image 跑!
```

### ✅ Correct: 改 main.py 后 force-recreate

```bash
docker compose build orchestrator
docker compose up -d --force-recreate orchestrator
```

### ❌ Wrong: 只 push 改了的镜像 sha tag

```bash
docker push huajiwuyan/vibebench-orchestrator:158b462
# worker/sidecar 还停在 9787fc1 — sha 配套缺失
```

### ✅ Correct: 三件套对齐 sha tag

```bash
SHA=158b462
docker tag vibebench-worker:latest  huajiwuyan/vibebench-worker:$SHA
docker tag vibebench-sidecar:latest huajiwuyan/vibebench-sidecar:$SHA
docker push huajiwuyan/vibebench-worker:$SHA       # ~1s (内容未变,manifest only)
docker push huajiwuyan/vibebench-sidecar:$SHA      # ~1s
docker push huajiwuyan/vibebench-orchestrator:$SHA # 正常推
```

---

## Common Mistakes

| 反模式 | 现象 | 怎么改 |
|--------|------|--------|
| `docker compose restart` 当作"重启加载新镜像" | 改代码不生效 | `up -d --force-recreate` |
| 单 tag(只 latest) | 想回滚找不到旧版 | 每发版必打 `:<git-sha>` |
| 忘记三镜像 sha 对齐 | 用 `:某 sha` 拉时缺其中两个 | 即使没改也 retag + push(秒级,值得) |
| 推完忘 git push | 镜像有了但 GitHub 还是旧 commit,sha tag 找不到对应源码 | push 镜像前/后 `git push origin <branch>`,顺序无所谓但都要做 |
| 在 build profile 之外去 build worker/sidecar | `service "worker-image" not found` | 加 `--profile build` |
