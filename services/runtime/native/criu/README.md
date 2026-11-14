# 固定 CRIU 恢复工具

本目录保存 CRIU 4.2 的 memfd 执行体恢复补丁。来源归档、补丁、构建二进制与编译器版本写入构建清单。

封存 memfd 执行体的快照使用 MEMFD 类型。补丁使执行体收集与打开遵循实际类型，并通过专用 `ccrb-executable:ccrb-native-runtime` 资源接入模板持有的同一背板。FD、执行体和内存映射统一使用该 inode。原有私有脏页、匿名内存及 FD 偏移、状态和别名继续按 CRIU 规则恢复。

构建环境需要 GCC、make、patch、pkg-config、protobuf 及 protobuf-c 编译器与开发包、libnl-3、libcap、libnet 和 uuid 开发包。依赖需与目标系统 ABI 匹配。

```bash
python3 services/runtime/scripts/criu/build.py --archive /受控目录/criu-v4.2.tar.gz --out /全新目录/criu-build
```

省略 `--archive` 时下载固定 HTTPS 来源并校验摘要。`--dependency-prefix` 可指向已经解包的私有开发依赖目录。构建工具只在新输出目录下工作；失败清理本轮输出。输出包含可执行文件、来源清单、私有构建日志与上游许可文件。

恢复控制器的实际 seccomp、能力和命名空间要求需通过目标环境预检。业务 worker 使用原有受限身份。

来源：[CRIU v4.2](https://github.com/checkpoint-restore/criu/tree/v4.2)。

## 账号恢复入口

`entry.py` 是可选的账号可信入口，拥有同账号的模板与 TLS 采集登记。业务 sender 与 worker 仍为 UID1001、能力全零、NoNewPrivs1、seccomp2。固定 C 入口安装构建时冻结的业务过滤器后降权。恢复控制器需要 seccomp0。

隔离 Linux6.12 实测的控制器能力集合为：`CHOWN DAC_OVERRIDE FOWNER KILL SETUID SETGID SETPCAP NET_ADMIN SYS_CHROOT SYS_PTRACE SYS_ADMIN SYS_RESOURCE SYS_TIME`。其中 NET_ADMIN 用于恢复套接字缓冲，SYS_TIME 用于新的时间命名空间偏移，FOWNER 用于 memfd 权限恢复，KILL 用于对受限目标暂停与继续。控制协议只接受已登记模板与实例标识。种子 PID 必须是权威 sender 的直属受限进程，并匹配固定执行体与零业务模板标记。

控制器先移交命名空间 pidfd，sender 持有后发送 ACK。之后才创建恢复 worker。管道通过 SCM_RIGHTS 直接交接。连接关闭触发命名空间退出；容量许可保留到 pidfd 确认实际退出。关闭操作会等待已经开始的清理完成。

模板保存在独立 `/var/lib/ccrb-criu` 私有磁盘挂载，目录0700、映像0600。控制 socket 位于 `/run/ccrb-criu`，父目录显式0750、socket0660，仅固定业务组可访问。快照包含账号内存状态。账号身份、凭据、代理、配置或内核变化会撤销原模板租约，已受理实例按原生命周期收口。

冻结文件记录 SHA256 与包含 ctime 的文件身份。恢复前核对完整文件集合、inode、大小、时间、所有权及权限。每实例复制私有目录，在挂载命名空间映射到冻结逻辑路径。原生所需权限与时间元数据在副本中恢复。

同账号模板保持原代理引用。恢复后保留原生构造和发送栈，每轮仍使用独立原生请求上下文。BoringSSL fork 标志、UUID 缓存与主执行域随机状态按固定 Bun1.4.3 配方重新建立。运行时版本、执行域结构或随机源画像变化会拒绝恢复。

模板登记时核验实际执行体摘要、大小与四项 seal，并由可信控制器固定为 root 所有、0555。内容 seal 与权限控制分别执行。模板持有只读 FD，种子退出后仍可维持背板存活。每个实例重新打开同一 inode，保留独立打开文件描述；模板撤销后等待在途实例收口，再释放模板引用。

CRIU 共享分支拒绝同名的其他 inode、错误类型、大小、封存及元数据。监督进程在恢复暂停期核对实际 exe 和执行体映射，Rust 在业务投递前再次核验实际 SHA、大小、seals 和缓存映像的 dev/inode。共享路径跟随现有 CRIU 开关，构建画像 `shared_memfd_restore=1` 为配套能力条件；旧工具或准入失败沿原截止回退普通共享映像 exec。

## 失败诊断

模板建立和恢复失败先记录 `criu_failure` 结构化事件，再沿原 finally 清理。摘要包含受控阶段、异常类型、可用 errno、CRIU/子进程退出码、规范模板/worker/实例 UUID 与受限源码位置。监督进程先把本实例首错写入私有 `failure.json`，控制器在清理前汇总；例如 `upstream.stage=criu_restore`、`upstream.criu_returncode=27` 与当前 `stage=report_decode` 分别表示原CRIU失败和后续空报告解码失败。

诊断只提取固定 CRIU 日志末尾最多16KiB中的错误/警告分类及受控源码位置，最多8项。`log_status` 区分 `available_tail/missing/invalid/not_applicable`，`upstream_status` 区分 `available/missing/invalid/not_applicable`。分类用于保留证据，根因需结合实际阶段判断。原始异常、stderr、路径、环境、配置、凭据、正文与内存快照排除在摘要之外。

摘要保存在 `/var/lib/ccrb-criu/failures/<UUID>.json`，复用账号root私有持久挂载，保留最多32条、每条8KiB，目录0700、文件0600。读写逐级拒绝链接，文件必须属于当前可信UID、单链接且为普通文件；轮换只处理合法受控摘要。`persistence=DIAGNOSTIC_STORE_FAILED` 表示普通日志仍包含摘要，私有留存失败；`DIAGNOSTIC_CAPTURE_FAILED` 表示取证自身失败。诊断失败继续原异常和资源清理，正常取消保持原语义。

sender的“原生第二 worker 预热”计时属于后台补暖。现有空闲进程可用时，业务直接领取该进程；空闲耗尽且补暖进行中时，等待计入 `checkout_ms` 与 `prepared_ms`。后台CPU消耗与请求等待分别观察。

## 镜像与启用

```bash
python3 services/runtime/scripts/criu/export_bundle.py --output /全新目录/criu
python3 /全新目录/criu/package.py --source /全新目录/criu --out /全新目录/ccrb-criu
```

账号 Dockerfile 在目标 ABI 内构建工具，并保留完整来源、二进制摘要和许可。`images/v3/criu` 是对应镜像输入。TLS 采集束按其既有导出流程同步。

部署开关缺省及空值为开启，显式 `V3_NATIVE_CRIU=0` 关闭；账号指纹 `native_criu_enabled` 缺省为true，显式false持久关闭。镜像标签 `vibebench.native-criu=1` 与独立恢复内存额度共同决定恢复入口。有限额度不足时保持普通exec。恢复内核需要协议1，默认配套beta.6，当前准入映像为 `564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79`、112843960字节；持久选择沿现有内核激活流程保持。旧内核继续正常exec。环境卡片按实际入口与同代遥测展示模板状态。

共享版本第一阶段继续保留每个恢复副本108MiB的预算余量。有限账号最低 sender RAM 仍为 `256 + max_workers × (192 + 108)` MiB；无限账号受显式 worker 上限约束。实际映像分配按唯一 inode 计量，预算调整以完整负载的峰值和切代重叠结果为依据。

入口先核验降权加载器与业务 BPF。该基础准入失败会终止启动。恢复权限或环境预检失败时，受限 sender 沿普通 exec 运行。模板、恢复或绑定失败在业务投递前清理，再沿原请求截止回退。每笔业务维持一次模型提交。

生产启用需要对应环境预检及独立部署授权。关闭开关并按原角色重建流程排空后回到共享映像 exec。
