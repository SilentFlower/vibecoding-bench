# Brief — 修复 CCH 封口与刷新误改正文（F01）

## Goal

- CCH 只更新真正的 system billing，保留正文和其它字段中的同名示例。

## Scope

- 收窄前置占位化，修复初始封口与重试刷新；覆盖 API／CC、system 字符串／数组及特殊调用路径。

## Non-Goals

- F03 身份重建、F04 缓存与重复 billing 规范化／环境／入口策略、F05 TLS，以及 303 升级、部署。

## Technical Overview

- 复用已有 JSON 字节扫描，定位唯一根级 billing 的五位 CCH；在最终字节上沿用现有版本算法计算并回填，不重序列化整个 body。

## Context & Decisions

- 普通文本／reminder 不再被通用 CCH 重置污染；现有 cache_control 跳过条件、billing 模式、seed、投影和后缀规则保留。缺失、非法或重复目标时，CCH 处理保持其输入，不回退全文搜索。

## Risks

- 转义和字节偏移可能误定位；歧义请求可能保留占位值，后续再由 F04 决定异常请求策略。

## Acceptance

- 原有初始／刷新反例及独立 xxhash 参考通过；用户、工具、metadata、reminder、普通 system 文档与嵌套 system 示例保持完整。
- 字符串／数组、顺序／空白／转义、非法／重复目标、历史版本与 API／CC 特殊路径有回归；CCH 处理只修改目标五位值。
- `cargo fmt --check`、`cargo test --locked`、`cargo test --locked cch` 与 Check-All 通过，再完成 Spec 评估与精确 Git 计划。

## Next Step

- 通过本 Brief 后启动任务，先添加能复现污染的失败回归。
