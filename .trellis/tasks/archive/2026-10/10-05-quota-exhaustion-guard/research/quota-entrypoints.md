# 额度保护入口与已有契约

本文件记录代码事实与已确认的需求边界，具体技术方案见 design.md。

## 已有额度链路

用户已要求新保护机制完全被动。下面记录的主动查询只用于说明现有代码，不能接入自动启动、等待或恢复路径。

- `_format_quota_result(raw)` 返回 `ok`、`five_hour`、`seven_day`、模型周窗口和 `raw`。窗口仅校验为 dict，`ok` 目前只要求至少存在一个通用窗口，不能直接当作严格的额度可用判定。见 `orchestrator/main.py:2337`、`:2399`。
- 页面 `openQuotaDetail()` 优先取窗口的 `used_percentage`，其次取 `utilization`，恢复时间来自 `resets_at`，以北京时间展示。见 `webui/app.js:373`。
- 已绑定账号的查询接口在 `_oauth_owner_lock` 内重读账号，先后同步 cc2api 凭据，中间调用 `Cc2ApiClient.refresh_usage()`。后者 POST 到 `/admin/accounts/{account_id}/usage`。见 `orchestrator/main.py:792`、`:6278`。
- 未绑定账号调用 `Runner.query_quota(account)`，创建临时 sidecar 和 login worker，经账号代理读取 `/api/oauth/usage`，最后清理容器与临时目录。该路径会持有 profile lock，并可能刷新及回写凭据。见 `orchestrator/main.py:3038`、`:3132`。
- 未绑定主动查询要求代理配置；被动机制不依赖这一查询入口，不能为首次任务主动补查。无观察记录时正常任务可取得首次样本，页面仍须显示额度未知。
- 现有 usage probe 对拿到的 HTTP 错误不重试，连接异常最多重试五次；遇到 HTTP 429 返回 status 和 retry_after_sec。额度保护不能把查询限流误解为账号模型额度耗尽。

## 调度入口

- `Scheduler._execute_batch()` 按 batch item 顺序投放，在前一批运行终态后等待随机间隔。错误成功会将批次推进到下一题。见 `orchestrator/main.py:4433`。
- `Scheduler._execute()` 取得账号 semaphore 后，在 owner lock 内重读账号并同步绑定凭据，再写 running 并创建 worker。额度最终检查应覆盖真正启动边界，不能只放在 task 创建 API。见 `orchestrator/main.py:4714`。
- `WarmupScheduler.trigger_account()` 认领到期账号、同步凭据后生成题目并创建 queued run；queued run 又进入共同执行器。见 `orchestrator/main.py:4932`。
- `WarmupScheduler.handle_run_terminal()` 只处理 run_kind=warmup；普通失败继续调度，认证失败按既有规则累计或立即暂停。新增额度结果需要明确独立等待语义，不能套用认证失败计数。见 `orchestrator/main.py:5032`。
- 用户已确认继续对话与抓包共同纳入保护。继续对话走独立 runner 和交互 websocket，需覆盖会话启动与新的输入。见 `orchestrator/main.py:7600` 起相关代码；抓包 run 经 Scheduler 启动，使用共同门禁。
- 范围核对：`continue_run_start()` 在 owner lock 内同步凭据后调用 `ContinueManager.start()`；`continue_run_ws()` 另外执行 `claude --resume`，浏览器输入直接写 PTY，未经过普通任务队列。因此只保护 `Scheduler._execute()` 不能保护继续对话；若纳入范围，需明确其额度拦截与交互输入处理，不能把用户输入当自动任务随意重放。
- 抓包已有独立规范要求：429 等异常后矩阵至少停 15 分钟、串行、相邻运行至少 120 秒。新的被动自动恢复不能取消该既有约束；其人工显式查询操作不属于自动采集链路。见 `.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md:112`。

## 完成判定缺陷

- `classify_claude_completion()` 将最后一条非空 assistant 消息作为完成候选，只把合成的 request timed out 转成 API 超时结果，旧认证文本之外的合成错误最终返回 complete。
- 10-2 的错误事件是 `isApiErrorMessage=true`、`message.model=<synthetic>`、`error=rate_limit`；暂停事件为 `error=account_on_hold`。只检查文本或者只识别 HTTP 401 不足以覆盖这些事件。
- 运行结果、batch item 和养号状态需要保持同一事实来源；不能只改页面显示。

## 必须保留的项目契约

- `.trellis/spec/vibecoding-bench/backend/database-guidelines.md`：写 SQLite 使用 `_db_lock`；网络和容器操作不得包在长数据库写事务内。
- 绑定账号只有 cc2api 能刷新 RT；不得为了额度查询降级成本地刷新。锁顺序固定为 owner lock -> profile lock，不能重入同一普通 Lock。
- `.trellis/spec/vibecoding-bench/backend/topic-prompt-contract.md`：最终 prompt 只生成一次；暂停、恢复和重试必须复用原 prompt、CLI 版本与 effort 快照。
- `.trellis/spec/vibecoding-bench/deploy/remote-deploy.md`：管理密码只注入 orchestrator；worker 改动需要 worker 镜像交付，生产交付独立遵守部署流程。

## cc2api 被动实现与可复用规则

- `cc2api/src/service/gateway.rs:6254` 的 `extract_passive_usage()` 从响应头提取窗口：`anthropic-ratelimit-unified-5h-*` 对应 `five_hour`，`7d-*` 对应 `seven_day`，`7d_oi-*` 对应 `seven_day_fable`。
- 完整窗口要求 `utilization` 与 `reset` 同时有效。比例乘以 100 后保存为百分比；拒绝非有限、负值和明显超出窗口尺度的 reset；支持秒、毫秒以及 RFC3339 时间。缺头不主动补查。
- `extract_rejected_passive_usage_windows()` 优先使用窗口 `status`：`rejected` 为拒绝，`allowed` 排除拒绝；没有明确状态时使用 `surpassed-threshold=true/正数` 或 `utilization >= 1.0` 兼容旧头。同一 429 并不意味着所有窗口均耗尽。
- Gateway 成功路径与 429 路径分别提交允许观察和按窗口拒绝观察，接入 `AccountService.update_passive_usage()`。该方法只合并持久化，不发 API 请求。
- `merge_usage_observation()` 只覆盖当前观察包含的窗口。旧 reset 已到期、新 reset 已推进且窗口未被拒绝时，旧、新值仍处于高位可视为周期残留：保存新 reset，首个新周期样本归零，后续同周期样本恢复真实值；真实拒绝窗口保留高位。
- 通用窗口 429 分类使用当前响应明确拒绝的窗口，没有当前用量时才回退缓存；恢复时间结合窗口 reset 和 retry-after，不能把真实 7d 冷却截断为 5h。
- cc2api 当前通用 429 分类阈值为 97%，这是其撞墙判断细节；用户本轮要求“用完后不要继续跑”，不据此擅自加入 bench 的可配置提前停跑阈值。
- cc2api 仍保留管理员手动刷新和显式开启的轮询入口；本轮 bench 自动保护不接入这些主动查询入口，也不修改 cc2api。

## bench 被动采集的接入边界

- `images/sidecar/recorder.py:417` 当前 `response()` 仅保存请求统计、状态码与 token usage，不保存普通响应中的额度头；完整 HTTP 捕获只在显式抓包模式开启。额度被动采集需要独立于完整抓包开关。
- 目前没有 `responseheaders()` hook。额度观察宜在收到响应头时产生，不能等长 SSE 完成才能保护其他排队任务；响应正文可补充额度拒绝分类，但不能把任意 429 当额度耗尽。
- orchestrator 可访问每个 run 的 `flows_dir`，现有统计文件位于该目录。被动观察的消费与持久化须在下一题投放前完成，并覆盖运行中收到拒绝后的保护；worker 与 sidecar 的控制信号传递需要在 design.md 中明确，不能假设 worker 已挂载 flow 目录。
- 保护应覆盖启动前读取缓存和运行中处理拒绝两处。仅采集头而不修复 worker 合成错误判定，仍会发生 10-2 的跳题。

## 后续设计需要验证的边界

- 使用百分比单位、有限数值校验、窗口缺失与真正没有该窗口的区别。
- 用户已确认被动 reset 全部到期后自动继续原题及养号；到期不等于主动确认额度恢复。首个真实任务若再次被拒绝，需要重新进入等待，不能循环探测；主动暂停、停止、关闭养号均优先于自动恢复。
- 两个窗口都耗尽时，要检查所有耗尽窗口；不能只选一个固定优先级而提前恢复。
- 没有首次观察时只能靠正常任务取得数据；已确认耗尽但缺少可信恢复时间时不能凭空设定 5h/7d，也不能主动查询来填充。
- 被动观察按账号和实际凭据绑定归属，需防止旧 run、改绑或重建账号把额度状态写到错误身份；顺序消费与去重不应丢失真实拒绝样本。
- 等待期间释放长时间占有的 owner lock、profile lock 和运行槽，确保取消、改绑和其他账号不被阻塞。
- 已在运行的任务不能保证永不收到第一次额度 429；目标是正确识别、停止继续请求并保护后续投放，不能承诺上游感知零延迟。

## 已有验证基础

- `orchestrator/test_main.py` 中 `ScheduledWarmupTests` 已包含绑定、RT 所有权、queued 后重同步、认证暂停以及用户关闭养号的覆盖。
- 可以扩展现有容器 mock 与 worker shell/Python 片段测试，复现真实合成错误；无需为验收耗尽生产账号额度。
- 产品策略已确定，实施需覆盖被动观察解析与合并、统一启动拦截、缺失恢复时间、恢复、重启和批次不跳题，并断言自动路径不调用主动额度接口。
