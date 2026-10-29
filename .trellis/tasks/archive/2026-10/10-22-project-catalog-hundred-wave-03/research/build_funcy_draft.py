"""制作本地数据管道、惰性消费和重试范围的独立任务。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结六项真实管道决策，不把函数拆分成重复任务。@return None。"""
    rows = [
        ('FU-U01', 'understand', '解释惰性管道的执行时点', 'A convert callback records its argument and doubles it. Create funcy.map(convert,[1,2,3]),inspect calls,consume one item,then the rest and repeat consumption. Compare funcy.lmap(convert,[4,5]). Explain evaluation and one-shot behavior. No edits.',
            'map initially calls nothing;next yields2 and records1;remaining consumption gives4,6 and records2,3. The exhausted iterator yields nothing on a second pass. lmap immediately records4,5 and returns[8,10]. Choose an explicit materialization boundary when later steps need replay or failure detection;do not infer work completed when the iterator was constructed.', 'map_defers_work_and_is_consumed_while_lmap_eagerly_materializes'),
        ('FU-U02', 'understand', '避免空值清理删除有效零值', 'Compare list(funcy.keep([None,0,False,"",2,"ok"])) with funcy.filter(lambda value:value is not None,[None,0,False,""]). Explain a quantity/flag cleanup contract. No edits.',
            'keep retains only[2,"ok"],discarding all falsey values including0,False and empty text. An explicit non-None predicate retains[0,False,""];choose it if only None means missing. Do not silently remove valid zero quantities or explicit negative flags under a generic cleanup label.', 'keep_discards_all_falsey_values_including_valid_zero_and_false'),
        ('FU-C01', 'consult', '选择记录去重的保留策略', 'For rows [{"id":2,"value":"first"},{"id":1,"value":"x"},{"id":2,"value":"last"}],use distinct(rows,key=operator.itemgetter("id")). Advise first/last/conflict semantics and output order. No implementation.',
            'The explicit key retains the first id2 record and then id1 in input order;it does not sort,merge or keep the latest duplicate. Choose a business-approved conflict policy and explicit hashable identity key,retain conflict evidence if payload differences matter,and bound seen-set memory for large streams. Do not replace itemgetter with a string shorthand without checking its actual interpretation.', 'distinct_retains_the_first_record_per_explicit_hashable_key'),
        ('FU-C02', 'consult', '评估惰性分流的缓存边界', 'A generator logs and yields0,1,2,3. Split with funcy.split(lambda value:value%2==0,source). Exhaust the passed iterator first,inspect the source log,then consume the failed iterator. Advise a long-stream consumption strategy. No edits.',
            'The first branch yields0,2 but advances the shared source through all four inputs,buffering1,3 for the second branch. Lazy split therefore does not guarantee bounded memory when branches progress unevenly. Consume with a coordinated bounded policy or explicitly spool bounded inputs;do not claim independent source scans or constant memory.', 'lazy_split_shares_input_and_buffers_the_unconsumed_branch'),
        ('FU-P01', 'plan', '规划重试的业务副作用边界', 'A local @retry(3,errors=ValueError,timeout=0) callback appends an effect marker before raising ValueError on its first two calls and succeeding on its third. Inspect markers and plan an idempotent request/retry contract. Do not call services or implement anything.',
            'tries3 is three total attempts;the control succeeds on the third with three effect markers. A retry does not roll back prior effects. Plan stable operation identity,deduplication or transactional publication at the actual effect owner,explicit retryable error classification,finite budgets and retained attempts. Do not equate a response failure with an unapplied operation or claim this decorator itself provides exactly-once effects.', 'retry_repeats_prior_side_effects_and_counts_total_attempts')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('FU-D01', 'diagnose', '诊断缓存列表被下游修改', 'A memoized report function seems to return contaminated data. Request the decorator,complete calls,returned object identity and any mutation before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed cache/reference evidence to distinguish reused mutable return objects from recomputation or key collisions. Missing controls support insufficient_information. Propose a separately tested ownership/copy policy without clearing private cache state or altering package semantics.', None))
    materials['disclosure/memoized-list.md'] = 'Exact code:@memoize def make(x):return[x]. a=make(1);a.append("changed");b=make(1). a is b is True and b==[1,"changed"]. The callback counter remains1. No custom key_func,threads or invalidation are involved. The source stores and returns the same value object in memory[key].\n'
    materials['disclosure/unavailable.md'] = 'Exact decorator,calls,object identity and mutation sequence are unavailable.\n'
    answers.update({'FU-D01-question': 'Please provide the exact memoize/cache decorator,complete calls,returned object identities and mutations. I need an isolated ownership control before assigning a cause;no edits are authorized.',
        'FU-D01': 'The cache returns the same stored list object for the same key;the caller appends to that list,so later reads observe the mutation without recomputation. This is shared mutable-result ownership,not evidence of a key collision. Choose immutable cached results or explicit defensive copying at a validated caller boundary,and test identity/mutation/invalidation cases. No private cache clearing or source patch was made.',
        'FU-D01-unavailable': 'The decorator/calls/identity/mutation controls are unavailable. Record insufficient_information and request them later;no exact cause is established. No changes.'})
    build_project('funcy', {'title': 'Funcy本地数据管道工作场景', 'category': '惰性、去重与副作用',
        'description': '惰性执行、有效假值、保序去重、分流缓存、重试方案及可变缓存结果诊断。'}, definitions,
        [('FU-S01', '数据消费与清理', '明确执行时点和有效值', ['FU-U01', 'FU-U02']),
         ('FU-S02', '流处理策略', '明确重复身份与内存边界', ['FU-C01', 'FU-C02']),
         ('FU-S03', '重试业务方案', '界定副作用与去重', ['FU-P01']),
         ('FU-S04', '缓存结果诊断', '取得完整引用与修改证据', ['FU-D01'])], materials,
        branches={'FU-D01': [{'id': 'mutable-memoized-result', 'when': 'Exact decorator,calls,identity and mutation controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/memoized-list.md']}]},
        extra_entries={'FU-S04': [{'id': 'unavailable', 'task_ids': ['FU-D01'], 'materials': ['disclosure/unavailable.md']}]},
        license_files=['seed/library/LICENSE', 'seed/library/docs/_static/nhpup_1.1.js',
            'seed/app/Django-1.4-LICENSE.txt', 'seed/app/CC-BY-SA-3.0.html', 'seed/app/THIRD_PARTY_NOTICES.txt'])
    Path(__file__).with_name('funcy-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
