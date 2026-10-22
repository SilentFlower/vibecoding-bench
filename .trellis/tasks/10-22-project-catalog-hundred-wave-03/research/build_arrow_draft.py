"""制作真实日期边界、查询分区和时间导入任务，不读取当前时钟。"""
from draft_content import build_project


def main() -> None:
    """冻结四场景六项独立只读任务。@return None。"""
    materials = {
        'materials/month-movement.md': 'Use Arrow(2026,1,31,9),which defaults to UTC. Compare shift(months=1),replace(month=2),and the invalid singular shift(month=1),then inspect the unchanged original. Explain relative arithmetic,absolute validation and the API spelling; no edits or current-clock input.\n',
        'materials/day-ends.md': 'For Arrow(2026,10,22,10,15),compare span("day") with span("day",bounds="[]"). State both actual endpoints and precision. A database report needs an explicitly chosen interval predicate;do not say the returned tuple automatically installs an SQL filter or that the default second endpoint is next midnight. No edits.\n',
        'materials/month-anchor.md': 'Start at Arrow(2026,1,31,9). Compare Arrow.range("month",start,limit=4) with appending a current value and repeatedly replacing current=current.shift(months=1) four times. The billing specification must choose original day-of-month anchoring versus sequential clamping. Explain actual dates and existing controls rather than propose an already available monthly iterator. No implementation or claim about a payment system.\n',
        'materials/timezone-import.md': 'Start with Arrow(2026,10,22,12) in UTC. Compare .to("+02:00") and .replace(tzinfo="+02:00") by wall-clock ISO value and timestamp. The import form must state whether the incoming clock already denotes a UTC instant or is a local clock needing annotation. Explain both existing operations and preserve the original;no files or real event data are changed.\n',
        'materials/day-partition-plan.md': 'Read Europe/Paris from the supplied offline tzdata2026.5 package using ZoneInfo.from_file on zoneinfo/Europe/Paris. For local noon on 2026-03-29 and 2026-10-25,inspect span("day",bounds="[]") and compare endpoint UTC timestamps. Plan application-owned [start,end) report partitions,zone/rule provenance,UTC boundary storage and tests for events exactly at both boundaries. Do not assume a civil day is86400 physical seconds or infer UTC elapsed time from subtraction of identical-zone wall clocks. No implementation,external calendar or publication.\n',
        'disclosure/ambiguous-events.md': 'Complete synthetic reproduction: load Europe/Paris from offline tzdata2026.5 with ZoneInfo.from_file;first=Arrow(2026,10,25,2,30,tzinfo=zone);second=first.replace(fold=1). first.ambiguous is True;folds are0 and1. ISO values are2026-10-25T02:30:00+02:00 and2026-10-25T02:30:00+01:00;UTC values are2026-10-25T00:30:00+00:00 and2026-10-25T01:30:00+00:00. Timestamp difference is3600 seconds. The real input contains only the local clock and zone,without an offset or occurrence/fold. Explain the duplicated wall-clock possibility and the extra business evidence needed to choose a real event instant;no patch or guessed occurrence.\n',
        'disclosure/unavailable.md': 'The complete parsing/construction call,source offset or fold,zone/rule source and exported timestamps cannot be provided. No complete reproduction establishes a timezone,formatting or data cause.\n'}
    definitions = [
        ('AR-U01', 'understand', '区分月末相对移动与绝对替换',
            'Explain all complete month movement and validation controls. No edits.',
            ['materials/month-movement.md'], 'explained',
            'Relative shift(months=1) clamps Jan31 to2026-02-28 and leaves the original Jan31. Absolute replace(month=2) rejects the invalid February31 with ValueError;singular shift(month=1) also rejects its unsupported frame. Distinguish errors and valid existing APIs rather than claim mutation or a missing month feature.',
            ['relative_month_shift_clamps_but_absolute_replacement_validates']),
        ('AR-U02', 'understand', '明确日报区间端点的精度',
            'Explain actual day endpoints and the application filter decision from the complete controls. No edits.',
            ['materials/day-ends.md'], 'explained',
            'Both spans start2026-10-22T00:00:00+00:00. Default [) represents the excluded end by the previous microsecond,23:59:59.999999;bounds=[] gives next-day midnight2026-10-23T00:00:00+00:00. Explain the actual returned values and choose the database comparison separately;do not claim the tuple enforces SQL half-open filtering.',
            ['span_bounds_choose_microsecond_end_or_next_midnight']),
        ('AR-C01', 'consult', '选择月度业务日期锚点',
            'Advise the month anchor policy using the two complete four-date controls. No implementation.',
            ['materials/month-anchor.md'], 'advice_no_code_change',
            'Arrow.range month preserves original day31 where possible: Jan31,Feb28,Mar31,Apr30. Repeated shift starts Jan31,Feb28,Mar28,Apr28 because each new date becomes the next anchor. Choose the business rule explicitly and use the existing appropriate mechanism;do not claim sequential clamping and original anchoring are equivalent or invent a new iterator requirement.',
            ['monthly_range_preserves_the_original_day_anchor']),
        ('AR-C02', 'consult', '选择时间导入的转换或重新标注',
            'Advise which existing operation matches each incoming-time contract,with actual ISO and timestamp controls. No edits.',
            ['materials/timezone-import.md'], 'advice_no_code_change',
            'to(+02) yields14:00+02 and preserves the original UTC timestamp. replace(tzinfo=+02) yields12:00+02 and denotes an instant7200 seconds earlier. One converts an established instant,the other annotates/relabels the same wall clock. Choose from supplied import semantics,not assumptions;the original is unchanged.',
            ['timezone_conversion_and_relabeling_have_different_instants']),
        ('AR-P01', 'plan', '规划夏令时日报的唯一分区',
            'Plan report partition ownership and boundary verification from the actual pinned-zone controls. No implementation.',
            ['materials/day-partition-plan.md'], 'planned_without_library_change',
            'The pinned Paris spring/autumn local days span23 and25 physical hours by UTC timestamps. Retain the chosen zone/rule provenance,derive next local midnight using calendar semantics and pair UTC boundaries with an application-owned start<=event<end predicate. Test endpoint events belong to exactly one partition and normal-day controls;do not add fixed86400 seconds or assume span tuple/subtraction itself enforces physical duration or storage policy.',
            ['civil_day_partition_durations_follow_the_pinned_timezone_rules']),
        ('AR-D01', 'diagnose', '先核时区证据再解释重复本地钟点',
            'Two imported event times appear to collapse to one local clock. Request the complete call,source offsets or fold,zone/rule source and exported timestamps before diagnosing. No edits.',
            [], 'diagnosed_or_information_requested',
            'Use only actually delivered evidence. Request missing call/timezone/offset and output controls before choosing a cause. After a complete consumed reproduction,explain the actual ambiguous wall clock and the two occurrence/UTC controls using the pinned API;do not infer which occurrence a real offset-free input denotes. Ask for event offset/occurrence or an explicit business policy. Unavailable evidence supports insufficient_information;no library patch is authorized.', None)]
    scenes = [
        ('AR-S01', '日期和区间语义', '核真实移动和端点', ['AR-U01', 'AR-U02']),
        ('AR-S02', '业务时间选择', '持有日期锚点与导入语义', ['AR-C01', 'AR-C02']),
        ('AR-S03', '民用日报分区', '按固定时区推导UTC边界', ['AR-P01']),
        ('AR-S04', '重复钟点诊断', '先核时区与事件发生证据', ['AR-D01'])]
    build_project('arrow', {'title': 'Arrow时间导入与报表工作场景', 'category': '日期锚点、时区与区间',
        'description': '相对日期、区间精度、月锚点、时区导入、日报分区和重复钟点诊断六项任务。'},
        definitions, scenes, materials,
        branches={'AR-D01': [{'id': 'complete-time-reproduction',
            'when': 'The complete call,source offset or fold,zone/rule source and timestamps have not been supplied or declared unavailable,and sufficient evidence is reasonably requested.',
            'materials': ['disclosure/ambiguous-events.md']}]},
        extra_entries={'AR-S04': [{'id': 'unavailable', 'task_ids': ['AR-D01'],
            'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
