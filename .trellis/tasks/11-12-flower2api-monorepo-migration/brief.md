# Brief — Flower2API 目录迁移与 Trellis 规范整合

## Goal

- 将三个项目合并为职责清晰的源码仓库，同步整理 Trellis，并延续 v3 原地升级。

## Scope

- `apps/web`、`apps/legacy-web`：分别承接 Vue 后台与现有工程界面。
- `services/gateway`、`services/orchestrator`、`services/runtime`：承接网关、编排器、运行时源码及其依赖锁、测试和许可。
- `resources`、`docs`、`scripts`：归并工程库、题库、研究资料、文档及仓库级工具；同步 `images`、`deploy` 和 CI 的构建入口。
- 根 `.trellis`：归并两边共 55 份 spec，整理公共指南、package 映射、索引和任务引用，并记录规范来源。

## Non-Goals

- Logo、界面重设计、功能删除及运行时协议改写留给后续任务。
- 正式发布、生产安装和生产数据迁移另行安排。

## Technical Overview

- 按“源码收编 → 服务与前端迁移 → 资源文档归位 → Trellis 整合与联合验证”推进，每步保存文件映射、内容摘要及验证证据。
- 新源码路径通过构建映射接入现有镜像和宿主更新器，沿用 v3 的数据根、部署身份、数据库合同和更新信任根。
- spec 分为 `platform / gateway / orchestrator / runtime / web / legacy-web / guides`；公共合同维护一个权威正文，旧路径提供转向入口。

## Context & Decisions

- 在 `flower2api` 分支持续改造；cc2api 改为直接管理源码，运行时按明确提交导入。
- 各语言保留现有工具与依赖锁。运行时源码来源和当前固定执行制品分别记录。
- 原有任务、日志及工作区改动按来源保留。Trellis 项目规范与模块映射随目录调整，Flower 受管框架沿现有所有权维护。

## Risks

- 构建快照、Rust 嵌入资源、Python 根定位和宿主固定源码包存在路径耦合，需要联动验证。
- 大量工程资源和长篇 spec 需要逐项核验，模板占位、重复内容及历史引用需要分别处理。

## Acceptance

- 单次克隆取得三个组件源码与依赖锁，新目录下构建和验证入口有效，源码与资源摘要符合迁移映射。
- 有效规范具备去向与来源；模块查询、索引、链接、任务引用和旧入口解析通过检查。
- Rust、Vue、Python、运行时对应回归及同批镜像构建通过；宿主固定源码包可独立运行，旧 v3 离线升级和回退验证通过。
- 原账号、环境身份、凭据、HOME、工作成果和历史记录的兼容合同通过回归。

## Next Step

- 激活任务后，固定三个仓库的来源提交与工作区基线，开始源码收编。
