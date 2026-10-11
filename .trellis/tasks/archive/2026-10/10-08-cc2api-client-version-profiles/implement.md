# 实施计划

## 1. 开发前上下文

- [x] 完成三件套收敛，生成并完整展示 brief，按 `trellis-task-brief` 评审后启动任务。
- [x] 进入 `trellis-route(target=implement)`，遵守所选执行方式；当前未派发子代理。
- [x] 按 `trellis-before-dev` 读取 backend/protocol/frontend guideline 和任务 context。
- [x] 核对类型与公开方法定义；遵守原缩进、显式 imports、中文接口文档和复杂逻辑原因注释。

## 2. 选择方式与配置

- [x] version_profile 增加选择模式解析、仅从原始 UA 识别版本、默认回退及请求级副本 helper。
- [x] settings_store、db、router、Gateway 装配/reload 与 Settings.vue 同步默认 key、幂等迁移、校验、热刷新及回退控件。
- [x] 自动匹配仅覆盖 260/280，保留访问策略和显式配置，不猜测新版本。

## 3. 请求链路

- [x] Gateway 冻结选择结果，改写使用最终账号的请求级副本，覆盖 messages、count_tokens、telemetry、bootstrap 与重试。
- [x] 原账号继续负责调度、sticky、RPM、并发、token 和上游 session 池。
- [x] 核对 header/body/CCH、billing suffix、模型与辅助请求规则统一读取有效画像；未知字段/SSE 保真。

## 4. 遥测与缓存

- [x] 遥测复合 key、固定后台画像、profile 运行 ID、异步结果归属和账号级聚合。
- [x] Stateful、hello singleflight/结果与非流探针 key 增加画像维度，保留真实 session 和账号总容量。

## 5. 验证

- [x] Resolver 覆盖 UA 大小写、精确版本边界、缺失/非法/未支持版本、默认 280 和旧模式；验证 GrowthBook/event_logging 请求体即使声明 260，也不能替代缺失 UA 或覆盖 UA 的选择。
- [x] 设置覆盖默认插入、非法值、热刷新、显式值保留、SQLite/Postgres 兼容及 UI 字符串契约。
- [x] 同账号交错/并发两版请求，断言模型 beta/CCH、持久账号不变及 401/签名/换号重试画像一致。
- [x] 验证 bootstrap、hello、原生与后台遥测的 UA/payload，同秒 ID、延迟结果、TTL 和管理聚合。
- [x] 验证同账号同真实 session 两版本缓存隔离、延迟提交和上游 session 池总容量。
- [x] 运行 `cd cc2api && cargo fmt --check` 与 `git diff --check`：通过。
- [x] 运行完整 `cd cc2api && cargo test`：609 项通过；CCH 专项单独执行并记录。
- [x] 运行 `cd cc2api/web && npm run build`：vue-tsc 与 Vite 通过。
- [x] 进入 `trellis-route(target=check)` / Check-All，核对实际 diff、异步上下文及旧版本回归。

## 6. 规范与交付

- [x] 按 `trellis-update-spec` 更新画像选择、遥测与缓存契约，保留用户现有 official-protocol-capture.md 改动。
- [x] 汇总实际改动、验证和真实上游验证限制；不部署或发布。
- [x] 用户确认精确 Git 计划后，提交并推送 cc2api 实现，以及 vibecoding-bench 规范与子模块引用。
- [x] 将已确认的 7 个任务产物纳入独立任务记录交付，由 `task_progress.py write --complete` 原子写入完成态与 Close。

## 回退点

- 设置 `claude_code_profile_selection_mode=account` 恢复原画像选择方式。
- 开发回退只撤销本任务局部改动，保留父仓已有用户变更和子模块提交。
- 本地验证使用脱敏 fixture、Memory/SQLite 与 mock HTTP，不写生产账号或启动真实推理。

## 本地验证记录

- 完整 `cargo test`：最终源码回归 609 项通过（552 单元 + 57 集成），退出码 0。
- `cargo test cch`：24 项通过，退出码 0；版本匹配、双版 hash fixture 与重试 CCH 也由完整回归覆盖。
- `cargo fmt --check`、父子仓 `git diff --check`：通过。
- Check-All：requested=auto，effective=full，inline；三件套实现、实现假设、完整性与规范均通过，无剩余 CHK/FBK。
- 验证覆盖：精确 UA/默认/账号模式、配置校验和热刷新、同账号交错与并发、401 热刷新期间的固定画像、签名重试、换号、count_tokens、bootstrap、hello 双版去重、遥测续期/延迟结果/TTL/聚合、stateful 反序延迟提交及非流式缓存 key。
- PostgreSQL：人工核对既有 `ON CONFLICT (key) DO NOTHING` 补齐语句；未连接 PostgreSQL 实例执行迁移。
- 前端 `npm run build`：通过，退出码 0。
- Update-Spec：`written`；更新既有 protocol、protocol index、service architecture 和 settings/database 规范，补齐 UA 唯一来源、默认回退、原子热刷新、遥测复合 key 与缓存隔离契约。
- 规范验证：源码签名及 10 个关键通过测试反向核对、6 节结构和 10 个本地链接检查、`git diff --check -- .trellis/spec` 通过；规范阶段外源码/任务/HEAD/index 和用户抓包文档与基线一致。
- 仅使用本地 SQLite、脱敏 fixture 和 mock HTTP，未进行真实上游推理或部署。

## 当前进度

- 实现、Check-All、规范同步与双仓业务提交/推送完成。
- 用户已确认 `trellis-push` 双仓精确计划；按同一次确认同步完成态、Close 和独立任务记录。
- 用户已有抓包文档未修改或提交；未发布或部署。
