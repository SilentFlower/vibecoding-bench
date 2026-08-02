# Brief — Topic 自然提示词变体

## Goal

- 降低默认 topic prompt 在批量运行中的固定语言特征，同时保持题目语义、任务可追溯性和正式 benchmark 的可比性。

## Scope

- 在后端提供 `natural` 与 `canonical` 两种 prompt 模式，并由单一 `build_topic_prompt()` 入口生成。
- 普通单任务、批次和养号默认自然模式；抓包默认规范模式。
- 单任务、批次和抓包 WebUI 增加“自然 / 规范”模式选择，并同步 `prompt_mode` API 字段。
- 自然模式提供至少 5 个结构不同但语义等价的人工模板；规范模式保持当前固定文本。
- 修正养号链路重复生成 prompt 的问题，确保数据库记录与 worker 实际下发完全一致。
- 增加后端单元测试和前端语法、双主题及表单契约验证。

## Non-Goals

- 不重写 `topics.md` 中的 600 条题目正文。
- 不接入外部模型实时改写 prompt。
- 不修改 worker 的超时收尾、认证恢复或工具权限提示词。
- 不新增数据库列，不为历史 task/run 回填变体元数据。

## Key Context

- 实际 prompt 已保存在 `tasks.prompt` 和 `task_batch_items.prompt`，无需新增 schema；创建后必须复用持久化文本。
- 自定义 `prompt` 覆盖始终优先，不参与模式渲染。
- 自然模板只能调整信息组织和措辞，不能增加技术栈、架构、依赖或超时策略要求。
- `prompt_mode` 由 Pydantic 在 API 边界校验，前端字段名和默认值必须与三个请求 DTO 一致。
- 养号当前先持久化一次、下发前又生成一次；随机模板会暴露该一致性缺陷。
- 前端保持原生 HTML/CSS/JavaScript 零构建架构，分段控件遵循终端实验室双主题、无圆角和稳定尺寸约束。

## Acceptance

- 至少 5 种自然模板可被选择，结构明显不同且保留现有交付语义。
- 规范模式对同一输入稳定，正式 benchmark 可显式选择。
- 单任务、批次、养号和抓包使用约定默认模式，自定义 prompt 行为不变。
- 养号持久化 prompt 与 `scheduler.submit()` 下发 prompt 完全一致。
- 三个 WebUI 表单均能提交正确的 `prompt_mode`，默认值与后端一致。
- Python 编译、后端单元测试和 JavaScript 语法检查通过，浏览器双主题和窄屏检查无异常。

## Next Step

- 完成 Check-All 修复重检；严格通过后等待用户回复 `继续`，再进入 `trellis-update-spec`。
