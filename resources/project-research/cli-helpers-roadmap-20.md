# CLI Helpers：二十步真实工程迭代路线

固定 [dbcli/cli_helpers@e2538b1d338ead4ed803ec0017017bf6779a380b](https://github.com/dbcli/cli_helpers/tree/e2538b1d338ead4ed803ec0017017bf6779a380b)，原生证据见 [单仓审查](./cli-helpers.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．格式选项不跨调用泄漏

- **类型与来源**：修复；固定源码与 observe.py 原版实测。
- **原版现状与收益**：fkwargs.update(kwargs) 修改类级注册默认字典；先传 N/A 后新实例默认也变 N/A。
- **交付及模块**：每次格式化从默认选项复制局部映射，注册默认不受调用参数污染；output_formatter.py:TabularOutputFormatter.format_output。
- **兼容与依赖**：显式本次 kwargs 仍覆盖默认；类级注册接口保持；步骤依赖：无。
- **正常验收**：两个 formatter 先后不同 NULL 标记，第三次无参回到原默认。
- **异常／边界验收**：嵌套可变默认值和惰性结果交错消费不串；调用者传入 dict 不被修改。
- **原生回归**：tests/tabular_output/test_output_formatter.py。

## 02．表格颜色状态局部化

- **类型与来源**：修复；tabulate_adapter.py:style_output_table 与 observe.py 合成样式交错实测。
- **原版现状与收益**：样式预处理改写 tabulate._table_formats；实测无样式后续输出仍含前次 ANSI，发生全局颜色泄漏。
- **交付及模块**：为本次输出构建局部 TableFormat，不叠加污染全局表格式；tabulate_adapter.py:style_output_table／adapter。
- **兼容与依赖**：已注册自定义样式仍有效；不修改共享 tabulate 配置，输出保持相同；步骤依赖：无。
- **正常验收**：着色／无样式／其他着色交错时每次仅包含自己选中的颜色。
- **异常／边界验收**：重复调用不累积 ANSI；异常后共享格式不变，Pygments 缺失分支正常。
- **原生回归**：tests/tabular_output/test_tabulate_adapter.py、tests/tabular_output/test_output_formatter.py。

## 03．一次性行迭代器保真

- **类型与来源**：修复；固定源码与 observe.py 原版实测。
- **原版现状与收益**：format_output 的 list(data) 没有固定每一行，_get_column_types 把生成器行消费后输出为空。
- **交付及模块**：在需要多次扫描的边界固定每行一次，并明确 headers 的一次性输入支持；output_formatter.py:format_output／_get_column_types、json_output_adapter.py。
- **兼容与依赖**：普通 list/tuple 不改变；不是把无限输入强行全量消费的新接口；步骤依赖：无。
- **正常验收**：generator of generator 与 list of list 输出逐字等价。
- **异常／边界验收**：空行、空数据、第二次读取禁止的迭代器；直接 JSON adapter headers 为生成器的多行场景。
- **原生回归**：tests/tabular_output/test_output_formatter.py、tests/tabular_output/test_json_output_adapter.py。

## 04．截断宽度符合终端显示

- **类型与来源**：修复；固定源码与 observe.py 原版实测。
- **原版现状与收益**：max_width 0／1／2 得到更长文本；len 按码点计算也使中文／ANSI 超过实际列宽。
- **交付及模块**：校验非负宽度、按终端可见宽度截断并选能放下的省略标记；utils.py:truncate_string、preprocessors.py:truncate_string。
- **兼容与依赖**：None 保留不截断，默认多行跳过策略保留；非法负宽明确报错；步骤依赖：无。
- **正常验收**：宽度 0..6 的 ASCII／中文结果显示宽度不超限。
- **异常／边界验收**：ANSI 不半截转义、组合字不破坏，宽度小于省略号长度仍受限；多行开关回归。
- **原生回归**：tests/test_utils.py、tests/tabular_output/test_preprocessors.py。

## 05．JSON 重复列名显式策略

- **类型与来源**：增强；固定源码与 observe.py 原版实测。
- **原版现状与收益**：dict(zip(headers,row)) 对重复列名静默只保留最后列，样本 {id:2} 丢失首列。
- **交付及模块**：提供 duplicate_headers=error／suffix／last 策略，严格导出可拒绝歧义；json_output_adapter.py、output_formatter.py。
- **兼容与依赖**：默认 last 兼容，strict 显式开启；suffix 规则先稳定编号；步骤依赖：无。
- **正常验收**：id,id 的 suffix 输出 id/id_2，error 在首行输出前报错。
- **异常／边界验收**：原列名已含 _2、空列名和非字符串列名明确；列顺序及 Unicode 保持。
- **原生回归**：tests/tabular_output/test_json_output_adapter.py。

## 06．Decimal 无损 JSON 输出

- **类型与来源**：增强；固定源码与 observe.py 原版实测。
- **原版现状与收益**：CustomEncoder 把 Decimal 转 float，0.12345678901234567890123456789 实测丢失精度。
- **交付及模块**：新增 decimal_mode=string／number 的明确策略，无损模式输出可往返十进制；json_output_adapter.py:CustomEncoder／adapter。
- **兼容与依赖**：默认 float 输出保持；无损数字若不能只用标准 json 安全实现则首版限定 string，不拼未校验 JSON；步骤依赖：无。
- **正常验收**：Decimal 字符串模式读回 Decimal 后精确等值。
- **异常／边界验收**：科学记数、大指数、负零、NaN／Infinity 的处理与严格 JSON 策略分开。
- **原生回归**：tests/tabular_output/test_json_output_adapter.py。

## 07．严格有限数 JSON

- **类型与来源**：增强；固定源码与 observe.py 原版实测。
- **原版现状与收益**：NaN 原样进入 JSON，严格消费者拒绝。
- **交付及模块**：提供 allow_nonfinite=False，有限 float 正常、非有限值可报错或显式替 null；json_output_adapter.py。
- **兼容与依赖**：默认既有宽松行为保持；不把普通字符串 NaN 当数字替换；步骤依赖：无。
- **正常验收**：严格解析器能读所有有限数字输出。
- **异常／边界验收**：float 和 Decimal 的 NaN/Infinity/-Infinity、空数据、错误行号不泄漏整行数据。
- **原生回归**：tests/tabular_output/test_json_output_adapter.py。

## 08．JSON 位置数组格式

- **类型与来源**：增强；固定源码和数据库 CLI 导出场景分析（增强，非上游承诺）。
- **原版现状与收益**：支持 jsonl 字典行，无 JSON 数组行格式；有重复列名的查询无法无损保留所有值。
- **交付及模块**：新增 jsonl-array 格式，可另行输出 header 元数据但数据行为位置数组；json_output_adapter.py、output_formatter.py 注册表。
- **兼容与依赖**：已有 jsonl 默认不变；数组模式不暗自把第一行当 headers；步骤依赖：无。
- **正常验收**：重复列名和任意列数均按原顺序保留值。
- **异常／边界验收**：空列、空记录、None、Decimal 与 bytes 复用明确策略，逐行均合法 JSON。
- **原生回归**：tests/tabular_output/test_json_output_adapter.py、tests/tabular_output/test_output_formatter.py。

## 09．大结果集逐行导出

- **类型与来源**：增强；format_output 强制 list(data)，即使提供 column_types 最终仍 list(data)。
- **原版现状与收益**：CSV／JSONL 的首行必须等整个结果全部消费，内存随行数增长。
- **交付及模块**：为可流式格式增加显式 stream 模式，提供 column_types 或可配置有界推断窗口；output_formatter.py、delimited_output_adapter.py、json_output_adapter.py。
- **兼容与依赖**：tabulate 等需全表布局的格式保留物化；不能把结果截断当流式；步骤依赖：03。
- **正常验收**：首行取出时上游只消费有界条数，十万合成行输出完整。
- **异常／边界验收**：上游中途错误／消费者提前 close 不过度读取；无限源必须由调用者显式限界。
- **原生回归**：tests/tabular_output/test_output_formatter.py、各导出适配器测试。

## 10．按列投影和重排

- **类型与来源**：增强；固定源码和数据库 CLI 导出场景分析（增强，非上游承诺）。
- **原版现状与收益**：公开入口把原始 headers／rows 全部传给适配器，无声明式投影；只能自写 preprocessor。
- **交付及模块**：增加 columns 选择器按名字或位置选列并可重排，headers 与 column_types 同步；output_formatter.py、preprocessors.py。
- **兼容与依赖**：不传 selector 保持所有列；重复列名要求位置选择以免歧义；步骤依赖：无。
- **正常验收**：查询输出 [id,password,name] 选 id/name 时两种导出均不含被排除值。
- **异常／边界验收**：未知列、重复选择、短行与生成器；不得只删表头而保留敏感单元格。
- **原生回归**：tests/tabular_output/test_output_formatter.py、tests/tabular_output/test_preprocessors.py。

## 11．每列数字格式

- **类型与来源**：增强；preprocessors.py:format_numbers 仅有全局 integer_format／float_format。
- **原版现状与收益**：不同金额／百分比／计数列不能分别格式化，需外部重写。
- **交付及模块**：新增 column_number_formats，按实际 header 或列号选格式并保留类型上下文；preprocessors.py:format_numbers、output_formatter.py。
- **兼容与依赖**：原全局格式作为后备，日期已有 per-column 不重复计步；步骤依赖：无。
- **正常验收**：金额两位小数、比率四位、计数分组同时正确。
- **异常／边界验收**：None、Decimal、非法格式、重复 header 和混合文本列不被误转数。
- **原生回归**：tests/tabular_output/test_preprocessors.py。

## 12．表格导出到电子表格的显式公式策略

- **类型与来源**：增强；delimited_output_adapter.py 和实际 CSV 字符串导出场景。
- **原版现状与收益**：原样 =SUM 等文本导入电子表格可能被解释成公式；普通 CSV 本身必须保留原值。
- **交付及模块**：提供 spreadsheet_safe 选项，只对文本列危险前缀作可逆/可说明的显示转义；delimited_output_adapter.py、preprocessors.py。
- **兼容与依赖**：默认关闭，原始科学数据与负数不能无条件改写；只宣称面向所选消费者约定；步骤依赖：无。
- **正常验收**：开启后 =、+、@ 和控制前缀的文本按文档策略转义。
- **异常／边界验收**：实际数值负数保持，Unicode／空白前缀覆盖；不把带引号 CSV 误当已完全解决。
- **原生回归**：tests/tabular_output/test_delimited_output_adapter.py。

## 13．二进制输出可选择编码

- **类型与来源**：增强；utils.py:bytes_to_string 当前自动可打印 UTF-8／hex。
- **原版现状与收益**：数据库 BLOB 的显示由可打印性推断，JSON 无元数据区分真字符串 0xff 与二进制。
- **交付及模块**：增加 binary_mode=auto／hex／base64 以及可选结构化 JSON 标记；utils.py、preprocessors.py:bytes_to_string、json_output_adapter.py。
- **兼容与依赖**：默认 auto 与当前结果保持；不把 bytes 解码错误归为源数据损坏；步骤依赖：无。
- **正常验收**：相同 BLOB 在显式 hex/base64 下可逆还原。
- **异常／边界验收**：空 bytes、非法 UTF-8、换行和文本看似 hex 的值；模式校验在消费数据前完成。
- **原生回归**：tests/test_utils.py、tests/tabular_output/test_json_output_adapter.py。

## 14．可往返的 TSV 转义模式

- **类型与来源**：增强；固定源码与 observe.py 原版实测。
- **原版现状与收益**：字面 a\nb 与含换行 a
b 实测输出相同，不可反向区分。
- **交付及模块**：增加显式 escaped TSV dialect，先转义反斜杠再转义 tab／CR／LF，并提供对应解码约定；tsv_output_adapter.py、preprocessors.py。
- **兼容与依赖**：已有 tsv 字节行为保持，新增 dialect 单独命名，CSV-tab 仍遵循 CSV 引号规则；步骤依赖：无。
- **正常验收**：含反斜杠、真实换行和 tab 的不同输入输出可区分并读回。
- **异常／边界验收**：连续反斜杠、结尾反斜杠、Unicode 和 None；不依赖多轮 replace 顺序偶然成立。
- **原生回归**：tests/tabular_output/test_tsv_output_adapter.py。

## 15．统一行列形状诊断

- **类型与来源**：增强；JSON zip(strict=True)、vertical zip 截断、其他适配器各自处理不同长度行。
- **原版现状与收益**：相同坏结果在不同格式下可能截断或抛无上下文异常。
- **交付及模块**：增加 row_shape=error／pad 策略，报告行号和实际／期望列数；output_formatter.py、适配器边界。
- **兼容与依赖**：默认兼容旧各格式；严格导出明确启用，不因一个长行静默丢列；步骤依赖：03。
- **正常验收**：严格模式在第二行缺列时明确定位，pad 模式只补缺失值。
- **异常／边界验收**：多列、零列、超长行、generator 一次消费和无 header 的合法模式。
- **原生回归**：tests/tabular_output/test_output_formatter.py、各适配器测试。

## 16．配置严格解析与原子应用

- **类型与来源**：增强；固定源码与 observe.py 原版实测。
- **原版现状与收益**：read_config_file 警告坏行后返回有效部分，validate=False 时 valid=True；部分结果会 update。
- **交付及模块**：strict=True 时结构错误或校验失败抛包含文件／行位置的 ConfigError，全部读取成功后才更新；config.py:Config.read_config_file／read_config_files。
- **兼容与依赖**：默认容错保持；严格加载不能留下前几个文件的半更新；步骤依赖：无。
- **正常验收**：正常分层文件全部装载，坏末文件使原 mapping 完整保留。
- **异常／边界验收**：缺文件、读权限、嵌套校验错误、坏编码明确；不在日志输出配置值。
- **原生回归**：tests/test_config.py。

## 17．配置节的递归合并

- **类型与来源**：增强；config.py:Config.read_config_files 使用 UserDict.update。
- **原版现状与收益**：两个文件的同名 section 后者整体覆盖，无法只覆盖 host 而保留 port。
- **交付及模块**：增加 merge=deep 的可选层级策略，逐键覆盖，保留来源默认顺序；config.py:read_config_files。
- **兼容与依赖**：默认浅层覆盖保持；list 默认整体替换，section 与 scalar 冲突明确；步骤依赖：无。
- **正常验收**：系统 [server] host/port 加用户 host，deep 结果保留 port。
- **异常／边界验收**：列表、空节、嵌套三层、类型冲突与注释所有权明确，不猜删键意图。
- **原生回归**：tests/test_config.py。

## 18．配置值来源诊断

- **类型与来源**：增强；config.py 仅 config_filenames，原版重读列表还重复；无逐键胜出来源。
- **原版现状与收益**：CLI 用户无法解释当前设置来自哪个层级。
- **交付及模块**：提供 inspect_sources 路径元数据，包括胜出文件、层级和覆盖链，默认不含值；config.py:read_config_file／read_config_files。
- **兼容与依赖**：普通 mapping 返回保持；去重文件列表不等同于逐键来源能力；步骤依赖：无。
- **正常验收**：同键三层覆盖可追到真实最终来源，default dict 有合成来源标签。
- **异常／边界验收**：失败读取不标记成功，重复路径、深合并、无文件对象和敏感值不泄漏。
- **原生回归**：tests/test_config.py。

## 19．配置写入受控发布

- **类型与来源**：增强；config.py:write／write_default_config 直接 wb 截断目标。
- **原版现状与收益**：写入失败可能破坏旧文件；默认路径父目录缺失时也没有明确创建策略。
- **交付及模块**：提供 atomic=True 写同目录临时文件后 replace，显式 parents 策略和 overwrite 排他边界；config.py:Config.write／write_default_config。
- **兼容与依赖**：默认读写格式和注释保留；不声称原子 rename 等于断电持久化，符号链接策略明确；步骤依赖：无。
- **正常验收**：新建／更新配置后 ConfigObj 读回值和注释一致。
- **异常／边界验收**：序列化或写入错误保留旧摘要并清理本轮临时文件；权限／非目录父路径明确。
- **原生回归**：tests/test_config.py。

## 20．重新加载反映已删除配置

- **类型与来源**：增强；固定源码与 observe.py 原版实测。
- **原版现状与收益**：同一 Config.read_config_files 重读 a=3 后已删 b=2 仍残留，来源重复；现有 read 是累加语义。
- **交付及模块**：新增 reload() 从冻结默认与当前层级重新构建 mapping，一次成功后替换，返回变更键集合；config.py:Config.read／read_config_files。
- **兼容与依赖**：现有 read 累加保持；reload 是明确的新契约，不把上次运行时 update 静默带入；步骤依赖：16、18。
- **正常验收**：文件删去 b 后 reload 结果无 b，变更清单含删除。
- **异常／边界验收**：文件消失、严格失败、无变化、深合并与来源链同步；失败保留旧完整配置。
- **原生回归**：tests/test_config.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
