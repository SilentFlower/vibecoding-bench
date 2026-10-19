# v3 内核与 CPU 指纹可控性及随机画像

## Goal

在现有 v3 隔离环境中提供按账号固定的随机内核信息与 CPU 型号文本，覆盖常规读取路径并明确绕过限制；说明当前任务目录的创建、复用与持久化规则。

## Background

- 用户要求尽量伪造和随机内核版本、CPU 信息，另外询问每次启动任务时的目录规则；没有要求修改目录行为。
- 正式批次 `ci-38925672032-1`，父仓提交 `1dbb1cbd43a6328eca7392b876b0bdf5fa68f798`。CLI 为普通用户、无 capabilities、根只读，不应为画像扩大权限。
- 宿主只读检查：`/dev/kvm` 不存在，当前 CPU 信息没有 vmx/svm 标志。不能假定现有 VPS 支持 KVM 加速的嵌套虚拟机；软件模拟等其他机制的性能和兼容性尚未验证。
- 身份导入探针通过 Node `os.release()` 读取内核，进入 `canonical_env.linux_kernel` 和 `canonical_prompt.os_version`（`orchestrator/account_runtime.py:2142`、`:2151`）；只替换外部 uname 命令不足以覆盖该路径。
- 现有环境画像首次固化 hostname、machine-id、MAC、时区、语言及资源预算（`orchestrator/account_runtime.py:59`、`:289`）。真实进程指标来自 cgroup/procfs。
- 新 run 使用随机 12 位运行 ID（`orchestrator/main.py:10125`），目录名为 `project-` 加 `SHA256(environment_id:run_id)` 前 12 位（`orchestrator/account_runtime.py:1419`）。同 run 恢复/续聊复用 cwd（`:1049`、`:1878`），正常收尾保留目录和 HOME（`:1303`）。
- 用户选择常规读取覆盖作为本轮范围，完整 CPU 仿真延期；对应产品边界归 R1、R4 所有。
- 离线实验确认 Node 可读取覆盖后的内核与 CPU 型号，官方 CLI 2.1.293 的 `auth status` 调用了被覆盖的 libc uname 并正常报告未登录。该结果不等于真实模型、登录或完整任务已验收，详情见 `research/coverage-and-options.md`。

## Requirements

- **R1：常规读取覆盖。** 覆盖动态链接程序的 uname、Node/Bun 对应内核接口，以及 `/proc/cpuinfo` 和常见内核信息文件的受支持读取；内核 release、build、proc version 使用同一画像，CPU 型号文本按模板生成。分别核查命令输出、系统调用、procfs/sysfs、语言运行时及 CPU 指令路径，报告已覆盖、未覆盖、未验证，不用管理页显示值代替真实容器验证。直接系统调用、静态程序、显式绕过和 CPUID 不保证覆盖。
- **R2：画像生命周期。** 用户已确认按账号首次生成后固定；同账号的新任务、恢复、续聊、重启及容器重建复用已保存画像，不按 run 或启动次数重新随机。同一画像内的字段保持一致。
- **R3：兼容与隔离。** 保持官方 CLI 的任务、登录、续聊、工具执行及现有 API 链路；不自动改换账号、设备 ID、凭据、代理或绑定，不修改宿主真实内核和其他部署。
- **R4：真实观测与边界。** CPU/内存实际限额、CPU 数量/拓扑/指令集能力和 RSS 等证据保持真实；常规读取覆盖范围内的内核字段及身份导入来源保持一致。CPU 型号文本与 CPUID 的差异、未覆盖系统接口仍可能显示真值，必须显式说明，不伪称全层一致。
- **R5：实际验证。** 使用合成数据及无真实模型请求的本地验证，核对候选机制对官方 CLI 的作用、生命周期和失败行为。命令替身通过不能等同原生 CLI 已覆盖。
- **R6：目录说明。** 解释新 run 独立目录、同 run 恢复/续聊复用、持久 HOME 共享及结束后保留。本轮不改变目录命名或新增每 run 文件系统沙箱。
- **R7：安全启用与恢复。** 仅 CLI 角色启用画像覆盖；既有账号首次补齐时保留原 hostname、machine-id、MAC、时区、设备 ID 和凭据。活动运行中不切换画像；配置损坏明确报错，不重新随机掩盖错误；停用或回滚后保留画像记录，重新启用复用原值。

## Acceptance Criteria

- [x] **A1 → R1、R4、R5：** 常规 uname、Node/Bun 读取、内核文件和 CPU 型号文本符合画像；逐路径记录官方 CLI 与直接系统调用/CPU 指令的边界，不伪报未覆盖路径。
- [x] **A2 → R2：** 同账号跨新任务、恢复、续聊、重启和重建的画像一致；不同账号各自保存画像，生成与保存规则明确。
- [x] **A3 → R3、R4、R7：** 实际限额、CPU 能力、运行观测、账号身份和凭据不被随机化覆盖，CLI/API 基础回归通过，不扩大 CLI 权限，活动任务不切换画像。
- [x] **A4 → R5：** 明确性能、兼容性、失败行为和部署前提，不默认发起真实模型请求。
- [x] **A5 → R6：** 对话说明与 `_project_view`、`start_run`、`begin_continue`、`cleanup` 的实际行为一致。
- [x] **A6 → R2、R7：** 老账号只增补一次，损坏记录阻止启用且不重生成；停用/回滚再启用保持相同画像，CLI 角色之外的网络与发送器不加载覆盖。

## Scope Boundaries

- 完整 Brief 已获用户确认，当前进入实施与离线验收；生产配置尚未修改。
- 不承诺隐藏所有容器/虚拟机特征，不把随机化描述成已确认的封号原因修复或免封保证。
- 不实现 CPU 指令级仿真，不更换宿主、Docker 运行时或真实内核，不修改每 run 目录及访问隔离。本轮不发起真实模型请求；构建发布和生产切换另按项目部署流程处理。

## References

- Linux UTS namespaces：https://man7.org/linux/man-pages/man7/uts_namespaces.7.html
- QEMU CPU models：https://www.qemu.org/docs/master/system/qemu-cpu-models.html
- gVisor 架构：https://gvisor.dev/docs/architecture_guide/intro/
- 运行环境契约：`.trellis/spec/vibecoding-bench/backend/account-runtime-v3.md`
