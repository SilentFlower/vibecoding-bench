# v3 规划依据与范围决定

## 工作区与历史

- 父仓 main：`49e8fb097a527bca9b16af1842b5c524ea5f2da9`；cc2api main：`34ed25fd5a352e823c1ec0269bdfb39b530bae92`。子模块工作区干净；已发现 `origin/v2`，不基于未研究的 v2 分支做本轮设计。
- 已有用户修改：`.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md`；保留，不覆盖或回退。旧持久环境任务取消，遥测任务明确暂缓。
- 本轮仅写新任务规划，未修改产品代码、启动容器、部署、发布镜像或发送真实账号请求。早前应用户要求停止 vm2api `kin-02` 属于独立操作，不代表 v3 部署目标已确定。

## 代码依据

| 位置 | 当前事实 | 本轮影响 |
| --- | --- | --- |
| `orchestrator/main.py:3309`、`:3546` | run 创建 worker/sidecar，cleanup 停止并删除 | 环境与执行生命周期拆分 |
| `:4385`、`:7469`、`:7590` | 登录真实执行 CLI auth login，但直接 Docker exec PTY；commit 清临时容器 | 改为固定环境 tmux，可重连并保留 HOME |
| `:4422` | 重授权暂存 profile，取消保护旧凭据 | 保留事务保护，不直接删真实登录状态 |
| `:3627`、`:3763`、`:3998` | 续聊、额度查询、刷新各有独立容器路径 | 全部统一环境归属，避免只改 start_run |
| `:2507` | 可控参数当前按账号名派生 | 继承有效值并登记不可变环境，不能每次重新选择配置池 |
| `:5132` | 统计扫描 run 下 projects JSONL | 完整 HOME 后明确主会话及本次增量 |
| `:5294` | semaphore 默认 2，仅普通调度覆盖 | 新执行协调覆盖全部入口，同账号 CLI 串行 |
| `:6235` | 养号绑定且启用时认领，主要排除 active warmup | 新增正式工作与网关占用让路，保留终态绑定检查 |
| `:6464`、`:4362` | 启动恢复额度并清理旧登录/续聊容器 | v3 清理按部署 labels，不能清到旧版 |
| `:6970` | bench 同步 cc2api 只传账号、凭据及代理等 | 新导入必须有显式身份契约 |
| `cc2api/src/handler/router.rs:352` | CreateAccountRequest 不接收环境身份字段 | 不杜撰旧 DTO 字段，新增受信任导入入口 |
| `cc2api/src/service/account.rs:664` | create_account 生成随机身份覆盖 Account 字段 | 保留原默认路径，CLI 导入另设受控路径 |
| `cc2api/src/model/identity.rs:373`、`:381` | device_id 为 64 hex 随机串，env/prompt/process 从预设生成 | 长度不能证明它等同 Linux machine-id 或 CLI userID |
| `cc2api/src/service/version_profile.rs:169`、`:206` | 原始 UA 冻结画像，软件字段在请求副本覆盖 | 本轮不改变 client_version/account 的处理 |
| `cc2api/src/service/gateway.rs:2520`、`:2561` | 管理端 HTTP client 构建并发送上游请求，随后处理额度/响应 | 提取发送边界到账号容器，管理端协议/重试/响应规则保留 |
| `cc2api/src/tlsfp/tlsfp.rs:362`、`:397` | 当前连接池仅按 proxy_url 缓存；显式 TLS 配置与代理失败不直连 | 复用传输实现，每账号容器独立进程/连接池，不以相同代理代表同账号 |
| `images/worker/Dockerfile`；`images/sidecar/start.sh` | worker 默认 root；sidecar 管理路由、DNS、MITM 等后台进程 | 合并为单账号容器必须显式隔离进程权限，不能机械拼接入口 |
| `cc2api/src/service/account.rs:265`、`:441` | FIFO 队列，weighted permits，wait 不计 RPM | 新占用在入场层协调，不破坏原权重、SSE 和粘性语义 |
| `cc2api/src/service/account.rs:1466` | managed resolve 使用唯一 OAuth 刷新锁 | 固定 CLI 不持 RT，401 通过既有受信任接口 |
| `images/worker/entrypoint.sh:69` | CLI 版本相同时跳过安装 | 收益是跨 run 持久复用，不宣称旧版每次必重装 |
| `images/worker/entrypoint.sh:1581`、`:1691` | 登录模式空转等 exec；任务已有 tmux | 登录复用 tmux 驱动，进程状态与任务分离 |
| `images/sidecar/recorder.py:18`、`:396`；`start.sh:80` | 记录来源、flow 和 ignore 设置在进程初始化确定 | 上下文切换覆盖全部设置，不能只改环境变量 |
| `.github/workflows/docker-publish.yml` | 当前三 bench 镜像由 main 发布旧 latest | v3 新仓名/独立 workflow，不影响旧标签 |
| `cc2api/.github/workflows/docker.yml` | cc2api 独立构建 main 的镜像 | 联合清单固定子模块 SHA，不将 v3 发布到旧仓名 |
| `orchestrator/Dockerfile`；`cc2api/docker/Dockerfile` | Python 3.12 与 Rust/Vue 分别打包 | 共享 control image，按角色启动两个独立容器 |
| `webui/index.html:11`；`cc2api/web/package.json` | bench 用 CDN xterm，Vue 当前无 terminal 依赖 | 新后台终端依赖打包入镜像，保持 WS 票据鉴权 |

## 必须遵循的规范

- `backend/database-guidelines.md:175`：绑定唯一性、owner -> profile 锁、排队后再次同步、旧绑定终态保护。
- `backend/database-guidelines.md:498`：被动额度 source/identity、未知 reset、原会话恢复、控制文件挂载和永久门禁。
- `deploy/official-protocol-capture.md:112`：抓包全局串行/间隔/冷却；固定环境需改为作业与连接收口，不删用户当前修改。
- `deploy/image-build-push.md:90`：worker/sidecar 不在常驻 Compose 服务列表也要验证镜像；`:499`：managed CLI 必须移除 RT。
- `cc2api/backend/service-architecture.md:178`：weighted slots/FIFO/RPM admission 顺序；协议 detector、session 池等保持原契约。
- `cc2api/protocol/claude-code-profile-upgrade.md:1458`：已有 293/280 软件画像及管理展示，本轮不通过统一 UI 强制换画像。
- `vibecoding-bench/deploy/auth-design.md`、`cc2api/frontend/frontend-guidelines.md`：统一管理桥不能让内部凭据到浏览器；WS 不天然经过 HTTP middleware，重连必须检查身份。
- `cc2api/deploy/deploy-guidelines.md`：子模块提交与前端构建产物；实际推送/部署时走相应 SOP。本轮仅规划。

## 已收敛决定

固定 Docker、原生 CLI tmux 登录、cc2api 管理融合、统一打包/启停、新旧隔离、大版本叫 v3、阈值放后续 roadmap 来自用户明确选择。最新要求确定两个镜像：管理镜像与账号镜像，每账号一个容器；用户进一步选择「账号容器实际发送 HTTPS」，取代旧的中央直接发送边界。管理端协议/响应规则保留，账号发送器复用现有 HTTP/TLS，不改成 CLI 推理。

前次用户把打包数量交由助手权衡，助手曾建议一份发行镜像；用户随后明确要求分开为管理/账号两个镜像，该最新选择优先。未实施三镜像或综合镜像草案，不保留待决数量问题。详细决定与传输证据见 `research/packaging-options.md`。

不重新追问当前会话及任务文件已有决定；后续 CLI 语义、镜像兼容和切换机制通过本地证据验证。不存在已授权的生产接管、发布或真实账号实验。
