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
| `docker-compose.remote.yml` | DockerHub pull(`image: huajiwuyan/vibebench-*`) | 远程部署 |

远程用法二选一:

1. **显式 `-f`**:`docker compose -f docker-compose.remote.yml --env-file .env up -d`
2. **覆盖默认**:`cp docker-compose.remote.yml docker-compose.yml`,以后 `docker compose up -d` 直跑 —— 但 git pull 时这个本地改动会冲突,处理见下方 [Pull 冲突协议](#pull-冲突协议)

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

# 用 remote.yml 拉 DockerHub 镜像 + 启动
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
- 不删除额外编号;例如远程本地自定义的 `no > 200` 默认保留
- `--apply` 前自动备份 DB 到同目录 `db.sqlite.bak-YYYYMMDD-HHMMSS`

### 4. Validation & Error Matrix

| 条件 | 行为 |
|------|------|
| `topics.md` 解析不到任何题 | 退出并提示“题库为空” |
| 编号重复 | 退出并列出重复编号 |
| 编号不连续 | 退出并提示期望范围和实际首尾 |
| 标题 / 描述 / 分类为空 | 退出并列出缺失编号 |
| DB 文件不存在 | 退出并提示数据库不存在,避免 `sqlite3.connect` 创建空库 |
| DB 未初始化 `topics` 表 | 退出并提示先启动 orchestrator 初始化 schema |
| 不传 `--apply` | 只输出解析数量、计划更新数、计划新增数,不写库 |

### 5. Good / Base / Bad Cases

**Good**:远程更新题库后,先 `scripts/sync-topics-db.py --topics topics.md --db data/db.sqlite` 看计划,确认无误再 `--apply`,最后登录 API 验证 `/api/topics` 数量。

**Base**:本地开发只想校验 `topics.md`,跑 `scripts/sync-topics-db.py --validate-only`。

**Bad**:只 scp 新 `topics.md` 到远程就以为 WebUI 会变。远程 DB 已有 `topics` 表时 seed 不会再执行,页面仍是旧题库。

### 6. Tests Required

- `scripts/sync-topics-db.py --topics topics.md --validate-only` 断言题目数量和编号连续。
- 用临时 SQLite 建 `topics` 表,插入 `no=1` 旧题和 `no=201` 自定义题,跑 dry-run + `--apply`,断言:
  - `no=1` 被更新但 `id` 保留
  - `no=200` 被插入
  - `no=201` 被保留
  - 生成 `.bak-YYYYMMDD-HHMMSS` 备份
- 远程同步后登录 API,断言 `/api/topics` 至少返回 200 条且包含 1-200。

### 7. Wrong vs Correct

#### Wrong

```bash
scp topics.md server:/root/vibecoding-bench/topics.md
# 误以为已 seed 过的远程 DB 会自动刷新
```

#### Correct

```bash
scp topics.md server:/root/vibecoding-bench/topics.md
scp scripts/sync-topics-db.py server:/root/vibecoding-bench/scripts/sync-topics-db.py
ssh server 'cd /root/vibecoding-bench && scripts/sync-topics-db.py --topics topics.md --db data/db.sqlite'
ssh server 'cd /root/vibecoding-bench && scripts/sync-topics-db.py --topics topics.md --db data/db.sqlite --apply'
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
