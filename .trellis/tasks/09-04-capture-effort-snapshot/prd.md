# 抓包 run 独立选择并快照思考预算

## Goal

让用户可以为单次完整 HTTP 抓包独立选择 Claude Code 思考预算，并把预算作为 run 的可恢复执行身份持久化，保证排队启动和继续历史会话时不会因全局设置变化发生漂移。

## Background

- 当前抓包表单只有账号、题目、超时、模型和 prompt，没有思考预算字段。
- `CaptureRunIn` 不接受预算；`Runner.start_run()` 对抓包固定使用 `.env` 的 `CLAUDE_CODE_EFFORT_LEVEL`，并明确忽略运行页覆盖值。
- `runs` 只保存 Claude Code 版本快照，没有思考预算快照；`Runner.start_continue()` 继续会话时重新读取 `.env`，无法恢复原 run 的预算。
- 允许值已有统一枚举：`max`、`xhigh`、`high`、`medium`、`low`，本任务复用现有校验和设置响应。

## Requirements

- 抓包表单新增独立思考预算下拉框，选项来自现有 `/api/settings/runtime-effort` 响应；默认项显示并使用 `.env` 兜底值，不继承运行页保存的普通/批量 run 覆盖值。
- `CaptureRunIn` 新增可选 `effort_level`。后端必须复用 `_normalize_claude_effort_level()` 校验；空值解析为 `.env` 的 `CLAUDE_CODE_EFFORT_LEVEL`。
- `runs` 新增可空 `claude_effort_level TEXT`，通过现有 `_ensure_column()` 幂等升级旧数据库。
- 普通、批量、养号和抓包 run 都必须在创建时解析一次有效预算，并同时写入数据库与 scheduler task payload：
  - 普通、批量和养号保持现有行为，使用创建时的 `effective_runtime_effort()`。
  - 抓包使用本次显式选择；未选择时使用 `.env` 的 `CLAUDE_CODE_EFFORT_LEVEL`。
- `Runner.start_run()` 必须使用 task payload 中的预算快照，不得在取得账号信号量后重新读取页面设置或 `.env`。
- `POST /api/runs/{rid}/continue/start` 必须在启动继续会话前确保 run 有预算快照；`Runner.start_continue()` 只使用该快照。
- 历史 `claude_effort_level IS NULL` 的 run 首次继续时，在数据库锁内原子补写 `.env` 的 `CLAUDE_CODE_EFFORT_LEVEL`，保持旧版继续会话行为；之后始终复用已补写值。
- 单次抓包选择不得回写运行页全局设置，也不得污染账号 profile 的预算兜底；`PROFILE_CLAUDE_CODE_EFFORT_LEVEL` 继续使用 `.env` 默认值。
- 抓包创建响应、抓包详情和 run 详情必须返回实际预算快照；WebUI run 详情展示该值。
- 非 run 临时 worker（登录、额度查询、OAuth refresh）继续在启动时读取 `.env`，不新增持久化身份。
- 补充后端与静态前端回归测试，覆盖合法/非法输入、默认值、四类 run 创建、排队后设置变化、继续复用和历史 NULL 兼容。

## Acceptance Criteria

- [ ] 抓包页面可选择 `max`、`xhigh`、`high`、`medium`、`low`，默认项清楚展示 `.env` 兜底值。
- [ ] 显式选择预算后，新抓包 run 的数据库快照、scheduler payload、worker 环境和 API 响应一致。
- [ ] 抓包留空时使用 `.env` 默认值，即使运行页另有普通/批量预算覆盖。
- [ ] 普通、批量和养号 run 创建时保存各自当时的有效预算；排队期间修改设置不会改变已创建 run。
- [ ] 初始 run 与继续会话使用同一个预算快照；修改全局设置后继续仍不漂移。
- [ ] 历史 NULL run 首次继续补写一次 `.env` 默认预算，第二次继续不再受环境或页面设置变化影响。
- [ ] 非法预算返回 400，且不会创建 task、run 或 worker。
- [ ] 旧数据库重复执行初始化后只新增一个 `claude_effort_level` 列，现有数据与自定义运行设置不被覆盖。
- [ ] 运行详情和抓包详情可核对实际预算；现有模型覆盖、Claude Code 版本快照和 profile 回写行为不回归。
- [ ] `python3 -m unittest orchestrator.test_main`、`node --check webui/app.js`、`bash -n images/worker/entrypoint.sh` 和 `git diff --check` 通过。

## Out of Scope

- 不修改思考预算枚举或 Claude Code 对各预算等级的协议语义。
- 不修改 cc2api 协议画像、模型策略或账号能力。
- 不处理 `8b6129adc9fa` 的上游无响应与 run 成功判定问题。
- 不在本任务中构建、发布或部署生产镜像。
