# 系统更新确认默认等待一分钟

## Goal

打开更新确认框即可使用一分钟的在途等待期限。

## Background

apps/web/src/components/SystemUpdates.vue:23,125,129 分别将初始选择、重开选择和冻结期限固定为 15 分钟及 900 秒。services/orchestrator/system_updates.py:85 DTO 默认 900 秒，deploy/flower2api/SYSTEM-UPDATES.md:153 描述默认十五分钟。

## Requirements

- R1：安装与回退确认每次打开默认一分钟，冻结请求 60 秒；继续提供 1/5/15/30/60/120 分钟。
- R2：后端 DTO 缺省值同步 60 秒，严格类型和期限范围校验保持。
- R3：已登记操作、恢复、重试使用原冻结参数；到期沿原超时恢复流程。
- R4：SOP 和验证说明同步。

## Acceptance Criteria

- AC1 → R1：初开及修改后取消重开默认一分钟，直接确认只产生一次 60 秒请求。
- AC2 → R1/R3：显式选择 30 分钟仍提交 1800 秒，恢复与重试的 UUID 和参数一致。
- AC3 → R2：省略字段为 60 秒；显式值保持；非法类型和超范围继续拒绝。
- AC4 → R3/R4：取消、Esc、遮罩、移动端及冻结参数场景通过，文档一致。

## Out of Scope

改变超时恢复策略、强制终止任务、发布及线上应用。

## Execution And Validation

本子任务为有界默认值同步，采用轻量 PRD。修改三个页面入口、DTO 及 SOP，扩展 verify_system_update_browser.py 的默认与重开重置场景。运行 Vue 构建、实际产物的更新浏览器测试、DTO 聚焦验证和相关更新恢复测试。使用合成数据与离线服务。
