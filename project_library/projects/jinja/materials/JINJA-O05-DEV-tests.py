"""宏import/from候选列表真实回退，不吞已选模板的错误。"""
from jinja2 import Environment,DictLoader,TemplatesNotFound,TemplateSyntaxError,UndefinedError,StrictUndefined
import asyncio
import pytest

def test_import_and_from_ordered_candidates_with_context():
    """首个可用宏被选择，with context仍传当前变量。@return None。"""
    env=Environment(loader=DictLoader({'default':'{% macro show() %}{{label|default("fallback")}}{% endmacro %}','theme':'{% macro show() %}theme{% endmacro %}'}))
    assert env.from_string('{% import ["missing","default"] as m with context %}{{m.show()}}').render(label='chosen')=='chosen'
    assert env.from_string('{% from candidates import show %}{{show()}}').render(candidates=['missing','theme','default'])=='theme'

def test_all_missing_empty_and_selected_syntax_error_not_skipped():
    """全部缺失保留TemplatesNotFound，存在但坏语法不能回退掩盖。@return None。"""
    env=Environment(loader=DictLoader({'bad':'{% if %}','good':'{% macro x() %}ok{% endmacro %}'}))
    for candidates in [[],['none','absent']]:
        with pytest.raises(TemplatesNotFound):env.from_string('{% import candidates as m %}').render(candidates=candidates)
    with pytest.raises(TemplateSyntaxError):env.from_string('{% import ["bad","good"] as m %}').render()

def test_async_string_import_and_missing_macro_behavior():
    """异步get-or-select再取module，普通字符串与缺宏错误不改。@return None。"""
    loader=DictLoader({'macros':'{% macro x() %}value{% endmacro %}'})
    env=Environment(loader=loader,enable_async=True)
    assert asyncio.run(env.from_string('{% import ["none","macros"] as m %}{{m.x()}}').render_async())=='value'
    assert Environment(loader=loader).from_string('{% import "macros" as m %}{{m.x()}}').render()=='value'
    with pytest.raises(UndefinedError):Environment(loader=loader,undefined=StrictUndefined).from_string('{% from ["macros"] import missing %}{{missing()}}').render()
