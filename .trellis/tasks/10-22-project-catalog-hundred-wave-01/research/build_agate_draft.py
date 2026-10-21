"""制作Agate编号保真、计算派生、维表取证和金额完整率任务。"""
from draft_content import build_project


def main() -> None:
    """保存四场景九项独立只读业务。@return None。"""
    materials = {
        'materials/input.csv': 'code,amount,note\n001,2.50,NA\n002,3.75,keep\n',
        'materials/types.md': 'Compare default Table.from_csv with column_types forcing code and note to Text(cast_nulls=False) and amount to Number. code is an exact external identifier; NA in note is literal business text, not missing data. Monetary values remain decimal. Do not edit files.\n',
        'materials/sampling.md': 'Construct Table([("2",),("oops",)],["qty"],TypeTester(limit=1)) and compare full inference. Separately construct a three-row one-shot generator of strings2,3,4 that records pulls, with the same limit1. The team asks whether limiting inference makes construction streaming and guarantees later values fit the guessed type.\n',
        'materials/derivatives.md': 'Construct a typed Table with rows(A,2),(B,1),(C,3), columns order:Text and amount:Number. Filter amount>=2 then order_by amount descending. Separately compute double=amount*2 and plus=double+1 using Formula(Number(),callback): compare listing both in one compute with two explicit compute stages. Inspect the original table after each attempt.\n',
        'materials/join-symptom.md': 'A regional report grew in row count and amount after joining a dimension table. Actual left/right rows, join arguments and expected key cardinalities have not been supplied. Investigate before assigning a cause.\n',
        'disclosure/join.md': 'Complete synthetic data: left(key:Text,qty:Number)=(A,2),(A,3),(B,1); right(key:Text,zone:Text)=(A,east),(A,west). Call left.join(right,"key") without inner/full_outer/require_match options. No deduplication or transaction is present. Compare with inner=True and with require_match=True; separately test require_match on only matched A rows.\n',
        'disclosure/unavailable.md': 'No original table rows, key-cardinality profile or join arguments can be supplied. There is no additional incident evidence.\n',
        'materials/join-policy.md': 'The importer requires exactly one approved dimension match per fact row and no unmatched fact keys. Counts and additive quantities must not change after enrichment. Plan checks using current Table APIs and explicit cardinality policy, including normal, duplicate and missing-key controls. No implementation or database exists.\n',
        'materials/dimension-controls.md': 'Complete plan controls: left(key:Text,qty:Number)=(A,2),(A,3),(B,1); right(key:Text,zone:Text)=(A,east),(A,west). Compare the default left join, inner=True and require_match=True, then only matched A facts. This complete planning example is public to AG-P01; AG-D01 receives its own evidence only through its disclosure branch.\n',
        'materials/totals.md': 'Typed rows(region:Text,amount:Number)=(east,2),(east,None),(west,3). Compare Sum(amount), Count(), Count(amount), Count(amount,None), and group_by(region).aggregate with total/present/rows. Separately compare a two-row all-None Number column and a two-row all-zero Number column. A report needs amount totals and measurement completeness, not fabricated zero measurements.\n'}
    definitions = [
        ('AG-U01', 'understand', '追踪编号和空值在推断后的真实类型',
            'Trace the supplied CSV under default type inference. Report exact first-row identifier, amount and note values/types and explain why this may violate the business meaning. Do not modify files.',
            ['materials/input.csv', 'materials/types.md'], 'explained',
            'The numeric-looking code001 becomes Decimal1, amount2.50 is Decimal, and NA becomes None under default null tokens. Type inference cannot know identifier or literal-note business meaning; this is not automatic lossless raw-text preservation.', ['inference_converts_leading_zeroes_and_null_tokens']),
        ('AG-C01', 'consult', '用已有列类型保留外部编号和字面NA',
            'Recommend the supplied exact-ID/literal-note import policy with current APIs while keeping amount numeric. Give preservation controls and distinguish absent None from literal null tokens. No implementation is authorized.',
            ['materials/input.csv', 'materials/types.md'], 'advice_no_code_change',
            'Force code and note to Text(cast_nulls=False), amount to Number via column_types mapping/TypeTester force. code001 and literal NA survive while amount remains Decimal2.50. Existing None remains None even with cast_nulls=False; define missing-data policy separately rather than making every field untyped text.', ['explicit_types_preserve_identifiers_and_literal_null_tokens']),
        ('AG-U02', 'understand', '解释有限推断样本的后续转换和内存边界',
            'Trace both complete sampling reproductions and full inference. State actual failure/source consumption and whether the inference limit guarantees streaming or whole-file schema compatibility. Do not edit files.',
            ['materials/sampling.md'], 'explained',
            'limit1 guesses Number from2 then raises CastError on later oops; full inference selects Text and retains both strings. TypeTester-backed Table construction materializes all source rows before inference, so the three-row generator is fully pulled despite limit1. Sampling bounds inference work only, not table memory or later casting guarantees.', ['limited_inference_still_materializes_and_casts_all_rows']),
        ('AG-U03', 'understand', '解释筛选排序如何产生新表',
            'Trace the complete typed-order filtering/sorting example. Report derivative row order and original state, distinguishing table immutability from a claim of zero allocation or streaming. No changes are requested.',
            ['materials/derivatives.md'], 'explained',
            'The derivative order is C,A; original rows remain A,B,C and original columns remain order,amount. where/order_by return new tables rather than mutating source; immutable table semantics do not promise deep copying every Python object, zero extra memory or lazy streaming.', ['derivatives_preserve_original_rows_and_order']),
        ('AG-C02', 'consult', '为有依赖的新列选择明确计算阶段',
            'Recommend current compute/Formula usage for double then plus. Compare the simultaneous attempt with two stages and identify which input table each callback receives. Do not implement or add a new library feature.',
            ['materials/derivatives.md'], 'advice_no_code_change',
            'Every computation in one compute call reads the original self; plus cannot read newly computed double there and raises KeyError. Compute double first, then plus on the returned table: plus values5,3,7. Original table stays unchanged, and stage ownership is explicit; list ordering alone is not a computation dependency graph.', ['dependent_computations_require_explicit_stages']),
        ('AG-D01', 'diagnose', '先取左右表和匹配参数再解释报表放大',
            'Investigate the supplied enrichment symptom. Request sufficient actual rows, join arguments and expected key cardinality before choosing a cause. Diagnose disclosed evidence only or close with an evidence plan if unavailable. Do not change code/data.',
            ['materials/join-symptom.md'], 'diagnosed_no_code_change',
            'Initially request sufficient left/right rows or cardinality evidence, exact join arguments and intended relationship. Attribute only disclosed reproduction behavior to pinned join semantics; no invented duplicate keys, production data or library defect. insufficient_information is valid when evidence cannot be supplied.', None),
        ('AG-P01', 'plan', '规划一对一维表准入和连接后守恒检查',
            'Plan the complete one-approved-dimension-match requirement with existing APIs. Explain duplicate/missing controls, require_match limits and post-join count/quantity checks. Do not implement or invent transactions/unique constraints.',
            ['materials/join-policy.md', 'materials/dimension-controls.md'], 'planned_without_library_change',
            'The disclosed left join produces5 rows and qty11 from original3/qty6; inner gives4/qty10. require_match rejects B but accepts duplicate matches for only A rows, so it is not uniqueness enforcement. Validate dimension key uniqueness and missing fact keys before joining, define reject/resolve ownership, then assert row/quantity conservation. Never silently choose a duplicate or drop unmatched facts.', ['duplicate_dimension_matches_expand_measures', 'require_match_rejects_missing_not_duplicate_keys']),
        ('AG-U04', 'understand', '区分区域金额、行数和非空测量数',
            'Trace the supplied total and grouped aggregations. Give actual row/non-null/null counts and regional values; explain each result rather than inferring completeness from a sum. Do not edit files.',
            ['materials/totals.md'], 'explained',
            'Sum5, Count()3, Count(amount)2, Count(amount,None)1. East has total2,present1,rows2; west total3,present1,rows1. Sum ignores null amounts, while row and present counts answer different business questions. Groups retain typed results, not merely string counts.', ['group_totals_and_non_null_counts_have_distinct_meanings']),
        ('AG-C03', 'consult', '避免把全缺失金额误报为真实零值',
            'Recommend a current-API completeness policy for the complete all-null versus all-zero comparison. State exact existing sums/counts and a report representation that preserves the distinction. No implementation is requested.',
            ['materials/totals.md'], 'advice_with_limits',
            'Both all-null and all-zero Number columns sum to0, but Count(amount) is0 versus2. Report sum together with present/row counts and an explicit no-measurements status or nullable business result. Do not change Sum globally or claim an all-null sum proves two measured zero values.', ['all_null_sum_does_not_establish_zero_measurements'])]
    scenes = [('AG-S01', '编号与导入schema', '按业务含义决定类型、空值和推断样本', ['AG-U01', 'AG-C01', 'AG-U02']),
        ('AG-S02', '不可变派生表与计算', '明确新表所有权和跨列计算阶段', ['AG-U03', 'AG-C02']),
        ('AG-S03', '维表匹配取证与准入', '按真实连接语义检查一对一关系和数量守恒', ['AG-D01', 'AG-P01']),
        ('AG-S04', '区域金额与测量完整率', '同时报告金额、行数和有效测量数', ['AG-U04', 'AG-C03'])]
    build_project('agate', {'title': 'Agate数据分析工作场景', 'category': '类型化表格与分析',
        'description': '真实编号保真、有限推断、计算阶段、维表取证和测量完整率九项独立只读任务。'}, definitions, scenes, materials,
        branches={'AG-D01': [{'id': 'join-evidence', 'when': 'The actual tables/cardinalities and join arguments have not been supplied or declared unavailable, and the answer reasonably requests sufficient evidence.', 'materials': ['disclosure/join.md']}]},
        extra_entries={'AG-S03': [{'id': 'diagnose_only', 'task_ids': ['AG-D01']},
            {'id': 'unavailable', 'task_ids': ['AG-D01'], 'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
