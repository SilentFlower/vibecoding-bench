"""制作端点、覆盖映射和空闲时间窗口任务。"""
from draft_content import build_project


def main() -> None:
    """冻结五项独立只读区间任务。@return None。"""
    materials = {
        'materials/endpoints.md': 'Compare closedopen(9,10)|openclosed(10,11) with closedopen(9,10)|closedopen(10,11). Inspect membership of10 and len() for both;also inspect len(closed(0,100)). Explain set connectivity and what len actually counts. No edits.\n',
        'materials/overlap.md': 'd=IntervalDict();d[closedopen(9,12)]="open";d[closedopen(10,11)]="meeting". Inspect point values9/10/11,find("open") and len(d). Explain replacement on overlap and grouping by equal values,without interpreting len as covered duration or individual source records. No edits.\n',
        'materials/gaps.md': 'd maps closedopen(9,10) to open. Compare d[closedopen(9,12)] with d.get(closedopen(9,12),"missing"),including returned domains/point11 and original d after both calls. Advise whether an export should expose explicit missing gaps or only covered data. No implementation.\n',
        'materials/iteration.md': 'Inspect only list(islice(iterate(closedopen(9,12),step=0),3));do not fully consume that iterator. Compare step1 and reverse=True,step=-1 on closed(9,11). Advise finite limits,progress/direction and caller validation before scheduling repeated work;do not assume the library rejects zero step or guarantees termination. No edits.\n',
        'materials/free-window.md': 'The work window is[9,17);busy is[9,11)|[13,14). Plan free=window-busy under half-open semantics. Verify exact free components,their intersection with busy,their union with busy clipped to the window,and membership at11/13/17. Actual dates,zones and duration measurement are outside this synthetic integer model and need explicit business rules before real use. No implementation.\n'}
    definitions = [
        ('PT-U01', 'understand', '区分端点缺口与区间长度', 'Explain all supplied endpoint/membership/len controls. No edits.', ['materials/endpoints.md'], 'explained',
            'The first union excludes10 and has two atomic components. The second includes10 and normalizes to one[9,11) component. len(closed(0,100)) is1 because len counts atomic interval components,not numerical width or elapsed duration.', ['interval_components_and_endpoint_membership_are_not_durations']),
        ('PT-U02', 'understand', '追踪重叠覆盖后的状态区间', 'Explain point values,grouped open interval and mapping length. No edits.', ['materials/overlap.md'], 'explained',
            'Last assignment wins on overlap:9open,10meeting,11open. find(open) is[9,10)|[11,12). Equal values share one possibly disconnected key,so len(d)==2 counts stored value groups,not three physical segments or duration.', ['overlapping_interval_assignment_replaces_values_on_the_overlap']),
        ('PT-C01', 'consult', '选择区间查询的缺口表示', 'Advise complete range indexing/get results and original-state preservation. No implementation.', ['materials/gaps.md'], 'advice_no_code_change',
            'Indexing returns only covered[9,10). Range get fills[10,12) with missing in a returned IntervalDict,so11 reads missing there. The original remains only[9,10) and does not contain11. Choose whether to present gaps explicitly;the default fill is not evidence of an existing stored state.', ['range_get_fills_gaps_without_mutating_the_original_mapping']),
        ('PT-C02', 'consult', '明确区间迭代的进展要求', 'Advise all finite zero/positive/reverse-step controls. No edits.', ['materials/iteration.md'], 'advice_no_code_change',
            'The bounded islice zero-step control yields9,9,9;the iterator itself does not advance or terminate. Positive1 yields9,10,11;reverse with-1 yields11,10,9. Validate step/direction,finite limits and callable progress at the application boundary and test termination. Do not fully consume zero-step or claim built-in rejection.', ['iteration_step_and_direction_need_an_application_progress_contract']),
        ('PT-P01', 'plan', '规划工作窗口内的空闲时段', 'Plan the supplied difference and boundary acceptance. No implementation.', ['materials/free-window.md'], 'planned_without_library_change',
            'Free is[11,13)|[14,17). It is disjoint from busy and together with busy clipped to[9,17) exactly covers the work window. Boundary11 is free,13 is busy,and17 is outside the window. Keep this endpoint policy explicit;add source dates,zones,units and duration rules before applying to real schedules. No real allocation or calendar change is authorized.', ['free_schedule_is_the_declared_window_minus_busy_intervals'])]
    scenes = [('PT-S01', '区间与覆盖语义', '明确端点和状态归并', ['PT-U01', 'PT-U02']),
        ('PT-S02', '查询与迭代策略', '显式处理缺口和推进', ['PT-C01', 'PT-C02']),
        ('PT-S03', '空闲时段方案', '核集合与业务边界', ['PT-P01'])]
    build_project('portion', {'title': 'Portion区间排程工作场景', 'category': '端点、覆盖状态与空闲窗口',
        'description': '区间归并、覆盖映射、缺口查询、迭代进展和空闲时段方案。'}, definitions, scenes, materials)


if __name__ == '__main__':
    main()
