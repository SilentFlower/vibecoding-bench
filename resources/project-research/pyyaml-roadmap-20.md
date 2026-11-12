# PyYAML：二十步真实工程迭代路线

固定 [yaml/pyyaml@f5e4504a92f169f65350a1047dccb23bc97028be](https://github.com/yaml/pyyaml/tree/f5e4504a92f169f65350a1047dccb23bc97028be)，详见[单仓审查](./pyyaml.md)。共 20 步：18 项增强提案、2 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．合并序列按键值保持首项优先（问题修复）

- 来源／场景：https://github.com/yaml/pyyaml/issues/953
- 原版现状：flatten_mapping用id(key_node.value)去重；长同名键字符串对象不同，<<:[*a,*b]当前得到后者值。
- 交付目标：按YAML键语义处理合并优先级，显式本地键继续覆盖合并键。
- 影响模块：constructor.py:SafeConstructor.flatten_mapping；tests/test_merge.py
- 兼容边界：不依赖Python短字符串驻留；不把字典1/true键相等问题另算一步。
- 正常验收：两个源的long_field_name相同时首源获胜，短键/长键相同。
- 异常／边界：嵌套merge、多个<<、显式覆盖、非标量键与无效merge类型。
- 原生回归：test_merge.py；legacy test_constructor/test_recursive
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．无效显式标量统一为带位置构造错误（问题修复）

- 来源／场景：https://github.com/yaml/pyyaml/issues/933
- 原版现状：!!bool maybe为KeyError、!!int/float nope为ValueError、!!timestamp nope为AttributeError，缺少YAML位置。
- 交付目标：捕获并规范为ConstructorError，保留原原因和node.start_mark。
- 影响模块：constructor.py:标量construct_yaml_*；error.py
- 兼容边界：正常合法标签值不变；未知内部编程错误不能全部吞掉。
- 正常验收：四类坏显式标签都可用except yaml.YAMLError捕获并定位。
- 异常／边界：空字符串、仅符号、无效日期/时区、超范围整数与嵌套节点。
- 原生回归：legacy test_errors/test_constructor；test_dump_load.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．安全转储复合键的可读回政策（增强提案）

- 来源／场景：https://github.com/yaml/pyyaml/issues/938
- 原版现状：safe_dump接受tuple键并写为sequence，safe_load随后因list不可哈希失败；当前已实测。
- 交付目标：增加明确composite_keys政策：严格拒绝不可安全读回的键，或使用显式不可变序列键loader模式。
- 影响模块：representer.py；SafeConstructor.construct_mapping；safe入口
- 兼容边界：默认行为兼容；不在SafeLoader隐含构造任意Python对象。
- 正常验收：strict模式在写入前拒绝tuple键；显式immutable模式可读回相等映射。
- 异常／边界：嵌套sequence键、集合/映射键、键碰撞、类型标签和序列值仍为list。
- 原生回归：legacy test_representer/test_constructor；test_dump_load.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．可选择 YAML 1.2 解析方案（增强提案）

- 来源／场景：resolver.py默认YAML1.1 bool/int/float规则；固定源码：[lib/yaml/resolver.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/resolver.py)、[lib/yaml/representer.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/representer.py)。
- 原版现状：on/off/yes/no目前按1.1转布尔，是原设计；没有公开1.2 Core/JSON schema配置。
- 交付目标：提供命名schema配置，使1.2与现有1.1可并存并影响配套转储引号判断。
- 影响模块：resolver.py；loader/dumper；representer.py
- 兼容边界：默认1.1不变；BaseLoader全字符串已有，不当作新增功能。
- 正常验收：1.2下on/off为字符串，true/false为布尔，0o前缀与数字规则按所选方案。
- 异常／边界：显式tag、sexagesimal、日期、quoted标量及dump再load类型保持。
- 原生回归：legacy test_schema/test_resolver；test_dump_load.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．重复映射键的显式处理（增强提案）

- 来源／场景：BaseConstructor.construct_mapping当前后者覆盖；固定源码：[lib/yaml/constructor.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/constructor.py)、[lib/yaml/composer.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/composer.py)。
- 原版现状：重复字段默默覆盖；compose有全部key nodes但普通safe_load丢失前位置。
- 交付目标：增加duplicate_keys=allow/warn/error，错误给出首次和再次位置及合并来源。
- 影响模块：constructor.py；composer.py；loader配置
- 兼容边界：默认allow保持；merge继承与本地覆盖不自动等同显式重复。
- 正常验收：a重复两次严格报错并展示两行，正常merge覆盖可配置接受。
- 异常／边界：1/true归一化碰撞、复杂键、别名复用、schema变化及重复<<。
- 原生回归：legacy test_constructor/test_errors；test_merge.py
- 真实依赖：01, 04

## 06．加载过程统一预算限制（增强提案）

- 来源／场景：composer.py递归与reader/scanner；深配置输入场景；固定源码：[lib/yaml/composer.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/composer.py)、[lib/yaml/reader.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/reader.py)、[lib/yaml/constructor.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/constructor.py)。
- 原版现状：无公开深度、节点、别名引用数和文档长度预算，SafeLoader安全标签不等于资源限制。
- 交付目标：提供LoadLimits，在读取/组合/构造各阶段受控报错并包含限制位置。
- 影响模块：reader.py；composer.py；constructor.py；Loader
- 兼容边界：默认不限；仅合成输入验证，不运行大规模资源耗尽攻击。
- 正常验收：小型合法树正常，超深/超节点/超别名在阈值处终止。
- 异常／边界：流分块字节数、0边界、单巨大标量、merge复用节点与文档计数。
- 原生回归：legacy test_recursive/test_reader/test_input_output
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．循环别名的可选择图政策（增强提案）

- 来源／场景：composer.py别名返回原Node；constructor缓存维护图身份；固定源码：[lib/yaml/composer.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/composer.py)。
- 原版现状：递归别名合法且会生成循环容器，配置消费方没有公开拒绝循环或复制别名的政策。
- 交付目标：提供alias_policy=preserve/reject_cycles/copy，复制模式限制展开成本。
- 影响模块：composer.py；constructor.construct_object；Loader
- 兼容边界：默认preserve保持YAML图语义；共享无环节点不能误判为环。
- 正常验收：self循环在reject_cycles受控报错，普通复用在preserve保持is关系。
- 异常／边界：间接环、列表环、嵌套merge、copy指数扩张受第06步预算约束。
- 原生回归：legacy test_recursive；test_merge.py
- 真实依赖：06

## 08．未知标签安全保留为数据（增强提案）

- 来源／场景：SafeConstructor.construct_undefined；自定义配置标签场景；固定源码：[lib/yaml/constructor.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/constructor.py)、[lib/yaml/representer.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/representer.py)、[lib/yaml/nodes.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/nodes.py)。
- 原版现状：SafeLoader遇!Environment等未知标签直接失败；只能逐个写constructor。
- 交付目标：增加显式TaggedValue保留tag、节点种类和值，不执行或导入标签指向对象。
- 影响模块：constructor.py；representer.py；nodes.py
- 兼容边界：默认仍拒绝；!!python/object等标签在保留模式也只是惰性数据，不触发构造。
- 正常验收：!Region cn及标记列表可读、检查并转储保留标签。
- 异常／边界：未知mapping键、递归tag、tag前缀冲突、标量隐式类型与安全读回。
- 原生回归：legacy test_multi_constructor/test_representer
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．构造结果可追溯源码位置（增强提案）

- 来源／场景：nodes.py有start_mark/end_mark；普通safe_load丢标记；固定源码：[lib/yaml/nodes.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/nodes.py)、[lib/yaml/constructor.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/constructor.py)。
- 原版现状：compose已可获取位置，但应用要同时拿构造值与每个字段行列需自写节点对应。
- 交付目标：提供load_with_marks返回值和按结构路径索引的来源元数据。
- 影响模块：constructor.py；nodes.py；error.Mark
- 兼容边界：不包装默认str/int值或改变其类型；标记侧表不保留全部输入除非显式。
- 正常验收：定位service/port到原文件行列，merge值可追溯锚点来源与覆盖位置。
- 异常／边界：别名多路径、非字符串键、Unicode列、多个文档与缺失路径。
- 原生回归：legacy test_mark/test_constructor；test_merge.py
- 真实依赖：01, 05

## 10．只构造选择的文档和字段（增强提案）

- 来源／场景：https://github.com/yaml/pyyaml/issues/910
- 原版现状：load_all虽按文档惰性，但每个选中文档仍构造全树；没有路径选择入口。
- 交付目标：select_load按文档编号与精确键/索引路径构造目标，仍解析校验未选内容。
- 影响模块：composer/constructor；新增selection入口
- 兼容边界：不宣称跳过解析或支持任意查询语言；别名引用目标外节点需明确构造。
- 正常验收：多文档中只取第2个的service/name，与完整load_all取值相同。
- 异常／边界：空匹配/null、复杂键、坏未选子树、merge/别名依赖与资源预算。
- 原生回归：test_dump_load.py；legacy test_structure/test_errors
- 真实依赖：06, 07, 09

## 11．保留注释与标量样式的文档模型（增强提案）

- 来源／场景：scanner.py忽略注释；compose节点保留部分style但不保留trivia；固定源码：[lib/yaml/scanner.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/scanner.py)。
- 原版现状：safe_load/dump再写配置会丢注释、引号细节与未变空白；目前不承诺round-trip编辑。
- 交付目标：独立RoundTripDocument保留token/trivia与值关联，单字段编辑只重写需要区间。
- 影响模块：scanner/parser；nodes；新增文档编辑与emitter层
- 兼容边界：默认轻量load/dump不变；不能把普通dict伪称无损文档。
- 正常验收：带注释、块标量和锚点的配置仅改port，其余未改字节保持。
- 异常／边界：CRLF、尾注释、重复键、别名编辑传播规则与多文档边界。
- 原生回归：legacy scanner/emitter/input_output；字节级文档验收
- 真实依赖：05, 07, 09

## 12．注册器按实例隔离并可组合（增强提案）

- 来源／场景：BaseConstructor/Resolver/BaseRepresenter.add_*类级注册；固定源码：[lib/yaml/constructor.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/constructor.py)、[lib/yaml/resolver.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/resolver.py)、[lib/yaml/representer.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/representer.py)。
- 原版现状：现有类继承能隔离，便捷add_constructor等仍改类全局；多租户服务易互相影响。
- 交付目标：提供不可变LoaderConfig注册表，可组合构造器/解析器/表示器并检测冲突。
- 影响模块：constructor/resolver/representer注册API；loader/dumper初始化
- 兼容边界：保留旧类方法；配置修改创建新对象，不依赖free-threading未验证现象称BUG。
- 正常验收：两个实例用同tag不同处理互不污染，组合重复tag默认拒绝。
- 异常／边界：多构造前缀优先级、继承内置规则、并发读及回调有状态隔离。
- 原生回归：legacy test_multi_constructor/test_resolver/test_representer
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．按字段路径控制标量展示（增强提案）

- 来源／场景：representer.py与emitter.py只收全局style/default_style；固定源码：[lib/yaml/representer.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/representer.py)、[lib/yaml/emitter.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/emitter.py)。
- 原版现状：单独让script字段用literal、短标签用双引号需自定义类型/representer，缺少声明式路径格式。
- 交付目标：增加style_rules匹配类型化路径，选择plain/single/double/literal/folded及chomping。
- 影响模块：representer/serializer/emitter；路径匹配辅助
- 兼容边界：默认风格不变；指定plain若会改变所选schema下类型必须报价或明确拒绝。
- 正常验收：script多行用|，id用双引号，其他字段自动风格且读回类型相同。
- 异常／边界：空串、尾换行、长Unicode、锚点共享节点多路径风格冲突。
- 原生回归：legacy test_emitter/test_representer；test_dump_load.py
- 真实依赖：04, 12

## 14．节点变换的稳定访问器入口（增强提案）

- 来源／场景：compose/serialize原生节点API；批量替换特定tag场景；固定源码：[lib/yaml/nodes.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/nodes.py)。
- 原版现状：用户可手工遍历Node，但需处理别名图、键值区别与元数据更新，没有稳定visitor协议。
- 交付目标：提供visit_nodes带键/值/索引路径与替换/跳过操作，维护Node种类和图共享。
- 影响模块：nodes.py；composer/serializer；新增visitor
- 兼容边界：不自动构造Python对象；回调返回错误Node应在序列化前失败。
- 正常验收：将!Old标签改为!New并只编辑指定标量，serialize后结构合法。
- 异常／边界：循环图只访问一次或按路径政策、删除mapping entry、无效tag与源码mark维护。
- 原生回归：legacy test_structure/test_recursive/test_emitter
- 真实依赖：07, 08, 09

## 15．显式 JSON 兼容转换政策（增强提案）

- 来源／场景：SafeLoader可产生date/bytes/set/非字符串键；JSON消费者真实场景；固定源码：[lib/yaml/constructor.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/constructor.py)。
- 原版现状：safe_load并不保证结果可json.dumps，应用需自行决定日期、集合、键和别名处理。
- 交付目标：提供to_json_compatible，声明日期/二进制/集合/非字符串键/非有限数政策并报告路径。
- 影响模块：新增兼容转换；constructor结果与TaggedValue
- 兼容边界：不改变safe_load类型；默认拒绝信息损失，转换政策不得偷偷覆盖键碰撞。
- 正常验收：日期转ISO、bytes转显式base64结构，输出可被标准json序列化。
- 异常／边界：1和"1"键碰撞、循环图、NaN/Infinity、未知tag与tuple键政策。
- 原生回归：legacy test_constructor/test_representer；独立json验收
- 真实依赖：03, 07, 08, 09

## 16．官方模块命令行验证与转换（增强提案）

- 来源／场景：当前lib/yaml无__main__.py；批量配置人工校验场景；固定源码：[lib/yaml/__init__.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/__init__.py)。
- 原版现状：库提供API但无python -m yaml统一验证/格式化/JSON转换入口。
- 交付目标：增加模块CLI，显式schema/loader、安全默认、文档序号和结构化位置错误。
- 影响模块：新增yaml/__main__.py；load/dump/JSON转换
- 兼容边界：不默认调用UnsafeLoader；单文档和多文档模式显式，不根据文件内容执行标签。
- 正常验收：检查多文档配置、格式化或转JSON，退出码和文件结果正确。
- 异常／边界：坏第2文档、未知tag、stdin/Unicode文件、预算、破管道与只验证不写输出。
- 原生回归：新增CLI场景；legacy test_errors/input_output
- 真实依赖：04, 06, 15

## 17．可配置且稳定的锚点名称（增强提案）

- 来源／场景：serializer.py:generate_anchor默认id001；结构图导出场景；固定源码：[lib/yaml/serializer.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/serializer.py)。
- 原版现状：输出锚点由顺序数字生成，不能显式提供业务名称或检查命名冲突。
- 交付目标：允许anchor_namer(node,path)或名称表，保留共享/循环图关系并验证合法唯一名称。
- 影响模块：serializer.py:anchor_node/generate_anchor；dumper
- 兼容边界：默认idNNN不变；不是复制别名，也不依赖私有Node动态属性。
- 正常验收：共享defaults用&defaults/*defaults，重排无关字段不改变指定名称。
- 异常／边界：同名冲突、非法字符、循环节点、未引用节点与手工名称空值。
- 原生回归：legacy test_recursive/test_serializer对照；test_emitter
- 真实依赖：07, 12

## 18．序列项目的公开缩进控制（增强提案）

- 来源／场景：emitter.py:increase_indent及expect_block_sequence；固定源码：[lib/yaml/emitter.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/emitter.py)。
- 原版现状：全局indent存在，但无法公共配置mapping下sequence的indentless行为与项目偏移。
- 交付目标：增加sequence_indent/indentless_sequences明确选项，保持嵌套list/map统一。
- 影响模块：emitter.py；dumper/__init__.py转储参数
- 兼容边界：默认输出保持；参数必须满足有效YAML缩进范围，不允许靠字符串后处理。
- 正常验收：services下-项目可缩进两格，嵌套mapping仍能safe_load等值。
- 异常／边界：空集合、嵌套序列、flow混用、多文档及宽度换行交互。
- 原生回归：legacy test_emitter/test_indent相关fixtures
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．文件转储的原子替换入口（增强提案）

- 来源／场景：dump_all向任意stream逐块写入；真实配置更新场景；固定源码：[lib/yaml/__init__.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/__init__.py)。
- 原版现状：现有dump只遵守writer协议，写一半失败会留下半文件；没有带原子替换的path API。
- 交付目标：提供dump_file_atomic，先同目录临时写成功再替换并清理，CLI复用。
- 影响模块：新增文件工具；dump_all；CLI写入
- 兼容边界：流API不变；明确权限、链接和replace失败行为，不承诺多文件分布式事务。
- 正常验收：有效配置替换成功；representer或writer失败原文件内容保持。
- 异常／边界：磁盘不足、只读目录、编码异常、空多文档与文件已存在策略。
- 原生回归：legacy test_input_output；文件副作用独立验收
- 真实依赖：16

## 20．显式 dataclass 配置映射适配（增强提案）

- 来源／场景：SafeConstructor/SafeRepresenter需逐类注册；结构化配置场景；固定源码：[lib/yaml/constructor.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/constructor.py)、[lib/yaml/representer.py](https://github.com/yaml/pyyaml/blob/f5e4504a92f169f65350a1047dccb23bc97028be/lib/yaml/representer.py)。
- 原版现状：YAMLObject需自定义类协议，普通dataclass没有按字段名/默认值/未知字段政策的安全适配。
- 交付目标：基于显式注册类型提供dataclass表示器和按给定类型加载，支持缺字段/未知字段政策及位置错误。
- 影响模块：适配模块；LoaderConfig；constructor/representer
- 兼容边界：不从输入tag导入任意类；不把typing注解当完整业务校验，首版列清支持类型。
- 正常验收：配置映射加载为已注册Service dataclass，默认port生效，转储可安全读回。
- 异常／边界：未知字段、必填缺失、嵌套list/Optional、递归类型、__post_init__异常与字段元数据。
- 原生回归：legacy custom constructor/representer；完整1287原生集合
- 真实依赖：09, 12

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
