# Boltons：二十步真实工程迭代路线

固定 [mahmoud/boltons@4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d](https://github.com/mahmoud/boltons/tree/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d)，详见[单仓审查](./boltons.md)。共 20 步：14 项增强提案、6 项问题修复。接口名是本试点拟议契约；本轮未实施，不以接口检查代替完成验收。

## 01．文本暂存流切换磁盘后保留未读字符（问题修复）

- 来源／场景：https://github.com/mahmoud/boltons/issues/581
- 原版现状：SpooledStringIO.readline 产生解码预读，rollover 按底层字节位置定位丢掉未读缓冲；实际下一次 read 返回空。
- 交付目标：磁盘切换／fileno 触发后按逻辑字符位置恢复读取。
- 影响模块：ioutils.py:SpooledStringIO.rollover/readline
- 兼容边界：保留文件全部内容、tell 字符语义与已有 seek 行为。
- 正常验收：读取 first 换行后切换，后续得到 last；显式和自动切换一致。
- 异常／边界：多字节 Unicode、readlines、EOF、重复 rollover、关闭流回归；不能只为 ASCII 修补。
- 原生回归：tests/test_ioutils.py；ioutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 02．自定义 tzinfo 的时区感知判定（问题修复）

- 来源／场景：https://github.com/mahmoud/boltons/issues/566
- 原版现状：以 bool(tzinfo) 判断感知；utcoffset=None 抛 TypeError，falsey 的 +02 时区错误多两小时，已实测。
- 交付目标：按 utcoffset 是否 None 判断，保持无时区视作 UTC 的承诺。
- 影响模块：timeutils.py:dt_to_timestamp
- 兼容边界：不改普通 datetime 和 naive-UTC 规则；自定义时区异常继续传播。
- 正常验收：两种自定义时区得到 -0.5 和 0，与 datetime.timestamp 对照。
- 异常／边界：负时间戳、非整小时偏移、UTC 零点、tzinfo 自身抛错。
- 原生回归：tests/test_timeutils.py；timeutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 03．多分支替换保留预编译正则 flags（问题修复）

- 来源／场景：https://github.com/mahmoud/boltons/issues/565
- 原版现状：预编译对象只取 .pattern，re.I 被丢弃；CAT cat 实际只替换后者。
- 交付目标：每个分支保留自身 flags，避免将分支 flags 全局合并泄漏。
- 影响模块：strutils.py:MultiReplace.__init__/_get_value
- 兼容边界：构造器全局 flags 和字面替换规则保持，分支优先级仍按输入顺序。
- 正常验收：I/M/S/X/A 模式分别正常，同一个替换器里互不污染。
- 异常／边界：VERBOSE 末尾注释、内联 flags、捕获组、Unicode 和空映射保持。
- 原生回归：tests/test_strutils.py；strutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 04．重复项检测尊重 falsey callable（问题修复）

- 来源／场景：https://github.com/mahmoud/boltons/issues/553
- 原版现状：合法 callable 通过验证后又用 truthiness 决定是否调用，FalseKey 被忽略。
- 交付目标：只把 None 视为没有 key，对所有合法 callable 调用归一化。
- 影响模块：iterutils.py:redundant
- 兼容边界：仍返回首个重复值而非第一个原值，groups 保序。
- 正常验收：a/A 经 FalseKey 得到 A，与 unique 的互补规则一致。
- 异常／边界：__len__=0 callable、不可哈希输入经 key 归一化、非 callable 拒绝。
- 原生回归：tests/test_iterutils.py 的 redundant/unique；iterutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 05．异构排序每元素仅求值一次 key（问题修复）

- 来源／场景：https://github.com/mahmoud/boltons/issues/551
- 原版现状：key 在比较中重算；本轮 3 元素记录 8 次调用，单元素 key 的 ZeroDivisionError 被跳过。
- 交付目标：比较包装器预存 key 值，保持 sorted 的每元素一次求值约定。
- 影响模块：iterutils.py:untyped_sorted
- 兼容边界：异构类型间已有排序退路、稳定性和 reverse 保持，不保证跨解释器类型顺序。
- 正常验收：三项 key 调用正好三次，结果及相等 key 相对次序正确。
- 异常／边界：单元素错误要传播；空集、重复对象、FalseKey、不可比较同类对象保持现有错误。
- 原生回归：tests/test_iterutils.py；iterutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 06．字节单位在舍入后可规范晋级（增强提案）

- 来源／场景：https://github.com/mahmoud/boltons/issues/524
- 原版现状：bytes2human(1048575) 是 1024K，属于现有先选单位再舍入策略。
- 交付目标：增加可选 normalize_rounding，使显示到 1024 时晋升下一单位。
- 影响模块：strutils.py:bytes2human
- 兼容边界：默认现有字符串保持；不将合法但不理想的显示策略统称缺陷。
- 正常验收：启用后 1048575 显示 1M，不同 ndigits 正确进位。
- 异常／边界：负数、0、极值、最大 Y 单位和不晋级对照，非法精度拒绝。
- 原生回归：tests/test_strutils.py；strutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 07．包装函数保留仅限位置参数签名（问题修复）

- 来源／场景：https://github.com/mahmoud/boltons/issues/510
- 原版现状：编译的 wrapper 丢失 /，原函数允许 original(1,a=2)，wrapped 抛重复参数错误；已复现。
- 交付目标：FunctionBuilder 生成签名保留 posonlyargs 并正确转发参数。
- 影响模块：funcutils.py:wraps/update_wrapper/FunctionBuilder
- 兼容边界：保留名称、文档、injected/expected 和 keyword-only 语义。
- 正常验收：inspect 与真实调用均支持 a 为位置参数、同名 a 留在 **kw。
- 异常／边界：默认位置参数、斜杠与星号并存、partial、hide_wrapped 和非法关键字回归。
- 原生回归：tests/test_funcutils_fb_py3.py；tests/test_funcutils.py；funcutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 08．按月日期序列显式选择月底策略（增强提案）

- 来源／场景：https://github.com/mahmoud/boltons/issues/500
- 原版现状：从 1 月 31 日按月迭代会在短月 replace 时抛日期错误，预期兼容策略上游尚未定。
- 交付目标：新增 month_policy=raise/clamp/anchor_end，默认 raise；明确按锚点而非默默日期漂移。
- 影响模块：timeutils.py:daterange
- 兼容边界：不改变默认非法日期行为；只 opt-in 保月底，并保留负向和年份步进。
- 正常验收：anchor_end 得 1/31、2/29、3/31，clamp 按约定，普通每日不变。
- 异常／边界：非月底锚点、闰年、反向、stop 包含与非前进步长拒绝。
- 原生回归：tests/test_timeutils.py；timeutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 09．JSONL 自定义 JSON 解码钩子（增强提案）

- 来源／场景：[boltons/jsonutils.py:JSONLIterator 与 TODO](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/jsonutils.py)
- 原版现状：固定调用 json.loads(line)，不接受 parse_float/object_pairs_hook 等；源码有 passthrough TODO。
- 交付目标：接收经校验的 loads_kwargs 或显式 decoder，支持 Decimal 等合法 JSON 解析。
- 影响模块：jsonutils.py:JSONLIterator.__init__/next
- 兼容边界：默认解码与 ignore_errors 不变；不执行文件中代码，钩子来自调用方。
- 正常验收：JSONL 小数经 Decimal 保真，顺序读取和 reverse 都正确。
- 异常／边界：未知 kwargs、钩子异常的 strict/ignore 规则明确，不吞掉调用方系统异常。
- 原生回归：tests/test_jsonutils.py；jsonutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 10．JSONL 错行结构化诊断（增强提案）

- 来源／场景：[boltons/jsonutils.py:JSONLIterator.next](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/jsonutils.py)
- 原版现状：ignore_errors 只有跳过开关，跳过了哪些行没有回调；CLI 只粗略显示 byte 附近。
- 交付目标：提供 on_error 诊断回调，含方向、行／字节位置和异常类型，默认不带内容。
- 影响模块：jsonutils.py:JSONLIterator；模块 CLI
- 兼容边界：原返回迭代项不包额外 tuple，默认不记录 JSON 敏感值。
- 正常验收：合法—坏行—合法输入得两条记录及一条位置诊断。
- 异常／边界：反向定位、空行、回调抛错、非 seekable 正向流和截断尾行行为明确。
- 原生回归：tests/test_jsonutils.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 11．JSONL 单行读取上限（增强提案）

- 来源／场景：[boltons/jsonutils.py:JSONLIterator 与 reverse_iter_lines](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/jsonutils.py)
- 原版现状：行读取／反向 buff 可增长到整条超长记录，没有 max_line_bytes。
- 交付目标：增加可选单行字节上限，越界明确抛错或按显式策略跳过。
- 影响模块：jsonutils.py:正向和反向分块读取
- 兼容边界：默认无限制兼容；界限按编码字节，非字符数，不声称全文件内存固定。
- 正常验收：小 blocksize 下跨块 JSON 行可读，超上限在继续增长前终止。
- 异常／边界：Unicode 跨块、无尾换行、正反向、极小／非法上限与 ignore_errors 组合。
- 原生回归：tests/test_jsonutils.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 12．原生 JSONL 写入器（增强提案）

- 来源／场景：[boltons/jsonutils.py:__all__](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/jsonutils.py)
- 原版现状：模块只导出 JSONLIterator 与 reverse_iter_lines，没有配套逐条 JSONLWriter。
- 交付目标：提供流式 writer.write/write_all，显式编码、flush 及 append 路径模式。
- 影响模块：jsonutils.py；fileutils.py 可选原子整批发布
- 兼容边界：不替调用方关闭提供的流；不把内嵌换行变成多条记录。
- 正常验收：逐条写订单再由 JSONLIterator 读回，Decimal 等使用显式 encoder。
- 异常／边界：不可序列化对象不写半条；空流、缺尾换行的 append 策略和写入失败明确。
- 原生回归：tests/test_jsonutils.py；tests/test_fileutils.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 13．原子保存的合作写入冲突检测（增强提案）

- 来源／场景：[boltons/fileutils.py:AtomicSaver.__init__ 的 TODO](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/fileutils.py)
- 原版现状：临时文件防半写，但没有检测目标在编辑期间被其他合作写者改动。
- 交付目标：新增 expected_digest 和合作锁选项，锁覆盖读取预期—发布，陈旧内容拒绝。
- 影响模块：fileutils.py:AtomicSaver.setup/__exit__
- 兼容边界：默认覆盖语义保持；限定本地 POSIX 合作写者，不承诺非合作写者或网络盘全局一致。
- 正常验收：两个受控写者更新不静默覆盖，陈旧预期报冲突并保留新文件。
- 异常／边界：目标从无到有／被删除、异常后锁释放、part 文件冲突和 rm_part_on_exc 保持。
- 原生回归：tests/test_fileutils.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 14．原子保存可选同步父目录（增强提案）

- 来源／场景：[boltons/fileutils.py:AtomicSaver.__exit__](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/fileutils.py)
- 原版现状：已有文件 flush+fsync，rename 后没有父目录同步。
- 交付目标：增加 durable_directory 选项，在成功发布后同步目录项并说明能力限制。
- 影响模块：fileutils.py:AtomicSaver.__exit__
- 兼容边界：默认不增加平台要求；不把普通调用顺序测试声称为断电证明。
- 正常验收：开启时文件同步先于 rename、目录同步在后，保存结果可读。
- 异常／边界：不支持目录 fsync、发布前失败、发布后同步失败分开报告且不误称已回滚。
- 原生回归：tests/test_fileutils.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 15．按单调时间过期的 LRU（增强提案）

- 来源／场景：[boltons/cacheutils.py:LRU/LRI](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/cacheutils.py)
- 原版现状：缓存只有数量上限与命中计数，无过期语义。
- 交付目标：增加独立 TTLCache/LRU 扩展，可注入单调时钟，过期值不返回。
- 影响模块：cacheutils.py:缓存扩展与 cached 集成
- 兼容边界：原 LRU 不变，不后台建线程；0/负 TTL 的语义明确。
- 正常验收：时钟推进前命中、到期 miss 并可 on_miss 重新计算，LRU 顺序正确。
- 异常／边界：重复覆盖延长过期、懒清理、get/contains/pop 一致，真实时钟回拨不影响。
- 原生回归：tests/test_cacheutils.py；cacheutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 16．按值权重限制缓存容量（增强提案）

- 来源／场景：[boltons/cacheutils.py:LRI.max_size](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/cacheutils.py)
- 原版现状：max_size 限制项数，不适合缓存不同大小响应字节。
- 交付目标：增加 WeightedLRU，用显式 weigher 和 max_weight 限制总权重并逐出。
- 影响模块：cacheutils.py:新的缓存子类
- 兼容边界：不改 LRU max_size 原单位；权重快照随 set 更新，不跟踪外部对象隐式变大。
- 正常验收：大／小响应插入与读取影响淘汰，总权重不超预算。
- 异常／边界：单项超预算、负／非数值权重、更新同 key、pop/clear 后账目正确。
- 原生回归：tests/test_cacheutils.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 17．统计分位数可选离散取值方法（增强提案）

- 来源／场景：[boltons/statsutils.py:Stats._get_quantile/get_quantile](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/statsutils.py)
- 原版现状：只提供线性插值，没有 nearest/lower/higher 等可选择方法。
- 交付目标：get_quantile 增加 method，支持明确的离散观测值分位数。
- 影响模块：statsutils.py:Stats.get_quantile
- 兼容边界：默认 linear 和缓存性质保持；不声称实现所有统计软件分位数类型。
- 正常验收：[1,2,10,20] 在相同 q 下各方法得到约定的可解释结果。
- 异常／边界：q=0/1、单元素、空数据 default、无效 method/q 拒绝。
- 原生回归：tests/test_statsutils.py；statsutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 18．统计输入的非有限数策略（增强提案）

- 来源／场景：[boltons/statsutils.py:Stats.__init__](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/statsutils.py)
- 原版现状：没有统一 nan/inf 输入政策，依不同计算可能传播或产生不直观结果。
- 交付目标：增加 nonfinite=propagate/omit/error，集中决定 NaN 与无穷是否进入样本。
- 影响模块：statsutils.py:Stats 初始化与 describe
- 兼容边界：默认 propagate 保留现有结果，不把样本内容默默重写。
- 正常验收：omit 后均值／分位数／直方图基于相同有效样本，error 指出非有限值。
- 异常／边界：全无效样本走 default；Decimal/float、use_copy=False 与排序缓存限制明确。
- 原生回归：tests/test_statsutils.py；tests/test_statsutils_histogram.py
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 19．URL 日志输出的显式脱敏（增强提案）

- 来源／场景：[boltons/urlutils.py:URL.to_text/get_authority](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/urlutils.py)
- 原版现状：to_text 直接包含 userinfo 和查询参数；get_authority 可排除 userinfo 但不是完整 URL 的脱敏入口。
- 交付目标：新增 to_safe_text，隐藏密码和显式指定查询键的全部重复值，返回副本字符串。
- 影响模块：urlutils.py:URL；QueryParamDict
- 兼容边界：to_text 保留传输用途；默认脱敏不修改 URL 对象，明确 fragment 不会自动扫描未知敏感值。
- 正常验收：合成 user:password URL 与重复 token 查询参数输出均不含原值，普通路径保留。
- 异常／边界：百分号编码、空密码、Unicode、重复键、大小写匹配策略及原对象未变。
- 原生回归：tests/test_urlutils.py；urlutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 20．Table 输出 GitHub Markdown（增强提案）

- 来源／场景：[boltons/tableutils.py:Table.to_html/to_text](https://github.com/mahmoud/boltons/blob/4e5faa3d7e4008d89e0d8bf1ea87b6d9a061a16d/boltons/tableutils.py)
- 原版现状：真实 Table 只有 HTML 与文本渲染，无 Markdown 表格渲染。
- 交付目标：新增 to_markdown，保留 header、列对齐和缺失格填充，适配报告输出。
- 影响模块：tableutils.py:Table
- 兼容边界：原 HTML escaping 和文本宽度行为保持，不引入网络或第三方渲染服务。
- 正常验收：原生 from_data 得到的字典列表生成可解析的 header/separator/rows。
- 异常／边界：竖线、反斜杠、换行、None、空表、Unicode 与嵌套单元格用明确文本规则。
- 原生回归：tests/test_tableutils.py；tableutils doctest
- 真实依赖：无前置新增步骤；在同一固定工程累计交付。

## 累计验收与计数

每步包含实现、测试、文档和失败修复，重试与测试维度不另计步。保持同一真实源码目录与累计检查点，控制端冻结独立断言，检查导入候选路径并观察真实业务输出／文件副作用；回归原生基线与此前全部已接受能力。修改候选自带测试或自报成功不能放行。依赖先准备，执行离线；研究完成不等于验收就绪、模型完成或生产部署。
