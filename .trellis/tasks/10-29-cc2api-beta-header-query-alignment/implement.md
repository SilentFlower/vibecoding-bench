# 实施计划：beta 请求头与查询参数对齐

## 开工条件

- [x] 完成规划收敛、配置子 agent 上下文，并完整展示 Brief 获得首次开工确认。
- [x] R2-06 交接共享 Gateway；核对其源码指纹和验证证据，刷新与其相关的规范摘录。
- [x] 激活本任务，经 trellis-route 选择用户要求的 subagent；禁止两个实现 agent 同时写 Gateway。

## 实施步骤

- [x] 读取实际提取函数、beta 合并函数、账号过滤／特殊画像、URL 构造器与 Gateway harness，确认签名后先增加会失败的实际 Gateway 回归。
- [x] 仅合并所有可用 anthropic-beta 行并精确去重，保留有效空值、其它头既有语义和账号／画像过滤。
- [x] 在现有目标路径将解码后同名 beta 归一为唯一 true；保留其它 query 原始片段，不引入全局白名单或新依赖。
- [x] 用实际 Gateway 覆盖 280／293 普通与特殊画像、API、count_tokens，及 URL 编码／重复／非目标矩阵；验证上游实际收到的头与 URL。
- [x] 对照 R2 交接基线确认清理开关、Session、stream 三态与已有 CCH 合同无回退。

## 验证与完成链

- [x] `cargo fmt --check`；有意义的新增回归先红后绿，记录命令、退出码、源码指纹及日志路径。
- [x] `cargo test --locked` 与 `cargo test --locked cch`；不重跑冻结差分研究、不使用真实账号推理。
- [x] 完成 Phase 2.1 Pre-Check，经 trellis-route 执行完整 Check-All 并通过；beta 权威 Spec 已按六节合同更新并验证。
- [x] 用户已确认精确 Push 计划，业务两仓提交／推送完成；当前任务记录按同一计划同步完成态与 Close。

2026-10-29 实施交接：六项 Gateway 专项 175 次出站通过，最终全量 717 通过／3 既有 PG 忽略，CCH 40 通过。实际退出码、覆盖矩阵与源码／独立增量指纹见 [validation.md](./validation.md)。实现子 agent 已停止产品修改，后续完成链交主会话。

## 回滚点

恢复本任务新增的 beta 多值折叠与 URL 归一及其回归即可。R2 功能、count_tokens 既有专用 URL、原生版本画像与账号 1M／Fast 合同不得随本次回滚删除。
