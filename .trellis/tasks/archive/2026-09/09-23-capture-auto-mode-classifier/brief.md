# Brief — 扩展正式抓包权限模式并核对 Auto Mode 协议

## Goal

- 让 vibecoding-bench 的正式抓包 run 可按次选择 Claude Code 2.1.280 的六种权限模式，并在完整复用目标账号运行环境的前提下，以模式/模型矩阵核对官方 Auto Mode classifier 的真实协议，再同步 cc2api。

## Scope

- 将 `POST /api/captures/run` 的 `permission_mode` 扩为 `manual`、`acceptEdits`、`plan`、`auto`、`dontAsk` 与 `bypassPermissions`，缺省保持 `bypassPermissions`。
- 将权限模式保存为 run 快照，并贯穿 scheduler payload、worker 环境、Claude CLI 启动参数和 capture continue 路径。
- 在抓包 WebUI 中展示六种权限模式，并在抓包详情中显示实际模式。
- 更新 README，说明权限模式对照、默认值和敏感数据边界。
- 完成单测、脚本语法、前端语法、Compose 和 Check-All 验证。
- 精确提交并推送本任务改动，等待 GitHub Actions 构建成功，按不可变提交镜像部署远端。
- 通过正式 capture API 创建 Opus 5.5 六模式和 Opus 4.8/Sonnet 4.5 auto/plan 矩阵，使用自然工程任务触发安全工具调用，提取脱敏后的 `safeguards` / `safeguard_results` 协议证据。
- 根据最终矩阵更新 cc2api 的模型级 beta 画像并验证请求体和 SSE 透明透传。

## Non-Goals

- 不使用宿主机直连、手工创建的 worker、临时容器或 `jp.ai.flower-cli.com` 生成官方对照样本；这些路径产生的结果不得作为验收证据。
- 不改变普通、批量、养号、登录和 quota run 的权限策略，也不把 `auto` 写回账号 profile。
- 不向 Git 提交原始 flow、Authorization、OAuth token、完整提示词或模型正文。

## Key Decisions

- 权限模式是每次抓包 run 的不可变快照，不是账号级持久配置；这样 continue 会继承原值，同时后续普通任务仍使用 `bypassPermissions`。
- 所选值只通过 Claude CLI 的 `--permission-mode` 对当前进程生效；现有 profile 默认设置保持不变，避免同步 profile 时污染账号后续行为。
- 官方文档确认 Plan 模式默认可复用 Auto classifier 审核命令，因此 Opus 5.5 必须覆盖全部六种模式；Opus 4.8 与不支持 Auto 的 Sonnet 4.5 用 auto/plan 复核模型边界。
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
- cc2api 已发现普通 beta 画像与第一轮 Auto 抓包存在差异；先保留本地未提交草案，等待扩展矩阵完成后再收敛并提交。

## Acceptance

- 抓包 API 接受六种 CLI 权限模式、拒绝非法值，未传字段时仍为 `bypassPermissions`。
- run 记录、scheduler payload、worker 启动参数和 continue 路径使用同一权限模式快照。
- 普通、批量、养号、登录和 quota 路径保持原行为。
- WebUI 可选择并显示六种权限模式，现有抓包字段继续可用。
- 后端单测、worker shell 检查、前端 JS 检查、两份 Compose 配置检查和 full Check-All 全部通过。
- 本任务代码提交并推送后，GitHub Actions 三个 bench 镜像构建成功；远端按提交 SHA 镜像部署并通过健康与版本检查。
- 正式官方抓包只能由 capture API / orchestrator 创建，并确认其复用了目标账号的完整环境、代理和 sidecar，目标 host 为 `api.anthropic.com`。
- 完成 Opus 5.5 六模式及 Opus 4.8/Sonnet 4.5 auto/plan 对照，明确 safeguards、结果事件与 beta 的模式边界。
- cc2api 请求体与 SSE 透明透传、条件 beta 画像以及 Rust 全量测试通过。
- 最终仅展示脱敏协议摘要，并给出远端受限原始证据路径。

## Next Step

- 先扩展 bench 的模式枚举并发布，再执行正式矩阵；最后按矩阵修正 cc2api、提交、构建和部署。
