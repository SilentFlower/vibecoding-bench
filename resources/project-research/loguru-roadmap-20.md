# Loguru：二十步真实工程迭代路线

固定 [Delgan/loguru@bce5dfd3b435b1d1658507d7e095ad7a9919bf1c](https://github.com/Delgan/loguru/tree/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c)，原生证据见[单仓审查](./loguru.md)。20项都是明确增强提案，原版现状与失败示例用于说明入口缺口，不把文档允许的行为虚报缺陷。仅研究，未实施。

已有全局extra、bind/contextualize、deepcopy独立logger、多条件rotation、固定活跃文件自动时间归档、async sink与complete、自定义sink/filter/patcher等均列为现有替代，未重复计为新增。记录/配置接口和文件/队列生命周期提案分别有独立用户效果；实现、测试、文档及失败修复不拆步。所有实跑数据为本地合成普通日志，不对外发送。

## 01．按handler更新级别和过滤器

- **类型与来源**：增强提案；调试运行中的本地业务进程时，需要调整某个sink的记录范围。
- **原版现状与证据**：01_handler_update：add返回id，类无update/update_handler；现有替代是保留外部配置后remove/add。
- **交付目标**：提供update_handler(id,level/filter)的原子替换入口，保留sink和id，正确重算全局最小级别。
- **影响模块**：loguru/_logger.py、loguru/_handler.py、loguru/_filters.py。
- **兼容边界**：不变更默认sink参数；已排队记录按明确旧/新策略处理，不能无提示重开文件。
- **正常验收**：INFO改DEBUG后新调试消息被写入，另一sink范围不变，id保持。
- **边界验收**：不存在id、非法level/filter、更新与写入交错、filter闭包和异常更新不损坏旧配置。
- **原生回归**：tests/test_add_option_filter.py、tests/test_add_option_level.py、tests/test_threading.py。
- **实际依赖**：无；现有锁与handler机制。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1414)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_filters.py)。

## 02．只读handler配置快照

- **类型与来源**：增强提案；本地管理界面需要列举sink配置与状态，不能解析repr。
- **原版现状与证据**：02_handler_snapshot：repr只给id/level/sink简要描述，无handlers/get_config；私有_core不可作为稳定接口。
- **交付目标**：增加只读快照API，包含id、sink类型、级别、格式/过滤器类别、enqueue及状态，标明不可序列化callable。
- **影响模块**：loguru/_logger.py、loguru/_handler.py。
- **兼容边界**：不返回可修改核心引用；不会pickle任意sink或为了显示配置调用其业务方法；repr继续保持。
- **正常验收**：两种sink快照顺序和id正确，修改返回映射不会修改logger。
- **边界验收**：已移除sink、动态formatter、自定义对象、队列状态和多线程读取一致性明确。
- **原生回归**：tests/test_repr.py、tests/test_configure.py、tests/test_remove.py。
- **实际依赖**：无；独立于步骤01，可单独读取。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1414)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)。

## 03．自动移除的sink作用域

- **类型与来源**：增强提案；本地工具临时捕获一段日志，希望with退出无论正常或异常都释放本轮sink。
- **原版现状与证据**：03_sink_scope：add返回int而非contextmanager，无sink_context；已有手工try/finally+remove。
- **交付目标**：提供sink_context/contextmanager，进入add并返回id，退出只remove自身id，拥有的文件/队列按原关闭契约收尾。
- **影响模块**：loguru/_logger.py。
- **兼容边界**：保留add/remove原语义；不删除其他sink；用户传入流所有权按现有sink协议保持。
- **正常验收**：块内消息进入临时缓冲，退出后不再写入，外部sink继续工作。
- **边界验收**：块内异常、外部提前remove、嵌套作用域、async sink与退出错误不遮蔽原异常的策略明确。
- **原生回归**：tests/test_add_sinks.py、tests/test_remove.py、tests/test_coroutine_sink.py。
- **实际依赖**：无；标准库contextlib，不依赖更新API。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)。

## 04．上下文范围的日志静默

- **类型与来源**：增强提案；某个本地循环暂时抑制INFO，退出后恢复并不影响同时运行任务。
- **原版现状与证据**：04_scoped_silence：disable(name)是模块全局启用策略，返回None；无silence上下文。filter/contextualize可手写组合。
- **交付目标**：新增contextvars范围静默策略，可按最低级别或模块生效，退出自动恢复，避免改进程全局activation。
- **影响模块**：loguru/_logger.py、loguru/_contextvars.py。
- **兼容边界**：enable/disable原有模块语义不变；显式局部策略与全局禁用优先级固定，子任务继承遵守contextvars。
- **正常验收**：with silence(INFO)块中INFO不出、ERROR仍出，退出INFO恢复，兄弟async任务不受影响。
- **边界验收**：嵌套、线程、新任务继承、异常退出、None模块名和多sink过滤组合回归。
- **原生回归**：tests/test_contextualize.py、tests/test_activation.py、tests/test_threading.py。
- **实际依赖**：无；沿用现有contextvars兼容层。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1309)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_contextvars.py)。

## 05．有截止时间的日志收尾

- **类型与来源**：增强提案；桌面/批处理工具关闭时需要知道哪些sink尚未完成，避免无限等待而无状态。
- **原版现状与证据**：05_complete_timeout：complete只接self，timeout关键字TypeError；现版已有队列确认及async awaitable完成机制。
- **交付目标**：增加可选择deadline/timeout及完成报告，分别等待排队确认和当前loop的async任务，超时返回未完成id或抛明确异常。
- **影响模块**：loguru/_logger.py、loguru/_handler.py、loguru/_simple_sinks.py。
- **兼容边界**：不设timeout时保持原阻塞/await语义；超时不冒充消息已交付，也不能强制中断任意阻塞sink函数。
- **正常验收**：正常队列与async sink在预算内完成，报告全部完成；受控未完成任务返回准确id。
- **边界验收**：零预算、部分完成、取消、跨事件loop、remove并发和后续再次complete可接续不丢确认。
- **原生回归**：tests/test_add_option_enqueue.py、tests/test_coroutine_sink.py、tests/test_multiprocessing.py。
- **实际依赖**：无；标准库计时及现有同步原语；不做压力洪泛。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1209)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_simple_sinks.py)。

## 06．显式队列容量与满载策略

- **类型与来源**：增强提案；普通本地慢文件sink需要可预测的记录数量预算与阻塞/丢弃选择。
- **原版现状与证据**：06_queue_capacity：queue_maxsize=3被拒绝；原enqueue使用SimpleQueue，不提供按记录数容量和满队列策略。未对上游#1419的无界内存指控作结论。
- **交付目标**：增加显式容量以及block/drop_new/drop_old等受支持策略，记录丢弃计数与可查询状态。
- **影响模块**：loguru/_logger.py、loguru/_handler.py。
- **兼容边界**：默认SimpleQueue行为不变；控制消息/complete确认不能被当普通日志丢弃；不把字节pipe阻塞误称按记录容量。
- **正常验收**：合成少量记录满容量时各策略结果与丢弃计数准确，普通未满路径顺序保持。
- **边界验收**：停止/完成标记、进程退出、容量1、非法容量、超时阻塞及sink异常保证不死锁；测试使用小规模确定协作事件。
- **原生回归**：tests/test_add_option_enqueue.py、tests/test_threading.py、tests/test_multiprocessing.py。
- **实际依赖**：无；标准库队列/同步原语；独立于步骤07后端选择。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1419)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)。

## 07．仅线程队列后端

- **类型与来源**：增强提案；单进程桌面工具只需后台写入，不希望所有extra都经过多进程序列化。
- **原版现状与证据**：07_queue_backend：实际队列类multiprocessing.queues.SimpleQueue；queue_backend=thread被拒绝；现有enqueue=False可同步发送任意对象。
- **交付目标**：提供明确thread queue backend，使用queue.Queue在同进程传递记录，并限制其跨进程使用；保留默认多进程后端。
- **影响模块**：loguru/_logger.py、loguru/_handler.py。
- **兼容边界**：不能把thread后端宣称multiprocessing-safe；pickle/进程复制行为明确拒绝或要求重建；默认enqueue不变。
- **正常验收**：单进程线程后端可发送普通不可pickle业务对象给sink，按序完成与关闭。
- **边界验收**：fork/spawn后使用、混合后端、remove、异常与complete确认回归；不以更换后端取消已有正确关闭流程。
- **原生回归**：tests/test_add_option_enqueue.py、tests/test_pickling.py、tests/test_threading.py。
- **实际依赖**：无；标准库queue；不依赖步骤06容量策略。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1338)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)。

## 08．每个sink的序列化回调

- **类型与来源**：增强提案；本地JSON导出需要选择字段和编码方式，保留同时存在的人类文本sink。
- **原版现状与证据**：08_serializer_callback：serializer关键字TypeError；serialize=True固定产生text/record schema。自定义sink可用message.record自行编码，这是已有替代。
- **交付目标**：新增明确serializer(record,formatted_text)回调或协议，独立配置每sink序列化，不要求重新实现文件/队列sink。
- **影响模块**：loguru/_logger.py、loguru/_handler.py。
- **兼容边界**：默认serialize布尔行为保持；明确回调返回str/bytes与编码责任，不修改共享原record。
- **正常验收**：一个sink输出简化JSON，另一个仍原文本；回调每条只调用一次，队列前后契约一致。
- **边界验收**：回调异常、Unicode、不可JSON化值、空输出、异常record、sink类型与serialization版本标识回归。
- **原生回归**：tests/test_add_option_serialize.py、tests/test_add_sinks.py、tests/test_add_option_enqueue.py。
- **实际依赖**：无；可使用标准库json，第三方serializer由应用自行提供。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1351)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)。

## 09．默认JSON中的结构化异常帧

- **类型与来源**：增强提案；本地日志查看器希望定位异常帧文件/行号，而非重新解析美化text。
- **原版现状与证据**：09_structured_exception_frames：record.exception只有type/value/traceback布尔；text本来已包含完整格式化异常。不能声称Loguru没有序列化异常文本。
- **交付目标**：增加opt-in结构化frames与cause/context/exception-group形状，只记录稳定文件/函数/行号/源码标识，保持现有text。
- **影响模块**：loguru/_handler.py、loguru/_better_exceptions.py、loguru/_recattrs.py。
- **兼容边界**：默认schema不变；不自动把局部变量值放进frames；不得长期持有原traceback对象阻碍释放。
- **正常验收**：普通ValueError JSON额外frames顺序和行号正确，原text与exception字段保持。
- **边界验收**：无traceback异常、链式异常、ExceptionGroup、缺失源文件与深度上限使用明确截断标识。
- **原生回归**：tests/test_add_option_serialize.py、tests/test_exceptions_formatting.py、tests/test_recattr.py。
- **实际依赖**：无；标准库traceback/现有formatter，可独立于步骤08回调。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1217)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_better_exceptions.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_recattrs.py)。

## 10．按业务记录选择本地日志文件

- **类型与来源**：增强提案；商品/订单分类希望各写自己的文件，继续使用同一日志格式和轮转策略。
- **原版现状与证据**：10_record_file_routing：delay=True路径{extra[category]}.log在首条记录KeyError extra；FileSink._create_path只提供time。现有可自写router sink。
- **交付目标**：新增明确record path factory或路由文件sink，按合成业务分类选择本地目标，提供文件缓存上限与关闭淘汰策略。
- **影响模块**：loguru/_file_sink.py、loguru/_logger.py。
- **兼容边界**：普通静态/time路径不变；不能在初始化时假定已存在record；同一路径合并的规则和资源所有权清楚。
- **正常验收**：catalog/orders两类记录只进入各自文件，切换分类不丢消息且可正确轮转。
- **边界验收**：缺分类、不可用文件名、相同规范化路径、缓存淘汰、关闭/重新打开和多线程写入有边界。
- **原生回归**：tests/test_filesink_delay.py、tests/test_filesink_rotation.py、tests/test_add_sinks.py。
- **实际依赖**：无；只用本地临时目录，不接外部日志服务。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1319)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_file_sink.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)。

## 11．独立的本地归档目录

- **类型与来源**：增强提案；活跃日志写入一个本地目录，轮转归档希望进入另一个本地目录。
- **原版现状与证据**：11_archive_directory：archive_directory参数传到open后TypeError；现有compression callable能手工搬移归档。
- **交付目标**：增加可选择archive_directory/path factory，规定归档重名、压缩前后顺序与保留策略的搜索范围。
- **影响模块**：loguru/_file_sink.py、loguru/_logger.py。
- **兼容边界**：默认同目录轮转保持；不把归档功能扩为云上传；跨文件系统采用明确复制完成后删除或报不支持。
- **正常验收**：轮转后新活跃文件继续写，旧文件到指定本地档案目录，压缩/retention针对正确集合。
- **边界验收**：目录缺失、重名、复制失败、不同文件系统、空文件及停止归档策略保持文件不丢失。
- **原生回归**：tests/test_filesink_rotation.py、tests/test_filesink_compression.py、tests/test_filesink_retention.py。
- **实际依赖**：无；标准库文件操作；与步骤10按record路由可独立。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1473)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_file_sink.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)。

## 12．可选择的异常栈帧展示筛选

- **类型与来源**：增强提案；普通框架包装层很长，开发者希望日志突出自己的业务调用链。
- **原版现状与证据**：12_traceback_filter：公开add无traceback_filter参数；ExceptionFormatter内部仅有隐藏特定文件的私有机制，backtrace/diagnose不能表达任意筛选。
- **交付目标**：提供每sink的frame predicate/规则，筛选展示帧并标明省略数量，保留异常链和最终异常信息。
- **影响模块**：loguru/_logger.py、loguru/_better_exceptions.py、loguru/_handler.py。
- **兼容边界**：默认完整现有显示不变；筛选只影响呈现，不改原异常或traceback，不改变reraise语义。
- **正常验收**：去掉两个合成包装函数帧后业务帧及异常末行仍出现，显示省略标记。
- **边界验收**：所有帧被筛、predicate异常、链式/分组异常、backtrace额外帧及源文件缺失行为明确。
- **原生回归**：tests/test_exceptions_formatting.py、tests/test_exceptions_catch.py、tests/test_add_option_backtrace.py。
- **实际依赖**：无；可与步骤09结构化帧采用一致策略，但不要求其先完成。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1263)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_better_exceptions.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)。

## 13．稳定的轮转文件信息入口

- **类型与来源**：增强提案；自定义业务轮转需要读取当前文件大小和创建时间来源，避免导入私有模块。
- **原版现状与证据**：13_rotation_file_info：file_info公共方法不存在；callback已有file.name；多个rotation条件的列表组合已支持，不计新增。当前get_ctime为私有且部分平台回退mtime。
- **交付目标**：提供只读RotationFileInfo或公共读取器，包含path/size/time值及其来源标签，供自定义轮转函数使用。
- **影响模块**：loguru/_file_sink.py、loguru/_ctime_functions.py、loguru/_logger.py。
- **兼容边界**：不把mtime fallback称为真实创建时间；保持原callback(message,file)可用，以明确新协议扩展。
- **正常验收**：本地当前日志信息的路径/字节大小正确，时间来源能区分native/xattr/fallback。
- **边界验收**：延迟未创建文件、已轮转、外部替换、平台不支持元数据及读取失败有确定值/错误。
- **原生回归**：tests/test_filesink_rotation.py、tests/test_filesink_watch.py。
- **实际依赖**：无；已有os元数据函数；平台差异需保留条件测试。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1418)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_file_sink.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_ctime_functions.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)。

## 14．保留策略失败的显式处置

- **类型与来源**：增强提案；本地档案文件暂时不可删除时，调用者希望选择报错、跳过或稍后重试并得到报告。
- **原版现状与证据**：14_retention_error_policy：合成patch os.remove抛PermissionError时remove传播；retention_errors参数TypeError。仅验证受控IO失败路径，未复现真实Windows问题。
- **交付目标**：增加retention错误回调/策略，逐文件报告失败，允许有界重试或继续处理其他归档；避免最后一项掩盖前面的结果。
- **影响模块**：loguru/_file_sink.py、loguru/_logger.py、loguru/_error_interceptor.py。
- **兼容边界**：默认传播/拦截约定保持；不悄悄删除更多文件补足数量；重试只针对本轮retention候选。
- **正常验收**：三档案一项受控失败时策略报告该项，其他项按选定策略处理；error默认回归。
- **边界验收**：文件已被移除、目录、压缩文件、停止时失败、回调自身异常和重试上限明确，保留失败对象。
- **原生回归**：tests/test_filesink_retention.py、tests/test_filesink_compression.py、tests/test_remove.py。
- **实际依赖**：无；本轮故障注入明确标为模拟；Windows原场景未跑。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1495)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_file_sink.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_error_interceptor.py)。

## 15．记录原生线程编号

- **类型与来源**：增强提案；本地桌面诊断希望把日志线程与操作系统工具展示的线程关联。
- **原版现状与证据**：15_native_thread_id：RecordThread只有id/name，没有native_id；已对照threading.get_native_id取得当前系统编号，id仍是Python ident。
- **交付目标**：新增thread.native_id字段与JSON对应值，保留thread.id，不按issue建议改名旧字段。
- **影响模块**：loguru/_logger.py、loguru/_recattrs.py、loguru/_handler.py、loguru/__init__.pyi。
- **兼容边界**：Python>=3.5历史支持不变，缺get_native_id平台返回None/明确不可用；不改变旧id语义或pickle格式兼容读取。
- **正常验收**：支持平台native_id等于当前线程get_native_id，新线程和主线程分别正确。
- **边界验收**：旧Python/平台缺方法、线程退出、pickle、格式化、JSON与后台writer线程不误写成业务调用线程。
- **原生回归**：tests/test_recattr.py、tests/test_add_option_serialize.py、tests/test_threading.py、tests/test_type_hinting.py。
- **实际依赖**：无；标准库threading。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1276)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_recattrs.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)；[依据5](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/__init__.pyi)。

## 16．异步任务上下文元数据

- **类型与来源**：增强提案；同一线程有多个普通业务协程，日志需显示任务名以辨别流程。
- **原版现状与证据**：16_async_task_metadata：真实async sink经await complete成功；当前record无task字段，已有thread/process无法区分同线程任务。可用patch/contextualize手工加入。
- **交付目标**：增加可选择task记录对象，包含当前任务名及进程内稳定标识，同步调用给None，序列化明确。
- **影响模块**：loguru/_logger.py、loguru/_recattrs.py、loguru/_handler.py、loguru/__init__.pyi。
- **兼容边界**：默认记录成本/字段变动需opt-in或版本化；不创建event loop、不把writer task误当调用任务。
- **正常验收**：两个并行命名任务各自日志保留正确name，sink调度不改变来源。
- **边界验收**：同步线程、无运行loop、旧Python无get_name、任务取消、nested任务和context传播回归。
- **原生回归**：tests/test_coroutine_sink.py、tests/test_contextualize.py、tests/test_add_option_serialize.py。
- **实际依赖**：无；标准库asyncio，兼容旧运行版本。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_recattrs.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/__init__.pyi)。

## 17．模块名缩写格式策略

- **类型与来源**：增强提案；长Python模块路径占据终端空间，开发者希望保留末段并缩写包名。
- **原版现状与证据**：17_module_abbreviation：{name:short}真实ValueError；name是普通str，当前替代是patch/bind自建short_name字段。
- **交付目标**：提供明确模块名formatter/token，支持保留末N段或缩写前缀，并保留原name数据。
- **影响模块**：loguru/_logger.py、loguru/_recattrs.py、loguru/_handler.py。
- **兼容边界**：原{name}及标准宽度格式不变；不能把{name:2}原标准str宽度无提示改义；使用不冲突的显式新语法。
- **正常验收**：application.backend.catalog.service按保留末2段输出a.b.catalog.service，保留末1段时输出a.b.c.service。
- **边界验收**：None/空名称、Unicode段、单段、数字段、左右对齐/截断和动态format均不报意外格式错误。
- **原生回归**：tests/test_formatting.py、tests/test_recattr.py、tests/test_add_option_format.py。
- **实际依赖**：无；字符串格式辅助。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1400)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_recattrs.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)。

## 18．多行消息的重复前缀

- **类型与来源**：增强提案；本地商品校验报告含多行，用户希望每行都有级别/时间并能看出同一事件。
- **原版现状与证据**：18_multiline_prefix：INFO前缀只出第一行，第二行无前缀；multiline=repeat被拒绝，手写format回调是已有替代。
- **交付目标**：新增opt-in多行呈现策略，支持重复前缀与首/中/尾标记，一次记录仍有同一event上下文。
- **影响模块**：loguru/_handler.py、loguru/_logger.py、loguru/_colorizer.py。
- **兼容边界**：默认原始多行格式保持；异常栈与message分开策略，不对JSON text重复拆成独立业务record。
- **正常验收**：三行message每行带正确级别，首中尾标记符合选项，sink只接收一次记录或明确批协议。
- **边界验收**：空行、CRLF、尾换行、颜色复位、raw=True、serialize=True和异常拼接不破坏文本/JSON边界。
- **原生回归**：tests/test_add_option_format.py、tests/test_formatting.py、tests/test_add_option_colorize.py。
- **实际依赖**：无；已有颜色与formatter逻辑。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1372)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_colorizer.py)。

## 19．逐参数的惰性值包装

- **类型与来源**：增强提案；有少量昂贵值的业务日志希望与普通参数混用，并只计算实际占位的值。
- **原版现状与证据**：19_per_argument_lazy：opt(lazy=True)会执行used和未引用unused；混入普通str抛TypeError。现有全部callable模式本来支持按级别提前短路，不能声称没有lazy。
- **交付目标**：提供公开LazyValue包装器或等价协议，与普通值混用，首次实际格式化时求值并按单条事件缓存。
- **影响模块**：loguru/_logger.py、loguru/_colorizer.py、loguru/__init__.pyi。
- **兼容边界**：opt(lazy=True)旧行为保持；明确extra捕获未求值对象的序列化策略，不多sink重复计算副作用函数。
- **正常验收**：一个惰性参数加普通姓名正常输出，未引用值不执行，重复同占位同一事件只计算一次。
- **边界验收**：级别过滤、格式spec、repr转换、异常、颜色、多sink和嵌套容器行为明确，缓存不跨事件。
- **原生回归**：tests/test_opt.py、tests/test_formatting.py、tests/test_add_option_serialize.py。
- **实际依赖**：无；标准库包装类型。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/issues/1207)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_colorizer.py)；[依据4](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/__init__.pyi)。

## 20．配置集合的事务替换模式

- **类型与来源**：增强提案；本地工具切换日志方案时，第二个sink参数错误不应关闭旧方案并留下半个新方案。
- **原版现状与证据**：20_atomic_configuration：configure先remove旧handler；第一个新sink成功、第二个object TypeError后旧sink无消息，部分新sink仍写消息。此为已文档化非事务流程，按增强而非现版BUG。
- **交付目标**：增加configure_atomic或明确atomic模式，预验证/准备新资源，全部成功后切换；失败关闭本轮新资源并保留旧配置。
- **影响模块**：loguru/_logger.py、loguru/_handler.py、loguru/_file_sink.py。
- **兼容边界**：普通configure顺序和返回ids保持；无法撤销的自定义sink初始化副作用必须明示，不保证任意应用回调事务。
- **正常验收**：无效第二sink时旧方案继续接收、无新sink残留；有效两sink一次切换后各收事件。
- **边界验收**：levels/extra/activation组合、文件打开失败、排队未完成、资源关闭失败及并发写入的切换点明确。
- **原生回归**：tests/test_configure.py、tests/test_remove.py、tests/test_threading.py。
- **实际依赖**：无；标准库与现有资源/锁；不依赖步骤01增量更新。 功能步骤依赖：无。
- **源码/原始来源**：[依据1](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_logger.py)；[依据2](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_handler.py)；[依据3](https://github.com/Delgan/loguru/blob/bce5dfd3b435b1d1658507d7e095ad7a9919bf1c/loguru/_file_sink.py)。

## 独立冻结验收边界

未来控制端冻结每步真实原生调用和小规模确定协作场景，检查实际sink输出、队列计数/完成、文件内容/归档位置、格式化record与资源关闭状态。超时用独立进程预算；不能依靠声称timeout的候选阻止永久阻塞。每步累计运行相关原生回归和此前接受能力。完整原版1679通过不证明这些新契约已经通过；离线依赖准备、冻结用例与平台接入尚未完成。
