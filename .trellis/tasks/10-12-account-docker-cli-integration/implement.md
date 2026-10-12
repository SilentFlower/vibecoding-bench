# v3 实施计划

## 实施前门禁与基线

- [x] 读取最新 PRD/design/research，完成 Brief 评审后才 `task.py start`；再按 trellis-route 的实现路由执行，不在 planning 修改产品代码。
- [x] 以当前已核对 main 为起点建立父仓和 cc2api 独立 v3 开发分支，记录两仓 SHA 和用户脏文件，保留已有 spec 修改和旧任务。不合并 cc2api `origin/v2`，不触发旧 main 的发布链。
- [x] 按当前包/层加载 before-dev 规范，核对实体、DTO 和实际方法；下面的拟新增组件必须先定义，再使用。既有入口与接口字段以源码为准。
- [x] 明确测试使用临时数据库、本地 Docker 项目和假凭据；不部署、不向旧服务调用写接口、不拿生产账号执行首轮请求。

## 1. 前置机制验证与契约定义

- [ ] 验证完整 HOME 挂载、顶层配置原子写、Docker exec 退出、tmux attach/detach/重连、取消后子进程收口；先用本地命令模拟，不发送模型请求。
- [ ] 研究目标 CLI 的项目/session 索引和暂存登录配置行为，记录真实定义；确认每 run cwd、主会话与继续对话的绑定方式。
- [ ] 对 CLI 设备字段与 cc2api device_id 分别确认保存位置、语义、格式及请求使用；建立受信任导入白名单。无证据的字段不猜、不用随机替代。
- [ ] 验证账号容器内网络/Recorder 的 HTTP/flow/ignore 配置切换、上下文 ACK、旧流归属和撤销失败处理，必要时采用作业间重启 mitmdump 进程。
- [ ] 核对并抽取 gateway 发送层与 tlsfp 的真实依赖；本地 mock 验证原始 body、有序 header、状态/响应头和 SSE 字节，不把整个 forward_request 的重试/额度分类搬进发送器。
- [ ] 验证内部传输桥背压、取消、发送前失败/提交不确定的区分、禁止直连回退及重复提交；确认 CLI 非 root 且不继承 NET_ADMIN、控制目录及 CA 私钥分权有效。
- [ ] 验证 Rust 到账号上游代理的路由/DNS不被本地 TUN 二次 MITM、不循环，CLI 透明观察仍有效；使用本地 TLS/代理 mock 核对真实连接路径。
- [ ] 定义 environment、execution、管理桥、导入和占用租约 DTO，明确 owner/generation、幂等键、错误体、时间单位和数据所有权。

## 2. 环境与作业基础

- [ ] 在 `orchestrator/main.py` 增加环境登记、幂等 SQLite 迁移、账号绑定与 run 主会话关联，保留原表和历史可空字段。
- [ ] 账号容器基础准备、常驻 init 和单作业入口分离；复用原 worker 与 sidecar 职责，不创建第二个账号容器。版本缓存复用，作业 cwd/env/临时状态/tmux/结果按代次独立。
- [ ] init 管理网络、DNS、Recorder 与 Rust 发送器健康及退出；CLI 使用显式去能力的非 root 用户，账号容器不挂 Docker socket 或 RT 管理目录。
- [ ] Docker 生命周期以 v3 deployment/environment/role labels 查询和修改；旧 cleanup_stale 不处理固定环境或旧版对象。
- [ ] 统一执行句柄领取、运行、停止、超时和收口；无法确认普通 CLI 收口时只隔离 CLI，保留独立 API；共享环境维护故障保持排他隔离。统计与 transcript 使用主会话新增内容。
- [ ] 适配历史 workspace/flows 读取；旧数据默认不导入在线凭据，离线迁移演练幂等且不重新启用停用账号。

## 3. tmux 登录、凭据和管理接口

- [ ] 改造 LoginManager 和 WS：原 CLI login 在固定环境 tmux 执行；WS 只 attach，断开后保留会话并允许重连；取消/到期真正收口。
- [ ] 登录 commit 校验 CLI 状态，按环境/login 幂等创建或关联 cc2api；失败可重试绑定，不重复创建账号。
- [ ] cc2api 新增受信任 CLI 导入入口，已有 create 默认路径及既有账号有效身份不覆盖。代理/身份/账号状态的编辑由 cc2api 管理 API 负责。
- [ ] 绑定环境使用 AT-only CLI 凭据；受限 RT 管理资料不挂入 worker，刷新遵守 owner -> profile 顺序，排队后再同步，401 不死锁。
- [ ] 同环境重授权保留暂存与取消保护；按现有活跃检查和解绑要求提交，不重置 HOME/会话/有效身份。
- [ ] 新增 cc2api 管理桥及 orchestrator 服务鉴权，白名单 HTTP/WS/SSE 操作，票据绑定会话和账号；密码/AT/RT 不入 URL、日志或浏览器运行数据。

## 4. 账号占用与全部入口适配

- [ ] cc2api 租约区分共享 CLI 与排他维护：prepare-cli 不关闭 API 入场，prepare 原子 draining 并排空 API；两类租约均保持 owner/generation 与 CLI 串行，旧无模式记录默认排他。
- [ ] 保留 weighted slot、FIFO、wait 不计 RPM、粘性会话和 permit 随 SSE 生命周期释放的规则；发送位置变化后请求与响应协议规则不变。
- [ ] 新增账号发送器及内部传输契约，复用 HTTP/TLS 实现，管理端继续选号/改写/重试/额度/响应分类；Prime 推理适配同一发送边界。每账号独立连接池、环境/代次鉴权、有限 origin/path，不接受任意转发地址。
- [ ] 桥接直接传递流并传播取消，permit 保持到远端收口；发送状态不确定不得盲重试，发送器不自行重放，环境未就绪/异常不绕过它直连。
- [ ] 本轮只协调实际推理与管理占用；Prime 推理入口遵守门禁，OAuth resolve 保持可用，遥测发送实现不改。
- [ ] 普通任务、批次、再次运行、继续对话、额度恢复、查询和维护统一租约，默认同账号 CLI 1；排队/额度等待释放资源。
- [ ] 养号只在 CLI 忙或已有正式 CLI 等待工作时顺延，API 活动与等待不阻止养号，保留原启用状态、绑定门槛、终态绑定检查和错误策略。
- [ ] 启动先消费额度证据、确认旧执行与租约、检查环境，再恢复调度；共享 CLI 心跳失联与重启只收口 CLI、保留 API，未确认前禁止下一 CLI；维护失联保持 API 门禁关闭。

## 5. 容器内网络、抓包与额度

- [ ] Recorder 引入每作业原子上下文/ACK，并在请求开始冻结归属；目录/identity/source/generation 校验不通过不放行模型请求。
- [ ] API 发送边界记录请求级观察，和 CLI run/session 分开标明来源；不强制 API 穿过 CLI MITM，不混合证据或推断两种客户端指纹相同。
- [ ] capture 切换覆盖完整 HTTP、原生 flow、索引及 ignore-hosts；首轮、续聊和恢复统一抓包锁与限频。
- [ ] 完成、停止、超时和异常归档观察并撤销诊断；失败时隔离，后续普通任务不能继承完整记录配置。
- [ ] 保留 QuotaGuard 逐窗口真实合并、用满门禁、日志/控制补证、一次原会话恢复与永久认证阻断；不新增阈值功能或主动探测。

## 6. 统一后台

- [ ] 扩展 `cc2api/web/src/api.ts`、router、Accounts 与任务/抓包页面，分别显示账号状态、环境状态、CLI 版本、网关基础画像和额度来源。
- [ ] 终端组件本地打包，登录/续聊复用受控 WS；断线、冲突、额度等待、取消和重连状态与服务端一致。
- [ ] 正式任务、批次、养号、抓包及结果查看在同一入口完成；保留原 bench UI/API 的兼容用途和未配置集成时行为。
- [ ] v3 会话 cookie/票据命名独立，禁止同 IP 不同端口时覆盖旧版 cookie；后端错误映射分别保留 `{error}` 与兼容 bench 错误语义。

## 7. 两个镜像、一套部署入口

- [x] 新增 `images/v3/Dockerfile` 的 control target：多阶段构建 Rust/Vue，最终 runtime 包含兼容 Python 3.12、orchestrator、题库和 UI，按 role exec 一个服务。
- [x] 新增 `images/v3/Dockerfile` 的 account target：兼容 Node/Python/Rust 的 runtime 打包 CLI/tmux/开发工具、网络/Recorder、Rust 发送器及进程 init，验证不同用户和权限。
- [ ] 交付 v3 control/account 两个镜像，独立镜像仓名、workflow 和 v3 标签；联合清单固定父仓/子模块 SHA、平台、CLI、布局、传输桥版本与两个 digest。
- [ ] 新增独立 Compose/env 和 `scripts/v3-stack build|up|status|stop`；gateway/orchestrator 共 control digest，只有 gateway 默认发布宿主端口。
- [ ] up 必须验证端口、名称、网络、realpath 挂载、镜像组合、资源余量和服务配置；建议默认 18080，但实际占用时失败，不停止旧服务或自动换端口。
- [ ] 发布配置没有旧 data/volume/网络/凭据/标签引用；account 即使不是 Compose 常驻服务也验证完整镜像清单，N 个账号各一个容器，总数 N+2。
- [ ] 固定环境 CPU/内存、全局活跃预算、有界唤醒、空闲停止和日志轮转生效；活动 API/SSE/CLI/后台连接阻止空闲停机。stop 先收口动态环境，再只停本部署服务，保留数据。

## 验证计划

实现阶段已运行本地产品回归与合成数据 Docker 演练；完整证据及限制见 progress.md。下面的既有入口按影响执行，不调用真实账号或生产系统。

### Check-All 修复批次

用户已选择修复全部 CHK-001～006、FBK-001～004；复用当前 inline 路由修复并重检，不执行提交、发布或生产操作。

- 登录入口验证短代理 DTO 到环境配置的显式映射；绑定代理以 cc2api 为唯一来源，停止实例在下一唤醒时更新，保留 HOME 与身份。
- 队列等待 RuntimeGate 期间继续占等待位，只计等待负载；覆盖满队列及取消，保持 FIFO 和 weighted slot。
- Recorder 身份域名校验使用既有 Host/SNI 取值契约；quota/login/401 回调只使用当前执行来源 token，旧容器 ID 不再触发清理。
- 环境准备与安装改用账号锁，有界安装及独立续租；慢账号准备不得阻塞其它账号心跳。
- 浏览器桥只转发管理白名单，拒绝内部及编码路径；统一退出撤销服务端会话，复制 Cookie 与旧票据不能重放，页面操作用独立 Chrome 验证。
- 离线元数据导入默认 dry-run，显式保存才落盘；同来源幂等、碰撞拒绝、账号停用、任务归档、旧运行停止，不接收凭据或恢复调度。
- status 展示动态账号容器、实际 digest、环境与租约；不可达占用标为不可用，不输出秘密。
- 补齐回环 HTTPS 应用响应、错误证书/主机名拒绝及取消测试，使用测试编译专用临时 CA，正式客户端维持原有验证。
- 收尾核对发现 CHK-007：实际账号 DNS 已采用部署哈希短名，网关却同时要求旧前缀；去掉冲突的旧条件，保留部署/账号/环境/版本精确绑定。补充合法短名和跨部署等拒绝测试，并通过真实网关进程到账号发送器验证，不能只直调发送器证明网关可用。

修复后联合重建两个镜像，再串行运行 `run_local_verification.py` 和 `verify_stack.py --browser`，完成定向验证后返回 Check-All；最终批次与结果记录在 progress.md。

```bash
python3 -m py_compile orchestrator/main.py orchestrator/quota_protocol.py images/sidecar/recorder.py
python3 -m unittest discover -s orchestrator -p 'test_*.py'
python3 -m unittest discover -s images/sidecar -p 'test_*.py'
bash -n images/worker/entrypoint.sh images/sidecar/start.sh
node --check webui/app.js
cd cc2api && cargo fmt --check
cd cc2api && cargo test
cd cc2api/web && npm run build
```

新增 shell 和 Python 文件加入相应语法检查；新版 Compose 使用明确配置执行 config 校验，env 示例提供占位路径，不解析或打印真实凭据。

| 场景 | 必须观察到的结果 |
| --- | --- |
| 登录断线/重连/取消 | 同一 tmux 会话重连，取消收口，固定 HOME 保留 |
| 已有 API SSE，普通 CLI/养号/抓包启动 | API 与 CLI 同时运行；新增 API 正常入场；CLI 取消及失联不停止 API 流 |
| 已有 API SSE，重授权/代理/停机/重建 | 维护仍关闭入场并排空旧流；忙碌时拒绝无损空闲维护 |
| 共享 CLI 租约心跳丢失，两个服务先后重启 | 只清理旧 CLI；不影响 API 入场/长流；确认收口前禁止下一 CLI，旧排他记录保守关闭 |
| 两个 CLI 入口竞争、排队后 AT 更新 | 仅一项运行，采用最新 AT，无 RT 双刷新 |
| 抓包结束后普通任务、流延迟响应 | 证据仍归原 run，诊断关闭，普通任务不继承完整抓包 |
| 额度等待、reset 未知、永久 auth 错误 | 保留当前暂停/恢复语义，无新探测、无盲目重跑 |
| 假旧容器、占用端口、旧目录 symlink | up 在变更 Docker 资源前拒绝，旧哨兵容器及文件不变 |
| v3 up/stop/失败清理/重建 | 操作仅匹配本部署 labels，镜像组合一致，持久数据保留 |
| 无占用 cc2api 基线请求 | body/header、画像、TLS 客户端选择、SSE、错误及重试保持原规则 |
| 两账号使用同一上游代理 | mock 观察发送来自各自账号容器，各自传输实例/连接池不共享 |
| 桥接断线、已提交但未收到响应 | 不直连回退、不自动重复提交，取消传递且最终释放 permit |
| 账号环境停机、唤醒及活动长流 | 有界等待且受预算约束，健康确认后才发送，活动 SSE 不被空闲停止 |
| CLI 尝试修改路由/控制目录 | 非 root、无网络能力和提权路径，服务私钥/控制资料不可读写 |

本地 Docker 生命周期实验使用独立 test-v3 项目、假登录程序与本地 HTTP mock；不调用真实账户或生产系统。真实 CLI 登录/首轮/续聊及抓包只能在独立账号与隔离部署可用后按 SOP 验证，未执行项保留为未验证。

## 回退与交付

- [ ] 保留 v3 当前 release 清单及数据库 backup，停调度、收口执行和 API 连接、确认没有继续请求，然后恢复 v3 上一兼容 control/account 两镜像组合；不把 v3 数据直接写入旧版数据目录。
- [ ] 记录破坏性边界：同账号双系统刷新、身份覆盖、粗前缀清理、Docker socket 跨部署操作、flow 归属切换、SSE permit 提前释放、桥接重复提交、容器故障直连回退、CLI 获得网络权限、临时配置破坏旧凭据。
- [ ] 完成实现后执行 Check-All、规范更新及 v3 部署手册，明确已执行验证和未执行真实操作。
- [ ] cc2api 与父仓各自按已展示范围提交/推送，父仓 gitlink 固定可拉取提交；镜像发布和生产部署另走授权流程，不自动启动旧账号迁移。

## 用户确认的 API/CLI 独立调度修订

- [x] 增加共享 CLI 租约与持久模式兼容；维护排他行为不变。
- [x] API 不准备 CLI 版本，CLI 版本安装移入认领之后并移出环境生命周期锁。
- [x] CLI 释放/取消/心跳故障/重启不停止独立 API；保存可恢复句柄，失败只隔离下一 CLI。
- [x] 养号忙碌判断移除 API 活动与排队；保留正式 CLI 优先级与现有额度门禁。
- [x] 验证共享/排他门禁、旧记录、旧回调、并行 API 流期间 CLI 取消与重启，并记录实际 Docker 证据。

- [x] 修复同 run/续聊额度恢复的 flows 兼容入口换代冲突：固定组目录、分代 Recorder 和额度游标、聚合统计/抓包索引，保留原始证据。同 run 两代实际运行的合成 CLI、旧文件不变、原 session/cwd 保留及错误链接拒绝已验证；真实官方 CLI/额度耗尽仍需隔离部署验证。
