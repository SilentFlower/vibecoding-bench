# Brief — AGY运行环境与Gemini API接入

## Goal

- 让现有AGY账号通过统一运行环境处理Gemini协议请求，完成文本、流式和工具续轮闭环。

## Scope

- 固定AGY 1.5.9内核、可复现制品及现有环境的启动、就绪、停止、恢复和资源管理。
- Gemini模型列表、generateContent、streamGenerateContent及调用方工具声明与结果回填。
- 按AGY账号实际模型能力接入Gemini和Claude模型，保存准确的平台与内核归属。
- AT-only工作副本、凭据代次切换、在途worker保护及有界认证恢复。
- 环境页平台能力、交互回归和供后续请求记录消费的基础事件。

## Non-Goals

- 工程任务与养号交互、新增公共Anthropic接口、new-api源码及渠道配置修改。
- 同形体文本转换、完整请求记录页面及跨子任务最终联调。
- 生产部署和新一轮真实模型费用。

## Technical Overview

- 在现有网关、账号选择、AccountRuntime和account-sender上增加AGY适配，复用令牌、权限、调度、代理及维护链路。
- 固化原型源码及版本化NDJSON适配，正式进程使用管理侧发布的AT-only OAuth状态；同版本共享只读封存代码映像。
- 新worker读取新代AT；真实工具结果先回填原worker完成该轮收尾，下一次模型生成再核对当前凭据代次。
- 流式响应采用原始Gemini逻辑帧，非流式沿同一执行路径聚合，按真实原生终态记录结果及用量。

## Context & Decisions

- 账号与凭据任务已经交付，当前分支为feat/agy-account-runtime，CC既有路径保持兼容。
- temperature、topP兼容接收并忽略，使用原生默认值；maxOutputTokens沿已验证映射处理。
- 公共模型名必须核对原生执行ID，接入覆盖账号实际支持的Gemini和Claude模型。
- 研究原型使用测试API Key与CA；正式适配使用OAuth及正常证书校验，交付通过现有镜像staging完成。
- 继续采用工程和隔离回环验证，真实模型调用预算为0。此前取消人工登录验收前置的决定持续适用。

## Risks

- 原型目前固定单个模型；实际目录映射、资源分项和共享映像须先完成零模型核对。
- 工具跨HTTP续轮、SSE开始后的取消及凭据换代涉及原worker归属，需要故障和并发验证。
- 真实Google身份、模型接受性及跨实际到期行为保留外部验证，由后续具备授权账号与预算的条件承接。

## Acceptance

- AGY模型请求按账号平台进入AGY内核，令牌账号权限和CC兼容回归通过。
- 文本、非流式、SSE、工具回填及temperature/topP兼容场景通过，签名、用量和终态来源准确。
- 新旧凭据代次、唯一刷新所有者、一次认证恢复、工具续轮、取消和重启隔离验证通过。
- 环境生命周期、资源与制品身份可核验，桌面和移动端草稿、焦点及迟到回执回归通过。

## Next Step

- 实现已接入现有环境与Gemini链路，当前进行完整Check-All及问题处置。
