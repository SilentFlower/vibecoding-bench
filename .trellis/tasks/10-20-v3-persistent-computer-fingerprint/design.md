# v3 持久计算机指纹设计

## 决定与边界

- 采用本项目自有生成器与现有原生 CLI，字段和首次生成后固定的行为对齐 vm2api 的可见机制；不调用、复制或分发闭源 `kin-computer`。
- 扩展对象是账号的静态系统身份，覆盖 DMI 六字段及既有主机名、MAC、machine-id、CPU／内核画像的统一持久性。时区和语言保留用户设置，软件、CPU 能力、cgroup、实际限额和 RSS 按真实环境处理。
- 本轮修改限定于 v3 编排、账号镜像、常规读取库、离线验证及说明文档；不新增管理页、远程部署、模型请求、cc2api 字段或遥测机制。

## 权威状态与字段契约

`account_environments.fingerprint_json` 继续作为唯一权威记录，不把容器层、每轮工作目录、内存缓存或生成器种子作为第二来源。

| 字段 | 规则 |
|---|---|
| 已有 hostname、MAC、machine_id | 保留已有合法值，新账号沿用现有独立随机来源 |
| 已有 tz、lang、mem、swap | 保留，不参与本轮重新随机 |
| 已有 system_profile | 保持原 schema 和对象不变；缺失时沿用既有生成与代际核验 |
| 新增 computer_profile.schema | 固定版本 1；显式空值、未知版本或额外未知键按坏记录拒绝 |
| 新增 computer_profile.template_id | 从与已保存 CPU 画像兼容的内置模板中选择一次，模板 ID 只追加、不重解释 |
| 新增 computer_profile.dmi | 固定 manufacturer、product、version、family、serial、uuid 六键 |

上述 `computer_profile` 已由本轮实现定义，旧 `system_profile` 的 schema 保持不变。

- manufacturer、product、version、family 以兼容模板作为整体选择，不独立拼接；候选覆盖当前已支持的 Naples 与 Cezanne CPU 画像。来源及显示值定义见 `research/hardware-template-sources.md`。
- serial 使用独立密码学随机字节生成有界大写字母／数字文本，uuid 独立生成标准 UUIDv4。两者不从 MAC、machine-id、官方 CLI userID、凭据或环境 ID 派生；首次提交时检查已存 UUID 冲突，重新生成只允许发生在新值尚未发布时。
- 新增对象的校验绑定已有 CPU 模板及代际，拒绝跨代组合、控制字符、NUL、换行、异常长度、非法 UUID 和未知模板。不因候选模板列表升级而重新选择旧对象。
- 静态身份摘要只涵盖已保存的静态字段，不能把实际 CPU 频率、采样时间、RSS 等变化误报为身份变化。

## 生成、保存与并发

复用 `AccountRuntime` 的环境锁和 `prepare_system_profile` 的受控创建窗口。实际 CPU 信息读取在短写事务外完成；进入 SQLite 短事务后重读本环境指纹，验证已有记录，仅对缺失对象生成并合并，再提交完整新 JSON。

- 以 SQLite 写事务及重读防止两个初始化者各自发布一套身份；不能用旧 row 副本覆盖其它操作刚写入的字段。UUID 冲突检查与首次保存位于同一事务中。
- 已有完整对象只验证并复用；存在 key 但值为空、损坏或版本不兼容时拒绝，不按缺失处理。
- 权威记录提交后才渲染只读文件。若进程在提交后、文件渲染中或容器创建前退出，重试根据同一 JSON 重建文件，不重新调用随机生成器。
- 渲染继续使用项目已有的防符号链接原子写入：账号隔离目录、root 所有、文件 0444、目录可遍历但不可写。临时文件、坏配置和未发布目录不成为可用身份。
- 普通任务、续聊、重启与 `maintenance(..., "rebuild")` 都只复用保存值。旧 legacy 专用 `reprofile` 路径至少保留新对象，不新增任何可用于重置 profile v2 指纹的入口；有历史／绑定／设备观察记录的既有阻塞继续生效。

## 容器读取覆盖

继续仅在 CLI 角色加载只读系统画像和共享库；network／sender 的网络、权限、挂载、凭据与 API 行为沿用现状。

- 在现有受保护画像目录内增加 DMI 只读子目录，与权威对象六字段一一对应。
- 扩展 `images/account/system-profile.c` 的路径白名单，将下列两个目录的六个指定文件和必要的目录句柄映射到同一 DMI 目录：`/sys/class/dmi/id`、`/sys/devices/virtual/dmi/id`。
- 对动态 libc 文件读取、支持的相对 cwd／目录 fd、存在性和可读性检查应用相同路径解析。所需 stat／access 等符号以当前目标镜像 glibc 实际接口为准，实施时核对并通过原生探针验证，不根据一个 cat 输出推定所有接口生效。
- 实际 Node 22/libuv 的 stat 查询经动态 libc syscall 的 statx 入口，实施中纳入该特定入口。x86_64 汇编转交其余系统调用的原始寄存器与第六参数，不用 va_arg 读取不存在的参数，并验证零参数、六参数和 errno；直接内联系统调用、静态程序及其它未列入口仍在原边界内。这是同一 Node 常规元数据验收范围内的机制补齐。
- 写入、创建、删除及越界路径不得变成可写画像入口；精确白名单之外保持原行为。初始化使用底层只读调用避免 hook 递归，保留 errno、原接口的 flag 语义与既有 kernel／CPU 覆盖。
- 增加独立的计算机画像镜像能力标签和 CLI 实际校验；不能仅据继承的镜像标签判断已加载。旧 CPU／内核对象仍使用原 schema，减少与旧控制端的兼容耦合。
- 验收包含文件不存在的本地 sysfs 环境，以及被模拟为已有文件／目录的路径场景；不能依赖宿主恰好提供 DMI。

覆盖契约只包含约定的常规动态接口。静态程序、直接 syscall、CPUID、SMBIOS 二进制、dmidecode、全 sysfs 树枚举和未列路径不保证覆盖，按实证列出实际结果。

## 旧环境启用与回滚

- 已有合法 CPU／内核、主机名、MAC、machine-id 和官方设备身份不变，只在显式空闲重建时补齐缺失的计算机画像。GET、页面读取、管理端重启或普通 API 不触发迁移。
- 旧 CLI 没有新能力或缺少对应挂载时，由既有 CLI 待对账门禁给出需要空闲重建的信息，保持健康的独立 API；不在正在运行的 CLI 中替换身份或库。
- 本轮不为现有被封账号执行重建或主动验证；生产切换不在本任务实施范围内。
- 回滚通过空闲时切回旧镜像与匹配控制端，并重建 CLI 去掉新能力；保留新增 DB 对象、HOME 和最新凭据。重新启用时使用原 computer_profile，不从旧备份恢复过期 RT，不在回滚中重置身份。

## 影响文件

- `orchestrator/system_profile.py`：独立模板、生成、校验、只读渲染与实际探针。
- `orchestrator/account_runtime.py`：受控补齐、持久化并发、坏记录及维护兼容。
- `orchestrator/account_isolation.py`、`images/v3/Dockerfile`：能力标识、仅 CLI 加载与创建校验。
- `images/account/system-profile.c`：DMI 动态读取和检查路径。
- `orchestrator/test_system_profile.py`、`orchestrator/test_account_runtime.py`：生成、迁移、并发、持久性、损坏和隔离回归。
- `deploy/v3/verify_system_profile.py`、`deploy/v3/fixtures/system_profile_probe.c`、`deploy/v3/verify_local.py`：实际读取、绕过边界及生命周期验证。
- `doc/v3-system-profile.md`、相关 Trellis spec：明确字段与常规覆盖契约。

## 验证矩阵

| 维度 | 验证内容 | 对应验收 |
|---|---|---|
| 生成与模板 | 兼容候选、独立标识、UUID 格式、未知版本和坏字段拒绝 | A1、A5 |
| 持久化 | 重入、并发初始化、提交后崩溃、原子渲染失败后复用同一对象 | A2、A5 |
| 旧账号 | 已有字段不变、缺失补齐一次、显式空闲重建、legacy 边界 | A3、A5 |
| 动态读取 | 两目录六字段，cat、Python、Node、C 文件接口和 stat／access，支持的相对读取 | A4 |
| 边界与权限 | 写入拒绝、无额外 capabilities、其它角色不加载、静态／直接 syscall 明确记录 | A4、A5 |
| 生命周期与回归 | 新任务、恢复、停止启动、控制端重启、容器重建及镜像能力升级保持摘要；本地模拟 API 兼容 | A2、A3、A6 |

规划阶段的临时原型仅证明部分内容读取可行，不替代以上实施验收。控制端进程重启与 B→C 镜像切换另用 `research/identity_lifecycle_probe.py` 在专用本地内部网络、持久合成 SQLite 与无真实凭据的环境中核对，结果只记录静态摘要。
