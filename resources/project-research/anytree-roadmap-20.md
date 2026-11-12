# AnyTree：二十步真实工程迭代路线

固定 [c0fec0de/anytree@2e0a1b956172654d75aff93277ce3d883355e0bf](https://github.com/c0fec0de/anytree/tree/2e0a1b956172654d75aff93277ce3d883355e0bf)，证据见[单仓审查](./anytree.md)。第18步为原版实证的共享状态修复，其余19项为明确的本地增强提案，尚未实施，不代表上游接受。已存在的通配 **、属性过滤、commonancestors、左右兄弟查询、Mermaid自定义边和children整体重排不当作新增。

## 01．深树的无递归遍历与序列化

- **场景／原版**：深层分类树超过默认递归深度；原生PreOrderIter递归调用，1100层实测RecursionError。此处按扩大支持规模的增强处理。
- **交付与模块**：用显式栈贯通前后序、渲染及字典进出路径，保持遍历顺序；`src/anytree/iterators/preorderiter.py`、`postorderiter.py`、`render.py`、`importer/dictimporter.py`、`exporter/dictexporter.py`。
- **兼容／依赖**：不修改全局recursionlimit；filter/stop/maxlevel和钩子次序保持；标准库，无前置步骤。
- **正常／边界验收**：5000层链可遍历和字典往返；单节点、宽树、stop截断和回调异常不泄漏栈或重复节点。
- **原生回归**：`tests/test_iterators.py`、`tests/test_render.py`、`tests/test_dictimporter.py`、`tests/test_dictexporter.py`。

## 02．可回滚的多节点编辑事务

- **场景／原版**：一次调整分类结构中某挂接钩子拒绝操作；原版移动先detach，pre_attach失败后节点已离开旧父级，已记录这个现有语义。
- **交付与模块**：新增显式编辑事务，预检环与类型、保存结构变化并在应用失败时恢复父子和顺序；`src/anytree/node/nodemixin.py`、`lightnodemixin.py`。
- **兼容／依赖**：默认parent赋值语义不变；不承诺回滚用户钩子外部副作用；事务失败恢复策略错误单独报告；标准库，无前置步骤。
- **正常／边界验收**：多次移动整体成功，末项拒绝时全部结构复原；跨树、重复子级、环、嵌套事务和恢复钩子失败有确定结果。
- **原生回归**：`tests/test_node_attach_detach.py`、`tests/test_node_integrity.py`、`tests/test_lightnode.py`。

## 03．无序父子记录表导入

- **场景／原版**：数据库导出id/parent_id行乱序；DictImporter只接受已经嵌套的children字典，调用者需自己建索引。
- **交付与模块**：新增平面记录导入器，先索引和校验，再按明确顺序挂接，保留业务属性；`src/anytree/importer/dictimporter.py`与新增同层导入模块。
- **兼容／依赖**：保留原嵌套协议；id与显示name分开；失败不交付半树；标准库，无前置步骤。
- **正常／边界验收**：父记录晚到仍正确建树；重复id、孤儿、循环、多个根和空输入按策略处理，不静默漏行。
- **原生回归**：`tests/test_dictimporter.py`、`tests/test_node_integrity.py`。

## 04．分类路径行导入及属性合并

- **场景／原版**：表格以“商品/饮品/茶”路径表达层级，没有id/parent_id；现有导入器不接受路径行。
- **交付与模块**：新增路径段行导入，复用公共前缀，声明重复叶属性合并／冲突与空段策略；`src/anytree/importer/`、`node/node.py`。
- **兼容／依赖**：显式段序列可包含字面分隔符；不把同名不同路径的节点合并；标准库，无前置步骤，不依赖第03步。
- **正常／边界验收**：两条共享“商品/饮品”的行构成正确分支并保留各叶属性；空行、前缀也是叶子、重复路径冲突和Unicode有断言。
- **原生回归**：`tests/test_dictimporter.py`、`tests/test_node_sep.py`。

## 05．带属性复制策略的子树克隆

- **场景／原版**：复用分类模板但保留日期／集合属性；可用copy或字典往返，尚无明确clone API及节点映射。
- **交付与模块**：提供克隆帮助器，声明浅/深/自定义属性复制和Symlink目标策略，返回旧新节点对应表；`src/anytree/util/__init__.py`、`node/symlinknodemixin.py`。
- **兼容／依赖**：不擅自复制父级与缓存私有字段；支持调用方节点工厂，无法复制的业务属性明确报错；标准库，无前置步骤。
- **正常／边界验收**：克隆子树修改可变业务属性不影响原树，顺序与类型按声明保持；自定义节点、共享属性、外部链接和copy回调异常有边界。
- **原生回归**：`tests/test_node.py`、`tests/test_node_symlink.py`、`tests/test_util.py`。

## 06．稳定的子级插入与区间重排

- **场景／原版**：编辑分类目录时只插入一项或移动连续范围；现有children setter可手工重建全部列表，没有完整的局部编辑契约。
- **交付与模块**：新增按位置/参照兄弟的插入和同父连续区间移动帮助器，预检后一次变更；`src/anytree/node/nodemixin.py`、`util/__init__.py`。
- **兼容／依赖**：不把已有整体children重排当新增；显式声明索引与跨父情况，原setter保持；标准库，无前置步骤。
- **正常／边界验收**：将中间区间移到开头且相对次序保留；负索引、同位置、重复节点、祖先插入和钩子触发次数稳定。
- **原生回归**：`tests/test_node_attach_detach.py`、`tests/test_util.py`。

## 07．保持身份的换根操作

- **场景／原版**：把组织树的某部门改为视图根节点；现有可逐个parent赋值，没有一次换根及顺序约定。
- **交付与模块**：新增reroot帮助器，先冻结原路径再翻转父子边，保持节点对象和非路径子树；`src/anytree/util/__init__.py`、`node/nodemixin.py`。
- **兼容／依赖**：不改节点业务属性，不把目标子树单独detach当换根；异常回滚范围明确；标准库，无前置步骤。
- **正常／边界验收**：链中节点换根后所有节点只出现一次且旁支保留；原根、叶、跨树、链接节点与钩子拒绝不形成环。
- **原生回归**：`tests/test_util.py`、`tests/test_node_integrity.py`、`tests/test_node_attach_detach.py`。

## 08．按业务键生成与应用树差异

- **场景／原版**：比较两版分类方案并生成可审查修改；没有tree_diff/patch公开入口，调用者只能自行对比遍历结果。
- **交付与模块**：新增按稳定业务键的添加、删除、移动、排序和属性修改差异及带前置条件的应用；`src/anytree/util/`、`exporter/dictexporter.py`。
- **兼容／依赖**：键函数由调用方提供，不用对象id跨序列化；属性比较/复制策略显式；标准库，无强制前置步骤。
- **正常／边界验收**：应用A→B差异后结构、顺序与选定属性等价B；重复键、旧版本前置不符、父子删除和循环补丁整体拒绝。
- **原生回归**：`tests/test_util.py`、`tests/test_dictexporter.py`、`tests/test_node_integrity.py`。

## 09．保留命中祖先链的裁剪副本

- **场景／原版**：搜索结果仍需显示分类上下文；现有filter_/stop可控制输出，但不返回保留最小祖先闭包的新树。
- **交付与模块**：提供pruned_copy，选择命中项并按策略包含祖先/后代，复用明确克隆策略；`src/anytree/search.py`、`util/__init__.py`。
- **兼容／依赖**：不修改原树，区别于原地删除；依赖第05步公开克隆契约，标准库。
- **正常／边界验收**：两片命中叶及公共祖先只复制一次；无命中、根命中、链接、谓词抛错和属性共享规则有边界。
- **原生回归**：`tests/test_search.py`、`tests/test_util.py`、`tests/test_node_symlink.py`。

## 10．可选兄弟业务键唯一约束

- **场景／原版**：可寻址分类树不允许同父重复name；原版同名兄弟合法，当前无可复用唯一约束策略。
- **交付与模块**：提供可选NodeMixin策略，覆盖构造、移动、批量children赋值及受管名称变更；`src/anytree/node/nodemixin.py`、`node/node.py`。
- **兼容／依赖**：默认仍允许同名；自定义任意属性原位写入无法自动观测时明确要求受管接口，不假装全局强制；标准库，无前置步骤。
- **正常／边界验收**：唯一策略下重复挂接提前拒绝且旧结构保留；不同父同名、大小写规范化、None键、批量内部冲突和移动到自己原父有断言。
- **原生回归**：`tests/test_node.py`、`tests/test_node_attach_detach.py`、`tests/test_node_integrity.py`。

## 11．节点属性规则与批量验证报告

- **场景／原版**：库存树每节点有单位与非负quantity；可写自定义Node类验证，原导入器没有复用规则和路径化错误报告。
- **交付与模块**：新增可选节点规则集合和只读整树验证，报告节点路径、属性与规则；与导入前预检对接；`src/anytree/importer/dictimporter.py`、`node/node.py`及新增规则模块。
- **兼容／依赖**：默认AnyNode任意属性保持；不自动改变类型或运行任意表达式；标准库，无前置步骤。
- **正常／边界验收**：有效库存树通过，多个节点错误一次完整定位；缺失/None、bool/int、用户谓词异常和重名路径用稳定标识区分。
- **原生回归**：`tests/test_dictimporter.py`、`tests/test_node.py`、`tests/test_search.py`。

## 12．无虚拟业务根的森林对象

- **场景／原版**：分类表有多个真正根，调用方不希望伪造一个业务根；当前节点模型一棵树一个根，森林只能自己保存list。
- **交付与模块**：增加轻量Forest包装器，维护有序互不重叠根、统一遍历和字典/JSON进出；`src/anytree/__init__.py`、`importer/`、`exporter/`。
- **兼容／依赖**：不改变Node.root；森林不是多父DAG；重叠根明确拒绝，不隐式detach；标准库，无前置步骤。
- **正常／边界验收**：两个根独立进出且遍历顺序稳定；空森林、同根重复、祖先与后代同时加入、根被外部重新挂接都有策略。
- **原生回归**：`tests/test_iterators.py`、`tests/test_dictimporter.py`、`tests/test_jsonexporter.py`。

## 13．进入与退出配对的遍历事件

- **场景／原版**：边遍历边输出层级文档，需知道何时闭合某节点；当前分别提供前序/后序，但无单次遍历enter/leave事件序列。
- **交付与模块**：新增显式栈事件迭代器，含节点、深度及enter/leave，过滤和剪枝语义一致；`src/anytree/iterators/abstractiter.py`及新增同层事件迭代器。
- **兼容／依赖**：原迭代器不变；没有新增格式解析或业务依赖；标准库，可复用第01步栈机制但不强制。
- **正常／边界验收**：事件可直接拼成正确开闭合分类XML且只遍历一次；空子级、stop、maxlevel、中途停止消费与深树保持配对约定。
- **原生回归**：`tests/test_iterators.py`、`tests/test_render.py`。

## 14．按字面路径段解析节点

- **场景／原版**：节点名称含斜杠或字面星号；Resolver现有get把字符串split(separator)，a/b作为单节点名称无法按同名字符串访问。
- **交付与模块**：新增接收明确路径段序列的解析入口，将绝对/相对与父级指令作为显式选项；`src/anytree/resolver.py:Resolver`。
- **兼容／依赖**：旧字符串和glob语义不变；段模式默认字面匹配，不把含**文本自动当通配；标准库，无前置步骤。
- **正常／边界验收**：名称a/b、..、*均可按字面段定位；空名称、不同separator、绝对根、大小写模式和缺失节点错误保持明确。
- **原生回归**：`tests/test_resolver.py`、`tests/test_node_sep.py`。

## 15．重名路径的歧义诊断

- **场景／原版**：同父有两个same节点；Resolver.get实测返回第一个，应用希望识别错误配置。
- **交付与模块**：为解析器新增显式歧义策略：保留first、要求unique或返回所有候选，并报告冲突层级；`src/anytree/resolver.py`。
- **兼容／依赖**：默认first不变；glob已有多结果能力保留；不是强制兄弟唯一约束，独立于第10步；标准库，无前置步骤。
- **正常／边界验收**：unique模式对重复same报歧义，对单一结果成功；忽略大小写碰撞、根冲突、relax与多层部分命中不误放行。
- **原生回归**：`tests/test_resolver.py`、`tests/test_search.py`。

## 16．树变更感知的可选搜索缓存

- **场景／原版**：反复查询可编辑分类树；cachedsearch仅以参数做可选fastcache LRU，没有树代次。当前未安装fastcache，未宣称已复现错误命中。
- **交付与模块**：新增可观测结构代次的缓存适配器，说明受管属性变更的失效方式与清理入口；`src/anytree/cachedsearch.py`、`node/nodemixin.py`、`search.py`。
- **兼容／依赖**：原无缓存回退行为保持；不承诺识别任意外部可变属性的原位修改；允许调用方显式invalidate；标准库后端可替代可选fastcache。
- **正常／边界验收**：缓存查询后添加/移动节点，下次结果反映新树；属性规则变化、detach、不同树同条件、容量淘汰与清理各有断言。
- **原生回归**：`tests/test_cachedsearch.py`、`tests/test_search.py`、`tests/test_node_attach_detach.py`；无前置步骤。

## 17．轻量槽位节点的显式属性导出协议

- **场景／原版**：使用LightNodeMixin节省内存；DictExporter访问__dict__，实际纯slots节点抛AttributeError。
- **交付与模块**：增加明确属性提供器协议，支持slots和property节点并排除结构私有槽；`src/anytree/exporter/dictexporter.py`、`node/lightnodemixin.py`。
- **兼容／依赖**：普通__dict__导出保持；不自动读取所有property造成业务副作用；调用者声明字段与读取策略；标准库，无前置步骤。
- **正常／边界验收**：轻量name/quantity树正确导出并可配合原生导入器还原；继承slots、未赋值槽、property抛错、弱引用和结构槽不泄漏。
- **原生回归**：`tests/test_lightnode.py`、`tests/test_dictexporter.py`、`tests/test_jsonexporter.py`。

## 18．JSON导出不污染共享字典导出器

- **场景／原版**：共用DictExporter分别导出摘要和全量；JsonExporter(maxlevel=1)直接把共享实例maxlevel改成1，下一次默认导出丢掉子树，原版实证。
- **交付与模块**：将本次深度覆盖限定在当前调用，保留传入导出器配置；`src/anytree/exporter/jsonexporter.py:JsonExporter._export`、`dictexporter.py`。
- **兼容／依赖**：保持JSON maxlevel实际效果；不深拷贝任意用户callable；自定义导出器协议和并发重用边界要明确；标准库，无前置步骤。
- **正常／边界验收**：摘要仅根，随后共享DictExporter仍全量且maxlevel原值未变；自定义子类、原来已有深度、异常退出和连续两种深度都有回归。
- **原生回归**：`tests/test_jsonexporter.py`、`tests/test_dictexporter.py`。

## 19．有宽度预算与省略标记的渲染

- **场景／原版**：窄终端浏览宽分类树；RenderTree有maxlevel和childiter但无内置宽度、每级数量和准确省略说明。
- **交付与模块**：新增显式渲染预算，按显示宽度截断并给出子级省略数量，支持多行属性；`src/anytree/render.py:RenderTree`。
- **兼容／依赖**：默认完整输出不变；不把调用方childiter已删掉的节点计入可知总数；Unicode显示宽度可固定可选wcwidth版本。
- **正常／边界验收**：中文及ASCII混合输出每行不超宽，省略数准确；组合字符、emoji、极小预算、多行内容与自定义style可预测。
- **原生回归**：`tests/test_render.py`；可选wcwidth，无前置步骤。

## 20．保留结果映射的子树聚合

- **场景／原版**：逐分类计算库存总额或叶数量；当前可手写PostOrderIter，但没有一次计算、每节点可访问结果的fold工具。
- **交付与模块**：新增只读后序fold，聚合器接节点和有序子结果，返回按节点身份的结果映射；`src/anytree/util/__init__.py`、`iterators/postorderiter.py`。
- **兼容／依赖**：不把结果隐式写入任意节点属性；链接是否展开明确，默认只沿children；标准库，无前置步骤。
- **正常／边界验收**：库存树每层总价和叶数量正确，原节点不变；空子级、负权值、聚合器抛错、共享链接与深树内存预算有断言。
- **原生回归**：`tests/test_util.py`、`tests/test_iterators.py`。
