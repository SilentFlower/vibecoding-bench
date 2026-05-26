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

修改 `images/worker/entrypoint.sh` 的 Claude task 模式时必须遵守本契约。worker 是 run 终态的唯一来源:退出码 `0` 会被 orchestrator 映射成 `success`,退出码 `124` 映射成 `timeout`,其它非 0 映射成 `failed`。

### 2. Signatures

task 模式环境变量:

| Env | 必填 | 含义 |
|-----|------|------|
| `TASK_PROMPT` | 是 | 原始题目 prompt |
| `RUN_ID` | 是 | 当前 run id,用于 tmux session 与日志归档 |
| `TIMEOUT_SEC` | 否 | worker 硬超时时间,默认 1800 |
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

Claude 返回认证错误文本时必须失败,不能作为最终 assistant 回复标成功。至少识别:

- `Please run /login`
- `API Error: 401`
- `Invalid authentication credentials`
- `OAuth token has expired`

task 启动前可以刷新 OAuth access token,但必须先读 `.credentials.json` 里的 `claudeAiOauth.expiresAt`:只有 access token 缺失、已过期或距离过期小于安全缓冲(当前 10 分钟)时才调用 refresh endpoint,避免每次 run 都刷新 token。

刷新 OAuth access token 或查询 OAuth usage API 前必须确认 sidecar DNS 对 `platform.claude.com` 和 `api.anthropic.com` 都可解析。不能只等待 `api.anthropic.com`:refresh endpoint 在 `platform.claude.com`,quota probe 又是通过 `docker exec` 进入 login-mode worker,两者都可能踩到 sidecar/unbound 冷启动竞态。DNS readiness 和 Python URL 请求都必须是有限等待/有限重试,不能无限循环。

不能用宿主机网络或宿主 DNS 作为 OAuth refresh / usage 的 fallback。账号相关请求和域名解析都必须留在 worker→sidecar→账号 SOCKS5 链路里,否则会从宿主原始 IP 泄漏域名查询或 HTTPS 出口。

worker 不能因为没看到最终 assistant 文本而反复向 Claude 追加 prompt；只能等待 JSONL 变化,直到完成、Claude 退出或 `TIMEOUT_SEC` 到期。

### 4. Validation & Error Matrix

| 条件 | worker 退出 | orchestrator 终态 |
|------|-------------|-------------------|
| 最新对话消息是稳定的纯文本 assistant 回复 | `0` | `success` |
| 最新对话消息是 user `tool_result` | 继续等到后续完成或超时 | 非 success |
| 最新 assistant 文本包含 `/login` / 401 认证错误 | `1` | `failed` |
| Claude 以 0 退出但没有最终 assistant 文本 | `1` | `failed` |
| 达到 `TIMEOUT_SEC` 仍无最终 assistant 文本 | `124` | `timeout` |
| 收到 `TERM/INT` | 先白名单回写 profile,再退出 | `stopped` 或 `failed` 由 orchestrator 状态决定 |

### 5. Good/Base/Bad Cases

**Good**:Claude 写完文件、跑完检查,最终回复一段纯文本总结。JSONL 稳定窗口后,worker 退出 `0`。

**Base**:Claude 停在工具结果后,TUI 回到输入框,但 JSONL 最新消息是 user `tool_result`。worker 继续等待,不会把该 run 标成 `success`。

**Bad**:Stop hook 执行 `touch /tmp/claude-done`,worker 只看这个文件就退出 `0`。这会把“工具调用中间态”误判为成功。

**Bad**:quota/statusLine 探测把 `statusLine` 写入账号 profile 的 `settings.json` 并回写。后续 task 会加载这段运行态配置,污染被测 run。

**Bad**:access token 明明还有很久才过期,每次 task 启动都调用 OAuth refresh endpoint。这样会制造额外请求和不必要的凭据轮换。

**Bad**:worker 启动前只等 `api.anthropic.com` 可解析,然后立刻刷新 OAuth token。`platform.claude.com` 尚未解析成功时会出现 `<urlopen error [Errno -3] Temporary failure in name resolution>`。

**Bad**:为了解决完成判定,把 `BENCH_DONE:<RUN_ID>` 之类的 bench sentinel 拼进题目 prompt。这样会污染被测任务的自然输出。

### 6. Tests Required

- `bash -n images/worker/entrypoint.sh`
- 用本地 JSONL 样例断言:
  - 最新消息是 user `tool_result` 时判未完成。
  - 最新消息是 assistant `tool_use` 时判未完成。
  - 最新消息是稳定的 assistant 文本时判完成。
  - 最新 assistant 文本包含 `Please run /login · API Error: 401 Invalid authentication credentials` 时判失败。
  - 最新 session JSONL mtime 未达到稳定窗口时判未完成。
- 用 profile settings 样例断言:合并默认 settings 后 `hooks` / `statusLine` 被删除。
- 用 worker/quota 启动路径断言:OAuth refresh/usage 前等待 `platform.claude.com` 和 `api.anthropic.com`,且 DNS/URL 临时失败有限重试。
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
