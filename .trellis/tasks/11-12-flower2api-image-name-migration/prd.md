# 单部署迁移 flower2api 镜像与容器名称

## Goal

通过一次正式发布和一次维护，将现有 US 部署的正式镜像、控制容器、账号容器及网络名称统一为 flower2api，保留账号身份、业务数据和首次迁移失败恢复能力。本版作为 Flower2API 后续正式维护的起点。

## Background

用户要求迁移当前 vibebench-v3-control/account 名称。2026-11-13 明确当前仅本人使用，选择直接改名并一次性迁移现有部署，取代多用户兼容过渡方案。前置任务 flower2api-legacy-package-cleanup 已 completed。

只读盘点：US 部署运行 ci-43357757874-1，包含两个控制角色与四个账号环境的十二个角色；持久数据根为 /srv/vibebench-v3-us，固定更新器根为 /opt/vibebench-v3-us/updates，服务为 vibebench-updater-us.service。发布、签名校验和账号镜像来源当前绑定旧名称。现有固定更新器需独立更新其源码及模板。

## Requirements

- N1：后续正式发布使用 flower2api-control/account；构建、拉取、离线包、来源校验和诊断一致。历史签名发行原始字节及精确旧引用保持可验证。
- N2：现有部署一次切换新容器及网络命名，保留账号/环境 ID、HOME、设备及凭据归属、双库、工作区、成果、运行记录和资源/内核选择。容器 ID 与环境代次沿原生命周期更新。
- N3：同步固定宿主更新器源码和受信 Compose 模板，核对当前部署、冻结文件 SHA 与服务归属；继续原签名目录和已注册手动发布入口。
- N4：交付可预览、可恢复的单部署维护流程，覆盖排空、快照、切换、验证及失败恢复。养号 CLI、API、评审和维护租约均在排空范围，当前作业自然结束后切换。
- N5：新 GHCR 包沿正式交付要求完成可见性配置及匿名拉取验证；正式发行、新建环境和后续重建均使用新命名，防止名称回退。
- N6：本版作为 Flower2API 正式基线。旧来源读取用于本次安装交接、已签材料核验和失败恢复；正式发布单写新包，采用现有通道一次切换。历史旧版本主动回退退出本次交付范围。

## Evidence

- 原规划锚点 manage.py:679 对应的当前发布引用构造位于 deploy/flower2api/manage.py:683；加载校验位于 :736，构建本地引用位于 :514。
- services/orchestrator/system_update_contract.py:179 和 account_update_identity.py:37 对精确旧镜像引用进行校验。
- services/orchestrator/account_runtime.py:750 生成账号容器前缀；deploy/flower2api/compose.yml:1、:45、:85 固定控制项目和网络名。
- deploy/flower2api/system_update_host.py:113 按固定网络取控制服务地址；upgrade_system_updater.py:127 对已为 v2 的安装返回 already-current。
- 现场盘点及官方新包权限规则见 research/single-deployment-cutover.md。

## Acceptance Criteria

- AC1 → N1/N5：新正式发行的 control/account 引用均为新包名；同批摘要、签名、离线包及匿名拉取核对通过。
- AC2 → N2/N3：实际控制和账号角色采用新容器名及网络，唯一角色归属正确，API/CLI、环境列表、原生预热及 CRIU 状态检查通过。
- AC3 → N2/N4：迁移前后账号身份、受保护持久数据和策略一致；停止环境保留原停止状态；恢复测试覆盖切换前后中断。
- AC4 → N1/N4/N6：在隔离环境完成当前旧命名部署 → 新命名候选及本次迁移失败恢复，保留原来源验签，拒绝未知仓库、错角色与错批次引用。后续正式升级与回退以本版为基线验收。
- AC5 → N3/N6：Git、发布和一次维护沿项目 SOP 执行，现场验收及恢复收据完整，任务完成以迁移验收通过为准。

## Non-Goals

多用户过渡版本、双包发布、额外更新通道、历史旧版本主动回退保障、历史正式包删除、账号重新创建、凭据/业务内容迁移、资源额度或内核选择调整。持久目录、更新服务名、V3 环境变量、内部归属标签、HTTP 路由及已有发行身份沿既有合同保留。
