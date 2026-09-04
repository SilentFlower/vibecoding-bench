# 技术设计

## 证据输入

每个样本记录：

```text
run_id
目标模型 / 实际 wire model
claude_code_version
单轮或多轮
终态与异常阶段
capture_index / http_capture / flow 可用性
```

优先使用 bench API 和本地 `data/flows`；如证据只在远程，按部署配置只读拉取到 Git
忽略目录，不在命令输出中展示凭据。

## 分析层次

1. 身份层：CLI 版本、build time、Node/Stainless/Bun、UA。
2. endpoint 层：bootstrap、hello/eval、telemetry、messages、辅助请求。
3. 模型层：Opus、Sonnet、Fable 5/5.1、Haiku。
4. 请求类型层：主请求、probe、title、classifier、继续轮次和非流式辅助请求。
5. 签名层：`cc_version` 文本源、UTF-16 语义、CCH seed 和字节级顶层归一化。

每层与 2.1.257 抓包/画像做结构化对比，不以单个请求代表整个版本。

## 输出

- `research.md`：脱敏事实、样本覆盖、差异矩阵、命中率和不确定项。
- `fixtures/` 或协议子任务中的最小 JSON：只保留复算所需结构和匿名文本。
- cc2api 影响清单：画像常量、request classification、CCH、settings/DB、telemetry、
  bootstrap、测试和部署验证。

## 安全边界

- 任何带 Authorization、Cookie、Token、邮箱或完整会话正文的文件均不得暂存。
- 展示 header 时敏感值统一 `[redacted]`；hash 样本使用人工构造的匿名文本。
- 远程读取为只读，不修改生产 DB、容器或抓包目录。
