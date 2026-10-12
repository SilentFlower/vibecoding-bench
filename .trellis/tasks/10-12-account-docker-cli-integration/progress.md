# v3 实现进度

## 分支与授权

- 父仓与 cc2api 子仓均为从本地 main 创建的 v3；基线分别为 `49e8fb097a527bca9b16af1842b5c524ea5f2da9`、`34ed25fd5a352e823c1ec0269bdfb39b530bae92`。
- Brief 已展示并获确认，任务 in_progress，实现路由 inline。
- 仅授权本地实现与验证；未授权生产部署、真实账号请求、发布或 Git 提交推送。
- 原有 official-protocol-capture.md 用户修改必须保留。

## 已落地（尚未整体验收）

- Rust 账号发送器及 gateway/Prime 发送层接入，旧模式保留直连路径。
- Rust 持久占用门禁及管理接口，入场、排空、领取、心跳和释放基础实现。
- Python AccountRuntime 初稿，固定目录/容器、发送绑定、driver exec 及清理基础实现；尚未接入 main。
- worker 的 v3 持久 HOME 分支。

## 验证证据

- `cargo test --manifest-path cc2api/Cargo.toml runtime_ --lib`：2 个新增测试通过；560 个过滤。仅覆盖基本目标绑定验证和排空门禁，不代表完整传输验证。
- `cargo fmt` 已执行。
- 未执行真实 CLI 登录、Docker 生命周期、完整 Rust/Python/前端回归。

## 后续必须完成

1. 原始请求、SSE、取消、不重放测试及租约故障恢复。
2. 账号镜像 PID1、网络上下文切换、CLI 版本缓存、非 root 权限。
3. AccountRuntime 完整登录/重授权/续聊/额度/恢复/空闲管理与 main 集成。
4. 独立 run 统计和额度/抓包路径兼容，不扫描累计 HOME。
5. 受控 CLI 身份导入、统一管理桥、WS 鉴权和终端资源。
6. 两镜像 Compose/构建/版本清单/冲突预检及隔离验证。
7. 完整聚焦验证后进入 Check-All；未运行的真实验证明确记录。

## 当前注意点

- AccountRuntime 当前引用的 v3-cli-version、v3-network-context 和 account 镜像尚不存在。
- claim 排空超时不能中断已经接受的 API 请求。
- 容器启动需要预算与 reconcile 门禁；记录文件必须按代次匹配，清理不能影响后续作业。
- CLI userID 与 device_id 映射必须从目标版本实际源码确认，不能猜测。

## 后续实现记录（第二轮）

- 父仓新增 images/account 的 PID1、网络上下文及版本缓存脚本；复用 sidecar 网络和 Recorder，服务故障退出，CLI 通过 setpriv 去掉能力。
- AccountRuntime 已接入 main 的 task/continue/login/quota/lifespan；登录使用固定 tmux，重授权暂存 HOME。已引入带来源摘要的执行 token，避免旧回调清理新作业。
- Rust 管理 HTTP/SSE/WS 桥、独立会话交换和 Python 短期终端票据；Vue 环境与任务入口、bench 环境维护页面。
- 受控 CLI identity 导入初稿：Recorder 仅从实际 messages metadata.user_id.device_id 保存证据，不推测 userID。新导入没有证据时返回明确冲突，用户先运行 CLI 任务后可重试。尚需测试及完整类型校验。
- images/v3/Dockerfile 两个最终 target、deploy/v3 Compose/manage.py/README/example.env、新 v3 CI 构建入口已写；尚未实际 Docker 构建。

### 新验证证据

- cargo test --test runtime_transport_test：3/3 通过（原始 body/头顺序/429、SSE首片/断开/无重放、旧代拒绝未触达上游）。
- cargo test --lib：562/562 通过。
- 原 Python 回归 101/101 通过；新增 test_account_runtime 5/5 通过（改名保持身份、旧 token清理不操作新job、排空超时保留API、等待API阻止idle claim、并发原子写受限文件）。
- cc2api/web npm run build 通过；Python py_compile、shell bash -n、webui JS syntax 通过。
- 宿主本地 Docker29.1.2可用，约13GiB可用内存、783GiB空闲空间。

### 仍须优先补齐与核实（不可称完成）

1. runtime_lease fsync/权限/过期及重启测试；import API 鉴权常量时间比较和完整 CanonicalEnvData校验。
2. 账号镜像健康/僵尸回收/上下文重启/取消真实进程树、proxy TUN不循环、版本缓存权限和工作脚本路径替换要实际Docker验证。
3. login commit/sync幂等、重授权取消保留旧值；登录到期清理目前尚未实现；WS登录断线连接数/PTY收口测试。
4. v3 continue根wrapper及PID写入已改，需实际读源码检视引号、cwd硬编码和取消；API gate等待必须保留原RPM/admission语义。
5. warmup标记已加入driver，但 trigger_account尚未在创建run前检查API/正式等待/CLI；排空失败不能变成正式失败，应顺延。
6. API证据及被动额度归属尚未补；run表环境快照字段尚未补；跨进程启动时持续容器状态和generation刷新仍需核实。
7. 现有account proxy/delete/rebind维护入口尚未全部接Runtime门禁；Runtime image/release标签核对未补。
8. manage.py需要隔离/端口/镜像错配测试、冻结源码清单及Docker构建验证；compose账户只启动2管理service，动态account由Runtime建。
9. 完整Rust集成/106个Python/Recorder回归及前端验证，然后路由Check-All（尚未进入），不得提前宣称v3完成。

### 工具与环境

- Python验证venv：/tmp/v3-verify-venv（requirements已安装）。原系统python缺docker，不可作为产品失败。
- 编译/测试日志：/tmp/v3-wire-tests.log、/tmp/v3-rust-tests.log、/tmp/v3-python-tests.log、/tmp/v3-runtime-python-tests.log、/tmp/v3-ui-build.log。
- npm目标CLI2.1.280包仅native binary：/tmp/v3-cli-contract/package/bin/claude.exe；没有可读userID/device_id源码。禁止猜测映射。

## 第三轮实现记录

- PreparedRequest增加UUID请求ID及首字节截止时间；环境解析与TTFB分别计时，原网关120秒、Prime30秒保持。sender按代次/目标/期限拒绝旧请求。
- RuntimeGate增加私有文件权限、文件与目录fsync；新增过期+重启必须对账测试通过。
- API额度头和请求ID保存独立root证据文件，bench独立API游标消费；证据写入失败保留当前响应，状态接口暴露evidence_ok并阻止下一提交/CLI。
- 绑定代理配置通过新增cc2api runtime/config核对；TUN bootstrap代理IP固定到sender，防止代理DNS漂移形成MITM循环。
- 管理修改代理/认证/状态及删除账号用配置租约阻止入场，检查与写库原子保护；最新cargo check通过。
- Runtime确保账号镜像角色/批次，并在runs增加environment_id/environment_generation/execution_source/runtime_release快照；停止再启动轮换generation/secret。
- cli项目子进程按UID收口，Stop hooks作业后恢复，task tmux socket转到root私有run目录。
- warmup触发前检查正式run/API等待/CLI工作，并顺延一分钟；driver再次idle claim处理竞态。但竞态busy异常目前仍记failed，需改为顺延。
- 全量Python106/106、Recorder9/9通过。完整cargo test（第2轮实现版本）通过，Postgres测试按既有规则忽略；第3轮修改后需最终重跑适当完整回归。
- 联合Docker检查构建已启动：exec session37717，日志/tmp/v3-image-build.log，标签local-check-20261012-a，计划清单/tmp/v3-local-check-a.json。仅本地测试构建，源码仍在修改，不能作为最终交付批次。需读取日志/继续poll。

### 剩余重要问题

- Docker构建未完成/尚未生命周期验证；manage.py还未冻结源码hash（需要先做冻结快照再最终build），隔离预检测试尚未写。
- login过期收口未实现、WS reconnect和force cancel尚未真实mock验证。
- CanonicalEnvData导入完整类型校验、常量时间内部令牌比较、已有身份冲突检测尚未补；新账号首次login不自动import，必须先用CLI任务观测device_id再同步，UI应明确显示这个状态。
- Rootnetwork-context切换可能僵尸累计：init不是所有mitm进程父进程，tini应回收，但需要Docker验证。init ready在sender真正监听前写入，Runtime当前单次状态检查可能竞态，需重试。
- continue shell wrapper已实际写入：请读取main.py open_bridge检查cwd命令仍含/workspace(仅用于旧top-configcopy，真实workdir已变/workspaces/run)，严格exec代次与PID收口验证。
- proxy/delete/rebind bench入口现有idle检查尚需接Runtime jobs/API门禁。
- unbound额度查询当前可能在HOME刷新RT，release会回写profile；短exec的release尚未等待查询CLI全部子进程（正常同步完成，但故障路径要检查）。
- 账号空闲stop/rebuild维护对已停止容器的_sender_active会连接失败；维护入口需要幂等处理。
- 缺少原始API证据轮转上限、运行元数据/健康展示细节和故障模拟。
- Image Dockerignore需改成白名单构建上下文；最终批次清单需冻结内容hash，避免工作区变动不透明。
- Skill check-all未进入；最终只有聚焦验证完成才进入路由check，无提交/生产/真实账号授权。

## 第四轮实现及隔离演练

- 两仓仍为 main 基线的 v3；没有提交、推送或生产操作。
- 绑定/改绑/解绑/删除同时持有环境锁与旧、新 cc2api 门禁，确认发送器空闲后停旧实例；下一唤醒轮换代次/秘密。cc2api 修改代理/认证/身份配置也凭配置门禁 quiesce 固定环境。
- 登录增加到期清理；低优先级认领使用 RuntimeBusy，养号并发竞态顺延一分钟而非记失败。CLI setup/cleanup 串行，401 watcher 回调匹配执行 token，清理失败保持隔离。
- CLI 导入使用完整类型校验和常量时间内部秘密比较，要求实际 device_id 与当前登录 account_uuid 归属一致；已有 cc2api 身份冲突时保留旧值并拒绝绑定。环境页显示待观测/已观测/冲突。
- API 证据保留最近两个各最多约16MiB的文件，健康故障阻断后续提交；原响应仍透传。手动额度查询在固定账号容器执行，绑定时 AT-only。
- 联合构建先冻结源码，清单含内容哈希、两个 digest、平台、默认CLI及桥/布局版本；新增 scripts/v3-stack。预检覆盖 Docker NAT 发布端口，无监听 socket 也拒绝冲突；预算按活跃环境内存计算。
- Docker 实验实际发现并修正：pipefail 下 grep -q 的路由检查、root网络服务 HOME/CA 路径、DNS 标签超过63字符、独立模块首次创建工作目录、网络服务退出健康联动。账号DNS名固定为 v3-<deployment SHA256前12位>-account-<环境ID>，完整部署归属用labels。
- 官方 npm CLI2.1.280完整安装后，在 network=none、UID1000/无能力的账号镜像中执行 --version 成功；未执行真实 OAuth 登录或账户调用。之前仅解包的 cli.exe 是500字节启动器，不能算原生二进制证据。
- /tmp/v3-docker-debug7-verify.log：隔离内部网络/空SQLite/合成凭据/明确CLI替身，固定HOME/实例/机器参数、tmux连接重连、重授权取消、原始body与429/API证据、实际账号TLS ClientHello、任务抓包撤销、续聊进程树收口、幂等停止/唤醒及两账号同代理相互独立均通过。此证据基于临时诊断镜像，不能代替最终批次演练。
- Rust完整563单元及既有全部集成通过；最新发送器聚焦3/3通过；Python111/111、Recorder10/10、预检7/7通过。最终变更后正在补足有效完整证据。
- 构建d已过Rust但账号下载旧无限重试被主动停止；e/f正在构建，日志/tmp/v3-image-build-e.log、/tmp/v3-image-build-f.log；f为最新源码候选，未最终验收。

### 尚需完成

1. 最终联合镜像构建及以完整清单重复Docker演练，Compose后台/桥/WS/SSE smoke及旧资源不变核对。
2. 最新源码有效回归、方案与实现逐项检查、Check-All。
3. 真实CLI OAuth/首轮/续聊及可信TLS应用响应只登记后续隔离验证，不能假报通过。
4. 无正式发布/切流/旧账号接管/提交推送授权。

## 第五轮正式批次与管理入口验证

- g 联合批次构建完成；完整账号 Docker 演练通过，增加 HEV 故障会关闭整个发送环境的验证，日志 /tmp/v3-docker-final-verify.log。
- 整套 Compose 启动与会话交换成功，但真实路由演练发现 /runtime/ 尾斜杠未匹配；已增加显式路由，不能把首次演练标成整套通过。最新 h 批次正在编译，日志 /tmp/v3-image-build-h.log。
- manage stop 改为依序停止调度器、账号发送器、网关，始终按产品/部署/角色标签选择，不依赖可能缺失的 Compose release 变量。
- 增加停机 backup：全目录加 SQLite backup API 快照、清单、0700 目标；拒绝运行中备份、重叠目录和覆盖。部署预检/停机/备份测试 10/10，日志 /tmp/v3-final-deploy-tests.log。
- 尾斜杠修正后完整 Rust563单元和全部既有集成再次通过，仅原 PostgreSQL 画像测试依既有规则忽略，日志 /tmp/v3-final-rust-tests.log。Python111、Recorder10、前端 build 的被测内容未变，复用有效证据。
- 新 verify_stack.py 验证统一 HTTP/SSE/WS、资源、注销、stop、backup 和旧哨兵；待 h 构建后执行。
- 当前未进入 Check-All；主流程落地不代表所有设计条目及故障场景已完成审查。没有 Git 提交、推送、生产或真实账号操作。

### 最终聚焦验证完成，转入 Phase 2.2

- h 两镜像联合清单 /tmp/v3-local-check-h.json，冻结源码哈希 8173ed6bac086a23816b7c937479066c070fd4e4175a3f0160d1ac57ead8ec2d，平台 linux/amd64；构建已完成。
- /tmp/v3-docker-final-h-verify.log 全部通过；账号固定实例、HOME、代次、tmux、任务/续聊/抓包取消、两个账号同代理隔离、HEV故障关闭发送器。
- /tmp/v3-stack-final-verify.log 整套 Compose/API/HTTP/SSE/WS/会话/静态资源/stop/backup/旧哨兵通过。测试已结束并删除仅本次随机标签的资源。首轮与并行临时容器移除造成的预检读取竞态失败保留事实，串行复跑通过。
- 最终 h 账号镜像在 network=none、UID1000、cap-drop ALL 下执行官方完整 CLI2.1.280 --version 通过。生命周期场景仍用明确替身，没有真实OAuth或模型调用。
- 最新 Rust全量563单元+全部集成、Python111、Recorder10、部署10、前端build、语法及diff-whitespace证据有效。
- 原两个历史任务的未跟踪文件内容与记录基线一致；用户spec未写入。当前没有提交、推送、发布或生产操作。
- 正在按默认无hold路径进入 inline Check-All，未提前宣称 v3 完整交付。

### Check-All 全部修复（进行中）

- 用户明确授权修复 CHK-001～006、FBK-001～004，已复用合法 inline implement 路由；修复/重检循环不进入普通 follow-up hold。
- 登录代理映射、代理配置权威同步、RuntimeGate 等待容量/负载、Recorder Host/SNI 身份、离线幂等导入、动态 status、浏览器桥白名单、账号独立心跳、执行 token 清理及统一退出已落地。实现与行为验证详见本批次日志，尚不能将未完成的镜像演练写成通过。
- 完整 Rust 回归 568 单元 + 61 集成通过；既有 PostgreSQL 画像测试仍按无外部 DSN 规则忽略，日志 /tmp/v3-fix-all-rust-tests.log。包含完整回环 HTTPS 响应、证书和主机名拒绝及长流取消，不仅是 ClientHello。
- Python 全量 118、Recorder 11、部署 15 通过，日志分别 /tmp/v3-fix-all-python-tests.log、/tmp/v3-fix-all-recorder-tests.log、/tmp/v3-fix-all-deploy-tests.log；TypeScript/Vite 通过证据 /tmp/v3-fix-ui-build.log，语法与 diff 检查通过。
- 随后补齐空实例重复 rebuild 的实际 Docker 查询边界，账号 Runtime 11 项定向复核通过，日志 /tmp/v3-fix-maintenance-recheck.log；最终 Docker 驱动同步采用登录来源 token，并添加重复重建保留 HOME/身份验证。
- local-check-20261012-fix-all-a 构建使用的是该最后维护修正前的冻结源码，只作为中间构建缓存，不能作为最终验收批次。最终批次待重建并执行生命周期、Compose 与真实浏览器验证。
- 浏览器契约核对发现 `/runtime` Cookie 不会发给 `/admin/runtime/logout`；统一退出修正为 `/runtime/logout`，仍受原 admin_auth 保护，旧未启用集成部署返回兼容成功。本地浏览器与 HTTP 演练同步走此路径，不以只清 Cookie 代替服务端撤销；受影响 Rust/前端验证重新执行。

### 全部修复定向验证完成，返回 Check-All

- 最终批次 local-check-20261012-fix-all-b，清单 /tmp/v3-local-check-fix-all-b.json，源码 SHA256 f44a685db2cec46dc57c0a1df93ed97f797f867ee8baee7fed5fb10217bf2bf9；按构建入口的冻结规则重新核对当前产品源码一致。平台 linux/amd64，默认 CLI2.1.280；构建日志 /tmp/v3-image-build-fix-all-b.log。
- control digest sha256:eb597247159f7f9d011ffd564ad9a411bec75bed78235f2ef795c1e466fa46d2；account digest sha256:5553046f624fd9c72204a39cb1d70a91414cb3ad985fb1afc19833f803a88714。
- 最终 Rust 568 单元 + 61 集成再次通过，仅原 PostgreSQL 测试无 DSN 忽略；/tmp/v3-fix-all-final-rust-tests.log。最终前端 TypeScript/Vite 通过：/tmp/v3-fix-all-final-ui-build.log。源码注释事实调整不影响上述行为证据，最终格式/语法/diff 检查通过。
- /tmp/v3-docker-fix-all-b-verify.log 通过：固定 HOME/container、原生 ClientHello 来自账号、HTTP429原始正文与 API 证据、非 root 隔离、tmux 重连、重授权取消、任务/续聊及抓包收口、双账号同代理隔离、网络故障关闭发送器、重复 rebuild 保留环境 ID/machine-id/HOME。
- /tmp/v3-stack-fix-all-b-verify.log 保留首次浏览器失败：驱动把 Input 的 input 与 submit 放同 tick，实际组件使用 passive useVModel，尚未同步父组件输入；未记为通过。驱动新增状态同步等待后，在相同最终镜像重新完整运行，/tmp/v3-stack-fix-all-b-browser-recheck.log 通过实际页面登录/环境/退出/旧 Cookie 重放拒绝、HTTP/SSE/WS 鉴权及白名单、状态、离线 dry-run/两次 apply、停机/备份、旧哨兵状态和数据库不变。修正仅在部署演练驱动，产品镜像输入未变化。
- 两次 Docker 演练均只清理本次随机资源；不操作生产账号、旧系统有效凭据或模型上游，未发布镜像、提交或推送。真实 OAuth/官方 CLI 业务行为与公网实际请求、生产同宿主健康仍属于隔离部署后的验证；本次未构建 arm64。
- 用户 spec SHA256 仍为 26cc5ba38271d857dcac1542327cc7499067133cea86a91f6701d421c7b01f2b，未改写；两个旧任务目录未操作。复用合法 check-all-inline route，修复环不进入普通 Pre-Check hold，开始 full 重检。

### 收尾发现网关绑定入口缺口

- 规范固化前只读核对发现 CHK-007：网关同时要求 `v3-<部署哈希>-account-<环境ID>` 精确主机名和旧 `vibebench-v3-` 前缀，合法运行时绑定会被拒绝。原 Docker 演练直接访问发送器及管理桥，没有覆盖此网关发送入口，先前通过结论的这部分覆盖不充分。
- 已去掉过期前缀并提取网关实际使用的绑定校验；合法短 DNS、其他部署/账号/版本、旧前缀、错误端口、路径、凭据及环境等定向测试通过。Rust 最新完整回归 569 单元 + 61 集成通过，原 PostgreSQL 无 DSN 忽略；日志 /tmp/v3-gateway-binding-rust-tests.log。
- Docker 驱动新增真实网关进程、空数据库、合成账号和绑定接口；将观察请求是否经网关到对应账号发出 ClientHello、错误账号是否拒绝且无重放。仍不访问公网或真实账号。
- 新联合批次 local-check-20261012-binding 正在构建；最终镜像演练与 Check-All 待完成，暂不进入规范写入或提交计划。

### 网关绑定补修验证及并发边界重新讨论

- local-check-20261012-binding 两镜像构建完成，清单 /tmp/v3-local-check-binding.json；真实网关入口到固定账号的 ClientHello、错误绑定拒绝与无重复发送验证通过。
- /tmp/v3-docker-binding-verify.log 保留首次演练失败：取消重授权时 Recorder 上下文切换失败，未记为通过；相同源码/镜像完整串行复核 /tmp/v3-docker-binding-recheck.log 退出 0，全部生命周期与网关入口场景通过。首次切换失败的具体原因尚未定位，不能把一次复核通过当作其根因已修复。
- 用户最新指出 cc2api API 与同账号养号/抓包/CLI 应独立运行。当前 claim/release、清理与恢复仍以 API/CLI 排他设计实现，不能说已经独立；已暂停规范写入和提交收尾，重新核对正常作业与维护操作的边界。
- 已说明拟议边界：普通 API 与 CLI 可并行，CLI 作业之间继续协调；重授权、代理修改、停机/重建仍处理共同环境。养号在 API 活跃时是否也可启动已提出一个调度策略澄清，未据此修改产品并发代码或已确认的 PRD/design。

### API/CLI 调度边界修订（用户已确认）

用户明确要求同账号 API 与普通 CLI、养号、抓包独立，随后“那修改吧”授权实施。已同步 PRD/design/implement/brief：共享 CLI 不阻止 API，只有共享环境维护排他；API 活动不阻止养号启动。进入当前 inline 实现，后续定向验证与 Docker 证据待补充，尚未提交或部署。

共享 CLI 实现已落地：Rust `prepare-cli/exclusive=false` 与旧记录默认排他；Python 保存 driver/tmux/hook/代次，普通清理/续租失败只隔离 CLI，重启恢复不停止发送器；CLI 专用 Recorder 退出标记不健康，公共网络/发送器故障仍退出容器。API 不安装 CLI，CLI 安装在串行认领之后且不持生命周期锁。养号不再因 API 活动/等待顺延，环境维护保留排他。

定向回归通过：Rust 571 单元 + 61 集成 = 632（原有 PostgreSQL 无 DSN 跳过保留，日志 `/tmp/v3-concurrent-rust-tests.log`）；Python 126（`/tmp/v3-concurrent-python-final-tests.log`）；部署 15（`/tmp/v3-concurrent-deploy-tests.log`）；fmt、语法及两仓 diff 空白检查通过。联合镜像正在本地构建，Docker 并行长流/取消/重启/Recorder 故障证据待补充。当前为 Check-All 后的用户反馈修改，已按 Phase 2.1 设 `follow-up-edit` hold，本轮只定向验证，不自动进入 Check-All、Update-Spec 或 Push。

### 并行演练迭代与实际执行修复

新增演练最初暴露了测试夹具问题：截止时间超过 120 秒、不同作业复用 run ID 造成既有证据绑定冲突、迁移后 runs 表新增列但测试 INSERT 没有指定字段、合成 OAuth 缺少 expiresAt、双账号 TLS 场景沿用了长流 HTTP target。均已按真实契约调整，历史失败日志保留，不能将它们称为完整通过。

加强验证要求 exec 正在运行且 tmux pane 出现合成 CLI 文本后，发现并修复产品执行问题：`setsid` 默认可能提前返回导致 Docker exec 假终态，普通与交互执行使用 `--wait`；tmux 登录 shell 重置 PATH，任务注入显式传入选定 CLI 缓存路径；普通任务保存独立 tmux socket，取消与重启收口对应 root tmux server。此后 Python 126 通过（`/tmp/v3-concurrent-d-python-tests.log`）。最后镜像批次为 `local-check-20261012-concurrent-d`，清单 `/tmp/v3-local-check-concurrent-d.json`，冻结产品源码 SHA256 `0685a28931f11abe30498c91a43509031c747ca63fdd7b951c5a334bc80395ab`。旧批次仅留本地，无发布。

`/tmp/v3-docker-concurrent-d-verify.log` 已通过真实网关共享 CLI 租约及 API 长流 + 真实运行中的合成 CLI/养号/抓包、第二次 API、取消、旧 callback、重启、Recorder 故障/修复；后面的双账号测试因夹具目标 URL 沿用 HTTP 而失败。已修正目标并重新运行完整演练，最终日志 `/tmp/v3-docker-concurrent-d-final.log` 结果待确认。

待后续 Check-All 复核的独立兼容问题：真实额度恢复递增 quota_attempt 并改变 `_quota_source`；当前 start_run 的 flows 兼容入口仍为同一 account/task/run，内部目的目录却按 source hash 分代，`_link_directory` 拒绝已有指向不同代次的 symlink。新并行场景使用不同 run 验证普通作业；不能以这些结果证明同 run 额度恢复的证据目录兼容已经通过，需在 v3 全面验收前处理。

### API/CLI 独立调度最终定向证据

最终产品源码与 `local-check-20261012-concurrent-d` 两镜像冻结哈希一致。Rust 632（`/tmp/v3-concurrent-rust-tests.log`）、Python 126（`/tmp/v3-concurrent-d-python-tests.log`）、部署 15（`/tmp/v3-concurrent-deploy-tests.log`）通过；语法/fmt/两仓空白检查通过。Docker 完整演练 `/tmp/v3-docker-concurrent-d-final.log` exit 0：共享 CLI 租约不挡真实网关 API；实际合成 CLI tmux 正在运行时 API 长流与第二次 API 同时发送；CLI 取消、旧 token、重启对账、Recorder 崩溃/修复均保留长流及同容器；双账号隔离、公共网络故障关闭发送器、重复停机/唤醒/重建通过。

整套 `/tmp/v3-stack-concurrent-d-browser.log` exit 0：Compose、HTTP/SSE/WS、真实 Chrome 页面登录/环境管理/退出、旧 Cookie 拒绝、离线导入/备份、旧哨兵容器与数据库不变通过。测试资源已清理；未操作真实账号、OAuth、生产部署、推送或发布，未做 arm64 或性能基准。官方 CLI/公网完整链路仍未验证。已有用户 official-protocol-capture.md SHA256 保持不变。

本轮用户反馈范围的 API/CLI 解耦定向验证完成，Pre-Check 保持 follow-up-edit hold，不自动进入 Check-All/Update-Spec/Push。同 run 额度恢复 flows 换代冲突仍是当前 v3 全面验收前的已知待修项，不能宣称整个 v3 已交付或所有场景已通过。

### 同 run/续聊证据恢复修复与全面复核

用户“下一步”恢复检查。本轮先完成已确认的目录冲突修复：兼容入口固定到账号内 group 目录，各 source 在 executions 子目录独立写入；QuotaGuard 游标登记实际本代文件；run 统计汇总各 run 执行且排除续聊/API；抓包索引和文件列表包含各代及续聊。平铺历史证据保留，错误链接仍拒绝；未部署的旧 v3 原型按 source 绑定的目录不自动接管。

Python 129/129（/tmp/v3-quota-python-tests.log）通过，新增回归覆盖同 run 统计只加一次、旧原生 flow 保留、分代额度游标、历史平铺文件与错误目录绑定。联合批次 local-check-20261012-quota 构建 exit 0（/tmp/v3-image-build-quota.log），清单 /tmp/v3-local-check-quota.json，冻结源码 SHA256 15ac4d8a83b0cde03459ef3cf8c15e774fb1821ebdbe4a55066cc1ae67b79226；最终工作区产品内容复采一致。

首次 Docker /tmp/v3-docker-quota.log exit 1：同 run 恢复、并行长流场景已通过，后续续聊夹具使用了不属于账号子目录的旧路径，被新增目录边界拒绝。只修正夹具路径；产品源码/镜像未变。完整复核 /tmp/v3-docker-quota-recheck.log exit 0，实际第二代合成 CLI 使用原 HOME/cwd 和 --resume 参数；旧统计/原生 flow 不变、新 flow 独立；共享 API 长流、取消、旧 token、重启、Recorder 故障/修复与两账号隔离继续通过。不能以合成 session 参数证明官方 CLI 实际会话或真实额度耗尽已验证。

整套 Compose + Chrome /tmp/v3-stack-quota-browser.log exit 0：统一 HTTP/SSE/WS、静态资源、页面登录/环境管理/退出、旧 Cookie/票据拒绝、备份及离线导入幂等、旧哨兵容器/进程/数据库保持不变。测试资源已清理，docker ps 仅原 new-api/postgres/redis/mysql8。用户 official-protocol-capture.md SHA256 不变。

已清除 Pre-Check hold 并复用 check-all-inline 路由；requested=auto、effective=full、confidence=high，因持久状态/并发/跨包契约变更覆盖整个当前 v3。三件套、实际 DTO/读写链、历史兼容和规范检查通过。复用未变化的 Rust 632、Recorder 11、部署 15 有效证据；本轮 fmt、Python/shell/JS 语法和两仓 diff 空白检查 exit 0。DOC-001 机械同步 design 的实际 runtime 路径、短 DNS 名、env 文件名和 CI 仅本地构建事实，未改变验收。剩余 CHK/FBK 为 0；旧 CHK-001～007、FBK-001～004 的修复与新 API/CLI 行为均有有效回归。

当前严格通过仅针对本地 linux/amd64 与代码契约。上线后由独立测试账号/隔离部署负责人验证官方 CLI OAuth、实际主会话与额度恢复、完整公网链路、同宿主压力；arm64 发布前另在对应构建环境验证。未提交、推送、发布镜像或部署，不标记整个任务已交付。
