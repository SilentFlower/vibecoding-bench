# Babel：二十步真实工程迭代路线

固定 [python-babel/babel@e2a17919f0eb988bfea2883b00793ca4d5d37c4f](https://github.com/python-babel/babel/tree/e2a17919f0eb988bfea2883b00793ca4d5d37c4f)，原生证据见 [单仓审查](./babel.md)。以下均为逐仓分析提出的本地工程增强提案，尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．本地化日期时间联合解析

- **来源／场景**：本地桌面导入一个同时含日期和时间的区域化字段；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/dates.py)。
- **原版缺口**：dates 提供 parse_date、parse_time，无 parse_datetime；调用方需自行拆分且分隔符因区域变化
- **交付及模块**：新增显式 locale、pattern 的联合解析，复用各日期时间字段并返回 datetime；`babel/dates.py:parse_date`, `babel/dates.py:parse_time`。
- **兼容与实际依赖**：不改变独立解析函数；无时区的输入保持 naive，不猜测系统时区；步骤依赖：无。
- **正常验收**：同一 datetime 经明确数字 pattern 格式化后可往返，日期与时间分隔文字按模式解析
- **异常／边界验收**：非法日期、尾随内容、缺少字段及有歧义输入明确失败；不自动把未知文字吞掉
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 02．月份名称日期解析

- **来源／场景**：导入 April 1, 2004 或德文月份日期；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/dates.py)。
- **原版缺口**：parse_date 的 FIXME 明确只支持数字；实际 MMMM 输入失败，属于现有能力外增强
- **交付及模块**：在显式文本月份模式下用 locale 的 format/stand-alone 月份数据解析，保持数字快速路径；`babel/dates.py:parse_date`, `babel/core.py:Locale`。
- **兼容与实际依赖**：默认数字输入和现有两位年份策略不变；不默认跨语言猜月份；步骤依赖：无。
- **正常验收**：英文全名、德文缩写和独立月份按各自明确模式返回正确 date
- **异常／边界验收**：同名窄月份的歧义、非法月份和额外数字拒绝；可选英语回退必须显式启用
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 03．时间小数与数字偏移解析

- **来源／场景**：本地记录导入 15:30:12.123+02:00；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/dates.py)。
- **原版缺口**：parse_time 仅使用前三个数字，TODO 标注时区未支持；实测丢弃小数和偏移，不把未承诺能力记为缺陷
- **交付及模块**：新增可选严格解析模式支持 S 小数及 X/x/Z 数字时区，返回带 microsecond 和固定偏移的 time；`babel/dates.py:parse_time`。
- **兼容与实际依赖**：旧默认启发式入口保留；不猜测时区缩写和夏令时地名；步骤依赖：无。
- **正常验收**：显式 HH:mm:ss.SSSXXX 往返保留 123000 微秒与 +02:00
- **异常／边界验收**：9 位小数的精度策略、越界偏移、12AM/12PM 和不完整偏移有明确结果
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 04．日期时间格式化字段分段

- **来源／场景**：本地报表要给日期与时区字段分别加样式；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/dates.py)。
- **原版缺口**：format_datetime 返回字符串，内部 DateTimePattern/DateTimeFormat 能格式化字段但无 parts API
- **交付及模块**：提供带字段类型、原值、输出文本和顺序的 format_datetime_to_parts；`babel/dates.py:DateTimePattern`, `babel/dates.py:DateTimeFormat`。
- **兼容与实际依赖**：拼接 parts 必须逐字等于原格式化结果；不把 HTML 标记塞进格式字符串；步骤依赖：无。
- **正常验收**：中英日期、字面量与时区分段拼接等于原输出，可单独样式化月份
- **异常／边界验收**：引号转义、重复字段、非 ASCII 字面量、空文字段与未知 pattern 符号按原策略处理
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 05．数字格式化字段分段

- **来源／场景**：账单希望独立展示符号、整数、分组、小数和货币标签；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/numbers.py)。
- **原版缺口**：NumberPattern.apply 返回整串，没有 format_decimal_to_parts；调用方拆分易错分组和负号
- **交付及模块**：提供 NumberPattern 的结构化 parts 输出，涵盖 decimal/currency/percent/scientific 的共同数字段；`babel/numbers.py:NumberPattern`。
- **兼容与实际依赖**：原字符串 API 不变；parts 拼接与对应原 API 完全一致，不另设四个计数步骤；步骤依赖：无。
- **正常验收**：德文小数、印度分组与负数生成正确整数、小数、分隔 parts
- **异常／边界验收**：NaN、无穷、会计括号、非断行空格和科学计数指数分别有一致分段
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 06．区域化数字区间

- **来源／场景**：本地统计图的最小最大值需一个区域化范围；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/numbers.py)。
- **原版缺口**：numbers 只有单值格式化，日期才有 format_interval；无 format_decimal_range
- **交付及模块**：新增 Decimal 数字范围格式化，约定范围连接、相同值收敛和顺序策略；`babel/numbers.py:format_decimal`, `babel/core.py:Locale`。
- **兼容与实际依赖**：单值格式化不变；只消费固定 CLDR 数据，不增加网络依赖；初版不宣称实现未导入的 CLDR range 复数规则；步骤依赖：无。
- **正常验收**：1.2 到 3.4 按 en/de 输出区域小数，两个端点均保留所需精度
- **异常／边界验收**：相等、倒序、负区间、舍入后相等、无穷边界策略显式，禁止悄悄交换端点
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 07．同币种金额区间

- **来源／场景**：离线价格范围需要统一保留货币显示及会计负数；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/numbers.py)。
- **原版缺口**：format_currency 仅单值，无 format_currency_range；调用方拼接会重复或遗漏币种
- **交付及模块**：新增同币种范围，支持明确符号合并策略及不得合并时回退完整双端点；`babel/numbers.py:format_currency`。
- **兼容与实际依赖**：只格式化不做汇率转换；默认遵守每币种小数位，原 currency_digits 参数语义保持；步骤依赖：无。
- **正常验收**：EUR 的德文范围和 USD 的英文范围端点、间隔与币种位置正确
- **异常／边界验收**：跨零会计格式、零小数币种、符号歧义及混币输入按定义拒绝或明确全显示
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 08．带币种文本解析

- **来源／场景**：导入本地账单 1.234,50 EUR；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/numbers.py)。
- **原版缺口**：parse_decimal 只接数字，公开无 parse_currency；调用方可先剥离币种再解析
- **交付及模块**：新增显式允许币种集合的货币文本解析，返回 Decimal 与 ISO 币种；`babel/numbers.py:parse_decimal`, `babel/numbers.py:get_currency_symbol`。
- **兼容与实际依赖**：不调用汇率或金融服务；美元符号歧义不可用系统区域默默决定；步骤依赖：无。
- **正常验收**：明确 de_DE+EUR 时解析前后置币种与非断行空格并保持 Decimal 精度
- **异常／边界验收**：多币种符号、未知代码、会计括号、缺币种和错误分组有精确错误；不得把 USD 与 CAD 混同
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 09．紧凑数值文本反向解析

- **来源／场景**：读取本地生成的 1.2K 或 1,2万 报表字段；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/numbers.py)。
- **原版缺口**：format_compact_decimal 有单向格式化，公开无 parse_compact_decimal
- **交付及模块**：新增 locale、format_type 和歧义策略明确的紧凑数解析，返回数值与是否舍入的信息；`babel/numbers.py:format_compact_decimal`, `babel/numbers.py:_get_compact_format`。
- **兼容与实际依赖**：不声称恢复格式化时丢失的低位数；返回表示值及原始精度范围；步骤依赖：无。
- **正常验收**：已知 compact pattern 的短/长文本可得到其表示数值及倍率
- **异常／边界验收**：倍率缩写歧义、负数、无倍率、多个倍率与未知区域模式拒绝；不能伪称精确逆运算
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 10．可选本地数字字形

- **来源／场景**：阿拉伯数字报表要求数字字符本身区域化；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/numbers.py)。
- **原版缺口**：format_decimal(numbering_system=default) 仅换符号；实测 ar_EG 输出仍含 ASCII 1234
- **交付及模块**：在独立显式 digit-shaping 选项中使用固定数字映射，保持符号和舍入逻辑；`babel/numbers.py:format_decimal`, `babel/numbers.py:NumberPattern`。
- **兼容与实际依赖**：现有 numbering_system 行为保持；不默认切换已有输出，不自动翻译字符串中的任意数字；步骤依赖：无。
- **正常验收**：ar_EG 的 1234.5 输出预期数字字形与本地分隔符，latn 不变
- **异常／边界验收**：未知算法数字系统明确不支持；负号、指数、NaN 与非数值货币标签不错误转写
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 11．度量单位区间

- **来源／场景**：设备说明用一个单位描述 3 至 5 米；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/units.py)。
- **原版缺口**：format_unit/format_compound_unit 都是单值，无 format_unit_range
- **交付及模块**：新增同单位范围格式化，端点数字处理和单位复数选择有明确首版规则；`babel/units.py:format_unit`。
- **兼容与实际依赖**：不承担量纲换算或自动缩放；明确复数规则来源，不把 compound numerator/denominator 当范围；步骤依赖：无。
- **正常验收**：en_US 的 meter 范围与中文长度范围正确，数字精度独立可控
- **异常／边界验收**：0/1/多值复数、相等端点、未知单位、倒序与不支持 range plural 的回退有断言
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 12．多分量持续时间格式化

- **来源／场景**：本地任务报告需 2 小时 15 分钟而非近似的 2 小时；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/dates.py)。
- **原版缺口**：format_timedelta 选择一个 granularity；无 format_duration 组合多个精确分量
- **交付及模块**：新增从 timedelta 或明确整数分量格式化持续时间的 API，可选允许的字段及最大字段数；`babel/dates.py:format_timedelta`, `babel/units.py:format_unit`, `babel/lists.py:format_list`。
- **兼容与实际依赖**：不把月/年当固定秒数换算；旧近似 format_timedelta 保持；步骤依赖：无。
- **正常验收**：2小时15分钟按 en/zh 组合，零字段策略与最大字段数符合选项
- **异常／边界验收**：负持续时间符号、跨天、微秒进位和截断/舍入各有定义，不因默认浮点丢精度
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 13．本地化列表元素分段

- **来源／场景**：报告要给每个列表元素加链接并保留正确连接词；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/lists.py)。
- **原版缺口**：format_list 返回整串，已有 style fallback 但无 element/literal parts
- **交付及模块**：新增 format_list_to_parts，保留输入索引、元素和连接文字；`babel/lists.py:format_list`。
- **兼容与实际依赖**：拼接必须等于现有格式化结果；列表连接不依赖 HTML 或字符串替换占位符；步骤依赖：无。
- **正常验收**：中英 3 元素列表分段后可恢复精确输出，重复元素仍保留原索引
- **异常／边界验收**：0/1/2 元素、元素内有花括号和连接词、回退 style 及空元素正确区分
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 14．可解释区域回退链

- **来源／场景**：离线翻译包加载需要知道 zh_Hant_HK 到哪些父区域；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/core.py)。
- **原版缺口**：Locale.parse 处理 likely-subtags，localedata.load 内有父区域继承，但无公开回退链结果
- **交付及模块**：公开基于现有 parent_exceptions 的 locale_fallback_chain，说明每一步来源；`babel/core.py:Locale`, `babel/localedata.py:load`。
- **兼容与实际依赖**：不把简单截断语言标签冒充 CLDR 父规则；不改变现有 load 缓存；步骤依赖：无。
- **正常验收**：含 script/territory 的区域返回有序去重链并最终到 root
- **异常／边界验收**：特殊父区域、未知 locale、别名、重复父项和显式不推断模式均不形成环
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 15．带权语言首选项协商

- **来源／场景**：把本地浏览器导出的语言偏好串用于离线报表选择；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/core.py)。
- **原版缺口**：negotiate_locale 只接受已排好序的 locale iterable，不解析 q 参数；直接传带 q 字串无匹配
- **交付及模块**：新增纯文本 Accept-Language 解析与协商助手，支持权重、稳定排序和 q=0 排除；`babel/core.py:negotiate_locale`。
- **兼容与实际依赖**：不添加 HTTP 请求或网络服务；旧协商接口保持，通配回退必须显式配置；步骤依赖：无。
- **正常验收**：fr-CA;q=0.8,en;q=0.9 在可用 en/fr 中选择 en
- **异常／边界验收**：无效权重、同权顺序、重复语言、q=0、通配和空输入有确定结果
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 16．日期骨架匹配解释

- **来源／场景**：维护区域日期模板时需要知道为何 yMMd 选了 yMd；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/dates.py)。
- **原版缺口**：match_skeleton 返回最佳名字或 None，分数和字段替换留在局部变量
- **交付及模块**：新增 explain_skeleton_match 返回候选距离、字段差异、替换及最终选择；`babel/dates.py:match_skeleton`。
- **兼容与实际依赖**：默认 match_skeleton 的稳定排序和结果不变；解释计算复用同一算法；步骤依赖：无。
- **正常验收**：yMMd 的候选距离和最终选择与原函数一致，z→v 替换可追踪
- **异常／边界验收**：不同字段不允许时给出排除原因；空选项、并列距离和未知字段不伪造匹配
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 17．目录更新预览

- **来源／场景**：翻译维护者在覆盖 PO 前希望查看新增、模糊匹配和废弃项；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/messages/catalog.py)。
- **原版缺口**：Catalog.update 原位改动并返回 None；虽可手动 clone 目录，但没有 preview_update
- **交付及模块**：新增无副作用预览结果，包含匹配映射、策略影响和可重用的更新计划；`babel/messages/catalog.py:Catalog.update`。
- **兼容与实际依赖**：既有 update 行为保持；预览不改变 catalog 消息、头和 obsolete，执行前可检查输入摘要；步骤依赖：无。
- **正常验收**：模板重命名时报告 fuzzy、保留翻译及废弃项目，按计划执行等于直接 update
- **异常／边界验收**：context 相同 msgid、复数变化、多个候选并列及输入被改动时拒绝应用过期计划
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 18．翻译抽取精确来源跨度

- **来源／场景**：本地编辑器需直接定位同一行多个翻译调用；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/messages/extract.py)。
- **原版缺口**：extract_from_file 返回 lineno/message/comments/context，未提供列和结束位置
- **交付及模块**：新增结构化抽取入口，Python 优先保留调用及字符串跨度；旧 extractor 以未知跨度适配；`babel/messages/extract.py:extract_python`, `babel/messages/extract.py:extract_from_file`。
- **兼容与实际依赖**：原 tuple 入口与插件签名不变；不把无法取得的位置猜成零；步骤依赖：无。
- **正常验收**：一行两个 _ 调用得到各自列跨度，多行文字位置准确
- **异常／边界验收**：编码声明、Unicode 列计量、隐式字符串拼接与第三方 extractor 无跨度明确标识
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 19．可逆目录 JSON 交换

- **来源／场景**：本地翻译审查工具希望无 PO 语法解析也能交换消息；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/messages/catalog.py)。
- **原版缺口**：Catalog 原生 IO 是 PO/MO，公开无 to_json/from_json；__dict__ 不是稳定协议
- **交付及模块**：一次交付带 schema 版本的 JSON 目录读写，保留 context、复数、comments、flags、locations 和 obsolete；`babel/messages/catalog.py:Catalog`, `babel/messages/pofile.py:write_po`。
- **兼容与实际依赖**：不替代 PO/MO 默认格式；不导出内部缓存；日期时区与 tuple 字段有明确编码；步骤依赖：无。
- **正常验收**：含上下文、复数和废弃项的目录往返后语义等价，仍可 write_po/write_mo
- **异常／边界验收**：重复主键、未知 schema、非法复数长度、空头部和 Unicode 不静默丢失
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。

## 20．目录间语义差异

- **来源／场景**：翻译评审需要比较两个 PO 而不被换行与排序变化淹没；[固定源码](https://github.com/python-babel/babel/blob/e2a17919f0eb988bfea2883b00793ca4d5d37c4f/babel/messages/catalog.py)。
- **原版缺口**：Catalog.check 只做单目录翻译检查，update 是合并；无只读 diff
- **交付及模块**：新增按 msgid+context 的语义 diff，区分文本、复数、flags、comments、locations 和头元数据；`babel/messages/catalog.py:Catalog.check`, `babel/messages/pofile.py:read_po`。
- **兼容与实际依赖**：不自动修改翻译或把 fuzzy 当已译；每类差异可单独忽略，源位置变化不冒充翻译变化；步骤依赖：无。
- **正常验收**：同内容不同 PO 换行无翻译差异，真实翻译及复数变更可逐字段定位
- **异常／边界验收**：context 不同不混项，新增/删除/obsolete 转移、空译文与排序稳定均有断言
- **原生回归**：`tests/test_dates.py`, `tests/test_numbers.py`, `tests/test_units.py`, `tests/test_lists.py`, `tests/test_core.py`, `tests/messages/test_catalog.py`, `tests/messages/test_extract.py`, `tests/messages/test_pofile.py`, `tests/messages/test_mofile.py`。
