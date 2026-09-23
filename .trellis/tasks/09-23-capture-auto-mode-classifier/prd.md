# 扩展正式抓包权限模式并核对 Auto Mode 协议

## Goal

让 vibecoding-bench 的正式抓包 run 可按次选择 Claude Code 2.1.280 的全部六种权限模式，完整复用 orchestrator 的账号指纹、OAuth profile、代理、sidecar 与 worker 链路，通过模式与模型对照确认 safeguards/safeguard_results 的触发边界，并据此同步 cc2api。

## Background

- 第一轮已支持 `bypassPermissions` 与 `auto`，但 Claude Code 2.1.280 还提供 `manual`、`acceptEdits`、`dontAsk` 与 `plan`。
- 官方文档明确说明：启用 Auto Mode 能力且 `useAutoModeDuringPlan` 保持默认开启时，Plan 模式也会调用 classifier 审核命令，因此只比较 `auto` 与 `bypassPermissions` 不足以确定协议边界。
- 有效协议证据必须由正式 orchestrator run 产生，链路为 `worker → sidecar MITM → 账号既有代理 → api.anthropic.com`；不得用宿主网络、手工 worker 或 `jp.ai.flower-cli.com` 代替官方直连对照。
- 官方只公开 `safeguards` / `safeguard_results` 透传契约；完整内容需要真实抓包确认。
- 账号 7-12 的七日额度已经用尽，不用于最终样本；正式执行前按 OAuth usage 快照选择可用账号。

## Requirements

### R1：抓包权限模式快照

- `POST /api/captures/run` 的 `permission_mode` 允许 Claude Code 2.1.280 CLI 暴露的六个值：`manual`、`acceptEdits`、`plan`、`auto`、`dontAsk` 与 `bypassPermissions`。
- 未传字段时保持 `bypassPermissions`，不改变普通任务、批量、养号、登录和 quota worker 的默认行为。
- 选定值写入 run 快照、调度 payload 和 worker 环境；抓包 run 的继续会话继承原值。
- 所选模式只通过 Claude CLI 的 `--permission-mode` 对当前会话生效，不改写账号 profile 的持久默认权限模式。

### R2：正式 UI 与可观测性

- WebUI 抓包表单提供六种权限模式选择，默认显示并提交 `bypassPermissions`。
- 抓包详情显示实际权限模式，便于区分普通抓包和 Auto Mode 协议样本。
- README 说明 Auto 抓包用途、默认值和敏感数据边界。

### R3：官方直连协议矩阵

- 发布后通过正式 capture API 创建 Claude Code 2.1.280 抓包矩阵：Opus 5.5 覆盖六种权限模式；Opus 4.8 与 Sonnet 4.5 覆盖 `auto`、`plan` 两个 classifier 重点分支。
- 使用语义相近的自然工程任务触发安全工具调用，不在提示词中提及 classifier、`safeguards`、权限模式或测试目标。
- 请求必须走所选账号的 OAuth profile、稳定指纹、既有代理和 sidecar，目标为 `api.anthropic.com`。
- 从原始抓包和 Claude debug 中脱敏提取 `anthropic-beta`、`safeguards`、`safeguard_results`、SSE 位置及 tool-use ID 对应关系；原始凭据和正文不进入 Git。

### R4：同步 cc2api

- 以扩展矩阵为准确定义普通请求、Auto Mode 与 Plan Mode 的模型级 beta 画像，不从权限模式名称猜测未观察行为。
- cc2api 必须保留请求体 `safeguards` 及未知 `classifier_context` 字段，并原样转发 SSE `message_delta.delta.safeguard_results`。
- 新协议兼容不得改变旧版独立 classifier 请求的本地拦截逻辑。

## Acceptance Criteria

- [x] 抓包 API 接受六种 CLI 权限模式，拒绝其他非法值；缺省行为仍为 `bypassPermissions`。
- [x] run 记录、调度 payload、worker 启动参数和 continue 路径使用同一个权限模式快照。
- [x] 普通、批量、养号、登录和 quota 路径仍使用原有权限模式。
- [x] WebUI 可以选择并显示六种权限模式，现有抓包表单字段保持可用。
- [x] 后端单测、worker shell 检查、前端 JS 检查和 Compose 检查通过。
- [x] 代码提交并推送后，GitHub Actions 构建成功，远端按不可变 tag/digest 部署并通过健康检查。
- [x] 完成 Opus 5.5 六模式以及 Opus 4.8/Sonnet 4.5 的 auto/plan 对照，明确每个分支是否出现 `safeguards`、`safeguard_results` 及 beta 差异。
- [x] cc2api 根据最终证据完成条件画像与透明透传测试，完整 Rust 测试通过。
- [x] 最终报告只展示脱敏协议摘要，并给出远端受限原始证据路径。

## Out of Scope

- 本任务不使用 `jp.ai.flower-cli.com`、宿主机直连或手工请求生成官方对照样本。
- 本任务不改变普通 run 的权限策略，不把 Auto 写回账号 profile。
- 本任务不提交原始 flow、Authorization、OAuth token、完整提示词或模型正文。
