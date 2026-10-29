# cc2api 每账号 5h/7d 控制线实施计划

## 当前阶段

- 用户已确认完整 Brief，任务已启动并由 `trellis-route(target=implement)` 解析为 inline；已加载 `trellis-before-dev` 相关规范。
- 已完成账号字段、双库迁移、消息选号和账号管理页；最终 Rust、PostgreSQL、bench 回归与浏览器验证均通过，命令证据见 `research/validation.md`。
- 用户补充要求核对 bench 创建 cc2api 账号功能，已纳入既有兼容验收：保持创建默认、绑定/凭据/进程指标链路，并执行旧 payload 与 bench 既有回归。
- 收尾时补齐状态与控制线同时提交的快捷分支，使用独立字段写入保留最新凭据/状态；最终双库回归包含旧快照更新的保护断言。

## 实施顺序

1. 通过 `trellis-task-brief` 同步并展示最终 Brief，获得首次开工确认；随后 `task.py start`，通过 `trellis-route(target=implement)` 决定执行方式，读取 `trellis-before-dev` 和适用规范。
2. 核对 `Account`、创建 DTO、动态更新接口、全部结构体字面量与账号 SQL；同步两个字段、服务校验、SQLite/PG schema 和幂等迁移。
3. 补齐存储与 API 回归，重点验证非零值创建/局部更新/读取、非法输入无部分写入、重复迁移保留值及旧 payload 兼容。
4. 在消息选号上下文中启用账号限制，统一 sticky 与普通候选过滤；保持 API Token 范围、Fable、RPM、上游 429 与 sticky 提交契约。
5. 增加有实际行为断言的调度回归：两个窗口、边界、关闭、未知/过期、OAuth/SetupToken、无替代账号与混合限制；验证非消息入口不套用新规则。
6. 更新 `web/src/api.ts`、`Accounts.vue` 所有表单入口与请求 payload，增加两个输入及列表上限展示；运行页面交互验证。
7. 更新 README 与项目可执行规范，运行完整必需检查并记录结果；进入 `trellis-route(target=check)` 质量检查，修复发现的问题。

## 预计修改文件

- `cc2api/src/model/account.rs`
- `cc2api/src/store/account_store.rs`、`cc2api/src/store/db.rs`
- `cc2api/src/handler/router.rs`
- `cc2api/src/service/account.rs`、`cc2api/src/service/gateway.rs`
- `cc2api/web/src/api.ts`、`cc2api/web/src/components/Accounts.vue`
- `cc2api/tests/account_scheduler_test.rs`、`account_store_timestamp_test.rs`、`gateway_429_retry_test.rs` 与已有模块内测试
- 其他包含 `Account { ... }` 的既有模块：只补默认字段及必要 fixture 同步，避免顺带重构。
- `cc2api/README.md` 与 `.trellis/spec/cc2api/` 相关账号字段/调度契约。

## 验证命令与证据

- 开发时优先执行新建的账号控制线、迁移与管理 API 定向测试，失败后按原因修复；最终只跑一次完整必要验证，除非后续有新修改。
- `cd cc2api && cargo fmt --check`
- `cd cc2api && cargo test`
- `cd cc2api/web && npm run build`
- 针对独立临时 PostgreSQL 数据库运行新增账号字段/迁移契约测试，不连接或修改生产数据库。
- 本地页面验证输入 80/60 保存、重新打开回显、设 0 关闭、输入小数/越界拒绝以及列表显示。
- 主仓和子模块分别 `git diff --check`，记录验证命令与结果到任务 research。

## 风险控制

- 不覆盖本轮开始前主仓已有的技能/Flower 修改；子模块初始工作树干净。
- INSERT/UPDATE 占位符与 bind 顺序严格对应；SQLite RETURNING 消费到完成，不能退回首行读取。
- 所有账号构造 fixture 补 0，避免将默认限制错误地应用到无关协议/遥测测试。
- 账号配置修改遵守现有运行时门禁；不因控制线功能停止活动发送器或改变 OAuth 所有权。
- 不自动部署、不提交/推送。限制启用由管理员在账号页显式保存；回滚将两个字段置 0。
