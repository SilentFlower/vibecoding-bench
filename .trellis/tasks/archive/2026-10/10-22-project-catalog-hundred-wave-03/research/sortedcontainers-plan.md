# Sorted Containers本地索引任务表

固定3ac358631f58c1347f1d6d2d92784117db0f38ed，完整258个Git文件，核心Apache-2.0。tests/sortedcollection.py原作者Raymond Hettinger及原始recipe链接保持；按官方recipe及本仓docs/performance.rst说明另附MIT全文和归属，不改上游原文件。

已读SortedList/SortedKeyList构造、排序、键缓存、二分和边界，SortedDict视图/按排名删除，SortedSet同步实现和比较异常写入。完整默认docs/src/tests集合366项通过，其中70项doctest；既有benchmark忽略与原stress选择保持。

| 任务 | 独立业务边界 | 只读授权、正常及反例 |
| --- | --- | --- |
| SC-U01 理解 | 订货明细数量不能被去重 | 同一输入SortedList与SortedSet，重复3保留或合并 |
| SC-U02 理解 | 已取得的映射视图会变化 | 值按键排列、切片删两个排名位置、实时视图与列表快照不同 |
| SC-C01 咨询 | 邻近排期查找 | bisect左右侧区分严格/非严格、重复值和两端guard，空列表不误取-1 |
| SC-C02 咨询 | 已存对象排序键变化 | 实际缓存不刷新导致rank3/2，按稳定键合同选择先移除再更新或重建，不冒称原类保证自动刷新 |
| SC-P01 方案 | 同优先级记录分页漏项 | 仅rank游标跳过第三条；组合稳定ID得到3/4，另明确应用快照和更新政策 |
| SC-D01 诊断 | 比较异常后成员与迭代不一致 | 先追问完整类型/操作/异常，披露后核_set/_list部分写入；不假定捕获异常等于回滚，不授权修改；缺材料正常收口 |

四场景六项，无虚假依赖。全部对象在本地进程内，无实际日程或文件写入。独立业务、产品链及Git/Docker准入另验。
