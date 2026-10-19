# v3 固定账号系统画像

每个账号首次创建支持该功能的 CLI 环境时，从兼容模板中选择一次内核信息和 CPU 型号文本，保存在 `account_environments.fingerprint_json.system_profile`。账号改名、新任务、续聊、停止唤醒及容器重建均复用原对象。

`fingerprint_json.computer_profile` 独立保存版本、机型模板及 DMI 的厂商、产品、版本、系列、序列号、UUID。机型从与已保存 CPU 兼容的模板中选择；序列号与 UUIDv4 各自独立生成。模板显示值由本项目定义，不是原厂实际 DMI 快照，也不调用 vm2api 的闭源生成器。

初始化在 SQLite 短写事务中重读已有行，只补缺失对象，先提交权威值再渲染文件。并发初始化、提交后文件发布失败和持旧行重试均复用同一已提交身份；已有 UUID 重复或对象损坏会拒绝，不换一套值掩盖问题。旧主机名、MAC、machine-id、CPU／内核、时区和语言保持原值。

已有账号需要在空闲时执行环境重建，才会补齐和应用该画像。原设备身份、HOME、项目文件、凭据及绑定保留；活动运行中不能切换。遇到坏记录明确报错，不通过重新随机恢复。

## 覆盖范围

| 入口 | 行为 |
| --- | --- |
| 动态程序的 libc uname、Node os.release、已验证 CLI 2.1.293 uname | 读取固定内核 release/build |
| 常规 open/open64/openat/openat64、fopen/fopen64 及 fortified open | 内核文件精确路径重定向；支持词法归一化和相对目录 fd |
| `/proc/version`、`/proc/sys/kernel/osrelease`、`/proc/sys/kernel/version` | 在上述动态文件接口内使用同一内核画像 |
| `/proc/cpuinfo`、Node os.cpus 型号 | 只读文件覆盖，只替换型号文本 |
| `/sys/class/dmi/id` 与 `/sys/devices/virtual/dmi/id` 下六个受支持文件 | 同一只读 DMI 画像；支持常规动态内容、存在性、可读性、相对目录 fd 及受支持的 chdir 后读取 |
| 动态 stat/lstat/stat64/lstat64、fstatat、statx、access/faccessat、旧 glibc stat ABI | 与内容使用同一精确路径映射，保留掩码、标志、只读权限和错误语义 |
| x86_64 的动态 libc syscall(statx)，包括 Node/libuv 的常规 stat 查询 | 同一映射；其它调用原样传递原始参数和 errno，不读取未传入的可变参数 |
| CPU 数量/拓扑/指令集、cgroup、RSS | 实际值 |
| 直接 uname syscall、静态程序、CPUID、显式绕过库、符号链接别名及未覆盖 sysfs | 仍可能读取真值，不承诺覆盖 |

覆盖只在 CLI 角色加载；网络和 Rust sender 不加载。CLI 仍是 UID1000、cap-drop ALL、no-new-privileges、根只读，画像文件由管理端生成并只读挂载，不增加 ptrace 或网络权限。

模板目前支持服务器 AMD Naples（family 23/model 1）及本地验证的 Cezanne（family 25/model 80）。其它代际明确报错，需要先补充核验。CPU 型号是文本覆盖，CPUID 品牌和其它真实字段可能与型号文本不同；覆盖机制本身也可观察，不能视为无指纹或免封保证。

完整 DMI 仅覆盖 `sys_vendor`、`product_name`、`product_version`、`product_family`、`product_serial`、`product_uuid` 六个名字及对应目录。直接内联系统调用、静态程序、完整 SMBIOS 表、dmidecode 和未列出的 sysfs 路径保持原边界。宿主缺少 DMI 目录时也能通过受支持动态入口读取，不依赖向只读 sysfs 创建新挂载点。

## 核验与恢复

管理端在创建完成及 CLI 任务入口核验真实读取结果。旧 CLI 或校验失败进入 CLI 待对账状态，健康的独立 API 保持可用。新建失败则保留记录并停止本代已创建角色。

账号镜像需要 `vibebench.computer-profile-version=1` 能力；继承标签不等于已加载，实际校验还要核对两类路径的内容、存在性、可读和不可写。新建旧镜像会明确拒绝，已有实例通过显式空闲重建启用，不在普通 API 或 GET 中迁移。画像标记损坏时拒绝 DMI 读取，不静默退回宿主值。

本地仅使用合成账号和联合测试镜像验证，可执行：

```bash
PYTHONPATH=orchestrator python3 deploy/v3/verify_system_profile.py --manifest <本地联合清单>
python3 deploy/v3/run_local_verification.py --manifest <本地联合清单>
```

前者验证默认 sysfs、模拟已有宿主 DMI 及损坏标记，包含 Python、Node、原生 C、相对目录、静态／直接 uname syscall 边界和零／六参数 syscall 透传。后者验证实际三角色、账号生命周期、重建、HOME 与凭据保留；日志分别标注原生探针和 CLI 替身，不能把替身当作官方 CLI 实测。

可在目标 CLI 容器中执行 `uname -r` 或 Node 的 `os.release()` 核对常规读取；这不能证明直接系统调用或 CPU 指令也被覆盖。官方 CLI 的无账号离线验证与真实 OAuth/模型验证分别报告。

`identity_import` 继续读取容器接口，新的导入内核与 CLI 画像一致。已绑定 cc2api 的保存环境不会自动批量改写，此功能也不创建或切换绑定。

回滚需在空闲窗口用旧镜像/配置重建，移除 CLI 的 preload 和画像挂载；保留 system_profile、computer_profile 两个对象，重新启用时复用原值。不能恢复历史凭据覆盖新轮换结果。

## 任务目录

新 run 使用 `/home/node/projects/project-<12位摘要>`，摘要来自环境 ID 和 run ID；同一次运行恢复、继续对话复用原目录，正常结束保留文件。同账号共用 HOME，项目目录之间没有额外的文件访问隔离。
