# 反重力 Messages 思考档位与图片回包设计

## 请求与选号

- 已鉴权的 `/v1/messages` 在 `services/gateway/src/service/gemini/messages.rs` 识别思考选项，与 Gemini 入口共用档位解析规则。Messages 把解析出的档位作为网关内部选号参数传递，生成正文保持已有形状。原生 Gemini 按原入口读取并消费 `thinkingConfig`。实际思考 token 数由 AGY 执行型号决定。
- 手动 `thinking.type=enabled` 携带有效正整数 `budget_tokens` 时使用预算。其余请求可从顶层 `output_config.effort` 读取已知档位。沿用 `low`、`medium`、`high`、`xhigh`，`max` 映射到 `xhigh`。Sub2API 使用的 `minimal` 和 `none` 别名归为低档。缺省或无法映射的可选值按原目录行为处理。显式关闭思考的精确语义由型号能力决定。
- 在普通 Messages 的基础模型请求中，目标档位优先，其后使用该基础模型原有的可接单候选顺序并去重。这样只有缺少或无法使用目标档位的目录仍能处理此前有效的请求。诊断按已有实际型号字段核对生效档位。显式档位和工具续轮由原有路由判定。独立 WebSearch 在其专用分支识别，现有 Gemini API 的档位规则沿原入口。

## 响应与媒体边界

- `agy_runtime/gemini_frames.py` 的 Part 投影与网关聚合保留原始 `inlineData`。图片的 JSON 和 SSE 表示都在 Messages 转换层构造，对应 Sub2API 非流式和流式输出中可显示的 Markdown 图片文本。
- 图片从同一 AGY 帧的 `mimeType` 与 Base64 `data` 构造。沿现有响应字节预算校验受支持的栅格图像类型和可安全嵌入的 Base64。无效图像记录不含源内容的诊断并省略该 Part，其余文本、思考块和工具按原类型输出。直接 Gemini 回包保留原始图片 Part。
- 当前 `agy_runtime/gemini_contract.py` 的显式输出只接收默认或 `TEXT`，单测覆盖 `IMAGE` 拒绝。启用主动出图需验证固定 `agy 1.5.9` 和实际目录的模型能回传图像。本轮可在实际二进制的隔离回环测试模型返回图片时的回包，真实出图沿授权环境验收。合成回环只作为协议兼容证据。

## 兼容性依据

- Claude 手动思考和自适应控制使用 `thinking.budget_tokens`、`output_config.effort`。AGY 档位沿用网关已有的选择规则。[Gemini 选号](../../../services/gateway/src/service/gemini.rs#L500) · [Claude 思考控制](https://platform.claude.com/docs/en/build-with-claude/effort) · [Sub2API 请求转换](https://github.com/Wei-Shaw/sub2api/blob/v0.2.24/backend/internal/pkg/antigravity/request_transformer.go)
- 图片外层是 Claude 文本内容，客户端按自身 Markdown 渲染能力展示。字节及顺序可从 API 结果独立验收。[Sub2API JSON 转换](https://github.com/Wei-Shaw/sub2api/blob/v0.2.24/backend/internal/pkg/antigravity/response_transformer.go) · [Sub2API SSE 转换](https://github.com/Wei-Shaw/sub2api/blob/v0.2.24/backend/internal/pkg/antigravity/stream_transformer.go)
