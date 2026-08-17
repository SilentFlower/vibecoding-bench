# 技术设计

## 设计目标

在不改变账号调度、并发、RPM 和普通 401/429 语义的前提下，为 Token 预解析增加可判定的永久凭据错误，并复用现有账号停用与账号排除循环完成同请求切号。

## 根因链路

```text
选择 active 账号
  -> 获取槽位 / RPM admission
  -> resolve_upstream_token
  -> refresh_oauth_account
  -> token endpoint: 400 invalid_grant
  -> 仅 update_auth_error + ServiceUnavailable
  -> Gateway 直接 return
  -> 账号 status 仍为 active
  -> 下一请求再次入选
```

修复后的目标链路：

```text
token endpoint: invalid_grant
  -> 结构化 PermanentCredential 错误
  -> disable_for_auth_failure
  -> exclude_ids.push(account.id)
  -> 释放当前槽位
  -> continue 选择下一账号
  -> 成功，或所有账号不可用后返回通用 503
```

## 错误分类

在现有 `AppError` 体系中增加一个明确的永久凭据错误类别，例如 `PermanentCredential(String)`，HTTP 映射保持 503。该类别只携带脱敏摘要，使 `AccountService`、Gateway 和管理端调用方都能保留机器可判定语义。

OAuth token endpoint 非 2xx 时优先按 JSON 解析短错误码：

| 条件 | 分类 | 账号动作 |
| --- | --- | --- |
| `error=invalid_grant` | 永久凭据错误 | Gateway 停用并排除 |
| refresh token 为空 | 永久凭据错误 | Gateway 停用并排除 |
| HTTP 429 | 临时错误 | 不停用，不跨账号放大 |
| HTTP 5xx | 临时错误 | 不停用 |
| 网络/超时/响应解析失败 | 临时错误 | 不停用 |
| 其他 OAuth 4xx | 默认临时错误 | 不在缺少证据时扩大停用范围 |

错误摘要只允许固定前缀、HTTP 状态和短错误码。OAuth `error_description` 和原始正文不进入停用原因；测试只使用虚构 token。

## AccountService 行为

- `resolve_upstream_token()` 继续返回 `Result<String, AppError>`，但永久错误不再退化成普通 `ServiceUnavailable`。
- `refresh_oauth_account()` 遇到永久凭据错误时：
  1. 写入脱敏 `auth_error`；
  2. 即使当前 AT 尚未过期，也不执行 fallback；
  3. 向调用方保留永久错误类别。
- 临时刷新错误仍按现有策略：允许在 `allow_still_valid_fallback=true` 且 AT 仍有效时返回旧 AT。
- 账号状态变更仍由 Gateway 调用 `disable_for_auth_failure()` 完成，避免后台 usage/telemetry/管理端解析一次临时调用就擅自改变调度状态。

## Gateway 行为

### `/v1/messages`

Token 预解析 match 增加永久错误分支：

1. 调用 `disable_for_auth_failure(account.id, safe_reason)`。
2. 设置 `auth_failure_excluded=true`。
3. 把账号 ID 加入 `exclude_ids`。
4. 显式释放 `slot_guard`。
5. `continue` 当前账号选择循环。

普通 `ServiceUnavailable` 等临时错误继续直接返回，防止 OAuth endpoint 整体故障时逐账号放大请求。

### `/v1/messages/count_tokens`

复用相同永久错误处理语义，在现有账号循环内停用、排除并继续。所有候选耗尽时返回 Anthropic `api_error` 503，不返回当前的 Token 获取 502 文案。

### Sticky 与 RPM

- `exclude_ids` 已参与 sticky 命中检查，当前请求加入排除后不会再次选择旧绑定账号。
- 账号变为 disabled 后，后续请求会因 `is_schedulable()` 为 false 清理过期 sticky 绑定。
- 不改变 slot/RPM 的现有执行顺序；测试断言每个账号在单请求内最多参与一次 admission，不引入重复 RPM。

## 测试设计

- 扩展现有 Gateway OAuth mock，使 token endpoint 能按 refresh token 返回成功、`invalid_grant`、429 或 5xx。
- 使用两个脱敏 OAuth fixture：首账号优先级更高且 AT 需要刷新，第二账号持有有效 AT。
- 断言请求成功、首账号 disabled、第二账号 active、OAuth refresh 调用次数和上游 Authorization 序列符合预期。
- 增加 sticky 绑定与 `count_tokens` 变体。
- 增加全永久失败变体，断言通用 503 和每账号一次探测。
- AccountService/OAuth 单测直接覆盖错误类别、永久错误不 fallback、临时错误 fallback。

## 兼容性与回滚

- 不涉及 schema、setting、API DTO 或前端构建。
- 新错误类别保持 HTTP 503，不改变外部成功响应协议。
- 回滚只需恢复上一版本镜像；被新版正确停用的账号不会被旧版自动重新启用，需要管理员完成重授权后手动恢复。
- 生产验证只观察脱敏日志、账号状态和自然请求切号，不撤销真实 RT 做故障注入。
