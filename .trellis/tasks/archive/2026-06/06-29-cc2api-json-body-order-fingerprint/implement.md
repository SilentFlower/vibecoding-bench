# 实施计划

## Step 1：依赖与 setting

- [ ] `cc2api/Cargo.toml` 将 `serde_json` 改为启用 `preserve_order`。
- [ ] `settings_store.rs` 增加 `DEFAULT_MESSAGE_BODY_ORDER_FINGERPRINT_ENABLED=true`。
- [ ] `db.rs` 默认 settings 插入新增 key。
- [ ] `GatewayService` 增加缓存字段、reload 方法和初始化默认值。
- [ ] `router.rs` settings 保存后 reload 新开关。
- [ ] `Settings.vue` 增加开关控件和默认值。

## Step 2：Rewriter 排序

- [ ] 在 `rewriter.rs` 增加 API mimicry `/v1/messages` 顶层字段排序函数。
- [ ] 将排序开关参数传入 body rewrite。
- [ ] 确保排序发生在序列化和 CCH 计算前。
- [ ] 确保 `ClientType::ClaudeCode` 保留真实客户端原始顶层顺序。

## Step 3：测试

- [ ] 增加 Rust 单测：API mimicry Opus 主请求顶层 key 顺序。
- [ ] 增加 Rust 单测：API mimicry Haiku `max_tokens=1` 生成体顺序。
- [ ] 增加 Rust 单测：API mimicry Haiku 流式标题生成体顺序。
- [ ] 增加 Rust 单测：关闭开关时不重排。
- [ ] 增加 Rust 单测：Claude Code 客户端开关开启时仍保留原始顶层顺序。
- [ ] 增加 Rust 单测：未知字段保留。
- [ ] 增加 Rust 单测：CCH 对排序后 body 生效。

## Step 4：验证

- [ ] `cd cc2api && cargo fmt --check`
- [ ] `cd cc2api && cargo test rewriter`
- [ ] `cd cc2api && cargo test settings`
- [ ] 如改前端：`cd cc2api/web && npm run build`

## 风险文件

- `cc2api/Cargo.toml`
- `cc2api/src/service/rewriter.rs`
- `cc2api/src/service/gateway.rs`
- `cc2api/src/store/settings_store.rs`
- `cc2api/src/store/db.rs`
- `cc2api/src/handler/router.rs`
- `cc2api/web/src/components/Settings.vue`
