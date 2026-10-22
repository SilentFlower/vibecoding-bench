"""制作标识双射维护、冲突策略与批量发布的实际任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结六项独立业务判断及完整和缺材料诊断路径。@return None。"""
    rows = [
        ('BI-U01', 'understand', '区分赋值与严格插入', 'Start bidict(a=1). Assign b["a"]=2; then separately try b.put("a",3) and b["b"]=2 on that state. Explain exceptions and retained associations. No edits.',
            'Assignment replaces the old value for the existing key, leaving a:2. put defaults to ON_DUP_RAISE and raises KeyDuplicationError for a:3. A new key claiming existing value2 raises ValueDuplicationError. Failed operations retain a:2; the double-sided uniqueness contract differs from plain dict.', 'assignment_and_put_have_distinct_duplicate_defaults'),
        ('BI-U02', 'understand', '理解反向标识视图的实时性', 'Start b=bidict(a=1); inv=b.inverse; set inv[2]="b"; delete b["a"]. Explain both maps and inv.inverse identity. No edits.',
            'The inverse shares both backing mappings: mutation through inv adds b:2 forward, and deleting a removes inverse1. Final maps are {b:2} and {2:b}; inv.inverse is b. It is a live mutable view, so use a separate snapshot when a report must remain stable.', 'inverse_is_a_live_mutable_bijection_view'),
        ('BI-C01', 'consult', '选择有损冲突处理策略', 'On bidict(a=1,b=2), first put("a",2,on_dup=OnDup(key=DROP_OLD,val=DROP_NEW)); then forceput("a",2). Advise a safe import policy and enumerate displaced associations. No implementation.',
            'The cross-item duplicate uses the val policy, so DROP_NEW keeps both original associations. forceput drops both conflicting associations and leaves only a:2, shrinking cardinality from2 to1. Require an explicit conflict report and business-approved replacement policy; forceput is not a lossless swap or merge.', 'forceput_can_displace_two_associations_and_shrink_cardinality'),
        ('BI-C02', 'consult', '选择稳定导出快照', 'Start b=bidict(a=1); take b.copy() and frozenbidict(b); then set b["b"]=2. Advise mutable working copies versus immutable/hashable scalar snapshots for a report. State the shallow-object limitation. No edits.',
            'Both copies retain only a:1 when the original gains b:2. copy is an independent mutable map; frozenbidict has no item assignment and is hashable by items. The supplied scalar keys/values are immutable; do not generalize to a recursive deep freeze or to safe mutation of user-defined hash/equality state.', 'copy_and_frozen_snapshot_are_independent_of_later_mapping_updates'),
        ('BI-P01', 'plan', '规划双射批量导入的事务边界', 'Start b=bidict(a=1,b=2). A generator logs each yield to events and yields ("c",3),("d",2). Call b.putall(generator). Plan retry/publication and external-effect handling based on the actual failure/rollback contract. No implementation.',
            'The second value conflicts and raises ValueDuplicationError; putall rolls the mapping back to a:1,b:2. Both input yields and their event log remain consumed. Plan to materialize/validate finite input once, preserve a conflict report, stage a separate working map and publish only success. Mapping rollback cannot undo an external log, generator or database operation; define those boundaries separately.', 'bulk_rollback_does_not_undo_consumption_or_external_side_effects')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('BI-D01', 'diagnose', '诊断有序映射比较未发现顺序变化',
        'A report says two OrderedBidict objects compare equal despite different display order. Request complete item sequences, comparison expression, type/version and the intended order-sensitive control. No edits.', [], 'diagnosed_or_information_requested',
        'Use actual comparison evidence to distinguish mapping equality from order-sensitive equality. The inherited == ignores order, while equals_order_sensitive checks it. Missing material supports insufficient_information; do not diagnose data loss or modify comparison semantics without evidence.', None))
    materials['disclosure/order.md'] = 'Pinned OrderedBidict x=[("a",1),("b",2)] and y=[("b",2),("a",1)] yield x==y True, list(x.items())!=list(y.items()) True, and x.equals_order_sensitive(y) False. They are distinct objects and no mutation occurs during comparison. The business report needs to detect reordered associations.\n'
    materials['disclosure/unavailable.md'] = 'Complete sequences, exact comparison, object type/version and order-sensitive control are unavailable.\n'
    answers.update({'BI-D01-question': 'Please provide both complete item sequences, the exact comparison, actual object type/version and an order-sensitive control. No edits are authorized.',
        'BI-D01': 'This is the supplied mapping equality contract, not evidence of missing data. OrderedBidict inherits order-insensitive == from BidictBase; the exact equals_order_sensitive control is False. Select that explicit order-aware comparison or compare an appropriate ordered representation for this report, and test reordered/equal cases. No library patch was made.',
        'BI-D01-unavailable': 'The exact sequences/comparison/type and control are unavailable. Record insufficient_information and request them when possible; no precise cause or data-loss conclusion is supported.'})
    build_project('bidict', {'title': 'Bidict标识映射工作场景', 'category': '双射、冲突与发布边界',
        'description': '严格插入、实时反向视图、有损替换、稳定快照、批量回滚及顺序比较诊断。'}, definitions,
        [('BI-S01', '双射读写语义', '保持两侧唯一性', ['BI-U01', 'BI-U02']),
         ('BI-S02', '冲突与快照策略', '明确丢弃和报告边界', ['BI-C01', 'BI-C02']),
         ('BI-S03', '批量导入方案', '区分映射回滚与外部副作用', ['BI-P01']),
         ('BI-S04', '顺序变化诊断', '核对实际比较表达式', ['BI-D01'])], materials,
        branches={'BI-D01': [{'id': 'ordered-comparison', 'when': 'Complete sequences, exact comparison, object type/version and order-sensitive control have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/order.md']}]},
        extra_entries={'BI-S04': [{'id': 'unavailable', 'task_ids': ['BI-D01'], 'materials': ['disclosure/unavailable.md']}]})
    Path(__file__).with_name('bidict-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
