# Dynaconf：二十步真实工程迭代路线

固定 [dynaconf/dynaconf@32f38478350a80020e7aab60a3cbd29dd7f8d9ea](https://github.com/dynaconf/dynaconf/tree/32f38478350a80020e7aab60a3cbd29dd7f8d9ea)，原生证据见 [单仓审查](./dynaconf.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．文件加载拒绝不合法的路径参数

- **类型与来源**：修复；[官方#1299](https://github.com/dynaconf/dynaconf/issues/1299)；固定源码/原版观察。
- **原版现状与收益**：load_file(module_object,silent=False)实测静默None，str转换把任意对象伪装为glob。
- **交付及模块**：规范只接str/PathLike及其有限序列，非法输入在任何silent模式下TypeError，缺文件与坏输入分开；base.Settings.load_file、utils.ensure_a_list、py_loader探测入口。
- **兼容与依赖**：保留字符串模块名/glob/PathLike；silent仍只影响可省略文件/加载错误，不吞程序参数类型错；步骤依赖：无。
- **正常验收**：str和PathLike真实文件加载一致，module/dict/数字输入明确拒绝。
- **异常／边界验收**：混合序列中坏项先整体验证、空列表、坏fspath返回类型、glob无结果和strict缺env节。
- **原生回归**：tests/test_base.py、tests/test_loaders.py、tests/test_py_loader.py。

## 02．条件Validator不记住其他实例的环境

- **类型与来源**：修复；Settings/Validator真实定义与本地配置使用场景；固定源码/原版观察。
- **原版现状与收益**：Validator.validate把self.when.envs从None改为首个dev；复用到prod后错误检查dev条件，让prod负port通过。
- **交付及模块**：把继承env仅作为本次求值上下文传递，不持久改写共享Validator/when；validator.Validator.validate／when执行、from_env协作。
- **兼容与依赖**：显式when.envs仍尊重；同一描述器可跨实例使用，不能靠深拷贝任意用户callable解决；步骤依赖：无。
- **正常验收**：dev条件False跳过后，prod条件True且port=-1必须拒绝，新/复用validator结果一致。
- **异常／边界验收**：多层when、or/and共享子validator、并发实例、显式不同env和only_current_env。
- **原生回归**：tests/test_validators.py、tests/test_base.py。

## 03．update不修改调用者的输入字典

- **类型与来源**：修复；Settings/Validator真实定义与本地配置使用场景；固定源码/原版观察。
- **原版现状与收益**：Settings.update执行data.update(kwargs)，原data从EXISTING变成含OTHER；函数未表达接管输入所有权。
- **交付及模块**：先创建顶层输入映射快照合并kwargs，再解析/校验；保留调用者原mapping；base.Settings.update。
- **兼容与依赖**：保持kwargs覆盖同名data的优先；只承诺顶层不写入，不擅自深拷贝不能复制的用户对象；步骤依赖：无。
- **正常验收**：传data与OTHER参数更新settings成功，原data字典完全不变。
- **异常／边界验收**：只读Mapping、空mapping、同key冲突、解析/校验失败和共享nested对象归属说明。
- **原生回归**：tests/test_base.py。

## 04．明确可变配置引用与快照读取

- **类型与来源**：增强；[官方#1209](https://github.com/dynaconf/dynaconf/issues/1209)；固定源码/原版观察。
- **原版现状与收益**：recursively_evaluate_lazy_format每次重建list，取出nested list append3后重读仍[1,2]；该复制有旧validator兼容背景。
- **交付及模块**：增加显式live view/稳定引用模式，并保留snapshot读取，惰性子项按约定一次/每读求值；utils.recursively_evaluate_lazy_format、utils.boxing.DynaBox、Settings读取profile。
- **兼容与依赖**：默认旧复制行为可保留；不能全局就地求值导致raw插值丢失，和readonly字段策略一致；步骤依赖：无。
- **正常验收**：live模式append真实保留，snapshot模式改动不影响配置，已有格式lazy值仍正确。
- **异常／边界验收**：循环list、BoxList保留类型、nested map/list、getter重复调用和校验读副作用。
- **原生回归**：tests/test_dynabox.py、tests/test_base.py、tests/test_utils.py。

## 05．验证失败可以原子回滚一批更新

- **类型与来源**：增强；Settings/Validator真实定义与本地配置使用场景；固定源码/原版观察。
- **原版现状与收益**：set/update先写store/_defaults/metadata再校验；错误后缺统一回滚契约。
- **交付及模块**：新增opt-in transaction update，临时求值完整变更，验证通过后一次提交管理器状态；base.Settings.set／update、validator执行、来源历史。
- **兼容与依赖**：普通update行为保持；不能撤销用户validator任意外部副作用，只保证拥有的配置/历史一致；步骤依赖：02、03。
- **正常验收**：两个字段一起改能满足跨字段约束，失败则旧值/defaults/inspect历史都保留。
- **异常／边界验收**：lazy错误、merge原地变更、nested视图旧引用、validator默认注入、递归更新拒绝或明确定义。
- **原生回归**：tests/test_base.py、tests/test_validators.py、tests/test_inspect.py。

## 06．按配置路径选择合并策略

- **类型与来源**：增强；[官方#999](https://github.com/dynaconf/dynaconf/issues/999)；固定源码/原版观察。
- **原版现状与收益**：全局merge_enabled会连list叶一起拼接；用户无法声明只合并map分支而替换某条list。
- **交付及模块**：提供路径级merge/replace/unique策略，应用到文件/env/set/load_file一致路径；utils.object_merge、Settings._merge_before_set、loaders.BaseLoader。
- **兼容与依赖**：默认历史merge保持；已修的unique顺序不另算BUG，冲突路径优先级明确；步骤依赖：05。
- **正常验收**：nested map保留兄弟键，同时servers列表可按路径选择整体replace。
- **异常／边界验收**：大小写路径、list索引、None、@merge/@reset显式token与路径策略冲突。
- **原生回归**：tests/test_utils.py、tests/test_base.py、tests/test_loaders.py。

## 07．插值只暴露指定环境变量集合

- **类型与来源**：增强；[官方#1373](https://github.com/dynaconf/dynaconf/issues/1373)；固定源码/原版观察。
- **原版现状与收益**：@format/@jinja等可接触环境，现有prefix控制载入但不能表达插值env的逐名允许映射。
- **交付及模块**：新增显式interpolation env mapping/allowlist，只提供配置声明的环境值和别名；utils.parse_conf.Formatters／Lazy、Settings插值profile。
- **兼容与依赖**：默认兼容模式保持；不把文件env前缀与插值变量权限混同，不引入外部secret后端；步骤依赖：无。
- **正常验收**：只声明FOOBAR的插值可用，未声明变量给明确缺值错误/默认策略。
- **异常／边界验收**：嵌套lazy链、jinja与format/get一致、同名别名、空值和初始化后环境变化策略。
- **原生回归**：tests/test_base.py、tests/test_utils.py。

## 08．无扩展名配置文件指定加载格式

- **类型与来源**：增强；[官方#1289](https://github.com/dynaconf/dynaconf/issues/1289)；固定源码/原版观察。
- **原版现状与收益**：settings_loader按扩展名匹配；CI临时文件无.yml时无法直接指定YAML读取。
- **交付及模块**：增加显式format/loader选择，可为单文件或结构化source声明，保留source metadata；loaders.settings_loader、BaseLoader、Settings.load_file。
- **兼容与依赖**：默认扩展名发现保持；只允许已注册loader，不能按用户数据任意import代码；步骤依赖：01。
- **正常验收**：无扩展临时文件以format=yaml加载与.yml同内容一致。
- **异常／边界验收**：未知format、内容语法错、format与扩展名冲突、glob多文件和loader缺依赖。
- **原生回归**：tests/test_settings_loader.py、tests/test_yaml_loader.py。

## 09．环境值解析器可按实例替换

- **类型与来源**：增强；[官方#1216](https://github.com/dynaconf/dynaconf/issues/1216)；固定源码/原版观察。
- **原版现状与收益**：parse_conf_data默认TOML推断并有auto_cast，但没有每实例自定义标量解析函数的稳定协议。
- **交付及模块**：增加实例级value parser profile，允许TOML/JSON/literal/调用者parser选择并保留显式@token优先；utils.parse_conf.parse_conf_data、env_loader、Settings解析配置。
- **兼容与依赖**：不是已有auto_cast=False的改名；默认TOML保持，parser不全局污染其他实例，失败策略明确；步骤依赖：无。
- **正常验收**：JSON profile将true/数组解析正确，另一个默认实例行为独立。
- **异常／边界验收**：非法JSON、空字符串、None、@str/@int/@merge、嵌套env和解析器抛错。
- **原生回归**：tests/test_env_loader.py、tests/test_utils.py。

## 10．敏感值类型贯穿输出与错误遮蔽

- **类型与来源**：增强；[官方#1152](https://github.com/dynaconf/dynaconf/issues/1152)；固定源码/原版观察。
- **原版现状与收益**：is_secret参数已标弃用，核心无统一Secret包装类型；普通inspect/CLI无法按值类型保留隐藏语义。
- **交付及模块**：新增Secret值包装与显式reveal，repr/CLI/inspect/ValidationError默认只显示遮蔽文本；typed类型、parse_conf converters、utils.inspect、cli、validator错误输出。
- **兼容与依赖**：不重复现有Vault/Redis loader，不发网络请求；序列化/比较与显式reveal边界确定，不记录真实值进历史再遮表面；步骤依赖：无。
- **正常验收**：合成Secret正常参与显式取值，list/inspect/校验错误不输出原字符串。
- **异常／边界验收**：nested容器、alias、lazy、日志repr、空secret、数据dump显式授权模式与copy。
- **原生回归**：tests/test_inspect.py、tests/test_cli.py、tests/test_validators.py。

## 11．加载完成后的只读字段

- **类型与来源**：增强；[官方#1219](https://github.com/dynaconf/dynaconf/issues/1219)、[官方#1136](https://github.com/dynaconf/dynaconf/issues/1136)；固定源码/原版观察。
- **原版现状与收益**：typed不识别Immutable，set/update/属性赋值/reload都可改变字段。
- **交付及模块**：提供初始化完成锁定的readonly字段声明，统一拦截所有写入入口和reload策略；typed元信息、Settings.set／unset／update／reload、属性/下标入口。
- **兼容与依赖**：首次正常来源优先合成后才锁，不在第一默认值时误锁；默认字段仍可变，deep readonly策略显式；步骤依赖：04、05。
- **正常验收**：default→file→env完成后字段锁定，后续set与属性写都同样拒绝。
- **异常／边界验收**：nested live view、批量含只读字段回滚、reload跳过/报错选项、alias绕过和删除。
- **原生回归**：tests/test_typed.py、tests/test_base.py。

## 12．复合tuple和Any的typed验证

- **类型与来源**：增强；[官方#1133](https://github.com/dynaconf/dynaconf/issues/1133)、[官方#1134](https://github.com/dynaconf/dynaconf/issues/1134)；固定源码/原版观察。
- **原版现状与收益**：tuple[int,str]实测SchemaError，Any也unsupported；参数化类型支持不完整。
- **交付及模块**：统一扩展typing解析/递归检查，支持定长/变长tuple及Any作为不限制值的节点；typed.guards／utils／main、validator_conditions.is_type_of。
- **兼容与依赖**：不把非法list[T,T]原生xfail当合法；tuple保持tuple，不把Any等同自动字符串转换；步骤依赖：无。
- **正常验收**：tuple[int,str]和tuple[int,...]正确校验，嵌套dict[str,Any]保留任意值。
- **异常／边界验收**：元组长度错、Union/Optional、Annotated附加validator、空元组与深层错误路径。
- **原生回归**：tests/test_typed.py、tests/test_validators_conditions.py。

## 13．typed字段声明多个输入别名

- **类型与来源**：增强；[官方#1137](https://github.com/dynaconf/dynaconf/issues/1137)；固定源码/原版观察。
- **原版现状与收益**：typed注解只按字段名匹配，缺Alias元数据；大小写兼容不能替代显式不同业务名。
- **交付及模块**：增加Alias标记并在每source载入时规范到schema字段，保留获胜来源说明；typed元信息、loaders赋值规范化、Settings dotted setter。
- **兼容与依赖**：默认字段名仍有效；同source多别名按明确声明/输入优先级决定，不能偶然字典遍历决定；步骤依赖：11。
- **正常验收**：identification与name都喂同name字段，跨source仍按原来源优先。
- **异常／边界验收**：重复alias指向多个字段、nested key、大小写、env prefix、readonly和未知字段策略。
- **原生回归**：tests/test_typed.py、tests/test_env_loader.py、tests/test_inspect.py。

## 14．日期时间字段的明确格式转换

- **类型与来源**：增强；[官方#1148](https://github.com/dynaconf/dynaconf/issues/1148)；固定源码/原版观察。
- **原版现状与收益**：typed SUPPORTED_TYPES无datetime；cast可自写函数但缺格式/时区/错误路径的声明式契约。
- **交付及模块**：增加date/datetime/time类型支持及显式Format注解，统一源字符串转换；typed.types／guards／main、validator转换管线。
- **兼容与依赖**：不靠机器locale猜日期，不把naive时间偷偷赋本地时区；现有普通字符串保持；步骤依赖：无。
- **正常验收**：ISO或明确%Y-%m-%d字符串转换到对应类型，typed错误显示字段路径。
- **异常／边界验收**：无效日期、闰日、时区偏移、DST歧义策略、已有datetime值及不同来源一致。
- **原生回归**：tests/test_typed.py、tests/test_validators.py。

## 15．字段首次访问才执行默认工厂

- **类型与来源**：增强；[官方#1147](https://github.com/dynaconf/dynaconf/issues/1147)；固定源码/原版观察。
- **原版现状与收益**：Validator.default已支持callable，但在校验取默认时执行；无typed首访工厂与每实例缓存声明。
- **交付及模块**：新增Factory元数据，按实例/字段首次需要时求值并定义缓存/失效策略；typed元信息、Settings lazy取值、validator默认协作。
- **兼容与依赖**：不把既有callable default再当新功能；预验证不得提前执行所有工厂，自引用给可定位循环错误；步骤依赖：11。
- **正常验收**：未读取字段时工厂计数0，首次读1，同实例再读按缓存契约，另一实例独立。
- **异常／边界验收**：并发首访、工厂异常重试、readonly字段、reload失效、返回mutable值不能跨实例共享。
- **原生回归**：tests/test_typed.py、tests/test_validators.py。

## 16．校验失败的显式恢复默认策略

- **类型与来源**：增强；[官方#1146](https://github.com/dynaconf/dynaconf/issues/1146)；固定源码/原版观察。
- **原版现状与收益**：apply_default_on_none只针对缺失/None，条件错误时仍抛ValidationError；无逐字段OnFailure恢复策略。
- **交付及模块**：新增OnFailure声明可选择报错/记录诊断并用经验证的默认值，保留恢复事件来源；validator失败路径、typed元信息、加载历史。
- **兼容与依赖**：默认继续抛错；不把任何空串自动当None，不吞系统异常，默认值本身失败不能递归重试；步骤依赖：05、10。
- **正常验收**：错误类型字段按指定策略回默认，其他字段正常，诊断列原失败与恢复原因。
- **异常／边界验收**：无默认、恢复默认仍不合法、Secret错误遮蔽、跨字段约束、only/exclude和批量回滚。
- **原生回归**：tests/test_validators.py、tests/test_inspect.py。

## 17．typed额外字段允许忽略或拒绝

- **类型与来源**：增强；[官方#1135](https://github.com/dynaconf/dynaconf/issues/1135)；固定源码/原版观察。
- **原版现状与收益**：TypedExtra(name=ok,extra=present)保留EXTRA，Options只有有限参数，缺extra策略。
- **交付及模块**：新增allow/ignore/forbid策略，按完整schema路径检查来自所有source的额外字段；typed.Options／main、loaders赋值、Settings更新验证。
- **兼容与依赖**：默认allow保持；Dynaconf内部配置键不被误判用户字段，不只在__init__过滤一次；步骤依赖：13。
- **正常验收**：forbid报告拼错字段与来源，ignore确实不在读取/inspect输出中，allow保持。
- **异常／边界验收**：nested DictValue、dict自由key、aliases、env内部选项、load_file/set/update后仍一致。
- **原生回归**：tests/test_typed.py、tests/test_base.py。

## 18．从运行配置推导可复核typed schema

- **类型与来源**：增强；[官方#1141](https://github.com/dynaconf/dynaconf/issues/1141)；固定源码/原版观察。
- **原版现状与收益**：inspect已有值/来源历史，ValidatorList有descriptions，但没有生成typed schema入口。
- **交付及模块**：新增generate-schema，提取运行值形状/默认/可表达validators并标注不能推断部分；cli新生成命令、typed schema emitter、Validator元数据。
- **兼容与依赖**：推导是草稿，不假装从当前值证明所有合法类型；Secret默认不写入生成文件，不执行输出代码验证自己成功；步骤依赖：10、12。
- **正常验收**：包含嵌套dict/list的配置生成可读schema，明确当前样本和validator约束。
- **异常／边界验收**：空/混合列表、None、动态字段、不可导出callable validator、非法Python标识符与敏感值。
- **原生回归**：tests/test_cli.py、tests/test_typed.py。

## 19．从typed schema生成带说明的示例配置

- **类型与来源**：增强；[官方#1140](https://github.com/dynaconf/dynaconf/issues/1140)、[官方#1272](https://github.com/dynaconf/dynaconf/issues/1272)；固定源码/原版观察。
- **原版现状与收益**：CLI init/write可人工写值，缺按schema的required/default/description自动生成样例。
- **交付及模块**：新增generate-settings输出YAML/TOML样例，展示字段说明/类型/约束与可编辑必填占位；cli、typed schema读取、现有文件writers。
- **兼容与依赖**：与运行值推导schema是不同输入/用途；不自动覆盖现有配置，不将占位内容声称已通过校验；步骤依赖：10。
- **正常验收**：schema含Database嵌套和默认port时样例层级/默认正确，必填字段明确待填。
- **异常／边界验收**：Secret隐藏、无source可取的类、Optional/NotRequired、格式不支持的数据类型与字段排序。
- **原生回归**：tests/test_cli.py、tests/test_typed.py。

## 20．CLI按模式筛选多个配置键

- **类型与来源**：增强；[官方#1218](https://github.com/dynaconf/dynaconf/issues/1218)；固定源码/原版观察。
- **原版现状与收益**：list/inspect的--key只精确单key/路径，无法一次查看一组DB_*配置。
- **交付及模块**：增加显式--glob/--regex多key选择，共用同一选择器覆盖list/inspect及机器格式输出；cli._list／inspect、utils.inspect查询层。
- **兼容与依赖**：默认--key保持精确，regex/glob不是隐式解释原key，不丢加载历史和Secret遮蔽；步骤依赖：10。
- **正常验收**：DB_*同时输出多个匹配key，JSON格式仍有效且顺序稳定。
- **异常／边界验收**：无匹配、非法/昂贵regex受控预算、nested路径、Unicode、内部字段隐藏和格式输出一致。
- **原生回归**：tests/test_cli.py、tests/test_inspect.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
