# Docker 隔离调研与改造边界

## 证据基线

- 父仓 v3，HEAD 为 72d5e42ad830af781873436f99f1a940b406da31；cc2api 为 ec108e79440c4cca8204ad25cdd6477d2c81dca8。任务意图基线保存 55 个既有脏文件，均不属于本任务交付。
- 规划阶段仅创建资料；截至下述实施验证记录，产品代码已经改造并在本地 Docker 验证，没有本任务的提交、推送、真实模型调用或生产启停。
- vm2api 对照固定提交 3752923cc4244ae6a245d89ffda7a10f20a18b33。临时检出 /tmp/vm2api-compare-20261016 仅为阅读便利，实施不能依赖它存在。

## 外部参考

- [Docker 启动实现](https://github.com/dofastted/vm2api/blob/3752923cc4244ae6a245d89ffda7a10f20a18b33/src/lib/vm/vm-runtime.mjs)：Docker 分支使用按槽位编号派生的普通 UID、cap-drop ALL、no-new-privileges、只读根、32 MiB noexec/nosuid 临时盘、256 进程上限、有限 RAM 且无额外 swap。HOME/run 独立挂载，二进制和 machine-id 只读。
- [出口实现](https://github.com/dofastted/vm2api/blob/3752923cc4244ae6a245d89ffda7a10f20a18b33/src/lib/vm/egress.mjs)：按代理创建 bridge，关闭 ICC/IPv6；SOCKS 模式关闭 masquerade，宿主 NAT 重定向 TCP/DNS 并阻止其他外部转发；本地出口模式另行启用 masquerade。它不是所有模式都禁止直连，也不是无条件一账号独享一个公网 IP。
- [机器资料生成](https://github.com/dofastted/vm2api/blob/3752923cc4244ae6a245d89ffda7a10f20a18b33/src/lib/identity/slot-computer.mjs)：闭源 kin-computer 生成资料；Docker 挂载的 DMI/hardware 位于自定义路径，不能证明完整替换 /sys、CPU 或宿主内核。本任务不复制该机制。
- [官方开发容器](https://code.claude.com/docs/en/devcontainer)：Claude Code 可在开发容器运行，参考配置覆盖持久认证、普通用户与出站防火墙。官方说明网络管理能力用于容器内防火墙，不是 Claude Code 本身必须的权限。该资料没有免封保证。

## 当前定义与消费者

| 文件与位置 | 已有事实 | 需要覆盖的边界 |
| --- | --- | --- |
| orchestrator/account_runtime.py:139、:270、:285 | account_environments 只有一个 container_id，环境/批次按标签核验 | 新角色持久登记、部分失败与启动对账，不能只改创建参数 |
| orchestrator/account_runtime.py:374 | 同一个 root 容器拥有 NET_ADMIN/TUN，挂载 HOME、所有 runtime、CLI 缓存、CA 和 quota-accounts | 拆分可见目录，避免 CLI 同时看到服务秘密或其他账号额度目录 |
| orchestrator/account_runtime.py:415、:840、:863 | root 安装精确 CLI 缓存，root driver 通过 setpriv 启动 UID1000 CLI | 非 root driver、只读缓存、安装与执行职责分开 |
| orchestrator/account_runtime.py:1076 | 网络上下文通过同一个容器内 exec 切换并核对 ACK | 定位网络角色，保持来源/模式/代次校验 |
| orchestrator/account_runtime.py:1130、:1367、:1772、:1976 | 清理、容量、维护和对账均围绕一个容器 | 按环境管理全部角色；CLI 清理仍不能截断独立 API |
| images/account/init.py:45 | root 监督网络和 sender 并采样本命名空间 CLI | 分角色就绪、秘密挂载、进程采样来源需要同步调整 |
| images/account/cli-version.sh | root 写 /cli、/run/v3 和 /var/log | 版本准备放入受控管理角色，业务侧只读 |
| images/account/network-context.py:99、:146 | CA 恢复/发布、日志路径和动态网络监听使用 root 私有目录 | CLI 只收到公钥，保留普通透传与显式 capture |
| cc2api/src/service/runtime_transport.rs:39、:67、:187、:331 | TransportBinding 与 SenderConfig 已定义；配置是每请求重读 JSON；v3 endpoint 有严格名称/批次/代次检查 | 沿用桥协议与发送器实现，不另造 HTTP/TLS 客户端或降低目标校验 |
| orchestrator/process_metrics.py | 在实际容器读取 cgroup 与 UID1000 原生 CLI 的 procfs，私有记录由管理身份写入 | 拆分后仍采 CLI 所在 PID/cgroup；不能拿 sidecar/sender 数值代替 |
| deploy/v3/manage.py:72、:191、:518 | 两镜像联合清单，状态按 account/control 区分镜像；stop/资源预检也依赖角色 | 全部角色纳入同批校验、容量、停止、备份和迁移 |
| deploy/v3/verify_forwarding.py | 已有正式管理桥、双账号、真实 Docker、JSON/SSE、CLI/API 并行和网络故障夹具 | 扩展当前验证入口，补权限/跨账号/启动窗口验收 |

## 设计决定

- 使用同一账号镜像的网络、CLI、发送器三个角色。分开 PID/文件挂载边界，解决单个非 root UID 同时运行 CLI 与 sender 时无法隐藏 sender 秘密的问题；不是增加新业务服务或新 API。
- 网络策略放在账号专属网络命名空间，避免在共享生产宿主上复制 vm2api 的全局 iptables 管理方式。宿主其他容器和规则不变。
- 账号 ID/HOME/机器身份保持；新角色容器 ID 属于可替换运行实例。
- 普通数据面、CLI 网络上下文和控制面沿用现有契约；特权网络角色不能成为 CLI 读写宿主或其他账号数据的入口。
- 资源按角色分配但合计不超过原账号预算；辅助角色开销会减少可分配给 CLI 的内存，必须实测后才能交付。

## 实施前置实验与失败处理

- 验证非 root driver、tmux、CLI 安装/缓存、只读系统和构建临时目录的组合；不能通过恢复 root、放宽控制目录或重开 capabilities 通过测试。
- 验证共享网络命名空间下 CLI 实际观察的 hostname/MAC/machine-id/时区，不能仅凭 Docker 参数声称身份保持。
- 验证网络角色启动前、停止后和重启阶段无直连窗口；可用前不启动任何 CLI/API/OAuth 业务。网络故障保持防火墙拒绝策略，不能自动切换到默认 bridge。
- 测量普通透传、显式 Recorder、sender 流与 CLI 构建的峰值，再冻结角色预算和临时目录容量。不能超过原 RAM/swap 总预算；若无法满足，停止交付并报告具体资源取舍。
- 这些实验用于确认实现机制，不改变已确定的隔离目标；若需要降低目标或扩大资源/宿主权限，先同步方案并由用户决定变化部分。

## 2026-10-16 基础 Docker 前置实验

- 脚本 `/tmp/v3-isolation-preflight.py`，复用已发布 account 镜像，全部随机标签资源已清理。
- 实际 UID1000，CapInh/Prm/Eff/Bnd/Amb 均为 0，NoNewPrivs=1；系统目录不可写，路由更改被拒绝。
- 共享网络下 hostname 与只读 machine-id 保持；PID 命名空间独立。tmux、本地 npm 依赖安装及工作区 C 编译执行通过；/tmp 为 noexec。
- 此实验只证明基础运行机制，不代表完整驱动、出口故障、峰值或真实上游模型验证通过。

## 实施细化

- 隔离布局版本 2 在受控 ensure/显式 rebuild 中登记；仅有身份、尚无实例的行保持布局 0，不能据此运行旧业务。
- 总预算内预留 network 256 MiB、sender 128 MiB；CLI 至少 512 MiB，额外 swap 仅分配 CLI。资源不足明确拒绝。
- CLI 与 network 的 `/flows/api` 使用空只读挂载遮蔽，只将 API 写入目录授予 sender；sender 配置目录 root:GID1001 0750/0640。
- 服务端 OAuth 刷新沿用现有 gateway 显式账号代理，并未迁移 Rust 刷新实现；需实测相同出口及失败不直连。用户浏览器仍不在服务器网络控制范围内。

## 2026-10-16 实施验证记录

以下是首轮命令与实际结果记录，不代替对话中的统一检查报告。首轮任务实际涉及父仓 33 个路径；程序重算原 20 个 tracked 文件 diff SHA256 与 35 个 untracked 文件 SHA256 均与任务基线一致，当时 cc2api 子仓 clean。

| 命令组 | 结果 | 原始证据 |
| --- | --- | --- |
| 后端 unittest discover | 293 项通过 | /tmp/v3-isolation-unit-complete.log |
| deploy/v3 unittest discover | 32 项通过 | /tmp/v3-isolation-deploy-unit.log |
| 账号网络单元 | 8 项通过 | /tmp/v3-isolation-network-unit.log |
| Recorder 单元 | 20 项通过 | /tmp/v3-isolation-recorder-unit.log |
| Python/JS/shell 语法及 diff 格式 | 通过 | py_compile、node --check、bash -n、git diff --check 的工具执行结果 |
| 正式与验证镜像构建 | 通过 | /tmp/v3-isolation-build-release.log、/tmp/v3-isolation-build-c.log；清单 /tmp/v3-isolation-release.json、/tmp/v3-isolation-c.json |
| 实际 Docker 生命周期及旧镜像来回转换 | 通过 | /tmp/v3-isolation-migration-fixed.log |
| 标准 browser + deleted-binding | 通过 | /tmp/v3-isolation-deleted-binding.log |
| 官方 CLI 冷安装资源实验 | 通过，限制见下文 | /tmp/v3-isolation-install-probe.log |
| 标准 forwarding | 失败；补齐测试夹具前提后的诊断运行通过 24 场景 | /tmp/v3-isolation-forwarding-c.log、/tmp/v3-isolation-forwarding-c4/results.json |
| 标准 browser + reauth | 失败；诊断通过重授权与草稿提交，最终停在不适用的故障注入 | /tmp/v3-isolation-reauth-patient.log |
| OAuth 清空代理保护审计 | 失败：测试防火墙截获 1 次直连尝试 | /tmp/v3-isolation-audit-oauth.log |

首轮按上述命令组计 9/12 通过。诊断通过不将标准失败入口计为通过，OAuth HTTP 503 也不代表没有直连尝试。

### 实际运行与资源观察

- 实际 CLI UID1000、sender UID1001，CapInh/Prm/Eff/Bnd/Amb 全 0，NoNewPrivs=1，根只读、PID 独立；CLI 读取 sender 秘密、私有 CA、网络代理环境被拒绝，不能改路由或创建 runtime 父目录文件。
- 官方 CLI 2.1.293 使用本地合成 SSE 工具响应，实际以 UID1000 调用 Bash 并完成 C 编译执行；本地 npm 离线依赖、tmux 与继续执行通过，没有真实模型推理。
- HTTP CONNECT 与 SOCKS5 两账号分别完成原生 TLS 的 JSON/SSE、代理内 OAuth TLS 刷新；验证 CA 仅在带 verification feature 的本地镜像存在。临时诊断脚本预置缺失的 CA 挂载目标，没有修改镜像、生产 TLS 或产品代码。
- 24 场景包含完整字节哈希、Billing 重写、4 个上游 session 池成员、实际 orchestrator 重启时 sender 长流持续、错误证书/域名/代理/绑定拒绝。有效代理场景的 gateway 测试防火墙直连尝试计数为 0。
- 账号默认路由被替换为 bridge 网关后，账号 OUTPUT 默认 DROP 内核计数实际增加 1，未因路由故障转为直连。Docker 内置 DNS 127.0.0.11 与 IPv6 绕行被拒绝。
- 1536 MiB 总 RAM 分配为 CLI 1152、network 256、sender 128 MiB，额外 swap 仅归 CLI。压力实验分配 288 MiB 并写满 128 MiB /tmp 后得到 ENOSPC，CLI cgroup 峰值 552144896 bytes，无 OOM；透传/Recorder/并行 API 的 network 峰值约 83–93 MiB。
- 冷安装实际下载官方 CLI 2.1.293，网络角色限额 268435456 bytes，memory.peak=268697600 bytes，退出 0、缓存 ready、OOMKilled=false。该实验为精确观察安装 RAM 使用，给安装命令显式配置测试 HTTPS 代理，仅转发 registry.npmjs.org；生产 TUN 出口由独立原生 TLS 场景验证，不能把此安装实验表述为同一次 TUN 冷安装验证。cgroup hard limit 可短暂超过，见 Linux 官方文档 https://docs.kernel.org/admin-guide/cgroup-v2.html 。不据此扩大保存预算。
- 使用真实旧批次 ci-38837053861-1 镜像完成单容器→三角色→排空/停机→旧镜像离线回退，保留原环境 ID、HOME、machine-id 和最新凭据；未恢复旧 DB/RT 覆盖新令牌。仅在本地合成账号验证。

### 标准入口失败与诊断边界

- sender 的 /run/v3 为只读目录，测试 CA 的额外 bind 目标 /run/v3/verification-ca.der 未预置，runc 创建挂载点报 read-only file system。临时 wrapper 在私有 sender 目录预置空目标后可继续运行，尚未修改正式工厂。
- reauth/draft 选择环境下第一个容器，拆分后会选中 sender，tmux 命令失败。临时 wrapper 仅将这些测试的业务查询限定到 CLI；完整集合清理不变。
- 页面统一等待 15 秒，对一次真实三角色冷启动不足；临时有界延长后记录授权入口就绪耗时 16.42 秒。该诊断未把准备中的页面视为成功。
- 诊断重授权通过同 SID 重连、真实键盘/粘贴/HTTP 幂等、错登拒绝、关闭取消、管理端重启、草稿恢复/新 SID、产物保留和正式提交。随后草稿取消故障测试尝试以业务用户 mv /usr/local/bin/v3-network-context，因只读系统失败；此外实际 Recorder 上下文已属于 network 角色，旧故障注入前提失效。此后恢复/完整删除路径尚未在标准入口完成。
- OAuth 缺口采用仅本次 gateway 网络命名空间的 REJECT 计数器验证，将 token 域名映射到保留测试地址；清空已绑定账号 proxy_url 后强制 resolve 返回 503，测试规则实际拦截 1 次连接，真实上游未访问。根因路径为 router 允许空代理→account 刷新→oauth_request_client→make_request_client 空串直连。账号网络角色的防火墙不能保护 gateway 自己发起的刷新。
- 所有本地测试容器已由各自 finally 收口；当前 Docker 中 vibebench.product=v3 无残留。镜像保留以供修复后的定向复验，不执行全局 prune。

## 2026-10-16 修复后的标准验证记录

用户选择“修复全部”后，补齐 CA 挂载目标、按角色查询业务容器、为账号启动设置 150 秒有界等待、改用 network 私有 PID 记录故障注入，以及 v3 OAuth 请求前代理保护。修复期间新增回归查询曾误用模型字段 expires_at，查阅 AccountStore 后改为实际列 oauth_expires_at；未改产品 schema。重启测试原先比较旧 Docker 对象缓存，已改为本次 SSE 首字节后的实时状态基线；日志记录旧基线 13:36:36 与本次流基线 13:36:55，重启后实际 sender 保持。

| 定向命令组 | 最终结果 | 原始证据 |
| --- | --- | --- |
| cargo fmt --check + cargo test --locked | 646 通过、0 失败；1 个需要独立 PostgreSQL DSN 的原有测试忽略 | /tmp/v3-isolation-fix-rust.log |
| 账号运行时 unittest | 49 通过 | /tmp/v3-isolation-fix-runtime-unit.log |
| Python/JS/shell 语法与两仓 diff 格式 | 通过 | py_compile、node --check、bash -n、git diff --check 工具结果 |
| 正式与 verification 镜像构建 | 通过；冻结源码一致 | /tmp/v3-isolation-build-fix1-release.log、/tmp/v3-isolation-build-fix1.log |
| 标准 verify_forwarding.py | 25 场景通过，公网直连尝试 0 | /tmp/v3-isolation-forwarding-fix3.log、/tmp/v3-isolation-forwarding-fix3/results.json |
| 标准 verify_stack.py --browser --reauth | 完整通过，含草稿故障恢复及删除 | /tmp/v3-isolation-fix-reauth.log |
| 标准 verify_stack.py --browser --deleted-binding | 完整通过，含 RT 交接、刷新失败与再次创建 | /tmp/v3-isolation-fix-deleted-binding.log |
| 标准 run_local_verification.py + 真实旧镜像转换 | 通过，身份/HOME/最新凭据保持 | /tmp/v3-isolation-fix-migration.log |

- 标准验收使用 `/tmp/v3-unbind-venv/bin/python` 直接运行仓库入口，没有诊断 wrapper。正式清单 `/tmp/v3-isolation-fix1-release.json`，测试清单 `/tmp/v3-isolation-fix1.json`，共同 source_content_sha256 为 `a97c50c0b5ce7db9466661644c4327b09d62f502fee0399c190360803fd60d97`。
- 转发参数为 `--manifest /tmp/v3-isolation-fix1.json --output /tmp/v3-isolation-forwarding-fix3 --cli-binary /root/.nvm/versions/node/v22.21.1/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe`。空串和空白代理均返回 503，AT/RT/有效期及账号状态保持；最终内核计数为 0，有效 HTTP CONNECT/SOCKS5 的 OAuth TLS 刷新各成功 1 次。
- 迁移参数额外指定 `--legacy-control-image ghcr.io/silentflower/vibebench-v3-control:v3-ci-38837053861-1 --legacy-account-image ghcr.io/silentflower/vibebench-v3-account:v3-ci-38837053861-1`。
- 正式两个镜像均没有 verification 标签或 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY 环境键。当前测试容器均已收口；没有生产操作或真实模型推理。父仓当前任务范围 36 个路径，cc2api 仅 src/service/oauth.rs；原 55 文件基线重算通过。
