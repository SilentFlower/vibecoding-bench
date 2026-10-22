"""制作文本匹配度量和方案边界任务。"""
from draft_content import build_project


def main() -> None:
    """冻结六项有独立业务意义的匹配任务。@return None。"""
    materials = {
        'materials/transposition.md': 'Compare Levenshtein(external=False) and DamerauLevenshtein(external=False) on guide/guied. Explain the exact operations/cost and the choice of distance model for document-name typos. Business probes disable external backends so the actual candidate implementation is observed;the complete original regression separately includes all registered external libraries. No edits.\n',
        'materials/score-scale.md': 'For Levenshtein(external=False),compare raw distance and normalized_similarity on ab/abc and ab/ac. Trace maximum length and normalized_distance. Explain why equal edit counts need not give equal normalized scores. No edits.\n',
        'materials/word-bag.md': 'Compare Jaccard(qval=None,external=False) and the same with as_set=True on tea tea book versus tea book. Also compare tea book with book tea. Advise whether frequency and order are part of the business matching contract. Do not call either score semantic equivalence. No implementation.\n',
        'materials/hamming.md': 'Compare Hamming(external=False) and Hamming(truncate=True,external=False) on ab/abc. Also compare default Hamming and Levenshtein on ab/xab. Advise fixed-position comparison versus edit alignment and whether ignoring unmatched suffixes is acceptable. No edits.\n',
        'materials/threshold-plan.md': 'Both a/b and abcdefghij/abcdefghik have one Levenshtein edit. Inspect normalized_similarity for each. Plan a document-candidate ranking/review threshold with explicit normalization,algorithm/backend,source length,language and tie policies;evaluate against appropriately labeled business examples. The supplied algorithm scores are not match probabilities or a validated production threshold. No implementation.\n',
        'disclosure/helper-interface.md': 'Complete isolated call: words_combinations(Levenshtein(external=False),"tea book","book tea"). It raises AttributeError: \'Levenshtein\' object has no attribute \'equality\'. The helper reads f.equality before invoking f,but the provided Levenshtein class defines no equality property. A separate Jaccard(qval=None,external=False) word-bag control returns1 for the reordered texts,with different semantics. No other wrapper or dynamically added attribute is present. Diagnose scope and choose a tested caller representation/metric if appropriate;do not patch arbitrary attributes or invoke unbounded word permutations.\n',
        'disclosure/unavailable.md': 'The exact metric object,constructor/backend,complete helper call,exception and small controls cannot be supplied.\n'}
    definitions = [
        ('TD-U01', 'understand', '选择文档名颠倒的编辑模型', 'Explain both complete transposition controls. No edits.', ['materials/transposition.md'], 'explained',
            'guide/guied costs2 under Levenshtein and1 under the supplied Damerau model because adjacent transposition is a distinct operation there. Choose the model from intended typo behavior;neither value proves semantic equivalence or universal algorithm superiority.', ['transposition_cost_depends_on_the_selected_edit_model']),
        ('TD-U02', 'understand', '解释编辑数与归一化分数', 'Explain both raw/normalized controls and the denominator. No edits.', ['materials/score-scale.md'], 'explained',
            'Both raw distances are1. Maximum input lengths3 and2 make normalized similarities2/3 and1/2 respectively. distance counts edits;normalized similarity is1-distance/max_length for these controls. Do not mix their scales or infer equal normalized closeness from equal edit counts.', ['raw_distance_and_normalized_similarity_have_different_scales']),
        ('TD-C01', 'consult', '明确词频和集合相似度策略', 'Advise word-bag/set/order semantics using every control. No implementation.', ['materials/word-bag.md'], 'advice_no_code_change',
            'Default Counter-based word Jaccard preserves multiplicity,so tea tea book versus tea book yields2/3. as_setTrue yields1. Reordering tea book does not change its word bag,also yielding1. Choose frequency/set/order meaning explicitly;token overlap is not semantic identity.', ['word_bag_multiplicity_and_set_semantics_are_explicit_choices']),
        ('TD-C02', 'consult', '避免截断比较掩盖文档后缀', 'Advise actual suffix and shift controls. No edits.', ['materials/hamming.md'], 'advice_no_code_change',
            'ab/abc gives Hamming1 but truncateTrue0 because the unmatched suffix is ignored. ab/xab gives positional Hamming3 versus Levenshtein1 insertion. Choose fixed-position versus edit alignment and explicit length policy;do not use a truncated zero as proof the complete strings match.', ['truncated_hamming_can_ignore_a_suffix_and_is_not_edit_alignment']),
        ('TD-P01', 'plan', '规划文档候选分数与复核阈值', 'Plan the score/length-aware acceptance study without inventing a validated threshold. No implementation.', ['materials/threshold-plan.md'], 'planned_without_library_change',
            'Both pairs have one edit,but the single-character pair scores0 and the length10 pair0.9. Define normalization,algorithm/backend,length/language and tie policy,then evaluate precision/recall and review handling against suitable labeled business examples. Retain source and failure evidence;these arithmetic scores are not calibrated match probabilities or an established production threshold.', ['one_edit_normalization_depends_on_length_and_is_not_match_probability']),
        ('TD-D01', 'diagnose', '诊断组合词工具的调用失败', 'A word-combination comparison helper raises unexpectedly. Request exact metric construction,complete call,exception and small controls before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
            'Use only actually consumed metric/call/exception evidence. Request missing controls,trace the relevant helper/object interface when established,and distinguish a compatible caller alternative from a source enhancement. Missing evidence supports insufficient_information. Do not invent attributes,patch source or run unbounded combinatorial work.', None)]
    scenes = [('TD-S01', '距离模型与分数', '明确操作和归一化', ['TD-U01', 'TD-U02']),
        ('TD-S02', '文本比较策略', '选择词频、位置和长度政策', ['TD-C01', 'TD-C02']),
        ('TD-S03', '候选复核方案', '基于真实数据确定阈值', ['TD-P01']),
        ('TD-S04', '比较工具诊断', '取得完整接口证据', ['TD-D01'])]
    build_project('textdistance', {'title': 'Textdistance文档匹配工作场景', 'category': '编辑模型、分数与匹配策略',
        'description': '颠倒成本、归一化、词袋、截断比较、阈值方案和工具诊断。'}, definitions, scenes, materials,
        branches={'TD-D01': [{'id': 'complete-helper-interface',
            'when': 'Exact metric construction/backend,complete helper call,exception and small controls have not been supplied or declared unavailable,and are reasonably requested.',
            'materials': ['disclosure/helper-interface.md']}]},
        extra_entries={'TD-S04': [{'id': 'unavailable', 'task_ids': ['TD-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
