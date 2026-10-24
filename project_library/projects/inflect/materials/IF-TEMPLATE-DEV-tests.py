"""公开受限业务报表模板回归。"""
import pytest
from inflect import engine
from inflect.templates import ReportTemplate

def test_compiled_fields_and_real_business_formats():
    template=ReportTemplate('{name}: {n:counted(child)}; {n:ordinal}; {word:article}')
    assert template.fields==('name','n','word')
    assert template.render(engine(),{'name':'A','n':2,'word':'hour'})=='A: 2 children; 2nd; an hour'

def test_literal_braces_and_values_are_not_reparsed():
    template=ReportTemplate('{{{name}}} {name}')
    assert template.render(engine(),{'name':'{bad}'})=='{{bad}} {bad}'

def test_unsafe_and_unknown_formats_fail_at_construction():
    for text in ('{x.__class__}','{x[0]}','{x!r}','{x:unknown}','{x:{y}}'):
        with pytest.raises(ValueError): ReportTemplate(text)

def test_custom_rules_join_and_original_state_are_preserved():
    target=engine();target.num(7);target.defnoun('widget','widgeten')
    result=ReportTemplate('{n:counted(widget)}: {names:join}').render(target,{'n':2,'names':iter(['a','b','c'])})
    assert result=='2 widgeten: a, b, and c' and target.persistent_count==7
