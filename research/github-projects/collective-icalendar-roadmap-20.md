# icalendar（Python）：二十步真实工程迭代路线

固定 [collective/icalendar@3ecf079acba0e592ea6a40c456514984c8657852](https://github.com/collective/icalendar/tree/3ecf079acba0e592ea6a40c456514984c8657852)，原生证据见 [单仓审查](./collective-icalendar.md)。以下为逐仓分析提出的本地工程改进路线，缺陷复现与增强提案分别记录；尚未实施，不代表上游承诺。每项交付包含实现、原生回归和说明，不把测试或重试独立计数。

## 01．CLI全天事件的缺省时长一致

- **来源／场景**：资料整理日只有DATE DTSTART，没有DTEND或DURATION；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cli.py)。
- **原版缺口**：Event.end/duration实测为次日及1天，cli.view却直接令end=start，显示同日和0:00:00
- **交付及模块**：CLI复用原生Event.start/end/duration语义，正确显示全天事件的排他结束日；`src/icalendar/cli.py:view`, `src/icalendar/cal/event.py`。
- **兼容与实际依赖**：已有显式DTEND/DURATION显示保持；不把所有无结束的timed事件强加1天；步骤依赖：无。
- **正常验收**：2026-10-22全天事件显示排他结束2026-10-23及1天，普通一小时会议保持
- **异常／边界验收**：DATE与DATE-TIME、显式多日时长、浮动时间及非法组合统一使用已有对象校验
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 02．组件结束名与栈顶匹配

- **来源／场景**：本地导出的ICS不小心把VEVENT结束写成VTODO；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/parser/ical/component.py)。
- **原版缺口**：handle_end_component不比较vals与栈顶name；实测错配仍返回VEVENT且errors为空
- **交付及模块**：在弹栈前核对BEGIN/END组件名，给出错配组件与预期名称的解析错误；`src/icalendar/parser/ical/component.py:handle_end_component`。
- **兼容与实际依赖**：组件名大小写不敏感保持；宽容恢复若保留需显式可选并记录errors，默认不静默当成合法配对；步骤依赖：无。
- **正常验收**：合法嵌套Calendar/Event/Alarm正常，END:VTODO错配VEVENT能定位失败
- **异常／边界验收**：孤立END、缺END、未知X组件、跨层错配及LazyCalendar延迟解析沿同一规则处理
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 03．聚合的日历语义诊断

- **来源／场景**：资料导入想一次看到多组件的必需字段及互斥属性问题；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/calendar.py)。
- **原版缺口**：各组件已有required/singletons/exclusive声明和日期getter校验；Calendar.validate仅检查PRODID/VERSION/非空子组件且首错抛出
- **交付及模块**：新增validate_report，遍历组件生成带规则代码/组件路径的诊断，覆盖已声明约束和时间一致性；`src/icalendar/cal/calendar.py:validate`, `src/icalendar/cal/component.py`, `src/icalendar/cal/event.py`。
- **兼容与实际依赖**：不宣称原版无校验；默认原宽容解析保持，新增诊断不自动修改日历或承诺全RFC证明；步骤依赖：无。
- **正常验收**：缺UID、重复单值与DTEND/DURATION互斥能同时列出，合规日历通过
- **异常／边界验收**：扩展属性、未知组件、floating/date类型混用、周期UNTIL类型和部分坏值都保留可解释级别
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 04．有界复发查询的生态适配

- **来源／场景**：日历业务要查询某一周实际发生的日程；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/calendar.py)。
- **原版缺口**：原包保存RRULE/RDATE/EXDATE及RECURRENCE-ID，不直接提供窗口展开；README已推荐recurring-ical-events与iCalEvents
- **交付及模块**：增加可选recurring-ical-events适配层，提供明确窗口、时区和实例来源合同；`src/icalendar/cal/calendar.py`, `src/icalendar/prop/recur/recur.py`, `README.rst`。
- **兼容与实际依赖**：明确这是生态集成增强，非首次发明复发支持；不默认安装额外包，不自行声称已验证其所有行为；步骤依赖：无。
- **正常验收**：日周期加EXDATE/RDATE和覆盖实例在有限窗口返回正确顺序及原UID/RECURRENCE-ID
- **异常／边界验收**：无界规则必须给窗口，跨夏令时、取消实例、date与datetime及重复规则按适配合同处理
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 05．从日程计算忙闲区间

- **来源／场景**：本地排程要把一周事件合成VFREEBUSY；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/free_busy.py)。
- **原版缺口**：FreeBusy组件能表示区间，Calendar.freebusy能查询既有组件，但没有从事件集合计算忙闲的合同
- **交付及模块**：新增compute_freebusy，按时间窗口归一化并合并事件区间，输出有来源的忙闲结果/FreeBusy；`src/icalendar/cal/free_busy.py`, `src/icalendar/cal/calendar.py`, `src/icalendar/cal/event.py`。
- **兼容与实际依赖**：复用复发适配；尊重TRANSP和STATUS，不把已有FreeBusy表示功能重计，默认不改事件；步骤依赖：04。
- **正常验收**：重叠会议合并、透明/取消事件不占忙，输出UTC范围且可序列化
- **异常／边界验收**：接触边界、零时长、全天覆盖、不同忙碌类型及floating无参考时区时有确定策略
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 06．在指定实例处分割复发系列

- **来源／场景**：用户想只把下周起的例会改成新安排；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/calendar.py)。
- **原版缺口**：原版能编辑RRULE与RECURRENCE-ID，但没有保持旧实例/例外一致的split_series操作
- **交付及模块**：新增系列分割计划，生成前后master并迁移例外、RDATE/EXDATE和RELATED-TO关联；`src/icalendar/cal/calendar.py`, `src/icalendar/cal/event.py`, `src/icalendar/prop/recur/recur.py`。
- **兼容与实际依赖**：显式生成新UID与旧系列边界；先返回计划不就地半改，保留原始组件备份；不自动发送日程邀请；步骤依赖：04。
- **正常验收**：在中间发生实例分割后前后展开并集等于原系列，后段可独立改变时间
- **异常／边界验收**：首个/最后实例、COUNT/UNTIL、取消例外、跨DST和RANGE=THISANDFUTURE不能丢失既有覆盖
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 07．整组日程的一致时间平移

- **来源／场景**：资料项目延期，需要把同一组主事件与例外整体后移；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/event.py)。
- **原版缺口**：单事件已有set_start/set_end保持duration/end锁定，但缺系列或日历级平移RRULE相关值及相对/绝对提醒的合同
- **交付及模块**：新增shift_schedule，明确墙钟或绝对时间策略并统一更新master、例外、RDATE/EXDATE和相关日期；`src/icalendar/cal/event.py:set_start`, `src/icalendar/cal/calendar.py`, `src/icalendar/alarms.py`。
- **兼容与实际依赖**：不重复计已有单事件setter；普通UID和文本保持，绝对提醒是否平移显式选择，原历可保留；步骤依赖：无。
- **正常验收**：整组后移一周，例外仍对应正确实例，时长和相对提醒保持
- **异常／边界验收**：DST跨度、floating/date、跨年UNTIL、绝对VALARM和只选择部分关联组件有明确预检
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 08．全天与定时事件的显式转换

- **来源／场景**：整理日要改为上午会议，或把跨时区任务改为全天标记；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/event.py)。
- **原版缺口**：Event日期setter接受date/datetime，但没有一起转换结束、复发例外及提醒的业务策略
- **交付及模块**：新增convert_all_day，要求参考时区、日期范围和结束策略，给出转换预览；`src/icalendar/cal/event.py`, `src/icalendar/attr.py`, `src/icalendar/alarms.py`。
- **兼容与实际依赖**：不把date直接假设为UTC午夜；保持排他结束规则，可能有损的时间信息明确返回；步骤依赖：无。
- **正常验收**：全天两日转定时按指定本地时刻和范围生成，定时转全天覆盖日按约定确定
- **异常／边界验收**：跨午夜/夏令时、零时长、多日RRULE、date型例外和绝对提醒不能被无提示误改
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 09．保留参数的参会者更新

- **来源／场景**：本地会议编辑只改一人的参与状态，同时保留CN/ROLE等参数；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/attr.py)。
- **原版缺口**：attendees属性已支持vCalAddress列表和赋值，缺按CAL-ADDRESS定位并部分更新的原子操作
- **交付及模块**：新增upsert/remove attendee helper，保留未改参数并明确重复地址处理；`src/icalendar/attr.py:attendees_property`, `src/icalendar/prop/cal_address.py`, `src/icalendar/cal/event.py`。
- **兼容与实际依赖**：复用原有vCalAddress；不重计参会者基础支持，不擅自统一所有URI大小写或移除委派关系；步骤依赖：无。
- **正常验收**：按地址把PARTSTAT改ACCEPTED，CN/ROLE/RSVP等未指定字段保持
- **异常／边界验收**：重复地址、多值DELEGATED-TO、mailto大小写、未知URI与无匹配删除按显式规则执行
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 10．待办状态的一致转换

- **来源／场景**：完成资料整理待办时要同时维护STATUS/COMPLETED/PERCENT-COMPLETE；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/todo.py)。
- **原版缺口**：Todo已表示状态和时间字段，示例要求调用者手工写三字段，缺转换动作及撤销合同
- **交付及模块**：新增Todo transition，统一完成、重开、取消动作与时间戳/进度验证；`src/icalendar/cal/todo.py`, `src/icalendar/attr.py:status_property`。
- **兼容与实际依赖**：保留直接属性编辑；动作明确是否更新SEQUENCE/DTSTAMP，不把业务流程自动当日程邀请协议；步骤依赖：无。
- **正常验收**：complete设置100和UTC完成时间，reopen按选项清完成字段且状态一致
- **异常／边界验收**：无开始/截止日、重复complete、未来完成时间、非法进度及取消转重开给出清楚结果
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 11．可解释的日历语义差异

- **来源／场景**：两次导出不同但用户要知道具体哪个会议属性改变；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/component.py)。
- **原版缺口**：Component.__eq__已有深层相等比较，to_ical可排序；无带组件身份与属性参数的差异结果
- **交付及模块**：新增semantic_diff，按UID/RECURRENCE-ID匹配并报告组件、值、参数和子组件改动；`src/icalendar/cal/component.py:__eq__`, `src/icalendar/cal/calendar.py`。
- **兼容与实际依赖**：不把已有相等判断说成缺失；不以字节folding差异冒充语义修改，不默认应用补丁；步骤依赖：无。
- **正常验收**：改SUMMARY、参会者PARTSTAT及增加VALARM各有定位，纯换行折叠可忽略
- **异常／边界验收**：重复UID、无UID子组件、参数多值顺序、timezone定义和date/datetime差异有可配置解释
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 12．按版本信息合并多个日历

- **来源／场景**：同一团队从两个本地导出恢复日程，需要识别新旧及冲突；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/component.py)。
- **原版缺口**：已有with_uid查询及Component.copy，调用方可自行拼接；无SEQUENCE/DTSTAMP/RECURRENCE-ID联合合并策略
- **交付及模块**：新增merge_calendar计划，分组master/exception、比较版本并保留并行冲突供选择；`src/icalendar/cal/component.py:with_uid`, `src/icalendar/cal/calendar.py`, `src/icalendar/cal/event.py`。
- **兼容与实际依赖**：默认不擅自选同版本不同内容；保留未知属性及VTIMEZONE冲突，不自动更改主日历；步骤依赖：无。
- **正常验收**：较新SEQUENCE版本选入，互不重叠UID合并，例外与master保持关联
- **异常／边界验收**：缺时间戳、同序列不同内容、取消记录、重复UID和同TZID不同定义有明确冲突结果
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 13．版本化的语义摘要

- **来源／场景**：归档去重想忽略无关折行与属性顺序，同时识别真实日程改动；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/component.py)。
- **原版缺口**：to_ical(sorted=True)已有稳定排序选项，但没有声明语义范围的canonical摘要配置
- **交付及模块**：新增calendar_fingerprint profile，规范日期/参数集合及可选忽略导出时间戳后计算摘要；`src/icalendar/cal/component.py:to_ical`, `src/icalendar/parser/content_line.py`。
- **兼容与实际依赖**：不把已有排序重新当功能；默认不忽略业务字段，摘要版本与选项必须写入结果；步骤依赖：无。
- **正常验收**：仅folding/允许的属性重排变化摘要相同，SUMMARY或DTSTART修改则不同
- **异常／边界验收**：多值参数、复发覆盖、floating时区、未知扩展和忽略字段白名单均有明确规范化规则
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 14．解析诊断的物理行及来源位置

- **来源／场景**：导入文件出现坏参数时需要定位原始折叠行；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/parser/content_line.py)。
- **原版缺口**：Component.errors已有字段/消息，Contentlines先展开输入，缺组件/属性到原始字节/物理行的统一位置
- **交付及模块**：新增opt-in parse_locations与结构化诊断，保留物理行、展开行、字节/字符跨度；`src/icalendar/parser/content_line.py`, `src/icalendar/parser/ical/component.py`, `src/icalendar/cal/component.py`。
- **兼容与实际依赖**：默认对象接口和宽容策略保持；非UTF8或不可解码部分不伪造字符位置，错误代码与消息分列；步骤依赖：无。
- **正常验收**：坏DTSTART或参数能定位到原文件对应折叠物理行，合法值也能查来源
- **异常／边界验收**：UTF8折叠、多字节、CRLF/LF、重复属性、嵌套和LazyCalendar解析时位置不丢失
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 15．只重写改动属性的保真编辑

- **来源／场景**：档案校订只改标题，希望未改部分的大小写、参数次序和folding保留；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/parser/content_line.py)。
- **原版缺口**：普通to_ical会规范化内容；LazyCalendar延迟解析不是可编辑原文补丁合同
- **交付及模块**：新增source-preserving document，跟踪改动组件/属性并对原范围应用文本编辑；`src/icalendar/parser/content_line.py`, `src/icalendar/parser/ical/lazy.py`, `src/icalendar/cal/component.py`。
- **兼容与实际依赖**：依赖位置模型；原to_ical保持规范输出，保真模式不声称能还原已丢失原字节来源的对象；步骤依赖：14。
- **正常验收**：只改SUMMARY时其他原始行逐字节保持，改行按当前编码与fold规则合法输出
- **异常／边界验收**：重复属性、插入/删除、组件移动、外部原文变动和属性跨折叠行均有冲突检测
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 16．按输入块读取日历组件

- **来源／场景**：本地大型归档文件需要逐个消费事件而非一次读全串；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/parser/content_line.py)。
- **原版缺口**：LazyCalendar已有延迟属性/子组件解析，但ComponentIcalParser仍先把bytes/str转完整Contentlines列表
- **交付及模块**：新增stream reader，增量解码/展开折行并在完整组件结束时yield，明确VTIMEZONE先后依赖；`src/icalendar/parser/content_line.py`, `src/icalendar/parser/ical/component.py`, `src/icalendar/parser/ical/lazy.py`。
- **兼容与实际依赖**：不重复计LazyCalendar；已有from_ical保持，遇后置timezone可缓存所需未决片段而不假定已知；步骤依赖：无。
- **正常验收**：任意正常块划分与全量解析语义一致，多个Calendar或事件可按顺序消费
- **异常／边界验收**：UTF8/CRLF/折行跨块、EOF未闭合、后置VTIMEZONE及消费者提前close都有明确状态
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 17．每次解析独立的时区上下文

- **来源／场景**：两个资料源含同名自定义TZID，希望分别解释；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/timezone/__init__.py)。
- **原版缺口**：公共tzp是共享实例，ComponentIcalParser保存全局tzp并在VTIMEZONE结束缓存；虽能构造TZP对象，但from_ical无独立provider入口
- **交付及模块**：新增ParseContext显式注入TZP/provider及缓存生命周期，避免不同日历相互影响；`src/icalendar/timezone/__init__.py`, `src/icalendar/timezone/tzp.py`, `src/icalendar/parser/ical/component.py`。
- **兼容与实际依赖**：默认全局use_pytz/use_zoneinfo行为保持；新上下文不修改进程全局，getter/serializer沿用对象时区；步骤依赖：无。
- **正常验收**：同名TZID在两个独立上下文可有各自定义，重复解析仍按各自缓存结果
- **异常／边界验收**：并发解析、LazyCalendar延后访问、Windows别名、自定义provider和未知TZID不串用状态
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 18．嵌入时区与运行数据库的差异审计

- **来源／场景**：跨年归档要了解文件VTIMEZONE与当前IANA规则是否一致；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/timezone.py)。
- **原版缺口**：已有used/missing TZID查询、add_missing_timezones、from_tzinfo与get_transitions；没有按业务窗口比较嵌入定义和provider并出差异报告
- **交付及模块**：新增timezone audit，在独立上下文比较偏移/转换时刻，报告覆盖范围及不一致来源；`src/icalendar/cal/timezone.py:get_transitions`, `src/icalendar/cal/calendar.py:get_missing_tzids`, `src/icalendar/timezone/tzp.py`。
- **兼容与实际依赖**：复用既有生成/查询能力，不把provider规则自动当唯一真相；只报告不替换文件时区；步骤依赖：17。
- **正常验收**：一致时区在指定窗口无差异，旧规则与新数据库差异明确列出转换时刻
- **异常／边界验收**：缺时区、有限覆盖、固定偏移、vendor TZID猜测与DST歧义保持可解释未知状态
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 19．本地附件导出及清单

- **来源／场景**：资料归档要把嵌入的二进制附件保存为文件并保留来源关联；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cal/component.py)。
- **原版缺口**：ATTACH与vBinary/vUri已有编码表示，没有导出文件、重名策略和组件到附件清单合同
- **交付及模块**：新增export_attachments，为嵌入附件生成调用方控制的文件名/摘要清单，URI附件只登记；`src/icalendar/cal/component.py`, `src/icalendar/prop/binary.py`, `src/icalendar/attr.py:attachments_property`。
- **兼容与实际依赖**：不改变原日历，不自动下载URI，不依据任意URI创建路径；保留FMTTYPE与未知参数；步骤依赖：无。
- **正常验收**：两场会议内相同附件可按摘要复用并保留各自UID/属性引用，字节内容一致
- **异常／边界验收**：空附件、无名附件、重复命名、解码错误、大附件和中断写出不产生错误成功清单
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。

## 20．可查询的本地agenda命令

- **来源／场景**：管理员想查看指定一周的中文日程并输出机器数据；[固定源码](https://github.com/collective/icalendar/blob/3ecf079acba0e592ea6a40c456514984c8657852/src/icalendar/cli.py)。
- **原版缺口**：现有CLI已支持多ICS/标准输入和人类摘要，但只遍历VEVENT，缺日期窗口、输出时区与结构化agenda
- **交付及模块**：扩展CLI agenda，按显式窗口通过复发适配查询，支持排序、时区和JSON/CSV投影；`src/icalendar/cli.py`, `src/icalendar/cal/calendar.py`, `pyproject.toml`。
- **兼容与实际依赖**：保留现有预览默认行为；复发依赖可选且缺失时明确提示，不把master直接当唯一发生实例；步骤依赖：04。
- **正常验收**：窗口内普通与复发例外按指定时区排序输出，JSON保留UID和发生实例身份
- **异常／边界验收**：全天排他结束、跨日事件、空窗口、坏文件、不同源相同UID及部分失败有准确状态
- **原生回归**：`src/icalendar/tests/test_cli_tool.py`, `src/icalendar/tests/test_recurrence.py`, `src/icalendar/tests/test_issue_899_copy_component.py`, `src/icalendar/tests/test_issue_1050_lazy_calendar.py`, `src/icalendar/tests/test_issue_716_alarm_time_computation.py`, `src/icalendar/tests/test_issue_722_generate_vtimezone.py`, `src/icalendar/tests/test_issue_898_todo_end.py`, `src/icalendar/tests/test_timezone_identification.py`。
