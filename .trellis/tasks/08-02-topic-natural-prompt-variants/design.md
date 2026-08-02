# Topic 自然提示词变体 - 技术设计

## Architecture

本任务在现有 topic 创建链路中增加一个轻量的 `prompt_mode` 请求字段，不改 topic、task、batch 或 run 数据库结构。完整数据流如下：

```text
WebUI mode control
  -> FastAPI Pydantic DTO(prompt_mode)
  -> build_topic_prompt(topic, prompt_mode)
  -> tasks.prompt / task_batch_items.prompt
  -> Scheduler task payload
  -> worker TASK_PROMPT
```

数据库中的最终 `prompt` 文本继续作为实际下发内容的唯一事实来源。自然模式只在创建任务时随机选择一次模板；创建完成后，调度、重试、批次恢复和详情查看均复用持久化文本，不重新渲染。

## Prompt Mode Contract

API 使用两个固定值：

- `natural`：从多种人工编写的结构模板中随机选择一种，保留标题、分类、描述、可运行 MVP、启动方式、验证方式和主要取舍等现有语义。
- `canonical`：保持当前固定五段式 prompt，供正式横向 benchmark 和抓包对比使用。

请求 DTO 默认值：

| 创建入口 | 默认模式 | 用户可选 |
| --- | --- | --- |
| 单任务 `TaskIn` | `natural` | 是 |
| 批次 `BatchIn` | `natural` | 是 |
| 定时养号 | `natural` | 否，内部固定 |
| 抓包 `CaptureRunIn` | `canonical` | 是 |

后端使用 Pydantic 字面量约束模式值，非法值由 FastAPI 返回 422。自定义 `prompt` 非空时继续原样优先，`prompt_mode` 不再处理该文本。

## Prompt Rendering

`build_topic_prompt()` 保持单一生成入口，新增模式参数：

- 规范模式沿用现有输出，避免已有 benchmark 语义漂移。
- 自然模式维护至少 5 个结构明显不同的静态模板；模板只重排已有信息并改变语气，不增加技术方案、依赖选择、超时策略或实现步骤。
- 模板集合定义在后端单一常量中，不在各路由复制拼接逻辑。
- 不使用运行时 LLM 改写，不修改 600 条 topic 描述，不把 prompt 原文写入日志。

自然模式的随机结果无需新增 `variant_id` 数据列：现有 `tasks.prompt` 和 `task_batch_items.prompt` 已完整保存实际文本，比只保存随机种子更直接。历史 task/run 保持不变，也不需要迁移。

## Warmup Consistency Fix

当前养号流程在 `_create_task_and_run()` 中生成并持久化 prompt，随后 `trigger_account()` 再次调用生成器构造 worker payload。引入随机模板后，两次调用可能选择不同结果。

调整为：

1. `trigger_account()` 生成一次自然 prompt。
2. 把该 prompt 传给 `_create_task_and_run()` 持久化。
3. 同一个字符串放入 `scheduler.submit()` 的 task payload。

该变更建立“生成一次、存储一次、下发同一文本”的明确契约。

## WebUI

单任务弹窗、批次表单和抓包表单各增加一个原生 radio 分段控件：

- 选项显示为“自然”和“规范”。
- 单任务、批次默认选中自然；抓包默认选中规范。
- `FormData` 读取 `prompt_mode` 并原样提交给对应 API。
- 控件使用现有终端实验室 CSS 变量、无圆角、稳定高度和宽度；不引入框架、构建工具或运行时校验库。

## Compatibility

- 老 API 客户端不传 `prompt_mode` 时使用 DTO 默认值。
- 自定义 prompt 行为不变。
- `_SCHEMA`、`init_db()`、`scripts/sync-topics-db.py` 和 `topics.md` 均不修改。
- 已持久化的 task、batch item 和 run 不受影响。
- 批次暂停/恢复继续读取 `task_batch_items.prompt`，不会重新抽取模板。

## Rollback

回滚时移除 DTO 字段、自然模板和 WebUI 控件，并把调用恢复为现有单参数 `build_topic_prompt(topic)`。由于没有 schema 或数据迁移，历史记录无需处理。
