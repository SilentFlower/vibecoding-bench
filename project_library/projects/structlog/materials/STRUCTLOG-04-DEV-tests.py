"""路径字段投影只输出声明范围，字面点号不改解释。"""
import unittest
from structlog.processors import EventProjector

def test_nested_order_summary_and_literal_key_list_identity():
    """客户名和订单金额按明确路径，不调用业务对象getter。@return None。"""
    payload=[];source={'event':'order','customer':{'name':'Ada'},'orders':[{'total':payload}],'literal.key':None,'secret':'omit'}
    result=EventProjector({'name':('customer','name'),'total':('orders',0,'total'),'null':('literal.key',)},keep=['event'])(None,'info',source)
    assert result=={'event':'order','name':'Ada','total':payload,'null':None}
    assert result['total'] is payload and 'secret' not in result and source['secret']=='omit'

def test_missing_policies_zero_indices_and_configuration_collisions():
    """显式None与缺项不同，路径不会当字符串逐字符走。@return None。"""
    source={'x':None}
    assert EventProjector({'value':('x',),'absent':('y',)},missing='omit')(None,'info',source)=={'value':None}
    assert EventProjector({'absent':('y',)},missing='default',default=False)(None,'info',source)=={'absent':False}
    with unittest.TestCase().assertRaises(KeyError):EventProjector({'absent':('y',)})(None,'info',source)
    with unittest.TestCase().assertRaises(TypeError):EventProjector({'bad':'a.b'})
    with unittest.TestCase().assertRaises(ValueError):EventProjector({'x':('y',)},keep=['x'])

