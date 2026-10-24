"Public regression tests for JINJA-O05-DEV; the complete business contract is in materials/JINJA-O05-DEV-contract.md."
from jinja2 import Environment,DictLoader,TemplatesNotFound,TemplateSyntaxError,UndefinedError,StrictUndefined
import asyncio
import pytest

def test_import_and_from_ordered_candidates_with_context():
    "Verify import and from ordered candidates with context."
    env=Environment(loader=DictLoader({'default':'{% macro show() %}{{label|default("fallback")}}{% endmacro %}','theme':'{% macro show() %}theme{% endmacro %}'}))
    assert env.from_string('{% import ["missing","default"] as m with context %}{{m.show()}}').render(label='chosen')=='chosen'
    assert env.from_string('{% from candidates import show %}{{show()}}').render(candidates=['missing','theme','default'])=='theme'

def test_all_missing_empty_and_selected_syntax_error_not_skipped():
    "Verify all missing empty and selected syntax error not skipped."
    env=Environment(loader=DictLoader({'bad':'{% if %}','good':'{% macro x() %}ok{% endmacro %}'}))
    for candidates in [[],['none','absent']]:
        with pytest.raises(TemplatesNotFound):env.from_string('{% import candidates as m %}').render(candidates=candidates)
    with pytest.raises(TemplateSyntaxError):env.from_string('{% import ["bad","good"] as m %}').render()

def test_async_string_import_and_missing_macro_behavior():
    "Verify async string import and missing macro behavior."
    loader=DictLoader({'macros':'{% macro x() %}value{% endmacro %}'})
    env=Environment(loader=loader,enable_async=True)
    assert asyncio.run(env.from_string('{% import ["none","macros"] as m %}{{m.x()}}').render_async())=='value'
    assert Environment(loader=loader).from_string('{% import "macros" as m %}{{m.x()}}').render()=='value'
    with pytest.raises(UndefinedError):Environment(loader=loader,undefined=StrictUndefined).from_string('{% from ["macros"] import missing %}{{missing()}}').render()
