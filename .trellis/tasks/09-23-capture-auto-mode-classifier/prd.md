# 为正式抓包 run 增加 Auto Mode 协议抓取

## Goal

让 vibecoding-bench 的正式抓包 run 可按次选择 Claude Code auto 权限模式，完整复用 orchestrator 的账号指纹、OAuth profile、代理、sidecar 与 worker 链路，部署后抓取官方 safeguards/safeguard_results 对照。

## Background

- 当前抓包 run 与普通 run 一样固定使用 `bypassPermissions`，不会触发 Claude Code 2.1.280 的服务端 Auto Mode classifier。
- 有效协议证据必须由正式 orchestrator run 产生，链路为 `worker → sidecar MITM → 账号既有代理 → api.anthropic.com`；不得用宿主网络、手工 worker 或 `jp.ai.flower-cli.com` 代替官方直连对照。
- 官方只公开 `safeguards` / `safeguard_results` 透传契约；完整内容需要真实抓包确认。
- 账号 7-12 的七日额度已经用尽，不用于最终样本；正式执行前按 OAuth usage 快照选择可用账号。

## Requirements

### R1：抓包权限模式快照

- `POST /api/captures/run` 增加仅抓包 run 使用的 `permission_mode`，允许 `bypassPermissions` 与 `auto`。
- 未传字段时保持 `bypassPermissions`，不改变普通任务、批量、养号、登录和 quota worker 的默认行为。
- 选定值写入 run 快照、调度 payload 和 worker 环境；抓包 run 的继续会话继承原值。
- Auto 只通过 Claude CLI 的 `--permission-mode auto` 对当前会话生效，不改写账号 profile 的持久默认权限模式。

### R2：正式 UI 与可观测性

- WebUI 抓包表单提供权限模式选择，默认显示并提交 `bypassPermissions`。
- 抓包详情显示实际权限模式，便于区分普通抓包和 Auto Mode 协议样本。
- README 说明 Auto 抓包用途、默认值和敏感数据边界。

### R3：官方直连协议样本

- 发布后通过正式 capture API 创建 `permission_mode=auto`、Claude Code 2.1.280 的抓包 run。
- 使用自然的环境检查提示词触发安全 Bash 工具调用，不在提示词中提及 classifier、`safeguards` 或测试目标。
- 请求必须走所选账号的 OAuth profile、稳定指纹、既有代理和 sidecar，目标为 `api.anthropic.com`。
- 从原始抓包和 Claude debug 中脱敏提取 `anthropic-beta`、`safeguards`、`safeguard_results`、SSE 位置及 tool-use ID 对应关系；原始凭据和正文不进入 Git。

## Acceptance Criteria

- [ ] 抓包 API 接受 `auto`，拒绝其他非法值；缺省行为仍为 `bypassPermissions`。
- [ ] run 记录、调度 payload、worker 启动参数和 continue 路径使用同一个权限模式快照。
- [ ] 普通、批量、养号、登录和 quota 路径仍使用原有权限模式。
- [ ] WebUI 可以选择并在详情中显示 `auto`，现有抓包表单字段保持可用。
- [ ] 后端单测、worker shell 检查、前端 JS 检查和 Compose 检查通过。
- [ ] 代码提交并推送后，GitHub Actions 构建成功，远端按不可变 tag/digest 部署并通过健康检查。
- [ ] 正式官方直连抓包中出现真实 `safeguards`；成功响应中出现可关联工具 ID 的 `safeguard_results`，或明确记录上游未返回结果的可复核证据。
- [ ] 最终报告只展示脱敏协议摘要，并给出远端受限原始证据路径。

## Out of Scope

- 本任务不修改 cc2api 的转发实现，不使用 `jp.ai.flower-cli.com` 生成官方对照样本。
- 本任务不改变普通 run 的权限策略，不把 Auto 写回账号 profile。
- 本任务不提交原始 flow、Authorization、OAuth token、完整提示词或模型正文。
