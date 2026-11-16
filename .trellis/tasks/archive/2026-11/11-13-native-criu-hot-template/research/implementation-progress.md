# 实施进度与恢复入口

当前任务已获确认并启动，路线 inline。确认请求8a05ea5e-5eea-4507-a096-faff523d4d7d，claimed=true且started/completed回执已写入；该完成只表示进入实施。

## 已实现

- 固定CRIU4.2来源、memfd补丁、构建及目标ABI包配方。
- runtime恢复绑定协议1；Bun1.4.3固定revision的原生fork标志、UUID池及主realm随机源复位。
- 每账号受信控制器：零业务模板登记、私有快照和冻结目录、文件完整性、PID/挂载空间、SCM_RIGHTS两阶段存活句柄和管道交接。
- NativePool后台预算内种子、模板优先恢复、业务前exec回退；真实PID、独立退出等待及取消时许可所有权。
- 同身份稳定代理Arc；账号/内核代次及维护清理。
- TLS登记表与目标活动PID空间采集；最终证据继续使用外部物理PID。
- 显式部署开关V3_NATIVE_CRIU=1、额外108MiB/进程代码预算、控制器cap/seccomp预检、降权入口及源包/Docker接线。
- 入口umask077控制目录显式0750；普通回退前必须核验降权入口及业务BPF。
- 最新清理修复：broker/controller跳过已在finally中等待物理退出/排空的任务，防止关闭时二次取消。

## 验证与剩余工作

验收映射、完整命令及结果见 acceptance-evidence.md。Bookworm真实CRIU包与实际entry已通过二十轮配对、失效模板完整submit回退、控制器强退与重启回收。最新20轮与阶段耗时见bookworm-entry-paired-summary.json。关闭管道析构告警修复后的实际入口运行通过。

runtime类型与187单测通过。集成第一轮49通过、1组失败，组内两项超时单独重跑通过。gateway全量881通过、9忽略；其后变更定向4通过，隔离release测试通过。orchestrator1240测试OK、skip1；部署当前52测试通过。控制器12、构建3、TLS观测14通过。

部署开关已贯穿compose/example.env/manage及orchestrator，默认0，非0/1拼写在部署预检拒绝。target ABI包与源码束SHA已逐项核对。源码/快照/熵/TLS/取消的安全合同由Check-All及Spec完成链继续复核。

最终质量检查及FBK-001修复重检通过，Spec已同步。真实pidfd EOF日志回归先失败后通过，普通Child错误/EOF/截止回归通过。源码与正式TLS清单已按用户确认的合并计划提交并推送，正式清单development=false且代码文件SHA保持已验收值。生产启用与权限变更沿后续上线流程。

## 临时环境及复跑

所有隔离资产在/tmp/flower2api-criu-research-9amnj8l_/。memfd-followup/run_bookworm_{controller,entry,death}_vm.py顺序使用自有无网卡KVM2CPU/3GiB镜像；每轮停机后e2fsck、debugfs写入并回读核SHA，启动后自动关机。已将受guard保护的核心夹具保存到research/verification，并用实际Bookworm产物复跑。

产品CRIU和C入口为DockerBookworm/GCC12编译，直接在客体glibc2.36运行。Rust宿主release测试借助客体私有glibc运行，其ABI适配仅属于实验夹具。候选runtime-restore-v1的launcherSHA fce50a30d739dbc614e450d4d1913208fa35c6373c4f07a3986657393a99261e、imageSHA 564019c9560e960e96875c9663975491534b27c789ea3d23e5c13309ff293c79，image112843960B；manifest的bridge_sources对应当前TS源码。

共享文件包含另一会话的native-error-diagnostics改动。Git计划需要按实际归属处理，并核对跨任务引用依赖。
