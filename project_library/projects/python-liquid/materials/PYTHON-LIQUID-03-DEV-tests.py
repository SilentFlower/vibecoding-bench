"Public regression tests for PYTHON-LIQUID-03-DEV; the complete business contract is in materials/PYTHON-LIQUID-03-DEV-contract.md."
import unittest
from liquid.context_schema import ContextField,ContextSchema,validate_context

def test_aggregate_missing_types_optional_nullable_and_list_positions():
    "Verify aggregate missing types optional nullable and list positions."
    schema=ContextSchema([ContextField(('user','name'),str),ContextField(('items',0,'amount'),int),ContextField(('note',),str,False),ContextField(('label',),str,True,True)])
    value={'user':{},'items':[{'amount':'bad'}],'label':None}
    problems=validate_context(value,schema)
    assert [(p.path,p.code) for p in problems]==[(('user','name'),'missing'),(('items',0,'amount'),'type')]
    assert validate_context({'user':{'name':'茶'},'items':[{'amount':3}],'label':None},schema)==()

def test_no_property_access_no_value_leak_bool_int_and_schema_errors():
    "Verify no property access no value leak bool int and schema errors."
    class Object:
        @property
        def secret(self):raise AssertionError('getter')
    schema=ContextSchema([ContextField(('obj','secret'),str),ContextField(('n',),int)])
    problems=validate_context({'obj':Object(),'n':True},schema)
    assert [x.code for x in problems]==['missing','type'] and all('True' not in x.message for x in problems)
    with unittest.TestCase().assertRaises(ValueError):ContextSchema([ContextField(('n',),int),ContextField(('n',),str)])

