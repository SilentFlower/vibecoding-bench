# 修复 cc2api 260 标题 beta 与端点请求头画像

## Goal

修复用户明确要求处理的 Haiku 标题 fallback beta 丢失和后台端点 UA/beta 错配。

## Requirements

- R1：标题仅保留客户端已携带的 `server-side-fallback-2026-07-01` 和 `fallback-credit-2026-06-01`，去重并放在 `cache-diagnosis` 前。无 token 不开启 fallback，排除无关主模型/实验 beta，两种客户端入口一致。
- R2：code sessions、bridge、worker、presence、sessions/archive、notification preferences、ultrareview quota 按已验证具体路径选择 UA/beta；明确无 beta 的路径删除传入 beta。
- R3：版本画像声明能力，修正限于已有证据的 2.1.257/2.1.260；旧画像、未知路径、普通消息、Fast Mode/1M 保持既有行为。
- R4：使用人工脱敏 fixture，不提交原始抓包、用户正文或凭据。

## Background

- 260 五份抓包共 999 条 JSONL，原始证据位于忽略目录 `data/evidence/claude-code-2.1.260/`。
- 标题 10 条中 3 条带可选 fallback token，被 `cc2api/src/service/rewriter.rs:1280` 精确 beta 分支删除。
- `rewriter.rs:256` 和 `rewriter.rs:1218` 的通用画像误用于后台端点；归档抓包报告确认相同标题变体和端点身份在 257 已存在。

## Non-Goals

- worker JWT 和 API context/diagnostics/global cache 本轮仅分析方案；不修改鉴权、账号路由、403 处理、消息状态或缓存结构。
- 不修改 Sonnet 白名单、自动遥测或生产设置。2026-09-05 用户追加授权：推送已完成修复并部署现有 cc2api 服务。

## Acceptance Criteria

- [x] 标题三种 beta 变体、重复/乱序/相似 token、probe 窄画像验证通过。
- [x] 两种入口后台路径矩阵匹配抓包；无 beta 路径不继承任意传入 beta。
- [x] 旧画像、未知路径、主模型、Fast Mode/1M 与 CCH 回归通过。
- [x] `cargo fmt --check`、定向及全量 `cargo test` 通过。
- [x] 向用户解释 worker JWT 和 API 状态/缓存方案（详见 design.md 与交付答复）。

## Notes

- 用户已明确要求处理 R1/R2；另外两项以方案答复，不扩大实现范围。
- 交付追加范围：精确推送子模块与父仓记录，使用 CI 对应提交镜像更新既有 cc2api；保留旧镜像/配置与 DB 备份，验证镜像 revision、HTTP 和启动状态。复用已通过协议测试，不发送主动模型探测请求。
