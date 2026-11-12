# TinyDB：二十步真实工程迭代路线

固定 [msiemens/tinydb@edff96aeb2616402e9489d46e90a592c05565621](https://github.com/msiemens/tinydb/tree/edff96aeb2616402e9489d46e90a592c05565621)，详见[单仓审查](./tinydb.md)。共 20 步：18 项增强提案、2 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．一次性 updates 迭代器覆盖全部目标（问题修复）

- 来源／场景：[tinydb/table.py:update_multiple](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)
- 原版现状：外层遍历文档、内层直接遍历 updates；一次性迭代器只更新第一条。MemoryStorage 和 JSONStorage 均已复现。
- 交付目标：在本次调用开始时固定更新规则，使列表、元组和一次性迭代器结果等价。
- 影响模块：table.py:Table.update_multiple
- 兼容边界：保留规则顺序、同文档多次命中和返回 ID 的既有规则。
- 正常验收：两条订单都被相同规则更新，列表与 generator 得到相同数据和 ID。
- 异常／边界：空规则不修改；规则迭代中抛错时不提交半份规则；回调错误保留现有公开异常类型。
- 原生回归：tests/test_tinydb.py 的 update_multiple 与两种 storage 夹具
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．片段查询缓存包含完整字段路径（问题修复）

- 来源／场景：[tinydb/queries.py:Query.fragment](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/queries.py)
- 原版现状：fragment 的缓存键只有 fragment 内容，没有 self._path；left/right 对同一片段的查询串用缓存。已复现左、右命中文档应分别为 1/2，缓存后右误得 1。
- 交付目标：把字段路径纳入可缓存查询身份，避免不同嵌套字段互相污染。
- 影响模块：queries.py:Query.fragment；table.py:Table.search
- 兼容边界：根级 fragment 行为保持；map 路径仍不可缓存。
- 正常验收：相同片段作用于不同路径分别返回正确文档，反复交换查询次序一致。
- 异常／边界：空片段、缺失字段、不可哈希参数与组合 AND/OR 不复用错误缓存。
- 原生回归：tests/test_queries.py 的 fragment/fragment_with_path；tests/test_tables.py 的 query_cache
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．查询结果可选深拷贝隔离（增强提案）

- 来源／场景：[tinydb/table.py:Table.search](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)
- 原版现状：文档已明确返回缓存中文档对象，调用方必须只读；没有深拷贝结果模式。
- 交付目标：增加表级 copy_results 选项，隔离顶层和嵌套值的调用方修改。
- 影响模块：table.py:Table.__init__/search/get/__iter__
- 兼容边界：默认继续旧性能和只读约定，不把文档中的限制误报为 BUG。
- 正常验收：启用后改搜索结果的嵌套列表，不影响再次查询和真实存储。
- 异常／边界：不可复制的自定义值明确报错；关闭模式、空结果与自定义 Document 类回归。
- 原生回归：tests/test_tables.py；tests/test_tinydb.py；tests/test_storages.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．查询路径支持显式数组下标（增强提案）

- 来源／场景：[tinydb/queries.py:Query.__getitem__/_generate_test](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/queries.py)
- 原版现状：路径只识别字符串或 callable；没有受支持的整数下标路径接口，任意 map 是现有替代。
- 交付目标：增加显式 at_index(index) 路径构建操作，用于订单首项等嵌套数组查询。
- 影响模块：queries.py:Query 与路径解析
- 兼容边界：不改变 Query[字符串] 的键访问；明确不把 dict 的整数键与数组下标混淆。
- 正常验收：数组第 0 项的 sku 可继续接字段比较，缓存身份包含下标。
- 异常／边界：越界和非序列返回不匹配；负数明确支持 Python 语义，bool 下标拒绝。
- 原生回归：tests/test_queries.py 的 path/map/any/all
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．递归对象片段匹配（增强提案）

- 来源／场景：[tinydb/queries.py:Query.fragment](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/queries.py)
- 原版现状：现有 fragment 对子对象直接相等，无法表达子对象只约束部分键。
- 交付目标：增加 deep_fragment，递归比较 Mapping 中给定的键，列表沿用完整相等。
- 影响模块：queries.py:Query；utils.py:freeze
- 兼容边界：普通 fragment 不变；不把列表自动改为子集或忽略顺序。
- 正常验收：客户地址对象只给 city 时可匹配带其他地址字段的文档。
- 异常／边界：缺失键、None、数组、空子对象与循环对象输入有确定结果或明确拒绝。
- 原生回归：tests/test_queries.py；tests/test_tables.py 的缓存
- 真实依赖：02

## 06．缺失字段的查询默认值（增强提案）

- 来源／场景：[tinydb/queries.py:Query._generate_test/map](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/queries.py)
- 原版现状：当前路径缺失直接 False；map 无法为不存在的字段提供值。
- 交付目标：增加 default(value) 路径语义，在缺失时采用显式默认值再比较。
- 影响模块：queries.py:Query 路径构建与缓存身份
- 兼容边界：缺失与显式 None 分开；默认模式继续缺失不匹配。
- 正常验收：没有 qty 字段的订单按 qty=0 被明确查询。
- 异常／边界：嵌套缺失、已存在的 0/False/空字符串、可变默认值不串用缓存。
- 原生回归：tests/test_queries.py 的 exists/path/eq/map
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．稳定排序与分页检索（增强提案）

- 来源／场景：[tinydb/table.py:Table.search](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)
- 原版现状：只能返回全部匹配，排序和切片需应用自行实现。
- 交付目标：提供 search_page 的排序、offset、limit 与总数，doc_id 作为并列次序。
- 影响模块：table.py:Table.search 与新增结果结构
- 兼容边界：保留 search 原返回类型，不宣称跨多次写入的快照一致性。
- 正常验收：按 qty 降序分页，重复排序键仍不重不漏，返回总匹配数。
- 异常／边界：负数参数拒绝；limit=0、缺失排序字段、多类型键有显式策略。
- 原生回归：tests/test_tables.py；tests/test_tinydb.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．指定字段投影（增强提案）

- 来源／场景：[tinydb/table.py:Table.search/get](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)
- 原版现状：所有读取返回整个文档；没有带嵌套路径的投影入口。
- 交付目标：提供 select_fields，返回指定字段及可选 doc_id，减少业务层重复投影。
- 影响模块：table.py:读取接口；queries.py 路径工具
- 兼容边界：默认整文档读取不变；投影不会删除真实文档字段。
- 正常验收：订单列表只返回 sku 与 address.city，字段顺序和 ID 可配置。
- 异常／边界：缺失路径可省略或显式默认；投影输出修改不污染缓存，拒绝重叠别名。
- 原生回归：tests/test_tables.py；tests/test_queries.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．字段唯一值统计（增强提案）

- 来源／场景：[tinydb/table.py:Table.count](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)
- 原版现状：已有 count(cond)，没有 distinct 字段值集合；应用需搜索后去重。
- 交付目标：增加 distinct_values(field,cond)，按首次出现顺序对 JSON 值去重。
- 影响模块：table.py；utils.py:freeze
- 兼容边界：不隐式排序混合 JSON 类型，区分 bool 与数值的策略写入契约。
- 正常验收：统计售出 sku，过滤条件和去重后顺序正确。
- 异常／边界：缺失字段、None、嵌套列表／对象值与空表不会因不可哈希而崩溃。
- 原生回归：tests/test_tables.py；tests/test_utils.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 10．按字段分组聚合（增强提案）

- 来源／场景：[tinydb/table.py:Table.count/search](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)
- 原版现状：只有总数与过滤计数，没有分组 sum/count/min/max。
- 交付目标：提供 group_by 聚合，以类别输出数量和显式数值聚合。
- 影响模块：table.py 与独立轻量聚合辅助逻辑
- 兼容边界：保持纯 Python／无服务；非数值和缺失处理必须由参数明确。
- 正常验收：订单按 sku 汇总 qty，组顺序固定、空输入结果确定。
- 异常／边界：非数值可拒绝或显式忽略，None 分组、所有值为空和零值回归。
- 原生回归：tests/test_tables.py；tests/test_tinydb.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．嵌套字段编辑操作（增强提案）

- 来源／场景：[tinydb/operations.py:set/delete](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/operations.py)
- 原版现状：现有 set/delete 仅按一个顶层键操作，点号被当成实际键。
- 交付目标：新增 set_path/delete_path，接受路径序列并可显式创建中间对象。
- 影响模块：operations.py；table.py:Table.update
- 兼容边界：保留原顶层含点键含义，不对全部字符串做隐式拆分。
- 正常验收：更新 address.city 不丢失 address.zip，删除目标叶节点。
- 异常／边界：路径不存在、穿过标量、空路径和数组下标越界按明确模式处理，失败不提交。
- 原生回归：tests/test_operations.py；tests/test_tinydb.py 的 update_transform
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．数组字段增删与去重追加（增强提案）

- 来源／场景：[tinydb/operations.py](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/operations.py)
- 原版现状：仅 add 可使用 Python +，没有按元素删除、去重追加的数组更新原语。
- 交付目标：新增一组数组编辑操作 append_items/pull_items，覆盖常见标签维护场景。
- 影响模块：operations.py；table.py:Table.update
- 兼容边界：本步合并为完整数组编辑交付，不把 append/pull 测试拆成多步；原 add 保持。
- 正常验收：标签追加保序，可选去重；按给定值移除全部目标项。
- 异常／边界：缺字段、None、字符串及嵌套 JSON 项处理明确，非法类型不默默拆字符。
- 原生回归：tests/test_operations.py；tests/test_tinydb.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．只补齐缺失字段的默认值更新（增强提案）

- 来源／场景：[tinydb/operations.py:set](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/operations.py)
- 原版现状：set 覆盖已有字段，应用需要自行写缺失判断回调。
- 交付目标：新增 set_defaults(mapping)，只为不存在的字段填默认值。
- 影响模块：operations.py；table.py:Table.update
- 兼容边界：None、False、0、空字符串属于已有值，不按假值覆盖。
- 正常验收：历史订单补 currency，已有 EUR 保持、缺失取 CNY。
- 异常／边界：多个文档不共享可变默认对象；空映射、非法键和回调失败回归。
- 原生回归：tests/test_operations.py；tests/test_tinydb.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 14．按自然键批量 upsert（增强提案）

- 来源／场景：[tinydb/table.py:Table.upsert](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)
- 原版现状：单条 upsert 已有，批量只能循环并反复读写整个 JSON。
- 交付目标：增加 upsert_multiple(documents,key_fields)，一次读取和发布，返回逐输入文档 ID。
- 影响模块：table.py:Table.upsert/_update_table
- 兼容边界：单条 upsert 继续更新所有 cond 命中；新 API 的自然键必须明确，不靠隐式第一个字段。
- 正常验收：同批已有 sku 更新、缺失 sku 插入，稳定返回对应 ID。
- 异常／边界：输入生成器、重复自然键的显式 last/error 策略、缺键与非法文档在写入前拒绝。
- 原生回归：tests/test_tinydb.py 的 upsert/insert_multiple
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．可选业务唯一键约束（增强提案）

- 来源／场景：[tinydb/table.py:Table.insert/insert_multiple/update](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)
- 原版现状：仅 doc_id 唯一；订单号等字段无约束，必须自行查询后判断。
- 交付目标：表可声明 unique_fields，所有本表写路径在发布前检查唯一性。
- 影响模块：table.py 写入口与 _update_table
- 兼容边界：默认无约束；仅保证单实例单次写入，不声称多进程并发安全或新增索引。
- 正常验收：重复订单号被拒绝，合法更新和批量写正常，错误含字段名与冲突 ID。
- 异常／边界：NULL/缺失策略明确；同批冲突、修改为冲突值时不提交整次更新。
- 原生回归：tests/test_tinydb.py；tests/test_tables.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．单实例批处理提交与回滚（增强提案）

- 来源／场景：[docs/extensions.rst:Tinyrecord；tinydb/storages.py:Storage](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/docs/extensions.rst)
- 原版现状：官方列出第三方 Tinyrecord，核心没有事务入口；CachingMiddleware 只缓冲写入且不回滚。
- 交付目标：增加显式 batch_changes 上下文，内存暂存单实例多表写，成功一次发布、异常丢弃。
- 影响模块：database.py；middlewares.py；table.py 缓存管理
- 兼容边界：仅单进程、单实例、非嵌套的受控批处理；不承诺 ACID、多线程或跨进程隔离，不把 TinyDB 改成服务。
- 正常验收：一次移动订单和写审计表同时提交，外层失败两表都恢复。
- 异常／边界：嵌套明确拒绝；读取自身未提交数据，底层提交失败保留错误并失效缓存。
- 原生回归：tests/test_tinydb.py；tests/test_middlewares.py；tests/test_storages.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．可选原子 JSON 文件发布（增强提案）

- 来源／场景：[tinydb/storages.py:JSONStorage.write](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/storages.py)
- 原版现状：当前在原文件 seek/write/fsync/truncate，已有 fsync 但没有临时文件原子替换。
- 交付目标：提供可选 AtomicJSONStorage，在同目录序列化临时文件、同步并替换，再重开句柄。
- 影响模块：storages.py；database.py 存储扩展点
- 兼容边界：不修改默认 JSONStorage 行为和第三方 Storage 协议；明确本地文件系统语义及 Windows 限制。
- 正常验收：缩短／加长 JSON 均可重新打开，原有权限和自定义 JSON 编码参数保留。
- 异常／边界：序列化／写入／替换前错误保留原文件并清临时文件；替换后同步错误如实报告。
- 原生回归：tests/test_storages.py；tests/test_middlewares.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 18．带校验的数据库备份与恢复（增强提案）

- 来源／场景：[tinydb/database.py:storage/tables](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/database.py)
- 原版现状：只能手动复制存储文件或自己读写全部 storage，没有验证完整结构的备份入口。
- 交付目标：增加 export_backup/import_backup，保留表名和 doc_id，恢复前校验结构与冲突策略。
- 影响模块：database.py；storages.py；table.py ID 与缓存
- 兼容边界：备份是逻辑 JSON 格式，与自定义存储路径分离；默认拒绝覆盖非空库。
- 正常验收：多表及显式 ID 备份到流、恢复后内容和下一自动 ID 正确。
- 异常／边界：坏 JSON、非法表结构、重复 ID 和中途解析错误在发布前拒绝，源库不变。
- 原生回归：tests/test_tinydb.py；tests/test_storages.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．无数据丢失的表重命名（增强提案）

- 来源／场景：[tinydb/database.py:table/drop_table](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/database.py)
- 原版现状：只有创建访问和删除，重命名需应用改写 storage 并自行处理缓存。
- 交付目标：新增 rename_table(old,new)，保持文档与 ID，更新表缓存归属并给出旧句柄策略。
- 影响模块：database.py；table.py:name 与缓存
- 兼容边界：默认目标已存在则拒绝，明确旧句柄失效而非悄悄写回旧表。
- 正常验收：带数据表改名后新名字查询一致，重启后仅新表存在。
- 异常／边界：同名、缺失源、目标冲突和底层 write 失败不丢失数据。
- 原生回归：tests/test_tables.py；tests/test_tinydb.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．提交后的文档变更通知（增强提案）

- 来源／场景：[tinydb/table.py:_update_table；tinydb/middlewares.py](https://github.com/msiemens/tinydb/blob/edff96aeb2616402e9489d46e90a592c05565621/tinydb/table.py)
- 原版现状：Storage middleware 可看到整库写入，但核心没有携带操作和文档 ID 的业务通知。
- 交付目标：增加可选 after_change 订阅，成功提交后发送表、操作、ID 和前后摘要供应用刷新界面。
- 影响模块：table.py 写入口；database.py 监听管理
- 兼容边界：不默认包含敏感文档值；通知失败不能伪装存储回滚，禁止重入写本实例。
- 正常验收：成功新增／更新／删除触发一次，批处理按明确提交事件合并。
- 异常／边界：写入失败无通知、取消订阅有效、监听异常可观察且已提交状态保留。
- 原生回归：tests/test_tinydb.py；tests/test_middlewares.py
- 真实依赖：16

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
