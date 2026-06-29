# cc2api 2.1.195 指纹升级与抓包分析

## 目标

将 `cc2api` 的 Claude Code 版本画像从 `2.1.187` 升级到真实抓包验证过的 `2.1.195`，重点对齐近期封号风险相关的 wire 指纹：User-Agent、Stainless runtime、`cc_version`、CCH、beta 顺序、bootstrap、telemetry env 和账号 canonical env 迁移。

## 背景

- 用户要求先从远程服务器拉取抓包 `23594999fa77`，再准备 `cc2api` 的 `2.1.195` 升级。
- 近期封号较严重，不能只改版本号；必须以真实抓包为依据，逐项确认是否有未对齐指纹。
- 原始抓包已拉取到任务本地 `evidence/` 目录，并通过任务内 `.gitignore` 排除，禁止提交原始 `http_capture.jsonl`、`.flow`、token、Cookie、邮箱、账号 UUID、完整 prompt 或响应正文。
- 脱敏摘要见 `research/run-23594999fa77-summary.md`。

## 已确认事实

- 抓包来源：远程 `/root/vibecoding-bench/data/flows/6-23/4638/23594999fa77/`。
- 抓包包含 86 个 flow，其中 `/v1/messages` 31 条，`/api/event_logging/v2/batch` 43 批。
- `2.1.195` 的 `/v1/messages` 使用 `claude-cli/2.1.195 (external, cli)`。
- `X-Stainless-Package-Version` 仍为 `0.94.0`。
- `X-Stainless-Runtime-Version` 从当前代码的 `v24.3.0` 变为 `v26.3.0`。
- telemetry env 中 `version/version_base` 为 `2.1.195`，`build_time` 为 `2026-06-26T01:00:56Z`，`node_version` 为 `v26.3.0`。
- `cc_version` 后缀算法对 30 条带 billing 的请求全部复算命中。
- CCH 对 30 条带 billing 的请求全部命中现有 `2.1.172+` top-level 规范化规则和 seed `0x4D659218E32A3268`。
- message beta、Haiku beta、MCP capability、MCP protocol、code triggers beta、event logging path 未发现变化。
- bootstrap response 顶层结构与现有处理路径兼容，仍需保留 gzip/长度 header 安全处理。

## 需求

- 新增内置 Claude Code profile `2.1.195`，并将默认 profile 切到 `2.1.195`。
- 将 `allowed_claude_code_versions` 默认上限扩展到 `2.1.195`。
- 将默认身份画像对齐 `version=2.1.195`、`version_base=2.1.195`、`build_time=2026-06-26T01:00:56Z`。
- 将请求和 OAuth token test 使用的 Stainless runtime version 对齐 `v26.3.0`。
- 将 CCH 版本白名单扩展到 `2.1.195`，保持现有 `2.1.172+` 规范化规则。
- 确保 settings 切换、DB 启动迁移、新账号创建、已有账号 canonical env 更新、前端 Settings profile 列表全部包含 `2.1.195`。
- 保留 `2.1.187` / `2.1.185` / `2.1.173` 作为可回滚 profile。
- 补充或更新单测覆盖 profile registry、settings 迁移、CCH seed/输入、`cc_version`、request headers、telemetry env。
- 运行必要质量检查：`cargo fmt --check`、`cargo test`、`cargo test cch`；如改前端 Settings，运行 `npm run build`。

## 非目标

- 不逆向或更改 TLS 指纹链路，除非实现时发现 HTTP 层全部对齐仍存在明确 TLS 证据缺口。
- 不提交原始抓包或任何高敏流量正文。
- 不调整账号调度、限流策略、封号恢复策略。
- 不在本任务中执行生产部署；部署和远程 DB 验收作为实现后的后续步骤或独立确认动作。

## 验收标准

- [ ] `cc2api` 默认 Claude Code profile 为 `2.1.195`。
- [ ] `/v1/messages` 画像输出对齐抓包中的 UA、Stainless package/runtime、beta、billing 与 CCH 规则。
- [ ] `cc_version` 对脱敏样本中的 Haiku / Opus 文本源复算结果与抓包一致。
- [ ] CCH 对 2.1.195 使用 `2.1.172+` 规范化规则，测试覆盖 `2.1.195`。
- [ ] settings 切换到 `2.1.195` 会同步覆盖 `allowed_claude_code_versions` 和所有账号 canonical env 的 `version/version_base/build_time`。
- [ ] 前端 Settings 可展示并选择 `2.1.195`，保存后重新加载显示后端强制覆盖的版本范围。
- [ ] 原有 `2.1.187` profile 可作为回滚选项保留。
- [ ] 质量检查通过，或明确记录未能运行的命令和原因。
