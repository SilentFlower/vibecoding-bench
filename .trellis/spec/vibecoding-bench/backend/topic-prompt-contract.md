# Topic Prompt Contract

> Topic 默认提示词的生成模式、API 字段、持久化事实来源和调度一致性契约。

## Scenario: Topic 提示词模式与持久化一致性

### 1. Scope / Trigger

- 当单任务、批次、定时养号或抓包 run 根据 topic 生成默认 prompt 时，必须遵循本契约。
- 当新增 prompt 表达模式、修改 WebUI 模式控件或调整任务创建与调度链路时，必须同步检查本契约。
- 当修改 `topics.md`、题库同步工具或 worker 自动注入提示时，必须同时遵守英文内容、安全扫描和历史 prompt 不回填约束。
- `prompt_mode` 只控制创建时的默认文本表达，不进入数据库 schema；已持久化的最终 `prompt` 才是后续调度、恢复和查看的事实来源。

### 2. Signatures

后端类型与生成入口：

```python
TopicPromptMode = Literal["natural", "canonical"]

def build_topic_prompt(
    topic: dict,
    mode: TopicPromptMode = "natural",
    recent_fingerprints: Optional[Sequence[frozenset[str]]] = None,
) -> str:
    ...

def _resolve_topic_prompt(
    topic: dict,
    prompt_override: Optional[str],
    mode: TopicPromptMode,
    recent_fingerprints: Optional[Sequence[frozenset[str]]] = None,
) -> str:
    ...

def _load_recent_topic_prompt_fingerprints(
    conn: sqlite3.Connection,
    limit: int = 64,
) -> deque[frozenset[str]]:
    ...

parse_topics(path: Path) -> list[Topic]
validate_topics(topics: list[Topic], require_followups: bool = True) -> None
backup_db(path: Path) -> Path
```

请求 DTO 与默认值：

| API | DTO | `prompt_mode` 默认值 | 响应关键字段 |
| --- | --- | --- | --- |
| `POST /api/tasks` | `TaskIn` | `natural` | `id` |
| `POST /api/task-batches` | `BatchIn` | `natural` | `id` |
| `POST /api/captures/run` | `CaptureRunIn` | `canonical` | `run_id`、`task_id`、`capture_mode`、`model_override` |
| 定时养号内部调用 | `WarmupScheduler.trigger_account()` | 固定 `natural` | `started`、`run_id`、`task_id` |

### 3. Contracts

- `topics.md` 固定包含 600 题、编号集合 1～600 和 21 个英文分类；分类、标题、描述不得含 CJK。明确风险目标和已知机器直译短语由 `validate_topics()` fail-closed，不能在同步时静默改写。
- 题库主题按用户选择排除模型训练／微调、网络协议／代理／网络扫描与安全，以及生物／医疗；同时排除逆向/反编译和所有大模型客户端、API 集成、训练、微调、蒸馏；普通文件遍历、课程练习、经典算法与引用关系图保留。`validate_topics()` 的 `_EXCLUDED_TOPIC_PATTERNS` 检查分类／标题／初始描述及全部补充，匹配时非零退出并报告题号，不静默替换。该范围是题库偏好，不代表服务商的违规判定。
- 原安全分类改为 `Organization and Recordkeeping Tools`，30 个原编号保持；分类中的 Recordkeeping 映射到 `product`，其余生成／同步契约保持。
- `natural`：英文分类风格、开场、需求表达、可运行交付、结果说明和布局片段组合候选；每次随机抽取 12 个不同组合，且每个候选都必须保留英文标题、分类、描述、当前工作区可运行交付、启动、验证和主要取舍语义。
- 分类风格只改变表达语气，不改变需求内容；现有分类归并为 `engineering`、`product`、`data_ai`、`creative`，未知分类使用 `generic` 回退。
- 自然候选必须先把当前 topic 的 `description`、`title`、`category` 按长度降序替换为统一占位符，再移除空白和标点并生成 4 字符 n-gram 集合。
- 候选风险分数是它与近期每条指纹的最高 Jaccard 相似度；选择风险分数最低的候选，平分时随机选择，无历史时直接随机选择候选。
- 近期窗口固定为 `deque(maxlen=64)`。历史只读查询合并 `tasks.prompt`（`batch_id IS NULL`）和 `task_batch_items.prompt`，关联 `topics` 获取专属字段，不获取 `_db_lock`，不新增 schema 或外部依赖。
- 单任务、养号和显式 `natural` 抓包各读取一次近期窗口；批次创建只读取一次，并在每个 item 选定后立即把其指纹追加到同一窗口。相似度比较量固定为每项 `12 × 64`。
- `canonical`：稳定输出 `Topic`、`Category`、`Description` 和英文 MVP/报告说明；同一 topic 重复生成必须完全一致，供正式 benchmark 和抓包对比使用。
- `prompt_override` 为非空字符串时必须原样优先，不能再调用模式渲染器或读取近期历史；`canonical` 同样不得读取近期历史。
- WebUI 的单任务和批次表单默认选择 `natural`，抓包表单默认选择 `canonical`；请求字段名必须统一为 `prompt_mode`。
- 单任务、抓包和养号的最终文本写入 `tasks.prompt`；批次逐项文本写入 `task_batch_items.prompt`。
- 随机自然 prompt 每个任务只生成一次。数据库记录、`scheduler.submit()` payload、批次恢复和详情查看必须复用同一最终字符串。
- 未分类回退固定为 `Uncategorized`，指纹弱化占位符固定为 `topic content`；默认包装不能在英文 topic 外重新引入中文。
- 新 Markdown 分类标题使用 `## 1. Category (20 topics)`；首次 seed 与同步解析器仍兼容旧 `## 一、分类（20 题）`，条目兼容半角/全角冒号。两个解析器必须对同一文件得到相同 category/title/description。
- 同步工具默认 dry-run，`--apply` 前使用 SQLite backup API 生成包含已提交 WAL 数据的一致备份，再按 `topic.no` 原位更新。既有 `topics.id`、task/run 数量和已持久化 prompt 不得变化。
- 不新增 `variant_id`、随机种子或 `prompt_mode` 数据库列。历史 task/run prompt 不翻译、不回填；`prompt_override` 和未来显式环境覆盖原样保留。
- Topic prompt 不承载超时、工具权限、认证恢复或网络策略。worker 的 resume、timeout wrap-up、OAuth retry 和 Claude API stall 默认注入文本必须为英文，重试次数、优先级和退出码保持不变；定时补充模式的短预算收尾时刻按下文时间契约冻结，其它路径的触发时机保持。

### 4. Validation & Error Matrix

| 条件 | 预期行为 |
| --- | --- |
| API 未提交 `prompt_mode` | Pydantic 使用对应 DTO 默认值 |
| API 提交 `natural` 或 `canonical` | 正常创建并持久化最终 prompt |
| API 提交其它模式值 | FastAPI/Pydantic 返回 422，不进入创建逻辑 |
| 内部直接调用 `build_topic_prompt()` 传入未知模式 | 抛出中文 `ValueError` |
| `prompt_override` 非空 | 原样返回覆盖文本，忽略 `prompt_mode` |
| topic 分类为空 | 使用 `Uncategorized` |
| 未知 topic 分类 | 使用 `generic` 风格生成，不能阻塞任务创建 |
| 自然模式无历史样本 | 从 12 个语义完整候选中随机选择 |
| 存在高相似近期样本 | 优先选择最高历史相似度更低的候选 |
| 批次包含多个 topic | 历史只查询一次，后续 item 可见本批次已选指纹，窗口始终不超过 64 |
| 自定义 prompt 或 `canonical` | 不查询历史，不生成自然候选 |
| 自然模式重复调用 | 允许选择不同组合，但每次产物内部语义必须完整 |
| 规范模式重复调用 | 输出必须完全一致 |
| 题库不是 600 条、编号不完整或分类不是 21 个 | `validate_topics()` 非零退出，不访问数据库 |
| 分类/标题/描述含 CJK、高风险目标或已知机器直译短语 | 校验失败并报告题号，不自动改写 |
| 模型训练、DNS proxy、网络扫描、安全或生物医疗主题 | 校验失败并报告用户排除主题，不访问数据库 |
| 普通天气样例、普通文件扫描、课程证书或引用关系图 | 通过主题范围校验，不按泛关键词误排除 |
| 英文分类标题 / 旧中文分类标题 | 两套解析器分别正常解析并保持相同结构 |
| `--apply` 处理 WAL 数据库 | SQLite backup API 备份包含已提交 WAL；更新后 topic ID 与历史 prompt 不变 |

### 5. Good / Base / Bad Cases

- Good：将 LAN Device Scanner 原编号替换为 Home Equipment Inventory，安全分类改为组织与记录工具；同步仍保留 topic ID 和历史 prompt。
- Bad：因 training 或 certificate 单词就删除课程练习，或把日常文件 scan 当网络扫描。Correct：检查完整领域表达，保留普通应用并用拒绝／保留两组测试验证。
- Good：正式横向 benchmark 显式传 `canonical`，得到稳定 prompt；抓包默认即为该模式。
- Good：养号先生成一次自然 prompt，再把同一字符串传给 `_create_task_and_run()` 和 `scheduler.submit()`。
- Good：批次开始前加载一次 64 条历史窗口，每生成一个 item 就追加其指纹，后续 item 自动避开近期同构包装。
- Base：旧 API 客户端不传字段，单任务和批次自动使用 `natural`，抓包自动使用 `canonical`。
- Base：用户提交自定义 prompt，最终持久化文本与用户输入完全一致。
- Base：已有 v3 数据库同步英文题库，只更新 600 个 topic 的 title/description/category/followups_json；历史任务继续展示原 prompt。
- Bad：自然片段增加指定框架、依赖、架构或超时策略，导致不同组合不再语义等价。
- Bad：把 `topics.md` 直接复制进已 seed 的运行实例，或用 `shutil.copy2` 备份活动 WAL 数据库，导致题库没有更新或备份不一致。
- Correct：先 `--validate-only` 和 dry-run，再由同步工具创建 SQLite 一致备份并 `--apply`；发布后回滚题库时仅定向恢复 topics，禁止整库覆盖新的运行或凭据。
- Bad：批次为每个 item 重查全部历史，或把全部已生成指纹无限追加，导致创建耗时随历史量或批次长度无界增长。
- Bad：持久化前生成一次、调度前再次生成一次，导致数据库记录与 worker 实际输入不一致。

### 6. Tests Required

- 单元测试生成 12 个自然候选，断言互不相同、无 CJK，并包含 title、category、description、当前工作区可运行交付、启动、验证和取舍语义。
- 遍历 `load_seed_topics()` 的 21 个现有分类，断言全部映射到已定义风格；未知分类断言使用 `generic`。
- 指纹测试断言不同 topic 套用相同公共包装时得到相同指纹，并覆盖 description 包含 title 的长字段优先替换。
- 选择器测试构造高相似与低相似候选，断言返回低风险候选。
- SQLite 测试同时写入普通 task 与 batch item，断言只返回最新 64 条指纹且顺序为从旧到新。
- 批次测试断言历史 helper 只调用一次，后续 item 依次看到本批次已追加的指纹。
- 单元测试重复调用 `canonical`，断言结果与规范文本完全一致。
- DTO 测试断言 `TaskIn` / `BatchIn` 默认 `natural`、`CaptureRunIn` 默认 `canonical`，非法值触发 `ValidationError`；自定义与 canonical 断言不读取近期历史。
- 覆盖优先级测试 mock `build_topic_prompt()`，断言非空自定义 prompt 不调用渲染器。
- 养号回归测试断言 `tasks.prompt == scheduler.submit()` payload 中的 `prompt`。
- 题库测试断言恰好 600 题、1～600、21 个英文分类、无 CJK/风险/机器直译短语，并核对 #39/#73/#76 的安全替换。
- 主题校验测试替换一条合法样本，分别验证训练模型／微调 LLM、DNS proxy、端口扫描、TCP、安全、生物和医疗被拒绝；天气 API、文件扫描、课程证书及引用关系图保持通过；现成 LLM 客户端/API 集成也应被拒绝。核对新 Recordkeeping 分类不落入 generic。
- 同步测试覆盖新旧分类标题、WAL 一致备份、按编号更新保留 topic ID 和历史 task prompt。
- worker 脚本测试提取四类默认注入文本，断言无 CJK，并包含各自的续跑、最小交付、OAuth 重试和 API 卡顿恢复语义。
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
recent = _load_recent_topic_prompt_fingerprints(conn)
prompt = build_topic_prompt(topic, "natural", recent)
created = self._create_task_and_run(account, topic, prompt)
task = {"prompt": prompt}
```

近期历史只读一次，随机选择也只发生一次；同一个最终字符串同时用于存储和下发。


## Scenario: 自包含题库与冻结的有限业务补充

### 1. Scope / Trigger

600 题均为英文初始需求及两条题目专属递进业务补充；编号 1～600、21 个分类块保持。`Writing and Document Workbenches` 与 `Rule-Based Workflow Workbenches` 替换原 AI 分类，映射 engineering。初始需求必须能在空目录开始，明确自建并标注合成记录、文件和图片/音频占位材料，无上传、外部账号、API Key、硬件或服务前提；高度依赖外部材料的题目改为本地工具或模拟器。关键词扫描只作门禁，不能代替逐题语义审查。

### 2. Signatures

- 共享模块 `orchestrator/topic_library.py` 提供 `Topic(no,title,description,category,followups=())`、`parse_topics`、`validate_topics`、`validate_followups`、`decode_followups`、`encode_followups`、`sample_followups`；seed 与同步脚本同源解析。
- SQLite 幂等增加 `topics.followups_json`、`tasks.followup_candidates_json`、`task_batch_items.followup_candidates_json`、`runs.followup_plan_json`，均为 `TEXT NOT NULL DEFAULT '[]'`。
- `POST /api/topics`、`PUT /api/topics/{id}` 的 `TopicIn.followups: Optional[list[StrictStr]]=None`；`GET /api/topics` 返回 `followups: list[str]`。
- `GET /api/runs/{rid}` 增加初始 `prompt` 与 `followups={planned,completed,phase,messages[,stage]}`。
- driver 调用 `python3 /usr/local/bin/v3-task-followups init|observe|advance --state <固定绝对路径> --project <主会话目录> [--resume] [--idle 10] [--no-next]`。
- `images/worker/task_followups.py` 提供 `read_dialogue(path: Path, offset: int = 0, include_queue: bool = False) -> list[dict]` 与 `latest_dialogue(project: Path, idle_seconds: float, baseline_path: Path) -> dict | None`；完成分类与阶段机共用。两种 worker 镜像均复制为 `/usr/local/bin/task_followups.py`，原命令 `/usr/local/bin/v3-task-followups` 为同文件链接；嵌入式分类器显式从该目录导入。

### 3. Contracts

Markdown 子行精确为 `  - Follow-up 1: <text>`、`  - Follow-up 2: <text>`，只进入独立字段，不能拼入初始 description。历史无子行解析为零补充，正式全量校验要求两条。消息最多两条、每条非空且最多 8000 字符，无 CJK、终端控制符或同题重复；编码后必须可往返解码，原文字面内容保持。

自然模式普通任务、批次及养号在创建初始 prompt 时冻结候选正文。每个新 run 等概率选择 0/1/2 的候选前缀，在同一 run 创建事务中保存正文；独立重复运行各选一次。canonical、非空自定义输入、抓包及历史空计划保持单轮。批次后改题不影响既有候选；QuotaGuard 与 Scheduler 以原 run 的计划为准，不重新抽签。worker 环境 `TASK_FOLLOWUPS_JSON` 默认 `[]`，`TASK_INITIAL_PROMPT` 保留原初始输入，不被 resume 控制提示覆盖。

时间快照为 NULL 的旧运行保留以下 schema 1 规则；新的定时模式见下节，不能向历史运行回填时间。

helper 的状态 schema 1 保存 run_id、规范 JSON 计划摘要、初始摘要、completed_stages、phase、session、各主 JSONL 字节 cursor、input_entry 与 reply_entry。phase 为 awaiting/pending/complete；总阶段数为 1+补充数。只识别主目录 JSONL 的对应普通 user 输入及其后稳定、非空、非 tool_use、非 synthetic/API 错误的最新 assistant；忽略 isMeta/isSidechain 与子目录。投递前落 pending 和新游标，tmux 成功不等于消费确认；observe 看到原主会话输入后才 acknowledged。pending 未确认重启必须失败，不能重发。最后阶段完成才可结束成功；完成状态也需重核最后输入/回复的原生证据。

user 正文只接受完整文本匹配，或去除外围空白后完整符合单层 `<pasted_content id="同一ID">\n正文\n</pasted_content id="同一ID">` 的消息；ID 为 1～128 位字母、数字、下划线或连字符，标签换行允许 CRLF。正文沿用两端 strip 后的精确比较，额外文字、错 ID、截断或并列包装不匹配。user 文本块列表仍须全部为有效 text；assistant 可混合 thinking/text，只提取有效 text，工具及 synthetic 判断独立，不能因含正文而放行。

JSONL 落盘顺序不代表对话顺序。`read_dialogue` 仅扫描保存字节游标之后的完整行，保留原字节 key/end；通过 uuid/parentUuid 及附件/元节点父链恢复依赖顺序。父链优先于时钟；全部对话均有有效带时区时间时，以时间排列无依赖节点，否则旧格式按文件顺序排列。重复对话 UUID、父链冲突或循环明确拒绝，不回退游标、不跨主会话读取旧工作。有 UUID 的阶段回复须能追溯至匹配输入；无 UUID 的旧格式保持兼容。逐次限长读取并跳过跨块长行，每次文件扫描限 64 MiB，超限须对账。

`latest_dialogue` 使用最新主文件、稳定窗口及 `COMPLETION_BASELINE` 对应的本次执行字节基线，返回逻辑最新消息。默认投递通过 `tmux send-keys -l --` 逐行输入，Ctrl+J 插入换行，末尾一次 Enter；含 Tab/CR 的正文保留括号粘贴，避免补全或提前提交。快速按键也可能被 CLI 包装，识别不能依赖传输方式；不加入随机人工节奏。

各轮复用原账号/cwd/session 和执行 deadline。停止、认证失败、额度暂停、总超时沿用既有优先级；收尾窗口或 CLI 已退出时禁止开始下一条，未完成补充不能标成功。额度恢复仍沿用既有每次尝试时限策略。v3 阶段文件是 `runtime/runs/<rid>/followups.json`，旧 worker 为工作区 `.bench-followups.json`；原子 0600 写入，拒绝错 run/计划/非法阶段、链接、特殊文件、超过 64KiB 的状态及会话截断。阶段扫描有界，不以工具大输出占满内存。

driver 已确认收尾回复或 CLI 退出后，`advance --no-next` 缺少匹配输入、正常回复或同阶段父链时返回 incomplete，保留未完成阶段，不继续等硬超时。`init/observe` 仍只观察；pending 恢复无消费证据仍明确失败，不能据此重发。

详情阶段缺失/损坏显示 unknown/invalid，不能冒充完成。页面只从冻结计划展示正文，使用 escapeHTML；topic 编辑缺省 followups 保留旧值，显式 [] 清空。状态摘要不扫描全部原生日志；成功判定由 worker 的证据核验负责。

### 4. Validation & Error Matrix

| 条件 | 行为 |
| --- | --- |
| 正式题库少子行、错序、重复或孤立子行 | 校验/解析非零退出，不能静默漏补充 |
| Topic API 非字符串列表元素 / 文本越界等 | Pydantic 422 / 业务校验 400 |
| 老数据库或历史任务 | 迁移默认 []；不回填旧 prompt/候选/计划 |
| 快照 JSON 损坏、null 或非法消息 | 明确拒绝；不吞掉为零补充 |
| pending 重启而无对应主输入 | 明确失败并保留现场，不重发 |
| 元消息、子代理、旧回复、工具或 synthetic 回复 | 不完成当前业务阶段 |
| 同 ID 的整体输入包装 / 额外文字或错误包装 | 前者精确确认，后者等待；advance --no-next 时明确 incomplete |
| thinking/text 混合回复 / 回复先于输入落盘 | 提取正文并按父链及时间恢复顺序，不漏判或重复推进 |
| 异根回复 / 父链循环、冲突或重复对话 UUID | 异根不完成；坏链明确拒绝，不能猜测顺序 |
| 错 run/计划、非法状态、会话截断或链接文件 | helper 非零退出；详情标无效 |
| 已进入收尾、CLI 已退出且尚有补充 | 不投新业务消息，不返回完整 success |
| 认证失败 / 额度耗尽 | 原 42 / 43 优先，原计划保持 |

### 5. Scenarios and Examples

- Normal：#257 首轮生成合成线索并评分排名；仅被选中时追加双日期窗口比较，再追加离线 HTML 对比报告。
- Base：选择零条的新 run 与历史 [] 都保持单轮；两条候选完整保存，但初始 prompt 不含后续正文。
- Incorrect：tmux paste 后重启，没找到该 user 输入就再发一次。Correct：保留 pending 并失败，人工核对原会话，避免重复业务需求。
- Incorrect：仅更新 topics.md 或在恢复时查询新题库。Correct：同步工具按 no 更新 topics 及 followups_json，历史 task/run 永远用自己的快照；同步代码须一起携带共享 topic_library.py。
- Incorrect：物理最后一条是 user 就一直等，或 thinking/text 混合就拒绝整个回复。Correct：两个消费者共用解析，按父链确认 user→assistant 的逻辑顺序，再校验正文、工具、错误和稳定窗口。

### 6. Tests Required

- 600/21/1200、完整编号、所有英文及排除主题、自启动合成样例要求、补充不出现在初始正文；逐题语义审查包含改题依据。
- 固定 0/1/2、同事务冻结、改题后普通/批次不漂移、养号候选、canonical/custom/旧记录零补充；quota payload 与实际下发原计划保持且不调用抽签。
- 阶段输入确认、旧回复/元/子消息排除、pending 不确定与确认后恢复、坏摘要/索引/链接/截断、收尾禁止新补充。
- 两个消费者对同一混合正文和原生乱序记录同时断言；覆盖 0/1/2 阶段、附件父链、倒序时钟、旧执行字节基线、无 UUID/时间、异根、坏链及完成后恢复复核；输入包装接受/拒绝矩阵、no-next 缺证据不空等。
- 实际按键多行保留空行、尾换行和字面字符，仅提交一次，Tab/CR 兼容输入不改变正文；原生 CLI 使用独立 HOME 与本地合成 SSE 核对真实格式，不能加载生产账号。
- `deploy/v3/run_local_verification.py --manifest <清单> [--followups-only]` 用正式 driver/tmux 与 CLI 替身断言 1/2/3 条输入、原 cwd/session、认证错误 42 且无补充、两种收尾及时以 124 退出且保留未完成。替身允许整体包装、thinking/text 混合及回复先落盘，区分 Ctrl+J 换行与 Enter 提交，并记录 keys/paste；错误样例包含结构化 error 字段。正式镜像还须核对模块/命令链接及 control driver 与被测源码一致。
- `deploy/v3/verify_stack.py --manifest <清单> --browser --topic-followups` 核对页面保存→API→SQLite、运行冻结正文、阶段摘要、XSS、1280/390px 明暗主题。替身和离线格式核对不能声称真实模型推理通过。

## Scenario: 随机时间投递与阶段证据

### 1. Scope / Trigger

自然模式普通、批量和养号创建新 run 时冻结随机投递时间；修改 worker 调度、额度恢复、JSONL 证据或详情 API/UI 时须同步核对本节。旧 run 的 NULL 时间快照继续使用旧阶段规则，不回填。

### 2. Signatures

```text
runs.followup_timing_json TEXT NULL
sample_followup_timing(messages: list[str], timeout_sec: int, wrapup_sec: int) -> str
decode_followup_timing(raw: str | None, count: int) -> dict | None
process(action, state_path, project, run_id, initial, followups,
        resume=False, idle_seconds=10, allow_next=True, timing=None) -> dict
v3-task-followups init|start|tick|observe|advance --state <绝对路径> --project <主目录>
                 [--resume] [--idle <秒>] [--no-next]
```

- 时间 JSON：`{schema:1,offsets_sec:[整数秒],timeout_sec:整数,wrapup_sec:整数}`。
- 环境 `TASK_FOLLOWUP_TIMING_JSON` 为空走旧模式；非空必须为有效对象，与正文数、`TIMEOUT_SEC`、`TIMEOUT_WRAPUP_SEC` 一致。
- 新状态 schema 2 保存原 run/正文摘要、`timing_digest`、`started_at`、`session/cursor`、`completed_stages/phase` 与 `items=[{status,cursor,queue_entry,input_entry,reply_entry}]`。
- 详情 `followups` 保留 planned/completed/phase/messages；定时模式增加 `mode="timed"`、`offsets_sec`、`started_at`、`delivered/consumed`、`items: list[str]`。公开 items 仅含状态，不返回证据键。

### 3. Contracts

- 次数仍等概率选择候选前缀 0/1/2。三个创建入口在原 run 事务中保存正文与时间：在 `[ceil(timeout*0.1),floor(timeout*0.6)]` 内无放回抽整数秒并排序，正文顺序不变。30 分钟为第 3～18 分钟，重复运行各抽一次。Scheduler、Runner、QuotaGuard 只读原快照。
- 有补充时冻结 `wrapup_sec=min(max(0,原设置),max(0,timeout-floor(timeout*0.6)-5))`，为轮询、提交和时钟取整留余量；零补充保持原收尾设置。
- init 捕获旧字节基线，初始需求实际投递后 start 一次固定 Unix 时钟。每轮先处理原停止/认证/额度/收尾/超时门禁，再 tick；初始主输入已确认且到点才保存 pending 并发送，不等待最终回复。首轮提前结束但仍有未来计划时继续等待。
- item 为 scheduled → pending → queued/consumed → completed。`type=queue-operation,operation=enqueue,sessionId=<主文件去后缀>` 的精确正文仅确认入队，须 include_queue=True 才读取；通用完成分类始终排除队列事件。普通主 user 才确认消费，正常最终 assistant 才确认完成；两条输入可共享同一最终回复，不要求逐条回复。
- 严格正文/整体包装、字节边界、父链、非工具/非 synthetic 和稳定窗口沿用前节。仅跟踪最多三条业务输入的祖先标记，避免平方内存增长。成功须通用分类及全部计划证据共同通过，计数和 phase 不能单独作为成功凭证。
- 恢复不重抽时间或时钟；暂停中到期的未发消息在新尝试门禁允许时依次投递，时限沿用既有尝试策略。原 CLI 内存队列无法跨进程保证保留，恢复时 pending/queued 无普通 user 必须失败、不重发。
- 已绑定主会话却找不到原初始输入时，init/observe/tick 立即拒绝并保留阶段文件原字节，不能将已消费/完成状态回退为等待。首次尚未绑定、输入未落盘时允许等待。
- 详情不扫描原生日志。已投递/消费/完成阶段的必需证据字段须为非空、非空白字符串；非 scheduled 条目须有有限正数时钟。运行后缺阶段文件为 unknown，损坏为 invalid；两者的 delivered/consumed/completed 均为 null，items 为 unknown。queued 尚未生成阶段文件可保持 not_started、投递/消费零及 scheduled。
- 前端显式展示 unknown/invalid 提示及待确认计数，不能显示成等待到点或确定完成；保留来自 DB 的目标时间及正文，继续 escapeHTML。不发送中断、不模拟人工输入节奏、不承诺降低账号限制风险。

### 4. Validation & Error Matrix

| 条件 | 预期行为 |
| --- | --- |
| 历史时间字段 NULL | 保留 schema 1，不回填、不重抽 |
| null/数组、时间数量/顺序/范围或执行预算不符 | 明确拒绝，不降级旧模式 |
| 到点仍忙 / 首轮提前结束 | 原队列投递 / 等待未来时刻，不中断、不提前成功 |
| 两条排队输入共同消费并得到一条正常最终回复 | 两条均可完成 |
| 重启只有 enqueue、无普通 user | 失败并保留现场，不重发 |
| 已绑定会话删除/截断/替换，原输入不可见 | 立即报错，原阶段字节不变 |
| 首次输入尚未落盘 | 正常等待 |
| queued 缺阶段文件 / 运行后缺文件 | not_started、零投递/消费 / unknown、全部计数 null |
| 空或空白证据、已执行阶段缺时钟 | invalid，不能冒充完成 |
| 停止、认证、额度、收尾、退出及硬超时 | 原门禁优先，禁止继续新增业务需求 |

### 5. Scenarios and Examples

- 正常：1800 秒任务冻结 `[300,780]`，第 5/13 分钟投递，原 cwd/session 保持；两条可以共享正常最终回复。
- 边界：零条保持单轮；短预算给最后计划点保留轮询余量；旧 NULL 运行仍按原回复边界执行。
- 错误：enqueue 就算已完成，或缺文件显示默认零值和等待到点。正确：分开传输、消费、完成证据，缺失显示未知。
- 错误：恢复时原输入已消失仍覆盖 phase=awaiting。正确：拒绝并保留原状态，不盲目重发。

### 6. Tests Required

- SQLite 核对三个创建入口、0/1/2、历史 NULL、窗口上界和短预算余量；恢复 payload 与原时间 JSON 一致，不调用抽签。
- helper 覆盖忙碌入队、提前空闲、共同回复、乱序/异根、初始落盘延迟、pending/queued 重启；对已消费/完成注入日志删除/截断/替换，断言 init/observe/tick 报错且原阶段字节保持。
- API 覆盖 queued/running/quota_wait/success 缺文件，空输入/回复/入队证据和缺时钟；正常分离计数、未知/无效空计数。真实浏览器覆盖文案、明暗/窄屏和 XSS。
- 正式 driver/tmux 覆盖提前空闲、忙碌两条及认证先停；可用 `--timed-followups-only` 定向执行。原生 CLI 在独立 HOME、断网和 localhost 合成 SSE 下只证明输入/队列，不冒称真实模型推理。
- 通过后端 unittest、Python 编译、shell/JS 语法；正式镜像的 helper/链接/driver 与源码一致。生产迁移和历史保留在发布后验收，不主动发起真实账号模型探测。
