# Brief — R3-02／04 beta 请求规范化

## Goal

- 修复重复 beta 请求头丢值和 URL beta 冲突。

## Scope

- anthropic-beta 多值合并；现有目标路径归一为唯一 beta=true。

## Non-Goals

- 请求解压、响应保活和全局 query 白名单不纳入本轮。

## Technical Overview

- 复用既有 beta 合并函数，再执行账号／画像过滤；只替换同名 beta query，保留其它原始参数。

## Context & Decisions

- 已读取 592 条原生 Messages，只有 beta=true；293 原件因连接超时未读。由子 agent 在 R2 共享文件交接后实施。

## Risks

- 编码后的同名键、重复头顺序和特殊画像容易漏测，须观察实际上游请求。

## Acceptance

- 280／293、1M／Fast、API／特殊画像、query 编码矩阵通过；R2、CCH、stream 及 Rust 全量回归通过。

## Next Step

- 首次 Brief 确认后激活任务，经 trellis-route 派子 agent 顺序实施。
