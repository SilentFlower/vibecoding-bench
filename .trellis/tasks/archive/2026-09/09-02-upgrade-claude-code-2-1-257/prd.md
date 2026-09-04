# 升级 cc2api 与 vibecoding-bench 到 Claude Code 2.1.257

## Goal

基于真实 Claude Code 2.1.257 抓包，将 `cc2api` 的默认协议画像和
`vibecoding-bench` 的 worker 运行版本从 2.1.220 升级到 2.1.257，确保请求拟态、
账号迁移、运行时安装和远程部署使用同一版本契约。

## Confirmed Facts

- 用户指定的两份完整抓包位于远端持久化目录，对应 run
  `0c3beffc2f35`（Opus 5）和 `2b9aeab66d11`（Fable 5）。
- 两份抓包的 CLI / HTTP `User-Agent` 均明确为 2.1.257：
  `claude --version`、`claude-cli/2.1.257 (external, cli)` 和
  `claude-code/2.1.257` 相互一致。
- 两份抓包的 telemetry `env.version` / `env.version_base` 均为
  `2.1.257`，`build_time` 均为 `2026-09-01T05:28:54Z`。
- `/v1/messages` 使用 `X-Stainless-Package-Version: 0.112.1`、
  `X-Stainless-Runtime-Version: v26.3.0`；hello / eval 使用 `Bun/1.4.1`。
- `/v1/messages` system 内容中的 billing header 使用
  `cc_version=2.1.257.<suffix>`；已观察到 `9ed`、`aa0`、`e73` 三种后缀，
  `cc_entrypoint=cli`，CCH 长度为 5。
- `capture_index.json` 的 `cc_versions` 为空不是版本错误：当前 recorder 只从
  HTTP header 读取 `x-anthropic-billing-header`，而本次 billing header 位于
  `/v1/messages` system 内容中。
- 当前仓库和远程正式服务的默认画像仍是 2.1.220；当前抓包 worker 已安装并运行
  2.1.257，但这不代表 `cc2api` 已完成 2.1.257 协议适配。
- 用户新增指定 Fable 5.1 抓包 run `9333aa5d1fe3`，模型为
  `claude-fable-5-1`。其 `cc_version` 旧算法 3/3 命中；CCH seed 不变，但 Fable
  5.1 的 `fallbacks: "default"` 必须参与 hash，不能复用 2.1.220 删除 fallbacks 的
  CCH 输入规则。
- 用户明确 `claude-fable-5` 与 `claude-fable-5-1` 是两个并存模型；本次升级分别
  建模并保留两者，不把 5.1 作为 5 的别名或直接覆盖旧 Fable 5 画像。
- 用户补充 Fable 5.1 多轮抓包 run `724f47b5673c`。原始 `.flow` 中 4 条 Fable
  5.1 请求的 `cc_version` / CCH 均命中；前两条完整成功，第三轮请求及其重试均在
  收到 HTTP 200 headers 后约 180.7 秒保持 0 SSE bytes，最终由 Claude Code 在
  184 秒超时并生成 `API Error: No response from API`。
- 该 no-response 不是 beta/CCH/HTTP 状态错误，而是上游接受请求后没有发送首个 SSE
  chunk。线上 cc2api 的 120 秒上游 idle timeout 会更早关闭同类零首字节流，且
  keepalive 在首个真实 chunk 前不会注入。
- 用户补充 Haiku 抓包 run `ea6d8e9bb665`，55 条 `/v1/messages` 均为
  `claude-haiku-4-5-20251001`。54 条带 billing 的请求中，现有 `cc_version`
  SHA256 文本位置算法 54/54 命中；CCH seed 仍为 `0x4D659218E32A3268`，将
  顶层 `model` 置空并删除 `max_tokens` 后 54/54 命中。
- Haiku probe 和结构化 title 的 beta 常量未变化，但 2.1.257 title prompt 不再
  命中当前字符串检测；Haiku 主请求和 `max_tokens=1024` 非流式辅助请求各自使用
  与当前通用非 Fable beta 不同的子画像。
- 用户确认 run `86926719c1ee` 由 Fable 5.1 `[1m]` 入口发起。直连官方链路的启动
  telemetry 先记录 `claude-opus-5[1m]` 和 `context-1m`，随后模型解析为
  `claude-fable-5-1`，实际 bootstrap、telemetry 和 message 请求均不再携带
  `context-1m-2025-08-07`。这不是 cc2api 剥离，而是 Claude Code 2.1.257 的
  可观察行为。
- 同一抓包再次复现 Fable 5.1 首字节卡死：两条主请求成功，后续请求约 184 秒无
  response 后重试，重试到抓包结束仍无 response；成功与失败请求使用同一套无 1M
  的 Fable 5.1 画像。

## Requirements

- 以真实抓包为准新增 2.1.257 版本画像，不通过替换常量猜测 wire 行为。
- 同步核对并实现 identity、User-Agent、Stainless runtime、Bun UA、
  `cc_version`、CCH、beta 顺序、请求体字段顺序、bootstrap 和 telemetry 差异。
- 保留现有回滚画像，并将旧默认 2.1.220 settings / account canonical env 安全迁移到
  2.1.257；管理员自定义 allowed range 时不得擅自覆盖。
- 将 `vibecoding-bench` 的 Dockerfile、Compose、orchestrator 兜底值、WebUI 文案、
  示例配置和部署规范同步为 2.1.257。
- 原始抓包仅用于本地或远端只读分析，不提交完整 JSONL、`.flow` 或任何敏感内容。
- 远程发布必须在镜像构建完成且 established 连接处于低位后执行；部署后核验服务、
  镜像摘要、账号版本分布和错误日志。
- 分别支持 Fable 5 与 Fable 5.1：同步模型识别、system role 白名单、独立 beta、
  thinking display、不同 fallback 结构、CCH 输入、bootstrap option/cwk/cedar 和
  Fable family quota 判断，保留 2.1.220 Fable 5 回滚画像。
- 迁移线上 `allow_system_role_models` 时追加 `claude-fable-5-1`，不得覆盖已有
  `claude-sonnet-5` 等管理员自定义模型。
- Fable 5.1 必须进入 `seven_day_fable` 共用配额的选号、sticky fallback 和模型级
  429 换号逻辑；disabled-thinking 等只适用于旧 Fable 5 的兼容规则不得自动外扩。
- no-response 故障必须保留可观测的 upstream request ID、首字节等待和 idle timeout
  日志，不通过伪造 SSE 首 chunk 或无限延长超时掩盖上游卡死。
- 为 2.1.257 增加 Haiku 请求子画像：保留 probe/title beta 常量，使用
  `output_config` JSON schema 等稳定结构识别新 title 请求，并为主请求和
  `max_tokens=1024` 非流式辅助请求配置各自的 beta。
- CCH 归一化不能仅按版本统一删除 `fallbacks`；同为 2.1.257 时，Haiku 与
  Fable 5.1 必须依据真实请求结构采用不同输入规则。
- 不为 Fable 5.1 自动注入 `context-1m-2025-08-07`，也不迁移账号
  `allow_1m_models`；bootstrap 中出现 `[1m]` 选项不等于 message wire profile 必须
  携带 1M beta。

## Task Breakdown

1. `09-02-cc2api-claude-code-2-1-257-protocol`
   - 基于真实抓包完成 cc2api 2.1.257 identity、请求子画像、CCH、模型限制、迁移与
     首字节超时可观测性。
2. `09-02-vibecoding-bench-claude-code-2-1-257-runtime`
   - 同步 worker、orchestrator、Compose、WebUI、示例配置、测试和部署文档的默认
     Claude Code 版本。
3. `09-02-deploy-claude-code-2-1-257`
   - 仅在前两个子任务实现和检查完成后，构建发布镜像、迁移线上服务并完成验收。
4. `09-02-cc2api-cli-bg-status-classifier`
   - 识别 2.1.257 `cli-bg` Agent 状态分类请求，提供默认放行/可切模拟的全局模式；
     放行时保留账号代理链路并绕过会触发 429 的正文形状改写，部署后经 cc2api 验收。

前两个实现子任务可以独立推进；发布子任务依赖两者均通过 Check-All。父任务只负责
跨子任务契约、依赖顺序和最终集成验收，不直接承载业务代码修改。

## Acceptance Criteria

- [ ] `cc2api` 默认 profile、allowed range、账号 canonical env 和所有版本相关 UA
      均为 2.1.257，旧回滚 profile 仍可用。
- [ ] Opus、Fable 5/Fable 5.1 和 2.1.257 Haiku 的 probe、title、主请求、非流式
      辅助请求抓包，其 `cc_version` 后缀与 CCH 可由各自版本画像全量复算命中，
      旧 profile 行为不回归。
- [ ] Haiku 2.1.257 的四类请求均发送抓包对应 beta；新结构化 title 能在不依赖
      prompt 原文的情况下被识别，旧 title 检测仍兼容。
- [ ] `/v1/messages` 的 beta、模型、fallback、顶层字段顺序、bootstrap 和 telemetry
      与 2.1.257 抓包一致。
- [ ] Fable 5 与 Fable 5.1 使用各自画像；5.1 system-role 请求不被本地 400 拒绝，
      并进入共用 Fable 周用量保护和模型级 429 换号逻辑。
- [ ] Fable 5.1 上游返回 200 但首个 SSE chunk 超时时，日志可关联 request ID、
      已收 chunk 数和超时原因，且不会错误归因于 CCH 或 beta。
- [ ] `vibecoding-bench` 新建普通 run、抓包 run、OAuth / quota worker 均默认运行
      Claude Code 2.1.257，页面覆盖值仍按原优先级生效。
- [ ] `cc2api` 通过 `cargo fmt --check`、`cargo test`、`cargo test cch`；
      `vibecoding-bench` 通过相关 Python 测试及前端/容器配置校验。
- [ ] 远程部署后 HTTP 健康检查通过，DB 版本分布迁移到 2.1.257，且最近日志无新增
      协议或迁移错误。
- [ ] 四个子任务均完成各自验收，父任务核对 cc2api 默认画像、worker 实际版本和线上
      运行配置均指向 2.1.257，且 `[1m]` 账号策略未被改动。
- [ ] `cli-bg` 状态分类子任务默认保持真实上游放行，经 cc2api 和账号 `proxy_url`
      验证不再因通用正文改写集中返回 429；本地模拟只作为显式可切换的降级模式。

## Out of Scope

- 不修改或提交原始抓包中的账号、Token、Cookie、Authorization、邮箱、prompt 或响应正文。
- 不在规划阶段构建、推送镜像或重启远程服务。
- 不保证 Anthropic Fable 5.1 上游始终可用，也不通过伪造响应消除官方上游的零首字节
  卡死；本次只保证协议画像、超时处理和诊断信息正确。
- 不自动开放 Fable 5 / Fable 5.1 `[1m]`，不修改现有账号的
  `allow_1m_models`。后续若新抓包证明官方 message 请求实际携带 1M beta，再单独建
  任务评估放行与迁移。
