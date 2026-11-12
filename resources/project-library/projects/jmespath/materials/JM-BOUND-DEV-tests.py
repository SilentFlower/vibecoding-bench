"Public regression tests for JM-BOUND-DEV; the complete business contract is in materials/JM-BOUND-DEV-contract.md."
from collections import OrderedDict
from jmespath import Options
from jmespath.bound import BoundExpression

def test_options_container_is_snapshotted_at_binding():
    options=Options(dict_cls=OrderedDict);query=BoundExpression('{b:b,a:a}',options)
    options.dict_cls=dict
    assert type(query.search({'a':1,'b':2})) is OrderedDict

def test_explicit_none_and_single_call_override_do_not_change_binding():
    query=BoundExpression('{a:a}',Options(dict_cls=OrderedDict))
    assert type(query.search({'a':1},options=None)) is dict
    assert type(query.search({'a':1})) is OrderedDict

def test_literal_results_remain_detached_and_expression_is_readable():
    query=BoundExpression('`{"a":[]}`');first=query.search({});first['a'].append(1)
    assert query.search({})=={'a':[]} and query.expression=='`{"a":[]}`'

def test_input_field_results_preserve_original_identity():
    values=[];query=BoundExpression('items')
    assert query.search({'items':values}) is values
