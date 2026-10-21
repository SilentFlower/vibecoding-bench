"""制作Toolz组合、缓存、区域统计和字典账单合并的真实独立任务。"""
from draft_content import build_project


def main() -> None:
    """生成四场景八项自足只读任务，无人为追问或缺失工程目标。@return None。"""
    materials = {
        'materials/pipeline.md': 'Let double(value)=value*2 and increment(value)=value+1. Compare compose(double,increment)(3) with pipe(3,double,increment). Separately create curried.map(double)(iter([1,2,3,4,5])) while recording every double call; inspect the record before consumption, then partition_all(2,mapped). Compare fresh partition(2,[2,4,6,8,10]) with partition_all for a no-order-loss export requirement. No files may be changed.\n',
        'materials/price-key.md': 'The complete pure calculation is price(items,discount=0)=sum(items)-discount. items is a list of integers. Compare default memoize(price)([1,2,3],discount=1) with an explicit key(args,kwargs) producing a hashable representation of items and every relevant discount argument. The supported calls include keyword discount=1 and positional1, plus keyword discount=2. Record actual function calls as test instrumentation only; no external pricing service exists.\n',
        'materials/price-lifetime.md': 'In a complete synthetic example, quote(qty) reads a mutable external unit-price cell initially2. Wrap quote with memoize(quote,cache=an_explicit_empty_dict), call qty2, change price to3, call qty2 again, clear that same cache dict and call qty2 a third time. The application wants current-price behavior; compare explicit cache lifetime with including the pricing input/version in a pure calculation. Do not invent a cache_clear method or call real services.\n',
        'materials/regions.json': '[{"region":"east","qty":1},{"region":"west","qty":2},{"region":"east","qty":3}]\n',
        'materials/grouping.md': 'Feed the complete nonconsecutive-region sequence to groupby("region", one_shot_source), recording all source pulls. Separately use reduceby("region", lambda total,row: total+row["qty"], source, init=0) on a fresh source. The report requires totals only, not retained original orders, and must address memory as distinct regions grow. Do not modify files or substitute itertools.groupby behavior.\n',
        'materials/config-merge.json': '{"base":{"theme":"light","options":{"labels":["a"]}},"override":{"theme":"dark"}}\n',
        'materials/bills.json': '{"first":{"A":2,"B":3},"second":{"A":5,"C":7}}\n',
        'materials/merge-policy.md': 'Compare merge on the supplied config mappings, inspect outer identity and nested options identity, then append b through the result options.labels in a separate in-memory experiment. For the supplied bill mappings, compare merge(first,second) with merge_with(sum,first,second), preserving both original billing dictionaries. The business wants summed charges when keys repeat, not last-write replacement. No project files may be edited.\n'}
    definitions = [
        ('TZ-U01', 'understand', '解释函数组合与数据管道的不同方向',
            'Trace the two complete numeric pipeline expressions. Give their actual outputs and the execution direction of compose versus pipe. Do not modify files or treat the two argument lists as equivalent.',
            ['materials/pipeline.md'], 'explained',
            'compose(double,increment)(3) applies increment then double and yields8; pipe(3,double,increment) applies double then increment and yields7. compose is right-to-left function composition, while pipe passes its data through listed functions left-to-right.', ['compose_and_pipe_have_distinct_order']),
        ('TZ-C01', 'consult', '选择保留订单尾项的已有分批助手',
            'Meet the supplied no-order-loss export requirement using current curried mapping and partition helpers. Explain actual source consumption and final batch behavior, using fresh sources for comparisons. No implementation is authorized.',
            ['materials/pipeline.md'], 'advice_no_code_change',
            'curried.map remains lazy, so double is not called before consumption. partition_all preserves (2,4),(6,8),(10,), while default partition drops the incomplete (10,) tail. Choose partition_all when every record must be exported, and do not accidentally reuse an exhausted comparison iterator or claim curry materializes data.', ['curried_map_remains_lazy', 'partition_all_preserves_partial_tail']),
        ('TZ-U02', 'understand', '解释可哈希缓存键和真实key调用接口',
            'Trace the complete price examples. Explain default list-argument failure and a correct explicit key for both supplied discount call forms. Give results and actual cache-hit/call behavior without changing files.',
            ['materials/price-key.md'], 'explained',
            'Default memoization rejects an unhashable list before executing price. The key callback receives (args,kwargs), not price arguments splatted directly. Normalize items to a tuple and include discount consistently for positional/keyword forms: repeated discount1 yields5 once, distinct discount2 yields4 via a second calculation. Do not drop a price-relevant input or confuse callback signatures.', ['default_memoize_requires_hashable_arguments', 'custom_key_receives_args_kwargs_and_preserves_inputs']),
        ('TZ-C02', 'consult', '为变化价格明确缓存生命周期',
            'Explain the complete external-price/cache-dict reproduction and recommend an explicit current-price policy with existing APIs. Distinguish pure inputs from changing external state and identify the real invalidation handle. Do not modify files or invent methods.',
            ['materials/price-lifetime.md'], 'advice_with_limits',
            'The three quote results are4,4,6: changing external price does not invalidate a cached qty key, and clearing the supplied cache dict permits recomputation. Prefer making pricing input/version explicit in a pure calculation or deliberately scoping/clearing the provided cache. No automatic TTL/current-price detection or returned-function cache_clear API is established.', ['external_state_change_does_not_invalidate_cache']),
        ('TZ-U03', 'understand', '解释全流分组而非连续分组',
            'Trace groupby for the supplied nonconsecutive region orders. Explain which original records appear in each list and when the one-shot input has been consumed. Do not modify files or apply itertools.groupby semantics.',
            ['materials/regions.json', 'materials/grouping.md'], 'explained',
            'Toolz groupby eagerly consumes the full source and groups both east records together despite west between them, preserving original items within lists. The result is east=[qty1,qty3],west=[qty2]; it is not a lazy consecutive-run grouper and retains grouped records.', ['groupby_collects_nonadjacent_full_groups']),
        ('TZ-C03', 'consult', '用已有按键归约避免保留整组订单',
            'Choose an existing API for the supplied totals-only report and explain its memory boundary as region cardinality grows. Compare with retaining groupby lists without implementing changes.',
            ['materials/regions.json', 'materials/grouping.md'], 'advice_no_code_change',
            'Existing reduceby with region key, qty accumulator and init0 yields east4,west2 without intermediate lists of original orders. State still scales with distinct keys and accumulator size; unbounded key cardinality may require an explicit window/eviction/external aggregation policy. Do not promise constant memory for arbitrary keys or propose reduceby as missing functionality.', ['existing_reduceby_keeps_only_business_accumulators']),
        ('TZ-U04', 'understand', '区分浅层新映射和嵌套对象共享',
            'Trace the supplied config merge and subsequent in-memory nested-list edit. Explain precedence, outer identity, whether merge itself changes base.theme, and whether nested options is deeply copied. Do not edit project files.',
            ['materials/config-merge.json', 'materials/merge-policy.md'], 'explained',
            'The result is a new outer dict with theme=dark, while base.theme remains light. merge is shallow and shares the options object, so appending b through result.options.labels also changes base nested labels to[a,b]. Do not call it a deep immutable copy or claim the merge call itself replaced base.theme.', ['merge_is_new_shallow_mapping_with_later_precedence']),
        ('TZ-C04', 'consult', '按账单规则选择覆盖或同键累加',
            'Meet the supplied sum-repeated-charge requirement with current mapping helpers. Compare actual merge and merge_with(sum) outputs and input ownership. No implementation or project-file change is requested.',
            ['materials/bills.json', 'materials/merge-policy.md'], 'advice_no_code_change',
            'merge uses later precedence and produces A5,B3,C7. merge_with(sum) combines all values for each key and yields A7,B3,C7, leaving both original billing mappings unchanged. Use the latter for the supplied additive rule, without claiming nested recursive merge or changing the business rule to last-write replacement.', ['merge_with_aggregates_all_same_key_values'])]
    scenes = [('TZ-S01', '函数组合与订单分批', '明确执行方向、惰性和尾项保留', ['TZ-U01', 'TZ-C01']),
        ('TZ-S02', '纯价格计算与缓存', '按真实键接口和价格生命周期决定缓存政策', ['TZ-U02', 'TZ-C02']),
        ('TZ-S03', '区域订单统计', '按分组或总量目标选择已有全流归约', ['TZ-U03', 'TZ-C03']),
        ('TZ-S04', '配置和账单映射合并', '区分浅层所有权、覆盖和同键累加', ['TZ-U04', 'TZ-C04'])]
    build_project('toolz', {'title': 'Toolz纯函数数据工作场景', 'category': '函数式管道与聚合',
        'description': '固定真实源码上的组合分批、缓存键、区域归约和映射合并八项独立只读任务。'},
        definitions, scenes, materials)


if __name__ == '__main__':
    main()
