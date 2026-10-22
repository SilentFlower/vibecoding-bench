"""制作真实解析边界、结果投影与源码位置任务。"""
from draft_content import build_project


def main() -> None:
    """冻结六项独立语法任务和完整的诊断材料入口。@return None。"""
    materials = {
        'materials/full-input.md': 'For rule=Word(nums),compare rule.parse_string("12 trailing") with parse_all=True,and the complete valid control"12". A quantity import must explicitly decide whether trailing material is acceptable. Explain actual tokens and errors without editing files or pretending prefix success establishes complete-record validation.\n',
        'materials/named-results.md': 'Parse"tea book" with OneOrMore(Word(alphas)("item")) and separately OneOrMore(Word(alphas)("item*")),both parse_all=True. Compare as_list(),as_dict() and the named lookup. Explain which projection preserves all repeated named values;do not say the token stream itself lost tea. No edits.\n',
        'materials/alternatives.md': 'Use short=Literal("a"),long=Literal("ab") and the input"ab". Compare short|long with and without parse_all=True,long|short with parse_all=True,and short^long with parse_all=True. Advise ordered-first versus longest selection for a command grammar. Include the actual failing control;do not claim end-of-input checking retries every successful alternative. No implementation.\n',
        'materials/action-composition.md': 'Define integer=Word(nums).set_parse_action(lambda tokens:int(tokens[0])). On independent copies compare .set_parse_action(lambda tokens:tokens[0]*2) and .add_parse_action(lambda tokens:tokens[0]*2),then parse"5" and inspect both types/values and the original rule result. A unit-conversion grammar must own whether its original conversion is replaced or composed. No edits or implicit deep-copy guarantee for arbitrary parse-action state.\n',
        'materials/source-map-plan.md': 'The original text is exactly a tab followed by价格=12. Compare Suppress("价格=")+Located(Word(nums)) with a separately built copy using parse_with_tabs(),both parse_all=True. Inspect locn_start,locn_end,the slice of the original Python string,and the UTF-8 byte length of the prefix. Plan editor diagnostics/source maps that explicitly identify raw versus expanded input,character versus byte coordinates and end exclusivity. Do not use expanded-string offsets directly on original bytes. No implementation.\n',
        'disclosure/memoization-order.md': 'Complete isolated sequence: ParserElement.disable_memoization();ParserElement.enable_packrat();ParserElement.enable_left_recursion(). The final call raises RuntimeError("Packrat and Bounded Recursion are not compatible"). A separate clean control disables memoization,then enables left recursion and parses an actual Forward expression E <<= E+"+"+Word(nums)|Word(nums) on"1+2+3",obtaining ["1","+","2","+","3"]. The diagnostic then disables its own global mode. No other component is running during this control. Explain the class-global incompatibility and explicit application initialization ownership;do not silently force-switch shared runtime mode or claim separate parser instances isolate these flags. No edits.\n',
        'disclosure/unavailable.md': 'The complete grammar construction,process-global parser-mode initialization order,exception and isolated controls cannot be supplied. No complete reproduction distinguishes a grammar error from global mode configuration.\n'}
    definitions = [
        ('PP-U01', 'understand', '区分数量前缀匹配与完整记录验收',
            'Explain the complete prefix/full-input controls and actual tokens/errors. No edits.',
            ['materials/full-input.md'], 'explained',
            'Default parse_string accepts the12 prefix and returns[12 as a string] despite trailing text. parse_allTrue rejects that supplied dirty record with ParseException,and the complete12 control succeeds. Explicit parse_all or an appropriate StringEnd is needed when the whole record must match;prefix acceptance is an existing API choice,not complete quantity validation.',
            ['whole_input_acceptance_requires_an_explicit_end_check']),
        ('PP-U02', 'understand', '追踪重复命名结果的不同投影',
            'Explain both token lists and named dictionaries from the complete repeated-value controls. No edits.',
            ['materials/named-results.md'], 'explained',
            'Both as_list views contain tea and book. The ordinary repeated item result name overwrites the named projection with book;item* uses all-matches collection and as_dict gives item:[tea,book]. Select the intended result-name policy and retain the distinction between positional tokens and named views;do not call this loss of parsed tokens.',
            ['named_result_overwrite_and_all_matches_are_different_views']),
        ('PP-C01', 'consult', '选择有序备选或最长规则',
            'Advise command grammar choice semantics using all complete success/failure controls. No edits.',
            ['materials/alternatives.md'], 'advice_no_code_change',
            'The | MatchFirst chooses short a first;without parse_all that prefix succeeds. End checking then fails on b with parse_allTrue rather than retrying the earlier successful alternative. Longer-first | or the actual ^ longest-match Or both accept ab here. Choose based on the grammar rule and preserve validation/action semantics;do not claim ^ supplies a general backtracking or performance guarantee.',
            ['ordered_choice_does_not_reconsider_a_success_for_whole_input']),
        ('PP-C02', 'consult', '保持单位转换的解析动作链',
            'Advise actual copy/set/add parse-action ownership and types from every supplied control. No implementation.',
            ['materials/action-composition.md'], 'advice_no_code_change',
            'set_parse_action replaces the earlier integer conversion,so its copied rule repeats the original string5 and yields string55. add_parse_action retains int conversion first and yields integer10. The original independent rule still yields integer5. Copy before specializing a reusable rule and deliberately choose replacement versus composition;these copies do not promise deep cloning of arbitrary external closure state.',
            ['parse_action_replacement_and_append_require_deliberate_rule_copies']),
        ('PP-P01', 'plan', '规划含制表符与中文的源码位置映射',
            'Plan original-source coordinate mapping using the actual Located controls. No implementation.',
            ['materials/source-map-plan.md'], 'planned_without_library_change',
            'Default parsing expands the leading tab,so the numeric span is11..13 in that expanded string. parse_with_tabs preserves raw Python character coordinates4..6,and slicing the supplied original gives12;the UTF-8 prefix is8 bytes,so character4 is not byte4. Own raw/expanded normalization,character/byte conversion and exclusive-end mapping explicitly. Test tabs,Unicode and end boundaries and preserve source provenance before displaying or applying edits.',
            ['source_spans_must_name_tab_and_character_vs_byte_coordinates']),
        ('PP-D01', 'diagnose', '先核全局初始化再定位语法组合错误',
            'A grammar works alone but initialization fails when another parser component is loaded. Request complete grammar/mode setup order,the exact exception and clean controls before diagnosing. No edits.',
            [], 'diagnosed_or_information_requested',
            'Use only actually consumed initialization/exception evidence. Request missing global calls and grammar controls before choosing a cause. Once complete evidence is supplied,trace the actual class-global modes and relevant compatibility guard,then advise explicit application initialization ownership and tested grammar choice without a silent shared-mode switch. Missing material supports insufficient_information;no source patch or concurrency guarantee is authorized.', None)]
    scenes = [
        ('PP-S01', '记录和结果验收', '分清完整输入与命名投影', ['PP-U01', 'PP-U02']),
        ('PP-S02', '规则与动作组合', '显式选择备选和转换链', ['PP-C01', 'PP-C02']),
        ('PP-S03', '编辑器位置映射', '持有原文和坐标体系', ['PP-P01']),
        ('PP-S04', '语法初始化诊断', '先核模式和异常证据', ['PP-D01'])]
    build_project('pyparsing', {'title': 'Pyparsing文本导入工作场景', 'category': '输入验收、语法组合与坐标',
        'description': '完整输入、重复结果、备选规则、动作组合、源码映射和模式诊断六项任务。'},
        definitions, scenes, materials,
        branches={'PP-D01': [{'id': 'complete-mode-reproduction',
            'when': 'The complete grammar/mode initialization order,exception and isolated controls have not been supplied or declared unavailable,and sufficient evidence is reasonably requested.',
            'materials': ['disclosure/memoization-order.md']}]},
        extra_entries={'PP-S04': [{'id': 'unavailable', 'task_ids': ['PP-D01'],
            'materials': ['disclosure/unavailable.md']}]})


if __name__ == '__main__':
    main()
