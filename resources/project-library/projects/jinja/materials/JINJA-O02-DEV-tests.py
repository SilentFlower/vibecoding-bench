"Public regression tests for JINJA-O02-DEV; the complete business contract is in materials/JINJA-O02-DEV-contract.md."
from jinja2 import Environment,DictLoader
import asyncio

def test_macro_nested_and_capture_output_actual_content():
    "Verify macro nested and capture output actual content."
    env=Environment(loader=DictLoader({'child':'included'}))
    template=env.from_string('{% macro inner() %}{% include "child" without context %}{% endmacro %}{% macro outer() %}[{{inner()}}]{% endmacro %}{{outer()}}|{% set captured %}{% include "child" without context %}{% endset %}{{captured}}')
    assert template.render()=='[included]|included'

def test_without_context_stays_isolated_ignore_missing_and_streaming():
    "Verify without context stays isolated ignore missing and streaming."
    env=Environment(loader=DictLoader({'child':'{{local|default("absent")}}'}))
    template=env.from_string('{% macro show(local) %}{% include "missing" ignore missing without context %}{% include "child" without context %}{% endmacro %}{{show("private")}}')
    assert template.render()=='absent'
    assert ''.join(env.from_string('before:{% include "child" without context %}:after').generate())=='before:absent:after'

def test_autoescape_filter_capture_and_async_parity():
    "Verify autoescape filter capture and async parity."
    text='{% macro show() %}{% filter upper %}{% include "child" without context %}{% endfilter %}{% endmacro %}{{show()}}'
    for async_mode in [False,True]:
        env=Environment(loader=DictLoader({'child':'<em>{{value}}</em>'}),autoescape=True,enable_async=async_mode)
        env.globals['value']='<x>'
        template=env.from_string(text)
        actual=asyncio.run(template.render_async()) if async_mode else template.render()
        assert actual=='<EM>&LT;X&GT;</EM>'
