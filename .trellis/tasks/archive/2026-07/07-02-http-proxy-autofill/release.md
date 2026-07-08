# Release Operations

## Conclusion
Release operations exist.

## Evidence Checked
- task.json
- prd.md
- design.md
- implement.md
- implement.jsonl
- check.jsonl
- git commits / changed files（`git show --stat 3fa32dc`）
- last_push_snapshot.notes（"发布需重建/redeploy orchestrator + sidecar"）

## Drift Check
Missing release.md. 本任务此前未写 release.md，本次首次补写。

## SQL Changes
- `accounts` 表新增 nullable 列 `upstream_proxy_scheme TEXT DEFAULT 'socks5'`。
  - 来源：`design.md` 数据模型段、`implement.md` Step 1、`git show 3fa32dc` 中 `orchestrator/main.py`。
- 升级方式：`init_db()` 通过 `_ensure_column(conn, "accounts", "upstream_proxy_scheme", "TEXT DEFAULT 'socks5'")` 幂等补列，兼容已有 `data/db.sqlite`，无需手写迁移脚本。
  - 来源：`design.md` 兼容与迁移段、`implement.md` Step 1。
- 风险：`implement.md` 风险点明确"账号表新增列必须保证旧 DB 幂等升级，否则远程实例启动会失败"。远程实例重启时由 `init_db()` 自动补列，无需人工 SQL 操作，但需确认 orchestrator 镜像已更新到含此 `_ensure_column` 的版本后再重启。

## Configuration Changes
- 新增 sidecar 环境变量 `UPSTREAM_PROXY_SCHEME`，orchestrator 在任务运行、继续对话、额度查询、OAuth 刷新、内嵌登录五处生成 sidecar 环境时传入；同时保留旧 `UPSTREAM_SOCKS5_*` 以降低改动面。
  - 来源：`design.md` sidecar 合约段、`implement.md` Step 2、`git show 3fa32dc` 中 `orchestrator/main.py`。
- `images/sidecar/start.sh` 读取 `UPSTREAM_PROXY_SCHEME` 并按 `http` / `socks5` / `socks5h` 归一化生成 proxychains `ProxyList` 类型；`https` 与未知值 fatal。
  - 来源：`implement.md` Step 3、`git show 3fa32dc` 中 `images/sidecar/start.sh`。
- 无新增 secrets / feature flags / 外部端点。

## Batch / Deployment Scripts / Data Repair
- 需要重建并 redeploy `orchestrator` 与 `sidecar` 镜像，使新的 schema 补列、环境变量和 proxychains 协议分支生效。
  - 来源：`last_push_snapshot.notes`、`design.md` 回滚段、`implement.md` 验证命令段（`docker compose up -d --build orchestrator sidecar worker`）。
- worker 镜像无代码改动但与 sidecar 共享网络命名空间，按 `docker compose up -d --build` 一并重建更稳妥。
- 无一次性数据修复命令、无定时任务触发、无后台 job rerun。

## External Systems / Dependent Platforms
None。本任务的所有发布对象都是本仓库的远程部署实例（orchestrator / sidecar / worker 容器），不涉及本仓库之外的第三方平台或外部协调方。

## Release Order
1. 先构建并推送含本次改动的 `orchestrator` 与 `sidecar`（及 `worker`）镜像。
2. 在远程部署实例拉取新镜像并 `docker compose up -d --build`，让 `init_db()` 自动给旧 `data/db.sqlite` 补 `upstream_proxy_scheme` 列。
3. 确认 orchestrator 启动日志无 schema 报错、sidecar 启动日志按账号协议生成 proxychains 配置后，再让账号实际跑 HTTP 代理验证。

## Rollback Notes
- 代码回滚：回退 `images/sidecar/start.sh` 与 `orchestrator/main.py` 的 schema/DTO/sidecar env 改动，恢复固定 SOCKS5 行为。
- 数据库：新增列是兼容性变更，回滚代码后旧代码会忽略 `upstream_proxy_scheme` 列，不需要删列、不丢数据。
- 前端：回退 `webui/{index.html,app.js,style.css}` 表单与粘贴解析改动。
- 回滚后已用 HTTP 协议保存的账号会回退为按 SOCKS5 运行，需提示用户这些账号需重新配置代理。

## Post-release Verification
- 按 `prd.md` Acceptance Criteria 验证：粘贴 `http://user:pass@proxy.example.com:8080` 自动填入协议/host/port/user/pass；粘贴 `socks5h://proxy.example.com` 默认端口 1080；重授权表单回填协议；HTTP 代理账号在登录 session、任务 run、继续对话、额度查询、OAuth 刷新时 sidecar 生成 `http` 出站配置；老账号仍按 SOCKS5 运行；粘贴 `https://proxy.example.com:443` 不被当成可用协议。
- 静态校验：`python3 -m py_compile orchestrator/main.py`、`bash -n images/sidecar/start.sh`、`node --check webui/app.js`、`git diff --check`。
- 远程实例：重启后确认 `accounts` 表已含 `upstream_proxy_scheme` 列且旧行默认 `socks5`；用 HTTP 代理账号实际发起一次任务 run，检查 sidecar 出站走 HTTP CONNECT。
