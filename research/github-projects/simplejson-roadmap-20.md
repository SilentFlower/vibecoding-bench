# simplejson：二十步真实工程迭代路线

固定 [simplejson/simplejson@9950b7e5f4443fff8defb51e80e41ab40d0a36b9](https://github.com/simplejson/simplejson/tree/9950b7e5f4443fff8defb51e80e41ab40d0a36b9)，详见[单仓审查](./simplejson.md)。共 20 步：19 项增强提案、1 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．文件格式化失败不清空原文件（问题修复）

- 来源／场景：[simplejson/tool.py:main；smoke真实文件复现](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/tool.py)
- 原版现状：tool在验证输入之前以w打开输出；坏JSON会清空已有输出，同一路径输入/输出也先被截断后解析失败。
- 交付目标：先完成解析/编码，临时同目录文件写入成功后替换；同路径可安全原地格式化，失败保持原内容。
- 影响模块：simplejson/tool.py；tests/test_tool.py
- 兼容边界：stdout流模式保留；原文件权限/替换失败政策明确，不承诺多个文件共同事务。
- 正常验收：坏输入时已有valuable.json保持不变，同路径有效输入可成功格式化。
- 异常／边界：写入异常、只读目录、磁盘错误、Unicode路径、符号链接政策和临时文件清理。
- 原生回归：tests/test_tool.py；smoke两个破坏性场景仅用合成文件
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．解码重复键的声明式政策（增强提案）

- 来源／场景：[index.rst:Repeated Names Within an Object；decoder.JSONObject](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/index.rst)
- 原版现状：默认重复名称最后值胜出；object_pairs_hook可自写处理，但没有统一first/error政策与重复位置。
- 交付目标：增加duplicate_keys=last/first/error，错误包含两个键位置和对象路径。
- 影响模块：decoder.py:JSONObject；scanner.py；_speedups.c；load/loads
- 兼容边界：默认last保持；object_pairs_hook优先级必须声明，不能静默覆盖调用方自定义hook。
- 正常验收：a重复两次时三种政策分别选末值/首值/错误，嵌套对象一致。
- 异常／边界：转义后相同键、Unicode、空名称、多个重复键与C/纯Python错误位置一致。
- 原生回归：tests/test_decode.py/test_errors.py；上游双引擎套件
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．编码归一化键碰撞检查（增强提案）

- 来源／场景：https://github.com/simplejson/simplejson/issues/77
- 原版现状：{1:integer,"1":string}输出两个相同JSON名称，重新解析会丢一项；既有宽松键转字符串行为已保留。
- 交付目标：增加key_collision=allow/error，在字符串化后检测同一对象键碰撞。
- 影响模块：encoder.py:_stringify_key/_iterencode_dict；_speedups.c
- 兼容边界：默认allow兼容；skipkeys跳过的键不参与，排序前后检查结果一致。
- 正常验收：1与"1"、None与"null"碰撞被明确拒绝，普通不同键可输出。
- 异常／边界：bytes/str解码同名、float/Decimal相同名称、Unicode与嵌套路径，双引擎一致。
- 原生回归：test_dump.py/test_decimal.py/test_item_sort_key.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．独立的自定义键编码入口（增强提案）

- 来源／场景：https://github.com/simplejson/simplejson/issues/156
- 原版现状：default用于未知值，不用于字典键；UUID等业务键只能先重建整个字典。
- 交付目标：增加default_key回调返回字符串键，并与排序/碰撞检查整合。
- 影响模块：JSONEncoder；_stringify_key；dump/dumps；_speedups.c
- 兼容边界：默认键集合和skipkeys行为不变；default值回调不被误用为键回调。
- 正常验收：UUID键通过显式回调成为固定字符串，值仍按原编码规则。
- 异常／边界：回调非字符串、抛错、重复字符串、返回自身和空键，不能循环回调。
- 原生回归：test_default.py/test_dump.py/test_item_sort_key.py
- 真实依赖：03

## 05．解码结构和字符串预算（增强提案）

- 来源／场景：[index.rst:Implementation Limitations；scanner/JSONObject/JSONArray](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/index.rst)
- 原版现状：除解释器整数位数上限等限制外，没有显式深度、节点、字符串长度和文档字节预算。
- 交付目标：提供DecodeLimits并在C/纯Python对应位置受控拒绝超预算输入。
- 影响模块：decoder.py；scanner.py；_speedups.c；errors.py
- 兼容边界：默认未设限制保持；不能把深度错误当普通语法EOF，配置不修改全局解释器设置。
- 正常验收：给定max_depth/max_nodes在刚好边界成功，超过后异常带位置和限制名。
- 异常／边界：空容器、长转义字符串、文档bytes与字符数区别、hook替换后对象成本和数字位数。
- 原生回归：test_decode.py/test_recursion.py/test_errors.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．编码递归和输出预算（增强提案）

- 来源／场景：JSONEncoder.iterencode；iterable_as_array处理无限迭代器场景；固定源码：[simplejson/encoder.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/encoder.py)。
- 原版现状：check_circular只防环，不限制无环深树、无限可迭代或输出总字符数。
- 交付目标：增加EncodeLimits约束深度、元素数和输出字节/字符，迭代中及时终止并清理markers。
- 影响模块：encoder.py:_make_iterencode；_speedups.c；dump/dumps
- 兼容边界：默认不限；budget错误不承诺已写流回滚，文件原子模式另按第01步。
- 正常验收：有限生成器在预算内正常输出，无限生成器超过元素预算受控终止。
- 异常／边界：default/for_json递归、单个巨大字符串、非ASCII字节数、发生错误后编码器可复用。
- 原生回归：test_iterable.py/test_check_circular.py/test_custom_method_cycles.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．分块输入的增量解码器（增强提案）

- 来源／场景：JSONDecoder.raw_decode仅支持完整字符串；分块网络/文件真实场景；固定源码：[simplejson/errors.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/errors.py)。
- 原版现状：raw_decode不能区分等待下一块和最终非法输入，用户需自管缓冲与多字节边界。
- 交付目标：新增IncrementalDecoder.feed/finalize，返回已完成文档，明确need_more状态并限制缓冲。
- 影响模块：新增增量入口；decoder/scanner状态；errors.py
- 兼容边界：不改变loads一次一个文档的规则；只支持标准JSON，不加入注释等语法。
- 正常验收：每个字符一块和整块输入得到相同结构，数字直到分隔符/EOF才确认完成。
- 异常／边界：UTF8字符/转义/指数断块、尾随垃圾、截断字符串、finalize重复和预算超限。
- 原生回归：test_decode.py/test_scanstring.py及分块独立断言
- 真实依赖：05

## 08．逐元素读取顶层大数组（增强提案）

- 来源／场景：decoder.py:JSONArray；大型JSON数组导入场景；固定源码：[simplejson/decoder.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/decoder.py)。
- 原版现状：load读完整文本并构建整个list，array_hook仅在数组完整后调用，不是惰性读取。
- 交付目标：提供iter_array逐个产出顶层数组元素，支持文本/二进制文件与分块缓冲。
- 影响模块：增量扫描器；JSONArray状态；公开流API
- 兼容边界：不宣称单个巨大元素内存恒定；默认load仍返回完整list。
- 正常验收：读取一万条合成订单，消费前三条不先构建余下全部对象。
- 异常／边界：非数组根、数组末尾垃圾、逗号/括号断块、早关迭代器与源文件所有权。
- 原生回归：test_decode.py/test_pass*.py；大数组计数流
- 真实依赖：07

## 09．多文档 JSONL 与记录序列接口（增强提案）

- 来源／场景：index.rst的JSON lines示例；当前仅给手工循环；固定源码：[index.rst](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/index.rst)、[simplejson/tool.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/tool.py)。
- 原版现状：文档已有逐行loads示例，没有统一序号错误、空行政策及RFC7464记录分隔模式。
- 交付目标：新增load_many/dump_many与tool流模式，显式jsonl/sequence格式、continue/stop和记录索引。
- 影响模块：公开多文档API；tool.py；增量解码器
- 兼容边界：默认仍单文档；不把格式自动猜测当容错；每记录独立限制，输出合法标准JSON。
- 正常验收：三条事件含中间坏记录时按选项继续并报告序号，Unicode记录可往返。
- 异常／边界：末尾无换行、空行、RS出现在字符串转义、BOM、破管道与文件失败原子策略。
- 原生回归：test_tool.py/test_decode.py；多文档真实文件
- 真实依赖：01, 07

## 10．显式可组合类型编码注册表（增强提案）

- 来源／场景：https://github.com/simplejson/simplejson/issues/321
- 原版现状：default/for_json可让调用方自写UUID等适配，但无可组合/可检查的类型注册表。
- 交付目标：提供TypeCodecs将UUID、日期时间、dataclass等适配器显式组合，定义优先级和未知类型错误。
- 影响模块：新增codec模块；JSONEncoder.default；for_json协作
- 兼容边界：所有适配均opt-in；不自动调用任意对象属性/反序列化任意类，不覆盖内置Decimal精度语义。
- 正常验收：业务记录的UUID/aware datetime/dataclass在注册后得到规定JSON表示，未注册仍TypeError。
- 异常／边界：多继承适配冲突、naive时间政策、递归dataclass、适配器返回自身与路径错误。
- 原生回归：test_default.py/test_for_json.py/test_custom_method_cycles.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．符合 JCS 的独立规范化输出（增强提案）

- 来源／场景：https://www.rfc-editor.org/rfc/rfc8785
- 原版现状：sort_keys+紧凑分隔符不等于JCS；Python键排序/浮点文本与UTF16顺序等有差异，默认Decimal扩展也超出其模型。
- 交付目标：提供独立canonicalize入口，按RFC8785键排序、字符串、数值和UTF8字节规则输出并拒绝越界数据。
- 影响模块：新增canonical模块；encoder浮点/字符串复用与严格校验
- 兼容边界：不改变dumps默认，也不把任意精度Decimal/大整数暗中舍入；不支持输入需明确报错。
- 正常验收：官方规范样本与浮点边界向量字节完全一致，重复编码哈希稳定。
- 异常／边界：NaN/Infinity、孤立代理、非字符串键、UTF16排序、负零及精度范围；独立参考向量交叉验证。
- 原生回归：test_float.py/test_unicode.py；RFC8785官方向量
- 真实依赖：02, 03

## 12．解码 hook 可获得结构路径（增强提案）

- 来源／场景：JSONDecoder.object_hook/object_pairs_hook/array_hook签名；固定源码：[simplejson/decoder.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/decoder.py)。
- 原版现状：现有hook只拿到完整容器，无法按字段路径区分同形对象、日期列或做定位校验。
- 交付目标：提供独立path_hook(path,value,kind)或上下文hook，可处理容器及标量，位置元数据可选。
- 影响模块：JSONObject/JSONArray/scanner；_speedups.c；Decoder参数
- 兼容边界：旧hook签名不变；调用先后与返回替换规则明确，不让未知hook偷偷改变默认类型。
- 正常验收：只将invoice/amount转Decimal或只校验特定对象路径，同形其他字段不受影响。
- 异常／边界：整数索引、重复键、hook异常、递归替换及C/纯Python调用次数/顺序一致。
- 原生回归：test_decode.py/test_decimal.py；第02步重复键用例
- 真实依赖：02

## 13．按指定 JSON 路径提取字段（增强提案）

- 来源／场景：scanner.py:_scan_once；大文档提取少量字段真实场景；固定源码：[simplejson/scanner.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/scanner.py)。
- 原版现状：load构造所有字段后调用方再取值，没有跳过未选子树对象构建的读取入口。
- 交付目标：提供select_load以显式键/索引路径选择目标，仍校验跳过文本的完整JSON合法性。
- 影响模块：scanner/decoder；增量状态；新增选择结果类型
- 兼容边界：首版精确路径不提供任意查询语言；缺失与null区分；不能以跳过为由接受坏JSON。
- 正常验收：从大型事件只提取id和customer/name，结果/位置与完整loads后取值一致。
- 异常／边界：父子路径重叠、空路径、数组越界、跳过子树非法转义/重复键政策和预算。
- 原生回归：test_decode.py/test_fail.py；选择路径差分验收
- 真实依赖：05, 07, 12

## 14．已验证的 RawJSON 构造方式（增强提案）

- 来源／场景：simplejson/raw_json.py；smoke的not-json片段；固定源码：[simplejson/raw_json.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/raw_json.py)。
- 原版现状：RawJSON按约定不检查文本，任意not-json会直接嵌入并生成坏JSON。
- 交付目标：新增RawJSON.from_validated或validate=True，要求恰好一个合法JSON值并可应用严格政策。
- 影响模块：raw_json.py；loads；encoder RawJSON分支
- 兼容边界：原RawJSON快路径保留；验证后内容不可被替换绕过，避免每次编码重复全量校验。
- 正常验收：预编码对象可安全嵌入，not-json/多文档/尾随垃圾构造时失败。
- 异常／边界：空白包裹、编码bytes、NaN政策、字符串根、深度限制及C/纯Python输出一致。
- 原生回归：test_raw_json.py/test_fail.py
- 真实依赖：05

## 15．二进制输入自动识别 Unicode 编码（增强提案）

- 来源／场景：JSONDecoder.decode；index.rst输入编码约定；固定源码：[index.rst](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/index.rst)。
- 原版现状：默认bytes按UTF8解码；UTF16带BOM的合法文档当前UnicodeDecodeError，显式encoding仍可由调用方指定。
- 交付目标：增加encoding=auto按BOM/JSON初始字节识别UTF8/16/32，再保持准确字符与字节错误偏移。
- 影响模块：load/loads；JSONDecoder；增量二进制入口
- 兼容边界：默认utf8保持；auto不猜任意地区编码，不吞掉无效字节。
- 正常验收：UTF8/16LE/BE/32LE/BE文档自动读为同结构，显式encoding优先。
- 异常／边界：截断BOM、无BOM初始模式、孤立代理、多字节断块和错误偏移。
- 原生回归：test_unicode.py/test_decode.py/test_scanstring.py
- 真实依赖：07

## 16．直接面向二进制流输出 UTF8（增强提案）

- 来源／场景：dump循环fp.write(str)；文档明确不接受bytes writer；固定源码：[simplejson/encoder.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/encoder.py)。
- 原版现状：二进制文件/响应体需调用方自行编码str；无公共dump_bytes/iterencode_bytes入口。
- 交付目标：提供二进制输出入口，按字节分块UTF8写入，保留原有Decimal/排序/适配选项。
- 影响模块：encoder.py；dump/dumps辅助；二进制writer协议
- 兼容边界：dump文本协议保持；不对每块添加BOM，明确短写/异常政策。
- 正常验收：写BytesIO/二进制文件可被标准JSON解码，中文与emoji无需额外中间完整字符串。
- 异常／边界：代理字符、空输出、writer短写、chunk边界、编码预算与破管道。
- 原生回归：test_dump.py/test_unicode.py/test_iterable.py
- 真实依赖：06

## 17．非有限数的可定制替换政策（增强提案）

- 来源／场景：https://github.com/simplejson/simplejson/issues/159
- 原版现状：已有allow_nan和ignore_nan三种常见行为，但不能按NaN/+Inf/-Inf及字段位置分别替换。
- 交付目标：新增显式nonfinite_handler，返回合法可编码替代值，float与Decimal统一。
- 影响模块：encoder.py:_floatstr/_encode_decimal；_speedups.c
- 兼容边界：默认allow_nan/ignore_nan不变；与handler冲突参数直接拒绝，不让替换返回无限递归数。
- 正常验收：NaN转null、正/负Infinity转指定字符串，Decimal对应值相同政策。
- 异常／边界：sNaN、字典键、handler抛错/返回自身、嵌套位置及C/Python差分一致。
- 原生回归：test_float.py/test_decimal.py/test_dump.py
- 真实依赖：03, 06

## 18．保留 JSON 数字原始词法（增强提案）

- 来源／场景：parse_int/parse_float回调；配置仅修改文字字段的真实场景；固定源码：[simplejson/scanner.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/scanner.py)。
- 原版现状：Decimal保持数值精度但不承诺1e3/1E+03/-0等词法原样；回调可自写但缺少安全数值词法类型。
- 交付目标：提供NumberToken与preserve_number_text模式，记录合法原文及数值访问，编码时受验证保留原词法。
- 影响模块：scanner.py数字分支；decoder参数；encoder数字token分支
- 兼容边界：默认int/float/Decimal不变；与canonicalize互斥或由规范化明确舍弃原词法。
- 正常验收：读入1E+03、-0、123.4500后只修改label，重新编码仍保留这三种数字文本。
- 异常／边界：超长数字、非法词法构造、正负零、比较/哈希定义及C/Python一致。
- 原生回归：test_float.py/test_decimal.py/test_decode.py
- 真实依赖：05, 14

## 19．数组与对象可分别控制排版（增强提案）

- 来源／场景：https://github.com/simplejson/simplejson/issues/239
- 原版现状：indent当前同时让对象与列表换行，无法让小型数值向量紧凑而对象保持易读层级。
- 交付目标：新增compact_arrays或array_layout规则，按元素种类/宽度阈值决定单行数组。
- 影响模块：JSONEncoder.iterencode/_iterencode_list；_speedups.c格式选项
- 兼容边界：默认排版字节不变；输出合法JSON，宽度按明示字符列近似，不承诺终端字宽。
- 正常验收：对象多行且[1,2,3]单行，嵌套大型对象数组仍多行。
- 异常／边界：空数组、长字符串、Unicode、custom separators、迭代器未知长度和循环错误。
- 原生回归：test_indent.py/test_separators.py/test_iterable.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．命令行显式验证和排版选项（增强提案）

- 来源／场景：simplejson/tool.py固定sort_keys/indent/use_decimal；固定源码：[simplejson/tool.py](https://github.com/simplejson/simplejson/blob/9950b7e5f4443fff8defb51e80e41ab40d0a36b9/simplejson/tool.py)。
- 原版现状：tool只有位置文件参数；不能只验证、不排序、选择compact/ensure_ascii或结构化错误格式。
- 交付目标：增加--check/--compact/--indent/--sort-keys及--diagnostic-json，明确默认兼容和组合约束。
- 影响模块：tool.py参数解析；编码/错误输出
- 兼容边界：原零至两个位置参数保持；check模式不打开输出文件，格式模式沿第01步原子替换。
- 正常验收：有效JSON --check不输出文档且退出0，compact结果合法，无sort时保持原输入成员顺序。
- 异常／边界：坏输入返回位置代码、互斥参数、stdout/stderr隔离、流格式与encoding自动识别。
- 原生回归：test_tool.py；全双引擎套件累计回归
- 真实依赖：01, 09, 15, 19

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
