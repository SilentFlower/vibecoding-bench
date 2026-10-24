"Public regression tests for TRANSITIONS-05-DEV; the complete business contract is in materials/TRANSITIONS-05-DEV-contract.md."
import unittest
from transitions import Machine

class Order:
    "Public regression fixture: Order."
    def __init__(self,allowed,error=False):self.allowed=allowed;self.error=error
    def guard(self,*args,**kwargs):
        "Support the public regression through guard."
        if self.error:raise ValueError('private business message')
        return self.allowed

def test_success_rejected_and_exception_rows_keep_input_order():
    "Verify success rejected and exception rows keep input order."
    models=[Order(True),Order(False),Order(False,True),Order(True)]
    machine=Machine(model=models,states=['draft','packed'],initial='draft',auto_transitions=False)
    machine.add_transition('pack','draft','packed',conditions='guard')
    rows=machine.dispatch_report('pack',7,reason='manual')
    assert [row['status'] for row in rows]==['succeeded','rejected','failed','succeeded']
    assert [row['model'] for row in rows]==models and [model.state for model in models]==['packed','draft','draft','packed']
    assert rows[2]['error_type']=='ValueError' and 'private' not in repr(rows[2])

def test_failfast_and_queue_rejection_before_any_execution():
    "Verify failfast and queue rejection before any execution."
    models=[Order(False,True),Order(True)];machine=Machine(model=models,states=['a','b'],initial='a',auto_transitions=False)
    machine.add_transition('go','a','b',conditions='guard')
    rows=machine.dispatch_report('go',collect_errors=False)
    assert len(rows)==1 and models[1].state=='a'
    queued=Machine(states=['a','b'],initial='a',auto_transitions=False,queued=True);queued.add_transition('go','a','b')
    with unittest.TestCase().assertRaises(ValueError):queued.dispatch_report('go')
    assert queued.state=='a'

