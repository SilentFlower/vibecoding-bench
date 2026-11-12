# v3 平台在线更新合同

## 1. 范围与触发

适用于 v3 的签名发行、管理页面 `/updates`、Python/Rust 共同维护门禁、独立宿主执行器和首次接入恢复。修改这些边界时，应同步核对本文与实际测试。日常操作见 [系统更新 SOP](../../../../deploy/v3/SYSTEM-UPDATES.md)；原账号归属和内核生命周期继续由 [账号运行时规范](../backend/account-runtime-v3.md) 定义。

默认每六小时检查受信目录，安装由管理员触发。宿主执行器独立于两个控制服务运行，使用固定策略和 Compose 模板。发行材料只提供受限声明。

## 2. 签名与入口

### 管理 API

浏览器沿网关会话鉴权访问 `/runtime/api/system-updates`，管理桥转到调度器 `/api/system-updates`，再以私有令牌访问 Unix socket。

| 方法与相对路径 | 请求 | 返回 |
| --- | --- | --- |
| `GET /status` | 无 | 安装能力、revision、实际组件来源、环境来源、当前操作、历史 |
| `GET /releases` | 无 | 已验签发行、目录新鲜度、检查状态及兼容结论 |
| `POST /check` | 空对象 | `202`，异步检查身份 |
| `POST /prepare`、`/install`、`/rollback` | 冻结操作 | `202`，原操作状态 |
| `GET /operations/{operation_id}` | 原 UUID | 脱敏进度 |
| `POST /operations/{operation_id}/cancel`、`recover` | `expected_revision` | `202`，原操作状态 |

核心校验签名位于 `orchestrator/system_update_contract.py`：

```python
validate_release(value: dict) -> dict
validate_index(value: dict, highest: list[int] | None = None, now: float | None = None) -> dict
validate_operation(value: dict) -> dict
compatible_data(original: dict, target: dict) -> bool
fetch_repository_file(name: str, commit: str, limit: int) -> bytes
```

首次接入使用 `python3 deploy/v3/install_system_updater.py prepare --env <配置> --release-dir <发行目录> --state-root <目录> --public-key <公钥>`；提交使用 `finalize --policy <策略>`。两者默认预览，实际执行显式追加 `--apply`。

## 3. 数据与环境合同

CI 在安装依赖及执行验证前，使用 `actions/setup-python` 显式设置 `python-version: '3.12'`，与 `images/v3/Dockerfile` 的两个正式 Python 阶段一致。验证虚拟环境和后续发行命令继承该解释器。变更次版本时应联合验证锁定依赖与正式镜像。

宿主快照测试及真实兼容恢复演练通过 `sudo` 调用同一虚拟环境解释器，匹配正式更新器的 root 权限，以读取跨进程数据库文件描述符。演练仅显式保留 `V3_SYSTEM_RELEASE_PRIVATE_KEY`，完成后把 `releases/database-compatibility.json` 归属交回 runner，供后续上传与签名发布读取。

### 受信发行

- 独立 Ed25519 密钥由 CI secret `V3_SYSTEM_RELEASE_PRIVATE_KEY` 提供。宿主保存 64 位十六进制公钥，签名原始长度为 64 字节，按原始 JSON 字节验签。
- v1 平台发行 `system-ci-*` 的必需字段为 `schema_version=1`、`release`、`sequence`、`published_at`、`platform`、`build_manifests`、`control`、`account`、`compatibility`、`data_compatibility`、`changes`、`bundle`。平台固定为 `linux/amd64`。
- 组件字段固定为 `release`、`reference`、`registry_digest`、`config_digest`、`revision`、`unpacked_bytes`、`content_sha256`。镜像仓固定为 `ghcr.io/silentflower/vibebench-v3-{control|account}`，精确来源为 `v3-ci-*`。仓库摘要、配置摘要和内容摘要分别校验。
- v1 兼容能力固定为 `updater=1`、`gate=1`、`bridge=1`、`layout=2`、`cli_install=2`、`credential_ownership=1`、`account_protocols=[1]`。
- 双库 `bench`、`gateway` 各有 `contract` 和 `rollback_compatible`。目标声明必须包含原版合同，才允许在线切换。默认策略仅认可自身合同。新增旧合同需要实际兼容验证。
- 签名目录字段固定为 `schema_version=1`、`sequence`、`issued_at`、`expires_at`、`releases`。目录和签名从同一 Git commit 获取；序号不得低于最高已接受序号。发布有效期为 30 天，校验上限为 31 天。准备和安装需要新鲜目录；回退使用独立验签的已安装历史。
- `fetch_repository_file` 只接受 `index.json|index.sig`、完整 40 位 commit 和 `1..INDEX_LIMIT` 字节上限。Contents API 仅定位固定提交下的文件路径、大小及 blob SHA；原始载荷从 Git Blob API 的 Base64 字段取得，严格核对编码、解码大小及 Git blob SHA，再执行原有 Ed25519 验签。Contents 的 raw 响应及 `content` 字段可能转换二进制签名字节。
- 清单上限 128 KiB，目录上限 256 KiB，版本说明上限 8000 字符，持久状态与操作读取上限 8 MiB。重复 JSON 字段、非有限数字和未知字段拒绝。下载采用固定 HTTPS 来源、有限重定向及有界字节数。

### 冻结操作与响应

冻结写请求精确包含以下字段，Pydantic 拒绝附加字段及布尔值冒充整数：

| 字段 | 约束 |
| --- | --- |
| `operation_id` | 规范形式 UUID，本次操作唯一身份 |
| `expected_revision` | 状态接口取得的规范形式 UUID |
| `target_release` | 精确 `system-ci-*` 发行 |
| `target_manifest_sha256` | 原始清单 SHA256，64 位小写十六进制 |
| `drain_timeout_seconds` | 整数 60～7200，API 默认 900 |

同一 UUID 与同一动作、参数重试返回原操作。复用 UUID 改动参数属于冲突。取消与恢复请求精确包含 `expected_revision`。

已接受的 `cancel_requested=true` 是单向持久意图，执行线程写阶段时必须合并该标记。排空后最后一次现场采集完成，再在与取消接口共用的锁内核对取消并持久进入 `switching`。此前接受的取消收口为 `cancelled`；进入切换后的取消返回 `409`。

已接入状态包含 `installed`、`revision`、`deployment`、`current_release`、`components`、`operation`、`busy`、`history`、`checked_at`、`check_error`；管理桥补充 `environments`。未接入返回 `installed=false` 与接入说明。公开操作包含 `operation_id`、`action`、`phase`、`created_at`、`updated_at`、`target_release`、`error`、`blockers`、`cancel_requested`、`cleanup`、`environment_results`，迁移版本额外返回 `database_snapshot`、`database_migrations`。状态额外提供 `migration_capability:bool`。

### 来源、准入与恢复

- `V3_RELEASE` 表示平台来源；`V3_ACCOUNT_RELEASE` 表示选定账号镜像来源。共享只读门禁通过 `V3_UPDATE_GATE_DIR` 接入；调度器通过 `V3_UPDATE_SOCKET_DIR` 连接更新服务。
- 账号私有 `runtime/account-image.json` 固定 `schema_version`、`environment_id`、`release`、`reference`、`image_id`、`protocol`，与真实 Docker image ID、标签及原角色归属共同核验。首次旧角色通过受控生命周期重建建立来源。
- 仅平台变化且账号内容摘要相同时，保留原账号镜像、三角色容器 ID、环境代次及内核选择。账号内容变化时逐项重建原本运行的环境；原本停止或退休的环境保留状态。
- 门禁 `admission.json` 固定 `schema_version`、`deployment`、`operation_id`、`epoch`、`phase`、`target_release`、`revision`、`created_at`；phase 为 `idle|blocked`。目录 0700、私有文件 0600，拒绝符号链接等不安全读取。接入后缺失或损坏门禁进入拒绝准入和对账路径。
- 两端活动计数覆盖响应正文 EOF、错误及断连。批次排队等待属于待认领工作；有限分派事务和实际执行计入活动。维护期间保留待认领项，释放门禁或控制重启后继续调度。
- 原工程或登录只能凭实际仍登记的有限作业续接。续接继续检查身份、时间窗口与配额；作业撤销后证明失效。
- 排空核对实际 API、jobs、executions、租约、sender、CLI 孤儿、三角色镜像及未决意图。未知活动阻断切换。排空超时和切换前取消按原操作释放门禁。
- v1 安装正常阶段为 `preparing → draining → switching → verifying → committing → cleaning → succeeded`。v2 在排空并锁定切换意图后增加 `snapshotting`；目标为 v2 时执行 `migrating`，随后进入 `switching`。失败恢复增加 `restoring_data`。单独 prepare 在 `prepared` 完成。恢复按持久意图、真实容器、配置 CAS、软件字段 CAS 与双库/身份摘要确定动作；不确定现场进入 `reconcile`。
- 账号部分恢复最多允许冻结的原版和候选两个实际镜像 ID。恢复仍要求环境、代次、epoch 以及原作业证明一致。恢复已释放的门禁前重新检查后来工作。
- `finalize --apply` 与独立执行器共用 `service.lock` 及存储维护锁。原首次接入在状态提交后、门禁释放前后中断，均可用同一发行重试收口。已完成重试保留原 `installed_at`；外来门禁和后来 revision 拒绝覆盖。
- 清理保护当前组合、最近两个完整历史组合、全部容器引用和恢复引用。只精确删除经证明的历史镜像；Docker 删除最后一个 tag 时可同步移除其 RepoDigest。清理失败记录 `succeeded_cleanup_pending`，通过原操作恢复重试。
- 宿主执行器沿既有专项运维边界修复：固定安装源码根及原、新文件 SHA256，核对无活动更新和 `idle` 门禁，停止独立服务后更换精确源码，再启动并复核原安装状态、门禁和签名目录检查。失败恢复原源码及服务。控制镜像发行与宿主执行器源码分别验收。

## 4. 校验与错误矩阵

| 条件 | 行为 |
| --- | --- |
| DTO 类型或附加字段错误 | 管理 API `422` |
| UUID、摘要、发行、等待范围或材料校验失败 | `400` |
| UUID 参数复用、旧 revision、已有活动操作、现场 CAS 冲突 | `409`，刷新状态再确认 |
| Unix peer UID 或私有令牌错误 | 执行器 `403` |
| 独立服务连接失败 | 管理桥 `503`，状态允许重试 |
| 维护期间新业务请求 | `503` 与 `Retry-After`；迟到原登录证明返回 `409` |
| 签名错误、目录回放/过期、数据合同不兼容 | 准备/安装受阻，记录具体原因 |
| 目录文件解码大小、Git blob 身份或签名不符 | 检查失败，保留上次已验证目录 |
| 准备或排空期间已接受取消；已经进入切换 | 前者保持取消意图并收口；后者取消返回 `409` |
| 未知进程、租约或角色归属 | 阻止切换，按实际阶段等待或进入 `reconcile` |
| 首次接入遇到活动服务锁 | 拒绝提交；按 SOP 停止独立更新服务后重试原 finalize |

## 5. 场景与示例

错误用法：依赖 runner 默认 Python 创建验证环境，随宿主升级到 3.14 后，锁定的 `pydantic-core==2.23.4` 安装失败。正确处理：先显式设置与正式镜像一致的 Python 3.12，再创建干净虚拟环境验证原依赖和测试命令。

正常：管理员读取 status 与 releases，用页面生成的 UUID、当前 revision 和清单摘要提交 install。下载时继续服务；排空完成后切换控制服务，验收成功持久提交并恢复准入。

边界：长响应仍在发送时，活动计数一直保留到正文结束。批次下一项在维护期间等待，当前有限执行结束后计数归零。控制重启保留原待认领项。目录过期时检查新目录；已安装历史仍按数据兼容条件提供回退。

错误用法：收到 `409` 后仅替换 UUID 自动重放原确认。正确处理：重新读取 revision、候选摘要和重建范围，再由管理员确认新请求。

错误用法：把 Contents API 返回的二进制签名作为文本重新编码，或直接信任其中的 Base64 `content`。正确处理：按固定提交取得 blob 身份，从 Git Blob API 读取原始字节，校验大小、blob SHA 及 Ed25519 签名。

错误用法：取消接口已经返回成功，执行线程随后用旧操作快照覆盖取消标记。正确处理：持久写入保留单向取消意图，并将最后一次取消核对与进入切换合为同一加锁边界。

错误用法：首次 finalize 中断后直接写 idle 门禁。正确处理：重试原 `finalize --policy <原策略> --apply`，由原发行、epoch、配置及共享服务锁证明收口。

错误用法：将整个批次等待循环计入维护活动，或以原作业证明绕过配额。正确处理：只登记有限分派和执行，续接保留其他准入校验。

## 6. 必需验证与断言

- CI 权限验证：宿主文件描述符检查采用 root，普通 runner 的 PermissionError 保持失败；同一虚拟环境解释器、明确保留的密钥变量及证据归属回交必须匹配工作流。
- CI 解释器变更：用干净 Python 3.12 虚拟环境安装 `orchestrator/requirements.txt`，执行 workflow 中两条 `unittest discover` 命令；检查设置步骤先于验证，且与两个正式镜像的 Python 次版本一致。工作流 YAML、shell 语法和 `git diff --check` 通过。
- `deploy/v3/test_system_*.py`：签名、目录顺序/时间、严格字段与大小、数据兼容、同参幂等、revision 冲突、恢复与清理保护。首次接入覆盖 dry-run、状态提交中断、释放响应中断、原 installed_at、外来门禁、后来 revision、配置 CAS、真实文件锁互斥。
- 目录读取覆盖 Contents 载荷转换、真实签名字节保留、错误编码/大小/blob SHA 及非固定来源拒绝；取消覆盖执行线程旧快照、最后一次现场采集中的取消，以及切换后的 `409`。真实 Docker 取消验收断言原控制容器保留且操作最终为 `cancelled`。
- `orchestrator/test_system_update*.py`：实际线程/文件准入、ASGI 正文结束、原登录撤销、部分恢复边界；真实 Scheduler + SQLite 验证批次等待不阻塞排空、维护抢先分派、重启续调度、原工程续接与时间窗口/被动配额拒绝。
- Rust `cargo test` 与 `cargo fmt --check`：门禁启动验证、完整 HttpBody 释放、租约与管理桥回归。Vue `npm --prefix web run build` 验证类型和构建。
- `verify_system_update_browser.py`：真实构建页面配合合成 API，覆盖桌面/移动端、确认、断线重连、409、回退/恢复、未接入；断言零脚本异常与零真实模型调用。
- `verify_system_update.py`：随机部署、独立数据根、本地 TLS 和合成密钥下验证真实 Docker 长流排空、控制复用、账号重建、停止状态保留、显式回退、健康失败恢复、部分角色恢复、独立进程中断恢复、容器引用保护与精确回收。Bookworm 二进制沿项目 Docker 构建路径验证兼容性。
- 生产首次接入、CI 私钥配置和真实发行获取由上线单另行核验。进程中断证据命名为进程恢复，宿主重启采用独立现场核验。


## Scenario: 自动数据库迁移与原操作恢复

### 1. Scope / Trigger

v3 的双 SQLite、签名发行及固定宿主执行器共同改变持久合同。适用数据库为 `bench/db.sqlite` 和 `gateway/gateway.sqlite`。gateway 的 PostgreSQL 继续使用原初始化语义。常规在线范围仅接纳已登记并完成旧程序兼容演练的迁移。

### 2. Signatures

```text
python3 -m database_migrations plan|apply|verify --operation-id <UUID> --target-version <N>
claude-code-gateway database-migrations plan|apply|verify --operation-id <UUID> --target-version <N>
python3 deploy/v3/upgrade_system_updater.py --policy <绝对路径> --source-root <核验源码根> --service <原服务> [--apply]
python3 deploy/v3/upgrade_system_updater.py --policy <原策略> --service <原服务> --recover <原UUID> [--apply]
system_schema_migrations(migration_id TEXT PRIMARY KEY, version INTEGER NOT NULL UNIQUE,
  checksum TEXT NOT NULL, applied_at TEXT NOT NULL, operation_id TEXT NOT NULL)
```

bench 默认使用 `/data/db.sqlite`，本地维护可显式传 `--database`。gateway 从原配置读取连接。宿主固定入口、参数、精确候选镜像和单库挂载，关闭维护容器网络并采用只读程序层；发行附件只提供版本声明。

### 3. Contracts

- 两库登记为 `{schema_version:1,database,steps}`；每步固定 `id,version,predecessor,checksum,engine,kind,rollback_mode`，要求连续前驱、`engine=sqlite`、`kind=schema|data`、`rollback_mode=compatible`。首版仅登记各自 `baseline.1`。增加版本需同时实现对应执行分支及演练。
- 合同为按 key 排序、紧凑 UTF-8 JSON 登记的 SHA256。Python 冻结定义使用忽略文档/注释的 AST 摘要，Rust 使用测试段之前的纯定义原字节摘要。冻结 SQL、默认值、历史画像及命名空间依赖归纯迁移模块所有，普通业务查询和页面改动保持合同。
- CLI 返回 `database,contract,current_version,target_version,steps,state,reason`；执行完成保留原台账 operation_id。已知台账摘要冲突或版本断链拒绝；旧程序读取兼容新增版本返回 `compatible_newer`。
- 旧库迁移前核验稳定账号核心字段。迁移完成且写入成功台账之前、以及已登记库 plan/apply 时，复核冻结基线的最低表/列、SQLite 亲和、主键及完整性。允许兼容新增表/列；非主键数字亲和支持历史兼容。空库沿相同初始化建立基线。
- v2 清单保留原字段，设置 `schema_version=2,compatibility.updater=2`，新增 `migrations:{protocol:1,plan,evidence}`。两个资产精确名为 `database-migrations.json`、`database-compatibility.json`，按大小和原字节 SHA256 绑定签名。计划包含两库版本、合同和完整步骤链；证据绑定候选源码、两类镜像配置摘要、旧版清单/镜像/合同及 upgrade/candidate_read_write/previous_read_write/idempotent 四项成功断言。
- v2 使用独立 `updates/v3-migrations` 通道，首发继承旧受信发行。`updates/v3` 保留 v1 及原最高序号，仅刷新时间和签名。受信新通道 ref 404 才允许读取旧通道；已有通道资产缺失直接失败。正式证据要求干净同批镜像。
- 从空闲现场关闭门禁并排空，停止双端并确认数据库 FD 退出后，保存同操作私有双库快照。回执绑定 deployment、operation_id、epoch、原发行、权限/归属及每库文件/逻辑摘要；空间预算先于迁移。默认保留最近两组完成快照，另外保护活动恢复引用，异常目录保留并报告。
- `database_snapshot` 仅公开 `state,completed_at,bytes`；`database_migrations` 按库公开 state 和 target_version。页面显示快照、迁移、数据恢复及具体阻断原因，未知值保留可见。
- `release_started` 先于实际释放准入持久化。此前失败按原 UUID 恢复同组两库和原程序；恢复意图先于暂存复制和替换，支持部分两库完成。账号重建后的六项生命周期登记以原身份和 CAS 续接，再恢复原环境。`database_restored` 先于原程序启动落盘，重启收口保护原程序后来写入。重新接单后的显式回退保留当前数据。
- 底座首次能力接入默认预览，持有独立接入锁；完整备份后发布 `updater-upgrades/<UUID>/upgrade.json`。未完成日志阻止新接入。`--recover` 默认预览，允许服务 inactive，按精确原/新源码 SHA、原策略/状态副本摘要、空闲门禁及服务归属验收，持有服务锁和存储锁后恢复原版并验证 socket。恢复再次中断继续原 UUID；后来状态、外来源码及后续接入日志触发现场保护。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 缺稳定核心字段、已登记库缺必要字段、类型/主键异常 | CLI 非零，拒绝登记成功 |
| 重复 ID、前驱断链、校验和改变、未登记结构定义 | 构建或维护验证失败 |
| 同合同仅历史许可列表变化 | 允许常规兼容安装 |
| v2 附件、来源清单或实际镜像证据不符 | 阻止准备/安装及兼容发布 |
| 快照空间不足、写入者未退出、损坏或外来快照 | 停止迁移并保持原操作恢复权 |
| 维护窗口中迁移/候选健康失败 | 同组双库及原程序恢复 |
| 已持久开放准入或存在后来操作 | 保护当前数据，按兼容回退或对账收口 |
| 底座接入中断 | 显示原 UUID，先预览 `--recover`，再显式 apply |
| 恢复副本摘要、服务、源码或后续接入记录发生外来变化 | 保留现场并拒绝覆盖 |

### 5. Scenarios and Examples

正常：旧预热版本通过 v1 底座一次接入能力后，在 `/updates` 准备并安装签名 v2；双库自动快照、迁移和验收，完成后轮换快照。

边界：bench 台账已为1而 gateway 仍为0时进程中断，使用原操作恢复同组双库。原程序已经启动后再次中断，按持久恢复标记继续收口。

错误用法：以台账存在代替结构验证，缺少 `accounts.token` 仍标记成功。正确处理：旧库核心准入、完成后最低结构复核及已登记复核均执行，缺列保持非零退出和原台账。

错误用法：底座源码替换中断后重新发起接入。正确处理：按日志原 UUID 执行 `--recover` 预览，复核后追加 `--apply`；服务停机沿同一恢复路径执行。

错误用法：CI 测试依赖终端额外设置 PYTHONPATH。正确处理：脚本自举所属项目路径，并以 `env -u PYTHONPATH` 验证 workflow 默认入口及独立 discover。

### 6. Tests Required

- `verify_database_definitions.py`：DDL 所有权和冻结摘要；业务模块 DDL、触发器/视图及纯定义外部依赖必须被拒绝。
- 两库迁移测试：空库、旧库、重复执行、台账冲突、兼容新增；缺列/类型/主键异常拒绝登记。Python 增量事务失败保持数据与台账。
- `test_system_database.py`、`test_system_migrations.py`：WAL、空间、损坏/外来快照、部分复制/替换恢复、保留轮换、同合同准入及开放后的数据保护。
- `test_system_upgrade.py`：来源/服务归属、失败恢复、源码/策略/状态替换真实进程终止、按 UUID 预览、恢复再次中断、重复恢复及后来状态保护。
- `verify_database_compatibility.py`：真实旧库→候选→原程序读写、重复迁移及快照恢复；结果绑定精确镜像及合同。默认环境独立入口必须工作。
- `verify_system_update.py --migration-manifest <候选清单>`：真实旧底座接入、固定源码独立导入、双库半完成中断、恢复后启动中断、健康失败、账号部分角色恢复、显式回退及最近两组快照断言。
- 页面真实浏览器覆盖迁移计划/阶段、未知状态、断线重连、390px 以及冻结 UUID/revision；合成环境真实模型请求计数为0。


## Scenario: 平台语义版本展示与旧发行兼容

### 1. Scope / Trigger

修改正式发行元数据、前端版本展示和构建/发布输入时适用。

### 2. Signatures

- `deploy/v3/platform-release.json` 精确字段为 `schema_version:1`、`version:string`、`changes:string`。
- `read_version(path)` 校验规范 `v<major>.<minor>.<patch>` 及说明；`signed_changes(metadata)` 生成受控首行 `平台版本：v1.0.0` 与正文。
- `ensure_forward_version(current,previous)` 检查受信前后发行；前端使用 `VITE_PLATFORM_VERSION` 构建输入。

### 3. Contracts

- 新发行首版 v1.0.0；修复递增补丁，功能递增次版本。元数据为唯一维护源，build 将版本传入 frontend Docker 阶段，且将元数据纳入源快照摘要。
- 发布端从同一元数据生成现有签名 changes，GitHub 标题使用可读版本。原 release/sequence/镜像/清单摘要及 v1/v2 字段集合保持原合同。
- 发布前从原已签目录取得最新完整清单并核对大小、摘要及格式；旧目录按签发时刻验证，允许正式发布刷新过期通道。不同源码使用相同或更低语义版本拒绝；同源重跑允许相同版本。
- 当前平台版本来自控制镜像中构建的前端；可用版本从已验签说明首行提取。独立构建缺输入时使用已有受信信息或历史构建语义。
- 旧发行字节保持可追溯，缺元数据展示历史构建日期及技术详情；CLI 和内核按账号分别展示实际来源。
- 更新列表默认突出当前与最新可用项，历史折叠，同一列表只保留一个详情展开。安装确认冻结真实 release、摘要、revision 及显示标题，轮询保持原参数。
- 时间按浏览者时区显示，技术详情保留原始标识；UTC 存储及安装参数沿用。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 非规范版本、空说明、未知元数据字段 | 构建/发布拒绝 |
| 不同源码复用版本、版本倒退 | 发布拒绝 |
| 原清单大小或摘要不符 | 发布拒绝 |
| 历史发行缺可读版本 | 日期及技术详情 |
| 目录不新鲜或安装现场变化 | 原更新合同要求重新检查/确认 |

### 5. Scenarios and Examples

- 正常：v1.0.0 → 修复 v1.0.1 → 功能 v1.1.0；同一源码 Action 重跑保留原版本。
- 边界：原系统仍使用严格 v1/v2 清单，版本信息沿受信 changes 兼容展示。
- 错误用法：把 ci 编号直接改名后作为安装参数。正确处理：语义版本用于展示，安装使用原受信身份。

### 6. Tests Required

- `test_system_platform_version` 覆盖实际元数据、历史说明、递增和不同源码拒绝；`test_system_release` 验证原签名与字段合同。
- Vue/TypeScript 生产构建和 `verify_management_ui.py` 覆盖当前/最新/历史、单展开、取消零写入及两个浏览器时区。


## Scenario: 构建与手动发布解耦及 v3 升级连续性

### 1. Scope / Trigger

修改 v3-build.yml、v3-release.yml、两个 Python 发布入口、发行序号或固定宿主源码包时适用。v3/Flower2API 按小版本沿原部署演进。

### 2. Signatures

- `release_ci.validate_publish_source(build: dict | None = None) -> str`：校验来源，返回当前 `ci-<run_id>-<attempt>`。
- `publish_system_release.check_signing_key() -> None`、`python3 deploy/v3/publish_system_release.py --check-signing`：核对实际手动入口和 Ed25519 签名配置。
- `gh workflow run v3-build.yml --ref flower2api`：只构建验证。
- `gh workflow run v3-release.yml --ref flower2api -f publish=true`：明确发布。

### 3. Contracts

- v3-build 的 push/目标 PR 分支为 v3、flower2api，另有手动构建。权限 contents:read，checkout 关闭持久凭据；仅测试、构建两镜像并上传本地清单，发布副作用为零。
- v3-release 仅 workflow_dispatch；布尔 input `publish` 默认 false，必须明确选中。本仓 v3/flower2api 分支可发布，同一 runner 冻结实际 SHA 并重新验证构建，真实旧库兼容演练通过后才推镜像。只有发布 job 取得 contents/packages 写权限。
- 两个 Python 发布入口共用来源校验：`GITHUB_ACTIONS=true`、`GITHUB_EVENT_NAME=workflow_dispatch`、`V3_PUBLISH_CONFIRMED=true`、精确 repo/ref，以及 `GITHUB_WORKFLOW_REF=<repo>/.github/workflows/v3-release.yml@<ref>`。run/attempt 为正整数串、SHA 为40位小写hex；清单批次、revision和clean标记必须匹配。
- 发布预检要求有效 `V3_SYSTEM_RELEASE_PRIVATE_KEY`，用实际 DER 格式确认 Ed25519。缺配置/错误类型在构建及推送前失败。签名私钥仅供手动发布侧使用。
- 工作流拆分后的 run_number 不用作发行序号；从同信任根已验签目录主序号最大值加1，第二项使用实际 attempt。历史目录按签发时刻校验原合同，主序号达到2^53-1时拒绝新发行。完整附件后才普通 fast-forward 推进目录，保留原版本递增与批次不可覆盖规则。
- 原仓库、v3镜像名、system-ci/v3-ci身份、updates/v3-migrations及updates/v3语义、信任根与双库兼容合同保持。管理员从原系统更新页准备/安装；旧底座按既有SOP原地补齐能力。
- `install_system_updater.SOURCE_FILES` 含 manage 的直接依赖 platform_version.py、release_ci.py；固定源码复制后必须能在仓库外独立导入。
- 旧 main 的 docker-publish 只接受手动事件+main ref。触发规则按所在分支生效；修复需同步到 v3/main，新手动入口需在默认分支 main 注册。分支同步、正式发布和线上安装分别验收。

### 4. Validation & Error Matrix

| 场景 | 结果 |
| --- | --- |
| push/PR/构建入口调用发布脚本 | ValueError，Docker/GitHub发布副作用为零 |
| 错误分支、仓库、SHA、工作流或缺确认标记 | 发布前拒绝 |
| 缺私钥、密钥非Ed25519 | 预检失败 |
| 历史目录主序号700，新工作流run_number=1 | 发行主序号701，原发行继续可读 |
| 历史签名损坏或序号达到上限 | 正式发行写入前失败 |
| 附件上传或目录并发推送失败 | 原目录受保护，已完成事实保留，无force覆盖 |
| 更新器源码包缺直接依赖 | 独立导入回归失败 |

### 5. Scenarios and Examples

正常：push flower2api→构建通过→手动发布→原v3管理员检查并安装后继版本。

边界：迁移通道首发承接原v1签名历史，并在原序号之后生成新序号。

错误用法：仅修改flower2api中的工作流就宣称v3/main远端自动发布已关闭。正确处理：将精确修复同步至各目标分支并分别验证实际触发规则。

### 6. Tests Required

- test_publication：两分支手动来源通过，自动/未确认/错误入口零Docker副作用，原批次与digest保护成立。
- test_system_publish：真实临时签名、高历史序号、迁移通道首发继承、签名损坏、目录竞争和安全整数上限。
- test_system_workflow：实际YAML事件、权限、零发布步骤、签名预检/兼容演练顺序，以及固定源码包仓库外独立导入。CI测试依赖固定PyYAML 6.0.3。
- actionlint覆盖三个工作流；原系统更新、双库合同及宿主恢复回归继续通过。
