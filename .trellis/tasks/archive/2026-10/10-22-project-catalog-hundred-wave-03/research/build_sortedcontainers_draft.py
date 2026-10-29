"""制作有序索引、视图和分页的独立业务问题。"""
from draft_content import build_project


def main() -> None:
    """冻结六项只读任务和比较失败的完整披露入口。@return None。"""
    materials = {
        'materials/multiplicity.md': 'A local order contains product quantities [3,1,3,2]. Compare list(SortedList(values)) and list(SortedSet(values)). Explain ordered multiplicity versus uniqueness before choosing a representation;do not discard a repeated order line by calling it a sort operation. No edits.\n',
        'materials/views.md': 'mapping=SortedDict({3:"A",1:"Z",2:"B",4:"Y"});view=mapping.values();snapshot=list(view);del mapping.keys()[1:3]. Explain snapshot,the live view and final mapping items after the complete sequence. Values are ordered by keys,not by their own alphabetic order. Deletion uses sorted rank positions. No edits.\n',
        'materials/neighbors.md': 'On SortedList([1,3,3,5]),compute strict predecessor/successor of3 using bisect_left/right,and floor/ceiling of4 using its insertion point. Inspect probes0 and6 and an empty list. Advise correct side selection and explicit edge handling;unconditionally indexing -1 is not a valid no-predecessor policy. No implementation.\n',
        'materials/key-stability.md': 'first={id:A,rank:1},second={id:B,rank:2};records=SortedKeyList([first,second],key=lambda item:item["rank"]). Mutate first["rank"]=3 after insertion. Inspect iteration,bisect_key_right(2),and a newly constructed SortedKeyList over those records. Advise the existing stable-sort-key contract and a safe application update/rebuild lifetime. Do not claim automatic index refresh or search for a changed value by assuming its new key is the old cached key. No edits.\n',
        'materials/cursor-plan.md': 'Records with IDs1,2,3 have rank1 and ID4 rank2. Compare a SortedKeyList keyed only by rank with one keyed by(rank,id). The first page is IDs1,2. Compare continuation after bisect_key_right(1) with continuation after bisect_key_right((1,2)). Plan stable cursor ownership,unique tie-breakers and an explicit snapshot/update policy;the container does not provide a database cursor or snapshot isolation. No implementation.\n',
        'disclosure/failed-insert.md': 'Complete synthetic reproduction: values=SortedSet([1,2]);values.add("x") raises TypeError during ordering. After catching that error,len(values)==3,"x" in values is True,but list(values)==[1,2]. The hash set was modified before sorted-list insertion failed. No other operations,threads or mutable keys are involved. Diagnose this actual state and advise validation/recovery from a known-valid source;do not claim catching the exception automatically rolled it back. No source patch is authorized.\n',
        'disclosure/unavailable.md': 'The complete initial values/types,insertion operation,exception and membership/length/iteration controls cannot be supplied.\n'}
    definitions = [
        ('SC-U01', 'understand', '保留有序订货明细的重复项', 'Explain actual multiplicity in both complete controls. No edits.', ['materials/multiplicity.md'], 'explained',
            'SortedList returns1,2,3,3 while SortedSet returns1,2,3. Choose ordered multiplicity or set uniqueness according to the order contract;sorting alone does not authorize dropping repeated product lines.', ['sorted_list_multiplicity_and_set_uniqueness_are_different_contracts']),
        ('SC-U02', 'understand', '追踪实时视图和排名切片删除', 'Explain all final view/snapshot/mapping states. No edits.', ['materials/views.md'], 'explained',
            'Snapshot stays Z,B,A,Y in key order1,2,3,4. Deleting keys()[1:3] removes keys2 and3 from the mapping;the live values view becomes Z,Y and items are1/Z,4/Y. A copied list is a snapshot but the view is live and values remain ordered by key.', ['ordered_views_are_live_and_rank_deletion_changes_the_mapping']),
        ('SC-C01', 'consult', '选择邻近排期的二分边界', 'Advise strict/non-strict neighbor lookup and every edge control. No implementation.', ['materials/neighbors.md'], 'advice_no_code_change',
            'For3,strict predecessor is1 via left-1 and successor5 via right. For4,floor3 and ceiling5 straddle its left insertion point. Probe0 gives left0,probe6 gives right=len,and empty gives0;guard missing sides explicitly instead of returning the opposite endpoint or indexing beyond length.', ['neighbor_queries_require_distinct_bisect_sides_and_edge_guards']),
        ('SC-C02', 'consult', '规划对象排序键的更新归属', 'Advise the actual mutated-key and fresh-index controls. No edits.', ['materials/key-stability.md'], 'advice_no_code_change',
            'The stored cache remains based on1,2 while object iteration now shows ranks3,2;bisect_key_right(2) still returns2. A fresh index recomputes keys and orders B,A. The existing contract requires stable keys while stored;remove using the old valid state before mutation/reinsert,or rebuild from a known-valid source. This is not evidence of promised automatic refresh.', ['mutating_a_stored_sort_key_does_not_refresh_the_cached_index']),
        ('SC-P01', 'plan', '规划同优先级记录的连续分页', 'Plan continuation with a stable tie-breaker and declared update policy. No implementation.', ['materials/cursor-plan.md'], 'planned_without_library_change',
            'Rank-only continuation after first page1,2 uses right(1),skipping the remaining rank1 record3 and returning4. Composite(rank,id) continuation after(1,2) returns3,4. Require a stable unique tie-breaker,bind the cursor to its sort definition and explicitly choose snapshot/version or documented update semantics. The container supplies searches,not persistent cursor isolation.', ['pagination_needs_a_stable_tie_breaker_and_explicit_snapshot_policy']),
        ('SC-D01', 'diagnose', '诊断写入失败后的成员与顺序差异', 'After catching an insertion error,a sorted collection reports inconsistent membership and iteration. Request full initial types,operation,exception and state controls before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
            'Use only actually consumed initial values,operation,exception and state observations. Request missing complete controls,then trace the actual index update order when established and advise caller-owned validation/recovery from known-valid data. Do not assume failed operations are transactional or authorize a source patch. Missing evidence supports insufficient_information.', None)]
    scenes = [('SC-S01', '集合与映射语义', '明确数量与实时视图', ['SC-U01', 'SC-U02']),
        ('SC-S02', '有序索引查询和更新', '明确二分与键稳定', ['SC-C01', 'SC-C02']),
        ('SC-S03', '分页设计', '保留相同排序键记录', ['SC-P01']),
        ('SC-S04', '写入失败诊断', '核完整失败和状态', ['SC-D01'])]
    build_project('sortedcontainers', {'title': 'Sorted Containers本地索引工作场景', 'category': '有序状态与业务查询',
        'description': '重复项、实时视图、邻居查询、键缓存、分页及失败状态诊断。'}, definitions, scenes, materials,
        branches={'SC-D01': [{'id': 'complete-failed-insert',
            'when': 'Complete initial values/types,operation,exception and state controls have not been supplied or declared unavailable,and are reasonably requested.',
            'materials': ['disclosure/failed-insert.md']}]},
        extra_entries={'SC-S04': [{'id': 'unavailable', 'task_ids': ['SC-D01'], 'materials': ['disclosure/unavailable.md']}]},
        license_files=['seed/library/LICENSE', 'seed/app/THIRD_PARTY_LICENSES.txt'])


if __name__ == '__main__':
    main()
