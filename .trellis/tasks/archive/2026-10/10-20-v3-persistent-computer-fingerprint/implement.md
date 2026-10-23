# v3 持久计算机指纹实施计划

## 实施前提

- 用户已确认完整 Brief，任务已通过 task.py start 激活，当前为 in_progress；本轮实施路由为 inline。
- 实施入口遵循 trellis-route，读取 trellis-before-dev 注入的当前项目规范。并行模式仅在适用指令明确允许时使用，不由本计划自行派发。
- 保留建任务时记录的全部原有 dirty baseline，不把 Flower、其它任务或部署草稿纳入本次功能改动。

## 顺序

1. [x] **字段与生成（R1、R3）**：在现有系统画像模块中定义版本化 computer_profile、兼容模板和严谨校验；保留 system_profile 原对象与已有身份。增加真正覆盖独立生成、组合合法性和损坏拒绝的单元验证。
2. [x] **受控持久化（R2、R5）**：接入环境锁和短事务重读，保证缺失对象只发布一次，已有对象不重抽；覆盖并发、半写入、提交后渲染失败及 legacy 维护保留。
3. [x] **常规读取（R4）**：扩展仅 CLI 使用的文件覆盖库，统一两类 DMI 路径的内容读取及 stat／access 等必要检查，处理支持的相对目录 fd；维持白名单、errno、写入拒绝和非目标路径行为。
4. [x] **能力与入口（R3、R5）**：加入独立能力标识、只读文件发布及容器内实际核验。旧实例要求显式空闲重建，失败只隔离相应 CLI，不重置凭据、设备或健康的独立 API。
5. [x] **离线生命周期（R2、R4、R6）**：扩展既有原生探针和本地 Docker 场景，逐字段核对内容、存在性、可读性、只读性；验证控制端重启、账号停启、容器重建和镜像能力升级后的静态身份摘要。
6. [x] **说明与交付（R1—R6）**：更新 doc/v3-system-profile.md，按实际代码运行 Check-All，完成规范同步；给出本地结果和生产启用／回滚边界，不自动发布或生产重建。

## 分层验证

控制端真实进程重启和 B→C 镜像切换补充使用 `research/identity_lifecycle_probe.py`，只记录合成环境的静态摘要。先运行与本次改动直接相关的生成、生命周期和 C 探针检查；通过后运行一次既有完整本地隔离验证。验证仅使用合成账号、本地模拟上游和专用随机标签资源。

| 层级 | 计划命令或入口 | 必须证明 |
|---|---|---|
| Python 定向 | `PYTHONPATH=orchestrator python3 -m unittest discover -s orchestrator -p 'test_system_profile.py'` | 模板、格式、真实 CPU 能力保留和坏记录拒绝 |
| 运行时定向 | `PYTHONPATH=orchestrator python3 -m unittest discover -s orchestrator -p 'test_account_runtime.py'` | 只生成一次、事务并发、旧身份及维护隔离 |
| 关联回归 | 根据实际修改运行已存在的 `test_login_reauth.py`、`test_process_metrics.py` 定向用例 | 重新授权、身份保留与真实进程指标不受指纹补齐影响 |
| C 编译与探针 | 现有 `-Wall -Wextra -Werror` 共享库构建与 `deploy/v3/fixtures/system_profile_probe.c` | 两类 DMI 路径、文件检查、线程、非目标路径、直接 syscall／静态边界 |
| 镜像与完整离线 | 按 `deploy/v3/manage.py build --help` 及本地 SOP 构建同批测试镜像；`python3 deploy/v3/run_local_verification.py --manifest <实际本地清单>` | 实际挂载、角色权限、读取结果、运行恢复及重建身份摘要 |
| 官方 CLI 离线 | 使用可确认版本的本地 CLI 缓存、空 HOME 与断网环境执行版本／无登录状态等无模型检查 | 不能用脚本替身冒充官方二进制兼容性；缺少缓存时明确记录未覆盖 |

上表 `<实际本地清单>` 是运行时生成的输入，不是已有文件名。实施前核实 manage.py 的当前参数与产物路径，不套用虚构命令或省略相关镜像构建。

## 检查重点

- 所有已保存静态字段的规范化摘要跨生命周期一致；不能把 CPU 频率或 RSS 变化混入摘要。
- 内容读取成功但 exists／access 失败属于未通过，不能以“看起来有值”验收。
- 新 key 缺失可以首次生成，显式 null、错误 schema、模板不符、已有字段损坏必须拒绝；不能偷偷重抽。
- 检查副作用：未知 JSON 字段、最新 AT／RT、官方设备 ID、HOME、代理及绑定均保留；不触发额外上游认证、额度、遥测或推理。
- 旧 CLI 能力不足只进入对应待对账状态；创建失败停止本代新增资源，不清理其他环境。
- 日志仅记录模板 ID、状态与必要短摘要；唯一标识和敏感字段不批量输出到产品日志。

## 回退点

- 生成与渲染失败：保留已提交权威对象，移除本次未完成角色，下一次从同一对象重建。
- 读取核验失败：保留配置和证据，隔离 CLI，不能换一个模板绕过。
- 实施兼容性不符：更新设计中的具体读取入口与证据，保持用户已确认的目标和范围；若需要 KVM、特权或生产动作，停止相应扩展并另行决策。
- 发布与生产切换不在本任务执行范围。未来空闲回滚保留新增对象和最新凭据，重新启用仍复用原身份。

## 实施验证记录（2026-10-20）

| 验证组 | 实际执行与证据 | 结果 |
|---|---|---|
| 全量单测 | `PYTHONPATH=orchestrator /tmp/quota-hard-stop-venv/bin/python -m unittest discover -s orchestrator`；`/tmp/v3-fingerprint-unit-20261020-final.log` | 378 项通过，覆盖最终事务锁修正 |
| 联合构建 | `python3 deploy/v3/manage.py build --release fingerprint-20261020-c --manifest /tmp/v3-fingerprint-20261020-c.json`；`/tmp/v3-fingerprint-build-20261020-c.log` | control/account 两镜像构建成功，C 库使用严格告警编译 |
| 原生接口 | `PYTHONPATH=orchestrator:deploy/v3 /tmp/quota-hard-stop-venv/bin/python deploy/v3/verify_system_profile.py --manifest /tmp/v3-fingerprint-20261020-c.json`；`/tmp/v3-fingerprint-native-20261020-c.log` | 默认 sysfs、预置宿主 DMI、坏标记三场景通过；Python／Node／C、相对读取、权限和 syscall ABI 均通过 |
| 完整隔离回归 | `/tmp/quota-hard-stop-venv/bin/python deploy/v3/run_local_verification.py --manifest /tmp/v3-fingerprint-20261020-b.json`；`/tmp/v3-fingerprint-lifecycle-20261020-b.log` | 三角色、重建、恢复、API／CLI、本地 TLS、故障关闭及 17 组续聊／收尾通过，退出 0 |
| 跨控制端与镜像 | `/tmp/quota-hard-stop-venv/bin/python .trellis/tasks/10-20-v3-persistent-computer-fingerprint/research/identity_lifecycle_probe.py --before-manifest /tmp/v3-fingerprint-20261020-b.json --after-manifest /tmp/v3-fingerprint-20261020-c.json --output /tmp/v3-fingerprint-identity-lifecycle-20261020.json` | 三个独立控制端进程、停止唤醒和 B→C 显式重建后静态 SHA256 一致，HOME／设备配置保留，最终 C 实际 DMI 核验通过 |
| 官方 CLI 离线 | 官方 `@anthropic-ai/claude-code-linux-x64@2.1.293`，二进制 SHA256 `8968405e26db478af44eabc4635ab5ca557057b702a54460a59c13e1b253e978`；`/tmp/v3-fingerprint-official-cli-20261020-b.json` | 无网络、空 HOME 下 `--version` 返回 0；`auth status` 返回预期未登录状态。B／C account RootFS 完全相同，可复用启动兼容证据 |
| Python 语法 | 对 7 个变更产品／验证 Python 文件和 `research/identity_lifecycle_probe.py` 执行 `ast.parse` | 8 个文件通过 |
| diff 格式 | `git diff --check` | 通过 |
| 上下文清单 | `python3 .trellis/scripts/task.py validate .trellis/tasks/10-20-v3-persistent-computer-fingerprint` | implement／check 各 5 条，全部通过 |

完整 B 回归后唯一的产品代码差异是移除 SQLite 写事务外层的全局 jobs 锁，避免等待写锁时占用全局锁；最终 378 项单测及 C 镜像跨进程重建已覆盖此修正。两批 account 镜像文件系统一致，C 原生接口已单独重验，无须再次重复完整续聊矩阵。

补充跨进程夹具首次因未标注 orchestrator 角色而被现有管理来源防火墙拒绝，已修正测试夹具标签后重跑通过；没有修改产品网络保护。全部临时资源按专用随机标签清理。

本轮没有部署、生产账号重建、真实 OAuth、模型请求或公网 usage／遥测探测。正式 CLI 仅证明离线启动兼容，不代表真实认证或模型业务验收。

本地实施收口：Check-All 为 full／strict pass（CHK 0、FBK 0）；规范同步为 written，修改 account-runtime-v3.md 和 backend/index.md，六节结构、签名、链接及 diff 检查通过。任务仍为 in_progress，等待精确 Git 计划确认；尚未提交、推送或部署。
