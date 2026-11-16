# 封存 memfd 执行体恢复研究

## 本轮结论

CRIU 4.2 的两处执行体恢复入口完成临时修补后，项目现有封存 memfd 执行体完成三轮恢复。每轮恢复后的本地模拟 Messages 请求均成功，每轮恰好一个上游 POST，预热阶段均为零 POST。

本轮为独立研究补丁与隔离环境验证。生产接入仍需完成实例归属、共享执行映像、恢复握手、管道和 TLS 观测等合同适配。

## 恢复失败根因

原快照日志将执行体保存为 memfd，ID 为 `0x1`。恢复时，`prepare_mm()` 对 `exe_file_id` 调用 `collect_special_file()`，后者只查找 `FD_TYPES__REG`，因此报出 `No entry for reg-file-ID 0x1`。执行体实际打开入口也直接调用 `open_reg_by_id()`。

研究补丁在上述两个入口识别 `FD_TYPES__MEMFD`，打开执行体时复用既有 `memfd_open()`。普通文件继续沿用原有处理。

来源：[CRIU 4.2 内存恢复入口](https://github.com/checkpoint-restore/criu/blob/v4.2/criu/mem.c)、[普通文件查找](https://github.com/checkpoint-restore/criu/blob/v4.2/criu/files-reg.c)、[执行体打开](https://github.com/checkpoint-restore/criu/blob/v4.2/criu/cr-restore.c)。本轮获取的 `criu-dev` 对应入口仍沿用相同的普通文件查找逻辑。

`--inherit-fd` 的资源接管发生于打开文件时。当前错误发生在更早的执行体类型查找阶段，因此该参数单独使用仍会遇到此处失败。

## 实测

环境沿用独立 KVM 测试机：Linux 6.12.115-0-virt、2 vCPU、1536 MiB；外部网卡关闭；研究程序运行在仅有回环接口的独立网络空间；账号及请求均为合成数据。

| 轮次 | 共享执行映像再启动至 ready | CRIU 恢复 | 恢复后模拟请求 | memfd 封存位 |
| --- | --- | --- | --- | --- |
| 普通进程 1 | 1121.36 ms | 120.89 ms | 成功，1 POST | 15 |
| 普通进程 2 | 1074.73 ms | 168.62 ms | 成功，1 POST | 15 |
| 受限进程 | 1072.48 ms | 145.92 ms | 成功，1 POST | 15 |

恢复耗时中位数为 145.92 ms。共享执行映像再启动至 ready 中位数为 1074.73 ms。两种测量口径的中位数之比为 7.37。

恢复耗时口径为 CRIU 命令墙钟时间。恢复后的首次模拟请求耗时为 139.16／148.42／141.14 ms。完整服务端准备还需计入恢复握手、归属校验及 TLS 探针交接。

三轮恢复执行体的 SHA256 均为 `af4cea9e21aa959c5e39c389173ba30ebb19b354b67acfe99164946450e9776d`。恢复后的内存映射与 `/proc/PID/exe` 使用对应的 memfd inode。

受限轮次在恢复后重新读取 `/proc/PID/status`，得到 UID 1001、CapEff=0、NoNewPrivs=1、Seccomp=2。CRIU 控制器运行于隔离测试机的特权、Seccomp=0 上下文。

三轮分别由各自启动的源进程生成快照。每轮成功恢复前均已停止对应源进程。原进程存活时，同一 PID 命名空间的恢复仍因 PID 冲突失败。

## 后续验证点

- 同一个模板多次恢复、并发副本及独立 PID 命名空间。
- 新实例的 worker_id、HOME、管道重新绑定及就绪握手。
- 当前补丁重建 memfd。进程池共享封存映像及 dev/inode 准入需要专项设计与验证。
- 凭据代次、随机状态、定时器及文件状态。
- 原生 TLS 实际发送与采集归属，以及完整准备耗时。

## 证据

- `summary.json`：三轮安全汇总。
- `vm-memfd-patched*-native-result.json`：完整结果。
- `vm-memfd-patched*-dump.log`、`*-restore.log`：完整日志。
- `memfd-executable.patch`：两个恢复入口的研究补丁。
- `patched-binary.json`：研究二进制哈希。
- `probe_memfd_followup.py`、`guest_runner.py`、`run_vm.py`：实验程序与有界虚拟机运行器。

编译依赖解包在本研究目录中。测试虚拟机已关机。
