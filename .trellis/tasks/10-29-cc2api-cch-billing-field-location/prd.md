# 修复 CCH 封口与刷新误改正文（F01）

## Goal

使 cc2api 只更新受管理的 system billing CCH，保持用户正文、工具与其它字段中的同名示例完整。

## Background

- 用户在 vm2api／cc2api 第一轮对齐评审中明确选择“F01 要修”。F03、F04、F05 仍是解释与研究事项，不合并为本次实现范围。
- [第一轮评审](../10-29-cc2api-vm2api-wire-differential-study/research/alignment-review/round-01.md)保留冻结反例：`api-body-cch-user-literal` 中用户 `cch=00000` 被改为 `fd17b`，真正 billing 仍为 `00000`；`api-cch-position-user-12345-first` 刷新时用户 `12345` 被改为 `3bcd5`，真正 billing 没有更新。
- 当前产品基线为 `d5749d923e997fd3c01dde31248b5af8dde906ee`。`src/service/rewriter.rs:2569` 的初始封口与 `2628` 的刷新定位均为全文搜索；`2342` 还会在通用系统文本／reminder 改写中重置 CCH。

## Requirements

| 编号 | 要求 |
| --- | --- |
| R1 | CCH 占位化、初始封口和二次刷新均限于根级 `system` 中受管理的 billing attribution 行；覆盖数组 text block 和既有字符串形状，兼容已有入口标签。 |
| R2 | 用户消息、普通 system 文档、工具定义／结果、metadata、嵌套 system 及 reminder 示例不得因上述 CCH 处理被改写。 |
| R3 | 在最终序列化字节上计算；沿用现有 seed、model／max_tokens／fallbacks 投影与 `cc_version` 规则；CCH 处理不得重排 JSON、改变空白／转义或重新序列化整个 body。 |
| R4 | 缺失、非法或存在多个可匹配 billing／CCH 目标时，不猜测目标、不回退全文搜索、不新增合并或拒绝行为。该约束只针对 CCH 处理，不承诺其它既有 body 改写停止。 |
| R5 | 保留初始改写已有的 cache_control 跳过条件与 billing 模式门禁；API／CC 的普通、特殊与重试路径遵守相同 CCH 定位边界。 |

## Acceptance Criteria

- [x] AC1（R1、R2）：修复用户 CCH 出现在 system 前／后的初次封口及刷新错误，真正 billing 与独立参考结果一致。
- [x] AC2（R2）：正文为 `00000`／非零值、工具／metadata／reminder／普通 system 文档含同名示例时，示例逐字节保持；嵌套 system 不被当作根级目标。
- [x] AC3（R1、R3）：数组和字符串 system、中文／转义／空白／字段顺序均有回归；字节差异只位于允许更新的五位 CCH 值。
- [x] AC4（R4）：缺失、非法长度／字符／边界、重复 billing 或重复 CCH 时，CCH 处理函数返回其收到的原始字节，不误写其它字段。
- [x] AC5（R3、R5）：旧版本、280／293 独立夹具、API／CC billing 模式和特殊／重试路径通过；现有缓存跳过语义有回归断言。
- [x] AC6：`cargo fmt --check`、`cargo test --locked`、`cargo test --locked cch` 通过并记录结果；Check-All 后按现有 Spec 与 Push 流程收尾。

## Non-Goals

- F03 身份重建、F04 缓存合法性／重复 billing 规范化／环境／入口策略、F05 TLS 对齐。
- 303 画像升级、身份来源、会话池、模型能力、缓存默认值、seed 或哈希投影变更。
- 复制 vm2api 整套输出、真实官方请求、部署或推送未经确认的文件范围。
