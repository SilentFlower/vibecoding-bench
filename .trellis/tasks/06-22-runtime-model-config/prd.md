# 运行模型动态配置

## Goal

把普通运行和批量运行使用的 Claude Code 默认模型从代码硬编码改为可配置项，便于在当前默认模型不可用时快速切换到其它模型，而不需要修改镜像脚本或代码。

用户价值：
- 当 `opus` / `opus[1m]` / 特定 Opus 版本不可用时，可以通过配置切换到 `sonnet[1m]`、`haiku` 或完整模型 ID。
- 保留现有默认行为，避免已有部署升级后模型选择突然变化。

## Confirmed Facts

- worker 入口 `images/worker/entrypoint.sh` 里的默认 `settings.json` 当前固定写入 `model: 'opus[1m]'`。
- worker 已支持一次性环境变量 `CLAUDE_MODEL_OVERRIDE`，启动 `claude` 时会转成 `--model <value>`，且不会写入账号 profile。
- orchestrator 已有 `normalize_claude_model_override` 校验逻辑，允许字母、数字、点、下划线、短横线和 `[]`。
- 当前 `CLAUDE_MODEL_OVERRIDE` 只由完整 HTTP 抓包 run 的 `model_override` 入口使用。
- 普通单次 task 和批量 task 的创建表单/API 没有模型字段，也没有全局默认模型配置。
- `.env.example` 目前没有默认运行模型配置项。
- 用户已确认本任务只需要全局默认模型配置，不需要给普通单次 task / 批量 task 增加逐次模型覆盖字段。
- 用户已确认抓包 run 不应被全局默认模型配置影响；抓包 run 继续只受已有 `model_override` 参数影响。

## Requirements

- 新增全局默认模型配置项，建议命名为 `CLAUDE_DEFAULT_MODEL`，默认值保持 `opus[1m]`。
- orchestrator 创建普通运行和批量运行的 worker 时必须把全局默认模型通过一次性模型参数传给 worker，优先复用抓包 run 已使用的 `CLAUDE_MODEL_OVERRIDE` 链路。
- 账号 profile 的默认 `settings.json` 模型继续保持现有 `opus[1m]` 基线，避免普通/批量运行的全局配置污染抓包 run。
- 抓包 run 必须保持现有行为：只有前端/接口传入 `model_override` 时才使用一次性覆盖；全局 `CLAUDE_DEFAULT_MODEL` 不改变抓包 run 的默认模型。
- 模型配置值必须复用现有模型名校验规则，避免无效字符进入 shell / CLI 参数。
- `.env.example`、`docker-compose.yml`、`docker-compose.remote.yml` 和 README 需要说明默认模型配置方式。
- 现有部署未配置 `CLAUDE_DEFAULT_MODEL` 时，行为必须与当前一致。

## Acceptance Criteria

- [ ] 未设置 `CLAUDE_DEFAULT_MODEL` 时，普通运行、批量运行和抓包 run 的默认模型仍是 `opus[1m]`。
- [ ] 设置 `CLAUDE_DEFAULT_MODEL=sonnet[1m]` 后，新启动的普通运行和批量运行会使用 `sonnet[1m]`。
- [ ] 设置 `CLAUDE_DEFAULT_MODEL=sonnet[1m]` 后，抓包 run 未填写 `model_override` 时仍使用抓包现有默认模型，不受全局配置影响。
- [ ] 抓包 run 的 `model_override` 非空时，本次 run 使用覆盖模型，且该覆盖仍只影响当前抓包 run。
- [ ] 非法模型配置会在 orchestrator 启动或创建 run 前给出明确错误，不静默回退。
- [ ] 文档说明修改 `.env` 后需要 recreate/restart orchestrator，已运行中的 run 不受影响。

## Out of Scope

- 不自动检测模型可用性或按失败状态自动降级。
- 不改 Claude Code CLI 本身的模型列表。
- 不迁移历史 run 的记录。
- 不给普通单次 task / 批量 task 增加逐次模型覆盖 UI。

## Open Questions

- 无。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
