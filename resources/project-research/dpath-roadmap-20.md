# dpath：二十步真实工程迭代路线

固定 [dpath-maintainers/dpath-python@15759d96a006fef5278de731cd263b4d839094c3](https://github.com/dpath-maintainers/dpath-python/tree/15759d96a006fef5278de731cd263b4d839094c3)，详见[单仓审查](./dpath.md)。共 20 步：18 项增强提案、2 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．过滤删除严格受 glob 范围约束（问题修复）

- 来源／场景：https://github.com/dpath-maintainers/dpath-python/issues/207
- 原版现状：delete中的selected分支不要求matched；wanted/*配合值过滤会删除unrelated/y，固定提交实测删除数为2。
- 交付目标：使glob和afilter共同限制删除，计数只包含范围内实际删除项。
- 影响模块：dpath/__init__.py:delete；tests/test_delete.py
- 兼容边界：保留无afilter和列表尾部删除规则；不扩大过滤器对容器的既有调用范围。
- 正常验收：wanted/x与unrelated/y都为1时只删除前者，返回1。
- 异常／边界：全不匹配抛PathNotFound；父子匹配、列表中间空位和多个相同值不越界。
- 原生回归：nose2完整集合；test_delete.py/test_broken_afilter.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．整数字典键的深合并（问题修复）

- 来源／场景：[dpath/__init__.py:merge；README.rst整数键约定](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/__init__.py)
- 原版现状：merge对每个key直接len(key)，{7:{enabled:True}}当前TypeError；类型安全错误路径也直接join原键。
- 交付目标：整数键与字符串键均可深合并，并正确生成含整数路径的类型冲突信息。
- 影响模块：dpath/__init__.py:merge/merger；segments.int_str
- 兼容边界：不把字典整数7改成字符串7；列表索引与字典键保持原类型。
- 正常验收：整数根键及嵌套整数键合并成功，ADDITIVE/REPLACE规则一致。
- 异常／边界：混合键类型、空字符串禁止选项、TYPESAFE冲突路径与布尔键按Python字典语义。
- 原生回归：tests/test_merge.py/test_types.py/test_segments.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．字面量路径模式免除通配转义（增强提案）

- 来源／场景：https://github.com/dpath-maintainers/dpath-python/issues/188
- 原版现状：分段列表能保留斜杠键，但每段仍走fnmatch；x[0]必须写x[[]0]才能精确取值。
- 交付目标：增加显式literal路径对象或匹配模式，让键名中的[]*?按字面量处理。
- 影响模块：dpath/types.py；_split_path；segments.match
- 兼容边界：默认字符串/分段路径仍为现有glob；不把现有通配语义默默改掉。
- 正常验收：a/b键下x[0]可直接精确读写删除，旁边x0不会被选中。
- 异常／边界：空键开关、bytes/Unicode、整数键与字符串数字、混合literal/glob段有明确规则。
- 原生回归：test_get_values.py/test_search.py/test_set.py/test_delete.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．无损返回类型化路径段（增强提案）

- 来源／场景：[dpath/__init__.py:search/yielder；README.rst分段路径场景](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/__init__.py)
- 原版现状：yielded结果通过separator.join拼成字符串；含分隔符的键和整数键类型无法往返。
- 交付目标：新增path_format=segments返回元组路径，供审计和后续精确操作。
- 影响模块：search；segments.walk；dpath/types.py
- 兼容边界：默认返回字符串对保持；不复制或改变结果值引用语义。
- 正常验收：a/b键和普通a/b两层路径返回不同元组；索引保持整数并可回传literal操作。
- 异常／边界：bytes键、负列表索引规范化、不同separator与空字符串键不丢失。
- 原生回归：test_search.py/test_path_get.py；第03步用例
- 真实依赖：03

## 05．循环容器的可解释遍历策略（增强提案）

- 来源／场景：https://github.com/dpath-maintainers/dpath-python/issues/184
- 原版现状：walk递归无祖先身份检测；self字典当前RecursionError，查询方无法获得循环路径。
- 交付目标：新增cycle_policy=error/skip，报告当前路径与最早祖先路径。
- 影响模块：segments.walk/fold/foldm；exceptions.py
- 兼容边界：默认保留旧行为或在独立安全入口启用；同一个共享节点在不同分支出现不能误当循环。
- 正常验收：self/a循环受控报错或跳过，正常共享子树仍在两条路径出现。
- 异常／边界：列表自环、间接环、深层无环对象、yielded中途异常不留下修改。
- 原生回归：test_segments.py/test_search.py/test_set.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．深层查询的深度和节点预算（增强提案）

- 来源／场景：[dpath/segments.py:walk；大配置与不受信任查询场景](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/segments.py)
- 原版现状：每次查询递归遍历全树，无深度/节点上限；一层**可遍历任意多节点。
- 交付目标：增加显式max_depth/max_nodes并给出完整/截断状态，不伪装成无匹配。
- 影响模块：segments.walk；get/search/values；exceptions.py
- 兼容边界：默认无预算限制；get多匹配错误不能被截断悄悄变成唯一结果。
- 正常验收：限定深度时只收集预算内配置项，并明确truncated标志。
- 异常／边界：0/负/非整数参数、恰好边界、宽树、循环策略与generator提前关闭。
- 原生回归：test_segments.py/test_search.py/test_get_values.py
- 真实依赖：05

## 07．编译并复用路径匹配器（增强提案）

- 来源／场景：[dpath/segments.py:match；每请求重复查询同批配置路径](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/segments.py)
- 原版现状：match为每个节点反复规范化glob，公开入口每次拆路径；无稳定可复用编译结果。
- 交付目标：提供compile_path保存段、单个**约束和匹配选项，可供各查询/编辑入口复用。
- 影响模块：segments.match；_split_path；新增编译路径类型
- 兼容边界：默认不共享可变全局缓存；对象不可变，兼容现有单**约束和fnmatch语义。
- 正常验收：同一匹配器用于get/search/set结果等于原字符串路径。
- 异常／边界：非法双**在编译时失败；separator差异、bytes与literal模式不能串用。
- 原生回归：test_segments.py/test_paths.py/test_search.py
- 真实依赖：03

## 08．按旧值和路径转换已有节点（增强提案）

- 来源／场景：https://github.com/dpath-maintainers/dpath-python/issues/153
- 原版现状：set只能把全部匹配节点替换为同一常量，不能根据旧值计算新值。
- 交付目标：新增update回调接收类型化path和旧值，支持显式跳过标记与变更计数。
- 影响模块：dpath/__init__.py:set；segments.foldm
- 兼容边界：不改变set把callable当普通值的既有语义；回调每个初始匹配只调用一次。
- 正常验收：所有servers/*/port按旧值加100，按路径给不同机房设置。
- 异常／边界：回调抛错、父子同时匹配、跳过与返回None区别，禁止循环新匹配。
- 原生回归：test_set.py/test_segments.py
- 真实依赖：04

## 09．批量配置补丁的事务边界（增强提案）

- 来源／场景：[dpath/__init__.py:new/set/delete；一次发布多字段配置场景](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/__init__.py)
- 原版现状：调用方需依次原地修改；中途PathNotFound或回调异常会留下半批结果。
- 交付目标：提供apply_operations批量new/set/delete/update，atomic模式失败保持原文档，返回每操作结果。
- 影响模块：新增批量编辑入口；segments.set/foldm
- 兼容边界：默认单项API保持原地行为；首版限定dict/list，不承诺任意自定义对象回滚。
- 正常验收：先改端口再加label再删除旧项，全部成功一次生效。
- 异常／边界：第二项失败文档原样；重复/父子路径按清单顺序，回调外部副作用不承诺撤销。
- 原生回归：test_new.py/test_set.py/test_delete.py及累计场景
- 真实依赖：08

## 10．列表删除可显式选择紧凑模式（增强提案）

- 来源／场景：[dpath/__init__.py:delete的None占位约定](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/__init__.py)
- 原版现状：中间元素删除以None保留索引，虽为已注明行为，配置清理需要真实缩短数组。
- 交付目标：增加sequence_mode=preserve/compact，紧凑模式按原索引倒序删除匹配元素。
- 影响模块：delete；segments.foldm/make_walkable
- 兼容边界：默认preserve保持；compact必须以原始匹配快照确定索引，不能随移位错删。
- 正常验收：[a,b,c,d]删除b/d得到[a,c]，preserve模式结果仍兼容。
- 异常／边界：连续尾部、全部元素、重复值、父子匹配和嵌套列表各自独立。
- 原生回归：tests/test_delete.py/test_segments.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．创建路径时显式处理空父节点（增强提案）

- 来源／场景：https://github.com/dpath-maintainers/dpath-python/issues/92
- 原版现状：new遇已存在None或标量父节点抛PathNotFound，creator主要负责缺失键，不能声明替换策略。
- 交付目标：增加on_scalar=error/replace及可限定None的规则，允许受控把空配置占位替换为容器。
- 影响模块：new；segments.set/_default_creator
- 兼容边界：默认error保持；不得无提示覆盖已有非空配置，替换策略必须显式。
- 正常验收：a=None时创建a/b成功且留下{"a":{"b":1}}，默认仍拒绝。
- 异常／边界：None位于列表、0/False/空字符串、类型提示、失效creator与部分修改原子模式。
- 原生回归：test_new.py/test_types.py
- 真实依赖：09

## 12．在通配父节点下创建子字段（增强提案）

- 来源／场景：https://github.com/dpath-maintainers/dpath-python/issues/202
- 原版现状：set按约定仅改已有键，new按约定不解释glob；给现有每个服务器新增timeout需手工循环。
- 交付目标：新增new_under(parent_glob,child_path,value)匹配现有容器后创建字面量子路径。
- 影响模块：新增new_under；search/new；类型化路径
- 兼容边界：不改set/new已有语义；只创建匹配父节点下的子字段，不凭空生成通配父节点。
- 正常验收：servers/*下缺timeout的对象均获得30，可选择覆盖或仅缺失时写入。
- 异常／边界：父节点为标量、空匹配、重叠父路径、列表父节点与子键含通配字符。
- 原生回归：test_new.py/test_set.py/test_search.py
- 真实依赖：03, 04, 09

## 13．深合并可隔离源对象引用（增强提案）

- 来源／场景：[dpath/__init__.py:merge的明确引用共享说明](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/__init__.py)
- 原版现状：默认将src节点引用放入dst；实测修改dst列表也改变src，并非未说明的BUG。
- 交付目标：新增copy_source选项，对纳入结果的来源节点深复制并保持内部别名关系。
- 影响模块：merge；segments.set；copy协议
- 兼容边界：默认共享引用不变；首版明确dict/list与可deepcopy对象，复制失败不得隐瞒。
- 正常验收：合并后改dst/a不改变src/a；同源共享子节点关系按说明保留。
- 异常／边界：循环源、custom deepcopy失败、afilter排除节点与大树成本，不承诺恒定内存。
- 原生回归：test_merge.py/test_segments.py
- 真实依赖：05

## 14．按路径声明列表合并策略（增强提案）

- 来源／场景：[dpath/types.py:MergeType；环境配置中plugins与ports策略不同](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/types.py)
- 原版现状：ADDITIVE/REPLACE为整个merge调用统一选项，无法对不同列表字段分别设置。
- 交付目标：增加path_policies，支持append/replace及去重append，规则命中返回可审计路径。
- 影响模块：merge；MergeType；编译路径匹配
- 兼容边界：全局flags继续为默认；重复/同优先级规则应拒绝或明确最具体规则胜出。
- 正常验收：plugins去重追加、ports整表替换，普通字典仍递归合并。
- 异常／边界：空列表、重复复杂对象、非哈希值、跨类型冲突与来源引用策略。
- 原生回归：test_merge.py/test_types.py
- 真实依赖：07, 13

## 15．按列表元素业务键对齐合并（增强提案）

- 来源／场景：[dpath/__init__.py:merge列表仅拼接或替换；服务配置按name合并场景](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/__init__.py)
- 原版现状：两份[{name:east,...}]只能append成重复元素或整表replace，不能按name更新。
- 交付目标：为指定路径增加keyed策略，按显式元素键递归合并并保留目的端顺序。
- 影响模块：merge列表策略；segments.get
- 兼容边界：仅显式路径启用；缺失或重复业务键要报清晰冲突，不凭位置猜测身份。
- 正常验收：east端口更新、west保留、north追加，顺序可预测。
- 异常／边界：键为None、数字/字符串差异、重复键、删除语义不隐含、嵌套列表策略。
- 原生回归：test_merge.py及keyed合成服务配置
- 真实依赖：14

## 16．值冲突可交给显式解析器（增强提案）

- 来源／场景：[dpath/__init__.py:merge类型冲突替换/TYPESAFE错误](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/__init__.py)
- 原版现状：普通值冲突一律src覆盖或类型不符报错，没有(path,dst,src)业务解析钩子。
- 交付目标：增加conflict_resolver，支持保留/替换/明确失败，并返回冲突审计条目。
- 影响模块：merge/merger；新增冲突结果类型
- 兼容边界：默认src覆盖不变；解析器与TYPESAFE的优先级必须明确，不绕过严格类型检查。
- 正常验收：容量配置选较大值、地区冲突显式失败，其余键正常深合并。
- 异常／边界：返回未定义标记、异常、None、父子策略及不可复制值的处理。
- 原生回归：test_merge.py/test_types.py
- 真实依赖：04, 14

## 17．类型安全合并提供原子模式（增强提案）

- 来源／场景：[dpath/__init__.py:merge的TYPESAFE；smoke部分更新观察](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/__init__.py)
- 原版现状：first已改成2后second类型冲突，当前留下部分变更；原API未承诺事务所以按增强处理。
- 交付目标：增加atomic=True先校验/构建再生效，错误含路径且dst/src保持原状。
- 影响模块：merge；复制与冲突预检
- 兼容边界：默认原地顺序保持；自定义容器先拒绝或明示不支持，回调副作用不在事务承诺内。
- 正常验收：多键同类型一次合并成功；后续类型冲突不会保留前面更新。
- 异常／边界：源复制失败、resolver失败、列表策略冲突和循环输入，内存预算显式。
- 原生回归：test_merge.py；smoke的typesafe_partial_change对照
- 真实依赖：13, 16

## 18．单次遍历组合包含与排除路径（增强提案）

- 来源／场景：[dpath/__init__.py:search仅接一个glob和单值afilter](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/__init__.py)
- 原版现状：导出所有端口但排除临时服务器需要多轮search与结果二次编辑，无法声明路径集合。
- 交付目标：新增select(include,exclude)复用编译器单次筛选，支持值结果与路径对结果。
- 影响模块：search；segments.walk；编译路径对象
- 兼容边界：不替换search；排除优先于包含，容器命中不能把已排除子树从父引用带回。
- 正常验收：包含servers/**并排除servers/*/temporary时导出树确实不含临时字段。
- 异常／边界：空包含/空排除、父节点整体命中、列表空位、literal键与预算截断。
- 原生回归：test_search.py/test_segments.py
- 真实依赖：04, 06, 07

## 19．路径缺失和匹配决策的解释结果（增强提案）

- 来源／场景：get的KeyError/ValueError与match的布尔输出；固定源码：[dpath/exceptions.py](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/exceptions.py)。
- 原版现状：调用方只知道没有唯一匹配，不知道在哪层不存在、类型不符或被过滤。
- 交付目标：提供explain_path，返回最深可达段、匹配数量及过滤/预算原因，不改变查询值。
- 影响模块：get/search；segments.match/get；exceptions.py
- 兼容边界：默认错误类型不变；诊断不重新调用有副作用afilter，默认不输出业务值。
- 正常验收：端口字段拼错能定位servers/0的缺失段；多匹配能列路径并受数量上限限制。
- 异常／边界：空键禁止、字面量与glob不同、类型化键、循环跳过与预算耗尽不误判。
- 原生回归：test_get_values.py/test_search.py
- 真实依赖：06, 07, 18

## 20．路径变化集驱动配置同步（增强提案）

- 来源／场景：segments.walk与批量编辑；配置版本审计真实场景；固定源码：[dpath/segments.py](https://github.com/dpath-maintainers/dpath-python/blob/15759d96a006fef5278de731cd263b4d839094c3/dpath/segments.py)。
- 原版现状：已有检索/修改原语，没有将前后JSON-like树转换成可审计增删改路径集合的接口。
- 交付目标：新增changes(before,after)输出类型化新增/删除/替换记录，可送入批量编辑恢复目标。
- 影响模块：新增changes模块；类型化路径与apply_operations
- 兼容边界：首版dict/list；列表按原索引定义稳定移位策略，不引入通用对象图Diff承诺。
- 正常验收：配置v1到v2含新增label/改port/删旧项，changes重放后等于v2。
- 异常／边界：字典键类型、None与不存在、父层替换合并、数组删除顺序与失败不部分写入。
- 原生回归：全部原生nose2集合；前19步累计验收
- 真实依赖：04, 09, 10

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
