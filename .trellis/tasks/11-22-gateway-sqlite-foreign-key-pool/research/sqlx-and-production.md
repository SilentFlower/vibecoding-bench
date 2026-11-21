# SQLite 外键与生产孤儿行核验

## 本地源码及实测

- `2995c4e6:services/gateway/src/store/db.rs:11` 的初始化在池上执行一次 `PRAGMA foreign_keys=ON`。该语句的作用范围是提供本次查询的那条连接。
- `services/gateway/Cargo.lock:2093` 锁定 SQLx 0.7.4。该版本的 `sqlx-sqlite/src/any.rs:186` 由 Any 配置构造 SQLite 选项。URL 解析从 `SqliteConnectOptions::default()` 开始，`src/options/mod.rs:173` 默认设置 `foreign_keys=ON`，`src/options/connect.rs:31–35` 在每次建连时执行配置中的 PRAGMA。
- 使用 Gateway 当前编译产物和同一套 SQLx 依赖进行本地探测。裸 `AnyPool::connect` 与当前 `init_db` 各同时持有 5 条文件数据库连接。每条的 `PRAGMA foreign_keys` 都为 1。关闭一条并重新建连后也为 1。两组 `AnyConnection::backend_name()` 都返回 `SQLite`。
- `AccountStore::delete` 先显式删除账号的凭据状态、归属及交接操作。OAuth 导入回执、会话绑定、发送状态和用量记录仍依赖数据库级联。 `ProxyStore::delete` 按版本删除代理，`proxy_route_sync` 依赖级联。

## 生产只读统计

观测时间为 2026 年 11 月 22 日 04:52:42（Asia/Shanghai）。通过 SQLite `mode=ro` 和 `PRAGMA query_only=ON` 在同一只读事务中读取 Gateway 库。用 `PRAGMA foreign_key_list` 枚举以 `accounts`、`proxy_routes` 或 `request_diagnostics` 为父表的 `ON DELETE CASCADE`。逐条统计外键值非空且父记录不存在的行。返回内容只有表名、外键列名和计数。

| 子表 | 父表 | 外键 | 孤儿行 |
| --- | --- | --- | ---: |
| `account_credential_states` | `accounts` | `account_id` | 0 |
| `gateway_account_send_state` | `accounts` | `account_id` | 0 |
| `gateway_session_bindings` | `accounts` | `account_id` | 0 |
| `oauth_account_ownerships` | `accounts` | `account_id` | 0 |
| `oauth_credential_imports` | `accounts` | `account_id` | 0 |
| `oauth_handoff_operations` | `accounts` | `account_id` | 0 |
| `usage_records` | `accounts` | `account_id` | 0 |
| `proxy_route_sync` | `proxy_routes` | `proxy_id` | 0 |
| `request_diagnostic_attempts` | `request_diagnostics` | `request_id` | 0 |

`agy_account_credentials` 和 `proxy_sync_jobs` 在此次抽查的 Gateway SQLite schema 中均不存在。代理同步级联的实际表名是 `proxy_route_sync`。以上计数覆盖这份数据库快照和列出的外键。生产进程持久连接上的 PRAGMA 状态仍未观测。

## 改动验证

- 新回归建立真实迁移的文件库，逐条检查池容量内的连接，强制替换连接并确认 WAL。并发调用真实账号与代理删除入口，断言目标的八组子表记录均被移除，并保留另一组记录。
- 全量 Rust 按同一编译产物核对 926 个通过的单元测试和 103 个通过的集成测试。另有 14 个现有忽略项。初次进程被中断，已按编译产物的完整测试清单分批补跑。Doc-tests 退出为 0。
- 本次 Rust 文件的 `rustfmt --check` 及 `git diff --check` 通过。全仓格式检查同时发现 `service/account.rs` 和 `service/agy_account.rs` 的基线格式差异。
