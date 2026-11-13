# 实施计划

1. 阅读诊断模型、存储、路由与账号表，复核所有构造和双驱动空值规则。
2. 添加兼容字段，在列表与详情查询中关联安全资料。
3. 同步 TypeScript 类型与统一展示，覆盖全部入口和手机长文本。
4. 扩展存储测试：跨账号、改名、删除、空资料、旧 JSON、过滤与分页。
5. 扩展真实产物管理浏览器场景：桌面、390px、长文本、各页签和 ID 直达。
6. 验证后进入 Check-All、Spec 与精确 Push 计划。

## 验证命令

- cargo fmt --check --manifest-path services/gateway/Cargo.toml
- cargo test --manifest-path services/gateway/Cargo.toml diagnostics
- 完整 cargo test --manifest-path services/gateway/Cargo.toml，复用仍适用的前序证据。
- npm --prefix apps/web run build
- python3 deploy/flower2api/verify_management_ui.py --output .deploy/management-ui/diagnostic-account-display
- 按实际 SQL 影响使用现有 PostgreSQL 合成夹具验证双驱动行为。

## 风险与回滚

重点验证重试关联、删除账号 LEFT JOIN、旧字段缺失、Any NULL 解码及手机长文本。回滚仅恢复展示和安全投影，持久数据维持原合同。
