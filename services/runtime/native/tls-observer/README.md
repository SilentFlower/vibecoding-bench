# 原生 TLS 接受边界采集器

此目录提供 Linux x64 的 PID 限定 eBPF 旁路观测。原生运行时继续拥有 TLS 握手、HTTP 字节及唯一业务提交。探针在固定 `SSL_write` 共同返回前读取正返回值对应的明文副本。

已准入执行体为 beta.5，SHA256 `af4cea9e21aa959c5e39c389173ba30ebb19b354b67acfe99164946450e9776d`。文件偏移 `0x232d5b3`，指令片段 `4883c4185b415c415d415e415f5dc3`。ABI：RBX 为 SSL 对象，R14 为缓冲地址，R15d 为提交长度，EAX 为实际接受长度。新映像需要重新完成来源、ABI、回环实收及握手对照准入。

## 构建与启用

```bash
python3 native/tls-observer/build.py
python3 -m unittest discover -s native/tls-observer -p 'test_*.py'
```

构建机使用 clang 和 Linux UAPI 头。运行机使用 Python 3.11+、libbpf.so.1、支持 BPF ring buffer 与 PID 命名空间查询的 Linux 内核。实际准入需通过 perf/BPF、读取目标执行体及用户内存所需权限和安全策略检查。容器宿主权限与生产启用独立走上线授权。

平台镜像内置可信采集制品，账号采集字段缺省为开启；显式false保持关闭。环境页“请求内容采集”统一控制入口、组装及TLS采集，debug保存脱敏原文。系统更新与环境重建自动恢复该选择。页面分别显示安装能力与实际探针就绪，单次完整性以请求记录为准。

容器内固定broker持有加载权限，固定启动器派生UID1001、零能力、NoNewPrivs的sender与原生worker。`CCRB_TLS_OBSERVER`自动指向镜像内`client.py`，私有Unixsocket校验SO_PEERCRED、本sender直属关系、进程启动时刻与pidfd；observer在ready前清零能力。独立使用`observer.py`时保留原直属PPID校验。sender为已验证worker后台预备单次探针，业务即时取用。启动及收口各2秒后台预算，退出回收等待上限25ms，后台保存使用两个许可及250ms等待。

正式导出要求canonical已提交且相关路径干净：

```bash
python3 native/tls-observer/export_bundle.py --output /root/project/vibecoding-bench/images/v3/tls-observer --control-policy-output /root/project/vibecoding-bench/services/orchestrator/native_tls_seccomp.json
```

开发快照显式追加`--development`，本地镜像构建显式`--build-arg V3_TLS_OBSERVER_DEVELOPMENT=1`。正式构建默认拒绝开发快照。候选镜像隔离验收：

```bash
python3 native/tls-observer/verify_container.py --image <账号候选镜像> --binary <固定beta.5分发体> --output <独立证据目录>
```

容器关闭外网，仅合成TLS回环；覆盖512KiB、4MiB以上、六worker并发、独立实体/HTTP摘要及ClientHello协议投影。副本超限、丢失或帮助进程故障明确显示原因。

## 私有协议

- 启动参数：`--pid`、`--image`、`--worker`、`--capture`，分别为直属 worker 的实际 PID、精确执行体 SHA、物理 worker ID 和独立采集代次 ID。采集器校验实际 PPID、执行体及固定指令后附着，返回 `schema_version=1,ready=true` 及相同归属。
- sender 收到 `cc_prepared` 后保留其唯一 `x-client-request-id`。在实际响应头到达或取消收口时发送一行 `{capture_id,client_request_id}`。
- 返回对象固定来源 `native_tls_uprobe`、表示 `http_entity_from_tls_accepted_write`，包含实际有序头、实体预览、完整性、实体字节与SHA、整体HTTP字节与SHA、worker/PID、SSL连接及接受次数。`flushed=null`，表示网络刷出证据独立。
- 只处理有唯一 Content-Length 的 HTTP/1.1 `POST /v1/messages`。未知协议、歧义长度、额外字节及错误归属按缺证收口。部分实体与事件丢失的全量摘要和范围均为 null。
- 每事件按16KiB/64KiB/256KiB/1MiB/4MiB/8MiB六档固定容量预留，非阻塞ring16MiB、最多8条SSL连接、头128KiB、每连接正文预览2MiB。Python仅复制32字节事件头和实际accepted字节。独立内核计数核对接受次数、总字节、丢弃、读取失败和超限。正文全量哈希按实际事件增量计算。
- PID通过实际命名空间dev/inode查询，不把宿主TGID冒充容器PID。帮助进程只通过私有管道交付原文。Rust持久化前统一注册秘密、脱敏并应用共同2MiB预算。
- 复制和哈希前按本次Content-Length限定实体范围。同连接后续请求的字节直接丢弃，并保留HTTP_EXTRA_BYTES原因。事件序号缺口后停止本代全部连接解析；最终对账故障会清空头与正文预览，避免跨缺口拼接留下凭据片段。Rust保存层对非HTTP_PARTIAL的不完整证据再次清空原文，截断状态明确记录。

关闭或杀死帮助进程将释放探针、映射及文件描述符。业务由原有worker继续执行。取消守卫使用旧作业的固定ID收口，完整证据优先于迟到的初始快照或缺证回执。

## 异步与准备缺口

每个worker最多一个在途预备。业务取用时的迟到启动结果会释放。worker退役直接取消在途启动并关闭就绪帮助进程。完整TLS实体收口后可在响应流期间预备下一份，worker_idle合并补偿。首次冷worker和连续快速请求可能取得CAPTURE_PREPARING。

初始快照返回queued并记录CAPTURE_PENDING；后台按真实request_id、worker及binding_generation原子更新。最终完整证据优先于迟到初始写入。保存失败按固定原因和作业标识记录安全日志。页面按相同尝试有限重读，关闭或换请求通过取消代次作废旧结果。

采集器私有帧使用schema_version=1和capture_id。实际业务request_id由sender拥有，并通过cc_prepared中唯一x-client-request-id绑定实收HTTP。TLS接受完整性、网络刷出及上游实收分别表示。

seccomp策略来源为Moby profiles固定revision `6049e40058759e8a1673ac1090ec6a7e36b9c9bd`的`seccomp/default.json`，遵循其Apache-2.0许可。按原零能力画像展开能力条件，保留架构/内核条件，仅补`bpf`与`perf_event_open`。业务保持原NoNewPrivs；初始化能力限于SYS_ADMIN及身份降权所需SETUID/SETGID。sender收口通过降权后的pidfd信号进行；观察器由零能力的同UID监督进程响应管道EOF收口，避免清理时再分配帮助进程句柄。两条路径均保持零额外KILL能力及PID归属保护。
