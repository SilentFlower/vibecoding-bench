# 普通原生 sender 内存准入设计

## 边界及数据流

网关提供权威账号后端及标准并发，编排侧 `sender_config` 生成冻结的 `NativeSenderConfig`，sender 按安装表选择目标版本后创建/复用池。此次只移除普通exec配置的静态MiB最低公式；有限额度仍传入配置并用于真实cgroup，物理容量仍由跨版共享许可控制。

## 配置合同

- `NativeSenderConfig.memory_mib:u64`：0表示无限，正数表示实际有限额度；调整字段注释，去掉正数按公式限制并发的表述。结构、序列化及安装表字段保持兼容。
- `max_workers:usize`：继续为正。编排侧仍按标准并发乘2生成；Rust继续使用该值限制活动、启动及空闲worker总数。
- `sender_config` 保留已核验的版本集合、有限预算解析及 `isolated_account_limits`。移除普通池基础份额及worker估算条件，零worker校验独立保留。
- `validate_distribution_config` 保留正worker及绝对路径校验；`native_version_config` 保留目标版本、安装表、独立work_root及冻结配置处理。两处分别删除普通exec的内存公式。
- CRIU 的 `criu_available`、`restore_status` 及编排恢复政策继续沿原独立预算。常量存在真实恢复用途时继续保留。
- 旧 `native_sender_budget_insufficient` 故障码仍可读取。新增失败原因仅在现有合同确有需要时处理，避免改变兼容边界。

## 测试及说明

现有Python测试中1535m双版、1407m单版及N4/1536m等旧拒绝用例改为准入断言，同时核对冻结预算、worker上限及角色总额。高并发测试按实际账号并发生成容量，移除依赖估算公式的人工worker上界假设。

Rust针对私有配置校验直接验证低预算准入与零worker/相对路径拒绝。现有真实二进制忽略测试中的 `insufficient-budget` 负例改为确切无效容量配置，保持该负例零业务发送的合同；同步相关标签和夹具计数。沿原两版容量、真实退出归还及CRIU预算回退用例验证。

真实 `native_real_binary` 及 `native_real_gateway` 离线夹具将有限配置设为128MiB，用实际二进制及本地TLS验证普通启动、版本选择与转发的准入变化。夹具中该数值是冻结配置，运行环境内存测量属于独立口径。账号生命周期测试另核对相同低额度确实传入Docker的mem_limit，角色资源总额和忙门禁保持。

同步 `deploy/flower2api/README.md`、`services/runtime/docs/native-versions.md`、runtime/orchestrator资源Spec及相关结构注释。旧验收记录与已发布说明保留其历史事实。

## 取舍与风险

移除预估门槛后，过小的有限额度可进入普通启动并触发真实资源不足，按现有准备/启动错误处理。此变更保留操作者显式额度及所有容量许可。共享映像降低同账号同版的重复背板开销，每个worker仍有独立状态，各账号分别持有池。

## 兼容及恢复

历史配置和默认unlimited的序列化继续沿用原合同。旧sender继续执行旧门槛，补丁生效依赖后续正常镜像升级。出现回归时按精确补丁提交回退，保留账号持久数据及原资源配置。正式发行和生产安装属于后续独立操作。

## Check-All修复续行

CHK-001经后台领取授权修复并重检。排队封禁计数断言在当前代码及v1.11.0基线均复现；补强错误码断言确认真实返回session_policy_blocked。SQLx SQLite的fetch_optional在收到RETURNING首行后即可返回，worker仍可能尚未完成语句。命中写入改用fetch_all读取唯一ID结果并等待语句完成，再读取并返回封禁记录，保证其它连接立即可见实际计数。保持原封禁键、拒绝语义、原子UPDATE及数据库定义，增加独立连接立即读计数回归。
