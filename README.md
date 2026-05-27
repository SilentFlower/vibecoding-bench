# vibecoding-bench

把 [`topics.md`](./topics.md) 里的 200 道题作为题库，让真实的 **Claude Code** 在容器里跑，按账号隔离、按账号并发限流、全程透明代理 + TLS MITM 抓 Anthropic API 原文。

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
│     → proxychains 包装 mitmproxy 出站 → 上游 SOCKS5
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

## WebUI 使用

| 页 | 用途 |
|---|---|
| **账号** | 添加在 init-account.sh 已建好 profile 的账号，配置上游 SOCKS5 |
| **题库** | 200 题；点击卡片 → 查看 / 编辑 topic，批量任务页可多选派发 |
| **任务** | 列表 + ▶ 运行（按 repeat_n 提交多次）|
| **运行** | SSE 实时列表 + 详情：transcript / 产物文件树 / token 统计 |

## 关键决策（已锁定 PRD）

| 项 | 选择 |
|---|---|
| Claude 接入 | 交互式 `claude`（非 `-p`），tmux 驱动，Stop hook 判完成 |
| 账号类型 | 仅 OAuth，mount `~/.claude/` |
| 并发 | 单账号 2 并发；总并发 = 账号数 × 2 |
| 任务派发 | 创建任务时指定账号，不切换 |
| 速率限制 | 撞限即停（标 failed），不自动切其它账号 |
| 透明代理 | sidecar 容器 + hev-socks5-tunnel + mitmproxy（TLS MITM）|
| WebUI | 纯 HTML + 原生 JS + SSE，零构建 |

## 目录结构

```
bench/
├── docker-compose.yml
├── .env.example
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
    ├── flows/<acc>/<task>/<run>/   stats.jsonl（SAVE_FULL_FLOWS=1 时额外保留 .flow）
    ├── workspaces/<run>/    claude 工作目录 + .bench-transcript.log
    └── db.sqlite
```

## P1 范围 vs 后续

**P1 已实现**：账号 CRUD、题库解析、topic 持久化维护、任务批量创建/运行、单账号 2 并发调度、sidecar+worker 编排、TLS MITM + flow 落盘、token 统计、SSE 实时状态、详情面板。

**待 P2**：多账号管理 UI、循环跑（题库扫完再来一轮）、按账号统计仪表盘、mitmproxy flow 在 WebUI 内浏览、失败重试策略、Stop hook 检测的更精细判定。

**待 P3（评测）**：自动跑产物里的测试 / lint / 起 dev server 截图 / LLM-as-judge。

## 已知限制 / 排查

- **HOST_BENCH_DATA 必须是宿主机绝对路径**，不能填 `./data`——orchestrator 用它告诉宿主 daemon 给 sibling 容器挂卷。
- **topics.md 只在 topics 表为空时 seed**。已经运行过的本地/远程实例需要执行 `scripts/sync-topics-db.py --apply` 才会把新版题库同步进 SQLite；默认不带 `--apply` 只做 dry-run。远程如果不是 git 仓库，执行前要先同步这个脚本。
- **OAuth flow** 假设 claude CLI 是 device-code/复制粘贴码方式；如果它非要回调到 `localhost:port`，init-account.sh 需要加 `-p` 端口映射。
- **首次 MITM CA 生成**：sidecar 启动时若 `data/ca/` 为空，会让 mitmproxy 自己生成；worker 启动时 CA 已经在卷里。若并发首次启动多个 run，有微小窗口期某些 run 拿不到 CA——P1 用 `SIDECAR_BOOT_WAIT=4` 兜底，足以；P2 改成显式等 CA 文件就绪。
- **certificate pinning 风险**：claude-code 当前不 pin；后续升级若 pin，MITM 会失败，需补丁或回退到不解密模式。
- **超时**：默认每 run 1800s，可在创建任务时调整。
- **磁盘占用**：默认 `SAVE_FULL_FLOWS=0` 不再保存完整 MITM `.flow`，只保留 `stats.jsonl`；默认 `CLEAN_WORKSPACE_DEPS=1` 会在 run 结束后清理 workspace 里的 `node_modules`、`.venv` 等依赖目录。
