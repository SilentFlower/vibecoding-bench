# new-api 支持 Claude count_tokens 透传 - 实施计划

## Implementation Checklist

- [x] 阅读 new-api 现有 Claude relay、channel adaptor、header override、错误返回和测试风格。
- [x] 增加 count_tokens 请求 DTO 或轻量 JSON 校验结构，避免复用要求生成语义的 `ClaudeRequest` 热路径。
- [x] 在 `router/relay-router.go` 注册 `POST /v1/messages/count_tokens`。
- [x] 新增专用 controller/relay handler，复用认证后的渠道上下文和 Claude header 规则。
- [x] 实现上游 URL 构造：`/v1/messages/count_tokens`，按需追加 `beta=true`。
- [x] 实现 `anthropic-beta` 合并去重，确保 `token-counting-2024-11-01` 存在。
- [x] 实现 body 保守清理逻辑，仅删除 count_tokens 不需要的生成字段，保留 `model/messages/tools/system/thinking`。
- [x] 实现成功/错误响应透传，过滤 hop-by-hop header，避免记录敏感正文。
- [x] 增加定向测试：路由命中、上游 URL、beta 注入、成功响应、错误响应、不会补 `max_tokens`。
- [x] 运行定向 Go 测试；可行时运行相关包测试。

## Validation

- `cd /root/project/new-api && go test ./router ./controller ./relay/...`
- 如包范围过大或环境缺依赖，至少运行新增测试所在包。
- 远程联调：Claude Code 经过 new-api 访问 `/context`，确认 cc2api 下游只看到 `count_tokens_forward`，不再出现同一时间大量 `max_tokens=1` fallback。

## Validation Results

- 通过：`/usr/local/go/bin/go test ./controller -run 'Test(BuildClaudeCountTokens|RelayClaudeCountTokens)'`
- 通过：`/usr/local/go/bin/go test ./router ./controller ./relay/common ./relay/channel -run 'Test(SetRelayRouterRegistersClaudeCountTokensRoute|BuildClaudeCountTokens|RelayClaudeCountTokens|ProcessHeaderOverride|RelayInfo)'`
- 部分失败：`/usr/local/go/bin/go test ./router ./controller ./relay/...`
  - `router`、`controller`、`relay/common`、`relay/channel` 通过。
  - 失败集中在既有 `relay/channel/claude` 的文件内容转换测试，以及 `relay/helper` 的 `TestStreamScannerHandler_StreamStatus_PreInitialized`，和本次 count_tokens 专用入口无直接交集。

## Review Gates

- 实现前确认不改动现有普通 `/v1/messages` 生成请求行为。
- 提交前检查 new-api 当前已有未提交改动，不能覆盖或回滚无关修改。
