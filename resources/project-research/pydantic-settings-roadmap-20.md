# Pydantic Settings：二十步真实工程迭代路线

固定 [pydantic/pydantic-settings@8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930](https://github.com/pydantic/pydantic-settings/tree/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930)，见[单仓审查](./pydantic-settings.md)。7项原版复现修复与13项增强，全部未实施。新API名是拟议契约。

已有来源定制/优先级、JSON/YAML/TOML及构造器路径覆盖、CLI子命令/UnknownArgs/serialize/help、strict环境转换、cache/clear、debug日志、普通别名合并均排除新增。本路线只处理本地文件、环境、纯本地CLI和普通配置维护。

## 01．字典联合值的嵌套环境JSON解码

- **类型与场景**：复现修复提案；本地商品配置的dict值既可能是字符串也可能是字符串列表。
- **原版证据**：APP_CONFIG__ITEM=[]被读取成字符串[]；dict值是原始Union注解时只检查_annotation_is_complex，没有走联合复杂分支。
- **交付目标**：对字典值联合注解采用与普通Union字段一致的复杂性/允许失败判断，合法JSON列表解码，普通str仍可保留。
- **真实模块**：pydantic_settings/sources/providers/env.py、pydantic_settings/sources/utils.py。
- **兼容边界**：保持str分支输入与NoDecode/ForceDecode、enable_decoding设置，不把所有文本强行JSON解析。
- **正常验收**：dict[str,list[str]|str]的[]变空列表，hello仍字符串，嵌套多项不互相覆盖。
- **边界验收**：非法JSON、None、Annotated/别名、字典多层、列表元素错误、严格类型和空值策略回归。
- **原生回归**：tests/test_settings.py。
- **实际依赖**：无；已有typing-inspection/Pydantic解码。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/1088)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/env.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/utils.py)。

## 02．CLI前缀和禁别名验证的字段匹配

- **类型与场景**：复现修复提案；商品工具命令以app前缀运行，字段定义有外部alias但本次只按字段名验证。
- **原版证据**：--app.apple x被忽略，apple仍default，普通--app.plain y正确；validate_by_alias=False组合失配。
- **交付目标**：统一CLI生成名、prefix移除和init字段名还原，遵循实际validate_by_name/alias策略。
- **真实模块**：pydantic_settings/sources/providers/cli.py、pydantic_settings/main.py、pydantic_settings/sources/utils.py。
- **兼容边界**：默认alias与现prefix规则保持；不接受被配置禁用的alias，不能靠同时开启所有别名绕过。
- **正常验收**：该样本apple=x/plain=y，无prefix与合法alias模式仍正确。
- **边界验收**：嵌套prefix、AliasChoices/Path、kebab_case、短参数、同名覆盖和init/env优先级回归。
- **原生回归**：tests/test_source_cli.py、tests/test_precedence_and_merging.py。
- **实际依赖**：无；现有argparse和字段元数据。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/1064)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/cli.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)；[来源4](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/utils.py)。

## 03．CLI集合容器的可逆序列化

- **类型与场景**：复现修复提案；配置对象的frozenset/deque被序列化为argv后需重新解析同值。
- **原版证据**：frozenset与deque写成Python repr，第二次解析后元素为repr片段，first!=second。
- **交付目标**：将受支持集合容器转成JSON兼容序列后按CLI列表约定编码，保留容器类型由模型校验恢复。
- **真实模块**：pydantic_settings/sources/providers/cli.py。
- **兼容边界**：已有list/dict/set/tuple与枚举/日期/Decimal编码保持；frozenset顺序不作为稳定业务顺序。
- **正常验收**：frozenset{x}和deque[x,y]序列化再运行后与原对象相等，队列顺序保留。
- **边界验收**：空容器、嵌套容器、Unicode/逗号、枚举元素、NoDecode、positionals及list_style适用范围回归。
- **原生回归**：tests/test_source_cli.py。
- **实际依赖**：无；已有pydantic_core.to_jsonable_python与JSON。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/1063)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/cli.py)。

## 04．显式pyproject路径的用户目录展开

- **类型与场景**：复现修复提案；本地工具明确指定~/pyproject.toml作为项目配置。
- **原版证据**：合成HOME下文件存在，但选定路径仍含字面~，读取回fallback；_pick_pyproject_toml_file直接resolve。
- **交付目标**：显式路径先expanduser再resolve，保持自动向上查找逻辑及路径不存在时已有策略。
- **真实模块**：pydantic_settings/sources/providers/pyproject.py。
- **兼容边界**：不新增任意路径搜索或更改cwd；普通绝对/相对Path保持，未知用户展开失败清楚。
- **正常验收**：~/pyproject.toml读到loaded，与指向同文件的绝对Path结果一致。
- **边界验收**：Unicode HOME、~user、相对路径、缺文件、depth边界、表头tuple和Traversable支持范围回归。
- **原生回归**：tests/test_source_pyproject_toml.py。
- **实际依赖**：无；标准库Path。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/1053)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/pyproject.py)。

## 05．未知CLI参数保留原命令层级

- **类型与场景**：复现修复提案；本地包装命令把父命令和子命令各自的未知参数交还上层处理。
- **原版证据**：原父unknown=[--parent-extra]、子unknown=[--child-extra]，serialize把两者都放sub后，回读父为空、子吸收两项。
- **交付目标**：序列化保留每层unknown片段相对subcommand的位置，不把各层统一挪到最后。
- **真实模块**：pydantic_settings/sources/providers/cli.py。
- **兼容边界**：既有CliUnknownArgs捕获和位置参数排序保持；不能默默丢unknown或把已知参数改归属。
- **正常验收**：序列化回读后父/子unknown分别原样，已知字段仍正确。
- **边界验收**：多层子命令、--分隔、重复未知选项、未知位置值、空unknown、未选择子命令和positionals_first回归。
- **原生回归**：tests/test_source_cli.py。
- **实际依赖**：无；已有argv结构。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/1048)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/cli.py)。

## 06．TypeAliasType包裹模型的嵌套解析

- **类型与场景**：复现修复提案；组件配置类型通过命名别名包含可选嵌套模型和列表。
- **原版证据**：child__values=[1,2]进入MaybeInner=Inner|None后仍str，ValidationError child.values不是list。
- **交付目标**：递归解析TypeAliasType/Annotated/Union的实际字段结构，再按真实子字段类型解码分段值。
- **真实模块**：pydantic_settings/sources/providers/env.py、pydantic_settings/sources/utils.py。
- **兼容边界**：命名别名本身保持，不无限展开递归类型；已有普通模型/Union和strict规则一致。
- **正常验收**：MaybeInner下values得到[1,2]，None与整个JSON对象两种输入仍可用。
- **边界验收**：多层别名、递归别名、泛型参数、AliasPath、同名字段、非法列表和max_split回归。
- **原生回归**：tests/test_settings.py、tests/test_utils.py。
- **实际依赖**：已有typing-inspection/Pydantic注解工具；无新运行库。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/1047)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/env.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/utils.py)。

## 07．按字段选择来源列表合并策略

- **类型与场景**：增强提案；本地配置文件提供基础插件列表，环境只想追加本次插件。
- **原版证据**：高优先级tags=[local]完全替换低优先级[base]；该替换符合当前deep_update。旧issue923别名合并样例已实测正确，排除修复。
- **交付目标**：新增显式逐字段列表合并策略replace/append/unique及受限定的keyed-record模式，记录确定顺序与冲突处理。
- **真实模块**：pydantic_settings/main.py、pydantic_settings/sources/base.py。
- **兼容边界**：默认replace保持；只对声明字段生效，不改变普通dict深合并或误把CLI重复flags等同多来源合并。
- **正常验收**：append得base/local，unique去重复保序，未声明仍只有local，来源优先级可说明。
- **边界验收**：空列表、None、重复key、不同元素类型、嵌套列表、来源错误和可变输入所有权回归。
- **原生回归**：tests/test_precedence_and_merging.py、tests/test_settings.py。
- **实际依赖**：无；标准库合并器；类型校验仍由Pydantic。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/505)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/base.py)。

## 08．CLI局部更新保留真实fields_set

- **类型与场景**：复现修复提案；本地配置补丁只提交nested.a，导出exclude_unset不能误带默认b。
- **原版证据**：--nested.a changed后nested.model_fields_set却含a/b，exclude_unset也带b=42；开启nested_model_default_partial_update。
- **交付目标**：保留默认嵌套对象的值用于partial merge，同时单独跟踪实际显式字段并还原正确fields_set。
- **真实模块**：pydantic_settings/main.py、pydantic_settings/sources/base.py、pydantic_settings/sources/providers/cli.py。
- **兼容边界**：默认b值仍42，修的是显式来源标记而非删默认值；不把CLI旧顶层修复自动视为嵌套已修。
- **正常验收**：实际值a=changed/b=42，fields_set只有a，exclude_unset只含a。
- **边界验收**：多层嵌套、init/env/CLI混用、显式传默认值、model/dataclass默认、列表对象和重复加载回归。
- **原生回归**：tests/test_source_cli.py、tests/test_precedence_and_merging.py。
- **实际依赖**：无；已有Pydantic字段集合语义。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/851)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/base.py)；[来源4](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/cli.py)。

## 09．显式且成对的CLI值编解码协议

- **类型与场景**：增强提案；配置字段的命令行表示与业务值不同，需要可逆的格式规则。
- **原版证据**：PlainSerializer把x=2的JSON显示成4，但CliApp.serialize仍发-x 2；直接套显示serializer可能破坏重建语义。
- **交付目标**：新增opt-in字段CLI codec，分别声明serialize与parse，默认继续原始业务值；可明确选择只用于展示的Pydantic serializer。
- **真实模块**：pydantic_settings/sources/providers/cli.py、pydantic_settings/sources/types.py、pydantic_settings/main.py。
- **兼容边界**：不盲目将PlainSerializer作为可逆CLI格式；model_dump显示和CLI输入默认保持分离。
- **正常验收**：quantity可编码为qty:2并由配对parser恢复2，默认数值字段argv行为不变。
- **边界验收**：只有单向serializer、无效编码、None、集合元素、AliasPath、子命令和codec异常回归。
- **原生回归**：tests/test_source_cli.py。
- **实际依赖**：无；本地callable协议；不需要另一个CLI框架。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/754)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/cli.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/types.py)；[来源4](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)。

## 10．字段允许来源与模型常量策略

- **类型与场景**：增强提案；商品工具某些构建标识由init固定，其他字段仍可读环境或文件。
- **原版证据**：普通title=fixed仍被APP_TITLE覆盖，无settings_sources选项；来源只能整体定制或手工过滤。
- **交付目标**：新增字段级source allow/deny或constant策略，在来源收集时按规范字段身份过滤，支持继承覆盖规则。
- **真实模块**：pydantic_settings/sources/base.py、pydantic_settings/sources/types.py、pydantic_settings/main.py。
- **兼容边界**：普通字段默认继续全部标准来源；ClassVar和Pydantic frozen/Final既有语义不等同来源控制。
- **正常验收**：指定init-only字段忽略env/file/CLI覆盖，但允许显式init，其他字段正常合并。
- **边界验收**：别名、多层字段、未知自定义source名、默认值、必填缺失、source类别继承与模板说明回归。
- **原生回归**：tests/test_settings.py、tests/test_precedence_and_merging.py。
- **实际依赖**：无；字段metadata和来源身份；不涉及账号或远程权限。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/521)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/base.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/types.py)；[来源4](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)。

## 11．环境分段索引构造模型列表

- **类型与场景**：增强提案；本地部署配置通过ITEMS__0__SKU表达少量商品行。
- **原版证据**：目前爆炸成{0:{sku:咖啡}}字典，list[Item]校验失败；整体JSON列表已支持。
- **交付目标**：新增opt-in索引列表展开，按真实目标list注解识别数字片段，定义稀疏索引和整JSON与分段项合并。
- **真实模块**：pydantic_settings/sources/providers/env.py、pydantic_settings/sources/utils.py。
- **兼容边界**：默认dict数字key不变；不能把所有数字字段名猜成数组，保留整体JSON替代。
- **正常验收**：两个连续索引生成两Item，嵌套list模型校验正确，dict[str,Item]仍是字典。
- **边界验收**：负/超大索引、空洞、重复项、混合str/int键、max_split、AliasPath和整体列表冲突回归。
- **原生回归**：tests/test_settings.py。
- **实际依赖**：无；标准库容器与现字段注解。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/376)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/env.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/utils.py)。

## 12．校验错误关联实际环境输入名

- **类型与场景**：增强提案；本地配置写错APP_QUANTITY时希望错误同时指出对应物理变量。
- **原版证据**：ValidationError.loc只有quantity，渲染不含APP_QUANTITY；复杂源解码也主要按模型字段报错。
- **交付目标**：新增可选结构化input-origin信息，把错误字段路径关联来源/物理env键或文件位置；保留Pydantic原loc和错误类型。
- **真实模块**：pydantic_settings/main.py、pydantic_settings/sources/base.py、pydantic_settings/sources/providers/env.py、pydantic_settings/exceptions.py。
- **兼容边界**：默认错误结构兼容；不将字段名替换成不可用于模型定位的env字符串，不默认转储所有值。
- **正常验收**：非法APP_QUANTITY错误保留loc并附该实际键；别名输入显示被实际使用的键。
- **边界验收**：嵌套多键参与一个值、初始化来源、文件无行号、非法JSON、大小写折叠和多个错误回归。
- **原生回归**：tests/test_settings.py、tests/test_precedence_and_merging.py。
- **实际依赖**：无；来源元数据；可独立于步骤18成功字段解释。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/24)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/base.py)；[来源4](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/env.py)；[来源5](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/exceptions.py)。

## 13．实例级本地文件源选项

- **类型与场景**：增强提案；同一配置类在两个本地项目读取各自JSON/YAML/TOML，无须改全局model_config。
- **原版证据**：YamlConfigSettingsSource构造器yaml_file覆盖已成功，BaseSettings(_yaml_file=path)却被extra_forbidden；_env_file已支持。
- **交付目标**：新增统一实例source-options/context，将明确的本地文件路径/section/encoding传到已选文件源，保持类配置只读。
- **真实模块**：pydantic_settings/main.py、pydantic_settings/sources/providers/json.py、pydantic_settings/sources/providers/yaml.py、pydantic_settings/sources/providers/toml.py。
- **兼容边界**：不是新增文件源构造参数、deep_merge或_env_file；显式选入文件源的机制仍可定制，不自动启用所有文件。
- **正常验收**：同类两个实例分别读A/B文件且互不污染，未传opts仍用原model_config路径。
- **边界验收**：None禁用、路径序列、显式source优先、section空值、未知选项、并发实例和缺文件策略回归。
- **原生回归**：tests/test_source_yaml.py、tests/test_source_toml.py、tests/test_source_json.py。
- **实际依赖**：JSON/TOML标准库，YAML沿用现PyYAML可选依赖。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/259)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/json.py)；[来源4](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/yaml.py)；[来源5](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/toml.py)。

## 14．可编辑的本地配置模板

- **类型与场景**：增强提案；商品工具初始化时生成可读的.env或TOML样例，附字段说明。
- **原版证据**：只有Pydantic JSON Schema和CLI help等既有描述，无settings_template入口。
- **交付目标**：新增离线模板生成，按真实alias/prefix/嵌套规则输出受支持格式，标注必填/默认/说明和无法静态表达的字段。
- **真实模块**：pydantic_settings/main.py、pydantic_settings/sources/utils.py。
- **兼容边界**：JSON Schema和help不变；不执行default_factory猜值，不把占位符当可直接通过校验的有效配置。
- **正常验收**：title/quantity模板能按说明填值并由同类重新加载，env名与实际加载完全一致。
- **边界验收**：None、复杂模型、Union、特殊字符、别名冲突、动态默认、排除字段与格式不支持时明确标记。
- **原生回归**：tests/test_settings.py、tests/test_source_toml.py、tests/test_docs.py。
- **实际依赖**：无；标准库可先覆盖.env/TOML文本；其他格式按现可选依赖。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/287)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/utils.py)。

## 15．嵌套组件的全局环境别名

- **类型与场景**：增强提案；复用组件在不同父路径下仍可读取同一个SHARED_QUANTITY环境键。
- **原版证据**：未显式拼接父路径时SHARED_QUANTITY不影响widget.quantity，仍1；无env_global_aliases策略。
- **交付目标**：新增显式全局env别名metadata，区分相对别名与根环境键，定义与局部嵌套/整体JSON的优先级。
- **真实模块**：pydantic_settings/sources/providers/env.py、pydantic_settings/sources/base.py、pydantic_settings/sources/types.py。
- **兼容边界**：现validation_alias/AliasPath的相对路径语义保持；不自动把嵌套所有alias全局化。
- **正常验收**：同一组件挂在两个父字段时可按声明共享键，局部override按明确规则只改一个实例。
- **边界验收**：循环模型、多别名、env_prefix、case_sensitive、整体JSON、冲突键、缺值和重复组件回归。
- **原生回归**：tests/test_settings.py、tests/test_precedence_and_merging.py。
- **实际依赖**：无；现环境映射和字段metadata。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/714)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/env.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/base.py)；[来源4](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/types.py)。

## 16．CLI嵌套分隔符配置

- **类型与场景**：增强提案；本地脚本使用--nested__a而不是默认点号表达嵌套配置。
- **原版证据**：CliSettingsSource(cli_nested_delimiter=__)TypeError；env_nested_delimiter存在但CLI使用自己的点号层级。
- **交付目标**：新增明确CLI delimiter选项并统一parser生成、帮助、解析和serialize的分隔规则。
- **真实模块**：pydantic_settings/sources/providers/cli.py、pydantic_settings/main.py。
- **兼容边界**：默认点号保持；不复用env选项导致原CLI静默变名，prefix与真实字段名的转义规则明确。
- **正常验收**：指定__时--nested__a可解析并serialize回同一参数，默认CLI仍用点号。
- **边界验收**：delimiter为空/多字符、字段名含分隔符、cli_prefix、AliasPath、kebab_case、子命令和shortcut回归。
- **原生回归**：tests/test_source_cli.py。
- **实际依赖**：无；argparse和字段命名逻辑。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/650)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/cli.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)。

## 17．离线命令行补全描述

- **类型与场景**：增强提案；商品工具希望终端补全已知flag、子命令和有限枚举值。
- **原版证据**：CliApp无complete入口，format_help已存在，不能将帮助生成再当新增。
- **交付目标**：新增纯元数据completion接口及受支持shell脚本导出，按当前argv上下文列候选，不执行cli_cmd业务方法。
- **真实模块**：pydantic_settings/main.py、pydantic_settings/sources/providers/cli.py。
- **兼容边界**：原解析和help输出不变；动态候选需调用方明确回调，默认仅静态schema信息。
- **正常验收**：在--前缀补全flag，在枚举参数后补全合法项，进入子命令只列该层选项。
- **边界验收**：引号/空格、Unicode、重复flag、布尔双flag、位置参数、AliasChoices、未知argv和shell转义回归。
- **原生回归**：tests/test_source_cli.py。
- **实际依赖**：无；可先提供shell无关候选数据；脚本是离线生成物，无外部服务。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/667)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/providers/cli.py)。

## 18．成功字段的来源和优先级解释

- **类型与场景**：增强提案；本地配置维护者要知道quantity最后来自env还是文件，而不是只看最终5。
- **原版证据**：已有PYDANTIC_SETTINGS_DEBUG来源级日志和source.settings_sources_data，最终实例无settings_explain。
- **交付目标**：新增opt-in逐字段来源记录，包含规范路径、物理键、选择/覆盖链与最终胜出来源；值可独立选择是否返回。
- **真实模块**：pydantic_settings/main.py、pydantic_settings/sources/base.py。
- **兼容边界**：已有调试日志继续；不把字段值相同就猜同来源，不改来源优先级；与步骤12失败定位是不同输出。
- **正常验收**：quantity解释为env覆盖dotenv，title解释为dotenv，嵌套两个字段可来自不同来源。
- **边界验收**：默认值、显式None/空值、alias合并、同类source多实例、自定义source元数据不足、初始化名还原和性能回归。
- **原生回归**：tests/test_precedence_and_merging.py、tests/test_settings.py。
- **实际依赖**：无；本地来源metadata；不依赖步骤12先实现。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/issues/505)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)；[来源3](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/base.py)。

## 19．验证后发布的配置刷新与差异

- **类型与场景**：增强提案；本地长期运行工具读取修改后的配置，先展示差异，验证失败保留旧实例。
- **原版证据**：settings_cached/clear_cache已有；环境2变8后缓存仍2，手动clear后8，无settings_refresh。
- **交付目标**：新增显式refresh候选构建与结构化diff，全部验证成功后可选择原子发布新缓存；旧引用保持原快照。
- **真实模块**：pydantic_settings/main.py。
- **兼容边界**：默认懒缓存和clear_cache保持；不自动起文件监听或修改旧可变对象，不承诺刷新所有调用者引用。
- **正常验收**：合法新quantity发布后新cached得到8，旧对象仍2；非法候选报错且缓存仍旧对象。
- **边界验收**：并发刷新/clear、无变化、子类缓存、来源异常、嵌套diff、可变字段和发布回调失败规则回归。
- **原生回归**：tests/test_settings.py。
- **实际依赖**：无；现锁/缓存与Pydantic校验；不依赖来源解释。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)。

## 20．可等待的本地来源构建

- **类型与场景**：增强提案；本地异步应用的来源适配器需要await读取/计算配置，保持现有优先级。
- **原版证据**：async local source返回协程后同步_build_values尝试copy，AttributeError；无settings_load_async，夹具关闭未等待协程。
- **交付目标**：新增独立async工厂，顺序或明确策略await同步/异步来源，再用既有合并和模型校验；同步构造保持。
- **真实模块**：pydantic_settings/main.py、pydantic_settings/sources/base.py。
- **兼容边界**：不在现构造器偷偷嵌套事件循环；来源异常/取消直接传给调用者，不自动并发有优先级依赖的来源。
- **正常验收**：await本地合成source与env组合得到预期值，来源执行顺序与同步版本一致且无未等待协程。
- **边界验收**：取消、超时由调用者管理、异常source、返回非mapping、已有运行loop、混合来源和缓存整合回归。
- **原生回归**：tests/test_settings.py、tests/test_precedence_and_merging.py。
- **实际依赖**：无；标准库asyncio/awaitable；不涉及任何远程配置服务。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/main.py)；[来源2](https://github.com/pydantic/pydantic-settings/blob/8dc9e05ab07d91e21dd2a37d0b9c30f6d92b1930/pydantic_settings/sources/base.py)。

## 控制端冻结与累计回归

未来以隔离环境字典、临时本地文件和合成argv调用真实BaseSettings/CliApp，核对值/类型、fields_set、来源身份、准确异常、argv往返和原输入未改。async仅使用本地受控协程。所有缓存观察都在结束时清理，文件和环境还原。每步累计关联原生回归。1256项原版通过不代表新增契约通过；冻结验收、离线制品和正式接入尚未开始。
