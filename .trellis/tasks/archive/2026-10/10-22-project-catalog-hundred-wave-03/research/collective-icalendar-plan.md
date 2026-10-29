# collective-icalendar实际场景任务表

固定来源：https://github.com/collective/icalendar@3ecf079acba0e592ea6a40c456514984c8657852。

先冻结逐仓已核事实、用户目标和独立验收，再制作内容。各任务不消费未声明的前序答案或代码；披露和材料不足路径不重复计数。

## IC-U01：解释全天事件的日期和结束边界

类型：understand；合法结果：explained。

用户问题与当前控制：Create Event with DTSTART=date(2026,10,22). Inspect inferred end,then add DTEND=date(2026,10,23),serialize/reparse and inspect native date type and duration. Explain inclusive start/non-inclusive end from the supplied Event contract. No edits.

独立验收：DATE serializes with VALUE=DATE and reparses as date. The default end for this start-only date event is the next date;an explicit October23 DTEND describes one day October22 because end is exclusive. Preserve date type and matching DATE end semantics;do not turn it into a midnight UTC instant or count the end date as another occupied day.

公开材料：materials/ic-u01.md

授权：只读，不产生接受代码检查点。

实际业务控制：all_day_date_events_use_an_exclusive_next_date_end。

## IC-U02：解释日历TEXT的转义与往返

类型：understand；合法结果：explained。

用户问题与当前控制：Set SUMMARY to the exact literal "计划,项目;路径\test" followed by a newline and "说明". Serialize Event to bytes and reparse. Explain Unicode,comma,semicolon,backslash,newline and CRLF handling. No edits.

独立验收：TEXT serialization escapes comma,semicolon,backslash and newline using the calendar grammar,uses UTF-8 bytes and CRLF content lines,and the parsed summary restores the original Unicode text. Use the property encoder rather than hand-concatenating raw content lines. This preserves this property control,not arbitrary original file formatting or byte-for-byte roundtrip.

公开材料：materials/ic-u02.md

授权：只读，不产生接受代码检查点。

实际业务控制：calendar_text_escaping_roundtrips_the_actual_unicode_and_delimiters。

## IC-C01：保留多个参与者及各自参数

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Add a vCalAddress mailto:a@example.invalid with ROLE=REQ-PARTICIPANT as attendee,then add mailto:b@example.invalid using ATTENDEE. Compare property shape before/after,case-insensitive lookup and serialized/reparsed per-value parameters. Advise an import representation. No implementation.

独立验收：One attendee is scalar;adding another appends into a list rather than replacing it. Lookup is case insensitive and the first value retains its own ROLE parameter. Normalize scalar/list handling at the caller boundary while preserving each participant and parameters;do not overwrite the first attendee or flatten parameterized properties into one string.

公开材料：materials/ic-c01.md

授权：只读，不产生接受代码检查点。

实际业务控制：repeated_properties_preserve_multiple_values_and_per_value_parameters。

## IC-C02：区分浮动时间、命名时区和UTC

类型：consult；合法结果：advice_no_code_change。

用户问题与当前控制：Serialize/reparse DTSTART for2026-10-22 09:00 as naive datetime,Europe/Berlin aware datetime and UTC aware datetime. Compare content-line forms and decoded offsets. Advise cross-user scheduling input. No edits.

独立验收：Naive input produces a floating DTSTART without Z/TZID and decodes without tzinfo. Berlin uses TZID=Europe/Berlin and this date resolves to+02:00;UTC uses trailing Z and zero offset. These09:00 wall values do not all identify the same instant. Choose the intended representation,retain zone definitions/context and ambiguity policy,and do not infer a viewer or server timezone for floating values.

公开材料：materials/ic-c02.md

授权：只读，不产生接受代码检查点。

实际业务控制：floating_named_zone_and_utc_datetime_representations_have_distinct_meanings。

## IC-P01：规划重复日程的展开与身份

类型：plan；合法结果：planned_without_library_change。

用户问题与当前控制：A synthetic Calendar holds one VEVENT with UID=recurrence-local-001,UTC DTSTART2026-01-01 09:00,RRULE FREQ=DAILY;COUNT=3 and fixed DTSTAMP. Compare walk("VEVENT") count with the rule count. Plan occurrence display/import,windowing,exception identity and validation. No implementation or real calendar access.

独立验收：walk returns the one stored VEVENT component,not three expanded occurrences;RRULE COUNT remains[3]. Select and validate an explicit recurrence-expansion strategy with bounded time windows/counts,timezone/DST rules,RDATE/EXDATE,RECURRENCE-ID overrides and stable UID plus recurrence identity. Keep source components and exceptions separately;do not duplicate the master component three times or claim walk already expands it.

公开材料：materials/ic-p01.md

授权：只读，不产生接受代码检查点。

实际业务控制：walking_a_recurring_event_returns_the_stored_component_not_expanded_occurrences。

## IC-D01：诊断设置时长后DTEND为何消失

类型：diagnose；合法结果：diagnosed_or_information_requested。

用户问题与当前控制：A calendar export loses an explicit DTEND after editing duration. Request complete property mutation order,typed start/end/duration and serialized before/after controls. No edits.

独立验收：Use consumed property-setter evidence to distinguish a representation change from loss of the computed end. Missing controls support insufficient_information. Do not restore mutually competing end representations or patch serialization without an explicit new contract.

公开材料：取得合理追问后才披露；材料不足允许合法收口

授权：只读，不产生接受代码检查点。

实际业务控制：核材料消费与语义结论。

完整原生、工程正反例、mock、页面／API／数据库及Git／Docker分别核验；未准入前不正式注册。模型调用0，不push或部署。
