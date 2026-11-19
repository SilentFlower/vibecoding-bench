# 代码研究依据

## 会话与调用方

- `services/gateway/src/model/api_token.rs`：`ApiToken.id: i64` 是现有访问令牌身份。
- `services/gateway/src/service/rewriter.rs:6357`：`extract_session_id_from_body(&Value) -> Option<String>` 解析 `metadata.user_id` 的 JSON 字符串与旧式 `_session_` 后缀。
- `services/gateway/src/service/gateway.rs:1950`：`handle_request_inner` 完成请求解码、JSON 解析，再进入客户端判别和调度，可在调度前使用原始 body 冻结封禁身份。
- 同文件 `forward_native_messages` 读取原始会话后才应用 upstream session 映射；`native_pool_session` 为原生分支校验 header/body 会话的一致性。
- `.trellis/spec/gateway/backend/service-architecture.md` 的稳定会话合同规定以域分隔、Token ID 与改写前 SID 生成 SHA256，持久摘要避免保留原 SID。

## 响应处理

- `GatewayService::forward_native_messages` 和普通 `forward_request` 最终汇合到 `finish_forward_response`。
- `services/gateway/src/service/usage.rs` 的 `UsageCapture` 已有有界增量 JSON/SSE 解析和 `ResponseBodyDecoder`；`MessageObservation` 保留 `stop_reason`、`error_type`，适合新增原因枚举而非持久化任意错误正文。
- `services/gateway/src/service/diagnostics.rs` 的 `AttemptTrace` 是诊断旁路，能力依赖诊断上下文。封禁执行必须独立于日志开关与诊断持久化结果。
- `finish_forward_response` 当前存在通用 HTTP 403 账号停用分支，策略拒答识别需要先于账号故障处理，避免把会话拒答升级为账号故障。
- 普通 Rust 分支有签名修复与 OAuth 恢复重试；所有真正提交边界需要复查封禁，策略拒答终止本次重试链。
- `handle_count_tokens_request_inner` 是独立入口，应复用同一会话查询机制。

## 数据库与管理界面

- `services/gateway/src/store/database_migrations.rs` 使用 `sqlx::AnyPool`，SQLite 有连续版本登记，PostgreSQL 保持独立初始化兼容。
- 当前登记至 `gateway.proxy-sync.3`。新表与默认设置应新增独立纯迁移模块及第 4 步，保持基线和已登记定义冻结。
- `deploy/flower2api/system_release.py::GATEWAY_SCHEMA_SOURCES` 定义迁移 ID 到源文件的精确映射；`verify_database_definitions.py` 校验 DDL 归属，新增步骤需同步映射和测试。
- `apps/web/src/components/Settings.vue` 结合 `apps/web/src/lib/settingsSchema.ts` 展示配置；`SettingsMap` 的 value 全为字符串。
- `apps/web/src/router.ts` 的 dashboard 子路由继承管理登录；`AppNavigation.vue` 由桌面与移动端共用。
- `apps/web/src/api.ts` 统一执行管理 API 鉴权和异常处理；管理列表复用现有 Table、Badge、SearchInput、ChoiceSelect、Pagination 和操作反馈。

## 外部参考

- `/root/project/vm2api/src/lib/core/refusal-guard.mjs`、`pool/upstream-error-policy.mjs` 提供上游拒答分类和本地提前拦截参考。
- 已使用截图完整文案构造 HTTP 400 错误，vm2api 识别为 `usage_policy_refusal`，命中原因是 `legal/aup`；仅 `[reasoning_extraction]` 未命中其现有规则。
- 本功能使用按真实会话隔离的限时封禁，具体实现依本仓库类型及合同。
