# Sorted Containers 二十步迭代研究路线

固定[grantjenks/python-sortedcontainers@3ac358631f58c1347f1d6d2d92784117db0f38ed](https://github.com/grantjenks/python-sortedcontainers/tree/3ac358631f58c1347f1d6d2d92784117db0f38ed)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已存在MutableSequence继承、SortedDict union、key/bisect_key/irange_key、视图按索引切片删除、set代数、负索引、copy和pickle，不重复列为新能力。反向key下irange遵循排序键顺序，未据旧issue把该设计误称缺陷。

## 01．比较或key异常后保持容器内部一致

- **类型／来源与场景**：bug_fix；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；正常导入一条不可比较数据并捕获错误后，容器仍要可继续使用。
- **原版现状／替代**：SortedSet.add先修改_set再排序，实跑add字符串到int集合报错后成员多x但顺序列表无x；SortedDict.setdefault也出现len2但迭代1键。
- **交付与模块**：对单次写入/批量更新的比较与key阶段先验证或可靠回滚，覆盖list/set/dict所有同步索引。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：异常类型原样传播；单次操作失败不留半条数据；不承诺任意有副作用用户key可回滚外部状态。
- **正常验收**：错误后len/contains/iteration/_check一致，合法后续写入成功。
- **异常／边界验收**：key抛错、hash抛错、bulk大分支、空容器和生成器异常，不只修一个setdefault入口。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sorteddict.py`、`tests/test_coverage_sortedset.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 02．集合运算符尊重反向分派协议

- **类型／来源与场景**：bug_fix；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedset.py)；应用的范围对象实现__rand__，希望接管与有序集合求交。
- **原版现状／替代**：__and__直接别名intersection，对不可迭代对象先TypeError，反向对象未获机会。
- **交付与模块**：运算符独立判断不支持类型并返回NotImplemented，方法式intersection仍按iterable契约。；`src/sortedcontainers/sortedset.py`。
- **兼容边界**：保留受支持iterable扩展；不能吞掉合法迭代器内部抛出的TypeError。
- **正常验收**：自定义Reflected的__rand__接管，普通set/list求交不变。
- **异常／边界验收**：四类二元及反向运算、两边均不支持、迭代中异常与in-place路径。
- **原生回归**：`tests/test_coverage_sortedset.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 03．相同排序键可选择左侧或右侧插入

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；相同优先级任务有时希望新任务在前、有时保持先来先到。
- **原版现状／替代**：add始终bisect_right，样例first/second/third保持到达顺序，没有side参数。
- **交付与模块**：提供明确add_left/add_right或side选项，同时返回/定义同键位置。；`src/sortedcontainers/sortedlist.py`。
- **兼容边界**：默认右插保持；不开放破坏排序的任意insert。
- **正常验收**：三条同key记录按指定side插入，跨块仍正确。
- **异常／边界验收**：全部相同key、空列表、key相同值不相等、边界块拆分与重复值。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 04．显式刷新已变排序键的元素

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；业务对象的rank经明确更新后，需要重新放入有序索引。
- **原版现状／替代**：排序键要求存储期间稳定；修改后缓存仍旧，实跑顺序rank3/2；可重建整个容器。
- **交付与模块**：增加refresh_at(index)或带旧键的refresh入口，按已存索引删除再重插。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：不把违反现有稳定键前提称原版缺陷；不能用已变新键搜索旧位置。
- **正常验收**：修改rank后显式刷新恢复顺序、值/成员与其他对象不变。
- **异常／边界验收**：同键重复值、index失效、refresh失败回滚、hash变化对象仍明确不支持。
- **原生回归**：`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sortedset.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 05．以新key函数原子重建排序策略

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；本地列表在名称排序和优先级排序间切换。
- **原版现状／替代**：key只读无rekey；调用方必须创建新容器并替换引用。
- **交付与模块**：新增rekey(new_key)或sorted_copy(key=...)，统一重算缓存并在成功后替换索引。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：与刷新单个对象区分；默认原容器策略不自动改变，公开选择原地/副本。
- **正常验收**：切换后顺序正确，容器类型/内容保持，所有代理bisect方法绑定新索引。
- **异常／边界验收**：key错误不污染旧状态、None策略、同键、空容器和copy/pickle。
- **原生回归**：`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sortedset.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 06．提供floor和ceil等相邻值查询

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；时间表寻找某时刻最近的前一项和后一项。
- **原版现状／替代**：只有bisect+索引的组合，没有floor/ceil/lower/higher。
- **交付与模块**：增加四种相邻查询及SortedDict对应item返回，统一缺项策略。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：尊重排序key定义的顺序；None可为合法值时不用None充当唯一缺项哨兵。
- **正常验收**：1/3/5中floor4=3、ceil4=5，等值和严格邻居符合定义。
- **异常／边界验收**：空容器、两端无邻居、反向key、重复key和显式default。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sortedset.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 07．按键区间批量删除或取出元素

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；一次移除时间窗中的全部计划并保留被移除项供撤销。
- **原版现状／替代**：可bisect后del切片，SortedDict.keys/items/values切片删除已经存在；没有直接值边界入口。
- **交付与模块**：增加pop_range/remove_range统一值边界、inclusive与返回类型，复用批量块删除。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：不把已有视图切片删除称新增；返回项遵循原排序，反向只影响返回顺序。
- **正常验收**：移除[2,4)只删2/3，返回有序副本且其余索引一致。
- **异常／边界验收**：空区间、重复值/键、无界、相同端点、跨块和key函数。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sortedset.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 08．同策略有序输入采用线性合并路径

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；合并两个已有排好序的大型本地结果，避免再次全排序。
- **原版现状／替代**：SortedSet.union重新构造，update大分支重排；功能已正确，暂无本轮速度承诺。
- **交付与模块**：增加可验证策略一致的merge/update_sorted入口，以归并处理重叠/不相交数据并构建块。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`。
- **兼容边界**：未证明策略一致时走原路径；支持明确有序单次流但需校验顺序；不只调常数阈值。
- **正常验收**：不相交及交错输入得到和参考sort/union一致结果，比较次数体现线性边界。
- **异常／边界验收**：同键稳定性、去重、key身份不同、乱序输入、迭代异常和内存预算。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sortedset.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 09．SortedList提供保留重复次数的多重集代数

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；对有重复SKU的两个订货批次求差和交集。
- **原版现状／替代**：SortedSet已有集合代数但会去重，SortedList没有multiset union/intersection/difference。
- **交付与模块**：增加以出现次数定义的多重集操作，允许不可hash但可比较值。；`src/sortedcontainers/sortedlist.py`。
- **兼容边界**：不改变+拼接后排序；对key相同但值不等明确分组规则。
- **正常验收**：[a,a,b]与[a,b,b]交集[a,b]、差[a]，并集按声明max或sum。
- **异常／边界验收**：空/全重复、不可hash对象、不同key策略、值相等协议异常。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 10．提供按工厂创建缺省值的有序映射

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sorteddict.py)；本地按日期累计计数或列表，需要defaultdict式工厂。
- **原版现状／替代**：没有SortedDefaultDict；SortedDict.setdefault需要调用方先构造默认值。
- **交付与模块**：新增可选default_factory的明确映射类型，保持排序视图和构造/copy/pickle。；`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：get/contains不触发工厂；SortedDict默认缺键行为不变。
- **正常验收**：首次下标访问调用一次工厂，已有键不重复调用，排序正确。
- **异常／边界验收**：工厂异常不插入、工厂返回None、不可比较键、copy/union/pickle保留工厂。
- **原生回归**：`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 11．增加按映射值排序的独立索引适配器

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sorteddict.py)；任务表按主键查找，同时按记录priority范围查询。
- **原版现状／替代**：SortedDict只按键或key(键)排序，SortedValuesView仍按键顺序，并非按值排序。
- **交付与模块**：提供明确ValueSortedDict/附加值索引适配器，__setitem__同步移除旧排序键并加新值。；`src/sortedcontainers/sorteddict.py`、`src/sortedcontainers/sortedlist.py`。
- **兼容边界**：不改变SortedDict原有keys/items顺序；值变化通过明确写入入口，外部原地变化需refresh。
- **正常验收**：按ID更新priority后范围/排名立即更新，主键查找仍正确。
- **异常／边界验收**：重复priority、相同值、删除、比较异常原子性和多视图一致。
- **原生回归**：`tests/test_coverage_sorteddict.py`、`tests/test_coverage_sortedkeylist_modulo.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 12．有序映射直接迭代区间items与values

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sorteddict.py)；日程查询希望直接获得(time,title)，不必额外按键回查。
- **原版现状／替代**：irange代理只返回键，现有items/values只支持索引切片；可生成器组合。
- **交付与模块**：新增irange_items/irange_values，统一key边界与key函数/反向。；`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：普通irange仍返回键；与SortedValuesView的按键排序一致，不新建值排序。
- **正常验收**：指定时间窗返回正确项和值，闭开边界与irange完全一致。
- **异常／边界验收**：空映射、无界、reverse、底层修改策略、键值None和自定义key。
- **原生回归**：`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 13．可选在迭代中修改时明确失败

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；应用调试时希望及时发现遍历中误删/误加，而非漏元素。
- **原版现状／替代**：文档已说明修改期间可能异常或漏项；实跑取1后插0，后续又输出1，没有版本跟踪。
- **交付与模块**：新增opt-in checked iterator与修改代数，下一次next统一抛出可解释RuntimeError。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：默认性能和既有宽松迭代保持；明确只改value是否使items/values迭代失效。
- **正常验收**：严格迭代对添加/删除立即失败，未修改可完整遍历。
- **异常／边界验收**：irange/islice/reverse/view、clear、替换既有值、空迭代和多个迭代器。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sortedset.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 14．稳定游标分页跨越相同排序键

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；本地结果页面按priority分页，下一页不能漏掉同priority对象。
- **原版现状／替代**：irange只有值/key边界，没有cursor/page；bisect右边界会跳过整个同key组。
- **交付与模块**：新增显式稳定tie_breaker的page_after接口，返回数据和可校验游标。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：不承诺任意可变容器的快照一致性；游标绑定排序配置和版本或声明弱一致策略。
- **正常验收**：同key跨两页无重复/遗漏，反向分页对称。
- **异常／边界验收**：游标对应项删除、插入同key、策略变化、失效游标、limit0/负数。
- **原生回归**：`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 15．多操作批次可整体提交或回滚

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；一次更新本地任务表同时删除旧任务、改值和添加新任务。
- **原版现状／替代**：仅单次mutator，无transaction；调用方可copy后替换引用，现有外部views无法自然保持关联。
- **交付与模块**：新增事务编辑器在暂存索引执行，commit统一替换并保持公开视图绑定。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：不同于第1项单操作失败一致性；不提供并发隔离或持久存储事务。
- **正常验收**：多个操作全部成功一次可见，任一步失败原表和原视图值保持。
- **异常／边界验收**：嵌套事务、重复commit、key异常、旧迭代器、rollback和用户主动异常。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedset.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 16．公开泛型类型契约和可分发类型标记

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；业务项目静态检查需要推断键/值、范围迭代器和视图元素类型。
- **原版现状／替代**：核心方法无注解，发行目录无py.typed；已有外部stubs不能等同本仓类型承诺。
- **交付与模块**：为核心容器、key重载和视图提供泛型注解或stubs，分发py.typed并增加类型样例验证。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`、`pyproject.toml`。
- **兼容边界**：保持运行兼容版本；typing处理不能让原支持Python导入失败。
- **正常验收**：SortedDict[str,int]的items推断tuple[str,int]，错误写入能在检查中识别。
- **异常／边界验收**：None键函数重载、SortedKeyList返回类型、set反向运算与视图切片。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sortedset.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 17．公开受支持的分块负载配置

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；大量小对象的应用希望在可测范围选择块大小且copy后保持策略。
- **原版现状／替代**：只有私有_reset(load)，构造参数无load；默认1000，不能称缺少底层能力。
- **交付与模块**：增加受校验load_factor配置和诊断信息，并统一copy/代数/序列化保留规则。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：默认1000保持；公开允许范围与重建开销，不承诺所有工作负载更快。
- **正常验收**：合法配置下增删/排名正确，副本与pickle按约定保留。
- **异常／边界验收**：0/负/非整数、小块持续拆合、空容器和跨配置合并。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sortedset.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 18．提供谓词批量筛除和移除计数

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；清理所有标记为完成的任务，即使它们不形成连续排序区间。
- **原版现状／替代**：无remove_if；迭代同时删除不可靠，调用方可先复制再逐项remove或重建。
- **交付与模块**：新增remove_if(predicate)以单次稳定筛选重建受影响块，返回删数或被删项。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sortedset.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：与区间删除不同，谓词按值或item明确；异常时保留原容器。
- **正常验收**：非连续匹配全部删除且剩余相对次序/索引正确。
- **异常／边界验收**：全删/全留、predicate异常、有副作用修改拒绝、重复值与key缓存。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sortedset.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 19．有序列表可选择保留前K或后K元素

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；本地候选排行榜只需保留最优100项，避免应用层每次裁剪。
- **原版现状／替代**：构造只有iterable/key，没有capacity；应用可add后del切片。
- **交付与模块**：增加明确有界适配器，声明保留方向、等key淘汰和批量update返回淘汰项。；`src/sortedcontainers/sortedlist.py`。
- **兼容边界**：普通SortedList无容量限制；不隐式更改原类行为，不把K理解为内存字节。
- **正常验收**：连续加入与参考排序截取一致，update一次和逐项规则一致。
- **异常／边界验收**：K0/负数、同key稳定性、reverse key、生成器异常及全部淘汰。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

## 20．写入可以直接返回最终排序位置

- **类型／来源与场景**：enhancement；[来源](https://github.com/grantjenks/python-sortedcontainers/blob/3ac358631f58c1347f1d6d2d92784117db0f38ed/src/sortedcontainers/sortedlist.py)；界面插入一行后要定位其行号，避免再index查一遍。
- **原版现状／替代**：add和SortedDict.__setitem__实跑都返回None；已有bisect但应用需重新搜索。
- **交付与模块**：新增add_with_index/setitem_with_index，在已有块位置上返回全局索引及是否新建。；`src/sortedcontainers/sortedlist.py`、`src/sortedcontainers/sorteddict.py`。
- **兼容边界**：不改变标准add/__setitem__返回值；同key采用已选插入side，已有dict键返回当前位置。
- **正常验收**：插入中间数据返回正确排名，跨块拆分后仍可由索引取回。
- **异常／边界验收**：相等重复值、相同key不同对象、既有键改value、空容器与异常不返回虚假位置。
- **原生回归**：`tests/test_coverage_sortedlist.py`、`tests/test_coverage_sortedkeylist_modulo.py`、`tests/test_coverage_sorteddict.py`。
- **实际依赖／步骤依赖**：运行无外部依赖；适用原生测试仅pytest/pytest-cov，未安装benchmark比较库，不需要任何服务。；无。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
