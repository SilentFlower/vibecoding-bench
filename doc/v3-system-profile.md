# v3 固定账号系统画像

每个账号首次创建支持该功能的 CLI 环境时，从兼容模板中选择一次内核信息和 CPU 型号文本，保存在 `account_environments.fingerprint_json.system_profile`。账号改名、新任务、续聊、停止唤醒及容器重建均复用原对象。

已有账号需要在空闲时执行环境重建，才会补齐和应用该画像。原设备身份、HOME、项目文件、凭据及绑定保留；活动运行中不能切换。遇到坏记录明确报错，不通过重新随机恢复。

## 覆盖范围

| 入口 | 行为 |
| --- | --- |
| 动态程序的 libc uname、Node os.release、已验证 CLI 2.1.293 uname | 读取固定内核 release/build |
| 常规 open/open64/openat/openat64、fopen/fopen64 及 fortified open | 内核文件精确路径重定向；支持词法归一化和相对目录 fd |
| `/proc/version`、`/proc/sys/kernel/osrelease`、`/proc/sys/kernel/version` | 在上述动态文件接口内使用同一内核画像 |
| `/proc/cpuinfo`、Node os.cpus 型号 | 只读文件覆盖，只替换型号文本 |
| CPU 数量/拓扑/指令集、cgroup、RSS | 实际值 |
| 直接 uname syscall、静态程序、CPUID、显式绕过库、符号链接别名及未覆盖 sysfs | 仍可能读取真值，不承诺覆盖 |

覆盖只在 CLI 角色加载；网络和 Rust sender 不加载。CLI 仍是 UID1000、cap-drop ALL、no-new-privileges、根只读，画像文件由管理端生成并只读挂载，不增加 ptrace 或网络权限。

模板目前支持服务器 AMD Naples（family 23/model 1）及本地验证的 Cezanne（family 25/model 80）。其它代际明确报错，需要先补充核验。CPU 型号是文本覆盖，CPUID 品牌和其它真实字段可能与型号文本不同；覆盖机制本身也可观察，不能视为无指纹或免封保证。

## 核验与恢复

管理端在创建完成及 CLI 任务入口核验真实读取结果。旧 CLI 或校验失败进入 CLI 待对账状态，健康的独立 API 保持可用。新建失败则保留记录并停止本代已创建角色。

可在目标 CLI 容器中执行 `uname -r` 或 Node 的 `os.release()` 核对常规读取；这不能证明直接系统调用或 CPU 指令也被覆盖。官方 CLI 的无账号离线验证与真实 OAuth/模型验证分别报告。

`identity_import` 继续读取容器接口，新的导入内核与 CLI 画像一致。已绑定 cc2api 的保存环境不会自动批量改写，此功能也不创建或切换绑定。

回滚需在空闲窗口用旧镜像/配置重建，移除 CLI 的 preload 和画像挂载；保留新增的 system_profile 对象，重新启用时复用原值。不能恢复历史凭据覆盖新轮换结果。

## 任务目录

新 run 使用 `/home/node/projects/project-<12位摘要>`，摘要来自环境 ID 和 run ID；同一次运行恢复、继续对话复用原目录，正常结束保留文件。同账号共用 HOME，项目目录之间没有额外的文件访问隔离。
