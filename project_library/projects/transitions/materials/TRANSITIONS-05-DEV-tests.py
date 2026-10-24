"""多订单事件分别记录实际结果，不把AND汇总当明细。"""
import unittest
from transitions import Machine

class Order:
    """受控同步业务模型。"""
    def __init__(self,allowed,error=False):self.allowed=allowed;self.error=error
    def guard(self,*args,**kwargs):
        """按模型决定成功、拒绝或程序错误。@return bool。"""
        if self.error:raise ValueError('private business message')
        return self.allowed

def test_success_rejected_and_exception_rows_keep_input_order():
    """继续收集错误后仍处理下一订单，无跨模型事务承诺。@return None。"""
    models=[Order(True),Order(False),Order(False,True),Order(True)]
    machine=Machine(model=models,states=['draft','packed'],initial='draft',auto_transitions=False)
    machine.add_transition('pack','draft','packed',conditions='guard')
    rows=machine.dispatch_report('pack',7,reason='manual')
    assert [row['status'] for row in rows]==['succeeded','rejected','failed','succeeded']
    assert [row['model'] for row in rows]==models and [model.state for model in models]==['packed','draft','draft','packed']
    assert rows[2]['error_type']=='ValueError' and 'private' not in repr(rows[2])

def test_failfast_and_queue_rejection_before_any_execution():
    """只处理到失败项，queued明确拒绝最终凭据语义。@return None。"""
    models=[Order(False,True),Order(True)];machine=Machine(model=models,states=['a','b'],initial='a',auto_transitions=False)
    machine.add_transition('go','a','b',conditions='guard')
    rows=machine.dispatch_report('go',collect_errors=False)
    assert len(rows)==1 and models[1].state=='a'
    queued=Machine(states=['a','b'],initial='a',auto_transitions=False,queued=True);queued.add_transition('go','a','b')
    with unittest.TestCase().assertRaises(ValueError):queued.dispatch_report('go')
    assert queued.state=='a'

