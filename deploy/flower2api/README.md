# flower2api 部署

部署源码位于 `deploy/flower2api/`，日常入口为 `scripts/flower2api-stack`。原 `scripts/v3-stack` 继续转发同一组参数和退出状态。固定宿主包、镜像及更新通道沿用已有 v3 身份，支持现有实例持续升级。构建与发布入口见 [系统更新 SOP](SYSTEM-UPDATES.md#构建与手动发布)。

本轮交付管理和账号两个镜像。管理镜像分别启动 gateway 和 orchestrator；每账号一个固定逻辑环境，包含 network、CLI、sender 三个角色容器（共 3N+2 个容器），账号角色没有宿主端口。原部署不会自动迁移或切流。

```bash
python3 deploy/flower2api/manage.py build --release local-20261012 --manifest releases/v3-local-20261012.json
cp deploy/flower2api/example.env /absolute/path/v3.env
# 填写独立数据目录、两个镜像标签、清单绝对路径及至少 32 字符的密码/秘密。
chmod 600 /absolute/path/v3.env
python3 deploy/flower2api/manage.py check --env /absolute/path/v3.env
python3 deploy/flower2api/manage.py up --env /absolute/path/v3.env
python3 deploy/flower2api/manage.py status --env /absolute/path/v3.env
python3 deploy/flower2api/manage.py stop --env /absolute/path/v3.env
python3 deploy/flower2api/manage.py backup --env /absolute/path/v3.env --backup-dir /absolute/path/new-v3-backup
```

建议端口 18080 只是默认值，实际启动前必须空闲。默认绑定 127.0.0.1；远程访问按现有安全反代配置接入这个新端口。内部账号和调度器服务只在独立 Docker 网络通信。

gateway 显式使用 `TZ=Asia/Shanghai`，峰值预热的小时配置按北京时间解释，例如 `4,6` 在每天 04:10、06:10 触发。账号容器继续使用各自保存的时区。

每个构建批次使用唯一 `v3-<release>` 标签。清单记录父仓和子仓提交、冻结源码内容哈希、工作区是否有未提交修改、平台、默认 CLI、布局与传输版本及两个镜像的本地 ID（`digest`）与原始配置哈希（`config_digest`）；启动逐项核对标签、角色、批次和镜像身份。不得用旧 latest、混用批次或覆盖清单。本地构建不会推送镜像。`scripts/flower2api-stack` 提供同一组命令的短入口。

## GHCR 发布与远程交付

`v3-build.yml` 在 v3/flower2api 的 push、目标分支 PR 或手动触发时执行合同验证和两镜像构建，上传本地清单。该入口使用只读权限，发布操作为零。

正式交付由 `v3-release.yml` 的手动入口执行：选择 v3 或 flower2api，明确勾选 `publish`，冻结当前提交并重新验证、构建，完成真实旧库升级和恢复演练，再发布 `ghcr.io/silentflower/flower2api-control`、`ghcr.io/silentflower/flower2api-account`。统一标签继续为 `v3-ci-<run_id>-<run_attempt>`。签名私钥为必需配置，缺失时在构建前失败。本版建立 Flower2API 正式维护基线。当前旧来源和已签材料用于首次交接与失败恢复；现有单部署首次名称切换见[系统更新 SOP](SYSTEM-UPDATES.md#单部署镜像与容器名称切换)。

现有 v3 实例沿原“系统更新”页面安装后继版本，继续使用原部署标识、数据根、账号身份及更新信任根。更早底座按[系统更新 SOP](SYSTEM-UPDATES.md)在原部署补齐能力。Flower2API 按后继小版本持续演进。

构建、显式发布和管理员安装是三个独立动作。精确入口、分支生效及默认分支注册说明见[系统更新 SOP](SYSTEM-UPDATES.md#构建与手动发布)。

只有两个镜像都推送成功并取得仓库 digest 后才保存发布清单。`digest` 是构建机 Docker 的本地 ID，可能指向 OCI 索引；`config_digest` 根据归档原始配置字节计算，`registry_digest` 则是推送的仓库 manifest/索引 digest。不同 Docker 存储实现的本地 ID 可以不同，启动仍必须匹配清单固定的配置或 OCI 根及相同平台。Action 的 `v3-release-<run_id>-<run_attempt>` artifact 保存发布清单、同批压缩镜像包及其 SHA256/大小，保留 14 天，不包含部署配置或账号资料。

```bash
# 从对应 Action 下载同批 artifact，先保存发布清单。
scripts/flower2api-stack pull --manifest /absolute/path/v3.json
# 首次包默认私有、无法匿名拉取时，使用同一 artifact 的镜像包。
scripts/flower2api-stack load --manifest /absolute/path/v3.json --bundle /absolute/path/v3-images.tar.gz
```

pull 按 `registry_digest` 固定下载，核对配置 ID后建立清单中的标签；load 先核对包名称、大小和 SHA256。随后两者都执行角色、批次、提交与平台核对。首次发布不自动修改包可见性；离线交付不需要服务器保存 GHCR PAT。env 中的两个镜像引用必须和发布清单完全一致。

## RAM 与 swap 预算

账号可在 cc2api 选择 `request_backend=native293`。该方式使用固定 2.1.293 单文件执行内核，在独立 sender 角色中按需启动进程。构建会下载并校验固定 beta 二进制；发布前可设置 `V3_NATIVE_RUNTIME_ASSET` 指向同 SHA256 的本地候选。联合清单记录其版本、大小和摘要，镜像再次校验分发文件。

账号默认 `V3_ACCOUNT_MEMORY=unlimited`，原生方式可省略 `V3_NATIVE_SENDER_MEMORY`。显式有限账号需要配置该发送器预算。标准并发 3 对应最多 6 个 Haiku 进程，已验证配置为 `1536m`，账号总 RAM `4g` 时 CLI 剩余 2304 MiB。有限模式的sender和network使用各自有限RAM，额外swap只交给CLI。原生池的 HOME/config/cwd 位于 UID 1001 独占的 `/native`，与 CLI 角色的 HOME 分离。池内共享经SHA与封存校验的只读执行映像，进程保持独立堆和上下文。额外进程空闲300秒（5分钟）后回收并保留1个暖进程。既有隔离V3六路实测峰值约646 MiB，1536 MiB限额内OOM为0，回收后sender约189 MiB。

`V3_NATIVE_PREWARM_ACCOUNT_ID` 默认为空。设为单个网关账号 ID 后，orchestrator 启动时尝试用空余容量提前启动该启用的原生账号，并准备一个 worker。首条业务占用唯一进程时，有足够并发额度则后台准备第二个。预热零模型调用，额外空闲进程仍按原时限回收。容量不足或账号需要维护时跳过后台启动。

有限模式的最低sender预算为 `256 + 192 × 2 × 标准并发` MiB。bench 创建账号默认标准并发 4，需要至少 `1792m`；使用已验证的 `1536m` 时，将该账号标准并发显式设为 3。账号总 RAM 还须覆盖 network 的 256 MiB 和 CLI 最低 512 MiB。

`V3_NATIVE_CRIU` 缺省及空值为 `1`，显式 `0` 关闭。账号选择缺省开启，管理员可在环境卡片关闭或空闲应用设置。支持 CRIU 的账号镜像通过受信任控制器创建同账号零业务热模板，新增进程优先恢复。配套内核需要恢复绑定协议 1，默认镜像内置 beta.6。恢复最低 sender 内存额度为 `256 + (192 + 108) × 2 × 标准并发` MiB，标准并发 3 为 `2056m`。额度不足时继续普通启动，业务最低额度仍为 `256 + 192 × 2 × 标准并发` MiB。内存无限模式通过静态额度条件，实际容量受共享宿主限制。卡片显示实际入口、模板状态及回退原因，旧遥测显示待核对。模板快照含账号身份数据，存放于 root 专属目录。

新隔离环境CLI、sender、network的CPU默认值分别为 `1.5`、`1.5`、`0.5` 核。使用 `V3_ACCOUNT_CLI_CPUS`、`V3_ACCOUNT_SENDER_CPUS`、`V3_ACCOUNT_NETWORK_CPUS` 独立覆盖。已保存的 `cpu-resources.json` 策略优先，旧 `V3_ACCOUNT_CPUS=2` 保留兼容用途。

CRIU 控制器单独启用受限 capability 集合和恢复所需的 seccomp 配置。业务 sender 与 worker 保持 UID 1001、capability 为零、NNP 与业务 seccomp 过滤。权限清单、固定构建来源、内核要求及回退步骤见 [CRIU 操作说明](../../services/runtime/native/criu/README.md)。启用属于部署权限变更，应按上线流程执行。

后端配置来自网关账号 runtime config。模式或资源布局改变时，环境无活动作业才允许重建。缺能力或预算时准备失败。空闲时切回 `legacy` 会恢复原 sender 布局。

`V3_ACCOUNT_MEMORY`缺省或空值为 `unlimited`，三个角色及派生评审共享宿主RAM和swap。显式有限值是每账号RAM上限，`V3_ACCOUNT_SWAP` 是额外 swap 上限，默认 `0` 保持禁用。Docker 的内存加 swap 总上限由两者相加生成，账号首次保存预算；历史环境缺 swap 字段时保持关闭。部署选择unlimited后，旧有限账号在下一次空闲准备或重建时解除内存限额。活动CLI、API和评审继续原环境，迁移顺延；停止账号保持停止。显式有限部署值继续沿用已冻结预算。身份和HOME保持。隔离布局 2 在原总额度内预留 network 256 MiB、sender 128 MiB，剩余分配 CLI；额外 swap 只分配 CLI。CLI 至少需要 512 MiB，总预算不足时拒绝启动。1536 MiB 账号的 CLI 实际 constrainedMemory 为 1152 MiB。

有限内存部署的可选起步配置：`V3_ACCOUNT_MEMORY=1536m`、`V3_ACCOUNT_SWAP=2048m`、`V3_MAX_ACTIVE_ACCOUNTS=1`，RAM 1.5 GiB，额外 swap 2 GiB，总额度 3.5 GiB。部署预检分别要求可用 RAM 至少为账号预算加可配置余量 `V3_MEMORY_HEADROOM_BYTES`（默认 256 MiB）、空闲 swap 足够覆盖活跃账号额度且 Docker 支持 swap 限额；显式更高的 `V3_MIN_FREE_MEMORY_BYTES` 仍生效。显式4GiB、单账号配置要求至少4.25GiB可用RAM，swap不能代替物理余量。默认无限模式继续核验宿主余量，尚未迁移的有限环境继续计入实际预算。起步上限不代表真实 CLI 的峰值已经验证。

首次使用空目录；不复制旧账号有效 RT。每账号 HOME、CA、工作目录、CLI 版本缓存和 Recorder 证据归属保存在 `bench/environments/<环境 ID>`。停止固定容器保留目录和容器，重启服务先对账遗留执行。停止入口按产品及部署标签收口，不 prune Docker、不删除数据或旧网络。

同一部署可重复 `up` 更新自有管理服务，外部资源冲突仍拒绝。需要停机备份的正式升级先 `stop`，再 `backup` 到全新且独立的目录。**默认精简备份**保留数据库、持久 HOME 身份/凭据、工作目录、任务成果、执行/恢复证据与部署配置；仅排除明确的 npm 下载缓存，以及已经证明可按固定来源恢复的 CLI 程序和当前镜像项目内容。缺少可信恢复元数据的旧程序、浏览器、未知 HOME 缓存及历史项目版本仍会保留，不能只按目录名删除。`--full` 显式保存全部可重建程序与缓存。

备份采用 SQLite backup API，保留 WAL 中的事务，目录权限为 0700。`backup-files.json` 保存文件字节摘要、权限/归属、链接、排除范围及依赖恢复来源；CLI 的公开依赖锁、程序摘要与 root 安装回执保留在恢复清单中。新快照必须在独立目录实际复制，校验文件、身份、配置和数据库后，才发布完成标记并轮换同父目录、同部署、同数据根的旧完整或精简副本，仅保留最近一份。失败保留原恢复点，未知、跨部署、未完成目录及目录链接不参与轮换。tmux 等 Unix socket 不进入快照，普通符号链接原样保留，不跟随其目标。精简恢复需按清单重新准备程序依赖；整盘丢失后不保证零下载恢复全部工具。备份含账号秘密，须按当前数据目录权限保管。

```bash
# 默认精简；只有明确需要完整工具副本时才使用 --full。
scripts/flower2api-stack backup --env /absolute/path/v3.env --backup-dir /absolute/path/new-backup
scripts/flower2api-stack backup --env /absolute/path/v3.env --backup-dir /absolute/path/new-full-backup --full
# 可离线复验新格式备份，不需要加载线上配置或调用账号。
scripts/flower2api-stack verify-backup --backup-dir /absolute/path/new-backup
# 先生成维护清单，再停机应用；清单变化后必须重新生成。
scripts/flower2api-stack storage --env /absolute/path/v3.env --output /absolute/path/new-storage-plan.json
scripts/flower2api-stack stop --env /absolute/path/v3.env
scripts/flower2api-stack storage --env /absolute/path/v3.env --apply --source /absolute/path/new-storage-plan.json --output /absolute/path/new-storage-result.json
scripts/flower2api-stack up --env /absolute/path/v3.env
```

备份、维护和 `up` 共用部署级非阻塞磁盘锁，维护时不可同时启动服务。`storage` 只清理本部署精确 `_cacache` 路径，并对冻结项目内容与具有新安装回执的静态 CLI 制品去重；账号 HOME、会话、凭据和候选工作区保持独立。浏览器及旧安装协议 CLI 在无法证明安全时保留，清单会记录原因。新 CLI 在暂存目录安装、验证精确版本、生成回执后原子发布，结束清理下载缓存；同版本遗留暂存会在取得安装锁后收口，缓存回收失败不阻断已验证就绪的程序。同字节且同权限的程序通过管理端私有 `bench/cli-artifacts` 复用，账号没有该缓存的跨账号可写挂载。已完成且通过隔离恢复的同部署备份保存带摘要保护的来源证明，程序及依赖锁未变时可以复用，清缓存后不必重新下载才能生成下一份精简备份。不要对 Docker 卷、其它应用目录或未知账号目录执行全局 prune。

v3 回退先停止当前批次并保留最新停机备份。只在布局/桥协议兼容时，把 env 中两个镜像及清单一起切回已保存的兼容批次，再 check/up；通过“环境与任务”的重建操作替换已停止的旧批次容器，保留环境 ID 和持久 HOME。未完成重建的环境会拒绝发送，不静默混用镜像。数据库或布局不兼容时不能直接回退镜像，需先在独立离线目录核对快照与最新凭据所有者，再安排恢复；没有自动恢复数据库或切回旧版的入口。

登录在真实 CLI/tmux 内完成。CLI 与 Rust API 发送器位于不同角色容器，共享本账号网络命名空间及代理，但仍是不同客户端。gateway 内的 OAuth 客户端使用账号显式代理；v3 缺少或只有空白代理时在请求前拒绝，不自动直连。固定环境不保证完整指纹相同或避免封禁。身份没有明确来源时不应猜测。遥测专项继续留在后续任务。

账号支持 5h/7d 已用百分比阈值，两个窗口独立配置 1～100 的整数或关闭，默认关闭。额度从正式响应被动更新，不在自动调度中查询 usage。观测到任一有效窗口达到阈值时，当前普通 CLI 或养号继续按原计划完成整轮（包括补充与收尾），不因自设百分比直接 STOP；后续批次任务等待额度恢复及原投放间隔，定时养号沿用原随机间隔。真实额度耗尽、认证失败、用户停止及原超时仍按原流程处理。窗口到期不伪造用量归零，仍复用持久单次正常更新机会。整轮可能越过设定百分比，此阈值只约束下一轮入场。未绑定但持有本地 OAuth 的账号也可以定时养号。抓包、继续对话与 cc2api API 保持原有百分比门禁。此功能需要同批 control/account 镜像，回滚前先关闭阈值并收口等待工作，保留持久数据。

账号页的“运行时段”按环境已固化时区设置星期和最多 8 个区间；结束早于开始表示跨午夜，并归属于开始日，夏令时按当地实际分钟判断。旧账号默认不限制时间。窗口外普通/抓包任务保持排队，批次和定时养号延后，立即养号与新续聊输入明确拒绝且不缓存；已开始的整轮及在途续聊输出继续。时间和自设额度阈值必须都允许才开始下一轮，原随机间隔仍生效。配置和排队信息持久化，等待不占 CLI 信号量或长期锁。对外 API、登录、OAuth 维护及手动额度查询不受时间窗口限制。回滚到不支持窗口的版本前，应先关闭限制并收口等待任务。

环境页可展开“物理特征”，分列已保存配置与上次容器实测，并显示采集时间、差异或未采集。点击“刷新实测”只读取当前归属的空闲 CLI 容器，停止/占用/失败时保留已有观察；页面不会为采集唤醒、重建或重新生成指纹。RAM 分开显示账号合计预算与 CLI 实际 cgroup 上限，不把宿主内存或 swap 当作 CLI RAM。账号页和环境页同时显示当地时钟及北京时间参考。

API 与同账号普通 CLI、养号、抓包独立调度，可以同时运行；CLI 之间串行，养号让位于正式 CLI 工作。API 准备发送器不安装 CLI。普通 CLI 的取消、心跳失联、调度器重启只清理本次进程和 CLI 观察上下文，保留账号容器与 API 长流；清理无法确认时标为 `cli_reconcile`，只禁止下一 CLI。旧无模式记录默认排他。重授权、代理修改、绑定切换、停止及重建仍关闭 API 入场并检查或排空已有请求。两条链路共享账号额度及容器资源，容器或公共网络故障仍可能影响两者。

本地验证使用合成账号和 mock 上游，不能将本地通过等同于真实账号已完成验证。生产部署、旧账号接管、真实验证和发布推送需要单独安排。

run 与续聊的证据入口保持固定，各次执行在 `executions/<source_hash>` 下独立保存统计、额度观察、HTTP 和原生 flow；额度恢复不会覆盖旧证据。run 统计汇总各 run 执行，抓包页面展示各代及续聊索引/文件。历史平铺证据仍可读取；未部署的早期 v3 原型目录链接不自动接管。本地演练覆盖同 run 第二代合成 CLI 在原 HOME/cwd 使用 `--resume`，不代表官方 CLI 或真实额度耗尽链路已验证。

```bash
# 需在已安装 orchestrator requirements 的 Python 环境运行。
python3 deploy/flower2api/run_local_verification.py --manifest /absolute/path/release.json
# 真实忙碌 driver 跨过 5h／7d 阈值后完成原补充和收尾，下一轮等待。
python3 deploy/flower2api/run_local_verification.py --manifest /absolute/path/release.json --quota-completion-only
# 真实物理采集、当前轮次跨时段及阈值、排队重启与两个门禁分别恢复。
python3 deploy/flower2api/run_local_verification.py --manifest /absolute/path/release.json --run-windows-only
python3 deploy/flower2api/verify_stack.py --manifest /absolute/path/release.json
# 已安装 Chrome/Chromium 时，验证真实页面的统一退出和旧 Cookie 重放拒绝。
python3 deploy/flower2api/verify_stack.py --manifest /absolute/path/release.json --browser
# 本轮完成阈值说明、历史停止记录的 API／SQLite 兼容与页面转义。
python3 deploy/flower2api/verify_stack.py --manifest /absolute/path/release.json --browser --quota-completion
# 当地时段保存/重读、双时钟、物理特征来源、XSS 和窄屏明暗主题。
python3 deploy/flower2api/verify_stack.py --manifest /absolute/path/release.json --browser --run-boundaries
# 验证实际 Recorder 的本地 HTTPS/SSE、未知一次机会及重启不重复。
python3 deploy/flower2api/verify_warmup_quota.py --manifest /absolute/path/release.json
# 在统一后台验证合成账号阈值配置、保存重读、明暗主题和 390px。
python3 deploy/flower2api/verify_stack.py --manifest /absolute/path/release.json --browser --warmup-quota
# 关联重授权的页面/WS/tmux/凭据落盘演练，使用专用合成账号和本地代理
python3 deploy/flower2api/verify_stack.py --manifest /absolute/path/release.json --browser --reauth
# 原 cc2api 删除后页面解绑、RT 交接、后台刷新失败收尾及再次创建，交叉核对两库和原身份。
python3 deploy/flower2api/verify_stack.py --manifest /absolute/path/release.json --browser --deleted-binding
```

演练创建随机部署标识的内部 Docker 网络，使用空 SQLite、合成凭据、CLI 测试替身及仅在本地处理的 SOCKS/DNS/HTTP。Docker 检查分别验证发送器直调和真实网关入口到账号的 ClientHello，断言合法短 DNS 绑定可用、共享 CLI 租约不阻止网关发送、错误账号绑定拒绝且无重复发送；另保持账号发送器 API 长流并启动 CLI 养号/抓包、发送第二次 API，验证 CLI 取消及调度器重启对账后长流继续且容器不变。Rust 的 `cargo test --lib local_https` 另用临时 CA 和回环 TLS 服务验证完整响应、原始字节/头顺序、非信任证书及错误主机名拒绝、长流取消。额外信任根仅编译进测试，正式镜像不提供跳过证书校验或追加测试 CA 的开关。TLS 测试需要 Python3 和 OpenSSL。结束只删除本次创建的测试资料与资源。

整套启动演练使用另一组随机资源和空数据库，核对统一会话、HTTP/SSE/WS 桥、内部路径拒绝、静态终端资源、退出后旧 Cookie 和终端票据拒绝，以及停机保留数据；另建合成旧哨兵，确认新版启停不会修改其容器或数据库。停机后只导入下述合成离线元数据并验证幂等；不读取真实账号或发送上游请求。浏览器验证使用独立临时配置，仅访问本地部署，不读取用户浏览器资料。

`status` 按本部署标签列出两个管理服务和全部动态账号容器，展示实际镜像 digest、环境代次及 API 活动/等待数、CLI 租约与执行证明。网关不可达时占用标为不可用，不把缺失信息当作空闲；输出不含发送器秘密、管理密码或 AT/RT。

旧资料可使用去凭据 JSON 做离线元数据导入，格式见 `fixtures/offline_metadata.json`。只接受账号名、历史任务标题/题号、运行 ID/状态及来源标识；凭据、代理、profile、提示词正文和工作目录内容均拒收。需先初始化并停止独立 v3 部署，默认演练在事务中验证后回滚，显式 `--apply` 才保存。按来源/类型/历史 ID 幂等，内容改变或账号名碰撞拒绝覆盖；账号统一停用且不绑定 cc2api，历史任务归档，未完成运行记为已停止，不恢复调度。真实旧账号接管仍需单独安排。

```bash
scripts/flower2api-stack import-offline --env /absolute/path/v3.env --source /absolute/path/metadata.json
scripts/flower2api-stack import-offline --env /absolute/path/v3.env --source /absolute/path/metadata.json --apply
```


### 隔离布局 2 升级与回退

CLI 为 UID1000、sender 为 UID1001，两者 capabilities 全部删除、no-new-privileges、根只读；PID/挂载独立，仅加入本账号网络命名空间。网络角色持有 NET_ADMIN/TUN，在账号命名空间默认拒绝出站；只允许回环、当前代理和 TUN，拒绝 Docker 内置 DNS、IPv6、其他私网目标。私有代理资料、CA 私钥、内部 sender 鉴权和全局额度目录不挂给 CLI。业务临时盘 noexec，工作区可安装本地依赖和运行编译产物。

旧单容器不会在 GET/普通发送中自动转换。先排空并用本次 `stop` 停止全套角色，保存全新停机备份；再按新清单启动管理端，在环境页执行“重建容器”。迁移保留环境 ID、generation 连续性、画像、HOME 和最新凭据，并在环境私有 `runtime/isolation-upgrade/` 保存原登记、SQLite 和配置快照。此快照用于核对，不会自动覆盖凭据。角色缺失/创建失败保留 reconcile，显式 stop/rebuild 处理完整集合；CLI 单独异常可通过“故障对账”恢复，健康 API 保持运行。

布局 2 不能直接切回只认识单容器的旧管理程序。回退必须先用布局 2 的 `stop` 和 `backup` 保存**最新**状态，再精确核对、移除待回退环境的三个已停止角色。在独立离线目录按迁移记录只恢复该环境的旧布局登记并清空三个容器 ID，保留当前 HOME/profile/gateway 的最新凭据与身份；禁止整体覆盖旧 SQLite 或恢复旧 RT。然后同时切回已保存的旧联合清单/两镜像，经 check 后启动，在副本验证完成前不对生产执行。没有自动数据降级入口。

## 完整账号转发与进程指标验收

`verify_forwarding.py` 使用真实管理桥、调度器、两个账号容器和独立 HTTP CONNECT/SOCKS 代理，验证正式 API 的成功 JSON、完整 SSE、慢流取消、共享 CLI 租约、账号隔离和故障关闭。网关的公网连接在本次网络命名空间内被阻断并计数；代理只连接本地 HTTPS 夹具。浏览器实际操作创建、关联和指标更新，并交叉核对 SQLite、发送器证据及账号卡片。RSS 来自在容器中运行的官方 2.1.293 原生 CLI，不发送真实模型请求。

本地 HTTPS 需显式构建 `verification-control` / `verification-account` 测试目标。构建仍复用 `manage.py` 的源码冻结和联合清单，唯一发送逻辑差异是 `v3-verification` 编译特性读取临时 CA；保留证书签名和主机名校验。正式 `control` / `account` 目标不依赖这些阶段，也没有运行时追加 CA 或关闭 TLS 校验的开关。测试镜像和标注 `verification_only` 的清单不得发布或用于生产。

```bash
# 需要本地 Docker、OpenSSL、Chrome/Chromium，以及包含 requests/docker/websockets 的 Python 环境。
# 批次、清单和输出目录都必须是全新的；官方二进制由调用方提供，不下载、不读真实凭据。
python3 deploy/flower2api/verify_forwarding.py --build --release verify-process-local \
  --manifest /absolute/path/v3-verification.json
python3 deploy/flower2api/verify_forwarding.py --manifest /absolute/path/v3-verification.json \
  --cli-binary /absolute/path/official-2.1.293/claude.exe \
  --output /absolute/path/new-verification-results
```

结果目录包含脱敏场景结果、代理/上游与发送器关联证据、进程观察和页面截图。失败也保留已完成证据，再清理本次随机标签的容器/网络；不会删除其它部署。旧重授权页面回归继续使用正式镜像执行 `verify_stack.py --browser --reauth`。

测试替身成功只证明隔离业务链路。生产发送器经账号代理完成非模型 HTTPS 往返、真实 Anthropic 模型推理是另外两项验收；受限账号不能用来证明成功推理。

默认 CLI 版本为 `2.1.293`；显式 `V3_CLI_VERSION`、页面版本覆盖及已有 Run 的冻结版本继续按原优先级生效。

官方 Claude Code CLI 的遥测和错误上报默认关闭，配置 `V3_CLI_TELEMETRY=off|on`，空值按 `off` 处理。`off` 为受控 CLI 设置和执行环境写入 `DISABLE_TELEMETRY=1`、`DISABLE_ERROR_REPORTING=1`；`on` 移除这两个关闭键，恢复官方默认许可。任务、养号、项目及交互 CLI 在下次启动时应用策略。CLI 自动更新继续由平台单独关闭。原生发送栈的遥测设置沿其自身配置。

## 完整开发周期的外接需求方

内容 schema 3 的新批次需要给 orchestrator 配置 `PROJECT_REQUESTER_BASE_URL=https://ai.flower-cli.com/v1`、`PROJECT_REQUESTER_MODEL=gemini-3-flash-agent`、`PROJECT_REQUESTER_FALLBACK_MODEL=deepseek-flash` 和受保护的 `PROJECT_REQUESTER_API_KEY`。沿用部署 env 的权限保护方式；环境值用于初始配置；项目页也可动态编辑一个 Base URL、私有密钥和 1～8 个有序模型，保存后无需重启。页面覆盖以 0600 原子存入 `bench/settings/project-requester.json`，API 只返回密钥是否已配置，留空保存沿用当前密钥，并可恢复环境配置。密钥不传给账号 CLI、sender 或浏览器响应。未配置或配置不合法时拒绝新完整任务，历史批次仍可读。

普通对话不启动独立评审；外部需求方按实际回答生成追问、确认实施或提交验收。402／明确额度不足、429 与暂时服务失败按已配置模型顺序有界降级；同一配置版本内当前任务之后沿用已选备用，新配置对后续请求生效。认证／参数错误、主备均不可用或结果未知会保留原任务及可见原因，不重建开发者会话。原会话、代码、生成消息和累计预算在暂停及执行切片超时后保留。

当前百项目重审口径、未准入清单、完整内容与本地验证命令见 [内容库说明](../../resources/project-library/README.md)。这次源码配置变更不表示生产已更新，也未自动启动真实 Claude 任务。

### 按账号无限内存与组装快照

全局 `V3_ACCOUNT_MEMORY`默认 `unlimited`。账号固化资源 `mem="unlimited"` 取消三个角色及派生评审的RAM/swap上限，Docker 对应 `Memory=0, MemorySwap=-1`。该账号直接与整机服务竞争内存。CPU/PID、标准并发和 RPM 沿用原值。

无限模式下原生池配置 `memory_mib=0`，省略 `V3_NATIVE_SENDER_MEMORY` 也能准备。物理进程上限仍为标准并发的两倍，按需创建并回收。有限账号仍执行显式 sender 预算与加权容量检查。内存策略调整在空闲时通过原排他维护租约重建，核验CLI孤儿、API及评审活动，使用同批控制与账号镜像。已有部署的显式 `V3_ACCOUNT_MEMORY=1536m` 仍是有限模式；上线时将其改为 `unlimited` 后应用新策略。

账号固化配置 `native_capture_enabled` 控制私有 CC 组装后头与正文采集。缺省开启，显式 `false` 保持关闭。管理员在「请求记录 → 详情」读取已脱敏内容。每账号保留至多 50 份、100 MiB，单份正文 2 MiB、请求头 128 KiB，超限截断及采集失败单独显示。原始凭据和完整正文均不进入普通服务日志。

## 按账号请求内核在线升级

部署配置设置 `V3_NATIVE_RELEASE_PUBLIC_KEY`（原始 Ed25519 32 字节公钥的小写十六进制）后，全部已绑定且使用 `native293` 的账号环境均可管理请求内核。旧 `V3_NATIVE_RELEASE_PILOT_ENVIRONMENT` 停止参与准入，新配置仅需发行公钥。已有 sender 首次接入时按原维护入口空闲重建，以取得只读版本目录和发行公钥。新镜像默认内核固定为已验证的 beta.6，兼容强制缓存 TTL 策略；构建校验分发 SHA256 和长度，sender 另核验实际执行体。

1. 在「固定账号环境」找到目标原生账号，点「检查更新」查看固定发行源的新版本；点「选择版本」从已发布列表选择并准备。发现结果缓存五分钟，失败时显示陈旧或不可用状态。发现结果仅作为版本线索。管理端准备时独立读取签名、清单和附件并验签，已准备的制品支持离线复核。校验期间旧内核继续接单。
2. 确认候选分发摘要后点「激活候选」。现有账号维护租约要求 CLI 租约空闲，并等待该账号的 API 在途流自然结束。排空超时保留原内核。候选以实际 PID、封存执行体摘要及私有握手确认，随后才开放接单。
3. 「回滚内核」按同一流程恢复上一版。候选启动失败时先验证旧版再开放；遇到未确定的结果时，使用「恢复对账」核对并处理本操作的门禁。切换和回滚只启动该账号的 worker，不重建账号容器。

版本目录为 `bench/native-releases/<标签>/<分发 SHA256>`；不要覆盖已准备的标签或删除当前、上一版和操作仍引用的目录。各账号保存独立的当前版本、上一版本和操作记录，准备同一制品可复用部署内的已验签文件。页面展示上次核验的 PID；进程之后可能因空闲回收或故障而变化。移除发行公钥前须先将使用在线版本的账号回到镜像内置版。内核操作不需要例行数据库或整机快照。
