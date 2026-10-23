# Tablib：二十步真实工程迭代路线

固定 [jazzband/tablib@966876c76a6378557c1951badc1665b4d1375875](https://github.com/jazzband/tablib/tree/966876c76a6378557c1951badc1665b4d1375875)，见[单仓审查](./tablib.md)。2项原版复现修复与18项增强，全部是研究提案，未实施；新API名称为拟议契约。

已排除既有dict setter、动态列、tag过滤、输出formatter、按整行去重、位置stack/stack_cols、transpose、CSV StringIO导出、XLSX全表列宽/跳行/active sheet导入和Databook全表导入。每项按一个完整业务交付计数，不拆成测试/文档/小修。

## 01．按键名对齐字典记录

- **类型与场景**：复现修复提案；本地商品导入包含键顺序不同但相同字段的字典记录。
- **原版证据**：dict setter取第一行keys作为headers，却逐行取values；第二行quantity=5/sku=B实际变为sku=5/quantity=B。
- **交付目标**：按照已确定的header键逐个取值，定义缺键/多键策略并在追加前检查，不能依赖每行字典插入顺序。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：dict setter已有且必须保留；这不是新增字典导入。正常同序记录保持，缺键处理不得悄悄丢字段。
- **正常验收**：两行异序映射得到A/2与B/5，JSON/YAML经同一路径也按键对齐。
- **边界验收**：缺键、额外键、空列表、不同类型键、None、嵌套值和混合记录有明确错误/策略。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库映射协议。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 02．动态列位置随结构变化维护

- **类型与场景**：复现修复提案；商品派生得分插在首列，后续继续追加普通两字段记录。
- **原版证据**：insert_col(0,callable)初始行score在首列，但_dynamic_columns登记索引2；新行变成米/3/30而非30/米/3。
- **交付目标**：登记真实插入位置，并在插入/删除前置列时一致重排派生列位置，保留计算次序和输入形状规则。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：append_col既有可用行为保持；不新增动态列概念，不把手工传完整派生值的能力删去。
- **正常验收**：首列或中间派生列在原数据与新append数据都落在正确header下。
- **边界验收**：多动态列、负/超界索引约定、删除普通/动态列、计算异常、提供全值和部分值维度回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；沿用现有callable列。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/issues/576)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 03．显式完整重置与清空策略

- **类型与场景**：增强提案；可复用表对象需要在导入另一种表结构前明确清除显示和派生规则。
- **原版证据**：wipe清data/headers，但原formatter、dynamic_columns和separator仍保留。
- **交付目标**：提供显式reset或wipe选项，选择仅清数据或同时清动态列/格式器/分隔符/title，并记录一致的默认策略。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：把现行为当既有生命周期策略，不直接宣称所有元数据保留都是BUG；旧wipe默认兼容。
- **正常验收**：完整reset后重建两列表不残留第三列计算和旧分隔符；轻量wipe模式保持老行为。
- **边界验收**：空对象、异常后重置、title是否保留、共享副本、重复reset及格式器回调身份不误复制。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；容器清理；不要求先完成步骤02。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 04．可选择的原子导入替换

- **类型与场景**：增强提案；本地编辑器导入坏CSV失败后需要保留正在编辑的商品表。
- **原版证据**：CSV先wipe再逐行append；三字段坏行抛InvalidDimensions时旧商品表已被A/1部分结果替换。
- **交付目标**：新增atomic导入模式，解析到临时Dataset/Databook，全部成功后一次替换目标状态；失败保留原内容和元数据。
- **真实模块**：src/tablib/core.py、src/tablib/formats/_csv.py、src/tablib/formats/_json.py、src/tablib/formats/_xlsx.py。
- **兼容边界**：默认流式写入旧行为可保留；不承诺任意用户回调外部副作用事务；内存成本明确。
- **正常验收**：坏行导入抛错后旧表逐值和元数据不变，好文件成功完整替换。
- **边界验收**：空输入、错误header、格式检测失败、第三张sheet失败、formatter/dynamic状态和异常清理回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；临时对象；可独立于步骤03显式选择需替换状态。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_csv.py)；[来源3](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_json.py)；[来源4](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_xlsx.py)。

## 05．有界内存的记录读取接口

- **类型与场景**：增强提案；大CSV导入流程逐条处理商品，不需要先构建完整Dataset。
- **原版证据**：CSV reader虽逐行读，import_set仍将每行存入_data；无iterload/记录流入口。
- **交付目标**：新增独立iterload记录流与headers描述，先支持CSV/TSV，逐行返回记录及源行位置，不建立全量Dataset。
- **真实模块**：src/tablib/core.py、src/tablib/formats/_csv.py、src/tablib/formats/_tsv.py、src/tablib/utils.py。
- **兼容边界**：Dataset.load继续全量可变表；记录流不提供随机索引或假装已加载全部格式；源文件所有权明确。
- **正常验收**：受控生成输入在取得首条后只读取必要前缀，批量累加与旧load内容一致。
- **边界验收**：空文件、跳过行、引号内换行、提前close、输入异常、ragged策略和headerless模式回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库csv及迭代器；不要求实现所有二进制格式流。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/issues/281)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)；[来源3](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_csv.py)；[来源4](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_tsv.py)；[来源5](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/utils.py)。

## 06．逐块写出的CSV输出

- **类型与场景**：增强提案；本地导出大表时将CSV直接写入目标或按块消费，避免第二份完整文本。
- **原版证据**：export_stream_set已经存在，但先_package全部行并写入StringIO；getvalue已有完整输出，不是按需生成器。
- **交付目标**：新增iterexport或write_to接口，按行/有界块编码并写sink，复用CSV quoting与formatter协议。
- **真实模块**：src/tablib/core.py、src/tablib/formats/_csv.py、src/tablib/formats/_tsv.py。
- **兼容边界**：现有export_stream_set/getvalue接口保持；仅新增有界输出，不冒充已有file-like能力缺失。
- **正常验收**：连接所有chunk逐字等于原CSV，受控sink可确认写首块前未格式化最后一行。
- **边界验收**：空表、header-only、Unicode分块、CRLF/自定义dialect、formatter异常、sink失败和取消清理回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库csv与IO；与步骤05输入流独立。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/issues/207)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)；[来源3](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_csv.py)；[来源4](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_tsv.py)。

## 07．跨格式的可选缺失值策略

- **类型与场景**：增强提案；同一商品表来自CSV或电子表格时希望统一空值语义。
- **原版证据**：CSV空单元是空字符串，XLSX空单元是None；不存在统一null_policy。
- **交付目标**：增加显式missing-value策略，声明输入空文本/占位符到None的转换和输出None表示，提供逐列覆盖。
- **真实模块**：src/tablib/core.py、src/tablib/formats/_csv.py、src/tablib/formats/_xlsx.py、src/tablib/formats/_ods.py。
- **兼容边界**：默认各格式行为保持；空串与缺值只有显式选择时合并，0/False不当缺失。
- **正常验收**：同样空quantity从CSV/XLSX在所选策略下得到同一None，关闭策略恢复差异。
- **边界验收**：空白、引号空串、NA字面商品名、逐列排除、日期空值、None输出和多次往返可说明。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；本地策略回调/记录，不依赖pandas。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/issues/512)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)；[来源3](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_csv.py)；[来源4](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_xlsx.py)；[来源5](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_ods.py)。

## 08．带行列定位的类型与业务校验

- **类型与场景**：增强提案；本地库存CSV需要quantity为整数且非负，逐行报告错误。
- **原版证据**：CSV导入quantity为str，只有输出formatter与维度检查，无schema/validate_rows。
- **交付目标**：新增独立schema/validate_rows协议，逐列转换、行规则与结构化错误定位；允许收集报告或拒绝整行。
- **真实模块**：src/tablib/core.py、src/tablib/exceptions.py、src/tablib/formats/_csv.py。
- **兼容边界**：输出formatter保持用途；不默认猜类型，不把schema变成数据库模型；新转换结果是否写回显式。
- **正常验收**：A/2转换为int，负数量及非整数给出行/列/代码，成功行与错误报告可区分。
- **边界验收**：多个错误、缺值、自定义转换异常、重复headers、headerless位置、嵌套值与collect/fail-fast一致。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库类型与callable，消费者可自带复杂validator。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/issues/20)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)；[来源3](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/exceptions.py)；[来源4](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_csv.py)。

## 09．无header表的索引切片

- **类型与场景**：增强提案；无表头矩阵按列序号提取小表，不人工伪造字段名。
- **原版证据**：headerless.subset(rows=[0],cols=[1])抛TypeError；当前cols只按header名称筛选。
- **交付目标**：提供明确的列索引/切片选择模式，支持无header表，保留选中顺序并定义重复索引与未知位置处理。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：旧按header子集模式默认不变；字符串header与整数位置不能隐式混淆。
- **正常验收**：headerless两列表选列1得到一列数量；显式位置模式可重排列。
- **边界验收**：空表、负索引、slice边界、重复/未知选择、header为整数及rows顺序规则明确。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库索引；不要求先添加schema。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/issues/366)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 10．多键与缺值排序策略

- **类型与场景**：增强提案；库存表按分类和数量排序，同时稳定放置缺数量记录。
- **原版证据**：sort只接收col/reverse；None与int混排TypeError，列表多键也TypeError。
- **交付目标**：增加显式多键排序、每键方向、null placement与可选key转换，稳定返回新表。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：默认单键排序保持；不私自将所有混合类型转成字符串；不修改原表。
- **正常验收**：同类记录按数量稳定排序，nulls-last可用，两个不同方向的键遵循声明。
- **边界验收**：重复键、空表、全None、自定义key失败、headerless、重复headers和元数据保留规则回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库稳定排序；不依赖pandas。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 11．按业务键选择重复记录

- **类型与场景**：增强提案；重复商品sku需要明确保留首条或末条，其他列可能不同。
- **原版证据**：remove_duplicates只按整行tuple去重；A/1和A/2都保留，签名没有键选项。
- **交付目标**：增加显式subset key与keep first/last/none模式，可选择返回新表或就地操作，并给出重复位置。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：无参数仍按整行去重并保留原序；不隐式把sku视为唯一键。
- **正常验收**：按sku保留first得A/1，last得A/2，默认仍两行。
- **边界验收**：None键、组合键、不可hash值策略、空表、tags/格式器、全部重复与keep-none回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库键提取与容器；不要求先实现排序。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 12．按键关联两个表

- **类型与场景**：增强提案；商品表和仓位表行序不同，需要按sku匹配。
- **原版证据**：stack_cols已支持按位置拼接，观察中咖啡被配给茶的东仓；无join入口。
- **交付目标**：新增显式inner/left/full key join，声明左右键、重复键基数与同名列后缀，按业务键构造新表。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：现有stack/stack_cols位置语义保持；不能把位置拼接叫缺陷；不访问数据库。
- **正常验收**：咖啡关联西仓、茶关联东仓，left join未匹配项按约定填空。
- **边界验收**：组合键、重复键多对多预算、None是否匹配、同名列、空表、排序与未匹配报告明确。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库索引；独立于步骤11去重，重复键有自己的显式策略。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 13．分组聚合表

- **类型与场景**：增强提案；本地销售表按商品统计数量和金额。
- **原版证据**：没有groupby/aggregate；现filter只按Row.tags选择记录，不能视为分组统计。
- **交付目标**：新增显式键分组及count/sum/min/max或callable聚合，结果表保留确定字段名和组顺序。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：不改变tag filter；不强制自动数值转换；空值处理和汇总结果类型有文档。
- **正常验收**：同sku两行合计得到正确数量/金额，count和自定义聚合可并用。
- **边界验收**：空表、全空列、Decimal、组合/不可hash键、聚合异常、输出列重名与输入未改回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库容器和numeric；可独立于步骤08接收已类型化值。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 14．明确重复值规则的透视变换

- **类型与场景**：增强提案；本地月度商品报表在长表与按月份展开的宽表之间转换。
- **原版证据**：transpose已有，但只是行列互换；无pivot/melt，不能完成index/columns/value的业务透视。
- **交付目标**：新增一个成套reshape能力，按显式index/column/value透视及反向展开，重复坐标需聚合器或报错。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：transpose原语义保持；不隐式丢掉重复坐标，字段命名和稀疏单元填充值明确。
- **正常验收**：商品/月/销量转为月份列，反向展开可在声明缺值规则下恢复记录。
- **边界验收**：重复坐标、稀疏表、非字符串键、列排序、空表、多值列支持范围与输出冲突回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库表构造；聚合可由调用者给函数，不依赖步骤13分组API。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 15．按工作表与区域导入XLSX

- **类型与场景**：增强提案；本地工作簿只需要第二张表的商品区域。
- **原版证据**：Dataset.load默认active sheet，sheet=第二表抛TypeError；Databook已有全工作簿导入，skip_lines/read_only已支持。
- **交付目标**：增加显式sheet名称/序号和行列区域选择，边界以工作表真实坐标定义，避免先全部读入后切片。
- **真实模块**：src/tablib/formats/_xlsx.py、src/tablib/core.py。
- **兼容边界**：默认active sheet、read_only和skip_lines保持；不重复提已有全表/跳行能力。
- **正常验收**：选第二表和指定矩形只返回期望header与行，原工作簿不变。
- **边界验收**：未知/重复sheet名、空区、超界、merged cells、稀疏尺寸、headers=False及只读句柄关闭回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：现有openpyxl；不新增Office进程或网络依赖。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_xlsx.py)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 16．逐列电子表格显示格式

- **类型与场景**：增强提案；本地金额、百分比和日期报表需要持久化对应Excel number format。
- **原版证据**：导出的quantity单元格number_format=General，number_formats参数TypeError；已有全表column_width和换行/表头样式。
- **交付目标**：增加逐列number-format及有限样式映射协议，设置真实单元格格式而不将原数值预转成展示字符串。
- **真实模块**：src/tablib/formats/_xlsx.py。
- **兼容边界**：原样式默认保持；新格式与add_formatter值转换分开，column_width已有能力不再新增。
- **正常验收**：金额单元仍是数值且number_format=0.00，日期按指定格式，默认列仍General。
- **边界验收**：headerless位置、无效列/格式、None、动态列、分隔行、Databook及已有freeze_panes回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：现有openpyxl样式；不要求引入模板引擎。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_xlsx.py)。

## 17．大整数标识符的显式保真导出

- **类型与场景**：增强提案；商品长编码不是计算值，需要电子表格往返逐位保留。
- **原版证据**：568883383628111873导出xls/xlsx后作为浮点读回并不等于原整数；旧issue样本本身在当前环境恰可精确表示，未冒称已复现同一值错误。
- **交付目标**：增加逐列标识符/text模式或超精度warn/error/text策略，写入文本单元格并报告转换；普通数值列保持数值。
- **真实模块**：src/tablib/formats/_xls.py、src/tablib/formats/_xlsx.py。
- **兼容边界**：这是在电子表格数值精度限制上的显式增强，不声称格式可无损保存任意大数值；不把所有int一律变文本。
- **正常验收**：text标识符模式下长整数逐位往返相等；普通quantity仍数值可计算。
- **边界验收**：2**53前后、前导零字符串、负值、None、Decimal、日期和已有formatter优先级明确。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：现有xlwt/xlrd/openpyxl；无Excel客户端依赖。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/issues/197)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_xls.py)；[来源3](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_xlsx.py)。

## 18．HTML表格的可选呈现元数据

- **类型与场景**：增强提案；本地生成商品报告需要caption、table class和可识别表头关联。
- **原版证据**：html输出固定table/thead/tbody，table_class参数TypeError；HTML导入已有table_id选择。
- **交付目标**：增加显式caption/id/class及表头scope等呈现选项，统一Dataset和Databook表格输出。
- **真实模块**：src/tablib/formats/_html.py。
- **兼容边界**：默认HTML结构保持；沿用ElementTree编码文本/属性，不把已有HTML输出或table_id导入当新功能。
- **正常验收**：设置inventory class及商品caption，真实解析HTML能读到属性和表头关联，数据逐格一致。
- **边界验收**：Unicode、空表、None headers、多sheet唯一id、用户属性冲突和不支持的结构选项明确。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库ElementTree；不生成浏览器交互或远程页面。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/issues/142)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/_html.py)。

## 19．明确文本与二进制的本地文件入口

- **类型与场景**：增强提案；用户从本地CSV/XLSX路径加载和保存，不手工选择不同open模式。
- **原版证据**：load_file不存在，PathLike传给CSV抛TypeError，str路径被当内容解析；当前load明确接收内容或文件对象。
- **交付目标**：新增独立load_file/save_file，接收本地PathLike，按格式决定binary/text及encoding/newline，保留stream入口。
- **真实模块**：src/tablib/core.py、src/tablib/utils.py、src/tablib/formats/__init__.py。
- **兼容边界**：字符串内容load语义不变；不把路径/URL混猜，不支持网络读取；资源所有权和覆盖模式明确。
- **正常验收**：本地Unicode路径CSV按UTF-8往返，XLSX按binary往返，调用后文件句柄关闭。
- **边界验收**：无扩展名、显式format覆盖、编码错误、missing path、路径含点、只读目录、原文件覆盖选项回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；标准库pathlib/IO，格式依赖沿用已有可选包。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/issues/511)；[来源2](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)；[来源3](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/utils.py)；[来源4](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/formats/__init__.py)。

## 20．工作簿的明确工作表管理

- **类型与场景**：增强提案；本地汇总工具按名称查找、替换和移除某张表。
- **原版证据**：Databook只有add_sheet/sheets/wipe/size等接口，get_sheet/remove_sheet/replace_sheet不存在；调用者可直接操作暴露列表。
- **交付目标**：新增名称/位置查找与替换/移除入口，明确重复title、引用所有权和返回值，保留sheet顺序。
- **真实模块**：src/tablib/core.py。
- **兼容边界**：原sheets列表接口兼容；不静默规范化所有title或复制所有Dataset；导出格式自己的标题限制仍独立。
- **正常验收**：名称替换第二表后首表不变、size正确，移除后可再导出有效多表工作簿。
- **边界验收**：无标题、重名、未知名、负索引、同对象多次加入、最后一表移除与无效Dataset类型回归。
- **原生回归**：tests/test_tablib.py的关联表对象、导入导出和格式用例，累计再跑完整tests集合。
- **实际依赖**：无；列表管理；不依赖其他19步。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/jazzband/tablib/blob/966876c76a6378557c1951badc1665b4d1375875/src/tablib/core.py)。

## 控制端验收与累计回归

未来以本地合成商品记录调用真实Dataset/Databook，断言行列对应、原输入状态、导出后实际解析结果与报错定位。有界IO用受控源/sink确认首产物前的读取/格式化次数及峰值内存，不只检查对象是不是stream。电子表格用实际xlrd/openpyxl回读单元值和样式；不需要Office客户端、外部数据库或网络账号。183项原版通过不代表新增能力通过，冻结契约、离线制品与正式接入尚未开始。
