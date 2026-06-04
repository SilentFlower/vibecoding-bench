# cc2api Claude Code 2.1.156 设备与运行身份画像优化

## Goal

将 cc2api 当前偏随机 preset 的账号身份指纹升级为“设备画像 + 运行画像”的稳定模型，让 `canonical_env`、system prompt 环境、process 指纹、session id、GrowthBook attributes 和 telemetry env 看起来来自同一台长期使用的真实机器。

## Background / Known Context

- 抓包目录：`/root/project/vibecoding-bench/data/flows/auto-2/1887/46ba25a8d791/`。
- 父任务已将默认 Claude Code 版本指纹升级到 `2.1.156`，并新增 `version_profile.rs`。
- 当前 [identity.rs](/root/project/cc2api/src/model/identity.rs) 通过随机 preset 生成 platform、arch、node version、terminal、package managers、working dir 和 process range。
- 当前 process 指纹主要按范围随机，缺少与 run uptime、session 生命周期、平台环境之间的连续关系。
- 抓包遥测中 env、process、GrowthBook attributes、system prompt 环境和 `/v1/messages` metadata 会共同构成身份画像；单个字段正确不等于整体一致。

## Requirements

- 将账号级稳定字段和运行级动态字段分层建模：
  - 设备画像：platform、arch、node version、terminal、package managers、runtime、build time、device id、account uuid、organization uuid。
  - 运行画像：session id、cwd、shell、process uptime、memory/cpu 曲线、request id、telemetry session。
- 新账号生成的身份字段必须在同一 profile 内保持相关性，例如 linux distro/kernel、terminal/shell、working_dir/home path、node runtime、Stainless headers、telemetry env 不能互相矛盾。
- 旧账号需要有兼容迁移策略：不强制破坏现有账号，但可提供“重生 identity profile”或“补齐缺失字段”的路径。
- process 指纹应从纯随机范围升级为随 uptime 演进的曲线模型，避免每次事件完全无关。
- session 生命周期要能关联 `/v1/messages`、`X-Claude-Code-Session-Id`、`metadata.user_id.session_id`、telemetry session、GrowthBook session。
- system prompt 中的 platform、shell、OS version、working dir 与 telemetry env 和 GrowthBook attributes 保持一致。
- 增加测试覆盖身份生成、旧账号补齐、字段一致性和多次请求的稳定性。

## Acceptance Criteria

- [ ] 有一份身份字段矩阵，列出账号级稳定字段、运行级动态字段、请求级字段，以及它们出现在哪些 endpoint/body 中。
- [ ] 新账号生成的 `canonical_env`、`canonical_prompt_env`、`canonical_process` 字段具有平台内一致性。
- [ ] 同一账号多次请求的设备级字段稳定，运行级字段在同一 run 内连续，跨 run 合理变化。
- [ ] telemetry env、GrowthBook attributes、system prompt 环境和 `/v1/messages` metadata 使用同一身份来源。
- [ ] 旧账号不会被静默改坏；迁移或补齐行为有明确接口或兼容策略。
- [ ] 新增测试覆盖 Linux/macOS/Windows profile、session 生命周期、process 曲线和旧账号 fallback。

## Out of Scope

- 不采集真实用户本机隐私信息。
- 不要求每个字段都与某个真实设备一一对应；目标是内部一致和可解释。
- 不提交抓包原文、账号 profile 原文、token、prompt 或响应体全文。

## Research References

- 抓包目录：`data/flows/auto-2/1887/46ba25a8d791/`
- 父任务：`.trellis/tasks/06-04-cc2api-claude-code-2156-cch-upgrade`
- 目标代码：`/root/project/cc2api/src/model/identity.rs`、`/root/project/cc2api/src/model/account.rs`、`/root/project/cc2api/src/service/rewriter.rs`、`/root/project/cc2api/src/service/telemetry.rs`
