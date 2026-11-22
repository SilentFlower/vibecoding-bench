# SSH 实施进度与执行边界

## 方案增量决定

用户在比较 HTTPS、WebSocket 和 vm2api 的 SSH 接入后，明确选择 SSH 纳管及隧道转发。本次决定沿首次批准后的增量规则同步 PRD、设计、实施计划与 Brief，继续同一任务。

## 已实现的基础

- `cluster_schema.py` 为独立冻结增量，`bench.baseline.1` 摘要保持原值。`bench.cluster.2` 建立节点登记、账号分配和迁移记录，并回填旧账号、为新账号建立默认归属。
- `cluster_nodes.py` 定义严格地址/路径/主机公钥/配置版本合同；`cluster_store.py` 维护中央节点与归属记录。
- `cluster_ssh.py` 使用系统 OpenSSH，私钥与 known_hosts 存于受保护目录，严格主机校验，控制与业务分别建立 SSH 隧道。节点资源检查是固定只读命令。
- `cluster_service.py` 和 `cluster_api.py` 提供登记、公钥探测、连接检查、启停接单状态与引用保护的节点移除接口。
- 网关管理桥增加精确节点路由，Vue 新增节点页面、主机指纹显式确认和只写私钥表单。
- 管理镜像加入 OpenSSH 客户端，固定宿主安装包补齐新的纯迁移定义。

## 已有验证

- 26 项数据库、节点、接口及 SSH 测试通过，包含真实隔离回环 sshd、错误主机身份拒绝、Unix socket 双向字节传输、隧道进程释放、旧库回填及新账号归属。
- 数据库定义检查通过：bench 2 步、gateway 4 步。
- Vue TypeScript 检查与 Vite 生产构建通过。

## 仍需实施的关键边界

1. 已新增仅适用于首次执行的人工分配与远程 sender 准备。已有环境必须继续实现迁移状态机，保证 HOME 与身份资料随迁移保留。
2. `AccountRuntime` 的 `.data`、`._root()`、`._network_runtime()` 与 `.database()` 广泛用于凭据发布、Docker 挂载、执行记录、抓包和终端；仅把 Docker SDK 换成远程客户端会使文件归属错误。
3. `main.py` 的 Runner、LoginManager、ContinueManager、QuotaGuard、环境维护及内部 transport 接口都需要按账号路由。环境持久状态、登录草稿和已存在作业应逐项核对。
4. `PiTerminal.start/passive_status/observe/send/control/workspace/conversation/usage` 与 `ProjectsTerminal`、`ProjectReviewRuntime` 直接操作本地文件和容器，需节点侧私有执行组件与中央适配。
5. 固定 reqwest 0.12.4 采用编排服务私有流式转接。Rust 校验固定中央 origin 与部署/环境路径；编排服务核对当前分配、节点开关和代次，并剥离中央认证头后通过 SSH Unix 隧道发往 sender。真实 HTTP 与 SSH 测试覆盖原字节、压缩响应、SSE 取消和计数释放。
6. 网关凭据所有权与 `RuntimeGate` 仍为中央权威。远程执行组件需要受限的租约/凭据协调，不持有中央管理员密码。
7. 完整 Rust 网关选号链路、后台出站、手动迁移、远程 CLI/终端/工程、节点升级/备份和浏览器验收仍待后续实施，A1～A11 整体验收保持未完成。

## 2026-11-17 纵向实施增量

- `NodeDeployment` 经 SSH Docker socket 准备同批 control/account 制品与节点专属网络。镜像内容冲突、归档歧义和导入错误的 4 项测试通过。bootstrap 首次创建私有空闲维护门禁，再次安装保留原维护状态。
- 节点私有 `NodeExecution` 保存有限账号投影，执行副本移除 RT，按节点/账号/环境/分配版本拒绝旧命令。只读 inspect 返回节点实际状态；中央恢复与清理跳过远程环境，中央 `_root/_container` 对远程归属保持拒绝。
- 首次分配使用中央环境锁及短数据库事务，保留分配 CAS。已有代次、角色、运行历史或环境资料时要求迁移。节点在安装期间改变接单状态时转为 needs_check，迟到回执不覆盖当前配置。
- `cluster-increment-07.log`：28 项节点、执行投影、真实HTTP/SSH转接、制品与本机恢复边界测试通过。`gateway-node-relay-increment-03.log`：Rust 固定 origin/部署/节点/环境/分配版本路径定向验证通过。
- `cluster-docker-increment-10.log`：真实 sshd、Docker 节点组件、network/CLI/sender 三角色、中央私有转接、节点代理和本地 TLS 合成上游完成 JSON/SSE 往返。中央账号环境目录保持缺失，节点 profile 为 AT-only。本测试共享开发机 Docker daemon，采用随机部署标签、独立数据根和节点网络。Rust 网关选号、完整计费与物理跨机网络仍需后续证据。
- Docker 证据镜像为本地源码叠加的 `flower2api-control:cluster-test-local`，继承验证用 CA 二进制。该测试制品仅用于开发验证。正式镜像和最终完整回归由交付阶段执行。
- 初次 TLS 夹具误用自签 CA 作为叶证书，已复用现有 `verify_forwarding.certificates` 的 CA/叶证书合同后通过。
- `cluster-native-increment-11.log`：同一真实 SSH/Docker 私有准备链路使用 native293 完成 JSON/SSE；实际原生二进制、合成 TLS 上游与代理均参与。此证据仍是单个远程节点和中央私有转接，完整 Rust 网关及双节点并行另验。
- 新增账号首次节点选择组件，复用现有选择器和确认对话框，迟到读取按账号代次丢弃。环境摘要显示节点归属及节点待核对状态。`web-increment-08.log` 为本阶段首次构建证据，后续小幅显示修改尚待复验。
- `web-increment-09.log`：包含环境所属节点和节点待核对显示的生产构建通过。
- `cluster-runtime-increment-12.log`：140项节点、转接、首次分配与原账号运行时测试通过。
- `gateway-cluster-verification-build-01.log`：当前 Rust 源码的验证版实际二进制构建通过。`cluster-gateway-increment-13.log` 与 `cluster-gateway-native-increment-14.log`：同一实际 Rust 网关创建合成账号/令牌、按令牌选定账号，经中央归属解析和私有认证转接、真实 SSH/Docker sender 到 TLS 合成上游，legacy/native293 各自完成 `/v1/messages` JSON/SSE。此证据的中央HTTP承载是只含内部transport与relay的隔离应用；完整main生命周期、浏览器与双节点并行另验。
- `cluster_archive.py` 新增停机环境归档与受限解包，源与目标复用 `tree_inventory` 的逐文件权限/归属/摘要，新增有界条目参数。整包摘要覆盖实际解包读取的同一描述符；路径、父目录类型、重复成员、文件摘要、容量与操作身份分别核验。该机制尚待迁移协调器接入。
- `cluster_migrations.py` 新增持久阶段、原分配CAS、目标环境原子切换及激活回执后开放；提交后未知结果保留目标并进入reconcile。该存储目前由定向测试调用，公开迁移操作与IO协调尚待实现。
- `cluster_environment.py` 新增本机/节点共用源隔离。持久执行/登录/凭据交接/评审/内核维护和sender活动会阻止停止。停止意图先落盘，真实三角色停止/PID归零后持久fenced回执。原运行时准备、claim与恢复/清理识别该标记；节点固定CLI增加fence动作。
- `cluster-archive-increment-16.log`：33项迁移归档及既有备份/存储回归通过。`cluster-migrations-increment-17.log`：6项真实SQLite迁移阶段/CAS/提交后失败保护通过。`cluster-migration-fence-increment-19.log`：24项源隔离、节点投影、迁移账本、归档验证通过。上述新增源隔离与归档尚未在新节点制品中跑真实迁移链路。
- 新增 `cluster_migration_files.py`：操作归属标记、幂等导出描述、目标独占上传目录、未发布私有树的恢复和发布意图保护。`cluster_transfer.py` 经 SSH Docker Unix socket 直接调用归档 HTTP API，保持有界读写与期限，剥离外层单文件 tar 并核对精确内包摘要，上传采用 tar 生成器。
- 节点固定CLI已支持 `export/stage-import/verify-import`；新增环境文件锁与独立节点容量锁，长包操作锁定所属环境。只读观察使用共享锁及非阻塞尝试。
- `cluster-runtime-increment-24.log`：147项最新运行时及迁移基础测试通过。`cluster-migration-files-increment-27.log`：17项迁移账本/有界传输/私有文件验证通过，新增源状态和同代配置摘要冻结。
- `node-test-image-build-03.log` 已重建开发节点镜像，包含归档、源隔离和新节点CLI。`cluster-migration-io-increment-26.log`：两个真实隔离sshd、同一中央归属库、两套节点网络及数据根，完成源三角色停止、归档导出、中央落盘、另一节点上传与逐文件导入核验，验证 HOME userID 和工程文件保留。中央保持原归属maintenance，目标仅存在操作私有副本。发布、CAS实际切换、激活及失败恢复仍待接通。
- 双节点夹具显式分配经 Docker 已用子网和宿主路由核对的测试网段，避免开发机默认地址池不足；按本次随机部署标签清理。

## 下一段执行顺序

1. 接通迁移协调器：中央owner/profile/environment锁及网关排他租约，持久requested/draining，核对CLI/终端/工程/登录，取得原节点fence收据。
2. 固定节点CLI增加export与stage/import/activate/cancel操作。归档保存在节点操作私有目录，Docker get_archive/put_archive 经既有SSH控制隧道有界传输，中央落盘中转并核对整包摘要。禁止把完整包读入内存。
3. 目标按同操作私有暂存导入，保留逻辑身份、HOME、工程及证据，剔除并重建旧运行配置和CRIU。实际角色无模型检查后CAS切换，目标激活收据后开放。提交前失败核对双方隔离再恢复源；提交后失败保持目标reconcile。
4. 继续远程CLI/终端/工程与后台出站的显式适配。当前私有NodeExecution每次docker exec独立进程，缺持久作业协调，不能据此宣称R5/R7/A10完成。
5. 双节点、真实完整main与浏览器、节点升级/组合备份与故障恢复仍属于本任务后续工作。最终遵循Check-All→Update-Spec→Push门禁。

## 目标发布、取消及排空增量

- 冻结导出包绑定CLI版本、设备/账号来源和源实际代次。目标在操作私有树和准备后的HOME分别复用原身份合同核对。目标发布意图先落盘，环境树通过目录fd原子移动，准备后登记新代次。
- 远程角色增加完整节点标签和节点限定DNS名称；本地默认命名保持原合同。角色读取、源停止、孤儿检查及容量统计核对节点范围。NodeExecution核对运行时的部署、节点与独立网络。
- `node-test-image-build-04.log`和`cluster-migration-publish-increment-39.log`：两个真实sshd、两套节点数据和Docker网络，源停止/导出/中转/私有核验，目标prepare-import、中央CAS、activate-import、finish全部通过，迁移后实际Rust网关再次完成JSON/SSE。合成上游以两网络中的同一固定代理别名承接，原业务代理配置保持。开发制品仍为验证CA专用镜像；本场景用隔离ASGI应用承接中央内部接口。
- 35号验证日志在归属切换后因夹具把首次分配后的版本硬编码为2而失败，已改按冻结target_revision核对。37号验证暴露旧断连监听的取消吞噬并被定向中断；同场景测试资源已按随机部署标签清理。39号使用直接ASGI receive监听并通过。
- relay准入与迁移begin共享中央短写锁，绑定核对和活动登记原子完成；新增账号活动流计数。后台线程取得通道时的协程取消等待原结果后释放。
- 新增源restore-source取消墓碑、目标revoke-import持久撤销、迟到上传/发布/激活拒绝。中央账本增加冻结检查点、原阶段resume、双端收据cancel；提交后继续保留目标。`cluster-recovery-increment-40.log`：33项目标身份发布、源恢复、账本CAS、检查点、取消和归档基础测试通过。33项测试覆盖文件和SQLite；实际双SSH取消与故障恢复另验。
- 当前仍需中央迁移协调器/公开状态与UI、本地目标和迁回旧副本、远程CLI/终端/工程、后台出站、节点预算/升级/备份和完整验收。任务保持in_progress。

## 中央协调与公开迁移操作增量

- 新增`cluster_migration_io.py`、`cluster_migration_lease.py`、`cluster_migration_runner.py`和`cluster_migration_api.py`。执行冻结范围与关闭账号准入同事务持久化；原导出/上传尝试重用。网关排他租约5秒续约，失败保留排他占用；恢复仅定向核对同操作旧代次。API/节点流先排空，再取得环境锁。
- 协调器覆盖源fence/export、有界传输、私有核验和prepare-import、CAS、activate与最终开放；取消先撤销目标，再恢复源；提交后恢复保留新节点。节点连接配置按摘要冻结，单纯暂停接单推进页面revision仍可收口原激活。
- 本机迁移目标新增独立node-execution-local.sqlite投影，共享中央本机容量/环境/作业锁。管理profile只消费且保留RT，中央权威行不提前覆盖。旧停止副本经精确角色收据核对、持久retirement意图、移除停止角色和目录fd移动后保存为previous-environment。取消后的较新目标代次从两端最大值继续。上述本机目标暂为真实文件/SQLite+运行时替身证据，实际本机三角色验证仍需后续。
- `cluster-migration-return-cancel-increment-44.log`：legacy实际Rust网关、双SSH节点迁移，迁回原停止节点并prepare后取消，目标真实角色停止、源恢复及中央原分配保留均通过。`cluster-migration-native-return-cancel-increment-45.log`同场景native293通过；旧夹具在维护期的后台探测曾输出预期RuntimeBusy堆栈，现夹具将其映射为503。
- `cluster-coordinator-docker-increment-48.log`：实际Rust网关排他租约prepare/claim/heartbeat/release与真实双SSH/Docker归档、目标发布、CAS激活通过，随后仍执行迁回取消。中央承载继续为隔离内部ASGI应用。该镜像是build-05验证制品，尚非生产同批镜像。
- main生命周期接入后台MigrationOperations，GET/POST账号node-migrations以及原操作resume/cancel；worker参与实际UPDATE_GATE，公开状态白名单移除所有检查点和秘密。mainguard按owner/profile顺序核对活动run、Pi、登录、续聊、凭据所有权和CLI作业；环境锁由协调器排空后取得。
- `cluster-migration-api-increment-52.log`：62项节点、转接、迁移基础及API/协调回归通过。后续连接摘要与暂停恢复增量在`cluster-coordinator-api-increment-53.log`：46项通过。主要故障覆盖目标prepare未知、CAS后激活未知、网关重启对账、其他holder占用、续约失效、双端取消收据和排空锁顺序。
- Rust管理桥为账号node和node-migrations增加精确方法/操作ID/层级白名单。04号桥接定向测试通过；05号桥接整组正在运行，包含有界状态GET与原长流合同。后续实际链路使用验证CA二进制前应重新cargo build --features v3-verification；常规cargo test可能重建默认二进制。
- `AccountNodeMigration.vue`、nodeApi公开类型和原节点选择页接入迁移/进度/继续/取消。确认冻结账号、目标、原版本与操作；未知POST结果仅GET核对同操作。`web-increment-10.log`生产构建通过；`cluster-ui-increment-02.log`和cluster-ui-02/results.json：真实构建产物的确认取消零写入、未知提交核对、提交后激活、提交前取消、账号切换和1440/390布局均通过。该浏览器证据使用合成API。

- `gateway-migration-bridge-increment-05.log`：10项Rust管理桥定向测试通过，节点/迁移状态GET采用有限期限，原长操作和流保持原生命周期。`cluster-main-guard-increment-54.log`：4项后台/API测试通过，包含实际main的owner/profile互斥、远程元数据读取且不访问中央HOME。
- `node-test-image-build-06.log`已重建最新开发节点制品；`gateway-cluster-verification-build-02.log`已重新构建含当前桥接修改的验证CA二进制。新真实场景`cluster-coordinator-local-increment-55.log`正在运行：在此前双SSH迁移和迁回取消后再迁回默认本机，检查本机真实三角色、管理profile RT不变、实际网关转发；夹具中央Python运行在宿主，Docker名字仅在本次隔离网络中用受限DNS替身解析。该结果以实际日志为准。

- 55号真实本机迁回已完成CAS、角色停止、工程资料和管理profile核对，随后网关请求502。夹具在本机目标准备后才创建gateway，静态入站策略尚无其地址。57号改为gateway先入网再prepare-import，符合实际部署时序；`cluster-coordinator-local-increment-57.log`：完整双SSH迁移、迁回取消、再迁回默认本机及本机实际Rust JSON/SSE全部通过（103.075s）。本机DNS替身的范围保持只映射本次隔离Docker名字。
- 后续源码补齐取消边界：目标业务目录缺失时仍核对实际角色，存在未知角色保持维护；本次尚未发布但目标存在旧fenced副本时，只读核对旧停止收据并保留资料后撤销本次操作。retire与revoke复用同一节点作用域角色核对。源fence要求原目录实际存在，避免生成替代空树。纯未使用环境在begin前返回首次分配指引，已有静态资料继续允许迁移。坏发布意图链接阻止私有树重建。
- relay数据库准入异常也释放已登记UPDATE_GATE活动；56号7项实际HTTP/SSH转接测试通过。59号58项取消/账本/节点/实际转接回归通过；最新60号40项执行/协调/API/归档/源隔离测试通过。后续新增坏意图链接测试包含在60号。真实节点制品build-06早于最近revoke/目录存在性增量，下一次实际节点验证需重建。

## 远程CLI/终端下一决策的初步定位

- 每次docker exec新建NodeExecution当前只适合prepare/inspect/fence与文件迁移。R5/R7需要保持实际作业、进程和输入边界，下一段应先核对持久节点执行进程方案与中央有界租约证明，再写执行代码。
- PiTerminal在start/passive_status/observe/send/control/workspace/conversation/usage读取AccountRuntime jobs、节点根和Docker实际进程。ProjectsTerminal位于projects_runtime.py并继承PiTerminal。原AccountRuntime心跳失败会cleanup作业，新的跨机控制需保留未知提交和原输入边界。
- 节点不能持有中央管理员密码；中央继续实际租约与额度准入，节点只接收绑定原操作/节点/账号/环境/分配/实际代次的有限证明。需要逐条适配具体操作，保持设计中不实现通用远程SQL/文件系统的边界。持久节点服务的具体合同仍待按实际类研究后写入设计与执行计划。
