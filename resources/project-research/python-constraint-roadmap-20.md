# Python Constraint 二十步迭代研究路线

固定[python-constraint/python-constraint@d91ba03d1fd6acc30d64fd9d513dc0523f697b5b](https://github.com/python-constraint/python-constraint/tree/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b)。以下每项是研究者提出的普通业务工程交付，来源为当前源码与明确业务场景；只有标注bug_fix的条目按实跑问题处理。20项均未实施或冻结新增验收。
已支持字符串普通算式优化、变量目标sum/product、负数域、MinConflicts自定义rand、OrderedList导出和并行线程/进程模式；不把这些现成能力重新计入。带负系数仍有独立实证问题，按统一加权界修复合并。

## 01．加权和剪枝正确处理负系数

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/constraints.py)；预算差额x-y=0应保留x/y相等的组合。
- **原版现状／替代**：ExactSumConstraint(0,[1,-1])对[1,2]两域实跑返回空，穷举应有(1,1)/(2,2)；min(domain)*负系数不是贡献下界。
- **交付与模块**：统一固定/变量目标求和约束的加权上下界与前向剪枝，按系数符号计算贡献范围。；`constraint/constraints.py`。
- **兼容边界**：现有正数/无系数语义保持；整数精确，浮点舍入策略单独明确。
- **正常验收**：exact/min/max与小规模参考枚举结果集合一致，负系数不丢合法解。
- **异常／边界验收**：零系数、全负、多负、负域、目标变量、fractional系数、域剪空不二次remove报错。
- **原生回归**：`tests/test_constraint.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 02．重复求解不累加字符串编译约束

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；同一本地排班模型多次查询应有稳定的约束数与成本。
- **原版现状／替代**：getSolutions两次结果相同但_constraints从1增至2；_getArgs每次编译后调用addConstraint且原字符串仍保留。
- **交付与模块**：解析结果只进入本轮求解列表或按模型版本缓存，增删变量时正确失效。；`constraint/problem.py`、`constraint/parser.py`。
- **兼容边界**：不改变字符串现有表达语义；保留用户显式重复添加的约束，不去重不同对象。
- **正常验收**：连续求解10次底层约束数量不增长且解集合不变。
- **异常／边界验收**：混合函数/字符串、切换solver可pickle策略、模型变更、解析异常与reset。
- **原生回归**：`tests/test_problem.py`、`tests/test_parser.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 03．单列结果顺序参数真正投影到指定变量

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；应用只导出变量a，不能收到全部变量值。
- **原版现状／替代**：getSolutionsOrderedList([a])实跑返回(1,2)而非(1,)；len(order)==1被误当默认路径。
- **交付与模块**：显式order统一按指定变量构造tuple，单列保持一元tuple；约定空order。；`constraint/problem.py`。
- **兼容边界**：order=None可保持已有值顺序或明确迁移；不隐式把字符串当变量列表。
- **正常验收**：两变量模型指定[a]只得到一元组，指定[b,a]正确重排。
- **异常／边界验收**：空order、重复变量、缺失变量、非字符串合法标识、getSolutionsAsListDict投影重复检查。
- **原生回归**：`tests/test_problem.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 04．域迭代器与任意可hash变量标识正确接入

- **类型／来源与场景**：bug_fix；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；由生成器读入同一组可选时间，分配给多个变量。
- **原版现状／替代**：addVariables对生成器首变量消费后次变量Domain empty；tuple标识配生成器因错误检查variable类型而TypeError。
- **交付与模块**：域输入统一在合适层物化一次，再为各变量独立Domain；检查对象应针对domain。；`constraint/problem.py`、`constraint/domain.py`。
- **兼容边界**：保留Domain子类deepcopy；不共享可变Domain状态；不隐式接受空域。
- **正常验收**：生成器[1,2]用于a/b产生4解，tuple标识单变量也正常。
- **异常／边界验收**：一次性迭代器异常、重复变量导致的部分写入契约、集合/range、Domain子类和空域。
- **原生回归**：`tests/test_problem.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 05．递归回溯求解器提供逐解迭代

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/solvers.py)；内存有限的离线组合题希望边求边消费，且继续使用递归策略。
- **原版现状／替代**：RecursiveBacktrackingSolver只提供单解/全列表，getSolutionIter明确NotImplementedError。
- **交付与模块**：实现递归yield搜索并可靠保存/恢复domain与assignment状态。；`constraint/solvers.py`、`constraint/domain.py`。
- **兼容边界**：现有单解/全列表结果集合保持；不通过先getSolutions再iter伪装流式。
- **正常验收**：首个next在未枚举全量前返回，遍历集合与参考求解一致。
- **异常／边界验收**：提前close、用户中断、无解、空模型、异常回滚和forwardcheck开关。
- **原生回归**：`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 06．求解可限制返回解数量

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；业务只需要前10个可行排班，不应计算全部方案。
- **原版现状／替代**：Problem.getSolutions无limit；可islice已有非递归迭代器，但solver能力不统一。
- **交付与模块**：增加统一max_solutions参数与结果完整性标识，底层搜索在达到数目后停止。；`constraint/problem.py`、`constraint/solvers.py`。
- **兼容边界**：默认全解保持；limit不保证某种最优性；支持能力差异需明确。
- **正常验收**：limit3只访问并返回3个解，complete=False且不继续搜完。
- **异常／边界验收**：0/负数、恰好总数、少于限制、无解和并行任务协作停止。
- **原生回归**：`tests/test_problem.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 07．可按搜索节点或时间预算协作停止

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；交互排班编辑希望用户取消时尽快返回已得方案。
- **原版现状／替代**：除MinConflicts.steps外没有通用budget/cancel；全解接口无控制参数。
- **交付与模块**：新增SearchControl节点/单调时间预算与cancel回调，返回stopped原因和部分结果。；`constraint/problem.py`、`constraint/solvers.py`。
- **兼容边界**：不能把预算耗尽当无解；不强行中止任意用户函数，声明检查粒度。
- **正常验收**：小节点预算可重复停止，取消后状态清理且同模型能再次完整求解。
- **异常／边界验收**：预算0、计时边界、回调异常、并行清理、无解与已求完区别。
- **原生回归**：`tests/test_problem.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 08．返回可解释的求解统计报告

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；比较普通排班模型的两种搜索策略时需要知道瓶颈是剪枝还是回溯。
- **原版现状／替代**：无公开getStatistics，benchmark只有外部耗时。
- **交付与模块**：新增SolveReport含访问节点、回溯、约束检查、域删减和阶段耗时，按求解返回隔离。；`constraint/problem.py`、`constraint/solvers.py`、`constraint/constraints.py`、`constraint/domain.py`。
- **兼容边界**：默认轻量统计或opt-in，数值含义文档固定；不声称统计本身提高算法速度。
- **正常验收**：已知小模型计数满足不变量，报告绑定本次模型版本和solver。
- **异常／边界验收**：多次/并发报告不串、预算中断/无解、用户约束异常和纯Python/C统计一致。
- **原生回归**：`tests/test_problem.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 09．约束返回句柄并可分组移除

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；排班界面取消某条偏好规则后需要重新求解。
- **原版现状／替代**：addConstraint返回None，只有reset全部清空，未提供removeConstraint。
- **交付与模块**：返回稳定ConstraintHandle并支持命名分组启停/移除，字符串编译缓存随之失效。；`constraint/problem.py`、`constraint/parser.py`。
- **兼容边界**：已有忽略返回值的调用兼容；变量变更与约束生命周期明确，不直接暴露私有list。
- **正常验收**：移除tea先于review规则后方案数恢复；只移除指定句柄实例。
- **异常／边界验收**：未知/重复移除、同函数两句柄、字符串分裂多约束、reset后旧句柄与group开关。
- **原生回归**：`tests/test_problem.py`、`tests/test_parser.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 10．临时假设限定某次求解而不修改模型

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；用户预选tea=9，尝试几套假设后恢复未限定的排班。
- **原版现状／替代**：getSolution无assumptions，需复制模型或永久增加函数限制。
- **交付与模块**：新增solve(assumptions=...)为本轮域求交并在结束/异常后恢复。；`constraint/problem.py`、`constraint/solvers.py`、`constraint/domain.py`。
- **兼容边界**：不自动把假设写入模型；非法值与逻辑无解区分；不依赖新增removeConstraint。
- **正常验收**：同模型先假设tea9、再tea10、最后无限定，各集合与参考一致。
- **异常／边界验收**：未知变量、域外值、空交集、迭代提前关闭、可变Domain子类。
- **原生回归**：`tests/test_problem.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 11．求解前验证模型并定位声明错误

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；GUI添加约束引用了不存在的变量，希望在搜索前得到说明。
- **原版现状／替代**：未知变量实跑KeyError(absent)，无validate入口；长度错误多为底层assert或zip静默。
- **交付与模块**：提供validate报告，检查变量引用、系数长度、空域与约束能力，保留原始规则来源。；`constraint/problem.py`、`constraint/constraints.py`、`constraint/parser.py`。
- **兼容边界**：只检查可静态确定的问题，不尝试执行所有用户约束；逻辑无解不是结构错误。
- **正常验收**：报告给出具体约束、缺失变量、建议位置，合法模型验证不改域。
- **异常／边界验收**：任意hashable变量、重复引用、可选allvariables、系数非数值和前向引用声明顺序。
- **原生回归**：`tests/test_problem.py`、`tests/test_parser.py`、`tests/test_constraint.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 12．模型快照与求解状态相互隔离

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；同一基础模型建立两份what-if草稿，并可同时消费解迭代器。
- **原版现状／替代**：无copy，_getArgs浅copy后Domain仍是原对象；约束preProcess及缓存可保留状态。
- **交付与模块**：新增明确ModelSnapshot/clone并为每次求解分配域状态，定义Constraint clone协议。；`constraint/problem.py`、`constraint/domain.py`、`constraint/constraints.py`、`constraint/solvers.py`。
- **兼容边界**：用户callable按文档共享引用或显式clone，不假称任意闭包可deepcopy；既有同步调用可迁移。
- **正常验收**：两个快照增约束互不影响，两次交错迭代解集合均完整。
- **异常／边界验收**：提前close、异常、Domain子类、约束内部缓存、不可复制资源与线程边界说明。
- **原生回归**：`tests/test_problem.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 13．把弧一致性作为可选预处理策略接入

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/solvers.py)；二元相等/不等限制密集的有限域题在回溯前减少域。
- **原版现状／替代**：getArcs/doArc8 helper存在但_getArgs调用被注释，当前默认未使用。
- **交付与模块**：审查并修正传播队列后提供opt-in arc-consistency预处理，记录删域原因。；`constraint/solvers.py`、`constraint/problem.py`、`constraint/domain.py`。
- **兼容边界**：不声称仅取消注释就可用；仅对支持的约束和有限域启用，保持合法解集合。
- **正常验收**：链式二元关系能传播至不相邻变量，解与未启用枚举一致。
- **异常／边界验收**：无解提前发现、变量赋值清理、重复边、孤立域、用户约束不支持传播时回退。
- **原生回归**：`tests/test_solvers.py`、`tests/test_constraint.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 14．搜索变量与值顺序策略可显式配置

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/solvers.py)；普通课程安排希望固定解顺序，或用最少剩余值加degree优先。
- **原版现状／替代**：优化solver构造仅forwardcheck，顺序启发式写死；MinConflicts已有rand可重复能力。
- **交付与模块**：增加variable_order/value_order协议与内建声明策略，报告最终策略和稳定tie-break。；`constraint/solvers.py`、`constraint/problem.py`。
- **兼容边界**：默认策略保持；不重复提案MinConflicts已有随机源注入。
- **正常验收**：固定策略多次求解返回同序列，自定义策略仍满足全部约束。
- **异常／边界验收**：不同类型变量标识不可强行比较、策略漏变量/重复值、动态域变化和异常。
- **原生回归**：`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 15．提供允许或禁止元组的表约束

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/constraints.py)；课程和教室合法组合由离线数据表直接给出。
- **原版现状／替代**：没有Table/Tuple约束，只能FunctionConstraint做membership。
- **交付与模块**：新增AllowedTuples/ForbiddenTuples约束，按变量位置建支持索引并进行前向筛域。；`constraint/constraints.py`。
- **兼容边界**：允许非数字域；tuple列顺序严格按variables，输入表只读持有快照。
- **正常验收**：三列允许表输出恰好指定组合，前向检查不漏解。
- **异常／边界验收**：空表、错列数、重复行、不可hash值的受限回退、部分赋值和超大表预算。
- **原生回归**：`tests/test_constraint.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 16．全局基数约束按每个值限制出现次数

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/constraints.py)；排班要求A班恰好2人、B班1至3人。
- **原版现状／替代**：SomeInSet已支持一组取值的数量，但没有一次按多个值分别规定的global cardinality。
- **交付与模块**：新增GlobalCardinalityConstraint(value_bounds)，综合已赋值/可支持域计数剪枝。；`constraint/constraints.py`。
- **兼容边界**：不把已有SomeInSet/SomeNotInSet重新包装计数；明确未列取值能否出现。
- **正常验收**：多值上下界同时满足，结果集合与小规模参考枚举一致。
- **异常／边界验收**：下界总和超变量数、上界不足、缺失值、重复变量和空域传播。
- **原生回归**：`tests/test_constraint.py`、`tests/test_some_not_in_set.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 17．提供普通日程的资源容量约束

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/constraints.py)；离线排班任务有起点、持续时间和人数，重叠时不能超过教室容量。
- **原版现状／替代**：无Cumulative/NoOverlap类，可写自定义函数但缺少通用传播。
- **交付与模块**：新增整数时间CumulativeConstraint及容量1的NoOverlap包装，先明确半开区间。；`constraint/constraints.py`。
- **兼容边界**：范围限定有限整数时间；零时长/负时长和可选任务策略明确，不宣称实数调度引擎。
- **正常验收**：同一时间资源总和不超容量，接壤任务不算重叠。
- **异常／边界验收**：零/负容量、跨午夜归一化、可变持续时间声明范围和部分赋值的保守剪枝。
- **原生回归**：`tests/test_constraint.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 18．支持带明确方向的最优解搜索

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；可行排班很多，用户希望最小化等待时间并获得最优性状态。
- **原版现状／替代**：没有objective/optimize接口；examples/abc自行枚举挑最小。
- **交付与模块**：新增显式objective与min/max方向，先可用枚举基线，再按可证明下界提供branch-and-bound。；`constraint/problem.py`、`constraint/solvers.py`。
- **兼容边界**：可行性约束不变；预算停止时只能称当前最好，不能称已最优；用户函数无下界时不剪枝。
- **正常验收**：小模型最优值与参考全枚举相等，平局解策略明确。
- **异常／边界验收**：无解、非数值目标、目标异常、负值、并列最优和预算报告。
- **原生回归**：`tests/test_solvers.py`、`tests/test_constraint.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 19．带标签约束可解释无解原因

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/problem.py)；排班规则互相冲突时希望看到一个仍然无解的规则子集。
- **原版现状／替代**：当前无解返回None/[]，无explain；用户只能逐条删规则试验。
- **交付与模块**：新增显式diagnose_unsat，在受限预算下按删除检验输出可验证冲突子集和标签。；`constraint/problem.py`、`constraint/solvers.py`。
- **兼容边界**：不保证最小基数；区分已证明无解与搜索未完成；假设和原模型域保持。
- **正常验收**：给出子集重新求解确实无解，声明minimal时去任一条均可解。
- **异常／边界验收**：多个独立冲突、基础域无解、用户约束有状态、预算不足和标签重复。
- **原生回归**：`tests/test_problem.py`、`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

## 20．并行求解明确限制worker与在途任务

- **类型／来源与场景**：enhancement；[来源](https://github.com/python-constraint/python-constraint/blob/d91ba03d1fd6acc30d64fd9d513dc0523f697b5b/constraint/solvers.py)；普通笔记本上的组合求解不能默认占满全部CPU和内存。
- **原版现状／替代**：ParallelSolver仅process_mode，Executor未给max_workers；每分支收集全列表。
- **交付与模块**：新增max_workers/max_pending及分支分块配置，逐批消费结果并按资源预算调度。；`constraint/solvers.py`、`constraint/problem.py`。
- **兼容边界**：保留线程/进程两模式；不是分布式服务，不增加网络通信；进程函数可pickle限制明确。
- **正常验收**：设置2workers确实只启动2个，结果集合与顺序求解一致。
- **异常／边界验收**：1/0/负workers、单变量分支、异常取消清理、进程字符串约束与大结果缓冲。
- **原生回归**：`tests/test_solvers.py`。
- **实际依赖／步骤依赖**：运行本体无外部服务；宿主构建使用poetry-core/setuptools/Cython，当前五个Cython扩展已实际加载；测试pytest/pytest-cov/pytest-benchmark与pep440，精确版本已冻结。；无。

实施时在同一真实源码累计修改，每步同时含实现、测试、文档和失败修复。未来控制端冻结独立验收、核对候选加载路径、运行正反场景并回归原生集合及此前步骤；本研究尚未执行这些未来验收。
