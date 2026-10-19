# 实施与验证计划

## 开工门禁

- [x] PRD、设计与本计划收敛后生成 Brief，完整展示并取得首次开工确认，再运行 `task.py start`。
- [x] 进入 `trellis-route(target=implement)` 与 `trellis-before-dev`，读取本任务相关规范；遵循单会话执行，不擅自派发子代理。
- [x] 保留基线 55 个非本任务文件；仅认领本任务材料及实际功能文件，不混入 Flower 升级或历史任务。

## 顺序实施

1. [x] 在画像模块中实现有限模板、字段校验与一次性持久化。新对象嵌套于 fingerprint_json，保留旧身份；补齐在空闲且受现有锁保护时执行。实现前读取实际实体、数据库与 lifecycle 接口，不猜字段。
2. [x] 核对 Debian 内核模板、服务器 AMD family 23/model 1 的同代 CPU 型号候选来源；模板成套、长度受限，CPU 数量/拓扑/flags 等真实字段不变。补充旧账号、改名、重建、坏配置的有意义测试。
3. [x] 在 `images/account/` 新增小型 C 覆盖库源码及受控配置；在 `images/v3/Dockerfile` 的 account 阶段编译，避免可变上游二进制。先完成动态 uname、只读 CPU 文件，再按探针补齐常规内核文件读取 API。
4. [x] 在 `orchestrator/account_isolation.py` 的 CLI 创建分支渲染并只读挂载配置、CPU 文件、`/etc/ld.so.preload`；网络/sender 不加载。完成旧容器需要对账/重建的兼容门禁，不能打断活动任务或放宽权限。
5. [x] 将实际探针接入创建就绪校验，覆盖身份导入值一致性；保留 process_import 的真实采样。补充角色、加载失败、配置损坏及只读权限回归。
6. [x] 完成逐路径覆盖报告、目录现状说明和局限说明，再进入检查阶段；不把离线启动当作完整任务/协议验收。

## 验证矩阵

| 场景 | 期望 |
| --- | --- |
| 同账号多个新 run、恢复、续聊、重启、重建 | 已保存替换字段相同，不重新抽签 |
| 老账号只补齐新对象 | 原 hostname/MAC/machine-id/TZ、设备 ID、凭据、绑定及 HOME/项目内容不变 |
| 画像 JSON/模板/权限损坏 | 明确拒绝启用，不重新随机；仍可停止/回滚/对账 |
| UID1000、cap-drop ALL、NNP、根只读、默认 seccomp、tmp noexec | 正常加载，无法修改画像，不要求 SYS_PTRACE/privileged |
| uname、Node、原生 CLI 2.1.293 的实际 uname、内核文件、CPU 文件 | 与画像一致，受支持 API/路径均有证据 |
| 绝对路径、相对路径、openat、fopen、Node/Bun fs、子进程 | 分别验证；未覆盖项列入局限，不推定通过 |
| 静态探针、直接 uname syscall、CPUID、sysfs | 报告真值/未覆盖边界，不能把探针绕过当实现成功 |
| CLI 外的 sender/network、管理页/API 与真实 cgroup/RSS | 不加载覆盖库，真实指标与转发行为保留 |
| mock run/续聊/取消、SSE、代理失败关闭、API 转发 | 原生命周期与链路通过，任务项目目录规则不变 |
| 停用/回滚再启用 | 原画像复用，原设备和工作文件保留 |

## 命令与证据

首先只运行受影响模块，新增改动再决定是否扩大范围：

```bash
python3 -m unittest discover -s orchestrator -p 'test_account_runtime.py'
python3 -m unittest discover -s deploy/v3 -p 'test_*.py'
python3 -m py_compile orchestrator/account_runtime.py orchestrator/account_isolation.py
git diff --check
```

新模块使用项目现有测试框架并加入相应 targeted 命令；C 编译开启警告检查，ASan/UBSan 仅用于隔离验证镜像。真实 Docker 验证先查看 `deploy/v3/run_local_verification.py --help` 与现有 fixtures，再复用其正式镜像/角色组合，不凭空发明参数。

无账号 CLI 使用精确 2.1.293 NPM 产物，在 `--network none` 下只运行本地子命令和最小辅助探针；无法离线验证的真实登录/模型路径注明未验，不使用受限账号探测。发布镜像重跑离线覆盖和现有本地转发/lifecycle 场景，不引用研究镜像结果替代。

记录冷启动/文件读取/合成任务耗时、错误与进程收口，和未开启覆盖的同一镜像比较。出现明显退化或原生 CLI 启动故障时先修复或返回设计，不带病启用。

## 检查、交付与回滚点

- [x] 依次执行 Trellis 检查与规范更新；报告实际覆盖范围及未验的真实模型/登录链路。
- [x] 提交/推送按精确文件范围交付，不自动纳入原有升级文件；生产部署单独按用户授权和既有 SOP 推进。
- [x] 画像持久化前、CLI 挂载启用前、角色重建前分别可恢复；回滚移除 preload/画像挂载并保留 system_profile 对象及原身份数据。

风险文件：`orchestrator/account_runtime.py`（锁、老账号及身份探针）、`orchestrator/account_isolation.py`（角色配置）、`images/v3/Dockerfile` 与新增 C 源码（加载器 ABI/线程安全）、`deploy/v3/verify_isolation.py` 与验证入口（真实 Docker 回归）。

## 实施验证记录

- 当前实现使用 `system_profile.py`、镜像内编译的 `system-profile.c` 和 CLI 专属只读挂载。旧 CLI 校验失败标记 cli_reconcile；只允许显式、排空后的 maintenance 认领恢复，普通任务仍拒绝，健康 API 保留。
- 测试依赖环境为 `/tmp/v3-unbind-venv/bin/python`；宿主默认 Python 缺少 docker 模块，最初尝试不计成功验证。该虚拟环境执行后端全量 301 项、部署脚本 32 项均通过；定向账号运行时 54 项包含在前者中，不重复计数。
- 同源正式 Dockerfile 构建完成，最终本地批次为 `system-profile-20261017-c`，清单 `/tmp/v3-system-profile-build-c.json`；这是未提交源码的本地构建，不能发布或直接生产部署。
- `run_local_verification.py --manifest /tmp/v3-system-profile-build-c.json` 通过；包含动态/静态 C、400 次并发读取、fortified open、相对 openat、Node/子进程、实际只读挂载、真实资源预算、合成任务/续聊/取消、API 长流、SOCKS/CONNECT 与故障失败关闭。日志 `/tmp/v3-system-profile-docker-final.log`。
- 同命令加 `--legacy-control-image ghcr.io/silentflower/vibebench-v3-control:v3-ci-38837053861-1 --legacy-account-image ghcr.io/silentflower/vibebench-v3-account:v3-ci-38837053861-1` 通过，验证新画像经过实际旧镜像回退和再启用仍保留，身份/HOME/合成凭据不变。日志 `/tmp/v3-system-profile-rollback.log`。
- 精确官方 CLI 2.1.293 在最终 account 镜像、UID1000/无 capabilities/根只读/断网下，版本命令、未登录状态和登录帮助通过。动态链接证据另确认原生 CLI 的 uname/open/fopen 绑定覆盖库；没有发真实 OAuth 或模型请求。
- 离线性能样本每组预热 1 次后取 5 次中位数：版本 15.4→14.9ms，状态查询 196.1→206.0ms，登录帮助 146.7→147.9ms；仅代表本地无账号启动，不代表真实长任务性能。原始数据 `/tmp/v3-system-profile-perf.json`。
- 损坏内核文件在实际容器内明确返回 EIO，进程仍可管理；Python 编译、C 严格编译及 diff 检查通过。原有 20 个跟踪改动的 diff 哈希与 35 个未跟踪文件哈希均保持。
- 明确未覆盖：raw syscall、静态 uname、CPUID、显式库绕过/符号链接别名、其它 sysfs；当前仅有 AMD Naples/Cezanne 兼容模板。真实 OAuth、真实模型及生产切换留待授权的上线流程验收。
