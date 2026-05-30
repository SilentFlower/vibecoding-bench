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
| `OAUTH_CREDENTIAL_SYNC_INTERVAL_SEC` | 否 | 运行中从账号 profile 单向同步 `.credentials.json` 的间隔,默认 15;`0` 关闭 |
| `OAUTH_401_PROFILE_WAIT_SEC` | 否 | 检测到 401 后等待后台刷新器更新 profile credentials 的最长秒数,默认 90;`0` 不等待 |
| `COMPLETION_IDLE_SEC` | 否 | JSONL 稳定窗口,默认 10 秒 |

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

task worker **禁止**在启动 run 前强制刷新 OAuth access token。启动前只校验 `.credentials.json` 的结构和 `accessToken` 是否存在,即使 access token 已过期或即将过期也不在 worker 启动阶段拒绝运行。真正刷新由 orchestrator 后台 `OAuthRefreshScheduler` 周期执行,并把新 `.credentials.json` 原子写回账号 profile。

task 运行期间必须单向同步 credentials:从 `/mnt/profile/.credentials.json` 同步到本地 `$HOME/.claude/.credentials.json`,不能从 run home 把 `.credentials.json` 回写覆盖 profile。同步前必须能解析 JSON 且存在 `claudeAiOauth`;写本地文件必须先写临时文件再 `rename` 原子替换。退出 / 停止路径只允许回写 `settings.json` 和 `.claude.json` 这类配置文件。

运行中检测到 401 / OAuth 认证错误时,worker 先同步 profile credentials;如果是第一次认证错误,最多等待 `OAUTH_401_PROFILE_WAIT_SEC` 秒让后台刷新器把新 credentials 落盘。只有本地 credentials 指纹变化且 `expiresAt` 明显越过安全缓冲区后,才向 Claude TUI 注入一次重试提示。等不到新 credentials 或重试后再次出现认证错误时,worker 写 `/workspace/.bench-status.json` 为 `{"status":"auth_failed","error":"..."}` 并以退出码 `42` 结束。

查询 OAuth usage API 前必须确认 sidecar 的通用 DNS resolver 已可用。sidecar/unbound 配的是通配 `forward-zone "."`,所以 readiness probe 应验证一个稳定探针域名能解析,不能把每个业务目标域名硬编码成白名单。orchestrator 可以用 `docker exec` 进 sidecar 等 `/tmp/sidecar-ready` 或通用探针解析成功,但不能用 orchestrator/宿主机网络代替 sidecar 解析。usage probe 必须在 worker 容器内按同一套 `expiresAt` 规则刷新 access token,再读 `.credentials.json` 调 usage API。实际 API URL 请求还必须有限重试,覆盖 resolver 刚启动后的瞬时 `Temporary failure in name resolution`。

不能用宿主机网络或宿主 DNS 作为 OAuth refresh / usage 的 fallback。账号相关请求和域名解析都必须留在 worker→sidecar→账号 SOCKS5 链路里,否则会从宿主原始 IP 泄漏域名查询或 HTTPS 出口。

上游 SOCKS5 服务器地址可以填域名。这个域名是建立代理链路之前的 bootstrap 解析,只能用 sidecar 启动时的默认 DNS 解析成 IP 后再连接代理;它和 Claude/API/WebFetch 访问的业务目标域名不是一类问题。不要为了阻断业务 DNS 泄漏而禁止 SOCKS5 域名。

worker 镜像里的 Claude Code CLI 版本、worker 运行时 `CLAUDE_CODE_VERSION`、OAuth usage 请求的 `User-Agent` 必须保持一致。当前固定为 `2.1.156`;升级时要同时改 Dockerfile 默认版本、orchestrator 注入的默认环境变量和 usage 请求头,不能让 runner 实际版本与 usage API UA 脱节。OAuth refresh 请求不要带 `User-Agent`:实测带 `claude-code/<version>` 会触发 token endpoint 429;refresh 仍必须在 worker→sidecar→账号 SOCKS5 链路内完成。

worker 不能因为没看到最终 assistant 文本而反复向 Claude 追加 prompt；只能等待 JSONL 变化,直到完成、Claude 退出或 `TIMEOUT_SEC` 到期。

### 4. Validation & Error Matrix

| 条件 | worker 退出 | orchestrator 终态 |
|------|-------------|-------------------|
| 最新对话消息是稳定的纯文本 assistant 回复 | `0` | `success` |
| 最新对话消息是 user `tool_result` | 继续等到后续完成或超时 | 非 success |
| 首次检测到 401 且后台刷新器及时写入新 credentials | 注入一次重试提示并继续等待 | 取决于后续完成结果 |
| 401 后等待 profile 刷新超时 | `42` | `auth_failed` |
| 重试后再次检测到 `/login` / 401 认证错误 | `42` | `auth_failed` |
| Claude 以 0 退出但没有最终 assistant 文本 | `1` | `failed` |
| 达到 `TIMEOUT_SEC` 仍无最终 assistant 文本 | `124` | `timeout` |
| 收到 `TERM/INT` | 先白名单回写 profile,再退出 | `stopped` 或 `failed` 由 orchestrator 状态决定 |

### 5. Good/Base/Bad Cases

**Good**:Claude 写完文件、跑完检查,最终回复一段纯文本总结。JSONL 稳定窗口后,worker 退出 `0`。

**Base**:Claude 停在工具结果后,TUI 回到输入框,但 JSONL 最新消息是 user `tool_result`。worker 继续等待,不会把该 run 标成 `success`。

**Bad**:Stop hook 执行 `touch /tmp/claude-done`,worker 只看这个文件就退出 `0`。这会把“工具调用中间态”误判为成功。

**Bad**:quota/statusLine 探测把 `statusLine` 写入账号 profile 的 `settings.json` 并回写。后续 task 会加载这段运行态配置,污染被测 run。

**Bad**:access token 明明还有很久才过期,每次 task 启动都调用 OAuth refresh endpoint。这样会制造额外请求和不必要的凭据轮换。

**Bad**:task worker 启动时发现 access token 已过期或 10 分钟内过期,就直接刷新或直接失败。正确做法是让 run 启动,运行中按 profile 单向同步;如果 Claude 实际遇到 401,再等待后台刷新器落盘并只重试一次。

**Bad**:task 结束时把 run home 里的 `.credentials.json` 回写到真实账号 profile。后台刷新器可能已经写入了更新 token,旧 run 结束再回写会把新 token 覆盖掉。

**Bad**:worker 启动前只等 `api.anthropic.com` 可解析,然后立刻刷新 OAuth token。`platform.claude.com` 尚未解析成功时会出现 `<urlopen error [Errno -3] Temporary failure in name resolution>`。

**Bad**:用 Python `urllib` 直接调用 `https://platform.claude.com/v1/oauth/token` 刷新 access token。Cloudflare 可能按浏览器签名返回 1010 `browser_signature_banned`;正确做法是在 worker 容器里按 `expiresAt` 判断后用 Node runtime 刷新,并把刷新后的 `.credentials.json` 回写 profile。

**Bad**:对 `platform.claude.com` 做 MITM 解密后再刷新 OAuth token。这样 Cloudflare 看到的是 mitmproxy/OpenSSL 的上游 TLS 指纹,不是 Claude CLI/Node 指纹,更容易触发 1010。该域名应在 sidecar 中 TLS passthrough,仍走同一个 SOCKS5 出口但不解密。

**Bad**:每遇到一个新网页域名就加一个 DNS 等待白名单。正确做法是验证 sidecar 的通用 resolver 可用,后续任意域名都走同一条 worker→unbound→tun→SOCKS5 链路。

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
  - run 结束路径不把 `.credentials.json` 回写 profile。
  - 401 后等待新 credentials 超时会写 `.bench-status.json` 且退出码语义为 `auth_failed`。
- 用 worker/quota 启动路径断言:usage 前等待通用 DNS resolver 可用,只在 access token 快过期时刷新 OAuth,刷新不用 Python `urllib`,且 DNS/URL 临时失败有限重试。
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
