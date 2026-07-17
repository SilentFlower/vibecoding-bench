# Brief — 增加定时养号功能

## Goal

- 让现有 bench 账号绑定对应的 cc2api OAuth 账号，按随机小时区间持续运行真实题库任务；保留 bench 现有 profile 和设备环境，并由 cc2api 单独负责 AT/RT 刷新。

## Scope

- 在现有 `accounts` 增加一对一 cc2api 绑定、养号开关、随机间隔、下次触发、最近状态和认证失败计数，旧账号默认关闭。
- cc2api 新增管理员凭据解析接口，复用账号级刷新锁，支持最小有效期和一次强制刷新，不改变现有 Gateway 选择行为。
- orchestrator 新增 cc2api 客户端、单账号安全创建/关联、profile 凭据原子同步和脱敏账号列表。
- 绑定账号的任意 bench run 启动前先同步 cc2api 凭据；worker 进入 managed OAuth 模式，运行副本不持有 RT、不本地刷新、不反向覆盖 profile。
- worker 检测 401 时通过 workspace 标记请求 orchestrator 让 cc2api 强制解析凭据，更新后最多重试一次。
- 新增 `WarmupScheduler`，按每账号最小/最大间隔随机调度；停机逾期最多补一次，同账号 warmup 不并发。
- 从有效题库随机抽题，按账号排除最近 20 道；创建真实 `[warmup]` task 和 `run_kind=warmup` run，复用现有 Scheduler、sidecar、worker、SSE 和详情链路。
- Accounts 页面增加单账号同步、养号配置、立即运行、恢复和解绑；Runs 页面增加 warmup 标识。
- 临时 cc2api 故障 15 分钟后重试；永久账号/凭据错误或连续 3 次 `auth_failed` 自动暂停。
- 更新本地/远程 compose、`.env.example`、README 和必要项目规范，并补充 bench 与 cc2api 的定向测试。

## Non-Goals

- 不做批量同步 accounts。
- 不做 cron、每周规则、固定整点或多套时间表。
- 不增加账号级模型、思考预算、Claude Code 版本或 timeout。
- 不在 prompt 中加入任何账号画像、邮箱、UUID 或凭据。
- 不从 bench 删除、停用或覆盖 cc2api 账号的非凭据业务配置。

## Key Context

- bench backend 是单文件 `orchestrator/main.py`，使用裸 SQLite、`_ensure_column` 和 `_db_lock`，外部 HTTP IO 不能在数据库锁内执行。
- bench frontend 是 `webui/index.html`、`app.js`、`style.css` 三个零构建静态文件，沿用 template/render/modal、全局 state 和 `escapeHTML`。
- 真实运行继续由现有 `Scheduler` 的每账号 Semaphore 管理；`runs.run_kind` 已存在，可新增 `warmup` 值。
- profile 的身份与环境继续来自现有 `.claude.json`、`settings.json`、代理、时区和账号指纹；cc2api 仅成为绑定账号的凭据刷新所有者。
- managed OAuth 适用于所有已绑定账号的 task、capture、continue 和额度链路，不只适用于自动 warmup；绑定期间 bench 重授权需先解绑。
- 单账号同步优先按 `account_uuid` 匹配，bench 缺 UUID 才按邮箱匹配；UUID 冲突返回 409，已有 cc2api 账号不得被 bench 旧 RT 覆盖。
- 新建 cc2api 账号时从 bench profile 提取 OAuth 身份和凭据，由 cc2api 自行生成 `device_id` 与 canonical 画像。
- cc2api 管理密码只存在 orchestrator 环境；浏览器、日志、测试 fixture 和规划文档不得出现真实 token、邮箱或 UUID 映射。
- 主要风险是 RT 双边轮换、旧 run 覆盖新凭据、调度重复认领和 run 期间解绑后的旧回调；设计分别用单一所有权、managed worker、原子认领和绑定条件更新约束。

## Acceptance

- 一个 bench 账号可与一个 cc2api 活跃 OAuth 账号一对一绑定并启用养号，重复绑定被后端拒绝，解绑保留历史和 profile。
- cc2api 是唯一 refresh 方；bench 后台、worker 和 401 恢复路径不会产生第二条本地 refresh 链路。
- 绑定账号的 run 启动前同步最新凭据；同步失败不启动 worker；401 只触发一次 cc2api 强制解析和一次重试。
- 随机间隔可跨重启恢复，停机只补一次，同账号不会并行出现两个 warmup run。
- 随机题目只来自有效题库，最近 20 道按账号去重，prompt 不包含额外账号信息。
- warmup 进入现有真实运行链路并可在 Runs 页面识别、查看、停止和追踪终态。
- 临时故障有限重试，永久凭据错误和连续认证失败会暂停并展示原因。
- 单账号同步可安全创建或关联 cc2api 账号，不按名称误匹配、不用旧 RT 覆盖已有账号。
- 普通任务、批次、抓包、继续对话、额度查询和账号删除行为不回归。

## Next Step

- 用户确认本 brief 与 `prd.md`、`design.md`、`implement.md` 后，运行 `task.py start`；进入执行阶段的第一步必须是 `trellis-route(implement)`，不能直接编辑代码。
