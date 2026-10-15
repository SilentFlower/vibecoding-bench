# v3 技术设计

## 架构与边界

本任务交付两个镜像：管理镜像与账号镜像。管理镜像分别启动 gateway、orchestrator 两个服务容器，每账号只启动一个固定账号容器；N 个账号共 N+2 个容器。账号容器包含 CLI/tmux、网络/抓包和 Rust 上游发送器，原 worker/sidecar 的职责在容器内分进程管理。以下新表、字段、接口和脚本都是拟新增设计，不是当前代码已有定义。Rust 与 Python 保留内部服务边界；cc2api 现有协议与响应处理留在管理端，实际 HTTPS 发送迁至账号环境。

```text
统一后台 / API（唯一发布宿主端口）
         │
         ├─ cc2api gateway：账号、凭据、选号、请求改写、重试及响应处理
         │       └─ 内部传输桥 → 目标账号容器内 Rust 发送器
         │                              └─ 原 HTTP/TLS 实现 → 账号配置的代理
         │
         └─ 管理桥接 → orchestrator：环境、题库、run、养号、抓包
                                  └─ 同一个账号容器内的 CLI/tmux
                                          └─ 容器内网络/Recorder → 同一账号配置的代理

gateway 和 orchestrator 共用管理镜像、分别启动容器
每账号一个 account 容器，共用账号镜像、各自持久 HOME/网络/状态
```

两条客户端链路共享账号环境与代理配置，但 API 使用现有 Rust 发送实现、CLI 使用真实 CLI，不能声称 TLS 或完整设备指纹相同。此次变化是连接建立的位置和传输实例归属，不能以替换指纹算法或重写协议来代替。

## 账号上游发送器与内部传输桥

管理端先按当前规则取得账号 permit，完成版本画像选择和最终 header/body，再将发送指令送入该账号容器。发送器复用 `cc2api/src/service/gateway.rs` 的方法/路径/query、header 顺序、body 字节及 `src/tlsfp/tlsfp.rs` 的 HTTP/TLS 构建规则；只建立连接、返回原始状态/响应头和流，不选号、不改写 body、不刷新 RT、不实现第二套重试或额度判定。管理端继续执行现有响应分类、被动额度、SSE 处理和重试策略。

内部契约先定义再编码，至少表达 deployment/environment/account、容器代次、请求 ID、目标方法/路径/query、有序头、原始 body 和截止时间；返回区分上游响应、发送前失败及发送后状态不确定。限目标 origin/路径、拒绝任意代理/URL，服务凭据限制到本账号，不由浏览器或 CLI 项目读取。内部鉴权头不混入最终上游请求。发送器不监听宿主公开端口，管理端验证环境绑定、release 和健康，错误不回退为管理端直连。

桥接以原始字节流传递响应，保持背压，不整体缓冲 SSE；客户端断开和取消传到发送器，直到远端连接收口才释放 permit。桥接超时不等于上游未接收；发送器从不自动重放，管理端不得将提交状态不确定的新故障映射为安全重试。进程代次变化不自动续接已有请求。

每账号一个发送器及独立连接池，即使两个账号使用相同代理也不共享。迁移后不再仅用中央的 proxy_url cache key 代表账号隔离。账号环境唤醒在有界等待和资源预算下完成；活跃 API/SSE、CLI 或后台连接阻止空闲停机。维护先关闭入场并排空两条链路，再切镜像或代理。

本轮保证网关推理入口与 Prime 推理使用该发送边界。OAuth 刷新仍由管理端唯一负责，resolve 不等待 CLI 正式占用；遥测发送专项继续暂缓，不把此次迁移描述成所有后台 HTTP 已统一。API 诊断直接在已知发送边界记录受限证据，不强制 Rust 流量穿过 CLI MITM，从而保留现有 TLS 行为。

原 sidecar 将默认路由导向 TUN/MITM；合并网络命名空间后必须显式区分 Rust 发送器到配置上游代理的路径与 CLI 的透明观察路径。Rust 使用同账号配置的上游代理并核对其路由/DNS，不因本地 TUN 被二次 MITM 或形成代理循环。该路径需本地 TLS/代理 mock 验证；不能仅凭“同容器”就假定保留了原 TLS。

## 数据所有权与接口

| 信息 | 唯一负责方 | 另一侧行为 |
| --- | --- | --- |
| 绑定账号的邮箱/UUID、认证状态、AT/RT、代理及网关设置 | cc2api | bench 经管理 API 获取/同步，不直接写 cc2api 数据库 |
| environment_id、持久 HOME、进程、run、题库、抓包、养号计划 | orchestrator | cc2api 经内部 API 查询/操作，不直接写 bench 数据库 |
| CLI 执行占用与网关入场协调 | cc2api 管理租约，bench 持有执行句柄 | 以 account_id、部署 ID、owner、generation 关联 |
| 被动额度事实 | 各链路保存真实观察及时间 | 展示明确来源，管理桥只合并可信同账号/同窗口观察，不猜测 reset |

bench 现有 `accounts` 保留兼容关联及未绑定账号能力；对于绑定账号不再把其中的代理与认证副本当作可独立编辑的权威数据。请求前复查绑定及 cc2api 状态。旧 `warmup_enabled`、run 及 batch 数据保持归属；UI 不提供两个互相覆盖的账号编辑入口。

拟新增 cc2api `/admin/runtime/...` 管理桥，覆盖账号环境状态、登录、任务、抓包、续聊与事件流；白名单操作映射到 orchestrator，不接受任意目标 URL 或任意 shell。拟新增部署内服务凭据，仅服务器间使用，和网页管理员凭据、CLI OAuth 凭据分开。

统一 UI 以现有 Vue 后台为入口，增加环境状态、CLI 登录及任务/抓包页面，复用后端 DTO 与现有任务语义。浏览器不直接访问 Docker socket、cc2api RT 或内部服务管理凭据。WS/SSE 采用经过管理员鉴权派发的短期连接票据或受限会话，票据绑定操作、账号和 session；浏览器的长期管理密码不能放 URL。终端库打进镜像，避免运行时依赖 CDN。

## 账号首次登录与提交

1. 在正式账号不存在时登记不可变草稿环境 ID，创建一个固定账号容器和完整 HOME；固定基础配置后进入待登录状态。
2. 账号容器内创建独立 tmux server/socket 与 `login-<sid>` 会话，由原生 CLI 执行 `claude auth login`，使用固定 HOME、账号代理与当前目标 CLI 版本。
3. 网页 WS 通过 Docker exec 连接 tmux attach；断线关闭 attach 连接，登录进程继续存在。重新连接校验原 sid/owner 后 attach 原会话，不重复执行 login。记录有限会话到期，取消或到期时关闭对应进程并保持草稿可检查。
4. 使用真实 CLI `claude auth status` 校验，然后由服务器读取受限凭据与账号资料。提交以 environment_id/login_id 为幂等来源；cc2api 创建/关联成功而 bench 写回失败时可重新完成绑定，不能再创建重复账号。
5. 新建绑定账号由 cc2api 接管刷新所有权，CLI HOME 原子发布 AT-only 凭据；受限管理目录保存兼容快照，不对 worker 挂载 RT。此后登录环境本身就是运行环境，不删除或复制成第二个环境。

现有 `POST /admin/accounts` 默认行为保持；CLI 导入走新增受信任导入入口，以免 `AccountService::create_account()` 自动生成新身份覆盖 CLI 已确认资料。绑定到既有账号必须校验 account UUID，缺失时按当前邮箱规则处理，不凭名称猜测。

重授权使用相同 worker 和网络，排他锁住账号执行并排空 API，在受限暂存配置中执行 CLI 登录并保留原有效设备配置。取消不覆盖真实凭据；成功原子提交后再更新所有权。CLI 对暂存配置目录的实际支持及身份读写需本地验证；验证失败修正机制，不通过换设备或删除完整 HOME 绕过。原有绑定账号先受控解绑后重授权的兼容限制保留，避免两个 RT 所有者。

## 设备与软件配置

拟新增 `account_environments` 保存 environment_id、bench/cc2api 关联 ID、部署标识、布局版本、基础镜像 digest、固化参数及来源、当前状态和执行代次。新表幂等建立；run 附加环境、主会话关联列允许历史值为空。

- 现有有效 Claude 设备配置沿用，不从每 run、可变账号名或更新后的配置池重新派生。
- hostname、machine-id、MAC、locale、时区、内存约束分别记录；CLI 的 `userID`、`machineID` 与网关 `device_id` 根据实际存储与请求语义建立映射，不能凭相同长度猜测。没有证据的字段显示未知。
- 新 CLI 账号导入只填入已经确认对应的设备身份和真实基础环境信息。软件版本字段仍遵守现有 cc2api 版本画像规则；既有账号不自动改写身份，冲突中止导入并说明来源。
- CLI 版本缓存按版本选择，与 run 的模型、effort、权限快照一致；不能在活动作业中替换全局 CLI。网关软件画像与容器 CLI 版本分开展示，不强制修改现有 `client_version`/`account` 选择方式。
- 同一环境升级容器镜像可以改变实际 Docker container ID，但保留持久环境 ID 和已确认设备状态。实际公网出口由上游代理决定，固定容器不提供固定公网 IP 保证。

## 持久目录与任务执行

```text
data-v3/<deployment_id>/
├── gateway/                          cc2api 数据库及配置
└── bench/
    ├── db.sqlite                     环境、任务及证据元数据
    ├── credentials/                  受限服务管理资料，不挂到 worker
    ├── quota/                        账号真实额度事实
    └── environments/<environment_id>/
        ├── home/                     完整 /home/node
        ├── cli/                      按版本缓存的 CLI
        ├── workspaces/<run_id>/       独立题目项目
        ├── flows/group-<path_hash>/   固定 run/续聊证据入口
        │   └── executions/<source_hash>/  各代统计、HTTP、原生 flow 与额度观察
        ├── runtime/                  job-<source_hash> 脚本/PID/tmux、execution.json 代次证明
        └── controls/                 作业/额度控制，与项目写权限分开
```

账号容器只挂当前账号 HOME、工作目录、网络/证据及必要只读凭据，不挂全局 data、RT 管理目录或其他账号 HOME。CLI 对额度控制只读，Recorder 对观察目录可写；目录按进程用户分权。顶层 `.claude.json` 随完整 HOME 目录挂载，避免单文件 bind mount 阻止 CLI 原子 rename。

账号容器的 init 管理发送器、网络/DNS 与 Recorder 的健康、信号和退出，CLI 仍按作业 exec。网络初始化所需 NET_ADMIN/TUN 不能继承给 CLI：CLI 使用独立非 root 用户，显式丢弃能力且禁止提权；控制/CA 私钥目录不对项目写入开放。原 worker 默认 root 与 sidecar 独立权限不能机械拼接，需通过本地行为测试证明隔离。公共网络或发送器进程退出时环境变为不可发送，不能让 API 绕过网络。CLI 专用 Recorder 退出只标记 CLI 不健康并禁止下一 CLI，不停止独立 API；维护对账可重新建立空闲 Recorder。

拆开环境准备入口、常驻 init 与作业入口；作业通过 Docker exec 指定 cwd、完整 env 与本次句柄启动。tmux、hook、401 marker、退出文件和 watchdog 临时状态都按 source/generation 隔离。现有固定 `/tmp/claude-*` 与 `/workspace` 假设逐项替换。

完成判断使用执行结果和本次主会话新增 JSONL；container.wait 只用于环境维护，不能判断 run。记录原会话、cwd 与观察偏移，续聊和 quota 恢复沿用原 run/session。依赖和工具的全局修改需受控；题目不能无意污染其他 run 的完成判断或后台进程。

## 执行协调与故障收口

bench 统一使用每账号单个正式执行句柄，覆盖所有 CLI 入口。排队普通任务/抓包等待，登录及交互续聊遇忙返回明确冲突；养号低优先级，仅空闲认领。不同账号并行受部署级活跃环境预算约束。

cc2api 的同账号执行租约区分共享 CLI 与排他环境维护，普通 API 与 CLI 独立调度：

- `prepare-cli` 只领取 CLI 串行租约，持久记录 `exclusive=false`；API 入场和 claim 均不等待 API 活动数归零。养号只检查正式 CLI 作业/排队与其它租约，不因 API 活动/等待顺延。
- 既有 `prepare` 仍原子设置排他 draining，持久记录 `exclusive=true`；重授权、代理修改、绑定切换、空闲停止及重建使用此路径。维护不得与 CLI 重叠，claim 仍要求已接受 API 收口。旧记录缺失模式或不可解析时默认排他。
- API/Prime 保留 weighted slot、FIFO、RPM、粘性会话及 SSE permit 生命周期。发送器就绪不依赖 CLI 安装，API 入口不安装 CLI 版本；正常 CLI 版本准备发生在 CLI 串行租约内，避免安装阻塞 API 的环境锁。
- 两类租约均使用 owner/generation、claim/heartbeat/release。取得 CLI 执行权后同步最新 AT，OAuth resolve 不等待此租约；共享 CLI 不修改 API 配置或传输代次。
- 普通 CLI 取消、超时及心跳故障只停止本句柄的 driver 进程组、tmux 与非 root CLI 子进程，归档证据、撤销 CLI 抓包、恢复 hook，再释放共享租约。不检查或排空独立 API，也不通过停止整个容器完成 CLI 清理。清理或租约释放失败记录 `cli_reconcile`，禁止下一 CLI，API 仍使用健康发送器。
- 持久执行记录保存排他模式、driver 句柄、tmux socket 与原 hook。orchestrator 重启对新共享记录只清理旧 CLI，并保留账号容器与 API；cc2api 重启的共享租约需对账才恢复 CLI，但不关闭 API。旧排他/不明记录保守处理，维护心跳故障仍保持全账号隔离。
- CLI 与 API 的额度、账号身份、代理和容器资源仍共享；同容器底层故障可能影响两条链路，调度独立不等于基础设施故障隔离。

## 容器内网络、抓包上下文与额度

原 sidecar 的 Recorder 当前通过进程初始化环境变量确定来源与路径；迁入账号容器并改为显式原子上下文及确认，包含 source、identity、代次、目录、AT-only 只读凭据位置和 capture 配置。API 证据使用请求级上下文，与 CLI 的 run/session 区分。不能以修改 Docker 环境变量模拟动态更新。

请求开始时固定归属，响应写回原上下文；不按响应完成时的最新上下文归档。上下文发布拒绝跨账号目录、旧代次或不一致身份，worker 等待 ACK 后才发请求。

诊断模式切换同时处理 HTTP JSONL、原生 flow writer 及 ignore-hosts；若某项需要重启 mitmdump，只在 CLI 作业间排空 CLI 连接后重启该进程，保留容器、网络、CA 与代理。结束与异常必须关闭完整记录；撤销失败只隔离后续 CLI，不停止独立 API。

QuotaGuard 保留原 source/identity、逐窗口时间合并、真实响应门禁、日志优先/控制补证、未知 reset 等待与一次恢复认领。管理融合展示来源，不把不同绑定或旧身份的额度混在一起；页面刷新不新增主动查询。本轮不增加 roadmap 中的阈值逻辑。

额度恢复的 run/续聊兼容目录固定指向同一组目录，各 source 的 Recorder 与额度游标指向独立 executions 子目录。原 run/session/workspace 不变；统计汇总原平铺文件和各 run 执行文件，不把续聊或 API 统计混入原 run。抓包索引汇总各执行与续聊，原生 flow 文件按代保留，历史平铺文件不删除、不复制计数。继续严格拒绝跨目录链接；尚未部署的旧 v3 原型按 source 绑定的链接不自动改写。

## 两镜像联合构建

| 镜像 | 包含内容 | 运行角色 |
| --- | --- | --- |
| `ghcr.io/silentflower/vibebench-v3-control` | cc2api Rust 网关、Vue 后台、Python orchestrator、题库、内部入口 | gateway 容器或 orchestrator 容器 |
| `ghcr.io/silentflower/vibebench-v3-account` | Node/Claude CLI、tmux/开发工具、Rust 发送器、网络/DNS/mitmproxy、环境与作业脚本 | 每账号一个 account 容器 |

control 镜像多阶段构建：复用 cc2api 前端/Rust 编译方式，最终以 Python 3.12 兼容 runtime 打包 Rust 网关与调度器。gateway/orchestrator 分别 exec 一个服务，不合并成多进程管理容器；orchestrator 独占 Docker socket。account 镜像选择兼容 Node/Python/Rust 与网络依赖的 runtime，打入独立发送器二进制及账号 init；同账号内按进程分权，不挂 Docker socket。

新增独立 v3 构建 workflow 与 `scripts/v3-stack` 入口；联合构建两个镜像并生成 `release-v3.json`，包括产品 release（例如 `3.0.0-rc.N`）、父仓 SHA、cc2api SHA、两个镜像 digest、传输桥协议版本、布局版本、实际 CLI 版本与平台。失败批次不作为可部署完整版本。保留 amd64/arm64 构建目标并核对各平台产物；拒绝混用不兼容管理/账号镜像。

已从核对过的 main 代码建立独立 v3 开发分支，不基于或合并 `origin/v2`。现有 CI 不发布 v3 分支到旧 `latest`，新 workflow 只在 runner 本地构建两镜像并保存版本清单，不推送 GHCR。正式镜像发布、提交与推送仍需进入对应交付流程。

## 独立 Compose 与端口

已新增 `deploy/v3/compose.yml`、`example.env` 与联合构建的 release 清单入口。旧 Compose 不复用，不使用 host networking 或旧外部 network/volume。

- 项目名默认 `vibebench-v3`，可带独立 deployment_id；control 容器使用项目作用域命名。
- 固定环境名为 `v3-<deployment_sha256前12位>-account-<environment_id>`，labels 同时记录完整部署标识、产品、环境与角色；所有 Docker 查找和删除均按这些标签再校验。
- 统一入口建议默认宿主 `18080` → gateway 容器 `5674`；orchestrator 容器 `8000` 仅内部使用。容器内相同端口有独立命名空间，不需要为了避让宿主而改业务监听端口。
- `18080` 是建议默认，不是已经验证空闲的服务器端口。启动前枚举监听端口、全部现有容器的 published ports、目标名称、网络及挂载 realpath；目标冲突则报错退出，不自动选端口、不停止占用者。
- 数据根必须是独立 `data-v3/<deployment_id>`；拒绝 symlink/realpath 指向旧 data、profile、CA 或数据库，拒绝挂载旧 named volume。
- 默认只发布统一入口；调试端口如显式启用，必须独立配置并通过同一冲突检查。管理员会话/服务凭据独立；同 IP 不同端口的 cookie 可能共享，v3 cookie 名和路由 scope 必须与旧版区别。
- 移除环境只允许匹配本部署 label 的对象，禁止 docker prune、按宽泛 bench 前缀删除或对旧 Compose 执行 down/recreate。

## 启停与同宿主资源预算

`scripts/v3-stack build|up|status|stop` 是拟交付的一套入口。up 先预检并校验两个镜像及传输契约，pull/验证 account 镜像，即使它不是常驻 Compose service。启动 gateway 健康后启动 orchestrator；后台对账完成才允许任务或账号发送。

stop 先阻止新任务、收口活跃执行和账号环境，再停止两个 control 容器；数据不删除。status 展示内部服务、账号环境、占用与实际镜像 digest。失败后可再次执行，但不得遗留继续请求的账号容器。

部署默认活跃账号环境上限 1，明确 CPU/内存上限、空闲停止与日志轮转；实际值由目标宿主容量确定并在 release 部署清单记录。worker 固化 memory 约束后不在每 run 动态改变。预检报告可用容量及预算，不足拒绝启动；正式部署后观测旧版健康与资源压力。共享宿主不是绝对性能隔离，必要时 v3 使用另一宿主。

## 迁移、回退及技术验证

默认新数据库和独立测试账号，不自动复制旧有效凭据。支持旧资料的幂等导入机制及去凭据离线演练，但真实旧账号接管必须先停止旧使用/刷新所有者、确认原系统不再使用该账号，再显式导入；本轮不执行该操作。历史目录不删除，旧会话兼容读取保持明确归属。

v3 的升级/回退只在自身部署进行：停止调度、收口进程和连接、SQLite backup API 快照、记录最新合法凭据所有者、切换同批两个镜像和布局、健康检查后恢复。旧系统不作为 v3 数据库回滚目标，也不被恢复脚本操作。

实现前置本地验证：CLI session/cwd 索引、Docker exec/PTY/tmux 分离与退出、持久 HOME 原子写、身份语义映射、容器内权限与 flow/ignore 切换、Rust 发送边界提取、桥接字节保真/取消/背压/不确定提交、SSE permit 持有及租约故障对账。无法证实的机制不得通过猜字段或降低保护条件解决。真实账号登录/请求验证需在隔离部署与账号条件具备后执行，未执行项如实记录。
