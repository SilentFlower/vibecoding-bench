# sqlite-utils：二十步真实工程迭代路线

研究日期：2026-10-21。来源为 [simonw/sqlite-utils](https://github.com/simonw/sqlite-utils)，固定提交 `9c66bafa52ae23d40499c74b0db3b635bcddb876`，包版本 4.2.1。工程规模、依赖成本及上游完整测试见 [首轮研究](./sqlite-utils.md)。

结论：可以在同一个真实仓库内安排 **20 个可分别交付的改进**，其中 **9 步修复已复现的问题，11 步增强现有功能**。原先两步只是首轮核实的范围。下面的新增功能均有上游需求来源；接口名称和兼容策略是本试点的路线提案，不代表上游已经承诺采用。

本轮已经核对相关源码、原生入口和测试，并保存原版行为证据；尚未实现这二十步，也未制作或执行修复后的二十套冻结验收。本文件不等于生产项目库已经接入。

## 二十步交付清单

每行是一次完整工程迭代，包含实现、本步验收和此前能力回归。测试、文档和错误重试都包含在对应步骤内，不单独计步。

| 步骤 | 实际交付 | 上游来源 | 冻结提交上的现状 | 完成时的主要验收 |
| --- | --- | --- | --- | --- |
| 01 | 全文索引接受一次性列迭代器 | [#902](https://github.com/simonw/sqlite-utils/issues/902) | 迭代器被重复消耗，填充索引报 SQL 错误 | 列表、元组、生成器的 FTS4/FTS5 查询与增删改同步结果相同 |
| 02 | 连续数据转换正确使用本次回调 | [#910](https://github.com/simonw/sqlite-utils/issues/910) | 同名回调复用旧转换，第二列被写成 NULL | dict.get、partial、同名函数及可调用实例连续转换结果正确 |
| 03 | 自动识别单列 CSV | [#907](https://github.com/simonw/sqlite-utils/issues/907) | 姓名文件无法识别；URL 文件被字母切列 | 单列保持一个字段，常用分隔符的多列输入继续正确识别 |
| 04 | 导入完整保留引用字段内的换行 | [#895](https://github.com/simonw/sqlite-utils/issues/895) | CSV/TSV 中 CRLF、CR 被替换成 LF | Python 读取和 CLI 导出再导入均保留字段内容 |
| 05 | TSV 和自动识别路径正确传递额外字段策略 | [#892](https://github.com/simonw/sqlite-utils/issues/892) | TSV 设置忽略或收集额外字段仍抛 RowError | 三种入口遵守相同的忽略、收集、默认报错策略 |
| 06 | 含 NULL 列的统计结果准确、稳定 | [#887](https://github.com/simonw/sqlite-utils/issues/887) | 错误计数、NULL 与字符串排序崩溃、NULL 显示为字符串 | 高频／低频计数正确，NULL 不变成文本，同频排序稳定 |
| 07 | 部分 upsert 保留省略字段 | [#878](https://github.com/simonw/sqlite-utils/issues/878)、[#873](https://github.com/simonw/sqlite-utils/issues/873) | 单行受 NOT NULL 阻断；混合字段批次覆盖旧值为 NULL | 单条／批量都区分省略字段和显式 NULL，保留已有有效值 |
| 08 | 日期配方统一处理解析溢出 | [#857](https://github.com/simonw/sqlite-utils/issues/857) | IGNORE、SET_NULL 对超大年份仍抛 OverflowError | 两种日期配方遵守错误策略，默认模式仍抛出异常 |
| 09 | 迁移在跨集合执行前核对停止条件 | [#870](https://github.com/simonw/sqlite-utils/issues/870) | 拒绝后一个已应用目标前，前一个集合已提交 | 无法满足 stop-before 时，先前待执行集合和迁移记录均不改变 |
| 10 | CSV/TSV CLI 提供额外字段处理选项 | [#444](https://github.com/simonw/sqlite-utils/issues/444)、[#890](https://github.com/simonw/sqlite-utils/issues/890) | Python 有策略，CLI 没有对应开关且默认截断 | CLI 能显式收集、忽略或拒绝多余字段，并正确报告互斥参数 |
| 11 | query／rows 支持显式 SQLite URI | [#650](https://github.com/simonw/sqlite-utils/issues/650) | 当前公开接口无对应 uri 选项 | mode=ro 能读且拒绝写，带空格／非 ASCII 路径正确打开 |
| 12 | 提供 SQL 函数注销接口 | [#589](https://github.com/simonw/sqlite-utils/issues/589) | 有注册接口，无对应公开注销方法 | 指定名称和参数个数的回调移除后不能再调用，之后可重新注册 |
| 13 | 按唯一字段获取单条记录 | [#588](https://github.com/simonw/sqlite-utils/issues/588) | get 只接受主键值 | 按字段返回唯一匹配；无匹配与多匹配都有明确结果，值通过参数绑定 |
| 14 | Python API 直接流式导出 CSV | [#580](https://github.com/simonw/sqlite-utils/issues/580) | CLI 支持导出，Table 无对应公开方法 | 调用方文件对象获得正确表头、列顺序、Unicode 和引用字段 |
| 15 | 建表时声明单列 UNIQUE 约束 | [#558](https://github.com/simonw/sqlite-utils/issues/558) | 已有内部约束生成和保留逻辑，公开 create 无 unique 参数 | 创建后真实 SQLite 拒绝重复值，多个列分别生效且遵守 NULL 语义 |
| 16 | insert-files 在入库前转换字段 | [#597](https://github.com/simonw/sqlite-utils/issues/597) | 必须先导入，再单独运行 convert | 单命令压缩文件内容后入库，解压校验一致，原始大小和元数据正确 |
| 17 | 从 JSON 指定顶层键选择记录数组 | [#489](https://github.com/simonw/sqlite-utils/issues/489) | 外层对象作为一条记录导入，无显式选取开关 | 选择 List 数组导入两条记录；键缺失或值类型不符时清楚报错 |
| 18 | create-table 支持 SELECT 查询结果建表 | [#481](https://github.com/simonw/sqlite-utils/issues/481) | 当前命令必须给列名／类型，无 sql 选项 | 聚合／过滤查询生成实际表和数据，失败时无半成品目标表 |
| 19 | rows 支持逐条键值展示 | [#535](https://github.com/simonw/sqlite-utils/issues/535) | 当前无 transpose 选项 | 宽表按记录展示，列筛选、行顺序与 limit/offset 仍准确 |
| 20 | 直接流式导入 gzip 压缩 CSV/TSV | [#318](https://github.com/simonw/sqlite-utils/issues/318) | 当前导入命令没有压缩输入选项 | 文件和标准输入均可解压导入，损坏压缩流报错，结果与未压缩输入相同 |

## 每步的边界与回归重点

### 01—05：索引、回调与输入保真

1. **FTS 迭代器**：一次修复覆盖列输入的列表、元组、一次性生成器，FTS4/FTS5，以及有／无同步触发器。初次查询和触发器下的新增、更新、删除都属于本步，不拆成多个计数。关联 `db.py:Table.enable_fts`、`populate_fts`；原生测试 `tests/test_fts.py`。
2. **转换回调隔离**：在两列及两张表连续调用，覆盖同名和不同名函数、lambda、dict.get、partial、可调用实例。保留 `Database.register_function` 原有 replace 行为，不能通过全局改写注册规则规避问题。关联 `db.py:Table.convert`、`Database.register_function`；原生测试 `tests/test_convert.py`、`tests/test_register_function.py`。
3. **单列 CSV**：将自动探测限制为合理分隔符，并给无分隔符文本确定的单列规则；覆盖 `memory` 原生 CLI。显式传入 dialect 的能力要回归。本步不擅自改变用户主动请求的 `insert --sniff` 行为。关联 `utils.py:rows_from_file`、`cli.py:memory`；原生测试 `tests/test_rows_from_file.py`、`tests/test_cli_memory.py`。
4. **引用字段换行**：覆盖 CRLF、CR、LF、CSV、TSV、自定义分隔符和引号，按 SQLite 实际读回值验收。Python 帮助函数和 CLI 独立读取路径都要修复。关联 `utils.py:rows_from_file`、`cli.py:insert_upsert_implementation`；原生测试 `tests/test_rows_from_file.py`、`tests/test_cli_insert.py`。
5. **额外字段参数传递**：CSV、TSV、自动识别入口均覆盖 ignore_extras、extras_key 及二者互斥；默认继续报 RowError。自动识别的回归输入要足以确定分隔符，不能把探测异常误计为参数修复。本步只修已有 Python 参数；第 10 步另提供用户此前没有的 CLI 控制。关联 `utils.py:rows_from_file`；原生测试 `tests/test_rows_from_file.py`。

### 06—10：数据正确性和可控导入

6. **NULL 统计**：一次处理三个相关症状：单值捷径错误、同频比较崩溃、NULL 转成字符串。保留 `count(distinct column)` 不计 NULL 的现有含义；同频非 NULL 值沿用既有排序，NULL 在同频组内置后。检查 CLI 展示和 `--save` 持久结果。关联 `db.py:Table.analyze_column`、`cli.py:_analyze`；原生测试 `tests/test_analyze.py`、`tests/test_analyze_tables.py`。
7. **部分更新**：将 #878 和 #873 合并为一个用户承诺：每条 upsert 只改变明确提供的字段。验证 NOT NULL、混合字段批次、复合主键、同一主键重复出现的顺序和新记录插入；显式 None 仍应赋 NULL 并受真实约束限制。不能借机屏蔽应当失败的新记录约束。关联 `db.py:Table.upsert_all`、`build_insert_queries_and_params`；原生测试 `tests/test_upsert.py`、`tests/test_atomic.py`。
8. **日期解析**：parsedate 和 parsedatetime 同时覆盖 IGNORE、SET_NULL、默认抛异常及正常日期。默认异常仍可追踪到原始原因。关联 `recipes.py`；原生测试 `tests/test_recipes.py`。
9. **迁移预检**：在任何待迁移集合执行前，检查所有 stop-before 目标是否存在、是否已经执行；覆盖限定／非限定名称、多个目标、多个集合。核对表和 `_sqlite_migrations` 的真实状态。本步修停止条件预检，不扩大为任意迁移错误下的全局事务；既有非事务迁移契约继续成立。关联 `cli.py:migrate`、`migrations.py:Migrations.applied`；原生测试 `tests/test_cli_migrate.py`、`tests/test_migrations.py`。
10. **CLI 额外字段策略**：拟新增 `--extras-key KEY`、`--ignore-extras`、`--strict-fields`，三者互斥；CSV/TSV 都支持，短行按原规则处理。显式 strict 才改变额外字段的报错选择，以兼容上游已断言的默认截断行为；帮助说明默认结果和新选项。收集到的列表按现有 JSON 值入库规则保存。基于第 05 步共享已修复的处理语义，覆盖 insert/upsert 共用入口；原生测试 `tests/test_cli_insert.py`、`tests/test_upsert.py`。

### 11—15：数据库与 Python API 增强

11. **SQLite URI**：拟增加显式 uri 参数，并让 query／rows 可通过 `--uri` 使用它；不根据普通路径中的问号暗中改变连接语义。使用本地临时数据库验证 `file:...?...`、mode=ro 的读写约束，以及 URI 转义和普通路径回归。暂不承诺把全部 CLI 子命令在本步改造。关联 `db.py:Database.__init__`、`cli.py:query/rows`；原生测试 `tests/test_constructor.py`、`tests/test_cli.py`、`tests/test_rows.py`。
12. **函数注销**：拟增加 `Database.unregister_function(name, arity)`；名称加参数个数确定目标，同时移除本地注册缓存，以便相同签名重新注册。其他参数个数和其他函数不受影响；明确重复注销结果。SQLite 拒绝旧调用且重新注册返回新结果才算通过，只改缓存不算。关联 `db.py:Database.register_function`；原生测试 `tests/test_register_function.py`。
13. **字段取单行**：拟扩展 `Table.get` 的关键字过滤形式，如 `get(name="entries")`。保留现有位置主键形式；没有匹配抛现有 NotFoundError，多条匹配、无过滤条件或同时传主键与过滤条件时明确拒绝。值通过 SQL 参数绑定，列名正确引用；含 NULL 条件按 IS NULL 处理。检查单列和复合唯一条件，避免静默任取一行。关联 `db.py:Table.get/rows_where`；原生测试 `tests/test_get.py`。
14. **Python CSV 导出**：拟增加 `Table.export_csv(...)`，写入调用方提供的文本文件对象，支持指定列序和过滤参数，逐行输出且不关闭外部对象。空表仍有表头；Unicode、逗号、引号和多行字段可由标准 csv.reader 正确解析；NULL 采用 CSV 的空字段表示，不宣称 CSV 能无损保留所有 SQLite 类型。已有 CLI CSV 输出做一致性回归。关联 `db.py:Table.rows_where`、`cli.py:_execute_query`；原生测试 `tests/test_rows.py`、`tests/test_cli.py`，实现时新增专门用例。
15. **建表 UNIQUE**：拟对公开建表 API 增加 `unique=["email", ...]`；每个列分别唯一，不将列表误解为复合约束。复用已有内部 UNIQUE 表达能力，保留当前变换流程对约束的处理。核对 sqlite_master、PRAGMA 及实际重复插入异常；NULL 遵循 SQLite 规则。非法列名需清楚拒绝，已存在表的 if_not_exists 不悄悄增加约束。关联 `db.py:Table.create/Database.create_table/create_table_sql`；原生测试 `tests/test_create.py`、`tests/test_transform.py`、`tests/test_create_table_parser.py`。

### 16—20：日常数据工作流增强

16. **文件入库前转换**：拟给 insert-files 增加 `--convert`、`--import`，以包含文件内容和元数据的 row 为输入，要求返回一条字典记录；复用现有转换编译机制。用标准库 zlib 实际压缩再解压验证，覆盖文件、目录及 stdin；原始 size、路径、哈希等元数据按转换前计算，转换明确修改的字段按返回值入库。关联 `cli.py:insert_files`；原生测试 `tests/test_insert_files.py`、`tests/test_cli_convert.py`。
17. **JSON 数组键**：拟新增 `--json-key KEY`，第一版只选顶层明确命名的键，不实现通用 JSONPath。正常数组、空数组、缺失键、非数组值及非对象元素都要验收；默认导入一个 JSON 对象的既有能力回归。上游提过自动猜键，本路线选显式参数以避免有多个数组时猜错。关联 `cli.py:insert_upsert_implementation`；原生测试 `tests/test_cli_insert.py`、`tests/test_upsert.py`。
18. **查询建表**：拟新增 `create-table --sql SELECT`；与列名／类型及不能用于 CTAS 的建表约束参数互斥。核对普通 SELECT、聚合、WITH、零行结果、带特殊字符的表名、目标表冲突，以及 SQL 错误下的表状态。复用现有 --ignore／--replace 的显式冲突选择，不能隐式删表。关联 `cli.py:create_table`；原生测试 `tests/test_create.py`、`tests/test_cli.py`。
19. **逐条展示**：拟新增 `rows --transpose`，按记录输出可辨识的字段／值，而不挤成宽表；保持列选择、WHERE、排序、分页的查询结果。定义 NULL、多行文本和空结果的稳定展示；与 CSV/TSV/JSON 数组等冲突输出参数同时使用时拒绝。该步是 CLI 展示能力，不增加网页或外部渲染依赖。关联 `cli.py:rows` 和输出处理；原生测试 `tests/test_rows.py`、`tests/test_cli.py`。
20. **gzip 导入**：拟新增 `--gzip`，覆盖显式 CSV/TSV 文件及标准输入，用 Python 标准库流式解压。接受同一压缩／未压缩输入并核对实际行值；覆盖编码、引用字段换行、额外字段策略以及损坏压缩流。前面第 04、10 步的能力在这里组合回归。第一版不包含压缩导出，也不自动识别其他压缩格式。关联 `cli.py:insert_upsert_implementation`；原生测试 `tests/test_cli_insert.py`，实现时新增压缩输入用例。

## 累计推进和验证方式

所有步骤在同一工作目录、同一真实工程上累计修改，通过一个就形成一个检查点。可以采用 01—05、06—10、11—15、16—20 四段展示；这些是内容分组，不是人为制造的功能依赖。第 10 步依赖第 05 步的字段策略；第 20 步组合第 04、10 步，其他改动的工程顺序通过累计回归约束。

控制端冻结本步验收和此前已接受能力的回归，不将验收脚本交给候选修改。验收要实际导入候选源码，调用原生 Python／CLI 并查询 SQLite；删除候选自己的测试或自行打印成功不能推进。每步首轮失败后的修复属于同一步，只有全部验收通过才计一个完成步骤。

本步测试、必要回归和文档在一次交付中完成。上游完整测试已有 1,497 通过、16 跳过的原版基线；后续应依据修改范围选测试，阶段末或涉及共用写入逻辑时运行完整适用集合。完整集合的隔离资源预算仍需另行实测，不能把本轮快速观察的耗时当成未来每步验收耗时。

本路线均围绕现有 SQLite、CLI 和 Python API，预计可使用当前运行依赖及标准库；没有安排前端构建、独立数据库、向量服务或新增必需云依赖。真实实现可能揭示更大影响，届时调整对应验收范围并保留变更记录，不用通过减少回归维持名义步数。

## 本轮观察证据与限制

证据在 `.deploy/real-project-review-20261021/`：

- `open-issues-page1.json`、`open-issues-page2.json`：GitHub 官方 API 返回的开放问题正文和来源链接，已排除 PR。
- `roadmap-baseline.py`、`roadmap-baseline-result.json`：检查二十步的原版行为及公开接口缺口。共 46 条观察：26 个缺陷表现、11 个增强接口缺口、9 个通过的对照；第 01、02 步沿用此前已执行并保存的复现结果，其余观察本轮执行。
- `roadmap-20.json`：本路线的结构化研究清单。它是研究文件，不是已经被 ProjectLibrary 接受的 project.json。
- `roadmap-evidence-sha256.json`：本轮证据和研究文档摘要。

第 01—09 步均已有原版失败复现。第 10—20 步通过上游请求、源码和对应公开接口检查确认缺口；现有 SQL、CLI 或用户自己编写 Python 的替代方式仍可能实现相同业务，这些步骤提供的是正式、可复用的便捷入口。接口缺失本身不是缺陷复现，更不代表新增接口的实现已经验收。

不纳入本路线：首批推断类型对 `007` 的既有转换策略、针对旧 3.x 的问题、明确面向 v5 的破坏性变更、需要额外重型依赖的扩展，以及仅修文字／CI 的维护项。没有为满足数量把一个缺陷的测试维度拆成多个步骤。

当前平台仍需要原生项目入口、离线依赖准备和独立原生验收适配；详见首轮研究。二十步路线能够支持较长的工程维护过程，但现阶段不能宣称已在线上完成二十步运行。
