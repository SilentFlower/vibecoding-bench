# 隔离验收复跑

这些夹具会改写客体的 `/etc/hosts`、`/probe`、`/run/ccrb-criu` 与 `/var/lib/ccrb-criu`，仅用于自有一次性虚拟机。根入口要求 `/probe/.disposable-criu-guest` 的内容精确为 `offline-synthetic-only`。客体需要关闭外部网卡，只启用回环。所有 bearer、账号、证书与模型响应均为合成数据。

## 已验证环境与构建

- KVM，2 vCPU / 3072 MiB，Linux 6.12.115-0-virt，Debian Bookworm glibc 2.36，Python 3.12。
- root 控制器有效能力 `032c11eb`、NNP 1、seccomp 0；业务 UID 1001、能力 0、NNP 1、seccomp 2。
- 按 `images/v3/Dockerfile` 的 `criu-build` 构建 `/opt/ccrb-criu`。Bookworm GCC 12.2.0 的 CRIU SHA 为 `e496fdc39d3d2189710146aff26b38ed8e4da945afd84e56675d9425650084bc`。完整固定来源见上一层 `bookworm-build-provenance.json`。
- 配套 `/opt/ccrb-tls-observer` 的 canonical Python 与固定 C 降权入口；客体内安装 libbpf1、bpftool、iproute2、mount、openssl 和 CRIU 动态依赖。
- 使用 runtime 的固定官方输入，通过现有 `scripts/build-runtime.ts` 生成恢复协议 1 候选。此轮 launcher SHA `fce50a30d739dbc614e450d4d1913208fa35c6373c4f07a3986657393a99261e`，执行体 SHA `564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79`，112843960 字节。候选放到 `/probe/ccrb-runtime`。

## 客体资产

1. 把本目录 Python 夹具复制到客体 `/probe`，写入一次性标记。使用独立磁盘副本，每次关机后恢复实验输入。
2. `/opt/ccrb-criu` 与其 `profile.json` 来自实际目标 ABI 包；保留 `/probe/bookworm-profile.json` 副本。根探针把本轮 canonical Python 文件的实际摘要写入合成 profile，确保阶段日志覆盖当前源码。
3. 将打包的业务 BPF 放到 `/probe/production-filter.bpf`。在客体使用 `cc -O2 -Wall -Wextra -Werror /probe/restricted-launch.c -o /probe/restricted-launch` 编译本目录的测试降权入口，为 Python sender 安装同一 BPF，并降到 UID 1001。产品真实入口测试直接使用 `/opt/ccrb-criu/launch sender`。
4. 编译 gateway：在 `services/gateway` 执行 `cargo test --release --locked --lib native_criu --no-run`。把对应测试可执行文件放到 `/probe/gateway-tests`。本轮 Rust 宿主为 glibc 2.39，客体测试通过 `/opt/criu4/lib` 私有加载器运行；这是测试可执行文件的 ABI 适配。CRIU 和产品 C 入口直接使用 Bookworm 构建。
5. 合成签名候选按现有 release 签名合同准备到 `/probe/releases/v0.1.0-beta.999/<launcher SHA>/`，保存 `runtime-release.json`、`runtime-release.sig`、`ccrb-runtime-linux-x64`。仅把本轮公钥字符串 JSON 放到 `/probe/test-public-key.json`。私钥仅用于一次性签名。
6. 复制 `criu-config.json`、`criu-identity.json`。`/usr/local/bin/account-sender` 使用本目录 `account-sender-test` 包装器。恢复目录属 root，候选只读可执行。

## 顺序运行与断言

每轮使用独立网络命名空间执行一个入口；单个虚拟机同一时刻只运行一轮。

```bash
unshare --net -- /usr/local/bin/python3 -u /probe/controller_probe.py
unshare --net -- /usr/local/bin/python3 -u /probe/bookworm_entry_probe.py
unshare --net -- /usr/local/bin/python3 -u /probe/bookworm_death_probe.py
```

- controller：同一源保持存活，串行 3、并发 4；七笔请求的最终 TLS 正文及规范化请求头摘要与独立接收端相等。核对七个独立会话与两种模型。随后注入五类非法身份/字段、非权威对端、ACK 前后取消、快照污染及模板过期。最终计数、目录、所有权登记归零。
- entry：实际 C 降权入口、业务 BPF 与 NativePool checkout。二十轮交替配对，包含执行体核验、恢复绑定和真实 TLS ready。源进程保持存活。完整 p50 降低至少 50%。最后注入失效登记，完整 submit 沿普通 exec 回退，接收端恰好收到一笔请求。测试末尾物理 live 归零。
- death：通过自有 pidfd 强退独立控制器。恢复命名空间及 worker 的 pidfd 均变为退出，源进程保持存活。新入口回收遗留模板和实例，零模型 POST。

性能摘要保留所有样本，首次建模板单列。`criu_supervisor` 的恢复及熵核验时间位于 root 私有 namespace 日志。gateway 的 `criu_template` / `criu_restore` 日志记录 dump、交接、映像核验、绑定、TLS 各阶段。正式诊断字段只输出白名单安全元数据。原始内存快照、完整正文、证书私钥与原生二进制留在一次性环境。

TLS 接收正文相对 `cc_prepared` 可能因原生最终 CCH 处理变化 3～5 字节。TLS 采集与实收为同一证据层级，二者独立比较。两层各保留摘要含义。

本目录夹具复用了实际隔离验收脚本。后续变化应重新运行受影响入口，并重新记录安全摘要；构建来源和真实环境权限属于各自验收边界。
