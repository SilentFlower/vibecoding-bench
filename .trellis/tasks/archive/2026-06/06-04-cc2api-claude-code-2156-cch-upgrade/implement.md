# cc2api Claude Code 2.1.156 兼容升级与 CCH 逆向实施计划

## Implementation Checklist

- [x] 固化抓包分析脚本或记录，输出端点、headers、body schema、事件名、版本字段、CCH 样本，不输出敏感正文。
- [x] 优先完成 CCH/cc_version controlled capture 或 binary 定位，判断 `b94`/`b2a` 后缀和 5 位 `cch` 的输入来源。
- [x] 建立 CCH/cc_version fixture 测试，验证旧算法对 2.1.156 抓包不匹配，并用于后续候选算法回归。
- [x] 在 `/root/project/cc2api` 中梳理现有版本常量和身份 profile，移除散落的 `2.1.81` fallback。
- [x] 设计并实现 Claude Code 版本 profile，新增 `2.1.156` profile。
- [x] 设计并实现 endpoint header profile，覆盖 `/v1/messages`、`/api/event_logging/v2/batch`、`/api/eval/*`、`/v1/code/triggers`、`/v1/mcp_servers` 和启动/配置接口。
- [x] 将 `/v1/messages` 的 `X-Stainless-Package-Version` 从当前 `0.70.0` 升级为抓包中的 `0.94.0`，并同步 runtime/node 版本指纹。
- [x] 升级 `/v1/messages` beta header 策略，覆盖抓包中 2.1.156 token。
- [x] 兼容 `/api/event_logging/v2/batch` 的拦截、改写和自动代发路径。
- [~] 扩展自动遥测事件模板，至少覆盖启动、API 成功、工具、技能、MCP、feature flag 类关键事件。
- [x] 补齐 GrowthBook eval attributes：`userType`、`rateLimitTier`、`entrypoint`。
- [x] 梳理并实现启动/配置接口的透传或伪响应策略。
- [x] 逆向 2.1.156 的 `cc_version` 后缀和 `cch` 算法；若无法复现，落地保守策略并记录下一轮抓包矩阵。
- [x] 更新 cc2api README 或内部文档，说明 2.1.156 兼容范围和 CCH 状态。

## Validation

- 在 `/root/project/cc2api` 运行 Rust 单元测试：
  - `cargo test`
- 针对 fixture 增加专项测试：
  - event_logging v2 path 识别和 payload 改写
  - endpoint header profile 生成和透传策略
  - beta header 生成
  - GrowthBook attributes
  - CCH/cc_version 版本策略
- 如有本地网关环境，使用抓包 fixture 或模拟请求验证不会泄露 token/prompt 到日志。

## Review Gates

- 开始实现前确认：CCH 未复现时不伪造 2.1.156 CCH。
- 提交前确认：不把 `data/flows/**/http_capture.jsonl`、`.flow`、账号 profile、token 或 prompt 原文提交到 git。

## Implementation Notes

- 已新增 `/root/project/cc2api/src/service/version_profile.rs`，集中管理 `2.1.156`、`build_time=2026-05-28T18:30:33Z`、Stainless `0.94.0`、runtime `v24.3.0`、endpoint beta 和 UA profile。
- `/api/event_logging/v2/batch` 已纳入遥测拦截、body 改写和自动代发；旧 `/api/event_logging/batch` 仅作为兼容路径保留。
- `/api/event_logging/v2/batch` 的真实 `event_data` 结构已覆盖身份、env/process、additional_metadata、user_attributes 改写。
- GrowthBook remote eval 和 telemetry user_attributes 已补齐 `userType`、`rateLimitTier`、`entrypoint`。
- `cc_version` 后缀测试已覆盖 JS 字符串索引语义；`2.1.156` 的 5 位 `cch` 已复现：最终 JSON body 中保留 `cch=00000` 占位，使用 `xxhash64` seed `0x4D659218E32A3268` 取低 20 bits。旧版本继续使用旧 seed `0x6E52736AC806831E`。
- 2026-06-04 按用户提供的 macOS watchpoint 思路在本机 Linux x64 做受控浅探：本地 dummy `/v1/messages?beta=true` 可稳定生成非零 CCH；旧 seed 对 JSON body 和完整 HTTP request bytes 均不匹配；动态 `cch=00000` heap 副本的写 watchpoint 不触发，说明 Linux/Bun 2.1.156 更可能在最终发送 buffer 构建阶段写入非零 CCH，不能直接照搬旧 seed 或 macOS 原地替换假设。
- 2026-06-04 继续沿 `send` buffer 上游定位：`0x43c7150` 是 native send 包装，`0x2e05400` 是 HTTP raw request 生成函数；复核后确认 `0x2e05400` 入口的 JSON body 源字段仍为 `cch=00000`，真正替换发生在其内部 `0x2e05b10` 路径，写回点位于 `0x2e06878` / `0x2e0687e` 附近。
- 2026-06-04 用新 seed `0x4D659218E32A3268` 对抓包 run `46ba25a8d791` 的 16 条带 billing `/v1/messages` 做离线摘要回归，结果 `16/16` 匹配；cc2api 已恢复 `2.1.156` 的 CCH rewrite，并新增版本 seed 测试。
- 自动遥测模板本轮升级到 v2 endpoint、API 成功事件和 GrowthBook 属性；工具/技能/MCP/feature flag 事件的完整模板仍建议等 CCH/遥测样本矩阵继续补齐，避免生成错误行为画像。
- check-all 复核时发现并修正 endpoint profile 偏差：`/api/oauth/*`、`/api/claude_code_grove`、`/api/claude_code_penguin_mode` 明确使用 `oauth-2025-04-20`，其中 `/api/claude_code_penguin_mode` 使用抓包中的 `axios/1.15.2` UA；旧 `/api/event_logging/batch` 兼容路径也归入 OAuth beta profile。
- 验证命令：`docker run --rm -v /root/project/cc2api:/work -w /work rust:latest /usr/local/cargo/bin/cargo test`，结果 90 个测试全部通过。
- 专项验证命令：`docker run --rm -v /root/project/cc2api:/work -w /work rust:latest /usr/local/cargo/bin/cargo test service::rewriter::tests`，结果 23 个 rewriter 相关测试全部通过。
- 本轮宿主机和 `rust:latest` 容器均没有可用 `rustfmt`/`rustup`，未能执行格式化工具；已执行 `git diff --check`，且 Rust 编译和测试通过。
- `cargo clippy --all-targets --all-features -- -D warnings` 会因既有 `router.rs`、`account.rs`、`store/*`、`tlsfp/*` 以及少量 `rewriter.rs` 风格类 lint 失败，本轮未扩大修复范围。
- `git diff --check` 通过。
