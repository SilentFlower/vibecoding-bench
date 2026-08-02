# Topic Prompt Contract

> Topic 默认提示词的生成模式、API 字段、持久化事实来源和调度一致性契约。

## Scenario: Topic 提示词模式与持久化一致性

### 1. Scope / Trigger

- 当单任务、批次、定时养号或抓包 run 根据 topic 生成默认 prompt 时，必须遵循本契约。
- 当新增 prompt 表达模式、修改 WebUI 模式控件或调整任务创建与调度链路时，必须同步检查本契约。
- `prompt_mode` 只控制创建时的默认文本表达，不进入数据库 schema；已持久化的最终 `prompt` 才是后续调度、恢复和查看的事实来源。

### 2. Signatures

后端类型与生成入口：

```python
TopicPromptMode = Literal["natural", "canonical"]

def build_topic_prompt(
    topic: dict,
    mode: TopicPromptMode = "natural",
) -> str:
    ...

def _resolve_topic_prompt(
    topic: dict,
    prompt_override: Optional[str],
    mode: TopicPromptMode,
) -> str:
    ...
```

请求 DTO 与默认值：

| API | DTO | `prompt_mode` 默认值 | 响应关键字段 |
| --- | --- | --- | --- |
| `POST /api/tasks` | `TaskIn` | `natural` | `id` |
| `POST /api/task-batches` | `BatchIn` | `natural` | `id` |
| `POST /api/captures/run` | `CaptureRunIn` | `canonical` | `run_id`、`task_id`、`capture_mode`、`model_override` |
| 定时养号内部调用 | `WarmupScheduler.trigger_account()` | 固定 `natural` | `started`、`run_id`、`task_id` |

### 3. Contracts

- `natural`：从后端静态模板集合中随机选择一种；模板数量不得少于 5，且必须保留标题、分类、描述、可运行交付、启动、验证和主要取舍语义。
- `canonical`：稳定输出规范五段式文本；同一 topic 重复生成必须完全一致，供正式 benchmark 和抓包对比使用。
- `prompt_override` 为非空字符串时必须原样优先，不能再调用模式渲染器。
- WebUI 的单任务和批次表单默认选择 `natural`，抓包表单默认选择 `canonical`；请求字段名必须统一为 `prompt_mode`。
- 单任务、抓包和养号的最终文本写入 `tasks.prompt`；批次逐项文本写入 `task_batch_items.prompt`。
- 随机自然 prompt 每个任务只生成一次。数据库记录、`scheduler.submit()` payload、批次恢复和详情查看必须复用同一最终字符串。
- 不新增 `variant_id`、随机种子或 `prompt_mode` 数据库列，也不修改 `topics.md` 和 topic Markdown 解析契约。
- Topic prompt 不承载超时、工具权限、认证恢复、网络策略或 worker 收尾指令，这些继续由 harness / worker 负责。

### 4. Validation & Error Matrix

| 条件 | 预期行为 |
| --- | --- |
| API 未提交 `prompt_mode` | Pydantic 使用对应 DTO 默认值 |
| API 提交 `natural` 或 `canonical` | 正常创建并持久化最终 prompt |
| API 提交其它模式值 | FastAPI/Pydantic 返回 422，不进入创建逻辑 |
| 内部直接调用 `build_topic_prompt()` 传入未知模式 | 抛出中文 `ValueError` |
| `prompt_override` 非空 | 原样返回覆盖文本，忽略 `prompt_mode` |
| topic 分类为空 | 使用 `未分类` |
| 自然模式重复调用 | 允许选择不同模板，但每次产物内部语义必须完整 |
| 规范模式重复调用 | 输出必须完全一致 |

### 5. Good / Base / Bad Cases

- Good：正式横向 benchmark 显式传 `canonical`，得到稳定 prompt；抓包默认即为该模式。
- Good：养号先生成一次自然 prompt，再把同一字符串传给 `_create_task_and_run()` 和 `scheduler.submit()`。
- Base：旧 API 客户端不传字段，单任务和批次自动使用 `natural`，抓包自动使用 `canonical`。
- Base：用户提交自定义 prompt，最终持久化文本与用户输入完全一致。
- Bad：自然模板增加指定框架、依赖、架构或超时策略，导致不同模板不再语义等价。
- Bad：持久化前生成一次、调度前再次生成一次，导致数据库记录与 worker 实际输入不一致。

### 6. Tests Required

- 单元测试遍历自然模板，断言模板不少于 5、互不相同，并包含 title、category、description、启动、验证和取舍语义。
- 单元测试重复调用 `canonical`，断言结果与规范文本完全一致。
- DTO 测试断言 `TaskIn` / `BatchIn` 默认 `natural`、`CaptureRunIn` 默认 `canonical`，非法值触发 `ValidationError`。
- 覆盖优先级测试 mock `build_topic_prompt()`，断言非空自定义 prompt 不调用渲染器。
- 养号回归测试断言 `tasks.prompt == scheduler.submit()` payload 中的 `prompt`。
- 静态契约检查核对三个 WebUI 表单的 `name="prompt_mode"`、选中默认值和 `app.js` 请求体字段。
- 提交前运行 Python 编译、后端单元测试、`node --check webui/app.js`，并在暗色、亮色和窄屏下检查分段控件。

### 7. Wrong vs Correct

#### Wrong

```python
created = self._create_task_and_run(account, topic)
task = {"prompt": build_topic_prompt(topic, "natural")}
```

持久化与下发各自随机生成，两个字符串可能不同，历史记录无法复现 worker 的真实输入。

#### Correct

```python
prompt = build_topic_prompt(topic, "natural")
created = self._create_task_and_run(account, topic, prompt)
task = {"prompt": prompt}
```

随机选择只发生一次；同一个最终字符串同时用于存储和下发。
