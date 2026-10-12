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

管理租约输入为 `operation: string`、`owner: string`、`generation: string | null`；操作为 `prepare-cli`、`prepare`、`claim`、`heartbeat`、`release`。查询返回 `lease`、`active`、`waiting`；租约包含 `owner`、`generation`、`expires_at`（UTC 秒）、`phase`、`exclusive`，TTL 为 30 秒。旧记录缺少 `exclusive` 时默认 `true`。

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

### 6. Tests Required

- Rust `cargo fmt --check && cargo test`：画像/改写、weighted FIFO/RPM、共享/排他租约、旧记录/过期/重启、绑定校验、原始字节/有序头/SSE取消、不重放；回环临时 CA 验证 HTTPS 正常响应及错误证书/主机名拒绝。测试 CA 不进入正式客户端。
- Python orchestrator 回归：原快照与 session 恢复、旧 token/绑定保护、并行与安装续租、证据/游标分代、统计不重复、错误链接拒绝、鉴权和永久额度门禁。
- Recorder 与部署回归：请求归属冻结、ACK/身份、冲突预检、准确资源归属、停机、备份和导入幂等。
- 资源/发布回归：1536m＋2048m 实际 Docker 限额，默认/旧缺字段、非法无限值、RAM/swap不足、已固化预算拒绝；当前 Action 来源/attempt、第一/第二件推送失败无完整清单、错误digest/包拒绝、本地标签不覆盖，跨 store ID相同配置可核对。
- actionlint 核对 ref、权限与 artifact；实际本地 registry 的 push/pull、归档 config 哈希以及双镜像 save/load 核对。CI/GHCR发布结果与指定服务器实时预检/健康/旧服务不变在发布后验收，不能以本地替身称其已完成。
- 联合重建后串行跑 `run_local_verification.py --manifest ...`、`verify_stack.py --manifest ... --browser`：实际运行中的合成 CLI、同 run 第二代、API 长流与新增 API、CLI 取消/重启/Recorder故障保留 API、tmux 重连、两账号传输隔离、旧哨兵及数据库不变。
- 校验冻结源码哈希和最终输入一致，标明平台、失败日志、测试替身及未执行项。真实 CLI OAuth/实际主会话/额度恢复、公网全链路与同宿主压力由隔离部署负责人后续验证；arm64 发布前在对应环境验证。不能用本地 mock 宣称这些真实验收已完成。
