"""制作商户模板语言语义、数据合同与受控渲染方案。"""
import json
from pathlib import Path

from draft_content import build_project


def main() -> None:
    """冻结七项有实际渲染业务价值的独立任务。@return None。"""
    rows = [
        ('LQ-U01', 'understand', '解释Liquid条件真值', 'Render {% if x %}yes{% else %}no{% endif %} for x=0,"",[],False,None with the supplied Environment defaults. Compare the intended business meaning with Python truthiness. No edits.',
            'Liquid treats0,empty string and empty list as truthy;False and None are falsey. Results are yes,yes,yes,no,no. Write an explicit emptiness/value predicate when business logic needs one;do not translate Python if behavior mechanically or treat zero inventory as missing.', 'liquid_truthiness_differs_from_python_for_zero_and_empty_containers'),
        ('LQ-U02', 'understand', '解释默认值过滤器的空值策略', 'Render {{ x | default: "fallback" }}|{{ x | default: "fallback", allow_false: true }} for x=0,False,"",None. Explain why this filter differs from a plain if. No edits.',
            'Outputs are0|0,fallback|false,fallback|fallback,fallback|fallback. Numeric zero is retained;allow_false preserves explicit False,but empty strings and nil still use the fallback. Define per-field nil/false/empty policy instead of treating default as a generic Python-or or validation function.', 'default_filter_distinguishes_numeric_zero_false_and_empty'),
        ('LQ-U03', 'understand', '解释模板片段的变量作用域', 'DictLoader provides p="{{ x }}{% assign x = \'inner\' %}". Compare templates that assign x="outer",then include "p" or render "p",then output |{{ x }}. No other globals or named arguments are supplied. No edits.',
            'include renders outer and changes the caller local x to inner,so outer|inner. render uses an isolated partial scope with no caller local x and does not change caller x,so |outer. Pass named data explicitly for reusable render snippets;do not call include/render equivalent or infer all globals are inaccessible.', 'include_shares_local_assignments_while_render_has_an_isolated_partial_scope'),
        ('LQ-C01', 'consult', '选择HTML输出的转义策略', 'Compare Environment() with Environment(autoescape=True) when rendering {{ x }} and plain context x="<b>A&B</b>". Advise a browser-output policy without displaying or executing the value. No implementation.',
            'Default autoescape=False emits the raw string;explicit True emits &lt;b&gt;A&amp;B&lt;/b&gt;. Choose escaping for the actual output context,keep untrusted values plain,and separately review safe/Markup values,custom filters and URL/attribute consumers. This fixed output probe is not a complete sandbox or a promise that every browser context is safe.', 'html_autoescaping_must_be_explicitly_selected_for_plain_context_values'),
        ('LQ-C02', 'consult', '选择模板缺失数据处理方式', 'Render A{{ user.name }}B with no user data using default undefined and StrictUndefined. Advise report validation/error handling and optional-field policy. No edits.',
            'Default Undefined silently yields AB;StrictUndefined raises UndefinedError when the missing value is consumed. Validate required report data and choose explicit optional fallbacks/error reporting before publication. Distinguish strict variable handling from tag/filter tolerance and do not claim defaults validate completeness.', 'missing_context_is_silent_by_default_and_rejected_by_strict_undefined'),
        ('LQ-P01', 'plan', '规划有资源边界的模板渲染', 'Set env.loop_iteration_limit=2 and render {% for x in xs %}{{ x }}{% endfor %} for xs=[1,2] and [1,2,3]. Inspect the default limit and other defined Environment limits. Plan finite rendering budgets,loader isolation and error publication;no implementation or real-service access.',
            'The two-item control yields12;the three-item control raises LoopIterationLimitError;the default loop limit is None. Plan explicit loop/output/namespace/context and external process time/memory budgets,restricted template loaders and reviewed filters,plus failure handling without publishing partial reports. Test nested/recursive/oversized cases against actual configured limits. A loop limit alone is not a complete sandbox or application authorization boundary.', 'finite_loop_limit_is_enforced_but_is_not_a_complete_sandbox')]
    definitions, materials, answers = [], {}, {}
    outcomes = {'understand': 'explained', 'consult': 'advice_no_code_change', 'plan': 'planned_without_library_change'}
    for identifier, kind, title, prompt, requirement, field in rows:
        path = 'materials/' + identifier.lower() + '.md'
        materials[path] = prompt + '\n'
        definitions.append((identifier, kind, title, prompt, [path], outcomes[kind], requirement, [field]))
        answers[identifier] = requirement + ' No changes were made.'
    definitions.append(('LQ-D01', 'diagnose', '诊断复合条件与预期不一致', 'A compound Liquid condition differs from a Python-style expectation. Request the complete expression,actual inputs,parser flags and branch output before diagnosing. No edits.', [], 'diagnosed_or_information_requested',
        'Use consumed logical-parser evidence to explain the actual association and propose a separately tested template decomposition. Missing evidence supports insufficient_information;do not assume Python precedence or promise unsupported parentheses.', None))
    materials['disclosure/logical.md'] = 'Default Environment renders {% if false and true or true %}yes{% else %}no{% endif %} as no. No custom values/tags/operators are present. Logical binary expressions associate from right to left: false and (true or true). The default logical_parentheses flag is False. The report author expected the Python expression (False and True) or True to be True.\n'
    materials['disclosure/unavailable.md'] = 'The exact expression,inputs,parser flags and branch control are unavailable.\n'
    answers.update({'LQ-D01-question': 'Please provide the complete Liquid expression,actual inputs,parser flags and exact branch output. I need the language-level control before diagnosing;no edits are authorized.',
        'LQ-D01': 'The supplied logical expression associates right to left,so it evaluates false and (true or true),which is false. Python precedence yields a different result for the analogous text. Rewrite the intended condition as explicit nested template decisions or a precomputed typed context value and test all truth-table cases. Default parentheses are disabled;do not prescribe them as already supported. No package change was made.',
        'LQ-D01-unavailable': 'Expression/input/flags and output controls are unavailable. Record insufficient_information and request them later;the cause cannot be established. No edits.'})
    build_project('python-liquid', {'title': 'Liquid商户模板工作场景', 'category': '语言语义、数据与渲染边界',
        'description': '真值、默认值、片段作用域、转义、缺失字段、资源方案及复合条件诊断。'}, definitions,
        [('LQ-S01', '模板语言语义', '正确处理值与片段', ['LQ-U01', 'LQ-U02', 'LQ-U03']),
         ('LQ-S02', '报告输出策略', '明确转义与缺失数据', ['LQ-C01', 'LQ-C02']),
         ('LQ-S03', '受控渲染方案', '界定资源和数据访问', ['LQ-P01']),
         ('LQ-S04', '条件表达式诊断', '核实际语言规则', ['LQ-D01'])], materials,
        branches={'LQ-D01': [{'id': 'logical-association', 'when': 'Exact expression,inputs,flags and output controls have not been supplied or declared unavailable and are reasonably requested.', 'materials': ['disclosure/logical.md']}]},
        extra_entries={'LQ-S04': [{'id': 'unavailable', 'task_ids': ['LQ-D01'], 'materials': ['disclosure/unavailable.md']}]},
        license_files=['seed/library/LICENSE', 'seed/library/tests/golden-liquid/LICENSE'])
    Path(__file__).with_name('python-liquid-answers.json').write_text(json.dumps(answers, indent=2) + '\n')


if __name__ == '__main__':
    main()
