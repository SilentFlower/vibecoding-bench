# 升级 cc2api 到 2.1.197

## 目标

将 `cc2api/` 的 Claude Code 版本画像升级到 `2.1.197`，基于真实抓包而不是只改版本号，确保默认 UA、账号 `canonical_env`、settings 版本范围、请求 beta、billing/CCH、telemetry 与目标版本一致。

## 背景与已确认事实

- `@anthropic-ai/claude-code@2.1.197` 已在 npm 发布；截至 2026-07-01 查询，`latest` 和 `next` dist-tag 都指向 `2.1.197`，发布时间为 2026-06-30 13:31:18 UTC。
- 当前 `cc2api` 子模块 HEAD 为 `27f00cd`，默认 Claude Code 画像仍是 `2.1.195`，关键入口是 `cc2api/src/service/version_profile.rs`、`cc2api/src/service/rewriter.rs`、`cc2api/src/service/gateway.rs`、`cc2api/src/store/db.rs`、`cc2api/web/src/components/Settings.vue`。
- 远程 `vibecoding-bench.env` 上 run `d72b00a1257b` 的抓包目录是 `data/flows/6-29/4876/d72b00a1257b`；本任务只记录脱敏协议摘要，不保存完整 `http_capture.jsonl`、token、Cookie、prompt 或响应正文。
- 该抓包共 155 条 HTTP flow，其中 `68` 条 `POST api.anthropic.com/v1/messages`、`71` 条 `POST api.anthropic.com/api/event_logging/v2/batch`。
- `2.1.197` bootstrap 请求为 `/api/claude_cli/bootstrap?entrypoint=cli&model=claude-sonnet-5`，UA 为 `claude-code/2.1.197`，beta 为 `oauth-2025-04-20`，响应模型选项中出现 `claude-fable-5[1m]`。
- `2.1.197` telemetry env 摘要显示 `version=2.1.197`、`version_base=2.1.197`、`build_time=2026-06-29T19:08:42Z`、`node_version=v26.3.0`。
- `2.1.197` Sonnet 主请求模型为 `claude-sonnet-5`，66/66 条 Sonnet `/v1/messages` 请求的 `anthropic-beta` 都包含 `context-1m-2025-08-07`，顺序为 `oauth-2025-04-20` 后、`interleaved-thinking-2025-05-14` 前。
- 用户确认 `claude-sonnet-4-6` 不带 `context-1m-2025-08-07`；因此不能用宽泛的 `sonnet` 子串作为默认 1M 白名单，否则会误放行 Sonnet 4.6。
- `2.1.197` Sonnet 主请求 body 顶层字段顺序主要为 `model,messages,system,tools,metadata,max_tokens,thinking,context_management,output_config,diagnostics,stream`；少量请求缺少 `diagnostics`。
- `2.1.197` Sonnet 主请求 billing header 形态为 `cc_version=2.1.197.<suffix>; cc_entrypoint=cli; cch=<5hex>;`，`cch` 存在且每次请求变化。
- `2.1.197` Sonnet 主请求首条 user message 有两个 text block；后缀算法仍需要按已有契约取最后一个 text block 复算。
- 当前 `cc2api` 的账号字段 `allow_1m_models` 默认是 `"opus"`，会过滤 Sonnet/Haiku 的 `context-1m-2025-08-07`；如果目标是忠实模拟 `2.1.197` Sonnet 5 抓包，需要精确放行 `claude-sonnet-5`，同时继续过滤 `claude-sonnet-4-6`。
- 已确认默认 1M 白名单调整为 `"opus,claude-sonnet-5"`，用于贴近 `2.1.197` Sonnet 5 抓包并避免误放行 Sonnet 4.6。

## 需求

1. 新增并启用 `2.1.197` Claude Code 内置画像，更新默认画像 key、默认版本、默认 build time、默认 allowed version range。
2. 保留 `2.1.195`、`2.1.187`、`2.1.185`、`2.1.173` 作为可回滚内置画像；未知画像 key 仍必须拒绝。
3. 启动迁移必须把旧默认 settings 组合升级到 `2.1.197` 默认画像，并批量更新账号 `canonical_env.version/version_base/build_time/node_version`。
4. 请求改写必须让 `2.1.197` 的 UA、Stainless package/runtime、beta 顺序、billing header、CCH 输入规则与抓包摘要一致。
5. Sonnet 1M beta 策略必须按模型精确度处理：`claude-sonnet-5` 可按 `2.1.197` 抓包保留 `context-1m-2025-08-07`，`claude-sonnet-4-6` 必须继续过滤；禁止把默认白名单写成宽泛的 `sonnet`。
6. 前端 Settings 的默认 profile、allowed range、fallback 选项必须与后端内置画像一致。
7. `vibecoding-bench` worker 默认 Claude Code 版本和远程 compose/env 相关文档如仍指向旧默认，需要同步到 `2.1.197`。
8. 不提交或记录完整远程抓包正文、Authorization、Cookie、账号邮箱、完整 prompt 或完整响应正文。

## 验收标准

- [ ] `cargo fmt --check` 通过。
- [ ] `cargo test` 通过。
- [ ] 版本画像测试覆盖 `2.1.197` 默认画像、回滚画像唯一性、默认 allowed range、build time、node runtime。
- [ ] migration/settings 测试覆盖旧默认 `claude_code_version_profile` 与旧默认 `allowed_claude_code_versions` 升级到 `2.1.197`，并覆盖管理员自定义 allowed range 的保留策略。
- [ ] protocol 测试覆盖 `2.1.197` 的 UA、`cc_version`、CCH seed/input profile、Sonnet 5 beta 顺序和 `context-1m-2025-08-07` 策略；同组测试必须断言 `claude-sonnet-4-6` 不带 `context-1m-2025-08-07`。
- [ ] telemetry 测试覆盖 `env.version/version_base/build_time/node_version` 输出 `2.1.197` 画像。
- [ ] 前端构建或相关静态检查覆盖 Settings 画像列表更新。
- [ ] 远程部署前检查连接数，部署后 `curl /` 返回 200，DB 版本分布全部为 `2.1.197`，容器日志无 `error|panic|failed|thread.*panicked`。

## 非目标

- 不改变完整抓包 run 的敏感数据落盘策略。
- 不把完整 `http_capture.jsonl` 或远程账号信息提交到仓库。
- 不新增任意版本字符串拼装能力；版本画像仍只允许内置 profile key。
