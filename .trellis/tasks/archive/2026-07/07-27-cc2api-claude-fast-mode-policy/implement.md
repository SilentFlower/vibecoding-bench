# 实施计划：Claude Fast Mode 账号级控制

## 1. 账号字段与数据库

- 在 `src/model/account.rs` 增加带中文 Doc comment 的 `allow_fast_mode: bool`，默认 `false`。
- 同步所有 `Account` 字面量和测试 fixture。
- 在 `src/store/db.rs` 的 SQLite/PostgreSQL schema 与幂等迁移中增加 `allow_fast_mode INTEGER NOT NULL DEFAULT 0`。
- 在 `src/store/account_store.rs` 同步查询投影、行映射、创建 SQL、更新 SQL及 bind 顺序。
- 补充迁移默认值和账号 create/update/list round-trip 测试。

## 2. 管理 API 与前端

- 在 `src/handler/router.rs` 的创建 DTO、创建默认值和更新解析中加入 `allow_fast_mode`。
- 在 `web/src/api.ts` 同步 `Account.allow_fast_mode` 类型。
- 在 `web/src/components/Accounts.vue` 同步表单默认值、编辑回填、创建/更新 payload，并加入账号级开关和风险说明。

## 3. 协议过滤

- 在 `src/service/rewriter.rs` 定义 Fast Mode beta 常量，并复用精确 token 过滤逻辑。
- `/v1/messages` 合并 beta 前：保留现有 1M 过滤，再按 `allow_fast_mode` 决定是否剥离 Fast Mode。
- 在 `src/service/gateway.rs::apply_count_tokens_beta_header` 应用同一策略。
- 不修改 `src/service/version_profile.rs` 的 required beta 列表，不主动注入 Fast Mode。

## 4. 测试

- Rewriter：默认过滤、显式允许、精确匹配、未携带时无关 token 不变、与 context-1m 组合时顺序稳定。
- Count tokens：默认过滤与显式允许各一例，并确认 token-counting beta 保留。
- Store/API：新旧账号默认 `false`，创建和更新 `true/false` 可往返。
- 前端：运行 TypeScript/Vite 构建验证类型和表单绑定。

## 5. vibecoding-bench 同步兼容

- 在 `orchestrator/main.py::sync_account_to_cc2api` 的首次创建 payload 中显式加入 `allow_fast_mode: False`。
- 不给既有账号同步路径增加配置更新调用，保持 cc2api 端管理员配置为权威值。
- 在 `orchestrator/test_main.py` 增加“无匹配账号时创建并绑定”的回归测试，断言 `create_account` payload、`cc2api_account_id` 和凭据镜像正确。
- 保留并运行既有账号重复同步测试，确认不会重新创建账号或破坏绑定/养号状态。

## 6. 验证命令

```bash
cd cc2api
cargo fmt --check
cargo test
cargo test cch
cd web
npm run build
cd ../..
python3 -m unittest orchestrator/test_main.py
```

## 风险检查

- 核对 `AccountStore` SQL 列、占位符和 bind 数量完全一致。
- 核对 SQLite/PostgreSQL schema 均包含新列。
- 核对消息与 count_tokens 两条链路行为一致。
- 核对精确 beta 画像和默认版本画像未加入 Fast Mode。
- 核对没有把管理员“允许透传”误实现成“主动注入”。
- 核对 bench 只在新建 cc2api 账号时显式禁止 Fast Mode，不覆盖既有账号配置。
