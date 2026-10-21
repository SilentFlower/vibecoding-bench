# sqlite-utils 第二批场景规划

研究日期：2026-10-22。当前子任务处于 planning；本文不代表正式内容、原生验收或真实模型已通过。本次只读固定源码、旧证据，并运行一个隔离宿主微探针；未修改上游、正式项目库或产品，未运行完整回归、真实模型、OAuth、Git 写操作或生产操作。

## 结论与计数

建议 **4 场景／13 项独立业务任务**：understand 2、consult 3、diagnose 4、plan 2、modify 2，11 项非修改。两个修改分别处理 FTS 的一次性列迭代器和连续转换的同名回调复用；二者处于独立场景，不隐式共享修复。非修改题包含既有 API 足够、正常默认行为、材料不足，不能因为不改代码而判失败。

| 场景 | 业务范围 | 默认任务顺序 |
| --- | --- | --- |
| SQ-S01 | 将本地订单整理接入 Python／CLI，规划可重复导入 | SQ-U01、SQ-C01、SQ-P01 |
| SQ-S02 | 导入失败、类型推断、空值语义 | SQ-D01、SQ-D02、SQ-C02 |
| SQ-S03 | 搜索索引的生命周期、更新和迭代器故障 | SQ-U02、SQ-C03、SQ-D03、SQ-M01 |
| SQ-S04 | 数据转换的保留原值方案与回调隔离 | SQ-P02、SQ-D04、SQ-M02 |

任务表是业务去重后的规格，不把列表／tuple／generator、FTS4／5、触发器开关等验收矩阵拆成独立任务。SQ-D02 是库 API 首批推断导致的存储类型诊断，SQ-C02 是 CSV 的空串／NULL 策略，SQ-C01 只讨论产品适用性，不再次问如何保留前导零。

## 固定来源与实际读取

- 官方仓库：`https://github.com/simonw/sqlite-utils`；本地 `.deploy/real-project-review-20261021/sqlite-utils/`。
- 本次实际 `rev-parse HEAD` 为 **`9c66bafa52ae23d40499c74b0db3b635bcddb876`**，origin 为 `https://github.com/simonw/sqlite-utils.git`，`git status --porcelain` 为空。没有查询或引入当前上游的新版本。
- 固定 `pyproject.toml` 声明 4.2.1、Python >=3.10、Apache-2.0。实际 LICENSE SHA256：`c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`；pyproject SHA256：`ec133707085153fae34f663ec8934ec95a731575a2b3b7577347ec2de0ac432c`。正式快照保留完整 LICENSE、来源、版权头及任何适用归属，不将上游源码改写为玩具 app.py。
- Python 包 `sqlite_utils` 位于项目根；公开 CLI 脚本为 `sqlite-utils = sqlite_utils.cli:cli`，也可实际执行 `python -m sqlite_utils`。可复用共享回归默认 `implementation_dir=sqlite_utils, import_root=.`，正式套件仍须明确加入可信 SUITES 并在当前镜像校准，不能认为历史测试已经接入平台。
- 已实际读 `Database` 构造／事务／公开注册函数、`Table.enable_fts/populate_fts/rebuild_fts/convert/_convert_multi/upsert/upsert_all`、CLI `insert_upsert_implementation`、CSV 处理和 `utils.rows_from_file`，以及对应冻结测试。以下定位均相对固定 checkout：

| 源码／测试 | 本次确认的契约 |
| --- | --- |
| `sqlite_utils/db.py:538/569/654` | Database 封装 SQLite 连接；显式本地文件或 memory；`atomic()` 对嵌套使用 savepoint。 |
| `db.py:793`、`tests/test_register_function.py:87` | 同名、同 arity、`replace=False` 保留先前注册；`replace=True` 才替换。测试明确保护这种行为，docstring 中“throw an error”不能代替实际实现。 |
| `db.py:3754/3846/3890`、`tests/test_fts.py` | enable_fts 多次消费 columns；默认不建触发器；rebuild_fts 可重建索引；replace 相同配置需保持只读查询、不重复 DDL。 |
| `db.py:4177`、`tests/test_convert.py` | convert 包装当前 fn，却按 fn 的名字注册；lambda 特殊生成名字。支持 output、where/where_args、Falsey 值、JSON 输出；multi 为另一条路径。 |
| `db.py:5031/5069`、`docs/python-api.rst:1271` | upsert／upsert_all 按主键更新或插入；遗漏主键不能得到合理幂等匹配；没有整份无限输入天然原子承诺。 |
| `cli.py:1061/1230`、`docs/cli.rst:1346` | 没有 csv/tsv 开关时按 JSON；CSV 默认自动探测类型，空格不等于空字符串；`--empty-null` 显式转换空单元格。 |
| `docs/cli.rst:1383/1402` | `--type` 在新建表时覆盖类型；已有表类型不被相同导入参数改写，不能承诺补回已经丢失的前导零。 |

旧研究来源：`research/github-projects/sqlite-utils.md`、母任务 `research/data-candidates.md` 的 sqlite-utils 波次及 `.deploy/real-project-review-20261021/` 原始证据。旧文“verifier 仅 app.py”是历史状态，本次不按它推断当前产品缺陷。

## 当前新增的最小实证

使用既有研究 venv 的 Python 3.12.3／SQLite 3.45.1，`PYTHONDONTWRITEBYTECODE=1`、`python -B`、显式固定源码 PYTHONPATH，并断言实际 `sqlite_utils.__file__` 属于上述 checkout。一个短进程完成 13 条观察、总工具墙钟约 0.535 秒；真实临时数据库位于忽略路径并自动清理。原始 JSON：`.deploy/project-catalog-second-pack/research/sqlite-utils/micro-result.json`。

| 观察 | 实际结果 |
| --- | --- |
| CLI 把 CSV 当默认输入 | exit1，完整 `Invalid JSON - use --csv for CSV or --tsv for TSV files`；不是固定版 JSON 解析器 BUG。 |
| CSV 默认类型／空值 | code `001/002` 成 INTEGER `1/2`，空 note 是 `''`。 |
| CSV `--type code text --empty-null` | code 原样 `001/002`，空 note 是 SQL NULL。 |
| 库插入前200条整数，末条 `007` | 默认建 INTEGER，实际末值7；显式 `columns={'code': str}` 得 TEXT `007`。 |
| FTS 列表、不建触发器 | 之后新插入 violet 搜不到；rebuild 后能搜到。 |
| FTS 列表、建触发器 | 之后新插入 violet 立即能搜到。 |
| FTS 一次性 iterator、建触发器 | 原版 OperationalError `near ")": syntax error`，留下 notes_fts 表。 |
| state/country 连续 dict.get 转换 | state 正常，country 错为 NULL；两独立 lambda 对照正确。 |
| 公开同名 SQL 函数 | 默认继续返回 old，显式 replace=True 后返回 new。 |
| 两次相同 upsert_all | 两条唯一主键行；已有 memo=keep 保留，新行 memo=NULL，无重复行。 |
| convert 的 output＋where | 原 raw 两行保留；id1 normalized=CA，id2 normalized=NULL。 |

这不是目标 account 镜像、容器资源或新增验收器实测。FTS4／FTS5 × 触发器开关等初始创建矩阵和四种回调形式在旧原版记录可追溯，本次没有把它们冒称新镜像通过。

为避免把未知兼容问题加入M01，另运行一个只读最小CRUD对照，记录于同目录 `fts-crud-control.json`：固定原版列表＋触发器的 **FTS4 UPDATE 抛 OperationalError: SQL logic error**；FTS5 UPDATE后匹配violet、DELETE后匹配为空。此为独立旧触发器缺陷，不属于本批迭代器修复：C03业务明确FTS5；M01要求FTS4初始化／插入兼容，FTS5完整增改删；FTS4的既有UPDATE失败不被误写成已支持或必须随本任务修复。

## 通用内容、披露和验收约束

1. 每场景独立工作区，从相同固定原版开始。各任务都不硬依赖前一答案；表内 answer/code 均为 `[]`。诊断与修改问题相关，但修改首问重复提供完整已确认复现与契约，不能依赖诊断文字或另场景检查点。没有真实累计代码依赖就不造 code DAG。
2. 默认入口如上；SQ-S02 另有 `unavailable` 入口，只选 SQ-D01，提供“命令／样本／报错暂时无法提供”的初始说明；不可随后强行披露隐藏复现。SQ-S03 另有 `diagnose_only`（U02、C03、D03）及 `modify_direct`（仅 M01）；SQ-S04 另有 `diagnose_only`（D04）及 `modify_direct`（M02）。直接修改入口给足材料，仍从对应场景原版开始。
3. SQ-D01 是唯一必需按请求披露项。初始只给含糊症状、冻结版本及合成业务背景；完整命令、输入样本、stderr 只在确实请求证据后交付。材料 unavailable 可以以 `insufficient_information` 成功收口。通用 rubric 只要求依据实际已消费证据推理，不能提前把“忘 --csv”写成必答事实或无条件 source_evidence。
4. 所有非修改任务 `allowed_paths=[]`，通过不创建代码检查点。需要 runnable 示例的 SQ-C02 用唯一 Python fenced block，真实抽取并运行候选 API／CLI，比较实际 SQL 值与类型；不能挑多个片段中碰巧通过的一个。其他理解／方案的 native 只核事实或可行性，答案质量仍由私有语义 rubric 判断。无候选文件交付时不强制 candidate 文件证据。
5. 模型首问、材料说明、branches.when、rubric 英文；标题、场景、goal 中文。下文中文用户问题是产品文案，English prompt 是待冻结建议；源码／报错字面保留。所有资料合成，不读取真实订单或生产数据库。
6. 公共 library/tests 为上游证据；可信 verification/reference、原生业务和固定原生回归保持控制端隔离。实际 import 指向当前候选，SQLite 输出／文件字节或独立标准库对照作判据，不信候选自报通过。

## SQ-S01：本地订单处理的接入和重复导入

### SQ-U01 · understand · 理解 Python API、CLI 与 SQLite 文件的数据路径

- 用户问题：这个项目做什么？命令行导入订单后，Python 为什么能读同一份数据，是否需要另起数据库服务？
- English prompt：`Explain this pinned project's purpose and trace the supplied local order import from its CLI entry through Database and Table to the SQLite file. Compare the Python and CLI entry points and identify what persists after the process exits. Do not edit files.`
- 材料／披露：完整 CLI 命令、两条订单 CSV、Python 查询片段和临时文件路径；无隐藏／无需 unavailable，材料齐备。
- 合法结论：`understood`；本地库和CLI封装SQLite，不虚构数据库守护进程或托管服务。
- 正常／反例：真实导入后用新Python进程及标准库 sqlite3 读相同行；memory 数据库重新打开不保留是反例。不能以对象内存等于SQLite文件持久性。
- 授权／依赖：`[]`；answer=[]、code=[]。

### SQ-C01 · consult · 判断单机数据整理与共享应用的适用边界

- 用户问题：单机每日报表、浏览器多人编辑、分布式任务调度这三种需求，哪种可直接用此项目？
- English prompt：`Assess this pinned library for a single-writer local reporting script, a browser-based multi-user editing application, and distributed job scheduling. Explain which requirements its current APIs cover and which require application components. No library change is requested.`
- 材料／披露：三个明确分开的需求选项，单机项只处理本地合成CSV；无隐藏／无需 unavailable。
- 合法结论：`advice_no_code_change`；API/CLI足够单机整理，多人界面和分布式调度需应用架构；不得把SQLite描述为绝对不能多连接，也不得声称此项目自带Web授权和任务执行器。
- 正常／反例：本地原生导入／查询成功作正见证；固定源码入口和文档核未提供这些应用组件。语义边界由私有评审核，短程序不能证明所有分布式性质。
- 授权／依赖：`[]`；answer=[]、code=[]。

### SQ-P01 · plan · 规划保留已有字段的可重复订单导入

- 用户问题：同一日文件会重跑，更新已有订单数量、补入新订单，又不能擦掉人工备注，最小方案是什么？
- English prompt：`Plan a repeatable local order import using existing APIs. IDs are stable text keys, each input file contains unique IDs, later imports replace supplied quantity values, and omitted memo fields must be preserved. Explain validation, schema setup, reruns and recovery boundaries. Provide a plan only.`
- 材料／披露：完整主键／重复输入策略、已有 id/qty/memo 与两轮有限输入；无隐藏／无需 unavailable。这里已明确去重政策，不再制造不必要澄清。
- 合法结论：`plan_ready`；使用真实 upsert_all、明确TEXT主键，保留未提供列；可以建议合成副本校验和备份。不要求执行迁移或给无限数据全局原子承诺。
- 正常／反例：私有可行性见证两次相同输入结果仍2行、qty更新、memo保留；无主键普通insert导致重复、replace抹备注、已有错误INTEGER schema不能靠参数自动重建为反例。输出方案通过不等于真实迁移或性能测试完成。
- 授权／依赖：`[]`；answer=[]、code=[]。

## SQ-S02：导入诊断与数据语义

### SQ-D01 · diagnose · 先收集导入证据，再判断是否需要改库

- 用户问题：订单导入失败，是不是这个库坏了？
- English prompt：`Our order import failed. The command, input sample and complete error output have not been provided. Diagnose only as far as the evidence supports and request the smallest useful materials. Do not change files.`
- 材料／披露：初始只有症状和版本。请求命令、格式样本和完整错误后交付真实 `python -m sqlite_utils insert ... -`（漏 --csv）、CSV样本和完整 stderr；不提前给根因。unavailable 入口不提供这些材料。
- 合法结论：初轮请求材料；正常披露后 `diagnosed`／既有 --csv 解决，不改库；unavailable 为 `insufficient_information`。不因用户“是不是BUG”便编造确定根因。
- 正常／反例：披露后原命令JSON错误、加 --csv 导入并真实查询成功；合法JSON默认导入应通过。披露前只核材料状态和文件不变，不运行隐藏复现来要求答案猜原因。
- 授权／依赖：`[]`；answer=[]、code=[]。正常澄清不增加业务尝试。

### SQ-D02 · diagnose · 区分首批类型推断与前导零数据丢失

- 用户问题：前200条code为整数，最后一条字符串007读回7，是转换回调漏执行了吗？
- English prompt：`The supplied library importer inserts 200 integer code values followed by the string '007'; the final value reads back as 7. Diagnose the result from table creation, batch inference and SQLite affinity. Show a safe prospective input/schema policy and explain the limits of recovering already-lost zeros. Do not change the library.`
- 材料／披露：完整生成器、默认batch参数、schema、末行真实值；无隐藏／无需 unavailable。
- 合法结论：`diagnosed`／无需默认改库；既定首批schema和SQLite亲和性说明现象，明确新表TEXT策略及既有数据恢复需源资料。
- 正常／反例：原版默认INTEGER→7，显式columns code:str→007；末值为普通非数文本及已有TEXT表作对照。不能仅检查 `str(7)=='7'` 便伪称原值已恢复，不许不经授权修改类型推断全局默认。
- 授权／依赖：`[]`；answer=[]、code=[]。

### SQ-C02 · consult · 用现有 CLI 明确空串和 NULL 的导入政策

- 用户问题：空单元格要作为SQL NULL，非空文本和数字不乱改，是否需要改解析器？
- English prompt：`Using the supplied CSV, show one runnable Python example that invokes the pinned CLI to import empty cells as SQL NULL while preserving nonempty values. Compare the default behavior and name the existing option. Use only temporary synthetic files and do not edit repository files.`
- 材料／披露：两行CSV使用普通整数id和note列，明确“只有零长度单元格是NULL，单个空格仍是文本”的需求；无隐藏／无需 unavailable。不在此重复前导零问题。
- 合法结论：`advice_no_code_change`，唯一Python示例实际调用CLI --csv --empty-null；可用sys.executable -m sqlite_utils，不依赖猜测的CLI可执行文件位置。
- 正常／反例：默认空串、开关后IS NULL，非空／空格保留；完整 SQL 类型及值验证。没有开关的关键词解释、把空格strip为NULL、把非空0置空均拒绝。
- 授权／依赖：`[]`；answer=[]、code=[]。

## SQ-S03：搜索索引维护与一次性列配置

### SQ-U02 · understand · 解释内容表、全文索引和触发器的职责

- 用户问题：notes和notes_fts为什么同时存在？建索引是不是会替换订单正文表？
- English prompt：`Trace enable_fts for the supplied notes table. Explain the content table, FTS virtual table, initial population and optional triggers, and how Table.search reads matching results. Distinguish configuration from copying or replacing the business table. Do not edit files.`
- 材料／披露：两个合成记录、列表columns、schema摘要；无隐藏／无需 unavailable。
- 合法结论：`understood`；依据 enable_fts/populate_fts/search 的真实路径解释。
- 正常／反例：建索引前后业务行及未索引字段字节不变，检索只匹配选择列；非索引字段含关键词不应被搜到。索引内部表数量随FTS版本不同，不硬编码成通用业务事实。
- 授权／依赖：`[]`；answer=[]、code=[]。

### SQ-C03 · consult · 选择触发器或显式重建来同步全文搜索

- 用户问题：列表建索引后新写入的数据搜不到，要加自动同步能力吗？
- English prompt：`A list-based FTS5 enable_fts call succeeded, then a later insert was not searchable. Recommend the smallest existing-API setup for ongoing writes and a separate rebuild procedure for an existing index. Explain the default and operational tradeoffs without changing the library.`
- 材料／披露：明确FTS5、create_triggers=False、列表输入、先建后写的时线；无隐藏／无需 unavailable，和D03的建索引失败是不同问题。
- 合法结论：`advice_no_code_change`，新建时create_triggers=True或受控重建；不能对已经有索引直接重复普通 enable_fts 并声称无条件安全。
- 正常／反例：FTS5原版新插入漏搜→rebuild后搜到，带触发器新建后增／改／删匹配同步；原本已经带触发器仍漏搜不能套用该解释。真实SQLite结果核对，不只查触发器名称。不将此成功结论泛化为FTS4的更新／删除保证。
- 授权／依赖：`[]`；answer=[]、code=[]。

### SQ-D03 · diagnose · 定位列配置迭代器耗尽导致的建索引失败

- 用户问题：同样text列用列表成功、iter列表失败并留下fts表，为什么？
- English prompt：`The attached list-based FTS setup succeeds, but replacing the same column list with a finite one-shot iterator fails with a SQL syntax error and leaves an FTS table. Diagnose the exact consumption path and suggest a caller workaround. Do not modify files.`
- 材料／披露：两种输入及真实traceback／表清单，同样版本和数据；无隐藏／无需 unavailable。
- 合法结论：`diagnosed`，连接第一次SQL格式化、populate和可选触发器消费同一迭代器的因果；临时caller固定有限列列表，不将所有 Iterable 泛称不可用。
- 正常／反例：固定原版列表成功、iterator失败，FTS4／5＋触发器开关在实施时补全；列表建成功后新行搜不到的C03是独立现象，不能错判本任务为缺触发器。
- 授权／依赖：`[]`；answer=[]、code=[]。

### SQ-M01 · modify · 使有限一次性列配置与列表建索引行为一致

- 用户问题：修复enable_fts接受一次性列配置，保持正常搜索及既有选项。
- English prompt：`Fix enable_fts so a finite one-shot iterable of column names behaves like the equivalent list or tuple throughout table creation, initial population and optional triggers. Preserve FTS4/FTS5, tokenization, quoted identifiers, replace semantics and existing public APIs. FTS4's existing update-trigger error is a separate known limitation and is outside this change; preserve successful FTS5 insert/update/delete behavior. Add focused regressions within the allowed paths.`
- 材料／披露：完整公开最小失败、列表对照、兼容边界；直接修改入口同样给足；无隐藏需求／无需 unavailable，参考补丁私有。
- 合法结论：目标行为修复、测试和完整适用回归通过后接受代码。
- 正常／反例：list／tuple／iter／generator同列序；FTS4／5及触发器开关、初始命中与后续INSERT；FTS5还核SQL UPDATE／DELETE真实命中。FTS4以固定列表的已知UPDATE异常作兼容边界，不要求此任务修掉。空业务表、含空格列名及tokenize、replace相同配置不发新DDL、变化配置仍正确。禁止吞SQL错返回self、只修populate但仍耗尽triggers、禁用所有触发器、修改测试或只对text特判。正常错误如不存在列不必被“修复”为成功。
- 兼容边界：输入明确有限，不承诺无限列流；只处理重复迭代输入的缺陷，不顺带修复FTS4既有更新触发器错误、不引入所有DDL失败的全事务保证、不自动清理用户既存故障索引。columns materialize发生在DDL前的实现自然避免枚举阶段局部写，但不得将其扩大为本批数据库事务重构。
- 授权：`library/sqlite_utils/db.py`、`library/tests/test_fts.py`。不许改环境、SQLite扩展、CLI、私有verification／reference或可信回归。
- 依赖：answer=[]、code=[]；对应场景独立原版，不继承SQ-M02。
- 冻结上游冲突预案：实际已读 `test_enable_fts_replace_does_nothing_if_args_the_same` 和 legacy quoted schema测试，均应保留。当前未识别有意必须改变的上游断言；参考若失败先修参考，不删节点或改期望。只有确证契约冲突才暂停准入、回到子任务设计审查，不把失败包成skip。

## SQ-S04：数据转换的业务方案与回调复用故障

### SQ-P02 · plan · 规划保留原始列的选择性标准化

- 用户问题：只先处理id1、保留raw和其他记录，怎样先做试点、核对后再扩大范围？
- English prompt：`Plan a small normalization pilot using existing Table.convert options. Preserve the raw column, write a separate normalized column, restrict the pilot using bound WHERE parameters, and define checks before expanding. Use the supplied pure conversion and synthetic rows; do not implement a migration.`
- 材料／披露：raw=ca/ny两条、id1试点、纯大写转换、不删除raw的完整要求；无隐藏／无需 unavailable，不依赖D04的隐藏知识或已修复状态。
- 合法结论：`plan_ready`，output、where／where_args可行；明确未处理行新列为NULL，回调异常按实际事务边界处理，不假装DDL创建和全迁移天然一起回滚。
- 正常／反例：控制端见证raw保持、id1 normalized=CA、id2 NULL；全表覆盖raw、手工拼业务值进where、承诺已执行迁移为反例。这里不要求返回可执行代码，不把事实探针当语义答案通过。
- 授权／依赖：`[]`；answer=[]、code=[]。

### SQ-D04 · diagnose · 解释第二个转换误用第一个同名回调

- 用户问题：州映射成功，随后国家映射全变NULL，明明字典中有US，是数据错了吗？
- English prompt：`The attached state conversion succeeds, but the following country conversion using a different dict.get returns NULL despite a valid mapping. Diagnose the callback registration path in the pinned code, compare the lambda control, and show a safe caller workaround without changing files.`
- 材料／披露：两套完整映射、两列原值、连续调用、真实输出、lambda对照；无隐藏／无需 unavailable。
- 合法结论：`diagnosed`；Table.convert包装命名和Database注册去重导致旧回调继续生效；不是把US数据直接判无效。caller用不同lambda或不同实际函数名是有边界的现有办法。
- 正常／反例：dict.get第二转换country=NULL、lambda正确；旧记录另有partial／callable object／同名函数的原版证据。单次映射、不同函数名和multi路径不能一律声称必坏。
- 授权／依赖：`[]`；answer=[]、code=[]。

### SQ-M02 · modify · 确保连续转换使用当次传入的回调

- 用户问题：修复同名／无名可调用转换串用旧映射，同时保护公开注册函数的替换策略。
- English prompt：`Fix Table.convert so each invocation uses the callable passed to that invocation, including consecutive dict.get, partial, callable-object and same-named function cases on the same Database. Preserve output, WHERE bindings, falsey values, lambda handling, multi conversion and the public register_function replace contract. Add focused regressions within the allowed paths.`
- 材料／披露：完整两个独立映射、不同列与跨表对照、正常lambda、公开register_function默认与显式replace行为；直接修改入口同样自足，参考私有；无额外隐藏／无需 unavailable。
- 合法结论：私有原生和完整适用回归通过才接受代码；允许实现选择本次受控注册替换或不同内部注册名，不硬编码参考方案。
- 正常／反例：四类可调用对象连续变换、跨表共用Database、同一回调重复调用；实际state和country均正确，False/0/空串仍交给回调，output、where/where_args和未选行保持。lambda、multi、回调异常传播／既有事务行为对照保持。公开register_function同名默认仍返回旧SQL函数，replace=True才替换；粗暴修改其默认、按列名特殊处理、把未知映射一律填固定字符串、静默吞异常均拒绝。
- 兼容边界：只纠正convert的当前fn被旧注册遮蔽，不更改Database公共注册默认、不添加连接全局reset、不重设所有现存SQL函数、不改SQLite/CLI默认。这里不新增任意递归调用convert、跨线程同连接同时修改的支持承诺；输入为正常同步纯映射。
- 授权：`library/sqlite_utils/db.py`、`library/tests/test_convert.py`、`library/tests/test_register_function.py`，控制端恢复冻结上游tests后执行回归；候选改公开测试不能改变验收。
- 依赖：answer=[]、code=[]；本场景从固定原版开始，与SQ-M01无代码父链。
- 冻结上游冲突预案：`test_register_function_replace` 明确期待默认不替换，禁止通过改测试／跳过化解。`test_convert_repeated`、Falsey、where/output/multi既有断言应全过。当前没有已证明的必需不兼容断言；参考与任何冻结节点冲突先修参考，确需改变产品契约则暂缓该目标并提规划审查。

## 离线环境、资源与适用回归

- 实际运行依赖来自固定pyproject：click>=8.3.1、click-default-group>=1.2.3、pluggy、python-dateutil、sqlite-fts4、tabulate、pip。pytest／hypothesis为适用原生测试工具。历史freeze为click8.5.0、click-default-group1.2.4、pluggy1.7.0、python-dateutil2.9.0.post0、sqlite-fts4 1.0.3、tabulate0.10.0、pytest9.1.1、hypothesis6.170.5及iniconfig/packaging/Pygments/six/sortedcontainers；这些是可复用锁来源，**还不是当前account镜像的离线wheel合同**。构建后端setuptools>=77只按实际安装方式冻结，不无条件把全部dev/docs依赖塞入业务环境。
- 旧完整宿主结果实际读取 `baseline-result.json`：1497 passed、16 skipped、0fail/error，25.01秒、291700KiB峰值，Python3.12.3／SQLite3.45.1。16项为3个本机缺sqlite3ext.h无法编译ext.c、1个缺pandas/numpy、12个缺SpatiaLite；必须按实际nodeid和reason在当前镜像确定适用性，不能按“固定16skip”盲继承，也不能为全绿删除失败节点。
- 旧镜像 `v3-ci-39482854683-1` 的FTS／convert／register_function相关75项在256MiB无网UID1000下通过，不是完整1497项在256MiB通过；本次未重复运行。当前基线是首批使用的 `ci-39609484070-1`／Python3.12.15，sqlite引擎特性、PythonABI、FTS4/5、插件、完整nodes、结果和skip必须重新实测冻结。
- 业务探针维持小数据、无网、UID1000、只读候选和独立临时目录，拟沿用business256MiB／30秒；是否足够需当前镜像实测。完整回归旧RSS已高于256MiB且耗时接近30秒，应使用既有regression资源profile的受控上限校准；不得增加账号1536MiB配额，也不得把所有测试挪到business后靠超时重试碰运气。新环境的上限以真实测量后写入profile，不在规划伪造固定可通过数值。
- 新可信suite必须收集非空逐节点合同、保留Python／插件／baseline摘要和适用结果；完整适用回归至少覆盖本冻结源码的全部可运行上游测试，不只两类目标的75项。Optional extension是否纳入要依据目标镜像现有能力和内容边界，不为本地测试改宿主系统或下载任意扩展。

## 可复用、待实测和障碍

**可复用**：固定干净源码／完整许可证、旧逐文件来源记录、15组旧原版复现与本次13条新观察、完整历史skip清单、共享根包布局与离线wheel机制、首批只读证据及隐藏材料修正经验。

**待实测**：正式schema材料／英文rubric、两个独立参考和错误候选反例、原版失败／参考通过、FTS4/5初始化及插入／FTS5更新删除、完整当前镜像节点及资源、wheel逐SHA与真实import、SQ-D01正常披露及unavailable、答复示例执行、全部默认／必要分支的真实产品链路mock及中文页面。任务路径数与13个唯一任务分开统计，模型调用必须保持0。

**技术障碍**：当前尚未证明完整上游回归适合哪个既有profile；16个旧skip要校准为真实当前能力；SQL函数公开默认必须与convert内部修复隔离。新发现的FTS4既有UPDATE触发器错误已作为明确限制保留，不捆绑成第三个修改。没有已证实需要新增平台schema、执行协议、UI或账号配额的阻断。若当前镜像缺本批所需FTS4/5，则暂停该项目准入并记录真实障碍，不换模拟搜索、不偷偷缩减目标。
