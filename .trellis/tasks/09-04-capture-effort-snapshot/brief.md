# Brief — 抓包 run 独立选择并快照思考预算

## Goal

- 为单次完整 HTTP 抓包提供独立思考预算选择，并把预算固化为 run 的可恢复执行身份，保证排队启动和继续会话不会随全局设置漂移。

## Scope

- 抓包表单增加 `默认、max、xhigh、high、medium、low` 下拉选择；默认项使用并展示 `.env` 兜底值，不继承运行页覆盖值。
- `CaptureRunIn` 接受可选 `effort_level`，复用现有预算枚举校验。
- `runs` 增加可空 `claude_effort_level`，旧数据库通过 `_ensure_column()` 幂等升级。
- 普通、批量、养号和抓包 run 在创建时把有效预算同时写入数据库和 scheduler task payload。
- `Runner.start_run()` 和 `Runner.start_continue()` 只使用 run 预算快照；继续接口负责校验或补写历史 NULL 快照。
- 抓包创建响应、run 详情和抓包详情返回并展示实际预算。
- 补齐数据库、API、调度、worker、继续会话和静态 WebUI 回归测试。

## Non-Goals

- 不修改预算枚举及 Claude Code 对预算等级的协议语义。
- 不修改 cc2api 协议画像、模型策略或账号能力。
- 不处理 `8b6129adc9fa` 的上游无响应与 run 成功判定问题。
- 不在本任务中构建、发布或部署生产镜像。

## Key Decisions

- 预算与 Claude Code 版本一样属于 run 执行身份；全局设置只在创建新 run 时参与解析。
- 抓包显式选择优先，留空回退 `.env` 的 `CLAUDE_CODE_EFFORT_LEVEL`，不会读取普通/批量 run 的页面覆盖值。
- 普通、批量和养号保持现有预算来源，在创建时固化 `effective_runtime_effort()`。
- 历史 NULL run 首次继续按旧行为使用 `.env` 默认预算，并在数据库锁内条件补写一次。
- 一次性抓包预算不回写账号 profile；`PROFILE_CLAUDE_CODE_EFFORT_LEVEL` 与非 run 临时 worker 保持现有 `.env` 行为。
- 前端复用 `/api/settings/runtime-effort` 的枚举和环境默认值，不维护第二套预算常量。

## Key Context

- 后端与 SQLite：`orchestrator/main.py` 的 `_SCHEMA`、`init_db()`、run 创建入口、`Runner.start_run()`、`Runner.start_continue()` 和 continue API。
- 测试：`orchestrator/test_main.py` 已有 Claude Code 版本快照测试，可扩展为预算快照对称覆盖。
- 前端：`webui/index.html` 的抓包表单和 `webui/app.js` 的 `bindCaptureForm()`、run/capture 详情渲染。
- 允许预算固定为 `max`、`xhigh`、`high`、`medium`、`low`。

## Risks / Deferred

- 四类 run 创建入口任一漏写快照都会在排队或继续时重新引入漂移，必须由矩阵测试覆盖。
- 历史 run 无法重建创建时页面覆盖值，只能按旧版继续行为补写 `.env` 默认值。
- 生产发布与真实抓包验证由后续部署动作处理，本任务只完成代码与本地质量门禁。

## Acceptance

- 抓包可独立选择预算，默认值和显式值都能正确落库、进入 scheduler payload 和 worker 环境。
- 抓包默认预算与运行页覆盖隔离；普通、批量和养号仍按现有来源创建快照。
- 修改全局设置后，已排队 run 和继续会话仍使用原预算；历史 NULL run 只补写一次。
- API 与 WebUI 可核对实际预算，非法输入返回 400 且不创建资源。
- 旧数据库升级幂等，模型覆盖、版本快照、profile 回写和临时 worker 行为不回归。
- `python3 -m unittest orchestrator.test_main`、`node --check webui/app.js`、`bash -n images/worker/entrypoint.sh`、`git diff --check` 和 Check-All 通过。

## Next Step

- Check-All 已通过；用户确认继续后进入 Phase 3.3，更新 run 思考预算快照相关项目规范。
