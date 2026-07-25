# 升级 cc2api 至 Claude Code 2.1.220

## Goal

基于 Opus 5 与重新抓取的 Fable 5 真实流量，将 `cc2api/` 的默认 Claude Code 协议画像升级到 `2.1.220`，同时保留旧画像可回滚能力，确保请求 header/body、billing、bootstrap、telemetry、全局设置和账号 canonical env 不混用旧版本指纹。

## Background

- 目标抓包已同步到本地 gitignored 目录：Opus 5 为 `data/flows/7-24/7788/1512e30eb37c`，Fable 5 为 `data/flows/7-24/7790/a0f3cfd653ea`；旧 Fable run `caa28dcdb85f` 不再作为实现依据。
- `2.1.220` 身份画像为 `version=2.1.220`、`version_base=2.1.220`、`build_time=2026-07-24T22:17:45Z`、Node `v26.3.0`、Stainless package `0.94.0`、GrowthBook UA `Bun/1.4.0`。
- Opus 5 主请求使用 `claude-opus-5`，通用 beta 在原有集合中新增 `fallback-credit-2026-06-01`；允许 1M 时 `context-1m-2025-08-07` 仍位于 `oauth-2025-04-20` 之后。
- 新 Fable 抓包的 15 条主请求均使用 `claude-fable-5`，fallback 为 `[{"model":"claude-opus-5"}]`，beta 同时包含 `server-side-fallback-2026-06-01` 与 `fallback-credit-2026-06-01`，不包含 `context-1m-2025-08-07`。
- Opus 5 和 Fable 5 主请求均出现 `messages[].role=system`。当前全局默认仅允许 `claude-opus-4-8`，升级后会导致新模型在账号选择前被本地拒绝。
- Fable 主请求稳定字段顺序为 `model,messages,system,tools,metadata,max_tokens,thinking,context_management,fallbacks,output_config,diagnostics,stream`，其中 `diagnostics` 可缺省。
- Opus 与新 Fable 原始 `.flow` 中共 69 个 billing 样本：`cc_version` 后缀 69/69 命中现有 UTF-16 SHA-256 算法；CCH 69/69 命中 seed `0x4D659218E32A3268` 和现有 2172+ top-level 规范化规则。
- Bootstrap configured 画像中，Fable query 使用 `cwk_cfg_key=marigold`，Opus 5 query 使用 `cwk_cfg_key=belladonna`；两者都包含 `client_data.cedar_basin="2026-08-31"` 和现有 Fable model options。
- `HEAD /api/hello` 是 Claude Code 启动时的无鉴权连通性预检，真实服务返回 200；当前 cc2api fallback 会先要求网关 token，可能返回 401。
- 本地运行 2.1.220 并将 `ANTHROPIC_BASE_URL` 指向脱敏探针后确认：`/v1/messages` 会进入配置入口，但 hello 固定请求 `https://api.anthropic.com/api/hello`，不会经过 `new-api`。cc2api 仍保留同名端点以覆盖直接访问和健康检查场景。
- `2.1.220` 原生 telemetry 的顶层字段和 env 字段集合与现有 `ClaudeCode2185` shape 一致，无需新增 wire shape；但自动 telemetry 的基础 beta 和启动模型仍使用全局旧常量。

## Requirements

1. 在 `version_profile` 中新增并启用 `2.1.220` 内置画像，默认允许范围更新为 `2.1.89-2.1.220`；保留 `2.1.197` 及更早画像作为显式回滚选项。
2. 所有会生成 Claude Code 请求或遥测的路径必须读取账号选中的版本画像，不得继续依赖“当前默认版本”的全局 beta、fallback、runtime 或模型常量；旧画像切换后必须恢复旧指纹。
3. `2.1.220` Opus 5 通用 beta 必须新增 `fallback-credit-2026-06-01`；Fable beta、1M 过滤和 token 顺序必须与抓包一致。
4. 全局 `allow_system_role_models` 默认值更新为 `claude-opus-5,claude-fable-5,claude-opus-4-8`；assistant prefill 默认模型列表加入 `claude-opus-5`。迁移只升级仍等于旧默认值的设置，不覆盖管理员自定义。
5. Fable fallback、API 默认 `max_tokens` 和 body 字段顺序必须对齐 `2.1.220`；旧画像仍使用旧 fallback 模型和旧 body 指纹。
6. 将 `2.1.220` 接入现有 `cc_version` 与 CCH 版本分支。不得修改已由 69 个样本验证的算法、seed 或 top-level 规范化语义。
7. Bootstrap passthrough 模式保持原响应；configured 模式按版本和 query model 注入 `cedar_basin`、Fable options、`marigold` 或 `belladonna`；hide_fable 模式继续隐藏 Fable，但不得误清除 Opus 5 的合法 `belladonna`。
8. 增加公开的 `GET/HEAD /api/hello`，无需网关 token即可返回 200；GET body 语义与真实服务 `{"message": "hello"}` 一致，且不进入账号选择、RPM、并发或上游转发。
9. 原生 telemetry 转发继续保留 `skill_name` 等客户端字段；自动 telemetry 使用版本画像的 identity、默认模型和 beta，请求 query/success 事件继续使用最终重写 header。不得因 Fable 模型无条件伪造 `flags=model` 或客户端本地 skill 事件。
10. 启动迁移将旧默认 `2.1.197` profile 与旧默认 allowed range 成对升级到 `2.1.220`，并同步已有账号 canonical env；显式回滚或自定义 allowed range 保持不变。
11. `cc2api` Settings 页面内置 fallback profile、默认值和说明同步到 `2.1.220`；`vibecoding-bench` worker、compose、orchestrator、WebUI 和 README 的兜底 Claude Code 版本同步到 `2.1.220`。
12. 不提交完整抓包、Authorization、Cookie、账号标识、完整 prompt 或响应正文；测试只使用脱敏最小 fixture。
13. 当前不得为 `new-api` 臆造 `/api/hello` 路由、渠道选择或故障转移规则；只有后续客户端开始让 hello 使用 `ANTHROPIC_BASE_URL` 时才重新评估。

## Acceptance Criteria

- [ ] 默认 profile、UA、canonical env、build time、allowed range 和 Settings 回显均为 `2.1.220`，旧内置 profile 仍可选择。
- [ ] Opus 5、Fable 5、Haiku 探测请求的 beta、runtime header、max tokens、fallback 和字段顺序都有定向测试，旧 profile 回滚测试证明不会混用 `2.1.220` 常量。
- [ ] `cc_version` 的 2.1.220 多 text block 测试命中；CCH 2.1.220 测试覆盖 Opus/Fable、`diagnostics` 保留和嵌套同名字段不被裁剪。
- [ ] 旧默认 settings 组合、`allow_system_role_models` 和 assistant prefill 模型列表按精确旧值迁移；管理员自定义值不被覆盖。
- [ ] configured bootstrap 分别覆盖 Fable `marigold`、Opus 5 `belladonna`、`cedar_basin` 和 hide_fable 行为；gzip response 回归保持通过。
- [ ] 未携带 token 的 `GET/HEAD /api/hello` 返回 200，其他 fallback 路由仍执行原有 token 鉴权。
- [ ] 本地 2.1.220 探针证明 `/v1/messages` 使用 `ANTHROPIC_BASE_URL`、hello 固定访问官方域名；`new-api` 业务代码保持零 diff。
- [ ] 原生 telemetry 结构回归通过，自动 telemetry 输出 2.1.220 identity 和版本化 beta，且不自动生成 Fable CLI flag。
- [ ] `cd cc2api && cargo fmt --check`、`cargo test`、`cargo test cch` 通过。
- [ ] `cd cc2api/web && npm run build` 通过；根仓相关 Python 测试和 compose 配置检查通过。

## Out Of Scope

- 本任务不部署远程 cc2api，不修改远程数据库或环境变量；部署和 DB 分布验证在代码合入后单独执行。
- 不追求完整复制 Claude Code 所有客户端本地 telemetry 事件，只保证转发不丢字段和自动合成事件不使用错误版本画像。
- 不新增任意版本字符串画像；版本仍只允许代码内置、抓包验证的 profile key。
- 不把 `/api/hello` 设计成无鉴权通用 relay，也不为预检请求新增渠道 ID、模型或远程地址配置。
