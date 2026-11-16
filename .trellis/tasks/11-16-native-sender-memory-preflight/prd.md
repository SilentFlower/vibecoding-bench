# 移除原生sender固定内存最低预检

## Goal

让普通原生 sender 按实际配置及共享池容量运行，消除按预估内存公式阻断准备和启动的行为。

## Background

- 用户说明当前 sender 已采用无限内存，并要求去掉固定预检门槛。
- 默认 `V3_ACCOUNT_MEMORY=unlimited`，原生 `memory_mib=0`。同账号同版本共享执行映像，worker 保有独立堆及请求缓冲。
- 需求提出时的普通启动门槛：历史293单版 `256+192*max_workers` MiB，双版 `384+192*max_workers` MiB。原入口位于 `services/orchestrator/native_sender.py:107`、`services/gateway/src/service/native_runtime.rs:84` 和 `services/gateway/src/service/runtime_transport.rs:99`。
- `deploy/flower2api/README.md:50` 记录既有293共享池六路峰值约646MiB及回收后约189MiB。280/293混合池峰值留待独立测量；映像字节数只表述共享背板大小。
- v1.11.0 已以提交 `cb5a16157194e3faea4c722ac4b584280d092924` 正式发布，本补丁独立推进。

## Requirements

- R1：普通 exec 的准备、版本选择与新进程校验统一移除按固定MiB公式判定容量不足的条件，覆盖280/293双版与历史293单版。
- R2：有限配置继续要求显式正数 sender 预算并严格校验格式，按账号真实总RAM划分角色，保留 network256MiB、CLI最低512MiB和额外swap归属。无限配置继续使用明确零限额语义。
- R3：账号加权并发、RPM和跨版物理进程上限保持原合同，`max_workers=2*标准并发` 且为正。活动、启动和空闲进程合计受该上限约束，进程真实退出后归还容量。
- R4：制品身份、版本、路径、绑定、代次和凭据校验保持原合同。CRIU 的独立恢复能力及预算继续决定恢复或普通exec回退。
- R5：同步当前资源合同、部署说明和测试，明确配置额度、共享映像大小与实测内存的区别；历史故障码继续支持旧sender状态解析。

## Acceptance Criteria

- [x] A1（R1）：低于旧单版及双版公式的合法有限预算均可生成配置并通过普通启动配置校验，保留实际预算和原worker上限。
- [x] A2（R2）：默认无限账号保持零限额和原容量；有限预算缺失、格式非法及侵占角色最低份额仍按原合同拒绝。
- [x] A3（R3、R4）：零worker、非法路径和缺失/身份不符制品仍拒绝；两版总物理容量及退出归还回归通过。
- [x] A4（R4）：CRIU恢复预算不足继续选择普通exec，历史readiness及故障码兼容回归通过。
- [x] A5（R5）：当前说明与上述行为一致，既有实测数据注明293场景，混合池测量状态明确。

## Non-Goals

- CRIU恢复预算调整、进程池架构改造及共享映像机制重做。
- 新增内存估算公式、宿主自动扩容或混合池性能测量。
- 改写已发布v1.11.0、追加正式发行或生产安装。
