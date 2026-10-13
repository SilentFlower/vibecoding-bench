# v3 任务额度门禁与全英文内容改造 — 技术设计

## 1. 变更边界

本任务在一个版本中交付两条共同影响新 run 的链路：账号阈值决定普通 run 是否允许创建 worker；英文题库与 prompt 生成决定允许启动后注入 Claude 的内容。两条链路共用 `orchestrator/main.py`，因此统一实施和验证，避免拆分版本产生中间态。

现有事实入口：

- `QuotaGuard.warmup_snapshot/admit/_resume_account`、`Scheduler._execute/_mark_quota_wait` 和 `warmup_quota_decision` 管理额度阈值与等待恢复。
- `accounts.warmup_quota_*_limit_percent` 与 `warmup_quota_admissions` 已持久化既有设置和养号单次机会。
- `topics.md` 由 `main.load_seed_topics()` 和 `scripts/sync-topics-db.py` 两套解析器消费。
- `build_topic_prompt()` 生成 natural/canonical 默认 prompt；`images/worker/entrypoint.sh` 注入 resume、wrap-up、auth retry 和 API stall 文本。

## 2. 额度策略设计

### 2.1 兼容接口

数据库不改列名，避免为语义重命名制造迁移风险：

```text
accounts.warmup_quota_5h_limit_percent INTEGER NULL
accounts.warmup_quota_7d_limit_percent INTEGER NULL
warmup_quota_admissions(...)  # 仍只记录养号的单次正式请求机会
```

配置 DTO 与 `/api/accounts/{aid}/warmup` 继续接受原字段。公开账号摘要可保留 `warmup_quota` 兼容字段，同时增加或改用语义化的 `quota_policy` 视图；两者必须来自同一份判定，不能分别读取导致状态漂移。

### 2.2 判定模型

把通用阈值计算与养号单次机会分开：

```text
QuotaGuard.policy_snapshot(account, workload, source=None, quota_state=None)
  workload = normal | warmup

QuotaGuard.admit(account, source, workload=None) -> bool
```

- `normal`：可信窗口命中阈值或任一启用窗口未知/到期均 blocked；不认领 `warmup_quota_admissions`。
- `warmup`：沿用现有 `sample_required/sample_used` 和持久认领逻辑。
- `None`：抓包、继续对话及其它入口只走共同额度耗尽保护。

底层可复用 `warmup_quota_decision()`，但对外命名和文案不得继续宣称普通任务不受控制。为减少一次性重构，可保留旧方法作为兼容 wrapper，核心判定只实现一份。

### 2.3 调度状态流

```text
create run (queued)
  -> Scheduler._execute 取得账号 owner 锁并重读配置/额度
  -> policy blocked: _mark_quota_wait，无 worker、无 CLI 租约
  -> policy allowed: 进入原 credentials sync / running / start_run

quota_wait
  -> QuotaGuard.tick 消费被动观察或手动额度查询
  -> 仍 blocked: 保持原记录
  -> allowed: 原 run quota_attempt+1，恢复 queued，复用 task/prompt/workspace/身份
```

`run_kind='normal'` 传 `workload='normal'`，`warmup` 传 `workload='warmup'`，`capture` 不传。批次 run 沿用 normal；某项等待时批次状态改为 `quota_wait`，恢复后继续原批次。阈值只在 worker 启动前检查，所以已经 running 的 run 不接收暂停信号，正常收尾后才阻止后续 run。

普通任务的等待消息优先使用 policy snapshot；共同额度耗尽、账号永久错误和用户停止仍保持更高优先级。身份变化继续转 `auth_failed`，不能把旧身份等待 run 自动交给新身份。

## 3. 英文题库设计

### 3.1 Markdown 格式

新格式：

```markdown
# Vibecoding Project Library: 600 Ideas

## 1. Command-Line Tools (20 topics)

- [ ] 1. **Markdown Renderer**: Build a CLI that ...
```

两套解析器共享等价规则，兼容旧格式 `## 一、分类（20 题）` 和新格式 `## 1. Category (20 topics)`。条目继续兼容半角/全角冒号，但新文件统一半角 `:`。实现增加交叉测试，防止 main 首次 seed 与同步脚本解析结果不一致。

### 3.2 安全替换与校验

| ID | 旧方向 | 新方向 |
| ---: | --- | --- |
| 39 | AI 写作风格迁移 | Editorial Tone Consistency Checker，不模仿具体个人或受保护作品 |
| 73 | 多站点自动签到 | Recurring Routine Reminder，不登录第三方账号或处理验证码 |
| 76 | 抢课/抢号页面监控 | Public Event Availability Digest，只使用公开/样例 feed，不自动预订 |

`validate_topics()` 新增字段级 CJK 检查和固定英文高风险短语检查。校验只针对 title/category/description，不限制 Markdown 代码块或代码注释。风险词命中失败关闭并打印题号，不在同步时自动改写内容。

### 3.3 翻译质量

- 题号、功能范围和验收语义保持不变；技术名词如 CSV、OAuth、WebSocket、SQLite 保留标准拼写。
- 每条描述使用完整英文句子，包含主要输入、核心处理和可观察输出，避免只把标题直译后留下空泛模板。
- 21 个分类使用稳定英文词汇，并同步更新 prompt style 分类关键词。
- 对每个分类抽样首尾题人工复核，另外完整复核安全扫描命中和固定替换题。

## 4. 英文 prompt 设计

`build_topic_prompt()` 保持输入/输出签名和 natural 随机去重算法，只替换文本资产：分类关键词、开场、需求、交付、报告、布局、canonical 模板、`Uncategorized` 与 fingerprint 占位符。

测试用英文标准 topic 验证 12 个候选都包含 title/category/description、runnable delivery、launch、validation 和 trade-off 语义；canonical 连续生成完全一致。

worker 四类默认提示逐字改为英文，shell 变量、触发条件和注入函数不变。测试从脚本提取默认值并断言无 CJK、包含各自必须语义；生产发布前只检查环境中是否存在覆盖键，不输出覆盖内容。

## 5. 数据同步与发布

1. 在临时 SQLite 复制现有 v3 schema、topics、tasks、runs，执行 `--validate-only`、dry-run 和 `--apply`。
2. 同步工具使用 SQLite backup API 生成一致备份，不只复制可能带 WAL 的主文件；现有 `topics.id` 通过 `no` 更新保持不变。
3. 对比同步前后：600 个 topic 字段变化；task/run 行数、prompt、账号、设置不变。
4. 构建同批 control/account 镜像，跑额度、prompt、worker、Docker 和浏览器验证。
5. 生产 v3 停机备份和镜像升级后，对 `/srv/vibebench-v3-us/bench/db.sqlite` 先 dry-run 再 apply；旧版 `/root/vibecoding-bench/data/db.sqlite` 不操作。
6. 生产检查 600 英文题、普通 run 阈值等待/恢复、旧服务容器身份不变。回滚需同时回退镜像和恢复题库同步前备份。

## 6. 取舍与风险

- 沿用旧 `warmup_quota_*` 列名可避免数据库迁移，但源码必须用注释和公开 DTO 解释其兼容含义。
- 普通 run 在未知额度时等待，牺牲无人值守启动率，换取不为探测额度而消耗一次完整任务；人工额度查询是明确恢复入口。
- 运行中任务不强停意味着实际已用比例可能越过阈值；页面必须说明阈值是后续入场门禁，不是硬消费上限。
- 全量翻译最主要风险是语义漂移和漏中文；通过解析器一致性、无 CJK、固定 ID、分类抽样和同步演练共同控制。
