# dataset：二十步真实工程迭代路线

固定 [pudo/dataset@db592cc041014762bba55fd544e982170831f227](https://github.com/pudo/dataset/tree/db592cc041014762bba55fd544e982170831f227)，详见[单仓审查](./dataset.md)。共 20 步：19 项增强提案、1 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．批量更新遵守自动建列与显式类型（问题修复）

- 来源／场景：https://github.com/pudo/dataset/issues/409
- 原版现状：update_many 声明 ensure/types，却没有调用 _sync_columns；ensure=True 更新新字段仍 CompileError，当前提交已复现。
- 交付目标：在构建批量 UPDATE 前统一同步新增列并使用 types，不丢失已有字段。
- 影响模块：table.py:Table.update_many/_sync_columns
- 兼容边界：ensure=False 仍不隐式建列；不把批次中缺字段自动当作删除或 NULL。
- 正常验收：两条现有记录批量增加新列，指定 integer 类型生效，普通字段更新保持。
- 异常／边界：缺少匹配 keys、新列类型不兼容、空输入与 ensure=False 的明确错误不留半份 DML。
- 原生回归：test/test_table.py 的 update_many、update 与自动建列
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．只连接已经存在的 SQLite 文件（增强提案）

- 来源／场景：https://github.com/pudo/dataset/issues/433
- 原版现状：connect 默认允许 SQLite 创建新文件；util.make_sqlite_url 可构建 ro/rw URI，但公开 connect 没有直接 existing_only 参数。
- 交付目标：增加 existing_only 便捷选项，SQLite 使用 URI mode=rw 或 ro，而非先 exists 后不受控创建。
- 影响模块：__init__.py:connect；util.py:make_sqlite_url
- 兼容边界：默认自动创建保持；非 SQLite 方言明确不支持或要求调用者原生 URL，不泛化服务端数据库检查。
- 正常验收：已有临时 SQLite 可连接，缺失路径报错且不出现文件。
- 异常／边界：路径含空格／问号、只读模式、内存 URL 和矛盾参数拒绝。
- 原生回归：test/test_database.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．find 与 find_one 字段投影（增强提案）

- 来源／场景：https://github.com/pudo/dataset/issues/432
- 原版现状：find 固定 self.table.select() 返回全部列；原生 SQLAlchemy select/db.query 是替代。
- 交付目标：增加保留字 _columns，生成只选择指定列的原生 SQL 查询。
- 影响模块：table.py:Table.find/find_one
- 兼容边界：默认完整行与 row_type 保持；列名使用 SQLAlchemy 引用，不拼接未转义 SQL。
- 正常验收：订单只取 sku/qty，过滤、排序、流式和 find_one 一致。
- 异常／边界：不存在列、空列集、重复列、含空格列名及无结果行为明确。
- 原生回归：test/test_table.py；test/test_row_type.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．按业务键清理重复行（增强提案）

- 来源／场景：https://github.com/pudo/dataset/issues/413
- 原版现状：需自写 SQL；Table 没有保留指定一条并删除其他重复记录的接口。
- 交付目标：增加 deduplicate(keys,keep,order_by)，提供预览和实际删除数。
- 影响模块：table.py；database.py:显式事务
- 兼容边界：默认 dry_run，必须明确 key 与稳定 keep 规则；不把全表相等误当自然键。
- 正常验收：按订单号分组保留最新 ID，删除清单与真实数据库行一致。
- 异常／边界：NULL、复合键、无主键表、非唯一排序及空键拒绝或显式策略，失败整次回滚。
- 原生回归：test/test_table.py；test/test_database.py 的事务
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．数据库内原子增减数值（增强提案）

- 来源／场景：https://github.com/pudo/dataset/issues/405
- 原版现状：目前需自己写 SQLAlchemy 表达式或 SQL；无简易 increment 入口。
- 交付目标：提供 increment(column,amount,filters)，单条 UPDATE 表达式执行并返回影响行数。
- 影响模块：table.py:数值更新辅助入口
- 兼容边界：不先读取再写入；已有 update 字面设置行为保持，NULL 规则显式。
- 正常验收：两连接受控更新同一库存，结果累计无丢失，过滤未命中返回 0。
- 异常／边界：非数值列、溢出、NULL、负数、amount=0 和 SQL 参数边界明确。
- 原生回归：test/test_table.py；test/test_database.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．Decimal 与 Enum 的显式编解码（增强提案）

- 来源／场景：https://github.com/pudo/dataset/issues/403
- 原版现状：Types.guess 不识别 Decimal/Enum；可以手动 SQLAlchemy 类型和预处理值，核心缺少统一 opt-in codec。
- 交付目标：允许每列显式 codec 与 Numeric/文本存储策略，枚举映射为 value，Decimal 不默默转 float。
- 影响模块：types.py:Types.guess；table.py 写入；util.py:convert_row
- 兼容边界：默认推断保持；不声称 SQLite Numeric 具有任意精度，精确保真使用文本 codec。
- 正常验收：金额 1.2300 与币种枚举写读按选定策略往返，多行入口一致。
- 异常／边界：非法枚举、非有限 Decimal、精度越界、None 与更新路径在写前校验。
- 原生回归：test/test_table.py；test/test_row_type.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．声明复合主键建表（增强提案）

- 来源／场景：https://github.com/pudo/dataset/issues/328
- 原版现状：create_table primary_id 仅一个字符串，底层 SQLAlchemy 可表达多列主键。
- 交付目标：增加明确 primary_keys 列规格，直接建立复合约束而非伪造 id。
- 影响模块：database.py:Database.create_table；table.py:Table 构建
- 兼容边界：单列 primary_id 保持；不能同时设置两套主键定义，不隐式增加自增列。
- 正常验收：国家+年份联合唯一，反射读回主键列及顺序一致。
- 异常／边界：重复组合、部分 NULL、类型不全、已有表结构不匹配明确拒绝。
- 原生回归：test/test_database.py 的 create_table
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．公开结构化索引与唯一键元数据（增强提案）

- 来源／场景：https://github.com/pudo/dataset/issues/332
- 原版现状：只有 has_index/create_index，用户可通过 db.inspect 自行读取，但没有 Table 级稳定摘要。
- 交付目标：提供 Table.indexes/unique_constraints 摘要，保存名称、顺序、unique 与主键区别。
- 影响模块：table.py；database.py:inspect
- 兼容边界：不自动把非唯一索引认作 upsert 冲突键；不更改原 has_index 覆盖判定。
- 正常验收：多列唯一／普通索引分别可见，刷新后反映外部创建的索引。
- 异常／边界：表达式索引／方言特殊项保留能力标记，不臆造 column_names。
- 原生回归：test/test_table.py；test/test_database.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．SQLite 数据库原生冲突更新（增强提案）

- 来源／场景：https://github.com/pudo/dataset/issues/317
- 原版现状：upsert 先 UPDATE 后 INSERT，不使用 SQLite ON CONFLICT；存在并发窗口及多语句成本。
- 交付目标：增加 opt-in native_upsert，首版只支持 SQLite 显式唯一键的 ON CONFLICT DO UPDATE。
- 影响模块：table.py:Table.upsert/upsert_many；SQLAlchemy sqlite 方言
- 兼容边界：普通 upsert 的多行匹配与返回规则不变；其他方言保留旧入口，不声称 PostgreSQL 已验证。
- 正常验收：唯一 sku 的插入和更新在单条语句完成，指定更新列不覆盖省略值。
- 异常／边界：没有对应唯一约束、重复输入、只含 key、NULL 冲突键及 returning 能力明确。
- 原生回归：test/test_table.py；test/test_database.py
- 真实依赖：08

## 10．管理连接生命周期的独立上下文（增强提案）

- 来源／场景：https://github.com/pudo/dataset/issues/418
- 原版现状：with db 已表示事务，退出不会关闭整个 Database，不能直接改变其既有语义。
- 交付目标：增加 closing_connect 或 Database.closing()，退出时确定 close，事务上下文仍可嵌套使用。
- 影响模块：__init__.py；database.py:Database.close
- 兼容边界：原 with db 继续只管提交／回滚；新资源上下文与事务行为分别说明。
- 正常验收：正常与异常退出后所有连接归还、engine disposed，文件可重开。
- 异常／边界：重复 close、内部迭代器尚在使用、线程连接及打开失败清理行为明确。
- 原生回归：test/test_database.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．查询结果作为可关闭上下文（增强提案）

- 来源／场景：[dataset/util.py:ResultIter.close](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/util.py)
- 原版现状：迭代耗尽会 close，提前 break 需要显式调用；没有 __enter__/__exit__。
- 交付目标：ResultIter 支持 with，提前退出释放独立 streamed connection 和结果游标。
- 影响模块：util.py:ResultIter；table.py:find(_streamed)
- 兼容边界：普通迭代和现有 close 保持，退出不关闭调用方共享的 Database。
- 正常验收：读取一行即退出上下文，游标与专用连接已释放，可继续查询。
- 异常／边界：异常、空结果、重复 close、row_type 转换抛错也回收结果。
- 原生回归：test/test_database.py；test/test_row_type.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．有界消费一次性批量输入（增强提案）

- 来源／场景：[dataset/table.py:Table.insert_many/update_many](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/table.py)
- 原版现状：公开类型为 Sequence；insert_many 两次遍历并用 len，不能直接接 generator；ChunkedInsert 是现有替代。
- 交付目标：增加明确 insert_iter/update_iter，按固定 chunk_size 有界收集并提交，可选整体事务。
- 影响模块：table.py；chunked.py
- 兼容边界：保留 Sequence 接口，不把未承诺的 generator 用法误报为缺陷；各 chunk 后出现新列的策略明确。
- 正常验收：生成器惰性生成万行，逐块入库且没有二次消费，计数正确。
- 异常／边界：输入中途异常、无效行、0/负 chunk_size、空输入与整体事务回滚明确。
- 原生回归：test/test_table.py；新增 chunked 回归集合
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．自动 schema 变更预览（增强提案）

- 来源／场景：[dataset/table.py:_sync_columns/_sync_table](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/table.py)
- 原版现状：ensure=True 会立即新增表／列，没有只读展示将发生何种变更的入口。
- 交付目标：提供 preview_schema(rows)，返回拟建列、推断类型、冲突与已有列，不执行 DDL。
- 影响模块：table.py:_sync_columns；types.py
- 兼容边界：预览不隐式创建空表，不消费后无法再用调用方迭代器；调用者提供样本或明确缓冲。
- 正常验收：订单样本预览新增 currency，调用前后 sqlite_master 字节语义不变。
- 异常／边界：混合类型、全 None、非法列名、类型 override 以及与真实 ensure 的一致性回归。
- 原生回归：test/test_table.py；test/test_database.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 14．受控重命名表与列（增强提案）

- 来源／场景：[dataset/table.py:create_column/drop_column；dataset/database.py:_tables](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/table.py)
- 原版现状：已有增删列，无原生 rename_table/rename_column 便捷入口，应用需走 Alembic。
- 交付目标：提供 rename 操作，使用已有 op／dialect 能力并同步清除反射缓存。
- 影响模块：table.py；database.py 缓存；Alembic Operations
- 兼容边界：首版验证 SQLite；目标冲突拒绝，不承诺所有数据库同一 DDL 事务语义。
- 正常验收：含空格名字安全重命名，旧句柄按定义失效，数据和索引保留。
- 异常／边界：源不存在、目标存在、受外键约束或不支持方言清楚失败，不静默重建丢数据。
- 原生回归：test/test_table.py；test/test_database.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．按稳定键的游标分页（增强提案）

- 来源／场景：[dataset/table.py:Table.find](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/table.py)
- 原版现状：仅 offset/limit；大量翻页和插入并发时应用须自行拼接 keyset 条件。
- 交付目标：新增 find_after，以显式唯一排序键与 opaque 版本游标继续查询。
- 影响模块：table.py:find 与排序辅助
- 兼容边界：保留 offset；游标不含凭据，不保证未锁定快照下看见新插入的过去记录。
- 正常验收：按时间+ID 翻页无重复，升降序组合及过滤保持。
- 异常／边界：坏游标、排序定义不匹配、NULL、非唯一键和数据删除边界明确。
- 原生回归：test/test_table.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．不写原始 SQL 的分组统计（增强提案）

- 来源／场景：[dataset/table.py:Table.find/count 文档](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/table.py)
- 原版现状：文档明确 GROUP BY 走 db.query；没有 count/sum 等分组入口。
- 交付目标：提供 aggregate(group_by,measures,filters)，用 SQLAlchemy 表达式构建。
- 影响模块：table.py；util.py:ResultIter
- 兼容边界：只支持枚举聚合，不接受未验证函数名拼接；默认 row_type 保持。
- 正常验收：按城市汇总温度 count/min/max/avg，与原生 SQL 结果一致。
- 异常／边界：缺列、空组、NULL、非法聚合、同名别名冲突有明确错误。
- 原生回归：test/test_table.py；test/test_row_type.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．带显式列类型的 CSV 交换（增强提案）

- 来源／场景：[dataset/__init__.py:__all__；dataset/table.py:insert_many/find](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/__init__.py)
- 原版现状：SQL 数据库包装本身不带 CSV 文件交换接口，用户需 csv 模块手动连接。
- 交付目标：新增 import_csv/export_csv 小型适配，显式编码、列名、类型和事务，使用既有批量／结果迭代。
- 影响模块：独立 dataset CSV 适配模块；table.py 原生入口
- 兼容边界：不引入 pandas 或重建旧 datafreeze 命令；默认流所有权属于调用方。
- 正常验收：含 Unicode、逗号、双引号和空值的 CSV 导入查询导出可按既定规则往返。
- 异常／边界：坏行、重复头、类型失败、已有表不兼容不留下半批（atomic 模式），公式值按字面导出。
- 原生回归：test/test_table.py；test/test_database.py
- 真实依赖：12

## 18．SQL 执行诊断与慢查询回调（增强提案）

- 来源／场景：[dataset/database.py:create_engine/query](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/database.py)
- 原版现状：可用 SQLAlchemy events 自行埋点，dataset 无统一且默认不含绑定值的诊断接口。
- 交付目标：暴露 on_query 钩子，报告 SQL 模板、耗时、影响行数与异常类型。
- 影响模块：database.py:连接事件；table.py 写入口
- 兼容边界：默认关闭，不输出 URL 密码／绑定值，不把打印日志算功能完成。
- 正常验收：受控查询与慢模拟操作触发对应事件，原返回值不变。
- 异常／边界：异常语句、回调错误、嵌套查询重入禁止以及 close 后解绑正确。
- 原生回归：test/test_database.py；test/test_table.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．SQLite 表关系的显式外键规格（增强提案）

- 来源／场景：[dataset/database.py:create_table；on_connect_statements](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/database.py)
- 原版现状：可用 SQLAlchemy/Alembic 原生 API，但 create_table 简化规格不提供外键声明。
- 交付目标：增加首版 SQLite foreign_keys 规格，显式引用和删除策略，连接时可明确启用 foreign_keys pragma。
- 影响模块：database.py；table.py 建表；types.py
- 兼容边界：默认不改变既有 SQLite 连接行为；不推断字段名即关系，不声称服务端方言全支持。
- 正常验收：父订单／子明细建立引用，非法引用被数据库拒绝，合法关联可查询。
- 异常／边界：循环规格、缺失父列、非唯一引用和删除受限行为清楚，反射保留信息。
- 原生回归：test/test_database.py；test/test_table.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．Chunked 上下文异常时的待提交队列策略（增强提案）

- 来源／场景：[dataset/chunked.py:_Chunker.__exit__](https://github.com/pudo/dataset/blob/db592cc041014762bba55fd544e982170831f227/dataset/chunked.py)
- 原版现状：__exit__ 无论是否异常都会 flush，实际应用抛错后尚未满一批的 queued 记录仍被写入。
- 交付目标：增加 on_error=flush/discard/raise 策略，默认 flush 兼容，discard 丢弃尚未提交队列。
- 影响模块：chunked.py:_Chunker/ChunkedInsert/ChunkedUpdate
- 兼容边界：不声称可撤销此前已提交 chunk；需要全任务回滚时要求显式 with db 事务。
- 正常验收：discard 模式正常退出照常写，异常退出队列不写且原应用异常保持。
- 异常／边界：回调异常、flush 失败、重复 flush、空队列和整体事务组合明确，不吞原错误。
- 原生回归：新增 chunked 用例；test/test_table.py；test/test_database.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
