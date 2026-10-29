"""核Liquid语言真值、缺失数据、HTML输出和片段作用域。"""
from json import dumps
from os import environ
from pathlib import Path
from sys import argv

import liquid
from liquid import DictLoader, Environment, StrictUndefined
from liquid.exceptions import LoopIterationLimitError, UndefinedError


def main() -> None:
    """只渲染本地固定字符串，不开放真实文件或服务。@return None。"""
    root = Path(environ['PROJECT_CANDIDATE_ROOT']).resolve()
    result = {'candidate_import': Path(liquid.__file__).resolve() == root / 'library/liquid/__init__.py'}
    task = argv[1]
    if task == 'LQ-U01':
        template = Environment().from_string('{% if x %}yes{% else %}no{% endif %}')
        result['liquid_truthiness_differs_from_python_for_zero_and_empty_containers'] = (
            [template.render(x=value) for value in (0, '', [], False, None)] == ['yes', 'yes', 'yes', 'no', 'no'])
    elif task == 'LQ-U02':
        template = Environment().from_string('{{ x | default: "fallback" }}|{{ x | default: "fallback", allow_false: true }}')
        result['default_filter_distinguishes_numeric_zero_false_and_empty'] = (
            [template.render(x=value) for value in (0, False, '', None)] == ['0|0', 'fallback|false', 'fallback|fallback', 'fallback|fallback'])
    elif task == 'LQ-U03':
        env = Environment(loader=DictLoader({'p': '{{ x }}{% assign x = "inner" %}'}))
        outputs = [env.from_string('{% assign x = "outer" %}{% ' + tag + ' "p" %}|{{ x }}').render()
            for tag in ('include', 'render')]
        result['include_shares_local_assignments_while_render_has_an_isolated_partial_scope'] = outputs == ['outer|inner', '|outer']
    elif task == 'LQ-C01':
        value = '<b>A&B</b>'
        result['html_autoescaping_must_be_explicitly_selected_for_plain_context_values'] = (
            Environment().from_string('{{ x }}').render(x=value) == value
            and Environment(autoescape=True).from_string('{{ x }}').render(x=value) == '&lt;b&gt;A&amp;B&lt;/b&gt;')
    elif task == 'LQ-C02':
        raised = False
        try:
            Environment(undefined=StrictUndefined).from_string('A{{ user.name }}B').render()
        except UndefinedError:
            raised = True
        result['missing_context_is_silent_by_default_and_rejected_by_strict_undefined'] = (
            Environment().from_string('A{{ user.name }}B').render() == 'AB' and raised)
    elif task == 'LQ-P01':
        env = Environment()
        env.loop_iteration_limit = 2
        raised = False
        try:
            env.from_string('{% for x in xs %}{{ x }}{% endfor %}').render(xs=[1, 2, 3])
        except LoopIterationLimitError:
            raised = True
        result['finite_loop_limit_is_enforced_but_is_not_a_complete_sandbox'] = (
            raised and env.from_string('{% for x in xs %}{{ x }}{% endfor %}').render(xs=[1, 2]) == '12'
            and Environment().loop_iteration_limit is None)
    else:
        raise ValueError('未冻结的业务任务')
    print(dumps(result))


if __name__ == '__main__':
    main()
