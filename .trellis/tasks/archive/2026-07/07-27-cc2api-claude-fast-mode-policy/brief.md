# Brief — 为 cc2api 增加 Claude Fast Mode 可配置控制

## Goal

- 默认阻止下游 Claude Code 客户端通过 `fast-mode-2026-02-01` 开启上游 Fast Mode，同时允许管理员按 cc2api 账号显式放行。

## Scope

- 为 cc2api `Account` 增加账号级布尔字段 `allow_fast_mode`，新账号、旧库迁移和缺失字段均默认 `false`。
- 同步 SQLite/PostgreSQL schema、迁移、AccountStore、账号创建/更新 API、前端 Account 类型和 Accounts 表单。
- 在 `/v1/messages` 与 `/v1/messages/count_tokens` 合并客户端 beta 前精确过滤 Fast Mode token；设置为 `true` 时仅允许透传，不主动注入。
- 保持 `context-1m-2025-08-07` 白名单、默认 Claude Code 版本画像、CCH 和 `cc_version` 现有语义不变。
- `vibecoding-bench` 首次同步创建 cc2api 账号时显式发送 `allow_fast_mode: false`；匹配既有或已绑定账号时不覆盖管理员配置。
- 增加 cc2api 协议、迁移、Store/API、前端构建及 orchestrator 同步回归测试。

## Non-Goals

- 不实现通用的任意 `anthropic-beta` 策略引擎。
- 不主动为任何请求注入 Fast Mode。
- 不修改 Fast Mode 计费、限流或账号调度逻辑。
- 不在 bench 数据库复制保存 `allow_fast_mode`，避免双写配置。
- 不改变 event logging、bootstrap、MCP 等不会合并客户端 beta 的精确画像路径。

## Key Context

- cc2api 当前只显式过滤 `context-1m-2025-08-07`，其余客户端 beta 会通过 `merge_anthropic_beta` 合并到上游。
- 主要实现入口：`cc2api/src/model/account.rs`、`src/store/db.rs`、`src/store/account_store.rs`、`src/handler/router.rs`、`src/service/rewriter.rs`、`src/service/gateway.rs`、`web/src/api.ts`、`web/src/components/Accounts.vue`。
- bench 同步入口：`orchestrator/main.py::sync_account_to_cc2api`；回归测试位于 `orchestrator/test_main.py`。
- token 过滤必须按逗号分隔后的完整 token 精确匹配，并保持其他 token 的相对顺序。
- Store SQL 占位符多，新增列时必须同步列顺序、bind 顺序和 `WHERE id` 参数编号。
- SQLite/PostgreSQL schema 与旧库幂等升级必须同时覆盖；旧账号升级后默认禁止。
- bench 新建 payload 显式禁止 Fast Mode，但既有账号同步只处理身份、绑定和凭据，不能重置 cc2api 管理员配置。

## Acceptance

- 默认账号收到带 `fast-mode-2026-02-01` 的请求时，最终上游 beta 不含该 token，其他 beta 顺序稳定。
- `allow_fast_mode=true` 时保留客户端已有 Fast Mode token，但系统不会自行注入。
- 新账号、旧库迁移账号和 bench 同步新建账号均默认禁止 Fast Mode。
- Account 字段在数据库、Store、创建/更新 API、列表响应和管理 UI 中正确往返。
- 主消息与 count_tokens 路径行为一致，未携带 Fast Mode 的请求不产生无关变化。
- bench 首次创建同步 payload 含 `allow_fast_mode: false`，绑定和凭据镜像成功；既有账号与重复同步不创建或更新配置。
- `cargo fmt --check`、`cargo test`、`cargo test cch`、`cc2api/web npm run build`、`python3 -m unittest orchestrator/test_main.py` 全部通过。

## Next Step

- 用户确认本 brief 后运行 `task.py start`，再通过 `trellis-route(target=implement)` 进入实现。
