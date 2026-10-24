"""渲染之前一次列出声明数据合同的问题，不运行模板过滤器。"""
import unittest
from liquid.context_schema import ContextField,ContextSchema,validate_context

def test_aggregate_missing_types_optional_nullable_and_list_positions():
    """明确数组位置与可选/空值独立，不强迫条件分支字段。@return None。"""
    schema=ContextSchema([ContextField(('user','name'),str),ContextField(('items',0,'amount'),int),ContextField(('note',),str,False),ContextField(('label',),str,True,True)])
    value={'user':{},'items':[{'amount':'bad'}],'label':None}
    problems=validate_context(value,schema)
    assert [(p.path,p.code) for p in problems]==[(('user','name'),'missing'),(('items',0,'amount'),'type')]
    assert validate_context({'user':{'name':'茶'},'items':[{'amount':3}],'label':None},schema)==()

def test_no_property_access_no_value_leak_bool_int_and_schema_errors():
    """仅Mapping/list路径，不读取任意对象属性或把bool当int。@return None。"""
    class Object:
        @property
        def secret(self):raise AssertionError('getter')
    schema=ContextSchema([ContextField(('obj','secret'),str),ContextField(('n',),int)])
    problems=validate_context({'obj':Object(),'n':True},schema)
    assert [x.code for x in problems]==['missing','type'] and all('True' not in x.message for x in problems)
    with unittest.TestCase().assertRaises(ValueError):ContextSchema([ContextField(('n',),int),ContextField(('n',),str)])

