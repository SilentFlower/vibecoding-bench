# CSVKit：二十步真实工程迭代路线

固定 [wireservice/csvkit@6d19c625214977ab2988e674441ca24638bc12d3](https://github.com/wireservice/csvkit/tree/6d19c625214977ab2988e674441ca24638bc12d3)，详见[单仓审查](./csvkit.md)。共 20 步：20 项增强提案。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．csvclean 输出稳定 JSONL 诊断（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1290
- 原版现状：已经在stderr输出机器可读CSV错误表，但没有JSONL格式、稳定错误代码和schema版本。
- 交付目标：新增--error-format=jsonl，输出行号、code、字段与消息，默认不含整行值。
- 影响模块：csvkit/utilities/csvclean.py；cleanup.py:Error
- 兼容边界：保留默认CSV错误输出与退出码1，不把现有CSV说成非机器可读。
- 正常验收：坏长度/空列等问题均有可解析JSON对象，stdout清洗结果不混日志。
- 异常／边界：Unicode、引号、多行逻辑记录、多错误同一行和--label保持；隐私值显式开关。
- 原生回归：tests/test_cleanup.py；tests/test_utilities/test_csvclean.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．稳定的非CLI清洗结果接口（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1269
- 原版现状：RowChecker已存在，但高层CSVClean绑定argparse与sys.exit；没有明确的库级版本化结果契约。
- 交付目标：提供clean_rows/clean_file与CleanResult，复用RowChecker，返回输出header、行和结构化错误。
- 影响模块：csvkit/cleanup.py；utilities/csvclean.py
- 兼容边界：不废弃RowChecker；库调用不关闭调用方流、不调用sys.exit或修改sys.stdout。
- 正常验收：同一合成CSV由API与CLI得到相同修复和错误，调用方可逐行消费。
- 异常／边界：空表、晚发现空列导致缓存、提前终止、IO异常和错误数上限明确。
- 原生回归：tests/test_cleanup.py；tests/test_utilities/test_csvclean.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．csvgrep 大小写不敏感匹配（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1273
- 原版现状：可用内联正则(?i)，但-m/-f与显式CLI flag没有统一casefold模式。
- 交付目标：新增--ignore-case，对精确文本／匹配文件及正则采用明确对应策略。
- 影响模块：csvkit/utilities/csvgrep.py；grep.py
- 兼容边界：默认区分大小写，原-i仍是invert-match，不能抢占旧短选项。
- 正常验收：A/a及Unicode大小写在-m和-f按casefold匹配，正则模式使用对应flags。
- 异常／边界：空匹配、None/短行、多列all/any、inverse与Unicode特殊字符。
- 原生回归：tests/test_grep.py；tests/test_utilities/test_csvgrep.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．csvsort 每个字段独立排序方向（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/931
- 原版现状：只有全局--reverse，无法一次地区升序、金额降序。
- 交付目标：增加有序--sort规格列表及每键NULL顺序，按原生类型做稳定排序。
- 影响模块：csvkit/utilities/csvsort.py
- 兼容边界：旧-c/-r保持；无需改变外部agate API，可以在本仓构建显式比较键。
- 正常验收：地区asc、金额desc、日期asc组合正确，行内容不被重写。
- 异常／边界：全NULL、同值稳定、中文ignore-case、非法列或方向、--no-inference控制。
- 原生回归：tests/test_utilities/test_csvsort.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．sql2csv 的绑定参数输入（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1048
- 原版现状：exec_driver_sql(query)不接参数，使用者只能自行拼SQL或外部脚本。
- 交付目标：新增--params-json，从显式JSON值映射绑定执行SQLAlchemy text或受支持driver参数。
- 影响模块：csvkit/utilities/sql2csv.py
- 兼容边界：默认查询模式保持；不eval参数、不拼接值进SQL，不记录连接密码。
- 正常验收：SQLite :city查询带引号/Unicode值按值匹配，输出CSV列和值正确。
- 异常／边界：缺失/多余参数、NULL/数值、坏JSON、不支持方言参数语法与异常清理。
- 原生回归：tests/test_utilities/test_sql2csv.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．csvsql 原生冲突策略（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1186
- 原版现状：--insert走既有agate-sql装载，没有ON CONFLICT CLI策略。
- 交付目标：首版为SQLite提供--on-conflict=error/ignore/update及显式冲突键、更新列。
- 影响模块：csvkit/utilities/csvsql.py；本仓SQL装载辅助
- 兼容边界：默认error，其他方言明确不支持而非静默fallback；已有--before/after-insert顺序保持。
- 正常验收：同一订单号重复导入可忽略或更新选定列，唯一约束实际生效。
- 异常／边界：缺唯一约束、坏键、同批重复、事务中失败和NULL键语义明确。
- 原生回归：tests/test_utilities/test_csvsql.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．csvsql 只生成 INSERT 脚本（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1049
- 原版现状：可生成CREATE TABLE或连接执行，但没有显式离线生成数据INSERT脚本的模式。
- 交付目标：增加--emit-inserts，按选定dialect输出安全字面语句与可选事务包裹，不执行。
- 影响模块：csvkit/utilities/csvsql.py
- 兼容边界：与--insert执行模式互斥；无连接时不创建DB，不能用简单字符串拼接转义。
- 正常验收：含引号、换行、NULL、Unicode、日期的脚本在临时SQLite执行后数据一致。
- 异常／边界：BLOB/非有限数、空表、不支持literal编译的类型明确报错不输出假成功。
- 原生回归：tests/test_utilities/test_csvsql.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．按列固定输入类型与空值策略（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/151
- 原版现状：get_column_types返回全局TypeTester，-I为全部文本，缺少CLI列级类型规格。
- 交付目标：新增--types-json，白名单映射Text/Number/Date/DateTime等及各自null_values。
- 影响模块：csvkit/cli.py:get_column_types；依赖该入口的utility
- 兼容边界：默认原推断顺序保持；不把列名数字自动当索引，类型声明不执行Python。
- 正常验收：客户代码001保持Text，金额Number、日期Date同时存在并传到json/sql/stat。
- 异常／边界：未知列/类型、坏日期格式、冲突选项、全NULL、schema与header不符在输出前拒绝。
- 原生回归：tests/test_cli.py；test_utilities/test_csvjson.py；test_csvsql.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．多文件命令使用显式输入清单（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1107
- 原版现状：Windows已有_expand_args自动glob，POSIX通常由shell展开；缺少跨平台确定顺序的--files-from清单。
- 交付目标：csvstack/csvjoin/csvsql提供UTF-8输入清单，按清单顺序读取，可显式允许重复。
- 影响模块：csvkit/cli.py；utilities/csvstack.py/csvjoin.py/csvsql.py
- 兼容边界：保留原glob/shell行为；清单只含路径，不展开环境变量或执行命令。
- 正常验收：带空格与Unicode文件名的三文件清单顺序、--groups/--filenames对应正确。
- 异常／边界：空清单、缺路径、重复/目录/相对路径基准与stdin冲突清楚拒绝。
- 原生回归：tests/test_cli.py；test_utilities/test_csvstack.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 10．CSV 逻辑行切片命令（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/669
- 原版现状：csvlook --max-rows只用于展示，没有保持CSV语法的head/tail/slice工具。
- 交付目标：增加csvslice，按逻辑记录选择start/stop/step或tail，保留单份header。
- 影响模块：新增csvkit.utilities.csvslice；cli公共reader/writer
- 兼容边界：不按物理文本行切坏引号内换行；tail使用有界deque，普通slice不先全读。
- 正常验收：多行字段CSV取前N/最后N/区间后由标准csv.reader读回正确记录。
- 异常／边界：空输入、header-only、0/负边界、步长0拒绝、压缩文件及stdin。
- 原生回归：新增csvslice集合；tests/test_cli.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．列标识显式区分名字与索引（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/468
- 原版现状：新解析器已支持存在的含连字符名字，但纯数字名仍按位置处理；不能直接显式声明名字模式。
- 交付目标：新增--column-names/--column-indexes互斥模式，适配选择/排除/排序/筛选。
- 影响模块：csvkit/cli.py:match/parse_column_identifiers；各utility参数
- 兼容边界：默认混合旧解析保持；不把已修复的hyphen范围解析再记为BUG。
- 正常验收：header为1/2-3时名字模式选字面列，索引模式仍可用范围和--zero。
- 异常／边界：逗号列名可配JSON名单、重复名/不存在名、-C容错与非法范围按模式区分。
- 原生回归：tests/test_cli.py；test_utilities/test_csvcut.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．一致的字段重命名映射（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/396
- 原版现状：csvclean有header-normalize-space，但没有批量header映射重命名的公共选项。
- 交付目标：增加--rename-columns-json，按精确原名映射并可选择冲突error/suffix。
- 影响模块：csvkit/cli.py；utilities/csvcut.py/csvclean.py
- 兼容边界：不改变数据单元格；现有空白归一化与自动去重顺序文档化，不静默覆盖同名列。
- 正常验收：中文/空格header映射后多命令管道都识别新名，原值保持。
- 异常／边界：未匹配映射、数字/重复header、空名、冲突和headerless模式拒绝不合理组合。
- 原生回归：tests/test_cli.py；test_utilities/test_csvclean.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．csvjson 的精确整数输出（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1251
- 原版现状：默认agate.Number.jsonify转float；无明确只将整数Decimal转JSON整数的选项。
- 交付目标：增加--number-mode，允许integral-int和exact-string，对超范围/非有限值有显式政策。
- 影响模块：csvkit/utilities/csvjson.py；本仓序列化辅助
- 兼容边界：默认既有float输出不变；不能先转float再判断，-I文本仍保持文本。
- 正常验收：9007199254740993以JSON整数原样输出，分数保留选定策略，流式模式一致。
- 异常／边界：NaN/Infinity、-0、超大值、GeoJSON坐标数值约束及--key唯一性。
- 原生回归：tests/test_utilities/test_csvjson.py
- 真实依赖：08

## 14．csvlook 保持多行字段可读（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1148
- 原版现状：显示依赖agate.print_table的截断策略，缺少newline=escape/wrap显式选项。
- 交付目标：增加--multiline，保持单元格多段显示与其他列对齐，或显式显示\n转义。
- 影响模块：csvkit/utilities/csvlook.py；本仓展示辅助
- 兼容边界：默认现有显示保持；CSV真实内容不改，不把显示格式误当CSV交换格式。
- 正常验收：备注含换行时完整读到同一逻辑行，数字列对齐且header清晰。
- 异常／边界：CRLF/连续空行、超宽中文、max-column-width/max-rows和NULL。
- 原生回归：tests/test_utilities/test_csvlook.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．csvlook 展开记录视图（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1313
- 原版现状：只有二维列展示，无psql expanded式逐条记录布局。
- 交付目标：新增--expanded，输出记录序号及逐字段值，适合宽CSV人工检查。
- 影响模块：csvkit/utilities/csvlook.py
- 兼容边界：不把--max-columns限制当成删除数据；普通展示保持，支持指定列。
- 正常验收：一条含20字段的记录逐项显示，字段名与原值对应。
- 异常／边界：多行长值、重复header、无header、NULL、max-rows截断提示明确。
- 原生回归：tests/test_utilities/test_csvlook.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．查找某值出现在哪些列（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1214
- 原版现状：csvgrep需先指定列，csvstat统计无值到列的定位命令。
- 交付目标：新增csvfind或csvstat --find-value，输出列名、匹配数与有界样本行号。
- 影响模块：utilities/csvstat.py或新csvfind；grep.py
- 兼容边界：默认精确文本，显式正则/类型化模式，不为每列重新读整文件。
- 正常验收：给定sku或数字一次扫描报告所有出现列，--json适合程序消费。
- 异常／边界：空值、引号/换行、重复列名、样本上限、只计数和无匹配退出语义。
- 原生回归：tests/test_grep.py；test_utilities/test_csvstat.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．长命令的结构化进度（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/993
- 原版现状：现有verbose/统计输出不是逐批进度，默认不能观察大输入当前处理量。
- 交付目标：增加--progress=text/jsonl，stderr报告读取/处理行数与阶段，使用单调时钟。
- 影响模块：csvkit/cli.py；流式reader与缓冲utility入口
- 兼容边界：默认关闭，stdout数据流字节不混诊断；未知总量不伪造百分比。
- 正常验收：长合成CSV按间隔输出单调计数，结束和出错阶段明确。
- 异常／边界：stdin、压缩源、低于一批、早停、broken pipe和回调/输出错误不吞本体结果。
- 原生回归：tests/test_cli.py；test_utilities/test_csvstack.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 18．GeoJSON 外加元数据的保留出口（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/870
- 原版现状：当前已保留Feature id与完整geometry字符串；Feature bbox/foreign members和collection元数据仍无独立出口。
- 交付目标：in2csv --metadata-sidecar保存集合元数据及按feature id/序号索引的外加元数据。
- 影响模块：csvkit/convert/geojs.py；utilities/in2csv.py
- 兼容边界：默认CSV字段保持，不把已有id/geometry计新能力；不读取地理URL或执行crs内容。
- 正常验收：带bbox/crs/foreign属性的集合转CSV+JSON sidecar后可以按行关联元数据。
- 异常／边界：无id/重复id、NULLgeometry、同名properties、空features与sidecar目标冲突。
- 原生回归：tests/test_convert 的GeoJSON集合；test_utilities/test_in2csv.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．指定列的 Epoch 日期时间转换（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/829
- 原版现状：全局日期格式和推断已有，但Epoch整数默认仍是Number，没有秒/毫秒的显式列转换。
- 交付目标：类型规格支持epoch_seconds/epoch_millis，显式目标时区并输出ISO时间。
- 影响模块：csvkit/cli.py类型注册；csvjson/in2csv输入转换
- 兼容边界：不猜时间单位，不把所有大整数都当时间；默认Number保持。
- 正常验收：同一时刻秒/毫秒列转UTC ISO一致，JSON和CSV路径符合选定格式。
- 异常／边界：负Epoch、小数、越界、空值、夏令时zone与未声明列保持。
- 原生回归：tests/test_cli.py；test_utilities/test_in2csv.py
- 真实依赖：08

## 20．非seekable输入的有界嗅探缓冲（增强提案）

- 来源／场景：https://github.com/wireservice/csvkit/issues/1344
- 原版现状：部分类型化路径依赖tell/read/seek；--snifflimit 0是当前绕行，任意非seekable流无统一缓冲适配。
- 交付目标：增加有界prefix缓冲适配，让显式小snifflimit读取后按原顺序回放，不要求整个输入可seek。
- 影响模块：csvkit/cli.py:输入包装；agate调用边界
- 兼容边界：默认stdin已有peek能力保持；不为负snifflimit无限读入内存，超预算需要显式临时溢写选择。
- 正常验收：合成非seekable文本流在嗅探后完整输出无丢首字节、无重复行。
- 异常／边界：UTF-8跨边界、引号内换行、空流、仅header、坏编码与提前关闭归属明确。
- 原生回归：tests/test_cli.py；test_utilities/test_in2csv.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
