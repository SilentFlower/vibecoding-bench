# ftfy：二十步真实工程迭代路线

固定 [rspeer/python-ftfy@74dd0452b48286a3770013b3a02755313bd5575e](https://github.com/rspeer/python-ftfy/tree/74dd0452b48286a3770013b3a02755313bd5575e)，原生证据见 [单仓审查](./ftfy.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．解释开关不能改变修整结果

- **来源／场景**：使用decode_inconsistent_utf8=False处理混合中文与mojibake，只想关闭解释以节省成本；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：fix_and_explain在steps为None时调用fix_encoding(text)遗漏config；实测中文cafÃ©在explain=True保持，False变成café
- **交付及模块**：把配置一致传递到编码修整分支，所有解释开关只影响解释生成；`ftfy/__init__.py:fix_and_explain`, `ftfy/__init__.py:fix_encoding`。
- **兼容与实际依赖**：保留默认正确修复，不把关闭解释当关闭用户选项；整类从属编码选项一次交付；步骤依赖：无。
- **正常验收**：同一配置仅切换explain，修整text逐字相同，解释分别为列表/None
- **异常／边界验收**：restore_byte_a0、replace_lossy_sequences、decode_inconsistent_utf8与fix_c1_controls的禁用均保持，空串和多轮修整也一致
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 02．无效分段长度及时拒绝

- **来源／场景**：本地批处理误把max_decode_length配置为0；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：TextFixerConfig允许0，fix_text分段pos无法前进；真实子进程1秒未结束，取证器已终止并回收
- **交付及模块**：在公开边界验证max_decode_length为正整数，统一拒绝无效配置；`ftfy/__init__.py:TextFixerConfig`, `ftfy/__init__.py:fix_text`。
- **兼容与实际依赖**：合法现有长度语义保持；不悄悄把0转换成无限制或默认值；步骤依赖：无。
- **正常验收**：长度1及默认长度都正常返回，0立即抛明确ValueError
- **异常／边界验收**：负数、bool、非整数和超长配置有一致策略，错误输入不启动修整循环
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 03．二进制文件按解码后换行

- **来源／场景**：正常UTF-16文本有两行中文；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：fix_file先按字节迭代换行再decode，UTF-16的换行被拆成半个字符；实跑抛truncated data
- **交付及模块**：使用指定编码的增量解码器先解码，再按Unicode行边界产生结果；`ftfy/__init__.py:fix_file`, `ftfy/__init__.py:guess_bytes`。
- **兼容与实际依赖**：Unicode文件入口保持；不把猜编码准确性扩展为保证；只改变已有明确编码的错误拆行；步骤依赖：无。
- **正常验收**：UTF-16/32多行中文与UTF-8多字节内容完整修整，尾行无换行也保留
- **异常／边界验收**：BOM、CRLF跨块、空文件、不完整末字节和解码错误定位均符合显式策略
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 04．HTML实体自动模式作用域

- **来源／场景**：输入由多条独立记录组成，某条含小于号不应影响后续记录；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：auto见到小于号后在当前配置关闭实体解码，后续文本沿用；这是当前文档定义，不能算缺陷
- **交付及模块**：新增显式entity_scope选项，区分整文档与逐记录作用域，保留auto的保守判断；`ftfy/__init__.py:fix_text`, `ftfy/__init__.py:fix_file`。
- **兼容与实际依赖**：默认整文档行为不变；逐记录仅在明确记录边界重置，不按任意chunk重置；步骤依赖：无。
- **正常验收**：逐记录模式下第二条amp实体可解码，文档模式继续保留
- **异常／边界验收**：小于号只是普通文字、跨行标签和嵌套实体各按所选模式，配置对象不会被外部突变
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 05．有标识的批量文本记录

- **来源／场景**：数据导入要处理record id及局部坏记录；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：fix_text处理一段，fix_file按行yield字符串；无fix_records结果合同
- **交付及模块**：新增迭代records入口，保留id、原text、结果、错误和计数，支持fail-fast/continue；`ftfy/__init__.py:fix_text`, `ftfy/__init__.py:fix_file`。
- **兼容与实际依赖**：不默认把dict转str；每记录使用独立配置状态；不吞掉未知异常；步骤依赖：无。
- **正常验收**：三条记录中一条类型错误，其余两条成功且id/顺序保持
- **异常／边界验收**：重复id、空记录、生成器中断、字节输入及continue后统计准确，未执行记录不记成功
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 06．输入输出位置映射

- **来源／场景**：编辑器高亮修整后的字符需能定位原文；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：ExplanationStep只有action/parameter，不含字符跨度；长度改变后调用者无法可靠反查
- **交付及模块**：提供fix_with_source_map，记录替换/删除/合并的原文区间到输出区间；`ftfy/__init__.py:ExplainedText`, `ftfy/fixes.py`。
- **兼容与实际依赖**：原fix_and_explain返回类型不变；映射允许多对一，不假造一一对应；步骤依赖：无。
- **正常验收**：mojibake、fi连字和NFC组合后所有输出段能追溯源位置
- **异常／边界验收**：删除控制字符、跨多个码点实体、空输出和补位字符均保留明确映射规则
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 07．每轮修整可观测轨迹

- **来源／场景**：语料维护者要理解何时解码、何时归一化改变了文字；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：现有解释可apply_plan重放，但不含每轮输入/输出、阶段或变化摘要
- **交付及模块**：新增可选trace_fixes，输出逐轮逐阶段的变化与统计，不改变算法决策；`ftfy/__init__.py:fix_and_explain`, `ftfy/__init__.py:_try_fix`。
- **兼容与实际依赖**：默认不保存中间全文，支持摘要模式；解释原有可重放合同保持；步骤依赖：无。
- **正常验收**：多层mojibake的每次解码与最终NFC有有序记录，可核对最终text
- **异常／边界验收**：未变化阶段、禁用fixer、explain=False和大段文本的截断/摘要状态明确
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 08．编码修整候选检查

- **来源／场景**：档案文字有歧义时希望先比较候选而不直接接受单一结果；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：fix_encoding按启发式选择单一路线，未公开可比较的候选集
- **交付及模块**：增加suggest_encoding_repairs，只枚举有证据的有限候选及badness变化/方案，默认不应用；`ftfy/__init__.py:_fix_encoding_one_step_and_explain`, `ftfy/badness.py`。
- **兼容与实际依赖**：不宣称概率置信度或通用编码检测；原fix_encoding结果保持；步骤依赖：无。
- **正常验收**：标准UTF8误解码候选包含现有修复路线，解释与候选文字可复核
- **异常／边界验收**：正常法语不强制产生候选；候选相同结果去重、数量上限、未知文字和有损候选明确标记
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 09．精确文字补丁

- **来源／场景**：档案校对者只愿应用对这份原文审核过的改动；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：apply_plan是可复用转换配方，设计上可应用其他文字；无带原文约束的补丁
- **交付及模块**：新增make_text_patch，保存精确替换区间、原值、目标值和输入摘要，支持验证与撤销；`ftfy/__init__.py:apply_plan`, `ftfy/__init__.py:ExplainedText`。
- **兼容与实际依赖**：不改变通用apply_plan语义；补丁不是任意脚本，未知原文不执行；步骤依赖：无。
- **正常验收**：已审核文本应用补丁等于修整结果，撤销可还原原始码点
- **异常／边界验收**：原文已变、重叠编辑、重复应用、空修整和部分失配全部明确拒绝或幂等
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 10．受保护文本区间

- **来源／场景**：Markdown代码或引用原文不允许被引号/宽度修整；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：TextFixerConfig按整个segment生效；无调用方保护跨度参数
- **交付及模块**：新增显式原文区间保护，在可修整区域运行既有逻辑并重组；`ftfy/__init__.py:fix_text`, `ftfy/__init__.py:fix_and_explain`。
- **兼容与实际依赖**：首版由调用方提供区间，不自动解析全部Markdown/HTML；保护文字逐码点不变；步骤依赖：无。
- **正常验收**：代码范围内全角/弯引号保持，正文mojibake仍修复
- **异常／边界验收**：交叠、越界、空范围、边界落在组合序列及跨分段文字有确定验证
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 11．字符映射细分策略

- **来源／场景**：日文档案想统一半角片假名但保留全角拉丁排版；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/fixes.py)。
- **原版缺口**：fix_character_width一个布尔开关同时处理全角拉丁及半角片假名；自定义只能全开/全关或手动调用
- **交付及模块**：增加明确CharacterMappingPolicy，按映射组选择，复用现有映射表而非任意替换所有字符；`ftfy/fixes.py:fix_character_width`, `ftfy/chardata.py:_build_width_map`。
- **兼容与实际依赖**：默认等于现有完整映射；不使用NFKC冒充相同范围的转换；步骤依赖：无。
- **正常验收**：选片假名组只转换该组，拉丁/空格按独立选项保持
- **异常／边界验收**：浊音组合、半角标点、CJK兼容字和非目标脚本保持；重复应用幂等
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 12．可选Unicode空白规范化

- **来源／场景**：文档从多个编辑器粘贴含NBSP、窄不换行空格和普通空格；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/fixes.py)。
- **原版缺口**：现有fix_line_breaks与remove_control_chars不提供横向空白的明确保留策略
- **交付及模块**：新增opt-in横向空白规范化，允许保留不换行语义并报告有损替换；`ftfy/fixes.py:fix_line_breaks`, `ftfy/fixes.py:remove_control_chars`。
- **兼容与实际依赖**：默认文本不增加空白转换；不折叠表格tab、代码缩进或换行；步骤依赖：无。
- **正常验收**：指定把可换行的Unicode空格统一为普通空格，NBSP按策略保持
- **异常／边界验收**：连续空格、首尾空格、窄空格、零宽连接符及软连字符不被粗暴同类处理
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 13．排版标点保留策略

- **来源／场景**：出版文本想把弯双引号变直而保留姓名中的弯撇号；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/fixes.py)。
- **原版缺口**：uncurl_quotes仅一个布尔开关，函数一起转换单/双引号
- **交付及模块**：增加可选PunctuationPolicy，独立选择引号家族与已知排版替换，保留原始策略默认；`ftfy/fixes.py:uncurl_quotes`, `ftfy/__init__.py:TextFixerConfig`。
- **兼容与实际依赖**：不做自然语言猜测或自动美化正确文字；默认输出不变；步骤依赖：无。
- **正常验收**：只选择双引号转换时姓名撇号保持，关闭时全部保持
- **异常／边界验收**：连续引号、CJK引号、prime角分符号和左右嵌套不会误当英文撇号
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 14．按显示宽度截断

- **来源／场景**：终端列表需要截断中英文混排标题而不切断emoji；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/formatting.py)。
- **原版缺口**：formatting提供宽度和左右居中补齐，无display_truncate
- **交付及模块**：新增显示宽度截断并可附省略号，按字素边界处理；`ftfy/formatting.py:monospaced_width`。
- **兼容与实际依赖**：不改变宽度/补齐函数；Unicode宽度版本与wcwidth依赖一起记录；步骤依赖：无。
- **正常验收**：宽度8截断中文与ASCII时总显示宽度不超限，文本短则原样
- **异常／边界验收**：组合字符、emoji ZWJ、省略号本身超宽、控制字符和零宽文字有明确定义
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 15．按显示宽度自动换行

- **来源／场景**：终端帮助文本需要中英文行宽一致；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/formatting.py)。
- **原版缺口**：只有单行宽度及justification，没有display_wrap
- **交付及模块**：增加基于显示宽度的wrap，支持缩进、现有换行和单词/字素拆分策略；`ftfy/formatting.py:monospaced_width`。
- **兼容与实际依赖**：不在fix_text默认管线插入新换行；不把字符数当显示格数；步骤依赖：无。
- **正常验收**：CJK与英文混排每行显示宽度符合配置并保持文本顺序
- **异常／边界验收**：长单词、组合序列、tab、零宽字符、空行和缩进已占满宽度时不循环
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 16．Unicode说明的结构化结果

- **来源／场景**：校对工具希望取得每字符名字与编码点而不是捕获stdout；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：explain_unicode直接打印，未提供unicode_details返回数据
- **交付及模块**：新增结构化字符详情迭代器，explain_unicode复用该数据渲染；`ftfy/__init__.py:explain_unicode`。
- **兼容与实际依赖**：原打印格式与默认行为保持；结构化数据只描述当前输入，不自动修复；步骤依赖：无。
- **正常验收**：中文、组合音标和emoji分别返回码点/名称/类别和位置
- **异常／边界验收**：未命名字符、代理码点、控制字符与多码点字素区别清楚，空串返回空集
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 17．CLI的JSONL记录处理

- **来源／场景**：数据管线每行是id+text的JSON，需只修text而保留其他列；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/cli.py)。
- **原版缺口**：CLI只按文本文件逐行输出，没有JSONL字段选择/机器解释模式
- **交付及模块**：新增--jsonl及明确text字段路径，输出记录结果和可选修整解释；`ftfy/cli.py:main`, `ftfy/__init__.py:fix_and_explain`。
- **兼容与实际依赖**：默认CLI文本输出保持；格式错误只走明确错误记录/退出码，不混入成功stdout；步骤依赖：无。
- **正常验收**：含中文及mojibake的JSONL只改变所选字段，id和其他列不变
- **异常／边界验收**：非法JSON、缺字段、非字符串、嵌套字段与解释选项有确定处理，不把整JSON当普通文字改写
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 18．CLI只检查与预览差异

- **来源／场景**：档案入库前希望先知道是否会修改，不立刻写结果；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/cli.py)。
- **原版缺口**：CLI没有check/diff，现有输出总是处理后的文本
- **交付及模块**：增加--check与--diff，定义未变化/有变化/执行错误的退出码及可读差异；`ftfy/cli.py:main`。
- **兼容与实际依赖**：默认命令不变；check不写新文件，diff不把可见控制字符直接混成格式控制；步骤依赖：无。
- **正常验收**：正常文本check成功，需修整文本给约定非零并可查看精确差异
- **异常／边界验收**：空输入、超长行、非UTF8输入、无换行尾行和输出不可写的错误码区分
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 19．文件输出失败不截断旧内容

- **来源／场景**：离线校对把输出路径指向已有归档副本；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/cli.py)。
- **原版缺口**：CLI打开输出w后边读边写，后续解码失败可能留下部分结果；无atomic输出
- **交付及模块**：新增显式原子输出模式，同目录临时文件成功结束后替换并保留所选元数据；`ftfy/cli.py:main`, `ftfy/__init__.py:fix_file`。
- **兼容与实际依赖**：默认stdout流式保持；不直接放开同文件读写，原同文件保护仍有效；步骤依赖：无。
- **正常验收**：完整成功后新文件内容正确，旧目标在处理完成前保持
- **异常／边界验收**：第二行解码错、写满、替换失败与取消保留旧目标，清理仅本次临时文件
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。

## 20．稳定的自定义修整器接口

- **来源／场景**：领域档案需要额外一个明确字符修整且能进入解释配方；[固定源码](https://github.com/rspeer/python-ftfy/blob/74dd0452b48286a3770013b3a02755313bd5575e/ftfy/__init__.py)。
- **原版缺口**：FIXERS是全局实现字典，调用方可猴子补丁但无register_fixer合同
- **交付及模块**：增加实例/管线级注册，声明名称、输入输出类型、启用选项及收敛边界；`ftfy/__init__.py:FIXERS`, `ftfy/__init__.py:_try_fix`, `ftfy/__init__.py:apply_plan`。
- **兼容与实际依赖**：不默认修改全局内建修整器；重放方案携带扩展版本，不装载远程代码；步骤依赖：无。
- **正常验收**：注册本地确定性修整器后解释可重放，其他配置实例结果保持
- **异常／边界验收**：重名、覆盖内建、返回非str、往复不收敛及缺失扩展版本明确失败
- **原生回归**：`tests/test_cli.py`, `tests/test_characters.py`, `tests/test_encodings.py`, `tests/test_bytes.py`, `tests/test_entities.py`, `tests/test_examples_in_json.py`。
