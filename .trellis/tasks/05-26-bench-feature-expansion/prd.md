# Bench 功能扩展

## Goal

把当前 bench 从“账号登录 + 题库创建单个 task + 查看 runs”扩展成更适合批量 vibe-coding 的工作台：账号可查询 Claude Code 额度，题库可维护，任务按账号批量调度，运行记录可停止、删除、继续对话，并修复 token / 请求统计为空的问题。整体 UI/UX 保持现有 Terminal Lab 风格，不引入前端构建系统。

## Background / Known Context

* 远程部署环境已记录到本地忽略文件 `.deploy/ai-havefun.env`，用于后续直接连接部署；该文件不进 git。
* 用户希望 accounts 增加 Claude 额度查询：5h 额度、7d 额度、7d Sonnet 额度；查询必须经过该账号配置的 SOCKS5。
* 已确认额度查询 MVP 先做稳定版：展示官方可稳定获取的 5h / 7d 字段；7d Sonnet 单独额度先显示“未返回/暂不支持”，后续再做实验解析。
* 用户希望 topics 支持添加、删除；点击 topic 后只关注 topic 本身，不再直接创建 tasks，因为 tasks 后续要大改。
* 已确认 topics 改为 SQLite 为主数据源，`topics.md` 仅用于首次 seed。
* 用户希望 tasks 改成账号维度：选定一个账号，再选一批 topic，支持全选/多选，批量同时跑 2 个，并按动态变化的间隔投放。
* 已确认动态间隔 MVP 用随机区间：用户配置最小/最大间隔，每次投放前随机取值。
* 用户补充 tasks 也要有删除按钮。
* 用户希望 runs 增加删除、停止、继续对话按钮。
* 已确认 runs 的“继续对话”优先做交互 TUI：点击继续后打开网页终端，用户手动和 Claude 对话。
* 已确认删除策略：task/run 做软删并从默认列表隐藏，保留 workspace、flow、transcript 等磁盘产物用于排查。
* 已确认账号凭据需要白名单同步：task/继续对话运行中如果 Claude Code 刷新 `.credentials.json`，应回写账号 profile；继续对话启动前也应把账号 profile 的最新 `.credentials.json` 覆盖到 run 的 `.claude-home`，避免很久以前的 run 因旧 token 失效。
* 已确认凭据回写必须覆盖失败/异常路径：任务失败、Claude 异常退出、startup/auth gate、timeout、用户停止前，只要运行时已经刷新过 `.credentials.json`，都应尽量回写账号 profile。
* 当前统计面板已有输入 token、输出 token、请求数，但远端成功 run `e699fbd31483` 的 `data/flows/auto/3/e699fbd31483/` 只有 `.flow` 文件，没有 `stats.jsonl`，所以 API 返回 0。
* 当前 topics 来自 `topics.md` 的 Markdown 解析，是只读数据源，不在 SQLite 里。
* 当前 tasks 表是持久任务定义：`topic_no/title/prompt/account_id/timeout_sec/repeat_n`，一次 task 只绑定一个账号。
* 当前 runs 表记录单次运行，只有 queued/running/success/failed/timeout 状态读取，没有删除、停止、继续对话 API。
* 当前 worker 每次 run 创建独立 workspace：`data/workspaces/<run_id>/`；Claude 会话文件在 `.claude-home/projects/-workspace/*.jsonl`。

## Research Notes

* Claude Code 官方状态栏 JSON 暴露 `rate_limits.five_hour.used_percentage`、`rate_limits.five_hour.resets_at`、`rate_limits.seven_day.used_percentage`、`rate_limits.seven_day.resets_at`；这些字段仅 Pro/Max 订阅用户在首次 API 响应后出现。
* Claude Code 官方帮助说明 Pro/Max 的 Claude 与 Claude Code 共用使用限制，并建议用 `/status` 监控剩余额度。
* 当前公开 status line schema 没看到单独的“7d Sonnet 额度”字段；本任务不把该字段作为阻塞项。

## Requirements

### Accounts

* 在 accounts 列表每个账号增加“查询额度”按钮。
* 查询额度必须复用该账号的 SOCKS5、CA、非 root Claude 环境，不能从 orchestrator 宿主直连。
* 查询结果至少展示 5h 使用百分比、5h reset 时间、7d 使用百分比、7d reset 时间。
* 7d Sonnet 单独额度在 MVP 中显示为“未返回/暂不支持”，不阻塞额度查询功能上线。
* 如果 Claude Code 未返回 rate limit 字段，应明确显示“暂无数据/需一次 API 响应后可用”，不能误报 0。
* 查询失败时保留可诊断错误，例如未登录、SOCKS5 不通、Claude Code 无 rate limit 字段。
* task 模式和继续对话模式中，Claude Code 如刷新认证凭据，必须把 `.credentials.json` 白名单回写到账号 profile，避免后续 run 继续使用过期 token。
* 凭据回写不能只依赖成功路径；失败、异常、timeout、停止等收口路径都必须尽量执行白名单回写。
* 凭据同步只能覆盖认证/配置白名单文件，不能把 run 的 `sessions/`、`telemetry/`、`backups/` 等运行态目录回写到账户 profile。

### Topics

* topics 页面支持新增 topic，字段至少包括编号、标题、描述、分类。
* topics 页面支持删除 topic，并有确认提示。
* 点击 topic 不再打开创建 task 弹窗；应进入 topic 查看/编辑语义，或者只选中/展开 topic 详情。
* 题库数据持久化在 SQLite；首次启动从 `topics.md` seed，后续 CRUD 以 DB 为准。

### Tasks

* tasks 页面改成按账号维度调度：先选账号，再选择一批 topic。
* topic 选择支持全选、单选/多选。
* 同一个批次支持配置最多并发数，MVP 默认和上限均为 2。
* 同一个批次支持配置随机区间间隔，用于控制下一批/下一次 run 的投放时间。
* 调度应保留现有每账号并发保护，不能让一个账号无限并发挤爆 Claude Code 额度。
* tasks 列表/批次列表需要有删除按钮，并有确认提示；删除为软删，默认列表隐藏但历史数据保留。

### Runs

* runs 列表增加删除按钮；删除为软删，默认列表和详情 API 不再返回，磁盘产物保留。
* queued/running run 支持停止；停止后容器应被清理，DB 状态可区分用户停止。
* completed run 支持继续对话；继续对话应基于该 run 的 Claude session 打开交互 TUI，而不是新开完全空白会话。
* 继续对话启动前应把该账号 profile 的最新 `.credentials.json`、`.claude.json`、`settings.json` 覆盖到 run 的 `.claude-home`，只复用 run 的会话历史和 workspace 产物，不能继续使用很久以前 workspace 里的旧 token。
* 继续对话结束后如 Claude Code 刷新了 `.credentials.json`，应按同一白名单策略回写账号 profile。
* runs detail 继续展示 transcript、产物文件和 token / 请求统计。
* 修复 stats 为空问题：成功 run 应能聚合请求数和 token；如果 token 无法解析，也至少应显示请求数和错误计数。

### UI / UX

* 保持现有 Terminal Lab 风格、暗/明主题兼容。
* 继续使用原生 `webui/index.html`、`webui/app.js`、`webui/style.css`，不引入 npm、框架或构建系统。
* 列表操作按钮、批量选择、详情/编辑弹窗都沿用当前表格、modal、pill、terminal 风格。

## Acceptance Criteria

* [ ] accounts 列表能对配置 SOCKS5 的账号发起额度查询，查询容器出站确认经过该账号 SOCKS5。
* [ ] 额度查询结果能显示 5h / 7d 使用百分比和 reset 时间；缺字段时显示明确空态。
* [ ] topics 可新增、删除，并在服务重启后仍保留。
* [ ] 点击 topic 不再创建 task；旧的 topic→task modal 被移除或替换为 topic 详情/编辑。
* [ ] tasks 可按账号选择多个 topic，并以最多 2 并发提交 runs。
* [ ] tasks 可软删，删除后默认列表不再显示，相关历史 runs 和磁盘产物保留。
* [ ] 随机区间间隔可配置，并能在 runs 创建时间上体现。
* [ ] running run 可停止，停止后容器不存在，DB 状态不再是 running。
* [ ] run 可软删，默认列表和详情 API 不再返回被删除项，workspace/flow/transcript 保留。
* [ ] completed run 可打开继续对话 TUI，并复用对应 Claude session 上下文。
* [ ] completed run 继续对话启动前使用账号 profile 的最新认证凭据，旧 run workspace 中的过期 `.credentials.json` 不会导致恢复失败。
* [ ] task/继续对话运行后如 Claude Code 刷新 `.credentials.json`，账号 profile 中的认证凭据会被白名单更新。
* [ ] task 失败、异常退出、timeout 或用户停止时，如运行时 `.credentials.json` 已刷新，账号 profile 仍会尽量获得白名单回写。
* [ ] 成功 run 的 stats 不再固定为 0；至少请求数正确，能解析 token 时 token 正确。
* [ ] UI 在窄屏下无明显重叠；暗/明主题可用。
* [ ] `python3 -m py_compile orchestrator/main.py`、`node --check webui/app.js`、相关 shell `bash -n` 通过。

## Open Questions

* 无。

## Out of Scope

* 不更换前端技术栈。
* 不引入 Celery/RQ 等外部任务队列。
* 不在本任务里实现多用户权限模型。
* 不在 MVP 中实现 7d Sonnet 单独额度；未公开数据后续只能作为实验性解析。
* 不在 MVP 中做磁盘产物自动清理；软删后的 workspace/flow/transcript 保留。

## Research References

* [`research/claude-code-rate-limits.md`](research/claude-code-rate-limits.md) — Claude Code 可通过 status line JSON 获取 5h/7d rate limit 字段，但 Sonnet 单独周额度未见公开字段。
