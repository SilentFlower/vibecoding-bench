# 技术设计

## 目标与边界

按用户已确认的被动采集、到期自动恢复、全部模型入口保护，实现一个账号共用的额度状态。自动路径不调用 usage API，不创建查询 worker，不额外发送模型探测。沿用 SQLite、线程与既有容器链路，不引入外部队列或新服务。

本任务保持为一个实现任务：响应采集、运行等待、恢复及页面显示必须共同交付，单独完成其中一层不能消除 10-2 的错误成功与持续投放。

## 规划时的代码依据

以下行号是规划基线定位；实现后的稳定入口名称及验证证据见 verification.md。

- `images/sidecar/recorder.py:394`、`:417` 只有请求阶段与响应正文完成后的统计；新增响应头观察必须独立于完整抓包开关。
- `orchestrator/main.py:2601` 的 `Runner.start_run()` 已持久化 workspace、Claude home 和 flows。恢复沿用这些目录，不复制账号内的其它历史项目。
- `Scheduler._execute():4714` 取得 semaphore 后，在 owner lock 内重读账号并创建 worker；这是启动前最终判定位置。当前 exit 0 判成功早于 worker 错误提示，必须改成明确错误优先。
- 批次在 `:4433` 顺序投放，`:4661` 判断是否结束；新增等待状态必须同时覆盖投放、计数及收口。
- 养号认领、终态和重启处理位于 `:4932`、`:5032`、`:5350`，等待不得当成普通终态安排下一道题。
- `Runner.start_continue():2911` 当前只有抓包 continue 挂载 flows；普通 continue 也需要持久化被动观察。`continue_run_ws():7651` 单独启动 `claude --resume` 并透传 PTY 输入，不能只改普通执行器。
- OAuth 身份字段已有 `accountUuid`、`organizationUuid` 和 `claudeAiOauth.accessToken`，解析位于 `:812` 起的 profile 读取代码。额度身份不能仅按账号名称归属。
- 参考 cc2api 的 `extract_passive_usage()`、`extract_rejected_passive_usage_windows()` 和 `merge_usage_observation()`，不改 cc2api 子模块。

## 数据流与运行内阻断

```text
用户已有任务或继续对话
  -> 启动前读取账号被动额度状态
  -> worker -> sidecar -> 账号既有代理 -> Anthropic
  -> sidecar 收到响应头，追加被动观察
  -> orchestrator 消费观察，持久化并发布账号阻断状态
  -> 任务等待；全部已耗尽窗口到期后认领一次正常恢复执行
```

sidecar 的 `responseheaders()` 只提取额度头白名单、HTTP 状态、flow 标识、观察时间及内部来源标识，追加独立的 `passive-quota.jsonl`，不把整组响应头加入普通 stats。`response()` 可补充有限、脱敏的额度拒绝分类；不保存任意错误正文作为账号状态。

请求归属同时校验目标 Anthropic API、模型请求路径以及当前 worker OAuth AT 的哈希。哈希来自本地凭据，随既有刷新链路更新，并保留本次执行仍可能使用的旧 AT 哈希；不把原始 AT、RT、请求鉴权头传入观察日志。由生成项目发起的 dummy API key 测试或其它身份请求不更新该账号额度。

sidecar 在明确窗口拒绝时立即设置本次执行的本地阻断；之后的模型请求在 MITM 内返回可识别的本地等待响应，不再发到上游。账号共享状态通过只读目录挂载供所有 sidecar 检查，因此其它并发执行及 continue 同样受到保护。仅拦模型请求，不阻断 OAuth、DNS、依赖下载或普通网页。

worker 只读挂载本次执行的额度控制目录，在主循环最前面检查暂停信号；一旦因额度拒绝或下一条模型请求被额度门禁拦截，先保存会话、transcript 与状态，再退出额度等待分支。该分支优先于认证重试、API stall 恢复和 timeout wrap-up，不注入任何额外提示。已被上游接受的流允许正常完成；成功响应携带 100% 不等于这一条已接受请求失败，只阻止后续请求。

窗口解析、合并和判定以 `orchestrator/quota_protocol.py` 为真实源，`scripts/sync-quota-protocol.py` 将字节一致副本同步到 sidecar 的独立 Docker 构建上下文，测试检查一致性。recorder 负责即时拒绝与本地拦截，main.py 的 QuotaGuard 负责唯一持久化事实来源及调度；不重构无关模块。

观察日志优先落盘，再原子发布暂停信号。控制对象附带归一化窗口作为日志写入故障的补证，保留真实 reset；明确 account_on_hold 同时保留有限错误码，不能转成自动恢复。门禁文件不可读时终止当前执行。继续对话在后台扫描和每次输入前都检查控制信号。

## 持久化与内部契约

以下为本任务新增契约。

| 存储 | 用途 |
| --- | --- |
| `account_quota_states` 新表，主键 `account_id` | 保存身份标识、归一化窗口 JSON、观察时间、未知恢复时间的耗尽证据、恢复认领来源及状态版本 |
| `quota_observation_cursors` 新表，主键为观察来源 | 保存已消费 JSONL 偏移和文件身份，跨重启防止旧样本重复覆盖新状态 |
| `runs.quota_attempt`，默认 0 | 区分同一 run 的自动恢复执行，拒绝旧 worker 回调与旧暂停信号 |
| `runs.quota_resume_at`，可空 | 下一次正常执行机会；未知恢复时间为空并保持等待 |
| `runs.execution_model`，可空 | 首次取得执行机会时、额度判定前固化有效模型；初次等待也保留该快照，自动恢复保持模型 |
| `runs.quota_identity`，可空 | 固化原执行身份；身份变化时停止旧等待工作，避免自动迁移到新账号 |
| 现有 status 字段新增 `quota_wait` 值 | 用于 run、batch item、batch 和养号最近状态，区别用户主动暂停与终态 |

JSON 内每个窗口保存百分比、UTC reset、允许/拒绝证据及该窗口的观察时间；缺失窗口不被新样本清空。内部身份包括 bench ID、cc2api 绑定 ID 与 profile 账号/组织身份，不能包含 token。绑定或重新登录切换身份时旧观察失效，旧等待工作不得自动在新身份上执行；`quota_wait` 也属于所有权切换的活跃工作，需先停止。

窗口解析明确区分比例与百分比，接受有限非负数；reset 支持秒、毫秒、RFC3339，按观察时间限制 5h/7d 的合理范围。拒绝状态独立于完整用量对象：即使利用率缺失，明确 `status=rejected` 仍形成阻断证据。`status=allowed` 优先于单纯高位猜测；缺少状态时才参考 surpassed-threshold 和耗尽利用率。

成功/允许样本按 cc2api 的跨周期规则合并，真实拒绝窗口保留拒绝事实。同周期较晚样本按窗口自身的观察时间更新；时间相同优先保留拒绝。旧来源、缓存窗口与旧观察不得清空较新的拒绝证据。展示可以保留模型专属窗口，但本轮通用 5h/7d 门禁不会因仅 `7d_oi` 耗尽而误停其它模型。

共享状态落在 `BENCH_DATA/quota/<account_id>`，采用临时文件加原子替换；子容器挂载使用 `HOST_BENCH_DATA`，只读挂载目录而不是单个被替换文件。控制目录为 `BENCH_DATA/quota-controls/<run_id>/<source_hash>`，位于可写 workspace 外；sidecar 可写、worker 只读。每次执行使用独立来源标识，旧信号不会影响恢复后的执行。

新增表使用 `CREATE TABLE IF NOT EXISTS`，新增 run 列使用 `_ensure_column()` 幂等补齐。所有写入与认领在 `_db_lock` 的短事务内完成；Docker、HTTP、profile I/O 和等待在锁外。owner lock -> profile lock 顺序不变，不为额度查询增加凭据刷新。

## 耗尽与恢复判定

通用窗口满足明确拒绝，或合法的当前周期利用率达到 100% 时阻止后续正式执行。cc2api 的 97% 撞墙分类阈值不直接变成 bench 的提前停跑设置。

所有已确认耗尽且尚未到期的窗口均参加等待判定，恢复机会取它们的最晚 reset，并尊重更晚的可信 retry-after。不能按固定窗口优先级选择较早时间。短暂速率 429 和单请求 credits 拒绝不能伪装成通用额度耗尽。

确认耗尽但缺少可信恢复时间时：优先使用同身份、同窗口已有未来 reset，仍不能确定则保持等待并展示原因；不猜测 `now + 5h/7d`，不自动发探测。明确 hit-your-limit 合成错误且窗口未知时保存内部 unknown 窗口；已有真实耗尽窗口时不追加未知阻断。可以从原本显式手动查询结果或后续合法被动证据更新等待条件，但自动调度不调用手动接口，页面区分手动与被动来源。

reset 到期不将缓存写成“已恢复”或 0%。后台仅从数据库判断到期并认领一个已有的正常任务/仍在线的 continue 作为首次恢复执行；收到该执行的真实允许响应后先合并再判定，未出现新的耗尽条件才释放其它等待工作。若仍拒绝则重新记录等待；若网络、容器或认证失败则释放认领并按原失败规则收口，不能让所有任务并发冲上游。认领以条件 UPDATE 防重入，等待期间不占账号 semaphore 或 owner/profile lock。

| 当前状态 | 事件 | 结果 |
| --- | --- | --- |
| 无记录 | 用户已有正常任务 | 正常运行获得首次观察；页面显示未知 |
| queued | 启动前发现耗尽 | `quota_wait`，不创建 worker |
| running | 明确额度拒绝 | 保存当前执行记录，清理容器，进入 `quota_wait` |
| quota_wait | 较早窗口到期但其它窗口未到期 | 继续等待 |
| quota_wait | 全部耗尽窗口到期，自动认领成功 | 原 run 回 queued/running，执行次数递增 |
| 恢复执行 | 再次额度拒绝 | 重新等待，不跳题、不连续重试 |
| 任意等待 | 用户停止/暂停/关闭、账号删除或停用 | 用户操作优先，不自动重启 |

普通 `rate_limit` 合成 API 错误不会判成功，但只有真实额度证据才能进入自动额度恢复；未知 API 错误为 failed，认证与 `account_on_hold` 为认证失败，超时维持既有超时语义。封号、invalid_grant 固化账号门禁、暂停批次并关闭养号，不按额度到期自动恢复。

## 原题、批次及养号恢复

quota_wait 是非终态；`ended_at` 不作为完成证据，批次 done_count 不包含它，`_TERMINAL_RUN_STATUSES` 不包含它。停止/删除/改绑的活跃状态判断必须覆盖 quota_wait，避免等待 run 在后台复活。等待、恢复和终态写入须校验当前 status、执行代次、父 task/batch 的可用状态及 stop_requested_at；不能用无条件 UPDATE 覆盖刚发生的用户停止。

保留同一个 run ID、task ID、batch item、prompt、workspace、Claude session、CLI/effort/权限和模型快照。自动恢复与用户“再次运行”是两个不同入口；后者仍创建新 run 并按既有规则获取当前配置。

已发生请求的执行记录按 quota_attempt 归档轻量状态与 transcript，flows 追加并带来源标识，不抹去过去的耗尽证据。找到同 run 的 Claude session 时采用 `--resume`，从原题和原 workspace 继续；未产生会话时重用原 prompt 正常启动。恢复启动须忽略上一执行遗留的最终 assistant / synthetic 错误，完成检测按新执行起始点判断，避免一启动就判旧成功或旧失败。首轮记录主项目会话文件基线，查找恢复会话时排除账号复制旧历史和子代理 JSONL。原 timeout 的有效运行预算不因等待耗尽，到期恢复获得原配置的执行预算，等待本身不算超时。

批次进入 quota_wait 后停止新增 item 投放，调度线程释放等待并结束，不一直阻塞在 `_wait_all_runs_finished()`。恢复先执行原来未完成的 run，完成后才继续后续 item；已经投放的其它 run 保持原有记录与顺序，不重新生成 prompt/配置。更新 `_finish_batch_when_done()`、状态统计和 pause/resume API，人工 paused 不变成自动恢复。

养号保留 warmup_enabled，最近状态为 quota_wait；到期认领不得选择新题或创建重复 task/run，优先恢复原 warmup run。尚未创建养号 run 就发现账号耗尽时只设置账号等待信息，到期再走正常选题。额度等待不累计认证失败，不在普通终态 helper 中安排下一题。用户关闭养号时取消等待工作，后续回调保持 off。

## 继续对话与抓包

continue start 可登记一个不占 worker 的等待会话，返回原 session_id 与 WS 地址，页面显示等待原因；不能在同步 HTTP 路由等待到 reset。已有在线会话在检测到耗尽时停止当前 Claude exec、保存会话并清理执行容器，保留等待会话与 WS；先断开旧 PTY，不只禁用前端按钮。

服务端拒绝等待期的文本、二进制输入，客户端停止输入发送并显示状态；resize、close 仍可处理。全部到期后通过共同认领机制自动重建执行容器并恢复同一个 Claude session，替换 PTY 桥并通知客户端可输入；不自动重放等待期输入或补发 /retry。WS 断开、用户关闭、会话删除都取消恢复，重建与取消竞态由会话锁和 generation 复查收口。

普通 continue 也挂载独立 flows 观察目录；抓包 continue 仍追加原 capture flows。continue 的错误与等待状态不改写原来已经终态的 run 成功记录，而在 continue 会话及账号状态展示。

抓包运行走共同 run 等待与恢复逻辑，保留 capture_mode、model_override、permission_mode 与 CLI/effort。抓包 run 与抓包续聊自动恢复共同检查活跃抓包及最近启动时间；官方抓包矩阵的串行、120 秒间隔及异常后至少 15 分钟暂停仍成立；本功能不自动启动下一矩阵样本、不自动换号，额度自动恢复不能缩短这些限制。

## 后台消费、重启与 UI

新增小型额度后台守护，挂入 lifespan 启停：运行期间消费 JSONL 与控制状态，启动前和 worker 收口前额外同步消费一次，确保批次换题前已保存拒绝证据。消费偏移和窗口状态同事务提交；半行留待下轮，轮换/截断按文件身份处理，不回放已消费的旧额度。

启动恢复顺序先加载额度状态、消费遗留来源、读取原身份、原代次的独立控制补证，核对并收口本任务关联的旧执行容器，再处理可恢复等待工作；容器清理后再次消费观察与控制补证。新后台与 `WarmupScheduler._recover_stale_runs()` 共享一次恢复事实，不能把 quota_wait 改成普通 failed 并另排新题。崩溃发生在观察、DB 更新、容器清理、queued 认领之间的场景均须可重入；禁止恢复前旧 worker 仍在发送请求。只恢复本功能的等待工作，不扩张为所有历史失败任务重跑。

账号 API 追加被动额度摘要；run/batch 返回 quota_wait 原因与恢复机会，保持现有 JSON 形状及字段兼容。沿用已有页面刷新、SSE 和 modal，在账号、批次、run、养号和继续对话上展示“额度等待”、耗尽窗口、观察时间与预计恢复时间；未知或过期数据明确标注，不展示为实时查询。手动 quota 按钮保留为显式动作，不因渲染/定时器触发查询。继续对话 WS 追加 JSON 状态事件，保持既有二进制终端输出格式。

## 交付与回滚

需配套 orchestrator、worker、sidecar 三个镜像及 WebUI；本轮仅本地实现和验证，发布/生产部署遵守独立 SOP。混用旧 worker/sidecar 无法获得完整保护，因此交付记录必须明确三件套版本。

数据库升级只新增表/列，保留历史数据；回滚旧代码后额度门禁失效且旧代码不识别 quota_wait，不能将等待记录批量改成 active 继续跑。回滚前先停止调度和本功能等待工作、保存 SQLite 与配置快照，配套回滚三个镜像；不得删除 profile、workspace、flows 或数据卷。

## 验证重点与限制

用脱敏 10-2 事件、构造响应头、临时 SQLite 和 Docker/PTY mock 验证全链路，不为测试耗尽生产账号额度。覆盖窗口缺失、跨周期、乱序、两窗口不同 reset、启动竞态、运行中连续 retry、等待取消、恢复再次拒绝、continue 输入、抓包快照和各崩溃点。

首次真实耗尽及已在途请求无法完全提前避免；被动采集不预测单次模型请求成本。响应缺少可信 reset 时自动恢复只能等待更多有效证据，页面须说明。该保护不能证明封号原因，也不能保证账号不会被风控。
