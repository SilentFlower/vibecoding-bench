# 反重力 Messages 适配设计

## 接入边界

- 用户确认在 Flower2API 处理 Messages 协议和反重力模型调度，WebSearch 用 `agy -p`。参考 Sub2API `v0.2.24` 的双向适配。VM2API `v1.4.169` 的公开原生适配范围限于单条流式纯文本。
- Rust 网关在原 `/v1/messages` 鉴权后识别反重力 Gemini 请求。按当前令牌和现有真实目录执行模型准入，Gemini 型号路径具有明确入口。复用现有会话与账号执行流程，Anthropic 自身的转发沿原入口。
- 原始 Messages 先解析会话及工具类型。Claude Code 的顶层 `system` 和消息列表内的 `system` 文本按顺序合并为 Gemini 系统提示。普通内容和函数按现有 Gemini 合同映射。工具结果按 `tool_use_id` 关联，真实模型签名跟随原工具轮。输出适配生成 Anthropic SSE 及 JSON，并保留源用量和错误分类。

## 运行和回包

- 识别单独声明 `web_search_20250305` 的搜索入口。实测 Claude Code 子请求用相同模型、原始 Session ID 和独立 `/v1/messages`。取其查询词及域约束，普通客户端工具继续走原工具回填。
- 对相关搜索，根据有效令牌、原会话、模型和查询核对唯一待回填轮。复用原账号许可及原运行环境。搜索和该主轮的下一次生成按同一许可串行。独立搜索使用现有正常准入。
- AGY 发送器沿同一私有鉴权、凭据代次、封存执行体与账号代理启动原版。以 `agy -p --input-format stream-json --output-format stream-json` 运行一次工具回合。搜索工作目录和 AT-only HOME 每次隔离。关联搜索沿用等待回填的许可，独立搜索计入现有发送器容量。
- 固定 `1.5.9` 的 `step_update` 提供搜索参数、会话、步骤和状态。按它定位本次 SQLite 轨迹里的 `SearchWeb` 结构，读取原生来源标题和 URL。执行成功且资源回收后发送同 ID 的 `server_tool_use` 和 `web_search_tool_result`。从结构化回执得出的空结果和运行故障有不同响应。
- 网关用可核对的来源域匹配允许域与禁止域。固定原版的 Google 搜索轨迹对 `vertexaisearch.cloud.google.com` 跳转链接只保留跳转地址和标题。指定域名规则时省略这种来源。无域名规则时交付原链接。
- 回填复用已匹配工具的真实模型签名。诊断在解码后冻结为反重力平台和 `anthropic_messages` 入口，保留客户端发来的原始 Session ID。
- New API 已有 Anthropic 透传请求与响应。经该渠道时，选定原模型和同一访问令牌发往 Flower2API。共享上游 Key 的访问权限按实际认证令牌划分，鉴权边界不以客户端自报字段扩大。

## 验证和兼容

- 基线为 Flower2API `7b13bd9aa9022d3cde1e3f19faa87a76d71620d3` 和固定原版 AGY `1.5.9`。本地离线 `init.tools` 会列出通用工具，执行范围以实际出站工具和负向调用验证为准。
- 回环先核对真实二进制，再用真实客户端联调普通工具、搜索、单并发与异常终态。真实外部结果在已有授权测试条件下单独验证。
- 普通 Claude 请求、现有 Gemini API、相同令牌隔离及已有账号迁移/维护边界作为回归范围。上线配置留到后续发布步骤。
