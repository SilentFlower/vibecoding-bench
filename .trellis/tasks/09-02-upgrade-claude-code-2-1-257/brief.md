# Brief — 升级 cc2api 与 vibecoding-bench 到 Claude Code 2.1.257

## Goal

- 基于真实 Claude Code 2.1.257 抓包，将 cc2api 协议画像、账号迁移、
  vibecoding-bench worker 运行版本和远程部署统一到同一版本契约。

## Scope

- cc2api 实现 2.1.257 identity、Opus、Fable 5、Fable 5.1 和 Haiku 请求子画像。
- 对齐 CCH、`cc_version`、beta、fallback、thinking、请求体字段顺序、bootstrap 和
  telemetry。
- Fable 5.1 加入 system-role 白名单、共享 Fable 周配额和模型级 429 换号逻辑。
- 区分零首字节超时与首 chunk 后 idle timeout，并保留 upstream request ID 诊断信息。
- vibecoding-bench 同步 worker、orchestrator、Compose、WebUI、示例配置和部署规范的
  默认 Claude Code 版本。
- 完成正式镜像发布、生产迁移、备份、健康验证和联合回滚核对。
- 识别 2.1.257 `cli-bg` 状态分类请求，默认真实上游放行，并保留显式可切换的本地模拟
  降级模式。
- 父任务只维护跨子任务契约、依赖顺序和最终集成验收，不直接承载业务代码修改。

## Non-Goals

- 不自动开放 Fable 5 或 Fable 5.1 `[1m]`，不迁移账号 `allow_1m_models`。
- 不伪造 SSE、不无限延长超时，也不保证 Anthropic Fable 5.1 上游始终可用。
- 不提交完整抓包、prompt、响应正文、账号、Token、Cookie 或远程凭据。
- 不把 Fable 5.1 作为 Fable 5 的别名，也不把同版本所有模型强行合并为单一 wire
  profile。

## Key Decisions

- Fable 5 与 Fable 5.1 分别建模；配额 family 共享，但 beta、fallback、thinking 和
  CCH 输入不能混用。
- 2.1.257 CCH 继续使用既有 seed；Fable 5.1 的 `fallbacks="default"` 必须参与 hash，
  Haiku 则按其真实请求结构归一化。
- Haiku 按 probe、结构化 title、主请求和 `max_tokens=1024` 非流式辅助请求选择独立
  子画像。
- Fable 5.1 `[1m]` 入口的官方 message 请求未携带 `context-1m-2025-08-07`，网关本轮
  不主动注入。
- system-role 迁移采用追加策略，保留管理员自定义模型；账号 1M allowlist 保持原值。
- `cli-bg` 默认放行真实上游，仅绕过会改变强特征请求正文形状的改写；账号 OAuth、
  header、代理、TLS 和重试链路保持原路径。
- 发布顺序固定为先验证并升级 cc2api，再部署匹配版本的 vibecoding-bench，回滚时按
  相反兼容顺序恢复。

## Key Context

- 核心抓包包括 Fable 5.1 run `9333aa5d1fe3`、`724f47b5673c`、`86926719c1ee`，
  Haiku run `ea6d8e9bb665`。
- Fable 5.1 成功与零首字节失败请求使用相同 beta/CCH，no-response 不能归因于 CCH、
  beta 或 HTTP 状态错误。
- 四个子任务分别负责 cc2api 协议、vibecoding-bench 运行时、正式部署验证和 `cli-bg`
  状态分类兼容。
- 生产发布必须使用 GitHub Actions/GHCR 正式镜像，并在低连接窗口完成数据库备份、
  Compose 校验和容器重建。

## Risks / Deferred

- 同一版本存在模型级 CCH 与 beta 差异，后续新增请求类型仍需以真实抓包核对。
- Anthropic 上游零首字节卡死无法由本项目消除，本项目只保证超时收口和诊断正确。
- Fable `[1m]` 后续若重新携带 1M beta，需要新抓包和独立任务评估，不在本次升级中
  推断放行。
- `/v1/code/sessions` 等新增端点是否经过自定义 base URL 尚未确认，本次不扩展其转发
  画像。

## Acceptance

- cc2api 默认 profile、allowed range、账号 canonical env、UA 和设置页统一为
  2.1.257，并保留旧版本回滚画像。
- Opus、Fable 5、Fable 5.1 和 Haiku 各类请求的 `cc_version`、CCH、beta、fallback 和
  请求结构与真实抓包一致。
- Fable 5.1 system role、共享配额和模型级 429 换号正确，零首字节超时日志可关联
  request ID。
- vibecoding-bench 所有 worker 类型默认运行 2.1.257，页面覆盖优先级保持不变。
- `cli-bg` 默认真实放行，经账号代理链路验证不再因通用正文改写集中返回 429。
- 正式镜像、生产健康、数据库版本分布、账号 1M 策略、日志和联合回滚路径均完成核验。
- 四个子任务均完成各自验收，父任务最终确认所有运行配置指向 2.1.257，且
  `allow_1m_models` 未被改动。

## Next Step

- 核对四个子任务完成状态和最终生产证据，完成父任务集成收口并进入提交、归档流程。
