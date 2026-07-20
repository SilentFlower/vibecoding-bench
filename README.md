# vibecoding-bench

把 [`topics.md`](./topics.md) 里的 300 道题作为题库，让真实的 **Claude Code** 在容器里跑，按账号隔离、按账号并发限流、全程透明代理 + TLS MITM 抓 Anthropic API 原文。

## 架构

```
┌─ WebUI (静态 HTML)
│
├─ Orchestrator (FastAPI + SQLite + Docker SDK)
│     每账号信号量=2；指定账号派发；SSE 推 runs
│             │
│  per-run ↓ 起两个容器（sidecar 先起，worker 共享其 netns）
│
├─ Sidecar  (hev-socks5-tunnel + mitmproxy 11)
│     tun → socks5 inbound → TLS MITM 解密 + flow 落盘
│     → proxychains 包装 mitmproxy 出站 → 上游 HTTP/SOCKS5 代理
│
└─ Worker   (node:22 + claude-code + tmux)
     network_mode: container:sidecar  ← 流量必走代理
     entrypoint：注入 MITM CA → 复制账号 profile → 注入 Stop hook
                 → tmux 内启动 `claude` → bracketed-paste 题目
                 → 等 Stop hook / 超时 → 抓 transcript 退出
```

## 启动

```bash
cd bench

# 1. 配置宿主机路径
cp .env.example .env
# 编辑 .env，把 HOST_BENCH_DATA 设为本目录 data/ 的绝对路径

# 2. 构建三个镜像
docker compose --profile build build

# 3. OAuth 登录至少一个账号
./scripts/init-account.sh main
# → 容器里启动 claude，运行 /login 完成 OAuth，退出后 profile 落到 data/profiles/main/

# 4. 启动后端
docker compose up -d orchestrator

# 5. 打开 WebUI
open http://localhost:8000
```

## 镜像发布与远程升级

push 到 `main` 后，[Docker 发布 workflow](https://github.com/SilentFlower/vibecoding-bench/actions/workflows/docker-publish.yml) 会构建并推送三组 `linux/amd64`、`linux/arm64` 镜像：

- `ghcr.io/silentflower/vibebench-orchestrator`
- `ghcr.io/silentflower/vibebench-worker`
- `ghcr.io/silentflower/vibebench-sidecar`

每组镜像同时发布 `latest` 和原始 7 位短 Git SHA tag。也可以在 Actions 页面手动运行 workflow，但发布 job 只接受 `main` ref，避免功能分支覆盖 `latest`。

首次发布后，三个 GHCR package 默认是 private。需要分别进入 package settings，将可见性改为 **Public**，再在未登录 GHCR 的远程主机验证镜像可以匿名拉取。package 公开后不能再改回 private。

远程部署继续使用 `docker-compose.remote.yml`：

```bash
docker compose -f docker-compose.remote.yml --env-file .env pull
docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator
```

`.env` 中不设置 `VIBEBENCH_TAG` 时使用 `latest`；需要锁定或回滚时，设置为某次成功 workflow 的 7 位短 SHA。

## WebUI 使用

| 页 | 用途 |
|---|---|
| **账号** | 添加 OAuth profile、配置上游代理、单账号同步/绑定 cc2api，并设置随机间隔养号 |
| **题库** | 300 题；点击卡片 → 查看 / 编辑 topic，批量任务页可多选派发 |
| **任务** | 列表 + ▶ 运行（按 repeat_n 提交多次）|
| **运行** | SSE 实时列表 + 默认模型 / 思考预算配置 + 详情：transcript / 产物文件树 / token 统计；显示抓包和养号 run 标识 |

## 关键决策（已锁定 PRD）

| 项 | 选择 |
|---|---|
| Claude 接入 | 交互式 `claude`（非 `-p`），tmux 驱动，Stop hook 判完成 |
| 账号类型 | 仅 OAuth，mount `~/.claude/` |
| 并发 | 单账号 2 并发；总并发 = 账号数 × 2 |
| 任务派发 | 创建任务时指定账号，不切换 |
| 速率限制 | 撞限即停（标 failed），不自动切其它账号 |
| 思考预算 | 普通 / 批量 run 默认使用 WebUI 运行页配置；未配置时回退到 `CLAUDE_CODE_EFFORT_LEVEL=max` |
| 默认模型 | 普通 / 批量 run 默认使用 WebUI 运行页配置；未配置时回退到 `CLAUDE_DEFAULT_MODEL=opus[1m]` |
| Claude Code 版本 | 新启动 worker 使用 WebUI 运行页配置；未配置时回退到 `CLAUDE_CODE_VERSION=2.1.197` |
| 透明代理 | sidecar 容器 + hev-socks5-tunnel + mitmproxy（TLS MITM）|
| WebUI | 纯 HTML + 原生 JS + SSE，零构建 |

## 目录结构

```
bench/
├── docker-compose.yml
├── .env.example
├── cc2api/              Git submodule: Claude Code 网关与账号池
├── orchestrator/        FastAPI 后端
│   ├── main.py
│   ├── Dockerfile
│   └── requirements.txt
├── webui/               静态前端
│   ├── index.html
│   ├── style.css
│   └── app.js
├── images/
│   ├── worker/          node + claude-code + tmux entrypoint
│   └── sidecar/         hev-socks5-tunnel + mitmproxy + proxychains
├── scripts/
│   └── init-account.sh  OAuth profile 引导脚本
└── data/                运行时数据（已 gitignore）
    ├── profiles/<acc>/      每账号一份 ~/.claude 副本
    ├── ca/                  mitmproxy 持久 CA（首次启动自动生成）
    ├── flows/<acc>/<task>/<run>/   stats.jsonl；抓包 run 额外有 http_capture.jsonl / capture_index.json / .flow
    ├── workspaces/<run>/    claude 工作目录 + .bench-transcript.log
    └── db.sqlite
```

## P1 范围 vs 后续

**P1 已实现**：账号 CRUD、题库解析、topic 持久化维护、任务批量创建/运行、单账号 2 并发调度、sidecar+worker 编排、TLS MITM + flow 落盘、token 统计、SSE 实时状态、详情面板、单 topic + 单账号完整 HTTP 抓包分析 run，以及 cc2api 单账号同步和定时养号。

**待 P2**：多账号批量同步、按账号统计仪表盘、mitmproxy flow 在 WebUI 内浏览、失败重试策略、Stop hook 检测的更精细判定。

## cc2api 绑定与定时养号

在 `.env` 中配置 `CC2API_BASE_URL` 和 `CC2API_ADMIN_PASSWORD` 后，账号页可以把单个现有 bench OAuth profile 同步到 cc2api，或显式选择同一身份的 active OAuth 账号进行绑定。同步匹配优先使用 `accountUuid`；bench profile 缺少 UUID 时才按邮箱匹配，账号名称不参与匹配。

绑定账号由 cc2api 单独持有并刷新 AT/RT。bench 在每次 run 前解析 cc2api 最新凭据；worker 运行副本会移除 RT，401 时只请求 cc2api 强制刷新一次，不能再走本地 refresh。绑定期间必须先解绑才能使用 bench 的重授权入口。

养号按账号配置最小/最大小时间隔。每次到期从当前有效题库随机抽题，优先排除该账号最近 20 个养号题目，创建真实 `run_kind=warmup` task/run 并继续受账号并发限制。临时 cc2api 故障按 `WARMUP_SYNC_RETRY_SEC` 重试；连续 3 次 `auth_failed` 或永久凭据错误会自动暂停。

下例假设 orchestrator 与 cc2api 已加入同一个 Docker network，且 cc2api 的服务名为 `claude-code-gateway`。若不共享网络，请改成 orchestrator 容器实际可达的外部地址。

```env
CC2API_BASE_URL=http://claude-code-gateway:5674
CC2API_ADMIN_PASSWORD=<admin-password>
CC2API_REQUEST_TIMEOUT_SEC=15
WARMUP_SCHEDULER_TICK_SEC=30
WARMUP_SYNC_RETRY_SEC=900
```

**待 P3（评测）**：自动跑产物里的测试 / lint / 起 dev server 截图 / LLM-as-judge。

## 完整 HTTP 抓包分析 run

运行页顶部的 `capture` 面板可以选择一个账号和一个 topic，启动一条专用抓包 run。该 run 复用普通 run 的账号 profile、上游代理、sidecar MITM 和 worker 执行流程，但会强制开启完整抓包，不受全局 `SAVE_FULL_FLOWS=0` 默认值影响。

输出目录：

```text
data/flows/<account>/<task_id>/<run_id>/
├── stats.jsonl          token / 状态码摘要，普通统计继续使用
├── http_capture.jsonl   每条 HTTP flow 的请求 headers、请求体全文、响应 headers、响应体全文
├── capture_index.json   轻量索引：method / host / path / status / bytes / cc_version / cc_entrypoint / CCH / 分类字段
└── *.flow               mitmproxy 原生 flow 文件
```

抓包 run 的 `http_capture.jsonl` 默认记录所有经过 sidecar MITM 的 HTTP flow，不只限于 Anthropic 域名；Datadog、Statsig、Sentry、WebSocket upgrade、额外遥测域名等请求只要走到 MITM，也会进入完整 JSONL。`capture_index.json` 会额外标记 `is_target`、`is_anthropic`、`is_telemetry_candidate`，便于从全量流量里筛 Anthropic 主链路和遥测候选。WebUI 详情页只展示脱敏索引；完整 `http_capture.jsonl` 会保存本地原文，可能包含 OAuth token、prompt、代码、响应内容、第三方请求内容等高敏数据，不要提交到 git，也不要暴露给不可信网络。

如果对抓包 run 点击“继续”并在继续会话里执行 `/cost`、`/context` 等操作，continue sidecar 会继承完整抓包配置，并把后续 HTTP flow 追加写回同一个 run 的 flows 目录；普通非抓包 run 的继续会话仍不保存完整请求/响应正文。

## 已知限制 / 排查

- **HOST_BENCH_DATA 必须是宿主机绝对路径**，不能填 `./data`——orchestrator 用它告诉宿主 daemon 给 sibling 容器挂卷。
- **topics.md 只在 topics 表为空时 seed**。已经运行过的本地/远程实例需要执行 `scripts/sync-topics-db.py --apply` 才会把新版题库同步进 SQLite；默认不带 `--apply` 只做 dry-run。远程如果不是 git 仓库，执行前要先同步这个脚本。
- **OAuth flow** 假设 claude CLI 是 device-code/复制粘贴码方式；如果它非要回调到 `localhost:port`，init-account.sh 需要加 `-p` 端口映射。
- **首次 MITM CA 生成**：sidecar 启动时若 `data/ca/` 为空，会让 mitmproxy 自己生成；worker 启动时 CA 已经在卷里。若并发首次启动多个 run，有微小窗口期某些 run 拿不到 CA——P1 用 `SIDECAR_BOOT_WAIT=4` 兜底，足以；P2 改成显式等 CA 文件就绪。
- **certificate pinning 风险**：claude-code 当前不 pin；后续升级若 pin，MITM 会失败，需补丁或回退到不解密模式。
- **超时**：默认每 run 1800s，可在创建任务时调整。worker 默认会在超时前 `TIMEOUT_WRAPUP_SEC=600` 秒注入一次收尾提示，要求 Claude 停止扩展并输出最终总结；设为 `0` 可关闭。
- **批次顺序**：题库浏览仍按编号展示；创建批次时会把已选 topic 随机写入执行队列，同一个批次内顺序固定，便于追踪运行结果。
- **思考预算**：普通 run 和批量 run 默认使用 WebUI「运行」页保存的思考预算；未保存页面覆盖值时回退到 `CLAUDE_CODE_EFFORT_LEVEL=max`。需要降低耗时或额度消耗时，优先在页面切到 `high` / `medium` / `low`，新启动的普通 / 批量 run 立即生效；清空页面覆盖后才回退到 `.env`。完整 HTTP 抓包 run 不受页面思考预算配置影响。只有修改 `.env` 兜底值时才需要重建 / recreate orchestrator。
- **API timeout 终态**：worker 会识别 Claude TUI 的 `API error` / `Request timed out` 重试卡死并按 watchdog 尝试恢复；如果 Claude JSONL 最终写入 synthetic `Request timed out`，run 会标记为 `failed` 并显示错误，不再当作 `success`。
- **默认模型**：普通 run 和批量 run 默认使用 WebUI「运行」页保存的模型；未保存页面覆盖值时回退到 `CLAUDE_DEFAULT_MODEL=opus[1m]`。如果某个模型临时不可用，优先在页面改成 `sonnet[1m]`、`haiku` 或完整模型 ID，新启动的普通 / 批量 run 立即生效；清空页面覆盖后才回退到 `.env`。完整 HTTP 抓包 run 不受页面配置或 `CLAUDE_DEFAULT_MODEL` 影响，只在抓包页填写 `model_override` 时覆盖当前抓包 run。

- **Claude Code 版本**：新启动的 task / 抓包 / 登录 / quota worker 使用 WebUI「运行」页保存的版本；未保存页面覆盖值时回退到 `CLAUDE_CODE_VERSION=2.1.197`。版本覆盖会在 worker 启动时检查 `claude --version`，不一致则安装指定 `@anthropic-ai/claude-code` 版本。清空页面覆盖后才回退到 `.env`。
- **OAuth 401 / token 刷新竞态**：未绑定账号保留原有 profile 新鲜度同步和一次本地强制 refresh。绑定 cc2api 的账号只镜像 cc2api 凭据，worker 不持有 RT、不反向覆盖 credentials；首次 401 会请求 orchestrator 让 cc2api 强制刷新并只重试一次，再次失败标记 `auth_failed`。
- **磁盘占用 / 敏感数据**：普通 run 默认 `SAVE_FULL_FLOWS=0`，只保留 `stats.jsonl`；完整抓包 run 会保存请求体和响应体全文、`.flow` 和索引，体积更大且包含高敏数据；默认 `CLEAN_WORKSPACE_DEPS=1` 会在 run 结束后清理 workspace 里的 `node_modules`、`.venv` 等依赖目录。
