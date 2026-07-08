# 支持删除账号 - 实施计划

## 实施步骤

1. 数据层
   - 在 `accounts` schema 增加 `deleted_at REAL`。
   - 在 `init_db()` 增加 `accounts.deleted_at` 的幂等补列。
   - 增加或复用一个内部 helper 读取可用账号，条件为 `id=? AND enabled=1 AND deleted_at IS NULL`。

2. 账号删除与恢复
   - 修改 `_account_reference_counts()` 保持统计所有历史引用。
   - 修改 `delete_account()`：已删除或不存在返回 404；无引用物理删除；有引用设置 `enabled=0, deleted_at=?` 并返回成功删除语义。
   - 修改 `list_accounts()` 只列出未软删除账号。
   - 修改 `create_account()` 和 `login_commit()`：同名软删账号恢复原行，清空 `deleted_at` 并更新代理配置。

3. 可用账号入口收口
   - `query_account_quota()` 改为只读取可用账号。
   - `create_task()` 增加账号可用校验。
   - `create_task_batch()` 只接受可用账号。
   - `start_capture_run()` 在现有 `enabled=1` 基础上增加 `deleted_at IS NULL`。
   - `run_task()` 运行旧任务前只接受可用账号。
   - `continue_run_start()` 继续对话前只接受可用账号。
   - `Scheduler._execute_batch()` 读取批次账号时只接受可用账号。

4. OAuth 刷新边界
   - `OAuthRefreshScheduler._tick()` 查询增加 `deleted_at IS NULL`。
   - `Runner.refresh_account_oauth_token()` 对传入账号做 `enabled/deleted_at` 防御，跳过已删除账号。

5. 前端
   - 删除账号成功后不再判断 `result.disabled`，只刷新账号页。
   - 保持现有 `/api/accounts` 数据源，不新增前端本地过滤。

## 验证命令

- `python3 -m py_compile orchestrator/main.py`
- 浏览器手测：删除有关联账号后账号页不显示该账号，且没有“已改为停用”提示。
- 浏览器手测：任务、批次、抓包下拉不显示删除账号。
- 接口手测：删除账号后调用 quota、创建任务、创建批次、抓包、旧任务 run、继续对话都返回错误且不启动 worker。

## 重点检查

- 所有写 DB 的变更必须在 `_db_lock` 内执行。
- 所有新增 SQL 值都使用 `?` 参数，不拼接用户输入。
- 不在 `_db_lock` 持有期间启动 Docker 容器或做文件 IO。
- 前端新字符串如进入 `innerHTML` 必须 `escapeHTML`；本任务预计不新增用户字符串渲染。
