# 账号创建时选择时区实施计划

## Checklist

1. 后端 schema 与校验
   - 在 `accounts` 表 `_SCHEMA` 增加 `timezone TEXT`。
   - 在 `init_db()` 加 `_ensure_column(conn, "accounts", "timezone", "TEXT")`。
   - 增加时区允许列表 helper，复用 `_TZ_POOL`，拒绝 `Asia/Shanghai` 和其他任意值。

2. 后端 API 与 DB 写入
   - `AccountIn` / `LoginStartIn` 增加 `timezone` 字段。
   - `/api/accounts` 创建、软删除恢复、同名恢复路径写入 timezone。
   - `/api/accounts/login/start` 校验 timezone 并传入登录会话。
   - `/api/accounts/login/{sid}/commit` 写入 / 更新 timezone。
   - `/api/accounts` 列表返回 `timezone`、`effective_timezone`、`timezone_mode`。

3. Worker 环境
   - `Runner.start_run()` 使用账号显式时区覆盖 `worker_env["TZ"]`。
   - `LoginManager.start()` 使用登录请求显式时区覆盖登录 worker `TZ`。
   - 保持 `LANG` / `LC_ALL` 等其他派生字段不变。

4. WebUI
   - `webui/index.html` 账号配置表单新增时区下拉框。
   - `webui/app.js` 增加时区选项常量 / 渲染或静态读取逻辑。
   - 新建账号默认自动模式；重登回显现有 `account.timezone`。
   - start/commit payload 带 `timezone`。
   - 账号列表展示有效时区和模式。

5. 验证
   - 运行后端 Python 语法检查：`python3 -m py_compile orchestrator/main.py`。
   - 静态检查前端资源可解析：至少用 `node --check webui/app.js`。
   - 可选本地接口验证：启动服务后测试非法 timezone 返回 400。
   - 人工或远程验证 worker `echo $TZ`。

## Risk Points

- 登录流程 start 和 commit 都使用 `LoginStartIn`，必须保证两处都携带并校验 timezone。
- 同名账号重新登录路径当前是 `INSERT` 失败后 `UPDATE`，需要同步更新 timezone。
- 软删除恢复走独立 helper `_restore_deleted_account()`，需要把 timezone 传进去。
- 账号列表展示必须使用 `escapeHTML`，防止未来字段变化带来的 XSS 风险。

## Rollback

- 代码回滚即可恢复派生时区行为。
- DB 多出的 nullable `accounts.timezone` 列可保留，不影响旧代码读取。
