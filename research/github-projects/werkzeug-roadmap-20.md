# Werkzeug：二十步真实工程迭代路线

固定 [pallets/werkzeug@665e760ca6325a348ce03e5cf780b17e4be01848](https://github.com/pallets/werkzeug/tree/665e760ca6325a348ce03e5cf780b17e4be01848)，原版证据见[单仓审查](./werkzeug.md)。2项已复现修复提案、18项明确增强提案；仅研究，未实现或运行提案验收。所有拟议API名称均不是现版承诺。

每步是一个完整用户可见交付，包含实现、测试、文档与失败修复。现有低层扩展点及手工替代明确保留，不把API类别或测试矩阵拆成步骤。所有匹配、文件和表单样本均在本地使用合成普通业务数据；不做网络策略、账号或外部系统研究。

## 01．稳定同权重路由的注册优先级

- **类型与来源**：原版已复现修复提案；官方 #3156；两个同优先级 converter 都能处理商品名，注册顺序应稳定。
- **原版现状与证据**：01_route_priority：原版 /foo 先命中 one；加入不可能匹配该地址的 /<string:value>/no_match 后变为 two。StateMachineMatcher 以 RulePart 合并动态状态再按 weight 排序，影响同权重跨状态规则。
- **交付目标**：保持相同权重候选之间的声明顺序，不让无关规则引起既有规则相对优先级改变；覆盖状态共享与终态候选。
- **影响模块**：src/werkzeug/routing/matcher.py、src/werkzeug/routing/rules.py。
- **兼容边界**：静态优先、converter weight、严格斜杠与方法匹配规则保持；只恢复同权重既有注册顺序，不按端点名字排序。
- **正常验收**：反例中添加无关规则前后都命中 one，调换两个业务规则顺序时都命中 two。
- **边界验收**：共享前缀、多个动态段、不同方法、部分隔离 converter 与重复规则拒绝回归；不把同一缺陷的测试矩阵拆步。
- **原生回归**：tests/test_routing.py。
- **实际依赖**：无；标准库状态机与当前路由系统。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/issues/3156)；[来源2](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/routing/matcher.py)；[来源3](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/routing/rules.py)。

## 02．修复分块表单的尾部字节一致性

- **类型与来源**：原版已复现修复提案；官方 #3285；普通表单空字段按不同读取块到达应得到相同内容。
- **原版现状与证据**：02_multipart_chunks：同一空字段完整输入得到空字节，逐字节输入变为 0d。已在固定提交 sansio.MultipartDecoder 上实跑，未使用外部请求。
- **交付目标**：修正部分边界缓冲与正文 CRLF 的归属，使字段和文件字节不随 chunk 划分改变。
- **影响模块**：src/werkzeug/sansio/multipart.py。
- **兼容边界**：保留合法正文中的真实 CR/LF；不简单 rstrip；状态和事件序列接口保持。
- **正常验收**：同一空字段及普通文件按整块、单字节和边界邻近拆分得到一致字节。
- **边界验收**：正文末尾真的含 CR/LF、空文件、多个 part、连续 NeedData 和结束事件只按同一修复交付回归。
- **原生回归**：tests/sansio/test_multipart.py、tests/test_formparser.py。
- **实际依赖**：无；已有 sansio decoder。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/issues/3285)；[来源2](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/sansio/multipart.py)。

## 03．重复参数的类型转换诊断

- **类型与来源**：研究者增强提案；批量商品数量表单包含有效整数与文字，页面需准确指出第几个值不可转换。
- **原版现状与证据**：03_conversion_report：getlist(quantity,type=int) 把 [2,many,3] 变成 [2,3] 并丢弃错误位置；该行为是文档约定。无 convert_report，现有替代是手工遍历。
- **交付目标**：提供独立转换报告入口，返回每个原始索引、成功值或失败原因，并可选择聚合失败。
- **影响模块**：src/werkzeug/datastructures/structures.py。
- **兼容边界**：get/getlist 的默认忽略和缺省逻辑不变；不把业务转换异常堆栈作为用户输出；仅约定 TypeError/ValueError 为转换失败。
- **正常验收**：三项输入返回两项成功与索引 1 的错误，顺序和重复值保留。
- **边界验收**：缺失键、空列表、转换器返回 None、TypeError 及其他异常的传播约定明确；不修改原 MultiDict。
- **原生回归**：tests/test_datastructures.py。
- **实际依赖**：无；已有泛型 MultiDict。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/datastructures/structures.py)。

## 04．组合参数的来源查询

- **类型与来源**：研究者增强提案；查询参数和表单都有 page，开发者需解释最终值与被遮蔽来源。
- **原版现状与证据**：04_parameter_origin：CombinedMultiDict 返回首个 page=2、全值 [2,3]，没有 get_sources；copy 已经可拍摄快照，不能把 copy 作为新功能。
- **交付目标**：为组合视图提供 get_sources(key) 或带来源标签的迭代，返回映射序号、该映射值列表和取值优先级。
- **影响模块**：src/werkzeug/datastructures/structures.py。
- **兼容边界**：旧 __getitem__/getlist 和底层映射实时视图语义保持；来源 API 不暴露映射之外的数据。
- **正常验收**：query/form 分别返回来源 0/1，并标出实际 first-value 来源。
- **边界验收**：空底层映射、缺失键、重复对象、底层后续变化和转换器跳过无效来源的说明可验证。
- **原生回归**：tests/test_datastructures.py。
- **实际依赖**：无；不依赖步骤 03。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/datastructures/structures.py)。

## 05．显式重复参数合并策略

- **类型与来源**：研究者增强提案；商品筛选默认 tag 与用户 tag 需要明确 append、replace 或保留默认策略。
- **原版现状与证据**：05_merge_policy：MultiDict.update 永远追加，base/next 得 [base,next]，没有 merge；当前可用手工 setlist/update 组合。
- **交付目标**：新增独立 merge(mapping,policy=...) 返回新 MultiDict，支持 append、replace、keep 与冲突时报错，给出确定空值处理。
- **影响模块**：src/werkzeug/datastructures/structures.py。
- **兼容边界**：现有 update 和 | 运算的追加语义不变；不改变输入映射，保留所有重复值的相对顺序。
- **正常验收**：相同两个输入在三种策略下得到各自明确结果，冲突策略报告实际键。
- **边界验收**：空列表、生成器输入、不可哈希键、相同映射和失败时原对象完整保持。
- **原生回归**：tests/test_datastructures.py。
- **实际依赖**：无；与来源诊断和类型转换独立。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/datastructures/structures.py)。

## 06．只取走一个重复值

- **类型与来源**：研究者增强提案；本地表单向导逐项消费待办步骤，取首项后需要保留后续项。
- **原版现状与证据**：06_pop_one：pop(step) 返回 first，但 second 也被丢弃；pop/poplist 均有既定语义，源码无 popone。
- **交付目标**：新增 popone(key,index=0) 或等价独立 API，只移除指定一个值；最后一个值移除后删除键。
- **影响模块**：src/werkzeug/datastructures/structures.py。
- **兼容边界**：不改变原 pop 删除整个键语义；遵守可变与不可变类型边界，明确负索引与 default 规则。
- **正常验收**：[first,second] 首次取 first 后余 [second]，再次取后键不存在。
- **边界验收**：缺失键、空列表、超界索引、重复相同值和不可变映射拒绝写入不破坏状态。
- **原生回归**：tests/test_datastructures.py。
- **实际依赖**：无；独立于步骤 05。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/datastructures/structures.py)。

## 07．响应元数据批量更新的事务模式

- **类型与来源**：研究者增强提案；本地生成多个响应描述头时，标题对象格式化失败不应留下半套新元数据。
- **原版现状与证据**：07_headers_atomic：Headers.update 先把 X-Count=1 改为 2，后续普通对象 __str__ 抛 ValueError，已写的值仍保留。原 API 没有原子承诺。
- **交付目标**：提供 update_atomic 或 atomic=True 选择，先在临时 Headers 完成格式化和校验，成功后替换目标内容。
- **影响模块**：src/werkzeug/datastructures/headers.py。
- **兼容边界**：原 update 默认语义保持；保留大小写不敏感查询、同名多值、顺序和现有值格式校验。
- **正常验收**：有效整批更新同时生效；格式化失败后 to_wsgi_list 与调用前完全一致。
- **边界验收**：列表型值、空更新、生成器中途失败、重复大小写键及子类行为明确；不吞源异常。
- **原生回归**：tests/test_datastructures.py、tests/test_wrappers.py。
- **实际依赖**：无；仅操作内存元数据，不涉及外部服务。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/datastructures/headers.py)。

## 08．本地文件原子保存选项

- **类型与来源**：研究者增强提案；导入商品 CSV 失败时需要保留已有本地文件。
- **原版现状与证据**：08_file_atomic_save：已有 old-records 被 save 以 wb 打开；合成源第一次返回 new、第二次 OSError 后目标只剩 new。save 没有 atomic 参数；这是新增保存保证。
- **交付目标**：新增显式 atomic 保存到同目录临时文件，完整复制后替换；失败清理本轮临时文件并保留已有目标。
- **影响模块**：src/werkzeug/datastructures/file_storage.py。
- **兼容边界**：普通 save 和传入文件对象保持；文件对象不承诺可回滚；目标路径由调用者明确给定，不从 filename 自动推断。
- **正常验收**：完整 CSV 替换目标；读取中断时旧目标字节不变且无临时残留。
- **边界验收**：目标不存在、空文件、写入/替换失败、权限错误及不同 buffer_size 均验证；不承诺断电持久性或跨文件系统事务。
- **原生回归**：tests/test_datastructures.py、tests/test_formparser.py。
- **实际依赖**：无；标准库 tempfile/os；与步骤 09 独立。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/datastructures/file_storage.py)。

## 09．带大小与摘要的文件保存回执

- **类型与来源**：研究者增强提案；本地导入任务保存 CSV 后需记录实际传输大小与内容摘要，避免再读一次文件。
- **原版现状与证据**：09_file_save_receipt：原 save 成功返回 None，样本实际20字节，sha256由研究脚本额外读取计算；无 save_with_receipt。
- **交付目标**：新增独立保存回执入口，单次复制返回实际字节数和显式算法摘要，可选在每块后回调累计进度。
- **影响模块**：src/werkzeug/datastructures/file_storage.py。
- **兼容边界**：原 save 返回 None 保持；回执依据实际读取，不信任 content_length；自带文件对象不由工具关闭。
- **正常验收**：回执大小20且摘要与对照文件一致，进度单调最终等于20。
- **边界验收**：空文件、从非零 stream 位置保存、非 seekable 源、回调抛错、未知摘要算法和短写处理明确。
- **原生回归**：tests/test_datastructures.py。
- **实际依赖**：无；标准库 hashlib；可与步骤 08 组合但不依赖其原子保证。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/datastructures/file_storage.py)。

## 10．文件集合的结构化资源作用域

- **类型与来源**：研究者增强提案；测试和本地导入工具一次处理多个同名文件，希望异常退出也自动关闭它们。
- **原版现状与证据**：10_file_collection_context：FileMultiDict 已有 close/clear；实际 close 可关闭流，但无 __enter__，调用者需自行 try/finally。
- **交付目标**：增加上下文管理协议或显式 owned_files 作用域，退出时关闭集合内拥有的文件，支持重复对象去重关闭。
- **影响模块**：src/werkzeug/datastructures/file_storage.py。
- **兼容边界**：不把现有 close/clear 当新增；资源所有权显式定义，借用流可 opt-out；退出不额外清除普通 MultiDict 内容。
- **正常验收**：两个同名文件在正常和异常退出时都关闭；块内仍可正常读取。
- **边界验收**：同一流被加入多次、提前关闭、关闭失败与新增文件期间异常都按明确定义执行，避免遮蔽原异常。
- **原生回归**：tests/test_datastructures.py、tests/test_test.py。
- **实际依赖**：无；标准库上下文协议。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/datastructures/file_storage.py)。

## 11．批量反向构建链接的结果集合

- **类型与来源**：研究者增强提案；本地邮件/报表一次构造多个商品链接，希望完整收集缺失 id 而非首错中断。
- **原版现状与证据**：11_build_many：MapAdapter.build 单项成功为 /items/3，缺 id 抛 BuildError；无 build_many，现有替代是应用自己循环。
- **交付目标**：新增 build_many，接收有序 endpoint/values/method 项，逐项返回 URL 或结构化失败，支持显式 fail-fast。
- **影响模块**：src/werkzeug/routing/map.py、src/werkzeug/routing/exceptions.py。
- **兼容边界**：单项 build 不变；不吞任意自定义 converter 程序错误；结果不根据 endpoint 排序而破坏输入对应。
- **正常验收**：有效、缺值、未知端点三项同时得到相同次序结果；fail-fast 仅处理到错误项。
- **边界验收**：空输入、生成器输入、MultiDict query、外部/相对 URL 和 Unicode 值保持单项 build 语义。
- **原生回归**：tests/test_routing.py。
- **实际依赖**：无；仅本地 URL 构建，不发请求。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/routing/map.py)；[来源2](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/routing/exceptions.py)。

## 12．路由匹配的只读解释结果

- **类型与来源**：研究者增强提案；开发者需解释商品地址为什么是404/405或落到某个 converter，而非执行视图。
- **原版现状与证据**：12_match_explanation：正常 match 返回 item 和 item_id=3，POST 抛 MethodNotAllowed；无 explain_match，当前只能读异常或调试内部状态。
- **交付目标**：新增 explain_match，返回静态/动态候选、converter校验、方法与斜杠拒绝原因及最终选择，明确有界轨迹。
- **影响模块**：src/werkzeug/routing/map.py、src/werkzeug/routing/matcher.py。
- **兼容边界**：match 快速路径与异常保持；解释模式显式开启，不保存全局轨迹，也不执行视图。
- **正常验收**：GET 选择理由与 match 一致，POST 说明允许 GET/HEAD 而非笼统失败。
- **边界验收**：轨迹预算、复杂共享前缀、redirect、converter异常和未匹配路径均有终态；不可把截断轨迹当完整候选集合。
- **原生回归**：tests/test_routing.py。
- **实际依赖**：无；解释已有匹配过程，可独立于步骤 01 交付，结果以对应 matcher 为准。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/routing/map.py)；[来源2](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/routing/matcher.py)。

## 13．保留十进制业务值的路由转换器

- **类型与来源**：研究者增强提案；价格筛选路径需要准确的 Decimal，而非二进制浮点近似。
- **原版现状与证据**：13_decimal_converter：/price/0.1 得 float，Decimal.from_float 显示0.10000000000000000555…；注册表没有 decimal。FloatConverter 已明确记录近似，不是精度 BUG。
- **交付目标**：新增 DecimalConverter，支持可选小数位数、正负与范围，match 返回 Decimal，build 输出明确规范化十进制字符串。
- **影响模块**：src/werkzeug/routing/converters.py。
- **兼容边界**：float/int 语义不变；新 converter 显式注册/采用；精度上下文、量化与拒绝策略先确定，不静默舍入。
- **正常验收**：价格0.1得到精确Decimal("0.1")，符合两位小数策略的值可往返构建。
- **边界验收**：超范围、负值、尾零、指数表示、非有限值和无法按规定精度表示的值有确定拒绝。
- **原生回归**：tests/test_routing.py。
- **实际依赖**：无；标准库 decimal。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/routing/converters.py)。

## 14．日历日期路由转换器

- **类型与来源**：研究者增强提案；按日归档的商品报表希望使用真正 date，避免每个视图重复校验日历。
- **原版现状与证据**：14_date_converter：构建含 date converter 的规则 LookupError；目前只能 string+业务解析或注册自定义 converter。
- **交付目标**：新增 ISO 日期 converter，返回 datetime.date，build 接受 date 并校验可选上下界，不把 datetime 无提示截断。
- **影响模块**：src/werkzeug/routing/converters.py。
- **兼容边界**：不改变 string 路由；明确仅 YYYY-MM-DD，不把任意用户格式或时区解析带入路由。
- **正常验收**：/archive/2024-02-29 返回正确 date，构建同对象得到相同路径。
- **边界验收**：非闰年2月29、缺少零填充、上下界、date最小/最大值及datetime传入规则明确。
- **原生回归**：tests/test_routing.py。
- **实际依赖**：无；标准库 datetime，与 Decimal converter 是不同业务契约。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/routing/converters.py)。

## 15．应用枚举类型路由转换器

- **类型与来源**：研究者增强提案；订单状态视图使用Python Enum，既希望静态限定合法段，也希望返回真实成员。
- **原版现状与证据**：15_enum_converter：AnyConverter 返回 str draft，build(State.DRAFT) ValueError；内建注册表没有 enum。AnyConverter 已能限制字符串，不能宣称有限候选匹配不存在。
- **交付目标**：提供绑定 Enum 类的 converter 工厂，明确按成员值或名称匹配，返回 Enum 成员并支持反向构建。
- **影响模块**：src/werkzeug/routing/converters.py。
- **兼容边界**：AnyConverter 保持字符串语义；Enum类由应用代码传入，不通过字符串动态求值导入；成员值必须是明确支持的标量。
- **正常验收**：draft 匹配 State.DRAFT，build 同成员得到 draft，视图不用二次转换。
- **边界验收**：别名、重复值、大小写、非字符串value、未知成员和其他Enum类传入均定义，不模糊接受。
- **原生回归**：tests/test_routing.py。
- **实际依赖**：无；标准库 enum，与日期/金额是独立输出类型及验收。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/routing/converters.py)。

## 16．测试客户端请求记录作用域

- **类型与来源**：研究者增强提案；本地业务流程跨三个请求，测试希望统一断言顺序、输入与响应而非保存每个临时变量。
- **原版现状与证据**：16_client_recording：Client 无 record/requests；TestResponse 已有单请求 request 和重定向 history，不把这些重做为新功能。
- **交付目标**：增加 opt-in 记录上下文，按调用次序保存请求摘要、响应状态和受控体片段，支持过滤，退出停止记录。
- **影响模块**：src/werkzeug/test.py。
- **兼容边界**：默认客户端不记录；不自动重读已消费输入流；重定向跳转与顶层调用的分组关系明确。
- **正常验收**：三个请求记录顺序正确，响应仍可常规使用；退出后不再追加，另一个客户端不受影响。
- **边界验收**：异常视图、流式响应、重定向、嵌套记录和体大小截断标记正确；不以记录层消费整个流。
- **原生回归**：tests/test_test.py。
- **实际依赖**：无；现有Client/TestResponse。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/test.py)。

## 17．带消费预算的流式测试助手

- **类型与来源**：研究者增强提案；本地导出生成器测试需要逐chunk检查且在异常无限输出时及时退出。
- **原版现状与证据**：17_stream_budget_helper：Response 已有 iter_encoded；get_data 只接收 as_text，没有限制总字节/块数的测试消费入口。
- **交付目标**：为 TestResponse 增加 iter_chunks/consume_stream helper，支持显式最大字节及chunk数、计数结果与关闭策略，超预算抛可识别测试错误。
- **影响模块**：src/werkzeug/test.py、src/werkzeug/wrappers/response.py。
- **兼容边界**：不改变普通 Response 流传输与 get_data；该助手仅是受控测试工具，不声称可强制终止单次阻塞生成器调用。
- **正常验收**：两个chunk保持顺序与字节内容，累计计数准确；预算不足时可靠失败。
- **边界验收**：空chunk、空流、最后一块跨预算、异常生成器和提前关闭均执行close；超时仍由外层测试进程控制。
- **原生回归**：tests/test_test.py、tests/test_wrappers.py。
- **实际依赖**：无；现有关闭迭代器契约。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/test.py)；[来源2](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/wrappers/response.py)。

## 18．表单解析诊断对象

- **类型与来源**：研究者增强提案；开发者调试普通不完整导入夹具时，需区分合法空表单和未解析完成。
- **原版现状与证据**：18_form_diagnostics：合成缺少结尾的表单在 Request.form 中返回空映射，无 form_parse_error；源码默认 silent 捕获 ValueError。旧 FormDataParser 已弃用，不把它作为未来唯一扩展入口。
- **交付目标**：在受支持的 Request._parse_form_data 路径保存可选只读诊断，给出阶段、part序号和原因；业务可明确选择抛错或保留原空结果。
- **影响模块**：src/werkzeug/wrappers/request.py、src/werkzeug/formparser.py、src/werkzeug/sansio/multipart.py。
- **兼容边界**：默认兼容原空表单行为；已有请求体/字段/part资源上限保持；诊断默认不复制正文。
- **正常验收**：有效空表单标记成功；不完整夹具标记失败并给出阶段，合法字段不误报。
- **边界验收**：未知mimetype、缺少必要参数、文本解码失败与底层IO异常的归属明确；缓存读取不重复解析。
- **原生回归**：tests/test_formparser.py、tests/sansio/test_multipart.py、tests/test_wrappers.py。
- **实际依赖**：无；可独立于步骤02修复，但回归兼容其正常字节处理。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/wrappers/request.py)；[来源2](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/formparser.py)；[来源3](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/sansio/multipart.py)。

## 19．高级表单分段迭代入口

- **类型与来源**：研究者增强提案；本地批量导入希望按part处理表单字段与文件，而非先等完整form/files集合。
- **原版现状与证据**：19_part_iterator：Request.form 可正常读取中文字段，但 Request 无 iter_parts；低层 MultipartDecoder 事件API已存在，现有替代是应用自行连接限流输入、decoder、临时流与清理。
- **交付目标**：提供受支持的上下文式 iter_parts，输出带字段名/元数据的字段与文件块，明确当前part完成和关闭后再取下一part的契约。
- **影响模块**：src/werkzeug/wrappers/request.py、src/werkzeug/formparser.py、src/werkzeug/sansio/multipart.py。
- **兼容边界**：不把现有低层事件当新增；与 Request.form/files 是显式互斥读取模式，第二种消费方式清楚报错，现有资源限制继续适用。
- **正常验收**：两字段两文件按原始顺序处理，无需在内存保存全部文件，累计内容与普通解析相同。
- **边界验收**：提前退出、跳过part、空文件、同名字段、原始流已消费及底层异常全部清理本轮临时资源。
- **原生回归**：tests/test_formparser.py、tests/test_wrappers.py、tests/sansio/test_multipart.py。
- **实际依赖**：无；标准库临时文件和已有decoder；不依赖步骤18诊断对象。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/wrappers/request.py)；[来源2](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/formparser.py)；[来源3](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/sansio/multipart.py)。

## 20．本地流式NDJSON读取助手

- **类型与来源**：研究者增强提案；测试/导入客户端需要读取本地商品NDJSON响应，保留逐条消费和行号。
- **原版现状与证据**：20_ndjson_reader：Response 无 iter_json_lines；强制 get_json 读取两行样本 JSONDecodeError Extra data。原 get_json 面向单份JSON，行为正确。
- **交付目标**：增加独立 iter_json_lines，跨chunk拼接UTF-8行并委托json_module.loads，输出逐行对象，可设行长度和总记录预算。
- **影响模块**：src/werkzeug/wrappers/response.py、src/werkzeug/test.py。
- **兼容边界**：不改变 .json/get_json 和NDJSON mimetype判断；空行策略、末行无换行与错误记录行为显式定义，不能静默吞损坏行。
- **正常验收**：两个对象分散在多个chunk时仍按行正确读取，Unicode跨chunk不损坏，首条不要求读完整响应。
- **边界验收**：空输入、CRLF、末行无换行、无效JSON、超行长、提前关闭与自定义json_module均验证行号和清理。
- **原生回归**：tests/test_wrappers.py、tests/test_test.py。
- **实际依赖**：无；标准库json与增量解码；与Flask输出助手属于不同仓库原生入口，未共享代码或计成同源项目。 功能步骤依赖：无。
- **源码/官方来源**：[来源1](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/wrappers/response.py)；[来源2](https://github.com/pallets/werkzeug/blob/665e760ca6325a348ce03e5cf780b17e4be01848/src/werkzeug/test.py)。

## 冻结验收与累计回归边界

未来控制端应按每步正常/边界条件冻结原生API输入，检查匹配结果、表单字节、重复值顺序、文件真实内容与资源关闭状态；核对候选加载路径，累计运行此前接受能力与关联原生回归。1019项原生通过只证明原版本身的适用基线，不能证明尚未实施的20步已通过。依赖离线准备、冻结验收和平台接入均尚未进行。
