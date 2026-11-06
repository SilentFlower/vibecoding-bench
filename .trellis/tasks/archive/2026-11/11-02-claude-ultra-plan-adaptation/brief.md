# Brief — Ultra 套餐适配

## Goal

- 让 v3 和 ai-fund 正确识别 Ultra/Max，并部署新版。

## Scope

- 贯通真实套餐分级字段、协议处理与两边账号展示。
- 区分真实、空值和未知的 5h 窗口，保留周额度和 Fable 控制。
- 增加旧来源显式停用能力，发布 v3 联合镜像与 ai-fund 主版 Worker/Pages。

## Non-Goals

- 不改 RPM/调度算法或全局 CLI 版本，不增加主动模型探针。

## Technical Overview

- 从官方 profile 保存原始类型与真实分级，协议保真，展示按明确证据识别；同步双库、管理接口和重授权幂等。

## Context & Decisions

- 9-17 仍返回 max/default_claude_max_20x，不能只改名称；普通 max 不猜档位，Ultra 也不一律取消 5h 保护。

## Risks

- 缺失分级或用量数据继续表示未知；元数据更新不得覆盖轮换凭据。

## Acceptance

- 套餐、窗口、凭据往返/幂等和来源隔离测试通过，两前端构建及部署健康通过；停用来源零请求。

## Next Step

- 启动本子任务，贯通真实分级字段与回归测试。
