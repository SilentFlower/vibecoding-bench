# cc2api system role guard

## Technical Design

### Scope

实现范围在 `/root/project/cc2api`：

- 后端 settings 默认值、settings 更新校验、settings store 读取 helper。
- 网关 `/v1/messages` 请求体本地校验。
- 管理前端设置页。
- README 中的配置说明。

### Settings Contract

复用现有 `settings` key-value 表，不新增账号字段、不改 `accounts` schema。

新增 key：

```text
allow_system_role_models=claude-opus-4-8
```

含义：

- 逗号分隔的模型 ID 精确匹配列表。
- 请求体顶层 `model` 命中列表时，允许透传 `messages[].role=system`。
- key 不存在时使用默认值 `claude-opus-4-8`。
- 空字符串表示不允许任何模型透传 `messages[].role=system`。

在 `db::migrate` 默认 settings 插入列表中补 `("allow_system_role_models", "claude-opus-4-8")`。

在 `SettingsStore` 增加读取字符串配置的 helper，例如：

```rust
pub async fn get_value(&self, key: &str, default: &str) -> Result<String, AppError>
```

网关侧解析为 `Vec<String>`：

- 按逗号切分。
- trim 后忽略空段。
- 保持配置顺序，用于错误响应。
- 匹配时使用精确模型 ID。

`GatewayService` 持有内存缓存：

- 启动时从 settings 加载 `allow_system_role_models`。
- `/admin/settings` 更新该 key 后主动刷新缓存。
- `/v1/messages` 请求路径只读内存 `Vec<String>`，不每次查询 settings 表。

### API Contract

后台 settings 接口：

- `GET /admin/settings` 返回 `allow_system_role_models`，默认 `"claude-opus-4-8"`。
- `PUT /admin/settings` 支持 `allow_system_role_models: string`。
- 允许空字符串，表示无允许模型。
- 如果列表中包含空白以外的非法字符，返回 HTTP 400；建议允许 `[A-Za-z0-9._:-]`，兼容 Anthropic 模型 ID。

### Gateway Guard

`GatewayService` 构造函数增加 `settings_store: Arc<SettingsStore>` 依赖，由 `main.rs` 注入，并提供刷新缓存方法。

校验放在 `GatewayService::handle_request_inner` 中读取请求体和解析 `body_map` 之后、客户端类型检测/账号选择/自动遥测/队列/改写之前。

原因：

- 该配置是全局配置，不依赖账号选择。
- 提前拦截能避免账号选择、自动遥测、rewrite、token 解析和上游请求副作用。
- 请求体已解析，可以不保存/输出正文，只检查结构。

候选函数：

```rust
fn has_system_role_message(body: &serde_json::Value) -> bool
fn parse_model_list(raw: &str) -> Vec<String>
fn is_model_allowed(model: &str, allowed: &[String]) -> bool
```

逻辑：

- 仅对 `path.starts_with("/v1/messages")` 生效。
- 请求体不是 JSON 或没有数组 `messages` 时不拦截，保持现有透传/错误路径。
- 只检查 `messages` 数组元素中的对象字段 `role == "system"`。
- 若发现 `role=system`，读取顶层 `model`；缺失时按空字符串处理。
- `model` 不在 `allow_system_role_models` 中时拦截。

错误响应建议不要只走现有 `AppError::BadRequest`，而是在网关中构造带额外字段的 400 JSON，保留 `error` 字段以兼容现有客户端：

```json
{
  "error": "messages[].role=system is not allowed for this model",
  "model": "claude-opus-4-7",
  "allowed_system_role_models": ["claude-opus-4-8"]
}
```

### Frontend

在 `Settings.vue`：

- 增加 `allowSystemRoleModels` state，加载 `data.allow_system_role_models ?? "claude-opus-4-8"`。
- 保存 settings 时写入 `allow_system_role_models: allowSystemRoleModels.value.trim()`。
- 增加一个设置区块，使用文本输入配置逗号分隔模型列表。
- 增加预设按钮：
  - `Opus 4.8` → `claude-opus-4-8`
  - `全部关闭` → 空字符串

### Compatibility

- 默认允许 `claude-opus-4-8`，符合当前本地验证结果。
- 管理员可将列表改为空字符串，严格拒绝所有 `messages[].role=system`。
- 未包含 `messages[].role=system` 的请求不受影响。
- 命中允许列表只放行，不新增改写或 header 变化。

### Rollback

- 代码回滚即可恢复旧行为。
- settings 中多余 key 对旧代码无影响，不需要迁移删除。
