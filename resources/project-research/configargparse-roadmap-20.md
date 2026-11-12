# ConfigArgParse：二十步真实工程迭代路线

固定 [bw2/ConfigArgParse@3ab2f323abcdd321b6c423f9eb6304ce35681307](https://github.com/bw2/ConfigArgParse/tree/3ab2f323abcdd321b6c423f9eb6304ce35681307)，原生证据见 [单仓审查](./configargparse.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．配置内重复键策略

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：DefaultConfigFileParser用OrderedDict覆盖重复port，实测只保留2。
- **交付及模块**：增加duplicates=last/warn/error，错误保留文件与两处位置；ConfigFileParser.parse返回metadata边界、Default/INI/YAML/TOML解析器。
- **兼容与依赖**：默认last保持；跨文件覆盖属于正常层级，不视为同文件重复；步骤依赖：无。
- **正常验收**：同文件重复port可在error模式拒绝，正常单定义解析相同。
- **异常／边界验收**：quoted key、长选项别名指同一Action、空值和重复list动作有明确规则。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 02．参数转换错误带真实来源位置

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：argparse错误只有option/值，_source_to_settings有文件来源但没有行列映射。
- **交付及模块**：配置解析保留字段位置，并把类型／choices失败附实际文件、行和环境名；ConfigFileParser、convert_item_to_command_line_arg、ArgumentParser.error。
- **兼容与依赖**：原退出码和error调用方式保持；CLI输入不伪标成配置来源；步骤依赖：无。
- **正常验收**：bad port类型失败定位settings.conf对应行。
- **异常／边界验收**：多层覆盖胜出源、list第N项、Composite和非seek流，错误不默认打印秘密值。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 03．诊断输出遮蔽敏感参数

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：format_values实测把合成secret完整输出，原API无sensitive标记。
- **交付及模块**：add_argument可标sensitive，format_values/print_values及explain使用固定占位；add_argument metadata、format_values／print_values。
- **兼容与依赖**：普通非敏感输出保持；原始内部数据为解析所需，不把遮蔽误当数据加密；步骤依赖：无。
- **正常验收**：敏感值来自CLI/env/config/default都不在安全诊断中出现。
- **异常／边界验收**：--secret=value、短选项合并、重复参数、list与异常message内值都覆盖。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 04．配置导出可选择字段

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：write_config_file按所有可配置Action收集当前值，无字段白名单／敏感排除策略。
- **交付及模块**：增加export/include/exclude元数据及导出选择集，默认敏感字段显式占位或不导出；get_items_for_config_file_output、add_argument、write_config_file。
- **兼容与依赖**：既有write路径必须来自真实CLI门禁保持；不改解析结果，只限制序列化；步骤依赖：03。
- **正常验收**：只导出公开host/port而非secret，重读保留所选值。
- **异常／边界验收**：别名、子命令、SUPPRESS、count/list与excluded字段不能从来源字典重新漏出。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 05．配置文件原子发布

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：虽先serialize再open，但真实写入仍直接w截断，磁盘中途失败可破坏旧文件。
- **交付及模块**：增加atomic=True同目录临时文件完整写入后replace，维护模式和清理；write_config_file、可选文件发布helper。
- **兼容与依赖**：默认自定义open_func保持，atomic需能力声明；不把rename说成断电持久；步骤依赖：无。
- **正常验收**：配置写出后原parser可读，读者只见旧／新完整内容。
- **异常／边界验收**：多输出路径不是跨文件事务；写/close/replace失败各有明确结果，不绕过写参数来源门禁。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 06．零附加依赖的JSON配置解析器

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：YAML可解析部分JSON但需要依赖，原公开parser列表无专门JSON parser。
- **交付及模块**：增加JSONConfigFileParser，严格要求对象并按已定义list／scalar契约转换；新增ConfigFileParser子类、公开导出。
- **兼容与依赖**：不把JSON parser与YAML heuristic混淆，nested对象默认拒绝或显式交给flatten模式；步骤依赖：01。
- **正常验收**：JSON bool/string/number/list对应argparse动作正确。
- **异常／边界验收**：重复key策略、null、非object根和坏UTF8有明确诊断。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 07．受控包含配置文件

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：default列表支持多个文件，但配置内容没有literal include机制。
- **交付及模块**：opt-in includes使用字面相对文件路径，基于当前源目录解析，限制根／深度／循环；ConfigFileParser元数据、_open_config_files。
- **兼容与依赖**：默认关闭，不执行shell/source、变量或网络；包含文件仍不能设置写出配置参数；步骤依赖：无。
- **正常验收**：主配置引入同目录子配置，按出现顺序确定优先。
- **异常／边界验收**：循环、越界、缺文件、重复引入策略和非文件stream无base时拒绝。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 08．显式配置profile选择

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：INI/TOML已有固定section列表，不能运行时从同一parser选择profile并解释覆盖链。
- **交付及模块**：增加profile参数，把预声明profile映射为section组合，CLI只选名字；TomlConfigParser／IniConfigParser、ArgumentParser元数据。
- **兼容与依赖**：现有固定sections保留；profile本身不允许文件任意选择写输出或动态导入parser；步骤依赖：无。
- **正常验收**：dev/prod使用同一Schema动作定义但各自port生效。
- **异常／边界验收**：未知profile拒绝，多个选择、继承链循环、默认profile和环境选择优先级清楚。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 09．配置值的显式变量引用

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：Default/YAML路径直接取字符串，未提供统一受控${NAME}展开。
- **交付及模块**：增加opt-in变量解析，以本次提供的env_vars及已定义配置键为输入；配置值转换前helper、parse_known_args。
- **兼容与依赖**：默认字面保留，INI本身插值不被重复展开；不执行命令替换或eval；步骤依赖：03。
- **正常验收**：ROOT与相对路径拼成值，缺省表达式按定义工作。
- **异常／边界验收**：循环／深度／长度、未授权环境、美元转义和敏感诊断遮蔽。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 10．每个参数可选来源优先级

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：当前统一CLI>env>config>default；有应用需要某指定env胜出且仍保留其他CLI习惯。
- **交付及模块**：为Action提供显式precedence列表，在转换前挑选获胜源；parse_known_args、source_to_settings、add_argument metadata。
- **兼容与依赖**：默认全局顺序完全保持；列表只能包含合法来源，不让write-out action接受env/config；步骤依赖：无。
- **正常验收**：指定port env优先时env生效，其他name仍CLI优先。
- **异常／边界验收**：相同值不同来源也记录真实winner、缺源、append和互斥组组合。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 11．环境变量迁移别名

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：Action.env_var为单名，auto前缀可生成单名，缺少旧名→新名迁移便利。
- **交付及模块**：支持env_var_aliases有序列表并给冲突诊断，新名优先规则显式；add_argument、parse_known_args环境读取。
- **兼容与依赖**：已有字符串env_var保持；只取本次env_vars，不遍历打印全环境；步骤依赖：无。
- **正常验收**：NEW_PORT存在时胜出，只有OLD_PORT时后备并可警告来源。
- **异常／边界验收**：两者值相同/不同、空串、alias重复、自动前缀冲突和sensitive参数遮蔽。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 12．嵌套配置映射到参数命名空间

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：YAML server.port当前变字符串server={port:...}，不能直接映射--server-port。
- **交付及模块**：提供明确flatten mapping，将预定义section路径映射Action，可指定分隔／别名；YAML/JSON/TOML parser adapter、get_possible_config_keys。
- **兼容与依赖**：默认flat保持；不能把含点字面键无条件拆开，映射须由应用明确选择；步骤依赖：无。
- **正常验收**：nested server.port映射--server-port并走int类型，其他值不乱窜。
- **异常／边界验收**：字面点键、list-of-object、同名冲突、unknown层级和scalar/table冲突提前拒绝。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 13．未知配置项的结构化报告

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：目前ignore_unknown开关或parse_known_args返回合成argv，缺少区分拼写错误与未知CLI的诊断对象。
- **交付及模块**：提供unknown_config=ignore/warn/error及源位置列表，与真实unknown argv分离；parse_known_args、get_command_line_key_for_unknown_config_file_setting。
- **兼容与依赖**：默认现有行为保持；不能把配置未知项伪装真实CLI影响写参数检查；步骤依赖：02。
- **正常验收**：拼错prot报告源文件与建议port，未知真实--flag仍原接口返回。
- **异常／边界验收**：多个文件同未知键、子命令专属Action、hyphen/underscore和alias不误报。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 14．带说明的安全配置模板

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：已有write_config输出当前有效值，没有以help/默认为模板且不依赖实际运行secret的模式。
- **交付及模块**：新增render_config_template，输出可配置Action的说明、类型、默认或占位；ConfigFileParser.serialize、Action元数据、template helper。
- **兼容与依赖**：普通write_config保持；不读取实际env/provider来生成示例，sensitive从不复制现值；步骤依赖：03、04。
- **正常验收**：host/port模板有help和默认，secret为空占位，原parser可读取。
- **异常／边界验收**：required无默认、list/count、子命令、格式不支持注释时采用另附说明而非无效语法。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 15．每次解析产生独立结果快照

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：get_source_to_settings_dict返回同一内部dict，下一次parse重写状态，用户需手工copy。
- **交付及模块**：新增ParseResult包含Namespace、不可变/深拷贝来源摘要、unknown和warnings；ArgumentParser.parse_result、来源结构。
- **兼容与依赖**：原parse_args仍返回Namespace，旧来源方法保持；不把不可序列化Action对象暴露成JSON快照；步骤依赖：无。
- **正常验收**：同parser连续两次parse，第一结果的值和来源不变。
- **异常／边界验收**：mutable defaults、append list、失败parse和自定义Namespace不会写坏前次结果。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 16．只预览将使用的配置源

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：_open_config_files是私有且会打开流并运行callable，没有无副作用发现入口。
- **交付及模块**：新增discover_config_files默认只列路径匹配及顺序，callable标为未执行来源；ArgumentParser源发现helper。
- **兼容与依赖**：默认配置解析仍原方式，dry discovery不调用provider、不创建文件；步骤依赖：无。
- **正常验收**：glob+PathLike列表预览与随后真实解析顺序相符。
- **异常／边界验收**：缺路径、glob稳定排序规则、重复source、不可读目录、provider名称不泄露返回值。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 17．参数允许的来源范围

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：除write-out特殊门禁，普通Action无法声明只能CLI或只能env。
- **交付及模块**：新增allowed_sources元数据，在合成argv前拒绝不允许的来源或按显式策略忽略；add_argument、parse_known_args、源转换入口。
- **兼容与依赖**：write-out已有仅真实CLI限制是不可放宽的底线，新增参数也不能覆盖它；步骤依赖：无。
- **正常验收**：确认类参数只允许CLI时配置/env不能设置；普通port仍三层。
- **异常／边界验收**：source value伪装选项、缩写/短选项、子命令和fromfile路径继续原安全回归。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 18．跨来源列表合并

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：append/nargs可消费列表，但高优先源通常覆盖低源；不能声明层间extend／unique规则。
- **交付及模块**：增加Action级merge_sources策略，先按来源合并再交argparse动作转换；parse_known_args、convert_item_to_command_line_arg。
- **兼容与依赖**：默认覆盖保留，count/boolean与list策略不混用；不重复实现原append动作；步骤依赖：10。
- **正常验收**：config标签A加env B加CLI C可按指定顺序得到A/B/C，unique去重稳定。
- **异常／边界验收**：空列表、重复项、nargs固定长度、自定义action以及类型错误位置可追踪。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 19．显式取消低层设置

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：高层空串可能是合法值，没有清除低层配置并恢复未设置/默认的通用显式标记。
- **交付及模块**：增加结构化unset标记或单独取消键集合，在来源解析时清除选定层值；ConfigFileParser结果协议、parse_known_args。
- **兼容与依赖**：不能选择普通字符串如null一概当unset；默认所有旧文本字面不变；步骤依赖：无。
- **正常验收**：override层取消base代理URL，后续按明确定义回退默认或missing。
- **异常／边界验收**：必需参数取消报错，list空与unset区分、CLI重新指定可恢复，来源记录取消动作。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 20．按源格式明确选择解析器

- **类型与来源**：增强提案；固定configargparse.py公开定义及observe.py原生CLI场景；无未核实issue编号。
- **原版现状与收益**：Composite按尝试顺序，源码已警告INI在TOML前会误识别；没有per-extension选择器。
- **交付及模块**：新增DispatchConfigParser按明确扩展名/源标签选择预声明parser，无标签才用显式fallback；CompositeConfigParser附近新策略、_open_config_files来源metadata。
- **兼容与依赖**：原Composite仍可用；不自动导入按内容命名模块，不让文件控制parser类；步骤依赖：无。
- **正常验收**：同次读取.ini/.toml/.yaml分别走指定parser而非猜测，类型输出一致。
- **异常／边界验收**：未知扩展、字符串stream、扩展名内容不符、缺可选依赖和非seek流有确定错误。
- **原生回归**：tests/test_configargparse.py对应parser/precedence/action/serialization原生集合与164主测试、226子测试回归。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
