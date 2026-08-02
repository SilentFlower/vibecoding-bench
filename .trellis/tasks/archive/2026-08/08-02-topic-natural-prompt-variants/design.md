# Topic 自然提示词变体 - 技术设计

## Architecture

`canonical` 路径保持现状；`natural` 路径升级为“分类风格 + 片段组合 + 近期指纹择优”：

```text
topic + prompt_mode
  -> 自定义 prompt 非空：原样返回
  -> canonical：稳定规范文本
  -> natural：
       分类映射
       -> 随机抽取多组片段组合
       -> 候选 prompt
       -> topic 专属字段归一化
       -> 与近期持久化指纹比较
       -> 选择最大相似度最低的候选
  -> tasks.prompt / task_batch_items.prompt
  -> Scheduler payload
  -> worker TASK_PROMPT 原样注入
```

数据库中的最终 prompt 继续作为唯一事实来源，不保存组合签名、相似度或模式元数据。

## Natural V2 Composition

后端维护四类独立片段：

- 分类风格开场：工程/命令行、产品/协作、数据/AI、创意/教育、通用回退。
- 需求表达：以不同句式承载 `description`。
- 可运行交付：用不同词汇表达当前工作区和可运行首版。
- 结果说明：用不同词汇和顺序表达启动、验证和主要取舍。

再通过多个布局模板改变信息顺序、段落数量和句子连接方式。候选生成只组合静态人工片段，不调用外部模型，也不增加技术栈、架构、依赖或超时要求。

候选池每次随机抽取 12 组不同组合，避免为单次创建物化全部组合；组合签名唯一，生成文本也必须唯一。

## Category Profiles

分类映射使用按优先级匹配的关键词规则：

| 风格 | 代表分类 |
| --- | --- |
| `engineering` | 命令行工具、自动化与脚本、开发者工具与工程平台、硬件/边缘、安全、运维测试 |
| `product` | 个人效率 Web、浏览器插件、协作、商业、行业工作台、团队知识、社区运营 |
| `data_ai` | AI 集成、数据可视化、AI Agent、数据运营与质量治理 |
| `creative` | 小游戏、内容创作、教育、创意实验 |
| `generic` | 未知、自定义或未命中分类 |

规则只影响表达语气，不改变需求内容。测试通过 `load_seed_topics()` 遍历现有分类，确认每个分类都能解析到已定义风格。

## Fingerprint And Similarity

指纹构造步骤：

1. 按长度从长到短，把 prompt 中当前 topic 的 `description`、`title`、`category` 替换为统一占位符。
2. 转为小写并移除空白、标点等非文字数字字符。
3. 对归一化文本生成 4 字符 n-gram 集合。

相似度使用 Jaccard：交集大小除以并集大小。候选风险分数为它与近期每个指纹相似度的最大值；选择风险分数最低的候选，平分时随机选择。无近期样本时直接从候选中随机选择。

近期窗口使用 `deque(maxlen=64)`，并缓存每条历史指纹的 n-gram set。批次内追加新指纹时自动淘汰最旧样本，因此单 item 比较量固定为 `12 × 64`，不会退化成随批次长度增长的二次复杂度。

该策略重点惩罚重复公共包装，不会因为两个题目的正文完全不同就误判为足够多样。

## Recent Prompt Query

新增只读 helper，接收现有 SQLite connection 并返回近期归一化指纹：

- 单任务/抓包/养号从 `tasks` 读取 `batch_id IS NULL` 的 prompt，关联 `topics` 获取专属字段。
- 批次从 `task_batch_items` 读取 prompt，关联 `topics` 获取专属字段。
- 两组按 `created_at` 合并排序并限制为最近 64 条。
- 自定义 prompt 或 canonical 路径不调用该查询。
- 只读查询不获取 `_db_lock`；所有值继续使用 `?` 参数占位。

## Call-Site Integration

- 单任务：读取 topic 时同时加载近期指纹，生成一次后写入 `tasks.prompt`。
- 批次：创建前加载一次近期指纹；每生成一个 item 后把其指纹追加到内存列表，再生成下一个 item。
- 养号：选定 topic 后加载近期指纹，生成一次，并把同一文本传给持久化和 `scheduler.submit()`。
- 抓包：默认 canonical 不读历史；用户显式选择 natural 时才加载近期指纹。
- 自定义 prompt：所有入口继续直接返回覆盖文本，不查询历史、不生成候选。

`build_topic_prompt()` 与 `_resolve_topic_prompt()` 增加可选近期指纹参数；默认空集合保持独立调用和测试兼容。

## Compatibility

- `TopicPromptMode`、三个 DTO、WebUI 字段和默认值不变。
- canonical 文本逐字不变，旧 API 客户端行为不变。
- 不修改 `_SCHEMA`、`init_db()`、`topics.md`、worker 镜像和调度 payload 结构。
- 已持久化的历史 prompt 不重写；它们只作为自然模式的只读比较样本。
- 查询或样本为空时自然模式仍可正常生成，不把多样性优化变成任务创建的硬依赖。

## Performance Budget

- 单任务、养号或 natural 抓包增加一次最多 64 行的本地 SQLite 只读查询。
- 批次无论包含多少 topic，都只查询一次历史，并在固定 64 条内存窗口中滚动更新。
- 真实 helper 本地复测中，12 个候选与 64 条历史的 4-gram Jaccard 比较约为 2.95ms/item；100 item 约 0.30 秒，600 item 约 1.77 秒。
- 该开销只发生在任务创建阶段，相比 worker 的分钟级运行时间可忽略；实现后仍需用真实 helper 做一次聚焦性能复测。

## Rollback

回滚时恢复第一阶段的完整自然模板集合，移除分类映射、指纹 helper、近期查询和调用点参数。由于没有 schema、迁移或历史数据写入，回滚不需要数据处理。
