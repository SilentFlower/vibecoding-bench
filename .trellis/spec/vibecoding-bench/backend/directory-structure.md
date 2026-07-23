# Directory Structure

> 本项目后端代码的组织方式。

---

## Overview

后端是一个**极简单文件 FastAPI 服务**:整个 orchestrator 业务逻辑都在 `orchestrator/main.py` 一个文件里,辅以一份 `scripts/init-account.sh` 引导 OAuth profile,以及两个容器镜像(`images/worker`、`images/sidecar`)的构建产物。

**核心理念**:P1 阶段(MVP)优先功能跑通,不为了"工程优雅"提前拆模块。当 `main.py` 真的拆不动时(预计超过 ~1500 行 / 单一职责开始模糊)再考虑拆包。

---

## Directory Layout

```
项目根/
├── orchestrator/                 FastAPI 后端(P1 全部在一个 main.py 里)
│   ├── main.py                   入口 + 配置 + DB + Runner + LoginManager + Scheduler + 所有路由
│   ├── Dockerfile                基于 python:3.11-slim,装 docker SDK + fastapi + sse-starlette
│   └── requirements.txt          依赖锁定文件,极简(<10 行)
│
├── scripts/
│   └── init-account.sh           CLI 模式 OAuth 引导(早期备份方案;WebUI 已可内嵌登录)
│
├── images/                       Docker 镜像构建上下文(运行时由 orchestrator 拉起)
│   ├── worker/                   node:22 + claude-code + tmux,跑题目的容器
│   └── sidecar/                  hev-socks5-tunnel + mitmproxy + proxychains,透明代理 + MITM
│
├── data/                         运行时数据(已 gitignore,挂卷进容器)
│   ├── profiles/<acc>/           每账号一份 ~/.claude
│   ├── ca/                       mitmproxy 持久 CA
│   ├── flows/<acc>/<task>/<run>/ .flow + stats.jsonl(sidecar 写)
│   ├── workspaces/<run>/         claude 工作目录 + .bench-transcript.log
│   └── db.sqlite                 唯一持久化:SQLite 单文件
│
├── docker-compose.yml            orchestrator 服务 + 镜像 build profile
├── .env.example                  HOST_BENCH_DATA 等环境变量样板
└── topics.md                     seed 题库(当前 600 道;SQLite 为空时导入；已 seed 实例需 scripts/sync-topics-db.py 同步)
```

---

## Module Organization

`orchestrator/main.py` 内部按"水平分节"组织,而不是拆类/拆包。每一节用 `# ============== 节名 ==============` 顶行注释开头,顺序固定:

```python
# ============== 配置 ==============         # 环境变量、路径常量
# ============== DB ==============           # _SCHEMA 字符串、get_db()、init_db()
# ============== Topics 解析 ==============   # _CAT_RE / _ITEM_RE + load_seed_topics()
# ============== Docker 运行器 ==============  # class Runner
# ============== Login 会话管理 ==============  # class LoginSession / LoginManager
# ============== 调度器 ==============         # class Scheduler
# ============== FastAPI ==============       # app = FastAPI(...) + lifespan
# ---------- accounts ----------              # 路由按资源分组,二级 # ---------- 分隔
# ---------- accounts: 内嵌 OAuth 登录 ----------
# ---------- topics ----------
# ---------- tasks ----------
# ---------- runs ----------
# ---------- SSE ----------
# ---------- 静态 WebUI ----------
```

**何时新增节** vs **何时塞进现有节**:
- 新资源(新的 REST 实体)→ 新 `# ---------- xxx ----------` 节,放在 FastAPI 路由区
- 新的横切能力(新的后台守护、新的协议桥)→ 新建顶级 `# ============== xxx ==============` 节,放在 FastAPI 之前
- 对现有资源的增量端点 → 塞进对应节,保持节内按"create / list / get / update / delete / 子操作"顺序

**何时该拆包**(目前 P1 都不满足,**不要预先拆**):
- `main.py` 超过 ~1500 行,且某一节自身已经 >300 行 → 把那一节拆成 `orchestrator/<name>.py`,在 `main.py` 顶部 import
- 出现第二个进程入口(例如独立的 worker 进程、独立的清理 daemon)→ 新文件
- 测试需要独立 import 某节(目前没有测试,所以不算)→ 抽出来

---

## Naming Conventions

- **文件名**:全部小写 + 下划线,如 `main.py`、`init-account.sh`(脚本可用短横线)
- **Python 类**:`PascalCase`,如 `Runner` / `Scheduler` / `LoginSession` / `LoginManager`
- **Python 函数 / 变量**:`snake_case`,如 `load_topics` / `init_db` / `run_id`
- **Python 私有**:单下划线前缀,如 `_db_lock` / `_SCHEMA` / `_ACC_NAME_RE` / `_sem()`
- **常量**:`UPPER_SNAKE`,如 `BENCH_DATA` / `WORKER_IMAGE` / `PER_ACCOUNT_CONCURRENCY` / `SIDECAR_BOOT_WAIT`
- **正则**:`_NAME_RE` 后缀,模块级常量(`_CAT_RE` / `_ITEM_RE` / `_ACC_NAME_RE`)
- **Docker 容器命名**:`bench-<role>-<id>`,如 `bench-sidecar-<run_id>` / `bench-worker-<run_id>` / `bench-login-sidecar-<sid>` / `bench-login-worker-<sid>`(`bench-login-*` 前缀用于启动时一键清残留)

**API 路径**:
- 全部挂在 `/api` 前缀下(`/` 留给静态 WebUI)
- 资源用复数:`/api/accounts`、`/api/tasks`、`/api/runs`、`/api/topics`
- 子资源:`/api/runs/{rid}/transcript`、`/api/runs/{rid}/files`、`/api/runs/{rid}/stats`
- 流端点:`/api/runs/stream`(SSE)、`/api/accounts/login/ws/{sid}`(WebSocket)
- 动作端点:HTTP 动词不够时退化到 RPC 风格,如 `/api/accounts/login/start`、`/api/accounts/login/{sid}/commit`、`/api/accounts/login/{sid}`(DELETE = 取消)

---

## Examples

- **典型资源 CRUD**:`orchestrator/main.py` 的 accounts 路由组(`create_account` / `list_accounts` / `delete_account`)是后端 REST 端点的标准范式
- **后台 run 调度**:`Scheduler._execute()` 展示了"DB 状态机 + 信号量 + 兜底清理"的写法
- **PTY ↔ WebSocket 桥**:`login_ws()` 是异步双向流的范式参考
- **正则解析外部数据**:`load_seed_topics()` + `_CAT_RE` / `_ITEM_RE` 是"用正则把 Markdown 当结构化 seed 数据读"的样例
