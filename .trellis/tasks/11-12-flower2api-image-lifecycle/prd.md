# flower2api 镜像品牌与历史制品整理

## Goal

清理旧架构制品，并使正式镜像采用flower2api品牌，保持原v3实例持续升级。

## Background

用户明确要求删除vibebench-orchestrator、vibebench-worker、vibebench-sidecar，并推进当前两个正式镜像的名称迁移。部署源码迁移已完成，业务提交258d0e93与记录e62d8292已推送，远端CI 43237274556成功。

## Requirements

- P1：旧包清理由flower2api-legacy-package-cleanup独立交付，包含旧发布入口退役、权限预检、精确删除及收据。
- P2：名称迁移由 flower2api-image-name-migration 独立交付，目标 flower2api-control/account。2026-11-13 用户选择仅针对本人在用 US 部署，通过一次发布和维护同步切换镜像、容器与网络命名，更新固定宿主执行器；本版作为正式维护基线，保留首次交接及失败恢复，历史旧版本主动回退退出交付范围。
- P3：顺序为旧包清理→名称兼容迁移→向规范整理任务交接最终合同。TLS采集BUG与补丁发布由cc-runtime-bridge中的tls-capture-warmup-readiness任务并行推进。

## Acceptance Criteria

- [ ] 三个旧包均有可核对的删除结果，旧入口退役。
- [ ] 新名称发布/消费合同明确，现有单部署迁移及首次失败恢复通过，建立后续正式维护基线。
- [ ] 两子任务的边界、来源及最终规范合同一致。

## Non-Goals

账号重新创建、凭据与业务内容改写。名称迁移中的容器关联和环境代次由子任务沿原维护生命周期更新。
