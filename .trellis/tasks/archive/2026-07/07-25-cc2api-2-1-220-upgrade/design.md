# 升级 cc2api 至 Claude Code 2.1.220 - 技术设计

## Architecture

版本差异继续由 `src/service/version_profile.rs` 统一声明。Gateway、Rewriter、TokenTester、Telemetry 和 Bootstrap 只消费选中画像，不在热路径散落 `2.1.220` 字符串特判。全局 settings 仍由 `settings_store` 提供默认值，由 `db::migrate` 对精确旧默认值进行保守升级。

根仓仅同步 worker 的兜底 Claude Code 版本和对应测试/文档，不改变运行页覆盖优先级或抓包数据结构。

## Version Profile

新增 `PROFILE_2_1_220`：

- identity：`2.1.220`、build time `2026-07-24T22:17:45Z`、Stainless `0.94.0`、Node `v26.3.0`。
- access policy：`2.1.89-2.1.220`。
- billing：沿用 `Sha256TextPositions` 和 `ClaudeCode2172Plus`。
- telemetry：沿用 `ClaudeCode2185` 和 `Bun/1.4.0`，默认模型改为 `claude-opus-5`。
- endpoint/bootstrap：声明 2.1.220 的 `cedar_basin`、Fable `marigold` 和 Opus 5 `belladonna` 指纹。

扩展请求子画像以显式承载至少以下版本差异：通用 message beta、Fable beta、Fable fallback model、Fable body-order profile。旧画像继续引用旧 beta 和 `claude-opus-4-8` fallback；2.1.220 引用新增 fallback-credit beta、`claude-opus-5` fallback 和 Fable 专用字段顺序。

## Request Rewrite

`rewrite_headers` 已持有账号和 canonical env，因此先按账号版本解析 profile，再把 profile 传给 endpoint beta 选择。`context-1m-2025-08-07` 仍由客户端输入与 `allow_1m_models` 决定，只负责过滤和固定顺序，不进入通用必需 beta。

API body 补全按同一 profile 执行：

- Opus 5 与 Fable 5 缺失 `max_tokens` 时补 64000，不覆盖显式值。
- Fable 缺失 `fallbacks` 时补选中 profile 的 fallback，不覆盖调用方已有字段。
- 字段排序先识别 Haiku probe/title，再识别 2.1.220 Fable，最后使用主请求默认顺序。
- 所有改写完成后才刷新 billing header 和 CCH。

`TokenTester` 根据 canonical env 版本获取 identity/request 子画像，避免旧 profile 使用当前默认 runtime 或 beta。

## Billing

2.1.220 仅加入现有版本映射：

- `cc_version` 继续按首条 user message 的最后一个 text block，以 JavaScript UTF-16 code unit 语义计算。
- CCH 继续在最终 body 字节上把 `cch` 还原为占位符，将顶层 `model` 置空并删除顶层 `max_tokens`、`fallbacks`，seed 保持 `0x4D659218E32A3268`。
- 不通过 JSON 重新序列化计算 CCH，不删除 `diagnostics` 或嵌套 tool schema 同名字段。

## Global Settings And Migration

默认设置调整：

```text
allow_system_role_models=claude-opus-5,claude-fable-5,claude-opus-4-8
intercept_assistant_prefill_models=claude-fable-5,claude-opus-5,claude-opus-4-8,claude-opus-4-7
```

迁移采用精确旧值匹配：

- profile=`2.1.197` 且 allowed range=`2.1.89-2.1.197` 时成对升级到 2.1.220。
- `allow_system_role_models` 仍等于旧默认 `claude-opus-4-8` 时升级；自定义列表保留。
- assistant prefill models 仍等于旧默认列表时加入 Opus 5；自定义列表保留。
- 账号 canonical env 使用迁移后选中的 profile 更新 version、version_base、build_time、node_version。

## Bootstrap

Passthrough 模式不修改上游 JSON。Configured 模式基于选中版本画像补齐：

```json
{
  "client_data": {
    "cedar_basin": "2026-08-31",
    "cedar_lagoon": {
      "claude-fable": true,
      "claude-mythos": true
    }
  }
}
```

query model 为 Fable 5 时写 `marigold`，为 Opus 5 时写 `belladonna`。HideFable 只删除 Fable options、关闭 Fable 标志并清理 `marigold`；已有 `belladonna` 保留。响应压缩解码和长度 header 清理沿用现有实现。

## Public Connectivity Endpoint

在管理路由与鉴权 fallback 之前注册公开 `/api/hello`。GET 返回 JSON hello，HEAD 复用同一路由语义并返回 200。该路径不读取网关 token，不创建账号或 telemetry 状态，也不代理到上游。

本地 2.1.220 实验确认 `ANTHROPIC_BASE_URL` 只影响 `/v1/messages` 等模型请求；hello 预检固定访问 `https://api.anthropic.com/api/hello`，不会到达 new-api。因此本次不为 new-api 增加同名路由或渠道选择规则，cc2api 端点仅覆盖直接访问 cc2api 的拓扑和健康检查。

## Telemetry

不新增 `TelemetryShape`。原生 event batch 继续只改写 canonical identity/session/process 等已知字段，未知字段原样保留。

自动 telemetry 构造函数改为接收完整版本画像：基础 event 的 beta 取 request profile，启动事件模型取 telemetry profile 默认模型；message query/success 仍以最终重写 header 构造的 context 覆盖 beta。客户端本地的 `skill_name`、`flags=model` 和事件集合不由服务端猜测。

## Compatibility And Rollback

- 2.1.197 及更早 profile 保留原 beta、fallback、bootstrap 和 billing 行为。
- 管理员可以切回旧 profile；迁移不会覆盖自定义 allowed range 和模型列表。
- 公开 `/api/hello` 只新增无状态成功响应，不放宽其他网关路径鉴权。
- new-api 保持不变；hello 不进入其渠道选择和模型 relay。
- 根仓默认版本更新不覆盖 WebUI 已保存版本或远程 `.env` 显式值。

## Risk Controls

- RequestProfile 新字段必须由所有内置 profile 显式赋值，避免编译通过但回滚画像缺项。
- Fable body order 和 CCH 输入顺序耦合，定向测试必须从最终序列化 body 复算。
- settings 迁移同时覆盖 SQLite/PostgreSQL 通用 SQL 路径，并测试幂等与自定义值保护。
- 抓包只作为本地验证输入，不复制敏感正文进入 fixture 或任务文档。
