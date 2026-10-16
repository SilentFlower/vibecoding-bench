# 实施计划

## 顺序与交付门禁

1. [x] 规划资料与完整 Brief 经用户确认；task.py start 成功后通过 trellis-route 进入实现，读取 trellis-before-dev。保持 v3 分支与已有 55 文件基线。
2. [x] 先做隔离前置实验：普通用户 driver/tmux/构建，三角色共享网络下真实身份，默认拒绝策略启动窗口，透传/Recorder/sender/CLI 峰值。将观察写入本任务 research，失败不降低目标。
3. [x] 引入角色登记、精确归属及共享预算；保留旧单容器读取与显式转换入口，覆盖部分创建失败/未知角色的恢复。
4. [x] 分拆账号镜像角色与挂载：网络/受控安装、非 root CLI、非 root sender。适配 driver/登录/续聊/刷新、公开 CA 与私有控制目录；CLI/API 无 capabilities、根只读。
5. [x] 在账号网络命名空间实现默认拒绝、代理例外、DNS/IPv6 与管理入站规则；同步网络就绪和 capture 切换确认，异常期间不运行新业务、不重放请求。
6. [x] 适配进程指标的实际 CLI PID/cgroup 与私有观察写入；适配所有 ensure/transport/claim/cleanup/maintenance/reconcile、草稿删除、重授权和凭据交接。
7. [x] 更新联合镜像布局校验、资源预检、状态、停机、备份与回滚，保留现有 UI/JSON/SSE/WS 入口；增加可解释的角色异常状态。
8. [x] 执行下表验证，先聚焦新增边界，再运行后端与既有部署回归；修正后复核冻结源码与最终镜像一致。
9. [x] 完成 Check-All、必要回溯与 Spec 更新，展示精确 Git 范围后按 trellis-push 交付；v3 发布/部署遵循现有 SOP，真实模型验收保持独立。

## 验证场景

| 组 | 场景与路径 | 通过标准 |
| --- | --- | --- |
| V1 权限 | 真实 Docker inspect + CLI/sender id、/proc/self/status、系统目录写入、路由修改 | 普通用户、零有效/允许/可继承能力、禁止提权、系统只读、无 TUN/NET_ADMIN；本账号工作区可写 |
| V2 文件隔离 | CLI 读取 sender 秘密、网络环境、私有 CA、其他账号 HOME/额度、管理控制树；目录逃逸 | 全部拒绝，必要暂停信号只读，挂载不包含其他账号资料；控制发布仍受管理端保护 |
| V3 出口 | 双账号独立本地代理/HTTPS；DNS；直连与 IPv6；管理端到 sender | 每账号仅使用自己的配置出口，来源/请求 ID/响应哈希可关联；绕过路径拒绝，未授权内部访问拒绝 |
| V4 故障 | 代理拒绝/认证错、hev/relay/DNS 退出、删路由、启动前与重启时发起请求 | 无直连窗口、无备用出口、无不确定请求盲重发；失败能定位角色并保留证据 |
| V5 执行 | 真实官方 CLI 离线工具、npm 本地依赖、Python 临时文件、编译执行、tmux 与续聊 | 只读/非 root 模式仍可完成原工作；同 HOME/cwd/session，原题和完成判定保持 |
| V6 并行与收口 | API JSON/SSE + CLI 同时运行，取消 CLI、Recorder 故障、管理端重启 | 健康 API 长流持续；CLI 故障仅关闭下一 CLI，公共网络故障准确关闭入场 |
| V7 认证 | 合成登录/草稿恢复/重授权/绑定/解绑/远端删除/再次创建/后台刷新失败 | 原身份与 AT/RT 所有权正确，不能删除 RT 或覆盖轮换后的合法凭据 |
| V8 迁移与预算 | 旧单容器显式转换、各阶段失败重启、总角色预算、内存/临时盘压力 | HOME/身份不变，全部角色计入预算，超额拒绝，恢复不重复创建或清理错误代次 |
| V9 交付 | 联合清单、实际镜像、stop/status/backup/恢复、统一页面/退出、旧部署哨兵 | 同批完整角色、全部停止才备份、恢复数据完整、其他部署不变 |

## 现有验证入口与拟扩展位置

- Python 单元：python3 -m unittest discover -s orchestrator -p 'test_*.py'。
- 部署单元：python3 -m unittest discover -s deploy/v3 -p 'test_*.py'。
- 网络与 Recorder：images/account/test_passthrough.py、images/account/test_network_context.py、images/sidecar/test_recorder.py，按模块现有入口执行。
- 联合构建：python3 deploy/v3/manage.py build --release <唯一批次> --manifest <新清单>。
- 真实 Docker：扩展 deploy/v3/verify_forwarding.py 与 verify_stack.py，保留合成账号、随机标签资源、本地 HTTP CONNECT/SOCKS/HTTPS，以及 --browser、--reauth、--deleted-binding 等已有场景；新增隔离断言统一复用该夹具。
- 若实际改动 cc2api 的服务权限注释或配置适配，读取其 backend spec，执行相关 Rust 检查；不因目录关联机械重跑无关前端构建。
- 不把新验证参数或计划中的帮助函数当作已存在命令；实施后根据实际 CLI 帮助固化精确复现命令、日志路径、退出码与镜像清单。

## 风险文件与恢复点

- orchestrator/account_runtime.py、orchestrator/main.py、orchestrator/process_metrics.py、orchestrator/resource_budget.py：生命周期、锁序、根/普通用户边界、单账号总预算。
- images/v3/Dockerfile、images/account/*、images/sidecar/start.sh、images/worker/entrypoint.sh：入口角色、只读挂载、网络和 driver；旧 worker 行为继续兼容。
- deploy/v3/manage.py、compose.yml、example.env、README.md、验证夹具及 .github/workflows/v3-build.yml：两镜像交付与完整环境收口。
- webui 或 cc2api 页面仅在现有状态无法表达角色故障时做必要兼容，不扩展产品布局。
- 迁移前保留最新停机备份；每阶段写私有恢复记录。回滚不得恢复旧 RT 覆盖新令牌，不得修改其他部署或删除持久目录。

## 当前状态

- 用户已选择“修复全部”：本轮修复 CHK-001 测试 CA 挂载目标、CHK-002 精确角色选择、CHK-003 启动等待、CHK-004 只读系统下故障注入，以及 FBK-001 v3 OAuth 空代理请求前拒绝。修复后运行标准验收入口和 Rust 全量测试，沿用原 ID 重检，不再逐项确认。

- 已完成请求收敛、源码/规范调研和三件套。
- 用户“可以下一步”已确认 Brief；task.py start 成功，当前会话 inline 实施。
- 基础 Docker 实验通过：UID1000、capabilities 全零、NoNewPrivs=1、根只读、tmux、本地 npm 包安装、C 编译执行、独立 PID、拒绝修改路由。
- 三角色生命周期、文件边界、账号网络默认拒绝、指标及部署管理适配已实现；后端 293、部署 32、网络 8、Recorder 20 项单元测试通过，正式两镜像和仅供验证的两镜像均已构建。
- 实际 Docker 已验证非 root/只读/秘密隔离、官方 CLI 本地工具编译、双账号 HTTP/SOCKS5 的 JSON/SSE、CLI 取消与管理端重启不截断 API 长流、旧镜像转换及离线回退；远端删除后解绑/RT 交接/再次创建的标准页面验收通过。完整日志与测试夹具限制见 research/isolation-evidence.md。
- 第 5 步的 OAuth 空代理缺口已修复：v3 任一部署标识存在时，空串/空白代理在创建客户端前拒绝。标准实际 Docker 验证有效 HTTP/SOCKS5 刷新、空代理拒绝、凭据与账号状态保持，以及 gateway 公网直连尝试计数为 0。
- 标准 forwarding 已通过 25 场景；新正式镜像上的 browser+reauth、browser+deleted-binding、实际旧镜像迁移及离线回退均通过，不依赖临时诊断 wrapper。草稿取消故障后的恢复与完整删除通过。源清单哈希相同，正式镜像没有 verification 标签或构建代理环境。
- 修复后 Rust 全量测试 646 项通过、1 项外部 PostgreSQL 测试按原条件忽略；账号运行时 49 项通过，语法、格式与 diff 检查通过。Check-All 三个维度通过，原 CHK-001～004、FBK-001 闭合，定向命令组 8/8 通过。
- 两仓业务代码已按确认计划提交并推送；cc2api 仅修改 src/service/oauth.rs，既有 55 文件基线保持。规范更新已完成，任务记录随本次确认同步；CI 构建后的 v3 部署与上线核验由 release.md 承接，本轮会话继续执行，当前尚未操作生产部署。
