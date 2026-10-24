"""公开可变参数完整类型验证回归。"""
import pytest
import jmespath
from jmespath import functions
from jmespath.exceptions import JMESPathTypeError

def test_later_builtin_merge_argument_has_controlled_type_error():
    with pytest.raises(JMESPathTypeError):
        jmespath.search('merge(a,b)',{'a':{},'b':'bad'})

def test_late_custom_argument_is_checked_before_body_runs():
    calls=[]
    class Custom(functions.Functions):
        @functions.signature({'types':['number']},{'types':['string'],'variadic':True})
        def _func_typed(self,number,*values):
            calls.append(1)
            return list(values)
    with pytest.raises(JMESPathTypeError):
        jmespath.search("typed(`1`, 'ok', `false`)",{},options=jmespath.Options(custom_functions=Custom()))
    assert calls==[]

def test_valid_variadic_and_untyped_functions_still_work():
    assert jmespath.search('merge(a,b,c)',{'a':{'x':1},'b':{'y':2},'c':{'x':3}})=={'x':3,'y':2}
    assert jmespath.search('not_null(a,b,c)',{'a':None,'b':False,'c':3}) is False

def test_array_subtype_rule_applies_to_each_variadic_value():
    class Custom(functions.Functions):
        @functions.signature({'types':['array-number'],'variadic':True})
        def _func_arrays(self,*values):
            return len(values)
    with pytest.raises(JMESPathTypeError):
        jmespath.search('arrays(a,b)',{'a':[1],'b':[True]},options=jmespath.Options(custom_functions=Custom()))
