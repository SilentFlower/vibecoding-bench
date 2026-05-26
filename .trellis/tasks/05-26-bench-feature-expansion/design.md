# Bench 功能扩展设计草案

## 技术边界

* 后端继续集中在 `orchestrator/main.py`，保持裸 `sqlite3`、Docker SDK、线程调度模式。
* 前端继续集中在 `webui/index.html`、`webui/app.js`、`webui/style.css`，保持零构建。
* worker / sidecar 镜像继续负责 Claude Code、SOCKS5、MITM、workspace 隔离。

## 数据模型方向

### Topics

当前 topics 从 `topics.md` 解析，无法可靠 CRUD。已确认把 topics 迁移到 SQLite 表：

* `topics(id/no/title/description/category/enabled/created_at/updated_at)`
* 首次启动从 `topics.md` seed；后续以 DB 为准，不再写回 Markdown。
* 删除建议 MVP 做软删，避免已有 run / task 引用断链。

### Tasks / Batch

当前 tasks 是“单账号 + 单 topic + repeat”。用户目标更接近“批次调度”：

* `task_batches(id/account_id/name/concurrency, interval_min_sec, interval_max_sec, status, created_at)`
* `task_batch_items(id/batch_id/topic_id/prompt/status/next_run_at/created_at)`
* `runs` 继续表示单次 Claude 执行，新增 `batch_id` / `topic_id` 可选字段。

MVP 可少建表：保留 `tasks` 兼容旧数据，新增 batch 表驱动新 UI。

### Runs

新增状态建议：

* `stopping`：用户请求停止，后台正在清容器。
* `stopped`：用户停止完成。
* `deleted`：task/run 软删后默认隐藏，保留磁盘产物。

停止需要通过 runs 表中的 `worker_container`、`sidecar_container` 调用现有 cleanup 逻辑。

删除采用软删：

* task/batch 删除只更新状态或 `deleted_at`，默认列表过滤。
* run 删除只更新状态或 `deleted_at`，默认列表和详情过滤。
* workspace、flow、transcript 保留，便于排查和手动恢复。

继续对话需要复用 run 的 `.claude-home/projects/-workspace/*.jsonl`。已确认 MVP 走交互 TUI：

* 在同一 workspace 的 `.claude-home` 副本上启动 `claude --resume <session_id>`。
* 启动前从账号 profile 白名单覆盖最新认证/配置文件到 run 的 `.claude-home`：`.credentials.json`、`.claude.json`、`settings.json`。这样历史 run 只提供会话上下文，不提供可能已经过期的 OAuth token。
* 覆盖时必须保留 run workspace 内的 `projects/` 会话历史和产物目录，不能用账号 profile 全量替换 `.claude-home`。
* 后端提供继续会话 API + WebSocket PTY 桥，前端打开 xterm modal。
* 用户手动输入后续对话；不在 MVP 中做追加 prompt 自动继续跑。
* 继续会话结束后沿用 task 模式的白名单回写，把 Claude Code 刷新的 `.credentials.json`、`.claude.json`、`settings.json` 同步回账号 profile。

## 账号凭据同步方向

当前 task 模式在运行开始时把账号 profile 复制到 run 的 `.claude-home`，运行结束只回写 `.claude.json` 和 `settings.json`，不会持久化 Claude Code 自动刷新的 `.credentials.json`。这会让后续 run 继续使用旧 token。

调整方向：

* 增加统一的 profile 白名单同步函数，覆盖文件限制为 `.credentials.json`、`.claude.json`、`settings.json`。
* task 结束、auth status 失败前、startup gate 失败前都调用同一同步逻辑，尽量保存 Claude Code 已经刷新过的凭据。
* worker 入口需要设置统一退出收口（例如 shell `trap`），保证成功、失败、异常退出、timeout 分支都会尝试白名单回写；用户停止容器前后端也应先尽量调用同一回写命令。
* 继续对话启动前从账号 profile 同步到 run `.claude-home`，继续对话结束后再从 run `.claude-home` 同步回账号 profile。
* 明确禁止同步 `sessions/`、`projects/`、`telemetry/`、`backups/` 等目录到账户 profile，避免不同 run 互相污染。

## Accounts 额度查询方向

推荐用临时 worker + sidecar 跑轻量查询，不复用正在运行的 task 容器：

1. 根据账号配置启动 `bench-quota-sidecar-*` 和 `bench-quota-worker-*`。
2. 复制 profile 到 worker 的 `/home/node/.claude`。
3. 写入临时 `statusLine` 配置：脚本把 stdin JSON 原样保存到 `/workspace/.bench-quota-status.json`。
4. 启动交互 Claude，触发一次极短消息或 `/status`。
5. 读取 `rate_limits` 字段，清理容器。

风险：

* 如果没有首次 API 响应，`rate_limits` 可能缺失。
* “7d Sonnet 单独额度”没有公开字段，MVP 不阻塞；前端显示“未返回/暂不支持”。

## Stats 修复方向

远端成功 run 有 `.flow`，但没有 `stats.jsonl`。候选原因：

* `recorder.py` 未被 mitmdump 正确加载。
* 目标 host/path 没匹配到 `anthropic.com`。
* 响应体是压缩/流式格式，`get_text()` 或 usage 解析失败，但按当前代码即使 usage 为空也应写请求记录，所以更像 addon 未执行或 host 未匹配。

实现时需要用 mitmproxy 工具或脚本读取 `.flow` 验证真实 host/path，再修 recorder。

## UI 设计方向

* Accounts：在操作列增加 `额度` 按钮，点击后行内 loading，结果用小型 modal 或行内展开展示。
* Topics：保留卡片网格和过滤；增加 `new topic` 按钮；卡片点击变成详情/编辑，不再跳 task 创建。
* Tasks：改成“账号 selector + topic 多选列表 + 并发/随机区间间隔配置 + 启动批次”的工作台；保留删除入口。
* Runs：操作列增加 `停止`、`继续`、`删除`，根据状态显示可用按钮；继续对话打开 xterm modal。

## Rollout / Rollback

* SQLite schema 需要幂等迁移；现有无 migration 系统，需在 `init_db()` 后补 `ALTER TABLE` 检查。
* 保留旧 `/api/tasks` 和旧 tasks 表读取一段时间，避免已有 runs 详情断掉。
* topics 首次 seed 要幂等，避免每次启动重复导入。
* 软删字段上线后，旧数据默认 `deleted_at IS NULL`，不影响现有列表。
