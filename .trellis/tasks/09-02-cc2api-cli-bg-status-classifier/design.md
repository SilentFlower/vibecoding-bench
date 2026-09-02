# 技术设计

## Architecture

本次变更只进入 cc2api，不修改 vibecoding-bench 运行时。数据流如下：

```text
Claude Code 2.1.257 request
  -> gateway access policy / body parse / ClientType
  -> cli-bg strong-shape detector
       -> mode=mock: local Anthropic Message response
       -> mode=passthrough: normal account/admission/proxy flow
            -> identity-only body rewrite
            -> normal Claude Code header rewrite + OAuth
            -> account proxy/TLS upstream request
```

## Setting Contract

- key: `intercept_cli_bg_status_classifier_mode`
- values: `passthrough | mock`
- default: `passthrough`
- backend enum: `CliBgStatusClassifierMode`
- cache: `GatewayService` 内 `RwLock<CliBgStatusClassifierMode>`
- reload: 独立 `reload_cli_bg_status_classifier_mode()`，启动时加载，管理 API 保存后热刷新。

新增 setting 按现有契约同步：

- `src/store/settings_store.rs`: 默认常量。
- `src/store/db.rs`: SQLite/PostgreSQL 共用 settings 默认插入与迁移测试。
- `src/handler/router.rs`: GET 默认、PUT 校验、热刷新与 API 测试。
- `src/main.rs`: 启动加载。
- `web/src/components/Settings.vue`: 枚举类型、加载、保存与二选一控件。

`web/src/api.ts` 已用 `SettingsMap=Record<string,string>`，无需新增独立 DTO 字段。

## Detection Contract

新增独立 detector，不复用旧 Auto Mode XML classifier：

```text
is_cli_bg_status_classifier_request(path, headers, body, client_type) -> bool
```

匹配层级：

1. wire gate: `path == /v1/messages`、Claude Code client、原始 `x-app == cli-bg`。
2. request gate: 精确 Fable 5.1、非流式、`max_tokens == 3072`、唯一 user message。
3. trusted system markers: 唯一 ephemeral text block，同时包含 Agent 状态分类用途、四状态集合、only JSON 输出约束与字段名。
4. input markers: user 文本以 `Current state:` 开始，并包含 tool calls、recent ask 和 assistant tail 标签。

精确模型 gate 避免把本次只在 Fable 5.1 上确认的旁路扩大到 Fable 5 或 `[1m]`。检测只读取可信 system 和唯一 user 文本，不扫描所有 request text，避免 transcript 中复制的提示词触发误命中。

检测不把 prompt 写入日志。日志输出 model、stream、max_tokens、body/text bytes、message count、retry count、mode、`shape_bypass` 和 `proxy_configured`。

## Passthrough Body Policy

普通 `rewrite_body_with_stateful_completion` 会依次处理空 text、metadata、system、message cache、TTL、disabled thinking、body order 与 CCH。该链路不能通过临时修改多个全局 setting 绕过，因为生产上的其他正常请求仍需要现有配置。

为命中请求增加 Rewriter 专用入口，职责限制为：

1. 解析 JSON；解析失败失败开放，返回原 bytes。
2. 复用现有账号身份逻辑更新 `metadata.user_id`，并应用已经解析出的 upstream session 映射。
3. 序列化正文，不运行其他 messages 改写，不计算/刷新 CCH，也不创建 stateful completion。

Gateway 仍执行原有：

- 账号选择、sticky、Fable 配额过滤。
- 并发槽与 RPM admission。
- upstream session pool 解析与 header/body session 对齐。
- Session Hello 现有策略。
- `rewrite_headers`，保留真实客户端 `x-app=cli-bg`，同时使用账号 2.1.257 身份画像。
- OAuth token 解析、账号 proxy/TLS、401 恢复、signature/429 重试和响应透传。

该边界既避免 system/message/cache/thinking 被改变，也避免把下游 metadata 的账号 UUID 原样发送给另一个代理 OAuth 账号。项目已启用 `serde_json/preserve_order`，结构化 identity 替换后仍保持对象字段相对顺序；不承诺保留原始 JSON 空白。

## Mock Response

模拟模式在 detector 命中后、生成 session hash 和账号选择之前返回，因此不会消耗 RPM 或并发槽。

响应外层复用现有 Anthropic Message envelope 生成能力：

```json
{
  "id": "msg_mock_cli_bg_status_classifier",
  "type": "message",
  "role": "assistant",
  "model": "claude-fable-5-1",
  "content": [{"type": "text", "text": "<serialized status JSON>"}],
  "stop_reason": "end_turn",
  "stop_sequence": null,
  "usage": {
    "input_tokens": 0,
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "output_tokens": 1
  }
}
```

内层状态 JSON 使用确定性规则：

- 只分析唯一 user 文本中的 `Current state` 与 `Assistant message tail`，不把 system 示例当成实际状态。
- API/auth/infra error、明确 blocked marker 或无自动复查的 user gate 优先判 blocked。
- 明确继续执行、下一次检查、仍在运行等 marker 判 working。
- 明确 no action/result/completed marker 判 done；明确 giving up / not actionable 判 failed。
- 没有明确 marker 时回退 `Current state`；仍不可解析时返回 working。

`detail`、`needs`、`output.result` 使用固定短文本，不回显完整 assistant tail，避免本地响应把任务内容复制到日志或其他观测面。

## Compatibility And Rollback

- 默认 `passthrough`，升级后不会默认伪造分类结果。
- setting 只对强特征命中生效；普通 `/v1/messages` 和旧 classifier 保持原路径。
- 快速行为切换：在 Settings 将模式切换为 `mock` 可停止该辅助请求访问上游；切回 `passthrough` 恢复真实分类。
- 代码/镜像回滚按 cc2api 远程部署规范恢复上一镜像；新增 settings key 留在数据库不会影响旧二进制。

## Production Verification

1. 完成本地质量门禁并推送 cc2api 子模块提交，构建 latest 镜像。
2. 远程部署前检查 5674 established 连接，低连接窗口才 recreate。
3. 部署后检查健康、镜像摘要、DB setting 和最近错误日志。
4. 临时关闭生产全文 429/非流请求日志或将 body limit 置 0，并保存原值供恢复。
5. 选择一个 `proxy_url` 非空的活跃账号，通过 `/admin/tokens` 创建仅允许该账号的一次性网关 token。
6. 构造脱敏 Claude Code 2.1.257 `cli-bg` 状态请求，通过 `https://us.flower-cli.com/v1/messages` 发起一次非流式调用。
7. 只输出 HTTP status、响应 envelope/schema 判断和 request-id 摘要；不输出 token、代理 URL或完整 prompt/response。
8. 核对容器日志的 `shape_bypass=true`、`proxy_configured=true` 命中摘要与该调用未触发上游 429。若仍为 429，基于最终出站摘要继续收敛旁路，不切 `mock` 冒充修复。
9. 删除一次性 token，恢复日志设置，确认生产模式为 `passthrough`。

## Risks

- TTL/message cache 是当前首要嫌疑，但上游错误体未明确因果；真实账号代理链路非 429 是必需验收，不只依赖单测。
- detector 过宽会误伤普通请求，过窄会因 prompt 小改失效；使用 wire/request/system/input 四层 gate 并覆盖负例。
- identity-only 仍会因结构化 metadata 替换重新序列化正文。若仍 429，下一轮需要对比 identity-only 与完全原始 body；完全原始 body 可能造成 OAuth 账号和 metadata identity 不一致，不能直接成为默认方案。
- 生产 `log_429_request_enabled` 当前可能记录正文；验收窗口必须先临时关闭或把 body limit 置 0，并在结束后恢复。
