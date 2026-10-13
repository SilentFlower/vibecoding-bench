# v3 固定账号运行环境契约

## Scenario: 固定 Docker、API/CLI 独立调度及证据恢复

### 1. Scope / Trigger

- 修改 `orchestrator/account_runtime.py`、v3 管理桥/租约/发送器、账号镜像及部署入口时适用。
- 本规范是 v3 的共同契约；旧版每 run 的 worker/sidecar 路径继续兼容。被动额度算法遵循 [数据库规范](./database-guidelines.md)，抓包限频遵循 [官方协议抓包规范](../deploy/official-protocol-capture.md)。
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
AccountRuntime.cleanup(container_id: str) -> None
```

管理租约输入为 `operation: string`、`owner: string`、`generation: string | null`；操作为 `prepare-cli`、`prepare`、`claim`、`heartbeat`、`fence`、`release`。查询返回 `lease`、`active`、`waiting`、`importing`；租约包含 `owner`、`generation`、`expires_at`（UTC 秒）、`phase`、`exclusive`，TTL 为 30 秒。旧记录缺少 `exclusive` 时默认 `true`。fence 与在途导入保护见下方重授权场景。

发送绑定 `TransportBinding`：`account_id: i64`、`environment_id: string`、`generation: u64`、`endpoint: string`、`secret: string`、`release_id: string`。`PreparedRequest` 增加 `request_id`（UUID）、`deadline_unix_ms`、`method`、`target_url`、有序 `headers` 及 `preserve_header_casing`；最终 body 独立传原始字节。秘密只在服务间传递。

```text
scripts/v3-stack build --release <唯一批次> --manifest <新清单>
scripts/v3-stack publish --manifest <本地清单> --output <新发布清单> --bundle <新镜像包>
scripts/v3-stack pull --manifest <发布清单>
scripts/v3-stack load --manifest <发布清单> --bundle <同批镜像包>
scripts/v3-stack up --env <独立配置> --manifest <联合清单>
scripts/v3-stack status --env <独立配置>
scripts/v3-stack stop --env <独立配置>
```

配置入口为 `deploy/v3/example.env`，实际参数以 `manage.py --help` 为准。

### 3. Contracts

**数据与凭据**：cc2api 拥有绑定账号、代理、OAuth 和唯一刷新权；bench 拥有环境、任务、持久目录及证据。两侧通过受控 API 协作。绑定 CLI HOME 仅发布 AT，删除 RT；401 沿用 managed 刷新流程。身份导入仅接受 Recorder 实际观测且与登录账号归属一致的设备身份，来源未知或冲突时阻止同步；不把 Linux machine-id 当成 device_id。

**环境**：每账号一个固定 account 容器、完整 `/home/node` 和版本缓存。环境 ID、固化 machine-id/hostname/MAC 不随 run、改名或停止唤醒重算；重建可换 container ID，但保留 HOME 和环境身份。容器 DNS 为 `v3-<deployment_sha256前12位>-account-<environment_id>`，完整归属由产品/部署/角色/环境 labels 校验。只按本部署精确标签维护，不用宽前缀或 prune。

**调度**：

- `prepare-cli` 创建共享租约：普通 CLI、养号、抓包、续聊彼此串行，API 可同时入场。共享 claim/release 不等待独立 API 排空；养号只让位于正式 CLI 工作与租约。
- `prepare` 创建排他维护门禁：重授权、代理修改、绑定切换、停止、重建检查或排空 API。配置 quiesce 验证排他 owner/generation、API 活动数和本环境 CLI/发送器状态。
- CLI 安装在认领后执行，不持有环境生命周期锁；API 就绪不安装 CLI。原 weighted slot/FIFO/RPM/粘性请求和 SSE permit 规则保留，OAuth resolve 不等待 CLI 租约。
- driver 和续聊 wrapper 使用 `setsid --wait`，Docker exec 生命周期必须跟随实际进程。tmux 登录 shell 显式保留选定 CLI 缓存 PATH。
- 清理必须匹配完整执行 token，不接受裸 container ID。停止本代进程组、tmux、UID1000 子进程，撤销 Recorder 并恢复 hook 后释放租约；不通过停止整个容器清理普通 CLI。
- `runtime/execution.json` 保存租约模式、owner/generation、driver/tmux/hook 证明。共享清理/心跳/重启对账失败进入 `cli_reconcile`，阻止下一 CLI，健康 API 继续；未知/旧排他记录保守隔离。公共网络或发送器故障仍关闭容器；CLI 专用 Recorder 故障只标记 CLI 不健康。

**HTTPS 与证据**：管理端完成选号、改写、重试和响应分类，目标账号内发送器复用现有 HTTP/TLS 实现实际建立上游连接。每账号独立进程/连接池及代理，API 不经 CLI MITM。绑定、批次、目标、截止时间和秘密不符时拒绝；桥接失败无直连回退，提交不确定不能盲重发。API 被动观察单独写 `flows/api/observations.jsonl`，不混入 run 统计。

```text
bench/environments/<environment_id>/
  home/                              完整 CLI HOME
  cli/<version>/                     版本安装缓存
  workspaces/<run_id>/                原任务 cwd
  flows/group-<relative_path_hash>/
    executions/<source_hash>/        stats/HTTP/index/原生 flow/被动额度
  controls/<source_hash>/             独立只读暂停信号
  runtime/                           作业脚本/PID/tmux、上下文/ACK、执行证明
bench/flows/<account>/<task>/<run>/    固定兼容链接
```

`execution_flows()` 在账号锁内固定兼容入口；run 与续聊各有自己的证据组。恢复原 run/session/workspace，仅换 source 子目录；QuotaGuard 登记本代实际观察文件，Recorder 使用同一目录。run 统计读取平铺历史及各 run 执行、排除续聊/API并去重路径；抓包索引和文件列表聚合各代及续聊。原生 flow 不覆盖，历史平铺文件保留。跨目录链接拒绝，未部署的旧 v3 原型 source 链接不自动接管。

**部署**：两个最终镜像 control/account；control 按 gateway/orchestrator 两个角色启动，N 个账号共 N+2 个容器，只有 orchestrator 挂 Docker socket。CLI 为 UID1000、无网络能力并禁止提权，服务秘密/控制目录不对项目写入开放。

**资源**：`resource_budget.account_limits(memory: str, swap: str = "0") -> tuple[int, int]` 共用于预检与账号创建；返回 RAM 字节数和 RAM＋swap 总字节数。`V3_ACCOUNT_MEMORY` 支持正整数 m/g，默认 4g；`V3_ACCOUNT_SWAP` 是额外 swap，默认 0，仅接受 0 或正整数 m/g，不接受 -1/无限额。首次保存 `fingerprint_json.mem/swap`；旧缺 swap 字段为 0，改全局配置不重算旧身份或预算。Compose 必须显式传递两参数。

预检分别比较 `MemAvailable` 与 `SwapFree`：RAM 至少为活跃上限×账号 RAM＋1 GiB，显式更高的 `V3_MIN_FREE_MEMORY_BYTES` 优先；swap 足够覆盖活跃账号额外额度，且 Docker `SwapLimit` 为 true。不能以 swap 抵扣 RAM 余量；已有环境保存的 RAM/swap 超过配置时拒绝启动，禁止下调配置掩盖未来唤醒预算。1536m RAM＋2048m swap、活跃 1 对应 Docker Memory=1610612736、MemorySwap=3758096384，预检要求约 2.5 GiB 可用 RAM与2 GiB空闲 swap；默认4g仍需5 GiB RAM。这是额度边界，真实 CLI 峰值另行验证。

清单记录 `schema=3`、`bridge_protocol=1`、`layout_version=1`、默认 CLI、release、父/子仓 revision、dirty 标记、冻结内容 SHA256 及两个 image ID/平台。`images[role].digest` 保留构建机本地 Docker Id；containerd 可用 OCI 索引作为 Id，所以另保存 `config_digest`（docker save 中原始配置字节 SHA256），发布后 `registry_digest` 才是仓库 manifest/索引 digest。换 daemon 时只接受清单固定的配置或 OCI 根，角色/批次/提交/平台仍检查，不能因 ID 语义不同放弃核对。构建先冻结源码，标签/清单不能覆盖。启动检查清单组合、实际镜像 labels、宿主发布端口、名称/网络/挂载 realpath、数据归属及资源预算。

**发布**：`.github/workflows/v3-build.yml` 只在 v3 ref 发布，联合 build 后使用 GITHUB_TOKEN（contents:read、packages:write）登录 GHCR；两个包为 `ghcr.io/silentflower/vibebench-v3-{control,account}`，标签 `v3-ci-<run_id>-<run_attempt>`，不写 latest/旧包。publish 校验 Action 的仓库、父提交与 run/attempt、干净构建来源和全新输出，独占 `.started` 标记禁止同次重试；失败保留现场，新 attempt 才重跑，不把仓库 denied 当成“未存在”。两件成功、仓库 digest 可核对且镜像包成功才写最终清单；原构建清单不改。

artifact `v3-release-<run_id>-<run_attempt>` 保存发布清单与同批 gzip 镜像包，保留14天；`bundle={name,sha256,size}` 核对完整包。pull 按 registry_digest 下载再建立受控标签，load 先核对名称/大小/SHA256；现有本地标签若镜像内容不同都拒绝覆盖。包不含部署配置/账号数据或 registry 登录资料；首次私有包不能匿名 pull 时使用同批 artifact，不在服务器保存 PAT或自动改变包可见性。

关键配置：`V3_DEPLOYMENT_ID`、`V3_RELEASE`、`V3_CONTROL_IMAGE`、`V3_ACCOUNT_IMAGE`、`V3_DATA_ROOT`、`V3_INTERNAL_TOKEN`、`V3_SESSION_SECRET`、`V3_ADMIN_PASSWORD`；服务间使用 `V3_RUNTIME_URL`、`V3_NETWORK`、`V3_LEASE_DIR`。默认宿主端口 `18080`、活跃账号上限 1，实际冲突拒绝，不自动停旧服务。内存/CPU、空闲停机与日志轮转由 v3 配置控制。

统一 Vue 后台通过受鉴权的 `/runtime/` 桥访问 bench，保留 HTTP/SSE/WS。浏览器桥限定路径/方法，拒绝内部和编码绕过；v3 Cookie 名和 scope 独立，退出撤销服务端会话及旧票据。终端资源打包到镜像，不依赖运行时 CDN。

**管理页面布局**：`route.name === 'environments'` 时 Dashboard 使用 `100dvh` 纵向 flex，隐藏统计卡片，main 全宽且 `flex: 1; min-height: 0`；Environments 的 iframe 填满剩余空间，无额外边距、圆角或固定高度扣减。外层不承担内容滚动，bench 保留原主题和自身滚动；离开该路由后恢复网关普通页的内容宽度、统计卡片和滚动。

bench 导航项不拆分中英文标签；宽度不超过 1440px 时导航独立一行，不超过 920px 时顶部区域单列、隐藏品牌副说明并允许整项换行。表格保持水平滚动和内容自适应高度，超出 1px 的装饰线不能触发纵向滚动条。静态 CSS 更新时同步 index.html 的样式版本参数，避免缓存保留旧布局。

停机/备份/离线导入只作用于本部署，保留持久数据。离线导入默认 dry-run，来源幂等，拒绝凭据，账号停用、旧活动 run 停止，不恢复旧调度；真实接管不能让旧、新系统同时刷新同一账号。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| API 活动或排队，普通 CLI 认领 | 共享认领，不关闭 API 入场 |
| 两个 CLI 同账号竞争 | 只认领一个；低优先级养号顺延 |
| 活动 API/CLI，空闲维护 | 拒绝，不中断已接受工作 |
| 旧 token/租约代次清理 | 不清理新作业 |
| 共享租约过期/服务重启 | 保留 API，先确认旧 CLI 收口，再允许下一 CLI |
| Recorder 撤销失败 | CLI 隔离，禁止下一 CLI；公共网络健康时 API 保留 |
| 同 run/续聊第二代 | 固定入口、新观察游标/flow，旧证据不变 |
| 错误环境绑定/镜像批次/秘密/目标 | 拒绝发送，不直连、不重放 |
| 宿主端口/名称/挂载或数据归属冲突 | 启动前拒绝，不操作旧资源 |
| 浏览器内部路径/退出后 Cookie 或票据 | 拒绝，服务秘密不下发 |
| RAM 不足、swap 不足/daemon 不支持、已有固化预算更高 | 拒绝启动，不改旧账号预算或旧服务 |
| 非当前 v3 Action、dirty 来源、同 attempt 或已有输出 | 拒绝发布，不覆盖批次 |
| 任一推送、仓库 digest 或镜像包失败 | 无完整发布清单，已推镜像保留 |
| 包名称/大小/SHA256、镜像角色/ID/平台不符 | 拒绝交付；本地同批标签不覆盖 |
| 桌面或窄屏打开环境与任务 | iframe 全宽，底边贴合视口；标签保持横排，外层不产生额外滚动 |

### 5. Scenarios and Examples

- 正常：API SSE 运行时启动养号 CLI，取消 CLI 后继续收到新 API 数据；同账号第二个 CLI 仍需等待。
- 基础/历史：停止唤醒或镜像重建保留 HOME、环境 ID 和 machine-id；平铺历史统计/抓包仍可读取，空环境返回可展示状态。
- 错误用法：`run:<rid>:1` 把原 run 链接改到新 source 目录，或者复用旧 `capture.flow`，造成冲突/证据覆盖。正确做法：固定证据组、每代独立目录，游标与 Recorder 共用实际路径，读取端汇总。
- 错误用法：看到 Docker exec 已创建就算 CLI 正在运行，或用 container.wait 判 run 完成。正确做法：`setsid --wait` 并确认 exec/tmux 实际运行，终态由本执行结果判断。
- 错误用法：只直调 sender 就宣称网关链路通过。正确做法：真实 gateway 入口经短 DNS 绑定到账号 sender，并验证错误绑定拒绝且无重放。
- 正常：同一 Action 发布两镜像，服务器按仓库 digest 拉取或加载校验过的同批包，再 check/up；空数据库只启动两管理服务。
- 基础/历史：旧环境没有 swap 字段，继续禁用；Docker 存储实现更换后本地 ID可以不同，但固定 config_digest/registry_digest 与平台仍能核对。
- 错误用法：将 memswap_limit 设成 RAM值却声称容器可用宿主 swap，或用 SwapFree 抵扣 RAM 预算。正确做法：总限额为RAM＋额外swap，预检分别比较两种余量。
- 错误用法：把本地 Docker Id 当作仓库 digest，或只成功推一件就生成可部署清单。正确做法：三种哈希明确区分，两个角色都成功后才保存完整交付结果。
- 错误用法：把 bench 放进网关的 max-width 容器，叠加统计卡片和 iframe 的 `100vh - 100px` 高度。正确做法：环境路由独占导航下方工作区，flex 根据实际导航高度分配 iframe 空间。

### 6. Tests Required

- Rust `cargo fmt --check && cargo test`：画像/改写、weighted FIFO/RPM、共享/排他租约、旧记录/过期/重启、绑定校验、原始字节/有序头/SSE取消、不重放；回环临时 CA 验证 HTTPS 正常响应及错误证书/主机名拒绝。测试 CA 不进入正式客户端。
- Python orchestrator 回归：原快照与 session 恢复、旧 token/绑定保护、并行与安装续租、证据/游标分代、统计不重复、错误链接拒绝、鉴权和永久额度门禁。
- Recorder 与部署回归：请求归属冻结、ACK/身份、冲突预检、准确资源归属、停机、备份和导入幂等。
- 资源/发布回归：1536m＋2048m 实际 Docker 限额，默认/旧缺字段、非法无限值、RAM/swap不足、已固化预算拒绝；当前 Action 来源/attempt、第一/第二件推送失败无完整清单、错误digest/包拒绝、本地标签不覆盖，跨 store ID相同配置可核对。
- actionlint 核对 ref、权限与 artifact；实际本地 registry 的 push/pull、归档 config 哈希以及双镜像 save/load 核对。CI/GHCR发布结果与指定服务器实时预检/健康/旧服务不变在发布后验收，不能以本地替身称其已完成。
- 联合重建后串行跑 `run_local_verification.py --manifest ...`、`verify_stack.py --manifest ... --browser`：实际运行中的合成 CLI、同 run 第二代、API 长流与新增 API、CLI 取消/重启/Recorder故障保留 API、tmux 重连、两账号传输隔离、旧哨兵及数据库不变。
- 校验冻结源码哈希和最终输入一致，标明平台、失败日志、测试替身及未执行项。真实 CLI OAuth/实际主会话/额度恢复、公网全链路与同宿主压力由隔离部署负责人后续验证；arm64 发布前在对应环境验证。不能用本地 mock 宣称这些真实验收已完成。
- 只改管理页面布局时运行 `cd cc2api/web && npm run build`，浏览器覆盖 1541/1280/920/390px 与明暗主题：iframe 宽度等于视口、顶边等于导航底边、底边等于视口高度，外层无溢出，标签不竖排；表格内容高度完整、窄屏水平滚动可用，弹窗及退出可用，切回网关账号页恢复统计卡片和普通布局。

## Scenario: v3 关联重授权提交与恢复

### 1. Scope / Trigger

- 修改绑定账号的 CLI 登录、凭据镜像、取消、启动对账及环境页维护时适用。cc2api 导入 DTO/回执/条件写入以 [服务契约](../../cc2api/backend/service-architecture.md#scenario-v3-重授权凭据导入与迟到回包保护) 为准；页面连接以 [终端生命周期](../frontend/hook-guidelines.md#scenario-v3-登录终端重连与授权链接) 为准。

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
- 测试环境安装 `orchestrator/requirements.txt` 与 `orchestrator/requirements-test.txt`，后者只用于 ASGI 客户端，不新增产品依赖。
- 隔离 Chrome/HTTP/WS/tmux 验证真实键盘/原生粘贴、按钮/Enter、回包丢失后查询且不重放、WS 断线独立发送；全新 HOME、禁网的真实支持 CLI 验证收到合成无效码，不访问真实 OAuth，不把实验二进制打入正式镜像。

## Scenario: v3 未提交登录草稿与完整清理

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

### 5. Scenarios and Examples

- 正常：start 创建专属环境，刷新账号页后用 `resume {"generation":"页面返回值"}` 继续原 SID；CLI 结束时显式 restart 创建新 SID，环境/CID/userID 保留。
- 基础：管理器突然退出后发现 interrupted 草稿；没有产物则重新登录，有产物则先验证认证再提交，账号容器仍按需唤醒。
- 错误用法：只有 credentials 文件就标记已登录，或提交 IO 失败后通过删除放行。正确处理：真实 CLI 认证检查；submitting 保留资料和门禁，继续提交/对账。
- 错误用法：用旧页面代次删除新登录，或凭账号名称前缀批量删容器。正确处理：锁内重读代次、精确标签和目录归属，仅清专属未提交资源。
- 基础：取消清理失败进入 reconcile，但原执行可核对且已停止；使用恢复检查收口旧会话，保留 HOME 后开放继续/重登/删除，不把恢复当作删除。

### 6. Tests Required

- `test_login_drafts.py` 用临时 SQLite/文件和 Docker 替身覆盖列表/旧环境、非调度、同 SID 继续、原身份重登、重启产物认证、本地保存中断、取消/提交/删除互斥、旧代次/锁内 404、正式/软删除/历史保护、labels/链接拒绝和部分清理重试。
- 必须断言坏 JSON、错环境及 home=null 只隔离单条，另一正式账号仍可读取，坏孤立标记可见且不能删资源；旧非 v3 status 继续按原凭据存在契约返回 credentials_ready，v3 仍须真实认证检查。
- `verify_stack.py --manifest <最终联合清单> --browser --reauth` 串入 `verify_login_drafts.py`：真实 Docker/Chrome/HTTP/WS/tmux、刷新原 SID、CLI 结束与迟到事件、管理器 SIGKILL 后对账/恢复、原环境提交、鼠标确认完整删除；验证全部专属目录/CID/DB 消失且正式账号保留。
- 合成 CLI/OAuth 和故障替身必须明确标注，不访问真实 OAuth；按随机部署精确标签清理测试数据与容器，核对旧哨兵不变和最终冻结源码哈希。真实 OAuth/正式 API 另作上线后验证。
- 清理故障验证 503、can_reconcile 与原 SID/名称释放；拒绝活动工作、未知证明、旧代次及未确认保存，恢复前后 HOME/身份不变。代理 JSON/DOM 不含 userinfo，配置读取失败为 unknown；真实浏览器点恢复后可完整删除草稿而正式账号保留。
