# 技术设计：Claude Fast Mode 账号级控制

## 设计目标

在不引入通用 beta 规则引擎的前提下，为每个 Anthropic 账号增加 `allow_fast_mode` 布尔开关。默认关闭时，所有会合并客户端 `anthropic-beta` 的请求路径都精确移除 `fast-mode-2026-02-01`；开启时保留客户端原始 token。系统永远不主动注入 Fast Mode。

## 数据模型与持久化

- 在 `Account` 增加 `allow_fast_mode: bool`，使用 `#[serde(default)]`，缺失时为 `false`。
- SQLite/PostgreSQL 的 `accounts` 建表语句增加 `allow_fast_mode` 整数字段，默认 `0`。
- `migrate` 增加幂等 `ALTER TABLE accounts ADD COLUMN allow_fast_mode INTEGER NOT NULL DEFAULT 0`，旧账号迁移后默认禁止 Fast Mode。
- `AccountStore` 的查询投影、行映射、创建和更新 SQL 全部同步该字段；数据库整数与 Rust `bool` 在 Store 边界转换。
- 所有测试和内部构造的 `Account` 字面量显式补充 `allow_fast_mode: false`，避免隐式行为漂移。

## 管理 API 与前端

- `CreateAccountRequest` 增加 `allow_fast_mode: Option<bool>`，创建账号时 `unwrap_or(false)`。
- `update_account` 仅在请求 JSON 明确包含布尔值时更新字段。
- 账号列表和详情继续直接序列化 `Account`，自然返回该字段。
- `web/src/api.ts` 的 `Account` 类型增加 `allow_fast_mode: boolean`。
- `Accounts.vue` 的新建、编辑、保存 payload 增加字段，并使用现有 toggle/checkbox 交互模式展示“允许客户端 Fast Mode”；默认关闭，辅助文案说明开启后会透传 `fast-mode-2026-02-01`，可能增加计费与限流风险。

## vibecoding-bench 账号同步

- `orchestrator/main.py::sync_account_to_cc2api` 在未匹配到既有账号、需要调用 `Cc2ApiClient.create_account` 时，创建 payload 显式加入 `"allow_fast_mode": False`。
- 显式发送默认值是 bench 集成契约，避免未来 cc2api 服务端默认值变化后，bench 新建账号意外允许 Fast Mode。
- 匹配既有账号或账号已经绑定时，bench 不新增 cc2api 账号更新调用；现有流程只做身份校验、绑定检查和 OAuth 凭据 resolve，因此管理员在 cc2api 中设置的 `allow_fast_mode` 保持不变。
- bench 本地 `accounts` 表不增加对应列，避免形成双写配置和所有权冲突；Fast Mode 配置由 cc2api 账号唯一持有。
- `orchestrator/test_main.py` 增加首次创建同步用例，断言 payload、绑定结果和凭据同步；既有账号重复同步用例继续证明不会重新创建或覆盖配置。

## 请求处理

### `/v1/messages`

在 `Rewriter::rewrite_headers` 合并客户端 beta 之前，对客户端已有 `anthropic-beta` 做账号策略过滤：

1. 保留现有 `context-1m-2025-08-07` 白名单判断。
2. 当 `account.allow_fast_mode == false` 时，精确删除 `fast-mode-2026-02-01`。
3. 将过滤后的客户端 beta 与版本画像的 required beta 合并。
4. 继续执行现有 `context-1m` 顺序整理和最终 header 写入。

实现应复用或轻量扩展现有 token 过滤函数，按逗号分隔后精确比较；不得使用字符串子串替换。版本画像本身不加入 Fast Mode token。

### `/v1/messages/count_tokens`

`apply_count_tokens_beta_header` 使用相同账号策略过滤客户端 beta，然后再合并 `COUNT_TOKENS_BETA_TOKENS` 并确保 `token-counting-2024-11-01` 存在。默认关闭和显式放行语义必须与主消息路径一致。

### 特殊精确画像

`requires_exact_beta_profile` 为真的路径本就不合并客户端 beta，因此保持现有精确画像，不因 `allow_fast_mode` 主动增删 required beta。事件日志、bootstrap、MCP 等非消息路径不扩大本次功能范围。

## 兼容性与风险

- 新旧账号默认值均为 `false`，属于有意的安全默认：升级后客户端无法再自行打开 Fast Mode。
- 通过 bench 创建的新账号会同时受到 bench 显式 payload 与 cc2api 服务端默认值两层保护。
- 管理员设置 `true` 后只允许透传客户端已有 token，不会自动开启 Fast Mode。
- 过滤发生在最终上游 header 生成之前；不修改请求体、默认版本画像、CCH 算法或 `cc_version` 算法。
- Store SQL 占位符较多，新增字段时必须同步列顺序、bind 顺序和 `WHERE id` 参数编号，重点用创建/更新往返测试防止错位。
- `cc2api` 同时支持 SQLite 和 PostgreSQL，建表与升级路径必须同步。

## 回滚

- 代码回滚后数据库保留未使用的 `allow_fast_mode` 列不会影响旧版本运行。
- 如需运营侧临时恢复旧行为，可在回滚前将目标账号 `allow_fast_mode` 设置为 `true`；本任务不提供全局批量开关。
