# pendulum实际场景任务表

固定来源：https://github.com/python-pendulum/pendulum@e06dacedc4cdea90fa1286b3965d180ab94cf251。

先冻结逐仓已核事实、用户目标和独立验收，再制作内容。各任务不消费未声明的前序答案或代码；披露和材料不足路径不重复计数。

## PN-U01：解释月份裁剪与连续加法

类型：understand；合法结果：explained。

用户问题与当前控制：Start datetime(2025,1,31,tz="UTC"). Compare add(months=1),then another month,with add(months=2) from the original. Explain the retained anchor and immutability. No edits.

独立验收：The first addition clips to February28;another month reaches March28. A single two-month addition from January31 reaches March31,and the original stays January31. Calendar month addition with clipping is not associative. Preserve the intended original day/short-month policy when calculating scheduled dates;do not infer repeated calls retain a hidden31st-day anchor.

公开材料：materials/pn-u01.md

授权：只读，不产生接受代码检查点。

实际业务控制：month_clipping_makes_repeated_addition_differ_from_a_single_combined_addition。

## PN-U02：区分日历月和近似秒数

类型：understand；合法结果：explained。

用户问题与当前控制：Create duration(months=1),inspect total_seconds(),and compare adding its months versus adding its total_seconds() to UTC January31,2025. Explain the resulting dates and elapsed duration. No edits.

独立验收：The duration scalar reports30 days of seconds. Applying one calendar month reaches February28,an actual28-day interval;adding the30-day seconds reaches March2. A calendar month is context dependent,so do not serialize it as that scalar and expect identical calendar arithmetic. Preserve typed units and the required arithmetic contract.

公开材料：materials/pn-u02.md

授权：只读，不产生接受代码检查点。

实际业务控制：calendar_months_and_approximate_duration_seconds_are_not_interchangeable。

## PN-C01：选择时区转换或墙钟重新解释

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：From UTC2026-01-01 12:00,compare in_timezone("America/New_York") with set(tz="America/New_York"). Inspect wall hour and integer timestamp. Advise an event-import interpretation contract. No implementation.

独立验收：in_timezone yields07:00-05:00 at the same instant. set retains12:00 wall fields with the new zone,shifting the instant by+5 hours. Choose conversion for an already known instant and a separately validated interpretation policy for local wall input;do not use set as an instant-preserving conversion.

公开材料：materials/pn-c01.md

授权：只读，不产生接受代码检查点。

实际业务控制：timezone_conversion_preserves_the_instant_while_set_reinterprets_wall_fields。

## PN-C02：明确夏令时重叠和不存在时间策略

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Compare Europe/Paris2026-10-25 02:30 with fold0 and fold1 by timestamps. Construct Europe/Paris2026-03-29 02:30 with raise_on_unknown_times=True. Advise scheduling input and retained evidence. No edits.

独立验收：The two02:30 folds are distinct instants one hour apart. The spring02:30 does not exist and explicit raising produces NonExistingTime. Require a named-zone/ambiguity/gap policy,retain original local fields and resolved offset/instant,and request a choice when needed. Do not silently assume one fold or claim wall fields alone identify an instant.

公开材料：materials/pn-c02.md

授权：只读，不产生接受代码检查点。

实际业务控制：ambiguous_folds_are_distinct_instants_and_nonexistent_times_can_be_rejected。

## PN-P01：规划带日期类型的事件数据接入

类型：plan；合法结果：planned_without_library_change。

用户问题与当前控制：Compare parse("2026-10-22") with exact=True and parse("12:30:00",exact=True). Inspect returned types and default timezone/time imputation. Plan separate date,local-time and instant fields plus validation/publication errors. No implementation.

独立验收：Ordinary date parsing yields a midnight UTC DateTime;exact=True preserves Date,and the exact time string yields Time. Define expected field types before parsing,require explicit timezone/offset where an instant is needed,and reject or explicitly resolve missing components instead of inventing midnight/UTC semantics. Preserve raw text and normalized typed values and test invalid/ambiguous input. Successful parsing alone does not establish a complete event instant.

公开材料：materials/pn-p01.md

授权：只读，不产生接受代码检查点。

实际业务控制：exact_parsing_preserves_date_and_time_types_instead_of_inventing_an_instant。

## PN-D01：诊断解析时区参数未转换结果

类型：diagnose；合法结果：diagnosed_or_information_requested。

用户问题与当前控制：A parse(...,tz=...) call appears to ignore the requested output zone. Request the full input string,explicit offset,options,returned timezone/timestamp and an in_timezone control before diagnosing. No edits.

独立验收：Use consumed offset/parser evidence to distinguish a default interpretation zone from output conversion. Missing controls support insufficient_information;do not erase an explicit offset or claim a timestamp changed without proof.

公开材料：取得合理追问后才披露；材料不足允许合法收口

授权：只读，不产生接受代码检查点。

实际业务控制：核材料消费与语义结论。

完整原生、工程正反例、mock、页面／API／数据库及Git／Docker分别核验；未准入前不正式注册。模型调用0，不push或部署。
