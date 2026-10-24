"""公开严格常量模板回归。"""
import pytest
from confuse import RootView,ConfigSource,ConfigValueError,NotFoundError
from confuse.literal import Literal

def test_boolean_number_and_nested_types_are_distinct():
    view=RootView([ConfigSource({'value':{'x':[True]}})])
    with pytest.raises(ConfigValueError): view['value'].get(Literal({'x':[1]}))
    assert view['value'].get(Literal({'x':[True]}))=={'x':[True]}

def test_mutated_constructor_input_cannot_change_contract():
    expected={'a':[1]};template=Literal(expected);expected['a'].append(2)
    assert RootView([ConfigSource({'v':{'a':[1]}})])['v'].get(template)=={'a':[1]}

def test_default_is_validated_and_each_result_is_detached():
    with pytest.raises(ValueError): Literal(True,default=1)
    view=RootView([ConfigSource({})]);template=Literal([],default=[])
    result=view['v'].get(template);result.append(1);assert view['v'].get(template)==[]

def test_required_error_and_success_copy_preserve_native_contract():
    view=RootView([ConfigSource({'v':[1]})])
    with pytest.raises(NotFoundError): view['missing'].get(Literal(1))
    result=view['v'].get(Literal([1]));result.append(2);assert view['v'].get()==[1]
