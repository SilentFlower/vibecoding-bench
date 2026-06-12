# cc2api 非流单消息探针缓存

## Goal

为 cc2api 增加一个可全局开关控制的短 TTL 缓存，用于复用 Claude Code 启动阶段反复发送的非流式单消息探针响应，减少对 Anthropic 上游的重复请求，同时通过缓存创建与命中日志保留可复现证据。

## Background / Known Context

* 远端 `cc2api.env` 对应容器日志显示，`non_stream_request_capture` 中存在大量 `POST /v1/messages`、`max_tokens=1`、`message_count=1`、未显式设置 `stream` 的 Claude Code 请求。
* 这批请求会经过账号选择、RPM、改写、token 解析并请求上游，不属于本地 mock。
* 典型文本包括 `count`、`Session-specific guidance`、`Context management`、Memory 路径说明、运行环境说明、初始 git status 快照、skill 描述等。
* `warmup_intercept_hit` 中的 `mock_allow` / `mock_text` 已经本地返回，不属于本任务缓存范围。
* cc2api 是独立仓库 `/root/project/cc2api`；Trellis 任务记录在当前 bench 仓。

## Requirements

* 增加全局设置 `non_stream_probe_cache_enabled`，默认关闭，管理员可在 Settings 页面开启或关闭。
* 缓存 TTL 固定为 30 分钟。
* 仅缓存强特征的上游请求：
  * `path == /v1/messages`
  * 客户端识别为 `ClaudeCode`
  * 请求不是流式：`stream` 缺失或 `false`
  * `max_tokens == 1`
  * `messages` 数组长度为 1，且唯一消息 `role == user`
  * 唯一消息文本命中已知探针特征，避免缓存真实用户业务 prompt
* 缓存 key 必须基于会影响上游响应的最终上游请求形态生成，至少包含模型、最终请求体、关键 Anthropic header、Claude Code beta/version 相关 header；key 只在日志中输出 hash，不打印原文。
* 首次未命中时正常请求上游；上游返回成功的非流 JSON message 响应后写入缓存。
* 缓存命中时直接返回缓存响应，不再进入上游转发；返回时应重新生成或修正响应中不应复用的易变字段，至少避免长期复用相同 `id` 造成客户端侧歧义。
* 记录缓存创建日志，日志名建议为 `non_stream_probe_cache_create`，包含 `cache_key_hash`、`probe_type`、`model`、`account_id`、`ttl_secs=1800`、`body_bytes`、`status`、`expires_at`。
* 记录缓存命中日志，日志名建议为 `non_stream_probe_cache_hit`，包含 `cache_key_hash`、`probe_type`、`model`、`account_id`、`age_secs`、`expires_in_secs`。
* 日志不得输出原始 prompt、Authorization、Cookie、token、完整请求体或完整响应体。
* 缓存存储可先使用进程内内存；重启丢失可接受。

## Acceptance Criteria

* [ ] `GET /admin/settings` 返回 `non_stream_probe_cache_enabled`，默认值为 `false`。
* [ ] `PUT /admin/settings` 能校验并保存 `non_stream_probe_cache_enabled`，只允许 `true` / `false`。
* [ ] Settings 页面出现“非流单消息探针缓存”全局开关，保存后立即生效。
* [ ] 开关关闭时，目标探针请求行为与现状一致，继续请求上游。
* [ ] 开关开启时，首次命中强特征探针会请求上游并记录 `non_stream_probe_cache_create`。
* [ ] 开关开启且 30 分钟内同 key 再次请求时，不请求上游并记录 `non_stream_probe_cache_hit`。
* [ ] 30 分钟后同 key 请求重新请求上游并刷新缓存。
* [ ] 完整对话类非流请求，例如 `messages=97` / `messages=485`，不会被缓存。
* [ ] API 客户端请求不会被该缓存处理。
* [ ] 已本地 mock 的 warmup / classifier 请求不受影响。
* [ ] 新增或更新单元测试覆盖匹配条件、拒绝条件、缓存创建、缓存命中、过期刷新、日志字段脱敏。

## Definition of Done

* `cargo fmt --check` 通过。
* `cargo test` 通过，或记录无法运行的原因。
* 前端构建或类型检查通过，或记录无法运行的原因。
* 任务实现只修改 cc2api 相关代码与本任务 Trellis 产物。
* 不提交完整抓包、token、Cookie、Authorization、邮箱或完整 prompt/响应正文。

## Out of Scope

* 不缓存完整对话类非流请求。
* 不对 `warmup_intercept_hit` 的本地 mock 请求再做缓存。
* 不做跨进程、跨重启、Redis 或数据库持久缓存。
* 不缓存非 Claude Code API 客户端请求。
* 不新增可配置 TTL；本任务固定 30 分钟。

## Research References

* `.trellis/spec/cc2api/claude-code-profile-upgrade.md` — cc2api 跨层设置、网关、前端与部署变更需要同步验证。
