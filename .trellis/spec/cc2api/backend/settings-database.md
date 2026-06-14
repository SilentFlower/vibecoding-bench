# cc2api Settings & Database

## 数据库栈

`cc2api` 同时支持 SQLite 和 PostgreSQL：

- 初始化入口：`src/store/db.rs::init_db`
- schema/migration 入口：`src/store/db.rs::migrate`
- 运行时连接：`sqlx::AnyPool`

所有 SQL 变更都必须考虑 SQLite 与 PostgreSQL 两套 schema。不要只改其中一套。

## 迁移规则

- `ALTER TABLE ... ADD COLUMN` 目前采用幂等失败吞掉的方式支持旧库升级；新增列要确认重复执行安全。
- settings 默认值通过 `settings` 表插入 key/value；新增 setting 必须有默认值、老值迁移策略和非法值兜底。
- 版本画像相关迁移必须更新已有账号的 `canonical_env.version/version_base/build_time`，不能只改新账号默认值。
- 删除或废弃 setting key 时，加入 `OBSOLETE_SETTINGS_KEYS`，并确认 UI 不再提交旧 key。

## Settings Key 契约

新增 setting 必须同步：

1. `src/store/settings_store.rs` 的 `DEFAULT_*` 常量。
2. `src/store/db.rs` 的默认插入或迁移。
3. `src/handler/router.rs` 的校验、解析、`update_settings` reload。
4. `src/service/gateway.rs` 或对应 service 的内存缓存字段。
5. `web/src/components/Settings.vue` 的控件。
6. README 或部署文档中需要用户配置的说明。

Setting value 应以字符串存储，进入 service 前解析成 enum/bool/number。非法值必须返回 `AppError::BadRequest` 或回退到明确默认值，不要让热路径 panic。

## Account 字段同步

账号字段跨越多层：

```text
src/model/account.rs
src/store/account_store.rs
src/service/account.rs
src/handler/router.rs
web/src/api.ts
web/src/components/Accounts.vue
```

新增账号字段时必须同步读写、分页列表、更新接口、前端类型和 UI。涉及 token、邮箱、OAuth、usage 的字段必须默认脱敏展示。

## 时间字段

- 后端持久化时间优先使用 RFC3339 字符串。
- 前端展示前只做格式化，不反推出业务窗口。
- usage window、RPM window、telemetry session 过期时间不能混用。

## Common Mistakes

| 反模式 | 风险 | 正确做法 |
|--------|------|----------|
| 只更新 SQLite schema | PostgreSQL 部署启动失败 | SQLite/PG 同步改 |
| 老 settings 没有迁移 | 远程实例仍使用旧行为 | 在 `migrate` 中处理旧 key/value |
| setting 写入后不 reload | UI 显示已保存但热路径不生效 | `update_settings` 后调用对应 reload |
| 前端类型漏字段 | 构建或运行时展示异常 | 同步 `web/src/api.ts` |
| 直接暴露 `access_token` / `refresh_token` | 凭据泄露 | 管理 API 和 UI 做脱敏或必要最小展示 |
