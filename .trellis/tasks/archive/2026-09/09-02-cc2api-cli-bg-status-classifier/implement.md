# 实施计划

## 1. 设置链路

- [x] 在 `settings_store.rs` 定义 `intercept_cli_bg_status_classifier_mode=passthrough` 默认值。
- [x] 在 `db.rs` 默认插入新 key，并补 SQLite 迁移默认值测试。
- [x] 在 `gateway.rs` 增加 `CliBgStatusClassifierMode`、内存缓存和 reload 方法。
- [x] 在 `router.rs` 补 GET 默认、PUT 枚举校验、保存后热刷新和对应测试。
- [x] 在 `main.rs` 启动时加载新 setting。
- [x] 在 `Settings.vue` 增加“放行 / 模拟”控件及加载、保存逻辑。

## 2. 特征检测与放行旁路

- [x] 实现 wire/request/system/input 四层强特征 detector，使用脱敏最小 fixture。
- [x] 补 Fable 5.1 正例和 path、UA、x-app、model、stream、max_tokens、system marker、user marker、普通主请求、Fable 5、`[1m]`、旧 XML classifier 等负例。
- [x] 在账号选择前读取模式；mock 直接返回，passthrough 仅记录命中标记后进入正常代理链路。
- [x] 在 Rewriter 增加 identity-only body 入口，复用既有 metadata/upstream session 映射，不执行其他正文改写。
- [x] Gateway 命中 passthrough 时调用 identity-only 入口，保持 header/OAuth/account proxy/TLS/RPM/429 原链路。
- [x] 补测试断言 system cache_control 无 `ttl`、messages 无新增 cache_control、thinking/业务字段不变、metadata/session 按账号更新。

## 3. 模拟响应

- [x] 实现只分析状态摘要与 assistant tail 的确定性规则，显式 marker 优先、`Current state` 回退、未知时 working。
- [x] 复用 Anthropic Message envelope，返回可解析的内层状态 JSON。
- [x] 补 working/blocked/done/failed、needs/output 字段和“不进入账号/upstream”的测试。

## 4. 本地验证

- [x] `cd cc2api && cargo fmt --check`
- [x] `cd cc2api && cargo test cli_bg_status_classifier`
- [x] `cd cc2api && cargo test settings`
- [x] `cd cc2api && cargo test cch`
- [x] `cd cc2api && cargo test`
- [x] `cd cc2api/web && npm run build`
- [x] 检查 git diff，确认无真实抓包、prompt、token、代理 URL、账号标识或构建噪音进入提交。

## 5. 发布与真实账号代理验收

- [ ] 按 `trellis-push` 展示 cc2api 精确提交范围并取得提交/推送确认。
- [ ] 等待并核验 latest 镜像构建完成。
- [ ] 检查远程 established 连接，低连接窗口 pull + force-recreate。
- [ ] 验证服务健康、新 setting 默认值和最近日志。
- [ ] 保存并临时关闭全文 429/非流请求日志，选择 `proxy_url` 非空的活跃账号。
- [ ] 创建固定到该账号的一次性网关 token，经 `https://us.flower-cli.com/v1/messages` 发起一次脱敏 Claude Code 2.1.257 `cli-bg` 请求。
- [ ] 断言真实响应不是 429、响应来自上游、日志命中 `shape_bypass=true` 和 `proxy_configured=true`，且没有输出敏感信息。
- [ ] 若仍为 429，回到第 2 步根据最终出站摘要修正旁路并重新走质量门禁；不得切 mock 伪造通过。
- [ ] 删除一次性 token，恢复日志设置，确认生产 setting 保持 `passthrough`。

## Risky Files And Rollback Points

- `cc2api/src/service/gateway.rs`: `/v1/messages` 热路径；任何误命中都可能改变业务请求。
- `cc2api/src/service/rewriter.rs`: 身份映射与 CCH/缓存改写顺序；专用入口必须与普通入口隔离。
- `cc2api/src/handler/router.rs` / `src/store/db.rs`: setting 校验、迁移和热刷新必须一致。
- `cc2api/web/src/components/Settings.vue`: 前端必须提交字符串枚举值。
- 生产回滚优先切回上一镜像；新 setting 为附加 key，不需要破坏性数据库回滚。
