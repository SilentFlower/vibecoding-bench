# 增加定时养号功能

## Goal

让现有 vibecoding-bench 账号可绑定对应的 cc2api OAuth 账号，并按随机小时区间持续运行真实题库任务。养号 run 必须复用账号现有 Claude Code profile、代理和设备环境，同时由 cc2api 统一持有并刷新 AT/RT，避免双边刷新导致凭据失效。

## Background

- vibecoding-bench 已有账号 profile、题库、任务、run 状态、随机批次调度和真实 Claude Code worker 执行链路。
- bench 账号以 `data/profiles/<name>` 保存 `.credentials.json`、`.claude.json` 和 `settings.json`，并按账号名派生稳定代理环境指纹。
- cc2api 账号独立存储 OAuth 凭据、账号身份和网关画像；当前 bench 尚未绑定或调用 cc2api 管理 API。
- cc2api 现有 `prime_poller` 只发送最小上游预热请求，不会随机抽取题库或生成 bench task/run，不能替代本功能。
- Claude Code 与 bench 后台刷新器都可能轮换 RT。若 bench 与 cc2api 同时刷新同一账号，服务端可能废弃其中一条 RT，不能只靠本地更新时间解决。

## Requirements

### 1. 现有账号启用养号

- 复用现有 bench `accounts` 和 profile，不创建第二套账号或 Claude Code 环境。
- 养号是账号级可选能力，默认关闭；未启用账号保持现有手动任务和运行行为。
- 启用后继续沿用账号现有 `.claude.json`、`settings.json`、代理、时区和稳定设备环境。
- 每个 bench 账号最多绑定一个 cc2api 账号，每个 cc2api 账号也只能绑定一个 bench 账号。
- 绑定必须由用户显式选择 cc2api 活跃 OAuth 账号；不得按名称或邮箱静默绑定。
- 解绑立即停止未来养号调度，但不得删除本地 profile、历史 task、run 或 workspace。

### 2. cc2api 单一凭据所有权

- cc2api 是绑定账号 AT/RT 的唯一刷新所有者。
- bench 只同步 cc2api 返回的最新 AT、RT 和过期时间，不使用 RT 主动调用 OAuth refresh endpoint。
- bench 后台 OAuth 刷新器必须跳过所有已绑定 cc2api 的账号，无论养号开关是否开启。
- 绑定账号启动任意 bench run 前，必须先由 cc2api 在账号锁内确保 AT 具有足够有效期，再同步到本地 profile。
- 绑定账号的 worker 运行副本不得使用 RT 自行刷新，也不得把运行副本凭据反向覆盖 profile。
- 运行中检测到 401 时，worker 请求 orchestrator 让 cc2api 强制解析一次新凭据；同步后最多重试一次。
- cc2api 不可用或凭据同步失败时，不得使用可能过期的本地凭据启动养号 run，也不得降级成本地刷新。
- 凭据文件写入前必须校验 JSON 和 `claudeAiOauth`，并通过临时文件加 `rename` 原子替换。
- `invalid_grant`、账号不存在、账号禁用或凭据结构无效必须停止自动尝试并暂停养号。
- API、日志、任务标题、prompt、workspace 和 transcript 均不得输出 AT、RT 或其他敏感账号字段。

### 3. 周期调度

- 每个养号账号配置最小和最大间隔小时，最大值不得小于最小值。
- 每次养号 run 到达终态后，在配置区间内随机计算并持久化下一次触发时间。
- 首次启用后先安排下一次随机触发；需要立即执行时使用“立即运行”。
- 服务停机期间不累计补跑；恢复后已逾期账号最多补触发一次。
- 同一账号已有养号 run 处于 queued、running 或 stopping 时，不得创建第二个养号 run。
- cc2api 临时网络失败时不创建 task/run，15 分钟后重试凭据同步，且不消耗正常随机间隔。

### 4. 题库与真实运行

- 到期后只从启用且未删除的题目中随机抽取一项。
- 每个账号排除最近 20 个养号 run 使用的题目，不允许连续两次抽中同一道题。
- 可选题不足时允许缩小或重置去重窗口，但必须仍从当前有效题库中选择。
- prompt 只使用现有 `build_topic_prompt` 生成的题库标准内容，不拼接账号名称、邮箱、UUID、AT/RT 或其他账号信息。
- 养号任务必须创建真实 task 和 `run_kind=warmup` 的 run，并复用现有 Scheduler、sidecar、worker、SSE 和运行详情链路。
- 养号 run 复用运行页当前全局默认模型、思考预算、Claude Code 版本和 `1800` 秒超时。
- 养号 run 继续受现有账号并发信号量约束，不得绕过手动任务或批次任务的并发限制。

### 5. 状态与失败处理

- 账号页展示 cc2api 绑定、养号开关、随机间隔、下次触发、最近 run 状态和暂停原因。
- 账号页提供“同步到 cc2api”“配置养号”“立即运行”“恢复养号”和“解绑”操作。
- 真实 run 普通失败或超时时不立即重跑，按下一次随机间隔继续。
- 连续 3 次养号 run 进入 `auth_failed` 时自动暂停，并保留可见原因。
- cc2api 账号不存在、禁用、UUID 冲突、`invalid_grant` 或凭据结构无效时立即自动暂停。
- Runs 页面继续显示现有状态，并为 `run_kind=warmup` 增加养号标识。

### 6. 单账号同步到 cc2api

- 账号页只提供单账号“同步到 cc2api”，本次不提供批量同步。
- 同步读取 bench profile：
  - `.credentials.json.claudeAiOauth` 提供 AT、RT、`expiresAt` 和订阅类型。
  - `.claude.json.oauthAccount` 提供 `emailAddress`、`accountUuid` 和 `organizationUuid`。
  - bench account 提供名称和上游代理配置。
- 匹配现有 cc2api 账号时优先使用 `account_uuid`；bench 缺少 UUID 时才允许按邮箱匹配，禁止按名称匹配。
- 未匹配时创建新的 cc2api OAuth 账号，并由 cc2api 自行生成 `device_id` 和 canonical 画像。
- 匹配到已有账号时只建立绑定，并立即用 cc2api 当前凭据更新 bench profile，不得用 bench 中可能较旧的 RT 覆盖 cc2api。
- 邮箱相同但 UUID 冲突时停止同步并提示人工处理。
- 同步成功后自动保存绑定 ID，但不自动开启养号。

## Acceptance Criteria

- [ ] 用户可以把一个现有 bench 账号与一个 cc2api 活跃 OAuth 账号一对一绑定并启用养号。
- [ ] 重复绑定同一个 cc2api 账号会被后端拒绝；解绑不删除任何历史数据或 profile。
- [ ] 绑定账号的 AT/RT 只由 cc2api 刷新，bench 后台、worker 和 401 恢复路径不会产生第二条本地 refresh 链路。
- [ ] 任意绑定账号 run 启动前都会同步 cc2api 最新凭据；同步失败时不会启动 worker。
- [ ] 运行中 401 只触发一次 cc2api 强制凭据解析和一次重试，失败后进入 `auth_failed`。
- [ ] 养号间隔落在配置范围内，可跨重启恢复；停机恢复最多补一次，同账号不会并行启动两个养号 run。
- [ ] 随机题目只来自有效题库，最近 20 道按账号去重，题目不足时仍可安全选择。
- [ ] 养号 task/run 进入现有真实运行链路，Runs 页面可识别养号类型并查看结果。
- [ ] 养号 prompt、日志和工作区不包含额外账号字段或凭据。
- [ ] cc2api 临时故障按 15 分钟重试；账号或凭据永久异常、连续 3 次认证失败会自动暂停。
- [ ] 用户可以手动立即运行并在问题修复后恢复养号。
- [ ] 单账号同步可安全创建或关联 cc2api 账号；UUID 冲突会拒绝，已有账号不会被 bench 旧 RT 覆盖。
- [ ] 养号功能不破坏现有手动任务、批次、抓包、继续对话、额度查询和账号删除语义。

## Out Of Scope

- 批量同步 bench accounts 到 cc2api。
- cron、每周规则、固定整点或每天多套时间表。
- 账号级模型、思考预算、Claude Code 版本或 timeout 覆盖。
- 在 prompt 中加入账号画像或个人信息。
- 删除、停用或修改 cc2api 账号的非凭据业务配置。

## Notes

- 本任务是一个跨 bench 后端、原生 WebUI、worker shell 和 cc2api Rust API 的内聚工作流，不拆分父子任务。
- 所有测试 fixture 和规划文档只能使用脱敏占位值，不得提交真实邮箱、UUID、AT 或 RT。
