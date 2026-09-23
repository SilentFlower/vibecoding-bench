# Brief — 为正式抓包 run 增加 Auto Mode 协议抓取

## Goal

- 让 vibecoding-bench 的正式抓包 run 可按次选择 Claude Code `auto` 权限模式，并在完整复用目标账号运行环境的前提下，抓取官方 Anthropic Auto Mode classifier 的真实协议样本。

## Scope

- 为 `POST /api/captures/run` 增加仅抓包 run 使用的 `permission_mode` 字段，允许 `bypassPermissions` 与 `auto`，缺省保持 `bypassPermissions`。
- 将权限模式保存为 run 快照，并贯穿 scheduler payload、worker 环境、Claude CLI 启动参数和 capture continue 路径。
- 在抓包 WebUI 中增加权限模式选择，并在抓包详情中显示实际模式。
- 更新 README，说明 Auto 抓包的用途、默认值和敏感数据边界。
- 完成单测、脚本语法、前端语法、Compose 和 Check-All 验证。
- 精确提交并推送本任务改动，等待 GitHub Actions 构建成功，按不可变提交镜像部署远端。
- 通过正式 capture API 创建 Claude Code 2.1.280 的 Auto run，使用自然提示词触发安全 Bash 工具调用，提取脱敏后的 `safeguards` / `safeguard_results` 协议证据。

## Non-Goals

- 不修改 cc2api 的转发实现。
- 不使用宿主机直连、手工创建的 worker、临时容器或 `jp.ai.flower-cli.com` 生成官方对照样本；这些路径产生的结果不得作为验收证据。
- 不改变普通、批量、养号、登录和 quota run 的权限策略，也不把 `auto` 写回账号 profile。
- 不向 Git 提交原始 flow、Authorization、OAuth token、完整提示词或模型正文。

## Key Decisions

- 权限模式是每次抓包 run 的不可变快照，不是账号级持久配置；这样 continue 会继承原值，同时后续普通任务仍使用 `bypassPermissions`。
- `auto` 只通过 Claude CLI 的 `--permission-mode auto` 对当前进程生效；现有 profile 默认设置保持不变，避免同步 profile 时污染账号后续行为。
- 正式协议证据必须由 orchestrator 创建的 capture run 产生，实际链路固定为 `worker → sidecar MITM → 账号既有代理 → api.anthropic.com`。
- 正式 run 必须复用所选账号的 OAuth profile、hostname、MAC、machine-id、TZ、LANG、cgroup 内存、sidecar CA、代理出口和当前 worker 镜像，不得绕过任何一层直接发请求。
- 最终样本优先使用 Claude Code 2.1.280 / Opus 5.5；若额度或支持范围限制，可用受支持的低额度模型复核，并单独标明模型与限制。

## Key Context

- 后端数据流为 `CaptureRunIn.permission_mode → runs.capture_permission_mode → scheduler task → worker 环境 → entrypoint → Claude CLI`。
- SQLite 新列通过现有 `_ensure_column` 幂等补齐；历史 run 的空值按 `bypassPermissions` 解释。
- 抓包 continue 必须从原 run 读取权限模式，不能回退为进程默认值。
- 账号 7-12 的七日额度已用尽，正式执行前需读取 OAuth usage 快照，并选择额度可用且没有并发 run 的账号。
- 原始抓包与 Claude debug 只保存在远端受限路径；仓库与最终报告只保留脱敏摘要以及原始证据路径。

## Risks / Deferred

- Auto Mode 可能受模型支持范围、账号额度、地区 rollout 或 Anthropic 上游状态影响；若没有返回预期字段，需保留可复核的上游响应证据并区分具体原因。
- 重点防止历史 run 空值解释错误、continue 漏传权限模式，以及 CLI 覆盖被误写回账号 profile。
- cc2api 对新 classifier 字段的正式透传改造延后；本任务先取得官方直连基线，再据此决定 cc2api 是否需要修改。

## Acceptance

- 抓包 API 接受 `auto`、拒绝非法值，未传字段时仍为 `bypassPermissions`。
- run 记录、scheduler payload、worker 启动参数和 continue 路径使用同一权限模式快照。
- 普通、批量、养号、登录和 quota 路径保持原行为。
- WebUI 可选择并显示 `auto`，现有抓包字段继续可用。
- 后端单测、worker shell 检查、前端 JS 检查、两份 Compose 配置检查和 full Check-All 全部通过。
- 本任务代码提交并推送后，GitHub Actions 三个 bench 镜像构建成功；远端按提交 SHA 镜像部署并通过健康与版本检查。
- 正式官方抓包只能由 capture API / orchestrator 创建，并确认其复用了目标账号的完整环境、代理和 sidecar，目标 host 为 `api.anthropic.com`。
- 官方抓包中出现真实 `safeguards`，成功响应中出现可与 tool-use ID 关联的 `safeguard_results`；若上游未返回，则提供脱敏且可复核的原因证据。
- 最终仅展示脱敏协议摘要，并给出远端受限原始证据路径。

## Next Step

- 启动任务后，先读取相关 DTO、数据库、调度器、worker entrypoint 与 WebUI 的现有定义，再实现 `permission_mode` 的端到端快照传递。
