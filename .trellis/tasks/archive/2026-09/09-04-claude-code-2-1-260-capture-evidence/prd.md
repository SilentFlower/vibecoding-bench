# 采集 Claude Code 2.1.260 协议证据

## Goal

在 bench 生产环境全量升级到 Claude Code 2.1.260 后，接收用户提供的各模型 run ID，
对原始会话进行只读、脱敏、可复算的协议分析，为 cc2api 2.1.260 画像实现提供唯一
事实来源。

## Requirements

- 用户为每份证据提供 run ID、目标模型和单轮/多轮说明；抓包 API 中的
  `claude_code_version` 必须为 2.1.260。
- 最低矩阵覆盖 Opus、Sonnet、Fable 5.1、Haiku；如果实际请求仍出现 Fable 5，则
  追加独立样本。至少一份复杂模型会话覆盖多轮继续。
- 分开统计 bootstrap、hello/eval、telemetry、`/v1/messages` 和后台辅助请求，不把
  不同 endpoint 的 header/body 画像混合。
- 对每个请求族核对版本、build time、User-Agent、Stainless、Bun、beta 顺序、顶层
  JSON 字段顺序、model、max_tokens、fallback、thinking、diagnostics 和响应形态。
- 用脱敏最小样本复算 `cc_version` 后缀和 CCH；先验证 2.1.257 算法/seed/归一化是否
  继续命中，不命中时基于多条样本定位变化，禁止按版本号猜测。
- 对比 2.1.257 基线，输出“保持不变、确认变化、证据不足”三类结论，以及对应 cc2api
  代码/测试影响清单。
- 原始 `.flow`、完整 JSONL、Token、Cookie、Authorization、邮箱、prompt 和响应正文
  不进入 Git；任务只保存脱敏统计、hash 结论、字段形态和最小 fixture。

## Acceptance Criteria

- [ ] 所有约定模型都有可定位的 2.1.260 run ID、版本快照和抓包完整性结论。
- [ ] 每个已观察请求族都有 endpoint、UA/header、beta、body、bootstrap/telemetry 和
      响应差异摘要。
- [ ] `cc_version` 与 CCH 对所有带签名样本给出命中率、算法输入和归一化规则；失败样本
      有明确分类，不能只记录单个值。
- [ ] 形成 cc2api 实施清单和脱敏测试 fixture，足以规划协议子任务且不依赖原始敏感
      抓包在 CI 中存在。
- [ ] Git 状态确认没有原始抓包或凭据文件。

## Out of Scope

- 不修改 cc2api 或 bench 业务代码。
- 不把上游偶发 429、5xx 或零首字节故障自动归因于协议画像；需保留 request ID 和阶段
  证据后单独分类。
- 不要求用户公开完整会话内容。
