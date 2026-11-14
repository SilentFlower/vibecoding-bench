# 账号内存默认无限额与API发送器默认1.5核

## Goal

账号默认采用无限额内存和1.5核API发送器，已有环境在应用新配置后安全解除旧内存限额，使原生准备通过资源配置门禁。

## Background

- 用户要求“把内存限制放开，默认放开，不要设限”，并补充“API发送器（核）也默认1.5核”。
- 11-14在线已安装v1.6.2，环境第4代ready，原养号目标继续运行；总RAM1536m、额外swap2048m、原生sender预算为空、标准并发4。
- services/orchestrator/account_runtime.py:321、:2947和deploy/flower2api/compose.yml:53、example.env:17、manage.py:207仍默认4g；manage.py:208拒绝全局unlimited。旧环境保留fingerprint_json.mem，修改全局默认不会替换旧值。
- services/orchestrator/resource_budget.py已支持unlimited的Docker Memory=0/MemorySwap=-1；native_sender.py:64支持memory_mib=0且省略sender预算。
- services/orchestrator/cpu_resources.py:20、compose.yml:51、example.env:15默认sender1核；已保存cpu-resources.json策略优先。
- 本部署只读清单为15个环境，11-5与10-30已经无限额；11-14与10-30的工程代理运行中。现场约5.79GiB物理RAM、2.29GiB可用，4GiBswap。

## Requirements

- R1：新建账号和缺省/空值配置统一采用unlimited，显式有限部署配置仍可使用。
- R2：部署配置选择unlimited后，已有有限环境在空闲准备/重建时解除RAM及swap限额；运行中作业先完成。停止环境保持停止，下一次明确唤醒应用。账号身份、HOME、工作区、原会话和进度保持。
- R3：无限原生配置使用memory_mib=0，省略sender预算仍可准备；请求内核、热进程和CRIU按真实证据展示。
- R4：API发送器默认1.5核，显式环境CPU值和已保存账号CPU策略继续优先。CLI默认1.5核、网络默认0.5核。
- R5：PID、标准并发、RPM、身份、代理、凭据归属、在途保护和部署归属校验沿既有合同。部署预检继续核验宿主余量及既存有限账号的真实预算。
- R6：交付本部署配置切换及旧环境迁移操作单，明确既有1536m显式配置的替换、空闲条件、恢复点和实际验收；随后续新版安装应用。
- R7：用户追加要求一并发布新版，按功能版本规则发布v1.7.0，完成CI、双镜像、发行附件和受信目录验签后关闭任务。

## Acceptance Criteria

- [x] A1 / R1：默认配置创建的三角色及派生评审均为Memory=0、MemorySwap=-1；显式有限配置回归通过。
- [x] A2 / R2：已有1536m空sender预算账号安全转换，忙时延后，原work/session及进度保持；停止环境零自动唤醒。
- [x] A3 / R3：native293、N=4、空sender预算生成memory_mib=0/max_workers=8；真实Docker零模型准备核验当前内核及热进程证据。
- [x] A4 / R4：默认sender为1500000000 NanoCpus；CPU覆盖、持久策略、重建及串行评审恢复通过。
- [x] A5 / R5-R6：默认无限的部署预检、混合有限/无限环境、宿主余量、失败恢复及上线操作单通过核对。

- [x] A6 / R7：v1.7.0正式发布流水线通过，双镜像及6项附件绑定实际源码，发行和两个受信目录独立验签通过。

## Non-Goals

- 调整PID、标准并发、RPM、账号凭据或主机物理容量。
- 主动发送付费模型请求、强制终止在途作业、批量唤醒停止账号。
- 线上安装和实际账号操作由后续安装指令承接。
