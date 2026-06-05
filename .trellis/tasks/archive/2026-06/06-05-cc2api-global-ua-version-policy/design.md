# cc2api 全局 Claude Code 版本与 UA 访问策略

## Technical Design

### Scope

本任务在 cc2api 中增加全局入口访问策略：

- `allowed_claude_code_versions`：允许的 Claude Code / Claude CLI 版本范围。
- `allowed_user_agents`：允许访问的原始客户端 User-Agent pattern 列表。

配置存储复用现有 `settings` 表和 `/admin/settings` API。设置页复用 `web/src/components/Settings.vue`。

### Data Flow

1. 请求进入 `GatewayService::handle_request_inner`。
2. 读取原始 `User-Agent` 和请求体。
3. 在账号选择、并发槽位、请求改写和上游请求之前执行全局访问策略校验。
4. 若不通过，返回本地拒绝响应，不请求上游。
5. 若通过，继续现有流程。

### Matching Rules

#### User-Agent

- 配置格式：逗号或换行分隔。
- 每个条目为 literal pattern，只有 `*` 具备通配语义。
- `*` 匹配任意字符，大小写敏感。
- 默认配置允许 `AI-Hub-Monitor*` 和 `python-httpx*`。
- 空配置表示不限制 User-Agent。
- 非空配置下，缺失或为空的 `User-Agent` 不允许通过。

示例：

```text
claude-code/*
claude-cli/*
MyClient/1.*
```

#### Claude Code Version

- 只对 `User-Agent` 以 `claude-code/` 或 `claude-cli/` 开头的请求生效。
- 配置格式：逗号或换行分隔。
- 支持三种条目：
  - 精确版本：`2.1.156`
  - 通配版本：`2.1.*`
  - 闭区间：`2.1.150-2.1.180`
- 版本比较按数字段比较，`2.1.9 < 2.1.10`。
- 无法从 Claude Code / Claude CLI UA 解析版本时，若版本限制非空，则拒绝。
- 默认配置为 `2.1.89-2.1.156`。
- 空配置表示不限制 Claude Code 版本。

### Compatibility

- 新增 settings 默认值为 `allowed_claude_code_versions=2.1.89-2.1.156`、`allowed_user_agents=AI-Hub-Monitor*\npython-httpx*`；清空配置可关闭对应限制。
- 配置更新后通过重新加载网关内存策略即时生效，避免每个请求读数据库。
- 错误响应应包含配置项名称和被拒绝原因，但不输出 token、请求体或敏感内容。

### Validation

- 后端保存 settings 时校验 UA pattern 和版本范围格式。
- UA pattern 限制为可打印 ASCII，允许常见 UA 字符和 `*`。
- 版本范围仅允许数字、点、`*`、`-`、逗号、换行和空白。

### Tests

- 单元测试覆盖 UA pattern 匹配。
- 单元测试覆盖版本范围解析和比较。
- 网关策略测试覆盖默认放行、UA 拒绝、版本拒绝。
- 前端至少通过 typecheck/build 验证设置页字段绑定。

## Rollout / Rollback

- Rollout：默认只允许指定 Claude Code / CLI 版本范围，并额外允许 `AI-Hub-Monitor*`、`python-httpx*` 这类非 Claude Code UA。
- Rollback：清空 `allowed_claude_code_versions` 和 `allowed_user_agents` 即可恢复不限制行为；必要时回滚代码也不会破坏现有 settings 表。
