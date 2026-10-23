# Humanize：二十步真实工程迭代路线

固定 [python-humanize/humanize@785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b](https://github.com/python-humanize/humanize/tree/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b)，见[单仓审查](./humanize.md)。6项原版复现修复与14项增强；仅研究，全部新契约未实施。

已有区域翻译、intcomma显式ndigits、naturaltime.when、平均月长近似、precisedelta绝对距离、byte桶截断、SI前缀以及各formatter的字符串输出均已阅读；不得将既有约定直接改称缺陷。每项是一项完整业务能力，代码/文档/测试/失败修复不拆步。

## 01．有限超大整数的精确识别

- **类型与来源**：复现修复提案；财务或计数报表显示超过浮点范围的合法整数。
- **原版观察**：ordinal/apnumber/fractional(10**400+123)均OverflowError，intcomma接受同一整数字符串却返回+Inf；共同原因是有限性检查或转换先经过float。
- **交付目标**：对明确接受整数的接口先识别有限整数，再采用整数算法或可说明的精确回退；此组同根转换缺陷只计一步。
- **真实模块**：src/humanize/number.py。
- **兼容边界**：保持NaN/Inf原输出、常规数值格式和非法字符串行为；不将本来仅接受float的所有接口无限扩域。
- **正常验收**：超大正整数和对应十进制字符串得到有限文本，ordinal后缀正确，分组没有丢位。
- **边界验收**：负大整数、0、bool、Decimal支持范围、非法文本、nonfinite和临界浮点转换明确处理。
- **原生回归**：tests/test_number.py。
- **实际依赖**：无；标准库整数和已有数值转换。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/419)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/number.py)。

## 02．非指数的浮点千位分组

- **类型与来源**：复现修复提案；报表的整数浮点值与微小小数需要可读十进制表示。
- **原版观察**：intcomma(1e16)为1e+16，intcomma(1e-5)为1e-05；显式ndigits=0才得到10,000,000,000,000,000。
- **交付目标**：无ndigits时以稳定的非指数十进制表示实施分组，明确小数精度策略，不对指数记号直接插分隔符。
- **真实模块**：src/humanize/number.py。
- **兼容边界**：显式ndigits的舍入、各locale分隔符和普通整数输出保持；与步骤01的超范围输入缺陷独立。
- **正常验收**：1e16显示分组十进制，1e-5显示0.00001，普通1.5不增加无意义尾零。
- **边界验收**：负数、负零、最小有限浮点、大指数、locale小数点、NaN/Inf和ndigits指定值回归。
- **原生回归**：tests/test_number.py、tests/test_i18n.py。
- **实际依赖**：无；标准库数值格式化。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/431)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/number.py)。

## 03．容量进位与自定义文案解耦

- **类型与来源**：复现修复提案；仪表板给容量值添加Size:前缀，同时使用GNU单位进位。
- **原版观察**：naturalsize(999999,gnu=True,format="Size: %.1f")抛ValueError，进位判断尝试float("Size: 976.6")。
- **交付目标**：先按数值精度判断进位，再将格式化文案与单位拼接；不能从含前后缀的完整显示文本反解析数值。
- **真实模块**：src/humanize/filesize.py。
- **兼容边界**：无文字的原format及GNU/binary/default进位约定保持；不承诺任意无效百分号格式可用。
- **正常验收**：带前后缀且临近进位阈值的显示成功，单位和无前缀模式数值一致。
- **边界验收**：负值、宽度/精度、字面百分号、999.95类进位、bytes分支、错误format的异常明确。
- **原生回归**：tests/test_filesize.py。
- **实际依赖**：无；沿用百分号格式化协议。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/366)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/filesize.py)。

## 04．容量数字遵循区域小数分隔符

- **类型与来源**：复现修复提案；法语容量报表需要数值和单位同时本地化。
- **原版观察**：激活fr_FR后intcomma(1.5)为1,5，naturalsize(1500000)却为1.5 Mo；decimal_separator已是逗号。
- **交付目标**：只对容量的数值部分应用当前区域小数分隔符，再组合已翻译单位；避免替换自定义前缀里的句点。
- **真实模块**：src/humanize/filesize.py、src/humanize/i18n.py。
- **兼容边界**：英文默认点号输出与格式精度不变；格式宽度和GNU紧凑单位保持；本地化不是全字符串replace。
- **正常验收**：fr_FR显示1,5 Mo，默认locale仍1.5 MB，带A.B前缀不误替换前缀。
- **边界验收**：整数容量、负数、无小数格式、GNU/binary、非默认catalog路径及频繁切换locale回归。
- **原生回归**：tests/test_filesize.py、tests/test_i18n.py、tests/test_benchmarks.py。
- **实际依赖**：无；使用现有i18n分隔符。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/460)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/filesize.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)。

## 05．最高SI数量级的有效数字进位

- **类型与来源**：复现修复提案；大科学计数在quetta边界仍需遵守precision。
- **原版观察**：precision=3时metric(9.996e30/31/32)分别是10.00 Q、100.0 Q、1000 Q；普通9999则是10.0 k。
- **交付目标**：在最高SI桶也按进位后的数量级重新核定有效数字；超出可表示前缀时采用明确科学记数回退。
- **真实模块**：src/humanize/number.py。
- **兼容边界**：默认precision及已正确的中间桶保持；输出数值相同而有效数字不能多一位。
- **正常验收**：三个样本分别满足3位有效数字，超quetta的1000 Q按文档规定科学记数回退。
- **边界验收**：负数、0、最小前缀、单位字符串、precision边界、阈值前后与nonfinite回归。
- **原生回归**：tests/test_number.py、tests/test_benchmarks.py。
- **实际依赖**：无；沿用已有SI和scientific逻辑。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/423)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/number.py)。

## 06．可选的不足一字节显示策略

- **类型与来源**：增强提案；平均流量或压缩统计可能包含非整数byte，需保留有意义的小数。
- **原版观察**：naturalsize(1.5)为1 Bytes，0.5为0 Bytes，1500为1.5 kB；原生测试明确断言小于基数时截断。
- **交付目标**：增加显式fractional-byte策略及精度，允许在byte桶保留小数，并定义单复数；默认截断保持。
- **真实模块**：src/humanize/filesize.py。
- **兼容边界**：按既有约定处理为增强；不偷偷改原生1.123456789到1 Bytes行为。
- **正常验收**：启用后1.5和0.5显示小数字节，未启用时原结果相同，整数1仍为单数Byte。
- **边界验收**：负小数、0、临近1000/1024、GNU、binary、format与locale组合明确。
- **原生回归**：tests/test_filesize.py、tests/test_i18n.py。
- **实际依赖**：无；现有数值格式化即可。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/459)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/filesize.py)。

## 07．精确时长的可选方向显示

- **类型与来源**：增强提案；本地工时差异报表要区分超时和节余。
- **原版观察**：precisedelta(+3661)与(-3661)都为1 hour, 1 minute and 1 second；源码使用绝对timedelta，是距离语义。
- **交付目标**：增加opt-in符号或方向模式，保留现有精确单位分解，再本地化正负方向的呈现。
- **真实模块**：src/humanize/time.py、src/humanize/i18n.py。
- **兼容边界**：默认绝对距离文本不变；不将既有_abs_timedelta约定当缺陷；方向和单位舍入必须分开。
- **正常验收**：启用后正负3661可区别，单位分解仍一致，未启用保持原字符串。
- **边界验收**：零、舍入为零的负值、suppress/minimum_unit、timedelta最大范围、翻译连接词和格式边界回归。
- **原生回归**：tests/test_time.py、tests/test_i18n.py。
- **实际依赖**：无；现有timedelta与翻译协议。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/379)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/time.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)。

## 08．翻译缓存区分目录来源

- **类型与来源**：复现修复提案；两个本地应用各自携带相同locale名但不同翻译目录。
- **原版观察**：临时catalog1的xx/one为uno，catalog2的xx/one为dos；依次activate同locale不同path，第二次仍得到uno，缓存仅以locale为键。
- **交付目标**：缓存键包含规范化catalog来源与locale，明确默认目录、重载和deactivate规则，使不同目录的翻译对象互不串用。
- **真实模块**：src/humanize/i18n.py。
- **兼容边界**：同一来源仍可缓存；不改变默认catalog搜索位置；不清空其他应用的缓存作为解决方法。
- **正常验收**：两目录依次activate后分别得到uno和dos，回到第一目录仍得到uno。
- **边界验收**：相对/绝对路径、PathLike、默认path、缺文件、同目录复用与路径重载策略明确。
- **原生回归**：tests/test_i18n.py。
- **实际依赖**：无；标准库路径身份与gettext；研究夹具使用本地msgfmt。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)。

## 09．嵌套且异步安全的区域作用域

- **类型与来源**：增强提案；同线程多个本地异步任务分别输出法语和默认英语报表。
- **原版观察**：只有threading.local持有当前翻译，无context API；事件同步的两个async任务交错后分隔符都是点号。
- **交付目标**：新增显式locale作用域或Formatter对象，使用任务上下文保存选定翻译并在退出后恢复，支持嵌套。
- **真实模块**：src/humanize/i18n.py、src/humanize/__init__.py。
- **兼容边界**：现有activate/deactivate兼容策略需明确；新作用域不全局修改其他任务，不把所有老线程用法强制迁移。
- **正常验收**：两个交错任务分别保持逗号和点号，嵌套退出恢复外层设置。
- **边界验收**：异常退出、取消、线程隔离、任务继承、未激活默认与重复进入规则回归。
- **原生回归**：tests/test_i18n.py。
- **实际依赖**：无；标准库contextvars/上下文管理；不依赖步骤08修复即可选定明确对象。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/__init__.py)。

## 10．调用者声明的翻译回退链

- **类型与来源**：增强提案；本地化工具支持缺少地区catalog时按指定顺序选择已有语言。
- **原版观察**：activate("fr_CA")在当前catalog中FileNotFoundError，签名仅locale和path，无显式回退链。
- **交付目标**：新增显式有序locale候选列表/回退策略，报告最终选择，支持调用者指定fr_CA、fr_FR、en。
- **真实模块**：src/humanize/i18n.py。
- **兼容边界**：原activate单locale失败语义保持；不猜测所有地区的语言替代规则。
- **正常验收**：指定链选择fr_FR并输出逗号，无匹配时按显式终止策略返回默认或抛错。
- **边界验收**：空链、重复locale、全缺失、英语默认、不同目录、损坏catalog与缓存回归。
- **原生回归**：tests/test_i18n.py。
- **实际依赖**：无；已有gettext加载；步骤08可改进缓存但不构成功能前置。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)。

## 11．区域或自定义数量级体系

- **类型与来源**：增强提案；日语和中文报表希望使用万、億等数量级，而非仅翻译百万。
- **原版观察**：ja_JP下intword(234909023)为234.9 百万；powers仍为全局10的3倍数阶梯，没有magnitude profile。
- **交付目标**：增加可选数量级profile，定义基数、单位和复数规则，允许区域profile与调用者自定义尺度。
- **真实模块**：src/humanize/number.py、src/humanize/i18n.py。
- **兼容边界**：英语默认million等体系保持；新增profile不能只替换单位字符串而沿用错误的缩放值。
- **正常验收**：选定万/億profile时数值按对应10的幂缩放，普通英语输出不变。
- **边界验收**：负数、舍入跨桶、稀疏profile、超大回退、未知profile、重复阈值及自定义单位冲突有规则。
- **原生回归**：tests/test_number.py、tests/test_i18n.py。
- **实际依赖**：无；新增本地数据表，语言单位需维护者复核；不要求CLDR外部服务。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/181)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/number.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)。

## 12．相对时间的方向语法上下文

- **类型与来源**：增强提案；德语等语言的过去/将来短语需要单位词形随语境变化。
- **原版观察**：原版德语单独一天为ein Tag，过去为vor ein Tag，未来为ein Tag ab jetzt；naturaltime将现有delta文本嵌入翻译模板。
- **交付目标**：让相对时间单位翻译接收past/future上下文，提供可审阅catalog词形；独立naturaldelta保留距离用法。
- **真实模块**：src/humanize/time.py、src/humanize/i18n.py、src/humanize/locale/de_DE/LC_MESSAGES/humanize.po。
- **兼容边界**：这是新增语法上下文协议；不声称研究者已完成全部语言审校，缺上下文的catalog回退原行为。
- **正常验收**：维护者确认的德语一天过去/将来样例使用相应词形，单独delta仍可用。
- **边界验收**：复数、小时/月、多个单位、just now、其他locale缺少上下文与自定义catalog回归。
- **原生回归**：tests/test_time.py、tests/test_i18n.py。
- **实际依赖**：无；gettext上下文及catalog更新，需要语言审核但不访问翻译服务。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/263)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/time.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)；[来源4](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/locale/de_DE/LC_MESSAGES/humanize.po)。

## 13．区域化列表连接规则

- **类型与来源**：增强提案；法语报表将多个商品名拼成自然语言列表。
- **原版观察**：激活fr_FR后natural_list([A,B,C])仍是A, B and C；签名只接收items，无conjunction或locale pattern。
- **交付目标**：增加可选区域列表pattern和连接词/serial-comma覆盖，统一处理两项与多项连接。
- **真实模块**：src/humanize/lists.py、src/humanize/i18n.py。
- **兼容边界**：默认英语文本保持；一项完整列表能力不拆成连接词、逗号和翻译三步。
- **正常验收**：法语pattern输出本地连接词，自定义连接词生效，默认英语与原生一致。
- **边界验收**：0/1/2/3项、一次性生成器、非字符串对象、空字符串、Unicode和翻译缺失回归。
- **原生回归**：tests/test_lists.py、tests/test_i18n.py。
- **实际依赖**：无；已有翻译和字符串协议。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/214)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/lists.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)。

## 14．显式ISO日期输入转换

- **类型与来源**：增强提案；本地数据文件的ISO日期需要进入日期人性化流程。
- **原版观察**：冻结2026-10-21时naturalday("2026-10-21")仍为原字符串，date对象则是today；无ISO转换helper。
- **交付目标**：增加显式ISO解析helper/输入模式，采用严格ISO规则，将成功结果交给现有date/time函数，不猜模糊地区日期。
- **真实模块**：src/humanize/time.py、src/humanize/__init__.py。
- **兼容边界**：原非日期输入的回传默认不变；新模式需要明确错误及日期/时间/时区支持范围。
- **正常验收**：ISO日期转换后显示today，带偏移的ISO datetime按明确参考时区显示。
- **边界验收**：Z、正负offset、仅日期、无效日期、空值、bytes、非字符串与夏令时边界有确定行为。
- **原生回归**：tests/test_time.py。
- **实际依赖**：无；标准库datetime解析；不新增通用自然语言解析依赖。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/129)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/time.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/__init__.py)。

## 15．可选的相对星期显示窗口

- **类型与来源**：增强提案；日历摘要希望较近的过去/将来使用星期名。
- **原版观察**：冻结2026-10-21时两天后的naturalday返回Oct 23；当前只特别处理昨天、今天和明天。
- **交付目标**：新增opt-in星期窗口和清楚的this/next/last周定义，使用区域星期名称，窗口外继续原日期格式。
- **真实模块**：src/humanize/time.py、src/humanize/i18n.py。
- **兼容边界**：默认±1天规则保持；周定义、周起始日和阈值显式，不混为固定天数模糊推断。
- **正常验收**：启用窗口后两天后的日期按选定星期策略输出，默认模式仍Oct 23。
- **边界验收**：跨周/年、周末、周起始日、正负阈值、date/datetime和参考时区一致。
- **原生回归**：tests/test_time.py、tests/test_i18n.py。
- **实际依赖**：无；标准库date与翻译；不强制依赖步骤16，可独立提供参考值。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/102)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/time.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)。

## 16．日期显示的显式参考时钟

- **类型与来源**：增强提案；历史报表或批量导出应围绕同一as-of日期重复生成。
- **原版观察**：naturalday(...,when=...)抛TypeError，naturaldate也没有when；naturaltime已支持when，不能再当新增。
- **交付目标**：给naturalday/naturaldate增加显式参考date/datetime或共享clock入口，避免为了批量结果改系统时钟。
- **真实模块**：src/humanize/time.py。
- **兼容边界**：不传参考值仍用原当前日期；已存在naturaltime.when保持；时区不一致要明确转换/拒绝策略。
- **正常验收**：同一输入和同一参考值在不同现实日期生成一致结果，两个日期函数共享该语义。
- **边界验收**：date与aware/naive datetime组合、跨午夜、夏令时、极端日期和None/错误类型回归。
- **原生回归**：tests/test_time.py。
- **实际依赖**：无；标准库datetime；测试可沿用既有freezegun但产品不依赖。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/time.py)。

## 17．按日历端点计算的年月间隔

- **类型与来源**：增强提案；订阅账期需按两个日期端点表达整月和余天，而非平均月长。
- **原版观察**：2024-01-31到2024-02-29相差29天，原naturaldelta按固定时长显示a month；没有接收start/end的日历间隔API。
- **交付目标**：新增独立calendar interval入口，明确月末截断周年规则，计算整年/月及剩余时长；区分原有平均月长的duration语义。
- **真实模块**：src/humanize/time.py、src/humanize/__init__.py。
- **兼容边界**：不改变现naturaldelta近似单位；业务需显式选择日历制与截断策略，不宣称所有文化共用同一日历。
- **正常验收**：所选截断规则下Jan31到Feb29为1日历月，Jan1到Jan30为0月29天，结果依赖真实端点。
- **边界验收**：反向区间、闰日周年、部分月、月底链、时间余量、aware时区与不支持的日历明确。
- **原生回归**：tests/test_time.py。
- **实际依赖**：无；标准库datetime可实现所限定公历规则，不引入完整历法依赖。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/time.py)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/__init__.py)。

## 18．明确输入量纲的百分比显示

- **类型与来源**：增强提案；本地统计将ratio与已经乘百的percent值一致显示。
- **原版观察**：没有naturalpercent入口；metric(0.125)为125 m，与百分比语义不同。
- **交付目标**：新增百分比formatter，调用者明确输入ratio或percent量纲，配置精度/舍入及区域数值和百分号间距。
- **真实模块**：src/humanize/number.py、src/humanize/i18n.py、src/humanize/__init__.py。
- **兼容边界**：不猜0.125代表0.125%还是12.5%；原metric/intword不变。
- **正常验收**：ratio=0.125显示12.5%，percent=12.5显示同值，区域小数分隔遵循选择。
- **边界验收**：0、负数、大于1比率、Decimal、极端值、NaN/Inf、边界约束和舍入半值定义明确。
- **原生回归**：tests/test_number.py、tests/test_i18n.py。
- **实际依赖**：无；标准库数值与现有区域能力；不需要绘图库或外部服务。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/277)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/number.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/i18n.py)；[来源4](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/__init__.py)。

## 19．本地命令行格式化入口

- **类型与来源**：增强提案；用户在本地脚本中直接格式化容量、数值和时长，无须另写Python包装。
- **原版观察**：python -m humanize naturalsize 1536返回1，缺少humanize.__main__；无可执行包入口。
- **交付目标**：新增本地CLI，分派既有formatter，提供明确数值/时间类型、locale/options及单值或stdin行模式。
- **真实模块**：src/humanize/__init__.py、src/humanize/filesize.py、src/humanize/number.py、src/humanize/time.py、pyproject.toml。
- **兼容边界**：新__main__为拟新增文件；库API输出保持；不启动服务器、不访问远程资源、不自动解释任意Python表达式。
- **正常验收**：容量命令的stdout与同参数naturalsize调用一致，时长/整数命令可用于本地管道。
- **边界验收**：缺参数、未知函数、无效值、退出码、Unicode stdin、空行、locale失败和中断有明确文案。
- **原生回归**：tests/test_filesize.py、tests/test_number.py、tests/test_time.py。
- **实际依赖**：无；标准库argparse；新CLI专测为未来新增，不冒充现有文件。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/issues/184)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/__init__.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/filesize.py)；[来源4](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/number.py)；[来源5](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/time.py)；[来源6](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/pyproject.toml)。

## 20．可选的结构化显示片段

- **类型与来源**：增强提案；本地UI需要对数值、单位和方向分别排版，同时保留可靠纯文本。
- **原版观察**：容量和时长入口均只返回str，无format_parts；调用方只能反解析已翻译的展示字符串。
- **交付目标**：新增opt-in结果/parts入口，提供有序number/unit/sign/separator片段、plain text及必要原数值信息，复用原舍入和区域逻辑。
- **真实模块**：src/humanize/filesize.py、src/humanize/number.py、src/humanize/time.py、src/humanize/lists.py、src/humanize/__init__.py。
- **兼容边界**：默认函数仍返回str；片段不逆向解析文本，不把显示的舍入值当原始业务值；新结果类型为拟议契约。
- **正常验收**：容量与多单位时长片段拼接逐字等于对应原文本，UI可单独选取单位和数值。
- **边界验收**：负数、nonfinite、多单位顺序、翻译重排、空列表、Unicode、舍入进位和结构版本兼容回归。
- **原生回归**：tests/test_filesize.py、tests/test_number.py、tests/test_time.py、tests/test_lists.py。
- **实际依赖**：无；标准库记录结构；各formatter可独立实现，不要求前19步先完成。 功能步骤依赖：无。
- **依据**：[来源1](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/filesize.py)；[来源2](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/number.py)；[来源3](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/time.py)；[来源4](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/lists.py)；[来源5](https://github.com/python-humanize/humanize/blob/785e5dcc0d0308ad0dff3f6cc0faa7085ad0375b/src/humanize/__init__.py)。

## 独立验收与累计回归

未来控制端以真实formatter调用验证数值/单位/纯文本、异常类型、原输入和区域作用域。时间使用固定参考值，catalog缓存用临时本地GNU目录，异步用事件确定交错；不依赖墙钟等待、远程翻译或外部账户。每步累计回归相关原生集合。856项原版通过不代表本路线新增契约通过，冻结验收与产品接入尚未开始。
