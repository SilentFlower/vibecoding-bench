# Brief — 修复 cc2api 260 标题 beta 与端点请求头画像

## Goal

- 修复标题 fallback beta 丢失和后台 UA/beta 错配。

## Scope

- 257/260 标题两个可选 token；会话、worker、presence、通知、quota 的 UA/beta；两种入口与回归测试。

## Non-Goals

- worker JWT 和 API context/diagnostics/global cache 仅给方案；不修改鉴权、路由、遥测、生产设置。

## Key Decisions

- 标题仅保留已携带 token；无 beta 后台端点删除传入 beta；未知路径与旧画像保留原行为。

## Key Context

- `version_profile.rs`、`rewriter.rs`、脱敏 fixture；依据五份 260 抓包及 257 基线。

## Risks / Deferred

- worker JWT 需要可信凭据/会话绑定；diagnostics 需要真实响应关联；不承诺完整 worker 代理或传输层顺序一致。

## Acceptance

- 标题变体、后台路径、旧版和主请求回归通过，格式及全量 Rust 测试通过。

## Next Step

- 请求头修复已推送并部署，CI、服务健康和数据一致性验证通过，部署证据见 release.md。worker JWT/API 后续方案未实现，后续按用户需要单独处理。
