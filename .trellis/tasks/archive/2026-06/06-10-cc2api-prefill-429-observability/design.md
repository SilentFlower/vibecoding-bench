# design.md

## Technical Design

### 配置链路

新增配置沿用现有 settings 模式:

* `src/store/settings_store.rs`:定义默认值常量。
* `src/store/db.rs`:迁移时 `INSERT OR IGNORE`/`ON CONFLICT DO NOTHING` 写入默认值。
* `src/handler/router.rs`:GET 补默认值,PUT 校验并保存,保存后调用 GatewayService reload。
* `src/service/gateway.rs`:新增配置结构和 `RwLock` 缓存,启动和设置更新时热加载。
* `src/main.rs`:启动时 reload 新配置。
* `web/src/components/Settings.vue`:新增 UI 状态、校验、加载和保存字段。

### Assistant Prefill 拦截

拦截位置放在 `handle_request_inner` 解析 body、检测 client_type 之后,账号选择之前。原因:

* 已有 `body_map`、`path`、模型字段可用。
* 在账号选择、RPM、并发槽、token 解析之前返回,避免坏请求消耗账号池。
* 只看原始客户端请求体即可判断 prefill 语义,不依赖后续 rewrite。

命中条件:

* `path.starts_with("/v1/messages")`
* 配置 `enabled == true`
* `model` 精确匹配配置列表,默认列表为 `claude-fable-5,claude-opus-4-8,claude-opus-4-7`
* `messages` 是数组且最后一条 `role == "assistant"`

响应使用 400 JSON,包含 `error.type=invalid_request_error`、稳定 `code=assistant_prefill_intercepted`、`model` 和简短 message。

### 429 请求观测

观测位置放在 `forward_request` 的 `status_code == 429` 分支。此时使用的是已改写、已加 upstream Authorization、实际发往 Anthropic 的 `headers` 和 `body`,符合“实际请求头/请求体”。

日志内容:

* 固定标记 `429_request_capture`
* `account_id`
* `path`
* `model`
* `stream`
* `request_headers`:脱敏后 JSON/字符串
* `request_body`:脱敏、规范化、按配置截断
* `body_summary`:字节数和 sha256 短摘要

脱敏策略:

* 请求头敏感 key 直接替换为 `***REDACTED***`:authorization、cookie、set-cookie、x-api-key、anthropic-api-key、proxy-authorization 等。
* JSON 请求体递归替换敏感 key:authorization、api_key、key、token、access_token、refresh_token、password、secret、setup_token 等。
* 非 JSON body 只按 UTF-8 lossy 输出并截断;仍做 bearer/basic/token 样式字符串脱敏。
* 截断按字符数进行,末尾追加 `...<truncated>`。

### 兼容性

两个功能默认关闭。新增 settings key 缺失时 GET 和 Gateway reload 都使用默认值,老数据库无需手工 migration。

## Rollout / Rollback

* Rollout:发布后先开启 429 观测,短时间收集日志;确认 prefill 风暴后开启 assistant prefill 拦截。
* Rollback:设置页关闭对应开关即可热回滚;必要时回退镜像。
