# cc2api Claude Code 版本升级控制 - Design

## Architecture

本任务在现有客户端访问策略上新增一层“禁止版本”规则，不引入新的路由或独立服务。实现边界如下：

- `src/service/access_policy.rs`：复用现有版本规则解析能力，扩展 `AccessPolicy` 同时持有允许规则和禁止规则。
- `src/store/settings_store.rs`：新增 `DEFAULT_BLOCKED_CLAUDE_CODE_VERSIONS_SETTING`，默认值为空字符串。
- `src/store/db.rs`：在 settings 默认插入列表中新增 `blocked_claude_code_versions`，老库迁移通过 `INSERT OR IGNORE` / `ON CONFLICT DO NOTHING` 自动补 key。
- `src/handler/router.rs`：`GET /admin/settings` 回填默认值，`PUT /admin/settings` 校验并触发 access policy 热刷新。
- `src/service/gateway.rs`：读取 `allowed_claude_code_versions`、`blocked_claude_code_versions`、`allowed_user_agents` 三个 setting，构造新的 `AccessPolicy`。
- `web/src/components/Settings.vue`：在“客户端访问策略”区域新增禁止版本输入控件，并把字段加入加载、校验和保存流程。
- `README.md`：补充禁止版本 setting、语法和优先级。

## Data Flow

```text
Settings.vue
  -> PUT /admin/settings { blocked_claude_code_versions: "2.1.187\n2.2.*" }
  -> router.rs 校验版本规则
  -> settings_store.upsert_many
  -> gateway_svc.reload_access_policy
  -> GatewayService 热路径读取 RwLock<AccessPolicy>
  -> claude-code/claude-cli User-Agent 入口校验
```

请求校验顺序：

1. 非 `claude-code/` / `claude-cli/` 的 User-Agent 跳过 Claude Code 版本规则，继续使用 `allowed_user_agents`。
2. Claude Code / CLI 请求先解析版本号。
3. 如果禁止规则非空且命中版本，返回 403，`setting=blocked_claude_code_versions`。
4. 如果没有命中禁止规则，按现有允许规则判断。
5. 如果允许规则为空，且未命中禁止规则，则允许通过。

## Contracts

- `blocked_claude_code_versions` 的语法必须与 `allowed_claude_code_versions` 完全一致。
- 版本规则解析和比较继续使用数字段比较：`2.1.9 < 2.1.89`，缺失段按 0 补齐。
- 禁止规则优先于允许规则。
- 禁止规则在允许规则为空时仍然生效。
- `claude_code_version_profile` 切换不得覆盖 `blocked_claude_code_versions`。
- 错误响应继续复用 `access_policy_error_response` 的 `{ type, error, setting, reason }` 结构。

## Compatibility

- 默认 `blocked_claude_code_versions=""`，升级后默认行为与当前线上一致。
- 老数据库不需要表结构变更，只新增 settings key。
- 旧客户端或脚本不提交 `blocked_claude_code_versions` 时，后端保持现有值或默认空值。
- 切换版本画像仍只覆盖 `allowed_claude_code_versions` 和账号 `canonical_env`，不影响禁止列表和 UA 白名单。

## UI

设置页沿用现有“客户端访问策略”卡片：

- `Claude Code 版本范围` 保持只读，用于展示版本画像强制覆盖后的允许范围。
- 新增 `禁止 Claude Code 版本` 文本域，支持逐行或逗号分隔输入。
- 说明文案强调：禁止规则优先生效；允许范围为空时仍会拦截禁止版本；只影响 `claude-code/` / `claude-cli`。
- 前端基础校验复用当前版本规则正则；最终校验以后端为准。

## Tests

后端重点测试 `access_policy.rs`、`settings_store.rs` 和 `db.rs`：

- 禁止精确版本、通配、范围。
- 禁止优先于允许。
- 允许规则为空时禁止仍生效。
- 非 Claude Code UA 不受禁止规则影响。
- 反向区间、非法版本号、过大版本号返回错误，错误文案中的 setting 指向正确 key。
- 切换 `claude_code_version_profile` 后，`blocked_claude_code_versions` 保持原值。
- migrate 给老 settings 表补默认空禁止列表。

前端验证 `npm run build`，并手工检查设置页字段加载和保存 payload。

## Risks

- 当前 `parse_version_parts` 的错误文案硬编码 `allowed_claude_code_versions`。实现时应让解析函数接收 setting 名称，否则禁止列表的错误信息会指向错误 key。
- `AccessPolicy::parse` 调用点较多，修改签名时要同步 tests、`GatewayService::new` 和 `reload_access_policy`。
- `update_settings` 中 profile 切换会先把 `allowed_claude_code_versions` 写进 body，之后调用 `apply_claude_code_profile` 并移除两个 key；新增禁止列表不能被这个流程误删。
