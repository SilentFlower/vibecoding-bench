# 思考预算动态配置

## Goal

把普通运行和批量运行使用的 Claude Code 思考预算从只能通过 `.env` 静态配置，改成可以在 WebUI 运行页动态调整，便于在额度紧张或需要提速时从 `max` 切到 `high` / `medium` / `low`，且不需要重启 orchestrator。

同时修复一次现场问题：run `71786b5cd2a9` 在 Claude TUI 连续 `API error` / `Request timed out` 后被记录为 `success`。这类 API timeout 不能被当成成功交付，需要被 watchdog 尝试恢复；最终仍失败时必须标成失败并暴露明确错误。

用户价值：
- 遇到额度消耗过高、运行时间过长时，可以立即降低新启动 run 的思考预算。
- 保留 `.env` 作为兜底默认值，避免现有部署升级后行为突然变化。
- 避免 API timeout 的半成品 run 被误记为成功，后续排查能直接看到真实失败原因。

## Confirmed Facts

- 当前 `CLAUDE_CODE_EFFORT_LEVEL` 在 `orchestrator/main.py` 中由环境变量读取，默认值是 `max`。
- `Runner.start_run()` 会把 `CLAUDE_CODE_EFFORT_LEVEL` 传给 worker 环境变量。
- worker 入口 `images/worker/entrypoint.sh` 会把该值写进默认 `settings.json` 的 `env.CLAUDE_CODE_EFFORT_LEVEL`。
- WebUI 运行页已经有“默认模型”运行时配置面板，后端已经有 `app_settings` 表和 `/api/settings/runtime-model` 风格的持久配置接口。
- 远端部署文档和 README 目前仍描述思考预算需要修改 `.env` 后 recreate。
- 现场 run `71786b5cd2a9` 使用 `claude-opus-4-6`，前几次 `/v1/messages` 为 200；后续消息请求只有 request 没有 response，TUI 显示 `Request timed out · attempt 10/10`。
- 当前 worker 的 API 卡死恢复主要依赖 Claude JSONL 的 `system api_error`；`71786b5cd2a9` 这类 synthetic `Request timed out` 没被识别，最终被完成判断当成普通 assistant 文本。

## Requirements

- 新增 WebUI 运行页的思考预算配置入口，保存后持久化到 SQLite。
- 页面配置优先于 `.env` 中的 `CLAUDE_CODE_EFFORT_LEVEL`；页面清空 / 重置后回退到 `.env`。
- 新启动的普通运行和批量运行必须在 worker 启动时读取当前页面配置，不需要重启 orchestrator。
- 抓包 run 必须保持隔离：不受页面思考预算配置影响，继续只使用 `.env` / 现有抓包默认行为。
- 思考预算值必须限制在 Claude Code 支持的预期枚举内，至少包含 `max`、`xhigh`、`high`、`medium`、`low`。
- 账号 profile 的长期配置不应被页面运行时配置污染；仍通过本次 worker 环境变量生效。
- `.env.example`、README 和远程部署 spec 需要说明页面配置优先级和 `.env` 兜底关系。
- 现有部署未配置页面覆盖值时，行为必须与当前一致：默认 `max`。
- worker 必须识别 Claude TUI transcript 中的 API retry / request timeout 卡死迹象，在没有有效对话或 workspace 进展超过 watchdog 窗口时走现有自动中断续跑机制。
- worker 必须识别 Claude JSONL 中的 synthetic API error 终态，例如 `isApiErrorMessage=true` 且文本为 `Request timed out`，不能把它判定为成功。
- synthetic API timeout 终态应写入 `.bench-status.json` 或 run 错误信息，使 WebUI 能显示明确失败原因。

## Acceptance Criteria

- [ ] 未设置页面覆盖值且未改 `.env` 时，新启动 run 的思考预算仍为 `max`。
- [ ] 在 WebUI 保存思考预算为 `medium` 后，新启动的普通运行和批量运行使用 `medium`，且不需要重启 orchestrator。
- [ ] 在 WebUI 清空 / 重置思考预算后，新启动的普通运行和批量运行回退到 `.env` 的 `CLAUDE_CODE_EFFORT_LEVEL`。
- [ ] 在 WebUI 保存思考预算后，抓包 run 仍不受页面配置影响。
- [ ] 非法思考预算值会被保存接口拒绝，并给出明确错误，不静默回退。
- [ ] 文档说明页面配置优先级高于 `.env`；只有修改 `.env` 兜底值时才需要 recreate/restart orchestrator。
- [ ] 当 Claude TUI 长时间停留在 `API error · Retrying ...` / `Request timed out · Retrying ...` 且没有产物进展时，worker 会按现有恢复上限中断并注入续跑提示。
- [ ] 当 Claude JSONL 出现 synthetic `Request timed out` API error 终态时，run 不会被标为 `success`，而是失败并显示可诊断错误。

## Out of Scope

- 不自动根据额度或失败状态调整思考预算。
- 不给普通单次 task / 批量 task 增加逐次思考预算覆盖字段。
- 不迁移历史 run 记录。
- 不改变抓包 run 的运行参数隔离策略。

## Open Questions

- 无。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
