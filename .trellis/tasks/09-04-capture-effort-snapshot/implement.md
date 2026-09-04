# Implementation Plan

## 1. 数据库与预算快照函数

- [x] 在 `_SCHEMA` 和 `init_db()` 中加入 `runs.claude_effort_level`。
- [x] 新增预算快照解析与历史 NULL 原子补写函数，复用现有预算枚举校验。
- [x] 增加旧数据库重复升级、非法快照和历史补写测试。

## 2. 全部 run 创建入口

- [x] 普通 task run 创建时保存并提交 `effective_runtime_effort()`。
- [x] 批量 run 创建时保存并提交创建时预算。
- [x] 养号 run 创建时保存并提交创建时预算。
- [x] 抓包 DTO 接受独立预算，空值回退 `.env`，并在响应中返回实际快照。
- [x] 扩展现有四类 run 快照测试，验证 DB 与 scheduler payload 一致。

## 3. Worker 与继续会话

- [x] `Runner.start_run()` 统一从 task payload 设置 `CLAUDE_CODE_EFFORT_LEVEL`。
- [x] 继续接口在启动前确保预算快照，`Runner.start_continue()` 只使用 run 快照。
- [x] 保持 `PROFILE_CLAUDE_CODE_EFFORT_LEVEL` 与临时 worker 的现有 `.env` 行为。
- [x] 增加排队后设置变化、继续后设置变化和历史 NULL 两次继续回归。

## 4. WebUI 与详情契约

- [x] 抓包表单增加预算下拉框，并复用运行时设置接口返回的枚举和 `.env` 默认值。
- [x] 抓包请求提交 `effort_level`，提交成功后恢复默认项。
- [x] run 详情和抓包详情展示 `claude_effort_level`。
- [x] 增加静态 HTML/JS 契约测试或现有等价断言。

## 5. 验证与检查

- [x] 运行 `python3 -m unittest orchestrator.test_main`。
- [x] 运行 `node --check webui/app.js`。
- [x] 运行 `bash -n images/worker/entrypoint.sh`。
- [x] 运行 `git diff --check`。
- [x] 执行 Check-All，核对数据库、API、scheduler、worker、continue 和 UI 的完整数据流。

## Rollback Points

- 业务代码可整体回退；SQLite 新增列保持存在但由旧代码忽略。
- 不在本任务修改生产 `.env`、数据库值或运行中容器。
- 若继续兼容测试失败，不允许只保留抓包表单字段而跳过 run 快照。
