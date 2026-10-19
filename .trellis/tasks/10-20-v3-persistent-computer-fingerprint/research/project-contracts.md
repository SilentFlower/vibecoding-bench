# 本任务适用的固定环境契约摘录

权威源：`.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`。
源文件 SHA256：`7cdb3a2b05a887590ce1b604d715d38d186a57ad7dd9eff31690ddbe10e5decf`。

实施时仍须经 trellis-before-dev 核对权威源；本快照固定记录实施前版本和哈希，用于避免整份大文件注入被截断。本任务新增的持久计算机身份契约已追加到权威源，不重写此历史摘录。

## 独立账号动作与真实指标（源 449—462 行）

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


## 三角色隔离与 OAuth 出口（源 572—586 行）

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


## 固定 CPU 与内核画像（源 640—651 行）

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
