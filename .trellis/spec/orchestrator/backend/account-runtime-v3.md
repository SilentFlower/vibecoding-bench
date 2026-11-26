# v3 固定账号运行环境契约

## Scenario: Claude 账号 V1/V2 切换及已运行发送器查询

### 1. Scope / Trigger

- 修改 Claude 账号转发选择、私有 sender 发现、节点检查或账号凭据回执时，核对账号、节点分配和工具轮归属。

### 2. Signatures

- `PUT /admin/accounts/{id}` 单独提交 `request_backend` 与非负整数 `request_backend_revision`。管理视图返回生效值、待切目标、修订和 `tui_v2_available`。
- `GET /internal/v3/transport/{account_id}?wake=false` 读取当前发送器。`NodeTransportInspection` 在节点 `inspect` 操作中携带正整数 `transport_gateway_account`。
- 账号镜像以 `tui-guard --check` 核验当前节点，以同一程序在发送器分配的 PTY 上启动固定 CLI。探测成功返回 0，隔离初始化失败返回 125。

### 3. Contracts

- 受管 Claude 账号有原生 `native293` 与交互 `tui_v2` 的账号级选择。管理读取只查现有绑定。保存涉及 V2 的切换时，编排确认无运行绑定后可以按需准备该账号。
- 切换以实际 sender 状态、绑定代次及在途工具回执为准。活动轮按原绑定收尾。V2 新请求沿账号凭据解析获取当次 AT，通过单次私有提交交给目标账号 sender。
- 隔离程序读取运行内核的 Landlock ABI。ABI 2 组合目录授权和进程过滤器保护私有文件，允许 CLI 通过本会话获准写入的文件描述符保存配置与历史。已授权的项目工作区可以共享。ABI 3 及以上使用内核的文件截短权限。
- 原 `NodeInspection`、`BoundIdentityRead` 与 `CredentialStatusRead` 保持现有字段。节点 `inspect` 仅在收到 `transport_gateway_account` 时按 `NodeTransportInspection` 解析。其他请求使用各自原模型。

### 4. Validation & Error Matrix

SSH 节点完成更新后，日志中的 `target_account_release` 来自实际准备回执的账号镜像发行。旧日志缺此键时，按原节点 ID、密钥标识、配置修订和目标控制发行匹配已准备回执，再比较账号镜像发行。显式空值或冲突值拒绝。控制镜像和账号镜像可以分批发行。

| 条件 | 结果 |
| --- | --- |
| 外部管理写入缺少修订或修订已变更 | 返回缺少修订或并发冲突 |
| 编排确认账号没有运行绑定 | 只读返回空。保存涉及 V2 的切换可以请求准备 |
| 正在交付旧轮或等待旧工具回执 | 待切目标保留，原内核继续处理 |
| 节点账号、环境、发行或代次证明不一致 | 拒绝该绑定 |
| Landlock ABI 低于 2、规则加载失败或进程过滤器加载失败 | 发送器隔离探测失败。账号切换沿现有未就绪路径返回 |

### 5. Scenarios and Examples

- 正常：在休眠账号保存 `{"request_backend":"tui_v2","request_backend_revision":0}`，编排准备同一账号后由 Gateway 登记已核验的绑定。
- 边界：工具续轮进行时保存 `native293`，待原轮收尾后对账生效。
- 在 ABI 2 节点更新账号镜像后，通过实时就绪检查即可保存 V2。仅凭镜像标签或宿主版本号判断可用会漏掉规则加载失败。
- 兼容：旧节点凭据回执按原模型完整字段比较。扩展字段登记在 V2 专用请求模型，保持凭据查询和身份回执可用。

### 6. Tests Required

- `test_cluster_synchronization`、`test_tui_node_transition` 核对分批镜像和旧节点日志的原绑定证明，包括节点或发行错配时的拒绝。
- 后台子代理首轮若比父 `Agent.prompt` 恰好多一个 LF，只有同一账号、环境代次、主体和会话的原工具启动回执匹配子代理 ID 才能接入。先来的子轮复用有界回执等待。仅比较签名时兼容这一个字符。`test_background_child_receipt_accepts_one_cli_line_feed` 覆盖回执晚到、额外空格、双换行、CRLF 和重复提交。

- `verify_tui_sender_status.py` 核对管理详情只读、休眠双向切换、在途工具续轮和错误绑定。
- `deploy/flower2api/verify_tui_guard.py` 验证私有配置、共享工作区、终端描述符及初始化失败。兼容性变更须在真实 ABI 2 与 ABI 3 或更高版本分别验证管理端切换、发送和重启后的原历史续写。
- `test_cluster_credential_refresh`、`test_cluster_owner_runner` 核对旧节点凭据与身份回执。`test_cluster_transport` 核对排空时原 V2 路由可用和源隔离后的拒绝。

## V2 后台派工的流式交接

### 1. 适用范围

Claude Code 在父模型响应仍打开时，可能已为完整的 `Agent` 或 `Task` 工具块发起子请求。

### 2. 接口

`WireStep.observe(event)` 在 `content_block_stop` 返回已校验的完整块。`SessionDriver.prepare` 使用原预留截止和取消信号等待归属。回执由 `tool_receipts(messages, previous, expected, *, input_format=None)` 核对。

### 3. 数据合同

派工在公开工具关闭帧前登记。等待首次匹配时冻结所属模型步骤，后续启动回执也须属于这些步骤。同一账号绑定、主体及会话内，已封闭工具组中的唯一精确提示可以认领。多一个 LF、同提示歧义或携带额外协调消息时，以原工具的成功启动回执核对子 ID。协调消息另需匹配原父代理发给该收件人的 `SendMessage` 内容。模型接收完整的原始消息。

### 4. 异常

等待中的原步骤取消，后来另一父轮发出相同提示时，旧等待按归属错误退出。新派工保留其启动资格。重复认领和不匹配的准备请求在提交模型前结束。

### 5. 场景

固定版 2.1.293 的父续轮可以把交错的文本归到工具组前。对已识别的该版 Agent/Task 纯文本与工具组合，比较时保持各自的原序，逐块核对文本、工具 ID、名称和参数。含签名或思考块的序列沿原顺序核对。

### 6. 验证

`test_open_group_waits_until_tool_order_is_known`、`test_cancelled_parent_waiter_cannot_move_to_replacement_step` 和 `test_closed_agent_block_and_late_directed_message` 分别覆盖组封闭、同提示替代派工、晚到回执与追加消息。`test_cli_groups_agent_text_without_changing_tools_or_signatures` 覆盖父续轮分组及内容改动。

## V2 思考签名 400 同轮恢复

### 1. 适用范围

Claude V2 的公开 Messages 请求。普通 API 和原生输入使用同一恢复协议，覆盖首轮、工具续轮、SSE 和 JSON。

### 2. 私有接口

- Unix 来源以 `signature_repair_protocol=1` 声明能力。Gateway 的 prepare 使用 `x-v3-tui-signature-repair: 1` 启用本轮，已命中失效历史时使用 `known`。sender 在准备响应确认 `1`。
- 首次完整拒绝可随私有 HTTP 400 返回 `x-v3-tui-signature-repair: pending`。恢复使用空正文 `POST /internal/tui-v2/repair`，沿原 Bearer 和 `x-v3-tui-reservation`，附 `x-v3-tui-repair-attempt`。值为区别于原预留 ID 的规范 UUID。
- 中继仅在 CC 路径放行此 POST，沿原节点、账号、环境代次及排空门禁。成功关联时响应必须回显同一尝试 UUID。明确拒绝使用私有 `409` 和 `x-v3-tui-signature-repair: declined`。私有控制字段由 Gateway 消费。

### 3. 合同

- 只接纳业务响应开始前实际提供方完整返回的 HTTP 400。错误体上限为 1 MiB，须符合 V1 的 `invalid_request_error` 思考签名拒绝判定。sender 核对正文确实可降级，保留原 Unix 连接和活跃预留。
- 账号源按 HTTP 定界核对错误体。声明长度时须读满，分块响应须读到结束块，省略长度的非分块响应以正常 EOF 结束。长度无效、正文截断或读取异常时沿原错误路径收口。`test_model_error_completeness_follows_http_framing` 覆盖上述边界与大小上限。
- Gateway 在原截止内再次获取同账号的发送准入，通过原账号和会话门禁才交付许可。sender 在原绑定内消费一次许可。原进程和同一模型步骤使用冻结的凭据、会话、模型、已组装的请求头和工具账本完成投递。实际 Content-Length 随修复正文计算。文件凭据仍以原快照的到期时间为准。已明确在出站前被拒绝时交付首次签名拒绝。
- 降级只改出站正文。历史 thinking 转成文本，清理 redacted thinking、顶层 thinking 及相关策略。工具字段与工具数值保留。已有 CCH 随最终字节刷新。
- 失败轮释放后，同会话按原生日志恢复时可以合并相邻用户行。认领主轮须匹配最后一个用户文本块的提示摘要与紧随系统消息中唯一独立的当前标记行。
- Gateway 仅在核对第二次实际响应后记录第二条尝试，使用独立 UUID 和 `signature_repair` 原因。收到 2xx 后复用 V1 按真实会话和完整历史前缀保存的摘要。后续命中时首发前降级。诊断采集继续按原授权和脱敏门禁处理。已协商最终 TLS 收集时，原预留将写出观察绑定到该次实际 UUID。两个尝试各自占用原写入名额并独立收口。

### 4. 校验与错误

| 条件 | 结果 |
| --- | --- |
| 本轮取得恢复许可并收到第二次实际响应 | 公开接口交付第二次响应 |
| 普通 400、错误不完整或业务 SSE 已开始 | 沿现有错误或事件流收口 |
| 准入超时、旧组件缺能力或旧中继明确发送前拒绝 | 保留首个 400，待恢复预留按原取消和时限收口 |
| 跨绑定、重复或过期的恢复指令 | 拒绝指令，额外模型投递为零 |
| 发出恢复许可后缺少可核验的提交回执 | 按提交状态未知返回 502 |

### 5. 场景

已有 Read 工具回执的原进程首次收到 `Invalid signature in thinking block` 时，降级后的第二次模型请求保留同一回执。新的 prepare 无法恢复原轮已认领的步骤。恢复指令应沿仍持有该步骤的原预留送达。

### 6. 回归

- `signature_repair_retains_original_source_until_resolution` 验证原连接、错绑定、许可撤销、重复控制和实际发送证据。`v2_repair_preserves_tool_value_bytes_and_refreshes_cch` 核对高精度工具参数和 CCH。
- `test_signature_repair_sends_twice_in_one_claimed_native_step` 核对只认领一次。`test_cluster_transport.py` 核对私有控制头、实际 sender 空正文及远端隔离规则。
- `test_resumed_user_blocks_bind_the_latest_prompt_and_system_guard` 核对失败会话恢复布局、旧提示、旧标记和重复标记。
- 隔离 HTTPS 回环逐次核对固定版 CLI 的真实模型收包、工具回执、原账号与会话、两条诊断及旧组件回退。

## V2 慢工具回执

### 1. 适用范围

客户端执行工具期间，账号进程通过会话专属的 Mod 回调等待工具结果。

### 2. 接口

首次私有请求为 `POST /results {"ids":[...]}`。返回 `{"pending":"<编号>"}` 后，Mod 用同一组 ID 和 `ticket` 继续查询。结果到齐即返回 `{"results":[...]}`。

### 3. 数据合同

在 V2 原生进度模式中，已核对完整工具组的网关使用 `agent_summary=true` 预留，源返回独立进度工作区。同一主体、会话及子代理复用专属进度目录。模型每次读取本次冻结的请求，进度 actor 结束后归还物理位。 账号没有 cgroup 内存硬上限时，只有正在等待工具的子代理可为原生进度查询借用一个额外驻留位。显式内存上限仍约束总进程数。全部物理位都在等待工具结果时，摘要请求按已有容量退避返回，真回执照常认领。

一次本地条件等待最多 20 秒。编号绑定原账号进程、模型步骤和工具 ID 集合。每段等待复用原工具有效期。业务回执就绪后唤醒等待方，并按原输入顺序交付结果。

### 4. 异常

过期、陈旧编号、错误组和重复交付的私有查询返回 409。会话取消会唤醒等待方。

### 5. 场景

Bash 在第 43 秒结束时跨过两次分段等待，第三次查询立即获得真实结果。下一步即使复用相同的工具 ID，也需要该步的编号。

### 6. 验证

`test_slow_receipt_polls_only_its_current_group` 核对编号、截止与重复交付。用真实 CC 2.1.293 核对慢工具、并发进度查询及真实模型续轮次数。

## V2 工具续轮断线恢复

### 1. 适用范围

客户端通过 `POST /v1/messages` 提交原工具组的结果后，网络断开可能发生在响应首包前、流式输出中或客户端慢读期间。网关在每次重试时核对入口令牌、可用账号、原环境绑定及会话策略。

### 2. 接口与存储

原发送器在 `continuation_only` 预留上通过私有响应头 `x-v3-tui-handoff-kind: recovered` 确认冷恢复。源端在账号卷的 `tui-reconnect/receipts.db` 保存历史与工具声明摘要、请求选项摘要、修订和到期时间。恢复沿用已有工作区与子代理身份。网关以原回执修订作条件更新。

### 3. 交付与计量

相同请求共享一次模型生成，可以从头接回原消息和原工具 ID。重连窗口自最后一个有效读者离开起算 10 秒，覆盖等待首包和慢读已完成回复。缓存已超限或工具组已推进时，拒绝的订阅保持原截止时间。进程级前缀缓存共用 64 MiB 预算，已有连接在预算耗尽后沿有界通道继续读取。

原进程退出且原回复已释放时，源端核对原主体、会话、子代理、环境代次、完整工具声明、历史及已绑定的结果与参数，按原修订消费一次替代生成许可。已完成的工具结果作为历史交给模型。每次实际生成按自己的调用 ID 保存上报的累计用量，接回响应复用原调用的记录。

### 4. 错误处理

新工具指令已经开始交付且缺少执行结果时，返回 `409 outstanding_tool`。已消费替代生成许可时，返回 `409 recovery_used`。已定位待恢复的原步骤，发送器准备阶段仅返回通用输入拒绝时，网关返回 `409 tool_recovery_unconfirmed`，提示核对原回执及参数、更新旧版账号后台。发送器的具体输入错误沿用原状态与分类。

### 5. 场景

同一子代理交回 Bash 结果后，客户端在大回复生成结束时继续读取 12 秒，断开 6 秒后并发重试。两条连接应收到相同的完整消息，模型投递一次。原进程和回复均已丢失时，可在同一子代理增加一次模型投递。若客户端已经交回下一组工具的结果，应从最新回复继续。

### 6. 回归

`reconnect_preserves_completed_reply_for_slow_reader` 和 `rejected_reconnect_preserves_idle_deadline` 分别核对慢读与无效订阅。用隔离公开路由验证首包前 JSON、SSE、网关重启、并发恢复、旧发送器提示和撤权。对照原消息 ID、旧工具的实际执行次数、下一轮工具结果和两次生成各自的用量记录。

`verify_tui_cold_history.py --reconnect-tool-stream` 在公开工具续轮交付半段参数后断开。等 6 秒后接回，逐字节核对前六个 SSE `data` 行，再放行余下参数。第二个读者收到第七个 `data` 行并断开后才放行终帧。第三个读者从缓存收到共十帧并逐字节保留已有七帧。以公开请求 ID 核对三个读者的尝试数为 1、0、0，模型累计收件保持为 2。下一合法工具回执再投递一次，过期回执返回 400。

## V2 直接工具调用的客户端回执

- `tool_receipts(messages, previous, expected)` 在原会话的历史和完整工具组匹配后，按工具 ID 交付结果。
- 上轮登记的 `tool_use.caller` 恰为 `{"type":"direct"}` 时，允许客户端在回传该块时省略顶层 `caller`。兼容只作用于比较快照。发给提供方的请求保留客户端的字段写法及既有缓存策略。
- 显式 `null`、非直接调用来源、工具 ID、名称、执行参数或签名发生变化时，沿原错误路径拒绝。省略工具输入中的同名业务字段仍属于参数变化。
- `test_tool_receipts_allow_missing_direct_caller_only` 核对正反例。公开接口验收分别使用显式和缺省会话 ID，回填并行工具组并继续下一轮，核对每次成功回填的单次模型提交、工具 ID 及缓存断点。

## Scenario: US 宿主管理工具继承既有口令例外

### 1. Scope / Trigger

- 更新 `/opt/vibebench-v3-us/deploy/v3/manage.py` 时，核对该宿主已有 `server-password-override.json`。通用仓库管理工具保持全部秘密至少 32 字符；US 宿主覆盖继承其已批准的现有管理员口令。

### 2. Signatures

```text
宿主覆盖函数：_existing_us_admin_password(values: dict, deployment: str) -> bool
宿主记录：/opt/vibebench-v3-us/server-password-override.json
预检：preflight(values) -> Path
兼容检查：check_credential_compatibility(root, manifest) -> None
```

### 3. Contracts

- 工具升级先核对旧宿主文件和部署配置摘要，使用确认 CI 的通用源文件，再继承已有服务器覆盖；运维记录保留来源、base_revision、original_sha256、override_sha256 和批准原因。服务配置与现有口令保持，不把秘密写入命令行、日志或任务记录。
- 例外只对 `deployment=us`、`V3_DATA_ROOT=/srv/vibebench-v3-us` 生效。记录必须为非链接普通文件，kind 为“服务器管理密码运维调整”，override_file 为 deploy/v3/manage.py；私有 approved_admin_sha256 必须与当前已批准管理员口令一致。字段值留在宿主受保护记录，不在文档写入实际摘要。
- 仅管理员口令可使用这项既有例外；V3_INTERNAL_TOKEN、V3_SESSION_SECRET 继续至少 32 字符，新口令或其它部署沿用通用长度检查。
- 候选环境只改变 release/control image/account image/manifest 四项，其他配置逐值相等。按当前 US 选择跳过 RAM 重算时，仍保留此前的端口、归属、镜像能力及凭据所有权回退检查。
- 发布只读验证包括同批实际镜像源文件、协议能力、两库、管理鉴权与接口响应；自建采样会话单独撤销，用户会话保持。是否等待 API 转发按本次用户授权执行，CLI/Pi 和未确认输入仍须收口。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| US 现有口令与受保护批准记录匹配 | 继承既有口令例外 |
| 新短口令、其它部署或记录缺失/损坏/链接 | 不使用例外，沿通用长度检查 |
| 内部服务或会话秘密不足 32 字符 | 预检拒绝 |
| 工具/配置摘要漂移、镜像协议不匹配 | 停止发布，不覆盖当前配置 |

### 5. Scenarios and Examples

- 正常：从确认 CI 更新宿主工具，保留记录批准的现有管理员口令；新所有权回退保护与原内部秘密校验同时生效。
- 基础：其它部署继续使用仓库通用管理工具，无 US 例外。
- 错误用法：直接覆盖宿主工具后，发现旧口令不满足通用长度要求便换密码，或删除所有秘密检查。正确处理：核对已有批准记录，仅继承对应管理员口令，保留内部和会话秘密校验。

### 6. Tests Required

- 宿主定向检查：原已批准口令命中；替换为另一短口令、另一 deployment 均不命中；内部/会话秘密短值分别抛出对应长度错误，且尚未运行资源计算。
- 正式 CI 镜像在断网空库启动，验证归属协议及迁移；同批预检和实际源文件摘要通过，环境候选仅四项变化。
- 部署后健康、归属/导航、原持久身份/目标/设置、非目标容器和两库 quick_check 通过。真实供应商 OAuth、真实模型探针与这组检查分别记录。

## Scenario: v3 凭据单一所有者与交接协议 1

### 1. Scope / Trigger

- 修改创建/关联/解绑、关联重授权、OAuth 刷新、后台上游活动、归属展示或联合回退时适用。短期运行租约与长期刷新权分别持久管理，租约过期不能解除长期暂停。

### 2. Signatures

```text
GET  /admin/runtime/credential-capabilities
GET  /admin/accounts/{id}/oauth-ownership
POST /admin/accounts/{id}/oauth-ownership
POST /api/accounts/{aid}/cc2api/create
POST /api/accounts/{aid}/cc2api/bind
DELETE /api/accounts/{aid}/cc2api-binding
POST /api/environments/{environment_id}/maintenance
CredentialOwnership.record_local_authorization(account_id, version=None) -> None
CredentialOwnership.guard(account, source=None) -> None
check_credential_compatibility(root: Path, manifest: dict) -> None
```

- 网关表：`oauth_account_ownerships(account_id BIGINT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE, record_json TEXT NOT NULL)`；`oauth_handoff_operations(operation_id TEXT PRIMARY KEY, account_id BIGINT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, record_json TEXT NOT NULL)`。SQLite/PostgreSQL 同事务保存所有权、回执及交接凭据，按完整原所有权 JSON 条件更新。
- bench 表：`account_credential_ownerships(account_id INTEGER PRIMARY KEY, record_json TEXT NOT NULL)`；`local_credential_authorizations(account_id INTEGER PRIMARY KEY, record_json TEXT NOT NULL)`。本地绑定与相应交接阶段用同一短事务保存；HTTP 在数据库锁外。

### 3. Contracts

- 内部接口同时要求管理 Bearer 与 `x-v3-service-token`；能力返回 `{credential_ownership_protocol:1}`。交接响应含 `protocol:1/ownership/receipt`，完整凭据快照只向受信任内部调用方返回。浏览器仅接收无身份秘密的 `owner/phase/message/remote_id/environment_id/direction` 摘要；列表批量读取，不逐账号刷新或扫描 HOME。
- 输入为 `protocol/operation_id/action/direction/identity/expected_generation/source_refresh_sha256/lease_owner/credentials`，拒绝未知字段；action 为 prepare/commit/finish/cancel/status，direction 为 create/attach/return/authorize/detach/reauth/retire。操作和代次为 32 位小写十六进制；identity 固定 deployment_id、environment_id、bench_account_id、device_id、email、account_uuid、organization_uuid，device_id 为 64 位十六进制。凭据为 access_token/refresh_token/expires_at（UTC 毫秒），不保存到待办、回执或证明表。
- owner 为 gateway/local；phase 为 ready/handoff/reauth/reconcile。仅 gateway/ready 允许网关新上游活动；无所有权记录的普通账号沿用原行为。坏记录只隔离所属账号，不影响整个账号列表或其他账号调度。
- prepare 先关闭新准入、持久归属并排空最多 8 秒。活动许可必须覆盖实际网络发送至结束，SSE 持有到流释放；模型、count_tokens、Hello/bootstrap、预热、额度、测试、遥测、OAuth/401 共用门禁。作用域允许的原 sticky 账号暂停时返回维护，保留绑定；不跨号绕过。归属拒绝不应触发认证停用，RPM/并发/优先级等普通配置仍可热编辑。
- detach 在本地空闲、网关排空后取当前权威快照，镜像/解绑并发布完整 HOME，远端提交 local/ready 后完成。return 必须有原本地接管回执、原 ID 与代次；由本地所有者按需刷新后交回当前 HOME，绑定并恢复 AT-only，再 finish 为 gateway/ready。root profile 落后时不能作为当前 HOME 的来源证明。
- attach 仅在当前 RT 摘要及设备/账号证明一致时认可远端当前凭据；来源不明拒绝。成功本地强制重授权可记录无令牌证明：原环境/设备/身份、RT 摘要及本次登录冻结的 `session.version`；关联时再次按该版本核验当前 HOME 后使用 authorize。独立登录未具备设备来源时允许保存本地账号、清除旧证明；不能据此解除 retired/refresh_pending 或跳过后续关联校验。
- reauth 保留原绑定及原 `login:` 租约；凭据导入回执 `import_operation_id` 与所有权回执关联，确认实际新授权导入后才允许 finish。回执保存 source_phase，取消返回原阶段，原 reconcile 不能被取消变 ready。普通执行不得冒用登录来源；未完成原操作不能开启另一个交接。
- 受管刷新发送前落库待确认；确定结果保存且 HOME 收口后才恢复 ready。断线/解析失败/崩溃不重试未经确认的旧 RT。finish 已提交而响应丢失时查同操作回执；若同代已提交后又进入远端 reconcile，确认原绑定完成并保持 `gateway_refresh_pending`，允许明确重授权，仍不放开普通执行。
- retire 无需有效 RT：先暂停原网关账号再本地删除，保留原 ID/HOME/历史；本地 retired 继续关闭普通执行，明确且身份核验成功的本地重授权才可恢复。远端明确删除仍须原绑定完整缺失证明，不能将新目标 404 当成成功。
- 两角色镜像标签 `vibebench.credential-ownership-protocol=1`，联合清单 `credential_ownership_protocol:1`；已有任一所有权记录时，只读兼容检查拒绝旧清单回退。US 沿用现有资源参数、不做生产备份、不重新计算内存；最终同批发布及健康验收由部署流程承接。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 缺内部证明、协议不匹配、未知字段或代次/来源冲突 | 拒绝交接，原凭据与回执保持 |
| 网关账号由本地管理或维护中 | 上游准入 503，不发请求、不按认证失败停用 |
| 本地归属、绑定或固定环境不一致 | 拒绝执行并提示对账，不按空绑定降级 |
| 交接超时、写入失败或回包未知 | 保留持久待办和维护，查同操作回执恢复 |
| 历史 receipt 与当前代次不符 | 拒绝旧回执，不覆盖当前 RT、不释放维护 |
| 独立未知版本登录 / 受管恢复身份未知 | 本地保存但无关联证明 / 继续维护并明确报错 |
| 任一受管记录 + 旧版联合清单 | 部署兼容检查拒绝，不写数据库 |

### 5. Scenarios and Examples

- 正常：解绑原远端 7 → local/ready；本地连续轮换三次 → return 到原 7 → HOME 仅 AT → gateway/ready，设备、缓存、策略和历史保持。
- 边界：commit 已生效而 HTTP 回包丢失，重启读取 status 的同代回执，再补镜像/绑定/finish，不能重复上传历史 RT。
- 错误用法：用到期时间较大的副本覆盖远端，或本地强制授权按后来修改的默认 CLI 版本生成证明。正确处理：按所有者/回执确认来源，证明及重验均使用实际登录冻结版本；不能确认时保留维护或明确重授权。

### 6. Tests Required

- `test_credential_ownership` 与原 runtime/reauth/deleted-binding/publication/main 回归：六个落盘边界、回包丢失、当前 HOME 来源、坏记录隔离、未知刷新关闭、原绑定重授权、独立未知版本登录与冻结版本证明。
- Rust 归属/活动许可/401/调度回归及 `account_store_timestamp_test` 的 SQLite、独立 PostgreSQL `credential_ownership_storage` 合同：双栈迁移幂等、凭据/回执原子性、条件失配、删除清理、旧 receipt 拒绝与其他账号继续准入。
- `test_manage.py`：旧联合清单拒绝且数据库字节不变。`verify_stack.py --manifest <联合清单> --browser --ownership`、`--reauth`、`--deleted-binding`：真实 HTTP、两库、Chrome、Docker 和本地合成 TLS 刷新，暂停零上游、三次刷新交回原 ID、AT-only、故障对账及删除恢复。`--source-overlay` 仅本地 dirty 清单可用且记录只读覆盖摘要；生产仍用最终干净 CI。
- 真实第三方 OAuth 可用性不以合成结果代替；部署后只读验证镜像协议、状态和既有工作，不擅自发起真实授权、解绑或模型请求。

## Scenario: 固定 Docker、API/CLI 独立调度及证据恢复

### 1. Scope / Trigger

- 修改 `services/orchestrator/account_runtime.py`、v3 管理桥/租约/发送器、账号镜像及部署入口时适用。
- 本规范是 v3 的共同契约；旧版每 run 的 worker/sidecar 路径继续兼容。被动额度算法遵循 [数据库规范](database-guidelines.md)，抓包限频遵循 [官方协议抓包规范](../../platform/deploy/official-protocol-capture.md)。
- 固定环境解决状态和生命周期归属；CLI 与 Rust 发送器使用不同客户端，不能推断完整指纹相同或保证不被限制。

### 2. Signatures

```text
account_environments(
  environment_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
  account_id INTEGER UNIQUE, fingerprint_json TEXT NOT NULL,
  generation INTEGER NOT NULL DEFAULT 0, container_id TEXT,
  state TEXT NOT NULL DEFAULT 'stopped')
runs: environment_id TEXT, environment_generation INTEGER,
      execution_source TEXT, runtime_release TEXT

GET  /admin/runtime/accounts/:id/config
GET  /admin/runtime/accounts/:id/lease
POST /admin/runtime/accounts/:id/lease
GET  /internal/v3/transport/{account_id}
POST /internal/v3/quiesce/{account_id}
GET  /api/environments
POST /api/environments/{environment_id}/maintenance

AccountRuntime.execution_flows(account: dict, source: str, flows: Path) -> Path
AccountRuntime.start_run(account, task, run_id, worker_env, quota_env) -> tuple[str, str]
AccountRuntime.execution_environment(row: dict) -> dict[str, str]
V3_DEFAULT_TIMEZONE = "America/Los_Angeles"
AccountRuntime.cleanup(container_id: str) -> None
AccountRuntime.environment_jobs(environment_id: str) -> list[dict]
AccountRuntime.run_session_path(run_id: str) -> Path
AccountRuntime.reprofile_blocker(row: dict) -> str | None
derive_v3_fingerprint(timezone: str | None = None) -> dict[str, object]
NetworkInspectionMode = "passthrough" | "quota" | "capture"
/run/v3/context.json -> {NETWORK_INSPECTION_MODE, QUOTA_SOURCE, ...}
/run/v3/context-ack.json -> {NETWORK_INSPECTION_MODE, QUOTA_SOURCE, process}
```

管理租约输入为 `operation: string`、`owner: string`、`generation: string | null`；操作为 `prepare-cli-shared`、`prepare-cli`、`prepare`、`claim`、`heartbeat`、`fence`、`release`。查询返回 `lease,holders,cli_capacity,active,waiting,importing`；`lease` 保留为旧占用提示，新调用按 `holders` 核对具体 owner／generation。租约包含 `owner,generation,expires_at,phase,exclusive,shared_cli`，TTL 为 30 秒。持久状态 schema 2 保存全部 holder，旧单租约保守读入；旧记录缺少 `exclusive` 时默认 `true`。fence 与在途导入保护见下方重授权场景。

发送绑定 `TransportBinding`：`account_id: i64`、`environment_id: string`、`generation: u64`、`endpoint: string`、`secret: string`、`release_id: string`。`PreparedRequest` 包含 `request_id`（UUID）、`deadline_unix_ms`、`method`、`target_url`、有序 `headers`、`preserve_header_casing` 和网关冻结的 `tls_profile` 注册ID；最终 body 独立传原始字节。sender不自行重选版本，缺字段沿历史兼容默认，显式未知ID在上游提交前拒绝；完整选择、连接池和错误行为见[版本TLS合同](../../gateway/protocol/claude-code-profile-upgrade.md#scenario-tls-画像版本绑定与冻结传输)。秘密只在服务间传递。

```text
scripts/flower2api-stack build --release <唯一批次> --manifest <新清单>
scripts/flower2api-stack publish --manifest <本地清单> --output <新发布清单> --bundle <新镜像包>
scripts/flower2api-stack pull --manifest <发布清单>
scripts/flower2api-stack load --manifest <发布清单> --bundle <同批镜像包>
scripts/flower2api-stack up --env <独立配置> --manifest <联合清单>
scripts/flower2api-stack status --env <独立配置>
scripts/flower2api-stack stop --env <独立配置>
```

配置入口为 `deploy/flower2api/example.env`，实际参数以 `manage.py --help` 为准。

### 3. Contracts

**数据与凭据**：cc2api 拥有绑定账号、代理、OAuth 和唯一刷新权；bench 拥有环境、任务、持久目录及证据。两侧通过受控 API 协作。绑定 CLI HOME 仅发布 AT，删除 RT；401 沿用 managed 刷新流程。身份导入接受 Recorder 实际请求观察，或经指定官方版本实测验证的本地字段映射，并核对登录账号归属；来源未知或冲突时阻止同步。当前 2.1.293 的 device_id 来自固定 HOME 的 `.claude.json.userID`，不能用 Linux machine-id 或独立 machineID 替代，详见下方身份同步场景。

**环境**：每账号一个固定 account 容器、完整 `/home/node` 和版本缓存。新环境的 `fingerprint_json.profile_version=2`；hostname 为独立随机 12 位小写十六进制，machine-id 为独立随机 32 位小写十六进制，MAC 为独立随机的本地管理单播地址。时区来自账号显式配置，locale 与地区成组持久化；未配置的新环境使用 `America/Los_Angeles` + `en_US.UTF-8`，IANA 时区自动处理夏令时；已有 UTC 或其它画像保持，generation=0 的已登记画像也不重算。环境 ID、profile、RAM/swap 不随 run、改名、停止唤醒或容器重建重算；旧记录缺 `profile_version` 时保持 legacy。重建可换 container ID，但保留 HOME 和环境身份。新建容器 DNS 为 `flower2api-<deployment_sha256前12位>-<environment_id>`；网关精确兼容历史 `v3-<deployment_sha256前12位>-account-<environment_id>`。sender 后缀完整名称最多63字节，完整归属由产品/部署/角色/环境 labels 校验。名称切换、跨仓库重建与首次失败恢复见[平台在线更新合同](../../platform/deploy/platform-online-update.md#scenario-flower2api-单部署名称切换与完整快照)。只按本部署精确标签维护，不用宽前缀或 prune。

**调度**：

- `prepare-cli-shared` 用于布局 2 的普通 Tasks／项目计划，账号至多两个 CLI holder，API 可同时入场。`PER_ACCOUNT_CONCURRENCY` 默认 2，合法较低配置继续限制 Tasks 与 Projects 总容量；API 容量独立。`prepare-cli` 仍为 CLI 专用排他，用于养号、抓包和续聊等既有操作，阻止其他 CLI 但允许 API；不能把旧调用自动解释成多 CLI。养号仍让位于正式工作。
- `prepare` 创建排他维护门禁：重授权、代理修改、绑定切换、停止、重建检查或排空 API。配置 quiesce 验证排他 owner/generation、API 活动数和本环境 CLI/发送器状态。
- CLI 安装在认领后执行，不持有环境生命周期锁；API 就绪不安装 CLI。API 保留 weighted slot/FIFO 与 SSE permit，精确 Messages 的稳定绑定、当前 RPM 间隔准入及可视化遵守 [v3 API 调度合同](../../gateway/backend/service-architecture.md#scenario-v3-api-稳定会话智能准入与平滑发送)；CLI 不共享该发送预算。OAuth resolve 不等待 CLI 租约。
- 普通 `_cli_setup()` 的串行交接检查、画像探针与 `claim()` 共用同一个环境锁，评审不能在检查与认领之间停止 CLI；安装版本时释放该锁，由已认领作业阻止评审。坏画像仍在认领前拒绝，健康 API 保留。
- driver 和续聊 wrapper 使用 `setsid --wait`，Docker exec 生命周期必须跟随实际进程。tmux 登录 shell 显式保留选定 CLI 缓存 PATH。
- v3 生成 driver 时去除内部时间戳 Stop hook；UID1000 无权写 root 私有 runtime 树，该信号也没有消费者。完成仍由真实主会话 JSONL 的最新稳定最终 assistant 文本判定；配置业务补充时还需 [阶段契约](topic-prompt-contract.md#scenario-自包含题库与冻结的有限业务补充) 核验全部选定轮次，不需要放宽控制目录权限。原 hooks 在作业收口时按快照恢复。
- `_cli_setup()` 在已认领的环境锁内合并固定 HOME 的 `settings.json.env.DISABLE_AUTOUPDATER="1"`、画像的 TZ/LANG/LC_ALL 及下文“官方 CLI 遥测部署策略”，保留其他 env/model/hooks 并发布为 UID1000 文件。普通任务、抓包、登录和续聊的 CLI 准备共用此入口；CLI 版本继续由管理端精确缓存与全局运行配置选择。
- 实际任务 driver 在合并 worker_env 后覆盖画像的 TZ/LANG/LC_ALL；登录 tmux 命令、短命令、OAuth 探测和续聊 PTY 使用同源值。账号列表 `effective_timezone` 优先只读既有画像，否则返回显式配置或新默认；GET 不创建环境，不再把旧账号名派生值当作 v3 有效设置。
- 正式普通任务通过 `CLAUDE_EXECUTION_SETTINGS` 和 `--settings` 使用每执行独立的模型／effort／hooks／`v3-cli-quota` 状态栏覆盖，原用户状态栏仍接收相同 stdin；不能来回改写共享 HOME 的运行态设置。原排他入口继续保存并按本代归属恢复字段。采集只消费官方 rate_limits 和主会话响应，不新增 usage／模型请求，详见 [额度契约](database-guidelines.md)。
- 普通并行作业以环境＋source 登记，私有 `runtime/executions/<source摘要>.json` 保存 schema 2、租约及监督器证明；旧排他入口保留 `runtime/execution.json`。启动监督器是 child subreaper，收养 double-fork／setsid 后代；管理端核对 source、容器、PID／内核启动时刻后才发出启动许可。`v3-cli-control inspect/freeze/resume/stop-job --source <source> --pid <pid> --started <tick>` 仅操作匹配树。
- 清理使用完整 token；存在多个作业时拒绝裸 container ID。并行入口不按整个 UID 清理、不在结束一个作业时重置兄弟网络／设置。旧 token 不能触及新作业，暂停验收一个作业时兄弟继续。不通过停止整个容器清理普通 CLI。
- 清理／心跳／重启逐个对账全部执行，失败进入 `cli_reconcile`，阻止下一 CLI、保留健康 API；未知、损坏或链接登记不能视为空闲。维护、登录、重授权、删除和驱逐检查全部作业。公共网络或发送器故障仍关闭容器，CLI 专用 Recorder 故障仅隔离 CLI。

**CLI 网络模式**：CLI 始终经 `tun0 -> hev-socks5-tunnel -> 127.0.0.1:8080` 使用账号代理。普通任务、养号、登录/重授权、额度查询和未绑定账号 OAuth 刷新选择 `passthrough`，本地 relay 只完成 SOCKS5 入站与 HTTP CONNECT/SOCKS5 上游握手并复制原始字节，不启动 mitmproxy，也不注入 MITM CA。显式完整抓包选择 `capture`；`quota` 只保留历史格式兼容，v3 不再用模型请求补样。usage 查询复用原生监听并解析返回 JSON，不需要 MITM。模式切换在 `network.lock` 内先核对并定向收口旧 PID，再写原子 ACK；调度器必须逐字段匹配 mode、source、process 才能启动 CLI。代理缺失、认证失败、旧监听未知、ACK 不符或监听退出都失败关闭，不回退直连；relay 的共享空闲计时由任一方向新字节重置。

普通并行作业复用已核验 PID／启动时刻及 ACK 的 passthrough relay；兄弟存活时不能重启监听。每 source 的额度与采集文件仍独立；结束一个执行，既有 TLS 长连接和另一个执行必须继续。capture 切换使用 CLI 专用排他。

**HTTPS 与证据**：管理端完成选号、改写、重试和响应分类，目标账号内发送器复用现有 HTTP/TLS 实现实际建立上游连接。每账号独立进程/连接池及代理，API 不经 CLI 网络监听。普通 `passthrough` 不生成 HTTP 明文、stats 或 flow；`quota/capture` 才显式信任当前 CA 并由 Recorder 产生对应证据。绑定、批次、目标、截止时间和秘密不符时拒绝；桥接失败无直连回退，提交不确定不能盲重发。API 被动观察单独写 `flows/api/observations.jsonl`，不混入 run 统计。

```text
bench/environments/<environment_id>/
  home/                              完整 CLI HOME
    .claude/projects/<opaque>/       主 session；不进入项目树
  cli/<version>/                     版本安装缓存
  projects/project-<12位摘要>/       Claude 可见任务 cwd
  workspaces/<run_id> -> projects/... 宿主兼容入口
  flows/group-<relative_path_hash>/
    executions/<source_hash>/        stats/HTTP/index/原生 flow/被动额度
  controls/<source_hash>/             独立只读暂停信号
  runtime/runs/<run_id>/             status/transcript/baseline/followups/刷新控制
  runtime/                           作业脚本/PID/tmux、上下文/ACK、执行证明
bench/flows/<account>/<task>/<run>/    固定兼容链接
```

`execution_flows()` 在账号锁内固定兼容入口；run 与续聊各有自己的证据组。恢复原 run/session/workspace，仅换 source 子目录；QuotaGuard 登记本代实际观察文件，Recorder 使用同一目录。真实 cwd 和 `.claude/projects` 键只能使用 `project-<摘要>`，原 run/environment ID、`.bench-*`、`.claude-home`、cc2api 刷新标记和 Stop hook 控制文件不能进入 Claude 可见项目树；旧系统生成的已知控制文件须定向迁移到 runtime，不能删除未知用户文件。v3 Runner 不再创建 per-run `.claude-home`；准备项目时仅用 rmdir 清理该非链接空目录，既有可核对 session 链接按原归属清理，非空／未知链接及其链接父目录保留。旧 runner 的 per-run HOME 保持。run 统计读取平铺历史及各 run 执行、排除续聊/API并去重路径；抓包索引和文件列表聚合各代及续聊。原生 flow 不覆盖，历史平铺文件保留。跨目录链接拒绝，未部署的旧 v3 原型 source 链接不自动接管。

`_project_view()` 在启动 CLI 前给固定 HOME 的 `.claude.json.projects[cwd]` 设置 `hasTrustDialogAccepted=true`，仅限当前系统专属物理项目目录；原子合并并保留 userID、OAuth 身份、其他项目及未知设置。持久 HOME 不走旧 worker 的顶层配置初始化，需显式保存本项目的确认标记。未登录或异常授权仍按原认证入口处理，不信任任意外部目录。

**显式画像校正**：`maintenance(..., "reprofile")` 只接受未绑定 cc2api、无 task/run/identity/草稿/提交/活动作业、容器已停止的 legacy 正式环境。操作保留账号/HOME/代理/资源预算，清理旧容器网络与 CA 产物，生成一次 profile v2 并回到 stopped，保留原登录凭据；不因环境字段变化强制重授权。启动时原 `profile_reauth` 迁回正常生命周期；原 `profile_reauth_reconcile` 的真实执行/提交故障仍按 reconcile 隔离。profile v2 永久拒绝再次 reprofile，真实认证失败才要求重新授权。

**部署**：两个最终镜像 control/account；control 按 gateway/orchestrator 两个角色启动，当前隔离布局的 N 个账号固定角色共 3N+2 个容器，评审另有受同账号 CLI 互斥门禁约束的临时子容器；只有 orchestrator 挂 Docker socket。CLI 为 UID1000、无网络能力并禁止提权，服务秘密/控制目录不对项目写入开放。root 管理的 `v3-account-init`、`v3-network-context`、`v3-cli-version`、`v3-passthrough` 和 `/sidecar` 为 0700；本地 CLI 额度采集 `v3-cli-quota` 为 0755，中文源码注释不必删除。

**资源**：`resource_budget.account_limits(memory: str, swap: str = "0") -> tuple[int, int]` 共用于预检与账号创建；返回 RAM 字节数和 RAM＋swap 总字节数。`V3_ACCOUNT_MEMORY` 支持正整数 m/g，默认 4g；`V3_ACCOUNT_SWAP` 是额外 swap，默认 0，仅接受 0 或正整数 m/g，不接受 -1/无限额。首次保存 `fingerprint_json.mem/swap`；旧缺 swap 字段为 0，改全局配置不重算旧身份或预算。Compose 必须显式传递两参数。

预检分别比较 `MemAvailable` 与 `SwapFree`：RAM 至少为活跃上限×账号 RAM＋可配置 `V3_MEMORY_HEADROOM_BYTES`（默认 256 MiB），显式更高的 `V3_MIN_FREE_MEMORY_BYTES` 优先；swap 足够覆盖活跃账号额外额度，且 Docker `SwapLimit` 为 true。不能以 swap 抵扣 RAM 余量；已有环境保存的 RAM/swap 超过配置时拒绝启动，禁止下调配置掩盖未来唤醒预算。1536m RAM＋2048m swap、活跃 1 对应 Docker Memory=1610612736、MemorySwap=3758096384，预检要求约 1.75 GiB 可用 RAM与2 GiB空闲 swap；默认4g需4.25 GiB RAM。这是额度边界，真实 CLI 峰值另行验证。

清单记录 `schema=3`、`bridge_protocol=1`、`layout_version=1`、默认 CLI、release、父/子仓 revision、dirty 标记、冻结内容 SHA256 及两个 image ID/平台。`images[role].digest` 保留构建机本地 Docker Id；containerd 可用 OCI 索引作为 Id，所以另保存 `config_digest`（docker save 中原始配置字节 SHA256），发布后 `registry_digest` 才是仓库 manifest/索引 digest。换 daemon 时只接受清单固定的配置或 OCI 根，角色/批次/提交/平台仍检查，不能因 ID 语义不同放弃核对。构建先冻结源码，标签/清单不能覆盖。启动检查清单组合、实际镜像 labels、宿主发布端口、名称/网络/挂载 realpath、数据归属及资源预算。重复 up 只复用本部署 gateway 的精确 5674 映射，其它进程和外部容器占用仍拒绝。 端口探测启用 `SO_REUSEADDR`，已关闭连接的 `TIME_WAIT` 不应延迟启动；真实 TCP 监听及外部 Docker NAT 发布仍必须拒绝，不能通过固定等待几十秒掩盖误判。

**发布**：`.github/workflows/v3-build.yml` 执行候选构建。正式发布通过 `v3-release.yml` 的 v3/flower2api 手动入口及明确 publish 标记，联合 build 后使用 GITHUB_TOKEN（contents:write、packages:write）登录 GHCR；两个包为 `ghcr.io/silentflower/flower2api-{control,account}`，标签 `v3-ci-<run_id>-<run_attempt>`，不写 latest/旧包。publish 校验 Action 的仓库、父提交与 run/attempt、干净构建来源和全新输出，独占 `.started` 标记禁止同次重试；失败保留现场，新 attempt 才重跑，不把仓库 denied 当成“未存在”。两件成功、仓库 digest 可核对且镜像包成功才写最终清单；原构建清单不改。

artifact `v3-release-<run_id>-<run_attempt>` 保存发布清单与同批 gzip 镜像包，保留14天；`bundle={name,sha256,size}` 核对完整包。pull 按 registry_digest 下载再建立受控标签，load 先核对名称/大小/SHA256；现有本地标签若镜像内容不同都拒绝覆盖。包不含部署配置/账号数据或 registry 登录资料；首次私有包不能匿名 pull 时使用同批 artifact，不在服务器保存 PAT或自动改变包可见性。

关键配置：`V3_DEPLOYMENT_ID`、`V3_RELEASE`、`V3_CONTROL_IMAGE`、`V3_ACCOUNT_IMAGE`、`V3_DATA_ROOT`、`V3_INTERNAL_TOKEN`、`V3_SESSION_SECRET`、`V3_ADMIN_PASSWORD`；服务间使用 `V3_RUNTIME_URL`、`V3_NETWORK`、`V3_LEASE_DIR`。默认 CLI 为 `2.1.293`，`V3_CLI_VERSION`、页面覆盖及已有 Run 冻结版本保持原优先级；不覆写用户显式版本。默认宿主端口 `18080`、活跃账号上限 1，与账号内 CLI 并发分别表达；实际冲突拒绝，不自动停旧服务。内存/CPU、空闲停机与日志轮转由 v3 配置控制。

停机 backup 用 lstat 排除不可复制的 Unix socket，保留普通文件及符号链接和 SQLite backup API 快照；tmux 等连接由新进程重建，不把运行 socket 当作持久数据，也不删除源 socket。真实 socket、WAL 事务、普通文件和符号链接须一并回归。

`backup --backup-dir <全新绝对目录>` 默认精简，`--full` 显式完整；独立恢复验证与持久完成标记成功后，才轮换同父目录、同部署、同数据根的旧完整或精简备份，仅留本次一份。备份、维护及 `up` 共享非阻塞磁盘锁；失败保留原恢复点，轮换失败保留新副本并报错。排除证明、恢复清单与维护边界见下方“精简备份与不可变制品维护”场景，不清理其他路径或 Docker 镜像。

统一 Vue 后台通过受鉴权的 `/runtime/` 桥访问 bench，保留 HTTP/SSE/WS。浏览器桥限定路径/方法，拒绝内部和编码绕过；v3 Cookie 名和 scope 独立，退出撤销服务端会话及旧票据。终端资源打包到镜像，不依赖运行时 CDN。

环境页固定资源 `GET|HEAD /runtime/environments.js`、`GET|HEAD /runtime/environments.css` 必须与 `apps/legacy-web/index.html` 的引用同步进入管理桥精确白名单，查询参数随原 URI 转发。资源沿用原 v3 会话鉴权，写方法、近似路径、编码及点段路径继续拒绝。新增本地脚本或样式时同时核对镜像分发和浏览器桥准入。

**管理页面布局**：环境由`RuntimeEnvironments.vue`直接渲染，任务由`TasksWorkspace.vue`挂载编译的执行模块；主文档承担页面滚动，详情工作区独立滚动。侧栏固定到视口，宽屏内容铺满。原任务明暗偏好、执行生命周期与独立`/runtime/`地址保留。具体组件和资源清理合同见web/frontend/ui-guidelines.md。

bench 导航项不拆分中英文标签。宽屏顶部三列使用 `max-content minmax(0, 1fr) max-content`，品牌和状态栏保留实际宽度；中间 `.tabs` 设置 `min-width:0` 并允许整项换行，不能让不换行的副标题溢入导航列。状态栏限制 `max-width:100%` 并允许控件换行，避免极窄屏横向溢出。

宽度不超过 1440px 时导航独立一行，不超过 920px 时顶部区域单列、隐藏品牌副说明。导航回归覆盖 320～2048px、明暗主题及登录状态，包含 1441／1536／1640px，核对品牌、六个导航项和状态控件均无重叠或横向溢出。工程迭代统一入口及账号/空间 URL 遵循 [导航状态契约](../../legacy-web/frontend/state-management.md#scenario-工程迭代空间与账号-url-状态)。表格保持水平滚动和内容自适应高度，超出 1px 的装饰线不能触发纵向滚动条。静态 CSS 更新时同步 index.html 的样式版本参数，避免缓存保留旧布局。

停机/备份/离线导入只作用于本部署，保留持久数据。离线导入默认 dry-run，来源幂等，拒绝凭据，账号停用、旧活动 run 停止，不恢复旧调度；真实接管不能让旧、新系统同时刷新同一账号。

当前 `us` 环境（`/opt/vibebench-v3-us/v3.env`）的用户明确运维选择：每次部署不做备份、不计算内存，沿用现有资源参数，不再据内存预检暂停部署。该选择不改变 `manage.py` 通用默认或其他部署的规则；本环境交付流程仍核对同批镜像、数据归属、端口、在途任务、身份和严格释放。不得为满足默认预算而擅自下调现有配置。

每次 v3 部署成功并完成健康验收后，必须执行[旧镜像定向回收](#scenario-v3-部署成功后的旧镜像回收)，再复核磁盘与服务状态；不能以 `pull/load`、`up` 成功代替部署收尾。保留当前批次、最近两个完整历史批次及所有容器引用的镜像。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 新环境未指定时区 / 已保存 UTC 画像 | 洛杉矶＋美国英语 UTF-8 / 沿用 UTC，展示与执行一致 |
| worker_env 或 HOME settings.env 含旧 ja_JP 值 | 按已固化画像覆盖 TZ/LANG/LC_ALL，其他 env 保持 |
| `.claude-home` 空目录 / 非空或未知链接 | 只移除空目录 / 保留内容与链接 |
| UID1000 读取管理脚本 / 执行 collector | 拒绝读取 / 允许本地执行 |
| API 活动或排队，普通 CLI 认领 | 共享认领，不关闭 API 入场 |
| 两个普通 CLI 同账号竞争／第三个 CLI | 真实容量允许时两个各持独立 holder／第三个等待；低优先级养号顺延 |
| 普通并行作业与旧排他 CLI／维护竞争 | CLI 专用排他拒绝其他 CLI；维护继续排空 API 和全部 CLI |
| 活动 API/CLI，空闲维护 | 拒绝，不中断已接受工作 |
| 旧 token/租约代次清理 | 不清理新作业 |
| 共享租约过期/服务重启 | 保留 API，先确认旧 CLI 收口，再允许下一 CLI |
| Recorder 撤销失败 | CLI 隔离，禁止下一 CLI；公共网络健康时 API 保留 |
| 普通任务、正常养号、登录或未绑定 OAuth 刷新 | `passthrough`，无 mitmproxy/CA 环境；代理失败时不直连 |
| 普通任务、养号或 usage 查询 / 显式完整抓包 | passthrough 原生 TLS / capture；usage 查询不切换监听 |
| relay 长连接持续单向传输 / 双向静默 | 任一方向字节重置共享空闲计时 / 达到期限后关闭 |
| 同 run/续聊第二代 | 固定入口、新观察游标/flow，旧证据不变 |
| legacy 环境不满足校正条件或已经 profile v2 | 拒绝 reprofile，不旋转任何身份字段 |
| reprofile 成功 / 历史画像门禁 / 真正收口失败 | stopped 保留凭据 / 迁回正常生命周期 / reconcile 保留执行证据 |
| Claude 可见项目树出现系统控制文件或原始 run ID | 验证失败；控制文件迁入 runtime，session 留在固定 HOME |
| 错误环境绑定/镜像批次/秘密/目标 | 拒绝发送，不直连、不重放 |
| 宿主端口/名称/挂载或数据归属冲突 | 启动前拒绝，不操作旧资源 |
| 浏览器内部路径/退出后 Cookie 或票据 | 拒绝，服务秘密不下发 |
| RAM 不足、swap 不足/daemon 不支持、已有固化预算更高 | 拒绝启动，不改旧账号预算或旧服务 |
| 非当前 v3 Action、dirty 来源、同 attempt 或已有输出 | 拒绝发布，不覆盖批次 |
| 任一推送、仓库 digest 或镜像包失败 | 无完整发布清单，已推镜像保留 |
| 包名称/大小/SHA256、镜像角色/ID/平台不符 | 拒绝交付；本地同批标签不覆盖 |
| 新备份失败／旧目录无完整同源归属 | 保留旧恢复点／该目录不参与自动轮换 |
| 桌面或窄屏打开环境与任务 | 原生页面填满侧栏右侧，标签保持横排，主页面滚动且没有iframe |
| 环境页 HTML/API 为 200，脚本或样式为 404 | 页面验收失败，核对固定静态资源白名单及实际原生路由模块初始化 |

### 5. Scenarios and Examples

- 正常：首次未指定时区使用洛杉矶；改名或重建后沿用已保存值，旧 worker_env 不影响实际 locale。
- 错误用法：只设置容器默认 LANG，却在 exec 注入旧日文 LANG/LC_ALL。正确做法：所有实际 CLI 入口与 HOME settings.env 从画像同源覆盖。
- 正常：API SSE 运行时启动养号 CLI，取消 CLI 后继续收到新 API 数据；同账号第二个 CLI 仍需等待。
- 正常：同账号两个普通 Tasks 或项目计划独立运行，冻结／停止 A 后 B 和既有 API SSE 继续；默认账号内 CLI 容量为 2，不增加原资源预算。
- 错误用法：只扩大信号量，仍修改共享 statusLine、按 UID 杀进程或重启 relay。正确做法：每执行独立 settings／租约／监督器及清理，复用已核验的原生透传监听。
- 正常：普通任务和可信额度养号经 HTTP CONNECT/SOCKS5 账号代理传递原始 TLS 字节，项目 cwd 只含 `project-<摘要>`；显式抓包切到 capture 后仍产生独立 flow。
- 基础/历史：停止唤醒或镜像重建保留 HOME、环境 ID 和 machine-id；平铺历史统计/抓包仍可读取，空环境返回可展示状态。
- 基础/历史：legacy 画像继续固定；满足全部条件时用户显式 reprofile 一次，HOME 与原凭据保留，不强制重新授权，profile v2 不可再次旋转。
- 错误用法：所有 CLI 都经过 Recorder，或正常养号因为 `QUOTA_WARMUP=1` 总是启用 MITM。正确做法：日常 CLI/usage 使用 passthrough，只有显式 capture 注入 CA；阈值数据由正式响应及 CLI 本地状态栏被动更新，usage 仅保留显式手动查询。
- 错误用法：用 `/workspaces/<run_id>` 作为容器 cwd，或借兼容链接把 `.claude-home` 写进项目。正确做法：项目、session、控制产物分别归属 projects、HOME 和 runtime，兼容入口只供宿主读取。
- 错误用法：`run:<rid>:1` 把原 run 链接改到新 source 目录，或者复用旧 `capture.flow`，造成冲突/证据覆盖。正确做法：固定证据组、每代独立目录，游标与 Recorder 共用实际路径，读取端汇总。
- 错误用法：看到 Docker exec 已创建就算 CLI 正在运行，或用 container.wait 判 run 完成。正确做法：`setsid --wait` 并确认 exec/tmux 实际运行，终态由本执行结果判断。
- 错误用法：只直调 sender 就宣称网关链路通过。正确做法：真实 gateway 入口经短 DNS 绑定到账号 sender，并验证错误绑定拒绝且无重放。
- 正常：同一 Action 发布两镜像，服务器按仓库 digest 拉取或加载校验过的同批包，再 check/up；空数据库只启动两管理服务。
- 基础/历史：旧环境没有 swap 字段，继续禁用；Docker 存储实现更换后本地 ID可以不同，但固定 config_digest/registry_digest 与平台仍能核对。
- 错误用法：将 memswap_limit 设成 RAM值却声称容器可用宿主 swap，或用 SwapFree 抵扣 RAM 预算。正确做法：总限额为RAM＋额外swap，预检分别比较两种余量。
- 错误用法：把本地 Docker Id 当作仓库 digest，或只成功推一件就生成可部署清单。正确做法：三种哈希明确区分，两个角色都成功后才保存完整交付结果。
- 错误用法：把 bench 放进网关的 max-width 容器，叠加统计卡片和 iframe 的 `100vh - 100px` 高度。正确做法：原生环境和任务路由直接填充侧栏右侧，页面与详情各自拥有滚动。
- 错误用法：新增 `environments.js/css` 后，仅验证 HTML 和环境 API 返回 200。正确做法：核对两个资源成功加载，并分别验证原生Vue环境组件与独立兼容页的脚本、样式和真实按钮。

### 6. Tests Required

- Rust `cargo fmt --check && cargo test`：画像/改写、weighted FIFO/RPM、共享/排他租约、旧记录/过期/重启、绑定校验、原始字节/有序头/SSE取消、不重放；回环临时 CA 验证 HTTPS 正常响应及错误证书/主机名拒绝。测试 CA 不进入正式客户端。
- `runtime_bridge::tests::environment_assets_are_exact_and_read_only` 覆盖资源 GET/HEAD、写方法和近似／编码路径拒绝；`verify_native_environments.py`验证主路由，独立兼容页核对脚本函数和CSS规则，缺失资源必须使浏览器验收失败。
- Python orchestrator 回归：原快照与 session 恢复、旧 token/绑定保护、并行与安装续租、证据/游标分代、统计不重复、错误链接拒绝、鉴权和永久额度门禁。
- `images/account/test_passthrough.py` 与 network-context 回归：HTTP CONNECT、SOCKS5/H 认证、IPv4/IPv6/域名、字节保真、代理失败无直连、静默关闭、跨空闲窗口单向活动，以及 PID/ACK/mode/source 归属。
- 环境回归：默认 LA/en_US、显式 UTC/Tokyo、既有画像和页面 GET 不分配；真实 Runner → AccountRuntime 启动、HOME settings.env、登录与续聊使用同源值；实际 UID1000 locale/date/ls 符合设置。
- 文件权限回归：UID1000 不能读取四个 root 脚本及 /sidecar，仍能执行 collector；root 初始化、版本准备、监听切换与 Recorder 保持；空目录清理不删除非空目录、未知链接或主 session。
- profile/project 回归：独立随机画像、时区-locale 配对、重建固定、legacy 不自动迁移、reprofile 全部前置条件/历史门禁迁移/凭据保留/成功后不可重复；容器内项目顶层只出现匿名目录，项目内部没有 `.bench-*`、`.claude-home`、刷新控制或系统 Stop hook。
- 目录信任回归：实际 `_project_view()` 写入当前 cwd 的信任标记，同时原账号 userID/OAuth 和其他项目配置保持；生产验收必须观察真实会话响应或工具调用，不能只凭 runs.status=running 宣称题目已执行。
- Stop hook 回归：调用实际 start_run 生成 driver，执行其中 Node 设置片段，断言不注入 Stop；执行生成脚本的完成判定函数，在没有 Stop 信号文件时仍识别最终 assistant。保留 shell 语法校验，不能靠给 runtime 树开放写权限消除错误。
- Recorder 与部署回归：请求归属冻结、ACK/身份、冲突预检、准确资源归属、停机、备份和导入幂等。
- 并行回归：`test_account_runtime.py` 的两 holder／独立 settings／全部登记恢复／旧 token 保护，Rust 全量覆盖共享容量 2、旧 CLI 排他、维护和持久 holder；`verify_cli_jobs.py` 在真实 UID1000 容器核验脱离进程组、过期 PID 证明及兄弟保护。
- 固定 CLI 参数验证：官方 2.1.293 以本地合成 SSE、无外网 Docker 验证 `--settings`、指定 session、原状态栏和零 usage；不能以本机其它版本 help 或合成回复称为真实模型效果。
- `test_manage.py`：最近一份备份轮换、失败保留、外部署／链接目录不删除、轮换失败保留新备份；`verify_project_scheduling.py` 核对 Tasks 并行与长连接跨补位／收口、relay PID／启动时刻不变。
- 资源/发布回归：1536m＋2048m 实际 Docker 限额，默认/旧缺字段、非法无限值、RAM/swap不足、已固化预算拒绝；当前 Action 来源/attempt、第一/第二件推送失败无完整清单、错误digest/包拒绝、本地标签不覆盖，跨 store ID相同配置可核对。
- actionlint 核对 ref、权限与 artifact；实际本地 registry 的 push/pull、归档 config 哈希以及双镜像 save/load 核对。CI/GHCR发布结果与指定服务器实时预检/健康/旧服务不变在发布后验收，不能以本地替身称其已完成。
- 联合重建后串行跑 `run_local_verification.py --manifest ...`、`verify_stack.py --manifest ... --browser`：实际运行中的合成 CLI、同 run 第二代、API 长流与新增 API、CLI 取消/重启/Recorder故障保留 API、tmux 重连、两账号传输隔离、旧哨兵及数据库不变。
- 校验冻结源码哈希和最终输入一致，标明平台、失败日志、测试替身及未执行项。真实 CLI OAuth/实际主会话/额度恢复、公网全链路与同宿主压力由隔离部署负责人后续验证；arm64 发布前在对应环境验证。不能用本地 mock 宣称这些真实验收已完成。
- 只改管理页面布局时运行`npm --prefix apps/web run build`，浏览器覆盖1541/1280/920/390px与任务明暗主题。验证侧栏占位、无iframe、无横向溢出、六模块导航、原生环境分区、弹窗和离页清理，切回账号页保持普通布局。

## Scenario: v3 关联重授权提交与恢复

### 1. Scope / Trigger

- 修改绑定账号的 CLI 登录、凭据镜像、取消、启动对账及环境页维护时适用。cc2api 导入 DTO/回执/条件写入以 [服务契约](../../gateway/backend/service-architecture.md#scenario-v3-重授权凭据导入与迟到回包保护) 为准；页面连接以 [终端生命周期](../../legacy-web/frontend/hook-guidelines.md#scenario-v3-登录终端重连与授权链接) 为准。

### 2. Signatures

```text
POST   /api/accounts/login/start
GET    /api/accounts/login/{sid}/status
POST   /api/accounts/login/{sid}/commit
DELETE /api/accounts/login/{sid}
WS     /api/accounts/login/ws/{sid}
POST   /api/environments/{environment_id}/maintenance
AccountRuntime.ensure(account, version=None, allow_inactive_login=False, allow_login_recovery=False)
AccountRuntime.login_commit_context(session) -> dict
AccountRuntime.finish_bound_login(record: dict, snapshot: dict) -> None
LoginManager.commit_bound(session: LoginSession) -> dict
LoginManager.cleanup_reconciled(environment_id: str) -> None
```

### 3. Contracts

- 仅 v3 且明确 `force_reauth:true` 的原绑定 OAuth 账号进入重授权。该路径才允许读取非 active 配置；普通执行仍拒绝。代理沿用 cc2api，时区沿用原账号；固定容器、环境 ID、userID 与固化设备字段保留。活动 run（含 quota_wait）、续聊或其它登录拒绝开始；现有 API 等待排空，不强行截断。
- start 返回 `session_id/ws_path/name/has_sidecar/reconnectable/cc2api_account_id`。LoginSession 记录原 bench ID、绑定 ID、邮箱/UUID/组织、环境/代次、租约、phase 与提交操作。phase 为 authorizing/submitting/committed/cancelled；成功结果无 AT/RT。
- force 在原 HOME 下的 `.v3-login/<sid>` 暂存登录；复制设备配置/设置，去掉旧 oauthAccount，不复制旧 credentials。新身份必须来自 CLI 登录产物和 auth status，不从旧配置补齐 UUID/组织。
- 提交先在 owner 锁内重读原绑定/活动状态，再按 owner → profile 顺序镜像。环境页维护使用 owner → profile → environment 顺序；`cleanup_reconciled` 自行取得非重入 owner 锁，必须在维护外层锁释放后调用。HTTP 在 `_db_lock` 外。
- HTTP 导入之前原子写 root 私有 `runtime/login-commit.json`（0600），保存 sid、name、两端账号 ID、操作 ID、环境/代次、租约、phase、auth_method 与已验证身份；不保存令牌、授权码或终端全文。内存 payload 保存同操作载荷供重试。
- 导入成功先镜像权威 AT/RT/expiry 到管理 profile，保留未知配置；主 HOME 与 runtime 只发布 AT，顶层配置只更新已核对的身份字段，保留 userID。不改 bench enabled、养号开关/阈值、限流或已有额度状态。
- 本地写入/清理未完成时保留暂存和记录，不报成功。重试先查回执，用当前快照；只有明确未提交才以原操作重试。收口 tmux/进程/Recorder并销毁暂存 RT 后再 release。成功结果缓存 1800 秒，仅含账号/同步状态，允许同名同 sid 的重复 commit。
- pending 记录优先于普通执行恢复。对账先停止新心跳、核对原租约，必要时取得新维护门禁，再 fence；等待 API/发送器收口、停止原容器、查询回执。已提交则镜像当前快照；明确未提交保留原 profile。删暂存、release、删执行/提交记录后才完成。未知结果或租约被其它代次接管时保留 reconcile 和门禁。
- 普通 TTL 清理处理 authorizing/ended/ready_to_submit；不确定提交不可自动删除。取消已提交只关闭终端，不回滚远端凭据。服务重启恢复结果，不承诺恢复同一交互终端；未提交草稿沿用下方独立契约。
- status 为 `Cache-Control:no-store`，返回 phase、credentials_ready、expires_at（UTC 秒）、reconnectable 与 authorization_url；已完成返回最小 committed 状态。URL 从同 tmux 的有界屏幕提取，不持久化终端全文。

### 4. Validation & Error Matrix

| 条件 | bench 行为 |
|---|---|
| 旧部署绑定重授权、绑定但未 force_reauth | 409，保持原保护 |
| 账号有活动工作、原绑定/环境改变、身份不符或缺失 | 409，不写其它账号或原 profile |
| 未登录或导入尚不能确认 | 提交未完成；连接/导入未知为 503，保留维护资料 |
| profile/HOME/cleanup 写入失败 | 500 或受控冲突，明确重试/对账，不假报成功 |
| 无 SID、authorizing 到期 | status 404/410；WS 拒绝失效输入 |
| 环境维护占用/归属冲突、对账连接未知 | 409/503；不强行放行 |

### 5. Scenarios and Examples

- 正常：原绑定账号用 `{"name":"账号名","force_reauth":true}` 登录，提交后仍为原 cc2api ID，管理 profile 有新 AT/RT，HOME 只有 AT。
- 基础：认证自动停用可恢复，人工停用保持；未绑定登录、普通 CLI/API 并行行为沿用原分支。
- 错误用法：读复制来的旧 oauthAccount 判断新登录身份，或调用普通 commit_login 把 RT 发到绑定 HOME。正确处理：暂存去旧身份，验证本次登录，走 finish_bound_login。
- 错误用法：HTTP 超时就清暂存/放门禁，或环境页对账绕开 owner 锁。正确处理：保留记录和原操作，fence 后对账，镜像与提交共用锁顺序。

### 6. Tests Required

- `test_login_reauth.py` 使用临时真实 SQLite/文件覆盖同 ID、设备/策略保留、AT-only、身份冲突/缺失、改绑、响应丢失、部分落盘、重启/未知结果、对账占用清理和维护等待 owner 锁；显式声明远端/Docker 替身。
- `verify_stack.py --manifest <联合清单> --browser --reauth`：随机独立部署、合成 CLI/本地代理，真实页面/HTTP/WS/tmux/双 DB 验证；控制 `.synthetic-login.json` 仅在验证目录，fixtures 不进正式镜像。
- `verify_browser.py` 的 insecure_http 模式用 `v3-verify.test` 只解析到回环，Chrome 仍阻止其它公网请求；检查真实非安全上下文的复制降级。原 localhost 属于安全上下文，不能以 HTTP 协议名冒充此验证。
- 两侧凭据、回执、设备、策略、租约与暂存前后比对；结束只按随机部署精确标签清理，核对旧哨兵 StartedAt/hash 不变。恢复测试数据后再验证无遗留。
- 单测/模拟通过不证明真实 OAuth 成功或账号限制解除；上线后由部署负责人安排可用测试账号，经真实 CLI 重授权和正式 API 验收。回滚前收口所有 pending 登录，不删除新回执表。

## Scenario: v3 授权码投递与发送回执

### 1. Scope / Trigger

- 修改授权码输入、`LoginCodeIn`、投递/回执 API、原 tmux stdin 或登录 WS 输入时适用。真实 CLI 可以关闭回显，不能用屏幕未显示授权码推断输入未送达；认证仍由 CLI 完成。

### 2. Signatures

```text
POST /api/accounts/login/{sid}/code
  {request_id: string, code: string}
GET /api/accounts/login/{sid}/code/{request_id}
  -> {request_id: string, status: string, message: string}
LoginCodeIn: StrictStr request_id/code；extra=forbid
AccountRuntime.send_login_code(session, request_id: str, code: str) -> None
LoginSession.code_receipts: dict[str, dict]
status = sending | delivered | uncertain | rejected
```

### 3. Contracts

- 管理 API 沿用既有服务鉴权及 `/accounts/` 桥接；只向 v3 原活跃会话发送。请求正文有界读取，最大 64 KiB；手动校验模型并转换为固定错误，默认 422 不得回显秘密 `input`。request_id 为 32 位小写 hex；code 去首尾空白后为 1–8192 字符，原文拒绝 C0/DEL 控制字符，内部不改写或补猜参数。
- owner 锁内重读原会话、TTL、phase 和草稿代次。缓存命中只返回原回执；未命中的新请求须为 authorizing、未过期且草稿未保存/清理。每 SID 最多保留 32 个不同标识，不淘汰旧标识后允许重放；回执只含标识、状态、说明，不保存 code，随会话结束清除。成功回执为 `Cache-Control:no-store`。
- 投递先登记 sending，再在 owner → environment 锁序下核对完整执行 token、原 SID/tmux/socket、容器 ID、环境代次和原执行证明；Docker IO 不持有 SQLite 全局锁。授权码经 Docker exec stdin 进入 `tmux load-buffer -b <request_id> -`，stdin EOF 与 exec 成功确认后在原会话 paste-buffer，再发送 Enter。code 不进入 argv、脚本或持久文件。
- 临时 tmux buffer 在 finally 中清理。投递前的 ValueError 拒绝为 rejected；可能已注入后的 IO、回包或清理异常均为 uncertain，不能误报“未发送”或自动重复 paste/Enter。delivered 只说明原 tmux 投递完成，认证成功仍须既有 CLI auth status/credentials_ready。
- GET 只查询原回执，不触发投递；原会话/回执不可查不能推断“尚未发送”。管理器重启不恢复授权码或重发队列。v3 登录 WS 保留双向终端交互、resize、ping/pong及同 SID 重连；当前连接的键盘输入只送入原 tmux，不缓存、不重放。授权码仍优先走独立 HTTP 输入框以获得可见回执，页面必须提示不要在两条路径重复发送。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 正文超过 64 KiB | 413，未投递 |
| 空码、控制字符、超长、错误类型/额外字段或非法请求标识 | 422，固定安全说明，无原始 input |
| 原会话不存在/非 v3 | POST 404，不宣称投递成功 |
| 新请求遇到结束/过期会话、保存/清理/换代或已达 32 次 | 409，未开始新投递 |
| 相同合法标识重复提交 | 返回原回执，不重复注入 |
| 原执行证明/终端校验 ValueError | 200 + rejected，明确未发送 |
| 投递或缓冲清理结果无法确认 | 200 + uncertain，不自动补发 |
| 原回执不可查或非法 GET 标识 | 404，明确结果未知 |

### 5. Scenarios and Examples

- 正常：输入框 POST `{request_id:"32位小写hex",code:"完整授权码"}` 到原 SID，显示 delivered 后继续等 CLI 认证检查；检查通过才提交保存。
- 基础：WS 断开但原 CLI 活跃，独立 HTTP 仍可投递；输出重连不创建新 CLI。
- 错误用法：收到 HTTP 超时后生成新标识重发同一授权码。正确处理：GET 原标识回执，未知时检查 CLI 或显式取消/重登。
- 错误用法：用会回显的合成 CLI 证明真实输入无问题，或把 delivered 当作已登录。正确处理：真实 native 禁网实验验证收到输入，合成成功链验证生命周期，并分别报告验证边界。

### 6. Tests Required

- `test_login_drafts.py`：真实 ASGI 验证鉴权、安全 422/413、no-store、同标识重复/并发单次投递、未知回执、32 次上限及过期拒绝；Docker 替身断言 code 只进 stdin、原 socket 及 buffer 清理，可能已投递的清理异常必须为 uncertain。
- 测试环境安装 `services/orchestrator/requirements.txt` 与 `services/orchestrator/requirements-test.txt`，后者只用于 ASGI 客户端，不新增产品依赖。
- 隔离 Chrome/HTTP/WS/tmux 验证真实键盘/原生粘贴、按钮/Enter、回包丢失后查询且不重放、WS 断线独立发送；全新 HOME、禁网的真实支持 CLI 验证收到合成无效码，不访问真实 OAuth，不把实验二进制打入正式镜像。

## Scenario: v3 未提交登录草稿与完整清理

### 1. Scope / Trigger

- 修改新账号登录开始、草稿列表/恢复/重登/删除、首次提交或宕机恢复时适用。已有正式账号的重授权及历史软删除保持原契约；终端交互见 [登录终端生命周期](../../legacy-web/frontend/hook-guidelines.md#scenario-v3-登录终端重连与授权链接)。
- 正式绑定后的首次准备及历史草稿环境遗漏额度挂载也适用；数据库绑定不会改变 Docker 创建时固定的挂载。

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
AccountRuntime.ensure(account: dict, version: str | None = None,
  allow_inactive_login: bool = False, allow_login_recovery: bool = False,
  preserve_proxy: bool = False, scenario_resources: bool = False,
  ownership_source: str | None = None, require_quota_mount: bool = True)
  -> tuple[dict, object]
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
- 布局 2 正式账号复用网络角色前，核对已验证归属并 reload 的实际 `Mounts`：唯一额度挂载必须为 `Type=bind`、`Source=HOST_BENCH_DATA/quota/<bench_id>`、`Destination=/quota-accounts/<bench_id>`、`RW is False`。新建正式环境后也须核对；不能根据数据库 ID 或宿主文件存在推断容器可读。错误账号、来源、可写、重复或不可核验的元数据均拒绝，不能按普通缺失处理。
- 明确没有额度挂载时，默认 `ensure()` 在原环境锁内补齐：只接受 ready/stopped 且无内存作业、单执行/共享执行登记、未确认提交和 CLI 遗留进程的环境，再经原 `maintenance(..., 'rebuild')` 排他空闲认领核对 active/waiting API、维护租约、发送连接和评审交接。保留环境 ID、画像、HOME/最新凭据、工作区及原任务会话，重读新代次后继续准备；正确挂载及重复准备直接复用。草稿无正式 ID、状态查询和旧隔离布局不触发此补齐。
- 仅独立 `transport()` 内部传 `require_quota_mount=False`：API 在准备前已持有自身并发许可，也不读取 CLI 额度文件，因此明确缺失时复用健康发送器；错误或不可核验的挂载仍拒绝。CLI 等其它准备沿默认 true，不新增 HTTP 参数或用户配置。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 非 v3 查询草稿 | 空列表；草稿操作 409 |
| resume/restart 缺少 generation 或带额外字段 | 422 |
| 已换代、正式/历史/归属冲突、清理或提交门禁 | 409，不操作新代或正式资源 |
| resume/restart 锁内重读已不存在 | 404，不能转成 503 并误称仍保留 |
| 重启后无产物或 CLI 认证未通过 | 409，不把文件存在当成功 |
| 单条元数据坏 JSON/结构/HOME/归属 | 该条 reconcile 只读可见，其他条目继续返回 |
| Docker/IO 未完成或恢复连接未知 | 503，保留可重试资料，不报删除/恢复成功 |
| 草稿恢复遇到活动工作、未知提交、旧代次或坏归属 | 409，不解除保护；只提供环境诊断 |
| 提交期间 DB/HOME/清理中断 | 不启用可用账号，保留 submitting，继续原提交 |
| 重复删除资源已不存在 | ok；正式提交后新草稿删除仍为 409 |
| 正式账号明确缺少额度挂载且已通过空闲门禁 | 补齐一次，核实新挂载后才继续准备 |
| 活动作业、active/waiting API、评审或维护占用 | 保留原容器和执行，沿 `RuntimeBusy` 等待/拒绝语义处理 |
| 错误/可写/其他账号挂载、坏 Docker 元数据或未知执行 | `ValueError`，不停止原容器来制造空闲 |
| 补齐时停止/移除/租约收口失败，或新挂载仍缺失 | `reconcile`，保留现场；不得发布 ready 或盲建下一代 |

### 5. Scenarios and Examples

- 正常：start 创建专属环境，刷新账号页后用 `resume {"generation":"页面返回值"}` 继续原 SID；CLI 结束时显式 restart 创建新 SID，环境/CID/userID 保留。
- 基础：管理器突然退出后发现 interrupted 草稿；没有产物则重新登录，有产物则先验证认证再提交，账号容器仍按需唤醒。
- 错误用法：只有 credentials 文件就标记已登录，或提交 IO 失败后通过删除放行。正确处理：真实 CLI 认证检查；submitting 保留资料和门禁，继续提交/对账。
- 错误用法：用旧页面代次删除新登录，或凭账号名称前缀批量删容器。正确处理：锁内重读代次、精确标签和目录归属，仅清专属未提交资源。
- 基础：取消清理失败进入 reconcile，但原执行可核对且已停止；使用恢复检查收口旧会话，保留 HOME 后开放继续/重登/删除，不把恢复当作删除。
- 正常/基础：无 ID 草稿保存为正式账号后调用 `runtime.ensure(account)`，空闲时补齐专属只读额度挂载；再次调用沿用新一代。若独立 API 正在转发，先维持 API，后续需要 CLI 额度文件的准备等待空闲。
- 错误用法：仅更新 `account_environments.account_id` 就认定旧容器额度可读，或挂整个全局额度目录绕过缺失。正确处理：核对实际单账号只读挂载，明确缺失才经过原空闲维护补齐。

### 6. Tests Required

- `test_login_drafts.py` 用临时 SQLite/文件和 Docker 替身覆盖列表/旧环境、非调度、同 SID 继续、原身份重登、重启产物认证、本地保存中断、取消/提交/删除互斥、旧代次/锁内 404、正式/软删除/历史保护、labels/链接拒绝和部分清理重试。
- 必须断言坏 JSON、错环境及 home=null 只隔离单条，另一正式账号仍可读取，坏孤立标记可见且不能删资源；旧非 v3 status 继续按原凭据存在契约返回 credentials_ready，v3 仍须真实认证检查。
- `verify_stack.py --manifest <最终联合清单> --browser --reauth` 串入 `verify_login_drafts.py`：真实 Docker/Chrome/HTTP/WS/tmux、刷新原 SID、CLI 结束与迟到事件、管理器 SIGKILL 后对账/恢复、原环境提交、鼠标确认完整删除；验证全部专属目录/CID/DB 消失且正式账号保留。
- 合成 CLI/OAuth 和故障替身必须明确标注，不访问真实 OAuth；按随机部署精确标签清理测试数据与容器，核对旧哨兵不变和最终冻结源码哈希。真实 OAuth/正式 API 另作上线后验证。
- 清理故障验证 503、can_reconcile 与原 SID/名称释放；拒绝活动工作、未知证明、旧代次及未确认保存，恢复前后 HOME/身份不变。代理 JSON/DOM 不含 userinfo，配置读取失败为 unknown；真实浏览器点恢复后可完整删除草稿而正式账号保留。
- `test_account_runtime.py` 从真实形状的无 ID 草稿创建与正式绑定开始，断言补齐一次、并发幂等、原资料不变；覆盖错误挂载、CLI/API active/waiting、评审、持久记录、孤儿进程和部分维护失败。独立 API 自持许可且明确缺挂载时继续准备，不进入排他认领。
- `verify_login_drafts.py` 在真实浏览器正式提交后准备原环境：容器读取本账号额度 JSON、写入被拒且看不到其他账号目录，Recorder 多次观察不因缺文件误停，重复准备不重建。新账号额度窗口未知允许缺省 `windows`，不能伪造 0% 或主动探测；本地源码覆盖不替代正式镜像发布后验证。

## Scenario: v3 原生 TLS 账号身份与同步

### 1. Scope / Trigger

- 修改首次同步、已有账号绑定、环境身份状态、CLI 版本或网络模式时适用。切换原生 TLS 后不能继续要求普通任务生成只有 Recorder 才能写出的身份文件。

### 2. Signatures

```text
POST /api/accounts/{aid}/cc2api/sync
  -> {ok, created, cc2api_account: {id, ...}}
AccountRuntime.read_cli_identity(row: dict, version: str) -> dict
AccountRuntime.identity_import(account: dict, version: str) -> dict
source = cli:/v1/messages:metadata.user_id.device_id
       | cli:2.1.293:config.userID
CLI payload: device_id, environment_id, source, canonical_env, canonical_prompt,
             canonical_process（可选，实测格式见下方独立动作契约）
```

### 3. Contracts

- 官方 2.1.293 经无外网实际请求验证：`metadata.user_id.device_id` 等于 `.claude.json.userID`，与独立 `machineID` 区分。只有该精确版本开放本地来源；新版本须另做隔离验证，不根据同名字段猜测。
- 固定 HOME 的 userID 必须为 64 位小写 hex，账号 UUID 必须非空且与管理 profile 一致。不能生成新设备、只按邮箱匹配或回退 Linux machine-id。已完成登录无需额外模型任务或完整抓包。
- 外部既有 profile 迁入新固定环境时，`identity_import` 只 ensure 并读取身份，不替代登录对 HOME 的初始化。只允许对本次新建、未绑定且无任务历史的环境在空闲停止后创建缺失的 `home/.claude.json` 与 `home/.claude/.credentials.json`，保留原 userID/UUID；已有内容不匹配时拒绝覆盖。随后仍经正式创建/关联校验，绑定后三份运行快照只保留 AT。不能为让校验通过而生成新设备或削弱冲突检查。
- 已有 `runtime/identity.json` 的 JSON、来源、冲突标记、设备格式及账号归属均须校验；已验证版本的本地设备与旧观察不同仍阻止同步，不能覆盖证据。未知版本只接受已有正式请求观察。
- 同步按 owner → profile → environment 锁序读取；环境 GET 尝试非阻塞取得同序锁，维护时返回待核对状态，不创建／唤醒环境、不生成证据文件。身份状态必须反映实际校验，不只检查文件存在。
- cc2api 仍要求内部服务证明及合法环境；本地来源必须与 canonical_env.version 和 version_base 均为 2.1.293 精确匹配。已有设备不自动替换。
- 已绑定重授权成功返回 `credentials_synced:true` 与原绑定 ID；未绑定 v3 保存返回 `credentials_synced:false, cc2api_account_id:null`。浏览器授权完成不代表保存成功，首次绑定仍须显式同步。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 2.1.293 登录产物齐全，无任务／无 Recorder 文件 | 可导出原设备并同步 |
| 只有管理 profile、固定 HOME 登录文件缺失 | 409；新建空环境按迁移前置初始化，已有环境拒绝盲目覆盖 |
| userID 缺失／类型错误／非 64 位小写 hex，或 UUID 不符 | 409，准确错误，不替代身份 |
| 历史观察损坏、未知来源、冲突或账号不符 | 409，保留原观察 |
| 未验证版本且无请求观察 | 409，提示版本身份来源未验证 |
| 来源与版本不符、缺内部服务证明 | cc2api 401，不创建账号 |
| GET 遇到维护锁 | 显示设备身份待核对，不等待维护完成 |

### 5. Scenarios and Examples

- 正常：官方 2.1.293 登录后按原生 TLS 模式显式创建或关联，cc2api 保存同一 userID；旧 sync API 保持兼容，已绑定重授权更新原账号凭据。
- 迁移：先关闭源调度/刷新入口并完成锁屏障，再把最终权威登录态与原 CLI 身份放入目标 profile；新建空 HOME 补齐必要文件后走正式绑定。旧任务、会话和工作目录不随账号迁入。
- 基础：未绑定账号重授权仅保存本地，页面明确尚未关联；未知版本有历史请求观察时沿用旧来源。
- 错误用法：为了补身份让用户反复跑普通任务，或直接用 machineID 兜底。正确处理：对已验证版本读取官方持久 userID，并保留所有冲突保护。

### 6. Tests Required

- `test_account_runtime.py`：无任务／无抓包导出、缺失及错误类型、UUID 不符、损坏／冲突观察、未知版本、GET 不唤醒及维护锁释放。
- `verify_cli_quota.py`：真实官方 2.1.293、不同的合成 userID／machineID、两条本地请求身份相符；采集前后请求完全一致且零 usage，Docker network=none。
- `verify_reauth_stack.py`：空 runs 表、无 identity.json，经正式同步 API 创建及绑定后核对网关 device_id；真实页面重授权后检查两端 DB、profile、AT-only HOME、回执、原账号／设备／策略和可见结果提示。
- 既有登录态迁移验收：读取源版本真实 DTO；resolve 的有效期必须满足该版 handler（当前 60–7200 秒），不能把参数校验返回的 400 当作刷新锁屏障。核对停用后的锁内 inactive、唯一所有者、原身份/代理/策略、三份 AT-only、原生用户可读与 API Token 范围复原；不运行真实模型压力探针。
- `test_login_drafts.py` 与 `verify_login_drafts.py`：未绑定提交返回明确 false/null，页面显示仅本地保存。官方 CLI 实证与合成成功链分别报告，不以替身冒充官方验证。

## Scenario: v3 独立账号动作、真实进程指标与完整转发验收

### 1. Scope / Trigger

- 修改 bench → cc2api 创建/关联、进程观察、账号卡片或 v3 转发验收时适用。设备来源沿用上方原生身份契约；凭据更新沿用重授权事务，不能把指标更新接到 OAuth 刷新路径。

### 2. Signatures

```text
POST /api/accounts/{aid}/cc2api/create
POST /api/accounts/{aid}/cc2api/bind  {cc2api_account_id: StrictInt > 0}
POST /api/accounts/{aid}/cc2api/process
POST /admin/accounts/:id/cli-process/import
AccountRuntime.ensure(..., preserve_proxy: bool = False)
AccountRuntime.process_identity_import(account: dict, version: str) -> dict
AccountRuntime.process_import(row: dict, container, version: str) -> dict
process_metrics.sample_process_metrics(root, proc, cli, cgroup) -> dict
AccountService::import_cli_process(id: i64, input: &CliProcessImport) -> Result<Value, AppError>
AccountStore::update_cli_process(account: &Account, process: &Value) -> Result<(), AppError>
```

`CliProcessImport` 为 `device_id/email/account_uuid/environment_id/cli_version/canonical_process`，拒绝其它顶层字段。内部导入同时要求管理员鉴权、v3 服务证明和运行门禁。响应为 `{ok, account_id, canonical_process}`；bench 指标响应使用 `cc2api_account_id`，均不含凭据。

### 3. Contracts

- 页面未关联时显示“创建网关账号”“关联已有账号”；已关联账号的“更新进程指标”位于任务账号配置的折叠“高级维护”。“重新授权”保持独立。关联选择从养号表单移出，后者只保存养号/额度。按钮状态不能替代服务端绑定/身份/占用校验。公开凭据归属消息使用“网关”，内部 cc2api 字段和路径保持兼容。
- 创建只接受未关联账号；匹配到现有身份返回冲突及关联提示，不自动切换。关联接受显式目标，只匹配该账号，不创建；按原所有权保护镜像 cc2api 权威凭据，保留养号和目标策略。新 UI 不再调用 `/cc2api/sync`，旧 sync 和 warmup 绑定字段保持兼容。
- 任务侧真正创建的载荷显式设置 `request_backend="native293"`、`five_hour_usage_limit_percent=85`、`seven_day_usage_limit_percent=80`、`billing_mode="rewrite"`、`upstream_session_pool_enabled=true`、`upstream_session_pool_size=4`、`upstream_session_refresh_policy="owner_only"`、`concurrency=4`、`rpm_limit=50`。额度闸线按对应窗口已用百分比计算。TTL 时长沿用默认 60 分钟；不修改 cc2api 手工创建的全局默认，不覆盖关联、指标更新、重复兼容同步或重授权后的既有策略。
- 指标更新持有 owner → profile → environment 锁序，仅核对代理配置，不能调用 `_sync_proxy` 回写代理或解析/刷新 OAuth。内部服务在排他配置门禁下拒绝活动/等待请求；不为指标写入 quiesce/停止在途发送器。存储只条件更新原身份的 `canonical_process/updated_at`，不能把旧 Account 副本整行写回而覆盖轮换后的凭据/策略。
- 实际 cgroup v2 `memory.max` 或 v1 `memory.limit_in_bytes` 提供 RAM 上限；零只表示明确的无限制。读取失败不能当作无限制，导入须与固化 RAM 预算交叉核对，不能把 RAM＋swap 或容器占用当作 RAM 限制/RSS。
- root 监督循环每两秒只读 procfs；只采 UID1000、root 所有且组/其它用户不可写、已完成版本缓存中的原生 `/cli/<version>/node_modules/@anthropic-ai/claude-code/bin/claude.exe`。核对进程启动时刻防 PID 复用，不读取命令正文或环境变量，不把 Node 探针/发送器当 CLI。
- Docker 默认无 SYS_PTRACE；仅在读 exe 链接时匹配账号 fsuid/fsgid，立即恢复后由 root 核对缓存，不能增加容器权限。root 私有 `runtime/process-metrics.json` 使用 schema=1、环境归属及最多 32 个版本，私有锁内原子写入、0600、文件 fsync；坏记录保留并拒绝导入。采样不发请求、不启动额外模型任务，普通观察失败不停止 API。
- `canonical_process.observation` 固定 `source="v3:procfs:cli"`、32 位小写 hex `environment_id`、精确 `cli_version`、UTC 秒 `observed_at/sampled_at`、整数 `sample_count`、字节 `rss_bytes/rss_min_bytes/rss_max_bytes`。内存/样本计数必须非负且小于 2^53；时间有限且不超当前 60 秒，采样时刻不晚于观察时刻。count=0 时采样时间及三个 RSS 都为 null；count>0 时它们必须齐全且 `0 < min <= rss <= max < 2^53`。
- 容器上限可独立导入；RSS 没样本显示“未采集”，有样本显示真实时间。v3 observation 不填旧兼容默认堆/CPU/RSS 范围，上游只发送有依据的 constrainedMemory 和可选 rss，内部来源元数据不进入遥测。普通旧账号画像沿用既有兼容，已有 v3 账号通过独立按钮补齐，不批量迁移设备或凭据。
- 完整转发验收使用真实调度器、空 SQLite、随机部署、两账号发送器、HTTP CONNECT/SOCKS 与本地 HTTPS 上游；来源 IP、合成标记、发送器 request_id 和响应哈希须可关联。正式 messages JSON/SSE、实际 CLI/API 并行、取消收口和失败关闭分别验收，不能以 ClientHello/502 或 runs-stream 代替成功业务响应。
- 原生池验收探针显式以 `user='1001:1001'` 执行并校验 `geteuid()==1001`，避免 root 启动的 TLS broker 与降权 worker 的 procfs 权限混淆。保留六 worker、一个封存映像、内存预算和默认120秒空闲回收断言，不能因探针权限失败放宽数量要求。
- 隔离构建仅显式启用 Cargo `v3-verification` 与 Docker `verification-control/verification-account`，临时根位于 `/run/v3/verification-ca.der`，仍验证签名与主机名。正式 control/account 不依赖这些阶段，不含该读取路径，不新增运行时 CA/跳过校验开关。测试镜像/清单不发布；生产非模型 HTTPS 与真实模型推理分别报告，受限账号不用于模型探测。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 已关联时创建/关联、创建遇已有匹配、关联目标不存在 | bench 409，不自动创建/改绑 |
| 任务侧首次创建 cc2api 账号 | 原生运行时 native293；5h 已用闸线 85%，7d 已用闸线 80% |
| 非 v3 或未关联时更新指标 | 409；不可用账号 404 |
| 代理不一致、来源/版本/样本/内存预算错误 | 409，不改目标进程、代理或凭据 |
| 内部证明缺失/伪造 | cc2api 401，不写库 |
| 活动/等待 API 或 CLI 维护占用 | 内部拒绝，原数据与在途流保持；bench 返回受控 409/502 |
| 新账号无 CLI 样本 | 上限准确，RSS null / 未采集 |
| 发送路径、代理、证书/主机名、绑定/代次/目标错误 | 明确失败，无直连回退和不安全重放 |

### 5. Scenarios and Examples

- 正常：未关联账号点击创建，使用原生运行时 native293、5h 已用闸线 85%、7d 已用闸线 80%，其余六项为 rewrite/开启/4/owner_only/4/50；已存在则显式选择关联，保留管理员自定义 strip/关闭/2/mapped_request/2/17 及运行时、额度闸线。关联后更新指标只改进程字段。
- 基础：`constrained_memory=1610612736`、`sample_count=0`、`sampled_at/rss_*=null`，页面显示容器上限 1.50G 与 CLI RSS 未采集；之后真实 CLI 样本补齐 RSS 和时间，停止/重启不伪造新样本。
- 错误用法：点击“更新进程指标”顺便 resolve OAuth，或把缺失堆数据填成静态默认值。正确处理：独立身份/观察载荷与条件列更新，未知项不发送。
- 错误用法：首个 session ID 未改变就判定池无效，或丢弃 urllib3 读取器后再测试“在途”拒绝。正确处理：前四个属主可保留 ID，第五个映射到四成员内；保留读取器并先断言 active>0，再取消及核对上游 completed=false。

### 6. Tests Required

- `test_process_metrics.py`：真实跨 UID procfs 路径及文件身份恢复、v1/v2/无限/损坏 cgroup、官方缓存/权限/PID/RSS、空样本、持久化及归属冲突；`test_account_runtime.py` 断言预算核对和原身份导出。
- `test_main.py`：创建冲突不刷新/关联，`test_explicit_create_sends_runtime_quota_defaults_and_preserves_warmup` 断言九项创建默认配置及保留本地养号设置；显式关联不创建/改养号、未关联指标拒绝、更新不读凭据或改账号。Rust service/store 测试覆盖坏来源/身份/版本/样本、条件列写入与并发凭据/策略保护；identity/rewriter 测试覆盖对象及 base64 中未知堆/CPU 不外发、旧画像兼容。
- `verify_forwarding.py --build ...` 复用 canonical 冻结与联合清单；实际浏览器点击三入口、明暗与 1440/720px、官方 CLI RSS → API/SQLite/卡片。正式 `/v1/messages` JSON/SSE 响应哈希、Billing 与 5→4 session、两账号隔离、实际官方 CLI 与 API 并行、取消及全部故障场景均通过；网关专属网络命名空间的公网阻断计数为零，结束按本次精确标签清理。
- 正式镜像继续跑 `verify_stack.py --browser --reauth`，核对原 ID、AT-only HOME、完整 profile、创建默认策略/TTL、错误登录/取消/草稿恢复及旧哨兵。页面驱动等首次列表事件处理器就绪，避免人为并发初始查询；失败保留脱敏证据。
- `cargo fmt --check && cargo test`、Python 全量及前端构建保持。可用账号的真实 Anthropic 推理单独验收，不用测试替身/生产非模型 200 冒充。

## Scenario: cc2api 删除后的悬空绑定收口与凭据交接

### 1. Scope / Trigger

- 修改 v3 解绑、正式账号删除、`owner_transition`、运行凭据发布或作业收尾时适用。远端删除的收口与本地刷新权交接必须同时完成。

### 2. Signatures

```text
DELETE /api/accounts/{aid}/cc2api-binding -> {ok: true}
DELETE /api/accounts/{aid}
AccountRuntime.owner_transition(account: dict, target_id: int | None, *, handoff_credentials: bool = True)
AccountRuntime.sync_credentials(row: dict, account: dict, *, take_ownership: bool = False) -> None
Cc2ApiClient.list_accounts(*, require_complete: bool = False) -> list[dict]
GET /admin/accounts?page=<从1开始的页号>&page_size=100
runtime/credential-handoff.json -> {schema: 1, account_id, environment_id,
                                   previous_binding, profile_sha256}
```

### 3. Contracts

- 只有 `target_id=None` 的解绑/本地删除，且失败 ID 为原绑定，才允许缺失收口。原 lease GET 或 prepare 的 ValueError 必须直接由 `urllib.error.HTTPError(code=404)` 引起；不能匹配错误文案，不能把网络、鉴权、5xx、坏 JSON 或其它冲突当作删除。
- 404 后再次成功读取完整账号列表，确认原 ID 不存在，才跳过已删除账号的远端门禁；原账号仍存在或列表读取失败时拒绝。新目标、改绑和正常远端账号继续严格查询、prepare、检查占用，并在事务后 release。
- 缺失证明调用 `list_accounts(require_complete=True)`：`page/page_size/total/total_pages` 为真实整数，页号匹配当前页、容量为 100、total 非负、页数为 ceil(total/100)，每页行数匹配应有数量；每行 ID 为正整数且全量去重后数量等于 total。空列表的 total/total_pages 均为 0。坏行不得静默过滤，不能只查第一页；普通列表调用默认保持原兼容行为。
- owner 锁内重读绑定并沿用 active run（含 quota_wait）、续聊、登录保护；环境作业和实际发送器仍须空闲。发送器状态未知也拒绝。确认空闲后停止旧容器、写 stopped，再由现有 SQLite 事务清空绑定和关闭未来养号，不能直接改库绕过收口。
- 解绑保留原账号、环境 ID、固化画像、HOME 和本地凭据。绑定期间管理 profile 持有完整镜像，HOME/access 只发布 AT；解除绑定后显式 `take_ownership=True` 把完整 AT/RT/expiry 交接给同账号 HOME，不调用远端 OAuth resolve/refresh 或自动创建账号。主入口持有 owner → profile → environment 锁序。重复空闲解绑返回成功，旧绑定缺失造成的待对账也可用同一显式入口收口。
- 本地完整凭据要求 AT/RT 均为非空字符串，expiry 为排除 bool 的有限正数且小于 2^53，允许已过期但结构完整。已有独立 HOME 的完整 RT 是轮换权威，不被旧 profile 回滚。给 AT-only HOME 补 RT 前核对两侧非空字符串 userID/accountUuid 相同；普通补齐还须 AT/expiry 完全相同，显式解绑才可交接原管理侧的更新快照。文件/身份损坏或来源冲突保留现有秘密并拒绝猜测合并。
- 交接资料先校验，停止旧实例后、DB 提交前原子写 0600 的无令牌意图记录；DB 和 HOME/access 全部发布完成才删除。记录校验账号/环境/原绑定与原管理文件 SHA256；来源变化或改绑目标拒绝。中断保持 reconcile，启动 reconcile/ensure 不能绕过记录；重复显式解绑验证原证明后续办，不能假报成功。
- 正式未绑定账号的 `release` 仅把完整 HOME 凭据原子镜像回 profile；AT-only、缺字段或坏 JSON 拒绝回写并保留执行证明/隔离，不能抹除已有 RT。未提交草稿没有正式 account_id，不回写正式 profile。显式本地账号删除用 `handoff_credentials=False`，保留原占用与停止门禁，不要求先修复失效 RT；旧 warmup 的 null 继续表示保留绑定。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 原 lease 404＋完整列表明确无原 ID＋本地空闲 | 解绑 200，绑定 null、养号 off、next null |
| 404 但原账号出现在任一页，或列表不完整/损坏 | 拒绝，原绑定和实例保持 |
| 鉴权、网络、服务错误或原门禁占用 | 拒绝，不能降级为已删除 |
| 本地 run/续聊/登录/环境作业或发送器占用/未知 | 拒绝，不中断活动发送 |
| 新目标缺失或改绑遇缺失原账号 | 继续严格拒绝，不使用解绑例外 |
| 已解绑的空闲账号再次解绑 | 200，不创建远端账号 |
| profile 完整、HOME AT-only、身份一致 | 解绑后 HOME 接管 RT，绑定空、养号 off |
| 未绑定 HOME 已有新完整 AT/RT | 保留轮换结果，收尾镜像回 profile |
| HOME 不完整/损坏、来源或身份不符 | 不降级覆盖管理凭据；交接前拒绝或收尾隔离 |
| DB 已解绑但 HOME/access 写入失败 | 保留交接记录与 reconcile，重复解绑可续办 |
| 交接记录来源变化、启动/普通唤醒/再次改绑 | 保留记录并拒绝自动放行 |
| 显式删除本地账号但凭据失效 | 无需交接 RT，仍按原空闲/停止/删除规则执行 |

### 5. Scenarios and Examples

- 正常：先在 cc2api 删除账号，再从 bench 点击解绑；确认无原 ID、停止旧实例后清空本地关联，页面恢复“创建 cc2api 账号”和“关联已有账号”。
- 基础：远端在 lease GET 与 prepare 之间删除；确认完整列表缺失后按相同本地空闲规则收口。重启调度器不改变该显式恢复入口。
- 错误用法：捕获所有管理请求异常后直接 UPDATE 本地绑定。正确处理：限定原 ID 的真实 404，并核对完整列表与本地发送器，不把“查不到”一概当作删除证明。
- 错误用法：解绑后继续优先已有 AT-only HOME，再在后台刷新失败的 finally 中覆盖 profile。正确处理：解绑时交接完整凭据，收尾前验证完整性，验收到下一次真实使用边界。

### 6. Tests Required

- `test_deleted_binding.py`：真实异常链/SQLite/运行时，保持原门禁回归，增加正常/悬空解绑 RT 交接、失败作业收尾、独立轮换、旧 AT-only 同源补齐、坏文件/身份冲突、HOME/access 写入故障、重启保留意图及重复恢复、来源变化/改绑拒绝，以及本地删除不依赖 RT。
- `test_login_drafts.py`：合成成功凭据具备真实 CLI 的 expiry；未提交 AT-only 草稿仍可取消，不污染正式 profile，保存失败和重试门禁保持。
- `verify_stack.py --manifest <同批正式清单> --browser --deleted-binding`：随机部署经正式创建/绑定、远端删除、重启与页面解绑，核对两库和 RT 交接；真实 scheduler/runner/容器执行仅替换 OAuth 探测为失败，收尾后再次页面创建成功，HOME 回到 AT-only。保留原身份、统一会话/退出与旧哨兵验证，不访问真实 OAuth/usage/模型，只清理本次标签资源。

## Scenario: v3 三角色 Docker 隔离与 OAuth 出口

### 1. Scope / Trigger

- 修改固定账号布局、权限/挂载、网络策略、资源预算、OAuth 客户端或账号迁移/部署验证时适用。本节是布局 2 对前述单容器约定的增量契约；普通 API/CLI 调度、凭据所有权与业务协议继续沿用。

### 2. Signatures

```text
account_environments.container_id TEXT                 # CLI，保留原字段
account_environments.network_container_id TEXT
account_environments.sender_container_id TEXT
account_environments.isolation_version INTEGER DEFAULT 0
account_isolation.ISOLATION_VERSION = 2
ROLE_COLUMNS = {cli: container_id, sender: sender_container_id, network: network_container_id}
ROLE_LABELS = {cli: account, sender: account-sender, network: account-network}
isolated_account_limits(memory: str, swap: str = "0") -> dict[str, tuple[int, int]]
services/gateway/src/service/oauth.rs: validate_oauth_proxy(proxy_url, runtime_url, deployment_id)
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
- 上述 sender 128 MiB 为 legacy 布局；native293 使用下文显式原生预算，CLI/评审/指标从同一冻结预算扣除 sender 份额。
- 新登录与项目环境均使用基础三角色预算，不再静态预留512MiB或创建 `runtime/project-review-layout.json`。评审先停止原固定CLI，再串行复用扣除network/sender后的RAM，结束后恢复同一CLI。旧schema1布局只读核验实际限制，不隐式扩容、重建或改写固定配额；旧隔离版本仍须显式空闲升级。`account_environments.container_id`始终指固定CLI；交接记录、私有目录、原owner刷新及严格收口以[项目场景契约](project-iterations.md#scenario-内容-schema-2-的真实项目多场景任务与-policy-3)为准。
- 创建按网络 ready 再业务角色，逐个登记；失败停止本代已创建实例并保留对账证据，未知/部分角色不能 ready。停止按 CLI→sender→network；维护、备份、草稿删除与孤儿处理核对完整角色集合。管理端重启与 CLI 单次取消保留健康 API/SSE；CLI 单独异常仅关闭下一 CLI。
- 布局 0 的已有实例只在显式空闲重建时转换，GET/普通发送不能静默迁移。先停机备份，转换保存私有 isolation-upgrade 快照；回退保留最新 HOME/凭据，不恢复旧 RT/数据库覆盖轮换结果。未创建实例的新行保持布局 0，受控 ensure 才登记 2。
- 业务指标取 CLI 实际 PID/cgroup，管理端写私有观察记录。验证 CA 仅供 verification 镜像，sender 的只读 /run/v3 下嵌套 CA bind 必须预置目标；正式镜像不读取该 CA。测试依赖的系统目录仍只读，故障注入使用网络私有运行记录。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| CLI/sender 修改系统目录、路由或读取其他角色秘密 | 拒绝；本账号 HOME/项目可写与执行 |
| 网络 ready 超时、标签冲突或部分角色创建 | 不发布可用绑定，保留 reconcile/证据 |
| 旧 root API 证据为普通单链接文件 | 内容保留，移交后可继续追加并轮换 |
| 旧 API 证据或父目录为链接，文件为多硬链接或特殊文件 | 拒绝创建，不改变链接目标属主/内容 |
| 删除默认路由后落到 bridge | 默认 DROP 内核计数增加，不直连 |
| v3 空白代理，包括只剩部署标识的配置 | OAuth 客户端创建前拒绝；不轮换 AT/RT 或停用账号 |
| 独立部署两个 v3 标识均为空 | 保留显式直连兼容语义 |
| 账号总 RAM 不足 896 MiB | 明确拒绝，不能静默加配 |
| CLI 取消或管理端重启时 API 长流健康 | sender 不重启，流完整或按原取消语义收口 |
| 旧布局仍有活动/提交未决或回退凭据来源不明 | 拒绝转换/覆盖，保留原资料 |

### 5. Scenarios and Examples

- 正常：1536m RAM + 2048m 额外 swap 分配为 CLI 1152m RAM + 2048m swap、network 256m、sender 128m；JSON/SSE 和官方 CLI 本地工具可并行。
- 基础：已有固定环境停机后显式重建，保留环境 ID、HOME、machine-id 与最新凭据；角色缺失先对账完整集合。
- 错误用法：只核对 CLI/sender 身份彼此相同，或只 chown API 证据父目录。正确处理：实际身份对照保存画像，同时移交已有证据与轮换文件，再验证真实发送后仍可追加。
- 错误用法：认为账号网络防火墙已保护 gateway 的所有 OAuth 请求。正确处理：OAuth 公共入口按 v3 标识拒绝空代理，并实测连接尝试为 0。
- 错误用法：`containers.list(environment)[0]` 后执行 tmux，或 mv 只读系统程序制造故障。正确处理：显式选择 account/account-network，使用私有运行记录注入并在 finally 恢复。
- 错误用法：用创建时缓存的 StartedAt 判断后续长流是否被重启。正确处理：流首字节之后 reload sender，比较本次在途重启前后的实时状态及完整响应哈希。

### 6. Tests Required

- 账号运行时单元覆盖角色登记/归属、部分创建/孤儿收口、总预算、旧行与受控转换、身份/凭据保持、链接逃逸拒绝。Rust `cargo fmt --check`、`cargo test --locked` 覆盖 v3 两种标识及部分配置、空白代理拒绝、独立部署兼容。
- MAC 回归使用真实 SDK 的 API 1.52 EndpointConfig 验证创建参数，并通过 Docker 实际网卡对照保存画像。`run_local_verification.py` 预置 root:root 0600 的当前/轮换证据，确认历史字节保留且 sender 能追加；单元覆盖符号链接、硬链接和 FIFO 拒绝且目标不变。
- `verify_forwarding.py` 标准入口覆盖真实权限/秘密、官方 CLI 本地工具、HTTP CONNECT/SOCKS5 的 OAuth/JSON/SSE、4 成员池、CLI/API 并行取消、管理端重启、错误证书/代理/绑定拒绝。空代理回归核对 AT/RT/oauth_expires_at/status 保持，最终 gateway 公网连接尝试内核计数必须为 0；SQL 字段以 AccountStore 的实际映射为准。
- `verify_stack.py --browser --reauth` 覆盖草稿取消故障、恢复及完整删除；账号冷启动等待可用 150 秒，普通 DOM 仍为 15 秒。`--deleted-binding` 保留 RT 交接与再次创建回归。脚本不得依赖诊断 wrapper 才通过。
- `run_local_verification.py` 使用同批正式清单与显式旧 control/account 镜像验收真实转换及离线回退、透传/Recorder、路由故障和总预算；分别记录本地夹具、正式非模型与真实模型证据，不以隔离承诺免封。

## Scenario: v3 按账号固定的常规内核与 CPU 型号画像

### 1. Scope / Trigger

- 修改 `system_profile.py`、账号镜像的 `system-profile.c`、画像挂载、初始化或 CLI 就绪门禁时适用。只覆盖常规软件读取，不把它当作新的安全沙箱或已确认的封禁原因修复。

### 2. Signatures

```text
fingerprint_json.system_profile = {
  schema: 1, kernel_template_id: string, kernel_release: string,
  kernel_version: string, proc_version: string,
  cpu_template_id: string, cpu_signature: [vendor_id, family, model], cpu_model_name: string
}
generate_system_profile(cpuinfo: str) -> dict
validate_system_profile(profile: dict, cpuinfo: str | None = None) -> dict
render_system_profile(profile: dict, cpuinfo: str) -> dict[str, str]
AccountRuntime.prepare_system_profile(row: dict, network) -> None
AccountRuntime.check_system_profile(row: dict, container) -> None
```

### 3. Contracts

- `system_profile` 独立于原 `profile_version=2`。首次受控创建时读取真实 Docker 网络角色的 `/proc/cpuinfo`，限定 4 MiB，核对所有逻辑 CPU 代际后从内置兼容模板选择一次；保存后跨 run、续聊、改名、停止唤醒、重建及回退复用。仅缺 key 可补齐，显式 null、未知 schema/模板或改写内容必须拒绝，不能重新随机。模板 ID 及内容只追加，不重解释旧记录。
- 已登记模板覆盖 `AuthenticAMD/23/1`（Naples）与 `AuthenticAMD/25/80`（Cezanne）；其它x64 CPU首次创建使用`host-cpu-v1`保存真实厂商、family/model和型号，缺少对应机型时使用`portable-computer-v1`。已保存画像跨CPU代际及厂商迁移保持原值；渲染只替换型号，目标实际family/model/stepping、flags、核心数和拓扑继续使用目标原文。格式、固定模板及身份完整性继续核验。
- 生成发生在环境锁内、CLI 创建前；有活动 job 或已有 CLI 实例时拒绝应用。旧容器须显式空闲重建，不能在 GET、普通 API 发送或正在运行的 CLI 中静默迁移。既有 hostname、MAC、machine-id、时区、设备、凭据和绑定保留；即使执行已获许可的 legacy reprofile，也保留已有合法 system_profile。
- account 镜像携带 `vibebench.system-profile-version=1` 能力标签及镜像内编译的共享库；容器可能继承镜像标签，不能据此推断某角色已加载。只有 CLI 挂载 root 所有的只读 `/etc/v3-system-profile`、`/etc/ld.so.preload` 与 `/proc/cpuinfo`；network/sender 的 preload 为空，权限、网络和预算沿用三角色契约。
- 覆盖库通过 libc uname 替换 release/version，保留 hostname/架构；常规 open/open64/openat/openat64、fopen/fopen64 及 fortified open 对三个内核文件精确重定向：`/proc/version`、`/proc/sys/kernel/osrelease`、`/proc/sys/kernel/version`。支持词法归一化、相对 cwd/目录 fd；写入仍走原接口，保留创建 mode、errno 和原 fortify 拒绝。配置初始化避免 hook 递归并使用 pthread_once，坏字段返回 EIO。
- raw syscall、静态 uname、CPUID、显式库绕过、符号链接别名及未覆盖 sysfs 可能显示真值。CPU 文本与 CPUID 可不同；挂载/库本身可观察，不宣称全层一致、无指纹或免封。CPU/RAM 实际限额及 RSS 不参与替换。
- 创建后及 CLI 入口执行实际读取/只读校验，标签不能代替证据。旧 CLI/坏画像只标记 `cli_reconcile`，不停止健康 API；其恢复允许 `exclusive + idle_only + maintenance:` 的显式维护认领，仍检查 API 排空，普通登录/任务不能借此绕过。新角色创建失败则停止本代已创建角色并保留 reconcile 证据。
- `identity_import` 继续真实执行容器 Node 探针，同源填充 `canonical_env.linux_kernel` 和 `canonical_prompt.os_version`；真实进程指标维持原契约。既有 cc2api 保存环境不自动批量改写，不生成新设备或修改凭据/策略。
- 回滚用旧镜像/配置在空闲窗口重建并去掉 CLI 画像挂载，保留新增 JSON 对象和最新 HOME/凭据；重新启用复用原对象。画像文本与 JSON 共用逐级 O_NOFOLLOW 目录 fd 的原子写入，不能沿账号链接覆盖外部文件。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 同账号新任务、续聊、唤醒、重建 | 固定替换字段保持，原项目目录规则不变 |
| 画像缺 key / 显式 null 或内容损坏 | 受控创建时补齐一次 / 拒绝，不重新随机 |
| 未登记CPU / 迁移后的不同CPU代际 | 使用实际型号首次生成 / 保留原画像 |
| CPU信息缺失、格式异常或混合代际 | 明确报错，保留原记录 |
| 活动 job 或已有 CLI 实例调用准备函数 | 拒绝改写，先完成空闲重建 |
| 旧 CLI 或实际读取不符 | CLI 待对账；健康 API 保留，可显式排空后重建 |
| preload 或覆盖库未实际加载、其它画像文件不符 | 实际探针失败，不假报 ready |
| release/build 文件权限、类型或单行格式不合法 | 运行库的 uname 返回 EIO，实际探针失败 |
| CPU 原始指令、静态或直接 syscall 探针 | 报告真实值，不伪称覆盖 |

### 5. Scenarios and Examples

- 正常：新账号选定一组模板，后续不同 run 及容器重建复用；只读 CPU 文件仅型号行改变。
- 边界：旧账号没有新对象时保留原身份并等待空闲重建；旧 CLI 校验失败不影响既有 API 长流，也不能让后续普通任务跳过门禁。
- 错误用法：仅替换外部 uname、修改管理页值、覆盖坏记录重新抽签，或靠增加 SYS_PTRACE/privileged 放宽 proc 挂载。正确处理：只读文件与动态接口配合，实际验证支持路径并明确绕过边界，损坏记录保留等待核对。

### 6. Tests Required

- 单元覆盖型号之外的CPU原文保持、未知CPU实际型号、跨代/跨厂商迁移保留画像、混合代际拒绝、画像损坏不重生成、首次增补一次、改名/重建/legacy reprofile保持及CLI待对账仍可显式维护。
- 实际 Docker 验证动态与静态 C、直接 uname syscall/CPUID、普通/fortified open、相对 openat、fopen、并发读取、Node/子进程、真实只读挂载及损坏字段 EIO；network/sender 不加载覆盖，实际资源/秘密边界保持。
- 精确官方 CLI 2.1.293 在无账号断网环境验证版本、认证状态和登录帮助，结合动态绑定证明 uname 确实走覆盖。auth status 的未登录退出码 1 不算启动失败；不能据此声称真实登录或模型交互已验收。
- 用 `run_local_verification.py` 的正式构建清单及显式旧 control/account 镜像验证 API/CLI 生命周期、重建和回退再启用，核对画像、身份及 HOME/凭据保留；记录本地启动性能及未执行的生产/真实模型边界。

## Scenario: v3 持久计算机身份与 DMI 常规读取

### 1. Scope / Trigger

- 修改计算机身份生成、`fingerprint_json.computer_profile`、DMI 读取库或跨重建持久性时适用。沿用前一场景的 CPU／内核、三角色权限和 CLI 待对账契约，不接入闭源生成器、不新增生产迁移入口。

### 2. Signatures

```text
fingerprint_json.computer_profile = {
  schema: 1, template_id: string,
  dmi: {manufacturer: string, product: string, version: string,
        family: string, serial: string, uuid: string}
}
generate_computer_profile(system_profile: dict) -> dict
validate_computer_profile(profile: dict, system_profile: dict) -> dict
render_computer_profile(profile: dict, system_profile: dict) -> dict[str, str]
verify_computer_profile(container, profile: dict, system_profile: dict) -> None
account 镜像能力标签：vibebench.computer-profile-version="1"
只读标记：/etc/v3-system-profile/computer-profile-version，内容为 1 加换行
```

### 3. Contracts

- 旧 `system_profile` schema=1 保持不变。计算机对象和 dmi 对象必须精确匹配声明的键；schema 必须为整数 1，不能用 bool。已登记CPU优先选同代合成机型，其余使用不绑定CPU的`portable-computer-v1`；已有机型随原画像迁移，serial和UUID保持。模板ID及显示内容只追加、不重解释，也不声称是原厂DMI快照。
- serial 为独立随机生成的 16 位大写十六进制，uuid 为独立标准小写 UUIDv4；不从 MAC、machine-id、账号或官方设备身份派生。已有合法 hostname、MAC、machine-id、时区／语言、CPU／内核、HOME、凭据及绑定继续保留；CPU 能力、实际限额和 RSS 不随机替换。
- `prepare_system_profile` 在环境锁内、CLI 创建前读取实际 CPU；Docker 读取位于 SQLite 写事务外。`BEGIN IMMEDIATE` 后重读本行指纹、generation 和 container_id，仅缺 key 才生成；不持全局 jobs 锁等待 SQLite。UUID 占用查询与首次提交位于同一事务，未发布碰撞最多尝试 8 次；已保存重复值报错，不能旋转身份。
- 先提交完整权威 JSON，再用逐级 O_NOFOLLOW 的原子写入渲染只读文件。画像和 dmi 目录 root 所有且 0755，文件 0444，计算机标记最后发布；提交后渲染失败、旧 row 重试或并发初始化都从 DB 复用同一对象。新任务、恢复、进程重启、唤醒、重建和镜像更新不重抽；legacy reprofile 也保留合法计算机对象。
- 仅 CLI 加载共享库与只读画像，不新增 capability。将 `/sys/class/dmi/id` 和 `/sys/devices/virtual/dmi/id` 下的 sys_vendor、product_name、product_version、product_family、product_serial、product_uuid 映射到同一 dmi 子目录；精确目录打开、相对目录 fd 与受支持 chdir 后读取也适用，不依赖宿主存在 DMI 目录。
- 内容和元数据共用路径映射：普通／fortified open、fopen，以及 stat/lstat/stat64/lstat64、fstatat/fstatat64、statx、access/faccessat、旧 glibc stat ABI。x86_64 的动态 libc `syscall(SYS_statx, ...)` 同样映射，以覆盖 Node/libuv；其它 syscall 保留原始参数和 errno。不得用 va_arg 读取未传入参数，零参数和六参数透传均须实测。
- `O_TMPFILE` 包含 `O_DIRECTORY` 位，必须按完整 mask 判断，不能把 `O_RDONLY | O_DIRECTORY` 当作写入。写入仍走原接口；白名单外保持原行为，不扩大为整棵 sysfs 仿真。静态程序、直接内联系统调用、CPUID、符号链接别名、完整 SMBIOS／dmidecode 和未列路径仍在覆盖边界外。
- 能力标签不代替实际证据：创建和 CLI 入口校验两目录六字段的内容、存在、可读和不可写。旧实例只能显式空闲重建；坏对象／旧 CLI 只隔离 CLI，健康独立 API 保留。库初始化区分旧画像缺标记和已发布标记损坏，后者拒绝 DMI 读取，不回退宿主值。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| key 缺失且处于受控创建窗口 | 生成并提交一次；旧基础身份和未知顶层字段保留 |
| 显式 null、未知键／版本／模板、格式坏或跨 CPU 代际 | ValueError，原记录保留，不重新随机 |
| 已提交 JSON，但文件发布或后续创建失败 | 停止本代已创建角色，重试复用已提交身份 |
| 新值 UUID 碰撞／已有 UUID 重复 | 首次发布前有界重试／已有身份报错不旋转 |
| 活动 job、CLI 已存在或 generation 改变 | 拒绝应用，等待合法空闲维护 |
| account 镜像缺少计算机能力 | 创建前拒绝，要求同批支持镜像 |
| 两目录内容或权限探针不符 | CLI 待对账，不能仅据标签报告已加载 |
| 已发布标记无效，或 DMI 文件不可读、类型／权限／有界单行格式损坏 | 常规 DMI 读取返回 EIO，不回退预置宿主内容 |

### 5. Scenarios and Examples

- 正常：保存兼容的 CPU 与计算机对象，独立控制端进程恢复、停止唤醒和另一批镜像显式重建后，规范化静态身份 SHA256 相同，实际 DMI 与 DB 一致。
- 基础：旧记录有合法 CPU／内核但缺计算机对象，在空闲重建时只增补后者；旧 CPU、时区和设备配置保持。
- 错误用法：`if not saved.get('computer_profile'): ...` 把损坏的 null 重新随机。正确处理：仅检查 key 是否存在，存在则严格校验：

```python
if 'computer_profile' not in saved:
    saved['computer_profile'] = generate_computer_profile(saved['system_profile'])
validate_computer_profile(saved['computer_profile'], saved['system_profile'])
```

- 错误用法：cat 输出合成文本就报告完成，或 stat 失败后显示缓存页面值。正确处理：分别用 Python、Node 和原生 C 校验内容、exists/stat、access 和相对目录接口，并在预置宿主 DMI 与缺 DMI 两种环境下验证。

### 6. Tests Required

- `test_system_profile.py`覆盖Naples／Cezanne候选、未知CPU通用机型、独立serial／UUID、严格键和格式校验、跨宿主保留原机型；机型与保存画像的内部关联仍核验，型号之外真实CPU原文继续断言。
- `test_account_runtime.py` 覆盖两个独立运行时共享 SQLite 的首次并发、提交后写文件失败及 stale row 重试、损坏记录拒绝、未发布 UUID 碰撞、旧身份／legacy reprofile 保留和健康 API 不受 CLI 门禁影响。
- `verify_system_profile.py --manifest` 与原生探针覆盖两目录六字段、Node/libuv statx、元数据／权限／只读、相对 fd／cwd、零／六参数 syscall 和 errno、静态／CPUID 边界，以及已有宿主值和坏标记不回退。
- `run_local_verification.py` 核对跨任务／恢复／重建、三角色权限、HOME／凭据和 CLI／API 隔离；任务研究中的 `identity_lifecycle_probe.py` 使用独立控制端进程、持久合成 SQLite 和两批真实镜像证明静态摘要、HOME／设备配置保持。真实账号、OAuth、模型和公网遥测不用于本地验收。

## Scenario: v3 只读物理特征面板与观察快照

### 1. Scope / Trigger

修改环境详情、配置与容器观察对照、物理探针或快照缓存时适用。展示已有身份和真实资源口径，采集不创建/唤醒/重建环境、不生成指纹、不调用模型或 OAuth。

### 2. Signatures

```text
GET /api/environments -> 每行增加 physical_features 与关联账号 run_window
POST /api/environments/{environment_id}/physical-features/refresh -> {ok: true}
AccountRuntime.refresh_physical_features(row: dict) -> None
validate_features(payload: object) -> dict
configured_features(row: dict) -> dict
physical_features_summary(row: dict, path: Path, now: float) -> dict
runtime/physical-features.json = {
  schema: 1, environment_id: string, generation: integer,
  container_id: string, observed_at: UTC秒, values: 白名单字段对象
}
```

### 3. Contracts

- 白名单为 runtime_type、hostname、os、kernel、architecture、cpu、cpu_visible、cpu_affinity、cpu_quota、memory_bytes、account_memory_bytes、root_disk、mac、manufacturer、product、version、family、serial、uuid、shell、package_manager、toolchain、timezone、locale、machine_id。不采集完整环境变量、命令、凭据或 machine-id 内容，后者只返回是否存在。
- 配置取已保存 fingerprint/system_profile/computer_profile，不为展示补齐身份；探针只读当前 CLI 本机文件和可执行工具。CPU 分开显示可见数量、亲和性及配额；RAM 来自实际 cgroup 上限，memory_bytes 对比 CLI 分配，account_memory_bytes 仅列账号合计预算。legacy 对比原总预算，未知不补零，0 只表示明确无限制；不把宿主总内存、RSS 或 RAM+swap 当作 CLI RAM。
- 列表只读已有缓存并沿原路径读取角色状态，不执行探针。显式刷新按 owner → profile → environment 非阻塞取锁，锁内重读当前代；由 role_container/既有归属核对定位 CLI，有活动 CLI job 或停止容器即拒绝。UID1000、/tmp 下运行 `timeout --signal=KILL 5 python3 -I -c <固定探针>`，Docker SDK 沿已有有限传输超时，不改共享 client 超时。
- 输出不超过 64 KiB，schema 必须整数 1，顶层及 values 必须精确匹配声明键。数字字段为非 bool、非负且小于 2^53 的整数；machine_id 为 bool；其它值为 null 或最多 512 字符的非空字符串，拒绝码点小于 32 的控制字符。
- 成功才 atomic_json 原子发布 root 私有 0600 快照；采集失败、超时、坏输出均保留旧观察。读取使用 O_NOFOLLOW/O_NONBLOCK，仅普通文件，限制 64 KiB；核对归属、代次类型、容器 ID、有限正 observed_at 且不超 now+60 秒。
- summary 返回 status、message、observed_at、generation、fields；字段为 `{key,label,configured,observed,status}`。快照状态 missing/cached/stale/invalid，逐字段 match/mismatch/observed/unobserved/stale；旧代或容器 ID 不符仍保留合法旧值和时间，明确标旧代。cached 只表示本代的上次观察，不承诺实时；保存值不回填到实测。
- UI 用独立列显示保存配置、容器实测及对照，标采集时间和缺失项；所有来自快照的文字先转义，窄屏可横向查看。停止/占用时禁用刷新，后端仍独立校验。刷新失败保留旧值并明确提示，不能自动修复指纹或放宽容器权限。
- 当地时钟和运行窗口沿账号已固化时区，契约见 [当地运行窗口](database-guidelines.md#scenario-v3-账号当地运行窗口与准备后复查)。物理缓存与 SQLite 时段各自独立，不互相假设采集或环境创建已执行。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| v3 未启用或环境不存在/关联账号已删除 | 404，不采集 |
| 锁占用、活动 CLI、停止或归属冲突 | 409，保留旧观察，不启动或重建 |
| 探针超时、非零退出或非法输出 | 409，固定采集失败说明，旧快照保留 |
| Docker/请求传输/系统读取失败 | 503，固定说明，旧快照保留 |
| 缺少缓存、坏格式/链接/越界或跨环境快照 | missing 或 invalid，实测未知，配置仍独立展示 |
| 合法旧代观察 | stale，保留旧时间和值，不标为当前一致 |
| 配置与实测不同 | mismatch，如实显示，不自动重抽/改写身份 |

### 5. Scenarios and Examples

- 正常：点击空闲环境的“刷新实测”，真实 DMI/CPU/内核/时区与配置一致，CLI cgroup RAM 与账号总预算分列；指纹、HOME、凭据及绑定摘要保持。
- 基础：从未采集的环境只显示配置和未采集；停止后打开页面仍显示合法上次观察，不唤醒容器。重建后旧快照标 stale，等空闲显式刷新。
- 错误用法：把 fingerprint 值填入 observed、用 /proc/meminfo 总量当 RAM，或为 GET 调 ensure。正确处理：保存值与真实观察分列，使用 cgroup 限额，列表只读缓存。
- 错误用法：把缓存文本拼成 HTML、遇到采集失败清空旧快照，或采集期间绕过 owner/profile 锁。正确处理：白名单严格校验、转义输出、成功才替换，并在锁内复核归属和代次。

### 6. Tests Required

- test_physical_features.py：无快照、实际 CLI/legacy RAM 口径、相同/差异、旧代、跨环境、坏类型/数值/控制字/额外字段及链接拒绝；配置不冒充实测。
- test_account_runtime.py：只读采集命令与截止/UID、缓存权限、停止/占用不 exec、失败不覆盖、身份和凭据保持。
- run_local_verification.py --manifest <联合清单> --run-windows-only：实际 CLI 采集 DMI/CPU/内核、cgroup、时区和 locale，核对配置、私有快照及采集前后凭据/指纹摘要。
- verify_stack.py --manifest <联合清单> --browser --run-boundaries：页面/API/SQLite 与缓存对照、停止不唤醒、来源与旧值、XSS、1280/390px 明暗主题；保持独立 API/CLI 生命周期回归。

## Scenario: v3 精简备份与不可变制品维护

### 1. Scope / Trigger

- 修改 `deploy/flower2api/manage.py` 的构建、备份或维护入口、`storage_*.py`、CLI 安装脚本及冻结项目安装时适用。减少物理副本，保留账号身份、历史成果与全部逻辑文件；不通过重建账号或重新授权换取空间。

### 2. Signatures

```text
scripts/flower2api-stack backup --env <配置> --backup-dir <全新规范绝对目录> [--full]
scripts/flower2api-stack verify-backup --backup-dir <新格式备份>
scripts/flower2api-stack storage --env <配置> --output <全新私有清单>
scripts/flower2api-stack storage --env <配置> --apply --source <清单> --output <全新回执>
storage_maintenance.acquire_storage_lock(root: Path) -> int
storage_maintenance.tree_inventory(root: Path, excluded: set[str] | None = None, *, durable: bool = False) -> dict[str, dict]
storage_maintenance.deduplicate_immutable_tree(root: Path, *, minimum_bytes=4096, owner_uid=None, apply=True, canonical_root=None) -> dict
storage_backup.verify_backup_data(target: Path) -> dict
```

### 3. Contracts

- 默认模式 `essential`，显式完整模式 `full`。数据库、HOME 身份/凭据、工作区、成果、恢复证据、未知缓存及历史内容版本保留；命令行备份同时保存配置及存在的宿主来源/密码兼容说明。Unix socket 不复制，普通符号链接原样保存。
- 仅排除精确 `home/.npm/_cacache`、`cli/.npm-cache/_cacache`，以及已证明恢复来源的程序。CLI 精确版本、公开 npm 依赖锁和程序 SHA256 必须匹配；证明来自 root 私有协议2安装回执、无网络 npm 重建，或同部署/数据根/平台且通过隔离恢复的完成备份。复用旧证明须核对完成标记绑定的恢复清单 SHA256；损坏或来源不明时包含原程序。浏览器恢复来源不足时保留。
- 当前项目版本只有经同批已核验 control 镜像在隔离目录真实重建且全树字节、权限与归属一致时才可排除，其他版本保留。共享 CLI 缓存只有全部文件被已证明的程序清单覆盖时才可排除。
- `backup-files.json` 为私有 schema2，包含 `mode/data/configuration/databases/excluded`；文件记录种类、模式、uid/gid、大小/SHA256，链接记录原目标。两库使用 SQLite backup API，保留 WAL 事务，显式关闭连接后盘点，避免清单记录随 GC 消失的 WAL/SHM。
- `verify-backup` 无需线上 env；仅校验新格式。真实复制到独立目录，恢复权限/归属/链接并核对文件与数据库 `integrity_check`、逻辑摘要。成功返回 `status=passed, files, databases, isolated_restore=true`；不回写生产凭据或数据库。
- 备份数据文件、目录、恢复清单及发布清单先落盘，再写私有 `.v3-backup.json` schema2：`mode/verified/files_manifest_sha256/deployment/source_root/layout_version/bridge_protocol/release/completed_at`。完成标记和父目录同步后才轮换；未知、跨部署、未完成和目录链接不参与轮换。
- `storage` 默认只读。schema1 清单以 `source_root/release/plan_sha256` 绑定范围，包含 `caches/content/cli/retained`；缓存条目另绑定设备、inode、逻辑清单摘要及字节数。应用必须全停机，先验证整份清单并独占预留结果文件，再用拒绝链接的目录 fd 收口精确缓存；失败回执包含 `status=failed/error_type/free_bytes`，不冒充清理成功。正常回执含清理路径、去重结果、保留原因及文件系统前后空闲字节。
- 备份、维护及 `up` 共用 `.v3-storage-maintenance.lock`；非阻塞加锁，要求当前维护用户、0600、普通单链接空文件。读取维护元数据用有界 `O_NOFOLLOW/O_NONBLOCK`，拒绝 FIFO。应用检查本部署全部运行角色，包含验证辅助容器；不处理其他应用、Docker 卷或全局 prune。
- 账号镜像用 `vibebench.cli-install-version=2` 声明暂存安装协议。安装锁内创建新目录，真实版本校验与 root 私有 `.v3-cli-install.json` 成功后发布 `.ready` 并原子替换；回执 schema1 含 `protocol=2/version/program_sha256/lock_sha256/package_sha256`。失败保留旧程序及原退出码，锁内收口同版本精确命名的遗留暂存；下载缓存回收失败不阻断已验证就绪版本。
- 管理端只对已核验协议2及隔离布局2的程序复用私有 `bench/cli-artifacts`，大文件下限1MiB；维护入口要求匹配安装回执。旧协议、未知来源或保护不足的程序保留，优化故障沿用已验证私有 CLI，不新增 Docker 查询或改变资源/租约顺序。
- 去重仅处理同文件系统、可信所有者、文件及父目录无组/其他用户写权限的普通文件；按字节、模式及uid/gid分组，替换前复核，临时硬链接后原子替换。共享缓存0700且独立于账号路径，账号没有跨账号可写挂载；HOME、会话、凭据和候选工作副本不参与。
- 项目库在构建快照 `COPY` 前和新冻结版本发布前去重，逻辑内容及摘要不变；候选仍独立复制。不能通过在后续镜像层删除文件声称释放下层空间；镜像虚拟大小不与实际文件系统收益相加。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 任一自有角色运行／部署锁已占用 | 拒绝备份或维护，不中断工作 |
| 备份目标已存在、非规范绝对路径或与数据根重叠 | 拒绝，不覆盖 |
| 恢复文件/凭据/模式/归属/数据库摘要变化 | 校验失败，保留旧恢复点，不发布半成品 |
| CLI 来源或旧备份证明无效、浏览器来源不全 | 包含或保留原程序，不扩大排除 |
| 维护清单过期、路径越界、链接/FIFO或回执已存在 | 删除前拒绝；已有回执不覆盖 |
| CLI 安装失败、返回错误版本／仅缓存回收失败 | 保留旧程序并报安装错误／就绪程序仍可执行 |
| 同字节但权限/归属不同、可写父目录或链接 | 不共享 inode，不越界写入 |

### 5. Scenarios and Examples

- 正常：停止本部署全部角色，生成默认精简备份；独立恢复通过后轮换旧副本，再按同发布清单维护，恢复服务并核对历史数据、工具启动和实际空闲变化。
- 基础：旧 CLI 无安装证明且离线重建失败，仍备份原程序；已有完整备份按原归属参与轮换，新格式才支持 `verify-backup`。需要完整工具副本时显式使用 `--full`。
- 错误用法：直接删除整个 `.cache`、`cli` 或旧版本，或在完成新恢复验证前删除原全量副本。正确处理：只应用精确清单，来源无法核验的程序保留，成功标记落盘后才轮换。
- 错误用法：将候选工作区链接到共享依赖，或重装时原地覆盖已共享程序。正确处理：候选复制独立字节，程序写入新暂存目录并原子发布。

### 6. Tests Required

- `deploy/flower2api/test_manage.py`、`test_storage_backup.py`：默认/完整、WAL事务及GC后日志消失、文件/归属/配置/链接隔离恢复、失败保留旧副本、旧格式轮换、完成来源证明复用与篡改拒绝、回执冲突和活动部署不删除。
- `services/orchestrator/test_storage_maintenance.py`：实际inode复用、字节/权限不变、幂等、目标变化、可写父目录及链接不参与、UID1000写入拒绝、缓存损坏/锁占用/FIFO及过期维护清单拒绝。
- `test_account_runtime.py`、`test_project_scenario_content.py`：两账号实际程序共享而HOME独立、旧协议跳过、缓存故障不阻断、冻结依赖去重及候选修改不污染基线。
- `deploy/flower2api/verify_storage.py --account-image <本地账号镜像> --output <全新回执>`：真实无网络Docker验证合成安装、共享、UID1000只读、失败/错版/重装、遗留暂存与缓存故障；不调用真实账号或模型。
- 构建前后逐文件核对完整项目库、Docker COPY及安装摘要，运行代表性真实离线原生观察。生产另核对身份/历史记录/工具及文件系统空闲增量；镜像保留与回收按下方“v3 部署成功后的旧镜像回收”执行，不把本地通过宣称为已上线。

## Scenario: 账号 CLI 版本与迭代抓包

### 1. Scope / Trigger

- 修改账号 CLI 设置、任一 CLI 启动入口、项目/养号抓包、停止收尾或历史读取时适用。账号默认值与执行身份分开：配置只影响后续新执行，已有运行、工作、会话与草稿保持原版本。

### 2. Signatures

```text
accounts.claude_code_version TEXT NULL
accounts.projects_capture_enabled INTEGER NOT NULL DEFAULT 0
accounts.warmup_capture_enabled INTEGER NOT NULL DEFAULT 0
runs.claude_code_version_source TEXT NULL
GET/PUT /api/accounts/{aid}/cli-settings
AccountCliSettingsIn.display_name: Optional[StrictStr]
app_settings.key = 'account_display_name:' + str(accounts.id)
CaptureRunIn.claude_code_version: Optional[StrictStr]
_resolve_account_cli_version(account: dict, value: Optional[str] = None) -> tuple[str, str]
GET /api/projects/work/{work_id}/capture
GET /api/projects/work/{work_id}/capture/file?path=<相对文件>
GET /api/accounts/warmup/pi/work/{work_id}/capture
GET /api/accounts/warmup/pi/work/{work_id}/capture/file?path=<相对文件>
capture_artifacts.capture_summary(base: Path, *, running: bool = False) -> dict
execution_role = pi-capture
network ACK: previous_listener_graceful: bool
capture-status.json: source, state, updated_at, recorder_graceful?, message?
```

### 3. Contracts

- 新列用 `_ensure_column` 幂等补齐，旧账号两个开关均关闭。PUT 仅写显式字段；版本为可空严格字符串，trim 后空值清除覆盖，开关为严格布尔，未知字段拒绝。GET/PUT 返回 account_id、display_name、配置版本、effective_claude_code_version、claude_code_version_source 与两个布尔开关；来源为 account/global。读或保存不准备环境、启动模型或热切网络。
- `display_name` 是显示别名，trim 后须为1～128字符且不含ASCII控制字符。省略保持，null或原name清除别名。保存在已有 `app_settings`，与同次版本修改共用事务；账号列表一次联表读取，可空别名由页面回退到name。原name参与路径、锁与授权身份，禁止随显示名修改；账号ID、profile_path、环境、凭据及历史保持。旧客户端省略此字段继续兼容。
- 精确版本解析优先级为单次显式值 > 账号配置 > 全局有效值，来源 explicit/account/global。账号页和两个迭代窗口读取同一权威版本；迭代窗口只提交本空间开关，缺失字段不覆盖另一空间。版本、安装准备、PATH 与 exec 环境必须一致，失败不能静默换版本。
- 所有 CLI 入口采用账号继承：普通/批量、抓包、项目/养号、兼容项目及 CLI 评审、登录/重授权、续聊和实际 CLI 维护命令。新 run/work/session/draft 保存版本，恢复优先已有快照；旧空 run/work/草稿只回填一次并记录 legacy-* 来源，run 优先匹配原执行证明。只读进程/身份观察不能用当前默认值冒充实际已执行版本；选择版本不升级 cc2api 画像或已验证身份来源。
- 项目和养号在新执行开始时读取账号的本空间开关，并在执行定位中记录 capture_enabled 和分代路径；既有 work 的版本快照不重写。关闭时沿共享 CLI/passthrough，兄弟作业存在时必须复用监听；开启时 `shared_cli=False, exclusive=False`，使用现有 `prepare-cli`，等待同账号 CLI 空闲，独立 API 继续可用。
- 捕获使用 pi-capture 监督角色，仍凭 source/PID/started、逐作业 tmux、启动许可和租约控制。保存并恢复 settings_override、network_inspection_mode、capture_flows；不能将独占租约伪装成 shared_cli 或 project-review。Recorder 按当前来源 ACK 后才启动 CLI，仅捕获进程显式信任 CA。
- 收尾先停止本作业，再恢复 passthrough 并释放租约。网络 ACK 返回 previous_listener_graceful；本代 capture-status.json 状态为 stopping/closed/partial/error，强制收口或未知优雅状态不能冒充完整。重启时可凭原环境行定位网络角色；不能确认收口则保留证据与 cli_reconcile，不停止健康独立 API。
- 工作读取从本空间 work、账号与固定环境派生 `group-<hash(namespace/work)>`；不接受任意宿主路径，不把 work ID 当 run ID。运行与双迭代共用脱敏聚合，保留旧平铺、分代及同账号受管续聊组链接。摘要含 files、index、index_available、sample_count、status 和 message，状态为 empty/collecting/partial/complete/error；索引缺失但已有数据仍列文件。
- `/capture/file` 只预览本组清单中的脱敏 capture_index.json、收尾摘要及 TLS 白名单；原始 HTTP、.flow、握手字节与凭据正文不公开。停止或关闭开关不删除旧数据，新代输出不覆盖原代。Recorder 的追加阶段及协议研究边界见 [正式抓包契约](../../platform/deploy/official-protocol-capture.md#35-条件标识正文归因与-tls-的采集边界)，TLS 存储与摘要遵循下方 ClientHello 场景。
- 配置和查看窗口在切账号、切空间、关闭时使旧回执失效，不覆盖新页面或未保存输入。工作抓包通过手动刷新读取，关闭不新增常驻轮询；运行详情沿原生命周期。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 账号/全局均空覆盖，旧账号无开关值 | 全局版本兜底、抓包关闭 |
| PUT 只提交一个空间开关或版本 null | 仅改该字段；null 清版本，另一空间保持 |
| 非法版本 / 非布尔开关 / 未知字段 | 400 / 422 / 422，不保存无效值 |
| 空白、超过128字符、含控制字符的显示名 / 非字符串显示名 | 400 / 422；同次版本修改一并保持原值 |
| 省略display_name / 显式null | 保留别名 / 清除别名并显示原name |
| 账号不存在或已软删除 | 配置接口 404，不启动执行 |
| 修改默认值后恢复排队运行、work、会话或草稿 | 已有非空快照保持；旧空值持久回填一次 |
| 捕获遇同账号兄弟 CLI | 等待，不能重启兄弟监听或排空独立 API |
| Recorder 强制收口、退出失败或响应中断 | 保留文件，报告 partial/error 或 interrupted，不假报完整 |
| 工作/文件不属于当前空间或路径不受支持 | 404；无环境和文件时抓包摘要为空状态 |

### 5. Scenarios and Examples

- 正常：全局 293、账号 303，抓包显式 293 只影响本次；之后未显式覆盖的执行仍用 303。清空账号配置后新执行继承全局，历史仍展示冻结值。
- 基础：项目开启捕获，养号仍关闭；保存不启动模型，下一次项目执行等 CLI 空闲后捕获，养号继续共享透传。关闭后旧抓包可查。
- 正常：`{display_name:"团队账号",claude_code_version:"2.1.303"}` 同次保存；原name为main时，其配置目录与授权仍使用main。错误：把显示名直接写回accounts.name或拼进路径。修正：只写独立别名键，显示时使用display_name/name回退。
- 错误用法：把单次版本输入放进 batch-form，只测试后端创建接口；抓包创建成功后清空不存在字段又报失败。正确处理：控件归属 capture-form，浏览器实际提交并检查请求、清空、详情和无错误弹窗。
- 错误用法：Recorder 停止后的迟到 response 把 interrupted 改回 complete。正确处理：保留单调中断事实，仅追加实际收到的字节；合成流量通过不等于正式协议画像通过。

### 6. Tests Required

- `test_account_cli_settings.py`：真实 SQLite/API 验证严格类型、增量更新、旧库幂等升级、继承组合、创建事务重读账号、旧 run 执行证明优先及登录版本稳定。
- 显示名覆盖原账号行、路径、凭据及历史快照保持，非法组合零写入、旧客户端省略保持、null恢复与列表回读。`verify_task_account_config.py`连接真实配置API，验证名称保存/取消、子窗草稿、局部路由、维护操作、迟到回执和原型计算样式。
- `test_capture_settings_runtime.py` 与 `test_account_runtime.py`：两个空间共享/独占分支、精确版本/PATH/CA、监督记录、租约/代次保护、恢复字段、文件隔离和受限预览；关闭不影响共享执行。
- `images/sidecar/test_recorder.py`：请求先落盘、索引同流去重、停止/错误为 interrupted、迟到 response 不覆盖中断；`images/account/test_network_context.py` 核对忽略 TERM 的监听器定向强停及 false 结果。
- 实际浏览器提交三种版本来源，验证表单归属、成功重置、详情、账号/全局设置保持及无错误弹窗；两个空间配置默认关闭、切账号、旧 GET/PUT 回执、明暗和窄屏均覆盖。
- 本地真实 HTTP/SSE + mitmdump 验证完整流后中断、JSONL/索引/stats/.flow 保留与新代不改旧文件哈希；真实账号和生产并行验证按发布授权单列，不以模型或 usage 请求探测配置。

## Scenario: 迁移验收后的旧部署永久退役

### 1. Scope / Trigger

- 用户明确选择永久删除、不归档，且迁移收据和当前 v3 目标账号均验收通过后适用；与只清旧发布镜像的日常流程分别执行。

### 2. Signatures

- 只读 `docker inspect`、`docker volume inspect`、`/proc/self/mountinfo` 盘点；执行只用精确容器 ID 的 `docker stop/rm`、精确卷名的 `docker volume rm` 和精确标签/digest 的 `docker image rm`。
- 私有 `plan.json` 冻结路径 realpath/inode/device、容器身份与挂载、卷元数据、镜像全部别名、配置摘要、保护发布和磁盘基线；`result.json` 逐项记录完成事实与最终实际空间差，不含源数据库、凭据或历史数据副本。

### 3. Contracts

- 顺序：迁移验收 → 下游退出旧入口 → 旧任务与网关全部账号排空 → 冻结清单 → 重新核对全部引用 → 停止/删除指定旧服务 → 删除固定旧挂载与已证明归属的旧备份/凭据副本 → 删除命名卷和无保护引用旧镜像 → 健康及空间复核。
- ai-fund 先部署旧来源显式停用，再移除旧地址/管理 Secret；NewAPI 等价切流保留原渠道 ID、模型、分组、并发及额度关系，密钥只在私有传输和进程内存中交接。
- 路径只接受固定父目录下已盘点的精确目标，拒绝链接根、嵌套挂载、任何其他容器的父子路径引用；递归不跟随链接。不删除整个源码父目录或 Docker 私有存储；命名卷必须经 Docker 删除。
- 不新建归档。已确认属于旧部署的既有数据库/镜像/配置备份一并纳入清单；未知及共享资源保留。日常镜像保护集继续覆盖当前和最近两套完整 v3 发布，以及全部非目标容器引用。
- 每次删除前重查引用、配置与身份；失败记录已完成事实和剩余项，不 force、不 prune、不盲目重跑，不把授权扩大为全机清理。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 缺少迁移验收、仍有旧消费者或在途工作 | 拒绝删除 |
| 归属、inode、配置或容器引用变化 | 停止相关删除并对账，保留已完成事实 |
| 旧卷没有 Compose 标签 | 必须核对固定卷元数据、精确旧容器身份、Compose 归属及实际挂载，不能猜标签 |
| Docker 删除失败或目标仍存在 | 不强制重试，不声称完成 |

### 5. Scenarios and Examples

- 正常：旧渠道等价切至 v3、旧来源停用、迁移目标健康，按冻结清单永久删除旧数据及旧副本，只留无秘密收据。
- 边界：共享挂载或未知文件不进入清单；v3 当前数据和两套历史发布保持。
- 错误：仅删除旧来源地址而保留自动启用的凭据，或直接清 Docker 卷底层目录。修正：先显式停用消费方，核对全部引用后通过 Docker 删除精确卷。

### 6. Tests Required

- 执行前验证真实收据字段、实时账号/任务排空、全部容器引用、路径边界和保护镜像；过期消费方证明、未知资源或身份变化必须拒绝。
- 执行后确认旧容器/路径/卷/镜像不存在、所有保留容器 ID/镜像/启动时间/重启次数和配置摘要保持；页面 200、未登录管理 API 401、数据库只读 quick_check=ok。报告同一文件系统实际可用字节差，不累加镜像虚拟大小，不发送真实模型探针。

## Scenario: v3 部署成功后的旧镜像回收

### 1. Scope / Trigger

- 每次 v3 生产部署完成健康验收后必做；磁盘空间不足时也按此流程定向清理。2026-10-27 生产曾因多批旧镜像累积，仅余约 457 MiB。`manage.py pull/load/up` 没有自动回收旧镜像，部署执行者必须完成本步骤。
- 本步骤只回收已核对的旧发布镜像；数据缓存与不可变制品维护继续走上一场景的停机、归属及锁契约。

### 2. Signatures

```text
df -h <V3_DATA_ROOT>
docker system df
docker ps -a --no-trunc --format '{{json .}}'
docker image ls --no-trunc --format '{{json .}}'
docker image inspect <精确镜像引用>
docker ps -aq --filter ancestor=<精确镜像引用>
docker image rm <精确旧批次标签>
docker image rm <已核对属于同一旧镜像的仓库@sha256引用>
```

- 当前批次与镜像来自生产 `V3_RELEASE`、`V3_CONTROL_IMAGE`、`V3_ACCOUNT_IMAGE`、`V3_RELEASE_MANIFEST`；不输出配置中的秘密。
- 私有审计目录保存 `plan.json` 与 `result.json`；结果包含 `status`、`removed_images`、`before/after.{total_bytes,free_bytes}`、`freed_bytes`、`protected_releases`、`original_containers_preserved`、`running_containers_preserved`、`deployment_unchanged`。

### 3. Contracts

- 顺序固定为：盘点磁盘和全部容器/镜像 → 发布与健康验收 → 冻结保留集和精确删除清单 → 逐项复核并回收 → 复核空间、服务与部署配置。升级失败或尚未验收时不清理回退镜像；没有可回收项也要记录检查结果。 每次成功部署都必须完成这次定向回收并记录结果，旧镜像不能随发布批次无限累积。
- 保留当前已验收批次、最近两个完整历史批次的 `control/account` 镜像对，以及显式回退/恢复方案仍需要的镜像。再合并宿主**全部容器（包括已停止容器及其他部署）**实际引用的镜像 ID 和引用；不能因旧容器已停止就删除其镜像或先删容器以释放引用。
- 仅候选发布清单归属明确、产品标签 `vibebench.product=v3`、`vibebench.role=control|account`、`vibebench.release` 与精确仓库/批次相符，且不在保留集中的镜像可删除。核对清单与实际配置/OCI 身份；未知来源、额外未知标签或跨应用引用均保留。
- 每次删除前重读当前部署引用和容器占用；部署发生变化或新容器开始引用候选时停止后续删除。只执行精确引用的 `docker image rm`，不使用 `--force`、`docker system prune`、`docker image prune -a` 或 volume/container prune。
- containerd 存储可能同时保留批次标签和 `repository@sha256` 引用。只有确认它们属于同一候选镜像、无其他保护引用后，才逐个移除并确认目标镜像已不存在；只移除标签不能算实际回收。
- 全程在线，不停止或重建服务，不修改数据库、账号 HOME/凭据、会话、工作区、项目成果、冻结历史、有效备份或其他应用资源。镜像回收不能借道删除 Docker/containerd 底层文件。
- 本步骤不新建数据备份；清理前只保存不含秘密的计划与容器状态元数据，逐项记录结果，不能复制数据库或整份状态制造新快照。私有目录 `0700`、记录 `0600`。失败保留已完成事实和剩余清单，明确报告收尾未完成，不为继续清理扩大范围。
- 以同一文件系统实际 `after.free_bytes - before.free_bytes` 报告释放量，不能累加镜像虚拟大小。清理后核对原容器 ID、镜像、启动时间及重启次数，运行中容器仍运行，网关健康、页面与鉴权正常，配置摘要和受保护镜像保持。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 新批次健康、旧镜像身份匹配且无引用 | 按精确清单在线删除，复核实际释放量 |
| 当前批次、最近两个完整历史批次、容器引用或显式恢复依赖 | 保留并记录原因，不删除旧容器绕过保护 |
| 发布未验收、归属未知、额外未知引用或部署发生变化 | 不删除相关镜像；部署变化时停止剩余清单 |
| Docker 拒绝移除、超时或删除后镜像仍存在 | 记录失败与已完成项，不加 `--force`，不宣称回收完成 |
| 没有合格候选 | 记录零删除和当前空闲空间，仍完成服务复核 |

### 5. Scenarios and Examples

- 正常：2026-10-27 定向删除 8 批共 16 个无容器引用的镜像，实际释放 `27,255,869,440` 字节，磁盘占用从 100% 降至 74%；26 个原容器保留，11 个运行中容器未重启，当前批次和最近两个完整历史批次保留。
- 边界：历史账号仍有已停止容器引用旧 `account` 镜像，保留该镜像；空间统计中的 reclaimable 不等于本次授权删除清单。
- 错误用法：每次只拉新镜像而跳过收尾，或看到磁盘满就全局 prune。正确处理：每次部署健康验收后按发布身份和全部容器引用定向回收，并记录最终空间。

### 6. Tests Required

- 计划核验：当前批次、最近两个完整历史批次、显式恢复依赖及运行/已停止容器的镜像均不进入删除清单；额外未知引用拒绝删除。
- 执行核验：逐项删除前重查部署和占用，引用变化及 Docker 拒绝时不强删；确认批次标签和已核对的 digest 引用均已移除，目标镜像实际不存在。
- 生产复核：清理前后 `df` 字节差、保留镜像身份、全部原容器 ID/镜像/启动时间/重启次数、网关健康、页面 200 及未登录管理 API 401；数据库只读 `quick_check=ok`。审计不得含凭据，不调用真实模型作为探针。

## Scenario: 客户端 ClientHello 私有证据与安全摘要

### 1. Scope / Trigger

- 修改 Recorder TLS hook、任一完整抓包入口、网络 context、抓包摘要或预览时适用。普通 run／续聊、Projects 与 warmup 共用；没有完整抓包时不增加 TLS 文件或握手。
- 本契约仅覆盖客户端到 Recorder 的 TCP ClientHello；官方 CLI 归因须结合真实 HTTP。cc2api TLS 模板、JA4、无解密透传对照、DTLS／QUIC／ECH 内层及 HRR 二次事件完整覆盖另行验证。

### 2. Signatures

```python
Recorder.tls_clienthello(data: tls.ClientHelloData) -> None
parse_clienthello(raw: bytes) -> dict[str, Any]
capture_context_snapshot(raw: str, quota_source: str) -> tuple[dict[str, Any], str, str | None]
append_private_jsonl(path: Path, record: dict[str, Any]) -> None
capture_context_json(source: str, version: str, *, run_id: str | None = None,
    namespace: str | None = None, work_id: str | None = None,
    version_source: str | None = None) -> str
capture_summary(base: Path, *, running: bool = False) -> dict
capture_file_preview(base: Path, relative: str) -> dict
CAPTURE_CONTEXT = JSON({schema: 1, source, claude_code_version, ...})
```

### 3. Contracts

- 固定 mitmproxy 11.1.3 的 `data.client_hello.raw_bytes(wrap_in_record=False)` 返回 **ClientHello 本体**；不含 handshake／record 头。`raw_format=clienthello_body`、`tls_record_preserved=false`；默认 SDK 合成 record 不能当原始 wire／pcap。
- 新文件为 `Path(CAPTURE_FILE).with_name('tls_clienthello.jsonl')`，仅 `CAPTURE_FULL_HTTP=1` 时追加；沿实际分代目录，不覆盖同 source 的前次字节。逐级 `dir_fd+O_NOFOLLOW` 打开父目录，目标必须是单链接普通文件，以 `0600` 创建／追加；拒绝文件、父目录链接、硬链接和 FIFO。
- 每行 `schema=1/event=tls_clienthello/ts/direction=client_to_recorder/transport=tcp/client_connection_id`；连接键取 `data.context.client.id`。HTTP 原始记录和轻量索引使用 `flow.client_conn.id` 的同名键及同一上下文，允许一条握手对应多个 flow；不能用 server ID 或猜未来 flow ID。
- 私有原始字段 `raw_base64/raw_bytes/raw_saved_bytes/raw_sha256/raw_truncated` 表示保存本体、全长、保存长度、完整本体 SHA256 和截断事实；最多保存 256 KiB（覆盖合法本体）。超限为 `parse_status=oversize`，明确截断且 JA3 为 null。正常／结构错误／SDK 不支持分别为 `ok/error/unsupported`，固定 `parse_error` 不含异常原文。
- 保留原序 `legacy_version/cipher_suites/extensions/signature_algorithms/supported_groups/supported_versions/ec_point_formats/key_share/sni/alpn_protocols`。扩展为 `{type,length,data_base64}`，key_share 为 `{group,key_exchange_length}`，ALPN 为 `{text,base64}`；缺扩展用 null，合法空 client_shares 用 `[]`。验证长度、偶数向量、重复扩展和 key_share 边界；未知 ID／GREASE 留在原始字段，不按名字表丢弃。
- `ja3={string,md5}` 使用 legacy_version 与原序 cipher／扩展／组／点格式五字段，仅在 JA3 投影中过滤标准 GREASE。TLS1.3 的 legacy_version 仍为771；签名算法、ALPN 和 key_share 具体值不能由 JA3 推出，JA3 不作为安全身份。
- TLS 目标范围沿 `CAPTURE_SCOPE/CAPTURE_TARGETS`：all 全收；显式非目标 SNI 跳过，缺 SNI／尚不可归因保留为 unclassified，不据目录或 IP 推断官方 CLI。此策略不改变 HTTP `_should_record`。采集／解析／写入异常只写固定 TLS 诊断，不更改握手参数或取消 TLS／HTTP 转发。
- `CAPTURE_CONTEXT` 在 Recorder 初始化时冻结并逐字段筛选；`source/claude_code_version` 必需，可选真实 `claude_code_version_source`。run／continue 填原 run_id，Projects／warmup 填 namespace/work_id，不能把 Pi 兼容 job.run_id 冒充 runs.id。五个入口必须取本次实际装载的版本，并通过 network-context 环境允许列表；缺失、非法、source 冲突分别为 missing／invalid／source_mismatch，版本未知，不查当前默认值猜测。现有 ACK 只核原模式／来源，元数据另核实际环境和产物。HTTP `analysis.cc_version` 仍表示 HTTP 观察结果。
- `capture_summary.tls_clienthello` 和双空间既有 `/capture/file` 共用逐层白名单；普通 run 沿既有摘要，不新增文件路由。只公开时间、方向、连接、受支持上下文、数值 offer、扩展类型／长度、key_share 组／长度、SNI、文本 ALPN、JA3 和状态。raw_*、扩展 payload、session/ticket/PSK/binder、未知字段及异常原文不公开。
- 全组共用最多4MiB、256行、64条有效记录预算，单行512KiB、公开向量4096项。半行、坏记录、非法公开字段或向量截减、读取异常及未读完必须报告 partial／issues／truncated；不完整时 `count_exact=false,total_records=null`，不能将有界扫描数称为精确总量。旧目录无TLS正常为 unavailable。共用 `renderCaptureDetail` 展示最多8条安全记录及 HTTP 连接键；动态值经 escapeHTML，保留原切换／关闭请求失效逻辑，更新 app.js URL 版本。
- v3 COPY 整个 sidecar，旧 sidecar Dockerfile 显式 COPY helper；两条打包路径必须均可导入，不能仅本地 PYTHONPATH 通过。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 关闭完整抓包／历史无TLS | 不读握手；无新文件，读取正常为空 |
| 上下文缺失／非法／source不同 | 明确未知状态；不猜版本，不阻断业务 |
| 截断、向量错误、重复扩展／超限 | 保留可用私有证据与固定错误；不生成完整 JA3 |
| 合法空 key_share／未知组或 GREASE | 保留原事实；只在 JA3 投影过滤 GREASE |
| 文件或父目录链接、硬链接、FIFO、写失败 | 拒绝写入、固定诊断，HTTPS 继续 |
| 非清单、跨空间、绝对或上跳预览路径 | 沿既有404，不扩展原始 HTTP／flow 权限 |
| 半行、坏JSON、嵌套材料、预算不足 | 白名单丢弃私有值，明确 partial 与非精确计数 |

### 5. Scenarios and Examples

- 正常：`projects:work:3` 实际装载2.1.303，同一客户端连接两次 messages；TLS 与两个 HTTP flow 使用同一连接键和 namespace/work_id。账号默认版本随后改变，不改 Recorder 的固定快照。
- 边界：旧TLS1.2无extensions仍可算五字段 JA3；TLS1.3提供空 client_shares 合法。未知ALPN字节留私有base64，公开显示非文本协议。
- 错误用法：把 `TLSv1.3` 写成772算JA3，或把默认 raw_bytes() 的合成record当原始抓包。正确处理：独立解码已保存本体，使用本体legacy_version及原序有序扩展，另核支持版本和采集方向。
- 错误用法：将整个 TLS JSON 原样返回，或把64条扫描结果当全部握手。正确处理：逐层重建已定义字段，受预算时保留非精确计数及部分状态。

### 6. Tests Required

- `images/sidecar/test_tls_clienthello.py`：官方JA3向量、GREASE／未知ID／非文本ALPN、每字节截断、错误向量／重复扩展、合法空key_share、超限、上下文未知及私有追加／链接／硬链接／FIFO。
- `images/sidecar/test_recorder.py`：hook方向与scope、不改握手策略、同连接多HTTP及索引、固定快照、写失败继续转发、部分／中断阶段和原额度回归。
- `test_capture_settings_runtime.py`、`test_main.py`、`test_account_cli_settings.py` 与 `images/account/test_network_context.py`：五入口实际冻结版本、原run与work分离、真实子进程环境、源允许列表、关闭／收尾保留及三入口摘要权限。
- `test_tls_capture_artifacts.py`：嵌套canary、全组预算、半行／损坏／缺指纹／链接／读错误、旧数据、合法空值、共用渲染和XSS。已有账号运行生命周期定向回归覆盖独立API及历史目录。
- 将 `deploy/flower2api/verify_tls_clienthello.py` 挂入固定11.1.3隔离账号镜像，仅回环模拟上游：TLS1.2／1.3各同socket两GET，独立BytesIO／struct核全部字段和JA3，核HTTP/index连接；真实写失败后另两GET成功。此结果标 synthetic，不能充作官方CLI样本。
- 上线核同批Actions／镜像源码、真实项目新文件0600、执行版本／来源及成功Claude HTTP连接，独立复算并验证真实鉴权页面的安全展示；目标版本完整对齐仍需无解密透传对照。

## Scenario: V3 原生 sender 共享映像池与资源预算

### 1. Scope / Trigger

- `request_backend=native293` 在现有账号 sender 内执行固定 293 独立二进制。三角色及凭据所有权继续遵循本文件；账号/Gateway 合同见 [按账号选择固定 293 原生后端](../../gateway/backend/service-architecture.md#scenario-按账号选择固定-293-原生后端)。
- 实现依据：`services/orchestrator/{native_sender,account_runtime,resource_budget,account_isolation}.py`、`images/v3/Dockerfile` 与 `services/gateway/src/service/native_runtime.rs`。

### 2. Signatures

- `AccountRuntime.ensure(..., prepare_sender: bool = True) -> tuple[dict, object]` 在原参数尾部增加准备职责；默认仍准备目标发送器。`_applied_native_sender(row: dict) -> dict | None` 读取并核验已生效布局。

- `sender_config(configuration:dict,memory:str,swap:str='0',budget:str|None=None) -> dict|None`；configuration 的后端及 concurrency 来自网关权威快照。
- `NativeSenderConfig = {binary_path,work_root,memory_mib:u64,max_workers:usize}`；legacy 的 native 配置为 None。
- `V3_NATIVE_PREWARM_ACCOUNT_ID` 缺省为空，可配置一个正整数网关账号 ID；`SenderConfig.native_adaptive_prewarm` 为私有布尔字段，旧配置缺省 false。
- 有限账号显式环境键 `V3_NATIVE_SENDER_MEMORY`；构建可选 `V3_NATIVE_RUNTIME_ASSET` 指定本地候选，否则下载固定 beta.6 附件。`stage_asset(destination:Path,source:str|None=None) -> dict` 冻结版本/大小/SHA。
- `account_limits(memory,swap)`、`isolated_account_limits`、`scenario_account_limits`、`serial_review_limits` 接受账号 `mem="unlimited"`，无限模式 Docker 额度为 `(0,-1)`；`memory_bytes` 继续只解析有限配置。 `default_account_memory(values:dict|None=None)->str`统一解析部署策略，`V3_ACCOUNT_MEMORY`缺省/空值为unlimited，显式有限值继续校验；`AccountRuntime._apply_unlimited_memory(row,image,*,startup_prewarm:bool)->None`在原环境锁内应用策略。
- fingerprint 可选 `native_sender_memory`，无限原生账号保存 `"unlimited"`，布局变更时保存，回退 legacy 时移除；镜像原生能力标签为 `vibebench.native-runtime=293-raw-1`。
- `AccountRuntime.native_preparation_snapshots() -> tuple[dict[int,dict],str|None]` 通过一次 `GET /admin/native-preparations` 读取批量快照，超时3秒；`native_preparation_summary(row,account,snapshots,read_error=None) -> dict|None` 为 `/api/environments` 生成安全的 `native_preparation`。

- `POST /api/environments/{environment_id}/native-preparation` 校验唯一账号绑定、环境 ready/stopped 及当前目标 native293，代理管理员 `wake=true` 入队；维护或非原生为409，准备通道失败固定503。
- `NativePreparationBlocked(ValueError)` 携带 `reason`；私有 transport 503 通过 `x-v3-runtime-reason` 仅传递 `native_sender_budget_missing|native_sender_budget_insufficient|account_memory_insufficient`，未知错误保持通用准备失败。

### 3. Contracts

- API transport、显式原生准备、启动预热及原生设置切换继续使用严格默认，按权威后端、并发和部署sender预算生成目标布局。CLI、额度查询、本地OAuth刷新、身份/指标读取、独立评审及系统更新rebuild/restore显式传 `prepare_sender=False`，沿已生效布局准备基础环境。
- CLI准备核验私有sender配置、固定binary/work路径、整数memory_mib/max_workers与指纹的native_sender_memory；已登记角色缺配置、链接、损坏或预算矛盾均拒绝。历史release/kernel_generation退出执行选择。运行中的CLI准备沿用已冻结资源与能力；停止唤醒按目标镜像补齐完整内置安装表并核对CRIU／采集策略，沿原空闲重建门禁执行。CLI保持原资源预算及按需预热边界。
- 首次环境没有已生效native时使用原基础三角色布局。目标native293保持，API原生准备仍在取得投递绑定前拒绝有限预算缺失、格式错误或账号总量不足；基础布局不授权目标原生请求转用legacy业务发送。已有native沿冻结实际预算重建和恢复，CLI不会将其改回基础布局。

- `/api/environments` 的 `request_backend` 表示权威目标，实际 sender 布局独立判断。目标原生而本地 native 为空时，只投影白名单等待、维护或失败摘要，PID 与进程数保持未观测；预算失败也可显示在 stopped 环境。真实 ready 继续核验当前身份、环境/内核代次和新鲜度。
- 页面准备中以2秒串行读取，普通状态20秒读取。显式重试沿唯一绑定及同一准备队列，离页/旧 generation 响应丢弃；读取零唤醒，准备基础、CRIU 模板及 TLS 采集分别展示。

- 原生进程上限为 `2*concurrency`，覆盖普通请求2单位和Haiku1单位。双版本合计共享物理上限；普通exec的双版本及历史293单版均不按固定MiB公式限制并发。有限sender显式正数额度继续冻结并落实到实际cgroup，账号总RAM须覆盖sender、network256 MiB及CLI最低512 MiB。legacy sender仍为128 MiB。安装表、版本化私有合同与独立准备/升级记录见[双版本自动选择](../../runtime/backend/runtime-contract.md#scenario-双版本自动选择与独立来源准入)。
- 账号 `fingerprint_json.mem="unlimited"` 取消network/CLI/sender与静态/串行评审的RAM/swap限额；额外swap保存原值并校验格式。全局 `V3_ACCOUNT_MEMORY`缺省或空值为unlimited，显式有限部署配置继续沿首次冻结预算。预检保留宿主余量及显式最低可用RAM；尚未迁移的有限环境按最大RAM/swap乘活跃账号数计入，有限全局继续拒绝超出其冻结预算的历史环境。无限模式直接共享宿主资源，不能把零上限当作零占用。
- 部署无限策略在空闲ensure阶段迁移旧有限指纹，独立于CLI/API的prepare_sender职责。平台更新门禁关闭、startup_prewarm、活动CLI/API、串行评审或内核维护时保留原环境，迁移顺延；扫描及只读解析不唤醒停止环境。迁移先核验实际sender和原预算，再经共用 `_rebuild_idle_environment` 验证持久执行记录、CLI孤儿及排他maintenance租约；保留env ID、身份、HOME、会话和CPU策略，按原生命周期重建。实际native的memory_mib及指纹native_sender_memory一并变为0/unlimited；发布中断进入reconcile，禁止混合预算继续创建。已有部署显式1536m需在上线窗口改为unlimited。
- 无限账号生成 `NativeSenderConfig.memory_mib=0`，缺省 sender 预算也可准备；正数表示实际有限额度，max_workers 始终为正数，版本/摘要/身份/目标/代次及并发许可保持。指标与配置内存均以 0 表示无限，界面显示“未限制”；评审交接接受精确 `(Memory=0,MemorySwap=-1)`，CPU/PID 仍必须有限有效。
- N=3、max_workers=6与N=4、max_workers=8的合法有限配置均按实际额度准入。配置限额、共享映像字节数和实际cgroup占用分别报告，过小额度可能触发真实准备或运行资源不足；CRIU恢复额度继续独立判断。
- 原生sender为UID1001，私有可写 `/native` 与CLI UID1000/HOME分离。PID限额 `128+32*max_workers`；CPU份额保持三角色规则，有限模式额外swap只归CLI。CLI指标、physical_features及静态/串行评审从同一冻结sender预算计算剩余份额。
- 每次新进程先核验固定分发体，通过FD启动，握手验证PID/版本/raw_input_protocol，再核实际执行体SHA。首个实际映像要求 WRITE/GROW/SHRINK/SEAL 四项封存，池缓存只读FD；后续重新exec共享同一dev/inode。分发/执行体固定摘要由消费者代码及桥接运行时合同登记，外部manifest不授信。
- CRIU恢复同样要求实际exe与池缓存共享dev/inode，并继续核验SHA、大小和四项封存；控制器持有root归属0555的封存映像，各实例独立打开FD，exe及目标VMA复用同一背板。独立进程、会话、私有页、绑定代次及唯一投递保持原合同，详细准入与生命周期见[原生CRIU热模板恢复协议](../../runtime/backend/runtime-contract.md#scenario-原生进程池-criu-热模板恢复协议-1)。共享上线初期保持保守恢复预算 `256+max_workers*(192+108)` MiB；旧画像缺 `shared_memfd_restore=1` 或恢复准入失败沿受限普通exec回退。
- 每个进程独立HOME/config/cwd、当前bearer及worker_id，每轮独立原生根。账号/身份/代理/凭据/并发摘要改变产生新代次，旧活动自然收口，空闲旧进程退役。单进程一次作业，唯一终态及匹配idle后复用；取消、迟到/损坏帧和状态不明均退役。
- 单个弱引用回收任务在额外进程默认空闲120秒后保留1个基础暖进程；忙进程保持当前归属。映像缓存可在所有原进程退出后支持重建，池销毁释放FD。全局`native_idle_timeout_secs`支持30–3600秒，后台巡检同步并唤醒旧计时器；完整接口和兼容合同见[空闲回收时间热配置](../../gateway/backend/settings-database.md#scenario-原生额外空闲进程回收时间热配置)。
- 运行中原生账号由网关每20秒零模型巡检并按需恢复，具体身份、退避和计时合同见[原生持续预热](../../gateway/backend/service-architecture.md#scenario-原生持续预热实时就绪与请求进程诊断)。普通巡检只查询已有绑定，不唤醒休眠环境。显式保存原生选择与重试由网关在门禁释放后允许唤醒。
- 批量客户端仅精确GET /admin/native-preparations接受最多4096项对象数组，其余路由继续要求对象。快照返回本次映射及read_failed；缺账号快照为snapshot_missing。页面按实际配置展示adaptive_prewarm，读取保持零模型操作。
- `native_preparation.state=maintenance` 仅保留已知 `system_maintenance|maintenance` 原因，分别表示平台更新与账号维护；其它原因回到账号维护固定说明，PID 和进程数保持未观测。平台维护与真实失败恢复调度遵循网关原生持续预热合同，页面读取继续零写入。
- 环境摘要先核验账号绑定、环境 ID/代次及本地 sender 的 `native.kernel_generation`；检查时间必须在当前时间前0～45000毫秒。只投影受控 state/reason、检查时间、环境归属和非负进程数/正 PID。ready 必须同时有空闲进程和 PID。历史 `native_kernel` 预热回执继续作为历史信息。
- `native_preparation.checking?:bool` 只在网关值严格为 true 时为真，仅表示后台检查进行中；不能授予 ready 或进程归属。首轮缺少环境 ID、整数代次或已配置的内核代次时返回 unknown/snapshot_pending；已有受控检查失败原因继续保留。身份冲突仍为 binding_unverified，过期仍为 check_expired，这些分支均不提供 PID 或进程数。
- 环境页将 snapshot_pending/snapshot_missing 区分为“正在检查”或“等待快照”；身份冲突、过期及读取失败分别展示真实原因。同代新鲜结果通过既有20秒串行 GET 自动恢复就绪。旧响应缺少 checking 时继续按原状态与原因展示，页面读取不主动准备或刷新凭据。
- 启动预热只解析唯一绑定且启用的原生账号；复用环境启动和既有首 worker 准备。有空余环境容量才启动新角色，保持原账号回收与维护策略。启动补偿有界，服务运行期间不循环唤醒。
- 首条业务拿走唯一进程且账号允许两条普通并发时，sender 可为当前代次登记一次后台补位。首条直接投递；后续请求优先取空闲进程，缺空闲时可在自己的截止前等这一轮就绪。补位失败沿现有 checkout 路径处理。补位使用原物理计数与已核验映像，只提交初始化指令；结果通过真实握手后进入同一空闲池。
- 布局/预算变化只在job和API活动为空时重建。配置事务已停sender时复用 `_running_sender_active` 记零活动；运行中读取真实活动，归属或查询失败仍拒绝重建。
- SOCKS5/5h使用逐进程随机Basic鉴权的回环CONNECT，固定目标 `api.anthropic.com:443`，保持原生TLS；socks5本地DNS、socks5h代理DNS。隧道不构造业务请求，生命周期绑定进程。
- 镜像构建冻结正式beta.6附件，校验27388048 B及分发SHA `fce50a30d739dbc614e450d4d1913208fa35c6373c4f07a3986657393a99261e`后复制；Rust默认消费者核验执行体SHA `564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79`及112843960 B，固定官方来源仍为2.1.293。默认发行、Python下载、Docker校验和Rust准入同步更新；TLS准入同时保留前版beta.5执行体身份。Cargo使用项目独立BuildKit锁定缓存和 `--locked`，输出复制至普通 `/out` 层；联合清单继续登记实际源摘要和最终镜像身份。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| API准备的有限账号缺显式预算、格式错误、账号总量不足、未知后端 | 准备拒绝，保持原环境 |
| CLI首次或已生效基础布局，目标原生且有限预算缺失/账号总量不足 | 沿基础布局准备CLI；API独立拒绝 |
| 有限额度低于旧单版/双版公式且配置及总量合法 | 普通exec配置准入，保留实际额度和跨版物理进程上限 |
| 已生效native，部署sender预算或目标并发后来改变 | CLI及更新恢复保留冻结布局；API准备继续核验目标 |
| CLI读取到缺失/链接/损坏sender配置或冻结预算矛盾 | 明确要求对账，保留原现场 |
| 无限账号缺 sender 预算 | 生成 memory_mib=0，仍检查并发及原生身份 |
| 全局缺省/空值/unlimited | 使用无限模式，保留宿主余量与待迁移有限预算预检 |
| 未知mem或非法swap | 明确拒绝 |
| 无限策略遇到CLI/API活动、评审、更新门禁或后台预启动 | 保留旧限额，沿下一次空闲准备迁移 |
| 内存迁移的角色移除或配置发布中断 | 保留原有限画像或reconcile现场，沿原维护恢复 |
| 镜像缺能力、分发/执行体不符或映像未封存 | 准备失败，模型零发送 |
| 活动中变更布局 | 忙门禁拒绝 |
| 请求取消、协议故障或旧代次迟到帧 | 退役并等待物理退出后归还进程计数 |
| 原生方式显式回退legacy | 空闲重建128 MiB sender，另一个账号保持其选择 |
| 后台预启动遇到环境容量已满或需要维护 | 跳过预启动，保留在运行的账号 |
| 补位期间切换内核或绑定代次变化 | 撤销旧补位，迟到进程退役 |
| 批量通道失败、未知能力、绑定或内核代次不符、检查过期 | 环境状态 unknown，显示受控原因 |
| 首轮 checking=true 但身份尚未返回 | unknown/snapshot_pending，显示检查进度，PID 与进程数未观测 |
| 平台 / 账号维护 | maintenance/system_maintenance 或 maintenance/maintenance，仅提供固定说明 |
| 旧代次或过期快照携带 checking=true | 保持 unknown 与原原因，检查进度不授予就绪 |
| 目标 legacy、草稿或普通停止环境 | 按原条件返回 null 或 sleeping；读取保持零模型调用 |
| 目标 native293 但实际仍为旧布局 | 显示等待/维护/受控失败；无 PID 或进程数 |
| 有限预算缺失或账号总量不足 | 分别投影native_sender_budget_missing/account_memory_insufficient；旧sender的native_sender_budget_insufficient继续兼容，已保存选择保持 |

### 5. Scenarios and Examples

- 正常：显式有限部署下，1536m账号选择native293且sender预算为空，`ensure(account, prepare_sender=False)` 使用network256m、sender128m和CLI1152m，停止后唤醒保留容器ID并增加代次；API transport返回native_sender_budget_missing。错误：在CLI入口沿目标预算重建sender，或用捕获任意ValueError后回退来放行API。正确：显式区分准备职责，已生效native继续使用其冻结预算。

- 正常：部署默认无限，新环境无需sender预算即可准备；旧1536m环境在空闲准备时应用，N=4生成memory_mib=0/max_workers=8。错误用法：只改示例默认就认定线上显式1536m已解除，或直接改数据库而保留原cgroup。正确处理：上线修改实际部署配置，沿原维护租约排空、重建并核验HostConfig/cgroup及原身份。

- 正常：旧布局选原生后先显示等待，后台准备成功才显示当前热进程。边界：总 RAM 1536 MiB、默认 N=4 且 sender 预算为空时，显示缺显式预算；合法有限额度准入后，CRIU另行判断恢复条件。错误用法：由目标 native293 推导 CRIU/TLS 已就绪，或将任意503原文透传页面。正确处理：独立核验实际状态，仅传资源原因白名单。

- 正常：无限账号 N=2、max_workers=4，三个角色与派生评审的 cgroup `memory.max/memory.swap.max` 均为 max，CPU/PID 保留。
- 正常：有限账号总4g、N=3、原生sender1536m时，network256m、CLI2304m；3普通/6Haiku实际TLS与加权准入保持。
- 边界：同账号同版的六个进程共享一个封存映像，各worker堆及请求缓冲独立，各账号分别持有池；额外进程默认空闲120秒后剩一个暖进程，下次并发按需重建。既有293隔离合成小请求的V3实测六路峰值约646 MiB、空闲约189 MiB，OOM计数为0；280/293混合、大正文和长流峰值按实际负载另验。
- 错误用法：把分发或执行映像大小当作进程RAM，或将合法低额度配置准入视为实际负载容量保证。正确处理：分别登记分发/展开/实际cgroup数据，按实际负载验证容量。
- 错误用法：布局检查查询已被配置事务停止的HTTP sender。正确处理：核验归属后按停止状态处理；运行中仍查询真实活动。
- 正常：配置试点后服务启动先准备一个 worker；首条占用后才补位，回收超期额外进程时仍保留一个。
- 错误用法：用合成 Messages 请求暖机，或让并发等待者各启动一个备用进程。正确处理：只做零模型握手，复用当前代次已有的补位登记。
- 正常：批量巡检快照显示最近检查时间和暖进程 PID；进程退出后下一轮重新准备。错误用法：将任意错误文本、bearer 或旧内核 ready 转发到环境页面。正确处理：只投影当前归属的白名单摘要。
- 边界：首次检查仅返回 preparing/checking=true，页面显示“正在检查”；同代新鲜 ready 到达后自动恢复。错误用法：把 checking=true 当作旧快照仍可就绪的依据。正确处理：身份与新鲜度继续独立校验。

- 正常：平台更新时显示“平台更新中，结束后自动准备”。错误用法：把维护一律解释为本地准备失败，或把任意原因原文转发页面。正确处理：维护原因沿白名单区分，失败观察继续独立投影。

### 6. Tests Required

- `test_cli_prepares_finite_native_selection_without_sender_budget`、`test_cli_keeps_running_layout_when_sender_exceeds_account_total`、`test_cli_preserves_applied_native_budget_flags_and_workers`：首次/停止、API活动、角色资源与ID、代次、冻结native及开关保持；API缺预算和总量不足拒绝独立。`test_cli_rejects_corrupt_or_missing_applied_sender_configuration` 保留配置对账保护。
- `test_native_sender`覆盖双版128m/1535m及单版1407m准入、N=4/1536m、实际额度冻结、非法有限配置和非正并发拒绝；`test_native_layout_rebuild_after_quiesce_keeps_busy_sender_protected`核对128m低额度真实生命周期传入Docker参数，忙时保护保持。
- `test_review_reaches_cli_handoff_with_native_selection_and_no_sender_budget` 核真实评审入口可到达CLI资源交接；`test_environment_actions_require_proof_and_preserve_applied_layout` 经真实HTTP、SQLite及生命周期核对基础和native布局的rebuild/restore、原证明和代次门禁。实际隔离Docker验证同输入首次与停止后准备、角色cgroup额度、模型调用0及API受控拒绝。 系统更新合成测试同时模拟宿主文件归属和权限调用，以普通UID运行CI原命令验证；真实root归属和只读保护继续由专用Docker验收覆盖。

- `test_account_runtime` 覆盖旧布局目标原生的等待与真实预算失败、秘密过滤、显式重试唯一绑定和当前后端校验；`test_native_sender` 断言缺预算、账号总量不足两项原因及 N=4 低于旧公式的合法额度准入。
- `verify_environment_ui.py` 覆盖旧布局等待、明确预算失败、显式重试到实际 ready，沿既有明暗、移动端及迟到响应场景核验。

- `test_native_readiness_preserves_only_known_maintenance_reasons` 及 `verify_environment_ui.py`：平台与账号维护分别展示，任意原因被固定投影，进程证据保持未观测且零业务写入。

- `test_native_unlimited_layout_and_capture_are_frozen_per_account`、`test_serial_unlimited_handoff_restores_exact_cli_limits` 及部署预检：零哨兵、4 物理进程、实际 Docker/cgroup max、指标 0、全局默认无限与显式有限覆盖、混合历史预算及旧布局恢复；重画像保留资源与采集开关。
- `test_default_memory_is_unlimited_for_missing_and_empty_configuration`、`test_unlimited_policy_migrates_idle_native_and_preserves_applied_identity`、`test_memory_migration_defers_cli_api_and_background_activity`、`test_memory_migration_failure_retains_budget_and_requires_reconciliation`：默认无限、旧native迁移、HOME与CPU策略保持、CLI/API/更新门禁延后及失败恢复。部署 `test_unlimited_deployment_counts_unmigrated_finite_budgets` 覆盖混合预算和只读预检；真实Docker核验三角色Memory=0/MemorySwap=-1、cgroup max、sender1.5核、N=4原生ready及模型调用0。
- `test_native_sender.py`：默认legacy、显式预算、总RAM/CLI下限、未知后端、容量无任意64进程上限；`test_native_layout_rebuild_after_quiesce_keeps_busy_sender_protected`：忙时拒绝、停止后正确重建和代次/预算。
- Rust实际 `native_real_binary`：共享dev/inode及四项封存、6→1空闲回收、取消→0、全部原进程退出后缓存重建、独立凭据及一次提交。
- 预启动回归：`test_account_runtime.py` 验证仅启用绑定、满容量时不腾挪、sender 开关先写后通知；`native_real_binary` 验证首个预热 PID、第二个唯一补位、回收到一个以及零模型计数。
- `test_account_runtime.py` 核验批量读取、绑定/内核代次、新鲜度、非法数字、legacy/休眠及秘密过滤；合成环境页断言读取零写入且准备失败/过期明确显示。
- `test_native_readiness_distinguishes_pending_checks_without_trusting_old_workers` 覆盖首次缺身份、严格布尔进度、真实失败、旧环境/内核及过期快照不投影 PID；`verify_environment_ui.py` 使用实际20秒轮询确认检查中到就绪，失败/冲突原因和零业务写入保持。
- `default_idle_reaper_keeps_spare_until_two_minutes`使用真实子进程及空闲年龄：60秒保留两个，121秒回收到一个；缩短30秒唤醒旧等待，延长300秒继续保留，忙进程、映像缓存及原池身份保持。
- `deploy/flower2api/verify_forwarding.py --native`：真实两账号三角色、HTTP/SOCKS、3普通/6Haiku、同映像/秘密隔离、cgroup峰值与OOM0、默认120秒回收及按账号回退；N4等待上限135秒，验证镜像的额外CA仅限本地夹具。
- 发布验收从实际Release下载附件，核SHA/大小、冻结构建输入并运行真实消费者；合成回环与真实付费推理分开记录。

## Scenario: 请求内核随平台版本交付与历史迁移

### 1. Scope / Trigger

- 平台镜像固定配套280／293内核，账号创建、升级、唤醒、恢复和平台回退按目标账号镜像建立安装表。独立发行、下载及切换入口退役。
- 实现依据：native_sender、native_kernel_upgrade、account_runtime、account_isolation、system_updates及Rust固定制品加载器。

### 2. Signatures

- GET `/api/environments/{environment_id}/native-kernel/releases`及POST `/api/environments/{environment_id}/native-kernel`保持原管理鉴权，统一返回410与“请求内核由平台版本统一管理，请通过系统更新升级或回退平台”。历史query／body退出解析和执行。
- `native_kernel`保留293别名；`native_kernels`按源版本提供`management=platform,source_version,state,revision,current,builtin,platform_release,error`。实际PID／进程数从`native_preparation.versions`独立投影。
- `builtin_config(configuration,versions)`生成目标内置安装表；`validate_records(root,account_id,reconciled=False)`先核对全部旧记录；`migrate_records`原子归一；`archive_binding_records(root,account_id)`在原绑定交接门禁内归档终态。
- `AccountRuntime.ensure(...,prepare_sender=False,native_migration=False)`管理调用沿目标镜像补齐已有原生布局；受控迁移参数只供持久上下文核验后的环境对账使用。
- 网关`native-kernel-probe`和sender`/internal/native/prepare-switch`退出活动路由；普通准备、readiness、status和空闲回收保持。

### 3. Contracts

- 镜像`vibebench.native-runtime-versions`缺省或精确`2.1.293`表示历史单版；精确`2.1.280,2.1.293`表示双版，其余拒绝。根配置代表293，双版另登记280的固定路径。
- 根及每版`release/kernel_generation`兼容解码后清除；Rust仅加载当前源版本的固定内置分发和执行映像，继续核验摘要、大小、精确FD、封存及实际握手。缓存能力继续按`cache_ttl_rewrite_protocol/message_cache_policy_protocol`核验。
- 目标镜像声明`vibebench.native-platform-managed=1`时，重建就绪前核对安装表归一、sender身份和代次，以及`/internal/native/status.versions`中每个目标版本的`available=true`和精确version。此核验沿按需预热及原容量策略执行。
- sender退出`/runtime-releases`挂载及独立发行公钥依赖；旧部署字段兼容保留。平台签名信任根继续生效。
- 两份旧记录分别为`runtime/native-kernel-upgrade.json`和`native-kernel-upgrade-280.json`。拒绝符号链接、非对象及超过65536字节的记录；全部归属和阶段通过后才写入。
- 终态idle/active/restored/failed归一为`management=platform,state=restored`，current、kernel_generation、previous、prepared、preparing_release归空，previous_available=false；保留有界migrated_from审计。旧平台读取为内置选择，重复执行一致。
- draining/switching/restoring/finishing/reconcile及未知状态继续阻挡普通维护。中断对账核对唯一账号、环境／代次、真实活动、旧操作和租约；外来owner／代次继续拒绝。
- `runtime/native-kernel-platform-migration.json`先于重建副作用持久化原记录、账号、环境、代次、停止意图及阶段。恢复核对当前／下一代次；发送器就绪并确认释放本owner租约后删除日志，失败保留reconcile及门禁。停止环境保持停止。
- 绑定切换先检查旧归属与未完成迁移，再在原双端绑定门禁内停止发送器，将终态记录持久归档为`native-kernel-upgrade[-280].account-<旧网关账号ID>.json`后移除活动记录，随后交接DB与凭据。归档写失败保留原记录；提交前中断可重试；新绑定采用内置选择。首次绑定只接纳空历史。
- preparing_release表示已退役下载。它退出维护门禁；启动恢复写空并保留cancelled_preparing_release审计。真实未完成操作、迁移日志及维护租约继续保护。
- API列表及页面保持只读，版本发现、候选、激活、独立回滚／恢复及快速操作轮询退出；TLS、CRIU、资源维护和平台更新操作沿既有合同。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 匿名调用旧管理入口／已鉴权旧调用 | 原鉴权拒绝／410；下载、切换及租约副作用为0 |
| 旧终态选择与当前唯一绑定一致 | 受控边界归一为目标内置选择 |
| 外来账号、未完成迁移或未知阶段 | 副作用前拒绝，明确待环境对账 |
| 外来租约、活动API／CLI或发送连接 | 保留原现场与其他owner门禁 |
| 安装表缺版、固定制品或回执代次不符 | 重建就绪失败，升级沿原恢复流程处理 |
| 退役下载标记／真实未完成操作 | 设置维护可继续／继续阻挡 |
| 原停止环境 | 归一文件并保持停止，下次唤醒按目标镜像补齐 |

### 5. Scenarios and Examples

- 正常：旧sender仅登记293且保存beta选择；平台升级维护阶段登记双版并核验，首笔293／280请求复用同代次、同三角色容器。
- 边界：停止环境迁移保持停止；历史单版目标只登记293；合法换绑归档旧记录，新账号通过同一归属校验。
- 错误用法：延后至首笔API补齐双版布局，遇养号作业后要求重建。正确处理：升级维护阶段先完成目标安装表及就绪核验。
- 错误用法：将HTTP active=0或过期租约当作可接管证明。正确处理：联合核对jobs、执行登记、sender及原owner／generation。

### 6. Tests Required

- test_native_kernel_upgrade：双记录归一及幂等、旧平台重写后的再次归一、旧程序可读、归档与写入中断、候选取消、外来归属／租约、真实维护、持久迁移重启及停止状态。
- test_account_runtime：换绑后真实ensure→transport、解绑／再绑定及交接中断；升级前完整登记，养号占用下首笔两版请求保持代次及容器；停止唤醒和单版目标。
- test_native_kernel_api：旧请求及过时payload已鉴权410、匿名拒绝、零下载／切换／租约副作用。采集／CRIU回归分别核对旧候选与真实维护门禁。
- verify_native_runtime_versions及verify_native_environments：两套页面只读、零退役请求、实际观察未知态、明暗390／1280px及原资源维护。
- verify_system_update.py：Bookworm兼容且启用v3-verification的隔离二进制、同批固定两版制品，核对长流排空、CLI阻断、旧单版登记升级后的真实双版API、停止保留、回退、失败及进程恢复；真实模型调用为0。


## Scenario: 三角色在线CPU与重建恢复

### 1. Scope / Trigger
- 修改环境资源接口、三角色创建、评审交接或系统更新CPU恢复时适用。仅隔离布局2，内存、PID和账号并发沿原合同。

### 2. Signatures
- GET/POST `/api/environments/{environment_id}/cpu-resources`，沿既有管理鉴权。
- POST字段：`expected_generation:StrictInt,expected_revision:StrictStr,cpus:{cli,sender,network}`；额度为严格数字，拒绝额外字段及bool。
- `cpu_resources.read_resources(runtime,row)`、`set_resources(runtime,row,expected_generation,expected_revision,cpus)`；`read_policy(runtime,row)`读取重建策略。
- `cpu_resources.default_cpu_limits(values:dict|None=None) -> dict[str,int]`：省略values读取环境，返回三个角色的NanoCpus；部署预检与角色创建共用。
- 返回generation、revision、host_cpus、cpus、persisted_cpus；revision冻结环境代次、持久策略及实际容器身份/额度/生命周期。

### 3. Contracts
- 三角色分别支持0.01到Docker宿主NCPU核，总和不设3核上限。CPU是共享调度额度，按NanoCpus精度校验有限数字，保留正数预算模式。
- POST先登记部署维护活动，在环境锁内重读当前环境及未删除账号；拒绝维护中、内核切换/对账中、评审串行交接中或旧代次/revision。只通过Docker更新NanoCpus，逐项核对实际归属、镜像、Memory/MemorySwap/PidsLimit、启动时间、重启数及运行状态/PID保持。
- 私有0600 `runtime/cpu-resources.json`为schema_version=1、environment_id、account_id、revision UUID、三角色nano_cpus；严格拒绝损坏、链接和错误归属。实际额度全部确认后原子发布。Docker异常可能已经生效，尝试集合先登记再调用；失败按原不可变容器恢复额度和原策略，记录restored或reconcile。
- 新角色CPU默认CLI1.5/sender1.5/network0.5核，通过 `V3_ACCOUNT_CLI_CPUS`、`V3_ACCOUNT_SENDER_CPUS`、`V3_ACCOUNT_NETWORK_CPUS` 独立覆盖。缺省或空字符串使用默认；有限数字至少0.01核且精确表示为整数纳核，bool、非法数值及超长小数拒绝。转换使用Decimal精确整数比，禁止依赖乘法上下文先舍入后验精度。固定宿主更新包SOURCE_FILES包含cpu_resources.py。
- 角色创建先使用独立默认及旧评审布局，最后应用合法保存策略。旧schema1布局只覆盖CPU核验视图，原内存/PID及文件保持；串行评审借用当前CLI额度，保存策略与三个实际角色逐项相等后使用新额度。无保存策略时总上界取三角色默认总量与旧V3_ACCOUNT_CPUS较大者；旧总量2核不将新角色按6:1:1重新分配。
- 宿主HostDeployment.environment_cpu在排空后、重建意图前冻结实际额度到operation.environment_cpu_before。新角色重建及软件失败回滚后按不可变ID/标签恢复，仅CPU变化；兼容旧平台忽略新策略文件。旧无限CPU且缺策略保持原升级路径，显式策略与实际预算不符时拒绝。
- 页面独立CPU表单按需读取，列表轮询保持输入；提交冻结revision，关闭/离页作废迟到回执。失败要求重读实际额度，成功提示即时应用并保存重建配置。

### 4. Validation & Error Matrix
| 条件 | 结果 |
| --- | --- |
| 三项各2核，宿主4核 | 接受合计6核 |
| bool/非有限值/低于0.01/单项超宿主 | 更新前拒绝 |
| 旧revision、错误归属、交接或维护占用 | 409，保留当前操作归属 |
| Docker返回失败但实际生效 | 按已尝试角色恢复并核对 |
| 策略损坏、链接或跨环境 | 明确拒绝，保持故障可见 |
| 旧平台重建恢复默认CPU | 宿主恢复维护前实际额度并验收 |
| 默认配置超长小数或非有限值 | 部署预检及创建前拒绝，保持精确纳核校验 |

### 5. Scenarios and Examples
- 正常：CLI=2、sender=1、network=0.5，保存后即时生效，下一次重建按同策略创建；系统回滚也保留实际额度。
- 基础：新环境无策略使用1.5/1/0.5，历史实际角色由GET观测；已有显式策略优先。
- 精度边界：1.000000001与相同值的尾随零合法，1.0000000000000000000000000001拒绝；禁止先舍入为1再接受。
- 错误用法：限制三项合计3核、只调用不支持nano_cpus的Docker SDK Container.update，或重建后丢掉在线调额。正确处理：逐项校验，沿SDK JSON入口发送NanoCpus，并由策略/宿主维护记录分别承接重建与旧版回滚。

### 6. Tests Required
- test_cpu_resources：合计6核、CAS、真实Docker SDK回环JSON、未知更新恢复、策略归属/链接及评审交接拒绝。
- default_cpu_limits覆盖独立覆盖、旧总量忽略、非法类型、科学计数法与尾随零；低精度Decimal上下文下合法纳核保持、超长小数拒绝。test_manage覆盖部署预检拒绝同一超长输入，test_system_workflow覆盖固定宿主包独立导入。
- test_account_runtime实际三角色创建沿保存额度；test_project_review_runtime旧布局按新CPU交接、原文件及RAM/PID保持、角色漂移拒绝。
- test_system_update_cpu核维护前持久冻结、重建实际新角色恢复、归属冲突更新前拒绝；原更新器回归保持。
- verify_native_diagnostics_cpu：轮询保留表单、冻结提交、冲突、晚回执、390像素及零真实模型调用。


## Scenario: 账号请求内容采集开关

### 1. Scope / Trigger

修改 `content_capture_settings.py`、`/api/environments/{environment_id}/content-capture`、管理桥准入及环境卡片开关时适用。

### 2. Signatures

- GET 返回 `environment_id`、bench `account_id`、`generation:int`、`revision:string`、`enabled:bool`、`applied:bool`、`supported:bool`及`tls_observer`能力摘要。
- POST 精确接收 `enabled:StrictBool`、`expected_generation:StrictInt`、`expected_revision:StrictStr`，拒绝附加字段。
- `read_settings(runtime,row,observation=None)` 只读复用批量巡检；`set_settings(runtime,row,account,enabled,expected_generation,expected_revision)` 在更新准入和账号锁内应用。Rust `NativeReadinessStatus`可选追加`tls_observer`，内部鉴权`/internal/native/status`也提供该摘要。

### 3. Contracts

- GET/POST 都通过实际 SQL 核对未删除账号与唯一网关绑定。row 的 `gateway_account_id` 为 SQL 投影；并发摘要包含该绑定、环境代次、状态、完整画像和 sender 文件摘要。
- sender 配置沿原 root:1001、0640 合同读取，安全文件读取拒绝链接和越界。`applied` 核对实际 native 配置、采集目录、账号、环境及发送器代次；公开响应排除凭据。
- `native_capture_policy.capture_enabled(fingerprint)`统一解释缺字段为开启，精确false为关闭，非法类型拒绝。新环境、重建和系统更新共用此解释；显式关闭持久保留，legacy发送器不创建原生采集目录。全局info/debug选择保持独立。
- 镜像能力标签`vibebench.native-tls-observer=1`对应sender配置`native_tls_observer_protocol=1`。启用采集的原生sender使用镜像内受限broker、固定只读制品和内联seccomp；NoNewPrivs保持true，业务UID1001及P/E/I/A能力为零。加载权限、ABI和回收合同由cc-runtime-bridge的原生TLS采集规范所有。libbpf实际动态库在镜像构建时核对。
- 摘要`state`为`not_installed|disabled|stopped|preparing|ready|unavailable`，附`reason`、`checked_at_ms`、`protocol_version`及`image_admitted`。ready只接受45秒内同账号/环境/代次/内核的巡检，协议为整数1且映像已准入；动态状态不进入配置revision。安装标签、原生worker_ready和单请求采集完整性分别表示。
- `pending_upgrade(root, include_preparing=True)` 同时排除候选下载；该关键字参数默认False，原调用沿用既有判定。
- POST 按 update admission → OAuth owner → profile → environment 锁顺序重读。原生未就绪、配置偏离、旧版本、活动工作、评审交接、内核维护及 API 活动均拒绝切换。
- 开启前独立核对安装协议，关闭态不能遮蔽旧镜像缺能力；失败在领取租约和重建前要求系统更新。操作只核对实际配置并复用既有异步零模型预备，维护锁内不等待网关反向解析绑定。
- 使用唯一 `capture:<uuid>` 领取、claim 和释放网关排他维护租约。API 在维护租约持有期间保持关闭；到期保持关闭，原 owner 可释放。维护重建使用独立租约，CLI 作业登记会阻止画像准备。
- 环境锁阻止其它本地工作进入，更新 admission 覆盖整个操作。重建复用原 ensure，保留 HOME、画像、资源策略及已保存内核。原停止环境在核对后恢复停止状态，过程模型调用为零。
- 指纹 `native_capture_enabled` 与实际 `native_capture_dir` 一致后返回成功。失败恢复原指纹并重新准备；恢复失败或租约释放不确定时置 reconcile，使用原环境维护对账。私有 `runtime/content-capture-operation.json` 保存操作与恢复状态。
- prepare 回执丢失时按唯一 owner 重读并释放本次租约。占用/旧版本返回 409；文件、Docker 或连接故障返回受控 503；明确恢复/对账错误保持可见。
- 开关只影响后续请求，与 request_diagnostics_log_mode 独立。沿用脱敏、7天和2MiB预览；每账号共同容量1GiB，取消份数上限，拒绝入站优先保留。具体容量轮转及最终TLS证据合同由网关settings-database.md所有。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 重复或删除绑定 | 404，零写入 |
| 布尔冒充代次、数字冒充开关、附加字段 | DTO 422 |
| 旧代次/摘要、活动 CLI/API、配置偏离 | 409，保留原策略 |
| 旧镜像关闭态请求开启 | 409，要求系统更新；零租约、零重建 |
| 巡检过期、错代次、缺能力或未知映像 | 显示受控缺口，不能以安装配置标记ready |
| 切换准备失败、恢复成功 | 409，说明原策略已恢复 |
| 恢复或门禁释放失败 | reconcile，明确要求对账 |

### 5. Scenarios and Examples

- 正常：开启→核对实际 sender 目录→关闭，账号独立，身份和内核选择保持。
- 边界：停止环境切换后保持停止；prepare 响应丢失后仅释放本次 owner。
- 正常：首次部署或系统更新后，原生环境自动开启并后台准备；显式关闭经重建继续关闭。错误用法：只检查页面disabled状态决定是否安装探针。正确处理：启用准入独立检查协议，实际ready依赖当前巡检。
- 错误用法：把采集维护登记为 CLI 作业后调用 ensure，导致画像准备被自身作业阻止。正确处理：在原环境锁和更新准入内独立持有排他维护租约。

### 6. Tests Required

- `test_content_capture_settings` 覆盖 DTO/SQL、实际配置偏离、账号独立、忙碌/旧版本、内核下载中零租约/零重建、回执丢失、恢复及门禁失败。
- `test_account_runtime.AccountRuntimeTests.test_content_capture_uses_real_lifecycle_and_preserves_identity` 走实际维护租约及配置重建路径；验证 sender 文件、代次、原身份和内核，作业集合与租约正常收口。
- `test_saved_role_cpu_policy_is_used_when_recreating_containers` 验证三角色重建沿原 CPU 策略；浏览器回归核对冻结版本、独立开关及重复提交。
- `test_native_tls_isolation.py`与真实`verify_roles`区分加载器、Rust sender及其worker，验证精确入口/能力/seccomp、业务零权限、秘密隔离、本地构建和资源压力；root加载器不能套用旧的容器默认UID断言。
- 内容采集测试覆盖缺省true、显式false、非法类型、同代次新鲜ready、旧镜像关闭态零维护写入。浏览器覆盖默认开启、取消、关闭再开启和五类TLS能力状态；真实模型调用为0。

## Scenario: CRIU默认选择、维护应用与实际状态

### 1. Scope / Trigger

- 修改恢复默认值、账号选择、sender入口、预算或前端状态时适用；恢复协议和业务权限沿[runtime合同](../../runtime/backend/runtime-contract.md#scenario-原生进程池-criu-热模板恢复协议-1)。

### 2. Signatures

- GET/POST `/api/environments/{environment_id}/criu`；POST为 `{enabled:StrictBool,expected_generation:StrictInt,expected_revision:StrictStr}`，拒绝额外字段。
- `native_criu_policy.account_enabled(fingerprint) -> bool`；`restore_policy(native,fingerprint,installed) -> dict`供角色创建、ensure与读取共用。
- `native_criu_settings.read_settings(runtime,row,observation=None)`与`set_settings(runtime,row,account,enabled,expected_generation,expected_revision)`；`native_settings_operation.apply_settings(...)`复用采集开关维护生命周期。

### 3. Contracts

- 全局 `V3_NATIVE_CRIU` 缺省/空值为1、精确0关闭；账号指纹可选 `native_criu_enabled:bool` 缺省true，非法类型拒绝。native配置、镜像能力、全局/账号选择及独立内存条件共同决定恢复入口；普通exec使用实际资源配置，恢复另需256+300×max_workers MiB，memory_mib=0为配置无限。
- sender.json保存有效 `native_criu_enabled`、固定原因 `native_criu_reason`、可选 `native_criu_protocol:1`。创建选择实际入口；ensure比较有效配置沿原空闲重建门禁。列表查询保持只读。
- 完整摘要包含schema_version=1、environment_id/generation/revision、enabled/platform_enabled/eligible、supported/installed/applied、memory_mib/required_memory_mib、state/reason、checked_at_ms、template_ready和last_start_source。state为disabled/not_installed/requires_rebuild/preparing/ready/unavailable/unknown。revision冻结指纹、策略、sender文件摘要及实际容器/入口身份。
- 镜像标签仅表明installed；applied同时核对唯一绑定、配置选择和实际Entrypoint。旧入口显示requires_rebuild。当前观测需匹配环境、generation、kernel_generation及45秒内整数时间戳；只接受schema1、受控state/reason与精确bool，ready和template_ready必须一致。旧字段缺失显示telemetry_missing，陈旧/跨代显示telemetry_stale；last_start_source仅接受exec/criu_restore。
- reason区分legacy_backend、platform_disabled、account_disabled、image_unsupported、memory_budget、container_rebuild_required、binding_unverified、environment_stopped、telemetry_missing/stale、controller_preflight_failed/unavailable、kernel_unsupported、template_failed/preparing及identity_changed；临时列表读取失败可仅返回schema1/unknown/read_failed。
- POST沿更新准入→owner/profile→environment锁顺序重读唯一账号及CAS。拒绝待处理内核维护、未就绪绑定、CLI/评审作业、API活动或占用租约；开启需核对平台与安装能力。同值且applied直接返回，历史未应用同值沿重建路径执行。
- 唯一criu:UUID owner申请prepare/claim，停止并移除原角色、持久选择、保留代理/HOME/身份及内核选择后ensure重建；原停止环境保持停止。核对后写私有runtime/criu-operation.json。失败恢复原指纹和角色；恢复或释放结果未知进入reconcile。finally只释放本owner租约，prepare回包丢失也重读归属。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 普通预算够、恢复预算不足 | 普通启动，unavailable/memory_budget |
| 全局0或账号false | 显示关闭原因，保留账号选择与普通启动 |
| 镜像具备工具、实际为旧入口 | requires_rebuild，空闲应用后核对 |
| 旧遥测、过期或跨代 | unknown及固定原因，禁止沿用旧ready |
| 未鉴权 / DTO错误 / CAS过期或忙碌 | 401 / 422 / 409 |
| 切换或释放失败 | 恢复原策略或reconcile，错误内容受控 |

### 5. Scenarios and Examples

- 正常：新无限原生账号缺省选择控制器；当前模板登记存活后显示ready，最近扩容来源可为criu_restore。
- 边界：1536MiB、max_workers=6继续普通启动并展示恢复需2056MiB；全局关闭时可保留账号true作为期望值。
- 错误用法：仅凭镜像标签或缺少恢复字段的旧巡检推定ready。正确处理：分别核对目标、实际入口和同代真实模板。
- 上线后：静态准入为受控重建前置条件；发布负责人仍需验收权限、实际恢复、唯一发送及宿主并发资源峰值。

### 6. Tests Required

- test_native_criu_settings：缺省/显式关闭、有限降级、无限额度、实际文件CAS、维护租约、失败恢复、同值旧入口、严格同代遥测；实际ASGI覆盖鉴权、严格DTO、旧CAS及只读发现。
- test_account_runtime：实际Docker调用选择控制器与新CPU，持久策略/采集/内核身份及旧维护回归。
- gateway：可选restore兼容、登记断开、独立预算与饱和计算；verify_environment_ui核对开关及实际状态，所有本地夹具零真实模型调用。

## Scenario: 官方 CLI 遥测部署策略

### 1. Scope / Trigger

修改官方 Claude Code CLI 的任务、项目/Pi、养号、登录或交互执行环境及部署配置时适用。原生发送栈的 `CCRB_TELEMETRY` 沿运行时合同独立管理。

### 2. Signatures

- `cli_telemetry_policy.cli_telemetry_mode(value: str | None = None) -> str`：显式值或环境值校验，返回 off/on。
- `cli_telemetry_policy.cli_telemetry_environment(environment: dict[str, str]) -> dict[str, str]`：返回应用策略后的副本。
- 部署变量 `V3_CLI_TELEMETRY=off|on` 由 compose 传至 orchestrator，服务导入与部署 preflight 共用校验。

### 3. Contracts

- 缺省、空值及去空白后空值使用 off；其它仅接受精确小写 off/on，非法值抛 ValueError。
- off 在受控 settings.env 和最终执行环境写入 `DISABLE_TELEMETRY=1`、`DISABLE_ERROR_REPORTING=1`。on 从两者删除这两个关闭键，恢复官方默认许可；不将0解释为开启，不承诺实际上传。
- `_cli_setup` 覆盖现有 HOME 设置，`execution_environment` 投影到任务、评审、登录及交互执行；Runner worker_env和子命令 `_claude_exec_env` 在最终合并边界应用同一策略。下次CLI启动应用部署选择。
- 自动更新的 `DISABLE_AUTOUPDATER=1` 独立保留，其他模型/env/hooks保持原归属；官方CLI分发体、原生sender及其身份、TLS和模型发送链路各沿自身合同。
- orchestrator镜像的 `COPY *.py` 包含纯策略模块；宿主 `manage.py` 的直接依赖同步登记 `install_system_updater.SOURCE_FILES`，固定源码包须支持仓库外独立导入。

### 4. Validation & Error Matrix

| 配置 | 结果 |
| --- | --- |
| 缺省、空值、off | 两个官方关闭键均为1 |
| on且旧settings/env含关闭键 | 删除两个键，其他设置保留 |
| 0、false、OFF或未知值 | 部署预检及服务策略入口拒绝 |
| 设置on | 恢复官方默认许可，上传仍由官方CLI决定 |

### 5. Scenarios and Examples

- 正常：部署未配置该键，普通任务、项目和养号的官方CLI设置及执行环境均关闭遥测和错误上报。
- 边界：切换on后重新启动CLI，旧的两个关闭键被清理，自动更新继续关闭。
- 错误用法：写入 `DISABLE_TELEMETRY=0` 表示开启，或把CLI策略当作原生sender的遥测开关。正确处理：on删除受控关闭键，两条执行链分别管理。

### 6. Tests Required

- `test_cli_telemetry_policy`：默认/空/off、已有关闭键覆盖、on最终环境清理、非法值拒绝。
- `test_account_runtime`：实际CLI准备入口保留model/hooks/其他env，任务driver及交互exec环境应用策略，on清理旧settings。
- `test_manage`：预检共用值域；`test_system_workflow`：固定宿主包在仓库外独立导入实际依赖。

## 代理引用与有界日志读取补充

`GET /internal/v3/proxy-references`沿用内部服务鉴权，返回任务账号及登录草稿的规范连接摘要、公开身份与complete。绑定任务由网关权威配置去重；未初始化运行时、损坏草稿、未知连接、未决选线或读取跨越选线活动代次使complete=false。摘要不转发浏览器；目录公开及删除保护见[代理目录合同](../../gateway/backend/proxy-directory.md)。

`GET /api/runs/{rid}/transcript?tail_bytes=131072`沿用可见运行与原artifact路径校验，可选范围1024～1048576。仅seek读取尾部，丢弃首个不完整行，以`X-Log-Truncated`标记截断；省略参数继续完整FileResponse，支持原独立页面。`test_run_log_tail.py`使用合成文件验证边界与兼容入口。

### 运行产物与公开抓包预览

- `GET /api/runs/{rid}/file?path=...` 先执行 `_require_visible_run`。普通运行通过 `AccountRuntime.run_workspace_path` 按 runs.environment_id 和既有摘要别名解析物理项目目录，避开 workspaces 兼容链接。每级目录使用 `O_NOFOLLOW`；拒绝私有目录、链接、设备和FIFO，文本最多64KiB，并区分空文件、二进制和截断。
- 工程运行复用现有冻结 `artifact_file` 读取器；场景运行选择与文件列表一致的最新冻结评测。历史预览不能回落到当前活动工作目录。
- `GET /api/runs/{rid}/capture?path=...` 继续经过可见性、run_kind和抓包目录归属检查，复用 `capture_file_preview` 的公开元数据白名单。路径最长512字符，拒绝原始请求/响应正文；错误返回受控400/404。
- 浏览器文件读取拥有独立取消信号及代次。切文件、关闭详情和换运行后，旧读取不能覆盖当前内容，也不能重新打开窗口。

## Scenario: 交互式任务代理保存

### 1. Scope / Trigger

适用于`task_proxy.py`、任务proxy-selection接口与引用完整性；后台`proxy_sync.py`继续保持原幂等同步语义。

### 2. Signatures

- 内部`GET/PUT /api/accounts/{aid}/proxy-selection`由Rust公开桥调用。PUT模型`TaskProxySelectionIn`只允许StrictStr的selection_revision、connection和operation_id。
- `save_selection(..., ownership_guard=None, authorize=None)`：既有身份/环境上下文中比较并保存；生产入口传入凭据guard与票据领取回调。
- `TaskProxyActivity.track(operation_id)`为完整请求上下文；`references(read)`核对读取前后活动与代次。

### 3. Contracts

- 版本以服务密钥HMAC绑定`['task-proxy-v1',task_id,binding_id,connection]`。绑定账号从网关config读取实际连接；独立账号恢复原五个分列字段，支持HTTP80、SOCKS1080、IPv6及转义认证。直连为空连接。
- PUT在UPDATE_GATE内先登记活动，再取owner→profile非阻塞锁，重新读取可见账号、核对凭据归属和版本。忙碌登录或停用账号拒绝；同配置只回读。副作用前领取网关一次性票据，绑定回调携带相同operation_id。
- 独立任务再取得environment锁，确认无jobs及sender活动，停止并移除旧实例，保留持久资料。DB锁仅包围SQL；WHERE比较任务ID、绑定及五个旧代理字段，只更新代理字段。
- 绑定任务持owner/profile调用网关许可，禁止先持environment锁再反向等待quiesce；网关代理始终是权威。内部私有响应必须经Rust白名单投影。
- 活动集合与原编排锁共同归单进程。异常退出清理活动，重复operation拒绝且保留原登记。读取引用前后的活动及generation必须一起核对，避免提交刚完成后把旧引用当作完整快照。跨服务超时所有权见[任务选线合同](../../gateway/backend/proxy-directory.md#scenario-任务账号选择与超时事务保护)。

### 4. Validation & Error Matrix

身份缺失404；ProxySelectionConflict按changed/busy/disabled返回409；其它维护错误为固定409说明，读取不可用503。取消在前端保持零PUT。提交前失败保留原数据库代理；提交后回读失败或回执不确定时重新读取权威配置，不宣称已经撤销。

### 5. Scenarios and Examples

正常：独立任务选目录后五个代理字段更新，凭据与限额保持。边界：直连清空主机/认证并将端口置null。错误：把后台同步的“源已变化则完成”用于交互保存；正确处理为明确版本冲突。错误：只在引用读取结束检查active；正确处理还要拒绝跨活动代次的旧快照。

### 6. Tests Required

`test_task_proxy.py`覆盖SQLite版本/绑定/删除、直连、停止失败、锁释放、实际main入口、票据领取前登记及跨代次引用。`verify_task_proxy_api.py`覆盖真实HTTP公开投影、私有字段隔离及45秒超时。全量`PYTHONPATH=services/orchestrator:deploy/flower2api .venv/bin/python -m unittest discover -s services/orchestrator`；真实Docker恢复由发布阶段验证。


## Scenario: 环境列表有界并发只读汇总

### 1. Scope / Trigger

修改`main.v3_environments`及环境状态汇总性能时适用。

### 2. Signatures

- `GET /api/environments`、浏览器桥`GET /runtime/api/environments`继续返回按名称排序的公开环境列表。
- `v3_environments() -> list[dict]`；`_v3_environment_summary(row, ownerships, native_preparations, native_preparation_error) -> dict`负责单环境投影。

### 3. Contracts

- 协调器先读取有资格的环境行，并各一次读取凭据归属摘要及原生准备快照；每轮最多三个ThreadPoolExecutor工作者，按输入顺序收集结果。空列表直接返回空数组。
- 每个工作者使用独立`copy_context()`保留请求上下文，数据库连接在工作者内创建并finally关闭；共享的本轮摘要只读使用。
- 保留owner→profile→environment的非阻塞核对、只读Docker状态、代次归属和原异常合同。列表不能唤醒容器、刷新凭据或等待维护锁；无跨请求状态缓存。

### 4. Validation & Error Matrix

| 条件 | 期望 |
| --- | --- |
| 四环境完成顺序不同 | 最大并发3，返回顺序沿SQL名称排序 |
| 空列表 | 空数组，单环境汇总调用零次 |
| 维护锁占用/快照缺失 | 沿原维护提示与未知状态合同 |
| 单环境原异常 | 沿原异常传播，不伪造成功投影 |

### 5. Scenarios and Examples

正常：四环境分成最多三路读取，先完成的环境也按输入位置返回。边界：请求上下文中的身份在每个工作者内保持。错误用法：把SQLite连接或同一个Context对象并发交给全部工作者；正确处理是工作者独立连接，每次提交复制上下文。

### 6. Tests Required

`test_environment_summary`断言并发上限、排序、ContextVar、空列表与异常；`test_account_runtime`继续覆盖只读身份、维护锁、删除/草稿过滤与公开字段。`verify_native_environments.py`及`verify_environment_cpu_summary.py`保持列表、CPU换代和编辑草稿回归。

## Scenario: CLI scratchpad 私有磁盘与启动恢复

### 1. Scope / Trigger

- 修改账号CLI的`/tmp/claude-1000`挂载、停止转存、重建、评审交接、备份或节点迁移时适用。实现归`cli_scratchpad.py`，调用入口沿用账号运行环境的原锁、空闲门禁和维护租约。

### 2. Signatures

- `preserve_cli_scratchpad(runtime, row: dict, container) -> None`：在停止原CLI前保全可读取的内存盘。
- `prepare_scratchpad_mount(runtime, row: dict) -> Mount | None`：准备账号独立磁盘卷，返回原容器路径的挂载。
- `restore_cli_scratchpad(runtime, row: dict, container, *, fresh: bool = False) -> None`：恢复原临时路径，或核验磁盘挂载。`fresh=True`只由已创建新空CLI的角色入口传入。
- `scratchpad_runtime_registered(root: Path, environment_id: str) -> bool`：核验允许在目标节点重建的工作目录协议。
- `remove_scratchpad_volume(runtime, row: dict) -> None`：全部角色移除后核验并清理卷元数据，持久文件继续独立保存。

### 3. Contracts

- 镜像标签`vibebench.cli-scratchpad-protocol=1`启用候选布局；已有`cli-scratchpad`资料继续进入保护逻辑。目录按不可变environment_id持有，HOME、原session路径、执行source和账号身份沿原映射。
- 持久根为`cli-scratchpad/data`，UID1000。Docker local overlay使用私有空lower、磁盘upper及work，目标固定`/tmp/claude-1000`，参数含`noexec,nosuid,nodev`。CLI继续UID1000、能力清零、只读根和no-new-privileges。普通`/tmp`沿原tmpfs。
- 管理记录属于root私有目录，协议身份为`{protocol:1,environment_id}`。`legacy.json`另绑定`container_id/generation/node_key/started_at/archive/sha256`；`restore.json`和`restored.json`绑定目标`container_id/started_at/archive_sha256`。转存流最多512MiB、清单最多100000条，拒绝路径逃逸、设备及链接父目录，核对文件内容与元数据并持久化后发布。
- Docker归档接口对隔离tmpfs的视图不作为转存依据。可信标准库程序通过原CLI的exec流导出，并在CLI实际挂载命名空间中恢复。导出结束复核源StartedAt，启动身份变化阻挡发布并保留上次快照。
- 同容器、同StartedAt且没有待恢复记录时，当前文件是权威状态，恢复入口直接沿用。启动身份改变或旧回执缺少started_at时，须先取得匹配本次启动与快照摘要的恢复完成证明，再允许新转存，避免空tmpfs覆盖唯一旧快照。恢复失败保留待恢复门禁及原包。
- 卷名称、真实宿主路径、driver、选项和标签绑定部署、节点及环境。管理容器路径使用data，Docker挂载源使用host_data。实际能力探针核验UID和挂载标志；新布局尚未发布时，能力不足可沿用tmpfs，已有磁盘资料要求兼容节点继续恢复。
- `runtime/scratchpad-mount/mount.json`与持久`layout.json`共同证明目录归属；已登记目录只含mount.json、lower、work，lower必须为空，目录保持管理端私有。创建归属标记先于lower/work，部分创建按同一身份续接。未知同名内容保留并阻挡挂载接管。
- 本机完整及精简备份保全真实数据。节点集群接线由集群任务持有：节点导出须在`scratchpad_runtime_registered`通过后动态排除工作目录，未知同名目录随迁移包保全。回退候选须识别并保护磁盘资料与最新HOME。
- 内存收益按退出tmpfs的shmem独立报告，普通页缓存、cgroup、进程内存及磁盘成本分别解释。接纳性能以固定sender、同宿主交错配对和明确负载的证据为准，实际发行镜像另做节点灰度。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 转存失败、磁盘满、内容变化或源启动身份改变 | 保留原实例及上次快照，阻挡后续停止移除 |
| 本次启动尚未恢复旧快照 | 拒绝新转存，保留原包及恢复定位 |
| 恢复失败或目标有未知内容 | 保留待恢复门禁及原文件，按同一恢复身份重试 |
| 外来环境、卷标签或挂载选项不符 | 拒绝复用与清理 |
| 已登记工作目录出现未知内容或外来标记 | 拒绝挂载及迁移排除，保留现场 |
| 未登记的同名历史目录 | 迁移保全；挂载接管要求先对账 |

### 5. Scenarios and Examples

- 正常：空闲旧CLI完成转存后重建，新CLI在原路径读取同一session文件，真实历史会话继续执行。
- 边界：转存后停止失败，源仍在同次启动中继续写入；对账沿用最新文件，下次转存保存新内容。
- 错误用法：CLI重启后先对空tmpfs转存。正确处理是先按旧快照恢复并保存本次启动证明，再允许新的转存。
- 错误用法：仅根据目录名称排除历史文件。正确处理是核验双份协议和私有目录，未知目录随迁移包保留。

### 6. Tests Required

- `test_cli_scratchpad`覆盖原路径、权限、硬链接/符号链接、三会话、源启动变化、同次启动继续写入、未恢复快照保护、旧回执、磁盘满、发布/恢复中断、跨账号及节点归属、完整/精简备份；集群迁移文件工具由集群交付追加验收。
- 登录草稿夹具提供实际镜像Config/Labels结构，`test_login_drafts`继续验证旧布局删除、重试和对账；账号及评审运行环境回归核对原门禁与停止顺序。
- `deploy/flower2api/verify_scratchpad_storage.py`在无外网隔离Docker中使用真实官方CLI和模拟上游，验证原会话续跑、两账号内容归属、安全挂载、重启前后快照保护、能力不足回退及3×8MiB退出tmpfs。性能配对模式覆盖真实sender、并发、吞吐、TTFT、分位延迟、冷启动和CPU。

## Scenario: 人工节点集群、所属执行与停机迁移

### 1. Scope / Trigger

- 人工分配改变Docker、HOME、工作区和出站执行位置，中央继续持有账号策略、唯一Gateway凭据所有权、任务和准入权威。默认`local`节点保留原单机路径。
- 首版使用中央可达的Linux x64服务器、同批control/account镜像、专用SSH密钥及已核对主机公钥。控制、业务和PTY通道各自保持原生命周期；操作规范见`deploy/flower2api/CLUSTER.md`。

- 账号、运行环境与请求诊断公开展示节点归属及原执行位置时沿本合同。

### 2. Signatures

```text
GET/POST /api/nodes
GET /api/accounts -> effective_claude_code_version:string, claude_code_version_source:account|global
POST /api/nodes/host-keys
POST /api/nodes/{node_id}/check
POST /api/nodes/{node_id}/prepare -> 202，返回已登记的公开安装状态
POST /api/nodes/synchronize -> 202，服务端选择当前可信批次并返回 {items}
ArchiveIndex(path): Mapping，临时磁盘清单
ProfileReference={sha256:HEX64,bytes:int>=2}
NodeDeployment.prefetch_images(node) -> tuple[str, Image]，返回账号批次和已核验的节点控制镜像
NodeSynchronization.install(installer,node_id,revision,maintenance=None,stage_only=False,late_restore=False) -> dict
GET /nodes、已登记管理页面及其尾斜杠地址 -> SPA HTML
PUT /api/nodes/{node_id}/enabled
PUT /api/nodes/{node_id}/name -> 更新显示名与配置版本
DELETE /api/nodes/{node_id} -> 202，返回原移除操作状态
GET/PUT /api/accounts/{aid}/node
GET/POST /api/accounts/{account_id}/node-migrations
GET /api/accounts/{account_id}/node-migrations/{operation_id}
POST /api/accounts/{account_id}/node-migrations/{operation_id}/{resume|cancel}
POST /api/environments/{environment_id}/maintenance {operation,expected_generation?}
cluster_node_ops.py check|status|stop|up --data-root PATH --host-data-root PATH
cluster_backup.py backup --data-root PATH --backup-dir PATH --epoch HEX32
node_backup.py verify-cluster --central-backup PATH --node-backup PATH [--node-backup PATH]
```

- bench追加`bench.cluster.2`、`bench.node-executions.3`、`bench.node-login-drafts.4`，定义分别归`cluster_schema.py`、`node_execution_schema.py`、`node_login_draft_schema.py`所有。新增`cluster_nodes/account_node_assignments/node_migrations/node_executions/node_login_drafts`；旧账号默认归属local，保留冻结基线摘要。
- Node持有`node-execution.sqlite`受限投影，默认本机迁移目标使用`node-execution-local.sqlite`。完整中央可写库和管理员凭据保持中央所有。

- `GET /api/accounts` 可选追加 `node:{node_id,node_key,node_name,kind,enabled,revision,phase}|null`、`node_observation:{state,stale,observed_at}|null`。账号身份使用外层 `id`；`ClusterStore.assignment_summaries() -> dict[int,dict]` 批量只读，归属版本取分配记录的 revision。

### 3. Contracts

- 节点迁移选择器从`GET /api/accounts`读取有效CLI版本；列表与`GET /api/accounts/{aid}/cli-settings`共用`_resolve_account_cli_version`，账号版本优先、全局版本兜底，并返回`claude_code_version_source`。读取列表只生成投影。
- `GET /api/nodes`的`account_count`只统计关联到`accounts.deleted_at IS NULL`的归属，包含人工停用账号；软删除的历史归属继续保留，零账号节点返回0。
- 节点安装在返回202前核对原配置并持久化`preparing`、预留更新活动；单节点后台线程持有原操作锁及有限续接证明，结束后保存`prepared/failed`并释放活动。重复同版本提交复用在途安装，版本变化仍拒绝；安装期间移除节点返回409。启动失败释放原锁与活动；服务重启将旧`preparing`标为`needs_check`，保留原目标和私有日志，后台沿原操作重新核对组件。
- 节点页提交受理后关闭确认窗，处理中及等待状态按3秒读取原节点列表，已托管空闲节点每15秒核对自动同步进度；离页清理轮询，返回页面从持久状态恢复。安装中禁用重复安装与移除；提交结果未知先只读核对，错误按受控说明显示。
- Rust为Vue已登记管理页面显式提供SPA入口及尾斜杠别名，包含`/nodes`；页面登录仍由Vue原守卫处理，管理API与未知路径保持原鉴权边界。
- `NodeLocation={node_key,account_id,environment_id,assignment_revision}`核对安装、正式账号和分配标记；具体工作另冻结实际环境`generation`、原source、操作和内容摘要。分配版本、环境代次、草稿身份及租约代次分别使用各自模型。
- Node私有UDS由同批control的长驻`cluster_agent`持有真实runtime/jobs。SSH只调用`cluster_agent_client`固定操作；轻量入口、Actor和SSH共用具体操作白名单，控制查询/续接保留独立槽位。
- 中央持有真实Gateway租约与原QuotaGuard许可。`ExecutionLeaseProof`只传`owner/generation/expires_at/exclusive/shared_cli`，从Gateway回执投影时保留其原`phase`在中央核对，claim后使用更新的截止时间。证明过期关闭新启动和输入；原Scope可恢复停止能力，实际停止确认后才释放原许可。
- 原Pi/Projects、Run、续聊、场景、私有评审和独立程序沿冻结工作调用Node原执行器。中央保留调度、预算、业务接受及最终验收；文件、日志、统计和快照从原执行位置读取。未知输入只查询同操作收据，已提交模型和未知RT交换保持单发。
- `TransportBinding`沿原字段，远程endpoint固定为中央`V3_RUNTIME_URL`的`/cluster-transports/v2/{deployment_digest}/{node_key}/{environment_id}/{assignment_revision}`。中央剥离服务认证后经独立SSH业务socket转发，核对账号/环境/实际代次与认证，保留原请求字节、SSE、取消和用量路径。
- legacy/native293及账号count_tokens、usage、遥测、预热和受管OAuth出站遵守同一节点归属及原代理。后台固定目标继续关闭自动重定向；独立账号使用当前Node HOME，绑定账号保持Gateway唯一刷新权和Node AT-only。
- 原`CredentialOwnership`继续管理关联、解绑、归还、重授权和退休。Node先持久原操作意图并确认真实角色停止，再发布原绑定结果和完整材料；迟到普通prepare不得写回旧绑定。published回执仅能重读原结果。原账号解绑后，配置缓存按实际Node SQL绑定允许新正式所有者接管原Gateway ID。
- generation=0的未准备独立正式账号退休仅建立无凭据停用投影，核对原账号/环境/分配、未知资料和实际角色，不为删除创建CLI或OAuth。投影中断按同一分配标记接续。
- 人工停用bench账号可迁移，保留enabled原值。独立迁移沿原owner/profile锁、持久maintenance归属、实际源fence和完整校验执行，保持lease=null；绑定迁移沿原真实排他租约。提交前取消先确认目标停止再恢复源；CAS后继续原目标激活。
- 暂停节点关闭普通新工作。不启动CLI的设备纯读、原操作停止及凭据交接收尾继续核对原Scope。节点容量或连接未知保持可见，其他节点独立准入。
- CPU、物理采样、私有请求快照、采集/CRIU和环境维护按人工归属落到Node原方法；中央先发现实际代次，前后核对归属及SSH配置，再CAS镜像环境。CPU保留原在线调整语义；采集/CRIU以每调用`lease_gateway/lease_owner`消费真实中央租约，避免替换共享runtime.gateway。
- 维护页面冻结`expected_generation`并原样交给所属执行路径。远程CC携带该字段时须为严格整数并匹配重读后的实际代次，在租约及停止前拒绝旧页面；Node再核对原Scope的generation。历史CC调用允许省略字段，本机CC的null沿原可选调用；AGY维护按其独立合同必填严格整数。
- 配置/维护SSH结果未知时，中央保留关闭的原租约；显式环境对账确认实际停止后释放。原Node配置审计和实际状态用于重读，不以TTL单独认定停止。原授权/凭据待确认继续由原协调器收口。
- 环境管理私有输入沿Actor的2MiB预算；响应预算由共用`response_limit`决定：请求快照8MiB，其余4MiB，服务端、轻量客户端和SSH一致。快照仍由原`read_capture`执行6MiB文件、UUID、账号和保留期校验；模型业务流不经该JSON预算。
- 环境摘要从Node原读取器取得采集/CRIU设置，Gateway观察仍核对环境、代次、内核及采样时效。缺失或失联显示未知。请求诊断的可选`execution_location={node_key,environment_id,generation,assignment_revision?}`来自同次已验证传输并沿原JSON持久化；历史缺字段保持未观测。Run详情使用原执行账本定位。
- AGY尝试同样从已核验TransportBinding冻结execution_location；当前本机执行的node_key为local、assignment_revision为空，与平台/凭据/工具轮的context独立共存。字段缺失保持未知，禁止根据当前账号归属补写历史位置。
- Node从首次安装保存自己的更新目录与实际镜像来源。来源校验沿原`image_reference`命名合同支持自定义批次；正式签名发行仍使用原独立规则。已托管节点后台自动识别当前目标；同批幂等复核，跨批经原工作排空、停止、原地切换组件后恢复，保持原HOME和身份。历史中央首次能力接入及离线应急沿集群停机SOP。
- 节点镜像预取按中央的实际 OCI 平台、根文件系统 `RootFS` 和 `vibebench.product/role/release` 标签核对目标。Docker 返回平台清单时，以所选平台的 `Available=true` 确认可导出性。节点现有引用完整时先复用。跨 daemon 的不同 ID 以原始配置摘要核对；中央不可导出时，核对两端同库同摘要和平台配置。
- 节点缺完整副本时，优先从中央流式导出并沿固定 SSH 通道导入。中央不可导出时，用其实际 OCI descriptor 或镜像 ID 与同库 `RepoDigests` 共同固定摘要，先在中央补齐。中央仍无法导出时，节点可匿名按该摘要拉取，核对仓库摘要、平台、层及角色批次后才绑定目标标签。Docker API 1.48 起在导出和导入时传递选定平台。旧 API 沿单平台归档接口。
- 自动同步与兼容维护先核验两类镜像，再登记新切换日志并开始排空。普通同步的镜像预取可让位于中央切换，兼容维护在预取前后复核原 `operation_id` 和 `epoch`。预取失败保留尚在运行的原角色，公开原目标及固定失败原因。已有切换日志的作业沿原阶段收口。
- 原迁移使用磁盘SQLite索引逐条读取和写出兼容的`{identity,entries,excluded}`清单，取消清单16MiB及100000条业务上限。临时定义由`cluster_archive_schema.py`纯模块所有，索引随当前临时目录删除；业务库版本台账保持原链。单条元数据解析预算128KiB，路径、类型、权限、逐文件/整包摘要、冻结实际字节与真实剩余磁盘继续核验。
- 迁移export/verify-import/prepare-import及大profile prepare-files取消UDS/SSH总时限。迁移包和profile取消600秒总传输时限，HTTP逐次读写15秒、SSH连接与存活检测保持。排空默认沿原操作等待并续约，服务关闭或租约变化终止推进。
- 普通profile准备以1MiB作为通路选择阈值，大文件进入私有摘要文件；迁移同样使用`profile_references`。固定文件名仅`.credentials.json/.claude.json/settings.json`，实际长度、SHA256、0600权限、单链接和归属逐次核验；绑定账号先去除RT。历史端通过固定受限适配复用其原锁、类型和准备器，身份算法沿原版本。
- `record.progress.stage`只表示实际处理步骤，确认阶段仍由原回执推进。reconcile公开固定`failure={code,stage,message,action}`，历史缺字段使用原通用提示；任意底层正文及私有路径排除出公开投影。继续迁移保持原operation_id和所有权，提交前取消继续先撤销目标再恢复源。
- 节点同步私有日志保存原目标、配置摘要、原控制/镜像、账号与隔离收据。并发最多两台，单节点组件切换与两端迁移共用操作锁。运行中的迁移先完成后同步；登记后尚未建立目标副本时可先同步空目标。暂停迁移按下述维护兼容规则核对实际停止和原租约，保留迁移资料及关闭的账号准入，只升级组件。
- 同步核对真实jobs、流、草稿、独立验收、凭据交接和实际角色。暂停接单偏好独立保存。停止原角色和控制后原地切换组件，作业持久data_policy=in_place；不生成数据根全量副本或隔离恢复副本。旧在途复制进程按作业ID及原镜像确认后停止。新控制失败在账号更新前恢复原实例；账号恢复已开始则保留当前现场继续。相同账号镜像以原撤销fence复用原角色和代次，镜像变化交原生命周期重建；回传传输绑定按实际账号镜像批次核验。
- 全局完整备份收齐同部署、同epoch的中央及全部登记Node快照。SQLite复制使用原backup API；离线固定副本读取使用immutable，避免生成WAL辅助文件改变清单。组合恢复核对安装身份、归属/分配和实际环境，保留pending/reconcile事实。

- 账号节点摘要从单次 SQL 读取有效账号与未删除节点，明确选择公开字段；账号停用继续返回归属。观察复用原缓存，state为reachable/unreachable、observed_at为秒、stale沿原60秒判定。列表读取不连接Node、不准备环境。
- 网关账号按外层 `cc2api_account_id` 关联节点摘要，通过同源 `/runtime/api/accounts` 批量读取。账号列表沿原5秒刷新；隐藏和卸载取消读取，代次丢弃迟到回执；读取失败保留原身份并标记归属待刷新。
- 账号与环境显示当前归属，请求列表只读末次 `last_attempt.execution_location`，详情从独立返回的有序 attempts 读取各次及末次位置。历史位置禁止用账号当前归属回填；只有真实node_key=local才显示默认本机。缺字段显示节点未观测，零次尝试显示无执行尝试。

### 4. Validation & Error Matrix

| 条件 | 期望 |
| --- | --- |
| Node参数或私钥格式非法 | 固定校验错误，不回显输入材料 |
| 账号版本继承全局或人工停用 | 列表仍返回有效CLI版本；停用账号仍计入节点归属 |
| 账号软删除 | 账号列表隐藏且节点计数排除，原历史归属保留 |
| 安装前缺必需配置、配置版本不符或平台维护 | 409，保持原组件归属 |
| 后台安装失败或服务重启中断 | 持久状态分别为failed或needs_check；释放活动后允许明确重试 |
| 已登记页面直达、刷新或尾斜杠 | 返回HTML；原管理API与未知网关路径继续鉴权 |
| 主机公钥、Scope、绑定、分配或实际代次变化 | 拒绝原提交，保留原归属及恢复定位 |
| malformed Node结果携带较新代次 | 结果校验失败，中央镜像保持原代次 |
| 远程维护携带过期或非整数expected_generation | 原公共入口返回409，在租约与实际停止前拒绝 |
| 旧证明、未知输入、未收口执行或RT未知 | 新业务保持关闭，查询/原停止继续按原范围 |
| Node暂停或bench人工停用 | 普通准入沿原门禁；允许合同中明确的管理或迁移操作 |
| 原快照缺失/过期/损坏 | 分别返回原404/410/503合同 |
| 配置准备回包丢失且尚未提交Node | 按本次唯一owner回查并收口原租约 |
| Node配置/维护提交后回包未知 | 保留原租约，实际停止对账后释放 |
| 源离线、资料不全或目标校验失败 | 保留原迁移阶段与维护状态 |
| 大清单、大profile或长迁移 | 逐条清单及独立文件通路，按实际空间与摘要核验 |
| 源导出暂停且目标无副本 | 空目标可先同步；原迁移随后按同一操作继续 |
| 工作或凭据维护未完成 | 保存等待原因，按原目标自动重试 |
| 同批组件 | 幂等核验，账号状态沿原生命周期保持 |
| 同 ID 的目标平台内容残缺 | 定向导入后重读确认两类镜像，成功后才切换。导入或复核失败时保留原目标供重试 |
| 中央运行镜像的目标平台 `Available=false` | 先核验并复用节点完整副本。无副本时按已冻结摘要补齐。摘要不匹配或仓库缺内容时在排空前失败 |
| 同名目标内容冲突或残缺引用归属未知 | 拒绝覆盖，保留原组件并提示核对节点制品 |
| 组合备份缺Node、错epoch或错安装归属 | 完整性校验拒绝，保留已生成快照 |
| 节点不可达、观察过期或账号列表读取失败 | 保留已保存归属，分别显示不可达、过期或待刷新 |
| 旧请求缺执行位置或请求无上游尝试 | 分别显示节点未观测或无执行尝试，原记录保持可读 |

### 5. Scenarios and Examples

- 正常：准备SSH节点2后，为尚无执行资料的账号1发送`PUT /api/accounts/1/node`，body为`{"node_id":2,"revision":1}`；原统一网关继续使用该账号原令牌。
- 正常：全局CLI为`2.1.293`且账号继承时，账号列表返回该有效版本供迁移确认冻结；本机14条归属中10个账号已软删除，页面`account_count`为4。
- 正常：提交安装收到202后可切页，返回后继续显示后台安装状态；后台作业真实完成后发布prepared。错误用法是用HTTP响应结束判定安装完成，或给所有未知路径返回SPA绕开网关鉴权；正确处理是保留真实后台活动并仅登记已知页面入口。
- 错误用法：直接把数据库内可空的`claude_code_version`作为迁移按钮准入版本。正确处理是返回解析后的`effective_claude_code_version`。
- 边界：人工停用的独立账号迁移仍保留enabled=0，当前HOME/RT及未知字段随完整包保存；后续普通执行沿原准入。
- 错误用法：对已有环境直接PUT换节点。正确处理是`POST /api/accounts/1/node-migrations`，冻结`{"operation_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","node_id":2,"revision":1,"version":"2.1.293"}`并按原操作查询/恢复。
- 错误用法：SSH断连后重新发送模型、OAuth或另起输入。正确处理是先查询原Scope/回执，未知状态保持隔离，明确实际停止后再按原业务恢复。
- 错误用法：合并诊断时用AGY context替换执行位置字段。正确处理是保留两个可选字段，并在同一真实尝试上分别记录平台上下文和冻结的执行位置。
- 镜像检查示例：节点 `Id` 和中央相同，`Architecture` 为空且 `RootFS` 缺少 `Type`。直接复用该引用会让容器创建失败。由 `prefetch_images` 补齐选定平台后，再读取完整的配置和层信息。
- 中央镜像正在运行且 `Available=false` 时，运行状态只说明已有快照可以启动。按实际 descriptor 与同库摘要核对后获取完整制品。用可变的仓库标签补齐可能取得另一份镜像。

- 正常：账号已迁移到Node B，历史请求仍显示原尝试的Node A；跨节点重试逐次显示各自环境和代次。错误用法：用账号当前归属填补旧请求。正确处理：旧记录缺字段时保持未观测。

### 6. Tests Required

- `test_cluster*`覆盖真实双SQLite、私有UDS/SSH、错误Scope/认证、有限证明、未知输入、各执行消费者、迁移CAS和恢复；Node关闭后仅恢复实际停止能力。
- `test_account_cli_settings`通过真实HTTP账号列表核对全局继承、账号覆盖与设置接口一致，软删除隐藏且读取保持账号数据和执行记录；`test_cluster_nodes`核对删除过滤、停用计数、空节点为0、历史归属保留及恢复后的计数。
- `test_cluster_node_installation`覆盖202、同节点去重、版本竞争、安装中移除、作业跨请求门禁、失败重试、线程启动失败及重启中断；`verify_cluster_ui.py`覆盖提交关闭、刷新恢复、自动收口与提交响应中断只读核对。Rust真实组合路由测试覆盖全部管理页面、尾斜杠、公开hello及未知路径鉴权。
- `test_cluster_environment_management`覆盖原HTTP路由、暂停节点管理、大快照、claim延期字段、未知提交保留门禁、实际对账释放及坏回执不推进中央代次；原本机CPU/采集/CRIU测试继续执行。
- 远程维护过期代次用例经原公共入口验证409、零实际停止和零维护租约；AGY诊断单测与`verify_cluster_request_ui.py`验证context与本机execution_location共存、历史未知以及1440/390布局。
- `test_cluster_node_docker`按开关运行随机隔离部署：同一真实Rust网关的双账号双Node JSON/SSE及并发、冻结诊断、原管理HTTP/WS、完整所有权、零代删除、独立迁移故障隔离、Node停机换批及HOME身份保留。上游及凭据均使用合成夹具。
- `test_cluster_recovery_limits`核对大于16MiB且超过100000条的原JSON清单、大profile、摘要/权限/路径限制及固定错误投影。规模演练须实际导出、恢复并核对原树，不以元数据样本代替完整恢复。
- `test_cluster_synchronization`核对旧控制自动停止原地换批、同批幂等、原容器回退、未知角色、未完成迁移、空目标先升级、互斥及平台重启续接。`test_cluster_system_update`核对宿主排空/取消/恢复及真实更新状态机先停止再原地切换的顺序。
- `test_cluster_deployment` 覆盖同 ID 缺配置、导入后内容仍残缺、同名冲突、归属未知和导入错误。`test_cluster_synchronization` 覆盖普通同步及兼容维护在预取失败时保留原角色，以及恢复后按原目标切换。隔离 Docker 同 ID 缺配置的换版验证需要核对两种镜像的补齐、节点健康和原账号资料。
- 中央不可导出回归覆盖节点完整副本复用、中央按摘要补齐、节点匿名按摘要补齐及不匹配拒绝。隔离 containerd 删除测试镜像的压缩层后，应同时观察中央容器仍可运行、镜像 `Available=false`、节点完成补齐。仓库缺层时确认拒绝绑定和原组件仍可用。
- `verify_cluster_node_upgrade.py`的隔离Docker开关覆盖自动控制更新保持原代次、账号镜像变化重建、组件恢复与最新资料保留、历史端大profile。`verify_cluster_ui.py`覆盖统一同步、明确失败动作及390px布局。
- `test_cluster_backup`及原备份测试核对真实SQLite隔离复制、清单/逻辑摘要、同批组合对应和pending恢复事实。`verify_database_definitions.py`核对当前bench5/gateway7及原步骤1—4冻结来源。
- 前端生产构建及`verify_cluster_ui.py`、`verify_cluster_draft_ui.py`、`verify_cluster_request_ui.py`覆盖冻结确认、迟到响应、独立/停用账号、原草稿/WS、历史未观测及390/1440布局；Rust执行fmt与全量测试。
- `test_cluster_nodes`、`test_cluster_main`覆盖批量摘要的只读性、字段白名单、删除过滤、停用账号及失联归属；`verify_execution_node_visibility.py`覆盖账号/环境/请求/任务账号的列表与详情、读取失败、跨节点历史、无尝试和1440/720/390px。节点样式复用ExecutionNodeBadge及兼容入口的renderAccountNode，长标识可换行，手机请求记录保留结果和详情入口。

## Scenario: 远程节点改名与移除

### 1. Scope / Trigger

- 涉及管理员改名、卸载远程节点、读取原节点历史或平台排空时，核对节点操作锁、远端归属证明与持久移除状态。

### 2. Signatures

- `PUT /api/nodes/{node_id}/name` 接受 `{revision, name}`，返回更新后的节点。`name` 限 1 至 80 字符，裁剪两端空白并拒绝控制字符。
- `DELETE /api/nodes/{node_id}` 接受 `{revision}`，以 `202` 返回 `{operation_id, state, phase, reason}`。`GET /api/nodes` 对活动节点返回同形状的 `removal` 或 `null`。
- `POST /internal/v3/system-updates/snapshot` 返回 `{nodes, node_removals, blockers, ...}`。`node_removals` 每项含 `name`、`state`，供原宿主排空读取。

### 3. Contracts

- 改名只写 `cluster_nodes.name` 并更新版本。SSH 登记 JSON 始终保留原字节，供在途迁移、执行、草稿及组件维护验证摘要。历史投影读取归档节点的名称和标识。
- 按节点配置版本和操作锁受理移除，登记 `preparation_json.removal` 并关闭接单。保留已完成或取消的迁移、已关闭的执行和草稿。当前有效归属包含人工停用账号。软删除账号保留历史关联，在移除开始后沿用新账号登记入口。
- 移除按 `checking → retiring_components → clearing_data → completed` 推进。`needs_check` 保留原操作 ID 与检查点，重试不产生新操作。核对原 SSH 主机、安装标记、控制角色、网络与数据根身份后推进。以宿主解析的真实路径和挂载身份识别其他 Docker 绑定源。原数据根可位于独占挂载，子挂载及其他容器共享源阻止清理。先停止控制角色，再移除本节点组件和网络，最后清空原数据根。保留空目录、中央历史及共享镜像。
- 远端清理核对通过后归档节点并释放 SSH 地址。关联到原节点的中央迁移、执行和关闭草稿保持历史视图。原节点独有的日志和产物返回 `410`。已归档且已确认清理的无账号关闭草稿按历史投影平台快照。
- 持久移除纳入平台升级和回退的排空条件。正在执行的移除可以完成，需重试或等待续接的操作使同版本平台更新在切换前结束。宿主在实际请求节点备份前保存 `node_backup_requested`，排空退出时仅收口原操作已经请求的备份。

### 4. Validation & Error Matrix

- 名称非法返回 `422`。本机节点、旧版本、有效账号归属、活动迁移或执行、未关闭草稿和组件维护返回 `409`。
- SSH 断线、原数据根身份变化和共享挂载返回可重试的 `needs_check`。已安装节点首次缺少归属证明时保持未归档。被新数据占用的原数据根仍须保留。
- 合法版本重试同一删除动作时返回原回执。移除已完成的节点由历史定位读取，远程文件接口返回受控 `410`。

### 5. Scenarios and Examples

- 已取消的迁移仍指向旧节点。执行 `DELETE` 后跟踪 `removal`，远端确认空目录后原 SSH 地址可再次登记，迁移记录沿原节点 ID 查询。
- 其他容器通过软链接挂载本节点的目录。比较容器报告的路径字符串会漏判，应该使用 SSH 宿主解析实际路径和文件系统挂载位置。
- 平台等待排空时收到移除待重试。宿主释放原平台门禁并提示从节点管理续接。原节点清理完成后重新发起更新或回退。

### 6. Tests Required

- `test_cluster_nodes`、`test_cluster_draft_schema` 覆盖改名换版、有效账号门禁、终态历史、断线重试、同地址登记和远程文件状态。
- `test_cluster_removal` 覆盖源路径别名、独占挂载根、嵌套挂载和清理幂等。隔离双节点验收使用真实 SSH 与 Docker，验证共享挂载阻断和回执丢失后的续接。
- `test_system_update_snapshot_lock`、`test_cluster_system_update` 覆盖移除期间的升级与回退门禁、待重试快速退出、归档后的历史投影和其他节点状态保护。`verify_cluster_ui.py` 覆盖改名、账号门禁、进度及重试。

## Scenario: SSH 节点密码认证与旧密钥配置兼容

### 1. Scope / Trigger

修改节点登记 DTO、私有认证存储、OpenSSH 命令与隧道、管理表单或节点安装配置诊断时适用。节点用户名沿原配置，认证方式支持私钥和 SSH password。

### 2. Signatures

- `POST /api/nodes`：在原配置上增加 `auth_method: private_key|password`，缺省为 private_key；只写 `private_key?:string|null`、`password?:string|null`。
- `GET /api/nodes` 的 SSH 投影增加 `auth_method`；本机为 null。NodeConfiguration 继续作为公开配置的严格模型。
- `SshNode.save_password(password)` 保存私有密码；命令由 `_command` 统一认证，Docker、sender、PTY 继续建立独立连接。
- `NodeInstallationConfigurationError` 仅公开缺失的 `V3_DEPLOYMENT_ID/V3_RELEASE/V3_CONTROL_IMAGE/V3_ACCOUNT_IMAGE` 名称，准备接口返回 409。

### 3. Contracts

- 所选认证方式必须对应唯一非空材料。私钥长度 64～32768 字符；密码长度 1～4096 字符，拒绝 NUL、CR、LF。密码保留前后空格、中文及 Shell 特殊字符。
- 私钥与密码排除 model_dump 和 repr，秘密仅进入中央节点专属私有文件；目录 0700、文件 0600。公开 config_json 仅保存配置。密钥节点省略默认 auth_method，保持已发布严格读取器的字段集合；密码节点显式保存 auth_method=password。
- 密码文件通过无链接目录访问及 O_NOFOLLOW 打开，fstat 核对当前 UID、常规文件和私有权限。sshpass 通过单独继承的文件描述符读取密码，业务 stdin、argv 和环境继续排除密码。
- 密码认证限制为 password 和一次密码提交，关闭公钥及键盘交互回退。两种方式继续固定主机公钥、known_hosts/HostKeyAlias、StrictHostKeyChecking，禁用用户 SSH 配置、代理及 agent。
- 命令、独立 Docker/业务/PTY 隧道共享认证构造。超时、失败和关闭按原归属回收进程及 socket；sshpass/OpenSSH 错误仅映射固定公开原因。
- 表单只提交所选材料；切换、成功、关闭和卸载清理秘密。既有节点在线换密和二次认证属于独立范围。
- 固定宿主模板与应用镜像分别维护。旧模板需按 SYSTEM-UPDATES.md 校验原字节、策略摘要及资源设置，通过原服务锁/存储锁同步，再沿维护门禁重建控制端。V3_RUNTIME_URL 沿模板采用中央回连地址。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 空密码、冲突材料、非法方式或控制字符 | 422 固定参数说明，排除原输入 |
| 错误密码 | 检查记录 unreachable，reason_code=authentication_failed |
| 主机公钥不符 | 拒绝连接，固定 host_key_mismatch 原因 |
| 密码文件为链接、公开权限或错误 UID | 拒绝使用该凭据 |
| 缺少中央安装配置 | 409 列出配置名，保留原准备状态 |
| 旧节点缺 auth_method | 默认私钥；新密钥节点继续可由旧版配置模型读取 |

### 5. Scenarios and Examples

- 正常：原主机配置加 `{"auth_method":"password","password":" 合成密码! "}`，保存原值并完成检查；连接复用及服务重启后重连均读取本节点私有文件。
- 边界：原请求只含 private_key，继续以密钥登记；公开列表显示 private_key，数据库保持原字段集合。
- 错误用法：同时提交 password 和 private_key，或把密码拼进 sshpass 参数、Shell、环境或业务 stdin。正确处理是唯一材料校验与独立文件描述符传递。
- 回退：密码节点要求包含 sshpass 的新控制程序；回退旧程序前先完成密码节点账号迁移和引用收口。私钥节点保留旧格式。

### 6. Tests Required

- `test_cluster_password` 核对严格 DTO、原值保存、只写/repr、目录权限、符号链接拒绝、重复登记清理、默认密钥持久字段和安装配置诊断。
- `CLUSTER_SSH_PASSWORD_TEST=1 ... -m unittest test_cluster_ssh_password` 使用合成密码与隔离回环 Docker sshd，核对正确/错误密码、主机指纹拒绝、特殊字符和大 stdin、实际 Docker SDK、三类隧道、重连及进程清理。夹具构建见 `deploy/flower2api/fixtures/ssh-password/Dockerfile`。
- 原 `test_cluster_nodes/test_cluster_ssh/test_cluster_backup` 回归，实际已发布 NodeConfiguration 重读新密钥配置；前端构建及 `verify_node_password_ui.py` 核对认证切换、掩码、唯一凭据、清理和 1440/390 布局。

## Scenario: 集群迁移兼容与暂停维护

### 1. Scope / Trigger

- 跨CPU代际/厂商、未准备或旧批次目标、目标创建中断，以及暂停迁移期间的组件/平台升级。现有交付制品仍为Linux x64，ARM需要匹配的运行制品。

### 2. Signatures

```text
MigrationCoordinator._ready(node, synchronize=False)
NodeExecution._prepare_locked(..., import_intent=None)
paused_migration_record(migration) -> dict | None
paused_migration_lease(database, environment, snapshot) -> dict | None
GET .../node-migrations: failure.stage 可为 preflight；运行中的恢复不展示上次failure
```

### 3. Contracts

- 首次归属和迁移选择器允许选择已启用、尚未准备的节点。保存首次归属后，后台扫描按account_count纳管；普通准备遇到未就绪组件主动提交同步并返回可重试的RuntimeBusy。迁移先在后台`preflight`等待原安装/自动同步、核对实际agent部署及批次，再取得两端操作锁并隔离源。检查保存画像的格式发生在登记前，原像完整性失败不会先停止源。
- 源隔离收据确认后，按原环境ID/账号/generation同步中央state=stopped；原运行意图保存在record.source_state。包、profile文件和逻辑身份沿原操作保留。普通节点准备取消1MiB拒绝条件，大profile继续由deliver_preparation按摘要文件通道传输；2MiB控制消息预算保持。
- 新操作在execution检查点保存source_node_location/target_node_location，字段为host、port、host_key、data_root。名称、SSH用户名及认证方式变化不改变资料定位；主机身份或数据位置变化仍拒绝。历史检查点缺location时继续核对原config_sha256。
- 暂停维护仅认可phase=reconcile、last_confirmed_phase为source_fenced/exporting/importing/verified、无cancellation的提交前操作。中央分配仍在原源且为reconcile，revision、environment_id、source_generation和source_fingerprint_sha256一致；网关active/waiting/importing全为0，唯一排他holder的owner/generation与原gateway_lease精确一致。独立账号保持空租约。历史SSH源中央state=ready时仍须取得节点实际停止证明。
- 本机源核对原fenced标记和全部角色Running=false/Pid=0。SSH源核对同标记、实际角色ID集合及停止状态；已发布的目标核对原operation、node、account、environment、revision和source_generation及published/prepared标记。无目标目录时不得存在目标角色。凭据交接、中央执行及连接继续排空。暂停账号从组件重建名单排除，全部资料原地保留，原租约和迁移游标保持。
- 目标创建失败留下reconcile时，prepare_import仅凭原published标记与相同import_intent恢复。原登记角色必须均已停止、没有外来角色或实际作业；收口这些角色后恢复stopped并按原身份重建，HOME、profile和迁移尝试保持。
- 已取消迁移的目标副本可随组件原地换批保留：中央phase及last_confirmed_phase均为cancelled，target_revoked收据精确匹配操作、目标节点、账号、环境及source_revision+1；节点node-fence同范围且为fenced，node-migration-target和原操作revoked.json同范围且为revoked，目标标记source_generation匹配原记录。实际剩余角色须属于fence.stopped_containers及已登记角色类型，全部Running=false/Pid=0。核对通过后沿原同步日志继续；保留HOME、工程、标记、取消状态和中央归属。新作业恢复旧控制组件时保留当前节点执行库和最新资料；历史缺data_policy的快照作业沿原恢复分支。backed_up作为旧宿主兼容的排空回执保留，公开页面显示已停止待切换。
- 迁移prepare-import回执的binding.release_id按configured_release(runtime)核对账号镜像来源，组件健康继续核对runtime.release_id。启用更新底座时允许V3_ACCOUNT_RELEASE与V3_RELEASE不同；账号、环境、代次、绑定秘密及原操作范围继续核验。旧控制端批次误判留下的importing/reconcile沿原操作和transfer_id续接，保持单次源隔离/导出，成功激活后释放原租约。
- 已保存CPU/机型画像随账号保留；目标硬件能力保持实际值。旧版仍使用各自的CPU和模板校验，跨代迁移后回退应选择包含该兼容能力的版本，或先按原迁移流程迁回旧版支持的节点。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 保存画像与目标CPU跨代/跨厂商 | 保留原画像并使用目标实际能力 |
| 新x64 CPU没有登记模板 | host-cpu-v1及通用机型，持久身份只生成一次 |
| 目标组件尚未就绪 | 后台preflight准备，源隔离延后 |
| 暂停且原租约、停止及身份均确认 | 保留原操作/资料，允许原地组件维护 |
| 外来holder、活动请求/导入、未知角色或标记不符 | 继续阻断维护 |
| 目标本次创建失败且全部角色已停止 | 收口本次失败角色，继续同次迁移 |
| 已取消迁移目标残留停止角色且双端撤销证明一致 | 自动识别历史副本，沿原同步完成组件换批并保留资料 |
| 控制组件已更新且账号镜像沿用原批次 | 按配置账号批次接纳准备回执；仅匹配控制批次的错误绑定继续拒绝 |
| 固定画像损坏/组件不符/位置变化/Docker创建失败 | system_profile/component_version/node_configuration/runtime_preparation固定公开原因 |

### 5. Scenarios and Examples

- 正常：Naples画像迁入Cezanne或Turin节点，保留设备、机型、HOME及工程资料，目标实际flags及核心数按宿主渲染。
- 正常：V3_RELEASE为新控制批次、V3_ACCOUNT_RELEASE为复用账号批次时，目标binding使用账号批次，完成原迁移并激活。错误：把binding改成控制批次来通过校验；正确处理：沿账号来源核对并续接原操作。
- 边界：目标已有本次迁移的停止角色和发布目录；原迁移暂停后原地升级控制组件并保留目标目录，随后继续原操作。
- 边界：取消后目标仅剩停止的account-network，中央归属账号为0；核对原取消收据、目标撤销标记及实际停止登记后自动继续原同步。缺失撤销证明或额外角色须核对原操作，不能仅凭零账号计数或exited状态放行。
- 错误用法：按租约TTL删除占用、把reconcile直接改ready，或删除画像重新随机。正确处理：核对原持久操作、双端实际停止和原代次，保留迁移关闭状态并继续原收口路径。

### 6. Tests Required

- test_system_profile：Turin/Intel首次画像、跨代渲染保持实际能力、旧画像和DMI身份保持、坏格式拒绝。
- test_cluster_migration_runner/migrations/nodes/synchronization：自动准备先于源隔离、名称/认证变更与位置保护、源停止镜像、未准备节点首次选择及自动纳管。
- test_cluster_migration_maintenance/execution：真实SQLite原租约及过期/外来/活动矩阵、源隔离证明、SSH磁盘标记、失败角色恢复保留身份与资料；未知或运行角色保持阻断。
- test_cluster_synchronization：取消目标残留停止网络角色时沿原job_id恢复并原地完成换批，资料字节、取消状态和中央归属保持；中央收据、撤销文件、节点/账号/操作/分配/源代次错配及外来/运行/PID非零角色继续阻断；已完成迁移旧源仍核对原代次。
- test_cluster_migration_runner：控制/账号不同批次完成归属CAS和激活；旧批次误判后的importing/reconcile复用原stage，源只隔离和导出一次；错误控制批次绑定保留源归属、reconcile及原租约。
- verify_cluster_ui：未准备目标可选并可提交迁移，既有确认、未知结果、恢复及窄屏交互保持。
- 隔离SSH/Docker验收：跨代画像完整迁移后读取目标实际CLI；暂停迁移目标原地控制换批及切回旧组件，原停止角色、标记、最新资料和中央游标保持；备份目录保持为空。正常账号升级/恢复保留最新工程文件及大profile。

## Scenario: AGY账号运行环境与Gemini业务接入

### 1. Scope / Trigger

修改AGY公共Gemini路由、账号发送器、原生适配、环境维护、资源或交付时适用。实现入口为gateway的gemini/runtime_transport/agy_runtime、orchestrator的agy_environment及agy_runtime包。管理凭据的唯一所有者继续遵循[AGY凭据合同](../../platform/deploy/agy-credential-contract.md)。

### 2. Signatures

- 公共GET `/v1beta/models`，POST `/v1beta/models/:model:generateContent`及`:streamGenerateContent?alt=sse`。令牌接受x-api-key、x-goog-api-key、Bearer或query key；不同来源冲突及重复query key拒绝。
- Gemini生成可用基础模型名配 `generationConfig.thinkingConfig`。`thinkingLevel` 接受 `MINIMAL`、`LOW`、`MEDIUM`、`HIGH`、`XHIGH`，大小写不敏感。`thinkingBudget` 接受整数 `-1` 或非负值。`includeThoughts` 接受布尔值，响应保留原生 Part。
- 账号发送器POST `/internal/agy/prepare`、`/internal/agy/generate`、`/internal/agy/tools`，复用Bearer、TransportBinding、原请求ID和截止校验；只接受冻结的POST `https://cloudcode-pa.googleapis.com/v1internal:streamGenerateContent`目标。
- `AgyAccessSnapshot`为account_id、credential_generation、access_token、expires_at、email，拒绝refresh_token。`AgyToolCompletion`为request、api_token_id、previous_request_id、body；旧工具控制不携带凭据。
- `agy_runtime.tool_schema.normalize(schema, path='', changes=None)` 返回独立工具 Schema，接收 `functionDeclarations[].parameters` 与 `parametersJsonSchema`。`changes` 可记录 `{path, action}`，原工具定义保持原样。
- `AgySenderConfig`包含protocol_version=1、完整source_sha256、module_root、binary_path、work_root、max_workers和memory_mib。内部监督协议schema_version=1，命令submit/prepare/finish_tools/status/cancel/shutdown，事件持续到job_finalized。
- AGY 监督器 `restore.failure` 和环境摘要 `criu.failure` 可包含 `{stage:string,reason:string}`。`agy_runtime.criu.read_failure` 核对允许的阶段和原因组合。历史回执可省略该字段。
- `AgyController(sender, root, criu, work_root)` 由可信入口传入 `agy.work_root`，在账号发送器容器内处理已核验的观察器与原生进程。
- `native_event.event.control_http_status` 是可选整数，记录失败终态已收到的 AGY 控制 HTTP 4xx/5xx。旧内核可省略该字段。Gemini 公开 `error.code` 使用已核对的状态码。
- 追加`bench.agy-environments.5`：platform_api_environments以唯一gateway_account_id及唯一environment_id绑定现有account_environments，platform固定antigravity。AGY环境account_id为空，名称采用`agy:<gateway-id>`；历史基线保持冻结。

### 3. Contracts

- 候选复用API令牌账号白黑名单、平台、active、凭据ready、已观测model_mappings、冷却、原队列/RPM/并发许可和维护门禁。AGY账号的Gemini/Claude模型都进入固定AGY 1.5.9；公开名与原生MODEL_*或整数ID由受信目录映射，不能按名称猜测。
- 公共目录把令牌可见且可用的 `gemini-*` 模型的 `low`、`medium`、`high`、`tiered`、`xhigh` 后缀版本合并为一条基础名称。相同基础名称跨账号去重。Claude、GPT 和管理端账号原生目录保留实际名称。
- 带档位的 Gemini 名称仍按完整名称匹配。基础名称显式给出有效档位时先匹配该档位，再匹配真实的同名无后缀型号。`thinkingLevel` 优先于 `thinkingBudget`，`MINIMAL` 视为 `low`，预算 `0–1024`、`1025–8192`、`-1` 或 `8193` 及以上分别对应 `low`、`medium`、`high`。省略档位时先找真实同名型号，再按 `high`、`medium`、`low`、`tiered`、`xhigh` 匹配目录。相同优先级继续按原账号负载排序。
- 基础名称和变体都只从令牌权限内账号的真实目录映射到原生执行 ID。目录存在且没有有效映射返回 Gemini 404。当前令牌无可见目录或已知模型暂不可用时沿原 503 路径。网关在原始入站采集后消费 `thinkingConfig`，通过已有私有协议发送目录型号及其执行 ID。请求诊断保留客户端模型名和实际提交的原生 ID，认证恢复和工具续轮沿用选定型号。
- temperature/topP兼容接收后忽略，记录字段及policy=native_default；maxOutputTokens映射原生maxTokens。工具、签名及其他输入继续按实际能力校验。SSE即时交付首个 `functionCall` 前的源帧。原生确认工具轮待回填后，网关登记归属，将缓冲的后续帧聚合成一条 SSE 事件，按原顺序保留 Part、签名、终态和用量。非流式沿同一执行路径聚合 Parts、未知扩展及 usage；禁止伪造 STOP、[DONE] 或成功用量。
- 外部小写 web_search 的无属性限制空声明补字符串 query。显式字段和闭合 Schema 保留。入站采集保存实际客户端正文，原生 MCP 列表与出站参数一致。
- 数组 `items` 缺失、为 `null`、`true` 或裸 `{}` 时，规范化为 `{"anyOf":[{}]}`，使 AGY 1.5.9 出站包含 `items:{}`。`items:false` 以 `maxItems:0` 表示。`prefixItems` 与旧式 `items:[]` 投影为单个元素 Schema，闭合元组保留 `maxItems` 上限，已有更小上限优先。原生接口按统一元素 Schema 表达元组，位置约束会丢失。工具调用和结果仍使用原 JSON 值。字符串 `const` 与已有 `enum` 取交集并输出单值 `enum`。
- 正式OAuth观察器核对完整原版SHA、映像身份及四个指令指纹。原生路由为0xa098532，channelModelResponseStream.Receive接收返回位置0x95d1e90，遥测0x89ed91f，codeassist Scanner栈检查后0x95f3212。Receive在AL给出接收结果、RCX给出已核对的GetChatMessageResponse；Scanner原块先私有归档，再解开SSE及response信封。EOF保留错误未知标记，业务成功同时要求源finishReason/安全拦截终态及真实控制RPC成功。部分文本、usage或通道关闭单独出现均不算成功。
- 管理侧锁内冻结ready状态和AT-only快照。新代采用新worker，最高代次单调，同代不同AT拒绝；旧在途及原工具轮保留归属。工具结果匹配调用方、账号、原历史和函数身份，先回填原MCP并收口，再读当前ready快照开始下一模型轮。concurrency=1复用原许可；pending/reconcile期间可独立收口旧工具，普通发布继续关闭。同结果回执仅在原截止内幂等，副作用只回填一次。
- 同轮多个 `functionCall` 可使用同一函数名。原生 ID 复用时按真实规划器和步骤位置路由结果，公开 ID 保持唯一。相同观察身份的重投只处理一次。不同源块的相同调用按原生真实步骤数核对。先为带 `functionResponse.id` 或使用已支持 ID 别名的结果保留对应位置，支持反序回填。其余结果按出现顺序与同名组内尚未匹配的调用依次配对。不同函数名的结果可以交错。要求整轮数量一致、每个调用至多匹配一次，原生回填与历史步骤按原调用顺序消费。活跃续轮继续核对完整原历史与调用参数。历史导入可从连续用户内容收齐同一批结果。
- 导入历史时，模型轮开头的空 `{}` 可作为一个或多个连续 `functionCall` 的占位，实际调用保留原 Part 下标。相邻用户轮以 `call_<数字>` 作为结果名回填多个同名调用时，数量须相等、整组省略显式 ID、每个别名在历史中唯一，并与函数名及已有 ID 区分。按同名组内顺序恢复调用与结果的 ID，保留原入站内容。异名且只有旧式别名的并行结果仍拒绝。回归 `test_parallel_history_placeholder_and_numeric_result_aliases` 核对原历史位置、参数、ID、结果和冲突拒绝。
- `native_history` 转换 `model.parts` 的 `[{}, {"functionCall": …}]` 时跳过首个空占位。函数调用继续在 `parts/1` 校验，缺省调用 ID 使用原始内容和 Part 索引。续轮前缀、身份比较和诊断沿用原始入站正文。
- 唯一领取原工具轮时同时登记接续轮响应。重读须使用相同鉴权令牌 ID、公开模型和完整入站 JSON，并通过原账号的当前令牌范围检查。摘要对 JSON 对象键排序，保持数组顺序。若同时匹配不同的已登记工具轮，返回 `AGY_TOOL_RESULT_MISMATCH`。
- 并发重读跟随原生成，从首帧读取同一有序响应和终态。后续工具调用的归属先于工具帧登记。重读沿选定 sender 的 120 或 240 秒生成预算，独立于原生工具等待。共享帧缓存预算为 64 MiB，到期或维护排空清理，不持有账号许可、原生作业及凭据。发送前失败释放重读登记，原 MCP 回执可按原截止复用。进入发送边界后，匹配的物理收口证明允许暂时性失败以完整历史恢复一次。状态未知时保留原发送保护。
- 结果省略 `id` 且 `name` 等于原工具轮的真实调用 ID 时，若没有同名函数，网关按该 ID 匹配。确认完整原工具轮后，向发送器提交的历史为对应调用和结果补真实 ID，并为结果恢复函数名。如果结果使用显式 ID 且客户端历史省略了对应调用的 ID，发送器历史也补入已核实的 ID。已归一化的前缀跨轮复用，公开入站诊断、网关归属和幂等回执比较使用客户端原始正文。
- 公共生成在原账号刷新锁内要求 AT 剩余有效期超过 550 秒。该值保留 AGY 1.5.9 的 310 秒断网启动实测余量和原生请求最长 240 秒预算。有效期不足时，由管理侧按原代次流程续期后再发布 AT-only 快照；在途工作继续使用自己的快照。
- 监督器将请求墙钟截止转换为单调截止，接收剩余时间范围 `(0,125]` 秒用于 120 秒准备与旧生成。双方声明支持新预算的生成可接纳 245 秒并钳制在 240 秒。安全出站使用本次进程收到的原单调截止。`Supervisor.acquire(value, until)`在选择及创建worker前复核截止，旧代关闭后重新检查；`Worker.start(until)`在Popen前再次复核。退役计入原请求耗时，过期返回 `request_deadline_exceeded`，停止新代创建及原生启动。
- 仅源错误code=401/status=UNAUTHENTICATED且没有候选及usage时参与有界恢复；须尚未交付、无工具结果历史、原作业实际收口、同账号ready新代且AT改变，最多一次。容量/控制失败、SSE首帧后、取消或过期均不重放。
- 控制响应头已返回 4xx/5xx 时保留状态码，错误正文解析失败时同样适用。普通 HTTP 和 SSE 首帧前用该状态结束请求，已开始的 SSE 通过尾帧 `error.code` 交付同一状态。尝试记录使用真实控制状态和 `native_control` 阶段，根记录保留实际客户端 HTTP 状态。已确证的上游配额 429 优先，已保留的成功结果继续按成功收尾。
- 原生控制关闭失败时，结果保留要求同一模型调用的完整 EOF、可交付候选、可核对用量及交付链完整。`STOP` 要求可见文本和完整常规计数。`MAX_TOKENS` 可保留文本、思考文本或内联媒体。省略 `candidatesTokenCount` 时，以合法的 `promptTokenCount`、`totalTokenCount` 和正数 `thoughtsTokenCount` 核对截断结果，原用量字段按源帧交付。源错误、待续工具、未确认归属、交付失败及缺少 EOF 继续进入原错误路径。
- 保留截断结果时完成事件使用 `finish_reason=max_tokens`，并记录已知 `observed_control_http_status` 和 `control_recovery=kept`。控制失败的工作进程仍按原路径排空和退役。原生控制成功且轨迹确认 `CASCADE_RUN_STATUS_IDLE` 时，结果可按既有工作进程轮换条件复用热进程。主调用的 `STOP` 或 `MAX_TOKENS` 配合 EOF 为独立旁路调用提供隔离依据。
- 账号内共享完整265700040字节封存映像，核对SHA和四封存，decode计数、分发大小、控制/内核/观察器/原生RSS/PSS/USS与cgroup独立展示。max_workers等于账号concurrency，范围1..64，跨模型和凭据代次共用物理上限。有限sender RAM为512+256×workers MiB，network 256MiB、CLI至少512MiB，总量受原预算约束；零沿明确无限策略。
- AGY 启动快照与同身份热进程分别回收。快照占用原缓存池名额，优先复用正在运行的热进程。控制器在线时，`restore.state` 的 `waiting` 表示尚无快照，`preparing` 表示后台准备中，`ready` 以当前代次的可恢复快照为准。准备失败以 `unavailable` 和 `template_failed` 表达，普通启动继续可用。
- 文件型模板观察器使用同一个 `/proc/PID/exe` 文件描述符核对实际文件身份和完整 SHA256。通过短暂的私有不可读映射取得内核报告的背板设备号和 inode，再按该组合核对目标进程映射。封存 memfd 按原设备号和 inode 核验。启动和恢复均要求唯一零偏移基址、非可写共享映射和四个固定指令指纹。模板启动固定 `GODEBUG=multipathtcp=0`，使当前 CRIU 4.2 能保存 AGY 的监听套接字。
- 保存时从已核验内核的实际父监督进程读取 `TMPDIR`，要求其为 `<agy.work_root>/<代次ID>`。内核的 `TMPDIR` 必须是该代次下的 `state/workers/<worker ID>`。两个 ID 均为 32 位小写十六进制，worker 工作目录须为实际目录且路径解析结果一致。将该目录传给 CRIU `--irmap-scan-path`，以定位绑定挂载里的 inotify 对象。快照保存后通过原生进程的 pidfd 回收由本容器 PID 1 接管的退出子进程，使原进程组 ID 可用于恢复。
- 模板和恢复失败在原 worker 清理前记录阶段和白名单原因，普通回退继承原单调截止。仅同一凭据代次的真实失败进入监督器状态，模板成功或凭据换代清除旧诊断。管理端在环境、代次、模块根和新鲜度核验后投影白名单诊断。原始异常路径、令牌及正文留在诊断字段之外。
- cgroup v2读取memory.max、memory.current、memory.peak和memory.swap.current；v1支持memory子目录或挂载根的memory.limit_in_bytes、memory.usage_in_bytes、memory.max_usage_in_bytes，memory.memsw.usage_in_bytes减RAM占用才是swap。v1限制大于等于2^60沿既有规则按无限处理；缺失/损坏为未知，监督器与冻结RAM不一致时拒绝，不能把未知当作无限。
- 正式模块根为/opt/v3/python，共享runtime_files位于/usr/local/bin。监督器和worker都冻结这两个搜索路径。AT HOME随worker私有发布，退役删除；采集复用账号开关与HTTP日志模式，长期有界脱敏快照位于flows/api/agy-prepared，原始执行材料沿临时worker目录和关闭清理。历史已退役采集保留七天；统一容量、内部旁路及读取合同由网关settings-database的AGY请求记录场景持有。普通输出采用有界匿名暂存，私有事件读取按帧及总字节控制背压。
- 旧工具和实际Root active纳入维护/升级排空。未知退出阻止新准备，显式对账停止本环境三角色后只清派生缓存和AT副本，保留权威凭据及身份。环境维护回执核对expected_generation；读取不唤醒，UI轮询保留草稿和焦点。存在AGY映射时目标control/account都须声明agy-runtime-protocol=1。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 缺失/禁用令牌 | 401，账号许可不进入业务 |
| 冲突key、未知输入、错工具调用方或 ID、找不到唯一归属 | 受控 400，拒绝发送或回填 |
| 活跃回填缺项、重复或未知 ID、剩余调用与无 ID 结果的工具名不能完整配对 | 400 `AGY_TOOL_RESULT_MISMATCH`，零模型提交 |
| `user` 内容含 `{}`，或 `model` 内容含其他形状的空 Part | `invalid_gemini_part`，错误路径保留原始索引 |
| 完整正文相同且响应仍在原截止内 | SSE 或 JSON 交付原响应，零额外回填和发送 |
| 已受理响应无法保留完整帧 | 重读返回 503 或 SSE 错误帧，首笔交付继续 |
| Gemini `thinkingConfig` 形状、档位、预算或字段无效 | 400 `INVALID_ARGUMENT`，零发送 |
| 字符串 `const` 不在同字段的 `enum` 内 | 400 `AGY_UNSUPPORTED_INPUT`，私有校验为 `invalid_tool_schema`，零发送 |
| 已有令牌可见目录，公开模型无对应映射 | 404 `NOT_FOUND`，提示读取 `GET /v1beta/models`，零发送 |
| pending/reconcile、旧凭据代次或无确证错误状态的原生失败 | 受控503，保留原请求归属及实际入口计数 |
| 原生终态失败，控制 HTTP 状态为 4xx/5xx | 保留原码。SSE 已发首帧时 HTTP 状态保持 200，尾帧 `error.code` 为原码 |
| 可信源 `MAX_TOKENS` 和模型 EOF 已交付，控制面返回 500 | 返回原截断内容与用量，Messages 终态为 `max_tokens`。控制 500 仍保留在诊断中，工作进程按失败路径退役 |
| 源只有文本或usage、缺少源终态 | 原生流不完整。已有控制错误码时保留原码，其他情况沿503路径 |
| v1/v2合法有限或明确无限预算 | 按冻结值准入；未知/不匹配拒绝 |
| 公共断连、原截止到期 | 精确取消原作业，活动保持到实际收口后释放 |
| 准入时、旧代收尾后或Popen前原截止已过 | `request_deadline_exceeded`，停止后续建代或启动副作用 |
| 监督器异常或旧镜像缺协议 | 待对账或拒绝升级，不自动重放未知请求 |
| 文件型映像的 `stat` 与目标映射设备号不同 | 依据已核验文件描述符的实际背板身份核对映射。无法确认背板、出现多个零偏移基址或可写共享映射时拒绝模板 |
| worker 目录越界、跨父监督代次、使用同名链接或无法核对 | 拒绝本次快照，沿原普通启动路径处理 |
| 当前代次模板保存或恢复失败 | 保留受控阶段，沿原截止普通启动。原生业务仍只提交一次 |

### 5. Scenarios and Examples

模型聚合示例。账号目录中的 `gemini-4-neon-low` 和 `gemini-4-neon-high` 对外列为 `models/gemini-4-neon`。客户端向 `/v1beta/models/gemini-4-neon:generateContent` 提交 `"thinkingConfig":{"thinkingLevel":"LOW"}`（放在 `generationConfig` 内），网关从该令牌允许的账号中查找 `gemini-4-neon-low`。如果目录只有两个带后缀的条目，`MEDIUM` 请求返回 404，客户端可选择目录实际支持的档位。

嵌套筛选数组示例。`{"type":"array","items":{"type":"array"}}` 的内层数组需经归一化补 `items`。直接补裸 `{}` 会被 AGY 序列化省略。使用 `{"anyOf":[{}]}` 可保留出站字段，`["count",">=",7]` 和 `["ready","==",true]` 的值类型维持原样。

控制错误示例。`SendUserCascadeMessage` 在源首帧前返回 HTTP 400 时，网关返回 `{"error":{"code":400,"status":"INVALID_ARGUMENT","message":"AGY 控制接口请求失败"}}`。原生流在成功控制响应后断开且缺少模型终态时，按未知错误路径返回 503。

正常：Gemini工具首轮返回真实functionCall并保留原许可；管理侧发布AT2后，调用方带原历史和functionResponse续轮，原AT1 worker完成真实MCP回填，下一模型由AT2 worker执行。边界：管理侧reconcile时先完成旧工具并保留原截止内回执，恢复ready后继续；资源无限必须有真实cgroup依据。

同轮调用 `Lookup(a)`、`Read(b)`、`Read(c)`、`Read(d)` 时，首条工具 SSE 的候选内容包含全部四个调用。省略 ID 时可按 `b`、`c`、`d`、`a` 回填。`Read` 组三项也要反序时，应在结果里携带真实调用 ID。混合回填时，较晚出现的显式 ID 优先领取对应调用。把真实 ID 放在结果的 `name` 时，可从已登记的工具轮恢复对应函数。重复使用同一 ID 或缺少一条结果时返回 400。

历史第 273 项为 `{"role":"model","parts":[{},{"functionCall":{"name":"Lookup"}}]}` 时，缺省 ID 为 `gemini-history-273-1`。工具续轮应保留已提交的历史前缀。客户端移除前缀中的 `{}` 会改变续轮身份，按历史不匹配拒绝。

重试边界：客户端使用同一份工具回填正文并发重试，重读原响应中的下一轮工具 ID。对象字段重排仍匹配同一响应。将同一正文转给新的模型生成会产生不同的工具轮归属，重试应在原截止内读取已登记响应。

错误用法：以HTTP 200、Go RPC返回或EOF认定部分文本成功；正确处理是同时验证源终态和控制终态。错误用法：用发送器替身的通过结果宣称原生OAuth业务已验证；正确处理是独立运行固定原版、本地TLS及真实MCP闭环。真实Google身份、目录接受性及跨实际到期仍由具备授权账号和独立预算的后续验收承接。

截止边界：旧代退役消耗剩余时间后，应使用原单调截止拒绝下一代。错误用法是收尾后重新给满预算或启动已过期进程；正确处理是继续沿用原 `until`，在建代和Popen前独立复核。

凭据边界：AT 剩余 299 秒时，固定原版断网启动报需要登录，剩余 310 秒时实测就绪。公共入口通过管理侧提前换代，首次模型提交使用新快照。

诊断示例。实际观察器未取得合格的目标映射时，可报告 `{"stage":"observer_start","reason":"execution_mapping_missing"}`。单凭 inode 或 `stat` 的设备号判断 OverlayFS 映射会产生错误准入判断。使用同一已核验文件描述符取得实际映射身份。

绑定挂载中的文件句柄无法直接打开时，将当前代次的 `state/workers/<worker ID>` 交给 CRIU 查找 inode。按平铺的 `<agy.work_root>/workers/<worker ID>` 校验会拒绝正式发送器创建的目录。恢复需复用原进程组 ID。保留已退出的原生子进程会占用原进程组 ID，退出时按保存前取得的 pidfd 回收。

### 6. Tests Required

- `test_agy_runtime`、`test_agy_supervisor`、`test_agy_environment`覆盖AT-only、参数、目录、帧/签名、终态、代次/工具、v1/v2有限/无限/未知预算、环境归属与维护。
- `test_agy_runtime` 覆盖两种工具声明、嵌套缺项、两种元组、字符串常量与 `enum` 冲突及重复归一化。固定原版回环断言实际出站的内层 `items`、元组长度上限、单值 `enum`，并核对工具调用保留数字及布尔值、结果完成回填。
- `test_agy_runtime` 验证已观测控制状态、非法 JSON 响应与成功结果保留。`verify_agy_gemini.py` 验证普通 HTTP、SSE 首帧前后与尝试记录的状态，覆盖 200 和旧内核字段缺失的503兜底。固定原版回环验证非法工具正则导致的控制500及零模型提交。
- `test_model_result_survives_only_post_stream_control_failure` 覆盖文本、纯思考、无候选计数、内联媒体及非法用量的 `MAX_TOKENS`，核对源帧、单次提交、诊断及退役。`test_isolated_calls_do_not_change_completed_tool_stream` 核对主轮 EOF 后的独立调用隔离。
- `test_agy_supervisor`覆盖已过期准入、旧代关闭耗尽截止以及真实Worker.start过期；分别断言worker创建为0、新代启动为0及Popen调用为0，均返回 `request_deadline_exceeded`。
- AGY 文件型模板应在普通业务权限的隔离 OverlayFS 上实际保存并恢复，核对首笔合成请求、原生 PID 和唯一提交。另验普通 memfd、错误文件身份、恢复失败及凭据换代。`test_agy_runtime`、`test_agy_supervisor` 和 `test_native_criu_settings` 核对阶段、原请求回退及旧代或非白名单原因的投影。
- `native/criu/test_agy.py` 核对正式监督代次布局、跨代目录和链接拒绝、文件句柄失败的脱敏摘要。在 Linux 6.1 的隔离 OCI 容器中使用账号工作目录与 CRIU 目录的绑定挂载，验证基线保存失败、修复后从同一 PID 恢复，以及保存失败、恢复失败、凭据换代各自只投递一次合成请求。授权现场验收时，用正式发送器的代次布局验证快照保存成功，实际模型请求须记录 `criu_restore` 并正常返回。
- Rust的runtime_transport单测覆盖精确AGY目标及CC路径隔离；agy_sender_test、gemini_account_test、gemini_contract_test、runtime_transport_test覆盖鉴权、绑定、权限、源聚合与取消。
- `verify_agy_gemini.py` 覆盖未知模型在流式和非流式入口返回 404、令牌范围外模型和未观测目录、已知模型暂不可用时的 503、临期凭据单次续期及有效期充足时继续复用。
- 同一断网探针核对公开 Gemini 目录跨账号去重、异平台名称保持、基础名和旧档位名实际发送的目录型号及原生 ID、显式档位隔离、工具续轮沿用型号和请求诊断保留原名。
- `verify_agy_native_loopback.py --image <明确测试镜像> [--loader-root <显式glibc目录>]`使用真实网关/SQLite/account-sender/监督器/原版和本地TLS/MCP；容器network=none、UID1001、根只读、零真实外部生成。一次性CA只挂验证容器系统信任根，正式配置无测试CA或跳过校验开关。断言参数实际出站、源usage、两代AT、并发1工具回填、同正文重读、64重复帧与SIGURG、截断/容量失败、断连取消、实际许可释放和共享映像。
- `verify_agy_native_loopback.py --parallel-tools` 模拟客户端读到首条工具 SSE 后断开，断言双同名调用以及 6、4、3 个调用连续三轮均完整交付，覆盖结果名称使用 ID、显式 ID 反序及部分结果保留 ID。用 `A、B、B、B` 调用与无 ID 的 `B、B、B、A` 回填核对真实出站参数和结果，并验证并发重读、对象键重排及重读后的下一轮。签名、源终态和用量沿原契约核对。缺项、冲突归属、跨令牌与原账号授权撤销返回 400，模型提交数保持不变。
- `test_agy_runtime` 核对分两段提交的混合历史、显式 ID 晚到、重复或未知 ID 拒绝，以及原 MCP 每个调用只回填一次。`test_agy_supervisor` 断言空闲回收同时保留同身份热进程和就绪模板。
- `test_agy_runtime` 用 293 条合成历史验证五个空占位、原始索引和工具配对。工具续轮核对显式调用 ID、旧式别名及前缀一致性。用户空 Part 与非法函数对象按实际位置拒绝。
- `verify_agy_native_loopback.py --tool-deadlines` 验证生成响应到期后重读返回 400，下一轮长工具仍按原监督器等待完成。`verify_agy_gemini.py` 核对发送前凭据对账、单次 MCP 回填与原失败终态。`gemini::replay` 单测核对原终态、有序多读者与容量回收。
- `verify_agy_runtime.py --native-image <明确镜像> [--crash]`保持零模型准备、两代、单次映像解码及正常/异常物理退出；`verify_agy_gemini.py`继续单独标记发送器替身证据；`verify_agy_environment_ui.py`覆盖1440/720/390px及实际控件边界、草稿、焦点和离页清理。制品资源须从当前受管理源码构建。

## Scenario: AGY账号系统文本同形体策略

### 1. Scope / Trigger

- 修改账号字段`agy_system_prompt_homoglyph_enabled`、Gemini准入/恢复、AGY私有提交、系统文本解码或策略记录时适用。开关按账号独立保存，缺省false；CC、工程任务和养号保持各自合同。

### 2. Signatures

- Rust `AgySubmission.system_prompt_policy: AgySystemPromptPolicy`：`schema_version=1`、`enabled:boolean`、`rule_version="new-api-homoglyph-v1"`。历史信封缺省关闭，关闭时省略扩展序列化；显式策略拒绝未知字段和版本。
- Python监督信封和`gemini_request`携带同名快照；公开Gemini正文无策略覆盖字段。`transform_system(system, policy)`返回提交文本及策略回执。
- `verify_agy_native_loopback.py --image <明确镜像> [--loader-root <显式glibc目录>] --homoglyph`验证真实固定原版系统段；`--capture-off`独立验证采集关闭。

### 3. Contracts

- 账号准入读取当前账号后冻结策略。同HTTP的有界OAuth恢复复用该快照；新HTTP工具续轮先收口原工具，再采用新请求的账号配置。策略排除在worker key之外，单独切换开关复用暖worker。
- 唯一字符表位于`agy_runtime/resources/system-prompt-homoglyph-v1.json`，固定26个ASCII到同形Unicode映射，构建纳入`admission.json.resource_hashes`。镜像及组件内容身份包含受管理规则资源，运行不依赖外部Worker目录。
- 只处理解码后的独立`system`，经Cortex自定义prompt section提交。多Part按既有换行合并；未命中码点原样，输出确定、幂等、Unicode码点数量保持一致。UTF-8字节数可改变。用户/模型历史、工具、参数、结果、ID和签名继续既有映射；原始`gemini_body`深拷贝保持转换前数据。
- `request_accepted.system_prompt_policy`含`schema_version/enabled/rule_version/rule_sha256/source/changed/replaced_codepoints/system_codepoints`。source固定`cortex_custom_system`，描述独立系统段处理来源；该事件产生于原生RPC提交前。`rule_sha256`标识规则资源字节，计数表示Unicode码点，均不换算token。开启但空文本或已转换文本可有`changed=false`。
- 网关按本HTTP和实际attempt身份核对回执的开关、版本、来源、摘要形状及计数一致性。启用请求收到匹配回执后才交付Gemini源帧；每次认证恢复重新等待回执。历史关闭请求兼容缺失回执。
- 临时执行材料中，`gemini-input.json`为转换前已解码Gemini视图，`input-mapping.json`记录策略，`rpc.ndjson`包含提交的系统段。长期采集使用独立有界脱敏快照，区分decoded_gemini_input及native_cascade_prompt_sections；原始HTTP由独立入站旁路保存。采集关闭沿匿名暂存与收口清理，公共日志仅记录策略元数据。
- 上游`usageMetadata`、缓存及思考扩展沿源帧交付。真实分词、缓存命中和计费效果使用授权账号及独立预算验收；本地TLS合成usage只验证来源保真。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 缺省关闭、显式关闭 | 目标文本原样处理；旧默认私有发送兼容 |
| 启用、空系统文本、已经转换 | 确定性处理；无替换时changed=false |
| 畸形策略、未知规则或资源摘要失配 | 在模型发送前拒绝；旧严格消费者拒绝未知启用扩展 |
| 启用请求缺失或错误回执 | 公共请求受控失败，拒绝交付源帧 |
| 超出固定原版上下文预算 | 保留原生失败边界，公开状态与 `error.code` 一致。零模型提交，后续预算内请求可用 |
| 关闭账号开关 | 后续HTTP恢复原文；同HTTP恢复和旧工具归属继续冻结合同 |

### 5. Scenarios and Examples

- 正常：开启账号将系统`ABC system 中文 {x: 3}`转换为`ΑΒС ѕуѕtеm 中文 {х: 3}`。同样内容作为用户文本仍按原历史映射；再次经过保持同一系统文本。
- 边界：请求开启后收到明确401，此时管理员关闭账号开关；该HTTP认证恢复仍开启，下个HTTP采用关闭配置。
- 错误用法：对完整Gemini JSON做字符替换，或以替换字符数宣称真实缓存收益。正确处理：只转换独立system，保留原始入站与结构字段，缓存及计费单独用供应商来源验收。

### 6. Tests Required

- `test_agy_system_prompt`核对26字符参考向量、幂等、Unicode/空文本/大文本、原始正文与历史/工具/签名保护、严格策略及公开覆盖拒绝。
- Rust `gemini_contract_test`、`agy_sender_test`核对缺省关闭省略、错误规则在启动前拒绝及回执计数/版本/来源；完整`cargo test --locked`继续覆盖CC回归。
- `verify_agy_gemini.py`单独标记真实HTTP/SQLite与合成发送器证据，覆盖两账号隔离、认证恢复策略冻结、下一HTTP读取新开关及缺失/错误回执。
- 本地TLS的`--homoglyph`覆盖普通/SSE、工具新HTTP、实际系统文本及用户历史对照、幂等、预算内大文本/超限零提交、暖PID、源usage/cache和策略账本；`--capture-off`核对转换生效且收口后无请求正文归档。容器保持断网、UID1001、零真实外部模型费用。
- 前端构建及`verify_agy_accounts_ui.py`覆盖原账号控件默认值、两账号差异载荷、草稿、授权回执归属及390px；迟到保存反馈继续受editorGeneration约束。

## Scenario: 节点迁移后的额度交接、上传续接与历史抓包

### 1. Scope / Trigger

- 本机与 SSH 节点双向或连续迁移、API 额度证据重读、上传中断续接及已结束工程的抓包查询适用。

### 2. Signatures

- `register_api_quota_cursor(connection, data, account_id, identity, environment_id, *, remote) -> None`；来源仍为 `api:<environment_id>:<identity>`。
- `quota_observation_cursors` 保持原结构；交接更新 `path/file_identity/byte_offset`。额度状态 JSON 的 `auth_verified_at` 保存完整人工核验的 UTC 秒时序。
- `MigrationFiles.stage(ImportStage)` 返回 `uploaded:bool,upload_state:empty|complete|incomplete` 及原 `protocol/node_key/operation_id/transfer_id/revision`。
- `NodeMigrations.renew_transfer(operation_id, previous, transfer_id) -> dict` 保存 `checkpoints.transfer={transfer_id,previous_transfer_ids}`；初始 `checkpoints.execution.transfer_id` 保持冻结。
- Node 私有操作 `project-history-capture` 使用 `ProjectHistoryCapture(NodeLocation)`，追加 `generation:int>=0,namespace:projects|warmup,work_id:32位hex,relative:str|null`。返回 `{protocol:1,node_key,history:{reference:<原请求>,capture:<原脱敏摘要或预览>}}`。

### 3. Contracts

- API 游标仅在同账号、同身份、同环境的系统固定本机证据和中央远程镜像路径间交接。同路径保留字节进度；切换路径清空文件身份并从零消费。额度窗口及已用恢复机会仍保存在原表，禁止以迁移清空。
- 远程读后与登记事务内核对分配／代次，本机登记也核对当前本机 ready 归属。消费以已打开文件的 fstat 身份读取，提交 CAS 比较来源、身份、路径、旧文件身份和字节位置；API 消费同时核对冻结分配／代次，拒绝往返迁移后的迟到写入。
- 历史认证错误只能按真实时序进入状态。完整人工核验解除门禁后保存 auth_verified_at，较旧或同次历史错误重读不能再次收口任务。较新的真实错误保持原保护。旧允许样本不得清除较新的恢复占用。
- 上传不完整状态由有限结构化回执表达，中央按专用异常进入新尝试登记。新尝试只允许在原 exporting 阶段且没有 target／cancellation 检查点时 CAS 认领；先持久后执行，旧部分文件和原包身份保留。完整上传未知回包重读原结果；已核验／发布的包变化继续报错，禁止作为普通中断换源。 最终激活和 committed 后的协调器重建同样读取持久化 transfer 检查点；缺少该检查点的旧操作才读取 execution 初始尝试。
- 已结束工作抓包与活动执行定位分开。中央从真实工作及当前环境确定查询；历史账本保留原节点。当前资料已完成迁移时，从当前节点读取原 `flows/group-sha256(namespace/work_id)[:20]`，旧节点离线不影响已迁移资料。
- 历史查询在 Node 只读锁内核对安装、账号／环境、分配和代次，复用原 capture_summary／capture_file_preview，保持空间隔离、文件白名单与脱敏；不准备运行时或启动角色。中央读后复核归属／代次，并核对完整查询回执。
- 新 Node 操作同时进入 Agent、轻量客户端与 SSH 操作／短查询白名单。中央与 Node 按同批控制组件发布；回滚前收口活动的新 transfer 检查点操作。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 固定 API 路径迁出／回迁 | 交接游标，保留原额度及许可 |
| 其他身份、未知路径、旧归属或迟到游标 | ValueError 或拒绝提交，保留新位置和原事实 |
| 人工核验后重读旧认证错误 | 门禁保持解除；新真实错误仍触发原保护 |
| 未核验的部分上传 | 回执 incomplete，原迁移登记新尝试 |
| 新尝试已经提交，激活回包未知或协调器重启 | 继续激活已发布的新尝试，保持原归属和准备结果 |
| 上传尝试 CAS 失配、取消或已发布 | 拒绝换源，沿原操作核对 |
| 历史抓包旧代次、错环境、目录链接、越界／私有文件 | 拒绝读取，公开入口沿原 404 合同 |
| 历史资料读取期间归属变化 | 拒绝迟到结果，不准备新环境 |

### 5. Scenarios and Examples

- 正常：本机 10% 游标迁出后消费远程 20%，回迁消费新 60%，再次迁出消费新 70%；逻辑来源保持。
- 基础：没有 transfer 检查点的旧迁移沿初始尝试；上传已经完整时重用原结果。旧额度 JSON 缺少 auth_verified_at 时沿既有观察时序处理。
- 中断：原尝试留下 partial 文件，新尝试先登记再上传；完整上传回包丢失并重建协调器后，继续同一迁移并复用已完整文件。 激活请求必须引用新尝试；committed 后激活回包丢失时，重建协调器仍引用相同新尝试，目标准备保持一次。
- 错误用法：直接覆盖 API 游标为任意路径、删除部分上传、为历史本机工作虚构远程操作。正确处理：核对固定来源后交接、保留旧证据并登记新尝试、使用独立的历史只读定位。

### 6. Tests Required

- `test_cluster_quota`：本机↔远程连续交接、两个真实 Node 数据根、旧位置迟到消费和未知路径保护、完整人工核验后换代重读及新认证错误。
- `test_cluster_migration_files/test_cluster_migration_runner`：真实部分文件、上传完成回包未知、协调器重建、CAS／取消后拒绝、已核验包和链接保护。 节点激活替身核对实际已准备尝试，覆盖新尝试的最终激活及 `test_renewed_transfer_activation_resumes_after_committed_response_loss` 的提交后重启续接。
- `test_cluster_project_capture/test_cluster_projects_terminal`：双空间实际文件、真实迁移归档、旧节点离线、原账本保持、零运行时准备、scope 和路径拒绝。
- `test_cluster_agent.NodeAgentTests.test_history_capture_through_real_ssh_light_client_and_actor`：真实隔离 SSH→轻量客户端→UDS Actor→原文件；Docker exec 使用明确命令替身，保持零真实账号请求。

## Scenario: 独立接单与账号整体停用

### 1. Scope / Trigger

修改网关账号工作准入、编排整体启停、工程/养号运行控制或计划恢复时适用。API 接单偏好、健康资格、业务计划与整体启用各自保存。

### 2. Signatures

- 网关 `GET/PUT /admin/accounts/:id/work-control`；PUT 接收 `api_accepting?:bool`、`work_enabled?:bool`、`expected_revision?:i64`，拒绝附加字段和空增量。
- 编排 `GET/PUT /api/accounts/{aid}/work-control`、`/api/gateway-accounts/{gateway_id}/work-control`；PUT 接收 `enabled:StrictBool`，拒绝附加字段。
- 网关增量表 `account_work_controls(account_id BIGINT PRIMARY KEY, api_accepting INTEGER DEFAULT 1, work_enabled INTEGER DEFAULT 1, revision BIGINT DEFAULT 0)`，所有列非空；迁移 `gateway.account-work.7`。
- `AccountWorkCoordinator.change(account_id, enabled)`、`snapshot(account_id)`、`recover()`；操作保存在原 `app_settings` 的 `account_work_control:<aid>`，字段 `id/enabled/phase`。
- 工程/养号运行控制 `ProjectsControlIn.disable_schedule:StrictBool=True`；新界面只暂停/停止当前运行时明确提交 false。

### 3. Contracts

- 网关快照返回 `api_accepting/work_enabled/revision/admitted_requests/phase/coordinated`；phase 为 enabled/draining/disabled。未保存记录默认两个开关开启、revision=0。原 status 继续表示健康资格。
- 开关保存和 `admit` 共用同步边界；请求进入账号队列前登记，许可随响应体终结或取消释放。关闭只拒绝此后登记的新请求，已有排队、JSON 和 SSE 沿原预算与活动许可正常结束。换到其它账号时重新核对目标准入。
- 整体操作先在身份锁内同事务保存 pending 意图并写 `accounts.enabled=0`，再在身份锁外更新网关并调用原停止能力，避免项目锁与身份锁反转。两端成功后保存 enabled/disabled；部分失败保存 reconcile 并保持新工作关闭。
- 编排快照返回 `enabled/phase/active_work/api/operation_id/message`；phase 追加 reconcile。占用读取失败时 active_work=null，公开待核对。实际占用或已接纳 API 尚在时显示 draining。
- 重复启用先核对两端目标已达成，直接只读返回，保持运行中的准入。停止重试复用原 operation_id，在单运行可重入锁内按原 quota_attempt 与 token 清理，保留 stop_requested_at；同线程清理回调的重复停止沿原 stopping 状态幂等返回，跨线程继续串行。隔离环境对账在原 environment_lock 内核对 environment_id/generation；旧代次禁止清理新环境。
- 计划到期与启动之间并发停用仍保留原触发时间；重启时为原中断计划保留下一次检查，已有未知动作、失败、额度冷却和业务阻塞保持原约束。整体恢复使用保存的独立开关与计划。
- `V3_RUNTIME_URL` 非空时，网关整体工作写入要求原内部服务身份；浏览器经原管理会话与精确 runtime bridge 白名单进入编排协调。独立 API 接单使用热更新入口。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 编排 enabled 错类型、附加字段或缺 PUT 正文 | 422，原意图保持 |
| 网关空增量或旧 expected_revision | 400，原开关保持 |
| 已关联部署直接从普通管理入口写整体开关 | 原内部身份核验拒绝 |
| 新请求到达已关闭账号 | 503 或沿原调度策略选择其它合格账号 |
| 部分停止失败、环境代次变化 | reconcile，保留原操作并支持重试；冲突 409，连接故障 503 |
| API 活动期间整体关闭 | 既有请求正常完成，观察实际占用后收口 |

### 5. Scenarios and Examples

- 正常：提交 `{"api_accepting":false}`，已有 SSE 完整结束；养号和工程按各自计划继续。
- 边界：整体停用跨过计划时间，恢复启用后原计划重新检查；重复启用期间运行准入保持开启。
- 错误用法：把 stopping 当成已清理成功。正确处理：沿同一操作和执行代次实际重试，隔离现场完成对账后才能宣布收口。
- 错误用法：用账号 status 承载接单偏好。正确处理：独立保存 api_accepting，原认证、额度、节点和维护资格继续生效。

### 6. Tests Required

- 网关真实 HTTP SSE 覆盖 legacy/v3 下关闭接单与整体关闭、原流完整、新请求拒绝、排队许可和取消回收；热更新验证健康状态、凭据和活动租约保持。
- `test_account_work_control` 覆盖部分成功、重启、同操作重试、重复启用和未知观察；`test_account_work_recovery` 覆盖失败停止、并发单执行、旧 quota_attempt、隔离环境及环境换代。
- `test_project_plans.ProjectPlanTests.test_repeated_internal_stop_does_not_clean_same_execution_twice`覆盖原清理回调重入；只清理一次，原运行最终成为stopped。
- `test_projects_schedule` 覆盖整体停用跨过触发时间、预查后并发停用、重启前后恢复、独立暂停保留计划及原业务阻塞。
- 真实浏览器验证独立开关、收尾进度与恢复偏好；迁移注册和数据库定义检查覆盖增量表。


## Scenario: 节点迁移后的额度交接、上传续接与历史抓包

### 1. Scope / Trigger

- 本机与 SSH 节点双向或连续迁移、API 额度证据重读、上传中断续接及已结束工程的抓包查询适用。

### 2. Signatures

- `register_api_quota_cursor(connection, data, account_id, identity, environment_id, *, remote) -> None`；来源仍为 `api:<environment_id>:<identity>`。
- `quota_observation_cursors` 保持原结构；交接更新 `path/file_identity/byte_offset`。额度状态 JSON 的 `auth_verified_at` 保存完整人工核验的 UTC 秒时序。
- `MigrationFiles.stage(ImportStage)` 返回 `uploaded:bool,upload_state:empty|complete|incomplete` 及原 `protocol/node_key/operation_id/transfer_id/revision`。
- `NodeMigrations.renew_transfer(operation_id, previous, transfer_id) -> dict` 保存 `checkpoints.transfer={transfer_id,previous_transfer_ids}`；初始 `checkpoints.execution.transfer_id` 保持冻结。
- Node 私有操作 `project-history-capture` 使用 `ProjectHistoryCapture(NodeLocation)`，追加 `generation:int>=0,namespace:projects|warmup,work_id:32位hex,relative:str|null`。返回 `{protocol:1,node_key,history:{reference:<原请求>,capture:<原脱敏摘要或预览>}}`。

### 3. Contracts

- API 游标仅在同账号、同身份、同环境的系统固定本机证据和中央远程镜像路径间交接。同路径保留字节进度；切换路径清空文件身份并从零消费。额度窗口及已用恢复机会仍保存在原表，禁止以迁移清空。
- 远程读后与登记事务内核对分配／代次，本机登记也核对当前本机 ready 归属。消费以已打开文件的 fstat 身份读取，提交 CAS 比较来源、身份、路径、旧文件身份和字节位置；API 消费同时核对冻结分配／代次，拒绝往返迁移后的迟到写入。
- 历史认证错误只能按真实时序进入状态。完整人工核验解除门禁后保存 auth_verified_at，较旧或同次历史错误重读不能再次收口任务。较新的真实错误保持原保护。旧允许样本不得清除较新的恢复占用。
- 上传不完整状态由有限结构化回执表达，中央按专用异常进入新尝试登记。新尝试只允许在原 exporting 阶段且没有 target／cancellation 检查点时 CAS 认领；先持久后执行，旧部分文件和原包身份保留。完整上传未知回包重读原结果；已核验／发布的包变化继续报错，禁止作为普通中断换源。 最终激活和 committed 后的协调器重建同样读取持久化 transfer 检查点；缺少该检查点的旧操作才读取 execution 初始尝试。
- 已结束工作抓包与活动执行定位分开。中央从真实工作及当前环境确定查询；历史账本保留原节点。当前资料已完成迁移时，从当前节点读取原 `flows/group-sha256(namespace/work_id)[:20]`，旧节点离线不影响已迁移资料。
- 历史查询在 Node 只读锁内核对安装、账号／环境、分配和代次，复用原 capture_summary／capture_file_preview，保持空间隔离、文件白名单与脱敏；不准备运行时或启动角色。中央读后复核归属／代次，并核对完整查询回执。
- 新 Node 操作同时进入 Agent、轻量客户端与 SSH 操作／短查询白名单。中央与 Node 按同批控制组件发布；回滚前收口活动的新 transfer 检查点操作。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 固定 API 路径迁出／回迁 | 交接游标，保留原额度及许可 |
| 其他身份、未知路径、旧归属或迟到游标 | ValueError 或拒绝提交，保留新位置和原事实 |
| 人工核验后重读旧认证错误 | 门禁保持解除；新真实错误仍触发原保护 |
| 未核验的部分上传 | 回执 incomplete，原迁移登记新尝试 |
| 新尝试已经提交，激活回包未知或协调器重启 | 继续激活已发布的新尝试，保持原归属和准备结果 |
| 上传尝试 CAS 失配、取消或已发布 | 拒绝换源，沿原操作核对 |
| 历史抓包旧代次、错环境、目录链接、越界／私有文件 | 拒绝读取，公开入口沿原 404 合同 |
| 历史资料读取期间归属变化 | 拒绝迟到结果，不准备新环境 |

### 5. Scenarios and Examples

- 正常：本机 10% 游标迁出后消费远程 20%，回迁消费新 60%，再次迁出消费新 70%；逻辑来源保持。
- 基础：没有 transfer 检查点的旧迁移沿初始尝试；上传已经完整时重用原结果。旧额度 JSON 缺少 auth_verified_at 时沿既有观察时序处理。
- 中断：原尝试留下 partial 文件，新尝试先登记再上传；完整上传回包丢失并重建协调器后，继续同一迁移并复用已完整文件。 激活请求必须引用新尝试；committed 后激活回包丢失时，重建协调器仍引用相同新尝试，目标准备保持一次。
- 错误用法：直接覆盖 API 游标为任意路径、删除部分上传、为历史本机工作虚构远程操作。正确处理：核对固定来源后交接、保留旧证据并登记新尝试、使用独立的历史只读定位。

### 6. Tests Required

- `test_cluster_quota`：本机↔远程连续交接、两个真实 Node 数据根、旧位置迟到消费和未知路径保护、完整人工核验后换代重读及新认证错误。
- `test_cluster_migration_files/test_cluster_migration_runner`：真实部分文件、上传完成回包未知、协调器重建、CAS／取消后拒绝、已核验包和链接保护。 节点激活替身核对实际已准备尝试，覆盖新尝试的最终激活及 `test_renewed_transfer_activation_resumes_after_committed_response_loss` 的提交后重启续接。
- `test_cluster_project_capture/test_cluster_projects_terminal`：双空间实际文件、真实迁移归档、旧节点离线、原账本保持、零运行时准备、scope 和路径拒绝。
- `test_cluster_agent.NodeAgentTests.test_history_capture_through_real_ssh_light_client_and_actor`：真实隔离 SSH→轻量客户端→UDS Actor→原文件；Docker exec 使用明确命令替身，保持零真实账号请求。

## Scenario: V2 受管账号从普通 Messages 冷导入已闭合工具历史

### 1. Scope / Trigger

- 修改受管账号的外部历史导入、工具续轮、私有 sender 协议或 CLI 出站诊断时适用。

### 2. Signatures

- 公开入口仍为 `POST /v1/messages`。受管 sender 在原绑定 Unix socket 的 `prepare` 提出整数 `native_cold_history_protocol: 1`。事件源选用该路径时在同一预留回执确认该字段。
- 冷导入回执启用 `capture_cli_submission_protocol: 1`。本次调试证据的 `tui_provider_request.representation` 为 `request_from_interactive_cli`。

### 3. Contracts

- 普通 Messages 的已闭合文本与工具历史、当前文本问题和支持的客户端工具声明共用当前账号作用域。工作区归属核验后，事件源原子发布固定 2.1.293 格式的私有会话记录。CLI 恢复该历史并提交当前问题。顶层追加指令保持输入顺序。
- 冷导入使用发送器已登记的 `native_session_id`。新导入记录的 `message` 只包含 `role` 和 `content`，原工具调用 ID 和结果仍保留在内容块中。首条 JSONL 记录的外层 `flower2apiImportBoundary` 保存规范化历史和本轮生效设置的摘要。同一工作区的完整主链、消息及摘要匹配时，保留文件和 UUID。旧格式沿原模型及主链匹配条件读回，保留原文件字节。
- 已有合法主链超出本轮确认边界，或历史、已记录的生效设置发生分歧时，按登记会话、确认历史及生效设置查找同一私有工作区的匹配分支。发布使用目录锁与原子不覆盖操作。恢复与导入回调返回的 UUID 均经 `_resume_path` 核对目标文件身份、权限、cwd 和原生 UUID。回调为纯新轮选中的 UUID 须尚无历史。
- 分叉已结束且本轮问题与档案里的原问题一致时，客户可重发同一确认历史触发新投递。启动器核对原分叉及同 UUID 的私有临时 JSONL。临时文件只载入已确认前缀，由本次 CLI 追加并在进程回收后清除。原分叉档案保留原字节。输入问题改变或已有分叉仍未完成时沿后续修订查找。
- 普通 Messages 在原公开会话中提交分叉的确认历史。启动器的显式恢复与自动恢复均可根据同一导入计划定位该分叉。单独按已登记 UUID 恢复时，选择原绑定的历史。普通历史分叉共享原会话的绑定文件与私有配置目录。
- 普通单文本首轮和已闭合的纯文本历史也使用该原生入口。无外部历史时由 CLI 自行创建会话记录。公开会话已有主链但本轮提交空前缀时，启动新的独立原生会话。普通顶层 `system` 省略、空串和空数组均保留原生默认工作正文。多个文本块按原顺序作为本轮追加指令。
- 当前用户消息的多个纯文本块在 `session.append` 阶段按原顺序替换本会话的提交标记，CLI 按原生方式保存并组装。派发前核对本轮标记和实际文本块。原工具回执冻结文本块边界。原进程丢失后，已提交的块随核对过的历史载入，继续提示单独提交。
- 普通 Messages 的已确认历史文本可保留 `ephemeral` 缓存标记、本来缺省的 TTL 与 `1h`、`5m`。原生路径可将当前轮纯文本或边界内的内嵌图文与至多四个按先长后短排序的历史断点组合。该会话关闭 CLI 自动断点，派发前逐条对照角色、消息和块位置及标记内容。当前图像的附件来源块也保持无标记。标记不符返回 422，零投递。根轮历史标记随工具组冻结，从续轮或丢进程恢复改写标记均拒绝。
- 平台强制 `5m` 或 `1h` 且缓存布局关闭时，带历史断点的原生计划先按账号政策生成导入历史。直接断点应用平台 TTL。已闭合工具结果内的标记保留客户端表示，单独存在或与直接断点混合时均按有效出站 TTL 检查前缀先长后短。工具回执冻结根轮的有效 TTL 和客户端原值。平台 TTL 更新对新轮生效；在线续轮使用原计划，丢进程后从同一持久边界核对根轮有效 TTL。客户端改写直接或嵌套历史断点仍返回 422。无显式断点及启用 `sub2api` 布局的强制形状沿各自已有合同。[缓存 TTL 顺序](https://platform.claude.com/docs/en/build-with-claude/prompt-caching#mixing-different-ttls)
- 已确认的用户历史与本轮用户消息可保留内嵌 Base64 PNG、JPEG、GIF 和 WebP。历史恢复按原角色和内容块顺序交给 CLI，用户提醒可附在同一条消息。URL 图像沿既有输入合同。
- 本轮图片暂存于当前私有 HOME 的 `tmp` 子目录。隔离启动器仅保留属于该 HOME 的 `O_PATH` 目录描述符。CLI 逐张使用原生 PTY 粘贴，Mod 依据公开图文顺序使用实际粘贴的图片块。主请求核对原图字节、图文边界和生成的进程内来源别名。该别名只标识进程内文件描述符和服务端生成的附件名。单张图片的原生粘贴边界包含长边 2000 像素及 Base64 解码后 512000 字节的上限值。固定 CLI 会重采样或重编码超界图像，公开入口在启动前按下表判断超界输入。
- 本轮图文的业务合同覆盖同一 `user` 行内的块顺序、重复块、文字内容与图片 MIME/Base64。固定 2.1.293 的 PTY 首轮和同进程续轮在原始数组前带有 CLI 上下文，尾部每张图片各有一条按粘贴顺序排列的来源文本。末个实际提交块为文字时，CLI 在来源文本前向该文字块追加一个 LF。末块为图片时，业务块本身逐块相等。两种 PTY 形状的完整 `content` 都含额外块。CLI 自动缓存标记可出现在首轮最后一条来源文本。
- 丢进程恢复用原始业务块重建该图文历史行。公开回归的恢复模型请求中，这一行的原始 `content` 与客户端业务数组逐块相等。续轮的工具结果及继续提示各有自己的消息边界。
- 固定版的 `--print --input-format stream-json` 对照也保留四种格式及重复块，并生成来源文本和相同的末文字换行。普通交互 PTY 拒绝该参数组合。X11 剪贴板 `Ctrl+V` 对照中，四种格式单张实收的 MIME/Base64 均相等，CLI 每张也生成一条来源文本。直接经当前 `session.append` 提交新图块的隔离探针未达到图片提交边界。当前入口继续使用实际粘贴。[CLI 输入参数](https://code.claude.com/docs/en/cli-reference) · [交互剪贴板入口](https://code.claude.com/docs/en/interactive-mode)
- 已闭合的旧工具结果可保留非空有序 `text` 块数组和原工具 ID。其余扩展字段沿现有输入合同，先前完成的工具保持已完成。
- 已闭合工具结果内的文本块也可带历史 `ephemeral` 标记。它与历史直接文本共用四个断点预算和 TTL 顺序。发送前按原调用 ID、角色及工具结果内的块位置核对；只处理已确认前缀，活跃工具的新结果继续使用原回执合同。
- 旧工具调用和回执可以拆在相邻同角色历史里。原生导入按角色合并相邻行，保持块内容和先后顺序，整组调用必须在下一助理轮前闭合。原公开历史仍作为回执归属的比较依据。
- V2 管理端可选择 `append`、`replace`、`user_reminder`。已核验发送器通过私有预留传递非默认动作。替换以启动文件承载系统正文，省略保留默认正文，显式空串或空数组仅保留身份和计费块。提醒保留默认系统正文，附到首条不含工具回执的用户消息。纯新轮的提醒随原问题提交。完整 CC 原生请求沿原输入合同。已登记等待工具的进程沿用其启动动作。
- 普通原生输入的 `output_config.effort` 支持 `low`、`medium`、`high`、`max`，由 2.1.293 的 `--effort` 组装。模型出站前核对实际字段。等待和冷恢复沿用根轮冻结的强度。
- 普通 Messages 的 `output_config.format.type=json_schema` 仍是退役兼容缺口。固定 2.1.293 的 `--json-schema` 交互 PTY 探针在禁用和启用默认工具时均未生成 `output_config.format`。`--print` 正对照经 `StructuredOutput` 工具发送 schema，模型正文仍无该字段。[Claude Code CLI 参数](https://code.claude.com/docs/en/cli-reference) · [Messages JSON 输出](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- 固定 2.1.293 对 `claude-sonnet-4-6` 和 `claude-opus-5-5` 原生支持显式 `adaptive/updates` 和 `adaptive/summarized`。后者在原生计划确定后以 CLI `--settings` 启用 `showThinkingSummaries`，恢复沿同一根轮配置。投递前核对 CLI 真实生成的 `thinking` 对象。回执改动 `display`、省略显式值、或改成平台会自动重写的 `disabled` 时返回 `422/unsupported_parameter`。新请求的缺省 `display`、显式 `omitted` 和平台自动重写沿既有合同。用 `--adaptive-thinking-model` 指定模型，搭配 `--adaptive-thinking-display summarized` 验证摘要，省略显示选项验证 `updates` 及其功能头。两种模式均可搭配 `--recover-pending-tool`。
- 工具声明由会话私有 HTTP MCP 返回。有工具的轮次等待 `tools/list` 应答写出后才提交 PTY 提示。公开调用块恢复原名，ID 与参数增量仍对应原模型事件。工具结果通过原进程的回执账本交付，接收方、历史、原调用和本轮生效设置均需匹配。
- 声明客户端工具时接受显式 `tool_choice.type=auto`，`disable_parallel_tool_use` 可省略或显式为 false。固定 CLI 2.1.293 的这两种输入保留工具声明，实际模型正文均省略 `tool_choice`。自动选择允许模型直接返回文本，公开 SSE 的 `stop_reason` 为 `end_turn`。等待工具时冻结客户端原字段形状。在线及丢进程后的回执把省略和 false 互换，或改为 `none`、禁止并行、指定工具，均返回 422 且模型零新增收件。原样回执仍可完成。
- 普通 Messages 的 `tool_choice={"type":"none"}` 在 `tools` 省略或为空数组时使用交互 CLI。派发前要求 CLI 正文的 `tools` 为空或省略，`tool_choice` 保持显式 `none` 或省略并应用无工具默认值。存在工具声明时仍按既有策略处理并保留完整列表。[Messages 工具选择](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
- `tool_choice.type=any` 要求模型调用已声明的任一工具，`type=tool` 要求指定名称。固定 2.1.293 交互对照用 `--tools ""` 关闭内置工具并声明两个 MCP 工具，`--allowedTools` 只预许可指定工具时仍保留两个声明，`--disallowedTools` 排除另一工具后仅发送一个声明。三种对照的 CLI 正文均省略 `tool_choice`，均可直接以文本收口。现有受支持的权限及声明入口缺少 Messages 的强制字段，原生支持仍为退役缺口。[CLI 工具选项](https://code.claude.com/docs/en/cli-reference) · [Messages 工具选择](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools)
- 普通追加策略的在途强制工具轮由已登记的账号发送器收口，合法回执显式切为 `auto` 时仍沿原归属。完成该轮并交付完整答复后，同一公开会话可带完整已确认历史提交独立的 `auto` 新问题。新轮按原生输入合同判断。验收的 `any` 和命名两例各由交互 CLI 生成并投递一次，模型保留两组已完成工具的调用与结果。
- 普通工具名中的连字符与下划线分别保留。固定 CLI 2.1.293 仅增加会话 MCP 前缀，嵌套 Schema 与参数沿原描述交付。重启后工具回执仍核对原名、ID 和完整参数。
- 原生等待进程丢失时，私有回执按同一修订核对根轮策略及正文摘要。新原生会话导入客户端已核对的工具结果，保留原 JSONL。由受管 PTY 使用 CLI 的继续提示启动模型步骤，原问题和已完成工具保持在历史中。旧工具回执仍以原表布局读取。
- 旧账号发送路径可能先登记工具回执，原 CLI 在写入原生主轮之前退出。已核对的旧回执使用自动恢复时，若原绑定档案可解析、归属有效且只有非主轮记录，启动器以新的 CLI 会话 UUID 继续同一已核验工作区，原绑定与档案字节保留。发送器继续使用账本核对过的请求历史。原生导入、显式恢复及普通新轮仍要求原有主链校验。历史内容损坏、文件权限异常及主链归属不符仍拒绝。
- 活跃工具组的签名属于发送器实收的助手块。回传时核对原签名和工具参数。受支持的原生根轮按工具 ID 登记实际 `message_start.message.model`，与当前回执修订一起保存，覆盖缺省 `thinking`、显式 `adaptive/updates` 和 `adaptive/summarized`。冷恢复仅将该事实写入对应的已验签助手行，普通外部历史仍使用 `role/content`。固定 CLI 2.1.293 依此保留原签名，模型提交前核对签名块和工具 ID 的原序。带签名回执的来源数据缺失或旧存量未登记助手模型时，冷恢复在准备阶段返回 `422/unsupported_parameter`，原会话文件保留，回执零尝试和零新增投递。无签名旧回执沿原布局恢复。
- CLI 回环模型请求沿原账号 sender 授权路径送到固定供应商。该次请求交付 CLI 实际生成的 JSON 实体。调试快照的正文摘要取自这一实体，`wire_final.status` 为 `unavailable`。
- 账户、会话、模型、替代的调用方参数或连接归属变更均沿原预留和回执门槛处理。冷导入只协商当前支持的普通输入形状。其他形状继续沿该发行既有入口合同。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 主体或公开会话与等待工具组不匹配 | 400，零新增模型提交 |
| 原工具参数被改写 | 422。准备阶段先归还回执，合法新请求可立即认领 |
| 同组合法回执已交付后再次提交 | 原回执规则拒绝重放 |
| 同绑定并发导入相同历史 | 使用同一原生 UUID，已有文件保持原字节 |
| 导入回调选中已有历史的 UUID 用于纯新轮 | 启动器拒绝使用该 UUID 创建会话 |
| 同一分叉边界 A→B→B，B 尚未推进 | 两次 B 使用同一分支 UUID。A 和首次 B 的文件保持原字节 |
| 分叉公开回复已成功交付，重启后再次提交相同历史及问题 | 新尝试使用同一分叉 UUID。模型只收到客户端确认的历史和一次当前问题，档案数量和已有字节保持 |
| 文件归属错误或包含其他工作区的主链 | 拒绝恢复，保留原文件 |
| 当前轮合法内嵌图像达到长边 2000 像素或解码后 512000 字节，且其余输入满足原生合同 | 三种账号动作均经交互 CLI 投递一次 |
| 当前轮内嵌图像长边超过 2000 像素或解码后超过 512000 字节，顶层 `system` 可省略或为已支持的文本 | `append` 沿旧账号发送路径保留原 `messages`，投递一次。`replace` 和 `user_reminder` 返回 `422/unsupported_parameter`，模型零收件 |
| 普通 API 携带 `output_config.format.type=json_schema`，单独使用或同带 `effort=medium` | `append` 经旧账号发送器透传，实收一次。`replace` 和 `user_reminder` 返回 `422/unsupported_parameter`，零尝试、零投递 |
| Sonnet 4.6 普通 API 声明两个客户端工具、关闭思考并要求 `tool_choice.type=any` 或指定 `type=tool` | `append` 经旧账号发送器保留工具表与精确选择。`replace` 和 `user_reminder` 返回 `422/unsupported_parameter`，零尝试、零投递 |
| 普通 API 声明工具且指定 `tool_choice.type=none` | `append` 经旧账号发送器保留选择和声明。`replace` 和 `user_reminder` 返回 `422/unsupported_parameter`，零尝试、零投递 |
| 仅开启该路径的调试采集 | 保存 CLI 实际实体证据，最终 TLS 写出未采集 |

### 5. Scenarios and Examples

- 首次带两组旧问答和已完成的工具对发起请求。HTTPS 模型收到原历史及一次当前问题，随后收到新工具的单次合法结果。
- 将 CLI 回环摘要标作最终 TLS 写出会混淆采集点。使用 `request_from_interactive_cli` 记录 CLI 实际交付，并单独对照 HTTPS 接收端正文摘要。

### 6. Tests Required

- `test_tui_cold_history.py` 核对闭合边界、私有 JSONL 父链、最小历史消息、旧格式字节保留、同绑定并发与 MCP 声明范围。`test_tui_workspace_launch.py` 核对首次导入、重复导入和后续预留的正式恢复入口使用同一文件。回调返回的分支须通过目录、会话和权限校验。
- `verify_tui_cold_history.py` 使用公开入口、生产事件源、真实 2.1.293 CLI 和账号代理，对照 HTTPS 实收、公开流式调用、JSON 续轮及拒绝路径。
- `verify_tui_cold_history.py --restart-history` 在原工具续轮收口后核对已导入消息的 `role` 和 `content`。以账号权限预先落盘改写后的历史，再重启发送器并从公开入口提交分叉确认历史，未推进时须复用同一 UUID。完整答复写入后再次重启并重发相同输入，检查独立响应、一次额外模型投递、确认历史、旧档案字节及工具归属。已推进的内容可由后续分支承接，报告记录实际 UUID 和持久档案数量。
- `verify_tui_cold_history.py --text-input` 从公开入口核对纯新轮、同公开会话另起新轮、纯文本历史以及缺省、空串、空数组和多段系统指令实收。
- `9aed7a1f` 的 `--cache-markers` 记录退役前基线。当前同名用例覆盖三种账号动作、嵌套历史断点和强制 `5m`、`1h` 的原生出站，以及本轮文本和工具声明的旧路径对照。请求根、顶层系统块上的标记，以及使用替换或用户提醒时的已测本轮文本标记返回 `422 / unsupported_parameter`，模型零收件。夹具按预留比对已认领正文及隔离 HTTPS 实收摘要，最终 TLS 写出保持未采集。`--history-cache-markers` 核对一次工具往返的两次模型请求，兼容 `--recover-pending-tool` 验证冷恢复和改写历史断点拒绝。同用 `--history-cache-ttl 5m`，等待中切换到 `off`，核对原回执继续使用 `5m`，同一公开会话的新轮应用 `off`。
- `--cache-marker-capabilities baseline` 核对 `405147a9` 的当前轮双文本块与双工具声明。追加动作下，首位及末位的显式标记都沿旧账号代发保留原位置及缺省 TTL、`5m`、`1h` 三种表示。替换、用户提醒的四个对照返回 422，模型零收件。无标记对照沿 CLI 原生路径。
- `--history-cache-markers --history-cache-ttl 5m|1h --history-cache-scope nested|mixed` 对照强制 TTL 下仅有嵌套标记及混合标记。普通续轮和 `--recover-pending-tool` 核对原工具 ID、第二个重复文本块的标记、直接断点的有效值及回执冻结。改写原值返回 422。同会话下一新轮核对平台关闭覆盖后的客户端原值。
- `--cache-marker-capabilities native-default` 和 `native-no-auto` 仅用于隔离能力实验。当前块通过 `prompt.submit` 与 `session.append` 交给固定 2.1.293；MCP `tools/list` 在声明及 `_meta` 中提供相同标记。默认配置的模型实收与无标记对照相同，当前用户末块自动标为 `1h`，工具声明无标记。关闭自动缓存后，两种位置均无标记。实收保留用户角色、两块的相邻顺序及工具名称映射、描述和 schema。末块 `1h` 样本同时检查无标记和关闭自动缓存对照，以免把默认行为认作客户端标记保真。此能力缺口影响调用方显式断点的前缀和时长，保留旧账号路径直至原生合同通过。最终 TLS 写出保持未采集。
- `--message-system-roles` 对照当前 V2、`bdaca089` 旧 V2 与固定 V1 制品。白名单模型的普通 API 可保留原位 `system` 文本及缓存块、`clear_at`、携带 effort 的空系统消息和根系统块。当前和旧 V2 都经账号代发，V1 经 `native293`。只有根 `system` 的当前 V2 对照使用交互 CLI。白名单外模型返回 `400/system_role_model_not_allowed`，给 user 或 assistant 加专属字段返回 `422/unsupported_parameter`，无效 `clear_at` 返回 `400/invalid_parameter`。显式测试的三个功能头均到达模型。客户端省略它们时，本次固定 V1 公开入口实收带 `mid-conversation-system-clear-at-2026-08-21`，两版 V2 实收缺少该项。
- `--ordinary-message-system-contract` 固定普通 API 上述状态、错误码、模型投递和尝试次数。省略缓存、`clear_at` 与 effort 的纯文本对照覆盖原位置和文档支持的 `user → system → assistant` 位置。模型实收核对成功请求的原系统角色、位置及内容。仅有顶层 `system` 的 V2 正对照须使用交互 CLI，允许 CLI 自行生成 effort 和环境上下文的 `system` 行。含消息级 `system` 的成功用例以实收合同为准，并记录实际处理路径。传入 `--v1-runtime` 时核对同一公开入口的固定 V1 制品。
- `--structured-output-contract` 从普通公开入口对照三种账号动作的无 schema、仅 schema、schema 与 `effort=medium`，覆盖 SSE 和非流式 JSON。无 schema 的六例走交互 CLI。成功用例核对模型实收的 `output_config`、问题一次、工作指令落点和公开响应终态。隔离模型仅在收到完整 schema 时返回约定的 JSON 文本。用预留、尝试和实收摘要确认发送路径，拒绝用例核对零尝试和零投递。最终 TLS 写出未采集。
- `--forced-tool-choice-contract live|restart` 从公开 Messages 对照 `any` 和指定第二个工具。隔离模型按实收字段决定调用，`any` 两次分别选择两个工具，指定工具两次使用同一名称及各自 ID。续轮提交原调用结果并保留强制选择，最后一个合法回执可在旧账号发送路径显式选用 `auto`，接收合成文本。其后在同一公开会话带已确认历史提交独立 `auto` 请求，核对 CLI 认领摘要等于模型实收、只投递一次、原两组工具调用和结果完整。`restart` 在第一个回执前结束原 CLI 并重启账号发送器。报告按预留对照 CLI 正文及实际模型请求的摘要、字段、工具名、参数与回执。`verify_tui_tool_choice_input.py <固定 CLI>` 在仅回环网络独立验证工具权限选项与模型请求。最终 TLS 写出未采集。
- `--forced-tool-choice-contract restart-metadata-only` 在首轮工具回执登记后结束原 CLI，原档只保留实际 CLI 写出的非主轮记录。通过相同公开请求验证父版 `cli_launch` 失败与本版独立 CLI UUID 成功，核对原档和绑定字节、回执归属及实收投递。观测记录原进程退出、旧发送器退出和新发送器就绪、入站正文摘要、预留以及 CLI 实际启动模式。
- `--no-tool-choice-contract` 从公开入口对照三种策略的缺省、显式 `none` 且 `tools` 省略、显式 `none` 且为空数组，以及 `none` 同带工具声明。按预留核对原生分支、模型实收工具及选择、工作指令角色和公开文本终态。最终 TLS 写出未采集。
- `--thinking-display-contract <claude-sonnet-4-6|claude-opus-5-5>` 通过普通 Messages 对照省略整个 `thinking`、仅省略 `display`、显式 `omitted` 和 `summarized`。完全省略时三种账号动作均使用交互 CLI 生成 `adaptive/updates`，显式 `summarized` 也走交互 CLI。仅省略 `display` 或显式 `omitted` 时，追加策略经账号代发保留原对象，替换及用户提醒均返回 `422/unsupported_parameter`、零投递。隔离模型按文档模拟 Sonnet 4.6 缺省摘要及 Opus 5.5 缺省省略，SSE 检查摘要增量和签名顺序，JSON 检查等价内容块。显式 `omitted` 的合成回复保留空思考块和签名。核对原生分支、正文 SHA-256 及预留和尝试的关联。最终 TLS 写出未采集。
- 将 `--thinking-cli-summaries on|off` 与 `--thinking-display-contract` 同用，探针只在启动固定 CLI 的 `--settings` 设置 `showThinkingSummaries`。公开请求省略整个 `thinking`。两个模型在 `on` 下原生生成 `adaptive/summarized`，在 `off` 下原生生成 `adaptive/updates`。两种状态的 SSE 和 JSON 均按隔离模型实际回复核对。`off` 产生的 `updates` 和显式 `omitted` 是不同的模型请求模式。
- `verify_tui_system_session_input.py <固定 CLI>` 在仅回环容器内以真实交互 2.1.293 和 Opus 5.5 核对 `hookSpecificOutput.additionalContext`。`UserPromptSubmit` 的正文由 CLI 加上来源前缀，放在该轮 user 之后、该轮 assistant 之前的 `system` 行。档案保存 `hook_additional_context` 附件，热续轮和从原档案 `--resume` 都保留该位置和一次内容。恢复时新执行的 `SessionStart` 钩子生成带来源前缀的当前轮 `system`，排在重开后新 user 之后。此组件实验记录直接由 CLI 发出的模型正文和原档案前缀，外部 Messages 原始文本块及指定历史位置仍需独立满足公开输入合同。当前公开追加策略对中途 `system` 的成功形状依赖旧账号代发，保留退役阻塞。
- 当前 V2 的普通 API 在替换和用户提醒下对已测消息级 `system` 返回 422。相同普通正文声明 CLI UA 时，入口按 UA 选用 Claude Code 路由，发送器仍按普通正文处理，模型单次实收保留消息级角色和内容，调用方的身份 metadata 缺失。带合法 billing 和结构化 metadata 的合成对照可保留其原生正文。无 billing 时，规范 `claude-cli` UA 与官方身份块、合法 metadata 的组合可保留客户端 metadata。无 billing 的 `claude-code` 别名对照可完成公开请求，发送器出站省略该 metadata。此对照记录入口策略和账号正文归因的实际边界，消息级 `system` 的新 V2 原生合同保持开放。最终 TLS 写出未采集。
- `verify_tui_cold_history.py --system-policy` 从管理 API 保存并读回动作，按公开 Messages 的模型实收核对三种落点。`--tool-policy` 对照替换和用户提醒的工具往返。`--toggle-pending-policy` 在原工具等待时更改动作，核对回执隔离及原轮指令。
- `verify_tui_cold_history.py --recover-pending-tool` 结束唯一等待中的真实 CLI 并重启其账号发送器。修改账号动作和客户端指令后，原回执仅继续其冻结策略，恢复模型步骤的正文来自真实 CLI。
- 公开首轮和原工具回执的意外状态或断连先写出 HTTP 状态、请求 ID、夹具阶段与隔离模型收件，再在网关退出前读取对应请求的诊断阶段及所属尝试。无响应头时只列同一合成会话和本次时间窗口内的候选。失败证据输出到 stderr，原失败仍使验收退出。
- `--trace-initial-startup` 复用 `tui_startup` 的单调时钟事件。Linux `v3-verification` 网关和账号发送器均由 `FLOWER_V2_STARTUP_TRACE=1` 打开。通过 `gateway_reservation` 的请求 ID 和预留 ID 关联 `sender_private_send`、`sender_send_claim`、`sender_submission_ledger_lock`、`sender_submission_ledger`、`sender_workspace_bind` 和 `sender_unix_send`。账号侧只写预留、阶段、固定结果及单调时间。提交截止时，外层账本结果可能先于阻塞线程的加锁结果写出。两处均按同一预留区分。搭配 `--recover-pending-tool --recovery-ledger-deadline` 的账本未提交对照或 `--recovery-workspace-rejection` 的提交后绑定拒绝，核对失败阶段、零新增模型投递和原回执可继续使用。
- 公开冷导入夹具在模型连接的工作线程办理 TLS 握手。用 `--initial-idle-model-connection` 在首请求前打开一条未握手的 TCP 连接并保持到公开回包，核对首请求返回 200、模型收件一次及后续工具正常续轮。
- `--trace-initial-startup` 开启当前 V2 源码夹具的启动观测，`--initial-idle-model-connection` 自动开启同一观测。网关用 Linux `v3-verification` 构建。日志记录同一单调时钟下的网关预留、事件源准备完成或拒绝、发送、CLI 起进程和回调、代理接入及模型 TCP、HTTP、完整正文边界。空闲连接和模型连接以回环端口区分。与 `--recover-pending-tool` 同用时，首轮和重启后的合法回执分别记录实际 sender 就绪、公开响应头与请求 ID、模型收件次数及正文摘要。原始失败首先输出，然后保留线程栈及请求诊断，最后独立读取一次 sender 状态。响应头缺失时的诊断记录标为会话候选，客户端取消只说明终结结果。
- 预留前的 V2 准入拒绝在同一时间线中以公开请求 ID 记录固定分支，预留字段缺省。预留后的准备事件以同一预留分别记录账本读取、本机绑定和准备交换的开始、确认或拒绝，并沿用提交认领、账本写入和工作区绑定事件。夹具故障行记录公开会话、请求正文摘要、响应状态和截至失败时的模型收件摘要。将 `--recovery-readiness-rejection` 与 `--recover-pending-tool` 同用，核对账本权限造成的预留前 503、`tui_readiness_ledger`、零次尝试和恢复权限后一次续轮。此对照与自然 503、首响应头超时分别记录。
- 发送器在向本机事件源发出 `send` 之前同步写入提交账本。账本终态写入沿原预留的单调截止等待文件锁。发送前账本拒绝的私有回包标为 `tui_submission_ledger`，网关记录同名诊断阶段并归还原工具回执。将 `--recovery-ledger-contention` 与 `--recover-pending-tool` 同用，核对持锁两秒后合法回执完成、模型总收件两次、原归档保留。
- 原工具回执的私有发送首包等待与准入共用截止时，网关在原截止后最多再观察 250 毫秒，只接纳同一已鉴权请求中带单值 `tui_submission_ledger` 标记的 429。提交截止和原预留保持不变。缺少明确拒绝时仍按提交状态未知处理。将 `--recovery-ledger-deadline` 与 `--recover-pending-tool` 同用，核对 3 秒预算持锁到回包的 429、账本阶段、零次模型尝试以及释锁后原回执单次续轮。
- 网关在根诊断的 `context.tui_reservation_id` 关联 sender 预留。已鉴权私有响应的固定阶段区分准备阶段的账本读取、源绑定及准备交换，以及提交阶段的预留认领、账本终态和工作区绑定。阶段标记限于单值白名单。工作区绑定在 Unix `send` 之前明确拒绝时归还原回执。将 `--recovery-workspace-rejection` 与 `--recover-pending-tool` 同用，核对 `tui_workspace_bind`、零 attempt、原回执可重新认领以及恢复绑定后仅向模型投递一次续轮。
- V2 私有 HTTP 提交结果未知时，公开 502 的完整响应记为 `transport_error / tui_send_http`，沿原请求保留预留 UUID 和实际观测的尝试数。该边界不生成发送前拒绝采集。将 `--recovery-slow-model` 与 `--recover-pending-tool` 同用，核对模型早于公开 502 收件、请求和预留关联、零已记录尝试、合计两轮模型和一次新工具。已有证据的发送前拒绝仍为 `local_rejected`。
- 首次创建工作区绑定仍在锁内原子发布。续轮只读已发布的绑定及工作目录，读取时核对原主体、会话键、UUID 和私有权限。测试在持有提交账本锁时读回既有绑定，同时核对跨主体拒绝及原文件字节。
- 就绪和准备的无锁账本读取若碰到原子替换后已脱离目录的旧文件描述符，沿原调用截止重新打开当前路径。属主、0600、唯一链接及账号环境仍须匹配。写入终态继续在锁内重读。就绪探测按 `tui_readiness_config`、`tui_readiness_ledger`、`tui_readiness_source` 区分配置、账本和本机源失败，准备账本失败仍标记 `tui_prepare_ledger`。
- `verify_tui_cold_history.py --output-effort` 核对四档强度、显式禁用思考及不同 `max_tokens` 的公开入口实收。`--recover-pending-tool` 核对原轮强度与拒绝改写。
- `verify_tui_cold_history.py --history-png` 核对追加、用户提醒两种动作下的原角色、历史图像字节和单次当前问题。
- `verify_tui_cold_history.py --history-images` 在同一旧用户消息中核对 PNG、JPEG、GIF、WebP 的顺序和原始数据。
- `verify_tui_cold_history.py --current-images` 核对本轮九块交错图文、四种内嵌格式、重复 PNG、重复多行文字与边界内纯图片请求的实际模型正文。增加 `--current-image-ending image` 对照图片末块。两种末块均覆盖同进程和 `--recover-pending-tool`，独立比较原始业务块、额外上下文和每条来源文本，并报告原始数组等价性及摘要。九块样本含五张图，首轮及热续轮实收九个业务块、五个 CLI 上下文块和五个附件来源块。末块为文字时多一个 LF。丢进程恢复的该历史行与客户端原始九块逐块相等。交换图片顺序的回执返回 422。夹具还覆盖隔离程序当前 HOME 的目录描述符读取及外部 HOME 拒绝。
- 独立图像补测使用可完整解码的透明 PNG、带 EXIF 的渐进 JPEG、双帧 GIF、双帧 WebP 及重复图块。核对原 MIME、Base64、顺序和上述原始数组差异。像素和字节边界的 18 例包含三种动作的 2000 像素、512000 字节正例，以及 2001 像素、512001 字节在有无顶层 `system` 时的路由和投递。正例各投递一次。超界 `append` 四例各投递一次，保留原 `messages`。另外八例均为 `422/unsupported_parameter`、零投递。
- `verify_tui_cold_history.py --history-tool-blocks` 核对已闭合的两个文本结果块、顺序及原 ID，并完成一次新工具回执。`--history-cache-markers` 还核对重复的工具结果文本上单个嵌套断点的准确位置，以及在线续轮、丢进程恢复和篡改拒绝。
- `--current-images --history-cache-markers` 核对同轮图文与直接、嵌套历史断点。首轮和合法回执各由交互 CLI 投递一次，保留图文业务块及断点位置，附件来源没有 CLI 自动断点。改写历史标记或交换图片顺序返回 422。与 `--recover-pending-tool` 同用时核对原图文行和断点同时恢复。
- `verify_tui_cold_history.py --stock-client` 让未修改的固定 Claude Code 2.1.293 从公开 V2 入口执行 `Read`。三种账号提示词策略各用独立客户端 HOME，隔离模型实收正文与客户端逻辑正文逐字节一致。按相同调用 ID 核对工具参数、原回执、客户端读到的便签与最终答复。当前六次投递在管理记录均归属旧账号发送器，并分别关联新进程与热续轮。此结果是完整 CC 的退役前基线。最终 TLS 写出未采集。
- `verify_tui_cold_history.py --cancel-and-change-question` 在公开首轮交付工具 ID 和部分参数时断开读者，隔离模型继续保留尾段。确认原请求终态为取消后，沿同一公开会话从客户端确认的历史改问。新轮走交互 CLI，已取消问题和工具不会进入模型正文，原绑定和会话档案按原字节保留。迟交被取消的工具回执返回 400、零尝试。两轮各一次模型实收。
- `verify_tui_cold_history.py --parallel-new-tools` 从公开入口核对同一模型响应的两个不同 Schema 的工具。客户端执行返回的调用并按原 ID 逆序回传。模型实收恢复调用顺序，成功文本逐字保留，失败保留 `is_error` 和原文本及原生 token 提醒。缺少结果、用重复 ID 代替缺项、齐全后追加重复项均返回 400，模型零新增收件。随后合法组完成一次。
- `verify_tui_cold_history.py --auto-tool-choice [bare|explicit-false]` 核对原字段形状、完整工具声明与实际模型正文省略 `tool_choice`。省略选项值时沿用 `explicit-false`。分别与 `--parallel-new-tools`、`--recover-pending-tool` 组合，核对双工具正常续轮与单组丢进程恢复各投递两次。四种改写均拒绝，随后原样回执成功。`--auto-tool-direct-text` 以 bare auto 带两项工具声明验证一次模型投递、零工具执行及公开文本 `end_turn`。
- `verify_tui_cold_history.py --split-history-tools` 核对分行的两对旧工具及结果、原顺序和单次新工具执行。
- `verify_tui_cold_history.py --current-text-blocks` 核对本轮两个独立文本块的模型实收，合并边界的回执返回 422。与 `--recover-pending-tool` 组合时，另核对重启后原始文本块、记录和工具结果仍被保留。
- `verify_tui_cold_history.py --signed-tool-history` 从公开 SSE 重组签名块，核对同进程和 `--recover-pending-tool` 的合法回执、原档及模型实收。用 `--adaptive-thinking-model <模型>` 和 `--adaptive-thinking-display default|updates|summarized` 区分省略 `thinking` 与两种显式模式。`--signed-tool-response signature-only` 模拟带签名的空思考块，`--signed-tool-response missing-model` 保留签名而省略模型响应里的助手模型，验证冷恢复 422 和零尝试。源检查点只登记实收模型，恢复档只在对应的已验签助手行携带该事实。
