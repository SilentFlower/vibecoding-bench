# 反重力兼容 Claude WebSearch

## Goal

让 Claude Code 通过 Flower2API 使用反重力 Gemini 对话和工具，联网搜索由原版 `agy` 执行。

## Requirements

- 在 Flower2API 接收 Claude `/v1/messages`。反重力 Gemini 路径支持系统提示、普通多轮文本、原生已支持的内嵌图片、函数声明和工具回填。按 Claude 格式返回 SSE 或 JSON。
- 保留令牌权限、原始 Session ID 和工具调用 ID。主回合与回填沿现有 Gemini 账号调度和原工具轮续接。
- 原生 `web_search_20250305` 的独立搜索请求用固定原版 `agy -p` 的 `stream-json` 执行 `search_web`。使用搜索回执中的标题和链接，按请求域名过滤，匹配 Claude 搜索工具 ID。搜索故障应可辨认。
- 单并发账号能完成相关的搜索与主回合回填。搜索权限只沿已认证令牌与原调用核验。结束、超时及取消后回收本次资源。
- New API 有需要时可用已有 Anthropic 渠道透传。任务交付和本地验收都在 Flower2API 仓库内。

## Non-Goals

- ACP、部署换版、New API 源码和渠道配置变更、完整的 Anthropic 服务端工具目录、Claude 专属缓存与计费语义属于独立工作。
- 工具图片的反重力内核识别改造由现有 `11-19-agy-png-tool-compatibility` 承担。本适配在已有能力内保持图片内容和工具关联。

## Acceptance Criteria

- [ ] 同一有效令牌下，Claude Code 的流式多轮、普通 JSON、同名并行乱序工具回填和含图片的普通请求工作。诊断显示原始 Session ID，既有 Claude 和 Gemini 入口回归通过。
- [ ] Claude Code 搜 `IANA Example Domains` 得到可追溯的标题与链接，搜索工具 ID 成对，`searchCount=1`，主对话收到回填并继续。
- [ ] 单并发、多候选账号时搜索与工具轮归属相同。覆盖令牌隔离、查询不匹配、重复、清理和后续正常接单。
- [ ] 回执格式、真实来源和已授权实际联网分别有证据。响应中的空结果与故障可区分。
