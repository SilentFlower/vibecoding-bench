"Public regression tests for STRUCTLOG-04-DEV; the complete business contract is in materials/STRUCTLOG-04-DEV-contract.md."
import unittest
from structlog.processors import EventProjector

def test_nested_order_summary_and_literal_key_list_identity():
    "Verify nested order summary and literal key list identity."
    payload=[];source={'event':'order','customer':{'name':'Ada'},'orders':[{'total':payload}],'literal.key':None,'secret':'omit'}
    result=EventProjector({'name':('customer','name'),'total':('orders',0,'total'),'null':('literal.key',)},keep=['event'])(None,'info',source)
    assert result=={'event':'order','name':'Ada','total':payload,'null':None}
    assert result['total'] is payload and 'secret' not in result and source['secret']=='omit'

def test_missing_policies_zero_indices_and_configuration_collisions():
    "Verify missing policies zero indices and configuration collisions."
    source={'x':None}
    assert EventProjector({'value':('x',),'absent':('y',)},missing='omit')(None,'info',source)=={'value':None}
    assert EventProjector({'absent':('y',)},missing='default',default=False)(None,'info',source)=={'absent':False}
    with unittest.TestCase().assertRaises(KeyError):EventProjector({'absent':('y',)})(None,'info',source)
    with unittest.TestCase().assertRaises(TypeError):EventProjector({'bad':'a.b'})
    with unittest.TestCase().assertRaises(ValueError):EventProjector({'x':('y',)},keep=['x'])

