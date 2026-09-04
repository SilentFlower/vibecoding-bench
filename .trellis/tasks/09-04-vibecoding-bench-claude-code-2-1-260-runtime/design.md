# 技术设计

## 默认版本升级

沿用现有版本优先级，只把默认值从 2.1.257 改为 2.1.260：

```text
WebUI app_settings.claude_code_version
  -> 未配置时使用 orchestrator 环境 CLAUDE_CODE_VERSION
  -> 环境未配置时使用代码 / Compose 默认 2.1.260
```

worker entrypoint 继续核对 `claude --version`，不一致时安装精确 npm 版本。

## 数据模型

`runs` 新增：

```sql
claude_code_version TEXT
```

该字段记录 run 创建时已经规范化的实际目标版本。字段允许 NULL 仅为兼容历史数据库，
新创建的 run 必须写入非空值。

## 创建与执行数据流

所有 run 创建入口在持有数据库事务前或事务内解析一次有效版本，并与 run 行同时写入：

```text
普通 task run ─┐
批量 run       ├─> resolve effective version -> INSERT runs snapshot
养号 run       ┤                                  -> scheduler task payload
抓包 run       ┘                                  -> Runner.start_run(snapshot)
```

`Runner.start_run()` 使用 `task["claude_code_version"]`。为了兼容旧测试或内部调用，
字段缺失时允许回退 `effective_claude_code_version()`，但生产创建入口必须全部显式传递。

## 继续对话数据流

```text
continue API -> SELECT runs.*
  -> snapshot 非空：规范化后直接使用
  -> snapshot 为空：解析当前有效版本并补写 runs
  -> Runner.start_continue(..., snapshot)
```

补写发生在启动 worker 前，确保即使第一次历史 continue 启动失败，下一次也不会因全局
设置再次变化而选到另一个版本。

## API

- `GET /api/runs` 和 `GET /api/runs/{rid}` 已返回 `SELECT *`，新增列会自然暴露。
- `POST /api/captures/run` 响应增加 `claude_code_version`。
- `GET /api/runs/{rid}/capture` 增加 `claude_code_version`，方便抓包证据核验。
- continue start 响应不需要重复版本；前端可从 run 详情读取，后端测试直接断言容器环境。

## 测试

- SQLite 新库和旧库补列。
- 四类持久化 run 创建入口的非空快照。
- run 创建后修改全局设置，启动仍使用创建快照。
- capture 2.1.260 -> 全局改 2.1.257 -> continue 仍为 2.1.260。
- 历史 NULL run 首次 continue 回退并补写。
- 同一 task 新建第二个 run 使用新的全局版本。
- 默认值、entrypoint、两份 Compose 和所有 worker 创建路径同步 2.1.260。

## 发布与回滚

- 发布前使用 SQLite `.backup` 保存数据库，并记录 `app_settings` 页面覆盖。
- 升级三镜像后 force recreate orchestrator；新 schema 由 `init_db()` 幂等补齐。
- 回滚代码时新增 SQLite 列可保留，旧代码会忽略；回滚版本时同时恢复页面覆盖和 `.env`。
