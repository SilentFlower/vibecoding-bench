# Inflect：二十步真实工程迭代路线

固定 [jaraco/inflect@99596854bd296af1557db2015cfa98c8104ec155](https://github.com/jaraco/inflect/tree/99596854bd296af1557db2015cfa98c8104ec155)，原生证据见 [单仓审查](./inflect.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．多词转换保持分词对齐且不越界

- **类型与来源**：修复；[官方#172](https://github.com/jaraco/inflect/issues/172) 与固定源码。
- **原版现状与收益**：plural处理I'm only here for a minute, John.实测postprocess IndexError，原/结果词数不同时按原index写结果。
- **交付及模块**：让大小写恢复基于实际转换片段映射；不直接裁切orig掩盖丢失文本；engine.postprocess、_pl_special_*／_plnoun返回映射边界。
- **兼容与依赖**：短词和既有compound/经典变体保持，不承诺对任意句子做语义单复数改写；步骤依赖：无。
- **正常验收**：示例句子返回受控结果或专属输入错误，绝不IndexError；合法compound文本完整。
- **异常／边界验收**：多空格、标点、缩写、classical带双分支、结果短于/长于原词数。
- **原生回归**：tests/test_pwd.py、tests/test_compounds.py。

## 02．自定义动词定义参与词形比较

- **类型与来源**：修复；原生test_user_input_defverb_compare已知xfail与实际False结果。
- **原版现状与收益**：defverb注册will/shall关系后compare和compare_verbs均False。
- **交付及模块**：比较引擎直接考虑已注册各人称映射及方向，不让后注册其他人称遮住有效关系；engine.defverb／_plequal／compare_verbs。
- **兼容与依赖**：plural_verb原规则优先级保持；compare仍返回现有eq/s:p/p:s/p:p/False集合；步骤依赖：无。
- **正常验收**：注册示例后will/shall返回s:p、反序p:s。
- **异常／边界验收**：多个人称重复单数、None规则、重定义覆盖、内置和用户冲突不误判无关词。
- **原生回归**：tests/test_pwd.py。

## 03．所有格比较正确区分同数变体

- **类型与来源**：修复；[官方#58](https://github.com/jaraco/inflect/issues/58) 与固定源码。
- **原版现状与收益**：dresses's/dresses'与dress's/dress'都被报告p:s；原生期待分别p:p与s:s，已知xfail仍存在。
- **交付及模块**：归一化所有格词尾时保留词干单复数和可选撇号写法，比较后恢复类别；engine._pl_check_plurals_adj／compare_adjs／_plequal。
- **兼容与依赖**：不把任意结尾s的词都当复数；现有普通名词比较类别保持；步骤依赖：无。
- **正常验收**：dresses两种所有格为p:p，dress和Jess两种为s:s。
- **异常／边界验收**：单个撇号、Unicode撇号按显式支持策略、名词本来以ss结尾及classical词。
- **原生回归**：tests/test_pwd.py。

## 04．分组读数尊重自定义one和zero

- **类型与来源**：修复；原生test_numwords_group的one参数xfail与观察ten,one。
- **原版现状与收益**：number_to_words(101,group=2,one=unity)仍ten,one，覆盖词未贯穿group1b/2/3。
- **交付及模块**：所有组尾单个数字经过同一当前调用读法选项，修复one/zero不一致；engine.group1bsub／group2sub／group3sub／enword。
- **兼容与依赖**：保持group=2既定左分组布局，不擅自把123默认变one twenty-three；不改无覆盖词输出；步骤依赖：无。
- **正常验收**：101/group2得到ten,unity，重复调用不记住上次one。
- **异常／边界验收**：前导0、全0、组尾1、decimal与wantlist、group1/3及并发不同engine。
- **原生回归**：tests/test_pwd.py、tests/test_numwords.py。

## 05．classical参数校验失败不留下半修改

- **类型与来源**：修复；固定engine定义、原生test_pwd.py与本地词形/数字处理场景。
- **原版现状与收益**：classical(all=True,unknown=True)先打开全部模式再抛UnknownClassicalModeError，状态污染后续调用。
- **交付及模块**：先校验完整参数集/类型，再一次提交新classical_dict；engine.classical。
- **兼容与依赖**：合法现有组合和默认names保留；不把任意truthy对象强制转bool而掩盖误用；步骤依赖：无。
- **正常验收**：非法键失败后状态字典与输出均等于调用前。
- **异常／边界验收**：all与具体项组合顺序、多个非法键、非法值、已有自定义规则不变。
- **原生回归**：tests/test_classical_all.py、tests/test_pwd.py。

## 06．数字字符串的严格语法模式

- **类型与来源**：增强；[官方#230](https://github.com/jaraco/inflect/issues/230) 与固定源码。
- **原版现状与收益**：number_to_words清除非数字；1e3变13、abc变0、3:2变32，调用者无法发现误输入。
- **交付及模块**：增加opt-in严格decimal/scientific输入解析，拒绝未声明符号，给带位置的BadNumValueError；engine.number_to_words／_chunk_num、数字解析helper。
- **兼容与依赖**：旧宽松行为保持；真实Number既有科学计数已支持，不重复当新增；步骤依赖：无。
- **正常验收**：严格1e3得到one thousand、合法Decimal保留小数位，abc/3:2受控拒绝。
- **异常／边界验收**：空白/正负号、NaN/Infinity、多个小数点、过大指数及Unicode数字策略。
- **原生回归**：tests/test_numwords.py、tests/test_pwd.py。

## 07．compound头词可应用自定义词规则

- **类型与来源**：增强；[官方#163](https://github.com/jaraco/inflect/issues/163) 与固定源码。
- **原版现状与收益**：defnoun(jeans,jeans)对单词生效，但blue jeans仍blue jeanss；规则目前匹配整个word。
- **交付及模块**：增加明确的compound_head规则范围，在确定的头词上运行用户规则再重组；engine.defnoun／ud_match／_plnoun／_sinoun、compound helpers。
- **兼容与依赖**：现有默认whole匹配保持；介词compound仍按既定头词规则，不把regex无条件匹配任意子串；步骤依赖：无。
- **正常验收**：显式head规则让blue jeans不变，pair of jeans只处理正确头部。
- **异常／边界验收**：前/后置介词、连字符、大小写、规则冲突、反向单数和多义词。
- **原生回归**：tests/test_compounds.py、tests/test_pwd.py。

## 08．减少一次性CLI的冷导入耗时

- **类型与来源**：增强；[官方#234](https://github.com/jaraco/inflect/issues/234) 与固定源码。
- **原版现状与收益**：三个独立进程import实测1.68–1.73秒，短命命令等待明显。
- **交付及模块**：分析并延迟非必需初始化/重复类型guard编译，在相同功能契约下缩短冷启动；inflect模块级规则初始化、_types.Word、typeguard包装边界。
- **兼容与依赖**：保持公开类身份/pickle路径、导入副作用和参数异常，不通过移除类型验证取得虚假提速；步骤依赖：无。
- **正常验收**：同主机交错原版/候选多轮中位冷导入改善≥30%，原生全部回归保持。
- **异常／边界验收**：无写缓存权限、第二次调用、并发导入、禁pyc与已缓存模式分别说明成本。
- **原生回归**：完整原生pytest/doctest、tests/test_typing.py、tests/test_pwd.py。

## 09．金额的精确英语读法

- **类型与来源**：增强；[官方#213](https://github.com/jaraco/inflect/issues/213) 与固定源码。
- **原版现状与收益**：number_to_words没有currency模式；decimal=and仅替换小数点单词，不能规范minor units。
- **交付及模块**：新增明确number_to_currency接口，Decimal/字符串输入，显式币种名称与小数位/舍入策略；engine数词管线、新currency helper。
- **兼容与依赖**：普通number_to_words不改；不猜$币种、不查询汇率，避免二进制float隐式舍入；步骤依赖：06。
- **正常验收**：USD示例100020.56按选项输出dollars/cents或56/100，单数复数正确。
- **异常／边界验收**：负值、零minor、超精度、未知币种、NaN和未提供舍入策略拒绝。
- **原生回归**：tests/test_numwords.py、新增原生currency场景。

## 10．带计量单位与百分号的数值读法

- **类型与来源**：增强；[官方#230](https://github.com/jaraco/inflect/issues/230) 与固定源码。
- **原版现状与收益**：33%与33º现版都只读thirty-three，失去单位；用户需自行处理单位复数。
- **交付及模块**：新增quantity helper，显式unit registry定义符号、名称、数一致规则；engine.number_to_words／plural_noun与quantity解析helper。
- **兼容与依赖**：普通数词函数仍只转换数字；不推断歧义符号#或撇号，不捆绑货币/单位换算；步骤依赖：06。
- **正常验收**：33%读thirty-three percent，1度与2度采用约定单复数。
- **异常／边界验收**：未知/相似Unicode符号、前后缀单位、负数、小数和不变单位名称。
- **原生回归**：tests/test_numwords.py、tests/test_pl_si.py。

## 11．保留上下文的文本数字替换

- **类型与来源**：增强；[官方#148](https://github.com/jaraco/inflect/issues/148) 与固定源码。
- **原版现状与收益**：number_to_words面向单个值；将整句传入会拼合数字并丢失非数字文本。
- **交付及模块**：新增replace_numbers(text,policy)扫描数字token并替换，保留原文非命中区段；新文本token扫描helper、engine.number_to_words。
- **兼容与依赖**：不把inflect的函数调用语法当数字扫描器；默认跳过URL/版本号/标识符，策略显式；步骤依赖：06。
- **正常验收**：In 2019, saved 54.得到两处读数且标点/空格完整。
- **异常／边界验收**：负数边界、小数与句末点、Unicode邻接、URL/version、重叠token与输出位置映射。
- **原生回归**：tests/test_numwords.py、新增原生文本替换场景。

## 12．明确的年份与编号分组读法

- **类型与来源**：增强；[官方#217](https://github.com/jaraco/inflect/issues/217) 与固定源码。
- **原版现状与收益**：group只给固定长度切分，123/group2为twelve,three；没有美式one twenty-three这种显式读法。
- **交付及模块**：新增named reading profile（如year/identifier），独立定义头组/零位与连接格式；engine.number_to_words／enword、profile配置。
- **兼容与依赖**：原group=0..3不改；不宣称所有英语地区相同，profile仅列固定约定；步骤依赖：04。
- **正常验收**：year2001/twenty模式和identifier123按所选规范读，默认数词不变。
- **异常／边界验收**：000开头、整百、跨千界、负数/小数不适用profile时受控拒绝。
- **原生回归**：tests/test_numwords.py、tests/test_pwd.py。

## 13．分数的英语数词与分母词形

- **类型与来源**：增强；现有数词管线会清除斜杠；分数朗读属于明确新增契约。
- **原版现状与收益**：1/2没有分数语法，普通numwords会把斜杠删除；当前没有Fraction入口专用语义。
- **交付及模块**：新增fraction_to_words支持标准Fraction或明确n/d语法，使用序数分母和不规则half/quarter；新fraction helper、engine.ordinal／number_to_words／plural_noun。
- **兼容与依赖**：不把旧number_to_words斜杠行为静默改掉，不执行输入表达式；是否约分由参数确定；步骤依赖：06。
- **正常验收**：1/2为one half、3/4为three quarters，混合数规则明确。
- **异常／边界验收**：分母0、负号位置、大整数、是否约分与不支持的浮点输入。
- **原生回归**：tests/test_numwords.py、新增原生fraction场景。

## 14．受限英语数词解析为数值

- **类型与来源**：增强；固定源码只有number_to_words单向转换，无对应英文读数解析入口。
- **原版现状与收益**：用户需要从已生成英文读数恢复数值，只能另写解析器。
- **交付及模块**：新增words_to_number，首版限定本库标准cardinal/decimal语法并返回int/Decimal；新逆向数词parser与既有unit/teen/ten/mill词表。
- **兼容与依赖**：不接受任意自然语言或模糊语义；方言/ordinal/fraction不在首版范围，不能eval文本；步骤依赖：06。
- **正常验收**：标准number_to_words数值集合往返一致，Decimal小数位策略明确。
- **异常／边界验收**：重复量级、错误and/连字符、未知词、负号、极大数与恶意长串受控失败。
- **原生回归**：tests/test_numwords.py、新增原生逆向数词场景。

## 15．保留缩写边界的命名大小写转换

- **类型与来源**：增强；[官方#200](https://github.com/jaraco/inflect/issues/200) 与固定源码。
- **原版现状与收益**：现有postprocess只恢复词形大小写，不提供pascalize/camelize/kebab/underscore用户入口。
- **交付及模块**：增加独立word-boundary tokenizer与命名style helper，显式缩写保留策略；新命名style helper，不混入engine.postprocess。
- **兼容与依赖**：不影响普通单复数或proper-names模式；不把非英语字符串强制拉丁化；步骤依赖：无。
- **正常验收**：HTTPServer到http_server、XML reader到指定Camel输出，缩写规则可配。
- **异常／边界验收**：数字段、已有分隔符、连续缩写、Unicode、空值与一字母词。
- **原生回归**：tests/test_unicode.py、新增原生命名style场景。

## 16．分词到基础动词的候选恢复

- **类型与来源**：增强；[官方#79](https://github.com/jaraco/inflect/issues/79) 与固定源码。
- **原版现状与收益**：present_participle只有第三人称→进行分词；running/killed等反向需求没有入口。
- **交付及模块**：新增verb_candidates返回候选和匹配规则，按用户词表消除歧义；新逆向verb helper、PRESENT_PARTICIPLE_REPLACEMENTS、defverb规则。
- **兼容与依赖**：不承诺无词典唯一还原（如lying的歧义），不把候选列表第一项伪装确定结果；步骤依赖：02。
- **正常验收**：running候选含run，killed按支持过去式规则含kill，用户规则优先。
- **异常／边界验收**：不规则词、双写/e删除、普通名词ending、未知词与自定义词形冲突。
- **原生回归**：tests/test_pwd.py、新增原生verb恢复场景。

## 17．解释单次词形转换命中的规则

- **类型与来源**：增强；固定engine定义、原生test_pwd.py与本地词形/数字处理场景。
- **原版现状与收益**：engine现有流程返回str/False，实际产品用户难定位classical/自定义/后备规则选型。
- **交付及模块**：新增explain_inflection返回结果、方向、命中规则类型、头词和相关模式快照；engine._plnoun／_sinoun／ud_match／postprocess的可选追踪。
- **兼容与依赖**：默认普通返回值和性能保持；不泄漏任意对象repr，不把追踪结果当语言学绝对证明；步骤依赖：无。
- **正常验收**：children解释为内置不规则，customURL指出用户规则，fallback明确标注推断。
- **异常／边界验收**：分支交替、compound、classical模式、不可逆/False、多层追踪顺序稳定。
- **原生回归**：tests/test_pwd.py、tests/test_compounds.py。

## 18．可移植的自定义词汇规则包

- **类型与来源**：增强；固定engine定义、原生test_pwd.py与本地词形/数字处理场景。
- **原版现状与收益**：defnoun/defverb/defadj/defa/defan分散修改engine，原生没有序列化/整体导入契约。
- **交付及模块**：增加版本化rule bundle，校验所有regex/替换引用后原子载入并可导出；engine规则注册API、新bundle schema/loader。
- **兼容与依赖**：仅数据，不执行Python/任意导入；现有逐条API继续可用，保留规则顺序和case=preserve；步骤依赖：05。
- **正常验收**：同一规则包在两个独立engine得到相同单复数/冠词，导出重载一致。
- **异常／边界验收**：坏regex、无效反向引用、重复ID、未知版本、半途失败不留部分词表。
- **原生回归**：tests/test_pwd.py、tests/test_unicode.py。

## 19．作用域内临时词形选项

- **类型与来源**：增强；固定engine定义、原生test_pwd.py与本地词形/数字处理场景。
- **原版现状与收益**：classical/count/gender保存engine状态，手动改回容易漏掉，缺context manager。
- **交付及模块**：提供options(...)上下文，按约定保存/恢复classical/count/gender并支持嵌套；engine.classical／num／gender与新options上下文。
- **兼容与依赖**：不把共享engine变成线程安全；显式方法仍持久修改，选项context不撤销新加用户规则除非另约定；步骤依赖：05。
- **正常验收**：with names=False内部Property为Properties，退出后恢复原proper-name行为。
- **异常／边界验收**：嵌套count/gender、异常退出、非法参数不进入、用户规则在作用域内增加的策略。
- **原生回归**：tests/test_classical_all.py、tests/test_pwd.py。

## 20．批量词形转换与逐条错误结果

- **类型与来源**：增强；固定engine定义、原生test_pwd.py与本地词形/数字处理场景。
- **原版现状与收益**：单项函数与Python map遇第一条错误即停止，无标准批处理返回路径/方法/错误。
- **交付及模块**：新增有界批量处理接口，按调用开始的选项快照运行，支持fail-fast或逐条结果；engine公开方法分派、Word校验、新batch helper。
- **兼容与依赖**：不暴露任意getattr调用、不共享修改persistent_count；流式消费与最大批量显式；步骤依赖：18、19。
- **正常验收**：包含noun/article/number任务按输入顺序返回结果，坏一项可报告索引并继续。
- **异常／边界验收**：生成器输入、未知操作、缺参数、超批量、结果中异常信息和提前关闭。
- **原生回归**：tests/test_typing.py、tests/test_pwd.py、新增原生batch场景。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
