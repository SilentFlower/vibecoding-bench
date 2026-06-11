# cc2api Code-Spec Index

> `cc2api` 是独立仓库 `/root/project/cc2api`，Trellis 任务记录保存在本仓。本目录只沉淀跨仓维护 `cc2api` 时必须遵守的可执行协议。

---

## Guidelines Index

| Guide | Description | Status |
|-------|-------------|--------|
| [Claude Code Profile Upgrade](./claude-code-profile-upgrade.md) | Claude Code 版本画像、CCH、`cc_version`、beta、bootstrap、账号迁移与抓包验收 | Filled |

---

## Pre-Development Checklist

修改 `/root/project/cc2api` 的 Claude Code 协议画像前必须：

1. 读取任务的 `prd.md` / `design.md` / `implement.md`。
2. 读取 [Claude Code Profile Upgrade](./claude-code-profile-upgrade.md)。
3. 搜索并核对 `/root/project/cc2api` 中的 `version_profile`、`rewriter`、`telemetry`、`db`、`settings_store`、bootstrap 相关代码。
4. 用真实抓包样本分别复算 `cc_version`、CCH、`anthropic-beta` 顺序和 bootstrap response 差异。

---

**Language**: 中文撰写；字段名、header、SQL、命令和模型 ID 保留原文。
