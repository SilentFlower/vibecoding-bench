# Fast 账号策略研究

## 决策来源

- 用户接受的行为：禁止 Fast 时同时移除根级 `speed: "fast"` 与 Fast beta，继续按普通模式发送；允许时保留客户端申请，普通请求不主动开启。
- 本轮只规划 R13-01，R13-02 单独保留。
- 官方说明：https://platform.claude.com/docs/en/build-with-claude/fast-mode 。普通模式回落示例删除 `speed: "fast"`；Opus 5.5 无需旧 Fast beta。仅作为公开 API 契约依据。

## 代码证据（规划时位置）

- `cc2api/src/model/account.rs:233`：`allow_fast_mode: bool`，serde 默认 false；无需新存储字段。
- `cc2api/src/service/rewriter.rs:271`：`filter_account_beta_tokens` 只精确过滤 beta，不处理正文。
- `cc2api/src/service/rewriter.rs:1968`、`:2006`、`:2146`：身份专用、状态分类归因和普通正文改写为不同入口。普通正文单独加过滤不能覆盖全部消息转发。
- `cc2api/src/service/rewriter.rs:2232`：公开 CCH 刷新受 billing/client_type 门禁控制；禁止 Fast 修改正文时需关注原生 CC billing 透传模式已有 CCH。
- `cc2api/src/service/rewriter.rs:2687`：既有根级 CCH 刷新函数；不得增加新的全文查找逻辑。
- `cc2api/src/service/gateway.rs:2226`：账号已确定后，分流三个正文改写入口；最终正文之后重新解析生成 header。适合在分流汇合处补账号策略，再交给既有后续签名修复／编码发送流程。
- `cc2api/src/service/gateway.rs:1551`、`:1668`：count_tokens 在选号前序列化通用正文，在账号循环中生成 header。策略必须从公共原文为当前账号派生正文，不能原地污染后续换号输入。
- `cc2api/src/service/gateway.rs:3405`：count_tokens 仅删已有生成参数；不能借此扩大全局字段白名单。
- `cc2api/src/service/gateway.rs:10246`：现有压缩请求测试助手；复用实际 Gateway／本地接收器验证最终报文。
- `cc2api/web/src/components/Accounts.vue:1471`、`:1494`：已有禁止／允许按钮，说明仍只提旧 token。
- `cc2api/Cargo.toml:36`：serde_json 启用 preserve_order；无变更请求仍应直接保留输入字节。

## VM 对照边界

- VM `src/lib/protocol/claude-code-betas.mjs:97` 根据支持模型和正文 Fast 申请补 beta。
- VM `src/lib/protocol/anthropic-policy.mjs:368` 有按 beta／模型清理 speed 的兼容函数；不能将该早期函数或单测推广成所有 CLI 路径的最终行为。
- VM 可见控制面没有与 cc2api 等价的账号 Fast 禁止字段。R13 实际 CLI 链路保留支持模型的 Fast 申请；该对照不决定 cc2api 的账号产品策略。

## 规范影响

- `.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md:954` 的 Fast 场景目前明确“只过滤 beta、不得修改正文”；需用本任务经评审的新契约替换该约束。
- `.trellis/spec/cc2api/protocol/claude-code-profile-upgrade.md:1713` 的多值 beta 规范继续成立；本轮不扩大 API／safeguard／title beta 合并范围。
- `.trellis/spec/cc2api/backend/service-architecture.md:38` 的请求压缩规则：在最终 CCH 后、每次真正发送前按冻结编码链编码，长度依据最终 bytes；必须复用。
- 后台身份／归因专用路径仍保留既有窄改写行为；Fast 账号策略是所有实际转发共同遵守的例外，不扩展为普通正文改写。

## 验证边界

- 规划阶段未改产品代码、未执行产品测试。
- 后续验证采用本地合成 Gateway／TCP，不使用真实凭据、官方模型或生产部署。
