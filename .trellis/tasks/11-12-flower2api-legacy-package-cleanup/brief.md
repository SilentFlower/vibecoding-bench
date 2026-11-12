# Brief — 退役旧三镜像发布并清理对应 GHCR 包

## Goal

- 清理旧三镜像包及其发布入口，完成可核对的制品退役。

## Scope

- 精确清理vibebench-orchestrator、vibebench-worker、vibebench-sidecar三个GHCR container包及其全部版本。
- 退役main和flower2api的旧发布入口，增加受信手动预览、应用与安全收据。

## Non-Goals

- 正式control/account改名、平台发版、宿主容器和数据删除。

## Technical Overview

- 使用仓库Actions临时令牌预检权限、包归属、ID、版本和引用，生成带源码与摘要的冻结计划。
- 应用前重新完整核对，按固定三项白名单逐项删除并复查，记录成功和失败现场。

## Context & Decisions

- 当前正式两镜像和旧v3签名历史进入保护集。后继名称迁移采用flower2api-control/account方向，并单独验证旧升级链。
- 已只读核查配置对应宿主的15个容器，旧三项引用为0。
- 本机令牌查询包列表返回403。实际包权限与ID由仓库Actions受控预览核验。

## Risks

- 包权限、归属或版本发生变化时，操作需要停在预检或冻结核对阶段。

## Acceptance

- 三项旧包具有删除收据和远端复查结果，旧入口完成退役，保护包保持原身份。
- 权限失败、404、计划漂移、错误归属、部分删除的回归通过，工作流和现有发行合同检查通过。

## Next Step

- 先建立合成API回归和默认预览工具，再完成实际权限预检。
