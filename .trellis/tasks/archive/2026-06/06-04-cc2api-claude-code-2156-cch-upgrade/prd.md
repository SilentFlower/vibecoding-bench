# cc2api Claude Code 2.1.156 兼容升级与 CCH 逆向

## Goal

基于 vibecoding-bench 已捕获的 Claude Code `2.1.156` 完整 HTTP 抓包，规划并实施 `/root/project/cc2api` 的版本兼容升级，重点覆盖新版遥测、请求头、请求体 schema、GrowthBook eval 属性，以及 `cc_version` 后缀和 `cch` 的真实计算机制。

## Background / Known Context

- 抓包 run：`46ba25a8d791`。
- 本地抓包目录：`/root/project/vibecoding-bench/data/flows/auto-2/1887/46ba25a8d791/`。
- 抓包文件包括 `http_capture.jsonl`、`capture_index.json`、`stats.jsonl`、`20260604-024430.flow`。
- 远端 worker 使用 Dockerfile 中的 `npm install -g @anthropic-ai/claude-code@2.1.156` 安装 Claude Code。
- 远端容器运行时 `CLAUDE_CODE_VERSION=2.1.156`。
- 抓包中 `2.1.156` npm 版 Claude Code 已经发送非零 `cch`，不是默认 `00000`。
- 抓包中出现的 billing 行形态：`x-anthropic-billing-header: cc_version=2.1.156.<suffix>; cc_entrypoint=cli; cch=<5hex>;`。
- 抓包中 `cc_version` 后缀出现 `b94` 和 `b2a`；`cch` 每次请求不同。
- 初步用 cc2api 当前算法反算抓包里的 `cc_version` 后缀和 `cch`，全部未匹配，说明 2.1.156 的 CCH/cc_version 机制与当前实现不兼容。
- 规划期浅尝研究已记录在 `research/cch-cc-version-first-pass.md`：旧 salt、`cch=00000`、billing 模板和 `xxHash64` 字符串仍存在于 2.1.156 native binary，但抓包复现失败，优先怀疑 hash 输入/canonicalization/调用时机改变。
- `/root/project/cc2api` 当前默认身份版本多处仍是 `2.1.81`。
- `/root/project/cc2api` 当前自动遥测代发目标是 `/api/event_logging/batch`，抓包中真实目标是 `/api/event_logging/v2/batch`。
- 抓包显示 2.1.156 的出站 headers 有版本漂移：`/v1/messages` 使用 `X-Stainless-Package-Version=0.94.0`、`X-Stainless-Runtime-Version=v24.3.0`、`User-Agent=claude-cli/2.1.156 (external, cli)`；cc2api 当前 API 模式仍生成 `0.70.0` 和旧版本指纹。
- 抓包显示 headers 需要按 endpoint 区分：`/api/event_logging/v2/batch` 使用 `User-Agent=claude-code/2.1.156`、`anthropic-beta=oauth-2025-04-20`、`x-service-name=claude-code`；`/v1/code/triggers` 额外使用 `anthropic-client-platform=claude_code_cli`、`x-organization-uuid` 和 `ccr-triggers-2026-01-30` beta；`/v1/mcp_servers` 使用 `mcp-servers-2025-12-04` beta。
- 抓包中本次未出现 Datadog host 或 WebSocket upgrade；所有 HTTP flow host 都是 `api.anthropic.com`。

## Requirements

- 升级 cc2api 的 Claude Code 默认版本指纹到 `2.1.156`，包括 `version`、`version_base`、`build_time` 和相关 UA fallback。
- 兼容 `/api/event_logging/v2/batch`，明确旧 `/api/event_logging/batch` 与新 v2 的拦截、改写和代发策略。
- 更新请求头传递/生成策略，按 endpoint 建立 2.1.156 header profile，覆盖 UA、`anthropic-beta`、`anthropic-version`、`anthropic-dangerous-direct-browser-access`、`x-app`、`X-Stainless-*`、`x-service-name`、`anthropic-client-platform`、`x-organization-uuid`、`x-client-request-id`、`X-Claude-Code-Session-Id` 等字段。
- 更新 `/v1/messages` 的 `anthropic-beta` 策略，覆盖 2.1.156 抓包中出现的新版 beta token，并同步 `X-Stainless-Package-Version=0.94.0`、`X-Stainless-Runtime-Version=v24.3.0`。
- 保留或正确生成 2.1.156 请求体中的新版字段：`context_management`、`diagnostics`、`output_config`、`thinking`、新版工具名等。
- 补齐 GrowthBook eval 属性：`userType`、`rateLimitTier`、`entrypoint` 等抓包中存在但 cc2api 当前缺失的字段。
- 梳理启动和配置接口的兼容策略：`/api/claude_cli/bootstrap`、`/api/claude_code_grove`、`/api/claude_code_penguin_mode`、`/v1/code/triggers`、`/v1/mcp_servers`、`/mcp-registry/v0/servers`。
- 逆向 `cc_version` 后缀和 `cch` 的真实计算方式，至少给出可复现的测试样本和算法判断。
- CCH/cc_version 逆向优先级高于常规兼容改造；实现前应先完成至少一轮 controlled capture 或 binary 定位，避免在 cc2api 中固化错误算法。
- 在算法未确认前，必须提供保守策略：真实 Claude Code 客户端请求优先透传/保留其原始 billing 行；API 注入模式不得伪造错误的 2.1.156 CCH。

## Acceptance Criteria

- [ ] 有一份基于 `46ba25a8d791` 抓包的结构化分析记录，列出端点、headers、body schema、事件名、版本字段和 CCH 样本。
- [ ] cc2api 对 2.1.156 的版本指纹和 UA fallback 不再默认落到 `2.1.81`。
- [ ] cc2api 能识别并处理 `/api/event_logging/v2/batch`，不会只兼容旧 `/api/event_logging/batch`。
- [ ] cc2api 的 endpoint header profile 与抓包样本一致，至少覆盖 `/v1/messages`、`/api/event_logging/v2/batch`、`/api/eval/*`、`/v1/code/triggers`、`/v1/mcp_servers` 和启动/配置接口。
- [ ] cc2api 的新版 beta token 策略与抓包样本一致，且 1M context 白名单策略仍可控。
- [ ] GrowthBook eval 生成或改写逻辑覆盖抓包中的关键 attributes。
- [ ] CCH/cc_version 逆向至少达到以下之一：
  - 能用算法复现抓包中 `cc_version` 后缀和 `cch`；
  - 或明确证明当前样本不足，并产出下一轮抓包矩阵和临时安全策略。
- [ ] 新增单元测试或离线 fixture 测试，覆盖 CCH/cc_version、event_logging v2、endpoint header profile、beta header 和 GrowthBook 属性。
- [ ] README 或内部文档更新，说明 2.1.156 兼容策略和 CCH 未知项。

## Out of Scope

- 不在本任务中处理账号滥用、封号绕过或规避平台风控的运营策略。
- 不提交抓包原文、OAuth token、prompt、响应体或其他敏感数据到 git。
- 不要求一次性实现 Datadog/WebSocket 兼容；本次抓包未捕获到相关样本，后续用新抓包任务补充。

## Research References

- 抓包目录：`data/flows/auto-2/1887/46ba25a8d791/`
- cc2api 代码目录：`/root/project/cc2api`
- vibecoding-bench 抓包任务：`.trellis/tasks/06-04-claude-code-mitm-full-capture`
