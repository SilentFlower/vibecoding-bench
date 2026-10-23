# Confuse：二十步真实工程迭代路线

固定 [beetbox/confuse@bf42783301ac4e9c640328ec95486952fd599ce6](https://github.com/beetbox/confuse/tree/bf42783301ac4e9c640328ec95486952fd599ce6)，原生证据见 [单仓审查](./confuse.md)。下列是逐仓源码核对后的研究提案，尚未实施；保持同一真实工作树累计推进。

## 01．嵌套叶覆盖避免对标量执行update

- **类型与来源**：修复；[官方#215](https://github.com/beetbox/confuse/issues/215) 与固定源码。
- **原版现状与收益**：APP_DATABASE完整YAML与APP_DATABASE__PORT同时存在抛AttributeError；点号set_args走相同build_dict缺陷。
- **交付及模块**：更具体嵌套键覆盖目标叶，仅映射对映射沿现有语义合并；util.build_dict、sources.EnvSource、ConfigView.set_args。
- **兼容与依赖**：父键排序和低优先级来源不变；环境与CLI共享修复，不拆两步；步骤依赖：无。
- **正常验收**：host保留localhost、port变5433，输入顺序反转仍一致。
- **异常／边界验收**：标量/list/null/映射互撞、空路径片段、None的keep_none、重复深路径。
- **原生回归**：test/test_env.py、test/test_cli.py、test/test_utils.py。

## 02．列表子视图更新保留列表结构和其他元素

- **类型与来源**：修复；[官方#169](https://github.com/beetbox/confuse/issues/169) 与固定源码。
- **原版现状与收益**：stages[0][name].set后stages变成{0:{name:...}}，第二项丢失。
- **交付及模块**：引入区分映射键与序列索引的覆写路径，在已有列表上形成正确局部overlay；core.Subview.set／add、RootView源组合。
- **兼容与依赖**：不就地修改调用者传入source；普通映射overlay仍可跨source继承，列表替换语义明确；步骤依赖：无。
- **正常验收**：修改第一stage名称后仍为两元素list，第二stage及第一项其余字段保留。
- **异常／边界验收**：负索引、越界、空列表、类型冲突、多层list/map、add与set优先级。
- **原生回归**：test/test_views.py、test/test_dump.py。

## 03．Choice接受有界通用可迭代候选

- **类型与来源**：增强；[官方#192](https://github.com/beetbox/confuse/issues/192) 与固定源码。
- **原版现状与收益**：Choice支持Sequence/dict/Enum，但frozenset实测NotImplementedError，构造doc称iterable而入口较窄。
- **交付及模块**：构造时一次快照通用Iterable，统一匹配与候选诊断；templates.Choice.convert_choices／format_choices。
- **兼容与依赖**：不是让无限迭代自动终止；明确要求有限输入，dict保留值映射/Enum保留实例，不把字符串拆为候选字符；步骤依赖：无。
- **正常验收**：frozenset和一次性生成器允许合法值，失败诊断仍能列候选。
- **异常／边界验收**：空候选、重复值、迭代中异常、仅一次遍历、不支持比较的对象和默认值。
- **原生回归**：test/test_validation.py、test/test_valid.py。

## 04．注释恢复处理文件末尾与重复嵌套键

- **类型与来源**：修复；[官方#148](https://github.com/beetbox/confuse/issues/148) 与固定源码。
- **原版现状与收益**：默认YAML最后为注释/空行时next越界StopIteration；当前按单个key存注释无法区分不同嵌套路径。
- **交付及模块**：将restore_yaml_comments按完整键路径/尾部区域归属恢复，尾部EOF正常终止；yaml_util.restore_yaml_comments、Configuration.dump。
- **兼容与依赖**：不承诺完整YAML CST保真；已支持的独立行注释顺序保持，不把正文字符串当注释；步骤依赖：无。
- **正常验收**：尾注释和空行文件可dump，两组同名子键保留各自说明。
- **异常／边界验收**：纯注释/空文件、删除默认键、多行scalar含冒号、嵌套列表与无默认文件。
- **原生回归**：test/test_dump.py、test/test_yaml.py。

## 05．校验后的映射序列能再次dump

- **类型与来源**：修复；[官方#137](https://github.com/beetbox/confuse/issues/137) 与固定源码。
- **原版现状与收益**：Sequence(MappingTemplate)生成AttrDict，set回配置后Dumper遇子AttrDict抛RepresenterError。
- **交付及模块**：在配置输出边界规范化本库校验产物或注册对应安全representer；templates.AttrDict、yaml_util.Dumper、ConfigView.flatten。
- **兼容与依赖**：不允许任意Python对象tag执行；调用者自定义未知对象继续明确拒绝，原OrderedDict顺序保持；步骤依赖：无。
- **正常验收**：servers验证加默认port后写回并dump，YAML重新读取值一致。
- **异常／边界验收**：多层AttrDict/list、空序列、Unicode、redaction和非支持对象错误。
- **原生回归**：test/test_dump.py、test/test_validation.py。

## 06．重新加载来源替换已删除键

- **类型与来源**：修复；固定core.py/sources.py/templates.py定义与本地原生配置使用场景。
- **原版现状与收益**：YamlSource与EnvSource.load仅update，文件或环境删除b后b仍残留，实测两者同样发生。
- **交付及模块**：先完整解析新来源，成功后替换原内容；保留source metadata/priority；sources.YamlSource.load／EnvSource.load、Configuration.reload。
- **兼容与依赖**：映射上用户额外手工插值的存续策略需明确；解析失败保留旧来源，不能先clear后损坏；步骤依赖：无。
- **正常验收**：文件a/b改为仅a、环境移除B后对应来源均不再含b。
- **异常／边界验收**：空文件、optional文件消失、无匹配env、解析失败与base_for_paths元数据。
- **原生回归**：test/test_yaml.py、test/test_env.py、test/test_views.py。

## 07．序列内部敏感路径也参与redaction

- **类型与来源**：修复；固定core.py/sources.py/templates.py定义与本地原生配置使用场景。
- **原版现状与收益**：users[0][token].redact=True之后dump(redact=True)仍输出原值，flatten遇list退回原始get。
- **交付及模块**：对list/tuple逐索引递归并按完整redaction路径遮蔽；core.ConfigView.flatten／get_redactions、Configuration.dump。
- **兼容与依赖**：默认redact=False不改值；只替换输出，不修改真实配置，父路径redact盖住全子树；步骤依赖：02。
- **正常验收**：序列中的token输出REDACTED，非敏感用户名保留。
- **异常／边界验收**：嵌套list/map、多来源覆盖、索引越界标记、父子标记和full=False。
- **原生回归**：test/test_dump.py、test/test_views.py。

## 08．明确取得跨来源合并映射快照

- **类型与来源**：增强；[官方#194](https://github.com/beetbox/confuse/issues/194) 与固定源码。
- **原版现状与收益**：get()只返回首source整体字典，而flatten能合并；用户易误以get()结果代表全部配置。
- **交付及模块**：增加显式merged读取模式/方法，将已有view合并规则用于映射和子视图快照；core.ConfigView.get／flatten、RootView。
- **兼容与依赖**：默认get保持，避免破坏已有first语义；不把列表拼接与映射合并混为一谈；步骤依赖：无。
- **正常验收**：两sources的host与port合并，port来自高优先级，嵌套映射一致。
- **异常／边界验收**：标量/映射冲突、None、空来源、list替换、来源对象不被修改。
- **原生回归**：test/test_views.py、test/test_valid.py。

## 09．文字常量验证模板

- **类型与来源**：增强；[官方#88](https://github.com/beetbox/confuse/issues/88) 与固定源码。
- **原版现状与收益**：OneOf([bool,ask,skip])中的字符串被解释为String默认值，unexpected也通过；这不是literal匹配。
- **交付及模块**：新增Literal/明确常量模板，供OneOf严格匹配状态值；templates新Literal、OneOf与as_template显式接入。
- **兼容与依赖**：保留现有字符串作默认值简写；不静默改变所有String默认契约；步骤依赖：无。
- **正常验收**：OneOf([bool,Literal(ask),Literal(skip)])接受三类、拒绝unexpected。
- **异常／边界验收**：False与0类型边界、None、集合常量不合法时清楚诊断、缺失默认。
- **原生回归**：test/test_validation.py、test/test_valid.py。

## 10．可选YAML1.2式标量解析预设

- **类型与来源**：增强；[官方#183](https://github.com/beetbox/confuse/issues/183) 与固定源码。
- **原版现状与收益**：默认继承SafeLoader的1.1规则，21:00实测为1260；应用时间配置需要字符串。
- **交付及模块**：提供独立明确命名的1.2兼容标量loader预设，统一用于Yaml/EnvSource；yaml_util.Loader resolver策略、Configuration.loader、EnvSource.loader。
- **兼容与依赖**：默认1.1保持；不能宣称已实现完整YAML1.2规范，仅列出bool/整数/sexagesimal解析差异；步骤依赖：无。
- **正常验收**：启用后21:00为str、true为bool、yes按新规则为str，文件/env一致。
- **异常／边界验收**：显式YAML tag、八进制、浮点/NaN、quoted值与输出重新加载一致。
- **原生回归**：test/test_yaml.py、test/test_env.py。

## 11．输出配置值的来源与遮蔽链

- **类型与来源**：增强；[官方#12](https://github.com/beetbox/confuse/issues/12) 与固定源码。
- **原版现状与收益**：resolve/first已有单view来源信息，但无整树带胜出/被遮蔽来源的解释输出。
- **交付及模块**：新增explain树，按完整路径列有效值、来源filename/类别、优先级与shadowed值摘要；core.ConfigView.resolve／first、sources.ConfigSource metadata。
- **兼容与依赖**：不声称原来无provenance基础；尊重redaction，不输出完整env或命令行，说明仅显式来源信息；步骤依赖：07。
- **正常验收**：混合文件、env、CLI的port能解释胜出顺序和默认回退。
- **异常／边界验收**：list索引、标量覆盖、无filename来源、自定义source与敏感字段遮蔽。
- **原生回归**：test/test_views.py、test/test_env.py。

## 12．配置文件包含相邻文件树

- **类型与来源**：增强；[官方#40](https://github.com/beetbox/confuse/issues/40) 与固定源码。
- **原版现状与收益**：set_file可手动堆来源，但YAML内无包含协议、相对解析/循环检测需应用重复实现。
- **交付及模块**：提供显式include配置入口，按声明顺序读相对文件并保留独立source metadata；sources.YamlSource、Configuration.set_file／read、include解析器。
- **兼容与依赖**：默认loader不解析任意新tag；不得用Python对象构造，优先级与include本地路径限定清楚；步骤依赖：11。
- **正常验收**：主文件包含db与feature，来源与路径基准正确且主文件覆盖策略确定。
- **异常／边界验收**：循环/重复包含、缺optional、越过允许根、坏类型/坏文件均给完整链。
- **原生回归**：test/test_yaml.py、test/test_paths.py。

## 13．TOML原生配置来源

- **类型与来源**：增强；[官方#151](https://github.com/beetbox/confuse/issues/151) 与固定源码。
- **原版现状与收益**：现有文件source仅YamlSource，虽可外部tomllib转换但会丢失统一文件元数据/重载路径。
- **交付及模块**：提供TomlSource及显式按format加载入口，复用ConfigSource协议；sources新TomlSource、Configuration.set_file／reload。
- **兼容与依赖**：默认YAML入口保持；Python3.10需可选tomli，3.11+用tomllib，不默猜扩展后执行代码；步骤依赖：06。
- **正常验收**：TOML含嵌套表/Unicode经视图覆盖和Path模板正常使用。
- **异常／边界验收**：非法TOML、根类型、日期值dump策略、来源删除键与缺可选依赖。
- **原生回归**：test/test_yaml.py、test/test_views.py、新增原生TOML source回归。

## 14．可选JSON Schema模板适配器

- **类型与来源**：增强；[官方#166](https://github.com/beetbox/confuse/issues/166) 与固定源码。
- **原版现状与收益**：原生Template系统不直接消费JSON Schema；调用者需自己拼取值与错误路径。
- **交付及模块**：添加可选JSONSchemaTemplate，用合并值验证并把ValidationError转原生带路径异常；templates新adapter、exceptions.ConfigError映射。
- **兼容与依赖**：jsonschema只为可选依赖；默认禁网络取$ref，registry由调用者显式提供，不取代现有Template；步骤依赖：08。
- **正常验收**：对象/数组schema正常返回原值，错误定位servers[1].port。
- **异常／边界验收**：缺可选库、无效schema、多个错误排序、本地$ref和循环schema边界。
- **原生回归**：test/test_validation.py、test/test_valid.py。

## 15．一次报告模板校验问题与未知字段

- **类型与来源**：增强；固定core.py/sources.py/templates.py定义与本地原生配置使用场景。
- **原版现状与收益**：MappingTemplate/Sequence逐项求值遇首错停止；MappingTemplate忽略未声明键。
- **交付及模块**：增加显式strict validation report模式，聚合字段错误并可拒绝未知键；templates.MappingTemplate／Sequence／MappingValues、exceptions报告结构。
- **兼容与依赖**：默认get仍首错；默认未知键保持宽松，report结果不能被误作已验证配置；步骤依赖：无。
- **正常验收**：三个独立坏字段与一个拼写未知键一次列出，顺序稳定、路径精确。
- **异常／边界验收**：嵌套OneOf候选噪声去重、缺required、converter副作用只运行一次、redaction。
- **原生回归**：test/test_validation.py、test/test_valid.py。

## 16．独立且不可变的已验证配置快照

- **类型与来源**：增强；[官方#8](https://github.com/beetbox/confuse/issues/8) 与固定源码。
- **原版现状与收益**：get返回可变AttrDict/list，views继续追踪来源；没有freeze接口冻结一次启动配置。
- **交付及模块**：新增freeze(template)先校验后深复制为只读映射/序列，可在来源重载后稳定读取；core.ConfigView新snapshot入口、templates产物冻结辅助。
- **兼容与依赖**：不改变view惰性和原get返回类型；不把用户任意对象pickle/exec，支持类型边界明确；步骤依赖：08。
- **正常验收**：快照port稳定，原source修改后快照不变，嵌套写入受控拒绝。
- **异常／边界验收**：循环容器、不可冻结对象、默认值别名、None和验证失败无半快照。
- **原生回归**：test/test_views.py、test/test_validation.py。

## 17．原子保存配置到指定文件

- **类型与来源**：增强；[官方#130](https://github.com/beetbox/confuse/issues/130) 与固定源码。
- **原版现状与收益**：dump只返回字符串，文件写入/冲突/替换全由调用者实现，无法通过同一API保存改动。
- **交付及模块**：增加显式save(path,...)，同目录临时文件写/flush后原子替换，允许预期版本冲突检查；Configuration新save入口、dump及来源元数据。
- **兼容与依赖**：绝不隐式写回默认文件；清楚区分full与override保存，保留调用者指定权限策略；步骤依赖：04、05、07。
- **正常验收**：修改值保存后重新载入一致，正常替换不留下临时文件。
- **异常／边界验收**：写满/编码/替换失败保留原文件，外部并发修改拒绝，symlink和目标为目录明确处理。
- **原生回归**：test/test_dump.py、test/test_paths.py。

## 18．作用域内临时覆盖配置

- **类型与来源**：增强；固定core.py/sources.py/templates.py定义与本地原生配置使用场景。
- **原版现状与收益**：set插入来源后没有成对恢复context manager，测试或单次命令必须手动删source。
- **交付及模块**：新增override(mapping)上下文，按来源身份移除自己插入的overlay并支持嵌套；core.RootView.sources、ConfigView／Subview override helper。
- **兼容与依赖**：不重置整个source列表，不撤掉作用域内用户另加来源；不承诺跨线程共享全局配置安全；步骤依赖：02。
- **正常验收**：外层port9000、内层9100，退出内外层逐次回原值。
- **异常／边界验收**：异常退出、同值overlay、嵌套Subview/list路径和来源列表被调用者改动。
- **原生回归**：test/test_views.py。

## 19．按输出宽度选择YAML列表布局

- **类型与来源**：增强；[官方#119](https://github.com/beetbox/confuse/issues/119) 与固定源码。
- **原版现状与收益**：Dumper仅按元素<4决定inline，两个长正则仍挤一行；dump width固定1000。
- **交付及模块**：暴露明确dump layout选项，可按序列估计输出宽度或强制block/flow；yaml_util.Dumper.represent_list、Configuration.dump。
- **兼容与依赖**：默认历史格式保持；不改变配置值或转义规则，不以str长度误当编码字节限；步骤依赖：04、05。
- **正常验收**：两个长regex可输出易读block列表，小短列表仍inline且读回一致。
- **异常／边界验收**：Unicode、nested列表、换行字符串、空序列、注释恢复与redaction。
- **原生回归**：test/test_dump.py、test/test_yaml.py。

## 20．从原生模板生成可编辑配置样例

- **类型与来源**：增强；[官方#86](https://github.com/beetbox/confuse/issues/86) 与固定源码。
- **原版现状与收益**：Template拥有default和required信息，但缺整体配置样例生成器；应用要另维护一份默认YAML。
- **交付及模块**：生成模板默认值/必填占位与结构化说明，用于首次启动初始化，输出不自动覆盖用户文件；templates元信息遍历、Configuration样例生成helper。
- **兼容与依赖**：区分缺省与None，不能捏造required字段有效值；Path基准与Choice候选说明保留；步骤依赖：09。
- **正常验收**：含Mapping/Sequence/Choice/Optional的模板生成可编辑YAML，已有默认值读回校验通过。
- **异常／边界验收**：无默认required、OneOf多种结构、递归模板、自定义Template无元数据需显式提供生成器。
- **原生回归**：test/test_validation.py、test/test_dump.py。

## 独立验收边界

每步的冻结断言由控制端保管，验收时检查候选导入路径、真实输出和业务副作用，累计回归已接受能力；候选删除自己的 tests 或自报成功不能放行。涉及文件只使用合成临时目录，网络或平台特定能力另列预算与环境证据。原生适用基线通过不表示二十步已经实现，也不表示已上线。
