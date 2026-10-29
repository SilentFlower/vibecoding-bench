# 请求诊断验证证据

工作目录：`cc2api/`。仅使用本地合成上游及临时数据库，无生产请求或配置变更。

## 实际命令与结果

| 验证 | 命令 | 结果 |
| --- | --- | --- |
| 完整 Rust 回归 | `cargo test --locked` | exit 0；669 passed，2 ignored |
| 显式导入收口后的定向回归 | `cargo test --locked diagnostics` | exit 0；9 passed，1 ignored |
| PostgreSQL 诊断契约 | `CC2API_DIAGNOSTICS_TEST_POSTGRES_DSN=<独立临时库> cargo test --locked postgres_diagnostics_storage_contract -- --include-ignored` | exit 0；1 passed，0 ignored |
| PostgreSQL 正式迁移集成 | `CC2API_PROFILE_TEST_POSTGRES_DSN=<独立临时库> cargo test --locked --test version_profile_settings_test postgres_profile_settings_and_rollback -- --include-ignored` | exit 0；1 passed，0 ignored |
| 格式 | `cargo fmt --check` | exit 0 |
| 差异空白 | `git diff --check` | exit 0 |

默认全量回归的两个 PostgreSQL ignored 测试均已在临时 PostgreSQL 16.15 上分别显式执行成功。定向回归的 ignored 项为同一个诊断 PG 测试，不另计缺口。

完整测试包含签名重试与 CCH、OAuth 恢复/换号、JSON/SSE/gzip/取消、缓存/count_tokens、费用次数、账号池 TTL 和真实 HTTP/TLS/bridge 字节保真。全量回归后仅将新增两个测试模块的通配导入改为显式导入；最终定向回归重新编译并覆盖这些模块，没有运行时代码变化。

## 验收证据索引

| 验收 | 主要证据 |
| --- | --- |
| A1 实际参数/画像/用量 | diagnostics_preserve_bytes_and_correlate_anonymous_sessions；gateway_usage_records_real_responses_once_without_telemetry |
| A2 请求与重试关联 | gateway_signature_retry_keeps_profile_and_recomputes_cch；oauth_unauthorized_refreshes_and_retries_same_gateway_account；gateway_unauthorized_disables_and_switches_setup_account |
| A3 本地/模拟/压缩/取消 | diagnostics_routes_require_admin_and_expose_committed_requests；cli_bg_status_classifier_mock_returns_parseable_message_without_account；diagnostics_record_stream_errors_and_cancellation_once；真实 HTTP 用量回归 |
| A4 匿名 session/thread | diagnostics_preserve_bytes_and_correlate_anonymous_sessions；gateway_hello_probe_reuses_resolved_upstream_session；既有池 TTL/目标失效回归；源码核对仅观察原解析结果 |
| A5 留存和查询 | 两库 storage_contract、管理员路由测试；独立重开 reader、幂等与八天精确边界 |
| A6 隐私和故障 | 合成秘密断言；diagnostics_overload_and_write_failures_are_observable；diagnostics_cover_early_cancellation_and_unavailable_storage；diagnostics_report_observation_failures_without_changing_bytes |

管理 HTTP 查询实际运行于 SQLite，PostgreSQL 对等 SQL/store 与正式迁移已运行；管理员路由至共享 store 的调用路径另经源码核对。new-api 本地源码现有读取 X-Request-Id，并落入 upstream_request_id；生产留存结果需部署后核对，不在本轮执行。

## 源码快照

以下为验证结束时的 SHA256；仅用于审计，不表示已提交或部署。

```text
fae7adb399a2f6dfc71af694549825ade8af0a6afd6e21eda22b2b7d65e0c2dc  cc2api/README.md
ae25d29fded24fb0eccd70b007bac9f8aab37bc673a5d922943b1b1c716f8f2d  cc2api/docs/request-diagnostics.md
5001b2668d1793fcfacabaf6d6c062f603ada2fa68f1de92246cd171075791d2  cc2api/src/handler/router.rs
99e7c88518801e87180c176a6bd63215bcffb711b9a91e6320f7bbe4d1dbb752  cc2api/src/main.rs
19ad292c3af96a3e2ee0aaadabe39f77407f709ac388d80ad9fd381d5f78a340  cc2api/src/model/mod.rs
34ea09042ac609335b40b76c44105c8a1bc22b0c87e35211a1a6af9d6d4ecb81  cc2api/src/model/request_diagnostics.rs
f9a4707f4ee81f1dca4f2dba264f1efa0c9ed28448d3d456a93f44bbae8550af  cc2api/src/service/diagnostics.rs
a973515c6c29fa1a0170c16274ef4b77e4945639e24f8726771fc04cf934ad17  cc2api/src/service/gateway.rs
cf5d771727b909092914d4784a6e703c3537c9d4c67b3db2342e28a4e9eacfb4  cc2api/src/service/mod.rs
b1b4059eb1e42a4257edcae9719f231df5fdd0da0530e4e6084cfe11975cb553  cc2api/src/service/runtime_transport.rs
779aaf579c3e509cf4d191d5816714a559a09114abca3f77e64dd1fc9ee4960f  cc2api/src/service/usage.rs
936b17d9020bb5d4ce857da734191b5fff1bf0d3ea83d58dbb4cc23f2307e740  cc2api/src/store/db.rs
140ba4c146dc0b88b889fb62f523d5370974b63aa999a14ac5d3f2198f25da0d  cc2api/src/store/diagnostics_store.rs
4c554f458c9362ae2847cfe6f1a8f16cba950e156a2cd8e80c63443da0a8bc08  cc2api/src/store/mod.rs
eb127fd698d998f64ee6cea2489fe97c513bc9e7fb9127c4d39093e21a451d17  cc2api/tests/runtime_transport_test.rs
```
