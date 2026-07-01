# Brief — 升级 cc2api 到 2.1.197

## Goal

- 将 `cc2api/` 的 Claude Code 版本画像升级到 `2.1.197`，基于真实抓包同步 UA、账号 `canonical_env`、settings 版本范围、请求 beta、billing/CCH、telemetry，并同步 `vibecoding-bench` worker 默认版本。

## Scope

- 新增 `2.1.197` 内置 profile，并切为默认画像；保留 `2.1.195`、`2.1.187`、`2.1.185`、`2.1.173` 作为回滚画像。
- 将默认版本范围更新为 `2.1.89-2.1.197`，启动迁移旧默认 settings 组合，并批量更新账号 `canonical_env.version/version_base/build_time/node_version`。
- 将默认 `allow_1m_models` 从 `"opus"` 改为 `"opus,claude-sonnet-5"`；`claude-sonnet-5` 可透传 `context-1m-2025-08-07`，`claude-sonnet-4-6` 必须继续过滤。
- 更新 `cc2api` 后端、Settings/Accounts 前端页、`vibecoding-bench` worker Dockerfile/compose/README/WebUI 默认版本提示。
- 准备远程部署验收：连接数检查、pull/recreate、`curl /`、DB 版本分布、日志检查。

## Non-Goals

- 不提交或记录完整 `http_capture.jsonl`、token、Cookie、账号邮箱、完整 prompt 或完整响应正文。
- 不改变完整抓包 run 的敏感数据落盘策略。
- 不新增任意版本字符串拼装能力；版本画像仍只允许内置 profile key。

## Key Context

- 脱敏抓包 run：`data/flows/6-29/4876/d72b00a1257b`。`2.1.197` Sonnet 5 主请求 66/66 条包含 `context-1m-2025-08-07`，顺序在 `oauth-2025-04-20` 后、`interleaved-thinking-2025-05-14` 前。
- telemetry env 目标值：`version=2.1.197`、`version_base=2.1.197`、`build_time=2026-06-29T19:08:42Z`、`node_version=v26.3.0`。
- `cc_version` 后缀已复算命中现有算法；Sonnet 5 多 text block 必须取最后一个 user text block。
- CCH 已复算命中 `CchProfile::ClaudeCode2172Plus`：seed `0x4D659218E32A3268`，最终 body 中将 `cch` 还原为 `00000`，top-level `model` 置空，删除 top-level `max_tokens` / `fallbacks`，保留 `diagnostics`。远程样本 Haiku 1/1、Sonnet 5 66/66 命中。
- 不能用宽泛 `sonnet` 白名单；用户确认 `claude-sonnet-4-6` 不带 1M 头。
- 高风险文件包括 `cc2api/src/service/version_profile.rs`、`cc2api/src/service/rewriter.rs`、`cc2api/src/service/gateway.rs`、`cc2api/src/store/db.rs`、`cc2api/src/model/account.rs`、`cc2api/src/handler/router.rs`、`cc2api/web/src/components/Settings.vue`、`cc2api/web/src/components/Accounts.vue`、`images/worker/entrypoint.sh`、`docker-compose.yml`、`docker-compose.remote.yml`。
- 1M 白名单仍是子串匹配；`claude-sonnet-5` 会匹配未来 `claude-sonnet-5-*`，但不会匹配 `claude-sonnet-4-6`。

## Acceptance

- `cd cc2api && cargo fmt --check` 通过。
- `cd cc2api && cargo test` 通过。
- `cd cc2api/web && npm run build` 通过。
- 版本画像测试覆盖 `2.1.197` 默认画像、回滚画像唯一性、默认 allowed range、build time、node runtime。
- migration/settings 测试覆盖旧默认 profile/range 升级到 `2.1.197`，管理员自定义 allowed range 保留，旧默认 `allow_1m_models="opus"` 升级为 `"opus,claude-sonnet-5"` 且自定义值保留。
- protocol 测试覆盖 `2.1.197` UA、`cc_version`、CCH seed/input profile、Sonnet 5 beta 顺序和 1M 策略，并断言 `claude-sonnet-4-6` 不带 `context-1m-2025-08-07`。
- telemetry 测试覆盖 `env.version/version_base/build_time/node_version` 输出 `2.1.197` 画像。
- 远程部署后 `curl /` 返回 200，DB 版本分布全部为 `2.1.197`，日志无 `error|panic|failed|thread.*panicked`。

## Next Step

- 用户确认 planning artifacts 和本 brief 后，运行 `python3 ./.trellis/scripts/task.py start .trellis/tasks/07-01-cc2api-2-1-197-upgrade`；进入 in_progress 后走 `trellis-route(implement)`，不能直接开始改代码。
