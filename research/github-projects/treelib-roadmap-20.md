# Treelib：二十步真实工程迭代路线

冻结 [caesar0301/treelib@83b3b87eaa7c56c9c7b86d19b2eede5252a1b482](https://github.com/caesar0301/treelib/tree/83b3b87eaa7c56c9c7b86d19b2eede5252a1b482)，原版证据见[审查报告](./treelib.md)。前5项是实证行为修复，其余15项为明确增强提案；均未实施，不代表上游承诺。所有交付在同一真实仓库中累计，测试、说明和重试不拆步。

## 01．重命名标识时拒绝覆盖其他节点

- **场景／现状**：编辑商品树把a改名为已有b；update_node先pop旧节点再直接覆盖_nodes[b]，实测节点数减少且根子指针重复。
- **交付／模块**：预检目标标识可用性和可哈希性，原子更新节点、索引与父子指针；`treelib/tree.py:Tree.update_node`、`treelib/node.py:identifier`。
- **兼容**：同标识无操作、原根及子级更新保持；共享多树节点不得只更新单树而破坏其他视图，无法安全改名时明确拒绝。
- **正常／边界验收**：改为新id后所有引用一致；冲突、不可哈希值、属性更新中途失败和多树共享时不丢节点。
- **回归／依赖**：`tests/test_tree.py`、`tests/test_tree_edge_cases.py`、`tests/test_node_comprehensive.py`；标准库，无前置步骤。

## 02．父子映射导入验证全部记录

- **场景／现状**：数据库导出含指向缺失父项的记录；from_map实测只返回可达root，静默丢弃orphan，未对完整输入校验。
- **交付／模块**：挂接前验证根、父引用、环和全部可达，失败提供涉及id，不交付半树；`treelib/tree.py:Tree.from_map`。
- **兼容**：合法乱序映射继续可用；明确不支持森林时拒绝多根，不能静默忽略离线环或孤儿。
- **正常／边界验收**：乱序合法映射全量导入且数量一致；孤儿、自环、与根断开的环、多根和空输入均有明确诊断。
- **回归／依赖**：`tests/test_tree.py`、`tests/test_tree_edge_cases.py`；标准库，无前置步骤。

## 03．映射类工厂尊重Tree子类

- **场景／现状**：业务CatalogTree调用继承的from_map，原版硬编码Tree()，实际返回基类，丢掉扩展行为。
- **交付／模块**：使用cls创建目标并兼容node_class构造契约；`treelib/tree.py:Tree.from_map`、`Tree._clone`的既有扩展惯例。
- **兼容**：普通Tree输出保持；子类必需构造参数必须由明确工厂选项传入，不能猜参数或吞构造异常。
- **正常／边界验收**：无参子类返回同子类并保留覆盖方法；自定义node_class、构造器错误和只要求关键字参数的子类边界清楚。
- **回归／依赖**：`tests/test_tree_comprehensive.py`、`tests/test_tree.py`；标准库，无前置步骤。

## 04．叶树与空树的JSON往返边界

- **场景／现状**：默认to_json对单叶输出JSON字符串，from_json却调用.items，实测AttributeError；空树当前也无明确往返编码。
- **交付／模块**：修正读取端接受自身合法叶表示，定义空树编码及一致错误；`treelib/tree.py:Tree.to_json`、`Tree.from_json`。
- **兼容**：现有含id/data的对象表示继续读取；默认叶表示保留兼容，不把任意标量都猜成有效复杂树。
- **正常／边界验收**：单叶、空树、多层树分别往返；bytes输入、空tag、非法JSON形状、重复id和多根对象明确处理。
- **回归／依赖**：`tests/test_tree_io.py`、`tests/test_tree_edge_cases.py`；标准库，无前置步骤。

## 05．完整序列化保留折叠节点的后代

- **场景／现状**：UI折叠drink后保存整树；to_dict以expanded控制successors，to_json所称整树也遗漏tea，原版已实证。
- **交付／模块**：区分展示剪枝与完整内容序列化，默认整树持久化不依赖expanded，并提供显式旧展示模式；`treelib/tree.py:Tree.to_dict`、`Tree.to_json`。
- **兼容**：show的折叠展示保持；为旧调用者说明行为变更并保留显式展示导出选项，不隐式改节点expanded。
- **正常／边界验收**：任意层折叠仍可完整往返所有id/data；单根折叠、多个折叠层、展示模式和sort选项结果分别验证。
- **回归／依赖**：`tests/test_tree_io.py`、`tests/test_tree_comprehensive.py`；标准库，无前置步骤。

## 06．可选整批原子合并

- **场景／现状**：merge逐个paste子树，后一个id冲突时前面的new已经留下；没有整批事务保证，按新能力设计。
- **交付／模块**：增加显式atomic合并模式，预检全部id/目的节点再提交关系和节点；`treelib/tree.py:Tree.merge`、`Tree.paste`。
- **兼容**：原默认语义保留；不回滚业务data对象的外部副作用；deep/shallow共享策略不变。
- **正常／边界验收**：合法多分支全量合并，末分支冲突时原树结构和指针全不变；空目标、自合并、子类及数据复制失败有边界。
- **回归／依赖**：`tests/test_tree.py`、`tests/test_tree_comprehensive.py`；标准库，无前置步骤。

## 07．版本化完整节点快照协议

- **场景／现状**：同tag节点和折叠状态需恢复；当前tag作字典键的JSON是展示树格式，没有版本号、expanded和节点扩展属性契约。
- **交付／模块**：新增扁平节点记录快照，含schema版本、root、id/tag/parent/order/expanded和明确数据字段，加载先校验；`treelib/tree.py`、`treelib/node.py`。
- **兼容**：旧to_json/from_json继续存在；不是把当前with_identifier开关重命名；禁止把任意Python类名当自动构造器。
- **正常／边界验收**：同tag兄弟、折叠和顺序完整恢复；未知版本、重复id、缺root、扩展字段和不可表达data有稳定错误。
- **回归／依赖**：`tests/test_tree_io.py`、`tests/test_node_comprehensive.py`；标准库，无前置步骤。

## 08．业务数据的显式编码与还原

- **场景／现状**：节点data含Decimal或日期；to_json没有serializer/decoder选项，只能预先改写data或自行实现输出。
- **交付／模块**：新增可组合data codec，编码与还原使用显式注册表和版本标签，不改实际节点对象；`treelib/tree.py:Tree.to_json`、`Tree.from_json`。
- **兼容**：默认JSON类型语义不变；不执行存储中的任意类名，未知类型明确报错；精度策略调用方选择。
- **正常／边界验收**：金额与带时区时间往返等价；未知codec、冲突标签、循环data、编码器异常和None有边界。
- **回归／依赖**：`tests/test_tree_io.py`；标准库，无前置步骤，可供第07步复用但不强依赖。

## 09．CSV节点记录进出

- **场景／现状**：办公表格以id,parent,tag与业务列保存；已有from_map只接内存映射，不提供CSV格式、列映射或流式读取。
- **交付／模块**：新增CSV读写适配器，明确列名、空parent和数据转换，保留兄弟顺序；`treelib/tree.py:Tree.from_map`旁的独立I/O模块。
- **兼容**：不从tag猜id，不把普通空业务值等同根标记；失败整批验证，CSV方言显式。
- **正常／边界验收**：乱序表格正确建树，写出再读保留字段和顺序；BOM、引号、逗号、换行、重复列与坏父引用有断言。
- **回归／依赖**：`tests/test_tree_io.py`、`tests/test_tree_edge_cases.py`；标准库csv，无强制前置步骤。

## 10．按显示路径解析节点

- **场景／现状**：用户选择“商品/饮品/茶”；已有id字典查找和rsearch不等于tag路径解析，没有resolve_path入口。
- **交付／模块**：提供明确路径段解析器，声明绝对/相对、转义和重名策略，返回实际Node/id；`treelib/tree.py:Tree.children`、`Tree.get_node`旁的新帮助器。
- **兼容**：id查找不变；默认段为字面匹配，重名拒绝或显式返回所有，不悄悄选任意项。
- **正常／边界验收**：相同tag不同分支可按路径区分；分隔符在tag内、根名缺失、重名、Unicode及空树有稳定行为。
- **回归／依赖**：`tests/test_tree.py`、`tests/test_tree_edge_cases.py`；标准库，无前置步骤。

## 11．将输出过滤与分支剪枝分开

- **场景／现状**：隐藏分类标题但仍显示其商品后代；expand_tree当前filter=False会剪掉整个后代，不能只隐藏当前项。
- **交付／模块**：新增独立emit_filter与prune选项，明确深/广/之字形各模式的访问语义；`treelib/tree.py:Tree.expand_tree`。
- **兼容**：保留旧filter剪枝；参数冲突明确拒绝；过滤器调用次数稳定，不改变存储结构。
- **正常／边界验收**：父项不输出但可见后代仍遍历；根被隐藏、剪枝优先、sort、回调错误和无命中均验证。
- **回归／依赖**：`tests/test_tree.py`、`tests/test_tree_comprehensive.py`；标准库，无前置步骤。

## 12．原生后序遍历模式

- **场景／现状**：按子级结果汇总库存或按叶到根释放业务对象；当前公开DEPTH/WIDTH/ZIGZAG，无POSTORDER。
- **交付／模块**：新增惰性后序模式，保持兄弟排序、过滤和根选择约定；`treelib/tree.py:Tree.expand_tree`。
- **兼容**：旧常量值及默认深序不变；不使用递归避免把深树汇总局限在Python栈深。
- **正常／边界验收**：所有子节点先于父节点输出且只一次；单节点、宽/深树、过滤、非法模式和提前停止消费有边界。
- **回归／依赖**：`tests/test_tree.py`、`tests/test_tree_performance.py`；标准库，无前置步骤。

## 13．宽树遍历避免重复列表复制

- **场景／现状**：expand_tree宽序反复queue[1:]+expansion，源码可见与宽度有关的拷贝开销；这属于性能增强，不声称当前结果错误。
- **交付／模块**：改用适合各遍历模式的deque/栈，保持当前输出与惰性，提供可复核规模基准；`treelib/tree.py:Tree.expand_tree`。
- **兼容**：排序规则和回调次序保持；不靠关闭sort更改默认结果；性能结论需相同数据和运行环境。
- **正常／边界验收**：一万节点宽树输出与旧实现逐项相同、增长趋势改善；极端宽/深组合、早停和过滤开销分开测量。
- **回归／依赖**：`tests/test_tree_performance.py`、`tests/test_tree.py`；标准库collections，无前置步骤。

## 14．持久兄弟顺序编辑

- **场景／现状**：用户调整目录位置并需sort=False后续读取保持；当前可在输出时排序，也可直接改Node指针，但缺Tree级顺序编辑与预检。
- **交付／模块**：新增按id列表完整重排与位置移动入口，保证成员集合不变及多树作用域明确；`treelib/tree.py`、`treelib/node.py:Node.set_successors`。
- **兼容**：输出sort=True继续按原规则排序；新编辑只影响当前tree_id，不改变其他树视图顺序。
- **正常／边界验收**：重排后show/expand_tree(sort=False)/快照顺序一致；遗漏、重复、外来id、空子集和共享节点有边界。
- **回归／依赖**：`tests/test_tree.py`、`tests/test_node_comprehensive.py`；标准库，无前置步骤。

## 15．只读结构一致性报告

- **场景／现状**：应用从本地旧存档迁移或使用nodes公开映射后，需要检查关系是否一致；没有validate_structure入口。
- **交付／模块**：输出root有效性、父子双向、重复指针、环、不可达节点及当前tree_id关系诊断，不自动修改；`treelib/tree.py:Tree.nodes`、`treelib/node.py`。
- **兼容**：报告仅描述实际结构；其他tree_id的合法关系不误报；不能把未验证data称为结构错误。
- **正常／边界验收**：健康树零诊断，合成缺父/重复子指针各定位准确；空树、大深度、共享视图和自定义Node有边界。
- **回归／依赖**：`tests/test_tree_edge_cases.py`、`tests/test_node_comprehensive.py`；标准库，无前置步骤。

## 16．共享视图关系的显式生命周期

- **场景／现状**：长期使用subtree浅视图，Node按每个tree_id保存指针；没有明确close_view来移除已不用视图的关系。
- **交付／模块**：提供只清理当前树作用域关系的释放入口和上下文协议，明确关闭后可用操作；`treelib/tree.py:Tree.subtree`、`treelib/node.py:Node.reset_pointers`。
- **兼容**：不删除其他树节点或业务data，不把正常子树删除与视图释放混为一谈；默认已有树不会自动关闭。
- **正常／边界验收**：创建并关闭多个视图后原树可正常遍历，关闭视图指针移除；重复关闭、共享子树、异常退出和原树先关闭均明确定义。
- **回归／依赖**：`tests/test_tree_comprehensive.py`、`tests/test_node_comprehensive.py`；标准库，无前置步骤。

## 17．独立节点与共享业务数据的复制模式

- **场景／现状**：Tree(tree=old,deep=False)共享整个Node，deep=True又深拷贝全部data；大数据分类编辑需要第三种模式。
- **交付／模块**：新增明确复制策略：复制节点/指针但可共享或按函数复制data，支持子类节点工厂；`treelib/tree.py:Tree.__init__`、`Tree._clone`。
- **兼容**：旧deep布尔语义保持；新策略和deep同时给出时拒绝矛盾参数；不能假称共享data互不影响。
- **正常／边界验收**：新副本改tag或expanded不影响原节点，data身份按声明共享；自定义Node、不可拷贝data、memo与视图指针有边界。
- **回归／依赖**：`tests/test_tree_comprehensive.py`、`tests/test_node_comprehensive.py`；标准库，无前置步骤。

## 18．粘贴时的显式标识映射

- **场景／现状**：复用带固定业务id的分类模板；paste遇任意重复id只报错，调用方需重建整棵输入树。
- **交付／模块**：新增独立paste_copy，接受id映射或命名空间函数，先验证新id和父子关系，返回完整映射；`treelib/tree.py:Tree.paste`。
- **兼容**：原paste默认拒绝冲突不变；不修改输入树，不悄悄改已存在业务id；共享data策略明确。
- **正常／边界验收**：同模板复制两次在两个命名空间中结构正确；映射不唯一、空映射、根冲突、自粘贴与回调失败整体拒绝。
- **回归／依赖**：`tests/test_tree.py`、`tests/test_tree_comprehensive.py`；标准库，无强制前置步骤，可复用第17步复制策略。

## 19．有容量边界的树编辑历史

- **场景／现状**：本地目录编辑器希望撤销/重做结构调整；没有历史API，应用自行存整树快照成本较大。
- **交付／模块**：提供显式编辑记录器，对add/remove/move/reorder及受管属性变更记录可逆操作，容量与checkpoint清楚；`treelib/tree.py`及新增历史模块。
- **兼容**：默认不记录；直接改任意data内部内容不承诺撤销；撤销遇外部结构变动要报前置条件不符，不覆盖新工作。
- **正常／边界验收**：连续多种编辑撤销再重做得到相同结构；容量淘汰、分支历史、失败编辑、自定义节点和复合操作有边界。
- **回归／依赖**：`tests/test_tree_comprehensive.py`、`tests/test_tree_edge_cases.py`；标准库，无强制前置步骤。

## 20．两节点间的公共祖先与路径

- **场景／现状**：分类迁移界面需显示从原类目到目标类目的路径；已有rsearch/ancestor但无path_between或最近公共祖先帮助器。
- **交付／模块**：新增同树两id的LCA和有序路径查询，返回节点标识并可只读计算距离；`treelib/tree.py:Tree.rsearch`、`Tree.ancestor`旁的关系帮助器。
- **兼容**：不重复实现已有单节点父链；不把tag相同当同节点；不扩展成任意图最短路径。
- **正常／边界验收**：兄弟、祖孙和根两端路径方向正确；同节点、缺id、断开结构与共享多树节点只依据当前tree_id判断。
- **回归／依赖**：`tests/test_tree.py`、`tests/test_tree_edge_cases.py`；标准库，无前置步骤。
