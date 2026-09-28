# 抓包 run 思考预算快照设计

## Architecture

预算数据流统一为：

```text
WebUI / 全局设置
  -> API 入口校验并解析有效值
  -> runs.claude_effort_level + scheduler task payload
  -> Runner.start_run() worker environment
  -> POST /runs/{rid}/continue/start
  -> Runner.start_continue() worker environment
  -> run / capture detail 展示
```

预算和 `claude_code_version` 一样属于 run 的可恢复执行身份。全局设置只在创建新 run 时作为输入，排队启动和继续会话不再重新解释全局状态。

## Database Contract

在 `_SCHEMA` 的 `runs` 表增加：

```text
claude_effort_level TEXT NULL
```

`init_db()` 使用 `_ensure_column(conn, "runs", "claude_effort_level", "TEXT")` 兼容旧库。新建 run 必须写非空值；NULL 只代表升级前历史数据。

## Backend Contracts

复用 `_normalize_claude_effort_level()`，新增与版本快照对称的内部函数：

```python
_resolve_run_claude_effort_level(value: Optional[str]) -> str
_ensure_run_claude_effort_level(run: dict) -> str
```

- `_resolve_run_claude_effort_level()` 规范化显式快照；空值只作为旧内部调用兼容，回退 `.env` 常量 `CLAUDE_CODE_EFFORT_LEVEL`。
- `_ensure_run_claude_effort_level()` 在 `_db_lock` 内重新读取数据库。字段为空时用 `.env` 默认值执行一次条件补写，字段已有值时只校验并返回。
- 保存值非法时继续接口返回 400，不启动 worker，也不静默降级。

## Creation Matrix

| 入口 | 创建时预算来源 | 持久化位置 |
| --- | --- | --- |
| 普通 task run | `effective_runtime_effort()` | DB + task payload |
| 批量 run | `effective_runtime_effort()` | DB + task payload |
| 养号 run | `effective_runtime_effort()` | DB + task payload |
| 完整抓包 run | `body.effort_level`，空值回退 `.env` | DB + task payload |

`Runner.start_run()` 统一读取 `task["claude_effort_level"]` 并设置 worker 的 `CLAUDE_CODE_EFFORT_LEVEL`。现有 capture/non-capture 分支只保留抓包、模型等其他差异，不再决定预算。

`PROFILE_CLAUDE_CODE_EFFORT_LEVEL` 保持 `.env` 默认值，避免一次性 run 选择覆盖账号 profile。

## Continue Compatibility

`continue_run_start()` 在 `_ensure_run_claude_code_version(run)` 后调用 `_ensure_run_claude_effort_level(run)`。`Runner.start_continue()` 从 run 字典读取两个快照。

历史 NULL 行无法可靠重建最初运行时的页面覆盖值；旧版继续会话本来固定使用 `.env`，因此首次继续按 `.env` 补写最符合兼容语义。条件更新保证并发首次继续只确定一个稳定值。

## API And UI

`CaptureRunIn` 增加 `effort_level: Optional[str] = None`，抓包创建响应增加 `claude_effort_level`。

抓包表单新增 `<select name="effort_level">`。`bindCaptureForm()` 使用已加载的 `state.runtimeEffort.allowed_efforts` 和 `env_default_effort` 生成选项，不重复维护枚举；提交后只重置抓包字段，不修改运行页设置。

run 详情增加思考预算 stat；抓包详情增加预算字段。现有 API 的 `SELECT *` 自动返回数据库字段，抓包详情显式返回快照以保持契约清楚。

## Compatibility And Rollback

- SQLite 只追加可空列，不重写旧行，回滚旧镜像时额外列会被忽略。
- API 新字段为可选，旧前端请求仍能创建抓包并使用 `.env` 默认值。
- 前端选项来源于已有设置接口，不新增 endpoint。
- 回滚代码后无需删除新列；恢复旧 compose/WebUI 即可恢复原行为。

## Risks

- 任一 run 创建入口漏写快照，会在 worker 启动时重新回退全局值；测试必须遍历全部四类入口。
- 继续会话只改 worker 环境但不补写数据库，会在后续继续再次漂移；测试必须验证两次继续之间修改全局值。
- 将一次性抓包预算写回 profile 会影响后续其他 run；测试必须锁定 `PROFILE_CLAUDE_CODE_EFFORT_LEVEL` 仍为 `.env` 默认值。
