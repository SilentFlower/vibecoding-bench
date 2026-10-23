# Click：二十步真实工程迭代路线

固定 [pallets/click@2247b35ea1c47c727d7a06e51fa280e12a863ff6](https://github.com/pallets/click/tree/2247b35ea1c47c727d7a06e51fa280e12a863ff6)，原生证据见 [单仓审查](./click.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．显示异常附注

- **类型与来源**：增强提案；[官方 #2740](https://github.com/pallets/click/issues/2740) 与固定源码。
- **原版现状与收益**：ClickException.show 只输出主消息，原生 add_note 附注已复现丢失；用户看不到补救提示。
- **交付及模块**：在 CLI 的受控异常输出中按顺序展示非空附注；exceptions.py:ClickException.show、UsageError.show。
- **兼容与依赖**：未添加附注时输出保持；Python 3.10 使用 getattr 兼容，不输出额外 traceback；步骤依赖：无。
- **正常验收**：主要错误和两条附注各一次，退出码保持 1／2。
- **异常／边界验收**：空附注、Unicode、多行和带 ANSI 内容按当前 color 策略；UsageError 的 usage 不重复。
- **原生回归**：tests/test_exceptions/、tests/test_basic.py、tests/test_commands.py。

## 02．帮助标识可重复选项

- **类型与来源**：增强提案；[官方 #3652](https://github.com/pallets/click/issues/3652) 与固定源码。
- **原版现状与收益**：multiple=True 的 --tag TEXT 与普通单值选项显示相同，实测帮助没有省略号。
- **交付及模块**：对可重复选项的 metavar 输出明确重复提示；core.py:Option.get_help_spec／get_help_record。
- **兼容与依赖**：普通选项、显式 metavar 和 count 的既有展示规则保留，可通过选项关闭新标识；步骤依赖：无。
- **正常验收**：--tag TEXT... 提示可重复，实际多次输入仍得到 tuple。
- **异常／边界验收**：nargs>1、Choice、flag 和隐藏选项不出现含糊或重复标记。
- **原生回归**：tests/test_options.py、tests/test_formatting.py。

## 03．原生集合参数类型

- **类型与来源**：增强提案；[官方 #3036](https://github.com/pallets/click/issues/3036) 与固定源码。
- **原版现状与收益**：convert_type 与公开导出无 Set／FrozenSet 组合类型，用户需自行回调去重。
- **交付及模块**：新增接受 item_type 的集合类型，重复来源规范化后去重，分别返回 set 或 frozenset；types.py、__init__.py、core.py:Parameter.type_cast_value。
- **兼容与依赖**：不改变 multiple=True 的 tuple 返回；只显式采用新类型的参数受影响；步骤依赖：无。
- **正常验收**：整数、UUID 和 Choice 集合正确转换、去重。
- **异常／边界验收**：空集合、非法成员、不可哈希结果有参数定位错误；稳定帮助不依赖集合随机顺序。
- **原生回归**：tests/test_types/test_convert_type.py、tests/test_types/test_ParamType.py、tests/test_options.py。

## 04．显式支持颜色环境约定

- **类型与来源**：增强提案；[官方 #3022](https://github.com/pallets/click/issues/3022) 与固定源码。
- **原版现状与收益**：源码未解析 FORCE_COLOR／NO_COLOR，用户需在每条命令手动配置 color。
- **交付及模块**：提供可选择的环境颜色策略并定义显式 color、NO_COLOR、FORCE_COLOR、TTY 的优先级；globals.py、_compat.py、utils.py:echo。
- **兼容与依赖**：默认现有自动 TTY 行为不突变；进入新策略时显式 color 的优先级最高；步骤依赖：无。
- **正常验收**：管道下 FORCE_COLOR 可保留 ANSI，NO_COLOR 可禁用。
- **异常／边界验收**：同时设置两个环境变量、空值、嵌套 Context 和 stderr 各有确定结果；不用真实终端冒充覆盖。
- **原生回归**：tests/test_utils/test_echo.py、tests/test_utils/test_style.py、tests/test_context.py。

## 05．机器可读命令信息包含用法

- **类型与来源**：增强提案；[官方 #2992](https://github.com/pallets/click/issues/2992) 与固定源码。
- **原版现状与收益**：Command.to_info_dict 实测有 params/help 等信息但没有 get_usage 的结果。
- **交付及模块**：信息树增加解析后的 usage 和原生 usage_pieces，供文档工具使用；core.py:Command.to_info_dict、Group.to_info_dict。
- **兼容与依赖**：现有键和对象结构保留，新增字段不执行命令回调或动态默认值；步骤依赖：无。
- **正常验收**：多层命令中 usage 使用实际 command_path。
- **异常／边界验收**：空命令、隐藏参数、长名字和自定义 Context 不触发 IO；输出可 JSON 序列化。
- **原生回归**：tests/test_info_dict.py、tests/test_formatting.py。

## 06．依赖上下文的动态 Choice

- **类型与来源**：增强提案；[官方 #928](https://github.com/pallets/click/issues/928) 与固定源码。
- **原版现状与收益**：Choice.__init__ 立即 tuple(choices)，传 callable 已实测 TypeError；动态选项需自定义 ParamType。
- **交付及模块**：提供独立 DynamicChoice 或显式 choices_factory(ctx)，让校验、帮助与补全使用同一快照；types.py:Choice、shell_completion.py。
- **兼容与依赖**：静态 Choice 原有一次消费和返回原值规则保持；工厂只在有需要时调用一次；步骤依赖：无。
- **正常验收**：前置 profile 参数改变后，合法 region 值与补全同步变化。
- **异常／边界验收**：工厂失败转为明确参数错误；帮助缺少上下文不访问网络，空候选、大小写冲突有确定行为。
- **原生回归**：tests/test_types/test_Choice.py、tests/test_shell_completion.py、tests/test_options.py。

## 07．分隔符列表选项

- **类型与来源**：增强提案；[官方 #2771](https://github.com/pallets/click/issues/2771) 与固定源码。
- **原版现状与收益**：Option(nargs=-1) 明确拒绝，无带非空分隔符的公开变长选项。
- **交付及模块**：新增单 token 的显式 delimited-list 类型／配置，在 token 内按选定分隔符形成可变长度值；types.py、core.py:Option。
- **兼容与依赖**：不修改现有 nargs 或吞掉后续参数；重复 --items 与列表值的组合规则单独定义；步骤依赖：无。
- **正常验收**：--items 1,2,3 转换为三个整数且后续位置参数仍正确。
- **异常／边界验收**：空片段、尾分隔符、转义分隔符、负数和非法元素有定位错误；空分隔符拒绝。
- **原生回归**：tests/test_options.py、tests/test_parser.py、tests/test_types/test_convert_type.py。

## 08．invoke 和 forward 保留参数来源

- **类型与来源**：增强提案；[官方 #2753](https://github.com/pallets/click/issues/2753) 与固定源码。
- **原版现状与收益**：直接解析有 ParameterSource，ctx.invoke 同值实测 None；包装命令无法诊断真实来源。
- **交付及模块**：invoke 默认填充值标 DEFAULT，显式 Python kwargs 标独立 INVOCATION，forward 继承可追踪的来源；core.py:Context.invoke／forward、ParameterSource。
- **兼容与依赖**：不把 Python 调用伪装成 COMMANDLINE；现有 params 和默认值转换保持；步骤依赖：无。
- **正常验收**：包装命令 forward 的 CLI 来源和 invoke 的 Python 来源可区分。
- **异常／边界验收**：显式 None、缺省值、多层 forward 与同名参数正确；没有可知来源时保留未知而非猜测。
- **原生回归**：tests/test_context.py、tests/test_defaults.py、tests/test_commands.py。

## 09．帮助示例引用实际命令路径

- **类型与来源**：增强提案；[官方 #2683](https://github.com/pallets/click/issues/2683) 与固定源码。
- **原版现状与收益**：help 与 epilog 的 %(prog)s 原生观察保持字面；包装安装后示例命令名会过期。
- **交付及模块**：提供 opt-in help 插值，只支持命令路径等明确占位键；core.py:Command.format_help_text／format_epilog。
- **兼容与依赖**：默认任意百分号文本不变；不使用 eval，不读取配置值或环境 secret；步骤依赖：无。
- **正常验收**：同一命令以不同 prog_name 和子命令路径显示正确示例。
- **异常／边界验收**：未知占位、百分号、长路径和 Unicode 可预测；帮助仍不执行 callback。
- **原生回归**：tests/test_formatting.py、tests/test_commands.py。

## 10．范围校验与范围展示独立配置

- **类型与来源**：增强提案；[官方 #2679](https://github.com/pallets/click/issues/2679) 与固定源码。
- **原版现状与收益**：IntRange 没有 show_range 配置，帮助始终包含范围表达式。
- **交付及模块**：新增帮助层 show_range 开关，校验与 clamp 继续生效；core.py:Option.get_help_extra、types.py:IntRange／FloatRange。
- **兼容与依赖**：默认继续显示原范围；只调整展示，绝不停止边界校验；步骤依赖：无。
- **正常验收**：隐藏范围的 verbose count 在 0..3 正常夹取。
- **异常／边界验收**：开闭区间、负数、float 与多个选项的策略不互串；错误仍解释合法范围。
- **原生回归**：tests/test_types/test_IntRange.py、tests/test_types/test_FloatRange.py、tests/test_options.py。

## 11．要求输出路径尚不存在

- **类型与来源**：增强提案；[官方 #1428](https://github.com/pallets/click/issues/1428) 与固定源码。
- **原版现状与收益**：exists=False 意味不要求存在，实测仍接受已有文件；缺少拒绝覆盖预检。
- **交付及模块**：为 Path 增加明确 must_not_exist 语义并与 exists 冲突时报配置错；types.py:Path.convert。
- **兼容与依赖**：现有 exists=False 语义保持；预检不是排他创建保证，文档明确竞争边界；步骤依赖：无。
- **正常验收**：新文件路径通过，已有普通文件和目录被拒绝。
- **异常／边界验收**：悬空符号链接按 lexists 策略定义；allow_dash、bytes、pathlib.Path 和 resolve_path 回归。
- **原生回归**：tests/test_types/test_Path.py。

## 12．相同内容保留目标文件

- **类型与来源**：增强提案；[官方 #1378](https://github.com/pallets/click/issues/1378) 与固定源码。
- **原版现状与收益**：atomic=True 写相同字节仍换 inode，已实测，构建系统发生无谓重编译。
- **交付及模块**：新增 only_if_changed 的原子写入选项，比较后相同即清除临时文件并保留目标；types.py:File、utils.py:open_file、_compat.py:_AtomicFile.close。
- **兼容与依赖**：默认始终替换行为保持；此能力不承诺多进程比较与替换的事务隔离；步骤依赖：无。
- **正常验收**：相同输出保持 inode／mtime，不同输出仍原子更新。
- **异常／边界验收**：空文件、二进制、目标缺失、比较失败、异常退出均清理临时文件；不删除非本轮目标。
- **原生回归**：tests/test_utils/test_open_file.py、tests/test_types/test_File.py、tests/test_stream_lifecycle.py。

## 13．选项帮助分组

- **类型与来源**：增强提案；[官方 #373](https://github.com/pallets/click/issues/373) 与固定源码。
- **原版现状与收益**：现有 format_options 把所有选项放在 Options，调用者只能覆写整个方法。
- **交付及模块**：增加参数 help_group 与组的显式排序，按标题呈现帮助；core.py:Parameter／Option、Command.format_options。
- **兼容与依赖**：未标组的参数仍在 Options，已有 Argument.help 和隐藏选项不改变；步骤依赖：无。
- **正常验收**：连接参数和输出参数两组各显示一次且保持声明顺序。
- **异常／边界验收**：空组不出现，重复组名合并；极窄终端、翻译标题和子命令不丢参数。
- **原生回归**：tests/test_formatting.py、tests/test_options.py、tests/test_info_dict.py。

## 14．声明顺序参数回调策略

- **类型与来源**：增强提案；[官方 #730](https://github.com/pallets/click/issues/730) 与固定源码。
- **原版现状与收益**：iter_params_for_processing 明确优先用户输入顺序，没有公开选择策略。
- **交付及模块**：增加命令级 processing_order=declaration 的 opt-in，稳定依赖前置参数的回调顺序；core.py:iter_params_for_processing、Command.parse_args。
- **兼容与依赖**：默认 invocation 保持；eager help/version 仍在普通参数前处理；步骤依赖：无。
- **正常验收**：两个参数颠倒 argv，declaration 模式回调仍按声明执行。
- **异常／边界验收**：缺省值、重复选项、eager 参数和回调抛错保持一次执行与既有退出语义。
- **原生回归**：tests/test_options.py、tests/test_defaults.py、tests/test_command_decorators.py。

## 15．生成等价的规范 argv

- **类型与来源**：增强提案；[官方 #1279](https://github.com/pallets/click/issues/1279) 与固定源码。
- **原版现状与收益**：Context 只有解析后的 params／args，无公开反向规范 argv；pip-tools 需稳定记录调用。
- **交付及模块**：提供有界的参数序列化器，支持内建可逆类型并明确不支持任意回调结果；core.py:Context、types.py:ParamType。
- **兼容与依赖**：不把原始 argv 与规范化结果混淆；默认不包含敏感或 hide_input 参数，调用者显式决定；步骤依赖：无。
- **正常验收**：短／长选项和 equals 语法相同值生成同一 argv，重新解析值相等。
- **异常／边界验收**：multiple、flag、负数、位置参数、-- 和含空格值正确；不可逆对象明确报不支持。
- **原生回归**：tests/test_context.py、tests/test_parser.py、tests/test_types/、tests/test_options.py。

## 16．不污染全局 gettext 的翻译注入

- **类型与来源**：增强提案；[官方 #2706](https://github.com/pallets/click/issues/2706) 与固定源码。
- **原版现状与收益**：各模块直接从 gettext 导入函数，切换域依赖进程全局状态。
- **交付及模块**：提供 Context 范围的 translation 对象，统一用于内建消息和复数表达；core.py:Context、exceptions.py、types.py、formatting.py、termui.py。
- **兼容与依赖**：没有显式 translation 时维持 GNU 全局函数行为；不能只翻译帮助而漏掉错误；步骤依赖：无。
- **正常验收**：两个不同翻译上下文分别输出目标语言，不修改 gettext.textdomain。
- **异常／边界验收**：嵌套 Context、缺少翻译、ngettext 复数和异常清理后不泄漏翻译状态。
- **原生回归**：tests/test_context.py、tests/test_formatting.py、tests/test_exceptions/、tests/test_types/。

## 17．嵌入程序可注入输出流

- **类型与来源**：增强提案；[官方 #2361](https://github.com/pallets/click/issues/2361) 与固定源码。
- **原版现状与收益**：Context 未接受 stdout／stderr；CliRunner 的全局替换只适合单线程测试，不适合宿主集成。
- **交付及模块**：增加 Context 作用域的默认文本输出流，供 echo、内建错误与 prompt 路由；core.py:Context、globals.py、utils.py:echo、termui.py。
- **兼容与依赖**：显式 echo(file=...) 仍优先；普通 CLI 继续系统流，不宣称完全隔离任意 print 或 C 扩展；步骤依赖：无。
- **正常验收**：两组命令各写自己的 StringIO，正常和错误流分离。
- **异常／边界验收**：嵌套上下文、bytes、TTY 探测与关闭资源所有权明确；宿主传入流不自动关闭。
- **原生回归**：tests/test_context.py、tests/test_utils/test_echo.py、tests/test_stream_lifecycle.py。

## 18．可定制受控错误呈现

- **类型与来源**：增强提案；[官方 #531](https://github.com/pallets/click/issues/531) 与固定源码。
- **原版现状与收益**：自定义错误展示需散落覆写 ClickException.show／Command.main，缺少统一入口。
- **交付及模块**：增加命令级 error_renderer 钩子，接受结构化异常与当前上下文并产生可控输出；core.py:Command.main、exceptions.py。
- **兼容与依赖**：未设置钩子使用原输出；退出码、standalone_mode=False 抛错和 Abort 不被吞掉；步骤依赖：无。
- **正常验收**：同一命令可选择一行诊断或结构化 JSON 错误，参数提示完整。
- **异常／边界验收**：renderer 自身失败有确定回退，不递归调用；敏感隐藏参数不进入诊断。
- **原生回归**：tests/test_commands.py、tests/test_basic.py、tests/test_exceptions/。

## 19．用法换行保留选项 token

- **类型与来源**：增强提案；[官方 #3362](https://github.com/pallets/click/issues/3362) 与固定源码。
- **原版现状与收益**：write_usage 把 args 交给一般 wrap_text；连字符选项的排版没有独立 token 规则。
- **交付及模块**：用法行支持不在 --long-option 的连字符处断开，过长单 token 单独占行；formatting.py:HelpFormatter.write_usage、_textwrap.py。
- **兼容与依赖**：普通说明文本的断行保持；单一长 token 允许超过宽度而不误改可复制参数；步骤依赖：无。
- **正常验收**：窄宽度的长选项跨行后每个 token 仍完整。
- **异常／边界验收**：Unicode 命令、ANSI 长度、可选方括号和无参数 Usage 边界；不得丢字符或双写。
- **原生回归**：tests/test_formatting.py、tests/test_parser.py。

## 20．提示文本结构化格式化钩子

- **类型与来源**：增强提案；[官方 #2875](https://github.com/pallets/click/issues/2875) 与固定源码。
- **原版现状与收益**：prompt_suffix 和 show_default 可配置，但默认值／choices 等完整布局由私有 _build_prompt 固定拼接。
- **交付及模块**：提供 prompt_formatter 接收提示、默认预览和 choices 元数据，统一管理布局；termui.py:_build_prompt／prompt、core.py:Option.prompt_for_value。
- **兼容与依赖**：默认格式逐字兼容；value_proc 仍负责转换，不把显示钩子变成输入解析器；步骤依赖：无。
- **正常验收**：默认值可显示在新行并保留 choices，输入结果与默认一致。
- **异常／边界验收**：hide_input 默认值不泄漏，确认重试、空输入、Unicode 与 formatter 异常不破坏终端恢复。
- **原生回归**：tests/test_utils/test_prompt.py、tests/test_options.py、tests/test_termui.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
