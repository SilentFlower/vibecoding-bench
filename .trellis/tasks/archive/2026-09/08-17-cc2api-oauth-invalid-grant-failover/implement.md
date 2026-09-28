# 实施计划

## 1. 增加永久凭据错误类别

- [x] 在 `cc2api/src/error.rs` 增加带 Javadoc 的永久凭据错误类别，并保持外部 HTTP 映射为 503。
- [x] 在 `cc2api/src/service/oauth.rs` 解析 OAuth 非 2xx 的短错误码，把 `invalid_grant` 映射为永久错误；其他错误保持临时错误。
- [x] 确保错误摘要不包含 refresh token、Authorization、代理密码或完整响应正文。
- [x] 增加 OAuth 错误分类单测。

## 2. 保留 AccountService 分类语义

- [x] 在 `cc2api/src/service/account.rs` 把缺失 refresh token 映射为永久凭据错误。
- [x] 调整 `refresh_oauth_account()`：永久错误写安全 `auth_error` 后直接返回，不允许沿用旧 AT；临时错误保持现有有效 AT fallback。
- [x] 增加永久/临时错误与 fallback 的 AccountService 定向测试。

## 3. 修复 Gateway Token 预解析切号

- [x] 在 `/v1/messages` Token 预解析分支识别永久凭据错误，调用 `disable_for_auth_failure()`，排除账号、释放槽位并继续账号循环。
- [x] 在 `/v1/messages/count_tokens` 实现相同语义，并在候选耗尽时返回通用 Anthropic 503。
- [x] 复用一个小型私有 helper 收口停用原因和账号状态更新，避免两条 Gateway 路径产生语义漂移；不拆分更多无必要抽象。
- [x] 保持临时错误、401、429、slot、RPM 和 sticky 的既有行为。

## 4. 补充 Gateway 回归测试

- [x] 扩展现有 Gateway OAuth mock，支持成功、`invalid_grant`、429 和 5xx 响应。
- [x] 覆盖普通 `/v1/messages` 永久错误停用并切号成功。
- [x] 覆盖 sticky 绑定指向失效账号时仍能切号。
- [x] 覆盖 `/v1/messages/count_tokens` 永久错误停用并切号成功。
- [x] 覆盖所有账号永久失效时通用 503、每账号最多探测一次。
- [x] 覆盖临时 OAuth 错误不禁用账号。
- [x] 检查日志与响应断言不包含 fixture token 或完整 OAuth 正文。

## 5. 验证与规范收口

- [x] 运行 `cd cc2api && cargo fmt --check`。
- [x] 运行 OAuth、AccountService、Gateway 相关定向测试。
- [x] 运行 `cd cc2api && cargo test`。
- [x] 按 Check-All 结果修复回归或规范偏差。
- [x] 将“Token 预解析永久凭据错误必须停用并切号，临时刷新错误不得误停”写入 cc2api 后端 service architecture spec。

## 风险与回滚点

- 错误分类过宽会批量误停账号，因此永久列表只包含有明确证据的 `invalid_grant` 和缺失 RT。
- 错误分类在 Gateway 前丢失会导致修复无效，测试必须从真实 mock token endpoint 跑完整调用链。
- sticky 或账号循环处理错误可能造成重复选号，测试必须断言每个账号最多探测一次。
- 回滚代码不会自动恢复已停用账号；需要先修复凭据并由管理员手动启用。
