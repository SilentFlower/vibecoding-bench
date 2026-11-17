# Brief — 连接池设置适用范围说明

## Goal

- 让管理员准确理解Rust代理连接池开关与native模型连接复用的适用范围。

## Scope

- 系统设置页现有连接池控件的标签与帮助说明。
- 文案呈现、开关草稿/撤销及保存载荷的定向验证。

## Non-Goals

- Rust或原生SDK连接池策略与参数调整。
- 账号迁移及原有后端退役。

## Technical Overview

- 调整settingsSchema.ts中现有控件的label/help，复用proxy_client_pool_enabled及原有字符串保存流程。

## Context & Decisions

- 标签：“Rust 代理 HTTP 连接池”。
- 说明：“复用 Rust HTTP 客户端连接。native 模型请求的连接复用由原生 SDK 管理。”
- 现有设置值与默认行为保持，其他后台请求按实际Rust客户端调用链确定适用性。
- 本任务为轻量文案任务，Brief来源为最新prd.md。

## Acceptance

- 页面准确显示已确认的标签与完整说明。
- 390/1440px下可阅读，控件草稿和撤销行为正确。
- 保存沿现有设置键提交字符串true/false，Web构建通过。

## Next Step

- 启动本任务，经trellis-route进入实现并更新两处文案。
