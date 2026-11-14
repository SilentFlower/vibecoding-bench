# 原生运行时切换后自动准备与新账号默认策略

## Goal

管理员切换账号到原生运行时后，系统主动完成零模型准备，环境页准确展示进度、就绪或失败原因。

## Background

- 用户已选择“保存后后台零模型准备”，随后明确要求修复；本任务承接当前 5 个默认策略 dirty 文件。
- 线上 11-14：网关已为 native293，环境第 3 代 stopped，sender.native 为空且绑定 account_id=0；镜像已带原生、CRIU、TLS 采集能力。
- 锚点：services/gateway/src/handler/router.rs:1128 在配置事务中领取门禁；services/gateway/src/service/account.rs:1035 等入口发出更新通知；services/gateway/src/service/native_prewarm.rs:345 仅 prepare_existing。services/orchestrator/account_runtime.py:824 对空 native 隐藏准备摘要；services/orchestrator/native_kernel_upgrade.py:212 隐藏内核摘要。
- 线上另有资源阻断：固化 RAM 1536 MiB、V3_NATIVE_SENDER_MEMORY 为空。有限预算预检位于 services/orchestrator/native_sender.py:38 和 resource_budget.py:39。

## Requirements

- R1：成功保存 active 账号的 native293 选择后，自动异步准备对应环境、原生热进程及符合既有准入的 CRIU 模板。
- R2：切换事务完成并释放门禁后才准备。普通扫描、周期巡检、GET 列表及状态读取继续只解析运行绑定。
- R3：复用有界准备协调器、失败退避、取消、身份和代次核验；重复提示合并，切回 legacy、停用及维护使旧准备及时失效。
- R4：环境页显示已选择原生、等待、准备中、实际就绪及受控失败原因；失败提供显式重试入口。旧配置及旧代次回执不能显示为就绪。
- R5：预算、绑定及认证仍由原门禁校验，展示可操作的固定原因。资源、并发及已选后端沿用实际保存值。
- R6：整合本轮已授权默认值：任务侧创建 cc2api 使用 native293 与 5h 已用 85%/7d 已用 80%；新增本地账号及首次登录保存的工程额度同为 85/80。恢复、重登、重试保留自定义及 NULL 关闭状态。
- R7：按已领取的 Check-All 修复授权处理 CHK-001：相同时间戳的最新提交及提交历史按确定的插入先后排序，项目和养号两个空间保持一致。

## Acceptance Criteria

- [x] A1 / R1-R3：停止的旧布局切为原生后，保存及时返回，释放门禁后自动准备；满足预算时实际 ready，合成模型 POST 增量 0。
- [x] A2 / R2-R3：普通读取零唤醒，重复通知合并；活动请求、CLI/系统维护、切回 legacy、停用、身份/代次变化及迟到回执回归通过。
- [x] A3 / R4-R5：等待、准备中、就绪、失败原因和重试可见；预算失败保留已选配置，调整后显式重试可恢复；390/1280px、明暗及离页迟到响应通过。
- [x] A4 / R1-R5：预算、身份、凭据归属、并发、唯一模型投递与 CRIU/TLS 各自准入保持原合同。
- [x] A5 / R6：新账号两处默认策略及旧策略保留回归通过。已有 134 项仅为旧默认策略证据，整合后重新验证。
- [x] A6 / R7：固定同一时间戳并使后提交 UUID 更小时，当前进度、历史首项仍为后一次提交；旧提交迟到事件被排除，两空间及历史记录兼容通过。

## Non-Goals

- 不批量唤醒休眠账号，不把轮询变成唤醒入口。
- 不自动提高线上资源、修改凭据归属、发送真实模型请求或部署版本。
- 不迁移既有账号默认值，不改网关手工创建账号的全局默认后端。
