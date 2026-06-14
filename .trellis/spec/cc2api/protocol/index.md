# cc2api Protocol Code-Spec Index

> 本层只覆盖 `cc2api/` 的 Claude Code / Anthropic wire protocol 画像：版本、User-Agent、CCH、`cc_version`、beta、bootstrap、telemetry 和账号 canonical env。Rust 后端结构见 [Backend](../backend/index.md)，管理前端见 [Frontend](../frontend/index.md)，部署见 [Deploy](../deploy/index.md)。

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Claude Code Profile Upgrade](./claude-code-profile-upgrade.md) | Claude Code 版本画像、CCH、`cc_version`、beta、bootstrap、telemetry、账号迁移与抓包验收 | Filled |

---

## Pre-Development Checklist

修改 `cc2api/` 的 Claude Code 协议画像前必须：

1. 读取任务的 `prd.md` / `design.md` / `implement.md`。
2. 读取 [Claude Code Profile Upgrade](./claude-code-profile-upgrade.md)。
3. 同时读取 [backend](../backend/index.md) 的 service/settings 规则。
4. 搜索并核对 `cc2api/` 中的 `version_profile`、`rewriter`、`telemetry`、`db`、`settings_store`、bootstrap 相关代码。
5. 如果影响设置页或发布流程，同时读取 [frontend](../frontend/index.md) / [deploy](../deploy/index.md)。
6. 用真实抓包样本分别复算 `cc_version`、CCH、`anthropic-beta` 顺序和 bootstrap response 差异。

## Quality Check

协议画像变更默认需要：

```bash
cd cc2api
cargo fmt --check
cargo test
cargo test cch
```

如涉及设置页：

```bash
cd cc2api/web
npm run build
```

---

**Language**: 中文撰写；字段名、header、SQL、命令和模型 ID 保留原文。
