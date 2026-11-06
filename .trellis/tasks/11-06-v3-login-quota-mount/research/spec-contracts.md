# 本任务规范摘录

以下摘录仅供任务上下文注入；权威合同仍以原规范为准。实施前须核对源文件及对应标题，源摘要变化时重新读取。

## .trellis/spec/vibecoding-bench/backend/account-runtime-v3.md

源 SHA256：`be0c4240562f6d6b39db02c1e618c48fdd156fa1ee8f562c9ee00c32ed845a00`。

### 原文第 435—468 行

### 1. Scope / Trigger

- 修改新账号登录开始、草稿列表/恢复/重登/删除、首次提交或宕机恢复时适用。已有正式账号的重授权及历史软删除保持原契约；终端交互见 [登录终端生命周期](../frontend/hook-guidelines.md#scenario-v3-登录终端重连与授权链接)。

### 2. Signatures

```text
GET    /api/accounts/login-drafts
POST   /api/accounts/login-drafts/{environment_id}/resume
POST   /api/accounts/login-drafts/{environment_id}/restart
POST   /api/accounts/login-drafts/{environment_id}/reconcile
DELETE /api/accounts/login-drafts/{environment_id}?generation=<页面代次>
LoginDraftActionIn: {generation: string}；extra=forbid
AccountRuntime.recover_login(sid: str, account: dict, version: str, home: str)
  -> tuple[dict, object]
AccountRuntime.login_terminal_alive(session) -> bool
bench/login-drafts/<32位小写hex环境ID>.json
```

### 3. Contracts

- 草稿使用 `account_environments.account_id=NULL`，首次 start 在初始化前写 preparing，成功后写 authorizing；不提前创建正式账号。正式账号列表及任务/养号/额度入口不能把草稿当作可用账号；只有账号页读取独立草稿列表。
- 列表 DTO 包含 `draft_id/environment_id/name/generation/state/session_id/reconnectable/credentials_ready/credentials_present/container_status/message/can_resume/can_restart/can_delete/can_reconcile/proxy_known/proxy_summary`。ID 是环境 ID，不能作为正式 account_id；`credentials_present` 只表示文件存在，不能推断认证成功。不返回令牌、代理密码、发送器秘密或 OAuth 参数。代理摘要从原私有 sender 配置提取，仅含协议/主机/端口；known=true且summary=null才是明确未配置，known=false显示待检查，不能冒充直连。
- 元数据使用 `atomic_json`、0600、原子替换与 fsync，保存在环境目录外。字段为环境/name、sid、字符串 generation、phase、version、home、created_at；保存中还可有 saved_account_id/cleanup_home，删除中有 deleting_at。不保存授权 URL/code/AT/RT 或终端全文。草稿 generation 是逻辑操作代次，与环境整数 generation 不同；旧无标记环境使用 `legacy-<环境generation>`，活动旧会话继续时补齐归属。
- 有效 phase 为 preparing/authorizing/ready_to_submit/committed/cancelled/ended/interrupted/reconcile/deleting/submitting。`home` 只接受 `/home/node` 或 `/home/node/.v3-login/<12位小写hex SID>`；元数据必须是对象，环境/name 一致、generation 是非空字符串、phase 有效。单条损坏或归属冲突显示 reconcile、generation=unverified、所有操作禁用，不能使其他草稿和正式账号不可见；JSON 或名称结构损坏的孤立标记也保留可见诊断。
- 列表不阻塞等待 owner 锁；初始化或提交锁仍占用时返回只读快照和操作进行中提示，禁用操作，不在该次查询改写会话状态。
- reconcile 输入沿用 `LoginDraftActionIn`。只允许原未绑定、SID/代次/环境归属可核对、非 preparing/deleting/submitting、无活动作业/发送请求及未知提交的草稿；原执行证明须匹配 login:SID、容器/环境代次，root/runtime/执行记录链接归属异常拒绝。列表只在可验证条件下开放 can_reconcile，状态读取失败只禁用本条恢复，不遮住其它账号。
- 恢复使用 owner → profile → environment 锁序，复用既有维护对账并保留 HOME、缓存和授权产物；外层 owner 释放后才调用自行加锁的 cleanup_reconciled。未绑定收口重新核对原 SID/草稿代次、环境 stopped、无作业/执行记录，只解除本代会话与名称占用，不能清理新代。取消清理失败返回固定 503 并保留草稿，不能假报取消成功。
- resume 有活动会话时继续原 SID/tmux，不启动第二个 CLI。重启后没有原会话但有产物时，在原环境/HOME/代理/版本认领新的维护 SID，实际 `claude auth status` 通过后才允许提交，不创建虚假的旧 tmux。restart 必须显式请求：先收口旧登录，再生成新 SID/草稿代次，仍保留原环境、容器、HOME 身份、代理及 CLI 缓存。
- 管理容器 `unless-stopped`，账号容器 `restart=no`、按需唤醒；启动 reconcile 收口遗留执行，HOME/草稿保留，状态显示中断或待检查产物。不承诺恢复宕机前已死亡的交互进程，不同时自启所有账号。
- 本地首次提交先写 submitting，持有 owner → profile 锁；中间 accounts 行保持 enabled=0。只要 submitting 标记仍存在，正式列表和 `_get_available_account` 均隔离该账号；仅原登录恢复路径允许 `allow_login_recovery=True` 穿过本地保存门禁。HOME 镜像成功后先把恢复入口改为主 HOME，再清暂存，失败仍能继续提交。全部保存和清理完成才启用账号、移除标记并缓存幂等结果。submitting 拒绝取消、删除及新登录，不能丢掉未确认产物。
- 完整删除采用 owner → profile → environment 锁序，锁内重读环境和代次。任一正式/软删除账号、同 profile 引用、run/flow 历史、未知提交/对账、其他作业或活动发送连接均拒绝。容器必须通过完整产品/部署/角色/环境 labels；目录须为专属 realpath，根或父目录链接、跨树内部链接均拒绝，npm 指向本专属树的链接允许。
- 先保存 deleting，收口原登录和执行，再停止并移除唯一归属容器，清环境 HOME/CLI 缓存/暂存和专属 profile；外部清理完成后才条件删除 account_environments，最后删除标记。Docker/文件/最终标记失败不能假成功；保留可见 deleting/reconcile 供重试，禁止期间唤醒/重建。重复删除已不存在草稿返回 ok；草稿已经正式提交时拒绝删除。


### 原文第 696—717 行

isolated_account_limits(memory: str, swap: str = "0") -> dict[str, tuple[int, int]]
cc2api/src/service/oauth.rs: validate_oauth_proxy(proxy_url, runtime_url, deployment_id)
AccountRuntime._adopt_sender_evidence(row: dict) -> None
verify_roles(cli, sender, network, fingerprint: dict) -> dict
```

### 3. Contracts

- 一个逻辑环境登记 network/CLI/sender 三个容器，共用同批 account 镜像；control/account 仍为两个交付镜像，清单 layout_version=2。三个角色严格核对 product/deployment/environment/role/release/isolation-version 标签；不能靠名称前缀或第一个环境容器推断角色。发送绑定继续核对环境、整数 generation、批次与秘密。
- network 持有 TUN/NET_ADMIN；CLI 为 UID1000、sender 为 UID1001，业务角色 cap_drop=ALL、no-new-privileges、根只读、独立 PID/挂载，加入本账号 network 容器的 netns。hostname/MAC 只配置在网络所有者，machine-id 两处只读挂载；保留原 HOME、userID、画像和最新凭据。
- MAC 使用 `networking_config={network: client.api.create_endpoint_config(mac_address=原画像MAC)}`，不能继续使用 Docker 29 / API 1.52 已废弃的容器顶层配置。验收同时核对网络端点及 CLI/sender 的实际 eth0 地址，并将 hostname/machine-id 与保存画像比较。
- network 只挂本账号网络控制、版本缓存写入区、私有 CA、CLI 证据/控制及必要 AT 快照，不挂完整 HOME。CLI 不挂 sender 秘密、代理密码、私有 CA 或其他账号额度，/flows/api 用空只读目录遮蔽；sender 只读私有配置并写自己的 API 证据。
- CLI 的 runtime 父目录 root:GID1000 0750，drivers/runs/jobs 由管理端保护父目录；单作业 group.pid 与 tmux 位于受控 jobs/<handle> 子目录。sender 配置目录 root:GID1001 0750、文件 0640，通过目录挂载接收原子替换。管理 JSON 使用逐级 O_NOFOLLOW 目录 fd、相对原子替换；读取限普通文件和 16 MiB，chown 不跟随账号链接。
- 创建角色前移交旧 `flows/api/observations.jsonl` 和 `.previous`：逐级 O_NOFOLLOW 目录 fd，以该 fd 将目录设为 1001:1001、0700；文件 O_NOFOLLOW/O_NONBLOCK，确认普通文件且硬链接数为 1 后 fchown 为 1001:1001、fchmod 为 0600。缺失文件由 sender 首次创建，已有内容不重写；只修改父目录无法使旧 root:root 0600 文件可追加。
- 网络过滤器在本账号 netns 原子安装 INPUT/FORWARD/OUTPUT 默认 DROP，先拒绝 Docker DNS 127.0.0.11，再开放回环、既有连接、指定代理 TCP、TUN；其他私网和 IPv6 拒绝。sender 8091 入站仅允许核验过的本部署 gateway/orchestrator 及桥网关。网络 ready 最多等 120 秒，确认前不启动业务；删路由/网络进程故障不能回退 bridge 直连，不修改宿主共享规则。
- 服务端 OAuth 仍由 gateway 的原 HTTP/TLS 客户端发出，账号 netns 防火墙不能保护它。`V3_RUNTIME_URL` 或 `V3_DEPLOYMENT_ID` 任一非空时，空串/空白代理在创建 OAuth 客户端前返回 ServiceUnavailable；授权交换、刷新和 usage 共用该入口。非空非法代理解析失败也不得直连；两个标识均为空的独立部署保留原空代理语义。不伪造浏览器网页授权的出口。
- 基础布局总 RAM/swap 来自已保存画像：network 256 MiB、sender 128 MiB、CLI 取剩余且至少 512 MiB，额外 swap 只归 CLI；Docker memswap 为角色 RAM 加其额外 swap。CPU 按 CLI:network:sender=6:1:1 分配，pids 分别为 512/128/128；CLI /tmp 为 128 MiB noexec。部署预检、容量及停止不能漏计辅助角色或放大账号总预算。
- 新登录与项目环境均使用基础三角色预算，不再静态预留512MiB或创建 `runtime/project-review-layout.json`。评审先停止原固定CLI，再串行复用扣除network/sender后的RAM，结束后恢复同一CLI。旧schema1布局只读核验实际限制，不隐式扩容、重建或改写固定配额；旧隔离版本仍须显式空闲升级。`account_environments.container_id`始终指固定CLI；交接记录、私有目录、原owner刷新及严格收口以[项目场景契约](./project-iterations.md#scenario-内容-schema-2-的真实项目多场景任务与-policy-3)为准。
- 创建按网络 ready 再业务角色，逐个登记；失败停止本代已创建实例并保留对账证据，未知/部分角色不能 ready。停止按 CLI→sender→network；维护、备份、草稿删除与孤儿处理核对完整角色集合。管理端重启与 CLI 单次取消保留健康 API/SSE；CLI 单独异常仅关闭下一 CLI。
- 布局 0 的已有实例只在显式空闲重建时转换，GET/普通发送不能静默迁移。先停机备份，转换保存私有 isolation-upgrade 快照；回退保留最新 HOME/凭据，不恢复旧 RT/数据库覆盖轮换结果。未创建实例的新行保持布局 0，受控 ensure 才登记 2。
- 业务指标取 CLI 实际 PID/cgroup，管理端写私有观察记录。验证 CA 仅供 verification 镜像，sender 的只读 /run/v3 下嵌套 CA bind 必须预置目标；正式镜像不读取该 CA。测试依赖的系统目录仍只读，故障注入使用网络私有运行记录。


## .trellis/spec/vibecoding-bench/backend/database-guidelines.md

源 SHA256：`e82f74105ee44dbfd6cf1e4265a359bea5892918d88ea27dff063e2783cd8660`。

### 原文第 533—549 行

### 3. Contracts

- 身份由 bench ID、绑定 ID、profile 的账号/组织 UUID 构成，不使用轮换 AT/RT。run 固化 quota_identity，身份变化不得自动在新身份执行旧工作。来源为 `run:<rid>:<attempt>` 或 `continue:<sid>:<generation>`。
- sidecar 仅观察当前 OAuth AT 所属的 `api.anthropic.com/v1/messages`。内部白名单 JSONL 保存 source、identity、ts、status、额度头及有限 account_error，不保存 AT/RT 或任意错误正文。dummy key、其它域名及 OAuth 路径不能污染账号额度。
- 每窗口保存 observed_at、utilization（百分比）、reset_at（UTC 秒）、rejected、exhausted。响应头比例乘 100；秒、毫秒、带时区 RFC3339 均可解析。缺失/非法窗口保留既有事实，按窗口自身时间合并，乱序或同时间允许不能清掉拒绝；跨周期高位残留按真实允许响应归零。
- 429 的 rejected 优先，allowed 排除该窗口的高位猜测；普通 RPM 429 不形成通用耗尽。仅 seven_day_fable / 7d_oi 耗尽不阻断通用窗口。通用窗口达到 100% 或明确拒绝后阻止后续正式请求；已接受的成功流可以完成。
- 多窗口耗尽取全部 reset 及可信 retry-after 的最晚值。无可信 reset 时保持等待，不猜 now+5h/7d。明确 limit 但窗口未知时保存 unknown 补证；已有真实耗尽窗口不再追加未知阻断。
- 到期仅为 retry_ready，不写成恢复或 0%。共同门禁先认领一个已有正式执行；其真实允许响应合并后，未再耗尽才放行其它工作。执行失败释放本代认领，不能批量冲上游。
- quota_wait 是非终态，不计批次完成。自动恢复沿用 run/task/prompt、workspace/session、CLI/effort/权限/模型快照；首次额度判定前固化 execution_model，空串也属于有效快照，不能重新读取全局覆盖。恢复使用原主会话并按本次新增 JSONL 判断完成，排除子代理和复制的旧历史。
- worker 优先处理独立暂停信号，保存状态后以 43 退出。rate_limit、account_on_hold、invalid_grant 及其它 synthetic API 错误不能判 success；明确封号/invalid_grant 固化永久门禁、暂停批次并关闭养号，不按额度到期恢复。
- 停止、暂停、关闭养号/续聊、账号停用及删除优先。代次/status/父任务/stop_requested_at 必须在恢复与收口时复查；绑定和重授权的活跃检查包含 quota_wait。等待不占 semaphore 或长期 owner/profile lock。
- 共享状态为 `BENCH_DATA/quota/<aid>/state.json`，原子替换并挂只读目录。控制为 `BENCH_DATA/quota-controls/<rid>/<source_hash>/pause.json`，位于可写 workspace 外，sidecar RW、worker RO；宿主挂载使用 HOST_BENCH_DATA。sidecar 使用 QUOTA_SOURCE、QUOTA_IDENTITY、QUOTA_STATE_FILE、QUOTA_SIGNAL_FILE、QUOTA_OBSERVATIONS_FILE、QUOTA_CREDENTIALS_FILE 和执行级 QUOTA_WARMUP；worker 消费来源、信号文件及养号作用域。固定 v3 的实际路径映射见 [账号运行环境](./account-runtime-v3.md)。
- 日志优先写入，再发布控制；控制携带归一化 quota_state，日志故障仍保留真实 reset 和封号分类。服务启动在清理原容器前后消费观察与控制补证，严格清理失败不得恢复。控制损坏或门禁不可读按执行失败收口。
- continue HTTP 可返回不占 worker 的等待 session；WS 的 quota_state 事件包含 status、message、resume_at、generation，running 只在 PTY 打开后通知。服务端拒绝等待期文本/二进制输入且不重放；关闭/断连取消重建。抓包 run 与抓包续聊自动恢复共同遵守串行、120 秒间隔和异常后至少 15 分钟暂停。
- accounts/run/batch API 的 passive_quota 只返回 source、known、windows、observed_at、blocked、exhausted、resume_at、retry_ready、message、account_error，不暴露内部身份或哈希；页面渲染、刷新、SSE 不触发主动查询，显式手动查询仍可更新来源为 manual 的记录。
- 配套交付 orchestrator、worker、sidecar 和 WebUI。回滚旧版前先停止等待工作并备份 SQLite；旧版不识别 quota_wait，不能将等待记录批量改为 active，不删除 profile/workspace/flows。


### 原文第 621—641 行

### 3. Contracts

- 阈值是 1～100 的已用整数百分比，两个窗口独立，默认 NULL；省略保留，null 关闭，StrictInt 拒绝 bool／字符串／小数。保存不隐式改绑。
- v3 保存请求显式包含任一阈值时，先落库并发布额度快照，再分别通知项目迭代和养号迭代重查。`recheck_waiting` 只把已启用、`schedule_state='waiting'`、没有在途控制者的计划移到当前本地检查时间，保留控制代次、原工作及会话；保存接口不调用模型。正常轮间 `scheduled`、人工关闭及服务退出不重新排期。
- 重查仍通过原 `start(..., scheduled=True)` 核对模型／运行故障冷却、账号身份、输入对账及实时门禁，未解除限制时继续等待。成功认领控制者时清空旧 `schedule_message`，避免运行中继续显示旧额度等待原因。
- 未绑定账号有完整本地 OAuth 时可以启用定时养号；绑定账号核实身份与 active OAuth，只由 cc2api 刷新。未绑定配置缺凭据返回 409，不调用 cc2api；NULL 绑定的调度写入用 IS ?。
- 首次额度未知不写成 0%，也不因无样本、进程重启或 300 秒缓存年龄而等待主动查询；没有真实拒绝或有效命中时可启动已有正常任务，由正式响应更新。任一有效窗口已用等于或高于启用阈值时，只阻止下一轮；已启动的普通任务／养号按冻结计划完成本轮，包括原定补充、收尾和超时。运行中降低阈值同样只影响后续入场，本轮可能越过自设百分比。
- Docker exec 等待循环只等待原执行退出并返回真实退出码，不再接受百分比强停回调。Scheduler 在发布终态之前消费最后的本地观察，保证下一轮门禁看到本轮用量；不因百分比写 stopping/stopped，不提前注入收尾。缺失、非法或过期窗口不构成有效阈值命中。
- 真实额度耗尽、认证失败、用户停止、删除、原超时和清理失败保留各自处理。既有用户停止和自然终态不被百分比重新分类，明确 account_on_hold／invalid_grant 保留永久门禁。历史停止意图只完成旧轮收口；已持久化停止终态仅补实际退出码，不改原因或结束时刻，不改为 quota_wait 或再次提交。
- 旧命中窗口 reset 到期只给一个已有执行正常恢复机会。共同耗尽到期同样参与认领，即使百分比阈值关闭；普通任务／养号／续聊／抓包共用 `policy_key="v3-passive-recovery"`，周期键包含阈值与 reset，以及已耗尽通用窗口的 reset。同周期并发、失败和重启不能再发探测；真实允许的新周期事实才能继续推进。
- v3 管理端和 Recorder 必须共用 `passive_recovery_decision`。`warmup_quota.policy_key="v3-passive-recovery"` 选择该规则；内部 `sample_windows` 仅列实际到期的旧命中／共同耗尽窗口，`warmup_sample_used` 据此匹配同一持久周期。空闲 0% 且 reset 为空仍可正常启动，不能因缺少旧 runner 的未知单次许可就写 `pause.json`；旧 runner 继续使用原 `warmup_quota_decision`。Recorder 仍合并当前实际响应，不能直接信任发布快照中的旧 `blocked` 值跳过最新阈值或真实耗尽保护。
- 真正额度耗尽的 quota_wait 仍保留原 run／批次、prompt、workspace/session 与版本／effort／模型快照并按既有恢复流程续跑。百分比命中后，已完成本轮保持实际终态；下一未执行 run／item 等待额度和原 next_launch_at，不重新执行已完成或历史 stopped item，不清空随机间隔。定时养号按既有间隔安排新一轮；零 run 活动批次依本地事实和恢复机会创建首个正常工作，后台不补查。
- API 继续消费发送器白名单响应头；CLI 在普通任务、养号、原任务恢复和非抓包续聊临时包装 statusLine，stdin 的 `rate_limits.five_hour/seven_day.used_percentage` 为 0～100，`resets_at` 为 UTC 秒。bool、非有限值、越界值、非未来 reset、超过观察时间 6 小时／8 天的 reset 或缺失窗口不写入；缺失不补零，不删除其它窗口。
- collector 校验 cwd、主会话目录／文件名、非链接 transcript，最多读取尾部 512 KiB；仅使用本代开始后且不超过当前时间 5 秒的正常主 assistant 响应，排除子会话、synthetic/API 错误和会话冲突。ts 使用响应时间；flock 去重 session／response ID／窗口内容，重复缓存不伪造新观察时间。
- 观察只保存 source=`cli:<执行来源>`、identity、ts、origin=cli、session_id、response_id 和 rate_limits 白名单；不保存完整 stdin、prompt、工具内容或凭据。QuotaGuard 校验游标来源、身份与 origin，CLI 事件不能提供 account_error。现有用户状态栏获得原 stdin 并保持输出；collector 无网络调用，不增加定时刷新、usage 或模型请求。
- 采集目录仅为当前 UID1000 开放专用写入和必要路径穿越，不放宽 root runtime。先落盘原 statusLine／本代命令证明，再改 HOME settings；收口及重启对账停止进程后，仅恢复仍由本代管理的字段。抓包保留 Recorder，采集与执行实际路径见 [账号运行环境](./account-runtime-v3.md)。
- 手动 usage 在固定容器使用 Node 原生 TLS，经账号代理发送 GET JSON，不安装 CLI、不切换监听、不注入 MITM CA；请求 15 秒截止，不在脚本内反复重试。只领取／释放共享 CLI 作业，API 可并行。owner 锁不可重入，绑定查询使用 _sync_bound_account_credentials_locked；HTTP／Docker IO 不在数据库锁内执行。
- 手动错误不安排后台重试，保留旧事实；只有结构化 `account_on_hold`／`invalid_grant` 固化永久门禁，普通 401／403、429、网络或 5xx 不凭状态码推断封禁。手动成功沿已有合并／恢复规则更新，不复活历史 auth_failed run。
- 公开 quota_policy 保留 enabled/limits/hit/unknown/blocked/resume_at/message/refresh_retry_at，后者为 null；不返回身份、许可或内部策略键。来源显示被动、manual 手动及 automatic 历史查询；页面读取、SSE 和批次等待均不主动查询。
- v3 lifespan 收口旧执行后恢复仍启用账号的 active 批次；先等待持久 next_launch_at，原 item 不重置，paused/done/deleted 或停用账号不恢复。旧 runner 启动行为保持。


## .trellis/spec/vibecoding-bench/backend/project-iterations.md

源 SHA256：`8f4b89dbfb175230e78f108353273f84e754ba5d29d79ab16f8d55c0bb80c6aa`。

### 原文第 1020—1034 行


- PiTerminal.start(account: dict, work: dict) -> dict：返回原有 token/source/workspace/native 及交互、额度信号定位；不新增公开字段。
- PiTerminal.passive_status(work: dict) -> dict：按已核对的逻辑 source 读取原生额度补证。
- job.handle 是本次启动独立的 20 位小写十六进制标识，沿既有执行记录保存；source 仍为 namespace:work_id:generation。

### 3. Contracts

- 每次 start 独立分配 handle，runtime/jobs/<handle> 与 controls/<handle> 必须独占创建，任一路径已存在就拒绝；不得覆盖旧证明、许可、结果或设置覆盖。
- tmux socket、driver、process.json、start.json、process-result.json、交互及暂停信号都绑定本次 handle，后续读写从现有 job 定位。
- _attach_process 继续核 schema、source、PID、内核启动时刻、parent、UID 及真实进程存活；核验并登记后才发布匹配许可。新目录不能成为放宽进程校验或解除隔离的理由。
- 原工作 ID、Claude session、cwd、冻结版本／设置、累计预算、source 和额度归因不变；恢复仍依据原会话文件选择 resume。
- 原生补证游标维持 runtime/<namespace>-quota/<sha256(source)前20位>.json；启动时从原会话当时的字节末尾开始。游标不能跟随随机 handle 改名，否则 passive_status 会重读旧错误。
- Projects 和工程养号、capture 开启／关闭共用本合同；捕获模式继续使用 pi-capture 独立监督与既有 CA／Recorder 配置。
- 旧执行记录按原 schema 与已保存 handle 读取，不批量改写历史。未知启动、清理结果不确定和未对账输入继续保留原门禁，不能仅凭可写结果中的 cleaned=true 自动清除。
