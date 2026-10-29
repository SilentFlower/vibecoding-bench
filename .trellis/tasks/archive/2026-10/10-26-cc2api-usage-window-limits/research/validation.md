# 每账号 5h/7d 用量控制线验证证据

验证日期：2026-10-26。全部使用本地合成账号、独立临时数据库与本地假上游；没有生产配置或真实额度请求。

| 工作目录 | 命令或验证 | 最终结果 |
| --- | --- | --- |
| `cc2api/` | `cargo fmt --check` | exit 0 |
| `cc2api/` | `cargo test --locked` | exit 0；678 passed、0 failed、3 ignored（需独立数据库的专项测试） |
| `cc2api/` | `CC2API_USAGE_LIMITS_TEST_POSTGRES_DSN=<独立临时库> cargo test --locked --test account_store_timestamp_test usage_limits_postgres_storage_and_legacy_migration -- --include-ignored` | exit 0；1 passed、0 ignored |
| `cc2api/web/` | `npm run build` | exit 0；TypeScript 与 Vite 构建通过 |
| `orchestrator/` | 下列 bench 定向 unittest | exit 0；15 passed |
| 独立本地网关 | Playwright + 本机 Chrome 真实页面与 SQLite 验证 | 保存 80/60、持久化、列表展示、编辑回显、小数/越界不提交、0 关闭、新建重置、无页面异常均通过 |
| 两个 Git 仓库 | `git diff --check` | exit 0 |

## Rust 关键覆盖

- 两类账号和两个窗口：等于上限换号，低于上限保持 sticky，替代账号实际承载前保留旧绑定。
- 按账号独立值、Token allow/block、全部达线 429、关闭限制、100 边界、非法/缺失/过期用量和重置恢复。
- Fable 与普通窗口分别排除不同账号时不回退到达线账号；普通模型不误用 Fable 专有窗口。
- 消息确实只到未达线的假上游账号；全部达线时无上游请求，`count_tokens` 继续可用；调高阈值后下一次选号恢复。
- 管理 API 创建默认、显式非零值、局部更新、错误类型及越界拒绝，非法请求不产生账号或状态变更。
- active/disabled 状态与控制线同次更新不会丢弃新阈值；独立控制线写入不会用旧快照覆盖刷新后的 OAuth、状态和进程指标。
- SQLite/PostgreSQL 均覆盖旧库缺列升级、默认 0、重复迁移保留非零值、创建/更新/详情/分页/调度查询，以及凭据刷新和指标写入后限制保留。
- 现有 Fable、RPM、队列、OAuth、协议改写与传输测试随完整套件通过。

## bench 回归命令

通过临时 Python venv 安装项目已有版本的 Docker SDK 和 SSE 依赖，未修改项目依赖：

```bash
python -m unittest -q \
  test_main.ScheduledWarmupTests.test_explicit_create_sends_six_defaults_and_preserves_warmup \
  test_main.ScheduledWarmupTests.test_explicit_bind_never_creates_or_changes_warmup \
  test_main.ScheduledWarmupTests.test_sync_links_existing_cc2api_account_without_create \
  test_main.ScheduledWarmupTests.test_sync_creates_cc2api_account_with_fast_mode_disabled \
  test_main.ScheduledWarmupTests.test_bound_account_refresh_scheduler_only_mirrors_cc2api \
  test_main.ScheduledWarmupTests.test_process_action_does_not_resolve_credentials_or_change_account \
  test_process_metrics test_credential_publication
```

旧创建载荷没有新字段时仍创建成功，默认 0；原有并发 4、RPM 50、session 池 4/owner_only、rewrite 计费模式保留。cc2api 的真实管理路由另外验证同样载荷与后续局部更新，双库存储验证凭据/指标操作保留控制线。

## 环境与已修正问题

- 首次 SQLite 内存库测试因多连接访问不同内存数据库失败；测试池限制为 1 后通过。
- PostgreSQL 真库测试发现旧 AccountStore 向 JSONB 列传文本、返回原生 JSONB/时间列导致 SQLx Any 不兼容；已增加显式 JSONB 参数转换、文本投影与时间解析，两库复测通过。
- 最终库使用独立 PostgreSQL 16 临时容器，不复用现有运行中的 PostgreSQL 服务或生产数据库。
- Cargo 输出包含已有 vendor reqwest cfg 和未来兼容性警告，没有本轮新增编译错误。

## 证据位置与边界

- 完整 Rust 输出：`/tmp/cc2api-usage-limits-full-test.log`。
- PostgreSQL 最终输出：`/tmp/cc2api-usage-limits-postgres-final.log`。
- 前端构建：`/tmp/cc2api-usage-limits-web-build.log`。
- bench 输出：`/tmp/cc2api-usage-limits-bench-tests.log`。
- 页面脚本和输出：`/tmp/cc2api-usage-limits-browser.py`、`/tmp/cc2api-usage-limits-browser.log`。页面证据覆盖本轮表单、持久化与常规更新；后续状态快捷分支修复由最终 Rust 管理路由和双库用例覆盖。
- 三个默认 ignored 专项中，本任务新增 PostgreSQL 控制线用例已另行执行；其余诊断存储、版本画像 PostgreSQL 专项不属于本轮改动的核心链路，没有将 ignored 计作通过。
- 控制依据已观测用量，未知窗口放行，可能因并发或单请求越线；独立 CLI 与后台用量不属于本轮网关消息选号约束。
