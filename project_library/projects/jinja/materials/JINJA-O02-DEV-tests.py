"""无context include在宏/捕获帧输出内容，不能返回generator表示。"""
from jinja2 import Environment,DictLoader
import asyncio

def test_macro_nested_and_capture_output_actual_content():
    """普通/嵌套宏及set捕获块都写入自身buffer。@return None。"""
    env=Environment(loader=DictLoader({'child':'included'}))
    template=env.from_string('{% macro inner() %}{% include "child" without context %}{% endmacro %}{% macro outer() %}[{{inner()}}]{% endmacro %}{{outer()}}|{% set captured %}{% include "child" without context %}{% endset %}{{captured}}')
    assert template.render()=='[included]|included'

def test_without_context_stays_isolated_ignore_missing_and_streaming():
    """without context不能悄悄带入宏局部变量，顶层仍流式。@return None。"""
    env=Environment(loader=DictLoader({'child':'{{local|default("absent")}}'}))
    template=env.from_string('{% macro show(local) %}{% include "missing" ignore missing without context %}{% include "child" without context %}{% endmacro %}{{show("private")}}')
    assert template.render()=='absent'
    assert ''.join(env.from_string('before:{% include "child" without context %}:after').generate())=='before:absent:after'

def test_autoescape_filter_capture_and_async_parity():
    """自动转义和异步既有缓冲路径保持相同文本。@return None。"""
    text='{% macro show() %}{% filter upper %}{% include "child" without context %}{% endfilter %}{% endmacro %}{{show()}}'
    for async_mode in [False,True]:
        env=Environment(loader=DictLoader({'child':'<em>{{value}}</em>'}),autoescape=True,enable_async=async_mode)
        env.globals['value']='<x>'
        template=env.from_string(text)
        actual=asyncio.run(template.render_async()) if async_mode else template.render()
        assert actual=='<EM>&LT;X&GT;</EM>'
