# 账号创建时选择时区设计

## Scope

本任务只修改 `vibecoding-bench` 主项目，不修改 `cc2api` 子模块。改动范围覆盖：

- `orchestrator/main.py`：账号 schema、DTO、校验、登录会话、账号写入 / 恢复、worker 环境变量。
- `webui/index.html`：账号登录配置表单新增时区下拉框。
- `webui/app.js`：表单初始化、payload、账号列表展示。

## Data Model

在 `accounts` 表新增 nullable 字段：

```sql
timezone TEXT
```

含义：

- `NULL` 或空字符串：自动模式，继续使用 `derive_fingerprint(account_name)["tz"]`。
- 允许列表内 IANA 时区名：显式时区，登录 / 任务 worker 都使用该值。

`init_db()` 需要用 `_ensure_column(conn, "accounts", "timezone", "TEXT")` 幂等补列，保持旧 DB 兼容。

## Allowed Values

允许列表复用现有 `_TZ_POOL`，不加入 `Asia/Shanghai`：

```python
[
    "Asia/Tokyo", "Asia/Singapore", "Asia/Seoul",
    "Australia/Sydney", "Europe/London", "Europe/Berlin", "Europe/Paris",
    "America/Los_Angeles", "America/New_York", "America/Chicago",
]
```

新增 helper：

- `_normalize_account_timezone(value)`：`None` / 空字符串返回 `None`；允许列表内返回原值；其他值抛 `ValueError`。
- `_effective_account_timezone(account_or_name, explicit_timezone=None)`：显式值存在时返回显式值，否则返回 `derive_fingerprint(name)["tz"]`。

## API Contract

### AccountIn

新增字段：

```python
timezone: Optional[str] = None
```

用于旧的 `/api/accounts` 手工创建已有 profile 场景。

### LoginStartIn

新增字段：

```python
timezone: Optional[str] = None
```

`/api/accounts/login/start` 在启动登录容器前校验时区，并把显式时区传入 `LoginManager.start()`。

`/api/accounts/login/{sid}/commit` 再次校验 body 时区，并写入 / 更新 `accounts.timezone`。commit 使用前端保存的 step 1 body，因此 start 与 commit 正常一致；如果 body 被篡改，以 commit body 为最终 DB 值。

### GET /api/accounts

每个账号返回：

```json
{
  "timezone": "Europe/Berlin",
  "effective_timezone": "Europe/Berlin",
  "timezone_mode": "manual"
}
```

自动模式示例：

```json
{
  "timezone": null,
  "effective_timezone": "Australia/Sydney",
  "timezone_mode": "auto"
}
```

## Worker Environment

`Runner.start_run()` 当前从 `derive_fingerprint(acc_name)` 得到 `fp["tz"]`。改为：

```python
tz = _effective_account_timezone(account)
```

并把 `worker_env["TZ"] = tz`。其他指纹字段仍来自 `derive_fingerprint()`，不改变 `LANG` / `LC_ALL`、hostname、MAC、machine-id、mem。

`LoginManager.start()` 同理：先派生完整 `fp`，再用显式时区覆盖 worker `TZ`。如果登录时未选择时区，使用账号名派生时区。

## Frontend

账号配置表单新增：

```html
<select name="timezone">
  <option value="">auto (...)</option>
  ...
</select>
```

要求：

- 新建账号默认自动模式。
- 重新登录已有账号时，回显 `account.timezone || ""`。
- payload 中提交 `timezone`；自动模式提交空字符串或 `null` 均可，后端归一化为 `None`。
- 账号列表增加有效时区展示，例如 `Europe/Berlin · manual` 或 `Australia/Sydney · auto`。

## Compatibility

- 旧 DB 通过 `_ensure_column` 补列；旧账号 `timezone` 为空，因此行为完全回退到派生时区。
- 软删除恢复和同名重登都必须写入当前表单时区，避免恢复旧账号时 timezone 漏更新。
- 旧客户端不传 `timezone` 时仍正常工作。

## Validation

后端：

- `_normalize_account_timezone(None / "" / "Europe/Berlin")` 通过。
- `_normalize_account_timezone("Asia/Shanghai")` 和任意字符串返回 400。
- `GET /api/accounts` 对自动账号返回派生 `effective_timezone`。

前端：

- 打开账号弹窗能看到自动模式 + 10 个时区。
- 重新登录账号能回显 `timezone`。
- 列表展示 `effective_timezone` 和模式。

运行级验证：

- 可用开发方式或手工 `docker exec bench-worker-<id> sh -c 'echo $TZ'` 验证显式时区生效。
