# Brief — 采集 Claude Code 2.1.260 协议证据

## Goal

- 对生产 bench 已完成的 Claude Code 2.1.260 抓包进行只读、脱敏、可复算分析，为 cc2api 2.1.260 协议画像实现提供唯一事实来源。

## Scope

- 核验 Opus、Sonnet、Fable 5.1、Haiku 的 run ID、版本快照、终态、轮次和抓包完整性；实际观察到 Fable 5 时追加独立样本。
- 按 bootstrap、hello/eval、telemetry、`/v1/messages` 和后台辅助请求分别提取身份、header、beta、body 字段顺序、模型参数与响应形态。
- 对比 2.1.257 基线，复算 `cc_version` 后缀和 CCH，区分保持不变、确认变化与证据不足。
- 写入脱敏 `research.md`、必要的最小 fixture 和 cc2api 文件/契约影响清单，并检查 Git 不包含原始抓包或凭据。

## Non-Goals

- 本任务不修改 cc2api 或 bench 业务代码。
- 不把上游偶发 429、5xx、零首字节或手动停止自动归因于协议画像。
- 不提交原始 `.flow`、完整 JSONL、Token、Cookie、Authorization、邮箱、完整 prompt 或响应正文。

## Key Decisions

- 原始证据只从生产环境只读拉取到 Git 忽略目录；仓库仅保存脱敏统计、字段形态、hash 结论和匿名最小样本。
- 协议分析按 endpoint、模型和请求类型分层，不能把不同请求族混成单一版本画像。
- `cc_version` 和 CCH 先验证 2.1.257 的算法、seed 与归一化规则；只有多条样本持续不命中时才判定算法变化。
- Fable 5 与 Fable 5.1 保持精确模型边界；至少一个复杂模型样本需要覆盖多轮继续。

## Key Context

- 抓包目录为 `data/flows/<account>/<topic_id>/<run_id>/`，入口文件包括 `capture_index.json`、`http_capture.jsonl`、`stats.jsonl` 和 `.flow`。
- bench API 和 `runs` 快照用于核验 CLI 版本、目标模型与终态；原始证据如仅在远程，按部署配置只读获取。
- cc2api 2.1.257 基线集中在 `version_profile`、`rewriter`、`telemetry`、bootstrap、settings/DB 迁移和现有协议测试中。

## Risks / Deferred

- 单个请求不能代表整个模型画像，主请求、probe、title、classifier、继续轮次和非流式辅助请求必须分别归类。
- Sonnet 或其他样本即使终态不是 success，只要抓包完整仍可作为协议证据，但必须单独标注中断阶段与覆盖缺口。
- cc2api 代码改动和生产发布分别由后续协议实现、部署子任务承接。

## Acceptance

- 约定模型均有可定位的 2.1.260 run、版本快照和抓包完整性结论。
- 每个已观察请求族都有脱敏的 endpoint、身份/header、beta、body、bootstrap/telemetry 和响应差异摘要。
- 所有带签名样本均给出 `cc_version`、CCH 的算法输入、归一化规则、命中率和失败分类。
- 形成足以直接实施 cc2api 2.1.260 画像的影响清单与最小 fixture，且 Git 不包含原始敏感抓包。

## Next Step

- 同步 Claude Code 协议规范中的 2.1.260 事实与 2.1.257 Fable 5 历史修正，再将结论交给 cc2api 2.1.260 协议子任务。
