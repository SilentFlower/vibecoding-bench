# 抓包 run 支持一次性模型覆盖

## Goal

为 vibecoding-bench 的完整抓包 run 增加一次性 Claude Code 模型覆盖能力。用户在启动抓包时可以从常用模型列表中选择，也可以手填任意自定义模型名；该模型只作用于本次抓包运行，不修改账号长期 `settings.json`。

## Background / Known Context

- 当前抓包入口位于 WebUI runs 页的“完整抓包”表单，对应后端 `POST /api/captures/run`。
- worker 默认通过 `~/.claude/settings.json` 写入 `model: "opus[1m]"`。
- 用户希望升级 Claude Code CLI 默认版本到 `2.1.172`。
- 用户确认一次性覆盖更适合使用 Claude Code CLI 的 `--model <model>` 参数，而不是长期修改 profile `settings.json`。
- `claude --help` 显示 `--model <model>` 支持别名和完整模型名；官方文档允许 alias 或 full model name。

## Requirements

- 将项目默认 Claude Code CLI 版本从 `2.1.169` 升级到 `2.1.172`，保持 Dockerfile、docker-compose 默认值、orchestrator 环境变量和 usage 请求 UA 一致。
- 在完整抓包表单增加模型选择能力：
  - 通过带预置选项的输入框提供常用模型选择。
  - 同一个输入框支持手填自定义模型名。
  - 留空时沿用现有默认模型行为。
- 预置模型至少包含：
  - `opus`
  - `opus[1m]`
  - `sonnet`
  - `sonnet[1m]`
  - `haiku`
  - `fable`
  - `claude-opus-4-8`
  - `claude-opus-4-8[1m]`
  - `claude-opus-4-7`
  - `claude-fable-5`
- 后端 `POST /api/captures/run` 接收可选模型字段，做基础校验和 trim。
- 后端启动 worker 时仅对本次抓包 run 传入模型覆盖。
- worker 启动 `claude` 时，如果存在本次模型覆盖，则使用 `--model <model>`。
- 模型覆盖不得写回账号 profile，不得污染后续普通 run 或抓包 run。
- 运行详情或抓包结果中需要能看到本次覆盖模型，便于回看抓包语境。

## Acceptance Criteria

- [ ] 默认不填写模型时，抓包 run 行为与当前一致。
- [ ] 选择预置模型后，worker 启动命令带上对应 `--model <model>`。
- [ ] 手填自定义模型名后，worker 启动命令带上手填值。
- [ ] 自定义模型名非法或过长时，后端拒绝启动并返回可读错误。
- [ ] 抓包 run 的模型覆盖只影响本次 run，不修改账号 profile 的 `settings.json`。
- [ ] 前端提供预置选择和自定义输入，提交单个 trim 后的模型覆盖值。
- [ ] Claude Code 默认版本相关配置全部为 `2.1.172`。
- [ ] 通过 Python 语法检查、worker shell 语法检查、前端静态检查或手动 smoke 验证、`git diff --check`。

## Out of Scope

- 不做全局默认模型设置页。
- 不自动从 Anthropic API 拉取实时模型列表。
- 不为普通非抓包 run 增加模型选择。
- 不改变账号 profile 的长期模型偏好。

## Research References

- `claude --help`：`--model <model>` 为当前会话模型覆盖。
- Anthropic Claude Code 文档：模型可使用 alias 或 full model name；settings `model` 是默认值，CLI 参数可覆盖。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
