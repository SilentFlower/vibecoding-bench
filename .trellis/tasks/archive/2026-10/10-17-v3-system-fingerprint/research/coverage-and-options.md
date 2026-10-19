# 内核与 CPU 常规读取覆盖：证据及取舍

## 已确认决定

- 用户选择账号首次生成后固定，新任务、恢复、续聊、重启和重建均复用。
- 用户选择“先覆盖常规读取（推荐）”，已说明直接系统调用、静态程序及 CPUID 仍可能读到真值；完整仿真延期。
- 保持现有 CLI 普通用户、无 capabilities、根只读与网络边界，不为画像放宽权限。

## 2026-10-17 离线实验

实验材料保存在 `/tmp/v3-fingerprint-research-20261017/`；未修改产品源码。基础镜像为本地 `vibebench-v3-account:v3-isolation-20261016-fix1`，不能把它当作当前正式镜像验收。正式发布镜像仍需重跑。

实验只在一次性容器下载依赖和精确 NPM 包 `@anthropic-ai/claude-code@2.1.293`。执行 CLI 时使用 `--network none`，没有挂载真实账号、凭据或生产目录。CLI `auth status` 返回 `loggedIn:false`，退出码 1 属于未登录结果，不是启动失败。没有请求模型。

生产只读检查得到 CPU 摘要：`AuthenticAMD`、family `23`、model `1`、stepping `2`、`AMD EPYC Processor`；不把本机 WSL 的 Ryzen CPU 当作服务器信息。

| 实验 | 结果 | 结论 |
| --- | --- | --- |
| Debian bookworm PRoot 5.1.0-1.3，UID1000，开启 `-k` | uname 与 Node 均报共享库 stat 的 EINVAL；禁用 PRoot seccomp 加速仍失败 | 不能直接采用发行版旧包；本实验没有确定根因 |
| 上游 PRoot `v5.4.1-32-g25dc6a3-25dc6a31`，UID1000、无 capabilities、根只读、默认 seccomp、NNP、断网 | libc uname、静态 C 的 `syscall(SYS_uname)` 与 Node `os.release()` 均返回指定 release；CLI 2.1.293 `--version`、`auth status` 正常 | ptrace 方案能覆盖更深的 release 路径，但尚未验证完整任务、性能和生产宿主 |
| 同上 PRoot 的 uname build、CPU 指令 | build 仍为真实内核值；CPUID 品牌仍为真实 Ryzen | `-k` 单独不足以形成一致内核画像，也没有 CPU 指令仿真 |
| PRoot 临时目录位于 noexec tmpfs | 报临时目录无执行权限，无法启动 | 需要可执行的临时工作区；改用模拟现有 HOME 的可写 bind 后成功 |
| 轻量 libc uname 覆盖库＋只读 `/proc/cpuinfo` bind，UID1000、cap-drop ALL、根只读、NNP、断网 | uname 与 Node 显示指定内核；Node `os.cpus()[0].model` 显示实验替换文本；CLI 2.1.293 `auth status` 输出实验 uname 标记并正常返回未登录 | 已证明官方原生 CLI 会调用这个 libc 接口，以及 Node 的 CPU 型号文件读取可覆盖；未证明全部 Bun CPU 接口或模型请求内容 |
| 同上静态 C 探针 | libc 和直接 syscall uname 都是真值；CPUID 也是真值 | 静态程序不加载覆盖库；必须按边界报告，不能宣称全层替换 |
| Docker 将普通文件直接 bind 到 `/proc/sys/kernel/osrelease` | OCI 初始化拒绝，提示不能挂载到该 proc 路径 | 当前方案不能靠这个 bind 统一内核文件；不得通过 privileged 或放宽 proc 安全规则绕过 |

PRoot 下载源为上游官网指定 `https://proot.gitlab.io/proot/bin/proot`，实验 SHA256 为 `90375de3807212b8f948ff98ed66020f7c9cf7ea447c8734f1af02a2643c8d26`。这是可变上游快照，仅作实验记录，不进入产品供应链。

官方 CLI 2.1.293 ELF 使用 `/lib64/ld-linux-x86-64.so.2`，动态导入 `uname`、`sysconf`、`sched_getaffinity`、`get_nprocs`。仅看到导入符号不等于实际调用；本次实际 uname 标记来自无账号的 `auth status`。

## 方案比较及本轮选择

| 机制 | 适用范围 | 代价与限制 | 本轮决定 |
| --- | --- | --- | --- |
| 只改管理页或外部 uname 命令 | 单个显示/命令入口 | Node/Bun、绝对路径、系统调用可绕过 | 排除 |
| 只读画像文件＋动态 libc 覆盖 | 常规动态程序、Node、已验证原生 CLI 的 uname 调用、CPU 型号文本 | raw syscall、静态程序、CPUID 和未覆盖 sysfs 可读到真值；需补齐文件 API 与子进程回归 | 采用，符合用户选择的尽力覆盖范围 |
| PRoot | 被追踪进程的 syscall/文件路径 | 需要合适版本和可执行临时目录；TracerPid 可观察；完整任务和开销未验证；默认不仿真 CPU | 延期，不为扩大覆盖引入新的进程跟踪层 |
| gVisor | 应用内核及部分系统接口 | 运行时与网络/指标兼容范围更大；Systrap 不等于任意 CPU 仿真 | 延期 |
| QEMU 用户态/完整虚拟机 | 可进一步控制 CPU 指令/模型，完整 VM 可提供独立内核 | 当前无可用 KVM；软件仿真性能与 Bun、工具链兼容性未测，不能说一定不可用或一定可接受 | 延期，不自动更换服务器或运行时 |

## 本轮需要进一步验证的技术细节

- `/etc/ld.so.preload` 的只读 CLI 挂载让动态 CLI 子进程自动加载覆盖，不依赖每个任务入口单独设置 LD_PRELOAD。实施后已在本地 `system-profile-20261017-c` 三角色组合中验证；真实授权和模型请求仍未执行。
- 内核文件通过精确路径的 libc 文件 API 重定向处理，不能根据一次 uname 成功推定 `cat`、Node fs、Bun fs、openat 或相对路径已覆盖。
- CPU 只覆盖型号文本；保持实际厂商、family/model/stepping、flags、数量和拓扑，模板须选择兼容的同代型号。不随机制造新指令能力。CPUID 品牌与型号文本的差异属于用户已接受的边界。
- `/proc/cpuinfo` 只读 bind 已通过；其它 proc/sysfs 不进行笼统覆盖。实际 cgroup/RSS 不经过画像文件。
- 每条支持的文件读取 API 及路径都须有运行证据；未知路径不能默认宣称隐藏。

## 官方资料

- Linux UTS namespace 只隔离 hostname/NIS domain：https://man7.org/linux/man-pages/man7/uts_namespaces.7.html
- uname 的内核字段与部分 proc 入口：https://man7.org/linux/man-pages/man2/uname.2.html
- PRoot 依靠 ptrace，`-k` 与虚拟 bind 由上游手册定义：https://raw.githubusercontent.com/proot-me/proot/master/doc/proot/manual.rst
- PRoot 下载位置：https://proot-me.github.io/
- gVisor Systrap 不依赖硬件虚拟化，但不是 CPU 指令仿真器：https://gvisor.dev/docs/architecture_guide/intro/
- QEMU 用户态可选择 CPU 模型，仍依赖系统调用翻译：https://www.qemu.org/docs/master/user/main.html
- Docker CPU quota/cpuset 属于资源约束：https://docs.docker.com/engine/containers/resource_constraints/

## 项目契约

- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md:393`：设备来源、身份所有权与版本边界。
- `.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md:449`：真实指标、采样证据和隔离转发验收。
- `.trellis/spec/vibecoding-bench/deploy/official-protocol-capture.md:7`：正式协议基线不能由临时 CLI 实验替代。
