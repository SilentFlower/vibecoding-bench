# 实施计划

## 1. 扩展 2.1.257 版本画像

- [x] 在 `cc2api/src/service/version_profile.rs` 新增 2.1.257 identity、allowed range、
      Opus/Fable/Haiku 子画像、CCH 策略和 bootstrap endpoint 参数。
- [x] 将默认 profile 切换到 2.1.257，保留并测试 2.1.220 回滚画像。
- [x] 更新 session hello、telemetry、TokenTester 等画像消费者，移除会破坏回滚画像的
      共享新版本常量依赖。

## 2. 实现模型级请求改写

- [x] 在 `cc2api/src/service/rewriter.rs` 精确识别 Fable 5 与 Fable 5.1。
- [x] 为 Fable 5.1 应用独立 beta、`fallbacks="default"`、64000 max tokens、thinking
      display updates 和 body order；旧 Fable 5 保持原行为。
- [x] 将 CCH 归一化改为画像驱动，补充 2.1.257 Fable 5.1 保留 fallback 的样本测试。
- [x] 增加 Haiku probe/title/main/non-stream aux 分类和 beta 测试。
- [x] 用 JSON schema 结构识别新 title，并让 gateway 拦截器复用该判定。
- [x] 增加 `[1m]` 边界测试：不主动注入、默认账号过滤显式 beta、`fable` allowlist
      命中时仅透传客户端已有 token。

## 3. 补齐 Fable 5.1 限制与迁移

- [x] 在 `cc2api/src/service/account.rs` 将 Fable 5.1 纳入共享周配额、sticky fallback
      和模型级 429 换号。
- [x] 更新 system-role 默认列表，并在 `cc2api/src/store/db.rs` 增加保留自定义值的
      一次性追加迁移。
- [x] 更新 profile/range、bootstrap 默认值、账号 canonical env 的条件迁移与测试。
- [x] 保持 assistant-prefill、disabled-thinking 和 `allow_1m_models` 不变并增加回归断言。
- [x] 同步 `cc2api/web/src/components/Settings.vue` 与 `cc2api/README.md` 的默认画像和
      配置说明。

## 4. 改善首字节超时可观测性

- [x] 在 `cc2api/src/service/gateway.rs` 将 upstream request ID 传入流状态。
- [x] 区分 0 chunk first-byte timeout 与首 chunk 后 idle timeout 的日志事件。
- [x] 保持首 chunk 前无 keepalive、timeout 后不伪造 SSE 的现有行为。
- [x] 增加 request ID、chunk_count 和超时阶段的定向测试，确保日志上下文不含敏感数据。

## 5. 验证

- [x] 运行 `cd cc2api && cargo fmt --check`。
- [x] 运行版本画像、rewriter CCH、Fable 配额、DB 迁移和 stream timeout 定向测试。
- [x] 运行 `cd cc2api && cargo test cch`。
- [x] 运行 `cd cc2api && cargo test`。
- [x] 运行 `cd cc2api/web && npm run build`。
- [x] 执行 Check-All 并处理规范、测试或跨层契约偏差。

Check-All 结论：通过（CHK-001 已由用户接受风险）。Haiku 历史 prompt marker 与递归
schema 匹配保持现有兼容宽度，不在缺少新抓包回归时收窄。

## 风险与回滚点

- CCH 输入字节变化会造成全量签名不命中，必须先用固定脱敏 fixture 锁定再改实现。
- system-role 迁移不能覆盖管理员自定义列表；测试必须包含线上形态的额外模型。
- 误把 Fable 5.1 加入旧 disabled-thinking 会破坏真实 adaptive display 请求。
- 误注入 1M beta 会偏离 `86926719c1ee`，并可能改变计费/上下文策略。
- 超时日志变更不能改变下游 SSE 字节；失败时可单独回滚诊断改动，不影响画像适配。
