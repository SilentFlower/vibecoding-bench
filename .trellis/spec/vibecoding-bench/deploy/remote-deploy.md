# Remote Deploy

> AWS EC2 / 自建 VPS 上把 vibecoding-bench 真跑起来。参考实例: <http://186.244.215.29:8080/>。

---

## Scope / Trigger

任何在远程主机起新实例 / 升级 / 改 env / 改端口 时,都按这里的契约执行。

---

## 部署清单(4 件套必齐)

远程主机上必须有这 4 样东西(目录建议 `~/vibecoding-bench/`):

| 文件 | 怎么来 | 为什么不能省 |
|------|--------|-------------|
| `docker-compose.yml`(或 `docker-compose.remote.yml` 配 `-f`) | `git clone` 或单文件 scp | 服务定义,Compose 入口 |
| `.env` | `cp .env.example .env && 编辑` | `HOST_BENCH_DATA` / `BENCH_PORT` / `WEBUI_USER` / `WEBUI_PASS` 等关键配置 |
| `topics.md` | git clone 自带 | 题库,bind mount 到 orchestrator `/repo/topics.md`(未烤进镜像) |
| `webui/`(3 文件) | git clone 自带 | 静态前端,bind mount 到 orchestrator `/webui`(未烤进镜像) |
| `data/`(空目录即可,首次启动 orchestrator 自动 mkdir 子目录) | `mkdir -p data` 或自动 | 持久化:profiles / flows / workspaces / db.sqlite / ca |

> **为什么 topics.md / webui/ 不烤进镜像**:刻意保留 bind mount,让"改题/改前端"可以热替换不重建镜像。代价是部署必须带这两个文件。

最便宜的拿齐法:`git clone https://github.com/SilentFlower/vibecoding-bench.git`,然后 `git pull` 升级。

> 题库维护额外需要 `scripts/sync-topics-db.py`:远程如果不是 git 仓库,同步新版 `topics.md` 时也要同步这个脚本,再按下方 [Topic 题库同步](#topic-题库同步) 写入 SQLite。

---

## Compose 选择:`docker-compose.yml` vs `docker-compose.remote.yml`

repo 里有两个:

| 文件 | image 来源 | 用法 |
|------|-----------|------|
| `docker-compose.yml` | 本地 build(`build: ./orchestrator`) | 本地开发 |
| `docker-compose.remote.yml` | GHCR 匿名 pull(`image: ghcr.io/silentflower/vibebench-*`) | 远程部署 |

远程用法二选一:

1. **显式 `-f`**:`docker compose -f docker-compose.remote.yml --env-file .env up -d`
2. **覆盖默认**:`cp docker-compose.remote.yml docker-compose.yml`,以后 `docker compose up -d` 直跑 —— 但 git pull 时这个本地改动会冲突,处理见下方 [Pull 冲突协议](#pull-冲突协议)

### GHCR 可见性前置条件

GitHub Actions 首次发布后,三个 GHCR package 默认 private。仓库 owner 必须在 package settings 中把 `vibebench-orchestrator`、`vibebench-worker`、`vibebench-sidecar` 分别改为 public。远程部署不保存 GHCR PAT,因此 package 未公开时 `docker compose pull` 会返回 `denied` / `unauthorized`。

package 公开后不能再改回 private。首次上线前要在未登录 GHCR 的主机验证三个镜像均可匿名 pull。

---

## .env 关键字段契约

```bash
# 必填:远程主机上 data/ 目录的【宿主机绝对路径】
# 极易错!不是容器内 /data,也不是相对路径
HOST_BENCH_DATA=/root/vibecoding-bench/data

# 必填:WebUI 监听端口(宿主机侧)
BENCH_PORT=8080

# 强烈建议填(留空 = 任何人可访问)
WEBUI_USER=admin
WEBUI_PASS=<强随机,用 openssl rand -base64 24>

# 可选:跨重启的 session secret(不填则进程启动随机生成,重启注销所有登录)
WEBUI_SESSION_SECRET=<openssl rand -hex 32>

# 可选:锁定镜像 tag(默认 latest)
VIBEBENCH_TAG=158b462

# 可选:普通 run / 批量 run 的兜底默认模型(默认 opus[1m]);
# WebUI「运行」页保存的页面覆盖值优先于这里。
CLAUDE_DEFAULT_MODEL=opus[1m]

# 可选:普通 run / 批量 run 的兜底思考预算(默认 max);
# WebUI「运行」页保存的页面覆盖值优先于这里。
CLAUDE_CODE_EFFORT_LEVEL=max

# 可选:新启动 worker 的 Claude Code CLI 兜底版本(默认 2.1.260);
# WebUI「运行」页保存的页面覆盖值优先于这里。
CLAUDE_CODE_VERSION=2.1.260
```

### HOST_BENCH_DATA 怎么填(最常错)

它**只用于** orchestrator 告诉宿主 docker daemon 给 sibling 容器(worker/sidecar)挂卷时用的路径。daemon 在宿主视角解析路径,容器内的 `/data` 它看不见。

规则:**`docker compose up -d` 在哪个目录跑,该目录下的 `./data` 的绝对路径,就是 `HOST_BENCH_DATA`**。

| 远程部署目录 | `HOST_BENCH_DATA` |
|---|---|
| `/root/vibecoding-bench/` | `/root/vibecoding-bench/data` |
| `/home/ubuntu/vibebench/` | `/home/ubuntu/vibebench/data` |
| `/srv/bench/` | `/srv/bench/data` |

填错的后果:**worker/sidecar 容器会挂载一个不存在的宿主路径,生成空目录,所有 profiles / flows / workspaces 都写入这个孤儿位置,看不到也找不回**。

---

### CLAUDE_DEFAULT_MODEL 兜底默认模型

`CLAUDE_DEFAULT_MODEL` 是普通 run 和批量 run 的兜底默认模型。WebUI「运行」页可以保存运行时页面覆盖值，页面覆盖值保存在 SQLite，优先级高于 `.env`，不需要 recreate orchestrator。页面覆盖值为空时，orchestrator 才回退到 `CLAUDE_DEFAULT_MODEL`。

orchestrator 创建普通 / 批量 worker 时会把当前生效模型作为一次性 `CLAUDE_MODEL_OVERRIDE` 传给 worker，worker 再用 Claude Code CLI 的 `--model` 参数启动本次 TUI。它不写入账号 profile 的 `settings.json`，也不改变抓包 run 的默认模型。

模型值必须匹配字符集 `[A-Za-z0-9._\-\[\]]+`，最长 128 字符。`.env` 非法值会让 orchestrator 启动失败；页面非法值会被保存接口拒绝，避免无效模型静默回退到旧默认。

| 场景 | 行为 |
|------|------|
| 未配置 `CLAUDE_DEFAULT_MODEL` | 普通 / 批量 run 使用 `opus[1m]` |
| 配置 `CLAUDE_DEFAULT_MODEL=sonnet[1m]` | 新启动的普通 / 批量 run 使用 `sonnet[1m]` |
| WebUI 运行页保存 `haiku` | 新启动的普通 / 批量 run 使用 `haiku`，即使 `.env` 仍是 `opus[1m]` |
| WebUI 运行页清空覆盖值 | 新启动的普通 / 批量 run 回退到 `.env` 的 `CLAUDE_DEFAULT_MODEL` |
| 完整 HTTP 抓包 run 未填 `model_override` | 仍沿用抓包现有默认模型，不受页面覆盖值或 `CLAUDE_DEFAULT_MODEL` 影响 |
| 完整 HTTP 抓包 run 填了 `model_override` | 只覆盖当前抓包 run |

修改 WebUI 页面覆盖值不需要重启，只影响后续新启动的普通 / 批量 run。修改 `.env` 的兜底值后必须 recreate orchestrator，已运行中的 run 不受影响：

```bash
docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator
```

---

### CLAUDE_CODE_EFFORT_LEVEL 兜底思考预算

`CLAUDE_CODE_EFFORT_LEVEL` 是普通 run 和批量 run 的兜底思考预算。WebUI「运行」页可以保存运行时页面覆盖值，页面覆盖值保存在 SQLite，优先级高于 `.env`，不需要 recreate orchestrator。页面覆盖值为空时，orchestrator 才回退到 `CLAUDE_CODE_EFFORT_LEVEL`。

允许值固定为 `max`、`xhigh`、`high`、`medium`、`low`。`.env` 非法值会让 orchestrator 启动失败；页面非法值会被保存接口拒绝。

| 场景 | 行为 |
|------|------|
| 未配置 `CLAUDE_CODE_EFFORT_LEVEL` | 普通 / 批量 run 使用 `max` |
| 配置 `CLAUDE_CODE_EFFORT_LEVEL=high` | 页面未覆盖时，新启动的普通 / 批量 run 使用 `high` |
| WebUI 运行页保存 `medium` | 新启动的普通 / 批量 run 使用 `medium`，即使 `.env` 仍是 `max` |
| WebUI 运行页清空覆盖值 | 新启动的普通 / 批量 run 回退到 `.env` 的 `CLAUDE_CODE_EFFORT_LEVEL` |
| 完整 HTTP 抓包 run | 继续使用 `.env` / 抓包现有默认行为，不受页面覆盖值影响 |

修改 WebUI 页面覆盖值不需要重启，只影响后续新启动的普通 / 批量 run。修改 `.env` 的兜底值后必须 recreate orchestrator，已运行中的 run 不受影响。

### CLAUDE_CODE_VERSION 兜底 CLI 版本

`CLAUDE_CODE_VERSION` 是新启动 worker 的 Claude Code CLI 兜底版本。WebUI「运行」页可以保存运行时页面覆盖值，页面覆盖值保存在 SQLite，优先级高于 `.env`，不需要 recreate orchestrator。页面覆盖值为空时，orchestrator 才回退到 `CLAUDE_CODE_VERSION`。

worker 启动时会检查 `claude --version`；如果和当前生效版本不一致，会在容器内执行 `npm install -g @anthropic-ai/claude-code@<version>`，然后再启动登录 / task / quota 流程。usage API 的 `User-Agent` 也使用同一个当前生效版本，避免 CLI 版本与 usage 探测 UA 脱节。

| 场景 | 行为 |
|------|------|
| 未配置 `CLAUDE_CODE_VERSION` | 新 worker 使用 `2.1.260` |
| 配置 `CLAUDE_CODE_VERSION=2.1.169` | 页面未覆盖时，新 worker 使用 `2.1.169` |
| WebUI 运行页保存 `2.1.169` | 新建 task / 批次 / 养号 / 抓包 run 保存 `2.1.169` 快照，登录 / quota worker 启动时使用 `2.1.169`，即使 `.env` 仍是 `2.1.260` |
| WebUI 运行页清空覆盖值 | 新 worker 回退到 `.env` 的 `CLAUDE_CODE_VERSION` |
| 指定不存在的版本 | worker 启动安装失败，run 明确失败，不静默回退 |

修改 WebUI 页面覆盖值不需要重启，只影响后续新启动 worker。修改 `.env` 的兜底值后必须 recreate orchestrator，已运行中的 run 不受影响。

---

## Scenario: cc2api 集成与养号调度环境

### 1. Scope / Trigger

- 远程启用/停用 bench 到 cc2api 的账号同步、managed OAuth 或定时养号时适用。
- 该集成由 orchestrator 主动调用 cc2api 管理 API；worker 不直接持有 cc2api 管理密码。

### 2. Signatures

`.env` 与 Compose 必须支持：

```text
CC2API_BASE_URL=
CC2API_ADMIN_PASSWORD=
CC2API_REQUEST_TIMEOUT_SEC=15
WARMUP_SCHEDULER_TICK_SEC=30
WARMUP_SYNC_RETRY_SEC=900
```

其中 `CC2API_BASE_URL` 是 orchestrator 容器可访问的服务根地址，`CC2API_ADMIN_PASSWORD` 是 cc2api 管理端 Bearer 密码。

### 3. Contracts

- `CC2API_BASE_URL` 或 `CC2API_ADMIN_PASSWORD` 任一为空时，集成功能不可用，但现有未绑定账号、普通 run、抓包和 WebUI 必须继续工作。
- 管理密码只注入 orchestrator；不得传给 worker/sidecar、返回 WebUI、写入 README 示例值、日志、task、workspace 或 transcript。
- Compose 中本地与远程 orchestrator 必须同时透传五个变量，默认超时 15 秒、调度 tick 30 秒、临时同步失败 900 秒重试。
- `CC2API_BASE_URL` 必须按容器网络视角填写。若 cc2api 在同一 Compose 网络，使用服务名和容器端口；若在宿主或外部主机，使用 orchestrator 容器真实可达地址，不能假设 `127.0.0.1` 指向宿主。
- 修改这些环境变量后必须 `up -d --force-recreate orchestrator`；只改 WebUI 不需要 recreate，修改 worker managed 逻辑则还必须重建/发布 worker 镜像。
- 远程恢复后已逾期养号账号最多认领一次；服务停机期间不累计补跑。

### 4. Validation & Error Matrix

| 条件 | 行为 |
|------|------|
| base URL 或管理密码为空 | cc2api 操作返回可见配置错误，普通功能不受影响 |
| orchestrator 容器无法访问 base URL | 养号不建 run，15 分钟后重试 |
| 管理密码错误 | 管理 API 失败；养号保持 `sync_failed` 重试，不得回显密码或 Authorization |
| cc2api 返回永久凭据错误 | 账号养号立即暂停，不按 900 秒循环重试 |
| 只执行 `docker compose restart` | 新环境不会可靠加载；必须 force-recreate |
| 远程重启后 next 已逾期 | 单次认领并置空 next，避免重复补跑 |

### 5. Good/Base/Bad Cases

- Good：orchestrator 与 cc2api 位于同一 Docker 网络，`CC2API_BASE_URL=http://claude-code-gateway:5674`，密码只存在 `.env`，Compose recreate 后账号页可列出脱敏账号。
- Base：五个变量保持默认/空值，bench 继续作为独立服务运行，所有老账号保持未绑定。
- Bad：把管理密码写进前端 JavaScript 或 worker environment；浏览器、容器 inspect 和 workspace 都会泄漏高权限凭据。
- Bad：cc2api 跑在宿主机却填写 `http://127.0.0.1:5674`；orchestrator 容器会访问自己而不是宿主。

### 6. Tests Required

- `docker compose --env-file .env.example config --quiet` 和远程 compose 同命令通过，确认五个变量均被解析。
- 在 orchestrator 容器内请求 `CC2API_BASE_URL/`，确认 DNS/端口可达；不得在输出中打印管理密码。
- 错密码和不可达地址分别验证 502/`sync_failed` 分类，并断言错误中不含密码或 Authorization。
- 重启 orchestrator 后检查已逾期账号只创建一个 warmup run，`warmup_next_run_at` 在认领时置空。
- `docker inspect` worker/sidecar environment，断言不存在 `CC2API_ADMIN_PASSWORD`。

### 7. Wrong vs Correct

#### Wrong

```bash
CC2API_BASE_URL=http://127.0.0.1:5674
CC2API_ADMIN_PASSWORD=plain-text-in-compose-file
docker compose restart orchestrator
```

#### Correct

```bash
# 值保存在 gitignored .env；服务名按实际共享网络填写。
CC2API_BASE_URL=http://claude-code-gateway:5674
CC2API_ADMIN_PASSWORD=<强随机管理密码>
docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator
```

---

## BENCH_PORT 选择

宿主机上 8000 经常被别的服务占(我们实测撞上 `amazonq2api`)。**首次部署先扫端口**:

```bash
for p in 8080 8888 9001 9090 18000; do
  ss -ltn "( sport = :$p )" 2>/dev/null | grep -q LISTEN && echo "$p 占用" || echo "$p 空闲"
done
```

挑一个空闲填进 `.env` 的 `BENCH_PORT`。

**AWS EC2 / 云主机额外步骤**:Security Group / 防火墙必须**单独放行**这个端口。云厂商默认只开 22(SSH)和 80/443。EC2 SG 在 console 加 Inbound Rule:Custom TCP 8080 from 0.0.0.0/0(或限定 IP)。

---

## 完整部署流程

### 首次部署

```bash
# 远程上
cd /root && git clone https://github.com/SilentFlower/vibecoding-bench.git
cd vibecoding-bench

cp .env.example .env
# 编辑 .env:填 HOST_BENCH_DATA / BENCH_PORT / WEBUI_USER / WEBUI_PASS
nano .env

mkdir -p data

# 用 remote.yml 匿名拉取 GHCR 镜像 + 启动
docker compose -f docker-compose.remote.yml --env-file .env pull
docker compose -f docker-compose.remote.yml --env-file .env up -d

# 验证
docker compose -f docker-compose.remote.yml ps
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:${BENCH_PORT:-8080}/api/topics  # 期望 401
curl -s -X POST http://localhost:${BENCH_PORT:-8080}/api/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"user\":\"$WEBUI_USER\",\"pwd\":\"$WEBUI_PASS\"}"  # 期望 {"ok":true,"user":"..."}
```

### 升级(开发推完新版后)

```bash
cd ~/vibecoding-bench
git pull --rebase
docker compose -f docker-compose.remote.yml --env-file .env pull
docker compose -f docker-compose.remote.yml --env-file .env up -d --force-recreate orchestrator
```

> 这里**必须** `--force-recreate`,不能用 `restart`(后者不会用新 image)。

---

## Pull 冲突协议

如果远程为了图方便 `cp docker-compose.remote.yml docker-compose.yml` 并删除了 `.remote.yml`,`git pull` 会失败:

```
error: cannot pull with rebase: You have unstaged changes.
```

干净的处理:

```bash
git checkout -- .       # 还原所有(包括恢复被删的 remote.yml)
rm -f docker-compose.yml.bak  # 旧 build 版本的本地备份(可选删)
git pull --rebase

# 重新 rename(因为 git checkout 恢复了 .yml 是 build 版,不再是 remote)
cp docker-compose.remote.yml docker-compose.yml
```

`.env` 是 gitignored,**不会被 git pull 动**,放心。

---

## Topic 题库同步

### 1. Scope / Trigger

`topics.md` 只在 SQLite `topics` 表为空时 seed。任何已经启动过 orchestrator 的本地或远程实例,更新 `topics.md` 后都必须显式同步 SQLite,否则 WebUI `/api/topics` 仍展示旧题库。

### 2. Signatures

```bash
scripts/sync-topics-db.py \
  --topics topics.md \
  --db data/db.sqlite \
  [--validate-only] \
  [--apply]
```

### 3. Contracts

| 参数 | 类型 | 默认值 | 契约 |
|------|------|--------|------|
| `--topics` | path | `topics.md` | Markdown 题库文件,条目格式必须是 `- [ ] N. **标题**：描述` |
| `--db` | path | `data/db.sqlite` | 已由 orchestrator 初始化过、且存在 `topics` 表的 SQLite 文件 |
| `--validate-only` | flag | false | 只校验 Markdown 解析结果,不访问数据库 |
| `--apply` | flag | false | 实际写入数据库;不传时只输出 dry-run 计划 |

同步策略按 `topics.no` upsert:
- 已存在编号 → `UPDATE title/description/category/enabled/deleted_at/updated_at`,保留原 `id`
- 不存在编号 → `INSERT`
- 不删除额外编号;例如远程本地自定义的 `no > 当前 seed 最大编号` 默认保留
- `--apply` 前自动备份 DB 到同目录 `db.sqlite.bak-YYYYMMDD-HHMMSS`

解析契约(与 `orchestrator/main.py` 的 `load_seed_topics` 对齐):
- 分类标题:`## <中文序号>、<分类名>（N 题）`;`_CAT_RE` 序号段须兼容 **十一及以上**(字符类含 `一二三四五六七八九十百零` 与可选数字),不能只写到「十」
- 条目:`- [ ] N. **标题**：描述`(冒号全半角均可)
- 扩容写法允许**按分类块末尾追加**新编号(文档内 `no` 不必从头到尾递增);例如一类内可出现 `…10 → 301…310 → 11…`
- 校验只要求编号集合完整覆盖 `1..max(no)` 且无重复,不要求文件内顺序等于 `1,2,3,…`

### 4. Validation & Error Matrix

| 条件 | 行为 |
|------|------|
| `topics.md` 解析不到任何题 | 退出并提示“题库为空” |
| 编号重复 | 退出并列出重复编号 |
| 编号集合不完整 | 退出并提示期望 `1..N`、实际条数,以及缺失/多余编号样例(不是“文档顺序不连续”错误) |
| 标题 / 描述 / 分类为空 | 退出并列出缺失编号 |
| DB 文件不存在 | 退出并提示数据库不存在,避免 `sqlite3.connect` 创建空库 |
| DB 未初始化 `topics` 表 | 退出并提示先启动 orchestrator 初始化 schema |
| 不传 `--apply` | 只输出解析数量、计划更新数、计划新增数,不写库 |

### 5. Good / Base / Bad Cases

**Good**:远程更新题库后,先 `scripts/sync-topics-db.py --topics topics.md --db data/db.sqlite` 看计划,确认无误再 `--apply`,最后登录 API 验证 `/api/topics` 数量与 `MAX(no)`。

**Base**:本地开发只想校验 `topics.md`,跑 `scripts/sync-topics-db.py --validate-only`(集合 `1..N` 完整即可;按类追加后顺序非递增也通过)。

**Bad**:只 scp 新 `topics.md` 到远程就以为 WebUI 会变。远程 DB 已有 `topics` 表时 seed 不会再执行,页面仍是旧题库。

### 6. Tests Required

- `scripts/sync-topics-db.py --topics topics.md --validate-only` 断言:解析条数 = `max(no)`,`set(no) == {1..max}`,无空字段。
- 用临时 Markdown 模拟“分类内插入更高编号再接回旧序列”(如 `1,2,10,301,11`),断言 validate 通过;故意缺号 `1,2,4` 时 validate 失败。
- 用临时 SQLite 建 `topics` 表,插入 `no=1` 旧题和 `no=601` 自定义题,跑 dry-run + `--apply`,断言:
  - `no=1` 被更新但 `id` 保留
  - 新增 seed 编号被插入
  - `no=601` 被保留
  - 生成 `.bak-YYYYMMDD-HHMMSS` 备份
- 远程同步后断言 SQLite `enabled` 条数与 seed 目标一致,且 `MAX(no)` 等于 seed 最大编号(当前仓库 seed 为 600)。

### 7. Wrong vs Correct

#### Wrong

```bash
scp topics.md server:/root/vibecoding-bench/topics.md
# 误以为已 seed 过的远程 DB 会自动刷新
```

```python
# 分类正则只到「十」,「十一、…」匹配失败 → 后续题目 category 为空或串类
_CAT_RE = re.compile(r"^##\s+[一二三四五六七八九十]+、(.+?)（")
# validate 要求 numbers == list(range(1,N+1)) 文件顺序,会误杀「按类追加」题库
if numbers != list(range(1, max(numbers) + 1)):
    raise SystemExit("题目编号不连续")
```

#### Correct

```bash
scp topics.md server:/root/vibecoding-bench/topics.md
scp scripts/sync-topics-db.py server:/root/vibecoding-bench/scripts/sync-topics-db.py
ssh server 'cd /root/vibecoding-bench && python3 scripts/sync-topics-db.py --topics topics.md --db data/db.sqlite'
ssh server 'cd /root/vibecoding-bench && python3 scripts/sync-topics-db.py --topics topics.md --db data/db.sqlite --apply'
```

```python
_CAT_RE = re.compile(r"^##\s+[一二三四五六七八九十百零\d]+、(.+?)（")
# 只校验集合覆盖 1..max(no)
if set(numbers) != set(range(1, max(numbers or [0]) + 1)):
    raise SystemExit("题目编号不完整")
```

---

## Validation & Error Matrix

| 现象 | 根因 | 修复 |
|------|------|------|
| `Bind for 0.0.0.0:8000 failed: port is already allocated` | BENCH_PORT 撞别的服务 | 改 .env 的 BENCH_PORT,`up -d` 自动 recreate |
| `HOST_BENCH_DATA must be set` | .env 没填 / `--env-file .env` 漏掉 | 检查 .env 存在 + 加 `--env-file` 或用默认名 `.env` |
| 容器起来但 worker run 时挂载失败 | HOST_BENCH_DATA 填错 / 写了容器内路径 | 改成宿主机绝对路径,值要等于 `pwd` 下 `data` 的全路径 |
| 浏览器访问超时 | 防火墙 / SG 没放行 BENCH_PORT | 云控制台加 Inbound Rule |
| 浏览器看到 401 弹框/JSON | 启用了 auth,正常 | 输入 WEBUI_USER/PASS |
| 升级后浏览器仍旧 UI | 浏览器缓存了旧 webui | Ctrl+F5 强刷 |
| `git pull` 报 unstaged changes | 用户改过 docker-compose.yml | 按 [Pull 冲突协议](#pull-冲突协议) 处理 |
| `docker compose pull` 返回 `denied` / `unauthorized` | GHCR package 仍是 private,或镜像地址拼错 | 把三个 package 设为 public,并核对 `ghcr.io/silentflower/vibebench-*` |
| 设置 `CLAUDE_DEFAULT_MODEL` 后普通 run 仍旧模型 | WebUI 页面覆盖值优先，或只改了 `.env` 但用了 `restart` / 未 recreate | 先在运行页清空覆盖值；若仍不生效，再 `docker compose ... up -d --force-recreate orchestrator` |
| WebUI 保存默认模型失败 | 模型名含非法字符或超过 128 字符 | 改成 `[A-Za-z0-9._\-\[\]]+` 范围内的模型名 |
| 抓包 run 未填 `model_override` 却被全局模型影响 | 说明实现错误：抓包 run 不应收到页面覆盖值或全局 `CLAUDE_MODEL_OVERRIDE` | 检查 `capture_full_http` 分支和 worker 环境变量 |
| 设置 `CLAUDE_CODE_EFFORT_LEVEL` 后普通 run 仍旧思考预算 | WebUI 页面覆盖值优先，或只改了 `.env` 但用了 `restart` / 未 recreate | 先在运行页清空覆盖值；若仍不生效，再 `docker compose ... up -d --force-recreate orchestrator` |
| WebUI 保存思考预算失败 | 值不在允许枚举内 | 改成 `max` / `xhigh` / `high` / `medium` / `low` |
| 抓包 run 被页面思考预算影响 | 说明实现错误：抓包 run 不应读取页面 `claude_effort_level` | 检查 `capture_full_http` 分支和 worker 环境变量 |

---

## Good / Base / Bad Cases

**Good**:首次部署按 4 件套清单 git clone → 填 .env(端口扫一遍 + 强密码) → SG 放行端口 → `up -d` → curl 401 + login 200 → 浏览器登录。

**Base**:HOST_BENCH_DATA 用 `pwd`/data 推算(最少思考成本)。

**Bad**:
- 8000 默认端口不扫直接跑,撞 amazonq2api 失败
- WEBUI_PASS 留空生产部署 → 任何扫到的人都能进
- HOST_BENCH_DATA 填了 `/opt/data`(凭印象写) → 实际目录不存在,所有 profile 写空 → "为什么我登录账号没保留"

---

## Tests Required

部署后断言:

1. `docker ps` 看到 `vibebench-orchestrator Up` + 端口映射对
2. `curl http://localhost:$BENCH_PORT/` 返回 200 + HTML
3. `curl http://localhost:$BENCH_PORT/api/topics` 返回 401(若 auth 开)或 200(若 auth 关)
4. 浏览器从**外网**访问 `http://<公网域名>:$BENCH_PORT/` 看到登录页
5. `docker exec vibebench-orchestrator ls /data/profiles /data/flows /data/workspaces` 三个目录都在(说明 BENCH_DATA 挂卷对了)
6. 跑一次 OAuth 登录账号 → 跑一次 task → `ls data/profiles/<name>/ data/workspaces/<run_id>/` 在**宿主**侧能看到落盘文件(说明 HOST_BENCH_DATA 给 sibling 容器报对了路径)
7. 若改了默认模型，优先在 WebUI「运行」页保存覆盖值后新建普通 run，确认 worker 启动环境含本次 `CLAUDE_MODEL_OVERRIDE`；同时启动未填 `model_override` 的抓包 run，确认它没有继承页面覆盖值或 `.env` 兜底值。
8. 若改了思考预算，优先在 WebUI「运行」页保存覆盖值后新建普通 run，确认 worker 启动环境含本次 `CLAUDE_CODE_EFFORT_LEVEL`；同时启动抓包 run，确认它仍使用 `.env` / 抓包默认值。

---

## Scenario: `cc2api.env` 远程升级与重启

### 1. Scope / Trigger

- Trigger: 用户要求重启远程 `cc2api.env`、升级 `claude-code-gateway` latest 镜像、清空容器日志、确认已有账号升级到新 Claude Code 画像。
- 这是独立于 vibecoding-bench 三镜像的远程服务，路径和镜像以 `.deploy/cc2api.env` 与远程 compose 为准。
- 重启前必须检查服务端口 established 连接数；连接数高时不要直接 recreate。

### 2. Signatures

本地 env 文件：

```text
.deploy/cc2api.env
REMOTE_HOST=<host>
REMOTE_PORT=<ssh port>
REMOTE_USER=<ssh user>
REMOTE_PASS=<secret>
REMOTE_PATH=/root/claude-code-gateway
```

远程 compose 入口：

```bash
cd "$REMOTE_PATH/docker"
docker compose --env-file ../.env pull claude-code-gateway
docker compose --env-file ../.env up -d --force-recreate claude-code-gateway
```

默认容器和端口：

```text
docker-claude-code-gateway-1
SERVER_PORT=5674
image=ghcr.io/silentflower/claude-code-gateway:latest
volume=docker_claude-code-gateway-data:/app/data
```

### 3. Contracts

- 读取 `.deploy/cc2api.env` 时要去掉 CRLF：`tr -d '\r'`，否则 SSH 端口可能变成 `22\r`。
- 只打印非敏感参数；不要输出 `REMOTE_PASS`、token、账号邮箱、Authorization、Cookie。
- 重启前检查连接数：

```bash
PORT="${SERVER_PORT:-5674}"
ss -tan state established "( sport = :$PORT or dport = :$PORT )" | tail -n +2 | wc -l
```

- 低连接窗口再执行重启；当前实践中 `0` established 可直接重启，超过小阈值应暂停并回报用户。
- 清日志要截断 Docker JSON log 文件，而不是删除容器或删除 volume：

```bash
log=$(docker inspect -f '{{.LogPath}}' docker-claude-code-gateway-1)
: > "$log"
```

- 镜像升级必须 `pull` 后 `up -d --force-recreate`；`docker compose restart` 不会加载新镜像。
- 账号版本升级依赖 `cc2api` 启动迁移，部署后必须查 volume 内 DB：

```text
/var/lib/docker/volumes/docker_claude-code-gateway-data/_data/claude-code-gateway.db
```

- SQLite 查询只输出版本分布，不输出账号敏感字段。

### 4. Validation & Error Matrix

| 条件 | 处理 |
|------|------|
| SSH 报 `Bad port '22\r'` | 读取 env 时 `tr -d '\r'` |
| established 连接数偏高 | 不重启；告知用户等待低峰或明确确认 |
| `docker compose pull` 成功但行为没变 | 检查是否漏了 `up -d --force-recreate` |
| 容器内无 `python3` / `sqlite3` | 在宿主机读取 Docker volume 内 SQLite |
| 日志很大 | 先截断旧容器 LogPath，再 recreate |
| 账号版本仍旧 | 查迁移代码和 DB 路径是否为当前容器 volume，不要查错宿主目录 |

### 5. Good/Base/Bad Cases

**Good**：连接数为 0 → 截断旧日志 → `pull latest` → `up -d --force-recreate` → `curl /` 200 → DB 版本分布全为目标版本 → 最近日志无 error。

**Base**：GitHub Actions 已经构建并推送 latest，本地只负责远程 pull/recreate，不再本地 build。

**Bad**：只执行 `docker compose restart`，容器 Up 了但仍跑旧 image id。

**Bad**：删除 Docker volume 来清日志，导致账号和设置数据丢失。

### 6. Tests Required

部署后至少断言：

1. `docker ps --filter name=docker-claude-code-gateway-1` 显示 `Up`。
2. `docker inspect -f '{{.Config.Image}}' docker-claude-code-gateway-1` 是 `ghcr.io/silentflower/claude-code-gateway:latest`。
3. `curl -sS -o /tmp/cc2api_root.out -w '%{http_code}\n' http://127.0.0.1:${SERVER_PORT:-5674}/` 返回 `200`。
4. Docker log 文件被重建后大小处于合理范围，不再保留重启前的大日志。
5. DB 版本分布：

```text
accounts.canonical_env.version      -> 目标版本
accounts.canonical_env.version_base -> 目标版本
accounts.canonical_env.build_time   -> 目标 build_time
```

6. `settings.allowed_claude_code_versions` 包含目标版本上限。
7. `docker logs --tail 200` 不出现 `error|panic|failed|thread.*panicked`。

### 7. Wrong vs Correct

#### Wrong

```bash
cd /root/claude-code-gateway/docker
docker compose restart claude-code-gateway
```

`restart` 只重启旧容器进程，不会使用 GitHub 已推送的新 latest 镜像。

#### Correct

```bash
cd /root/claude-code-gateway/docker
docker compose --env-file ../.env pull claude-code-gateway
docker compose --env-file ../.env up -d --force-recreate claude-code-gateway
```

#### Wrong

```bash
rm -rf /var/lib/docker/volumes/docker_claude-code-gateway-data/_data
```

这是数据 volume，不是日志目录，会删除账号和配置。

#### Correct

```bash
log=$(docker inspect -f '{{.LogPath}}' docker-claude-code-gateway-1)
: > "$log"
```

---

## Scenario: vibecoding-bench 与 cc2api 联合回滚

### 1. Scope / Trigger

- 同一发布批次同时升级 vibecoding-bench worker 的 Claude Code CLI 和 cc2api 的版本画像或允许范围，且需要把两套服务回滚到旧版本时适用。
- 单服务回滚仍按各自部署流程执行；只要旧 cc2api 的允许上限可能低于当前 worker CLI，就必须使用本场景的联合回滚顺序。
- 回滚操作必须由故障处置明确授权，日常验证只能在临时副本中演练，不得为了测试触发生产回滚。

### 2. Signatures

联合回滚依赖以下配置和持久化键：

```text
vibecoding-bench SQLite:
  app_settings.key = 'claude_code_version'

cc2api SQLite:
  settings.key = 'claude_code_version_profile'
  settings.key = 'allowed_claude_code_versions'

部署配置:
  VIBEBENCH_TAG=<旧镜像 tag>
  CLAUDE_CODE_VERSION=<兼容旧网关的 CLI 版本>
```

SQLite 回滚前快照必须使用数据库 API，不能直接复制在线数据库文件：

```bash
sqlite3 "$db_path" ".backup '$snapshot_path'"
sqlite3 "$db_path" ".restore '$rollback_backup'"
```

### 3. Contracts

- 回滚前先确定 `rollback_cli_version`：它必须落在旧 cc2api 的 `allowed_claude_code_versions` 范围内，并优先等于旧 worker 镜像内实际执行 `claude --version` 的结果。
- WebUI 保存的 `app_settings.claude_code_version` 优先于 `.env` 的 `CLAUDE_CODE_VERSION`。恢复旧 vibecoding-bench 数据库后，必须显式把页面覆盖值固定为 `rollback_cli_version`；只修改 `.env` 不能保证旧 worker 使用兼容版本。
- 顺序固定为：确认无活跃 run 和残留 worker/sidecar -> 停止 orchestrator -> 快照当前 bench 数据库与部署配置 -> 恢复旧 bench 数据库并固定 CLI 页面覆盖值 -> 校验旧 Compose、旧 worker 镜像和 CLI 版本但保持 orchestrator 停止 -> 确认 cc2api 连接进入低窗口 -> 停止并快照当前 cc2api 数据库 -> 恢复旧 cc2api 数据库和镜像 -> 校验旧网关版本画像及允许范围 -> 最后启动并校验旧 orchestrator。
- 不得先回滚 cc2api，除非已经证明所有可能连入的 worker CLI 均不高于旧网关允许上限；否则会制造旧网关拒绝新 worker 的版本断层。
- 两套 SQLite 在 `.restore` 前都必须创建当前状态快照，并执行 `PRAGMA integrity_check`。快照目录权限设为 `700`，数据库快照权限设为 `600`，便于回滚失败后恢复到操作前状态。
- 回滚不得删除 Docker volume、bench `data/`、账号 profile 或 workspace。旧镜像、旧 Compose、旧数据库备份任一缺失时停止操作并回报，不得用猜测值继续。
- cc2api 切换期间 orchestrator 必须保持停止；只有旧网关 HTTP 健康、版本画像和允许范围均匹配 `rollback_cli_version` 后才能重新启动。

### 4. Validation & Error Matrix

| 条件 | 处理 |
|------|------|
| 存在活跃 run 或 worker/sidecar | 停止回滚，先等待或按故障流程终止任务并确认容器清零 |
| bench / cc2api 回滚备份完整性失败 | 不执行 `.restore`，保留当前服务状态并修复备份 |
| 恢复后的 WebUI CLI 覆盖值高于旧网关上限 | 保持 orchestrator 停止，将覆盖值固定为 `rollback_cli_version` 后重验 |
| 旧 worker 镜像不存在或 `claude --version` 不匹配 | 不启动 orchestrator，先恢复正确镜像或重新选择兼容版本 |
| cc2api established 连接数不为低窗口 | 暂停网关切换，等待连接释放或取得明确故障处置授权 |
| 旧 cc2api HTTP 健康检查失败 | 不启动 orchestrator，优先恢复刚创建的 cc2api 操作前快照 |
| 旧 cc2api 画像或允许范围不包含回滚 CLI | 不启动 orchestrator，修正旧网关配置或选择范围内 CLI 后重验 |
| 最终 orchestrator HTTP 健康检查失败 | 保留旧网关运行，检查 bench 配置；必要时用 bench 操作前快照恢复 |

### 5. Good/Base/Bad Cases

- Good：先把 bench 恢复到与旧网关兼容的 CLI 页面覆盖值，验证旧 worker 实际版本，再切换旧网关，最后启动 orchestrator；两套数据库都有可校验的操作前快照。
- Base：只回滚 vibecoding-bench，cc2api 允许范围仍覆盖旧 worker CLI；按 bench 单服务流程处理，无需停止网关。
- Bad：先恢复旧 cc2api，再让仍使用新 CLI 的 worker 继续连入；请求会因版本不在旧允许范围而失败。
- Bad：直接 `.restore` 覆盖当前数据库且没有操作前快照；回滚脚本中途失败后无法恢复到开始操作时的状态。

### 6. Tests Required

联合回滚操作单至少完成以下非破坏性验证：

1. 对完整回滚脚本执行 `bash -n`；有 `shellcheck` 时同时通过静态检查。
2. 从两套生产备份各复制一份到临时目录，分别演练 `.backup`、`.restore` 和 `PRAGMA integrity_check`，不得操作在线数据库。
3. 在 bench 临时数据库中写入 `app_settings.claude_code_version=rollback_cli_version`，重新读取并确认生效。
4. 运行旧 worker 镜像的 `claude --version`，断言等于 `rollback_cli_version`。
5. 使用旧 `.env` 和 Compose 执行 `docker compose config`，确认 orchestrator、worker、sidecar 均解析为预期旧镜像。
6. 对操作单做顺序断言：停止 orchestrator 和固定 CLI 必须早于停止 cc2api，启动 orchestrator 必须晚于旧网关全部验证。
7. 生产执行后分别验证 cc2api 与 orchestrator HTTP 状态，并确认新建 worker 的 CLI 版本位于旧网关允许范围内。

### 7. Wrong vs Correct

#### Wrong

```bash
stop_cc2api
sqlite3 "$cc2api_db" ".restore '$old_cc2api_db'"
start_cc2api
rollback_vibebench
```

该顺序会先缩窄网关允许范围，而且覆盖当前数据库前没有可恢复快照。

#### Correct

```bash
assert_no_active_runs_or_workers
stop_orchestrator
snapshot_and_restore_bench
pin_webui_cli_override "$rollback_cli_version"
validate_old_worker_cli

wait_for_cc2api_low_connections
stop_cc2api
snapshot_and_restore_cc2api
start_and_validate_old_cc2api

start_and_validate_old_orchestrator
```

---

## Wrong vs Correct

### ❌ Wrong:HOST_BENCH_DATA 写容器内路径

```bash
HOST_BENCH_DATA=/data        # ✗ 这是容器内路径,daemon 在宿主上找不到
```

worker 起来后 `ls data/profiles` 在宿主侧是空的;`docker exec vibebench-worker-xxx ls /workspace` 也是空的;但容器在跑,看起来一切正常,实际数据全飞了。

### ✅ Correct:HOST_BENCH_DATA 用宿主绝对路径

```bash
HOST_BENCH_DATA=/root/vibecoding-bench/data
```

### ❌ Wrong:升级用 restart

```bash
docker compose pull
docker compose restart   # ✗ 用旧 image 重启进程
```

### ✅ Correct:升级用 force-recreate

```bash
docker compose pull
docker compose up -d --force-recreate orchestrator
```

---

## Common Mistakes

| 反模式 | 现象 | 怎么改 |
|--------|------|--------|
| 端口默认 8000 不扫直接用 | port already allocated | 先 `ss -ltn` 扫一遍再填 .env |
| HOST_BENCH_DATA 凭印象写 | 数据全飞 / 看不到 profile | `pwd`/data 推算 |
| 远程没 mkdir data | 首次启动 orchestrator 创不出子目录 | 显式 `mkdir -p data` |
| `--env-file .env` 漏 | 必填 env 报错 | 用默认 `.env` 名,或显式 `--env-file` |
| WEBUI_PASS 留空生产 | 公开端口任何人能进 | 强密码,`openssl rand -base64 24` |
| WEBUI_PASS = WEBUI_USER 或同 SSH 密码 | 字典攻击秒破 | 各自独立强随机 |
| 升级后浏览器仍旧 UI | 浏览器缓存 | Ctrl+F5 |
| SG 漏放端口 | 浏览器连不上但 curl 本机能通 | 云控制台加 Inbound Rule |
