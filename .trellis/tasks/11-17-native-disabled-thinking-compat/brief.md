# Brief — Native disabled thinking 兼容

## Goal

- 让native转发支持原有按模型范围控制的disabled到adaptive兼容，提供默认关闭、可手动启用的能力。

## Scope

- 既有兼容开关、精确模型名单与保存后热生效。
- native首次发送、429换号及签名修复的业务副本改写。
- 原始入站与实际出站的诊断归属、280/293实际原生回环验证。

## Non-Goals

- 模型能力自动探测、默认模型名单扩大及既有历史签名修复规则调整。
- 正式部署和生产验证由后续流程承接。

## Technical Overview

- 复用rewrite_disabled_thinking_enabled、rewrite_disabled_thinking_models及原有最小改写函数，按完整模型ID精确匹配。
- 单请求冻结配置，在会话映射得到的业务副本上仅将命中的顶层thinking.type从disabled改为adaptive，随后进入原生封口；同请求各次发送沿用同一配置。
- 原始入站保留原值，实际业务副本、cc_prepared、CCH及TLS实收正文分别核对。

## Context & Decisions

- 用户已明确要求在缺少真实失败样例时继续适配，真实上游效果调整为后续验证项。
- 出厂默认关闭，默认名单为claude-fable-5；已有管理员配置保持。
- adaptive会允许模型自适应思考，该语义沿已确认方案执行。
- 本Brief来源为本任务最新prd.md、design.md和implement.md。

## Risks

- 原生构造器对adaptive及tool_choice组合的表达须按280/293分别验证。
- 真实上游兼容效果仍待后续观测；本轮证据采用合成凭据及隔离回环上游。

## Acceptance

- 开关关闭、未命中模型及其他thinking类型保持既有行为；命中且开启时实际发送adaptive。
- 其他thinking子字段、历史签名、缓存及TTL符合既有合同，原始诊断保留改写前值。
- 验证完整模型名含[1m]的精确匹配、配置热生效、单请求冻结及重试一致性。
- 280/293真实执行体的实际TLS发送、CCH和调用次数具有独立证据。

## Next Step

- 启动本任务，经trellis-route进入实现，先冻结当前代码与双版本验证基线。
