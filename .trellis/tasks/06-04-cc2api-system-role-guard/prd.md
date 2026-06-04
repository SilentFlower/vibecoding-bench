# cc2api system role guard

## Goal

为 cc2api 增加全局模型白名单式 `messages[].role=system` 透传保护：只有请求体 `model` 命中全局允许模型列表时，才允许 `messages` 数组包含 `role=system`；未命中时遇到该格式，网关本地直接返回错误，不请求上游，并在错误响应中返回当前允许列表。

这个功能用于兼容 Claude Code 2.1.156 在 `claude-opus-4-8` 下出现的 mid-conversation system reminder，同时避免未准备好的上游适配器收到 Anthropic beta 格式后返回不清晰的 400。

## Background / Known Context

- 本机验证显示 Claude Code 2.1.156 对 `claude-opus-4-8` 会发送 `messages[].role=system`，对 `claude-opus-4-7` 和 `claude-sonnet-4-6` 仍只使用顶层 `system`。
- cc2api 当前会改写 `/v1/messages` 请求体并转发上游，未看到针对 `messages[].role=system` 的本地兼容校验。
- cc2api 已有全局 settings key-value 表和 `/admin/settings` 管理接口，可复用来承载此类全局兼容开关。
- 现有错误响应统一为 `{"error":"..."}`，业务校验错误使用 HTTP 400。
- 当前规划假设默认允许列表为 `claude-opus-4-8`，因为这是本地确认会发送 `messages[].role=system` 的 Claude Code 2.1.156 模型。

## Requirements

- 新增全局配置项，用于配置允许透传 `messages[].role=system` 的模型列表。
- 模型匹配应基于请求体顶层 `model` 字段。
- 模型匹配应使用逗号分隔的精确模型 ID 列表，忽略首尾空白；不使用 `opus` 这类子串匹配，避免误放行 `claude-opus-4-7`。
- 默认允许列表建议为 `claude-opus-4-8`。
- 对 `/v1/messages` 请求，如果请求体 JSON 中 `messages` 数组任意元素的 `role` 为 `system`，且 `model` 不在全局允许列表中，必须直接返回 HTTP 400。
- 本地拦截后不能请求 Anthropic 上游。
- 本地拦截应发生在请求体改写、自动遥测记录、上游 token 解析和上游转发之前，避免为一个必然失败的请求产生额外副作用。
- 错误响应必须包含：
  - `error`：错误说明。
  - `model`：当前请求模型，缺失时为空字符串。
  - `allowed_system_role_models`：当前全局允许模型列表。
- 命中全局允许列表后必须保持现有转发逻辑，不删除、不改写 `messages[].role=system`。
- 后台 settings 接口必须读写和校验该配置项。
- 管理前端设置页需要能配置该模型列表，并提供 `claude-opus-4-8` 预设。
- 文档需要说明开关用途、默认值、错误行为和适用场景。

## Acceptance Criteria

- [ ] 全局 settings 包含 `allow_system_role_models`，默认值为 `claude-opus-4-8`。
- [ ] `/admin/settings` 返回 `allow_system_role_models`，未配置时表现为默认值。
- [ ] `/admin/settings` 更新时可切换 `allow_system_role_models`，保存逗号分隔模型 ID 列表。
- [ ] `/v1/messages` 请求包含 `messages[].role=system` 且 `model` 不在允许列表时返回 HTTP 400。
- [ ] 400 响应体包含 `error`、`model`、`allowed_system_role_models`。
- [ ] 上述 400 场景不会调用上游，也不会进入 body rewrite / 自动遥测记录链路。
- [ ] `model` 命中允许列表后，同样请求可以继续进入原有上游转发路径。
- [ ] 无 `messages[].role=system` 的传统请求行为不变。
- [ ] 覆盖后端单元测试或集成测试，至少包含未开启拦截、开启放行、传统请求不受影响。
- [ ] `cargo fmt --check`、`cargo test --offline` 通过；前端类型检查或构建按项目现有能力验证。

## Out of Scope

- 不在本任务中实现把 `messages[].role=system` 自动转换为顶层 `system`。
- 不在本任务中做按账号配置；本任务只做全局模型列表。
- 不在本任务中做模型能力探测；允许列表由配置决定。
- 不改变 `anthropic-beta` header、CCH、cc_version、telemetry profile 的既有逻辑。
- 不新增账号字段，也不改变账号创建/编辑表单。
- 不保存或输出请求体全文。

## Notes

- 错误信息可在实现时根据项目错误类型做轻微调整，但必须清晰指出当前模型未命中 `messages[].role=system` 允许列表。
