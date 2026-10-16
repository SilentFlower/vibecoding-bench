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
AccountRuntime.execution_environment(row: dict) -> dict[str, str]
V3_DEFAULT_TIMEZONE = "America/Los_Angeles"
AccountRuntime.cleanup(container_id: str) -> None
AccountRuntime.run_session_path(run_id: str) -> Path
AccountRuntime.reprofile_blocker(row: dict) -> str | None
derive_v3_fingerprint(timezone: str | None = None) -> dict[str, object]
NetworkInspectionMode = "passthrough" | "quota" | "capture"
/run/v3/context.json -> {NETWORK_INSPECTION_MODE, QUOTA_SOURCE, ...}
/run/v3/context-ack.json -> {NETWORK_INSPECTION_MODE, QUOTA_SOURCE, process}
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

**数据与凭据**：cc2api 拥有绑定账号、代理、OAuth 和唯一刷新权；bench 拥有环境、任务、持久目录及证据。两侧通过受控 API 协作。绑定 CLI HOME 仅发布 AT，删除 RT；401 沿用 managed 刷新流程。身份导入接受 Recorder 实际请求观察，或经指定官方版本实测验证的本地字段映射，并核对登录账号归属；来源未知或冲突时阻止同步。当前 2.1.293 的 device_id 来自固定 HOME 的 `.claude.json.userID`，不能用 Linux machine-id 或独立 machineID 替代，详见下方身份同步场景。

**环境**：每账号一个固定 account 容器、完整 `/home/node` 和版本缓存。新环境的 `fingerprint_json.profile_version=2`；hostname 为独立随机 12 位小写十六进制，machine-id 为独立随机 32 位小写十六进制，MAC 为独立随机的本地管理单播地址。时区来自账号显式配置，locale 与地区成组持久化；未配置的新环境使用 `America/Los_Angeles` + `en_US.UTF-8`，IANA 时区自动处理夏令时；已有 UTC 或其它画像保持，generation=0 的已登记画像也不重算。环境 ID、profile、RAM/swap 不随 run、改名、停止唤醒或容器重建重算；旧记录缺 `profile_version` 时保持 legacy。重建可换 container ID，但保留 HOME 和环境身份。容器 DNS 为 `v3-<deployment_sha256前12位>-account-<environment_id>`，完整归属由产品/部署/角色/环境 labels 校验。只按本部署精确标签维护，不用宽前缀或 prune。

**调度**：

- `prepare-cli` 创建共享租约：普通 CLI、养号、抓包、续聊彼此串行，API 可同时入场。共享 claim/release 不等待独立 API 排空；养号只让位于正式 CLI 工作与租约。
- `prepare` 创建排他维护门禁：重授权、代理修改、绑定切换、停止、重建检查或排空 API。配置 quiesce 验证排他 owner/generation、API 活动数和本环境 CLI/发送器状态。
- CLI 安装在认领后执行，不持有环境生命周期锁；API 就绪不安装 CLI。原 weighted slot/FIFO/RPM/粘性请求和 SSE permit 规则保留，OAuth resolve 不等待 CLI 租约。
- driver 和续聊 wrapper 使用 `setsid --wait`，Docker exec 生命周期必须跟随实际进程。tmux 登录 shell 显式保留选定 CLI 缓存 PATH。
- v3 生成 driver 时去除内部时间戳 Stop hook；UID1000 无权写 root 私有 runtime 树，该信号也没有消费者。完成仍由真实主会话 JSONL 的最新稳定最终 assistant 文本判定，不需要放宽控制目录权限。原 hooks 在作业收口时按快照恢复。
- `_cli_setup()` 在已认领的环境锁内合并固定 HOME 的 `settings.json.env.DISABLE_AUTOUPDATER="1"` 及画像的 TZ/LANG/LC_ALL，保留其他 env/model/hooks 并发布为 UID1000 文件。普通任务、抓包、登录和续聊的 CLI 准备共用此入口；CLI 版本继续由管理端精确缓存与全局运行配置选择。
- 实际任务 driver 在合并 worker_env 后覆盖画像的 TZ/LANG/LC_ALL；登录 tmux 命令、短命令、OAuth 探测和续聊 PTY 使用同源值。账号列表 `effective_timezone` 优先只读既有画像，否则返回显式配置或新默认；GET 不创建环境，不再把旧账号名派生值当作 v3 有效设置。
- 正式普通任务／养号／恢复及非抓包续聊临时安装 `/usr/local/bin/v3-cli-quota` 状态栏包装，只消费官方 rate_limits 与当前主会话的真实响应；不新增 usage 或模型请求。先落盘原 statusLine 及本代命令，收口／重启对账在停止进程后仅恢复仍由本代管理的字段，保留用户运行中改写；具体采集与周期认领见 [额度契约](./database-guidelines.md)。
- 清理必须匹配完整执行 token，不接受裸 container ID。停止本代进程组、tmux、UID1000 子进程，把 CLI 网络恢复为空闲 `passthrough`，恢复 hook 后释放租约；不通过停止整个容器清理普通 CLI。
- `runtime/execution.json` 保存租约模式、owner/generation、driver/tmux/hook 证明。共享清理/心跳/重启对账失败进入 `cli_reconcile`，阻止下一 CLI，健康 API 继续；未知/旧排他记录保守隔离。公共网络或发送器故障仍关闭容器；CLI 专用 Recorder 故障只标记 CLI 不健康。

**CLI 网络模式**：CLI 始终经 `tun0 -> hev-socks5-tunnel -> 127.0.0.1:8080` 使用账号代理。普通任务、养号、登录/重授权、额度查询和未绑定账号 OAuth 刷新选择 `passthrough`，本地 relay 只完成 SOCKS5 入站与 HTTP CONNECT/SOCKS5 上游握手并复制原始字节，不启动 mitmproxy，也不注入 MITM CA。显式完整抓包选择 `capture`；`quota` 只保留历史格式兼容，v3 不再用模型请求补样。usage 查询复用原生监听并解析返回 JSON，不需要 MITM。模式切换在 `network.lock` 内先核对并定向收口旧 PID，再写原子 ACK；调度器必须逐字段匹配 mode、source、process 才能启动 CLI。代理缺失、认证失败、旧监听未知、ACK 不符或监听退出都失败关闭，不回退直连；relay 的共享空闲计时由任一方向新字节重置。

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
  runtime/runs/<run_id>/             status/transcript/baseline/刷新控制
  runtime/                           作业脚本/PID/tmux、上下文/ACK、执行证明
bench/flows/<account>/<task>/<run>/    固定兼容链接
```

`execution_flows()` 在账号锁内固定兼容入口；run 与续聊各有自己的证据组。恢复原 run/session/workspace，仅换 source 子目录；QuotaGuard 登记本代实际观察文件，Recorder 使用同一目录。真实 cwd 和 `.claude/projects` 键只能使用 `project-<摘要>`，原 run/environment ID、`.bench-*`、`.claude-home`、cc2api 刷新标记和 Stop hook 控制文件不能进入 Claude 可见项目树；旧系统生成的已知控制文件须定向迁移到 runtime，不能删除未知用户文件。v3 Runner 不再创建 per-run `.claude-home`；准备项目时仅用 rmdir 清理该非链接空目录，既有可核对 session 链接按原归属清理，非空／未知链接及其链接父目录保留。旧 runner 的 per-run HOME 保持。run 统计读取平铺历史及各 run 执行、排除续聊/API并去重路径；抓包索引和文件列表聚合各代及续聊。原生 flow 不覆盖，历史平铺文件保留。跨目录链接拒绝，未部署的旧 v3 原型 source 链接不自动接管。

`_project_view()` 在启动 CLI 前给固定 HOME 的 `.claude.json.projects[cwd]` 设置 `hasTrustDialogAccepted=true`，仅限当前系统专属物理项目目录；原子合并并保留 userID、OAuth 身份、其他项目及未知设置。持久 HOME 不走旧 worker 的顶层配置初始化，需显式保存本项目的确认标记。未登录或异常授权仍按原认证入口处理，不信任任意外部目录。

**显式画像校正**：`maintenance(..., "reprofile")` 只接受未绑定 cc2api、无 task/run/identity/草稿/提交/活动作业、容器已停止的 legacy 正式环境。操作保留账号/HOME/代理/资源预算，清理旧容器网络与 CA 产物，生成一次 profile v2 并回到 stopped，保留原登录凭据；不因环境字段变化强制重授权。启动时原 `profile_reauth` 迁回正常生命周期；原 `profile_reauth_reconcile` 的真实执行/提交故障仍按 reconcile 隔离。profile v2 永久拒绝再次 reprofile，真实认证失败才要求重新授权。

**部署**：两个最终镜像 control/account；control 按 gateway/orchestrator 两个角色启动，N 个账号共 N+2 个容器，只有 orchestrator 挂 Docker socket。CLI 为 UID1000、无网络能力并禁止提权，服务秘密/控制目录不对项目写入开放。root 管理的 `v3-account-init`、`v3-network-context`、`v3-cli-version`、`v3-passthrough` 和 `/sidecar` 为 0700；本地 CLI 额度采集 `v3-cli-quota` 为 0755，中文源码注释不必删除。

**资源**：`resource_budget.account_limits(memory: str, swap: str = "0") -> tuple[int, int]` 共用于预检与账号创建；返回 RAM 字节数和 RAM＋swap 总字节数。`V3_ACCOUNT_MEMORY` 支持正整数 m/g，默认 4g；`V3_ACCOUNT_SWAP` 是额外 swap，默认 0，仅接受 0 或正整数 m/g，不接受 -1/无限额。首次保存 `fingerprint_json.mem/swap`；旧缺 swap 字段为 0，改全局配置不重算旧身份或预算。Compose 必须显式传递两参数。

预检分别比较 `MemAvailable` 与 `SwapFree`：RAM 至少为活跃上限×账号 RAM＋可配置 `V3_MEMORY_HEADROOM_BYTES`（默认 256 MiB），显式更高的 `V3_MIN_FREE_MEMORY_BYTES` 优先；swap 足够覆盖活跃账号额外额度，且 Docker `SwapLimit` 为 true。不能以 swap 抵扣 RAM 余量；已有环境保存的 RAM/swap 超过配置时拒绝启动，禁止下调配置掩盖未来唤醒预算。1536m RAM＋2048m swap、活跃 1 对应 Docker Memory=1610612736、MemorySwap=3758096384，预检要求约 1.75 GiB 可用 RAM与2 GiB空闲 swap；默认4g需4.25 GiB RAM。这是额度边界，真实 CLI 峰值另行验证。

清单记录 `schema=3`、`bridge_protocol=1`、`layout_version=1`、默认 CLI、release、父/子仓 revision、dirty 标记、冻结内容 SHA256 及两个 image ID/平台。`images[role].digest` 保留构建机本地 Docker Id；containerd 可用 OCI 索引作为 Id，所以另保存 `config_digest`（docker save 中原始配置字节 SHA256），发布后 `registry_digest` 才是仓库 manifest/索引 digest。换 daemon 时只接受清单固定的配置或 OCI 根，角色/批次/提交/平台仍检查，不能因 ID 语义不同放弃核对。构建先冻结源码，标签/清单不能覆盖。启动检查清单组合、实际镜像 labels、宿主发布端口、名称/网络/挂载 realpath、数据归属及资源预算。重复 up 只复用本部署 gateway 的精确 5674 映射，其它进程和外部容器占用仍拒绝。

**发布**：`.github/workflows/v3-build.yml` 只在 v3 ref 发布，联合 build 后使用 GITHUB_TOKEN（contents:read、packages:write）登录 GHCR；两个包为 `ghcr.io/silentflower/vibebench-v3-{control,account}`，标签 `v3-ci-<run_id>-<run_attempt>`，不写 latest/旧包。publish 校验 Action 的仓库、父提交与 run/attempt、干净构建来源和全新输出，独占 `.started` 标记禁止同次重试；失败保留现场，新 attempt 才重跑，不把仓库 denied 当成“未存在”。两件成功、仓库 digest 可核对且镜像包成功才写最终清单；原构建清单不改。

artifact `v3-release-<run_id>-<run_attempt>` 保存发布清单与同批 gzip 镜像包，保留14天；`bundle={name,sha256,size}` 核对完整包。pull 按 registry_digest 下载再建立受控标签，load 先核对名称/大小/SHA256；现有本地标签若镜像内容不同都拒绝覆盖。包不含部署配置/账号数据或 registry 登录资料；首次私有包不能匿名 pull 时使用同批 artifact，不在服务器保存 PAT或自动改变包可见性。

关键配置：`V3_DEPLOYMENT_ID`、`V3_RELEASE`、`V3_CONTROL_IMAGE`、`V3_ACCOUNT_IMAGE`、`V3_DATA_ROOT`、`V3_INTERNAL_TOKEN`、`V3_SESSION_SECRET`、`V3_ADMIN_PASSWORD`；服务间使用 `V3_RUNTIME_URL`、`V3_NETWORK`、`V3_LEASE_DIR`。默认宿主端口 `18080`、活跃账号上限 1，实际冲突拒绝，不自动停旧服务。内存/CPU、空闲停机与日志轮转由 v3 配置控制。

停机 backup 用 lstat 排除不可复制的 Unix socket，保留普通文件及符号链接和 SQLite backup API 快照；tmux 等连接由新进程重建，不把运行 socket 当作持久数据，也不删除源 socket。真实 socket、WAL 事务、普通文件和符号链接须一并回归。

统一 Vue 后台通过受鉴权的 `/runtime/` 桥访问 bench，保留 HTTP/SSE/WS。浏览器桥限定路径/方法，拒绝内部和编码绕过；v3 Cookie 名和 scope 独立，退出撤销服务端会话及旧票据。终端资源打包到镜像，不依赖运行时 CDN。

**管理页面布局**：`route.name === 'environments'` 时 Dashboard 使用 `100dvh` 纵向 flex，隐藏统计卡片，main 全宽且 `flex: 1; min-height: 0`；Environments 的 iframe 填满剩余空间，无额外边距、圆角或固定高度扣减。外层不承担内容滚动，bench 保留原主题和自身滚动；离开该路由后恢复网关普通页的内容宽度、统计卡片和滚动。

bench 导航项不拆分中英文标签；宽度不超过 1440px 时导航独立一行，不超过 920px 时顶部区域单列、隐藏品牌副说明并允许整项换行。表格保持水平滚动和内容自适应高度，超出 1px 的装饰线不能触发纵向滚动条。静态 CSS 更新时同步 index.html 的样式版本参数，避免缓存保留旧布局。

停机/备份/离线导入只作用于本部署，保留持久数据。离线导入默认 dry-run，来源幂等，拒绝凭据，账号停用、旧活动 run 停止，不恢复旧调度；真实接管不能让旧、新系统同时刷新同一账号。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 新环境未指定时区 / 已保存 UTC 画像 | 洛杉矶＋美国英语 UTF-8 / 沿用 UTC，展示与执行一致 |
| worker_env 或 HOME settings.env 含旧 ja_JP 值 | 按已固化画像覆盖 TZ/LANG/LC_ALL，其他 env 保持 |
| `.claude-home` 空目录 / 非空或未知链接 | 只移除空目录 / 保留内容与链接 |
| UID1000 读取管理脚本 / 执行 collector | 拒绝读取 / 允许本地执行 |
| API 活动或排队，普通 CLI 认领 | 共享认领，不关闭 API 入场 |
| 两个 CLI 同账号竞争 | 只认领一个；低优先级养号顺延 |
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
| 桌面或窄屏打开环境与任务 | iframe 全宽，底边贴合视口；标签保持横排，外层不产生额外滚动 |

### 5. Scenarios and Examples

- 正常：首次未指定时区使用洛杉矶；改名或重建后沿用已保存值，旧 worker_env 不影响实际 locale。
- 错误用法：只设置容器默认 LANG，却在 exec 注入旧日文 LANG/LC_ALL。正确做法：所有实际 CLI 入口与 HOME settings.env 从画像同源覆盖。
- 正常：API SSE 运行时启动养号 CLI，取消 CLI 后继续收到新 API 数据；同账号第二个 CLI 仍需等待。
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
- 错误用法：把 bench 放进网关的 max-width 容器，叠加统计卡片和 iframe 的 `100vh - 100px` 高度。正确做法：环境路由独占导航下方工作区，flex 根据实际导航高度分配 iframe 空间。

### 6. Tests Required

- Rust `cargo fmt --check && cargo test`：画像/改写、weighted FIFO/RPM、共享/排他租约、旧记录/过期/重启、绑定校验、原始字节/有序头/SSE取消、不重放；回环临时 CA 验证 HTTPS 正常响应及错误证书/主机名拒绝。测试 CA 不进入正式客户端。
- Python orchestrator 回归：原快照与 session 恢复、旧 token/绑定保护、并行与安装续租、证据/游标分代、统计不重复、错误链接拒绝、鉴权和永久额度门禁。
- `images/account/test_passthrough.py` 与 network-context 回归：HTTP CONNECT、SOCKS5/H 认证、IPv4/IPv6/域名、字节保真、代理失败无直连、静默关闭、跨空闲窗口单向活动，以及 PID/ACK/mode/source 归属。
- 环境回归：默认 LA/en_US、显式 UTC/Tokyo、既有画像和页面 GET 不分配；真实 Runner → AccountRuntime 启动、HOME settings.env、登录与续聊使用同源值；实际 UID1000 locale/date/ls 符合设置。
- 文件权限回归：UID1000 不能读取四个 root 脚本及 /sidecar，仍能执行 collector；root 初始化、版本准备、监听切换与 Recorder 保持；空目录清理不删除非空目录、未知链接或主 session。
- profile/project 回归：独立随机画像、时区-locale 配对、重建固定、legacy 不自动迁移、reprofile 全部前置条件/历史门禁迁移/凭据保留/成功后不可重复；容器内项目顶层只出现匿名目录，项目内部没有 `.bench-*`、`.claude-home`、刷新控制或系统 Stop hook。
- 目录信任回归：实际 `_project_view()` 写入当前 cwd 的信任标记，同时原账号 userID/OAuth 和其他项目配置保持；生产验收必须观察真实会话响应或工具调用，不能只凭 runs.status=running 宣称题目已执行。
- Stop hook 回归：调用实际 start_run 生成 driver，执行其中 Node 设置片段，断言不注入 Stop；执行生成脚本的完成判定函数，在没有 Stop 信号文件时仍识别最终 assistant。保留 shell 语法校验，不能靠给 runtime 树开放写权限消除错误。
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
- 已有 `runtime/identity.json` 的 JSON、来源、冲突标记、设备格式及账号归属均须校验；已验证版本的本地设备与旧观察不同仍阻止同步，不能覆盖证据。未知版本只接受已有正式请求观察。
- 同步按 owner → profile → environment 锁序读取；环境 GET 尝试非阻塞取得同序锁，维护时返回待核对状态，不创建／唤醒环境、不生成证据文件。身份状态必须反映实际校验，不只检查文件存在。
- cc2api 仍要求内部服务证明及合法环境；本地来源必须与 canonical_env.version 和 version_base 均为 2.1.293 精确匹配。已有设备不自动替换。
- 已绑定重授权成功返回 `credentials_synced:true` 与原绑定 ID；未绑定 v3 保存返回 `credentials_synced:false, cc2api_account_id:null`。浏览器授权完成不代表保存成功，首次绑定仍须显式同步。

### 4. Validation & Error Matrix

| 条件 | 结果 |
|---|---|
| 2.1.293 登录产物齐全，无任务／无 Recorder 文件 | 可导出原设备并同步 |
| userID 缺失／类型错误／非 64 位小写 hex，或 UUID 不符 | 409，准确错误，不替代身份 |
| 历史观察损坏、未知来源、冲突或账号不符 | 409，保留原观察 |
| 未验证版本且无请求观察 | 409，提示版本身份来源未验证 |
| 来源与版本不符、缺内部服务证明 | cc2api 401，不创建账号 |
| GET 遇到维护锁 | 显示设备身份待核对，不等待维护完成 |

### 5. Scenarios and Examples

- 正常：官方 2.1.293 登录后按原生 TLS 模式显式创建或关联，cc2api 保存同一 userID；旧 sync API 保持兼容，已绑定重授权更新原账号凭据。
- 基础：未绑定账号重授权仅保存本地，页面明确尚未关联；未知版本有历史请求观察时沿用旧来源。
- 错误用法：为了补身份让用户反复跑普通任务，或直接用 machineID 兜底。正确处理：对已验证版本读取官方持久 userID，并保留所有冲突保护。

### 6. Tests Required

- `test_account_runtime.py`：无任务／无抓包导出、缺失及错误类型、UUID 不符、损坏／冲突观察、未知版本、GET 不唤醒及维护锁释放。
- `verify_cli_quota.py`：真实官方 2.1.293、不同的合成 userID／machineID、两条本地请求身份相符；采集前后请求完全一致且零 usage，Docker network=none。
- `verify_reauth_stack.py`：空 runs 表、无 identity.json，经正式同步 API 创建及绑定后核对网关 device_id；真实页面重授权后检查两端 DB、profile、AT-only HOME、回执、原账号／设备／策略和可见结果提示。
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

- 页面未关联时显示“创建 cc2api 账号”“关联已有账号”，已关联时显示“更新进程指标”；“重新授权”保持独立。关联选择从养号表单移出，后者只保存养号/额度。按钮状态不能替代服务端绑定/身份/占用校验。
- 创建只接受未关联账号；匹配到现有身份返回冲突及关联提示，不自动切换。关联接受显式目标，只匹配该账号，不创建；按原所有权保护镜像 cc2api 权威凭据，保留养号和目标策略。新 UI 不再调用 `/cc2api/sync`，旧 sync 和 warmup 绑定字段保持兼容。
- 真正创建的载荷显式设置 `billing_mode="rewrite"`、`upstream_session_pool_enabled=true`、`upstream_session_pool_size=4`、`upstream_session_refresh_policy="owner_only"`、`concurrency=4`、`rpm_limit=50`。TTL 时长沿用默认 60 分钟；不修改 cc2api 手工创建的全局默认，不覆盖关联、指标更新、重复兼容同步或重授权后的既有策略。
- 指标更新持有 owner → profile → environment 锁序，仅核对代理配置，不能调用 `_sync_proxy` 回写代理或解析/刷新 OAuth。内部服务在排他配置门禁下拒绝活动/等待请求；不为指标写入 quiesce/停止在途发送器。存储只条件更新原身份的 `canonical_process/updated_at`，不能把旧 Account 副本整行写回而覆盖轮换后的凭据/策略。
- 实际 cgroup v2 `memory.max` 或 v1 `memory.limit_in_bytes` 提供 RAM 上限；零只表示明确的无限制。读取失败不能当作无限制，导入须与固化 RAM 预算交叉核对，不能把 RAM＋swap 或容器占用当作 RAM 限制/RSS。
- root 监督循环每两秒只读 procfs；只采 UID1000、root 所有且组/其它用户不可写、已完成版本缓存中的原生 `/cli/<version>/node_modules/@anthropic-ai/claude-code/bin/claude.exe`。核对进程启动时刻防 PID 复用，不读取命令正文或环境变量，不把 Node 探针/发送器当 CLI。
- Docker 默认无 SYS_PTRACE；仅在读 exe 链接时匹配账号 fsuid/fsgid，立即恢复后由 root 核对缓存，不能增加容器权限。root 私有 `runtime/process-metrics.json` 使用 schema=1、环境归属及最多 32 个版本，私有锁内原子写入、0600、文件 fsync；坏记录保留并拒绝导入。采样不发请求、不启动额外模型任务，普通观察失败不停止 API。
- `canonical_process.observation` 固定 `source="v3:procfs:cli"`、32 位小写 hex `environment_id`、精确 `cli_version`、UTC 秒 `observed_at/sampled_at`、整数 `sample_count`、字节 `rss_bytes/rss_min_bytes/rss_max_bytes`。内存/样本计数必须非负且小于 2^53；时间有限且不超当前 60 秒，采样时刻不晚于观察时刻。count=0 时采样时间及三个 RSS 都为 null；count>0 时它们必须齐全且 `0 < min <= rss <= max < 2^53`。
- 容器上限可独立导入；RSS 没样本显示“未采集”，有样本显示真实时间。v3 observation 不填旧兼容默认堆/CPU/RSS 范围，上游只发送有依据的 constrainedMemory 和可选 rss，内部来源元数据不进入遥测。普通旧账号画像沿用既有兼容，已有 v3 账号通过独立按钮补齐，不批量迁移设备或凭据。
- 完整转发验收使用真实调度器、空 SQLite、随机部署、两账号发送器、HTTP CONNECT/SOCKS 与本地 HTTPS 上游；来源 IP、合成标记、发送器 request_id 和响应哈希须可关联。正式 messages JSON/SSE、实际 CLI/API 并行、取消收口和失败关闭分别验收，不能以 ClientHello/502 或 runs-stream 代替成功业务响应。
- 隔离构建仅显式启用 Cargo `v3-verification` 与 Docker `verification-control/verification-account`，临时根位于 `/run/v3/verification-ca.der`，仍验证签名与主机名。正式 control/account 不依赖这些阶段，不含该读取路径，不新增运行时 CA/跳过校验开关。测试镜像/清单不发布；生产非模型 HTTPS 与真实模型推理分别报告，受限账号不用于模型探测。

### 4. Validation & Error Matrix

| 条件 | 结果 |
| --- | --- |
| 已关联时创建/关联、创建遇已有匹配、关联目标不存在 | bench 409，不自动创建/改绑 |
| 非 v3 或未关联时更新指标 | 409；不可用账号 404 |
| 代理不一致、来源/版本/样本/内存预算错误 | 409，不改目标进程、代理或凭据 |
| 内部证明缺失/伪造 | cc2api 401，不写库 |
| 活动/等待 API 或 CLI 维护占用 | 内部拒绝，原数据与在途流保持；bench 返回受控 409/502 |
| 新账号无 CLI 样本 | 上限准确，RSS null / 未采集 |
| 发送路径、代理、证书/主机名、绑定/代次/目标错误 | 明确失败，无直连回退和不安全重放 |

### 5. Scenarios and Examples

- 正常：未关联账号点击创建，六项为 rewrite/开启/4/owner_only/4/50；已存在则显式选择关联，保留管理员自定义 strip/关闭/2/mapped_request/2/17。关联后更新指标只改进程字段。
- 基础：`constrained_memory=1610612736`、`sample_count=0`、`sampled_at/rss_*=null`，页面显示容器上限 1.50G 与 CLI RSS 未采集；之后真实 CLI 样本补齐 RSS 和时间，停止/重启不伪造新样本。
- 错误用法：点击“更新进程指标”顺便 resolve OAuth，或把缺失堆数据填成静态默认值。正确处理：独立身份/观察载荷与条件列更新，未知项不发送。
- 错误用法：首个 session ID 未改变就判定池无效，或丢弃 urllib3 读取器后再测试“在途”拒绝。正确处理：前四个属主可保留 ID，第五个映射到四成员内；保留读取器并先断言 active>0，再取消及核对上游 completed=false。

### 6. Tests Required

- `test_process_metrics.py`：真实跨 UID procfs 路径及文件身份恢复、v1/v2/无限/损坏 cgroup、官方缓存/权限/PID/RSS、空样本、持久化及归属冲突；`test_account_runtime.py` 断言预算核对和原身份导出。
- `test_main.py`：创建冲突不刷新/关联、六项载荷、显式关联不创建/改养号、未关联指标拒绝、更新不读凭据或改账号。Rust service/store 测试覆盖坏来源/身份/版本/样本、条件列写入与并发凭据/策略保护；identity/rewriter 测试覆盖对象及 base64 中未知堆/CPU 不外发、旧画像兼容。
- `verify_forwarding.py --build ...` 复用 canonical 冻结与联合清单；实际浏览器点击三入口、明暗与 1440/720px、官方 CLI RSS → API/SQLite/卡片。正式 `/v1/messages` JSON/SSE 响应哈希、Billing 与 5→4 session、两账号隔离、实际官方 CLI 与 API 并行、取消及全部故障场景均通过；网关专属网络命名空间的公网阻断计数为零，结束按本次精确标签清理。
- 正式镜像继续跑 `verify_stack.py --browser --reauth`，核对原 ID、AT-only HOME、完整 profile、六项策略/TTL、错误登录/取消/草稿恢复及旧哨兵。页面驱动等首次列表事件处理器就绪，避免人为并发初始查询；失败保留脱敏证据。
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
- 总 RAM/swap 来自已保存画像：network 256 MiB、sender 128 MiB、CLI 取剩余且至少 512 MiB，额外 swap 只归 CLI；Docker memswap 为角色 RAM 加其额外 swap。CPU 按 CLI:network:sender=6:1:1 分配，pids 分别为 512/128/128；CLI /tmp 为 128 MiB noexec。部署预检、容量及停止不能漏计辅助角色或放大账号总预算。
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
- 当前支持 `AuthenticAMD/23/1`（Naples）与 `AuthenticAMD/25/80`（Cezanne）。只替换 CPU 型号文本，保留创建时实际厂商、family/model/stepping、flags、数量/拓扑/频率等原文；真实硬件变化后空闲重建刷新非替换字段，跨代际迁移必须先核对，不能自动换画像。
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
| 未支持、混合或迁移后的冲突 CPU 代际 | 明确报错，保留原记录 |
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

- 单元覆盖型号之外的 CPU 原文保持、未知/混合/迁移代际拒绝、画像损坏不重生成、首次增补一次、改名/重建/legacy reprofile 保持及 CLI 待对账仍可显式维护。
- 实际 Docker 验证动态与静态 C、直接 uname syscall/CPUID、普通/fortified open、相对 openat、fopen、并发读取、Node/子进程、真实只读挂载及损坏字段 EIO；network/sender 不加载覆盖，实际资源/秘密边界保持。
- 精确官方 CLI 2.1.293 在无账号断网环境验证版本、认证状态和登录帮助，结合动态绑定证明 uname 确实走覆盖。auth status 的未登录退出码 1 不算启动失败；不能据此声称真实登录或模型交互已验收。
- 用 `run_local_verification.py` 的正式构建清单及显式旧 control/account 镜像验证 API/CLI 生命周期、重建和回退再启用，核对画像、身份及 HOME/凭据保留；记录本地启动性能及未执行的生产/真实模型边界。
