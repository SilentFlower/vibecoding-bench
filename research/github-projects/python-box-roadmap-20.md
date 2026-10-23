# python-box：二十步真实工程迭代路线

固定 [cdgriffith/Box@a4c10e977b574114613431394b30412b50aaacce](https://github.com/cdgriffith/Box/tree/a4c10e977b574114613431394b30412b50aaacce)，原生证据见 [单仓审查](./python-box.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．pickle保留Box子类身份

- **类型与来源**：修复；[官方 #308](https://github.com/cdgriffith/Box/issues/308) 与固定源码。
- **原版现状与收益**：ReviewBox.a原为ReviewBox，unpickle后变Box，原版实测。
- **交付及模块**：让__new__/state恢复使用真实子类与配置，嵌套box_class保持一致；box.py:Box.__new__／__setstate__。
- **兼容与依赖**：不改变普通Box，也不通过全局pickle钩子修补；仅本地可信pickle验收；步骤依赖：无。
- **正常验收**：pickle协议往返后根与子节点类和选项相同。
- **异常／边界验收**：frozen/default_box、自定义__init__／__new__、深层BoxList和共享引用。
- **原生回归**：test/test_box.py、test/test_box_list.py。

## 02．点分导入不因键顺序丢值

- **类型与来源**：修复；[官方 #305](https://github.com/cdgriffith/Box/issues/305) 与固定源码。
- **原版现状与收益**：a.b先出现时创建a.b，随后a映射覆盖；反序同源数据却保留b。
- **交付及模块**：导入时检测或合并点分展开冲突，保证顺序不造成静默数据丢失；box.py:__init__／__setitem__、from_yaml路径。
- **兼容与依赖**：冲突有不同标量时显式error/last策略；box_dots=False字面键保持；步骤依赖：无。
- **正常验收**：两种实测YAML顺序得到等价a.b与a.d。
- **异常／边界验收**：真冲突、点分字面排除、列表下标、空子表和default_box组合。
- **原生回归**：test/test_box.py、test/test_from_file.py、test/test_converters.py。

## 03．冻结嵌套结构能序列化YAML

- **类型与来源**：修复；[官方 #272](https://github.com/cdgriffith/Box/issues/272) 与固定源码。
- **原版现状与收益**：frozen_box列表内嵌Box触发RepresenterError，实测。
- **交付及模块**：输出前递归转换冻结tuple／Box为YAML后端支持的数据，不修改原冻结对象；box.py:to_dict／to_yaml、box_list.py、converters.py。
- **兼容与依赖**：序列化不解冻源对象；普通JSON/TOML/msgpack不回归；步骤依赖：无。
- **正常验收**：冻结dict含多层list/dict写YAML再读回语义一致。
- **异常／边界验收**：空tuple、混合自定义intact类型、循环和非字符串key的异常明确。
- **原生回归**：test/test_converters.py、test/test_box.py、test/test_box_list.py。

## 04．默认节点只在赋值时附着

- **类型与来源**：增强；[官方 #274](https://github.com/cdgriffith/Box/issues/274) 与固定源码。
- **原版现状与收益**：create_on_get=False返回脱离的临时Box，b.foo.bar=1后b仍空。
- **交付及模块**：提供create_on_set的惰性路径代理，读取不创建、成功写入才连接父路径；box.py:__get_default／__getattr__／__setitem__。
- **兼容与依赖**：现有create_on_get语义保持，功能显式开启；不把普通读取转永久状态；步骤依赖：无。
- **正常验收**：读b.foo不改b，随后写b.foo.bar后b正确含层级。
- **异常／边界验收**：冻结父节点、代理重复使用、父中途替换、列表与异常赋值不能留下半路径。
- **原生回归**：test/test_box.py。

## 05．CamelCase属性别名保持原始键

- **类型与来源**：增强；[官方 #279](https://github.com/cdgriffith/Box/issues/279) 与固定源码、#300。
- **原版现状与收益**：camel_killer_box实测输出load_balancer，无法原样发回要求loadBalancer的外部API。
- **交付及模块**：新增alias模式，只转换属性访问映射，实际dict键保持；box.py:_safe_attr／__getattr__／__setattr__。
- **兼容与依赖**：现有破坏式camel_killer行为保持；alias与dotted路径组合规则统一；步骤依赖：无。
- **正常验收**：用load_balancer修改后to_dict仍为loadBalancer。
- **异常／边界验收**：loadBalancer与load_balancer同时出现给冲突策略，多个大小写／列表下标访问一致。
- **原生回归**：test/test_box.py。

## 06．列表元素可按位置或主键合并

- **类型与来源**：增强；[官方 #263](https://github.com/cdgriffith/Box/issues/263) 与固定源码。
- **原版现状与收益**：已有extend/unique，缺少按元素位置或稳定key递归合并。
- **交付及模块**：扩展box_merge_lists增加index/key策略和冲突处理，保留尾部元素政策显式；box.py:merge_update、box_list.py。
- **兼容与依赖**：默认replace、已有extend/unique保持；不是重复增加已存在列表追加；步骤依赖：无。
- **正常验收**：两个items对象以id合并字段，未触及元素保留。
- **异常／边界验收**：重复id、无id、不同长度、非dict项和frozen目标保持确定错误／回滚边界。
- **原生回归**：test/test_box.py、test/test_box_list.py。

## 07．固定字段形状而允许改值

- **类型与来源**：增强；[官方 #147](https://github.com/cdgriffith/Box/issues/147) 与固定源码。
- **原版现状与收益**：frozen_box把改值也禁掉，无仅锁定新增字段的策略。
- **交付及模块**：提供sealed_box，按定义的层级禁止未知键，合法已有值可更新；box.py:__setitem__／update／merge_update、BoxList。
- **兼容与依赖**：默认不锁定；不能只拦属性写而漏dict/update/merge，是否允许删除明确；步骤依赖：无。
- **正常验收**：port可改，拼错porrt通过所有入口均拒绝。
- **异常／边界验收**：嵌套、default_box冲突、删除后重加、pickle/copy和list新元素策略。
- **原生回归**：test/test_box.py、test/test_box_list.py。

## 08．结构化字段类型契约

- **类型与来源**：增强；[官方 #209](https://github.com/cdgriffith/Box/issues/209) 与固定源码。
- **原版现状与收益**：Box可泛型提示但无TypedDict等字段契约或运行时结构校验。
- **交付及模块**：提供独立TypedBox工厂消费TypedDict／显式schema，按字段验证并产出明确类型信息；Box扩展类、ConfigBox与schema helper。
- **兼容与依赖**：普通动态Box不变；类型声明与运行时校验区分，不eval任意注解代码；步骤依赖：无。
- **正常验收**：必需name/可选year按schema读写，导出普通dict正常。
- **异常／边界验收**：未知键、Union、nested/list及完整错误路径；静态类型测试另列工具预算。
- **原生回归**：test/test_box.py、test/test_config_box.py、新增schema／typing集合。

## 09．YAML注释与顺序保真模式

- **类型与来源**：增强；[官方 #184](https://github.com/cdgriffith/Box/issues/184) 与固定源码。
- **原版现状与收益**：Box.from_yaml后再to_yaml实测原首／inline注释均丢失。
- **交付及模块**：增加roundtrip=True的源元数据桥接，修改Box值时维护ruamel注释对象对应关系；converters.py:_from_yaml／_to_yaml、Box metadata。
- **兼容与依赖**：默认数据模式保持；可选ruamel依赖显式，不声称PyYAML也能保留所有风格；步骤依赖：无。
- **正常验收**：改一个端口后未动字段的comment与顺序保持。
- **异常／边界验收**：锚点alias、quoted key、list插删、新字段和源对象不共享意外可变状态。
- **原生回归**：test/test_converters.py、test/test_from_file.py。

## 10．显式导出原生标量类型

- **类型与来源**：增强；[官方 #264](https://github.com/cdgriffith/Box/issues/264) 与固定源码。
- **原版现状与收益**：YAML读回ScalarFloat，to_dict仍可包含ruamel标量子类；其他库不接受精确非builtin类型。
- **交付及模块**：提供native_types=True递归归一化受支持标量，保留数值／字符串语义；box.py:to_dict、box_list.py:to_list、converters.py。
- **兼容与依赖**：默认当前类型保留；与roundtrip模式分开输出，不为归一化丢精度或日期类型；步骤依赖：无。
- **正常验收**：ScalarFloat/ScalarInt等导出为预期builtin且json等可用。
- **异常／边界验收**：Decimal/date/intact自定义类型按显式注册策略，不无条件str化；深层结构及循环。
- **原生回归**：test/test_converters.py、test/test_box.py。

## 11．无歧义的分段路径API

- **类型与来源**：增强；[官方 #123](https://github.com/cdgriffith/Box/issues/123) 与固定源码、#298。
- **原版现状与收益**：box_dots字符串把数字键／字面点／括号与路径混用；regex exclude只能整体绕过。
- **交付及模块**：提供get_path/set_path/delete_path接受显式str/int段序列，避免用字符串猜真实键类型；box.py路径helper、box_list.py。
- **兼容与依赖**：普通Box[2]和Box["2"]仍不同，旧box_dots保留；字符串解析作为显式辅助；步骤依赖：无。
- **正常验收**：["uno",2]取整数键，["a.b"]取字面含点键，列表0正确。
- **异常／边界验收**：负索引、空路径、缺失父结构、冻结策略与创造节点上限明确。
- **原生回归**：test/test_box.py、test/test_box_list.py。

## 12．选择字段并保持结构

- **类型与来源**：增强；现有Box配置编辑与导出路径分析（增强提案）。
- **原版现状与收益**：只有完整to_dict或手写循环，没有声明式include/exclude投影。
- **交付及模块**：新增select(paths,exclude=...)生成独立Box子树，按分段路径精确筛选；Box投影helper、BoxList。
- **兼容与依赖**：不修改原对象；缺失路径策略明确，禁止把同名字串全局匹配替代路径；步骤依赖：11。
- **正常验收**：选出server.port和users[*].id后结构正确且无其他值。
- **异常／边界验收**：缺路径、重叠include/exclude、字面点键、空列表和别名共享不得意外泄漏字段。
- **原生回归**：test/test_box.py、test/test_box_list.py。

## 13．保持键顺序的重命名

- **类型与来源**：增强；现有Box配置编辑与导出路径分析（增强提案）。
- **原版现状与收益**：删后赋值会把键移到尾部并重新触发转换，缺少公共rename_key。
- **交付及模块**：新增rename_key检查目标冲突并按原位置更新key和safe_attr映射；box.py转换索引与顺序存储。
- **兼容与依赖**：现有赋值不变；不隐式重命名别处引用字符串；步骤依赖：无。
- **正常验收**：port→listen_port值、位置和子Box配置保持。
- **异常／边界验收**：camel别名冲突、protected keys、frozen/sealed、int键和失败后原样。
- **原生回归**：test/test_box.py。

## 14．批量修改失败回滚

- **类型与来源**：增强；现有Box配置编辑与导出路径分析（增强提案）。
- **原版现状与收益**：update/merge_update遇中间recast错误可留下已写字段，无公开事务编辑上下文。
- **交付及模块**：新增transaction或copy-edit-commit入口，成功整体接受，异常保留原值／配置；box.py:update／merge_update、事务helper。
- **兼容与依赖**：普通赋值行为保持；不声称多线程或多进程隔离，首版对象内事务；步骤依赖：无。
- **正常验收**：两项更新成功都提交，第二项cast失败时第一项也回滚。
- **异常／边界验收**：深层BoxList、冻结/封字段、异常退出与嵌套事务规则明确，原引用关系不破坏。
- **原生回归**：test/test_box.py、test/test_box_list.py。

## 15．按顺序加载多份配置

- **类型与来源**：增强；[官方 #224](https://github.com/cdgriffith/Box/issues/224) 与固定源码。
- **原版现状与收益**：已有box_from_file单文件统一加载，但多层merge需应用自己循环并决定错误边界。
- **交付及模块**：提供load_layers(paths,merge_policy)显式冻结顺序、缺文件策略和一次性发布结果；from_file.py、box.py:merge_update。
- **兼容与依赖**：单文件入口保持；不自动找祖先配置或加载未声明文件；步骤依赖：06、14。
- **正常验收**：base.json+override.yaml合并遵守指定优先，未改基础源。
- **异常／边界验收**：缺文件、混合根dict/list、解析失败、未知扩展和lists策略不留下半结果。
- **原生回归**：test/test_from_file.py、test/test_box.py。

## 16．配置值来源与覆盖链

- **类型与来源**：增强；现有Box配置编辑与导出路径分析（增强提案）。
- **原版现状与收益**：Box只存值，合并后不知道哪份文件或调用覆盖了字段。
- **交付及模块**：新增opt-in来源元数据，可按分段路径查询胜出源和被覆盖源，不含原值；from_file.py、merge_update provenance hook。
- **兼容与依赖**：默认不增加元数据；to_dict默认不暴露源信息，未跟踪字段可标unknown；步骤依赖：15。
- **正常验收**：多层配置端口来源明确，对应实际最终值。
- **异常／边界验收**：列表key合并、rename、删除／重加、默认创建与手动赋值更新来源，不保留敏感值副本。
- **原生回归**：test/test_from_file.py、test/test_box.py。

## 17．序列化文件可原子发布

- **类型与来源**：增强；converters.py:_to_json/_to_yaml等直接写文件的源码。
- **原版现状与收益**：导出直接w截断，遇编码／后端错误可能破坏旧文件。
- **交付及模块**：增加通用atomic输出选项，先序列化／临时文件完成后同目录发布；converters.py多格式写入公共helper。
- **兼容与依赖**：不改变返回字符串模式；已存在mode/encoding规则保持，原子不等于断电持久；步骤依赖：无。
- **正常验收**：JSON/YAML/TOML/msgpack合成文件导出后原生读回一致。
- **异常／边界验收**：序列化或replace失败保留旧字节，临时权限与清理有界，调用者流不擅自close。
- **原生回归**：test/test_converters.py、test/test_from_file.py。

## 18．ConfigBox的严格类型转换

- **类型与来源**：增强；固定源码与observe.py配置／文件场景。
- **原版现状与收益**：ConfigBox.bool("maybe")实测True，int/float失败无完整key上下文。
- **交付及模块**：增加strict=True及明确缺失哨兵，未知bool词拒绝，允许显式default=None；config_box.py:bool／int／float／list。
- **兼容与依赖**：默认旧宽松cast保留；不把空字符串误当缺字段，用户custom mod仍支持；步骤依赖：无。
- **正常验收**：true/false/yes/no按规则，坏port报key路径，缺值可返回None。
- **异常／边界验收**：NaN/Infinity许可、bool作为int、None／空值、列表单项失败与secret遮蔽。
- **原生回归**：test/test_config_box.py。

## 19．大数据JSONL逐记录导出

- **类型与来源**：增强；_from_json(multiline=True)已有导入；BoxList.to_json当前全表json dump。
- **原版现状与收益**：现有JSONL导入不等于流式导出，批量结果需应用自行循环。
- **交付及模块**：提供BoxList.iter_jsonl／write_jsonl和对任意有界iterator导出辅助，逐条编码；box_list.py、converters.py。
- **兼容与依赖**：现有from_json(multiline=True)保留作对照，不计新增读取；普通JSON格式不变；步骤依赖：无。
- **正常验收**：十万合成记录首条有界取出，逐行标准json重读内容一致。
- **异常／边界验收**：中途坏记录、提前close、newline、空输入和不支持类型的错误行号；atomic整文件模式需预算。
- **原生回归**：test/test_box_list.py、test/test_converters.py。

## 20．YAML多文档流读取

- **类型与来源**：增强；converters.py:_from_yaml使用单次yaml.load，配置分批文档使用场景。
- **原版现状与收益**：单文档读Box不能消费---分隔的多个独立配置。
- **交付及模块**：增加from_yaml_all惰性入口，每个文档单独转换Box/BoxList，空文档策略明确；converters.py、from_file.py与Box/BoxList便捷入口。
- **兼容与依赖**：单文档from_yaml不变；显式safe loader，不能用任意对象构造扩展；步骤依赖：无。
- **正常验收**：两个dict文档和list文档逐一读取，类型和值正确。
- **异常／边界验收**：空文档、坏第二文档、锚点跨文档拒绝、资源限制和文件关闭，roundtrip支持范围另列。
- **原生回归**：test/test_converters.py、test/test_from_file.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
