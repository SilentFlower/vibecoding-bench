# python-dotenv：二十步真实工程迭代路线

研究日期：2026-10-21，固定 [theskumar/python-dotenv@0b2880591780a426b0551436f47a17e7a76d954f](https://github.com/theskumar/python-dotenv/tree/0b2880591780a426b0551436f47a17e7a76d954f)，版本 1.2.4。原生隔离基线为 288 项全过，详见 [单仓审查](./python-dotenv.md)。

共 **4 步问题修复、16 步增强提案**。每步包含实现、原生回归、冻结验收和文档；接口名称及兼容取舍是本试点研究方案，上游未必采用。本轮尚未实施或冻结修复后的验收。

## 二十步交付清单

| 步骤 | 交付 | 来源／场景 | 原版现状 | 主要验收目标 |
| --- | --- | --- | --- | --- |
| 01 | 冒号默认值处理空字符串 | [#715](https://github.com/theskumar/python-dotenv/issues/715) | 空 B 使 ${B:-d} 得到空值 | 空／缺失 B 得 d，非空值保持，无默认插值语义保持 |
| 02 | CLI 字符串参数正确引用 | src/dotenv/__init__.py:get_cli_string 实际复现 | 带空格路径拆参，引号值失真 | POSIX shell 参数拆分往返保留每个参数 |
| 03 | 编辑保留非目标内容换行 | main.py:rewrite/set_key 实际字节复现 | CRLF 全部改成 LF | 注释、多行非目标值和混合换行原样保留 |
| 04 | 写入前拒绝不可表示的键 | main.py:set_key 实际复现 | 换行键写入成功但无法读回 | 非法键明确报错且原文件／新路径保持未修改 |
| 05 | 可选持久写入 | [#713](https://github.com/theskumar/python-dotenv/issues/713) | 原子替换前没有 fsync | 内容和元数据先同步，再替换与目录同步，失败阶段明确 |
| 06 | 可选严格读取 | [#631](https://github.com/theskumar/python-dotenv/issues/631)、[#467](https://github.com/theskumar/python-dotenv/issues/467) | 缺文件空返回，坏行警告后跳过 | strict 抛带位置错误，load 不留下半份环境 |
| 07 | 可配置重复键策略 | [#591](https://github.com/theskumar/python-dotenv/issues/591) | 默默取最后值 | last/warn/error 显式选择，位置清楚且不泄露值 |
| 08 | 从映射序列化 .env | [#502](https://github.com/theskumar/python-dotenv/issues/502) | 有单键编辑，无公开完整映射导出 | Unicode、引号、换行、空值与裸键可往返 |
| 09 | 生成不含值的示例模板 | [#618](https://github.com/theskumar/python-dotenv/issues/618)、[#354](https://github.com/theskumar/python-dotenv/issues/354) | 没有 template 命令 | 保留键和指定注释，去除实际值并支持显式排除 |
| 10 | 作用域内临时环境 | [#594](https://github.com/theskumar/python-dotenv/issues/594) | 只有全局加载，无可回退上下文 | 离开时恢复原值、移除新增值，异常与嵌套也正确 |
| 11 | 有序多文件加载与运行 | [#418](https://github.com/theskumar/python-dotenv/issues/418) | 重复 -f 只取最后文件 | 按顺序叠加、明确环境优先级，CLI 子进程读到合并结果 |
| 12 | 指定查找起点和上界 | [#494](https://github.com/theskumar/python-dotenv/issues/494)、[#509](https://github.com/theskumar/python-dotenv/issues/509) | 起点推断自调用栈／cwd，上溯到根 | 显式目录范围查找，不临时改 cwd、不越出已指定上界 |
| 13 | 单个表达式可保持字面量 | [#422](https://github.com/theskumar/python-dotenv/issues/422) | 只能关闭全部插值，$${B} 得 $real | opt-in 转义模式可混用字面和正常插值 |
| 14 | 按键自定义环境合并 | [#374](https://github.com/theskumar/python-dotenv/issues/374) | 只能覆盖或保留 | PATH 等指定键可去重追加，其他键遵守原 override |
| 15 | 结构化来源诊断 | [#483](https://github.com/theskumar/python-dotenv/issues/483) | 公开结果只有映射，错误日志不含加载来源 | 可查文件、行号、有效覆盖来源，默认不含值 |
| 16 | 显式初始化缺失配置 | [#644](https://github.com/theskumar/python-dotenv/issues/644) | 无 init_dotenv_path | 只在目标缺失且显式提供模板时创建，不覆盖已有文件 |
| 17 | 可选百分号变量语法 | [#459](https://github.com/theskumar/python-dotenv/issues/459) | %ROOT% 保持字面 | 启用后正确展开，默认 POSIX 解析不变 |
| 18 | 可选递归变量解析 | [#459](https://github.com/theskumar/python-dotenv/issues/459)、[#595](https://github.com/theskumar/python-dotenv/issues/595) | 一次顺序解析无法处理前向依赖 | 递归模式解析依赖图，循环／超深报错，默认顺序模式保持 |
| 19 | 显式引入其他 .env 文件 | [#617](https://github.com/theskumar/python-dotenv/issues/617) | 无受控 includes；不执行 source | opt-in 解析字面文件指令，按父文件路径解析并检测循环 |
| 20 | 检测陈旧编辑与协作写冲突 | [#713 的明确后续边界](https://github.com/theskumar/python-dotenv/issues/713)及受控交错复现 | 先读后替换可覆盖中间已成功写入 | 协作写锁与预期摘要拒绝陈旧写，不默默丢失更新 |

## 每步边界、影响模块与验收

1. **空默认值**：`variables.py:Variable.resolve` 和 `main.py:resolve_variables`。覆盖空字符串、缺失键、裸键 None、非空值、环境优先级、无默认 `${B}` 和 `interpolate=False`；只修 `:-` 的空／未设置语义。该修复会改变依赖旧空字符串行为的输出，须记录兼容说明，不能把现有“按空值覆盖”的一般规则一起改变。原生 `tests/test_variables.py`、`tests/test_main.py`。
2. **命令引用**：`__init__.py:get_cli_string` 按 POSIX 参数引用构建结果，覆盖文件路径、key、value、quote 模式和空值。用 shlex.split 核对包含空格、单／双引号、美元符号和换行的参数数组，不执行生成的 shell 字符串；不宣称适用于 Windows cmd 的不同语法。现有只比较字符串的原生用例随合法引用结果调整，并保留参数语义。`tests/test_utils.py`、`tests/test_cli.py`。
3. **编辑换行保真**：`main.py:rewrite/set_key/unset_key` 保留文件读取的原始换行，非目标 Binding.original.string 按原字节／编码还原；被修改／新增行沿用检测到的主要换行，无法判断才用 LF。覆盖 CRLF、LF、CR、混合样式、缺末尾换行、多行值、注释和删除最后一项。既有 BOM、权限保留、符号链接规则和失败清理不回归。`tests/test_main.py`、`tests/test_parser.py`。
4. **键合法性**：`main.py:set_key/unset_key` 在打开或创建目标前校验。首版拒绝空键、换行、NUL、等号等无法由现有无引号 key 写法往返的输入；需要引号才能表示的键明确拒绝，不偷换键名。覆盖 Python 和 CLI 的错误码、原文件摘要不变、新文件不出现、合法 Unicode／下划线键照常使用。`tests/test_main.py`、`tests/test_cli.py`。
5. **持久写入**：`main.py:rewrite` 拟增加 opt-in durable 选项，供 set/unset 透传。临时文件写入、flush、需要保留的模式设置、文件 fsync、replace、支持时目录 fsync 顺序可观察；文件同步失败发生在 replace 前时保留旧文件并清理临时文件。替换后目录同步失败与替换前失败分开报告，不声称可以撤销已发生的替换。明确 Windows 和不支持目录同步的文件系统能力；普通测试只证明调用顺序与错误路径，不证明断电后一定无损。`tests/test_main.py`、`tests/test_cli.py`。
6. **严格读取**：公开 `load_dotenv`／`dotenv_values` 和 DotEnv 增加 strict=False；严格时缺文件或解析错误抛带路径、行号且不含配置值的异常，默认仍兼容原返回／警告。先完成解析再修改 os.environ，失败不加载前半段；关闭环境加载的 PYTHON_DOTENV_DISABLED 仍先返回不读文件。与普通 stream、空文件和 verbose 的组合明确。`tests/test_main.py`、`tests/test_parser.py`。
7. **重复键**：DotEnv 解析增加 duplicates="last|warn|error"，默认 last 保留旧行为；同一输入文件的重复定义能定位两处行号，error 与 strict 一样在修改环境前失败，warn 不打印值。跨文件覆盖属于第 11 步层级策略，不自动视作文件内重复。重复的空值、裸键和 export 都要覆盖。`tests/test_main.py`、`tests/test_parser.py`。
8. **映射导出**：拟增加 `dump_values(mapping, stream=...)`，按明确的输入顺序导出，None 表示裸键、空字符串表示空赋值，使用本库格式而不宣称任意 Bash 语法兼容。序列化验证先完成，调用方文件对象不关闭；新路径写入走既有受控 rewrite 时保留错误清理。检查引号、反斜杠、多行、Unicode 和 `interpolate=False` 下读回等价。`tests/test_main.py`、`tests/test_parser.py`；依赖第 04 步有效键规则。
9. **模板**：CLI 增加 template，以原解析 Binding 保留注释／键并替换所有值；默认绝不保留原值，排除指定键和保留显式允许的非敏感值作为选项。多行值必须完整移除，不能残留后半段；拒绝将输出覆盖输入，输入严格失败时不生成半份模板。覆盖 key/value 里出现其他键名的文本，不能用全局字符串替换。`tests/test_cli.py`、`tests/test_parser.py`；可复用第 08 步输出但不把导出所有真实值当作模板。
10. **临时环境**：拟增加 dotenv_context，进入时记录它实际影响的键及旧值，离开恢复，支持异常退出和嵌套；保留未被此次加载触及的键。不是简单按当前文件中的 key 全部删除；默认 load_dotenv 的永久加载保持。明确 os.environ 是进程共享状态，本步不声称隔离其他线程并发写同一键。`tests/test_main.py`、`tests/test_ipython.py`。
11. **多文件层级**：CLI -f 支持多个有序文件，并提供对应 load_dotenv_files／dotenv_values_files 便捷入口；同键后文件覆盖前文件，--no-override 让原进程值优先。插值基于已加载的前层和当前层前项，文件缺失／解析失败在严格模式下不执行子进程、不修改环境。验证路径带空格、空文件、共享键与真实子进程 stdout；原单文件调用继续可用。`tests/test_cli.py`、`tests/test_main.py`；依赖第 06 步的严格失败契约。
12. **有界查找**：`find_dotenv` 拟接受 start_dir、stop_dir，二者显式时不走调用栈也不改进程 cwd；起点必须位于上界内，越界、上界不存在或路径类型不符拒绝。沿起点到上界含边界查找最近文件，保持默认无参数推断。以临时目录树内外各放不同的合成 .env 验证，不读取真实祖先配置；明确这只是查找边界，不是任意文件访问的系统沙箱。`tests/test_main.py`、`tests/test_is_interactive.py`、`tests/test_zip_imports.py`。
13. **选择性字面量**：拟在插值配置中新增 opt-in escape_dollar 模式，把 `$${B}` 解析为字面 `${B}`，同一文件的普通 `${B}` 正常展开；模式关闭时保持原行为。与全局 interpolate=False、引号、连续美元符和默认表达式的组合须定义，不能无条件把所有美元符删掉。`variables.py`、`parser.py`、`main.py`；`tests/test_variables.py`、`tests/test_main.py`。
14. **按键合并**：load 入口拟接受 merge 映射，指定键的 callable 收到旧值和新值并返回字符串／None 的明确结果，其他键按 override；先计算全部合并再一次应用，合并回调错误不留半更新。以 PATH 的去重追加为真实用例，路径分隔符用 os.pathsep；不修改全局 PATH 做研究，验收使用独立映射／合成键。`main.py:DotEnv.set_as_environment_variables`；`tests/test_main.py`。
15. **来源诊断**：拟提供 inspect_values，返回 key 的文件、原始行号、覆盖关系、解析状态和是否插值等元数据，默认不含实际值或原始行内容。复用既有 Binding 的 original.line，跨文件记录路径和最终胜出来源；普通返回映射类型不变。验证坏行、多行定义、重复键和 stream 的来源标签，诊断序列化不会暴露合成 secret 值。`main.py`、`parser.py`、`cli.py`；`tests/test_main.py`、`tests/test_cli.py`；与第 07／11 步组合回归。
16. **初始化缺失文件**：`load_dotenv` 拟加 init_dotenv_path，只有显式给出目标与模板、目标不存在时才创建，再走正常解析。使用排他创建或受控发布，目标在竞争中出现时保留它，不覆盖；模板缺失、目录不存在、权限错误和复制失败清楚报告。默认自动查找不在祖先目录写文件，不隐式执行模板内容；已存在目标和 PYTHON_DOTENV_DISABLED 不被修改。`tests/test_main.py`、`tests/test_cli.py`。
17. **百分号语法**：插值增加 opt-in percent 模式，解析 `%ROOT%`，默认 POSIX 模式继续保留原字符串；变量名查找区分大小写的策略显式沿当前 Mapping，不暗改所有平台键。一次展开即可，缺失值行为和字面 %% 明确；递归由下一步控制。覆盖 Windows 风格反斜杠路径，但测试不假装已在 Windows 上跑过。`variables.py`、`main.py`；`tests/test_variables.py`、`tests/test_main.py`。
18. **递归解析**：增加独立 opt-in recursive 模式，对已收集配置建立引用依赖，允许前向引用；设置最大深度／展开长度，循环引用报带键路径的错误且不改变环境。默认当前单遍顺序模式保持；混用百分号／POSIX 语法按第 17 步所选模式工作，普通缺失值与默认值按已定义语义。用链、菱形依赖、自循环、互循环、重复键胜出和环境优先级测试；不执行表达式或子命令。`variables.py`、`main.py:resolve_variables`；`tests/test_variables.py`、`tests/test_main.py`。
19. **字面文件引入**：增加 includes=False 的 opt-in，仅支持确定的 `source ./relative.env` 或 `. ./relative.env` 字面文件指令；不支持 shell 变量、通配符、管道或命令替换。相对路径按包含它的文件目录，统一到明确 root 范围，检测循环和最大深度；按出现顺序展开，相同文件重复引入的策略明确为允许且受深度／循环控制。缺失包含、越界、坏行严格失败且不改环境。`parser.py`、`main.py`；`tests/test_parser.py`、`tests/test_main.py`；依赖第 06、11、12 步的解析、层级和边界能力。
20. **陈旧编辑冲突**：拟对协作编辑增加 expected_digest 及同路径写锁，锁在读取旧文件前取得并保持到发布完成；摘要不符拒绝并保留当前文件。第一版限定本地 POSIX 文件系统的合作写入，明确非合作编辑器和网络文件系统不由此获得无条件一致性保证；只有检查摘要而没有覆盖读改写全程的锁不算完成。用受控进程／屏障证明两个不同键更新都保留、陈旧预期被拒绝、异常后锁释放，保留 set/unset 的权限／链接规则及第 05 步持久写入。`main.py:rewrite/set_key/unset_key`；`tests/test_main.py`、`tests/test_cli.py`。

## 组合回归与不计步内容

在同一真实仓库工作目录累计修改；每步检查当前能力和此前已接受能力，并保留检查点。第 05 步证明同步调用与失败边界，第 20 步证明协作写冲突，两者解决不同问题，不能把前者的原子替换误当成后者已解决。strict 与重复键策略为不同用户选择，既有默认行为分别保留。

按模块运行原生回归，跨共享解析／写入逻辑时运行适用完整集合；本轮隔离全套 288 项约三秒，保留原始权限、FIFO、IPython 和 CLI 测试。控制端冻结独立验收，实际读回文件字节、调用 CLI 子进程、核对候选加载路径和环境恢复，不能信任候选修改自己的 tests。

符号链接跟随、FIFO、BOM 和 dotenv 自身单引号／反斜杠往返在当前固定提交已存在，全部作为回归，不计新增步骤。未安排 Web UI、加密密钥管理、完整 Bash 解析、执行 `source` 命令、命令替换或云服务。重复键错误的多个测试、CLI 入口适配与失败重试不拆成额外步骤。

本轮 22 条原版观察为 4 个缺陷表现、16 个增强缺口、2 个通过对照。未演示断电故障，也未实施二十步；完整来源、命令、结构化路线及失败／通过证据见单仓审查。
