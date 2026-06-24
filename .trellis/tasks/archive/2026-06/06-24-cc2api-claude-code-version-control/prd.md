# cc2api Claude Code 版本升级控制

## Goal

在 cc2api 全局设置中完善 Claude Code 版本治理能力：保留现有版本画像升级流程，并新增独立的禁止版本规则，让管理员可以按精确版本、通配或范围阻止特定 Claude Code / Claude CLI 版本进入网关。

## User Value

- 管理员可以在发现某个 Claude Code 版本有协议风险、封禁风险或兼容性问题时，快速在网关侧禁止该版本。
- 禁止规则可以覆盖单个版本，也可以覆盖一段版本范围，不需要等待代码发版才能调整入口策略。
- 现有版本画像选择仍负责同步账号 `canonical_env.version/version_base/build_time` 和默认允许范围，新增禁止规则只作为额外拦截层。

## Confirmed Facts

- `cc2api` 已有全局 settings 接口：`GET /admin/settings` 和 `PUT /admin/settings`。
- 现有 `claude_code_version_profile` 支持选择内置 Claude Code 版本画像，并会同步所有账号 `canonical_env` 中的版本字段。
- 历史约定：切换 `claude_code_version_profile` 时会强制覆盖 `allowed_claude_code_versions`，但不修改 `allowed_user_agents`。
- 现有 `allowed_claude_code_versions` 只作用于 `User-Agent` 以 `claude-code/` 或 `claude-cli/` 开头的客户端。
- 现有版本规则语法已支持精确版本、通配和闭区间，例如 `2.1.187`、`2.1.*`、`2.1.89-2.1.187`。
- 现有设置页已经有“客户端访问策略”区域；`allowed_claude_code_versions` 当前由版本画像强制覆盖并以只读文本框展示。
- 新增 setting 按项目规范需要同步默认值、数据库默认插入、GET/PUT 校验、Gateway 热刷新、前端设置页和 README。
- 产品语义已确认：`blocked_claude_code_versions` 即使在 `allowed_claude_code_versions` 为空时也继续生效，用于“默认放开，只禁止已知坏版本”的治理模式。

## Requirements

- 新增全局 setting `blocked_claude_code_versions`，默认值为空字符串。
- `blocked_claude_code_versions` 使用与 `allowed_claude_code_versions` 相同的版本规则语法：
  - 精确版本：`2.1.187`
  - 通配：`2.1.*`
  - 闭区间：`2.1.180-2.1.187`
  - 支持逗号、换行或回车分隔。
- Gateway 在账号选择和上游请求之前校验 Claude Code / Claude CLI `User-Agent`：
  - 先识别 `claude-code/` / `claude-cli/` 版本号。
  - 被 `blocked_claude_code_versions` 命中时直接本地返回 403，不请求上游。
  - 未命中禁止规则时，再按现有 `allowed_claude_code_versions` 继续校验。
- `blocked_claude_code_versions` 在 `allowed_claude_code_versions` 为空时仍然生效。
- 禁止规则只影响 Claude Code / Claude CLI 入口版本，不影响非 Claude Code 客户端的 `allowed_user_agents`。
- 切换 `claude_code_version_profile` 仍按现有约定覆盖 `allowed_claude_code_versions` 并同步账号版本字段，但不得清空或覆盖 `blocked_claude_code_versions`。
- 设置页在“客户端访问策略”区域新增“禁止 Claude Code 版本”控件，支持管理员按行或逗号输入版本规则，并提供前端基础格式校验。
- 后端保存设置时必须校验 `blocked_claude_code_versions` 格式，非法配置返回 `BadRequest`。
- 保存 `blocked_claude_code_versions` 后必须热刷新 Gateway 访问策略，不能要求重启服务。
- README 的客户端访问策略说明要补充禁止版本规则、语法和优先级。

## Acceptance Criteria

- [ ] `GET /admin/settings` 在老数据库缺少 key 时返回 `blocked_claude_code_versions=""`。
- [ ] `PUT /admin/settings` 接受合法的禁止版本配置，并拒绝反向区间、非法版本号或过大的版本号。
- [ ] `claude-code/<version>` 或 `claude-cli/<version>` 命中禁止规则时返回 403，错误体包含 setting code `blocked_claude_code_versions`。
- [ ] 同一版本同时命中允许规则和禁止规则时，禁止规则优先生效。
- [ ] `allowed_claude_code_versions` 为空时，命中 `blocked_claude_code_versions` 的 Claude Code / CLI 版本仍返回 403。
- [ ] 非 Claude Code / CLI `User-Agent` 不受 `blocked_claude_code_versions` 影响。
- [ ] 选择新的 `claude_code_version_profile` 后，`blocked_claude_code_versions` 保持原值。
- [ ] 设置页可以加载、编辑、校验并保存禁止版本规则。
- [ ] 后端单测覆盖禁止精确版本、禁止范围、禁止通配、允许空禁止列表、禁止优先于允许、版本画像切换不覆盖禁止列表。
- [ ] 前端构建通过，后端格式化和测试通过。

## Notes

- 该任务涉及后端访问策略、settings 持久化/迁移、Gateway 热刷新、前端设置页和 README，属于复杂任务，需要补充 `design.md` 和 `implement.md` 后再开始实现。

## Open Questions

- 无。
