# Brief — 反重力兼容 Claude WebSearch

## Goal

- Claude Code 经 Flower2API 使用反重力 Gemini 模型与原生搜索。

## Scope

- Flower2API 的 `/v1/messages` 反重力双向适配。覆盖日常对话、客户端工具回填、流式和普通 JSON。
- 用 `agy -p` 执行独立的 Claude WebSearch 子请求。保留原始会话和账号归属。

## Non-Goals

- New API 源码及部署配置、ACP、通用服务器工具、原生 Claude 的所有特性及生产发布分别留作独立工作。

## Technical Overview

- 网关识别反重力模型后复用同一套 Gemini 执行、账号调度与工具续轮。WebSearch 走账号发送器的 headless `search_web`。结果由网关返回 Claude 格式。

## Context & Decisions

- **【关键决定】转换与搜索都在 Flower2API 完成。** New API 可使用已有 Anthropic 渠道透传。
- **【关键决定】关联搜索共享原账号许可。** 原主回合等待时，单并发配置也能执行搜索。

## Risks

- **【交付风险】原版工具范围和可解析的来源回执用隔离的固定制品先核对。** 实际联网另用授权测试环境验收。

## Acceptance

- 聊天、同名工具乱序回填、双响应格式和原 Session ID 正常。
- Claude Code 接到真实搜索结果并继续。多账号及单并发的归属、失败恢复和既有入口通过回归。

## Next Step

- 验证固定原版 AGY 的 headless 工具调用和回执。
