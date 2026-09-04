# 实施计划

## 1. 接收与校验样本

- [x] 收集用户提供的 run ID、模型和轮次说明。
- [x] 核验每个 run 的 `claude_code_version=2.1.260`、抓包目录和终态。
- [x] 建立 Opus、Sonnet、Fable 5.1、Haiku覆盖矩阵；按实际情况追加 Fable 5。

## 2. 协议对比

- [x] 分 endpoint 提取脱敏 identity、header、beta、body order 和响应形态。
- [x] 分模型/请求类型对比 2.1.257 基线。
- [x] 复算全部可用 `cc_version` 与 CCH 样本，记录命中率和失败分类。
- [x] 检查新增 endpoint、后台请求、bootstrap/telemetry 字段和超时行为。

## 3. 交付 cc2api 输入

- [x] 写入脱敏 `research.md` 和差异矩阵。
- [x] 生成可提交的最小 fixture，不包含真实账号或会话正文。
- [x] 输出 cc2api 文件/契约影响清单和必须保留的 2.1.257 回滚行为。
- [x] 检查 Git 不包含原始抓包并完成任务 Check-All。
